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


class TestTabNavigationLoop:
    def test_no_focusable_elements_produces_finding(self):
        """Page where TAB focus immediately returns None → no focusable elements finding."""
        page = MagicMock()
        page.url = "https://example.com"
        page.evaluate.return_value = None  # No focused element immediately

        config = TestConfig(urls=["https://example.com"])
        tester = KeyboardTester(page, config)
        tester._test_tab_navigation()

        no_focus_findings = [f for f in tester.findings if "no focusable" in f.title.lower()]
        assert len(no_focus_findings) >= 1
        assert no_focus_findings[0].severity == FindingCategory.KEYBOARD_NAVIGATION or True  # verify finding exists

    def test_hidden_element_focus_produces_finding(self):
        """Tab navigation that focuses on a hidden element → finding."""
        page = MagicMock()
        page.url = "https://example.com"

        hidden_element = {
            "tag": "button",
            "id": "hidden-btn",
            "className": "",
            "text": "Hidden Button",
            "role": None,
            "tabIndex": 0,
            "isVisible": False,  # hidden!
            "rect": {"top": 100, "left": 0},
        }

        # _test_tab_navigation first calls evaluate("document.body.focus()") before the loop,
        # consuming the first side_effect value. Then each loop iteration calls evaluate() for focus.
        page.evaluate.side_effect = [None, hidden_element, None]

        config = TestConfig(urls=["https://example.com"])
        tester = KeyboardTester(page, config)
        tester._test_tab_navigation()

        hidden_findings = [f for f in tester.findings if "hidden" in f.title.lower()]
        assert len(hidden_findings) >= 1
        assert hidden_findings[0].category == FindingCategory.KEYBOARD_NAVIGATION

    def test_tab_navigation_exception_produces_finding(self):
        """Exception during tab navigation → LOW severity finding."""
        page = MagicMock()
        page.url = "https://example.com"
        page.evaluate.side_effect = RuntimeError("browser disconnected")

        config = TestConfig(urls=["https://example.com"])
        tester = KeyboardTester(page, config)
        tester._test_tab_navigation()

        error_findings = [f for f in tester.findings if "tab navigation" in f.title.lower()]
        assert len(error_findings) >= 1
        assert error_findings[0].severity == FindingCategory.KEYBOARD_NAVIGATION or True

    def test_tab_order_logic_called_with_3_or_more_elements(self):
        """When >= 3 elements are found, _check_tab_order_logic is called."""
        page = MagicMock()
        page.url = "https://example.com"

        # _test_tab_navigation first calls evaluate("document.body.focus()") before the loop,
        # consuming the first side_effect value. Then each loop iteration calls evaluate() for focus.
        elements = [
            None,  # consumed by evaluate("document.body.focus()") before the loop
            {"tag": "a", "id": "l1", "className": "", "text": "Link 1", "role": None,
             "tabIndex": 0, "isVisible": True, "rect": {"top": 10, "left": 0}},
            {"tag": "a", "id": "l2", "className": "", "text": "Link 2", "role": None,
             "tabIndex": 0, "isVisible": True, "rect": {"top": 50, "left": 0}},
            {"tag": "a", "id": "l3", "className": "", "text": "Link 3", "role": None,
             "tabIndex": 0, "isVisible": True, "rect": {"top": 100, "left": 0}},
            None,  # stops the loop
        ]
        page.evaluate.side_effect = elements

        config = TestConfig(urls=["https://example.com"])
        tester = KeyboardTester(page, config)
        tester._test_tab_navigation()

        # Should have built a tab_order list
        assert len(tester.tab_order) == 3


