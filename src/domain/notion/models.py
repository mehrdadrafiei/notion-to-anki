from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional


class BlockType(Enum):
    """Enumeration of supported Notion block types."""

    HEADING_1 = auto()
    HEADING_2 = auto()
    HEADING_3 = auto()
    BULLETED_LIST_ITEM = auto()
    PARAGRAPH = auto()

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

    @property
    def is_heading(self) -> bool:
        """Check if the block is a heading."""
        return BlockType.is_heading(self.type)

    @property
    def to_flashcard_dict(self) -> Dict[str, str]:
        """Convert block to flashcard dictionary format."""
        return {"front": self.text, "back": self.nested_text or self.text, "url": self.url}

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
                return cls(
                    type=BlockType[block_type.upper().replace('heading_', 'HEADING_')],
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
        return [
            block.to_flashcard_dict
            for block in self.blocks
            if block
            and block.type
            in {BlockType.HEADING_1, BlockType.HEADING_2, BlockType.HEADING_3, BlockType.BULLETED_LIST_ITEM}
        ]
