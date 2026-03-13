"""
Phase 5 tests — EventBus Bridge + Path Delta.

Tests for:
- Node seq tracking (last_change_seq stamped on write/invalidate/cascade)
- since_seq shortcut on get()
- EventBus publishing (mediator:write, mediator:invalidated)
- Batch mode (accumulate + aggregate event)
- Diag additions (last_change_seq, batch_active)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.tree import DataTree, TreeRegistration


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture()
def tree() -> DataTree:
    """Tree with a dependency chain: A → B → C and a standalone D."""
    t = DataTree()
    t.register(TreeRegistration(
        path="test.a",
        resolver=lambda: {"value": "a"},
    ))
    t.register(TreeRegistration(
        path="test.b",
        resolver=lambda: {"value": "b"},
        depends_on=["test.a"],
    ))
    t.register(TreeRegistration(
        path="test.c",
        resolver=lambda: {"value": "c"},
        depends_on=["test.b"],
    ))
    t.register(TreeRegistration(
        path="test.d",
        resolver=lambda: {"value": "d"},
    ))
    return t


@pytest.fixture()
def mediator(tree: DataTree) -> QueryMediator:
    return QueryMediator(tree, Path("/tmp/test"))


# ── TestNodeSeqTracking ───────────────────────────────────────────


class TestNodeSeqTracking:
    """Verify that last_change_seq is stamped correctly on nodes."""

    def test_initial_last_change_seq_is_zero(
        self, mediator: QueryMediator,
    ) -> None:
        """All nodes start with last_change_seq=0."""
        for p in mediator.tree.all_paths():
            node = mediator.tree.resolve(p)
            assert node is not None
            assert node.last_change_seq == 0

    def test_put_write_stamps_node_seq(
        self, mediator: QueryMediator,
    ) -> None:
        """Writing data stamps last_change_seq on the target node."""
        result = mediator.put("test.a", data={"x": 1}, notify=False)
        seq = result["seq"]

        node = mediator.tree.resolve("test.a")
        assert node is not None
        assert node.last_change_seq == seq

    def test_put_invalidate_stamps_node_seq(
        self, mediator: QueryMediator,
    ) -> None:
        """Invalidating a cached node stamps last_change_seq."""
        # Seed data first
        mediator.put("test.d", data={"x": 1}, notify=False)

        # Now invalidate
        result = mediator.put("test.d", notify=False)
        seq = result["seq"]

        node = mediator.tree.resolve("test.d")
        assert node is not None
        assert node.last_change_seq == seq

    def test_cascade_stamps_dependent_nodes(
        self, mediator: QueryMediator,
    ) -> None:
        """Cascade invalidation stamps last_change_seq on all affected dependents."""
        # Seed data into A, B, and C
        mediator.put("test.a", data={"x": 1}, cascade=False, notify=False)
        mediator.put("test.b", data={"x": 2}, cascade=False, notify=False)
        mediator.put("test.c", data={"x": 3}, cascade=False, notify=False)

        # Invalidate A with cascade — should cascade to B and C
        result = mediator.put("test.a", cascade=True, notify=False)
        seq = result["seq"]

        assert "test.b" in result["invalidated"]
        assert "test.c" in result["invalidated"]

        # Check that dependent nodes got stamped
        node_b = mediator.tree.resolve("test.b")
        node_c = mediator.tree.resolve("test.c")
        assert node_b is not None
        assert node_c is not None
        assert node_b.last_change_seq == seq
        assert node_c.last_change_seq == seq

    def test_seq_is_monotonically_increasing(
        self, mediator: QueryMediator,
    ) -> None:
        """Each put() gets a strictly increasing seq."""
        seqs = []
        for i in range(5):
            result = mediator.put("test.d", data={"i": i}, notify=False)
            seqs.append(result["seq"])

        assert seqs == sorted(seqs)
        assert len(set(seqs)) == 5  # all unique


# ── TestSinceSeq ──────────────────────────────────────────────────


class TestSinceSeq:
    """Verify the since_seq shortcut on get()."""

    def test_get_since_seq_unchanged_returns_false(
        self, mediator: QueryMediator,
    ) -> None:
        """If node hasn't changed since since_seq, return changed=False."""
        # Write data (seq=1)
        result = mediator.put("test.d", data={"v": 1}, notify=False)
        write_seq = result["seq"]

        # Ask with since_seq >= write_seq → no change
        r = mediator.get("test.d", since_seq=write_seq)
        assert r["changed"] is False
        assert r["meta"]["current_seq"] == write_seq

    def test_get_since_seq_changed_returns_data(
        self, mediator: QueryMediator,
    ) -> None:
        """If node changed after since_seq, return full data."""
        # Write data twice
        mediator.put("test.d", data={"v": 1}, notify=False)
        result2 = mediator.put("test.d", data={"v": 2}, notify=False)
        _write_seq = result2["seq"]

        # Ask with since_seq=0 (before any change) → data returned
        r = mediator.get("test.d", since_seq=0)
        assert "data" in r
        assert r["data"] == {"v": 2}
        assert r["meta"]["source"] == "cache"

    def test_get_since_seq_zero_always_returns_data(
        self, mediator: QueryMediator,
    ) -> None:
        """since_seq=0 always returns data (0 < any positive seq)."""
        mediator.put("test.d", data={"v": 1}, notify=False)

        r = mediator.get("test.d", since_seq=0)
        assert "data" in r

    def test_get_since_seq_none_is_normal_get(
        self, mediator: QueryMediator,
    ) -> None:
        """since_seq=None behaves exactly like normal get()."""
        r = mediator.get("test.d", since_seq=None)
        assert "data" in r
        assert r["meta"]["source"] == "computed"


