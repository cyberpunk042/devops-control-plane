"""
Dev Scenarios — generates synthetic §6 remediation responses for the
Stage Debugger (D1).

Each scenario is produced by calling ``build_remediation_response()``
with synthetic inputs (fake tool, fake stderr) against real handlers.
This guarantees the scenario data always matches the actual handler
logic — no hard-coded JSON that can drift.

System presets let the developer test the same handler against
different OS profiles (Debian, Fedora, Alpine, macOS, Arch).
"""

from __future__ import annotations

import copy
import re
from typing import Any

from src.core.services.tool_install.data.remediation_handlers import (
    BOOTSTRAP_HANDLERS,
    INFRA_HANDLERS,
    METHOD_FAMILY_HANDLERS,
)
from src.core.services.tool_install.domain.remediation_planning import (
    build_remediation_response,
)


# ═════════════════════════════════════════════════════════════════
# System presets — fake _detect_os() shapes for each target
# ═════════════════════════════════════════════════════════════════

SYSTEM_PRESETS: dict[str, dict[str, Any]] = {
    # ── Debian family ───────────────────────────────────────────
    "ubuntu_2004": {
        "system": "Linux",
        "arch": "amd64",
        "wsl": False,
        "wsl_version": None,
        "distro": {
            "id": "ubuntu", "family": "debian",
            "version": "20.04", "version_tuple": [20, 4],
            "name": "Ubuntu 20.04.6 LTS", "codename": "focal",
        },
        "container": {"in_container": False, "runtime": None, "in_k8s": False, "read_only_rootfs": False},
        "capabilities": {"has_systemd": True, "systemd_state": "running", "has_sudo": True, "passwordless_sudo": False, "is_root": False},
        "package_manager": {"primary": "apt", "available": ["apt"], "snap_available": True},
        "libraries": {"glibc_version": "2.31", "libc_type": "glibc"},
        "hardware": {"arch": "amd64", "cpu_cores": 4},
        "python": {"default_version": [3, 8], "pep668": False},
    },
    "ubuntu_2204": {
        "system": "Linux",
        "arch": "amd64",
        "wsl": False,
        "wsl_version": None,
        "distro": {
            "id": "ubuntu", "family": "debian",
            "version": "22.04", "version_tuple": [22, 4],
            "name": "Ubuntu 22.04.4 LTS", "codename": "jammy",
        },
        "container": {"in_container": False, "runtime": None, "in_k8s": False, "read_only_rootfs": False},
        "capabilities": {"has_systemd": True, "systemd_state": "running", "has_sudo": True, "passwordless_sudo": False, "is_root": False},
        "package_manager": {"primary": "apt", "available": ["apt"], "snap_available": True},
        "libraries": {"glibc_version": "2.35", "libc_type": "glibc"},
        "hardware": {"arch": "amd64", "cpu_cores": 4},
        "python": {"default_version": [3, 10], "pep668": False},
    },
    "ubuntu_2404": {
        "system": "Linux",
        "arch": "amd64",
        "wsl": False,
        "wsl_version": None,
        "distro": {
            "id": "ubuntu", "family": "debian",
            "version": "24.04", "version_tuple": [24, 4],
            "name": "Ubuntu 24.04 LTS", "codename": "noble",
        },
        "container": {"in_container": False, "runtime": None, "in_k8s": False, "read_only_rootfs": False},
        "capabilities": {"has_systemd": True, "systemd_state": "running", "has_sudo": True, "passwordless_sudo": False, "is_root": False},
        "package_manager": {"primary": "apt", "available": ["apt"], "snap_available": True},
        "libraries": {"glibc_version": "2.39", "libc_type": "glibc"},
        "hardware": {"arch": "amd64", "cpu_cores": 4},
        "python": {"default_version": [3, 12], "pep668": True},
    },
    "debian_11": {
        "system": "Linux",
        "arch": "amd64",
        "wsl": False,
        "wsl_version": None,
        "distro": {
            "id": "debian", "family": "debian",
            "version": "11", "version_tuple": [11],
            "name": "Debian GNU/Linux 11 (bullseye)", "codename": "bullseye",
        },
        "container": {"in_container": False, "runtime": None, "in_k8s": False, "read_only_rootfs": False},
        "capabilities": {"has_systemd": True, "systemd_state": "running", "has_sudo": True, "passwordless_sudo": False, "is_root": False},
        "package_manager": {"primary": "apt", "available": ["apt"], "snap_available": False},
        "libraries": {"glibc_version": "2.31", "libc_type": "glibc"},
        "hardware": {"arch": "amd64", "cpu_cores": 4},
        "python": {"default_version": [3, 9], "pep668": False},
    },
    "debian_12": {
        "system": "Linux",
        "arch": "amd64",
        "wsl": False,
        "wsl_version": None,
        "distro": {
            "id": "debian", "family": "debian",
            "version": "12", "version_tuple": [12],
            "name": "Debian GNU/Linux 12 (bookworm)", "codename": "bookworm",
        },
        "container": {"in_container": False, "runtime": None, "in_k8s": False, "read_only_rootfs": False},
        "capabilities": {"has_systemd": True, "systemd_state": "running", "has_sudo": True, "passwordless_sudo": False, "is_root": False},
        "package_manager": {"primary": "apt", "available": ["apt"], "snap_available": False},
        "libraries": {"glibc_version": "2.36", "libc_type": "glibc"},
        "hardware": {"arch": "amd64", "cpu_cores": 4},
        "python": {"default_version": [3, 11], "pep668": True},
    },
    "raspbian_bookworm": {
        "system": "Linux",
        "arch": "arm64",
        "wsl": False,
        "wsl_version": None,
        "distro": {
            "id": "raspbian", "family": "debian",
            "version": "12", "version_tuple": [12],
            "name": "Raspberry Pi OS 12 (bookworm)", "codename": "bookworm",
        },
        "container": {"in_container": False, "runtime": None, "in_k8s": False, "read_only_rootfs": False},
        "capabilities": {"has_systemd": True, "systemd_state": "running", "has_sudo": True, "passwordless_sudo": True, "is_root": False},
        "package_manager": {"primary": "apt", "available": ["apt"], "snap_available": True},
        "libraries": {"glibc_version": "2.36", "libc_type": "glibc"},
        "hardware": {"arch": "arm64", "cpu_cores": 4},
        "python": {"default_version": [3, 11], "pep668": True},
    },
    "wsl2_ubuntu_2204": {
        "system": "Linux",
        "arch": "amd64",
        "wsl": True,
        "wsl_version": 2,
        "distro": {
            "id": "ubuntu", "family": "debian",
            "version": "22.04", "version_tuple": [22, 4],
            "name": "Ubuntu 22.04.4 LTS", "codename": "jammy",
        },
        "container": {"in_container": False, "runtime": None, "in_k8s": False, "read_only_rootfs": False},
        "capabilities": {"has_systemd": True, "systemd_state": "degraded", "has_sudo": True, "passwordless_sudo": False, "is_root": False},
        "package_manager": {"primary": "apt", "available": ["apt"], "snap_available": True},
        "libraries": {"glibc_version": "2.35", "libc_type": "glibc"},
        "hardware": {"arch": "amd64", "cpu_cores": 4},
        "python": {"default_version": [3, 10], "pep668": False},
    },

    # ── RHEL family ─────────────────────────────────────────────
    "fedora_39": {
        "system": "Linux",
        "arch": "amd64",
        "wsl": False,
        "wsl_version": None,
        "distro": {
            "id": "fedora", "family": "rhel",
            "version": "39", "version_tuple": [39],
            "name": "Fedora Linux 39", "codename": None,
        },
        "container": {"in_container": False, "runtime": None, "in_k8s": False, "read_only_rootfs": False},
        "capabilities": {"has_systemd": True, "systemd_state": "running", "has_sudo": True, "passwordless_sudo": False, "is_root": False},
        "package_manager": {"primary": "dnf", "available": ["dnf"], "snap_available": False},
        "libraries": {"glibc_version": "2.38", "libc_type": "glibc"},
        "hardware": {"arch": "amd64", "cpu_cores": 4},
        "python": {"default_version": [3, 12], "pep668": True},
    },
    "fedora_41": {
        "system": "Linux",
        "arch": "amd64",
        "wsl": False,
        "wsl_version": None,
        "distro": {
            "id": "fedora", "family": "rhel",
            "version": "41", "version_tuple": [41],
            "name": "Fedora Linux 41", "codename": None,
        },
        "container": {"in_container": False, "runtime": None, "in_k8s": False, "read_only_rootfs": False},
        "capabilities": {"has_systemd": True, "systemd_state": "running", "has_sudo": True, "passwordless_sudo": False, "is_root": False},
        "package_manager": {"primary": "dnf", "available": ["dnf"], "snap_available": False},
        "libraries": {"glibc_version": "2.40", "libc_type": "glibc"},
        "hardware": {"arch": "amd64", "cpu_cores": 4},
        "python": {"default_version": [3, 13], "pep668": True},
    },
    "centos_stream9": {
        "system": "Linux",
        "arch": "amd64",
        "wsl": False,
        "wsl_version": None,
        "distro": {
            "id": "centos", "family": "rhel",
            "version": "9", "version_tuple": [9],
            "name": "CentOS Stream 9", "codename": None,
        },
        "container": {"in_container": False, "runtime": None, "in_k8s": False, "read_only_rootfs": False},
        "capabilities": {"has_systemd": True, "systemd_state": "running", "has_sudo": True, "passwordless_sudo": False, "is_root": False},
        "package_manager": {"primary": "dnf", "available": ["dnf"], "snap_available": False},
        "libraries": {"glibc_version": "2.34", "libc_type": "glibc"},
        "hardware": {"arch": "amd64", "cpu_cores": 4},
        "python": {"default_version": [3, 9], "pep668": False},
    },
    "rocky_9": {
        "system": "Linux",
        "arch": "amd64",
        "wsl": False,
        "wsl_version": None,
        "distro": {
            "id": "rocky", "family": "rhel",
            "version": "9.3", "version_tuple": [9, 3],
            "name": "Rocky Linux 9.3", "codename": None,
        },
        "container": {"in_container": False, "runtime": None, "in_k8s": False, "read_only_rootfs": False},
        "capabilities": {"has_systemd": True, "systemd_state": "running", "has_sudo": True, "passwordless_sudo": False, "is_root": False},
        "package_manager": {"primary": "dnf", "available": ["dnf"], "snap_available": False},
        "libraries": {"glibc_version": "2.34", "libc_type": "glibc"},
        "hardware": {"arch": "amd64", "cpu_cores": 4},
        "python": {"default_version": [3, 9], "pep668": False},
    },

    # ── Alpine ──────────────────────────────────────────────────
    "alpine_318": {
        "system": "Linux",
        "arch": "amd64",
        "wsl": False,
        "wsl_version": None,
        "distro": {
            "id": "alpine", "family": "alpine",
            "version": "3.18", "version_tuple": [3, 18],
            "name": "Alpine Linux v3.18", "codename": None,
        },
        "container": {"in_container": False, "runtime": None, "in_k8s": False, "read_only_rootfs": False},
        "capabilities": {"has_systemd": False, "systemd_state": None, "has_sudo": False, "passwordless_sudo": False, "is_root": True},
        "package_manager": {"primary": "apk", "available": ["apk"], "snap_available": False},
        "libraries": {"glibc_version": None, "libc_type": "musl"},
        "hardware": {"arch": "amd64", "cpu_cores": 4},
        "python": {"default_version": [3, 11], "pep668": False},
    },
    "alpine_320": {
        "system": "Linux",
        "arch": "amd64",
        "wsl": False,
        "wsl_version": None,
        "distro": {
            "id": "alpine", "family": "alpine",
            "version": "3.20", "version_tuple": [3, 20],
            "name": "Alpine Linux v3.20", "codename": None,
        },
        "container": {"in_container": False, "runtime": None, "in_k8s": False, "read_only_rootfs": False},
        "capabilities": {"has_systemd": False, "systemd_state": None, "has_sudo": False, "passwordless_sudo": False, "is_root": True},
        "package_manager": {"primary": "apk", "available": ["apk"], "snap_available": False},
        "libraries": {"glibc_version": None, "libc_type": "musl"},
        "hardware": {"arch": "amd64", "cpu_cores": 4},
        "python": {"default_version": [3, 12], "pep668": False},
    },

    # ── Arch ────────────────────────────────────────────────────
    "arch_latest": {
        "system": "Linux",
        "arch": "amd64",
        "wsl": False,
        "wsl_version": None,
        "distro": {
            "id": "arch", "family": "arch",
            "version": "", "version_tuple": [],
            "name": "Arch Linux", "codename": None,
        },
        "container": {"in_container": False, "runtime": None, "in_k8s": False, "read_only_rootfs": False},
        "capabilities": {"has_systemd": True, "systemd_state": "running", "has_sudo": True, "passwordless_sudo": False, "is_root": False},
        "package_manager": {"primary": "pacman", "available": ["pacman"], "snap_available": False},
        "libraries": {"glibc_version": "2.39", "libc_type": "glibc"},
        "hardware": {"arch": "amd64", "cpu_cores": 4},
        "python": {"default_version": [3, 12], "pep668": True},
    },

    # ── SUSE ────────────────────────────────────────────────────
    "opensuse_15": {
        "system": "Linux",
        "arch": "amd64",
        "wsl": False,
        "wsl_version": None,
        "distro": {
            "id": "opensuse-leap", "family": "suse",
            "version": "15.5", "version_tuple": [15, 5],
            "name": "openSUSE Leap 15.5", "codename": None,
        },
        "container": {"in_container": False, "runtime": None, "in_k8s": False, "read_only_rootfs": False},
        "capabilities": {"has_systemd": True, "systemd_state": "running", "has_sudo": True, "passwordless_sudo": False, "is_root": False},
        "package_manager": {"primary": "zypper", "available": ["zypper"], "snap_available": False},
        "libraries": {"glibc_version": "2.31", "libc_type": "glibc"},
        "hardware": {"arch": "amd64", "cpu_cores": 4},
        "python": {"default_version": [3, 6], "pep668": False},
    },

    # ── macOS ───────────────────────────────────────────────────
    "macos_14_arm": {
        "system": "Darwin",
        "arch": "arm64",
        "wsl": False,
        "wsl_version": None,
        "distro": {
            "id": "macos", "family": "macos",
            "version": "14.0", "version_tuple": [14, 0],
            "name": "macOS 14.0 Sonoma", "codename": None,
        },
        "container": {"in_container": False, "runtime": None, "in_k8s": False, "read_only_rootfs": False},
        "capabilities": {"has_systemd": False, "systemd_state": None, "has_sudo": True, "passwordless_sudo": False, "is_root": False},
        "package_manager": {"primary": "brew", "available": ["brew"], "snap_available": False},
        "libraries": {"glibc_version": None, "libc_type": None},
        "hardware": {"arch": "arm64", "cpu_cores": 8},
        "python": {"default_version": [3, 9], "pep668": False},
    },
    "macos_13_x86": {
        "system": "Darwin",
        "arch": "amd64",
        "wsl": False,
        "wsl_version": None,
        "distro": {
            "id": "macos", "family": "macos",
            "version": "13.0", "version_tuple": [13, 0],
            "name": "macOS 13.0 Ventura", "codename": None,
        },
        "container": {"in_container": False, "runtime": None, "in_k8s": False, "read_only_rootfs": False},
        "capabilities": {"has_systemd": False, "systemd_state": None, "has_sudo": True, "passwordless_sudo": False, "is_root": False},
        "package_manager": {"primary": "brew", "available": ["brew"], "snap_available": False},
        "libraries": {"glibc_version": None, "libc_type": None},
        "hardware": {"arch": "amd64", "cpu_cores": 8},
        "python": {"default_version": [3, 9], "pep668": False},
    },

    # ── Container edge cases ────────────────────────────────────
    "docker_debian_12": {
        "system": "Linux",
        "arch": "amd64",
        "wsl": False,
        "wsl_version": None,
        "distro": {
            "id": "debian", "family": "debian",
            "version": "12", "version_tuple": [12],
            "name": "Debian GNU/Linux 12 (bookworm)", "codename": "bookworm",
        },
        "container": {"in_container": True, "runtime": "docker", "in_k8s": False, "read_only_rootfs": False},
        "capabilities": {"has_systemd": False, "systemd_state": None, "has_sudo": False, "passwordless_sudo": False, "is_root": True},
        "package_manager": {"primary": "apt", "available": ["apt"], "snap_available": False},
        "libraries": {"glibc_version": "2.36", "libc_type": "glibc"},
        "hardware": {"arch": "amd64", "cpu_cores": 2},
        "python": {"default_version": [3, 11], "pep668": True},
    },
    "k8s_alpine_318": {
        "system": "Linux",
        "arch": "amd64",
        "wsl": False,
        "wsl_version": None,
        "distro": {
            "id": "alpine", "family": "alpine",
            "version": "3.18", "version_tuple": [3, 18],
            "name": "Alpine Linux v3.18", "codename": None,
        },
        "container": {"in_container": True, "runtime": "containerd", "in_k8s": True, "read_only_rootfs": True},
        "capabilities": {"has_systemd": False, "systemd_state": None, "has_sudo": False, "passwordless_sudo": False, "is_root": True},
        "package_manager": {"primary": "apk", "available": ["apk"], "snap_available": False},
        "libraries": {"glibc_version": None, "libc_type": "musl"},
        "hardware": {"arch": "amd64", "cpu_cores": 1},
        "python": {"default_version": [3, 11], "pep668": False},
    },
}



