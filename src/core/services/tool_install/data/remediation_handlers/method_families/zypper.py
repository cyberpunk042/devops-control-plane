"""
L0 Data — zypper method-family remediation handlers.

Pure data, no logic.
"""

from __future__ import annotations


_ZYPPER_HANDLERS: list[dict] = [
        {
            "pattern": (
                r"No provider of|"
                r"not found in package names|"
                r"package .* not found"
            ),
            "failure_id": "zypper_not_found",
            "category": "package_manager",
            "label": "Package not found",
            "description": (
                "zypper cannot find the package in any enabled "
                "repository. The repository may need to be added "
                "or refreshed."
            ),
            "example_stderr": (
                "No provider of 'docker-compose' found."
            ),
            "options": [
                {
                    "id": "zypper-refresh-retry",
                    "label": "Refresh repositories and retry",
                    "description": (
                        "Run zypper refresh to update repository "
                        "metadata, then retry."
                    ),
                    "icon": "🔄",
                    "recommended": True,
                    "strategy": "cleanup_retry",
                    "cleanup_commands": [["zypper", "refresh"]],
                },
                {
                    "id": "switch-to-default",
                    "label": "Try alternative install method",
                    "description": (
                        "Use a direct download instead of zypper."
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
                r"System management is locked|"
                r"another zypper process|"
                r"zypp is locked"
            ),
            "failure_id": "zypper_locked",
            "category": "package_manager",
            "label": "Package manager locked",
            "description": (
                "Another zypper or PackageKit process is using "
                "the system package database. Wait for it to "
                "finish."
            ),
            "example_stderr": (
                "System management is locked by the application "
                "with pid 1234 (zypper)."
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
                    "label": "Check and remove lock",
                    "description": (
                        "Identify the process holding the lock and "
                        "wait or kill it."
                    ),
                    "icon": "🔓",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Check what process holds the zypp lock:\n"
                        "  sudo zypper ps\n"
                        "Or remove the PID file if no zypper process "
                        "is running:\n"
                        "  sudo rm /run/zypp.pid"
                    ),
                },
            ],
        },
]
