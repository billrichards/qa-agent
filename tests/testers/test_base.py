"""Tests for qa_agent/testers/base.py — BaseTester utility methods."""

from __future__ import annotations

from unittest.mock import MagicMock

from qa_agent.config import ScreenshotConfig, TestConfig
from qa_agent.testers.mouse import MouseTester  # concrete subclass of BaseTester


def _tester(page=None, screenshots_enabled=False) -> MouseTester:
    """Create a MouseTester (concrete BaseTester subclass) with optional screenshot config."""
    if page is None:
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.return_value = MagicMock(count=MagicMock(return_value=0))
    config = TestConfig(
        urls=["https://example.com"],
        screenshots=ScreenshotConfig(enabled=screenshots_enabled),
    )
    return MouseTester(page, config)


class TestSafeExecute:
    def test_successful_callable_returns_result(self):
        tester = _tester()
        result = tester._safe_execute("test_action", lambda: 42)
        assert result == 42

    def test_exception_returns_error_dict(self):
        def failing():
            raise ValueError("something went wrong")

        tester = _tester()
        result = tester._safe_execute("my_action", failing)
        assert isinstance(result, dict)
        assert "error" in result
        assert "something went wrong" in result["error"]
        assert result["action"] == "my_action"

    def test_callable_with_args(self):
        tester = _tester()
        result = tester._safe_execute("add", lambda a, b: a + b, 3, 7)
        assert result == 10

    def test_callable_with_kwargs(self):
        tester = _tester()
        result = tester._safe_execute("greet", lambda name="world": f"hello {name}", name="alice")
        assert result == "hello alice"


class TestGetElementInfo:
    def test_element_exists_returns_info(self):
        page = MagicMock()
        page.url = "https://example.com"

        mock_element = MagicMock()
        mock_element.count.return_value = 1
        mock_element.is_visible.return_value = True
        mock_element.is_enabled.return_value = True
        mock_element.text_content.return_value = "Click me"
        mock_element.evaluate.return_value = "button"

        mock_locator = MagicMock()
        mock_locator.first = mock_element
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        info = tester._get_element_info("button#submit")

        assert info["exists"] is True
        assert info["visible"] is True
        assert info["enabled"] is True
        assert info["tag"] == "button"

    def test_element_not_found_returns_not_exists(self):
        page = MagicMock()
        page.url = "https://example.com"

        mock_element = MagicMock()
        mock_element.count.return_value = 0  # nothing found

        mock_locator = MagicMock()
        mock_locator.first = mock_element
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        info = tester._get_element_info("#nonexistent")

        assert info["exists"] is False

    def test_exception_returns_error_dict(self):
        page = MagicMock()
        page.url = "https://example.com"
        page.locator.side_effect = RuntimeError("locator failure")

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        info = tester._get_element_info("button")

        assert info["exists"] is False
        assert "error" in info

    def test_none_text_content_handled(self):
        page = MagicMock()
        page.url = "https://example.com"

        mock_element = MagicMock()
        mock_element.count.return_value = 1
        mock_element.is_visible.return_value = True
        mock_element.is_enabled.return_value = False
        mock_element.text_content.return_value = None  # empty element
        mock_element.evaluate.return_value = "span"

        mock_locator = MagicMock()
        mock_locator.first = mock_element
        page.locator.return_value = mock_locator

        config = TestConfig(urls=["https://example.com"])
        tester = MouseTester(page, config)
        info = tester._get_element_info("span")

        assert info["exists"] is True
        assert info["text"] is None


class TestTakeScreenshot:
    def test_screenshots_disabled_returns_none(self):
        page = MagicMock()
        page.url = "https://example.com"
        config = TestConfig(
            urls=["https://example.com"],
            screenshots=ScreenshotConfig(enabled=False),
        )
        tester = MouseTester(page, config)

        result = tester._take_screenshot("test_name")
        assert result is None
        page.screenshot.assert_not_called()

    def test_screenshots_enabled_returns_filepath(self, tmp_path):
        page = MagicMock()
        page.url = "https://example.com"
        page.screenshot.return_value = None

        config = TestConfig(
            urls=["https://example.com"],
            screenshots=ScreenshotConfig(enabled=True, output_dir=str(tmp_path), full_page=False),
        )
        tester = MouseTester(page, config)

        result = tester._take_screenshot("my_test")
        assert result is not None
        assert "my_test" in result
        assert result.endswith(".png")

    def test_screenshots_creates_directory(self, tmp_path):
        page = MagicMock()
        page.url = "https://example.com"
        page.screenshot.return_value = None

        new_dir = tmp_path / "screenshots" / "nested"
        config = TestConfig(
            urls=["https://example.com"],
            screenshots=ScreenshotConfig(enabled=True, output_dir=str(new_dir), full_page=True),
        )
        tester = MouseTester(page, config)
        tester._take_screenshot("dir_creation_test")

        assert new_dir.exists()

    def test_screenshot_failure_returns_none(self, tmp_path):
        page = MagicMock()
        page.url = "https://example.com"
        page.screenshot.side_effect = RuntimeError("browser crashed")

        config = TestConfig(
            urls=["https://example.com"],
            screenshots=ScreenshotConfig(enabled=True, output_dir=str(tmp_path), full_page=False),
        )
        tester = MouseTester(page, config)

        result = tester._take_screenshot("failing_screenshot")
        assert result is None
