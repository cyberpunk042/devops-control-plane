"""
Docker → K8s bridge — cross-domain wiring (Layer 1.1b).

Reads docker_status() output and produces K8s-ready service definitions
that can be fed into wizard_state_to_resources() or generate_manifests().

This is pure data transformation — no I/O, no subprocess calls.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def docker_to_k8s_services(docker_status: dict) -> list[dict]:
    """Translate Docker detection output into K8s service definitions.

    Reads compose_service_details (preferred) or dockerfile_details
    and returns a list of dicts, each suitable as a wizard ``_services``
    entry::

        {
            "name": str,
            "image": str,
            "port": int | None,
            "kind": "Deployment",
            "build_args": dict | None,  # from compose build.args
        }

    Priority:
        1. Compose services (name, image, ports, build.args)
        2. Dockerfile (ports from EXPOSE, image = project:latest)
    """
    services: list[dict] = []

    compose_details = docker_status.get("compose_service_details", [])
    if compose_details:
        services = _from_compose(compose_details)
    elif docker_status.get("dockerfile_details"):
        services = _from_dockerfiles(docker_status["dockerfile_details"])

    return services


def _from_compose(compose_details: list[dict]) -> list[dict]:
    """Build K8s service defs from compose service details."""
    services: list[dict] = []

    for svc in compose_details:
        name = svc.get("name", "")
        if not name:
            continue

        # Image: explicit → build-derived → fallback
        image = svc.get("image") or ""
        build_info = svc.get("build")

        if not image:
            # If compose has build context but no image tag → {name}:latest
            if build_info:
                image = f"{name}:latest"
            else:
                image = f"{name}:latest"

        # Port: first container port from normalised ports list
        port = None
        ports = svc.get("ports", [])
        if ports and isinstance(ports, list):
            first = ports[0]
            if isinstance(first, dict):
                port = first.get("container")
            elif isinstance(first, (int, str)):
                # raw "3000:3000" shouldn't happen (normalised), but fallback
                try:
                    port = int(str(first).split(":")[-1].split("/")[0])
                except (ValueError, IndexError):
                    pass

        # Build args
        build_args = None
        if build_info and isinstance(build_info, dict):
            args = build_info.get("args")
            if args and isinstance(args, dict):
                build_args = dict(args)

        entry: dict[str, Any] = {
            "name": name,
            "image": image,
            "port": port,
            "kind": "Deployment",
        }
        if build_args:
            entry["build_args"] = build_args

        services.append(entry)

    return services


def _from_dockerfiles(dockerfile_details: list[dict]) -> list[dict]:
    """Build K8s service defs from Dockerfile parsing results.

    With only a Dockerfile (no compose), we can only extract ports.
    The image name defaults to the Dockerfile directory name or "app".
    """
    services: list[dict] = []

    for df in dockerfile_details:
        path_str = df.get("path", "Dockerfile")

        # Derive a name from the path
        # "Dockerfile" → "app", "services/api/Dockerfile" → "api"
        parts = path_str.replace("\\", "/").split("/")
        if len(parts) >= 2:
            name = parts[-2]  # parent directory
        else:
            name = "app"

        # Port: last EXPOSE port (closest to final stage)
        ports = df.get("ports", [])
        port = ports[-1] if ports else None

        services.append({
            "name": name,
            "image": f"{name}:latest",
            "port": port,
            "kind": "Deployment",
        })

    return services
