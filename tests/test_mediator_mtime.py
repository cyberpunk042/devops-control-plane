"""Tests for mtime_paths-based staleness in the mediator core engine.

Verifies that nodes with ``mtime_paths`` set correctly detect file
changes and recompute even when the TTL hasn't expired.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from src.core.services.mediator.core import QueryMediator, _check_mtime
from src.core.services.mediator.tree import DataTree, TreeRegistration


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal project structure for mtime testing."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("# app\n")
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n")
    return tmp_path


@pytest.fixture()
def mediator_with_mtime(tmp_project: Path) -> tuple[QueryMediator, list[int]]:
    """Create a mediator with a node that uses mtime_paths."""
    call_count = [0]

    def _resolver():
        call_count[0] += 1
        return {"value": call_count[0]}

    tree = DataTree()
    tree.register(TreeRegistration(
        path="detect.docker",
        resolver=_resolver,
        ttl=3600,  # long TTL — should NOT expire during test
        mtime_paths=["Dockerfile"],
    ))
    m = QueryMediator(tree, tmp_project)
    return m, call_count


# ── _check_mtime unit tests ─────────────────────────────────────


class TestCheckMtime:
    """Unit tests for the _check_mtime helper."""

    def test_no_change_returns_false(self, tmp_project: Path):
        """If files haven't changed, returns False (not stale)."""
        computed_at = time.time() + 1  # computed "in the future"
        assert _check_mtime(tmp_project, ["Dockerfile"], computed_at) is False

    def test_file_changed_returns_true(self, tmp_project: Path):
        """If a watched file was modified after computed_at, returns True."""
        computed_at = time.time() - 10  # computed 10 seconds ago
        # Touch the file
        (tmp_project / "Dockerfile").write_text("FROM python:3.13\n")
        assert _check_mtime(tmp_project, ["Dockerfile"], computed_at) is True

    def test_missing_file_returns_false(self, tmp_project: Path):
        """If a watched file doesn't exist, returns False (not stale)."""
        computed_at = time.time() - 10
        assert _check_mtime(tmp_project, ["nonexistent.txt"], computed_at) is False

    def test_directory_walk(self, tmp_project: Path):
        """Directory paths (ending with /) walk files for max mtime."""
        computed_at = time.time() - 10
        # src/ contains app.py which was just created — newer than computed_at
        assert _check_mtime(tmp_project, ["src/"], computed_at) is True

    def test_directory_walk_no_change(self, tmp_project: Path):
        """Directory walk returns False when files are older than computed_at."""
        time.sleep(0.05)  # ensure files are older
        computed_at = time.time() + 1  # computed "in the future"
        assert _check_mtime(tmp_project, ["src/"], computed_at) is False

    def test_multiple_paths_any_stale(self, tmp_project: Path):
        """Returns True if ANY path is stale, not just all."""
        computed_at = time.time() - 10
        # Dockerfile is newer, nonexistent.txt doesn't exist
        assert _check_mtime(
            tmp_project,
            ["nonexistent.txt", "Dockerfile"],
            computed_at,
        ) is True

    def test_git_head_detection(self, tmp_project: Path):
        """Specifically tests .git/HEAD mtime detection."""
        computed_at = time.time() - 10
        (tmp_project / ".git" / "HEAD").write_text("ref: refs/heads/feature\n")
        assert _check_mtime(
            tmp_project, [".git/HEAD"], computed_at
        ) is True


# ── Integration tests with QueryMediator.get() ──────────────────


