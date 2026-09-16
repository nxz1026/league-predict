"""web.lifecycle — 应用启动生命周期（P0-DASH1a：自 web/api.py 逐字搬出）。

_create_app() 内闭包提升为模块级 `lifespan`；`_start_cron` 亦同，函数体一字未改。
web/api.py 装配时 `from web.lifecycle import lifespan`。
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from web import config
from web import errors


def _start_cron(app: FastAPI) -> None:
    """ENABLE_CRON=true 时启动 apscheduler（可选件，try-import 降级）。"""
    if not config.ENABLE_CRON:
        return
    try:
        from web.services.cron import start_scheduler
        start_scheduler(app)
    except Exception as exc:  # 任何异常都不许拖垮 app 启动
        errors.logger.exception("cron 启动失败（降级为不启用）: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时清理一次过期会话（幂等；正常路径有惰性清理兜底）。
    from web import session_store
    session_store.purge_expired_sessions()
    _start_cron(app)
    yield
    try:
        from web.services.cron import shutdown_scheduler
        shutdown_scheduler()
    except Exception:
        pass
