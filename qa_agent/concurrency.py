"""Thread-safe primitives for running page-workers concurrently.

These helpers let multiple worker threads cooperate on a single test run:

* :class:`Frontier` is a thread-safe BFS frontier shared by all workers. It
  enforces the ``max_pages`` / ``max_depth`` budget *correctly under
  concurrency* (a URL is marked visited the moment it is claimed, so N workers
  can never overshoot the page budget) and coordinates clean termination — a
  worker's :meth:`Frontier.claim` returns ``None`` only when the queue is empty
  **and** no other worker is still in-flight (so no links remain to discover).

The actual per-page work and Playwright lifecycle live in :mod:`qa_agent.agent`;
this module is deliberately free of any browser dependency so it can be unit
tested without Playwright.
"""

from __future__ import annotations

import itertools
import threading


class Frontier:
    """A thread-safe BFS frontier with a page/depth budget.

    Parameters
    ----------
    max_pages:
        Maximum number of distinct URLs that may be claimed across all workers.
    max_depth:
        Maximum BFS depth. URLs deeper than this are never claimed, and
        :meth:`add_links` will not enqueue children beyond it.
    stop_event:
        Optional :class:`threading.Event`; when set, :meth:`claim` returns
        ``None`` so workers wind down promptly.
    """

    def __init__(
        self,
        max_pages: int,
        max_depth: int,
        stop_event: threading.Event | None = None,
    ) -> None:
        self.max_pages = max(0, int(max_pages))
        self.max_depth = max(0, int(max_depth))
        self._stop_event = stop_event

        self._queue: list[str] = []          # FIFO of pending URLs
        self._depth: dict[str, int] = {}     # URL -> depth (queued or visited)
        self._visited: set[str] = set()      # claimed URLs (in-progress or done)
        self._in_progress = 0
        self._cond = threading.Condition()

    # -- seeding / enqueueing -------------------------------------------------

    def seed(self, urls: list[str], depth: int = 0) -> None:
        """Add the initial URLs at the given depth."""
        with self._cond:
            for url in urls:
                if url and url not in self._depth and url not in self._visited:
                    self._queue.append(url)
                    self._depth[url] = depth
            self._cond.notify_all()

    def add_links(self, urls: list[str], parent_depth: int) -> None:
        """Enqueue freshly discovered child URLs (deduped, depth-bounded)."""
        new_depth = parent_depth + 1
        if new_depth > self.max_depth:
            return
        with self._cond:
            for url in urls:
                if not url or url in self._depth or url in self._visited:
                    continue
                self._queue.append(url)
                self._depth[url] = new_depth
            self._cond.notify_all()

    # -- claiming / completing ------------------------------------------------

    def claim(self) -> tuple[str, int] | None:
        """Claim the next testable URL, or ``None`` when work is exhausted.

        Blocks while the queue is momentarily empty but other workers are still
        in-flight (they may yet discover new links). Returns ``None`` when the
        page budget is hit, ``stop_event`` is set, or the queue is drained and
        no worker is in-flight.
        """
        with self._cond:
            while True:
                if self._stop_event is not None and self._stop_event.is_set():
                    return None
                if len(self._visited) >= self.max_pages:
                    return None

                claimed = self._pop_claimable_locked()
                if claimed is not None:
                    url, depth = claimed
                    self._visited.add(url)
                    self._in_progress += 1
                    return claimed

                # Nothing claimable right now.
                if self._in_progress == 0:
                    return None  # queue drained and no one can enqueue more

                # Another worker is in-flight; wait for links or completion.
                self._cond.wait(timeout=0.5)

    def _pop_claimable_locked(self) -> tuple[str, int] | None:
        """Pop the next URL that is unvisited and within depth (caller holds lock)."""
        while self._queue:
            url = self._queue.pop(0)
            if url in self._visited:
                continue
            depth = self._depth.get(url, 0)
            if depth > self.max_depth:
                continue
            return (url, depth)
        return None

    def complete_one(self) -> None:
        """Signal that an in-flight page finished (wakes blocked claimers)."""
        with self._cond:
            if self._in_progress > 0:
                self._in_progress -= 1
            self._cond.notify_all()

    # -- introspection --------------------------------------------------------

    @property
    def visited_count(self) -> int:
        with self._cond:
            return len(self._visited)


class PageIndexer:
    """Hands out monotonically increasing, thread-safe page indices.

    Used for worker-safe screenshot filenames so concurrent workers never
    collide. Starts at 0 to match the legacy sequential naming
    (``page_0``, ``page_1``, …).
    """

    def __init__(self) -> None:
        self._counter = itertools.count()
        self._lock = threading.Lock()

    def next(self) -> int:
        with self._lock:
            return next(self._counter)
