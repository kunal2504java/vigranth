"""
Redis connection pool for caching, sessions, and rate limiting.

Cache key patterns (from Architecture doc):
  feed:{user_id}                          TTL 30s   - Ranked priority feed
  contact:{user_id}:{platform}:{id}       TTL 1h    - Sender context
  thread:{platform}:{thread_id}           TTL 5min  - Full thread
  session:{token}                         TTL 24h   - User session
  platform_token:{user_id}:{platform}     Until exp - OAuth tokens
  rate:{user_id}:{endpoint}               TTL 60s   - Rate limit counter
"""
import redis.asyncio as aioredis
import json
from typing import Any, Optional
from backend.core.config import get_settings

settings = get_settings()

# Connection pool shared across the app
redis_pool = aioredis.ConnectionPool.from_url(
    settings.REDIS_URL,
    max_connections=50,
    decode_responses=True,
)

redis_client = aioredis.Redis(connection_pool=redis_pool)


class RedisCache:
    """High-level caching operations for UnifyInbox."""

    def __init__(self, client: aioredis.Redis = redis_client):
        self._r = client

    # --- Generic ---

    async def get(self, key: str) -> Optional[Any]:
        raw = await self._r.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    async def set(self, key: str, value: Any, ttl: int = 60) -> None:
        serialized = json.dumps(value) if not isinstance(value, str) else value
        await self._r.set(key, serialized, ex=ttl)

    async def delete(self, key: str) -> None:
        await self._r.delete(key)

    async def exists(self, key: str) -> bool:
        return bool(await self._r.exists(key))

    # --- Feed cache ---

    async def get_feed(self, user_id: str) -> Optional[list]:
        return await self.get(f"feed:{user_id}")

    async def set_feed(self, user_id: str, feed: list) -> None:
        await self.set(f"feed:{user_id}", feed, ttl=30)

    async def invalidate_feed(self, user_id: str) -> None:
        await self.delete(f"feed:{user_id}")

    # --- Contact cache ---

    async def get_contact(self, user_id: str, platform: str, contact_id: str) -> Optional[dict]:
        return await self.get(f"contact:{user_id}:{platform}:{contact_id}")

    async def set_contact(self, user_id: str, platform: str, contact_id: str, data: dict) -> None:
        await self.set(f"contact:{user_id}:{platform}:{contact_id}", data, ttl=3600)

    # --- Thread cache ---

    async def get_thread(self, platform: str, thread_id: str) -> Optional[list]:
        return await self.get(f"thread:{platform}:{thread_id}")

    async def set_thread(self, platform: str, thread_id: str, messages: list) -> None:
        await self.set(f"thread:{platform}:{thread_id}", messages, ttl=300)

    # --- Rate limiting ---

    async def check_rate_limit(self, user_id: str, endpoint: str, limit: int, window: int = 60) -> bool:
        """Returns True if request is allowed, False if rate-limited."""
        key = f"rate:{user_id}:{endpoint}"
        current = await self._r.get(key)
        if current is not None and int(current) >= limit:
            return False
        pipe = self._r.pipeline()
        pipe.incr(key)
        pipe.expire(key, window)
        await pipe.execute()
        return True

    # --- Sync timestamps ---

    async def get_last_sync(self, user_id: str, platform: str) -> Optional[str]:
        return await self.get(f"sync:{user_id}:{platform}")

    async def set_last_sync(self, user_id: str, platform: str, timestamp: str) -> None:
        await self.set(f"sync:{user_id}:{platform}", timestamp, ttl=86400)


# Singleton instance
cache = RedisCache()


async def close_redis():
    """Cleanup on shutdown."""
    await redis_pool.disconnect()
