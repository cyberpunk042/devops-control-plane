"""
Project Status API — unified integration status for the connected journey.

Blueprint: project_bp
Prefix: /api

Thin HTTP wrappers over ``src.core.services.project_probes``.

Endpoints:
    GET  /project/status  — complete integration state
    GET  /project/next    — suggested next integration to configure
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

project_bp = Blueprint("project", __name__)


@project_bp.route("/project/status")
def project_status():  # type: ignore[no-untyped-def]
    """Complete integration status for all cards."""
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("devops.status", force=force)
    return jsonify(result["data"])


@project_bp.route("/project/next")
def project_next():  # type: ignore[no-untyped-def]
    """Suggest just the next integration to configure."""
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("devops.status", force=force)
    return jsonify(result["data"])

