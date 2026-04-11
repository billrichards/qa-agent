# QA Agent - Repository Knowledge

## Project Overview

QA Agent is an automated exploratory testing tool built with Python and Playwright. It performs comprehensive QA testing on web applications by simulating human user interactions through various input methods.

## Quick Commands

```bash
# Install
pip install -e .
playwright install chromium

# Install with PDF support
pip install -e ".[pdf]"

# Build distribution (clean build)
rm -rf build/ dist/ && python -m build

# Run tests
python -m qa_agent https://example.com

# Explore mode
python -m qa_agent --mode explore --max-pages 10 https://example.com

# Full test with all outputs (including PDF)
python -m qa_agent --output console,json,markdown,pdf --screenshots https://example.com
```

## Architecture

```text
qa_agent/
├── __init__.py          # Package init
├── __main__.py          # Module entry point
├── cli.py               # CLI argument parsing
├── agent.py             # Core QA agent orchestrator
├── ai_planner.py        # AI-powered test planning (optional)
├── config.py            # Configuration dataclasses
├── models.py            # Data models (Finding, PageAnalysis, TestSession)
├── plan_cache.py        # Caching for AI test plans
├── testers/             # Test modules
│   ├── base.py          # Base tester class
│   ├── keyboard.py      # Keyboard navigation tests
│   ├── mouse.py         # Mouse interaction tests
│   ├── forms.py         # Form handling tests
│   ├── accessibility.py # Accessibility/WCAG tests
│   ├── wcag_compliance.py # Extended WCAG compliance tests
│   ├── custom.py        # Custom/user-defined tests
│   └── errors.py        # Console/network error detection
├── reporters/           # Output generators
│   ├── base.py          # Base reporter class
│   ├── console.py       # Real-time console output
│   ├── markdown.py      # Markdown report
│   ├── json_reporter.py # JSON report
│   └── pdf.py           # PDF report (requires weasyprint)
└── web/                 # Web UI (optional)
    ├── server.py        # Flask web server
    ├── static/          # CSS and JavaScript assets
    └── templates/       # HTML templates
```

## Test Categories

### Keyboard Tests (keyboard.py)

- TAB navigation and focusability
- Arrow key navigation in widgets
- Enter key activation
- Escape key modal closing
- Keyboard trap detection
- Focus visibility indicators

### Mouse Tests (mouse.py)

- Click target functionality
- Hover state feedback
- Double-click behavior
- Right-click/context menus
- Click target sizes (WCAG 2.5.5 - 44x44px minimum)
- Overlapping element detection

### Form Tests (forms.py)

- Required field indicators
- Input validation feedback
- Error message accessibility
- Form label associations
- HTML5 input type usage
- Autocomplete attributes

### Accessibility Tests (accessibility.py)

- Image alt text
- Heading structure (h1-h6)
- Link text quality
- Color contrast
- ARIA usage validation
- Landmark regions
- Language attributes
- Skip navigation links

### Error Detection (errors.py)

- Console errors and warnings
- Network errors (4xx, 5xx)
- JavaScript exceptions
- Broken images
- Broken anchor links
- Mixed content warnings

## Configuration

Main config class: `TestConfig` in `config.py`

Key settings:

- `mode`: FOCUSED or EXPLORE
- `max_depth`: Link depth for exploration
- `max_pages`: Max pages to test
- `test_*`: Enable/disable test categories
- `screenshots`: Screenshot configuration
- `recording`: Video recording configuration
- `auth`: Authentication settings

## Adding New Tests

1. Create a new tester in `testers/` extending `BaseTester`
2. Implement the `run()` method returning `list[Finding]`
3. Add to `testers/__init__.py`
4. Add config flag in `config.py` (e.g., `test_new_feature`)
5. Call from `agent.py` in `_test_page()`

## Severity Levels

- CRITICAL: Security issues, data loss
- HIGH: Major usability blockers
- MEDIUM: UX problems, accessibility issues
- LOW: Minor improvements, best practices
- INFO: Informational findings

## Output Formats

- Console: Real-time colored output
- Markdown: Human-readable report with tables
- JSON: Machine-readable for CI/CD integration
- PDF: Professional PDF report (requires `weasyprint` - install with `pip install -e ".[pdf]"`)

## Dependencies

- playwright>=1.40.0 (browser automation)
- Python 3.10+

### Optional Dependencies

- anthropic>=0.50.0 (agentic testing with `--instructions` — install with `pip install "qa-agent[ai]"`)
- weasyprint>=60.0 (PDF output support — install with `pip install "qa-agent[pdf]"`)
- flask>=3.0, markdown>=3.5 (web UI — install with `pip install "qa-agent[web]"`)
