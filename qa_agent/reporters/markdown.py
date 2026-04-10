"""Markdown report generator."""

import os
from datetime import datetime
from typing import TYPE_CHECKING

from .base import BaseReporter

if TYPE_CHECKING:
    from ..models import Finding, TestSession


class MarkdownReporter(BaseReporter):
    """Generates Markdown format reports."""

    def generate(self, session: "TestSession") -> str:
        """Generate Markdown report and save to file."""
        os.makedirs(self.output_dir, exist_ok=True)

        timestamp = session.start_time.strftime("%Y%m%d_%H%M%S")
        filename = f"qa_report_{timestamp}.md"
        filepath = os.path.join(self.output_dir, filename)

        content = self._build_report(session)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
            f.write("\n")

        return filepath

    def _build_report(self, session: "TestSession") -> str:
        """Build the complete Markdown report."""
        lines = []

        # Header
        lines.append("# QA Agent Test Report")
        lines.append("")
        lines.append(f"**Session ID:** `{session.session_id}`")
        lines.append(f"**Date:** {session.start_time.strftime('%Y-%m-%d %H:%M:%S')}")

        if session.end_time:
            duration = (session.end_time - session.start_time).total_seconds()
            lines.append(f"**Duration:** {duration:.1f} seconds")

        lines.append(f"**Mode:** {session.config_summary.get('mode', 'N/A')}")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Pages Tested:** {len(session.pages_tested)}")
        lines.append(f"- **Total Findings:** {session.total_findings}")
        lines.append("")

        # Severity breakdown
        if session.findings_by_severity:
            lines.append("### Findings by Severity")
            lines.append("")
            lines.append("| Severity | Count |")
            lines.append("| --- | --- |")
            for severity in ["critical", "high", "medium", "low", "info"]:
                count = session.findings_by_severity.get(severity, 0)
                if count > 0:
                    emoji = self._severity_emoji(severity)
                    lines.append(f"| {emoji} {severity.upper()} | {count} |")
            lines.append("")

        # Category breakdown
        if session.findings_by_category:
            lines.append("### Findings by Category")
            lines.append("")
            lines.append("| Category | Count |")
            lines.append("| --- | --- |")
            for category, count in sorted(session.findings_by_category.items(), key=lambda x: -x[1]):
                if count > 0:
                    emoji = self._category_emoji(category)
                    cat_name = category.replace("_", " ").title()
                    lines.append(f"| {emoji} {cat_name} | {count} |")
            lines.append("")

        # Pages tested
        lines.append("## Pages Tested")
        lines.append("")
        for page in session.pages_tested:
            finding_count = len(page.findings)
            status = "✅" if finding_count == 0 else f"⚠️ {finding_count} issues"
            lines.append(f"- [{page.title or page.url}]({page.url}) - {status}")
        lines.append("")

        # Detailed findings
        findings = session.get_deduplicated_findings()
        raw_count = session.total_findings
        dedup_count = len(findings)
        if findings:
            lines.append("## Detailed Findings")
            lines.append("")
            if dedup_count < raw_count:
                lines.append(
                    f"> **Note:** {raw_count} raw findings were consolidated into "
                    f"{dedup_count} unique issues by grouping identical problems "
                    f"across URL variants (e.g. `/widget/{{id}}`)."
                )
                lines.append("")

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

                emoji = self._severity_emoji(severity)
                lines.append(f"### {emoji} {severity.upper()} Severity")
                lines.append("")

                for i, finding in enumerate(grouped[severity], 1):
                    cat_emoji = self._category_emoji(finding.category.value)
                    lines.extend(self._format_finding(finding, i, cat_emoji))
                    lines.append("")
        elif not session.pages_tested:
            lines.append("## ⚠️ No Pages Tested")
            lines.append("")
            lines.append("No pages were successfully loaded. Check URLs and connectivity.")
            lines.append("")
        else:
            lines.append("## ✅ No Issues Found")
            lines.append("")
            lines.append("All tests passed without detecting any issues.")
            lines.append("")

        # Footer
        lines.append("---")
        lines.append("")
        lines.append(f"*Generated by QA Agent on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        if session.recording_path:
            lines.append("")
            lines.append(f"📹 **Session Recording:** `{session.recording_path}`")

        return "\n".join(lines)

    def _format_finding(self, finding: "Finding", index: int, emoji: str) -> list[str]:
        """Format a single finding as Markdown, with screenshot paths relative to the report file."""
        lines = []

        lines.append(f"#### {index}. {emoji} {finding.title}")
        lines.append("")
        lines.append(f"**Description:** {finding.description}")
        lines.append("")

        if finding.url:
            if finding.affected_urls:
                lines.append(f"**URL Pattern:** `{finding.url}` — affects {len(finding.affected_urls)} pages")
                lines.append("")
                lines.append("<details><summary>Affected pages</summary>")
                lines.append("")
                for u in finding.affected_urls:
                    lines.append(f"- [{u}]({u})")
                lines.append("")
                lines.append("</details>")
            else:
                lines.append(f"**URL:** [{finding.url}]({finding.url})")
            lines.append("")

        if finding.element_selector:
            lines.append(f"**Element:** `{finding.element_selector}`")
            lines.append("")

        if finding.element_text:
            lines.append(f"**Element Text:** {finding.element_text}")
            lines.append("")

        if finding.expected_behavior or finding.actual_behavior:
            lines.append("| Expected | Actual |")
            lines.append("| --- | --- |")
            expected = (finding.expected_behavior or "-").replace("|", "\\|")
            actual = (finding.actual_behavior or "-").replace("|", "\\|")
            lines.append(f"| {expected} | {actual} |")
            lines.append("")

        if finding.steps_to_reproduce:
            lines.append("**Steps to Reproduce:**")
            for step in finding.steps_to_reproduce:
                lines.append(f"1. {step}")
            lines.append("")

        if finding.screenshot_path:
            # Make screenshot path relative to the markdown file location
            from pathlib import Path
            report_dir = Path(self.output_dir)
            screenshot_path = Path(finding.screenshot_path)
            try:
                rel_path = screenshot_path.relative_to(report_dir)
            except ValueError:
                # If not a subpath, fall back to os.path.relpath
                rel_path = Path(os.path.relpath(str(screenshot_path), str(report_dir)))
            lines.append(f"**Screenshot:** ![Screenshot]({rel_path})")
            lines.append("")

        if finding.raw_error:
            lines.append("**Raw Error:**")
            lines.append("")
            lines.append("```")
            lines.append(finding.raw_error[:500])
            lines.append("```")
            lines.append("")

        if finding.metadata:
            import json
            lines.append("<details><summary><strong>Additional Details</strong></summary>")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(finding.metadata, indent=2, default=str))
            lines.append("```")
            lines.append("")
            lines.append("</details>")
            lines.append("")

        # Strip trailing blank lines — the caller appends exactly one blank
        # between findings, so we avoid producing double blank lines.
        while lines and lines[-1] == "":
            lines.pop()

        return lines