# ═════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════

def _summarize_availability(response: dict) -> str:
    """Summarize option availability mix."""
    avails = [o.get("availability", "ready") for o in response.get("options", [])]
    if all(a == "ready" for a in avails):
        return "all-ready"
    if all(a == "locked" for a in avails):
        return "all-locked"
    if all(a == "impossible" for a in avails):
        return "all-impossible"
    return "mixed"


def _max_risk(response: dict) -> str:
    """Return highest risk level among options."""
    risks = [o.get("risk", "low") for o in response.get("options", [])]
    for level in ("high", "medium", "low"):
        if level in risks:
            return level
    return "low"


def _build_synthetic_recipe(system_preset_id: str) -> dict:
    """Build a synthetic recipe that has all common install methods.

    The scenario generator needs a recipe with realistic install methods
    so that ``switch_method`` availability checks pass instead of
    returning ``impossible`` for every option.

    The recipe is tuned to the system preset — Debian gets apt/snap,
    Fedora gets dnf, Alpine gets apk, macOS gets brew, Arch gets pacman.
    All presets also get pip, npm, cargo, _default, and source.

    This is purely for scenario testing — not used for real installs.
    """
    preset = SYSTEM_PRESETS.get(system_preset_id, {})
    pkg_mgr = preset.get("package_manager", {}).get("primary", "apt")
    family = preset.get("distro", {}).get("family", "debian")

    # Common install methods every recipe could have
    install = {
        "_default": [{"label": "Default install", "cmd": "echo install"}],
        "pip": [{"label": "Install via pip", "cmd": "pip install test"}],
        "npm": [{"label": "Install via npm", "cmd": "npm install -g test"}],
        "cargo": [{"label": "Install via cargo", "cmd": "cargo install test"}],
        "source": [{"label": "Build from source", "cmd": "make install"}],
    }

    # Add the system's native package manager
    if pkg_mgr == "apt":
        install["apt"] = [{"label": "Install via apt", "cmd": "sudo apt install -y test"}]
        install["snap"] = [{"label": "Install via snap", "cmd": "sudo snap install test"}]
    elif pkg_mgr == "dnf":
        install["dnf"] = [{"label": "Install via dnf", "cmd": "sudo dnf install -y test"}]
    elif pkg_mgr == "apk":
        install["apk"] = [{"label": "Install via apk", "cmd": "apk add test"}]
    elif pkg_mgr == "zypper":
        install["zypper"] = [{"label": "Install via zypper", "cmd": "sudo zypper install -y test"}]
    elif pkg_mgr == "brew":
        install["brew"] = [{"label": "Install via brew", "cmd": "brew install test"}]
    elif pkg_mgr == "pacman":
        install["pacman"] = [{"label": "Install via pacman", "cmd": "sudo pacman -S --noconfirm test"}]

    return {
        "cli": "test",
        "label": "Test Tool",
        "install": install,
    }


