# QA Agent

An automated exploratory testing tool that performs comprehensive QA testing on web applications, simulating human user interactions through various input methods (mouse, keyboard, TAB navigation, arrow keys, etc.).

## Features

- **Agentic Testing (powered by Claude):**
  - Provide a feature description or bug report in plain English
  - Claude generates custom test steps targeting your specific scenario
  - Runs alongside the standard test suite automatically

- **Two Testing Modes:**
  - **Focused Mode**: Tests only the specified URL(s)
  - **Explore Mode**: Discovers and tests additional pages by following links

- **Comprehensive Input Testing:**
  - Keyboard navigation (TAB, arrow keys, Enter, Escape)
  - Mouse interactions (click, hover, double-click, right-click)
  - Form handling and validation
  - Accessibility checks (WCAG compliance)

- **Error Detection:**
  - Console errors and warnings
  - Network failures (404s, 500s, etc.)
  - JavaScript exceptions
  - Broken images and links
  - Mixed content warnings

- **Multiple Output Formats:**
  - Real-time console output with colors
  - Markdown reports
  - JSON reports (for CI/CD integration)
  - PDF reports (professional formatted reports)

- **Screenshots & Recording:**
  - Automatic screenshots on errors
  - Full session video recording

## Installation

```bash
# Install the package
pip install -e .

# Install Playwright browsers
playwright install chromium

# Optional: Install PDF support
pip install -e ".[pdf]"
```

> **Agentic testing** requires an Anthropic API key. Set the `ANTHROPIC_API_KEY` environment variable before using `--instructions`.
> ```bash
> export ANTHROPIC_API_KEY=sk-ant-...
> ```

## Quick Start

```bash
# Test a single URL
qa-agent https://example.com

# Test multiple URLs
qa-agent https://example.com https://example.com/about

# Explore mode - discover and test pages
qa-agent --mode explore --max-depth 2 https://example.com
```

## Agentic Testing

Pass natural language instructions — a feature description, a bug report, or any testing guidance — and the agent will call Claude to interpret them and generate custom test steps to run on top of the standard suite.

### From a bug report

```bash
qa-agent --instructions "The login button does nothing when email is left blank — no validation error is shown" \
  https://example.com/login
```

### From a feature description

```bash
qa-agent --instructions "We added a 'Remember me' checkbox to the login form. \
  It should persist the session across browser restarts and be unchecked by default." \
  https://example.com/login
```

### From a file

For longer specs or bug reports, put the text in a file:

```bash
qa-agent --instructions-file feature-spec.txt https://example.com
```

### What happens

1. Before any browser testing, the agent calls Claude with your instructions and the target URL.
2. Claude returns a structured test plan: a summary, focus areas, custom test steps (with Playwright actions and assertions), and suggested URLs to include.
3. The agent prints the plan summary, then runs the custom steps on every tested page alongside the standard keyboard/mouse/form/accessibility/error testers.
4. Any assertion failure becomes a finding in the report with the severity and category Claude assigned.

If the Claude API call fails for any reason, a warning is printed and the run continues with the standard tests only.

### Model selection

By default the agent uses `claude-sonnet-4-6`. Override with `--ai-model`:

```bash
qa-agent --instructions "Test the checkout flow" \
  --ai-model claude-opus-4-6 \
  https://shop.example.com
```

### Programmatic usage with instructions

```python
from qa_agent import QAAgent, TestConfig

config = TestConfig(
    urls=["https://example.com/login"],
    instructions="Verify the password reset flow sends an email and the link expires after 24 hours.",
    ai_model="claude-opus-4-6",
)

agent = QAAgent(config)
session = agent.run()
```

---

## Usage

### Basic Testing

```bash
# Focused mode (default) - test only specified URLs
qa-agent https://example.com

# Explore mode - crawl and test discovered pages
qa-agent --mode explore https://example.com
```

### Authentication

```bash
# Username/password authentication
qa-agent --auth "username:password@https://example.com/login" https://example.com/dashboard

# Using a JSON auth file
qa-agent --auth-file auth.json https://example.com

# Using cookies
qa-agent --cookies cookies.json https://example.com

# Custom headers (e.g., Bearer token)
qa-agent --header "Authorization: Bearer token123" https://example.com
```

**auth.json example:**
```json
{
  "username": "testuser",
  "password": "testpass",
  "auth_url": "https://example.com/login",
  "username_selector": "input#email",
  "password_selector": "input#password",
  "submit_selector": "button[type=submit]"
}
```

### Output Options

```bash
# Specify output formats
qa-agent --output console,markdown,json https://example.com

# Generate PDF report (requires pdf extra)
qa-agent --output pdf https://example.com

# Multiple formats including PDF
qa-agent --output console,markdown,pdf https://example.com

# Custom output directory
qa-agent --output-dir ./my-reports https://example.com
```

