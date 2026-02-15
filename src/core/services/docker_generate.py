"""Docker config generation — Dockerfile, .dockerignore, compose."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

def generate_dockerfile(project_root: Path, stack_name: str) -> dict:
    """Generate a Dockerfile for the given stack.

    Returns:
        {"ok": True, "file": {...}} or {"error": "..."}
    """
    from src.core.services.generators.dockerfile import generate_dockerfile as _gen

    result = _gen(project_root, stack_name)
    if result is None:
        from src.core.services.generators.dockerfile import supported_stacks

        return {
            "error": f"No Dockerfile template for stack '{stack_name}'",
            "supported": supported_stacks(),
        }

    return {"ok": True, "file": result.model_dump()}


def generate_dockerignore(project_root: Path, stack_names: list[str]) -> dict:
    """Generate a .dockerignore for the given stacks.

    Returns:
        {"ok": True, "file": {...}}
    """
    from src.core.services.generators.dockerignore import generate_dockerignore as _gen

    result = _gen(project_root, stack_names)
    return {"ok": True, "file": result.model_dump()}


def generate_compose(
    project_root: Path,
    modules: list[dict],
    *,
    project_name: str = "",
) -> dict:
    """Generate a docker-compose.yml from detected modules.

    Returns:
        {"ok": True, "file": {...}} or {"error": "..."}
    """
    from src.core.services.generators.compose import generate_compose as _gen

    result = _gen(project_root, modules, project_name=project_name)
    if result is None:
        return {"error": "No eligible modules for compose generation"}

    return {"ok": True, "file": result.model_dump()}


def generate_compose_from_wizard(
    project_root: Path,
    services: list[dict],
    *,
    project_name: str = "",
) -> dict:
    """Generate a docker-compose.yml from user-defined service specifications.

    Args:
        project_root: Project root directory.
        services: List of service dicts with:
            name, image, build_context, dockerfile, ports, volumes,
            environment, depends_on, restart, command, networks.
        project_name: Optional project name for compose.

    Returns:
        {"ok": True, "file": {...}} or {"error": "..."}
    """
    from src.core.models.template import GeneratedFile

    if not services:
        return {"error": "At least one service is required"}

    import yaml

    compose: dict = {"services": {}}
    if project_name:
        compose["name"] = project_name

    all_networks: set[str] = set()

    for svc in services:
        name = (svc.get("name") or "").strip()
        if not name:
            continue

        spec: dict = {}

        # Image vs build
        image = (svc.get("image") or "").strip()
        build_ctx = (svc.get("build_context") or "").strip()
        dockerfile = (svc.get("dockerfile") or "").strip()

        if image and not build_ctx:
            spec["image"] = image
        elif build_ctx:
            build_def: dict = {"context": build_ctx}
            if dockerfile:
                build_def["dockerfile"] = dockerfile
            spec["build"] = build_def
            if image:
                spec["image"] = image
        elif not image and not build_ctx:
            spec["image"] = name  # fallback

        # Ports
        ports = svc.get("ports", [])
        if ports:
            spec["ports"] = [str(p) for p in ports if p]

        # Volumes
        volumes = svc.get("volumes", [])
        if volumes:
            spec["volumes"] = [str(v) for v in volumes if v]

        # Environment
        env = svc.get("environment", {})
        if isinstance(env, dict) and env:
            spec["environment"] = {k: str(v) for k, v in env.items()}
        elif isinstance(env, list) and env:
            spec["environment"] = [str(e) for e in env if e]

        # Depends on
        deps = svc.get("depends_on", [])
        if deps:
            spec["depends_on"] = [str(d) for d in deps if d]

        # Restart
        restart = (svc.get("restart") or "unless-stopped").strip()
        if restart:
            spec["restart"] = restart

        # Command
        command = (svc.get("command") or "").strip()
        if command:
            spec["command"] = command

        # Networks
        networks = svc.get("networks", [])
        if networks:
            spec["networks"] = [str(n) for n in networks if n]
            all_networks.update(n for n in networks if n)

        # Container name
        container_name = (svc.get("container_name") or "").strip()
        if container_name:
            spec["container_name"] = container_name

        # Health check
        healthcheck = svc.get("healthcheck")
        if isinstance(healthcheck, dict) and healthcheck:
            spec["healthcheck"] = healthcheck

        # Build args
        build_args = svc.get("build_args")
        if isinstance(build_args, dict) and build_args:
            if "build" in spec and isinstance(spec["build"], dict):
                spec["build"]["args"] = {k: str(v) for k, v in build_args.items()}
            elif "build" in spec:
                spec["build"] = {"context": spec["build"], "args": {k: str(v) for k, v in build_args.items()}}

        # Platform
        platform = (svc.get("platform") or "").strip()
        if platform:
            spec["platform"] = platform

        compose["services"][name] = spec

    # Add top-level networks if any
    if all_networks:
        compose["networks"] = {n: {} for n in sorted(all_networks)}

    content = "# Generated by DevOps Control Plane — Compose Wizard\n"
    content += yaml.dump(
        compose,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )

    file_data = GeneratedFile(
        path="docker-compose.yml",
        content=content,
        overwrite=False,
        reason=f"Compose wizard: {len(compose['services'])} service(s)",
    )

    return {"ok": True, "file": file_data.model_dump()}


def write_generated_file(project_root: Path, file_data: dict) -> dict:
    """Write a GeneratedFile to disk.

    Args:
        project_root: Project root directory.
        file_data: Dict with 'path', 'content', 'overwrite'.

    Returns:
        {"ok": True, "path": "...", "written": True} or {"error": "..."}
    """
    rel_path = file_data.get("path", "")
    content = file_data.get("content", "")
    overwrite = file_data.get("overwrite", False)

    if not rel_path or not content:
        return {"error": "Missing path or content"}

    target = project_root / rel_path

    if target.exists() and not overwrite:
        return {
            "error": f"File already exists: {rel_path} (use overwrite=true to replace)",
            "path": rel_path,
            "written": False,
        }

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    logger.info("Wrote generated file: %s", target)

    return {"ok": True, "path": rel_path, "written": True}

