"""Error detection module for console and network errors."""

from datetime import datetime

from playwright.sync_api import ConsoleMessage, Page, Request, Response

from ..config import TestConfig
from ..models import Finding, FindingCategory, Severity
from .base import BaseTester


class ErrorDetector(BaseTester):
    """Detects console errors, network failures, and JavaScript exceptions."""

    def __init__(self, page: Page, config: TestConfig):
        super().__init__(page, config)
        self.console_messages: list[dict] = []
        self.network_errors: list[dict] = []
        self.js_errors: list[dict] = []
        self._listeners_attached = False

    def attach_listeners(self):
        """Attach event listeners for console and network events."""
        if self._listeners_attached:
            return

        def on_console(msg: ConsoleMessage):
            self.console_messages.append({
                "type": msg.type,
                "text": msg.text,
                "location": str(msg.location),
                "timestamp": datetime.now().isoformat(),
            })

        def on_page_error(error):
            self.js_errors.append({
                "message": str(error),
                "timestamp": datetime.now().isoformat(),
            })

        def on_response(response: Response):
            if response.status >= 400:
                self.network_errors.append({
                    "url": response.url,
                    "status": response.status,
                    "status_text": response.status_text,
                    "timestamp": datetime.now().isoformat(),
                })

        def on_request_failed(request: Request):
            self.network_errors.append({
                "url": request.url,
                "failure": request.failure,
                "timestamp": datetime.now().isoformat(),
            })

        self.page.on("console", on_console)
        self.page.on("pageerror", on_page_error)
        self.page.on("response", on_response)
        self.page.on("requestfailed", on_request_failed)

        self._listeners_attached = True

    def run(self) -> list[Finding]:
        """Analyze collected errors and run additional checks."""
        self.findings = []

        self._analyze_console_errors()
        self._analyze_console_warnings()
        self._analyze_network_errors()
        self._analyze_js_errors()
        self._check_broken_images()
        self._check_broken_links()
        self._check_mixed_content()

        return self.findings

    def _analyze_console_errors(self):
        """Analyze console error messages."""
        errors = [m for m in self.console_messages if m["type"] == "error"]

        if len(errors) > 0:
            # Group similar errors
            error_groups = {}
            for error in errors:
                key = error["text"][:100]
                if key not in error_groups:
                    error_groups[key] = []
                error_groups[key].append(error)

            for error_text, occurrences in error_groups.items():
                severity = Severity.MEDIUM

                # Check for severe errors
                severe_patterns = ["uncaught", "undefined is not", "null is not", "cannot read property", "TypeError", "ReferenceError"]
                if any(p.lower() in error_text.lower() for p in severe_patterns):
                    severity = Severity.HIGH

                self.findings.append(Finding(
                    title="Console error detected",
                    description=error_text[:200],
                    category=FindingCategory.CONSOLE_ERROR,
                    severity=severity,
                    url=self.page.url,
                    raw_error=error_text,
                    metadata={
                        "count": len(occurrences),
                        "location": occurrences[0].get("location"),
                    },
                ))

    def _analyze_console_warnings(self):
        """Analyze console warnings for potential issues."""
        warnings = [m for m in self.console_messages if m["type"] == "warning"]

        # Only report significant warnings
        significant_patterns = [
            "deprecated",
            "security",
            "violation",
            "performance",
            "accessibility",
            "mixed content",
        ]

        significant_warnings = []
        for warning in warnings:
            text_lower = warning["text"].lower()
            if any(pattern in text_lower for pattern in significant_patterns):
                significant_warnings.append(warning)

        if len(significant_warnings) > 3:
            self.findings.append(Finding(
                title="Multiple console warnings",
                description=f"{len(significant_warnings)} significant warnings in console",
                category=FindingCategory.CONSOLE_ERROR,
                severity=Severity.LOW,
                url=self.page.url,
                metadata={"warnings": [w["text"][:100] for w in significant_warnings[:5]]},
            ))

    def _analyze_network_errors(self):
        """Analyze network errors."""
        if len(self.network_errors) == 0:
            return

        # Group by status code
        status_groups = {}
        for error in self.network_errors:
            status = error.get("status", "failed")
            if status not in status_groups:
                status_groups[status] = []
            status_groups[status].append(error)

        for status, errors in status_groups.items():
            severity = Severity.MEDIUM

            if status == 404:
                severity = Severity.MEDIUM
                title = "404 Not Found errors"
            elif status == 500 or status == 502 or status == 503:
                severity = Severity.HIGH
                title = f"Server error ({status})"
            elif status == 403:
                severity = Severity.MEDIUM
                title = "403 Forbidden errors"
            elif status == "failed":
                severity = Severity.HIGH
                title = "Network request failed"
            else:
                title = f"HTTP {status} errors"

            self.findings.append(Finding(
                title=title,
                description=f"{len(errors)} requests returned {status}",
                category=FindingCategory.NETWORK_ERROR,
                severity=severity,
                url=self.page.url,
                metadata={
                    "count": len(errors),
                    "urls": [e["url"][:100] for e in errors[:5]],
                },
            ))

    def _analyze_js_errors(self):
        """Analyze JavaScript exceptions."""
        for error in self.js_errors:
            self.findings.append(Finding(
                title="JavaScript exception",
                description=error["message"][:200],
                category=FindingCategory.CONSOLE_ERROR,
                severity=Severity.HIGH,
                url=self.page.url,
                raw_error=error["message"],
                timestamp=datetime.fromisoformat(error["timestamp"]),
            ))

    def _check_broken_images(self):
        """Check for broken images."""
        try:
            broken_images = self.page.evaluate("""() => {
                const images = document.querySelectorAll('img');
                const broken = [];

                images.forEach(img => {
                    // Check if image failed to load
                    if (!img.complete || img.naturalWidth === 0) {
                        broken.push({
                            src: img.src?.slice(-100),
                            alt: img.alt,
                            visible: img.offsetParent !== null
                        });
                    }
                });

                return broken;
            }""")

            visible_broken = [img for img in broken_images if img.get("visible")]

            if len(visible_broken) > 0:
                self.findings.append(Finding(
                    title="Broken images detected",
                    description=f"{len(visible_broken)} visible images failed to load",
                    category=FindingCategory.NETWORK_ERROR,
                    severity=Severity.HIGH,
                    url=self.page.url,
                    expected_behavior="All images should load successfully",
                    actual_behavior="Some images show as broken",
                    metadata={"images": visible_broken[:5]},
                ))

        except Exception:
            pass

    def _check_broken_links(self):
        """Identify potentially broken internal links (non-navigating check)."""
        try:
            links_data = self.page.evaluate("""() => {
                const links = document.querySelectorAll('a[href]');
                const suspicious = [];

                links.forEach(link => {
                    const href = link.getAttribute('href');

                    // Check for obviously broken patterns
                    if (href === '#' || href === '') {
                        if (link.onclick || link.getAttribute('onclick')) {
                            return; // Has JS handler, probably intentional
                        }
                        suspicious.push({
                            href,
                            text: link.textContent?.slice(0, 30),
                            issue: 'empty_href'
                        });
                    } else if (href === 'javascript:void(0)' || href === 'javascript:;') {
                        if (!link.onclick && !link.getAttribute('onclick')) {
                            suspicious.push({
                                href,
                                text: link.textContent?.slice(0, 30),
                                issue: 'javascript_void'
                            });
                        }
                    } else if (href.startsWith('#') && href.length > 1) {
                        // Check if anchor target exists
                        const targetId = href.slice(1);
                        if (!document.getElementById(targetId)) {
                            suspicious.push({
                                href,
                                text: link.textContent?.slice(0, 30),
                                issue: 'missing_anchor'
                            });
                        }
                    }
                });

                return suspicious;
            }""")

            empty_links = [lnk for lnk in links_data if lnk.get("issue") == "empty_href"]
            missing_anchors = [lnk for lnk in links_data if lnk.get("issue") == "missing_anchor"]

            if len(empty_links) > 0:
                self.findings.append(Finding(
                    title="Empty href links",
                    description=f"{len(empty_links)} links have empty or '#' href without handlers",
                    category=FindingCategory.UNEXPECTED_BEHAVIOR,
                    severity=Severity.LOW,
                    url=self.page.url,
                    expected_behavior="Links should have valid destinations or onclick handlers",
                    actual_behavior="Links go nowhere when clicked",
                    metadata={"links": empty_links[:5]},
                ))

            if len(missing_anchors) > 0:
                self.findings.append(Finding(
                    title="Broken anchor links",
                    description=f"{len(missing_anchors)} anchor links point to non-existent IDs",
                    category=FindingCategory.NETWORK_ERROR,
                    severity=Severity.MEDIUM,
                    url=self.page.url,
                    expected_behavior="Anchor links should point to existing elements",
                    actual_behavior="Target elements not found",
                    metadata={"links": missing_anchors[:5]},
                ))

        except Exception:
            pass

    def _check_mixed_content(self):
        """Check for mixed content (HTTP on HTTPS page)."""
        try:
            if not self.page.url.startswith("https://"):
                return

            mixed_content = self.page.evaluate("""() => {
                const mixed = [];

                // Check images
                document.querySelectorAll('img[src^="http:"]').forEach(el => {
                    mixed.push({ type: 'image', url: el.src });
                });

                // Check scripts
                document.querySelectorAll('script[src^="http:"]').forEach(el => {
                    mixed.push({ type: 'script', url: el.src });
                });

                // Check stylesheets
                document.querySelectorAll('link[href^="http:"]').forEach(el => {
                    if (el.rel === 'stylesheet') {
                        mixed.push({ type: 'stylesheet', url: el.href });
                    }
                });

                // Check iframes
                document.querySelectorAll('iframe[src^="http:"]').forEach(el => {
                    mixed.push({ type: 'iframe', url: el.src });
                });

                return mixed;
            }""")

            if len(mixed_content) > 0:
                active_mixed = [m for m in mixed_content if m["type"] in ["script", "stylesheet"]]
                passive_mixed = [m for m in mixed_content if m["type"] in ["image", "iframe"]]

                if len(active_mixed) > 0:
                    self.findings.append(Finding(
                        title="Active mixed content",
                        description=f"{len(active_mixed)} scripts/stylesheets loaded over HTTP",
                        category=FindingCategory.NETWORK_ERROR,
                        severity=Severity.HIGH,
                        url=self.page.url,
                        expected_behavior="All resources should be loaded over HTTPS",
                        actual_behavior="Active content loaded over insecure HTTP",
                        metadata={"resources": active_mixed[:5]},
                    ))

                if len(passive_mixed) > 0:
                    self.findings.append(Finding(
                        title="Passive mixed content",
                        description=f"{len(passive_mixed)} images/iframes loaded over HTTP",
                        category=FindingCategory.NETWORK_ERROR,
                        severity=Severity.MEDIUM,
                        url=self.page.url,
                        expected_behavior="All resources should be loaded over HTTPS",
                        actual_behavior="Passive content loaded over insecure HTTP",
                        metadata={"resources": passive_mixed[:5]},
                    ))

        except Exception:
            pass

    def get_summary(self) -> dict:
        """Get summary of collected errors."""
        return {
            "console_errors": len([m for m in self.console_messages if m["type"] == "error"]),
            "console_warnings": len([m for m in self.console_messages if m["type"] == "warning"]),
            "network_errors": len(self.network_errors),
            "js_exceptions": len(self.js_errors),
        }
