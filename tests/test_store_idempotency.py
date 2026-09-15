"""stg 装载幂等：同一文件装两遍 → 第二次 rows_ups=0 且 count(*) 不变。

铁律：league_ing 没有 DELETE，本文件所有落库写入都留在一个事务里，用例结束整体 ROLLBACK（不留痕可洗）；
连不上 league 库 → skip 并带上原因，绝不 fail。测试行带 pytest_<uuid> 标记，便于人工识别来源。
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from store import pg  # noqa: E402
from store.upsert_official import canonical_src_hash, load_file  # noqa: E402

TABLE = "jczq_offer"


@pytest.fixture()
def conn():
    """写事务连接：用例内可自由写，收尾一律 rollback。"""
    try:
        connection = pg.connect("ing")
    except Exception as exc:  # 无库/无凭据/连不上：skip，不 fail
        pytest.skip(f"no db: {type(exc).__name__}: {exc}")
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _row(tag: str) -> dict:
    return {
        "snap_ts": "2026-09-15T13:00:00Z", "jc_display_num": "周三001", "league_cn": "英超",
        "home_cn": "阿森纳", "away_cn": "曼联", "play_type": "hhad", "line": "-1",
        "options": {"home": 1.85, "draw": 3.40, "away": 3.90}, "single": True,
        "src_hash": f"pytest_{tag}", "probe": f"pytest_{tag}",
    }


def _write(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    return path


def _stored(conn, rows: list[dict]) -> int:
    """本批行的库内计数（按本地算出的 src_hash 精确定位，不掺别人的数据）。"""
    hashes = [canonical_src_hash(row) for row in rows]
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM stg.jczq_offer WHERE src_hash = ANY(%s)", (hashes,))
        return cur.fetchone()[0]


def test_first_load_inserts_every_row(conn, tmp_path):
    tag = uuid.uuid4().hex
    rows = [_row(f"{tag}-{i}") for i in range(3)]
    result = load_file(conn, _write(tmp_path / f"{tag}.jsonl", rows), TABLE)
    assert (result["rows_in"], result["rows_ups"], result["rejected_n"]) == (3, 3, 0)
    assert _stored(conn, rows) == 3


def test_second_load_of_same_file_inserts_nothing(conn, tmp_path):
    tag = uuid.uuid4().hex
    rows = [_row(f"{tag}-{i}") for i in range(3)]
    path = _write(tmp_path / f"{tag}.jsonl", rows)
    load_file(conn, path, TABLE)
    again = load_file(conn, path, TABLE)
    assert (again["rows_in"], again["rows_ups"], again["rejected_n"]) == (3, 0, 0)
    assert _stored(conn, rows) == 3  # count(*) 一次都没变


def test_same_rows_repushed_under_new_name_still_idempotent(conn, tmp_path):
    """幂等键是行内容而非文件名/到达次数：改名重推不能多出一行。"""
    tag = uuid.uuid4().hex
    rows = [_row(f"{tag}-{i}") for i in range(2)]
    load_file(conn, _write(tmp_path / f"{tag}.jsonl", rows), TABLE)
    repush = load_file(conn, _write(tmp_path / f"{tag}__repush.jsonl", rows), TABLE)
    assert repush["rows_ups"] == 0
    assert _stored(conn, rows) == 2


def test_unknown_stg_table_is_refused(conn, tmp_path):
    """表名不在 stg 七表白名单 → 直接拒绝，绝不拼出 stg 之外的 SQL。"""
    path = _write(tmp_path / "x.jsonl", [_row(uuid.uuid4().hex)])
    with pytest.raises(ValueError):
        load_file(conn, path, "fact_fixture")
