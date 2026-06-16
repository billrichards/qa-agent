"""Core QA Agent implementation."""

import copy
import os
import re
import threading
import time
import uuid
from datetime import datetime
from typing import Any, cast
from urllib.parse import urlparse

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from .concurrency import Frontier, PageIndexer
from .config import OutputFormat, TestConfig, TestMode
from .models import Finding, FindingCategory, PageAnalysis, Severity, TestPlan, TestSession
from .rate_limiter import HostRateLimiter
from .reporters import ConsoleReporter, JSONReporter, MarkdownReporter, PDFReporter
from .reporters.base import BaseReporter
from .testers import (
    AccessibilityTester,
    CustomTester,
    ErrorDetector,
    FormTester,
    KeyboardTester,
    MouseTester,
    WCAGComplianceTester,
)
from .testers.base import BaseTester


def _extract_domain(url: str) -> str:
    """Return a filesystem-safe domain (including subdomain) from a URL.

    e.g. ``https://www.example.com/path`` → ``www.example.com``
    """
    netloc = urlparse(url).netloc
    # Strip port number if present
    netloc = netloc.split(":")[0]
    # Sanitise: keep alphanumerics, dots, and hyphens; replace anything else
    safe = re.sub(r"[^\w.\-]", "_", netloc)
    return safe or "unknown"


def _hostname(url: str) -> str:
    """Return the bare hostname (no port) from a URL, for rate-limiter keys."""
    return urlparse(url).netloc.split(":")[0]


