# src/dependencies/container.py
import asyncio
import logging
from typing import Optional

from redis.asyncio import Redis, RedisCluster
from redis.asyncio.cluster import ClusterNode

from src.common.websocket import WebSocketManager
from src.core.config import settings
from src.domain.task.task_service import TaskService

logger = logging.getLogger(__name__)


class RedisConnection:
    """Singleton Redis connection manager."""

    _instance: Optional[Redis] = None
    _lock: asyncio.Lock = asyncio.Lock()

    @classmethod
    async def get_connection(cls) -> Redis:
        """Get or create Redis connection."""
        async with cls._lock:
            if cls._instance is None:
                try:
                    if settings.environment == "production":
                        nodes = [ClusterNode(host, port) for host, port in settings.redis_cluster_nodes]
                        cls._instance = RedisCluster(
                            startup_nodes=nodes, decode_responses=True, max_connections=settings.redis_max_connections
                        )
                    else:
                        cls._instance = Redis(
                            host=settings.redis_host,
                            port=settings.redis_port,
                            decode_responses=True,
                            max_connections=settings.redis_max_connections,
                        )
                    # Verify connection
                    await cls._instance.ping()
                    logger.info("Redis connection established successfully")
                except Exception as e:
                    logger.error(f"Failed to establish Redis connection: {e}")
                    raise
            return cls._instance

    @classmethod
    async def close(cls):
        """Close Redis connection."""
        if cls._instance:
            await cls._instance.close()
            cls._instance = None
            logger.info("Redis connection closed")


class DependencyContainer:
    """Singleton container for application-wide dependencies."""

    _instance: Optional['DependencyContainer'] = None
    _websocket_manager: Optional[WebSocketManager] = None
    _task_service: Optional[TaskService] = None
    _redis: Optional[Redis] = None

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
            redis = await RedisConnection.get_connection()
            cls._task_service = TaskService(redis=redis, websocket_manager=websocket_manager)
            logger.info("Created new TaskService instance")
        return cls._task_service


# FastAPI dependencies
async def get_redis() -> Redis:
    """Dependency for getting Redis connection."""
    return await RedisConnection.get_connection()


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
        await RedisConnection.get_connection()
        await DependencyContainer.get_task_service()
        logger.info("Dependencies initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize dependencies: {e}")
        raise


async def cleanup_dependencies():
    """Cleanup application dependencies."""
    try:
        logger.info("Cleaning up application dependencies...")
        await RedisConnection.close()
        logger.info("Dependencies cleaned up successfully")
    except Exception as e:
        logger.error(f"Error during dependency cleanup: {e}")
        raise
