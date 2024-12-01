import asyncio
import logging
import time
from functools import wraps
from typing import Dict, List, Optional, Tuple, Union

from cachetools import TTLCache

from src.core.config import settings
from src.core.error_handling import handle_exceptions, handle_service_errors
from src.core.exceptions.base import ValidationError
from src.core.exceptions.domain import (
    ChatBotError,
    FlashcardCreationError,
    FlashcardError,
    FlashcardStorageError,
    FlashcardValidationError,
)
from src.domain.flashcard.config import FlashcardGenerationConfig
from src.domain.task.service import TaskService
from src.repositories.flashcard_repository import Flashcard, FlashcardRepositoryInterface

from ..chatbot.base import ChatBot


class FlashcardValidator:
    """Validates flashcard content integrity."""

    @staticmethod
    def validate_flashcard_content(text: str, min_length: int = 3, max_length: int = 500) -> bool:
        """
        Validate flashcard content.

        Args:
            text (str): Text to validate
            min_length (int, optional): Minimum text length. Defaults to 3.
            max_length (int, optional): Maximum text length. Defaults to 500.

        Returns:
            bool: Whether the text meets validation criteria
        """
        if not text or not isinstance(text, str):
            return False

        text = text.strip()
        if not text or text == "Summary unavailable":
            return False

        return min_length <= len(text) <= max_length and text.strip() != "None"


class FlashcardCache:
    """Manage time-limited caching for flashcard summaries."""

    def __init__(self, maxsize: int = 100, ttl: int = 3600):
        """
        Initialize the cache.

        Args:
            maxsize (int, optional): Maximum cache size. Defaults to 100.
            ttl (int, optional): Time-to-live in seconds. Defaults to 3600.
        """
        self.cache = TTLCache(maxsize=maxsize, ttl=ttl)

    @handle_service_errors(default_return_value=None)
    async def get(self, key: str) -> Optional[str]:
        """
        Retrieve value from cache.

        Args:
            key (str): Cache key

        Returns:
            Optional[str]: Cached value or None
        """
        return self.cache.get(key)

    @handle_service_errors()
    async def set(self, key: str, value: str) -> None:
        """
        Set value in cache.

        Args:
            key (str): Cache key
            value (str): Value to cache
        """
        self.cache[key] = value


def rate_limit(calls: int, period: int):
    """
    Decorator to rate limit async function calls.

    Args:
        calls (int): Maximum number of calls
        period (int): Time period in seconds

    Returns:
        Callable: Decorated function
    """
    min_interval = period / calls
    last_called = [0.0]

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            last_called[0] = time.time()
            return await func(*args, **kwargs)

        return wrapper

    return decorator


