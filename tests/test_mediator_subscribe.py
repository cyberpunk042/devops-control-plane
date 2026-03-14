"""
Phase 6A tests — subscribe() + unsubscribe() + _notify_subscribers().

Tests for:
- Subscription ID generation
- Callback invocation on write/invalidation
- Glob pattern matching (wildcard, exact)
- Unsubscribe stops delivery
- Subscriber errors are swallowed
- notify=False suppresses subscribers
- Batch mode notifies on exit
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
    t = DataTree()
    t.register(TreeRegistration(
        path="devops.git",
        resolver=lambda: {"tool": "git"},
    ))
    t.register(TreeRegistration(
        path="devops.docker",
        resolver=lambda: {"tool": "docker"},
        depends_on=["devops.git"],
    ))
    t.register(TreeRegistration(
        path="posture.toolchain",
        resolver=lambda: {"pillar": "toolchain"},
    ))
    return t


@pytest.fixture()
def mediator(tree: DataTree) -> QueryMediator:
    return QueryMediator(tree, Path("/tmp/test"))


# ── TestSubscribe ─────────────────────────────────────────────────


class TestSubscribe:
    """Verify subscribe/unsubscribe and callback delivery."""

    def test_subscribe_returns_unique_id(
        self, mediator: QueryMediator,
    ) -> None:
        """Each subscribe() returns a unique ID."""
        cb = MagicMock()
        id1 = mediator.subscribe("devops.*", cb)
        id2 = mediator.subscribe("devops.*", cb)
        assert id1 != id2
        assert id1.startswith("sub-")
        assert id2.startswith("sub-")

    def test_subscriber_called_on_write(
        self, mediator: QueryMediator,
    ) -> None:
        """Subscriber receives events when data is written."""
        cb = MagicMock()
        mediator.subscribe("devops.*", cb)

        with patch("src.core.services.event_bus.bus", MagicMock()):
            mediator.put("devops.git", data={"v": 1}, cascade=False)

        cb.assert_called_once()
        event = cb.call_args[0][0]
        assert event["type"] == "write"
        assert event["trigger"] == "devops.git"
        assert "devops.git" in event["paths"]
        assert isinstance(event["seq"], int)

    def test_subscriber_called_on_invalidation(
        self, mediator: QueryMediator,
    ) -> None:
        """Subscriber receives events when data is invalidated."""
        # Seed data first
        mediator.put("devops.git", data={"v": 1}, notify=False)

        cb = MagicMock()
        mediator.subscribe("devops.*", cb)

        with patch("src.core.services.event_bus.bus", MagicMock()):
            mediator.put("devops.git", cascade=False)

        cb.assert_called_once()
        event = cb.call_args[0][0]
        assert event["type"] == "invalidated"
        assert "devops.git" in event["paths"]

    def test_wildcard_pattern_matches(
        self, mediator: QueryMediator,
    ) -> None:
        """Pattern 'devops.*' matches devops.git and devops.docker."""
        cb = MagicMock()
        mediator.subscribe("devops.*", cb)

        with patch("src.core.services.event_bus.bus", MagicMock()):
            mediator.put("devops.git", data={"v": 1}, cascade=False)
            mediator.put("devops.docker", data={"v": 2}, cascade=False)

        assert cb.call_count == 2

    def test_exact_pattern_matches(
        self, mediator: QueryMediator,
    ) -> None:
        """Exact pattern 'devops.git' only matches devops.git."""
        cb = MagicMock()
        mediator.subscribe("devops.git", cb)

        with patch("src.core.services.event_bus.bus", MagicMock()):
            mediator.put("devops.git", data={"v": 1}, cascade=False)
            mediator.put("devops.docker", data={"v": 2}, cascade=False)

        assert cb.call_count == 1

    def test_non_matching_pattern_not_called(
        self, mediator: QueryMediator,
    ) -> None:
        """Subscriber with non-matching pattern is NOT called."""
        cb = MagicMock()
        mediator.subscribe("posture.*", cb)

        with patch("src.core.services.event_bus.bus", MagicMock()):
            mediator.put("devops.git", data={"v": 1}, cascade=False)

        cb.assert_not_called()

    def test_unsubscribe_stops_delivery(
        self, mediator: QueryMediator,
    ) -> None:
        """After unsubscribe, callback is no longer called."""
        cb = MagicMock()
        sub_id = mediator.subscribe("devops.*", cb)

        with patch("src.core.services.event_bus.bus", MagicMock()):
            mediator.put("devops.git", data={"v": 1}, cascade=False)
        assert cb.call_count == 1

        mediator.unsubscribe(sub_id)

        with patch("src.core.services.event_bus.bus", MagicMock()):
            mediator.put("devops.git", data={"v": 2}, cascade=False)
        assert cb.call_count == 1  # still 1, not 2

    def test_unsubscribe_unknown_id_returns_false(
        self, mediator: QueryMediator,
    ) -> None:
        """Unsubscribing with unknown ID returns False."""
        assert mediator.unsubscribe("sub-999") is False

    def test_multiple_subscribers_all_called(
        self, mediator: QueryMediator,
    ) -> None:
        """Multiple subscribers for the same pattern all receive events."""
        cb1 = MagicMock()
        cb2 = MagicMock()
        mediator.subscribe("devops.*", cb1)
        mediator.subscribe("devops.*", cb2)

        with patch("src.core.services.event_bus.bus", MagicMock()):
            mediator.put("devops.git", data={"v": 1}, cascade=False)

        cb1.assert_called_once()
        cb2.assert_called_once()

    def test_subscriber_error_swallowed(
        self, mediator: QueryMediator,
    ) -> None:
        """A failing subscriber doesn't prevent other subscribers."""
        cb_bad = MagicMock(side_effect=ValueError("boom"))
        cb_good = MagicMock()
        mediator.subscribe("devops.*", cb_bad)
        mediator.subscribe("devops.*", cb_good)

        with patch("src.core.services.event_bus.bus", MagicMock()):
            mediator.put("devops.git", data={"v": 1}, cascade=False)

        cb_bad.assert_called_once()
        cb_good.assert_called_once()  # still called despite cb_bad failing

    def test_notify_false_skips_subscribers(
        self, mediator: QueryMediator,
    ) -> None:
        """notify=False suppresses subscriber notification."""
        cb = MagicMock()
        mediator.subscribe("devops.*", cb)

        mediator.put("devops.git", data={"v": 1}, notify=False)

        cb.assert_not_called()

    def test_batch_notifies_on_exit(
        self, mediator: QueryMediator,
    ) -> None:
        """In batch mode, subscribers are notified on exit, not during."""
        cb = MagicMock()
        mediator.subscribe("devops.*", cb)

        with patch("src.core.services.event_bus.bus", MagicMock()):
            with mediator.batch():
                mediator.put("devops.git", data={"v": 1}, cascade=False)
                mediator.put("devops.docker", data={"v": 2}, cascade=False)
                cb.assert_not_called()  # not called during batch

        # Called on exit with aggregate paths
        assert cb.call_count >= 1
        # Gather all paths across all calls
        all_paths = []
        for call in cb.call_args_list:
            all_paths.extend(call[0][0]["paths"])
        assert "devops.git" in all_paths
        assert "devops.docker" in all_paths


