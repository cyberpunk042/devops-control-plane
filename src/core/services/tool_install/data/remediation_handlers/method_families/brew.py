"""
L0 Data — brew method-family remediation handlers.

Pure data, no logic.
"""

from __future__ import annotations


_BREW_HANDLERS: list[dict] = [
        {
            "pattern": r"No formulae found|No available formula",
            "failure_id": "brew_no_formula",
            "category": "package_manager",
            "label": "Homebrew formula not found",
            "description": "This tool isn't available via Homebrew.",
            "example_stderr": "Error: No formulae found for \"ruff\".",
            "options": [
                {
                    "id": "switch-default",
                    "label": "Install via direct download",
                    "description": "Use the default install script or binary release",
                    "icon": "🌐",
                    "recommended": True,
                    "strategy": "switch_method",
                    "method": "_default",
                },
                {
                    "id": "switch-pip",
                    "label": "Install via pip",
                    "description": "Use pip if this is a Python tool",
                    "icon": "🐍",
                    "recommended": False,
                    "strategy": "switch_method",
                    "method": "pip",
                },
            ],
        },
]
