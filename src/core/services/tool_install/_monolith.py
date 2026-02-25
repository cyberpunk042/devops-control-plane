"""
Tool installation service — install missing devops tools.

Provides install recipes for common tools and handles subprocess
execution with optional sudo password piping.

Channel-independent: no Flask or HTTP dependency.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("audit")

# ── Module-level caches and constants ──
_VERSION_FETCH_CACHE: dict[str, dict] = {}
_IARCH_MAP = {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "armhf"}

# ── Install Recipes ─────────────────────────────────────────────

import sys

# Resolve pip via the current interpreter — avoids "pip not found" when
# running inside a venv where bare `pip` isn't on the system PATH.
_PIP = [sys.executable, "-m", "pip"]


# ── Unified recipe registry ── All tools, all platforms ─────────
#
# Keys: tool ID (matches _TOOLS registry in l0_detection.py)
# See Phase 2.2 analysis for full field specification.

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


# ── System dependency checks ───────────────────────────────────────


def _is_pkg_installed(pkg: str, pkg_manager: str) -> bool:
    """Check if a single system package is installed.

    Uses the appropriate checker for the given package manager:
      apt    → dpkg-query -W -f='${Status}' PKG
      dnf    → rpm -q PKG
      yum    → rpm -q PKG
      zypper → rpm -q PKG
      apk    → apk info -e PKG
      pacman → pacman -Q PKG
      brew   → brew ls --versions PKG

    Args:
        pkg: Exact package name (must match the distro's naming).
        pkg_manager: One of: apt, dnf, yum, zypper, apk, pacman, brew.

    Returns:
        True if installed, False if not installed or check failed.
    """
    try:
        if pkg_manager == "apt":
            r = subprocess.run(
                ["dpkg-query", "-W", "-f=${Status}", pkg],
                capture_output=True, text=True, timeout=10,
            )
            return "install ok installed" in r.stdout

        if pkg_manager in ("dnf", "yum", "zypper"):
            r = subprocess.run(
                ["rpm", "-q", pkg],
                capture_output=True, timeout=10,
            )
            return r.returncode == 0

        if pkg_manager == "apk":
            r = subprocess.run(
                ["apk", "info", "-e", pkg],
                capture_output=True, timeout=10,
            )
            return r.returncode == 0

        if pkg_manager == "pacman":
            r = subprocess.run(
                ["pacman", "-Q", pkg],
                capture_output=True, timeout=10,
            )
            return r.returncode == 0

        if pkg_manager == "brew":
            r = subprocess.run(
                ["brew", "ls", "--versions", pkg],
                capture_output=True, timeout=30,  # brew is slow
            )
            return r.returncode == 0

    except FileNotFoundError:
        # Checker binary not on PATH (e.g. dpkg-query on Fedora)
        logger.warning(
            "Package checker not found for pm=%s (checking %s)",
            pkg_manager, pkg,
        )
    except subprocess.TimeoutExpired:
        logger.warning(
            "Timeout checking package %s with pm=%s",
            pkg, pkg_manager,
        )
    except OSError as exc:
        logger.warning(
            "OS error checking package %s with pm=%s: %s",
            pkg, pkg_manager, exc,
        )

    return False


def check_system_deps(
    packages: list[str],
    pkg_manager: str = "apt",
) -> dict[str, list[str]]:
    """Check which system packages are installed.

    Args:
        packages: Package names to check. Names must match the target
                  distro's naming convention (e.g. "libssl-dev" for Debian,
                  "openssl-devel" for RHEL).
        pkg_manager: Which package manager to use for checking.
                     Defaults to "apt" for backward compatibility.

    Returns:
        {"missing": ["pkg1", ...], "installed": ["pkg2", ...]}
    """
    missing: list[str] = []
    installed: list[str] = []
    for pkg in packages:
        if _is_pkg_installed(pkg, pkg_manager):
            installed.append(pkg)
        else:
            missing.append(pkg)
    return {"missing": missing, "installed": installed}


def _build_pkg_install_cmd(packages: list[str], pm: str) -> list[str]:
    """Build a package-install command for a list of packages.

    Args:
        packages: Package names to install.
        pm: Package manager ID.

    Returns:
        Command list suitable for subprocess.run().
    """
    if pm == "apt":
        return ["apt-get", "install", "-y"] + packages
    if pm == "dnf":
        return ["dnf", "install", "-y"] + packages
    if pm == "yum":
        return ["yum", "install", "-y"] + packages
    if pm == "zypper":
        return ["zypper", "install", "-y"] + packages
    if pm == "apk":
        return ["apk", "add"] + packages
    if pm == "pacman":
        return ["pacman", "-S", "--noconfirm"] + packages
    if pm == "brew":
        return ["brew", "install"] + packages
    # Unknown pm — return a no-op that explains the problem
    logger.error("No install command for package manager: %s", pm)
    return ["echo", f"ERROR: no install command for package manager '{pm}'"]


# ── Resolver engine — build ordered install plans ───────────────

import shlex


def _pick_install_method(
    recipe: dict,
    primary_pm: str,
    snap_available: bool,
) -> str | None:
    """Pick the best install method for a recipe on this system.

    Resolution order:
      1. Recipe's ``prefer`` list (respecting system availability)
      2. System's primary package manager (apt, dnf, etc.)
      3. snap (if available)
      4. ``_default`` fallback
      5. Any remaining method whose binary is on PATH

    Args:
        recipe: A TOOL_RECIPES entry.
        primary_pm: The system's primary package manager (e.g. ``"apt"``).
        snap_available: Whether snap is available on this system.

    Returns:
        A key from ``recipe["install"]``, or ``None`` if no method works.
    """
    install = recipe.get("install", {})
    if not install:
        return None

    # 1. Recipe's preferred order (respect availability)
    for method in recipe.get("prefer", []):
        if method not in install:
            continue
        if method == "snap":
            if not snap_available:
                continue
        elif method == "brew":
            if not shutil.which("brew"):
                continue
        elif method not in (primary_pm, "_default"):
            # It's a PM key that doesn't match our system — skip
            continue
        return method

    # 2. System's primary pm
    if primary_pm in install:
        return primary_pm

    # 3. snap
    if snap_available and "snap" in install:
        return "snap"

    # 4. _default
    if "_default" in install:
        return "_default"

    # 5. Any available pm that's on PATH
    for method in install:
        if method.startswith("_"):
            continue
        if shutil.which(method):
            return method

    return None


def _is_batchable(method: str, primary_pm: str) -> bool:
    """Is this install method a system package install that can be batched?"""
    return method == primary_pm


def _extract_packages_from_cmd(cmd: list[str], pm: str) -> list[str]:
    """Extract package names from a package manager install command.

    Args:
        cmd: Full install command (e.g. ``["apt-get", "install", "-y", "git"]``).
        pm: Package manager id.

    Returns:
        List of package name strings.
    """
    if pm in ("apt", "dnf", "yum", "zypper"):
        # apt-get install -y PKG1 PKG2
        return [c for c in cmd[3:] if not c.startswith("-")]
    if pm in ("apk", "brew"):
        # apk add PKG1 / brew install PKG1
        return [c for c in cmd[2:] if not c.startswith("-")]
    if pm == "pacman":
        # pacman -S --noconfirm PKG1
        return [c for c in cmd[3:] if not c.startswith("-")]
    return []


def _wrap_with_env(cmd: list[str], env_setup: str) -> list[str]:
    """Wrap a command with environment setup (e.g. PATH export).

    If the command is already a ``bash -c`` command, prepend the env setup
    to the existing expression. Otherwise wrap the whole thing in ``bash -c``.

    Args:
        cmd: Original command list.
        env_setup: Shell commands to prepend (e.g. ``'export PATH=...'``).

    Returns:
        New command list with env setup prepended.
    """
    if len(cmd) >= 3 and cmd[0] == "bash" and cmd[1] == "-c":
        return ["bash", "-c", f"{env_setup} && {cmd[2]}"]
    plain = " ".join(shlex.quote(c) for c in cmd)
    return ["bash", "-c", f"{env_setup} && {plain}"]


def _evaluate_condition(
    condition: str | None,
    system_profile: dict,
) -> bool:
    """Evaluate a post_install condition against the system profile.

    Args:
        condition: One of ``"has_systemd"``, ``"not_root"``,
                   ``"not_container"``, or ``None``.
        system_profile: Phase 1 system detection output.

    Returns:
        True if the condition is met (step should be included).
    """
    if condition is None:
        return True
    if condition == "has_systemd":
        return system_profile.get("capabilities", {}).get("systemd", False)
    if condition == "has_openrc":
        return (
            system_profile.get("init_system", {}).get("type") == "openrc"
        )
    if condition == "not_root":
        return not system_profile.get("capabilities", {}).get("is_root", False)
    if condition == "is_root":
        return system_profile.get("capabilities", {}).get("is_root", False)
    if condition == "not_container":
        return not system_profile.get("container", {}).get("in_container", False)
    if condition == "has_docker":
        return shutil.which("docker") is not None
    if condition.startswith("file_exists:"):
        target_path = condition.split(":", 1)[1]
        return os.path.isfile(target_path)
    logger.warning("Unknown post_install condition: %s", condition)
    return True


def _collect_deps(
    tool_id: str,
    system_profile: dict,
    visited: set[str],
    batch_packages: list[str],
    tool_steps: list[dict],
    batched_tools: list[str],
    post_env_map: dict[str, str],
) -> None:
    """Walk the dependency tree depth-first, collecting steps.

    Mutates *batch_packages*, *tool_steps*, *batched_tools*, and
    *post_env_map* in place.

    Args:
        tool_id: Tool to resolve.
        system_profile: Phase 1 system detection output.
        visited: Set of already-processed tool IDs (cycle guard).
        batch_packages: Accumulator for batchable system packages.
        tool_steps: Accumulator for non-batchable tool install steps.
        batched_tools: Accumulator for tool IDs installed via batch
                       (needed for post_install / verify even when batched).
        post_env_map: Maps tool_id → post_env string.
    """
    if tool_id in visited:
        return
    visited.add(tool_id)

    recipe = TOOL_RECIPES.get(tool_id)
    if not recipe:
        logger.warning("Dependency '%s' not found in TOOL_RECIPES", tool_id)
        return

    cli = recipe.get("cli", tool_id)

    # Skip if already installed
    if shutil.which(cli):
        return

    pm = system_profile.get("package_manager", {}).get("primary", "apt")
    family = system_profile.get("distro", {}).get("family", "debian")
    snap_ok = system_profile.get("package_manager", {}).get("snap_available", False)

    # 1. Recurse into binary deps first (depth-first)
    for dep_id in recipe.get("requires", {}).get("binaries", []):
        _collect_deps(
            dep_id, system_profile, visited,
            batch_packages, tool_steps, batched_tools, post_env_map,
        )

    # 2. Collect system packages for this tool
    pkg_map = recipe.get("requires", {}).get("packages", {})
    family_pkgs = pkg_map.get(family, [])
    for pkg in family_pkgs:
        if not _is_pkg_installed(pkg, pm) and pkg not in batch_packages:
            batch_packages.append(pkg)

    # 3. Pick install method
    method = _pick_install_method(recipe, pm, snap_ok)
    if method is None:
        logger.warning(
            "No install method for '%s' on pm=%s", tool_id, pm,
        )
        return

    # 4. Batchable or not?
    if _is_batchable(method, pm):
        pkgs = _extract_packages_from_cmd(recipe["install"][method], pm)
        for pkg in pkgs:
            if not _is_pkg_installed(pkg, pm) and pkg not in batch_packages:
                batch_packages.append(pkg)
        batched_tools.append(tool_id)
    else:
        tool_steps.append({
            "tool_id": tool_id,
            "recipe": recipe,
            "method": method,
        })

    # 5. Track post_env
    pe = recipe.get("post_env", "")
    if pe:
        post_env_map[tool_id] = pe


# ── Risk system ────────────────────────────────────────────────
#
# Spec source: domain-risk-levels (3 levels, inference rules,
#              backup-before, plan-level aggregation).


_HIGH_RISK_LABELS = frozenset({
    "kernel", "driver", "grub", "bootloader", "dkms", "vfio",
    "modprobe", "nvidia",
})
"""Label keywords that automatically promote a step to high risk."""


def _infer_risk(step: dict) -> str:
    """Infer risk level for a plan step from its context.

    Rules (first match wins):
        1. ``restart_required == "system"`` → **high**
        2. Label contains a high-risk keyword → **high**
        3. ``needs_sudo`` is True → **medium**
        4. Otherwise → **low**

    An explicit ``step["risk"]`` always takes precedence—this
    function is only called when ``risk`` is absent.

    Returns:
        ``"low"`` | ``"medium"`` | ``"high"``
    """
    # Explicit risk always wins.
    explicit = step.get("risk")
    if explicit in ("low", "medium", "high"):
        return explicit

    if step.get("restart_required") == "system":
        return "high"

    label = step.get("label", "").lower()
    if any(kw in label for kw in _HIGH_RISK_LABELS):
        return "high"

    if step.get("needs_sudo"):
        return "medium"

    return "low"


def check_version_constraint(
    selected_version: str,
    constraint: dict,
) -> dict:
    """Validate a selected version against a constraint rule.

    Constraint types:
        - ``minor_range``: ±N minor versions (e.g. kubectl ±1 of cluster)
        - ``gte``: >= a minimum version
        - ``exact``: must match exactly
        - ``semver_compat``: ~= compatibility (same major, >= minor)

    Args:
        selected_version: The version string chosen, e.g. ``"1.29.3"``.
        constraint: Dict with ``type``, ``reference``, and type-specific fields.
            Examples::

                {"type": "minor_range", "reference": "1.30.0", "range": 1}
                {"type": "gte", "reference": "2.0.0"}
                {"type": "exact", "reference": "3.1.4"}

    Returns:
        ``{"valid": True}`` or ``{"valid": False, "message": "...", "warning": "..."}``
    """
    def _parse_semver(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in v.lstrip("v").split(".")[:3])

    ctype = constraint.get("type", "gte")
    ref = constraint.get("reference", "")

    try:
        sel_parts = _parse_semver(selected_version)
        ref_parts = _parse_semver(ref)
    except (ValueError, IndexError):
        return {"valid": True, "parse_error": True}

    if ctype == "minor_range":
        rng = constraint.get("range", 1)
        # Compare major must match, minor within ±range
        if sel_parts[0] != ref_parts[0]:
            return {
                "valid": False,
                "message": (
                    f"Major version mismatch: {selected_version} vs {ref}. "
                    f"Must be same major version."
                ),
            }
        minor_diff = abs(sel_parts[1] - ref_parts[1])
        if minor_diff > rng:
            return {
                "valid": False,
                "message": (
                    f"Version {selected_version} is {minor_diff} minor versions "
                    f"away from {ref}. Maximum allowed: ±{rng}."
                ),
                "warning": (
                    f"kubectl should be within ±{rng} minor versions of the "
                    f"cluster version ({ref})."
                ),
            }
        return {"valid": True}

    elif ctype == "gte":
        if sel_parts >= ref_parts:
            return {"valid": True}
        return {
            "valid": False,
            "message": f"Version {selected_version} < {ref}. Minimum required: {ref}.",
        }

    elif ctype == "exact":
        if sel_parts == ref_parts:
            return {"valid": True}
        return {
            "valid": False,
            "message": f"Version {selected_version} != {ref}. Exact match required.",
        }

    elif ctype == "semver_compat":
        # ~=: same major, selected minor >= reference minor
        if sel_parts[0] != ref_parts[0]:
            return {
                "valid": False,
                "message": f"Major version mismatch: {selected_version} vs {ref}.",
            }
        if sel_parts[1:] >= ref_parts[1:]:
            return {"valid": True}
        return {
            "valid": False,
            "message": f"Version {selected_version} not compatible with ~={ref}.",
        }

    return {"valid": True}


def _plan_risk(steps: list[dict]) -> dict:
    """Compute aggregate risk metadata for a plan.

    Returns a summary dict suitable for inclusion in the plan
    response so the frontend can display risk indicators and
    gate confirmations.

    Returns::

        {
            "level": "medium",          # highest step risk
            "counts": {"low": 3, "medium": 2, "high": 0},
            "has_high": False,
        }
    """
    counts: dict[str, int] = {"low": 0, "medium": 0, "high": 0}
    for step in steps:
        risk = step.get("risk", "low")
        counts[risk] = counts.get(risk, 0) + 1

    if counts["high"]:
        level = "high"
    elif counts["medium"]:
        level = "medium"
    else:
        level = "low"

    return {
        "level": level,
        "counts": counts,
        "has_high": counts["high"] > 0,
    }


_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def _check_risk_escalation(
    recipe: dict,
    resolved_risk: dict,
) -> dict | None:
    """Check if user choices escalated the risk beyond recipe default.

    Compares the recipe's base ``risk`` field with the resolved plan's
    aggregate risk.  If the resolved risk is higher, returns escalation
    details for the frontend confirmation gate.

    Args:
        recipe: TOOL_RECIPES entry.
        resolved_risk: Output of ``_plan_risk()``.

    Returns:
        Escalation dict ``{"from": "low", "to": "high", "reason": "..."}``
        or ``None`` if no escalation.
    """
    base_risk = recipe.get("risk", "low")
    resolved_level = resolved_risk.get("level", "low")

    if _RISK_ORDER.get(resolved_level, 0) > _RISK_ORDER.get(base_risk, 0):
        return {
            "from": base_risk,
            "to": resolved_level,
            "reason": (
                f"Your choices escalated the risk from {base_risk} to "
                f"{resolved_level}. Please review the plan carefully."
            ),
        }
    return None
def _backup_before_step(
    step: dict,
    *,
    sudo_password: str = "",
) -> list[str]:
    """Back up paths listed in ``step["backup_before"]``.

    Creates timestamped copies (``PATH.bak.YYYYMMDD_HHMMSS``)
    using ``cp -rp`` (recursive, preserve attributes).  Failures
    are logged but do **not** abort the step—the caller decides
    whether to proceed.

    Returns:
        List of created backup paths (may be empty).
    """
    paths = step.get("backup_before", [])
    if not paths:
        return []

    import time as _bk_time

    ts = _bk_time.strftime("%Y%m%d_%H%M%S")
    backed_up: list[str] = []

    for path_str in paths:
        path = Path(path_str)
        if not path.exists():
            logger.debug("backup_before: path does not exist, skipping: %s", path_str)
            continue
        backup_dest = f"{path_str}.bak.{ts}"
        result = _run_subprocess(
            ["cp", "-rp", path_str, backup_dest],
            needs_sudo=step.get("needs_sudo", False),
            sudo_password=sudo_password,
            timeout=15,
        )
        if result["ok"]:
            backed_up.append(backup_dest)
            logger.info("Backed up %s → %s", path_str, backup_dest)
        else:
            logger.warning(
                "backup_before failed for %s: %s",
                path_str, result.get("error", "unknown"),
            )

    return backed_up


def resolve_install_plan(
    tool: str,
    system_profile: dict,
) -> dict:
    """Produce an ordered install plan for a tool.

    Walks the dependency tree depth-first, batches system packages,
    orders tool installs, applies post-env propagation, filters
    post_install conditions, and adds a verify step.

    Args:
        tool: Tool ID (e.g. ``"cargo-outdated"``).
        system_profile: Phase 1 ``_detect_os()`` output.

    Returns:
        Plan dict with ``steps`` list on success, or ``error`` key
        on failure::

            {
                "tool": "cargo-outdated",
                "label": "cargo-outdated",
                "needs_sudo": True,
                "already_installed": False,
                "steps": [ ... ],
            }
    """
    recipe = TOOL_RECIPES.get(tool)
    if not recipe:
        return {"tool": tool, "error": f"No recipe for '{tool}'."}

    cli = recipe.get("cli", tool)
    if shutil.which(cli):
        return {
            "tool": tool,
            "label": recipe["label"],
            "already_installed": True,
            "steps": [],
        }

    pm = system_profile.get("package_manager", {}).get("primary", "apt")
    snap_ok = system_profile.get("package_manager", {}).get("snap_available", False)

    # Check if a method exists for the target tool itself
    method_for_target = _pick_install_method(recipe, pm, snap_ok)
    if method_for_target is None:
        available = [m for m in recipe.get("install", {}) if not m.startswith("_")]
        return {
            "tool": tool,
            "label": recipe["label"],
            "error": f"No install method available for {recipe['label']} on this system.",
            "available_methods": available,
            "suggestion": (
                f"Install {' or '.join(available)} to enable "
                f"{recipe['label']} installation."
                if available else "No known install method for this platform."
            ),
        }

    # ── Collect deps ──
    batch_packages: list[str] = []
    tool_steps: list[dict] = []
    batched_tools: list[str] = []
    post_env_map: dict[str, str] = {}
    visited: set[str] = set()

    _collect_deps(
        tool, system_profile, visited,
        batch_packages, tool_steps, batched_tools, post_env_map,
    )

    # ── Build plan steps ──
    steps: list[dict] = []

    # 1. Repo setup (if any tool step has repo_setup for this pm)
    for ts in tool_steps:
        for rs in ts["recipe"].get("repo_setup", {}).get(pm, []):
            steps.append({
                "type": "repo_setup",
                "label": rs["label"],
                "tool_id": ts["tool_id"],
                "command": rs["command"],
                "needs_sudo": rs.get("needs_sudo", True),
            })

    # 2. System packages batch (single step)
    if batch_packages:
        cmd = _build_pkg_install_cmd(batch_packages, pm)
        steps.append({
            "type": "packages",
            "label": "Install system packages",
            "command": cmd,
            "needs_sudo": pm != "brew",
            "packages": list(batch_packages),
        })

    # 3. Tool install steps (dependency order)
    accumulated_env = ""
    for ts in tool_steps:
        tool_id = ts["tool_id"]
        recipe_t = ts["recipe"]
        method = ts["method"]
        cmd = list(recipe_t["install"][method])
        sudo = recipe_t["needs_sudo"].get(method, False)

        if accumulated_env:
            cmd = _wrap_with_env(cmd, accumulated_env)

        steps.append({
            "type": "tool",
            "label": f"Install {recipe_t['label']}",
            "tool_id": tool_id,
            "command": cmd,
            "needs_sudo": sudo,
        })

        pe = recipe_t.get("post_env", "")
        if pe:
            accumulated_env = (
                pe if not accumulated_env
                else f"{accumulated_env} && {pe}"
            )

    # 4. Post-install steps (for both tool_steps and batched_tools)
    all_tool_ids = [ts["tool_id"] for ts in tool_steps] + batched_tools
    for tid in all_tool_ids:
        rec = TOOL_RECIPES.get(tid, {})
        for pis in rec.get("post_install", []):
            if not _evaluate_condition(pis.get("condition"), system_profile):
                continue
            steps.append({
                "type": "post_install",
                "label": pis["label"],
                "tool_id": tid,
                "command": pis["command"],
                "needs_sudo": pis.get("needs_sudo", False),
            })

    # 5. Verify step
    verify_cmd = recipe.get("verify")
    if verify_cmd:
        cmd = list(verify_cmd)
        if accumulated_env:
            cmd = _wrap_with_env(cmd, accumulated_env)
        steps.append({
            "type": "verify",
            "label": f"Verify {recipe['label']}",
            "command": cmd,
            "needs_sudo": False,
        })

    # ── Risk tagging ──
    for step in steps:
        step["risk"] = _infer_risk(step)

    # ── Plan-level flags ──
    any_sudo = any(s["needs_sudo"] for s in steps)
    has_sudo = system_profile.get("capabilities", {}).get("has_sudo", True)

    plan: dict[str, Any] = {
        "tool": tool,
        "label": recipe["label"],
        "already_installed": False,
        "needs_sudo": any_sudo,
        "risk_summary": _plan_risk(steps),
        "steps": steps,
    }

    # Check for risk escalation from user choices
    escalation = _check_risk_escalation(recipe, plan["risk_summary"])
    if escalation:
        plan["risk_escalation"] = escalation

    # Confirmation gate — three levels per domain-risk-levels spec
    if plan["risk_summary"]["has_high"]:
        high_steps = []
        for i, s in enumerate(steps):
            if s.get("risk") == "high":
                high_steps.append({
                    "label": s.get("label", f"Step {i+1}"),
                    "risk_description": s.get(
                        "risk_description",
                        "This step modifies system components.",
                    ),
                    "rollback": s.get("rollback", ""),
                    "backup_before": s.get("backup_before", []),
                })
        plan["confirmation_gate"] = {
            "type": "double",
            "required": True,
            "reason": "This plan contains high-risk steps that modify system components.",
            "confirm_text": "I understand",
            "high_risk_steps": high_steps,
        }
    elif plan["risk_summary"]["has_medium"]:
        medium_count = sum(
            1 for s in steps if s.get("risk") == "medium"
        )
        plan["confirmation_gate"] = {
            "type": "single",
            "required": True,
            "reason": (
                f"This plan requires administrator access (sudo) "
                f"for {medium_count} step{'s' if medium_count > 1 else ''}."
            ),
        }
    else:
        plan["confirmation_gate"] = {
            "type": "none",
            "required": False,
        }

    if any_sudo and not has_sudo:
        plan["warning"] = (
            "This plan requires sudo but sudo is not available on this system."
        )

    return plan


# ── Phase 4: Two-pass resolver — choices, inputs, decision trees ───

# Network reachability probe cache (avoids repeated probes per session)
_REACH_CACHE: dict[str, dict] = {}


def _can_reach(endpoint: str, *, timeout: int = 5) -> bool:
    """Probe if a network endpoint is reachable.

    Uses an HTTP HEAD request with a short timeout. Results are
    cached for 60 seconds to avoid hammering the same host.

    Args:
        endpoint: URL or hostname (e.g. ``"https://pypi.org"``
                  or ``"registry.npmjs.org"``).
        timeout: Probe timeout in seconds.

    Returns:
        True if reachable, False if not.
    """
    import urllib.request

    # Normalize to URL
    url = endpoint if endpoint.startswith("http") else f"https://{endpoint}"
    host = url.split("//")[-1].split("/")[0]

    # Check cache
    cached = _REACH_CACHE.get(host)
    if cached and (time.time() - cached["ts"]) < 60:
        return cached["ok"]

    try:
        req = urllib.request.Request(
            url, method="HEAD",
            headers={"User-Agent": "devops-cp/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout):
            pass
        _REACH_CACHE[host] = {"ok": True, "ts": time.time()}
        return True
    except Exception:
        _REACH_CACHE[host] = {"ok": False, "ts": time.time()}
        return False


def _resolve_choice_option(
    option: dict,
    system_profile: dict,
) -> dict:
    """Evaluate a single choice option against the system profile.

    Checks ``requires.network``, ``requires.platforms``,
    ``requires.binaries``, and ``requires.hardware`` constraints.
    Returns the option dict enriched with ``available``,
    ``disabled_reason``, ``enable_hint``, ``failed_constraint``,
    and ``all_failures`` fields.

    Options are NEVER removed — they are returned disabled with reasons.
    All constraint checks run (not short-circuit) to build full
    ``all_failures`` list.
    """
    failures: list[dict] = []

    reqs = option.get("requires", {})

    # ── Network endpoints (reachability probe) ──
    for endpoint in reqs.get("network", []):
        if not _can_reach(endpoint):
            failures.append({
                "constraint": "network",
                "reason": f"Cannot reach {endpoint}",
                "hint": "Check network/proxy settings",
            })

    # ── Platform constraints ──
    platforms = reqs.get("platforms", [])
    if platforms:
        family = system_profile.get("distro_family", "")
        if family not in platforms:
            failures.append({
                "constraint": "platform",
                "reason": f"Not available on {family}",
                "hint": f"Available on: {', '.join(platforms)}",
            })

    # ── Binary requirements ──
    for binary in reqs.get("binaries", []):
        if not shutil.which(binary):
            failures.append({
                "constraint": "binary",
                "reason": f"Requires {binary}",
                "hint": f"Install {binary} first",
            })

    # ── Hardware requirements ──
    hw = reqs.get("hardware", {})
    if isinstance(hw, dict):
        for key, expected in hw.items():
            # Dot-path resolution into system_profile
            parts = key.split(".")
            val = system_profile
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p)
                else:
                    val = None
                    break

            if val is None:
                failures.append({
                    "constraint": "hardware",
                    "reason": f"Hardware not detected: {key}",
                    "hint": f"Requires {key} = {expected}",
                })
            elif isinstance(expected, bool):
                if bool(val) != expected:
                    failures.append({
                        "constraint": "hardware",
                        "reason": f"{key} is {val}, requires {expected}",
                        "hint": f"Requires {key} = {expected}",
                    })
            elif isinstance(expected, str) and expected.startswith(">="):
                try:
                    if float(val) < float(expected[2:]):
                        failures.append({
                            "constraint": "hardware",
                            "reason": f"{key} is {val}, requires {expected}",
                            "hint": f"Upgrade {key} to {expected}",
                        })
                except (ValueError, TypeError):
                    failures.append({
                        "constraint": "hardware",
                        "reason": f"Cannot compare {key}: {val}",
                        "hint": f"Check {key} value",
                    })
    elif isinstance(hw, list):
        for h in hw:
            gpu = system_profile.get("gpu", {})
            found = False
            if "nvidia" in h.lower() and gpu.get("nvidia", {}).get("present"):
                found = True
            elif "amd" in h.lower() and gpu.get("amd", {}).get("present"):
                found = True
            elif "intel" in h.lower() and gpu.get("intel", {}).get("present"):
                found = True
            if not found:
                failures.append({
                    "constraint": "hardware",
                    "reason": f"No {h} detected",
                    "hint": f"Install {h} hardware to enable",
                })

    available = len(failures) == 0

    return {
        **option,
        "available": available if not option.get("_force_available") else True,
        "disabled_reason": failures[0]["reason"] if failures else None,
        "enable_hint": failures[0]["hint"] if failures else None,
        "failed_constraint": failures[0]["constraint"] if failures else None,
        "all_failures": failures if len(failures) > 1 else None,
    }


def _resolve_single_choice(
    choice: dict,
    system_profile: dict,
) -> dict:
    """Resolve a single choice — evaluate all options for availability.

    Returns the choice dict with resolved ``options`` list where each
    option has ``available``, ``disabled_reason``, and ``enable_hint``.
    Also determines the default value.
    """
    resolved_options = []
    default_value = None

    for opt in choice.get("options", []):
        resolved = _resolve_choice_option(opt, system_profile)
        resolved_options.append(resolved)

        # Track default
        if opt.get("default") and resolved["available"]:
            default_value = opt["id"] if "id" in opt else opt.get("value")

    # If no explicit default, pick first available
    if default_value is None:
        for opt in resolved_options:
            if opt["available"]:
                default_value = opt.get("id", opt.get("value"))
                break

    # Auto-select: if exactly one option is available, auto-select it
    available_opts = [o for o in resolved_options if o["available"]]
    auto_selected = len(available_opts) == 1

    return {
        **choice,
        "options": resolved_options,
        "default": default_value,
        "auto_selected": auto_selected,
    }


def _input_condition_met(
    inp: dict,
    answers: dict,
    system_profile: dict,
) -> bool:
    """Check if an input field should be shown based on its condition.

    Conditions can reference:
      - Other choice answers: ``{"choice": "method", "equals": "source"}``
      - System profile values: ``{"profile": "has_systemd", "equals": True}``
      - Logical operators (future): ``{"and": [...]}``

    Returns True if the input should be shown.
    """
    cond = inp.get("condition")
    if not cond:
        return True

    if isinstance(cond, str):
        # Simple profile flag: "has_systemd"
        return bool(system_profile.get("capabilities", {}).get(cond))

    if isinstance(cond, dict):
        # Choice-dependent: {"choice": "method", "equals": "source"}
        if "choice" in cond:
            choice_id = cond["choice"]
            expected = cond.get("equals")
            actual = answers.get(choice_id)
            if expected is not None:
                return actual == expected
            # "not_equals"
            not_expected = cond.get("not_equals")
            if not_expected is not None:
                return actual != not_expected
            return actual is not None

        # Profile-dependent: {"profile": "has_systemd", "equals": True}
        if "profile" in cond:
            key = cond["profile"]
            expected = cond.get("equals")
            parts = key.split(".")
            val = system_profile
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p)
                else:
                    val = None
                    break
            if expected is not None:
                return val == expected
            return bool(val)

    return True


def resolve_choices(
    tool: str,
    system_profile: dict,
) -> dict:
    """Pass 1 — Extract choices the user must make before installation.

    Reads the recipe's ``choices`` and ``inputs`` fields, evaluates
    constraints against the system profile, and returns a decision tree
    for the frontend to render.

    If the recipe has NO choices → returns ``auto_resolve: True`` so the
    frontend can skip the choice modal and go straight to the plan.

    Args:
        tool: Tool ID.
        system_profile: Phase 1 ``_detect_os()`` output.

    Returns::

        {
            "tool": "docker",
            "label": "Docker",
            "choices": [...],
            "inputs": [...],
            "defaults": {...},
            "auto_resolve": False,
        }
    """
    recipe = TOOL_RECIPES.get(tool)
    if not recipe:
        return {"tool": tool, "error": f"No recipe for '{tool}'."}

    # Check if already installed
    cli = recipe.get("cli", tool)
    if shutil.which(cli):
        return {
            "tool": tool,
            "label": recipe["label"],
            "already_installed": True,
            "auto_resolve": True,
            "choices": [],
            "inputs": [],
            "defaults": {},
        }

    raw_choices = recipe.get("choices", [])
    raw_inputs = recipe.get("inputs", [])

    # No choices → auto-resolve
    if not raw_choices and not raw_inputs:
        return {
            "tool": tool,
            "label": recipe["label"],
            "auto_resolve": True,
            "choices": [],
            "inputs": [],
            "defaults": {},
        }

    # Resolve each choice
    resolved_choices = []
    defaults: dict[str, Any] = {}

    # ── Version choice (if present) ──
    version_choice = recipe.get("version_choice")
    if version_choice:
        source = version_choice.get("source", "static")
        if source == "static":
            # Static version list — convert to standard choice format
            vc_options = version_choice.get("options", [])
            vc_as_choice = {
                "id": "version",
                "label": version_choice.get("label", "Version"),
                "type": "single",
                "options": [
                    {
                        "id": opt["id"],
                        "label": opt.get("label", opt["id"]),
                        "default": opt.get("default", False),
                        "warning": opt.get("warning"),
                        "requires": opt.get("requires", {}),
                    }
                    for opt in vc_options
                ],
            }
            resolved = _resolve_single_choice(vc_as_choice, system_profile)
            resolved_choices.append(resolved)
            if resolved.get("default") is not None:
                defaults["version"] = resolved["default"]
        elif source == "package_manager":
            # Let the PM decide — no user choice needed
            defaults["version"] = "latest"
        elif source == "dynamic":
            # Dynamic version fetch from GitHub releases API
            repo = version_choice.get("github_repo", "")
            cache_ttl = version_choice.get("cache_ttl", 3600)
            max_versions = version_choice.get("max_versions", 10)
            asset_pattern = version_choice.get("asset_pattern", "")

            dynamic_options: list[dict] = []
            fetch_error: str | None = None

            if repo:
                # Check cache first
                cache_key = f"version_fetch:{repo}"
                cached = _VERSION_FETCH_CACHE.get(cache_key)
                if cached and (time.time() - cached["ts"]) < cache_ttl:
                    dynamic_options = cached["options"]
                else:
                    # Fetch from GitHub API
                    try:
                        import urllib.request
                        import json as _json

                        api_url = f"https://api.github.com/repos/{repo}/releases"
                        req = urllib.request.Request(
                            api_url,
                            headers={
                                "Accept": "application/vnd.github.v3+json",
                                "User-Agent": "devops-cp/1.0",
                            },
                        )
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            releases = _json.loads(resp.read())

                        for rel in releases[:max_versions]:
                            tag = rel.get("tag_name", "")
                            if not tag:
                                continue
                            ver = tag.lstrip("v")
                            dynamic_options.append({
                                "id": ver,
                                "label": f"{ver}" + (" (latest)" if rel == releases[0] else ""),
                                "default": rel == releases[0],
                                "prerelease": rel.get("prerelease", False),
                            })

                        # Cache the results
                        _VERSION_FETCH_CACHE[cache_key] = {
                            "ts": time.time(),
                            "options": dynamic_options,
                        }
                    except Exception as exc:
                        fetch_error = str(exc)[:100]
                        logger.warning(
                            "Dynamic version fetch failed for %s: %s",
                            repo, fetch_error,
                        )

            if dynamic_options:
                # Build a real choice from fetched versions
                vc_options_resolved = []
                for opt in dynamic_options:
                    resolved_opt = _resolve_choice_option(opt, system_profile)
                    # Pre-release versions get a warning
                    if opt.get("prerelease"):
                        resolved_opt["warning"] = "Pre-release version"
                    vc_options_resolved.append(resolved_opt)

                vc_resolved = {
                    "id": "version",
                    "label": version_choice.get("label", "Version"),
                    "type": "single",
                    "options": vc_options_resolved,
                    "default": dynamic_options[0]["id"],
                    "source": "dynamic",
                    "github_repo": repo,
                    "cache_ttl": cache_ttl,
                }
                resolved_choices.append(vc_resolved)
                defaults["version"] = dynamic_options[0]["id"]
            else:
                # Fallback: single "latest" option
                resolved_choices.append({
                    "id": "version",
                    "label": version_choice.get("label", "Version"),
                    "type": "single",
                    "options": [{
                        "id": "latest",
                        "label": "Latest",
                        "available": True,
                        "default": True,
                        "disabled_reason": None,
                        "enable_hint": None,
                    }],
                    "default": "latest",
                    "auto_selected": True,
                    "source": "dynamic",
                    "fetch_error": fetch_error,
                })
                defaults["version"] = "latest"

    for choice in raw_choices:
        resolved = _resolve_single_choice(choice, system_profile)
        resolved_choices.append(resolved)
        if resolved.get("default") is not None:
            defaults[choice["id"]] = resolved["default"]

    # Filter inputs by conditions (using defaults as initial answers)
    visible_inputs = []
    for inp in raw_inputs:
        if _input_condition_met(inp, defaults, system_profile):
            visible_inputs.append(inp)
            if "default" in inp:
                defaults[inp["id"]] = inp["default"]

    # Check if ALL choices are forced (only one available option each)
    all_forced = True
    for choice in resolved_choices:
        available_opts = [o for o in choice["options"] if o["available"]]
        if len(available_opts) != 1:
            all_forced = False
            break

    return {
        "tool": tool,
        "label": recipe["label"],
        "auto_resolve": all_forced and not visible_inputs,
        "choices": resolved_choices,
        "inputs": visible_inputs,
        "defaults": defaults,
    }


def _apply_choices(
    recipe: dict,
    answers: dict,
) -> dict:
    """Apply user's choice answers to produce a flattened recipe.

    For each choice in the recipe, the user's answer selects a branch.
    Fields that are keyed by choice ID are resolved to the selected value.

    Handles:
      - ``install_variants`` → selects the right install commands
      - ``needs_sudo`` dict-of-variants → selects the right sudo flag
      - ``verify`` dict-of-variants → selects the right verify command
      - ``post_install`` dict-of-variants → selects the right post-install
      - ``data_packs`` filtered by selection

    Returns a new recipe dict with choices resolved.
    """
    resolved = dict(recipe)

    # If recipe has install_variants keyed by choice answers
    install_variants = recipe.get("install_variants", {})
    if install_variants:
        # Find which choice answer picks the variant
        for choice in recipe.get("choices", []):
            cid = choice["id"]
            answer = answers.get(cid)
            if answer and answer in install_variants:
                variant = install_variants[answer]

                # Variant can be a dict with "command" or "steps"
                if "steps" in variant:
                    # Multi-step variant — convert to install format
                    resolved["_resolved_steps"] = variant["steps"]
                elif "command" in variant:
                    resolved["install"] = {"_default": variant["command"]}
                    if "needs_sudo" in variant:
                        resolved["needs_sudo"] = {
                            "_default": variant["needs_sudo"]
                        }

                # Resolve post_install for this variant
                post_install = recipe.get("post_install", {})
                if isinstance(post_install, dict) and answer in post_install:
                    resolved["post_install"] = post_install[answer]

                # Resolve verify for this variant
                verify = recipe.get("verify", {})
                if isinstance(verify, dict) and answer in verify:
                    resolved["verify"] = verify[answer]

                break

    return resolved


def _apply_inputs(
    recipe: dict,
    answers: dict,
) -> dict:
    """Substitute user input values into recipe commands.

    Template variables use ``{input_id}`` syntax in commands, configs,
    and paths. Also provides built-in variables:
      - ``{user}`` — current username
      - ``{home}`` — home directory
      - ``{arch}`` — CPU architecture (amd64/arm64)
      - ``{nproc}`` — number of CPU cores

    Returns a new recipe dict with templates substituted.
    """
    import os
    import multiprocessing

    # Build substitution map: user answers + built-in variables
    subs: dict[str, str] = {
        "user": os.environ.get("USER", "unknown"),
        "home": os.path.expanduser("~"),
        "arch": os.uname().machine,
        "nproc": str(multiprocessing.cpu_count()),
    }
    subs.update({k: str(v) for k, v in answers.items()})

    def _sub_str(s: str) -> str:
        """Substitute {var} placeholders in a string."""
        for key, val in subs.items():
            s = s.replace("{" + key + "}", val)
        return s

    def _sub_list(lst: list) -> list:
        """Recursively substitute in a list (command args)."""
        result = []
        for item in lst:
            if isinstance(item, str):
                result.append(_sub_str(item))
            elif isinstance(item, list):
                result.append(_sub_list(item))
            elif isinstance(item, dict):
                result.append(_sub_dict(item))
            else:
                result.append(item)
        return result

    def _sub_dict(d: dict) -> dict:
        """Recursively substitute in a dict."""
        result = {}
        for k, v in d.items():
            if isinstance(v, str):
                result[k] = _sub_str(v)
            elif isinstance(v, list):
                result[k] = _sub_list(v)
            elif isinstance(v, dict):
                result[k] = _sub_dict(v)
            else:
                result[k] = v
        return result

    return _sub_dict(recipe)


def resolve_install_plan_with_choices(
    tool: str,
    system_profile: dict,
    answers: dict,
) -> dict:
    """Pass 2 — Resolve an install plan using the user's choice answers.

    Takes the user's answers from the choice modal, applies them to
    the recipe (selecting branches, substituting inputs), then resolves
    the plan using the standard single-pass resolver.

    Args:
        tool: Tool ID.
        system_profile: Phase 1 ``_detect_os()`` output.
        answers: ``{"choice_id": "selected_value", "input_id": "val"}``.

    Returns:
        Install plan (same format as ``resolve_install_plan()``).
    """
    recipe = TOOL_RECIPES.get(tool)
    if not recipe:
        return {"tool": tool, "error": f"No recipe for '{tool}'."}

    # Check if already installed
    cli = recipe.get("cli", tool)
    if shutil.which(cli):
        return {
            "tool": tool,
            "label": recipe["label"],
            "already_installed": True,
            "steps": [],
        }

    # Apply choices → flatten recipe branches
    resolved_recipe = _apply_choices(recipe, answers)

    # Apply inputs → template substitution
    resolved_recipe = _apply_inputs(resolved_recipe, answers)

    # If choices produced _resolved_steps (multi-step variant like
    # build-from-source), construct the plan directly
    if "_resolved_steps" in resolved_recipe:
        steps = []
        for raw_step in resolved_recipe["_resolved_steps"]:
            step = dict(raw_step)
            step.setdefault("type", "tool")
            step.setdefault("needs_sudo", False)
            steps.append(step)

        # Add verify step if present
        verify_cmd = resolved_recipe.get("verify")
        if verify_cmd:
            if isinstance(verify_cmd, list):
                steps.append({
                    "type": "verify",
                    "label": f"Verify {recipe['label']}",
                    "command": verify_cmd,
                    "needs_sudo": False,
                })

        any_sudo = any(s.get("needs_sudo", False) for s in steps)
        has_sudo = system_profile.get(
            "capabilities", {}
        ).get("has_sudo", True)

        plan: dict[str, Any] = {
            "tool": tool,
            "label": recipe["label"],
            "already_installed": False,
            "needs_sudo": any_sudo,
            "steps": steps,
        }
        if any_sudo and not has_sudo:
            plan["warning"] = (
                "This plan requires sudo but sudo is not available."
            )
        return plan

    # Otherwise, the choices flattened the recipe to a simple form.
    # Temporarily patch TOOL_RECIPES for the single-pass resolver,
    # then restore.
    original = TOOL_RECIPES.get(tool)
    try:
        TOOL_RECIPES[tool] = resolved_recipe
        return resolve_install_plan(tool, system_profile)
    finally:
        if original is not None:
            TOOL_RECIPES[tool] = original
        else:
            TOOL_RECIPES.pop(tool, None)


# ── Error analysis — parse failures into actionable remediation ─────

import re


def _get_system_deps(tool: str) -> list[str]:
    """Get system package deps for a tool, using detected distro family.

    Looks up requires.packages from TOOL_RECIPES keyed by distro family.
    Falls back to debian names if family not found.
    Returns empty list if tool has no package requirements.
    """
    recipe = TOOL_RECIPES.get(tool, {})
    pkg_map = recipe.get("requires", {}).get("packages", {})
    if not pkg_map:
        return []
    from src.core.services.audit.l0_detection import _detect_os
    family = _detect_os().get("distro", {}).get("family", "debian")
    return pkg_map.get(family, pkg_map.get("debian", []))

def _analyse_install_failure(
    tool: str, cli: str, stderr: str,
) -> dict[str, Any] | None:
    """Parse stderr from a failed install and return structured remediation.

    Returns None if no known pattern matched.
    Returns a dict with:
      - reason: human-readable explanation
      - options: list of actionable remediation paths
    """
    if not stderr:
        return None

    # ── Rust version mismatch ──
    # Pattern: "it requires rustc X.Y or newer, while the currently active
    #           rustc version is Z.W"
    # Hint:    "package_name X.Y.Z supports rustc A.B.C"
    rustc_req = re.search(
        r"requires rustc (\d+\.\d+(?:\.\d+)?)\s+or newer.*?"
        r"currently active rustc version is (\d+\.\d+(?:\.\d+)?)",
        stderr,
        re.DOTALL,
    )
    if rustc_req:
        required = rustc_req.group(1)
        current = rustc_req.group(2)

        # Try to extract the compatible fallback version
        compat = re.search(
            rf"`?{re.escape(tool)}\s+(\d+\.\d+\.\d+)`?\s+supports\s+rustc",
            stderr,
        )
        compat_ver = compat.group(1) if compat else None

        options: list[dict[str, Any]] = []

        # Option 1: Install compatible version
        if compat_ver:
            options.append({
                "id": "compatible-version",
                "label": "Compatible Version",
                "icon": "📦",
                "description": (
                    f"Install {tool}@{compat_ver} "
                    f"(works with your rustc {current})"
                ),
                "command": ["cargo", "install", f"{tool}@{compat_ver}"],
                "needs_sudo": False,
                "system_deps": _get_system_deps(tool),
            })

        # Option 2: Upgrade Rust via rustup
        options.append({
            "id": "upgrade-dep",
            "label": "Upgrade Rust",
            "icon": "⬆️",
            "description": (
                f"Install rustup + Rust {required}+, "
                f"then install latest {tool}"
            ),
            "system_deps": _get_system_deps(tool),
            "steps": [
                {
                    "label": "Install rustup + latest Rust",
                    "command": [
                        "bash", "-c",
                        "curl --proto '=https' --tlsv1.2 -sSf "
                        "https://sh.rustup.rs | sh -s -- -y",
                    ],
                    "needs_sudo": False,
                },
                {
                    "label": f"Install {tool}",
                    "command": [
                        "bash", "-c",
                        f'export PATH="$HOME/.cargo/bin:$PATH" && cargo install {tool}',
                    ],
                    "needs_sudo": False,
                },
            ],
        })

        # Option 3: Build from source
        # Cargo can build older commits that support the system rustc
        options.append({
            "id": "build-source",
            "label": "Build from Source",
            "icon": "🔧",
            "description": (
                f"Build {tool} from source using system rustc {current}"
            ),
            "command": [
                "bash", "-c",
                f"cargo install {tool} --locked 2>/dev/null "
                f"|| cargo install {tool}@{compat_ver}" if compat_ver
                else f"cargo install {tool} --locked",
            ],
            "needs_sudo": False,
            "system_deps": _get_system_deps(tool),
        })

        return {
            "type": "version_mismatch",
            "reason": (
                f"{tool} requires rustc {required}+ "
                f"(you have {current})"
            ),
            "options": options,
        }

    # ── npm / node not found ──
    if "npm: command not found" in stderr or "npm: not found" in stderr:
        return {
            "type": "missing_runtime",
            "reason": "npm is not installed",
            "options": [
                {
                    "id": "install-npm",
                    "label": "Install npm",
                    "icon": "📦",
                    "description": "Install npm via system packages",
                    "tool": "npm",
                    "needs_sudo": True,
                },
            ],
        }

    # ── pip not found ──
    if "No module named pip" in stderr or "pip: command not found" in stderr:
        return {
            "type": "missing_runtime",
            "reason": "pip is not installed",
            "options": [
                {
                    "id": "install-pip",
                    "label": "Install pip",
                    "icon": "📦",
                    "description": "Install pip via system packages",
                    "tool": "pip",
                    "needs_sudo": True,
                },
            ],
        }

    # ── Permission denied (npm global) ──
    if "EACCES" in stderr and "permission denied" in stderr.lower():
        return {
            "type": "permissions",
            "reason": "Permission denied — try with sudo",
            "options": [
                {
                    "id": "retry-sudo",
                    "label": "Retry with sudo",
                    "icon": "🔒",
                    "description": "Re-run the install with sudo privileges",
                    "retry_sudo": True,
                },
            ],
        }

    return None


# ── Version detection ───────────────────────────────────────────
#
# Maps tool IDs to (command, regex) for extracting version strings.
# The regex MUST have exactly ONE capture group returning the semver.

VERSION_COMMANDS: dict[str, tuple[list[str], str]] = {
    # pip tools
    "ruff":         (["ruff", "--version"],           r"ruff\s+(\d+\.\d+\.\d+)"),
    "black":        (["black", "--version"],           r"black.*?(\d+\.\d+\.\d+)"),
    "mypy":         (["mypy", "--version"],            r"mypy\s+(\d+\.\d+(?:\.\d+)?)"),
    "pytest":       (["pytest", "--version"],          r"pytest\s+(\d+\.\d+\.\d+)"),
    "pip-audit":    (["pip-audit", "--version"],       r"pip-audit\s+(\d+\.\d+\.\d+)"),
    "safety":       (["safety", "--version"],          r"(\d+\.\d+\.\d+)"),
    "bandit":       (["bandit", "--version"],          r"bandit\s+(\d+\.\d+\.\d+)"),
    # npm tools
    "eslint":       (["eslint", "--version"],          r"v?(\d+\.\d+\.\d+)"),
    "prettier":     (["prettier", "--version"],        r"(\d+\.\d+\.\d+)"),
    # cargo tools
    "cargo-audit":  (["cargo", "audit", "--version"],  r"cargo-audit\s+(\d+\.\d+\.\d+)"),
    "cargo-outdated": (["cargo", "outdated", "--version"], r"cargo-outdated\s+v?(\d+\.\d+\.\d+)"),
    # devops / infra
    "docker":       (["docker", "--version"],          r"Docker version\s+(\d+\.\d+\.\d+)"),
    "kubectl":      (["kubectl", "version", "--client=true"],
                                                       r"v(\d+\.\d+\.\d+)"),
    "helm":         (["helm", "version", "--short"],   r"v(\d+\.\d+\.\d+)"),
    "terraform":    (["terraform", "version"],         r"Terraform\s+v(\d+\.\d+\.\d+)"),
    "git":          (["git", "--version"],              r"git version\s+(\d+\.\d+\.\d+)"),
    "go":           (["go", "version"],                 r"go(\d+\.\d+\.\d+)"),
    "node":         (["node", "--version"],              r"v(\d+\.\d+\.\d+)"),
    "cargo":        (["cargo", "--version"],             r"cargo\s+(\d+\.\d+\.\d+)"),
    "rustc":        (["rustc", "--version"],             r"rustc\s+(\d+\.\d+\.\d+)"),
    "gh":           (["gh", "--version"],                r"gh version\s+(\d+\.\d+\.\d+)"),
    "trivy":        (["trivy", "version"],               r"Version:\s+(\d+\.\d+\.\d+)"),
    "hugo":         (["hugo", "version"],                r"v(\d+\.\d+\.\d+)"),
    "k9s":          (["k9s", "version", "--short"],     r"v(\d+\.\d+\.\d+)"),
    "argocd":       (["argocd", "version", "--client"], r"v(\d+\.\d+\.\d+)"),
    "ansible":      (["ansible", "--version"],          r"ansible.*?(\d+\.\d+\.\d+)"),
    "minikube":     (["minikube", "version", "--short"], r"v(\d+\.\d+\.\d+)"),
    "k3s":          (["k3s", "--version"],               r"v(\d+\.\d+\.\d+)"),
    "skaffold":     (["skaffold", "version"],            r"v(\d+\.\d+\.\d+)"),
    "kustomize":    (["kustomize", "version"],           r"v(\d+\.\d+\.\d+)"),
    "lazydocker":   (["lazydocker", "--version"],        r"Version:\s*(\d+\.\d+\.\d+)"),
    "containerd":   (["containerd", "--version"],        r"containerd\s+v?(\d+\.\d+\.\d+)"),
    "cri-o":        (["crio", "--version"],              r"Version:\s+(\d+\.\d+\.\d+)"),
    "podman":       (["podman", "--version"],            r"podman version\s+(\d+\.\d+\.\d+)"),
    "nerdctl":      (["nerdctl", "--version"],           r"nerdctl version\s+(\d+\.\d+\.\d+)"),
    "act":          (["act", "--version"],               r"version\s+(\d+\.\d+\.\d+)"),
    "pip":          (_PIP + ["--version"],               r"pip\s+(\d+\.\d+\.\d+)"),
    "npm":          (["npm", "--version"],               r"(\d+\.\d+\.\d+)"),
}


def get_tool_version(tool: str) -> str | None:
    """Get the installed version of a tool.

    Uses ``VERSION_COMMANDS`` to look up the command and regex pattern.
    Falls back to recipe's ``version_command`` / ``version_pattern``
    fields if the tool isn't in ``VERSION_COMMANDS``.

    Returns:
        Semver string (e.g. ``"0.5.1"``) or ``None`` if the tool
        is not installed or version can't be determined.
    """
    # Look up from the static table first
    entry = VERSION_COMMANDS.get(tool)

    # Fall back to recipe override
    if not entry:
        recipe = TOOL_RECIPES.get(tool, {})
        vcmd = recipe.get("version_command")
        vpat = recipe.get("version_pattern")
        if vcmd and vpat:
            entry = (vcmd, vpat)
        else:
            return None

    cmd, pattern = entry
    cli = cmd[0]
    if not shutil.which(cli):
        return None

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )
        # Some tools write version to stderr (e.g. mypy in some versions)
        output = (result.stdout or "") + (result.stderr or "")
        match = re.search(pattern, output)
        if match:
            return match.group(1)
    except (subprocess.TimeoutExpired, Exception):
        pass

    return None


def _pick_method_command(
    method_map: dict,
    system_profile: dict | None = None,
) -> tuple[list[str], str] | None:
    """Resolve a method-keyed command map to (command, method).

    Uses the same method-selection logic as install:
    primary PM → snap → _default → first available.

    Args:
        method_map: E.g. ``{"_default": ["pip", ...], "apt": ["apt-get", ...]}``.
        system_profile: From ``_detect_os()``.  If ``None``, auto-detects.

    Returns:
        ``(command_list, method_key)`` or ``None`` if no method matches.
    """
    if not method_map:
        return None

    if system_profile is None:
        from src.core.services.audit.l0_detection import _detect_os
        system_profile = _detect_os()

    primary_pm = system_profile.get("package_manager", {}).get("primary", "apt")
    snap_available = system_profile.get("package_manager", {}).get("snap_available", False)

    for candidate in (primary_pm, "snap", "_default"):
        if candidate == "snap" and not snap_available:
            continue
        if candidate in method_map:
            return method_map[candidate], candidate

    # Any available key
    for key, cmd in method_map.items():
        if key.startswith("_"):
            continue
        return cmd, key

    return None


def update_tool(
    tool: str,
    *,
    sudo_password: str = "",
) -> dict[str, Any]:
    """Update an installed tool to the latest version.

    Uses the recipe's ``update`` command map, resolved for the current
    system.  Records version before and after.

    Args:
        tool: Tool ID.
        sudo_password: Sudo password if the update needs root.

    Returns:
        ``{"ok": True, "from_version": "...", "to_version": "..."}``
        on success, or error dict.
    """
    recipe = TOOL_RECIPES.get(tool)
    if not recipe:
        return {"ok": False, "error": f"No recipe for '{tool}'"}

    cli = recipe.get("cli", tool)
    if not shutil.which(cli):
        return {
            "ok": False,
            "error": f"{tool} is not installed. Install it first.",
        }

    update_map = recipe.get("update")
    if not update_map:
        return {"ok": False, "error": f"No update command defined for {tool}"}

    # Resolve command for this system
    resolved = _pick_method_command(update_map)
    if not resolved:
        return {"ok": False, "error": f"No update method available for {tool}"}

    cmd, method = resolved
    needs_sudo = recipe.get("needs_sudo", {}).get(method, False)

    # Record version before update
    version_before = get_tool_version(tool)

    _audit(
        "⬆️ Tool Update",
        f"{tool}: updating via {method}",
        action="started",
        target=tool,
    )

    result = _run_subprocess(
        cmd,
        needs_sudo=needs_sudo,
        sudo_password=sudo_password,
        timeout=300,  # cargo recompiles can be slow
    )

    if not result["ok"]:
        _audit(
            "❌ Tool Update Failed",
            f"{tool}: {result['error']}",
            action="failed",
            target=tool,
        )
        return result

    # Record version after update
    version_after = get_tool_version(tool)

    if version_before and version_after and version_before == version_after:
        msg = f"{tool} is already at the latest version ({version_after})"
        _audit(
            "✅ Tool Already Latest",
            msg,
            action="completed",
            target=tool,
        )
        return {"ok": True, "message": msg, "already_latest": True}

    change = (
        f"{version_before} → {version_after}"
        if version_before and version_after
        else f"updated to {version_after}" if version_after
        else "updated"
    )
    msg = f"{tool} updated: {change}"

    _audit(
        "⬆️ Tool Updated",
        msg,
        action="updated",
        target=tool,
    )

    return {
        "ok": True,
        "message": msg,
        "from_version": version_before,
        "to_version": version_after,
        "invalidates": ["l0_detection", "tool_status"],
    }


def remove_tool(
    tool: str,
    *,
    sudo_password: str = "",
) -> dict[str, Any]:
    """Remove (uninstall) a tool using the appropriate method.

    Resolution order for the remove command:
      1. Recipe's explicit ``remove`` command map (if defined)
      2. ``UNDO_COMMANDS`` catalog based on the install method

    Args:
        tool: Tool ID from TOOL_RECIPES.
        sudo_password: Sudo password if removal needs root.

    Returns:
        ``{"ok": True, "message": "..."}`` on success, or error dict.
    """
    recipe = TOOL_RECIPES.get(tool)
    if not recipe:
        return {"ok": False, "error": f"No recipe for '{tool}'"}

    cli = recipe.get("cli", tool)
    if not shutil.which(cli):
        return {
            "ok": False,
            "error": f"{tool} is not installed.",
        }

    # 1. Try explicit remove command in recipe
    remove_map = recipe.get("remove")
    if remove_map:
        resolved = _pick_method_command(remove_map)
        if resolved:
            cmd, method = resolved
            needs_sudo = recipe.get("needs_sudo", {}).get(method, True)
            _audit(
                "🗑️ Tool Remove",
                f"{tool}: removing via {method}",
                action="started",
                target=tool,
            )
            result = _run_subprocess(
                cmd,
                needs_sudo=needs_sudo,
                sudo_password=sudo_password,
                timeout=120,
            )
            if result["ok"]:
                result["message"] = f"{tool} removed"
                result["invalidates"] = ["l0_detection", "tool_status"]
                _audit(
                    "✅ Tool Removed",
                    f"{tool} removed via {method}",
                    action="completed",
                    target=tool,
                )
            else:
                _audit(
                    "❌ Tool Remove Failed",
                    f"{tool}: {result.get('error', '')}",
                    action="failed",
                    target=tool,
                )
            return result

    # 2. Derive remove command from install method + UNDO_COMMANDS
    install_map = recipe.get("install", {})
    resolved = _pick_method_command(install_map)
    if not resolved:
        return {"ok": False, "error": f"Cannot determine install method for {tool}"}

    _cmd, method = resolved
    # Map method to UNDO_COMMANDS key
    undo_key = method
    if method == "_default":
        # For _default (curl|bash scripts, binary downloads), removal
        # is by deleting the binary from PATH
        binary_path = shutil.which(cli)
        if binary_path:
            undo = UNDO_COMMANDS.get("binary", {})
            cmd = [t.replace("{install_path}", binary_path)
                   for t in undo.get("command", ["rm", binary_path])]
            needs_sudo = undo.get("needs_sudo", True)
        else:
            return {"ok": False, "error": f"Cannot find {cli} binary for removal"}
    elif undo_key in UNDO_COMMANDS:
        undo = UNDO_COMMANDS[undo_key]
        # Substitute {package} with the package name(s)
        # For apt/dnf/pacman: the package name is typically the tool name
        packages = recipe.get("packages", [tool])
        if isinstance(packages, dict):
            packages = packages.get(method, [tool])
        pkg_str = " ".join(packages) if isinstance(packages, list) else str(packages)
        cmd = [t.replace("{package}", pkg_str) for t in undo["command"]]
        needs_sudo = undo.get("needs_sudo", True)
    else:
        return {"ok": False, "error": f"No removal method known for {tool} (method: {method})"}

    _audit(
        "🗑️ Tool Remove",
        f"{tool}: removing via {undo_key}",
        action="started",
        target=tool,
    )

    result = _run_subprocess(
        cmd,
        needs_sudo=needs_sudo,
        sudo_password=sudo_password,
        timeout=120,
    )
    if result["ok"]:
        result["message"] = f"{tool} removed"
        result["invalidates"] = ["l0_detection", "tool_status"]
        _audit(
            "✅ Tool Removed",
            f"{tool} removed via {undo_key}",
            action="completed",
            target=tool,
        )
    else:
        _audit(
            "❌ Tool Remove Failed",
            f"{tool}: {result.get('error', '')}",
            action="failed",
            target=tool,
        )
    return result


def check_updates(
    tools: list[str] | None = None,
) -> list[dict]:
    """Check installed tools for their current version.

    Returns a list of status dicts per installed tool.

    Note: Latest-version fetching (comparing with PyPI, apt-cache, etc.)
    is deferred to a later phase — requires network calls and separate
    caching strategy.  This function returns what the system CAN detect
    locally and cheaply.

    Args:
        tools: Specific tools to check.  Defaults to all TOOL_RECIPES.

    Returns:
        List of ``{"tool": "...", "installed": True, "version": "..."}``
        dicts for installed tools.
    """
    if tools is None:
        tools = list(TOOL_RECIPES.keys())

    results = []
    for tool_id in tools:
        recipe = TOOL_RECIPES.get(tool_id, {})
        cli = recipe.get("cli", tool_id)
        installed = shutil.which(cli) is not None

        if not installed:
            continue

        version = get_tool_version(tool_id)
        has_update_cmd = bool(recipe.get("update"))

        results.append({
            "tool": tool_id,
            "installed": True,
            "version": version,
            "has_update": has_update_cmd,
        })

    return results



import os
import time


def _run_subprocess(
    cmd: list[str],
    *,
    needs_sudo: bool = False,
    sudo_password: str = "",
    timeout: int = 120,
    env_overrides: dict[str, str] | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Run a subprocess command with sudo and env support.

    This is the SINGLE PLACE where subprocess.run is called for
    install operations.  All security, logging, and error handling
    is centralised here.

    Security invariants (from domain-sudo-security):
    - Password piped via stdin only (``sudo -S``)
    - ``-k`` invalidates cached credentials every time
    - Password never logged, never written to disk
    - Password never appears in command args

    Args:
        cmd: Command list for ``subprocess.run()``.
        needs_sudo: Whether the command requires root.
        sudo_password: Sudo password (piped to stdin).
        timeout: Seconds before ``TimeoutExpired``.
        env_overrides: Extra env vars (e.g. PATH from ``post_env``).

        cwd: Working directory for the command (Phase 5 builds).

    Returns:
        ``{"ok": True, "stdout": "...", "elapsed_ms": N}`` on success,
        ``{"ok": False, "error": "...", ...}`` on failure.
    """
    # ── Sudo handling ──
    if needs_sudo:
        if os.geteuid() == 0:
            # Already root — no sudo prefix needed
            pass
        elif not sudo_password:
            return {
                "ok": False,
                "needs_sudo": True,
                "error": "This step requires sudo. Please enter your password.",
            }
        else:
            cmd = ["sudo", "-S", "-k"] + cmd

    # ── Environment ──
    env = os.environ.copy()
    if env_overrides:
        for key, value in env_overrides.items():
            env[key] = os.path.expandvars(value)

    # ── Execute ──
    start = time.monotonic()
    try:
        stdin_data = (
            (sudo_password + "\n")
            if (needs_sudo and sudo_password and os.geteuid() != 0)
            else None
        )
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=stdin_data,
            env=env,
            cwd=cwd,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if result.returncode == 0:
            return {
                "ok": True,
                "stdout": result.stdout[-2000:] if result.stdout else "",
                "elapsed_ms": elapsed_ms,
            }

        stderr = result.stderr[-2000:] if result.stderr else ""

        # Wrong password?
        if needs_sudo and (
            "incorrect password" in stderr.lower()
            or "sorry" in stderr.lower()
        ):
            return {
                "ok": False,
                "needs_sudo": True,
                "error": "Wrong password. Try again.",
            }

        return {
            "ok": False,
            "error": f"Command failed (exit {result.returncode})",
            "stderr": stderr,
            "stdout": result.stdout[-2000:] if result.stdout else "",
            "elapsed_ms": elapsed_ms,
        }

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Command timed out ({timeout}s)"}
    except Exception as e:
        logger.exception("Subprocess error: %s", cmd)
        return {"ok": False, "error": str(e)}


