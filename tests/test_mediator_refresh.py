"""
Phase 6B tests — refresh(), refresh_branch(), refresh_stale(), bust().

Tests for:
- Single-path refresh
- Multi-path refresh
- refresh_branch with prefix matching
- refresh_stale with TTL expiry
- bust with max_age temporal invalidation
- bust with prefix filter
- Error handling in refresh
- Parallel execution via executor
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.tree import DataTree, TreeRegistration


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture()
def tree() -> DataTree:
    t = DataTree()
    t.register(TreeRegistration(
        path="posture.platform",
        resolver=lambda: {"pillar": "platform"},
        ttl=0.1,
    ))
    t.register(TreeRegistration(
        path="posture.toolchain",
        resolver=lambda: {"pillar": "toolchain"},
        ttl=0.1,
    ))
    t.register(TreeRegistration(
        path="posture.project",
        resolver=lambda: {"pillar": "project"},
        ttl=0.1,
    ))
    t.register(TreeRegistration(
        path="devops.git",
        resolver=lambda: {"card": "git"},
        ttl=60,
    ))
    t.register(TreeRegistration(
        path="devops.docker",
        resolver=lambda: {"card": "docker"},
        ttl=60,
    ))
    return t


@pytest.fixture()
def mediator(tree: DataTree) -> QueryMediator:
    return QueryMediator(tree, Path("/tmp/test"))


# ── TestRefresh ───────────────────────────────────────────────────


class TestRefresh:
    """Verify refresh() force-recompute."""

    def test_refresh_single_path(
        self, mediator: QueryMediator,
    ) -> None:
        """Refresh a single path returns its result."""
        result = mediator.refresh("posture.platform")
        assert "posture.platform" in result["refreshed"]
        assert result["errors"] == {}
        assert result["elapsed_s"] >= 0

    def test_refresh_multiple_paths(
        self, mediator: QueryMediator,
    ) -> None:
        """Refresh multiple paths returns all results."""
        result = mediator.refresh(
            "posture.platform", "posture.toolchain", "posture.project",
        )
        assert len(result["refreshed"]) == 3
        assert "posture.platform" in result["refreshed"]
        assert "posture.toolchain" in result["refreshed"]
        assert "posture.project" in result["refreshed"]
        assert result["errors"] == {}

    def test_refresh_empty_paths(
        self, mediator: QueryMediator,
    ) -> None:
        """Refresh with no paths returns empty result."""
        result = mediator.refresh()
        assert result["refreshed"] == {}
        assert result["errors"] == {}
        assert result["elapsed_s"] == 0.0

    def test_refresh_unknown_path_in_errors(
        self, mediator: QueryMediator,
    ) -> None:
        """Unknown path appears in errors dict."""
        result = mediator.refresh("nonexistent.path")
        assert "nonexistent.path" in result["errors"]
        assert result["refreshed"] == {}

    def test_refresh_includes_elapsed(
        self, mediator: QueryMediator,
    ) -> None:
        """Result includes elapsed_s timing."""
        result = mediator.refresh("posture.platform")
        assert "elapsed_s" in result
        assert isinstance(result["elapsed_s"], float)

    def test_refresh_result_has_meta(
        self, mediator: QueryMediator,
    ) -> None:
        """Refreshed entries contain result metadata."""
        result = mediator.refresh("posture.platform")
        meta = result["refreshed"]["posture.platform"]
        assert "source" in meta
        assert meta["source"] == "computed"

    def test_refresh_updates_cache(
        self, mediator: QueryMediator,
    ) -> None:
        """After refresh, get() returns cached result."""
        mediator.refresh("posture.platform")

        result = mediator.get("posture.platform")
        assert result["meta"]["source"] == "cache"
        assert result["data"] == {"pillar": "platform"}

    def test_refresh_with_executor_parallel(
        self, tree: DataTree,
    ) -> None:
        """With executor, multiple paths run via the executor."""
        executor = ThreadPoolExecutor(max_workers=2)
        try:
            m = QueryMediator(tree, Path("/tmp/test"), executor=executor)
            result = m.refresh(
                "posture.platform", "posture.toolchain",
            )
            assert len(result["refreshed"]) == 2
            assert result["errors"] == {}
        finally:
            executor.shutdown(wait=True)


# ── TestRefreshBranch ─────────────────────────────────────────────


class TestRefreshBranch:
    """Verify refresh_branch() prefix matching."""

    def test_refresh_branch_posture(
        self, mediator: QueryMediator,
    ) -> None:
        """refresh_branch('posture') refreshes all posture.* nodes."""
        result = mediator.refresh_branch("posture")
        assert len(result["refreshed"]) == 3
        assert "posture.platform" in result["refreshed"]
        assert "posture.toolchain" in result["refreshed"]
        assert "posture.project" in result["refreshed"]

    def test_refresh_branch_devops(
        self, mediator: QueryMediator,
    ) -> None:
        """refresh_branch('devops') refreshes only devops.* nodes."""
        result = mediator.refresh_branch("devops")
        assert len(result["refreshed"]) == 2
        assert "devops.git" in result["refreshed"]
        assert "devops.docker" in result["refreshed"]

    def test_refresh_branch_no_match(
        self, mediator: QueryMediator,
    ) -> None:
        """refresh_branch with non-existent prefix returns empty."""
        result = mediator.refresh_branch("nonexistent")
        assert result["refreshed"] == {}
        assert result["elapsed_s"] == 0.0


# ── TestRefreshStale ──────────────────────────────────────────────


class TestRefreshStale:
    """Verify refresh_stale() only refreshes expired nodes."""

    def test_refresh_stale_only_expired(
        self, mediator: QueryMediator,
    ) -> None:
        """Only stale cached entries are refreshed."""
        # Seed all posture nodes (TTL=0.1s)
        mediator.put("posture.platform", data={"v": 1}, notify=False)
        mediator.put("posture.toolchain", data={"v": 2}, notify=False)
        # Seed devops.git (TTL=60s) — won't be stale
        mediator.put("devops.git", data={"v": 3}, notify=False)

        # Wait for posture TTL to expire
        time.sleep(0.15)

        result = mediator.refresh_stale()
        # Only posture nodes should be refreshed (stale)
        assert "posture.platform" in result["refreshed"]
        assert "posture.toolchain" in result["refreshed"]
        # devops.git should NOT be refreshed (still fresh)
        assert "devops.git" not in result["refreshed"]

    def test_refresh_stale_skips_fresh(
        self, mediator: QueryMediator,
    ) -> None:
        """Fresh entries are not refreshed."""
        mediator.put("devops.git", data={"v": 1}, notify=False)
        # Don't wait — everything is fresh

        result = mediator.refresh_stale()
        assert result["refreshed"] == {}

    def test_refresh_stale_with_prefix(
        self, mediator: QueryMediator,
    ) -> None:
        """Prefix filter limits which stale entries are refreshed."""
        # Seed and make stale
        mediator.put("posture.platform", data={"v": 1}, notify=False)
        mediator.put("posture.toolchain", data={"v": 2}, notify=False)
        time.sleep(0.15)

        result = mediator.refresh_stale(prefix="posture")
        assert len(result["refreshed"]) == 2

    def test_refresh_stale_nothing_cached(
        self, mediator: QueryMediator,
    ) -> None:
        """No cached entries → nothing to refresh."""
        result = mediator.refresh_stale()
        assert result["refreshed"] == {}


# ── TestBust ──────────────────────────────────────────────────────


class TestBust:
    """Verify bust() temporal invalidation."""

    def test_bust_invalidates_old(
        self, mediator: QueryMediator,
    ) -> None:
        """Entries older than max_age are invalidated."""
        mediator.put("posture.platform", data={"v": 1}, notify=False)
        time.sleep(0.15)

        result = mediator.bust(max_age=0.1)
        assert "posture.platform" in result["busted"]
        assert result["count"] >= 1

        # Cache should be gone
        entry = mediator._get_cached("posture.platform")
        assert entry is None

    def test_bust_skips_young(
        self, mediator: QueryMediator,
    ) -> None:
        """Entries younger than max_age are NOT invalidated."""
        mediator.put("devops.git", data={"v": 1}, notify=False)

        result = mediator.bust(max_age=60)
        assert "devops.git" not in result["busted"]
        assert result["count"] == 0

    def test_bust_with_prefix(
        self, mediator: QueryMediator,
    ) -> None:
        """Prefix filter limits which entries are busted."""
        mediator.put("posture.platform", data={"v": 1}, notify=False)
        mediator.put("devops.git", data={"v": 2}, notify=False)
        time.sleep(0.15)

        result = mediator.bust(max_age=0.1, prefix="posture")
        assert "posture.platform" in result["busted"]
        assert "devops.git" not in result["busted"]

    def test_bust_empty_cache(
        self, mediator: QueryMediator,
    ) -> None:
        """Bust with nothing cached returns empty."""
        result = mediator.bust(max_age=0)
        assert result["busted"] == []
        assert result["count"] == 0

    def test_bust_cascades(
        self, tree: DataTree,
    ) -> None:
        """Bust invalidation cascades to dependents."""
        # Add a dependency: docker depends on git
        tree.register(TreeRegistration(
            path="devops.ci",
            resolver=lambda: {"card": "ci"},
            depends_on=["devops.git"],
        ))
        m = QueryMediator(tree, Path("/tmp/test"))

        # Seed both
        m.put("devops.git", data={"v": 1}, notify=False)
        m.put("devops.ci", data={"v": 2}, notify=False)
        time.sleep(0.15)

        # Bust git — should cascade to ci
        result = m.bust(max_age=0.1, notify=False)
        assert "devops.git" in result["busted"]

        # ci should also be invalidated via cascade
        ci_entry = m._get_cached("devops.ci")
        assert ci_entry is None


# ── TestDiagPhase6B ───────────────────────────────────────────────


class TestDiagPhase6B:
    """Verify Phase 6B diag additions."""

    def test_diag_has_executor(
        self, mediator: QueryMediator,
    ) -> None:
        """Summary diag includes has_executor."""
        info = mediator.diag()
        assert "has_executor" in info
        assert info["has_executor"] is False

    def test_diag_has_executor_true(
        self, tree: DataTree,
    ) -> None:
        """has_executor is True when executor is injected."""
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            m = QueryMediator(tree, Path("/tmp/test"), executor=executor)
            info = m.diag()
            assert info["has_executor"] is True
        finally:
            executor.shutdown(wait=True)