def _synthesize_stderr(handler: dict) -> str:
    """Return stderr that matches the handler's pattern.

    Uses the ``example_stderr`` field added in D1.1.
    Falls back to the raw pattern string if no example exists.
    """
    return handler.get("example_stderr", handler.get("pattern", "error"))


def _synthesize_exit_code(handler: dict) -> int:
    """Return the exit code for the handler."""
    return handler.get("example_exit_code", handler.get("exit_code", 1))


# ═════════════════════════════════════════════════════════════════
# Method-family scenario generation
# ═════════════════════════════════════════════════════════════════

def _generate_method_family_scenarios(
    system_preset_id: str = "debian_12",
) -> list[dict]:
    """Generate one scenario per method-family handler."""
    profile = SYSTEM_PRESETS[system_preset_id]
    synthetic_recipe = _build_synthetic_recipe(system_preset_id)
    scenarios: list[dict] = []

    for method, handlers in METHOD_FAMILY_HANDLERS.items():
        for handler in handlers:
            stderr = _synthesize_stderr(handler)
            exit_code = _synthesize_exit_code(handler)

            response = build_remediation_response(
                tool_id=f"test_{method}",
                step_idx=0,
                step_label=f"Install test_{method}",
                exit_code=exit_code,
                stderr=stderr,
                method=method,
                system_profile=profile,
                recipe_override=synthetic_recipe,
            )
            if not response:
                continue

            scenarios.append({
                "_meta": {
                    "id": f"{method}_{handler['failure_id']}",
                    "label": handler["label"],
                    "group": "method-family",
                    "family": method,
                    "system": system_preset_id,
                    "description": handler.get("description", ""),
                    "option_count": len(response.get("options", [])),
                    "availability": _summarize_availability(response),
                    "max_risk": _max_risk(response),
                },
                "toolId": f"test_{method}",
                "toolLabel": f"Test ({method})",
                "remediation": response,
            })

    return scenarios


