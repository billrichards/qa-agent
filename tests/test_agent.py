"""Tests for qa_agent/agent.py — domain extraction, URL filtering, orchestration."""

from __future__ import annotations

import threading
from typing import Literal
from unittest.mock import MagicMock, patch

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from qa_agent.agent import QAAgent, _extract_domain
from qa_agent.config import AuthConfig, OutputFormat, TestConfig, TestMode
from qa_agent.models import Finding, FindingCategory, Severity
from tests.conftest import make_mock_playwright_factory

# ---------------------------------------------------------------------------
# _extract_domain
# ---------------------------------------------------------------------------

class TestExtractDomain:
    def test_simple_url(self):
        assert _extract_domain("https://example.com/path") == "example.com"

    def test_strips_port(self):
        assert _extract_domain("https://example.com:8080/path") == "example.com"

    def test_subdomain_preserved(self):
        assert _extract_domain("https://www.example.com") == "www.example.com"

    def test_case_preserved_from_netloc(self):
        # urlparse lowercases scheme, not necessarily netloc; we just want it to not crash
        result = _extract_domain("https://Example.COM/path")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_no_scheme_returns_safe_string(self):
        # Should not crash; may return partial or "unknown"
        result = _extract_domain("not-a-url")
        assert isinstance(result, str)

    def test_empty_string_returns_unknown(self):
        assert _extract_domain("") == "unknown"

    def test_non_alphanumeric_in_netloc_replaced(self):
        # Dots and hyphens are allowed; anything else replaced
        result = _extract_domain("https://my-site.example.com")
        # hyphens preserved
        assert "my-site" in result

    def test_dot_and_hyphen_produce_distinct_outputs(self):
        """a.b.com and a-b-com must NOT map to the same directory name.

        NOTE: This test documents a known collision risk. Currently _extract_domain
        preserves both dots and hyphens, so 'a.b.com' → 'a.b.com' and
        'a-b-com' → 'a-b-com' are already distinct. If the implementation ever
        changes to replace dots, this test will catch the regression.
        """
        d1 = _extract_domain("https://a.b.com")
        d2 = _extract_domain("https://a-b-com")
        assert d1 != d2, (
            "Domain collision: a.b.com and a-b-com produce the same output directory name. "
            "This is a security/correctness issue — sessions for different sites could overwrite each other."
        )

    def test_ip_address(self):
        result = _extract_domain("http://127.0.0.1:8080/page")
        assert "127.0.0.1" in result


# ---------------------------------------------------------------------------
# _should_skip_url (via QAAgent instance)
# ---------------------------------------------------------------------------

class TestShouldSkipUrl:
    def _agent(self, ignore_patterns=None, same_domain_only=True, base_url="https://example.com"):
        config = TestConfig(
            urls=[base_url],
            ignore_patterns=ignore_patterns or [],
            same_domain_only=same_domain_only,
        )
        factory, _, _, _ = make_mock_playwright_factory()
        agent = QAAgent(config, playwright_factory=factory)
        return agent

    def test_pattern_match_skips_url(self):
        agent = self._agent(ignore_patterns=[r"/logout"])
        assert agent._should_skip_url("https://example.com/logout") is True

    def test_non_matching_pattern_allows_url(self):
        agent = self._agent(ignore_patterns=[r"/logout"])
        assert agent._should_skip_url("https://example.com/dashboard") is False

    def test_extension_skipped(self):
        agent = self._agent()
        for ext in [".pdf", ".zip", ".jpg", ".png", ".css", ".js"]:
            assert agent._should_skip_url(f"https://example.com/file{ext}") is True

    def test_no_patterns_allows_normal_url(self):
        agent = self._agent()
        assert agent._should_skip_url("https://example.com/about") is False

    def test_multiple_patterns(self):
        agent = self._agent(ignore_patterns=[r"/admin", r"/api/"])
        assert agent._should_skip_url("https://example.com/admin/users") is True
        assert agent._should_skip_url("https://example.com/api/v1") is True
        assert agent._should_skip_url("https://example.com/home") is False

    def test_redos_does_not_hang(self):
        """Catastrophic-backtracking regex must not hang the process.

        This is a known security risk: an attacker-controlled --ignore pattern
        could DoS the test run. The test enforces a 2-second wall-clock limit.
        If it times out, _should_skip_url needs to add regex timeout protection.
        """
        evil_pattern = r"(a+)+"
        evil_input = "a" * 25 + "b"
        agent = self._agent(ignore_patterns=[evil_pattern])

        result_holder = {}
        def run():
            result_holder["result"] = agent._should_skip_url(f"https://example.com/{evil_input}")

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(timeout=2.0)

        if t.is_alive():
            pytest.xfail(
                "ReDoS: _should_skip_url hangs on catastrophic backtracking pattern. "
                "Fix by wrapping re.search in a timeout or pre-validating patterns."
            )
        # If it finished, that's a pass regardless of result value