# ── TestComputeSubscriber ─────────────────────────────────────────


class TestComputeSubscriber:
    """Verify subscribers fire on get() computation with compute_meta."""

    def test_subscriber_fires_on_get_compute(
        self, mediator: QueryMediator,
    ) -> None:
        """Subscriber is called when get() computes a value."""
        cb = MagicMock()
        mediator.subscribe("devops.*", cb)

        with patch("src.core.services.event_bus.bus", MagicMock()):
            mediator.get("devops.git")

        cb.assert_called_once()
        event = cb.call_args[0][0]
        assert event["type"] == "computed"
        assert event["trigger"] == "devops.git"
        assert "devops.git" in event["paths"]

    def test_compute_meta_contains_data(
        self, mediator: QueryMediator,
    ) -> None:
        """compute_meta includes the computed data."""
        cb = MagicMock()
        mediator.subscribe("devops.*", cb)

        with patch("src.core.services.event_bus.bus", MagicMock()):
            mediator.get("devops.git")

        event = cb.call_args[0][0]
        assert "compute_meta" in event
        meta = event["compute_meta"]
        assert meta["data"] == {"tool": "git"}

    def test_compute_meta_contains_elapsed(
        self, mediator: QueryMediator,
    ) -> None:
        """compute_meta includes elapsed_s."""
        cb = MagicMock()
        mediator.subscribe("devops.*", cb)

        with patch("src.core.services.event_bus.bus", MagicMock()):
            mediator.get("devops.git")

        meta = cb.call_args[0][0]["compute_meta"]
        assert "elapsed_s" in meta
        assert isinstance(meta["elapsed_s"], float)
        assert meta["elapsed_s"] >= 0

    def test_compute_meta_contains_computed_at(
        self, mediator: QueryMediator,
    ) -> None:
        """compute_meta includes computed_at timestamp."""
        cb = MagicMock()
        mediator.subscribe("devops.*", cb)

        with patch("src.core.services.event_bus.bus", MagicMock()):
            mediator.get("devops.git")

        meta = cb.call_args[0][0]["compute_meta"]
        assert "computed_at" in meta
        assert isinstance(meta["computed_at"], float)

    def test_subscriber_not_fired_on_cache_hit(
        self, mediator: QueryMediator,
    ) -> None:
        """Subscriber is NOT called when get() returns cached data."""
        cb = MagicMock()

        # First get — computes (no subscriber yet)
        with patch("src.core.services.event_bus.bus", MagicMock()):
            mediator.get("devops.git")

        # Now subscribe
        mediator.subscribe("devops.*", cb)

        # Second get — cache hit, no compute
        mediator.get("devops.git")

        cb.assert_not_called()

    def test_put_events_have_no_compute_meta(
        self, mediator: QueryMediator,
    ) -> None:
        """put() events do NOT include compute_meta."""
        cb = MagicMock()
        mediator.subscribe("devops.*", cb)

        with patch("src.core.services.event_bus.bus", MagicMock()):
            mediator.put("devops.git", data={"v": 1}, cascade=False)

        event = cb.call_args[0][0]
        assert "compute_meta" not in event
