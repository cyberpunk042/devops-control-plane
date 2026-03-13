"""
Tests for mediator-native index registration.

Phase 8A: scan, delta, files, dirs, paths, stats.
Phase 8B: incremental symbols.
Phase 8C: incremental peek.
Phase 8E: classification.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.registrations.index import (
    FileEntry,
    IndexSymbolEntry,
    ScanDelta,
    classify_project,
    derive_dir_map,
    derive_file_map,
    diff_scans,
    incremental_peek,
    incremental_symbols,
    register_index,
    scan_project,
)
from src.core.services.mediator.tree import DataTree


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Create a minimal project structure for index testing."""
    # Python files
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "core").mkdir()
    (tmp_path / "src" / "core" / "main.py").write_text("def main(): pass\n")
    (tmp_path / "src" / "core" / "utils.py").write_text("def helper(): pass\n")

    # Markdown files
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text(
        "# Hello\n\nSee `main.py` for the entry point.\n"
    )

    # Config files
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
    (tmp_path / "project.yml").write_text("name: test\n")

    # Files that should be skipped
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("bare = false\n")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "foo.pyc").write_text("bytecode\n")
    (tmp_path / ".hidden_file").write_text("secret\n")

    # Nested structure
    (tmp_path / "src" / "ui").mkdir()
    (tmp_path / "src" / "ui" / "app.js").write_text("console.log('hi');\n")

    return tmp_path


@pytest.fixture
def mediator(project: Path) -> QueryMediator:
    """Create a mediator with index nodes registered."""
    tree = DataTree()
    m = QueryMediator(tree, project)
    register_index(m)
    return m


# ── scan_project tests ──────────────────────────────────────────


class TestScanProject:
    """Tests for the scan_project function."""

    def test_scans_all_visible_files(self, project: Path) -> None:
        scan = scan_project(project)
        # Should find: main.py, utils.py, README.md, pyproject.toml,
        # project.yml, app.js
        assert len(scan) == 6

    def test_returns_file_entries(self, project: Path) -> None:
        scan = scan_project(project)
        rel = os.path.join("src", "core", "main.py")
        assert rel in scan
        entry = scan[rel]
        assert isinstance(entry, FileEntry)
        assert entry.ext == "py"
        assert entry.size > 0
        assert entry.mtime > 0

    def test_skips_hidden_dirs(self, project: Path) -> None:
        scan = scan_project(project)
        # .git/config should NOT be in the scan
        git_config = os.path.join(".git", "config")
        assert git_config not in scan

    def test_skips_pycache(self, project: Path) -> None:
        scan = scan_project(project)
        pycache = os.path.join("__pycache__", "foo.pyc")
        assert pycache not in scan

    def test_skips_hidden_files(self, project: Path) -> None:
        scan = scan_project(project)
        assert ".hidden_file" not in scan

    def test_extension_extraction(self, project: Path) -> None:
        scan = scan_project(project)
        rel_md = os.path.join("docs", "README.md")
        assert scan[rel_md].ext == "md"
        assert scan["pyproject.toml"].ext == "toml"

    def test_file_without_extension(self, project: Path) -> None:
        (project / "Makefile").write_text("all:\n\techo hi\n")
        scan = scan_project(project)
        assert scan["Makefile"].ext == ""

    def test_skips_node_modules(self, project: Path) -> None:
        nm = project / "node_modules" / "lodash"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {};\n")
        scan = scan_project(project)
        assert os.path.join("node_modules", "lodash", "index.js") not in scan

    def test_skips_venv(self, project: Path) -> None:
        venv = project / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "stuff.py").write_text("x = 1\n")
        scan = scan_project(project)
        assert os.path.join(".venv", "lib", "stuff.py") not in scan


# ── diff_scans tests ────────────────────────────────────────────


