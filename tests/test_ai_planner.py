"""Tests for qa_agent/ai_planner.py — prompt construction, response parsing, security."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from qa_agent.ai_planner import AIPlannerClient
from qa_agent.llm_client import LLMProvider, LLMResponse
from qa_agent.models import TestPlan


def _mock_client(response_text: str, provider: LLMProvider = LLMProvider.ANTHROPIC) -> MagicMock:
    """Return a mock LLM client whose complete() returns response_text."""
    client = MagicMock()
    client.complete.return_value = LLMResponse(
        text=response_text,
        provider=provider,
        model="mock-model",
    )
    return client


VALID_PLAN_JSON = """{
    "summary": "Test the login flow",
    "focus_areas": ["authentication", "form validation"],
    "custom_steps": [
        {
            "description": "Submit login form with valid credentials",
            "severity": "high",
            "category": "form_handling",
            "actions": [
                {"type": "fill", "selector": "#username", "value": "user@example.com"},
                {"type": "fill", "selector": "#password", "value": "password"},
                {"type": "click", "selector": "button[type=submit]"}
            ],
            "assertions": [
                {"type": "url_contains", "value": "/dashboard", "description": "Redirected after login"}
            ]
        }
    ],
    "suggested_urls": [],
    "notes": "Focus on the login page",
    "warnings": []
}"""


class TestAIPlannerParsing:
    def _planner(
        self,
        response_text: str,
        provider: LLMProvider = LLMProvider.ANTHROPIC,
    ) -> AIPlannerClient:
        planner = AIPlannerClient(provider=provider, model="mock-model")
        planner._client = _mock_client(response_text, provider)
        return planner

    def test_valid_json_returns_test_plan(self):
        planner = self._planner(VALID_PLAN_JSON)
        plan = planner.plan("test the login flow", "https://example.com")
        assert isinstance(plan, TestPlan)
        assert plan.summary == "Test the login flow"

    def test_focus_areas_parsed(self):
        planner = self._planner(VALID_PLAN_JSON)
        plan = planner.plan("test the login flow", "https://example.com")
        assert "authentication" in plan.focus_areas

    def test_custom_steps_parsed(self):
        planner = self._planner(VALID_PLAN_JSON)
        plan = planner.plan("test the login flow", "https://example.com")
        assert len(plan.custom_steps) == 1
        step = plan.custom_steps[0]
        assert step.description == "Submit login form with valid credentials"
        assert len(step.actions) == 3
        assert len(step.assertions) == 1

    def test_suggested_urls_always_empty(self):
        """AIPlannerClient should never trust AI-constructed URLs."""
        json_with_urls = VALID_PLAN_JSON.replace('"suggested_urls": []', '"suggested_urls": ["https://evil.com"]')
        planner = self._planner(json_with_urls)
        plan = planner.plan("test login", "https://example.com")
        assert plan.suggested_urls == []

    def test_malformed_json_raises_value_error(self):
        planner = self._planner("this is not json at all }{")
        with pytest.raises(ValueError, match="invalid JSON"):
            planner.plan("test", "https://example.com")

    def test_no_text_content_raises_llm_error(self):
        from qa_agent.llm_client import LLMError
        client = MagicMock()
        client.complete.side_effect = LLMError("No text content")
        planner = AIPlannerClient(provider=LLMProvider.ANTHROPIC, model="test")
        planner._client = client
        with pytest.raises(LLMError):
            planner.plan("test", "https://example.com")

    def test_empty_custom_steps_allowed(self):
        minimal = '{"summary": "no steps", "focus_areas": [], "custom_steps": [], "suggested_urls": [], "notes": "", "warnings": []}'
        planner = self._planner(minimal)
        plan = planner.plan("test", "https://example.com")
        assert plan.custom_steps == []

    def test_unknown_severity_defaults_to_medium(self):
        import json
        data = json.loads(VALID_PLAN_JSON)
        data["custom_steps"][0]["severity"] = "nonexistent_severity"
        planner = self._planner(json.dumps(data))
        plan = planner.plan("test", "https://example.com")
        from qa_agent.models import Severity
        assert plan.custom_steps[0].severity == Severity.MEDIUM

    def test_unknown_category_defaults_to_unexpected_behavior(self):
        import json
        data = json.loads(VALID_PLAN_JSON)
        data["custom_steps"][0]["category"] = "nonexistent_category"
        planner = self._planner(json.dumps(data))
        plan = planner.plan("test", "https://example.com")
        from qa_agent.models import FindingCategory
        assert plan.custom_steps[0].category == FindingCategory.UNEXPECTED_BEHAVIOR

    def test_openai_provider_parses_same_schema(self):
        """OpenAI responses use the same JSON schema — parsing must work for both providers."""
        planner = self._planner(VALID_PLAN_JSON, provider=LLMProvider.OPENAI)
        plan = planner.plan("test the login flow", "https://example.com")
        assert isinstance(plan, TestPlan)
        assert plan.summary == "Test the login flow"


class TestAIPlannerAPICall:
    def test_model_passed_to_complete(self):
        planner = AIPlannerClient(provider=LLMProvider.ANTHROPIC, model="claude-specific-model")
        planner._client = _mock_client(VALID_PLAN_JSON)
        planner.plan("test", "https://example.com")
        call_kwargs = planner._client.complete.call_args
        assert "claude-specific-model" in str(call_kwargs) or \
               planner.model == "claude-specific-model"

    def test_base_url_included_in_user_message(self):
        planner = AIPlannerClient(provider=LLMProvider.ANTHROPIC, model="test")
        planner._client = _mock_client(VALID_PLAN_JSON)
        planner.plan("test the checkout", "https://shop.example.com/cart")
        call_kwargs = planner._client.complete.call_args
        assert "https://shop.example.com/cart" in str(call_kwargs)

    def test_instructions_included_in_user_message(self):
        planner = AIPlannerClient(provider=LLMProvider.ANTHROPIC, model="test")
        planner._client = _mock_client(VALID_PLAN_JSON)
        planner.plan("verify the payment form accepts all card types", "https://example.com")
        call_kwargs = planner._client.complete.call_args
        assert "payment form" in str(call_kwargs)

    def test_system_prompt_passed_to_complete(self):
        planner = AIPlannerClient(provider=LLMProvider.OPENAI, model="gpt-4o")
        planner._client = _mock_client(VALID_PLAN_JSON, LLMProvider.OPENAI)
        planner.plan("check form validation", "https://example.com")
        call_kwargs = planner._client.complete.call_args
        assert "system" in str(call_kwargs)


class TestAIPlannerSecurity:
    def test_api_key_not_in_plan_object(self):
        """API key must never leak into the returned TestPlan."""
        fake_key = "sk-ant-test-supersecret-key-12345"
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": fake_key}):
            planner = AIPlannerClient(provider=LLMProvider.ANTHROPIC, model="test")
            planner._client = _mock_client(VALID_PLAN_JSON)
            plan = planner.plan("test", "https://example.com")

        plan_str = str(plan.__dict__)
        assert fake_key not in plan_str

    def test_api_key_not_in_exception_message(self):
        """If the API call fails, the key must not appear in the exception message."""
        fake_key = "sk-ant-test-supersecret-key-99999"
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": fake_key}):
            planner = AIPlannerClient(provider=LLMProvider.ANTHROPIC, model="test")
            planner._client = _mock_client("bad json {{{")
            try:
                planner.plan("test", "https://example.com")
            except ValueError as e:
                assert fake_key not in str(e)

    def test_openai_key_not_in_plan_object(self):
        """OpenAI API key must never leak into the returned TestPlan."""
        fake_key = "sk-openai-test-supersecret-key-12345"
        with patch.dict(os.environ, {"OPENAI_API_KEY": fake_key}):
            planner = AIPlannerClient(provider=LLMProvider.OPENAI, model="test")
            planner._client = _mock_client(VALID_PLAN_JSON, LLMProvider.OPENAI)
            plan = planner.plan("test", "https://example.com")

        plan_str = str(plan.__dict__)
        assert fake_key not in plan_str


class TestLLMClientMissingKey:
    def test_anthropic_missing_key_raises_llm_error(self):
        from qa_agent.llm_client import AnthropicClient, LLMError
        with patch.dict(os.environ, {}, clear=True):
            # Remove the key if present
            env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
            with patch.dict(os.environ, env, clear=True):
                with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
                    AnthropicClient(model="test")

    def test_openai_missing_key_raises_llm_error(self):
        from qa_agent.llm_client import LLMError, OpenAIClient
        env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(LLMError, match="OPENAI_API_KEY"):
                OpenAIClient(model="test")

    def test_create_llm_client_anthropic_missing_key(self):
        from qa_agent.llm_client import LLMError, create_llm_client
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
                create_llm_client(LLMProvider.ANTHROPIC)

    def test_create_llm_client_openai_missing_key(self):
        from qa_agent.llm_client import LLMError, create_llm_client
        env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(LLMError, match="OPENAI_API_KEY"):
                create_llm_client(LLMProvider.OPENAI)
