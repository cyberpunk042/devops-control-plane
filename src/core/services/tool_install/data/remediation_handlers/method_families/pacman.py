"""
L0 Data — pacman method-family remediation handlers.

Pure data, no logic.
"""

from __future__ import annotations


_PACMAN_HANDLERS: list[dict] = [
        {
            "pattern": (
                r"error: target not found|"
                r"error: could not find or read package"
            ),
            "failure_id": "pacman_target_not_found",
            "category": "package_manager",
            "label": "Package not found",
            "description": (
                "pacman cannot find the package. The package "
                "database may be stale, or the package may be "
                "in the AUR (not official repos)."
            ),
            "example_stderr": (
                "error: target not found: docker-compose"
            ),
            "options": [
                {
                    "id": "pacman-sync-retry",
                    "label": "Sync database and retry",
                    "description": (
                        "Run pacman -Syy to force-refresh the "
                        "package database, then retry."
                    ),
                    "icon": "🔄",
                    "recommended": True,
                    "strategy": "cleanup_retry",
                    "cleanup_commands": [
                        ["pacman", "-Syy", "--noconfirm"],
                    ],
                },
                {
                    "id": "switch-to-default",
                    "label": "Try alternative install method",
                    "description": (
                        "Use a direct download. The package may "
                        "only be in the AUR."
                    ),
                    "icon": "🔧",
                    "recommended": False,
                    "strategy": "switch_method",
                    "method": "_default",
                },
            ],
        },
        {
            "pattern": (
                r"unable to lock database|"
                r"failed to init transaction|"
                r"could not lock database"
            ),
            "failure_id": "pacman_locked",
            "category": "package_manager",
            "label": "Package database locked",
            "description": (
                "Another pacman process holds the database lock. "
                "Wait for it to finish or remove the stale lock "
                "file at /var/lib/pacman/db.lck."
            ),
            "example_stderr": (
                "error: failed to init transaction "
                "(unable to lock database)"
            ),
            "options": [
                {
                    "id": "wait-retry",
                    "label": "Wait and retry",
                    "description": (
                        "Wait 30 seconds for the lock to release, "
                        "then retry."
                    ),
                    "icon": "⏳",
                    "recommended": True,
                    "strategy": "retry_with_modifier",
                    "modifier": {"wait_seconds": 30, "retry": True},
                },
                {
                    "id": "manual-unlock",
                    "label": "Remove stale lock",
                    "description": (
                        "Remove the lock file if no pacman process "
                        "is running."
                    ),
                    "icon": "🔓",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Check for running pacman processes:\n"
                        "  ps aux | grep pacman\n"
                        "If none are running, remove the lock:\n"
                        "  sudo rm /var/lib/pacman/db.lck"
                    ),
                },
            ],
        },
]