class QAAgent:
    """Main QA Agent that orchestrates exploratory testing."""

    def __init__(
        self,
        config: TestConfig,
        playwright_factory=None,
        worker_thread_init=None,
        rate_limiter: HostRateLimiter | None = None,
    ):
        # Deep-copy so per-session output-dir derivation below never mutates the
        # caller's config — essential when the same TestConfig template is handed
        # to several concurrent agents (e.g. by BatchRunner).
        self.config = copy.deepcopy(config)
        config = self.config
        self.session: TestSession | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.error_detector: ErrorDetector | None = None
        self.visited_urls: set[str] = set()
        self.urls_to_visit: list[str] = []
        self.test_plan: TestPlan | None = None
        self.stop_event: threading.Event | None = None  # Set by web server to request graceful stop
        self._reauth_count: int = 0  # Guards against infinite re-auth loops on bad credentials

        # If instructions explicitly mention logout/destructive flows, honour the user's intent
        # and disable the default destructive-link heuristic in explore mode.
        _instruction_text = (config.instructions or "").lower()
        _destructive_keywords = ["logout", "log out", "sign out", "signout", "log-out", "sign-out"]
        self._allow_destructive_urls: bool = any(kw in _instruction_text for kw in _destructive_keywords)

        # Optional factory callable that returns a sync_playwright() context manager.
        # Used by tests to inject a mock playwright without touching the network.
        self._playwright_factory = playwright_factory

        # Optional callable run at the very start of each worker thread. The web
        # layer uses this to route the worker's stdout to the right job queue.
        self._worker_thread_init = worker_thread_init

        # Concurrency state (used only when config.workers > 1).
        self._session_lock = threading.Lock()  # guards session aggregation
        self._page_indexer = PageIndexer()      # worker-safe screenshot indices
        self._recording_paths: list[str] = []   # one video per worker context

        # Shared per-host navigation rate limiter. One instance per QAAgent run
        # so all page-workers throttle against the same per-host budget.
        # BatchRunner may pass a shared instance so concurrent sessions hitting
        # the same host also share the budget; otherwise each agent builds its
        # own from config.rate_limit.
        self._rate_limiter = (
            rate_limiter if rate_limiter is not None else HostRateLimiter(config.rate_limit)
        )

        # Generate the session ID here so all output paths can be organized
        # under a session-specific subdirectory before reporters are created.
        self.session_id = str(uuid.uuid4())[:8]

        # Build the session base: output/{domain}/{session_id}/
        domain = _extract_domain(config.urls[0]) if config.urls else "unknown"
        session_base = os.path.join(config.output_dir, domain, self.session_id)
        config.output_dir = os.path.join(session_base, "qa_reports")
        config.screenshots.output_dir = os.path.join(session_base, "screenshots")
        config.recording.output_dir = os.path.join(session_base, "recordings")

        # Initialize reporters
        self.reporters: list[BaseReporter] = []
        if OutputFormat.CONSOLE in config.output_formats:
            self.reporters.append(ConsoleReporter(config.output_dir))
        if OutputFormat.MARKDOWN in config.output_formats:
            self.reporters.append(MarkdownReporter(config.output_dir))
        if OutputFormat.JSON in config.output_formats:
            self.reporters.append(JSONReporter(config.output_dir))
        if OutputFormat.PDF in config.output_formats:
            self.reporters.append(PDFReporter(config.output_dir))

        self.console = next(
            (r for r in self.reporters if isinstance(r, ConsoleReporter)),
            ConsoleReporter(config.output_dir)
        )

    def run(self) -> TestSession:
        """Run the complete QA test session."""
        self.session = TestSession(
            session_id=self.session_id,
            start_time=datetime.now(),
            config_summary={
                "mode": self.config.mode.value,
                "urls": self.config.urls,
                "headless": self.config.headless,
                "max_depth": self.config.max_depth if self.config.mode == TestMode.EXPLORE else None,
                "max_pages": self.config.max_pages if self.config.mode == TestMode.EXPLORE else None,
            }
        )

        # Generate AI test plan if instructions were provided
        if self.config.instructions:
            self._generate_test_plan()

        if self.config.workers > 1:
            self._run_concurrent()
        else:
            with self._factory()() as playwright:
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

        # Post-run LLM synthesis (opt-in)
        if self.config.synthesize_results:
            self._synthesize_results()

        # Generate reports
        self._generate_reports()

        return self.session

    def _generate_test_plan(self):
        """Call the AI planner to interpret instructions and build a TestPlan.

        Results are stored in a filesystem cache (keyed by instructions + URLs)
        and reused on subsequent runs with identical inputs unless
        ``config.use_plan_cache`` is False.
        """
        from .ai_planner import AIPlannerClient, effective_model
        from .llm_client import LLMError
        from .plan_cache import PlanCache

        cache = PlanCache() if self.config.use_plan_cache else None
        cache_key = PlanCache.make_key(self.config.instructions, self.config.urls) if cache else None

        # Try cache first
        if cache and cache_key:
            cached = cache.get(cache_key)
            if cached is not None:
                self.console.print_progress("Using cached AI test plan (pass --no-cache to regenerate).")
                self.test_plan = cached
                self._apply_test_plan()
                if self.test_plan and self.test_plan.warnings:
                    self.session.config_summary["plan_warnings"] = self.test_plan.warnings
                return

        model_name = effective_model(self.config.llm_provider, self.config.ai_model)
        self.console.print_progress(
            f"Generating AI test plan using {self.config.llm_provider.value}/{model_name}…"
        )
        try:
            planner = AIPlannerClient(
                provider=self.config.llm_provider,
                model=self.config.ai_model,
            )
            base_url = self.config.urls[0] if self.config.urls else ""
            self.test_plan = planner.plan(self.config.instructions, base_url)

            if cache and cache_key:
                cache.set(cache_key, self.test_plan)

            self._apply_test_plan()
            if self.test_plan and self.test_plan.warnings:
                self.session.config_summary["plan_warnings"] = self.test_plan.warnings

        except LLMError as exc:
            self.console.print_progress(
                f"Warning: AI planning failed — {exc}\nContinuing with standard tests only."
            )
            self.test_plan = None
        except Exception as exc:
            self.console.print_progress(
                f"Warning: AI planning failed ({exc}). Continuing with standard tests only."
            )
            self.test_plan = None

    def _apply_test_plan(self):
        """Print the test plan summary and enqueue any suggested URLs."""
        self.console.print_progress(f"Test plan: {self.test_plan.summary}")
        if self.test_plan.focus_areas:
            self.console.print_progress(
                "Focus areas: " + ", ".join(self.test_plan.focus_areas)
            )
        if self.test_plan.warnings:
            for warning in self.test_plan.warnings:
                self.console.print_warning(warning)
        self.console.print_progress(
            f"Custom test steps: {len(self.test_plan.custom_steps)}"
        )

        existing = set(self.config.urls)
        added: list[str] = []
        for url in self.test_plan.suggested_urls:
            if url and url not in existing:
                self.config.urls.append(url)
                existing.add(url)
                added.append(url)
        if added:
            self.console.print_progress(
                "AI suggested additional URL(s) to test: " + ", ".join(added)
            )

        if self.test_plan.notes:
            self.console.print_progress(f"Notes: {self.test_plan.notes}")

    def _synthesize_results(self):
        """Call the LLM post-run to produce a narrative synthesis of findings."""
        from .synthesizer import synthesize

        self.console.print_progress("Synthesizing results with AI...")
        result = synthesize(
            session=self.session,
            provider=self.config.llm_provider,
            model=self.config.ai_model,
        )
        if result:
            self.session.synthesis = result
            self.console.print_progress("AI synthesis complete.")
        else:
            self.console.print_progress(
                "Warning: AI synthesis failed — continuing without it."
            )

    def _factory(self):
        """Return the playwright context-manager factory (real or injected mock)."""
        return self._playwright_factory if self._playwright_factory is not None else sync_playwright

    def _launch_browser(self, playwright: Playwright) -> Browser:
        """Launch a Chromium browser with the configured options."""
        return playwright.chromium.launch(headless=self.config.headless)

    def _new_context_page(self, browser: Browser, storage_state=None) -> tuple[BrowserContext, Page]:
        """Create a browser context + page with the configured options.

        ``storage_state`` (a dict exported from a previously authenticated
        context) seeds cookies/localStorage so per-worker contexts inherit the
        logged-in session without each repeating the login flow.
        """
        context_options: dict = {
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

        if storage_state is not None:
            context_options["storage_state"] = storage_state

        context = browser.new_context(**context_options)
        context.set_default_timeout(self.config.timeout)
        page = context.new_page()
        return context, page

    def _setup_browser(self, playwright):
        """Set up the shared browser/context/page for the sequential code path."""
        self.browser = self._launch_browser(playwright)
        self.context, self.page = self._new_context_page(self.browser)

        # Set up error detector
        self.error_detector = ErrorDetector(self.page, self.config)
        self.error_detector.attach_listeners()

    def _authenticate(self, page: Page | None = None, context: BrowserContext | None = None):
        """Perform authentication if configured.

        Operates on the given ``page``/``context`` when supplied (used by
        concurrent workers re-authenticating on their own browser), otherwise
        falls back to the agent's shared ``self.page``/``self.context``.
        """
        auth = self.config.auth
        if auth is None:
            return
        context = context if context is not None else self.context
        assert context is not None

        # Handle cookies (no page needed). Cookies are user-supplied dicts that
        # match Playwright's SetCookieParam shape at runtime; cast for the typer.
        if auth.cookies:
            cookies = [auth.cookies] if isinstance(auth.cookies, dict) else auth.cookies
            context.add_cookies(cast("Any", cookies))
            return

        # Handle form-based auth
        page = page if page is not None else self.page
        assert page is not None
        if auth.auth_url and auth.username and auth.password:
            self.console.print_progress(f"Authenticating at {auth.auth_url}")
            self._rate_limiter.acquire(_hostname(auth.auth_url))
            page.goto(auth.auth_url)

            ctx = self.config.invocation_context
            if ctx == "cli":
                _selector_hint = (
                    'Tip: use --auth-file with a JSON file, e.g.:\n'
                    '  {\n'
                    '    "auth_url": "https://example.com/login",\n'
                    '    "username": "user@example.com",\n'
                    '    "password": "yourpassword",\n'
                    '    "username_selector": "input#email",\n'
                    '    "password_selector": "input#password",\n'
                    '    "submit_selector": "button[type=\'submit\']"\n'
                    '  }'
                )
            elif ctx == "web":
                _selector_hint = (
                    "Tip: expand the Advanced section under Authentication and "
                    "enter custom CSS selectors for the username, password, and submit fields."
                )
            else:
                _selector_hint = (
                    "Tip: set username_selector, password_selector, and submit_selector "
                    "on AuthConfig to target the correct form fields."
                )

            # Find and fill username
            username_selector = auth.username_selector or 'input[type="email"], input[type="text"][name*="user"], input[name*="email"], input#username, input#email'
            try:
                page.fill(username_selector, auth.username)
            except Exception as e:
                msg = f"Could not fill username field: {e}"
                if isinstance(e, PlaywrightTimeoutError) and not auth.username_selector:
                    msg += f"\n  {_selector_hint}"
                self.console.print_error(msg)

            # Find and fill password
            password_selector = auth.password_selector or 'input[type="password"]'
            try:
                page.fill(password_selector, auth.password)
            except Exception as e:
                msg = f"Could not fill password field: {e}"
                if isinstance(e, PlaywrightTimeoutError) and not auth.password_selector:
                    msg += f"\n  {_selector_hint}"
                self.console.print_error(msg)

            # Submit
            submit_selector = auth.submit_selector or 'button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("Sign in")'
            try:
                page.click(submit_selector)
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception as e:
                msg = f"Could not submit login form: {e}"
                if isinstance(e, PlaywrightTimeoutError) and not auth.submit_selector:
                    msg += f"\n  {_selector_hint}"
                self.console.print_error(msg)

    def _run_focused_mode(self):
        """Run tests on specific URLs only."""
        for url in self.config.urls:
            if self.stop_event and self.stop_event.is_set():
                break
            if url in self.visited_urls:
                continue

            self._test_page(url)
            self.visited_urls.add(url)

    def _run_explore_mode(self):
        """Explore and test pages, following links (sequential path)."""
        # Initialize with seed URLs
        self.urls_to_visit = list(self.config.urls)
        depth_map = {url: 0 for url in self.urls_to_visit}

        while self.urls_to_visit and len(self.visited_urls) < self.config.max_pages:
            if self.stop_event and self.stop_event.is_set():
                break
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
                new_links = self._discover_links(self.page, url)
                for link in new_links:
                    new_url = link['href']
                    if new_url not in self.visited_urls and new_url not in self.urls_to_visit:
                        if not self._should_skip_url(new_url, link.get('text', '')):
                            self.urls_to_visit.append(new_url)
                            depth_map[new_url] = current_depth + 1

    # -- concurrent (multi-worker) path --------------------------------------

    def _run_concurrent(self):
        """Test pages with ``config.workers`` cooperating worker threads.

        Each worker owns its own browser/context/page and pulls URLs from a
        shared thread-safe :class:`Frontier`. Authentication, when configured,
        is performed once on a bootstrap context and exported as a
        ``storage_state`` dict that seeds every worker context.
        """
        storage_state = self._bootstrap_auth()

        if self.config.mode == TestMode.FOCUSED:
            frontier = Frontier(
                max_pages=max(1, len(self.config.urls)),
                max_depth=0,  # focused mode never discovers links
                stop_event=self.stop_event,
            )
            num_workers = min(self.config.workers, max(1, len(self.config.urls)))
        else:
            frontier = Frontier(
                max_pages=self.config.max_pages,
                max_depth=self.config.max_depth,
                stop_event=self.stop_event,
            )
            num_workers = self.config.workers

        frontier.seed(self.config.urls, depth=0)

        threads = [
            threading.Thread(
                target=self._worker_loop,
                args=(frontier, storage_state),
                name=f"qa-worker-{i}",
                daemon=True,
            )
            for i in range(num_workers)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Surface collected recordings (one video per worker context).
        if self._recording_paths:
            self.session.recording_path = self._recording_paths[0]
            if len(self._recording_paths) > 1:
                self.session.config_summary["recording_paths"] = list(self._recording_paths)

    def _bootstrap_auth(self):
        """Authenticate once and return an exported ``storage_state`` (or None)."""
        if not self.config.auth:
            return None
        storage_state = None
        with self._factory()() as playwright:
            browser = self._launch_browser(playwright)
            context, page = self._new_context_page(browser)
            # Temporarily expose on self so _authenticate's fallbacks work.
            self.context, self.page = context, page
            try:
                self._authenticate(page=page, context=context)
                storage_state = context.storage_state()
            except Exception as exc:
                self.console.print_error(f"Bootstrap authentication failed: {exc}")
            finally:
                context.close()
                browser.close()
        return storage_state

    def _worker_loop(self, frontier: Frontier, storage_state):
        """Worker thread: own a browser, drain the frontier until exhausted."""
        if self._worker_thread_init is not None:
            try:
                self._worker_thread_init()
            except Exception as exc:
                self.console.print_error(f"worker_thread_init failed: {exc}")

        with self._factory()() as playwright:
            browser = self._launch_browser(playwright)
            context, page = self._new_context_page(browser, storage_state=storage_state)
            error_detector = ErrorDetector(page, self.config)
            if self.config.test_console_errors or self.config.test_network_errors:
                error_detector.attach_listeners()

            try:
                while True:
                    claimed = frontier.claim()
                    if claimed is None:
                        break
                    url, depth = claimed
                    try:
                        self._test_page_on(page, error_detector, url, self._page_indexer.next())
                        if self.config.mode == TestMode.EXPLORE and depth < self.config.max_depth:
                            links = self._discover_links(page, url)
                            new_urls = [
                                link['href'] for link in links
                                if not self._should_skip_url(link['href'], link.get('text', ''))
                            ]
                            frontier.add_links(new_urls, depth)
                    except Exception as exc:
                        self.console.print_error(f"Worker error on {url}: {exc}")
                    finally:
                        frontier.complete_one()
            finally:
                self._capture_recording(page)
                try:
                    context.close()
                    browser.close()
                except Exception:
                    pass

    def _capture_recording(self, page: Page) -> None:
        """Record a worker context's video path, if recording is enabled."""
        if not self.config.recording.enabled:
            return
        try:
            video = page.video
            if video:
                path = video.path()
                if path:
                    with self._session_lock:
                        self._recording_paths.append(str(path))
        except Exception:
            pass

    def _add_page_analysis(self, page_analysis: PageAnalysis) -> None:
        """Thread-safe aggregation of a page result into the session."""
        assert self.session is not None
        with self._session_lock:
            self.session.add_page_analysis(page_analysis)

    def _test_page(self, url: str):
        """Test a single page on the agent's shared browser (sequential path)."""
        assert self.page is not None
        assert self.error_detector is not None
        self._test_page_on(self.page, self.error_detector, url, self._page_indexer.next())

    def _test_page_on(self, page: Page, error_detector: "ErrorDetector", url: str, page_index: int):
        """Test a single page on the given page/error_detector.

        ``page_index`` is a globally unique, worker-safe counter used to name
        screenshots so concurrent workers never collide.
        """
        assert page is not None
        assert self.session is not None
        self.console.print_page_start(url)

        try:
            start_time = time.time()
            self._rate_limiter.acquire(_hostname(url))
            response = page.goto(url, wait_until="domcontentloaded")
            if response is None or response.status < 400:
                page.wait_for_load_state("networkidle", timeout=10000)
            load_time = (time.time() - start_time) * 1000
        except Exception as e:
            self.console.print_error(f"Error loading page: {e}")
            return

        # If we were redirected to the login page, re-authenticate once and continue.
        # Guard against infinite loops when credentials are wrong.
        auth = self.config.auth
        if auth and auth.auth_url and page.url != url:
            auth_path = urlparse(auth.auth_url).path.rstrip('/')
            current_path = urlparse(page.url).path.rstrip('/')
            if auth_path and current_path == auth_path:
                if self._reauth_count < 1:
                    self._reauth_count += 1
                    self.console.print_progress("Detected redirect to login page, re-authenticating...")
                    self._authenticate(page=page, context=page.context)
                else:
                    self.console.print_error(
                        "Re-authentication attempted but still redirected to login page — "
                        "check credentials. Skipping further re-auth attempts."
                    )
                    return

        # Fail fast on page-level HTTP errors — report one finding, skip all testers
        if response is not None and response.status >= 400:
            status = response.status
            severity = Severity.CRITICAL if status >= 500 else Severity.HIGH
            finding = Finding(
                title=f"HTTP {status} – page not available",
                description=f"Page returned HTTP {status} ({response.status_text}). No further tests were run.",
                category=FindingCategory.NETWORK_ERROR,
                severity=severity,
                url=url,
                metadata={"status": status, "status_text": response.status_text},
            )
            self.console.print_finding(finding)
            page_analysis = PageAnalysis(
                url=url,
                title=f"HTTP {status}",
                load_time_ms=load_time,
                interactive_elements=0,
                forms_count=0,
                links_count=0,
                images_count=0,
                findings=[finding],
            )
            self._add_page_analysis(page_analysis)
            if error_detector is not None:
                error_detector.console_messages = []
                error_detector.network_errors = []
                error_detector.js_errors = []
            return

        # Gather page info
        page_info = self._analyze_page_structure(page)

        page_analysis = PageAnalysis(
            url=url,
            title=page.title(),
            load_time_ms=load_time,
            interactive_elements=page_info["interactive_elements"],
            forms_count=page_info["forms_count"],
            links_count=page_info["links_count"],
            images_count=page_info["images_count"],
        )

        # Run testers
        all_findings: list[Finding] = []
        tester: BaseTester

        if self.config.test_keyboard:
            self.console.print_test_category("keyboard navigation")
            tester = KeyboardTester(page, self.config)
            findings = tester.run()
            all_findings.extend(findings)
            for f in findings:
                self.console.print_finding(f)

        if self.config.test_mouse:
            self.console.print_test_category("mouse interaction")
            tester = MouseTester(page, self.config)
            findings = tester.run()
            all_findings.extend(findings)
            for f in findings:
                self.console.print_finding(f)

        if self.config.test_forms:
            self.console.print_test_category("form handling")
            tester = FormTester(page, self.config)
            findings = tester.run()
            all_findings.extend(findings)
            for f in findings:
                self.console.print_finding(f)

        if self.config.test_accessibility:
            self.console.print_test_category("accessibility")
            tester = AccessibilityTester(page, self.config)
            findings = tester.run()
            all_findings.extend(findings)
            for f in findings:
                self.console.print_finding(f)

        if self.config.test_wcag_compliance:
            self.console.print_test_category("WCAG 2.1 AA compliance")
            tester = WCAGComplianceTester(page, self.config)
            findings = tester.run()
            all_findings.extend(findings)
            for f in findings:
                self.console.print_finding(f)

        if self.config.test_console_errors or self.config.test_network_errors:
            assert error_detector is not None
            self.console.print_test_category("error detection")
            findings = error_detector.run()
            all_findings.extend(findings)
            for f in findings:
                self.console.print_finding(f)

            error_detector.get_summary()
            page_analysis.console_errors = [
                m["text"] for m in error_detector.console_messages
                if m["type"] == "error"
            ]
            page_analysis.network_errors = error_detector.network_errors

        if self.test_plan and self.test_plan.custom_steps:
            self.console.print_test_category("custom AI steps")
            tester = CustomTester(page, self.config, self.test_plan)
            findings = tester.run()
            all_findings.extend(findings)
            for f in findings:
                self.console.print_finding(f)

        # Take screenshot if there were errors
        if all_findings and self.config.screenshots.on_error:
            screenshot_path = self._take_screenshot(page, f"page_{page_index}")
            if screenshot_path:
                for finding in all_findings:
                    if not finding.screenshot_path:
                        finding.screenshot_path = screenshot_path

        page_analysis.findings = all_findings
        self._add_page_analysis(page_analysis)

        # Reset error detector for next page
        if error_detector is not None:
            error_detector.console_messages = []
            error_detector.network_errors = []
            error_detector.js_errors = []

    def _analyze_page_structure(self, page: Page) -> dict:
        """Analyze the structure of the current page."""
        assert page is not None
        try:
            return dict(page.evaluate("""() => ({
                interactive_elements: document.querySelectorAll('a, button, input, select, textarea, [onclick], [role="button"]').length,
                forms_count: document.querySelectorAll('form').length,
                links_count: document.querySelectorAll('a[href]').length,
                images_count: document.querySelectorAll('img').length,
            })"""))
        except Exception:
            return {
                "interactive_elements": 0,
                "forms_count": 0,
                "links_count": 0,
                "images_count": 0,
            }

    _DESTRUCTIVE_URL_PATTERNS = [
        r'/logout', r'/log-out', r'/sign-out', r'/signout',
        r'/delete-account', r'/deactivate',
    ]
    _DESTRUCTIVE_LINK_TEXT = [
        'log out', 'logout', 'sign out', 'signout', 'delete account', 'deactivate account',
    ]

    def _discover_links(self, page: Page, current_url: str) -> list[dict]:
        """Discover links on the current page for exploration."""
        assert page is not None
        try:
            raw = page.evaluate("""() => {
                const links = document.querySelectorAll('a[href]');
                return Array.from(links).map(a => ({
                    href: a.href,
                    text: (a.textContent || '').trim().toLowerCase()
                })).filter(item =>
                    item.href &&
                    !item.href.startsWith('javascript:') &&
                    !item.href.startsWith('mailto:') &&
                    !item.href.startsWith('tel:') &&
                    !item.href.startsWith('#')
                );
            }""")

            seen: set[str] = set()
            valid_links: list[dict] = []
            current_domain = urlparse(current_url).netloc

            for item in raw:
                parsed = urlparse(item['href'])

                if self.config.same_domain_only and parsed.netloc != current_domain:
                    continue

                normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                if normalized.endswith('/'):
                    normalized = normalized[:-1]

                if normalized not in seen:
                    seen.add(normalized)
                    valid_links.append({'href': normalized, 'text': item['text']})

            return valid_links

        except Exception:
            return []

    def _should_skip_url(self, url: str, link_text: str = "") -> bool:
        """Check if URL should be skipped based on ignore patterns or destructive heuristics."""
        for pattern in self.config.ignore_patterns:
            if re.search(pattern, url):
                return True

        # Skip common non-page resources
        skip_extensions = ['.pdf', '.zip', '.jpg', '.png', '.gif', '.svg', '.css', '.js', '.ico']
        for ext in skip_extensions:
            if url.lower().endswith(ext):
                return True

        # Skip destructive/logout URLs — bypassed when AI instructions explicitly request it
        if not self._allow_destructive_urls:
            for pattern in self._DESTRUCTIVE_URL_PATTERNS:
                if re.search(pattern, url, re.IGNORECASE):
                    self.console.print_progress(f"Skipping destructive link: {url}")
                    return True

            if link_text and any(t in link_text for t in self._DESTRUCTIVE_LINK_TEXT):
                self.console.print_progress(f"Skipping logout link (text match): {url}")
                return True

        return False

    def _take_screenshot(self, page: Page, name: str) -> str | None:
        """Take a screenshot and return the path."""
        if not self.config.screenshots.enabled:
            return None

        assert page is not None
        os.makedirs(self.config.screenshots.output_dir, exist_ok=True)
        # Microsecond precision so concurrent workers never produce the same filename.
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{name}_{timestamp}.png"
        filepath = os.path.join(self.config.screenshots.output_dir, filename)

        try:
            page.screenshot(
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
            elif isinstance(reporter, PDFReporter):
                try:
                    filepath = reporter.generate(self.session)
                    self.console.print_progress(f"PDF report saved: {filepath}")
                except ImportError as e:
                    self.console.print_progress(f"PDF not available ({e}), falling back to Markdown")
                    fallback = MarkdownReporter(reporter.output_dir)
                    filepath = fallback.generate(self.session)
                    self.console.print_progress(f"Markdown report saved: {filepath}")
