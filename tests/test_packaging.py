"""Packaging validation, web-UI asset inclusion, CLI smoke, and public-API tests.

These tests do not require a browser or an Anthropic API key.  The build-level
tests (``TestPackagingBuild``) invoke ``python -m build`` as a subprocess and
may take ~20 s on first run; subsequent runs reuse the ``tmp_path_factory``
fixture.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Helper — build artifacts (cached per test session via class-scoped fixture)
# ---------------------------------------------------------------------------

def _build_dist(kind: str, dest: Path) -> Path:
    """Run ``python -m build`` to produce a wheel or sdist in *dest*.

    Returns the single artifact path.
    """
    flag = "--wheel" if kind == "wheel" else "--sdist"
    result = subprocess.run(
        [sys.executable, "-m", "build", flag, "--outdir", str(dest), str(REPO_ROOT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"{kind} build failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    ext = "*.whl" if kind == "wheel" else "*.tar.gz"
    artifacts = list(dest.glob(ext))
    assert len(artifacts) == 1, f"Expected 1 {kind} artifact, found: {artifacts}"
    return artifacts[0]


# ---------------------------------------------------------------------------
# Packaging validation — wheel and sdist contents
# ---------------------------------------------------------------------------

class TestPackagingBuild:
    """Build wheel and sdist, then inspect their contents."""

    @pytest.fixture(scope="class")
    def wheel_path(self, tmp_path_factory):
        return _build_dist("wheel", tmp_path_factory.mktemp("wheel_dist"))

    @pytest.fixture(scope="class")
    def sdist_path(self, tmp_path_factory):
        return _build_dist("sdist", tmp_path_factory.mktemp("sdist_dist"))

    # -- wheel ----------------------------------------------------------------

    def test_wheel_contains_core_modules(self, wheel_path):
        """All core Python modules must be present in the wheel."""
        with zipfile.ZipFile(wheel_path) as zf:
            names = zf.namelist()
        expected = [
            "qa_agent/__init__.py",
            "qa_agent/agent.py",
            "qa_agent/cli.py",
            "qa_agent/config.py",
            "qa_agent/models.py",
            "qa_agent/ai_planner.py",
            "qa_agent/plan_cache.py",
            "qa_agent/web/__init__.py",
            "qa_agent/web/server.py",
        ]
        for path in expected:
            assert any(path in n for n in names), (
                f"{path!r} missing from wheel.  Wheel contents sample: {names[:15]}"
            )

    def test_wheel_contains_web_templates(self, wheel_path):
        """HTML templates must be bundled inside the wheel."""
        with zipfile.ZipFile(wheel_path) as zf:
            names = zf.namelist()
        for template in ("index.html", "base.html", "run.html", "session.html", "sessions.html"):
            assert any(f"templates/{template}" in n for n in names), (
                f"Template {template!r} missing from wheel.\n"
                f"Web-related entries: {[n for n in names if 'web' in n]}"
            )

    def test_wheel_contains_static_assets(self, wheel_path):
        """JS and CSS static assets must be bundled inside the wheel."""
        with zipfile.ZipFile(wheel_path) as zf:
            names = zf.namelist()
        for asset in ("app.js", "style.css"):
            assert any(f"static/{asset}" in n for n in names), (
                f"Static asset {asset!r} missing from wheel"
            )

    def test_wheel_metadata_version_matches_package(self, wheel_path):
        """The METADATA file version must match ``qa_agent.__version__``."""
        from qa_agent import __version__
        with zipfile.ZipFile(wheel_path) as zf:
            metadata_entries = [n for n in zf.namelist() if n.endswith("/METADATA")]
            assert metadata_entries, "No METADATA file found in wheel"
            metadata = zf.read(metadata_entries[0]).decode()
        assert f"Version: {__version__}" in metadata, (
            f"Version {__version__!r} not found in wheel METADATA"
        )

    def test_wheel_entry_points(self, wheel_path):
        """The CLI entry points ``qa-agent`` and ``qa-agent-web`` must be declared."""
        with zipfile.ZipFile(wheel_path) as zf:
            ep_entries = [n for n in zf.namelist() if "entry_points" in n]
            assert ep_entries, "No entry_points.txt found in wheel"
            ep_text = zf.read(ep_entries[0]).decode()
        assert "qa-agent" in ep_text, f"qa-agent entry point missing. entry_points.txt:\n{ep_text}"
        assert "qa-agent-web" in ep_text, (
            f"qa-agent-web entry point missing. entry_points.txt:\n{ep_text}"
        )

    # -- sdist ----------------------------------------------------------------

    def test_sdist_contains_readme(self, sdist_path):
        """README.md must be included in the sdist."""
        with tarfile.open(sdist_path, "r:gz") as tf:
            members = tf.getnames()
        assert any("README.md" in m for m in members), "README.md missing from sdist"

    def test_sdist_contains_pyproject(self, sdist_path):
        """pyproject.toml must be included in the sdist."""
        with tarfile.open(sdist_path, "r:gz") as tf:
            members = tf.getnames()
        assert any("pyproject.toml" in m for m in members), "pyproject.toml missing from sdist"

    def test_sdist_contains_license(self, sdist_path):
        """LICENSE must be included in the sdist."""
        with tarfile.open(sdist_path, "r:gz") as tf:
            members = tf.getnames()
        assert any("LICENSE" in m for m in members), "LICENSE missing from sdist"

    def test_sdist_contains_source_modules(self, sdist_path):
        """Core source files must be in the sdist."""
        with tarfile.open(sdist_path, "r:gz") as tf:
            members = tf.getnames()
        for module in ("cli.py", "agent.py", "models.py", "config.py"):
            assert any(module in m for m in members), f"{module} missing from sdist"

    def test_sdist_contains_web_assets(self, sdist_path):
        """Web templates and static assets must be in the sdist."""
        with tarfile.open(sdist_path, "r:gz") as tf:
            members = tf.getnames()
        for asset in ("app.js", "style.css", "index.html", "base.html"):
            assert any(asset in m for m in members), (
                f"Web asset {asset!r} missing from sdist"
            )


# ---------------------------------------------------------------------------
# Web UI asset inclusion — on-disk verification (no build required)
# ---------------------------------------------------------------------------

class TestWebUIAssets:
    """Verify web UI assets exist on disk and are declared in pyproject.toml."""

    def test_templates_directory_exists(self):
        templates_dir = REPO_ROOT / "qa_agent" / "web" / "templates"
        assert templates_dir.is_dir(), f"templates/ missing at {templates_dir}"

    def test_static_directory_exists(self):
        static_dir = REPO_ROOT / "qa_agent" / "web" / "static"
        assert static_dir.is_dir(), f"static/ missing at {static_dir}"

    @pytest.mark.parametrize("name", ["base.html", "index.html", "run.html",
                                       "session.html", "sessions.html"])
    def test_html_template_present_and_nonempty(self, name):
        path = REPO_ROOT / "qa_agent" / "web" / "templates" / name
        assert path.exists(), f"Template {name!r} not found"
        assert path.stat().st_size > 0, f"Template {name!r} is empty"

    def test_app_js_present_and_nonempty(self):
        path = REPO_ROOT / "qa_agent" / "web" / "static" / "app.js"
        assert path.exists(), "app.js not found"
        assert path.stat().st_size > 0, "app.js is empty"

    def test_style_css_present_and_nonempty(self):
        path = REPO_ROOT / "qa_agent" / "web" / "static" / "style.css"
        assert path.exists(), "style.css not found"
        assert path.stat().st_size > 0, "style.css is empty"

    def test_pyproject_declares_package_data_for_web(self):
        """``[tool.setuptools.package-data]`` must cover web templates and static files."""
        content = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert "[tool.setuptools.package-data]" in content, (
            "No [tool.setuptools.package-data] section found in pyproject.toml; "
            "web assets will be excluded from the wheel."
        )
        # The section must reference qa_agent.web (or a wildcard) and cover
        # templates and/or static files.
        assert "qa_agent.web" in content, (
            "pyproject.toml package-data does not mention qa_agent.web"
        )
        assert "template" in content or "static" in content, (
            "pyproject.toml package-data entry for qa_agent.web must cover "
            "templates/*.html and/or static/*"
        )

    def test_flask_app_references_correct_template_dir(self):
        """Flask app in server.py must resolve templates relative to the web package."""
        server_src = (REPO_ROOT / "qa_agent" / "web" / "server.py").read_text()
        # Flask(name) uses the module's directory — templates must live there
        assert "Flask(__name__)" in server_src, (
            "Flask app is not created with __name__; template resolution may be wrong"
        )


# ---------------------------------------------------------------------------
# README consistency and formatting
# ---------------------------------------------------------------------------

class TestReadmeConsistency:
    """README examples must match the actual implementation."""

    @pytest.fixture(scope="class")
    def readme(self):
        return (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    def test_readme_uses_pages_tested(self, readme):
        """The programmatic example must use ``session.pages_tested`` (not ``session.pages``)."""
        # ``session.pages`` does not exist on TestSession; the correct attribute is pages_tested
        assert "session.pages_tested" in readme, (
            "README programmatic example should reference session.pages_tested"
        )

    def test_readme_does_not_reference_nonexistent_pages_attr(self, readme):
        """``session.pages`` (without _tested) must not appear in code blocks."""
        # Find all fenced code blocks and check they don't use the wrong attribute
        code_blocks = re.findall(r"```(?:python)?\n(.*?)```", readme, re.DOTALL)
        for block in code_blocks:
            # session.pages[ or session.pages) signals the wrong attribute name
            bad = re.search(r"session\.pages(?!_tested)[\[\)\.\s,]", block)
            assert not bad, (
                f"README code block uses 'session.pages' (non-existent attribute):\n{block}"
            )

    def test_readme_documents_exit_codes(self, readme):
        """README must document all four exit codes."""
        for code in ("0", "1", "2", "130"):
            assert code in readme, f"Exit code {code!r} not documented in README"

    def test_readme_installation_commands(self, readme):
        """README must show pip install and playwright install commands."""
        assert "pip install" in readme
        assert "playwright install" in readme

    def test_readme_version_flag_mentioned(self, readme):
        """README must document the --version flag."""
        assert "--version" in readme, "README should document the --version CLI flag"

    def test_no_broken_local_image_links(self, readme):
        """Every local image path referenced in README must exist on disk."""
        pattern = re.compile(r"!\[.*?\]\(\./([^)]+)\)")
        for match in pattern.finditer(readme):
            rel_path = match.group(1)
            full_path = REPO_ROOT / rel_path
            assert full_path.exists(), (
                f"README references image that doesn't exist: {rel_path!r}"
            )

    def test_readme_programmatic_imports_importable(self, readme):
        """Classes imported in the README programmatic example must actually exist."""
        # Extract the from-import line in the programmatic usage section
        imports = re.findall(
            r"from qa_agent(?:\.\w+)? import ([\w, ]+)", readme
        )
        for import_list in imports:
            for name in (n.strip() for n in import_list.split(",")):
                if not name:
                    continue
                # Try to import from all likely submodules
                found = False
                for module in ("qa_agent", "qa_agent.agent", "qa_agent.config", "qa_agent.models"):
                    try:
                        mod = __import__(module, fromlist=[name])
                        if hasattr(mod, name):
                            found = True
                            break
                    except ImportError:
                        pass
                assert found, (
                    f"README imports {name!r} but it cannot be found in qa_agent.*"
                )


# ---------------------------------------------------------------------------
# CLI smoke tests — subprocess
# ---------------------------------------------------------------------------

class TestCLISmoke:
    """Invoke the CLI via subprocess to verify the installed entry point works."""

    def test_version_flag_exits_0(self):
        result = subprocess.run(
            [sys.executable, "-m", "qa_agent", "--version"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"--version exited {result.returncode}. stderr: {result.stderr}"
        )

    def test_version_flag_prints_version_string(self):
        from qa_agent import __version__
        result = subprocess.run(
            [sys.executable, "-m", "qa_agent", "--version"],
            capture_output=True, text=True,
        )
        output = result.stdout + result.stderr
        assert __version__ in output, (
            f"Expected {__version__!r} in output, got: {output!r}"
        )

    def test_help_flag_exits_0(self):
        result = subprocess.run(
            [sys.executable, "-m", "qa_agent", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

    def test_help_flag_mentions_url_argument(self):
        result = subprocess.run(
            [sys.executable, "-m", "qa_agent", "--help"],
            capture_output=True, text=True,
        )
        output = result.stdout + result.stderr
        assert "url" in output.lower(), f"'url' not found in --help output: {output[:500]}"

    def test_help_flag_mentions_mode(self):
        result = subprocess.run(
            [sys.executable, "-m", "qa_agent", "--help"],
            capture_output=True, text=True,
        )
        output = result.stdout + result.stderr
        assert "--mode" in output

    def test_help_flag_mentions_output(self):
        result = subprocess.run(
            [sys.executable, "-m", "qa_agent", "--help"],
            capture_output=True, text=True,
        )
        output = result.stdout + result.stderr
        assert "--output" in output

    def test_no_args_exits_nonzero(self):
        """The CLI with no arguments must exit non-zero (missing required URL arg)."""
        result = subprocess.run(
            [sys.executable, "-m", "qa_agent"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0, "Expected non-zero exit when no URL is given"

    def test_no_cache_without_instructions_exits_2(self):
        """--no-cache without --instructions must exit 2."""
        result = subprocess.run(
            [sys.executable, "-m", "qa_agent", "--no-cache", "https://example.com"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2

    def test_invalid_mode_exits_nonzero(self):
        result = subprocess.run(
            [sys.executable, "-m", "qa_agent", "--mode", "not_a_mode", "https://example.com"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# Public API smoke tests
# ---------------------------------------------------------------------------

class TestPublicAPI:
    """The public Python API must be importable and structurally correct."""

    def test_version_attribute_exists(self):
        from qa_agent import __version__
        assert isinstance(__version__, str) and __version__

    def test_version_is_pep440(self):
        from qa_agent import __version__
        assert re.match(r"^\d+\.\d+(\.\d+)?", __version__), (
            f"__version__ {__version__!r} does not look like a PEP 440 version"
        )

    def test_qaagent_importable(self):
        from qa_agent.agent import QAAgent
        assert callable(QAAgent)

    def test_testconfig_importable_and_constructible(self):
        from qa_agent.config import TestConfig
        cfg = TestConfig(urls=["https://example.com"])
        assert cfg.urls == ["https://example.com"]

    def test_testmode_values(self):
        from qa_agent.config import TestMode
        assert hasattr(TestMode, "FOCUSED")
        assert hasattr(TestMode, "EXPLORE")

    def test_outputformat_values(self):
        from qa_agent.config import OutputFormat
        for name in ("CONSOLE", "JSON", "MARKDOWN", "PDF"):
            assert hasattr(OutputFormat, name), f"OutputFormat.{name} missing"

    def test_severity_values(self):
        from qa_agent.models import Severity
        for name in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
            assert hasattr(Severity, name), f"Severity.{name} missing"

    def test_finding_category_values(self):
        from qa_agent.models import FindingCategory
        for name in ("KEYBOARD_NAVIGATION", "MOUSE_INTERACTION", "FORM_HANDLING",
                     "ACCESSIBILITY", "CONSOLE_ERROR", "NETWORK_ERROR"):
            assert hasattr(FindingCategory, name), f"FindingCategory.{name} missing"

    def test_testsession_get_all_findings_returns_list(self):
        from datetime import datetime
        from qa_agent.models import TestSession
        session = TestSession(session_id="test-id", start_time=datetime.now())
        assert isinstance(session.get_all_findings(), list)

    def test_testsession_to_dict_keys(self):
        from datetime import datetime
        from qa_agent.models import TestSession
        session = TestSession(session_id="s1", start_time=datetime.now())
        d = session.to_dict()
        for key in ("session_id", "findings", "pages_tested", "total_findings",
                    "findings_by_severity"):
            assert key in d, f"Key {key!r} missing from TestSession.to_dict()"

    def test_finding_to_dict_keys(self):
        from datetime import datetime
        from qa_agent.models import Finding, FindingCategory, Severity
        finding = Finding(
            title="Test",
            description="desc",
            category=FindingCategory.ACCESSIBILITY,
            severity=Severity.MEDIUM,
            url="https://example.com",
        )
        d = finding.to_dict()
        for key in ("title", "description", "category", "severity", "url"):
            assert key in d, f"Key {key!r} missing from Finding.to_dict()"

    def test_reporters_importable(self):
        from qa_agent.reporters.console import ConsoleReporter
        from qa_agent.reporters.json_reporter import JSONReporter
        from qa_agent.reporters.markdown import MarkdownReporter
        for cls in (ConsoleReporter, JSONReporter, MarkdownReporter):
            assert callable(cls), f"{cls} is not callable"

    def test_testers_importable(self):
        from qa_agent.testers.accessibility import AccessibilityTester
        from qa_agent.testers.errors import ErrorDetector
        from qa_agent.testers.forms import FormTester
        from qa_agent.testers.keyboard import KeyboardTester
        from qa_agent.testers.mouse import MouseTester
        for cls in (AccessibilityTester, ErrorDetector, FormTester, KeyboardTester, MouseTester):
            assert callable(cls), f"{cls} is not callable"


# ---------------------------------------------------------------------------
# Exit-code smoke coverage (subprocess)
# ---------------------------------------------------------------------------

class TestExitCodeSmoke:
    """Verify all documented exit codes are produced under the correct conditions."""

    def _run_patched(self, findings_by_severity: dict, side_effect=None) -> int:
        """Run the CLI in a subprocess with QAAgent.run patched to return a fake session."""
        lines = [
            "import sys",
            "from unittest.mock import MagicMock, patch",
            "sys.argv = ['qa-agent', 'https://example.com']",
            "session = MagicMock()",
            f"session.findings_by_severity = {findings_by_severity!r}",
        ]
        if side_effect == "KeyboardInterrupt":
            lines += [
                "with patch('qa_agent.cli.QAAgent.__init__', return_value=None), \\",
                "     patch('qa_agent.cli.QAAgent.run', side_effect=KeyboardInterrupt):",
                "    from qa_agent.cli import main; main()",
            ]
        elif side_effect == "RuntimeError":
            lines += [
                "with patch('qa_agent.cli.QAAgent.__init__', return_value=None), \\",
                "     patch('qa_agent.cli.QAAgent.run', side_effect=RuntimeError('boom')):",
                "    from qa_agent.cli import main; main()",
            ]
        else:
            lines += [
                "with patch('qa_agent.cli.QAAgent.__init__', return_value=None), \\",
                "     patch('qa_agent.cli.QAAgent.run', return_value=session):",
                "    from qa_agent.cli import main; main()",
            ]
        result = subprocess.run(
            [sys.executable, "-c", "\n".join(lines)],
            capture_output=True,
            text=True,
        )
        return result.returncode

    def test_exit_0_no_critical_or_high_findings(self):
        """No critical/high findings → exit 0."""
        assert self._run_patched({}) == 0

    def test_exit_0_only_medium_findings(self):
        """Only medium findings → exit 0."""
        assert self._run_patched({"medium": 3}) == 0

    def test_exit_1_critical_findings(self):
        """Critical findings → exit 1."""
        assert self._run_patched({"critical": 1}) == 1

    def test_exit_1_high_findings(self):
        """High findings → exit 1."""
        assert self._run_patched({"high": 2}) == 1

    def test_exit_1_mixed_critical_and_high(self):
        """Both critical and high findings → exit 1."""
        assert self._run_patched({"critical": 1, "high": 1}) == 1

    def test_exit_2_on_runtime_error(self):
        """RuntimeError during run → exit 2."""
        assert self._run_patched({}, side_effect="RuntimeError") == 2

    def test_exit_130_on_keyboard_interrupt(self):
        """KeyboardInterrupt → exit 130."""
        assert self._run_patched({}, side_effect="KeyboardInterrupt") == 130
