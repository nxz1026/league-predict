"""web.routers.ai — AI 富化扩展端点（契约 §5，M3）。

- GET /api/v1/ai/status   require_auth；AI 模块可用性 + 富化数据概览。
- GET /api/v1/ai/details  require_auth；富化明细条目。

降级语义（契约 §5.5）：模块不可用 / ai_scores.json 缺失 / 读取异常，
一律 200 + {available:false, reason}，绝不 500、绝不拖垮 web 主流程。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from web.auth import require_auth
from web.services import ai

router = APIRouter(prefix="/api/v1", tags=["ai"])


@router.get("/ai/status")
def ai_get_status(request: Request, _: None = Depends(require_auth)) -> dict:
    """AI 模块状态 + 概览（限时降级）。"""
    return ai.try_ai_status()


@router.get("/ai/details")
def ai_get_details(request: Request, _: None = Depends(require_auth)) -> dict:
    """AI 富化明细（最多 50 条，按 ai_score 降序）。"""
    return ai.ai_details()