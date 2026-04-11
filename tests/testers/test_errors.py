"""Tests for qa_agent/testers/errors.py — console and network error detection."""

from __future__ import annotations

from unittest.mock import MagicMock

from qa_agent.config import TestConfig
from qa_agent.models import FindingCategory, Severity
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

    def test_non_severe_error_is_medium_severity(self):
        """Errors without 'uncaught/TypeError/etc' patterns → MEDIUM severity."""
        detector = _detector()
        detector.console_messages = [
            {"type": "error", "text": "Custom application error: operation failed", "location": "app.js:50"},
        ]
        findings = detector.run()
        console_findings = [f for f in findings if f.category == FindingCategory.CONSOLE_ERROR]
        assert len(console_findings) == 1
        assert console_findings[0].severity == Severity.MEDIUM


class TestConsoleWarnings:
    def test_more_than_3_significant_warnings_produces_finding(self):
        """More than 3 significant warnings → a single LOW finding."""
        detector = _detector()
        detector.console_messages = [
            {"type": "warning", "text": "deprecated: use new API instead", "location": ""},
            {"type": "warning", "text": "security violation detected", "location": ""},
            {"type": "warning", "text": "performance issue: slow render", "location": ""},
            {"type": "warning", "text": "accessibility warning: missing label", "location": ""},
        ]
        findings = detector.run()
        warning_findings = [f for f in findings if "warning" in f.title.lower()]
        assert len(warning_findings) >= 1
        assert warning_findings[0].severity == Severity.LOW

    def test_3_or_fewer_significant_warnings_no_finding(self):
        """3 or fewer significant warnings → no finding (threshold not met)."""
        detector = _detector()
        detector.console_messages = [
            {"type": "warning", "text": "deprecated: old method", "location": ""},
            {"type": "warning", "text": "security issue", "location": ""},
            {"type": "warning", "text": "mixed content warning", "location": ""},
        ]
        findings = detector.run()
        warning_findings = [f for f in findings if "warning" in f.title.lower()]
        assert len(warning_findings) == 0

    def test_non_significant_warnings_ignored(self):
        """Warnings without significant patterns → not counted."""
        detector = _detector()
        detector.console_messages = [
            {"type": "warning", "text": "some generic warning", "location": ""},
            {"type": "warning", "text": "another harmless warning", "location": ""},
            {"type": "warning", "text": "yet another warning", "location": ""},
            {"type": "warning", "text": "fourth generic warning", "location": ""},
        ]
        findings = detector.run()
        warning_findings = [f for f in findings if "warning" in f.title.lower()]
        assert len(warning_findings) == 0


