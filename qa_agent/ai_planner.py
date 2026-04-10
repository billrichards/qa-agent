"""AI-powered test planner that interprets natural language instructions.

Given a natural language description (feature spec, bug report, or general
testing guidance), this module calls the Claude API and returns a structured
``TestPlan`` that the agent will execute alongside its standard test suite.
"""

import json
import time

from .models import (
    CustomStep,
    FindingCategory,
    Severity,
    StepAction,
    StepAssertion,
    TestPlan,
)

_SYSTEM_PROMPT = """You are an expert QA test planner for web applications.

You will be given:
1. A target URL being tested
2. Natural language instructions — a feature description, bug report, or testing guidance

Your job is to generate a structured test plan that a Playwright-based QA agent will execute.

The agent already runs standard tests for:
- Keyboard navigation (tab order, focus visibility, keyboard traps)
- Mouse interactions (click targets, hover states, WCAG 2.5.5 minimum target size)
- Form handling (validation, error messages, label associations)
- Accessibility (alt text, heading structure, color contrast, ARIA attributes)
- Console and network errors

Your test plan should focus on CUSTOM scenarios specific to the provided instructions:
targeted user flows, specific feature behaviors, regression scenarios for bug reports,
or edge cases mentioned in the instructions.

Guidelines for writing good test steps:
- Use resilient CSS selectors: prefer [data-testid], [name="..."], [role="..."], #id
  over brittle descendant paths
- Keep actions short and sequential; each step tests one scenario
- Assertions should reflect exactly what the instructions say should (or should not) happen
- Assign severity based on impact: "critical" for auth/data-loss flows, "high" for broken
  core features, "medium" for degraded UX, "low" for cosmetic issues, "info" for
  informational observations
- Leave suggested_urls empty. The URLs to test are provided by the user; do not construct
  or guess URLs. All navigation must happen through browser interactions (clicks, form
  submissions, keyboard) — never by constructing a URL and navigating directly to it.

Return ONLY valid JSON matching the schema — no markdown, no commentary."""


_TEST_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "One or two sentences describing what this test plan covers.",
        },
        "focus_areas": {
            "type": "array",
            "items": {"type": "string"},
            "description": "High-level areas of the application to focus on (e.g. 'login flow', 'checkout form').",
        },
        "custom_steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Human-readable description of what this step tests.",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["info", "low", "medium", "high", "critical"],
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "keyboard_navigation",
                            "mouse_interaction",
                            "form_handling",
                            "accessibility",
                            "console_error",
                            "network_error",
                            "visual_issue",
                            "performance",
                            "unexpected_behavior",
                        ],
                    },
                    "actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": [
                                        "click",
                                        "fill",
                                        "hover",
                                        "press_key",
                                        "wait",
                                        "scroll",
                                    ],
                                },
                                "selector": {
                                    "type": "string",
                                    "description": "CSS selector for the target element.",
                                },
                                "value": {
                                    "type": "string",
                                    "description": (
                                        "For 'fill': text to type. "
                                        "For 'press_key': key name (e.g. 'Enter', 'Tab'). "
                                        "For 'wait': milliseconds as a string. "
                                        "For 'scroll': 'down' or 'up'."
                                    ),
                                },
                                "description": {"type": "string"},
                            },
                            "required": ["type"],
                            "additionalProperties": False,
                        },
                    },
                    "assertions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": [
                                        "visible",
                                        "hidden",
                                        "text_contains",
                                        "url_contains",
                                        "element_count",
                                    ],
                                },
                                "selector": {
                                    "type": "string",
                                    "description": "CSS selector of the element to assert on.",
                                },
                                "value": {
                                    "type": "string",
                                    "description": (
                                        "For 'text_contains': expected substring. "
                                        "For 'url_contains': expected URL fragment. "
                                        "For 'element_count': expected count as a string."
                                    ),
                                },
                                "description": {
                                    "type": "string",
                                    "description": "What passing this assertion proves.",
                                },
                            },
                            "required": ["type"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["description", "severity", "category", "actions", "assertions"],
                "additionalProperties": False,
            },
        },
        "suggested_urls": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Always return an empty array. URLs are provided by the user; do not construct or guess any URLs.",
        },
        "notes": {
            "type": "string",
            "description": "Any extra context, caveats, or observations for the tester.",
        },
    },
    "required": ["summary", "focus_areas", "custom_steps", "suggested_urls", "notes"],
    "additionalProperties": False,
}


# Errors that are safe to retry (transient — not a bug in our request)
_RETRYABLE_ERRORS: tuple = ()  # populated lazily after anthropic is imported

# How long to wait before each retry attempt (seconds)
_RETRY_DELAYS = (2, 5)   # up to 3 attempts total: initial + 2 retries

# Timeout for a single messages.create() call (seconds)
_API_TIMEOUT = 60

# Max characters of raw API response to include in error messages
_MAX_RAW_RESPONSE_IN_ERROR = 300

# Required top-level keys in the JSON returned by the model
_REQUIRED_KEYS = frozenset({"summary", "focus_areas", "custom_steps"})


_SEVERITY_MAP: dict[str, Severity] = {
    "info": Severity.INFO,
    "low": Severity.LOW,
    "medium": Severity.MEDIUM,
    "high": Severity.HIGH,
    "critical": Severity.CRITICAL,
}

_CATEGORY_MAP: dict[str, FindingCategory] = {
    "keyboard_navigation": FindingCategory.KEYBOARD_NAVIGATION,
    "mouse_interaction": FindingCategory.MOUSE_INTERACTION,
    "form_handling": FindingCategory.FORM_HANDLING,
    "accessibility": FindingCategory.ACCESSIBILITY,
    "console_error": FindingCategory.CONSOLE_ERROR,
    "network_error": FindingCategory.NETWORK_ERROR,
    "visual_issue": FindingCategory.VISUAL_ISSUE,
    "performance": FindingCategory.PERFORMANCE,
    "unexpected_behavior": FindingCategory.UNEXPECTED_BEHAVIOR,
}


