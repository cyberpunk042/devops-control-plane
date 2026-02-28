"""
L0 — OS detection helpers and main ``_detect_os()``.

Static data maps (architecture, distro-family), parsing helpers,
and the composite OS-profile builder.

Split from ``l0_detection.py`` — that file kept the tool/module/
manifest/Python/venv detectors and the public API entry point.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Architecture normalization ──────────────────────────────────

_ARCH_MAP: dict[str, str] = {
    "x86_64": "amd64", "amd64": "amd64",
    "aarch64": "arm64", "arm64": "arm64",
    "armv7l": "armv7",
}

# ── Distro family mapping ──────────────────────────────────────

_FAMILY_MAP: dict[str, str] = {
    # Debian family
    "ubuntu": "debian", "debian": "debian", "linuxmint": "debian",
    "pop": "debian", "elementary": "debian", "zorin": "debian",
    "kali": "debian", "raspbian": "debian", "deepin": "debian",
    # RHEL family
    "fedora": "rhel", "centos": "rhel", "rhel": "rhel",
    "rocky": "rhel", "almalinux": "rhel", "oracle": "rhel",
    "amzn": "rhel",
    # Alpine
    "alpine": "alpine",
    # Arch family
    "arch": "arch", "manjaro": "arch", "endeavouros": "arch",
    # SUSE family
    "opensuse-leap": "suse", "opensuse-tumbleweed": "suse", "sles": "suse",
}


# ═══════════════════════════════════════════════════════════════════
#  Parsing helpers
# ═══════════════════════════════════════════════════════════════════


def _parse_os_release() -> dict[str, str]:
    """Parse /etc/os-release into a dict of key=value pairs."""
    data: dict[str, str] = {}
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    key, val = line.split("=", 1)
                    data[key] = val.strip('"')
    except (FileNotFoundError, OSError):
        pass
    return data


def _get_distro_family(distro_id: str, id_like: str) -> str:
    """Determine distro family from ID and ID_LIKE fields."""
    if distro_id in _FAMILY_MAP:
        return _FAMILY_MAP[distro_id]
    for parent in id_like.split():
        if parent in _FAMILY_MAP:
            return _FAMILY_MAP[parent]
    return "unknown"


def _parse_version_tuple(version_str: str) -> list[int]:
    """Parse '20.04' → [20, 4], '39' → [39]."""
    parts: list[int] = []
    for p in version_str.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return parts


# ═══════════════════════════════════════════════════════════════════
#  Sub-detectors called by _detect_os()
# ═══════════════════════════════════════════════════════════════════


def _detect_container() -> dict:
    """Detect if running inside a container (Docker, K8s, podman)."""
    result: dict[str, object] = {
        "in_container": False,
        "runtime": None,
        "in_k8s": False,
    }

    # Method 1: /.dockerenv file
    if os.path.isfile("/.dockerenv"):
        result["in_container"] = True
        result["runtime"] = "docker"

    # Method 2: /proc/1/cgroup contains docker/kubepods/containerd
    try:
        with open("/proc/1/cgroup", encoding="utf-8") as f:
            cgroup = f.read().lower()
            if "docker" in cgroup:
                result["in_container"] = True
                result["runtime"] = result["runtime"] or "docker"
            elif "kubepods" in cgroup:
                result["in_container"] = True
                result["runtime"] = "containerd"
                result["in_k8s"] = True
            elif "containerd" in cgroup:
                result["in_container"] = True
                result["runtime"] = "containerd"
    except (FileNotFoundError, OSError, PermissionError):
        pass

    # Method 3: /proc/1/environ contains container=
    try:
        with open("/proc/1/environ", encoding="utf-8", errors="replace") as f:
            env = f.read()
            if "container=" in env:
                result["in_container"] = True
    except (FileNotFoundError, OSError, PermissionError):
        pass

    # Method 4: KUBERNETES_SERVICE_HOST env var
    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        result["in_k8s"] = True
        result["in_container"] = True

    # ── Read-only filesystem detection ──
    result["read_only_rootfs"] = False
    if result["in_container"]:
        try:
            probe = "/tmp/.dcp_ro_probe"
            with open(probe, "w") as f:
                f.write("probe")
            os.unlink(probe)
        except (OSError, PermissionError):
            result["read_only_rootfs"] = True

    # ── K8s ephemeral install warning ──
    if result["in_k8s"]:
        result["ephemeral_warning"] = (
            "Running in a Kubernetes pod. Installed tools will be lost "
            "when the pod restarts. Consider building a custom image instead."
        )

    return result


def _detect_capabilities() -> dict:
    """Detect system capabilities: systemd, sudo, root."""
    result: dict[str, object] = {
        "has_systemd": False,
        "systemd_state": None,
        "has_sudo": shutil.which("sudo") is not None,
        "passwordless_sudo": False,
        "is_root": os.getuid() == 0 if hasattr(os, "getuid") else False,
    }

    # systemd detection
    if shutil.which("systemctl"):
        try:
            r = subprocess.run(
                ["systemctl", "is-system-running"],
                capture_output=True, text=True, timeout=5,
            )
            state = r.stdout.strip()
            result["systemd_state"] = state
            result["has_systemd"] = state in ("running", "degraded")
        except (subprocess.TimeoutExpired, OSError):
            pass

    # Passwordless sudo
    if result["has_sudo"] and not result["is_root"]:
        try:
            r = subprocess.run(
                ["sudo", "-n", "true"],
                capture_output=True, timeout=5,
            )
            result["passwordless_sudo"] = r.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            pass

    return result


def _detect_package_managers(has_systemd: bool) -> dict:
    """Detect available package managers and pick the primary one."""
    _PM_BINARIES = [
        ("apt", "apt-get"),
        ("dnf", "dnf"),
        ("yum", "yum"),
        ("apk", "apk"),
        ("pacman", "pacman"),
        ("zypper", "zypper"),
        ("brew", "brew"),
    ]

    available: list[str] = []
    primary: str | None = None
    for pm_id, binary in _PM_BINARIES:
        if shutil.which(binary):
            available.append(pm_id)
            if primary is None:
                primary = pm_id

    snap_available = shutil.which("snap") is not None and has_systemd

    return {
        "primary": primary or "none",
        "available": available,
        "snap_available": snap_available,
    }


def _detect_libraries() -> dict:
    """Detect library versions: OpenSSL, glibc/musl."""
    result: dict[str, str | None] = {
        "openssl_version": None,
        "glibc_version": None,
        "libc_type": "unknown",
    }

    # OpenSSL version
    if shutil.which("openssl"):
        try:
            r = subprocess.run(
                ["openssl", "version"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                parts = r.stdout.strip().split()
                if len(parts) >= 2:
                    result["openssl_version"] = parts[1]
        except (subprocess.TimeoutExpired, OSError):
            pass

    # glibc version via ctypes
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        libc.gnu_get_libc_version.restype = ctypes.c_char_p
        result["glibc_version"] = libc.gnu_get_libc_version().decode()
        result["libc_type"] = "glibc"
    except (OSError, AttributeError):
        # Might be musl — check via ldd
        try:
            r = subprocess.run(
                ["ldd", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            output = (r.stdout + r.stderr).lower()
            if "musl" in output:
                result["libc_type"] = "musl"
                ver = re.search(r"version\s+([\d.]+)", output)
                if ver:
                    result["glibc_version"] = ver.group(1)
        except (subprocess.TimeoutExpired, OSError):
            pass

    return result


# ═══════════════════════════════════════════════════════════════════
#  Main OS detection
# ═══════════════════════════════════════════════════════════════════


def _detect_os() -> dict:
    """Detect full operating system profile.

    Returns a comprehensive dict covering: OS basics, architecture,
    distro identity and family, WSL, container environment,
    system capabilities, package managers, and library versions.
    """
    system = platform.system()
    machine = platform.machine()

    # ── Real userland arch detection ───────────────────────────
    # On Raspbian, the kernel may be 64-bit (aarch64) but the
    # userland 32-bit (armv7l). platform.machine() reports the
    # kernel arch, which gives the wrong binary. We detect this
    # by checking the pointer size of the running Python process.
    import struct
    pointer_bits = struct.calcsize("P") * 8
    if machine.lower() == "aarch64" and pointer_bits == 32:
        machine = "armv7l"

    info: dict[str, object] = {
        "system": system,
        "release": platform.release(),
        "machine": machine,
        "arch": _ARCH_MAP.get(machine.lower(), machine.lower()),
    }

    # ── WSL detection ──────────────────────────────────────────
    version_str = ""
    try:
        with open("/proc/version", encoding="utf-8") as f:
            version_str = f.read().lower()
            info["wsl"] = "microsoft" in version_str or "wsl" in version_str
    except (FileNotFoundError, OSError):
        info["wsl"] = False

    if info["wsl"]:
        info["wsl_version"] = 2 if "wsl2" in version_str else 1
    else:
        info["wsl_version"] = None

    # ── Distro detection ───────────────────────────────────────
    if system == "Linux":
        osr = _parse_os_release()
        distro_id = osr.get("ID", "linux").lower()
        id_like = osr.get("ID_LIKE", "")
        version_id = osr.get("VERSION_ID", "")
        info["distro"] = {
            "id": distro_id,
            "name": osr.get("PRETTY_NAME", f"Linux ({distro_id})"),
            "version": version_id,
            "version_tuple": _parse_version_tuple(version_id) if version_id else [],
            "family": _get_distro_family(distro_id, id_like),
            "codename": osr.get("VERSION_CODENAME"),
        }
    elif system == "Darwin":
        mac_ver = platform.mac_ver()[0] or ""
        info["distro"] = {
            "id": "macos",
            "name": f"macOS {mac_ver}" if mac_ver else "macOS",
            "version": mac_ver,
            "version_tuple": _parse_version_tuple(mac_ver) if mac_ver else [],
            "family": "macos",
            "codename": None,
        }
    else:
        info["distro"] = {
            "id": system.lower(),
            "name": system,
            "version": "",
            "version_tuple": [],
            "family": "unknown",
            "codename": None,
        }

    # ── Container detection ────────────────────────────────────
    info["container"] = _detect_container()

    # ── System capabilities ────────────────────────────────────
    capabilities = _detect_capabilities()
    info["capabilities"] = capabilities

    # ── Package managers ───────────────────────────────────────
    info["package_manager"] = _detect_package_managers(
        bool(capabilities["has_systemd"]),
    )

    # ── Library versions ───────────────────────────────────────
    info["libraries"] = _detect_libraries()

    # ── Hardware basics (fast tier) ────────────────────────────
    hw: dict[str, object] = {
        "cpu_cores": os.cpu_count() or 1,
        "arch": info["arch"],
    }
    # RAM detection
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    hw["ram_total_mb"] = round(kb / 1024)
                elif line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    hw["ram_available_mb"] = round(kb / 1024)
    except (FileNotFoundError, OSError, ValueError):
        # Fallback for non-Linux or restricted containers
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            if pages > 0 and page_size > 0:
                hw["ram_total_mb"] = round((pages * page_size) / (1024 * 1024))
        except (ValueError, OSError, AttributeError):
            hw.setdefault("ram_total_mb", None)
        hw.setdefault("ram_available_mb", None)
    # Disk free (root partition)
    try:
        disk_usage = shutil.disk_usage("/")
        hw["disk_free_gb"] = round(disk_usage.free / (1024 ** 3), 1)
        hw["disk_total_gb"] = round(disk_usage.total / (1024 ** 3), 1)
    except OSError:
        hw["disk_free_gb"] = None
        hw["disk_total_gb"] = None
    info["hardware"] = hw

    return info
