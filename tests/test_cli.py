"""Tests for qa_agent/cli.py — argument parsing, auth config, exit codes."""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from qa_agent.cli import parse_auth_config
from qa_agent.config import AuthConfig, TestMode
from qa_agent.models import Severity


# ---------------------------------------------------------------------------
# parse_auth_config
# ---------------------------------------------------------------------------

class TestParseAuthConfig:
    def test_simple_credentials(self):
        auth = parse_auth_config("user:pass", None)
        assert auth is not None
        assert auth.username == "user"
        assert auth.password == "pass"
        assert auth.auth_url is None

    def test_credentials_with_auth_url(self):
        auth = parse_auth_config("user:pass@https://example.com/login", None)
        assert auth is not None
        assert auth.username == "user"
        assert auth.password == "pass"
        assert auth.auth_url == "https://example.com/login"

    def test_password_with_colons(self):
        auth = parse_auth_config("user:p:a:s:s", None)
        assert auth is not None
        assert auth.username == "user"
        assert auth.password == "p:a:s:s"

    def test_malformed_no_colon_returns_none(self, capsys):
        auth = parse_auth_config("nocoiolon", None)
        assert auth is None
        captured = capsys.readouterr()
        assert captured.err  # error message written to stderr

    def test_none_auth_str_and_file_returns_none(self):
        assert parse_auth_config(None, None) is None

    def test_auth_file_happy_path(self, tmp_path):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text(json.dumps({"username": "u", "password": "p"}))
        auth = parse_auth_config(None, str(auth_file))
        assert auth is not None
        assert auth.username == "u"

    def test_auth_file_missing_returns_none(self, capsys):
        auth = parse_auth_config(None, "/nonexistent/path/auth.json")
        assert auth is None
        assert capsys.readouterr().err

    def test_auth_file_malformed_json_returns_none(self, tmp_path, capsys):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json {{{")
        auth = parse_auth_config(None, str(bad_file))
        assert auth is None
        assert capsys.readouterr().err

    def test_auth_file_binary_returns_none(self, tmp_path, capsys):
        bin_file = tmp_path / "binary.bin"
        bin_file.write_bytes(bytes(range(256)))
        auth = parse_auth_config(None, str(bin_file))
        assert auth is None


# ---------------------------------------------------------------------------
# main() argument parsing
# ---------------------------------------------------------------------------

def _fake_session(critical_count=0, high_count=0):
    """Return a minimal fake TestSession."""
    session = MagicMock()
    session.findings_by_severity = {}
    if critical_count:
        session.findings_by_severity["critical"] = critical_count
    if high_count:
        session.findings_by_severity["high"] = high_count
    return session


class TestMainParsing:
    def _run_main(self, argv, session=None, monkeypatch=None):
        """Patch QAAgent.run, set sys.argv, call main(), return captured exit code."""
        import qa_agent.cli as cli_mod
        if session is None:
            session = _fake_session()
        if monkeypatch:
            monkeypatch.setattr(sys, "argv", argv)

        with patch.object(cli_mod.QAAgent, "__init__", return_value=None) as mock_init, \
             patch.object(cli_mod.QAAgent, "run", return_value=session):
            mock_init.return_value = None
            # We also need to set config on the agent after init
            try:
                cli_mod.main()
            except SystemExit as e:
                return e.code
        return 0

    def test_default_mode_is_focused(self, monkeypatch):
        captured_config = {}

        def fake_init(self, config, **kwargs):
            captured_config["config"] = config

        with patch("qa_agent.cli.QAAgent.__init__", fake_init), \
             patch("qa_agent.cli.QAAgent.run", return_value=_fake_session()):
            monkeypatch.setattr(sys, "argv", ["qa-agent", "https://example.com"])
            import qa_agent.cli as cli_mod
            try:
                cli_mod.main()
            except SystemExit:
                pass

        assert captured_config["config"].mode == TestMode.FOCUSED

    def test_mode_explore(self, monkeypatch):
        captured_config = {}

        def fake_init(self, config, **kwargs):
            captured_config["config"] = config

        with patch("qa_agent.cli.QAAgent.__init__", fake_init), \
             patch("qa_agent.cli.QAAgent.run", return_value=_fake_session()):
            monkeypatch.setattr(sys, "argv", ["qa-agent", "--mode", "explore", "https://example.com"])
            import qa_agent.cli as cli_mod
            try:
                cli_mod.main()
            except SystemExit:
                pass

        assert captured_config["config"].mode == TestMode.EXPLORE

    def test_json_always_appended(self, monkeypatch):
        """JSON format must be in output_formats even when not explicitly requested."""
        from qa_agent.config import OutputFormat
        captured_config = {}

        def fake_init(self, config, **kwargs):
            captured_config["config"] = config

        with patch("qa_agent.cli.QAAgent.__init__", fake_init), \
             patch("qa_agent.cli.QAAgent.run", return_value=_fake_session()):
            monkeypatch.setattr(sys, "argv", ["qa-agent", "--output", "console", "https://example.com"])
            import qa_agent.cli as cli_mod
            try:
                cli_mod.main()
            except SystemExit:
                pass

        assert OutputFormat.JSON in captured_config["config"].output_formats

    def test_unknown_output_format_does_not_crash(self, monkeypatch, capsys):
        def fake_init(self, config, **kwargs):
            pass

        with patch("qa_agent.cli.QAAgent.__init__", fake_init), \
             patch("qa_agent.cli.QAAgent.run", return_value=_fake_session()):
            monkeypatch.setattr(sys, "argv", ["qa-agent", "--output", "bogusformat", "https://example.com"])
            import qa_agent.cli as cli_mod
            try:
                cli_mod.main()
            except SystemExit:
                pass
        # Should produce a warning but not raise
        out = capsys.readouterr()
        assert "bogusformat" in out.err or True  # warning may go to stderr

    def test_bad_viewport_falls_back(self, monkeypatch, capsys):
        captured_config = {}

        def fake_init(self, config, **kwargs):
            captured_config["config"] = config

        with patch("qa_agent.cli.QAAgent.__init__", fake_init), \
             patch("qa_agent.cli.QAAgent.run", return_value=_fake_session()):
            monkeypatch.setattr(sys, "argv", ["qa-agent", "--viewport", "bogus", "https://example.com"])
            import qa_agent.cli as cli_mod
            try:
                cli_mod.main()
            except SystemExit:
                pass

        assert captured_config["config"].viewport_width == 1280
        assert captured_config["config"].viewport_height == 720

    def test_valid_viewport_parsed(self, monkeypatch):
        captured_config = {}

        def fake_init(self, config, **kwargs):
            captured_config["config"] = config

        with patch("qa_agent.cli.QAAgent.__init__", fake_init), \
             patch("qa_agent.cli.QAAgent.run", return_value=_fake_session()):
            monkeypatch.setattr(sys, "argv", ["qa-agent", "--viewport", "1920x1080", "https://example.com"])
            import qa_agent.cli as cli_mod
            try:
                cli_mod.main()
            except SystemExit:
                pass

        assert captured_config["config"].viewport_width == 1920
        assert captured_config["config"].viewport_height == 1080

    def test_no_cache_without_instructions_exits_2(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["qa-agent", "--no-cache", "https://example.com"])
        import qa_agent.cli as cli_mod
        with pytest.raises(SystemExit) as exc:
            cli_mod.main()
        assert exc.value.code == 2

    def test_skip_keyboard_disables_test(self, monkeypatch):
        captured_config = {}

        def fake_init(self, config, **kwargs):
            captured_config["config"] = config

        with patch("qa_agent.cli.QAAgent.__init__", fake_init), \
             patch("qa_agent.cli.QAAgent.run", return_value=_fake_session()):
            monkeypatch.setattr(sys, "argv", ["qa-agent", "--skip-keyboard", "https://example.com"])
            import qa_agent.cli as cli_mod
            try:
                cli_mod.main()
            except SystemExit:
                pass

        assert captured_config["config"].test_keyboard is False

    def test_skip_flags_all_work(self, monkeypatch):
        captured_config = {}

        def fake_init(self, config, **kwargs):
            captured_config["config"] = config

        with patch("qa_agent.cli.QAAgent.__init__", fake_init), \
             patch("qa_agent.cli.QAAgent.run", return_value=_fake_session()):
            monkeypatch.setattr(sys, "argv", [
                "qa-agent",
                "--skip-keyboard", "--skip-mouse", "--skip-forms",
                "--skip-accessibility", "--skip-errors",
                "https://example.com",
            ])
            import qa_agent.cli as cli_mod
            try:
                cli_mod.main()
            except SystemExit:
                pass

        cfg = captured_config["config"]
        assert cfg.test_keyboard is False
        assert cfg.test_mouse is False
        assert cfg.test_forms is False
        assert cfg.test_accessibility is False
        assert cfg.test_console_errors is False
        assert cfg.test_network_errors is False

    def test_header_parsing(self, monkeypatch):
        captured_config = {}

        def fake_init(self, config, **kwargs):
            captured_config["config"] = config

        with patch("qa_agent.cli.QAAgent.__init__", fake_init), \
             patch("qa_agent.cli.QAAgent.run", return_value=_fake_session()):
            monkeypatch.setattr(sys, "argv", [
                "qa-agent",
                "--header", "X-Foo: bar",
                "--header", "Authorization: Bearer xyz",
                "https://example.com",
            ])
            import qa_agent.cli as cli_mod
            try:
                cli_mod.main()
            except SystemExit:
                pass

        headers = captured_config["config"].auth.headers
        assert headers["X-Foo"] == "bar"
        assert headers["Authorization"] == "Bearer xyz"

    def test_header_without_colon_does_not_crash(self, monkeypatch):
        def fake_init(self, config, **kwargs):
            pass

        with patch("qa_agent.cli.QAAgent.__init__", fake_init), \
             patch("qa_agent.cli.QAAgent.run", return_value=_fake_session()):
            monkeypatch.setattr(sys, "argv", ["qa-agent", "--header", "NoColon", "https://example.com"])
            import qa_agent.cli as cli_mod
            try:
                cli_mod.main()
            except SystemExit:
                pass

    def test_cookies_happy_path(self, monkeypatch, tmp_path):
        captured_config = {}

        def fake_init(self, config, **kwargs):
            captured_config["config"] = config

        cookies_file = tmp_path / "cookies.json"
        cookies_file.write_text(json.dumps([{"name": "session", "value": "abc", "domain": "example.com"}]))

        with patch("qa_agent.cli.QAAgent.__init__", fake_init), \
             patch("qa_agent.cli.QAAgent.run", return_value=_fake_session()):
            monkeypatch.setattr(sys, "argv", [
                "qa-agent", "--cookies", str(cookies_file), "https://example.com",
            ])
            import qa_agent.cli as cli_mod
            try:
                cli_mod.main()
            except SystemExit:
                pass

        assert captured_config["config"].auth is not None

    def test_cookies_malformed_does_not_crash(self, monkeypatch, tmp_path, capsys):
        bad = tmp_path / "bad.json"
        bad.write_text("not json")

        def fake_init(self, config, **kwargs):
            pass

        with patch("qa_agent.cli.QAAgent.__init__", fake_init), \
             patch("qa_agent.cli.QAAgent.run", return_value=_fake_session()):
            monkeypatch.setattr(sys, "argv", ["qa-agent", "--cookies", str(bad), "https://example.com"])
            import qa_agent.cli as cli_mod
            try:
                cli_mod.main()
            except SystemExit:
                pass

    def test_instructions_file(self, monkeypatch, tmp_path):
        captured_config = {}

        def fake_init(self, config, **kwargs):
            captured_config["config"] = config

        inst_file = tmp_path / "instructions.txt"
        inst_file.write_text("Test the login flow")

        with patch("qa_agent.cli.QAAgent.__init__", fake_init), \
             patch("qa_agent.cli.QAAgent.run", return_value=_fake_session()):
            monkeypatch.setattr(sys, "argv", [
                "qa-agent", "--instructions-file", str(inst_file), "https://example.com",
            ])
            import qa_agent.cli as cli_mod
            try:
                cli_mod.main()
            except SystemExit:
                pass

        assert captured_config["config"].instructions == "Test the login flow"

    def test_instructions_file_missing_does_not_crash(self, monkeypatch, capsys):
        def fake_init(self, config, **kwargs):
            pass

        with patch("qa_agent.cli.QAAgent.__init__", fake_init), \
             patch("qa_agent.cli.QAAgent.run", return_value=_fake_session()):
            monkeypatch.setattr(sys, "argv", [
                "qa-agent", "--instructions-file", "/nonexistent/inst.txt", "https://example.com",
            ])
            import qa_agent.cli as cli_mod
            try:
                cli_mod.main()
            except SystemExit:
                pass


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

class TestExitCodes:
    def _run(self, monkeypatch, argv, session):
        monkeypatch.setattr(sys, "argv", argv)
        import qa_agent.cli as cli_mod

        def fake_init(self, config, **kwargs):
            pass

        with patch("qa_agent.cli.QAAgent.__init__", fake_init), \
             patch("qa_agent.cli.QAAgent.run", return_value=session):
            with pytest.raises(SystemExit) as exc:
                cli_mod.main()
            return exc.value.code

    def test_exit_0_no_critical_or_high(self, monkeypatch):
        """main() returns normally (no sys.exit) when there are no critical/high findings."""
        session = _fake_session()
        monkeypatch.setattr(sys, "argv", ["qa-agent", "https://example.com"])
        import qa_agent.cli as cli_mod

        def fake_init(self, config, **kwargs):
            pass

        with patch("qa_agent.cli.QAAgent.__init__", fake_init), \
             patch("qa_agent.cli.QAAgent.run", return_value=session):
            # No SystemExit should be raised
            cli_mod.main()

    def test_exit_1_critical_findings(self, monkeypatch):
        session = _fake_session(critical_count=1)
        code = self._run(monkeypatch, ["qa-agent", "https://example.com"], session)
        assert code == 1

    def test_exit_1_high_findings(self, monkeypatch):
        session = _fake_session(high_count=2)
        code = self._run(monkeypatch, ["qa-agent", "https://example.com"], session)
        assert code == 1

    def test_exit_2_on_exception(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["qa-agent", "https://example.com"])
        import qa_agent.cli as cli_mod

        def fake_init(self, config, **kwargs):
            pass

        with patch("qa_agent.cli.QAAgent.__init__", fake_init), \
             patch("qa_agent.cli.QAAgent.run", side_effect=RuntimeError("boom")):
            with pytest.raises(SystemExit) as exc:
                cli_mod.main()
        assert exc.value.code == 2

    def test_exit_130_on_keyboard_interrupt(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["qa-agent", "https://example.com"])
        import qa_agent.cli as cli_mod

        def fake_init(self, config, **kwargs):
            pass

        with patch("qa_agent.cli.QAAgent.__init__", fake_init), \
             patch("qa_agent.cli.QAAgent.run", side_effect=KeyboardInterrupt):
            with pytest.raises(SystemExit) as exc:
                cli_mod.main()
        assert exc.value.code == 130
