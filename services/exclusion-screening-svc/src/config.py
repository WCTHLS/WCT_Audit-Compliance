"""
Configuration settings for Exclusion Screening Service.
Loads database and service parameters from environment variables or .env file.
"""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable fallback."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../../infra/.env", "../../secrets/.env", "infra/.env", "secrets/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service Configuration
    SERVICE_NAME: str = "exclusion-screening-svc"
    SERVICE_PORT: int = 8002
    DEBUG: bool = False

    # PostgreSQL Database Settings
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "change-me"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5433
    POSTGRES_DB: str = "audit_compliance"
    DATABASE_URL: Optional[str] = None

    @property
    def database_url(self) -> str:
        """Constructs full PostgreSQL connection string if not explicitly set."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
