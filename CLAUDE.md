# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
pip install -e ".[dev,web,pdf]"
playwright install chromium
```

The package must be installed (editable is fine) for `python -m qa_agent`, the
`qa-agent`/`qa-agent-web` entry points, and subprocess-based tests (e.g.
`tests/_cli_exit_helper.py`) to find the `qa_agent` module. If packaging tests
fail with `ModuleNotFoundError: No module named 'qa_agent'` or version
mismatches, run `pip install -e .` first — check with `pip show qa-agent`.

## Commands

```bash
# Unit tests (fast, no browser)
pytest -v -m "not integration and not network"

# Single test
pytest tests/test_agent.py::TestClassName::test_name -v

# Integration tests (real Playwright against local fixture server)
pytest -v -m integration --no-cov

# Lint / format / type-check
ruff check .
ruff format .
mypy qa_agent

# Build
rm -rf build/ dist/ && python -m build
```

Coverage is enforced at 70% via `--cov-fail-under=70` in `pyproject.toml`
(applies to default `pytest` invocations). Running a small subset of tests
without `--no-cov` will fail on the coverage gate even if the tests
themselves pass — use `-p no:cacheprovider -o addopts=""` or `--no-cov` to
bypass when checking a few tests in isolation.

Integration tests serve fixtures from `tests/fixtures/test-target/` (a
73-page HTML fixture site driven by `manifest.json`, which is the source of
truth for parametrized integration tests — each entry maps a fixture file to
an expected finding title/category). Start the fixture server manually for
debugging:

```bash
cd tests/fixtures/test-target && python3 -m http.server 8181
```

## Architecture

Request flow: `cli.py` parses args into a `TestConfig` (`config.py`) →
if `--instructions`/`--instructions-file` is set, `ai_planner.py` calls
`llm_client.py` (Anthropic/OpenAI via stdlib `urllib`, no SDK deps) to
produce a `TestPlan`, cached on disk by `plan_cache.py` (24h TTL) →
`agent.py` (`QAAgent`) launches Playwright, sweeps each configured viewport in
turn, iterating/crawling target URLs and running each enabled tester from
`testers/` against every page, collecting `Finding` objects → reporters in
`reporters/` consume the resulting `TestSession` and write
console/markdown/json/pdf output.

- **Concurrency**: `concurrency.py` implements page-level worker pools
  (`--workers`, max 16) within a single run, and `batch.py` (`BatchRunner`)
  runs multiple independent `TestConfig` sessions concurrently with a bounded
  pool (`--pool-size`/`--batch-file`, max 8). Total live browsers ≈
  `pool_size × workers`.
- **Rate limiting**: `rate_limiter.py` (`HostRateLimiter`) paces
  `page.goto()` navigations per-hostname (`--rate-limit`, default 3 req/s,
  `0` disables). One shared instance per `QAAgent` run covers all its
  workers; `BatchRunner` can hold a single shared instance passed to every
  `QAAgent` it constructs so concurrent batch jobs hitting the same host
  share one budget.
- **Viewports**: `viewports.py` holds the `Viewport` device profile (size plus
  device scale factor, touch, mobile flag, user agent) and the preset registry.
  `TestConfig.viewports` accepts preset names, `WxH` strings, dicts, or
  `Viewport` objects and normalises them in `__post_init__`; empty means a
  single viewport from the legacy `viewport_width`/`viewport_height` pair,
  which afterwards mirror `viewports[0]`. The agent runs one full sweep per
  viewport (max `VIEWPORTS_MAX`, 10), so total cost multiplies by the count.
  Viewport is part of the dedup key in `models.py`, keeping a mobile-only
  finding distinct from its desktop namesake. The registry is a plain data
  table, not a `playwright.devices` lookup, so it imports without a browser.
- **Testers** (`testers/`) all extend `BaseTester` (`testers/base.py`),
  receive a Playwright `Page` + `TestConfig`, and return `list[Finding]`.
  `custom.py` runs AI-generated steps from the cached `TestPlan`.
  `wcag_compliance.py` is opt-in (`--wcag-compliance`) and excluded from
  coverage.
- **Reporters** (`reporters/`) all extend `BaseReporter` and consume a
  `TestSession`; JSON is always written regardless of `--output` (web UI
  relies on it for session discovery).
- **Web UI** (`web/`): Flask app (`server.py`) with SSE streaming for live
  run output; templates/static assets are in `web/templates/` and
  `web/static/`. No auth — local/internal use only.
- **Models** (`models.py`): `Finding`, `FindingCategory`, `Severity`,
  `PageAnalysis`, `TestSession`, `TestPlan` — the shared data contracts
  between testers, the agent, and reporters.

### Adding a new tester

1. New module in `testers/` extending `BaseTester`, implement `run() ->
   list[Finding]`.
2. Export from `testers/__init__.py`.
3. Add a `test_*` bool to `TestConfig` (`config.py`).
4. Wire into `agent.py` `_test_page()`.
5. Add `--skip-*`/opt-in flag in `cli.py` if needed.
6. Add tests in `tests/testers/`.

### Severity levels

`CRITICAL` (security/data loss) · `HIGH` (major usability blockers) ·
`MEDIUM` (UX/accessibility) · `LOW` (minor/best-practice) · `INFO`.

### Exit codes (CLI)

`0` no critical/high findings · `1` critical/high findings found · `2` error
during run · `130` interrupted (Ctrl+C). Covered by
`tests/test_packaging.py::TestExitCodeSmoke` via `tests/_cli_exit_helper.py`.