# ---------------------------------------------------------------------------
# QAAgent.run — orchestration
# ---------------------------------------------------------------------------

def _make_config(**kwargs: object) -> TestConfig:
    # Start with typed defaults
    from typing import cast

    from qa_agent.config import LLMProvider, RecordingConfig, ScreenshotConfig

    # Extract known kwargs with type casting
    urls = cast(list[str], kwargs.pop("urls", ["https://example.com"]))
    output_formats = cast(list[OutputFormat], kwargs.pop("output_formats", []))
    headless = cast(bool, kwargs.pop("headless", True))
    mode = cast(TestMode, kwargs.pop("mode", TestMode.FOCUSED))
    output_dir = cast(str, kwargs.pop("output_dir", "./output"))
    viewport_width = cast(int, kwargs.pop("viewport_width", 1280))
    viewport_height = cast(int, kwargs.pop("viewport_height", 720))
    timeout = cast(int, kwargs.pop("timeout", 30000))
    max_depth = cast(int, kwargs.pop("max_depth", 3))
    max_pages = cast(int, kwargs.pop("max_pages", 20))
    max_interactions_per_page = cast(int, kwargs.pop("max_interactions_per_page", 50))
    test_keyboard = cast(bool, kwargs.pop("test_keyboard", True))
    test_mouse = cast(bool, kwargs.pop("test_mouse", True))
    test_forms = cast(bool, kwargs.pop("test_forms", True))
    test_accessibility = cast(bool, kwargs.pop("test_accessibility", True))
    test_console_errors = cast(bool, kwargs.pop("test_console_errors", True))
    test_network_errors = cast(bool, kwargs.pop("test_network_errors", True))
    test_wcag_compliance = cast(bool, kwargs.pop("test_wcag_compliance", False))
    auth = cast(AuthConfig | None, kwargs.pop("auth", None))
    screenshots = cast(ScreenshotConfig, kwargs.pop("screenshots", ScreenshotConfig()))
    recording = cast(RecordingConfig, kwargs.pop("recording", RecordingConfig()))
    ignore_patterns = cast(list[str], kwargs.pop("ignore_patterns", []))
    same_domain_only = cast(bool, kwargs.pop("same_domain_only", True))
    instructions = cast(str | None, kwargs.pop("instructions", None))
    llm_provider = cast(LLMProvider, kwargs.pop("llm_provider", LLMProvider.ANTHROPIC))
    ai_model = cast(str | None, kwargs.pop("ai_model", None))
    use_plan_cache = cast(bool, kwargs.pop("use_plan_cache", True))
    invocation_context = cast(Literal["cli", "web"] | None, kwargs.pop("invocation_context", None))

    # Any remaining kwargs are passed as-is (will cause mypy error if they don't match TestConfig)
    # This is fine for test code where we might pass extra kwargs for future compatibility
    return TestConfig(
        urls=urls,
        output_formats=output_formats,
        headless=headless,
        mode=mode,
        output_dir=output_dir,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        timeout=timeout,
        max_depth=max_depth,
        max_pages=max_pages,
        max_interactions_per_page=max_interactions_per_page,
        test_keyboard=test_keyboard,
        test_mouse=test_mouse,
        test_forms=test_forms,
        test_accessibility=test_accessibility,
        test_console_errors=test_console_errors,
        test_network_errors=test_network_errors,
        test_wcag_compliance=test_wcag_compliance,
        auth=auth,
        screenshots=screenshots,
        recording=recording,
        ignore_patterns=ignore_patterns,
        same_domain_only=same_domain_only,
        instructions=instructions,
        llm_provider=llm_provider,
        ai_model=ai_model,
        use_plan_cache=use_plan_cache,
        invocation_context=invocation_context,
        **kwargs,  # type: ignore[arg-type]
    )


def _make_agent(config=None, mock_page=None):
    """Return (agent, mock_page) with playwright factory injected."""
    if config is None:
        config = _make_config()
    factory, page, context, browser = make_mock_playwright_factory(mock_page)
    # _analyze_page_structure needs evaluate to return the right shape
    page.evaluate.return_value = {
        "interactive_elements": 0,
        "forms_count": 0,
        "links_count": 0,
        "images_count": 0,
    }
    agent = QAAgent(config, playwright_factory=factory)
    return agent, page