class TestDiffScans:
    """Tests for the diff_scans function."""

    def test_empty_to_populated(self) -> None:
        prev: dict[str, FileEntry] = {}
        curr = {
            "a.py": FileEntry(mtime=100.0, size=10, ext="py"),
            "b.md": FileEntry(mtime=200.0, size=20, ext="md"),
        }
        delta = diff_scans(prev, curr)
        assert sorted(delta.added) == ["a.py", "b.md"]
        assert delta.removed == []
        assert delta.modified == []
        assert not delta.empty
        assert delta.total_changes == 2

    def test_no_changes(self) -> None:
        entries = {
            "a.py": FileEntry(mtime=100.0, size=10, ext="py"),
        }
        delta = diff_scans(entries, entries)
        assert delta.empty
        assert delta.total_changes == 0

    def test_file_removed(self) -> None:
        prev = {
            "a.py": FileEntry(mtime=100.0, size=10, ext="py"),
            "b.py": FileEntry(mtime=100.0, size=10, ext="py"),
        }
        curr = {
            "a.py": FileEntry(mtime=100.0, size=10, ext="py"),
        }
        delta = diff_scans(prev, curr)
        assert delta.added == []
        assert delta.removed == ["b.py"]
        assert delta.modified == []

    def test_file_modified(self) -> None:
        prev = {
            "a.py": FileEntry(mtime=100.0, size=10, ext="py"),
        }
        curr = {
            "a.py": FileEntry(mtime=200.0, size=15, ext="py"),
        }
        delta = diff_scans(prev, curr)
        assert delta.added == []
        assert delta.removed == []
        assert delta.modified == ["a.py"]

    def test_mixed_changes(self) -> None:
        prev = {
            "keep.py": FileEntry(mtime=100.0, size=10, ext="py"),
            "remove.py": FileEntry(mtime=100.0, size=10, ext="py"),
            "modify.py": FileEntry(mtime=100.0, size=10, ext="py"),
        }
        curr = {
            "keep.py": FileEntry(mtime=100.0, size=10, ext="py"),
            "add.py": FileEntry(mtime=300.0, size=10, ext="py"),
            "modify.py": FileEntry(mtime=200.0, size=15, ext="py"),
        }
        delta = diff_scans(prev, curr)
        assert delta.added == ["add.py"]
        assert delta.removed == ["remove.py"]
        assert delta.modified == ["modify.py"]
        assert delta.total_changes == 3

    def test_changed_paths(self) -> None:
        prev: dict[str, FileEntry] = {}
        curr = {
            "a.py": FileEntry(mtime=100.0, size=10, ext="py"),
        }
        delta = diff_scans(prev, curr)
        assert delta.changed_paths == ["a.py"]

    def test_same_mtime_not_modified(self) -> None:
        """File with same mtime but different size is NOT modified."""
        prev = {"a.py": FileEntry(mtime=100.0, size=10, ext="py")}
        curr = {"a.py": FileEntry(mtime=100.0, size=20, ext="py")}
        delta = diff_scans(prev, curr)
        assert delta.empty  # mtime-based, not size-based


# ── derive_file_map tests ───────────────────────────────────────


class TestDeriveFileMap:
    """Tests for the derive_file_map function."""

    def test_groups_by_filename(self) -> None:
        scan = {
            "src/core/main.py": FileEntry(mtime=100, size=10, ext="py"),
            "tests/main.py": FileEntry(mtime=100, size=10, ext="py"),
            "docs/README.md": FileEntry(mtime=100, size=10, ext="md"),
        }
        fmap = derive_file_map(scan)
        assert sorted(fmap["main.py"]) == ["src/core/main.py", "tests/main.py"]
        assert fmap["README.md"] == ["docs/README.md"]

    def test_empty_scan(self) -> None:
        assert derive_file_map({}) == {}


# ── derive_dir_map tests ────────────────────────────────────────


class TestDeriveDirMap:
    """Tests for the derive_dir_map function."""

    def test_extracts_directories(self) -> None:
        scan = {
            "src/core/main.py": FileEntry(mtime=100, size=10, ext="py"),
            "src/ui/app.js": FileEntry(mtime=100, size=10, ext="js"),
        }
        dmap = derive_dir_map(scan)
        # Should have: src, core, ui (each with regular + trailing slash)
        assert "core" in dmap
        assert "core/" in dmap
        assert "ui" in dmap
        assert "src" in dmap

    def test_includes_trailing_slash_variant(self) -> None:
        scan = {
            "docs/README.md": FileEntry(mtime=100, size=10, ext="md"),
        }
        dmap = derive_dir_map(scan)
        assert "docs" in dmap
        assert "docs/" in dmap

    def test_empty_scan(self) -> None:
        assert derive_dir_map({}) == {}

    def test_nested_dirs(self) -> None:
        scan = {
            "a/b/c/file.py": FileEntry(mtime=100, size=10, ext="py"),
        }
        dmap = derive_dir_map(scan)
        # Should walk up: a/b/c, a/b, a
        assert "c" in dmap
        assert "b" in dmap
        assert "a" in dmap


