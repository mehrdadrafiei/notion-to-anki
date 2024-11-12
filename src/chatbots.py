import re

from groq import Groq
from mistralai import Mistral

from config import settings
from error_handling import handle_errors


class ChatBot:
    def get_summary(self, prompt: str, model: str = "llama-3.1-8b-instant") -> str:
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
        self.client = Groq(api_key=settings.groq_api_key)

    @handle_errors(default_return_value="Summary unavailable", message="GroqChatBot failed to summarize")
    def get_summary(self, prompt: str, model: str = "llama-3.1-8b-instant") -> str:
        summary = self.client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=model,
        )
        return self.process_response(summary)


class MistralChatBot(ChatBot):
    def __init__(self):
        super().__init__()
        self.client = Mistral(api_key=settings.mistral_api_key)

    @handle_errors(default_return_value="Summary unavailable", message="MistralChatBot failed to summarize")
    def get_summary(self, prompt: str, model: str = "mistral-large-latest") -> str:
        summary = self.client.chat.complete(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return self.process_response(summary)


def chatbot_factory(chatbot_type: str) -> ChatBot:
    if chatbot_type == "groq":
        return GroqChatBot()
    elif chatbot_type == "mistral":
        return MistralChatBot()
    else:
        raise ValueError("Unsupported chatbot type")
