"""
L2 Resolver — Dynamic dependency resolution.

Resolves dependency names to install commands when no TOOL_RECIPES entry
exists. Uses a 4-tier strategy:

  1. Recipe lookup  — TOOL_RECIPES (delegates back to normal path)
  2. Known packages — KNOWN_PACKAGES (manually verified per PM)
  3. Library mapping — LIB_TO_PACKAGE_MAP (C library → dev package)
  4. Identity        — assume dep name = package name (medium confidence)

No I/O, no subprocess. Only references to static data and shutil.which.
"""

from __future__ import annotations

import logging
import shutil
from typing import Any

from src.core.services.tool_install.data.recipes import TOOL_RECIPES
from src.core.services.tool_install.data.remediation_handlers import (
    LIB_TO_PACKAGE_MAP,
)

logger = logging.getLogger(__name__)


# ── PM install command templates ─────────────────────────────────

_PM_INSTALL_CMD: dict[str, list[str]] = {
    "apt":    ["apt-get", "install", "-y"],
    "dnf":    ["dnf", "install", "-y"],
    "apk":    ["apk", "add"],
    "pacman": ["pacman", "-S", "--noconfirm"],
    "zypper": ["zypper", "install", "-y"],
    "brew":   ["brew", "install"],
}


# ── PM → distro family mapping (for LIB_TO_PACKAGE_MAP lookup) ──

_PM_TO_FAMILY: dict[str, str] = {
    "apt":    "debian",
    "dnf":    "rhel",
    "apk":    "alpine",
    "pacman": "arch",
    "zypper": "suse",
    "brew":   "macos",
}


# ═══════════════════════════════════════════════════════════════════
# KNOWN_PACKAGES — manually verified per package manager
# ═══════════════════════════════════════════════════════════════════
#
# Keys are binary/tool names (what you'd pass to shutil.which).
# Values are dicts mapping PM name → package name(s).
#
# If the value for a PM is a list, ALL packages in the list are needed.
# If the key "_install_cmd" exists, it's a standalone install command
# (for tools that aren't in any system package repo).

