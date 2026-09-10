"""web.session_store — SQLite 会话存储（仅 stdlib sqlite3）。

模型：token(uuid4hex) / created(UTC epoch) / expires(UTC epoch)。
- 默认 TTL 12h（config.SESSION_TTL_SECONDS）。
- 过期行在每次访问时惰性清理（check_same_thread=False + 每请求短连接，
  线程安全无需锁）。
- 时间一律 UTC epoch 秒；展示换算 BJT 由上层负责。
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path

from web import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    token   TEXT PRIMARY KEY,
    created REAL NOT NULL,
    expires REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions (expires);
"""


def _connect() -> sqlite3.Connection:
    Path(config.SESSION_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.SESSION_DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


def create_session(ttl_seconds: int | None = None) -> str:
    """创建会话，返回 token。ttl 覆盖 config 默认值（测试用）。"""
    ttl = ttl_seconds if ttl_seconds is not None else config.SESSION_TTL_SECONDS
    token = uuid.uuid4().hex
    now = time.time()
    with _connect() as conn:
        _init_db(conn)
        conn.execute(
            "INSERT INTO sessions (token, created, expires) VALUES (?, ?, ?)",
            (token, now, now + ttl),
        )
    return token


def validate_token(token: str) -> bool:
    """token 有效（存在且未过期）则 True，并惰性清理过期行。"""
    with _connect() as conn:
        _init_db(conn)
        _purge_expired(conn)
        row = conn.execute(
            "SELECT expires FROM sessions WHERE token = ?", (token,)
        ).fetchone()
        if row is None:
            return False
        if row["expires"] < time.time():
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
            return False
        return True


def delete_session(token: str) -> None:
    """主动失效（logout）。"""
    with _connect() as conn:
        _init_db(conn)
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()


def _purge_expired(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
    conn.commit()
