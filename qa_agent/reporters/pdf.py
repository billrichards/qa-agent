"""PDF report generator using WeasyPrint."""

import os
from datetime import datetime
from typing import TYPE_CHECKING

from .base import BaseReporter

if TYPE_CHECKING:
    from ..models import TestSession, Finding


class PDFReporter(BaseReporter):
    """Generates PDF format reports using WeasyPrint."""

    def generate(self, session: "TestSession") -> str:
        """Generate PDF report and save to file."""
        try:
            from weasyprint import HTML, CSS
        except ImportError:
            raise ImportError(
                "weasyprint is required for PDF output. "
                "Install it with: pip install weasyprint"
            )

        os.makedirs(self.output_dir, exist_ok=True)

        timestamp = session.start_time.strftime("%Y%m%d_%H%M%S")
        filename = f"qa_report_{timestamp}.pdf"
        filepath = os.path.join(self.output_dir, filename)

        html_content = self._build_html(session)
        css = self._get_styles()

        HTML(string=html_content).write_pdf(filepath, stylesheets=[CSS(string=css)])

        return filepath

    def _get_styles(self) -> str:
        """Return CSS styles for the PDF report."""
        return """
            @page {
                size: A4;
                margin: 2cm;
                @bottom-center {
                    content: "Page " counter(page) " of " counter(pages);
                    font-size: 10px;
                    color: #666;
                }
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                font-size: 11px;
                line-height: 1.5;
                color: #333;
            }

            h1 {
                color: #1a1a1a;
                font-size: 24px;
                border-bottom: 2px solid #333;
                padding-bottom: 8px;
                margin-bottom: 16px;
            }

            h2 {
                color: #2c3e50;
                font-size: 18px;
                margin-top: 24px;
                margin-bottom: 12px;
                border-bottom: 1px solid #ddd;
                padding-bottom: 4px;
            }

            h3 {
                color: #34495e;
                font-size: 14px;
                margin-top: 16px;
                margin-bottom: 8px;
            }

            h4 {
                color: #555;
                font-size: 12px;
                margin-top: 12px;
                margin-bottom: 6px;
            }

            .meta {
                background-color: #f8f9fa;
                padding: 12px;
                border-radius: 4px;
                margin-bottom: 20px;
            }

            .meta p {
                margin: 4px 0;
            }

            table {
                width: 100%;
                border-collapse: collapse;
                margin: 12px 0;
                font-size: 10px;
            }

            th, td {
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }

            th {
                background-color: #f2f2f2;
                font-weight: 600;
            }

            tr:nth-child(even) {
                background-color: #fafafa;
            }

            .severity-critical { color: #d63031; font-weight: bold; }
            .severity-high { color: #e17055; font-weight: bold; }
            .severity-medium { color: #fdcb6e; }
            .severity-low { color: #74b9ff; }
            .severity-info { color: #636e72; }

            .finding {
                background-color: #fff;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 12px;
                margin: 12px 0;
                page-break-inside: avoid;
            }

            .finding-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 8px;
            }

            .finding-title {
                font-weight: 600;
                font-size: 12px;
            }

            .badge {
                display: inline-block;
                padding: 2px 8px;
                border-radius: 3px;
                font-size: 9px;
                font-weight: 600;
                text-transform: uppercase;
            }

            .badge-critical { background-color: #d63031; color: white; }
            .badge-high { background-color: #e17055; color: white; }
            .badge-medium { background-color: #fdcb6e; color: #333; }
            .badge-low { background-color: #74b9ff; color: #333; }
            .badge-info { background-color: #b2bec3; color: #333; }

            .label {
                font-weight: 600;
                color: #555;
            }

            .code {
                font-family: 'Courier New', monospace;
                background-color: #f5f5f5;
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 10px;
                word-break: break-all;
            }

            .steps-list {
                margin: 8px 0;
                padding-left: 20px;
            }

            .steps-list li {
                margin: 4px 0;
            }

            pre {
                background-color: #f5f5f5;
                padding: 10px;
                border-radius: 4px;
                overflow-x: auto;
                font-size: 9px;
                white-space: pre-wrap;
                word-wrap: break-word;
            }

            .page-list {
                margin: 0;
                padding-left: 20px;
            }

            .page-list li {
                margin: 4px 0;
            }

            .success { color: #00b894; }
            .warning { color: #fdcb6e; }

            .footer {
                margin-top: 30px;
                padding-top: 10px;
                border-top: 1px solid #ddd;
                text-align: center;
                font-size: 9px;
                color: #666;
            }

            img.screenshot {
                max-width: 100%;
                max-height: 300px;
                border: 1px solid #ddd;
                border-radius: 4px;
                margin: 8px 0;
            }

            .comparison-table td {
                width: 50%;
                vertical-align: top;
            }
        """

    def _build_html(self, session: "TestSession") -> str:
        """Build the complete HTML content for PDF generation."""
        lines = ['<!DOCTYPE html>', '<html>', '<head>', '<meta charset="UTF-8">', '</head>', '<body>']

        # Header
        lines.append('<h1>QA Agent Test Report</h1>')

        # Metadata
        lines.append('<div class="meta">')
        lines.append(f'<p><span class="label">Session ID:</span> <span class="code">{session.session_id}</span></p>')
        lines.append(f'<p><span class="label">Date:</span> {session.start_time.strftime("%Y-%m-%d %H:%M:%S")}</p>')

        if session.end_time:
            duration = (session.end_time - session.start_time).total_seconds()
            lines.append(f'<p><span class="label">Duration:</span> {duration:.1f} seconds</p>')

        lines.append(f'<p><span class="label">Mode:</span> {session.config_summary.get("mode", "N/A")}</p>')
        lines.append('</div>')

        # Summary
        lines.append('<h2>Summary</h2>')
        lines.append(f'<p><span class="label">Pages Tested:</span> {len(session.pages_tested)}</p>')
        lines.append(f'<p><span class="label">Total Findings:</span> {session.total_findings}</p>')

        # Severity breakdown table
        if session.findings_by_severity:
            lines.append('<h3>Findings by Severity</h3>')
            lines.append('<table>')
            lines.append('<tr><th>Severity</th><th>Count</th></tr>')
            for severity in ["critical", "high", "medium", "low", "info"]:
                count = session.findings_by_severity.get(severity, 0)
                if count > 0:
                    emoji = self._severity_emoji(severity)
                    lines.append(
                        f'<tr><td class="severity-{severity}">{emoji} {severity.upper()}</td>'
                        f'<td>{count}</td></tr>'
                    )
            lines.append('</table>')

        # Category breakdown table
        if session.findings_by_category:
            lines.append('<h3>Findings by Category</h3>')
            lines.append('<table>')
            lines.append('<tr><th>Category</th><th>Count</th></tr>')
            for category, count in sorted(session.findings_by_category.items(), key=lambda x: -x[1]):
                if count > 0:
                    emoji = self._category_emoji(category)
                    cat_name = category.replace("_", " ").title()
                    lines.append(f'<tr><td>{emoji} {cat_name}</td><td>{count}</td></tr>')
            lines.append('</table>')

        # Pages tested
        lines.append('<h2>Pages Tested</h2>')
        lines.append('<ul class="page-list">')
        for page in session.pages_tested:
            finding_count = len(page.findings)
            if finding_count == 0:
                status = '<span class="success">✓ No issues</span>'
            else:
                status = f'<span class="warning">⚠ {finding_count} issue(s)</span>'
            title = self._escape_html(page.title or page.url)
            lines.append(f'<li><strong>{title}</strong><br/>{page.url} — {status}</li>')
        lines.append('</ul>')

        # Detailed findings
        findings = session.get_deduplicated_findings()
        raw_count = session.total_findings
        dedup_count = len(findings)

        if findings:
            lines.append('<h2>Detailed Findings</h2>')
            if dedup_count < raw_count:
                lines.append(
                    f'<p><em>{raw_count} raw findings were consolidated into {dedup_count} '
                    f'unique issues by grouping identical problems across URL variants.</em></p>'
                )

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
                lines.append(f'<h3>{emoji} {severity.upper()} Severity</h3>')

                for i, finding in enumerate(grouped[severity], 1):
                    lines.extend(self._format_finding_html(finding, i, severity))
        else:
            lines.append('<h2>✅ No Issues Found</h2>')
            lines.append('<p>All tests passed without detecting any issues.</p>')

        # Footer
        lines.append('<div class="footer">')
        lines.append(f'Generated by QA Agent on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        if session.recording_path:
            lines.append(f'<br/>Session Recording: {session.recording_path}')
        lines.append('</div>')

        lines.append('</body>')
        lines.append('</html>')

        return '\n'.join(lines)

    def _format_finding_html(self, finding: "Finding", index: int, severity: str) -> list[str]:
        """Format a single finding as HTML."""
        lines = []

        cat_emoji = self._category_emoji(finding.category.value)
        cat_name = finding.category.value.replace("_", " ").title()

        lines.append('<div class="finding">')
        lines.append('<div class="finding-header">')
        lines.append(f'<span class="finding-title">{index}. {cat_emoji} {self._escape_html(finding.title)}</span>')
        lines.append(f'<span class="badge badge-{severity}">{severity}</span>')
        lines.append('</div>')

        lines.append(f'<p><span class="label">Category:</span> {cat_name}</p>')
        lines.append(f'<p><span class="label">Description:</span> {self._escape_html(finding.description)}</p>')

        if finding.url:
            if finding.affected_urls:
                lines.append(
                    f'<p><span class="label">URL Pattern:</span> '
                    f'<span class="code">{self._escape_html(finding.url)}</span> '
                    f'— affects {len(finding.affected_urls)} pages</p>'
                )
                lines.append('<p><span class="label">Affected Pages:</span></p>')
                lines.append('<ul class="page-list">')
                for u in finding.affected_urls[:10]:  # Limit to first 10 to save space
                    lines.append(f'<li><span class="code">{self._escape_html(u)}</span></li>')
                if len(finding.affected_urls) > 10:
                    lines.append(f'<li><em>... and {len(finding.affected_urls) - 10} more</em></li>')
                lines.append('</ul>')
            else:
                lines.append(
                    f'<p><span class="label">URL:</span> '
                    f'<span class="code">{self._escape_html(finding.url)}</span></p>'
                )

        if finding.element_selector:
            lines.append(
                f'<p><span class="label">Element:</span> '
                f'<span class="code">{self._escape_html(finding.element_selector)}</span></p>'
            )

        if finding.element_text:
            lines.append(
                f'<p><span class="label">Element Text:</span> '
                f'{self._escape_html(finding.element_text)}</p>'
            )

        if finding.expected_behavior or finding.actual_behavior:
            lines.append('<table class="comparison-table">')
            lines.append('<tr><th>Expected</th><th>Actual</th></tr>')
            expected = self._escape_html(finding.expected_behavior or "-")
            actual = self._escape_html(finding.actual_behavior or "-")
            lines.append(f'<tr><td>{expected}</td><td>{actual}</td></tr>')
            lines.append('</table>')

        if finding.steps_to_reproduce:
            lines.append('<p><span class="label">Steps to Reproduce:</span></p>')
            lines.append('<ol class="steps-list">')
            for step in finding.steps_to_reproduce:
                lines.append(f'<li>{self._escape_html(step)}</li>')
            lines.append('</ol>')

        if finding.screenshot_path:
            # Embed screenshot as file reference (WeasyPrint can handle local paths)
            lines.append(f'<p><span class="label">Screenshot:</span></p>')
            lines.append(f'<img class="screenshot" src="file://{finding.screenshot_path}" alt="Screenshot"/>')

        if finding.raw_error:
            lines.append('<p><span class="label">Raw Error:</span></p>')
            lines.append(f'<pre>{self._escape_html(finding.raw_error[:500])}</pre>')

        lines.append('</div>')

        return lines

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )
