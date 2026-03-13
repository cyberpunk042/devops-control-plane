"""Tests for QueryMediator Phase 0 — tree registry and core mediator."""

from __future__ import annotations

import math
import threading
import time
from pathlib import Path

import pytest

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.tree import DataTree, TreeRegistration


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def tree() -> DataTree:
    return DataTree()


@pytest.fixture
def mediator(tree: DataTree) -> QueryMediator:
    return QueryMediator(tree, Path("/tmp/test-project"))


# ── DataTree tests ─────────────────────────────────────────────────


class TestTreeRegister:
    """Test node registration and path resolution."""

    def test_register_simple(self, tree: DataTree) -> None:
        """Single path registers and resolves."""
        node = tree.register(TreeRegistration(
            path="posture.toolchain",
            resolver=lambda: "data",
            ttl=300,
        ))
        assert node.path == "posture.toolchain"
        assert node.ttl == 300
        assert node.is_registered

    def test_resolve(self, tree: DataTree) -> None:
        """Registered path resolves correctly."""
        tree.register(TreeRegistration(path="a.b.c", resolver=lambda: 1))
        node = tree.resolve("a.b.c")
        assert node is not None
        assert node.path == "a.b.c"

    def test_resolve_missing(self, tree: DataTree) -> None:
        """Non-existent path returns None."""
        assert tree.resolve("nonexistent") is None

    def test_duplicate_raises(self, tree: DataTree) -> None:
        """Registering same path twice raises ValueError."""
        tree.register(TreeRegistration(path="a.b", resolver=lambda: 1))
        with pytest.raises(ValueError, match="already registered"):
            tree.register(TreeRegistration(path="a.b", resolver=lambda: 2))

    def test_empty_path_raises(self, tree: DataTree) -> None:
        """Empty path raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            tree.register(TreeRegistration(path=""))


class TestTreeIntermediate:
    """Test auto-creation of branch nodes."""

    def test_intermediate_branches(self, tree: DataTree) -> None:
        """Registering a.b.c auto-creates a and a.b as branches."""
        tree.register(TreeRegistration(path="a.b.c", resolver=lambda: 1))

        branch_a = tree.resolve("a")
        assert branch_a is not None
        assert not branch_a.is_registered
        assert branch_a.is_branch

        branch_ab = tree.resolve("a.b")
        assert branch_ab is not None
        assert not branch_ab.is_registered
        assert branch_ab.is_branch

    def test_promote_branch(self, tree: DataTree) -> None:
        """Registering at an auto-created branch path promotes it."""
        tree.register(TreeRegistration(path="a.b.c", resolver=lambda: 1))
        # a.b exists as branch; now register it
        tree.register(TreeRegistration(
            path="a.b", resolver=lambda: 2, ttl=60,
        ))
        node = tree.resolve("a.b")
        assert node is not None
        assert node.is_registered
        assert node.ttl == 60
        # Still has child
        assert node.is_branch

    def test_children(self, tree: DataTree) -> None:
        """children() returns direct children."""
        tree.register(TreeRegistration(path="a.x", resolver=lambda: 1))
        tree.register(TreeRegistration(path="a.y", resolver=lambda: 2))
        tree.register(TreeRegistration(path="a.y.z", resolver=lambda: 3))

        children = tree.children("a")
        paths = [c.path for c in children]
        assert sorted(paths) == ["a.x", "a.y"]

    def test_top_level_children(self, tree: DataTree) -> None:
        """children('') returns top-level nodes."""
        tree.register(TreeRegistration(path="alpha.x", resolver=lambda: 1))
        tree.register(TreeRegistration(path="beta.y", resolver=lambda: 2))

        children = tree.children("")
        paths = [c.path for c in children]
        assert sorted(paths) == ["alpha", "beta"]


class TestTreeDependencies:
    """Test dependency tracking and cascade resolution."""

    def test_depends_on(self, tree: DataTree) -> None:
        """depends_on is stored correctly."""
        tree.register(TreeRegistration(
            path="a", resolver=lambda: 1,
        ))
        tree.register(TreeRegistration(
            path="b", resolver=lambda: 2,
            depends_on=["a"],
        ))

        node_b = tree.resolve("b")
        assert node_b is not None
        assert node_b.depends_on == ["a"]

    def test_reverse_dependents(self, tree: DataTree) -> None:
        """Reverse dependencies are auto-computed."""
        tree.register(TreeRegistration(path="a", resolver=lambda: 1))
        tree.register(TreeRegistration(
            path="b", resolver=lambda: 2,
            depends_on=["a"],
        ))

        node_a = tree.resolve("a")
        assert node_a is not None
        assert "b" in node_a.dependents

    def test_transitive_dependents(self, tree: DataTree) -> None:
        """dependents() walks transitive dependencies."""
        tree.register(TreeRegistration(path="a", resolver=lambda: 1))
        tree.register(TreeRegistration(
            path="b", resolver=lambda: 2, depends_on=["a"],
        ))
        tree.register(TreeRegistration(
            path="c", resolver=lambda: 3, depends_on=["b"],
        ))

        deps = tree.dependents("a")
        assert "b" in deps
        assert "c" in deps

    def test_glob_dependents(self, tree: DataTree) -> None:
        """Glob patterns in depends_on are resolved."""
        tree.register(TreeRegistration(path="detect.tools.go", resolver=lambda: 1))
        tree.register(TreeRegistration(path="detect.tools.docker", resolver=lambda: 2))
        tree.register(TreeRegistration(
            path="posture.toolchain", resolver=lambda: 3,
            depends_on=["detect.tools.*"],
        ))

        # detect.tools.go should have posture.toolchain as dependent
        node_go = tree.resolve("detect.tools.go")
        assert node_go is not None
        assert "posture.toolchain" in node_go.dependents

        # Same for docker
        node_docker = tree.resolve("detect.tools.docker")
        assert node_docker is not None
        assert "posture.toolchain" in node_docker.dependents

    def test_depth_limited_dependents(self, tree: DataTree) -> None:
        """depth=0 returns only direct dependents."""
        tree.register(TreeRegistration(path="a", resolver=lambda: 1))
        tree.register(TreeRegistration(
            path="b", resolver=lambda: 2, depends_on=["a"],
        ))
        tree.register(TreeRegistration(
            path="c", resolver=lambda: 3, depends_on=["b"],
        ))

        deps = tree.dependents("a", depth=0)
        assert deps == ["b"]  # c not included


class TestTreeDiagnostics:
    """Test tree introspection methods."""

    def test_all_paths(self, tree: DataTree) -> None:
        """all_paths returns only registered paths, sorted."""
        tree.register(TreeRegistration(path="b.x", resolver=lambda: 1))
        tree.register(TreeRegistration(path="a.y", resolver=lambda: 2))

        paths = tree.all_paths()
        # Should not include auto-created branches "a" and "b"
        assert paths == ["a.y", "b.x"]

    def test_stats(self, tree: DataTree) -> None:
        """stats returns node counts."""
        tree.register(TreeRegistration(path="a.b", resolver=lambda: 1, persist=True))
        tree.register(TreeRegistration(path="a.c", resolver=lambda: 2))

        stats = tree.stats()
        assert stats["registered"] == 2
        assert stats["persistent"] == 1
        assert stats["total_nodes"] >= 3  # a (branch) + a.b + a.c

    def test_subtree(self, tree: DataTree) -> None:
        """subtree returns nested dict structure."""
        tree.register(TreeRegistration(path="a.b", resolver=lambda: 1, ttl=60))
        tree.register(TreeRegistration(path="a.c", resolver=lambda: 2))

        st = tree.subtree("a")
        assert st["path"] == "a"
        assert "b" in st.get("children", {})
        assert st["children"]["b"]["ttl"] == 60

    def test_match_glob(self, tree: DataTree) -> None:
        """match() returns nodes matching glob pattern."""
        tree.register(TreeRegistration(path="detect.tools.go", resolver=lambda: 1))
        tree.register(TreeRegistration(path="detect.tools.docker", resolver=lambda: 2))
        tree.register(TreeRegistration(path="detect.os", resolver=lambda: 3))

        matches = tree.match("detect.tools.*")
        paths = sorted(n.path for n in matches)
        assert paths == ["detect.tools.docker", "detect.tools.go"]


# ── QueryMediator tests ───────────────────────────────────────────


class TestMediatorGet:
    """Test get() resolution."""

    def test_get_miss_no_resolver(self, mediator: QueryMediator) -> None:
        """get() on path without resolver and no cache raises."""
        mediator.tree.register(TreeRegistration(path="empty"))
        with pytest.raises(RuntimeError, match="No resolver"):
            mediator.get("empty")

    def test_get_not_registered(self, mediator: QueryMediator) -> None:
        """get() on non-existent path raises KeyError."""
        with pytest.raises(KeyError, match="not found"):
            mediator.get("nonexistent")

    def test_get_computed(self, mediator: QueryMediator) -> None:
        """get() calls resolver and returns data."""
        mediator.tree.register(TreeRegistration(
            path="test.value", resolver=lambda: 42, ttl=60,
        ))
        result = mediator.get("test.value")
        assert result["data"] == 42
        assert result["meta"]["source"] == "computed"

    def test_get_cached(self, mediator: QueryMediator) -> None:
        """Second get() returns cached value."""
        call_count = 0

        def resolver():
            nonlocal call_count
            call_count += 1
            return call_count

        mediator.tree.register(TreeRegistration(
            path="test.counter", resolver=resolver, ttl=60,
        ))

        r1 = mediator.get("test.counter")
        r2 = mediator.get("test.counter")

        assert r1["data"] == 1
        assert r2["data"] == 1  # same value, not recomputed
        assert r2["meta"]["source"] == "cache"
        assert call_count == 1

    def test_get_force_recomputes(self, mediator: QueryMediator) -> None:
        """force=True bypasses cache."""
        call_count = 0

        def resolver():
            nonlocal call_count
            call_count += 1
            return call_count

        mediator.tree.register(TreeRegistration(
            path="test.force", resolver=resolver, ttl=60,
        ))

        mediator.get("test.force")
        r2 = mediator.get("test.force", force=True)

        assert r2["data"] == 2
        assert r2["meta"]["source"] == "computed"
        assert call_count == 2

    def test_get_max_age(self, mediator: QueryMediator) -> None:
        """max_age triggers recompute when cache is older."""
        call_count = 0

        def resolver():
            nonlocal call_count
            call_count += 1
            return call_count

        mediator.tree.register(TreeRegistration(
            path="test.age", resolver=resolver, ttl=300,
        ))

        mediator.get("test.age")
        # Manually age the cache entry
        entry = mediator._cache.get("test.age")
        assert entry is not None
        entry.computed_at = time.time() - 10  # 10 seconds old

        r2 = mediator.get("test.age", max_age=5)
        assert r2["data"] == 2  # recomputed because age > max_age
        assert call_count == 2

    def test_get_explain(self, mediator: QueryMediator) -> None:
        """explain=True includes resolution explanation."""
        mediator.tree.register(TreeRegistration(
            path="test.explain", resolver=lambda: "ok", ttl=60,
        ))
        result = mediator.get("test.explain", explain=True)
        assert "explain" in result["meta"]

    def test_get_infinite_ttl(self, mediator: QueryMediator) -> None:
        """Node with infinite TTL never expires."""
        call_count = 0

        def resolver():
            nonlocal call_count
            call_count += 1
            return call_count

        mediator.tree.register(TreeRegistration(
            path="test.forever", resolver=resolver, ttl=math.inf,
        ))

        mediator.get("test.forever")
        entry = mediator._cache.get("test.forever")
        assert entry is not None
        entry.computed_at = time.time() - 999999  # very old

        r2 = mediator.get("test.forever")
        assert r2["data"] == 1  # not recomputed
        assert call_count == 1


class TestMediatorPut:
    """Test put() write/invalidate/cascade."""

    def test_put_write(self, mediator: QueryMediator) -> None:
        """put(data=...) stores value in cache."""
        mediator.tree.register(TreeRegistration(path="test.put"))
        mediator.put("test.put", data="hello")

        result = mediator.get("test.put")
        assert result["data"] == "hello"

    def test_put_invalidate(self, mediator: QueryMediator) -> None:
        """put(data=None) removes from cache."""
        mediator.tree.register(TreeRegistration(
            path="test.inv", resolver=lambda: 1, ttl=60,
        ))
        mediator.get("test.inv")  # populate cache
        result = mediator.put("test.inv")
        assert "test.inv" in result["invalidated"]

        # Next get recomputes
        r2 = mediator.get("test.inv")
        assert r2["meta"]["source"] == "computed"

    def test_put_cascade(self, mediator: QueryMediator) -> None:
        """put(cascade=True) invalidates dependents."""
        mediator.tree.register(TreeRegistration(
            path="base", resolver=lambda: 1, ttl=60,
        ))
        mediator.tree.register(TreeRegistration(
            path="derived", resolver=lambda: 2, ttl=60,
            depends_on=["base"],
        ))

        # Populate both caches
        mediator.get("base")
        mediator.get("derived")

        # Invalidate base with cascade
        result = mediator.put("base", cascade=True)
        assert "derived" in result["invalidated"]

    def test_put_no_cascade(self, mediator: QueryMediator) -> None:
        """put(cascade=False) only invalidates the target."""
        mediator.tree.register(TreeRegistration(
            path="base2", resolver=lambda: 1, ttl=60,
        ))
        mediator.tree.register(TreeRegistration(
            path="derived2", resolver=lambda: 2, ttl=60,
            depends_on=["base2"],
        ))

        mediator.get("base2")
        mediator.get("derived2")

        result = mediator.put("base2", cascade=False)
        assert "derived2" not in result["invalidated"]


class TestMediatorDiag:
    """Test diag() diagnostics."""

    def test_diag_summary(self, mediator: QueryMediator) -> None:
        """diag() returns tree and cache summary."""
        mediator.tree.register(TreeRegistration(
            path="a", resolver=lambda: 1, ttl=60,
        ))
        mediator.get("a")  # populate cache

        info = mediator.diag()
        assert "tree" in info
        assert "cached" in info
        assert info["cached"] == 1

    def test_diag_node_detail(self, mediator: QueryMediator) -> None:
        """diag(path) returns detail for one node."""
        mediator.tree.register(TreeRegistration(
            path="b", resolver=lambda: 2, ttl=60, persist=True,
        ))
        mediator.get("b")

        info = mediator.diag("b")
        assert info["path"] == "b"
        assert info["cached"] is True
        assert info["ttl"] == 60
        assert info["persist"] is True
        assert "age_s" in info

    def test_diag_missing_path(self, mediator: QueryMediator) -> None:
        """diag() for non-existent path returns error."""
        info = mediator.diag("nope")
        assert "error" in info


class TestMediatorConcurrency:
    """Test thread safety of compute locks."""

    def test_concurrent_get_dedup(self, mediator: QueryMediator) -> None:
        """Multiple threads requesting same path only compute once."""
        call_count = 0
        lock = threading.Lock()

        def slow_resolver():
            nonlocal call_count
            with lock:
                call_count += 1
            time.sleep(0.1)
            return "result"

        mediator.tree.register(TreeRegistration(
            path="slow", resolver=slow_resolver, ttl=60,
        ))

        results: list[dict] = []
        errors: list[Exception] = []

        def worker():
            try:
                r = mediator.get("slow")
                results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors
        assert len(results) == 5
        assert call_count == 1  # only one computation
        for r in results:
            assert r["data"] == "result"
