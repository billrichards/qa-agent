"""Tests for qa_agent/plan_cache.py — round-trip, key stability, security."""

from __future__ import annotations

import json
import time
from pathlib import Path

from qa_agent.models import (
    CustomStep,
    FindingCategory,
    Severity,
    StepAction,
    StepAssertion,
    TestPlan,
)
from qa_agent.plan_cache import PlanCache


def _make_plan(summary: str = "Test plan") -> TestPlan:
    return TestPlan(
        summary=summary,
        focus_areas=["login", "checkout"],
        custom_steps=[
            CustomStep(
                description="Click submit",
                severity=Severity.HIGH,
                category=FindingCategory.FORM_HANDLING,
                actions=[StepAction(type="click", selector="#submit")],
                assertions=[StepAssertion(type="url_contains", value="/success")],
            )
        ],
        suggested_urls=[],
        notes="Some notes",
    )


class TestPlanCacheRoundTrip:
    def test_set_then_get_returns_same_plan(self, tmp_path):
        cache = PlanCache(cache_dir=tmp_path)
        plan = _make_plan("Login flow test")
        key = PlanCache.make_key("test login", ["https://example.com"])
        cache.set(key, plan)
        retrieved = cache.get(key)

        assert retrieved is not None
        assert retrieved.summary == "Login flow test"
        assert retrieved.focus_areas == ["login", "checkout"]
        assert len(retrieved.custom_steps) == 1
        assert retrieved.custom_steps[0].description == "Click submit"

    def test_get_missing_key_returns_none(self, tmp_path):
        cache = PlanCache(cache_dir=tmp_path)
        assert cache.get("nonexistent_key") is None

    def test_corrupt_cache_file_returns_none(self, tmp_path):
        cache = PlanCache(cache_dir=tmp_path)
        key = "corrupt_key_abc123"
        cache_file = tmp_path / f"{key}.json"
        cache_file.write_text("this is not valid json {{{")

        assert cache.get(key) is None  # must not crash

    def test_expired_entry_returns_none(self, tmp_path):
        cache = PlanCache(cache_dir=tmp_path, ttl=1)
        plan = _make_plan()
        key = PlanCache.make_key("test", ["https://example.com"])
        cache.set(key, plan)

        # Manually backdate the created_at timestamp
        cache_file = tmp_path / f"{key}.json"
        data = json.loads(cache_file.read_text())
        data["created_at"] = time.time() - 10  # 10 seconds ago, TTL is 1
        cache_file.write_text(json.dumps(data))

        assert cache.get(key) is None

    def test_fresh_entry_returned(self, tmp_path):
        cache = PlanCache(cache_dir=tmp_path, ttl=3600)
        plan = _make_plan()
        key = PlanCache.make_key("test", ["https://example.com"])
        cache.set(key, plan)
        assert cache.get(key) is not None

    def test_set_failure_is_silent(self, tmp_path):
        """set() must not raise even if the file write fails."""
        cache = PlanCache(cache_dir=tmp_path)
        plan = _make_plan()
        # Patch Path.write_text to raise so we test the silent-failure path
        from unittest.mock import patch as _patch
        with _patch.object(Path, "write_text", side_effect=OSError("disk full")):
            cache.set("anykey", plan)  # must not raise


class TestPlanCacheKeyStability:
    def test_same_inputs_produce_same_key(self):
        k1 = PlanCache.make_key("test login", ["https://example.com"])
        k2 = PlanCache.make_key("test login", ["https://example.com"])
        assert k1 == k2

    def test_different_instructions_produce_different_key(self):
        k1 = PlanCache.make_key("test login", ["https://example.com"])
        k2 = PlanCache.make_key("test checkout", ["https://example.com"])
        assert k1 != k2

    def test_different_urls_produce_different_key(self):
        k1 = PlanCache.make_key("test login", ["https://example.com"])
        k2 = PlanCache.make_key("test login", ["https://other.com"])
        assert k1 != k2

    def test_url_order_normalised(self):
        """URLs are sorted before hashing so order doesn't matter."""
        k1 = PlanCache.make_key("test", ["https://b.com", "https://a.com"])
        k2 = PlanCache.make_key("test", ["https://a.com", "https://b.com"])
        assert k1 == k2

    def test_key_is_filesystem_safe(self):
        """Key must not contain path separators or dangerous characters."""
        key = PlanCache.make_key("some instructions", ["https://example.com"])
        assert "/" not in key
        assert "\\" not in key
        assert ".." not in key


class TestPlanCacheSecurity:
    def test_path_traversal_in_instructions_does_not_escape_cache_dir(self, tmp_path):
        """An instruction containing ../../etc/passwd must not write outside cache_dir."""
        cache = PlanCache(cache_dir=tmp_path)
        evil_instructions = "../../etc/passwd"
        key = PlanCache.make_key(evil_instructions, ["https://example.com"])
        plan = _make_plan()
        cache.set(key, plan)

        # The key is a SHA256 hex digest — no path segments possible
        assert "/" not in key
        assert "\\" not in key

        # The cache file must be inside cache_dir
        expected_file = tmp_path / f"{key}.json"
        assert expected_file.exists()

        # Verify nothing was written to /etc/passwd or tmp_path parent
        parent = tmp_path.parent
        unexpected = parent / "etc" / "passwd"
        assert not unexpected.exists()
