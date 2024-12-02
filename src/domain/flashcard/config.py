from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ExportFormat(Enum):
    CSV = "csv"
    ANKI = "anki"


class SummaryLength(Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"

    def word_limit(self):
        """Return the word limit for each summary length."""
        word_limits = {"short": 25, "medium": 50, "long": 100}
        return word_limits[self.value]


@dataclass
class FlashcardGenerationConfig:
    """Configuration for flashcard generation."""

    export_format: ExportFormat = ExportFormat.CSV
    use_ai_summary: bool = False
    summary_length: SummaryLength = SummaryLength.MEDIUM
    max_cards_per_page: Optional[int] = None
    include_urls: bool = True
    include_checklists: bool = True
    include_headings: bool = True
    include_bullets: bool = True
    include_toggles: bool = True

    def get_summary_prompt(self, text: str) -> str:
        """Generate appropriate prompt based on summary length setting."""

        word_count = len(text.split())
        if word_count <= self.summary_length.word_limit():
            return f"[[{text.strip()}]]"

        length_prompts = {
            SummaryLength.SHORT: "Summarize this concisely in about 50 words: ",
            SummaryLength.MEDIUM: "Provide a clear summary in about 100 words: ",
            SummaryLength.LONG: "Give a comprehensive summary in about 200 words: ",
        }
        return f"{length_prompts[self.summary_length]}\n\n`{text}`"
