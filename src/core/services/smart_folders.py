"""
Smart Folders — discovery and resolution service.

Scans source paths for documentation files (typically README.md),
cross-references with declared project modules, and builds a
module-grouped tree structure.

Channel-independent: no Flask or HTTP dependency.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ── Discovery ───────────────────────────────────────────────────────


def discover(
    project_root: Path,
    sources: list[dict],
) -> list[dict]:
    """Scan source paths and return flat list of discovered doc files.

    Args:
        project_root: Project root directory.
        sources: List of source dicts, each with:
            - path: str — root directory to scan (relative to project_root)
            - pattern: str — glob pattern (e.g. ``**/README.md``)

    Returns:
        List of dicts, each with:
            - source_path: str — path relative to project root
            - relative_path: str — path relative to source.path
            - name: str — file basename
            - size_bytes: int
            - modified: str — ISO timestamp
    """
    results: list[dict] = []
    seen: set[str] = set()

    for source in sources:
        source_dir = project_root / source["path"]
        pattern = source.get("pattern", "**/README.md")

        if not source_dir.is_dir():
            log.warning("smart_folders: source path does not exist: %s", source_dir)
            continue

        for filepath in _glob_walk(source_dir, pattern):
            # Path relative to project root
            try:
                source_path = str(filepath.relative_to(project_root))
            except ValueError:
                continue

            if source_path in seen:
                continue
            seen.add(source_path)

            # Path relative to this source's root
            try:
                relative_path = str(filepath.relative_to(source_dir))
            except ValueError:
                relative_path = source_path

            try:
                stat = filepath.stat()
                size_bytes = stat.st_size
                modified = datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat()
            except OSError:
                size_bytes = 0
                modified = ""

            results.append({
                "source_path": source_path,
                "relative_path": relative_path,
                "name": filepath.name,
                "size_bytes": size_bytes,
                "modified": modified,
            })

    results.sort(key=lambda r: r["source_path"])
    return results


# ── Module Matching ─────────────────────────────────────────────────


def _match_module(
    source_path: str,
    modules: list[dict],
) -> tuple[dict | None, str]:
    """Find the module whose path is a prefix of source_path.

    Returns:
        (module_dict, module_relative_path) or (None, source_path)
    """
    best: dict | None = None
    best_len = 0

    for mod in modules:
        mod_path = mod.get("path", "")
        if not mod_path:
            continue
        # Normalize: ensure no trailing slash for prefix matching
        mod_path = mod_path.rstrip("/")
        # Check if source_path starts with module path
        if source_path == mod_path or source_path.startswith(mod_path + "/"):
            if len(mod_path) > best_len:
                best = mod
                best_len = len(mod_path)

    if best:
        mod_path = best["path"].rstrip("/")
        rel = source_path[len(mod_path):].lstrip("/")
        return best, rel

    return None, source_path


# ── Resolution (Module-Grouped Tree) ───────────────────────────────


def resolve(
    project_root: Path,
    smart_folder: dict,
    modules: list[dict],
) -> dict:
    """Resolve a smart folder into a module-grouped tree structure.

    Args:
        project_root: Project root directory.
        smart_folder: Smart folder config from project.yml.
        modules: Module list from project.yml.

    Returns:
        Dict with:
            - name: str
            - label: str
            - target: str
            - total_files: int
            - groups: list of module groups, each with:
                - module: str (module name or "other")
                - module_path: str (module path or "")
                - file_count: int
                - tree: nested tree dict
    """
    sources = smart_folder.get("sources", [])
    files = discover(project_root, sources)

    # Group files by module
    groups_map: dict[str, dict[str, Any]] = {}

    for f in files:
        mod, mod_rel = _match_module(f["source_path"], modules)
        mod_name = mod["name"] if mod else "other"
        mod_path = mod["path"] if mod else ""

        if mod_name not in groups_map:
            groups_map[mod_name] = {
                "module": mod_name,
                "module_path": mod_path,
                "files": [],
            }

        groups_map[mod_name]["files"].append({
            **f,
            "module_relative": mod_rel,
        })

    # Build tree for each module group
    groups: list[dict] = []
    for mod_name in sorted(groups_map.keys()):
        grp = groups_map[mod_name]
        tree = _build_tree(mod_name, grp["files"])
        groups.append({
            "module": grp["module"],
            "module_path": grp["module_path"],
            "file_count": len(grp["files"]),
            "tree": tree,
        })

    return {
        "name": smart_folder.get("name", ""),
        "label": smart_folder.get("label", ""),
        "target": smart_folder.get("target", ""),
        "total_files": len(files),
        "groups": groups,
    }


# ── Tree Builder ────────────────────────────────────────────────────


def _build_tree(root_name: str, files: list[dict]) -> dict:
    """Build a nested tree from a flat list of files using module_relative paths.

    Args:
        root_name: Name for the root node.
        files: List of file dicts, each with ``module_relative`` key.

    Returns:
        Nested tree dict: {name, children: [...], files: [...]}
    """
    root: dict[str, Any] = {"name": root_name, "children": [], "files": []}

    for f in files:
        parts = Path(f["module_relative"]).parts
        node = root

        # Navigate/create intermediate directories
        for part in parts[:-1]:
            child = next(
                (c for c in node["children"] if c["name"] == part),
                None,
            )
            if child is None:
                child = {"name": part, "children": [], "files": []}
                node["children"].append(child)
            node = child

        # Add file to the leaf directory
        node["files"].append({
            "name": parts[-1] if parts else f["name"],
            "source_path": f["source_path"],
            "size_bytes": f["size_bytes"],
            "modified": f["modified"],
        })

    # Sort children and files at every level
    _sort_tree(root)
    return root


def _sort_tree(node: dict) -> None:
    """Recursively sort children by name and files by name."""
    node["children"].sort(key=lambda c: c["name"])
    node["files"].sort(key=lambda f: f["name"])
    for child in node["children"]:
        _sort_tree(child)


# ── Glob Walker ─────────────────────────────────────────────────────


def _glob_walk(directory: Path, pattern: str) -> list[Path]:
    """Walk a directory matching files against a glob pattern.

    Supports ``**`` for recursive matching (e.g. ``**/README.md``).
    Ignores common non-content directories.
    """
    _SKIP = {
        "__pycache__", ".git", ".venv", "node_modules",
        ".mypy_cache", ".pytest_cache", ".tox", "dist", "build",
    }

    matches: list[Path] = []

    for dirpath, dirnames, filenames in os.walk(directory):
        # Prune skipped directories
        dirnames[:] = [d for d in dirnames if d not in _SKIP]

        current = Path(dirpath)
        for filename in filenames:
            filepath = current / filename
            # Match relative to the walk root
            try:
                rel = str(filepath.relative_to(directory))
            except ValueError:
                continue
            if fnmatch(rel, pattern):
                matches.append(filepath)

    return matches


# ── Helpers ─────────────────────────────────────────────────────────


def find_smart_folder(
    smart_folders: list[dict],
    name: str,
) -> dict | None:
    """Find a smart folder config by name."""
    for sf in smart_folders:
        if sf.get("name") == name:
            return sf
    return None


def list_smart_folder_names(smart_folders: list[dict]) -> list[str]:
    """Return list of smart folder names."""
    return [sf.get("name", "") for sf in smart_folders if sf.get("name")]
