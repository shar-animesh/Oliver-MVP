# Path: config.py
# Description: Central validated configuration for the Oliver API, OpenAI models, and PostgreSQL.

from functools import lru_cache
from typing import Optional

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application, model-provider, and database settings."""

    ENV: str = "development"
    LOGGING_LEVEL: str = "INFO"

    OPENAI_API_KEY: SecretStr
    OPENAI_BASE_URL: Optional[str] = None
    OPENAI_MODEL: str
    OPENAI_REASONING_EFFORT: str = "high"

    INTERNAL_API_KEY: SecretStr
    DATABASE_URL: SecretStr

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )


@lru_cache
def get_settings() -> Settings:
    """Get settings from .env file."""
    return Settings()
