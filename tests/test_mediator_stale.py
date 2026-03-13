"""
Phase 6A tests — stale_ok + refreshing state.

Tests for:
- stale_ok returns stale data immediately
- stale_ok metadata (stale, refreshing flags)
- on_stale hook invocation
- stale_ok with no hook still returns stale
- stale_ok with fresh data returns normally
- stale_ok with no cache computes blocking
- stale_ok=False blocks on stale (default behavior)
- mark_refreshing / clear_refreshing tracking
- diag() includes refreshing and subscription count
"""

from __future__ import annotations

import time
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
        path="test.fast",
        resolver=lambda: {"v": "fresh"},
        ttl=0.1,  # 100ms TTL — easy to make stale in tests
    ))
    t.register(TreeRegistration(
        path="test.no_ttl",
        resolver=lambda: {"v": "computed"},
    ))
    return t


@pytest.fixture()
def mediator(tree: DataTree) -> QueryMediator:
    return QueryMediator(tree, Path("/tmp/test"))


# ── TestStaleOk ───────────────────────────────────────────────────


class TestStaleOk:
    """Verify stale_ok read-side behavior."""

    def test_stale_ok_returns_stale_data(
        self, mediator: QueryMediator,
    ) -> None:
        """stale_ok=True returns stale cached data instead of recomputing."""
        # Seed data
        mediator.put("test.fast", data={"v": "original"}, notify=False)

        # Wait for TTL to expire
        time.sleep(0.15)

        # Get with stale_ok — should return stale data, not recompute
        result = mediator.get("test.fast", stale_ok=True)
        assert result["data"] == {"v": "original"}
        assert result["meta"]["source"] == "cache_stale"

    def test_stale_ok_meta_has_stale_flag(
        self, mediator: QueryMediator,
    ) -> None:
        """stale_ok result includes stale=True in meta."""
        mediator.put("test.fast", data={"v": "original"}, notify=False)
        time.sleep(0.15)

        result = mediator.get("test.fast", stale_ok=True)
        assert result["meta"]["stale"] is True

    def test_stale_ok_meta_has_refreshing_flag(
        self, mediator: QueryMediator,
    ) -> None:
        """stale_ok result includes refreshing=False when not refreshing."""
        mediator.put("test.fast", data={"v": "original"}, notify=False)
        time.sleep(0.15)

        result = mediator.get("test.fast", stale_ok=True)
        assert result["meta"]["refreshing"] is False

    def test_stale_ok_calls_on_stale_hook(
        self, tree: DataTree,
    ) -> None:
        """stale_ok triggers the on_stale hook with the path."""
        hook = MagicMock()
        m = QueryMediator(tree, Path("/tmp/test"), on_stale=hook)

        m.put("test.fast", data={"v": "original"}, notify=False)
        time.sleep(0.15)

        m.get("test.fast", stale_ok=True)

        hook.assert_called_once_with("test.fast")

    def test_stale_ok_no_hook_still_returns_stale(
        self, mediator: QueryMediator,
    ) -> None:
        """stale_ok works even with on_stale=None (default)."""
        mediator.put("test.fast", data={"v": "original"}, notify=False)
        time.sleep(0.15)

        # on_stale is None by default — should still return stale
        result = mediator.get("test.fast", stale_ok=True)
        assert result["data"] == {"v": "original"}
        assert result["meta"]["source"] == "cache_stale"

    def test_stale_ok_fresh_data_returns_normally(
        self, mediator: QueryMediator,
    ) -> None:
        """stale_ok with fresh cache returns normal result (not stale)."""
        mediator.put("test.fast", data={"v": "original"}, notify=False)

        # Don't wait — data is fresh
        result = mediator.get("test.fast", stale_ok=True)
        assert result["meta"]["source"] == "cache"
        assert "stale" not in result["meta"]

    def test_stale_ok_no_cache_computes_blocking(
        self, mediator: QueryMediator,
    ) -> None:
        """stale_ok with no cached data falls through to blocking compute."""
        # No data seeded — must compute
        result = mediator.get("test.fast", stale_ok=True)
        assert result["data"] == {"v": "fresh"}  # resolver returns "fresh"
        assert result["meta"]["source"] == "computed"

    def test_stale_ok_false_blocks_on_stale(
        self, mediator: QueryMediator,
    ) -> None:
        """Default stale_ok=False recomputes stale data."""
        mediator.put("test.fast", data={"v": "original"}, notify=False)
        time.sleep(0.15)

        result = mediator.get("test.fast")  # stale_ok=False (default)
        # Should recompute, returning resolver result
        assert result["data"] == {"v": "fresh"}
        assert result["meta"]["source"] == "computed"

    def test_stale_ok_hook_error_swallowed(
        self, tree: DataTree,
    ) -> None:
        """Failing on_stale hook doesn't prevent stale data return."""
        hook = MagicMock(side_effect=RuntimeError("hook exploded"))
        m = QueryMediator(tree, Path("/tmp/test"), on_stale=hook)

        m.put("test.fast", data={"v": "original"}, notify=False)
        time.sleep(0.15)

        # Should still return stale data despite hook failure
        result = m.get("test.fast", stale_ok=True)
        assert result["data"] == {"v": "original"}
        assert result["meta"]["source"] == "cache_stale"

    def test_stale_ok_explain(
        self, mediator: QueryMediator,
    ) -> None:
        """stale_ok with explain=True includes explanation."""
        mediator.put("test.fast", data={"v": "original"}, notify=False)
        time.sleep(0.15)

        result = mediator.get("test.fast", stale_ok=True, explain=True)
        assert "stale_ok=True" in result["meta"]["explain"]


