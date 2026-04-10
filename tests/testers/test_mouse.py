"""Tests for qa_agent/testers/mouse.py — smoke tests and click target size."""

from __future__ import annotations

from unittest.mock import MagicMock

from qa_agent.config import TestConfig
from qa_agent.models import FindingCategory, Severity
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


class TestClickableElements:
    def test_text_cursor_on_button_produces_finding(self):
        """A button showing 'text' cursor instead of 'pointer' should produce a finding."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.is_visible.return_value = True
        element.evaluate.return_value = {
            "tag": "button",
            "text": "Click me",
            "href": None,
            "type": "button",
            "disabled": False,
            "ariaDisabled": None,
            "cursor": "text",
        }

        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.nth.return_value = element
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        tester._test_clickable_elements()

        cursor_findings = [f for f in tester.findings if "cursor" in f.title.lower()]
        assert len(cursor_findings) >= 1
        assert cursor_findings[0].severity == Severity.LOW

    def test_disabled_element_with_high_opacity_produces_finding(self):
        """A visually indistinct disabled element should produce a finding."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.is_visible.return_value = True
        # First evaluate call returns element info, second returns styles
        element.evaluate.side_effect = [
            {
                "tag": "button",
                "text": "Submit",
                "href": None,
                "type": "submit",
                "disabled": True,
                "ariaDisabled": None,
                "cursor": "default",
            },
            {
                "opacity": "1.0",
                "pointerEvents": "none",
            },
        ]

        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.nth.return_value = element
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        tester._test_clickable_elements()

        disabled_findings = [f for f in tester.findings if "disabled" in f.title.lower()]
        assert len(disabled_findings) >= 1
        assert disabled_findings[0].severity == Severity.MEDIUM

    def test_normal_pointer_cursor_no_finding(self):
        """An element with pointer cursor should not produce a cursor finding."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.is_visible.return_value = True
        element.evaluate.return_value = {
            "tag": "button",
            "text": "Click me",
            "href": None,
            "type": "button",
            "disabled": False,
            "ariaDisabled": None,
            "cursor": "pointer",
        }

        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.nth.return_value = element
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        tester._test_clickable_elements()

        cursor_findings = [f for f in tester.findings if "cursor" in f.title.lower()]
        assert len(cursor_findings) == 0

    def test_invisible_element_skipped(self):
        """Elements that are not visible should be skipped without findings."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.is_visible.return_value = False

        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.nth.return_value = element
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        tester._test_clickable_elements()

        assert tester.findings == []

    def test_exception_in_element_eval_skipped(self):
        """If evaluate() raises, the element is skipped gracefully."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.is_visible.return_value = True
        element.evaluate.side_effect = RuntimeError("eval error")

        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.nth.return_value = element
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        tester._test_clickable_elements()  # should not raise

        assert tester.findings == []


class TestHoverStates:
    def test_many_elements_without_hover_produces_finding(self):
        """When >50% of elements (with count>3) have no hover state change, flag it."""
        page = MagicMock()
        page.url = "https://example.com"

        # Same styles before and after hover → no change
        same_style = {
            "backgroundColor": "rgb(0,0,0)",
            "color": "rgb(255,255,255)",
            "transform": "none",
            "boxShadow": "none",
            "borderColor": "rgb(0,0,0)",
            "textDecoration": "none",
            "text": "button",
        }

        element = MagicMock()
        element.is_visible.return_value = True
        element.evaluate.return_value = same_style
        element.hover.return_value = None

        mock_locator = MagicMock()
        mock_locator.count.return_value = 5  # more than 3
        mock_locator.nth.return_value = element
        page.locator.return_value = mock_locator
        page.wait_for_timeout.return_value = None

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        tester._test_hover_states()

        hover_findings = [f for f in tester.findings if "hover" in f.title.lower()]
        assert len(hover_findings) >= 1

    def test_hover_state_changes_no_finding(self):
        """When styles change on hover, no finding should be produced."""
        page = MagicMock()
        page.url = "https://example.com"

        before_style = {
            "backgroundColor": "rgb(0,0,0)",
            "color": "rgb(255,255,255)",
            "transform": "none",
            "boxShadow": "none",
            "borderColor": "rgb(0,0,0)",
            "textDecoration": "none",
            "text": "button",
        }
        after_style = {
            "backgroundColor": "rgb(100,100,100)",  # changed!
            "color": "rgb(255,255,255)",
            "transform": "none",
            "boxShadow": "none",
            "borderColor": "rgb(0,0,0)",
            "textDecoration": "none",
        }

        element = MagicMock()
        element.is_visible.return_value = True
        element.evaluate.side_effect = [before_style, after_style] * 5  # cycle through
        element.hover.return_value = None

        mock_locator = MagicMock()
        mock_locator.count.return_value = 5
        mock_locator.nth.return_value = element
        page.locator.return_value = mock_locator
        page.wait_for_timeout.return_value = None

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        tester._test_hover_states()

        hover_findings = [f for f in tester.findings if "hover" in f.title.lower()]
        assert len(hover_findings) == 0

    def test_fewer_than_4_elements_no_finding(self):
        """With 3 or fewer elements, the hover threshold check is skipped."""
        page = MagicMock()
        page.url = "https://example.com"

        same_style = {
            "backgroundColor": "rgb(0,0,0)",
            "color": "white",
            "transform": "none",
            "boxShadow": "none",
            "borderColor": "black",
            "textDecoration": "none",
            "text": "btn",
        }

        element = MagicMock()
        element.is_visible.return_value = True
        element.evaluate.return_value = same_style
        element.hover.return_value = None

        mock_locator = MagicMock()
        mock_locator.count.return_value = 3  # exactly 3 — threshold not met
        mock_locator.nth.return_value = element
        page.locator.return_value = mock_locator
        page.wait_for_timeout.return_value = None

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        tester._test_hover_states()

        hover_findings = [f for f in tester.findings if "hover" in f.title.lower()]
        assert len(hover_findings) == 0


class TestDoubleClick:
    def test_dblclick_no_effect_produces_finding(self):
        """ondblclick element that produces no visible change → finding."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.text_content.return_value = "double click me"
        element.dblclick.return_value = None

        # Same content before and after → no effect
        page.content.return_value = "<html><body>static</body></html>"

        dblclick_locator = MagicMock()
        dblclick_locator.count.return_value = 1
        dblclick_locator.nth.return_value = element

        # Return empty locator for p/span/div, real locator for ondblclick
        def locator_dispatch(selector):
            if "ondblclick" in selector:
                return dblclick_locator
            return MagicMock(count=MagicMock(return_value=0))

        page.locator.side_effect = locator_dispatch
        page.wait_for_timeout.return_value = None

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        tester._test_double_click()

        dblclick_findings = [f for f in tester.findings if "double" in f.title.lower()]
        assert len(dblclick_findings) >= 1

    def test_dblclick_with_effect_no_finding(self):
        """ondblclick that changes content should produce no finding."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.text_content.return_value = "item"
        element.dblclick.return_value = None

        # Different content after dblclick → has effect
        page.content.side_effect = ["<html>before</html>", "<html>AFTER CHANGE</html>"]

        dblclick_locator = MagicMock()
        dblclick_locator.count.return_value = 1
        dblclick_locator.nth.return_value = element

        def locator_dispatch(selector):
            if "ondblclick" in selector:
                return dblclick_locator
            return MagicMock(count=MagicMock(return_value=0))

        page.locator.side_effect = locator_dispatch
        page.wait_for_timeout.return_value = None

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        tester._test_double_click()

        dblclick_findings = [f for f in tester.findings if "double" in f.title.lower()]
        assert len(dblclick_findings) == 0

    def test_no_dblclick_elements_no_finding(self):
        """No ondblclick elements → no finding."""
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value = MagicMock(count=MagicMock(return_value=0))

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        tester._test_double_click()

        assert tester.findings == []


class TestDragAndDrop:
    def test_draggable_without_aria_produces_finding(self):
        """Draggable element missing aria-grabbed and role → accessibility finding."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.evaluate.return_value = {
            "ariaGrabbed": None,
            "ariaDropeffect": None,
            "role": None,
            "text": "draggable item",
        }

        draggable_locator = MagicMock()
        draggable_locator.count.return_value = 1
        draggable_locator.nth.return_value = element

        page.locator.return_value = draggable_locator

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        tester._test_drag_and_drop_targets()

        drag_findings = [f for f in tester.findings if "draggable" in f.title.lower()]
        assert len(drag_findings) >= 1
        assert drag_findings[0].category == FindingCategory.ACCESSIBILITY

    def test_draggable_with_aria_no_finding(self):
        """Draggable element with aria-grabbed → no accessibility finding."""
        page = MagicMock()
        page.url = "https://example.com"

        element = MagicMock()
        element.evaluate.return_value = {
            "ariaGrabbed": "false",
            "ariaDropeffect": "move",
            "role": "listitem",
            "text": "draggable item",
        }

        draggable_locator = MagicMock()
        draggable_locator.count.return_value = 1
        draggable_locator.nth.return_value = element

        page.locator.return_value = draggable_locator

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        tester._test_drag_and_drop_targets()

        drag_findings = [f for f in tester.findings if "draggable" in f.title.lower()]
        assert len(drag_findings) == 0

    def test_no_draggable_elements_no_finding(self):
        """No draggable elements → no finding."""
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value = MagicMock(count=MagicMock(return_value=0))

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        tester._test_drag_and_drop_targets()

        assert tester.findings == []


