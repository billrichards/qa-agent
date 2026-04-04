"""JSON report generator."""

import json
import os
from datetime import datetime
from typing import TYPE_CHECKING

from .base import BaseReporter

if TYPE_CHECKING:
    from ..models import TestSession


class JSONReporter(BaseReporter):
    """Generates JSON format reports."""

    def __init__(self, output_dir: str = "./qa_reports", indent: int = 2):
        super().__init__(output_dir)
        self.indent = indent

    def generate(self, session: "TestSession") -> str:
        """Generate JSON report and save to file."""
        os.makedirs(self.output_dir, exist_ok=True)
        
        timestamp = session.start_time.strftime("%Y%m%d_%H%M%S")
        filename = f"qa_report_{timestamp}.json"
        filepath = os.path.join(self.output_dir, filename)
        
        report_data = self._build_report(session)
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=self.indent, default=str)
        
        return filepath

    def _build_report(self, session: "TestSession") -> dict:
        """Build the complete JSON report structure."""
        return {
            "meta": {
                "session_id": session.session_id,
                "start_time": session.start_time.isoformat(),
                "end_time": session.end_time.isoformat() if session.end_time else None,
                "duration_seconds": (
                    (session.end_time - session.start_time).total_seconds()
                    if session.end_time else None
                ),
                "config": session.config_summary,
                "recording_path": session.recording_path,
            },
            "summary": {
                "pages_tested": len(session.pages_tested),
                "total_findings": session.total_findings,
                "unique_findings": len(session.get_deduplicated_findings()),
                "findings_by_severity": session.findings_by_severity,
                "findings_by_category": session.findings_by_category,
            },
            "pages": [
                {
                    "url": page.url,
                    "title": page.title,
                    "load_time_ms": page.load_time_ms,
                    "interactive_elements": page.interactive_elements,
                    "forms_count": page.forms_count,
                    "links_count": page.links_count,
                    "images_count": page.images_count,
                    "console_errors": page.console_errors,
                    "network_errors": page.network_errors,
                    "findings_count": len(page.findings),
                    "timestamp": page.timestamp.isoformat(),
                }
                for page in session.pages_tested
            ],
            "findings": [finding.to_dict() for finding in session.get_deduplicated_findings()],
        }

    def get_json_string(self, session: "TestSession") -> str:
        """Get report as JSON string without saving to file."""
        report_data = self._build_report(session)
        return json.dumps(report_data, indent=self.indent, default=str)
