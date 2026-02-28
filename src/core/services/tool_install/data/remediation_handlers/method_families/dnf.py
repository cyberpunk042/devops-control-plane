"""
L0 Data — dnf method-family remediation handlers.

Pure data, no logic.
"""

from __future__ import annotations


_DNF_HANDLERS: list[dict] = [
        {
            "pattern": r"No match for argument",
            "failure_id": "dnf_no_match",
            "category": "package_manager",
            "label": "Package not found",
            "description": "Package name may differ on this distro/version.",
            "example_stderr": "Error: No match for argument: ruff",
            "options": [
                {
                    "id": "enable-epel",
                    "label": "Enable EPEL repository",
                    "description": "Install and enable EPEL for extra packages",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_packages",
                    "packages": {
                        "rhel": ["epel-release"],
                    },
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
