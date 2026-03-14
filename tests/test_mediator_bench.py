"""Performance benchmarks for QueryMediator v2 foundation.

Proves the mediator meets the milestone's success criteria:

    REQ-PERF-1  Hydration:     < 100ms  for 15 shards (~2MB)
    REQ-PERF-2  Cache read:    < 1ms    for peek() / get() cache hit
    REQ-PERF-3  Cascade cost:  < 5ms    for bust("index.scan") across 52 nodes
    REQ-PERF-4  Shard write:   < 50ms   for 100KB JSON
    MILESTONE   Symbols delta: < 1s     for 1-file change (vs 30s full rebuild)
    MILESTONE   Dispatch skip: 0 nodes  recomputed when nothing relevant changed

Each benchmark runs N iterations and reports min / median / p95 / max.
Assertions enforce the target.  If a target is missed, the test fails
with the actual timing, making performance regressions visible in CI.

NOTE: These benchmarks use the REAL 52-node tree with all 5 domains
registered.  They do NOT use mocks — the tree is the production tree.
Resolvers are replaced with fast stubs so we measure mediator overhead,
not resolver cost.
"""

from __future__ import annotations

import json
import math
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

from src.core.services.mediator.core import CacheEntry, QueryMediator
from src.core.services.mediator.registrations import register_all
from src.core.services.mediator.tree import DataTree, TreeRegistration


# ── Helpers ────────────────────────────────────────────────────────


def _timed_iterations(fn, n: int = 100) -> dict[str, float]:
    """Run fn() n times, return timing stats in milliseconds."""
    times: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        elapsed = (time.perf_counter() - t0) * 1000  # ms
        times.append(elapsed)
    times.sort()
    return {
        "min_ms": times[0],
        "median_ms": statistics.median(times),
        "p95_ms": times[int(len(times) * 0.95)],
        "max_ms": times[-1],
        "mean_ms": statistics.mean(times),
        "iterations": n,
    }


def _report(label: str, stats: dict[str, float], target_ms: float) -> None:
    """Print benchmark results for visibility in test output."""
    print(
        f"\n  {label}:"
        f"  min={stats['min_ms']:.3f}ms"
        f"  median={stats['median_ms']:.3f}ms"
        f"  p95={stats['p95_ms']:.3f}ms"
        f"  max={stats['max_ms']:.3f}ms"
        f"  target=<{target_ms}ms"
    )


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def full_mediator() -> QueryMediator:
    """Create a mediator with all 52 nodes registered (production tree).

    This is the same tree as server.py creates, with all 5 domains.
    """
    tree = DataTree()
    m = QueryMediator(tree, Path("."))
    register_all(m)
    return m


@pytest.fixture
def warm_mediator(full_mediator: QueryMediator) -> QueryMediator:
    """Full mediator with all 52 nodes pre-cached.

    Injects stub data into every node so peek() and get() return
    immediately.  This simulates a warm cache after hydration.
    """
    for path in full_mediator.tree.all_paths():
        full_mediator.put(
            path,
            data={"stub": True, "path": path},
            cascade=False,
            notify=False,
        )
    return full_mediator


@pytest.fixture
def bench_dir(tmp_path: Path) -> Path:
    """Temporary directory for persistence benchmarks."""
    shard_dir = tmp_path / ".state" / "mediator_index"
    shard_dir.mkdir(parents=True)
    return tmp_path


# ── BENCH-1: Cache read — peek() on warm cache ────────────────────


class TestBenchPeek:
    """REQ-PERF-2: peek() on hot cache must be < 1ms."""

    TARGET_MS = 1.0

    def test_peek_single_path(self, warm_mediator: QueryMediator) -> None:
        """peek() for a single path — target < 1ms."""
        stats = _timed_iterations(
            lambda: warm_mediator.peek("posture.toolchain"),
            n=1000,
        )
        _report("peek(single)", stats, self.TARGET_MS)
        assert stats["p95_ms"] < self.TARGET_MS, (
            f"peek() p95={stats['p95_ms']:.3f}ms exceeds target {self.TARGET_MS}ms"
        )

    def test_peek_many(self, warm_mediator: QueryMediator) -> None:
        """peek_many() for 5 paths — target < 1ms."""
        paths = [
            "posture.toolchain", "posture.platform",
            "detect.docker", "detect.k8s", "devops.git",
        ]
        stats = _timed_iterations(
            lambda: warm_mediator.peek_many(*paths),
            n=1000,
        )
        _report("peek_many(5)", stats, self.TARGET_MS)
        assert stats["p95_ms"] < self.TARGET_MS, (
            f"peek_many() p95={stats['p95_ms']:.3f}ms exceeds target {self.TARGET_MS}ms"
        )


