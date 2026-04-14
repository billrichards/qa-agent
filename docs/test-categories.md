# Test Categories

QA Agent ships with six test suites. Five run by default; WCAG 2.1 AA compliance is opt-in.

---

## Keyboard Navigation

**Tester:** [`KeyboardTester`](../qa_agent/testers/keyboard.py)

Verifies that every interactive element is operable without a mouse.

| Check | What it tests |
|---|---|
| TAB order | Every focusable element receives focus in a logical sequence |
| Arrow key navigation | Widgets like menus and tabs respond to arrow keys |
| Enter key activation | Buttons and links activate on Enter |
| Escape key | Modals and popups close on Escape |
| Keyboard traps | Focus is never locked inside a component |
| Focus visibility | Focused elements have a visible focus indicator |

---

## Mouse Interaction

**Tester:** [`MouseTester`](../qa_agent/testers/mouse.py)

Exercises pointer-based interactions and validates target sizing.

| Check | What it tests |
|---|---|
| Click targets | Buttons, links, and controls respond to clicks |
| Hover states | Elements provide visual feedback on hover |
| Double-click | Double-click handlers fire correctly |
| Right-click / context menus | Custom context menus appear when expected |
| Target size (WCAG 2.5.5) | Click targets meet the 44 × 44 px minimum |
| Overlapping elements | No elements obscure clickable targets |

---

## Form Handling

**Tester:** [`FormTester`](../qa_agent/testers/forms.py)

Fills and submits forms, checking validation and labelling.

| Check | What it tests |
|---|---|
| Required field indicators | Required fields are visually and programmatically marked |
| Validation feedback | Invalid input produces clear, timely error messages |
| Error message accessibility | Error messages are associated with their fields via `aria-describedby` or equivalent |
| Label associations | Every input has a `<label>` or `aria-label` |
| HTML5 input types | Inputs use appropriate `type` attributes (`email`, `tel`, etc.) |
| Autocomplete attributes | Login and address fields include `autocomplete` hints |

---

## Accessibility (WCAG)

**Tester:** [`AccessibilityTester`](../qa_agent/testers/accessibility.py)

Covers the most common WCAG 2.1 Level A and AA success criteria.

| Check | What it tests |
|---|---|
| Alt text (1.1.1) | Images have meaningful `alt` attributes |
| Heading structure | `h1`–`h6` elements follow a logical hierarchy |
| Link text quality (2.4.4) | Links have descriptive, non-generic text |
| Color contrast (1.4.3) | Text meets 4.5 : 1 (normal) / 3 : 1 (large) contrast ratios |
| ARIA usage (4.1.2) | ARIA roles, states, and properties are valid |
| Landmark regions | Pages use `<main>`, `<nav>`, `<header>`, etc. |
| Language attribute (3.1.1) | `<html lang="…">` is present and valid |
| Skip navigation (2.4.1) | A skip-to-content link exists |

---

## Error Detection

**Tester:** [`ErrorDetector`](../qa_agent/testers/errors.py)

Monitors the browser console and network layer for runtime problems.

| Check | What it tests |
|---|---|
| Console errors / warnings | JavaScript `console.error()` and `console.warn()` calls |
| Network errors | HTTP 4xx and 5xx responses |
| JavaScript exceptions | Uncaught exceptions in page scripts |
| Broken images | `<img>` elements that fail to load |
| Broken anchors | In-page `#fragment` links that point to missing IDs |
| Mixed content | HTTP resources loaded on HTTPS pages |

---

## WCAG 2.1 AA Compliance (opt-in)

**Tester:** [`WCAGComplianceTester`](../qa_agent/testers/wcag_compliance.py)

> Enable with `--wcag-compliance` (CLI) or `"test_wcag_compliance": true` (API).

Extends the default accessibility suite with deeper checks against the full WCAG 2.1 Level AA specification.

| WCAG Criterion | What it tests |
|---|---|
| 1.3.2 Meaningful Sequence | DOM order matches visual reading order |
| 1.3.5 Input Purpose | Input fields declare their purpose via `autocomplete` |
| 1.4.1 Use of Color | Information is not conveyed by color alone |
| 1.4.11 Non-text Contrast | UI components and graphics meet 3 : 1 contrast |
| 1.4.13 Content on Hover/Focus | Tooltips and popovers are dismissible and persistent |
| 2.4.7 Focus Visible | Focus indicators are clearly visible |
| 2.5.3 Label in Name | Accessible name contains the visible label text |
| 2.5.5 Target Size | Touch/click targets are at least 44 × 44 px |
| 3.1.2 Language of Parts | Content in a different language uses `lang` attributes |
| 3.3.1 Error Identification | Form errors are identified and described in text |
| ARIA validation | Roles have required properties; parent/child relationships are correct |
