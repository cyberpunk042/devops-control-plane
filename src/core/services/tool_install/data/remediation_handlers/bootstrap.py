"""
L0 Data — Bootstrap failure handlers (Layer 0).

Lowest-level failures: no package manager, no shell.
Pure data, no logic.
"""

from __future__ import annotations


BOOTSTRAP_HANDLERS: list[dict] = [
    {
        "pattern": (
            r"apt-get:\s*command not found|"
            r"dnf:\s*command not found|"
            r"apk:\s*command not found|"
            r"pacman:\s*command not found"
        ),
        "failure_id": "no_package_manager",
        "category": "bootstrap",
        "label": "No package manager found",
        "description": (
            "No system package manager is available. "
            "This system may be a minimal container or custom build."
        ),
        "example_stderr": "bash: apt-get: command not found",
        "options": [
            {
                "id": "install-brew",
                "label": "Install Homebrew",
                "description": "Install Homebrew (works on Linux and macOS)",
                "icon": "🍺",
                "recommended": True,
                "strategy": "env_fix",
                "fix_commands": [
                    ["bash", "-c",
                     '/bin/bash -c "$(curl -fsSL '
                     'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'],
                ],
            },
            {
                "id": "manual-pm",
                "label": "Manual installation",
                "description": "Install the appropriate package manager for your OS",
                "icon": "📖",
                "recommended": False,
                "strategy": "manual",
                "instructions": (
                    "Install a package manager for your OS:\n"
                    "  Debian/Ubuntu: apt-get is usually present by default\n"
                    "  Alpine: apk is present by default\n"
                    "  RHEL/Fedora: dnf is present by default\n"
                    "  macOS: install Homebrew (https://brew.sh)"
                ),
            },
        ],
    },
    {
        "pattern": r"bash:\s*command not found|/bin/sh:\s*not found",
        "failure_id": "no_shell",
        "category": "bootstrap",
        "label": "Shell not available",
        "description": "bash or sh is not available. Cannot execute install scripts.",
        "example_stderr": "/bin/sh: not found",
        "options": [
            {
                "id": "manual-shell",
                "label": "Install shell manually",
                "description": "Ensure /bin/sh or /bin/bash exists",
                "icon": "📖",
                "recommended": True,
                "strategy": "manual",
                "instructions": (
                    "This environment has no usable shell.\n"
                    "If in a container: use a base image that includes bash.\n"
                    "If on bare metal: something is seriously wrong with the OS."
                ),
            },
        ],
    },
]


