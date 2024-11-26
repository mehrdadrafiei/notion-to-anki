import logging
import re
from abc import ABC, abstractmethod
from typing import Optional

from src.core.error_handling import handle_exceptions, handle_service_errors
from src.core.exceptions.base import ValidationError
from src.core.exceptions.domain import ChatBotError

logger = logging.getLogger(__name__)


class ChatBot(ABC):
    """Abstract base class for all chatbot implementations"""

    def __init__(self):
        self.client = None
        self.is_initialized = False

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize any necessary clients or resources"""
        pass

    @abstractmethod
    async def get_summary(self, prompt: str, model: Optional[str] = None) -> str:
        """Generate a summary from the given prompt"""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Cleanup any resources"""
        pass

    @handle_service_errors(
        default_return_value=None,
        error_mapping={
            ValueError: "Invalid response format",
            KeyError: "Missing required response fields",
            Exception: "Failed to process response",
        },
    )
    async def process_response(self, response) -> Optional[str]:
        """Process the API response."""
        if not response:
            raise ChatBotError("Empty response received", self.__class__.__name__)

        if not hasattr(response, 'choices'):
            raise ChatBotError("Invalid response format", self.__class__.__name__, {"received": str(type(response))})

        content = response.choices[0].message.content
        if not content:
            raise ChatBotError("Empty content in response", self.__class__.__name__, {"response": str(response)})

        # Extract content within [[ ]]
        pattern = r"\[\[(.*?)\]\]"
        find_match = re.findall(pattern, content)

        if find_match:
            summary = find_match[0].strip()
            if not summary:
                raise ChatBotError("Empty summary in brackets", self.__class__.__name__, {"content": content})
            return summary

        # If no brackets found, use the whole content
        content = content.strip()
        if not content:
            raise ChatBotError("Empty content after processing", self.__class__.__name__, {"original": str(response)})
        return content

    def validate_prompt(self, prompt: str) -> None:
        """Validate the prompt before sending to the API."""
        if not prompt:
            raise ValidationError("Prompt cannot be empty", "prompt")

        if len(prompt) > 4000:  # Adjust this limit based on your needs
            raise ValidationError(
                "Prompt exceeds maximum length", "prompt", {"max_length": 4000, "current_length": len(prompt)}
            )

    async def ensure_initialized(self) -> None:
        """Ensure the chatbot is initialized before use."""
        if not self.is_initialized:
            try:
                await self.initialize()
                self.is_initialized = True
            except Exception as e:
                raise ChatBotError(
                    f"Failed to initialize {self.__class__.__name__}", self.__class__.__name__, {"error": str(e)}
                )

    async def __aenter__(self):
        await self.ensure_initialized()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
