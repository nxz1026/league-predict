"""web.errors — 统一 JSON 错误结构 {code, message, detail?}。

绝不向客户端泄漏堆栈；服务端日志用 loguru 记录原始异常。
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("web.errors")


class ApiError(Exception):
    """业务异常：code 为短标识，message 为可展示文案。"""

    def __init__(self, code: str, message: str, detail: str | None = None,
                 http_status: int = status.HTTP_400_BAD_REQUEST):
        self.code = code
        self.message = message
        self.detail = detail
        self.http_status = http_status
        super().__init__(message)


class LockTimeout(Exception):
    """文件锁获取超时（内部信号，由路由层映射为 503 lock_busy）。"""

    pass


def _payload(exc_or_code, message: str, detail: str | None) -> dict:
    code = exc_or_code if isinstance(exc_or_code, str) else exc_or_code.code
    body = {"code": code, "message": message}
    if detail:
        body["detail"] = detail
    return body


def register(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=_payload(exc.code, exc.message, exc.detail),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload("http_error", str(exc.detail), None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_payload("validation_error", "请求参数不合法", str(exc.errors()[:5])),
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        # 只记服务端日志，绝不回传堆栈。
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_payload("internal_error", "服务器内部错误", None),
        )
