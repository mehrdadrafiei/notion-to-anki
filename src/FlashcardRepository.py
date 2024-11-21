import csv
import logging
import os
from abc import ABC, abstractmethod
from typing import Dict, List

import aiofiles as aiof


class FlashcardRepository(ABC):
    @abstractmethod
    async def get_existing_flashcards(self, page_id: str) -> set:
        pass

    @abstractmethod
    async def save_flashcard(self, flashcards: List[Dict[str, str]]) -> None:
        pass


class CSVFlashcardRepository(FlashcardRepository):
    """
    A class for handling flashcards stored in a CSV file.
    """

    def __init__(self, anki_output_file: str):
        self.anki_output_file = anki_output_file
        self.logger = logging.getLogger(__name__)

    # TODO: Not using this anymore, update it later.
    async def get_existing_flashcards(self) -> set:
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

    async def save_flashcard(self, front: str, back_with_link: str) -> None:
        try:
            async with aiof.open(self.anki_output_file, mode="a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                await writer.writerow([front, back_with_link])
                self.logger.info(f"Flashcard with front: '{front}' created!")
        except Exception as e:
            self.logger.error(f"Error saving flashcard: {str(e)}")
            raise
