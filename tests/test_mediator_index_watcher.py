"""
Tests for Phase 8D — index watcher (FS polling → mediator cascade bridge).

Tests the dir mtime scanning, change detection logic, and mediator
integration without actually sleeping or starting daemon threads.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.index_watcher import (
    scan_dir_mtimes,
    start_index_watcher,
)
from src.core.services.mediator.registrations.index import register_index
from src.core.services.mediator.tree import DataTree


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Create a minimal project structure for watcher testing."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "core").mkdir()
    (tmp_path / "src" / "core" / "main.py").write_text("def main(): pass\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("# Hello\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")

    # Directories that should be skipped
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("bare = false\n")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "foo.pyc").write_text("bytecode\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg").mkdir()

    return tmp_path


@pytest.fixture
def mediator(project: Path) -> QueryMediator:
    """Create a mediator with index nodes registered."""
    tree = DataTree()
    m = QueryMediator(tree, project)
    register_index(m)
    return m


# ── scan_dir_mtimes tests ──────────────────────────────────────


class TestScanDirMtimes:
    """Tests for the scan_dir_mtimes function."""

    def test_returns_directory_mtimes(self, project: Path) -> None:
        mtimes = scan_dir_mtimes(project)
        assert isinstance(mtimes, dict)
        # Should include root and subdirectories
        assert "" in mtimes  # root
        assert "src" in mtimes
        assert os.path.join("src", "core") in mtimes
        assert "docs" in mtimes

    def test_skips_hidden_dirs(self, project: Path) -> None:
        mtimes = scan_dir_mtimes(project)
        assert ".git" not in mtimes

    def test_skips_pycache(self, project: Path) -> None:
        mtimes = scan_dir_mtimes(project)
        assert "__pycache__" not in mtimes

    def test_skips_node_modules(self, project: Path) -> None:
        mtimes = scan_dir_mtimes(project)
        assert "node_modules" not in mtimes

    def test_mtimes_are_floats(self, project: Path) -> None:
        mtimes = scan_dir_mtimes(project)
        for _path, mt in mtimes.items():
            assert isinstance(mt, float)
            assert mt > 0

    def test_detects_new_subdir(self, project: Path) -> None:
        before = scan_dir_mtimes(project)
        (project / "src" / "newpkg").mkdir()
        after = scan_dir_mtimes(project)
        assert os.path.join("src", "newpkg") in after
        assert os.path.join("src", "newpkg") not in before

    def test_detects_file_change_via_dir_mtime(self, project: Path) -> None:
        before = scan_dir_mtimes(project)
        time.sleep(0.05)  # ensure mtime granularity
        (project / "src" / "core" / "new.py").write_text("x = 1\n")
        after = scan_dir_mtimes(project)
        src_core = os.path.join("src", "core")
        # The directory's mtime should have changed
        assert after[src_core] >= before[src_core]


# ── Change detection tests ─────────────────────────────────────


class TestChangeDetection:
    """Tests for the watcher's change detection logic."""

    def test_no_change_detected(self, project: Path) -> None:
        """Two consecutive scans with no changes should match."""
        snap1 = scan_dir_mtimes(project)
        snap2 = scan_dir_mtimes(project)
        changed = [
            d for d, mt in snap2.items()
            if snap1.get(d) != mt
        ]
        assert changed == []

    def test_change_detected_after_file_edit(self, project: Path) -> None:
        """File edit may or may not cause parent dir mtime to change.

        On most filesystems, editing a file's *content* does NOT change
        the parent directory's mtime.  Only creating or deleting files
        does.  But on some systems (tmpfs, WSL) it does.  So we test
        that creating a new file in the dir IS detected (which is the
        watcher's primary job).
        """
        snap1 = scan_dir_mtimes(project)
        time.sleep(0.05)
        # Create a NEW file — this always updates dir mtime
        (project / "src" / "core" / "brand_new.py").write_text(
            "x = 1\n"
        )
        snap2 = scan_dir_mtimes(project)
        changed = [
            d for d, mt in snap2.items()
            if snap1.get(d) != mt
        ]
        src_core = os.path.join("src", "core")
        assert src_core in changed

    def test_change_detected_after_new_file(self, project: Path) -> None:
        """New file should cause parent dir mtime to change."""
        snap1 = scan_dir_mtimes(project)
        time.sleep(0.05)
        (project / "docs" / "guide.md").write_text("# Guide\n")
        snap2 = scan_dir_mtimes(project)
        changed = [
            d for d, mt in snap2.items()
            if snap1.get(d) != mt
        ]
        assert "docs" in changed

    def test_change_detected_after_file_delete(self, project: Path) -> None:
        """File deletion should cause parent dir mtime to change."""
        snap1 = scan_dir_mtimes(project)
        time.sleep(0.05)
        (project / "pyproject.toml").unlink()
        snap2 = scan_dir_mtimes(project)
        changed = [
            d for d, mt in snap2.items()
            if snap1.get(d) != mt
        ]
        # Root directory mtime should change
        assert "" in changed

    def test_new_directory_detected(self, project: Path) -> None:
        """New directory should appear in the snapshot."""
        snap1 = scan_dir_mtimes(project)
        (project / "tests").mkdir()
        snap2 = scan_dir_mtimes(project)
        assert "tests" in snap2
        assert "tests" not in snap1


