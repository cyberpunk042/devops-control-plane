"""
Admin API — Outline and glossary endpoints.

Blueprint: content_bp (imported from routes_content)
Prefix: /api
Routes:
    GET  /api/content/outline   — structural outline for a single file
    GET  /api/content/glossary  — folder glossary tree with per-file outlines
"""

from __future__ import annotations

import logging

from flask import jsonify, request

from . import content_bp
from .helpers import project_root as _project_root, resolve_safe_path

logger = logging.getLogger(__name__)


# ── Single file outline ─────────────────────────────────────────────

@content_bp.route("/content/outline", methods=["GET"])
def content_outline():
    """Return the structural outline for a single file.

    Query params:
        path (str): Relative path to the file within the project root.

    Returns:
        JSON with ``path``, ``type``, ``line_count``, ``size_bytes``,
        ``encrypted``, ``outline`` (list of nested heading/symbol nodes).

    Errors:
        400 — missing ``path`` parameter
        404 — file not found or path escapes project root
    """
    rel_path = request.args.get("path", "").strip()
    if not rel_path:
        return jsonify({"error": "Missing 'path' parameter"}), 400

    resolved = resolve_safe_path(rel_path)
    if resolved is None:
        return jsonify({"error": "Invalid path"}), 404

    if not resolved.is_file():
        return jsonify({"error": "Not a file"}), 404

    from src.core.services.content.outline import extract_outline

    result = extract_outline(resolved)

    # Replace absolute path with relative for the response
    root = _project_root()
    try:
        result["path"] = str(resolved.relative_to(root))
    except ValueError:
        pass

    return jsonify(result)


# ── Folder glossary ─────────────────────────────────────────────────

@content_bp.route("/content/glossary", methods=["GET"])
def content_glossary():
    """Return the glossary tree for a folder or smart folder.

    Walks the folder, extracts outlines for every file, and returns a
    nested tree matching the directory structure.

    Query params:
        path (str):          Relative path to the folder.
        smart_folder (str):  Smart folder name — returns combined glossary
                             for all modules in the smart folder.
        recursive (str):     ``"true"`` (default) or ``"false"``.

    Returns:
        JSON with ``path``, ``total_files``, ``entries`` (nested tree).
        When smart_folder is used, entries are grouped by module with
        ``module`` and ``module_path`` fields on each group node.

    Errors:
        400 — missing both ``path`` and ``smart_folder`` parameters
        404 — folder/smart folder not found or path escapes project root
    """
    smart_folder_name = request.args.get("smart_folder", "").strip()
    rel_path = request.args.get("path", "").strip()

    recursive_str = request.args.get("recursive", "true").lower()
    recursive = recursive_str != "false"

    root = _project_root()

    # ── Smart folder mode: combined glossary for all modules ──
    if smart_folder_name:
        from src.core.services import smart_folders as sf
        from src.core.services.content.outline import extract_folder_glossary
        from src.core.services import config_ops

        cfg = config_ops.read_config(root).get("config", {})
        smart_list = cfg.get("smart_folders", [])
        modules_list = cfg.get("modules", [])

        folder = sf.find_smart_folder(smart_list, smart_folder_name)
        if folder is None:
            return jsonify({"error": f"Smart folder '{smart_folder_name}' not found"}), 404

        resolved = sf.resolve(root, folder, modules_list)
        groups = resolved.get("groups", [])

        combined_entries = []
        combined_total = 0

        for grp in groups:
            mod_path = grp.get("module_path", "")
            if not mod_path:
                continue
            mod_dir = root / mod_path
            if not mod_dir.is_dir():
                continue

            glossary = extract_folder_glossary(mod_dir, root, recursive=recursive)
            combined_total += glossary.get("total_files", 0)

            # Wrap this module's entries under a module group node
            combined_entries.append({
                "name": grp.get("module", mod_path),
                "path": mod_path,
                "is_dir": True,
                "module": grp.get("module", ""),
                "module_path": mod_path,
                "file_count": grp.get("file_count", 0),
                "children": glossary.get("entries", []),
            })

        return jsonify({
            "path": smart_folder_name,
            "smart_folder": smart_folder_name,
            "total_files": combined_total,
            "entries": combined_entries,
        })

    # ── Regular path mode ──
    if not rel_path:
        return jsonify({"error": "Missing 'path' or 'smart_folder' parameter"}), 400

    resolved = resolve_safe_path(rel_path)
    if resolved is None:
        return jsonify({"error": "Invalid path"}), 404

    if not resolved.is_dir():
        return jsonify({"error": "Not a directory"}), 404

    from src.core.services.content.outline import extract_folder_glossary

    result = extract_folder_glossary(resolved, root, recursive=recursive)

    return jsonify(result)
