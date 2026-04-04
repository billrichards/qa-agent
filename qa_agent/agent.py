"""Core QA Agent implementation."""

import os
import re
import time
import uuid
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext

from .config import TestConfig, TestMode, OutputFormat, AuthConfig
from .models import TestSession, PageAnalysis, Finding
from .testers import (
    KeyboardTester,
    MouseTester,
    FormTester,
    AccessibilityTester,
    ErrorDetector,
)
from .reporters import ConsoleReporter, MarkdownReporter, JSONReporter


class QAAgent:
    """Main QA Agent that orchestrates exploratory testing."""

    def __init__(self, config: TestConfig):
        self.config = config
        self.session: Optional[TestSession] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.error_detector: Optional[ErrorDetector] = None
        self.visited_urls: set[str] = set()
        self.urls_to_visit: list[str] = []
        
        # Initialize reporters
        self.reporters = []
        if OutputFormat.CONSOLE in config.output_formats:
            self.reporters.append(ConsoleReporter(config.output_dir))
        if OutputFormat.MARKDOWN in config.output_formats:
            self.reporters.append(MarkdownReporter(config.output_dir))
        if OutputFormat.JSON in config.output_formats:
            self.reporters.append(JSONReporter(config.output_dir))
        
        self.console = next(
            (r for r in self.reporters if isinstance(r, ConsoleReporter)),
            ConsoleReporter(config.output_dir)
        )

    def run(self) -> TestSession:
        """Run the complete QA test session."""
        self.session = TestSession(
            session_id=str(uuid.uuid4())[:8],
            start_time=datetime.now(),
            config_summary={
                "mode": self.config.mode.value,
                "urls": self.config.urls,
                "headless": self.config.headless,
                "max_depth": self.config.max_depth if self.config.mode == TestMode.EXPLORE else None,
                "max_pages": self.config.max_pages if self.config.mode == TestMode.EXPLORE else None,
            }
        )
        
        with sync_playwright() as playwright:
            self._setup_browser(playwright)
            
            try:
                # Authenticate if needed
                if self.config.auth:
                    self._authenticate()
                
                # Run tests based on mode
                if self.config.mode == TestMode.FOCUSED:
                    self._run_focused_mode()
                else:
                    self._run_explore_mode()
                    
            finally:
                self._cleanup()
        
        self.session.end_time = datetime.now()
        
        # Generate reports
        self._generate_reports()
        
        return self.session

    def _setup_browser(self, playwright):
        """Set up browser and context."""
        browser_options = {
            "headless": self.config.headless,
        }
        
        self.browser = playwright.chromium.launch(**browser_options)
        
        context_options = {
            "viewport": {
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            },
        }
        
        # Set up recording if enabled
        if self.config.recording.enabled:
            os.makedirs(self.config.recording.output_dir, exist_ok=True)
            context_options["record_video_dir"] = self.config.recording.output_dir
            context_options["record_video_size"] = self.config.recording.video_size
        
        # Add custom headers if provided in auth
        if self.config.auth and self.config.auth.headers:
            context_options["extra_http_headers"] = self.config.auth.headers
        
        self.context = self.browser.new_context(**context_options)
        self.context.set_default_timeout(self.config.timeout)
        
        self.page = self.context.new_page()
        
        # Set up error detector
        self.error_detector = ErrorDetector(self.page, self.config)
        self.error_detector.attach_listeners()

    def _authenticate(self):
        """Perform authentication if configured."""
        auth = self.config.auth
        
        # Handle cookies
        if auth.cookies:
            self.context.add_cookies([auth.cookies] if isinstance(auth.cookies, dict) else auth.cookies)
            return
        
        # Handle form-based auth
        if auth.auth_url and auth.username and auth.password:
            self.console.print_progress(f"Authenticating at {auth.auth_url}")
            self.page.goto(auth.auth_url)
            
            # Find and fill username
            username_selector = auth.username_selector or 'input[type="email"], input[type="text"][name*="user"], input[name*="email"], input#username, input#email'
            try:
                self.page.fill(username_selector, auth.username)
            except Exception as e:
                self.console.print_progress(f"Warning: Could not fill username field: {e}")
            
            # Find and fill password
            password_selector = auth.password_selector or 'input[type="password"]'
            try:
                self.page.fill(password_selector, auth.password)
            except Exception as e:
                self.console.print_progress(f"Warning: Could not fill password field: {e}")
            
            # Submit
            submit_selector = auth.submit_selector or 'button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("Sign in")'
            try:
                self.page.click(submit_selector)
                self.page.wait_for_load_state("networkidle", timeout=10000)
            except Exception as e:
                self.console.print_progress(f"Warning: Could not submit login form: {e}")

    def _run_focused_mode(self):
        """Run tests on specific URLs only."""
        for url in self.config.urls:
            if url in self.visited_urls:
                continue
            
            self._test_page(url)
            self.visited_urls.add(url)

    def _run_explore_mode(self):
        """Explore and test pages, following links."""
        # Initialize with seed URLs
        self.urls_to_visit = list(self.config.urls)
        depth_map = {url: 0 for url in self.urls_to_visit}
        
        while self.urls_to_visit and len(self.visited_urls) < self.config.max_pages:
            url = self.urls_to_visit.pop(0)
            
            if url in self.visited_urls:
                continue
            
            current_depth = depth_map.get(url, 0)
            
            if current_depth > self.config.max_depth:
                continue
            
            self._test_page(url)
            self.visited_urls.add(url)
            
            # Discover new links
            if current_depth < self.config.max_depth:
                new_urls = self._discover_links(url)
                for new_url in new_urls:
                    if new_url not in self.visited_urls and new_url not in self.urls_to_visit:
                        if not self._should_skip_url(new_url):
                            self.urls_to_visit.append(new_url)
                            depth_map[new_url] = current_depth + 1

    def _test_page(self, url: str):
        """Test a single page."""
        self.console.print_page_start(url)
        
        try:
            start_time = time.time()
            self.page.goto(url, wait_until="domcontentloaded")
            self.page.wait_for_load_state("networkidle", timeout=10000)
            load_time = (time.time() - start_time) * 1000
        except Exception as e:
            self.console.print_progress(f"Error loading page: {e}")
            return
        
        # Gather page info
        page_info = self._analyze_page_structure()
        
        page_analysis = PageAnalysis(
            url=url,
            title=self.page.title(),
            load_time_ms=load_time,
            interactive_elements=page_info["interactive_elements"],
            forms_count=page_info["forms_count"],
            links_count=page_info["links_count"],
            images_count=page_info["images_count"],
        )
        
        # Run testers
        all_findings: list[Finding] = []
        
        if self.config.test_keyboard:
            self.console.print_test_category("keyboard navigation")
            tester = KeyboardTester(self.page, self.config)
            findings = tester.run()
            all_findings.extend(findings)
            for f in findings:
                self.console.print_finding(f)
        
        if self.config.test_mouse:
            self.console.print_test_category("mouse interaction")
            tester = MouseTester(self.page, self.config)
            findings = tester.run()
            all_findings.extend(findings)
            for f in findings:
                self.console.print_finding(f)
        
        if self.config.test_forms:
            self.console.print_test_category("form handling")
            tester = FormTester(self.page, self.config)
            findings = tester.run()
            all_findings.extend(findings)
            for f in findings:
                self.console.print_finding(f)
        
        if self.config.test_accessibility:
            self.console.print_test_category("accessibility")
            tester = AccessibilityTester(self.page, self.config)
            findings = tester.run()
            all_findings.extend(findings)
            for f in findings:
                self.console.print_finding(f)
        
        if self.config.test_console_errors or self.config.test_network_errors:
            self.console.print_test_category("error detection")
            findings = self.error_detector.run()
            all_findings.extend(findings)
            for f in findings:
                self.console.print_finding(f)
            
            error_summary = self.error_detector.get_summary()
            page_analysis.console_errors = [
                m["text"] for m in self.error_detector.console_messages 
                if m["type"] == "error"
            ]
            page_analysis.network_errors = self.error_detector.network_errors
        
        # Take screenshot if there were errors
        if all_findings and self.config.screenshots.on_error:
            screenshot_path = self._take_screenshot(f"page_{len(self.visited_urls)}")
            if screenshot_path:
                for finding in all_findings:
                    if not finding.screenshot_path:
                        finding.screenshot_path = screenshot_path
        
        page_analysis.findings = all_findings
        self.session.add_page_analysis(page_analysis)
        
        # Reset error detector for next page
        self.error_detector.console_messages = []
        self.error_detector.network_errors = []
        self.error_detector.js_errors = []

    def _analyze_page_structure(self) -> dict:
        """Analyze the structure of the current page."""
        try:
            return self.page.evaluate("""() => ({
                interactive_elements: document.querySelectorAll('a, button, input, select, textarea, [onclick], [role="button"]').length,
                forms_count: document.querySelectorAll('form').length,
                links_count: document.querySelectorAll('a[href]').length,
                images_count: document.querySelectorAll('img').length,
            })""")
        except Exception:
            return {
                "interactive_elements": 0,
                "forms_count": 0,
                "links_count": 0,
                "images_count": 0,
            }

    def _discover_links(self, current_url: str) -> list[str]:
        """Discover links on the current page for exploration."""
        try:
            links = self.page.evaluate("""() => {
                const links = document.querySelectorAll('a[href]');
                return Array.from(links).map(a => a.href).filter(href => 
                    href && 
                    !href.startsWith('javascript:') && 
                    !href.startsWith('mailto:') &&
                    !href.startsWith('tel:') &&
                    !href.startsWith('#')
                );
            }""")
            
            valid_links = []
            current_domain = urlparse(current_url).netloc
            
            for link in links:
                parsed = urlparse(link)
                
                # Filter by domain if configured
                if self.config.same_domain_only and parsed.netloc != current_domain:
                    continue
                
                # Normalize URL
                normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                if normalized.endswith('/'):
                    normalized = normalized[:-1]
                
                valid_links.append(normalized)
            
            return list(set(valid_links))
            
        except Exception:
            return []

    def _should_skip_url(self, url: str) -> bool:
        """Check if URL should be skipped based on ignore patterns."""
        for pattern in self.config.ignore_patterns:
            if re.search(pattern, url):
                return True
        
        # Skip common non-page resources
        skip_extensions = ['.pdf', '.zip', '.jpg', '.png', '.gif', '.svg', '.css', '.js', '.ico']
        for ext in skip_extensions:
            if url.lower().endswith(ext):
                return True
        
        return False

    def _take_screenshot(self, name: str) -> Optional[str]:
        """Take a screenshot and return the path."""
        if not self.config.screenshots.enabled:
            return None
        
        os.makedirs(self.config.screenshots.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{timestamp}.png"
        filepath = os.path.join(self.config.screenshots.output_dir, filename)
        
        try:
            self.page.screenshot(
                path=filepath,
                full_page=self.config.screenshots.full_page
            )
            return filepath
        except Exception:
            return None

    def _cleanup(self):
        """Clean up browser resources."""
        if self.config.recording.enabled and self.context:
            # Get video path
            try:
                video = self.page.video
                if video:
                    video_path = video.path()
                    self.session.recording_path = video_path
            except Exception:
                pass
        
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()

    def _generate_reports(self):
        """Generate all configured reports."""
        for reporter in self.reporters:
            if isinstance(reporter, ConsoleReporter):
                reporter.generate(self.session)
            elif isinstance(reporter, MarkdownReporter):
                filepath = reporter.generate(self.session)
                self.console.print_progress(f"Markdown report saved: {filepath}")
            elif isinstance(reporter, JSONReporter):
                filepath = reporter.generate(self.session)
                self.console.print_progress(f"JSON report saved: {filepath}")
