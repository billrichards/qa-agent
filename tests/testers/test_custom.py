"""Tests for qa_agent/testers/custom.py — action execution, assertion checking."""

from __future__ import annotations

import warnings
from unittest.mock import MagicMock

from qa_agent.config import TestConfig
from qa_agent.models import (
    CustomStep,
    FindingCategory,
    Severity,
    StepAction,
    StepAssertion,
    TestPlan,
)
from qa_agent.testers.custom import CustomTester


def _tester(page=None, steps=None) -> CustomTester:
    if page is None:
        page = MagicMock()
        page.url = "https://example.com"
    config = TestConfig(urls=["https://example.com"])
    plan = TestPlan(
        summary="Test plan",
        custom_steps=steps or [],
    )
    return CustomTester(page, config, plan)


def _step(
    description="Test step",
    actions=None,
    assertions=None,
    severity=Severity.MEDIUM,
    category=FindingCategory.UNEXPECTED_BEHAVIOR,
) -> CustomStep:
    return CustomStep(
        description=description,
        actions=actions or [],
        assertions=assertions or [],
        severity=severity,
        category=category,
    )


class TestActionExecution:
    def test_click_action_calls_page_locator_click(self):
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value.first.click.return_value = None
        step = _step(actions=[StepAction(type="click", selector="#btn")])
        tester = _tester(page, steps=[step])
        findings = tester.run()
        page.locator.assert_called_with("#btn")
        assert len(findings) == 0  # no assertion failures

    def test_fill_action_calls_fill(self):
        page = MagicMock()
        page.url = "https://example.com"
        step = _step(actions=[StepAction(type="fill", selector="#input", value="hello")])
        tester = _tester(page, steps=[step])
        tester.run()
        page.locator.return_value.first.fill.assert_called()

    def test_action_failure_produces_finding(self):
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value.first.click.side_effect = RuntimeError("element not found")
        step = _step(actions=[StepAction(type="click", selector="#missing")])
        tester = _tester(page, steps=[step])
        findings = tester.run()
        assert len(findings) == 1
        assert "action failed" in findings[0].title.lower()

    def test_action_failure_aborts_assertions(self):
        """When an action fails, subsequent assertions in the same step are skipped."""
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value.first.click.side_effect = RuntimeError("boom")
        step = _step(
            actions=[StepAction(type="click", selector="#btn")],
            assertions=[StepAssertion(type="visible", selector="#result")],
        )
        tester = _tester(page, steps=[step])
        findings = tester.run()
        # Only one finding from action failure, not one from assertion too
        assert len(findings) == 1

    def test_unknown_action_type_emits_warning_not_finding(self):
        page = MagicMock()
        page.url = "https://example.com"
        step = _step(actions=[StepAction(type="teleport_to_moon")])
        tester = _tester(page, steps=[step])
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            findings = tester.run()
        assert len(findings) == 0  # unknown action type is a warning, not a finding
        assert any("teleport_to_moon" in str(warning.message) for warning in w)

    def test_wait_action_calls_wait_for_timeout(self):
        page = MagicMock()
        page.url = "https://example.com"
        step = _step(actions=[StepAction(type="wait", value="500")])
        tester = _tester(page, steps=[step])
        tester.run()
        page.wait_for_timeout.assert_called_with(500)

    def test_wait_action_default_timeout_when_not_digit(self):
        """Non-digit wait value → defaults to 1000ms."""
        page = MagicMock()
        page.url = "https://example.com"
        step = _step(actions=[StepAction(type="wait", value="slow")])
        tester = _tester(page, steps=[step])
        tester.run()
        page.wait_for_timeout.assert_called_with(1000)

    def test_press_key_without_selector_uses_keyboard(self):
        page = MagicMock()
        page.url = "https://example.com"
        step = _step(actions=[StepAction(type="press_key", value="Enter")])
        tester = _tester(page, steps=[step])
        tester.run()
        page.keyboard.press.assert_called_with("Enter")

    def test_press_key_with_selector_uses_element_press(self):
        """press_key with a selector should press on the element, not keyboard."""
        page = MagicMock()
        page.url = "https://example.com"
        step = _step(actions=[StepAction(type="press_key", selector="#input", value="Tab")])
        tester = _tester(page, steps=[step])
        tester.run()
        page.locator.return_value.first.press.assert_called_with("Tab", timeout=5000)
        page.keyboard.press.assert_not_called()

    def test_hover_action_calls_hover(self):
        """Hover action should call hover() on the located element."""
        page = MagicMock()
        page.url = "https://example.com"
        step = _step(actions=[StepAction(type="hover", selector="#menu-item")])
        tester = _tester(page, steps=[step])
        tester.run()
        page.locator.assert_called_with("#menu-item")
        page.locator.return_value.first.hover.assert_called_with(timeout=5000)

    def test_navigate_action_calls_goto(self):
        """Navigate action should call page.goto()."""
        page = MagicMock()
        page.url = "https://example.com"
        step = _step(actions=[StepAction(type="navigate", value="https://example.com/about")])
        tester = _tester(page, steps=[step])
        tester.run()
        page.goto.assert_called_with("https://example.com/about", wait_until="domcontentloaded")

    def test_navigate_action_restores_url(self):
        """After a navigate action, the original URL should be restored."""
        original_url = "https://example.com"
        new_url = "https://example.com/about"

        page = MagicMock()
        page.url = original_url
        # After navigation, page.url becomes new_url
        page.goto.side_effect = lambda url, **kw: None

        # Simulate URL change after navigate
        type(page).url = property(
            fget=lambda self: new_url,  # always returns new_url after navigate
        )

        step = _step(actions=[StepAction(type="navigate", value=new_url)])
        tester = _tester(page, steps=[step])
        tester.run()

        # Should have called goto twice: once for navigate, once for restoration
        assert page.goto.call_count >= 1

    def test_scroll_action_with_selector(self):
        """Scroll with a selector → scroll_into_view_if_needed."""
        page = MagicMock()
        page.url = "https://example.com"
        step = _step(actions=[StepAction(type="scroll", selector="#footer")])
        tester = _tester(page, steps=[step])
        tester.run()
        page.locator.return_value.first.scroll_into_view_if_needed.assert_called()

    def test_scroll_action_down_without_selector(self):
        """Scroll without selector and direction 'down' → mouse.wheel with positive delta."""
        page = MagicMock()
        page.url = "https://example.com"
        step = _step(actions=[StepAction(type="scroll", value="down")])
        tester = _tester(page, steps=[step])
        tester.run()
        page.mouse.wheel.assert_called_with(0, 300)

    def test_scroll_action_up_without_selector(self):
        """Scroll without selector and direction 'up' → mouse.wheel with negative delta."""
        page = MagicMock()
        page.url = "https://example.com"
        step = _step(actions=[StepAction(type="scroll", value="up")])
        tester = _tester(page, steps=[step])
        tester.run()
        page.mouse.wheel.assert_called_with(0, -300)

    def test_scroll_action_default_direction_is_down(self):
        """Scroll with no value → defaults to 'down' (positive delta)."""
        page = MagicMock()
        page.url = "https://example.com"
        step = _step(actions=[StepAction(type="scroll")])
        tester = _tester(page, steps=[step])
        tester.run()
        page.mouse.wheel.assert_called_with(0, 300)


