"""
Docker & Compose operations — backward-compat re-export hub.

Shared runners live in ``docker_common``.
Feature code lives in ``docker_detect``, ``docker_containers``,
and ``docker_generate``.
"""

from __future__ import annotations

# ── Shared runners ──
from src.core.services.docker_common import (  # noqa: F401
    run_docker,
    run_compose,
)

# ── Detect ──
from src.core.services.docker_detect import (  # noqa: F401
    find_compose_file,
    docker_status,
    _parse_compose_services,
    _parse_compose_service_details,
    _env_list_to_dict,
    _normalise_ports,
    _long_volume_to_str,
)

# ── Observe + Act (containers) ──
from src.core.services.docker_containers import (  # noqa: F401
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
from src.core.services.docker_generate import (  # noqa: F401
    generate_dockerfile,
    generate_dockerignore,
    generate_compose,
    generate_compose_from_wizard,
    write_generated_file,
)
