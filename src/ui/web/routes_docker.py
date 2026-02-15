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

from src.core.services import docker_ops, devops_cache

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
    no_cache = data.get("no_cache", False)
    root = _project_root()

    result = docker_ops.docker_build(root, service=service, no_cache=no_cache)

    if "error" in result:
        return jsonify(result), 400

    devops_cache.record_event(
        root,
        label="📦 Docker Build",
        summary=f"Image built" + (f" for {service}" if service else "") + (" (no-cache)" if no_cache else ""),
        detail={"service": service, "no_cache": no_cache},
        card="docker",
    )
    return jsonify(result)


@docker_bp.route("/docker/up", methods=["POST"])
def docker_up():  # type: ignore[no-untyped-def]
    """Start compose services."""
    data = request.get_json(silent=True) or {}
    service = data.get("service")
    root = _project_root()

    result = docker_ops.docker_up(root, service=service)

    if "error" in result:
        return jsonify(result), 400

    devops_cache.record_event(
        root,
        label="▶️ Docker Up",
        summary=f"Compose services started" + (f" ({service})" if service else ""),
        detail={"service": service},
        card="docker",
    )
    return jsonify(result)


@docker_bp.route("/docker/down", methods=["POST"])
def docker_down():  # type: ignore[no-untyped-def]
    """Stop compose services."""
    data = request.get_json(silent=True) or {}
    volumes = data.get("volumes", False)
    root = _project_root()

    result = docker_ops.docker_down(root, volumes=volumes)

    if "error" in result:
        return jsonify(result), 400

    devops_cache.record_event(
        root,
        label="⏹️ Docker Down",
        summary=f"Compose services stopped" + (" (volumes removed)" if volumes else ""),
        detail={"volumes": volumes},
        card="docker",
    )
    return jsonify(result)


@docker_bp.route("/docker/restart", methods=["POST"])
def docker_restart():  # type: ignore[no-untyped-def]
    """Restart compose services."""
    data = request.get_json(silent=True) or {}
    service = data.get("service")
    root = _project_root()

    result = docker_ops.docker_restart(root, service=service)

    if "error" in result:
        return jsonify(result), 400

    devops_cache.record_event(
        root,
        label="🔄 Docker Restart",
        summary=f"Compose services restarted" + (f" ({service})" if service else ""),
        detail={"service": service},
        card="docker",
    )
    return jsonify(result)


@docker_bp.route("/docker/prune", methods=["POST"])
def docker_prune():  # type: ignore[no-untyped-def]
    """Remove unused Docker resources."""
    root = _project_root()
    result = docker_ops.docker_prune(root)

    if "error" in result:
        return jsonify(result), 400

    devops_cache.record_event(
        root,
        label="🧹 Docker Prune",
        summary="Unused Docker resources cleaned up",
        detail={},
        card="docker",
    )
    return jsonify(result)


# ── Facilitate (generate) ───────────────────────────────────────────


@docker_bp.route("/docker/generate/dockerfile", methods=["POST"])
def generate_dockerfile():  # type: ignore[no-untyped-def]
    """Generate a Dockerfile for a given stack."""
    data = request.get_json(silent=True) or {}
    stack_name = data.get("stack", "")
    if not stack_name:
        return jsonify({"error": "Missing 'stack' field"}), 400

    root = _project_root()
    result = docker_ops.generate_dockerfile(root, stack_name)

    if "error" in result:
        return jsonify(result), 400

    devops_cache.record_event(
        root,
        label="📝 Dockerfile Generated",
        summary=f"Dockerfile generated for {stack_name} stack",
        detail={"stack": stack_name},
        card="docker",
    )
    return jsonify(result)


@docker_bp.route("/docker/generate/dockerignore", methods=["POST"])
def generate_dockerignore():  # type: ignore[no-untyped-def]
    """Generate a .dockerignore for given stacks."""
    data = request.get_json(silent=True) or {}
    stacks = data.get("stacks", [])
    if not stacks:
        return jsonify({"error": "Missing 'stacks' field (list of stack names)"}), 400

    root = _project_root()
    result = docker_ops.generate_dockerignore(root, stacks)

    devops_cache.record_event(
        root,
        label="📝 .dockerignore Generated",
        summary=f".dockerignore generated for {len(stacks)} stack(s)",
        detail={"stacks": stacks},
        card="docker",
    )
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

    devops_cache.record_event(
        root,
        label="📝 Compose Generated",
        summary=f"docker-compose.yml generated ({len(modules)} module(s))",
        detail={"modules": len(modules), "project": project.name},
        card="docker",
    )
    return jsonify(result)


@docker_bp.route("/docker/generate/compose-wizard", methods=["POST"])
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

    devops_cache.record_event(
        root,
        label="📝 Compose Wizard Generated",
        summary=f"docker-compose.yml generated from wizard ({len(services)} service(s))",
        detail={"services_count": len(services)},
        card="docker",
    )
    return jsonify(result)


@docker_bp.route("/docker/generate/write", methods=["POST"])
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

    devops_cache.record_event(
        root,
        label="💾 Docker File Written",
        summary=f"Generated file written: {file_data.get('path', '?')}",
        detail={"file": file_data.get("path", "?")},
        card="docker",
    )
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

    devops_cache.record_event(
        root,
        label="⬇️ Docker Pull",
        summary=f"Image pulled: {image}",
        detail={"image": image},
        card="docker",
    )
    return jsonify(result)


@docker_bp.route("/docker/exec", methods=["POST"])
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

    devops_cache.record_event(
        root,
        label="▶️ Docker Exec",
        summary=f"Command executed in {container}",
        detail={"container": container, "command": command},
        card="docker",
    )
    return jsonify(result)


@docker_bp.route("/docker/rm", methods=["POST"])
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

    devops_cache.record_event(
        root,
        label="🗑️ Container Removed",
        summary=f"Container '{container}' removed" + (" (forced)" if force else ""),
        detail={"container": container, "force": force},
        card="docker",
    )
    return jsonify(result)


@docker_bp.route("/docker/rmi", methods=["POST"])
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

    devops_cache.record_event(
        root,
        label="🗑️ Image Removed",
        summary=f"Image '{image}' removed" + (" (forced)" if force else ""),
        detail={"image": image, "force": force},
        card="docker",
    )
    return jsonify(result)
