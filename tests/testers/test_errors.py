"""Tests for qa_agent/testers/errors.py — console and network error detection."""

from __future__ import annotations

from unittest.mock import MagicMock

from qa_agent.config import TestConfig
from qa_agent.models import FindingCategory
from qa_agent.testers.errors import ErrorDetector


def _detector(page=None) -> ErrorDetector:
    if page is None:
        page = MagicMock()
        page.url = "https://example.com"
    config = TestConfig(urls=["https://example.com"])
    return ErrorDetector(page, config)


class TestConsoleErrors:
    def test_console_error_produces_finding(self):
        detector = _detector()
        detector.console_messages = [
            {"type": "error", "text": "Uncaught ReferenceError: foo is not defined", "location": "app.js:10"},
        ]
        findings = detector.run()
        assert any(f.category == FindingCategory.CONSOLE_ERROR for f in findings)

    def test_console_error_severity_high_for_uncaught(self):
        detector = _detector()
        detector.console_messages = [
            {"type": "error", "text": "Uncaught TypeError: Cannot read property 'x' of null", "location": "app.js:5"},
        ]
        from qa_agent.models import Severity
        findings = detector.run()
        console_findings = [f for f in findings if f.category == FindingCategory.CONSOLE_ERROR]
        assert any(f.severity == Severity.HIGH for f in console_findings)

    def test_no_console_errors_no_finding(self):
        detector = _detector()
        detector.console_messages = []
        findings = detector.run()
        console_findings = [f for f in findings if f.category == FindingCategory.CONSOLE_ERROR]
        assert len(console_findings) == 0

    def test_multiple_console_errors_grouped(self):
        """Identical error text should be grouped, not produce N findings."""
        detector = _detector()
        same_error = "Uncaught ReferenceError: bar is not defined"
        detector.console_messages = [
            {"type": "error", "text": same_error, "location": "app.js:10"},
            {"type": "error", "text": same_error, "location": "app.js:10"},
            {"type": "error", "text": same_error, "location": "app.js:10"},
        ]
        findings = detector.run()
        console_findings = [f for f in findings if f.category == FindingCategory.CONSOLE_ERROR]
        # Should be grouped into 1 finding, not 3
        assert len(console_findings) == 1


class TestNetworkErrors:
    def test_404_produces_finding(self):
        detector = _detector()
        detector.network_errors = [
            {"url": "https://example.com/missing.js", "status": 404, "status_text": "Not Found"},
        ]
        findings = detector.run()
        assert any(f.category == FindingCategory.NETWORK_ERROR for f in findings)

    def test_500_produces_high_severity_finding(self):
        from qa_agent.models import Severity
        detector = _detector()
        detector.network_errors = [
            {"url": "https://example.com/api/data", "status": 500, "status_text": "Server Error"},
        ]
        findings = detector.run()
        network_findings = [f for f in findings if f.category == FindingCategory.NETWORK_ERROR]
        assert any(f.severity == Severity.HIGH for f in network_findings)

    def test_no_network_errors_no_finding(self):
        detector = _detector()
        detector.network_errors = []
        findings = detector.run()
        network_findings = [f for f in findings if f.category == FindingCategory.NETWORK_ERROR]
        assert len(network_findings) == 0


class TestAttachListeners:
    def test_attach_listeners_registers_handlers(self):
        page = MagicMock()
        page.url = "https://example.com"
        page.evaluate.return_value = []
        config = TestConfig(urls=["https://example.com"])
        detector = ErrorDetector(page, config)
        detector.attach_listeners()
        # on() called for console, pageerror, response, requestfailed
        assert page.on.call_count >= 4

    def test_attach_listeners_idempotent(self):
        page = MagicMock()
        page.url = "https://example.com"
        config = TestConfig(urls=["https://example.com"])
        detector = ErrorDetector(page, config)
        detector.attach_listeners()
        first_count = page.on.call_count
        detector.attach_listeners()
        # Second call should not add more listeners
        assert page.on.call_count == first_count


class TestGetSummary:
    def test_summary_contains_expected_keys(self):
        detector = _detector()
        summary = detector.get_summary()
        assert "console_errors" in summary
        assert "console_warnings" in summary
        assert "network_errors" in summary
        assert "js_exceptions" in summary

    def test_summary_counts_correctly(self):
        detector = _detector()
        detector.console_messages = [
            {"type": "error", "text": "err1", "location": ""},
            {"type": "warning", "text": "warn1", "location": ""},
        ]
        detector.network_errors = [{"url": "x", "status": 404}]
        summary = detector.get_summary()
        assert summary["console_errors"] == 1
        assert summary["console_warnings"] == 1
        assert summary["network_errors"] == 1
