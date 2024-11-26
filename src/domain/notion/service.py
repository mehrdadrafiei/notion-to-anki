import asyncio
import logging
import re
from typing import Dict, List, Optional

from notion_client import AsyncClient
from notion_client.errors import APIResponseError, HTTPResponseError

from src.core.config import settings
from src.core.error_handling import handle_exceptions, handle_service_errors
from src.core.exceptions.base import ExternalServiceError, ResourceNotFoundError, ValidationError
from src.core.exceptions.domain import NotionAuthenticationError, NotionContentError, NotionError

from .models import NotionBlock, NotionPage

logger = logging.getLogger(__name__)


class NotionService:
    """Service class for interacting with Notion API."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize NotionService with API key."""
        try:
            self.client = AsyncClient(auth=api_key or settings.notion_api_key)
            self._url_cache: Dict[str, str] = {}
        except Exception as e:
            raise NotionAuthenticationError() from e

    @staticmethod
    def extract_page_id(page_id_or_url: str) -> str:
        """
        Extract the page ID from a Notion page URL or return the input if it's already a page ID.

        Args:
            page_id_or_url (str): Notion page ID or URL

        Returns:
            str: Extracted page ID

        Raises:
            ValidationError: If the input is invalid
        """
        if not page_id_or_url:
            raise ValidationError("Page ID or URL cannot be empty", "page_id_or_url")

        if page_id_or_url.startswith(("https://www.notion.so/", "https://notion.so/")):
            match = re.search(r"[a-f0-9]{32}", page_id_or_url)
            if match:
                return match.group()
            raise ValidationError("Invalid Notion URL format", "page_id_or_url")

        if not re.match(r"^[a-f0-9]{32}$", page_id_or_url):
            raise ValidationError("Invalid page ID format", "page_id_or_url")

        return page_id_or_url

    @handle_service_errors(default_return_value=None)
    async def get_page_url(self, page_id: str) -> Optional[str]:
        """
        Retrieve the URL of the Notion page.

        Args:
            page_id (str): Notion page ID

        Returns:
            Optional[str]: The URL of the page or None if retrieval fails

        Raises:
            NotionError: If there's an error communicating with Notion API
        """
        if page_id in self._url_cache:
            return self._url_cache[page_id]

        try:
            page_content = await self.client.pages.retrieve(page_id=page_id)
            url = page_content.get("url")
            if url:
                self._url_cache[page_id] = url
                return url
            raise NotionError("Page URL not found in response", {"page_id": page_id})
        except APIResponseError as e:
            raise ExternalServiceError("Notion", "Failed to retrieve page URL", {"error": str(e)})

    async def _process_block(self, block: Dict, base_url: str) -> Optional[NotionBlock]:
        """
        Process a single block, including nested content.

        Args:
            block (Dict): Notion block to process
            base_url (str): Base URL of the page

        Returns:
            Optional[NotionBlock]: Processed block

        Raises:
            NotionContentError: If block processing fails
        """
        try:
            nested_text = ""
            if block.get('has_children', False):
                nested_blocks = await self.client.blocks.children.list(block_id=block['id'])
                nested_text = self._extract_nested_text(nested_blocks.get('results', []))

            return NotionBlock.from_block_data(block, base_url=base_url, nested_text=nested_text)
        except Exception as e:
            logger.warning(f"Failed to process block: {str(e)}", extra={"block_id": block.get('id')})
            return None

    def _extract_nested_text(self, children: List[Dict]) -> str:
        """
        Extract text from child blocks.

        Args:
            children (List[Dict]): List of child blocks

        Returns:
            str: Concatenated text from child blocks
        """
        texts = []
        supported_types = ['paragraph', 'bulleted_list_item', 'heading_1', 'heading_2', 'heading_3']

        for child in children:
            block_type = child['type']
            if block_type in supported_types:
                try:
                    text = child[block_type]['rich_text'][0]['text']['content']
                    texts.append(text)
                except (KeyError, IndexError):
                    continue

        return "\n".join(texts)

    @handle_exceptions(
        {
            ValidationError: (400, "Invalid page ID or URL"),
            NotionAuthenticationError: (401, "Failed to authenticate with Notion"),
            ResourceNotFoundError: (404, "Notion page not found"),
            NotionError: (502, "Error processing Notion content"),
            ExternalServiceError: (502, "Error communicating with Notion API"),
        }
    )
    async def get_page_content(self, page_id_or_url: str) -> NotionPage:
        """
        Retrieve and process all content from a Notion page.

        Args:
            page_id_or_url (str): Notion page ID or URL

        Returns:
            NotionPage: Processed page content

        Raises:
            Various exceptions based on the error type
        """
        page_id = self.extract_page_id(page_id_or_url)
        url = await self.get_page_url(page_id)

        if not url:
            raise ResourceNotFoundError("Notion page", page_id)

        try:
            blocks_response = await self.client.blocks.children.list(block_id=page_id)
            results = blocks_response.get('results', [])

            if not results:
                raise NotionContentError("Page has no content", page_id)

            # Process blocks concurrently
            tasks = [self._process_block(block, url) for block in results]
            processed_blocks = await asyncio.gather(*tasks)

            # Filter out None values
            valid_blocks = [block for block in processed_blocks if block is not None]

            if not valid_blocks:
                raise NotionContentError("No valid blocks found in page", page_id)

            return NotionPage(id=page_id, url=url, blocks=valid_blocks)

        except APIResponseError as e:
            if e.status == 401:
                raise NotionAuthenticationError()
            elif e.status == 404:
                raise ResourceNotFoundError("Notion page", page_id)
            else:
                raise ExternalServiceError("Notion", str(e), {"status": e.status})
        except Exception as e:
            raise NotionError(str(e), {"page_id": page_id})
