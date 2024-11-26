# src/services/task_service.py
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import HTTPException
from redis.asyncio import Redis

from src.common.websocket import WebSocketManager

logger = logging.getLogger(__name__)


class TaskService:
    def __init__(self, redis: Redis, websocket_manager: WebSocketManager):
        self.redis = redis
        self.websocket_manager = websocket_manager
        self._lock = asyncio.Lock()  # Add lock for Redis operations

    async def create_task(self, user_id: str, task_id: str, initial_data: Dict) -> None:
        """Create a new task with initial data."""
        task_key = f"task:{user_id}:{task_id}"
        task_data = {**initial_data, "timestamp": datetime.now().isoformat(), "user_id": user_id}

        try:
            async with self._lock:  # Use lock for Redis operations
                # Store task data with 24-hour TTL
                await self.redis.setex(task_key, 86400, json.dumps(task_data))  # 24 hours
        except Exception as e:
            logger.error(f"Failed to create task {task_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to create task")

    async def update_task_progress(self, user_id: str, task_id: str, progress: int, status: str, message: str) -> None:
        """Update task progress and notify via WebSocket."""
        task_key = f"task:{user_id}:{task_id}"

        try:
            async with self._lock:  # Use lock for Redis operations
                # Get existing task data
                existing_data = await self.redis.get(task_key)
                if existing_data:
                    task_data = json.loads(existing_data)
                else:
                    task_data = {}

                # Update task data
                task_data.update(
                    {
                        "progress": progress,
                        "status": status,
                        "message": message,
                        "timestamp": datetime.now().isoformat(),
                        "user_id": user_id,
                    }
                )

                # Store updated data
                await self.redis.setex(task_key, 86400, json.dumps(task_data))  # 24 hours

            # Send WebSocket update outside the lock
            try:
                await self.websocket_manager.send_progress(task_id, task_data)
            except Exception as ws_error:
                logger.error(f"WebSocket error for task {task_id}: {ws_error}")

        except Exception as e:
            logger.error(f"Failed to update task {task_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to update task status")

    async def get_task_status(self, user_id: str, task_id: str) -> Dict:
        """Get current task status."""
        task_key = f"task:{user_id}:{task_id}"

        try:
            task_data = await self.redis.get(task_key)
            if not task_data:
                raise HTTPException(status_code=404, detail="Task not found")

            return json.loads(task_data)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get task status for {task_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to get task status")

    async def add_to_history(self, user_id: str, task_details: Dict) -> None:
        """Add completed task to user's history."""
        history_key = f"history:{user_id}"

        try:
            # Add to sorted set with timestamp as score
            timestamp = datetime.fromisoformat(task_details['timestamp']).timestamp()

            await self.redis.zadd(history_key, {json.dumps(task_details): timestamp})

            # Trim history to last 100 entries
            await self.redis.zremrangebyrank(history_key, 0, -101)

            # Set 30-day TTL for history
            await self.redis.expire(history_key, 2592000)

        except Exception as e:
            logger.error(f"Failed to add task to history for user {user_id}: {e}")
            # Non-critical operation, log error but don't raise exception

    async def get_user_history(self, user_id: str, limit: int = 50) -> List[Dict]:
        """Get user's task history."""
        history_key = f"history:{user_id}"

        try:
            # Get history entries sorted by timestamp
            entries = await self.redis.zrevrange(history_key, 0, limit - 1)

            return [json.loads(entry) for entry in entries]

        except Exception as e:
            logger.error(f"Failed to get history for user {user_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to retrieve task history")