class FlashcardCreator:
    """
    Manages the creation of flashcards from various content sources.
    """

    PROMPT_PREFIX = "Summarize the following text. Provide only the summary, enclosed in [[ ]]"

    def __init__(
        self,
        flashcard_repository: FlashcardRepositoryInterface,
        cache: Optional[FlashcardCache] = None,
        task_service: Optional[TaskService] = None,
        task_id: str = None,
        user_id: str = None,
    ):
        """
        Initialize FlashcardCreator.

        Args:
            flashcard_repository (FlashcardRepositoryInterface): Repository to save flashcards
            cache (Optional[FlashcardCache], optional): Cache for summaries. Defaults to None.
        """
        self.flashcard_repository = flashcard_repository
        self.cache = cache or FlashcardCache(maxsize=settings.cache_maxsize, ttl=settings.cache_expiry)
        self.task_service = task_service
        self.logger = logging.getLogger(__name__)
        self.task_id = task_id
        self.user_id = user_id

    @handle_service_errors(default_return_value=None)
    async def get_cached_summary(
        self, text: str, config: FlashcardGenerationConfig, chatbot: Optional[ChatBot] = None
    ) -> str:
        """
        Generate or retrieve a cached summary for given text.

        Args:
            text (str): Text to summarize
            chatbot (Optional[ChatBot], optional): Chatbot for generating summary

        Returns:
            str: Generated or cached summary
        """
        if not chatbot:
            return text

        prompt = f"{self.PROMPT_PREFIX}. {config.get_summary_prompt(text)}"
        cache_key = f"summary_{hash(prompt)}"

        # Check cache first
        cached_summary = await self.cache.get(cache_key)
        if cached_summary:
            self.logger.info(f"Cache hit for prompt: {text[:50]}...")
            return cached_summary

        try:
            summary = await chatbot.get_summary(prompt)
            if summary:
                await self.cache.set(cache_key, summary)
                return summary
            return None
        except Exception as e:
            raise ChatBotError(str(e), chatbot.__class__.__name__)

    async def process_single_flashcard(
        self, item: Dict[str, str], config: FlashcardGenerationConfig, chatbot: Optional[ChatBot]
    ) -> Optional[Flashcard]:
        """Process a single flashcard item."""
        try:
            card = Flashcard(front=item["front"], back=item["back"], url=item["url"])

            # Validate content
            FlashcardValidator.validate_flashcard_content(card.front)

            if chatbot:
                summary = await self.get_cached_summary(card.back, config, chatbot)
                if not summary:
                    raise FlashcardCreationError("Failed to generate summary")
                card.back = summary

            # Append URL to back content
            card.back += f'\n URL: <a href="{item["url"]}">Link</a>'
            return card

        except (FlashcardValidationError, ChatBotError) as e:
            self.logger.warning(f"Skipping flashcard: {str(e)}", extra=e.details)
            return None
        except Exception as e:
            raise FlashcardCreationError(str(e))

    @handle_exceptions(
        {
            FlashcardValidationError: (400, "Invalid flashcard content"),
            FlashcardCreationError: (500, "Failed to create flashcard"),
            FlashcardStorageError: (500, "Failed to store flashcard"),
        }
    )
    async def create_flashcards(
        self,
        notion_content: List[Dict[str, str]],
        config: FlashcardGenerationConfig = None,
        chatbot: Optional[ChatBot] = None,
        batch_size: int = 10,
    ) -> Tuple[str, str]:
        """
        Create flashcards from provided content.

        Args:
            headings_and_bullets (List[Dict[str, str]]): Content to convert to flashcards
            chatbot (Optional[ChatBot], optional): Chatbot for summary generation
            batch_size (int, optional): Number of flashcards to process in batch
        """
        if not notion_content:
            raise ValidationError("No content provided", "notion_content")

        total_items = len(notion_content)
        processed_items = 0
        skipped_items = 0

        try:
            for item in notion_content:
                processed_items += 1

                try:
                    card = await self.process_single_flashcard(item, config, chatbot)

                    if not card:
                        skipped_items += 1
                        continue

                    # Save flashcard
                    await self.flashcard_repository.save_flashcard(card)

                    # Update progress
                    if self.task_service:
                        await self.task_service.update_task_progress(
                            user_id=self.user_id,
                            task_id=self.task_id,
                            progress=int((processed_items / total_items) * 100),
                            status="processing",
                            message=f"Created flashcard ({processed_items}/{total_items})",
                        )

                except Exception as e:
                    skipped_items += 1
                    self.logger.error(f"Error processing flashcard: {str(e)}")
                    if self.task_service:
                        await self.task_service.update_task_progress(
                            user_id=self.user_id,
                            task_id=self.task_id,
                            progress=int((processed_items / total_items) * 100),
                            status="warning",
                            message=f"Error with flashcard ({processed_items}/{total_items}): {str(e)}",
                        )

                await asyncio.sleep(0.1)  # Prevent overwhelming the system

            # Determine final status
            if skipped_items == total_items:
                message = "All flashcards failed to generate"
                status = "failed"
            elif skipped_items > 0:
                message = f"Flashcard generation completed with {processed_items - skipped_items} successful and {skipped_items} failed"
                status = "completed_with_errors"
            else:
                message = f"Flashcard generation completed successfully for all {total_items} flashcards"
                status = "completed"

            if self.task_service:
                await self.task_service.update_task_progress(
                    user_id=self.user_id, task_id=self.task_id, progress=100, status=status, message=message
                )

            return message, status

        except Exception as e:
            raise FlashcardCreationError(str(e))


class FlashcardService:
    """Orchestrates the flashcard creation process."""

    def __init__(
        self,
        flashcard_creator: FlashcardCreator,
        notion_content: List[Dict[str, str]],
        config: FlashcardGenerationConfig,
        chatbot: Optional[ChatBot] = None,
    ):
        """
        Initialize FlashcardService.

        Args:
            flashcard_creator (FlashcardCreator): Creator to generate flashcards
            notion_content (List[Dict[str, str]]): Content to convert to flashcards
            chatbot (Optional[ChatBot], optional): Chatbot for summary generation
        """
        self.flashcard_creator = flashcard_creator
        self.notion_content = notion_content
        self.config = config
        self.chatbot = chatbot
        self.logger = logging.getLogger(__name__)

    @handle_exceptions({FlashcardError: (500, "Flashcard generation failed"), ValidationError: (400, "Invalid input")})
    async def run(self) -> Tuple[str, str]:
        """Execute flashcard creation process."""
        if not self.notion_content:
            raise ValidationError("No content provided", "notion_content")

        try:
            return await self.flashcard_creator.create_flashcards(self.notion_content, self.config, self.chatbot)
        except Exception as e:
            raise FlashcardError(str(e))