KNOWN_PACKAGES: dict[str, dict[str, str | list[str]]] = {
    # ── System utilities ────────────────────────────────────────
    "curl": {
        "apt": "curl", "dnf": "curl", "apk": "curl",
        "pacman": "curl", "zypper": "curl", "brew": "curl",
    },
    "wget": {
        "apt": "wget", "dnf": "wget", "apk": "wget",
        "pacman": "wget", "zypper": "wget", "brew": "wget",
    },
    "unzip": {
        "apt": "unzip", "dnf": "unzip", "apk": "unzip",
        "pacman": "unzip", "zypper": "unzip", "brew": "unzip",
    },
    "tar": {
        "apt": "tar", "dnf": "tar", "apk": "tar",
        "pacman": "tar", "zypper": "tar", "brew": "gnu-tar",
    },
    "jq": {
        "apt": "jq", "dnf": "jq", "apk": "jq",
        "pacman": "jq", "zypper": "jq", "brew": "jq",
    },
    "git": {
        "apt": "git", "dnf": "git", "apk": "git",
        "pacman": "git", "zypper": "git", "brew": "git",
    },
    "make": {
        "apt": "make", "dnf": "make", "apk": "make",
        "pacman": "make", "zypper": "make", "brew": "make",
    },
    "gcc": {
        "apt": "gcc", "dnf": "gcc", "apk": "gcc",
        "pacman": "gcc", "zypper": "gcc", "brew": "gcc",
    },
    "g++": {
        "apt": "g++", "dnf": "gcc-c++", "apk": "g++",
        "pacman": "gcc", "zypper": "gcc-c++", "brew": "gcc",
    },
    "cmake": {
        "apt": "cmake", "dnf": "cmake", "apk": "cmake",
        "pacman": "cmake", "zypper": "cmake", "brew": "cmake",
    },
    "tree": {
        "apt": "tree", "dnf": "tree", "apk": "tree",
        "pacman": "tree", "zypper": "tree", "brew": "tree",
    },
    "htop": {
        "apt": "htop", "dnf": "htop", "apk": "htop",
        "pacman": "htop", "zypper": "htop", "brew": "htop",
    },
    "tmux": {
        "apt": "tmux", "dnf": "tmux", "apk": "tmux",
        "pacman": "tmux", "zypper": "tmux", "brew": "tmux",
    },
    "rsync": {
        "apt": "rsync", "dnf": "rsync", "apk": "rsync",
        "pacman": "rsync", "zypper": "rsync", "brew": "rsync",
    },
    "socat": {
        "apt": "socat", "dnf": "socat", "apk": "socat",
        "pacman": "socat", "zypper": "socat", "brew": "socat",
    },
    "strace": {
        "apt": "strace", "dnf": "strace", "apk": "strace",
        "pacman": "strace", "zypper": "strace", "brew": "strace",
    },
    "xz": {
        "apt": "xz-utils", "dnf": "xz", "apk": "xz",
        "pacman": "xz", "zypper": "xz", "brew": "xz",
    },
    "zstd": {
        "apt": "zstd", "dnf": "zstd", "apk": "zstd",
        "pacman": "zstd", "zypper": "zstd", "brew": "zstd",
    },
    "gpg": {
        "apt": "gnupg", "dnf": "gnupg2", "apk": "gnupg",
        "pacman": "gnupg", "zypper": "gpg2", "brew": "gnupg",
    },
    "kubectl": {
        "apt": "kubectl", "dnf": "kubernetes-client", "apk": "kubectl",
        "pacman": "kubectl", "zypper": "kubernetes-client", "brew": "kubectl",
    },
    "yarn": {
        "apt": "yarn", "dnf": "yarnpkg", "apk": "yarn",
        "pacman": "yarn", "zypper": "yarn", "brew": "yarn",
    },
    "poetry": {
        "apt": "python3-poetry", "dnf": "python3-poetry",
        "pacman": "python-poetry", "brew": "poetry",
    },
    "pipx": {
        "apt": "pipx", "dnf": "pipx", "apk": "pipx",
        "pacman": "python-pipx", "zypper": "python3-pipx",
        "brew": "pipx",
    },
    "bash": {
        "apt": "bash", "dnf": "bash", "apk": "bash",
        "pacman": "bash", "zypper": "bash", "brew": "bash",
    },
    "file": {
        "apt": "file", "dnf": "file", "apk": "file",
        "pacman": "file", "zypper": "file", "brew": "file-formula",
    },
    "patch": {
        "apt": "patch", "dnf": "patch", "apk": "patch",
        "pacman": "patch", "zypper": "patch", "brew": "gpatch",
    },
    "sudo": {
        "apt": "sudo", "dnf": "sudo", "apk": "sudo",
        "pacman": "sudo", "zypper": "sudo",
    },
    "pkg-config": {
        "apt": "pkg-config", "dnf": "pkgconf-pkg-config", "apk": "pkgconf",
        "pacman": "pkgconf", "zypper": "pkg-config", "brew": "pkg-config",
    },
    "autoconf": {
        "apt": "autoconf", "dnf": "autoconf", "apk": "autoconf",
        "pacman": "autoconf", "zypper": "autoconf", "brew": "autoconf",
    },
    "automake": {
        "apt": "automake", "dnf": "automake", "apk": "automake",
        "pacman": "automake", "zypper": "automake", "brew": "automake",
    },
    "libtool": {
        "apt": "libtool", "dnf": "libtool", "apk": "libtool",
        "pacman": "libtool", "zypper": "libtool", "brew": "libtool",
    },
    "ninja": {
        "apt": "ninja-build", "dnf": "ninja-build", "apk": "samurai",
        "pacman": "ninja", "zypper": "ninja", "brew": "ninja",
    },

    # ── Tools where package name differs from binary name ───────
    "pip": {
        "apt": "python3-pip", "dnf": "python3-pip",
        "apk": "py3-pip", "pacman": "python-pip",
        "zypper": "python3-pip", "brew": "python3",
    },
    "pip3": {
        "apt": "python3-pip", "dnf": "python3-pip",
        "apk": "py3-pip", "pacman": "python-pip",
        "zypper": "python3-pip", "brew": "python3",
    },
    "pipx": {
        "apt": "pipx", "dnf": "pipx",
        "apk": "pipx", "pacman": "python-pipx",
        "zypper": "python3-pipx", "brew": "pipx",
    },
    "python3": {
        "apt": "python3", "dnf": "python3",
        "apk": "python3", "pacman": "python",
        "zypper": "python3", "brew": "python@3",
    },
    "python3-venv": {
        "apt": "python3-venv", "dnf": "python3-venv",
        "apk": "python3", "pacman": "python",
        "zypper": "python3", "brew": "python@3",
    },
    "cargo": {
        "apt": "cargo", "dnf": "cargo",
        "apk": "cargo", "pacman": "rustup",
        "zypper": "cargo", "brew": "rustup",
    },
    "node": {
        "apt": "nodejs", "dnf": "nodejs",
        "apk": "nodejs", "pacman": "nodejs",
        "zypper": "nodejs20", "brew": "node",
    },
    "npm": {
        "apt": "npm", "dnf": "npm",
        "apk": "npm", "pacman": "npm",
        "zypper": "npm20", "brew": "node",
    },
    "ruby": {
        "apt": "ruby-full", "dnf": "ruby",
        "apk": "ruby", "pacman": "ruby",
        "zypper": "ruby", "brew": "ruby",
    },
    "php": {
        "apt": "php-cli", "dnf": "php-cli",
        "apk": "php", "pacman": "php",
        "zypper": "php8", "brew": "php",
    },
    "go": {
        "apt": "golang-go", "dnf": "golang",
        "apk": "go", "pacman": "go",
        "zypper": "go", "brew": "go",
        "snap": "go",
    },
    "docker": {
        "apt": "docker.io", "dnf": "docker",
        "apk": "docker", "pacman": "docker",
        "zypper": "docker", "brew": "docker",
    },
    "docker-compose": {
        "apt": "docker-compose-plugin",
        "dnf": "docker-compose-plugin",
        "apk": "docker-cli-compose",
        "pacman": "docker-compose",
        "zypper": "docker-compose",
        "brew": "docker-compose",
    },
    "clang": {
        "apt": "clang", "dnf": "clang",
        "apk": "clang", "pacman": "clang",
        "zypper": "clang", "brew": "llvm",
    },
    "sqlite3": {
        "apt": "sqlite3", "dnf": "sqlite",
        "apk": "sqlite", "pacman": "sqlite",
        "zypper": "sqlite3", "brew": "sqlite",
    },
    "erl": {
        "apt": "erlang", "dnf": "erlang",
        "apk": "erlang", "pacman": "erlang",
        "zypper": "erlang", "brew": "erlang",
    },
    "lua": {
        "apt": "lua5.4", "dnf": "lua",
        "apk": "lua", "pacman": "lua",
        "zypper": "lua", "brew": "lua",
    },

    # ── Build dependency meta-packages ──────────────────────────
    "build-essential": {
        "apt": "build-essential",
        "dnf": ["gcc", "gcc-c++", "make"],
        "apk": "build-base",
        "pacman": "base-devel",
        "zypper": ["gcc", "gcc-c++", "make"],
        "brew": ["gcc", "make"],
    },

    # ── Not in system repos — standalone installers ─────────────
    "rustup": {
        "_install_cmd": (
            "curl --proto '=https' --tlsv1.2 -sSf"
            " https://sh.rustup.rs | sh -s -- -y"
        ),
    },
    "nvm": {
        "_install_cmd": (
            "curl -o-"
            " https://raw.githubusercontent.com/nvm-sh/nvm/HEAD/install.sh"
            " | bash"
        ),
    },
}


