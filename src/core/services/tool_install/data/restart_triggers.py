"""
L0 Data — Restart trigger categories.

Maps restart types to the conditions that trigger them.
"""

from __future__ import annotations

RESTART_TRIGGERS: dict[str, list[str]] = {
    "shell_restart": [
        "PATH modification",
        "Shell config change (.bashrc, .zshrc)",
        "New binary in non-standard directory",
    ],
    "service_restart": [
        "Config file changed",
        "Service installation",
        "Module loaded/unloaded",
    ],
    "reboot_required": [
        "Kernel module installed (DKMS)",
        "GPU driver installed",
        "Kernel updated",
        "Secure Boot key enrolled",
    ],
}
