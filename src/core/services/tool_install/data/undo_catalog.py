"""
L0 Data — Undo (rollback) commands for each install method.

Maps install methods to their reverse operation. Templates use
``{package}``, ``{binary_path}``, ``{install_path}``, ``{service}``
placeholders that are resolved at rollback time.
"""

from __future__ import annotations

UNDO_COMMANDS: dict[str, dict] = {
    "pip": {
        "command": ["pip", "uninstall", "-y", "{package}"],
        "needs_sudo": False,
    },
    "pip_global": {
        "command": ["pip", "uninstall", "-y", "{package}"],
        "needs_sudo": True,
    },
    "apt": {
        "command": ["apt-get", "purge", "-y", "{package}"],
        "needs_sudo": True,
    },
    "dnf": {
        "command": ["dnf", "remove", "-y", "{package}"],
        "needs_sudo": True,
    },
    "pacman": {
        "command": ["pacman", "-Rns", "--noconfirm", "{package}"],
        "needs_sudo": True,
    },
    "apk": {
        "command": ["apk", "del", "{package}"],
        "needs_sudo": True,
    },
    "brew": {
        "command": ["brew", "uninstall", "{package}"],
        "needs_sudo": False,
    },
    "snap": {
        "command": ["snap", "remove", "{package}"],
        "needs_sudo": True,
    },
    "npm": {
        "command": ["npm", "uninstall", "-g", "{package}"],
        "needs_sudo": False,
    },
    "cargo": {
        "command": ["cargo", "uninstall", "{package}"],
        "needs_sudo": False,
    },
    "go": {
        "command": ["rm", "{binary_path}"],
        "needs_sudo": False,
    },
    "binary": {
        "command": ["rm", "{install_path}"],
        "needs_sudo": True,
    },
    "systemctl_enable": {
        "command": ["systemctl", "disable", "{service}"],
        "needs_sudo": True,
    },
    "systemctl_start": {
        "command": ["systemctl", "stop", "{service}"],
        "needs_sudo": True,
    },
}
