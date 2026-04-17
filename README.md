# QA Agent

Automated exploratory QA testing for web applications — powered by Playwright and, optionally, LLMs (Claude or GPT-4o).

<p align="center">
  <a href="https://github.com/billrichards/qa-agent/actions/workflows/test.yml"><img src="https://github.com/billrichards/qa-agent/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://pypi.org/project/qa-agent/"><img src="https://img.shields.io/pypi/v/qa-agent" alt="PyPI version"></a>
  <a href="https://pypi.org/project/qa-agent/"><img src="https://img.shields.io/pypi/pyversions/qa-agent" alt="Python versions"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/billrichards/qa-agent" alt="License"></a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/billrichards/qa-agent/main/docs/console-output-showing-a-test-run-in-progress.png" alt="Console output showing a test run in progress" width="700">
</p>

Point QA Agent at a URL and it explores your application like a real user: clicking buttons, filling forms, navigating with the keyboard, and checking for accessibility issues. Then it reports what it finds. No test scripts to write or maintain.

Need targeted tests? Pass plain-English instructions and an LLM generates custom Playwright steps that run alongside the standard suite.

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Agentic Testing](#agentic-testing)
- [Web Interface & API](#web-interface--api)
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
|---|---|
| **Agentic testing** | Give Claude or GPT-4o a bug report or feature spec; it generates custom Playwright test steps automatically |
| **Two modes** | `focused` tests only given URLs; `explore` crawls and discovers pages |
| **Six test suites** | Keyboard · mouse · forms · accessibility · error detection (on by default) + WCAG 2.1 AA compliance (opt-in) |
| **Auth support** | Username/password, cookies, Bearer tokens, custom headers |
| **Four output formats** | Console, Markdown, JSON, PDF |
| **Screenshots & video** | On-error or every-interaction screenshots; full session recording |
| **Web UI** | Dashboard for launching runs, live output, and browsing past sessions |
| **CI/CD ready** | Exit codes map to pass/fail; JSON output integrates with any pipeline |

---

## Installation

> **Requires Python 3.10+.** Check with `python --version`.

```bash
pip install qa-agent            # standard testing (Playwright only)
playwright install chromium     # required — downloads browser binaries
```

Optional extras:

```bash
pip install "qa-agent[pdf]"    # PDF reports (adds WeasyPrint)
pip install "qa-agent[web]"    # web UI (adds Flask)
pip install "qa-agent[all]"    # everything above
```

Agentic testing requires an API key for your chosen provider:

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # Anthropic (default)
export OPENAI_API_KEY=sk-...          # OpenAI
```

> `playwright install chromium` must run once after every fresh install. See [Troubleshooting](#troubleshooting) if anything goes wrong.

---

## Quick Start

```bash
# Test a single URL
qa-agent https://example.com

# Test multiple URLs
qa-agent https://example.com https://example.com/about

# Crawl and test discovered pages
qa-agent --mode explore --max-depth 2 https://example.com

# Generate reports in a custom directory
qa-agent --output json,markdown --output-dir ./reports https://example.com

# Run via module
python -m qa_agent https://example.com
```

---

## Agentic Testing

Pass natural-language instructions and an LLM generates custom test steps that run alongside the standard suite. Supports **Anthropic** (Claude) and **OpenAI** (GPT-4o and others). No third-party AI packages are required — all API calls use Python's built-in `urllib`.

```bash
# From a bug report (Anthropic, default)
qa-agent --instructions "The login button does nothing when email is blank" \
  https://example.com/login

# Using OpenAI instead
qa-agent --llm openai --instructions "The login button does nothing when email is blank" \
  https://example.com/login

# From a feature spec
qa-agent --instructions "The 'Remember me' checkbox should be unchecked by default \
  and persist the session across browser restarts." \
  https://example.com/login

# From a file
qa-agent --instructions-file feature-spec.txt https://example.com
```

### How it works

1. The LLM receives your instructions and the target URL.
2. It returns a structured plan: summary, focus areas, and custom Playwright test steps.
3. The agent runs those steps on every tested page alongside the standard suites.
4. Assertion failures become findings in the report with the severity the LLM assigned.

If the API call fails (or the key is missing), a warning is printed and the run continues with standard tests only.

### Provider, model & caching

```bash
# Choose provider (default: anthropic)
qa-agent --llm anthropic --instructions "Test checkout" https://shop.example.com
qa-agent --llm openai    --instructions "Test checkout" https://shop.example.com

# Override model (defaults: anthropic → claude-sonnet-4-6, openai → gpt-4o)
qa-agent --llm openai --ai-model gpt-4o-mini --instructions "Test checkout" https://shop.example.com

# Bypass the plan cache
qa-agent --no-cache --instructions "..." https://example.com
```

Plans are cached to `~/.qa_agent/cache/` (24-hour TTL). Pass `--no-cache` to force a fresh API call.

---

## Web Interface & API

<p align="center">
  <img src="https://raw.githubusercontent.com/billrichards/qa-agent/main/docs/web-UI-configuration-form.png" alt="Web interface configuration form" width="700">
</p>

```bash
python -m qa_agent web              # http://127.0.0.1:5000
qa-agent-web --host 0.0.0.0 --port 8080  # custom bind
```

- Configuration form with all CLI options
- Real-time streaming output (Server-Sent Events)
- Stop a running test mid-run
- Browse past sessions grouped by domain
- Session detail: findings table, severity breakdown, screenshot gallery, report downloads

<p align="center">
  <img src="https://raw.githubusercontent.com/billrichards/qa-agent/main/docs/session-detail-view-showing-findings-table.png" alt="Session detail view showing findings table" width="700">
</p>

> **No authentication** — intended for local or internal use only.

Output is written to `output/` by default. CLI sessions appear in the web UI automatically (JSON is always written).

### REST API

The web server exposes a JSON API at `http://127.0.0.1:5000` (default).

```bash
# Launch a test run
curl -X POST http://127.0.0.1:5000/api/run \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"]}'
# → {"job_id": "a1b2c3d4", "status": "running", "stream_url": "/api/stream/a1b2c3d4"}

# Stream live output (Server-Sent Events)
curl -N http://127.0.0.1:5000/api/stream/a1b2c3d4

# List past sessions
curl http://127.0.0.1:5000/api/sessions?limit=10
```

→ [Full API reference](https://github.com/billrichards/qa-agent/blob/main/docs/web-api.md) — all endpoints, request body schema, and SSE event types.

---

## CLI Reference

```bash
qa-agent --version
qa-agent --help
```

### Modes

```bash
qa-agent --mode focused https://example.com   # default — test only given URLs
qa-agent --mode explore https://example.com    # crawl and test discovered pages
```

### Exploration (explore mode)

| Flag | Default | Description |
|---|---|---|
| `--max-depth N` | `3` | Max link depth |
| `--max-pages N` | `100` | Max pages to test |
| `--max-interactions N` | `50` | Max interactions per page |
| `--allow-external` | off | Follow links to other domains |
| `--ignore PATTERN` | — | URL regex to skip (repeatable) |

### Authentication

```bash
qa-agent --auth "user:pass@https://example.com/login" https://example.com/dashboard
qa-agent --auth-file auth.json https://example.com
qa-agent --cookies cookies.json https://example.com
qa-agent --header "Authorization: Bearer token123" https://example.com
```

<details>
<summary><strong>auth.json schema</strong></summary>

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

</details>

### Output

```bash
qa-agent --output console,markdown,json,pdf https://example.com
qa-agent --output-dir ./reports https://example.com
```

Default: `console,markdown`. JSON is always written regardless of `--output` (for web UI discovery). Output is organized as `output/{domain}/{session_id}/qa_reports|screenshots|recordings`.

> PDF requires the `[pdf]` extra. Falls back to Markdown if WeasyPrint is not installed.

### Screenshots & recording

```bash
qa-agent --screenshots       https://example.com  # on errors
qa-agent --screenshots-all   https://example.com  # every interaction
qa-agent --full-page         https://example.com  # full-page captures
qa-agent --record            https://example.com  # session video
```

### Browser

```bash
qa-agent --no-headless                  # visible browser window
qa-agent --viewport 1920x1080           # default: 1280x720
qa-agent --timeout 60000                # ms, default: 30000
```

### Test suites

```bash
# Skip standard suites
qa-agent --skip-keyboard      https://example.com
qa-agent --skip-mouse         https://example.com
qa-agent --skip-forms         https://example.com
qa-agent --skip-accessibility https://example.com
qa-agent --skip-errors        https://example.com

# Enable opt-in suites
qa-agent --wcag-compliance    https://example.com
```

### Agentic testing flags

| Flag | Default | Description |
|---|---|---|
| `--llm {anthropic,openai}` | `anthropic` | LLM provider for AI instructions |
| `--ai-model MODEL` | provider default | Model override (`claude-sonnet-4-6` / `gpt-4o`) |
| `--no-cache` | off | Bypass the 24-hour plan cache |

---

## Programmatic Usage

```python
from qa_agent import QAAgent, TestConfig, TestMode, OutputFormat
from qa_agent.llm_client import LLMProvider

config = TestConfig(
    urls=["https://example.com"],
    mode=TestMode.EXPLORE,
    output_formats=[OutputFormat.CONSOLE, OutputFormat.JSON],
    max_depth=2,
    max_pages=10,
    instructions="Verify the password reset flow.",  # optional
    llm_provider=LLMProvider.OPENAI,   # optional, default: LLMProvider.ANTHROPIC
    ai_model="gpt-4o-mini",            # optional, default: None (uses provider default)
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

Six built-in suites cover keyboard navigation, mouse interaction, form handling, accessibility (WCAG), runtime error detection, and an opt-in WCAG 2.1 AA compliance audit. Five run by default; enable the sixth with `--wcag-compliance`.

→ [Detailed test-by-test reference](https://github.com/billrichards/qa-agent/blob/main/docs/test-categories.md)

---

## Output Formats

### Console

![Colorized console output with summary table](https://raw.githubusercontent.com/billrichards/qa-agent/main/docs/colorized-console-output-with-summary-table.png)

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
|---|---|
| `CRITICAL` | Security issues, data loss |
| `HIGH` | Major usability blockers |
| `MEDIUM` | UX problems, accessibility issues |
| `LOW` | Minor improvements, best practices |
| `INFO` | Informational observations |

---

## CI/CD Integration

```yaml
# GitHub Actions example
- name: Run QA Tests
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}   # or OPENAI_API_KEY
  run: |
    pip install qa-agent
    playwright install chromium
    qa-agent --output json --output-dir ./qa-results https://staging.example.com

- name: Upload Results
  uses: actions/upload-artifact@v4
  with:
    name: qa-results
    path: ./qa-results/
```

Exits with code `1` when critical or high severity issues are found, failing the CI step automatically. See [Exit Codes](#exit-codes).

> Omit `--instructions` / `--instructions-file` and the API key env vars if you only need standard tests.

---

## Architecture

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

→ [Extending QA Agent — adding custom testers](https://github.com/billrichards/qa-agent/blob/main/docs/architecture.md)

---

## Development

```bash
git clone https://github.com/billrichards/qa-agent.git
cd qa-agent
pip install -e ".[dev,web,ai]"
playwright install chromium

# Unit tests (no browser needed)
pytest -v -m "not integration and not network"

# Integration tests (real Playwright)
pytest -v -m integration --no-cov

# Browse the test harness in a browser
cd tests/fixtures/test-target && python3 -m http.server 8181

# Lint & type check
ruff check .
mypy qa_agent
```

CI runs unit tests across Python 3.10–3.12 on Ubuntu, macOS, and Windows. Integration tests run on Ubuntu with Playwright. See [`.github/workflows/test.yml`](https://github.com/billrichards/qa-agent/blob/main/.github/workflows/test.yml).

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b my-feature`)
3. Make your changes and add tests
4. Run `pytest -v -m "not integration and not network"`
5. Open a pull request against `main`

Code style: Ruff + Black, line length 100.

---

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | All tests passed (no critical/high findings) |
| `1` | Critical or high severity issues found |
| `2` | Error running tests |
| `130` | Interrupted (Ctrl+C) |

---

## Troubleshooting

### Playwright browser not found

```bash
playwright install chromium
```

Must run once after every fresh install. Easy to forget in CI.

### Web UI not working

```bash
pip install "qa-agent[web]"
```

Required for `qa-agent-web` and `python -m qa_agent web`.

### PDF reports missing

```bash
pip install "qa-agent[pdf]"
```

Falls back to Markdown silently if WeasyPrint is absent.

### Agentic testing skipped

No extra packages are needed — LLM calls use Python's built-in `urllib`. You only need a valid API key for your chosen provider:

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # for --llm anthropic (default)
export OPENAI_API_KEY=sk-...          # for --llm openai
```

If the key is missing or the API call fails, qa-agent prints a warning and continues with standard tests.

### Python version too old

Requires **3.10+**. Check with `python --version`.

---

## License

MIT — Copyright (c) 2026 Bill Richards. See [LICENSE](https://github.com/billrichards/qa-agent/blob/main/LICENSE).
