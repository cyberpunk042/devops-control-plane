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
from src.core.services.run_tracker import run_tracked

docker_bp = Blueprint("docker", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


# ── Detect ──────────────────────────────────────────────────────────


@docker_bp.route("/docker/status")
def docker_status():  # type: ignore[no-untyped-def]
    """Docker availability, version, daemon, project files."""
    from src.core.services.devops_cache import get_cached

    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "docker",
        lambda: docker_ops.docker_status(root),
        force=force,
    ))


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


# ── Facilitate (generate) ───────────────────────────────────────────


@docker_bp.route("/docker/generate/dockerfile", methods=["POST"])
@run_tracked("generate", "generate:dockerfile")
def generate_dockerfile():  # type: ignore[no-untyped-def]
    """Generate a Dockerfile for a given stack."""
    data = request.get_json(silent=True) or {}
    stack_name = data.get("stack", "")
    if not stack_name:
        return jsonify({"error": "Missing 'stack' field"}), 400

    base_image = data.get("base_image") or None
    root = _project_root()
    result = docker_ops.generate_dockerfile(root, stack_name, base_image=base_image)

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@docker_bp.route("/docker/generate/dockerignore", methods=["POST"])
@run_tracked("generate", "generate:dockerignore")
def generate_dockerignore():  # type: ignore[no-untyped-def]
    """Generate a .dockerignore for given stacks."""
    data = request.get_json(silent=True) or {}
    stacks = data.get("stacks", [])
    if not stacks:
        return jsonify({"error": "Missing 'stacks' field (list of stack names)"}), 400

    root = _project_root()
    result = docker_ops.generate_dockerignore(root, stacks)

    return jsonify(result)


@docker_bp.route("/docker/generate/compose", methods=["POST"])
@run_tracked("generate", "generate:compose")
def generate_compose():  # type: ignore[no-untyped-def]
    """Generate a docker-compose.yml from detected modules."""
    root = _project_root()
    result = docker_ops.generate_compose(root)

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@docker_bp.route("/docker/generate/compose-wizard", methods=["POST"])
@run_tracked("generate", "generate:compose_wizard")
def generate_compose_wizard():  # type: ignore[no-untyped-def]
    """Generate docker-compose.yml from custom service definitions.

    JSON body:
        project_name: optional project name
        services: list of service definitions, each with:
            name: service name (required)
            image: Docker image (optional, uses build if empty)
            build_context: build context path (optional)
            dockerfile: Dockerfile path (optional)
            ports: list of "host:container" port mappings
            volumes: list of "host:container" volume mounts
            environment: dict of env vars {KEY: value}
            depends_on: list of service names this depends on
            restart: restart policy (default: unless-stopped)
            command: custom command (optional)
            networks: list of network names (optional)
    """
    data = request.get_json(silent=True) or {}
    services = data.get("services", [])
    if not services:
        return jsonify({"error": "At least one service is required"}), 400

    root = _project_root()

    result = docker_ops.generate_compose_from_wizard(
        root,
        services,
        project_name=data.get("project_name", ""),
    )

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@docker_bp.route("/docker/generate/write", methods=["POST"])
@run_tracked("generate", "generate:docker_write")
def write_generated():  # type: ignore[no-untyped-def]
    """Write a generated file to disk."""
    data = request.get_json(silent=True) or {}
    file_data = data.get("file")
    if not file_data:
        return jsonify({"error": "Missing 'file' field"}), 400

    root = _project_root()
    result = docker_ops.write_generated_file(root, file_data)

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


# ── Extended Observe ────────────────────────────────────────────────


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


# ── Extended Act ────────────────────────────────────────────────────


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
