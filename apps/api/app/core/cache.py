"""Optional cache layer.

Uses Redis when REDIS_URL is configured; falls back to an in-process TTL map
otherwise (and whenever Redis is unreachable). Never a hard dependency.
"""

import json
import time
from typing import Any

from app.core.config import get_settings

_memory_store: dict[str, tuple[float, str]] = {}
_redis_client = None
_redis_failed_at = 0.0
REDIS_RETRY_SECONDS = 30


class InMemoryCache:
    async def get_json(self, key: str) -> Any | None:
        entry = _memory_store.get(key)
        if entry is None:
            return None
        expires_at, payload = entry
        if time.monotonic() > expires_at:
            _memory_store.pop(key, None)
            return None
        return json.loads(payload)

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        _memory_store[key] = (time.monotonic() + ttl, json.dumps(value, default=str))


class RedisCache:
    def __init__(self, url: str) -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(url, decode_responses=True)

    async def get_json(self, key: str) -> Any | None:
        global _redis_failed_at
        try:
            payload = await self._redis.get(key)
            return json.loads(payload) if payload else None
        except Exception:
            _redis_failed_at = time.monotonic()
            return await _fallback().get_json(key)

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        global _redis_failed_at
        try:
            await self._redis.set(key, json.dumps(value, default=str), ex=ttl)
        except Exception:
            _redis_failed_at = time.monotonic()
            await _fallback().set_json(key, value, ttl)


def _fallback() -> InMemoryCache:
    return _memory_cache


_memory_cache = InMemoryCache()


def get_cache():
    """Return the configured cache backend; degrade gracefully to memory."""
    global _redis_client, _redis_failed_at
    settings = get_settings()
    if not settings.REDIS_URL:
        return _memory_cache
    if time.monotonic() - _redis_failed_at < REDIS_RETRY_SECONDS:
        return _memory_cache
    if _redis_client is None:
        try:
            _redis_client = RedisCache(settings.REDIS_URL)
        except Exception:
            _redis_failed_at = time.monotonic()
            return _memory_cache
    return _redis_client
