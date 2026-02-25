"""
L2 Resolver — Install method selection.

Decides which package manager / method to use for installing a tool.
Transforms recipe data + system profile into concrete commands.
"""

from __future__ import annotations

import logging
import shlex
import shutil
from typing import Any

from src.core.services.tool_install.data.recipes import TOOL_RECIPES

logger = logging.getLogger(__name__)


def _build_pkg_install_cmd(packages: list[str], pm: str) -> list[str]:
    """Build a package-install command for a list of packages.

    Args:
        packages: Package names to install.
        pm: Package manager ID.

    Returns:
        Command list suitable for subprocess.run().
    """
    if pm == "apt":
        return ["apt-get", "install", "-y"] + packages
    if pm == "dnf":
        return ["dnf", "install", "-y"] + packages
    if pm == "yum":
        return ["yum", "install", "-y"] + packages
    if pm == "zypper":
        return ["zypper", "install", "-y"] + packages
    if pm == "apk":
        return ["apk", "add"] + packages
    if pm == "pacman":
        return ["pacman", "-S", "--noconfirm"] + packages
    if pm == "brew":
        return ["brew", "install"] + packages
    # Unknown pm — return a no-op that explains the problem
    logger.error("No install command for package manager: %s", pm)
    return ["echo", f"ERROR: no install command for package manager '{pm}'"]


def _pick_install_method(
    recipe: dict,
    primary_pm: str,
    snap_available: bool,
) -> str | None:
    """Pick the best install method for a recipe on this system.

    Resolution order:
      1. Recipe's ``prefer`` list (respecting system availability)
      2. System's primary package manager (apt, dnf, etc.)
      3. snap (if available)
      4. ``_default`` fallback
      5. Any remaining method whose binary is on PATH

    Args:
        recipe: A TOOL_RECIPES entry.
        primary_pm: The system's primary package manager (e.g. ``"apt"``).
        snap_available: Whether snap is available on this system.

    Returns:
        A key from ``recipe["install"]``, or ``None`` if no method works.
    """
    install = recipe.get("install", {})
    if not install:
        return None

    # 1. Recipe's preferred order (respect availability)
    for method in recipe.get("prefer", []):
        if method not in install:
            continue
        if method == "snap":
            if not snap_available:
                continue
        elif method == "brew":
            if not shutil.which("brew"):
                continue
        elif method not in (primary_pm, "_default"):
            # It's a PM key that doesn't match our system — skip
            continue
        return method

    # 2. System's primary pm
    if primary_pm in install:
        return primary_pm

    # 3. snap
    if snap_available and "snap" in install:
        return "snap"

    # 4. _default
    if "_default" in install:
        return "_default"

    # 5. Any available pm that's on PATH
    for method in install:
        if method.startswith("_"):
            continue
        if shutil.which(method):
            return method

    return None


def _is_batchable(method: str, primary_pm: str) -> bool:
    """Is this install method a system package install that can be batched?"""
    return method == primary_pm


def _extract_packages_from_cmd(cmd: list[str], pm: str) -> list[str]:
    """Extract package names from a package manager install command.

    Args:
        cmd: Full install command (e.g. ``["apt-get", "install", "-y", "git"]``).
        pm: Package manager id.

    Returns:
        List of package name strings.
    """
    if pm in ("apt", "dnf", "yum", "zypper"):
        # apt-get install -y PKG1 PKG2
        return [c for c in cmd[3:] if not c.startswith("-")]
    if pm in ("apk", "brew"):
        # apk add PKG1 / brew install PKG1
        return [c for c in cmd[2:] if not c.startswith("-")]
    if pm == "pacman":
        # pacman -S --noconfirm PKG1
        return [c for c in cmd[3:] if not c.startswith("-")]
    return []


def _wrap_with_env(cmd: list[str], env_setup: str) -> list[str]:
    """Wrap a command with environment setup (e.g. PATH export).

    If the command is already a ``bash -c`` command, prepend the env setup
    to the existing expression. Otherwise wrap the whole thing in ``bash -c``.

    Args:
        cmd: Original command list.
        env_setup: Shell commands to prepend (e.g. ``'export PATH=...'``).

    Returns:
        New command list with env setup prepended.
    """
    if len(cmd) >= 3 and cmd[0] == "bash" and cmd[1] == "-c":
        return ["bash", "-c", f"{env_setup} && {cmd[2]}"]
    plain = " ".join(shlex.quote(c) for c in cmd)
    return ["bash", "-c", f"{env_setup} && {plain}"]


def _pick_method_command(
    method_map: dict,
    system_profile: dict | None = None,
) -> tuple[list[str], str] | None:
    """Resolve a method-keyed command map to (command, method).

    Uses the same method-selection logic as install:
    primary PM → snap → _default → first available.

    Args:
        method_map: E.g. ``{"_default": ["pip", ...], "apt": ["apt-get", ...]}``.
        system_profile: From ``_detect_os()``.  If ``None``, auto-detects.

    Returns:
        ``(command_list, method_key)`` or ``None`` if no method matches.
    """
    if not method_map:
        return None

    if system_profile is None:
        from src.core.services.audit.l0_detection import _detect_os
        system_profile = _detect_os()

    primary_pm = system_profile.get("package_manager", {}).get("primary", "apt")
    snap_available = system_profile.get("package_manager", {}).get("snap_available", False)

    for candidate in (primary_pm, "snap", "_default"):
        if candidate == "snap" and not snap_available:
            continue
        if candidate in method_map:
            return method_map[candidate], candidate

    # Any available key
    for key, cmd in method_map.items():
        if key.startswith("_"):
            continue
        return cmd, key

    return None
