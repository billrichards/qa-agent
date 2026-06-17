"""Tests for qa_agent/summarizer.py and summary integration."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from qa_agent.models import (
    RootCauseCluster,
    SummaryResult,
    TestSession,
)
from qa_agent.summarizer import _parse_summary, _serialize_session, generate_summary
from tests.conftest import make_finding, make_session, make_session_with_findings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_summary(**kwargs) -> SummaryResult:
    defaults: dict = {
        "executive_summary": "Two critical accessibility issues require immediate attention.",
        "priority_recommendations": ["Fix ARIA labels", "Add focus indicators"],
        "root_cause_clusters": [
            RootCauseCluster(
                label="Missing ARIA labels",
                finding_titles=["No alt text on logo"],
                root_cause="Icon-only buttons lack accessible names",
                suggested_fix="Add aria-label to all icon buttons",
            )
        ],
        "false_positive_candidates": ["Console error on third-party script"],
    }
    defaults.update(kwargs)
    return SummaryResult(**defaults)  # type: ignore[arg-type]


_VALID_LLM_RESPONSE = json.dumps({
    "executive_summary": "Three issues found, one critical.",
    "priority_recommendations": ["Fix focus trap", "Add ARIA labels"],
    "root_cause_clusters": [
        {
            "label": "Focus management",
            "finding_titles": ["Keyboard trap in modal"],
            "root_cause": "Modal does not implement focus trap correctly",
            "suggested_fix": "Use a focus trap library or manually manage tabIndex",
        }
    ],
    "false_positive_candidates": ["Network error on beacon endpoint"],
})


# ---------------------------------------------------------------------------
# _serialize_session
# ---------------------------------------------------------------------------

class TestSerializeSession:
    def test_produces_valid_json(self):
        session = make_session_with_findings()
        payload = _serialize_session(session)
        data = json.loads(payload)
        assert "findings" in data
        assert "pages_tested" in data
        assert "total_findings" in data

    def test_finding_fields_present(self):
        session = make_session_with_findings()
        data = json.loads(_serialize_session(session))
        finding = data["findings"][0]
        assert "title" in finding
        assert "severity" in finding
        assert "category" in finding
        assert "description" in finding

    def test_duration_computed(self):
        session = make_session_with_findings()
        data = json.loads(_serialize_session(session))
        assert data["duration_seconds"] == pytest.approx(300.0)

    def test_no_end_time_produces_none_duration(self):
        session = TestSession(
            session_id="x",
            start_time=datetime(2024, 1, 1),
            config_summary={"urls": []},
        )
        data = json.loads(_serialize_session(session))
        assert data["duration_seconds"] is None

    def test_empty_findings_list(self):
        session = make_session()
        data = json.loads(_serialize_session(session))
        assert data["findings"] == []

    def test_uses_deduplicated_findings(self):
        """Duplicates across pages should be collapsed before sending to LLM."""
        f1 = make_finding(title="Focus issue", url="https://example.com/a")
        f2 = make_finding(title="Focus issue", url="https://example.com/b")
        from tests.conftest import make_page_analysis
        session = TestSession(
            session_id="dup",
            start_time=datetime(2024, 1, 1),
            config_summary={"urls": []},
        )
        session.add_page_analysis(make_page_analysis(findings=[f1]))
        session.add_page_analysis(make_page_analysis(url="https://example.com/b", findings=[f2]))
        data = json.loads(_serialize_session(session))
        assert data["unique_findings"] == 1
        assert len(data["findings"]) == 1


# ---------------------------------------------------------------------------
# _parse_summary
# ---------------------------------------------------------------------------

class TestParseSummary:
    def test_parses_valid_response(self):
        result = _parse_summary(_VALID_LLM_RESPONSE)
        assert isinstance(result, SummaryResult)
        assert result.executive_summary == "Three issues found, one critical."
        assert result.priority_recommendations == ["Fix focus trap", "Add ARIA labels"]
        assert len(result.root_cause_clusters) == 1
        cluster = result.root_cause_clusters[0]
        assert cluster.label == "Focus management"
        assert cluster.finding_titles == ["Keyboard trap in modal"]
        assert result.false_positive_candidates == ["Network error on beacon endpoint"]

    def test_strips_markdown_fences(self):
        wrapped = f"```json\n{_VALID_LLM_RESPONSE}\n```"
        result = _parse_summary(wrapped)
        assert result.executive_summary == "Three issues found, one critical."

    def test_strips_markdown_fences_no_language(self):
        wrapped = f"```\n{_VALID_LLM_RESPONSE}\n```"
        result = _parse_summary(wrapped)
        assert result.executive_summary == "Three issues found, one critical."

    def test_empty_arrays_allowed(self):
        payload = json.dumps({
            "executive_summary": "All good.",
            "priority_recommendations": [],
            "root_cause_clusters": [],
            "false_positive_candidates": [],
        })
        result = _parse_summary(payload)
        assert result.priority_recommendations == []
        assert result.root_cause_clusters == []

    def test_missing_optional_fields_default_to_empty(self):
        payload = json.dumps({"executive_summary": "Brief."})
        result = _parse_summary(payload)
        assert result.priority_recommendations == []
        assert result.root_cause_clusters == []
        assert result.false_positive_candidates == []

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_summary("not json at all")


# ---------------------------------------------------------------------------
# generate_summary() — with mocked LLM client
# ---------------------------------------------------------------------------

class TestGenerateSummaryFunction:
    def _mock_client(self, response_text: str):
        from qa_agent.llm_client import LLMProvider, LLMResponse
        client = MagicMock()
        client.complete.return_value = LLMResponse(
            text=response_text,
            provider=LLMProvider.ANTHROPIC,
            model="claude-sonnet-4-6",
        )
        return client

    def test_returns_summary_result_on_success(self):
        session = make_session_with_findings()
        client = self._mock_client(_VALID_LLM_RESPONSE)
        with patch("qa_agent.summarizer.create_llm_client", return_value=client):
            result = generate_summary(session)
        assert isinstance(result, SummaryResult)
        assert result.executive_summary == "Three issues found, one critical."

    def test_returns_none_on_empty_session(self):
        session = TestSession(
            session_id="empty",
            start_time=datetime(2024, 1, 1),
            config_summary={},
        )
        result = generate_summary(session)
        assert result is None

    def test_returns_none_on_no_findings(self):
        session = make_session()  # session with page but no findings
        result = generate_summary(session)
        assert result is None

    def test_returns_none_on_llm_error(self):
        from qa_agent.llm_client import LLMError
        session = make_session_with_findings()
        with patch("qa_agent.summarizer.create_llm_client") as mock_factory:
            mock_factory.return_value.complete.side_effect = LLMError("API error", status_code=500)
            result = generate_summary(session)
        assert result is None

    def test_returns_none_on_json_parse_error(self):
        session = make_session_with_findings()
        client = self._mock_client("not valid json {{{")
        with patch("qa_agent.summarizer.create_llm_client", return_value=client):
            result = generate_summary(session)
        assert result is None

    def test_passes_provider_and_model_to_client_factory(self):
        from qa_agent.llm_client import LLMProvider
        session = make_session_with_findings()
        client = self._mock_client(_VALID_LLM_RESPONSE)
        with patch("qa_agent.summarizer.create_llm_client", return_value=client) as mock_factory:
            generate_summary(session, provider=LLMProvider.OPENAI, model="gpt-4o")
        mock_factory.assert_called_once_with(
            provider=LLMProvider.OPENAI,
            model="gpt-4o",
            api_key=None,
        )

    def test_passes_api_key_to_client_factory(self):
        from qa_agent.llm_client import LLMProvider
        session = make_session_with_findings()
        client = self._mock_client(_VALID_LLM_RESPONSE)
        with patch("qa_agent.summarizer.create_llm_client", return_value=client) as mock_factory:
            generate_summary(session, api_key="sk-test")
        mock_factory.assert_called_once_with(
            provider=LLMProvider.ANTHROPIC,
            model=None,
            api_key="sk-test",
        )


# ---------------------------------------------------------------------------
# SummaryResult model
# ---------------------------------------------------------------------------

class TestSummaryResultModel:
    def test_to_dict_structure(self):
        summary = _make_summary()
        d = summary.to_dict()
        assert "executive_summary" in d
        assert "priority_recommendations" in d
        assert "root_cause_clusters" in d
        assert "false_positive_candidates" in d

    def test_to_dict_cluster_fields(self):
        summary = _make_summary()
        cluster = summary.to_dict()["root_cause_clusters"][0]
        assert cluster["label"] == "Missing ARIA labels"
        assert "finding_titles" in cluster
        assert "root_cause" in cluster
        assert "suggested_fix" in cluster

    def test_session_summary_field_defaults_to_none(self):
        session = make_session()
        assert session.summary is None

    def test_session_to_dict_includes_summary_none(self):
        session = make_session()
        d = session.to_dict()
        assert d["summary"] is None

    def test_session_to_dict_includes_summary_when_set(self):
        session = make_session_with_findings()
        session.summary = _make_summary()
        d = session.to_dict()
        assert d["summary"] is not None
        assert d["summary"]["executive_summary"].startswith("Two critical")


# ---------------------------------------------------------------------------
# Reporter integration — Markdown
# ---------------------------------------------------------------------------

class TestMarkdownSummarySection:
    def _report_content(self, session: TestSession, tmp_path) -> str:
        from qa_agent.reporters.markdown import MarkdownReporter
        reporter = MarkdownReporter(str(tmp_path))
        filepath = reporter.generate(session)
        return open(filepath).read()

    def test_summary_section_absent_when_none(self, tmp_path):
        session = make_session_with_findings()
        content = self._report_content(session, tmp_path)
        assert "## AI Analysis" not in content

    def test_summary_section_present_when_set(self, tmp_path):
        session = make_session_with_findings()
        session.summary = _make_summary()
        content = self._report_content(session, tmp_path)
        assert "## AI Analysis" in content

    def test_executive_summary_in_report(self, tmp_path):
        session = make_session_with_findings()
        session.summary = _make_summary()
        content = self._report_content(session, tmp_path)
        assert "Two critical accessibility issues" in content

    def test_priority_recommendations_in_report(self, tmp_path):
        session = make_session_with_findings()
        session.summary = _make_summary()
        content = self._report_content(session, tmp_path)
        assert "Fix ARIA labels" in content

    def test_root_cause_cluster_in_report(self, tmp_path):
        session = make_session_with_findings()
        session.summary = _make_summary()
        content = self._report_content(session, tmp_path)
        assert "Missing ARIA labels" in content
        assert "Icon-only buttons" in content

    def test_false_positive_candidates_in_report(self, tmp_path):
        session = make_session_with_findings()
        session.summary = _make_summary()
        content = self._report_content(session, tmp_path)
        assert "Possible False Positives" in content
        assert "Console error on third-party script" in content

    def test_no_false_positive_section_when_empty(self, tmp_path):
        session = make_session_with_findings()
        session.summary = _make_summary(false_positive_candidates=[])
        content = self._report_content(session, tmp_path)
        assert "Possible False Positives" not in content

    def test_no_cluster_section_when_empty(self, tmp_path):
        session = make_session_with_findings()
        session.summary = _make_summary(root_cause_clusters=[])
        content = self._report_content(session, tmp_path)
        assert "Root Cause Clusters" not in content


# ---------------------------------------------------------------------------
# Reporter integration — JSON
# ---------------------------------------------------------------------------

class TestJSONSummarySection:
    def _report_data(self, session: TestSession, tmp_path) -> dict[str, Any]:
        from qa_agent.reporters.json_reporter import JSONReporter
        reporter = JSONReporter(str(tmp_path))
        filepath = reporter.generate(session)
        return cast(dict[str, Any], json.loads(open(filepath).read()))

    def test_summary_null_when_none(self, tmp_path):
        session = make_session_with_findings()
        data = self._report_data(session, tmp_path)
        assert data["ai_summary"] is None

    def test_summary_populated_when_set(self, tmp_path):
        session = make_session_with_findings()
        session.summary = _make_summary()
        data = self._report_data(session, tmp_path)
        assert data["ai_summary"] is not None
        assert data["ai_summary"]["executive_summary"] == "Two critical accessibility issues require immediate attention."

    def test_summary_clusters_serialised(self, tmp_path):
        session = make_session_with_findings()
        session.summary = _make_summary()
        data = self._report_data(session, tmp_path)
        clusters = data["ai_summary"]["root_cause_clusters"]
        assert len(clusters) == 1
        assert clusters[0]["label"] == "Missing ARIA labels"
