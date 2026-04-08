"""Subprocess helper invoked by TestExitCodeSmoke in test_packaging.py.

Keeping the mock wiring here (rather than as inline strings) means a rename
or refactor of qa_agent.cli will produce a clear ImportError/AttributeError
rather than a mysterious wrong-exit-code failure.

Usage:
    python tests/_cli_exit_helper.py <scenario>

Scenarios and expected exit codes:
    clean              0   — no findings
    medium             0   — only medium-severity findings
    critical           1   — one critical finding
    high               1   — one high finding
    mixed              1   — critical + high findings
    runtime_error      2   — agent raises RuntimeError
    keyboard_interrupt 130 — agent raises KeyboardInterrupt
"""

import sys
from unittest.mock import MagicMock, patch

if len(sys.argv) < 2:
    print(f"Usage: {__file__} <scenario>", file=sys.stderr)
    sys.exit(255)

scenario = sys.argv[1]
# Reset argv so the CLI parser sees a clean invocation
sys.argv = ["qa-agent", "https://example.com"]

_FINDINGS: dict[str, dict] = {
    "clean":    {},
    "medium":   {"medium": 3},
    "critical": {"critical": 1},
    "high":     {"high": 2},
    "mixed":    {"critical": 1, "high": 1},
}

from qa_agent.cli import main as _cli_main  # noqa: E402 — intentional late import

if scenario in _FINDINGS:
    session = MagicMock()
    session.findings_by_severity = _FINDINGS[scenario]
    with patch("qa_agent.cli.QAAgent.__init__", return_value=None), \
         patch("qa_agent.cli.QAAgent.run", return_value=session):
        _cli_main()

elif scenario == "runtime_error":
    with patch("qa_agent.cli.QAAgent.__init__", return_value=None), \
         patch("qa_agent.cli.QAAgent.run", side_effect=RuntimeError("boom")):
        _cli_main()

elif scenario == "keyboard_interrupt":
    with patch("qa_agent.cli.QAAgent.__init__", return_value=None), \
         patch("qa_agent.cli.QAAgent.run", side_effect=KeyboardInterrupt):
        _cli_main()

else:
    print(f"Unknown scenario: {scenario!r}", file=sys.stderr)
    sys.exit(255)
