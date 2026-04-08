"""Tests for qa_agent/ai_planner.py — prompt construction, response parsing, security."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from qa_agent.ai_planner import AIPlannerClient
from qa_agent.models import TestPlan


def _mock_client(response_text: str) -> MagicMock:
    """Return a mock anthropic.Anthropic client that returns response_text."""
    block = MagicMock()
    block.type = "text"
    block.text = response_text

    message = MagicMock()
    message.content = [block]

    client = MagicMock()
    client.messages.create.return_value = message
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
    "notes": "Focus on the login page"
}"""


class TestAIPlannerParsing:
    def _planner(self, response_text: str) -> AIPlannerClient:
        planner = AIPlannerClient(model="claude-test-model")
        planner._client = _mock_client(response_text)
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

    def test_no_text_content_raises_value_error(self):
        block = MagicMock()
        block.type = "not_text"
        message = MagicMock()
        message.content = [block]
        client = MagicMock()
        client.messages.create.return_value = message

        planner = AIPlannerClient(model="test")
        planner._client = client
        with pytest.raises(ValueError):
            planner.plan("test", "https://example.com")

    def test_empty_custom_steps_allowed(self):
        minimal = '{"summary": "no steps", "focus_areas": [], "custom_steps": [], "suggested_urls": [], "notes": ""}'
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


class TestAIPlannerAPICall:
    def test_model_id_used_in_create_call(self):
        planner = AIPlannerClient(model="claude-specific-model")
        planner._client = _mock_client(VALID_PLAN_JSON)
        planner.plan("test", "https://example.com")
        call_kwargs = planner._client.messages.create.call_args
        assert call_kwargs.kwargs.get("model") == "claude-specific-model" or \
               call_kwargs[1].get("model") == "claude-specific-model" or \
               "claude-specific-model" in str(call_kwargs)

    def test_base_url_included_in_user_message(self):
        planner = AIPlannerClient(model="test")
        planner._client = _mock_client(VALID_PLAN_JSON)
        planner.plan("test the checkout", "https://shop.example.com/cart")
        call_kwargs = planner._client.messages.create.call_args
        # user message should contain the URL
        user_content = str(call_kwargs)
        assert "https://shop.example.com/cart" in user_content

    def test_instructions_included_in_user_message(self):
        planner = AIPlannerClient(model="test")
        planner._client = _mock_client(VALID_PLAN_JSON)
        planner.plan("verify the payment form accepts all card types", "https://example.com")
        call_kwargs = planner._client.messages.create.call_args
        assert "payment form" in str(call_kwargs)


class TestAIPlannerSecurity:
    def test_api_key_not_in_plan_object(self):
        """API key must never leak into the returned TestPlan."""
        fake_key = "sk-ant-test-supersecret-key-12345"
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": fake_key}):
            planner = AIPlannerClient(model="test")
            planner._client = _mock_client(VALID_PLAN_JSON)
            plan = planner.plan("test", "https://example.com")

        plan_str = str(plan.__dict__)
        assert fake_key not in plan_str

    def test_api_key_not_in_exception_message(self):
        """If the API call fails, the key must not appear in the exception message."""
        fake_key = "sk-ant-test-supersecret-key-99999"
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": fake_key}):
            planner = AIPlannerClient(model="test")
            planner._client = _mock_client("bad json {{{")
            try:
                planner.plan("test", "https://example.com")
            except ValueError as e:
                assert fake_key not in str(e)
