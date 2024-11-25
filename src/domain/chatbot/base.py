import logging
import re
from abc import ABC, abstractmethod
from functools import wraps
from typing import Optional

logger = logging.getLogger(__name__)


def handle_errors(
    default_return_value: Optional[str] = None,
    exceptions: tuple = (Exception,),
    message: str = "Error in chatbot operation",
):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except exceptions as e:
                logger.error(f"{message}: {str(e)}")
                return default_return_value

        return wrapper

    return decorator


class ChatBot(ABC):
    """Abstract base class for all chatbot implementations"""

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

    @handle_errors(exceptions=(AttributeError, IndexError), message="Error processing response")
    async def process_response(self, response) -> Optional[str]:
        """
        Process the API response, returning None if the summary is invalid or empty.
        """
        if not response or not hasattr(response, 'choices'):
            return None

        content = response.choices[0].message.content
        if not content:
            return None

        pattern = r"\[\[(.*?)\]\]"  # Matches the content within [[ ]]
        find_match = re.findall(pattern, content)

        if find_match:
            summary = find_match[0].strip()
            return summary if summary else None
        else:
            # If no brackets found, use the whole content if it's not empty
            content = content.strip()
            return content if content else None

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
