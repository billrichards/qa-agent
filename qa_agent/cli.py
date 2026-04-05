"""Command-line interface for QA Agent."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Resolve the project root once at import time (the directory that contains
# pyproject.toml / .git), walking up from this file's location.  This means
# default output directories are always anchored to the project root regardless
# of the working directory from which the command is invoked.
def _find_project_root() -> Path:
    candidate = Path(__file__).resolve().parent
    while candidate != candidate.parent:
        if (candidate / "pyproject.toml").exists() or (candidate / ".git").exists():
            return candidate
        candidate = candidate.parent
    return Path(__file__).resolve().parent.parent  # fallback

_PROJECT_ROOT = _find_project_root()

from .config import (
    TestConfig,
    TestMode,
    OutputFormat,
    AuthConfig,
    ScreenshotConfig,
    RecordingConfig,
)
from .agent import QAAgent


def parse_auth_config(auth_str: Optional[str], auth_file: Optional[str]) -> Optional[AuthConfig]:
    """Parse authentication configuration from string or file."""
    if auth_file:
        try:
            with open(auth_file, 'r') as f:
                auth_data = json.load(f)
            return AuthConfig(**auth_data)
        except Exception as e:
            print(f"Error loading auth file: {e}", file=sys.stderr)
            return None
    
    if auth_str:
        # Format: username:password or username:password@auth_url
        try:
            if '@' in auth_str and '://' in auth_str.split('@')[-1]:
                # Has auth URL
                creds, auth_url = auth_str.rsplit('@', 1)
                username, password = creds.split(':', 1)
                return AuthConfig(username=username, password=password, auth_url=auth_url)
            else:
                username, password = auth_str.split(':', 1)
                return AuthConfig(username=username, password=password)
        except ValueError:
            print(f"Invalid auth format. Use: username:password or username:password@auth_url", file=sys.stderr)
            return None
    
    return None


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="QA Agent - Automated Exploratory Testing Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test a single URL in focused mode
  qa-agent https://example.com

  # Test multiple URLs
  qa-agent https://example.com https://example.com/about

  # Explore mode - crawl and test
  qa-agent --mode explore --max-depth 2 https://example.com

  # With authentication
  qa-agent --auth "user:pass@https://example.com/login" https://example.com/dashboard

  # Custom output formats
  qa-agent --output json,markdown,pdf https://example.com

  # With screenshots and recording
  qa-agent --screenshots --record https://example.com
        """,
    )
    
    # Positional arguments
    parser.add_argument(
        "urls",
        nargs="+",
        help="URL(s) to test",
    )
    
    # Mode options
    parser.add_argument(
        "-m", "--mode",
        choices=["focused", "explore"],
        default="focused",
        help="Test mode: 'focused' tests only given URLs, 'explore' discovers and tests additional pages (default: focused)",
    )
    
    # Exploration options
    parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="Maximum link depth to explore in explore mode (default: 3)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=20,
        help="Maximum number of pages to test in explore mode (default: 20)",
    )
    parser.add_argument(
        "--same-domain",
        action="store_true",
        default=True,
        help="Stay within the same domain when exploring (default: true)",
    )
    parser.add_argument(
        "--allow-external",
        action="store_true",
        help="Allow exploring external domains (overrides --same-domain)",
    )
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        help="Regex pattern(s) for URLs to ignore (can be used multiple times)",
    )
    
    # Output options
    parser.add_argument(
        "-o", "--output",
        default="console,markdown",
        help="Output formats, comma-separated: console,markdown,json,pdf (default: console,markdown)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(_PROJECT_ROOT / "output"),
        help="Base directory for all output (default: <project-root>/output). "
             "Results are written to output/{domain}/{session_id}/qa_reports|screenshots|recordings",
    )
    
    # Browser options
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode (default: true)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser with visible window",
    )
    parser.add_argument(
        "--viewport",
        default="1280x720",
        help="Viewport size as WIDTHxHEIGHT (default: 1280x720)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30000,
        help="Timeout in milliseconds (default: 30000)",
    )
    
    # Test categories
    parser.add_argument(
        "--skip-keyboard",
        action="store_true",
        help="Skip keyboard navigation tests",
    )
    parser.add_argument(
        "--skip-mouse",
        action="store_true",
        help="Skip mouse interaction tests",
    )
    parser.add_argument(
        "--skip-forms",
        action="store_true",
        help="Skip form handling tests",
    )
    parser.add_argument(
        "--skip-accessibility",
        action="store_true",
        help="Skip accessibility tests",
    )
    parser.add_argument(
        "--skip-errors",
        action="store_true",
        help="Skip console/network error detection",
    )
    
    # Authentication
    parser.add_argument(
        "--auth",
        help="Authentication: 'username:password' or 'username:password@auth_url'",
    )
    parser.add_argument(
        "--auth-file",
        help="Path to JSON file with authentication config",
    )
    parser.add_argument(
        "--cookies",
        help="Path to JSON file with cookies to set",
    )
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        help="Custom header in 'Name: Value' format (can be used multiple times)",
    )
    
    # Screenshots and recording
    parser.add_argument(
        "--screenshots",
        action="store_true",
        help="Enable screenshots on errors",
    )
    parser.add_argument(
        "--screenshots-all",
        action="store_true",
        help="Take screenshot after each interaction",
    )
    parser.add_argument(
        "--full-page",
        action="store_true",
        help="Take full page screenshots",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="Record browser session as video",
    )

    # Agentic testing options (--instructions and --instructions-file are mutually exclusive)
    instruct_group = parser.add_mutually_exclusive_group()
    instruct_group.add_argument(
        "--instructions",
        help=(
            "Natural language instructions for agentic testing: a feature description, "
            "bug report, or testing guidance. Claude will interpret these and generate "
            "custom test steps to run alongside the standard test suite."
        ),
    )
    instruct_group.add_argument(
        "--instructions-file",
        help="Path to a text file containing natural language testing instructions.",
    )
    parser.add_argument(
        "--ai-model",
        default="claude-sonnet-4-6",
        help="Claude model to use for instruction interpretation (default: claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass the test plan cache and always call the AI. Only valid with --instructions or --instructions-file.",
    )
    args = parser.parse_args()

    # Validate: --no-cache requires instructions
    if args.no_cache and not (args.instructions or args.instructions_file):
        parser.error("--no-cache can only be used with --instructions or --instructions-file")
    
    # Parse output formats
    output_formats = []
    for fmt in args.output.split(","):
        fmt = fmt.strip().lower()
        if fmt == "console":
            output_formats.append(OutputFormat.CONSOLE)
        elif fmt == "markdown":
            output_formats.append(OutputFormat.MARKDOWN)
        elif fmt == "json":
            output_formats.append(OutputFormat.JSON)
        elif fmt == "pdf":
            output_formats.append(OutputFormat.PDF)
        else:
            print(f"Unknown output format: {fmt}", file=sys.stderr)
    
    if not output_formats:
        output_formats = [OutputFormat.CONSOLE, OutputFormat.MARKDOWN]
    
    # Parse viewport
    try:
        width, height = map(int, args.viewport.split("x"))
    except ValueError:
        print(f"Invalid viewport format: {args.viewport}. Use WIDTHxHEIGHT", file=sys.stderr)
        width, height = 1280, 720
    
    # Parse authentication
    auth_config = parse_auth_config(args.auth, args.auth_file)
    
    # Handle cookies file
    if args.cookies:
        try:
            with open(args.cookies, 'r') as f:
                cookies = json.load(f)
            if auth_config:
                auth_config.cookies = cookies
            else:
                auth_config = AuthConfig(cookies=cookies)
        except Exception as e:
            print(f"Error loading cookies: {e}", file=sys.stderr)
    
    # Handle custom headers
    if args.header:
        headers = {}
        for header in args.header:
            if ':' in header:
                name, value = header.split(':', 1)
                headers[name.strip()] = value.strip()
        if headers:
            if auth_config:
                auth_config.headers = headers
            else:
                auth_config = AuthConfig(headers=headers)
    
    # Resolve natural language instructions (inline or from file)
    instructions: Optional[str] = None
    if args.instructions_file:
        try:
            instructions = Path(args.instructions_file).read_text(encoding="utf-8").strip()
        except Exception as e:
            print(f"Error reading instructions file: {e}", file=sys.stderr)
    elif args.instructions:
        instructions = args.instructions.strip() or None

    # Build configuration
    config = TestConfig(
        urls=args.urls,
        mode=TestMode.EXPLORE if args.mode == "explore" else TestMode.FOCUSED,
        output_formats=output_formats,
        output_dir=args.output_dir,
        headless=not args.no_headless,
        viewport_width=width,
        viewport_height=height,
        timeout=args.timeout,
        max_depth=args.max_depth,
        max_pages=args.max_pages,
        test_keyboard=not args.skip_keyboard,
        test_mouse=not args.skip_mouse,
        test_forms=not args.skip_forms,
        test_accessibility=not args.skip_accessibility,
        test_console_errors=not args.skip_errors,
        test_network_errors=not args.skip_errors,
        auth=auth_config,
        screenshots=ScreenshotConfig(
            enabled=args.screenshots or args.screenshots_all,
            on_error=args.screenshots or args.screenshots_all,
            on_interaction=args.screenshots_all,
            full_page=args.full_page,
        ),
        recording=RecordingConfig(
            enabled=args.record,
        ),
        ignore_patterns=args.ignore,
        same_domain_only=not args.allow_external,
        instructions=instructions,
        ai_model=args.ai_model,
        use_plan_cache=not args.no_cache,
    )
    
    # Run the agent
    agent = QAAgent(config)
    
    try:
        session = agent.run()
        
        # Exit with error code if critical/high issues found
        critical_high = (
            session.findings_by_severity.get("critical", 0) +
            session.findings_by_severity.get("high", 0)
        )
        
        if critical_high > 0:
            sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\nError running tests: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
