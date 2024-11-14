import csv
import datetime
import logging
import os
import uuid
from typing import Dict, List, Optional

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from config import settings
from src.chatbots import CHATBOT_LIST, chatbot_factory
from src.flashcard import FlashcardCreator, FlashcardService, FlashcardStorage
from src.notion_handler import notion_handler_factory

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
    chatbot_type: str = Field("groq", strip_whitespace=True)

    @field_validator("chatbot_type")
    def validate_chatbot_type(cls, value):
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


def update_task_progress(task_id: str, progress: int, status: str, message: str):
    tasks[task_id] = {
        "progress": progress,
        "status": status,
        "message": message,
        "timestamp": datetime.now().isoformat(),
    }


def generate_flashcards(page_id: str, output_path: str, batch_size: int, chatbot_type: str) -> None:
    try:
        # Initialize components
        storage = FlashcardStorage(anki_output_file=output_path)
        notion_handler = notion_handler_factory(page_id)
        chatbot = chatbot_factory(chatbot_type)
        flashcard_creator = FlashcardCreator(flashcard_storage=storage)

        # Create and run service
        service = FlashcardService(notion_handler=notion_handler, chatbot=chatbot, flashcard_creator=flashcard_creator)

        service.run()
    except Exception as e:
        # Log the error
        print(f"Error in background task: {str(e)}")
        raise


async def generate_flashcards_task(task_id: str, request: FlashcardRequest):
    try:
        update_task_progress(task_id, 0, "starting", "Initializing components...")

        # Initialize components
        storage = FlashcardStorage(anki_output_file=request.output_path)
        notion_handler = notion_handler_factory(request.notion_page_id)
        chatbot = chatbot_factory(request.chatbot_type)

        update_task_progress(task_id, 20, "processing", "Fetching Notion content...")
        notion_content = notion_handler.get_headings_and_bullets()

        update_task_progress(task_id, 40, "processing", "Creating flashcards...")
        flashcard_creator = FlashcardCreator(flashcard_storage=storage)

        # Create and run service with progress callback
        service = FlashcardService(notion_content=notion_content, chatbot=chatbot, flashcard_creator=flashcard_creator)

        update_task_progress(task_id, 60, "processing", "Generating flashcards...")
        service.run()

        update_task_progress(task_id, 100, "completed", "Flashcards generated successfully!")

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
        # Create output directory
        os.makedirs(os.path.dirname(request.output_path), exist_ok=True)

        # Generate unique task ID
        task_id = f"task_{uuid.uuid4()}"
        logger.info(f"Generated task ID: {task_id}")

        # Add task to background tasks
        background_tasks.add_task(
            generate_flashcards,
            page_id=request.notion_page_id,
            output_path=request.output_path,
            batch_size=request.batch_size,
            chatbot_type=request.chatbot_type,
        )

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
