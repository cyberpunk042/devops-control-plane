"""Docker detection — status endpoint."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import docker_ops
from src.ui.web.helpers import project_root as _project_root

from . import docker_bp


@docker_bp.route("/docker/status")
def docker_status():  # type: ignore[no-untyped-def]
    """Docker availability, version, daemon, project files."""
    from src.core.services.devops.cache import get_cached

    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "docker",
        lambda: docker_ops.docker_status(root),
        force=force,
    ))
