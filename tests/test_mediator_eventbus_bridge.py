"""
Tests for the EventBus compatibility bridge subscriber.

Verifies that mediator computed events are translated to legacy
cache:done / cache:error events on the EventBus.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.subscribers.eventbus_bridge import (
    _on_computed,
    register_eventbus_bridge,
)
from src.core.services.mediator.tree import DataTree, TreeRegistration


# ── Callback tests ─────────────────────────────────────────────────


class TestOnComputed:
    """Test the bridge callback logic."""

    def test_ignores_non_computed_events(self):
        """Only 'computed' events are bridged."""
        with patch("src.core.services.event_bus.bus") as mock_bus:
            _on_computed({"type": "write", "paths": ["devops.docker"]})
            mock_bus.publish.assert_not_called()

    def test_ignores_events_without_meta(self):
        """Events without compute_meta are skipped."""
        with patch("src.core.services.event_bus.bus") as mock_bus:
            _on_computed({"type": "computed", "paths": ["devops.docker"]})
            mock_bus.publish.assert_not_called()

    def test_bridges_to_cache_done(self):
        """Successful compute → cache:done event."""
        event = {
            "type": "computed",
            "trigger": "devops.docker",
            "paths": ["devops.docker"],
            "compute_meta": {
                "data": {"available": True, "version": "24.0"},
                "elapsed_s": 0.123,
                "computed_at": 1000000.0,
            },
        }
        with patch("src.core.services.event_bus.bus") as mock_bus:
            _on_computed(event)
            mock_bus.publish.assert_called_once_with(
                "cache:done",
                key="docker",
                data={"available": True, "version": "24.0"},
                duration_s=0.123,
            )

    def test_bridges_to_cache_error(self):
        """Error data → cache:error event."""
        event = {
            "type": "computed",
            "trigger": "devops.docker",
            "paths": ["devops.docker"],
            "compute_meta": {
                "data": {"error": "connection refused"},
                "elapsed_s": 0.05,
                "computed_at": 1000000.0,
            },
        }
        with patch("src.core.services.event_bus.bus") as mock_bus:
            _on_computed(event)
            mock_bus.publish.assert_called_once_with(
                "cache:error",
                key="docker",
                error="connection refused",
                duration_s=0.05,
            )

    def test_uses_legacy_card_key(self):
        """Mediator path is translated to legacy card key."""
        event = {
            "type": "computed",
            "trigger": "audit.scores",
            "paths": ["audit.scores"],
            "compute_meta": {
                "data": {"complexity": {}, "quality": {}},
                "elapsed_s": 0.5,
                "computed_at": 1000000.0,
            },
        }
        with patch("src.core.services.event_bus.bus") as mock_bus:
            _on_computed(event)
            mock_bus.publish.assert_called_once()
            assert mock_bus.publish.call_args[1]["key"] == "audit:scores"


# ── Integration test ───────────────────────────────────────────────


class TestEventBusBridgeIntegration:
    """Integration: mediator.get() → subscriber → EventBus."""

    def test_get_emits_cache_done(self):
        """get() computation triggers cache:done on EventBus."""
        tree = DataTree()
        tree.register(TreeRegistration(
            path="devops.git",
            resolver=lambda: {"branch": "main", "ahead": 0},
        ))
        m = QueryMediator(tree, Path("/tmp/test"))
        register_eventbus_bridge(m)

        with patch("src.core.services.event_bus.bus") as mock_bus:
            m.get("devops.git")

        # Should have mediator:write (from _publish_change) AND
        # cache:done (from our bridge)
        event_types = [c.args[0] for c in mock_bus.publish.call_args_list]
        assert "cache:done" in event_types

        # Verify the cache:done payload
        done_call = next(
            c for c in mock_bus.publish.call_args_list
            if c.args[0] == "cache:done"
        )
        assert done_call[1]["key"] == "git"
        assert done_call[1]["data"]["branch"] == "main"

    def test_cache_hit_does_not_emit(self):
        """Cache hits do NOT trigger cache:done."""
        tree = DataTree()
        tree.register(TreeRegistration(
            path="devops.docker",
            resolver=lambda: {"available": True},
        ))
        m = QueryMediator(tree, Path("/tmp/test"))

        # First get — computes (no bridge yet)
        with patch("src.core.services.event_bus.bus", MagicMock()):
            m.get("devops.docker")

        # Now register bridge
        register_eventbus_bridge(m)

        # Second get — cache hit
        with patch("src.core.services.event_bus.bus") as mock_bus:
            m.get("devops.docker")

        # EventBus should NOT have been called
        mock_bus.publish.assert_not_called()
