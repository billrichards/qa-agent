"""Integration smoke tests — real Playwright against the local fixture site.

Run with: pytest -m integration
Excluded from the default pytest run (requires Playwright browsers installed).
"""

from __future__ import annotations

import json
import os
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Generator

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "site"


@pytest.fixture(scope="session")
def fixture_server() -> Generator[str, None, None]:
    """Serve the fixture HTML site on a random port and yield its base URL."""

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(FIXTURES_DIR), **kwargs)

        def log_message(self, format, *args):
            pass  # Silence HTTP access logs during tests

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.mark.integration
class TestSmoke:
    def test_index_produces_accessibility_finding(self, fixture_server, tmp_path):
        """The fixture index.html has an image without alt — must produce a finding."""
        from qa_agent.agent import QAAgent
        from qa_agent.config import OutputFormat, TestConfig

        config = TestConfig(
            urls=[f"{fixture_server}/index.html"],
            output_formats=[OutputFormat.JSON],
            output_dir=str(tmp_path),
            headless=True,
            test_keyboard=False,
            test_mouse=False,
        )
        agent = QAAgent(config)
        session = agent.run()

        all_findings = session.get_all_findings()
        categories = [f.category.value for f in all_findings]
        assert "accessibility" in categories, (
            f"Expected an accessibility finding from missing alt text. Got: {categories}"
        )

    def test_index_produces_form_finding(self, fixture_server, tmp_path):
        """The fixture index.html has an unlabeled input — must produce a form finding."""
        from qa_agent.agent import QAAgent
        from qa_agent.config import OutputFormat, TestConfig

        config = TestConfig(
            urls=[f"{fixture_server}/index.html"],
            output_formats=[OutputFormat.JSON],
            output_dir=str(tmp_path),
            headless=True,
            test_keyboard=False,
            test_mouse=False,
            test_accessibility=False,
        )
        agent = QAAgent(config)
        session = agent.run()

        all_findings = session.get_all_findings()
        categories = [f.category.value for f in all_findings]
        assert "form_handling" in categories, (
            f"Expected a form_handling finding from unlabeled input. Got: {categories}"
        )

    def test_index_produces_console_error_finding(self, fixture_server, tmp_path):
        """The fixture index.html calls console.error — must produce a console_error finding."""
        from qa_agent.agent import QAAgent
        from qa_agent.config import OutputFormat, TestConfig

        config = TestConfig(
            urls=[f"{fixture_server}/index.html"],
            output_formats=[OutputFormat.JSON],
            output_dir=str(tmp_path),
            headless=True,
            test_keyboard=False,
            test_mouse=False,
            test_forms=False,
            test_accessibility=False,
        )
        agent = QAAgent(config)
        session = agent.run()

        all_findings = session.get_all_findings()
        categories = [f.category.value for f in all_findings]
        assert "console_error" in categories, (
            f"Expected a console_error finding from console.error call. Got: {categories}"
        )

    def test_json_report_written_and_parseable(self, fixture_server, tmp_path):
        """After a run, a valid JSON report file must exist in the output directory."""
        from qa_agent.agent import QAAgent
        from qa_agent.config import OutputFormat, TestConfig

        config = TestConfig(
            urls=[f"{fixture_server}/index.html"],
            output_formats=[OutputFormat.JSON],
            output_dir=str(tmp_path),
            headless=True,
        )
        agent = QAAgent(config)
        agent.run()

        json_files = list(tmp_path.rglob("*.json"))
        assert len(json_files) >= 1, "No JSON report file written"

        data = json.loads(json_files[0].read_text())
        assert "meta" in data
        assert "findings" in data

    def test_explore_mode_visits_linked_page(self, fixture_server, tmp_path):
        """In explore mode, page2.html (linked from index.html) must also be visited."""
        from qa_agent.agent import QAAgent
        from qa_agent.config import OutputFormat, TestConfig, TestMode

        config = TestConfig(
            urls=[f"{fixture_server}/index.html"],
            mode=TestMode.EXPLORE,
            output_formats=[OutputFormat.JSON],
            output_dir=str(tmp_path),
            headless=True,
            max_depth=1,
            max_pages=5,
        )
        agent = QAAgent(config)
        session = agent.run()

        visited_urls = [p.url for p in session.pages_tested]
        assert any("page2" in url for url in visited_urls), (
            f"Expected page2.html to be visited in explore mode. Visited: {visited_urls}"
        )

    def test_explore_mode_respects_max_pages(self, fixture_server, tmp_path):
        """max_pages=1 must halt after testing only one page."""
        from qa_agent.agent import QAAgent
        from qa_agent.config import OutputFormat, TestConfig, TestMode

        config = TestConfig(
            urls=[f"{fixture_server}/index.html"],
            mode=TestMode.EXPLORE,
            output_formats=[OutputFormat.JSON],
            output_dir=str(tmp_path),
            headless=True,
            max_depth=3,
            max_pages=1,
        )
        agent = QAAgent(config)
        session = agent.run()
        assert len(session.pages_tested) <= 1

    def test_no_exception_raised(self, fixture_server, tmp_path):
        """A clean run against the fixture site must not raise any exception."""
        from qa_agent.agent import QAAgent
        from qa_agent.config import OutputFormat, TestConfig

        config = TestConfig(
            urls=[f"{fixture_server}/index.html"],
            output_formats=[OutputFormat.JSON],
            output_dir=str(tmp_path),
            headless=True,
        )
        agent = QAAgent(config)
        session = agent.run()  # must not raise
        assert session is not None