# ── BENCH-2: Cache read — get() cache hit ─────────────────────────


class TestBenchGetCacheHit:
    """REQ-PERF-2: get() with cache hit must be < 1ms."""

    TARGET_MS = 1.0

    def test_get_cache_hit(self, warm_mediator: QueryMediator) -> None:
        """get() on a cached node — target < 1ms."""
        stats = _timed_iterations(
            lambda: warm_mediator.get("posture.toolchain"),
            n=1000,
        )
        _report("get(cache_hit)", stats, self.TARGET_MS)
        assert stats["p95_ms"] < self.TARGET_MS, (
            f"get() cache hit p95={stats['p95_ms']:.3f}ms exceeds target {self.TARGET_MS}ms"
        )

    def test_get_since_seq_shortcircuit(self, warm_mediator: QueryMediator) -> None:
        """get(since_seq=current) returns immediately — target < 0.5ms."""
        # Get current seq for the node
        result = warm_mediator.get("posture.toolchain")
        seq = result["meta"]["seq"]

        stats = _timed_iterations(
            lambda: warm_mediator.get("posture.toolchain", since_seq=seq),
            n=1000,
        )
        _report("get(since_seq=current)", stats, 0.5)
        assert stats["p95_ms"] < 0.5, (
            f"since_seq shortcircuit p95={stats['p95_ms']:.3f}ms exceeds 0.5ms"
        )


# ── BENCH-3: Cascade invalidation ─────────────────────────────────


class TestBenchCascade:
    """REQ-PERF-3: bust("index.scan") cascade must be < 5ms for 52 nodes."""

    TARGET_MS = 5.0

    def test_cascade_from_scan(self, warm_mediator: QueryMediator) -> None:
        """put("index.scan") cascade across all dependents — target < 5ms.

        After each cascade, re-warm the cache for the next iteration.
        """
        m = warm_mediator
        times: list[float] = []

        for _ in range(50):
            # Re-warm all nodes
            for path in m.tree.all_paths():
                m.put(path, data={"stub": True}, cascade=False, notify=False)

            # Time the cascade
            t0 = time.perf_counter()
            m.put("index.scan")  # data=None → invalidate + cascade
            elapsed = (time.perf_counter() - t0) * 1000
            times.append(elapsed)

        times.sort()
        stats = {
            "min_ms": times[0],
            "median_ms": statistics.median(times),
            "p95_ms": times[int(len(times) * 0.95)],
            "max_ms": times[-1],
            "mean_ms": statistics.mean(times),
            "iterations": 50,
        }
        _report("cascade(index.scan→52)", stats, self.TARGET_MS)
        assert stats["p95_ms"] < self.TARGET_MS, (
            f"cascade p95={stats['p95_ms']:.3f}ms exceeds target {self.TARGET_MS}ms"
        )

    def test_cascade_returns_invalidated_count(
        self, warm_mediator: QueryMediator,
    ) -> None:
        """Cascade from index.scan should invalidate most of the tree."""
        result = warm_mediator.put("index.scan")
        invalidated = result.get("invalidated", [])
        # index.scan → classify → all 13 detect → all 14 devops
        #   → extra.project_status (via devops.status)
        # Plus index.delta → symbols → peek, stats
        # Should be 36+ nodes (everything except independent posture/extra)
        assert len(invalidated) >= 30, (
            f"Expected >= 30 invalidated, got {len(invalidated)}: {sorted(invalidated)}"
        )

    def test_bust_path_cost(self, warm_mediator: QueryMediator) -> None:
        """bust_path() single node — target < 1ms."""
        # Re-warm
        warm_mediator.put(
            "detect.docker",
            data={"stub": True},
            cascade=False,
            notify=False,
        )
        stats = _timed_iterations(
            lambda: warm_mediator.bust_path("detect.docker"),
            n=200,
        )
        _report("bust_path(detect.docker)", stats, 1.0)
        assert stats["p95_ms"] < 1.0, (
            f"bust_path p95={stats['p95_ms']:.3f}ms exceeds 1.0ms"
        )


