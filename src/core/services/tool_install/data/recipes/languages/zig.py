"""
L0 Data — Zig tools.

Categories: zig
Pure data, no logic.
"""

from __future__ import annotations


_ZIG_RECIPES: dict[str, dict] = {

    "zig": {
        "label": "Zig (language + build system)",
        "category": "zig",
        "install": {
            "apt": ["apt-get", "install", "-y", "zig"],
            "pacman": ["pacman", "-S", "--noconfirm", "zig"],
            "brew": ["brew", "install", "zig"],
            "snap": ["snap", "install", "zig", "--classic", "--beta"],
        },
        "needs_sudo": {"apt": True, "pacman": True,
                       "brew": False, "snap": True},
        "verify": ["zig", "version"],
    },
    "zls": {
        "label": "ZLS (Zig language server)",
        "category": "zig",
        "install": {
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL -o /usr/local/bin/zls"
                    " https://github.com/zigtools/zls/releases/latest/download/"
                    "zls-linux-x86_64 && chmod +x /usr/local/bin/zls",
                ],
            },
            "brew": ["brew", "install", "zls"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "verify": ["zls", "--version"],
    },
}
