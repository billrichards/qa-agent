"""Configuration management for QA Agent."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class TestMode(Enum):
    """Testing mode for the QA agent."""
    FOCUSED = "focused"  # Test only the given URL(s)
    EXPLORE = "explore"  # Navigate and discover new pages


class OutputFormat(Enum):
    """Output format for test results."""
    CONSOLE = "console"
    MARKDOWN = "markdown"
    JSON = "json"
    PDF = "pdf"


@dataclass
class AuthConfig:
    """Authentication configuration."""
    username: str | None = None
    password: str | None = None
    auth_url: str | None = None  # URL to perform login
    username_selector: str | None = None  # Selector for username field
    password_selector: str | None = None  # Selector for password field
    submit_selector: str | None = None  # Selector for submit button
    cookies: dict | None = None  # Pre-set cookies for authentication
    headers: dict | None = None  # Custom headers (e.g., Bearer token)


@dataclass
class ScreenshotConfig:
    """Screenshot configuration."""
    enabled: bool = True
    on_error: bool = True  # Capture on errors
    on_interaction: bool = False  # Capture on each interaction
    full_page: bool = False
    output_dir: str = "./output"


@dataclass
class RecordingConfig:
    """Session recording configuration."""
    enabled: bool = False
    output_dir: str = "./output"
    video_size: dict = field(default_factory=lambda: {"width": 1280, "height": 720})


@dataclass
class TestConfig:
    """Main test configuration."""
    urls: list[str] = field(default_factory=list)
    mode: TestMode = TestMode.FOCUSED
    output_formats: list[OutputFormat] = field(
        default_factory=lambda: [OutputFormat.CONSOLE, OutputFormat.MARKDOWN]
    )
    output_dir: str = "./output"

    # Browser settings
    headless: bool = True
    viewport_width: int = 1280
    viewport_height: int = 720
    timeout: int = 30000  # ms

    # Exploration settings
    max_depth: int = 3  # Max navigation depth in explore mode
    max_pages: int = 20  # Max pages to visit in explore mode
    max_interactions_per_page: int = 50  # Max interactions per page

    # Test categories to run
    test_keyboard: bool = True
    test_mouse: bool = True
    test_forms: bool = True
    test_accessibility: bool = True
    test_console_errors: bool = True
    test_network_errors: bool = True
    test_wcag_compliance: bool = False  # Detailed WCAG 2.1 AA compliance (opt-in, intensive)

    # Authentication
    auth: AuthConfig | None = None

    # Screenshots and recording
    screenshots: ScreenshotConfig = field(default_factory=ScreenshotConfig)
    recording: RecordingConfig = field(default_factory=RecordingConfig)

    # Ignore patterns (URLs to skip in explore mode)
    ignore_patterns: list[str] = field(default_factory=list)

    # Stay within same domain in explore mode
    same_domain_only: bool = True

    # Agentic testing: natural language instructions interpreted by Claude
    instructions: str | None = None
    ai_model: str = "claude-sonnet-4-6"
    use_plan_cache: bool = True  # Cache generated test plans to avoid redundant API calls

    # Invocation context — used to tailor diagnostic hints
    invocation_context: Literal["cli", "web"] | None = None
