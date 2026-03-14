"""
Tests for the activity logging subscriber.

Verifies that computed events trigger activity logging and audit staging.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.subscribers.activity import (
    _on_computed,
    _path_to_card_key,
    register_activity_subscriber,
)
from src.core.services.mediator.tree import DataTree, TreeRegistration


# ── Path mapping tests ─────────────────────────────────────────────


class TestPathToCardKey:
    """Test mediator path → legacy card key conversion."""

    def test_devops_paths(self):
        assert _path_to_card_key("devops.docker") == "docker"
        assert _path_to_card_key("devops.k8s") == "k8s"
        assert _path_to_card_key("devops.security") == "security"
        assert _path_to_card_key("devops.status") == "project-status"

    def test_audit_paths(self):
        assert _path_to_card_key("audit.scores") == "audit:scores"
        assert _path_to_card_key("audit.l2_risks") == "audit:l2:risks"
        assert _path_to_card_key("audit.scores_enriched") == "audit:scores:enriched"

    def test_github_paths(self):
        assert _path_to_card_key("github.pulls") == "gh-pulls"
        assert _path_to_card_key("github.runs") == "gh-runs"
        assert _path_to_card_key("github.workflows") == "gh-workflows"

    def test_detect_wizard(self):
        assert _path_to_card_key("detect.wizard") == "wiz:detect"

    def test_catalog_paths(self):
        assert _path_to_card_key("catalog.tools") == "tools"
        assert _path_to_card_key("catalog.builders") == "builders"
        assert _path_to_card_key("catalog.scripts") == "scripts"
        assert _path_to_card_key("catalog.pages") == "pages"

    def test_unknown_path_strips_domain(self):
        assert _path_to_card_key("unknown.something") == "something"


# ── Callback tests ─────────────────────────────────────────────────


class TestOnComputed:
    """Test the subscriber callback logic."""

    def test_ignores_non_computed_events(self):
        """Events that are not 'computed' are ignored."""
        with patch(
            "src.core.services.devops.activity.record_scan_activity"
        ) as mock_record:
            _on_computed({"type": "write", "paths": ["devops.docker"]})
            mock_record.assert_not_called()

    def test_ignores_events_without_compute_meta(self):
        """Events without compute_meta are ignored."""
        with patch(
            "src.core.services.devops.activity.record_scan_activity"
        ) as mock_record:
            _on_computed({"type": "computed", "paths": ["devops.docker"]})
            mock_record.assert_not_called()


# ── Integration test ───────────────────────────────────────────────


class TestActivitySubscriberIntegration:
    """Integration test: mediator.get() → subscriber → activity log."""

    @pytest.fixture()
    def setup(self, tmp_path: Path):
        """Set up a mediator with the activity subscriber."""
        tree = DataTree()
        tree.register(TreeRegistration(
            path="devops.docker",
            resolver=lambda: {
                "available": True,
                "version": "24.0.1",
                "dockerfiles": ["Dockerfile"],
            },
        ))
        m = QueryMediator(tree, tmp_path)
        register_activity_subscriber(m)
        return m, tmp_path

    def test_get_triggers_activity_log(self, setup):
        """get() computation writes to the activity log file."""
        m, root = setup
        activity_path = root / ".state" / "audit_activity.json"

        with patch("src.core.services.event_bus.bus", MagicMock()):
            m.get("devops.docker")

        assert activity_path.exists(), "Activity log file should be created"
        entries = json.loads(activity_path.read_text())
        assert len(entries) >= 1

        entry = entries[-1]
        assert entry["card"] == "docker"
        assert entry["status"] == "ok"
        assert isinstance(entry["duration_s"], float)
        assert entry["duration_s"] >= 0

    def test_get_triggers_audit_staging(self, setup):
        """get() computation stages an audit snapshot."""
        m, root = setup
        pending_path = root / ".state" / "pending_audits.json"

        with patch("src.core.services.event_bus.bus", MagicMock()):
            m.get("devops.docker")

        assert pending_path.exists(), "Pending audits file should be created"
        pending = json.loads(pending_path.read_text())
        assert "docker" in pending
        snapshot = pending["docker"]
        assert snapshot["card_key"] == "docker"
        assert snapshot["status"] == "ok"
        assert "data" in snapshot

    def test_cache_hit_does_not_log(self, setup):
        """Cache hits should NOT trigger activity logging."""
        m, root = setup
        activity_path = root / ".state" / "audit_activity.json"

        with patch("src.core.services.event_bus.bus", MagicMock()):
            m.get("devops.docker")

        count_after_first = len(json.loads(activity_path.read_text()))

        # Second get — cache hit
        m.get("devops.docker")

        count_after_second = len(json.loads(activity_path.read_text()))
        assert count_after_second == count_after_first, (
            "Cache hit should not add activity entries"
        )

    def test_error_data_logs_error_status(self, tmp_path: Path):
        """If resolver returns data with 'error' key, status is 'error'."""
        tree = DataTree()
        tree.register(TreeRegistration(
            path="devops.broken",
            resolver=lambda: {"error": "connection refused"},
        ))
        m = QueryMediator(tree, tmp_path)
        register_activity_subscriber(m)

        with patch("src.core.services.event_bus.bus", MagicMock()):
            m.get("devops.broken")

        activity_path = tmp_path / ".state" / "audit_activity.json"
        entries = json.loads(activity_path.read_text())
        entry = entries[-1]
        assert entry["status"] == "error"
