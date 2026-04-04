"""Base reporter class."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import TestSession


class BaseReporter(ABC):
    """Base class for all report generators."""

    def __init__(self, output_dir: str = "./qa_reports"):
        self.output_dir = output_dir

    @abstractmethod
    def generate(self, session: "TestSession") -> str:
        """Generate the report and return path or output."""
        pass

    def _severity_emoji(self, severity: str) -> str:
        """Get emoji for severity level."""
        return {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🔵",
            "info": "⚪",
        }.get(severity, "⚪")

    def _category_emoji(self, category: str) -> str:
        """Get emoji for category."""
        return {
            "keyboard_navigation": "⌨️",
            "mouse_interaction": "🖱️",
            "form_handling": "📝",
            "accessibility": "♿",
            "console_error": "🔧",
            "network_error": "🌐",
            "visual_issue": "👁️",
            "performance": "⚡",
            "unexpected_behavior": "❓",
        }.get(category, "📋")
