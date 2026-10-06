"""
Configuration settings for Notification Service.
Loads parameters from environment variables or .env file.
"""

from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable fallback."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../../infra/.env", "../../secrets/.env", "infra/.env", "secrets/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service Configuration
    SERVICE_NAME: str = "notification-svc"
    SERVICE_PORT: int = 8003
    DEBUG: bool = False

    # Dispatcher Configuration
    DEFAULT_SENDER: str = "notifications@wct-health.com"
    ACTIVE_PROVIDERS: str = "console"  # comma-separated: console,webhook,smtp

    # Inter-Service Authentication
    JWT_SECRET_KEY: str = "wct-audit-compliance-dev-secret-key-2026"

    # In-memory history retention limit
    MAX_HISTORY_ENTRIES: int = 500


settings = Settings()