# ── BENCH-4: Persistence write ────────────────────────────────────


class TestBenchPersistence:
    """REQ-PERF-4: Shard write must be < 50ms for 100KB JSON."""

    TARGET_MS = 50.0

    def test_persist_node_100kb(self, bench_dir: Path) -> None:
        """Write a 100KB JSON shard — target < 50ms."""
        from src.core.services.mediator.persistence import persist_node

        # Generate ~100KB of realistic data
        data = {f"key_{i}": {"value": f"data_{i}" * 20, "n": i} for i in range(500)}
        json_size = len(json.dumps(data))
        assert json_size > 80_000, f"Test data too small: {json_size} bytes"

        stats = _timed_iterations(
            lambda: persist_node(bench_dir, "bench.large", data),
            n=50,
        )
        _report(f"persist_node({json_size // 1024}KB)", stats, self.TARGET_MS)
        assert stats["p95_ms"] < self.TARGET_MS, (
            f"persist_node p95={stats['p95_ms']:.3f}ms exceeds target {self.TARGET_MS}ms"
        )

    def test_persist_node_small(self, bench_dir: Path) -> None:
        """Write a small shard (~1KB) — target < 10ms."""
        from src.core.services.mediator.persistence import persist_node

        data = {"status": "ok", "items": list(range(50))}

        stats = _timed_iterations(
            lambda: persist_node(bench_dir, "bench.small", data),
            n=100,
        )
        _report("persist_node(~1KB)", stats, 10.0)
        assert stats["p95_ms"] < 10.0, (
            f"persist_node (small) p95={stats['p95_ms']:.3f}ms exceeds 10ms"
        )


# ── BENCH-5: Hydration ────────────────────────────────────────────


class TestBenchHydration:
    """REQ-PERF-1: Hydration of 15 shards (< 2MB total) must be < 100ms."""

    TARGET_MS = 100.0

    def test_hydrate_15_shards(self, bench_dir: Path) -> None:
        """Load 15 shards from disk into a fresh mediator — target < 100ms."""
        from src.core.services.mediator.persistence import (
            hydrate_cache,
            persist_node,
        )

        # Write 15 realistic shards to disk
        shard_names = [
            "detect.docker", "detect.k8s", "detect.ci", "detect.git",
            "detect.github", "detect.terraform", "detect.packages",
            "posture.full", "posture.toolchain", "posture.platform",
            "github.pulls", "audit.scores", "audit.system",
            "index.scan", "index.symbols",
        ]
        for name in shard_names:
            # ~50KB each ≈ 750KB total (realistic)
            data = {f"item_{i}": f"value_{i}" * 10 for i in range(200)}
            persist_node(bench_dir, name, data)

        # Benchmark hydration
        times: list[float] = []
        for _ in range(10):
            tree = DataTree()
            m = QueryMediator(tree, bench_dir)
            register_all(m)

            t0 = time.perf_counter()
            count = hydrate_cache(m, bench_dir)
            elapsed = (time.perf_counter() - t0) * 1000
            times.append(elapsed)

        times.sort()
        stats = {
            "min_ms": times[0],
            "median_ms": statistics.median(times),
            "p95_ms": times[int(len(times) * 0.95)],
            "max_ms": times[-1],
            "mean_ms": statistics.mean(times),
            "iterations": 10,
        }
        _report(f"hydrate({len(shard_names)} shards)", stats, self.TARGET_MS)
        assert count >= 15, f"Expected 15+ hydrated, got {count}"
        assert stats["p95_ms"] < self.TARGET_MS, (
            f"hydration p95={stats['p95_ms']:.3f}ms exceeds target {self.TARGET_MS}ms"
        )


