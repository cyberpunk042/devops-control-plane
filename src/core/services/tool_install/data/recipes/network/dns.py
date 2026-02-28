"""
L0 Data — DNS tools.

Categories: dns
Pure data, no logic.
"""

from __future__ import annotations


_DNS_RECIPES: dict[str, dict] = {

    "bind-utils": {
        "label": "BIND utilities (nslookup/host)",
        "category": "dns",
        "cli": "nslookup",
        "install": {
            "apt": ["apt-get", "install", "-y", "dnsutils"],
            "dnf": ["dnf", "install", "-y", "bind-utils"],
            "apk": ["apk", "add", "bind-tools"],
            "pacman": ["pacman", "-S", "--noconfirm", "bind"],
            "zypper": ["zypper", "install", "-y", "bind-utils"],
            "brew": ["brew", "install", "bind"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["nslookup", "-version"],
    },
    "dog": {
        "label": "dog (DNS lookup TUI)",
        "category": "dns",
        "install": {
            "_default": ["cargo", "install", "dog"],
            "brew": ["brew", "install", "dog"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "cargo"},
        "verify": ["dog", "--version"],
    },
    "dnsx": {
        "label": "dnsx (DNS toolkit)",
        "category": "dns",
        "install": {
            "_default": ["go", "install",
                         "github.com/projectdiscovery/dnsx/cmd/dnsx@latest"],
            "brew": ["brew", "install", "dnsx"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "go"},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && dnsx --version'],
    },
}
