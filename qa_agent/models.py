"""Data models for QA Agent findings and results."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any


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
    element_selector: Optional[str] = None
    element_text: Optional[str] = None
    screenshot_path: Optional[str] = None
    steps_to_reproduce: list[str] = field(default_factory=list)
    expected_behavior: Optional[str] = None
    actual_behavior: Optional[str] = None
    raw_error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

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
        }


@dataclass
class PageInteraction:
    """Record of an interaction with a page element."""
    interaction_type: str  # click, type, keypress, etc.
    element_selector: str
    element_text: Optional[str]
    input_value: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
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


@dataclass
class TestSession:
    """Complete test session results."""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    config_summary: dict = field(default_factory=dict)
    pages_tested: list[PageAnalysis] = field(default_factory=list)
    total_findings: int = 0
    findings_by_severity: dict[str, int] = field(default_factory=dict)
    findings_by_category: dict[str, int] = field(default_factory=dict)
    recording_path: Optional[str] = None

    def add_page_analysis(self, page: PageAnalysis):
        """Add page analysis and update totals."""
        self.pages_tested.append(page)
        for finding in page.findings:
            self.total_findings += 1
            sev = finding.severity.value
            cat = finding.category.value
            self.findings_by_severity[sev] = self.findings_by_severity.get(sev, 0) + 1
            self.findings_by_category[cat] = self.findings_by_category.get(cat, 0) + 1

    def get_all_findings(self) -> list[Finding]:
        """Get all findings across all pages."""
        findings = []
        for page in self.pages_tested:
            findings.extend(page.findings)
        return findings

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
            "findings": [f.to_dict() for f in self.get_all_findings()],
        }