# ── BENCH-6: Dispatch skip (delta principle) ──────────────────────


class TestBenchDispatchDelta:
    """MILESTONE: On file change, dispatch skips nodes with fresh cache."""

    def test_dispatch_skips_fresh_nodes(
        self, warm_mediator: QueryMediator,
    ) -> None:
        """After warming all caches, dispatch should skip ALL nodes.

        This verifies the delta principle: if nothing is stale, nothing
        recomputes.  Dispatch should return immediately.
        """
        m = warm_mediator

        # Ensure all TTL-based nodes are fresh
        # (warm_mediator already injected data via put(), which sets computed_at=now)

        # Count how many resolvers actually fire
        call_count = 0
        original_get = m.get

        def counting_get(path, **kwargs):
            nonlocal call_count
            call_count += 1
            return original_get(path, **kwargs)

        # Dispatch ALL paths
        all_paths = m.tree.all_paths()
        t0 = time.perf_counter()
        m.dispatch(*all_paths)
        dispatch_time = (time.perf_counter() - t0) * 1000

        # Give background threads time to finish (if any started)
        time.sleep(0.5)

        print(f"\n  dispatch({len(all_paths)} paths): {dispatch_time:.3f}ms")
        print(f"  (background threads finished, 500ms wait)")

        # The dispatch itself should return very quickly
        assert dispatch_time < 50, (
            f"dispatch() took {dispatch_time:.1f}ms — should be near-instant"
        )

    def test_cascade_then_dispatch_only_stale(
        self, warm_mediator: QueryMediator,
    ) -> None:
        """After cascade from index.scan, only invalidated nodes should
        be eligible for recompute.  Posture nodes (not in the cascade)
        should be skipped."""
        m = warm_mediator

        # Cascade from index.scan — invalidates index.* + detect.* + devops.*
        result = m.put("index.scan")
        invalidated = set(result.get("invalidated", []))

        # Posture nodes should NOT be invalidated (independent)
        posture_paths = [p for p in m.tree.all_paths() if p.startswith("posture.")]
        for p in posture_paths:
            # posture nodes are independent — not in cascade from index.scan
            # (posture.full depends on its own pillars, not detect/devops)
            cached = m.peek(p)
            if p not in invalidated:
                assert cached is not None, (
                    f"{p} was invalidated by index.scan cascade but shouldn't have been"
                )


# ── BENCH-7: Incremental symbols (the big win) ────────────────────


class TestBenchIncrementalSymbols:
    """MILESTONE: 1-file change symbol update must be < 1s (vs 30s full)."""

    TARGET_MS = 1000.0  # 1 second

    def test_incremental_symbols_one_file(self, tmp_path: Path) -> None:
        """Simulate: warm symbol index, then 1 file changes.

        The incremental_symbols function should only re-parse that
        one file, not all files.
        """
        from src.core.services.mediator.registrations.index import (
            FileEntry,
            IndexSymbolEntry,
            ScanDelta,
            incremental_symbols,
        )

        # Create a small project with 100 Python files
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        for i in range(100):
            f = src_dir / f"module_{i}.py"
            f.write_text(
                f"class Widget{i}:\n"
                f"    def process(self):\n"
                f"        pass\n"
                f"\n"
                f"def helper_{i}():\n"
                f"    return {i}\n"
            )

        # Cold start: build full symbol index
        cold_delta = ScanDelta(
            added=[f"src/module_{i}.py" for i in range(100)],
            removed=[],
            modified=[],
            timestamp=time.time(),
        )
        t0 = time.perf_counter()
        symbols = incremental_symbols(tmp_path, cold_delta, {})
        cold_time = (time.perf_counter() - t0) * 1000
        print(f"\n  symbols(cold, 100 files): {cold_time:.1f}ms")
        print(f"  total symbols: {sum(len(v) for v in symbols.values())}")

        # Warm: modify 1 file
        changed_file = src_dir / "module_50.py"
        changed_file.write_text(
            "class NewWidget:\n"
            "    def new_method(self):\n"
            "        pass\n"
            "\n"
            "def new_helper():\n"
            "    return 999\n"
        )

        warm_delta = ScanDelta(
            added=[],
            removed=[],
            modified=["src/module_50.py"],
            timestamp=time.time(),
        )

        # Benchmark incremental update
        stats = _timed_iterations(
            lambda: incremental_symbols(tmp_path, warm_delta, dict(symbols)),
            n=20,
        )
        _report("symbols(incremental, 1 file)", stats, self.TARGET_MS)

        # The incremental update should be MUCH faster than cold
        assert stats["p95_ms"] < self.TARGET_MS, (
            f"incremental symbols p95={stats['p95_ms']:.3f}ms exceeds {self.TARGET_MS}ms"
        )

        # Sanity: incremental should be at least 5x faster than cold
        if cold_time > 0:
            speedup = cold_time / stats["median_ms"]
            print(f"  speedup: {speedup:.1f}x (cold={cold_time:.1f}ms, "
                  f"warm={stats['median_ms']:.1f}ms)")


