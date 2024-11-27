import json
from typing import Any, Dict, Optional

from redis.asyncio import Redis

from .base import StorageBackend


class RedisBackend(StorageBackend):
    """Redis storage backend implementation."""

    def __init__(self, redis_client: Redis):
        self.redis = redis_client

    async def set(self, key: str, value: Any, expiry: int = None) -> None:
        if expiry:
            await self.redis.setex(key, expiry, json.dumps(value))
        else:
            await self.redis.set(key, json.dumps(value))

    async def get(self, key: str) -> Optional[Any]:
        value = await self.redis.get(key)
        return json.loads(value) if value else None

    async def delete(self, key: str) -> None:
        await self.redis.delete(key)

    async def zadd(self, key: str, mapping: Dict[str, float]) -> None:
        await self.redis.zadd(key, mapping)

    async def zrevrange(self, key: str, start: int, end: int) -> list:
        return await self.redis.zrevrange(key, start, end)

    async def zremrangebyrank(self, key: str, start: int, end: int) -> None:
        await self.redis.zremrangebyrank(key, start, end)

    async def expire(self, key: str, seconds: int) -> None:
        await self.redis.expire(key, seconds)
