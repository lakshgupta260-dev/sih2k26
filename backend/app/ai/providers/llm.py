"""LLM provider abstraction.

There is deliberately **no** fake implementation here. If no provider is
configured, :class:`NullLLMProvider` reports itself unavailable and the
extraction service falls back to the deterministic rule-based extractor,
recording which extractor actually ran. A stub that invented plausible-looking
output would make the pipeline appear to work while producing fiction, which is
worse than not having it.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.core.logging import get_logger

logger = get_logger(__name__)


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal contract: given a prompt, return the model's text."""

    name: str

    def is_available(self) -> bool: ...

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> str: ...


class NullLLMProvider:
    """Used when no LLM is configured. Always unavailable, never invents text."""

    name = "none"

    def is_available(self) -> bool:
        return False

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> str:
        raise ExternalServiceError(
            "No LLM provider is configured. Set LLM_PROVIDER and LLM_API_KEY, "
            "or rely on the rule-based extractor.",
            code="LLM_NOT_CONFIGURED",
        )


class AnthropicLLMProvider:
    """Anthropic Messages API. Active only when an API key is configured."""

    name = "anthropic"
    endpoint = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str, timeout: int) -> None:
        self.api_key = api_key
        self.model = model or "claude-sonnet-4-5"
        self.timeout = timeout

    def is_available(self) -> bool:
        return bool(self.api_key)

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> str:
        try:
            response = httpx.post(
                self.endpoint,
                timeout=self.timeout,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
            response.raise_for_status()
            blocks = response.json().get("content", [])
            return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"LLM request failed: {exc}") from exc


class OpenAICompatibleLLMProvider:
    """Any OpenAI-compatible chat-completions endpoint."""

    name = "openai"

    def __init__(self, api_key: str, model: str, timeout: int,
                 base_url: str = "https://api.openai.com/v1") -> None:
        self.api_key = api_key
        self.model = model or "gpt-4o-mini"
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> str:
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                timeout=self.timeout,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"] or ""
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            raise ExternalServiceError(f"LLM request failed: {exc}") from exc


def get_llm_provider() -> LLMProvider:
    """Build the configured provider. Never raises; falls back to Null."""
    kind = (settings.LLM_PROVIDER or "none").strip().lower()
    if kind in ("", "none", "noop"):
        return NullLLMProvider()
    if not settings.LLM_API_KEY:
        logger.warning(
            "llm_provider_configured_without_key",
            extra={"provider": kind},
        )
        return NullLLMProvider()
    if kind == "anthropic":
        return AnthropicLLMProvider(
            settings.LLM_API_KEY, settings.LLM_MODEL, settings.LLM_TIMEOUT_SECONDS
        )
    if kind in ("openai", "openai_compatible"):
        return OpenAICompatibleLLMProvider(
            settings.LLM_API_KEY, settings.LLM_MODEL, settings.LLM_TIMEOUT_SECONDS
        )
    logger.warning("unknown_llm_provider", extra={"provider": kind})
    return NullLLMProvider()
