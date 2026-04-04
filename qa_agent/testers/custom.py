"""Custom tester that executes AI-generated test steps from a TestPlan."""

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
        url = self.page.url

        for step in self.test_plan.custom_steps:
            self._execute_step(step, url)

        return self.findings

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------

    def _execute_step(self, step: CustomStep, url: str) -> None:
        action_log: list[str] = []

        for action in step.actions:
            description = self._execute_action(action)
            if description:
                action_log.append(description)

        for assertion in step.assertions:
            finding = self._check_assertion(assertion, step, url, action_log)
            if finding:
                self.findings.append(finding)

    def _execute_action(self, action: StepAction) -> str:
        """Perform one action.  Returns a human-readable log line (always)."""
        try:
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
                    self.page.locator(action.selector).first.scroll_into_view_if_needed(
                        timeout=5000
                    )
                    return f"Scrolled '{action.selector}' into view"
                direction = action.value or "down"
                delta = 300 if direction != "up" else -300
                self.page.mouse.wheel(0, delta)
                return f"Scrolled page {direction}"

        except Exception as exc:
            return f"{action.type} on '{action.selector}' failed: {exc}"

        return f"Unknown action type '{action.type}' (skipped)"

    # ------------------------------------------------------------------
    # Assertion checking
    # ------------------------------------------------------------------

    def _check_assertion(
        self,
        assertion: StepAssertion,
        step: CustomStep,
        url: str,
        action_log: list[str],
    ) -> Finding | None:
        """Evaluate one assertion.  Returns a Finding only when it *fails*."""
        try:
            passed = self._evaluate_assertion(assertion)
        except Exception as exc:
            passed = False
            # Embed the exception in the finding description
            assertion = StepAssertion(
                type=assertion.type,
                selector=assertion.selector,
                value=assertion.value,
                description=f"{assertion.description or assertion.type} — evaluation error: {exc}",
            )

        if passed:
            return None

        # Build a human-readable failure message
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
            url=url,
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

        # Unknown assertion type: pass silently to avoid false positives
        return True
