"""Docker observation — containers, images, compose, logs, stats, networks, volumes, inspect."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import docker_ops
from src.ui.web.helpers import project_root as _project_root

from . import docker_bp


@docker_bp.route("/docker/containers")
def docker_containers():  # type: ignore[no-untyped-def]
    """List Docker containers."""
    all_ = request.args.get("all", "true").lower() in ("true", "1", "yes")
    return jsonify(docker_ops.docker_containers(_project_root(), all_=all_))


@docker_bp.route("/docker/images")
def docker_images():  # type: ignore[no-untyped-def]
    """List local Docker images."""
    return jsonify(docker_ops.docker_images(_project_root()))


@docker_bp.route("/docker/compose/status")
def docker_compose_status():  # type: ignore[no-untyped-def]
    """Compose service status."""
    return jsonify(docker_ops.docker_compose_status(_project_root()))


@docker_bp.route("/docker/logs")
def docker_logs():  # type: ignore[no-untyped-def]
    """Logs for a compose service."""
    service = request.args.get("service", "")
    if not service:
        return jsonify({"error": "Missing 'service' parameter"}), 400

    tail = request.args.get("tail", 100, type=int)
    result = docker_ops.docker_logs(_project_root(), service, tail=tail)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@docker_bp.route("/docker/stats")
def docker_stats():  # type: ignore[no-untyped-def]
    """Container resource usage."""
    return jsonify(docker_ops.docker_stats(_project_root()))


@docker_bp.route("/docker/networks")
def docker_networks():  # type: ignore[no-untyped-def]
    """List Docker networks."""
    return jsonify(docker_ops.docker_networks(_project_root()))


@docker_bp.route("/docker/volumes")
def docker_volumes():  # type: ignore[no-untyped-def]
    """List Docker volumes."""
    return jsonify(docker_ops.docker_volumes(_project_root()))


@docker_bp.route("/docker/inspect")
def docker_inspect():  # type: ignore[no-untyped-def]
    """Inspect a Docker container."""
    container = request.args.get("id", "")
    if not container:
        return jsonify({"error": "Missing 'id' parameter"}), 400
    result = docker_ops.docker_inspect(_project_root(), container)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)
