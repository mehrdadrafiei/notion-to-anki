from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from src.domain.chatbot.factory import ChatBotFactory
from src.domain.flashcard.config import ExportFormat, SummaryLength


class FlashcardRequest(BaseModel):
    """Request schema for generating flashcards"""

    notion_page: str = Field(..., description="Notion page ID or URL")
    output_path: str = Field("output/flashcards.csv", description="Path to save the flashcards")
    export_format: ExportFormat = Field(ExportFormat.CSV, description="Export format (csv or anki)")
    batch_size: int = Field(10, gt=0, le=100)
    use_chatbot: bool = Field(False)
    chatbot_type: Optional[str] = Field(None)
    summary_length: SummaryLength = Field(SummaryLength.MEDIUM)
    include_urls: bool = Field(True)
    include_checklists: bool = Field(True)
    include_headings: bool = Field(True)
    include_bullets: bool = Field(True)
    include_toggles: bool = Field(True)
    max_cards: Optional[int] = Field(None)

    @field_validator("chatbot_type")
    def validate_chatbot_type(cls, value, values):
        """
        Validate chatbot type when using a chatbot.

        Args:
            value (str): Chatbot type
            values (Dict): Other request values

        Returns:
            str: Validated chatbot type

        Raises:
            ValueError: If chatbot type is invalid
        """
        if values.data.get('use_chatbot'):
            if not value:
                raise ValueError("Chatbot type is required when use_chatbot is True")
            available_chatbots = ChatBotFactory.get_available_chatbots()
            if value not in available_chatbots:
                raise ValueError(f"Invalid chatbot type. Allowed types: {available_chatbots}")
        return value

    class Config:
        json_schema_extra = {
            "example": {
                "notion_page": "page_id_or_url",
                "output_path": "output/flashcards.csv",
                "export_format": "csv",
                "use_chatbot": True,
                "chatbot_type": "groq",
                "summary_length": "medium",
                "include_checklists": True,
                "include_headings": True,
                "include_bullets": True,
                "max_cards": 50,
                "batch_size": 10,
            }
        }


class FlashcardResponse(BaseModel):
    """Response schema for generating flashcards"""

    message: str
    task_id: str
