from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional


class BlockType(Enum):
    """Enumeration of supported Notion block types."""

    HEADING_1 = auto()
    HEADING_2 = auto()
    HEADING_3 = auto()
    BULLETED_LIST_ITEM = auto()
    NUMBERED_LIST_ITEM = auto()
    PARAGRAPH = auto()
    CODE = auto()
    QUOTE = auto()

    @classmethod
    def is_heading(cls, block_type: 'BlockType') -> bool:
        """Check if the block type is a heading."""
        return block_type in {cls.HEADING_1, cls.HEADING_2, cls.HEADING_3}


@dataclass
class NotionBlock:
    """Domain model representing a Notion block with structured information."""

    type: BlockType
    text: str
    url: str
    nested_text: Optional[str] = None
    code_content: Optional[str] = None
    language: Optional[str] = None

    @property
    def is_heading(self) -> bool:
        """Check if the block is a heading."""
        return BlockType.is_heading(self.type)

    @property
    def to_flashcard_dict(self) -> Dict[str, str]:
        """Convert block to flashcard dictionary format."""
        if self.text.strip().startswith("**Q."):
            front = self.text.replace("**Q.", "").replace("**", "").strip()
            back = self.nested_text or ""
            return {"front": front, "back": back, "url": self.url}
        return {"front": self.text, "back": self.nested_text or "", "url": self.url}

    @staticmethod
    def _extract_rich_text(rich_text_list: List[Dict]) -> str:
        """Extract text content from Notion's rich text format."""
        text_parts = []
        for text_obj in rich_text_list:
            text = text_obj.get('text', {}).get('content', '')
            annotations = text_obj.get('annotations', {})

            if annotations.get('bold'):
                text = f"**{text}**"
            if annotations.get('italic'):
                text = f"*{text}*"
            if annotations.get('code'):
                text = f"`{text}`"
            if text_obj.get('href'):
                text = f"[{text}]({text_obj['href']})"

            text_parts.append(text)
        return ''.join(text_parts)

    @classmethod
    def from_block_data(cls, block: Dict, base_url: str, nested_text: Optional[str] = None) -> Optional['NotionBlock']:
        """
        Factory method to create NotionBlock from Notion API block data.

        Args:
            block (Dict): Raw block data from Notion API
            base_url (str): Base URL of the Notion page
            nested_text (Optional[str]): Nested content text

        Returns:
            Optional[NotionBlock]: Parsed Notion block or None if unsupported
        """
        block_type = block['type']
        block_id = block['id'].replace("-", "")

        try:
            if block_type in ['heading_1', 'heading_2', 'heading_3']:
                text = cls._extract_rich_text(block[block_type].get('rich_text', []))
                return cls(
                    type=BlockType[block_type.upper().replace('heading_', 'HEADING_')],
                    text=text,
                    url=f"{base_url}#{block_id}",
                )
            elif block_type == 'bulleted_list_item':
                text = cls._extract_rich_text(block['bulleted_list_item'].get('rich_text', []))
                return cls(
                    type=BlockType.BULLETED_LIST_ITEM,
                    text=text,
                    url=f"{base_url}#{block_id}",
                    nested_text=nested_text,
                )
            elif block_type == 'numbered_list_item':
                text = cls._extract_rich_text(block['numbered_list_item'].get('rich_text', []))
                return cls(
                    type=BlockType.NUMBERED_LIST_ITEM,
                    text=text,
                    url=f"{base_url}#{block_id}",
                    nested_text=nested_text,
                )
            elif block_type == 'paragraph':
                text = cls._extract_rich_text(block['paragraph'].get('rich_text', []))
                return cls(
                    type=BlockType.PARAGRAPH,
                    text=text,
                    url=f"{base_url}#{block_id}",
                    nested_text=nested_text,
                )
            elif block_type == 'code':
                text = cls._extract_rich_text(block['code'].get('rich_text', []))
                return cls(
                    type=BlockType.CODE,
                    text=text,
                    url=f"{base_url}#{block_id}",
                    code_content=text,
                    language=block['code'].get('language', ''),
                )
            return None

        except (KeyError, IndexError):
            return None


@dataclass
class NotionPage:
    """Domain model representing a Notion page."""

    id: str
    url: Optional[str]
    blocks: List[NotionBlock]

    @property
    def to_flashcard_format(self) -> List[Dict[str, str]]:
        """Convert page blocks to flashcard format."""
        flashcards = []

        for block in self.blocks:
            flashcards.append(
                {
                    "front": block.text,
                    "back": block.nested_text or "",
                    "url": block.url,
                }
            )

        return flashcards
