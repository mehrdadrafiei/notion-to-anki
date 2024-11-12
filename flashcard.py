import csv
import logging
import os
import time
from functools import wraps
from typing import Dict, List

from cachetools import TTLCache
from tenacity import retry, stop_after_attempt, wait_exponential

from chatbots import ChatBot, GroqChatBot, MistralChatBot
from notion_handler import NotionClientHandler, NotionHandler

NOTION_PAGE_ID = os.getenv("NOTION_PAGE_ID")
ANKI_OUTPUT_FILE = "anki_flashcards.csv"
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
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            last_called[0] = time.time()
            return func(*args, **kwargs)

        return wrapper

    return decorator


class FlashcardStorage:
    def __init__(self, anki_output_file: str):
        self.anki_output_file = anki_output_file
        self.logger = logging.getLogger(__name__)

    def get_existing_flashcards(self):
        existing_flashcards = set()
        if os.path.exists(self.anki_output_file):
            try:
                with open(self.anki_output_file, mode="r", newline="", encoding="utf-8") as file:
                    reader = csv.reader(file)
                    for row in reader:
                        existing_flashcards.add(row[0])
                self.logger.info(f"Loaded {len(existing_flashcards)} existing flashcards")
            except Exception as e:
                self.logger.error(f"Error loading existing flashcards: {str(e)}")
        return existing_flashcards

    def save_flashcard(self, front: str, back_with_link: str):
        try:
            with open(self.anki_output_file, mode="a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow([front, back_with_link])
                logger.info(f"Flashcard with front: '{front}' created!")
        except Exception as e:
            self.logger.error(f"Error saving flashcard: {str(e)}")
            raise


class FlashcardCreator:
    def __init__(self, flashcard_storage: FlashcardStorage):
        self.flashcard_storage = flashcard_storage
        self.cache = TTLCache(maxsize=100, ttl=3600)  # Cache responses for 1 hour

    def validate_flashcard_content(self, text: str) -> bool:
        """Validate flashcard content meets requirements."""
        if not text or not isinstance(text, str):
            return False
        if len(text.strip()) < 3:  # Minimum content length
            return False
        if len(text) > 500:  # Maximum content length
            return False
        return True

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    @rate_limit(calls=10, period=60)  # 10 calls per minute
    def get_cached_summary(self, prompt: str, chatbot: ChatBot) -> str:
        """Get summary with caching and retry logic."""
        cache_key = f"summary_{hash(prompt)}"
        if cache_key in self.cache:
            logger.info(f"Cache hit for prompt: {prompt[:50]}...")
            return self.cache[cache_key]

        summary = chatbot.get_summary(prompt)
        self.cache[cache_key] = summary
        return summary

    def create_flashcards(
        self, headings_and_bullets: List[Dict[str, str]], chatbot: ChatBot, batch_size: int = 10
    ) -> None:
        """
        Creates flashcards from headings and bullets using the specified chatbot.

        Args:
            headings_and_bullets: List of dictionaries containing text and URLs
            chatbot: ChatBot instance to generate summaries
            batch_size: Number of flashcards to process in one batch
        """
        logger.info(f"Starting flashcard creation for {len(headings_and_bullets)} items")
        existing_flashcards = self.flashcard_storage.get_existing_flashcards()

        for i in range(0, len(headings_and_bullets), batch_size):
            batch = headings_and_bullets[i : i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}")

            for item in batch:
                front = item["text"]
                # Validate content
                if not self.validate_flashcard_content(front):
                    logger.warning(f"Invalid content skipped: {front[:50]}...")
                    continue

                if front in existing_flashcards:
                    logger.info(f"Skipping existing flashcard: {front[:50]}...")
                    continue

                try:
                    prompt = f"{PROMPT_PREFIX} {front}"
                    back = self.get_cached_summary(prompt, chatbot)
                    back_with_link = f'{back}\n URL: <a href="{item["url"]}">Link</a>'
                    self.flashcard_storage.save_flashcard(front, back_with_link)
                    logger.info(f"Created flashcard: {front[:50]}...")
                except Exception as e:
                    logger.error(f"Error creating flashcard: {str(e)}")

        logger.info(f"Flashcard creation completed in '{self.flashcard_storage.anki_output_file}'")


class FlashcardService:
    def __init__(self, notion_handler: NotionHandler, chatbot: ChatBot, flashcard_creator: FlashcardCreator):
        self.notion_handler = notion_handler
        self.chatbot = chatbot
        self.flashcard_creator = flashcard_creator

    def run(self) -> None:
        headings_and_bullets = self.notion_handler.get_headings_and_bullets()
        self.flashcard_creator.create_flashcards(headings_and_bullets, self.chatbot)


def chatbot_factory(chatbot_type: str) -> ChatBot:
    if chatbot_type == "groq":
        return GroqChatBot()
    elif chatbot_type == "mistral":
        return MistralChatBot()
    else:
        raise ValueError("Unsupported chatbot type")


def notion_handler_factory(page_id: str) -> NotionHandler:
    return NotionClientHandler(page_id)


if __name__ == "__main__":
    notion_handler = notion_handler_factory(NOTION_PAGE_ID)
    chatbot = chatbot_factory("mistral")
    flashcard_storage = FlashcardStorage(ANKI_OUTPUT_FILE)
    flashcard_creator = FlashcardCreator(flashcard_storage)

    service = FlashcardService(notion_handler, chatbot, flashcard_creator)
    service.run()

    logger.info("Process completed!")
