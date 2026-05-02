# Development Guide

This guide covers the development workflow for QA Agent: setting up your environment, running tests, building distributions, and debugging.

---

## Environment Setup

### Prerequisites

| Tool | Minimum Version | Check |
|---|---|---|
| Python | 3.10 | `python --version` |
| pip | 23.0 | `pip --version` |
| Git | 2.30 | `git --version` |

### Clone and Install

```bash
git clone https://github.com/billrichards/qa-agent.git
cd qa-agent
pip install -e ".[dev,web,pdf]"
playwright install chromium
```

The `-e` flag installs the package in editable mode so changes to source files are reflected immediately without reinstalling.

### Verify Setup

```bash
# Run the full unit test suite
pytest -v -m "not integration and not network"

# Lint check
ruff check .

# Type check
mypy qa_agent
```

---

## Running Tests

### Test Categories

| Category | Command | Description |
|---|---|---|
| Unit tests | `pytest -v -m "not integration and not network"` | Fast tests, no browser required |
| Integration tests | `pytest -v -m integration --no-cov` | Real Playwright against local fixtures |
| Network tests | `pytest -v -m network` | Tests requiring real network access |
| All tests | `pytest -v` | Everything (slow) |

### Fixture Server

Integration tests run against a local HTTP server serving files from `tests/fixtures/test-target/`. Start it manually for debugging:

```bash
cd tests/fixtures/test-target
python3 -m http.server 8181
```

Then point QA Agent at it:

```bash
qa-agent http://localhost:8181
```

### Coverage

```bash
# Terminal report
pytest --cov=qa_agent --cov-report=term-missing

# HTML report
pytest --cov=qa_agent --cov-report=html
open htmlcov/index.html  # macOS
```

The CI threshold is 70% (`--cov-fail-under=70` in `pyproject.toml`).

### Parallel Execution

```bash
pytest -n auto  # uses pytest-xdist
```

---

## Code Quality

### Formatting

```bash
ruff format .
```

Black-compatible formatting with 100-character line width (configured in `pyproject.toml`).

### Linting

```bash
ruff check .
ruff check --fix .  # auto-fix safe issues
```

Enabled rules: `E` (pycodestyle errors), `F` (pyflakes), `W` (pycodestyle warnings), `I` (isort), `N` (pep8-naming), `UP` (pyupgrade), `B` (bugbear).

### Type Checking

```bash
mypy qa_agent
```

Target: Python 3.10 with `warn_return_any` and `warn_unused_configs` enabled.

---

## Building Distributions

### Clean Build

```bash
rm -rf build/ dist/
python -m build
```

Output:

- `dist/qa_agent-<version>-py3-none-any.whl` — wheel
- `dist/qa-agent-<version>.tar.gz` — source distribution

### Install from Local Build

```bash
pip install dist/qa_agent-<version>-py3-none-any.whl
```

### Verify Package Contents

```bash
python -m twine check dist/*
```

---

## Debugging

### Verbose Playwright Output

```bash
DEBUG=pw:api qa-agent https://example.com
```

### Run with Visible Browser

```bash
qa-agent --no-headless https://example.com
```

### Session Recording

```bash
qa-agent --record https://example.com
```

Video is saved to `output/{domain}/{session_id}/recordings/`.

### Python Debugger

```bash
python -m pdb -m qa_agent https://example.com
```

Or insert breakpoints directly:

```python
import pdb; pdb.set_trace()
```

---

## CI/CD

GitHub Actions (`.github/workflows/test.yml`) runs:

1. **Unit tests** on Python 3.10, 3.11, 3.12 across Ubuntu, macOS, and Windows
2. **Integration tests** on Ubuntu with Playwright
3. **Linting** (Ruff) and **type checking** (mypy)
4. **Packaging** verification (build + install)

### Local CI Simulation

```bash
# Simulate the full CI locally
ruff check . && ruff format --check .
mypy qa_agent
pytest -v -m "not integration and not network"
rm -rf build/ dist/ && python -m build
pip install dist/*.whl
qa-agent --version
```

---

## Adding New Features

### New Test Category

1. Create `qa_agent/testers/new_category.py` extending `BaseTester`
2. Implement `run() -> list[Finding]`
3. Export from `qa_agent/testers/__init__.py`
4. Add config flag to `TestConfig` in `config.py`
5. Wire into `agent.py` `_test_page()` method
6. Add tests in `tests/testers/test_new_category.py`

### New Output Format

1. Create `qa_agent/reporters/new_format.py` extending `BaseReporter`
2. Implement `generate()` method
3. Export from `qa_agent/reporters/__init__.py`
4. Add to `OutputFormat` enum in `models.py`
5. Wire into `agent.py` report generation
6. Add tests in `tests/test_reporters.py`

### New CLI Flag

1. Add argument to `cli.py` `build_parser()`
2. Add field to `TestConfig` in `config.py`
3. Pass through in `cli.py` `main()`
4. Update `--help` output
5. Add tests in `tests/test_cli.py`

---

## Troubleshooting Development Issues

### Playwright Browser Missing

```bash
playwright install chromium
```

### Tests Hanging

Integration tests may hang if the fixture server isn't running. Start it:

```bash
cd tests/fixtures/test-target && python3 -m http.server 8181 &
```

### mypy Errors on Third-Party Libraries

```bash
mypy --ignore-missing-imports qa_agent
```

Or add to `pyproject.toml`:

```toml
[tool.mypy]
ignore_missing_imports = true
```

### Stale Cache

AI test plans are cached in `~/.qa_agent/cache/`. Clear it:

```bash
rm -rf ~/.qa_agent/cache/
```

Or use `--no-cache` when running.
