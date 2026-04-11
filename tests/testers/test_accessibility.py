"""Tests for qa_agent/testers/accessibility.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from qa_agent.config import TestConfig
from qa_agent.testers.accessibility import AccessibilityTester


def _tester(page=None) -> AccessibilityTester:
    if page is None:
        page = MagicMock()
        page.url = "https://example.com"
    config = TestConfig(urls=["https://example.com"])
    return AccessibilityTester(page, config)


def _page_with_evaluate(evaluate_responses: dict) -> MagicMock:
    """Return a page mock where evaluate() dispatches based on snippet content."""
    page = MagicMock()
    page.url = "https://example.com"

    def evaluate_side_effect(script, *args, **kwargs):
        for key, response in evaluate_responses.items():
            if key in script:
                return response
        return None

    page.evaluate.side_effect = evaluate_side_effect
    return page


class TestImageAltText:
    def test_image_without_alt_produces_finding(self):
        page = MagicMock()
        page.url = "https://example.com"

        # Single image with no alt attribute
        mock_img = MagicMock()
        mock_img.evaluate.return_value = {
            "src": "banner.jpg",
            "alt": "",
            "hasAlt": False,
            "role": None,
            "ariaHidden": None,
            "width": 200,
            "height": 100,
            "isInLink": False,
        }

        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.nth.return_value = mock_img
        page.locator.return_value = mock_locator

        # Other evaluate calls return safe defaults
        page.evaluate.return_value = {"main": 1, "nav": 1, "header": 1, "footer": 1, "search": 0}

        tester = _tester(page)
        findings = tester.run()

        titles = [f.title for f in findings]
        assert any("alt" in t.lower() or "missing" in t.lower() for t in titles)

    def test_decorative_image_with_empty_alt_no_finding(self):
        """alt="" indicates intentionally decorative — should not flag as missing."""
        page = MagicMock()
        page.url = "https://example.com"

        mock_img = MagicMock()
        mock_img.evaluate.return_value = {
            "src": "decoration.png",
            "alt": "",
            "hasAlt": True,  # has the attribute, value is empty string
            "role": None,
            "ariaHidden": None,
            "width": 50,
            "height": 50,
            "isInLink": False,
        }

        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.nth.return_value = mock_img
        page.locator.return_value = mock_locator
        page.evaluate.return_value = {}

        tester = _tester(page)
        findings = tester.run()

        # Should not produce a "missing alt" finding
        missing_alt = [f for f in findings if "missing alt" in f.title.lower()]
        assert len(missing_alt) == 0

    def test_tiny_image_skipped(self):
        """Images smaller than 20x20 are decorative spacers and should be ignored."""
        page = MagicMock()
        page.url = "https://example.com"

        mock_img = MagicMock()
        mock_img.evaluate.return_value = {
            "src": "spacer.gif",
            "alt": "",
            "hasAlt": False,
            "role": None,
            "ariaHidden": None,
            "width": 1,
            "height": 1,
            "isInLink": False,
        }

        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.nth.return_value = mock_img
        page.locator.return_value = mock_locator
        page.evaluate.return_value = {}

        tester = _tester(page)
        findings = tester.run()
        missing_alt = [f for f in findings if "missing alt" in f.title.lower()]
        assert len(missing_alt) == 0


class TestLanguageAttribute:
    def test_missing_lang_attribute_produces_finding(self):
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value = MagicMock(count=MagicMock(return_value=0))

        def evaluate_dispatch(script, *args, **kwargs):
            if "hasLang" in script:
                return {"hasLang": False, "lang": "", "hasXmlLang": False}
            if "main" in script and "nav" in script:
                return {"main": 1, "nav": 1, "header": 1, "footer": 1, "search": 0}
            return {}

        page.evaluate.side_effect = evaluate_dispatch

        tester = _tester(page)
        findings = tester.run()

        titles = [f.title for f in findings]
        assert any("language" in t.lower() for t in titles)

    def test_present_lang_attribute_no_language_finding(self):
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value = MagicMock(count=MagicMock(return_value=0))

        def evaluate_dispatch(script, *args, **kwargs):
            if "hasLang" in script:
                return {"hasLang": True, "lang": "en", "hasXmlLang": False}
            if "main" in script and "nav" in script:
                return {"main": 1, "nav": 1, "header": 1, "footer": 1, "search": 0}
            return []

        page.evaluate.side_effect = evaluate_dispatch

        tester = _tester(page)
        findings = tester.run()

        lang_findings = [f for f in findings if "language" in f.title.lower()]
        assert len(lang_findings) == 0


class TestSmokeRun:
    def test_run_on_empty_page_does_not_crash(self):
        """Accessibility tester must not raise even when page returns nothing."""
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value = MagicMock(count=MagicMock(return_value=0))
        page.evaluate.return_value = []

        tester = _tester(page)
        findings = tester.run()
        assert isinstance(findings, list)

    def test_run_returns_list(self):
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value = MagicMock(count=MagicMock(return_value=0))
        page.evaluate.return_value = []

        tester = _tester(page)
        result = tester.run()
        assert isinstance(result, list)
