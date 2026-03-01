"""Docker generation — dockerfile, dockerignore, compose, compose-wizard, write."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import docker_ops
from src.core.services.run_tracker import run_tracked
from src.ui.web.helpers import project_root as _project_root

from . import docker_bp


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
