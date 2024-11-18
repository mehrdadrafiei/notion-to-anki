import asyncio
import csv
import logging
import os
import time
from functools import wraps
from typing import Dict, List, Optional

import aiofiles as aiof
from cachetools import TTLCache
from tenacity import retry, stop_after_attempt, wait_exponential

from chatbots.base import ChatBot
from config import settings

PROMPT_PREFIX = (
    "Summarize the following text for the back of an Anki flashcard. Provide only the summary, enclosed in [[ ]]: \n"
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', filename='flashcard_service.log'
)
logger = logging.getLogger(__name__)


# Rate limiter decorator
def rate_limit(calls: int, period: int):
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


class FlashcardStorage:
    def __init__(self, anki_output_file: str):
        self.anki_output_file = anki_output_file
        self.logger = logging.getLogger(__name__)

    # TODO: Not using this anymore, update it later.
    async def get_existing_flashcards(self):
        existing_flashcards = set()
        if os.path.exists(self.anki_output_file):
            try:
                async with aiof.open(self.anki_output_file, mode="r", newline="", encoding="utf-8") as file:
                    reader = csv.reader(await file.readlines())
                    for row in reader:
                        existing_flashcards.add(row[0])
                self.logger.info(f"Loaded {len(existing_flashcards)} existing flashcards")
            except Exception as e:
                self.logger.error(f"Error loading existing flashcards: {str(e)}")
        return existing_flashcards

    async def save_flashcard(self, front: str, back_with_link: str):
        try:
            async with aiof.open(self.anki_output_file, mode="a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                await writer.writerow([front, back_with_link])
                logger.info(f"Flashcard with front: '{front}' created!")
        except Exception as e:
            self.logger.error(f"Error saving flashcard: {str(e)}")
            raise


class FlashcardCreator:
    def __init__(self, flashcard_storage: FlashcardStorage):
        self.flashcard_storage = flashcard_storage
        self.cache = TTLCache(maxsize=100, ttl=settings.cache_expiry)  # Cache responses for 1 hour
        self.progress_callback = None

    def set_progress_callback(self, callback):
        self.progress_callback = callback

    def update_progress(self, processed_items: int, total_items: int, status: str, message: str):
        if self.progress_callback:
            progress = int((processed_items / total_items) * 100)
            self.progress_callback(progress, status, message)

    def validate_flashcard_content(self, text: str) -> bool:
        """Validate flashcard content meets requirements."""
        if not text or not isinstance(text, str):
            return False
        if len(text.strip()) < 3:  # Minimum content length
            return False
        if len(text) > 500:  # Maximum content length
            return False
        return True

    @retry(stop=stop_after_attempt(settings.max_retries), wait=wait_exponential(multiplier=1, min=4, max=10))
    @rate_limit(calls=settings.rate_limit_calls, period=settings.rate_limit_period)  # 10 calls per minute
    async def get_cached_summary(self, text: str, chatbot: Optional[ChatBot] = None) -> str:
        """Get summary with caching and retry logic."""
        prompt = f"{PROMPT_PREFIX} {text}"
        cache_key = f"summary_{hash(prompt)}"
        if cache_key in self.cache:
            logger.info(f"Cache hit for prompt: {text[:50]}...")
            return self.cache[cache_key]

        summary = await chatbot.get_summary(prompt)
        self.cache[cache_key] = summary
        return summary

    async def create_flashcards(
        self, headings_and_bullets: List[Dict[str, str]], chatbot: Optional[ChatBot] = None, batch_size: int = 10
    ) -> None:
        """
        Creates flashcards from headings and bullets using the specified chatbot.

        Args:
            headings_and_bullets: List of dictionaries containing text and URLs
            chatbot: ChatBot instance to generate summaries
            batch_size: Number of flashcards to process in one batch
        """
        logger.info(f"Starting flashcard creation for {len(headings_and_bullets)} items")
        existing_flashcards = await self.flashcard_storage.get_existing_flashcards()
        total_items = len(headings_and_bullets)
        processed_items = 0

        for item in headings_and_bullets:
            front = item["front"]
            back = item["back"]

            if front in existing_flashcards:
                processed_items += 1
                self.update_progress(
                    processed_items,
                    total_items,
                    "processing",
                    f"Skipped existing flashcard ({processed_items}/{total_items})",
                )
                logger.info(f"Skipping existing flashcard: {front[:50]}...")
                # Add a small delay to ensure WebSocket has time to process
                await asyncio.sleep(0.1)
                continue

            # Validate content
            if not self.validate_flashcard_content(front):
                logger.warning(f"Invalid content skipped: {front[:50]}...")
                continue

            try:
                back = await self.get_cached_summary(back, chatbot) if chatbot else back
                back_with_link = f'{back}\n URL: <a href="{item["url"]}">Link</a>'
                await self.flashcard_storage.save_flashcard(front, back_with_link)
                processed_items += 1
                self.update_progress(
                    processed_items, total_items, "processing", f"Created flashcard ({processed_items}/{total_items})"
                )
                await asyncio.sleep(0.1)
                logger.info(f"Created flashcard: {front[:50]}...")

            except Exception as e:
                logger.error(f"Error processing flashcard: {str(e)}")
                self.update_progress(
                    processed_items,
                    total_items,
                    "warning",
                    f"Error with flashcard ({processed_items}/{total_items}): {str(e)}",
                )
                await asyncio.sleep(0.1)

        # Final progress update
        self.update_progress(
            total_items, total_items, "completed", f"Completed processing all {total_items} flashcards"
        )
        logger.info(f"Flashcard creation completed in '{self.flashcard_storage.anki_output_file}'")


class FlashcardService:
    def __init__(
        self,
        flashcard_creator: FlashcardCreator,
        notion_content: List[Dict[str, str]],
        chatbot: Optional[ChatBot] = None,
    ):
        self.flashcard_creator = flashcard_creator
        self.notion_content = notion_content
        self.chatbot = chatbot

    def set_progress_callback(self, callback):
        self.flashcard_creator.set_progress_callback(callback)

    async def run(self) -> None:
        await self.flashcard_creator.create_flashcards(self.notion_content, self.chatbot)
