"""Tests for qa_agent/testers/forms.py — label detection, required fields."""

from __future__ import annotations

from unittest.mock import MagicMock

from qa_agent.config import TestConfig
from qa_agent.models import FindingCategory
from qa_agent.testers.forms import FormTester


def _tester(page=None) -> FormTester:
    if page is None:
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value = MagicMock(count=MagicMock(return_value=0))
    config = TestConfig(urls=["https://example.com"])
    return FormTester(page, config)


class TestFormTesterSmoke:
    def test_run_returns_list(self):
        result = _tester().run()
        assert isinstance(result, list)

    def test_run_does_not_raise_on_empty_page(self):
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value = MagicMock(count=MagicMock(return_value=0))
        _tester(page).run()


class TestFormLabels:
    def test_input_without_label_produces_finding(self):
        page = MagicMock()
        page.url = "https://example.com"

        # 1 unlabeled input
        mock_input = MagicMock()
        mock_input.evaluate.side_effect = [
            "text",  # first call: input type
            {        # second call: label info
                "id": "email",
                "type": "text",
                "name": "email",
                "hasLabel": False,
                "hasAriaLabel": False,
                "hasAriaLabelledby": False,
                "hasPlaceholder": False,
                "hasTitle": False,
                "hasParentLabel": False,
                "placeholder": None,
            },
        ]

        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.nth.return_value = mock_input

        def locator_dispatch(selector):
            return mock_locator

        page.locator.side_effect = locator_dispatch

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_form_labels()

        label_findings = [f for f in tester.findings if "label" in f.title.lower()]
        assert len(label_findings) >= 1

    def test_input_with_placeholder_only_produces_finding(self):
        page = MagicMock()
        page.url = "https://example.com"

        mock_input = MagicMock()
        mock_input.evaluate.side_effect = [
            "text",
            {
                "id": "",
                "type": "text",
                "name": "search",
                "hasLabel": False,
                "hasAriaLabel": False,
                "hasAriaLabelledby": False,
                "hasPlaceholder": True,
                "hasTitle": False,
                "hasParentLabel": False,
                "placeholder": "Search...",
            },
        ]

        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.nth.return_value = mock_input
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_form_labels()

        placeholder_findings = [f for f in tester.findings if "placeholder" in f.title.lower()]
        assert len(placeholder_findings) >= 1

    def test_input_with_proper_label_no_finding(self):
        page = MagicMock()
        page.url = "https://example.com"

        mock_input = MagicMock()
        mock_input.evaluate.side_effect = [
            "text",
            {
                "id": "email",
                "type": "text",
                "name": "email",
                "hasLabel": True,  # ← has a proper label
                "hasAriaLabel": False,
                "hasAriaLabelledby": False,
                "hasPlaceholder": True,
                "hasTitle": False,
                "hasParentLabel": False,
                "placeholder": "email@example.com",
            },
        ]

        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.nth.return_value = mock_input
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_form_labels()

        assert tester.findings == []


class TestRequiredFields:
    def test_required_without_indicator_produces_finding(self):
        page = MagicMock()
        page.url = "https://example.com"

        mock_input = MagicMock()
        mock_input.evaluate.return_value = {
            "id": "name",
            "name": "name",
            "labelText": "Full Name",  # no asterisk, no "required"
            "hasVisualIndicator": False,
            "hasAriaRequired": False,
        }

        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.nth.return_value = mock_input
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_required_fields()

        assert any("required" in f.title.lower() for f in tester.findings)

    def test_required_with_asterisk_no_finding(self):
        page = MagicMock()
        page.url = "https://example.com"

        mock_input = MagicMock()
        mock_input.evaluate.return_value = {
            "id": "email",
            "name": "email",
            "labelText": "Email *",  # has asterisk
            "hasVisualIndicator": True,
            "hasAriaRequired": False,
        }

        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.nth.return_value = mock_input
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_required_fields()

        assert tester.findings == []