# ── Step executors ──────────────────────────────────────────────


def _execute_package_step(
    step: dict, *, sudo_password: str = "",
) -> dict[str, Any]:
    """Install system packages, skipping already-installed ones.

    Uses ``check_system_deps()`` (Phase 2.1) to determine which
    packages are missing, then rebuilds the install command with
    only the missing packages via ``_build_pkg_install_cmd()``.
    """
    packages = step.get("packages", [])
    if not packages:
        return {"ok": True, "message": "No packages to install", "skipped": True}

    # Determine package manager from command (first token)
    pm = step.get("package_manager")
    if not pm:
        # Infer from the command: "apt-get" → "apt", "dnf" → "dnf"
        cmd_bin = step["command"][0] if step.get("command") else "apt-get"
        pm = cmd_bin.replace("-get", "")  # apt-get → apt

    result = check_system_deps(packages, pm)
    missing = result.get("missing", [])

    if not missing:
        return {
            "ok": True,
            "message": "All packages already installed",
            "skipped": True,
        }

    # Rebuild command with only missing packages
    cmd = _build_pkg_install_cmd(missing, pm)
    return _run_subprocess(
        cmd,
        needs_sudo=step.get("needs_sudo", True),
        sudo_password=sudo_password,
        timeout=step.get("timeout", 120),
    )


