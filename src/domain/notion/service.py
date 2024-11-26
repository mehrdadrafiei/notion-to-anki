import asyncio
import logging
import re
from typing import Dict, List, Optional

from notion_client import AsyncClient
from notion_client.errors import APIResponseError, HTTPResponseError

from src.common.error_handling import handle_errors_decorator
from src.core.config import settings

from .exceptions import NotionServiceError
from .models import NotionBlock, NotionPage

logger = logging.getLogger(__name__)


class NotionService:
    """Service class for interacting with Notion API."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize NotionService with API key."""
        self.client = AsyncClient(auth=api_key or settings.notion_api_key)
        self._url_cache: Dict[str, str] = {}

    @staticmethod
    def extract_page_id(page_id_or_url: str) -> str:
        """
        Extract the page ID from a Notion page URL or return the input if it's already a page ID.

        Args:
            page_id_or_url (str): Notion page ID or URL

        Returns:
            str: Extracted page ID
        """
        if page_id_or_url.startswith(("https://www.notion.so/", "https://notion.so/")):
            match = re.search(r"[a-f0-9]{32}", page_id_or_url)
            if match:
                return match.group()
        return page_id_or_url

    @handle_errors_decorator(
        default_return_value=None,
        exceptions=(APIResponseError, HTTPResponseError),
        message="Error retrieving page URL from Notion",
    )
    async def get_page_url(self, page_id: str) -> Optional[str]:
        """
        Retrieve the URL of the Notion page.

        Args:
            page_id (str): Notion page ID

        Returns:
            Optional[str]: The URL of the page or None if retrieval fails
        """
        if page_id in self._url_cache:
            return self._url_cache[page_id]

        page_content = await self.client.pages.retrieve(page_id=page_id)
        url = page_content.get("url")
        if url:
            self._url_cache[page_id] = url
        return url

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

    async def _process_block(self, block: Dict, base_url: str) -> Optional[NotionBlock]:
        """
        Process a single block, including nested content.

        Args:
            block (Dict): Notion block to process
            base_url (str): Base URL of the page

        Returns:
            Optional[NotionBlock]: Processed block
        """
        nested_text = ""
        if block.get('has_children', False):
            nested_blocks = await self.client.blocks.children.list(block_id=block['id'])
            nested_text = self._extract_nested_text(nested_blocks.get('results', []))

        return NotionBlock.from_block_data(block, base_url=base_url, nested_text=nested_text)

    @handle_errors_decorator(
        default_return_value=[],
        exceptions=(APIResponseError, HTTPResponseError),
        message="Error retrieving blocks from Notion",
    )
    async def get_page_content(self, page_id_or_url: str) -> NotionPage:
        """
        Retrieve and process all content from a Notion page.

        Args:
            page_id_or_url (str): Notion page ID or URL

        Returns:
            NotionPage: Processed page content

        Raises:
            NotionServiceError: If page content cannot be retrieved
        """
        page_id = self.extract_page_id(page_id_or_url)
        url = await self.get_page_url(page_id)

        if not url:
            raise NotionServiceError(f"Could not retrieve URL for page {page_id}")

        blocks_response = await self.client.blocks.children.list(block_id=page_id)
        results = blocks_response.get('results', [])

        # Process blocks concurrently
        tasks = [self._process_block(block, url) for block in results]
        processed_blocks = await asyncio.gather(*tasks)

        # Filter out None values
        valid_blocks = [block for block in processed_blocks if block is not None]

        return NotionPage(id=page_id, url=url, blocks=valid_blocks)

    async def get_flashcards(self, page_id_or_url: str) -> List[Dict[str, str]]:
        """
        Get page content in flashcard format.

        Args:
            page_id_or_url (str): Notion page ID or URL

        Returns:
            List[Dict[str, str]]: List of flashcard dictionaries
        """
        page = await self.get_page_content(page_id_or_url)
        return page.to_flashcard_format
