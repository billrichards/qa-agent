"""Configuration management for QA Agent."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from .llm_client import LLMProvider
from .viewports import (
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    MAX_DIMENSION,
    MIN_DIMENSION,
    Viewport,
    coerce_viewports,
)


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
    cookies: dict | list[dict] | None = None  # Pre-set cookies for authentication
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
    output_dir: str = "./qa-agent-output"

    # Browser settings
    headless: bool = True

    # Viewports to sweep. Each entry runs the full page sweep in its own
    # browser context, so findings can be attributed per device profile.
    # Accepts Viewport objects, preset names ("mobile"), raw sizes
    # ("1920x1080"), or dicts; normalised in __post_init__.
    # Empty (the default) means "one viewport at viewport_width x
    # viewport_height", preserving single-viewport behaviour.
    viewports: list[Viewport] = field(default_factory=list)

    # Legacy single-viewport size. Still fully supported as input; after
    # __post_init__ these always mirror the first entry of ``viewports``.
    viewport_width: int = DEFAULT_WIDTH
    viewport_height: int = DEFAULT_HEIGHT
    timeout: int = 30000  # ms

    # Exploration settings
    max_depth: int = 3  # Max navigation depth in explore mode
    max_pages: int = 100  # Max pages to visit in explore mode
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

    # Agentic testing: natural language instructions interpreted by an LLM
    instructions: str | None = None
    llm_provider: LLMProvider = LLMProvider.ANTHROPIC
    ai_model: str | None = None  # None → use the provider's default model
    use_plan_cache: bool = True  # Cache generated test plans to avoid redundant API calls

    # Post-run LLM summary: narrative analysis of findings after the run completes
    generate_summary: bool = False

    # Invocation context — used to tailor diagnostic hints
    invocation_context: Literal["cli", "web"] | None = None

    # Number of concurrent page-workers per run. 1 = sequential (default).
    # Each worker drives its own browser/context, so total browsers scale with
    # this value; it is clamped to a sane ceiling in __post_init__.
    workers: int = 1

    # Hard ceiling on concurrent page-workers to bound browser RAM/CPU.
    WORKERS_MAX = 16

    # Max page navigations per second to any single host (page.goto() only).
    # Shared across all workers/batch jobs targeting that host, to avoid
    # overwhelming fragile dev/staging servers with "too many connections"
    # when --workers / --batch-file fan out many concurrent browsers.
    # 0 disables throttling entirely.
    rate_limit: float = 3.0

    # Ceiling on rate_limit to prevent runaway configs from disabling
    # effective throttling via an absurdly high rate.
    RATE_LIMIT_MAX = 50.0

    # Ceiling on the number of viewports swept in one run. Every viewport is a
    # full re-sweep of every page, so the run cost is multiplied by this count.
    VIEWPORTS_MAX = 10

    def __post_init__(self) -> None:
        self._normalize_viewports()

        # Clamp worker count to [1, WORKERS_MAX]. Defensive against bad input
        # from CLI flags or web request bodies.
        try:
            workers = int(self.workers)
        except (TypeError, ValueError):
            workers = 1
        self.workers = max(1, min(self.WORKERS_MAX, workers))

        # Clamp rate_limit to [0, RATE_LIMIT_MAX]. 0 (or negative) means
        # "unlimited" and is preserved as exactly 0.0 rather than floored up.
        try:
            rate_limit = float(self.rate_limit)
        except (TypeError, ValueError):
            rate_limit = 3.0
        self.rate_limit = 0.0 if rate_limit <= 0 else min(self.RATE_LIMIT_MAX, rate_limit)

    def _normalize_viewports(self) -> None:
        """Resolve ``viewports`` into a non-empty list of :class:`Viewport`.

        Callers may pass preset names, ``WxH`` strings, dicts, or Viewport
        objects; all are coerced here so the agent only ever sees Viewport
        instances. When nothing is given, the legacy
        ``viewport_width``/``viewport_height`` pair becomes the single
        viewport, which keeps existing configs behaving exactly as before.

        Invalid viewport *specs* raise (a typo like ``--viewport moblie`` must
        not silently test the wrong size), but an out-of-range legacy
        width/height falls back to the default rather than raising, matching
        how ``workers`` and ``rate_limit`` treat bad input.
        """
        viewports = coerce_viewports(self.viewports)

        if not viewports:
            width, height = self.viewport_width, self.viewport_height
            if not _in_dimension_range(width) or not _in_dimension_range(height):
                width, height = DEFAULT_WIDTH, DEFAULT_HEIGHT
            viewports = [Viewport(name=f"{width}x{height}", width=width, height=height)]

        self.viewports = viewports[: self.VIEWPORTS_MAX]

        # Keep the legacy scalars meaningful for existing readers (reporters,
        # web UI, third-party SDK callers) by mirroring the first viewport.
        self.viewport_width = self.viewports[0].width
        self.viewport_height = self.viewports[0].height

    @property
    def viewport_names(self) -> list[str]:
        """Names of the viewports this config will sweep, in order."""
        return [vp.name for vp in self.viewports]


def _in_dimension_range(value: object) -> bool:
    """True if ``value`` is an int-like dimension within the allowed bounds."""
    try:
        dimension: int = int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return False
    return MIN_DIMENSION <= dimension <= MAX_DIMENSION
