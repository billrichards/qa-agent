"""Detailed WCAG 2.1 AA compliance testing module.

Covers WCAG criteria not already tested by AccessibilityTester, which handles:
  - 1.1.1 (images alt text), 1.3.1 (headings/landmarks partial), 1.4.3 (color contrast),
  - 2.4.1 (skip links), 2.4.4 (link text), 3.1.1 (lang attribute),
  - 4.1.2 (ARIA roles/references partial)

This module adds coverage for the remaining WCAG 2.1 AA criteria.
"""

from playwright.sync_api import Page

from .base import BaseTester
from ..models import Finding, FindingCategory, Severity
from ..config import TestConfig


# ARIA roles and their required owned properties
_ARIA_REQUIRED_PROPS: dict[str, list[str]] = {
    "checkbox": ["aria-checked"],
    "combobox": ["aria-expanded"],
    "listbox": [],
    "option": [],
    "radio": ["aria-checked"],
    "scrollbar": ["aria-valuenow", "aria-valuemin", "aria-valuemax", "aria-controls"],
    "slider": ["aria-valuenow", "aria-valuemin", "aria-valuemax"],
    "spinbutton": ["aria-valuenow"],
    "switch": ["aria-checked"],
    "tab": [],
    "treeitem": [],
}

# Required parent roles (child role -> acceptable parent roles)
_ARIA_REQUIRED_PARENTS: dict[str, list[str]] = {
    "tab": ["tablist"],
    "option": ["listbox", "combobox"],
    "menuitem": ["menu", "menubar"],
    "menuitemcheckbox": ["menu", "menubar"],
    "menuitemradio": ["menu", "menubar"],
    "treeitem": ["tree", "group"],
    "row": ["table", "grid", "treegrid", "rowgroup"],
    "cell": ["row"],
    "gridcell": ["row"],
    "columnheader": ["row"],
    "rowheader": ["row"],
}

# Semantic HTML elements and the ARIA role they implicitly have (redundant to add)
_REDUNDANT_ROLES: dict[str, str] = {
    "button": "button",
    "a": "link",
    "nav": "navigation",
    "header": "banner",
    "footer": "contentinfo",
    "main": "main",
    "aside": "complementary",
    "section": "region",
    "form": "form",
    "h1": "heading",
    "h2": "heading",
    "h3": "heading",
    "h4": "heading",
    "h5": "heading",
    "h6": "heading",
    "ul": "list",
    "ol": "list",
    "li": "listitem",
    "table": "table",
    "tr": "row",
    "th": "columnheader",
    "td": "cell",
    "img": "img",
    "input[type=checkbox]": "checkbox",
    "input[type=radio]": "radio",
}


