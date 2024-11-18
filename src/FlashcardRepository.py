from abc import ABC, abstractmethod
from typing import Dict, List


class FlashcardRepository(ABC):
    @abstractmethod
    async def save(self, flashcards: List[Dict[str, str]]) -> None:
        pass

    @abstractmethod
    async def get_by_notion_page(self, page_id: str) -> List[Dict[str, str]]:
        pass


class CSVFlashcardRepository(FlashcardRepository):
    def __init__(self, base_path: str):
        self.base_path = base_path

    async def save(self, flashcards: List[Dict[str, str]]) -> None:
        # Implementation for CSV storage
        pass
