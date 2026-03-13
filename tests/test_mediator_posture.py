"""Tests for QueryMediator Phase 1 — posture system registration and wiring."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.registrations.posture import register_posture
from src.core.services.mediator.tree import DataTree


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def mediator() -> QueryMediator:
    """Mediator with posture nodes registered."""
    tree = DataTree()
    m = QueryMediator(tree, Path("."))
    register_posture(m)
    return m


# ── Registration tests ─────────────────────────────────────────────


class TestPostureRegistration:
    """Test that posture nodes are registered correctly."""

    def test_six_nodes_registered(self, mediator: QueryMediator) -> None:
        """All 6 posture nodes should be registered."""
        paths = mediator.tree.all_paths()
        assert len(paths) == 6
        expected = {
            "posture.platform",
            "posture.toolchain",
            "posture.project",
            "posture.runtime",
            "posture.full",
            "posture.summary",
        }
        assert set(paths) == expected

    def test_tree_structure(self, mediator: QueryMediator) -> None:
        """posture branch should have 6 children."""
        children = mediator.tree.children("posture")
        paths = sorted(c.path for c in children)
        assert paths == [
            "posture.full",
            "posture.platform",
            "posture.project",
            "posture.runtime",
            "posture.summary",
            "posture.toolchain",
        ]

    def test_posture_branch_exists(self, mediator: QueryMediator) -> None:
        """posture should be an auto-created branch."""
        node = mediator.tree.resolve("posture")
        assert node is not None
        assert node.is_branch
        assert not node.is_registered  # auto-created

    def test_platform_ttl_infinite(self, mediator: QueryMediator) -> None:
        """posture.platform should have infinite TTL."""
        node = mediator.tree.resolve("posture.platform")
        assert node is not None
        assert node.ttl == math.inf

    def test_runtime_ttl_zero(self, mediator: QueryMediator) -> None:
        """posture.runtime should have TTL=0."""
        node = mediator.tree.resolve("posture.runtime")
        assert node is not None
        assert node.ttl == 0

    def test_toolchain_ttl(self, mediator: QueryMediator) -> None:
        """posture.toolchain should have 300s TTL."""
        node = mediator.tree.resolve("posture.toolchain")
        assert node is not None
        assert node.ttl == 300

    def test_all_have_resolvers(self, mediator: QueryMediator) -> None:
        """Every registered posture node should have a resolver."""
        for path in mediator.tree.all_paths():
            node = mediator.tree.resolve(path)
            assert node is not None
            assert node.resolver is not None, f"{path} has no resolver"

    def test_persist_flags(self, mediator: QueryMediator) -> None:
        """All nodes except runtime should be persistent."""
        expected_persist = {
            "posture.platform": True,
            "posture.toolchain": True,
            "posture.project": True,
            "posture.runtime": False,
            "posture.full": True,
            "posture.summary": True,
        }
        for path, should_persist in expected_persist.items():
            node = mediator.tree.resolve(path)
            assert node is not None
            assert node.persist is should_persist, (
                f"{path}: persist={node.persist}, expected={should_persist}"
            )


# ── Dependency graph tests ─────────────────────────────────────────


class TestPostureCascade:
    """Test cascade chain correctness."""

    def test_toolchain_cascades_to_full_and_summary(
        self, mediator: QueryMediator
    ) -> None:
        """Invalidating toolchain should cascade to full → summary."""
        deps = mediator.tree.dependents("posture.toolchain")
        assert "posture.full" in deps
        assert "posture.summary" in deps

    def test_platform_cascades_to_full_and_summary(
        self, mediator: QueryMediator
    ) -> None:
        """Invalidating platform should cascade to full → summary."""
        deps = mediator.tree.dependents("posture.platform")
        assert "posture.full" in deps
        assert "posture.summary" in deps

    def test_project_cascades_to_full_and_summary(
        self, mediator: QueryMediator
    ) -> None:
        """Invalidating project should cascade to full → summary."""
        deps = mediator.tree.dependents("posture.project")
        assert "posture.full" in deps
        assert "posture.summary" in deps

    def test_runtime_cascades_to_full_and_summary(
        self, mediator: QueryMediator
    ) -> None:
        """Invalidating runtime should cascade to full → summary."""
        deps = mediator.tree.dependents("posture.runtime")
        assert "posture.full" in deps
        assert "posture.summary" in deps

    def test_full_depends_on_four_pillars(
        self, mediator: QueryMediator
    ) -> None:
        """posture.full should depend on all four pillars."""
        node = mediator.tree.resolve("posture.full")
        assert node is not None
        assert set(node.depends_on) == {
            "posture.platform",
            "posture.toolchain",
            "posture.project",
            "posture.runtime",
        }

    def test_summary_depends_on_full(
        self, mediator: QueryMediator
    ) -> None:
        """posture.summary should depend on posture.full."""
        node = mediator.tree.resolve("posture.summary")
        assert node is not None
        assert node.depends_on == ["posture.full"]

    def test_full_cascades_to_summary(
        self, mediator: QueryMediator
    ) -> None:
        """Invalidating full should cascade to summary."""
        deps = mediator.tree.dependents("posture.full")
        assert "posture.summary" in deps

    def test_summary_has_no_dependents(
        self, mediator: QueryMediator
    ) -> None:
        """summary is a terminal node — nothing depends on it."""
        deps = mediator.tree.dependents("posture.summary")
        assert deps == []


# ── TTL=0 behavior tests ──────────────────────────────────────────


class TestTtlZero:
    """Test TTL=0 skip-cache behavior in the mediator."""

    def test_ttl0_never_caches(self) -> None:
        """Node with TTL=0 should call resolver every time, never cache."""
        call_count = 0

        def counter():
            nonlocal call_count
            call_count += 1
            return call_count

        tree = DataTree()
        from src.core.services.mediator.tree import TreeRegistration

        tree.register(TreeRegistration(path="test.fresh", resolver=counter, ttl=0))
        m = QueryMediator(tree, Path("."))

        r1 = m.get("test.fresh")
        r2 = m.get("test.fresh")
        r3 = m.get("test.fresh")

        assert r1["data"] == 1
        assert r2["data"] == 2
        assert r3["data"] == 3
        assert call_count == 3

        # Verify nothing is in cache
        assert m._get_cached("test.fresh") is None

    def test_ttl0_with_explain(self) -> None:
        """TTL=0 path should explain why it skipped cache."""
        tree = DataTree()
        from src.core.services.mediator.tree import TreeRegistration

        tree.register(TreeRegistration(
            path="test.explain0", resolver=lambda: "ok", ttl=0,
        ))
        m = QueryMediator(tree, Path("."))

        r = m.get("test.explain0", explain=True)
        assert "ttl=0" in r["meta"]["explain"]
        assert "always fresh" in r["meta"]["explain"]


# ── Diag tests ─────────────────────────────────────────────────────


class TestPostureDiag:
    """Test diagnostics for posture nodes."""

    def test_diag_summary_shows_six(self, mediator: QueryMediator) -> None:
        """diag() should show 6 registered posture nodes."""
        info = mediator.diag()
        assert info["tree"]["registered"] == 6
        # runtime has persist=False
        assert info["tree"]["persistent"] == 5

    def test_diag_toolchain_detail(self, mediator: QueryMediator) -> None:
        """diag('posture.toolchain') should show correct metadata."""
        info = mediator.diag("posture.toolchain")
        assert info["path"] == "posture.toolchain"
        assert info["registered"] is True
        assert info["has_resolver"] is True
        assert info["ttl"] == 300
        assert info["persist"] is True
        assert info["cached"] is False  # not computed yet

    def test_diag_posture_branch(self, mediator: QueryMediator) -> None:
        """diag('posture') should show branch info (not registered)."""
        info = mediator.diag("posture")
        assert info["path"] == "posture"
        assert info["registered"] is False
        assert info["is_branch"] is True
        assert len(info["children"]) == 6
