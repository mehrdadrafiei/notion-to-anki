import csv
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from pydantic import BaseModel, Field, field_validator

from src.core.auth import get_current_user
from src.core.container import get_task_service
from src.core.error_handling import handle_exceptions
from src.core.exceptions.base import ResourceNotFoundError, ValidationError
from src.core.exceptions.domain import ChatBotError, FlashcardCreationError, FlashcardError, NotionError, TaskError
from src.domain.chatbot.factory import ChatBotFactory
from src.domain.flashcard.service import FlashcardCreator, FlashcardService
from src.domain.notion.factory import create_notion_service
from src.domain.task.service import TaskService
from src.repositories.flashcard_repository import CSVFlashcardRepository

# Configure logging
logger = logging.getLogger(__name__)
router = APIRouter()


class FlashcardRequest(BaseModel):
    """Request schema for generating flashcards"""

    notion_page: str = Field(..., description="Notion page ID or URL")
    output_path: str = Field("output/flashcards.csv", description="Path to save the flashcards")
    batch_size: int = Field(10, gt=0, le=100)
    use_chatbot: bool = Field(False)
    chatbot_type: Optional[str] = Field(None)

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

    class Config:
        json_schema_extra = {
            "example": {
                "notion_page": "page_id_or_url",
                "output_path": "output/flashcards.csv",
                "batch_size": 10,
                "use_chatbot": True,
                "chatbot_type": "groq",
            }
        }


class FlashcardResponse(BaseModel):
    """Response schema for generating flashcards"""

    message: str
    task_id: str


@handle_exceptions(
    {
        ValidationError: (400, "Invalid request parameters"),
        NotionError: (502, "Failed to access Notion content"),
        ChatBotError: (502, "Chatbot service error"),
        FlashcardError: (500, "Failed to generate flashcards"),
        TaskError: (500, "Task management error"),
    }
)
async def generate_flashcards_task(task_service: TaskService, user_id: str, task_id: str, request: FlashcardRequest):
    """
    Background task for generating flashcards.

    Args:
        task_id (str): Unique identifier for the task
        request (FlashcardRequest): Flashcard generation request details
    """
    try:
        # Initialize task
        await task_service.update_task_progress(
            user_id=user_id, task_id=task_id, progress=0, status="starting", message="Initializing components..."
        )

        # Initialize components
        flashcard_repository = CSVFlashcardRepository(anki_output_file=request.output_path)
        notion_service = await create_notion_service()

        # Fetch Notion content
        await task_service.update_task_progress(
            user_id=user_id, task_id=task_id, progress=10, status="processing", message="Fetching Notion content..."
        )

        notion_page = await notion_service.get_page_content(request.notion_page)
        notion_content = notion_page.to_flashcard_format

        # Create flashcards
        await task_service.update_task_progress(
            user_id=user_id, task_id=task_id, progress=20, status="processing", message="Creating flashcards..."
        )

        flashcard_creator = FlashcardCreator(
            flashcard_repository=flashcard_repository, task_service=task_service, task_id=task_id, user_id=user_id
        )

        async def run_service(chatbot=None):
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
                result_message, result_status = await run_service(chatbot)
        else:
            result_message, result_status = await run_service()

        # Add to history
        await task_service.add_to_history(
            user_id,
            {
                "task_id": task_id,
                "notion_page": notion_page.url,
                "chatbot_type": request.chatbot_type,
                "output_path": request.output_path,
                "timestamp": datetime.now().isoformat(),
                "status": result_status,
            },
        )

    except Exception as e:
        logger.exception(f"Task {task_id} failed")
        await task_service.update_task_progress(
            user_id=user_id, task_id=task_id, progress=100, status="failed", message=str(e)
        )
        raise


@router.post("/generate-flashcards/", response_model=FlashcardResponse)
@handle_exceptions({ValidationError: (400, "Invalid request"), TaskError: (500, "Failed to create task")})
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

    # Add generation task to background tasks
    background_tasks.add_task(
        generate_flashcards_task, task_service=task_service, user_id=current_user, task_id=task_id, request=request
    )

    return FlashcardResponse(message="Flashcard generation started", task_id=task_id)


@router.get("/task-status/{task_id}")
@handle_exceptions({ResourceNotFoundError: (404, "Task not found"), TaskError: (500, "Failed to get task status")})
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


@router.get("/generation-history")
@handle_exceptions({TaskError: (500, "Failed to retrieve generation history")})
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


@router.get("/preview-flashcards/{task_id}")
@handle_exceptions(
    {
        ResourceNotFoundError: (404, "Flashcards not found or still processing"),
        FlashcardError: (500, "Failed to preview flashcards"),
    }
)
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
        raise ResourceNotFoundError("Flashcards", task_id)

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
        raise FlashcardError(f"Failed to read flashcard file: {str(e)}")

    return preview_cards


@router.get("/download/{task_id}")
@handle_exceptions(
    {
        ResourceNotFoundError: (404, "Flashcards not found or still processing"),
        FlashcardError: (500, "Failed to download flashcards"),
    }
)
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
        raise ResourceNotFoundError("Flashcards", task_id)

    output_path = f"output/flashcards_{task_id}.csv"
    try:
        with open(output_path, 'rb') as f:
            content = f.read()
    except Exception as e:
        raise FlashcardError(f"Failed to read flashcard file: {str(e)}")

    return Response(
        content=content,
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="flashcards_{task_id}.csv"'},
    )