class TestNetworkErrors:
    def test_404_produces_finding(self):
        detector = _detector()
        detector.network_errors = [
            {"url": "https://example.com/missing.js", "status": 404, "status_text": "Not Found"},
        ]
        findings = detector.run()
        assert any(f.category == FindingCategory.NETWORK_ERROR for f in findings)

    def test_500_produces_high_severity_finding(self):
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

    def test_502_produces_high_severity_finding(self):
        """502 Bad Gateway → HIGH severity."""
        detector = _detector()
        detector.network_errors = [
            {"url": "https://example.com/api", "status": 502, "status_text": "Bad Gateway"},
        ]
        findings = detector.run()
        network_findings = [f for f in findings if f.category == FindingCategory.NETWORK_ERROR]
        assert any(f.severity == Severity.HIGH for f in network_findings)

    def test_503_produces_high_severity_finding(self):
        """503 Service Unavailable → HIGH severity."""
        detector = _detector()
        detector.network_errors = [
            {"url": "https://example.com/api", "status": 503, "status_text": "Service Unavailable"},
        ]
        findings = detector.run()
        network_findings = [f for f in findings if f.category == FindingCategory.NETWORK_ERROR]
        assert any(f.severity == Severity.HIGH for f in network_findings)

    def test_403_produces_medium_severity_finding(self):
        """403 Forbidden → MEDIUM severity."""
        detector = _detector()
        detector.network_errors = [
            {"url": "https://example.com/secret", "status": 403, "status_text": "Forbidden"},
        ]
        findings = detector.run()
        network_findings = [f for f in findings if f.category == FindingCategory.NETWORK_ERROR]
        assert any(f.severity == Severity.MEDIUM for f in network_findings)
        assert any("forbidden" in f.title.lower() for f in network_findings)

    def test_request_failed_produces_high_severity_finding(self):
        """Failed request (no status code) → HIGH severity."""
        detector = _detector()
        detector.network_errors = [
            {"url": "https://example.com/api", "failure": "net::ERR_CONNECTION_REFUSED"},
        ]
        findings = detector.run()
        network_findings = [f for f in findings if f.category == FindingCategory.NETWORK_ERROR]
        assert any(f.severity == Severity.HIGH for f in network_findings)

    def test_unknown_status_produces_finding_with_generic_title(self):
        """Other HTTP status codes produce a generic title."""
        detector = _detector()
        detector.network_errors = [
            {"url": "https://example.com/redirect", "status": 301, "status_text": "Moved Permanently"},
        ]
        findings = detector.run()
        network_findings = [f for f in findings if f.category == FindingCategory.NETWORK_ERROR]
        assert len(network_findings) >= 1
        assert "301" in network_findings[0].title


class TestJSErrors:
    def test_js_exception_produces_high_severity_finding(self):
        """JS exceptions from pageerror events → HIGH severity CONSOLE_ERROR finding."""
        detector = _detector()
        detector.js_errors = [
            {
                "message": "TypeError: Cannot set property 'x' of undefined",
                "timestamp": "2024-01-01T00:00:00",
            }
        ]
        findings = detector.run()
        js_findings = [f for f in findings if f.category == FindingCategory.CONSOLE_ERROR]
        assert any(f.severity == Severity.HIGH for f in js_findings)
        assert any("exception" in f.title.lower() for f in js_findings)

    def test_multiple_js_errors_all_produce_findings(self):
        """Each JS error produces a separate finding."""
        detector = _detector()
        detector.js_errors = [
            {"message": "Error 1", "timestamp": "2024-01-01T00:00:00"},
            {"message": "Error 2", "timestamp": "2024-01-01T00:00:01"},
        ]
        findings = detector.run()
        js_findings = [f for f in findings if "exception" in f.title.lower()]
        assert len(js_findings) == 2


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

    def test_console_handler_captures_messages(self):
        """The registered console handler should append to console_messages."""
        page = MagicMock()
        page.url = "https://example.com"
        config = TestConfig(urls=["https://example.com"])
        detector = ErrorDetector(page, config)
        detector.attach_listeners()

        # Extract the callback registered for "console"
        calls = page.on.call_args_list
        console_call = next(c for c in calls if c[0][0] == "console")
        on_console = console_call[0][1]

        # Simulate a console message
        mock_msg = MagicMock()
        mock_msg.type = "error"
        mock_msg.text = "Test error"
        mock_msg.location = {"url": "app.js", "lineNumber": 10}
        on_console(mock_msg)

        assert len(detector.console_messages) == 1
        assert detector.console_messages[0]["type"] == "error"

    def test_pageerror_handler_captures_js_errors(self):
        """The registered pageerror handler should append to js_errors."""
        page = MagicMock()
        page.url = "https://example.com"
        config = TestConfig(urls=["https://example.com"])
        detector = ErrorDetector(page, config)
        detector.attach_listeners()

        calls = page.on.call_args_list
        pageerror_call = next(c for c in calls if c[0][0] == "pageerror")
        on_pageerror = pageerror_call[0][1]

        on_pageerror(RuntimeError("uncaught js error"))

        assert len(detector.js_errors) == 1
        assert "uncaught js error" in detector.js_errors[0]["message"]

    def test_response_handler_captures_4xx_errors(self):
        """The response handler should record 4xx/5xx status codes."""
        page = MagicMock()
        page.url = "https://example.com"
        config = TestConfig(urls=["https://example.com"])
        detector = ErrorDetector(page, config)
        detector.attach_listeners()

        calls = page.on.call_args_list
        response_call = next(c for c in calls if c[0][0] == "response")
        on_response = response_call[0][1]

        mock_response = MagicMock()
        mock_response.status = 404
        mock_response.url = "https://example.com/missing"
        mock_response.status_text = "Not Found"
        on_response(mock_response)

        assert len(detector.network_errors) == 1
        assert detector.network_errors[0]["status"] == 404

    def test_response_handler_ignores_2xx(self):
        """The response handler should NOT record 2xx responses."""
        page = MagicMock()
        page.url = "https://example.com"
        config = TestConfig(urls=["https://example.com"])
        detector = ErrorDetector(page, config)
        detector.attach_listeners()

        calls = page.on.call_args_list
        response_call = next(c for c in calls if c[0][0] == "response")
        on_response = response_call[0][1]

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.url = "https://example.com/"
        on_response(mock_response)

        assert len(detector.network_errors) == 0

    def test_request_failed_handler_captures_failures(self):
        """The requestfailed handler should record failed requests."""
        page = MagicMock()
        page.url = "https://example.com"
        config = TestConfig(urls=["https://example.com"])
        detector = ErrorDetector(page, config)
        detector.attach_listeners()

        calls = page.on.call_args_list
        reqfail_call = next(c for c in calls if c[0][0] == "requestfailed")
        on_request_failed = reqfail_call[0][1]

        mock_request = MagicMock()
        mock_request.url = "https://example.com/api"
        mock_request.failure = "net::ERR_CONNECTION_REFUSED"
        on_request_failed(mock_request)

        assert len(detector.network_errors) == 1
        assert detector.network_errors[0]["failure"] == "net::ERR_CONNECTION_REFUSED"


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


