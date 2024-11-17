import re
from typing import Optional

from groq import AsyncGroq
from mistralai import Mistral

from config import settings
from error_handling import handle_errors

CHATBOT_LIST = ["groq", "mistral"]


class ChatBot:
    async def get_summary(self, prompt: str, model: str = "llama-3.1-8b-instant") -> str:
        raise NotImplementedError

    @handle_errors(
        default_return_value=None, exceptions=(AttributeError, IndexError), message="Error processing response"
    )
    def process_response(self, response) -> str:
        """
        A helper method to extract the summary from the API response, which is common to all chatbots.
        """
        content = response.choices[0].message.content
        pattern = r"\[\[(.*?)\]\]"  # Matches the content within [[ ]]
        return re.findall(pattern, content)[0]


class GroqChatBot(ChatBot):
    def __init__(self):
        super().__init__()
        self.client = AsyncGroq(api_key=settings.groq_api_key)

    @handle_errors(default_return_value="Summary unavailable", message="GroqChatBot failed to summarize")
    async def get_summary(self, prompt: str, model: str = "llama-3.1-8b-instant") -> str:
        summary = await self.client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=model,
        )
        return self.process_response(summary)


class MistralChatBot(ChatBot):
    def __init__(self):
        super().__init__()
        self.client = Mistral(api_key=settings.mistral_api_key)

    @handle_errors(default_return_value="Summary unavailable", message="MistralChatBot failed to summarize")
    async def get_summary(self, prompt: str, model: str = "mistral-large-latest") -> str:
        summary = await self.client.chat.complete(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return self.process_response(summary)


def chatbot_factory(chatbot_type: Optional[str]) -> Optional[ChatBot]:
    if chatbot_type:
        match chatbot_type:
            case "groq":
                return GroqChatBot()
            case "mistral":
                return MistralChatBot()
            case _:
                raise ValueError("Unsupported chatbot type")
    else:
        return None
