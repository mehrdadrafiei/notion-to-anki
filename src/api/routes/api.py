import csv
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, Union

import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.sessions import SessionMiddleware

from monitoring.health import HealthCheck
from src.common.websocket import WebSocketManager
from src.core.auth import get_current_user
from src.core.config import settings
from src.core.container import cleanup_dependencies, get_task_service, get_websocket_manager, init_dependencies
from src.domain.chatbot.factory import ChatBotFactory
from src.domain.flashcard.flashcard import FlashcardCreator, FlashcardService
from src.domain.notion.notion_handler import notion_handler_factory
from src.domain.task.task_service import TaskService
from src.repositories.FlashcardRepository import CSVFlashcardRepository

from ..middleware.rate_limiting import RateLimitMiddleware

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_dependencies()
    yield
    # Shutdown
    await cleanup_dependencies()


class FlashcardRequest(BaseModel):
    """Request schema for generating flashcards"""

    notion_page: str
    output_path: Optional[str] = "output/flashcards.csv"
    batch_size: int = Field(10, gt=0, le=100)  # Positive integer, max 100
    use_chatbot: bool = Field(False)
    chatbot_type: Optional[str] = Field(None, strip_whitespace=True)

    @field_validator("chatbot_type")
    def validate_chatbot_type(cls, value, values):
        """
        Validate chatbot type when using a chatbot.

        Args:
            value (str): Chatbot type
            values (Dict): Other request values

        Returns:
            str: Validated chatbot type

        Raises:
            ValueError: If chatbot type is invalid
        """
        if values.data.get('use_chatbot'):
            if not value:
                raise ValueError("Chatbot type is required when use_chatbot is True")
            available_chatbots = ChatBotFactory.get_available_chatbots()
            if value not in available_chatbots:
                raise ValueError(f"Invalid chatbot type. Allowed types: {available_chatbots}")
        return value


