"""Unit tests for test plan reliability warnings."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from qa_agent.ai_planner import validate_plan
from qa_agent.config import LLMProvider
from qa_agent.models import CustomStep, StepAction, StepAssertion, TestPlan
from qa_agent.plan_cache import _deserialize, _serialize
from qa_agent.reporters.console import ConsoleReporter


class TestValidatePlanNoAssertions:
    """Rule 1: steps without assertions."""

    def test_step_without_assertions(self):
        plan = TestPlan(
            summary="Test",
            focus_areas=[],
            custom_steps=[
                CustomStep(
                    description="Click something",
                    actions=[StepAction(type="click", selector="button")],
                    assertions=[],
                )
            ],
        )
        warnings = validate_plan(plan)
        assert len(warnings) == 1
        assert "has actions but no assertions" in warnings[0]
        assert "Step 1" in warnings[0]

    def test_step_with_assertions_no_warning(self):
        plan = TestPlan(
            summary="Test",
            focus_areas=[],
            custom_steps=[
                CustomStep(
                    description="Click and check",
                    actions=[StepAction(type="click", selector="button")],
                    assertions=[StepAssertion(type="visible", selector=".result")],
                )
            ],
        )
        warnings = validate_plan(plan)
        assert len(warnings) == 0


class TestValidatePlanUnknownAssertionTypes:
    """Rule 2: unknown assertion types silently pass."""

    def test_unknown_assertion_type(self):
        plan = TestPlan(
            summary="Test",
            focus_areas=[],
            custom_steps=[
                CustomStep(
                    description="Check something",
                    actions=[],
                    assertions=[StepAssertion(type="css_property", selector="div")],
                )
            ],
        )
        warnings = validate_plan(plan)
        assert len(warnings) == 1
        assert "assertion type 'css_property' is not supported" in warnings[0]
        assert "Supported types" in warnings[0]

    def test_known_assertion_types_no_warning(self):
        plan = TestPlan(
            summary="Test",
            focus_areas=[],
            custom_steps=[
                CustomStep(
                    description="Check",
                    actions=[],
                    assertions=[
                        StepAssertion(type="visible", selector="div"),
                        StepAssertion(type="hidden", selector="span"),
                        StepAssertion(type="text_contains", selector="p", value="hello"),
                        StepAssertion(type="url_contains", value="/path"),
                        StepAssertion(type="element_count", selector="li", value="5"),
                    ],
                )
            ],
        )
        warnings = validate_plan(plan)
        assert len(warnings) == 0


class TestValidatePlanHoverNoWait:
    """Rule 3: hover with no wait before assertions."""

    def test_hover_no_wait_before_assertion(self):
        plan = TestPlan(
            summary="Test",
            focus_areas=[],
            custom_steps=[
                CustomStep(
                    description="Hover and check",
                    actions=[StepAction(type="hover", selector=".card")],
                    assertions=[StepAssertion(type="visible", selector=".tooltip")],
                )
            ],
        )
        warnings = validate_plan(plan)
        assert len(warnings) == 1
        assert "ends with a hover but has no 'wait' before assertions" in warnings[0]

    def test_hover_with_wait_no_warning(self):
        plan = TestPlan(
            summary="Test",
            focus_areas=[],
            custom_steps=[
                CustomStep(
                    description="Hover, wait, check",
                    actions=[
                        StepAction(type="hover", selector=".card"),
                        StepAction(type="wait", value="300"),
                    ],
                    assertions=[StepAssertion(type="visible", selector=".tooltip")],
                )
            ],
        )
        warnings = validate_plan(plan)
        assert len(warnings) == 0

    def test_hover_then_click_no_warning(self):
        # hover → click → assertion should NOT trigger Rule 3 (click clears the hover-timing flag)
        plan = TestPlan(
            summary="Test",
            focus_areas=[],
            custom_steps=[
                CustomStep(
                    description="Hover then click",
                    actions=[
                        StepAction(type="hover", selector=".card"),
                        StepAction(type="click", selector=".button"),
                    ],
                    assertions=[StepAssertion(type="visible", selector=".result")],
                )
            ],
        )
        warnings = validate_plan(plan)
        assert len(warnings) == 0

    def test_hover_without_selector_still_warns_on_timing(self):
        # hover without selector (edge case) should not crash
        plan = TestPlan(
            summary="Test",
            focus_areas=[],
            custom_steps=[
                CustomStep(
                    description="Hover no selector",
                    actions=[StepAction(type="hover")],
                    assertions=[StepAssertion(type="visible", selector=".tooltip")],
                )
            ],
        )
        warnings = validate_plan(plan)
        # Should trigger warning because hover with no wait before assertions
        assert len(warnings) == 1
        assert "ends with a hover but has no 'wait' before assertions" in warnings[0]


class TestValidatePlanHoverVisibleSameSelector:
    """Rule 4: trivial visible assertion on same hover selector."""

    def test_hover_visible_same_selector(self):
        plan = TestPlan(
            summary="Test",
            focus_areas=[],
            custom_steps=[
                CustomStep(
                    description="Hover and assert same element visible",
                    actions=[StepAction(type="hover", selector=".card")],
                    assertions=[StepAssertion(type="visible", selector=".card")],
                )
            ],
        )
        warnings = validate_plan(plan)
        # Should trigger both rule 3 (hover no wait) and rule 4 (hover+visible same selector)
        assert len(warnings) == 2
        # Check for rule 3 warning
        rule3_warnings = [w for w in warnings if "ends with a hover but has no 'wait' before assertions" in w]
        assert len(rule3_warnings) == 1
        # Check for rule 4 warning
        rule4_warnings = [w for w in warnings if "asserts '.card' is visible after hovering it" in w]
        assert len(rule4_warnings) == 1
        assert "trivially passes" in rule4_warnings[0]

    def test_hover_hidden_same_selector_no_warning(self):
        # hidden assertion is not trivial (element could be hidden before hover)
        plan = TestPlan(
            summary="Test",
            focus_areas=[],
            custom_steps=[
                CustomStep(
                    description="Hover and assert hidden",
                    actions=[StepAction(type="hover", selector=".card")],
                    assertions=[StepAssertion(type="hidden", selector=".card")],
                )
            ],
        )
        warnings = validate_plan(plan)
        # Should trigger rule 3 (hover no wait) but NOT rule 4 (hidden assertion)
        assert len(warnings) == 1
        assert "ends with a hover but has no 'wait' before assertions" in warnings[0]

    def test_hover_visible_different_selector_no_warning(self):
        plan = TestPlan(
            summary="Test",
            focus_areas=[],
            custom_steps=[
                CustomStep(
                    description="Hover one, assert another",
                    actions=[StepAction(type="hover", selector=".card")],
                    assertions=[StepAssertion(type="visible", selector=".tooltip")],
                )
            ],
        )
        warnings = validate_plan(plan)
        # Should trigger rule 3 (hover no wait) but NOT rule 4 (different selector)
        assert len(warnings) == 1
        assert "ends with a hover but has no 'wait' before assertions" in warnings[0]

    def test_hover_without_selector_does_not_trigger_rule4(self):
        """Edge case: hover with no selector should not add to hover_selectors set.
        This ensures Rule 4 (trivial visible assertion) doesn't fire spuriously
        when action.selector is None.
        """
        plan = TestPlan(
            summary="Test",
            focus_areas=[],
            custom_steps=[
                CustomStep(
                    description="Hover without selector, assert visible on some element",
                    actions=[StepAction(type="hover")],  # selector is None
                    assertions=[StepAssertion(type="visible", selector=".tooltip")],
                )
            ],
        )
        warnings = validate_plan(plan)
        # Should trigger rule 3 (hover no wait) but NOT rule 4 (no selector to compare)
        assert len(warnings) == 1
        assert "ends with a hover but has no 'wait' before assertions" in warnings[0]
        # Ensure no rule 4 warning about trivial visible assertion
        assert not any("trivially passes" in w for w in warnings)


class TestValidatePlanMultiStep:
    """Step numbers in warning text, multi-step plans."""

    def test_multi_step_warnings(self):
        plan = TestPlan(
            summary="Test",
            focus_areas=[],
            custom_steps=[
                CustomStep(
                    description="First step",
                    actions=[StepAction(type="click", selector="button")],
                    assertions=[],
                ),
                CustomStep(
                    description="Second step",
                    actions=[StepAction(type="hover", selector=".card")],
                    assertions=[StepAssertion(type="visible", selector=".card")],
                ),
            ],
        )
        warnings = validate_plan(plan)
        # Step 1: rule 1 (no assertions)
        # Step 2: rule 3 (hover no wait) + rule 4 (hover+visible same selector)
        assert len(warnings) == 3
        # Check step numbers
        step1_warnings = [w for w in warnings if "Step 1" in w]
        step2_warnings = [w for w in warnings if "Step 2" in w]
        assert len(step1_warnings) == 1
        assert len(step2_warnings) == 2
        # Verify content
        assert "has actions but no assertions" in step1_warnings[0]
        rule3_warnings = [w for w in step2_warnings if "ends with a hover but has no 'wait' before assertions" in w]
        rule4_warnings = [w for w in step2_warnings if "asserts '.card' is visible after hovering it" in w]
        assert len(rule3_warnings) == 1
        assert len(rule4_warnings) == 1


class TestPrintWarning:
    """ConsoleReporter.print_warning() output."""

    def test_print_warning_with_colors(self):
        import sys
        from io import StringIO
        from unittest.mock import patch

        # Patch isatty to return True so colors are enabled
        with patch('sys.stdout.isatty', return_value=True):
            reporter = ConsoleReporter(use_colors=True)
            # Mock print to capture output
            old_stdout = sys.stdout
            sys.stdout = StringIO()
            try:
                reporter.print_warning("CSS property checks are not supported.")
                output = sys.stdout.getvalue().strip()
            finally:
                sys.stdout = old_stdout
            assert "WARNING:" in output
            assert "CSS property checks are not supported." in output
            # ANSI color codes present
            assert "\033[" in output

    def test_print_warning_without_colors(self):
        reporter = ConsoleReporter(use_colors=False)
        import sys
        from io import StringIO
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            reporter.print_warning("Animation timing ambiguous.")
            output = sys.stdout.getvalue().strip()
        finally:
            sys.stdout = old_stdout
        assert "WARNING:" in output
        assert "Animation timing ambiguous." in output
        # No ANSI codes
        assert "\033[" not in output


class TestParsePlanWarnings:
    """LLM + rule warnings merged; missing/empty field degrades gracefully."""

    def test_parse_plan_with_warnings(self):
        from qa_agent.ai_planner import AIPlannerClient
        # Mock LLM response containing warnings
        json_data = {
            "summary": "Test",
            "focus_areas": [],
            "custom_steps": [
                {
                    "description": "Click button",
                    "severity": "medium",
                    "category": "form_handling",
                    "actions": [{"type": "click", "selector": "button"}],
                    "assertions": [],
                }
            ],
            "suggested_urls": [],
            "notes": "",
            "warnings": ["CSS property checks are not supported."],
        }
        mock_client = MagicMock()
        mock_client.complete.return_value = MagicMock(
            text=json.dumps(json_data),
            provider=LLMProvider.ANTHROPIC,
            model="mock",
        )
        planner = AIPlannerClient(provider=LLMProvider.ANTHROPIC, model="mock")
        planner._client = mock_client
        plan = planner.plan("test", "https://example.com")
        # Should have both LLM warning and rule-based warning (no assertions)
        assert len(plan.warnings) == 2
        llm_warnings = [w for w in plan.warnings if "CSS property" in w]
        assert len(llm_warnings) == 1
        rule_warnings = [w for w in plan.warnings if "has actions but no assertions" in w]
        assert len(rule_warnings) == 1

    def test_parse_plan_with_empty_warnings(self):
        from qa_agent.ai_planner import AIPlannerClient
        json_data = {
            "summary": "Test",
            "focus_areas": [],
            "custom_steps": [
                {
                    "description": "Click button",
                    "severity": "medium",
                    "category": "form_handling",
                    "actions": [{"type": "click", "selector": "button"}],
                    "assertions": [{"type": "visible", "selector": ".result"}],
                }
            ],
            "suggested_urls": [],
            "notes": "",
            "warnings": [],
        }
        mock_client = MagicMock()
        mock_client.complete.return_value = MagicMock(
            text=json.dumps(json_data),
            provider=LLMProvider.ANTHROPIC,
            model="mock",
        )
        planner = AIPlannerClient(provider=LLMProvider.ANTHROPIC, model="mock")
        planner._client = mock_client
        plan = planner.plan("test", "https://example.com")
        # No warnings
        assert plan.warnings == []

    def test_parse_plan_with_non_string_warnings_filtered(self):
        from qa_agent.ai_planner import AIPlannerClient
        json_data = {
            "summary": "Test",
            "focus_areas": [],
            "custom_steps": [],
            "suggested_urls": [],
            "notes": "",
            "warnings": [123, None, "valid warning", ""],
        }
        mock_client = MagicMock()
        mock_client.complete.return_value = MagicMock(
            text=json.dumps(json_data),
            provider=LLMProvider.ANTHROPIC,
            model="mock",
        )
        planner = AIPlannerClient(provider=LLMProvider.ANTHROPIC, model="mock")
        planner._client = mock_client
        plan = planner.plan("test", "https://example.com")
        # Only the valid string warning is kept, empty string filtered out
        assert plan.warnings == ["valid warning"]


class TestPlanCacheWarningsRoundTrip:
    """Serialize → deserialize preserves warnings; old cache files return []."""

    def test_serialize_deserialize_with_warnings(self):
        plan = TestPlan(
            summary="Test",
            focus_areas=["login"],
            custom_steps=[],
            suggested_urls=[],
            notes="",
            warnings=["Warning one", "Warning two"],
        )
        data = _serialize(plan)
        assert "warnings" in data
        assert data["warnings"] == ["Warning one", "Warning two"]
        deserialized = _deserialize(data)
        assert deserialized.warnings == ["Warning one", "Warning two"]

    def test_deserialize_old_cache_without_warnings(self):
        # Simulate old cache data missing the warnings key
        data = {
            "summary": "Test",
            "focus_areas": [],
            "notes": "",
            "suggested_urls": [],
            "custom_steps": [],
        }
        deserialized = _deserialize(data)
        assert deserialized.warnings == []

    def test_deserialize_with_empty_warnings(self):
        data = {
            "summary": "Test",
            "focus_areas": [],
            "notes": "",
            "suggested_urls": [],
            "custom_steps": [],
            "warnings": [],
        }
        deserialized = _deserialize(data)
        assert deserialized.warnings == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
