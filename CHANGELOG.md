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

[Unreleased]: https://github.com/billrichards/qa-agent/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/billrichards/qa-agent/compare/v0.2.0...v0.2.2
[0.2.0]: https://github.com/billrichards/qa-agent/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/billrichards/qa-agent/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/billrichards/qa-agent/releases/tag/v0.1.0
