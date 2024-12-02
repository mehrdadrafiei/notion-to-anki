import logging
import os
import uuid
from datetime import datetime
from typing import Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from src.api.models.models import FlashcardRequest, FlashcardResponse
from src.core.auth import get_current_user
from src.core.container import RepositoryManager, get_task_service
from src.core.error_handling import handle_exceptions
from src.core.exceptions.base import ResourceNotFoundError, ValidationError
from src.core.exceptions.domain import ChatBotError, FlashcardError, NotionError, TaskError
from src.domain.chatbot.factory import ChatBotFactory
from src.domain.flashcard.config import FlashcardGenerationConfig
from src.domain.flashcard.service import FlashcardCreator, FlashcardService
from src.domain.notion.factory import create_notion_service
from src.domain.task.service import TaskService

logger = logging.getLogger(__name__)
router = APIRouter()


@handle_exceptions(
    {
        ValidationError: (400, "Invalid request parameters"),
        NotionError: (502, "Failed to access Notion content"),
        ChatBotError: (502, "Chatbot service error"),
        FlashcardError: (500, "Failed to generate flashcards"),
        TaskError: (500, "Task management error"),
    }
)
async def generate_flashcards_task(
    request: FlashcardRequest, task_id: str, user_id: str, task_service: TaskService
) -> None:
    """
    Background task for generating flashcards.

    Args:
        request (FlashcardRequest): Flashcard generation request
        task_id (str): Unique task identifier
        user_id (str): Current user ID
        task_service (TaskService): Task service instance
    """
    try:
        # Initialize task
        await task_service.update_task_progress(
            user_id=user_id, task_id=task_id, progress=0, status="starting", message="Initializing components..."
        )

        notion_service = await create_notion_service()

        chatbot = (
            await ChatBotFactory.create(request.chatbot_type) if request.use_chatbot and request.chatbot_type else None
        )

        # Configure repository with new instance for this task
        # Create and configure task-specific repository
        repository = await RepositoryManager.create_repository(
            task_id=task_id, export_format=request.export_format, output_file=f"output/flashcards_{task_id}"
        )
        # Create flashcard creator
        creator = FlashcardCreator(
            flashcard_repository=repository,
            task_service=task_service,
            task_id=task_id,
            user_id=user_id,
        )

        try:
            # Update task status
            await task_service.update_task_progress(
                user_id=user_id, task_id=task_id, progress=20, status="processing", message="Creating flashcards..."
            )

            # Create configuration
            config = FlashcardGenerationConfig(
                export_format=request.export_format,
                use_ai_summary=request.use_chatbot,
                summary_length=request.summary_length,
                max_cards_per_page=request.max_cards,
                include_urls=request.include_urls,
                include_checklists=request.include_checklists,
                include_toggles=request.include_toggles,
                include_headings=request.include_headings,
                include_bullets=request.include_bullets,
            )

            # Get Notion content
            notion_page = await notion_service.get_page_content(request.notion_page, config)

            # Create and run service
            service = FlashcardService(
                flashcard_creator=creator,
                notion_content=notion_page.to_flashcard_format,
                config=config,
                chatbot=chatbot,
            )

            message, status = await service.run()

            # Add to history
            await task_service.add_to_history(
                user_id,
                {
                    "task_id": task_id,
                    "notion_page": request.notion_page,
                    "status": status,
                    "message": message,
                    "timestamp": datetime.now().isoformat(),
                },
            )

        finally:
            # Cleanup resources
            if chatbot:
                await chatbot.cleanup()

    except NotionError as e:
        logger.error(f"Notion error: {str(e)}")
        await task_service.update_task_progress(
            user_id=user_id,
            task_id=task_id,
            progress=100,
            status="failed",
            message=f"Notion error: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Error generating flashcards: {str(e)}")
        await task_service.update_task_progress(
            user_id=user_id,
            task_id=task_id,
            progress=100,
            status="failed",
            message=f"Error: {str(e)}",
        )
        await RepositoryManager.cleanup_repository(task_id)  # Cleanup repository on error


@router.post("/generate-flashcards/", response_model=FlashcardResponse)
@handle_exceptions({ValidationError: (400, "Invalid request"), TaskError: (500, "Failed to create task")})
async def generate_flashcards(
    request: FlashcardRequest,
    background_tasks: BackgroundTasks,
    task_service: TaskService = Depends(get_task_service),
    user_id: str = Depends(get_current_user),
) -> FlashcardResponse:
    """
    Generate flashcards from a Notion page.

    Args:
        request (FlashcardRequest): Flashcard generation request
        background_tasks (BackgroundTasks): FastAPI background tasks
        task_service (TaskService): Task service instance
        user_id (str): Current user ID

    Returns:
        FlashcardResponse: Response containing task ID

    Raises:
        HTTPException: If request validation or processing fails
    """
    try:
        # Generate unique task ID
        task_id = str(uuid.uuid4())

        # Create initial task record
        await task_service.create_task(
            user_id=user_id,
            task_id=task_id,
            initial_data={
                "status": "initiated",
                "message": "Starting flashcard generation",
                "progress": 0,
                "notion_page": request.notion_page,
                "use_chatbot": request.use_chatbot,
                "chatbot_type": request.chatbot_type if request.use_chatbot else None,
            },
        )

        # Add task to background tasks
        background_tasks.add_task(
            generate_flashcards_task,
            request=request,
            task_id=task_id,
            user_id=user_id,
            task_service=task_service,
        )

        return FlashcardResponse(message="Flashcard generation started", task_id=task_id)

    except Exception as e:
        logger.error(f"Failed to initiate flashcard generation: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to start flashcard generation")


