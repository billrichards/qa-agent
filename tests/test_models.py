"""Tests for qa_agent/models.py — data models, URL normalisation, deduplication."""

from datetime import datetime

from qa_agent.models import (
    Finding,
    FindingCategory,
    Severity,
    TestSession,
    _normalize_url,
)
from tests.conftest import make_finding, make_page_analysis, make_session

# ---------------------------------------------------------------------------
# _normalize_url
# ---------------------------------------------------------------------------

class TestNormalizeUrl:
    def test_numeric_segment_replaced(self):
        assert _normalize_url("https://example.com/users/42") == "https://example.com/users/{id}"

    def test_uuid_segment_replaced(self):
        url = "https://example.com/items/550e8400-e29b-41d4-a716-446655440000"
        result = _normalize_url(url)
        assert "{id}" in result
        assert "550e8400" not in result

    def test_multiple_numeric_segments(self):
        result = _normalize_url("https://example.com/org/1/user/99")
        assert result == "https://example.com/org/{id}/user/{id}"

    def test_non_numeric_segment_preserved(self):
        result = _normalize_url("https://example.com/about")
        assert result == "https://example.com/about"

    def test_query_string_preserved(self):
        # Query string should not be stripped (only path is normalised)
        result = _normalize_url("https://example.com/items/42?page=1")
        assert "{id}" in result
        # query string still present
        assert "page=1" in result

    def test_no_path(self):
        result = _normalize_url("https://example.com")
        assert result == "https://example.com"

    def test_empty_string_does_not_crash(self):
        # Should return something (not raise)
        result = _normalize_url("")
        assert isinstance(result, str)

    def test_slug_starting_with_digit(self):
        result = _normalize_url("https://example.com/products/123-blue-widget")
        assert "{id}" in result

    def test_preserves_scheme_and_host(self):
        result = _normalize_url("https://sub.example.com/users/7/profile")
        assert result.startswith("https://sub.example.com")


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------

class TestFinding:
    def test_to_dict_contains_required_keys(self):
        f = make_finding()
        d = f.to_dict()
        for key in ("title", "description", "category", "severity", "url", "timestamp"):
            assert key in d

    def test_to_dict_category_is_string(self):
        f = make_finding()
        assert isinstance(f.to_dict()["category"], str)

    def test_to_dict_severity_is_string(self):
        f = make_finding()
        assert isinstance(f.to_dict()["severity"], str)

    def test_screenshot_path_none_by_default(self):
        assert make_finding().to_dict()["screenshot_path"] is None

    def test_screenshot_path_string_when_set(self):
        f = make_finding(screenshot_path="/tmp/shot.png")
        assert f.to_dict()["screenshot_path"] == "/tmp/shot.png"

    def test_affected_urls_empty_by_default(self):
        assert make_finding().to_dict()["affected_urls"] == []


# ---------------------------------------------------------------------------
# TestSession
# ---------------------------------------------------------------------------

class TestTestSession:
    def test_add_page_analysis_increments_total(self):
        session = make_session(findings=[make_finding()])
        assert session.total_findings == 1

    def test_findings_by_severity_updated(self):
        session = make_session(findings=[
            make_finding(severity=Severity.HIGH),
            make_finding(severity=Severity.HIGH),
            make_finding(severity=Severity.LOW),
        ])
        assert session.findings_by_severity["high"] == 2
        assert session.findings_by_severity["low"] == 1

    def test_findings_by_category_updated(self):
        session = make_session(findings=[
            make_finding(category=FindingCategory.ACCESSIBILITY),
            make_finding(category=FindingCategory.ACCESSIBILITY),
            make_finding(category=FindingCategory.FORM_HANDLING),
        ])
        assert session.findings_by_category["accessibility"] == 2
        assert session.findings_by_category["form_handling"] == 1

    def test_get_all_findings_across_pages(self):
        session = TestSession(
            session_id="s1",
            start_time=datetime.now(),
            config_summary={},
        )
        session.add_page_analysis(make_page_analysis(
            url="https://example.com/a", findings=[make_finding()],
        ))
        session.add_page_analysis(make_page_analysis(
            url="https://example.com/b", findings=[make_finding(), make_finding()],
        ))
        assert len(session.get_all_findings()) == 3


class TestDeduplication:
    def _session_with(self, findings: list[Finding]) -> TestSession:
        session = TestSession(session_id="ded1", start_time=datetime.now(), config_summary={})
        page = make_page_analysis(findings=findings)
        session.add_page_analysis(page)
        return session

    def test_same_title_category_on_two_urls_collapses(self):
        f1 = make_finding("Missing alt text", url="https://example.com/users/1")
        f2 = make_finding("Missing alt text", url="https://example.com/users/2")
        session = self._session_with([f1, f2])
        deduped = session.get_deduplicated_findings()
        assert len(deduped) == 1
        assert len(deduped[0].affected_urls) == 2

    def test_different_titles_stay_separate(self):
        f1 = make_finding("Issue A", url="https://example.com/users/1")
        f2 = make_finding("Issue B", url="https://example.com/users/1")
        session = self._session_with([f1, f2])
        assert len(session.get_deduplicated_findings()) == 2

    def test_different_categories_stay_separate(self):
        f1 = make_finding("Same Title", category=FindingCategory.ACCESSIBILITY, url="https://example.com/1")
        f2 = make_finding("Same Title", category=FindingCategory.FORM_HANDLING, url="https://example.com/2")
        session = self._session_with([f1, f2])
        assert len(session.get_deduplicated_findings()) == 2

    def test_empty_findings_returns_empty(self):
        session = self._session_with([])
        assert session.get_deduplicated_findings() == []

    def test_single_finding_unchanged(self):
        f = make_finding(url="https://example.com/page/1")
        session = self._session_with([f])
        deduped = session.get_deduplicated_findings()
        assert len(deduped) == 1
        assert deduped[0].affected_urls == []

    def test_to_dict_includes_findings(self):
        session = make_session(findings=[make_finding()])
        d = session.to_dict()
        assert "findings" in d
        assert isinstance(d["findings"], list)
        assert len(d["findings"]) == 1
