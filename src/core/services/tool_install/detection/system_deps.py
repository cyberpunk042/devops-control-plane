"""
L3 Detection — System dependency checking.

Read-only probes for package/binary availability.
Uses subprocess for package manager queries.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)


def _is_pkg_installed(pkg: str, pkg_manager: str) -> bool:
    """Check if a single system package is installed.

    Uses the appropriate checker for the given package manager:
      apt    → dpkg-query -W -f='${Status}' PKG
      dnf    → rpm -q PKG
      yum    → rpm -q PKG
      zypper → rpm -q PKG
      apk    → apk info -e PKG
      pacman → pacman -Q PKG
      brew   → brew ls --versions PKG

    Args:
        pkg: Exact package name (must match the distro's naming).
        pkg_manager: One of: apt, dnf, yum, zypper, apk, pacman, brew.

    Returns:
        True if installed, False if not installed or check failed.
    """
    try:
        if pkg_manager == "apt":
            r = subprocess.run(
                ["dpkg-query", "-W", "-f=${Status}", pkg],
                capture_output=True, text=True, timeout=10,
            )
            return "install ok installed" in r.stdout

        if pkg_manager in ("dnf", "yum", "zypper"):
            r = subprocess.run(
                ["rpm", "-q", pkg],
                capture_output=True, timeout=10,
            )
            return r.returncode == 0

        if pkg_manager == "apk":
            r = subprocess.run(
                ["apk", "info", "-e", pkg],
                capture_output=True, timeout=10,
            )
            return r.returncode == 0

        if pkg_manager == "pacman":
            r = subprocess.run(
                ["pacman", "-Q", pkg],
                capture_output=True, timeout=10,
            )
            return r.returncode == 0

        if pkg_manager == "brew":
            r = subprocess.run(
                ["brew", "ls", "--versions", pkg],
                capture_output=True, timeout=30,  # brew is slow
            )
            return r.returncode == 0

    except FileNotFoundError:
        # Checker binary not on PATH (e.g. dpkg-query on Fedora)
        logger.warning(
            "Package checker not found for pm=%s (checking %s)",
            pkg_manager, pkg,
        )
    except subprocess.TimeoutExpired:
        logger.warning(
            "Timeout checking package %s with pm=%s",
            pkg, pkg_manager,
        )
    except OSError as exc:
        logger.warning(
            "OS error checking package %s with pm=%s: %s",
            pkg, pkg_manager, exc,
        )

    return False


def check_system_deps(
    packages: list[str],
    pkg_manager: str = "apt",
) -> dict[str, list[str]]:
    """Check which system packages are installed.

    Args:
        packages: Package names to check. Names must match the target
                  distro's naming convention (e.g. "libssl-dev" for Debian,
                  "openssl-devel" for RHEL).
        pkg_manager: Which package manager to use for checking.
                     Defaults to "apt" for backward compatibility.

    Returns:
        {"missing": ["pkg1", ...], "installed": ["pkg2", ...]}
    """
    # ── L4: Brew batch optimization ──────────────────────────
    if pkg_manager == "brew" and len(packages) > 1:
        return _check_brew_batch(packages)

    missing: list[str] = []
    installed: list[str] = []
    for pkg in packages:
        if _is_pkg_installed(pkg, pkg_manager):
            installed.append(pkg)
        else:
            missing.append(pkg)
    return {"missing": missing, "installed": installed}


def _check_brew_batch(packages: list[str]) -> dict[str, list[str]]:
    """Batch-check brew packages in a single call.

    ``brew ls --versions pkg1 pkg2 pkg3`` returns one line per *installed*
    package (e.g. ``pkg1 1.2.3``). Missing packages produce no output line.
    Much faster than N individual ``brew ls --versions`` calls.
    """
    installed: list[str] = []
    missing: list[str] = list(packages)

    try:
        cmd = ["brew", "ls", "--versions"] + list(packages)
        r = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=30,
        )
        # Parse output: each line is "pkgname version(s)"
        installed_names = set()
        for line in r.stdout.strip().splitlines():
            parts = line.strip().split()
            if parts:
                installed_names.add(parts[0])

        installed = [p for p in packages if p in installed_names]
        missing = [p for p in packages if p not in installed_names]

    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("Brew batch check failed: %s. Falling back to individual checks.", exc)
        # Fall back to individual checks
        installed = []
        missing = []
        for pkg in packages:
            if _is_pkg_installed(pkg, "brew"):
                installed.append(pkg)
            else:
                missing.append(pkg)

    return {"missing": missing, "installed": installed}
