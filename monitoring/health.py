# monitoring/health.py
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse

from config import settings
from src.chatbots.factory import ChatBotFactory


@dataclass
class ServiceHealth:
    notion_api: bool
    chatbots: Dict[str, bool]


class HealthCheck:
    """Health check service for APIs"""

    def __init__(self):
        self.client = httpx.AsyncClient()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def _check_notion_api(self) -> bool:
        """Check the health of the Notion API."""
        try:
            response = await self.client.get(
                "https://api.notion.com/v1/users/me",
                headers={"Authorization": f"Bearer {settings.notion_api_key}", "Notion-Version": "2022-06-28"},
            )
            return response.status_code == 200
        except Exception:
            return False

    async def _check_chatbots(self) -> Dict[str, bool]:
        """Check the health of all available chatbots."""
        chatbot_health = {}
        for chatbot_type in ChatBotFactory.get_available_chatbots():
            try:
                chatbot = await ChatBotFactory.create(chatbot_type)
                summary = await chatbot.get_summary("Just say hi!")
                chatbot_health[chatbot_type] = summary is not None
                await chatbot.cleanup()
            except Exception:
                chatbot_health[chatbot_type] = False
        return chatbot_health

    async def check_services(self) -> Dict[str, Any]:
        """Perform health checks for all services."""
        health_status = {
            "notion_api": await self._check_notion_api(),
            "chatbots": await self._check_chatbots(),
        }
        return ServiceHealth(**health_status).__dict__

    async def get_health(self, request: Request):
        """Endpoint to return the health status of all services."""
        health_check = await self.check_services()
        status = "healthy" if all(health_check.values()) else "unhealthy"
        return JSONResponse(
            content={"status": status, "services": health_check}, status_code=200 if status == "healthy" else 503
        )
