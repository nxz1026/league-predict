"""align 纯函数用例 + 全链路相对增量断言（A1/A2/A6、ok_synonym 落库）。合成 raw 报文与 DB 辅助函数也在本文件，供
test_upsert_from_raw 复用；真库单事务、收尾整体 ROLLBACK（对 fact/ref 无 DELETE），连不上库 skip，断言一律相对量。"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from store import align, pg, upsert_fixtures, upsert_results  # noqa: E402

COUNT_SQL = ("SELECT (SELECT count(*) FROM fact.fixture), (SELECT count(*) FROM fact.fixture_result),"
             " (SELECT count(*) FROM ops.ingest_log)")


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
    """摆一块假响应；返回 params_hash，让 run 只处理本用例的块。"""
    digest = f"align_{uuid.uuid4().hex}"
    endpoint = "/fixtures" if table == "af_raw" else "/v4/competitions/PL/matches"
    conn.execute("INSERT INTO raw." + table + " (endpoint, params, params_hash, http_status, body)"
                 " VALUES (%s, %s, %s, %s, %s)", (endpoint, Jsonb({}), digest, http_status, Jsonb(body)))
    return digest


def _af_body(fid, tag, ft, ht, league_id=39, kick="2024-08-16T19:00:00+00:00", home=None, away=None) -> dict:
    teams = {"home": {"id": fid + 1, "name": home or f"Home {tag}"},
             "away": {"id": fid + 2, "name": away or f"Away {tag}"}}
    node = {"fixture": {"id": fid, "date": kick, "status": {"short": "FT"}},
            "league": {"id": league_id, "season": 2024, "round": "Regular Season - 1"}, "teams": teams,
            "score": {"halftime": {"home": ht[0], "away": ht[1]}, "fulltime": {"home": ft[0], "away": ft[1]}}}
    return {"response": [node]}


def _fd_body(fid, tag, ft, ht, home=None, away=None, kick="2024-08-16T19:00:00Z") -> dict:
    node = {"id": fid, "utcDate": kick, "status": "FINISHED", "competition": {"code": "PL"},
            "season": {"startDate": "2024-08-16"}, "homeTeam": {"id": fid + 3, "name": home or f"Home {tag} FC"},
            "awayTeam": {"id": fid + 4, "name": away or f"Away {tag}"},
            "score": {"fullTime": {"home": ft[0], "away": ft[1]}, "halfTime": {"home": ht[0], "away": ht[1]}}}
    return {"matches": [node]}


def _row(fid, home, away, kick="2024-08-16T19:00:00Z") -> dict:  # AF 锚点行与 FD 行同口径（align 只读这 5 键）
    return {"fixture_id": fid, "league_key": "epl", "kickoff_at": kick, "home_name": home, "away_name": away}


def test_tokens_and_match_fd_rules():  # 剥类型词/去变音符；同义表键值必须已是归一口径；同刻多场靠队名配对唯一化
    assert align.normalize_team("Cádiz CF") == align.normalize_team("Cadiz") == "cadiz"
    assert align.normalize_team("Scunthorpe United") == "scunthorpe united"  # sc 只是子串，不许误伤
    assert align.normalize_team("Club Brugge") == "brugge" and align.normalize_team(None) == ""
    assert all(align.normalize_team(k) == k and align.normalize_team(v) == v for k, v in align.TEAM_SYNONYMS.items())
    rows = [_row(11, "Newcastle", "Sevilla"), _row(12, "Inter", "Sevilla"), _row(13, "Manchester City", "Sevilla")]
    index, names = align.af_index(rows), align.af_names(rows)
    assert align.match_fd(_row(1, "Newcastle United FC", "Sevilla FC"), index, names) == ("11", align.OK)
    assert align.match_fd(_row(2, "FC Internazionale Milano", "Sevilla FC"), index, names) == ("12", align.OK_SYNONYM)
    assert align.match_fd(_row(3, "Manchester United FC", "Sevilla FC"), index, names)[1] == align.NAME_MISMATCH
    assert align.match_fd(_row(4, "FC", "Club FC"), index, names)[1] == align.NAME_MISMATCH  # 两侧剥成空集不算证据
    assert align.match_fd(_row(5, "Newcastle United FC", "Sevilla FC", "2024-08-16T19:01:00Z"), index, names)[1] \
        == align.NO_TIME
    assert align.match_fd(_row(6, "Sevilla FC", "Newcastle United FC"), index, names)[1] == align.SWAPPED
    dup = [_row(11, "Newcastle", "Sevilla"), _row(12, "Newcastle United", "Sevilla")]  # 同刻同对阵两场 ⇒ 真歧义
    index, names = align.af_index(dup), align.af_names(dup)
    assert align.match_fd(_row(7, "Newcastle United FC", "Sevilla FC"), index, names) == ("", align.AMBIGUOUS)


def test_fd_block_merges_into_af_fixture_only(conn):
    """A1/A2/A6 + ok_synonym：FD 只把 id 并进 AF fixture（不插场）；两源专名不同的行靠同义表也照样上岸。"""
    fid, fd_id, syn_fd, tag = 990010001, 550010001, 550010002, uuid.uuid4().hex
    hashes = [_put(conn, "af_raw", _af_body(fid, tag, (2, 0), (1, 0))),
              _put(conn, "af_raw", _af_body(fid + 1, tag, (1, 1), (0, 1), home="Inter")),
              _put(conn, "fd_raw", _fd_body(fd_id, tag, (2, 0), (1, 0))),
              _put(conn, "fd_raw", _fd_body(syn_fd, tag, (1, 1), (0, 1), home="FC Internazionale Milano"))]
    before, written = _q(conn, COUNT_SQL)[0], upsert_fixtures.run(conn, hashes)
    results, after = upsert_results.run(conn, hashes), _q(conn, COUNT_SQL)[0]
    assert (after[0] - before[0], written["fixtures"], written["fd_merged"], written["fd_unmatched"]) == (2, 2, 2, 0)
    assert (after[1] - before[1], results["rows"], results["unmatched"]) == (4, 4, 0)  # A2：两源各一行赛果
    assert _q(conn, "SELECT source_ids -> 'football_data' FROM fact.fixture WHERE fixture_id = %s", fid + 1) \
        == [(syn_fd,)]  # ok_synonym 也是命中：football_data id 真并进来了
    upsert_fixtures.run(conn, hashes)  # A6 幂等：同一份 raw 连跑两遍，fixture/result 计数完全一致
    upsert_results.run(conn, hashes)
    assert _q(conn, COUNT_SQL)[0] == after
