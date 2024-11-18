import logging
import re
from abc import ABC, abstractmethod
from functools import wraps
from typing import Optional

logger = logging.getLogger(__name__)


def handle_errors(
    default_return_value: str = "Summary unavailable",
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

    @handle_errors(
        default_return_value=None, exceptions=(AttributeError, IndexError), message="Error processing response"
    )
    async def process_response(self, response) -> str:
        """
        A helper method to extract the summary from the API response, which is common to all chatbots.
        """
        content = response.choices[0].message.content
        pattern = r"\[\[(.*?)\]\]"  # Matches the content within [[ ]]
        return re.findall(pattern, content)[0]

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
