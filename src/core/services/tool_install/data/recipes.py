"""
L0 Data — Unified tool recipe registry.

All 296 tools, all platforms. Pure data, no logic.

Keys match tool IDs in _TOOLS registry (l0_detection.py).
See Phase 2.2 analysis for full field specification.
"""

from __future__ import annotations

import sys

# Resolve pip via the current interpreter.
_PIP: list[str] = [sys.executable, "-m", "pip"]


TOOL_RECIPES: dict[str, dict] = {

    # ── Category 1: pip tools (platform-independent) ────────────

    "ruff": {
        "label": "Ruff",
        "install": {"_default": _PIP + ["install", "ruff"]},
        "needs_sudo": {"_default": False},
        "verify": ["ruff", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "ruff"]},
    },
    "mypy": {
        "label": "mypy",
        "install": {"_default": _PIP + ["install", "mypy"]},
        "needs_sudo": {"_default": False},
        "verify": ["mypy", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "mypy"]},
    },
    "pytest": {
        "label": "pytest",
        "install": {"_default": _PIP + ["install", "pytest"]},
        "needs_sudo": {"_default": False},
        "verify": ["pytest", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "pytest"]},
    },
    "black": {
        "label": "Black",
        "install": {"_default": _PIP + ["install", "black"]},
        "needs_sudo": {"_default": False},
        "verify": ["black", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "black"]},
    },
    "pip-audit": {
        "label": "pip-audit",
        "install": {"_default": _PIP + ["install", "pip-audit"]},
        "needs_sudo": {"_default": False},
        "verify": _PIP + ["show", "pip-audit"],
        "update": {"_default": _PIP + ["install", "--upgrade", "pip-audit"]},
    },
    "safety": {
        "label": "Safety",
        "install": {"_default": _PIP + ["install", "safety"]},
        "needs_sudo": {"_default": False},
        "verify": ["safety", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "safety"]},
    },
    "bandit": {
        "label": "Bandit",
        "install": {"_default": _PIP + ["install", "bandit"]},
        "needs_sudo": {"_default": False},
        "verify": ["bandit", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "bandit"]},
    },

    # ── Category 2: npm tools ───────────────────────────────────

    "eslint": {
        "label": "ESLint",
        "install": {"_default": ["npm", "install", "-g", "eslint"]},
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["eslint", "--version"],
        "update": {"_default": ["npm", "update", "-g", "eslint"]},
    },
    "prettier": {
        "label": "Prettier",
        "install": {"_default": ["npm", "install", "-g", "prettier"]},
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["prettier", "--version"],
        "update": {"_default": ["npm", "update", "-g", "prettier"]},
    },

    # ── Category 3: cargo tools (need cargo + sys dev packages) ─

    "cargo-audit": {
        "label": "cargo-audit",
        "install": {"_default": ["cargo", "install", "cargo-audit"]},
        "needs_sudo": {"_default": False},
        "requires": {
            "binaries": ["cargo"],
            "packages": {
                "debian": ["pkg-config", "libssl-dev"],
                "rhel":   ["pkgconf-pkg-config", "openssl-devel"],
                "alpine": ["pkgconf", "openssl-dev"],
                "arch":   ["pkgconf", "openssl"],
                "suse":   ["pkg-config", "libopenssl-devel"],
                "macos":  ["pkg-config", "openssl@3"],
            },
        },
        "verify": ["cargo", "audit", "--version"],
        "update": {"_default": ["cargo", "install", "cargo-audit"]},
    },
    "cargo-outdated": {
        "label": "cargo-outdated",
        "install": {"_default": ["cargo", "install", "cargo-outdated"]},
        "needs_sudo": {"_default": False},
        "requires": {
            "binaries": ["cargo"],
            "packages": {
                "debian": ["pkg-config", "libssl-dev", "libcurl4-openssl-dev"],
                "rhel":   ["pkgconf-pkg-config", "openssl-devel", "libcurl-devel"],
                "alpine": ["pkgconf", "openssl-dev", "curl-dev"],
                "arch":   ["pkgconf", "openssl", "curl"],
                "suse":   ["pkg-config", "libopenssl-devel", "libcurl-devel"],
                "macos":  ["pkg-config", "openssl@3", "curl"],
            },
        },
        "verify": ["cargo", "outdated", "--version"],
        "update": {"_default": ["cargo", "install", "cargo-outdated"]},
    },

    # ── Category 4: Runtimes via bash-curl ──────────────────────

    "cargo": {
        "label": "Cargo (Rust)",
        "install": {
            "_default": [
                "bash", "-c",
                "curl --proto '=https' --tlsv1.2 -sSf "
                "https://sh.rustup.rs | sh -s -- -y",
            ],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.cargo/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.cargo/bin:$PATH" && cargo --version'],
        "update": {"_default": ["bash", "-c",
                   'export PATH="$HOME/.cargo/bin:$PATH" && rustup update']},
    },
    "rustc": {
        "label": "Rust Compiler",
        "install": {
            "_default": [
                "bash", "-c",
                "curl --proto '=https' --tlsv1.2 -sSf "
                "https://sh.rustup.rs | sh -s -- -y",
            ],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.cargo/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.cargo/bin:$PATH" && rustc --version'],
        "update": {"_default": ["bash", "-c",
                   'export PATH="$HOME/.cargo/bin:$PATH" && rustup update']},
    },

    # ── Category 5: bash-curl + brew alternatives ───────────────

    "helm": {
        "label": "Helm",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -fsSL https://raw.githubusercontent.com/helm/helm"
                "/main/scripts/get-helm-3 | bash",
            ],
            "brew": ["brew", "install", "helm"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["helm", "version"],
        "update": {
            "_default": [
                "bash", "-c",
                "curl -fsSL https://raw.githubusercontent.com/helm/helm"
                "/main/scripts/get-helm-3 | bash",
            ],
            "brew": ["brew", "upgrade", "helm"],
        },
    },
    "trivy": {
        "label": "Trivy",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sfL https://raw.githubusercontent.com/aquasecurity/"
                "trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin",
            ],
            "brew": ["brew", "install", "trivy"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["trivy", "--version"],
        "update": {
            "_default": [
                "bash", "-c",
                "curl -sfL https://raw.githubusercontent.com/aquasecurity/"
                "trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin",
            ],
            "brew": ["brew", "upgrade", "trivy"],
        },
    },
    "skaffold": {
        "label": "Skaffold",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -Lo /usr/local/bin/skaffold "
                "https://storage.googleapis.com/skaffold/releases/latest/"
                "skaffold-linux-amd64 && chmod +x /usr/local/bin/skaffold",
            ],
            "brew": ["brew", "install", "skaffold"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["skaffold", "version"],
        "update": {
            "_default": [
                "bash", "-c",
                "curl -Lo /usr/local/bin/skaffold "
                "https://storage.googleapis.com/skaffold/releases/latest/"
                "skaffold-linux-amd64 && chmod +x /usr/local/bin/skaffold",
            ],
            "brew": ["brew", "upgrade", "skaffold"],
        },
    },

    # ── Category 6: snap tools with platform variants ───────────

    "kubectl": {
        "label": "kubectl",
        "install": {
            "snap": ["snap", "install", "kubectl", "--classic"],
            "brew": ["brew", "install", "kubectl"],
            "_default": [
                "bash", "-c",
                'curl -LO "https://dl.k8s.io/release/'
                '$(curl -L -s https://dl.k8s.io/release/stable.txt)'
                '/bin/linux/amd64/kubectl" '
                '&& chmod +x kubectl && sudo mv kubectl /usr/local/bin/',
            ],
        },
        "needs_sudo": {"snap": True, "brew": False, "_default": True},
        "prefer": ["snap", "brew", "_default"],
        "requires": {"binaries": ["curl"]},
        "version_constraint": {
            "type": "minor_range",
            "reference_hint": "cluster_version",
            "range": 1,
            "description": "kubectl should be within ±1 minor version of the K8s cluster.",
        },
        "verify": ["kubectl", "version", "--client"],
        "update": {
            "snap": ["snap", "refresh", "kubectl"],
            "brew": ["brew", "upgrade", "kubectl"],
            "_default": [
                "bash", "-c",
                'curl -LO "https://dl.k8s.io/release/'
                '$(curl -L -s https://dl.k8s.io/release/stable.txt)'
                '/bin/linux/amd64/kubectl" '
                '&& chmod +x kubectl && sudo mv kubectl /usr/local/bin/',
            ],
        },
    },
    "terraform": {
        "label": "Terraform",
        "install": {
            "snap": ["snap", "install", "terraform", "--classic"],
            "brew": ["brew", "install", "terraform"],
        },
        "needs_sudo": {"snap": True, "brew": False},
        "prefer": ["snap", "brew"],
        "verify": ["terraform", "--version"],
        "update": {
            "snap": ["snap", "refresh", "terraform"],
            "brew": ["brew", "upgrade", "terraform"],
        },
    },
    "node": {
        "label": "Node.js",
        "install": {
            "snap":   ["snap", "install", "node", "--classic"],
            "apt":    ["apt-get", "install", "-y", "nodejs"],
            "dnf":    ["dnf", "install", "-y", "nodejs"],
            "apk":    ["apk", "add", "nodejs"],
            "pacman": ["pacman", "-S", "--noconfirm", "nodejs"],
            "brew":   ["brew", "install", "node"],
        },
        "needs_sudo": {
            "snap": True, "apt": True, "dnf": True,
            "apk": True, "pacman": True, "brew": False,
        },
        "prefer": ["snap", "brew"],
        "version_constraint": {
            "type": "gte",
            "reference": "18.0.0",
            "description": "Node.js 18+ required for modern ESM and fetch support.",
        },
        "verify": ["node", "--version"],
        "update": {
            "snap":   ["snap", "refresh", "node"],
            "apt":    ["apt-get", "install", "--only-upgrade", "-y", "nodejs"],
            "dnf":    ["dnf", "upgrade", "-y", "nodejs"],
            "apk":    ["apk", "upgrade", "nodejs"],
            "pacman": ["pacman", "-S", "--noconfirm", "nodejs"],
            "brew":   ["brew", "upgrade", "node"],
        },
    },
    "go": {
        "label": "Go",
        "install": {
            "snap":   ["snap", "install", "go", "--classic"],
            "apt":    ["apt-get", "install", "-y", "golang-go"],
            "dnf":    ["dnf", "install", "-y", "golang"],
            "apk":    ["apk", "add", "go"],
            "pacman": ["pacman", "-S", "--noconfirm", "go"],
            "brew":   ["brew", "install", "go"],
        },
        "needs_sudo": {
            "snap": True, "apt": True, "dnf": True,
            "apk": True, "pacman": True, "brew": False,
        },
        "prefer": ["snap", "brew"],
        "verify": ["go", "version"],
        "update": {
            "snap":   ["snap", "refresh", "go"],
            "apt":    ["apt-get", "install", "--only-upgrade", "-y", "golang-go"],
            "dnf":    ["dnf", "upgrade", "-y", "golang"],
            "apk":    ["apk", "upgrade", "go"],
            "pacman": ["pacman", "-S", "--noconfirm", "go"],
            "brew":   ["brew", "upgrade", "go"],
        },
    },
    "gh": {
        "label": "GitHub CLI",
        "install": {
            "snap": ["snap", "install", "gh"],
            "brew": ["brew", "install", "gh"],
        },
        "needs_sudo": {"snap": True, "brew": False},
        "prefer": ["snap", "brew"],
        "verify": ["gh", "--version"],
        "update": {
            "snap": ["snap", "refresh", "gh"],
            "brew": ["brew", "upgrade", "gh"],
        },
    },

    # ── Category 7: Simple system packages (same name everywhere) ─

    "git": {
        "label": "Git",
        "install": {
            "apt":    ["apt-get", "install", "-y", "git"],
            "dnf":    ["dnf", "install", "-y", "git"],
            "apk":    ["apk", "add", "git"],
            "pacman": ["pacman", "-S", "--noconfirm", "git"],
            "zypper": ["zypper", "install", "-y", "git"],
            "brew":   ["brew", "install", "git"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "verify": ["git", "--version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y", "git"],
            "dnf":    ["dnf", "upgrade", "-y", "git"],
            "apk":    ["apk", "upgrade", "git"],
            "pacman": ["pacman", "-S", "--noconfirm", "git"],
            "zypper": ["zypper", "update", "-y", "git"],
            "brew":   ["brew", "upgrade", "git"],
        },
    },
    "curl": {
        "cli": "curl",
        "label": "curl (URL transfer tool)",
        "category": "system",
        "install": {
            "apt":    ["apt-get", "install", "-y", "curl"],
            "dnf":    ["dnf", "install", "-y", "curl"],
            "apk":    ["apk", "add", "curl"],
            "pacman": ["pacman", "-S", "--noconfirm", "curl"],
            "zypper": ["zypper", "install", "-y", "curl"],
            "brew":   ["brew", "install", "curl"],
            "snap":   ["snap", "install", "curl"],
            "source": {
                "build_system": "autotools",
                "tarball_url": "https://curl.se/download/curl-{version}.tar.gz",
                "default_version": "8.18.0",
                "requires_toolchain": ["make", "gcc", "autoconf",
                                       "automake", "libtool", "pkg-config"],
                "configure_args": ["--with-openssl", "--with-zlib"],
            },
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
            "snap": True, "source": True,
        },
        "requires": {
            "packages": {
                "debian": ["libssl-dev", "zlib1g-dev"],
                "rhel":   ["openssl-devel", "zlib-devel"],
                "alpine": ["openssl-dev", "zlib-dev", "ca-certificates"],
                "arch":   ["openssl", "zlib"],
                "suse":   ["libopenssl-devel", "zlib-devel"],
                "macos":  ["openssl@3"],
            },
        },
        "verify": ["curl", "--version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y", "curl"],
            "dnf":    ["dnf", "upgrade", "-y", "curl"],
            "apk":    ["apk", "upgrade", "curl"],
            "pacman": ["pacman", "-S", "--noconfirm", "curl"],
            "zypper": ["zypper", "update", "-y", "curl"],
            "brew":   ["brew", "upgrade", "curl"],
        },
    },
    "jq": {
        "label": "jq",
        "install": {
            "apt":    ["apt-get", "install", "-y", "jq"],
            "dnf":    ["dnf", "install", "-y", "jq"],
            "apk":    ["apk", "add", "jq"],
            "pacman": ["pacman", "-S", "--noconfirm", "jq"],
            "zypper": ["zypper", "install", "-y", "jq"],
            "brew":   ["brew", "install", "jq"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "verify": ["jq", "--version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y", "jq"],
            "dnf":    ["dnf", "upgrade", "-y", "jq"],
            "apk":    ["apk", "upgrade", "jq"],
            "pacman": ["pacman", "-S", "--noconfirm", "jq"],
            "zypper": ["zypper", "update", "-y", "jq"],
            "brew":   ["brew", "upgrade", "jq"],
        },
    },
    "make": {
        "label": "Make",
        "install": {
            "apt":    ["apt-get", "install", "-y", "make"],
            "dnf":    ["dnf", "install", "-y", "make"],
            "apk":    ["apk", "add", "make"],
            "pacman": ["pacman", "-S", "--noconfirm", "make"],
            "zypper": ["zypper", "install", "-y", "make"],
            "brew":   ["brew", "install", "make"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "verify": ["make", "--version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y", "make"],
            "dnf":    ["dnf", "upgrade", "-y", "make"],
            "apk":    ["apk", "upgrade", "make"],
            "pacman": ["pacman", "-S", "--noconfirm", "make"],
            "zypper": ["zypper", "update", "-y", "make"],
            "brew":   ["brew", "upgrade", "make"],
        },
    },
    "gzip": {
        "label": "gzip",
        "install": {
            "apt":    ["apt-get", "install", "-y", "gzip"],
            "dnf":    ["dnf", "install", "-y", "gzip"],
            "apk":    ["apk", "add", "gzip"],
            "pacman": ["pacman", "-S", "--noconfirm", "gzip"],
            "zypper": ["zypper", "install", "-y", "gzip"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True,
        },
        "verify": ["gzip", "--version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y", "gzip"],
            "dnf":    ["dnf", "upgrade", "-y", "gzip"],
            "apk":    ["apk", "upgrade", "gzip"],
            "pacman": ["pacman", "-S", "--noconfirm", "gzip"],
            "zypper": ["zypper", "update", "-y", "gzip"],
        },
    },
    "rsync": {
        "label": "rsync",
        "install": {
            "apt":    ["apt-get", "install", "-y", "rsync"],
            "dnf":    ["dnf", "install", "-y", "rsync"],
            "apk":    ["apk", "add", "rsync"],
            "pacman": ["pacman", "-S", "--noconfirm", "rsync"],
            "zypper": ["zypper", "install", "-y", "rsync"],
            "brew":   ["brew", "install", "rsync"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "verify": ["rsync", "--version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y", "rsync"],
            "dnf":    ["dnf", "upgrade", "-y", "rsync"],
            "apk":    ["apk", "upgrade", "rsync"],
            "pacman": ["pacman", "-S", "--noconfirm", "rsync"],
            "zypper": ["zypper", "update", "-y", "rsync"],
            "brew":   ["brew", "upgrade", "rsync"],
        },
    },
    "openssl": {
        "label": "OpenSSL",
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
    "ffmpeg": {
        "label": "FFmpeg",
        "install": {
            "apt":    ["apt-get", "install", "-y", "ffmpeg"],
            "dnf":    ["dnf", "install", "-y", "ffmpeg-free"],
            "apk":    ["apk", "add", "ffmpeg"],
            "pacman": ["pacman", "-S", "--noconfirm", "ffmpeg"],
            "zypper": ["zypper", "install", "-y", "ffmpeg"],
            "brew":   ["brew", "install", "ffmpeg"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "verify": ["ffmpeg", "-version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y", "ffmpeg"],
            "dnf":    ["dnf", "upgrade", "-y", "ffmpeg-free"],
            "apk":    ["apk", "upgrade", "ffmpeg"],
            "pacman": ["pacman", "-S", "--noconfirm", "ffmpeg"],
            "zypper": ["zypper", "update", "-y", "ffmpeg"],
            "brew":   ["brew", "upgrade", "ffmpeg"],
        },
    },
    "expect": {
        "label": "Expect",
        "install": {
            "apt":    ["apt-get", "install", "-y", "expect"],
            "dnf":    ["dnf", "install", "-y", "expect"],
            "apk":    ["apk", "add", "expect"],
            "pacman": ["pacman", "-S", "--noconfirm", "expect"],
            "zypper": ["zypper", "install", "-y", "expect"],
            "brew":   ["brew", "install", "expect"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "verify": ["expect", "-version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y", "expect"],
            "dnf":    ["dnf", "upgrade", "-y", "expect"],
            "apk":    ["apk", "upgrade", "expect"],
            "pacman": ["pacman", "-S", "--noconfirm", "expect"],
            "zypper": ["zypper", "update", "-y", "expect"],
            "brew":   ["brew", "upgrade", "expect"],
        },
    },

    # ── Category 7b: Terminal emulators (desktop Linux only) ────

    "xterm": {
        "label": "xterm",
        "install": {
            "apt":    ["apt-get", "install", "-y", "xterm"],
            "dnf":    ["dnf", "install", "-y", "xterm"],
            "pacman": ["pacman", "-S", "--noconfirm", "xterm"],
            "zypper": ["zypper", "install", "-y", "xterm"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "pacman": True, "zypper": True},
        "verify": ["xterm", "-version"],
    },
    "gnome-terminal": {
        "label": "GNOME Terminal",
        "install": {
            "apt":    ["apt-get", "install", "-y", "gnome-terminal"],
            "dnf":    ["dnf", "install", "-y", "gnome-terminal"],
            "pacman": ["pacman", "-S", "--noconfirm", "gnome-terminal"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "pacman": True},
        "verify": ["gnome-terminal", "--version"],
    },
    "xfce4-terminal": {
        "label": "Xfce Terminal",
        "install": {
            "apt":    ["apt-get", "install", "-y", "xfce4-terminal"],
            "dnf":    ["dnf", "install", "-y", "xfce4-terminal"],
            "pacman": ["pacman", "-S", "--noconfirm", "xfce4-terminal"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "pacman": True},
        "verify": ["xfce4-terminal", "--version"],
    },
    "konsole": {
        "label": "Konsole",
        "install": {
            "apt":    ["apt-get", "install", "-y", "konsole"],
            "dnf":    ["dnf", "install", "-y", "konsole"],
            "pacman": ["pacman", "-S", "--noconfirm", "konsole"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "pacman": True},
        "verify": ["konsole", "--version"],
    },
    "kitty": {
        "label": "Kitty",
        "install": {
            "apt":    ["apt-get", "install", "-y", "kitty"],
            "dnf":    ["dnf", "install", "-y", "kitty"],
            "pacman": ["pacman", "-S", "--noconfirm", "kitty"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "pacman": True},
        "verify": ["kitty", "--version"],
    },

    # ── Category 8: System packages — different names per distro ─

    "python": {
        "label": "Python",
        "cli": "python3",
        "install": {
            "apt":    ["apt-get", "install", "-y", "python3"],
            "dnf":    ["dnf", "install", "-y", "python3"],
            "apk":    ["apk", "add", "python3"],
            "pacman": ["pacman", "-S", "--noconfirm", "python"],
            "zypper": ["zypper", "install", "-y", "python3"],
            "brew":   ["brew", "install", "python@3"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "verify": ["python3", "--version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y", "python3"],
            "dnf":    ["dnf", "upgrade", "-y", "python3"],
            "apk":    ["apk", "upgrade", "python3"],
            "pacman": ["pacman", "-S", "--noconfirm", "python"],
            "zypper": ["zypper", "update", "-y", "python3"],
            "brew":   ["brew", "upgrade", "python@3"],
        },
    },
    "pip": {
        "label": "pip",
        "install": {
            "apt":    ["apt-get", "install", "-y", "python3-pip"],
            "dnf":    ["dnf", "install", "-y", "python3-pip"],
            "apk":    ["apk", "add", "py3-pip"],
            "pacman": ["pacman", "-S", "--noconfirm", "python-pip"],
            "zypper": ["zypper", "install", "-y", "python3-pip"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True,
        },
        "verify": ["pip", "--version"],
        "update": {"_default": ["pip", "install", "--upgrade", "pip"]},
    },
    "npm": {
        "label": "npm",
        "install": {
            "apt":    ["apt-get", "install", "-y", "npm"],
            "dnf":    ["dnf", "install", "-y", "npm"],
            "apk":    ["apk", "add", "npm"],
            "pacman": ["pacman", "-S", "--noconfirm", "npm"],
            "brew":   ["brew", "install", "node"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "brew": False,
        },
        "verify": ["npm", "--version"],
        "update": {"_default": ["npm", "install", "-g", "npm"]},
    },
    "npx": {
        "label": "npx",
        "install": {
            "apt":    ["apt-get", "install", "-y", "npm"],
            "dnf":    ["dnf", "install", "-y", "npm"],
            "apk":    ["apk", "add", "npm"],
            "pacman": ["pacman", "-S", "--noconfirm", "npm"],
            "brew":   ["brew", "install", "node"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "brew": False,
        },
        "verify": ["npx", "--version"],
    },
    "dig": {
        "label": "dig",
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
    "docker": {
        "label": "Docker",
        "install": {
            "apt":    ["apt-get", "install", "-y", "docker.io"],
            "dnf":    ["dnf", "install", "-y", "docker"],
            "apk":    ["apk", "add", "docker"],
            "pacman": ["pacman", "-S", "--noconfirm", "docker"],
            "zypper": ["zypper", "install", "-y", "docker"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True,
        },
        "post_install": [
            {
                "label": "Start Docker daemon",
                "command": ["systemctl", "start", "docker"],
                "needs_sudo": True,
                "condition": "has_systemd",
            },
            {
                "label": "Enable Docker on boot",
                "command": ["systemctl", "enable", "docker"],
                "needs_sudo": True,
                "condition": "has_systemd",
            },
            {
                "label": "Add user to docker group",
                "command": ["bash", "-c", "usermod -aG docker $USER"],
                "needs_sudo": True,
                "condition": "not_root",
            },
        ],
        "verify": ["docker", "--version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y", "docker.io"],
            "dnf":    ["dnf", "upgrade", "-y", "docker"],
            "apk":    ["apk", "upgrade", "docker"],
            "pacman": ["pacman", "-S", "--noconfirm", "docker"],
            "zypper": ["zypper", "update", "-y", "docker"],
        },
    },
    "docker-compose": {
        "label": "Docker Compose",
        "install": {
            "apt":    ["apt-get", "install", "-y", "docker-compose-v2"],
            "dnf":    ["dnf", "install", "-y", "docker-compose-plugin"],
            "apk":    ["apk", "add", "docker-compose"],
            "pacman": ["pacman", "-S", "--noconfirm", "docker-compose"],
            "zypper": ["zypper", "install", "-y", "docker-compose"],
            "brew":   ["brew", "install", "docker-compose"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "requires": {"binaries": ["docker"]},
        "version_constraint": {
            "type": "gte",
            "reference": "2.0.0",
            "description": "Docker Compose V2 required (docker compose, not docker-compose).",
        },
        "verify": ["docker", "compose", "version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y", "docker-compose-v2"],
            "dnf":    ["dnf", "upgrade", "-y", "docker-compose-plugin"],
            "apk":    ["apk", "upgrade", "docker-compose"],
            "pacman": ["pacman", "-S", "--noconfirm", "docker-compose"],
            "zypper": ["zypper", "update", "-y", "docker-compose"],
            "brew":   ["brew", "upgrade", "docker-compose"],
        },
    },

    # ── Category 9: GPU drivers ─────────────────────────────────
    #
    # Spec: Phase 6 §Driver option matrix, domain-gpu.
    # Risk: HIGH — kernel modules, DKMS, possible reboot.

    "nvidia-driver": {
        "label": "NVIDIA Driver",
        "cli": "nvidia-smi",
        "category": "gpu",
        "risk": "high",
        "install": {
            "apt": ["apt-get", "install", "-y", "nvidia-driver-535"],
            "dnf": ["dnf", "install", "-y", "nvidia-gpu-firmware",
                    "akmod-nvidia"],
        },
        "needs_sudo": {"apt": True, "dnf": True},
        "repo_setup": {
            "apt": [
                {
                    "label": "Add NVIDIA PPA",
                    "command": ["add-apt-repository", "-y",
                                "ppa:graphics-drivers/ppa"],
                    "needs_sudo": True,
                },
                {
                    "label": "Update package lists",
                    "command": ["apt-get", "update"],
                    "needs_sudo": True,
                },
            ],
        },
        "requires": {
            "hardware": {"gpu_vendor": "nvidia"},
            "packages": {
                "debian": ["linux-headers-generic", "dkms"],
                "rhel":   ["kernel-devel", "kernel-headers"],
            },
        },
        "post_install": [
            {
                "label": "Load NVIDIA kernel module",
                "command": ["modprobe", "nvidia"],
                "needs_sudo": True,
            },
        ],
        "verify": ["nvidia-smi"],
        "rollback": {
            "apt": ["apt-get", "purge", "-y", "nvidia-driver-535"],
            "post": ["modprobe", "nouveau"],
        },
        "restart_required": "system",
    },
    "cuda-toolkit": {
        "label": "CUDA Toolkit",
        "cli": "nvcc",
        "category": "gpu",
        "risk": "high",
        "install": {
            "apt": ["apt-get", "install", "-y", "nvidia-cuda-toolkit"],
            "dnf": ["dnf", "install", "-y", "cuda-toolkit"],
        },
        "needs_sudo": {"apt": True, "dnf": True},
        "requires": {
            "hardware": {"gpu_vendor": "nvidia"},
            "binaries": ["nvidia-smi"],
        },
        "post_install": [
            {
                "label": "Set CUDA environment paths",
                "command": [
                    "bash", "-c",
                    'echo "export PATH=/usr/local/cuda/bin:$PATH" '
                    '>> /etc/profile.d/cuda.sh && '
                    'echo "/usr/local/cuda/lib64" > '
                    "/etc/ld.so.conf.d/cuda.conf && ldconfig",
                ],
                "needs_sudo": True,
            },
        ],
        "verify": ["nvcc", "--version"],
    },
    "vfio-passthrough": {
        "type": "data_pack",
        "label": "VFIO GPU Passthrough",
        "category": "gpu",
        "risk": "high",
        "install": {
            # No package install — kernel modules are built-in or via DKMS
        },
        "needs_sudo": {"_default": True},
        "requires": {
            "hardware": {"gpu.has_gpu": True},
        },
        "steps": [
            {
                "id": "vfio-modules",
                "type": "config",
                "label": "Enable VFIO kernel modules",
                "action": "ensure_line",
                "file": "/etc/modules-load.d/vfio.conf",
                "lines": [
                    "vfio",
                    "vfio_iommu_type1",
                    "vfio_pci",
                    "vfio_virqfd",
                ],
                "needs_sudo": True,
                "risk": "high",
                "backup_before": ["/etc/modules-load.d/vfio.conf"],
            },
            {
                "id": "iommu-grub",
                "type": "config",
                "label": "Enable IOMMU in boot parameters",
                "action": "ensure_line",
                "file": "/etc/default/grub",
                "content": 'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash intel_iommu=on iommu=pt"',
                "needs_sudo": True,
                "risk": "high",
                "backup_before": ["/etc/default/grub"],
                "depends_on": ["vfio-modules"],
            },
            {
                "id": "update-grub",
                "type": "post_install",
                "label": "Update GRUB configuration",
                "command": ["update-grub"],
                "needs_sudo": True,
                "depends_on": ["iommu-grub"],
            },
            {
                "id": "load-vfio",
                "type": "post_install",
                "label": "Load VFIO modules",
                "command": ["modprobe", "vfio-pci"],
                "needs_sudo": True,
                "depends_on": ["vfio-modules"],
            },
        ],
        "verify": ["lsmod | grep vfio"],
        "rollback": {
            "remove_files": ["/etc/modules-load.d/vfio.conf"],
            "post": ["update-grub"],
        },
        "restart_required": "system",
    },
    "rocm": {
        "label": "AMD ROCm",
        "cli": "rocminfo",
        "category": "gpu",
        "risk": "high",
        "install": {
            "apt": [
                "bash", "-c",
                "wget https://repo.radeon.com/amdgpu-install/latest/"
                "ubuntu/jammy/amdgpu-install_6.0_all.deb && "
                "dpkg -i amdgpu-install_6.0_all.deb && "
                "amdgpu-install --usecase=rocm --no-dkms -y",
            ],
            "dnf": ["dnf", "install", "-y", "rocm-dev"],
        },
        "needs_sudo": {"apt": True, "dnf": True},
        "requires": {
            "hardware": {"gpu_vendor": "amd"},
            "platforms": ["debian", "rhel"],
        },
        "post_install": [
            {
                "label": "Add user to render and video groups",
                "command": [
                    "bash", "-c",
                    "usermod -aG render,video $USER",
                ],
                "needs_sudo": True,
            },
        ],
        "verify": ["rocminfo"],
        "remove": {
            "apt": ["amdgpu-install", "--uninstall"],
            "dnf": ["dnf", "remove", "-y", "rocm-dev"],
        },
        "rollback": {
            "apt": ["amdgpu-install", "--uninstall"],
            "post": ["modprobe", "amdgpu"],
        },
        "restart_required": "session",
    },

    # ── Category 11: ML/AI recipes ───────────────────────────────
    #
    # Spec: domain-ml-ai §Recipes.
    # These use choice-based GPU/CPU variant selection.

    "pytorch": {
        "label": "PyTorch",
        "cli": "python3",
        "cli_verify_args": ["-c", "import torch; print(torch.__version__)"],
        "category": "ml",
        "risk": "low",
        "choices": [{
            "id": "variant",
            "label": "PyTorch variant",
            "type": "single",
            "options": [
                {
                    "id": "cpu",
                    "label": "CPU only",
                    "description": "Installs PyTorch with CPU-only support. "
                        "Suitable for development, testing, and inference on "
                        "machines without a dedicated GPU.",
                    "risk": "low",
                    "estimated_time": "2-5 minutes",
                    "default": True,
                },
                {
                    "id": "cuda",
                    "label": "NVIDIA CUDA (GPU accelerated)",
                    "description": "Installs PyTorch with NVIDIA CUDA support "
                        "for GPU-accelerated training and inference. Requires "
                        "a compatible NVIDIA GPU and CUDA drivers.",
                    "risk": "low",
                    "warning": "Requires NVIDIA drivers and CUDA toolkit. "
                        "Package is significantly larger (~2 GB).",
                    "estimated_time": "5-15 minutes",
                    "requires": {"hardware": ["nvidia"]},
                },
                {
                    "id": "rocm",
                    "label": "AMD ROCm (GPU accelerated)",
                    "description": "Installs PyTorch with AMD ROCm support "
                        "for GPU-accelerated training on AMD Radeon GPUs. "
                        "Requires ROCm drivers installed.",
                    "risk": "low",
                    "warning": "Requires ROCm stack installed. Limited "
                        "platform support compared to CUDA.",
                    "estimated_time": "5-15 minutes",
                    "requires": {"hardware": ["amd"]},
                },
            ],
        }],
        "install_variants": {
            "cpu": {
                "command": [
                    "pip3", "install", "torch", "torchvision",
                    "torchaudio", "--index-url",
                    "https://download.pytorch.org/whl/cpu",
                ],
            },
            "cuda": {
                "command": [
                    "pip3", "install", "torch", "torchvision",
                    "torchaudio",
                ],
            },
            "rocm": {
                "command": [
                    "pip3", "install", "torch", "torchvision",
                    "torchaudio", "--index-url",
                    "https://download.pytorch.org/whl/rocm6.2",
                ],
            },
        },
        "install": {
            "pip": ["pip3", "install", "torch"],
        },
        "needs_sudo": {"pip": False},
        "verify": ["python3", "-c", "import torch; print(torch.__version__)"],
    },
    "opencv": {
        "label": "OpenCV",
        "cli": "python3",
        "cli_verify_args": ["-c", "import cv2; print(cv2.__version__)"],
        "category": "ml",
        "risk": "low",
        "choices": [{
            "id": "variant",
            "label": "OpenCV variant",
            "type": "single",
            "options": [
                {
                    "id": "headless",
                    "label": "Headless (no GUI, pip install)",
                    "description": "Minimal OpenCV without GUI dependencies. "
                        "Ideal for servers, containers, and headless "
                        "image/video processing pipelines.",
                    "risk": "low",
                    "estimated_time": "1-3 minutes",
                    "default": True,
                },
                {
                    "id": "full",
                    "label": "Full (GUI support, pip install)",
                    "description": "OpenCV with GUI support (highgui, imshow). "
                        "Requires X11 or Wayland display server for window "
                        "display functions.",
                    "risk": "low",
                    "warning": "Requires display server (X11/Wayland). "
                        "Will not work in headless environments.",
                    "estimated_time": "1-3 minutes",
                },
                {
                    "id": "contrib",
                    "label": "Full + contrib modules (pip install)",
                    "description": "Full OpenCV plus community-contributed "
                        "modules (face detection, tracking, SIFT, etc.). "
                        "Largest package but most feature-complete.",
                    "risk": "low",
                    "estimated_time": "2-5 minutes",
                },
            ],
        }],
        "install_variants": {
            "headless": {
                "command": ["pip3", "install", "opencv-python-headless"],
            },
            "full": {
                "command": ["pip3", "install", "opencv-python"],
            },
            "contrib": {
                "command": ["pip3", "install", "opencv-contrib-python"],
            },
        },
        "install": {
            "pip": ["pip3", "install", "opencv-python-headless"],
        },
        "needs_sudo": {"pip": False},
        "verify": ["python3", "-c", "import cv2; print(cv2.__version__)"],
    },

    # ── Category 12: Data pack recipes ──────────────────────────
    #
    # Spec: domain-data-packs §Recipes.
    # These produce `type: "download"` steps with disk check,
    # resume, checksums, and freshness tracking.

    "trivy-db": {
        "type": "data_pack",
        "label": "Trivy Vulnerability DB",
        "category": "data_pack",
        "risk": "low",
        "steps": [
            {
                "id": "download-trivy-db",
                "type": "download",
                "label": "Download Trivy vulnerability database",
                "url": "https://github.com/aquasecurity/trivy-db/releases/"
                       "latest/download/db.tar.gz",
                "dest": "~/.cache/trivy/db/trivy.db",
                "size_bytes": 150_000_000,
                "freshness_days": 7,
            },
        ],
        "requires": {
            "binaries": ["trivy"],
        },
    },
    "geoip-db": {
        "type": "data_pack",
        "label": "MaxMind GeoIP Database",
        "category": "data_pack",
        "risk": "low",
        "inputs": [
            {
                "id": "license_key",
                "label": "MaxMind License Key",
                "type": "password",
                "required": True,
                "help_text": "Get a free key from https://www.maxmind.com",
            },
        ],
        "steps": [
            {
                "id": "download-geoip",
                "type": "download",
                "label": "Download GeoLite2 City database",
                "url": "https://download.maxmind.com/app/geoip_download"
                       "?edition_id=GeoLite2-City&license_key="
                       "{license_key}&suffix=tar.gz",
                "dest": "~/.local/share/GeoIP/GeoLite2-City.mmdb",
                "freshness_days": 30,
            },
        ],
    },
    "wordlists": {
        "type": "data_pack",
        "label": "Security Wordlists (rockyou)",
        "category": "data_pack",
        "risk": "low",
        "steps": [
            {
                "id": "download-rockyou",
                "type": "download",
                "label": "Download rockyou.txt wordlist",
                "url": "https://github.com/brannondorsey/naive-hashcat/"
                       "releases/download/data/rockyou.txt",
                "dest": "~/.local/share/wordlists/rockyou.txt",
                "size_bytes": 139_921_497,
            },
        ],
    },
    "spacy-en": {
        "type": "data_pack",
        "label": "spaCy English Model",
        "category": "data_pack",
        "risk": "low",
        "steps": [
            {
                "id": "download-spacy-en",
                "type": "post_install",
                "label": "Download spaCy English NLP model",
                "command": [
                    "python3", "-m", "spacy", "download", "en_core_web_sm",
                ],
            },
        ],
        "requires": {
            "binaries": ["python3"],
        },
    },
    "hf-model": {
        "type": "data_pack",
        "label": "HuggingFace Model (gated)",
        "category": "data_pack",
        "risk": "low",
        "inputs": [
            {
                "id": "model_id",
                "label": "Model ID",
                "type": "text",
                "default": "meta-llama/Llama-2-7b-hf",
                "required": True,
            },
            {
                "id": "hf_token",
                "label": "HuggingFace Token",
                "type": "password",
                "required": True,
                "help_text": "Get a token from https://huggingface.co/settings/tokens",
            },
        ],
        "steps": [
            {
                "id": "download-hf-model",
                "type": "post_install",
                "label": "Download HuggingFace model",
                "command": [
                    "python3", "-c",
                    "from huggingface_hub import snapshot_download; "
                    "snapshot_download('{model_id}', token='{hf_token}')",
                ],
            },
        ],
        "requires": {
            "binaries": ["python3"],
            "network": ["https://huggingface.co"],
        },
    },

    # ── Category 10: Config template recipes ────────────────────
    #
    # Spec: domain-config-files §Examples.
    # These produce `action: "template"` config steps.

    "docker-daemon-config": {
        "type": "config",
        "label": "Docker daemon.json",
        "category": "config",
        "config_templates": [{
            "id": "docker_config",
            "file": "/etc/docker/daemon.json",
            "format": "json",
            "template": '{\n'
                        '  "storage-driver": "{docker_storage_driver}",\n'
                        '  "log-driver": "json-file",\n'
                        '  "log-opts": {\n'
                        '    "max-size": "{log_max_size}",\n'
                        '    "max-file": "{log_max_files}"\n'
                        '  }\n'
                        '}',
            "inputs": [
                {"id": "docker_storage_driver", "label": "Storage Driver",
                 "type": "select",
                 "options": ["overlay2", "btrfs", "devicemapper"],
                 "default": "overlay2"},
                {"id": "log_max_size",
                 "label": "Max log size per container",
                 "type": "select",
                 "options": ["10m", "50m", "100m", "500m"],
                 "default": "50m"},
                {"id": "log_max_files",
                 "label": "Max log files per container",
                 "type": "select",
                 "options": ["1", "3", "5", "10"],
                 "default": "3"},
            ],
            "needs_sudo": True,
            "post_command": ["systemctl", "restart", "docker"],
            "condition": "has_systemd",
            "backup": True,
        }],
        # No install — this is a config-only recipe.
        "install": {},
        "needs_sudo": {},
        "verify": ["bash", "-c", "test -f /etc/docker/daemon.json"],
    },
    "journald-config": {
        "type": "config",
        "label": "journald configuration",
        "category": "config",
        "config_templates": [{
            "id": "journald_config",
            "file": "/etc/systemd/journald.conf.d/custom.conf",
            "format": "ini",
            "template": (
                "[Journal]\n"
                "SystemMaxUse={journal_max_size}\n"
                "Compress=yes\n"
                "RateLimitBurst={rate_limit}\n"
            ),
            "inputs": [
                {"id": "journal_max_size", "label": "Max journal size",
                 "type": "select",
                 "options": ["100M", "500M", "1G", "2G"],
                 "default": "500M"},
                {"id": "rate_limit", "label": "Rate limit burst",
                 "type": "number", "default": 1000,
                 "validation": {"min": 100, "max": 100000}},
            ],
            "needs_sudo": True,
            "post_command": ["systemctl", "restart", "systemd-journald"],
            "condition": "has_systemd",
        }],
        "install": {},
        "needs_sudo": {},
        "verify": ["bash", "-c",
                   "test -f /etc/systemd/journald.conf.d/custom.conf"],
    },
    "logrotate-docker": {
        "type": "config",
        "label": "Docker logrotate config",
        "category": "config",
        "config_templates": [{
            "id": "logrotate_docker",
            "file": "/etc/logrotate.d/docker-containers",
            "format": "raw",
            "template": (
                "/var/lib/docker/containers/*/*.log {\n"
                "    daily\n"
                "    rotate {rotate_count}\n"
                "    compress\n"
                "    delaycompress\n"
                "    missingok\n"
                "    notifempty\n"
                "    copytruncate\n"
                "}\n"
            ),
            "inputs": [
                {"id": "rotate_count", "label": "Days to keep",
                 "type": "number", "default": 14,
                 "validation": {"min": 1, "max": 365}},
            ],
            "needs_sudo": True,
        }],
        "install": {},
        "needs_sudo": {},
        "verify": ["bash", "-c",
                   "test -f /etc/logrotate.d/docker-containers"],
    },
    "nginx-vhost": {
        "type": "config",
        "label": "nginx virtual host",
        "category": "config",
        "config_templates": [{
            "id": "nginx_vhost",
            "file": "/etc/nginx/sites-available/{site_name}",
            "format": "raw",
            "template": (
                "server {\n"
                "    listen {port};\n"
                "    server_name {server_name};\n"
                "    root {document_root};\n"
                "\n"
                "    location / {\n"
                "        try_files $uri $uri/ =404;\n"
                "    }\n"
                "}\n"
            ),
            "inputs": [
                {"id": "site_name", "label": "Site name",
                 "type": "text", "default": "default"},
                {"id": "port", "label": "Listen port",
                 "type": "number", "default": 80,
                 "validation": {"min": 1, "max": 65535}},
                {"id": "server_name", "label": "Server name",
                 "type": "text", "default": "_"},
                {"id": "document_root", "label": "Document root",
                 "type": "path", "default": "/var/www/html"},
            ],
            "needs_sudo": True,
            "post_command": [
                "bash", "-c",
                "ln -sf /etc/nginx/sites-available/{site_name} "
                "/etc/nginx/sites-enabled/ && nginx -t && "
                "systemctl reload nginx",
            ],
            "condition": "has_systemd",
            "backup": True,
        }],
        "install": {},
        "needs_sudo": {},
        "verify": ["nginx", "-t"],
    },

    # ── Category 11: Build toolchain meta-packages ──────────────

    "build-essential": {
        "label": "Build Essential (C/C++ toolchain)",
        "cli": "gcc",
        "install": {
            "apt": ["apt-get", "install", "-y", "build-essential"],
            "dnf": ["dnf", "groupinstall", "-y", "Development Tools"],
            "pacman": ["pacman", "-S", "--noconfirm", "base-devel"],
            "apk": ["apk", "add", "build-base"],
            "brew": ["brew", "install", "gcc"],
            "_default": ["apt-get", "install", "-y", "build-essential"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "pacman": True,
            "apk": True, "brew": False, "_default": True,
        },
        "verify": ["gcc", "--version"],
        "update": {
            "apt": ["apt-get", "install", "-y", "--only-upgrade", "build-essential"],
            "dnf": ["dnf", "groupupdate", "-y", "Development Tools"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "base-devel"],
        },
    },

    # ── Category 12: Pages install tools (GitHub releases) ──────

    "hugo": {
        "label": "Hugo",
        "install": {
            "apt": ["apt-get", "install", "-y", "hugo"],
            "brew": ["brew", "install", "hugo"],
            "snap": ["snap", "install", "hugo"],
            "_default": [
                "bash", "-c",
                "curl -sL https://github.com/gohugoio/hugo/releases/latest/"
                "download/hugo_extended_{version}_linux-{arch}.tar.gz "
                "| tar xz -C /usr/local/bin hugo",
            ],
        },
        "needs_sudo": {
            "apt": True, "brew": False, "snap": True, "_default": True,
        },
        "prefer": ["brew", "apt", "snap", "_default"],
        "verify": ["hugo", "version"],
        "update": {
            "apt": ["apt-get", "install", "-y", "--only-upgrade", "hugo"],
            "brew": ["brew", "upgrade", "hugo"],
            "snap": ["snap", "refresh", "hugo"],
        },
        "arch_map": {"x86_64": "amd64", "aarch64": "arm64"},
    },
    "mkdocs": {
        "label": "MkDocs",
        "cli": "mkdocs",
        "category": "pages",
        "risk": "low",
        "choices": [{
            "id": "variant",
            "label": "MkDocs variant",
            "type": "single",
            "options": [
                {
                    "id": "basic",
                    "label": "MkDocs (basic)",
                    "description": "Vanilla MkDocs with the default theme. "
                        "Lightweight and fast. Good for simple documentation "
                        "sites without advanced styling needs.",
                    "risk": "low",
                    "estimated_time": "< 1 minute",
                    "default": True,
                },
                {
                    "id": "material",
                    "label": "MkDocs Material (recommended)",
                    "description": "MkDocs with Material for MkDocs theme. "
                        "Includes search, dark mode, navigation tabs, "
                        "code annotations, and many other premium features.",
                    "risk": "low",
                    "estimated_time": "1-2 minutes",
                },
            ],
        }],
        "install_variants": {
            "basic": {
                "command": ["pip3", "install", "mkdocs"],
            },
            "material": {
                "command": ["pip3", "install", "mkdocs-material"],
            },
        },
        "install": {
            "pip": ["pip3", "install", "mkdocs"],
        },
        "needs_sudo": {"pip": False},
        "verify": ["mkdocs", "--version"],
        "update": {
            "pip": ["pip3", "install", "--upgrade", "mkdocs"],
        },
    },
    "docusaurus": {
        "label": "Docusaurus",
        "cli": "npx",
        "cli_verify_args": ["docusaurus", "--version"],
        "category": "pages",
        "risk": "low",
        "install": {
            "npm": ["npm", "install", "-g", "@docusaurus/core"],
        },
        "needs_sudo": {"npm": False},
        "verify": ["npx", "docusaurus", "--version"],
        "update": {
            "npm": ["npm", "update", "-g", "@docusaurus/core"],
        },
        "requires": {
            "binaries": ["node", "npm"],
        },
    },

    # ════════════════════════════════════════════════════════════
    # Batch 1 — Go stack
    # ════════════════════════════════════════════════════════════

    "gopls": {
        "label": "gopls (Go language server)",
        "category": "go",
        "install": {
            "_default": ["go", "install", "golang.org/x/tools/gopls@latest"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["go"]},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && gopls version'],
        "update": {"_default": ["go", "install",
                                "golang.org/x/tools/gopls@latest"]},
    },
    "golangci-lint": {
        "label": "golangci-lint",
        "category": "go",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL https://raw.githubusercontent.com/golangci/"
                "golangci-lint/HEAD/install.sh | sh -s -- -b "
                "$(go env GOPATH)/bin",
            ],
            "brew": ["brew", "install", "golangci-lint"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["go", "curl"]},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && golangci-lint --version'],
        "update": {
            "_default": [
                "bash", "-c",
                "curl -sSfL https://raw.githubusercontent.com/golangci/"
                "golangci-lint/HEAD/install.sh | sh -s -- -b "
                "$(go env GOPATH)/bin",
            ],
            "brew": ["brew", "upgrade", "golangci-lint"],
        },
    },
    "delve": {
        "label": "Delve (Go debugger)",
        "category": "go",
        "install": {
            "_default": ["go", "install",
                         "github.com/go-delve/delve/cmd/dlv@latest"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["go"]},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && dlv version'],
        "cli": "dlv",
    },
    "air": {
        "label": "Air (Go live reload)",
        "category": "go",
        "install": {
            "_default": ["go", "install",
                         "github.com/air-verse/air@latest"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["go"]},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && air -v'],
    },
    "mockgen": {
        "label": "mockgen (Go mock generator)",
        "category": "go",
        "install": {
            "_default": ["go", "install",
                         "go.uber.org/mock/mockgen@latest"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["go"]},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && mockgen --version'],
    },
    "protoc-gen-go": {
        "label": "protoc-gen-go (Go protobuf)",
        "category": "go",
        "install": {
            "_default": ["go", "install",
                         "google.golang.org/protobuf/cmd/protoc-gen-go@latest"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["go"]},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && protoc-gen-go --version'],
    },

    # ════════════════════════════════════════════════════════════
    # Cloud CLIs
    # ════════════════════════════════════════════════════════════

    "aws-cli": {
        "label": "AWS CLI v2",
        "category": "cloud",
        "cli": "aws",
        "install": {
            "_default": [
                "bash", "-c",
                'curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip"'
                ' -o /tmp/awscliv2.zip && cd /tmp && unzip -qo awscliv2.zip'
                ' && sudo ./aws/install --update && rm -rf /tmp/aws /tmp/awscliv2.zip',
            ],
            "brew": ["brew", "install", "awscli"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["aws", "--version"],
        "update": {
            "_default": [
                "bash", "-c",
                'curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip"'
                ' -o /tmp/awscliv2.zip && cd /tmp && unzip -qo awscliv2.zip'
                ' && sudo ./aws/install --update && rm -rf /tmp/aws /tmp/awscliv2.zip',
            ],
            "brew": ["brew", "upgrade", "awscli"],
        },
    },
    "gcloud": {
        "label": "Google Cloud SDK",
        "category": "cloud",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSL https://sdk.cloud.google.com | bash -s -- "
                "--disable-prompts --install-dir=$HOME",
            ],
            "brew": ["brew", "install", "google-cloud-sdk"],
            "snap": ["snap", "install", "google-cloud-cli", "--classic"],
        },
        "needs_sudo": {"_default": False, "brew": False, "snap": True},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/google-cloud-sdk/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/google-cloud-sdk/bin:$PATH" && gcloud --version'],
        "prefer": ["snap", "brew"],
    },
    "az-cli": {
        "label": "Azure CLI",
        "category": "cloud",
        "cli": "az",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash",
            ],
            "brew": ["brew", "install", "azure-cli"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["az", "--version"],
        "update": {
            "_default": [
                "bash", "-c",
                "curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash",
            ],
            "brew": ["brew", "upgrade", "azure-cli"],
        },
    },

    # ════════════════════════════════════════════════════════════
    # K8s extended
    # ════════════════════════════════════════════════════════════

    "kustomize": {
        "label": "Kustomize",
        "category": "k8s",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -s https://raw.githubusercontent.com/kubernetes-sigs/"
                "kustomize/master/hack/install_kustomize.sh | bash"
                " && sudo mv kustomize /usr/local/bin/",
            ],
            "brew": ["brew", "install", "kustomize"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["kustomize", "version"],
    },
    "k9s": {
        "label": "K9s (K8s TUI)",
        "category": "k8s",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sS https://webinstall.dev/k9s | bash",
            ],
            "brew": ["brew", "install", "k9s"],
            "snap": ["snap", "install", "k9s", "--devmode"],
        },
        "needs_sudo": {"_default": False, "brew": False, "snap": True},
        "requires": {"binaries": ["curl"]},
        "verify": ["k9s", "version"],
        "prefer": ["brew", "snap"],
    },
    "stern": {
        "label": "Stern (multi-pod log tailing)",
        "category": "k8s",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -Lo stern https://github.com/stern/stern/releases/"
                "latest/download/stern_linux_amd64"
                " && chmod +x stern && sudo mv stern /usr/local/bin/",
            ],
            "brew": ["brew", "install", "stern"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["stern", "--version"],
    },
    "kubectx": {
        "label": "kubectx + kubens",
        "category": "k8s",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -Lo kubectx https://github.com/ahmetb/kubectx/releases/"
                "latest/download/kubectx"
                " && chmod +x kubectx && sudo mv kubectx /usr/local/bin/"
                " && curl -Lo kubens https://github.com/ahmetb/kubectx/"
                "releases/latest/download/kubens"
                " && chmod +x kubens && sudo mv kubens /usr/local/bin/",
            ],
            "brew": ["brew", "install", "kubectx"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["kubectx", "--help"],
    },
    "argocd-cli": {
        "label": "Argo CD CLI",
        "category": "k8s",
        "cli": "argocd",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSL -o /usr/local/bin/argocd "
                "https://github.com/argoproj/argo-cd/releases/latest/"
                "download/argocd-linux-amd64"
                " && chmod +x /usr/local/bin/argocd",
            ],
            "brew": ["brew", "install", "argocd"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["argocd", "version", "--client"],
    },
    "flux": {
        "label": "Flux CD CLI",
        "category": "k8s",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -s https://fluxcd.io/install.sh | sudo bash",
            ],
            "brew": ["brew", "install", "fluxcd/tap/flux"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["flux", "--version"],
    },
    "istioctl": {
        "label": "Istio CLI",
        "category": "k8s",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -L https://istio.io/downloadIstio | ISTIO_VERSION=latest"
                " sh - && sudo mv istio-*/bin/istioctl /usr/local/bin/"
                " && rm -rf istio-*",
            ],
            "brew": ["brew", "install", "istioctl"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["istioctl", "version", "--remote=false"],
    },
    "helmfile": {
        "label": "Helmfile",
        "category": "k8s",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -fsSL -o /usr/local/bin/helmfile "
                "https://github.com/helmfile/helmfile/releases/latest/"
                "download/helmfile_linux_amd64"
                " && chmod +x /usr/local/bin/helmfile",
            ],
            "brew": ["brew", "install", "helmfile"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl", "helm"]},
        "verify": ["helmfile", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Security tools
    # ════════════════════════════════════════════════════════════

    "snyk": {
        "label": "Snyk CLI",
        "category": "security",
        "install": {
            "_default": ["npm", "install", "-g", "snyk"],
            "brew": ["brew", "install", "snyk-cli"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["snyk", "--version"],
        "update": {
            "_default": ["npm", "update", "-g", "snyk"],
            "brew": ["brew", "upgrade", "snyk-cli"],
        },
    },
    "grype": {
        "label": "Grype (vulnerability scanner)",
        "category": "security",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL https://raw.githubusercontent.com/anchore/grype/"
                "main/install.sh | sh -s -- -b /usr/local/bin",
            ],
            "brew": ["brew", "install", "grype"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["grype", "version"],
    },
    "gitleaks": {
        "label": "Gitleaks (secret scanner)",
        "category": "security",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL https://github.com/gitleaks/gitleaks/releases/"
                "latest/download/gitleaks_linux_x64.tar.gz"
                " | tar xz -C /usr/local/bin gitleaks",
            ],
            "brew": ["brew", "install", "gitleaks"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["gitleaks", "version"],
    },
    "tfsec": {
        "label": "tfsec (Terraform security)",
        "category": "security",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL https://raw.githubusercontent.com/aquasecurity/"
                "tfsec/master/scripts/install_linux.sh | bash",
            ],
            "brew": ["brew", "install", "tfsec"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["tfsec", "--version"],
    },
    "checkov": {
        "label": "Checkov (IaC scanner)",
        "category": "security",
        "install": {
            "_default": _PIP + ["install", "checkov"],
        },
        "needs_sudo": {"_default": False},
        "verify": ["checkov", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "checkov"]},
    },
    "semgrep": {
        "label": "Semgrep (SAST)",
        "category": "security",
        "install": {
            "_default": _PIP + ["install", "semgrep"],
            "brew": ["brew", "install", "semgrep"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "verify": ["semgrep", "--version"],
        "update": {
            "_default": _PIP + ["install", "--upgrade", "semgrep"],
            "brew": ["brew", "upgrade", "semgrep"],
        },
    },
    "detect-secrets": {
        "label": "detect-secrets (Yelp)",
        "category": "security",
        "install": {
            "_default": _PIP + ["install", "detect-secrets"],
        },
        "needs_sudo": {"_default": False},
        "verify": ["detect-secrets", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade",
                                       "detect-secrets"]},
    },

    # ════════════════════════════════════════════════════════════
    # Container tools
    # ════════════════════════════════════════════════════════════

    "buildx": {
        "label": "Docker Buildx",
        "category": "container",
        "cli": "docker",
        "cli_verify_args": ["buildx", "version"],
        "install": {
            "apt": ["apt-get", "install", "-y", "docker-buildx-plugin"],
            "dnf": ["dnf", "install", "-y", "docker-buildx-plugin"],
            "_default": [
                "bash", "-c",
                "mkdir -p ~/.docker/cli-plugins"
                " && curl -sSL https://github.com/docker/buildx/releases/"
                "latest/download/buildx-linux-amd64"
                " -o ~/.docker/cli-plugins/docker-buildx"
                " && chmod +x ~/.docker/cli-plugins/docker-buildx",
            ],
        },
        "needs_sudo": {"apt": True, "dnf": True, "_default": False},
        "requires": {"binaries": ["docker"]},
        "verify": ["docker", "buildx", "version"],
    },
    "podman": {
        "label": "Podman",
        "category": "container",
        "install": {
            "apt": ["apt-get", "install", "-y", "podman"],
            "dnf": ["dnf", "install", "-y", "podman"],
            "apk": ["apk", "add", "podman"],
            "pacman": ["pacman", "-S", "--noconfirm", "podman"],
            "zypper": ["zypper", "install", "-y", "podman"],
            "brew": ["brew", "install", "podman"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["podman", "--version"],
        "update": {
            "apt": ["apt-get", "install", "-y", "--only-upgrade", "podman"],
            "dnf": ["dnf", "upgrade", "-y", "podman"],
            "brew": ["brew", "upgrade", "podman"],
        },
    },
    "skopeo": {
        "label": "Skopeo (container image tool)",
        "category": "container",
        "install": {
            "apt": ["apt-get", "install", "-y", "skopeo"],
            "dnf": ["dnf", "install", "-y", "skopeo"],
            "apk": ["apk", "add", "skopeo"],
            "pacman": ["pacman", "-S", "--noconfirm", "skopeo"],
            "brew": ["brew", "install", "skopeo"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "brew": False},
        "verify": ["skopeo", "--version"],
    },
    "dive": {
        "label": "Dive (Docker image explorer)",
        "category": "container",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL https://github.com/wagoodman/dive/releases/"
                "latest/download/dive_linux_amd64.tar.gz"
                " | tar xz -C /usr/local/bin dive",
            ],
            "brew": ["brew", "install", "dive"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["dive", "--version"],
    },
    "hadolint": {
        "label": "Hadolint (Dockerfile linter)",
        "category": "container",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL -o /usr/local/bin/hadolint "
                "https://github.com/hadolint/hadolint/releases/latest/"
                "download/hadolint-Linux-x86_64"
                " && chmod +x /usr/local/bin/hadolint",
            ],
            "brew": ["brew", "install", "hadolint"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["hadolint", "--version"],
    },
    "dagger": {
        "label": "Dagger (CI/CD engine)",
        "category": "container",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL https://dl.dagger.io/dagger/install.sh | sh",
            ],
            "brew": ["brew", "install", "dagger/tap/dagger"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["dagger", "version"],
    },

    # ════════════════════════════════════════════════════════════
    # Dev tools
    # ════════════════════════════════════════════════════════════

    "direnv": {
        "label": "direnv",
        "category": "devtools",
        "install": {
            "apt": ["apt-get", "install", "-y", "direnv"],
            "dnf": ["dnf", "install", "-y", "direnv"],
            "apk": ["apk", "add", "direnv"],
            "pacman": ["pacman", "-S", "--noconfirm", "direnv"],
            "brew": ["brew", "install", "direnv"],
            "_default": [
                "bash", "-c",
                "curl -sfL https://direnv.net/install.sh | bash",
            ],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "brew": False, "_default": True},
        "verify": ["direnv", "version"],
    },
    "tmux": {
        "label": "tmux",
        "category": "devtools",
        "install": {
            "apt": ["apt-get", "install", "-y", "tmux"],
            "dnf": ["dnf", "install", "-y", "tmux"],
            "apk": ["apk", "add", "tmux"],
            "pacman": ["pacman", "-S", "--noconfirm", "tmux"],
            "zypper": ["zypper", "install", "-y", "tmux"],
            "brew": ["brew", "install", "tmux"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["tmux", "-V"],
    },
    "fzf": {
        "label": "fzf (fuzzy finder)",
        "category": "devtools",
        "install": {
            "apt": ["apt-get", "install", "-y", "fzf"],
            "dnf": ["dnf", "install", "-y", "fzf"],
            "apk": ["apk", "add", "fzf"],
            "pacman": ["pacman", "-S", "--noconfirm", "fzf"],
            "brew": ["brew", "install", "fzf"],
            "_default": [
                "bash", "-c",
                "git clone --depth 1 https://github.com/junegunn/fzf.git "
                "~/.fzf && ~/.fzf/install --all",
            ],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "brew": False, "_default": False},
        "verify": ["fzf", "--version"],
    },
    "ripgrep": {
        "label": "ripgrep (rg)",
        "category": "devtools",
        "cli": "rg",
        "install": {
            "apt": ["apt-get", "install", "-y", "ripgrep"],
            "dnf": ["dnf", "install", "-y", "ripgrep"],
            "apk": ["apk", "add", "ripgrep"],
            "pacman": ["pacman", "-S", "--noconfirm", "ripgrep"],
            "zypper": ["zypper", "install", "-y", "ripgrep"],
            "brew": ["brew", "install", "ripgrep"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["rg", "--version"],
    },
    "bat": {
        "label": "bat (cat with syntax highlighting)",
        "category": "devtools",
        "install": {
            "apt": ["apt-get", "install", "-y", "bat"],
            "dnf": ["dnf", "install", "-y", "bat"],
            "apk": ["apk", "add", "bat"],
            "pacman": ["pacman", "-S", "--noconfirm", "bat"],
            "brew": ["brew", "install", "bat"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "brew": False},
        "verify": ["bat", "--version"],
    },
    "eza": {
        "label": "eza (modern ls)",
        "category": "devtools",
        "install": {
            "apt": ["apt-get", "install", "-y", "eza"],
            "dnf": ["dnf", "install", "-y", "eza"],
            "pacman": ["pacman", "-S", "--noconfirm", "eza"],
            "brew": ["brew", "install", "eza"],
            "_default": ["cargo", "install", "eza"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "pacman": True,
                       "brew": False, "_default": False},
        "verify": ["eza", "--version"],
    },
    "fd": {
        "label": "fd (modern find)",
        "category": "devtools",
        "cli": "fd",
        "install": {
            "apt": ["apt-get", "install", "-y", "fd-find"],
            "dnf": ["dnf", "install", "-y", "fd-find"],
            "apk": ["apk", "add", "fd"],
            "pacman": ["pacman", "-S", "--noconfirm", "fd"],
            "brew": ["brew", "install", "fd"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "brew": False},
        "verify": ["fd", "--version"],
    },
    "starship": {
        "label": "Starship (shell prompt)",
        "category": "devtools",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sS https://starship.rs/install.sh | sh -s -- -y",
            ],
            "brew": ["brew", "install", "starship"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["starship", "--version"],
    },
    "zoxide": {
        "label": "zoxide (smart cd)",
        "category": "devtools",
        "install": {
            "apt": ["apt-get", "install", "-y", "zoxide"],
            "dnf": ["dnf", "install", "-y", "zoxide"],
            "pacman": ["pacman", "-S", "--noconfirm", "zoxide"],
            "brew": ["brew", "install", "zoxide"],
            "_default": [
                "bash", "-c",
                "curl -sS https://raw.githubusercontent.com/ajeetdsouza/"
                "zoxide/main/install.sh | bash",
            ],
        },
        "needs_sudo": {"apt": True, "dnf": True, "pacman": True,
                       "brew": False, "_default": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["zoxide", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Python extended
    # ════════════════════════════════════════════════════════════

    "poetry": {
        "label": "Poetry (Python packaging)",
        "category": "python",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSL https://install.python-poetry.org | python3 -",
            ],
            "brew": ["brew", "install", "poetry"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.local/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.local/bin:$PATH" && poetry --version'],
    },
    "uv": {
        "label": "uv (fast Python package manager)",
        "category": "python",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -LsSf https://astral.sh/uv/install.sh | sh",
            ],
            "brew": ["brew", "install", "uv"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.cargo/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.cargo/bin:$PATH" && uv --version'],
    },
    "pyright": {
        "label": "Pyright (Python type checker)",
        "category": "python",
        "install": {
            "_default": ["npm", "install", "-g", "pyright"],
            "brew": ["brew", "install", "pyright"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["pyright", "--version"],
        "update": {
            "_default": ["npm", "update", "-g", "pyright"],
            "brew": ["brew", "upgrade", "pyright"],
        },
    },
    "isort": {
        "label": "isort (import sorter)",
        "category": "python",
        "install": {"_default": _PIP + ["install", "isort"]},
        "needs_sudo": {"_default": False},
        "verify": ["isort", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "isort"]},
    },
    "flake8": {
        "label": "Flake8 (Python linter)",
        "category": "python",
        "install": {"_default": _PIP + ["install", "flake8"]},
        "needs_sudo": {"_default": False},
        "verify": ["flake8", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "flake8"]},
    },
    "tox": {
        "label": "tox (test automation)",
        "category": "python",
        "install": {"_default": _PIP + ["install", "tox"]},
        "needs_sudo": {"_default": False},
        "verify": ["tox", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "tox"]},
    },
    "nox": {
        "label": "nox (test automation)",
        "category": "python",
        "install": {"_default": _PIP + ["install", "nox"]},
        "needs_sudo": {"_default": False},
        "verify": ["nox", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "nox"]},
    },
    "pdm": {
        "label": "PDM (Python package manager)",
        "category": "python",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSL https://pdm-project.org/install-pdm.py | python3 -",
            ],
            "brew": ["brew", "install", "pdm"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.local/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.local/bin:$PATH" && pdm --version'],
    },
    "hatch": {
        "label": "Hatch (Python project manager)",
        "category": "python",
        "install": {
            "_default": _PIP + ["install", "hatch"],
            "brew": ["brew", "install", "hatch"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "verify": ["hatch", "--version"],
        "update": {
            "_default": _PIP + ["install", "--upgrade", "hatch"],
            "brew": ["brew", "upgrade", "hatch"],
        },
    },

    # ════════════════════════════════════════════════════════════
    # Node.js extended
    # ════════════════════════════════════════════════════════════

    "yarn": {
        "label": "Yarn",
        "category": "node",
        "install": {
            "_default": ["npm", "install", "-g", "yarn"],
            "brew": ["brew", "install", "yarn"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["yarn", "--version"],
        "update": {
            "_default": ["npm", "update", "-g", "yarn"],
            "brew": ["brew", "upgrade", "yarn"],
        },
    },
    "pnpm": {
        "label": "pnpm",
        "category": "node",
        "install": {
            "_default": ["npm", "install", "-g", "pnpm"],
            "brew": ["brew", "install", "pnpm"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["pnpm", "--version"],
        "update": {
            "_default": ["npm", "update", "-g", "pnpm"],
            "brew": ["brew", "upgrade", "pnpm"],
        },
    },
    "bun": {
        "label": "Bun (JS runtime)",
        "category": "node",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -fsSL https://bun.sh/install | bash",
            ],
            "brew": ["brew", "install", "oven-sh/bun/bun"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.bun/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.bun/bin:$PATH" && bun --version'],
    },
    "tsx": {
        "label": "tsx (TypeScript execute)",
        "category": "node",
        "install": {"_default": ["npm", "install", "-g", "tsx"]},
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["tsx", "--version"],
        "update": {"_default": ["npm", "update", "-g", "tsx"]},
    },
    "vitest": {
        "label": "Vitest (test framework)",
        "category": "node",
        "install": {"_default": ["npm", "install", "-g", "vitest"]},
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["vitest", "--version"],
        "update": {"_default": ["npm", "update", "-g", "vitest"]},
    },
    "playwright": {
        "label": "Playwright (browser testing)",
        "category": "node",
        "install": {"_default": ["npm", "install", "-g", "playwright"]},
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["npx", "playwright", "--version"],
        "cli": "npx",
    },

    # ════════════════════════════════════════════════════════════
    # C/C++ build tools
    # ════════════════════════════════════════════════════════════

    "gcc": {
        "label": "GCC",
        "category": "cpp",
        "install": {
            "apt": ["apt-get", "install", "-y", "gcc"],
            "dnf": ["dnf", "install", "-y", "gcc"],
            "apk": ["apk", "add", "gcc", "musl-dev"],
            "pacman": ["pacman", "-S", "--noconfirm", "gcc"],
            "zypper": ["zypper", "install", "-y", "gcc"],
            "brew": ["brew", "install", "gcc"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["gcc", "--version"],
    },
    "clang": {
        "label": "Clang/LLVM",
        "category": "cpp",
        "install": {
            "apt": ["apt-get", "install", "-y", "clang"],
            "dnf": ["dnf", "install", "-y", "clang"],
            "apk": ["apk", "add", "clang"],
            "pacman": ["pacman", "-S", "--noconfirm", "clang"],
            "zypper": ["zypper", "install", "-y", "clang"],
            "brew": ["brew", "install", "llvm"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["clang", "--version"],
    },
    "cmake": {
        "label": "CMake",
        "category": "cpp",
        "install": {
            "apt": ["apt-get", "install", "-y", "cmake"],
            "dnf": ["dnf", "install", "-y", "cmake"],
            "apk": ["apk", "add", "cmake"],
            "pacman": ["pacman", "-S", "--noconfirm", "cmake"],
            "zypper": ["zypper", "install", "-y", "cmake"],
            "brew": ["brew", "install", "cmake"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["cmake", "--version"],
    },
    "ninja": {
        "label": "Ninja (build system)",
        "category": "cpp",
        "install": {
            "apt": ["apt-get", "install", "-y", "ninja-build"],
            "dnf": ["dnf", "install", "-y", "ninja-build"],
            "apk": ["apk", "add", "samurai"],
            "pacman": ["pacman", "-S", "--noconfirm", "ninja"],
            "zypper": ["zypper", "install", "-y", "ninja"],
            "brew": ["brew", "install", "ninja"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "cli": "ninja",
        "verify": ["ninja", "--version"],
    },
    "valgrind": {
        "label": "Valgrind (memory debugger)",
        "category": "cpp",
        "install": {
            "apt": ["apt-get", "install", "-y", "valgrind"],
            "dnf": ["dnf", "install", "-y", "valgrind"],
            "apk": ["apk", "add", "valgrind"],
            "pacman": ["pacman", "-S", "--noconfirm", "valgrind"],
            "zypper": ["zypper", "install", "-y", "valgrind"],
            "brew": ["brew", "install", "valgrind"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["valgrind", "--version"],
    },
    "gdb": {
        "label": "GDB (debugger)",
        "category": "cpp",
        "install": {
            "apt": ["apt-get", "install", "-y", "gdb"],
            "dnf": ["dnf", "install", "-y", "gdb"],
            "apk": ["apk", "add", "gdb"],
            "pacman": ["pacman", "-S", "--noconfirm", "gdb"],
            "zypper": ["zypper", "install", "-y", "gdb"],
            "brew": ["brew", "install", "gdb"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["gdb", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # IaC tools
    # ════════════════════════════════════════════════════════════

    "ansible": {
        "label": "Ansible",
        "category": "iac",
        "install": {
            "_default": _PIP + ["install", "ansible"],
            "apt": ["apt-get", "install", "-y", "ansible"],
            "dnf": ["dnf", "install", "-y", "ansible"],
            "brew": ["brew", "install", "ansible"],
        },
        "needs_sudo": {"_default": False, "apt": True,
                       "dnf": True, "brew": False},
        "verify": ["ansible", "--version"],
        "update": {
            "_default": _PIP + ["install", "--upgrade", "ansible"],
            "brew": ["brew", "upgrade", "ansible"],
        },
    },
    "pulumi": {
        "label": "Pulumi",
        "category": "iac",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -fsSL https://get.pulumi.com | sh",
            ],
            "brew": ["brew", "install", "pulumi"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.pulumi/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.pulumi/bin:$PATH" && pulumi version'],
    },
    "cdktf": {
        "label": "CDK for Terraform",
        "category": "iac",
        "install": {"_default": ["npm", "install", "-g", "cdktf-cli"]},
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["cdktf", "--version"],
        "update": {"_default": ["npm", "update", "-g", "cdktf-cli"]},
    },

    # ════════════════════════════════════════════════════════════
    # Database CLIs
    # ════════════════════════════════════════════════════════════

    "psql": {
        "label": "PostgreSQL client",
        "category": "database",
        "install": {
            "apt": ["apt-get", "install", "-y", "postgresql-client"],
            "dnf": ["dnf", "install", "-y", "postgresql"],
            "apk": ["apk", "add", "postgresql-client"],
            "pacman": ["pacman", "-S", "--noconfirm", "postgresql"],
            "zypper": ["zypper", "install", "-y", "postgresql"],
            "brew": ["brew", "install", "libpq"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["psql", "--version"],
    },
    "mysql-client": {
        "label": "MySQL client",
        "category": "database",
        "cli": "mysql",
        "install": {
            "apt": ["apt-get", "install", "-y", "mysql-client"],
            "dnf": ["dnf", "install", "-y", "mysql"],
            "apk": ["apk", "add", "mysql-client"],
            "pacman": ["pacman", "-S", "--noconfirm", "mariadb-clients"],
            "zypper": ["zypper", "install", "-y", "mysql-client"],
            "brew": ["brew", "install", "mysql-client"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["mysql", "--version"],
    },
    "mongosh": {
        "label": "MongoDB Shell",
        "category": "database",
        "install": {
            "_default": ["npm", "install", "-g", "mongosh"],
            "brew": ["brew", "install", "mongosh"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["mongosh", "--version"],
        "update": {
            "_default": ["npm", "update", "-g", "mongosh"],
            "brew": ["brew", "upgrade", "mongosh"],
        },
    },
    "redis-cli": {
        "label": "Redis CLI",
        "category": "database",
        "cli": "redis-cli",
        "install": {
            "apt": ["apt-get", "install", "-y", "redis-tools"],
            "dnf": ["dnf", "install", "-y", "redis"],
            "apk": ["apk", "add", "redis"],
            "pacman": ["pacman", "-S", "--noconfirm", "redis"],
            "zypper": ["zypper", "install", "-y", "redis"],
            "brew": ["brew", "install", "redis"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["redis-cli", "--version"],
    },
    "sqlite3": {
        "label": "SQLite3",
        "category": "database",
        "install": {
            "apt": ["apt-get", "install", "-y", "sqlite3"],
            "dnf": ["dnf", "install", "-y", "sqlite"],
            "apk": ["apk", "add", "sqlite"],
            "pacman": ["pacman", "-S", "--noconfirm", "sqlite"],
            "zypper": ["zypper", "install", "-y", "sqlite3"],
            "brew": ["brew", "install", "sqlite"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["sqlite3", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # CI/CD tools
    # ════════════════════════════════════════════════════════════

    "act": {
        "cli": "act",
        "label": "act (local GitHub Actions)",
        "category": "cicd",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL https://raw.githubusercontent.com/nektos/act/"
                "master/install.sh | sudo bash",
            ],
            "brew": ["brew", "install", "act"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl", "docker"]},
        "verify": ["act", "--version"],
    },
    "gitlab-cli": {
        "label": "GitLab CLI (glab)",
        "category": "cicd",
        "cli": "glab",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL https://raw.githubusercontent.com/profclems/"
                "glab/trunk/scripts/install.sh | sudo sh",
            ],
            "brew": ["brew", "install", "glab"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["glab", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Networking tools
    # ════════════════════════════════════════════════════════════

    "mkcert": {
        "label": "mkcert (local TLS certs)",
        "category": "network",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL -o /usr/local/bin/mkcert "
                "https://github.com/FiloSottile/mkcert/releases/latest/"
                "download/mkcert-linux-amd64"
                " && chmod +x /usr/local/bin/mkcert",
            ],
            "brew": ["brew", "install", "mkcert"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["mkcert", "--version"],
    },
    "caddy": {
        "label": "Caddy (web server)",
        "category": "network",
        "install": {
            "apt": ["apt-get", "install", "-y", "caddy"],
            "dnf": ["dnf", "install", "-y", "caddy"],
            "pacman": ["pacman", "-S", "--noconfirm", "caddy"],
            "brew": ["brew", "install", "caddy"],
            "_default": [
                "bash", "-c",
                "curl -sSfL https://getcaddy.com | bash -s personal",
            ],
        },
        "needs_sudo": {"apt": True, "dnf": True, "pacman": True,
                       "brew": False, "_default": True},
        "verify": ["caddy", "version"],
    },

    # ════════════════════════════════════════════════════════════
    # Java stack
    # ════════════════════════════════════════════════════════════

    "openjdk": {
        "label": "OpenJDK",
        "category": "java",
        "cli": "java",
        "install": {
            "apt": ["apt-get", "install", "-y", "default-jdk"],
            "dnf": ["dnf", "install", "-y", "java-latest-openjdk-devel"],
            "apk": ["apk", "add", "openjdk17"],
            "pacman": ["pacman", "-S", "--noconfirm", "jdk-openjdk"],
            "zypper": ["zypper", "install", "-y", "java-17-openjdk-devel"],
            "brew": ["brew", "install", "openjdk"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["java", "--version"],
    },
    "maven": {
        "label": "Apache Maven",
        "category": "java",
        "cli": "mvn",
        "install": {
            "apt": ["apt-get", "install", "-y", "maven"],
            "dnf": ["dnf", "install", "-y", "maven"],
            "apk": ["apk", "add", "maven"],
            "pacman": ["pacman", "-S", "--noconfirm", "maven"],
            "zypper": ["zypper", "install", "-y", "maven"],
            "brew": ["brew", "install", "maven"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "requires": {"binaries": ["java"]},
        "verify": ["mvn", "--version"],
    },
    "gradle": {
        "label": "Gradle",
        "category": "java",
        "install": {
            "apt": ["apt-get", "install", "-y", "gradle"],
            "dnf": ["dnf", "install", "-y", "gradle"],
            "pacman": ["pacman", "-S", "--noconfirm", "gradle"],
            "brew": ["brew", "install", "gradle"],
            "snap": ["snap", "install", "gradle", "--classic"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "pacman": True,
                       "brew": False, "snap": True},
        "requires": {"binaries": ["java"]},
        "verify": ["gradle", "--version"],
        "prefer": ["snap", "brew"],
    },

    # ════════════════════════════════════════════════════════════
    # Ruby stack
    # ════════════════════════════════════════════════════════════

    "ruby": {
        "label": "Ruby",
        "category": "ruby",
        "install": {
            "apt": ["apt-get", "install", "-y", "ruby-full"],
            "dnf": ["dnf", "install", "-y", "ruby", "ruby-devel"],
            "apk": ["apk", "add", "ruby", "ruby-dev"],
            "pacman": ["pacman", "-S", "--noconfirm", "ruby"],
            "zypper": ["zypper", "install", "-y", "ruby-devel"],
            "brew": ["brew", "install", "ruby"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["ruby", "--version"],
    },
    "bundler": {
        "label": "Bundler (Ruby dependency manager)",
        "category": "ruby",
        "cli": "bundle",
        "install": {"_default": ["gem", "install", "bundler"]},
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["ruby"]},
        "verify": ["bundle", "--version"],
    },
    "rubocop": {
        "label": "RuboCop (Ruby linter)",
        "category": "ruby",
        "install": {"_default": ["gem", "install", "rubocop"]},
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["ruby"]},
        "verify": ["rubocop", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # PHP stack
    # ════════════════════════════════════════════════════════════

    "php": {
        "label": "PHP",
        "category": "php",
        "install": {
            "apt": ["apt-get", "install", "-y", "php-cli"],
            "dnf": ["dnf", "install", "-y", "php-cli"],
            "apk": ["apk", "add", "php83"],
            "pacman": ["pacman", "-S", "--noconfirm", "php"],
            "zypper": ["zypper", "install", "-y", "php8"],
            "brew": ["brew", "install", "php"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["php", "--version"],
    },
    "composer": {
        "label": "Composer (PHP dependency manager)",
        "category": "php",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sS https://getcomposer.org/installer | php"
                " && sudo mv composer.phar /usr/local/bin/composer",
            ],
            "brew": ["brew", "install", "composer"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["php", "curl"]},
        "verify": ["composer", "--version"],
    },
    "phpstan": {
        "label": "PHPStan (PHP static analysis)",
        "category": "php",
        "install": {
            "_default": [
                "bash", "-c",
                "composer global require phpstan/phpstan",
            ],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["composer"]},
        "post_env": 'export PATH="$HOME/.config/composer/vendor/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.config/composer/vendor/bin:$PATH"'
                   ' && phpstan --version'],
    },
    "phpunit": {
        "label": "PHPUnit (PHP testing)",
        "category": "php",
        "install": {
            "_default": [
                "bash", "-c",
                "composer global require phpunit/phpunit",
            ],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["composer"]},
        "post_env": 'export PATH="$HOME/.config/composer/vendor/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.config/composer/vendor/bin:$PATH"'
                   ' && phpunit --version'],
    },

    # ════════════════════════════════════════════════════════════
    # Batch 2 — Rust extended
    # ════════════════════════════════════════════════════════════

    "cargo-watch": {
        "label": "cargo-watch (file watcher)",
        "category": "rust",
        "install": {"_default": ["cargo", "install", "cargo-watch"]},
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["cargo"]},
        "verify": ["cargo", "watch", "--version"],
    },
    "cargo-edit": {
        "label": "cargo-edit (add/rm/upgrade)",
        "category": "rust",
        "install": {"_default": ["cargo", "install", "cargo-edit"]},
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["cargo"]},
        "verify": ["cargo", "add", "--version"],
    },
    "cargo-nextest": {
        "label": "cargo-nextest (test runner)",
        "category": "rust",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -LsSf https://get.nexte.st/latest/linux"
                " | tar zxf - -C ${CARGO_HOME:-~/.cargo}/bin",
            ],
            "brew": ["brew", "install", "cargo-nextest"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["cargo", "curl"]},
        "verify": ["cargo", "nextest", "--version"],
    },
    "sccache": {
        "label": "sccache (compilation cache)",
        "category": "rust",
        "install": {
            "_default": ["cargo", "install", "sccache"],
            "brew": ["brew", "install", "sccache"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["cargo"]},
        "verify": ["sccache", "--version"],
    },
    "cross": {
        "label": "cross (cross-compilation)",
        "category": "rust",
        "install": {"_default": ["cargo", "install", "cross"]},
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["cargo", "docker"]},
        "verify": ["cross", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Monitoring & Observability
    # ════════════════════════════════════════════════════════════

    "prometheus": {
        "label": "Prometheus",
        "category": "monitoring",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL https://github.com/prometheus/prometheus/"
                "releases/latest/download/prometheus-*.linux-amd64.tar.gz"
                " | tar xz --strip-components=1 -C /usr/local/bin"
                " prometheus promtool",
            ],
            "brew": ["brew", "install", "prometheus"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["prometheus", "--version"],
    },
    "grafana-cli": {
        "label": "Grafana CLI",
        "category": "monitoring",
        "cli": "grafana-cli",
        "install": {
            "apt": ["apt-get", "install", "-y", "grafana"],
            "dnf": ["dnf", "install", "-y", "grafana"],
            "brew": ["brew", "install", "grafana"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "brew": False},
        "verify": ["grafana-cli", "--version"],
    },
    "loki": {
        "label": "Grafana Loki",
        "category": "monitoring",
        "cli": "loki",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL -o /usr/local/bin/loki"
                " https://github.com/grafana/loki/releases/latest/download/"
                "loki-linux-amd64.zip && chmod +x /usr/local/bin/loki",
            ],
            "brew": ["brew", "install", "loki"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["loki", "--version"],
    },
    "promtail": {
        "label": "Promtail (Loki agent)",
        "category": "monitoring",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL -o /usr/local/bin/promtail"
                " https://github.com/grafana/loki/releases/latest/download/"
                "promtail-linux-amd64.zip && chmod +x /usr/local/bin/promtail",
            ],
            "brew": ["brew", "install", "promtail"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["promtail", "--version"],
    },
    "jaeger": {
        "label": "Jaeger (distributed tracing)",
        "category": "monitoring",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL https://github.com/jaegertracing/jaeger/releases/"
                "latest/download/jaeger-all-in-one-linux-amd64.tar.gz"
                " | tar xz -C /usr/local/bin",
            ],
            "brew": ["brew", "install", "jaeger"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["jaeger-all-in-one", "version"],
        "cli": "jaeger-all-in-one",
    },
    "vegeta": {
        "label": "Vegeta (HTTP load testing)",
        "category": "monitoring",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL https://github.com/tsenart/vegeta/releases/"
                "latest/download/vegeta_linux_amd64.tar.gz"
                " | tar xz -C /usr/local/bin vegeta",
            ],
            "brew": ["brew", "install", "vegeta"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["vegeta", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Shell utilities
    # ════════════════════════════════════════════════════════════

    "shellcheck": {
        "label": "ShellCheck (shell linter)",
        "category": "shell",
        "install": {
            "apt": ["apt-get", "install", "-y", "shellcheck"],
            "dnf": ["dnf", "install", "-y", "ShellCheck"],
            "apk": ["apk", "add", "shellcheck"],
            "pacman": ["pacman", "-S", "--noconfirm", "shellcheck"],
            "zypper": ["zypper", "install", "-y", "ShellCheck"],
            "brew": ["brew", "install", "shellcheck"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["shellcheck", "--version"],
    },
    "shfmt": {
        "label": "shfmt (shell formatter)",
        "category": "shell",
        "install": {
            "_default": ["go", "install",
                         "mvdan.cc/sh/v3/cmd/shfmt@latest"],
            "brew": ["brew", "install", "shfmt"],
            "snap": ["snap", "install", "shfmt"],
        },
        "needs_sudo": {"_default": False, "brew": False, "snap": True},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && shfmt --version'],
    },
    "bats": {
        "label": "Bats (Bash testing)",
        "category": "shell",
        "install": {
            "apt": ["apt-get", "install", "-y", "bats"],
            "brew": ["brew", "install", "bats-core"],
            "_default": [
                "bash", "-c",
                "git clone https://github.com/bats-core/bats-core.git /tmp/bats"
                " && cd /tmp/bats && sudo ./install.sh /usr/local"
                " && rm -rf /tmp/bats",
            ],
        },
        "needs_sudo": {"apt": True, "brew": False, "_default": True},
        "verify": ["bats", "--version"],
    },
    "zsh": {
        "label": "Zsh",
        "category": "shell",
        "install": {
            "apt": ["apt-get", "install", "-y", "zsh"],
            "dnf": ["dnf", "install", "-y", "zsh"],
            "apk": ["apk", "add", "zsh"],
            "pacman": ["pacman", "-S", "--noconfirm", "zsh"],
            "zypper": ["zypper", "install", "-y", "zsh"],
            "brew": ["brew", "install", "zsh"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["zsh", "--version"],
    },
    "fish": {
        "label": "Fish shell",
        "category": "shell",
        "install": {
            "apt": ["apt-get", "install", "-y", "fish"],
            "dnf": ["dnf", "install", "-y", "fish"],
            "apk": ["apk", "add", "fish"],
            "pacman": ["pacman", "-S", "--noconfirm", "fish"],
            "zypper": ["zypper", "install", "-y", "fish"],
            "brew": ["brew", "install", "fish"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["fish", "--version"],
    },
    "nushell": {
        "label": "Nushell",
        "category": "shell",
        "cli": "nu",
        "install": {
            "_default": ["cargo", "install", "nu"],
            "brew": ["brew", "install", "nushell"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "verify": ["nu", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Networking extended
    # ════════════════════════════════════════════════════════════

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

    # ════════════════════════════════════════════════════════════
    # Data / ML extended
    # ════════════════════════════════════════════════════════════

    "jupyter": {
        "label": "Jupyter Notebook",
        "category": "ml",
        "install": {"_default": _PIP + ["install", "jupyter"]},
        "needs_sudo": {"_default": False},
        "verify": ["jupyter", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "jupyter"]},
    },
    "numpy": {
        "label": "NumPy",
        "category": "ml",
        "install": {"_default": _PIP + ["install", "numpy"]},
        "needs_sudo": {"_default": False},
        "cli": "python3",
        "verify": ["python3", "-c", "import numpy; print(numpy.__version__)"],
    },
    "pandas": {
        "label": "Pandas",
        "category": "ml",
        "install": {"_default": _PIP + ["install", "pandas"]},
        "needs_sudo": {"_default": False},
        "cli": "python3",
        "verify": ["python3", "-c", "import pandas; print(pandas.__version__)"],
    },
    "tensorflow": {
        "label": "TensorFlow",
        "category": "ml",
        "install": {"_default": _PIP + ["install", "tensorflow"]},
        "needs_sudo": {"_default": False},
        "cli": "python3",
        "verify": ["python3", "-c",
                   "import tensorflow; print(tensorflow.__version__)"],
    },

    # ════════════════════════════════════════════════════════════
    # Virtualization
    # ════════════════════════════════════════════════════════════

    "vagrant": {
        "label": "Vagrant",
        "category": "virtualization",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -fsSL https://apt.releases.hashicorp.com/gpg"
                " | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp.gpg"
                ' && echo "deb [signed-by=/usr/share/keyrings/hashicorp.gpg]'
                ' https://apt.releases.hashicorp.com $(lsb_release -cs) main"'
                " | sudo tee /etc/apt/sources.list.d/hashicorp.list"
                " && sudo apt-get update && sudo apt-get install -y vagrant",
            ],
            "brew": ["brew", "install", "vagrant"],
            "dnf": ["dnf", "install", "-y", "vagrant"],
            "pacman": ["pacman", "-S", "--noconfirm", "vagrant"],
        },
        "needs_sudo": {"_default": True, "brew": False,
                       "dnf": True, "pacman": True},
        "verify": ["vagrant", "--version"],
    },
    "packer": {
        "label": "Packer (image builder)",
        "category": "virtualization",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -fsSL https://apt.releases.hashicorp.com/gpg"
                " | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp.gpg"
                ' && echo "deb [signed-by=/usr/share/keyrings/hashicorp.gpg]'
                ' https://apt.releases.hashicorp.com $(lsb_release -cs) main"'
                " | sudo tee /etc/apt/sources.list.d/hashicorp.list"
                " && sudo apt-get update && sudo apt-get install -y packer",
            ],
            "brew": ["brew", "install", "packer"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["packer", "--version"],
    },
    "qemu": {
        "label": "QEMU",
        "category": "virtualization",
        "cli": "qemu-system-x86_64",
        "install": {
            "apt": ["apt-get", "install", "-y", "qemu-system"],
            "dnf": ["dnf", "install", "-y", "qemu-kvm"],
            "apk": ["apk", "add", "qemu-system-x86_64"],
            "pacman": ["pacman", "-S", "--noconfirm", "qemu-full"],
            "zypper": ["zypper", "install", "-y", "qemu"],
            "brew": ["brew", "install", "qemu"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["qemu-system-x86_64", "--version"],
    },
    "libvirt": {
        "label": "libvirt (VM management)",
        "category": "virtualization",
        "cli": "virsh",
        "install": {
            "apt": ["apt-get", "install", "-y", "libvirt-daemon-system",
                    "libvirt-clients"],
            "dnf": ["dnf", "install", "-y", "libvirt", "libvirt-client"],
            "apk": ["apk", "add", "libvirt", "libvirt-client"],
            "pacman": ["pacman", "-S", "--noconfirm", "libvirt"],
            "zypper": ["zypper", "install", "-y", "libvirt",
                       "libvirt-client"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True},
        "verify": ["virsh", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Messaging / Queue
    # ════════════════════════════════════════════════════════════

    "rabbitmqctl": {
        "label": "RabbitMQ tools",
        "category": "messaging",
        "cli": "rabbitmqctl",
        "install": {
            "apt": ["apt-get", "install", "-y", "rabbitmq-server"],
            "dnf": ["dnf", "install", "-y", "rabbitmq-server"],
            "brew": ["brew", "install", "rabbitmq"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "brew": False},
        "verify": ["rabbitmqctl", "version"],
    },
    "nats-cli": {
        "label": "NATS CLI",
        "category": "messaging",
        "cli": "nats",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL https://raw.githubusercontent.com/nats-io/"
                "natscli/main/install.sh | sh",
            ],
            "brew": ["brew", "install", "nats-io/nats-tools/nats"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["nats", "--version"],
    },
    "kafkacat": {
        "label": "kcat (Kafka CLI)",
        "category": "messaging",
        "cli": "kcat",
        "install": {
            "apt": ["apt-get", "install", "-y", "kafkacat"],
            "dnf": ["dnf", "install", "-y", "kafkacat"],
            "brew": ["brew", "install", "kcat"],
            "_default": [
                "bash", "-c",
                "git clone https://github.com/edenhill/kcat.git /tmp/kcat"
                " && cd /tmp/kcat && ./configure && make"
                " && sudo make install && rm -rf /tmp/kcat",
            ],
        },
        "needs_sudo": {"apt": True, "dnf": True, "brew": False,
                       "_default": True},
        "verify": ["kcat", "-V"],
    },

    # ════════════════════════════════════════════════════════════
    # System utilities
    # ════════════════════════════════════════════════════════════

    "htop": {
        "label": "htop (process viewer)",
        "category": "system",
        "install": {
            "apt": ["apt-get", "install", "-y", "htop"],
            "dnf": ["dnf", "install", "-y", "htop"],
            "apk": ["apk", "add", "htop"],
            "pacman": ["pacman", "-S", "--noconfirm", "htop"],
            "zypper": ["zypper", "install", "-y", "htop"],
            "brew": ["brew", "install", "htop"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["htop", "--version"],
    },
    "btop": {
        "label": "btop++ (resource monitor)",
        "category": "system",
        "install": {
            "apt": ["apt-get", "install", "-y", "btop"],
            "dnf": ["dnf", "install", "-y", "btop"],
            "pacman": ["pacman", "-S", "--noconfirm", "btop"],
            "brew": ["brew", "install", "btop"],
            "snap": ["snap", "install", "btop"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "pacman": True,
                       "brew": False, "snap": True},
        "verify": ["btop", "--version"],
    },
    "ncdu": {
        "label": "ncdu (disk usage analyzer)",
        "category": "system",
        "install": {
            "apt": ["apt-get", "install", "-y", "ncdu"],
            "dnf": ["dnf", "install", "-y", "ncdu"],
            "apk": ["apk", "add", "ncdu"],
            "pacman": ["pacman", "-S", "--noconfirm", "ncdu"],
            "zypper": ["zypper", "install", "-y", "ncdu"],
            "brew": ["brew", "install", "ncdu"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["ncdu", "--version"],
    },
    "tree": {
        "label": "tree (directory listing)",
        "category": "system",
        "install": {
            "apt": ["apt-get", "install", "-y", "tree"],
            "dnf": ["dnf", "install", "-y", "tree"],
            "apk": ["apk", "add", "tree"],
            "pacman": ["pacman", "-S", "--noconfirm", "tree"],
            "zypper": ["zypper", "install", "-y", "tree"],
            "brew": ["brew", "install", "tree"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["tree", "--version"],
    },
    "strace": {
        "label": "strace (system call tracer)",
        "category": "system",
        "install": {
            "apt": ["apt-get", "install", "-y", "strace"],
            "dnf": ["dnf", "install", "-y", "strace"],
            "apk": ["apk", "add", "strace"],
            "pacman": ["pacman", "-S", "--noconfirm", "strace"],
            "zypper": ["zypper", "install", "-y", "strace"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True},
        "verify": ["strace", "-V"],
    },
    "lsof": {
        "label": "lsof (list open files)",
        "category": "system",
        "install": {
            "apt": ["apt-get", "install", "-y", "lsof"],
            "dnf": ["dnf", "install", "-y", "lsof"],
            "apk": ["apk", "add", "lsof"],
            "pacman": ["pacman", "-S", "--noconfirm", "lsof"],
            "zypper": ["zypper", "install", "-y", "lsof"],
            "brew": ["brew", "install", "lsof"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["lsof", "-v"],
    },
    "jc": {
        "label": "jc (JSON CLI output converter)",
        "category": "system",
        "install": {
            "_default": _PIP + ["install", "jc"],
            "apt": ["apt-get", "install", "-y", "jc"],
            "brew": ["brew", "install", "jc"],
        },
        "needs_sudo": {"_default": False, "apt": True, "brew": False},
        "verify": ["jc", "--version"],
    },
    "yq": {
        "label": "yq (YAML processor)",
        "category": "system",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL -o /usr/local/bin/yq"
                " https://github.com/mikefarah/yq/releases/latest/download/"
                "yq_linux_amd64 && chmod +x /usr/local/bin/yq",
            ],
            "brew": ["brew", "install", "yq"],
            "snap": ["snap", "install", "yq"],
        },
        "needs_sudo": {"_default": True, "brew": False, "snap": True},
        "requires": {"binaries": ["curl"]},
        "verify": ["yq", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # HashiCorp extended
    # ════════════════════════════════════════════════════════════

    "vault": {
        "label": "HashiCorp Vault",
        "category": "hashicorp",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -fsSL https://apt.releases.hashicorp.com/gpg"
                " | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp.gpg"
                ' && echo "deb [signed-by=/usr/share/keyrings/hashicorp.gpg]'
                ' https://apt.releases.hashicorp.com $(lsb_release -cs) main"'
                " | sudo tee /etc/apt/sources.list.d/hashicorp.list"
                " && sudo apt-get update && sudo apt-get install -y vault",
            ],
            "brew": ["brew", "install", "vault"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["vault", "--version"],
    },
    "consul": {
        "label": "HashiCorp Consul",
        "category": "hashicorp",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -fsSL https://apt.releases.hashicorp.com/gpg"
                " | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp.gpg"
                ' && echo "deb [signed-by=/usr/share/keyrings/hashicorp.gpg]'
                ' https://apt.releases.hashicorp.com $(lsb_release -cs) main"'
                " | sudo tee /etc/apt/sources.list.d/hashicorp.list"
                " && sudo apt-get update && sudo apt-get install -y consul",
            ],
            "brew": ["brew", "install", "consul"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["consul", "--version"],
    },
    "nomad": {
        "label": "HashiCorp Nomad",
        "category": "hashicorp",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -fsSL https://apt.releases.hashicorp.com/gpg"
                " | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp.gpg"
                ' && echo "deb [signed-by=/usr/share/keyrings/hashicorp.gpg]'
                ' https://apt.releases.hashicorp.com $(lsb_release -cs) main"'
                " | sudo tee /etc/apt/sources.list.d/hashicorp.list"
                " && sudo apt-get update && sudo apt-get install -y nomad",
            ],
            "brew": ["brew", "install", "nomad"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["nomad", "--version"],
    },
    "boundary": {
        "label": "HashiCorp Boundary",
        "category": "hashicorp",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -fsSL https://apt.releases.hashicorp.com/gpg"
                " | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp.gpg"
                ' && echo "deb [signed-by=/usr/share/keyrings/hashicorp.gpg]'
                ' https://apt.releases.hashicorp.com $(lsb_release -cs) main"'
                " | sudo tee /etc/apt/sources.list.d/hashicorp.list"
                " && sudo apt-get update && sudo apt-get install -y boundary",
            ],
            "brew": ["brew", "install", "boundary"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["boundary", "version"],
    },

    # ════════════════════════════════════════════════════════════
    # Documentation tools
    # ════════════════════════════════════════════════════════════

    "sphinx": {
        "label": "Sphinx (Python docs)",
        "category": "docs",
        "cli": "sphinx-build",
        "install": {"_default": _PIP + ["install", "sphinx"]},
        "needs_sudo": {"_default": False},
        "verify": ["sphinx-build", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "sphinx"]},
    },
    "mdbook": {
        "label": "mdBook (Rust doc generator)",
        "category": "docs",
        "install": {
            "_default": ["cargo", "install", "mdbook"],
            "brew": ["brew", "install", "mdbook"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "verify": ["mdbook", "--version"],
    },
    "asciidoctor": {
        "label": "Asciidoctor",
        "category": "docs",
        "install": {
            "apt": ["apt-get", "install", "-y", "asciidoctor"],
            "dnf": ["dnf", "install", "-y", "rubygem-asciidoctor"],
            "brew": ["brew", "install", "asciidoctor"],
            "_default": ["gem", "install", "asciidoctor"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "brew": False,
                       "_default": False},
        "verify": ["asciidoctor", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Git extended
    # ════════════════════════════════════════════════════════════

    "git-lfs": {
        "label": "Git LFS",
        "category": "git",
        "install": {
            "apt": ["apt-get", "install", "-y", "git-lfs"],
            "dnf": ["dnf", "install", "-y", "git-lfs"],
            "apk": ["apk", "add", "git-lfs"],
            "pacman": ["pacman", "-S", "--noconfirm", "git-lfs"],
            "zypper": ["zypper", "install", "-y", "git-lfs"],
            "brew": ["brew", "install", "git-lfs"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["git", "lfs", "version"],
        "cli": "git",
    },
    "delta": {
        "label": "delta (git diff viewer)",
        "category": "git",
        "install": {
            "_default": ["cargo", "install", "git-delta"],
            "apt": ["apt-get", "install", "-y", "git-delta"],
            "brew": ["brew", "install", "git-delta"],
        },
        "needs_sudo": {"_default": False, "apt": True, "brew": False},
        "verify": ["delta", "--version"],
    },
    "lazygit": {
        "label": "lazygit (Git TUI)",
        "category": "git",
        "install": {
            "_default": ["go", "install",
                         "github.com/jesseduffield/lazygit@latest"],
            "brew": ["brew", "install", "lazygit"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && lazygit --version'],
    },
    "pre-commit": {
        "label": "pre-commit (Git hooks)",
        "category": "git",
        "install": {
            "_default": _PIP + ["install", "pre-commit"],
            "brew": ["brew", "install", "pre-commit"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "verify": ["pre-commit", "--version"],
        "update": {
            "_default": _PIP + ["install", "--upgrade", "pre-commit"],
            "brew": ["brew", "upgrade", "pre-commit"],
        },
    },

    # ════════════════════════════════════════════════════════════
    # Formatting / cross-language
    # ════════════════════════════════════════════════════════════

    "editorconfig-checker": {
        "label": "editorconfig-checker",
        "category": "formatting",
        "cli": "ec",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL -o /usr/local/bin/ec"
                " https://github.com/editorconfig-checker/"
                "editorconfig-checker/releases/latest/download/"
                "ec-linux-amd64 && chmod +x /usr/local/bin/ec",
            ],
            "brew": ["brew", "install", "editorconfig-checker"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["ec", "--version"],
    },
    "yamllint": {
        "label": "yamllint (YAML linter)",
        "category": "formatting",
        "install": {
            "_default": _PIP + ["install", "yamllint"],
            "apt": ["apt-get", "install", "-y", "yamllint"],
            "brew": ["brew", "install", "yamllint"],
        },
        "needs_sudo": {"_default": False, "apt": True, "brew": False},
        "verify": ["yamllint", "--version"],
    },
    "jsonlint": {
        "label": "jsonlint (JSON linter)",
        "category": "formatting",
        "install": {
            "_default": ["npm", "install", "-g", "jsonlint"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["jsonlint", "--version"],
    },
    "markdownlint": {
        "label": "markdownlint-cli",
        "category": "formatting",
        "install": {
            "_default": ["npm", "install", "-g", "markdownlint-cli"],
            "brew": ["brew", "install", "markdownlint-cli"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["markdownlint", "--version"],
    },
    "taplo": {
        "label": "taplo (TOML toolkit)",
        "category": "formatting",
        "install": {
            "_default": ["cargo", "install", "taplo-cli"],
            "brew": ["brew", "install", "taplo"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "verify": ["taplo", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Batch 3 — Editors / IDE support
    # ════════════════════════════════════════════════════════════

    "neovim": {
        "label": "Neovim",
        "category": "editors",
        "cli": "nvim",
        "install": {
            "apt": ["apt-get", "install", "-y", "neovim"],
            "dnf": ["dnf", "install", "-y", "neovim"],
            "apk": ["apk", "add", "neovim"],
            "pacman": ["pacman", "-S", "--noconfirm", "neovim"],
            "zypper": ["zypper", "install", "-y", "neovim"],
            "brew": ["brew", "install", "neovim"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["nvim", "--version"],
    },
    "helix": {
        "label": "Helix (modal editor)",
        "category": "editors",
        "cli": "hx",
        "install": {
            "apt": ["apt-get", "install", "-y", "helix"],
            "pacman": ["pacman", "-S", "--noconfirm", "helix"],
            "brew": ["brew", "install", "helix"],
            "_default": ["cargo", "install", "--locked", "helix-term"],
        },
        "needs_sudo": {"apt": True, "pacman": True,
                       "brew": False, "_default": False},
        "verify": ["hx", "--version"],
    },
    "micro": {
        "label": "Micro (terminal editor)",
        "category": "editors",
        "install": {
            "_default": [
                "bash", "-c",
                "curl https://getmic.ro | bash"
                " && sudo mv micro /usr/local/bin/",
            ],
            "apt": ["apt-get", "install", "-y", "micro"],
            "brew": ["brew", "install", "micro"],
            "snap": ["snap", "install", "micro", "--classic"],
        },
        "needs_sudo": {"_default": True, "apt": True,
                       "brew": False, "snap": True},
        "verify": ["micro", "--version"],
    },
    "code-server": {
        "label": "code-server (VS Code in browser)",
        "category": "editors",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -fsSL https://code-server.dev/install.sh | sh",
            ],
            "brew": ["brew", "install", "code-server"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["code-server", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Protobuf / gRPC
    # ════════════════════════════════════════════════════════════

    "protoc": {
        "label": "Protocol Buffers compiler",
        "category": "protobuf",
        "install": {
            "apt": ["apt-get", "install", "-y", "protobuf-compiler"],
            "dnf": ["dnf", "install", "-y", "protobuf-compiler"],
            "apk": ["apk", "add", "protobuf"],
            "pacman": ["pacman", "-S", "--noconfirm", "protobuf"],
            "zypper": ["zypper", "install", "-y", "protobuf-devel"],
            "brew": ["brew", "install", "protobuf"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["protoc", "--version"],
    },
    "grpcurl": {
        "label": "grpcurl (gRPC CLI)",
        "category": "protobuf",
        "install": {
            "_default": ["go", "install",
                         "github.com/fullstorydev/grpcurl/cmd/grpcurl@latest"],
            "brew": ["brew", "install", "grpcurl"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && grpcurl --version'],
    },
    "buf": {
        "label": "Buf (protobuf tooling)",
        "category": "protobuf",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSL https://github.com/bufbuild/buf/releases/latest/"
                "download/buf-Linux-x86_64"
                " -o /usr/local/bin/buf && chmod +x /usr/local/bin/buf",
            ],
            "brew": ["brew", "install", "bufbuild/buf/buf"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["buf", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # .NET / C#
    # ════════════════════════════════════════════════════════════

    "dotnet-sdk": {
        "label": ".NET SDK",
        "category": "dotnet",
        "cli": "dotnet",
        "install": {
            "apt": ["apt-get", "install", "-y", "dotnet-sdk-8.0"],
            "dnf": ["dnf", "install", "-y", "dotnet-sdk-8.0"],
            "brew": ["brew", "install", "dotnet"],
            "_default": [
                "bash", "-c",
                "curl -sSL https://dot.net/v1/dotnet-install.sh | bash",
            ],
        },
        "needs_sudo": {"apt": True, "dnf": True, "brew": False,
                       "_default": False},
        "verify": ["dotnet", "--version"],
    },
    "omnisharp": {
        "label": "OmniSharp (C# language server)",
        "category": "dotnet",
        "install": {
            "_default": ["dotnet", "tool", "install", "-g", "csharp-ls"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["dotnet"]},
        "cli": "csharp-ls",
        "verify": ["csharp-ls", "--version"],
    },
    "nuget": {
        "label": "NuGet CLI",
        "category": "dotnet",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSL -o /usr/local/bin/nuget.exe"
                " https://dist.nuget.org/win-x86-commandline/latest/nuget.exe"
                " && chmod +x /usr/local/bin/nuget.exe",
            ],
            "brew": ["brew", "install", "nuget"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["nuget", "help"],
        "cli": "nuget",
    },
    "dotnet-ef": {
        "label": "Entity Framework CLI",
        "category": "dotnet",
        "install": {
            "_default": ["dotnet", "tool", "install", "-g", "dotnet-ef"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["dotnet"]},
        "verify": ["dotnet", "ef", "--version"],
        "cli": "dotnet",
    },

    # ════════════════════════════════════════════════════════════
    # Elixir / Erlang
    # ════════════════════════════════════════════════════════════

    "erlang": {
        "label": "Erlang/OTP",
        "category": "elixir",
        "cli": "erl",
        "install": {
            "apt": ["apt-get", "install", "-y", "erlang"],
            "dnf": ["dnf", "install", "-y", "erlang"],
            "apk": ["apk", "add", "erlang"],
            "pacman": ["pacman", "-S", "--noconfirm", "erlang"],
            "zypper": ["zypper", "install", "-y", "erlang"],
            "brew": ["brew", "install", "erlang"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["erl", "-eval",
                   "io:format(\"~s~n\", [erlang:system_info(otp_release)]), halt().",
                   "-noshell"],
    },
    "elixir": {
        "label": "Elixir",
        "category": "elixir",
        "install": {
            "apt": ["apt-get", "install", "-y", "elixir"],
            "dnf": ["dnf", "install", "-y", "elixir"],
            "apk": ["apk", "add", "elixir"],
            "pacman": ["pacman", "-S", "--noconfirm", "elixir"],
            "brew": ["brew", "install", "elixir"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "brew": False},
        "requires": {"binaries": ["erl"]},
        "verify": ["elixir", "--version"],
    },
    "mix": {
        "label": "Mix (Elixir build tool)",
        "category": "elixir",
        "install": {
            # Mix comes with Elixir — this just verifies it
            "_default": ["elixir", "-e", "IO.puts Mix.env()"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["elixir"]},
        "verify": ["mix", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Zig
    # ════════════════════════════════════════════════════════════

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
            "_default": [
                "bash", "-c",
                "curl -sSfL -o /usr/local/bin/zls"
                " https://github.com/zigtools/zls/releases/latest/download/"
                "zls-linux-x86_64 && chmod +x /usr/local/bin/zls",
            ],
            "brew": ["brew", "install", "zls"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["zls", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Lua
    # ════════════════════════════════════════════════════════════

    "lua": {
        "label": "Lua",
        "category": "lua",
        "install": {
            "apt": ["apt-get", "install", "-y", "lua5.4"],
            "dnf": ["dnf", "install", "-y", "lua"],
            "apk": ["apk", "add", "lua5.4"],
            "pacman": ["pacman", "-S", "--noconfirm", "lua"],
            "zypper": ["zypper", "install", "-y", "lua54"],
            "brew": ["brew", "install", "lua"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["lua", "-v"],
    },
    "luarocks": {
        "label": "LuaRocks (Lua package manager)",
        "category": "lua",
        "install": {
            "apt": ["apt-get", "install", "-y", "luarocks"],
            "dnf": ["dnf", "install", "-y", "luarocks"],
            "apk": ["apk", "add", "luarocks"],
            "pacman": ["pacman", "-S", "--noconfirm", "luarocks"],
            "brew": ["brew", "install", "luarocks"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "brew": False},
        "requires": {"binaries": ["lua"]},
        "verify": ["luarocks", "--version"],
    },
    "stylua": {
        "label": "StyLua (Lua formatter)",
        "category": "lua",
        "install": {
            "_default": ["cargo", "install", "stylua"],
            "brew": ["brew", "install", "stylua"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "verify": ["stylua", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # WebAssembly
    # ════════════════════════════════════════════════════════════

    "wasmtime": {
        "label": "Wasmtime (Wasm runtime)",
        "category": "wasm",
        "install": {
            "_default": [
                "bash", "-c",
                "curl https://wasmtime.dev/install.sh -sSf | bash",
            ],
            "brew": ["brew", "install", "wasmtime"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.wasmtime/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.wasmtime/bin:$PATH" && wasmtime --version'],
    },
    "wasmer": {
        "label": "Wasmer (Wasm runtime)",
        "category": "wasm",
        "install": {
            "_default": [
                "bash", "-c",
                "curl https://get.wasmer.io -sSfL | sh",
            ],
            "brew": ["brew", "install", "wasmer"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.wasmer/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.wasmer/bin:$PATH" && wasmer --version'],
    },
    "wasm-pack": {
        "label": "wasm-pack (Rust → Wasm)",
        "category": "wasm",
        "install": {
            "_default": ["cargo", "install", "wasm-pack"],
            "brew": ["brew", "install", "wasm-pack"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["cargo"]},
        "verify": ["wasm-pack", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Crypto / TLS
    # ════════════════════════════════════════════════════════════

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
        "label": "step CLI (Smallstep CA)",
        "category": "crypto",
        "cli": "step",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL https://github.com/smallstep/cli/releases/"
                "latest/download/step-cli_amd64.deb -o /tmp/step-cli.deb"
                " && sudo dpkg -i /tmp/step-cli.deb && rm /tmp/step-cli.deb",
            ],
            "brew": ["brew", "install", "step"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["step", "--version"],
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
        "verify": ["age", "--version"],
    },
    "sops": {
        "label": "SOPS (secret encryption)",
        "category": "crypto",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL -o /usr/local/bin/sops"
                " https://github.com/getsops/sops/releases/latest/download/"
                "sops-linux-amd64 && chmod +x /usr/local/bin/sops",
            ],
            "brew": ["brew", "install", "sops"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["sops", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Backup tools
    # ════════════════════════════════════════════════════════════

    "restic": {
        "label": "Restic (backup)",
        "category": "backup",
        "install": {
            "apt": ["apt-get", "install", "-y", "restic"],
            "dnf": ["dnf", "install", "-y", "restic"],
            "apk": ["apk", "add", "restic"],
            "pacman": ["pacman", "-S", "--noconfirm", "restic"],
            "zypper": ["zypper", "install", "-y", "restic"],
            "brew": ["brew", "install", "restic"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["restic", "version"],
    },
    "borgbackup": {
        "label": "BorgBackup",
        "category": "backup",
        "cli": "borg",
        "install": {
            "apt": ["apt-get", "install", "-y", "borgbackup"],
            "dnf": ["dnf", "install", "-y", "borgbackup"],
            "apk": ["apk", "add", "borgbackup"],
            "pacman": ["pacman", "-S", "--noconfirm", "borg"],
            "zypper": ["zypper", "install", "-y", "borgbackup"],
            "brew": ["brew", "install", "borgbackup"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["borg", "--version"],
    },
    "rclone": {
        "label": "Rclone (cloud storage sync)",
        "category": "backup",
        "install": {
            "_default": [
                "bash", "-c",
                "curl https://rclone.org/install.sh | sudo bash",
            ],
            "apt": ["apt-get", "install", "-y", "rclone"],
            "brew": ["brew", "install", "rclone"],
        },
        "needs_sudo": {"_default": True, "apt": True, "brew": False},
        "verify": ["rclone", "version"],
    },

    # ════════════════════════════════════════════════════════════
    # DNS tools
    # ════════════════════════════════════════════════════════════

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
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && dnsx --version'],
    },

    # ════════════════════════════════════════════════════════════
    # Compression
    # ════════════════════════════════════════════════════════════

    "pigz": {
        "label": "pigz (parallel gzip)",
        "category": "compression",
        "install": {
            "apt": ["apt-get", "install", "-y", "pigz"],
            "dnf": ["dnf", "install", "-y", "pigz"],
            "apk": ["apk", "add", "pigz"],
            "pacman": ["pacman", "-S", "--noconfirm", "pigz"],
            "zypper": ["zypper", "install", "-y", "pigz"],
            "brew": ["brew", "install", "pigz"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["pigz", "--version"],
    },
    "zstd": {
        "label": "Zstandard",
        "category": "compression",
        "install": {
            "apt": ["apt-get", "install", "-y", "zstd"],
            "dnf": ["dnf", "install", "-y", "zstd"],
            "apk": ["apk", "add", "zstd"],
            "pacman": ["pacman", "-S", "--noconfirm", "zstd"],
            "zypper": ["zypper", "install", "-y", "zstd"],
            "brew": ["brew", "install", "zstd"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["zstd", "--version"],
    },
    "lz4": {
        "label": "LZ4",
        "category": "compression",
        "install": {
            "apt": ["apt-get", "install", "-y", "lz4"],
            "dnf": ["dnf", "install", "-y", "lz4"],
            "apk": ["apk", "add", "lz4"],
            "pacman": ["pacman", "-S", "--noconfirm", "lz4"],
            "zypper": ["zypper", "install", "-y", "lz4"],
            "brew": ["brew", "install", "lz4"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["lz4", "--version"],
    },
    "xz": {
        "label": "XZ Utils",
        "category": "compression",
        "install": {
            "apt": ["apt-get", "install", "-y", "xz-utils"],
            "dnf": ["dnf", "install", "-y", "xz"],
            "apk": ["apk", "add", "xz"],
            "pacman": ["pacman", "-S", "--noconfirm", "xz"],
            "zypper": ["zypper", "install", "-y", "xz"],
            "brew": ["brew", "install", "xz"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["xz", "--version"],
    },
    "p7zip": {
        "label": "7-Zip",
        "category": "compression",
        "cli": "7z",
        "install": {
            "apt": ["apt-get", "install", "-y", "p7zip-full"],
            "dnf": ["dnf", "install", "-y", "p7zip", "p7zip-plugins"],
            "apk": ["apk", "add", "p7zip"],
            "pacman": ["pacman", "-S", "--noconfirm", "p7zip"],
            "zypper": ["zypper", "install", "-y", "p7zip-full"],
            "brew": ["brew", "install", "p7zip"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["7z", "--help"],
    },

    # ════════════════════════════════════════════════════════════
    # Process management
    # ════════════════════════════════════════════════════════════

    "supervisor": {
        "label": "Supervisor (process manager)",
        "category": "process",
        "cli": "supervisord",
        "install": {
            "_default": _PIP + ["install", "supervisor"],
            "apt": ["apt-get", "install", "-y", "supervisor"],
            "dnf": ["dnf", "install", "-y", "supervisor"],
        },
        "needs_sudo": {"_default": False, "apt": True, "dnf": True},
        "verify": ["supervisord", "--version"],
    },
    "pm2": {
        "label": "PM2 (Node process manager)",
        "category": "process",
        "install": {
            "_default": ["npm", "install", "-g", "pm2"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["pm2", "--version"],
        "update": {"_default": ["npm", "update", "-g", "pm2"]},
    },
    "s6": {
        "label": "s6 (process supervision suite)",
        "category": "process",
        "cli": "s6-svscan",
        "install": {
            "apk": ["apk", "add", "s6"],
            "apt": ["apt-get", "install", "-y", "s6"],
            "_default": [
                "bash", "-c",
                "curl -sSfL https://skarnet.org/software/s6/s6.tar.gz"
                " | tar xz && cd s6-* && ./configure && make"
                " && sudo make install && cd .. && rm -rf s6-*",
            ],
        },
        "needs_sudo": {"apk": True, "apt": True, "_default": True},
        "verify": ["s6-svscan", "--help"],
    },

    # ════════════════════════════════════════════════════════════
    # API tools
    # ════════════════════════════════════════════════════════════

    "postman-cli": {
        "label": "Postman CLI (newman)",
        "category": "api",
        "cli": "newman",
        "install": {
            "_default": ["npm", "install", "-g", "newman"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["newman", "--version"],
        "update": {"_default": ["npm", "update", "-g", "newman"]},
    },
    "insomnia-cli": {
        "label": "Inso CLI (Insomnia)",
        "category": "api",
        "cli": "inso",
        "install": {
            "_default": ["npm", "install", "-g", "insomnia-inso"],
            "brew": ["brew", "install", "inso"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["inso", "--version"],
    },
    "swagger-cli": {
        "label": "Swagger CLI",
        "category": "api",
        "cli": "swagger-cli",
        "install": {
            "_default": ["npm", "install", "-g", "@apidevtools/swagger-cli"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["swagger-cli", "--version"],
    },
    "openapi-generator": {
        "label": "OpenAPI Generator CLI",
        "category": "api",
        "install": {
            "_default": ["npm", "install", "-g",
                         "@openapitools/openapi-generator-cli"],
            "brew": ["brew", "install", "openapi-generator"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["npm"]},
        "cli": "openapi-generator-cli",
        "verify": ["openapi-generator-cli", "version"],
    },

    # ════════════════════════════════════════════════════════════
    # Cloud / SDK extended
    # ════════════════════════════════════════════════════════════

    "doctl": {
        "label": "DigitalOcean CLI",
        "category": "cloud",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSL https://github.com/digitalocean/doctl/releases/"
                "latest/download/doctl-linux-amd64.tar.gz"
                " | tar xz -C /usr/local/bin",
            ],
            "brew": ["brew", "install", "doctl"],
            "snap": ["snap", "install", "doctl"],
        },
        "needs_sudo": {"_default": True, "brew": False, "snap": True},
        "requires": {"binaries": ["curl"]},
        "verify": ["doctl", "version"],
    },
    "linode-cli": {
        "label": "Linode CLI",
        "category": "cloud",
        "install": {
            "_default": _PIP + ["install", "linode-cli"],
            "brew": ["brew", "install", "linode-cli"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "verify": ["linode-cli", "--version"],
    },
    "flyctl": {
        "label": "Fly.io CLI",
        "category": "cloud",
        "cli": "fly",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -L https://fly.io/install.sh | sh",
            ],
            "brew": ["brew", "install", "flyctl"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.fly/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.fly/bin:$PATH" && fly version'],
    },
    "wrangler": {
        "label": "Wrangler (Cloudflare Workers)",
        "category": "cloud",
        "install": {
            "_default": ["npm", "install", "-g", "wrangler"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["wrangler", "--version"],
        "update": {"_default": ["npm", "update", "-g", "wrangler"]},
    },
    "vercel": {
        "label": "Vercel CLI",
        "category": "cloud",
        "install": {
            "_default": ["npm", "install", "-g", "vercel"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["vercel", "--version"],
        "update": {"_default": ["npm", "update", "-g", "vercel"]},
    },
    "netlify-cli": {
        "label": "Netlify CLI",
        "category": "cloud",
        "cli": "netlify",
        "install": {
            "_default": ["npm", "install", "-g", "netlify-cli"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["netlify", "--version"],
        "update": {"_default": ["npm", "update", "-g", "netlify-cli"]},
    },

    # ════════════════════════════════════════════════════════════
    # Batch 4 — Scala / JVM extended
    # ════════════════════════════════════════════════════════════

    "scala": {
        "label": "Scala",
        "category": "scala",
        "install": {
            "apt": ["apt-get", "install", "-y", "scala"],
            "dnf": ["dnf", "install", "-y", "scala"],
            "pacman": ["pacman", "-S", "--noconfirm", "scala"],
            "brew": ["brew", "install", "scala"],
        },
        "needs_sudo": {"apt": True, "dnf": True,
                       "pacman": True, "brew": False},
        "verify": ["scala", "-version"],
    },
    "sbt": {
        "label": "sbt (Scala build tool)",
        "category": "scala",
        "install": {
            "_default": [
                "bash", "-c",
                'echo "deb https://repo.scala-sbt.org/scalasbt/debian all main"'
                " | sudo tee /etc/apt/sources.list.d/sbt.list"
                " && curl -sL https://keyserver.ubuntu.com/pks/lookup?"
                "op=get&search=0x99E82A75642AC823"
                " | sudo apt-key add -"
                " && sudo apt-get update && sudo apt-get install -y sbt",
            ],
            "brew": ["brew", "install", "sbt"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "verify": ["sbt", "--version"],
    },
    "ammonite": {
        "label": "Ammonite (Scala REPL)",
        "category": "scala",
        "cli": "amm",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSL -o /usr/local/bin/amm"
                " https://github.com/com-lihaoyi/Ammonite/releases/latest/"
                "download/3.0-M2-2.13/amm && chmod +x /usr/local/bin/amm",
            ],
            "brew": ["brew", "install", "ammonite-repl"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["amm", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Kotlin
    # ════════════════════════════════════════════════════════════

    "kotlin": {
        "label": "Kotlin",
        "category": "kotlin",
        "cli": "kotlinc",
        "install": {
            "snap": ["snap", "install", "kotlin", "--classic"],
            "brew": ["brew", "install", "kotlin"],
        },
        "needs_sudo": {"snap": True, "brew": False},
        "verify": ["kotlinc", "-version"],
    },
    "ktlint": {
        "label": "ktlint (Kotlin linter)",
        "category": "kotlin",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSLO https://github.com/pinterest/ktlint/releases/"
                "latest/download/ktlint && chmod +x ktlint"
                " && sudo mv ktlint /usr/local/bin/",
            ],
            "brew": ["brew", "install", "ktlint"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["ktlint", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Haskell
    # ════════════════════════════════════════════════════════════

    "ghc": {
        "label": "GHC (Haskell compiler)",
        "category": "haskell",
        "install": {
            "apt": ["apt-get", "install", "-y", "ghc"],
            "dnf": ["dnf", "install", "-y", "ghc"],
            "pacman": ["pacman", "-S", "--noconfirm", "ghc"],
            "brew": ["brew", "install", "ghc"],
        },
        "needs_sudo": {"apt": True, "dnf": True,
                       "pacman": True, "brew": False},
        "verify": ["ghc", "--version"],
    },
    "cabal": {
        "label": "Cabal (Haskell build tool)",
        "category": "haskell",
        "cli": "cabal",
        "install": {
            "apt": ["apt-get", "install", "-y", "cabal-install"],
            "dnf": ["dnf", "install", "-y", "cabal-install"],
            "pacman": ["pacman", "-S", "--noconfirm", "cabal-install"],
            "brew": ["brew", "install", "cabal-install"],
        },
        "needs_sudo": {"apt": True, "dnf": True,
                       "pacman": True, "brew": False},
        "verify": ["cabal", "--version"],
    },
    "stack": {
        "label": "Stack (Haskell tool stack)",
        "category": "haskell",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSL https://get.haskellstack.org/ | sh",
            ],
            "brew": ["brew", "install", "haskell-stack"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["stack", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # OCaml
    # ════════════════════════════════════════════════════════════

    "ocaml": {
        "label": "OCaml",
        "category": "ocaml",
        "install": {
            "apt": ["apt-get", "install", "-y", "ocaml"],
            "dnf": ["dnf", "install", "-y", "ocaml"],
            "apk": ["apk", "add", "ocaml"],
            "pacman": ["pacman", "-S", "--noconfirm", "ocaml"],
            "brew": ["brew", "install", "ocaml"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "brew": False},
        "verify": ["ocaml", "--version"],
    },
    "opam": {
        "label": "opam (OCaml package manager)",
        "category": "ocaml",
        "install": {
            "apt": ["apt-get", "install", "-y", "opam"],
            "dnf": ["dnf", "install", "-y", "opam"],
            "pacman": ["pacman", "-S", "--noconfirm", "opam"],
            "brew": ["brew", "install", "opam"],
        },
        "needs_sudo": {"apt": True, "dnf": True,
                       "pacman": True, "brew": False},
        "verify": ["opam", "--version"],
    },
    "dune": {
        "label": "Dune (OCaml build system)",
        "category": "ocaml",
        "install": {
            "apt": ["apt-get", "install", "-y", "ocaml-dune"],
            "brew": ["brew", "install", "dune"],
            "_default": ["opam", "install", "-y", "dune"],
        },
        "needs_sudo": {"apt": True, "brew": False, "_default": False},
        "verify": ["dune", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # R language
    # ════════════════════════════════════════════════════════════

    "r-base": {
        "label": "R (language)",
        "category": "rlang",
        "cli": "R",
        "install": {
            "apt": ["apt-get", "install", "-y", "r-base"],
            "dnf": ["dnf", "install", "-y", "R"],
            "brew": ["brew", "install", "r"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "brew": False},
        "verify": ["R", "--version"],
    },
    "rscript": {
        "label": "Rscript (R CLI)",
        "category": "rlang",
        "cli": "Rscript",
        "install": {
            "apt": ["apt-get", "install", "-y", "r-base"],
            "dnf": ["dnf", "install", "-y", "R"],
            "brew": ["brew", "install", "r"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "brew": False},
        "verify": ["Rscript", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Proxy / Load balancers
    # ════════════════════════════════════════════════════════════

    "nginx": {
        "label": "Nginx",
        "category": "proxy",
        "install": {
            "apt": ["apt-get", "install", "-y", "nginx"],
            "dnf": ["dnf", "install", "-y", "nginx"],
            "apk": ["apk", "add", "nginx"],
            "pacman": ["pacman", "-S", "--noconfirm", "nginx"],
            "zypper": ["zypper", "install", "-y", "nginx"],
            "brew": ["brew", "install", "nginx"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["nginx", "-v"],
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
            "_default": [
                "bash", "-c",
                "curl -sSfL https://github.com/traefik/traefik/releases/"
                "latest/download/traefik_linux_amd64.tar.gz"
                " | tar xz -C /usr/local/bin traefik",
            ],
            "brew": ["brew", "install", "traefik"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["traefik", "version"],
    },
    "envoy": {
        "label": "Envoy Proxy",
        "category": "proxy",
        "install": {
            "apt": ["apt-get", "install", "-y", "envoy"],
            "brew": ["brew", "install", "envoy"],
            "_default": [
                "bash", "-c",
                "curl -sSfL -o /usr/local/bin/envoy"
                " https://github.com/envoyproxy/envoy/releases/latest/"
                "download/envoy-contrib-linux-x86_64"
                " && chmod +x /usr/local/bin/envoy",
            ],
        },
        "needs_sudo": {"apt": True, "brew": False, "_default": True},
        "verify": ["envoy", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Log management
    # ════════════════════════════════════════════════════════════

    "vector": {
        "label": "Vector (log pipeline)",
        "category": "logging",
        "install": {
            "_default": [
                "bash", "-c",
                "curl --proto '=https' --tlsv1.2 -sSfL"
                " https://sh.vector.dev | bash -s -- -y",
            ],
            "brew": ["brew", "install", "vectordotdev/brew/vector"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["vector", "--version"],
    },
    "fluentbit": {
        "label": "Fluent Bit",
        "category": "logging",
        "cli": "fluent-bit",
        "install": {
            "apt": ["apt-get", "install", "-y", "fluent-bit"],
            "dnf": ["dnf", "install", "-y", "fluent-bit"],
            "brew": ["brew", "install", "fluent-bit"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "brew": False},
        "verify": ["fluent-bit", "--version"],
    },
    "stern-log": {
        "label": "stern (K8s multi-pod log tailing)",
        "category": "logging",
        "cli": "stern",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL https://github.com/stern/stern/releases/"
                "latest/download/stern_linux_amd64.tar.gz"
                " | tar xz -C /usr/local/bin stern",
            ],
            "brew": ["brew", "install", "stern"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["stern", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Testing frameworks
    # ════════════════════════════════════════════════════════════

    "k6": {
        "label": "k6 (load testing)",
        "category": "testing",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL https://github.com/grafana/k6/releases/"
                "latest/download/k6-linux-amd64.tar.gz"
                " | tar xz --strip-components=1 -C /usr/local/bin",
            ],
            "brew": ["brew", "install", "k6"],
            "snap": ["snap", "install", "k6"],
        },
        "needs_sudo": {"_default": True, "brew": False, "snap": True},
        "requires": {"binaries": ["curl"]},
        "verify": ["k6", "version"],
    },
    "locust": {
        "label": "Locust (Python load testing)",
        "category": "testing",
        "install": {
            "_default": _PIP + ["install", "locust"],
        },
        "needs_sudo": {"_default": False},
        "verify": ["locust", "--version"],
    },
    "cypress": {
        "label": "Cypress (E2E testing)",
        "category": "testing",
        "install": {
            "_default": ["npm", "install", "-g", "cypress"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["cypress", "--version"],
    },
    "artillery": {
        "label": "Artillery (load testing)",
        "category": "testing",
        "install": {
            "_default": ["npm", "install", "-g", "artillery"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["artillery", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Image / media tools
    # ════════════════════════════════════════════════════════════

    "imagemagick": {
        "label": "ImageMagick",
        "category": "media",
        "cli": "magick",
        "install": {
            "apt": ["apt-get", "install", "-y", "imagemagick"],
            "dnf": ["dnf", "install", "-y", "ImageMagick"],
            "apk": ["apk", "add", "imagemagick"],
            "pacman": ["pacman", "-S", "--noconfirm", "imagemagick"],
            "zypper": ["zypper", "install", "-y", "ImageMagick"],
            "brew": ["brew", "install", "imagemagick"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["magick", "--version"],
    },
    "gifsicle": {
        "label": "Gifsicle (GIF optimizer)",
        "category": "media",
        "install": {
            "apt": ["apt-get", "install", "-y", "gifsicle"],
            "dnf": ["dnf", "install", "-y", "gifsicle"],
            "brew": ["brew", "install", "gifsicle"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "brew": False},
        "verify": ["gifsicle", "--version"],
    },
    "jpegoptim": {
        "label": "jpegoptim (JPEG optimizer)",
        "category": "media",
        "install": {
            "apt": ["apt-get", "install", "-y", "jpegoptim"],
            "dnf": ["dnf", "install", "-y", "jpegoptim"],
            "apk": ["apk", "add", "jpegoptim"],
            "pacman": ["pacman", "-S", "--noconfirm", "jpegoptim"],
            "brew": ["brew", "install", "jpegoptim"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "brew": False},
        "verify": ["jpegoptim", "--version"],
    },
    "optipng": {
        "label": "OptiPNG (PNG optimizer)",
        "category": "media",
        "install": {
            "apt": ["apt-get", "install", "-y", "optipng"],
            "dnf": ["dnf", "install", "-y", "optipng"],
            "apk": ["apk", "add", "optipng"],
            "pacman": ["pacman", "-S", "--noconfirm", "optipng"],
            "zypper": ["zypper", "install", "-y", "optipng"],
            "brew": ["brew", "install", "optipng"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["optipng", "--version"],
    },
    "svgo": {
        "label": "SVGO (SVG optimizer)",
        "category": "media",
        "install": {
            "_default": ["npm", "install", "-g", "svgo"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["npm"]},
        "verify": ["svgo", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Task runners / build automation
    # ════════════════════════════════════════════════════════════

    "task": {
        "label": "Task (task runner)",
        "category": "taskrunner",
        "install": {
            "_default": [
                "bash", "-c",
                "sh -c \"$(curl --location"
                " https://taskfile.dev/install.sh)\" -- -d -b /usr/local/bin",
            ],
            "brew": ["brew", "install", "go-task"],
            "snap": ["snap", "install", "task", "--classic"],
        },
        "needs_sudo": {"_default": True, "brew": False, "snap": True},
        "requires": {"binaries": ["curl"]},
        "verify": ["task", "--version"],
    },
    "just": {
        "label": "Just (command runner)",
        "category": "taskrunner",
        "install": {
            "_default": ["cargo", "install", "just"],
            "brew": ["brew", "install", "just"],
            "pacman": ["pacman", "-S", "--noconfirm", "just"],
        },
        "needs_sudo": {"_default": False, "brew": False, "pacman": True},
        "verify": ["just", "--version"],
    },
    "earthly": {
        "label": "Earthly (CI/CD build tool)",
        "category": "taskrunner",
        "install": {
            "_default": [
                "bash", "-c",
                "curl -sSfL https://github.com/earthly/earthly/releases/"
                "latest/download/earthly-linux-amd64"
                " -o /usr/local/bin/earthly && chmod +x /usr/local/bin/earthly",
            ],
            "brew": ["brew", "install", "earthly"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["earthly", "--version"],
    },
    "mage": {
        "label": "Mage (Go build tool)",
        "category": "taskrunner",
        "install": {
            "_default": ["go", "install",
                         "github.com/magefile/mage@latest"],
            "brew": ["brew", "install", "mage"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && mage --version'],
    },

    # ════════════════════════════════════════════════════════════
    # Service discovery / mesh
    # ════════════════════════════════════════════════════════════

    "etcd": {
        "label": "etcd",
        "category": "service_discovery",
        "cli": "etcdctl",
        "install": {
            "apt": ["apt-get", "install", "-y", "etcd-client"],
            "brew": ["brew", "install", "etcd"],
            "_default": [
                "bash", "-c",
                "curl -sSfL https://github.com/etcd-io/etcd/releases/"
                "latest/download/etcd-linux-amd64.tar.gz"
                " | tar xz --strip-components=1 -C /usr/local/bin"
                " etcdctl etcd",
            ],
        },
        "needs_sudo": {"apt": True, "brew": False, "_default": True},
        "verify": ["etcdctl", "version"],
    },
    "linkerd": {
        "label": "Linkerd CLI",
        "category": "service_discovery",
        "install": {
            "_default": [
                "bash", "-c",
                "curl --proto '=https' --tlsv1.2 -sSfL"
                " https://run.linkerd.io/install | sh",
            ],
            "brew": ["brew", "install", "linkerd"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.linkerd2/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.linkerd2/bin:$PATH" && linkerd version --client'],
    },

    # ════════════════════════════════════════════════════════════
    # Profiling / benchmarking
    # ════════════════════════════════════════════════════════════

    "perf": {
        "label": "perf (Linux profiler)",
        "category": "profiling",
        "install": {
            "apt": ["apt-get", "install", "-y", "linux-tools-common"],
            "dnf": ["dnf", "install", "-y", "perf"],
            "apk": ["apk", "add", "perf"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True},
        "verify": ["perf", "--version"],
    },
    "flamegraph": {
        "label": "FlameGraph (perf visualization)",
        "category": "profiling",
        "cli": "flamegraph.pl",
        "install": {
            "_default": [
                "bash", "-c",
                "git clone https://github.com/brendangregg/FlameGraph.git"
                " /opt/FlameGraph",
            ],
            "brew": ["brew", "install", "flamegraph"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "verify": ["bash", "-c", "test -f /opt/FlameGraph/flamegraph.pl"],
    },
    "hyperfine": {
        "label": "hyperfine (benchmarking)",
        "category": "profiling",
        "install": {
            "_default": ["cargo", "install", "hyperfine"],
            "apt": ["apt-get", "install", "-y", "hyperfine"],
            "brew": ["brew", "install", "hyperfine"],
        },
        "needs_sudo": {"_default": False, "apt": True, "brew": False},
        "verify": ["hyperfine", "--version"],
    },
    "py-spy": {
        "label": "py-spy (Python profiler)",
        "category": "profiling",
        "install": {
            "_default": _PIP + ["install", "py-spy"],
            "brew": ["brew", "install", "py-spy"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "verify": ["py-spy", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Terminal multiplexers / window managers
    # ════════════════════════════════════════════════════════════

    "screen": {
        "label": "GNU Screen",
        "category": "terminal",
        "install": {
            "apt": ["apt-get", "install", "-y", "screen"],
            "dnf": ["dnf", "install", "-y", "screen"],
            "apk": ["apk", "add", "screen"],
            "pacman": ["pacman", "-S", "--noconfirm", "screen"],
            "zypper": ["zypper", "install", "-y", "screen"],
            "brew": ["brew", "install", "screen"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["screen", "--version"],
    },
    "zellij": {
        "label": "Zellij (terminal workspace)",
        "category": "terminal",
        "install": {
            "_default": ["cargo", "install", "zellij"],
            "brew": ["brew", "install", "zellij"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "verify": ["zellij", "--version"],
    },
    "mosh": {
        "label": "Mosh (mobile shell)",
        "category": "terminal",
        "install": {
            "apt": ["apt-get", "install", "-y", "mosh"],
            "dnf": ["dnf", "install", "-y", "mosh"],
            "apk": ["apk", "add", "mosh"],
            "pacman": ["pacman", "-S", "--noconfirm", "mosh"],
            "zypper": ["zypper", "install", "-y", "mosh"],
            "brew": ["brew", "install", "mosh"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True,
                       "pacman": True, "zypper": True, "brew": False},
        "verify": ["mosh", "--version"],
    },

    # ════════════════════════════════════════════════════════════
    # Embedded / cross-compilation
    # ════════════════════════════════════════════════════════════

    "arm-gcc": {
        "label": "ARM GCC toolchain",
        "category": "embedded",
        "cli": "arm-none-eabi-gcc",
        "install": {
            "apt": ["apt-get", "install", "-y",
                    "gcc-arm-none-eabi"],
            "dnf": ["dnf", "install", "-y",
                    "arm-none-eabi-gcc-cs"],
            "pacman": ["pacman", "-S", "--noconfirm",
                       "arm-none-eabi-gcc"],
            "brew": ["brew", "install", "arm-none-eabi-gcc"],
        },
        "needs_sudo": {"apt": True, "dnf": True,
                       "pacman": True, "brew": False},
        "verify": ["arm-none-eabi-gcc", "--version"],
    },
    "openocd": {
        "label": "OpenOCD (on-chip debugger)",
        "category": "embedded",
        "install": {
            "apt": ["apt-get", "install", "-y", "openocd"],
            "dnf": ["dnf", "install", "-y", "openocd"],
            "pacman": ["pacman", "-S", "--noconfirm", "openocd"],
            "brew": ["brew", "install", "openocd"],
        },
        "needs_sudo": {"apt": True, "dnf": True,
                       "pacman": True, "brew": False},
        "verify": ["openocd", "--version"],
    },
    "platformio": {
        "label": "PlatformIO (embedded IoT)",
        "category": "embedded",
        "cli": "pio",
        "install": {
            "_default": _PIP + ["install", "platformio"],
        },
        "needs_sudo": {"_default": False},
        "verify": ["pio", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade",
                                       "platformio"]},
    },
    "esptool": {
        "label": "esptool (ESP8266/ESP32 flasher)",
        "category": "embedded",
        "install": {
            "_default": _PIP + ["install", "esptool"],
        },
        "needs_sudo": {"_default": False},
        "verify": ["esptool.py", "version"],
        "cli": "esptool.py",
    },
}

