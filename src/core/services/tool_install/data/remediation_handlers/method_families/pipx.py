"""
L0 Data — pipx method-family remediation handlers.

Pure data, no logic.
"""

from __future__ import annotations


_PIPX_HANDLERS: list[dict] = [
        {
            "pattern": (
                r"No module named ['\"]?venv['\"]?|"
                r"python3-venv.*not installed|"
                r"FileNotFoundError.*venv|"
                r"venv.*required|"
                r"venv.*not found"
            ),
            "failure_id": "pipx_venv_missing",
            "category": "dependency",
            "label": "python3-venv not installed (required by pipx)",
            "description": (
                "pipx creates isolated virtual environments for each "
                "tool it installs. On Debian/Ubuntu, the 'venv' module "
                "is packaged separately as python3-venv. Without it, "
                "pipx cannot create environments and all installs fail."
            ),
            "example_stderr": (
                "Error: Python's venv module is required but not found. "
                "Please install python3-venv."
            ),
            "options": [
                {
                    "id": "install-python3-venv",
                    "label": "Install python3-venv",
                    "description": (
                        "Install the python3-venv package so pipx can "
                        "create isolated environments."
                    ),
                    "icon": "🐍",
                    "recommended": True,
                    "strategy": "install_packages",
                    "packages": {
                        "debian": ["python3-venv"],
                        "rhel": ["python3-libs"],
                        "alpine": ["python3"],
                        "arch": ["python"],
                        "suse": ["python3-base"],
                        "macos": ["python@3"],
                    },
                    "risk": "low",
                },
            ],
        },
        {
            "pattern": (
                r"pipx.*command not found|"
                r"pipx.*No such file or directory|"
                r"pipx: not found"
            ),
            "failure_id": "missing_pipx",
            "category": "dependency",
            "label": "pipx not installed",
            "description": (
                "The pipx tool is not installed on this system. "
                "pipx is needed to install Python CLI tools like "
                "poetry, black, and ruff in isolated environments."
            ),
            "example_stderr": (
                "bash: pipx: command not found"
            ),
            "options": [
                {
                    "id": "install-pipx",
                    "label": "Install pipx",
                    "description": (
                        "Install pipx using the system package manager "
                        "or pip, then retry."
                    ),
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_dep",
                    "dep": "pipx",
                    "risk": "low",
                },
                {
                    "id": "use-pip-instead",
                    "label": "Install with pip instead",
                    "description": (
                        "Skip pipx and use pip to install the tool. "
                        "Less isolation but works without pipx."
                    ),
                    "icon": "🔄",
                    "recommended": False,
                    "strategy": "switch_method",
                    "method": "pip",
                    "risk": "low",
                },
            ],
        },
]