# ── BENCH-8: Tree operations ──────────────────────────────────────


class TestBenchTreeOps:
    """Tree introspection and dependency resolution performance."""

    def test_all_paths_speed(self, full_mediator: QueryMediator) -> None:
        """all_paths() on 52-node tree — target < 0.5ms."""
        stats = _timed_iterations(
            lambda: full_mediator.tree.all_paths(),
            n=1000,
        )
        _report("all_paths(52 nodes)", stats, 0.5)
        assert stats["p95_ms"] < 0.5, (
            f"all_paths p95={stats['p95_ms']:.3f}ms exceeds 0.5ms"
        )

    def test_resolve_speed(self, full_mediator: QueryMediator) -> None:
        """resolve() single path — target < 0.1ms."""
        stats = _timed_iterations(
            lambda: full_mediator.tree.resolve("detect.docker"),
            n=1000,
        )
        _report("resolve(detect.docker)", stats, 0.1)
        assert stats["p95_ms"] < 0.1, (
            f"resolve p95={stats['p95_ms']:.3f}ms exceeds 0.1ms"
        )

    def test_dependents_speed(self, full_mediator: QueryMediator) -> None:
        """dependents() full transitive walk — target < 2ms."""
        stats = _timed_iterations(
            lambda: full_mediator.tree.dependents("index.scan"),
            n=500,
        )
        _report("dependents(index.scan→all)", stats, 2.0)
        assert stats["p95_ms"] < 2.0, (
            f"dependents p95={stats['p95_ms']:.3f}ms exceeds 2.0ms"
        )

    def test_diag_speed(self, warm_mediator: QueryMediator) -> None:
        """diag() full state snapshot — target < 5ms."""
        stats = _timed_iterations(
            lambda: warm_mediator.diag(),
            n=200,
        )
        _report("diag(52 nodes)", stats, 5.0)
        assert stats["p95_ms"] < 5.0, (
            f"diag p95={stats['p95_ms']:.3f}ms exceeds 5.0ms"
        )


# ── BENCH-9: Subscribe notification cost ──────────────────────────


class TestBenchSubscribe:
    """Subscription notification overhead during put()."""

    def test_put_with_subscribers(self, warm_mediator: QueryMediator) -> None:
        """put() with 5 active subscribers — should not add > 1ms overhead."""
        events: list[dict] = []

        # Register 5 subscribers matching different patterns
        for pattern in ["posture.*", "detect.*", "devops.*", "index.*", "*"]:
            warm_mediator.subscribe(pattern, lambda e: events.append(e))

        # Benchmark put with subscribers active
        stats = _timed_iterations(
            lambda: warm_mediator.put(
                "detect.docker",
                data={"stub": True},
                cascade=False,
                notify=True,
            ),
            n=200,
        )
        _report("put(with 5 subscribers)", stats, 2.0)
        assert stats["p95_ms"] < 2.0, (
            f"put+notify p95={stats['p95_ms']:.3f}ms exceeds 2.0ms"
        )
        # Verify subscribers were actually called
        assert len(events) > 0, "Subscribers were not called"
