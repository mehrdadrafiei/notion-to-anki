from typing import Dict, Optional

from .base import AppError


class NotionError(AppError):
    """Notion-related errors"""

    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, "NOTION_ERROR", details)


class NotionAuthenticationError(NotionError):
    """Notion authentication errors"""

    def __init__(self):
        super().__init__("Failed to authenticate with Notion API")


class NotionContentError(NotionError):
    """Notion content processing errors"""

    def __init__(self, message: str, page_id: str):
        super().__init__(message, {"page_id": page_id})


class ChatBotError(AppError):
    """Chatbot-related errors"""

    def __init__(self, message: str, bot_type: str, details: Optional[Dict] = None):
        super().__init__(message=message, error_code="CHATBOT_ERROR", details={"bot_type": bot_type, **(details or {})})


class TaskError(AppError):
    """Task-related errors"""

    def __init__(self, message: str, task_id: str, details: Optional[Dict] = None):
        super().__init__(message=message, error_code="TASK_ERROR", details={"task_id": task_id, **(details or {})})


class FlashcardError(AppError):
    """Base class for flashcard-related errors"""

    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, "FLASHCARD_ERROR", details)


class FlashcardValidationError(FlashcardError):
    """Raised when flashcard content validation fails"""

    def __init__(self, field: str, reason: str, value: Optional[str] = None):
        details = {"field": field, "reason": reason}
        if value:
            details["value"] = value
        super().__init__(f"Invalid flashcard {field}: {reason}", details)


class FlashcardCreationError(FlashcardError):
    """Raised when flashcard creation fails"""

    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(f"Failed to create flashcard: {message}", details)


class FlashcardStorageError(FlashcardError):
    """Raised when flashcard storage operations fail"""

    def __init__(self, operation: str, reason: str, details: Optional[Dict] = None):
        super().__init__(
            f"Flashcard storage {operation} failed: {reason}",
            {"operation": operation, "reason": reason, **(details or {})},
        )
