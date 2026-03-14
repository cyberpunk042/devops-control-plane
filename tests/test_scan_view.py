"""Tests for ScanView — materialized view over scan data.

Tests cover:
    - files_with_ext (extension lookup)
    - files_named (exact filename lookup)
    - files_in_dir (directory scoping, recursive & non-recursive)
    - dir_exists (directory existence check)
    - has_file (file existence check)
    - file_entry (metadata retrieval)
    - file_count (total count)
    - extensions (distinct extension listing)
    - get_scan_view (safe accessor with fallback to None)
"""

from __future__ import annotations

import os

import pytest

from src.core.services.mediator.registrations.index import (
    FileEntry,
    ScanView,
)


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def scan_data() -> dict[str, FileEntry]:
    """Simulated scan output."""
    return {
        "src/core/main.py": FileEntry(mtime=1000.0, size=500, ext="py"),
        "src/core/utils.py": FileEntry(mtime=1001.0, size=300, ext="py"),
        "src/core/style.css": FileEntry(mtime=1002.0, size=200, ext="css"),
        "src/web/server.py": FileEntry(mtime=1003.0, size=800, ext="py"),
        "src/web/routes.js": FileEntry(mtime=1004.0, size=400, ext="js"),
        "tests/test_main.py": FileEntry(mtime=1005.0, size=600, ext="py"),
        "tests/conftest.py": FileEntry(mtime=1006.0, size=100, ext="py"),
        "Dockerfile": FileEntry(mtime=1007.0, size=50, ext=""),
        "docker-compose.yml": FileEntry(mtime=1008.0, size=150, ext="yml"),
        "README.md": FileEntry(mtime=1009.0, size=250, ext="md"),
        "deploy/k8s/pod.yaml": FileEntry(mtime=1010.0, size=120, ext="yaml"),
        "deploy/k8s/svc.yaml": FileEntry(mtime=1011.0, size=130, ext="yaml"),
        "deploy/helm/Chart.yaml": FileEntry(mtime=1012.0, size=140, ext="yaml"),
    }


@pytest.fixture
def view(scan_data: dict[str, FileEntry]) -> ScanView:
    """Pre-built ScanView for testing."""
    return ScanView(scan_data)


# ── files_with_ext ─────────────────────────────────────────────────


class TestFilesWithExt:
    """Test extension-based file lookup."""

    def test_python_files(self, view: ScanView) -> None:
        """All .py files are found."""
        py = view.files_with_ext("py")
        assert len(py) == 5
        assert "src/core/main.py" in py
        assert "tests/test_main.py" in py

    def test_yaml_files(self, view: ScanView) -> None:
        """All .yaml files are found."""
        yaml = view.files_with_ext("yaml")
        assert len(yaml) == 3

    def test_missing_ext(self, view: ScanView) -> None:
        """Non-existent extension returns empty list."""
        assert view.files_with_ext("rs") == []

    def test_single_ext(self, view: ScanView) -> None:
        """Extension with single match works."""
        css = view.files_with_ext("css")
        assert len(css) == 1
        assert css[0] == "src/core/style.css"


# ── files_named ────────────────────────────────────────────────────


class TestFilesNamed:
    """Test exact filename lookup."""

    def test_dockerfile(self, view: ScanView) -> None:
        """Finds files named 'Dockerfile'."""
        results = view.files_named("Dockerfile")
        assert "Dockerfile" in results

    def test_chart_yaml(self, view: ScanView) -> None:
        """Finds all 'Chart.yaml' files."""
        results = view.files_named("Chart.yaml")
        assert len(results) == 1
        assert "deploy/helm/Chart.yaml" in results

    def test_missing_name(self, view: ScanView) -> None:
        """Non-existent filename returns empty list."""
        assert view.files_named("nonexistent.txt") == []


# ── files_in_dir ───────────────────────────────────────────────────


class TestFilesInDir:
    """Test directory-scoped file listing."""

    def test_recursive(self, view: ScanView) -> None:
        """Recursive listing includes subdirectories."""
        src_files = view.files_in_dir("src")
        assert len(src_files) == 5
        assert "src/core/main.py" in src_files
        assert "src/web/routes.js" in src_files

    def test_non_recursive(self, view: ScanView) -> None:
        """Non-recursive listing only returns direct children."""
        core_files = view.files_in_dir("src/core", recursive=False)
        assert len(core_files) == 3
        for f in core_files:
            assert f.startswith("src/core/")
            # Should not have deeper nesting
            rel = f[len("src/core/"):]
            assert "/" not in rel

    def test_deploy_subdir(self, view: ScanView) -> None:
        """Files in nested deploy directory."""
        k8s = view.files_in_dir("deploy/k8s")
        assert len(k8s) == 2

    def test_missing_dir(self, view: ScanView) -> None:
        """Non-existent directory returns empty list."""
        assert view.files_in_dir("nonexistent") == []


# ── dir_exists ─────────────────────────────────────────────────────


class TestDirExists:
    """Test directory existence checks."""

    def test_existing_dir(self, view: ScanView) -> None:
        """Existing directory returns True."""
        assert view.dir_exists("src") is True
        assert view.dir_exists("src/core") is True
        assert view.dir_exists("deploy/k8s") is True

    def test_missing_dir(self, view: ScanView) -> None:
        """Non-existent directory returns False."""
        assert view.dir_exists("nonexistent") is False
        assert view.dir_exists("src/missing") is False


# ── has_file ───────────────────────────────────────────────────────


class TestHasFile:
    """Test file existence checks."""

    def test_existing_file(self, view: ScanView) -> None:
        """Existing file returns True."""
        assert view.has_file("src/core/main.py") is True
        assert view.has_file("Dockerfile") is True

    def test_missing_file(self, view: ScanView) -> None:
        """Non-existent file returns False."""
        assert view.has_file("nonexistent.py") is False


# ── file_entry ─────────────────────────────────────────────────────


class TestFileEntry:
    """Test metadata retrieval."""

    def test_existing_entry(self, view: ScanView) -> None:
        """Existing file returns its FileEntry."""
        entry = view.file_entry("src/core/main.py")
        assert entry is not None
        assert entry.size == 500
        assert entry.ext == "py"

    def test_missing_entry(self, view: ScanView) -> None:
        """Non-existent file returns None."""
        assert view.file_entry("missing.py") is None


# ── file_count ─────────────────────────────────────────────────────


class TestFileCount:
    """Test total file counting."""

    def test_total_count(self, view: ScanView) -> None:
        """Total count matches scan data size."""
        assert view.file_count == 13


# ── extensions ─────────────────────────────────────────────────────


class TestExtensions:
    """Test distinct extension listing."""

    def test_all_extensions(self, view: ScanView) -> None:
        """Returns all unique extensions in scan."""
        exts = view.extensions
        assert "py" in exts
        assert "js" in exts
        assert "yaml" in exts
        assert "yml" in exts
        assert "md" in exts
        assert "css" in exts


# ── get_scan_view ──────────────────────────────────────────────────


class TestGetScanView:
    """Test the safe accessor function."""

    def test_returns_none_without_mediator(self) -> None:
        """get_scan_view returns None when mediator isn't initialized."""
        from src.core.services.mediator.registrations.index import get_scan_view
        result = get_scan_view()
        assert result is None


# ── repr ───────────────────────────────────────────────────────────


class TestRepr:
    """Test string representation."""

    def test_repr(self, view: ScanView) -> None:
        """ScanView has reasonable repr."""
        r = repr(view)
        assert "ScanView" in r
        assert "13" in r  # file count
