"""
L0 Data — snap method-family remediation handlers.

Pure data, no logic.
"""

from __future__ import annotations


_SNAP_HANDLERS: list[dict] = [
        {
            "pattern": (
                r"cannot communicate with server|"
                r"system does not fully support snapd|"
                r"snap \"install\" is not available"
            ),
            "failure_id": "snapd_unavailable",
            "category": "environment",
            "label": "snapd not running",
            "description": "snap requires systemd. Falling back to alternative install.",
            "example_stderr": "error: cannot communicate with server: Post http://localhost/v2/snaps: dial unix /run/snapd.socket: connect: no such file or directory",
            "options": [
                {
                    "id": "switch-apt",
                    "label": "Install via apt instead",
                    "description": "Use apt package manager (if available)",
                    "icon": "🐧",
                    "recommended": True,
                    "strategy": "switch_method",
                    "method": "apt",
                },
                {
                    "id": "switch-default",
                    "label": "Install via direct download",
                    "description": "Use the default install script",
                    "icon": "🌐",
                    "recommended": False,
                    "strategy": "switch_method",
                    "method": "_default",
                },
            ],
        },
]
