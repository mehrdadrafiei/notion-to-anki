import asyncio
import logging
import time
from functools import wraps
from typing import Callable, Dict, List, Optional, Union

from cachetools import TTLCache
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.config import settings
from src.domain.task.task_service import TaskService

from ...repositories.FlashcardRepository import Flashcard, FlashcardRepositoryInterface
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

    def get(self, key: str) -> Optional[str]:
        """
        Retrieve value from cache.

        Args:
            key (str): Cache key

        Returns:
            Optional[str]: Cached value or None
        """
        return self.cache.get(key)

    def set(self, key: str, value: str) -> None:
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

    PROMPT_PREFIX = (
        "Summarize the following text for the back of an Anki flashcard. "
        "Provide only the summary, enclosed in [[ ]]: \n"
    )

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
        self.progress_callback: Optional[Callable] = None
        self.task_service = task_service
        self.logger = logging.getLogger(__name__)
        self.task_id = task_id
        self.user_id = user_id

    @retry(stop=stop_after_attempt(settings.max_retries), wait=wait_exponential(multiplier=1, min=4, max=10))
    @rate_limit(calls=settings.rate_limit_calls, period=settings.rate_limit_period)
    async def get_cached_summary(self, text: str, chatbot: Optional[ChatBot] = None) -> str:
        """
        Generate or retrieve a cached summary for given text.

        Args:
            text (str): Text to summarize
            chatbot (Optional[ChatBot], optional): Chatbot for generating summary

        Returns:
            str: Generated or cached summary
        """
        prompt = f"{self.PROMPT_PREFIX} {text}"
        cache_key = f"summary_{hash(prompt)}"

        # Check cache first
        cached_summary = self.cache.get(cache_key)
        if cached_summary:
            self.logger.info(f"Cache hit for prompt: {text[:50]}...")
            return cached_summary

        # Generate summary if chatbot available
        if not chatbot:
            return text

        try:
            summary = await chatbot.get_summary(prompt)

            if summary:
                self.cache.set(cache_key, summary)
                return summary
            return None
        except Exception as e:
            self.logger.error(f"Error getting summary: {e}")
            return None

    async def create_flashcards(
        self, headings_and_bullets: List[Dict[str, str]], chatbot: Optional[ChatBot] = None, batch_size: int = 10
    ) -> Union[str, str]:
        """
        Create flashcards from provided content.

        Args:
            headings_and_bullets (List[Dict[str, str]]): Content to convert to flashcards
            chatbot (Optional[ChatBot], optional): Chatbot for summary generation
            batch_size (int, optional): Number of flashcards to process in batch
        """
        self.logger.info(f"Starting flashcard creation for {len(headings_and_bullets)} items")

        # Retrieve existing flashcards to avoid duplicates
        existing_flashcards = await self.flashcard_repository.get_existing_flashcards()
        total_items = len(headings_and_bullets)
        processed_items = 0
        skipped_items = 0

        for item in headings_and_bullets:
            processed_items += 1

            # Create flashcard
            card = Flashcard(front=item["front"], back=item["back"], url=item["url"])

            # Skip existing flashcards
            if card.front in existing_flashcards:
                skipped_items += 1
                if self.task_service:
                    await self.task_service.update_task_progress(
                        user_id=self.user_id,
                        task_id=self.task_id,
                        progress=int((processed_items / total_items) * 100),
                        status="processing",
                        message=f"Skipped existing flashcard ({processed_items}/{total_items})",
                    )
                self.logger.info(f"Skipping existing flashcard: {card.front[:50]}...")
                await asyncio.sleep(0.1)
                continue

            # Validate content
            if not FlashcardValidator.validate_flashcard_content(card.front):
                skipped_items += 1
                self.logger.warning(f"Invalid content skipped: {card.front[:50]}...")
                continue

            try:
                if chatbot:
                    # Try to get summary, skip if it fails
                    summary = await self.get_cached_summary(card.back, chatbot)
                    if summary is None:
                        skipped_items += 1
                        if self.task_service:
                            await self.task_service.update_task_progress(
                                user_id=self.user_id,
                                task_id=self.task_id,
                                progress=int((processed_items / total_items) * 100),
                                status="warning",
                                message=f"Skipped flashcard due to summarization failure ({skipped_items} skipped)",
                            )
                        self.logger.warning(f"Skipping flashcard due to summarization failure: {card.front[:50]}...")
                        continue

                    card.back = summary

                # Append URL to back content
                card.back += f'\n URL: <a href="{item["url"]}">Link</a>'

                # Save flashcard
                await self.flashcard_repository.save_flashcard(card)

                # Update progress after saving
                if self.task_service:
                    await self.task_service.update_task_progress(
                        user_id=self.user_id,
                        task_id=self.task_id,
                        progress=int((processed_items / total_items) * 100),
                        status="processing",
                        message=f"Created flashcard ({processed_items}/{total_items})",
                    )

                self.logger.info(f"Created flashcard: {card.front[:50]}...")
                await asyncio.sleep(0.1)

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
                await asyncio.sleep(0.1)

        # Final progress update
        if self.task_service:
            if skipped_items == total_items:
                message = "All flashcards failed to generate"
                status = "failed"
            elif skipped_items > 0:
                message = f"Flashcard generation completed with {processed_items - skipped_items} successful and {skipped_items} failed"
                status = "completed_with_errors"
            else:
                message = f"Flashcard generation completed successfully for all {total_items} flashcards"
                status = "completed"

            await self.task_service.update_task_progress(
                user_id=self.user_id,
                task_id=self.task_id,
                progress=100,
                status=status,
                message=message,
            )
        self.logger.info(f"Flashcard creation completed in '{self.flashcard_repository.anki_output_file}'")

        return message, status


class FlashcardService:
    """Orchestrates the flashcard creation process."""

    def __init__(
        self,
        flashcard_creator: FlashcardCreator,
        notion_content: List[Dict[str, str]],
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
        self.chatbot = chatbot
        self.logger = logging.getLogger(__name__)

    async def run(self) -> Union[str, str]:
        """Execute flashcard creation process."""
        try:
            return await self.flashcard_creator.create_flashcards(self.notion_content, self.chatbot)
        except Exception as e:
            self.logger.error(f"Error in flashcard creation: {e}")
            raise