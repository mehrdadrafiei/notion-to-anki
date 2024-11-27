import asyncio
import time
from typing import Any, Dict, Optional

from .base import StorageBackend


class DictionaryBackend(StorageBackend):
    """In-memory dictionary storage backend implementation."""

    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.expiry: Dict[str, float] = {}
        self.sorted_sets: Dict[str, Dict[str, float]] = {}
        self._cleanup_task = asyncio.create_task(self._cleanup_expired())

    async def _cleanup_expired(self):
        """Background task to clean up expired keys."""
        while True:
            current_time = time.time()
            expired_keys = [key for key, expire_time in self.expiry.items() if expire_time <= current_time]
            for key in expired_keys:
                self.data.pop(key, None)
                self.expiry.pop(key, None)
            await asyncio.sleep(1)

    async def set(self, key: str, value: Any, expiry: int = None) -> None:
        self.data[key] = value
        if expiry:
            self.expiry[key] = time.time() + expiry

    async def get(self, key: str) -> Optional[Any]:
        if key in self.expiry and time.time() > self.expiry[key]:
            self.data.pop(key, None)
            self.expiry.pop(key, None)
            return None
        return self.data.get(key)

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)
        self.expiry.pop(key, None)

    async def zadd(self, key: str, mapping: Dict[str, float]) -> None:
        if key not in self.sorted_sets:
            self.sorted_sets[key] = {}
        self.sorted_sets[key].update(mapping)

    async def zrevrange(self, key: str, start: int, end: int) -> list:
        if key not in self.sorted_sets:
            return []
        sorted_items = sorted(self.sorted_sets[key].items(), key=lambda x: x[1], reverse=True)
        return [item[0] for item in sorted_items[start : end + 1]]

    async def zremrangebyrank(self, key: str, start: int, end: int) -> None:
        if key in self.sorted_sets:
            sorted_items = sorted(self.sorted_sets[key].items(), key=lambda x: x[1], reverse=True)
            to_remove = sorted_items[start : end + 1]
            for item, _ in to_remove:
                self.sorted_sets[key].pop(item, None)

    async def expire(self, key: str, seconds: int) -> None:
        self.expiry[key] = time.time() + seconds
