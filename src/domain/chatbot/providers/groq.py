from typing import Optional

from groq import AsyncGroq
from httpx import HTTPError

from src.core.config import settings
from src.core.error_handling import handle_exceptions
from src.core.exceptions.domain import ChatBotError

from ..base import ChatBot


class GroqChatBot(ChatBot):
    """Groq API implementation of ChatBot."""

    def __init__(self):
        super().__init__()
        self.default_model = "llama-3.1-8b-instant"

    async def initialize(self) -> None:
        """Initialize Groq client."""
        try:
            self.client = AsyncGroq(api_key=settings.groq_api_key)
        except Exception as e:
            raise ChatBotError("Failed to initialize Groq client", "groq", {"error": str(e)})

    @handle_exceptions({ChatBotError: (500, "Groq API error"), ValueError: (400, "Invalid input")})
    async def get_summary(self, prompt: str, model: Optional[str] = None) -> str:
        """Generate a summary using Groq API."""
        await self.ensure_initialized()
        self.validate_prompt(prompt)

        try:
            summary = await self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=model or self.default_model,
                temperature=0.7,
                max_tokens=500,
            )
            return await self.process_response(summary)

        except HTTPError as e:
            # Handle HTTP-specific errors
            raise ChatBotError(
                "Groq API request failed",
                "groq",
                {
                    "status_code": getattr(e.response, 'status_code', None),
                    "error": str(e),
                    "model": model or self.default_model,
                },
            )
        except ValueError as e:
            # Handle API validation errors
            raise ChatBotError(
                "Invalid request to Groq API", "groq", {"error": str(e), "model": model or self.default_model}
            )
        except Exception as e:
            raise ChatBotError("Unexpected error in Groq request", "groq", {"error": str(e)})

    async def cleanup(self) -> None:
        """Cleanup Groq client resources."""
        if self.client:
            await self.client.close()
            self.client = None
            self.is_initialized = False