> **Note:** PDF output requires the `weasyprint` library. Install with `pip install -e ".[pdf]"`. If not installed, PDF output will automatically fall back to Markdown.

### Screenshots & Recording

```bash
# Enable screenshots on errors
qa-agent --screenshots https://example.com

# Take screenshots after every interaction
qa-agent --screenshots-all https://example.com

# Full page screenshots
qa-agent --full-page --screenshots https://example.com

# Record video of the session
qa-agent --record https://example.com
```

### Browser Options

```bash
# Run with visible browser window
qa-agent --no-headless https://example.com

# Custom viewport size
qa-agent --viewport 1920x1080 https://example.com

# Custom timeout (in milliseconds)
qa-agent --timeout 60000 https://example.com
```

### Exploration Options

```bash
# Limit exploration depth
qa-agent --mode explore --max-depth 3 https://example.com

# Limit number of pages
qa-agent --mode explore --max-pages 50 https://example.com

# Allow external domains
qa-agent --mode explore --allow-external https://example.com

# Ignore certain URL patterns
qa-agent --mode explore --ignore ".*logout.*" --ignore ".*admin.*" https://example.com
```

### Skip Specific Tests

```bash
# Skip keyboard tests
qa-agent --skip-keyboard https://example.com

# Skip multiple test categories
qa-agent --skip-mouse --skip-forms https://example.com

# Available skip options:
#   --skip-keyboard
#   --skip-mouse
#   --skip-forms
#   --skip-accessibility
#   --skip-errors
```

## Programmatic Usage

```python
from qa_agent import QAAgent, TestConfig, TestMode, OutputFormat

config = TestConfig(
    urls=["https://example.com"],
    mode=TestMode.EXPLORE,
    output_formats=[OutputFormat.CONSOLE, OutputFormat.JSON, OutputFormat.PDF],
    max_depth=2,
    max_pages=10,
)

agent = QAAgent(config)
session = agent.run()

# Access results
print(f"Total findings: {session.total_findings}")
for finding in session.get_all_findings():
    print(f"- {finding.severity.value}: {finding.title}")
```

## Test Categories

### Keyboard Navigation
- TAB order and focusability
- Arrow key navigation in widgets
- Enter key activation
- Escape key for closing modals
- Keyboard trap detection
- Focus visibility indicators

### Mouse Interaction
- Click target functionality
- Hover states
- Double-click behavior
- Right-click/context menus
- Click target sizes (WCAG 2.5.5)
- Overlapping elements

### Form Handling
- Required field indicators
- Input validation feedback
- Error message accessibility
- Form labels and associations
- HTML5 input types
- Autocomplete attributes

### Accessibility
- Image alt text
- Heading structure (h1-h6)
- Link text quality
- Color contrast
- ARIA usage
- Landmark regions
- Language attributes
- Skip navigation links

### Error Detection
- Console errors and warnings
- Network errors (4xx, 5xx)
- JavaScript exceptions
- Broken images
- Broken anchor links
- Mixed content (HTTP on HTTPS)

## Output Examples

### Console Output
```
======================================================================
  QA AGENT TEST REPORT
======================================================================
  Session ID: a1b2c3d4
  Started:    2024-01-15 10:30:00
  Duration:   45.2 seconds
  Mode:       explore
======================================================================

📊 SUMMARY
----------------------------------------
  Pages tested: 5
  Total findings: 12

  By Severity:
    🟠 HIGH: 2
    🟡 MEDIUM: 5
    🔵 LOW: 5

  By Category:
    ⌨️ Keyboard Navigation: 3
    ♿ Accessibility: 4
    📝 Form Handling: 3
    🔧 Console Error: 2
```

### JSON Output
```json
{
  "meta": {
    "session_id": "a1b2c3d4",
    "start_time": "2024-01-15T10:30:00",
    "duration_seconds": 45.2
  },
  "summary": {
    "pages_tested": 5,
    "total_findings": 12,
    "findings_by_severity": {
      "high": 2,
      "medium": 5,
      "low": 5
    }
  },
  "findings": [...]
}
```

## CI/CD Integration

```yaml
# GitHub Actions example
- name: Run QA Tests
  run: |
    pip install qa-agent
    playwright install chromium
    qa-agent --output json --output-dir ./qa-results https://staging.example.com
  
- name: Upload Results
  uses: actions/upload-artifact@v3
  with:
    name: qa-results
    path: ./qa-results/
```

## Exit Codes

- `0`: All tests passed or only low/info severity issues
- `1`: Critical or high severity issues found
- `2`: Error running tests
- `130`: Interrupted by user (Ctrl+C)

## License

MIT License
