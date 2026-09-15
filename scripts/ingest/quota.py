"""ops.quota_ledger 配额账本：AF 免费档不回传剩余额度头（README §3.1），本地账本是强制项。

用法：
    with pg.write_conn("ing") as conn:
        quota.charge(conn, "2026-09-15", "api_football", cap=100, n=1)
    quota.remaining(conn, day, source, cap)   # 当日无账本行 → 返回 cap（满额）
charge 在「已用 + n > cap」时抛 QuotaExceeded；越界判定由 ON CONFLICT DO UPDATE 的 WHERE 守卫原子完成，
并发下不会出现两条请求各读到"还剩 1 次"而同时扣。
注意：已有账本行的 cap 不会被 charge(cap=更大) 抬高——守卫比的是**库里的** ops.quota_ledger.cap，不是本次传入的 cap；
将来要做当日动态扩容，必须改 CHARGE_SQL 把 EXCLUDED.cap 一起 SET 并纳入守卫，否则会静默改写历史额度。
"""

from __future__ import annotations

import datetime as dt

from psycopg import Connection

DEFAULT_SOURCE = "api_football"
CHARGE_SQL = """
INSERT INTO ops.quota_ledger (day, source, used, cap) VALUES (%s, %s, %s, %s)
ON CONFLICT (day, source) DO UPDATE
  SET used = ops.quota_ledger.used + EXCLUDED.used
  WHERE ops.quota_ledger.used + EXCLUDED.used <= ops.quota_ledger.cap
RETURNING used
"""


class QuotaExceeded(RuntimeError):
    """本次请求会越过 cap。"""


def _as_day(day: dt.date | str) -> dt.date:
    return dt.date.fromisoformat(day) if isinstance(day, str) else day


def remaining(conn: Connection, day: dt.date | str, source: str = DEFAULT_SOURCE, cap: int = 0) -> int:
    """剩余可用次数；已用超过 cap 时归零。"""
    with conn.cursor() as cur:
        cur.execute("SELECT cap - used FROM ops.quota_ledger WHERE day = %s AND source = %s", (_as_day(day), source))
        row = cur.fetchone()
    return cap if row is None else max(0, row[0])


def charge(conn: Connection, day: dt.date | str, source: str = DEFAULT_SOURCE, cap: int = 100, n: int = 1) -> int:
    """占用 n 次配额并返回累计已用；超 cap 抛 QuotaExceeded（此时不落任何写）。"""
    if n < 1:
        raise ValueError("n must be >= 1")
    if n > cap:
        raise QuotaExceeded(f"{source} cap={cap} 小于本次请求 n={n}")
    with conn.cursor() as cur:
        cur.execute(CHARGE_SQL, (_as_day(day), source, n, cap))
        row = cur.fetchone()
    if row is None:
        raise QuotaExceeded(f"{source} {_as_day(day)} 配额已用尽（cap={cap}，本次请求 n={n}）")
    return int(row[0])
