import asyncio
from typing import Optional

from mistralai import Mistral

from src.core.config import settings
from src.core.error_handling import handle_exceptions
from src.core.exceptions.domain import ChatBotError

from ..base import ChatBot


class MistralChatBot(ChatBot):
    """Mistral API implementation of ChatBot."""

    def __init__(self):
        super().__init__()
        self.default_model = "mistral-large-latest"

    async def initialize(self) -> None:
        """Initialize Mistral client."""
        try:
            self.client = Mistral(api_key=settings.mistral_api_key)
        except Exception as e:
            raise ChatBotError("Failed to initialize Mistral client", "mistral", {"error": str(e)})

    @handle_exceptions({ChatBotError: (500, "Mistral API error"), ValueError: (400, "Invalid input")})
    async def get_summary(self, prompt: str, model: Optional[str] = None) -> str:
        """Generate a summary using Mistral API."""
        if not self.client:
            await self.initialize()

        self.validate_prompt(prompt)

        try:
            # Simple retry logic for rate limits
            for attempt in range(3):  # Try up to 3 times
                try:
                    response = await self.client.chat.complete_async(
                        model=model or self.default_model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.7,
                        max_tokens=500,
                    )

                    processed_response = await self.process_response(response)
                    if processed_response:
                        return processed_response
                    raise ChatBotError("Empty response from Mistral", "mistral", {"response": str(response)})

                except Exception as e:
                    if "rate limit" in str(e).lower() and attempt < 2:
                        await asyncio.sleep(2**attempt)  # Simple exponential backoff
                        continue
                    raise

        except Exception as e:
            raise ChatBotError(str(e), "mistral", {"error": str(e), "model": model or self.default_model})

    async def cleanup(self) -> None:
        """Cleanup Mistral client resources."""
        if hasattr(self.client, 'aclose'):
            await self.client.aclose()
        self.client = None
