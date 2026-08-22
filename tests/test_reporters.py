"""Tests for qa_agent/reporters/* — output correctness, injection safety."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from qa_agent.models import TestSession
from qa_agent.reporters.console import ConsoleReporter
from qa_agent.reporters.json_reporter import JSONReporter
from qa_agent.reporters.markdown import MarkdownReporter
from tests.conftest import (
    make_finding,
    make_multi_viewport_session,
    make_session,
    make_session_with_findings,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _xss_session():
    """Session with XSS payload in finding title, description, and raw_error."""
    return make_session(findings=[
        make_finding(
            title='<script>alert("xss")</script>',
            description='</pre><img src=x onerror=alert(1)>',
            raw_error='</code><script>document.cookie</script>',
        )
    ])


# ---------------------------------------------------------------------------
# ConsoleReporter
# ---------------------------------------------------------------------------

class TestConsoleReporter:
    def test_generate_does_not_raise(self, tmp_path, capsys):
        reporter = ConsoleReporter(str(tmp_path))
        reporter.generate(make_session_with_findings())

    def test_generate_returns_string(self, tmp_path):
        reporter = ConsoleReporter(str(tmp_path))
        result = reporter.generate(make_session())
        assert isinstance(result, str)

    def test_print_finding_does_not_raise(self, tmp_path, capsys):
        reporter = ConsoleReporter(str(tmp_path))
        reporter.print_finding(make_finding())

    def test_output_contains_severity(self, tmp_path, capsys):
        reporter = ConsoleReporter(str(tmp_path), use_colors=False)
        reporter.generate(make_session_with_findings())
        out = capsys.readouterr().out
        assert "CRITICAL" in out or "HIGH" in out


# ---------------------------------------------------------------------------
# MarkdownReporter
# ---------------------------------------------------------------------------

class TestMarkdownReporter:
    def test_generate_creates_file(self, tmp_path):
        reporter = MarkdownReporter(str(tmp_path))
        path = reporter.generate(make_session_with_findings())
        assert path.endswith(".md")
        from pathlib import Path
        assert Path(path).exists()

    def test_report_contains_session_id(self, tmp_path):
        reporter = MarkdownReporter(str(tmp_path))
        path = reporter.generate(make_session(session_id="abc12345"))
        content = open(path, encoding="utf-8").read()
        assert "abc12345" in content

    def test_report_contains_finding_title(self, tmp_path):
        reporter = MarkdownReporter(str(tmp_path))
        session = make_session(findings=[make_finding(title="Unique Finding Title XYZ")])
        path = reporter.generate(session)
        content = open(path, encoding="utf-8").read()
        assert "Unique Finding Title XYZ" in content

    def test_report_contains_severity_counts(self, tmp_path):
        reporter = MarkdownReporter(str(tmp_path))
        path = reporter.generate(make_session_with_findings())
        content = open(path, encoding="utf-8").read()
        assert "CRITICAL" in content or "critical" in content.lower()

    def test_empty_session_generates_ok(self, tmp_path):
        reporter = MarkdownReporter(str(tmp_path))
        path = reporter.generate(make_session())
        assert open(path, encoding="utf-8").read()

    def test_xss_title_present_in_output(self, tmp_path):
        """Document current behaviour: XSS payload appears in markdown.

        NOTE: The markdown library does NOT escape raw HTML by default, so
        a finding title containing <script> will be passed through verbatim
        when rendered via Flask's /files/*.md endpoint. This test records
        the current (insecure) behaviour as a known issue to fix.
        """
        reporter = MarkdownReporter(str(tmp_path))
        path = reporter.generate(_xss_session())
        content = open(path, encoding="utf-8").read()
        # The raw content is present in the markdown file
        assert 'script' in content.lower()
        # BUG: this raw HTML will execute if served via /files/ without sanitisation.
        # Fix: escape HTML in finding titles/descriptions before writing to markdown,
        # or pass output="escape" to markdown.markdown() in server.py.

    def test_deduplication_note_when_raw_count_greater(self, tmp_path):
        """When deduplicated count < raw count, a note appears in the report."""
        from unittest.mock import patch

        session = make_session_with_findings()
        # The raw count is 5. Make deduplicated return only 2 findings.
        deduplicated = session.get_all_findings()[:2]
        reporter = MarkdownReporter(str(tmp_path))

        with patch.object(session, "get_deduplicated_findings", return_value=deduplicated):
            path = reporter.generate(session)

        content = open(path, encoding="utf-8").read()
        assert "consolidated" in content or "unique" in content

    def test_no_pages_tested_section(self, tmp_path):
        """Session with no pages tested shows a warning section."""
        session = TestSession(
            session_id="empty-test",
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            config_summary={"mode": "explore"},
        )
        # No pages added → pages_tested is empty
        reporter = MarkdownReporter(str(tmp_path))
        path = reporter.generate(session)
        content = open(path, encoding="utf-8").read()
        assert "No Pages Tested" in content or "no pages" in content.lower()

    def test_recording_path_in_report(self, tmp_path):
        """When session has a recording_path, it appears in the report."""
        session = make_session()
        session.recording_path = "/tmp/recording.webm"
        reporter = MarkdownReporter(str(tmp_path))
        path = reporter.generate(session)
        content = open(path, encoding="utf-8").read()
        assert "recording.webm" in content

    def test_format_finding_with_element_selector(self, tmp_path):
        """Finding with element_selector shows the selector in the report."""
        finding = make_finding(element_selector="button#submit")
        session = make_session(findings=[finding])
        reporter = MarkdownReporter(str(tmp_path))
        path = reporter.generate(session)
        content = open(path, encoding="utf-8").read()
        assert "button#submit" in content

    def test_format_finding_with_element_text(self, tmp_path):
        """Finding with element_text shows the text in the report."""
        finding = make_finding(element_text="Submit Form")
        session = make_session(findings=[finding])
        reporter = MarkdownReporter(str(tmp_path))
        path = reporter.generate(session)
        content = open(path, encoding="utf-8").read()
        assert "Submit Form" in content

    def test_format_finding_with_expected_actual(self, tmp_path):
        """Finding with expected/actual behavior shows a comparison table."""
        finding = make_finding(
            expected_behavior="Button should be focusable",
            actual_behavior="Button has tabindex=-1",
        )
        session = make_session(findings=[finding])
        reporter = MarkdownReporter(str(tmp_path))
        path = reporter.generate(session)
        content = open(path, encoding="utf-8").read()
        assert "Button should be focusable" in content
        assert "tabindex" in content

    def test_format_finding_with_steps_to_reproduce(self, tmp_path):
        """Finding with steps_to_reproduce lists the steps."""
        finding = make_finding(steps_to_reproduce=["Open the page", "Click Login", "Check focus"])
        session = make_session(findings=[finding])
        reporter = MarkdownReporter(str(tmp_path))
        path = reporter.generate(session)
        content = open(path, encoding="utf-8").read()
        assert "Open the page" in content
        assert "Click Login" in content

    def test_format_finding_with_screenshot(self, tmp_path):
        """Finding with screenshot_path includes relative screenshot link."""
        screenshot = tmp_path / "shot.png"
        screenshot.write_bytes(b"fake png")
        finding = make_finding(screenshot_path=str(screenshot))
        session = make_session(findings=[finding])
        reporter = MarkdownReporter(str(tmp_path))
        path = reporter.generate(session)
        content = open(path, encoding="utf-8").read()
        assert "Screenshot" in content
        assert "shot.png" in content

    def test_format_finding_with_metadata(self, tmp_path):
        """Finding with metadata shows a JSON details block."""
        finding = make_finding(metadata={"count": 3, "urls": ["https://example.com"]})
        session = make_session(findings=[finding])
        reporter = MarkdownReporter(str(tmp_path))
        path = reporter.generate(session)
        content = open(path, encoding="utf-8").read()
        assert "Additional Details" in content or "details" in content.lower()
        assert "count" in content

    def test_format_finding_with_raw_error(self, tmp_path):
        """Finding with raw_error includes the error in a code block."""
        finding = make_finding(raw_error="TypeError: Cannot read property 'x' of undefined")
        session = make_session(findings=[finding])
        reporter = MarkdownReporter(str(tmp_path))
        path = reporter.generate(session)
        content = open(path, encoding="utf-8").read()
        assert "Raw Error" in content
        assert "TypeError" in content

    def test_format_finding_with_affected_urls(self, tmp_path):
        """Finding with affected_urls shows the URL pattern and collapsible list."""
        finding = make_finding()
        finding.affected_urls = ["https://example.com/a", "https://example.com/b"]
        session = make_session(findings=[finding])
        reporter = MarkdownReporter(str(tmp_path))
        path = reporter.generate(session)
        content = open(path, encoding="utf-8").read()
        assert "affects" in content or "Affected" in content

    def test_no_findings_shows_passed_message(self, tmp_path):
        """Session with pages but no findings shows 'No Issues Found'."""
        session = make_session(findings=[])
        reporter = MarkdownReporter(str(tmp_path))
        path = reporter.generate(session)
        content = open(path, encoding="utf-8").read()
        assert "No Issues Found" in content or "no issues" in content.lower()

    def test_session_with_end_time_shows_duration(self, tmp_path):
        """Session with end_time shows the duration in the report."""
        session = make_session()  # already has end_time set
        reporter = MarkdownReporter(str(tmp_path))
        path = reporter.generate(session)
        content = open(path, encoding="utf-8").read()
        assert "Duration" in content or "seconds" in content


# ---------------------------------------------------------------------------
# JSONReporter
# ---------------------------------------------------------------------------

class TestJSONReporter:
    def test_generate_creates_valid_json_file(self, tmp_path):
        reporter = JSONReporter(str(tmp_path))
        path = reporter.generate(make_session_with_findings())
        data = json.loads(open(path, encoding="utf-8").read())
        assert "meta" in data
        assert "summary" in data
        assert "findings" in data

    def test_total_findings_is_integer(self, tmp_path):
        reporter = JSONReporter(str(tmp_path))
        path = reporter.generate(make_session_with_findings())
        data = json.loads(open(path, encoding="utf-8").read())
        assert isinstance(data["summary"]["total_findings"], int)

    def test_pages_tested_is_integer(self, tmp_path):
        reporter = JSONReporter(str(tmp_path))
        path = reporter.generate(make_session())
        data = json.loads(open(path, encoding="utf-8").read())
        assert isinstance(data["summary"]["pages_tested"], int)

    def test_screenshot_path_is_string_or_null(self, tmp_path):
        reporter = JSONReporter(str(tmp_path))
        session = make_session(findings=[
            make_finding(screenshot_path="/tmp/shot.png"),
            make_finding(),  # no screenshot
        ])
        path = reporter.generate(session)
        data = json.loads(open(path, encoding="utf-8").read())
        for finding in data["findings"]:
            assert finding["screenshot_path"] is None or isinstance(finding["screenshot_path"], str)

    def test_get_json_string_does_not_write_file(self, tmp_path):
        reporter = JSONReporter(str(tmp_path))
        result = reporter.get_json_string(make_session())
        assert isinstance(result, str)
        data = json.loads(result)
        assert "meta" in data

    def test_xss_in_json_is_present_but_data_only(self, tmp_path):
        """JSON output stores the raw string — it's data, not HTML.

        A finding title containing <script> is fine in JSON since it's just
        a data value. The risk is in HTML rendering contexts (markdown/PDF).
        The JSON reporter itself escapes nothing (json.dumps handles it).
        """
        reporter = JSONReporter(str(tmp_path))
        path = reporter.generate(_xss_session())
        # Must parse without error
        data = json.loads(open(path, encoding="utf-8").read())
        # The raw string is preserved in the data
        titles = [f["title"] for f in data["findings"]]
        assert any("script" in t.lower() for t in titles)

    def test_severity_values_are_strings(self, tmp_path):
        reporter = JSONReporter(str(tmp_path))
        path = reporter.generate(make_session_with_findings())
        data = json.loads(open(path, encoding="utf-8").read())
        for finding in data["findings"]:
            assert isinstance(finding["severity"], str)

    def test_category_values_are_strings(self, tmp_path):
        reporter = JSONReporter(str(tmp_path))
        path = reporter.generate(make_session_with_findings())
        data = json.loads(open(path, encoding="utf-8").read())
        for finding in data["findings"]:
            assert isinstance(finding["category"], str)


# ---------------------------------------------------------------------------
# PDFReporter
# ---------------------------------------------------------------------------

class TestPDFReporter:
    def test_pdf_smoke(self, tmp_path):
        """Smoke test: file created and non-empty. Skipped if weasyprint absent."""
        pytest.importorskip("weasyprint")
        from qa_agent.reporters.pdf import PDFReporter
        reporter = PDFReporter(str(tmp_path))
        path = reporter.generate(make_session_with_findings())
        from pathlib import Path
        assert Path(path).exists()
        assert Path(path).stat().st_size > 0


# ---------------------------------------------------------------------------
# Viewport reporting
# ---------------------------------------------------------------------------

class TestViewportReporting:
    """Every reporter must distinguish findings by the viewport they came from.

    The same page is swept once per viewport, so without this the reports read
    as unexplained duplicates -- and a mobile-only bug is indistinguishable
    from its desktop namesake.
    """

    def test_markdown_lists_viewports_and_breakdown(self, tmp_path):
        session = make_multi_viewport_session()
        reporter = MarkdownReporter(str(tmp_path))
        content = Path(reporter.generate(session)).read_text(encoding="utf-8")

        assert "**Viewports:** desktop, mobile" in content
        assert "Findings by Viewport" in content
        assert "| 📐 desktop | 1 |" in content
        assert "| 📐 mobile | 1 |" in content
        # Repeated URLs in "Pages Tested" are disambiguated by viewport.
        assert "Test Page — desktop" in content
        assert "Test Page — mobile" in content

    def test_markdown_omits_viewport_for_single_viewport_run(self, tmp_path):
        """A single-viewport report must look exactly as it did before."""
        session = make_session_with_findings()
        reporter = MarkdownReporter(str(tmp_path))
        content = Path(reporter.generate(session)).read_text(encoding="utf-8")

        assert "Findings by Viewport" not in content
        assert "**Viewports:**" not in content

    def test_json_exposes_viewport_fields(self, tmp_path):
        session = make_multi_viewport_session()
        reporter = JSONReporter(str(tmp_path))
        data = json.loads(Path(reporter.generate(session)).read_text(encoding="utf-8"))

        assert data["summary"]["viewports_tested"] == ["desktop", "mobile"]
        assert data["summary"]["findings_by_viewport"] == {"desktop": 1, "mobile": 1}

        pages = {(p["viewport"], p["viewport_width"], p["viewport_height"]) for p in data["pages"]}
        assert pages == {("desktop", 1920, 1080), ("mobile", 390, 844)}

        # Same title at two viewports stays two findings rather than merging.
        assert sorted(f["viewport"] for f in data["findings"]) == ["desktop", "mobile"]

    def test_console_prints_viewport_breakdown(self, capsys):
        session = make_multi_viewport_session()
        ConsoleReporter(use_colors=False).generate(session)
        out = capsys.readouterr().out

        assert "By Viewport:" in out
        assert "desktop: 1" in out
        assert "mobile: 1" in out

    def test_console_omits_viewport_for_single_viewport_run(self, capsys):
        ConsoleReporter(use_colors=False).generate(make_session_with_findings())
        out = capsys.readouterr().out
        assert "By Viewport:" not in out
        assert "Viewport:" not in out

    def test_console_viewport_banner_labels_sweep(self, capsys):
        ConsoleReporter(use_colors=False).print_viewport_start("mobile (390x844)")
        assert "mobile (390x844)" in capsys.readouterr().out

    def test_pdf_html_includes_viewport_sections(self):
        from qa_agent.reporters.pdf import PDFReporter

        html = PDFReporter()._build_html(make_multi_viewport_session())
        assert "Findings by Viewport" in html
        assert "Viewports:" in html
        assert "desktop" in html and "mobile" in html

    def test_pdf_html_omits_viewport_for_single_viewport_run(self):
        from qa_agent.reporters.pdf import PDFReporter

        html = PDFReporter()._build_html(make_session_with_findings())
        assert "Findings by Viewport" not in html
