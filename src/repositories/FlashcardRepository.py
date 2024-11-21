import csv
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Generic, List, Optional, TypeVar

import aiofiles

# Generic type for repository
T = TypeVar('T')


@dataclass
class Flashcard:
    """Domain model representing a Flashcard."""

    front: str
    back: str
    url: Optional[str] = None
    tags: Optional[List[str]] = field(default_factory=list)
    created_at: Optional[str] = None

    def __post_init__(self):
        """Validate flashcard data after initialization."""
        if not self.front or not self.back:
            raise ValueError("Flashcard must have both front and back content")

        # Trim excessive whitespace
        self.front = self.front.strip()
        self.back = self.back.strip()


class FlashcardRepositoryInterface(ABC, Generic[T]):
    """Abstract base class defining the interface for Flashcard repositories."""

    @abstractmethod
    async def get_existing_flashcards(self) -> set:
        """
        Retrieve a set of existing flashcards.

        Returns:
            set: A set of existing flashcard identifiers.
        """
        pass

    @abstractmethod
    async def save_flashcard(self, item: T) -> None:
        """
        Save a single flashcard.

        Args:
            item (T): The flashcard to be saved.
        """
        pass


class CSVFlashcardRepository(FlashcardRepositoryInterface):
    """Concrete implementation of a CSV-based Flashcard repository."""

    def __init__(self, anki_output_file: str):
        """
        Initialize the CSV Flashcard Repository.

        Args:
            anki_output_file (str): Path to the output CSV file.
        """
        self.anki_output_file = anki_output_file
        self.logger = logging.getLogger(__name__)

    async def get_existing_flashcards(self) -> set:
        """
        Load existing flashcards from the CSV file.

        Returns:
            set: A set of existing flashcard front texts.
        """
        existing_flashcards = set()

        if not os.path.exists(self.anki_output_file):
            return existing_flashcards

        try:
            async with aiofiles.open(self.anki_output_file, mode="r", encoding="utf-8") as file:
                content = await file.read()
                reader = csv.reader(content.splitlines())
                existing_flashcards = {row[0] for row in reader if row}

            self.logger.info(f"Loaded {len(existing_flashcards)} existing flashcards")
        except Exception as e:
            self.logger.error(f"Error loading existing flashcards: {str(e)}")

        return existing_flashcards

    async def save_flashcard(self, item: Flashcard) -> None:
        """
        Save a single flashcard to the CSV file.

        Args:
            item (Flashcard): The flashcard to be saved.

        Raises:
            Exception: If there's an error during file writing.
        """
        try:
            async with aiofiles.open(self.anki_output_file, mode="a", encoding="utf-8", newline="") as file:
                writer = csv.writer(file)
                await writer.writerow([item.front, item.back])
                self.logger.info(f"Flashcard with front: '{item.front[:50]}...' created!")
        except Exception as e:
            self.logger.error(f"Error saving flashcard: {str(e)}")
            raise
