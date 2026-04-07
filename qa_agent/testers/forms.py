"""Form testing module."""

from playwright.sync_api import Page

from ..config import TestConfig
from ..models import Finding, FindingCategory, Severity
from .base import BaseTester


class FormTester(BaseTester):
    """Tests form interactions, validation, and error handling."""

    def __init__(self, page: Page, config: TestConfig):
        super().__init__(page, config)
        self.forms_data: list[dict] = []

    def run(self) -> list[Finding]:
        """Run all form tests."""
        self.findings = []

        self._analyze_forms()
        self._test_required_fields()
        self._test_input_validation()
        self._test_error_messages()
        self._test_form_labels()
        self._test_input_types()
        self._test_autocomplete()
        self._test_form_submission()

        return self.findings

    def _analyze_forms(self):
        """Analyze all forms on the page."""
        try:
            forms = self.page.locator('form:visible')
            count = forms.count()

            for i in range(count):
                form = forms.nth(i)
                try:
                    form_data = form.evaluate("""el => {
                        const inputs = el.querySelectorAll('input, textarea, select');
                        const inputData = [];

                        inputs.forEach(input => {
                            inputData.push({
                                type: input.type || input.tagName.toLowerCase(),
                                name: input.name,
                                id: input.id,
                                required: input.required,
                                pattern: input.pattern,
                                placeholder: input.placeholder,
                                ariaLabel: input.getAttribute('aria-label'),
                                ariaDescribedby: input.getAttribute('aria-describedby'),
                                hasLabel: !!document.querySelector(`label[for="${input.id}"]`)
                            });
                        });

                        return {
                            id: el.id,
                            action: el.action,
                            method: el.method,
                            inputs: inputData,
                            hasSubmit: !!el.querySelector('input[type="submit"], button[type="submit"], button:not([type])')
                        };
                    }""")

                    self.forms_data.append(form_data)

                except Exception:
                    continue

        except Exception:
            pass

    def _test_required_fields(self):
        """Test that required fields are properly indicated."""
        try:
            required_inputs = self.page.locator('input[required]:visible, select[required]:visible, textarea[required]:visible')
            count = required_inputs.count()

            unmarked_required = []

            for i in range(count):
                element = required_inputs.nth(i)
                try:
                    info = element.evaluate("""el => {
                        const label = document.querySelector(`label[for="${el.id}"]`);
                        const labelText = label?.textContent || '';
                        const ariaLabel = el.getAttribute('aria-label') || '';
                        const placeholder = el.placeholder || '';

                        const hasAsterisk = labelText.includes('*') || ariaLabel.includes('*') || placeholder.includes('*');
                        const hasRequiredText = (labelText + ariaLabel).toLowerCase().includes('required');
                        const hasAriaRequired = el.getAttribute('aria-required') === 'true';

                        return {
                            id: el.id,
                            name: el.name,
                            labelText: labelText.slice(0, 50),
                            hasVisualIndicator: hasAsterisk || hasRequiredText,
                            hasAriaRequired
                        };
                    }""")

                    if not info['hasVisualIndicator'] and not info['hasAriaRequired']:
                        unmarked_required.append(info)

                except Exception:
                    continue

            if len(unmarked_required) > 0:
                self.findings.append(Finding(
                    title="Required fields not visually marked",
                    description=f"{len(unmarked_required)} required fields lack visual indicators (asterisk, 'required' text)",
                    category=FindingCategory.FORM_HANDLING,
                    severity=Severity.MEDIUM,
                    url=self.page.url,
                    expected_behavior="Required fields should be visually indicated with asterisk or 'required' text",
                    actual_behavior="Required fields have no visual indicator",
                    metadata={"fields": unmarked_required[:5]},
                ))

        except Exception:
            pass

    def _test_input_validation(self):
        """Test input validation with various invalid inputs."""
        try:
            test_inputs = [
                # Email fields
                {"selector": 'input[type="email"]:visible', "invalid": "notanemail", "valid": "test@example.com", "field_type": "email"},
                # Number fields
                {"selector": 'input[type="number"]:visible', "invalid": "abc", "valid": "123", "field_type": "number"},
                # URL fields
                {"selector": 'input[type="url"]:visible', "invalid": "notaurl", "valid": "https://example.com", "field_type": "URL"},
                # Tel fields
                {"selector": 'input[type="tel"]:visible', "invalid": "abc", "valid": "1234567890", "field_type": "phone"},
            ]

            for test in test_inputs:
                elements = self.page.locator(test["selector"])
                count = min(elements.count(), 3)

                for i in range(count):
                    element = elements.nth(i)
                    try:
                        if not element.is_visible():
                            continue

                        # Clear and type invalid input
                        element.clear()
                        element.type(test["invalid"])
                        element.press("Tab")  # Trigger blur validation

                        self.page.wait_for_timeout(200)

                        # Check for validation state
                        validation_state = element.evaluate("""el => ({
                            validity: el.validity?.valid,
                            validationMessage: el.validationMessage,
                            hasErrorClass: el.classList.contains('error') || el.classList.contains('invalid') ||
                                           el.getAttribute('aria-invalid') === 'true',
                            parentHasError: el.parentElement?.classList.contains('error') ||
                                           el.parentElement?.classList.contains('has-error')
                        })""")

                        # Check for visible error message
                        error_visible = self.page.locator('.error:visible, .invalid-feedback:visible, [role="alert"]:visible').count() > 0

                        if validation_state['validity'] is False and not validation_state['hasErrorClass'] and not error_visible:
                            self.findings.append(Finding(
                                title=f"No visual feedback for invalid {test['field_type']}",
                                description=f"Invalid {test['field_type']} input doesn't show visual error state",
                                category=FindingCategory.FORM_HANDLING,
                                severity=Severity.MEDIUM,
                                url=self.page.url,
                                element_selector=test["selector"],
                                expected_behavior="Invalid input should show visual error indicator",
                                actual_behavior=f"Field with invalid value '{test['invalid']}' has no error styling",
                            ))

                        # Clear for next test
                        element.clear()

                    except Exception:
                        continue

        except Exception:
            pass

    def _test_error_messages(self):
        """Test that error messages are accessible and clear."""
        try:
            # Find any visible error messages
            error_selectors = [
                '.error-message:visible',
                '.error:visible',
                '.invalid-feedback:visible',
                '[role="alert"]:visible',
                '.form-error:visible',
            ]

            for selector in error_selectors:
                errors = self.page.locator(selector)
                count = errors.count()

                for i in range(count):
                    error = errors.nth(i)
                    try:
                        info = error.evaluate("""el => ({
                            text: el.textContent,
                            ariaLive: el.getAttribute('aria-live'),
                            role: el.getAttribute('role'),
                            id: el.id,
                            color: window.getComputedStyle(el).color
                        })""")

                        # Check if error is associated with input
                        if info['id']:
                            associated = self.page.locator(f'[aria-describedby*="{info["id"]}"]').count()
                            if associated == 0:
                                self.findings.append(Finding(
                                    title="Error message not associated with input",
                                    description="Error message exists but not linked to input via aria-describedby",
                                    category=FindingCategory.FORM_HANDLING,
                                    severity=Severity.MEDIUM,
                                    url=self.page.url,
                                    element_text=info['text'][:50] if info['text'] else None,
                                    expected_behavior="Error messages should be associated with inputs via aria-describedby",
                                    actual_behavior="Error message has no aria-describedby association",
                                ))

                        # Check for aria-live on dynamic errors
                        if not info.get('ariaLive') and info.get('role') != 'alert':
                            pass  # Only flag if we know it's dynamic

                    except Exception:
                        continue

        except Exception:
            pass

    def _test_form_labels(self):
        """Test that form inputs have proper labels."""
        try:
            inputs = self.page.locator('input:visible, select:visible, textarea:visible')
            count = min(inputs.count(), 20)

            unlabeled_inputs = []

            for i in range(count):
                element = inputs.nth(i)
                try:
                    input_type = element.evaluate("el => el.type")

                    # Skip hidden, submit, button, and image types
                    if input_type in ['hidden', 'submit', 'button', 'image', 'reset']:
                        continue

                    label_info = element.evaluate("""el => {
                        const id = el.id;
                        const label = id ? document.querySelector(`label[for="${id}"]`) : null;
                        const ariaLabel = el.getAttribute('aria-label');
                        const ariaLabelledby = el.getAttribute('aria-labelledby');
                        const placeholder = el.placeholder;
                        const title = el.title;
                        const parentLabel = el.closest('label');

                        return {
                            id,
                            type: el.type,
                            name: el.name,
                            hasLabel: !!label,
                            hasAriaLabel: !!ariaLabel,
                            hasAriaLabelledby: !!ariaLabelledby,
                            hasPlaceholder: !!placeholder,
                            hasTitle: !!title,
                            hasParentLabel: !!parentLabel,
                            placeholder: placeholder?.slice(0, 30)
                        };
                    }""")

                    # Check if input has accessible name
                    has_accessible_name = any([
                        label_info['hasLabel'],
                        label_info['hasAriaLabel'],
                        label_info['hasAriaLabelledby'],
                        label_info['hasParentLabel'],
                        label_info['hasTitle'],
                    ])

                    if not has_accessible_name:
                        # Placeholder alone is not sufficient
                        if label_info['hasPlaceholder']:
                            unlabeled_inputs.append({
                                **label_info,
                                "issue": "placeholder_only"
                            })
                        else:
                            unlabeled_inputs.append({
                                **label_info,
                                "issue": "no_label"
                            })

                except Exception:
                    continue

            # Report placeholder-only issues
            placeholder_only = [i for i in unlabeled_inputs if i.get('issue') == 'placeholder_only']
            if len(placeholder_only) > 0:
                self.findings.append(Finding(
                    title="Form inputs use placeholder as only label",
                    description=f"{len(placeholder_only)} inputs use placeholder text as only accessible name",
                    category=FindingCategory.FORM_HANDLING,
                    severity=Severity.MEDIUM,
                    url=self.page.url,
                    expected_behavior="Form inputs should have proper labels, not just placeholders",
                    actual_behavior="Placeholder disappears when typing, leaving user without context",
                    metadata={"inputs": placeholder_only[:5]},
                ))

            # Report completely unlabeled inputs
            no_label = [i for i in unlabeled_inputs if i.get('issue') == 'no_label']
            if len(no_label) > 0:
                self.findings.append(Finding(
                    title="Form inputs without labels",
                    description=f"{len(no_label)} inputs have no accessible name (label, aria-label, etc.)",
                    category=FindingCategory.FORM_HANDLING,
                    severity=Severity.HIGH,
                    url=self.page.url,
                    expected_behavior="All form inputs must have accessible labels",
                    actual_behavior="Inputs have no way for assistive technology to identify them",
                    metadata={"inputs": no_label[:5]},
                ))

        except Exception:
            pass

    def _test_input_types(self):
        """Test that inputs use appropriate HTML5 types."""
        try:
            text_inputs = self.page.locator('input[type="text"]:visible, input:not([type]):visible')
            count = min(text_inputs.count(), 20)

            wrong_types = []

            for i in range(count):
                element = text_inputs.nth(i)
                try:
                    info = element.evaluate("""el => {
                        const name = (el.name || '').toLowerCase();
                        const id = (el.id || '').toLowerCase();
                        const placeholder = (el.placeholder || '').toLowerCase();
                        const label = document.querySelector(`label[for="${el.id}"]`)?.textContent?.toLowerCase() || '';

                        const combined = name + id + placeholder + label;

                        // Detect what type it should be
                        let suggestedType = null;
                        if (combined.includes('email') || combined.includes('e-mail')) suggestedType = 'email';
                        else if (combined.includes('phone') || combined.includes('tel') || combined.includes('mobile')) suggestedType = 'tel';
                        else if (combined.includes('url') || combined.includes('website') || combined.includes('link')) suggestedType = 'url';
                        else if (combined.includes('password') || combined.includes('pwd')) suggestedType = 'password';
                        else if (combined.includes('search')) suggestedType = 'search';
                        else if (combined.includes('date') || combined.includes('birthday') || combined.includes('dob')) suggestedType = 'date';
                        else if (combined.includes('number') || combined.includes('amount') || combined.includes('quantity') || combined.includes('age')) suggestedType = 'number';

                        return {
                            name: el.name,
                            id: el.id,
                            currentType: el.type,
                            suggestedType,
                            label: label.slice(0, 30)
                        };
                    }""")

                    if info['suggestedType'] and info['suggestedType'] != info['currentType']:
                        wrong_types.append(info)

                except Exception:
                    continue

            if len(wrong_types) > 0:
                self.findings.append(Finding(
                    title="Inputs not using semantic HTML5 types",
                    description=f"{len(wrong_types)} inputs could benefit from proper HTML5 input types",
                    category=FindingCategory.FORM_HANDLING,
                    severity=Severity.LOW,
                    url=self.page.url,
                    expected_behavior="Use semantic input types (email, tel, url, etc.) for better mobile keyboards and validation",
                    actual_behavior="Generic text inputs used where specific types would be better",
                    metadata={"suggestions": wrong_types[:5]},
                ))

        except Exception:
            pass

    def _test_autocomplete(self):
        """Test autocomplete attributes on form fields."""
        try:
            common_fields = self.page.locator("""
                input[name*="email"]:visible,
                input[name*="name"]:visible,
                input[name*="phone"]:visible,
                input[name*="address"]:visible,
                input[name*="city"]:visible,
                input[name*="zip"]:visible,
                input[name*="postal"]:visible,
                input[type="password"]:visible
            """)
            count = common_fields.count()

            missing_autocomplete = []

            for i in range(count):
                element = common_fields.nth(i)
                try:
                    info = element.evaluate("""el => ({
                        name: el.name,
                        type: el.type,
                        autocomplete: el.autocomplete,
                        hasAutocomplete: el.hasAttribute('autocomplete')
                    })""")

                    if not info['hasAutocomplete'] or info['autocomplete'] == '':
                        missing_autocomplete.append(info)

                except Exception:
                    continue

            if len(missing_autocomplete) > 2:
                self.findings.append(Finding(
                    title="Missing autocomplete attributes",
                    description=f"{len(missing_autocomplete)} common fields lack autocomplete attribute",
                    category=FindingCategory.FORM_HANDLING,
                    severity=Severity.LOW,
                    url=self.page.url,
                    expected_behavior="Common fields should have autocomplete for better UX and autofill",
                    actual_behavior="Fields missing autocomplete attribute",
                    metadata={"fields": missing_autocomplete[:5]},
                ))

        except Exception:
            pass

    def _test_form_submission(self):
        """Test form submission behavior without actually submitting."""
        try:
            forms = self.page.locator('form:visible')
            count = forms.count()

            for i in range(count):
                form = forms.nth(i)
                try:
                    info = form.evaluate("""el => ({
                        hasAction: el.action && el.action !== window.location.href,
                        method: el.method,
                        hasSubmit: !!el.querySelector('input[type="submit"], button[type="submit"], button:not([type])'),
                        hasPreventDefault: false,  // Can't easily detect this
                        inputs: el.querySelectorAll('input, textarea, select').length
                    })""")

                    # Check for form without submit button
                    if info['inputs'] > 0 and not info['hasSubmit']:
                        self.findings.append(Finding(
                            title="Form without submit button",
                            description="Form has inputs but no visible submit button",
                            category=FindingCategory.FORM_HANDLING,
                            severity=Severity.MEDIUM,
                            url=self.page.url,
                            expected_behavior="Forms should have a clear submit button",
                            actual_behavior="No submit button found in form",
                        ))

                    # Check for single-input forms (might need Enter key submission)
                    if info['inputs'] == 1:
                        # Test Enter key submission
                        input_elem = form.locator('input:visible').first
                        if input_elem.count() > 0:
                            # Focus and press Enter
                            input_elem.focus()

                            # Don't actually submit - just check if handler exists
                            has_submit_handler = form.evaluate("""el => {
                                const events = el.onsubmit || el.getAttribute('onsubmit');
                                return !!events || !!el.querySelector('button, input[type="submit"]');
                            }""")

                            if not has_submit_handler:
                                self.findings.append(Finding(
                                    title="Single-field form may not submit on Enter",
                                    description="Form with single input may not handle Enter key submission",
                                    category=FindingCategory.FORM_HANDLING,
                                    severity=Severity.LOW,
                                    url=self.page.url,
                                    expected_behavior="Single-input forms should submit when pressing Enter",
                                    actual_behavior="No submit handler detected",
                                ))

                except Exception:
                    continue

        except Exception:
            pass
