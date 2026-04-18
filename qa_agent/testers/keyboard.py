"""Keyboard navigation and input testing."""

import logging

from playwright.sync_api import Page

from ..config import TestConfig
from ..models import Finding, FindingCategory, Severity
from .base import BaseTester

logger = logging.getLogger(__name__)


class KeyboardTester(BaseTester):
    """Tests keyboard navigation and interactions."""

    def __init__(self, page: Page, config: TestConfig):
        super().__init__(page, config)
        self.tab_order: list[dict] = []
        self.focusable_elements: list = []

    def run(self) -> list[Finding]:
        """Run all keyboard tests."""
        self.findings = []

        self._test_tab_navigation()
        self._test_arrow_key_navigation()
        self._test_enter_activation()
        self._test_escape_key()
        self._test_keyboard_traps()
        self._test_focus_visibility()
        self._test_shortcut_keys()

        return self.findings

    def _test_tab_navigation(self):
        """Test TAB key navigation through focusable elements."""
        try:
            # Reset focus to body
            self.page.evaluate("document.body.focus()")
            self.page.keyboard.press("Tab")

            visited_elements = []
            max_tabs = 100  # Prevent infinite loops
            tabs_pressed = 0

            while tabs_pressed < max_tabs:
                # Get currently focused element
                focused = self.page.evaluate("""() => {
                    const el = document.activeElement;
                    if (!el || el === document.body) return null;
                    return {
                        tag: el.tagName.toLowerCase(),
                        id: el.id || null,
                        className: el.className || null,
                        text: el.textContent?.slice(0, 50) || null,
                        role: el.getAttribute('role'),
                        tabIndex: el.tabIndex,
                        isVisible: el.offsetParent !== null,
                        rect: el.getBoundingClientRect()
                    };
                }""")

                if focused is None:
                    break

                # Check if we've cycled back to first element
                element_key = f"{focused['tag']}_{focused['id']}_{focused['text']}"
                if element_key in [f"{e['tag']}_{e['id']}_{e['text']}" for e in visited_elements[:3]]:
                    break

                visited_elements.append(focused)

                # Check for issues
                if not focused.get("isVisible", True):
                    self.findings.append(Finding(
                        title="Hidden element receives focus",
                        description=f"Tab navigation focused on a hidden element: {focused['tag']}",
                        category=FindingCategory.KEYBOARD_NAVIGATION,
                        severity=Severity.MEDIUM,
                        url=self.page.url,
                        element_selector=f"#{focused['id']}" if focused['id'] else focused['tag'],
                        element_text=focused.get('text'),
                        expected_behavior="Only visible elements should receive focus",
                        actual_behavior="Hidden element received keyboard focus",
                    ))

                self.page.keyboard.press("Tab")
                tabs_pressed += 1

            self.tab_order = visited_elements

            # Check if tab order seems logical (top-to-bottom, left-to-right)
            if len(visited_elements) >= 3:
                self._check_tab_order_logic(visited_elements)

            # Check for lack of focusable elements
            if len(visited_elements) == 0:
                self.findings.append(Finding(
                    title="No focusable elements found",
                    description="TAB navigation found no focusable elements on the page",
                    category=FindingCategory.KEYBOARD_NAVIGATION,
                    severity=Severity.HIGH,
                    url=self.page.url,
                    expected_behavior="Interactive elements should be focusable via keyboard",
                    actual_behavior="No elements received focus when pressing TAB",
                ))

        except Exception as e:
            self.findings.append(Finding(
                title="Tab navigation test failed",
                description=f"Error during tab navigation test: {str(e)}",
                category=FindingCategory.KEYBOARD_NAVIGATION,
                severity=Severity.LOW,
                url=self.page.url,
                raw_error=str(e),
            ))

    def _check_tab_order_logic(self, elements: list[dict]):
        """Check if tab order follows visual layout."""
        significant_jumps = 0
        for i in range(1, len(elements)):
            prev_rect = elements[i-1].get('rect', {})
            curr_rect = elements[i].get('rect', {})

            if not prev_rect or not curr_rect:
                continue

            # Check for significant backwards jump (going back up the page)
            if curr_rect.get('top', 0) < prev_rect.get('top', 0) - 100:
                significant_jumps += 1

        if significant_jumps > len(elements) * 0.3:
            self.findings.append(Finding(
                title="Illogical tab order detected",
                description=f"Tab order jumps around the page unexpectedly ({significant_jumps} backwards jumps)",
                category=FindingCategory.KEYBOARD_NAVIGATION,
                severity=Severity.MEDIUM,
                url=self.page.url,
                expected_behavior="Tab order should follow visual reading order (top-to-bottom, left-to-right)",
                actual_behavior="Focus jumps backwards on the page multiple times",
                metadata={"backwards_jumps": significant_jumps, "total_elements": len(elements)},
            ))

    def _test_arrow_key_navigation(self):
        """Test arrow key navigation in lists, menus, and form controls."""
        try:
            # Find elements that typically use arrow keys
            arrow_nav_selectors = [
                '[role="listbox"]',
                '[role="menu"]',
                '[role="menubar"]',
                '[role="tablist"]',
                '[role="radiogroup"]',
                'select',
                '[role="slider"]',
                '[role="spinbutton"]',
            ]

            for selector in arrow_nav_selectors:
                elements = self.page.locator(selector)
                count = elements.count()

                for i in range(min(count, 3)):  # Test up to 3 of each type
                    element = elements.nth(i)
                    if not element.is_visible():
                        continue

                    try:
                        element.focus()

                        # Test arrow keys
                        initial_state = self.page.evaluate("""() => {
                            const el = document.activeElement;
                            return {
                                value: el.value,
                                ariaSelected: el.getAttribute('aria-selected'),
                                ariaChecked: el.getAttribute('aria-checked'),
                                ariaActiveDescendant: el.getAttribute('aria-activedescendant')
                            };
                        }""")

                        self.page.keyboard.press("ArrowDown")
                        self.page.wait_for_timeout(100)

                        after_state = self.page.evaluate("""() => {
                            const el = document.activeElement;
                            return {
                                value: el.value,
                                ariaSelected: el.getAttribute('aria-selected'),
                                ariaChecked: el.getAttribute('aria-checked'),
                                ariaActiveDescendant: el.getAttribute('aria-activedescendant')
                            };
                        }""")

                        # For interactive widgets, arrow should do something
                        if selector in ['[role="listbox"]', '[role="menu"]', 'select']:
                            if initial_state == after_state:
                                self.findings.append(Finding(
                                    title="Arrow keys not functional in widget",
                                    description=f"Arrow keys don't navigate in {selector} element",
                                    category=FindingCategory.KEYBOARD_NAVIGATION,
                                    severity=Severity.MEDIUM,
                                    url=self.page.url,
                                    element_selector=selector,
                                    expected_behavior="Arrow keys should navigate options in list/menu widgets",
                                    actual_behavior="Arrow key press had no effect",
                                ))

                    except Exception as e:
                        logger.debug("%s: error testing arrow key on %s: %s", self.__class__.__name__, selector, e)
                        continue

        except Exception as e:
            logger.debug("%s: _test_arrow_key_navigation failed: %s", self.__class__.__name__, e)

    def _test_enter_activation(self):
        """Test that Enter key activates focused elements."""
        try:
            # Find buttons and links
            interactive_elements = self.page.locator('button:visible, a:visible, [role="button"]:visible')
            count = min(interactive_elements.count(), 5)

            for i in range(count):
                element = interactive_elements.nth(i)
                try:
                    element.focus()

                    # Get initial URL and any click handlers

                    # Check if element is focused
                    is_focused = self.page.evaluate("""(selector) => {
                        const el = document.activeElement;
                        return el && (el.matches('button, a, [role="button"]'));
                    }""", None)

                    if not is_focused:
                        tag = element.evaluate("el => el.tagName.toLowerCase()")
                        text = element.text_content()[:30] if element.text_content() else ""
                        self.findings.append(Finding(
                            title="Interactive element not focusable",
                            description=f"{tag} element cannot receive focus",
                            category=FindingCategory.KEYBOARD_NAVIGATION,
                            severity=Severity.HIGH,
                            url=self.page.url,
                            element_text=text,
                            expected_behavior="Buttons and links should be focusable",
                            actual_behavior="Element could not be focused via JavaScript",
                        ))

                except Exception as e:
                    logger.debug("%s: error testing enter activation on element: %s", self.__class__.__name__, e)
                    continue

        except Exception as e:
            logger.debug("%s: _test_enter_activation failed: %s", self.__class__.__name__, e)

    def _test_escape_key(self):
        """Test that Escape key closes modals/dropdowns."""
        try:
            # Look for open modals or dialogs
            modal_selectors = [
                '[role="dialog"]:visible',
                '[role="alertdialog"]:visible',
                '.modal:visible',
                '[aria-modal="true"]:visible',
            ]

            for selector in modal_selectors:
                if self.page.locator(selector).count() > 0:
                    self.page.keyboard.press("Escape")
                    self.page.wait_for_timeout(300)

                    if self.page.locator(selector).count() > 0:
                        self.findings.append(Finding(
                            title="Escape key doesn't close modal",
                            description=f"Modal/dialog ({selector}) remains open after pressing Escape",
                            category=FindingCategory.KEYBOARD_NAVIGATION,
                            severity=Severity.MEDIUM,
                            url=self.page.url,
                            element_selector=selector,
                            expected_behavior="Escape key should close modals and dialogs",
                            actual_behavior="Modal remained open after Escape key press",
                        ))

        except Exception as e:
            logger.debug("%s: _test_escape_key failed: %s", self.__class__.__name__, e)

    def _test_keyboard_traps(self):
        """Test for keyboard traps where user cannot TAB out."""
        try:
            total_focusable = self.page.evaluate("""() => {
                return document.querySelectorAll(
                    'a[href], button:not([disabled]), input:not([disabled]), ' +
                    'select:not([disabled]), textarea:not([disabled]), ' +
                    '[tabindex]:not([tabindex="-1"])'
                ).length;
            }""")

            # A page needs more than 3 focusable elements before a small cycle
            # can be considered a trap — otherwise it's just a simple page.
            if not total_focusable or total_focusable <= 3:
                return

            self.page.evaluate("document.body.focus()")

            visited_indices: set[int] = set()

            # Build a stable element→index map once so each Tab press is O(1).
            self.page.evaluate("""() => {
                const all = Array.from(document.querySelectorAll('*'));
                all.forEach((el, i) => el.setAttribute('data-qa-idx', i));
            }""")

            for _ in range(min(50, total_focusable * 2)):
                self.page.keyboard.press("Tab")

                focused_index = self.page.evaluate("""() => {
                    const el = document.activeElement;
                    if (!el || el === document.body) return -1;
                    const idx = el.getAttribute('data-qa-idx');
                    return idx !== null ? parseInt(idx, 10) : -1;
                }""")

                if focused_index == -1:
                    continue

                if focused_index in visited_indices and len(visited_indices) < 3:
                    # Focus is cycling through fewer than 3 elements while the page
                    # has more than 3 focusable elements — genuine trap.
                    self.findings.append(Finding(
                        title="Potential keyboard trap detected",
                        description=f"Focus cycles through only {len(visited_indices)} elements repeatedly",
                        category=FindingCategory.KEYBOARD_NAVIGATION,
                        severity=Severity.HIGH,
                        url=self.page.url,
                        expected_behavior="User should be able to TAB through all interactive elements",
                        actual_behavior=f"Focus trapped cycling through {len(visited_indices)} elements",
                        metadata={"trapped_elements": list(visited_indices)},
                    ))
                    break

                visited_indices.add(focused_index)

        except Exception as e:
            logger.debug("%s: _test_keyboard_traps failed: %s", self.__class__.__name__, e)

    def _test_focus_visibility(self):
        """Test that focus indicators are visible."""
        try:
            self.page.evaluate("document.body.focus()")

            elements_without_focus_style = []

            for _ in range(10):  # Check first 10 focusable elements
                self.page.keyboard.press("Tab")

                focus_visible = self.page.evaluate("""() => {
                    const el = document.activeElement;
                    if (!el || el === document.body) return null;

                    const styles = window.getComputedStyle(el);
                    const beforeStyles = window.getComputedStyle(el, ':focus');

                    // Check for common focus indicators
                    const hasOutline = styles.outlineStyle !== 'none' && styles.outlineWidth !== '0px';
                    const hasBoxShadow = styles.boxShadow !== 'none';
                    const hasBorder = styles.borderWidth !== '0px';

                    return {
                        tag: el.tagName.toLowerCase(),
                        text: el.textContent?.slice(0, 30),
                        hasOutline,
                        hasBoxShadow,
                        outline: styles.outline,
                        boxShadow: styles.boxShadow,
                        hasSomeFocusIndicator: hasOutline || hasBoxShadow
                    };
                }""")

                if focus_visible and not focus_visible.get('hasSomeFocusIndicator'):
                    elements_without_focus_style.append(focus_visible)

            if len(elements_without_focus_style) > 3:
                self.findings.append(Finding(
                    title="Missing focus indicators",
                    description=f"{len(elements_without_focus_style)} elements lack visible focus indicators",
                    category=FindingCategory.KEYBOARD_NAVIGATION,
                    severity=Severity.MEDIUM,
                    url=self.page.url,
                    expected_behavior="Focused elements should have visible focus indicators (outline, box-shadow, etc.)",
                    actual_behavior="Multiple elements have no visible focus state",
                    metadata={"elements": elements_without_focus_style[:5]},
                ))

        except Exception as e:
            logger.debug("%s: _test_focus_visibility failed: %s", self.__class__.__name__, e)

    def _test_shortcut_keys(self):
        """Test common keyboard shortcuts don't break the page."""
        shortcuts = [
            ("Control+a", "Select all"),
            ("Control+c", "Copy"),
            ("Control+f", "Find"),
        ]

        try:
            initial_url = self.page.url

            for shortcut, description in shortcuts:
                self.page.keyboard.press(shortcut)
                self.page.wait_for_timeout(100)

                # Check for unexpected navigation
                if self.page.url != initial_url:
                    self.findings.append(Finding(
                        title="Keyboard shortcut causes navigation",
                        description=f"Pressing {shortcut} ({description}) caused unexpected navigation",
                        category=FindingCategory.KEYBOARD_NAVIGATION,
                        severity=Severity.MEDIUM,
                        url=initial_url,
                        expected_behavior=f"{shortcut} should perform {description}",
                        actual_behavior=f"Page navigated to {self.page.url}",
                    ))
                    self.page.goto(initial_url)

                # Press Escape to close any dialogs that opened
                self.page.keyboard.press("Escape")

        except Exception as e:
            logger.debug("%s: _test_shortcut_keys failed: %s", self.__class__.__name__, e)
