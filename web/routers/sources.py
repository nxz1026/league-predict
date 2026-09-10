"""web.routers.sources — 上游数据源状态（静态配置，require_auth）。

GET /api/v1/sources/status
返回：配置了哪些上游、各上游 env 键是否存在（绝不回传值）、联赛默认源映射。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from web.auth import require_auth
from web.services.datasource import SOURCE_KEYS, LEAGUES, DEFAULT_SOURCE

router = APIRouter(prefix="/api/v1", tags=["sources"])


@router.get("/sources/status")
def sources_status(request: Request,
                   _: None = Depends(require_auth)) -> dict:
    """静态上游配置状态（无敏感值）。"""
    import os
    configured = []
    enabled = {}
    for source, keys in SOURCE_KEYS.items():
        has_keys = all(os.environ.get(k) for k in keys) if keys else True
        configured.append(source)
        enabled[source] = has_keys
    return {
        "configured": configured,
        "enabled": enabled,
        "default_source": DEFAULT_SOURCE,
        "leagues": {
            league: {"name": info["name"], "data_source": info["data_source"]}
            for league, info in LEAGUES.items()
        },
    }