"""Data models for QA Agent findings and results."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Severity(Enum):
    """Severity level of a finding."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingCategory(Enum):
    """Category of finding."""
    KEYBOARD_NAVIGATION = "keyboard_navigation"
    MOUSE_INTERACTION = "mouse_interaction"
    FORM_HANDLING = "form_handling"
    ACCESSIBILITY = "accessibility"
    CONSOLE_ERROR = "console_error"
    NETWORK_ERROR = "network_error"
    VISUAL_ISSUE = "visual_issue"
    PERFORMANCE = "performance"
    UNEXPECTED_BEHAVIOR = "unexpected_behavior"


@dataclass
class Finding:
    """A single finding/issue discovered during testing."""
    title: str
    description: str
    category: FindingCategory
    severity: Severity
    url: str
    timestamp: datetime = field(default_factory=datetime.now)
    element_selector: str | None = None
    element_text: str | None = None
    screenshot_path: str | None = None
    steps_to_reproduce: list[str] = field(default_factory=list)
    expected_behavior: str | None = None
    actual_behavior: str | None = None
    raw_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # Populated during deduplication: all URLs where this issue was seen
    affected_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert finding to dictionary."""
        return {
            "title": self.title,
            "description": self.description,
            "category": self.category.value,
            "severity": self.severity.value,
            "url": self.url,
            "timestamp": self.timestamp.isoformat(),
            "element_selector": self.element_selector,
            "element_text": self.element_text,
            "screenshot_path": self.screenshot_path,
            "steps_to_reproduce": self.steps_to_reproduce,
            "expected_behavior": self.expected_behavior,
            "actual_behavior": self.actual_behavior,
            "raw_error": self.raw_error,
            "metadata": self.metadata,
            "affected_urls": self.affected_urls,
        }


@dataclass
class PageInteraction:
    """Record of an interaction with a page element."""
    interaction_type: str  # click, type, keypress, etc.
    element_selector: str
    element_text: str | None
    input_value: str | None = None
    success: bool = True
    error_message: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class PageAnalysis:
    """Analysis results for a single page."""
    url: str
    title: str
    load_time_ms: float
    interactive_elements: int
    forms_count: int
    links_count: int
    images_count: int
    console_errors: list[str] = field(default_factory=list)
    console_warnings: list[str] = field(default_factory=list)
    network_errors: list[dict] = field(default_factory=list)
    interactions: list[PageInteraction] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# AI-generated test plan models
# ---------------------------------------------------------------------------

@dataclass
class StepAction:
    """A single action to perform during a custom test step."""
    type: str  # "click", "fill", "hover", "press_key", "wait", "navigate", "scroll"
    selector: str | None = None
    value: str | None = None  # fill text, key name, wait ms, navigate URL, scroll direction
    description: str | None = None


@dataclass
class StepAssertion:
    """An assertion to check after actions in a custom test step."""
    type: str  # "visible", "hidden", "text_contains", "url_contains", "element_count"
    selector: str | None = None
    value: str | None = None  # expected text, URL fragment, or count
    description: str | None = None


@dataclass
class CustomStep:
    """An AI-generated custom test step."""
    description: str
    actions: list[StepAction] = field(default_factory=list)
    assertions: list[StepAssertion] = field(default_factory=list)
    severity: Severity = field(default_factory=lambda: Severity.MEDIUM)
    category: FindingCategory = field(default_factory=lambda: FindingCategory.UNEXPECTED_BEHAVIOR)


@dataclass
class TestPlan:
    """An AI-generated test plan derived from user instructions."""
    summary: str
    focus_areas: list[str] = field(default_factory=list)
    custom_steps: list[CustomStep] = field(default_factory=list)
    suggested_urls: list[str] = field(default_factory=list)
    notes: str = ""


# ---------------------------------------------------------------------------
# URL normalisation for deduplication
# ---------------------------------------------------------------------------

# Patterns replaced from left to right in the URL *path* segment.
_URL_NORM_PATTERNS: list[tuple[re.Pattern, str]] = [
    # UUID (e.g. 550e8400-e29b-41d4-a716-446655440000)
    (re.compile(
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
        re.IGNORECASE,
    ), '{id}'),
    # Pure numeric segment (e.g. /123 or /456/)
    (re.compile(r'(?<=/)\d+(?=/|$)'), '{id}'),
    # Slug-style alphanumeric ID that ends a path segment and starts with a digit
    # (e.g. /products/123-blue-widget) – only when the segment *starts* with digits
    (re.compile(r'(?<=/)\d[\w-]*(?=/|$)'), '{id}'),
]


def _normalize_url(url: str) -> str:
    """Return a normalised URL with variable path segments replaced by ``{id}``.

    Only the path is modified; the scheme, host, and query string are left
    intact so that issues on genuinely different pages are not incorrectly
    merged.
    """
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(url)
    path = parsed.path
    for pattern, replacement in _URL_NORM_PATTERNS:
        path = pattern.sub(replacement, path)
    normalised = urlunparse(parsed._replace(path=path))
    return normalised


@dataclass
class TestSession:
    """Complete test session results."""
    session_id: str
    start_time: datetime
    end_time: datetime | None = None
    config_summary: dict = field(default_factory=dict)
    pages_tested: list[PageAnalysis] = field(default_factory=list)
    total_findings: int = 0
    findings_by_severity: dict[str, int] = field(default_factory=dict)
    findings_by_category: dict[str, int] = field(default_factory=dict)
    recording_path: str | None = None

    def add_page_analysis(self, page: PageAnalysis):
        """Add page analysis and update totals."""
        self.pages_tested.append(page)
        for finding in page.findings:
            self.total_findings += 1
            sev = finding.severity.value
            cat = finding.category.value
            self.findings_by_severity[sev] = self.findings_by_severity.get(sev, 0) + 1
            self.findings_by_category[cat] = self.findings_by_category.get(cat, 0) + 1

    def get_all_findings(self) -> list["Finding"]:
        """Get all findings across all pages."""
        findings = []
        for page in self.pages_tested:
            findings.extend(page.findings)
        return findings

    def get_deduplicated_findings(self) -> list["Finding"]:
        """Return findings with URL-pattern duplicates collapsed.

        Findings that share the same title, category, severity, and normalized
        URL pattern (e.g. ``/widget/{id}``) are merged into a single entry.
        The merged finding's ``affected_urls`` lists every distinct URL where
        the issue occurred; ``url`` is set to the normalized pattern so it is
        still informative.  Findings that appear on only one URL are returned
        unchanged (``affected_urls`` stays empty).
        """
        groups: dict[tuple, list[Finding]] = {}
        for finding in self.get_all_findings():
            key = (
                finding.title,
                finding.category.value,
                finding.severity.value,
            )
            groups.setdefault(key, []).append(finding)

        deduped: list[Finding] = []
        for (_title, _cat, _sev), group in groups.items():
            if len(group) == 1:
                deduped.append(group[0])
                continue

            # Merge: use the first finding as the representative, update url
            # and affected_urls.  Preserve the original object so screenshots
            # and other metadata from the first occurrence are kept.
            import copy
            merged = copy.copy(group[0])
            merged.url = _normalize_url(group[0].url)
            merged.affected_urls = sorted({f.url for f in group})
            deduped.append(merged)

        return deduped

    @property
    def status(self) -> str:
        """Machine-readable result status for this session.

        ``no_pages_tested`` — no pages were successfully loaded (e.g. all timed out).
        ``issues_found``    — at least one finding was recorded.
        ``passed``          — pages were tested and no findings were recorded.
        """
        if not self.pages_tested:
            return "no_pages_tested"
        if self.total_findings > 0:
            return "issues_found"
        return "passed"

    def to_dict(self) -> dict:
        """Convert session to dictionary."""
        return {
            "session_id": self.session_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "config_summary": self.config_summary,
            "pages_tested": len(self.pages_tested),
            "total_findings": self.total_findings,
            "findings_by_severity": self.findings_by_severity,
            "findings_by_category": self.findings_by_category,
            "recording_path": self.recording_path,
            "status": self.status,
            "findings": [f.to_dict() for f in self.get_deduplicated_findings()],
        }
