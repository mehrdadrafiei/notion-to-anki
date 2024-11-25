from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional

from notion_client import AsyncClient
from notion_client.errors import APIResponseError, HTTPResponseError

from config import settings

from .error_handling import handle_errors_decorator


class BlockType(Enum):
    """Enumeration of supported Notion block types."""

    HEADING_1 = auto()
    HEADING_2 = auto()
    HEADING_3 = auto()
    BULLETED_LIST_ITEM = auto()
    PARAGRAPH = auto()


@dataclass
class NotionBlock:
    """Represents a parsed Notion block with structured information."""

    type: BlockType
    text: str
    url: str
    nested_text: Optional[str] = None

    @classmethod
    def from_block_data(cls, block: Dict, base_url: str, nested_text: Optional[str] = None) -> Optional[NotionBlock]:
        """
        Factory method to create NotionBlock from Notion API block data.

        Args:
            block (Dict): Raw block data from Notion API
            base_url (str): Base URL of the Notion page
            nested_text (Optional[str], optional): Nested content text. Defaults to None.

        Returns:
            Optional[NotionBlock]: Parsed Notion block or None if unsupported
        """
        block_type = block['type']
        block_id = block['id'].replace("-", "")

        try:
            if block_type in ['heading_1', 'heading_2', 'heading_3']:
                return cls(
                    type=BlockType[block_type.upper().replace('HEADING_', '')],
                    text=block[block_type]['text'][0]['text']['content'],
                    url=f"{base_url}#{block_id}",
                )

            elif block_type == 'bulleted_list_item':
                return cls(
                    type=BlockType.BULLETED_LIST_ITEM,
                    text=block['bulleted_list_item']['rich_text'][0]['text']['content'],
                    url=f"{base_url}#{block_id}",
                    nested_text=nested_text,
                )

            return None

        except (KeyError, IndexError) as e:
            # Log the error or handle it appropriately
            print(f"Error parsing block: {e}")
            return None


class NotionHandler:
    """Abstract base class for Notion content retrieval."""

    async def get_headings_and_bullets(self) -> List[Dict[str, str]]:
        """
        Retrieve headings and bullet points from a Notion page.

        Raises:
            NotImplementedError: This method must be implemented by subclasses.
        """
        raise NotImplementedError("Subclass must implement abstract method")


class NotionClientHandler(NotionHandler):
    """Concrete implementation of Notion content retrieval using Notion API."""

    def __init__(self, page_id_or_url: str):
        """
        Initialize NotionClientHandler.

        Args:
            page_id (str): Unique identifier for the Notion page
        """
        self.client = AsyncClient(auth=settings.notion_api_key)
        self.page_id = self._extract_page_id(page_id_or_url)
        self.url: Optional[str] = None

    async def initialize(self) -> None:
        """
        Initialize the handler by retrieving the page URL.
        """
        if not self.url:
            self.url = await self._get_page_url()

    @staticmethod
    def _extract_page_id(page_id_or_url: str) -> str:
        """
        Extract the page ID from a Notion page URL or return the input if it's already a page ID.

        Args:
            page_id_or_url (str): Notion page ID or URL

        Returns:
            str: Extracted page ID
        """
        if page_id_or_url.startswith("https://www.notion.so/") or page_id_or_url.startswith("https://notion.so/"):
            match = re.search(r"[a-f0-9]{32}", page_id_or_url)
            if match:
                return match.group()
        return page_id_or_url

    @handle_errors_decorator(
        default_return_value=None,
        exceptions=(APIResponseError, HTTPResponseError),
        message="Error retrieving page URL from Notion",
    )
    async def _get_page_url(self) -> Optional[str]:
        """
        Retrieve the URL of the Notion page.

        Returns:
            Optional[str]: The URL of the page or None if retrieval fails
        """
        page_content = await self.client.pages.retrieve(page_id=self.page_id)
        return page_content.get("url")

    @handle_errors_decorator(
        default_return_value=[],
        exceptions=(APIResponseError, HTTPResponseError),
        message="Error retrieving blocks from Notion",
    )
    async def get_headings_and_bullets(self) -> List[Dict[str, str]]:
        """
        Retrieve headings and bullet points from a Notion page.

        Returns:
            List[Dict[str, str]]: Parsed headings and bullet points
        """
        if not self.url:
            await self.initialize()

        # Retrieve top-level blocks
        blocks_response = await self.client.blocks.children.list(block_id=self.page_id)
        results = blocks_response.get('results', [])

        async def process_block(block) -> Optional[Dict[str, str]]:
            """
            Process a single block, including nested content.

            Args:
                block (Dict): Notion block to process

            Returns:
                Optional[Dict[str, str]]: Processed block data
            """
            # Fetch nested blocks if available
            nested_text = ""
            if block.get('has_children', False):
                nested_blocks = await self.client.blocks.children.list(block_id=block['id'])
                nested_text = self._extract_nested_text(nested_blocks.get('results', []))

            # Parse the block
            parsed_block = NotionBlock.from_block_data(block, base_url=self.url or "", nested_text=nested_text)

            # Convert parsed block to dictionary format
            if parsed_block and parsed_block.type in [
                BlockType.HEADING_1,
                BlockType.HEADING_2,
                BlockType.HEADING_3,
                BlockType.BULLETED_LIST_ITEM,
            ]:
                return {
                    "front": parsed_block.text,
                    "back": parsed_block.nested_text or parsed_block.text,
                    "url": parsed_block.url,
                }

            return None

        # Process blocks concurrently
        tasks = [process_block(block) for block in results]
        processed_blocks = await asyncio.gather(*tasks)

        # Filter out None values
        return [block for block in processed_blocks if block]

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
                    # Silently skip blocks without text
                    continue

        return "\n".join(texts)


async def notion_handler_factory(page_id: str) -> NotionHandler:
    """
    Factory function to create a NotionHandler instance.

    Args:
        page_id (str): Unique identifier for the Notion page

    Returns:
        NotionHandler: Configured Notion handler
    """
    handler = NotionClientHandler(page_id)
    await handler.initialize()
    return handler
