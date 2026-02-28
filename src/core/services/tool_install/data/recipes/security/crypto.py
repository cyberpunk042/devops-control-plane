"""
L0 Data — Crypto & TLS tools.

Categories: crypto
Pure data, no logic.
"""

from __future__ import annotations


_CRYPTO_RECIPES: dict[str, dict] = {
    "openssl": {
        "label": "OpenSSL",
        "category": "crypto",
        "install": {
            "apt":    ["apt-get", "install", "-y", "openssl"],
            "dnf":    ["dnf", "install", "-y", "openssl"],
            "apk":    ["apk", "add", "openssl"],
            "pacman": ["pacman", "-S", "--noconfirm", "openssl"],
            "zypper": ["zypper", "install", "-y", "openssl"],
            "brew":   ["brew", "install", "openssl@3"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "verify": ["openssl", "version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y", "openssl"],
            "dnf":    ["dnf", "upgrade", "-y", "openssl"],
            "apk":    ["apk", "upgrade", "openssl"],
            "pacman": ["pacman", "-S", "--noconfirm", "openssl"],
            "zypper": ["zypper", "update", "-y", "openssl"],
            "brew":   ["brew", "upgrade", "openssl@3"],
        },
    },

    "certbot": {
        "label": "Certbot (Let's Encrypt)",
        "category": "crypto",
        "install": {
            "apt": ["apt-get", "install", "-y", "certbot"],
            "dnf": ["dnf", "install", "-y", "certbot"],
            "apk": ["apk", "add", "certbot"],
            "pacman": ["pacman", "-S", "--noconfirm", "certbot"],
            "zypper": ["zypper", "install", "-y", "certbot"],
            "brew": ["brew", "install", "certbot"],
            "snap": ["snap", "install", "certbot", "--classic"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False,
                       "snap": True},
        "verify": ["certbot", "--version"],
        "prefer": ["snap"],
    },
    "step-cli": {
        "cli": "step",
        "label": "step CLI (Smallstep certificate authority toolkit)",
        "category": "crypto",
        # Written in Go. Zero-trust PKI, ACME, SSH certificates.
        # brew: step. GitHub releases: step_linux_{amd64|arm64}.tar.gz
        # Also provides .deb and .rpm but tar.gz is cross-platform.
        # Uses amd64/arm64 in asset names (NOT x86_64/aarch64).
        # NOT in apt, dnf, apk, pacman (standard), zypper, snap.
        # AUR has step-cli but that's yay, not pacman -S.
        "install": {
            "brew": ["brew", "install", "step"],
            "_default": [
                "bash", "-c",
                "curl -sSfL https://github.com/smallstep/cli/releases/"
                "latest/download/step_linux_{arch}.tar.gz"
                " | sudo tar -xz -C /usr/local/bin --strip-components=2"
                " step/bin/step",
            ],
        },
        "needs_sudo": {"brew": False, "_default": True},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "arch_map": {"x86_64": "amd64", "aarch64": "arm64"},
        "prefer": ["brew"],
        "verify": ["step", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "step"],
            "_default": [
                "bash", "-c",
                "curl -sSfL https://github.com/smallstep/cli/releases/"
                "latest/download/step_linux_{arch}.tar.gz"
                " | sudo tar -xz -C /usr/local/bin --strip-components=2"
                " step/bin/step",
            ],
        },
    },
    "age": {
        "label": "age (file encryption)",
        "category": "crypto",
        "install": {
            "apt": ["apt-get", "install", "-y", "age"],
            "dnf": ["dnf", "install", "-y", "age"],
            "pacman": ["pacman", "-S", "--noconfirm", "age"],
            "brew": ["brew", "install", "age"],
            "_default": ["go", "install",
                         "filippo.io/age/cmd/...@latest"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "pacman": True,
                       "brew": False, "_default": False},
        "install_via": {"_default": "go"},
        "verify": ["age", "--version"],
    },
    "sops": {
        "label": "SOPS (secret encryption)",
        "category": "crypto",
        "install": {
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL -o /usr/local/bin/sops"
                    " https://github.com/getsops/sops/releases/latest/download/"
                    "sops-linux-amd64 && chmod +x /usr/local/bin/sops",
                ],
            },
            "brew": ["brew", "install", "sops"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "verify": ["sops", "--version"],
    },
}