# ═══════════════════════════════════════════════════════════════════
# Shared package groups
# ═══════════════════════════════════════════════════════════════════
#
# Named package sets used by `install_packages` strategy options.
# Handlers reference a group by name (string) instead of duplicating
# the family→packages mapping.  The resolver expands the string to
# a dict at availability-check / execution time.
#
# Keys: distro *family* names (not PM names) because handler
# `packages` dicts are already keyed by family.

PACKAGE_GROUPS: dict[str, dict[str, list[str]]] = {
    "build_tools": {
        "debian": ["build-essential"],
        "rhel": ["gcc", "gcc-c++", "make"],
        "alpine": ["build-base"],
        "arch": ["base-devel"],
        "suse": ["gcc", "gcc-c++", "make"],
        "macos": ["gcc"],
    },
    "node_build_tools": {
        "debian": ["build-essential", "python3"],
        "rhel": ["gcc", "gcc-c++", "make", "python3"],
        "alpine": ["build-base", "python3"],
        "arch": ["base-devel", "python"],
        "suse": ["gcc", "gcc-c++", "make", "python3"],
        "macos": ["python3"],
    },
    "epel": {
        "rhel": ["epel-release"],
    },
}


def resolve_package_group(packages):
    """Expand a string package-group reference to its dict.

    If *packages* is already a dict, return it unchanged.
    If it is a string, look it up in ``PACKAGE_GROUPS``.
    Raises ``KeyError`` if the name is unknown.
    """
    if isinstance(packages, dict):
        return packages
    return PACKAGE_GROUPS[packages]


# ═══════════════════════════════════════════════════════════════════
# Core resolver
# ═══════════════════════════════════════════════════════════════════

