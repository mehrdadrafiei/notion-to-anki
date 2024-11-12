from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    notion_api_key: str = Field(..., env='NOTION_API_KEY', description="API Key for Notion service")
    groq_api_key: str = Field(..., env='GROQ_API_KEY', description="API Key for Groq chatbot service")
    mistral_api_key: str = Field(..., env='MISTRAL_API_KEY', description="API Key for Mistral chatbot service")

    class Config:
        # Automatically load the settings from environment variables
        env_file = ".env"
        env_file_encoding = "utf-8"

try:
    settings = Settings()  # This will load from the .env or environment variables
except ValueError as e:
    print(f"Error loading configuration: {e}")