def _execute_repo_step(
    step: dict, *, sudo_password: str = "",
) -> dict[str, Any]:
    """Set up a package repository (GPG key + source list).

    Handles both single-command steps and multi-step ``sub_steps``.
    Each sub-step runs in order; first failure aborts.
    """
    sub_steps = step.get("sub_steps", [step])
    results = []

    for sub_step in sub_steps:
        result = _run_subprocess(
            sub_step["command"],
            needs_sudo=sub_step.get("needs_sudo", True),
            sudo_password=sudo_password,
            timeout=sub_step.get("timeout", 60),
        )
        results.append(result)
        if not result["ok"]:
            return result

    return {
        "ok": True,
        "message": "Repository configured",
        "sub_results": results,
    }


def _execute_command_step(
    step: dict,
    *,
    sudo_password: str = "",
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute a command step (tool install or post_install action)."""
    return _run_subprocess(
        step["command"],
        needs_sudo=step.get("needs_sudo", False),
        sudo_password=sudo_password,
        timeout=step.get("timeout", 120),
        env_overrides=env_overrides,
    )


def _execute_verify_step(
    step: dict,
    *,
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Verify a tool is installed and working.

    Checks PATH first (with env_overrides for non-standard locations
    like ``~/.cargo/bin``).  If the binary isn't found, returns an
    advisory error instead of running the command.
    """
    cli = step.get("cli", step["command"][0])

    # Build expanded PATH for lookup
    check_path = os.environ.get("PATH", "")
    if env_overrides and "PATH" in env_overrides:
        check_path = os.path.expandvars(env_overrides["PATH"])

    binary = shutil.which(cli, path=check_path)
    if not binary:
        return {
            "ok": False,
            "error": f"'{cli}' not found in PATH after install",
            "needs_shell_restart": True,
        }

    # Run verify command
    return _run_subprocess(
        step["command"],
        needs_sudo=False,
        timeout=10,
        env_overrides=env_overrides,
    )


# ── Phase 6: Hardware detection — GPU, kernel, system resources ────

import platform


def _extract_gpu_model(line: str) -> str:
    """Extract GPU model from an lspci line."""
    # e.g. "01:00.0 VGA compatible controller [0300]: NVIDIA Corporation ... [10de:2684]"
    # Strip PCI address and classification, keep the device name
    parts = line.split(":", 2)
    if len(parts) >= 3:
        # Remove PCI ID brackets at end
        model = re.sub(r"\s*\[[0-9a-f:]+\]\s*$", "", parts[2].strip())
        return model
    return line.strip()


def _extract_pci_id(line: str) -> str | None:
    """Extract PCI vendor:device ID from an lspci line."""
    m = re.search(r"\[([0-9a-f]{4}:[0-9a-f]{4})\]", line, re.IGNORECASE)
    return m.group(1) if m else None


def _lspci_gpu() -> dict | None:
    """Parse lspci for GPU info."""
    try:
        r = subprocess.run(
            ["lspci", "-nn"],
            capture_output=True, text=True, timeout=5,
        )
        for line in r.stdout.splitlines():
            if "VGA" in line or "3D controller" in line:
                upper = line.upper()
                if "NVIDIA" in upper or "10DE:" in upper:
                    return {"vendor": "nvidia",
                            "model": _extract_gpu_model(line),
                            "pci_id": _extract_pci_id(line)}
                if "AMD" in upper or "ATI" in upper or "1002:" in upper:
                    return {"vendor": "amd",
                            "model": _extract_gpu_model(line),
                            "pci_id": _extract_pci_id(line)}
                if "INTEL" in upper:
                    return {"vendor": "intel",
                            "model": _extract_gpu_model(line),
                            "pci_id": _extract_pci_id(line)}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _nvidia_smi() -> dict | None:
    """Get NVIDIA driver and CUDA info from nvidia-smi."""
    if not shutil.which("nvidia-smi"):
        return None
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version,name",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            parts = r.stdout.strip().split(",")
            driver_ver = parts[0].strip()

            # Get CUDA version from the header nvidia-smi output
            r2 = subprocess.run(
                ["nvidia-smi"],
                capture_output=True, text=True, timeout=5,
            )
            cuda_ver = None
            m = re.search(r"CUDA Version:\s+(\d+\.\d+)", r2.stdout)
            if m:
                cuda_ver = m.group(1)

            return {"driver_version": driver_ver, "cuda_version": cuda_ver}
    except Exception:
        pass
    return None


def _rocminfo() -> dict | None:
    """Get AMD ROCm info."""
    if not shutil.which("rocminfo"):
        return None
    try:
        r = subprocess.run(
            ["rocminfo"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            m = re.search(r"Runtime Version:\s+(\d+\.\d+)", r.stdout)
            return {"version": m.group(1)} if m else {"version": "unknown"}
    except Exception:
        pass
    return None


def _list_gpu_modules() -> list[str]:
    """List loaded GPU-related kernel modules."""
    relevant = {"nvidia", "nvidia_drm", "nvidia_modeset", "nvidia_uvm",
                "nouveau", "amdgpu", "radeon", "i915", "vfio_pci"}
    try:
        with open("/proc/modules") as f:
            loaded = {line.split()[0] for line in f}
        return sorted(relevant & loaded)
    except FileNotFoundError:
        return []


def detect_gpu() -> dict:
    """Detect GPU hardware and driver state.

    Returns a structured dict with:
      - Per-vendor GPU info (nvidia, amd, intel)
      - Driver version and loaded status
      - CUDA/ROCm version if applicable
      - Loaded kernel modules

    This feeds into Phase 4 choice constraint evaluation for
    hardware-gated options (CUDA, ROCm, OpenCL).
    """
    result: dict = {
        "has_gpu": False,
        "nvidia": {"present": False, "model": None, "driver_version": None,
                   "cuda_version": None, "driver_loaded": False},
        "amd": {"present": False, "model": None, "rocm_version": None,
                "driver_loaded": False},
        "intel": {"present": False, "model": None,
                  "driver_loaded": False},
        "modules_loaded": [],
    }

    # Detect via lspci
    gpu_info = _lspci_gpu()
    if gpu_info:
        result["has_gpu"] = True
        vendor = gpu_info["vendor"]

        if vendor == "nvidia":
            result["nvidia"]["present"] = True
            result["nvidia"]["model"] = gpu_info["model"]
            result["nvidia"]["pci_id"] = gpu_info.get("pci_id")
            # nvidia-smi for driver + CUDA
            nvsmi = _nvidia_smi()
            if nvsmi:
                result["nvidia"]["driver_loaded"] = True
                result["nvidia"]["driver_version"] = nvsmi["driver_version"]
                result["nvidia"]["cuda_version"] = nvsmi["cuda_version"]

        elif vendor == "amd":
            result["amd"]["present"] = True
            result["amd"]["model"] = gpu_info["model"]
            result["amd"]["pci_id"] = gpu_info.get("pci_id")
            # ROCm info
            rocm = _rocminfo()
            if rocm:
                result["amd"]["driver_loaded"] = True
                result["amd"]["rocm_version"] = rocm["version"]

        elif vendor == "intel":
            result["intel"]["present"] = True
            result["intel"]["model"] = gpu_info["model"]
            result["intel"]["pci_id"] = gpu_info.get("pci_id")

    # Check loaded modules
    result["modules_loaded"] = _list_gpu_modules()

    # Infer driver_loaded from modules if not set via tool
    if not result["nvidia"]["driver_loaded"]:
        result["nvidia"]["driver_loaded"] = "nvidia" in result["modules_loaded"]
    if not result["amd"]["driver_loaded"]:
        result["amd"]["driver_loaded"] = "amdgpu" in result["modules_loaded"]
    if not result["intel"]["driver_loaded"]:
        result["intel"]["driver_loaded"] = "i915" in result["modules_loaded"]

    # ── Container GPU passthrough detection ──
    result["container_gpu"] = {"passthrough_detected": False, "method": None}
    # Check for NVIDIA device nodes (Docker --gpus or k8s GPU plugin)
    if os.path.exists("/dev/nvidia0"):
        result["container_gpu"]["passthrough_detected"] = True
        result["container_gpu"]["method"] = "nvidia-device"
        result["nvidia"]["present"] = True
    # Check NVIDIA_VISIBLE_DEVICES env var (Docker --gpus flag)
    if os.environ.get("NVIDIA_VISIBLE_DEVICES"):
        result["container_gpu"]["passthrough_detected"] = True
        result["container_gpu"]["method"] = "nvidia-docker"
        result["container_gpu"]["visible_devices"] = os.environ["NVIDIA_VISIBLE_DEVICES"]
        result["nvidia"]["present"] = True
    # Check for AMD/Intel render nodes
    if os.path.exists("/dev/dri/renderD128"):
        if not result["container_gpu"]["passthrough_detected"]:
            result["container_gpu"]["passthrough_detected"] = True
            result["container_gpu"]["method"] = "dri-render-node"

    return result


# ── CUDA / Driver compatibility matrix ─────────────────────────
# Source: https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/
# Maps minimum driver version required for each CUDA toolkit version.
_CUDA_DRIVER_COMPAT: list[tuple[str, str]] = [
    # (cuda_version, min_driver_version)
    ("12.6", "560.28"),
    ("12.5", "555.42"),
    ("12.4", "550.54"),
    ("12.3", "545.23"),
    ("12.2", "535.86"),
    ("12.1", "530.30"),
    ("12.0", "525.60"),
    ("11.8", "520.61"),
    ("11.7", "515.43"),
    ("11.6", "510.39"),
    ("11.5", "495.29"),
    ("11.4", "470.42"),
    ("11.3", "465.19"),
    ("11.2", "460.27"),
    ("11.1", "455.23"),
    ("11.0", "450.36"),
    ("10.2", "440.33"),
    ("10.1", "418.39"),
    ("10.0", "410.48"),
]


def check_cuda_driver_compat(
    cuda_version: str,
    driver_version: str,
) -> dict:
    """Check if a driver version is compatible with a CUDA toolkit version.

    Args:
        cuda_version: Installed or target CUDA version, e.g. ``"12.4"``.
        driver_version: Installed NVIDIA driver version, e.g. ``"535.183"``.

    Returns:
        ``{"compatible": True}`` or
        ``{"compatible": False, "min_driver": "...", "message": "..."}``
    """
    # Normalize cuda_version to major.minor
    parts = cuda_version.split(".")
    cuda_mm = f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else cuda_version

    min_driver = None
    for cv, md in _CUDA_DRIVER_COMPAT:
        if cv == cuda_mm:
            min_driver = md
            break

    if min_driver is None:
        # Unknown CUDA version — can't validate
        return {"compatible": True, "unknown_cuda": cuda_mm}

    try:
        drv_parts = [int(x) for x in driver_version.split(".")]
        min_parts = [int(x) for x in min_driver.split(".")]

        # Compare major.minor
        drv_tuple = tuple(drv_parts[:2]) if len(drv_parts) >= 2 else (drv_parts[0], 0)
        min_tuple = tuple(min_parts[:2]) if len(min_parts) >= 2 else (min_parts[0], 0)

        if drv_tuple >= min_tuple:
            return {"compatible": True}
        else:
            return {
                "compatible": False,
                "min_driver": min_driver,
                "message": (
                    f"CUDA {cuda_mm} requires driver >= {min_driver}, "
                    f"but installed driver is {driver_version}. "
                    f"Update the NVIDIA driver first."
                ),
            }
    except (ValueError, IndexError):
        return {"compatible": True, "parse_error": True}


def _detect_secure_boot() -> bool | None:
    """Detect if Secure Boot is enabled.

    Returns True if enabled, False if disabled, None if detection fails
    (no mokutil, not applicable for the platform).
    """
    try:
        r = subprocess.run(
            ["mokutil", "--sb-state"],
            capture_output=True, text=True, timeout=5,
        )
        if "SecureBoot enabled" in r.stdout:
            return True
        if "SecureBoot disabled" in r.stdout:
            return False
    except FileNotFoundError:
        pass
    return None


def detect_kernel() -> dict:
    """Detect kernel version, headers, DKMS, Secure Boot, and GPU modules.

    Returns:
        Dict with kernel details for driver/module install decisions.
    """
    version = platform.release()
    result: dict = {
        "version": version,
        "major": None,
        "minor": None,
        "arch": platform.machine(),
        "headers_installed": False,
        "dkms_available": False,
        "secure_boot": None,
        "modules_loaded": [],
    }

    # Parse version
    m = re.match(r"(\d+)\.(\d+)\.", version)
    if m:
        result["major"] = int(m.group(1))
        result["minor"] = int(m.group(2))

    # Kernel headers
    result["headers_installed"] = Path(
        f"/lib/modules/{version}/build"
    ).exists()

    # DKMS
    result["dkms_available"] = shutil.which("dkms") is not None

    # Secure Boot
    result["secure_boot"] = _detect_secure_boot()

    # GPU-related loaded modules
    result["modules_loaded"] = _list_gpu_modules()

    return result


def _read_cpu_model() -> str:
    """Read CPU model name from /proc/cpuinfo."""
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except (FileNotFoundError, IndexError):
        pass
    return platform.processor() or "unknown"


def _read_total_ram_mb() -> int:
    """Read total RAM in MB from /proc/meminfo."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except (FileNotFoundError, ValueError):
        pass
    return 0


def _read_available_ram_mb() -> int:
    """Read available RAM in MB from /proc/meminfo."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except (FileNotFoundError, ValueError):
        pass
    return 0


def _read_disk_free_mb(path: str = "/") -> int:
    """Read free disk space in MB."""
    try:
        import shutil as sh
        disk = sh.disk_usage(path)
        return disk.free // (1024 * 1024)
    except OSError:
        return 0


def detect_hardware() -> dict:
    """Detect hardware capabilities — CPU, RAM, disk, GPU, kernel.

    Assembles a full hardware profile that feeds into Phase 4 choice
    constraint evaluation and Phase 5 resource checking.

    Returns::

        {
            "cpu_arch": "x86_64",
            "cpu_count": 8,
            "cpu_model": "Intel Core i7-12700K",
            "ram_total_mb": 16384,
            "ram_available_mb": 12288,
            "disk_free_mb": 50000,
            "gpu": { ... },
            "kernel": { ... },
        }
    """
    return {
        "cpu_arch": platform.machine(),
        "cpu_count": os.cpu_count(),
        "cpu_model": _read_cpu_model(),
        "ram_total_mb": _read_total_ram_mb(),
        "ram_available_mb": _read_available_ram_mb(),
        "disk_free_mb": _read_disk_free_mb("/"),
        "gpu": detect_gpu(),
        "kernel": detect_kernel(),
    }


# ── Phase 5: Build-from-source step executors ──────────────────

from pathlib import Path


# ── Build timeout tiers ──
BUILD_TIMEOUT_TIERS: dict[str, int] = {
    "small": 300,    # < 10k LOC
    "medium": 600,   # 10k-100k LOC
    "large": 1200,   # 100k-1M LOC
    "huge": 3600,    # 1M+ LOC (LLVM, Linux kernel)
}


def detect_build_toolchain() -> dict[str, str | None]:
    """Detect available build tools and their versions.

    Checks compilers (gcc, clang, rustc), build systems (make, cmake,
    ninja, meson, autotools), and language toolchains (cargo, go).

    Returns:
        Dict mapping tool name → version string (or None if not found).
        Only includes tools that are actually installed.
    """
    _patterns = {
        "gcc": r"(\d+\.\d+\.\d+)",
        "g++": r"(\d+\.\d+\.\d+)",
        "clang": r"(\d+\.\d+\.\d+)",
        "make": r"(\d+\.\d+)",
        "cmake": r"(\d+\.\d+\.\d+)",
        "ninja": r"(\d+\.\d+\.\d+)",
        "meson": r"(\d+\.\d+\.\d+)",
        "autoconf": r"(\d+\.\d+)",
        "automake": r"(\d+\.\d+)",
        "pkg-config": r"(\d+\.\d+)",
        "rustc": r"(\d+\.\d+\.\d+)",
        "cargo": r"(\d+\.\d+\.\d+)",
        "go": r"go(\d+\.\d+\.\d+)",
    }
    found: dict[str, str | None] = {}
    for binary, pattern in _patterns.items():
        if not shutil.which(binary):
            continue
        try:
            r = subprocess.run(
                [binary, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            m = re.search(pattern, r.stdout + r.stderr)
            found[binary] = m.group(1) if m else "unknown"
        except Exception:
            found[binary] = "unknown"
    return found


def _validate_toolchain(
    requires_toolchain: list[str],
) -> dict:
    """Validate that required build tools are installed.

    Checks each tool in ``requires_toolchain`` against the system
    PATH.  Returns missing tools with install suggestions.

    Args:
        requires_toolchain: List of required tool names, e.g.
            ``["gcc", "make", "cmake"]``.

    Returns:
        ``{"ok": True, "available": [...]}`` if all tools present,
        ``{"ok": False, "missing": [...], "suggestion": "..."}`` otherwise.
    """
    available: list[str] = []
    missing: list[str] = []

    for tool in requires_toolchain:
        if shutil.which(tool):
            available.append(tool)
        else:
            missing.append(tool)

    if not missing:
        return {"ok": True, "available": available}

    # Build install suggestion
    suggestion_parts = []
    # Check if build-essential would cover it
    essential_tools = {"gcc", "g++", "make", "libc-dev", "dpkg-dev"}
    if missing and set(missing) & essential_tools:
        suggestion_parts.append("Install build-essential: apt-get install -y build-essential")

    other_missing = [t for t in missing if t not in essential_tools]
    if other_missing:
        suggestion_parts.append(
            f"Install: {', '.join(other_missing)}"
        )

    return {
        "ok": False,
        "missing": missing,
        "available": available,
        "suggestion": " | ".join(suggestion_parts) if suggestion_parts else f"Install: {', '.join(missing)}",
    }


def _check_build_resources(
    disk_estimate_mb: int = 500,
    ram_estimate_mb: int = 512,
    build_dir: str = "/tmp",
) -> dict:
    """Check if system has sufficient resources for a build.

    Checks available disk space in the build directory and available
    RAM.  Returns a status dict with any issues found.

    Args:
        disk_estimate_mb: Estimated disk space needed (MB).
        ram_estimate_mb: Estimated RAM needed (MB).
        build_dir: Directory where the build will happen.

    Returns::

        {"ok": True, "disk_free_mb": N, "ram_free_mb": N}
        or
        {"ok": False, "issues": [...], ...}
    """
    import shutil as sh

    issues: list[str] = []

    # Disk check
    disk_free_mb = 0
    try:
        disk = sh.disk_usage(build_dir)
        disk_free_mb = disk.free // (1024 * 1024)
        if disk_free_mb < disk_estimate_mb:
            issues.append(
                f"Need {disk_estimate_mb}MB disk, have {disk_free_mb}MB"
            )
    except OSError:
        issues.append(f"Cannot check disk at {build_dir}")

    # RAM check
    ram_free_mb = 0
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    ram_free_mb = int(line.split()[1]) // 1024
                    break
        if ram_free_mb < ram_estimate_mb:
            issues.append(
                f"Need {ram_estimate_mb}MB RAM, have {ram_free_mb}MB"
            )
    except (OSError, ValueError):
        pass  # /proc/meminfo not available (macOS, container)

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "disk_free_mb": disk_free_mb,
        "ram_free_mb": ram_free_mb,
    }


# ── Build system adapters (plan generators) ────────────────────
#
# Spec: Phase 5 §Build System Adapters, domain-build-systems,
#        domain-build-from-source §The Pipeline.
#
# These are FACTORY functions: recipe + profile → list[step dict].
# The returned steps are consumed by the existing Phase 5
# executors (_execute_source_step, _execute_build_step, etc.).


def _substitute_build_vars(
    command: list[str],
    variables: dict[str, str],
) -> list[str]:
    """Replace ``{var}`` placeholders in a command array.

    Handles the standard build variables (``{nproc}``,
    ``{build_dir}``) plus any recipe-specific input values
    (``{cuda_flag}``, ``{build_type}``, etc.).

    Args:
        command: Command array with possible ``{var}`` tokens.
        variables: Mapping of variable names to their values.

    Returns:
        New list with all ``{key}`` tokens substituted.
    """
    result: list[str] = []
    for token in command:
        for key, value in variables.items():
            token = token.replace(f"{{{key}}}", str(value))
        result.append(token)
    return result


def _substitute_install_vars(
    command: list[str],
    profile: dict,
    *,
    version: str = "",
    extra: dict[str, str] | None = None,
) -> list[str]:
    """Replace ``{var}`` placeholders in install commands and URLs.

    Standard variables available:
    - ``{arch}`` — normalized architecture (``amd64``, ``arm64``)
    - ``{version}`` — selected version (if supplied)
    - ``{user}`` — current username
    - ``{home}`` — home directory
    - ``{distro}`` — distro id (``ubuntu``, ``fedora``, etc.)
    - ``{nproc}`` — CPU core count

    Also accepts ``extra`` for recipe-specific variables.

    Args:
        command: Command array with possible ``{var}`` tokens.
        profile: System profile from l0_system_profile().
        version: Selected version string (may be empty).
        extra: Additional key-value substitutions.

    Returns:
        New list with tokens substituted.
    """
    machine = platform.machine().lower()
    variables: dict[str, str] = {
        "arch": _IARCH_MAP.get(machine, machine),
        "user": os.getenv("USER", os.getenv("LOGNAME", "unknown")),
        "home": str(Path.home()),
        "nproc": str(os.cpu_count() or 1),
    }
    # Distro from profile or fallback
    distro_info = profile.get("distro", {})
    variables["distro"] = distro_info.get("id", platform.system().lower())
    variables["distro_family"] = distro_info.get("family", "unknown")

    if version:
        variables["version"] = version

    # Recipe arch map (e.g. x86_64 → amd64 for Hugo)
    arch_map = profile.get("_arch_map", {})
    if arch_map:
        raw_arch = platform.machine().lower()
        variables["arch"] = arch_map.get(raw_arch, variables["arch"])

    if extra:
        variables.update(extra)

    return _substitute_build_vars(command, variables)


def _autotools_plan(
    recipe: dict,
    profile: dict,
    build_dir: str,
) -> list[dict]:
    """Generate plan steps for an autotools (./configure && make) build.

    Produces three steps:
        1. ``./configure`` with optional recipe args
        2. ``make`` with parallel flag from CPU count
        3. ``make install`` with sudo

    Args:
        recipe: Build recipe with optional ``configure_args``,
                ``install_prefix``, ``disk_estimate_mb``.
        profile: System profile from ``l0_system_profile()``.
        build_dir: Absolute path to the source directory.

    Returns:
        Ordered list of step dicts ready for ``execute_plan_step()``.
    """
    nproc = str(profile.get("resources", {}).get("cpu_count", 1))
    configure_args = list(recipe.get("configure_args", []))
    prefix = recipe.get("install_prefix", "/usr/local")

    # Build variable map for substitution
    variables = {"nproc": nproc, "build_dir": build_dir}
    variables.update(recipe.get("input_values", {}))

    # Configure step
    configure_cmd = ["./configure", f"--prefix={prefix}"] + configure_args
    configure_cmd = _substitute_build_vars(configure_cmd, variables)

    steps: list[dict] = [
        {
            "type": "build",
            "label": "Configure (autotools)",
            "command": configure_cmd,
            "cwd": build_dir,
            "needs_sudo": False,
            "timeout": recipe.get("configure_timeout", 120),
        },
        {
            "type": "build",
            "label": f"Compile ({nproc} cores)",
            "command": ["make", f"-j{nproc}"],
            "cwd": build_dir,
            "needs_sudo": False,
            "parallel": True,
            "timeout": BUILD_TIMEOUT_TIERS.get(
                recipe.get("build_size", "medium"), 600,
            ),
        },
        {
            "type": "install",
            "label": "Install (make install)",
            "command": ["make", "install"],
            "cwd": build_dir,
            "needs_sudo": recipe.get("install_needs_sudo", True),
            "timeout": 60,
        },
    ]

    return steps


def _cmake_plan(
    recipe: dict,
    profile: dict,
    build_dir: str,
) -> list[dict]:
    """Generate plan steps for a CMake build.

    Produces three steps:
        1. ``cmake -B build`` with build type and optional flags
        2. ``cmake --build build`` with parallel jobs
        3. ``cmake --install build`` with sudo

    Args:
        recipe: Build recipe with optional ``cmake_args``,
                ``build_type``, ``disk_estimate_mb``.
        profile: System profile from ``l0_system_profile()``.
        build_dir: Absolute path to the source directory.

    Returns:
        Ordered list of step dicts ready for ``execute_plan_step()``.
    """
    nproc = str(profile.get("resources", {}).get("cpu_count", 1))
    cmake_args = list(recipe.get("cmake_args", []))
    build_type = recipe.get("build_type", "Release")
    prefix = recipe.get("install_prefix", "/usr/local")

    # Build variable map
    variables = {"nproc": nproc, "build_dir": build_dir}
    variables.update(recipe.get("input_values", {}))

    # Configure step — cmake generates the build system
    configure_cmd = [
        "cmake", "-B", "build",
        f"-DCMAKE_BUILD_TYPE={build_type}",
        f"-DCMAKE_INSTALL_PREFIX={prefix}",
    ] + cmake_args
    configure_cmd = _substitute_build_vars(configure_cmd, variables)

    steps: list[dict] = [
        {
            "type": "build",
            "label": "CMake configure",
            "command": configure_cmd,
            "cwd": build_dir,
            "needs_sudo": False,
            "timeout": recipe.get("configure_timeout", 60),
        },
        {
            "type": "build",
            "label": f"CMake build ({nproc} cores)",
            "command": ["cmake", "--build", "build", "-j", nproc],
            "cwd": build_dir,
            "needs_sudo": False,
            "parallel": True,
            "timeout": BUILD_TIMEOUT_TIERS.get(
                recipe.get("build_size", "medium"), 600,
            ),
        },
        {
            "type": "install",
            "label": "CMake install",
            "command": ["cmake", "--install", "build"],
            "cwd": build_dir,
            "needs_sudo": recipe.get("install_needs_sudo", True),
            "timeout": 60,
        },
    ]

    return steps


def _cargo_git_plan(
    recipe: dict,
    profile: dict,
) -> list[dict]:
    """Generate plan steps for ``cargo install --git``.

    This is the simplest adapter: a single step that cargo handles
    end-to-end (download → compile → install to ``~/.cargo/bin/``).

    Args:
        recipe: Build recipe with ``git_repo`` (required) and
                optional ``branch``, ``features``.
        profile: System profile (unused but kept for signature
                 consistency with other adapters).

    Returns:
        Single-step list ready for ``execute_plan_step()``.
    """
    git_repo = recipe["git_repo"]
    cmd = ["cargo", "install", "--git", git_repo]

    branch = recipe.get("branch")
    if branch:
        cmd += ["--branch", branch]

    features = recipe.get("features")
    if features:
        cmd += ["--features", ",".join(features)]

    return [{
        "type": "tool",
        "label": f"Build from git ({git_repo.split('/')[-1]})",
        "command": cmd,
        "needs_sudo": False,
        "timeout": BUILD_TIMEOUT_TIERS.get(
            recipe.get("build_size", "medium"), 600,
        ),
    }]


# ── Adapter dispatch ───────────────────────────────────────────

_BUILD_ADAPTERS: dict[str, Any] = {
    "autotools": _autotools_plan,
    "cmake": _cmake_plan,
    "cargo_git": _cargo_git_plan,
}
"""Map of build_system identifier → adapter function."""


def _execute_source_step(
    step: dict,
    *,
    sudo_password: str = "",
) -> dict[str, Any]:
    """Obtain source code — git clone, tarball download, or local path.

    Step format::

        {
            "type": "source",
            "source": {
                "type": "git",
                "repo": "https://github.com/...",
                "branch": "stable",
                "depth": 1,
            },
            "dest": "/tmp/build-dir",
        }
    """
    source = step.get("source", {})
    dest = step.get("dest", step.get("cwd", "/tmp/build"))
    source_type = source.get("type", "git")

    if source_type == "git":
        cmd: list[str] = ["git", "clone"]
        if source.get("branch"):
            cmd += ["--branch", source["branch"]]
        if source.get("depth"):
            cmd += ["--depth", str(source["depth"])]
        cmd += [source["repo"], dest]
        return _run_subprocess(
            cmd,
            timeout=step.get("timeout", 120),
            needs_sudo=step.get("needs_sudo", False),
            sudo_password=sudo_password,
        )

    elif source_type == "tarball":
        url = source.get("url", "")
        if not url:
            return {"ok": False, "error": "No tarball URL specified"}
        # Download and extract
        Path(dest).mkdir(parents=True, exist_ok=True)
        dl_cmd = ["bash", "-c",
                  f"curl -fsSL '{url}' | tar xz -C '{dest}' --strip-components=1"]
        return _run_subprocess(
            dl_cmd,
            timeout=step.get("timeout", 120),
            needs_sudo=step.get("needs_sudo", False),
            sudo_password=sudo_password,
        )

    elif source_type == "local":
        if not Path(dest).exists():
            return {"ok": False, "error": f"Source not found: {dest}"}
        return {"ok": True, "message": "Source already present"}

    else:
        return {"ok": False, "error": f"Unknown source type: {source_type}"}


def _parse_build_progress(output: str) -> dict:
    """Parse build output for progress information.

    Recognizes progress patterns from:
    - **ninja**: ``[45/100]``
    - **cmake**: ``[ 45%]``
    - **make**: counts targets (heuristic)

    Args:
        output: Combined stdout+stderr from the build command.

    Returns:
        ``{"total_targets": N, "completed": N, "percent": 0-100}``
        or empty dict if no progress detected.
    """
    if not output:
        return {}

    # Ninja: [N/Total]
    ninja_matches = re.findall(r"\[(\d+)/(\d+)\]", output)
    if ninja_matches:
        last = ninja_matches[-1]
        completed = int(last[0])
        total = int(last[1])
        return {
            "total_targets": total,
            "completed": completed,
            "percent": int(completed * 100 / total) if total > 0 else 0,
        }

    # CMake: [ 45%]
    cmake_matches = re.findall(r"\[\s*(\d+)%\]", output)
    if cmake_matches:
        percent = int(cmake_matches[-1])
        return {"percent": percent}

    # Make: count "Compiling" or "CC" lines as a rough heuristic
    compile_lines = re.findall(
        r"(?:^|\n)\s*(?:Compiling|CC|CXX|g\+\+|gcc)\s",
        output,
    )
    if compile_lines:
        return {
            "completed": len(compile_lines),
            "percent": None,  # can't determine total without reading Makefile
        }

    return {}


def _analyse_build_failure(
    tool: str,
    stderr: str,
    build_system: str = "",
) -> dict | None:
    """Analyse a build failure's stderr for common patterns.

    Returns a remediation dict with ``cause`` and ``suggestion``,
    or ``None`` if the error is unrecognized.

    Args:
        tool: Tool being built.
        stderr: stderr output from the failed build.
        build_system: Build system (``make``, ``cmake``, ``ninja``).

    Returns:
        ``{"cause": "...", "suggestion": "...", "confidence": "high|medium|low"}``
    """
    if not stderr:
        return None

    s = stderr.lower()

    # Missing header files
    if "fatal error:" in s and ".h" in s:
        # Extract the missing header
        m = re.search(r"fatal error:\s*(.+\.h):\s*no such file", s)
        header = m.group(1) if m else "unknown"
        return {
            "cause": f"Missing header file: {header}",
            "suggestion": f"Install the development package for {header}. "
                          f"Try: apt-get install -y {tool}-dev or the appropriate -devel package.",
            "confidence": "high",
        }

    # Missing library
    if "cannot find -l" in s:
        m = re.search(r"cannot find -l(\S+)", s)
        lib = m.group(1) if m else "unknown"
        return {
            "cause": f"Missing library: lib{lib}",
            "suggestion": f"Install lib{lib}-dev (Debian) or {lib}-devel (Fedora)",
            "confidence": "high",
        }

    # Out of memory (OOM during compilation)
    if "internal compiler error" in s and ("killed" in s or "virtual memory" in s):
        return {
            "cause": "Out of memory during compilation",
            "suggestion": "Reduce parallel jobs: try -j1 or -j2 instead of full parallelism",
            "confidence": "medium",
        }

    # CMake: package not found
    if "could not find" in s and "cmake" in (build_system or "cmake"):
        m = re.search(r"could not find.*?package\s+(\S+)", s)
        pkg = m.group(1) if m else "a required package"
        return {
            "cause": f"CMake package not found: {pkg}",
            "suggestion": f"Install the cmake package for {pkg} or set CMAKE_PREFIX_PATH",
            "confidence": "medium",
        }

    # Compiler not found
    if "cc: not found" in s or "g++: not found" in s or "gcc: not found" in s:
        return {
            "cause": "C/C++ compiler not found",
            "suggestion": "Install build-essential: apt-get install -y build-essential",
            "confidence": "high",
        }

    # Permission denied
    if "permission denied" in s:
        return {
            "cause": "Permission denied during build",
            "suggestion": "The build step may need sudo, or the build directory permissions need fixing",
            "confidence": "medium",
        }

    return None


def _execute_build_step(
    step: dict,
    *,
    sudo_password: str = "",
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run a build command (make, cmake --build, ninja).

    Supports:
      - ``parallel: true`` — auto-detect CPU count for ``-j`` flag
      - ``jobs: N`` — override parallel job count
      - ``cwd`` — build directory
      - Extended timeout (default 600s for builds)
      - **Progress parsing** from build output
      - **Failure analysis** on build errors
    """
    import multiprocessing

    cmd = list(step["command"])
    cwd = step.get("cwd")

    # Auto-parallel: add -j flag if parallel requested
    if step.get("parallel", True):  # builds default to parallel
        jobs = step.get("jobs", multiprocessing.cpu_count())
        # Only add -j if not already present and command supports it
        has_j = any(a.startswith("-j") for a in cmd)
        if not has_j:
            if cmd[0] in ("make", "ninja"):
                cmd.append(f"-j{jobs}")
            elif cmd[0] == "cmake" and "--build" in cmd:
                cmd += ["--", f"-j{jobs}"]

    # ── ccache integration ──
    if step.get("ccache", True) and shutil.which("ccache"):
        # Inject ccache wrapper via env vars (non-invasive)
        build_env = dict(env_overrides or {})
        if "CC" not in build_env:
            # Detect actual compiler
            cc = shutil.which("gcc") or shutil.which("cc")
            if cc:
                build_env["CC"] = f"ccache {os.path.basename(cc)}"
        if "CXX" not in build_env:
            cxx = shutil.which("g++") or shutil.which("c++")
            if cxx:
                build_env["CXX"] = f"ccache {os.path.basename(cxx)}"
        env_overrides = build_env

    result = _run_subprocess(
        cmd,
        needs_sudo=step.get("needs_sudo", False),
        sudo_password=sudo_password,
        timeout=step.get("timeout", 600),
        env_overrides=env_overrides,
        cwd=cwd,
    )

    # Report ccache stats if available
    if step.get("ccache", True) and shutil.which("ccache") and result.get("ok"):
        try:
            stats = subprocess.run(
                ["ccache", "-s"],
                capture_output=True, text=True, timeout=5,
            )
            if stats.returncode == 0:
                result["ccache_stats"] = stats.stdout.strip()[:500]
        except Exception:
            pass

    # Parse progress from output
    output = result.get("stdout", "") + result.get("stderr", "")
    progress = _parse_build_progress(output)
    if progress:
        result["build_progress"] = progress

    # Failure analysis
    if not result["ok"]:
        build_system = cmd[0] if cmd else ""
        tool_name = step.get("tool", step.get("label", "unknown"))
        analysis = _analyse_build_failure(
            tool_name, result.get("stderr", ""), build_system,
        )
        if analysis:
            result["build_failure_analysis"] = analysis

    return result


def _execute_install_step(
    step: dict,
    *,
    sudo_password: str = "",
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run an install command in a build directory (make install, cmake --install)."""
    return _run_subprocess(
        step["command"],
        needs_sudo=step.get("needs_sudo", True),
        sudo_password=sudo_password,
        timeout=step.get("timeout", 120),
        env_overrides=env_overrides,
        cwd=step.get("cwd"),
    )


def _execute_cleanup_step(
    step: dict,
) -> dict[str, Any]:
    """Clean up build artifacts.

    Removes the build directory.  Non-fatal — a failed cleanup
    only produces a warning, not a plan failure.
    """
    import shutil as sh

    target = step.get("target")
    if not target:
        # Fall back to command's last arg or cwd
        cmd = step.get("command", [])
        target = cmd[-1] if cmd else step.get("cwd")

    if target and Path(target).exists():
        try:
            sh.rmtree(target, ignore_errors=True)
            return {"ok": True, "message": f"Cleaned up {target}"}
        except Exception as e:
            return {"ok": True, "warning": f"Cleanup partial: {e}"}

    return {"ok": True, "message": "Nothing to clean"}


# ── Phase 7: Data packs — downloads, checksums, freshness ──────


def _fmt_size(n: int | float) -> str:
    """Format byte count to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _verify_checksum(path: Path, expected: str) -> bool:
    """Verify file checksum.  Format: ``algo:hex``.

    Supports sha256, sha1, md5.

    Args:
        path: Path to the downloaded file.
        expected: Checksum string like ``sha256:abc123...``.

    Returns:
        True if the file's computed digest matches ``expected``.
    """
    import hashlib

    algo, expected_hash = expected.split(":", 1)
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest() == expected_hash


def _estimate_download_time(size_bytes: int) -> dict[str, str]:
    """Estimate download time at various connection speeds."""
    speeds = {
        "10 Mbps": 10 * 1024 * 1024 / 8,
        "50 Mbps": 50 * 1024 * 1024 / 8,
        "100 Mbps": 100 * 1024 * 1024 / 8,
    }
    result: dict[str, str] = {}
    for label, speed in speeds.items():
        secs = int(size_bytes / speed)
        if secs < 60:
            result[label] = f"{secs}s"
        elif secs < 3600:
            result[label] = f"{secs // 60}m {secs % 60}s"
        else:
            result[label] = f"{secs // 3600}h {(secs % 3600) // 60}m"
    return result


def _resolve_github_release_url(
    repo: str,
    *,
    asset_pattern: str = "",
    version: str = "latest",
    timeout: int = 15,
) -> dict[str, Any]:
    """Resolve a GitHub release URL for binary download.

    Fetches the release metadata from GitHub API and finds the
    matching asset based on the ``asset_pattern``.

    Args:
        repo: GitHub repo in ``owner/repo`` format.
        asset_pattern: Glob or substring to match asset filename.
            Supports ``{arch}`` and ``{os}`` placeholders, e.g.
            ``"tool-{arch}-{os}.tar.gz"``.
        version: Version tag to fetch, or ``"latest"``.
        timeout: HTTP request timeout in seconds.

    Returns:
        ``{"ok": True, "url": "...", "version": "...", "size_bytes": N}``
        or error dict.
    """
    import urllib.request
    import json as _json

    # Build API URL
    if version == "latest":
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    else:
        tag = version if version.startswith("v") else f"v{version}"
        api_url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"

    try:
        req = urllib.request.Request(
            api_url,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "devops-cp/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = _json.loads(resp.read())
    except Exception as exc:
        return {"ok": False, "error": f"Failed to fetch release: {exc}"}

    release_tag = data.get("tag_name", "")
    assets = data.get("assets", [])

    if not assets:
        return {"ok": False, "error": f"No assets found for {repo} {release_tag}"}

    # Resolve arch/os in pattern
    machine = platform.machine().lower()
    arch = _IARCH_MAP.get(machine, machine)
    os_name = platform.system().lower()

    resolved_pattern = asset_pattern
    if resolved_pattern:
        resolved_pattern = resolved_pattern.replace("{arch}", arch)
        resolved_pattern = resolved_pattern.replace("{os}", os_name)

    # Find matching asset
    matched = None
    for asset in assets:
        name = asset.get("name", "")
        if resolved_pattern:
            if resolved_pattern in name:
                matched = asset
                break
        else:
            # Auto-match by arch + OS in filename
            name_lower = name.lower()
            if arch in name_lower and os_name in name_lower:
                matched = asset
                break

    if not matched:
        available = [a["name"] for a in assets[:10]]
        return {
            "ok": False,
            "error": f"No asset matching '{resolved_pattern}' in {repo} {release_tag}",
            "available_assets": available,
        }

    return {
        "ok": True,
        "url": matched["browser_download_url"],
        "version": release_tag.lstrip("v"),
        "size_bytes": matched.get("size", 0),
        "asset_name": matched["name"],
    }

def _execute_download_step(
    step: dict,
) -> dict[str, Any]:
    """Download a data pack with disk space check, resume, and checksum verification.

    Supports:
      - **Resume**: If a partial file exists, attempts to resume via
        HTTP Range header instead of re-downloading.
      - **Progress**: Logs download progress every 5%.
      - **Disk check**: Verifies sufficient free disk space.
      - **Checksum**: Verifies integrity after download.

    Step format::

        {
            "type": "download",
            "label": "Download Trivy DB",
            "url": "https://...",
            "dest": "~/.cache/trivy/db.tar.gz",
            "size_bytes": 150000000,
            "checksum": "sha256:abc123...",
        }
    """
    import urllib.request

    url = step.get("url", "")
    if not url:
        return {"ok": False, "error": "No download URL specified"}

    dest = Path(step.get("dest", "/tmp/download")).expanduser()
    expected_size = step.get("size_bytes")
    checksum = step.get("checksum")

    # Disk space pre-check
    if expected_size:
        try:
            import shutil as sh
            disk_free = sh.disk_usage(str(dest.parent) if dest.parent.exists() else "/tmp").free
            if disk_free < expected_size * 1.2:  # 20% buffer
                return {
                    "ok": False,
                    "error": f"Not enough disk space. Need {_fmt_size(expected_size)}, "
                             f"have {_fmt_size(disk_free)}",
                }
        except OSError:
            pass  # Can't check — proceed anyway

    # Create dest directory
    dest.parent.mkdir(parents=True, exist_ok=True)

    # ── Resume support ──
    resume_offset = 0
    if dest.exists():
        resume_offset = dest.stat().st_size
        logger.info("Partial file found: %s (%s), attempting resume",
                     dest, _fmt_size(resume_offset))

    # Download
    try:
        headers = {"User-Agent": "devops-cp/1.0"}

        # ── Auth header for gated downloads ──
        auth_type = step.get("auth_type")  # "bearer", "basic", "header"
        auth_token = step.get("auth_token", "")
        auth_env_var = step.get("auth_env_var", "")

        if auth_type and not auth_token and auth_env_var:
            auth_token = os.environ.get(auth_env_var, "")

        if auth_type and auth_token:
            if auth_type == "bearer":
                headers["Authorization"] = f"Bearer {auth_token}"
            elif auth_type == "basic":
                headers["Authorization"] = f"Basic {auth_token}"
            elif auth_type == "header":
                # Custom header name, e.g. "X-API-Key"
                header_name = step.get("auth_header_name", "Authorization")
                headers[header_name] = auth_token

        if resume_offset > 0:
            headers["Range"] = f"bytes={resume_offset}-"

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            # Check if server supports resume
            status = resp.getcode()
            if resume_offset > 0 and status == 206:
                # Partial content — resume
                mode = "ab"
                total = int(resp.headers.get("Content-Length", 0)) + resume_offset
                logger.info("Resuming download from %s", _fmt_size(resume_offset))
            else:
                # Full download (server doesn't support Range, or fresh start)
                mode = "wb"
                total = int(resp.headers.get("Content-Length", 0))
                resume_offset = 0

            with open(dest, mode) as f:
                downloaded = resume_offset
                last_progress = -1
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    # Progress tracking (log every 5%)
                    if total > 0:
                        pct = int(downloaded * 100 / total)
                        if pct >= last_progress + 5:
                            last_progress = pct
                            logger.info(
                                "Download progress: %d%% (%s / %s)",
                                pct, _fmt_size(downloaded), _fmt_size(total),
                            )

        # Verify checksum if provided
        if checksum:
            if not _verify_checksum(dest, checksum):
                dest.unlink(missing_ok=True)
                return {"ok": False, "error": "Checksum mismatch — download corrupted"}

        # Record download timestamp for freshness tracking
        stamp_dir = Path("~/.cache/devops-cp/data-stamps").expanduser()
        stamp_dir.mkdir(parents=True, exist_ok=True)
        step_id = step.get("data_pack_id", dest.stem)
        (stamp_dir / step_id).write_text(str(int(time.time())))

        return {
            "ok": True,
            "message": f"Downloaded {_fmt_size(downloaded)} to {dest}",
            "size_bytes": downloaded,
        }

    except Exception as e:
        dest.unlink(missing_ok=True)
        return {"ok": False, "error": f"Download failed: {e}"}


# ── Data pack storage conventions ──

DATA_DIRS: dict[str, str] = {
    "vulnerability_db": "~/.cache/trivy",
    "language_model": "~/.cache/spacy",
    "ml_model": "~/.cache/whisper",
    "container_image": "/var/lib/docker",
    "geoip": "~/.local/share/geoip",
    "fonts": "~/.local/share/fonts",
}

DATA_UPDATE_SCHEDULES: dict[str, int | None] = {
    "daily": 86400,
    "weekly": 604800,
    "monthly": 2592000,
    "manual": None,
}


def check_data_freshness(pack_id: str) -> dict:
    """Check if a data pack needs updating.

    Reads the timestamp marker written by _execute_download_step()
    and compares against the recipe's update_schedule.

    Returns::

        {"stale": True/False, "schedule": "daily", "age_seconds": N}
    """
    recipe = TOOL_RECIPES.get(pack_id, {})
    schedule = recipe.get("update_schedule", "manual")
    ttl = DATA_UPDATE_SCHEDULES.get(schedule)

    if ttl is None:
        return {"stale": False, "schedule": "manual"}

    marker = Path(f"~/.cache/devops-cp/data-stamps/{pack_id}").expanduser()
    if not marker.exists():
        return {"stale": True, "reason": "Never downloaded", "schedule": schedule}

    try:
        age = time.time() - marker.stat().st_mtime
    except OSError:
        return {"stale": True, "reason": "Cannot read timestamp", "schedule": schedule}

    return {
        "stale": age > ttl,
        "age_seconds": int(age),
        "schedule": schedule,
        "next_update": max(0, int(ttl - age)),
    }


def get_data_pack_usage() -> list[dict]:
    """Report disk usage of known data pack directories.

    Returns a list of dicts with type, path, size_bytes, size_human.
    """
    usage: list[dict] = []
    for pack_type, base_dir in DATA_DIRS.items():
        path = Path(base_dir).expanduser()
        if path.exists():
            try:
                size = sum(
                    f.stat().st_size
                    for f in path.rglob("*")
                    if f.is_file()
                )
                usage.append({
                    "type": pack_type,
                    "path": str(path),
                    "size_bytes": size,
                    "size_human": _fmt_size(size),
                })
            except OSError:
                pass
    return usage


# ── Phase 8: System config, services, restart management ──────


def _detect_init_system() -> str:
    """Detect the init system (systemd, openrc, initd, or unknown)."""
    if Path("/run/systemd/system").exists():
        return "systemd"
    if shutil.which("rc-service"):
        return "openrc"
    if Path("/etc/init.d").exists():
        return "initd"
    return "unknown"


def _execute_service_step(
    step: dict,
    *,
    sudo_password: str = "",
) -> dict[str, Any]:
    """Manage a system service (start/stop/restart/enable/disable/status).

    Supports systemd, openrc, and initd. Automatically detects
    the init system and dispatches accordingly.

    Step format::

        {
            "type": "service",
            "action": "start",
            "service": "docker",
            "needs_sudo": True,
        }
    """
    action = step.get("action", "status")
    service = step.get("service", "")
    if not service:
        return {"ok": False, "error": "No service specified"}

    init_system = _detect_init_system()

    if init_system == "systemd":
        cmd_map = {
            "start":   ["systemctl", "start", service],
            "stop":    ["systemctl", "stop", service],
            "restart": ["systemctl", "restart", service],
            "enable":  ["systemctl", "enable", service],
            "disable": ["systemctl", "disable", service],
            "status":  ["systemctl", "is-active", service],
        }
    elif init_system == "openrc":
        cmd_map = {
            "start":   ["rc-service", service, "start"],
            "stop":    ["rc-service", service, "stop"],
            "restart": ["rc-service", service, "restart"],
            "enable":  ["rc-update", "add", service, "default"],
            "disable": ["rc-update", "del", service, "default"],
            "status":  ["rc-service", service, "status"],
        }
    elif init_system == "initd":
        cmd_map = {
            "start":   ["service", service, "start"],
            "stop":    ["service", service, "stop"],
            "restart": ["service", service, "restart"],
            "enable":  ["update-rc.d", service, "defaults"],
            "disable": ["update-rc.d", service, "remove"],
            "status":  ["service", service, "status"],
        }
    else:
        return {"ok": False, "error": f"No init system detected for service management"}

    cmd = cmd_map.get(action)
    if not cmd:
        return {"ok": False, "error": f"Unknown service action: {action}"}

    # Status check doesn't need sudo
    needs_sudo = action != "status"

    result = _run_subprocess(
        cmd,
        needs_sudo=needs_sudo,
        sudo_password=sudo_password,
        timeout=30,
    )

    # Enrich status result
    if action == "status":
        result["active"] = result.get("ok", False)
        result["ok"] = True  # the status check itself always "succeeds"

    return result


def get_service_status(service: str) -> dict:
    """Get comprehensive service status (systemd only).

    Returns active state, sub-state, load state for systemd services.
    Falls back to a simple active check for other init systems.
    """
    init = _detect_init_system()

    if init == "systemd":
        result: dict = {}
        for prop in ("ActiveState", "SubState", "LoadState"):
            try:
                r = subprocess.run(
                    ["systemctl", "show", service, f"--property={prop}"],
                    capture_output=True, text=True, timeout=5,
                )
                key, _, val = r.stdout.strip().partition("=")
                result[key.lower()] = val
            except Exception:
                pass

        return {
            "service": service,
            "init_system": "systemd",
            "active": result.get("activestate") == "active",
            "state": result.get("activestate", "unknown"),
            "sub_state": result.get("substate", "unknown"),
            "loaded": result.get("loadstate") == "loaded",
        }

    return {"service": service, "init_system": init, "active": None, "state": "unknown"}


# ── Config template helpers ────────────────────────────────────
#
# Spec: domain-config-files §Template Schema, §Variable substitution,
#        §Validation, §Config File Write Pipeline.


def _render_template(template: str, inputs: dict) -> str:
    """Substitute ``{var}`` placeholders with input values.

    Simple string replacement — no Jinja, no escaping.

    **Built-in variables** are auto-populated from the environment
    and merged under user-provided inputs (user inputs take priority):

    - ``{user}`` — current username
    - ``{home}`` — home directory
    - ``{arch}`` — machine architecture (``amd64``, ``arm64``)
    - ``{distro}`` — distro ID (``ubuntu``, ``fedora``, etc.)
    - ``{tool_name}`` — tool being installed (if in inputs)
    - ``{nproc}`` — CPU core count

    Args:
        template: Template string with ``{key}`` tokens.
        inputs: Mapping of input IDs to their resolved values.

    Returns:
        Rendered string.
    """
    # Built-in variables (environment-sourced)
    machine = platform.machine().lower()
    _ARCH_MAP = {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "armhf"}
    builtins = {
        "user": os.getenv("USER", os.getenv("LOGNAME", "unknown")),
        "home": str(Path.home()),
        "arch": _ARCH_MAP.get(machine, machine),
        "nproc": str(os.cpu_count() or 1),
    }
    # Distro detection (lightweight)
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                if line.startswith("ID="):
                    builtins["distro"] = line.strip().split("=", 1)[1].strip('"')
                    break
    except (FileNotFoundError, OSError):
        builtins["distro"] = platform.system().lower()

    # Merge: builtins first, then user inputs override
    merged = {**builtins, **inputs}

    result = template
    for key, value in merged.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result


def _check_unsubstituted(rendered: str) -> list[str]:
    """Return list of unsubstituted ``{var}`` placeholders.

    Scans the rendered output for remaining ``{word}`` tokens that
    were not replaced by either built-in or user-provided inputs.
    Ignores JSON-like braces (``{}``, ``{{``, ``}}``) and known
    safe patterns like ``{0}``, ``{1}`` (format string indices).

    Returns:
        List of unresolved variable names (empty = all good).
    """
    import re
    # Match {word} but not {{ or }} or {0} or empty {}
    pattern = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
    return pattern.findall(rendered)

def _validate_input(input_def: dict, value: Any) -> str | None:
    """Validate a single input value against its schema.

    Args:
        input_def: Input definition from the recipe
                   (``type``, ``options``, ``validation``, etc.).
        value: User-provided value to check.

    Returns:
        Error message string, or ``None`` if valid.
    """
    input_type = input_def.get("type", "text")

    if input_type == "select":
        options = input_def.get("options", [])
        if value not in options:
            return f"Must be one of: {options}"

    elif input_type == "number":
        v = input_def.get("validation", {})
        try:
            num = int(value) if isinstance(value, str) else value
        except (ValueError, TypeError):
            return f"Must be a number"
        if "min" in v and num < v["min"]:
            return f"Must be >= {v['min']}"
        if "max" in v and num > v["max"]:
            return f"Must be <= {v['max']}"

    elif input_type == "text":
        if not isinstance(value, str):
            return "Must be a string"
        v = input_def.get("validation", {})
        if "min_length" in v and len(value) < v["min_length"]:
            return f"Must be at least {v['min_length']} characters"
        if "max_length" in v and len(value) > v["max_length"]:
            return f"Must be at most {v['max_length']} characters"
        if "pattern" in v:
            if not re.match(v["pattern"], value):
                return f"Must match pattern: {v['pattern']}"

    elif input_type == "path":
        if not isinstance(value, str):
            return "Must be a string"
        if not value.startswith("/"):
            return "Must be an absolute path"

    elif input_type == "boolean":
        if not isinstance(value, bool):
            return "Must be true or false"

    elif input_type == "password":
        if not isinstance(value, str):
            return "Must be a string"
        v = input_def.get("validation", {})
        min_len = v.get("min_length", 1)
        if len(value) < min_len:
            return f"Must be at least {min_len} characters"
        # password fields are implicitly sensitive — the value must
        # never be logged, returned in plan state, or sent to frontend

    return None


def _validate_output(content: str, fmt: str) -> str | None:
    """Validate rendered template content against its declared format.

    Args:
        content: Rendered file content to check.
        fmt: One of ``"json"``, ``"yaml"``, ``"ini"``, ``"raw"``.

    Returns:
        Error message if invalid, or ``None`` if valid.
    """
    if fmt == "json":
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            return f"Invalid JSON: {exc}"

    elif fmt == "yaml":
        try:
            import yaml  # type: ignore[import-untyped]
            yaml.safe_load(content)
        except Exception as exc:
            return f"Invalid YAML: {exc}"

    elif fmt == "ini":
        import configparser
        parser = configparser.ConfigParser()
        try:
            parser.read_string(content)
        except configparser.Error as exc:
            return f"Invalid INI: {exc}"

    # "raw" → no validation
    return None


def _execute_config_step(
    step: dict,
    *,
    sudo_password: str = "",
) -> dict[str, Any]:
    """Write or modify a config file (write, append, ensure_line, template).

    Automatically creates a timestamped backup before any modification.

    Step format::

        {
            "type": "config",
            "action": "write",
            "path": "/etc/docker/daemon.json",
            "content": '{"features": {"buildkit": true}}',
            "needs_sudo": True,
            "backup": True,
        }

    The ``template`` action uses the full pipeline:
    validate inputs → render ``{var}`` placeholders → validate
    output format → write.
    """
    action = step.get("action", "write")
    path_str = step.get("path", "")
    if not path_str:
        return {"ok": False, "error": "No config path specified"}

    path = Path(path_str)
    backup = step.get("backup", True)

    # Backup existing file before modification
    if backup and path.exists():
        import time as _time
        ts = _time.strftime("%Y%m%d_%H%M%S")
        backup_path = f"{path}.bak.{ts}"
        bk_result = _run_subprocess(
            ["cp", "-p", str(path), backup_path],
            needs_sudo=step.get("needs_sudo", False),
            sudo_password=sudo_password,
            timeout=5,
        )
        if not bk_result["ok"]:
            logger.warning("Config backup failed for %s: %s", path, bk_result.get("error"))

    # ── Helper: apply mode/owner after write ─────────────────
    def _apply_file_attrs(
        target: str,
        step_data: dict,
        sp: str,
    ) -> None:
        """Apply chmod/chown if specified in step."""
        mode = step_data.get("mode")
        if mode:
            _run_subprocess(
                ["chmod", str(mode), target],
                needs_sudo=step_data.get("needs_sudo", False),
                sudo_password=sp,
                timeout=5,
            )
        owner = step_data.get("owner")
        if owner:
            _run_subprocess(
                ["chown", str(owner), target],
                needs_sudo=step_data.get("needs_sudo", False),
                sudo_password=sp,
                timeout=5,
            )

    if action == "write":
        content = step.get("content", "")
        # Write via tee (handles sudo correctly)
        if step.get("needs_sudo"):
            cmd = ["bash", "-c", f"echo '{content}' | sudo tee '{path_str}' > /dev/null"]
        else:
            cmd = ["bash", "-c", f"echo '{content}' > '{path_str}'"]
        result = _run_subprocess(
            cmd,
            needs_sudo=False,  # sudo is inside bash -c
            timeout=10,
        )
        if result["ok"]:
            _apply_file_attrs(path_str, step, sudo_password)
            result["message"] = f"Config written: {path_str}"
        return result

    elif action == "append":
        content = step.get("content", step.get("line", ""))
        cmd = ["bash", "-c", f"echo '{content}' >> '{path_str}'"]
        result = _run_subprocess(
            cmd,
            needs_sudo=step.get("needs_sudo", False),
            sudo_password=sudo_password,
            timeout=10,
        )
        if result["ok"]:
            _apply_file_attrs(path_str, step, sudo_password)
            result["message"] = f"Content appended to {path_str}"
        return result

    elif action == "ensure_line":
        line = step.get("line", step.get("content", ""))
        if not line:
            return {"ok": False, "error": "No line specified for ensure_line"}

        # Check if line already exists
        if path.exists():
            try:
                existing = path.read_text()
                if line in existing:
                    return {"ok": True, "message": "Line already present", "skipped": True}
            except PermissionError:
                # Try reading with sudo
                check = _run_subprocess(
                    ["grep", "-F", line, str(path)],
                    needs_sudo=step.get("needs_sudo", False),
                    sudo_password=sudo_password,
                    timeout=5,
                )
                if check["ok"]:
                    return {"ok": True, "message": "Line already present", "skipped": True}

        # Append the line
        cmd = ["bash", "-c", f"echo '{line}' >> '{path_str}'"]
        result = _run_subprocess(
            cmd,
            needs_sudo=step.get("needs_sudo", False),
            sudo_password=sudo_password,
            timeout=5,
        )
        if result["ok"]:
            _apply_file_attrs(path_str, step, sudo_password)
        return result

    elif action == "template":
        # Full template pipeline: validate → render → validate → write
        template_str = step.get("template", "")
        input_defs = step.get("inputs", [])
        input_values = step.get("input_values", {})
        fmt = step.get("format", "raw")

        # 1. Collect defaults for missing inputs
        for inp in input_defs:
            inp_id = inp.get("id", "")
            if inp_id and inp_id not in input_values:
                if "default" in inp:
                    input_values[inp_id] = inp["default"]

        # 2. Validate all inputs
        errors: list[str] = []
        for inp in input_defs:
            inp_id = inp.get("id", "")
            if inp_id in input_values:
                err = _validate_input(inp, input_values[inp_id])
                if err:
                    errors.append(f"{inp.get('label', inp_id)}: {err}")
        if errors:
            return {"ok": False, "error": f"Input validation failed: {'; '.join(errors)}"}

        # 3. Render template
        rendered = _render_template(template_str, input_values)

        # 3.5. Check for unresolved placeholders
        unresolved = _check_unsubstituted(rendered)
        if unresolved:
            return {
                "ok": False,
                "error": f"Unresolved template variables: {', '.join(f'{{{v}}}' for v in unresolved)}",
            }

        # 4. Validate output format
        fmt_err = _validate_output(rendered, fmt)
        if fmt_err:
            return {"ok": False, "error": f"Template output validation failed: {fmt_err}"}

        # 5. Write via the existing write path (preserves mode/owner)
        write_step = dict(step)
        write_step["action"] = "write"
        write_step["content"] = rendered
        return _execute_config_step(write_step, sudo_password=sudo_password)

    else:
        return {"ok": False, "error": f"Unknown config action: {action}"}


# ── Restart detection & batching ──

RESTART_TRIGGERS: dict[str, list[str]] = {
    "shell_restart": [
        "PATH modification",
        "Shell config change (.bashrc, .zshrc)",
        "New binary in non-standard directory",
    ],
    "service_restart": [
        "Config file changed",
        "Service installation",
        "Module loaded/unloaded",
    ],
    "reboot_required": [
        "Kernel module installed (DKMS)",
        "GPU driver installed",
        "Kernel updated",
        "Secure Boot key enrolled",
    ],
}


def detect_restart_needs(
    plan: dict,
    completed_steps: list[dict],
) -> dict:
    """Analyze completed plan steps to detect restart requirements.

    Returns::

        {
            "shell_restart": True/False,
            "service_restart": ["docker", "nginx"],
            "reboot_required": True/False,
            "reasons": ["PATH was modified — restart shell", ...],
        }
    """
    needs: dict = {
        "shell_restart": False,
        "service_restart": [],
        "reboot_required": False,
        "reasons": [],
    }

    # post_env means PATH changed → shell restart
    if plan.get("post_env"):
        needs["shell_restart"] = True
        needs["reasons"].append(
            "PATH was modified — restart shell to use new tools"
        )

    for step in completed_steps:
        # Config file change → service restart
        if step.get("type") == "config":
            service = step.get("restart_service")
            if service and service not in needs["service_restart"]:
                needs["service_restart"].append(service)
                needs["reasons"].append(
                    f"Config changed — restart {service}"
                )

        # Kernel module load → may need reboot
        if step.get("type") == "post_install":
            cmd = step.get("command", [])
            if cmd and cmd[0] == "modprobe":
                needs["reasons"].append(
                    f"Kernel module '{cmd[1] if len(cmd) > 1 else '?'}' loaded — reboot recommended"
                )

        # GPU driver → reboot
        if step.get("gpu_driver"):
            needs["reboot_required"] = True
            needs["reasons"].append(
                "GPU driver installed — reboot required"
            )

    return needs


def _batch_restarts(restart_needs: dict) -> list[dict]:
    """Convert restart_needs into minimal plan steps + notifications.

    Service restarts become service steps.
    Shell/reboot restarts become notification steps (never auto-executed).
    """
    steps: list[dict] = []

    # Deduplicate service restarts
    services = list(set(restart_needs.get("service_restart", [])))
    for svc in services:
        steps.append({
            "type": "service",
            "action": "restart",
            "service": svc,
            "needs_sudo": True,
            "label": f"Restart {svc}",
        })

    # Shell restart → notification (user must act)
    if restart_needs.get("shell_restart"):
        steps.append({
            "type": "notification",
            "message": "Restart your shell or run: source ~/.bashrc",
            "severity": "info",
        })

    # Reboot → notification (never auto-executed!)
    if restart_needs.get("reboot_required"):
        steps.append({
            "type": "notification",
            "message": "A system reboot is required for changes to take effect",
            "severity": "warning",
        })

    return steps


# ── Shell Config Step ───────────────────────────────────────────

_PROFILE_MAP: dict[str, dict[str, str]] = {
    "bash": {"rc_file": "~/.bashrc", "login_profile": "~/.bash_profile"},
    "zsh": {"rc_file": "~/.zshrc", "login_profile": "~/.zprofile"},
    "fish": {
        "rc_file": "~/.config/fish/config.fish",
        "login_profile": "~/.config/fish/config.fish",
    },
    "sh": {"rc_file": "~/.profile", "login_profile": "~/.profile"},
    "dash": {"rc_file": "~/.profile", "login_profile": "~/.profile"},
    "ash": {"rc_file": "~/.profile", "login_profile": "~/.profile"},
}


def _shell_config_line(
    shell_type: str,
    *,
    path_entry: str | None = None,
    env_var: tuple[str, str] | None = None,
) -> str:
    """Generate shell-specific PATH or env export line.

    Args:
        shell_type: ``"bash"`` | ``"zsh"`` | ``"fish"`` | etc.
        path_entry: Directory to add to PATH, e.g. ``"$HOME/.cargo/bin"``.
        env_var: Tuple of ``(name, value)`` e.g. ``("GOPATH", "$HOME/go")``.

    Returns:
        Shell-specific export line.
    """
    if shell_type == "fish":
        if path_entry:
            return f"set -gx PATH {path_entry} $PATH"
        if env_var:
            return f"set -gx {env_var[0]} {env_var[1]}"
    else:
        # POSIX (bash, zsh, sh, dash, ash)
        if path_entry:
            return f'export PATH="{path_entry}:$PATH"'
        if env_var:
            return f'export {env_var[0]}="{env_var[1]}"'
    return ""


def _execute_github_release_step(
    step: dict,
    *,
    sudo_password: str = "",
) -> dict[str, Any]:
    """Execute a github_release step — download + install a binary from GitHub.

    Step format::

        {
            "type": "github_release",
            "label": "Install lazygit",
            "repo": "jesseduffield/lazygit",
            "asset_pattern": "lazygit_{version}_Linux_{arch}.tar.gz",
            "binary_name": "lazygit",
            "install_dir": "/usr/local/bin",
            "version": "latest",
            "checksum": "sha256:...",
        }

    Supports tar.gz, zip, and raw binary assets.

    Returns:
        ``{"ok": True, "version": "...", "path": "..."}``
    """
    import urllib.request
    import tarfile
    import zipfile

    repo = step.get("repo", "")
    if not repo:
        return {"ok": False, "error": "No GitHub repo specified"}

    version = step.get("version", "latest")
    asset_pattern = step.get("asset_pattern", "")
    binary_name = step.get("binary_name", "")
    install_dir = step.get("install_dir", "/usr/local/bin")

    # Resolve the download URL
    resolved = _resolve_github_release_url(
        repo,
        asset_pattern=asset_pattern,
        version=version,
    )
    if not resolved.get("ok"):
        return resolved

    url = resolved["url"]
    asset_name = resolved.get("asset_name", "")
    actual_version = resolved.get("version", version)

    # Download to temp
    tmp_dir = Path(f"/tmp/gh_release_{repo.replace('/', '_')}")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_file = tmp_dir / asset_name

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "devops-cp/1.0"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            with open(tmp_file, "wb") as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
    except Exception as exc:
        return {"ok": False, "error": f"Download failed: {exc}"}

    # Checksum verify
    checksum = step.get("checksum", "")
    if checksum:
        if not _verify_checksum(tmp_file, checksum):
            return {
                "ok": False,
                "error": f"Checksum mismatch for {asset_name}",
            }

    # Extract or copy
    extract_dir = tmp_dir / "extracted"
    extract_dir.mkdir(exist_ok=True)

    if asset_name.endswith(".tar.gz") or asset_name.endswith(".tgz"):
        try:
            with tarfile.open(tmp_file, "r:gz") as tf:
                tf.extractall(extract_dir)
        except Exception as exc:
            return {"ok": False, "error": f"Extract failed: {exc}"}
    elif asset_name.endswith(".zip"):
        try:
            with zipfile.ZipFile(tmp_file, "r") as zf:
                zf.extractall(extract_dir)
        except Exception as exc:
            return {"ok": False, "error": f"Extract failed: {exc}"}
    else:
        # Raw binary — just copy
        import shutil as _sh
        _sh.copy2(tmp_file, extract_dir / (binary_name or asset_name))

    # Find the binary
    if binary_name:
        # Search for the binary in extracted files
        found = None
        for p in extract_dir.rglob(binary_name):
            if p.is_file():
                found = p
                break
        if not found:
            # Might be the direct file
            direct = extract_dir / binary_name
            if direct.is_file():
                found = direct

        if not found:
            available = [str(p.name) for p in extract_dir.rglob("*") if p.is_file()]
            return {
                "ok": False,
                "error": f"Binary '{binary_name}' not found in release archive",
                "available_files": available[:10],
            }
    else:
        # If no binary_name, pick the first executable
        found = None
        for p in extract_dir.rglob("*"):
            if p.is_file() and os.access(p, os.X_OK):
                found = p
                break
        if not found:
            return {"ok": False, "error": "No executable found in archive"}

    # Make executable
    os.chmod(found, 0o755)

    # Install to target dir
    target = Path(install_dir) / (binary_name or found.name)
    needs_sudo = step.get("needs_sudo", not os.access(install_dir, os.W_OK))

    if needs_sudo:
        result = _run_subprocess(
            ["cp", str(found), str(target)],
            needs_sudo=True,
            sudo_password=sudo_password,
            timeout=10,
        )
        if not result.get("ok"):
            return result
        # Make sure it's executable
        _run_subprocess(
            ["chmod", "+x", str(target)],
            needs_sudo=True,
            sudo_password=sudo_password,
            timeout=5,
        )
    else:
        import shutil as _sh
        _sh.copy2(str(found), str(target))
        os.chmod(target, 0o755)

    # Cleanup temp
    import shutil as _sh
    _sh.rmtree(tmp_dir, ignore_errors=True)

    return {
        "ok": True,
        "version": actual_version,
        "path": str(target),
        "asset": asset_name,
    }


def _execute_shell_config_step(
    step: dict,
) -> dict[str, Any]:
    """Execute a shell_config step — write PATH/env to shell profile.

    The step dict can have:
        - ``file``: Explicit profile path (overrides auto-detection)
        - ``line``: Explicit line to write
        - ``path_append``: List of dirs to add to PATH
        - ``env_vars``: Dict of env vars to export
        - ``shell_type``: Override detected shell type

    Writes are IDEMPOTENT — lines already present are skipped.

    Spec: domain-shells §Phase 4 shell_config.

    Returns:
        ``{"ok": True, "lines_added": N, ...}``
    """
    # Determine shell type
    shell_type = step.get("shell_type", "")
    if not shell_type:
        shell_env = os.environ.get("SHELL", "/bin/bash")
        shell_type = os.path.basename(shell_env)

    # Determine target file
    target_file = step.get("file", "")
    if not target_file:
        profile_info = _PROFILE_MAP.get(shell_type, _PROFILE_MAP["sh"])
        target_file = profile_info["rc_file"]

    target_path = os.path.expanduser(target_file)

    # Collect lines to write
    lines_to_add: list[str] = []

    # Explicit line
    if step.get("line"):
        lines_to_add.append(step["line"])

    # path_append entries
    for path_entry in step.get("path_append", []):
        lines_to_add.append(_shell_config_line(
            shell_type, path_entry=path_entry,
        ))

    # env_vars
    for var_name, var_value in step.get("env_vars", {}).items():
        lines_to_add.append(_shell_config_line(
            shell_type, env_var=(var_name, var_value),
        ))

    if not lines_to_add:
        return {"ok": True, "lines_added": 0, "note": "nothing to add"}

    # Read existing content (for idempotency check)
    existing_content = ""
    if os.path.isfile(target_path):
        try:
            with open(target_path) as f:
                existing_content = f.read()
        except OSError:
            pass

    # Filter out lines already present
    new_lines = [ln for ln in lines_to_add if ln.strip() and ln not in existing_content]

    if not new_lines:
        return {
            "ok": True,
            "lines_added": 0,
            "file": target_file,
            "note": "all lines already present",
        }

    # Backup before writing
    if os.path.isfile(target_path):
        import shutil as _shutil
        backup = f"{target_path}.backup.{int(time.time())}"
        try:
            _shutil.copy2(target_path, backup)
        except OSError:
            pass

    # Ensure parent directories exist
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    # Append lines
    try:
        with open(target_path, "a") as f:
            if existing_content and not existing_content.endswith("\n"):
                f.write("\n")
            f.write(f"\n# Added by devops-control-plane\n")
            for ln in new_lines:
                f.write(f"{ln}\n")
    except OSError as exc:
        return {"ok": False, "error": f"Failed to write {target_file}: {exc}"}

    return {
        "ok": True,
        "lines_added": len(new_lines),
        "file": target_file,
        "shell_type": shell_type,
        "lines": new_lines,
    }


def _execute_notification_step(step: dict) -> dict[str, Any]:
    """Handle a notification step (no-op with message pass-through).

    Notifications are informational. They always succeed.
    The frontend displays them to the user.
    """
    return {
        "ok": True,
        "message": step.get("message", ""),
        "severity": step.get("severity", "info"),
        "notification": True,
    }


# ── Rollback system ───────────────────────────────────────────

UNDO_COMMANDS: dict[str, dict] = {
    "pip": {
        "command": ["pip", "uninstall", "-y", "{package}"],
        "needs_sudo": False,
    },
    "pip_global": {
        "command": ["pip", "uninstall", "-y", "{package}"],
        "needs_sudo": True,
    },
    "apt": {
        "command": ["apt-get", "purge", "-y", "{package}"],
        "needs_sudo": True,
    },
    "dnf": {
        "command": ["dnf", "remove", "-y", "{package}"],
        "needs_sudo": True,
    },
    "pacman": {
        "command": ["pacman", "-Rns", "--noconfirm", "{package}"],
        "needs_sudo": True,
    },
    "apk": {
        "command": ["apk", "del", "{package}"],
        "needs_sudo": True,
    },
    "brew": {
        "command": ["brew", "uninstall", "{package}"],
        "needs_sudo": False,
    },
    "snap": {
        "command": ["snap", "remove", "{package}"],
        "needs_sudo": True,
    },
    "npm": {
        "command": ["npm", "uninstall", "-g", "{package}"],
        "needs_sudo": False,
    },
    "cargo": {
        "command": ["cargo", "uninstall", "{package}"],
        "needs_sudo": False,
    },
    "go": {
        "command": ["rm", "{binary_path}"],
        "needs_sudo": False,
    },
    "binary": {
        "command": ["rm", "{install_path}"],
        "needs_sudo": True,
    },
    "systemctl_enable": {
        "command": ["systemctl", "disable", "{service}"],
        "needs_sudo": True,
    },
    "systemctl_start": {
        "command": ["systemctl", "stop", "{service}"],
        "needs_sudo": True,
    },
}


def _generate_rollback(completed_steps: list[dict]) -> list[dict]:
    """Generate a rollback plan from completed steps (reverse order).

    For each completed step that has a ``rollback`` field, the
    rollback instruction is added to the list. Steps without
    rollback data are skipped.

    Args:
        completed_steps: List of step dicts that completed successfully.

    Returns:
        Ordered list of rollback step dicts (reverse of execution order).
    """
    rollback: list[dict] = []
    for step in reversed(completed_steps):
        rb = step.get("rollback")
        if rb:
            rollback.append(rb)
    return rollback


def _execute_rollback(
    rollback_steps: list[dict],
    *,
    sudo_password: str = "",
) -> dict[str, Any]:
    """Execute rollback steps with best-effort error handling.

    Runs each rollback step in order. If a step fails, it is
    logged but does NOT stop the remainder of the rollback.

    Args:
        rollback_steps: List of rollback step dicts with
                        ``command``, ``needs_sudo``, ``description``.
        sudo_password: Optional sudo password.

    Returns:
        Summary dict with ``ok``, ``steps_run``, ``steps_failed``,
        ``errors``.
    """
    results: list[dict] = []
    errors: list[str] = []

    for rb_step in rollback_steps:
        cmd = rb_step.get("command", [])
        desc = rb_step.get("description", " ".join(cmd) if cmd else "unknown")
        logger.info("Rollback step: %s", desc)

        if not cmd:
            errors.append(f"No command for rollback step: {desc}")
            continue

        result = _run_subprocess(
            cmd,
            needs_sudo=rb_step.get("needs_sudo", False),
            sudo_password=sudo_password,
            timeout=rb_step.get("timeout", 30),
        )
        results.append({"description": desc, **result})
        if not result["ok"]:
            errors.append(f"Rollback step failed: {desc} — {result.get('error', '')}")
            logger.warning("Rollback step failed: %s — %s", desc, result.get("error"))

    return {
        "ok": len(errors) == 0,
        "steps_run": len(results),
        "steps_failed": len(errors),
        "errors": errors,
        "results": results,
    }


# ── State persistence ──────────────────────────────────────────
#
# Spec: domain-restart §State Persistence, §Plan Engine State Machine.
#
# Plans can be paused (restart_required) and resumed later.
# State is saved as JSON in ~/.local/share/devops-control-plane/plans/.
# On startup, the frontend checks for pending plans and offers resume.

from pathlib import Path
import uuid as _uuid_mod


def _plan_state_dir() -> Path:
    """Resolve and lazily create the plan state directory.

    Uses ``<project_root>/.state/install_plans/`` following the
    project's standard ``.state/`` convention for ephemeral data.

    Falls back to ``~/.local/share/devops-control-plane/plans/``
    if no project root can be determined.

    Returns:
        Absolute path to the state directory.
    """
    # Try to resolve project root from Flask app context
    try:
        from flask import current_app
        root = Path(current_app.config["PROJECT_ROOT"])
    except (ImportError, RuntimeError, KeyError):
        # Outside Flask context — try env var or fallback
        import os
        root_env = os.environ.get("DEVOPS_CP_ROOT")
        if root_env:
            root = Path(root_env)
        else:
            root = Path.home() / ".local" / "share" / "devops-control-plane"

    d = root / ".state" / "install_plans"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_plan_state(state: dict) -> Path:
    """Write plan state to disk.

    The ``state`` dict **must** contain ``plan_id`` (string).
    If missing, one is generated.

    **Sensitive fields** (password input values) are stripped before
    persistence — they must never be written to disk in plaintext.

    Args:
        state: Plan state dict matching the schema defined in
               domain-restart §State Persistence.

    Returns:
        Path to the written JSON file.
    """
    if "plan_id" not in state:
        state["plan_id"] = str(_uuid_mod.uuid4())

    import datetime as _dt

    state.setdefault("updated_at", _dt.datetime.now(_dt.timezone.utc).isoformat())

    # Strip sensitive values before persisting
    safe_state = json.loads(json.dumps(state, default=str))
    for step in safe_state.get("plan", {}).get("steps", []):
        if step.get("type") == "config" and step.get("action") == "template":
            for inp in step.get("inputs", []):
                if inp.get("type") == "password":
                    inp_id = inp.get("id", "")
                    iv = step.get("input_values", {})
                    if inp_id in iv:
                        iv[inp_id] = "***REDACTED***"

    path = _plan_state_dir() / f"{safe_state['plan_id']}.json"
    path.write_text(json.dumps(safe_state, indent=2, default=str))
    logger.info("Plan state saved: %s", path)
    return path


def load_plan_state(plan_id: str) -> dict | None:
    """Load a plan state from disk.

    Args:
        plan_id: UUID string identifying the plan.

    Returns:
        Plan state dict, or ``None`` if the file doesn't exist
        or is corrupt.
    """
    path = _plan_state_dir() / f"{plan_id}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load plan state %s: %s", plan_id, exc)
        return None


def list_pending_plans() -> list[dict]:
    """Find all paused or pending plans on disk.

    Returns:
        List of plan state dicts whose status is ``"paused"``
        or ``"running"`` (crashed mid-run).
    """
    results: list[dict] = []
    state_dir = _plan_state_dir()
    for f in state_dir.glob("*.json"):
        try:
            plan = json.loads(f.read_text())
            if plan.get("status") in ("paused", "running", "failed"):
                results.append(plan)
        except (json.JSONDecodeError, OSError):
            logger.debug("Skipping corrupt plan file: %s", f)
    return results


def cancel_plan(plan_id: str) -> bool:
    """Mark a paused plan as cancelled.

    Args:
        plan_id: UUID string identifying the plan.

    Returns:
        True if the plan was found and cancelled.
    """
    import datetime as _dt

    state = load_plan_state(plan_id)
    if state is None:
        return False
    state["status"] = "cancelled"
    state["cancelled_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    save_plan_state(state)
    return True


def resume_plan(plan_id: str) -> dict:
    """Resume a paused or failed plan from its last completed step.

    Loads the saved state, skips already-completed steps, and returns
    a new plan dict containing only the remaining steps. The returned
    plan can be fed directly into ``execute_plan_step()`` or the
    SSE execute endpoint.

    Args:
        plan_id: UUID string identifying the plan.

    Returns:
        Plan dict with ``steps`` containing only unfinished steps,
        plus ``plan_id`` and ``resumed: True``.
        Returns ``{"error": "..."}`` if the plan can't be resumed.
    """
    state = load_plan_state(plan_id)
    if state is None:
        return {"error": f"Plan '{plan_id}' not found"}

    status = state.get("status", "")
    if status == "done":
        return {"error": f"Plan '{plan_id}' already completed"}
    if status == "cancelled":
        return {"error": f"Plan '{plan_id}' was cancelled"}

    all_steps = state.get("steps", [])
    completed = set(state.get("completed_steps", []))

    # Filter to remaining steps
    remaining_steps = [
        s for i, s in enumerate(all_steps)
        if i not in completed
    ]

    if not remaining_steps:
        return {"error": f"Plan '{plan_id}' has no remaining steps"}

    # Mark the state as resuming
    import datetime as _dt
    state["status"] = "running"
    state["resumed_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    save_plan_state(state)

    return {
        "tool": state.get("tool", ""),
        "label": state.get("tool", ""),
        "plan_id": plan_id,
        "resumed": True,
        "steps": remaining_steps,
        "original_total": len(all_steps),
        "completed_count": len(completed),
    }


def archive_plan(plan_id: str) -> bool:
    """Move a completed or cancelled plan to the archive subdirectory.

    Args:
        plan_id: UUID string identifying the plan.

    Returns:
        True if the plan was found and archived.
    """
    src = _plan_state_dir() / f"{plan_id}.json"
    if not src.is_file():
        return False
    archive_dir = _plan_state_dir() / "archive"
    archive_dir.mkdir(exist_ok=True)
    dst = archive_dir / f"{plan_id}.json"
    src.rename(dst)
    logger.info("Plan archived: %s → %s", src, dst)
    return True


# ── DAG execution engine ──────────────────────────────────────
#
# Spec: Phase 8 §DAG Execution Engine.
#
# Steps with `depends_on` run after their dependencies complete.
# Independent steps run in parallel (using threads).
# Package manager steps are serialized (PM lock conflicts).
# Falls back to linear order for steps without `depends_on`.


def _add_implicit_deps(steps: list[dict]) -> list[dict]:
    """Add implicit linear dependencies for steps missing ``depends_on``.

    If a step has no ``depends_on`` field, it gets an implicit
    dependency on the previous step. This preserves backward
    compatibility with linear plans.

    Also auto-generates ``id`` fields if missing.

    Args:
        steps: Mutable list of step dicts (modified in place).

    Returns:
        The same list, with ``id`` and ``depends_on`` populated.
    """
    for i, step in enumerate(steps):
        if "id" not in step:
            step["id"] = f"step_{i}"
        if "depends_on" not in step:
            step["depends_on"] = [steps[i - 1]["id"]] if i > 0 else []
    return steps


def _validate_dag(steps: list[dict]) -> list[str]:
    """Validate the step dependency DAG.

    Checks for:
    - Duplicate step IDs
    - References to non-existent step IDs
    - Cycles (Kahn's algorithm)

    Args:
        steps: Steps with ``id`` and ``depends_on`` populated.

    Returns:
        List of error strings (empty = valid).
    """
    errors: list[str] = []
    ids = {s["id"] for s in steps}

    # Duplicate IDs
    seen: set[str] = set()
    for s in steps:
        if s["id"] in seen:
            errors.append(f"Duplicate step ID: {s['id']}")
        seen.add(s["id"])

    # Missing refs
    for s in steps:
        for dep in s.get("depends_on", []):
            if dep not in ids:
                errors.append(
                    f"Step '{s['id']}' depends on unknown step '{dep}'"
                )

    if errors:
        return errors

    # Cycle detection (Kahn's algorithm)
    in_degree: dict[str, int] = {s["id"]: 0 for s in steps}
    for s in steps:
        for dep in s.get("depends_on", []):
            in_degree[s["id"]] += 1

    queue = [sid for sid, deg in in_degree.items() if deg == 0]
    processed = 0
    # Build adjacency: dep → list of steps that depend on it
    adj: dict[str, list[str]] = {s["id"]: [] for s in steps}
    for s in steps:
        for dep in s.get("depends_on", []):
            adj[dep].append(s["id"])

    while queue:
        node = queue.pop(0)
        processed += 1
        for successor in adj[node]:
            in_degree[successor] -= 1
            if in_degree[successor] == 0:
                queue.append(successor)

    if processed < len(steps):
        errors.append("Dependency cycle detected in plan steps")

    return errors


def _get_ready_steps(
    steps: list[dict],
    completed: set[str],
    running: set[str],
) -> list[dict]:
    """Find steps whose dependencies are all completed.

    Args:
        steps: All plan steps.
        completed: Set of completed step IDs.
        running: Set of currently running step IDs.

    Returns:
        Steps that are ready to execute.
    """
    ready: list[dict] = []
    done_or_running = completed | running
    for step in steps:
        sid = step["id"]
        if sid in done_or_running:
            continue
        deps = step.get("depends_on", [])
        if all(d in completed for d in deps):
            ready.append(step)
    return ready


def _get_step_pm(step: dict) -> str | None:
    """Extract the package manager from a step's command.

    Used to prevent parallel execution of steps that use the
    same package manager (which holds a lock).

    Returns:
        Package manager name, or None if not a PM step.
    """
    cmd = step.get("command", [])
    if not cmd:
        return None
    binary = cmd[0] if isinstance(cmd, list) else cmd.split()[0]
    if binary in ("apt-get", "apt", "dpkg"):
        return "apt"
    if binary in ("dnf", "yum"):
        return "dnf"
    if binary in ("apk",):
        return "apk"
    if binary in ("pacman",):
        return "pacman"
    if binary in ("zypper",):
        return "zypper"
    if binary in ("snap",):
        return "snap"
    if binary in ("brew",):
        return "brew"
    return None


def _enforce_parallel_safety(steps: list[dict]) -> list[dict]:
    """Filter parallel steps to avoid package manager lock conflicts.

    Same-PM steps are serialized: only the first from each PM group
    is kept. Non-PM steps can all run in parallel.

    Args:
        steps: Candidate steps for parallel execution.

    Returns:
        Subset of steps that are safe to run concurrently.
    """
    pm_seen: set[str] = set()
    safe: list[dict] = []

    for step in steps:
        pm = _get_step_pm(step)
        if pm:
            if pm in pm_seen:
                continue  # Skip — same PM already running
            pm_seen.add(pm)
        safe.append(step)

    return safe


def execute_plan_dag(
    plan: dict,
    *,
    sudo_password: str = "",
    on_progress: Any = None,
) -> dict[str, Any]:
    """Execute a plan with DAG-aware parallel step support.

    Steps with ``depends_on`` run after their dependencies.
    Independent steps run concurrently (via threads).
    Package manager steps are serialized to avoid lock conflicts.

    Falls back to linear execution for plans without ``depends_on``.

    Spec: Phase 8 §DAG Execution Engine.

    Args:
        plan: Install plan from ``resolve_install_plan()``.
        sudo_password: Password for sudo steps.
        on_progress: Optional callback ``(step_id, status)`` for
                     progress reporting.

    Returns:
        ``{"ok": True, "completed": [...], ...}`` on full success,
        ``{"ok": False, "failed": [...], ...}`` on any failure.
    """
    import concurrent.futures

    steps = list(plan["steps"])  # Shallow copy
    steps = _add_implicit_deps(steps)

    # Validate DAG
    dag_errors = _validate_dag(steps)
    if dag_errors:
        return {"ok": False, "error": f"Invalid plan: {', '.join(dag_errors)}"}

    # Build step lookup
    step_by_id = {s["id"]: s for s in steps}

    completed: set[str] = set()
    failed: set[str] = set()
    results: dict[str, dict] = {}

    plan_id = plan.get("plan_id", str(_uuid_mod.uuid4()))

    while len(completed) + len(failed) < len(steps):
        ready = _get_ready_steps(steps, completed, set())

        if not ready:
            # All remaining steps are blocked by failures
            break

        # Filter out steps blocked by failed dependencies
        runnable: list[dict] = []
        for step in ready:
            deps = step.get("depends_on", [])
            if any(d in failed for d in deps):
                failed.add(step["id"])
                results[step["id"]] = {
                    "ok": False, "skipped": True,
                    "reason": "dependency failed",
                }
                if on_progress:
                    on_progress(step["id"], "skipped")
                continue
            runnable.append(step)

        if not runnable:
            break

        # Check parallelism safety
        if len(runnable) > 1:
            runnable = _enforce_parallel_safety(runnable)

        # Execute: single step → inline, multiple → threaded
        if len(runnable) == 1:
            step = runnable[0]
            if on_progress:
                on_progress(step["id"], "started")
            result = execute_plan_step(step, sudo_password=sudo_password)
            results[step["id"]] = result

            if result.get("ok"):
                completed.add(step["id"])
                if on_progress:
                    on_progress(step["id"], "done")
            else:
                failed.add(step["id"])
                if on_progress:
                    on_progress(step["id"], "failed")

            # Check restart_required — pause plan
            if result.get("ok") and step.get("restart_required"):
                save_plan_state({
                    "plan_id": plan_id,
                    "tool": plan.get("tool", ""),
                    "status": "paused",
                    "pause_reason": f"{step['restart_required']}_restart",
                    "current_step": step["id"],
                    "completed_steps": list(completed),
                    "steps": steps,
                })
                return {
                    "ok": False,
                    "paused": True,
                    "pause_reason": step["restart_required"],
                    "pause_message": step.get(
                        "restart_message",
                        f"A {step['restart_required']} restart is required.",
                    ),
                    "plan_id": plan_id,
                    "completed": list(completed),
                    "results": results,
                }
        else:
            # Parallel execution via thread pool
            def _exec_step(s: dict) -> tuple[dict, dict]:
                """Execute a single step, returning (step, result)."""
                return s, execute_plan_step(s, sudo_password=sudo_password)

            for step in runnable:
                if on_progress:
                    on_progress(step["id"], "started")

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=len(runnable),
            ) as pool:
                futures = {
                    pool.submit(_exec_step, s): s for s in runnable
                }
                for future in concurrent.futures.as_completed(futures):
                    step, result = future.result()
                    results[step["id"]] = result
                    if result.get("ok"):
                        completed.add(step["id"])
                        if on_progress:
                            on_progress(step["id"], "done")
                    else:
                        failed.add(step["id"])
                        if on_progress:
                            on_progress(step["id"], "failed")

    # Save final state
    final_status = "done" if not failed else "failed"
    save_plan_state({
        "plan_id": plan_id,
        "tool": plan.get("tool", ""),
        "status": final_status,
        "completed_steps": list(completed),
        "failed_steps": list(failed),
        "steps": steps,
    })

    return {
        "ok": len(failed) == 0,
        "plan_id": plan_id,
        "completed": list(completed),
        "failed": list(failed),
        "results": results,
    }


# ── Plan step dispatcher ───────────────────────────────────────


def execute_plan_step(
    step: dict,
    *,
    sudo_password: str = "",
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute a single plan step by dispatching on ``step["type"]``.

    Args:
        step: Single step dict from ``plan["steps"]``.
        sudo_password: Sudo password if ``step["needs_sudo"]``.
        env_overrides: Extra env vars (e.g. PATH from ``post_env``).

    Returns:
        ``{"ok": True, ...}`` on success,
        ``{"ok": False, ...}`` on failure.
    """
    step_type = step.get("type", "tool")

    # ── High-risk safeguard: backup before execution ──
    if step.get("risk") == "high" and step.get("backup_before"):
        backed_up = _backup_before_step(step, sudo_password=sudo_password)
        if not backed_up and step.get("backup_before"):
            logger.warning(
                "High-risk step '%s' has backup_before but no backups were created",
                step.get("label", "?"),
            )

    if step_type == "packages":
        return _execute_package_step(step, sudo_password=sudo_password)
    elif step_type == "repo_setup":
        return _execute_repo_step(step, sudo_password=sudo_password)
    elif step_type == "tool":
        return _execute_command_step(
            step, sudo_password=sudo_password, env_overrides=env_overrides,
        )
    elif step_type == "post_install":
        # ── SecureBoot check before modprobe ──
        cmd = step.get("command", [])
        if cmd and len(cmd) >= 1 and cmd[0] == "modprobe":
            sb = _detect_secure_boot()
            if sb is True:
                module_name = cmd[1] if len(cmd) > 1 else "unknown"
                return {
                    "ok": False,
                    "error": (
                        f"SecureBoot is enabled. Loading unsigned kernel module "
                        f"'{module_name}' will fail. Either disable SecureBoot "
                        f"in BIOS or sign the module with MOK (Machine Owner Key)."
                    ),
                    "secure_boot": True,
                    "remediation": [
                        "Option 1: Disable SecureBoot in BIOS/UEFI settings",
                        f"Option 2: Sign the module: sudo mokutil --import /path/to/{module_name}.der",
                        "Option 3: Use DKMS which handles signing automatically (if configured)",
                    ],
                }
        return _execute_command_step(
            step, sudo_password=sudo_password, env_overrides=env_overrides,
        )
    elif step_type == "verify":
        return _execute_verify_step(step, env_overrides=env_overrides)
    # ── Phase 5: Build-from-source step types ──
    elif step_type == "source":
        return _execute_source_step(step, sudo_password=sudo_password)
    elif step_type == "build":
        return _execute_build_step(
            step, sudo_password=sudo_password, env_overrides=env_overrides,
        )
    elif step_type == "install":
        return _execute_install_step(
            step, sudo_password=sudo_password, env_overrides=env_overrides,
        )
    elif step_type == "cleanup":
        return _execute_cleanup_step(step)
    # ── Phase 7: Data pack step type ──
    elif step_type == "download":
        return _execute_download_step(step)
    # ── Phase 8: System config step types ──
    elif step_type == "service":
        return _execute_service_step(step, sudo_password=sudo_password)
    elif step_type == "config":
        return _execute_config_step(step, sudo_password=sudo_password)
    elif step_type == "notification":
        return _execute_notification_step(step)
    elif step_type == "shell_config":
        return _execute_shell_config_step(step)
    elif step_type == "github_release":
        return _execute_github_release_step(step, sudo_password=sudo_password)
    else:
        return {"ok": False, "error": f"Unknown step type: {step_type}"}


# ── Plan execution engine ──────────────────────────────────────


def execute_plan(
    plan: dict,
    *,
    sudo_password: str = "",
    start_from: int = 0,
) -> dict[str, Any]:
    """Execute an install plan step by step.

    Runs each step in order, accumulates ``post_env`` for subsequent
    steps, logs progress via ``_audit()``, and handles partial
    failures with remediation analysis.

    Args:
        plan: Install plan from ``resolve_install_plan()``.
        sudo_password: Sudo password for steps that need it.
            Piped to each sudo step — password entered ONCE by
            the user, reused for all sudo steps in the plan
            (per domain-sudo-security §password flow).
        start_from: Step index to resume from (for retry after
            partial failure).  Steps before this index are skipped.

    Returns:
        ``{"ok": True, "tool": "...", "steps_completed": N, ...}``
        on success,
        ``{"ok": False, "error": "...", "step": N, ...}`` on failure.
    """
    tool = plan["tool"]
    steps = plan["steps"]
    post_env = plan.get("post_env", {})
    completed = []
    env_overrides: dict[str, str] = {}

    for i, step in enumerate(steps):
        # Skip already-completed steps (resume support)
        if i < start_from:
            continue

        step_label = step.get("label", f"Step {i + 1}")
        step_type = step.get("type", "tool")

        _audit(
            f"🔧 Plan Step {i + 1}/{len(steps)}",
            f"{tool}: {step_label}",
            action="started",
            target=tool,
        )

        # Accumulate env overrides for tool/post_install/verify steps
        # post_env applies AFTER a tool step installs to a non-standard
        # PATH (e.g. cargo → ~/.cargo/bin).  Applied to the step that
        # produces the env AND all subsequent steps.
        if step_type in ("tool", "post_install", "verify") and post_env:
            env_overrides.update(post_env)

        result = execute_plan_step(
            step,
            sudo_password=sudo_password,
            env_overrides=env_overrides if env_overrides else None,
        )

        # ── Skipped (already satisfied) ──
        if result.get("skipped"):
            _audit(
                "⏭️ Step Skipped",
                f"{tool}: {step_label} (already satisfied)",
                action="skipped",
                target=tool,
            )
            completed.append({
                "step": i, "label": step_label, "skipped": True,
            })
            continue

        # ── Failure ──
        if not result["ok"]:
            # Sudo needed — propagate to caller for password prompt
            if result.get("needs_sudo"):
                return {
                    "ok": False,
                    "needs_sudo": True,
                    "error": result["error"],
                    "step": i,
                    "step_label": step_label,
                    "completed": completed,
                }

            # Step failed — try remediation analysis for tool steps
            remediation = None
            if step_type == "tool":
                remediation = _analyse_install_failure(
                    tool, plan.get("cli", tool),
                    result.get("stderr", ""),
                )

            _audit(
                "❌ Step Failed",
                f"{tool}: {step_label} — {result['error']}",
                action="failed",
                target=tool,
                detail={
                    "step": i,
                    "stderr": result.get("stderr", "")[:500],
                },
            )

            # ── Auto-rollback for completed steps ──
            rollback_plan = _generate_rollback(
                [s for s in steps[:i] if s.get("rollback")]
            )

            # Risk-based failure response
            step_risk = step.get("risk", "low")
            auto_rollback_result = None
            if step_risk == "medium" and step.get("rollback"):
                # Auto-rollback the failed step itself
                auto_rollback_result = _execute_rollback(
                    [step["rollback"]],
                    sudo_password=sudo_password,
                )

            response: dict[str, Any] = {
                "ok": False,
                "error": result["error"],
                "step": i,
                "step_label": step_label,
                "completed": completed,
                "stderr": result.get("stderr", ""),
                "rollback_plan": rollback_plan,
            }
            if remediation:
                response["remediation"] = remediation
            if auto_rollback_result:
                response["auto_rollback"] = auto_rollback_result
            if step_risk == "high" and step.get("rollback", {}).get("manual_instructions"):
                response["manual_instructions"] = step["rollback"]["manual_instructions"]
            return response

        # ── Success ──
        _audit(
            "✅ Step Done",
            f"{tool}: {step_label}",
            action="completed",
            target=tool,
        )
        completed.append({
            "step": i,
            "label": step_label,
            "elapsed_ms": result.get("elapsed_ms"),
        })

        # ── Restart check — pause plan if step requires restart ──
        restart_level = step.get("restart_required")
        if restart_level:
            plan_id = plan.get("plan_id", str(_uuid_mod.uuid4()))
            save_plan_state({
                "plan_id": plan_id,
                "tool": tool,
                "status": "paused",
                "pause_reason": f"{restart_level}_restart",
                "current_step": i,
                "resume_from": i + 1,
                "steps": [
                    {
                        "id": j,
                        "label": s.get("label", f"Step {j + 1}"),
                        "status": "done" if j <= i else "pending",
                    }
                    for j, s in enumerate(steps)
                ],
                "rollback_plan": _generate_rollback(
                    [steps[j] for j in range(i + 1)]
                ),
                "plan": plan,
            })
            _audit(
                "⏸️ Plan Paused",
                f"{tool}: restart required ({restart_level})",
                action="paused",
                target=tool,
            )
            return {
                "ok": False,
                "paused": True,
                "pause_reason": restart_level,
                "pause_message": step.get(
                    "restart_message",
                    f"A {restart_level} restart is required.",
                ),
                "plan_id": plan_id,
                "resume_from": i + 1,
                "step": i,
                "step_label": step_label,
                "completed": completed,
            }

    # ── All steps complete ──
    _audit(
        "✅ Tool Installed",
        f"{tool}: all {len(steps)} steps completed",
        action="installed",
        target=tool,
    )

    return {
        "ok": True,
        "tool": tool,
        "message": f"{tool} installed successfully",
        "steps_completed": len(completed),
        "completed": completed,
        "invalidates": ["l0_detection", "system_deps", "tool_status"],
    }


# ── Public API ──────────────────────────────────────────────────


def install_tool(
    tool: str,
    *,
    cli: str = "",
    sudo_password: str = "",
    override_command: list[str] | None = None,
) -> dict[str, Any]:
    """Install a missing devops tool — backward-compatible wrapper.

    Generates a plan via ``resolve_install_plan()``, then executes
    it via ``execute_plan()``.  Existing callers don't need changes.

    For override commands (remediation), uses ``_run_subprocess()``
    directly — no plan needed.

    Args:
        tool: Tool name (e.g. ``"helm"``, ``"ruff"``).
        cli: CLI binary name to check (defaults to *tool*).
        sudo_password: Password for sudo, required for system packages.
        override_command: If provided, run this command instead of
            the recipe.  Used by remediation options.

    Returns:
        ``{"ok": True, "message": "...", ...}`` on success,
        ``{"ok": False, "error": "...", ...}`` on failure,
        ``{"ok": False, "needs_sudo": True, ...}`` when password needed.
    """
    tool = tool.lower().strip()
    cli = (cli or tool).strip()

    if not tool:
        return {"ok": False, "error": "No tool specified"}

    # ── Override command (remediation path) ──
    # Direct execution — no plan, no dependency walk.
    if override_command:
        _audit(
            "🔧 Tool Install (override)",
            f"{tool}: custom command",
            action="started",
            target=tool,
        )
        result = _run_subprocess(
            override_command,
            needs_sudo=False,
            timeout=120,
        )
        if result["ok"]:
            installed = shutil.which(cli) is not None
            result["message"] = (
                f"{tool} installed successfully"
                if installed
                else f"Command succeeded but '{cli}' not found in PATH yet"
                " — you may need to restart your shell"
            )
            result["installed"] = installed
            _audit(
                "✅ Tool Installed",
                result["message"],
                action="installed",
                target=tool,
            )
        else:
            remediation = _analyse_install_failure(
                tool, cli, result.get("stderr", ""),
            )
            if remediation:
                result["remediation"] = remediation
            _audit(
                "❌ Tool Install Failed",
                f"{tool}: {result['error']}",
                action="failed",
                target=tool,
            )
        return result

    # ── Plan-based execution ──
    from src.core.services.audit.l0_detection import _detect_os

    system_profile = _detect_os()
    plan = resolve_install_plan(tool, system_profile)

    # Resolution failed?
    if plan.get("error"):
        _audit(
            "🔧 Tool Install — No Plan",
            f"{tool}: {plan['error']}",
            action="failed",
            target=tool,
        )
        return {"ok": False, "error": plan["error"]}

    # Already installed?
    if plan.get("already_installed"):
        _audit(
            "🔧 Tool Already Installed",
            f"{tool} is already available",
            action="checked",
            target=tool,
        )
        return {
            "ok": True,
            "message": f"{tool} is already installed",
            "already_installed": True,
        }

    # Execute the plan
    return execute_plan(plan, sudo_password=sudo_password)
