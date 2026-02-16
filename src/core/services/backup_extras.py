"""Backup extras — git tracking (mark-special) and file tree scanning."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from src.core.services.backup_common import (
    backup_dir_for, classify_file, resolve_folder, SKIP_DIRS, MEDIA_EXT, DOC_EXT,
)

logger = logging.getLogger(__name__)


from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("backup")


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
            _audit(
                "📌 Backup Unmarked",
                f"{backup_path} removed from git tracking",
                action="unmarked",
                target=backup_path,
                detail={"backup": backup_path, "unmark": True},
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
        _audit(
            "📌 Backup Marked",
            f"{backup_path} added to git tracking",
            action="marked",
            target=backup_path,
            detail={"backup": backup_path, "unmark": False},
        )
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
#  Release operations (upload/delete release artifacts for backups)
# ═══════════════════════════════════════════════════════════════════


def upload_backup_to_release(project_root: Path, backup_path: str) -> dict:
    """Upload a backup file to a GitHub Release as an artifact.

    Creates release metadata sidecar and starts background upload.

    Args:
        project_root: Project root directory.
        backup_path: Relative path to the backup file.

    Returns:
        Dict with success info or error.
    """
    import json
    from datetime import datetime, timezone

    if not backup_path:
        return {"error": "Missing 'path'"}

    file_path = (project_root / backup_path).resolve()
    try:
        file_path.relative_to(project_root)
    except ValueError:
        return {"error": "Invalid path"}

    if not file_path.exists():
        return {"error": "File not found", "_status": 404}

    try:
        from src.core.services.content_release import upload_to_release_bg
        file_id = f"backup_{file_path.stem}"
        upload_to_release_bg(file_id, file_path, project_root)

        meta_path = file_path.parent / f"{file_path.name}.release.json"
        meta = {
            "file_id": file_id,
            "asset_name": file_path.name,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "status": "uploading",
        }
        meta_path.write_text(json.dumps(meta, indent=2))

        _audit(
            "☁️ Backup Release Upload",
            f"{file_path.name} upload started to GitHub Release",
            action="uploaded",
            target=backup_path,
            detail={"file": backup_path, "file_id": file_id},
        )

        return {
            "success": True,
            "file_id": file_id,
            "message": f"Upload started for {file_path.name}",
        }
    except Exception as e:
        logger.exception("Failed to start release upload")
        _audit(
            "❌ Backup Release Upload Failed",
            f"{file_path.name}: {e}",
            detail={"file": backup_path, "error": str(e)},
        )
        return {"error": f"Upload failed: {e}", "_status": 500}


def delete_backup_release(project_root: Path, backup_path: str) -> dict:
    """Delete a backup file's GitHub Release artifact.

    Reads release metadata sidecar, deletes the asset, and cleans up.

    Args:
        project_root: Project root directory.
        backup_path: Relative path to the backup file.

    Returns:
        Dict with success info or error.
    """
    import json

    if not backup_path:
        return {"error": "Missing 'backup_path'"}

    file_path = (project_root / backup_path).resolve()
    try:
        file_path.relative_to(project_root)
    except ValueError:
        return {"error": "Invalid path"}

    meta_path = file_path.parent / f"{file_path.name}.release.json"
    if not meta_path.exists():
        return {"error": "No release metadata found for this backup", "_status": 404}

    try:
        meta = json.loads(meta_path.read_text())
    except Exception:
        return {"error": "Could not read release metadata", "_status": 500}

    asset_name = meta.get("old_asset_name") or meta.get("asset_name", file_path.name)

    try:
        from src.core.services.content_release import delete_release_asset
        delete_release_asset(asset_name, project_root)
        meta_path.unlink(missing_ok=True)

        _audit(
            "☁️❌ Release Asset Deleted",
            f"Release asset '{asset_name}' deletion queued",
            action="deleted",
            target=asset_name,
            detail={"backup": backup_path, "asset": asset_name},
        )

        return {
            "success": True,
            "message": f"Queued deletion of release asset: {asset_name}",
        }
    except Exception as e:
        logger.exception("Failed to delete release asset")
        _audit(
            "❌ Release Delete Failed",
            f"{asset_name}: {e}",
            detail={"backup": backup_path, "asset": asset_name, "error": str(e)},
        )
        return {"error": f"Deletion failed: {e}", "_status": 500}


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
