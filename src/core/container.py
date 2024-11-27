import asyncio
import logging
from typing import Optional

from redis.asyncio import Redis, RedisCluster
from redis.asyncio.cluster import ClusterNode

from src.common.websocket import WebSocketManager
from src.core.config import settings
from src.domain.task.service import TaskService
from src.storage.base import StorageBackend
from src.storage.memory import DictionaryBackend
from src.storage.redis import RedisBackend

logger = logging.getLogger(__name__)


class StorageConnection:
    """Storage connection manager."""

    _instance: Optional[StorageBackend] = None
    _lock: asyncio.Lock = asyncio.Lock()

    @classmethod
    async def get_connection(cls) -> StorageBackend:
        """Get or create storage connection."""
        async with cls._lock:
            if cls._instance is None:
                try:
                    if settings.storage_type == "redis":
                        if settings.environment == "production":
                            nodes = [ClusterNode(host, port) for host, port in settings.redis_cluster_nodes]
                            redis_client = RedisCluster(
                                startup_nodes=nodes,
                                decode_responses=True,
                                max_connections=settings.redis_max_connections,
                            )
                        else:
                            redis_client = Redis(
                                host=settings.redis_host,
                                port=settings.redis_port,
                                decode_responses=True,
                                max_connections=settings.redis_max_connections,
                            )
                        cls._instance = RedisBackend(redis_client)
                        # Verify connection if using Redis
                        await redis_client.ping()
                    else:
                        cls._instance = DictionaryBackend()

                    logger.info(f"{settings.storage_type} storage connection established successfully")
                except Exception as e:
                    logger.error(f"Failed to establish storage connection: {e}")
                    raise
            return cls._instance

    @classmethod
    async def close(cls):
        """Close storage connection."""
        if cls._instance:
            if isinstance(cls._instance, RedisBackend):
                await cls._instance.redis.close()
            cls._instance = None
            logger.info("Storage connection closed")


class DependencyContainer:
    """Singleton container for application-wide dependencies."""

    _instance: Optional['DependencyContainer'] = None
    _websocket_manager: Optional[WebSocketManager] = None
    _task_service: Optional[TaskService] = None
    _storage: Optional[StorageBackend] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._websocket_manager = WebSocketManager()
        return cls._instance

    @classmethod
    def get_websocket_manager(cls) -> WebSocketManager:
        """Get or create WebSocketManager instance."""
        if cls._websocket_manager is None:
            cls._websocket_manager = WebSocketManager()
            logger.info("Created new WebSocketManager instance")
        return cls._websocket_manager

    @classmethod
    async def get_task_service(cls) -> TaskService:
        """Get or create TaskService instance with shared WebSocketManager."""
        if cls._task_service is None:
            websocket_manager = cls.get_websocket_manager()
            storage = await StorageConnection.get_connection()
            cls._task_service = TaskService(storage=storage, websocket_manager=websocket_manager)
            logger.info("Created new TaskService instance")
        return cls._task_service


# FastAPI dependencies
async def get_storage() -> StorageBackend:
    """Dependency for getting storage connection."""
    return await StorageConnection.get_connection()


async def get_websocket_manager() -> WebSocketManager:
    """Dependency for getting WebSocketManager instance."""
    return DependencyContainer.get_websocket_manager()


async def get_task_service() -> TaskService:
    """Dependency for getting TaskService instance."""
    return await DependencyContainer.get_task_service()


# Application lifecycle management
async def init_dependencies():
    """Initialize application dependencies."""
    try:
        logger.info("Initializing application dependencies...")
        await StorageConnection.get_connection()
        await DependencyContainer.get_task_service()
        logger.info("Dependencies initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize dependencies: {e}")
        raise


async def cleanup_dependencies():
    """Cleanup application dependencies."""
    try:
        logger.info("Cleaning up application dependencies...")
        await StorageConnection.close()
        logger.info("Dependencies cleaned up successfully")
    except Exception as e:
        logger.error(f"Error during dependency cleanup: {e}")
        raise
