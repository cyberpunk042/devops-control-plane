"""
L0 Data — Core networking tools.

Categories: network
Pure data, no logic.
"""

from __future__ import annotations

from src.core.services.tool_install.data.constants import _PIP


_NETWORK_RECIPES: dict[str, dict] = {
    "dig": {
        "label": "dig",
        "category": "network",
        "install": {
            "apt":    ["apt-get", "install", "-y", "dnsutils"],
            "dnf":    ["dnf", "install", "-y", "bind-utils"],
            "apk":    ["apk", "add", "bind-tools"],
            "pacman": ["pacman", "-S", "--noconfirm", "bind"],
            "zypper": ["zypper", "install", "-y", "bind-utils"],
            "brew":   ["brew", "install", "bind"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "verify": ["dig", "-v"],
    },

    "mkcert": {
        "cli": "mkcert",
        "label": "mkcert (local TLS certificate authority)",
        "category": "network",
        # Written in Go. Creates locally-trusted dev certificates.
        # brew: mkcert. pacman: mkcert (Arch community). apk: mkcert (Alpine).
        # GitHub releases: mkcert-v{ver}-linux-{amd64|arm64} — raw binary.
        # Uses amd64/arm64 (NOT x86_64/aarch64) in asset names.
        # libnss3-tools (certutil) recommended for Firefox/Chrome trust stores
        # but not required for basic cert generation.
        # NOT in apt, dnf, zypper, snap.
        "install": {
            "brew": ["brew", "install", "mkcert"],
            "pacman": ["pacman", "-S", "--noconfirm", "mkcert"],
            "apk": ["apk", "add", "--no-cache", "mkcert"],
            "_default": [
                "bash", "-c",
                "curl -sSfL -o /usr/local/bin/mkcert "
                "https://github.com/FiloSottile/mkcert/releases/latest/"
                "download/mkcert-$(uname -s)-{arch}"
                " && chmod +x /usr/local/bin/mkcert",
            ],
        },
        "needs_sudo": {
            "brew": False, "pacman": True, "apk": True, "_default": True,
        },
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "arch_map": {"x86_64": "amd64", "aarch64": "arm64"},
        "prefer": ["brew", "pacman", "apk"],
        "verify": ["mkcert", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "mkcert"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "mkcert"],
            "apk": ["apk", "upgrade", "mkcert"],
            "_default": [
                "bash", "-c",
                "curl -sSfL -o /usr/local/bin/mkcert "
                "https://github.com/FiloSottile/mkcert/releases/latest/"
                "download/mkcert-$(uname -s)-{arch}"
                " && chmod +x /usr/local/bin/mkcert",
            ],
        },
    },
    "caddy": {
        "cli": "caddy",
        "label": "Caddy (automatic HTTPS web server)",
        "category": "network",
        # Written in Go. Automatic TLS with Let's Encrypt.
        # brew: caddy. pacman: caddy (Arch community). apk: caddy (Alpine).
        # dnf: caddy (Fedora has it, RHEL/CentOS via COPR).
        # apt: NOT in default Debian/Ubuntu repos — needs official Caddy
        #   repo setup (apt-key + sources.list). Too complex for a simple
        #   `apt-get install` — omitted in favor of _default.
        # zypper: available via OBS but not standard — omitted.
        # OLD getcaddy.com script is for Caddy v1 — DO NOT USE.
        # GitHub releases: caddy_{ver}_linux_{amd64|arm64}.tar.gz
        # Uses amd64/arm64 in asset names.
        # NOT in snap.
        "install": {
            "brew": ["brew", "install", "caddy"],
            "pacman": ["pacman", "-S", "--noconfirm", "caddy"],
            "dnf": ["dnf", "install", "-y", "caddy"],
            "apk": ["apk", "add", "--no-cache", "caddy"],
            "_default": [
                "bash", "-c",
                "curl -sSfL "
                "https://github.com/caddyserver/caddy/releases/latest/"
                "download/caddy_$(curl -sSf "
                "https://api.github.com/repos/caddyserver/caddy/releases/latest"
                " | grep -o '\"tag_name\":\"[^\"]*' | cut -d'\"' -f4 | sed 's/^v//')"
                "_linux_{arch}.tar.gz"
                " | sudo tar -xz -C /usr/local/bin caddy",
            ],
        },
        "needs_sudo": {
            "brew": False, "pacman": True, "dnf": True,
            "apk": True, "_default": True,
        },
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "arch_map": {"x86_64": "amd64", "aarch64": "arm64"},
        "prefer": ["brew", "pacman", "dnf", "apk"],
        "verify": ["caddy", "version"],
        "update": {
            "brew": ["brew", "upgrade", "caddy"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "caddy"],
            "dnf": ["dnf", "upgrade", "-y", "caddy"],
            "apk": ["apk", "upgrade", "caddy"],
            "_default": [
                "bash", "-c",
                "curl -sSfL "
                "https://github.com/caddyserver/caddy/releases/latest/"
                "download/caddy_$(curl -sSf "
                "https://api.github.com/repos/caddyserver/caddy/releases/latest"
                " | grep -o '\"tag_name\":\"[^\"]*' | cut -d'\"' -f4 | sed 's/^v//')"
                "_linux_{arch}.tar.gz"
                " | sudo tar -xz -C /usr/local/bin caddy",
            ],
        },
    },

    "nmap": {
        "label": "Nmap",
        "category": "network",
        "install": {
            "apt": ["apt-get", "install", "-y", "nmap"],
            "dnf": ["dnf", "install", "-y", "nmap"],
            "apk": ["apk", "add", "nmap"],
            "pacman": ["pacman", "-S", "--noconfirm", "nmap"],
            "zypper": ["zypper", "install", "-y", "nmap"],
            "brew": ["brew", "install", "nmap"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["nmap", "--version"],
    },
    "httpie": {
        "label": "HTTPie",
        "category": "network",
        "cli": "http",
        "install": {
            "_default": _PIP + ["install", "httpie"],
            "apt": ["apt-get", "install", "-y", "httpie"],
            "dnf": ["dnf", "install", "-y", "httpie"],
            "brew": ["brew", "install", "httpie"],
            "snap": ["snap", "install", "httpie"],
        },
        "needs_sudo": {"_default": False, "apt": True, "dnf": True,
                       "brew": False, "snap": True},
        "install_via": {"_default": "pip"},
        "verify": ["http", "--version"],
    },
    "wget": {
        "label": "wget",
        "category": "network",
        "install": {
            "apt": ["apt-get", "install", "-y", "wget"],
            "dnf": ["dnf", "install", "-y", "wget"],
            "apk": ["apk", "add", "wget"],
            "pacman": ["pacman", "-S", "--noconfirm", "wget"],
            "zypper": ["zypper", "install", "-y", "wget"],
            "brew": ["brew", "install", "wget"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["wget", "--version"],
    },
    "socat": {
        "label": "socat (socket relay)",
        "category": "network",
        "install": {
            "apt": ["apt-get", "install", "-y", "socat"],
            "dnf": ["dnf", "install", "-y", "socat"],
            "apk": ["apk", "add", "socat"],
            "pacman": ["pacman", "-S", "--noconfirm", "socat"],
            "zypper": ["zypper", "install", "-y", "socat"],
            "brew": ["brew", "install", "socat"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["socat", "-V"],
    },
    "wireguard-tools": {
        "label": "WireGuard tools",
        "category": "network",
        "cli": "wg",
        "install": {
            "apt": ["apt-get", "install", "-y", "wireguard-tools"],
            "dnf": ["dnf", "install", "-y", "wireguard-tools"],
            "apk": ["apk", "add", "wireguard-tools"],
            "pacman": ["pacman", "-S", "--noconfirm", "wireguard-tools"],
            "zypper": ["zypper", "install", "-y", "wireguard-tools"],
            "brew": ["brew", "install", "wireguard-tools"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["wg", "--version"],
    },
}