# ═════════════════════════════════════════════════════════════════
# Infrastructure scenario generation
# ═════════════════════════════════════════════════════════════════

def _generate_infra_scenarios(
    system_preset_id: str = "debian_12",
) -> list[dict]:
    """Generate one scenario per infra handler."""
    profile = SYSTEM_PRESETS[system_preset_id]
    synthetic_recipe = _build_synthetic_recipe(system_preset_id)
    scenarios: list[dict] = []

    for handler in INFRA_HANDLERS:
        stderr = _synthesize_stderr(handler)
        exit_code = _synthesize_exit_code(handler)

        response = build_remediation_response(
            tool_id="test_infra",
            step_idx=0,
            step_label="Install test_infra",
            exit_code=exit_code,
            stderr=stderr,
            method="apt",
            system_profile=profile,
            recipe_override=synthetic_recipe,
        )
        if not response:
            continue

        scenarios.append({
            "_meta": {
                "id": f"infra_{handler['failure_id']}",
                "label": handler["label"],
                "group": "infrastructure",
                "system": system_preset_id,
                "description": handler.get("description", ""),
                "option_count": len(response.get("options", [])),
                "availability": _summarize_availability(response),
                "max_risk": _max_risk(response),
            },
            "toolId": "test_infra",
            "toolLabel": "Test (Infra)",
            "remediation": response,
        })

    return scenarios