# ── TestEventBusPublishing ────────────────────────────────────────


class TestEventBusPublishing:
    """Verify that put() publishes events on the EventBus."""

    def test_put_write_publishes_mediator_write(
        self, mediator: QueryMediator,
    ) -> None:
        """Writing data publishes a mediator:write event."""
        mock_bus = MagicMock()
        with patch(
            "src.core.services.mediator.core.bus",
            mock_bus,
            create=True,
        ):
            # Patch the deferred import
            with patch(
                "src.core.services.event_bus.bus",
                mock_bus,
            ):
                mediator.put("test.d", data={"v": 1}, notify=True)

        # Find the mediator:write call
        write_calls = [
            c for c in mock_bus.publish.call_args_list
            if c[0][0] == "mediator:write"
        ]
        assert len(write_calls) == 1
        call_kwargs = write_calls[0]
        assert call_kwargs[1]["key"] == "test.d"
        assert "test.d" in call_kwargs[1]["data"]["writes"]

    def test_put_invalidate_publishes_mediator_invalidated(
        self, mediator: QueryMediator,
    ) -> None:
        """Invalidating publishes a mediator:invalidated event."""
        # Seed first
        mediator.put("test.d", data={"v": 1}, notify=False)

        mock_bus = MagicMock()
        with patch(
            "src.core.services.event_bus.bus",
            mock_bus,
        ):
            mediator.put("test.d", notify=True)

        inv_calls = [
            c for c in mock_bus.publish.call_args_list
            if c[0][0] == "mediator:invalidated"
        ]
        assert len(inv_calls) == 1
        assert "test.d" in inv_calls[0][1]["data"]["invalidated"]

    def test_cascade_invalidation_publishes_all_paths(
        self, mediator: QueryMediator,
    ) -> None:
        """Cascade invalidation includes all affected paths in the event."""
        # Seed A, B, C
        mediator.put("test.a", data={"v": 1}, cascade=False, notify=False)
        mediator.put("test.b", data={"v": 2}, cascade=False, notify=False)
        mediator.put("test.c", data={"v": 3}, cascade=False, notify=False)

        mock_bus = MagicMock()
        with patch(
            "src.core.services.event_bus.bus",
            mock_bus,
        ):
            mediator.put("test.a", cascade=True, notify=True)

        inv_calls = [
            c for c in mock_bus.publish.call_args_list
            if c[0][0] == "mediator:invalidated"
        ]
        assert len(inv_calls) == 1
        inv_paths = inv_calls[0][1]["data"]["invalidated"]
        assert "test.a" in inv_paths
        assert "test.b" in inv_paths
        assert "test.c" in inv_paths

    def test_notify_false_suppresses_events(
        self, mediator: QueryMediator,
    ) -> None:
        """notify=False suppresses all EventBus publishing."""
        mock_bus = MagicMock()
        with patch(
            "src.core.services.event_bus.bus",
            mock_bus,
        ):
            mediator.put("test.d", data={"v": 1}, notify=False)

        mock_bus.publish.assert_not_called()

    def test_event_payload_structure(
        self, mediator: QueryMediator,
    ) -> None:
        """Verify the exact payload structure of mediator events."""
        mock_bus = MagicMock()
        with patch(
            "src.core.services.event_bus.bus",
            mock_bus,
        ):
            mediator.put("test.d", data={"v": 1}, notify=True)

        write_calls = [
            c for c in mock_bus.publish.call_args_list
            if c[0][0] == "mediator:write"
        ]
        assert len(write_calls) == 1

        # Check publish was called with correct positional + keyword args
        call = write_calls[0]
        assert call[0][0] == "mediator:write"  # event_type
        assert call[1]["key"] == "test.d"       # key kwarg
        data = call[1]["data"]
        assert "trigger" in data
        assert "mediator_seq" in data
        assert "writes" in data
        assert data["trigger"] == "test.d"
        assert isinstance(data["mediator_seq"], int)
        assert data["writes"] == ["test.d"]


