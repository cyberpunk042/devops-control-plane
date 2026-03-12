"""
Platform scanner — OS, kernel, glibc, WSL, and architecture detection.

Detects the host operating system and maps it against the OS lifecycle
database to compute deprecation ranks.

Reuses existing detection modules:
  - ``tool_install/detection/hardware.py``  → ``detect_kernel()``
  - ``wsl_transport/environment.py``        → ``is_wsl2()``
  - ``pages/install.py`` pattern            → glibc via ctypes

The only NEW subprocess call is glibc detection via ctypes (no subprocess).
OS detection uses Python's ``platform`` stdlib and ``/etc/os-release``.
"""

from __future__ import annotations

import logging
import platform
import re
from pathlib import Path
from typing import Any

from ..models import PillarResult, PostureItem, RankLevel
from ..ranking import load_os_lifecycle, rank_by_eol

logger = logging.getLogger(__name__)


def scan_platform() -> PillarResult:
    """Scan the host platform and rank each component.

    Detects:
      - OS distribution + version  → ranked against os_lifecycle.json
      - Kernel version             → informational (no EOL ranking)
      - Architecture               → informational
      - glibc version              → informational (warns if very old)
      - WSL status                 → informational

    Returns:
        PillarResult with items for each detected component.
    """
    items: list[PostureItem] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    # ── OS distribution ─────────────────────────────────────────
    distro, version, codename = _detect_os()
    os_rank, os_detail, os_eol = _rank_os(distro, version)

    display_name = distro.capitalize()
    display_value = f"{version} ({codename})" if codename else version

    items.append(PostureItem(
        name=display_name,
        value=display_value,
        rank=os_rank,
        detail=os_detail,
        eol_date=os_eol,
    ))

    if os_rank.severity >= RankLevel.OUTDATED.severity:
        warnings.append(f"{display_name} {version} is {os_rank.value}")
    if os_rank.severity >= RankLevel.DEPRECATED.severity:
        recommendations.append(f"Upgrade {display_name} to a supported release")

    # ── Kernel ──────────────────────────────────────────────────
    kernel_info = _detect_kernel_safe()
    kernel_version = kernel_info.get("version", platform.release())

    items.append(PostureItem(
        name="Kernel",
        value=kernel_version,
        rank=RankLevel.NA,  # Kernel rank is derived from OS rank
        detail=f"arch={kernel_info.get('arch', platform.machine())}",
    ))

    # ── Architecture ────────────────────────────────────────────
    arch = platform.machine()
    arch_rank = RankLevel.CURRENT if arch in ("x86_64", "aarch64", "arm64") else RankLevel.AGING

    items.append(PostureItem(
        name="Architecture",
        value=arch,
        rank=arch_rank,
        detail="64-bit" if "64" in arch else "32-bit",
    ))

    if "64" not in arch:
        warnings.append(f"32-bit architecture ({arch}) — many tools lack 32-bit support")
        recommendations.append("Consider migrating to a 64-bit system")

    # ── glibc ───────────────────────────────────────────────────
    glibc_version = _detect_glibc()
    if glibc_version and glibc_version != "unknown":
        glibc_rank, glibc_detail = _rank_glibc(glibc_version)
        items.append(PostureItem(
            name="glibc",
            value=glibc_version,
            rank=glibc_rank,
            detail=glibc_detail,
        ))
        if glibc_rank.severity >= RankLevel.OUTDATED.severity:
            warnings.append(f"glibc {glibc_version} is old — some binaries may fail")
    elif platform.system() == "Linux":
        # On Linux, no glibc likely means musl (Alpine)
        items.append(PostureItem(
            name="libc",
            value="musl (or unknown)",
            rank=RankLevel.UNKNOWN,
            detail="Non-glibc system — some pre-compiled binaries may not work",
        ))

    # ── WSL ─────────────────────────────────────────────────────
    wsl_version = _detect_wsl()
    if wsl_version:
        items.append(PostureItem(
            name="WSL",
            value=wsl_version,
            rank=RankLevel.NA,
            detail="Windows Subsystem for Linux",
        ))

    # ── Assemble result ─────────────────────────────────────────
    from ..ranking import worst_rank  # lazy to avoid circular

    return PillarResult(
        pillar="platform",
        rank=worst_rank(items),
        items=items,
        warnings=warnings,
        recommendations=recommendations,
    )


# ── OS detection ────────────────────────────────────────────────


def _detect_os() -> tuple[str, str, str]:
    """Detect OS distribution, version, and codename.

    Returns:
        (distro_id, version, codename) tuple.
        Examples: ("ubuntu", "22.04", "jammy"),
                  ("macos", "14.2", "sonoma"),
                  ("arch", "rolling", "")
    """
    system = platform.system()

    if system == "Linux":
        return _detect_linux_os()
    elif system == "Darwin":
        return _detect_macos()
    else:
        return (system.lower(), platform.release(), "")


def _detect_linux_os() -> tuple[str, str, str]:
    """Parse /etc/os-release for Linux distribution info."""
    os_release = Path("/etc/os-release")
    if not os_release.exists():
        return ("linux", platform.release(), "")

    try:
        text = os_release.read_text(encoding="utf-8")
    except OSError:
        return ("linux", platform.release(), "")

    info: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, _, val = line.partition("=")
            # Strip quotes
            val = val.strip().strip('"').strip("'")
            info[key.strip()] = val

    distro_id = info.get("ID", "linux").lower()
    version = info.get("VERSION_ID", "")
    codename = info.get("VERSION_CODENAME", "")

    # Arch and other rolling distros may not have VERSION_ID
    if not version and distro_id in ("arch", "void", "gentoo"):
        version = "rolling"

    return (distro_id, version, codename)


