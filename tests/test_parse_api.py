"""parse_api 纯函数契约：真报文抠出的最小片段钉死字段路径 / status 归一 / HT 缺失=NULL / aet·pen 区分。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from store.parse_api import af_fixtures, fd_fixtures  # noqa: E402

AF_NODE = {  # raw.af_raw 真报文首节点（Ligue 1 2023 第 1 轮），裁到本文件要钉的字段
    "fixture": {"id": 1044885, "date": "2023-08-11T19:00:00+00:00", "venue": {"name": "Allianz Riviera"},
                "status": {"long": "Match Finished", "short": "FT", "elapsed": 90, "extra": None}},
    "league": {"id": 61, "name": "Ligue 1", "season": 2023, "round": "Regular Season - 1"},
    "teams": {"home": {"id": 84, "name": "Nice"}, "away": {"id": 79, "name": "Lille"}},
    "score": {"halftime": {"home": 1, "away": 0}, "fulltime": {"home": 1, "away": 1},
              "extratime": {"home": None, "away": None}, "penalty": {"home": None, "away": None}},
}
FD_NODE = {  # raw.fd_raw 真报文首节点（Bundesliga 2023 第 1 轮）
    "id": 441789, "utcDate": "2023-08-18T18:30:00Z", "matchday": 1, "stage": "REGULAR_SEASON", "status": "FINISHED",
    "season": {"startDate": "2023-08-18"}, "competition": {"code": "BL1"},
    "homeTeam": {"id": 12, "name": "SV Werder Bremen"}, "awayTeam": {"id": 721, "name": "FC Bayern München"},
    "score": {"duration": "REGULAR", "fullTime": {"home": 0, "away": 4}, "halfTime": {"home": 0, "away": 1}},
}


def _af(short: str = "FT", elapsed: int = 90, league_id: int = 61, score: dict | None = None) -> dict:
    """在真节点上只改本次要钉的字段（状态/联赛/比分），其余保持真报文原样。"""
    node = {**AF_NODE, "fixture": {**AF_NODE["fixture"], "status": {"short": short, "elapsed": elapsed}},
            "league": {**AF_NODE["league"], "id": league_id}}
    return {**node, "score": score} if score is not None else node


def _af_row(**kw) -> dict:
    return af_fixtures({"response": [_af(**kw)]})[0]


def _quad(row: dict) -> tuple:
    """(FT 主, FT 客, HT 主, HT 客)：HT 那两项专门盯"缺失 NULL / 半场 0:0"之别。"""
    return (row["ft_h"], row["ft_a"], row["ht_h"], row["ht_a"])


def test_af_row_paths_come_from_the_real_payload():
    row, = af_fixtures({"response": [AF_NODE]})
    assert row["fixture_id"] == 1044885 and row["league_key"] == "ligue1"  # 61 → ref.league.ids.api_football
    assert (row["season"], row["round"]) == (2023, "Regular Season - 1")
    assert row["kickoff_at"] == "2023-08-11T19:00:00+00:00" and row["raw_node"] is AF_NODE
    assert row["af_team_id"] == (84, 79) and row["fd_team_id"] is None and row["venue"] == "Allianz Riviera"
    assert (row["home_name"], row["away_name"]) == ("Nice", "Lille")
    assert (row["status"],) + _quad(row) == ("ft", 1, 1, 1, 0)


@pytest.mark.parametrize(("short", "expected"), [("NS", "scheduled"), ("FT", "ft"), ("AET", "aet"), ("PEN", "pen"),
                                                 ("HT", "pending"), ("SUSP", "interrupted"), ("ZZZ", "unknown")])
def test_af_status_always_normalised(short, expected):
    assert _af_row(short=short)["status"] == expected


def test_af_missing_half_time_is_null_never_zero():
    """半场 0:0 与"半场没数据"必须分得开：前者 (0, 0)，后者 (None, None)。"""
    hollow = {"fulltime": {"home": 0, "away": 0}, "halftime": {"home": None, "away": None}}
    zero = {"fulltime": {"home": 0, "away": 0}, "halftime": {"home": 0, "away": 0}}
    assert (_quad(_af_row(score=zero)), _quad(_af_row(score=hollow))) == ((0, 0, 0, 0), (0, 0, None, None))
    assert _quad(af_fixtures({"response": [{k: v for k, v in AF_NODE.items() if k != "score"}]})[0]) == (None,) * 4


def test_af_elapsed_only_at_halftime_and_unknown_league_not_guessed():
    assert _af_row(short="HT", elapsed=45)["elapsed_ht"] == 45
    assert _af_row(short="FT", elapsed=90)["elapsed_ht"] is None
    assert _af_row(league_id=999)["league_key"] is None
    assert af_fixtures({"response": [_af(league_id=999)]}, {999: "epl"})[0]["league_key"] == "epl"  # 生产注入真映射


def test_fd_row_paths_come_from_the_real_payload():
    row, = fd_fixtures({"filters": {"season": 2023}, "matches": [FD_NODE]})
    assert row["fixture_id"] == 441789 and row["league_key"] == "bundesliga"  # competition.code BL1
    assert (row["season"], row["round"], row["kickoff_at"]) == (2023, "Matchday 1", "2023-08-18T18:30:00Z")
    assert row["fd_team_id"] == (12, 721) and row["af_team_id"] is None and row["venue"] is None
    assert (row["home_name"], row["away_name"]) == ("SV Werder Bremen", "FC Bayern München")
    assert (row["status"],) + _quad(row) == ("ft", 0, 4, 0, 1)  # 驼峰 halfTime/fullTime 被读到


@pytest.mark.parametrize(("status", "duration", "expected"), [("FINISHED", "REGULAR", "ft"),
                                                             ("FINISHED", "EXTRA_TIME", "aet"),
                                                             ("FINISHED", "PENALTY_SHOOTOUT", "pen"),
                                                             ("SCHEDULED", None, "scheduled"),
                                                             ("WHATEVER", None, "unknown")])
def test_fd_status_uses_status_and_duration(status, duration, expected):
    node = {**FD_NODE, "status": status, "score": {**FD_NODE["score"], "duration": duration}}
    assert fd_fixtures({"matches": [node]})[0]["status"] == expected


def test_af_and_fd_rows_share_one_key_set_and_skip_identityless_nodes():
    assert sorted(af_fixtures({"response": [AF_NODE]})[0]) == sorted(fd_fixtures({"matches": [FD_NODE]})[0])
    assert [af_fixtures({"response": [{"fixture": {"id": 1}, "league": {"id": 61}}]}),
            fd_fixtures({"matches": [{"id": None, "utcDate": "2023-08-18T18:30:00Z"}]})] == [[], []]
