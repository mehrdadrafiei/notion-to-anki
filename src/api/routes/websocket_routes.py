import logging
from typing import Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from ...common.websocket import WebSocketManager
from ...core.container import get_websocket_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/{task_id}")
async def websocket_endpoint(
    websocket: WebSocket, task_id: str, websocket_manager: WebSocketManager = Depends(get_websocket_manager)
):
    """
    WebSocket endpoint for real-time task progress updates.

    Args:
        websocket (WebSocket): WebSocket connection
        task_id (str): Unique identifier for the task
        websocket_manager(WebSocketManager): WebSocket connections manager for task progress tracking
    """
    try:
        await websocket_manager.connect(task_id, websocket)
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for task {task_id}")
                break
            except Exception as e:
                logger.error(f"WebSocket error for task {task_id}: {str(e)}")
                break
    finally:
        websocket_manager.disconnect(task_id)