# ═════════════════════════════════════════════════════════════════
# Bootstrap scenario generation
# ═════════════════════════════════════════════════════════════════

def _generate_bootstrap_scenarios(
    system_preset_id: str = "debian_12",
) -> list[dict]:
    """Generate one scenario per bootstrap handler."""
    profile = SYSTEM_PRESETS[system_preset_id]
    synthetic_recipe = _build_synthetic_recipe(system_preset_id)
    scenarios: list[dict] = []

    for handler in BOOTSTRAP_HANDLERS:
        stderr = _synthesize_stderr(handler)
        exit_code = _synthesize_exit_code(handler)

        response = build_remediation_response(
            tool_id="test_bootstrap",
            step_idx=0,
            step_label="Install test_bootstrap",
            exit_code=exit_code,
            stderr=stderr,
            method="_default",
            system_profile=profile,
            recipe_override=synthetic_recipe,
        )
        if not response:
            continue

        scenarios.append({
            "_meta": {
                "id": f"bootstrap_{handler['failure_id']}",
                "label": handler["label"],
                "group": "bootstrap",
                "system": system_preset_id,
                "description": handler.get("description", ""),
                "option_count": len(response.get("options", [])),
                "availability": _summarize_availability(response),
                "max_risk": _max_risk(response),
            },
            "toolId": "test_bootstrap",
            "toolLabel": "Test (Bootstrap)",
            "remediation": response,
        })

    return scenarios


