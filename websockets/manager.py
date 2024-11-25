import logging
from typing import Dict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections for task progress tracking."""

    def __init__(self):
        """Initialize WebSocket connections dictionary."""
        self.connections: Dict[str, WebSocket] = {}
        logger.info("WebSocketManager initialized")

    async def connect(self, task_id: str, websocket: WebSocket):
        """
        Establish a WebSocket connection for a specific task.

        Args:
            task_id (str): Unique identifier for the task
            websocket (WebSocket): WebSocket connection
        """
        try:
            await websocket.accept()
            self.connections[task_id] = websocket
            logger.info(f"WebSocket connection established for task {task_id}")
        except Exception as e:
            logger.error(f"Failed to establish WebSocket connection for task {task_id}: {str(e)}")
            raise

    def disconnect(self, task_id: str):
        """
        Remove a WebSocket connection.

        Args:
            task_id (str): Unique identifier for the task
        """
        if task_id in self.connections:
            self.connections.pop(task_id)
            logger.info(f"WebSocket connection removed for task {task_id}")

    async def send_progress(self, task_id: str, progress_data: Dict):
        """
        Send progress update to a specific WebSocket connection.

        Args:
            task_id (str): Unique identifier for the task
            progress_data (Dict): Progress update information
        """
        if task_id in self.connections:
            try:
                websocket = self.connections[task_id]
                await websocket.send_json(progress_data)
                logger.debug(f"Progress update sent for task {task_id}: {progress_data}")
            except Exception as e:
                logger.error(f"Failed to send progress update for task {task_id}: {str(e)}")
                self.disconnect(task_id)
