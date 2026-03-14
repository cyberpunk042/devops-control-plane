"""Tests for ConsolidatedWalker and TreeWalkCollector.

Tests cover:
    - Single collector full-tree walk
    - Multiple collectors in one walk (the core value prop)
    - Scoped collectors (only specific directories)
    - Mixed full-tree + scoped collectors
    - FileListCollector (extension-based filtering)
    - FileNameCollector (exact filename matching)
    - Skip directory pruning
    - Empty directory handling
    - Max file cap
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.core.services.mediator.tree_walker import (
    BaseCollector,
    ConsolidatedWalker,
    FileListCollector,
    FileNameCollector,
    SKIP_DIRS,
)


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Create a realistic project structure for testing."""
    # Source files
    (tmp_path / "src" / "core").mkdir(parents=True)
    (tmp_path / "src" / "core" / "main.py").write_text("# main")
    (tmp_path / "src" / "core" / "utils.py").write_text("# utils")
    (tmp_path / "src" / "core" / "style.css").write_text("/* css */")

    (tmp_path / "src" / "web").mkdir(parents=True)
    (tmp_path / "src" / "web" / "server.py").write_text("# server")
    (tmp_path / "src" / "web" / "routes.js").write_text("// routes")

    # Test files
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("# test")
    (tmp_path / "tests" / "conftest.py").write_text("# conftest")

    # Config files
    (tmp_path / "Dockerfile").write_text("FROM python")
    (tmp_path / "docker-compose.yml").write_text("version: '3'")
    (tmp_path / "Chart.yaml").write_text("name: app")
    (tmp_path / "README.md").write_text("# Readme")

    # Deploy dir
    (tmp_path / "deploy" / "k8s").mkdir(parents=True)
    (tmp_path / "deploy" / "k8s" / "pod.yaml").write_text("kind: Pod")
    (tmp_path / "deploy" / "k8s" / "svc.yaml").write_text("kind: Service")
    (tmp_path / "deploy" / "helm").mkdir(parents=True)
    (tmp_path / "deploy" / "helm" / "Chart.yaml").write_text("name: helm")

    # Directories that should be skipped
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("git stuff")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.json").write_text("{}")

    return tmp_path


# ── FileListCollector ──────────────────────────────────────────────


class TestFileListCollector:
    """Tests for extension-based file collection."""

    def test_collect_python_files(self, project: Path) -> None:
        """Collects all .py files from project tree."""
        collector = FileListCollector("python", frozenset({".py"}))
        walker = ConsolidatedWalker(project)
        stats = walker.walk([collector])

        assert stats["collectors"] == 1
        assert stats["dirs_walked"] > 0
        # Should find: main.py, utils.py, server.py, test_main.py, conftest.py
        py_names = sorted(os.path.basename(f) for f in collector.files)
        assert "main.py" in py_names
        assert "utils.py" in py_names
        assert "server.py" in py_names
        assert "test_main.py" in py_names
        assert "conftest.py" in py_names
        assert len(collector.files) == 5

    def test_collect_yaml_files(self, project: Path) -> None:
        """Collects all .yaml and .yml files."""
        collector = FileListCollector(
            "yaml", frozenset({".yaml", ".yml"}),
        )
        walker = ConsolidatedWalker(project)
        walker.walk([collector])

        names = sorted(os.path.basename(f) for f in collector.files)
        assert "Chart.yaml" in names
        assert "docker-compose.yml" in names
        assert "pod.yaml" in names
        assert "svc.yaml" in names

    def test_skips_git_and_node_modules(self, project: Path) -> None:
        """Files in .git and node_modules are skipped."""
        collector = FileListCollector("all", frozenset({".py", ".json"}))
        walker = ConsolidatedWalker(project)
        walker.walk([collector])

        for f in collector.files:
            assert ".git" not in f
            assert "node_modules" not in f

    def test_max_files_cap(self, project: Path) -> None:
        """Respects max_files limit."""
        collector = FileListCollector(
            "capped", frozenset({".py"}), max_files=2,
        )
        walker = ConsolidatedWalker(project)
        walker.walk([collector])

        assert len(collector.files) == 2

    def test_scoped_collector(self, project: Path) -> None:
        """Scoped collector only sees files in specified directories."""
        collector = FileListCollector(
            "tests-only",
            frozenset({".py"}),
            wants_full_tree=False,
            scope_dirs=["tests"],
        )
        walker = ConsolidatedWalker(project)
        walker.walk([collector])

        for f in collector.files:
            assert f.startswith("tests")
        assert len(collector.files) == 2  # test_main.py, conftest.py


# ── FileNameCollector ──────────────────────────────────────────────


class TestFileNameCollector:
    """Tests for exact filename matching."""

    def test_collect_dockerfiles(self, project: Path) -> None:
        """Collects files named 'Dockerfile'."""
        collector = FileNameCollector(
            "docker", frozenset({"Dockerfile"}),
        )
        walker = ConsolidatedWalker(project)
        walker.walk([collector])

        assert len(collector.files) == 1
        assert os.path.basename(collector.files[0]) == "Dockerfile"

    def test_collect_chart_yaml(self, project: Path) -> None:
        """Collects all Chart.yaml files."""
        collector = FileNameCollector(
            "helm", frozenset({"Chart.yaml"}),
        )
        walker = ConsolidatedWalker(project)
        walker.walk([collector])

        assert len(collector.files) == 2  # root + deploy/helm
        names = [os.path.basename(f) for f in collector.files]
        assert all(n == "Chart.yaml" for n in names)