# ── TestRefreshing ────────────────────────────────────────────────


class TestRefreshing:
    """Verify refreshing state tracking."""

    def test_mark_refreshing(
        self, mediator: QueryMediator,
    ) -> None:
        """mark_refreshing adds path to the set."""
        mediator.mark_refreshing("test.fast")
        assert "test.fast" in mediator._refreshing

    def test_clear_refreshing(
        self, mediator: QueryMediator,
    ) -> None:
        """clear_refreshing removes path from the set."""
        mediator.mark_refreshing("test.fast")
        mediator.clear_refreshing("test.fast")
        assert "test.fast" not in mediator._refreshing

    def test_clear_refreshing_missing(
        self, mediator: QueryMediator,
    ) -> None:
        """clear_refreshing on absent path doesn't error."""
        mediator.clear_refreshing("test.fast")  # should not raise

    def test_meta_shows_refreshing_true(
        self, mediator: QueryMediator,
    ) -> None:
        """stale_ok result shows refreshing=True when path is being refreshed."""
        mediator.put("test.fast", data={"v": "original"}, notify=False)
        mediator.mark_refreshing("test.fast")
        time.sleep(0.15)

        result = mediator.get("test.fast", stale_ok=True)
        assert result["meta"]["refreshing"] is True

    def test_meta_shows_refreshing_false(
        self, mediator: QueryMediator,
    ) -> None:
        """stale_ok result shows refreshing=False when path is NOT refreshing."""
        mediator.put("test.fast", data={"v": "original"}, notify=False)
        time.sleep(0.15)

        result = mediator.get("test.fast", stale_ok=True)
        assert result["meta"]["refreshing"] is False


# ── TestDiagPhase6A ───────────────────────────────────────────────


class TestDiagPhase6A:
    """Verify Phase 6A additions to diag()."""

    def test_diag_includes_refreshing(
        self, mediator: QueryMediator,
    ) -> None:
        """Summary diag includes refreshing list."""
        mediator.mark_refreshing("test.fast")
        info = mediator.diag()
        assert "refreshing" in info
        assert "test.fast" in info["refreshing"]

    def test_diag_includes_subscription_count(
        self, mediator: QueryMediator,
    ) -> None:
        """Summary diag includes subscription count."""
        mediator.subscribe("devops.*", lambda e: None)
        mediator.subscribe("posture.*", lambda e: None)
        info = mediator.diag()
        assert info["subscriptions"] == 2

    def test_diag_detail_includes_refreshing(
        self, mediator: QueryMediator,
    ) -> None:
        """Detail diag includes refreshing flag for a specific node."""
        mediator.mark_refreshing("test.fast")
        info = mediator.diag("test.fast")
        assert info["refreshing"] is True

        mediator.clear_refreshing("test.fast")
        info2 = mediator.diag("test.fast")
        assert info2["refreshing"] is False
