"""
Admin API — Backup tree scan endpoint.

Thin HTTP wrapper over ``src.core.services.backup_ops.file_tree_scan``.

Blueprint: backup_bp (imported from routes_backup)
Prefix: /api
Routes:
    /api/backup/tree  — return expandable file tree filtered by type
"""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import backup_ops
from .routes_backup import backup_bp, _project_root


# ── Tree endpoint ──────────────────────────────────────────────────


@backup_bp.route("/backup/tree")
def api_tree():  # type: ignore[no-untyped-def]
    """Return an expandable file tree filtered by type."""
    rel_path = request.args.get("path", "").strip()
    type_filter = request.args.get(
        "types",
        "document,code,script,config,data,image,video,audio,archive,encrypted,other",
    )
    max_depth = min(int(request.args.get("depth", "5")), 10)
    allowed_types = set(type_filter.split(","))
    respect_gitignore = request.args.get("gitignore", "").lower() == "true"

    if not rel_path:
        return jsonify({"error": "Missing 'path'"}), 400

    result = backup_ops.file_tree_scan(
        _project_root(),
        rel_path,
        allowed_types=allowed_types,
        max_depth=max_depth,
        respect_gitignore=respect_gitignore,
    )

    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)
