# QA Agent

Automated exploratory QA testing for web applications — powered by Playwright and, optionally, Claude.

<p align="center">
  <a href="https://github.com/billrichards/qa-agent/actions/workflows/test.yml"><img src="https://github.com/billrichards/qa-agent/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://pypi.org/project/qa-agent/"><img src="https://img.shields.io/pypi/v/qa-agent" alt="PyPI version"></a>
  <a href="https://pypi.org/project/qa-agent/"><img src="https://img.shields.io/pypi/pyversions/qa-agent" alt="Python versions"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/billrichards/qa-agent" alt="License"></a>
</p>

<p align="center">
  <img src="./docs/console-output-showing-a-test-run-in-progress.png" alt="Console output showing a test run in progress" width="700">
</p>

---

## Why QA Agent?

Most automated testing tools require you to write and maintain test scripts. QA Agent takes a different approach: point it at a URL and it **explores your application like a real user would** — clicking buttons, filling forms, navigating with the keyboard, and checking for accessibility issues — then reports what it finds.

Need targeted tests? Pass natural-language instructions (a bug report, a feature spec, a test plan) and Claude generates custom Playwright test steps that run alongside the standard suite. No test scripts to write or maintain.

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Agentic Testing](#agentic-testing)
- [Web Interface](#web-interface)
- [CLI Reference](#cli-reference)
- [Programmatic Usage](#programmatic-usage)
- [Test Categories](#test-categories)
- [Output Formats](#output-formats)
- [CI/CD Integration](#cicd-integration)
- [Architecture](#architecture)
- [Development](#development)
- [Contributing](#contributing)
- [Exit Codes](#exit-codes)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Features

| Category | What it does |
| --- | --- |
| **Agentic testing** | Give Claude a bug report or feature spec; it generates custom Playwright test steps automatically |
| **Two modes** | `focused` tests only given URLs; `explore` crawls and discovers additional pages |
| **Six test suites** | Keyboard nav · mouse interaction · form handling · accessibility (WCAG) · error detection (5 on by default) + WCAG 2.1 AA compliance (opt-in) |
| **Auth support** | Username/password, cookies, Bearer tokens, custom headers |
| **Four output formats** | Console, Markdown, JSON, PDF |
| **Screenshots & video** | On-error or every-interaction screenshots; full session video recording |
| **Web UI** | Browser-based dashboard for launching runs, watching live output, and browsing past sessions |
| **CI/CD ready** | Exit codes map to pass/fail; JSON output integrates with any pipeline |

---

## Installation

> **Requires Python 3.10 or newer.** Check with `python --version` before installing.

```bash
# Core install (standard testing only)
pip install qa-agent
playwright install chromium   # required — downloads browser binaries

# Agentic testing (adds Anthropic SDK for --instructions support)
pip install "qa-agent[ai]"

# PDF report support (adds WeasyPrint)
pip install "qa-agent[pdf]"

# Web UI support (adds Flask)
pip install "qa-agent[web]"

# Everything
pip install "qa-agent[all]"
playwright install chromium
```

**Core dependencies:** Python ≥ 3.10 · Playwright ≥ 1.40

> **Note:** `playwright install chromium` must be run once after every fresh install to download the browser binaries. See [Troubleshooting](#troubleshooting) if anything goes wrong.

**Agentic testing** (the `--instructions` flag) requires the `[ai]` extra and an Anthropic API key:

```bash
pip install "qa-agent[ai]"
export ANTHROPIC_API_KEY=sk-ant-...
```

---

## Quick Start

```bash
# Test a single URL
qa-agent https://example.com

# Test multiple URLs
qa-agent https://example.com https://example.com/about

# Crawl and test discovered pages (depth 2, up to 20 pages)
qa-agent --mode explore --max-depth 2 https://example.com

# Generate JSON + Markdown reports in a custom directory
qa-agent --output json,markdown --output-dir ./reports https://example.com
```

You can also run via `python -m qa_agent`:

```bash
python -m qa_agent https://example.com
python -m qa_agent --mode explore --max-pages 10 https://example.com
```

---

## Agentic Testing

Pass natural-language instructions and Claude generates custom test steps that run alongside the standard suite.

```bash
# From a bug report
qa-agent --instructions "The login button does nothing when email is blank — no validation error is shown" \
  https://example.com/login

# From a feature description
qa-agent --instructions "We added a 'Remember me' checkbox to the login form. \
  It should persist the session across browser restarts and be unchecked by default." \
  https://example.com/login

# From a file (for longer specs)
qa-agent --instructions-file feature-spec.txt https://example.com
```

### What happens

1. Before any browser testing, Claude receives your instructions and the target URL.
2. Claude returns a structured plan: summary, focus areas, custom Playwright test steps, and suggested URLs.
3. The agent prints the plan, then runs those custom steps on every tested page alongside the standard test suites.
4. Assertion failures become findings in the report with the severity and category Claude assigned.

If the API call fails, a warning is printed and the run continues with standard tests only.

### Model & caching

```bash
# Use a different model (default: claude-sonnet-4-6)
qa-agent --ai-model claude-opus-4-6 --instructions "Test checkout" https://shop.example.com

# Bypass the plan cache and always call the API
qa-agent --no-cache --instructions "..." https://example.com
```

Generated test plans are cached to `~/.qa_agent/cache/` by default (24-hour TTL). Rerunning with the same instructions and URLs reuses the cached plan. Pass `--no-cache` to force a fresh API call.

---

## Web Interface

<p align="center">
  <img src="./docs/web-UI-configuration-form.png" alt="Web interface configuration form" width="700">
</p>

A browser-based dashboard for configuring and monitoring runs.

```bash
# Start the server (opens at http://127.0.0.1:5000)
python -m qa_agent web
# or
qa-agent-web

# Custom host/port
qa-agent-web --host 0.0.0.0 --port 8080
```

**Capabilities:**

- Configuration form with all CLI options (collapsible sections)
- Real-time streaming output via Server-Sent Events
- Stop a running test mid-run
- Browse past sessions grouped by domain
- Session detail view: findings table, severity breakdown, screenshot gallery, report downloads

<p align="center">
  <img src="./docs/session-detail-view-showing-findings-table.png" alt="Session detail view showing findings table" width="700">
</p>

> **Security note:** The web interface has no authentication — intended for local or internal use only.

All output is written to `output/` in the project directory. CLI sessions are also visible in the web UI as long as JSON output format was used (JSON is always written by default).

---

## CLI Reference

```bash
qa-agent --version   # print installed version and exit
qa-agent --help      # show full option reference
```

### Modes

```bash
qa-agent --mode focused https://example.com   # default: test only given URLs
qa-agent --mode explore  https://example.com   # crawl and test discovered pages
```

### Exploration options (explore mode)

| Flag | Default | Description |
| --- | --- | --- |
| `--max-depth N` | `3` | Max link depth to follow |
| `--max-pages N` | `20` | Max pages to test |
| `--allow-external` | off | Follow links to other domains |
| `--ignore PATTERN` | — | Regex pattern(s) for URLs to skip (repeatable) |

### Authentication

```bash
# Username/password with login URL
qa-agent --auth "username:password@https://example.com/login" https://example.com/dashboard

# JSON auth file
qa-agent --auth-file auth.json https://example.com

# Pre-set cookies
qa-agent --cookies cookies.json https://example.com

# Custom header (repeatable)
qa-agent --header "Authorization: Bearer token123" https://example.com
```

**auth.json schema:**

```json
{
  "username": "testuser",
  "password": "testpass",
  "auth_url": "https://example.com/login",
  "username_selector": "input#email",
  "password_selector": "input#password",
  "submit_selector": "button[type=submit]"
}
```

### Output

```bash
# Formats: console, markdown, json, pdf (comma-separated, default: console,markdown)
qa-agent --output console,markdown,json,pdf https://example.com

# Custom output directory (default: <project-root>/output)
qa-agent --output-dir ./reports https://example.com
```

> **Note:** JSON output is always written regardless of `--output`, so sessions appear in the web UI.

Output is organized as `output/{domain}/{session_id}/qa_reports|screenshots|recordings`.

> PDF requires WeasyPrint. Install with `pip install "qa-agent[pdf]"`. Falls back to Markdown if not installed.

### Screenshots & recording

```bash
qa-agent --screenshots       https://example.com  # capture on errors
qa-agent --screenshots-all   https://example.com  # capture after every interaction
qa-agent --full-page         https://example.com  # full-page screenshots
qa-agent --record            https://example.com  # record session video
```

### Browser options

```bash
qa-agent --no-headless                  # visible browser window
qa-agent --viewport 1920x1080           # custom viewport (default: 1280x720)
qa-agent --timeout 60000                # timeout in ms (default: 30000)
```

### Test category flags

```bash
# Skip standard suites
qa-agent --skip-keyboard      https://example.com
qa-agent --skip-mouse         https://example.com
qa-agent --skip-forms         https://example.com
qa-agent --skip-accessibility https://example.com
qa-agent --skip-errors        https://example.com

# Enable opt-in suites
qa-agent --wcag-compliance    https://example.com  # detailed WCAG 2.1 AA audit
```

---

## Programmatic Usage

```python
from qa_agent import QAAgent, TestConfig, TestMode, OutputFormat

config = TestConfig(
    urls=["https://example.com"],
    mode=TestMode.EXPLORE,
    output_formats=[OutputFormat.CONSOLE, OutputFormat.JSON, OutputFormat.PDF],
    max_depth=2,
    max_pages=10,
    # Optional: agentic testing
    instructions="Verify the password reset flow sends an email and the link expires after 24 hours.",
    ai_model="claude-opus-4-6",
)

agent = QAAgent(config)
session = agent.run()

print(f"Pages tested:   {len(session.pages_tested)}")
print(f"Total findings: {session.total_findings}")

for finding in session.get_all_findings():
    print(f"  [{finding.severity.value.upper()}] {finding.title}")
```

---

## Test Categories

### Keyboard Navigation

TAB order and focusability · Arrow key navigation in widgets · Enter key activation · Escape key for closing modals · Keyboard trap detection · Focus visibility indicators

### Mouse Interaction

Click target functionality · Hover states · Double-click behavior · Right-click/context menus · Click target sizes (WCAG 2.5.5 minimum 44×44 px) · Overlapping element detection

### Form Handling

Required field indicators · Input validation feedback · Error message accessibility · Label associations · HTML5 input types · Autocomplete attributes

### Accessibility (WCAG)

Image alt text · Heading structure (h1–h6) · Link text quality · Color contrast · ARIA usage · Landmark regions · Language attributes · Skip navigation links

### Error Detection

Console errors and warnings · Network errors (4xx, 5xx) · JavaScript exceptions · Broken images · Broken anchor links · Mixed content (HTTP on HTTPS)

### WCAG 2.1 AA Compliance (opt-in: `--wcag-compliance`)

Covers WCAG criteria not already in the standard accessibility suite: non-text contrast (1.4.11) · use of color (1.4.1) · content on hover/focus (1.4.13) · meaningful sequence (1.3.2) · input purpose (1.3.5) · focus visible (2.4.7) · label in name (2.5.3) · target size (2.5.5) · language of parts (3.1.2) · error identification (3.3.1) · detailed ARIA role/property validation

---

## Output Formats

### Console

![Colorized console output with summary table](./docs/colorized-console-output-with-summary-table.png)

``` plaintext
======================================================================
  QA AGENT TEST REPORT
======================================================================
  Session ID: a1b2c3d4
  Started:    2024-01-15 10:30:00
  Duration:   45.2 seconds
  Mode:       explore
======================================================================

SUMMARY
  Pages tested:   5
  Total findings: 12

  By Severity:
    HIGH:   2
    MEDIUM: 5
    LOW:    5
```

### JSON

```json
{
  "meta": {
    "session_id": "a1b2c3d4",
    "start_time": "2024-01-15T10:30:00",
    "duration_seconds": 45.2
  },
  "summary": {
    "pages_tested": 5,
    "total_findings": 12,
    "findings_by_severity": { "high": 2, "medium": 5, "low": 5 }
  },
  "findings": [...]
}
```

### Severity levels

| Level | Meaning |
| --- | --- |
| `CRITICAL` | Security issues, data loss |
| `HIGH` | Major usability blockers |
| `MEDIUM` | UX problems, accessibility issues |
| `LOW` | Minor improvements, best practices |
| `INFO` | Informational findings |

---

## CI/CD Integration

```yaml
# GitHub Actions example
- name: Run QA Tests
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  run: |
    pip install "qa-agent[ai]"
    playwright install chromium
    qa-agent --output json --output-dir ./qa-results https://staging.example.com

- name: Upload Results
  uses: actions/upload-artifact@v4
  with:
    name: qa-results
    path: ./qa-results/
```

The process exits with code `1` when critical or high severity issues are found, failing the CI step automatically. See [Exit Codes](#exit-codes) for the full table.

---

## Architecture

``` plaintext
qa_agent/
├── __init__.py              # Package init, version detection
├── __main__.py              # Module entry point (python -m qa_agent)
├── cli.py                   # Argument parsing, CLI entry point
├── agent.py                 # Core orchestrator
├── config.py                # TestConfig, AuthConfig, ScreenshotConfig, RecordingConfig
├── models.py                # Finding, PageAnalysis, TestSession, TestPlan, CustomStep
├── ai_planner.py            # Claude integration — plan generation
├── plan_cache.py            # Filesystem cache for generated test plans
├── testers/
│   ├── base.py              # BaseTester abstract class
│   ├── keyboard.py          # Keyboard navigation tests
│   ├── mouse.py             # Mouse interaction tests
│   ├── forms.py             # Form handling tests
│   ├── accessibility.py     # WCAG / accessibility tests
│   ├── wcag_compliance.py   # Detailed WCAG 2.1 AA compliance (opt-in)
│   ├── errors.py            # Console & network error detection
│   └── custom.py            # Agentic custom test steps (from --instructions)
├── reporters/
│   ├── base.py              # BaseReporter abstract class
│   ├── console.py           # Real-time colored output
│   ├── markdown.py          # Markdown report
│   ├── json_reporter.py     # JSON report
│   └── pdf.py               # PDF report (requires weasyprint)
└── web/
    ├── __init__.py           # Web entry point with friendly Flask-missing error
    ├── server.py             # Flask app, SSE streaming, session browser
    ├── templates/            # Jinja2 HTML templates
    └── static/               # CSS and JavaScript
```

### Adding a custom tester

1. Create `testers/my_tester.py` extending `BaseTester`, implement `run() -> list[Finding]`
2. Export it from `testers/__init__.py`
3. Add a `test_my_feature: bool = True` flag to `TestConfig` in `config.py`
4. Call it from `agent.py` in `_test_page()`

---

## Development

```bash
# Clone and install in editable mode with dev dependencies
git clone https://github.com/billrichards/qa-agent.git
cd qa-agent
pip install -e ".[dev,web]"
playwright install chromium

# Run the full test suite (unit tests only, no browser needed)
pytest -v -m "not integration and not network"

# Run integration tests (requires Playwright browsers)
pytest -v -m integration --no-cov

# Lint
ruff check .

# Type check
mypy qa_agent
```

The CI pipeline (GitHub Actions) runs unit tests across Python 3.10, 3.11, and 3.12 on Ubuntu, macOS, and Windows. Integration tests run on Ubuntu with real Playwright browsers. See [`.github/workflows/test.yml`](.github/workflows/test.yml) for details.

---

## Contributing

Contributions are welcome! Here's how to get started:

1. Fork the repository
2. Create a feature branch (`git checkout -b my-feature`)
3. Make your changes and add tests
4. Run the test suite (`pytest -v -m "not integration and not network"`)
5. Open a pull request against `main`

Please follow the existing code style (enforced by Ruff and Black, line length 100).

---

## Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | All tests passed (no critical/high findings) |
| `1` | Critical or high severity issues found |
| `2` | Error running tests |
| `130` | Interrupted by user (Ctrl+C) |

---

## Troubleshooting

### Web UI command not found or import error

The `qa-agent-web` command and `python -m qa_agent web` require Flask, which is not installed by default:

```bash
pip install "qa-agent[web]"
```

### PDF reports not generated

PDF output requires WeasyPrint:

```bash
pip install "qa-agent[pdf]"
```

If WeasyPrint is not installed, qa-agent falls back to Markdown silently.

### Playwright browser not found

The Playwright Python package does not bundle browser binaries. You must install them separately after installing qa-agent:

```bash
playwright install chromium
# or, for all browsers:
playwright install
```

This step is easy to forget when setting up a new environment or CI job.

### Python version too old

qa-agent requires Python **3.10 or newer**. If you see `SyntaxError` or `ImportError` on startup, check your Python version:

```bash
python --version
```

Use `python3.10`, `python3.11`, or `python3.12` explicitly if your system default is older.

### Agentic testing does nothing / skips AI steps

The `--instructions` flag requires the `[ai]` extra and an Anthropic API key:

```bash
pip install "qa-agent[ai]"
export ANTHROPIC_API_KEY=sk-ant-...
```

If the package is not installed, qa-agent prints a warning and continues with standard tests only. If the package is installed but the key is missing or invalid, the same graceful fallback applies.

---

## License

MIT — Copyright (c) 2026 Bill Richards. See [LICENSE](LICENSE) for details.
