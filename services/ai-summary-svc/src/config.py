"""
Configuration settings for AI Summary Service.
"""

import os
from dataclasses import dataclass


@dataclass
class Settings:
    """Application settings with environment variable support."""

    SERVICE_NAME: str = os.getenv("SERVICE_NAME", "ai-summary-svc")
    SERVICE_PORT: int = int(os.getenv("SERVICE_PORT", "8001"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

    # LLM Settings
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "foundry")  # "foundry" | "ollama" | "mock" | "openai"
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    LLM_TIMEOUT_SECONDS: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "120.0"))

    # Foundry Local Settings
    FOUNDRY_BASE_URL: str = os.getenv("FOUNDRY_BASE_URL", "http://127.0.0.1:51664/v1")
    FOUNDRY_MODEL: str = os.getenv("FOUNDRY_MODEL", "qwen2.5-7b-instruct-openvino-gpu")

    # Context & Token Limits
    MODEL_CONTEXT_LIMIT: int = int(os.getenv("MODEL_CONTEXT_LIMIT", "32768"))
    OUTPUT_TOKENS: int = int(os.getenv("OUTPUT_TOKENS", "1000"))


settings = Settings()

