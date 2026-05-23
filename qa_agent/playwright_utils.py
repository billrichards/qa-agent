"""Utilities for Playwright browser management."""

import subprocess
import sys


def ensure_chromium_installed() -> None:
    """Ensure Chromium browser is installed. Install it if missing.
    
    This function verifies that Chromium browser binaries are actually
    installed by attempting to launch the browser. If the browser is
    not found, it automatically runs 'playwright install chromium'.
    
    Raises:
        SystemExit: With code 2 if installation fails.
    """
    try:
        from playwright.sync_api import sync_playwright
        
        # Actually verify chromium is installed by trying to launch it
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        # If we got here, chromium is installed
        return
    except Exception as e:
        # Check if this is a "browser not found" error
        err_str = str(e).lower()
        if "executable" not in err_str and "not found" not in err_str:
            # This is some other error, re-raise it
            raise
        
        # Browser not found, attempt to install
        print("Installing Chromium browser (this may take a minute)...", file=sys.stderr)
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True,
                capture_output=True,
                text=True,
            )
            print("✓ Chromium installed successfully", file=sys.stderr)
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.lower() if e.stderr else ""
            if "permission" in err_msg or "denied" in err_msg:
                print(
                    "Permission denied installing Chromium. Try:\n"
                    "  playwright install chromium\n"
                    "Or set PLAYWRIGHT_BROWSERS_PATH to a writable directory:\n"
                    "  export PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers\n"
                    "  qa-agent <url>",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Failed to install Chromium:\n{e.stderr or 'Unknown error'}\n\n"
                    "Try manually: playwright install chromium",
                    file=sys.stderr,
                )
            sys.exit(2)