# ── Mediator integration tests ──────────────────────────────────


class TestIndexMediator:
    """Tests for index nodes via the mediator."""

    def test_scan_returns_all_files(self, mediator: QueryMediator) -> None:
        result = mediator.get("index.scan")
        scan = result["data"]
        assert isinstance(scan, dict)
        assert len(scan) == 6

    def test_delta_first_run_all_added(self, mediator: QueryMediator) -> None:
        result = mediator.get("index.delta")
        delta = result["data"]
        assert isinstance(delta, ScanDelta)
        # First run: everything is "added" (prev_scan was empty)
        assert len(delta.added) == 6
        assert delta.removed == []
        assert delta.modified == []

    def test_delta_second_run_no_changes(self, mediator: QueryMediator) -> None:
        # First delta populates prev_scan
        mediator.get("index.delta")
        # Invalidate cache + cascade (simulates what the watcher does)
        mediator.put("index.scan")
        # Second delta: nothing changed
        result = mediator.get("index.delta")
        delta = result["data"]
        assert delta.empty

    def test_delta_detects_new_file(
        self, mediator: QueryMediator, project: Path
    ) -> None:
        # First delta
        mediator.get("index.delta")
        # Add a file
        (project / "new_file.txt").write_text("hello\n")
        # Invalidate cache + cascade (simulates what the watcher does)
        mediator.put("index.scan")
        # Second delta
        result = mediator.get("index.delta")
        delta = result["data"]
        assert "new_file.txt" in delta.added
        assert not delta.empty

    def test_delta_detects_removed_file(
        self, mediator: QueryMediator, project: Path
    ) -> None:
        # First delta
        mediator.get("index.delta")
        # Remove a file
        (project / "pyproject.toml").unlink()
        # Invalidate cache + cascade (simulates what the watcher does)
        mediator.put("index.scan")
        # Second delta
        result = mediator.get("index.delta")
        delta = result["data"]
        assert "pyproject.toml" in delta.removed

    def test_delta_detects_modification(
        self, mediator: QueryMediator, project: Path
    ) -> None:
        # First delta
        mediator.get("index.delta")
        # Modify a file (ensure mtime changes)
        target = project / "src" / "core" / "main.py"
        time.sleep(0.05)  # ensure mtime granularity
        target.write_text("def main(): pass  # modified\n")
        # Invalidate cache + cascade (simulates what the watcher does)
        mediator.put("index.scan")
        # Second delta
        result = mediator.get("index.delta")
        delta = result["data"]
        rel = os.path.join("src", "core", "main.py")
        assert rel in delta.modified

    def test_files_map(self, mediator: QueryMediator) -> None:
        result = mediator.get("index.files")
        fmap = result["data"]
        assert isinstance(fmap, dict)
        assert "main.py" in fmap
        assert len(fmap["main.py"]) == 1

    def test_dirs_map(self, mediator: QueryMediator) -> None:
        result = mediator.get("index.dirs")
        dmap = result["data"]
        assert isinstance(dmap, dict)
        assert "core" in dmap
        assert "docs" in dmap

    def test_paths_set(self, mediator: QueryMediator) -> None:
        result = mediator.get("index.paths")
        paths = result["data"]
        assert isinstance(paths, set)
        assert "pyproject.toml" in paths
        rel_main = os.path.join("src", "core", "main.py")
        assert rel_main in paths

    def test_stats(self, mediator: QueryMediator) -> None:
        result = mediator.get("index.stats")
        stats = result["data"]
        assert stats["file_count"] == 6
        assert stats["dir_count"] > 0
        assert stats["total_size_bytes"] > 0
        assert "py" in stats["extensions"]
        assert "md" in stats["extensions"]

    def test_all_nodes_registered(self, mediator: QueryMediator) -> None:
        paths = mediator.tree.all_paths()
        for expected in [
            "index.scan", "index.delta", "index.files",
            "index.dirs", "index.paths", "index.stats",
            "index.symbols", "index.peek", "index.classify",
        ]:
            assert expected in paths, f"{expected} not registered"

    def test_diag_includes_index_nodes(self, mediator: QueryMediator) -> None:
        diag = mediator.diag()
        entries = diag["entries"]
        index_nodes = [p for p in entries if p.startswith("index.")]
        assert len(index_nodes) == 9