# ═════════════════════════════════════════════════════════════════
# Chain scenario generation (pre-built escalation states)
# ═════════════════════════════════════════════════════════════════

def _generate_chain_scenarios(
    system_preset_id: str = "debian_12",
) -> list[dict]:
    """Generate scenarios with escalation chains at various depths."""
    profile = SYSTEM_PRESETS[system_preset_id]
    synthetic_recipe = _build_synthetic_recipe(system_preset_id)
    scenarios: list[dict] = []

    # Depth 1: ruff → pip failure (PEP 668)
    chain_1 = {
        "chain_id": "test_chain_d1",
        "depth": 1,
        "breadcrumbs": [
            {"label": "Install ruff", "depth": 0, "status": "failed", "icon": "📦"},
        ],
        "original_goal": {"tool": "ruff", "label": "Ruff"},
    }
    resp_1 = build_remediation_response(
        tool_id="ruff", step_idx=0, step_label="Install ruff",
        exit_code=1,
        stderr="error: externally-managed-environment",
        method="pip",
        system_profile=profile,
        chain=chain_1,
        recipe_override=synthetic_recipe,
    )
    if resp_1:
        scenarios.append({
            "_meta": {
                "id": "chain_depth_1",
                "label": "Chain Depth 1 (ruff → pip PEP 668)",
                "group": "chains",
                "chain_depth": 1,
                "option_count": len(resp_1.get("options", [])),
                "availability": _summarize_availability(resp_1),
                "max_risk": _max_risk(resp_1),
            },
            "toolId": "ruff",
            "toolLabel": "Ruff",
            "remediation": resp_1,
        })

    # Depth 2: ruff → pip → pipx not found
    chain_2 = {
        "chain_id": "test_chain_d2",
        "depth": 2,
        "breadcrumbs": [
            {"label": "Install ruff", "depth": 0, "status": "failed", "icon": "📦"},
            {"label": "Install via pipx", "depth": 1, "status": "failed", "icon": "📦"},
        ],
        "original_goal": {"tool": "ruff", "label": "Ruff"},
    }
    resp_2 = build_remediation_response(
        tool_id="pipx", step_idx=0, step_label="Install pipx",
        exit_code=1,
        stderr="pip: command not found",
        method="pip",
        system_profile=profile,
        chain=chain_2,
        recipe_override=synthetic_recipe,
    )
    if resp_2:
        scenarios.append({
            "_meta": {
                "id": "chain_depth_2",
                "label": "Chain Depth 2 (ruff → pip → pipx)",
                "group": "chains",
                "chain_depth": 2,
                "option_count": len(resp_2.get("options", [])),
                "availability": _summarize_availability(resp_2),
                "max_risk": _max_risk(resp_2),
            },
            "toolId": "pipx",
            "toolLabel": "pipx",
            "remediation": resp_2,
        })

    return scenarios


