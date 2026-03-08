"""
File Discovery Module
=====================
Walk directories with configurable filters and return file lists.

Thin wrapper over pathlib that standardises exclusion patterns
and provides a consistent interface for all scripts.

Pipeline position: Step 1 (discover) → parse → graph → render → report
"""

from __future__ import annotations

from pathlib import Path


# Standard exclusion patterns (shared across all scripts)
DEFAULT_EXCLUDES: tuple[str, ...] = (
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".git",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "build",
    "dist",
    ".eggs",
    ".ruff_cache",
)


def discover_files(
    root: Path,
    *,
    extensions: tuple[str, ...] = (".py",),
    exclude_patterns: tuple[str, ...] = DEFAULT_EXCLUDES,
    include_hidden: bool = False,
) -> list[Path]:
    """Discover files under root matching the given extensions.

    Walks the directory tree recursively, filtering by extension and
    skipping excluded directories.

    Args:
        root: Root directory to scan.
        extensions: File extensions to include (with leading dot).
        exclude_patterns: Directory names to skip entirely.
        include_hidden: Include dotfiles (files starting with .).

    Returns:
        Sorted list of absolute paths.
    """
    if not root.is_dir():
        return []

    result: list[Path] = []
    exclude_set = set(exclude_patterns)

    for item in sorted(root.rglob("*")):
        # Skip directories themselves — we only collect files
        if item.is_dir():
            continue

        # Check if any parent directory is in the exclude set
        if _path_contains_excluded(item, root, exclude_set):
            continue

        # Check extension
        if extensions and item.suffix not in extensions:
            continue

        # Check hidden files
        if not include_hidden and item.name.startswith("."):
            continue

        result.append(item.resolve())

    return result


def discover_python_files(
    root: Path,
    *,
    source_dir: str = "src",
    exclude_patterns: tuple[str, ...] = DEFAULT_EXCLUDES,
) -> list[Path]:
    """Convenience: discover all Python files in a source directory.

    Equivalent to ``discover_files(root / source_dir, extensions=(".py",))``
    but handles the case where *source_dir* doesn't exist gracefully.

    Args:
        root: Project root directory.
        source_dir: Source directory relative to root.
        exclude_patterns: Directory names to skip.

    Returns:
        Sorted list of absolute paths to ``.py`` files.
    """
    scan_root = root / source_dir
    if not scan_root.is_dir():
        return []
    return discover_files(
        scan_root,
        extensions=(".py",),
        exclude_patterns=exclude_patterns,
    )


def group_by_package(
    files: list[Path],
    root: Path,
) -> dict[str, list[Path]]:
    """Group files by their parent package.

    Args:
        files: List of absolute file paths (from discover_files).
        root: Root directory that was scanned.

    Returns:
        Dict mapping package name → list of files in that package.
        e.g., ``{"core.services.vault": [Path("vault/__init__.py"), ...]}``
    """
    groups: dict[str, list[Path]] = {}
    resolved_root = root.resolve()

    for fpath in files:
        resolved = fpath.resolve()
        try:
            rel = resolved.relative_to(resolved_root)
        except ValueError:
            # File is not under root — skip
            continue

        # Package = parent directory as dotted path
        parent_parts = rel.parent.parts
        if parent_parts:
            package = ".".join(parent_parts)
        else:
            package = "(root)"

        groups.setdefault(package, []).append(resolved)

    return groups


def file_relative_module(path: Path, root: Path) -> str:
    """Convert a file path to a Python module path.

    e.g., ``/project/src/core/services/vault/ops.py``
    → ``src.core.services.vault.ops``

    Strips ``.py`` extension and ``__init__`` suffix.

    Args:
        path: Absolute path to a ``.py`` file.
        root: Project root directory.

    Returns:
        Dotted module path string.
    """
    resolved_path = path.resolve()
    resolved_root = root.resolve()

    try:
        rel = resolved_path.relative_to(resolved_root)
    except ValueError:
        # Fallback: use the filename stem
        return path.stem

    # Remove .py extension
    parts = list(rel.with_suffix("").parts)

    # Remove __init__ — the module is the package itself
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]

    return ".".join(parts)


# ── Internal helpers ──────────────────────────────────────────────


def _path_contains_excluded(
    item: Path,
    root: Path,
    exclude_set: set[str],
) -> bool:
    """Check if any parent directory name is in the exclude set."""
    try:
        rel = item.relative_to(root)
    except ValueError:
        return False

    for part in rel.parts[:-1]:  # Check directories, not the file itself
        if part in exclude_set:
            return True
    return False
