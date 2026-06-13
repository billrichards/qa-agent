"""Shared fixtures for qa-agent tests."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from qa_agent.models import Finding, FindingCategory, PageAnalysis, Severity, TestSession

# ---------------------------------------------------------------------------
# Data factories
# ---------------------------------------------------------------------------

def make_finding(
    title: str = "Test Finding",
    description: str = "A test finding",
    category: FindingCategory = FindingCategory.ACCESSIBILITY,
    severity: Severity = Severity.MEDIUM,
    url: str = "https://example.com",
    **kwargs,
) -> Finding:
    return Finding(
        title=title,
        description=description,
        category=category,
        severity=severity,
        url=url,
        **kwargs,
    )


def make_page_analysis(
    url: str = "https://example.com",
    findings: list[Finding] | None = None,
) -> PageAnalysis:
    return PageAnalysis(
        url=url,
        title="Test Page",
        load_time_ms=100.0,
        interactive_elements=5,
        forms_count=1,
        links_count=3,
        images_count=2,
        findings=findings or [],
    )


def make_session(
    session_id: str = "test1234",
    findings: list[Finding] | None = None,
) -> TestSession:
    session = TestSession(
        session_id=session_id,
        start_time=datetime(2024, 1, 1, 12, 0, 0),
        end_time=datetime(2024, 1, 1, 12, 5, 0),
        config_summary={"mode": "focused", "urls": ["https://example.com"]},
    )
    page = make_page_analysis(findings=findings or [])
    session.add_page_analysis(page)
    return session


def make_session_with_findings() -> TestSession:
    """Return a session pre-populated with one finding of each severity."""
    session = TestSession(
        session_id="rich5678",
        start_time=datetime(2024, 1, 1, 12, 0, 0),
        end_time=datetime(2024, 1, 1, 12, 5, 0),
        config_summary={"mode": "focused", "urls": ["https://example.com"]},
    )
    page = make_page_analysis(findings=[
        make_finding("Critical Issue", severity=Severity.CRITICAL),
        make_finding("High Issue", severity=Severity.HIGH),
        make_finding("Medium Issue", severity=Severity.MEDIUM, category=FindingCategory.FORM_HANDLING),
        make_finding("Low Issue", severity=Severity.LOW, category=FindingCategory.KEYBOARD_NAVIGATION),
        make_finding("Info Issue", severity=Severity.INFO, category=FindingCategory.CONSOLE_ERROR),
    ])
    session.add_page_analysis(page)
    return session


# ---------------------------------------------------------------------------
# Playwright mock factory
# ---------------------------------------------------------------------------

def _make_mock_page() -> MagicMock:
    """Return a MagicMock Page with sensible defaults for common methods."""
    page = MagicMock()
    page.url = "https://example.com"
    page.title.return_value = "Test Page"
    page.evaluate.return_value = {
        "interactive_elements": 0,
        "forms_count": 0,
        "links_count": 0,
        "images_count": 0,
    }
    page.locator.return_value = MagicMock(count=MagicMock(return_value=0))
    page.wait_for_load_state.return_value = None
    page.goto.return_value = None
    return page


def make_mock_playwright_factory(page: MagicMock | None = None):
    """
    Return a callable that acts like ``sync_playwright`` (context-manager style).

    Usage::

        factory, mock_page = make_mock_playwright_factory()
        agent = QAAgent(config, playwright_factory=factory)
    """
    if page is None:
        page = _make_mock_page()

    context = MagicMock()
    browser = MagicMock()
    chromium = MagicMock()
    pw = MagicMock()

    context.new_page.return_value = page
    context.storage_state.return_value = {"cookies": [], "origins": []}
    browser.new_context.return_value = context
    chromium.launch.return_value = browser
    pw.chromium = chromium

    @contextmanager
    def factory():
        yield pw

    return factory, page, context, browser


def make_multi_mock_playwright_factory():
    """Return a factory whose contexts/pages are DISTINCT per call.

    Use for multi-worker (``config.workers > 1``) tests so each worker gets its
    own mock page rather than a shared singleton. Returns ``(factory, pages)``
    where ``pages`` is a live list that accumulates every page handed out.
    """
    pages: list[MagicMock] = []

    def _new_page(*_a, **_k):
        page = _make_mock_page()
        pages.append(page)
        return page

    def _new_context(*_a, **_k):
        context = MagicMock()
        context.new_page.side_effect = _new_page
        context.storage_state.return_value = {"cookies": [], "origins": []}
        return context

    browser = MagicMock()
    browser.new_context.side_effect = _new_context
    chromium = MagicMock()
    chromium.launch.return_value = browser
    pw = MagicMock()
    pw.chromium = chromium

    @contextmanager
    def factory():
        yield pw

    return factory, pages


# ---------------------------------------------------------------------------
# pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_chromium_install(request):
    """Prevent ensure_chromium_installed from touching real browsers in unit tests.

    Patches the function at every import site (cli, web) so tests that exercise
    main() or serve_web_cli() don't attempt to download or launch Chromium.
    test_playwright_utils.py tests the function directly and is unaffected because
    it imports from qa_agent.playwright_utils, not from these call-site namespaces.
    """
    if "test_playwright_utils" in request.fspath.basename:
        yield
        return
    # Patch both the source and the cli call site so importlib.reload() in web
    # tests still picks up the mock rather than the real function.
    with patch("qa_agent.playwright_utils.ensure_chromium_installed"), \
         patch("qa_agent.cli.ensure_chromium_installed"):
        yield


@pytest.fixture
def mock_page():
    return _make_mock_page()


@pytest.fixture
def mock_playwright_factory(mock_page):
    factory, page, context, browser = make_mock_playwright_factory(mock_page)
    return factory


@pytest.fixture
def rich_session():
    return make_session_with_findings()


@pytest.fixture
def empty_session():
    return make_session()
