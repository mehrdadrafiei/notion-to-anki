class AppError(Exception):
    """Base application exception"""

    pass


class ValidationError(AppError):
    """Raised when input validation fails"""

    pass


class NotionError(AppError):
    """Raised when Notion API operations fail"""

    pass


class FlashcardError(AppError):
    """Raised when flashcard operations fail"""

    pass


class ChatBotError(AppError):
    """Raised when chatbot operations fail"""

    pass
