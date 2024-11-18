class ChatBotError(Exception):
    """Base exception for all chatbot-related errors"""

    pass


class ChatBotNotFoundError(ChatBotError):
    """Raised when a requested chatbot type is not found"""

    pass


class ChatBotInitializationError(ChatBotError):
    """Raised when a chatbot fails to initialize"""

    pass


class ChatBotAPIError(ChatBotError):
    """Raised when there's an error communicating with the chatbot API"""

    pass
