"""
Smart Folders API routes.

Blueprint: smart_folders_bp
Prefix: /api

Routes:
    GET /api/smart-folders                 — list configured smart folders
    GET /api/smart-folders/discover        — auto-detect potential smart folder sources
    GET /api/smart-folders/<name>/tree     — resolve a smart folder into module-grouped tree
    GET /api/smart-folders/<name>/file     — read a file from its real source location
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import config_ops
from src.core.services import smart_folders as sf
from src.ui.web.helpers import project_root as _project_root

logger = logging.getLogger(__name__)

smart_folders_bp = Blueprint("smart_folders", __name__)


def _load_config() -> dict:
    """Load project config."""
    return config_ops.read_config(_project_root()).get("config", {})


# ── List configured smart folders ───────────────────────────────────


@smart_folders_bp.route("/smart-folders")
def api_smart_folders_list():  # type: ignore[no-untyped-def]
    """Return list of configured smart folders with summary stats."""
    cfg = _load_config()
    smart = cfg.get("smart_folders", [])
    modules = cfg.get("modules", [])
    root = _project_root()

    results = []
    for folder in smart:
        try:
            resolved = sf.resolve(root, folder, modules)
            results.append({
                "name": resolved["name"],
                "label": resolved["label"],
                "target": resolved["target"],
                "total_files": resolved["total_files"],
                "sources": folder.get("sources", []),
                "groups": [
                    {
                        "module": g["module"],
                        "module_path": g["module_path"],
                        "file_count": g["file_count"],
                    }
                    for g in resolved["groups"]
                ],
            })
        except Exception as e:
            logger.warning("Error resolving smart folder %s: %s", folder.get("name"), e)
            results.append({
                "name": folder.get("name", "?"),
                "label": folder.get("label", ""),
                "target": folder.get("target", ""),
                "error": str(e),
            })

    return jsonify({"smart_folders": results})


# ── Auto-detect potential sources ───────────────────────────────────


@smart_folders_bp.route("/smart-folders/discover")
def api_smart_folders_discover():  # type: ignore[no-untyped-def]
    """Scan the project for markdown files in code directories.

    This is used by the wizard to auto-detect candidates for smart folders.
    It scans all module paths declared in project.yml for .md files.

    Query params:
        pattern: glob pattern (default: ``**/README.md``)
    """
    cfg = _load_config()
    modules = cfg.get("modules", [])
    root = _project_root()
    pattern = request.args.get("pattern", "**/README.md")

    # Build sources from all module paths (excluding the docs module)
    sources = []
    for mod in modules:
        mod_path = mod.get("path", "")
        if not mod_path:
            continue
        # Skip modules that are content folders (e.g. "docs" module with path "docs")
        if mod_path in cfg.get("content_folders", []):
            continue
        if (root / mod_path).is_dir():
            sources.append({"path": mod_path, "pattern": pattern})

    files = sf.discover(root, sources)

    # Group by module for summary
    module_counts: dict[str, int] = {}
    for f in files:
        mod, _ = sf._match_module(f["source_path"], modules)
        mod_name = mod["name"] if mod else "other"
        module_counts[mod_name] = module_counts.get(mod_name, 0) + 1

    return jsonify({
        "total_files": len(files),
        "pattern": pattern,
        "module_counts": module_counts,
        "sources_scanned": [s["path"] for s in sources],
        "files": files,
    })


# ── Resolve smart folder tree ──────────────────────────────────────


@smart_folders_bp.route("/smart-folders/<name>/tree")
def api_smart_folders_tree(name: str):  # type: ignore[no-untyped-def]
    """Resolve a smart folder into its full module-grouped tree."""
    cfg = _load_config()
    smart = cfg.get("smart_folders", [])
    modules = cfg.get("modules", [])
    root = _project_root()

    folder = sf.find_smart_folder(smart, name)
    if folder is None:
        return jsonify({"error": f"Smart folder '{name}' not found"}), 404

    resolved = sf.resolve(root, folder, modules)
    return jsonify(resolved)


# ── Read file from real location ────────────────────────────────────


@smart_folders_bp.route("/smart-folders/<name>/file")
def api_smart_folders_file(name: str):  # type: ignore[no-untyped-def]
    """Read a file from its real source location.

    Query params:
        path: source path relative to project root
            (e.g. ``src/core/services/chat/README.md``)
    """
    cfg = _load_config()
    smart = cfg.get("smart_folders", [])
    root = _project_root()

    folder = sf.find_smart_folder(smart, name)
    if folder is None:
        return jsonify({"error": f"Smart folder '{name}' not found"}), 404

    rel_path = request.args.get("path", "").strip()
    if not rel_path:
        return jsonify({"error": "Missing 'path' parameter"}), 400

    # Security: verify the path is within the project root
    filepath = (root / rel_path).resolve()
    if not str(filepath).startswith(str(root.resolve())):
        return jsonify({"error": "Path traversal not allowed"}), 403

    if not filepath.is_file():
        return jsonify({"error": f"File not found: {rel_path}"}), 404

    try:
        content = filepath.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return jsonify({"error": "File is not UTF-8 text"}), 400
    except Exception as e:
        return jsonify({"error": f"Read error: {e}"}), 500

    stat = filepath.stat()

    return jsonify({
        "path": rel_path,
        "name": filepath.name,
        "content": content,
        "size_bytes": stat.st_size,
        "lines": content.count("\n") + 1,
    })
