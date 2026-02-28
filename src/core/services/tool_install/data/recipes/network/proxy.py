"""
L0 Data — Proxy & load balancer tools.

Categories: proxy
Pure data, no logic.
"""

from __future__ import annotations


_PROXY_RECIPES: dict[str, dict] = {

    "nginx": {
        "cli": "nginx",
        "label": "Nginx (high-performance web server and reverse proxy)",
        "category": "proxy",
        # Written in C. Available in ALL major distro repos.
        # Best PM coverage in the project — apt, dnf, apk, pacman, zypper, brew.
        # No _default needed — every target platform has nginx in its repos.
        # Verify: nginx -v (not --version).
        # snap: nginx is available but rarely used — omitted.
        "install": {
            "apt": ["apt-get", "install", "-y", "nginx"],
            "dnf": ["dnf", "install", "-y", "nginx"],
            "apk": ["apk", "add", "--no-cache", "nginx"],
            "pacman": ["pacman", "-S", "--noconfirm", "nginx"],
            "zypper": ["zypper", "install", "-y", "nginx"],
            "brew": ["brew", "install", "nginx"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["nginx", "-v"],
        "update": {
            "apt": ["apt-get", "install", "--only-upgrade", "-y", "nginx"],
            "dnf": ["dnf", "upgrade", "-y", "nginx"],
            "apk": ["apk", "upgrade", "nginx"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "nginx"],
            "zypper": ["zypper", "update", "-y", "nginx"],
            "brew": ["brew", "upgrade", "nginx"],
        },
    },
    "haproxy": {
        "label": "HAProxy",
        "category": "proxy",
        "install": {
            "apt": ["apt-get", "install", "-y", "haproxy"],
            "dnf": ["dnf", "install", "-y", "haproxy"],
            "apk": ["apk", "add", "haproxy"],
            "pacman": ["pacman", "-S", "--noconfirm", "haproxy"],
            "zypper": ["zypper", "install", "-y", "haproxy"],
            "brew": ["brew", "install", "haproxy"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["haproxy", "-v"],
    },
    "traefik": {
        "label": "Traefik",
        "category": "proxy",
        "install": {
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL https://github.com/traefik/traefik/releases/"
                    "latest/download/traefik_linux_amd64.tar.gz"
                    " | tar xz -C /usr/local/bin traefik",
                ],
            },
            "brew": ["brew", "install", "traefik"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "verify": ["traefik", "version"],
    },
    "envoy": {
        "label": "Envoy Proxy",
        "category": "proxy",
        "install": {
            "apt": ["apt-get", "install", "-y", "envoy"],
            "brew": ["brew", "install", "envoy"],
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL -o /usr/local/bin/envoy"
                    " https://github.com/envoyproxy/envoy/releases/latest/"
                    "download/envoy-contrib-linux-x86_64"
                    " && chmod +x /usr/local/bin/envoy",
                ],
            },
        },
        "needs_sudo": {"apt": True, "brew": False, "_default": True},
        "install_via": {"_default": "github_release"},
        "verify": ["envoy", "--version"],
    },
}
