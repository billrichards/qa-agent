"""Tests for qa_agent/testers/forms.py — label detection, required fields."""

from __future__ import annotations

from unittest.mock import MagicMock

from qa_agent.config import TestConfig
from qa_agent.models import FindingCategory, Severity
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

    def test_hidden_input_type_skipped(self):
        """Hidden, submit, button, image, and reset input types should be skipped."""
        page = MagicMock()
        page.url = "https://example.com"

        mock_input = MagicMock()
        mock_input.evaluate.return_value = "hidden"

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

    def test_required_with_aria_required_no_finding(self):
        """Fields with aria-required=true should not produce a finding."""
        page = MagicMock()
        page.url = "https://example.com"

        mock_input = MagicMock()
        mock_input.evaluate.return_value = {
            "id": "username",
            "name": "username",
            "labelText": "Username",
            "hasVisualIndicator": False,
            "hasAriaRequired": True,  # aria-required covers it
        }

        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.nth.return_value = mock_input
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_required_fields()

        assert tester.findings == []


class TestAnalyzeForms:
    def test_form_data_collected(self):
        """_analyze_forms should populate self.forms_data."""
        page = MagicMock()
        page.url = "https://example.com"

        form_element = MagicMock()
        form_element.evaluate.return_value = {
            "id": "login-form",
            "action": "https://example.com/login",
            "method": "post",
            "inputs": [
                {"type": "email", "name": "email", "id": "email",
                 "required": True, "pattern": None, "placeholder": "Email",
                 "ariaLabel": None, "ariaDescribedby": None, "hasLabel": True},
            ],
            "hasSubmit": True,
        }

        forms_locator = MagicMock()
        forms_locator.count.return_value = 1
        forms_locator.nth.return_value = form_element

        page.locator.return_value = forms_locator

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._analyze_forms()

        assert len(tester.forms_data) == 1
        assert tester.forms_data[0]["id"] == "login-form"

    def test_empty_page_no_forms_data(self):
        """No forms on page → forms_data stays empty."""
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value = MagicMock(count=MagicMock(return_value=0))

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._analyze_forms()

        assert tester.forms_data == []