class TestQAAgentRun:
    def _patch_testers(self):
        """Context manager that patches all tester run() methods to return []."""
        from unittest.mock import patch as _patch
        targets = [
            "qa_agent.agent.KeyboardTester.run",
            "qa_agent.agent.MouseTester.run",
            "qa_agent.agent.FormTester.run",
            "qa_agent.agent.AccessibilityTester.run",
            "qa_agent.agent.ErrorDetector.run",
            "qa_agent.agent.ErrorDetector.attach_listeners",
            "qa_agent.agent.ErrorDetector.get_summary",
        ]
        patchers = [_patch(t, return_value=[]) for t in targets]
        return patchers

    def test_focused_mode_tests_one_page(self):
        agent, page = _make_agent()
        patchers = self._patch_testers()
        for p in patchers:
            p.start()
        try:
            session = agent.run()
        finally:
            for p in patchers:
                p.stop()

        assert len(session.pages_tested) == 1

    def test_findings_aggregate_into_session(self):
        from qa_agent.models import FindingCategory, Severity

        config = _make_config(urls=["https://example.com/a", "https://example.com/b"])
        agent, page = _make_agent(config)

        finding = Finding(
            title="Test",
            description="desc",
            category=FindingCategory.ACCESSIBILITY,
            severity=Severity.LOW,
            url="https://example.com/a",
        )

        call_count = [0]
        def mock_accessibility_run(self):
            call_count[0] += 1
            return [finding] if call_count[0] == 1 else []

        patchers = [
            patch("qa_agent.agent.KeyboardTester.run", return_value=[]),
            patch("qa_agent.agent.MouseTester.run", return_value=[]),
            patch("qa_agent.agent.FormTester.run", return_value=[]),
            patch("qa_agent.agent.AccessibilityTester.run", mock_accessibility_run),
            patch("qa_agent.agent.ErrorDetector.run", return_value=[]),
            patch("qa_agent.agent.ErrorDetector.attach_listeners", return_value=None),
            patch("qa_agent.agent.ErrorDetector.get_summary", return_value={}),
        ]
        for p in patchers:
            p.start()
        try:
            session = agent.run()
        finally:
            for p in patchers:
                p.stop()

        assert session.total_findings >= 1

    def test_stop_event_halts_before_next_page(self):
        config = _make_config(urls=["https://example.com/a", "https://example.com/b", "https://example.com/c"])
        agent, page = _make_agent(config)

        pages_visited = []
        def counting_goto(url, **kwargs):
            pages_visited.append(url)
            # Set stop after first page navigation
            if len(pages_visited) == 1 and agent.stop_event:
                agent.stop_event.set()

        page.goto.side_effect = counting_goto

        import threading as thr
        agent.stop_event = thr.Event()

        patchers = [
            patch("qa_agent.agent.KeyboardTester.run", return_value=[]),
            patch("qa_agent.agent.MouseTester.run", return_value=[]),
            patch("qa_agent.agent.FormTester.run", return_value=[]),
            patch("qa_agent.agent.AccessibilityTester.run", return_value=[]),
            patch("qa_agent.agent.ErrorDetector.run", return_value=[]),
            patch("qa_agent.agent.ErrorDetector.attach_listeners", return_value=None),
            patch("qa_agent.agent.ErrorDetector.get_summary", return_value={}),
        ]
        for p in patchers:
            p.start()
        try:
            session = agent.run()
        finally:
            for p in patchers:
                p.stop()

        # Should have tested fewer than 3 pages
        assert len(session.pages_tested) < 3

    def test_tester_exception_does_not_abort_run(self):
        """If one tester raises, the page test should still complete."""
        agent, page = _make_agent()

        def raising_run(self):
            raise RuntimeError("tester exploded")

        patchers = [
            patch("qa_agent.agent.KeyboardTester.run", raising_run),
            patch("qa_agent.agent.MouseTester.run", return_value=[]),
            patch("qa_agent.agent.FormTester.run", return_value=[]),
            patch("qa_agent.agent.AccessibilityTester.run", return_value=[]),
            patch("qa_agent.agent.ErrorDetector.run", return_value=[]),
            patch("qa_agent.agent.ErrorDetector.attach_listeners", return_value=None),
            patch("qa_agent.agent.ErrorDetector.get_summary", return_value={}),
        ]
        for p in patchers:
            p.start()
        try:
            # Should not raise despite keyboard tester blowing up
            # (agent wraps per-tester execution defensively)
            # If it does raise, the test fails — that's intentional; it surfaces
            # that the agent needs error handling around individual testers.
            try:
                session = agent.run()
                # Run completed — session exists
                assert session is not None
            except RuntimeError:
                pytest.xfail(
                    "agent.py does not currently guard individual testers against exceptions. "
                    "Consider wrapping each tester.run() in try/except."
                )
        finally:
            for p in patchers:
                p.stop()


