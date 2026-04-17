"""Per-page integration tests against the test-target fixture harness.

Each HTML file in tests/fixtures/test-target/ is designed to trigger exactly one
qa-agent finding. These tests run each page in focused mode and assert that the
intended finding is present.

Run with: pytest -m integration
"""

from __future__ import annotations

import json
import threading
from collections.abc import Generator
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import pytest

MANIFEST_PATH = Path(__file__).parent.parent / "fixtures" / "test-target" / "manifest.json"
TARGET_DIR = MANIFEST_PATH.parent


def _load_cases() -> list[dict[str, object]]:
    data: dict[str, list[dict[str, object]]] = json.loads(MANIFEST_PATH.read_text())
    return data["cases"]


@pytest.fixture(scope="session")
def target_fixture_server() -> Generator[str, None, None]:
    """Serve the test-target harness on a random port and yield its base URL."""

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(TARGET_DIR), **kwargs)

        def log_message(self, format, *args):  # noqa: A002
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.mark.integration
@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["filename"])
def test_target_page_triggers_intended_finding(case, target_fixture_server, tmp_path):
    """Each test-target page must produce its intended finding when run through qa-agent."""
    from qa_agent.agent import QAAgent
    from qa_agent.config import OutputFormat, TestConfig

    url = f"{target_fixture_server}/{case['filename']}"

    config = TestConfig(
        urls=[url],
        output_formats=[OutputFormat.JSON],
        output_dir=str(tmp_path),
        headless=True,
        test_wcag_compliance=case["wcag_compliance"],
    )
    session = QAAgent(config).run()

    findings = session.get_all_findings()
    titles = [f.title for f in findings]
    categories = {f.category.value for f in findings}

    expected_substring = case["expected_title"].lower()
    assert any(expected_substring in t.lower() for t in titles), (
        f"{case['filename']}: expected a finding containing {case['expected_title']!r}\n"
        f"  Got: {titles}"
    )

    expected_category = case["expected_category"]
    assert expected_category in categories, (
        f"{case['filename']}: expected category {expected_category!r} in findings\n"
        f"  Got categories: {categories}"
    )