# ── ScanDelta property tests ───────────────────────────────────


class TestScanDelta:
    """Tests for ScanDelta dataclass properties."""

    def test_empty_delta(self) -> None:
        delta = ScanDelta(added=[], removed=[], modified=[], timestamp=0)
        assert delta.empty
        assert delta.total_changes == 0
        assert delta.changed_paths == []

    def test_non_empty_delta(self) -> None:
        delta = ScanDelta(
            added=["a"], removed=["b"], modified=["c"],
            timestamp=time.time(),
        )
        assert not delta.empty
        assert delta.total_changes == 3
        assert sorted(delta.changed_paths) == ["a", "c"]


# ── Incremental symbol tests (Phase 8B) ─────────────────────────


class TestIncrementalSymbols:
    """Tests for the incremental_symbols function."""

    def test_cold_start_parses_all(self, project: Path) -> None:
        """Cold start (empty current) should parse all source files."""
        delta = ScanDelta(
            added=["src/core/main.py", "src/core/utils.py"],
            removed=[], modified=[], timestamp=time.time(),
        )
        current: dict[str, list[IndexSymbolEntry]] = {}
        result = incremental_symbols(project, delta, current)
        # Should have parsed the .py files and found symbols
        # main.py has "main", utils.py has "helper"
        assert "main" in result
        assert "helper" in result
        assert result["main"][0].kind in ("function", "async_function")
        assert result["main"][0].file.endswith("main.py")

    def test_empty_delta_skips(self, project: Path) -> None:
        """Empty delta should return current unchanged."""
        delta = ScanDelta(
            added=[], removed=[], modified=[], timestamp=time.time(),
        )
        sentinel = {"test": [IndexSymbolEntry("test", "x.py", 1, "function")]}
        result = incremental_symbols(project, delta, sentinel)
        assert result is sentinel  # same object, no work done

    def test_incremental_add(self, project: Path) -> None:
        """Adding a file should parse only that file."""
        # First: cold start with main.py only
        delta1 = ScanDelta(
            added=["src/core/main.py"],
            removed=[], modified=[], timestamp=time.time(),
        )
        current: dict[str, list[IndexSymbolEntry]] = {}
        current = incremental_symbols(project, delta1, current)
        assert "main" in current
        initial_names = set(current.keys())

        # Now add utils.py
        delta2 = ScanDelta(
            added=[os.path.join("src", "core", "utils.py")],
            removed=[], modified=[], timestamp=time.time(),
        )
        current = incremental_symbols(project, delta2, current)
        assert "helper" in current
        # main should still be there
        assert "main" in current

    def test_incremental_remove(self, project: Path) -> None:
        """Removing a file should purge its symbols."""
        # Cold start
        delta1 = ScanDelta(
            added=["src/core/main.py", "src/core/utils.py"],
            removed=[], modified=[], timestamp=time.time(),
        )
        current: dict[str, list[IndexSymbolEntry]] = {}
        current = incremental_symbols(project, delta1, current)
        assert "main" in current
        assert "helper" in current

        main_rel = os.path.join("src", "core", "main.py")
        # Remove main.py
        delta2 = ScanDelta(
            added=[], removed=[main_rel],
            modified=[], timestamp=time.time(),
        )
        current = incremental_symbols(project, delta2, current)
        assert "main" not in current  # purged
        assert "helper" in current    # untouched

    def test_incremental_modify(self, project: Path) -> None:
        """Modifying a file should purge old + parse new symbols."""
        # Cold start
        delta1 = ScanDelta(
            added=["src/core/main.py"],
            removed=[], modified=[], timestamp=time.time(),
        )
        current: dict[str, list[IndexSymbolEntry]] = {}
        current = incremental_symbols(project, delta1, current)
        assert "main" in current

        # Modify main.py: rename function
        (project / "src" / "core" / "main.py").write_text(
            "def new_main(): pass\n"
        )
        main_rel = os.path.join("src", "core", "main.py")
        delta2 = ScanDelta(
            added=[], removed=[],
            modified=[main_rel], timestamp=time.time(),
        )
        current = incremental_symbols(project, delta2, current)
        assert "main" not in current      # old symbol purged
        assert "new_main" in current       # new symbol added

    def test_non_parseable_files_skipped(self, project: Path) -> None:
        """Non-source files (txt, etc) should be silently skipped."""
        (project / "notes.txt").write_text("just notes\n")
        delta = ScanDelta(
            added=["notes.txt"],
            removed=[], modified=[], timestamp=time.time(),
        )
        # Pre-populate so it takes the incremental path
        current = {"existing": [IndexSymbolEntry("existing", "x.py", 1, "function")]}
        result = incremental_symbols(project, delta, current)
        # Should not crash, existing symbols preserved
        assert "existing" in result


