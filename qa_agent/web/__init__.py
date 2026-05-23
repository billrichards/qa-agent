"""QA Agent web interface package.

The ``serve_web_cli`` function here is the ``qa-agent-web`` entry point.
It wraps the real server import so that a missing Flask installation produces
a clear, actionable error instead of a bare ``ModuleNotFoundError``.
"""

import subprocess
import sys


def _ensure_chromium_installed() -> None:
    """Ensure Chromium browser is installed. Install it if missing."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium
    except Exception:
        print("Installing Chromium browser (this may take a minute)...", file=sys.stderr)
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True,
                capture_output=False,
            )
        except subprocess.CalledProcessError:
            print("Failed to install Chromium. Run: playwright install chromium", file=sys.stderr)
            sys.exit(2)


def serve_web_cli() -> None:
    """Entry-point wrapper for the ``qa-agent-web`` command.

    Imports the Flask-based server lazily so that a missing ``flask`` package
    produces a helpful error message rather than a traceback.
    """
    _ensure_chromium_installed()

    try:
        import nh3  # noqa: F401 — verify optional dep is present before starting

        from qa_agent.web.server import serve_web_cli as _serve
    except ModuleNotFoundError as exc:
        missing = str(exc).lower()
        if "flask" in missing or "nh3" in missing or "markdown" in missing:
            print(
                "Error: the web interface requires Flask, nh3, and markdown, which are not installed.\n"
                "\n"
                "Install them with:\n"
                "    pip install 'qa-agent[web]'\n"
                "\n"
                "Then re-run:  qa-agent-web",
                file=sys.stderr,
            )
            sys.exit(1)
        raise
    _serve()