@router.get("/task-status/{task_id}")
@handle_exceptions(
    {
        ResourceNotFoundError: (404, "Resource not found"),  # Generic mapping for all ResourceNotFoundError
        TaskError: (500, "Failed to get task status"),
    }
)
async def get_task_status(
    task_id: str, user_id: str = Depends(get_current_user), task_service: TaskService = Depends(get_task_service)
):
    """
    Get status of a flashcard generation task.

    Args:
        task_id (str): Task identifier
        task_service (TaskService): Task service instance
        user_id (str): Current user ID

    Returns:
        dict: Task status information
    Raises:
        HTTPException: If task is not found
    """
    try:
        task_data = await task_service.get_task_status(user_id, task_id)
        if not task_data:
            raise ResourceNotFoundError("Task", task_id)
        return task_data
    except Exception as e:
        logger.error(f"Error getting task status: {str(e)}")
        raise


@router.get("/generation-history")
@handle_exceptions({TaskError: (500, "Failed to retrieve generation history")})
async def get_generation_history(
    user_id: str = Depends(get_current_user),
    limit: int = 50,
    task_service: TaskService = Depends(get_task_service),
):
    """
    Get flashcard generation history.

    Args:
        task_service (TaskService): Task service instance
        user_id (str): Current user ID
        limit (int): Maximum number of history items

    Returns:
        List[dict]: Generation history
    """
    try:
        return await task_service.get_user_history(user_id, limit)
    except Exception as e:
        logger.error(f"Error getting generation history: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve generation history")


@router.get("/preview-flashcards/{task_id}")
@handle_exceptions(
    {
        ResourceNotFoundError: (404, "Resource not found"),  # Generic mapping
        FlashcardError: (500, "Failed to preview flashcards"),
    }
)
async def preview_flashcards(
    task_id: str,
    limit: int = Query(default=5, ge=1, le=20),
    task_service: TaskService = Depends(get_task_service),
    user_id: str = Depends(get_current_user),
) -> List[Dict[str, str]]:
    """
    Preview generated flashcards.

    Args:
        task_id (str): Task identifier
        limit (int): Maximum number of cards to preview
        task_service (TaskService): Task service instance
        user_id (str): Current user ID
        repository (FlashcardRepositoryInterface): Flashcard repository instance
    Returns:
        List[Flashcard]: List of preview flashcards
    Raises:
        HTTPException: If flashcards are not found or still processing
    """
    try:
        task_status = await task_service.get_task_status(user_id, task_id)
        if not task_status:
            raise ResourceNotFoundError("Task", task_id)

        if task_status["status"] not in ["completed", "completed_with_errors"]:
            raise ResourceNotFoundError("Flashcards", task_id, details={"status": task_status["status"]})

        repository = RepositoryManager.get_repository(task_id)
        if not repository or not os.path.exists(repository.output_file):
            raise ResourceNotFoundError("FlashcardRepository", task_id)

        return await repository.get_flashcards(limit=limit)

    except ResourceNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error previewing flashcards: {str(e)}")
        raise FlashcardError(f"Failed to preview flashcards: {str(e)}")


@router.get("/download/{task_id}")
@handle_exceptions(
    {
        ResourceNotFoundError: (404, "Resource not found"),  # Generic mapping
        FlashcardError: (500, "Failed to download flashcards"),
    }
)
async def download_flashcards(
    task_id: str, user_id: str = Depends(get_current_user), task_service: TaskService = Depends(get_task_service)
):
    """
    Download generated flashcards.

    Args:
        task_id (str): Task identifier
        user_id (str): Current user ID
        task_service (TaskService): Task service instance
        repository (FlashcardRepositoryInterface): Flashcard repository instance
    Returns:
        FileResponse: Generated flashcard file
    Raises:
        HTTPException: If flashcards are not found or an error occurs
    """
    try:
        task_status = await task_service.get_task_status(user_id, task_id)
        if not task_status:
            raise ResourceNotFoundError("Task", task_id)

        if task_status["status"] not in ["completed", "completed_with_errors"]:
            raise ResourceNotFoundError("Flashcards", task_id, details={"status": task_status["status"]})

        repository = RepositoryManager.get_repository(task_id)
        if not repository or not os.path.exists(repository.output_file):
            raise ResourceNotFoundError("FlashcardRepository", task_id)

        # Determine the correct file extension and media type
        file_extension = os.path.splitext(repository.output_file)[1].lower()
        media_type = "application/apkg" if file_extension == ".apkg" else "text/csv"

        return FileResponse(
            repository.output_file,
            media_type=media_type,
            filename=os.path.basename(repository.output_file),
            headers={"Content-Disposition": f"attachment; filename={os.path.basename(repository.output_file)}"},
        )

    except ResourceNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error downloading flashcards: {str(e)}")
        raise FlashcardError(f"Failed to download flashcards: {str(e)}")
