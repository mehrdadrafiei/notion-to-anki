import secrets
from typing import List, Literal, Tuple

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    notion_api_key: str = Field(..., env="NOTION_API_KEY", description="API Key for Notion service")
    groq_api_key: str = Field(..., env="GROQ_API_KEY", description="API Key for Groq chatbot service")
    mistral_api_key: str = Field(..., env="MISTRAL_API_KEY", description="API Key for Mistral chatbot service")
    max_retries: int = Field(3, description="Maximum number of retries for API calls")
    rate_limit_calls: int = Field(5, description="Rate limit - maximum calls allowed in the specified period")
    rate_limit_period: int = Field(60, description="Rate limit time period in seconds")
    cache_expiry: int = Field(3600, description="Cache expiry duration in seconds")
    cache_maxsize: int = Field(100, description="Cache maximum size")
    environment: str = Field("production", description="Environment for task tracking")
    secret_key: str = Field(secrets.token_urlsafe(32), description="Secret key for session management")
    redis_cluster_nodes: List[Tuple[str, int]] = Field(
        [("localhost", 7001), ("localhost", 7002), ("localhost", 7003)], description="Redis cluster node IP addresses"
    )
    redis_host: str = Field("localhost", description="Redis host")
    redis_port: int = Field(6379, description="Redis port")
    redis_max_connections: int = Field(10, description="Redis max connections")
    storage_type: Literal["memory", "redis"] = Field("memory", description="Storage backend type")

    @field_validator('notion_api_key', 'groq_api_key', 'mistral_api_key')
    def validate_api_keys(cls, v: str) -> str:
        """
        Validate that API keys are not empty and meet basic length criteria.
        """
        if not v or len(v.strip()) < 10:
            raise ValueError("The API key appears to be invalid or too short.")
        return v

    class Config:
        # Automatically load the settings from environment variables
        env_file = ".env"
        env_file_encoding = "utf-8"


class RedisSettings(BaseSettings):
    host: str = Field(..., env="REDIS_HOST")
    port: int = Field(..., env="REDIS_PORT")
    max_connections: int = Field(10, env="REDIS_MAX_CONNECTIONS")

    @field_validator("max_connections")
    def validate_max_connections(cls, v: int) -> int:
        if v < 1 or v > 100:
            raise ValueError("max_connections must be between 1 and 100")
        return v


class AppSettings(BaseSettings):
    redis: RedisSettings
    debug: bool = Field(False, env="DEBUG")
    environment: str = Field("development", env="ENVIRONMENT")


# Create a settings instance
settings = Settings()

# Export settings instance
__all__ = ['settings']
