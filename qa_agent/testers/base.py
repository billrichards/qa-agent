"""Base class for all testers."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from playwright.sync_api import Page

if TYPE_CHECKING:
    from ..config import TestConfig
    from ..models import Finding


class BaseTester(ABC):
    """Base class for all test modules."""

    def __init__(self, page: Page, config: "TestConfig"):
        self.page = page
        self.config = config
        self.findings: list[Finding] = []

    @abstractmethod
    def run(self) -> list["Finding"]:
        """Run the tests and return findings."""
        pass

    def _safe_execute(self, action_name: str, action_callable, *args, **kwargs):
        """Safely execute an action and catch exceptions."""
        try:
            return action_callable(*args, **kwargs)
        except Exception as e:
            return {"error": str(e), "action": action_name}

    def _get_element_info(self, selector: str) -> dict:
        """Get information about an element."""
        try:
            element = self.page.locator(selector).first
            if element.count() == 0:
                return {"exists": False}

            return {
                "exists": True,
                "visible": element.is_visible(),
                "enabled": element.is_enabled(),
                "text": (element.text_content() or "")[:100] or None,
                "tag": element.evaluate("el => el.tagName.toLowerCase()"),
            }
        except Exception:
            return {"exists": False, "error": "Could not get element info"}

    def _take_screenshot(self, name: str) -> str | None:
        """Take a screenshot if enabled."""
        if not self.config.screenshots.enabled:
            return None

        import os
        from datetime import datetime

        os.makedirs(self.config.screenshots.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{name}_{timestamp}.png"
        filepath = os.path.join(self.config.screenshots.output_dir, filename)

        try:
            self.page.screenshot(
                path=filepath,
                full_page=self.config.screenshots.full_page
            )
            return filepath
        except Exception:
            return None
