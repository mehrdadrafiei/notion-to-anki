import asyncio
import csv
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from chatbots.factory import ChatBotFactory
from config import settings
from middleware.rate_limiting import RateLimitMiddleware
from monitoring.health import HealthCheck
from repositories.FlashcardRepository import CSVFlashcardRepository
from src.flashcard import FlashcardCreator, FlashcardService
from src.notion_handler import notion_handler_factory

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections for task progress tracking."""

    def __init__(self):
        """Initialize WebSocket connections dictionary."""
        self.connections: Dict[str, WebSocket] = {}

    async def connect(self, task_id: str, websocket: WebSocket):
        """
        Establish a WebSocket connection for a specific task.

        Args:
            task_id (str): Unique identifier for the task
            websocket (WebSocket): WebSocket connection
        """
        await websocket.accept()
        self.connections[task_id] = websocket

    def disconnect(self, task_id: str):
        """
        Remove a WebSocket connection.

        Args:
            task_id (str): Unique identifier for the task
        """
        self.connections.pop(task_id, None)

    async def send_progress(self, task_id: str, progress_data: Dict):
        """
        Send progress update to a specific WebSocket connection.

        Args:
            task_id (str): Unique identifier for the task
            progress_data (Dict): Progress update information
        """
        if task_id in self.connections:
            websocket = self.connections[task_id]
            await websocket.send_json(progress_data)


class TaskTracker:
    """Manages task status and history tracking."""

    def __init__(self):
        """Initialize task tracking structures."""
        self.tasks: Dict[str, Dict] = {}
        self.generation_history: List[Dict] = []
        self.websocket_manager = WebSocketManager()

    def update_task_progress(self, task_id: str, progress: int, status: str, message: str):
        """
        Update task progress and log the update.

        Args:
            task_id (str): Unique identifier for the task
            progress (int): Current progress percentage
            status (str): Current task status
            message (str): Detailed status message
        """
        task_update = {
            "progress": progress,
            "status": status,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        }

        self.tasks[task_id] = task_update
        logger.info(f"Task {task_id} updated: {progress}% - {status} - {message}")

        # Send WebSocket update
        asyncio.create_task(self.websocket_manager.send_progress(task_id, task_update))

    def add_to_history(self, task_details: Dict):
        """
        Add task details to generation history.

        Args:
            task_details (Dict): Details of the completed task
        """
        self.generation_history.append(task_details)


class FlashcardRequest(BaseModel):
    """Request schema for generating flashcards"""

    notion_page_id: str
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
        title="Flashcard Generator API", description="API for generating flashcards from Notion pages", version="1.0.0"
    )

    # Add middleware
    app.add_middleware(RateLimitMiddleware, calls=settings.rate_limit_calls, period=settings.rate_limit_period)

    # Mount static files and templates
    app.mount("/static", StaticFiles(directory="static"), name="static")

    return app


# Global task tracker
task_tracker = TaskTracker()
app = create_app()
templates = Jinja2Templates(directory="templates")


async def generate_flashcards_task(task_id: str, request: FlashcardRequest):
    """
    Background task for generating flashcards.

    Args:
        task_id (str): Unique identifier for the task
        request (FlashcardRequest): Flashcard generation request details
    """
    try:
        task_tracker.update_task_progress(task_id, 0, "starting", "Initializing components...")

        # Initialize components
        flashcard_repository = CSVFlashcardRepository(anki_output_file=request.output_path)
        notion_handler = await notion_handler_factory(request.notion_page_id)

        task_tracker.update_task_progress(task_id, 20, "processing", "Fetching Notion content...")
        notion_content = await notion_handler.get_headings_and_bullets()

        def progress_callback(progress: int, status: str, message: str):
            """
            Callback to update task progress during flashcard generation.

            Args:
                progress (int): Current progress percentage
                status (str): Current status
                message (str): Detailed status message
            """
            scaled_progress = 20 + int(progress * 0.8)  # Scale progress between 20 and 100
            task_tracker.update_task_progress(task_id, scaled_progress, status, message)

        task_tracker.update_task_progress(task_id, 20, "processing", "Creating flashcards...")
        flashcard_creator = FlashcardCreator(flashcard_repository=flashcard_repository)

        # Prepare service with or without chatbot
        async def run_flashcard_service(chatbot=None):
            """
            Run flashcard service with optional chatbot.

            Args:
                chatbot (Optional[ChatBot]): Chatbot for summary generation
            """
            service = FlashcardService(
                flashcard_creator=flashcard_creator, notion_content=notion_content, chatbot=chatbot
            )
            service.set_progress_callback(progress_callback)
            await service.run()

        if request.use_chatbot:
            chatbot = await ChatBotFactory.create(request.chatbot_type)
            async with chatbot:
                await run_flashcard_service(chatbot)
        else:
            await run_flashcard_service()

        task_tracker.update_task_progress(task_id, 100, "completed", "Flashcards generated successfully!")
        logger.info(f"Task {task_id} completed successfully.")

        # Add to history
        task_tracker.add_to_history(
            {
                "task_id": task_id,
                "notion_page_id": request.notion_page_id,
                "chatbot_type": request.chatbot_type,
                "output_path": request.output_path,
                "timestamp": datetime.now().isoformat(),
                "status": "completed",
            }
        )

    except Exception as e:
        task_tracker.update_task_progress(task_id, 0, "failed", str(e))
        logger.exception(f"Task {task_id} failed")
        raise


@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """
    WebSocket endpoint for real-time task progress updates.

    Args:
        websocket (WebSocket): WebSocket connection
        task_id (str): Unique identifier for the task
    """
    await task_tracker.websocket_manager.connect(task_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        task_tracker.websocket_manager.disconnect(task_id)


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
async def create_flashcards(request: FlashcardRequest, background_tasks: BackgroundTasks):
    """
    Endpoint to initiate flashcard generation.

    Args:
        request (FlashcardRequest): Flashcard generation request details
        background_tasks (BackgroundTasks): FastAPI background tasks manager

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

        # Add task to background tasks
        background_tasks.add_task(generate_flashcards_task, task_id=task_id, request=request)

        return FlashcardResponse(message="Flashcard generation started", task_id=task_id)

    except Exception as e:
        logger.exception("Failed to initiate flashcard generation")
        raise HTTPException(status_code=500, detail="An error occurred while starting the flashcard generation.")


@app.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    """
    Retrieve status of a specific task.

    Args:
        task_id (str): Unique identifier for the task

    Returns:
        Dict: Task status information

    Raises:
        HTTPException: If task is not found
    """
    if task_id not in task_tracker.tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return task_tracker.tasks[task_id]


@app.get("/generation-history")
async def get_generation_history():
    """
    Retrieve generation history.

    Returns:
        List[Dict]: List of past generation tasks
    """
    return task_tracker.generation_history


@app.get("/preview-flashcards/{task_id}")
async def preview_flashcards(task_id: str):
    """
    Preview first 5 generated flashcards.

    Args:
        task_id (str): Unique identifier for the task

    Returns:
        List[Dict]: Preview of generated flashcards

    Raises:
        HTTPException: If flashcards are not found or still processing
    """
    task = task_tracker.tasks.get(task_id)
    if not task or task["status"] != "completed":
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
async def download_flashcards(task_id: str):
    """
    Download generated flashcards CSV file.

    Args:
        task_id (str): Unique identifier for the task

    Returns:
        Response: CSV file download

    Raises:
        HTTPException: If flashcards are not found or an error occurs
    """
    task = task_tracker.tasks.get(task_id)
    if not task or task["status"] != "completed":
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
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
