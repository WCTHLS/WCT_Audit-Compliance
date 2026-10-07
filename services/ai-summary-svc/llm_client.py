"""
LLM Client abstraction for AI Summary Service.
Interacts with Foundry Local and Ollama models with OpenAI-compatible API.
Raises LLMClientError on any failure without silent fallbacks.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
import httpx

from src.config import settings

logger = logging.getLogger("ai_summary.llm_client")


class LLMClientError(Exception):
    """Raised when an LLM completion request fails."""
    pass


class LLMClient:
    """
    Client for interacting with local LLMs (Foundry / Ollama) or external providers.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.provider = (provider or settings.LLM_PROVIDER).lower()
        if self.provider == "foundry":
            self.base_url = base_url or settings.FOUNDRY_BASE_URL.rstrip("/")
            self.model = model or settings.FOUNDRY_MODEL
        else:
            self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
            self.model = model or settings.OLLAMA_MODEL
        self.timeout = timeout or settings.LLM_TIMEOUT_SECONDS
        self.last_finish_reason: Optional[str] = None
        self.last_prompt_tokens: Optional[int] = None

    async def check_health(self) -> Dict[str, Any]:
        """Checks if the configured LLM provider is reachable."""
        if self.provider == "foundry":
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(f"{self.base_url}/models")
                    if resp.status_code == 200:
                        data = resp.json().get("data", [])
                        models = [m.get("id") for m in data]
                        return {
                            "provider": "foundry",
                            "status": "connected",
                            "base_url": self.base_url,
                            "configured_model": self.model,
                            "available_models": models,
                        }
            except Exception as exc:
                logger.debug(f"Foundry health check probe failed: {exc}")

            return {
                "provider": "foundry",
                "status": "unreachable",
                "base_url": self.base_url,
                "model": self.model,
            }

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                if resp.status_code == 200:
                    models = [m.get("name") for m in resp.json().get("models", [])]
                    return {
                        "provider": "ollama",
                        "status": "connected",
                        "base_url": self.base_url,
                        "configured_model": self.model,
                        "available_models": models,
                    }
        except Exception as exc:
            logger.debug(f"LLM health check probe failed: {exc}")

        return {
            "provider": self.provider,
            "status": "unreachable",
            "base_url": self.base_url,
            "model": self.model,
        }

    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        case_id: Optional[str] = None,
        claim_ref: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 700,
        stop_sequences: Optional[List[str]] = None,
    ) -> str:
        """
        Sends a prompt to the LLM and returns the text response.
        Raises LLMClientError on any provider error, timeout, or HTTP failure.
        """
        self.last_finish_reason = None
        self.last_prompt_tokens = None

        sys_msg = system_prompt or (
            "You are a healthcare claims audit summarization assistant. "
            "You write the narrative sections of a case summary that a human auditor reads."
        )
        if "/no_think" not in sys_msg:
            sys_msg = sys_msg + "\n/no_think"

        stops = stop_sequences or ["CASE DATA", "=========", "<|eot_id|>", "<|im_end|>"]

        # 1. Foundry Local / OpenAI-compatible endpoint
        if self.provider in ("foundry", "openai"):
            endpoint = f"{self.base_url}/chat/completions"
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            client_timeout = httpx.Timeout(self.timeout, connect=5.0)
            max_busy_retries = 5
            for attempt in range(max_busy_retries):
                try:
                    async with httpx.AsyncClient(timeout=client_timeout) as client:
                        resp = await client.post(endpoint, json=payload)
                        if resp.status_code == 200:
                            data = resp.json()
                            usage = data.get("usage") or {}
                            self.last_prompt_tokens = usage.get("prompt_tokens")
                            choices = data.get("choices", [])
                            if choices and "message" in choices[0]:
                                self.last_finish_reason = choices[0].get("finish_reason")
                                content = choices[0]["message"].get("content", "").strip()
                                if content:
                                    logger.info(
                                        f"LLM completion received via {self.provider} ({len(content)} chars, prompt_tokens={self.last_prompt_tokens})."
                                    )
                                    return content
                            raise LLMClientError(f"Foundry returned 200 but response content was empty: {data}")
                        elif resp.status_code == 500 and "busy" in resp.text.lower() and attempt < max_busy_retries - 1:
                            logger.warning(f"Foundry infer request is busy, waiting 3s before retry (attempt {attempt + 1}/{max_busy_retries})...")
                            await asyncio.sleep(3.0)
                            continue
                        else:
                            raise LLMClientError(f"Foundry returned HTTP {resp.status_code}: {resp.text}")
                except httpx.RequestError as req_err:
                    if attempt < max_busy_retries - 1:
                        await asyncio.sleep(2.0)
                        continue
                    raise LLMClientError(f"Connection to Foundry at '{self.base_url}' failed: {req_err}") from req_err

        # 2. Ollama native /api/chat
        native_endpoint = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {
                "num_ctx": 4096,
                "temperature": temperature,
                "top_p": 0.9,
                "repeat_penalty": 1.05,
                "num_predict": max_tokens,
                "stop": stops,
            },
        }

        try:
            client_timeout = httpx.Timeout(self.timeout, connect=3.0)
            async with httpx.AsyncClient(timeout=client_timeout) as client:
                resp = await client.post(native_endpoint, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    msg = data.get("message", {})
                    content = msg.get("content", "").strip()
                    if content:
                        self.last_prompt_tokens = data.get("prompt_eval_count")
                        logger.info(f"LLM completion received via Ollama ({len(content)} chars).")
                        return content
                    raise LLMClientError(f"Ollama returned 200 but message content was empty: {data}")
                raise LLMClientError(f"Ollama returned HTTP {resp.status_code}: {resp.text}")
        except httpx.RequestError as exc:
            raise LLMClientError(f"Connection to Ollama at '{self.base_url}' failed: {exc}") from exc


# Global singleton instance
llm_client = LLMClient()