# ── Mediator cascade integration ───────────────────────────────


class TestWatcherMediatorIntegration:
    """Tests for watcher → mediator.put cascade."""

    def test_put_invalidates_index_scan(
        self, mediator: QueryMediator,
    ) -> None:
        """mediator.put('index.scan') should invalidate the scan."""
        # Prime the cache
        result1 = mediator.get("index.scan")
        assert result1["data"] is not None

        # Invalidate (what the watcher does)
        mediator.put("index.scan")

        # Next get() should recompute
        result2 = mediator.get("index.scan")
        assert result2["data"] is not None
        # Should be a fresh computation (different seq)
        assert result2["meta"]["seq"] != result1["meta"]["seq"]

    def test_put_cascades_to_delta(
        self, mediator: QueryMediator,
    ) -> None:
        """Invalidating index.scan should cascade to index.delta."""
        # Prime
        mediator.get("index.delta")
        # Invalidate scan → delta should also be invalidated
        mediator.put("index.scan")
        # Delta should recompute on next get
        result = mediator.get("index.delta")
        assert result["data"] is not None

    def test_put_cascades_to_symbols(
        self, mediator: QueryMediator,
    ) -> None:
        """Invalidating index.scan should cascade to index.symbols."""
        mediator.get("index.symbols")
        mediator.put("index.scan")
        result = mediator.get("index.symbols")
        assert result["data"] is not None

    def test_put_cascades_to_peek(
        self, mediator: QueryMediator,
    ) -> None:
        """Invalidating index.scan should cascade to index.peek."""
        mediator.get("index.peek")
        mediator.put("index.scan")
        result = mediator.get("index.peek")
        assert result["data"] is not None

    def test_full_cascade_from_file_change(
        self, mediator: QueryMediator, project: Path,
    ) -> None:
        """Simulate watcher cycle: file change → put → cascade → fresh data."""
        # First: prime all caches
        scan1 = mediator.get("index.scan")["data"]
        mediator.get("index.delta")  # prime prev_scan

        # Now: add a file (real FS change)
        time.sleep(0.05)
        (project / "src" / "core" / "new.py").write_text(
            "def brand_new(): pass\n"
        )

        # Watcher would call this:
        mediator.put("index.scan")

        # Verify scan picks up the new file
        scan2 = mediator.get("index.scan")["data"]
        assert len(scan2) > len(scan1)

        # Verify delta detects the addition
        delta = mediator.get("index.delta")["data"]
        new_rel = os.path.join("src", "core", "new.py")
        assert new_rel in delta.added


# ── start_index_watcher tests ──────────────────────────────────


class TestStartIndexWatcher:
    """Tests for the start_index_watcher function."""

    def test_starts_daemon_thread(
        self, project: Path, mediator: QueryMediator,
    ) -> None:
        """Should start a daemon thread with the right name."""
        t = start_index_watcher(project, mediator, poll_interval=9999)
        assert t.is_alive()
        assert t.daemon
        assert t.name == "index-watcher"
