from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional, final


@final
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
    TOGGLE = auto()

    @classmethod
    def is_heading(cls, block_type: 'BlockType') -> bool:
        """Check if the block type is a heading."""
        return block_type in {cls.HEADING_1, cls.HEADING_2, cls.HEADING_3}


@dataclass(frozen=True)
class RichTextContent:
    """Represents rich text content with its annotations."""

    text: str
    is_bold: bool = False
    is_italic: bool = False
    is_code: bool = False
    href: Optional[str] = None

    def to_markdown(self) -> str:
        """Convert rich text to markdown format."""
        result = self.text
        if self.is_bold:
            result = f"**{result}**"
        if self.is_italic:
            result = f"*{result}*"
        if self.is_code:
            result = f"`{result}`"
        if self.href:
            result = f"[{result}]({self.href})"
        return result


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
        if self._is_question_format():
            return self._create_question_flashcard()
        return self._create_standard_flashcard()

    def _is_question_format(self) -> bool:
        """Check if the text is in question format."""
        return self.text.strip().startswith("**Q.")

    def _create_question_flashcard(self) -> Dict[str, str]:
        """Create a flashcard from question format."""
        front = self.text.replace("**Q.", "").replace("**", "").strip()
        return {"front": front, "back": self.nested_text or "", "url": self.url}

    def _create_standard_flashcard(self) -> Dict[str, str]:
        """Create a standard format flashcard."""
        return {"front": self.text, "back": self.nested_text or "", "url": self.url}

    @staticmethod
    def _extract_rich_text(rich_text_list: List[Dict]) -> str:
        """Extract text content from Notion's rich text format."""
        text_contents = [
            RichTextContent(
                text=text_obj.get('text', {}).get('content', ''),
                is_bold=text_obj.get('annotations', {}).get('bold', False),
                is_italic=text_obj.get('annotations', {}).get('italic', False),
                is_code=text_obj.get('annotations', {}).get('code', False),
                href=text_obj.get('href'),
            ).to_markdown()
            for text_obj in rich_text_list
        ]
        return ''.join(text_contents)

    @classmethod
    def from_block_data(cls, block: Dict, base_url: str, nested_text: Optional[str] = None) -> Optional['NotionBlock']:
        """Create NotionBlock from Notion API block data.

        Args:
            block: Raw block data from Notion API
            base_url: Base URL of the Notion page
            nested_text: Nested content text

        Returns:
            Parsed Notion block or None if unsupported
        """
        block_type = block.get('type')
        if not block_type:
            return None

        block_id = block['id'].replace("-", "")
        url = f"{base_url}#{block_id}"

        block_handlers = {
            'heading': cls._create_heading_block,
            'bulleted_list_item': cls._create_bulleted_list_block,
            'numbered_list_item': cls._create_numbered_list_block,
            'paragraph': cls._create_paragraph_block,
            'code': cls._create_code_block,
        }

        for block_prefix, handler in block_handlers.items():
            if block_type.startswith(block_prefix):
                return handler(block, url, block_type, nested_text)

        return None

    @classmethod
    def _create_heading_block(cls, block: Dict, url: str, block_type: str, _: Optional[str]) -> 'NotionBlock':
        text = cls._extract_rich_text(block[block_type].get('rich_text', []))
        return cls(type=BlockType[block_type.upper().replace('heading_', 'HEADING_')], text=text, url=url)

    @classmethod
    def _create_bulleted_list_block(
        cls, block: Dict, url: str, block_type: str, nested_text: Optional[str]
    ) -> 'NotionBlock':
        text = cls._extract_rich_text(block[block_type].get('rich_text', []))
        return cls(type=BlockType.BULLETED_LIST_ITEM, text=text, url=url, nested_text=nested_text)

    @classmethod
    def _create_numbered_list_block(
        cls, block: Dict, url: str, block_type: str, nested_text: Optional[str]
    ) -> 'NotionBlock':
        text = cls._extract_rich_text(block[block_type].get('rich_text', []))
        return cls(type=BlockType.NUMBERED_LIST_ITEM, text=text, url=url, nested_text=nested_text)

    @classmethod
    def _create_paragraph_block(
        cls, block: Dict, url: str, block_type: str, nested_text: Optional[str]
    ) -> 'NotionBlock':
        text = cls._extract_rich_text(block[block_type].get('rich_text', []))
        return cls(type=BlockType.PARAGRAPH, text=text, url=url, nested_text=nested_text)

    @classmethod
    def _create_code_block(cls, block: Dict, url: str, block_type: str, _: Optional[str]) -> 'NotionBlock':
        text = cls._extract_rich_text(block[block_type].get('rich_text', []))
        return cls(
            type=BlockType.CODE, text=text, url=url, code_content=text, language=block[block_type].get('language', '')
        )


@dataclass(frozen=True)
class NotionPage:
    """Domain model representing a Notion page."""

    id: str
    url: Optional[str]
    blocks: List[NotionBlock]

    @property
    def to_flashcard_format(self) -> List[Dict[str, str]]:
        """Convert page blocks to flashcard format."""
        return [block.to_flashcard_dict for block in self.blocks]
