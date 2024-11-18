from typing import Optional

from mistralai.async_client import MistralAsyncClient
from mistralai.client import MistralClient

from config import settings

from ..base import ChatBot, handle_errors


class MistralChatBot(ChatBot):
    def __init__(self):
        self.client: Optional[MistralAsyncClient] = None
        self.default_model = "mistral-large-latest"

    async def initialize(self) -> None:
        self.client = MistralAsyncClient(api_key=settings.mistral_api_key)

    @handle_errors(message="MistralChatBot failed to summarize")
    async def get_summary(self, prompt: str, model: Optional[str] = None) -> str:
        if not self.client:
            await self.initialize()

        summary = await self.client.chat(
            model=model or self.default_model,
            messages=[{"role": "user", "content": prompt}],
        )
        return self.process_response(summary)

    async def cleanup(self) -> None:
        if self.client:
            await self.client.close()
            self.client = None
