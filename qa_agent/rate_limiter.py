"""Thread-safe per-host request rate limiting.

Used to pace outgoing ``page.goto()`` navigations against a single host so
concurrent page-workers / batch sessions don't overwhelm a target server with
"too many connections" bursts.
"""

from __future__ import annotations

import threading
import time


class HostRateLimiter:
    """Enforces a minimum interval between navigations to the same hostname.

    ``requests_per_second <= 0`` disables throttling entirely; ``acquire()``
    then becomes a no-op with no locking overhead.
    """

    def __init__(self, requests_per_second: float) -> None:
        self._rate = float(requests_per_second)
        self._min_interval = (1.0 / self._rate) if self._rate > 0 else 0.0
        self._lock = threading.Lock()
        self._last_request: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        return self._rate > 0

    def acquire(self, hostname: str) -> None:
        """Block until it is safe to issue the next request to ``hostname``."""
        if not self.enabled:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                last = self._last_request.get(hostname)
                if last is None or (now - last) >= self._min_interval:
                    self._last_request[hostname] = now
                    return
                wait = self._min_interval - (now - last)
            time.sleep(wait)
