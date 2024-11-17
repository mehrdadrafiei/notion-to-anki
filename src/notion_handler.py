import asyncio
from typing import Dict, List

from notion_client import AsyncClient
from notion_client.errors import APIResponseError, HTTPResponseError

from config import settings
from error_handling import handle_errors


class NotionHandler:
    async def get_headings_and_bullets(self) -> List[Dict[str, str]]:
        raise NotImplementedError


class NotionClientHandler(NotionHandler):
    def __init__(self, page_id: str):
        self.client = AsyncClient(auth=settings.notion_api_key)
        self.page_id = page_id
        self.url = None

    async def initialize(self):
        self.url = await self._get_page_url()

    @handle_errors(
        default_return_value=None,
        exceptions=(APIResponseError, HTTPResponseError),
        message="Error retrieving blocks from Notion",
    )
    async def _get_page_url(self):
        page_content = await self.client.pages.retrieve(page_id=self.page_id)
        return page_content["url"]

    @handle_errors(
        default_return_value=[],
        exceptions=(APIResponseError, HTTPResponseError),
        message="Error retrieving blocks from Notion",
    )
    async def get_headings_and_bullets(self) -> List[Dict[str, str]]:
        # Retrieve the top-level blocks
        blocks = await self.client.blocks.children.list(block_id=self.page_id)
        results = blocks["results"]

        async def fetch_nested_blocks(block):
            # Check if the block has children
            if block["has_children"]:
                nested_blocks = await self.client.blocks.children.list(block_id=block["id"])
                # Combine all child content into one text
                nested_text = " ".join(
                    child_block[child_block["type"]]["rich_text"][0]["text"]["content"]
                    for child_block in nested_blocks["results"]
                    if "rich_text" in child_block.get(child_block["type"], {})
                )
                return self._parse_block(block, nested_text=nested_text)
            else:
                return self._parse_block(block)

        # Create tasks for fetching nested blocks
        tasks = [fetch_nested_blocks(block) for block in results]

        # Flatten and run the tasks asynchronously
        parsed_blocks = await asyncio.gather(*tasks)
        return [block for block in parsed_blocks if block]

    def _parse_block(self, block, nested_text="") -> Dict[str, str]:
        block_type = block["type"]
        block_id = block["id"].replace("-", "")

        if block_type in ["heading_1", "heading_2", "heading_3"]:
            return {
                "type": block_type,
                "text": block[block_type]["text"][0]["text"]["content"],
                "url": f"{self.url}#{block_id}",
            }
        elif block_type == "bulleted_list_item":
            return {
                "type": "bullet_point",
                "front": block["bulleted_list_item"]["rich_text"][0]["text"]["content"],
                "back": nested_text,  # Include nested text for bullet points
                "url": f"{self.url}#{block_id}",
            }

    def _extract_nested_text(self, children: List[Dict]) -> str:
        """
        Extract all text from a list of child blocks into a single string.
        """
        texts = []
        for child in children:
            block_type = child["type"]
            if block_type in ["paragraph", "bulleted_list_item", "heading_1", "heading_2", "heading_3"]:
                texts.append(child[block_type]["rich_text"][0]["text"]["content"])
        return "\n".join(texts)


async def notion_handler_factory(page_id: str) -> NotionHandler:
    return NotionClientHandler(page_id)