class TestBrokenImages:
    def test_visible_broken_image_produces_finding(self):
        """Visible broken images → HIGH severity NETWORK_ERROR finding."""
        page = MagicMock()
        page.url = "https://example.com"
        page.evaluate.return_value = [
            {"src": "/images/hero.png", "alt": "Hero image", "visible": True}
        ]

        config = TestConfig(urls=["https://example.com"])
        detector = ErrorDetector(page, config)
        detector._check_broken_images()

        broken_findings = [f for f in detector.findings if "broken" in f.title.lower() and "image" in f.title.lower()]
        assert len(broken_findings) >= 1
        assert broken_findings[0].severity == Severity.HIGH

    def test_invisible_broken_image_no_finding(self):
        """Broken images that are not visible → no finding."""
        page = MagicMock()
        page.url = "https://example.com"
        page.evaluate.return_value = [
            {"src": "/images/hidden.png", "alt": "", "visible": False}
        ]

        config = TestConfig(urls=["https://example.com"])
        detector = ErrorDetector(page, config)
        detector._check_broken_images()

        broken_findings = [f for f in detector.findings if "image" in f.title.lower()]
        assert len(broken_findings) == 0

    def test_no_broken_images_no_finding(self):
        """No broken images → no finding."""
        page = MagicMock()
        page.url = "https://example.com"
        page.evaluate.return_value = []

        config = TestConfig(urls=["https://example.com"])
        detector = ErrorDetector(page, config)
        detector._check_broken_images()

        assert detector.findings == []


