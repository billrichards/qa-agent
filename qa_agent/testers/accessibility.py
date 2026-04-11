"""Accessibility testing module."""

from playwright.sync_api import Page

from ..config import TestConfig
from ..models import Finding, FindingCategory, Severity
from .base import BaseTester


class AccessibilityTester(BaseTester):
    """Tests accessibility issues and WCAG compliance."""

    def __init__(self, page: Page, config: TestConfig):
        super().__init__(page, config)

    def run(self) -> list[Finding]:
        """Run all accessibility tests."""
        self.findings = []

        self._test_images_alt_text()
        self._test_headings_structure()
        self._test_link_text()
        self._test_color_contrast()
        self._test_aria_usage()
        self._test_landmark_regions()
        self._test_language_attribute()
        self._test_skip_links()
        self._test_motion_preferences()

        return self.findings

    def _test_images_alt_text(self):
        """Test that images have appropriate alt text."""
        try:
            images = self.page.locator('img:visible')
            count = images.count()

            issues = {
                "missing_alt": [],
                "empty_decorative": 0,
                "suspicious_alt": [],
            }

            for i in range(count):
                img = images.nth(i)
                try:
                    info = img.evaluate("""el => ({
                        src: el.src?.slice(-50),
                        alt: el.alt,
                        hasAlt: el.hasAttribute('alt'),
                        role: el.getAttribute('role'),
                        ariaHidden: el.getAttribute('aria-hidden'),
                        width: el.width,
                        height: el.height,
                        isInLink: !!el.closest('a')
                    })""")

                    # Skip tiny images (likely icons/spacers)
                    if info['width'] < 20 and info['height'] < 20:
                        continue

                    # Missing alt attribute entirely
                    if not info['hasAlt'] and info.get('role') != 'presentation' and info.get('ariaHidden') != 'true':
                        issues['missing_alt'].append(info['src'])

                    # Empty alt (intentional decorative)
                    elif info['alt'] == '':
                        issues['empty_decorative'] += 1

                    # Suspicious alt text patterns
                    elif info['alt']:
                        alt_lower = info['alt'].lower()
                        suspicious_patterns = ['image', 'picture', 'photo', 'img', '.jpg', '.png', '.gif', 'untitled']
                        if any(pattern in alt_lower for pattern in suspicious_patterns) and len(info['alt']) < 20:
                            issues['suspicious_alt'].append({"alt": info['alt'], "src": info['src']})

                        # Image in link with non-descriptive alt
                        if info['isInLink'] and info['alt'] in ['click here', 'read more', 'link', 'image']:
                            issues['suspicious_alt'].append({"alt": info['alt'], "src": info['src'], "issue": "link_image"})

                except Exception:
                    continue

            if len(issues['missing_alt']) > 0:
                self.findings.append(Finding(
                    title="Images missing alt attribute",
                    description=f"{len(issues['missing_alt'])} images lack alt attribute",
                    category=FindingCategory.ACCESSIBILITY,
                    severity=Severity.HIGH,
                    url=self.page.url,
                    expected_behavior="All images must have alt attribute (empty for decorative)",
                    actual_behavior="Images found without alt attribute",
                    metadata={"images": issues['missing_alt'][:5]},
                ))

            if len(issues['suspicious_alt']) > 0:
                self.findings.append(Finding(
                    title="Images with unhelpful alt text",
                    description=f"{len(issues['suspicious_alt'])} images have generic or file-name alt text",
                    category=FindingCategory.ACCESSIBILITY,
                    severity=Severity.MEDIUM,
                    url=self.page.url,
                    expected_behavior="Alt text should describe the image content meaningfully",
                    actual_behavior="Alt text contains generic terms like 'image' or file names",
                    metadata={"images": issues['suspicious_alt'][:5]},
                ))

        except Exception:
            pass

    def _test_headings_structure(self):
        """Test heading hierarchy (h1-h6)."""
        try:
            headings = self.page.evaluate("""() => {
                const headings = document.querySelectorAll('h1, h2, h3, h4, h5, h6');
                return Array.from(headings).map((h, idx) => ({
                    level: parseInt(h.tagName[1]),
                    text: h.textContent?.slice(0, 50),
                    visible: h.offsetParent !== null,
                    index: idx
                }));
            }""")

            visible_headings = [h for h in headings if h['visible']]

            # Check for missing h1
            h1_count = sum(1 for h in visible_headings if h['level'] == 1)
            if h1_count == 0:
                self.findings.append(Finding(
                    title="Page missing h1 heading",
                    description="No h1 element found on the page",
                    category=FindingCategory.ACCESSIBILITY,
                    severity=Severity.MEDIUM,
                    url=self.page.url,
                    expected_behavior="Each page should have exactly one h1",
                    actual_behavior="No h1 found",
                ))
            elif h1_count > 1:
                self.findings.append(Finding(
                    title="Multiple h1 headings",
                    description=f"Page has {h1_count} h1 elements",
                    category=FindingCategory.ACCESSIBILITY,
                    severity=Severity.LOW,
                    url=self.page.url,
                    expected_behavior="Pages typically should have one main h1",
                    actual_behavior=f"Found {h1_count} h1 elements",
                ))

            # Check heading level skips
            skipped_levels = []
            for i in range(1, len(visible_headings)):
                prev_level = visible_headings[i-1]['level']
                curr_level = visible_headings[i]['level']

                if curr_level > prev_level + 1:
                    skipped_levels.append({
                        "from": f"h{prev_level}",
                        "to": f"h{curr_level}",
                        "heading": visible_headings[i]['text']
                    })

            if len(skipped_levels) > 0:
                self.findings.append(Finding(
                    title="Heading level skipped",
                    description=f"Heading hierarchy skips levels {len(skipped_levels)} times",
                    category=FindingCategory.ACCESSIBILITY,
                    severity=Severity.MEDIUM,
                    url=self.page.url,
                    expected_behavior="Heading levels should not skip (e.g., h1 to h3)",
                    actual_behavior="Heading levels skip, breaking document outline",
                    metadata={"skips": skipped_levels[:5]},
                ))

        except Exception:
            pass

    def _test_link_text(self):
        """Test that links have descriptive text."""
        try:
            links = self.page.locator('a:visible')
            count = min(links.count(), 30)

            bad_links = []

            for i in range(count):
                link = links.nth(i)
                try:
                    info = link.evaluate("""el => {
                        const text = el.textContent?.trim() || '';
                        const ariaLabel = el.getAttribute('aria-label') || '';
                        const title = el.title || '';
                        const imgAlt = el.querySelector('img')?.alt || '';

                        const accessibleName = ariaLabel || text || imgAlt || title;

                        return {
                            text: text.slice(0, 50),
                            accessibleName: accessibleName.slice(0, 50),
                            href: el.href?.slice(-50),
                            hasImage: !!el.querySelector('img')
                        };
                    }""")

                    # Check for generic link text
                    generic_patterns = ['click here', 'here', 'read more', 'more', 'link', 'click', 'this']
                    accessible_name_lower = info['accessibleName'].lower().strip()

                    if accessible_name_lower in generic_patterns:
                        bad_links.append({
                            "text": info['accessibleName'],
                            "issue": "generic",
                            "href": info['href']
                        })

                    # Empty link
                    elif not info['accessibleName'].strip():
                        bad_links.append({
                            "text": "(empty)",
                            "issue": "empty",
                            "href": info['href']
                        })

                except Exception:
                    continue

            empty_links = [lnk for lnk in bad_links if lnk['issue'] == 'empty']
            generic_links = [lnk for lnk in bad_links if lnk['issue'] == 'generic']

            if len(empty_links) > 0:
                self.findings.append(Finding(
                    title="Empty links found",
                    description=f"{len(empty_links)} links have no accessible name",
                    category=FindingCategory.ACCESSIBILITY,
                    severity=Severity.HIGH,
                    url=self.page.url,
                    expected_behavior="All links must have descriptive text or aria-label",
                    actual_behavior="Links exist with no text or accessible name",
                    metadata={"links": empty_links[:5]},
                ))

            if len(generic_links) > 3:
                self.findings.append(Finding(
                    title="Generic link text used",
                    description=f"{len(generic_links)} links use generic text like 'click here'",
                    category=FindingCategory.ACCESSIBILITY,
                    severity=Severity.LOW,
                    url=self.page.url,
                    expected_behavior="Link text should describe the destination",
                    actual_behavior="Generic phrases used instead of descriptive text",
                    metadata={"links": generic_links[:5]},
                ))

        except Exception:
            pass

    def _test_color_contrast(self):
        """Test color contrast of text elements."""
        try:
            # Sample some text elements
            text_elements = self.page.locator('p:visible, span:visible, a:visible, li:visible, td:visible')
            count = min(text_elements.count(), 20)

            low_contrast = []

            for i in range(count):
                element = text_elements.nth(i)
                try:
                    contrast_info = element.evaluate("""el => {
                        const style = window.getComputedStyle(el);
                        const color = style.color;
                        const bgColor = style.backgroundColor;
                        const fontSize = parseFloat(style.fontSize);
                        const fontWeight = style.fontWeight;

                        // Parse RGB values
                        const parseColor = (c) => {
                            const match = c.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                            if (match) return [parseInt(match[1]), parseInt(match[2]), parseInt(match[3])];
                            return null;
                        };

                        const fg = parseColor(color);
                        const bg = parseColor(bgColor);

                        if (!fg || !bg) return null;

                        // Calculate relative luminance
                        const luminance = (rgb) => {
                            const [r, g, b] = rgb.map(c => {
                                c = c / 255;
                                return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
                            });
                            return 0.2126 * r + 0.7152 * g + 0.0722 * b;
                        };

                        const l1 = luminance(fg);
                        const l2 = luminance(bg);
                        const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);

                        const isLargeText = fontSize >= 18 || (fontSize >= 14 && parseInt(fontWeight) >= 700);
                        const requiredRatio = isLargeText ? 3 : 4.5;

                        return {
                            ratio: ratio.toFixed(2),
                            passes: ratio >= requiredRatio,
                            requiredRatio,
                            text: el.textContent?.slice(0, 30),
                            color,
                            bgColor,
                            fontSize,
                            isTransparentBg: bg[0] === 0 && bg[1] === 0 && bg[2] === 0 && bgColor.includes('rgba') && bgColor.includes(', 0)')
                        };
                    }""")

                    if contrast_info and not contrast_info.get('passes') and not contrast_info.get('isTransparentBg'):
                        low_contrast.append(contrast_info)

                except Exception:
                    continue

            if len(low_contrast) > 3:
                self.findings.append(Finding(
                    title="Low color contrast detected",
                    description=f"{len(low_contrast)} text elements may have insufficient contrast",
                    category=FindingCategory.ACCESSIBILITY,
                    severity=Severity.MEDIUM,
                    url=self.page.url,
                    expected_behavior="Text should have 4.5:1 contrast ratio (3:1 for large text)",
                    actual_behavior="Some text has low contrast against background",
                    metadata={"elements": low_contrast[:5]},
                ))

        except Exception:
            pass

    def _test_aria_usage(self):
        """Test correct usage of ARIA attributes."""
        try:
            aria_issues = self.page.evaluate("""() => {
                const issues = [];

                // Check for aria-hidden on focusable elements
                document.querySelectorAll('[aria-hidden="true"]').forEach(el => {
                    const focusable = el.querySelector('a, button, input, select, textarea, [tabindex]:not([tabindex="-1"])');
                    if (focusable && focusable.offsetParent !== null) {
                        issues.push({
                            type: 'hidden_focusable',
                            element: el.tagName.toLowerCase(),
                            text: el.textContent?.slice(0, 30)
                        });
                    }
                });

                // Check for invalid ARIA roles
                const validRoles = ['alert', 'alertdialog', 'application', 'article', 'banner', 'button',
                    'cell', 'checkbox', 'columnheader', 'combobox', 'complementary', 'contentinfo',
                    'definition', 'dialog', 'directory', 'document', 'feed', 'figure', 'form', 'grid',
                    'gridcell', 'group', 'heading', 'img', 'link', 'list', 'listbox', 'listitem',
                    'log', 'main', 'marquee', 'math', 'menu', 'menubar', 'menuitem', 'menuitemcheckbox',
                    'menuitemradio', 'navigation', 'none', 'note', 'option', 'presentation', 'progressbar',
                    'radio', 'radiogroup', 'region', 'row', 'rowgroup', 'rowheader', 'scrollbar',
                    'search', 'searchbox', 'separator', 'slider', 'spinbutton', 'status', 'switch',
                    'tab', 'table', 'tablist', 'tabpanel', 'term', 'textbox', 'timer', 'toolbar',
                    'tooltip', 'tree', 'treegrid', 'treeitem'];

                document.querySelectorAll('[role]').forEach(el => {
                    const role = el.getAttribute('role');
                    if (!validRoles.includes(role)) {
                        issues.push({
                            type: 'invalid_role',
                            role,
                            element: el.tagName.toLowerCase()
                        });
                    }
                });

                // Check for elements with aria-labelledby pointing to non-existent ID
                document.querySelectorAll('[aria-labelledby]').forEach(el => {
                    const ids = el.getAttribute('aria-labelledby').split(' ');
                    ids.forEach(id => {
                        if (!document.getElementById(id)) {
                            issues.push({
                                type: 'missing_labelledby_target',
                                id,
                                element: el.tagName.toLowerCase()
                            });
                        }
                    });
                });

                // Check for aria-describedby pointing to non-existent ID
                document.querySelectorAll('[aria-describedby]').forEach(el => {
                    const ids = el.getAttribute('aria-describedby').split(' ');
                    ids.forEach(id => {
                        if (!document.getElementById(id)) {
                            issues.push({
                                type: 'missing_describedby_target',
                                id,
                                element: el.tagName.toLowerCase()
                            });
                        }
                    });
                });

                return issues;
            }""")

            if len(aria_issues) > 0:
                for issue in aria_issues[:5]:
                    if issue['type'] == 'hidden_focusable':
                        self.findings.append(Finding(
                            title="Focusable element inside aria-hidden",
                            description="aria-hidden element contains focusable children",
                            category=FindingCategory.ACCESSIBILITY,
                            severity=Severity.HIGH,
                            url=self.page.url,
                            element_text=issue.get('text'),
                            expected_behavior="aria-hidden elements should not contain focusable elements",
                            actual_behavior="Focusable element hidden from assistive technology but still focusable",
                        ))
                    elif issue['type'] == 'invalid_role':
                        self.findings.append(Finding(
                            title="Invalid ARIA role",
                            description=f"Element uses invalid role '{issue['role']}'",
                            category=FindingCategory.ACCESSIBILITY,
                            severity=Severity.MEDIUM,
                            url=self.page.url,
                            expected_behavior="ARIA roles must be valid WAI-ARIA roles",
                            actual_behavior=f"Invalid role: {issue['role']}",
                        ))
                    elif 'missing' in issue['type']:
                        self.findings.append(Finding(
                            title="ARIA reference points to missing element",
                            description=f"aria-labelledby/describedby references non-existent ID: {issue['id']}",
                            category=FindingCategory.ACCESSIBILITY,
                            severity=Severity.MEDIUM,
                            url=self.page.url,
                            expected_behavior="ARIA ID references must point to existing elements",
                            actual_behavior=f"Referenced ID '{issue['id']}' not found",
                        ))

        except Exception:
            pass

    def _test_landmark_regions(self):
        """Test for proper landmark regions."""
        try:
            landmarks = self.page.evaluate("""() => {
                return {
                    main: document.querySelectorAll('main, [role="main"]').length,
                    nav: document.querySelectorAll('nav, [role="navigation"]').length,
                    header: document.querySelectorAll('header, [role="banner"]').length,
                    footer: document.querySelectorAll('footer, [role="contentinfo"]').length,
                    search: document.querySelectorAll('[role="search"]').length
                };
            }""")

            if landmarks['main'] == 0:
                self.findings.append(Finding(
                    title="Missing main landmark",
                    description="Page has no <main> element or role='main'",
                    category=FindingCategory.ACCESSIBILITY,
                    severity=Severity.MEDIUM,
                    url=self.page.url,
                    expected_behavior="Pages should have a main landmark for primary content",
                    actual_behavior="No main landmark found",
                ))

            if landmarks['main'] > 1:
                self.findings.append(Finding(
                    title="Multiple main landmarks",
                    description=f"Page has {landmarks['main']} main landmarks",
                    category=FindingCategory.ACCESSIBILITY,
                    severity=Severity.LOW,
                    url=self.page.url,
                    expected_behavior="Pages should have exactly one main landmark",
                    actual_behavior=f"Found {landmarks['main']} main landmarks",
                ))

        except Exception:
            pass

    def _test_language_attribute(self):
        """Test for lang attribute on html element."""
        try:
            lang_info = self.page.evaluate("""() => ({
                hasLang: document.documentElement.hasAttribute('lang'),
                lang: document.documentElement.lang,
                hasXmlLang: document.documentElement.hasAttribute('xml:lang')
            })""")

            if not lang_info['hasLang']:
                self.findings.append(Finding(
                    title="Missing language attribute",
                    description="HTML element lacks lang attribute",
                    category=FindingCategory.ACCESSIBILITY,
                    severity=Severity.MEDIUM,
                    url=self.page.url,
                    expected_behavior="<html> should have lang attribute for screen readers",
                    actual_behavior="No lang attribute on html element",
                ))
            elif len(lang_info.get('lang', '')) < 2:
                self.findings.append(Finding(
                    title="Invalid language code",
                    description=f"Language code '{lang_info.get('lang')}' appears invalid",
                    category=FindingCategory.ACCESSIBILITY,
                    severity=Severity.LOW,
                    url=self.page.url,
                    expected_behavior="Lang attribute should be valid (e.g., 'en', 'en-US')",
                    actual_behavior=f"Lang attribute value: '{lang_info.get('lang')}'",
                ))

        except Exception:
            pass

    def _test_skip_links(self):
        """Test for skip navigation links."""
        try:
            skip_link = self.page.evaluate("""() => {
                // Look for skip links
                const links = document.querySelectorAll('a');
                for (const link of links) {
                    const text = link.textContent?.toLowerCase() || '';
                    const href = link.getAttribute('href') || '';

                    if ((text.includes('skip') || text.includes('jump')) &&
                        (text.includes('main') || text.includes('content') || text.includes('navigation')) &&
                        href.startsWith('#')) {

                        // Check if target exists
                        const targetId = href.slice(1);
                        const target = document.getElementById(targetId);

                        return {
                            found: true,
                            text: link.textContent,
                            href,
                            targetExists: !!target,
                            isVisible: link.offsetParent !== null,
                            becomesVisible: window.getComputedStyle(link).position === 'absolute'
                        };
                    }
                }
                return { found: false };
            }""")

            # Check for significant navigation before main content
            nav_before_main = self.page.evaluate("""() => {
                const main = document.querySelector('main, [role="main"]');
                if (!main) return 0;

                let links = 0;
                let el = document.body.firstElementChild;
                while (el && el !== main && !main.contains(el)) {
                    links += el.querySelectorAll('a').length;
                    el = el.nextElementSibling;
                }
                return links;
            }""")

            if nav_before_main > 5 and not skip_link['found']:
                self.findings.append(Finding(
                    title="Missing skip navigation link",
                    description=f"{nav_before_main} links before main content with no skip link",
                    category=FindingCategory.ACCESSIBILITY,
                    severity=Severity.MEDIUM,
                    url=self.page.url,
                    expected_behavior="Pages with navigation should have skip link for keyboard users",
                    actual_behavior="No skip navigation link found",
                ))
            elif skip_link['found'] and not skip_link.get('targetExists'):
                self.findings.append(Finding(
                    title="Skip link target missing",
                    description=f"Skip link points to {skip_link['href']} but target doesn't exist",
                    category=FindingCategory.ACCESSIBILITY,
                    severity=Severity.MEDIUM,
                    url=self.page.url,
                    expected_behavior="Skip link should point to existing element",
                    actual_behavior="Skip link target ID not found",
                ))

        except Exception:
            pass

    def _test_motion_preferences(self):
        """Test respect for reduced motion preference."""
        try:
            result = self.page.evaluate("""() => {
                const allElements = document.querySelectorAll('*');
                let hasAnimations = false;
                let respectsMotion = false;

                for (const el of allElements) {
                    const style = window.getComputedStyle(el);
                    const animation = style.animation || style.webkitAnimation;
                    const transition = style.transition || style.webkitTransition;

                    if (animation && animation !== 'none' && !animation.includes('0s')) {
                        hasAnimations = true;
                    }
                    if (transition && transition !== 'none' && transition !== 'all 0s ease 0s') {
                        hasAnimations = true;
                    }
                }

                // Check for prefers-reduced-motion media query in stylesheets
                try {
                    for (const sheet of document.styleSheets) {
                        try {
                            for (const rule of sheet.cssRules) {
                                if (rule.media && rule.media.mediaText?.includes('prefers-reduced-motion')) {
                                    respectsMotion = true;
                                    break;
                                }
                            }
                        } catch (e) {
                            // CORS blocked stylesheet
                        }
                    }
                } catch (e) {}

                return { hasAnimations, respectsMotion };
            }""")

            if result and result.get("hasAnimations") and not result.get("respectsMotion"):
                self.findings.append(Finding(
                    title="Animations without reduced-motion support",
                    description="Page has animations or transitions but no prefers-reduced-motion media query",
                    category=FindingCategory.ACCESSIBILITY,
                    severity=Severity.LOW,
                    url=self.page.url,
                    expected_behavior="Animations should be suppressed when prefers-reduced-motion is set",
                    actual_behavior="No prefers-reduced-motion media query found in stylesheets",
                ))

        except Exception:
            pass
