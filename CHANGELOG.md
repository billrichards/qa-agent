# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Breaking change policy

- **CLI flags** – renaming or removing a flag is a breaking change (major bump).
- **Exit codes** – changing the meaning of an exit code is a breaking change.
- **JSON report schema** – removing or renaming fields is a breaking change.
- **Python API** – changing public imports (`from qa_agent import QAAgent, TestConfig`) in a non-backward-compatible way is a breaking change.

---

## [Unreleased]

## [0.3.0] - 2026-06-13

### Added

- **Multi-worker concurrency** — two layers, available identically across CLI, web, and the Python API:
  - *Page-level*: `TestConfig.workers` (CLI `--workers`, web `workers` in the `POST /api/run` body) tests multiple pages of a single run in parallel, each worker driving its own browser/context. Defaults to `1` (sequential, unchanged behaviour); capped at 16. Authentication is performed once and replicated to every worker via Playwright `storage_state`.
  - *Session-level*: `BatchRunner` (`from qa_agent import BatchRunner`) runs multiple independent sessions through a bounded thread pool. The CLI exposes it via `--batch-file`/`--pool-size`; the web server now uses it instead of an unbounded thread-per-job model (`QA_AGENT_JOB_POOL_SIZE`, default 4).
- **Expanded public API** — `from qa_agent import QAAgent, TestConfig, BatchRunner, …` now re-exports the full public surface for library use.
- **Per-host rate limiting**: `HostRateLimiter` paces `page.goto()` navigations to at most `--rate-limit` requests/second per hostname (default `3.0`, `0` disables). Shared across all page-workers in a run and, optionally, across concurrent `BatchRunner` jobs targeting the same host, to avoid overwhelming fragile dev/staging servers. Web server honours `QA_AGENT_RATE_LIMIT`.

### Fixed

- **Web UI duplicate log lines**: progress (`🔍 Testing: <url>`) and finding lines were rendered twice in the live log stream (once as a generic log line, once as a styled progress/finding line). Each line now renders exactly once.
- **Silent `worker_thread_init` failures**: errors from the per-worker stdout-routing hook are now surfaced via the console / logger instead of being swallowed.

## [0.2.3] - 2026-05-22

### Fixed

- **CSP / stuck-queued bug**: All inline `<script>` blocks extracted from Jinja2 templates to external static files (`static/index.js`, `run.js`, `sessions.js`, `session.js`), resolving `script-src 'self'` violations that blocked SSE event handling and caused the web UI to show "Queued" indefinitely.
- **Stop button**: Now correctly reflects actual job state on page load via a pre-flight `/api/status` check before opening the SSE stream. Button text updated to "Stopping after current page…".
- **Exploratory mode logout links**: Explore mode now skips URLs and link text matching common logout/destructive patterns (`/logout`, `/sign-out`, "log out", etc.) by default. When AI instructions explicitly reference logout flows, the heuristic is bypassed to honour the user's intent.
- **Re-auth loop guard**: Re-authentication on login-page redirect is now limited to one attempt per page; subsequent redirects log a red error and skip the page rather than looping indefinitely.

### Added

- `ConsoleReporter.print_error()`: errors now render in red (`✗ ERROR:`) in CLI output, distinct from progress messages.
- Export/Import config buttons in the web UI — download current form config as `qa-agent-config.json` or load a previously saved file.
- Auth file tip now includes a complete JSON example with all supported fields.

### Changed

- Default output directory renamed from `./output` to `./qa-agent-output` (CLI `--output-dir`, web server, and `TestConfig` default). Explicit `--output-dir` flags are unaffected.
- Keyboard trap (focus cycling through a single element) severity lowered from HIGH to MEDIUM with an updated description citing WCAG 2.1 SC 2.1.2.

## [0.2.2] - 2026-05-02

### Added

- `CONTRIBUTING.md` with development setup, architecture overview, and contribution guidelines.
- `docs/README.md` as a documentation hub linking to all detailed docs.
- `docs/development.md` with detailed development guide covering environment setup, testing, building, and debugging.
- `docs/api-reference.md` with complete programmatic API reference for embedding QA Agent in Python code.

### Changed

- README.md trimmed for PyPI: Architecture, Development, Contributing, and Programmatic Usage sections moved to dedicated docs files.
- `pyproject.toml` now includes a `Documentation` URL pointing to `docs/README.md`.
- All documentation links in README.md use full GitHub URLs so they render correctly on PyPI.

## [0.2.0] - 2026-04-14