class FlashcardResponse(BaseModel):
    """Response schema for generating flashcards"""

    message: str
    task_id: str


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        FastAPI: Configured application instance
    """
    app = FastAPI(
        title="Flashcard Generator API",
        description="API for generating flashcards from Notion pages",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
    # Add middleware
    app.add_middleware(RateLimitMiddleware, calls=settings.rate_limit_calls, period=settings.rate_limit_period)

    # Mount static files and templates
    app.mount("/static", StaticFiles(directory="static"), name="static")
    return app


app = create_app()
templates = Jinja2Templates(directory="templates")


async def generate_flashcards_task(task_service: TaskService, user_id: str, task_id: str, request: FlashcardRequest):
    """
    Background task for generating flashcards.

    Args:
        task_id (str): Unique identifier for the task
        request (FlashcardRequest): Flashcard generation request details
    """
    try:
        await task_service.update_task_progress(
            user_id=user_id, task_id=task_id, progress=0, status="starting", message="Initializing components..."
        )
        # Initialize components
        flashcard_repository = CSVFlashcardRepository(anki_output_file=request.output_path)
        notion_handler = await notion_handler_factory(request.notion_page)
        await task_service.update_task_progress(
            user_id=user_id, task_id=task_id, progress=20, status="processing", message="Fetching Notion content..."
        )
        notion_content = await notion_handler.get_headings_and_bullets()

        await task_service.update_task_progress(
            user_id=user_id, task_id=task_id, progress=20, status="processing", message="Creating flashcards..."
        )
        flashcard_creator = FlashcardCreator(
            flashcard_repository=flashcard_repository, task_service=task_service, task_id=task_id, user_id=user_id
        )

        # Prepare service with or without chatbot
        async def run_flashcard_service(chatbot=None) -> Union[str, str]:
            """
            Run flashcard service with optional chatbot.

            Args:
                chatbot (Optional[ChatBot]): Chatbot for summary generation
            """
            service = FlashcardService(
                flashcard_creator=flashcard_creator, notion_content=notion_content, chatbot=chatbot
            )
            return await service.run()

        if request.use_chatbot:
            chatbot = await ChatBotFactory.create(request.chatbot_type)
            async with chatbot:
                result_message, result_status = await run_flashcard_service(chatbot)
        else:
            result_message, result_status = await run_flashcard_service()

        logger.info(f"Task {task_id} completed successfully.")

        # Add to history
        await task_service.add_to_history(
            user_id,
            {
                "task_id": task_id,
                "notion_page": notion_handler.url,
                "chatbot_type": request.chatbot_type,
                "output_path": request.output_path,
                "timestamp": datetime.now().isoformat(),
                "status": result_status,
            },
        )

    except Exception as e:
        await task_service.update_task_progress(
            user_id=user_id, task_id=task_id, progress=0, status="failed", message=str(e)
        )
        logger.exception(f"Task {task_id} failed")
        raise


@app.websocket("/ws/{task_id}")
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


@app.get("/")
async def home(request: Request):
    """
    Home route rendering the index page.

    Args:
        request (Request): Incoming HTTP request

    Returns:
        TemplateResponse: Rendered index page
    """
    return templates.TemplateResponse(
        "index.html", {"request": request, "chatbot_types": ChatBotFactory.get_available_chatbots()}
    )


@app.post("/generate-flashcards/", response_model=FlashcardResponse)
async def create_flashcards(
    request: FlashcardRequest,
    background_tasks: BackgroundTasks,
    current_user: str = Depends(get_current_user),
    task_service: TaskService = Depends(get_task_service),
):
    """
    Endpoint to initiate flashcard generation.

    Args:
        request (FlashcardRequest): Flashcard generation request details
        background_tasks (BackgroundTasks): FastAPI background tasks manager
        current_user (str): user id
        task_service (TaskService): task_service

    Returns:
        FlashcardResponse: Task initiation response
    """
    try:
        # Generate unique task ID and output path
        task_id = f"task_{uuid.uuid4()}"
        output_path = f"output/flashcards_{task_id}.csv"
        request.output_path = output_path
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Create task with initial status
        await task_service.create_task(
            user_id=current_user,
            task_id=task_id,
            initial_data={"status": "created", "output_path": output_path, "request": request.model_dump()},
        )

        # Add flashcard generation to background tasks
        background_tasks.add_task(
            generate_flashcards_task, task_service=task_service, user_id=current_user, task_id=task_id, request=request
        )

        return FlashcardResponse(message="Flashcard generation started", task_id=task_id)
    except Exception as e:
        logger.exception("Failed to initiate flashcard generation")
        raise HTTPException(status_code=500, detail="An error occurred while starting the flashcard generation.")


@app.get("/task-status/{task_id}")
async def get_task_status(
    task_id: str, current_user: str = Depends(get_current_user), task_service: TaskService = Depends(get_task_service)
):
    """
    Retrieve status of a specific task.

    Args:
        task_id (str): Unique identifier for the task
        task_service (TaskService): task_service

    Returns:
        Dict: Task status information

    Raises:
        HTTPException: If task is not found
    """
    return await task_service.get_task_status(current_user, task_id)


@app.get("/generation-history")
async def get_generation_history(
    current_user: str = Depends(get_current_user),
    limit: int = 50,
    task_service: TaskService = Depends(get_task_service),
):
    """
    Retrieve generation history.

    Returns:
        List[Dict]: List of past generation tasks
    """
    return await task_service.get_user_history(current_user, limit)


@app.get("/preview-flashcards/{task_id}")
async def preview_flashcards(
    task_id: str, current_user: str = Depends(get_current_user), task_service: TaskService = Depends(get_task_service)
):
    """
    Preview first 5 generated flashcards.

    Args:
        task_id (str): Unique identifier for the task
        task_service (TaskService): task_service

    Returns:
        List[Dict]: Preview of generated flashcards

    Raises:
        HTTPException: If flashcards are not found or still processing
    """
    task = await task_service.get_task_status(current_user, task_id)
    if not task or task["status"] not in ["completed", "completed_with_errors"]:
        raise HTTPException(status_code=404, detail="Flashcards not found or still processing")
    output_path = f"output/flashcards_{task_id}.csv"
    preview_cards = []
    try:
        with open(output_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i >= 5:  # Preview only first 5 cards
                    break
                preview_cards.append({"front": row[0], "back": row[1]})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return preview_cards


@app.get("/download/{task_id}")
async def download_flashcards(
    task_id: str, current_user: str = Depends(get_current_user), task_service: TaskService = Depends(get_task_service)
):
    """
    Download generated flashcards CSV file.

    Args:
        task_id (str): Unique identifier for the task
        task_service (TaskService) : task_service

    Returns:
        Response: CSV file download

    Raises:
        HTTPException: If flashcards are not found or an error occurs
    """
    task = await task_service.get_task_status(current_user, task_id)
    if not task or task["status"] not in ["completed", "completed_with_errors"]:
        raise HTTPException(status_code=404, detail="Flashcards not found or still processing")
    output_path = f"output/flashcards_{task_id}.csv"
    try:
        with open(output_path, 'rb') as f:
            content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return Response(
        content=content,
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="flashcards_{task_id}.csv"'},
    )


@app.get("/health")
async def health_check(request: Request):
    """
    Perform system health check.

    Args:
        request (Request): Incoming HTTP request

    Returns:
        Dict: Health check results
    """
    async with HealthCheck() as health_check:
        return await health_check.get_health(request)


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True, ws="websockets", log_level="info")
