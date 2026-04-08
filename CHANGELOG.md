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

[Unreleased]: https://github.com/billrichards/qa-agent/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/billrichards/qa-agent/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/billrichards/qa-agent/releases/tag/v0.1.0
