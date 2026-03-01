"""Quality status — detected quality tools."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services.quality import ops as quality_ops
from src.ui.web.helpers import project_root as _project_root, get_stack_names as _get_stack_names

from . import quality_bp


@quality_bp.route("/quality/status")
def quality_status():  # type: ignore[no-untyped-def]
    """Detected quality tools and their availability."""
    from src.core.services.devops.cache import get_cached

    root = _project_root()
    force = request.args.get("bust", "") == "1"

    def _compute() -> dict:
        stack_names = _get_stack_names()
        return quality_ops.quality_status(root, stack_names=stack_names)

    return jsonify(get_cached(root, "quality", _compute, force=force))
