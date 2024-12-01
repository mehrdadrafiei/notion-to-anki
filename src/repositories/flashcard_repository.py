import asyncio
import csv
import logging
import os
import random
from abc import ABC, abstractmethod
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TypeVar

import aiofiles
import genanki

from ..core.exceptions.domain import FlashcardStorageError
from ..domain.flashcard.config import ExportFormat
from ..domain.flashcard.models import Flashcard

logger = logging.getLogger(__name__)
T = TypeVar('T')


class FlashcardRepositoryInterface(ABC):
    """Abstract base class defining the interface for Flashcard repositories."""

    def __init__(self, base_dir: str = "output", export_format: str = "csv"):
        self.base_dir = base_dir
        self.export_format = export_format

    @abstractmethod
    async def get_flashcards(self, limit: int = 5) -> List[Dict[str, str]]:
        """Retrieve a list of flashcards."""
        pass

    @abstractmethod
    async def save_flashcard(self, item: T) -> None:
        """
        Save a single flashcard.

        Args:
            item (T): The flashcard to be saved.
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Perform any necessary cleanup."""
        pass


class CSVFlashcardRepository(FlashcardRepositoryInterface):
    """CSV implementation of flashcard repository."""

    def __init__(self, output_file: str):
        """
        Initialize the CSV Flashcard Repository.

        Args:
            output_file (str): Path to the output CSV file.
        """
        self.output_file = Path(output_file)
        self.logger = logging.getLogger(__name__)
        self._file_lock = asyncio.Lock()
        self._ensure_output_directory()

    def _ensure_output_directory(self) -> None:
        """Ensure the output directory exists."""
        self.output_file.parent.mkdir(parents=True, exist_ok=True)

    async def get_flashcards(self, limit: int = 5) -> List[Dict[str, str]]:
        """
        Load flashcards from the CSV file.

        Returns:
            set: A list of flashcards.
        """
        flashcards = []

        if not self.output_file.exists():
            return flashcards

        try:
            async with self._file_lock:
                async with aiofiles.open(self.output_file, mode="r", encoding="utf-8") as file:
                    content = await file.read()
                    reader = csv.reader(content.splitlines())
                    for row in list(reader)[:limit]:
                        flashcards.append({"front": row[0], "back": row[1]})

            self.logger.info(f"Loaded {len(flashcards)} existing flashcards")
        except Exception as e:
            self.logger.error(f"Error loading existing flashcards: {str(e)}")

        return flashcards

    async def save_flashcard(self, flashcard: Flashcard) -> None:
        """
        Save a single flashcard to the CSV file.

        Args:
            flashcard (Flashcard): The flashcard to be saved.

        Raises:
            FlashcardStorageError: If there's an error during file writing.
        """
        try:
            async with self._file_lock:
                async with aiofiles.open(self.output_file, mode="a", encoding="utf-8", newline="") as file:
                    # Convert to CSV line and write
                    writer = csv.writer(file)
                    await writer.writerow([flashcard.front, flashcard.back])

                self.logger.info(f"Flashcard saved successfully: {flashcard.front[:50]}...")
        except Exception as e:
            error_msg = f"Error saving flashcard: {str(e)}"
            self.logger.error(error_msg)
            raise FlashcardStorageError(error_msg)

    async def cleanup(self) -> None:
        """
        Perform cleanup operations. For CSV, mainly logging completion.
        """
        self.logger.info(f"Completed flashcard generation to {self.output_file}")


class AnkiFlashcardRepository(FlashcardRepositoryInterface):
    """Simple Anki implementation of flashcard repository."""

    def __init__(self, output_file: str):
        """
        Initialize the Anki Flashcard Repository.

        Args:
            output_file (str): Path to save the Anki deck
        """
        self.output_file = Path(output_file)
        self.logger = logging.getLogger(__name__)
        self._file_lock = asyncio.Lock()
        self._ensure_output_directory()
        self._flashcards = []  # In-memory list to store cards

        # Setup basic Anki deck and model
        self.model = genanki.Model(
            1607392319,  # Fixed model ID
            "Basic",
            fields=[{'name': 'Front'}, {'name': 'Back'}],
            templates=[{'name': 'Card', 'qfmt': '{{Front}}', 'afmt': '{{FrontSide}}<hr id="answer">{{Back}}'}],
        )
        self.deck = genanki.Deck(2059400110, "Generated Flashcards")  # Fixed deck ID

    def _ensure_output_directory(self) -> None:
        """Ensure the output directory exists."""
        self.output_file.parent.mkdir(parents=True, exist_ok=True)

    async def get_flashcards(self, limit: int = 5) -> List[Dict[str, str]]:
        """
        Return the most recently added flashcards.
        Args:
            limit (int): Maximum number of flashcards to return
        Returns:
            list: List of recent flashcards
        """
        return self._flashcards[-limit:]  # Return last 'limit' cards

    async def save_flashcard(self, flashcard: Flashcard) -> None:
        """
        Save a single flashcard to the Anki deck.

        Args:
            flashcard (Flashcard): The flashcard to be saved.

        Raises:
            FlashcardStorageError: If there's an error during saving.
        """
        try:
            async with self._file_lock:
                # Create a basic note with just front and back
                note = genanki.Note(model=self.model, fields=[flashcard.front, flashcard.back])
                self.deck.add_note(note)

                # Add to in-memory list
                self._flashcards.append({"front": flashcard.front, "back": flashcard.back})

                # Save the deck immediately
                package = genanki.Package(self.deck)
                package.write_to_file(str(self.output_file))

            self.logger.info(f"Flashcard saved successfully: {flashcard.front[:50]}...")

        except Exception as e:
            error_msg = f"Error saving flashcard: {str(e)}"
            self.logger.error(error_msg)
            raise FlashcardStorageError(error_msg)

    async def cleanup(self) -> None:
        """
        Perform cleanup operations. For Anki, mainly logging completion.
        """
        self.logger.info(f"Completed flashcard generation to {self.output_file}")


class FlashcardRepositoryFactory:
    """Factory for creating flashcard repositories."""

    @staticmethod
    def create(export_format: ExportFormat, output_file: str, **kwargs: Dict[str, Any]) -> FlashcardRepositoryInterface:
        """
        Create appropriate repository based on export format.

        Args:
            export_format (ExportFormat): Desired export format
            output_file (str): Path to save the output
            **kwargs: Additional arguments for specific repository types

        Returns:
            FlashcardRepositoryInterface: Configured repository instance

        Raises:
            ValueError: If export format is unsupported
        """
        if export_format == ExportFormat.ANKI:
            return AnkiFlashcardRepository(output_file + ".apkg", **kwargs)
        elif export_format == ExportFormat.CSV:
            return CSVFlashcardRepository(output_file + ".csv")
        else:
            raise ValueError(f"Unsupported export format: {export_format}")