class TestBrokenLinks:
    def test_empty_href_link_produces_finding(self):
        """Links with empty href and no JS handler → finding."""
        page = MagicMock()
        page.url = "https://example.com"
        page.evaluate.return_value = [
            {"href": "#", "text": "Click here", "issue": "empty_href"}
        ]

        config = TestConfig(urls=["https://example.com"])
        detector = ErrorDetector(page, config)
        detector._check_broken_links()

        empty_findings = [f for f in detector.findings if "empty" in f.title.lower()]
        assert len(empty_findings) >= 1
        assert empty_findings[0].severity == Severity.LOW

    def test_missing_anchor_produces_finding(self):
        """Links pointing to non-existent IDs → MEDIUM finding."""
        page = MagicMock()
        page.url = "https://example.com"
        page.evaluate.return_value = [
            {"href": "#nonexistent-section", "text": "Jump to section", "issue": "missing_anchor"}
        ]

        config = TestConfig(urls=["https://example.com"])
        detector = ErrorDetector(page, config)
        detector._check_broken_links()

        anchor_findings = [f for f in detector.findings if "anchor" in f.title.lower()]
        assert len(anchor_findings) >= 1
        assert anchor_findings[0].severity == Severity.MEDIUM

    def test_valid_links_no_finding(self):
        """No suspicious links → no finding."""
        page = MagicMock()
        page.url = "https://example.com"
        page.evaluate.return_value = []

        config = TestConfig(urls=["https://example.com"])
        detector = ErrorDetector(page, config)
        detector._check_broken_links()

        assert detector.findings == []


class TestMixedContent:
    def test_active_mixed_content_produces_high_severity_finding(self):
        """Scripts or stylesheets over HTTP on HTTPS page → HIGH severity."""
        page = MagicMock()
        page.url = "https://example.com"
        page.evaluate.return_value = [
            {"type": "script", "url": "http://cdn.example.com/analytics.js"},
        ]

        config = TestConfig(urls=["https://example.com"])
        detector = ErrorDetector(page, config)
        detector._check_mixed_content()

        active_findings = [f for f in detector.findings if "active" in f.title.lower()]
        assert len(active_findings) >= 1
        assert active_findings[0].severity == Severity.HIGH

    def test_passive_mixed_content_produces_medium_severity_finding(self):
        """Images or iframes over HTTP on HTTPS page → MEDIUM severity."""
        page = MagicMock()
        page.url = "https://example.com"
        page.evaluate.return_value = [
            {"type": "image", "url": "http://example.com/logo.png"},
        ]

        config = TestConfig(urls=["https://example.com"])
        detector = ErrorDetector(page, config)
        detector._check_mixed_content()

        passive_findings = [f for f in detector.findings if "passive" in f.title.lower()]
        assert len(passive_findings) >= 1
        assert passive_findings[0].severity == Severity.MEDIUM

    def test_http_page_skipped(self):
        """HTTP page → mixed content check is a no-op."""
        page = MagicMock()
        page.url = "http://example.com"  # HTTP, not HTTPS

        config = TestConfig(urls=["http://example.com"])
        detector = ErrorDetector(page, config)
        detector._check_mixed_content()

        assert detector.findings == []
        page.evaluate.assert_not_called()

    def test_no_mixed_content_no_finding(self):
        """HTTPS page with no mixed content → no finding."""
        page = MagicMock()
        page.url = "https://example.com"
        page.evaluate.return_value = []  # no mixed content

        config = TestConfig(urls=["https://example.com"])
        detector = ErrorDetector(page, config)
        detector._check_mixed_content()

        assert detector.findings == []

    def test_both_active_and_passive_mixed_content(self):
        """Both active and passive mixed content → two findings."""
        page = MagicMock()
        page.url = "https://example.com"
        page.evaluate.return_value = [
            {"type": "script", "url": "http://cdn.example.com/app.js"},
            {"type": "image", "url": "http://example.com/banner.png"},
        ]

        config = TestConfig(urls=["https://example.com"])
        detector = ErrorDetector(page, config)
        detector._check_mixed_content()

        assert len(detector.findings) == 2
        titles = [f.title for f in detector.findings]
        assert any("active" in t.lower() for t in titles)
        assert any("passive" in t.lower() for t in titles)
