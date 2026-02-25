"""
L0 Data — Unified tool recipe registry.

All 61 tools, all platforms. Pure data, no logic.

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
        "label": "curl",
        "install": {
            "apt":    ["apt-get", "install", "-y", "curl"],
            "dnf":    ["dnf", "install", "-y", "curl"],
            "apk":    ["apk", "add", "curl"],
            "pacman": ["pacman", "-S", "--noconfirm", "curl"],
            "zypper": ["zypper", "install", "-y", "curl"],
            "brew":   ["brew", "install", "curl"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
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
        "verify": ["python3", "-c", "import cv2; print(cv2.__version__)"],
    },

    # ── Category 12: Data pack recipes ──────────────────────────
    #
    # Spec: domain-data-packs §Recipes.
    # These produce `type: "download"` steps with disk check,
    # resume, checksums, and freshness tracking.

    "trivy-db": {
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
}
