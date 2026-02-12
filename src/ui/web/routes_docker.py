"""
Docker routes — container and compose management endpoints.

Blueprint: docker_bp
Prefix: /api

Thin HTTP wrappers over ``src.core.services.docker_ops``.

Endpoints:
    GET  /docker/status          — Docker availability, version, project files
    GET  /docker/containers      — list containers
    GET  /docker/images          — list images
    GET  /docker/compose/status  — compose service status
    GET  /docker/logs?service=   — logs for a compose service
    GET  /docker/stats           — container resource usage
    POST /docker/build           — build images via compose
    POST /docker/up              — start compose services
    POST /docker/down            — stop compose services
    POST /docker/restart         — restart compose services
    POST /docker/prune           — remove unused resources
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import docker_ops

docker_bp = Blueprint("docker", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


# ── Detect ──────────────────────────────────────────────────────────


@docker_bp.route("/docker/status")
def docker_status():  # type: ignore[no-untyped-def]
    """Docker availability, version, daemon, project files."""
    return jsonify(docker_ops.docker_status(_project_root()))


# ── Observe ─────────────────────────────────────────────────────────


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


# ── Act ─────────────────────────────────────────────────────────────


@docker_bp.route("/docker/build", methods=["POST"])
def docker_build():  # type: ignore[no-untyped-def]
    """Build images via compose."""
    data = request.get_json(silent=True) or {}
    service = data.get("service")

    result = docker_ops.docker_build(_project_root(), service=service)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@docker_bp.route("/docker/up", methods=["POST"])
def docker_up():  # type: ignore[no-untyped-def]
    """Start compose services."""
    data = request.get_json(silent=True) or {}
    service = data.get("service")

    result = docker_ops.docker_up(_project_root(), service=service)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@docker_bp.route("/docker/down", methods=["POST"])
def docker_down():  # type: ignore[no-untyped-def]
    """Stop compose services."""
    data = request.get_json(silent=True) or {}
    volumes = data.get("volumes", False)

    result = docker_ops.docker_down(_project_root(), volumes=volumes)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@docker_bp.route("/docker/restart", methods=["POST"])
def docker_restart():  # type: ignore[no-untyped-def]
    """Restart compose services."""
    data = request.get_json(silent=True) or {}
    service = data.get("service")

    result = docker_ops.docker_restart(_project_root(), service=service)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@docker_bp.route("/docker/prune", methods=["POST"])
def docker_prune():  # type: ignore[no-untyped-def]
    """Remove unused Docker resources."""
    result = docker_ops.docker_prune(_project_root())

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── Facilitate (generate) ───────────────────────────────────────────


@docker_bp.route("/docker/generate/dockerfile", methods=["POST"])
def generate_dockerfile():  # type: ignore[no-untyped-def]
    """Generate a Dockerfile for a given stack."""
    data = request.get_json(silent=True) or {}
    stack_name = data.get("stack", "")
    if not stack_name:
        return jsonify({"error": "Missing 'stack' field"}), 400

    result = docker_ops.generate_dockerfile(_project_root(), stack_name)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@docker_bp.route("/docker/generate/dockerignore", methods=["POST"])
def generate_dockerignore():  # type: ignore[no-untyped-def]
    """Generate a .dockerignore for given stacks."""
    data = request.get_json(silent=True) or {}
    stacks = data.get("stacks", [])
    if not stacks:
        return jsonify({"error": "Missing 'stacks' field (list of stack names)"}), 400

    result = docker_ops.generate_dockerignore(_project_root(), stacks)
    return jsonify(result)


@docker_bp.route("/docker/generate/compose", methods=["POST"])
def generate_compose():  # type: ignore[no-untyped-def]
    """Generate a docker-compose.yml from detected modules."""
    data = request.get_json(silent=True) or {}

    from src.core.config.loader import load_project
    from src.core.config.stack_loader import discover_stacks
    from src.core.services.detection import detect_modules

    root = _project_root()
    config_path = root / "project.yml"
    project = load_project(config_path)
    stacks = discover_stacks(root / "stacks")
    detection = detect_modules(project, root, stacks)
    modules = [m.model_dump() for m in detection.modules]

    result = docker_ops.generate_compose(root, modules, project_name=project.name)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@docker_bp.route("/docker/generate/write", methods=["POST"])
def write_generated():  # type: ignore[no-untyped-def]
    """Write a generated file to disk."""
    data = request.get_json(silent=True) or {}
    file_data = data.get("file")
    if not file_data:
        return jsonify({"error": "Missing 'file' field"}), 400

    result = docker_ops.write_generated_file(_project_root(), file_data)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)