class TestInputValidation:
    def test_invalid_email_with_no_error_state_produces_finding(self):
        """Email field with invalid input and no error styling → finding."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.is_visible.return_value = True
        element.evaluate.return_value = {
            "validity": False,
            "validationMessage": "Please include an '@' in the email address.",
            "hasErrorClass": False,
            "parentHasError": False,
        }
        element.clear.return_value = None
        element.type.return_value = None
        element.press.return_value = None

        email_locator = MagicMock()
        email_locator.count.return_value = 1
        email_locator.nth.return_value = element

        # Separate locator for error messages (none visible)
        error_locator = MagicMock()
        error_locator.count.return_value = 0

        def locator_dispatch(selector):
            if "email" in selector or "number" in selector or "url" in selector or "tel" in selector:
                return email_locator
            return error_locator

        page.locator.side_effect = locator_dispatch
        page.wait_for_timeout.return_value = None

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_input_validation()

        validation_findings = [f for f in tester.findings if "invalid" in f.title.lower()]
        assert len(validation_findings) >= 1

    def test_invalid_input_with_error_class_no_finding(self):
        """Email field with invalid input but has error CSS class → no finding."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.is_visible.return_value = True
        element.evaluate.return_value = {
            "validity": False,
            "validationMessage": "Invalid email",
            "hasErrorClass": True,  # error is shown visually
            "parentHasError": False,
        }
        element.clear.return_value = None
        element.type.return_value = None
        element.press.return_value = None

        email_locator = MagicMock()
        email_locator.count.return_value = 1
        email_locator.nth.return_value = element

        error_locator = MagicMock()
        error_locator.count.return_value = 0

        def locator_dispatch(selector):
            if "email" in selector or "number" in selector or "url" in selector or "tel" in selector:
                return email_locator
            return error_locator

        page.locator.side_effect = locator_dispatch
        page.wait_for_timeout.return_value = None

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_input_validation()

        validation_findings = [f for f in tester.findings if "invalid" in f.title.lower()]
        assert len(validation_findings) == 0

    def test_valid_input_validity_no_finding(self):
        """Field with valid input (validity=True) → no finding."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.is_visible.return_value = True
        element.evaluate.return_value = {
            "validity": True,
            "validationMessage": "",
            "hasErrorClass": False,
            "parentHasError": False,
        }
        element.clear.return_value = None
        element.type.return_value = None
        element.press.return_value = None

        email_locator = MagicMock()
        email_locator.count.return_value = 1
        email_locator.nth.return_value = element

        page.locator.return_value = email_locator
        page.wait_for_timeout.return_value = None

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_input_validation()

        validation_findings = [f for f in tester.findings if "invalid" in f.title.lower()]
        assert len(validation_findings) == 0


class TestErrorMessages:
    def test_unassociated_error_message_produces_finding(self):
        """Error message with id but no aria-describedby reference → finding."""
        page = MagicMock()
        page.url = "https://example.com"

        error_elem = MagicMock()
        error_elem.evaluate.return_value = {
            "text": "This field is required",
            "ariaLive": None,
            "role": None,
            "id": "email-error",  # has an id but nobody references it
            "color": "rgb(255, 0, 0)",
        }

        error_locator = MagicMock()
        error_locator.count.return_value = 1
        error_locator.nth.return_value = error_elem

        # The aria-describedby query returns 0 results → not associated
        aria_locator = MagicMock()
        aria_locator.count.return_value = 0

        def locator_dispatch(selector):
            if "aria-describedby" in selector:
                return aria_locator
            return error_locator

        page.locator.side_effect = locator_dispatch

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_error_messages()

        assoc_findings = [f for f in tester.findings if "associated" in f.title.lower()]
        assert len(assoc_findings) >= 1

    def test_associated_error_message_no_finding(self):
        """Error message properly referenced via aria-describedby → no finding."""
        page = MagicMock()
        page.url = "https://example.com"

        error_elem = MagicMock()
        error_elem.evaluate.return_value = {
            "text": "Email is invalid",
            "ariaLive": "polite",
            "role": "alert",
            "id": "email-error",
            "color": "rgb(255, 0, 0)",
        }

        error_locator = MagicMock()
        error_locator.count.return_value = 1
        error_locator.nth.return_value = error_elem

        # Some input does reference this error via aria-describedby
        aria_locator = MagicMock()
        aria_locator.count.return_value = 1

        def locator_dispatch(selector):
            if "aria-describedby" in selector:
                return aria_locator
            return error_locator

        page.locator.side_effect = locator_dispatch

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_error_messages()

        assert tester.findings == []

    def test_error_without_id_no_association_finding(self):
        """Error message without an id → association check skipped, no finding."""
        page = MagicMock()
        page.url = "https://example.com"

        error_elem = MagicMock()
        error_elem.evaluate.return_value = {
            "text": "Error occurred",
            "ariaLive": None,
            "role": None,
            "id": "",  # no id → association check skipped
            "color": "rgb(255, 0, 0)",
        }

        error_locator = MagicMock()
        error_locator.count.return_value = 1
        error_locator.nth.return_value = error_elem

        page.locator.return_value = error_locator

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_error_messages()

        assert tester.findings == []


class TestInputTypes:
    def test_email_field_using_text_type_produces_finding(self):
        """A text input with 'email' in its name should suggest type=email."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.evaluate.return_value = {
            "name": "email",
            "id": "user-email",
            "currentType": "text",
            "suggestedType": "email",
            "label": "email address",
        }

        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.nth.return_value = element
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_input_types()

        type_findings = [f for f in tester.findings if "html5" in f.title.lower() or "semantic" in f.title.lower()]
        assert len(type_findings) >= 1
        assert type_findings[0].severity == Severity.LOW

    def test_correctly_typed_field_no_finding(self):
        """An input already using the suggested type → no finding."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.evaluate.return_value = {
            "name": "email",
            "id": "email",
            "currentType": "email",  # already correct
            "suggestedType": "email",
            "label": "email",
        }

        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.nth.return_value = element
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_input_types()

        assert tester.findings == []

    def test_no_suggested_type_no_finding(self):
        """An input with no detectable semantic type → no finding."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.evaluate.return_value = {
            "name": "first_name",
            "id": "first_name",
            "currentType": "text",
            "suggestedType": None,  # can't infer a better type
            "label": "First Name",
        }

        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.nth.return_value = element
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_input_types()

        assert tester.findings == []


