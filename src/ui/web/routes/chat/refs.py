"""Chat @-reference resolution and autocomplete."""

from __future__ import annotations

import logging

from flask import jsonify, request

from src.core.services.chat import autocomplete, resolve_ref
from src.ui.web.helpers import project_root as _project_root

from . import chat_bp

logger = logging.getLogger(__name__)


@chat_bp.route("/chat/refs/resolve")
def chat_resolve_ref():
    """Resolve an @-reference to entity metadata.

    Query params:
        ref — reference string, e.g. "@run:run_20260217_detect_a1b2"
    """
    try:
        root = _project_root()
        ref = request.args.get("ref", "")
        if not ref:
            return jsonify({"error": "ref parameter is required"}), 400

        result = resolve_ref(ref, root)
        if result is None:
            return jsonify({"error": "not_found", "ref": ref}), 404

        return jsonify(result)
    except Exception as e:
        logger.exception("Failed to resolve ref")
        return jsonify({"error": str(e)}), 500


@chat_bp.route("/chat/refs/autocomplete")
def chat_autocomplete():
    """Autocomplete @-reference prefix.

    Query params:
        prefix — partial reference, e.g. "@run:", "@run:run_2026"
    """
    try:
        root = _project_root()
        prefix = request.args.get("prefix", "")
        if not prefix:
            return jsonify({"suggestions": []})

        results = autocomplete(prefix, root)
        return jsonify({"suggestions": results})
    except Exception as e:
        logger.exception("Failed to autocomplete ref")
        return jsonify({"error": str(e), "suggestions": []}), 500
