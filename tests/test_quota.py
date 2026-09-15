"""ops.quota_ledger 常驻用例：两条越界路径（更新路径的 WHERE 守卫 / 插入路径）与 remaining 口径。

铁律同 test_store_idempotency：单连接、全部写入留在事务里，用例收尾一律 ROLLBACK（league_ing 无 DELETE，
痕迹必须主动丢弃）；连不上库 → pytest.skip 带原因，绝不 fail。source 带 pytest_ 前缀 + uuid，互不干扰。
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ingest import quota  # noqa: E402
from store import pg  # noqa: E402

DAY = "2026-09-15"


@pytest.fixture()
def conn():
    """写事务连接：用例内可自由写，收尾一律 rollback。"""
    try:
        connection = pg.connect("ing")
    except Exception as exc:  # 无库/无凭据/连不上：skip 并带上原因，不 fail
        pytest.skip(f"no db: {type(exc).__name__}: {exc}")
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _src() -> str:
    """账本主键是 (day, source)：每个用例自己的 source，不与既存行抢锁也不互相干扰。"""
    return f"pytest_quota_{uuid.uuid4().hex[:12]}"


def _used(conn, source: str) -> int:
    """账本里该 source 的已用次数（越界判定必须「一行不改」的观测点）。"""
    row = conn.execute("SELECT used FROM ops.quota_ledger WHERE day = %s AND source = %s", (DAY, source)).fetchone()
    return row[0]


def test_charge_over_cap_raises_and_leaves_ledger_untouched(conn):
    """used=cap 时再 charge → QuotaExceeded，账本 used 一行不改（越界判定在 ON CONFLICT 的 WHERE 守卫里）。"""
    source = _src()
    assert quota.charge(conn, DAY, source, cap=2, n=2) == 2
    with pytest.raises(quota.QuotaExceeded):
        quota.charge(conn, DAY, source, cap=2, n=1)
    assert _used(conn, source) == 2
    assert quota.remaining(conn, DAY, source, cap=2) == 0


def test_charge_more_than_cap_on_empty_day_is_refused(conn):
    """当日首行走 INSERT 路径（没有 WHERE 守卫）：n > cap 必须抛 QuotaExceeded 且不落行，否则出现脏账本。"""
    source = _src()
    with pytest.raises(quota.QuotaExceeded):
        quota.charge(conn, DAY, source, cap=0, n=1)
    with pytest.raises(quota.QuotaExceeded):
        quota.charge(conn, DAY, source, cap=3, n=4)
    assert conn.execute("SELECT count(*) FROM ops.quota_ledger WHERE source = %s", (source,)).fetchone()[0] == 0


def test_remaining_returns_cap_when_no_row_and_cap_minus_used_after(conn):
    """无行 → 返回 cap（满额，AF 免费档不回传剩余额度，本地账本是唯一真相）；有行 → cap - used。"""
    source = _src()
    assert quota.remaining(conn, DAY, source, cap=7) == 7
    quota.charge(conn, DAY, source, cap=7, n=3)
    assert quota.remaining(conn, DAY, source, cap=7) == 4


def test_connection_still_usable_after_quota_exceeded(conn):
    """QuotaExceeded 是应用层异常（SQL 本身没报错）：抛完事务未污染，同一连接还能接着读写。"""
    source = _src()
    assert quota.charge(conn, DAY, source, cap=1, n=1) == 1
    with pytest.raises(quota.QuotaExceeded):
        quota.charge(conn, DAY, source, cap=1, n=1)
    assert quota.remaining(conn, DAY, source, cap=1) == 0  # 读：账本照样查得到
    assert quota.charge(conn, DAY, _src(), cap=3, n=2) == 2  # 写：换一条 source 立刻可用
    assert _used(conn, source) == 1  # 失败那次一行没动
