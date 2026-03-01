"""Docker actions — build, up, down, restart, prune, pull, exec, rm, rmi."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import docker_ops
from src.core.services.run_tracker import run_tracked
from src.ui.web.helpers import project_root as _project_root

from . import docker_bp


@docker_bp.route("/docker/build", methods=["POST"])
@run_tracked("build", "build:docker")
def docker_build():  # type: ignore[no-untyped-def]
    """Build images via compose."""
    data = request.get_json(silent=True) or {}
    service = data.get("service")
    no_cache = data.get("no_cache", False)
    root = _project_root()

    result = docker_ops.docker_build(root, service=service, no_cache=no_cache)

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@docker_bp.route("/docker/up", methods=["POST"])
@run_tracked("deploy", "deploy:docker_up")
def docker_up():  # type: ignore[no-untyped-def]
    """Start compose services."""
    data = request.get_json(silent=True) or {}
    service = data.get("service")
    root = _project_root()

    result = docker_ops.docker_up(root, service=service)

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@docker_bp.route("/docker/down", methods=["POST"])
@run_tracked("destroy", "destroy:docker_down")
def docker_down():  # type: ignore[no-untyped-def]
    """Stop compose services."""
    data = request.get_json(silent=True) or {}
    volumes = data.get("volumes", False)
    root = _project_root()

    result = docker_ops.docker_down(root, volumes=volumes)

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@docker_bp.route("/docker/restart", methods=["POST"])
@run_tracked("deploy", "deploy:docker_restart")
def docker_restart():  # type: ignore[no-untyped-def]
    """Restart compose services."""
    data = request.get_json(silent=True) or {}
    service = data.get("service")
    root = _project_root()

    result = docker_ops.docker_restart(root, service=service)

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@docker_bp.route("/docker/prune", methods=["POST"])
@run_tracked("destroy", "destroy:docker_prune")
def docker_prune():  # type: ignore[no-untyped-def]
    """Remove unused Docker resources."""
    root = _project_root()
    result = docker_ops.docker_prune(root)

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@docker_bp.route("/docker/pull", methods=["POST"])
@run_tracked("install", "install:docker_pull")
def docker_pull():  # type: ignore[no-untyped-def]
    """Pull a Docker image."""
    data = request.get_json(silent=True) or {}
    image = data.get("image", "")
    if not image:
        return jsonify({"error": "Missing 'image' field"}), 400
    root = _project_root()
    result = docker_ops.docker_pull(root, image)
    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@docker_bp.route("/docker/exec", methods=["POST"])
@run_tracked("test", "test:docker_exec")
def docker_exec():  # type: ignore[no-untyped-def]
    """Execute a command in a running container."""
    data = request.get_json(silent=True) or {}
    container = data.get("container", "")
    command = data.get("command", "")
    if not container:
        return jsonify({"error": "Missing 'container' field"}), 400
    if not command:
        return jsonify({"error": "Missing 'command' field"}), 400
    root = _project_root()
    result = docker_ops.docker_exec_cmd(root, container, command)
    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@docker_bp.route("/docker/rm", methods=["POST"])
@run_tracked("destroy", "destroy:docker_rm")
def docker_rm():  # type: ignore[no-untyped-def]
    """Remove a Docker container."""
    data = request.get_json(silent=True) or {}
    container = data.get("container", "")
    if not container:
        return jsonify({"error": "Missing 'container' field"}), 400
    force = data.get("force", False)
    root = _project_root()
    result = docker_ops.docker_rm(root, container, force=force)
    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@docker_bp.route("/docker/rmi", methods=["POST"])
@run_tracked("destroy", "destroy:docker_rmi")
def docker_rmi():  # type: ignore[no-untyped-def]
    """Remove a Docker image."""
    data = request.get_json(silent=True) or {}
    image = data.get("image", "")
    if not image:
        return jsonify({"error": "Missing 'image' field"}), 400
    force = data.get("force", False)
    root = _project_root()
    result = docker_ops.docker_rmi(root, image, force=force)
    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)
