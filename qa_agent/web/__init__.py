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
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.lower() if e.stderr else ""
            if "permission" in err_msg or "denied" in err_msg:
                print(
                    "Permission denied installing Chromium. Try:\n"
                    "  playwright install chromium\n"
                    "Or set PLAYWRIGHT_BROWSERS_PATH to a writable directory:\n"
                    "  export PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers\n"
                    "  qa-agent-web",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Failed to install Chromium:\n{e.stderr or 'Unknown error'}\n\n"
                    "Try manually: playwright install chromium",
                    file=sys.stderr,
                )
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
