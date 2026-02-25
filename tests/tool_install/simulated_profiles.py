"""
Test fixtures — Simulated OS profiles for cross-platform testing.

Each profile represents a real-world system configuration. The resolver
uses these fields from the profile:

    - package_manager.primary  (apt/dnf/apk/pacman/zypper/brew)
    - package_manager.snap_available  (bool)
    - distro.family  (debian/rhel/alpine/arch/suse/macos)
    - distro.id  (ubuntu/debian/fedora/rhel/centos/alpine/arch/manjaro/opensuse/macos)
    - capabilities.has_sudo  (bool)
    - arch  (amd64/arm64)
"""

from __future__ import annotations


def _make_profile(
    *,
    distro_id: str,
    family: str,
    pm: str,
    snap: bool = False,
    sudo: bool = True,
    arch: str = "amd64",
    container: bool = False,
    version: str = "",
) -> dict:
    """Build a minimal but complete simulated system profile."""
    return {
        "system": "Darwin" if family == "macos" else "Linux",
        "release": "6.1.0",
        "machine": "x86_64" if arch == "amd64" else "aarch64",
        "arch": arch,
        "wsl": False,
        "wsl_version": None,
        "distro": {
            "id": distro_id,
            "name": f"{distro_id} (simulated)",
            "version": version,
            "version_tuple": [int(x) for x in version.split(".")] if version else [],
            "family": family,
            "codename": None,
        },
        "container": {"detected": container, "runtime": "docker" if container else None},
        "capabilities": {
            "has_systemd": not container and family != "alpine",
            "has_sudo": sudo,
            "has_bash": True,
            "init_system": "systemd" if not container and family != "alpine" else "none",
        },
        "package_manager": {
            "primary": pm,
            "snap_available": snap,
            "brew_available": family == "macos",
            "all": [pm] + (["snap"] if snap else []),
        },
        "libraries": {},
        "hardware": {
            "cpu_cores": 4,
            "arch": arch,
            "ram_total_mb": 8192,
            "ram_available_mb": 4096,
            "disk_free_gb": 50.0,
            "disk_total_gb": 100.0,
        },
    }


# ── 14 Canonical Profiles ─────────────────────────────────────

PROFILES: dict[str, dict] = {
    "ubuntu-desktop": _make_profile(
        distro_id="ubuntu", family="debian", pm="apt",
        snap=True, version="22.04",
    ),
    "ubuntu-server": _make_profile(
        distro_id="ubuntu", family="debian", pm="apt",
        snap=True, version="24.04",
    ),
    "debian-container": _make_profile(
        distro_id="debian", family="debian", pm="apt",
        container=True, version="12",
    ),
    "debian-rootless": _make_profile(
        distro_id="debian", family="debian", pm="apt",
        container=True, sudo=False, version="12",
    ),
    "fedora": _make_profile(
        distro_id="fedora", family="rhel", pm="dnf",
        version="39",
    ),
    "rhel": _make_profile(
        distro_id="rhel", family="rhel", pm="dnf",
        version="9.3",
    ),
    "centos-stream": _make_profile(
        distro_id="centos", family="rhel", pm="dnf",
        version="9",
    ),
    "alpine": _make_profile(
        distro_id="alpine", family="alpine", pm="apk",
        container=True, version="3.19",
    ),
    "alpine-rootless": _make_profile(
        distro_id="alpine", family="alpine", pm="apk",
        container=True, sudo=False, version="3.19",
    ),
    "arch": _make_profile(
        distro_id="arch", family="arch", pm="pacman",
    ),
    "manjaro": _make_profile(
        distro_id="manjaro", family="arch", pm="pacman",
        snap=True,
    ),
    "opensuse": _make_profile(
        distro_id="opensuse-leap", family="suse", pm="zypper",
        version="15.5",
    ),
    "macos-intel": _make_profile(
        distro_id="macos", family="macos", pm="brew",
        version="14.0",
    ),
    "macos-arm": _make_profile(
        distro_id="macos", family="macos", pm="brew",
        arch="arm64", version="14.0",
    ),
}


# Convenience: families covered
FAMILIES = sorted({p["distro"]["family"] for p in PROFILES.values()})
# Convenience: PM names covered
PMS = sorted({p["package_manager"]["primary"] for p in PROFILES.values()})
