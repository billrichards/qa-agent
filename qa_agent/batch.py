"""Bounded pool for running multiple QA sessions concurrently.

This is the *job-level* (layer 2) concurrency, distinct from the per-run
page-worker concurrency in :mod:`qa_agent.concurrency`. A :class:`BatchRunner`
owns a bounded :class:`~concurrent.futures.ThreadPoolExecutor`; each submitted
:class:`~qa_agent.config.TestConfig` runs a full ``QAAgent(config).run()`` on a
pool thread. It is shared by both the web server (replacing its unbounded
thread-per-job model) and the CLI/library ``batch`` entry point, so all three
usage modes get the same bounded, back-pressured behaviour.

Note: page-workers (``config.workers``) are spawned *within* each pool thread,
so the total live browsers ≈ ``pool_size × workers``. Size both with that
multiplicative cost in mind.
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field

from .agent import QAAgent
from .config import TestConfig
from .models import TestSession
from .rate_limiter import HostRateLimiter

DEFAULT_POOL_SIZE = 4
POOL_SIZE_MAX = 8


@dataclass
class BatchJob:
    """Handle for a single submitted session."""

    job_id: str
    future: Future[TestSession]
    agent: QAAgent
    stop_event: threading.Event
    session_id: str
    domain: str = ""
    _started: threading.Event = field(default_factory=threading.Event)

    @property
    def status(self) -> str:
        """Derive a coarse status from the underlying future."""
        if self.future.cancelled():
            return "stopped"
        if self.future.done():
            return "failed" if self.future.exception() is not None else "completed"
        if self._started.is_set():
            return "running"
        return "queued"

    def result(self, timeout: float | None = None) -> TestSession:
        """Block for the session result (re-raises any worker exception)."""
        return self.future.result(timeout=timeout)

    def stop(self) -> None:
        """Request a graceful stop (and cancel if still queued)."""
        self.stop_event.set()
        self.future.cancel()


class BatchRunner:
    """Run multiple :class:`TestConfig` sessions with bounded concurrency."""

    def __init__(
        self,
        pool_size: int = DEFAULT_POOL_SIZE,
        thread_name_prefix: str = "qa-job",
        rate_limit: float | None = None,
    ):
        self.pool_size = max(1, min(POOL_SIZE_MAX, int(pool_size)))
        self._executor = ThreadPoolExecutor(
            max_workers=self.pool_size, thread_name_prefix=thread_name_prefix
        )
        # Shared per-host rate limiter so concurrent batch jobs targeting the
        # same host (e.g. multiple specs against the same dev server) share
        # one navigation budget rather than each getting an independent
        # allowance. None → each QAAgent builds its own from config.rate_limit.
        self._rate_limiter: HostRateLimiter | None = (
            HostRateLimiter(rate_limit) if rate_limit is not None else None
        )

    def submit(
        self,
        config: TestConfig,
        *,
        worker_thread_init=None,
        stop_event: threading.Event | None = None,
        job_id: str | None = None,
    ) -> BatchJob:
        """Submit one session to the pool and return its :class:`BatchJob`."""
        stop_event = stop_event if stop_event is not None else threading.Event()
        agent = QAAgent(
            config,
            worker_thread_init=worker_thread_init,
            rate_limiter=self._rate_limiter,
        )
        agent.stop_event = stop_event

        domain = ""
        if config.urls:
            from urllib.parse import urlparse
            domain = urlparse(config.urls[0]).netloc.split(":")[0]

        job = BatchJob(
            job_id=job_id or str(uuid.uuid4())[:8],
            future=None,  # type: ignore[arg-type]  # set just below
            agent=agent,
            stop_event=stop_event,
            session_id=agent.session_id,
            domain=domain,
        )

        def _task() -> TestSession:
            job._started.set()
            # Initialise this pool thread (e.g. route its stdout) before running.
            # The agent calls the same hook again on each page-worker sub-thread;
            # it is thread-local and idempotent, so both layers are covered.
            if worker_thread_init is not None:
                try:
                    worker_thread_init()
                except Exception:
                    pass
            return agent.run()

        job.future = self._executor.submit(_task)
        return job

    def run_all(self, configs: list[TestConfig]) -> list[TestSession | Exception]:
        """Submit all configs, wait, and return results in input order.

        A failing session yields its exception in place rather than aborting the
        whole batch.
        """
        jobs = [self.submit(cfg) for cfg in configs]
        results: list[TestSession | Exception] = []
        for job in jobs:
            try:
                results.append(job.result())
            except Exception as exc:  # noqa: BLE001 - isolate per-job failure
                results.append(exc)
        return results

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)

    def __enter__(self) -> BatchRunner:
        return self

    def __exit__(self, *exc) -> None:
        self.shutdown(wait=True)