# ── ConsolidatedWalker ─────────────────────────────────────────────


class TestConsolidatedWalker:
    """Tests for the single-walk-multiple-consumer pattern."""

    def test_multiple_collectors_one_walk(self, project: Path) -> None:
        """Multiple collectors fed from a single os.walk pass."""
        py_collector = FileListCollector("python", frozenset({".py"}))
        js_collector = FileListCollector("js", frozenset({".js"}))
        docker_collector = FileNameCollector(
            "docker", frozenset({"Dockerfile"}),
        )

        walker = ConsolidatedWalker(project)
        stats = walker.walk([py_collector, js_collector, docker_collector])

        assert stats["collectors"] == 3
        assert len(py_collector.files) == 5
        assert len(js_collector.files) == 1
        assert len(docker_collector.files) == 1

    def test_mixed_scoped_and_full(self, project: Path) -> None:
        """Full-tree collector + scoped collector in one walk."""
        full = FileListCollector("all-py", frozenset({".py"}))
        scoped = FileListCollector(
            "deploy-yaml",
            frozenset({".yaml", ".yml"}),
            wants_full_tree=False,
            scope_dirs=["deploy"],
        )

        walker = ConsolidatedWalker(project)
        walker.walk([full, scoped])

        # Full collector gets all py files
        assert len(full.files) == 5

        # Scoped collector only gets yaml files under deploy/
        for f in scoped.files:
            assert f.startswith("deploy")
        assert len(scoped.files) >= 2  # pod.yaml, svc.yaml, Chart.yaml

    def test_empty_collectors_list(self, project: Path) -> None:
        """Walking with no collectors returns zero stats."""
        walker = ConsolidatedWalker(project)
        stats = walker.walk([])
        assert stats["dirs_walked"] == 0
        assert stats["files_seen"] == 0

    def test_custom_skip_dirs(self, project: Path) -> None:
        """Custom skip_dirs override the defaults."""
        # Create a dir that wouldn't normally be skipped
        (project / "custom_skip").mkdir()
        (project / "custom_skip" / "data.py").write_text("# data")

        collector = FileListCollector("py", frozenset({".py"}))
        walker = ConsolidatedWalker(
            project,
            skip_dirs=frozenset({"custom_skip"}),
        )
        walker.walk([collector])

        # custom_skip/data.py should be excluded
        for f in collector.files:
            assert "custom_skip" not in f

    def test_stats_accuracy(self, project: Path) -> None:
        """Walk stats reflect actual traversal counts."""
        collector = FileListCollector("all", frozenset({".py", ".js", ".yaml", ".yml", ".css", ".md"}))
        walker = ConsolidatedWalker(project)
        stats = walker.walk([collector])

        assert stats["dirs_walked"] > 0
        assert stats["files_seen"] > 0
        # files_seen >= collected files (some don't match extensions)
        assert stats["files_seen"] >= len(collector.files)

    def test_scoped_only_collectors(self, project: Path) -> None:
        """When all collectors are scoped, only scoped dirs are walked."""
        c1 = FileListCollector(
            "tests", frozenset({".py"}),
            wants_full_tree=False, scope_dirs=["tests"],
        )
        c2 = FileListCollector(
            "deploy", frozenset({".yaml", ".yml"}),
            wants_full_tree=False, scope_dirs=["deploy"],
        )

        walker = ConsolidatedWalker(project)
        stats = walker.walk([c1, c2])

        # Only tests/ and deploy/ dirs should be walked
        # (not src/, the root, etc.)
        assert len(c1.files) == 2  # test_main.py, conftest.py
        assert len(c2.files) >= 2  # pod.yaml, svc.yaml, ...

        # Verify no src/ files leaked in
        for f in c1.files:
            assert f.startswith("tests")
        for f in c2.files:
            assert f.startswith("deploy")


# ── BaseCollector subclassing ──────────────────────────────────────


class TestBaseCollector:
    """Test the convenience base class."""

    def test_subclass_override(self, project: Path) -> None:
        """Custom collector subclass accumulates results."""

        class CountCollector(BaseCollector):
            name = "counter"
            wants_full_tree = True
            scope_dirs = None

            def __init__(self):
                self.dir_count = 0
                self.file_count = 0

            def on_dir(self, rel_dir, dirnames, filenames):
                self.dir_count += 1
                self.file_count += len(filenames)

        collector = CountCollector()
        walker = ConsolidatedWalker(project)
        walker.walk([collector])

        assert collector.dir_count > 0
        assert collector.file_count > 0

    def test_base_raises_not_implemented(self) -> None:
        """BaseCollector.on_dir raises if not overridden."""
        base = BaseCollector(name="test")
        with pytest.raises(NotImplementedError):
            base.on_dir(".", [], [])
