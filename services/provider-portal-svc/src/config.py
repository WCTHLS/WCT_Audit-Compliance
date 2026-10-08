"""
Configuration settings for Provider Portal Service.
Loads parameters from environment variables or .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings for provider-portal-svc."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../../infra/.env", "../../secrets/.env", "infra/.env", "secrets/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service Identification
    SERVICE_NAME: str = "provider-portal-svc"
    SERVICE_PORT: int = 8005
    DEBUG: bool = False

    # Inter-Service Integration URLs
    CASE_MANAGEMENT_URL: str = "http://localhost:8000"
    NOTIFICATION_URL: str = "http://localhost:8003"

    # Security
    JWT_SECRET_KEY: str = "wct-audit-compliance-dev-secret-key-2026"

    # In-Memory Storage Limits
    MAX_REQUESTS_ENTRIES: int = 1000


settings = Settings()
