"""
QA Agent - Automated Exploratory Testing Tool

A Python/Playwright-based QA agent that performs exploratory testing on web applications,
testing various input methods and detecting UX issues.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("qa-agent")
except PackageNotFoundError:
    # Package not installed (e.g. running from source without install)
    __version__ = "0.1.1"