class TestAutocomplete:
    def test_more_than_two_missing_autocomplete_produces_finding(self):
        """More than 2 fields missing autocomplete → finding."""
        page = MagicMock()
        page.url = "https://example.com"

        # 3 fields, none with autocomplete
        element = MagicMock()
        element.evaluate.return_value = {
            "name": "email",
            "type": "email",
            "autocomplete": "",
            "hasAutocomplete": False,
        }

        mock_locator = MagicMock()
        mock_locator.count.return_value = 3
        mock_locator.nth.return_value = element
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_autocomplete()

        autocomplete_findings = [f for f in tester.findings if "autocomplete" in f.title.lower()]
        assert len(autocomplete_findings) >= 1
        assert autocomplete_findings[0].severity == Severity.LOW

    def test_two_or_fewer_missing_no_finding(self):
        """Two or fewer fields missing autocomplete → no finding (threshold not met)."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.evaluate.return_value = {
            "name": "email",
            "type": "email",
            "autocomplete": "",
            "hasAutocomplete": False,
        }

        mock_locator = MagicMock()
        mock_locator.count.return_value = 2
        mock_locator.nth.return_value = element
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_autocomplete()

        assert tester.findings == []

    def test_fields_with_autocomplete_no_finding(self):
        """Fields that have autocomplete attribute → no finding."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.evaluate.return_value = {
            "name": "email",
            "type": "email",
            "autocomplete": "email",
            "hasAutocomplete": True,
        }

        mock_locator = MagicMock()
        mock_locator.count.return_value = 5
        mock_locator.nth.return_value = element
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_autocomplete()

        assert tester.findings == []


class TestFormSubmission:
    def test_form_without_submit_button_produces_finding(self):
        """Form with inputs but no submit button → finding."""
        page = MagicMock()
        page.url = "https://example.com"

        form_elem = MagicMock()
        form_elem.evaluate.return_value = {
            "hasAction": True,
            "method": "post",
            "hasSubmit": False,  # no submit button
            "hasPreventDefault": False,
            "inputs": 2,
        }
        form_elem.locator.return_value = MagicMock(count=MagicMock(return_value=0))

        forms_locator = MagicMock()
        forms_locator.count.return_value = 1
        forms_locator.nth.return_value = form_elem

        page.locator.return_value = forms_locator

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_form_submission()

        submit_findings = [f for f in tester.findings if "submit" in f.title.lower()]
        assert len(submit_findings) >= 1
        assert submit_findings[0].severity == Severity.MEDIUM

    def test_form_with_submit_button_no_finding(self):
        """Form with a submit button → no finding."""
        page = MagicMock()
        page.url = "https://example.com"

        form_elem = MagicMock()
        form_elem.evaluate.return_value = {
            "hasAction": True,
            "method": "post",
            "hasSubmit": True,
            "hasPreventDefault": False,
            "inputs": 2,
        }

        forms_locator = MagicMock()
        forms_locator.count.return_value = 1
        forms_locator.nth.return_value = form_elem

        page.locator.return_value = forms_locator

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_form_submission()

        submit_findings = [f for f in tester.findings if "submit" in f.title.lower()]
        assert len(submit_findings) == 0

    def test_single_input_form_without_handler_produces_finding(self):
        """Single-input form without submit handler → finding about Enter key."""
        page = MagicMock()
        page.url = "https://example.com"

        input_locator = MagicMock()
        # `.first` is a property that returns another Locator; set count on it explicitly
        input_locator.first.count.return_value = 1
        input_locator.first.focus.return_value = None

        form_elem = MagicMock()
        form_elem.evaluate.side_effect = [
            {
                "hasAction": True,
                "method": "get",
                "hasSubmit": True,  # has submit, so no "no submit button" finding
                "hasPreventDefault": False,
                "inputs": 1,  # single input
            },
            False,  # has_submit_handler = False
        ]
        form_elem.locator.return_value = input_locator

        forms_locator = MagicMock()
        forms_locator.count.return_value = 1
        forms_locator.nth.return_value = form_elem

        page.locator.return_value = forms_locator

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_form_submission()

        enter_findings = [f for f in tester.findings if "enter" in f.title.lower()]
        assert len(enter_findings) >= 1
        assert enter_findings[0].severity == Severity.LOW

    def test_form_with_no_inputs_no_finding(self):
        """Form with zero inputs → no finding from submission check."""
        page = MagicMock()
        page.url = "https://example.com"

        form_elem = MagicMock()
        form_elem.evaluate.return_value = {
            "hasAction": False,
            "method": "get",
            "hasSubmit": False,
            "hasPreventDefault": False,
            "inputs": 0,  # no inputs
        }

        forms_locator = MagicMock()
        forms_locator.count.return_value = 1
        forms_locator.nth.return_value = form_elem

        page.locator.return_value = forms_locator

        config = TestConfig(urls=["https://example.com"])
        tester = FormTester(page, config)
        tester._test_form_submission()

        assert tester.findings == []
