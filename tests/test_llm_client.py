"""Tests for qa_agent/llm_client.py — HTTP clients, error handling, retry behaviour."""

from __future__ import annotations

import io
import json
import os
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from qa_agent.llm_client import (
    DEFAULT_MODELS,
    AnthropicClient,
    LLMError,
    LLMProvider,
    LLMResponse,
    OpenAIClient,
    _http_post,
    create_llm_client,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _urlopen_ok(body: dict):
    """Return a mock urlopen context-manager that yields *body* as JSON."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(body).encode("utf-8")
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _http_error(code: int, body: str = "error"):
    """Return an HTTPError with the given status code."""
    exc = urllib.error.HTTPError(
        url="https://example.com",
        code=code,
        msg="HTTP Error",
        hdrs=MagicMock(),
        fp=io.BytesIO(body.encode("utf-8")),
    )
    return exc


# ---------------------------------------------------------------------------
# _http_post
# ---------------------------------------------------------------------------

class TestHttpPost:
    def test_successful_post_returns_parsed_json(self):
        body = {"key": "value"}
        with patch("urllib.request.urlopen", return_value=_urlopen_ok(body)):
            result = _http_post("https://api.example.com", {}, {}, timeout=10)
        assert result == body

    def test_post_sends_correct_method_and_body(self):
        with patch("urllib.request.Request") as mock_req, \
             patch("urllib.request.urlopen", return_value=_urlopen_ok({})):
            _http_post("https://api.example.com", {"H": "V"}, {"k": "v"}, timeout=10)
        mock_req.assert_called_once()
        # urllib.request.Request(url, data=..., headers=..., method=...)
        # first positional arg is url; data is a keyword arg
        args, kwargs = mock_req.call_args.args, mock_req.call_args.kwargs
        assert args[0] == "https://api.example.com"
        assert json.loads(kwargs["data"]) == {"k": "v"}
        assert kwargs["method"] == "POST"

    @pytest.mark.parametrize("code", [429, 500, 502, 503, 504, 529])
    def test_http_error_retryable_codes(self, code):
        with patch("urllib.request.urlopen", side_effect=_http_error(code)):
            with pytest.raises(LLMError) as exc_info:
                _http_post("https://api.example.com", {}, {}, timeout=10)
        assert exc_info.value.retryable is True
        assert exc_info.value.status_code == code

    @pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
    def test_http_error_non_retryable_codes(self, code):
        with patch("urllib.request.urlopen", side_effect=_http_error(code)):
            with pytest.raises(LLMError) as exc_info:
                _http_post("https://api.example.com", {}, {}, timeout=10)
        assert exc_info.value.retryable is False
        assert exc_info.value.status_code == code

    def test_url_error_is_retryable(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
            with pytest.raises(LLMError) as exc_info:
                _http_post("https://api.example.com", {}, {}, timeout=10)
        assert exc_info.value.retryable is True

    def test_timeout_error_is_retryable(self):
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            with pytest.raises(LLMError) as exc_info:
                _http_post("https://api.example.com", {}, {}, timeout=10)
        assert exc_info.value.retryable is True

    def test_http_error_status_code_in_message(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(429, "rate limited")):
            with pytest.raises(LLMError) as exc_info:
                _http_post("https://api.example.com", {}, {}, timeout=10)
        assert "429" in str(exc_info.value)


# ---------------------------------------------------------------------------
# AnthropicClient
# ---------------------------------------------------------------------------

_ANTHROPIC_RESPONSE = {
    "content": [{"type": "text", "text": "Hello from Claude"}],
    "model": "claude-sonnet-4-6",
}


class TestAnthropicClient:
    def _client(self, key="test-key"):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": key}):
            return AnthropicClient(model="claude-sonnet-4-6")

    def test_complete_returns_llm_response(self):
        client = self._client()
        with patch("qa_agent.llm_client._http_post", return_value=_ANTHROPIC_RESPONSE):
            result = client.complete("system", "user", max_tokens=100, timeout=10)
        assert isinstance(result, LLMResponse)
        assert result.text == "Hello from Claude"
        assert result.provider == LLMProvider.ANTHROPIC

    def test_complete_sends_correct_url(self):
        client = self._client()
        with patch("qa_agent.llm_client._http_post", return_value=_ANTHROPIC_RESPONSE) as mock_post:
            client.complete("system", "user", max_tokens=100, timeout=10)
        url = mock_post.call_args[0][0]
        assert url == "https://api.anthropic.com/v1/messages"

    def test_complete_sends_api_key_header(self):
        client = self._client(key="my-secret-key")
        with patch("qa_agent.llm_client._http_post", return_value=_ANTHROPIC_RESPONSE) as mock_post:
            client.complete("system", "user", max_tokens=100, timeout=10)
        headers = mock_post.call_args[0][1]
        assert headers["x-api-key"] == "my-secret-key"

    def test_complete_sends_anthropic_version_header(self):
        client = self._client()
        with patch("qa_agent.llm_client._http_post", return_value=_ANTHROPIC_RESPONSE) as mock_post:
            client.complete("system", "user", max_tokens=100, timeout=10)
        headers = mock_post.call_args[0][1]
        assert "anthropic-version" in headers

    def test_complete_body_includes_model_and_messages(self):
        client = self._client()
        with patch("qa_agent.llm_client._http_post", return_value=_ANTHROPIC_RESPONSE) as mock_post:
            client.complete("sys prompt", "user msg", max_tokens=512, timeout=10)
        body = mock_post.call_args[0][2]
        assert body["model"] == "claude-sonnet-4-6"
        assert body["max_tokens"] == 512
        assert body["system"] == "sys prompt"
        assert body["messages"] == [{"role": "user", "content": "user msg"}]

    def test_complete_no_text_content_raises_llm_error(self):
        client = self._client()
        empty_response = {"content": [{"type": "image", "data": "..."}]}
        with patch("qa_agent.llm_client._http_post", return_value=empty_response):
            with pytest.raises(LLMError, match="no text content"):
                client.complete("system", "user", max_tokens=100, timeout=10)

    def test_complete_empty_content_raises_llm_error(self):
        client = self._client()
        with patch("qa_agent.llm_client._http_post", return_value={"content": []}):
            with pytest.raises(LLMError):
                client.complete("system", "user", max_tokens=100, timeout=10)

    def test_api_key_from_env_var(self):
        env = {**{k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"},
               "ANTHROPIC_API_KEY": "env-key-value"}
        with patch.dict(os.environ, env, clear=True):
            client = AnthropicClient(model="test")
        assert client._api_key == "env-key-value"

    def test_explicit_api_key_overrides_env(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}):
            client = AnthropicClient(model="test", api_key="explicit-key")
        assert client._api_key == "explicit-key"

    def test_missing_key_raises_llm_error(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
                AnthropicClient(model="test")

    def test_api_key_not_in_response(self):
        """API key must not appear in the LLMResponse."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "super-secret-anthropic-key"}):
            client = AnthropicClient(model="test")
        with patch("qa_agent.llm_client._http_post", return_value=_ANTHROPIC_RESPONSE):
            result = client.complete("system", "user", max_tokens=100, timeout=10)
        assert "super-secret-anthropic-key" not in result.text
        assert "super-secret-anthropic-key" not in result.model


# ---------------------------------------------------------------------------
# OpenAIClient
# ---------------------------------------------------------------------------

_OPENAI_RESPONSE = {
    "choices": [
        {"message": {"role": "assistant", "content": "Hello from GPT"}}
    ],
    "model": "gpt-4o",
}


class TestOpenAIClient:
    def _client(self, key="test-openai-key"):
        with patch.dict(os.environ, {"OPENAI_API_KEY": key}):
            return OpenAIClient(model="gpt-4o")

    def test_complete_returns_llm_response(self):
        client = self._client()
        with patch("qa_agent.llm_client._http_post", return_value=_OPENAI_RESPONSE):
            result = client.complete("system", "user", max_tokens=100, timeout=10)
        assert isinstance(result, LLMResponse)
        assert result.text == "Hello from GPT"
        assert result.provider == LLMProvider.OPENAI

    def test_complete_sends_correct_url(self):
        client = self._client()
        with patch("qa_agent.llm_client._http_post", return_value=_OPENAI_RESPONSE) as mock_post:
            client.complete("system", "user", max_tokens=100, timeout=10)
        url = mock_post.call_args[0][0]
        assert url == "https://api.openai.com/v1/chat/completions"

    def test_complete_sends_bearer_auth_header(self):
        client = self._client(key="sk-my-openai-key")
        with patch("qa_agent.llm_client._http_post", return_value=_OPENAI_RESPONSE) as mock_post:
            client.complete("system", "user", max_tokens=100, timeout=10)
        headers = mock_post.call_args[0][1]
        assert headers["Authorization"] == "Bearer sk-my-openai-key"

    def test_complete_body_includes_model_and_messages(self):
        client = self._client()
        with patch("qa_agent.llm_client._http_post", return_value=_OPENAI_RESPONSE) as mock_post:
            client.complete("sys prompt", "user msg", max_tokens=256, timeout=10)
        body = mock_post.call_args[0][2]
        assert body["model"] == "gpt-4o"
        assert body["max_tokens"] == 256  # standard model — uses max_tokens
        messages = body["messages"]
        assert {"role": "system", "content": "sys prompt"} in messages
        assert {"role": "user", "content": "user msg"} in messages

    # -- Reasoning model token parameter --

    @pytest.mark.parametrize("model", ["o1", "o1-mini", "o1-preview", "o3", "o3-mini"])
    def test_reasoning_models_use_max_completion_tokens(self, model):
        """o1* and o3* models must send max_completion_tokens, not max_tokens."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}):
            client = OpenAIClient(model=model)
        with patch("qa_agent.llm_client._http_post", return_value=_OPENAI_RESPONSE) as mock_post:
            client.complete("system", "user", max_tokens=512, timeout=10)
        body = mock_post.call_args[0][2]
        assert "max_completion_tokens" in body, f"{model} should use max_completion_tokens"
        assert "max_tokens" not in body, f"{model} must not send max_tokens"
        assert body["max_completion_tokens"] == 512

    @pytest.mark.parametrize("model", ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"])
    def test_standard_models_use_max_tokens(self, model):
        """Non-reasoning models must send max_tokens, not max_completion_tokens."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}):
            client = OpenAIClient(model=model)
        with patch("qa_agent.llm_client._http_post", return_value=_OPENAI_RESPONSE) as mock_post:
            client.complete("system", "user", max_tokens=512, timeout=10)
        body = mock_post.call_args[0][2]
        assert "max_tokens" in body, f"{model} should use max_tokens"
        assert "max_completion_tokens" not in body, f"{model} must not send max_completion_tokens"

    def test_tokens_param_o1_returns_max_completion_tokens(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}):
            client = OpenAIClient(model="o1")
        assert client._tokens_param(1024) == {"max_completion_tokens": 1024}

    def test_tokens_param_gpt4o_returns_max_tokens(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}):
            client = OpenAIClient(model="gpt-4o")
        assert client._tokens_param(1024) == {"max_tokens": 1024}

    def test_complete_system_message_first(self):
        """System message must come before user message in the messages list."""
        client = self._client()
        with patch("qa_agent.llm_client._http_post", return_value=_OPENAI_RESPONSE) as mock_post:
            client.complete("system", "user", max_tokens=100, timeout=10)
        messages = mock_post.call_args[0][2]["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_complete_no_choices_raises_llm_error(self):
        client = self._client()
        with patch("qa_agent.llm_client._http_post", return_value={"choices": []}):
            with pytest.raises(LLMError, match="no choices"):
                client.complete("system", "user", max_tokens=100, timeout=10)

    def test_complete_empty_content_raises_llm_error(self):
        client = self._client()
        empty = {"choices": [{"message": {"role": "assistant", "content": ""}}]}
        with patch("qa_agent.llm_client._http_post", return_value=empty):
            with pytest.raises(LLMError, match="no text content"):
                client.complete("system", "user", max_tokens=100, timeout=10)

    def test_api_key_from_env_var(self):
        env = {**{k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"},
               "OPENAI_API_KEY": "env-openai-key"}
        with patch.dict(os.environ, env, clear=True):
            client = OpenAIClient(model="test")
        assert client._api_key == "env-openai-key"

    def test_explicit_api_key_overrides_env(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"}):
            client = OpenAIClient(model="test", api_key="explicit-openai-key")
        assert client._api_key == "explicit-openai-key"

    def test_missing_key_raises_llm_error(self):
        env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(LLMError, match="OPENAI_API_KEY"):
                OpenAIClient(model="test")

    def test_api_key_not_in_response(self):
        """API key must not appear in the LLMResponse."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "super-secret-openai-key"}):
            client = OpenAIClient(model="test")
        with patch("qa_agent.llm_client._http_post", return_value=_OPENAI_RESPONSE):
            result = client.complete("system", "user", max_tokens=100, timeout=10)
        assert "super-secret-openai-key" not in result.text
        assert "super-secret-openai-key" not in result.model


# ---------------------------------------------------------------------------
# create_llm_client factory
# ---------------------------------------------------------------------------

class TestCreateLLMClient:
    def test_anthropic_returns_anthropic_client(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "key"}):
            client = create_llm_client(LLMProvider.ANTHROPIC)
        assert isinstance(client, AnthropicClient)

    def test_openai_returns_openai_client(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}):
            client = create_llm_client(LLMProvider.OPENAI)
        assert isinstance(client, OpenAIClient)

    def test_anthropic_uses_default_model_when_none(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "key"}):
            client = create_llm_client(LLMProvider.ANTHROPIC, model=None)
        assert client.model == DEFAULT_MODELS[LLMProvider.ANTHROPIC]

    def test_openai_uses_default_model_when_none(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}):
            client = create_llm_client(LLMProvider.OPENAI, model=None)
        assert client.model == DEFAULT_MODELS[LLMProvider.OPENAI]

    def test_explicit_model_overrides_default(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "key"}):
            client = create_llm_client(LLMProvider.ANTHROPIC, model="claude-opus-4-6")
        assert client.model == "claude-opus-4-6"

    def test_explicit_api_key_used(self):
        with patch.dict(os.environ, {}, clear=True):
            client = create_llm_client(LLMProvider.ANTHROPIC, api_key="direct-key")
        assert client._api_key == "direct-key"


# ---------------------------------------------------------------------------
# DEFAULT_MODELS
# ---------------------------------------------------------------------------

class TestDefaultModels:
    def test_anthropic_default_model_defined(self):
        assert LLMProvider.ANTHROPIC in DEFAULT_MODELS
        assert DEFAULT_MODELS[LLMProvider.ANTHROPIC]  # non-empty string

    def test_openai_default_model_defined(self):
        assert LLMProvider.OPENAI in DEFAULT_MODELS
        assert DEFAULT_MODELS[LLMProvider.OPENAI]  # non-empty string


# ---------------------------------------------------------------------------
# LLMProvider enum
# ---------------------------------------------------------------------------

class TestLLMProvider:
    def test_values(self):
        assert LLMProvider.ANTHROPIC.value == "anthropic"
        assert LLMProvider.OPENAI.value == "openai"

    def test_str_lookup(self):
        assert LLMProvider("anthropic") == LLMProvider.ANTHROPIC
        assert LLMProvider("openai") == LLMProvider.OPENAI

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            LLMProvider("gemini")


# ---------------------------------------------------------------------------
# Retry behaviour in AIPlannerClient
# ---------------------------------------------------------------------------

class TestAIPlannerRetry:
    """Tests for _call_with_retry in ai_planner.AIPlannerClient."""

    def _planner_with_failing_client(self, side_effects):
        from qa_agent.ai_planner import AIPlannerClient
        client = MagicMock()
        client.complete.side_effect = side_effects
        planner = AIPlannerClient(provider=LLMProvider.ANTHROPIC, model="test")
        planner._client = client
        return planner

    def test_retryable_error_retried_then_succeeds(self):
        """A retryable error on attempt 1 should be retried and succeed on attempt 2."""
        from qa_agent.ai_planner import AIPlannerClient
        good_response = LLMResponse(text='{"summary":"s","focus_areas":[],"custom_steps":[],"suggested_urls":[],"notes":""}',
                                    provider=LLMProvider.ANTHROPIC, model="test")
        client = MagicMock()
        client.complete.side_effect = [
            LLMError("rate limit", retryable=True),
            good_response,
        ]
        planner = AIPlannerClient(provider=LLMProvider.ANTHROPIC, model="test")
        planner._client = client

        with patch("time.sleep"):  # don't actually sleep in tests
            plan = planner.plan("instructions", "https://example.com")

        assert client.complete.call_count == 2
        assert plan.summary == "s"

    def test_non_retryable_error_raised_immediately(self):
        """A non-retryable error must be re-raised after the first attempt."""
        client = MagicMock()
        client.complete.side_effect = LLMError("bad request", retryable=False)

        from qa_agent.ai_planner import AIPlannerClient
        planner = AIPlannerClient(provider=LLMProvider.ANTHROPIC, model="test")
        planner._client = client

        with patch("time.sleep"):
            with pytest.raises(LLMError, match="bad request"):
                planner.plan("instructions", "https://example.com")

        assert client.complete.call_count == 1  # no retries

    def test_exhausted_retries_raises_last_exception(self):
        """After all retries are exhausted the last retryable error should propagate."""
        client = MagicMock()
        client.complete.side_effect = LLMError("overloaded", retryable=True)

        from qa_agent.ai_planner import AIPlannerClient
        planner = AIPlannerClient(provider=LLMProvider.ANTHROPIC, model="test")
        planner._client = client

        with patch("time.sleep"):
            with pytest.raises(LLMError, match="overloaded"):
                planner.plan("instructions", "https://example.com")

        # 3 total attempts: 1 initial + 2 retries (_RETRY_DELAYS has 2 entries)
        assert client.complete.call_count == 3

    def test_sleep_called_between_retries(self):
        good_response = LLMResponse(
            text='{"summary":"s","focus_areas":[],"custom_steps":[],"suggested_urls":[],"notes":""}',
            provider=LLMProvider.ANTHROPIC, model="test",
        )
        client = MagicMock()
        client.complete.side_effect = [
            LLMError("retry me", retryable=True),
            LLMError("retry me again", retryable=True),
            good_response,
        ]
        from qa_agent.ai_planner import AIPlannerClient
        planner = AIPlannerClient(provider=LLMProvider.ANTHROPIC, model="test")
        planner._client = client

        with patch("time.sleep") as mock_sleep:
            planner.plan("instructions", "https://example.com")

        # sleep should be called once before attempt 2, once before attempt 3
        assert mock_sleep.call_count == 2
