import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketException

from src.common.websocket import WebSocketManager
from src.core.container import get_websocket_manager
from src.core.exceptions.base import AppError

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
            except Exception as e:
                logger.warning(f"WebSocket connection closed for task {task_id}: {str(e)}")
                break

    except WebSocketException as e:
        logger.error(f"WebSocket error for task {task_id}: {str(e)}")
        if websocket.client_state.connected:
            await websocket.close(code=1011, reason=str(e))

    except AppError as e:
        logger.error(
            f"Application error in WebSocket for task {task_id}",
            extra={"error_code": e.error_code, "details": e.details},
        )
        if websocket.client_state.connected:
            await websocket.close(code=1011, reason=str(e))

    except Exception as e:
        logger.exception(f"Unexpected error in WebSocket for task {task_id}")
        if websocket.client_state.connected:
            await websocket.close(code=1011, reason="Internal server error")

    finally:
        websocket_manager.disconnect(task_id)
