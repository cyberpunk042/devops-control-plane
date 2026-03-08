"""Tests for file_discovery shared library module."""

from pathlib import Path

import pytest

from src.core.data.script_templates.lib.file_discovery import (
    DEFAULT_EXCLUDES,
    discover_files,
    discover_python_files,
    file_relative_module,
    group_by_package,
)


# ── DEFAULT_EXCLUDES ─────────────────────────────────────────────


def test_default_excludes_contains_standard_patterns():
    """Core exclusion patterns are present."""
    for pattern in ("__pycache__", ".venv", "node_modules", ".git"):
        assert pattern in DEFAULT_EXCLUDES


# ── discover_files ───────────────────────────────────────────────


def test_discover_files_finds_py_files(tmp_path):
    """Discovers .py files in a directory tree."""
    (tmp_path / "a.py").write_text("# a")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("# b")
    (tmp_path / "sub" / "c.txt").write_text("not python")

    result = discover_files(tmp_path, extensions=(".py",))

    names = [p.name for p in result]
    assert "a.py" in names
    assert "b.py" in names
    assert "c.txt" not in names


def test_discover_files_excludes_pycache(tmp_path):
    """Files inside excluded directories are filtered out."""
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "cached.py").write_text("# cached")
    (tmp_path / "real.py").write_text("# real")

    result = discover_files(tmp_path)

    names = [p.name for p in result]
    assert "real.py" in names
    assert "cached.py" not in names


def test_discover_files_excludes_nested_excluded_dir(tmp_path):
    """Exclusion works for deeply nested excluded directories."""
    deep = tmp_path / "a" / "b" / ".venv" / "c"
    deep.mkdir(parents=True)
    (deep / "hidden.py").write_text("# hidden")
    (tmp_path / "top.py").write_text("# top")

    result = discover_files(tmp_path)

    names = [p.name for p in result]
    assert "top.py" in names
    assert "hidden.py" not in names


def test_discover_files_filters_dotfiles_by_default(tmp_path):
    """Hidden files (starting with .) are excluded by default."""
    (tmp_path / ".hidden.py").write_text("# hidden")
    (tmp_path / "visible.py").write_text("# visible")

    result = discover_files(tmp_path)

    names = [p.name for p in result]
    assert "visible.py" in names
    assert ".hidden.py" not in names


def test_discover_files_includes_dotfiles_when_requested(tmp_path):
    """Hidden files are included when include_hidden=True."""
    (tmp_path / ".hidden.py").write_text("# hidden")

    result = discover_files(tmp_path, include_hidden=True)

    names = [p.name for p in result]
    assert ".hidden.py" in names


def test_discover_files_multiple_extensions(tmp_path):
    """Discovers files matching any of the given extensions."""
    (tmp_path / "a.py").write_text("# py")
    (tmp_path / "b.sh").write_text("# sh")
    (tmp_path / "c.txt").write_text("# txt")

    result = discover_files(tmp_path, extensions=(".py", ".sh"))

    names = [p.name for p in result]
    assert "a.py" in names
    assert "b.sh" in names
    assert "c.txt" not in names


def test_discover_files_no_extension_filter(tmp_path):
    """Empty extensions tuple discovers all files."""
    (tmp_path / "a.py").write_text("# py")
    (tmp_path / "b.txt").write_text("# txt")

    result = discover_files(tmp_path, extensions=())

    names = [p.name for p in result]
    assert "a.py" in names
    assert "b.txt" in names


def test_discover_files_empty_directory(tmp_path):
    """Empty directory returns empty list."""
    result = discover_files(tmp_path)
    assert result == []


def test_discover_files_nonexistent_directory():
    """Non-existent directory returns empty list (no crash)."""
    result = discover_files(Path("/nonexistent/path/unlikely"))
    assert result == []


def test_discover_files_returns_sorted(tmp_path):
    """Results are returned in sorted order."""
    (tmp_path / "z.py").write_text("# z")
    (tmp_path / "a.py").write_text("# a")
    (tmp_path / "m.py").write_text("# m")

    result = discover_files(tmp_path)

    names = [p.name for p in result]
    assert names == sorted(names)


def test_discover_files_returns_absolute_paths(tmp_path):
    """All returned paths are absolute."""
    (tmp_path / "a.py").write_text("# a")

    result = discover_files(tmp_path)

    for p in result:
        assert p.is_absolute()