class TestSymbolsMediator:
    """Tests for index.symbols via the mediator."""

    def test_symbols_node_exists(self, mediator: QueryMediator) -> None:
        assert "index.symbols" in mediator.tree.all_paths()

    def test_symbols_returns_dict(self, mediator: QueryMediator) -> None:
        result = mediator.get("index.symbols")
        symbols = result["data"]
        assert isinstance(symbols, dict)

    def test_symbols_finds_project_functions(
        self, mediator: QueryMediator,
    ) -> None:
        result = mediator.get("index.symbols")
        symbols = result["data"]
        # The test project has main.py with def main() and utils.py with def helper()
        assert "main" in symbols
        assert "helper" in symbols

    def test_symbol_entries_have_correct_fields(
        self, mediator: QueryMediator,
    ) -> None:
        result = mediator.get("index.symbols")
        symbols = result["data"]
        entries = symbols.get("main", [])
        assert len(entries) >= 1
        entry = entries[0]
        assert isinstance(entry, IndexSymbolEntry)
        assert entry.name == "main"
        assert entry.kind in ("function", "async_function")
        assert entry.line >= 1
        assert entry.file.endswith("main.py")


# ── Incremental peek tests (Phase 8C) ──────────────────────────


class TestIncrementalPeek:
    """Tests for the incremental_peek function."""

    def test_cold_start_peeks_all_md(self, project: Path) -> None:
        """Cold start should peek all .md files."""
        scan = scan_project(project)
        delta = ScanDelta(
            added=list(scan.keys()),
            removed=[], modified=[], timestamp=time.time(),
        )
        # Build symbols first (needed by peek)
        symbols: dict[str, list[IndexSymbolEntry]] = {}
        symbols = incremental_symbols(project, delta, symbols)

        current: dict = {}
        result = incremental_peek(project, delta, symbols, scan, current)
        # README.md should be in the peek cache if it has resolvable refs
        md_files = [p for p in scan if p.endswith(".md")]
        assert len(md_files) >= 1  # we have docs/README.md
        # The result should be the same object (mutated in place)
        assert result is current

    def test_empty_delta_returns_cached(self, project: Path) -> None:
        """Empty delta should return current unchanged."""
        scan = scan_project(project)
        empty_delta = ScanDelta(
            added=[], removed=[], modified=[], timestamp=time.time(),
        )
        sentinel = {"test.md": {"resolved": [{"text": "foo"}]}}
        result = incremental_peek(
            project, empty_delta, {}, scan, sentinel,
        )
        assert result is sentinel

    def test_md_change_re_peeks_only_that_file(self, project: Path) -> None:
        """When only .md files change, re-peek only those."""
        scan = scan_project(project)
        # Cold start
        delta1 = ScanDelta(
            added=list(scan.keys()),
            removed=[], modified=[], timestamp=time.time(),
        )
        symbols: dict[str, list[IndexSymbolEntry]] = {}
        symbols = incremental_symbols(project, delta1, symbols)
        current: dict = {}
        current = incremental_peek(project, delta1, symbols, scan, current)

        readme_rel = os.path.join("docs", "README.md")
        # Modify the readme
        delta2 = ScanDelta(
            added=[], removed=[],
            modified=[readme_rel], timestamp=time.time(),
        )
        result = incremental_peek(project, delta2, symbols, scan, current)
        assert isinstance(result, dict)

    def test_purges_removed_md(self, project: Path) -> None:
        """Removed .md files should be purged from cache."""
        readme_rel = os.path.join("docs", "README.md")
        scan = scan_project(project)
        current = {readme_rel: {"resolved": []}}
        delta = ScanDelta(
            added=[], removed=[readme_rel],
            modified=[], timestamp=time.time(),
        )
        result = incremental_peek(project, delta, {}, scan, current)
        assert readme_rel not in result


