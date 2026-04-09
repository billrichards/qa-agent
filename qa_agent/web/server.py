"""Flask web server for QA Agent."""

import io
import json
import queue
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from flask import Flask, Response, abort, jsonify, render_template, request, send_file

from ..agent import QAAgent
from ..config import (
    AuthConfig,
    OutputFormat,
    RecordingConfig,
    ScreenshotConfig,
    TestConfig,
    TestMode,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent      # qa_agent/web/
_PROJECT_ROOT = _HERE.parent.parent          # project root
OUTPUT_DIR = _PROJECT_ROOT / "output"

# ── Flask app ──────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder=str(_HERE / "templates"))

# ── Thread-local stdout multiplexer ───────────────────────────────────────────
# Redirects print() calls in job threads to their per-job queue without
# interfering with the main thread's stdout.

_local = threading.local()
_original_stdout = sys.stdout


class _MultiplexedStdout:
    """sys.stdout replacement that routes writes to the current thread's stream."""

    def write(self, text: str) -> int:
        stream = getattr(_local, "stream", None)
        if stream is not None:
            return int(stream.write(text))
        return _original_stdout.write(text)

    def flush(self) -> None:
        stream = getattr(_local, "stream", None)
        if stream is not None:
            stream.flush()
        else:
            _original_stdout.flush()

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:
        raise io.UnsupportedOperation("no fileno for multiplexed stdout")


sys.stdout = _MultiplexedStdout()  # type: ignore[assignment]


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class _QueueWriter:
    """Writes stdout lines into a job's event queue as SSE-ready dicts."""

    def __init__(self, q: queue.Queue, events: list) -> None:
        self._q = q
        self._events = events
        self._buf = ""

    def write(self, text: str) -> int:
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            clean = _ANSI_RE.sub("", line)
            if clean.strip():
                self._emit("log", {"message": clean})
                self._detect_structured(clean)
        return len(text)

    def flush(self) -> None:
        pass

    def _emit(self, event_type: str, data: dict) -> None:
        msg = {"type": event_type, "data": data}
        self._events.append(msg)
        self._q.put(msg)

    def _detect_structured(self, line: str) -> None:
        # Page start: "Testing: <url>"
        m = re.search(r"Testing:\s+(https?://\S+)", line)
        if m:
            self._emit("progress", {"url": m.group(1), "message": line.strip()})
            return

        # Finding: "[SEVERITY] <title>"
        m = re.search(r"\[(CRITICAL|HIGH|MEDIUM|LOW|INFO)\]\s+(.+)", line, re.IGNORECASE)
        if m:
            self._emit("finding", {
                "severity": m.group(1).lower(),
                "title": m.group(2).strip(),
            })


# ── Job management ─────────────────────────────────────────────────────────────

_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _make_job(job_id: str) -> dict:
    return {
        "job_id": job_id,
        "status": "queued",
        "queue": queue.Queue(),
        "events": [],         # full replay buffer
        "stop_event": threading.Event(),
        "session_id": None,
        "domain": None,
        "total_findings": 0,
        "current_url": None,
        "pages_tested": 0,
        "error": None,
        "created_at": datetime.now().isoformat(),
    }


def _run_job(job_id: str, config: TestConfig) -> None:
    """Execute QAAgent in a background thread, streaming output to the job queue."""
    job = _jobs[job_id]
    q = job["queue"]
    events = job["events"]
    writer = _QueueWriter(q, events)
    _local.stream = writer

    try:
        job["status"] = "running"
        agent = QAAgent(config)
        agent.stop_event = job["stop_event"]

        # Capture session_id and domain before run() (agent sets them in __init__)
        job["session_id"] = agent.session_id
        domain = urlparse(config.urls[0]).netloc.split(":")[0] if config.urls else "unknown"
        job["domain"] = domain

        session = agent.run()

        job["total_findings"] = session.total_findings
        job["pages_tested"] = len(session.pages_tested)

        if job["stop_event"].is_set():
            job["status"] = "stopped"
            status = "stopped"
        else:
            job["status"] = "completed"
            status = "completed"

        complete_data = {
            "session_id": session.session_id,
            "domain": domain,
            "total_findings": session.total_findings,
            "status": status,
        }
        msg = {"type": "complete", "data": complete_data}
        events.append(msg)
        q.put(msg)

    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        msg = {"type": "error", "data": {"message": str(exc)}}
        events.append(msg)
        q.put(msg)

    finally:
        q.put(None)  # sentinel — stream generator stops here
        _local.stream = None


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/run/<job_id>")
def run_view(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        abort(404)
    return render_template("run.html", job_id=job_id)


@app.route("/sessions")
def sessions_view():
    return render_template("sessions.html")


@app.route("/session/<domain>/<session_id>")
def session_view(domain: str, session_id: str):
    data = _load_session(domain, session_id)
    if data is None:
        abort(404)
    return render_template("session.html", session=data, domain=domain)


# ── API ────────────────────────────────────────────────────────────────────────

@app.route("/api/run", methods=["POST"])
def api_run():
    body = request.get_json(force=True, silent=True) or {}

    # Validate URLs
    urls = body.get("urls", [])
    if not urls or not isinstance(urls, list):
        return jsonify({"error": "urls is required and must be a non-empty list"}), 400

    # Build config
    try:
        config = _build_config(body)
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400

    import uuid
    job_id = str(uuid.uuid4())[:8]
    job = _make_job(job_id)
    with _jobs_lock:
        _jobs[job_id] = job

    t = threading.Thread(target=_run_job, args=(job_id, config), daemon=True)
    t.start()

    return jsonify({
        "job_id": job_id,
        "status": "running",
        "stream_url": f"/api/stream/{job_id}",
    }), 202


@app.route("/api/stream/<job_id>")
def api_stream(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404

    def generate():
        # Replay buffered events for late-joining clients
        cursor = 0
        while True:
            # Drain buffered events first
            snapshot = job["events"]
            while cursor < len(snapshot):
                msg = snapshot[cursor]
                cursor += 1
                yield f"event: {msg['type']}\ndata: {json.dumps(msg['data'])}\n\n"

            # Check if job is done
            if job["status"] in ("completed", "failed", "stopped"):
                break

            # Wait for the next event via queue (timeout for keep-alive)
            try:
                msg = job["queue"].get(timeout=25)
                if msg is None:
                    break
                # It's already in the events buffer, cursor will catch it on next loop
            except queue.Empty:
                yield ": keep-alive\n\n"

    resp = Response(generate(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


@app.route("/api/status/<job_id>")
def api_status(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "job_id": job_id,
        "status": job["status"],
        "session_id": job["session_id"],
        "domain": job["domain"],
        "total_findings": job["total_findings"],
        "pages_tested": job["pages_tested"],
        "error": job["error"],
    })


@app.route("/api/stop/<job_id>", methods=["POST"])
def api_stop(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] in ("completed", "failed", "stopped"):
        return jsonify({"error": "Job already finished"}), 400

    job["stop_event"].set()
    return jsonify({"job_id": job_id, "status": "stopping"})


@app.route("/api/jobs")
def api_jobs():
    """Return all active (non-completed) in-memory jobs."""
    with _jobs_lock:
        jobs_snapshot = list(_jobs.values())

    result = []
    for job in jobs_snapshot:
        result.append({
            "job_id": job["job_id"],
            "status": job["status"],
            "session_id": job["session_id"],
            "domain": job["domain"],
            "total_findings": job["total_findings"],
            "pages_tested": job["pages_tested"],
            "current_url": job["current_url"],
            "error": job["error"],
            "created_at": job["created_at"],
        })

    # Most recent first
    result.sort(key=lambda j: j["created_at"], reverse=True)
    return jsonify({"jobs": result})


@app.route("/api/sessions")
def api_sessions():
    domain = request.args.get("domain")
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    return jsonify(_scan_sessions(domain_filter=domain, limit=limit, offset=offset))


@app.route("/api/session/<domain>/<session_id>")
def api_session_detail(domain: str, session_id: str):
    data = _load_session(domain, session_id)
    if data is None:
        return jsonify({"error": "Session not found"}), 404
    return jsonify(data)


@app.route("/files/<path:filepath>")
def serve_file(filepath: str):
    """Serve output files (reports, screenshots, recordings)."""
    abs_path = OUTPUT_DIR / filepath
    # Security: ensure path stays within OUTPUT_DIR
    try:
        abs_path.resolve().relative_to(OUTPUT_DIR.resolve())
    except ValueError:
        abort(403)

    if not abs_path.exists():
        abort(404)

    suffix = abs_path.suffix.lower()

    if suffix == ".md":
        content = abs_path.read_text(encoding="utf-8")
        try:
            import markdown as md_lib  # type: ignore[import-untyped]
            html_body = md_lib.markdown(content, extensions=["fenced_code", "tables"])
        except ImportError:
            html_body = f"<pre>{content}</pre>"
        html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>{abs_path.name}</title>
<style>body{{font-family:system-ui;max-width:900px;margin:2rem auto;padding:0 1rem;line-height:1.6;}}
pre{{background:#1e1e1e;color:#d4d4d4;padding:1rem;overflow-x:auto;border-radius:4px;}}
</style></head><body>{html_body}</body></html>"""
        return Response(html, mimetype="text/html")

    if suffix == ".json":
        import html as html_lib
        data = json.loads(abs_path.read_text(encoding="utf-8"))
        pretty = html_lib.escape(json.dumps(data, indent=2))
        html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>{abs_path.name}</title>
<style>body{{background:#1e1e1e;color:#d4d4d4;font-family:monospace;font-size:13px;padding:1rem;margin:0;}}
pre{{white-space:pre-wrap;word-break:break-all;}}</style></head>
<body><pre>{pretty}</pre></body></html>"""
        return Response(html, mimetype="text/html")

    return send_file(abs_path)


# ── Session discovery ──────────────────────────────────────────────────────────

_session_cache: dict = {}
_session_cache_time: float = 0.0
_CACHE_TTL = 60.0  # seconds


def _scan_sessions(
    domain_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    global _session_cache, _session_cache_time

    now = time.time()
    if now - _session_cache_time < _CACHE_TTL and not domain_filter:
        sessions = _session_cache.get("all", [])
    else:
        sessions = _build_session_list()
        _session_cache["all"] = sessions
        _session_cache_time = now

    if domain_filter:
        sessions = [s for s in sessions if s["domain"] == domain_filter]

    total = len(sessions)
    return {
        "sessions": sessions[offset : offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _build_session_list() -> list:
    sessions: list[dict] = []
    if not OUTPUT_DIR.exists():
        return sessions

    for domain_dir in OUTPUT_DIR.iterdir():
        if not domain_dir.is_dir():
            continue
        domain = domain_dir.name

        for session_dir in domain_dir.iterdir():
            if not session_dir.is_dir():
                continue
            session_id = session_dir.name

            reports_dir = session_dir / "qa_reports"
            if not reports_dir.exists():
                continue

            json_files = sorted(reports_dir.glob("qa_report_*.json"))
            if not json_files:
                continue

            try:
                data = json.loads(json_files[0].read_text(encoding="utf-8"))
                meta = data.get("meta", {})
                summary = data.get("summary", {})
                sessions.append({
                    "session_id": meta.get("session_id", session_id),
                    "domain": domain,
                    "start_time": meta.get("start_time"),
                    "end_time": meta.get("end_time"),
                    "duration_seconds": meta.get("duration_seconds"),
                    "urls": meta.get("config", {}).get("urls", []),
                    "total_findings": summary.get("total_findings", 0),
                    "findings_by_severity": summary.get("findings_by_severity", {}),
                })
            except Exception:
                continue

    sessions.sort(key=lambda s: s.get("start_time") or "", reverse=True)
    return sessions


def _load_session(domain: str, session_id: str) -> dict | None:
    session_dir = OUTPUT_DIR / domain / session_id
    if not session_dir.exists():
        return None

    reports_dir = session_dir / "qa_reports"
    json_files = sorted(reports_dir.glob("qa_report_*.json")) if reports_dir.exists() else []
    if not json_files:
        return None

    try:
        data = json.loads(json_files[0].read_text(encoding="utf-8"))
    except Exception:
        return None

    meta = data.get("meta", {})
    summary = data.get("summary", {})
    findings = data.get("findings", [])

    # Collect report file links
    reports: dict[str, str] = {}
    screenshots: list[str] = []
    recording: str | None = None

    if reports_dir.exists():
        for f in reports_dir.iterdir():
            rel = f.relative_to(OUTPUT_DIR)
            if f.suffix == ".md":
                reports["markdown"] = f"/files/{rel}"
            elif f.suffix == ".json":
                reports.setdefault("json", f"/files/{rel}")
            elif f.suffix == ".pdf":
                reports["pdf"] = f"/files/{rel}"

    screenshots_dir = session_dir / "screenshots"
    if screenshots_dir.exists():
        for f in sorted(screenshots_dir.iterdir()):
            if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                screenshots.append(f"/files/{f.relative_to(OUTPUT_DIR)}")

    recordings_dir = session_dir / "recordings"
    if recordings_dir.exists():
        for f in recordings_dir.iterdir():
            if f.suffix.lower() in (".webm", ".mp4"):
                recording = f"/files/{f.relative_to(OUTPUT_DIR)}"
                break

    # Convert absolute screenshot_path values to OUTPUT_DIR-relative paths
    # so the template can build correct /files/<rel> URLs.
    for finding in findings:
        sp = finding.get("screenshot_path")
        if sp:
            sp_path = Path(sp)
            try:
                rel = sp_path.relative_to(OUTPUT_DIR)
                finding["screenshot_path"] = str(rel)
            except ValueError:
                pass  # already relative or outside OUTPUT_DIR — leave as-is

    return {
        "session_id": meta.get("session_id", session_id),
        "domain": domain,
        "start_time": meta.get("start_time"),
        "end_time": meta.get("end_time"),
        "duration_seconds": meta.get("duration_seconds"),
        "config_summary": meta.get("config", {}),
        "pages_tested": summary.get("pages_tested", 0),
        "total_findings": summary.get("total_findings", 0),
        "unique_findings": summary.get("unique_findings", 0),
        "findings_by_severity": summary.get("findings_by_severity", {}),
        "findings_by_category": summary.get("findings_by_category", {}),
        "findings": findings,
        "reports": reports,
        "screenshots": screenshots,
        "recording": recording,
    }


# ── Config builder ─────────────────────────────────────────────────────────────

def _build_config(body: dict) -> TestConfig:
    """Convert JSON request body into a TestConfig."""
    urls = body["urls"]
    mode_str = body.get("mode", "focused").lower()
    mode = TestMode.EXPLORE if mode_str == "explore" else TestMode.FOCUSED

    fmt_strs = body.get("output_formats", ["console", "markdown", "json"])
    fmt_map = {
        "console": OutputFormat.CONSOLE,
        "markdown": OutputFormat.MARKDOWN,
        "json": OutputFormat.JSON,
        "pdf": OutputFormat.PDF,
    }
    output_formats = [fmt_map[f] for f in fmt_strs if f in fmt_map]
    # Always include JSON so sessions are discoverable
    if OutputFormat.JSON not in output_formats:
        output_formats.append(OutputFormat.JSON)

    auth_data = body.get("auth") or {}
    auth: AuthConfig | None = None
    if any(auth_data.get(k) for k in ("username", "cookies", "headers", "auth_url")):
        cookies = auth_data.get("cookies")
        if isinstance(cookies, str) and cookies.strip():
            try:
                cookies = json.loads(cookies)
            except json.JSONDecodeError:
                cookies = None
        headers = auth_data.get("headers")
        if isinstance(headers, str) and headers.strip():
            try:
                headers = json.loads(headers)
            except json.JSONDecodeError:
                headers = None
        auth = AuthConfig(
            username=auth_data.get("username") or None,
            password=auth_data.get("password") or None,
            auth_url=auth_data.get("auth_url") or None,
            username_selector=auth_data.get("username_selector") or None,
            password_selector=auth_data.get("password_selector") or None,
            submit_selector=auth_data.get("submit_selector") or None,
            cookies=cookies,
            headers=headers,
        )

    ss_data = body.get("screenshots") or {}
    rec_data = body.get("recording") or {}

    # Enforce screenshot dependencies matching CLI behaviour:
    #   on_error and full_page require enabled
    #   on_interaction requires on_error (mirrors --screenshots-all coupling)
    ss_enabled = bool(ss_data.get("enabled", True))
    ss_on_error = bool(ss_data.get("on_error", True)) and ss_enabled
    ss_on_interaction = bool(ss_data.get("on_interaction", False)) and ss_on_error
    ss_full_page = bool(ss_data.get("full_page", False)) and ss_enabled

    return TestConfig(
        urls=urls,
        mode=mode,
        output_formats=output_formats,
        output_dir=str(body.get("output_dir") or OUTPUT_DIR),
        headless=bool(body.get("headless", True)),
        viewport_width=int(body.get("viewport_width", 1280)),
        viewport_height=int(body.get("viewport_height", 720)),
        timeout=int(body.get("timeout", 30000)),
        max_depth=int(body.get("max_depth", 3)),
        max_pages=int(body.get("max_pages", 20)),
        max_interactions_per_page=int(body.get("max_interactions_per_page", 50)),
        test_keyboard=bool(body.get("test_keyboard", True)),
        test_mouse=bool(body.get("test_mouse", True)),
        test_forms=bool(body.get("test_forms", True)),
        test_accessibility=bool(body.get("test_accessibility", True)),
        test_console_errors=bool(body.get("test_console_errors", True)),
        test_network_errors=bool(body.get("test_network_errors", True)),
        test_wcag_compliance=bool(body.get("test_wcag_compliance", False)),
        ignore_patterns=body.get("ignore_patterns", []),
        same_domain_only=bool(body.get("same_domain_only", True)),
        instructions=body.get("instructions") or None,
        ai_model=body.get("ai_model", "claude-sonnet-4-6"),
        use_plan_cache=bool(body.get("use_plan_cache", True)),
        auth=auth,
        screenshots=ScreenshotConfig(
            enabled=ss_enabled,
            on_error=ss_on_error,
            on_interaction=ss_on_interaction,
            full_page=ss_full_page,
        ),
        recording=RecordingConfig(
            enabled=bool(rec_data.get("enabled", False)),
            video_size=rec_data.get("video_size", {"width": 1280, "height": 720}),
        ),
    )


# ── Entry point ────────────────────────────────────────────────────────────────

def serve_web(host: str = "127.0.0.1", port: int = 5000, debug: bool = False) -> None:
    """Start the Flask development server."""
    print(f"QA Agent web interface running at http://{host}:{port}", file=_original_stdout)
    app.run(host=host, port=port, debug=debug, threaded=True, use_reloader=False)


def serve_web_cli() -> None:
    """Entry point for `qa-agent web` subcommand."""
    import argparse
    parser = argparse.ArgumentParser(description="QA Agent Web Interface")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    args = parser.parse_args()
    serve_web(host=args.host, port=args.port, debug=args.debug)
