"""P0-COLLECT3b2 写手测试（§9-79：单 conn 单所有者，fixture 收尾 rollback+close；
查"库最终 0 行"另开 read_conn("ro") 只读连接）：T2 回滚自证 + T3 坏行不炸批。
夹具 = tests/fixtures/odds_history/**。"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ingest import jc_odds_write  # noqa: E402
from psycopg.types.json import Json  # noqa: E402
from store import pg  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "odds_history"
ENVS = [json.loads(l) for f in ("finished_卡塔尔亚vs韩国亚__2041482.jsonl", "onsale_柏太阳神__2041495.jsonl")
        for l in (FIX / f).read_text(encoding="utf-8").splitlines()]


@pytest.fixture()
def conn():
    try:
        connection = pg.connect("ing")
    except Exception as exc:
        pytest.skip(f"no db: {type(exc).__name__}: {exc}")
    try:
        yield connection  # 用例里不要再套 closing / with
    finally:
        connection.rollback()  # 库里最终 0 行的保证
        connection.close()


def _count(cur, sql) -> int:
    return cur.execute(sql).fetchone()[0]


def test_t2_upsert_replay_then_rollback(conn):
    cur = conn.cursor()
    # 直插自检：不经容错路径，先确认 1 条能插进去
    cur.execute(jc_odds_write._SQL, [2041482, "had", datetime(2026, 9, 15, 1, 39, 39, tzinfo=timezone.utc),
                                     0, None, None, Json({"h": "3.0"}), True, False, 83, "t2", "t2"])
    assert cur.rowcount == 1
    conn.rollback()
    n = jc_odds_write.upsert_from_env(cur, ENVS[0]) + jc_odds_write.upsert_from_env(cur, ENVS[1])
    assert n == 34
    assert _count(cur, "select count(*) from fact.jc_odds_history") == 34
    assert _count(cur, "select count(*) filter (where is_first) from fact.jc_odds_history") == 10
    assert _count(cur, "select count(*) filter (where is_close) from fact.jc_odds_history") == 0
    assert _count(cur, "select count(*) filter (where goal_line is not null) from fact.jc_odds_history") == 9
    row1 = cur.execute("select last_seen_at, first_seen_at from fact.jc_odds_history "
                       "where match_id=2041482 and play_type='had' order by seq_no desc limit 1").fetchone()
    jc_odds_write.upsert_from_env(cur, ENVS[0])
    jc_odds_write.upsert_from_env(cur, ENVS[1])
    row2 = cur.execute("select last_seen_at, first_seen_at from fact.jc_odds_history "
                       "where match_id=2041482 and play_type='had' order by seq_no desc limit 1").fetchone()
    assert _count(cur, "select count(*) from fact.jc_odds_history") == 34
    assert row1[0] is not None and row2[0] is not None
    assert row2[0] >= row1[0]
    assert row2[1] == row1[1]  # first_seen_at 不在 do-update 列表里 ⇒ 重放不变
    conn.rollback()
    with pg.read_conn("ro") as c:
        assert c.execute("select count(*) from fact.jc_odds_history").fetchone()[0] == 0


def _row(play, odds, seq=0):
    return {"match_id": 2041482, "play_type": play, "update_ts": datetime(2026, 9, 15, 1, 39, 39, tzinfo=timezone.utc),
            "seq_no": seq, "goal_line": None, "goal_line_value": None, "odds": odds, "is_first": seq == 0,
            "is_close": False, "league_id": 83, "src_hash": "t3", "src_file": "t3"}


def test_t3_bad_rows_do_not_kill_batch(conn, caplog):
    cur = conn.cursor()
    rows = [_row("had", {"h": "3.0"}), _row("xxx", {"h": "3.0"}), _row("ttg", ["bad"])]
    n = jc_odds_write.upsert_jc_odds_history(cur, rows, {"src_hash": "t3", "src_file": "t3"})
    assert n == 1
    rejects = [r.getMessage() for r in caplog.records if "odds-hist-reject" in r.getMessage()]
    assert len(rejects) == 2
    assert _count(cur, "select count(*) from fact.jc_odds_history") == 1
    conn.rollback()
    with pg.read_conn("ro") as c:
        assert c.execute("select count(*) from fact.jc_odds_history").fetchone()[0] == 0
