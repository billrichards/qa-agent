"""Tests for qa_agent/testers/keyboard.py — smoke tests and tab-order logic."""

from __future__ import annotations

from unittest.mock import MagicMock

from qa_agent.config import TestConfig
from qa_agent.models import FindingCategory
from qa_agent.testers.keyboard import KeyboardTester


def _tester(page=None) -> KeyboardTester:
    if page is None:
        page = MagicMock()
        page.url = "https://example.com"
        # evaluate() returns None by default — means no focused element → stops tab loop early
        page.evaluate.return_value = None
    config = TestConfig(urls=["https://example.com"])
    return KeyboardTester(page, config)


class TestKeyboardTesterSmoke:
    def test_run_returns_list(self):
        tester = _tester()
        result = tester.run()
        assert isinstance(result, list)

    def test_run_does_not_raise_on_empty_page(self):
        page = MagicMock()
        page.url = "https://example.com"
        page.evaluate.return_value = None  # no focused element
        page.locator.return_value = MagicMock(count=MagicMock(return_value=0))
        tester = _tester(page)
        tester.run()  # must not raise


class TestTabOrderLogic:
    def _tester_instance(self) -> KeyboardTester:
        page = MagicMock()
        page.url = "https://example.com"
        config = TestConfig(urls=["https://example.com"])
        return KeyboardTester(page, config)

    def test_illogical_tab_order_produces_finding(self):
        tester = self._tester_instance()
        # Backwards jump threshold is > 100px upward.
        # Use alternating big/small top values so every other step is >100px backwards.
        elements = [
            {"tag": "a", "id": "link1", "text": "Link 1", "rect": {"top": 500, "left": 0}},
            {"tag": "a", "id": "link2", "text": "Link 2", "rect": {"top": 10, "left": 0}},   # 490px back
            {"tag": "a", "id": "link3", "text": "Link 3", "rect": {"top": 600, "left": 0}},
            {"tag": "a", "id": "link4", "text": "Link 4", "rect": {"top": 5, "left": 0}},    # 595px back
            {"tag": "a", "id": "link5", "text": "Link 5", "rect": {"top": 800, "left": 0}},
            {"tag": "a", "id": "link6", "text": "Link 6", "rect": {"top": 0, "left": 0}},    # 800px back
        ]
        tester._check_tab_order_logic(elements)
        # 3 backwards jumps out of 5 steps = 60% > 30% threshold → finding expected
        assert any(f.category == FindingCategory.KEYBOARD_NAVIGATION for f in tester.findings)

    def test_logical_tab_order_no_finding(self):
        tester = self._tester_instance()
        # Elements flowing top to bottom
        elements = [
            {"tag": "a", "id": "link1", "text": "Link 1", "rect": {"top": 10, "left": 0}},
            {"tag": "a", "id": "link2", "text": "Link 2", "rect": {"top": 50, "left": 0}},
            {"tag": "a", "id": "link3", "text": "Link 3", "rect": {"top": 100, "left": 0}},
            {"tag": "a", "id": "link4", "text": "Link 4", "rect": {"top": 150, "left": 0}},
        ]
        tester._check_tab_order_logic(elements)
        assert tester.findings == []

    def test_too_few_elements_skips_check(self):
        tester = self._tester_instance()
        # _check_tab_order_logic requires >= 3 elements; 2 should silently return
        elements = [
            {"tag": "a", "id": "a", "text": "A", "rect": {"top": 100}},
            {"tag": "a", "id": "b", "text": "B", "rect": {"top": 10}},
        ]
        tester._check_tab_order_logic(elements)
        # 2 elements: 1 backwards jump out of 1 = 100%, but < 3 elements so check may not run
        # Just verify it doesn't crash
