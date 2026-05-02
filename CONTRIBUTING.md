# Contributing to QA Agent

Thank you for your interest in contributing! This guide covers everything you need to set up a development environment, run tests, and submit contributions.

## Quick Links

- [Architecture Overview](docs/architecture.md)
- [Development Guide](docs/development.md)
- [API Reference](docs/api-reference.md)
- [Test Categories](docs/test-categories.md)
- [Web API Reference](docs/web-api.md)
- [Issue Tracker](https://github.com/billrichards/qa-agent/issues)

---

## Development Setup

### Prerequisites

- **Python 3.10+** — check with `python --version`
- **Git**
- **Playwright** — installed via pip, then browser binaries

### Clone and Install

```bash
git clone https://github.com/billrichards/qa-agent.git
cd qa-agent
pip install -e ".[dev,web,pdf]"
playwright install chromium
```

### Verify Installation

```bash
# Run unit tests (no browser needed)
pytest -v -m "not integration and not network"

# Run integration tests (real Playwright)
pytest -v -m integration --no-cov

# Browse the test harness (run in background)
cd tests/fixtures/test-target && python3 -m http.server 8181 &
```

---

## Code Style

- **Formatter:** Black (line length 100)
- **Linter:** Ruff (selects: E, F, W, I, N, UP, B)
- **Type checking:** mypy (Python 3.10 target)

```bash
ruff check .
ruff format .
mypy qa_agent
```

CI enforces these checks on all PRs.

---

## Project Structure

```
qa_agent/
├── cli.py                   # CLI entry point (argparse)
├── agent.py                 # Core orchestrator (QAAgent class)
├── config.py                # Configuration dataclasses (TestConfig)
├── models.py                # Data models (Finding, PageAnalysis, TestSession)
├── llm_client.py            # Anthropic & OpenAI clients (stdlib urllib)
├── ai_planner.py            # LLM-powered test plan generation
├── plan_cache.py            # Filesystem cache for test plans
├── testers/                 # Test modules (extend BaseTester)
│   ├── base.py              # BaseTester abstract class
│   ├── keyboard.py          # Keyboard navigation tests
│   ├── mouse.py             # Mouse interaction tests
│   ├── forms.py             # Form handling tests
│   ├── accessibility.py     # WCAG accessibility tests
│   ├── wcag_compliance.py   # WCAG 2.1 AA compliance (opt-in)
│   ├── errors.py            # Console & network error detection
│   └── custom.py            # AI-generated test steps
├── reporters/               # Output generators (extend BaseReporter)
│   ├── base.py              # BaseReporter abstract class
│   ├── console.py           # Colored terminal output
│   ├── markdown.py          # Markdown report
│   ├── json_reporter.py     # JSON report
│   └── pdf.py               # PDF report (requires weasyprint)
└── web/                     # Web UI (Flask)
    ├── server.py            # Flask app with SSE streaming
    ├── templates/           # Jinja2 templates
    └── static/              # CSS and JavaScript
```

→ [Full architecture reference](docs/architecture.md)

---

## Adding New Tests

1. Create a new tester in `qa_agent/testers/` extending [`BaseTester`](qa_agent/testers/base.py)
2. Implement the `run()` method returning `list[Finding]`
3. Add to `qa_agent/testers/__init__.py`
4. Add a config flag in [`config.py`](qa_agent/config.py) (e.g., `test_new_feature`)
5. Call from [`agent.py`](qa_agent/agent.py) in `_test_page()`

### Example: Adding a Performance Tester

```python
# qa_agent/testers/performance.py
from qa_agent.testers.base import BaseTester
from qa_agent.models import Finding, Severity

class PerformanceTester(BaseTester):
    def run(self):
        findings = []
        # Your test logic here
        findings.append(Finding(
            severity=Severity.MEDIUM,
            title="Page load time exceeds 3 seconds",
            url=self.page.url,
            description="..."
        ))
        return findings
```

---

## Running Tests

### Unit Tests

Fast tests that don't require a browser:

```bash
pytest -v -m "not integration and not network"
```

### Integration Tests

Real Playwright tests against local fixture server:

```bash
# Start fixture server in background
cd tests/fixtures/test-target && python3 -m http.server 8181 &

# Run integration tests
pytest -v -m integration --no-cov
```

### Coverage

```bash
pytest --cov=qa_agent --cov-report=html
open htmlcov/index.html  # macOS
```

---

## Pull Request Process

1. **Fork** the repository
2. **Create a feature branch** (`git checkout -b my-feature`)
3. **Make your changes** and add tests
4. **Run the test suite** (`pytest -v -m "not integration and not network"`)
5. **Lint and format** (`ruff check . && ruff format .`)
6. **Open a pull request** against `main`

### PR Checklist

- [ ] Tests added or updated
- [ ] Documentation updated (if applicable)
- [ ] Changelog entry added (for user-facing changes)
- [ ] All CI checks pass

---

## CI/CD

GitHub Actions runs:

- Unit tests on Python 3.10, 3.11, 3.12
- Integration tests on Ubuntu with Playwright
- Linting (Ruff) and type checking (mypy)

See [`.github/workflows/test.yml`](.github/workflows/test.yml) for the full configuration.

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
