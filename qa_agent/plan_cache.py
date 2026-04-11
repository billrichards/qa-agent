"""Filesystem cache for AI-generated test plans.

Cache entries are keyed by a SHA-256 hash of the instructions and sorted URLs,
stored as JSON files under ``~/.qa_agent/cache/``.  Each entry records its
creation timestamp; entries older than ``ttl`` seconds are treated as expired.
"""

import hashlib
import json
import time
from pathlib import Path

from .models import (
    CustomStep,
    FindingCategory,
    Severity,
    StepAction,
    StepAssertion,
    TestPlan,
)

DEFAULT_CACHE_DIR = Path.home() / ".qa_agent" / "cache"
DEFAULT_TTL = 86400  # 24 hours


class PlanCache:
    """Read/write TestPlan objects from a filesystem cache."""

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR, ttl: int = DEFAULT_TTL) -> None:
        self.cache_dir = cache_dir
        self.ttl = ttl
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def make_key(instructions: str, urls: list[str]) -> str:
        """Return a stable cache key for the given instructions and URLs."""
        content = instructions.strip() + "\n" + "\n".join(sorted(urls))
        return hashlib.sha256(content.encode()).hexdigest()[:24]

    def get(self, key: str) -> TestPlan | None:
        """Return the cached TestPlan if present and not expired, else None."""
        path = self._path(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            age = time.time() - data["created_at"]
            if age > self.ttl:
                path.unlink(missing_ok=True)
                return None
            return _deserialize(data["test_plan"])
        except Exception:
            return None

    def set(self, key: str, plan: TestPlan) -> None:
        """Write a TestPlan to the cache (failures are silently ignored)."""
        try:
            payload = {"created_at": time.time(), "test_plan": _serialize(plan)}
            self._path(key).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _serialize(plan: TestPlan) -> dict:
    return {
        "summary": plan.summary,
        "focus_areas": plan.focus_areas,
        "notes": plan.notes,
        "suggested_urls": plan.suggested_urls,
        "warnings": plan.warnings,
        "custom_steps": [
            {
                "description": s.description,
                "severity": s.severity.value,
                "category": s.category.value,
                "actions": [
                    {"type": a.type, "selector": a.selector, "value": a.value, "description": a.description}
                    for a in s.actions
                ],
                "assertions": [
                    {"type": a.type, "selector": a.selector, "value": a.value, "description": a.description}
                    for a in s.assertions
                ],
            }
            for s in plan.custom_steps
        ],
    }


_SEVERITY = {s.value: s for s in Severity}
_CATEGORY = {c.value: c for c in FindingCategory}


def _deserialize(data: dict) -> TestPlan:
    steps = []
    for s in data.get("custom_steps", []):
        steps.append(
            CustomStep(
                description=s["description"],
                severity=_SEVERITY.get(s.get("severity", "medium"), Severity.MEDIUM),
                category=_CATEGORY.get(s.get("category", "unexpected_behavior"), FindingCategory.UNEXPECTED_BEHAVIOR),
                actions=[
                    StepAction(type=a["type"], selector=a.get("selector"), value=a.get("value"), description=a.get("description"))
                    for a in s.get("actions", [])
                ],
                assertions=[
                    StepAssertion(type=a["type"], selector=a.get("selector"), value=a.get("value"), description=a.get("description"))
                    for a in s.get("assertions", [])
                ],
            )
        )
    return TestPlan(
        summary=data.get("summary", ""),
        focus_areas=data.get("focus_areas", []),
        notes=data.get("notes", ""),
        suggested_urls=data.get("suggested_urls", []),
        warnings=data.get("warnings", []),
        custom_steps=steps,
    )