def _detect_macos() -> tuple[str, str, str]:
    """Detect macOS version and codename."""
    version = platform.mac_ver()[0]  # e.g. "14.2.1"

    # Simplify to major version for lifecycle lookup
    major = version.split(".")[0] if version else ""

    # Map major version to codename
    codenames: dict[str, str] = {
        "15": "sequoia",
        "14": "sonoma",
        "13": "ventura",
        "12": "monterey",
        "11": "big sur",
        "10": "catalina",  # 10.15.x
    }
    codename = codenames.get(major, "")

    return ("macos", major, codename)


# ── OS ranking ──────────────────────────────────────────────────


def _rank_os(distro: str, version: str) -> tuple[RankLevel, str, str]:
    """Rank an OS version against the lifecycle database.

    Returns:
        (rank, detail_string, eol_date)
    """
    os_db = load_os_lifecycle()

    # Look up distro in database
    distro_data = os_db.get(distro)
    if not distro_data:
        return (RankLevel.UNKNOWN, f"Unknown distribution: {distro}", "")

    # Look up version
    version_data = distro_data.get(version)
    if not version_data:
        # Try with just major version (macOS)
        major = version.split(".")[0] if version else ""
        version_data = distro_data.get(major)

    if not version_data:
        if version == "rolling":
            return (RankLevel.CURRENT, "Rolling release (always current)", "")
        return (RankLevel.UNKNOWN, f"Unknown version: {distro} {version}", "")

    eol = version_data.get("eol")
    name = version_data.get("name", "")
    release_type = version_data.get("type", "")

    # Rolling releases have no EOL
    if eol is None:
        return (RankLevel.CURRENT, f"{name} — rolling release", "")

    rank = rank_by_eol(eol)

    if rank == RankLevel.CURRENT:
        detail = f"{name} — supported until {eol}"
    elif rank == RankLevel.AGING:
        detail = f"{name} — EOL {eol}, consider planning upgrade"
    elif rank == RankLevel.OUTDATED:
        detail = f"{name} — EOL {eol}, nearing end of life"
    elif rank == RankLevel.DEPRECATED:
        detail = f"{name} — EOL since {eol}"
    else:
        detail = f"{name} — EOL since {eol}, critical risk"

    if release_type:
        detail += f" ({release_type})"

    return (rank, detail, eol)


# ── glibc detection ─────────────────────────────────────────────


def _detect_glibc() -> str:
    """Detect glibc version using ctypes.

    Same approach as ``pages/install.py::_glibc_version()``.
    Returns version string like "2.35" or "unknown".
    """
    if platform.system() != "Linux":
        return ""  # macOS/Windows don't use glibc

    try:
        import ctypes

        libc = ctypes.CDLL("libc.so.6")
        libc.gnu_get_libc_version.restype = ctypes.c_char_p
        return libc.gnu_get_libc_version().decode()
    except Exception:
        return "unknown"


def _rank_glibc(version: str) -> tuple[RankLevel, str]:
    """Rank glibc version.

    glibc doesn't have formal EOL dates, but very old versions
    prevent running modern pre-compiled binaries.

    Thresholds (based on tool requirements):
        >= 2.31:  Current  (Ubuntu 20.04+, required by most modern tools)
        >= 2.28:  Aging    (Node 18+, Python 3.10+ via uv)
        >= 2.17:  Outdated (CentOS 7 level — many binaries fail)
        < 2.17:   Dangerous
    """
    from ..ranking import parse_semver

    v = parse_semver(version)
    if not v:
        return (RankLevel.UNKNOWN, f"Cannot parse glibc version: {version}")

    # Compare as (major, minor)
    if v >= (2, 31):
        return (RankLevel.CURRENT, f"glibc {version} — modern, all tools supported")
    elif v >= (2, 28):
        return (RankLevel.AGING, f"glibc {version} — Node 18+ works, some tools need ≥2.31")
    elif v >= (2, 17):
        return (RankLevel.OUTDATED, f"glibc {version} — many pre-compiled binaries will fail")
    else:
        return (RankLevel.DANGEROUS, f"glibc {version} — critically old, most tools incompatible")


# ── Kernel detection (reuse existing) ───────────────────────────


def _detect_kernel_safe() -> dict[str, Any]:
    """Safely detect kernel info, falling back on errors.

    Wraps ``tool_install/detection/hardware.detect_kernel()`` with
    a fallback to stdlib ``platform`` on import or runtime errors.
    """
    try:
        from src.core.services.tool_install.detection.hardware import detect_kernel
        return detect_kernel()
    except Exception as exc:
        logger.debug("kernel detection fallback: %s", exc)
        return {
            "version": platform.release(),
            "arch": platform.machine(),
        }


# ── WSL detection (reuse existing) ─────────────────────────────


def _detect_wsl() -> str:
    """Detect if running under WSL and return version string.

    Returns:
        "WSL2", "WSL1", or "" (not WSL).
    """
    if platform.system() != "Linux":
        return ""

    # Check /proc/version for WSL signature
    try:
        proc_version = Path("/proc/version").read_text(encoding="utf-8")
        if "microsoft" in proc_version.lower():
            # WSL2 uses a real Linux kernel with "microsoft" in version
            if "WSL2" in proc_version:
                return "WSL2"
            # Heuristic: WSL2 kernels are typically 5.x+
            m = re.search(r"(\d+)\.", proc_version)
            if m and int(m.group(1)) >= 5:
                return "WSL2"
            return "WSL1"
    except OSError:
        pass

    return ""
