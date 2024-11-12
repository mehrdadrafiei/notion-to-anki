from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    notion_api_key: str = Field(..., env="NOTION_API_KEY", description="API Key for Notion service")
    groq_api_key: str = Field(..., env="GROQ_API_KEY", description="API Key for Groq chatbot service")
    mistral_api_key: str = Field(..., env="MISTRAL_API_KEY", description="API Key for Mistral chatbot service")

    @validator('notion_api_key', 'groq_api_key', 'mistral_api_key')
    def validate_api_keys(cls, v):
        if not v or len(v.strip()) < 10:  # Basic validation
            raise ValueError("API key appears to be invalid")
        return v

    class Config:
        # Automatically load the settings from environment variables
        env_file = ".env"
        env_file_encoding = "utf-8"


try:
    settings = Settings()  # This will load from the .env or environment variables
except ValueError as e:
    print(f"Error loading configuration: {e}")
