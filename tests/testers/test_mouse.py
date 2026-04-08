"""Tests for qa_agent/testers/mouse.py — smoke tests and click target size."""

from __future__ import annotations

from unittest.mock import MagicMock

from qa_agent.config import TestConfig
from qa_agent.models import FindingCategory
from qa_agent.testers.mouse import MouseTester


def _tester(page=None) -> MouseTester:
    if page is None:
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value = MagicMock(count=MagicMock(return_value=0))
    config = TestConfig(urls=["https://example.com"])
    return MouseTester(page, config)


class TestMouseTesterSmoke:
    def test_run_returns_list(self):
        result = _tester().run()
        assert isinstance(result, list)

    def test_run_does_not_raise_on_empty_page(self):
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value = MagicMock(count=MagicMock(return_value=0))
        page.click.return_value = None
        _tester(page).run()


class TestClickTargetSizes:
    def test_small_targets_produce_finding(self):
        """More than 3 elements smaller than 44x44 → finding."""
        page = MagicMock()
        page.url = "https://example.com"

        # 5 tiny buttons
        small_element = MagicMock()
        small_element.is_visible.return_value = True
        small_element.evaluate.return_value = {
            "width": 10,
            "height": 10,
            "text": "x",
            "tag": "button",
        }

        mock_locator = MagicMock()
        mock_locator.count.return_value = 5
        mock_locator.nth.return_value = small_element
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        tester._test_click_target_sizes()

        assert any(f.category == FindingCategory.MOUSE_INTERACTION for f in tester.findings)

    def test_large_targets_no_finding(self):
        """Elements meeting the minimum size threshold should not flag."""
        page = MagicMock()
        page.url = "https://example.com"

        large_element = MagicMock()
        large_element.is_visible.return_value = True
        large_element.evaluate.return_value = {
            "width": 120,
            "height": 44,
            "text": "Submit",
            "tag": "button",
        }

        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.nth.return_value = large_element
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        tester._test_click_target_sizes()

        size_findings = [f for f in tester.findings if "small" in f.title.lower()]
        assert len(size_findings) == 0
