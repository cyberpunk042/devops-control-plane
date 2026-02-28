"""
L0 Data — _default method-family remediation handlers.

Pure data, no logic.
"""

from __future__ import annotations


_DEFAULT_HANDLERS: list[dict] = [
        {
            "pattern": r"curl:\s*command not found|curl:\s*not found",
            "failure_id": "missing_curl",
            "category": "dependency",
            "label": "curl not installed",
            "description": "curl is required to download the install script.",
            "example_stderr": "bash: curl: command not found",
            "options": [
                {
                    "id": "install-curl",
                    "label": "Install curl",
                    "description": "Install curl via system package manager",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_dep",
                    "dep": "curl",
                },
                {
                    "id": "use-wget",
                    "label": "Use wget instead",
                    "description": "Try downloading with wget instead of curl",
                    "icon": "🔧",
                    "recommended": False,
                    "strategy": "retry_with_modifier",
                    "modifier": {"substitute_curl_with_wget": True},
                    "requires_binary": "wget",
                },
                {
                    "id": "use-python3-urllib",
                    "label": "Use python3 urllib instead",
                    "description": (
                        "Download using Python's built-in urllib "
                        "(independent of libcurl)"
                    ),
                    "icon": "🐍",
                    "recommended": False,
                    "strategy": "retry_with_modifier",
                    "modifier": {"substitute_curl_with_python3": True},
                    "requires_binary": "python3",
                },
            ],
        },
        {
            "pattern": r"git:\s*command not found|git:\s*not found",
            "failure_id": "missing_git",
            "category": "dependency",
            "label": "git not installed",
            "description": "git is required to clone the source repository.",
            "example_stderr": "bash: git: command not found",
            "options": [
                {
                    "id": "install-git",
                    "label": "Install git",
                    "description": "Install git via system package manager",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_dep",
                    "dep": "git",
                },
            ],
        },
        {
            "pattern": r"wget:\s*command not found|wget:\s*not found",
            "failure_id": "missing_wget",
            "category": "dependency",
            "label": "wget not installed",
            "description": "wget is required to download files.",
            "example_stderr": "bash: wget: command not found",
            "options": [
                {
                    "id": "install-wget",
                    "label": "Install wget",
                    "description": "Install wget via system package manager",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_dep",
                    "dep": "wget",
                },
            ],
        },
        {
            "pattern": r"unzip:\s*command not found|unzip:\s*not found",
            "failure_id": "missing_unzip",
            "category": "dependency",
            "label": "unzip not installed",
            "description": "unzip is required to extract downloaded archives.",
            "example_stderr": "bash: unzip: command not found",
            "options": [
                {
                    "id": "install-unzip",
                    "label": "Install unzip",
                    "description": "Install unzip via system package manager",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_dep",
                    "dep": "unzip",
                },
            ],
        },
        {
            "pattern": r"npm:\s*command not found|npm:\s*not found",
            "failure_id": "missing_npm_default",
            "category": "dependency",
            "label": "npm not installed",
            "description": "npm is required to install this package.",
            "example_stderr": "bash: npm: command not found",
            "options": [
                {
                    "id": "install-npm",
                    "label": "Install npm via system packages",
                    "description": "Use the OS package manager to install Node.js + npm",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_dep",
                    "dep": "npm",
                },
                {
                    "id": "install-nvm",
                    "label": "Install via nvm (Node Version Manager)",
                    "description": "Install nvm for flexible Node.js version management",
                    "icon": "🌐",
                    "recommended": False,
                    "strategy": "install_dep",
                    "dep": "nvm",
                },
            ],
        },
]