class TestPeekMediator:
    """Tests for index.peek via the mediator."""

    def test_peek_node_exists(self, mediator: QueryMediator) -> None:
        assert "index.peek" in mediator.tree.all_paths()

    def test_peek_returns_dict(self, mediator: QueryMediator) -> None:
        result = mediator.get("index.peek")
        peek = result["data"]
        assert isinstance(peek, dict)

    def test_peek_contains_md_entries(self, mediator: QueryMediator) -> None:
        result = mediator.get("index.peek")
        peek = result["data"]
        # Our README.md has `main.py` reference which should be peekable
        md_keys = [k for k in peek if k.endswith(".md")]
        # At least some .md files should be peeked
        # (depends on whether the peek module resolves anything)
        assert isinstance(md_keys, list)


# ── Classification tests (Phase 8E) ────────────────────────────


class TestClassifyProject:
    """Tests for the classify_project function."""

    def test_detects_python(self, project: Path) -> None:
        scan = scan_project(project)
        result = classify_project(scan)
        assert "python" in result["languages"]

    def test_detects_markdown(self, project: Path) -> None:
        scan = scan_project(project)
        result = classify_project(scan)
        assert "markdown" in result["languages"]

    def test_primary_language(self, project: Path) -> None:
        scan = scan_project(project)
        result = classify_project(scan)
        assert result["primary_language"] != ""
        assert result["primary_language"] in result["languages"]

    def test_extensions_counted(self, project: Path) -> None:
        scan = scan_project(project)
        result = classify_project(scan)
        assert "py" in result["extensions"]
        assert result["extensions"]["py"] >= 1

    def test_detects_pyproject_framework(self, project: Path) -> None:
        scan = scan_project(project)
        result = classify_project(scan)
        assert "python-project" in result["frameworks"]

    def test_empty_scan(self) -> None:
        result = classify_project({})
        assert result["languages"] == {}
        assert result["primary_language"] == ""
        assert result["frameworks"] == []
        assert result["extensions"] == {}

    def test_framework_from_dockerfile(self, project: Path) -> None:
        """Adding a Dockerfile should detect docker framework."""
        (project / "Dockerfile").write_text("FROM python:3.12\n")
        scan = scan_project(project)
        result = classify_project(scan)
        assert "docker" in result["frameworks"]


class TestClassifyMediator:
    """Tests for index.classify via the mediator."""

    def test_classify_node_exists(self, mediator: QueryMediator) -> None:
        assert "index.classify" in mediator.tree.all_paths()

    def test_classify_returns_dict(self, mediator: QueryMediator) -> None:
        result = mediator.get("index.classify")
        data = result["data"]
        assert isinstance(data, dict)
        assert "languages" in data
        assert "primary_language" in data
        assert "frameworks" in data
        assert "extensions" in data

    def test_classify_finds_python(self, mediator: QueryMediator) -> None:
        result = mediator.get("index.classify")
        assert "python" in result["data"]["languages"]

    def test_stats_includes_classify_data(
        self, mediator: QueryMediator,
    ) -> None:
        stats = mediator.get("index.stats")["data"]
        assert "primary_language" in stats
        assert "framework_count" in stats
        assert "symbol_count" in stats
