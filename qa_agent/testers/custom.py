"""Custom tester that executes AI-generated test steps from a TestPlan."""

import warnings

from playwright.sync_api import Page

from ..config import TestConfig
from ..models import CustomStep, Finding, StepAction, StepAssertion, TestPlan
from .base import BaseTester


class CustomTester(BaseTester):
    """Executes the :class:`~qa_agent.models.CustomStep` entries in a :class:`~qa_agent.models.TestPlan`.

    Each step consists of a sequence of *actions* (navigation, clicks, form
    fills, etc.) followed by *assertions*.  A failed assertion produces a
    :class:`~qa_agent.models.Finding` with the severity and category specified
    in the step.

    Navigation actions are restored after each step so the page is in a known
    state for subsequent steps and for the standard testers that follow.
    """

    def __init__(self, page: Page, config: TestConfig, test_plan: TestPlan) -> None:
        super().__init__(page, config)
        self.test_plan = test_plan

    # ------------------------------------------------------------------
    # BaseTester interface
    # ------------------------------------------------------------------

    def run(self) -> list[Finding]:
        """Execute all custom steps and return any findings."""
        self.findings = []

        for step in self.test_plan.custom_steps:
            self._execute_step(step)

        return self.findings

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------

    def _execute_step(self, step: CustomStep) -> None:
        """Execute one step: run all actions, then check all assertions.

        The page URL is restored after the step completes so that navigate
        actions don't corrupt the state for subsequent steps.  If any action
        raises, a Finding is recorded and the rest of the step is skipped.
        """
        original_url = self.page.url
        action_log: list[str] = []

        for action in step.actions:
            try:
                log_line = self._execute_action(action)
                action_log.append(log_line)
            except Exception as exc:
                msg = f"{action.type} action failed: {exc}"
                action_log.append(msg)
                self.findings.append(
                    Finding(
                        title=f"Custom step action failed: {step.description}",
                        description=msg,
                        category=step.category,
                        severity=step.severity,
                        url=self.page.url,
                        steps_to_reproduce=action_log,
                        expected_behavior=action.description or f"Action '{action.type}' should succeed",
                        actual_behavior=msg,
                        screenshot_path=self._take_screenshot("custom_action_failure"),
                    )
                )
                return  # Abort — assertions would run on broken state

        for assertion in step.assertions:
            finding = self._check_assertion(assertion, step, action_log)
            if finding:
                self.findings.append(finding)

        # Best-effort restore: navigate back if actions moved us to a different URL
        if self.page.url != original_url:
            try:
                self.page.goto(original_url, wait_until="domcontentloaded")
                self.page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

    def _execute_action(self, action: StepAction) -> str:
        """Perform one action.  Returns a description string; raises on failure."""
        if action.type == "click":
            if action.selector:
                self.page.locator(action.selector).first.click(timeout=5000)
            return f"Clicked '{action.selector}'"

        if action.type == "fill":
            if action.selector and action.value is not None:
                self.page.locator(action.selector).first.fill(action.value, timeout=5000)
            return f"Filled '{action.selector}' with '{action.value}'"

        if action.type == "hover":
            if action.selector:
                self.page.locator(action.selector).first.hover(timeout=5000)
            return f"Hovered over '{action.selector}'"

        if action.type == "press_key":
            key = action.value or ""
            if action.selector:
                self.page.locator(action.selector).first.press(key, timeout=5000)
            else:
                self.page.keyboard.press(key)
            return f"Pressed key '{key}'"

        if action.type == "wait":
            ms = int(action.value) if action.value and action.value.isdigit() else 1000
            self.page.wait_for_timeout(ms)
            return f"Waited {ms}ms"

        if action.type == "navigate":
            if action.value:
                self.page.goto(action.value, wait_until="domcontentloaded")
                self.page.wait_for_load_state("networkidle", timeout=10000)
            return f"Navigated to '{action.value}'"

        if action.type == "scroll":
            if action.selector:
                self.page.locator(action.selector).first.scroll_into_view_if_needed(timeout=5000)
                return f"Scrolled '{action.selector}' into view"
            direction = action.value or "down"
            delta = 300 if direction != "up" else -300
            self.page.mouse.wheel(0, delta)
            return f"Scrolled page {direction}"

        # Unknown action type — warn but don't raise so the step can continue
        warnings.warn(f"Unknown custom action type '{action.type}' — skipped", stacklevel=2)
        return f"Unknown action type '{action.type}' (skipped)"

    # ------------------------------------------------------------------
    # Assertion checking
    # ------------------------------------------------------------------

    def _check_assertion(
        self,
        assertion: StepAssertion,
        step: CustomStep,
        action_log: list[str],
    ) -> Finding | None:
        """Evaluate one assertion.  Returns a Finding only when it *fails*."""
        try:
            passed = self._evaluate_assertion(assertion)
        except Exception as exc:
            passed = False
            assertion = StepAssertion(
                type=assertion.type,
                selector=assertion.selector,
                value=assertion.value,
                description=f"{assertion.description or assertion.type} — evaluation error: {exc}",
            )

        if passed:
            return None

        parts = [f"Assertion '{assertion.type}' failed"]
        if assertion.selector:
            parts.append(f"for selector '{assertion.selector}'")
        if assertion.value:
            parts.append(f"(expected: '{assertion.value}')")
        failure_msg = " ".join(parts)

        return Finding(
            title=f"Custom check failed: {step.description}",
            description=assertion.description or failure_msg,
            category=step.category,
            severity=step.severity,
            url=self.page.url,  # live URL at finding creation — accurate after any navigate
            steps_to_reproduce=action_log,
            expected_behavior=assertion.description or f"Assertion '{assertion.type}' should pass",
            actual_behavior=failure_msg,
            screenshot_path=self._take_screenshot("custom_step_failure"),
        )

    def _evaluate_assertion(self, assertion: StepAssertion) -> bool:
        """Return True if the assertion passes, False otherwise."""
        atype = assertion.type

        if atype == "visible":
            if not assertion.selector:
                return False
            return self.page.locator(assertion.selector).first.is_visible()

        if atype == "hidden":
            if not assertion.selector:
                return False
            return not self.page.locator(assertion.selector).first.is_visible()

        if atype == "text_contains":
            if not assertion.selector or not assertion.value:
                return False
            text = self.page.locator(assertion.selector).first.text_content() or ""
            return assertion.value.lower() in text.lower()

        if atype == "url_contains":
            if not assertion.value:
                return False
            return assertion.value.lower() in self.page.url.lower()

        if atype == "element_count":
            if not assertion.selector or not assertion.value:
                return False
            count = self.page.locator(assertion.selector).count()
            return str(count) == assertion.value

        # Unknown assertion type: warn and pass to avoid false positives from typos
        warnings.warn(
            f"Unknown custom assertion type '{atype}' — treating as passed. "
            "Check your test plan for unsupported assertion types.",
            stacklevel=2,
        )
        return True
