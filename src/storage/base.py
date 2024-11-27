from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    async def set(self, key: str, value: Any, expiry: int = None) -> None:
        """Set a value with optional expiry in seconds."""
        pass

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get a value by key."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a value by key."""
        pass

    @abstractmethod
    async def zadd(self, key: str, mapping: Dict[str, float]) -> None:
        """Add to a sorted set with scores."""
        pass

    @abstractmethod
    async def zrevrange(self, key: str, start: int, end: int) -> list:
        """Get range from sorted set in reverse order."""
        pass

    @abstractmethod
    async def zremrangebyrank(self, key: str, start: int, end: int) -> None:
        """Remove range from sorted set by rank."""
        pass

    @abstractmethod
    async def expire(self, key: str, seconds: int) -> None:
        """Set expiry on a key."""
        pass