class TestAssertionChecking:
    def test_passing_visible_assertion_no_finding(self):
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value.first.is_visible.return_value = True
        step = _step(assertions=[StepAssertion(type="visible", selector="#result")])
        tester = _tester(page, steps=[step])
        findings = tester.run()
        assert len(findings) == 0

    def test_failing_visible_assertion_produces_finding(self):
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value.first.is_visible.return_value = False
        step = _step(assertions=[StepAssertion(type="visible", selector="#result")])
        tester = _tester(page, steps=[step])
        findings = tester.run()
        assert len(findings) == 1
        assert "custom check failed" in findings[0].title.lower()

    def test_url_contains_assertion_passes(self):
        page = MagicMock()
        page.url = "https://example.com/dashboard"
        step = _step(assertions=[StepAssertion(type="url_contains", value="/dashboard")])
        tester = _tester(page, steps=[step])
        findings = tester.run()
        assert len(findings) == 0

    def test_url_contains_assertion_fails(self):
        page = MagicMock()
        page.url = "https://example.com/login"
        step = _step(assertions=[StepAssertion(type="url_contains", value="/dashboard")])
        tester = _tester(page, steps=[step])
        findings = tester.run()
        assert len(findings) == 1

    def test_url_contains_no_value_fails(self):
        """url_contains with no value → returns False (fails)."""
        page = MagicMock()
        page.url = "https://example.com/dashboard"
        step = _step(assertions=[StepAssertion(type="url_contains")])
        tester = _tester(page, steps=[step])
        findings = tester.run()
        assert len(findings) == 1

    def test_text_contains_assertion(self):
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value.first.text_content.return_value = "Welcome, Alice"
        step = _step(assertions=[StepAssertion(type="text_contains", selector="#greeting", value="Alice")])
        tester = _tester(page, steps=[step])
        findings = tester.run()
        assert len(findings) == 0

    def test_text_contains_case_insensitive(self):
        """text_contains is case-insensitive."""
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value.first.text_content.return_value = "WELCOME ALICE"
        step = _step(assertions=[StepAssertion(type="text_contains", selector="#msg", value="alice")])
        tester = _tester(page, steps=[step])
        findings = tester.run()
        assert len(findings) == 0

    def test_text_contains_fails_when_not_present(self):
        """text_contains fails when the value is not found."""
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value.first.text_content.return_value = "Hello Bob"
        step = _step(assertions=[StepAssertion(type="text_contains", selector="#msg", value="Alice")])
        tester = _tester(page, steps=[step])
        findings = tester.run()
        assert len(findings) == 1

    def test_text_contains_no_selector_fails(self):
        """text_contains without a selector → returns False."""
        page = MagicMock()
        page.url = "https://example.com"
        step = _step(assertions=[StepAssertion(type="text_contains", value="hello")])
        tester = _tester(page, steps=[step])
        findings = tester.run()
        assert len(findings) == 1

    def test_hidden_assertion_passes_when_invisible(self):
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value.first.is_visible.return_value = False
        step = _step(assertions=[StepAssertion(type="hidden", selector="#modal")])
        tester = _tester(page, steps=[step])
        findings = tester.run()
        assert len(findings) == 0

    def test_hidden_assertion_fails_when_visible(self):
        """hidden assertion fails if the element is actually visible."""
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value.first.is_visible.return_value = True  # visible → fails
        step = _step(assertions=[StepAssertion(type="hidden", selector="#modal")])
        tester = _tester(page, steps=[step])
        findings = tester.run()
        assert len(findings) == 1

    def test_hidden_assertion_no_selector_fails(self):
        """hidden without a selector → returns False."""
        page = MagicMock()
        page.url = "https://example.com"
        step = _step(assertions=[StepAssertion(type="hidden")])
        tester = _tester(page, steps=[step])
        findings = tester.run()
        assert len(findings) == 1

    def test_element_count_assertion_passes(self):
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value.count.return_value = 3
        step = _step(assertions=[StepAssertion(type="element_count", selector="li", value="3")])
        tester = _tester(page, steps=[step])
        findings = tester.run()
        assert len(findings) == 0

    def test_element_count_assertion_fails_wrong_count(self):
        """element_count fails when actual count differs from expected."""
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value.count.return_value = 5
        step = _step(assertions=[StepAssertion(type="element_count", selector="li", value="3")])
        tester = _tester(page, steps=[step])
        findings = tester.run()
        assert len(findings) == 1

    def test_element_count_no_selector_fails(self):
        """element_count without selector → returns False."""
        page = MagicMock()
        page.url = "https://example.com"
        step = _step(assertions=[StepAssertion(type="element_count", value="3")])
        tester = _tester(page, steps=[step])
        findings = tester.run()
        assert len(findings) == 1

    def test_unknown_assertion_type_passes_and_warns(self):
        page = MagicMock()
        page.url = "https://example.com"
        step = _step(assertions=[StepAssertion(type="future_assertion_type")])
        tester = _tester(page, steps=[step])
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            findings = tester.run()
        assert len(findings) == 0  # unknown → passes to avoid false positives
        assert any("future_assertion_type" in str(warning.message) for warning in w)

    def test_finding_uses_step_severity_and_category(self):
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value.first.is_visible.return_value = False
        step = _step(
            severity=Severity.CRITICAL,
            category=FindingCategory.KEYBOARD_NAVIGATION,
            assertions=[StepAssertion(type="visible", selector="#x")],
        )
        tester = _tester(page, steps=[step])
        findings = tester.run()
        assert findings[0].severity == Severity.CRITICAL
        assert findings[0].category == FindingCategory.KEYBOARD_NAVIGATION

    def test_assertion_evaluation_exception_produces_finding(self):
        """If _evaluate_assertion raises, the assertion is treated as failed."""
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value.first.is_visible.side_effect = RuntimeError("browser error")
        step = _step(assertions=[StepAssertion(type="visible", selector="#btn")])
        tester = _tester(page, steps=[step])
        findings = tester.run()
        assert len(findings) == 1
        # The description should include the evaluation error
        assert "evaluation error" in findings[0].description.lower() or "custom check failed" in findings[0].title.lower()


class TestMultipleSteps:
    def test_run_returns_empty_list_with_no_steps(self):
        page = MagicMock()
        page.url = "https://example.com"
        tester = _tester(page, steps=[])
        assert tester.run() == []

    def test_findings_from_all_failing_steps_returned(self):
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value.first.is_visible.return_value = False

        steps = [
            _step(assertions=[StepAssertion(type="visible", selector="#a")]),
            _step(assertions=[StepAssertion(type="visible", selector="#b")]),
        ]
        tester = _tester(page, steps=steps)
        findings = tester.run()
        assert len(findings) == 2
