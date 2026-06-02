"""Tests for qa_agent/playwright_utils.py — chromium installation logic."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest

from qa_agent.playwright_utils import ensure_chromium_installed


class TestEnsureChromiumInstalled:
    """Tests for automatic Chromium installation."""

    def test_chromium_already_installed(self):
        """When chromium is installed, should not attempt to install."""
        mock_browser = MagicMock()

        with patch("qa_agent.playwright_utils.sync_playwright") as mock_pw:
            mock_p = MagicMock()
            mock_p.chromium.launch.return_value = mock_browser
            mock_pw.return_value.__enter__.return_value = mock_p

            # Should not raise or print anything
            ensure_chromium_installed()

            # Should have tried to launch chromium
            mock_p.chromium.launch.assert_called_once_with(headless=True)
            # Should have closed the browser
            mock_browser.close.assert_called_once()

    def test_chromium_missing_install_succeeds(self, capsys):
        """When chromium is missing, should install successfully."""
        # First call raises "executable not found", second call succeeds
        mock_browser = MagicMock()
        call_count = {"count": 0}

        def launch_side_effect(*args, **kwargs):
            call_count["count"] += 1
            if call_count["count"] == 1:
                raise Exception("Executable doesn't exist at /path/to/chromium")
            return mock_browser

        with patch("qa_agent.playwright_utils.sync_playwright") as mock_pw, \
             patch("qa_agent.playwright_utils.subprocess.run") as mock_run:

            mock_p = MagicMock()
            mock_p.chromium.launch.side_effect = launch_side_effect
            mock_pw.return_value.__enter__.return_value = mock_p
            mock_run.return_value = Mock(returncode=0)

            ensure_chromium_installed()

            # Should have called subprocess to install
            mock_run.assert_called_once_with(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True,
                capture_output=True,
                text=True,
            )

            # Should show installation message
            captured = capsys.readouterr()
            assert "Installing Chromium" in captured.err
            assert "successfully" in captured.err

    def test_chromium_missing_permission_denied(self, capsys):
        """When installation fails due to permissions, should show helpful message."""
        with patch("qa_agent.playwright_utils.sync_playwright") as mock_pw, \
             patch("qa_agent.playwright_utils.subprocess.run") as mock_run:

            mock_p = MagicMock()
            mock_p.chromium.launch.side_effect = Exception("Executable not found")
            mock_pw.return_value.__enter__.return_value = mock_p

            # Simulate permission error
            error = subprocess.CalledProcessError(1, "playwright")
            error.stderr = "Permission denied writing to /usr/local/bin"
            mock_run.side_effect = error

            with pytest.raises(SystemExit) as exc:
                ensure_chromium_installed()

            assert exc.value.code == 2

            captured = capsys.readouterr()
            assert "Permission denied" in captured.err
            assert "PLAYWRIGHT_BROWSERS_PATH" in captured.err

    def test_chromium_missing_install_fails_other_error(self, capsys):
        """When installation fails for other reasons, should show error."""
        with patch("qa_agent.playwright_utils.sync_playwright") as mock_pw, \
             patch("qa_agent.playwright_utils.subprocess.run") as mock_run:

            mock_p = MagicMock()
            mock_p.chromium.launch.side_effect = Exception("Browser executable not found")
            mock_pw.return_value.__enter__.return_value = mock_p

            # Simulate generic error
            error = subprocess.CalledProcessError(1, "playwright")
            error.stderr = "Network timeout downloading chromium"
            mock_run.side_effect = error

            with pytest.raises(SystemExit) as exc:
                ensure_chromium_installed()

            assert exc.value.code == 2

            captured = capsys.readouterr()
            assert "Failed to install Chromium" in captured.err
            assert "Network timeout" in captured.err

    def test_other_exceptions_are_reraised(self):
        """Exceptions that aren't 'browser not found' should be re-raised."""
        with patch("qa_agent.playwright_utils.sync_playwright") as mock_pw:
            mock_p = MagicMock()
            # Simulate an unrelated error (no "executable" or "not found" in message)
            mock_p.chromium.launch.side_effect = RuntimeError("Network error")
            mock_pw.return_value.__enter__.return_value = mock_p

            with pytest.raises(RuntimeError, match="Network error"):
                ensure_chromium_installed()

    def test_import_error_triggers_installation(self, capsys):
        """When playwright itself has issues, should attempt installation."""
        with patch("qa_agent.playwright_utils.sync_playwright") as mock_pw, \
             patch("qa_agent.playwright_utils.subprocess.run") as mock_run:

            # First call raises import-related error, second succeeds
            mock_browser = MagicMock()
            call_count = {"count": 0}

            def context_side_effect():
                call_count["count"] += 1
                if call_count["count"] == 1:
                    raise ImportError("Browser executable not found")

                mock_p = MagicMock()
                mock_p.chromium.launch.return_value = mock_browser
                return mock_p

            mock_pw.return_value.__enter__.side_effect = context_side_effect
            mock_run.return_value = Mock(returncode=0)

            ensure_chromium_installed()

            # Should have attempted installation
            mock_run.assert_called_once()
            captured = capsys.readouterr()
            assert "Installing Chromium" in captured.err
