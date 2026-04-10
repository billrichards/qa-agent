"""Lightweight LLM clients for Anthropic and OpenAI using Python's built-in urllib.

No third-party packages are required — all HTTP calls are made with ``urllib.request``
from the standard library.  Adding a new provider means implementing one class with a
single ``complete()`` method and registering it in ``create_llm_client``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"


# Default model IDs used when the caller does not specify one
DEFAULT_MODELS: dict[LLMProvider, str] = {
    LLMProvider.ANTHROPIC: "claude-sonnet-4-6",
    LLMProvider.OPENAI: "gpt-4o",
}

# Environment variable names for API keys
_KEY_ENV_VARS: dict[LLMProvider, str] = {
    LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
    LLMProvider.OPENAI: "OPENAI_API_KEY",
}


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""

    text: str
    provider: LLMProvider
    model: str


class LLMError(Exception):
    """Raised when an LLM API call fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


# ---------------------------------------------------------------------------
# Shared HTTP helper
# ---------------------------------------------------------------------------

def _http_post(url: str, headers: dict[str, str], body: dict, timeout: int) -> dict:
    """POST JSON to *url* and return the parsed response body.

    Raises :class:`LLMError` on HTTP errors, connection failures, or timeouts.
    The ``retryable`` flag is set for transient conditions (rate limits, server
    errors, connection problems) so callers can apply back-off retry logic.
    """
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return cast(dict[str, Any], json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        retryable = exc.code in (429, 500, 502, 503, 504, 529)
        raise LLMError(
            f"HTTP {exc.code}: {raw[:300]}",
            status_code=exc.code,
            retryable=retryable,
        ) from exc
    except urllib.error.URLError as exc:
        raise LLMError(str(exc), retryable=True) from exc
    except TimeoutError as exc:
        raise LLMError("Request timed out", retryable=True) from exc


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

class AnthropicClient:
    """Calls the Anthropic Messages API (``POST /v1/messages``) using urllib."""

    _API_URL = "https://api.anthropic.com/v1/messages"
    _API_VERSION = "2023-06-01"

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.model = model
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise LLMError(
                "Anthropic API key not found. "
                "Set the ANTHROPIC_API_KEY environment variable."
            )
        self._api_key = key

    def complete(self, system: str, user: str, max_tokens: int, timeout: int) -> LLMResponse:
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self._API_VERSION,
            "content-type": "application/json",
        }
        body: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        data = _http_post(self._API_URL, headers, body, timeout)
        content = data.get("content", [])
        text = next((b["text"] for b in content if b.get("type") == "text"), None)
        if not text:
            raise LLMError("Anthropic API returned no text content.")
        return LLMResponse(text=text, provider=LLMProvider.ANTHROPIC, model=self.model)


class OpenAIClient:
    """Calls the OpenAI Chat Completions API (``POST /v1/chat/completions``) using urllib."""

    _API_URL = "https://api.openai.com/v1/chat/completions"

    # OpenAI reasoning models use max_completion_tokens instead of max_tokens.
    # Match o1, o1-mini, o1-preview, o3, o3-mini, etc.
    _REASONING_MODEL_PREFIX = ("o1", "o3")

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.model = model
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise LLMError(
                "OpenAI API key not found. "
                "Set the OPENAI_API_KEY environment variable."
            )
        self._api_key = key

    def _tokens_param(self, max_tokens: int) -> dict:
        """Return the correct token-limit parameter for this model.

        Reasoning models (o1*, o3*) require ``max_completion_tokens``; all
        other models use the standard ``max_tokens``.
        """
        key = (
            "max_completion_tokens"
            if any(self.model.startswith(p) for p in self._REASONING_MODEL_PREFIX)
            else "max_tokens"
        )
        return {key: max_tokens}

    def complete(self, system: str, user: str, max_tokens: int, timeout: int) -> LLMResponse:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body: dict = {
            "model": self.model,
            **self._tokens_param(max_tokens),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        data = _http_post(self._API_URL, headers, body, timeout)
        choices = data.get("choices", [])
        if not choices:
            raise LLMError("OpenAI API returned no choices.")
        text = choices[0].get("message", {}).get("content", "")
        if not text:
            raise LLMError("OpenAI API returned no text content.")
        return LLMResponse(text=text, provider=LLMProvider.OPENAI, model=self.model)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_llm_client(
    provider: LLMProvider,
    model: str | None = None,
    api_key: str | None = None,
) -> AnthropicClient | OpenAIClient:
    """Create an LLM client for *provider*, using *model* (or the provider default).

    Raises :class:`LLMError` if the required API key is absent.
    """
    resolved_model = model or DEFAULT_MODELS[provider]
    if provider == LLMProvider.ANTHROPIC:
        return AnthropicClient(model=resolved_model, api_key=api_key)
    if provider == LLMProvider.OPENAI:
        return OpenAIClient(model=resolved_model, api_key=api_key)
    raise ValueError(f"Unknown LLM provider: {provider!r}")
