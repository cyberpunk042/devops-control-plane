"""
L0 Data — apk method-family remediation handlers.

Pure data, no logic.
"""

from __future__ import annotations


_APK_HANDLERS: list[dict] = [
        {
            "pattern": (
                r"unsatisfiable constraints|"
                r"ERROR:.*unable to select packages|"
                r"ERROR:.*is not installable"
            ),
            "failure_id": "apk_unsatisfiable",
            "category": "package_manager",
            "label": "Package not found or dependency conflict",
            "description": (
                "The requested package cannot be found or has "
                "unsatisfiable dependencies. The package may not "
                "be in the configured repositories, or the community "
                "repository may need to be enabled."
            ),
            "example_stderr": (
                "ERROR: unsatisfiable constraints:\n"
                "  docker-compose (missing):\n"
                "    required by: world[docker-compose]"
            ),
            "options": [
                {
                    "id": "apk-update-retry",
                    "label": "Update package index and retry",
                    "description": (
                        "Run apk update to refresh the repository "
                        "index, then retry the install."
                    ),
                    "icon": "🔄",
                    "recommended": True,
                    "strategy": "cleanup_retry",
                    "cleanup_commands": [["apk", "update"]],
                },
                {
                    "id": "apk-enable-community",
                    "label": "Enable community repository",
                    "description": (
                        "Add the Alpine community repository. Many "
                        "packages are only in community, not main."
                    ),
                    "icon": "📦",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Edit /etc/apk/repositories and ensure the "
                        "community repo is uncommented:\n"
                        "  https://dl-cdn.alpinelinux.org/alpine/"
                        "v3.XX/community\n"
                        "Then run: apk update"
                    ),
                },
                {
                    "id": "switch-to-default",
                    "label": "Try alternative install method",
                    "description": (
                        "Use a direct download instead of apk."
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
                r"Unable to lock database|"
                r"unable to obtain lock|"
                r"Failed to lock"
            ),
            "failure_id": "apk_locked",
            "category": "package_manager",
            "label": "Package database locked",
            "description": (
                "Another apk process is using the database. "
                "Wait for it to finish or remove the stale lock."
            ),
            "example_stderr": (
                "ERROR: Unable to lock database: "
                "Resource temporarily unavailable"
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
                        "Manually remove the lock file if no apk "
                        "process is running."
                    ),
                    "icon": "🔓",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Check for running apk processes:\n"
                        "  ps aux | grep apk\n"
                        "If none are running, remove the lock:\n"
                        "  rm -f /lib/apk/db/lock"
                    ),
                },
            ],
        },
]
