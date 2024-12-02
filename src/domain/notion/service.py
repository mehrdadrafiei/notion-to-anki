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
from src.domain.flashcard.config import FlashcardGenerationConfig

from .models import BlockType, NotionBlock, NotionPage

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

    def get_flashcard_included_blocks(self, config: FlashcardGenerationConfig) -> List[BlockType]:
        """
        Returns a list of BlockType objects that should be included in the generated flashcards.
        """
        block_list = []

        if config.include_bullets:
            block_list.append("bulleted_list_item")
        if config.include_toggles:
            block_list.append("toggle")

        return block_list

    async def get_page_content(self, page_id_or_url: str, config: FlashcardGenerationConfig) -> NotionPage:
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
        included_blocks = self.get_flashcard_included_blocks(config)

        if not url:
            raise ResourceNotFoundError("Notion page", page_id)

        try:
            # Get root blocks
            response = await self.client.blocks.children.list(page_id)
            root_blocks = response.get('results', [])

            if not root_blocks:
                raise NotionContentError("Page has no content", page_id)

            processed_blocks = []

            # Process each root block
            for block in root_blocks:
                if block.get('has_children'):
                    # Get the text from the root block
                    block_type = block['type']
                    if block_type not in included_blocks:
                        continue

                    front_text = NotionBlock._extract_rich_text(block[block_type].get('rich_text', []))

                    # Get all nested blocks
                    nested_content = await self._get_nested_content(block['id'])

                    if processed_block := NotionBlock(
                        type=BlockType.PARAGRAPH,
                        text=front_text,
                        url=f"{url}#{block['id'].replace('-', '')}",
                        nested_text=nested_content,
                    ):
                        processed_blocks.append(processed_block)

            if not processed_blocks:
                raise NotionContentError("No valid blocks found in page", page_id)

            return NotionPage(id=page_id, url=url, blocks=processed_blocks)

        except APIResponseError as e:
            if e.status == 401:
                raise NotionAuthenticationError()
            elif e.status == 404:
                raise ResourceNotFoundError("Notion page", page_id)
            else:
                raise ExternalServiceError("Notion", str(e), {"status": e.status})
        except Exception as e:
            raise NotionError(str(e), {"page_id": page_id})

    async def _get_nested_content(self, block_id: str) -> str:
        """
        Get all nested content for a block and format it as markdown.
        """
        try:
            response = await self.client.blocks.children.list(block_id)
            blocks = response.get('results', [])

            content_parts = []
            numbered_list_count = 1

            for block in blocks:
                block_type = block['type']

                # Extract text based on block type
                if block_type == 'bulleted_list_item':
                    text = NotionBlock._extract_rich_text(block['bulleted_list_item'].get('rich_text', []))
                    content_parts.append(f"* {text}")

                elif block_type == 'numbered_list_item':
                    text = NotionBlock._extract_rich_text(block['numbered_list_item'].get('rich_text', []))
                    content_parts.append(
                        f"{numbered_list_count}. {text}"
                    )  # Markdown will handle numbering automatically
                    numbered_list_count += 1

                elif block_type == 'paragraph':
                    text = NotionBlock._extract_rich_text(block['paragraph'].get('rich_text', []))
                    content_parts.append(text)

                elif block_type == 'code':
                    text = NotionBlock._extract_rich_text(block['code'].get('rich_text', []))
                    language = block['code'].get('language', '')
                    content_parts.append(f"```{language}\n{text}\n```")

                # If this nested block has its own children, get them too
                if block.get('has_children'):
                    nested_text = await self._get_nested_content(block['id'])
                    if nested_text:
                        content_parts.append(nested_text)

            return '\n'.join(content_parts)

        except Exception as e:
            logger.error(f"Error getting nested content for block {block_id}: {str(e)}")
            return ""
