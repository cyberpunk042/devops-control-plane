"""
L2 Resolver — Install method selection.

Decides which package manager / method to use for installing a tool.
Transforms recipe data + system profile into concrete commands.
"""

from __future__ import annotations

import logging
import platform
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
        elif method == "_default":
            # _default may be a dict keyed by OS (linux/darwin).
            # If so, only select it when the current OS has a variant.
            default_val = install["_default"]
            if isinstance(default_val, dict):
                current_os = platform.system().lower()
                if current_os not in default_val:
                    continue
        elif method != primary_pm:
            # It's a PM key that doesn't match our system — skip
            continue
        return method

    # 2. System's primary pm
    if primary_pm in install:
        return primary_pm

    # 3. snap
    if snap_available and "snap" in install:
        return "snap"

    # 4. _default (same OS gating as above)
    if "_default" in install:
        default_val = install["_default"]
        if isinstance(default_val, dict):
            current_os = platform.system().lower()
            if current_os in default_val:
                return "_default"
        else:
            return "_default"

    # 5. source (last-resort — needs compiler + build tools)
    if "source" in install:
        return "source"

    # 6. Any available pm that's on PATH
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


# ═══════════════════════════════════════════════════════════════════
# Update command derivation
# ═══════════════════════════════════════════════════════════════════
#
# Standard PM-based update commands are derivable from install commands.
# Only PM methods are derivable — _default and source are NOT because
# binary-download updates vary wildly between tools.

# PM → (install_verb, update_verb, extra_flags)
# The derivation replaces `install_verb` with `update_verb` in the command.
_PM_UPDATE_RULES: dict[str, tuple[str, str, list[str]]] = {
    # apt-get install -y PKG  →  apt-get install --only-upgrade -y PKG
    "apt":    ("install", "install", ["--only-upgrade"]),
    # dnf install -y PKG  →  dnf upgrade -y PKG
    "dnf":    ("install", "upgrade", []),
    # yum install -y PKG  →  yum update -y PKG
    "yum":    ("install", "update", []),
    # apk add PKG  →  apk upgrade PKG
    "apk":    ("add", "upgrade", []),
    # pacman -S --noconfirm PKG  →  pacman -S --noconfirm PKG (same)
    "pacman": ("-S", "-S", []),
    # zypper install -y PKG  →  zypper update -y PKG
    "zypper": ("install", "update", []),
    # brew install PKG  →  brew upgrade PKG
    "brew":   ("install", "upgrade", []),
    # snap install PKG  →  snap refresh PKG
    "snap":   ("install", "refresh", []),
}

# Methods that are NOT derivable — each tool's update is unique
_NON_DERIVABLE_METHODS = {"_default", "source", "pip", "npm", "cargo"}


def _derive_update_cmd(
    install_cmd: list[str],
    pm: str,
) -> list[str] | None:
    """Derive an update command from an install command for a given PM.

    Returns ``None`` if the PM has no derivation rule or the command
    doesn't match the expected pattern.
    """
    rule = _PM_UPDATE_RULES.get(pm)
    if not rule:
        return None

    install_verb, update_verb, extra_flags = rule

    # Find and replace the verb
    cmd = list(install_cmd)  # copy
    try:
        idx = cmd.index(install_verb)
    except ValueError:
        # Command doesn't contain expected verb — can't derive
        return None

    cmd[idx] = update_verb

    # Insert extra flags right after the verb
    if extra_flags:
        for i, flag in enumerate(extra_flags):
            cmd.insert(idx + 1 + i, flag)

    # Strip install-only flags that don't apply to update
    if pm == "snap":
        # --classic, --channel flags are install-time only
        cmd = [c for c in cmd if c not in (
            "--classic", "--edge", "--beta", "--candidate",
        )]

    return cmd


def get_update_map(recipe: dict) -> dict[str, list[str]]:
    """Get the update command map for a recipe.

    Resolution:
      1. Recipe's explicit ``update`` map (returned as-is if present)
      2. Derived from ``install`` map for standard PM methods

    Only PM methods are derived. ``_default``, ``source``, and language
    PMs (pip, npm, cargo) are excluded because their update commands
    are tool-specific and not derivable.

    Returns:
        Method→command dict.  May be empty if no methods are derivable
        and no explicit update exists.
    """
    explicit = recipe.get("update")
    if explicit:
        return explicit

    install = recipe.get("install", {})
    if not install:
        return {}

    derived: dict[str, list[str]] = {}
    for method, cmd in install.items():
        if method in _NON_DERIVABLE_METHODS:
            continue
        if not isinstance(cmd, list):
            continue
        update_cmd = _derive_update_cmd(cmd, method)
        if update_cmd:
            derived[method] = update_cmd

    return derived
