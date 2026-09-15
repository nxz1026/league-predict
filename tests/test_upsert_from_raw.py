"""raw 假块（自 INSERT）→ ref.team/fact.fixture/fact.fixture_result 行为 + I1~I4 不变式；真库单事务，收尾整体
ROLLBACK（league_ing 无 DELETE，测试不留痕），连不上库 pytest.skip。
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core.i18n import to_cn  # noqa: E402
from store import pg, upsert_fixtures, upsert_results  # noqa: E402

ENDPOINT = {"af_raw": "/fixtures", "fd_raw": "/v4/competitions/PL/matches"}
RAW_SQL = "INSERT INTO raw.{} (endpoint, params, params_hash, http_status, body) VALUES (%s, %s, %s, %s, %s)"


@pytest.fixture()
def conn():
    try:
        connection = pg.connect("ing")
    except Exception as exc:
        pytest.skip(f"no db: {type(exc).__name__}: {exc}")
    yield connection
    connection.rollback()
    connection.close()


def _q(conn, sql: str, *params) -> list[tuple]:
    return conn.execute(sql, params).fetchall()


def _put(conn, table: str, body: dict, http_status: int = 200) -> str:
    """摆一块假响应（league_ing 对 raw 有 INSERT）；返回 params_hash，让 run 只处理本用例的块。"""
    params_hash = f"fact1_{uuid.uuid4().hex}"
    conn.execute(RAW_SQL.format(table), (ENDPOINT[table], Jsonb({}), params_hash, http_status, Jsonb(body)))
    return params_hash


def _af_body(fid: int, tag: str, ft: tuple, ht: tuple, league_id: int = 39) -> dict:
    node = {"fixture": {"id": fid, "date": "2024-08-16T19:00:00+00:00", "status": {"short": "FT", "elapsed": 90}},
            "league": {"id": league_id, "season": 2024, "round": "Regular Season - 1"},
            "teams": {"home": {"id": fid + 1, "name": f"Home {tag}"}, "away": {"id": fid + 2, "name": f"Away {tag}"}},
            "score": {"halftime": {"home": ht[0], "away": ht[1]}, "fulltime": {"home": ft[0], "away": ft[1]}}}
    return {"response": [node]}


def _fd_body(fid: int, tag: str, ft: tuple, ht: tuple, home: str | None = None) -> dict:
    """最小 FD 响应：数组键 matches、驼峰 halfTime/fullTime；home 可改名以钉 aliases 合并。"""
    node = {"id": fid, "utcDate": "2024-08-16T19:00:00Z", "matchday": 1, "stage": "REGULAR_SEASON",
            "status": "FINISHED", "season": {"startDate": "2024-08-16"}, "competition": {"code": "PL"},
            "homeTeam": {"id": fid + 3, "name": home or f"FD Home {tag}"},
            "awayTeam": {"id": fid + 4, "name": f"FD Away {tag}"},
            "score": {"duration": "REGULAR", "fullTime": {"home": ft[0], "away": ft[1]},
                      "halfTime": {"home": ht[0], "away": ht[1]}}}
    return {"filters": {"season": 2024}, "matches": [node]}


COUNT_SQL = ("SELECT (SELECT count(*) FROM fact.fixture), (SELECT count(*) FROM fact.fixture_result),"
             " (SELECT count(*) FROM ref.team)")


def test_i1_idempotent_i2_two_sources_i3_no_invented_chinese_i4_fk_intact(conn):
    tag, fid = uuid.uuid4().hex, 990000101
    home = f"Home {tag}"  # 两源同一个队名 → 钉 UNIQUE(sport,name_cn) 命中时 aliases 合并
    hashes = [_put(conn, "af_raw", _af_body(fid, tag, (1, 1), (0, 1))),
              _put(conn, "fd_raw", _fd_body(fid, tag, (3, 0), (1, 0), home=home))]  # 两源 ft 故意不一致
    written, results = upsert_fixtures.run(conn, hashes), upsert_results.run(conn, hashes)
    assert (written["fixtures"], written["skipped"], results["results"], results["orphans"]) == (2, 0, 2, 0)
    counts = _q(conn, COUNT_SQL)[0]
    upsert_fixtures.run(conn, hashes)  # I1 幂等：同一份 raw 再跑一遍
    upsert_results.run(conn, hashes)
    assert _q(conn, COUNT_SQL)[0] == counts
    # I2：两源并存不塌（n_sources=2），且两源 FT 不一致的这场能被分歧视图查到
    assert _q(conn, "SELECT n_sources FROM fact.v_result_conflict WHERE fixture_id = %s", fid)[0] == (2,)
    for src, tid, name in (("api_football", fid + 1, home), ("football_data", fid + 3, home),
                           ("football_data", fid + 4, f"FD Away {tag}")):  # I3：name_cn 只能是 to_cn(原名) 的结果
        assert _q(conn, "SELECT name_cn FROM ref.team WHERE aliases->>%s = %s", src, str(tid))[0][0] == to_cn(name)
    assert _q(conn, "SELECT count(*) FROM ref.team WHERE name_cn = %s", to_cn(home))[0][0] == 1
    joined = _q(conn, "SELECT count(*) FROM fact.fixture f JOIN ref.league USING (league_key)"
                      " JOIN ref.team h ON h.team_id = f.home_team_id"
                      " JOIN ref.team a ON a.team_id = f.away_team_id WHERE f.fixture_id = %s", fid)[0][0]
    assert joined == 1  # I4：主客队与联赛都能在 ref 找到


def test_unknown_league_is_skipped_with_warning_and_403_block_never_parsed(conn, caplog):
    tag, unknown, forbidden = uuid.uuid4().hex, 990000201, 990000202
    blocked = _fd_body(forbidden, tag, (2, 0), (1, 0))  # 形态完整：若忽视 http_status，它就会写出赛果行
    hashes = [_put(conn, "af_raw", _af_body(unknown, tag, (1, 0), (0, 0), league_id=999)),
              _put(conn, "fd_raw", blocked, 403)]
    written = upsert_fixtures.run(conn, hashes)
    assert (written["fixtures"], written["skipped"], written["unknown_leagues"]) == (0, 1, ["None"])  # 不静默丢
    assert [r for r in caplog.records if r.levelname == "WARNING" and "跳过" in r.getMessage()]
    assert upsert_results.run(conn, hashes)["results"] == 0  # fixture 未落 → 赛果不落，外键不破
    assert _q(conn, "SELECT count(*) FROM fact.fixture WHERE fixture_id IN (%s, %s)", unknown, forbidden)[0][0] == 0