# ── TestBatchMode ─────────────────────────────────────────────────


class TestBatchMode:
    """Verify the batch() context manager."""

    def test_batch_suppresses_individual_events(
        self, mediator: QueryMediator,
    ) -> None:
        """During batch, individual put() calls don't publish."""
        mock_bus = MagicMock()
        with patch(
            "src.core.services.event_bus.bus",
            mock_bus,
        ):
            with mediator.batch():
                mediator.put("test.a", data={"v": 1}, notify=True)
                mediator.put("test.d", data={"v": 2}, notify=True)
                # No events should fire yet
                assert mock_bus.publish.call_count == 0

        # After exiting batch, one aggregate event fires
        assert mock_bus.publish.call_count >= 1

    def test_batch_publishes_aggregate_on_exit(
        self, mediator: QueryMediator,
    ) -> None:
        """On batch exit, one aggregate event is published."""
        mock_bus = MagicMock()
        with patch(
            "src.core.services.event_bus.bus",
            mock_bus,
        ):
            with mediator.batch():
                mediator.put("test.a", data={"v": 1}, notify=True)
                mediator.put("test.d", data={"v": 2}, notify=True)

        # Should have exactly one mediator:write event with both paths
        write_calls = [
            c for c in mock_bus.publish.call_args_list
            if c[0][0] == "mediator:write"
        ]
        assert len(write_calls) == 1
        writes = write_calls[0][1]["data"]["writes"]
        assert "test.a" in writes
        assert "test.d" in writes

    def test_batch_accumulates_writes_and_invalidations(
        self, mediator: QueryMediator,
    ) -> None:
        """Batch accumulates both writes and invalidations."""
        # Seed test.d so we can invalidate it
        mediator.put("test.d", data={"v": 0}, notify=False)

        mock_bus = MagicMock()
        with patch(
            "src.core.services.event_bus.bus",
            mock_bus,
        ):
            with mediator.batch():
                # Write to A
                mediator.put("test.a", data={"v": 1}, cascade=False)
                # Invalidate D
                mediator.put("test.d")

        # Should have both write and invalidated events
        write_calls = [
            c for c in mock_bus.publish.call_args_list
            if c[0][0] == "mediator:write"
        ]
        inv_calls = [
            c for c in mock_bus.publish.call_args_list
            if c[0][0] == "mediator:invalidated"
        ]
        assert len(write_calls) == 1
        assert len(inv_calls) == 1
        assert "test.a" in write_calls[0][1]["data"]["writes"]
        assert "test.d" in inv_calls[0][1]["data"]["invalidated"]

    def test_nested_batch_raises_error(
        self, mediator: QueryMediator,
    ) -> None:
        """Nested batch() raises RuntimeError."""
        with mediator.batch():
            with pytest.raises(RuntimeError, match="Nested batch"):
                with mediator.batch():
                    pass  # pragma: no cover

    def test_batch_empty_no_event(
        self, mediator: QueryMediator,
    ) -> None:
        """Empty batch (no put calls) doesn't publish any event."""
        mock_bus = MagicMock()
        with patch(
            "src.core.services.event_bus.bus",
            mock_bus,
        ):
            with mediator.batch():
                pass  # no operations

        mock_bus.publish.assert_not_called()


# ── TestDiagPhase5 ────────────────────────────────────────────────


class TestDiagPhase5:
    """Verify Phase 5 additions to diag()."""

    def test_diag_includes_last_change_seq(
        self, mediator: QueryMediator,
    ) -> None:
        """Node detail includes last_change_seq."""
        mediator.put("test.d", data={"v": 1}, notify=False)

        info = mediator.diag("test.d")
        assert "last_change_seq" in info
        assert info["last_change_seq"] > 0

    def test_diag_includes_batch_state(
        self, mediator: QueryMediator,
    ) -> None:
        """Summary diag includes batch_active."""
        info = mediator.diag()
        assert "batch_active" in info
        assert info["batch_active"] is False
