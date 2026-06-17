"""Tests for the BatchRunner job pool (layer-2 concurrency)."""

from __future__ import annotations

import threading
import time

from qa_agent.batch import BatchRunner
from qa_agent.config import TestConfig, TestMode
from qa_agent.models import TestSession


def _cfg(url: str = "https://example.com") -> TestConfig:
    return TestConfig(urls=[url], mode=TestMode.FOCUSED)


class TestBatchRunner:
    def test_pool_size_clamped(self):
        assert BatchRunner(pool_size=999).pool_size <= 8
        assert BatchRunner(pool_size=0).pool_size == 1

    def test_run_all_preserves_order(self, monkeypatch):
        def fake_run(self):
            return TestSession(session_id=self.config.urls[0], start_time=__import__("datetime").datetime.now())

        monkeypatch.setattr("qa_agent.batch.QAAgent.run", fake_run, raising=True)
        with BatchRunner(pool_size=4) as runner:
            cfgs = [_cfg(f"https://example.com/{i}") for i in range(5)]
            results = runner.run_all(cfgs)
        assert [r.session_id for r in results if isinstance(r, TestSession)] == [
            f"https://example.com/{i}" for i in range(5)
        ]

    def test_per_job_exception_isolated(self, monkeypatch):
        def fake_run(self):
            if "boom" in self.config.urls[0]:
                raise RuntimeError("kaboom")
            return TestSession(session_id="ok", start_time=__import__("datetime").datetime.now())

        monkeypatch.setattr("qa_agent.batch.QAAgent.run", fake_run, raising=True)
        with BatchRunner(pool_size=4) as runner:
            results = runner.run_all([_cfg("https://example.com/ok"), _cfg("https://example.com/boom")])
        assert isinstance(results[0], TestSession)
        assert isinstance(results[1], RuntimeError)

    def test_concurrency_is_bounded(self, monkeypatch):
        """No more than pool_size sessions run simultaneously."""
        pool_size = 2
        active = [0]
        peak = [0]
        lock = threading.Lock()

        def fake_run(self):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.1)
            with lock:
                active[0] -= 1
            return TestSession(session_id="x", start_time=__import__("datetime").datetime.now())

        monkeypatch.setattr("qa_agent.batch.QAAgent.run", fake_run, raising=True)
        with BatchRunner(pool_size=pool_size) as runner:
            runner.run_all([_cfg(f"https://example.com/{i}") for i in range(6)])
        assert peak[0] <= pool_size

    def test_submit_returns_job_with_status(self, monkeypatch):
        def fake_run(self):
            return TestSession(session_id="s", start_time=__import__("datetime").datetime.now())

        monkeypatch.setattr("qa_agent.batch.QAAgent.run", fake_run, raising=True)
        with BatchRunner(pool_size=2) as runner:
            job = runner.submit(_cfg())
            result = job.result(timeout=5)
        assert result.session_id == "s"
        assert job.status == "completed"

    def test_does_not_mutate_caller_config(self, monkeypatch):
        """The shared template's output_dir must be untouched after a run."""
        def fake_run(self):
            return TestSession(session_id="s", start_time=__import__("datetime").datetime.now())

        monkeypatch.setattr("qa_agent.batch.QAAgent.run", fake_run, raising=True)
        cfg = _cfg()
        original_output_dir = cfg.output_dir
        with BatchRunner(pool_size=2) as runner:
            runner.run_all([cfg])
        assert cfg.output_dir == original_output_dir


class TestBatchRunnerRateLimiter:
    def _fake_run(self):
        return TestSession(session_id="s", start_time=__import__("datetime").datetime.now())

    def test_no_rate_limit_means_each_agent_builds_its_own(self, monkeypatch):
        monkeypatch.setattr("qa_agent.batch.QAAgent.run", self._fake_run, raising=True)
        with BatchRunner(pool_size=2) as runner:
            job1 = runner.submit(_cfg("https://example.com/a"))
            job2 = runner.submit(_cfg("https://example.com/b"))
            job1.result(timeout=5)
            job2.result(timeout=5)
        assert job1.agent._rate_limiter is not job2.agent._rate_limiter
        assert job1.agent._rate_limiter.enabled is True  # default config.rate_limit

    def test_shared_rate_limit_is_passed_to_every_agent(self, monkeypatch):
        monkeypatch.setattr("qa_agent.batch.QAAgent.run", self._fake_run, raising=True)
        with BatchRunner(pool_size=2, rate_limit=5.0) as runner:
            job1 = runner.submit(_cfg("https://example.com/a"))
            job2 = runner.submit(_cfg("https://example.com/b"))
            job1.result(timeout=5)
            job2.result(timeout=5)
        assert job1.agent._rate_limiter is runner._rate_limiter
        assert job2.agent._rate_limiter is runner._rate_limiter
        assert runner._rate_limiter.enabled is True

    def test_shared_rate_limit_zero_disables_throttling(self, monkeypatch):
        monkeypatch.setattr("qa_agent.batch.QAAgent.run", self._fake_run, raising=True)
        with BatchRunner(pool_size=2, rate_limit=0) as runner:
            job = runner.submit(_cfg())
            job.result(timeout=5)
        assert job.agent._rate_limiter.enabled is False
