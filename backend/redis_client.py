import asyncio
import logging
import time
from typing import Optional, Dict, Any
import redis.asyncio as aioredis
from config import REDIS_URL

logger = logging.getLogger("medibook.redis")

_redis_client: Optional[aioredis.Redis] = None
_redis_available: Optional[bool] = None


class InMemoryLockStore:
    """
    Thread-safe in-memory key-value lock store with TTL eviction.
    Acts as a transparent fallback when Redis is unavailable during local development/testing.
    """
    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def set_nx(self, key: str, value: str, ttl_seconds: int) -> bool:
        async with self._lock:
            now = time.time()
            # Clean expired
            if key in self._store:
                if self._store[key]["expires_at"] <= now:
                    del self._store[key]
                else:
                    return False
            self._store[key] = {
                "value": value,
                "expires_at": now + ttl_seconds
            }
            return True

    async def get(self, key: str) -> Optional[str]:
        async with self._lock:
            now = time.time()
            if key in self._store:
                if self._store[key]["expires_at"] <= now:
                    del self._store[key]
                    return None
                return self._store[key]["value"]
            return None

    async def ttl(self, key: str) -> int:
        async with self._lock:
            now = time.time()
            if key in self._store:
                remaining = int(self._store[key]["expires_at"] - now)
                if remaining > 0:
                    return remaining
                del self._store[key]
            return -2

    async def release(self, key: str, value: str) -> bool:
        async with self._lock:
            now = time.time()
            if key in self._store:
                if self._store[key]["expires_at"] > now and self._store[key]["value"] == value:
                    del self._store[key]
                    return True
                elif self._store[key]["expires_at"] <= now:
                    del self._store[key]
            return False

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False


_in_memory_lock_store = InMemoryLockStore()


async def get_redis() -> Optional[aioredis.Redis]:
    """Returns async Redis client singleton or None if connection fails."""
    global _redis_client, _redis_available
    if _redis_client is not None and _redis_available:
        return _redis_client

    try:
        client = aioredis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )
        await client.ping()
        _redis_client = client
        _redis_available = True
        logger.info("Connected to Redis successfully at %s", REDIS_URL)
        return _redis_client
    except Exception as e:
        _redis_available = False
        logger.warning(
            "Redis unavailable at %s (%s). Using in-memory fallback.",
            REDIS_URL,
            str(e)
        )
        return None


def get_memory_lock_store() -> InMemoryLockStore:
    return _in_memory_lock_store


async def is_redis_connected() -> bool:
    global _redis_available
    if _redis_client is None:
        await get_redis()
    return bool(_redis_available)


async def close_redis():
    global _redis_client, _redis_available
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
        _redis_available = None