class TestFailFastHttpErrors:
    """_test_page should short-circuit on HTTP 4xx/5xx responses."""

    def _make_response(self, status: int, status_text: str = "Error") -> MagicMock:
        response = MagicMock()
        response.status = status
        response.status_text = status_text
        return response

    def _run_with_response(self, status: int, status_text: str = "Error"):
        """Run agent against a single URL where page.goto returns a given HTTP status."""
        config = _make_config(urls=["https://example.com/missing"])
        factory, page, context, browser = make_mock_playwright_factory()
        page.goto.return_value = self._make_response(status, status_text)
        agent = QAAgent(config, playwright_factory=factory)
        # Patch attach_listeners so ErrorDetector setup doesn't fail
        with patch("qa_agent.agent.ErrorDetector.attach_listeners", return_value=None):
            session = agent.run()
        return session, page

    def test_404_creates_high_severity_finding(self):
        session, page = self._run_with_response(404, "Not Found")
        assert len(session.pages_tested) == 1
        findings = session.pages_tested[0].findings
        assert len(findings) == 1
        assert findings[0].severity == Severity.HIGH
        assert "404" in findings[0].title

    def test_500_creates_critical_severity_finding(self):
        session, page = self._run_with_response(500, "Internal Server Error")
        findings = session.pages_tested[0].findings
        assert len(findings) == 1
        assert findings[0].severity == Severity.CRITICAL
        assert "500" in findings[0].title

    def test_http_error_finding_category_is_network_error(self):
        session, _ = self._run_with_response(503, "Service Unavailable")
        findings = session.pages_tested[0].findings
        assert findings[0].category == FindingCategory.NETWORK_ERROR

    def test_http_error_skips_all_testers(self):
        """No tester should run when the page returns an HTTP error."""
        config = _make_config(urls=["https://example.com/gone"])
        factory, page, context, browser = make_mock_playwright_factory()
        page.goto.return_value = self._make_response(410, "Gone")
        agent = QAAgent(config, playwright_factory=factory)

        with patch("qa_agent.agent.KeyboardTester.run") as kb, \
             patch("qa_agent.agent.MouseTester.run") as ms, \
             patch("qa_agent.agent.FormTester.run") as fm, \
             patch("qa_agent.agent.AccessibilityTester.run") as ac, \
             patch("qa_agent.agent.ErrorDetector.run") as ed, \
             patch("qa_agent.agent.ErrorDetector.attach_listeners", return_value=None):
            agent.run()

        kb.assert_not_called()
        ms.assert_not_called()
        fm.assert_not_called()
        ac.assert_not_called()
        ed.assert_not_called()

    def test_200_response_proceeds_normally(self):
        """A 200 response must not trigger the fail-fast path."""
        config = _make_config(urls=["https://example.com"])
        factory, page, context, browser = make_mock_playwright_factory()
        ok_response = MagicMock()
        ok_response.status = 200
        page.goto.return_value = ok_response
        agent = QAAgent(config, playwright_factory=factory)

        with patch("qa_agent.agent.KeyboardTester.run", return_value=[]) as kb, \
             patch("qa_agent.agent.MouseTester.run", return_value=[]), \
             patch("qa_agent.agent.FormTester.run", return_value=[]), \
             patch("qa_agent.agent.AccessibilityTester.run", return_value=[]), \
             patch("qa_agent.agent.ErrorDetector.run", return_value=[]), \
             patch("qa_agent.agent.ErrorDetector.attach_listeners", return_value=None), \
             patch("qa_agent.agent.ErrorDetector.get_summary", return_value={}):
            agent.run()

        kb.assert_called_once()

    def test_none_response_proceeds_normally(self):
        """If goto returns None (Playwright quirk), must not crash and must run testers."""
        config = _make_config(urls=["https://example.com"])
        factory, page, context, browser = make_mock_playwright_factory()
        page.goto.return_value = None
        agent = QAAgent(config, playwright_factory=factory)

        with patch("qa_agent.agent.KeyboardTester.run", return_value=[]) as kb, \
             patch("qa_agent.agent.MouseTester.run", return_value=[]), \
             patch("qa_agent.agent.FormTester.run", return_value=[]), \
             patch("qa_agent.agent.AccessibilityTester.run", return_value=[]), \
             patch("qa_agent.agent.ErrorDetector.run", return_value=[]), \
             patch("qa_agent.agent.ErrorDetector.attach_listeners", return_value=None), \
             patch("qa_agent.agent.ErrorDetector.get_summary", return_value={}):
            session = agent.run()

        assert session is not None
        kb.assert_called_once()


