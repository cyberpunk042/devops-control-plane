"""
Docker & Compose — detection, containers, generation, K8s bridge.

Sub-modules::

    common.py       — shared subprocess runners (run_docker, run_compose)
    detect.py       — compose parsing, environment probes, status
    containers.py   — container/image/network/volume ops, streaming actions
    generate.py     — Dockerfile, .dockerignore, compose generation
    k8s_bridge.py   — Docker → K8s service translation (pure data)

Public re-exports below keep ``from src.core.services.docker import X`` working.
The legacy ``docker_ops.py`` facade also re-exports from here for backward compat.
"""

from __future__ import annotations

# ── Shared runners ──
from .common import (  # noqa: F401
    run_docker,
    run_compose,
)

# ── Detect ──
from .detect import (  # noqa: F401
    find_compose_file,
    docker_status,
    _parse_compose_services,
    _parse_compose_service_details,
    _env_list_to_dict,
    _normalise_ports,
    _long_volume_to_str,
)

# ── Observe + Act (containers) ──
from .containers import (  # noqa: F401
    docker_action_stream,
    docker_containers,
    docker_images,
    docker_compose_status,
    docker_logs,
    docker_stats,
    docker_build,
    docker_up,
    docker_down,
    docker_restart,
    docker_prune,
    docker_networks,
    docker_volumes,
    docker_inspect,
    docker_pull,
    docker_exec_cmd,
    docker_rm,
    docker_rmi,
)

# ── Generate ──
from .generate import (  # noqa: F401
    generate_dockerfile,
    generate_dockerignore,
    generate_compose,
    generate_compose_from_wizard,
    write_generated_file,
)

# ── K8s bridge ──
from .k8s_bridge import (  # noqa: F401
    docker_to_k8s_services,
)
