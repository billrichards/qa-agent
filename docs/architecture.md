# Architecture

This document describes QA Agent's internal structure and explains how to extend it with custom testers.

---

## Module Map

```
qa_agent/
├── cli.py                   # CLI entry point
├── agent.py                 # Core orchestrator
├── config.py                # Configuration dataclasses
├── models.py                # Finding, PageAnalysis, TestSession, TestPlan
├── llm_client.py            # Anthropic & OpenAI clients via stdlib urllib
├── ai_planner.py            # LLM-powered test plan generation
├── plan_cache.py            # Filesystem cache for test plans
├── testers/
│   ├── base.py              # BaseTester abstract class
│   ├── keyboard.py          # Keyboard navigation
│   ├── mouse.py             # Mouse interaction
│   ├── forms.py             # Form handling
│   ├── accessibility.py     # WCAG accessibility
│   ├── wcag_compliance.py   # WCAG 2.1 AA compliance (opt-in)
│   ├── errors.py            # Console & network errors
│   └── custom.py            # AI-generated test steps
├── reporters/
│   ├── console.py           # Colored terminal output
│   ├── markdown.py          # Markdown report
│   ├── json_reporter.py     # JSON report
│   └── pdf.py               # PDF report (requires weasyprint)
└── web/
    ├── server.py             # Flask app with SSE streaming
    ├── templates/            # Jinja2 templates
    └── static/               # CSS and JavaScript
```

---

## Request Flow

1. **Entry** — [`cli.py`](https://github.com/billrichards/qa-agent/blob/main/qa_agent/cli.py) parses arguments and builds a [`TestConfig`](https://github.com/billrichards/qa-agent/blob/main/qa_agent/config.py).
2. **Planning** — If `--instructions` is provided, [`ai_planner.py`](https://github.com/billrichards/qa-agent/blob/main/qa_agent/ai_planner.py) calls the LLM via [`llm_client.py`](https://github.com/billrichards/qa-agent/blob/main/qa_agent/llm_client.py) to generate a `TestPlan`. Plans are cached to disk by [`plan_cache.py`](https://github.com/billrichards/qa-agent/blob/main/qa_agent/plan_cache.py) (24-hour TTL).
3. **Orchestration** — [`agent.py`](https://github.com/billrichards/qa-agent/blob/main/qa_agent/agent.py) launches Playwright, iterates over target URLs (or crawls in explore mode), and calls each enabled tester on every page.
4. **Testing** — Each tester (see [Test Categories](https://github.com/billrichards/qa-agent/blob/main/docs/test-categories.md)) receives the Playwright `Page` and returns a `list[Finding]`.
5. **Reporting** — Reporters in [`reporters/`](https://github.com/billrichards/qa-agent/tree/main/qa_agent/reporters/) consume the `TestSession` and write output in the requested formats.

---

## Adding a Custom Tester

### 1. Create the tester module

Add a file in [`testers/`](https://github.com/billrichards/qa-agent/tree/main/qa_agent/testers/) that extends [`BaseTester`](https://github.com/billrichards/qa-agent/blob/main/qa_agent/testers/base.py):

```python
# qa_agent/testers/my_tester.py
from playwright.sync_api import Page

from ..config import TestConfig
from ..models import Finding, FindingCategory, Severity
from .base import BaseTester


class MyTester(BaseTester):
    """Describe what this tester checks."""

    def run(self) -> list[Finding]:
        findings: list[Finding] = []

        # Use self.page (Playwright Page) and self.config (TestConfig)
        # to perform checks. Append Finding objects for each issue.

        return findings
```

[`BaseTester`](https://github.com/billrichards/qa-agent/blob/main/qa_agent/testers/base.py) provides:

| Member | Purpose |
|---|---|
| `self.page` | The Playwright [`Page`](https://playwright.dev/python/docs/api/class-page) under test |
| `self.config` | The active [`TestConfig`](https://github.com/billrichards/qa-agent/blob/main/qa_agent/config.py) instance |
| `self.findings` | A convenience list (you can also return your own) |
| `_safe_execute()` | Wraps an action in a try/except and returns an error dict on failure |
| `_get_element_info()` | Returns visibility, text, and tag info for a CSS selector |
| `_take_screenshot()` | Captures a screenshot if the config allows it |

### 2. Export from the package

Add your class to [`testers/__init__.py`](https://github.com/billrichards/qa-agent/blob/main/qa_agent/testers/__init__.py):

```python
from .my_tester import MyTester

__all__ = [
    # …existing exports…
    "MyTester",
]
```

### 3. Add a config flag

In [`config.py`](https://github.com/billrichards/qa-agent/blob/main/qa_agent/config.py), add a boolean to [`TestConfig`](https://github.com/billrichards/qa-agent/blob/main/qa_agent/config.py#L56):

```python
@dataclass
class TestConfig:
    # …existing fields…
    test_my_feature: bool = True  # or False for opt-in
```

### 4. Wire it into the orchestrator

In [`agent.py`](https://github.com/billrichards/qa-agent/blob/main/qa_agent/agent.py), call your tester inside `_test_page()`:

```python
if self.config.test_my_feature:
    from .testers import MyTester
    tester = MyTester(page, self.config)
    findings.extend(tester.run())
```

### 5. (Optional) Add a CLI flag

In [`cli.py`](https://github.com/billrichards/qa-agent/blob/main/qa_agent/cli.py), add `--skip-my-feature` or `--my-feature` following the pattern of the existing suite flags.

---

## Severity Levels

| Level | When to use |
|---|---|
| `CRITICAL` | Security issues, data loss risks |
| `HIGH` | Major usability blockers |
| `MEDIUM` | UX problems, accessibility violations |
| `LOW` | Minor improvements, best-practice suggestions |
| `INFO` | Informational observations |

Defined in [`models.Severity`](https://github.com/billrichards/qa-agent/blob/main/qa_agent/models.py#L10).

---

## Finding Categories

Each finding is tagged with a [`FindingCategory`](https://github.com/billrichards/qa-agent/blob/main/qa_agent/models.py#L19):

`KEYBOARD_NAVIGATION` · `MOUSE_INTERACTION` · `FORM_HANDLING` · `ACCESSIBILITY` · `CONSOLE_ERROR` · `NETWORK_ERROR` · `VISUAL_ISSUE` · `PERFORMANCE` · `UNEXPECTED_BEHAVIOR`
