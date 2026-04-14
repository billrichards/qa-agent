# Web API Reference

QA Agent's web server exposes a REST + SSE API for launching test runs, streaming live output, and browsing past sessions. All endpoints are served by the Flask app in [`server.py`](https://github.com/billrichards/qa-agent/blob/main/qa_agent/web/server.py).

**Base URL:** `http://127.0.0.1:5000` (default; configurable with `--host` / `--port`)

> **No authentication** — the API is intended for local or internal use only.

---

## Table of Contents

- [Jobs](#jobs)
  - [POST /api/run](#post-apirun) — Launch a test run
  - [GET /api/stream/:job_id](#get-apistreamjob_id) — Stream live output (SSE)
  - [GET /api/status/:job_id](#get-apistatusjob_id) — Poll job status
  - [POST /api/stop/:job_id](#post-apistopjob_id) — Stop a running job
  - [GET /api/jobs](#get-apijobs) — List active jobs
- [Sessions](#sessions)
  - [GET /api/sessions](#get-apisessions) — List past sessions
  - [GET /api/session/:domain/:session_id](#get-apisessiondomainsession_id) — Session detail
- [Files](#files)
  - [GET /files/:path](#get-filespath) — Serve output files
- [Request Body Reference](#request-body-reference)
- [SSE Event Types](#sse-event-types)

---

## Jobs

### POST /api/run

Launch a new test run. Returns immediately with a job ID; the test executes in a background thread.

**Request:**

```bash
curl -X POST http://127.0.0.1:5000/api/run \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://example.com"],
    "mode": "focused",
    "test_wcag_compliance": false
  }'
```

**Response** `202 Accepted`:

```json
{
  "job_id": "a1b2c3d4",
  "status": "running",
  "stream_url": "/api/stream/a1b2c3d4"
}
```

**Error** `400 Bad Request` — returned when `urls` is missing or empty:

```json
{ "error": "urls is required and must be a non-empty list" }
```

See [Request Body Reference](#request-body-reference) for the full list of accepted fields.

---

### GET /api/stream/:job_id

Stream real-time output from a running job via [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events).

```bash
curl -N http://127.0.0.1:5000/api/stream/a1b2c3d4
```

The stream emits events until the job completes, fails, or is stopped. A `: keep-alive` comment is sent every 25 seconds to prevent connection timeouts. Late-joining clients receive a full replay of all previous events.

See [SSE Event Types](#sse-event-types) for the event format.

**Error** `404` — job ID not found.

---

### GET /api/status/:job_id

Poll the current status of a job without opening an SSE stream.

```bash
curl http://127.0.0.1:5000/api/status/a1b2c3d4
```

**Response** `200`:

```json
{
  "job_id": "a1b2c3d4",
  "status": "running",
  "session_id": "f9e8d7c6",
  "domain": "example.com",
  "total_findings": 3,
  "pages_tested": 2,
  "error": null
}
```

| Field | Type | Description |
|---|---|---|
| `status` | string | `queued`, `running`, `completed`, `failed`, or `stopped` |
| `session_id` | string \| null | Set once the agent initialises |
| `domain` | string \| null | Extracted from the first URL |
| `total_findings` | integer | Updated when the run finishes |
| `pages_tested` | integer | Updated when the run finishes |
| `error` | string \| null | Error message if `status` is `failed` |

**Error** `404` — job ID not found.

---

### POST /api/stop/:job_id

Signal a running job to stop gracefully. The agent finishes the current page and then exits.

```bash
curl -X POST http://127.0.0.1:5000/api/stop/a1b2c3d4
```

**Response** `200`:

```json
{ "job_id": "a1b2c3d4", "status": "stopping" }
```

**Error** `404` — job ID not found.
**Error** `400` — job already finished (`completed`, `failed`, or `stopped`).

---

### GET /api/jobs

List all in-memory jobs (active and recently finished). Jobs are sorted most-recent-first.

```bash
curl http://127.0.0.1:5000/api/jobs
```

**Response** `200`:

```json
{
  "jobs": [
    {
      "job_id": "a1b2c3d4",
      "status": "completed",
      "session_id": "f9e8d7c6",
      "domain": "example.com",
      "total_findings": 5,
      "pages_tested": 3,
      "current_url": null,
      "error": null,
      "created_at": "2026-04-11T14:30:00.000000"
    }
  ]
}
```

> Jobs live in memory only. Restarting the server clears the list. Use [`/api/sessions`](#get-apisessions) for persistent history.

---

## Sessions

Sessions are persisted to disk as JSON reports in the `output/` directory. Both CLI and web runs appear here.

### GET /api/sessions

List past sessions from the `output/` directory. Results are cached for 60 seconds.

```bash
# All sessions (paginated)
curl "http://127.0.0.1:5000/api/sessions?limit=10&offset=0"

# Filter by domain
curl "http://127.0.0.1:5000/api/sessions?domain=example.com"
```

| Parameter | Default | Description |
|---|---|---|
| `domain` | — | Filter sessions to a single domain |
| `limit` | `50` | Max sessions to return |
| `offset` | `0` | Pagination offset |

**Response** `200`:

```json
{
  "sessions": [
    {
      "session_id": "f9e8d7c6",
      "domain": "example.com",
      "start_time": "2026-04-11T14:30:00",
      "end_time": "2026-04-11T14:30:45",
      "duration_seconds": 45.2,
      "urls": ["https://example.com"],
      "pages_tested": 3,
      "total_findings": 5,
      "findings_by_severity": { "high": 1, "medium": 3, "low": 1 },
      "status": "issues_found"
    }
  ],
  "total": 1,
  "limit": 10,
  "offset": 0
}
```

| `status` value | Meaning |
|---|---|
| `passed` | No findings |
| `issues_found` | One or more findings |
| `no_pages_tested` | Run completed but tested zero pages |

---

### GET /api/session/:domain/:session_id

Full detail for a single session, including all findings, report links, screenshots, and recordings.

```bash
curl http://127.0.0.1:5000/api/session/example.com/f9e8d7c6
```

**Response** `200`:

```json
{
  "session_id": "f9e8d7c6",
  "domain": "example.com",
  "start_time": "2026-04-11T14:30:00",
  "end_time": "2026-04-11T14:30:45",
  "duration_seconds": 45.2,
  "config_summary": { "urls": ["https://example.com"], "mode": "focused" },
  "pages_tested": 3,
  "total_findings": 5,
  "unique_findings": 4,
  "findings_by_severity": { "high": 1, "medium": 3, "low": 1 },
  "findings_by_category": { "accessibility": 3, "keyboard_navigation": 2 },
  "status": "issues_found",
  "findings": [
    {
      "title": "Image missing alt text",
      "description": "…",
      "category": "accessibility",
      "severity": "medium",
      "url": "https://example.com",
      "timestamp": "2026-04-11T14:30:12",
      "element_selector": "img.hero",
      "element_text": null,
      "screenshot_path": "example.com/f9e8d7c6/screenshots/…",
      "steps_to_reproduce": [],
      "expected_behavior": "Image should have descriptive alt text",
      "actual_behavior": "alt attribute is empty",
      "raw_error": null,
      "metadata": {},
      "affected_urls": ["https://example.com", "https://example.com/about"]
    }
  ],
  "reports": {
    "markdown": "/files/example.com/f9e8d7c6/qa_reports/qa_report_….md",
    "json": "/files/example.com/f9e8d7c6/qa_reports/qa_report_….json",
    "pdf": "/files/example.com/f9e8d7c6/qa_reports/qa_report_….pdf"
  },
  "screenshots": [
    "/files/example.com/f9e8d7c6/screenshots/error_20260411_143012.png"
  ],
  "recording": "/files/example.com/f9e8d7c6/recordings/session.webm"
}
```

**Error** `404` — session not found.

---

## Files

### GET /files/:path

Serve output files (reports, screenshots, recordings) from the `output/` directory.

```bash
# Download a JSON report
curl http://127.0.0.1:5000/files/example.com/f9e8d7c6/qa_reports/qa_report_20260411.json

# View a screenshot
curl http://127.0.0.1:5000/files/example.com/f9e8d7c6/screenshots/error_20260411.png
```

- **Markdown** (`.md`) files are rendered as HTML with syntax highlighting.
- **JSON** (`.json`) files are pretty-printed in an HTML wrapper.
- All other files are served with their native MIME type.

Path traversal is blocked — requests that resolve outside `output/` return `403`.

---

## Request Body Reference

The [`POST /api/run`](#post-apirun) endpoint accepts a JSON object. Only `urls` is required; all other fields have sensible defaults matching the CLI.

### Core

| Field | Type | Default | Description |
|---|---|---|---|
| `urls` | string[] | *(required)* | URLs to test |
| `mode` | string | `"focused"` | `"focused"` or `"explore"` |
| `output_formats` | string[] | `["console","markdown","json"]` | Any of `console`, `markdown`, `json`, `pdf` |
| `output_dir` | string | `"./output"` | Directory for reports and screenshots |

### Browser

| Field | Type | Default | Description |
|---|---|---|---|
| `headless` | boolean | `true` | Run browser in headless mode |
| `viewport_width` | integer | `1280` | Browser viewport width in pixels |
| `viewport_height` | integer | `720` | Browser viewport height in pixels |
| `timeout` | integer | `30000` | Page load timeout in milliseconds |

### Exploration (explore mode)

| Field | Type | Default | Description |
|---|---|---|---|
| `max_depth` | integer | `3` | Maximum link depth |
| `max_pages` | integer | `100` | Maximum pages to test |
| `max_interactions_per_page` | integer | `50` | Maximum interactions per page |
| `same_domain_only` | boolean | `true` | Stay within the same domain |
| `ignore_patterns` | string[] | `[]` | URL regex patterns to skip |

### Test Suites

| Field | Type | Default | Description |
|---|---|---|---|
| `test_keyboard` | boolean | `true` | Run keyboard navigation tests |
| `test_mouse` | boolean | `true` | Run mouse interaction tests |
| `test_forms` | boolean | `true` | Run form handling tests |
| `test_accessibility` | boolean | `true` | Run accessibility tests |
| `test_console_errors` | boolean | `true` | Detect console errors |
| `test_network_errors` | boolean | `true` | Detect network errors |
| `test_wcag_compliance` | boolean | `false` | Run WCAG 2.1 AA compliance (opt-in) |

### Agentic Testing

| Field | Type | Default | Description |
|---|---|---|---|
| `instructions` | string | `null` | Natural-language test instructions for the LLM |
| `llm_provider` | string | `"anthropic"` | `"anthropic"` or `"openai"` |
| `ai_model` | string | `null` | Model override (e.g. `"gpt-4o-mini"`) |
| `use_plan_cache` | boolean | `true` | Use the 24-hour plan cache |

### Authentication

Pass an `auth` object:

```json
{
  "auth": {
    "username": "testuser",
    "password": "testpass",
    "auth_url": "https://example.com/login",
    "username_selector": "input#email",
    "password_selector": "input#password",
    "submit_selector": "button[type=submit]",
    "cookies": [{ "name": "session", "value": "abc123", "domain": "example.com" }],
    "headers": { "Authorization": "Bearer token123" }
  }
}
```

`cookies` and `headers` can be JSON strings or objects. All fields are optional.

### Screenshots

Pass a `screenshots` object:

```json
{
  "screenshots": {
    "enabled": true,
    "on_error": true,
    "on_interaction": false,
    "full_page": false
  }
}
```

`on_error` requires `enabled`. `on_interaction` requires `on_error`.

### Recording

Pass a `recording` object:

```json
{
  "recording": {
    "enabled": false,
    "video_size": { "width": 1280, "height": 720 }
  }
}
```

---

## SSE Event Types

The [`/api/stream/:job_id`](#get-apistreamjob_id) endpoint emits the following Server-Sent Events:

| Event | Data fields | Description |
|---|---|---|
| `log` | `message` | A line of console output (ANSI codes stripped) |
| `progress` | `url`, `message` | Emitted when the agent starts testing a new page |
| `finding` | `severity`, `title` | Emitted for each finding as it's discovered |
| `complete` | `session_id`, `domain`, `total_findings`, `status` | Emitted once when the run finishes |
| `error` | `message` | Emitted if the run fails with an exception |

### Example SSE stream

```
event: log
data: {"message": "QA Agent v0.2.0 — starting test run"}

event: progress
data: {"url": "https://example.com", "message": "Testing: https://example.com"}

event: finding
data: {"severity": "medium", "title": "Image missing alt text"}

event: complete
data: {"session_id": "f9e8d7c6", "domain": "example.com", "total_findings": 3, "status": "completed"}
```

### JavaScript client example

```javascript
const source = new EventSource("/api/stream/a1b2c3d4");

source.addEventListener("log", (e) => {
  console.log(JSON.parse(e.data).message);
});

source.addEventListener("finding", (e) => {
  const { severity, title } = JSON.parse(e.data);
  console.warn(`[${severity.toUpperCase()}] ${title}`);
});

source.addEventListener("complete", (e) => {
  const { total_findings, status } = JSON.parse(e.data);
  console.log(`Done — ${total_findings} findings (${status})`);
  source.close();
});

source.addEventListener("error", (e) => {
  console.error("Stream error", e);
  source.close();
});
```
