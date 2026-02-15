"""Backup extras — git tracking (mark-special) and file tree scanning."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from src.core.services.backup_common import (
    backup_dir_for, classify_file, resolve_folder, MEDIA_EXT, DOC_EXT,
)

logger = logging.getLogger(__name__)

_SPECIAL_MAX_BYTES = 25 * 1024 * 1024  # 25 MB

def mark_special(project_root: Path, backup_path: str, *, unmark: bool = False) -> dict:
    """Force-add a backup to git (git add -f), or unmark (git rm --cached)."""
    if not backup_path:
        return {"error": "Missing 'backup_path'"}

    file_path = (project_root / backup_path).resolve()
    try:
        file_path.relative_to(project_root)
    except ValueError:
        return {"error": "Invalid path"}

    if not file_path.exists():
        return {"error": "File not found"}

    if unmark:
        try:
            subprocess.run(
                ["git", "rm", "--cached", str(file_path)],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=15,
            )
            return {"success": True, "message": "Removed from git tracking"}
        except Exception as e:
            return {"error": f"git rm --cached failed: {e}"}

    size = file_path.stat().st_size
    if size > _SPECIAL_MAX_BYTES:
        size_mb = size / (1024 * 1024)
        return {
            "error": (
                f"File too large for git ({size_mb:.1f} MB). "
                f"Maximum is {_SPECIAL_MAX_BYTES // (1024 * 1024)} MB. "
                "Use '🚀 Upload to Release' instead."
            ),
        }

    try:
        result = subprocess.run(
            ["git", "add", "-f", str(file_path)],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return {"error": f"git add -f failed: {result.stderr[:200]}"}
        return {
            "success": True,
            "message": f"Added to git (force): {file_path.name}",
            "size_bytes": size,
        }
    except Exception as e:
        logger.exception("Failed to mark backup as special")
        return {"error": f"git add -f failed: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  File tree scan (for archive panel)
# ═══════════════════════════════════════════════════════════════════


def file_tree_scan(
    project_root: Path,
    rel_path: str,
    *,
    allowed_types: set[str] | None = None,
    max_depth: int = 5,
    respect_gitignore: bool = False,
) -> dict:
    """Return an expandable file tree filtered by type."""
    if not rel_path:
        return {"error": "Missing 'path'"}

    folder = resolve_folder(project_root, rel_path)
    if folder is None:
        return {"error": f"Folder not found: {rel_path}"}

    if allowed_types is None:
        allowed_types = {
            "document", "code", "script", "config", "data",
            "image", "video", "audio", "archive", "encrypted", "other",
        }

    max_depth = min(max_depth, 10)

    # Build set of allowed files if respecting gitignore
    gitignore_allowed: set[str] | None = None
    if respect_gitignore:
        try:
            result = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                gitignore_allowed = set(result.stdout.strip().splitlines())
        except Exception:
            pass

    def _scan(directory: Path, depth: int) -> list[dict]:
        if depth > max_depth:
            return []
        items: list[dict] = []
        try:
            entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return []

        for entry in entries:
            if entry.name.startswith(".") or entry.name in SKIP_DIRS:
                continue

            if entry.is_dir():
                children = _scan(entry, depth + 1)
                if children:
                    items.append({
                        "name": entry.name,
                        "path": str(entry.resolve().relative_to(project_root)),
                        "type": "directory",
                        "children": children,
                        "count": sum(
                            c.get("count", 1) if c["type"] == "directory" else 1
                            for c in children
                        ),
                    })
            elif entry.is_file():
                if gitignore_allowed is not None:
                    rel_file = str(entry.resolve().relative_to(project_root))
                    if rel_file not in gitignore_allowed:
                        continue
                ftype = classify_file(entry)
                if ftype in allowed_types:
                    items.append({
                        "name": entry.name,
                        "path": str(entry.resolve().relative_to(project_root)),
                        "type": ftype,
                        "size": entry.stat().st_size,
                    })
        return items

    tree = _scan(folder, 0)

    def _count(nodes: list[dict]) -> dict[str, int]:
        c: dict[str, int] = {}
        for n in nodes:
            if n["type"] == "directory":
                sub = _count(n["children"])
                for k, v in sub.items():
                    c[k] = c.get(k, 0) + v
            else:
                c[n["type"]] = c.get(n["type"], 0) + 1
        return c

    counts = _count(tree)
    return {"root": rel_path, "tree": tree, "counts": counts}


# ═══════════════════════════════════════════════════════════════════
#  Internal helpers
# ═══════════════════════════════════════════════════════════════════


def _cleanup_release_sidecar(file_path: Path, project_root: Path) -> None:
    """Clean up release sidecar + GitHub asset if present."""
    try:
        from src.core.services.content_release import cleanup_release_sidecar
        cleanup_release_sidecar(file_path, project_root)
    except (ImportError, Exception):
        pass
