"""
Admin API — Backup tree scan endpoint.

Split from routes_backup.py. Provides the expandable file tree filtered by type
for the archive panel UI.

Blueprint: backup_bp (imported from routes_backup)
Prefix: /api
Routes:
    /api/backup/tree  — return expandable file tree filtered by type
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import jsonify, request

from .routes_backup import (
    backup_bp,
    _project_root,
    _resolve_folder,
    _classify,
    _SKIP_DIRS,
)

logger = logging.getLogger(__name__)


# ── Tree endpoint ──────────────────────────────────────────────────


@backup_bp.route("/backup/tree")
def api_tree():  # type: ignore[no-untyped-def]
    """Return an expandable file tree filtered by type.

    Query params:
        path:       root folder to scan (relative to project root)
        types:      comma-separated types to include (docs,media,encrypted,other)
                    defaults to all
        depth:      max recursion depth (default 5)
        gitignore:  if 'true', exclude files matched by .gitignore
    """
    rel_path = request.args.get("path", "").strip()
    type_filter = request.args.get("types", "document,code,script,config,data,image,video,audio,archive,encrypted,other")
    max_depth = min(int(request.args.get("depth", "5")), 10)
    allowed_types = set(type_filter.split(","))
    respect_gitignore = request.args.get("gitignore", "").lower() == "true"

    if not rel_path:
        return jsonify({"error": "Missing 'path'"}), 400

    folder = _resolve_folder(rel_path)
    if folder is None:
        return jsonify({"error": f"Folder not found: {rel_path}"}), 404

    root = _project_root()

    # Build set of allowed files if respecting gitignore
    gitignore_allowed: set[str] | None = None
    if respect_gitignore:
        try:
            import subprocess
            result = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                gitignore_allowed = set(result.stdout.strip().splitlines())
        except Exception:
            pass  # Fall back to no filtering if git not available

    def _scan(directory: Path, depth: int) -> list[dict]:
        if depth > max_depth:
            return []

        items: list[dict] = []
        try:
            entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return []

        for entry in entries:
            # Skip hidden dirs, .backup, and tool directories
            if entry.name.startswith(".") or entry.name in _SKIP_DIRS:
                continue

            if entry.is_dir():
                children = _scan(entry, depth + 1)
                if children:  # only include dirs that have matching files
                    items.append({
                        "name": entry.name,
                        "path": str(entry.resolve().relative_to(root)),
                        "type": "directory",
                        "children": children,
                        "count": sum(
                            c.get("count", 1) if c["type"] == "directory" else 1
                            for c in children
                        ),
                    })
            elif entry.is_file():
                # Skip files excluded by .gitignore
                if gitignore_allowed is not None:
                    rel_file = str(entry.resolve().relative_to(root))
                    if rel_file not in gitignore_allowed:
                        continue
                ftype = _classify(entry)
                if ftype in allowed_types:
                    items.append({
                        "name": entry.name,
                        "path": str(entry.resolve().relative_to(root)),
                        "type": ftype,
                        "size": entry.stat().st_size,
                    })

        return items

    tree = _scan(folder, 0)

    # Count totals
    def _count(nodes: list[dict]) -> dict:
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

    return jsonify({
        "root": rel_path,
        "tree": tree,
        "counts": counts,
    })
