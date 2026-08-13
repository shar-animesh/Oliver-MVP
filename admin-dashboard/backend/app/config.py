# Path: app/config.py
# Description: Central, validated environment configuration for the admin dashboard backend.

from functools import lru_cache
from typing import List, Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from process environment and an optional local `.env` file."""

    # Application configuration
    ENV: Literal["development", "test", "production"] = "development"
    LOG_LEVEL: str = "INFO"
    ANYIO_THREAD_POOL_TOKENS: int = Field(default=200, ge=1)
    OLIVER_CORS_ORIGINS: str = "http://localhost:5173"
    DATABASE_URL: SecretStr

    @property
    def cors_origins(self) -> List[str]:
        """Return normalized browser origins from the comma-separated environment value."""
        return [origin.strip() for origin in self.OLIVER_CORS_ORIGINS.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated settings singleton."""
    return Settings()
