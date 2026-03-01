"""Docs status — inventory, coverage, links."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services.docs_svc import ops as docs_ops
from src.ui.web.helpers import project_root as _project_root

from . import docs_bp


@docs_bp.route("/docs/status")
def docs_status():  # type: ignore[no-untyped-def]
    """Documentation inventory."""
    from src.core.services.devops.cache import get_cached

    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "docs",
        lambda: docs_ops.docs_status(root),
        force=force,
    ))


@docs_bp.route("/docs/coverage")
def docs_coverage():  # type: ignore[no-untyped-def]
    """Per-module documentation coverage."""
    return jsonify(docs_ops.docs_coverage(_project_root()))


@docs_bp.route("/docs/links")
def docs_links():  # type: ignore[no-untyped-def]
    """Check for broken internal links."""
    file_path = request.args.get("file")
    return jsonify(docs_ops.check_links(_project_root(), file_path=file_path))
