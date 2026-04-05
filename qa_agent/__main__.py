"""Allow running the package as a module: python -m qa_agent

Usage:
  python -m qa_agent <url> [options]   # Run tests via CLI
  python -m qa_agent web [options]     # Start the web interface
"""

import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "web":
        sys.argv.pop(1)  # Remove 'web' so serve_web_cli sees only --host/--port/--debug
        from .web.server import serve_web_cli
        serve_web_cli()
    else:
        from .cli import main as cli_main
        cli_main()


if __name__ == "__main__":
    main()