### Added

- **Multi-LLM support**: Anthropic (Claude) and OpenAI (GPT-4o) providers via Python's built-in `urllib` — no third-party AI SDK required. New `--llm` and `--ai-model` CLI flags. New `llm_client.py` module.
- **AI plan validation warnings**: `validate_plan()` detects four patterns in LLM-generated test plans — steps with no assertions, unknown assertion types, hover actions without wait, and trivially-passing hover+visible assertions. Warnings appear in console, Markdown, and JSON reports.
- `--max-interactions` CLI flag to control the maximum number of interactions per page (default: 50).
- `nh3` HTML sanitizer for Markdown report rendering in the web UI, preventing XSS from finding titles/descriptions that captured payloads from tested sites.
- Content-Security-Policy and security headers (`X-Content-Type-Options`, `X-Frame-Options`) on all web server responses.
- HTML tag escaping in Markdown report output to prevent injection.
- Markdown reports now list all affected pages under each deduplicated finding.
- Documentation restructured: new `docs/test-categories.md`, `docs/architecture.md`, and `docs/web-api.md`; README trimmed with links to detailed docs.

### Changed

- **`max_pages` default increased** from `20` to `100` (CLI, web API, and config).
- Inline text links are now exempt from the small click-target check in the mouse tester (reduces false positives).
- Animations under 50 ms are now ignored in the reduced-motion accessibility check.
- Test coverage improved from 67 % to 77 % across all modules.

### Fixed

- Keyboard trap detection rewritten for reliability — no longer produces false positives on pages with few focusable elements.
- XSS vulnerabilities in the `/files/` endpoint (path traversal via symlinks, unescaped JSON rendering).
- `nh3` import moved to module level for consistent startup-time failure when the package is missing.
- `mypy` no-any-return errors in `llm_client` and `ai_planner`.

## [0.1.1] - 2026-04-07

### Added

- Comprehensive test suite: unit tests for `agent`, `cli`, `config`, `models`, `plan_cache`, all reporters, and all testers; web server tests; integration smoke tests against local HTML fixtures. (~3 400 lines across 12 test files, PR #8).
- GitHub Actions CI workflow (`test.yml`) running the full test suite on push and pull request.
- HTML test fixtures (`tests/fixtures/site/`) used by integration and unit tests.
- `tests/conftest.py` shared fixtures (mock Playwright page, mock session, local fixture server).

### Fixed

- JSON report rendering in the web UI (`web/server.py`).
- Screenshot rendering in the web UI — base64 images now display correctly in the session detail view.
- Type-checker errors in `agent.py`, `reporters/console.py`, `reporters/markdown.py`, `testers/base.py`, and `web/server.py`.
- Markdown report file opened with explicit UTF-8 encoding in tests, fixing failures on Windows-default locales.

### Changed

- Ruff lint configuration moved to `[tool.ruff.lint]` (new spec); all 500+ pre-existing lint errors resolved across the entire codebase.

## [0.1.0] - 2026-04-07

### Added

- Initial public release.
- Agentic exploratory QA testing powered by Claude (Anthropic API).
- Two test modes: `focused` (given URLs only) and `explore` (crawl and discover).
- Five standard test suites: keyboard navigation, mouse interaction, form handling, accessibility (WCAG), and error detection.
- Opt-in WCAG 2.1 AA compliance tester (`--wcag-compliance`): covers non-text contrast, use of color, content on hover/focus, meaningful sequence, input purpose, focus visible, label in name, target size, language of parts, error identification, and detailed ARIA role/property validation.
- Authentication support: username/password, cookies, Bearer tokens, custom headers.
- Four output formats: console, Markdown, JSON, PDF.
- On-error and every-interaction screenshot capture; full session video recording.
- Web UI dashboard for launching runs, watching live output, and browsing past sessions.
- `qa-agent` and `qa-agent-web` console entry points.
- `--version` flag (`qa-agent --version`).
- Optional dependency extras: `pdf`, `web`, `all`.
- CI/CD integration via exit codes (0 = pass, 1 = critical/high issues, 2 = error, 130 = interrupted).

[Unreleased]: https://github.com/billrichards/qa-agent/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/billrichards/qa-agent/compare/v0.2.3...v0.3.0
[0.2.2]: https://github.com/billrichards/qa-agent/compare/v0.2.0...v0.2.2
[0.2.0]: https://github.com/billrichards/qa-agent/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/billrichards/qa-agent/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/billrichards/qa-agent/releases/tag/v0.1.0
