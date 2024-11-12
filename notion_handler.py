
from typing import List, Dict
from notion_client import Client
from notion_client.errors import APIResponseError, HTTPResponseError
from config import settings
from exceptions import handle_errors

class NotionHandler:
    def get_headings_and_bullets(self) -> List[Dict[str, str]]:
        raise NotImplementedError

class NotionClientHandler(NotionHandler):
    def __init__(self, page_id: str):
        self.client = Client(auth=settings.notion_api_key)
        self.page_id = page_id
        self.url = self._get_page_url()

    @handle_errors(default_return_value=None,exceptions=(APIResponseError, HTTPResponseError), message="Error retrieving page URL")
    def _get_page_url(self):
        page_content = self.client.pages.retrieve(page_id=self.page_id)
        return page_content["url"]

    @handle_errors(default_return_value=[],exceptions=(APIResponseError, HTTPResponseError), message="Error retrieving blocks from Notion")
    def get_headings_and_bullets(self) -> List[Dict[str, str]]:
        blocks = self.client.blocks.children.list(block_id=self.page_id)
        return [
            self._parse_block(block) for block in blocks["results"]
            if block["type"] in ['heading_1', 'heading_2', 'heading_3', 'bulleted_list_item']
        ]

    def _parse_block(self, block):
        block_type = block["type"]
        block_id = block["id"].replace("-", "")

        if block_type in ['heading_1', 'heading_2', 'heading_3']:
            return {
                "type": block_type,
                "text": block[block_type]["text"][0]["text"]["content"],
                "url": f"{self.url}#{block_id}"
            }
        elif block_type == 'bulleted_list_item':
            return {
                "type": 'bullet_point',
                "text": block["bulleted_list_item"]["rich_text"][0]["text"]["content"],
                "url": f"{self.url}#{block_id}"
            }