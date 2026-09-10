"""web.api — FastAPI 应用工厂与开发入口。

- GET  /health    免鉴权健康检查
- 静态挂载 /login（static/login.html）；未登录 GET / → 302 /login
- 注册 auth 路由与统一异常处理
- python web/api.py 启动开发服务器（host/port 读 env，默认仅本机）
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from web import config
from web import errors
from web.auth import router as auth_router

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
APP_TITLE = "league-predict Web Dashboard"
APP_VERSION = "0.1.0"


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 启动时清理一次过期会话（幂等；正常路径有惰性清理兜底）。
        from web import session_store
        _conn = session_store._connect()
        session_store._init_db(_conn)
        session_store._purge_expired(_conn)
        yield

    app = FastAPI(title=APP_TITLE, version=APP_VERSION, lifespan=lifespan)
    errors.register(app)

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "time_utc_epoch": time.time(),
            "config": config.env_summary(),
        }

    @app.get("/")
    def index(request: Request):
        from web.auth import COOKIE_NAME
        from web import session_store
        token = request.cookies.get(COOKIE_NAME, "")
        if not token or not session_store.validate_token(token):
            return RedirectResponse(url="/login", status_code=302)
        # M1 无业务页；已登录访问 / 也先指向 /login 骨架（M4 换 index.html）。
        return RedirectResponse(url="/login", status_code=302)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/login")
    def login_page():
        return RedirectResponse(url="/static/login.html", status_code=302)

    app.include_router(auth_router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT)