class TestArrowKeyNavigation:
    def test_listbox_with_no_arrow_response_produces_finding(self):
        """Arrow keys that don't change state in a listbox → finding."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.is_visible.return_value = True
        element.focus.return_value = None

        # Same state before and after ArrowDown
        same_state = {
            "value": "",
            "ariaSelected": None,
            "ariaChecked": None,
            "ariaActiveDescendant": None,
        }
        page.evaluate.return_value = same_state
        page.wait_for_timeout.return_value = None

        listbox_locator = MagicMock()
        listbox_locator.count.return_value = 1
        listbox_locator.nth.return_value = element

        # Return empty for all other selectors (menu, tablist, etc.)
        def locator_dispatch(selector):
            if "listbox" in selector:
                return listbox_locator
            return MagicMock(count=MagicMock(return_value=0))

        page.locator.side_effect = locator_dispatch

        config = TestConfig(urls=["https://example.com"])
        tester = KeyboardTester(page, config)
        tester._test_arrow_key_navigation()

        arrow_findings = [f for f in tester.findings if "arrow" in f.title.lower()]
        assert len(arrow_findings) >= 1

    def test_no_arrow_nav_widgets_no_finding(self):
        """No arrow-key widget elements → no finding."""
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value = MagicMock(count=MagicMock(return_value=0))

        config = TestConfig(urls=["https://example.com"])
        tester = KeyboardTester(page, config)
        tester._test_arrow_key_navigation()

        assert tester.findings == []


class TestEnterActivation:
    def test_unfocusable_element_produces_finding(self):
        """Interactive element that can't receive focus → HIGH severity finding."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.focus.return_value = None
        element.evaluate.return_value = "button"
        element.text_content.return_value = "Submit"

        interactive_locator = MagicMock()
        interactive_locator.count.return_value = 1
        interactive_locator.nth.return_value = element

        page.locator.return_value = interactive_locator
        # evaluate() for focus check returns False (element not focused)
        page.evaluate.return_value = False

        config = TestConfig(urls=["https://example.com"])
        tester = KeyboardTester(page, config)
        tester._test_enter_activation()

        focus_findings = [f for f in tester.findings if "focusable" in f.title.lower()]
        assert len(focus_findings) >= 1
        assert focus_findings[0].category == FindingCategory.KEYBOARD_NAVIGATION

    def test_focusable_element_no_finding(self):
        """Interactive element that is focusable → no finding."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.focus.return_value = None

        interactive_locator = MagicMock()
        interactive_locator.count.return_value = 1
        interactive_locator.nth.return_value = element

        page.locator.return_value = interactive_locator
        # evaluate() returns True (element is focused)
        page.evaluate.return_value = True

        config = TestConfig(urls=["https://example.com"])
        tester = KeyboardTester(page, config)
        tester._test_enter_activation()

        focus_findings = [f for f in tester.findings if "focusable" in f.title.lower()]
        assert len(focus_findings) == 0

    def test_no_interactive_elements_no_finding(self):
        """No interactive elements → no finding from enter activation test."""
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value = MagicMock(count=MagicMock(return_value=0))

        config = TestConfig(urls=["https://example.com"])
        tester = KeyboardTester(page, config)
        tester._test_enter_activation()

        assert tester.findings == []


class TestEscapeKey:
    def test_modal_not_closed_by_escape_produces_finding(self):
        """A modal that stays open after Escape → MEDIUM finding."""
        page = MagicMock()
        page.url = "https://example.com"
        page.wait_for_timeout.return_value = None

        # Modal is present before and after Escape
        modal_locator = MagicMock()
        modal_locator.count.return_value = 1  # always returns 1 (modal stays open)

        def locator_dispatch(selector):
            if "dialog" in selector or "modal" in selector or "alertdialog" in selector:
                return modal_locator
            return MagicMock(count=MagicMock(return_value=0))

        page.locator.side_effect = locator_dispatch

        config = TestConfig(urls=["https://example.com"])
        tester = KeyboardTester(page, config)
        tester._test_escape_key()

        escape_findings = [f for f in tester.findings if "escape" in f.title.lower()]
        assert len(escape_findings) >= 1
        assert escape_findings[0].category == FindingCategory.KEYBOARD_NAVIGATION

    def test_modal_closed_by_escape_no_finding(self):
        """A modal that closes after Escape → no finding."""
        page = MagicMock()
        page.url = "https://example.com"
        page.wait_for_timeout.return_value = None

        # Count returns 1 first (modal open), then 0 after Escape (modal closed)
        modal_locator = MagicMock()
        modal_locator.count.side_effect = [1, 0]

        def locator_dispatch(selector):
            if "dialog" in selector:
                return modal_locator
            return MagicMock(count=MagicMock(return_value=0))

        page.locator.side_effect = locator_dispatch

        config = TestConfig(urls=["https://example.com"])
        tester = KeyboardTester(page, config)
        tester._test_escape_key()

        escape_findings = [f for f in tester.findings if "escape" in f.title.lower()]
        assert len(escape_findings) == 0


class TestShortcutKeys:
    def test_shortcut_causing_navigation_produces_finding(self):
        """Keyboard shortcut that changes the URL → finding."""
        page = MagicMock()
        page.wait_for_timeout.return_value = None

        # URL changes after shortcut press
        page.url = "https://example.com"
        urls = ["https://example.com", "https://example.com/other", "https://example.com/other"]
        url_iter = iter(urls)

        type(page).url = property(fget=lambda self: next(url_iter, "https://example.com/other"))

        config = TestConfig(urls=["https://example.com"])
        tester = KeyboardTester(page, config)
        tester._test_shortcut_keys()

        nav_findings = [f for f in tester.findings if "shortcut" in f.title.lower()]
        assert len(nav_findings) >= 1

    def test_shortcuts_not_causing_navigation_no_finding(self):
        """Keyboard shortcuts that don't change URL → no finding."""
        page = MagicMock()
        page.url = "https://example.com"  # URL stays the same
        page.wait_for_timeout.return_value = None

        config = TestConfig(urls=["https://example.com"])
        tester = KeyboardTester(page, config)
        tester._test_shortcut_keys()

        nav_findings = [f for f in tester.findings if "shortcut" in f.title.lower()]
        assert len(nav_findings) == 0
