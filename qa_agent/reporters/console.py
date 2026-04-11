"""Console reporter for real-time output."""

import sys
from typing import TYPE_CHECKING

from .base import BaseReporter

if TYPE_CHECKING:
    from ..models import Finding, TestSession


class ConsoleReporter(BaseReporter):
    """Outputs test results to the console in real-time."""

    def __init__(self, output_dir: str = "./qa_reports", use_colors: bool = True):
        super().__init__(output_dir)
        self.use_colors = use_colors and sys.stdout.isatty()

    def _color(self, text: str, color_code: str) -> str:
        """Apply ANSI color code to text."""
        if not self.use_colors:
            return text
        return f"\033[{color_code}m{text}\033[0m"

    def _severity_color(self, severity: str) -> str:
        """Get color for severity."""
        return {
            "critical": "91",  # Red
            "high": "93",      # Yellow
            "medium": "33",    # Dark yellow
            "low": "94",       # Blue
            "info": "90",      # Gray
        }.get(severity, "0")

    def generate(self, session: "TestSession") -> str:
        """Generate console output for the complete session."""
        self._print_header(session)
        self._print_summary(session)
        self._print_findings(session)
        self._print_footer(session)
        return "Console output complete"

    def print_finding(self, finding: "Finding"):
        """Print a single finding in real-time."""
        emoji = self._severity_emoji(finding.severity.value)
        cat_emoji = self._category_emoji(finding.category.value)
        severity = finding.severity.value.upper()
        color = self._severity_color(finding.severity.value)

        print(f"\n{emoji} {self._color(f'[{severity}]', color)} {cat_emoji} {finding.title}")
        print(f"   {finding.description}")
        if finding.url:
            print(f"   📍 {self._color(finding.url, '90')}")

    def print_progress(self, message: str):
        """Print progress message."""
        print(f"  → {message}")

    def print_warning(self, message: str) -> None:
        """Print a test reliability warning."""
        print(f"  ⚠  {self._color('WARNING:', '93')} {message}")

    def print_page_start(self, url: str):
        """Print when starting to test a new page."""
        print(f"\n{'='*60}")
        print(f"🔍 Testing: {self._color(url, '96')}")
        print(f"{'='*60}")

    def print_test_category(self, category: str):
        """Print test category being run."""
        print(f"  📋 Running {category} tests...")

    def _print_header(self, session: "TestSession"):
        """Print report header."""
        print("\n" + "=" * 70)
        print(self._color("  QA AGENT TEST REPORT", "1;96"))
        print("=" * 70)
        print(f"  Session ID: {session.session_id}")
        print(f"  Started:    {session.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        if session.end_time:
            duration = (session.end_time - session.start_time).total_seconds()
            print(f"  Completed:  {session.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  Duration:   {duration:.1f} seconds")
        print(f"  Mode:       {session.config_summary.get('mode', 'N/A')}")
        print("=" * 70)

    def _print_summary(self, session: "TestSession"):
        """Print summary statistics."""
        print(f"\n{self._color('📊 SUMMARY', '1;97')}")
        print("-" * 40)
        print(f"  Pages tested: {len(session.pages_tested)}")
        print(f"  Total findings: {session.total_findings}")

        if session.findings_by_severity:
            print(f"\n  {self._color('By Severity:', '1')}")
            for severity in ["critical", "high", "medium", "low", "info"]:
                count = session.findings_by_severity.get(severity, 0)
                if count > 0:
                    emoji = self._severity_emoji(severity)
                    color = self._severity_color(severity)
                    print(f"    {emoji} {self._color(severity.upper(), color)}: {count}")

        if session.findings_by_category:
            print(f"\n  {self._color('By Category:', '1')}")
            for category, count in sorted(session.findings_by_category.items(), key=lambda x: -x[1]):
                if count > 0:
                    emoji = self._category_emoji(category)
                    print(f"    {emoji} {category.replace('_', ' ').title()}: {count}")

    def _print_findings(self, session: "TestSession"):
        """Print all findings grouped by severity."""
        findings = session.get_all_findings()

        if not findings:
            if not session.pages_tested:
                print(f"\n{self._color('⚠️  No pages were successfully tested!', '93')}")
            else:
                print(f"\n{self._color('✅ No issues found!', '92')}")
            return

        print(f"\n{self._color('📋 FINDINGS', '1;97')}")
        print("-" * 40)

        # Group by severity
        severity_order = ["critical", "high", "medium", "low", "info"]
        grouped: dict[str, list] = {}
        for finding in findings:
            sev = finding.severity.value
            if sev not in grouped:
                grouped[sev] = []
            grouped[sev].append(finding)

        for severity in severity_order:
            if severity not in grouped:
                continue

            color = self._severity_color(severity)
            emoji = self._severity_emoji(severity)
            print(f"\n{emoji} {self._color(severity.upper() + ' SEVERITY', f'1;{color}')}")

            for i, finding in enumerate(grouped[severity], 1):
                cat_emoji = self._category_emoji(finding.category.value)
                print(f"\n  {i}. {cat_emoji} {self._color(finding.title, '1')}")
                print(f"     {finding.description}")

                if finding.url:
                    print(f"     📍 URL: {self._color(finding.url, '90')}")
                if finding.element_selector:
                    print(f"     🎯 Selector: {finding.element_selector}")
                if finding.expected_behavior:
                    print(f"     ✓ Expected: {finding.expected_behavior}")
                if finding.actual_behavior:
                    print(f"     ✗ Actual: {finding.actual_behavior}")
                if finding.steps_to_reproduce:
                    print(f"     📝 Steps: {', '.join(finding.steps_to_reproduce)}")

    def _print_footer(self, session: "TestSession"):
        """Print report footer."""
        print("\n" + "=" * 70)

        if not session.pages_tested:
            print(self._color("  ⚠️  No pages were successfully tested — check URLs and connectivity", "93"))
        elif session.total_findings == 0:
            print(self._color("  ✅ All tests passed with no issues found!", "92"))
        else:
            critical_high = session.findings_by_severity.get("critical", 0) + session.findings_by_severity.get("high", 0)
            if critical_high > 0:
                print(self._color(f"  ⚠️  {critical_high} critical/high severity issues require attention", "91"))
            else:
                print(self._color(f"  ℹ️  {session.total_findings} issues found, none critical", "93"))

        if session.recording_path:
            print(f"  📹 Recording saved: {session.recording_path}")

        print("=" * 70 + "\n")
