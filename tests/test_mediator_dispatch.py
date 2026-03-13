"""
Phase 6B tests — dispatch() async background recompute.

Tests for:
- Task ID generation
- Paths marked as refreshing
- on_stale hook fallback
- Executor-based dispatch
- dispatch() with no executor/hook
- _dispatch_worker clears refreshing
- dispatch with unregistered paths
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
        ttl=60,
    ))
    t.register(TreeRegistration(
        path="posture.toolchain",
        resolver=lambda: {"pillar": "toolchain"},
        ttl=60,
    ))
    return t


@pytest.fixture()
def mediator(tree: DataTree) -> QueryMediator:
    return QueryMediator(tree, Path("/tmp/test"))


# ── TestDispatch ──────────────────────────────────────────────────


class TestDispatch:
    """Verify dispatch() async recompute."""

    def test_dispatch_returns_task_id(
        self, mediator: QueryMediator,
    ) -> None:
        """dispatch() returns a unique task ID."""
        r1 = mediator.dispatch("posture.platform")
        r2 = mediator.dispatch("posture.toolchain")
        assert r1["task_id"] != r2["task_id"]
        assert r1["task_id"].startswith("task-")
        assert r1["status"] == "dispatched"

    def test_dispatch_marks_refreshing(
        self, mediator: QueryMediator,
    ) -> None:
        """dispatch() marks paths as refreshing."""
        mediator.dispatch("posture.platform")
        assert "posture.platform" in mediator._refreshing

    def test_dispatch_calls_on_stale_hook(
        self, tree: DataTree,
    ) -> None:
        """Without executor, dispatch falls back to on_stale hook."""
        hook = MagicMock()
        m = QueryMediator(tree, Path("/tmp/test"), on_stale=hook)

        m.dispatch("posture.platform")

        hook.assert_called_once_with("posture.platform")

    def test_dispatch_multiple_paths(
        self, tree: DataTree,
    ) -> None:
        """dispatch() with multiple paths calls hook for each."""
        hook = MagicMock()
        m = QueryMediator(tree, Path("/tmp/test"), on_stale=hook)

        result = m.dispatch("posture.platform", "posture.toolchain")
        assert len(result["paths"]) == 2
        assert hook.call_count == 2

    def test_dispatch_with_executor(
        self, tree: DataTree,
    ) -> None:
        """With executor, dispatch submits to executor and returns immediately."""
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            m = QueryMediator(tree, Path("/tmp/test"), executor=executor)

            result = m.dispatch("posture.platform")
            assert result["status"] == "dispatched"
            assert "posture.platform" in result["paths"]

            # Wait for background worker to finish
            executor.shutdown(wait=True)

            # After worker completes, data should be cached
            get_result = m.get("posture.platform")
            assert get_result["data"] == {"pillar": "platform"}

            # Refreshing should be cleared by worker
            assert "posture.platform" not in m._refreshing
        finally:
            executor.shutdown(wait=False)

    def test_dispatch_without_anything(
        self, mediator: QueryMediator,
    ) -> None:
        """Without executor or hook, dispatch returns dispatched but no work."""
        result = mediator.dispatch("posture.platform")
        assert result["status"] == "dispatched"
        # Path is marked refreshing but won't actually refresh
        assert "posture.platform" in mediator._refreshing

    def test_dispatch_unregistered_path(
        self, mediator: QueryMediator,
    ) -> None:
        """dispatch() with unregistered path returns empty."""
        result = mediator.dispatch("nonexistent.path")
        assert result["status"] == "empty"
        assert result["paths"] == []

    def test_dispatch_worker_clears_refreshing(
        self, tree: DataTree,
    ) -> None:
        """_dispatch_worker clears refreshing after completing."""
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            m = QueryMediator(tree, Path("/tmp/test"), executor=executor)
            m.dispatch("posture.platform", "posture.toolchain")

            # Wait for background work
            executor.shutdown(wait=True)

            assert "posture.platform" not in m._refreshing
            assert "posture.toolchain" not in m._refreshing
        finally:
            executor.shutdown(wait=False)

    def test_dispatch_hook_error_swallowed(
        self, tree: DataTree,
    ) -> None:
        """Failing on_stale hook doesn't prevent dispatch from returning."""
        hook = MagicMock(side_effect=RuntimeError("boom"))
        m = QueryMediator(tree, Path("/tmp/test"), on_stale=hook)

        # Should not raise
        result = m.dispatch("posture.platform")
        assert result["status"] == "dispatched"