class AIPlannerClient:
    """Calls the Claude API to turn natural language instructions into a ``TestPlan``."""

    def __init__(self, model: str = "claude-sonnet-4-6") -> None:
        self.model = model
        self.__anthropic_client = None

    @property  # type: ignore[override]
    def _client(self):
        if self.__anthropic_client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise ImportError(
                    "The 'anthropic' package is required for AI planning. "
                    "Install it with: pip install 'qa-agent[ai]'"
                ) from exc
            self.__anthropic_client = anthropic.Anthropic()
        return self.__anthropic_client

    @_client.setter
    def _client(self, value) -> None:
        self.__anthropic_client = value

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def plan(self, instructions: str, base_url: str) -> TestPlan:
        """Generate a :class:`TestPlan` from natural language instructions.

        Args:
            instructions: A feature description, bug report, or testing guidance.
            base_url: The primary URL under test (gives Claude context).

        Returns:
            A structured :class:`TestPlan` ready for :class:`CustomTester`.

        Raises:
            anthropic.APIError: Propagated after all retries are exhausted.
            ValueError: If the response cannot be parsed into a valid plan.
        """
        user_message = (
            f"Target URL: {base_url}\n\n"
            f"Instructions:\n{instructions}\n\n"
            "Generate a test plan as a JSON object."
        )

        response = self._call_with_retry(user_message)

        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            raise ValueError("Claude returned no text content for the test plan request.")

        data = self._parse_json(text)
        return self._parse_plan(data)

    def _call_with_retry(self, user_message: str):
        """Call messages.create with timeout and exponential-backoff retry.

        Retries on transient errors: rate limits, overload (529), connection
        errors, and timeouts. Non-retryable errors (auth, bad request, etc.)
        are re-raised immediately.
        """
        import anthropic

        global _RETRYABLE_ERRORS
        if not _RETRYABLE_ERRORS:
            _RETRYABLE_ERRORS = (
                anthropic.RateLimitError,
                anthropic.InternalServerError,  # includes 529 overload
                anthropic.APIConnectionError,
                anthropic.APITimeoutError,
            )

        last_exc: Exception | None = None
        attempts = 1 + len(_RETRY_DELAYS)

        for attempt, delay in enumerate(
            [None] + list(_RETRY_DELAYS),  # None = no pre-sleep on first attempt
            start=1,
        ):
            if delay is not None:
                time.sleep(delay)
            try:
                return self._client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_message}],
                    timeout=_API_TIMEOUT,
                )
            except _RETRYABLE_ERRORS as exc:
                last_exc = exc
                if attempt < attempts:
                    continue
            except Exception:
                raise  # non-retryable — surface immediately

        raise last_exc  # type: ignore[misc]

    def _parse_json(self, text: str) -> dict:
        """Strip optional markdown fences and parse JSON, with a clean error on failure."""
        # Some models wrap the JSON in markdown code fences despite instructions not to.
        stripped = text.strip()
        if stripped.startswith("```"):
            # Remove the opening fence line (```json or just ```)
            stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
            # Remove the closing fence
            closing = stripped.rfind("```")
            if closing != -1:
                stripped = stripped[:closing]
            stripped = stripped.strip()

        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            preview = text[:_MAX_RAW_RESPONSE_IN_ERROR]
            suffix = "…" if len(text) > _MAX_RAW_RESPONSE_IN_ERROR else ""
            raise ValueError(
                f"Claude returned invalid JSON: {exc}\n\nResponse preview:\n{preview}{suffix}"
            ) from exc

        if not isinstance(data, dict):
            raise ValueError(f"Claude returned JSON but not an object (got {type(data).__name__}).")

        missing = _REQUIRED_KEYS - data.keys()
        if missing:
            preview = text[:_MAX_RAW_RESPONSE_IN_ERROR]
            suffix = "…" if len(text) > _MAX_RAW_RESPONSE_IN_ERROR else ""
            raise ValueError(
                f"Claude response is missing required fields: {sorted(missing)}. "
                f"The model may have returned a different schema.\n\nResponse preview:\n{preview}{suffix}"
            )

        return data

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_plan(self, data: dict) -> TestPlan:
        custom_steps: list[CustomStep] = []

        for step_data in data.get("custom_steps", []):
            actions = [
                StepAction(
                    type=a["type"],
                    selector=a.get("selector"),
                    value=a.get("value"),
                    description=a.get("description"),
                )
                for a in step_data.get("actions", [])
            ]
            assertions = [
                StepAssertion(
                    type=a["type"],
                    selector=a.get("selector"),
                    value=a.get("value"),
                    description=a.get("description"),
                )
                for a in step_data.get("assertions", [])
            ]
            severity = _SEVERITY_MAP.get(step_data.get("severity", "medium"), Severity.MEDIUM)
            category = _CATEGORY_MAP.get(
                step_data.get("category", "unexpected_behavior"),
                FindingCategory.UNEXPECTED_BEHAVIOR,
            )
            custom_steps.append(
                CustomStep(
                    description=step_data.get("description", ""),
                    actions=actions,
                    assertions=assertions,
                    severity=severity,
                    category=category,
                )
            )

        return TestPlan(
            summary=data.get("summary", ""),
            focus_areas=data.get("focus_areas", []),
            custom_steps=custom_steps,
            suggested_urls=[],  # Never trust AI-constructed URLs; user supplies all URLs
            notes=data.get("notes", ""),
        )
