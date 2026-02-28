"""
L0 Data — apt method-family remediation handlers.

Pure data, no logic.
"""

from __future__ import annotations


_APT_HANDLERS: list[dict] = [
        {
            "pattern": r"Unable to locate package",
            "failure_id": "apt_stale_index",
            "category": "package_manager",
            "label": "Package not found — stale index",
            "description": "apt package index may be outdated.",
            "example_stderr": "E: Unable to locate package ruff",
            "options": [
                {
                    "id": "apt-update-retry",
                    "label": "Update package index and retry",
                    "description": "Run apt-get update, then retry the install",
                    "icon": "🔄",
                    "recommended": True,
                    "strategy": "cleanup_retry",
                    "cleanup_commands": [["apt-get", "update"]],
                },
                {
                    "id": "switch-to-other",
                    "label": "Try alternative install method",
                    "description": "Use a different install method for this tool",
                    "icon": "🔧",
                    "recommended": False,
                    "strategy": "switch_method",
                    "method": "_default",
                },
            ],
        },
        {
            "pattern": r"Could not get lock|dpkg was interrupted",
            "failure_id": "apt_locked",
            "category": "package_manager",
            "label": "Package manager locked",
            "description": "Another process is using apt/dpkg. Wait and retry.",
            "example_stderr": "E: Could not get lock /var/lib/dpkg/lock-frontend",
            "options": [
                {
                    "id": "wait-retry",
                    "label": "Wait and retry",
                    "description": "Wait 30 seconds for the lock to release, then retry",
                    "icon": "⏳",
                    "recommended": True,
                    "strategy": "retry_with_modifier",
                    "modifier": {"wait_seconds": 30, "retry": True},
                },
                {
                    "id": "manual-unlock",
                    "label": "Manual intervention",
                    "description": "Check what process holds the lock",
                    "icon": "🔍",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Check for a running apt/dpkg process:\n"
                        "  sudo lsof /var/lib/dpkg/lock-frontend\n"
                        "  sudo kill <PID> or wait for it to finish"
                    ),
                },
            ],
        },
]
