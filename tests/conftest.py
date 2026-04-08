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
    browser.new_context.return_value = context
    chromium.launch.return_value = browser
    pw.chromium = chromium

    @contextmanager
    def factory():
        yield pw

    return factory, page, context, browser


# ---------------------------------------------------------------------------
# pytest fixtures
# ---------------------------------------------------------------------------

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
