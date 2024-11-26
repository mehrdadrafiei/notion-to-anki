class NotionServiceError(Exception):
    """Base exception for Notion service-related errors."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class NotionAuthenticationError(NotionServiceError):
    """Raised when there are authentication issues with Notion API."""

    pass


class NotionPageNotFoundError(NotionServiceError):
    """Raised when a Notion page cannot be found."""

    pass


class NotionContentError(NotionServiceError):
    """Raised when there are issues processing Notion content."""

    pass
