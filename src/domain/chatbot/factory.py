from typing import Dict, Type

from src.core.error_handling import handle_exceptions
from src.core.exceptions.base import ValidationError
from src.core.exceptions.domain import ChatBotError

from .base import ChatBot
from .providers.groq import GroqChatBot
from .providers.mistral import MistralChatBot


class ChatBotFactory:
    """Factory class for creating chatbot instances."""

    _chatbots: Dict[str, Type[ChatBot]] = {'groq': GroqChatBot, 'mistral': MistralChatBot}

    @classmethod
    @handle_exceptions(
        {ValidationError: (400, "Invalid chatbot type"), ChatBotError: (500, "Failed to create chatbot")}
    )
    async def create(cls, chatbot_type: str) -> ChatBot:
        """
        Create and initialize a chatbot instance.

        Args:
            chatbot_type: The type of chatbot to create

        Returns:
            An initialized chatbot instance

        Raises:
            ValidationError: If the chatbot type is invalid
            ChatBotError: If initialization fails
        """
        if not chatbot_type:
            raise ValidationError("Chatbot type must be specified", "chatbot_type")

        chatbot_class = cls._chatbots.get(chatbot_type.lower())
        if not chatbot_class:
            raise ValidationError(
                f"Unsupported chatbot type: {chatbot_type}",
                "chatbot_type",
                {"available_types": list(cls._chatbots.keys())},
            )

        try:
            chatbot = chatbot_class()
            await chatbot.initialize()
            return chatbot
        except Exception as e:
            raise ChatBotError(f"Failed to initialize {chatbot_type} chatbot", chatbot_type, {"error": str(e)})

    @classmethod
    def register_chatbot(cls, name: str, chatbot_class: Type[ChatBot]) -> None:
        """
        Register a new chatbot type.

        Args:
            name: The name to register the chatbot under
            chatbot_class: The chatbot class to register

        Raises:
            ValidationError: If the name is invalid or already registered
        """
        if not name:
            raise ValidationError("Chatbot name must be specified", "name")

        if name.lower() in cls._chatbots:
            raise ValidationError(
                f"Chatbot type {name} is already registered", "name", {"existing_types": list(cls._chatbots.keys())}
            )

        cls._chatbots[name.lower()] = chatbot_class

    @classmethod
    def get_available_chatbots(cls) -> list[str]:
        """Get a list of all available chatbot types."""
        return list(cls._chatbots.keys())
