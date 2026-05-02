# API Reference

This document covers the programmatic (Python) API for embedding QA Agent in your own code.

---

## Quick Start

```python
from qa_agent import QAAgent, TestConfig, TestMode, OutputFormat
from qa_agent.llm_client import LLMProvider

config = TestConfig(
    urls=["https://example.com"],
    mode=TestMode.EXPLORE,
    output_formats=[OutputFormat.CONSOLE, OutputFormat.JSON],
    max_depth=2,
    max_pages=10,
)

agent = QAAgent(config)
session = agent.run()

print(f"Pages tested:   {len(session.pages_tested)}")
print(f"Total findings: {session.total_findings}")

for finding in session.get_all_findings():
    print(f"  [{finding.severity.value.upper()}] {finding.title}")
```

---

## Core Classes

### `QAAgent`

The main orchestrator class. Accepts a `TestConfig` and runs the full test suite.

```python
from qa_agent import QAAgent

agent = QAAgent(config)
session = agent.run()
```

#### Methods

| Method | Returns | Description |
|---|---|---|
| `run()` | `TestSession` | Executes all tests and returns a session object |

### `TestConfig`

Configuration dataclass controlling all aspects of a test run.

```python
from qa_agent import TestConfig, TestMode, OutputFormat

config = TestConfig(
    urls=["https://example.com"],
    mode=TestMode.FOCUSED,
    output_formats=[OutputFormat.CONSOLE, OutputFormat.JSON],
    output_dir="./output",
    max_depth=3,
    max_pages=100,
    max_interactions=50,
    screenshots=False,
    screenshots_all=False,
    full_page_screenshots=False,
    recording=False,
    headless=True,
    viewport_width=1280,
    viewport_height=720,
    timeout=30000,
    allow_external=False,
    ignore_patterns=[],
    test_keyboard=True,
    test_mouse=True,
    test_forms=True,
    test_accessibility=True,
    test_errors=True,
    test_wcag_compliance=False,
    instructions=None,
    llm_provider=LLMProvider.ANTHROPIC,
    ai_model=None,
    no_cache=False,
    auth=None,
    auth_file=None,
    cookies_file=None,
    headers=[],
)
```

#### Key Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `urls` | `list[str]` | required | URLs to test |
| `mode` | `TestMode` | `TestMode.FOCUSED` | `FOCUSED` or `EXPLORE` |
| `output_formats` | `list[OutputFormat]` | `[CONSOLE, MARKDOWN]` | Output formats to generate |
| `output_dir` | `str` | `"./output"` | Directory for reports and artifacts |
| `max_depth` | `int` | `3` | Max link crawl depth (explore mode) |
| `max_pages` | `int` | `100` | Max pages to test |
| `max_interactions` | `int` | `50` | Max interactions per page |
| `screenshots` | `bool` | `False` | Screenshot on errors |
| `screenshots_all` | `bool` | `False` | Screenshot every interaction |
| `full_page_screenshots` | `bool` | `False` | Full-page captures |
| `recording` | `bool` | `False` | Record session video |
| `headless` | `bool` | `True` | Run browser headless |
| `viewport_width` | `int` | `1280` | Browser viewport width |
| `viewport_height` | `int` | `720` | Browser viewport height |
| `timeout` | `int` | `30000` | Action timeout (ms) |
| `allow_external` | `bool` | `False` | Follow external domain links |
| `ignore_patterns` | `list[str]` | `[]` | URL regex patterns to skip |
| `test_keyboard` | `bool` | `True` | Enable keyboard tests |
| `test_mouse` | `bool` | `True` | Enable mouse tests |
| `test_forms` | `bool` | `True` | Enable form tests |
| `test_accessibility` | `bool` | `True` | Enable accessibility tests |
| `test_errors` | `bool` | `True` | Enable error detection |
| `test_wcag_compliance` | `bool` | `False` | Enable WCAG 2.1 AA compliance |
| `instructions` | `str \| None` | `None` | Natural-language test instructions |
| `llm_provider` | `LLMProvider` | `LLMProvider.ANTHROPIC` | LLM provider for agentic testing |
| `ai_model` | `str \| None` | `None` | Model override (uses provider default) |
| `no_cache` | `bool` | `False` | Bypass plan cache |
| `auth` | `str \| None` | `None` | Auth string (`user:pass@url`) |
| `auth_file` | `str \| None` | `None` | Path to auth JSON file |
| `cookies_file` | `str \| None` | `None` | Path to cookies JSON file |
| `headers` | `list[str]` | `[]` | Custom headers (`Key: Value`) |

### `TestSession`

The result object returned by `QAAgent.run()`.

```python
session = agent.run()
```

#### Properties

| Property | Type | Description |
|---|---|---|
| `session_id` | `str` | Unique session identifier |
| `start_time` | `datetime` | When the session started |
| `end_time` | `datetime \| None` | When the session ended |
| `pages_tested` | `list[PageAnalysis]` | Pages that were tested |
| `total_findings` | `int` | Total number of findings |
| `findings_by_severity` | `dict[str, int]` | Findings grouped by severity |

#### Methods

