"""Mouse interaction testing."""

import logging

from playwright.sync_api import Page

from ..config import TestConfig
from ..models import Finding, FindingCategory, Severity
from .base import BaseTester

logger = logging.getLogger(__name__)


class MouseTester(BaseTester):
    """Tests mouse interactions and hover states."""

    def __init__(self, page: Page, config: TestConfig):
        super().__init__(page, config)

    def run(self) -> list[Finding]:
        """Run all mouse interaction tests."""
        self.findings = []

        self._test_clickable_elements()
        self._test_hover_states()
        self._test_double_click()
        self._test_right_click()
        self._test_drag_and_drop_targets()
        self._test_click_target_sizes()
        self._test_overlapping_elements()

        return self.findings

    def _test_clickable_elements(self):
        """Test that clickable elements respond to clicks."""
        try:
            clickable_selectors = [
                'button:visible',
                'a[href]:visible',
                '[role="button"]:visible',
                '[onclick]:visible',
                'input[type="submit"]:visible',
                'input[type="button"]:visible',
            ]

            for selector in clickable_selectors:
                elements = self.page.locator(selector)
                count = min(elements.count(), 5)

                for i in range(count):
                    element = elements.nth(i)
                    try:
                        if not element.is_visible():
                            continue

                        # Get element info before click
                        info = element.evaluate("""el => ({
                            tag: el.tagName.toLowerCase(),
                            text: el.textContent?.slice(0, 50) || '',
                            href: el.href || null,
                            type: el.type || null,
                            disabled: el.disabled,
                            ariaDisabled: el.getAttribute('aria-disabled'),
                            cursor: window.getComputedStyle(el).cursor
                        })""")

                        # Check cursor style
                        if info['cursor'] not in ['pointer', 'default', 'auto']:
                            if info['tag'] in ['button', 'a'] and info['cursor'] == 'text':
                                self.findings.append(Finding(
                                    title="Clickable element has wrong cursor",
                                    description=f"{info['tag']} element shows text cursor instead of pointer",
                                    category=FindingCategory.MOUSE_INTERACTION,
                                    severity=Severity.LOW,
                                    url=self.page.url,
                                    element_selector=selector,
                                    element_text=info['text'],
                                    expected_behavior="Clickable elements should show pointer cursor",
                                    actual_behavior=f"Cursor is '{info['cursor']}'",
                                ))

                        # Check for disabled elements that look clickable
                        if info.get('disabled') or info.get('ariaDisabled') == 'true':
                            styles = element.evaluate("""el => ({
                                opacity: window.getComputedStyle(el).opacity,
                                pointerEvents: window.getComputedStyle(el).pointerEvents
                            })""")

                            if float(styles.get('opacity', 1)) > 0.7:
                                self.findings.append(Finding(
                                    title="Disabled element not visually distinct",
                                    description=f"Disabled {info['tag']} doesn't appear disabled visually",
                                    category=FindingCategory.MOUSE_INTERACTION,
                                    severity=Severity.MEDIUM,
                                    url=self.page.url,
                                    element_text=info['text'],
                                    expected_behavior="Disabled elements should be visually distinguished (e.g., grayed out)",
                                    actual_behavior=f"Disabled element has opacity {styles['opacity']}",
                                ))

                    except Exception as e:
                        logger.debug("%s: error evaluating clickable element %s: %s", self.__class__.__name__, selector, e)
                        continue

        except Exception as e:
            logger.debug("%s: _test_clickable_elements failed: %s", self.__class__.__name__, e)

    def _test_hover_states(self):
        """Test hover states on interactive elements."""
        try:
            interactive = self.page.locator('button:visible, a:visible, [role="button"]:visible')
            count = min(interactive.count(), 10)

            elements_without_hover = []

            for i in range(count):
                element = interactive.nth(i)
                try:
                    if not element.is_visible():
                        continue

                    # Get styles before hover
                    before_styles = element.evaluate("""el => ({
                        backgroundColor: window.getComputedStyle(el).backgroundColor,
                        color: window.getComputedStyle(el).color,
                        transform: window.getComputedStyle(el).transform,
                        boxShadow: window.getComputedStyle(el).boxShadow,
                        borderColor: window.getComputedStyle(el).borderColor,
                        textDecoration: window.getComputedStyle(el).textDecoration,
                        text: el.textContent?.slice(0, 30)
                    })""")

                    # Hover over element (3 s cap — covered elements fail fast)
                    element.hover(timeout=3000)
                    self.page.wait_for_timeout(150)  # Wait for transition

                    # Get styles after hover
                    after_styles = element.evaluate("""el => ({
                        backgroundColor: window.getComputedStyle(el).backgroundColor,
                        color: window.getComputedStyle(el).color,
                        transform: window.getComputedStyle(el).transform,
                        boxShadow: window.getComputedStyle(el).boxShadow,
                        borderColor: window.getComputedStyle(el).borderColor,
                        textDecoration: window.getComputedStyle(el).textDecoration
                    })""")

                    # Check if any style changed
                    style_changed = any(
                        before_styles.get(key) != after_styles.get(key)
                        for key in ['backgroundColor', 'color', 'transform', 'boxShadow', 'borderColor', 'textDecoration']
                    )

                    if not style_changed:
                        elements_without_hover.append(before_styles.get('text', 'unknown'))

                except Exception as e:
                    logger.debug("%s: error evaluating hover state: %s", self.__class__.__name__, e)
                    continue

            if len(elements_without_hover) > count * 0.5 and count > 3:
                self.findings.append(Finding(
                    title="Interactive elements lack hover feedback",
                    description=f"{len(elements_without_hover)} of {count} interactive elements have no hover state",
                    category=FindingCategory.MOUSE_INTERACTION,
                    severity=Severity.LOW,
                    url=self.page.url,
                    expected_behavior="Interactive elements should provide visual feedback on hover",
                    actual_behavior="No visual change on hover",
                    metadata={"elements": elements_without_hover[:5]},
                ))

        except Exception as e:
            logger.debug("%s: _test_hover_states failed: %s", self.__class__.__name__, e)

    def _test_double_click(self):
        """Test double-click behavior on elements."""
        try:
            # Find text content that might be selectable
            self.page.locator('p:visible, span:visible, div:visible')

            # Also check for elements that might have dblclick handlers
            dblclick_handlers = self.page.locator('[ondblclick]:visible')

            if dblclick_handlers.count() > 0:
                for i in range(min(dblclick_handlers.count(), 3)):
                    element = dblclick_handlers.nth(i)
                    try:
                        initial_state = self.page.content()[:500]
                        element.dblclick()
                        self.page.wait_for_timeout(200)
                        after_state = self.page.content()[:500]

                        if initial_state == after_state:
                            text = element.text_content()[:30] if element.text_content() else ""
                            self.findings.append(Finding(
                                title="Double-click handler has no effect",
                                description="Element has ondblclick but double-clicking produces no visible change",
                                category=FindingCategory.MOUSE_INTERACTION,
                                severity=Severity.LOW,
                                url=self.page.url,
                                element_text=text,
                                expected_behavior="Double-click handler should produce visible effect",
                                actual_behavior="No visible change after double-click",
                            ))
                    except Exception as e:
                        logger.debug("%s: error testing double-click handler: %s", self.__class__.__name__, e)
                        continue

        except Exception as e:
            logger.debug("%s: _test_double_click failed: %s", self.__class__.__name__, e)

    def _test_right_click(self):
        """Test right-click/context menu behavior."""
        try:
            # Try right-clicking on the page
            self.page.click('body', button='right')
            self.page.wait_for_timeout(200)

            # Check for custom context menu
            custom_menu = self.page.locator('[role="menu"]:visible, .context-menu:visible, .dropdown-menu:visible')

            if custom_menu.count() > 0:
                # Custom menu appeared - this is fine, but check if it's accessible
                menu = custom_menu.first

                # Check if menu items are keyboard accessible
                menu_items = menu.locator('[role="menuitem"], li, a')
                if menu_items.count() > 0:
                    # Try keyboard navigation
                    self.page.keyboard.press("ArrowDown")
                    self.page.wait_for_timeout(100)

                    focused_in_menu = self.page.evaluate("""() => {
                        const active = document.activeElement;
                        const menu = document.querySelector('[role="menu"], .context-menu, .dropdown-menu');
                        return menu && menu.contains(active);
                    }""")

                    if not focused_in_menu:
                        self.findings.append(Finding(
                            title="Context menu not keyboard accessible",
                            description="Custom context menu doesn't support keyboard navigation",
                            category=FindingCategory.MOUSE_INTERACTION,
                            severity=Severity.MEDIUM,
                            url=self.page.url,
                            expected_behavior="Context menus should be navigable with arrow keys",
                            actual_behavior="Arrow keys don't move focus within the menu",
                        ))

                # Close menu
                self.page.keyboard.press("Escape")

        except Exception as e:
            logger.debug("%s: _test_right_click failed: %s", self.__class__.__name__, e)

    def _test_drag_and_drop_targets(self):
        """Test drag-and-drop elements."""
        try:
            draggable = self.page.locator('[draggable="true"]:visible')
            self.page.locator('[ondrop]:visible, [ondragover]:visible, .drop-zone:visible, .dropzone:visible')

            if draggable.count() > 0:
                # Check if draggable elements have proper ARIA
                for i in range(min(draggable.count(), 5)):
                    element = draggable.nth(i)
                    try:
                        aria_info = element.evaluate("""el => ({
                            ariaGrabbed: el.getAttribute('aria-grabbed'),
                            ariaDropeffect: el.getAttribute('aria-dropeffect'),
                            role: el.getAttribute('role'),
                            text: el.textContent?.slice(0, 30)
                        })""")

                        if not aria_info.get('ariaGrabbed') and not aria_info.get('role'):
                            self.findings.append(Finding(
                                title="Draggable element lacks ARIA attributes",
                                description="Draggable element missing aria-grabbed or role attributes",
                                category=FindingCategory.ACCESSIBILITY,
                                severity=Severity.LOW,
                                url=self.page.url,
                                element_text=aria_info.get('text'),
                                expected_behavior="Draggable elements should have aria-grabbed and proper role",
                                actual_behavior="Missing ARIA attributes for drag-and-drop accessibility",
                            ))
                    except Exception as e:
                        logger.debug("%s: error evaluating draggable element ARIA: %s", self.__class__.__name__, e)
                        continue

        except Exception as e:
            logger.debug("%s: _test_drag_and_drop_targets failed: %s", self.__class__.__name__, e)

    def _test_click_target_sizes(self):
        """Test that click targets meet minimum size requirements."""
        try:
            interactive = self.page.locator(
                'button:visible, a:visible, [role="button"]:visible, '
                'input[type="submit"]:visible, input[type="button"]:visible, '
                'input[type="reset"]:visible, input[type="checkbox"]:visible, '
                'input[type="radio"]:visible'
            )
            count = min(interactive.count(), 20)

            small_targets = []
            min_size = 44  # WCAG recommends 44x44px minimum

            for i in range(count):
                element = interactive.nth(i)
                try:
                    if not element.is_visible():
                        continue

                    size = element.evaluate("""el => {
                        const rect = el.getBoundingClientRect();
                        const display = window.getComputedStyle(el).display;
                        return {
                            width: rect.width,
                            height: rect.height,
                            text: el.textContent?.slice(0, 30) || '',
                            tag: el.tagName.toLowerCase(),
                            inline: display === 'inline'
                        };
                    }""")

                    # Inline text links (e.g. "Read more" in body copy) are exempt from
                    # WCAG 2.5.5 target size — the requirement applies to discrete controls.
                    if size['inline']:
                        continue

                    # For <a> elements both dimensions must be small — text links are
                    # naturally wide so a wide-but-short link is not a usability problem.
                    # For discrete controls (button, input) flag if either dimension is small.
                    if size['tag'] == 'a':
                        too_small = size['width'] < min_size and size['height'] < min_size
                    else:
                        too_small = size['width'] < min_size or size['height'] < min_size

                    if too_small:
                        small_targets.append({
                            "text": size['text'],
                            "tag": size['tag'],
                            "size": f"{size['width']:.0f}x{size['height']:.0f}px"
                        })

                except Exception as e:
                    logger.debug("%s: error measuring click target size: %s", self.__class__.__name__, e)
                    continue

            if len(small_targets) > 3:
                self.findings.append(Finding(
                    title="Small click targets detected",
                    description=f"{len(small_targets)} interactive elements smaller than {min_size}x{min_size}px",
                    category=FindingCategory.MOUSE_INTERACTION,
                    severity=Severity.MEDIUM,
                    url=self.page.url,
                    expected_behavior=f"Click targets should be at least {min_size}x{min_size}px for accessibility",
                    actual_behavior="Multiple elements have small click targets",
                    metadata={"small_targets": small_targets[:10]},
                ))

        except Exception as e:
            logger.debug("%s: _test_click_target_sizes failed: %s", self.__class__.__name__, e)

    def _test_overlapping_elements(self):
        """Test for overlapping clickable elements."""
        try:
            interactive = self.page.locator('button:visible, a:visible, [role="button"]:visible')
            count = min(interactive.count(), 20)

            elements_data = []
            for i in range(count):
                element = interactive.nth(i)
                try:
                    if element.is_visible():
                        rect = element.evaluate("""el => {
                            const r = el.getBoundingClientRect();
                            return {
                                left: r.left, top: r.top,
                                right: r.right, bottom: r.bottom,
                                text: el.textContent?.slice(0, 30)
                            };
                        }""")
                        elements_data.append(rect)
                except Exception as e:
                    logger.debug("%s: error measuring element overlap rect: %s", self.__class__.__name__, e)
                    continue

            # Check for overlaps
            overlaps = []
            for i, el1 in enumerate(elements_data):
                for el2 in elements_data[i+1:]:
                    # Check if rectangles overlap
                    if (el1['left'] < el2['right'] and el1['right'] > el2['left'] and
                        el1['top'] < el2['bottom'] and el1['bottom'] > el2['top']):
                        overlaps.append((el1['text'], el2['text']))

            if len(overlaps) > 0:
                self.findings.append(Finding(
                    title="Overlapping clickable elements",
                    description=f"Found {len(overlaps)} pairs of overlapping interactive elements",
                    category=FindingCategory.MOUSE_INTERACTION,
                    severity=Severity.HIGH,
                    url=self.page.url,
                    expected_behavior="Clickable elements should not overlap",
                    actual_behavior="Some interactive elements overlap, making clicks ambiguous",
                    metadata={"overlaps": overlaps[:5]},
                ))

        except Exception as e:
            logger.debug("%s: _test_overlapping_elements failed: %s", self.__class__.__name__, e)