class WCAGComplianceTester(BaseTester):
    """Detailed WCAG 2.1 AA compliance testing, covering criteria not in AccessibilityTester."""

    def __init__(self, page: Page, config: TestConfig):
        super().__init__(page, config)

    def run(self) -> list[Finding]:
        self.findings = []

        # Perceivable (WCAG 1.x)
        self._test_non_text_content()        # 1.1.1
        self._test_info_and_relationships()  # 1.3.1
        self._test_meaningful_sequence()     # 1.3.2
        self._test_identify_input_purpose()  # 1.3.5
        self._test_use_of_color()            # 1.4.1
        self._test_non_text_contrast()       # 1.4.11
        self._test_content_on_hover_focus()  # 1.4.13

        # Operable (WCAG 2.x)
        self._test_page_titled()             # 2.4.2
        self._test_focus_visible()           # 2.4.7
        self._test_label_in_name()           # 2.5.3
        self._test_target_size()             # 2.5.5

        # Understandable (WCAG 3.x)
        self._test_language_of_parts()       # 3.1.2
        self._test_form_labels()             # 3.3.2
        self._test_error_identification()    # 3.3.1

        # Robust (WCAG 4.x)
        self._test_parsing_duplicate_ids()   # 4.1.1
        self._test_name_role_value()         # 4.1.2
        self._test_status_messages()         # 4.1.3

        # ARIA pattern checks
        self._test_aria_required_properties()
        self._test_aria_widget_patterns()
        self._test_aria_parent_child()
        self._test_redundant_aria_roles()

        return self.findings

    def _add_finding(self, title: str, description: str, severity: Severity,
                     wcag_criterion: str, wcag_level: str = "AA", **kwargs):
        principle_map = {
            "1": "Perceivable", "2": "Operable",
            "3": "Understandable", "4": "Robust",
        }
        principle = principle_map.get(wcag_criterion.split(".")[0], "")
        extra_meta = kwargs.pop("metadata", {}) or {}
        self.findings.append(Finding(
            title=title,
            description=description,
            category=FindingCategory.ACCESSIBILITY,
            severity=severity,
            url=self.page.url,
            metadata={
                "wcag_criterion": wcag_criterion,
                "wcag_level": wcag_level,
                "wcag_principle": principle,
                **extra_meta,
            },
            **kwargs,
        ))

    # -------------------------------------------------------------------------
    # PERCEIVABLE (1.x)
    # -------------------------------------------------------------------------

    def _test_non_text_content(self):
        """WCAG 1.1.1 — Non-text content beyond images (SVG, canvas, video, icon fonts)."""
        try:
            issues = self.page.evaluate("""() => {
                const issues = [];

                // SVG elements without accessible name
                document.querySelectorAll('svg').forEach(svg => {
                    if (svg.getAttribute('aria-hidden') === 'true') return;
                    const hasTitle = !!svg.querySelector('title');
                    const hasAriaLabel = svg.hasAttribute('aria-label') || svg.hasAttribute('aria-labelledby');
                    const role = svg.getAttribute('role');
                    if (!hasTitle && !hasAriaLabel && role !== 'presentation' && role !== 'none') {
                        issues.push({ type: 'svg_no_name', element: svg.outerHTML.slice(0, 80) });
                    }
                });

                // Canvas without fallback or label
                document.querySelectorAll('canvas').forEach(canvas => {
                    if (canvas.getAttribute('aria-hidden') === 'true') return;
                    const hasFallback = canvas.textContent?.trim().length > 0;
                    const hasLabel = canvas.hasAttribute('aria-label') || canvas.hasAttribute('aria-labelledby');
                    if (!hasFallback && !hasLabel) {
                        issues.push({ type: 'canvas_no_fallback', id: canvas.id || '(no id)' });
                    }
                });

                // Video/audio without captions track
                document.querySelectorAll('video, audio').forEach(media => {
                    const hasTrack = media.querySelector('track[kind="captions"], track[kind="subtitles"]');
                    if (!hasTrack) {
                        issues.push({ type: 'media_no_track', tag: media.tagName.toLowerCase(), src: media.src?.slice(-50) || '(no src)' });
                    }
                });

                // Icon fonts: <i> or <span> elements with common icon class patterns but no accessible name
                const iconPattern = /^(fa|icon|glyphicon|bi|material-icons|mdi)/;
                document.querySelectorAll('i, span').forEach(el => {
                    if (el.getAttribute('aria-hidden') === 'true') return;
                    const classes = Array.from(el.classList).join(' ');
                    if (iconPattern.test(classes) || classes.includes('-icon') || classes.includes('icon-')) {
                        const hasLabel = el.hasAttribute('aria-label') || el.hasAttribute('aria-labelledby') || el.title;
                        const hasText = el.textContent?.trim().length > 0;
                        if (!hasLabel && !hasText) {
                            issues.push({ type: 'icon_no_name', classes });
                        }
                    }
                });

                return issues;
            }""")

            svg_issues = [i for i in issues if i['type'] == 'svg_no_name']
            canvas_issues = [i for i in issues if i['type'] == 'canvas_no_fallback']
            media_issues = [i for i in issues if i['type'] == 'media_no_track']
            icon_issues = [i for i in issues if i['type'] == 'icon_no_name']

            if svg_issues:
                self._add_finding(
                    title="SVG elements missing accessible name",
                    description=f"{len(svg_issues)} SVG(s) lack a <title> element or aria-label",
                    severity=Severity.MEDIUM,
                    wcag_criterion="1.1.1",
                    expected_behavior="Meaningful SVGs need a <title> or aria-label for screen readers",
                    actual_behavior="SVG found without accessible name",
                    metadata={"elements": svg_issues[:5]},
                )
            if canvas_issues:
                self._add_finding(
                    title="Canvas elements missing fallback content",
                    description=f"{len(canvas_issues)} <canvas> element(s) have no fallback text or aria-label",
                    severity=Severity.MEDIUM,
                    wcag_criterion="1.1.1",
                    expected_behavior="Canvas elements should contain fallback content or aria-label",
                    actual_behavior="Canvas found without accessible fallback",
                    metadata={"elements": canvas_issues[:5]},
                )
            if media_issues:
                self._add_finding(
                    title="Video/audio missing captions track",
                    description=f"{len(media_issues)} media element(s) have no <track kind='captions'>",
                    severity=Severity.HIGH,
                    wcag_criterion="1.1.1",
                    expected_behavior="Video and audio must provide captions or text alternatives",
                    actual_behavior="Media element found without captions track",
                    metadata={"elements": media_issues[:5]},
                )
            if icon_issues:
                self._add_finding(
                    title="Icon elements missing accessible name",
                    description=f"{len(icon_issues)} icon element(s) are not hidden and have no accessible name",
                    severity=Severity.MEDIUM,
                    wcag_criterion="1.1.1",
                    expected_behavior="Decorative icons should use aria-hidden='true'; meaningful icons need aria-label",
                    actual_behavior="Icon element found without aria-hidden or accessible name",
                    metadata={"elements": icon_issues[:5]},
                )
        except Exception:
            pass

    def _test_info_and_relationships(self):
        """WCAG 1.3.1 — Info and relationships: tables, form groups."""
        try:
            issues = self.page.evaluate("""() => {
                const issues = [];

                // Data tables without th, scope, or caption
                document.querySelectorAll('table').forEach(table => {
                    const hasTh = !!table.querySelector('th');
                    const hasCaption = !!table.querySelector('caption');
                    const hasScope = !!table.querySelector('[scope]');
                    const rowCount = table.querySelectorAll('tr').length;
                    if (rowCount > 1 && !hasTh && !hasCaption && !hasScope) {
                        issues.push({ type: 'table_no_headers', rows: rowCount });
                    }
                });

                // Radio/checkbox groups not wrapped in fieldset+legend
                const groups = {};
                document.querySelectorAll('input[type="radio"], input[type="checkbox"]').forEach(input => {
                    const name = input.getAttribute('name');
                    if (!name) return;
                    if (!groups[name]) groups[name] = [];
                    groups[name].push(input);
                });

                Object.entries(groups).forEach(([name, inputs]) => {
                    if (inputs.length < 2) return;
                    const inFieldset = inputs.every(i => !!i.closest('fieldset'));
                    if (!inFieldset) {
                        issues.push({ type: 'group_no_fieldset', name, count: inputs.length });
                    }
                });

                return issues;
            }""")

            table_issues = [i for i in issues if i['type'] == 'table_no_headers']
            group_issues = [i for i in issues if i['type'] == 'group_no_fieldset']

            if table_issues:
                self._add_finding(
                    title="Data tables missing header markup",
                    description=f"{len(table_issues)} table(s) lack <th>, scope, or <caption>",
                    severity=Severity.MEDIUM,
                    wcag_criterion="1.3.1",
                    expected_behavior="Data tables must use <th> with scope or <caption> to convey structure",
                    actual_behavior="Table found without header markup",
                    metadata={"tables": table_issues[:5]},
                )
            if group_issues:
                self._add_finding(
                    title="Radio/checkbox group not in fieldset",
                    description=f"{len(group_issues)} group(s) of related inputs lack <fieldset>/<legend>",
                    severity=Severity.MEDIUM,
                    wcag_criterion="1.3.1",
                    expected_behavior="Related radio buttons and checkboxes should be grouped in <fieldset> with <legend>",
                    actual_behavior="Input group found outside fieldset",
                    metadata={"groups": group_issues[:5]},
                )
        except Exception:
            pass

    def _test_meaningful_sequence(self):
        """WCAG 1.3.2 — CSS order/reverse-direction may alter reading sequence."""
        try:
            reordered = self.page.evaluate("""() => {
                const issues = [];
                document.querySelectorAll('*').forEach(el => {
                    const style = window.getComputedStyle(el);
                    const order = parseInt(style.order || '0', 10);
                    const flexDir = style.flexDirection || '';
                    if (order !== 0) {
                        issues.push({ element: el.tagName.toLowerCase(), order, text: el.textContent?.slice(0, 40) });
                    } else if (flexDir.includes('reverse') && el.children.length > 1) {
                        issues.push({ element: el.tagName.toLowerCase(), flexDir, childCount: el.children.length });
                    }
                });
                return issues.slice(0, 20);
            }""")

            if reordered:
                self._add_finding(
                    title="CSS visual order differs from DOM order",
                    description=f"{len(reordered)} element(s) use CSS order or flex-direction: reverse, which may break reading sequence",
                    severity=Severity.LOW,
                    wcag_criterion="1.3.2",
                    expected_behavior="Content reading order should match DOM order",
                    actual_behavior="CSS reordering detected — manual review recommended",
                    metadata={"elements": reordered[:5]},
                )
        except Exception:
            pass

    def _test_identify_input_purpose(self):
        """WCAG 1.3.5 — Personal info inputs should have autocomplete attributes."""
        try:
            missing = self.page.evaluate("""() => {
                const patterns = {
                    name: ['name', 'fullname', 'full-name', 'full_name'],
                    email: ['email', 'e-mail'],
                    tel: ['phone', 'telephone', 'tel', 'mobile'],
                    'street-address': ['address', 'street', 'addr'],
                    'postal-code': ['zip', 'postal', 'postcode'],
                    'cc-number': ['card', 'credit', 'cardnumber', 'card-number'],
                };

                const missing = [];
                document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"])').forEach(input => {
                    if (input.hasAttribute('autocomplete')) return;
                    const idName = ((input.id || '') + ' ' + (input.name || '') + ' ' + (input.placeholder || '')).toLowerCase();
                    for (const [autocompleteVal, terms] of Object.entries(patterns)) {
                        if (terms.some(t => idName.includes(t))) {
                            missing.push({ type: input.type || 'text', id: input.id, name: input.name, suggestedAutocomplete: autocompleteVal });
                            break;
                        }
                    }
                });
                return missing;
            }""")

            if missing:
                self._add_finding(
                    title="Personal info inputs missing autocomplete",
                    description=f"{len(missing)} input(s) collecting personal data lack autocomplete attribute",
                    severity=Severity.MEDIUM,
                    wcag_criterion="1.3.5",
                    expected_behavior="Inputs for name, email, phone, address should have autocomplete attribute",
                    actual_behavior="Personal info inputs found without autocomplete",
                    metadata={"inputs": missing[:5]},
                )
        except Exception:
            pass

    def _test_use_of_color(self):
        """WCAG 1.4.1 — Links in body text distinguished by color alone."""
        try:
            issues = self.page.evaluate("""() => {
                const issues = [];
                document.querySelectorAll('p a, li a, td a').forEach(link => {
                    if (!link.offsetParent) return;
                    const parent = link.parentElement;
                    if (!parent) return;

                    const linkStyle = window.getComputedStyle(link);
                    const parentStyle = window.getComputedStyle(parent);

                    const linkDeco = linkStyle.textDecoration || '';
                    const hasUnderline = linkDeco.includes('underline');
                    const linkWeight = parseInt(linkStyle.fontWeight || '400', 10);
                    const parentWeight = parseInt(parentStyle.fontWeight || '400', 10);
                    const weightDiff = Math.abs(linkWeight - parentWeight) >= 200;
                    const hasBorder = linkStyle.borderBottomWidth !== '0px' && linkStyle.borderBottomStyle !== 'none';

                    if (!hasUnderline && !weightDiff && !hasBorder) {
                        issues.push({
                            text: link.textContent?.slice(0, 40),
                            href: link.href?.slice(-50),
                            decoration: linkDeco,
                        });
                    }
                });
                return issues.slice(0, 20);
            }""")

            if len(issues) > 3:
                self._add_finding(
                    title="Links distinguished by color only",
                    description=f"{len(issues)} link(s) in body text have no underline or other non-color indicator",
                    severity=Severity.MEDIUM,
                    wcag_criterion="1.4.1",
                    expected_behavior="Links should be distinguishable from surrounding text without relying on color alone",
                    actual_behavior="Links found with no underline, border, or font-weight difference",
                    metadata={"links": issues[:5]},
                )
        except Exception:
            pass

    def _test_non_text_contrast(self):
        """WCAG 1.4.11 — UI component contrast (input borders, focus indicators)."""
        try:
            low_contrast = self.page.evaluate("""() => {
                const luminance = (rgb) => {
                    const [r, g, b] = rgb.map(c => {
                        c = c / 255;
                        return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
                    });
                    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
                };
                const parseRGB = (c) => {
                    const m = c.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                    return m ? [parseInt(m[1]), parseInt(m[2]), parseInt(m[3])] : null;
                };
                const ratio = (fg, bg) => {
                    const l1 = luminance(fg), l2 = luminance(bg);
                    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
                };

                const issues = [];
                const inputs = document.querySelectorAll('input:not([type="hidden"]), select, textarea');
                Array.from(inputs).slice(0, 20).forEach(input => {
                    if (!input.offsetParent) return;
                    const style = window.getComputedStyle(input);
                    const borderColor = style.borderColor || style.borderTopColor;
                    const bgColor = style.backgroundColor;
                    const fg = parseRGB(borderColor);
                    const bg = parseRGB(bgColor || 'rgb(255,255,255)');
                    if (fg && bg) {
                        const r = ratio(fg, bg);
                        if (r < 3) {
                            issues.push({ element: input.tagName.toLowerCase(), type: input.type, ratio: r.toFixed(2), borderColor });
                        }
                    }
                });
                return issues;
            }""")

            if low_contrast:
                self._add_finding(
                    title="Form input borders have low contrast",
                    description=f"{len(low_contrast)} input(s) have border contrast below 3:1 ratio",
                    severity=Severity.MEDIUM,
                    wcag_criterion="1.4.11",
                    expected_behavior="UI component boundaries (e.g., input borders) need at least 3:1 contrast ratio",
                    actual_behavior="Input borders found with insufficient contrast",
                    metadata={"elements": low_contrast[:5]},
                )
        except Exception:
            pass

    def _test_content_on_hover_focus(self):
        """WCAG 1.4.13 — Native title tooltips are not dismissible or hoverable."""
        try:
            title_elements = self.page.evaluate("""() => {
                const els = [];
                document.querySelectorAll('[title]').forEach(el => {
                    const title = el.getAttribute('title');
                    if (!title || title.trim().length === 0) return;
                    if (el.tagName.toLowerCase() === 'html') return;
                    // Exclude elements whose title duplicates the visible label (common pattern, lower concern)
                    const visibleText = el.textContent?.trim() || '';
                    if (title === visibleText) return;
                    els.push({ tag: el.tagName.toLowerCase(), title: title.slice(0, 60) });
                });
                return els.slice(0, 20);
            }""")

            if len(title_elements) > 2:
                self._add_finding(
                    title="Native title tooltips used for content",
                    description=f"{len(title_elements)} element(s) use the title attribute for tooltip content",
                    severity=Severity.LOW,
                    wcag_criterion="1.4.13",
                    expected_behavior="Tooltip content must be dismissible, hoverable, and persistent; native title tooltips are not",
                    actual_behavior="title attribute used to convey content that may not be accessible",
                    metadata={"elements": title_elements[:5]},
                )
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # OPERABLE (2.x)
    # -------------------------------------------------------------------------

    def _test_page_titled(self):
        """WCAG 2.4.2 — Pages must have descriptive titles."""
        try:
            title_info = self.page.evaluate("""() => ({
                title: document.title,
                hasTitle: !!document.title && document.title.trim().length > 0,
            })""")

            boilerplate = {"untitled", "untitled document", "document", "page", "home"}
            title_val = (title_info.get("title") or "").strip().lower()

            if not title_info.get("hasTitle"):
                self._add_finding(
                    title="Page has no title",
                    description="The <title> element is missing or empty",
                    severity=Severity.HIGH,
                    wcag_criterion="2.4.2",
                    expected_behavior="Each page must have a descriptive <title>",
                    actual_behavior="No page title found",
                )
            elif title_val in boilerplate:
                self._add_finding(
                    title="Page title is generic/boilerplate",
                    description=f"Page title '{title_info['title']}' is not descriptive",
                    severity=Severity.MEDIUM,
                    wcag_criterion="2.4.2",
                    expected_behavior="Page title should describe the page's topic or purpose",
                    actual_behavior=f"Generic title used: '{title_info['title']}'",
                )
        except Exception:
            pass

    def _test_focus_visible(self):
        """WCAG 2.4.7 — Focus indicator must be visible on interactive elements."""
        try:
            elements = self.page.locator(
                'a:visible, button:visible, input:visible:not([type="hidden"]), select:visible, textarea:visible, [tabindex]:visible'
            )
            count = min(elements.count(), 15)
            invisible_focus = []

            for i in range(count):
                el = elements.nth(i)
                try:
                    result = el.evaluate("""el => {
                        const before = window.getComputedStyle(el);
                        el.focus();
                        const after = window.getComputedStyle(el);

                        const outlineNone = after.outlineStyle === 'none' || after.outlineWidth === '0px';
                        const boxShadowSame = before.boxShadow === after.boxShadow;
                        const borderSame = before.borderColor === after.borderColor;
                        const bgSame = before.backgroundColor === after.backgroundColor;

                        const noVisibleFocusStyle = outlineNone && boxShadowSame && borderSame && bgSame;
                        el.blur();

                        return {
                            noFocus: noVisibleFocusStyle,
                            tag: el.tagName.toLowerCase(),
                            type: el.type || '',
                            text: el.textContent?.slice(0, 30) || el.value?.slice(0, 30) || '',
                            outline: after.outline,
                        };
                    }""")
                    if result and result.get("noFocus"):
                        invisible_focus.append(result)
                except Exception:
                    continue

            if invisible_focus:
                self._add_finding(
                    title="Focus indicator not visible",
                    description=f"{len(invisible_focus)} interactive element(s) show no visible focus style",
                    severity=Severity.HIGH,
                    wcag_criterion="2.4.7",
                    expected_behavior="All interactive elements must have a visible focus indicator",
                    actual_behavior="Elements found with no outline, box-shadow, border, or background change on focus",
                    metadata={"elements": invisible_focus[:5]},
                )
        except Exception:
            pass

    def _test_label_in_name(self):
        """WCAG 2.5.3 — Accessible name must contain visible label text."""
        try:
            mismatches = self.page.evaluate("""() => {
                const issues = [];
                document.querySelectorAll('[aria-label]').forEach(el => {
                    if (!el.offsetParent) return;
                    const ariaLabel = (el.getAttribute('aria-label') || '').trim().toLowerCase();
                    const visibleText = (el.textContent || '').trim().toLowerCase();
                    if (visibleText.length > 0 && !ariaLabel.includes(visibleText.slice(0, 20))) {
                        issues.push({
                            tag: el.tagName.toLowerCase(),
                            visibleText: visibleText.slice(0, 40),
                            ariaLabel: el.getAttribute('aria-label')?.slice(0, 60),
                        });
                    }
                });
                return issues.slice(0, 20);
            }""")

            if mismatches:
                self._add_finding(
                    title="Accessible name does not include visible label",
                    description=f"{len(mismatches)} element(s) have aria-label that doesn't contain the visible text",
                    severity=Severity.MEDIUM,
                    wcag_criterion="2.5.3",
                    expected_behavior="The accessible name should include the visible text label so speech input users can activate the element",
                    actual_behavior="aria-label found that differs from visible text content",
                    metadata={"elements": mismatches[:5]},
                )
        except Exception:
            pass

    def _test_target_size(self):
        """WCAG 2.5.5 / 2.5.8 — Interactive elements should meet minimum target size."""
        try:
            small_targets = self.page.evaluate("""() => {
                const issues = [];
                const selectors = 'button:not([disabled]), [role="button"], [role="link"], input[type="checkbox"], input[type="radio"]';
                document.querySelectorAll(selectors).forEach(el => {
                    if (!el.offsetParent) return;
                    const rect = el.getBoundingClientRect();
                    if (rect.width < 24 || rect.height < 24) {
                        issues.push({
                            tag: el.tagName.toLowerCase(),
                            role: el.getAttribute('role') || '',
                            text: el.textContent?.slice(0, 30) || '',
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                        });
                    }
                });
                return issues.slice(0, 20);
            }""")

            if small_targets:
                self._add_finding(
                    title="Interactive elements below minimum target size",
                    description=f"{len(small_targets)} control(s) are smaller than 24×24px",
                    severity=Severity.MEDIUM,
                    wcag_criterion="2.5.5",
                    expected_behavior="Interactive controls should be at least 24×24px (ideally 44×44px) for easy activation",
                    actual_behavior="Controls found below minimum target size",
                    metadata={"elements": small_targets[:5]},
                )
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # UNDERSTANDABLE (3.x)
    # -------------------------------------------------------------------------

    def _test_language_of_parts(self):
        """WCAG 3.1.2 — Content in a different language should have a lang attribute."""
        try:
            result = self.page.evaluate("""() => {
                const pageLang = (document.documentElement.lang || '').split('-')[0].toLowerCase();
                if (!pageLang) return [];

                const issues = [];
                // Heuristic: detect CJK characters on non-CJK pages or Latin on CJK pages
                const cjkRegex = /[\u3000-\u9fff\uac00-\ud7af\uf900-\ufaff]/;
                const latinRegex = /[a-zA-Z]{5,}/;
                const cjkLangs = ['zh', 'ja', 'ko'];

                document.querySelectorAll('p, li, td, span, div').forEach(el => {
                    if (!el.offsetParent) return;
                    if (el.closest('[lang]') !== document.documentElement) return; // already has lang
                    const text = el.textContent?.trim() || '';
                    if (text.length < 10) return;

                    const isCJKPage = cjkLangs.includes(pageLang);
                    if (!isCJKPage && cjkRegex.test(text)) {
                        issues.push({ tag: el.tagName.toLowerCase(), sample: text.slice(0, 40) });
                    } else if (isCJKPage && !cjkRegex.test(text) && latinRegex.test(text) && text.length > 30) {
                        issues.push({ tag: el.tagName.toLowerCase(), sample: text.slice(0, 40) });
                    }
                });
                return issues.slice(0, 10);
            }""")

            if result:
                self._add_finding(
                    title="Text in different language missing lang attribute",
                    description=f"{len(result)} element(s) appear to contain text in a different language without a lang attribute",
                    severity=Severity.LOW,
                    wcag_criterion="3.1.2",
                    expected_behavior="Content in a different language should have lang attribute on the containing element",
                    actual_behavior="Multi-language content found without lang attribute",
                    metadata={"elements": result[:5]},
                )
        except Exception:
            pass

    def _test_form_labels(self):
        """WCAG 3.3.2 — All form inputs must have an accessible label."""
        try:
            unlabeled = self.page.evaluate("""() => {
                const excluded = ['hidden', 'submit', 'button', 'reset', 'image'];
                const issues = [];

                document.querySelectorAll('input, select, textarea').forEach(input => {
                    if (!input.offsetParent) return;
                    if (excluded.includes(input.type)) return;

                    // Check for associated label via for/id
                    const id = input.id;
                    const hasLabelFor = id && !!document.querySelector(`label[for="${id}"]`);
                    // Check for wrapping label
                    const hasWrapLabel = !!input.closest('label');
                    // Check for aria-label / aria-labelledby / title
                    const hasAriaLabel = input.hasAttribute('aria-label') || input.hasAttribute('aria-labelledby');
                    const hasTitle = !!input.title;
                    // Check for placeholder (insufficient on its own but note it)
                    const hasPlaceholder = !!input.placeholder;

                    if (!hasLabelFor && !hasWrapLabel && !hasAriaLabel && !hasTitle) {
                        issues.push({
                            tag: input.tagName.toLowerCase(),
                            type: input.type || 'text',
                            id: input.id || '(no id)',
                            name: input.name || '(no name)',
                            hasPlaceholderOnly: hasPlaceholder,
                        });
                    }
                });
                return issues;
            }""")

            if unlabeled:
                self._add_finding(
                    title="Form inputs missing accessible label",
                    description=f"{len(unlabeled)} input(s) have no associated label, aria-label, or title",
                    severity=Severity.HIGH,
                    wcag_criterion="3.3.2",
                    expected_behavior="All form inputs must have a visible label or accessible name",
                    actual_behavior="Inputs found without any label association",
                    metadata={"inputs": unlabeled[:5]},
                )
        except Exception:
            pass

    def _test_error_identification(self):
        """WCAG 3.3.1 — Error fields must have a programmatically associated error message."""
        try:
            issues = self.page.evaluate("""() => {
                const issues = [];
                document.querySelectorAll('[aria-invalid="true"]').forEach(el => {
                    if (!el.offsetParent) return;
                    const describedby = el.getAttribute('aria-describedby');
                    let hasErrorMsg = false;
                    if (describedby) {
                        const target = document.getElementById(describedby);
                        hasErrorMsg = !!target && target.textContent?.trim().length > 0;
                    }
                    // Check for adjacent alert/error element
                    const parent = el.parentElement;
                    const adjacentAlert = parent && (
                        parent.querySelector('[role="alert"]') ||
                        parent.querySelector('.error, .invalid, .field-error')
                    );
                    if (!hasErrorMsg && !adjacentAlert) {
                        issues.push({ tag: el.tagName.toLowerCase(), id: el.id, describedby });
                    }
                });
                return issues;
            }""")

            if issues:
                self._add_finding(
                    title="Error fields missing error message association",
                    description=f"{len(issues)} field(s) marked aria-invalid have no associated error description",
                    severity=Severity.HIGH,
                    wcag_criterion="3.3.1",
                    expected_behavior="Fields with aria-invalid should have an error message via aria-describedby or adjacent role='alert'",
                    actual_behavior="Invalid fields found without accessible error descriptions",
                    metadata={"fields": issues[:5]},
                )
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # ROBUST (4.x)
    # -------------------------------------------------------------------------

    def _test_parsing_duplicate_ids(self):
        """WCAG 4.1.1 — Duplicate id attributes cause parsing errors."""
        try:
            duplicates = self.page.evaluate("""() => {
                const ids = {};
                document.querySelectorAll('[id]').forEach(el => {
                    const id = el.id;
                    if (!id) return;
                    ids[id] = (ids[id] || 0) + 1;
                });
                return Object.entries(ids)
                    .filter(([, count]) => count > 1)
                    .map(([id, count]) => ({ id, count }));
            }""")

            if duplicates:
                self._add_finding(
                    title="Duplicate id attributes found",
                    description=f"{len(duplicates)} id value(s) appear on multiple elements",
                    severity=Severity.HIGH,
                    wcag_criterion="4.1.1",
                    expected_behavior="Each id attribute value must be unique within the document",
                    actual_behavior="Duplicate IDs found, which break ARIA references and label associations",
                    metadata={"duplicates": duplicates[:10]},
                )
        except Exception:
            pass

    def _test_name_role_value(self):
        """WCAG 4.1.2 — All UI components need an accessible name and role."""
        try:
            issues = self.page.evaluate("""() => {
                const issues = [];

                // Elements with explicit role but no accessible name
                const rolesNeedingName = ['button', 'link', 'checkbox', 'radio', 'combobox',
                    'listbox', 'menu', 'menubar', 'radiogroup', 'searchbox', 'slider',
                    'spinbutton', 'switch', 'tab', 'textbox', 'tree', 'treegrid'];

                document.querySelectorAll('[role]').forEach(el => {
                    if (!el.offsetParent) return;
                    const role = el.getAttribute('role');
                    if (!rolesNeedingName.includes(role)) return;
                    const hasName = el.hasAttribute('aria-label') ||
                        el.hasAttribute('aria-labelledby') ||
                        el.textContent?.trim().length > 0 ||
                        el.title;
                    if (!hasName) {
                        issues.push({ type: 'role_no_name', role, tag: el.tagName.toLowerCase() });
                    }
                });

                // Clickable divs/spans without role or tabindex
                document.querySelectorAll('div[onclick], span[onclick]').forEach(el => {
                    if (!el.offsetParent) return;
                    const hasRole = el.hasAttribute('role');
                    const hasTabindex = el.hasAttribute('tabindex');
                    if (!hasRole || !hasTabindex) {
                        issues.push({
                            type: 'clickable_no_role',
                            tag: el.tagName.toLowerCase(),
                            text: el.textContent?.slice(0, 30),
                        });
                    }
                });

                return issues.slice(0, 20);
            }""")

            role_issues = [i for i in issues if i['type'] == 'role_no_name']
            click_issues = [i for i in issues if i['type'] == 'clickable_no_role']

            if role_issues:
                self._add_finding(
                    title="ARIA role elements missing accessible name",
                    description=f"{len(role_issues)} element(s) have an interactive role but no accessible name",
                    severity=Severity.HIGH,
                    wcag_criterion="4.1.2",
                    expected_behavior="All interactive components must have an accessible name (text, aria-label, or aria-labelledby)",
                    actual_behavior="Interactive role elements found without accessible name",
                    metadata={"elements": role_issues[:5]},
                )
            if click_issues:
                self._add_finding(
                    title="Clickable elements without role or keyboard access",
                    description=f"{len(click_issues)} div/span element(s) have onclick but no role or tabindex",
                    severity=Severity.HIGH,
                    wcag_criterion="4.1.2",
                    expected_behavior="Custom interactive elements need a role (e.g., role='button') and tabindex='0'",
                    actual_behavior="Clickable elements found that are inaccessible to keyboard users",
                    metadata={"elements": click_issues[:5]},
                )
        except Exception:
            pass

    def _test_status_messages(self):
        """WCAG 4.1.3 — Status messages must be programmatically determinable."""
        try:
            issues = self.page.evaluate("""() => {
                const notifPatterns = /toast|snackbar|notification|alert-box|status-msg|flash-message|banner-message/i;
                const issues = [];
                document.querySelectorAll('[class]').forEach(el => {
                    const cls = el.className || '';
                    if (!notifPatterns.test(cls)) return;
                    const role = el.getAttribute('role');
                    const ariaLive = el.getAttribute('aria-live');
                    const hasLiveRegion = ['status', 'alert', 'log', 'marquee', 'timer'].includes(role) || ariaLive;
                    if (!hasLiveRegion) {
                        issues.push({ classes: cls.slice(0, 60), role, ariaLive });
                    }
                });
                return issues.slice(0, 10);
            }""")

            if issues:
                self._add_finding(
                    title="Notification elements missing live region",
                    description=f"{len(issues)} notification-like element(s) lack role='status', role='alert', or aria-live",
                    severity=Severity.MEDIUM,
                    wcag_criterion="4.1.3",
                    expected_behavior="Dynamic status messages must use aria-live or role='status'/'alert' so screen readers announce them",
                    actual_behavior="Notification elements found without live region markup",
                    metadata={"elements": issues[:5]},
                )
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # ARIA PATTERN CHECKS
    # -------------------------------------------------------------------------

    def _test_aria_required_properties(self):
        """ARIA spec — roles must have their required owned properties."""
        try:
            required_props = _ARIA_REQUIRED_PROPS
            issues = self.page.evaluate("""(requiredProps) => {
                const issues = [];
                Object.entries(requiredProps).forEach(([role, props]) => {
                    if (props.length === 0) return;
                    document.querySelectorAll(`[role="${role}"]`).forEach(el => {
                        if (!el.offsetParent) return;
                        const missing = props.filter(p => !el.hasAttribute(p));
                        if (missing.length > 0) {
                            issues.push({ role, missing, tag: el.tagName.toLowerCase(), text: el.textContent?.slice(0, 30) });
                        }
                    });
                });
                return issues.slice(0, 20);
            }""", required_props)

            if issues:
                self._add_finding(
                    title="ARIA roles missing required properties",
                    description=f"{len(issues)} element(s) have ARIA roles that lack required owned properties",
                    severity=Severity.HIGH,
                    wcag_criterion="4.1.2",
                    expected_behavior="ARIA roles must include their required properties (e.g., role='slider' needs aria-valuenow)",
                    actual_behavior="ARIA roles found without required owned properties",
                    metadata={"elements": issues[:5]},
                )
        except Exception:
            pass

    def _test_aria_widget_patterns(self):
        """ARIA spec — validate widget composition patterns (tabs, combobox, menu)."""
        try:
            issues = self.page.evaluate("""() => {
                const issues = [];

                // Tablist must contain tab elements; tabs must reference tabpanels
                document.querySelectorAll('[role="tablist"]').forEach(tablist => {
                    const tabs = tablist.querySelectorAll('[role="tab"]');
                    if (tabs.length === 0) {
                        issues.push({ type: 'tablist_no_tabs', element: tablist.tagName.toLowerCase() });
                    }
                    tabs.forEach(tab => {
                        const controls = tab.getAttribute('aria-controls');
                        if (controls && !document.getElementById(controls)) {
                            issues.push({ type: 'tab_bad_controls', id: controls });
                        }
                    });
                });

                // Combobox must have aria-expanded and an associated listbox
                document.querySelectorAll('[role="combobox"]').forEach(cb => {
                    if (!cb.hasAttribute('aria-expanded')) {
                        issues.push({ type: 'combobox_no_expanded', tag: cb.tagName.toLowerCase() });
                    }
                });

                // Menu/menubar must contain menuitems
                document.querySelectorAll('[role="menu"], [role="menubar"]').forEach(menu => {
                    const items = menu.querySelectorAll('[role="menuitem"], [role="menuitemcheckbox"], [role="menuitemradio"]');
                    if (items.length === 0) {
                        issues.push({ type: 'menu_no_items', role: menu.getAttribute('role') });
                    }
                });

                return issues;
            }""")

            if issues:
                self._add_finding(
                    title="ARIA widget pattern violations",
                    description=f"{len(issues)} ARIA widget(s) have incorrect composition (tabs, combobox, or menu structure)",
                    severity=Severity.HIGH,
                    wcag_criterion="4.1.2",
                    expected_behavior="ARIA widgets must follow their required composition pattern",
                    actual_behavior="Widget pattern violations found (e.g., tablist without tabs, menu without items)",
                    metadata={"issues": issues[:5]},
                )
        except Exception:
            pass

    def _test_aria_parent_child(self):
        """ARIA spec — certain roles require specific parent roles."""
        try:
            required_parents = _ARIA_REQUIRED_PARENTS
            issues = self.page.evaluate("""(requiredParents) => {
                const issues = [];
                Object.entries(requiredParents).forEach(([childRole, parentRoles]) => {
                    document.querySelectorAll(`[role="${childRole}"]`).forEach(el => {
                        if (!el.offsetParent) return;
                        let ancestor = el.parentElement;
                        let found = false;
                        while (ancestor) {
                            const role = ancestor.getAttribute('role') || ancestor.tagName.toLowerCase();
                            if (parentRoles.some(p => role === p || ancestor.getAttribute('role') === p)) {
                                found = true;
                                break;
                            }
                            ancestor = ancestor.parentElement;
                        }
                        if (!found) {
                            issues.push({
                                childRole,
                                expectedParents: parentRoles,
                                tag: el.tagName.toLowerCase(),
                                text: el.textContent?.slice(0, 30),
                            });
                        }
                    });
                });
                return issues.slice(0, 20);
            }""", required_parents)

            if issues:
                self._add_finding(
                    title="ARIA child roles outside required parent",
                    description=f"{len(issues)} element(s) have roles that require a specific parent role",
                    severity=Severity.MEDIUM,
                    wcag_criterion="4.1.2",
                    expected_behavior="Certain ARIA roles must be contained within a required parent (e.g., tab inside tablist)",
                    actual_behavior="Role elements found outside their required parent context",
                    metadata={"elements": issues[:5]},
                )
        except Exception:
            pass

    def _test_redundant_aria_roles(self):
        """ARIA spec — semantic HTML with redundant explicit ARIA roles adds noise."""
        try:
            issues = self.page.evaluate("""() => {
                const redundant = {
                    'BUTTON': 'button',
                    'NAV': 'navigation',
                    'HEADER': 'banner',
                    'FOOTER': 'contentinfo',
                    'MAIN': 'main',
                    'ASIDE': 'complementary',
                    'UL': 'list',
                    'OL': 'list',
                    'LI': 'listitem',
                    'TABLE': 'table',
                    'TR': 'row',
                };
                const issues = [];
                Object.entries(redundant).forEach(([tag, role]) => {
                    document.querySelectorAll(`${tag.toLowerCase()}[role="${role}"]`).forEach(el => {
                        issues.push({ tag: tag.toLowerCase(), role });
                    });
                });
                // <a href> with role="link"
                document.querySelectorAll('a[href][role="link"]').forEach(() => {
                    issues.push({ tag: 'a', role: 'link' });
                });
                return issues.slice(0, 20);
            }""")

            if issues:
                self._add_finding(
                    title="Redundant ARIA roles on semantic HTML",
                    description=f"{len(issues)} element(s) have ARIA roles that duplicate the element's native semantics",
                    severity=Severity.LOW,
                    wcag_criterion="4.1.2",
                    wcag_level="A",
                    expected_behavior="Semantic HTML already conveys the role — adding an explicit role is redundant",
                    actual_behavior="Redundant role attributes found (e.g., <button role='button'>)",
                    metadata={"elements": issues[:5]},
                )
        except Exception:
            pass
