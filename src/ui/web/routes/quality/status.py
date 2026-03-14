"""Quality status — detected quality tools."""

from __future__ import annotations

from flask import jsonify, request

from . import quality_bp


@quality_bp.route("/quality/status")
def quality_status():  # type: ignore[no-untyped-def]
    """Detected quality tools and their availability."""
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("devops.quality", force=force)
    return jsonify(result["data"])