class TestMtimePathsInGet:
    """Verify that get() uses mtime_paths for staleness detection."""

    def test_cached_value_returned_when_no_file_change(
        self, mediator_with_mtime: tuple[QueryMediator, list[int]]
    ):
        """When watched file hasn't changed, get() returns cached value."""
        m, call_count = mediator_with_mtime

        # First call — computes
        r1 = m.get("detect.docker")
        assert r1["data"]["value"] == 1
        assert call_count[0] == 1

        # Second call — should hit cache (TTL=3600, file unchanged)
        r2 = m.get("detect.docker")
        assert r2["data"]["value"] == 1
        assert call_count[0] == 1  # NOT recomputed

    def test_recomputes_when_file_changes(
        self, mediator_with_mtime: tuple[QueryMediator, list[int]]
    ):
        """When watched file is modified, get() recomputes despite TTL."""
        m, call_count = mediator_with_mtime

        # First call — computes
        r1 = m.get("detect.docker")
        assert r1["data"]["value"] == 1
        assert call_count[0] == 1

        # Touch the Dockerfile — make it newer than computed_at
        time.sleep(0.05)  # ensure mtime is measurably different
        (m.project_root / "Dockerfile").write_text("FROM python:3.13\n")

        # Second call — should recompute because Dockerfile changed
        r2 = m.get("detect.docker")
        assert r2["data"]["value"] == 2
        assert call_count[0] == 2  # DID recompute

    def test_mtime_check_with_explain(
        self, mediator_with_mtime: tuple[QueryMediator, list[int]]
    ):
        """The explain output mentions mtime_paths when they cause staleness."""
        m, call_count = mediator_with_mtime

        # Populate cache
        m.get("detect.docker")

        # Touch file
        time.sleep(0.05)
        (m.project_root / "Dockerfile").write_text("FROM python:3.13\n")

        # Get with explain
        r = m.get("detect.docker", explain=True)
        explain_str = r.get("meta", {}).get("explain", "")
        assert "mtime_paths" in explain_str, (
            f"Expected 'mtime_paths' in explain, got: {explain_str!r}"
        )

    def test_no_mtime_paths_no_check(self, tmp_project: Path):
        """Nodes without mtime_paths use normal TTL behavior only."""
        call_count = [0]

        def _resolver():
            call_count[0] += 1
            return {"value": call_count[0]}

        tree = DataTree()
        tree.register(TreeRegistration(
            path="devops.test",
            resolver=_resolver,
            ttl=3600,  # long TTL, NO mtime_paths
        ))
        m = QueryMediator(tree, tmp_project)

        # First call — computes
        m.get("devops.test")
        assert call_count[0] == 1

        # Touch Dockerfile (but node doesn't watch it)
        time.sleep(0.05)
        (tmp_project / "Dockerfile").write_text("FROM python:3.13\n")

        # Second call — should NOT recompute (no mtime_paths, TTL not expired)
        m.get("devops.test")
        assert call_count[0] == 1

    def test_directory_mtime_path(self, tmp_project: Path):
        """Nodes watching a directory recompute when files inside change."""
        call_count = [0]

        def _resolver():
            call_count[0] += 1
            return {"count": call_count[0]}

        tree = DataTree()
        tree.register(TreeRegistration(
            path="detect.quality",
            resolver=_resolver,
            ttl=3600,
            mtime_paths=["src/"],
        ))
        m = QueryMediator(tree, tmp_project)

        # First call
        m.get("detect.quality")
        assert call_count[0] == 1

        # Modify a file inside src/
        time.sleep(0.05)
        (tmp_project / "src" / "app.py").write_text("# updated\n")

        # Second call — should recompute
        m.get("detect.quality")
        assert call_count[0] == 2

    def test_ttl_none_with_mtime_paths(self, tmp_project: Path):
        """Nodes with ttl=None + mtime_paths use mtime for staleness."""
        call_count = [0]

        def _resolver():
            call_count[0] += 1
            return {"n": call_count[0]}

        tree = DataTree()
        tree.register(TreeRegistration(
            path="detect.git",
            resolver=_resolver,
            ttl=None,  # no TTL — mtime_paths is the only staleness signal
            mtime_paths=[".git/HEAD"],
        ))
        m = QueryMediator(tree, tmp_project)

        # First call
        m.get("detect.git")
        assert call_count[0] == 1

        # No change → cache hit
        m.get("detect.git")
        assert call_count[0] == 1

        # Change .git/HEAD → stale
        time.sleep(0.05)
        (tmp_project / ".git" / "HEAD").write_text("ref: refs/heads/dev\n")
        m.get("detect.git")
        assert call_count[0] == 2
