"""Command-line interface for QA Agent."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .agent import QAAgent
from .config import (
    AuthConfig,
    OutputFormat,
    RecordingConfig,
    ScreenshotConfig,
    TestConfig,
    TestMode,
)
from .llm_client import LLMProvider


def parse_auth_config(auth_str: str | None, auth_file: str | None) -> AuthConfig | None:
    """Parse authentication configuration from string or file."""
    if auth_file:
        try:
            with open(auth_file) as f:
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
            print("Invalid auth format. Use: username:password or username:password@auth_url", file=sys.stderr)
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

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    # Positional arguments
    parser.add_argument(
        "urls",
        nargs="*",
        help="URL(s) to test (omit only when using --batch-file)",
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
        default=100,
        help="Maximum number of pages to test in explore mode (default: 100)",
    )
    parser.add_argument(
        "--max-interactions",
        type=int,
        default=50,
        dest="max_interactions_per_page",
        help="Maximum number of interactions per page (default: 50)",
    )

    # Concurrency
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of concurrent page-workers per run (default: 1, max: 16). "
             "Each worker drives its own browser, so memory scales with this value.",
    )
    parser.add_argument(
        "--batch-file",
        help="Path to a JSON file describing multiple runs to execute concurrently. "
             "Each entry is an object with at least 'urls' and optional overrides "
             "(mode, max_depth, max_pages, instructions, workers). Other settings are "
             "inherited from the command-line flags.",
    )
    parser.add_argument(
        "--pool-size",
        type=int,
        default=4,
        help="Max concurrent runs when using --batch-file (default: 4, max: 8).",
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
        default=str(Path.cwd() / "qa-agent-output"),
        help="Base directory for all output (default: ./qa-agent-output relative to current directory). "
             "Results are written to qa-agent-output/{domain}/{session_id}/qa_reports|screenshots|recordings",
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
    parser.add_argument(
        "--wcag-compliance",
        action="store_true",
        help="Enable detailed WCAG 2.1 AA compliance testing (off by default)",
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
            "bug report, or testing guidance. The LLM will interpret these and generate "
            "custom test steps to run alongside the standard test suite."
        ),
    )
    instruct_group.add_argument(
        "--instructions-file",
        help="Path to a text file containing natural language testing instructions.",
    )
    parser.add_argument(
        "--llm",
        choices=["anthropic", "openai"],
        default="anthropic",
        dest="llm_provider",
        help="LLM provider to use for AI instructions (default: anthropic)",
    )
    parser.add_argument(
        "--ai-model",
        default=None,
        help=(
            "Model to use for the selected LLM provider. "
            "Defaults: anthropic=claude-sonnet-4-6, openai=gpt-4o"
        ),
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

    # Validate: need URLs unless running a batch file
    if not args.urls and not args.batch_file:
        parser.error("at least one URL is required (or use --batch-file)")

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

    # Always include JSON so sessions are discoverable in the web interface
    if OutputFormat.JSON not in output_formats:
        output_formats.append(OutputFormat.JSON)

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
            with open(args.cookies) as f:
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
    instructions: str | None = None
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
        max_interactions_per_page=args.max_interactions_per_page,
        test_keyboard=not args.skip_keyboard,
        test_mouse=not args.skip_mouse,
        test_forms=not args.skip_forms,
        test_accessibility=not args.skip_accessibility,
        test_console_errors=not args.skip_errors,
        test_network_errors=not args.skip_errors,
        test_wcag_compliance=args.wcag_compliance,
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
        llm_provider=LLMProvider(args.llm_provider),
        ai_model=args.ai_model or None,
        use_plan_cache=not args.no_cache,
        workers=args.workers,
        invocation_context="cli",
    )

    # Batch mode: run multiple sessions concurrently from a spec file.
    if args.batch_file:
        _run_batch(args, config)
        return

    # Run the agent
    agent = QAAgent(config)

    try:
        session = agent.run()

        # Exit with error code if no pages were tested or critical/high issues found
        if not session.pages_tested:
            sys.exit(2)

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


def _run_batch(args, template: TestConfig) -> None:
    """Run multiple sessions concurrently from a JSON --batch-file.

    Each spec is an object with at least ``urls`` plus optional per-run overrides
    (``mode``, ``max_depth``, ``max_pages``, ``instructions``, ``workers``); all
    other settings are inherited from ``template`` (the command-line flags).
    Exits non-zero if any session has critical/high findings or tested no pages.
    """
    import copy

    from .batch import BatchRunner

    try:
        specs = json.loads(Path(args.batch_file).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error reading batch file: {e}", file=sys.stderr)
        sys.exit(2)

    if not isinstance(specs, list) or not specs:
        print("Batch file must be a non-empty JSON array of run specs", file=sys.stderr)
        sys.exit(2)

    configs: list[TestConfig] = []
    for i, spec in enumerate(specs):
        if not isinstance(spec, dict) or not spec.get("urls"):
            print(f"Batch spec #{i} must be an object with a non-empty 'urls'", file=sys.stderr)
            sys.exit(2)
        cfg = copy.deepcopy(template)
        cfg.urls = list(spec["urls"])
        if "mode" in spec:
            cfg.mode = TestMode.EXPLORE if spec["mode"] == "explore" else TestMode.FOCUSED
        if "max_depth" in spec:
            cfg.max_depth = int(spec["max_depth"])
        if "max_pages" in spec:
            cfg.max_pages = int(spec["max_pages"])
        if "instructions" in spec:
            cfg.instructions = spec["instructions"] or None
        if "workers" in spec:
            cfg.workers = int(spec["workers"])
        cfg.__post_init__()  # re-clamp workers after override
        configs.append(cfg)

    print(f"Running {len(configs)} sessions (pool size {args.pool_size})…")
    runner = BatchRunner(pool_size=args.pool_size)
    try:
        results = runner.run_all(configs)
    finally:
        runner.shutdown(wait=True)

    exit_code = 0
    for cfg, result in zip(configs, results, strict=False):
        label = cfg.urls[0] if cfg.urls else "?"
        if isinstance(result, Exception):
            print(f"  ✗ {label}: failed — {result}")
            exit_code = max(exit_code, 2)
            continue
        critical_high = (
            result.findings_by_severity.get("critical", 0)
            + result.findings_by_severity.get("high", 0)
        )
        print(
            f"  • {label}: {len(result.pages_tested)} pages, "
            f"{result.total_findings} findings ({result.status})"
        )
        if not result.pages_tested:
            exit_code = max(exit_code, 2)
        elif critical_high > 0:
            exit_code = max(exit_code, 1)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