def resolve_dep_install(
    dep: str,
    system_profile: dict[str, Any],
) -> dict[str, Any] | None:
    """Resolve how to install a dependency on this system.

    Resolution order:
      1. TOOL_RECIPES  — full recipe with install methods
      2. KNOWN_PACKAGES — common tools with per-PM package names
      3. LIB_TO_PACKAGE_MAP — C library mappings by distro family
      4. Identity — assume dep name = package name

    Args:
        dep: Dependency name (binary name, tool ID, or lib short name).
        system_profile: Phase 1 ``_detect_os()`` output.

    Returns:
        Resolution dict or None if truly unresolvable::

            {
                "dep": "unzip",
                "source": "recipe" | "known_package" | "lib_mapping"
                          | "identity" | "special_installer",
                "package_names": ["unzip"],
                "install_cmd": ["apt-get", "install", "-y", "unzip"],
                "needs_sudo": True,
                "pm": "apt",
                "confidence": "high" | "medium",
                "notes": None | "Using identity mapping — verify ...",
            }
    """
    if not dep:
        return None

    pm = system_profile.get("package_manager", {}).get("primary", "apt")
    family = system_profile.get("distro", {}).get("family", "debian")

    # ── Tier 1: Recipe lookup ──────────────────────────────────
    recipe = TOOL_RECIPES.get(dep)
    if recipe:
        return {
            "dep": dep,
            "source": "recipe",
            "package_names": [],
            "install_cmd": [],
            "needs_sudo": False,
            "pm": None,
            "confidence": "high",
            "notes": None,
        }

    # ── Tier 2: Known packages ─────────────────────────────────
    known = KNOWN_PACKAGES.get(dep)
    if known:
        # Special installer (rustup, nvm — not in any repo)
        if "_install_cmd" in known:
            return {
                "dep": dep,
                "source": "special_installer",
                "package_names": [],
                "install_cmd": known["_install_cmd"],
                "needs_sudo": False,
                "pm": None,
                "confidence": "high",
                "notes": f"Uses standalone installer script",
            }

        pkg_value = known.get(pm)
        if pkg_value is None:
            # PM not in the mapping — can't resolve for this system
            logger.debug(
                "KNOWN_PACKAGES has '%s' but not for pm='%s'", dep, pm,
            )
            # Fall through to identity mapping
        else:
            pkg_names = [pkg_value] if isinstance(pkg_value, str) else list(pkg_value)
            return {
                "dep": dep,
                "source": "known_package",
                "package_names": pkg_names,
                "install_cmd": _build_install_cmd(pm, pkg_names, system_profile),
                "needs_sudo": _needs_sudo(pm, system_profile),
                "pm": pm,
                "confidence": "high",
                "notes": None,
            }

    # ── Tier 3: Library mapping ────────────────────────────────
    lib_map = LIB_TO_PACKAGE_MAP.get(dep)
    if lib_map:
        # LIB_TO_PACKAGE_MAP is keyed by distro family, not PM
        pkg_name = lib_map.get(family)
        if pkg_name:
            pkg_names = [pkg_name] if isinstance(pkg_name, str) else list(pkg_name)
            return {
                "dep": dep,
                "source": "lib_mapping",
                "package_names": pkg_names,
                "install_cmd": _build_install_cmd(pm, pkg_names, system_profile),
                "needs_sudo": _needs_sudo(pm, system_profile),
                "pm": pm,
                "confidence": "high",
                "notes": f"C library '{dep}' mapped to {pkg_names}",
            }
        else:
            logger.debug(
                "LIB_TO_PACKAGE_MAP has '%s' but not for family='%s'",
                dep, family,
            )

    # ── Tier 4: Identity mapping ───────────────────────────────
    # Assume the dep name IS the package name. Works for ~80% of
    # system packages (curl, wget, git, jq, htop, etc.)
    if pm in _PM_INSTALL_CMD:
        return {
            "dep": dep,
            "source": "identity",
            "package_names": [dep],
            "install_cmd": _build_install_cmd(pm, [dep], system_profile),
            "needs_sudo": _needs_sudo(pm, system_profile),
            "pm": pm,
            "confidence": "medium",
            "notes": (
                f"Package name assumed to be '{dep}'. "
                f"If install fails, verify the correct package name "
                f"for your system."
            ),
        }

    # ── No resolution possible ─────────────────────────────────
    return None


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _build_install_cmd(
    pm: str,
    package_names: list[str],
    system_profile: dict[str, Any],
) -> list[str]:
    """Build the install command list for the given PM and packages.

    Returns a list suitable for ``subprocess.run()``.
    """
    base = list(_PM_INSTALL_CMD.get(pm, ["echo", "unknown-pm"]))
    if _needs_sudo(pm, system_profile):
        base = ["sudo"] + base
    return base + package_names


def _needs_sudo(pm: str, system_profile: dict[str, Any]) -> bool:
    """Determine if the PM command needs sudo on this system."""
    capabilities = system_profile.get("capabilities", {})

    # Root user — never needs sudo
    if capabilities.get("is_root", False):
        return False

    # brew should never run as root/sudo
    if pm == "brew":
        return False

    # System PMs need sudo when not root
    return True
