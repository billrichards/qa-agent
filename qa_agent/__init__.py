"""
QA Agent - Automated Exploratory Testing Tool

A Python/Playwright-based QA agent that performs exploratory testing on web applications,
testing various input methods and detecting UX issues.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("qa-agent")
except PackageNotFoundError:
    # Package not installed (e.g. running from source without install)
    __version__ = "0.3.0"

from .agent import QAAgent  # noqa: E402
from .batch import BatchJob, BatchRunner  # noqa: E402
from .config import (  # noqa: E402
    AuthConfig,
    OutputFormat,
    RecordingConfig,
    ScreenshotConfig,
    TestConfig,
    TestMode,
)
from .llm_client import LLMProvider  # noqa: E402
from .models import Finding, PageAnalysis, Severity, TestSession  # noqa: E402
from .viewports import (  # noqa: E402
    PRESETS,
    Viewport,
    list_presets,
    parse_viewports,
)

__all__ = [
    "QAAgent",
    "BatchRunner",
    "BatchJob",
    "TestConfig",
    "AuthConfig",
    "ScreenshotConfig",
    "RecordingConfig",
    "TestMode",
    "OutputFormat",
    "LLMProvider",
    "TestSession",
    "PageAnalysis",
    "Finding",
    "Severity",
    "Viewport",
    "PRESETS",
    "list_presets",
    "parse_viewports",
    "__version__",
]
