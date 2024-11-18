from typing import Dict, Type

from .base import ChatBot
from .exceptions import ChatBotNotFoundError
from .providers.groq import GroqChatBot
from .providers.mistral import MistralChatBot


class ChatBotFactory:
    """Factory class for creating chatbot instances"""

    _chatbots: Dict[str, Type[ChatBot]] = {'groq': GroqChatBot, 'mistral': MistralChatBot}

    @classmethod
    async def create(cls, chatbot_type: str) -> ChatBot:
        """
        Create and initialize a chatbot instance

        Args:
            chatbot_type: The type of chatbot to create

        Returns:
            An initialized chatbot instance

        Raises:
            ChatBotNotFoundError: If the requested chatbot type is not supported
        """
        chatbot_class = cls._chatbots.get(chatbot_type.lower())
        if not chatbot_class:
            raise ChatBotNotFoundError(
                f"Unsupported chatbot type: {chatbot_type}. " f"Available types: {list(cls._chatbots.keys())}"
            )

        chatbot = chatbot_class()
        await chatbot.initialize()
        return chatbot

    @classmethod
    def register_chatbot(cls, name: str, chatbot_class: Type[ChatBot]) -> None:
        """
        Register a new chatbot type

        Args:
            name: The name to register the chatbot under
            chatbot_class: The chatbot class to register
        """
        cls._chatbots[name.lower()] = chatbot_class

    @classmethod
    def get_available_chatbots(cls) -> list[str]:
        """Get a list of all available chatbot types"""
        return list(cls._chatbots.keys())
