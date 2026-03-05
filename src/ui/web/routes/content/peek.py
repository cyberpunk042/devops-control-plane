"""
Admin API — Peek resolution endpoints.

Blueprint: content_bp (imported from routes_content)
Prefix: /api
Routes:
    GET  /api/content/peek-refs     — instant lookup from passive project index
    POST /api/content/peek-resolve  — on-demand scan + resolve (legacy/fallback)
"""

from __future__ import annotations

import logging

from flask import jsonify, request

from . import content_bp
from .helpers import project_root as _project_root

logger = logging.getLogger(__name__)


# ── Peek refs (instant, index-backed) ───────────────────────────────

@content_bp.route("/content/peek-refs", methods=["GET"])
def peek_refs():  # type: ignore[no-untyped-def]
    """Look up pre-computed peek references from the passive project index.

    Query parameters:
        path:  Relative path of the document being viewed
               (e.g. "src/core/services/audit/README.md")

    Returns:
        JSON with resolved + unresolved references if cached.
        Falls back to on-demand resolution if index not ready.
    """
    doc_path = request.args.get("path", "").strip()
    if not doc_path:
        return jsonify({"references": [], "unresolved": []})

    # Try the passive project index first (instant, zero I/O)
    try:
        from src.core.services.project_index import get_index
        idx = get_index()
        if idx.peek_cached and doc_path in idx.peek_cache:
            cached = idx.peek_cache[doc_path]
            return jsonify({
                "references": cached.get("resolved", []),
                "unresolved": cached.get("unresolved", []),
                "pending": [],
                "symbols_ready": idx.symbols_ready,
                "_source": "index",
            })
    except ImportError:
        pass

    # Fallback: on-demand resolution (reads file from disk)
    root = _project_root()
    file_path = root / doc_path

    if not file_path.is_file():
        return jsonify({"references": [], "unresolved": []})

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return jsonify({"references": [], "unresolved": []})

    from src.core.services.peek import scan_and_resolve_all, build_symbol_index

    try:
        # block=False: NEVER trigger the 23-second AST parse in a
        # request handler. Returns {} if symbols aren't ready yet —
        # T5 references are simply skipped until background build finishes.
        sym_idx = build_symbol_index(root, block=False) or None
        symbols_ready = sym_idx is not None
        refs, unresolved, pending = scan_and_resolve_all(content, doc_path, root, sym_idx)
    except Exception as e:
        logger.warning("Peek refs fallback failed for %s: %s", doc_path, e)
        return jsonify({"references": [], "unresolved": [], "pending": [], "symbols_ready": False, "error": str(e)})

    return jsonify({
        "references": [
            {
                "text": r.text,
                "type": r.type,
                "resolved_path": r.resolved_path,
                "line_number": r.line_number,
                "is_directory": r.is_directory,
            }
            for r in refs
        ],
        "unresolved": [
            {
                "text": u.text,
                "type": u.type,
            }
            for u in unresolved
        ],
        "pending": [
            {
                "text": p.text,
                "type": p.type,
            }
            for p in pending
        ],
        "symbols_ready": symbols_ready,
        "_source": "on-demand",
    })


# ── Peek resolve (legacy POST, kept for backward compat) ───────────

@content_bp.route("/content/peek-resolve", methods=["POST"])
def peek_resolve():  # type: ignore[no-untyped-def]
    """Scan a document for file references and resolve against filesystem.

    LEGACY: prefer GET /api/content/peek-refs?path=... for instant results.

    Request body (JSON):
        doc_path:  Relative path of the document being viewed
                   (e.g. "src/core/services/audit/README.md")
        content:   Raw markdown content of the document

    Returns:
        JSON with resolved references list, each containing:
            text, type, resolved_path, line_number, is_directory
    """
    from src.core.services.peek import scan_and_resolve_all, build_symbol_index

    data = request.get_json(silent=True) or {}
    doc_path = data.get("doc_path", "").strip()
    content = data.get("content", "")

    if not doc_path or not content:
        return jsonify({"references": [], "unresolved": []})

    root = _project_root()

    try:
        # block=False: NEVER trigger the 23-second AST parse in a
        # request handler. The background project index thread handles it.
        sym_idx = build_symbol_index(root, block=False) or None
        refs, unresolved, pending = scan_and_resolve_all(content, doc_path, root, sym_idx)
    except Exception as e:
        logger.warning("Peek resolve failed for %s: %s", doc_path, e)
        return jsonify({"references": [], "unresolved": [], "pending": [], "error": str(e)})

    return jsonify({
        "references": [
            {
                "text": r.text,
                "type": r.type,
                "resolved_path": r.resolved_path,
                "line_number": r.line_number,
                "is_directory": r.is_directory,
            }
            for r in refs
        ],
        "unresolved": [
            {
                "text": u.text,
                "type": u.type,
            }
            for u in unresolved
        ],
        "pending": [
            {
                "text": p.text,
                "type": p.type,
            }
            for p in pending
        ],
    })
