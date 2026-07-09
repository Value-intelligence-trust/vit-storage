import json
import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

class _MemoryStore:
    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at and time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        expires_at = (time.monotonic() + ttl) if ttl else 0.0
        self._store[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

_memory = _MemoryStore()
_redis_client = None
_redis_checked = False

def _get_redis():
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True

    # Read from tachyon settings
    from tachyon.core.config import settings
    redis_url = settings.REDIS_URL
    if not redis_url:
        return None
    try:
        import redis.asyncio as aioredis
        _redis_client = aioredis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=0.5,
            socket_connect_timeout=1.0,
        )
        logger.info("Cache: Redis backend enabled")
    except Exception as exc:
        logger.warning("Cache: Redis unavailable (%s) — using memory fallback", exc)
        _redis_client = None
    return _redis_client
