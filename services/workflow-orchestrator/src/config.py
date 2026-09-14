import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Workflow Orchestrator configuration settings."""

    # Temporal Cluster Settings
    TEMPORAL_HOST: str = "localhost"
    TEMPORAL_PORT: int = 7233
    TEMPORAL_NAMESPACE: str = "default"
    TASK_QUEUE: str = "wct-case-audit-queue"

    # Upstream / Peer Service URLs
    CASE_MANAGEMENT_URL: str = "http://localhost:8000"
    AI_SUMMARY_URL: str = "http://localhost:8001"
    EXCLUSION_SCREENING_URL: str = "http://localhost:8002"
    NOTIFICATION_URL: str = "http://localhost:8003"
    AUDIT_TRAIL_URL: str = "http://localhost:8004"

    # SLA and Timeout Settings
    SLA_TIMEOUT_HOURS: int = 72

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def temporal_address(self) -> str:
        """Returns host:port formatted Temporal address."""
        return f"{self.TEMPORAL_HOST}:{self.TEMPORAL_PORT}"


settings = Settings()
