"""采集机三个测试文件（test_collector_contract / test_collector_arrival / test_collector_v11）的共享
fixture 与 helper（P0-COLLECT1c 从 test_collector_contract.py 抽出，全仓唯一一份）：conn 单事务写连接 + 收尾 ROLLBACK；
_drop 摆 incoming/<host>/<topic>/.jsonl 与 .done 标记；_envelope 造契约 v1.1 一行（src_hash 按 §5.0 本地复算）；_q 查询。
import 方向：三个测试文件 → 本文件；本文件只 import scripts/store，单向无环。"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from store import pg  # noqa: E402
from store.parse_collector import canonical_src_hash  # noqa: E402

HOST = "collector-host"
ENDPOINT = "https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry?channel=c"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "collector_v11"


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


def _q(conn, sql: str, *params) -> list[tuple]:
    return conn.execute(sql, params).fetchall()


def _envelope(topic: str, payload: dict, **patch) -> str:
    """契约 v1.1 的一行（src_hash 按 §5.0 本地复算）；**patch 覆盖外壳字段以造坏行。"""
    line = {"kind": "line", "topic": topic, "snap_ts": "2026-09-15T13:00:00Z", "endpoint": ENDPOINT, "http_status": 200,
            "collector_host": HOST, "payload": payload, "src_hash": canonical_src_hash(payload)}
    return json.dumps(line | patch, ensure_ascii=False)


def _drop(tmp_path: Path, topic: str, lines: list[str], marker: bool = True) -> tuple[Path, Path, Path, Path]:
    """摆 incoming/<host>/<topic>/<file>.jsonl（可选 .done 标记）；返回 incoming 根、done、bad、数据文件。"""
    data = tmp_path / "incoming" / HOST / topic / f"2026-09-15T13-30Z__{uuid.uuid4().hex}.jsonl"
    data.parent.mkdir(parents=True)
    data.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if marker:
        data.with_name(data.name + ".done").write_text("", encoding="utf-8")
    return tmp_path / "incoming", tmp_path / "done", tmp_path / "bad", data