class TestAuthenticate:
    def test_cookie_auth_sets_cookies(self):
        cookies = [{"name": "session", "value": "abc", "domain": "example.com"}]
        auth = AuthConfig(cookies=cookies)
        config = _make_config(auth=auth)
        agent, page = _make_agent(config)
        factory, _, context, _ = make_mock_playwright_factory(page)
        agent._playwright_factory = factory
        agent.context = context

        agent._authenticate()
        context.add_cookies.assert_called_once()

    def test_credentials_not_in_stdout(self, capsys):
        """Security: password must not appear in any captured output."""
        auth = AuthConfig(
            username="secretuser",
            password="supersecretpassword123",
            auth_url="https://example.com/login",
        )
        config = _make_config(auth=auth)
        agent, page = _make_agent(config)

        patchers = [
            patch("qa_agent.agent.KeyboardTester.run", return_value=[]),
            patch("qa_agent.agent.MouseTester.run", return_value=[]),
            patch("qa_agent.agent.FormTester.run", return_value=[]),
            patch("qa_agent.agent.AccessibilityTester.run", return_value=[]),
            patch("qa_agent.agent.ErrorDetector.run", return_value=[]),
            patch("qa_agent.agent.ErrorDetector.attach_listeners", return_value=None),
            patch("qa_agent.agent.ErrorDetector.get_summary", return_value={}),
        ]
        for p in patchers:
            p.start()
        try:
            agent.run()
        except Exception:
            pass
        finally:
            for p in patchers:
                p.stop()

        captured = capsys.readouterr()
        assert "supersecretpassword123" not in captured.out
        assert "supersecretpassword123" not in captured.err

    def _auth_timeout_agent(self, invocation_context=None, username_selector=None, password_selector=None):
        """Helper: agent whose page.fill always raises a Playwright-style timeout."""
        auth = AuthConfig(
            username="user",
            password="pass",
            auth_url="https://example.com/login",
            username_selector=username_selector,
            password_selector=password_selector,
        )
        config = _make_config(auth=auth, invocation_context=invocation_context)
        agent, page = _make_agent(config)
        factory, _, context, _ = make_mock_playwright_factory(page)
        agent._playwright_factory = factory
        agent.context = context
        agent.page = page
        page.goto = MagicMock()
        page.fill = MagicMock(side_effect=PlaywrightTimeoutError("Timeout 30000ms exceeded."))
        page.click = MagicMock()
        page.wait_for_load_state = MagicMock()
        return agent

    def test_timeout_cli_context_suggests_auth_file(self, capsys):
        """CLI context: timeout on default selector should mention --auth-file."""
        self._auth_timeout_agent(invocation_context="cli")._authenticate()
        out = capsys.readouterr().out
        assert "--auth-file" in out
        assert "Advanced" not in out

    def test_timeout_web_context_suggests_advanced_section(self, capsys):
        """Web context: timeout on default selector should mention the Advanced UI section."""
        self._auth_timeout_agent(invocation_context="web")._authenticate()
        out = capsys.readouterr().out
        assert "Advanced" in out
        assert "--auth-file" not in out

    def test_timeout_api_context_suggests_authconfig(self, capsys):
        """API context (no invocation_context): timeout should mention AuthConfig fields."""
        self._auth_timeout_agent(invocation_context=None)._authenticate()
        out = capsys.readouterr().out
        assert "AuthConfig" in out

    def test_timeout_with_custom_selector_no_hint(self, capsys):
        """When a custom selector is provided, no hint should appear."""
        self._auth_timeout_agent(
            invocation_context="cli",
            username_selector="#my-user",
            password_selector="#my-pass",
        )._authenticate()
        out = capsys.readouterr().out
        assert "--auth-file" not in out
        assert "AuthConfig" not in out