# ═════════════════════════════════════════════════════════════════
# Custom edge-case scenarios (hand-crafted, not from handlers)
# ═════════════════════════════════════════════════════════════════

CUSTOM_SCENARIOS: list[dict] = [
    {
        "_meta": {
            "id": "edge_single_option",
            "label": "Single Option Only",
            "group": "edge-cases",
            "description": "Tests UI when there's exactly 1 option",
            "option_count": 1,
            "availability": "all-ready",
            "max_risk": "low",
        },
        "toolId": "test_edge",
        "toolLabel": "Test (Edge)",
        "remediation": {
            "ok": False,
            "tool_id": "test_edge",
            "step_idx": 0,
            "step_label": "Install test_edge",
            "exit_code": 1,
            "stderr": "generic failure",
            "failure": {
                "failure_id": "test_single",
                "category": "test",
                "label": "Single Option Test",
                "description": "Only one remediation option available.",
                "matched_layer": "custom",
                "matched_method": "test",
            },
            "options": [
                {
                    "id": "only_option",
                    "label": "The only thing you can do",
                    "description": "This is the only available option.",
                    "icon": "🔧",
                    "recommended": True,
                    "strategy": "retry_with_modifier",
                    "risk": "low",
                    "availability": "ready",
                    "step_count": 1,
                },
            ],
            "chain": None,
            "fallback_actions": [
                {"id": "cancel", "label": "Cancel", "icon": "✕"},
            ],
        },
    },
    {
        "_meta": {
            "id": "edge_all_locked",
            "label": "All Options Locked",
            "group": "edge-cases",
            "description": "Tests UI when every option is locked",
            "option_count": 3,
            "availability": "all-locked",
            "max_risk": "medium",
        },
        "toolId": "test_edge",
        "toolLabel": "Test (Edge)",
        "remediation": {
            "ok": False,
            "tool_id": "test_edge",
            "step_idx": 0,
            "step_label": "Install test_edge",
            "exit_code": 1,
            "stderr": "hypothetical all-locked failure",
            "failure": {
                "failure_id": "test_all_locked",
                "category": "test",
                "label": "All Options Locked",
                "description": "Every remediation path requires prerequisites.",
                "matched_layer": "custom",
                "matched_method": "test",
            },
            "options": [
                {
                    "id": "locked_a",
                    "label": "Option A (locked)",
                    "description": "Requires dependency X.",
                    "icon": "🔒",
                    "recommended": True,
                    "strategy": "install_dep",
                    "risk": "low",
                    "availability": "locked",
                    "lock_reason": "dep_x is not installed",
                    "step_count": 3,
                },
                {
                    "id": "locked_b",
                    "label": "Option B (locked)",
                    "description": "Requires admin elevation.",
                    "icon": "🔒",
                    "recommended": False,
                    "strategy": "retry_with_modifier",
                    "risk": "medium",
                    "availability": "locked",
                    "lock_reason": "sudo access required but not available",
                    "step_count": 2,
                },
                {
                    "id": "locked_c",
                    "label": "Option C (locked)",
                    "description": "Requires network access.",
                    "icon": "🔒",
                    "recommended": False,
                    "strategy": "env_fix",
                    "risk": "low",
                    "availability": "locked",
                    "lock_reason": "network is unreachable",
                    "step_count": 1,
                },
            ],
            "chain": None,
            "fallback_actions": [
                {"id": "cancel", "label": "Cancel", "icon": "✕"},
            ],
        },
    },
    {
        "_meta": {
            "id": "edge_all_impossible",
            "label": "All Options Impossible",
            "group": "edge-cases",
            "description": "Tests dead-end UI — no option can work",
            "option_count": 2,
            "availability": "all-impossible",
            "max_risk": "high",
        },
        "toolId": "test_edge",
        "toolLabel": "Test (Edge)",
        "remediation": {
            "ok": False,
            "tool_id": "test_edge",
            "step_idx": 0,
            "step_label": "Install test_edge",
            "exit_code": 1,
            "stderr": "hypothetical all-impossible failure",
            "failure": {
                "failure_id": "test_all_impossible",
                "category": "test",
                "label": "Dead End — No Options Available",
                "description": "None of the remediation strategies can work on this system.",
                "matched_layer": "custom",
                "matched_method": "test",
            },
            "options": [
                {
                    "id": "impossible_a",
                    "label": "Option A (impossible)",
                    "description": "Not supported on this architecture.",
                    "icon": "🚫",
                    "recommended": False,
                    "strategy": "install_dep",
                    "risk": "low",
                    "availability": "impossible",
                    "impossible_reason": "ARM architecture is not supported",
                    "step_count": 0,
                },
                {
                    "id": "impossible_b",
                    "label": "Option B (impossible)",
                    "description": "Deprecated and removed.",
                    "icon": "🚫",
                    "recommended": False,
                    "strategy": "switch_method",
                    "risk": "high",
                    "availability": "impossible",
                    "impossible_reason": "This method has been permanently removed upstream",
                    "step_count": 0,
                },
            ],
            "chain": None,
            "fallback_actions": [
                {"id": "cancel", "label": "Cancel", "icon": "✕"},
            ],
        },
    },
]


# ═════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════

def generate_all_scenarios(
    system_preset_id: str = "debian_12",
) -> list[dict]:
    """Generate all scenarios for the given system preset.

    Returns a list of scenario dicts, each with ``_meta``, ``toolId``,
    ``toolLabel``, and ``remediation`` keys.
    """
    scenarios: list[dict] = []
    scenarios.extend(_generate_method_family_scenarios(system_preset_id))
    scenarios.extend(_generate_infra_scenarios(system_preset_id))
    scenarios.extend(_generate_bootstrap_scenarios(system_preset_id))
    scenarios.extend(_generate_chain_scenarios(system_preset_id))

    # Custom edge cases are static — deep-copy to avoid mutation
    scenarios.extend(copy.deepcopy(CUSTOM_SCENARIOS))

    return scenarios


def get_system_presets() -> list[str]:
    """Return list of valid system preset IDs."""
    return list(SYSTEM_PRESETS.keys())
