from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    notion_api_key: str = Field(..., env="NOTION_API_KEY", description="API Key for Notion service")
    groq_api_key: str = Field(..., env="GROQ_API_KEY", description="API Key for Groq chatbot service")
    mistral_api_key: str = Field(..., env="MISTRAL_API_KEY", description="API Key for Mistral chatbot service")
    max_retries: int = 3
    rate_limit_calls: int = 10
    rate_limit_period: int = 60
    cache_expiry: int = 3600

    @validator('notion_api_key', 'groq_api_key', 'mistral_api_key')
    def validate_api_keys(cls, v):
        if not v or len(v.strip()) < 10:  # Basic validation
            raise ValueError("API key appears to be invalid")
        return v

    class Config:
        # Automatically load the settings from environment variables
        env_file = ".env"
        env_file_encoding = "utf-8"


# Create settings instance
settings = Settings()

# Export settings instance
__all__ = ['settings']
