"""采集契约校验：stg 真实列结构 == 期望常量；坏行全进 rejected 且不入库；无 .done 的文件不处理。
铁律同 test_store_idempotency：单事务 + 收尾 ROLLBACK；目录一律 tmp，绝不读写 /srv/league-staging。
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from ingest.collector_pull import run  # noqa: E402
from store import pg  # noqa: E402

# stg 七表期望契约（来源 docs/db/infra_p0_2_schemas.sql；类型串按 information_schema.columns 口径）
EXPECTED_COLUMNS = [("line", "jsonb", "NO"), ("src_hash", "text", "NO"),
                    ("loaded_at", "timestamp with time zone", "NO"), ("src_file", "text", "NO")]
STG_TABLES = ["jc_issue", "jc_issue_result", "jclq_offer", "jclq_result", "jczq_offer", "jczq_result", "lottery_draw"]


@pytest.fixture()
def conn():
    """写事务连接：收尾一律 rollback（league_ing 无 DELETE，痕迹必须主动丢弃）。"""
    try:
        connection = pg.connect("ing")
    except Exception as exc:  # 无库/无凭据/连不上：skip 并带上原因，不 fail
        pytest.skip(f"no db: {type(exc).__name__}: {exc}")
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _drop(tmp_path: Path, topic: str, lines: list[str], marker: bool = True) -> tuple[Path, Path, Path, Path]:
    """摆 incoming/<host>/<topic>/<file>.jsonl（可选 .done 标记）；返回 incoming 根、done、bad、数据文件。"""
    data = tmp_path / "incoming" / "collector-host" / topic / f"2026-09-15T13-30Z__{uuid.uuid4().hex}.jsonl"
    data.parent.mkdir(parents=True)
    data.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if marker:
        data.with_name(data.name + ".done").write_text("", encoding="utf-8")
    return tmp_path / "incoming", tmp_path / "done", tmp_path / "bad", data


def _line(tag: str, **extra) -> str:
    return json.dumps({"src_hash": f"pytest_{tag}", **extra}, ensure_ascii=False)


def _q(conn, sql: str, *params) -> list[tuple]:
    return conn.execute(sql, params).fetchall()


def test_stg_schema_matches_contract(conn):
    """七张 stg 表的列名/类型/可空性必须与期望常量逐字一致（契约冻结前 stg 的唯一真相）。"""
    rows = _q(conn, "SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns"
                    " WHERE table_schema = 'stg' ORDER BY table_name, ordinal_position")
    seen: dict[str, list] = {}
    for table, column, data_type, nullable in rows:
        seen.setdefault(table, []).append((column, data_type, nullable))
    assert sorted(seen) == STG_TABLES, "stg 表集合与契约不符"
    for table, got in seen.items():
        assert got == EXPECTED_COLUMNS, f"{table} 列结构与契约不符"


def test_dirty_file_rejects_bad_lines_and_archives_to_bad(conn, tmp_path):
    """非 JSON / 非 object / 缺必需字段 → 全进 rejected 且不入库；原件进 bad/、.done 标记进 done/。"""
    tag = uuid.uuid4().hex
    good = _line(tag, snap_ts="2026-09-15T13:00:00Z", jc_display_num="周三001", play_type="had", options={"home": 1.9})
    missing = _line(f"{tag}-miss", snap_ts="2026-09-15T13:00:00Z", play_type="had", options={})
    incoming, done, bad, data = _drop(tmp_path, "jczq_offer", [good, "{not json", "[1, 2]", missing])
    size = data.stat().st_size
    assert run(conn, incoming, done, bad)[0]["rejected_n"] == 3
    assert _q(conn, "SELECT count(*) FROM stg.jczq_offer WHERE src_file = %s", data.name)[0][0] == 1  # 只落合法行
    assert _q(conn, "SELECT rows_in, rows_ups, ok, jsonb_array_length(rejected) FROM ops.ingest_log"
                    " WHERE src_file = %s", data.name)[0] == (4, 1, False, 3)
    assert _q(conn, "SELECT bytes, rows, done_marker FROM ops.file_arrival WHERE src_file = %s",
              str(data.relative_to(incoming)))[0] == (size, 4, True)
    assert not data.exists() and (bad / "collector-host/jczq_offer" / data.name).exists()
    assert (done / "collector-host/jczq_offer" / f"{data.name}.done").exists()


def test_clean_file_archives_to_done(conn, tmp_path):
    """零拒绝行 → 原件与 .done 都进 done/，ingest_log.ok = true。"""
    line = _line(uuid.uuid4().hex, game="dlt", issue_no="26001", draw_date="2026-09-15", numbers={"front": [1, 2]})
    incoming, done, bad, data = _drop(tmp_path, "lottery_draw", [line])
    assert run(conn, incoming, done, bad)[0]["rows_ups"] == 1
    assert (done / "collector-host/lottery_draw" / data.name).exists() and not (bad / "collector-host").exists()
    assert _q(conn, "SELECT ok, rows_ups FROM ops.ingest_log WHERE src_file = %s", data.name)[0] == (True, 1)


def test_file_without_done_marker_is_ignored(conn, tmp_path):
    """缺 .done（疑似半包）→ 原地不动、不入库、不留 ingest_log。"""
    line = _line(uuid.uuid4().hex, match_display_num="周三002", home_cn="阿森纳", away_cn="曼联", ft="2-1")
    incoming, done, bad, data = _drop(tmp_path, "jczq_result", [line], marker=False)
    assert run(conn, incoming, done, bad) == []  # 没标记 → 整批不处理
    assert data.exists() and not (done / "collector-host").exists() and not (bad / "collector-host").exists()
    assert _q(conn, "SELECT count(*) FROM ops.ingest_log WHERE src_file = %s", data.name)[0][0] == 0
    assert _q(conn, "SELECT count(*) FROM stg.jczq_result WHERE src_file = %s", data.name)[0][0] == 0
