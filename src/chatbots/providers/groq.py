from typing import Optional

from groq import AsyncGroq

from config import settings

from ..base import ChatBot, handle_errors


class GroqChatBot(ChatBot):
    def __init__(self):
        self.client: Optional[AsyncGroq] = None
        self.default_model = "llama-3.1-8b-instant"

    async def initialize(self) -> None:
        self.client = AsyncGroq(api_key=settings.groq_api_key)

    @handle_errors(message="GroqChatBot failed to summarize")
    async def get_summary(self, prompt: str, model: Optional[str] = None) -> str:
        if not self.client:
            await self.initialize()

        summary = await self.client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=model or self.default_model,
        )
        return await self.process_response(summary)

    async def cleanup(self) -> None:
        if self.client:
            await self.client.close()
            self.client = None
