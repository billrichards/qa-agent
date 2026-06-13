"""Tests for qa_agent/rate_limiter.py — per-host navigation throttling."""

from __future__ import annotations

import threading

from qa_agent.rate_limiter import HostRateLimiter


class TestDisabled:
    def test_zero_rate_is_disabled(self):
        assert HostRateLimiter(0).enabled is False

    def test_negative_rate_is_disabled(self):
        assert HostRateLimiter(-1).enabled is False

    def test_disabled_acquire_never_sleeps(self, monkeypatch):
        sleep_calls = []
        monkeypatch.setattr("qa_agent.rate_limiter.time.sleep", lambda s: sleep_calls.append(s))
        limiter = HostRateLimiter(0)
        limiter.acquire("example.com")
        limiter.acquire("example.com")
        assert sleep_calls == []


class TestEnabled:
    def test_positive_rate_is_enabled(self):
        assert HostRateLimiter(3.0).enabled is True

    def test_first_request_no_wait(self, monkeypatch):
        monkeypatch.setattr("qa_agent.rate_limiter.time.monotonic", lambda: 100.0)
        sleep_calls = []
        monkeypatch.setattr("qa_agent.rate_limiter.time.sleep", lambda s: sleep_calls.append(s))

        limiter = HostRateLimiter(2.0)  # min interval 0.5s
        limiter.acquire("example.com")
        assert sleep_calls == []

    def test_second_request_within_interval_sleeps(self, monkeypatch):
        clock = [100.0]
        monkeypatch.setattr("qa_agent.rate_limiter.time.monotonic", lambda: clock[0])

        sleep_calls = []

        def fake_sleep(seconds):
            sleep_calls.append(seconds)
            clock[0] += seconds

        monkeypatch.setattr("qa_agent.rate_limiter.time.sleep", fake_sleep)

        limiter = HostRateLimiter(2.0)  # min interval 0.5s
        limiter.acquire("example.com")  # t=100.0, no wait
        limiter.acquire("example.com")  # still t=100.0 -> must wait 0.5s
        assert sleep_calls == [0.5]

    def test_request_after_interval_does_not_sleep(self, monkeypatch):
        clock = [100.0]
        monkeypatch.setattr("qa_agent.rate_limiter.time.monotonic", lambda: clock[0])
        sleep_calls = []
        monkeypatch.setattr("qa_agent.rate_limiter.time.sleep", lambda s: sleep_calls.append(s))

        limiter = HostRateLimiter(2.0)  # min interval 0.5s
        limiter.acquire("example.com")  # t=100.0
        clock[0] = 100.5
        limiter.acquire("example.com")  # exactly one interval later -> no wait
        assert sleep_calls == []

    def test_different_hosts_have_independent_budgets(self, monkeypatch):
        monkeypatch.setattr("qa_agent.rate_limiter.time.monotonic", lambda: 100.0)
        sleep_calls = []
        monkeypatch.setattr("qa_agent.rate_limiter.time.sleep", lambda s: sleep_calls.append(s))

        limiter = HostRateLimiter(2.0)
        limiter.acquire("a.example.com")
        limiter.acquire("b.example.com")
        assert sleep_calls == []


class TestThreadSafety:
    def test_concurrent_acquires_complete_without_error(self):
        """A high (but non-zero) rate keeps this fast while exercising the lock."""
        limiter = HostRateLimiter(1000.0)  # 1ms min interval
        results: list[int] = []
        lock = threading.Lock()

        def worker():
            limiter.acquire("example.com")
            with lock:
                results.append(1)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(results) == 10
