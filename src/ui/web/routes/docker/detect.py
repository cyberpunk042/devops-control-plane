"""Docker detection — status endpoint."""

from __future__ import annotations

from flask import jsonify, request

from . import docker_bp


@docker_bp.route("/docker/status")
def docker_status():  # type: ignore[no-untyped-def]
    """Docker availability, version, daemon, project files."""
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("devops.docker", force=force)
    return jsonify(result["data"])
