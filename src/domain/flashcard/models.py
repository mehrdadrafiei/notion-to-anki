from dataclasses import dataclass, field
from typing import List, Optional


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
