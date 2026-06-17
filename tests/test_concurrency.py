"""Tests for the thread-safe Frontier and PageIndexer primitives."""

from __future__ import annotations

import threading
import time

from qa_agent.concurrency import Frontier, PageIndexer


class TestFrontierBasics:
    def test_seed_and_claim_focused(self):
        f = Frontier(max_pages=3, max_depth=0)
        f.seed(["a", "b", "c"])
        claimed = []
        while True:
            item = f.claim()
            if item is None:
                break
            claimed.append(item[0])
            f.complete_one()
        assert sorted(claimed) == ["a", "b", "c"]

    def test_dedup_on_seed_and_add(self):
        f = Frontier(max_pages=10, max_depth=2)
        f.seed(["a", "a"])
        f.add_links(["a", "b"], parent_depth=0)
        seen = []
        while True:
            item = f.claim()
            if item is None:
                break
            seen.append(item[0])
            f.complete_one()
        assert sorted(seen) == ["a", "b"]

    def test_depth_limit_blocks_deeper_links(self):
        f = Frontier(max_pages=10, max_depth=1)
        f.seed(["root"])
        url, depth = f.claim()  # type: ignore[misc]
        assert depth == 0
        f.add_links(["child"], parent_depth=0)   # depth 1 — allowed
        f.add_links(["grandchild"], parent_depth=1)  # depth 2 — rejected
        f.complete_one()
        rest = []
        while True:
            item = f.claim()
            if item is None:
                break
            rest.append(item[0])
            f.complete_one()
        assert rest == ["child"]

    def test_stop_event_halts_claims(self):
        stop = threading.Event()
        f = Frontier(max_pages=10, max_depth=0, stop_event=stop)
        f.seed(["a", "b"])
        stop.set()
        assert f.claim() is None


class TestFrontierConcurrency:
    def test_max_pages_never_exceeded(self):
        """Many workers hammering claim/add must not overshoot the budget."""
        f = Frontier(max_pages=50, max_depth=5)
        f.seed([f"seed-{i}" for i in range(5)])
        claimed_lock = threading.Lock()
        claimed: list[str] = []
        counter = [0]

        def worker():
            while True:
                item = f.claim()
                if item is None:
                    return
                url, depth = item
                with claimed_lock:
                    claimed.append(url)
                # Each page spawns 3 children to keep the frontier busy.
                if depth < 5:
                    with claimed_lock:
                        n = counter[0]
                        counter[0] += 3
                    f.add_links([f"u-{n}", f"u-{n+1}", f"u-{n+2}"], depth)
                f.complete_one()

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert all(not t.is_alive() for t in threads), "workers deadlocked"
        assert len(claimed) <= 50
        assert len(claimed) == len(set(claimed)), "a URL was tested twice"

    def test_clean_termination_when_drained_mid_flight(self):
        """No deadlock when the queue empties while a worker is still in-flight."""
        f = Frontier(max_pages=10, max_depth=2)
        f.seed(["only"])

        results: list[str] = []
        lock = threading.Lock()

        def worker():
            while True:
                item = f.claim()
                if item is None:
                    return
                url, depth = item
                # Simulate slow work so other workers block in claim() waiting.
                time.sleep(0.05)
                if url == "only":
                    f.add_links(["child"], depth)
                with lock:
                    results.append(url)
                f.complete_one()

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert all(not t.is_alive() for t in threads), "deadlock on termination"
        assert sorted(results) == ["child", "only"]


class TestPageIndexer:
    def test_unique_indices_across_threads(self):
        idx = PageIndexer()
        got: list[int] = []
        lock = threading.Lock()

        def worker():
            for _ in range(100):
                v = idx.next()
                with lock:
                    got.append(v)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(got) == 800
        assert len(set(got)) == 800, "duplicate page index handed out"