def test_discover_files_custom_excludes(tmp_path):
    """Custom exclusion patterns override defaults."""
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "lib.py").write_text("# vendored")
    (tmp_path / "real.py").write_text("# real")

    # Default excludes don't contain "vendor"
    result_default = discover_files(tmp_path)
    names_default = [p.name for p in result_default]
    assert "lib.py" in names_default

    # Custom excludes with "vendor"
    result_custom = discover_files(tmp_path, exclude_patterns=("vendor",))
    names_custom = [p.name for p in result_custom]
    assert "lib.py" not in names_custom
    assert "real.py" in names_custom


# ── discover_python_files ────────────────────────────────────────


def test_discover_python_files_scans_source_dir(tmp_path):
    """Scans the source_dir subdirectory."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("# main")
    (tmp_path / "setup.py").write_text("# setup — outside src")

    result = discover_python_files(tmp_path, source_dir="src")

    names = [p.name for p in result]
    assert "main.py" in names
    assert "setup.py" not in names  # Outside source_dir


def test_discover_python_files_missing_source_dir(tmp_path):
    """Returns empty list when source_dir doesn't exist."""
    result = discover_python_files(tmp_path, source_dir="nonexistent")
    assert result == []


def test_discover_python_files_with_nested_packages(tmp_path):
    """Finds files in nested package directories."""
    pkg = tmp_path / "src" / "core" / "services"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "engine.py").write_text("# engine")

    result = discover_python_files(tmp_path, source_dir="src")

    names = [p.name for p in result]
    assert "__init__.py" in names
    assert "engine.py" in names


# ── group_by_package ─────────────────────────────────────────────


def test_group_by_package_groups_correctly(tmp_path):
    """Groups files by their parent directory as dotted path."""
    pkg_a = tmp_path / "core" / "services"
    pkg_a.mkdir(parents=True)
    (pkg_a / "foo.py").write_text("")
    (pkg_a / "bar.py").write_text("")

    pkg_b = tmp_path / "core" / "models"
    pkg_b.mkdir(parents=True)
    (pkg_b / "base.py").write_text("")

    files = discover_files(tmp_path)
    groups = group_by_package(files, tmp_path)

    assert "core.services" in groups
    assert "core.models" in groups
    assert len(groups["core.services"]) == 2
    assert len(groups["core.models"]) == 1


def test_group_by_package_root_files(tmp_path):
    """Files in the root directory are grouped under '(root)'."""
    (tmp_path / "setup.py").write_text("")

    files = discover_files(tmp_path)
    groups = group_by_package(files, tmp_path)

    assert "(root)" in groups
    assert len(groups["(root)"]) == 1


def test_group_by_package_file_outside_root(tmp_path):
    """Files outside root are skipped."""
    other = tmp_path / "other"
    other.mkdir()
    outside_file = other / "outside.py"
    outside_file.write_text("")

    # Manually pass an outside file
    groups = group_by_package([outside_file.resolve()], tmp_path / "src")

    # Should be empty — the file is not under root
    assert len(groups) == 0


# ── file_relative_module ─────────────────────────────────────────


def test_file_relative_module_basic(tmp_path):
    """Converts a path to dotted module notation."""
    py_file = tmp_path / "src" / "core" / "services" / "vault" / "ops.py"
    py_file.parent.mkdir(parents=True)
    py_file.write_text("")

    result = file_relative_module(py_file, tmp_path)

    assert result == "src.core.services.vault.ops"


def test_file_relative_module_init(tmp_path):
    """__init__.py maps to the package, not the __init__ module."""
    init_file = tmp_path / "src" / "core" / "__init__.py"
    init_file.parent.mkdir(parents=True)
    init_file.write_text("")

    result = file_relative_module(init_file, tmp_path)

    assert result == "src.core"


def test_file_relative_module_root_file(tmp_path):
    """File directly in root → module name is just the stem."""
    py_file = tmp_path / "setup.py"
    py_file.write_text("")

    result = file_relative_module(py_file, tmp_path)

    assert result == "setup"


def test_file_relative_module_root_init(tmp_path):
    """__init__.py directly in root → empty module path."""
    init_file = tmp_path / "__init__.py"
    init_file.write_text("")

    result = file_relative_module(init_file, tmp_path)

    assert result == ""


def test_file_relative_module_outside_root(tmp_path):
    """File outside root falls back to stem."""
    other = tmp_path / "other"
    other.mkdir()
    py_file = other / "module.py"
    py_file.write_text("")

    # root is tmp_path / "project" — doesn't exist as parent of py_file
    result = file_relative_module(py_file, tmp_path / "project")

    assert result == "module"
