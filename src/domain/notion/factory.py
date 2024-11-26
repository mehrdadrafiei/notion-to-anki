from typing import Optional

from src.core.config import settings

from .service import NotionService


async def create_notion_service(api_key: Optional[str] = None) -> NotionService:
    """
    Factory function to create a NotionService instance.

    Args:
        api_key (Optional[str]): Optional API key override

    Returns:
        NotionService: Configured Notion service
    """
    service = NotionService(api_key or settings.notion_api_key)
    return service
