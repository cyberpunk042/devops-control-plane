"""
L0 Data — yum method-family remediation handlers.

Pure data, no logic.
"""

from __future__ import annotations


_YUM_HANDLERS: list[dict] = [
        {
            "pattern": r"No package .* available",
            "failure_id": "yum_no_package",
            "category": "package_manager",
            "label": "Package not available",
            "description": "Package may not exist in enabled repos.",
            "example_stderr": "No package ruff available.",
            "options": [
                {
                    "id": "enable-epel",
                    "label": "Enable EPEL repository",
                    "description": "Install and enable EPEL for extra packages",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_packages",
                    "packages": "epel",
                },
                {
                    "id": "switch-method",
                    "label": "Try alternative install method",
                    "description": "Use a different install method for this tool",
                    "icon": "🔧",
                    "recommended": False,
                    "strategy": "switch_method",
                    "method": "_default",
                },
            ],
        },
]