class TestOverlappingElements:
    def test_overlapping_elements_produce_finding(self):
        """Two overlapping interactive elements → HIGH severity finding."""
        page = MagicMock()
        page.url = "https://example.com"

        # Two elements that overlap
        element1 = MagicMock()
        element1.is_visible.return_value = True
        element1.evaluate.return_value = {
            "left": 10, "top": 10, "right": 60, "bottom": 60, "text": "Button A"
        }

        element2 = MagicMock()
        element2.is_visible.return_value = True
        element2.evaluate.return_value = {
            "left": 40, "top": 40, "right": 90, "bottom": 90, "text": "Button B"
        }

        mock_locator = MagicMock()
        mock_locator.count.return_value = 2
        mock_locator.nth.side_effect = [element1, element2]
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        tester._test_overlapping_elements()

        overlap_findings = [f for f in tester.findings if "overlapping" in f.title.lower()]
        assert len(overlap_findings) >= 1
        assert overlap_findings[0].severity == Severity.HIGH

    def test_non_overlapping_elements_no_finding(self):
        """Non-overlapping interactive elements → no finding."""
        page = MagicMock()
        page.url = "https://example.com"

        element1 = MagicMock()
        element1.is_visible.return_value = True
        element1.evaluate.return_value = {
            "left": 0, "top": 0, "right": 50, "bottom": 50, "text": "Button A"
        }

        element2 = MagicMock()
        element2.is_visible.return_value = True
        element2.evaluate.return_value = {
            "left": 100, "top": 100, "right": 150, "bottom": 150, "text": "Button B"
        }

        mock_locator = MagicMock()
        mock_locator.count.return_value = 2
        mock_locator.nth.side_effect = [element1, element2]
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        tester._test_overlapping_elements()

        overlap_findings = [f for f in tester.findings if "overlapping" in f.title.lower()]
        assert len(overlap_findings) == 0

    def test_no_elements_no_finding(self):
        """No interactive elements → no finding."""
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value = MagicMock(count=MagicMock(return_value=0))

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        tester._test_overlapping_elements()

        assert tester.findings == []
