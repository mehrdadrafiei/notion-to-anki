import asyncio
import logging
import re
from typing import Dict, List, Optional, Set

from notion_client import AsyncClient
from notion_client.errors import APIResponseError

from src.core.config import settings
from src.core.error_handling import handle_service_errors
from src.core.exceptions.base import ExternalServiceError, ResourceNotFoundError, ValidationError
from src.core.exceptions.domain import NotionAuthenticationError, NotionContentError, NotionError
from src.domain.flashcard.config import FlashcardGenerationConfig

from .models import BlockType, NotionBlock, NotionPage

logger = logging.getLogger(__name__)


class NotionService:
    """Service class for interacting with Notion API."""

    URL_PATTERN = re.compile(r"[a-f0-9]{32}")
    PAGE_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
    NOTION_URL_PREFIX = ("https://www.notion.so/", "https://notion.so/")

    def __init__(self, api_key: Optional[str] = None):
        """Initialize NotionService with API key.

        Args:
            api_key: Optional API key override. If not provided, uses settings.

        Raises:
            NotionAuthenticationError: If authentication fails
        """
        try:
            self.client = AsyncClient(auth=api_key or settings.notion_api_key)
            self._url_cache: Dict[str, str] = {}
        except Exception as e:
            raise NotionAuthenticationError() from e

    def extract_page_id(self, page_id_or_url: str) -> str:
        """Extract page ID from a Notion page URL or validate existing page ID.

        Args:
            page_id_or_url: Notion page ID or URL

        Returns:
            Extracted or validated page ID

        Raises:
            ValidationError: If input format is invalid
        """
        if not page_id_or_url:
            raise ValidationError("Page ID or URL cannot be empty", "page_id_or_url")

        if page_id_or_url.startswith(self.NOTION_URL_PREFIX):
            if match := self.URL_PATTERN.search(page_id_or_url):
                return match.group()
            raise ValidationError("Invalid Notion URL format", "page_id_or_url")

        if not self.PAGE_ID_PATTERN.match(page_id_or_url):
            raise ValidationError("Invalid page ID format", "page_id_or_url")

        return page_id_or_url

    @handle_service_errors(default_return_value=None)
    async def get_page_url(self, page_id: str) -> Optional[str]:
        """Retrieve the URL of a Notion page.

        Args:
            page_id: Notion page ID

        Returns:
            Page URL if found, None otherwise

        Raises:
            ExternalServiceError: If API request fails
            NotionError: If URL not found in response
        """
        if url := self._url_cache.get(page_id):
            return url

        try:
            page_content = await self.client.pages.retrieve(page_id=page_id)
            if url := page_content.get("url"):
                self._url_cache[page_id] = url
                return url
            raise NotionError("Page URL not found in response", {"page_id": page_id})
        except APIResponseError as e:
            raise ExternalServiceError("Notion", "Failed to retrieve page URL", {"error": str(e)})

    def get_flashcard_included_blocks(self, config: FlashcardGenerationConfig) -> Set[str]:
        """Get block types to include in flashcard generation.

        Args:
            config: Flashcard generation configuration

        Returns:
            Set of block type identifiers to include
        """
        included_blocks = set()

        if config.include_bullets:
            included_blocks.add("bulleted_list_item")
        if config.include_toggles:
            included_blocks.add("toggle")

        return included_blocks

    async def get_page_content(self, page_id_or_url: str, config: FlashcardGenerationConfig) -> NotionPage:
        """Retrieve and process content from a Notion page.

        Args:
            page_id_or_url: Notion page ID or URL
            config: Flashcard generation configuration

        Returns:
            Processed page content

        Raises:
            ResourceNotFoundError: If page not found
            NotionContentError: If page has no valid content
            NotionAuthenticationError: If authentication fails
            NotionError: For other Notion-related errors
        """
        page_id = self.extract_page_id(page_id_or_url)
        url = await self.get_page_url(page_id)
        included_blocks = self.get_flashcard_included_blocks(config)

        if not url:
            raise ResourceNotFoundError("Notion page", page_id)

        try:
            blocks = await self._get_root_blocks(page_id)
            processed_blocks = await self._process_blocks(blocks, url, included_blocks)

            if not processed_blocks:
                raise NotionContentError("No valid blocks found in page", page_id)

            return NotionPage(id=page_id, url=url, blocks=processed_blocks)

        except APIResponseError as e:
            self._handle_api_error(e, page_id)
        except Exception as e:
            raise NotionError(str(e), {"page_id": page_id})

    async def _get_root_blocks(self, page_id: str) -> List[Dict]:
        """Retrieve root-level blocks from a Notion page.

        Args:
            page_id: Notion page ID

        Returns:
            List of root blocks

        Raises:
            NotionContentError: If page has no content
        """
        response = await self.client.blocks.children.list(page_id)
        blocks = response.get('results', [])

        if not blocks:
            raise NotionContentError("Page has no content", page_id)

        return blocks

    async def _process_blocks(self, blocks: List[Dict], url: str, included_blocks: Set[str]) -> List[NotionBlock]:
        """Process blocks and their nested content.

        Args:
            blocks: List of blocks to process
            url: Base URL for block references
            included_blocks: Set of block types to include

        Returns:
            List of processed NotionBlock objects
        """
        processed_blocks = []

        for block in blocks:
            if not block.get('has_children'):
                continue

            block_type = block['type']
            if block_type not in included_blocks:
                continue

            front_text = NotionBlock._extract_rich_text(block[block_type].get('rich_text', []))
            nested_content = await self._get_nested_content(block['id'])

            if processed_block := NotionBlock(
                type=BlockType.PARAGRAPH,
                text=front_text,
                url=f"{url}#{block['id'].replace('-', '')}",
                nested_text=nested_content,
            ):
                processed_blocks.append(processed_block)

        return processed_blocks

    async def _get_nested_content(self, block_id: str) -> str:
        """Get nested content for a block formatted as markdown.

        Args:
            block_id: Block ID to get nested content for

        Returns:
            Formatted markdown string of nested content
        """
        try:
            blocks = await self._get_child_blocks(block_id)
            return self._format_nested_blocks(blocks)
        except Exception as e:
            logger.error(f"Error getting nested content for block {block_id}: {str(e)}")
            return ""

    async def _get_child_blocks(self, block_id: str) -> List[Dict]:
        """Retrieve child blocks for a given block.

        Args:
            block_id: Parent block ID

        Returns:
            List of child blocks
        """
        response = await self.client.blocks.children.list(block_id)
        return response.get('results', [])

    def _format_nested_blocks(self, blocks: List[Dict]) -> str:
        """Format nested blocks into markdown.

        Args:
            blocks: List of blocks to format

        Returns:
            Formatted markdown string
        """
        content_parts = []
        numbered_list_count = 1

        for block in blocks:
            block_type = block['type']
            formatted_text = self._format_block(block, block_type, numbered_list_count)

            if formatted_text:
                content_parts.append(formatted_text)
                if block_type == 'numbered_list_item':
                    numbered_list_count += 1

            if block.get('has_children'):
                nested_text = asyncio.run(self._get_nested_content(block['id']))
                if nested_text:
                    content_parts.append(nested_text)

        return '\n'.join(content_parts)

    def _format_block(self, block: Dict, block_type: str, list_count: int) -> Optional[str]:
        """Format a single block into markdown.

        Args:
            block: Block to format
            block_type: Type of block
            list_count: Current numbered list counter

        Returns:
            Formatted markdown string or None if block type not supported
        """
        text = NotionBlock._extract_rich_text(block[block_type].get('rich_text', []))

        if not text:
            return None

        format_map = {
            'bulleted_list_item': lambda t: f"* {t}",
            'numbered_list_item': lambda t: f"{list_count}. {t}",
            'paragraph': lambda t: t,
            'code': lambda t: f"```{block['code'].get('language', '')}\n{t}\n```",
        }

        if formatter := format_map.get(block_type):
            return formatter(text)

        return None

    def _handle_api_error(self, error: APIResponseError, page_id: str) -> None:
        """Handle Notion API errors appropriately.

        Args:
            error: API error to handle
            page_id: Related page ID

        Raises:
            NotionAuthenticationError: For authentication errors
            ResourceNotFoundError: For not found errors
            ExternalServiceError: For other API errors
        """
        if error.status == 401:
            raise NotionAuthenticationError()
        elif error.status == 404:
            raise ResourceNotFoundError("Notion page", page_id)
        else:
            raise ExternalServiceError("Notion", str(error), {"status": error.status})