| Method | Returns | Description |
|---|---|---|
| `get_all_findings()` | `list[Finding]` | All findings across all pages |
| `get_findings_by_severity(severity)` | `list[Finding]` | Findings filtered by severity |
| `get_findings_by_page(url)` | `list[Finding]` | Findings for a specific page |

### `Finding`

A single issue detected during testing.

```python
from qa_agent.models import Finding, Severity

finding = Finding(
    severity=Severity.MEDIUM,
    title="Missing alt text on image",
    url="https://example.com",
    description="An img element lacks an alt attribute",
    element="<img src='logo.png'>",
    wcag_criterion="1.1.1",
)
```

#### Fields

| Field | Type | Description |
|---|---|---|
| `severity` | `Severity` | Severity level |
| `title` | `str` | Short description of the issue |
| `url` | `str` | URL where the issue was found |
| `description` | `str` | Detailed explanation |
| `element` | `str \| None` | HTML element involved (if applicable) |
| `wcag_criterion` | `str \| None` | WCAG criterion reference (if applicable) |

### `Severity`

Enum for finding severity levels.

```python
from qa_agent.models import Severity

Severity.CRITICAL   # Security issues, data loss
Severity.HIGH       # Major usability blockers
Severity.MEDIUM     # UX problems, accessibility issues
Severity.LOW        # Minor improvements, best practices
Severity.INFO       # Informational observations
```

### `TestMode`

Enum for test execution modes.

```python
from qa_agent import TestMode

TestMode.FOCUSED   # Test only the given URLs
TestMode.EXPLORE   # Crawl and discover pages
```

### `OutputFormat`

Enum for output format options.

```python
from qa_agent import OutputFormat

OutputFormat.CONSOLE    # Real-time colored terminal output
OutputFormat.MARKDOWN   # Markdown report
OutputFormat.JSON       # JSON report
OutputFormat.PDF        # PDF report (requires weasyprint)
```

### `LLMProvider`

Enum for LLM provider selection.

```python
from qa_agent.llm_client import LLMProvider

LLMProvider.ANTHROPIC   # Anthropic Claude (default)
LLMProvider.OPENAI      # OpenAI GPT-4o
```

---

## Reporters

Reporters can also be used directly if you have a `TestSession` and want to generate output in a specific format.

### Console Reporter

```python
from qa_agent.reporters.console import ConsoleReporter

reporter = ConsoleReporter()
reporter.generate(session)
```

### Markdown Reporter

```python
from qa_agent.reporters.markdown import MarkdownReporter

reporter = MarkdownReporter(output_dir="./reports")
reporter.generate(session)
```

### JSON Reporter

```python
from qa_agent.reporters.json_reporter import JSONReporter

reporter = JSONReporter(output_dir="./reports")
reporter.generate(session)
```

### PDF Reporter

```python
from qa_agent.reporters.pdf import PDFReporter

reporter = PDFReporter(output_dir="./reports")
reporter.generate(session)
```

---

## Testers

Individual testers can be instantiated and run manually if you need fine-grained control.

```python
from playwright.sync_api import sync_playwright
from qa_agent.testers.keyboard import KeyboardTester
from qa_agent.config import TestConfig

config = TestConfig(urls=["https://example.com"])

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page()
    page.goto("https://example.com")

    tester = KeyboardTester(page, config)
    findings = tester.run()

    for f in findings:
        print(f"[{f.severity.value}] {f.title}")

    browser.close()
```

### Available Testers

| Tester | Module | Description |
|---|---|---|
| `KeyboardTester` | `qa_agent.testers.keyboard` | Keyboard navigation and focus |
| `MouseTester` | `qa_agent.testers.mouse` | Mouse interaction and target sizes |
| `FormTester` | `qa_agent.testers.forms` | Form handling and validation |
| `AccessibilityTester` | `qa_agent.testers.accessibility` | WCAG accessibility checks |
| `WcagComplianceTester` | `qa_agent.testers.wcag_compliance` | WCAG 2.1 AA compliance audit |
| `ErrorTester` | `qa_agent.testers.errors` | Console and network error detection |
| `CustomTester` | `qa_agent.testers.custom` | AI-generated test steps |

---

## AI Planner

The AI planner generates test plans from natural-language instructions.

```python
from qa_agent.ai_planner import AIPlanner
from qa_agent.llm_client import LLMClient
from qa_agent.config import TestConfig

config = TestConfig(
    urls=["https://example.com/login"],
    instructions="The login button does nothing when email is blank",
)

llm = LLMClient(config.llm_provider, config.ai_model)
planner = AIPlanner(llm)

plan = planner.generate(config)
print(plan.summary)
print(plan.steps)
```

### Plan Caching

Plans are cached automatically. To bypass the cache:

```python
planner = AIPlanner(llm, use_cache=False)
```

---

## Error Handling

QA Agent handles errors gracefully at multiple levels:

- **Individual test failures** are caught and reported as findings
- **Page navigation failures** skip the page and continue
- **LLM API failures** print a warning and continue with standard tests only
- **Reporter failures** are caught and logged without stopping other reporters

To handle errors in your own code:

```python
try:
    session = agent.run()
except Exception as e:
    print(f"Test run failed: {e}")
```
