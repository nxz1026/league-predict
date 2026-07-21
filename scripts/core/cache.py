from __future__ import annotations

"""File-based API response cache (P3-2: 减少重复 API 调用).

TTL 默认 1 小时。缓存文件为 JSON 格式，含 mtime 元数据。
"""

import json
import time
import hashlib
from pathlib import Path
from typing import Any

from core.config import FOOTBALL_DIR
from core.log import logger

_CACHE_DIR: Path = FOOTBALL_DIR / ".cache"
_DEFAULT_TTL_SECONDS: float = 3600.0  # 1 hour


def _cache_key(url: str, params: dict | None = None) -> str:
    """Generate deterministic cache key from URL + params."""
    raw = url
    if params:
        raw += "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def get_cached(key: str) -> dict[str, Any] | None:
    """Read cache entry if exists and not expired."""
    cache_file = _CACHE_DIR / f"{key}.json"
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text())
        cached_at = data.get("_cached_at", 0)
        ttl = data.get("_ttl", _DEFAULT_TTL_SECONDS)
        if time.time() - cached_at > ttl:
            return None
        logger.debug(f"Cache hit: {key}")
        return data.get("_payload")
    except (json.JSONDecodeError, OSError, KeyError) as e:
        logger.debug(f"Cache read error for {key}: {e}")
        return None


def set_cache(key: str, payload: Any, ttl: float = _DEFAULT_TTL_SECONDS) -> None:
    """Write payload to cache with timestamp."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "_payload": payload,
            "_cached_at": time.time(),
            "_ttl": ttl,
        }
        cache_file = _CACHE_DIR / f"{key}.json"
        cache_file.write_text(json.dumps(entry, ensure_ascii=False))
        logger.debug(f"Cache written: {key}")
    except OSError as e:
        logger.warning(f"Cache write error for {key}: {e}")


def clear_cache() -> int:
    """Remove all cache files. Returns count of deleted files."""
    if not _CACHE_DIR.exists():
        return 0
    count = 0
        for f in _CACHE_DIR.glob("*.json"):
            f.unlink()
            count += 1
    logger.info(f"Cleared {count} cache entries")
    return count


def cached_fetch(
    fetch_fn,  # callable that returns dict/list
    cache_key: str,
    ttl: float = _DEFAULT_TTL_SECONDS,
) -> Any:
    """Wrapper: check cache first, call fetch_fn on miss.

    Args:
        fetch_fn: No-arg callable returning the data to cache.
        cache_key: String key for this request.
        TTL: Seconds before cache expires.

    Returns:
        The fetched/cached data.
    """
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    data = fetch_fn()
    set_cache(cache_key, data, ttl)
    return data
