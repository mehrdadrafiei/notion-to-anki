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

from config import settings
from src.chatbots import CHATBOT_LIST, chatbot_factory
from src.flashcard import FlashcardCreator, FlashcardService, FlashcardStorage
from src.notion_handler import notion_handler_factory

# In-memory storage for WebSocket connections
websocket_connections: Dict[str, WebSocket] = {}

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Flashcard Generator API", description="API for generating flashcards from Notion pages", version="1.0.0"
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# In-memory storage for task progress and history
# In production, use a proper database
tasks: Dict[str, Dict] = {}
generation_history: List[Dict] = []


class FlashcardRequest(BaseModel):
    notion_page_id: str
    output_path: Optional[str] = "output/flashcards.csv"
    batch_size: int = Field(10, gt=0, le=100)  # Positive integer, max 100
    use_chatbot: bool = Field(False)
    chatbot_type: Optional[str] = Field(None, strip_whitespace=True)

    @field_validator("chatbot_type")
    def validate_chatbot_type(cls, value, values):
        # Only validate chatbot_type if use_chatbot is True
        if values.data.get('use_chatbot'):
            if not value:
                raise ValueError("Chatbot type is required when use_chatbot is True")
            if value not in CHATBOT_LIST:
                raise ValueError(f"Invalid chatbot type. Allowed types: {CHATBOT_LIST}")
        return value


class FlashcardResponse(BaseModel):
    message: str
    task_id: str


class TaskStatus(BaseModel):
    task_id: str
    progress: int
    status: str
    message: str


@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await websocket.accept()
    websocket_connections[task_id] = websocket
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        del websocket_connections[task_id]


def update_task_progress(task_id: str, progress: int, status: str, message: str):
    tasks[task_id] = {
        "progress": progress,
        "status": status,
        "message": message,
        "timestamp": datetime.now().isoformat(),
    }
    logger.info(f"Task {task_id} updated: {progress}% - {status} - {message}")

    # Send progress update to WebSocket if connected
    if task_id in websocket_connections:
        websocket = websocket_connections[task_id]
        asyncio.create_task(websocket.send_json(tasks[task_id]))


async def generate_flashcards_task(task_id: str, request: FlashcardRequest):
    try:
        update_task_progress(task_id, 0, "starting", "Initializing components...")

        # Initialize components
        storage = FlashcardStorage(anki_output_file=request.output_path)
        notion_handler = await notion_handler_factory(request.notion_page_id)
        chatbot = chatbot_factory(request.chatbot_type)

        update_task_progress(task_id, 20, "processing", "Fetching Notion content...")
        notion_content = await notion_handler.get_headings_and_bullets()

        # Create progress callback for this specific task
        def progress_callback(progress: int, status: str, message: str):
            # Scale progress to be between 20 and 100
            scaled_progress = 20 + int(progress * 0.8)  # 20% was already completed by fetching content
            update_task_progress(task_id, scaled_progress, status, message)

        update_task_progress(task_id, 40, "processing", "Creating flashcards...")
        flashcard_creator = FlashcardCreator(flashcard_storage=storage)

        # Create and run service with progress callback
        service = FlashcardService(flashcard_creator=flashcard_creator, notion_content=notion_content, chatbot=chatbot)
        service.set_progress_callback(progress_callback)

        update_task_progress(task_id, 60, "processing", "Generating flashcards...")
        await service.run()

        update_task_progress(task_id, 100, "completed", "Flashcards generated successfully!")
        logger.info(f"Task {task_id} completed successfully.")

        # Add to history
        generation_history.append(
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
        update_task_progress(task_id, 0, "failed", str(e))
        raise


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "chatbot_types": ["groq", "mistral"]})


@app.post("/generate-flashcards/", response_model=FlashcardResponse)
async def create_flashcards(request: FlashcardRequest, background_tasks: BackgroundTasks):
    try:
        # Generate unique task ID
        task_id = f"task_{uuid.uuid4()}"
        logger.info(f"Generated task ID: {task_id}")

        # Create unique output path for this task
        output_path = f"output/flashcards_{task_id}.csv"
        request.output_path = output_path  # Update the request with the unique path

        # Create output directory
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Add task to background tasks
        background_tasks.add_task(generate_flashcards_task, task_id=task_id, request=request)

        return FlashcardResponse(message="Flashcard generation started", task_id=task_id)

    except Exception as e:
        logger.exception("Failed to initiate flashcard generation")
        raise HTTPException(status_code=500, detail="An error occurred while starting the flashcard generation.")


@app.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id]


@app.get("/generation-history")
async def get_generation_history():
    return generation_history


@app.get("/preview-flashcards/{task_id}")
async def preview_flashcards(task_id: str):
    task = tasks.get(task_id)
    if not task or task["status"] != "completed":
        raise HTTPException(status_code=404, detail="Flashcards not found or still processing")

    # Read the first 5 flashcards from the CSV
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
    task = tasks.get(task_id)
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


@app.get("/health/")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
