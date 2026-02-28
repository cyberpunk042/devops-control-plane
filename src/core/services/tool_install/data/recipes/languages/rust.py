"""
L0 Data — Rust ecosystem tools.

Categories: rust, language
Pure data, no logic.
"""

from __future__ import annotations


_RUST_RECIPES: dict[str, dict] = {

    "cargo-audit": {
        "label": "cargo-audit",
        "category": "rust",
        "install": {"_default": ["cargo", "install", "cargo-audit"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "cargo"},
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
        "category": "rust",
        "install": {"_default": ["cargo", "install", "cargo-outdated"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "cargo"},
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

    "cargo": {
        "label": "Cargo (Rust)",
        "category": "language",
        # EVOLUTION NOTE (2026-02-26):
        # Originally a _default-only stub using rustup.rs. Expanded to
        # full multi-PM coverage. Two installation paths exist:
        #   1. rustup (_default, brew, pacman, snap) — latest stable,
        #      user-local ($HOME/.cargo/bin), no sudo. Recommended.
        #   2. system packages (apt, dnf, apk, zypper) — distro-maintained,
        #      often outdated (e.g. Ubuntu 22.04 ships Rust 1.66 vs
        #      current 1.83+). System-wide, needs sudo.
        # The `prefer` field routes to _default first.
        #
        # IMPORTANT: pacman/brew/snap install rustup (the manager), NOT
        # cargo. They need a chained `rustup default stable` or
        # `rustup-init -y` to actually produce a cargo binary.
        "install": {
            "apt":    ["apt-get", "install", "-y", "cargo"],
            "dnf":    ["dnf", "install", "-y", "cargo"],
            "apk":    ["apk", "add", "cargo"],
            "pacman": ["bash", "-c",
                       "pacman -S --noconfirm rustup && "
                       "rustup default stable"],
            "zypper": ["zypper", "install", "-y", "cargo"],
            "brew":   ["bash", "-c",
                       "brew install rustup && "
                       "rustup-init -y"],
            "snap":   ["bash", "-c",
                       "snap install rustup --classic && "
                       "rustup default stable"],
            "_default": [
                "bash", "-c",
                "curl --proto '=https' --tlsv1.2 -sSf "
                "https://sh.rustup.rs | sh -s -- -y",
            ],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True,
            "brew": False, "snap": True, "_default": False,
        },
        "install_via": {"_default": "curl_pipe_bash"},
        "prefer": ["_default", "brew", "snap"],
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.cargo/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.cargo/bin:$PATH" && cargo --version'],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y", "cargo"],
            "dnf":    ["dnf", "upgrade", "-y", "cargo"],
            "apk":    ["apk", "upgrade", "cargo"],
            "pacman": ["bash", "-c",
                       'export PATH="$HOME/.cargo/bin:$PATH" && '
                       "rustup update"],
            "zypper": ["zypper", "update", "-y", "cargo"],
            "brew":   ["bash", "-c",
                       'export PATH="$HOME/.cargo/bin:$PATH" && '
                       "rustup update"],
            "snap":   ["bash", "-c",
                       'export PATH="$HOME/.cargo/bin:$PATH" && '
                       "rustup update"],
            "_default": ["bash", "-c",
                   'export PATH="$HOME/.cargo/bin:$PATH" && rustup update'],
        },
    },
    "rustc": {
        "label": "Rust Compiler",
        "category": "rust",
        "install": {
            "_default": [
                "bash", "-c",
                "curl --proto '=https' --tlsv1.2 -sSf "
                "https://sh.rustup.rs | sh -s -- -y",
            ],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.cargo/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.cargo/bin:$PATH" && rustc --version'],
        "update": {"_default": ["bash", "-c",
                   'export PATH="$HOME/.cargo/bin:$PATH" && rustup update']},
    },
    # ── rustup ──────────────────────────────────────────────────
    # Official Rust toolchain installer and version manager.
    # Installs to ~/.cargo/bin (rustup, rustc, cargo).
    # Unlike nvm, rustup IS a binary so shutil.which() works.
    #
    # IMPORTANT: Most PM installs only provide `rustup` (or
    # `rustup-init`) — you still need `rustup default stable`
    # to get rustc and cargo. The commands below chain this.
    #
    # apt: Debian 13+ / Ubuntu 24.04+ only. Older versions
    # don't have the rustup package.
    "rustup": {
        "cli": "rustup",
        "label": "rustup (Rust toolchain manager)",
        "category": "rust",
        "install": {
            "apt":    ["bash", "-c",
                       "apt-get install -y rustup && "
                       "rustup default stable"],
            "dnf":    ["bash", "-c",
                       "dnf install -y rustup && "
                       "rustup-init -y"],
            "apk":    ["bash", "-c",
                       "apk add rustup && "
                       "rustup-init -y"],
            "pacman": ["bash", "-c",
                       "pacman -S --noconfirm rustup && "
                       "rustup default stable"],
            "zypper": ["bash", "-c",
                       "zypper install -y rustup && "
                       "rustup toolchain install stable"],
            "brew":   ["bash", "-c",
                       "brew install rustup && "
                       "rustup-init -y"],
            "snap":   ["bash", "-c",
                       "snap install rustup --classic && "
                       "rustup default stable"],
            "_default": [
                "bash", "-c",
                "curl --proto '=https' --tlsv1.2 -sSf "
                "https://sh.rustup.rs | sh -s -- -y",
            ],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True,
            "brew": False, "snap": True, "_default": False,
        },
        "install_via": {"_default": "curl_pipe_bash"},
        "prefer": ["_default", "brew", "pacman", "snap"],
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.cargo/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.cargo/bin:$PATH" && '
                   "rustup --version"],
        "update": {
            "_default": ["bash", "-c",
                   'export PATH="$HOME/.cargo/bin:$PATH" && '
                   "rustup self update"],
            "apt":    ["apt-get", "install", "--only-upgrade", "-y", "rustup"],
            "dnf":    ["dnf", "upgrade", "-y", "rustup"],
            "apk":    ["apk", "upgrade", "rustup"],
            "pacman": ["pacman", "-S", "--noconfirm", "rustup"],
            "zypper": ["zypper", "update", "-y", "rustup"],
            "brew":   ["brew", "upgrade", "rustup"],
            "snap":   ["snap", "refresh", "rustup"],
        },
    },

    "node": {
        "label": "Node.js",
        "cli": "node",
        "category": "language",
        # EVOLUTION NOTE (2026-02-26):
        # Full coverage + remediation audit. Added cli, category, zypper,
        # _default binary download, arch_map, requires. Removed explicit
        # update (derived by get_update_map for PM methods).
        #
        # _default is an OS-variant dict (Evolution: OS & Arch Awareness):
        #   linux  — .tar.xz archive, tar -xJf
        #   darwin — .tar.gz archive, tar -xzf
        # Both use {arch} placeholder resolved via arch_map.
        #
        # Node.js publishes pre-compiled binaries for:
        #   linux-x64, linux-arm64, linux-armv7l
        #   darwin-x64, darwin-arm64
        "install": {
            "snap":   ["snap", "install", "node", "--classic"],
            "apt":    ["apt-get", "install", "-y", "nodejs"],
            "dnf":    ["dnf", "install", "-y", "nodejs"],
            "apk":    ["apk", "add", "nodejs", "npm"],
            "pacman": ["pacman", "-S", "--noconfirm", "nodejs", "npm"],
            "zypper": ["zypper", "install", "-y", "nodejs20"],
            "brew":   ["brew", "install", "node"],
            "_default": {
                "linux": [
                    "bash", "-c",
                    "NODE_VERSION=$(curl -sSf "
                    "https://nodejs.org/dist/index.json "
                    "| python3 -c \"import sys,json;"
                    "vs=[v for v in json.load(sys.stdin) if v['lts']];"
                    "print(vs[0]['version'])\" "
                    "2>/dev/null || echo v22.15.0) && "
                    "curl -sSfL "
                    "\"https://nodejs.org/dist/${NODE_VERSION}/"
                    "node-${NODE_VERSION}-linux-{arch}.tar.xz\" "
                    "-o /tmp/node.tar.xz && "
                    "tar -xJf /tmp/node.tar.xz -C /usr/local "
                    "--strip-components=1 && "
                    "rm /tmp/node.tar.xz",
                ],
                "darwin": [
                    "bash", "-c",
                    "NODE_VERSION=$(curl -sSf "
                    "https://nodejs.org/dist/index.json "
                    "| python3 -c \"import sys,json;"
                    "vs=[v for v in json.load(sys.stdin) if v['lts']];"
                    "print(vs[0]['version'])\" "
                    "2>/dev/null || echo v22.15.0) && "
                    "curl -sSfL "
                    "\"https://nodejs.org/dist/${NODE_VERSION}/"
                    "node-${NODE_VERSION}-darwin-{arch}.tar.gz\" "
                    "-o /tmp/node.tar.gz && "
                    "tar -xzf /tmp/node.tar.gz -C /usr/local "
                    "--strip-components=1 && "
                    "rm /tmp/node.tar.gz",
                ],
            },
        },
        "needs_sudo": {
            "snap": True, "apt": True, "dnf": True,
            "apk": True, "pacman": True, "zypper": True,
            "brew": False, "_default": True,
        },
        "prefer": ["_default", "snap", "brew"],
        "requires": {"binaries": ["curl"]},
        "arch_map": {"x86_64": "x64", "aarch64": "arm64", "armv7l": "armv7l"},
        "version_constraint": {
            "type": "gte",
            "reference": "18.0.0",
            "description": "Node.js 18+ required for modern ESM and fetch support.",
        },
        "verify": ["node", "--version"],
    },
    "go": {
        "cli": "go",
        "label": "Go",
        "category": "language",
        # EVOLUTION NOTE (2026-02-26):
        # Originally had 6 PM methods. Expanded to 8 with _default
        # binary download from go.dev, added zypper.
        #
        # _default uses {os} placeholder (Evolution: OS & Arch Awareness)
        # since Go uses the same .tar.gz format on both linux and darwin.
        # URL pattern: go.dev/dl/${GO_VERSION}.{os}-{arch}.tar.gz
        "install": {
            "apt":    ["apt-get", "install", "-y", "golang-go"],
            "dnf":    ["dnf", "install", "-y", "golang"],
            "apk":    ["apk", "add", "go"],
            "pacman": ["pacman", "-S", "--noconfirm", "go"],
            "zypper": ["zypper", "install", "-y", "go"],
            "brew":   ["brew", "install", "go"],
            "snap":   ["snap", "install", "go", "--classic"],
            "_default": [
                "bash", "-c",
                "GO_VERSION=$(curl -sSf https://go.dev/VERSION?m=text "
                "| head -1) && "
                "curl -sSfL "
                "\"https://go.dev/dl/${GO_VERSION}.{os}-{arch}.tar.gz\" "
                "-o /tmp/go.tar.gz && "
                "rm -rf /usr/local/go && "
                "tar -C /usr/local -xzf /tmp/go.tar.gz && "
                "rm /tmp/go.tar.gz",
            ],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
            "snap": True, "_default": True,
        },
        "prefer": ["_default", "snap", "brew"],
        "requires": {"binaries": ["curl"]},
        "arch_map": {"armv7l": "armv6l"},
        "post_env": 'export PATH=$PATH:/usr/local/go/bin',
        "verify": ["bash", "-c",
                   'export PATH=$PATH:/usr/local/go/bin && go version'],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y", "golang-go"],
            "dnf":    ["dnf", "upgrade", "-y", "golang"],
            "apk":    ["apk", "upgrade", "go"],
            "pacman": ["pacman", "-S", "--noconfirm", "go"],
            "zypper": ["zypper", "update", "-y", "go"],
            "brew":   ["brew", "upgrade", "go"],
            "snap":   ["snap", "refresh", "go"],
            "_default": [
                "bash", "-c",
                "GO_VERSION=$(curl -sSf https://go.dev/VERSION?m=text "
                "| head -1) && "
                "curl -sSfL "
                "\"https://go.dev/dl/${GO_VERSION}.{os}-{arch}.tar.gz\" "
                "-o /tmp/go.tar.gz && "
                "rm -rf /usr/local/go && "
                "tar -C /usr/local -xzf /tmp/go.tar.gz && "
                "rm /tmp/go.tar.gz",
            ],
        },
    },

    "python": {
        "label": "Python",
        "cli": "python3",
        "category": "language",
        # EVOLUTION NOTE (2026-02-26):
        # Python is special: system Python is pre-installed on almost all
        # Linux distros. This recipe is for when it's MISSING or when a
        # newer version is needed. Two paths:
        #   1. System PM (apt/dnf/apk/pacman/zypper/brew) — fast, distro version
        #   2. _default — build from source (python.org tarball), always latest
        # snap is intentionally excluded: python3-alt snap naming is
        # confusing and conflicts with system python3 symlink.
        "install": {
            "apt":    ["apt-get", "install", "-y", "python3"],
            "dnf":    ["dnf", "install", "-y", "python3"],
            "apk":    ["apk", "add", "python3"],
            "pacman": ["pacman", "-S", "--noconfirm", "python"],
            "zypper": ["zypper", "install", "-y", "python3"],
            "brew":   ["brew", "install", "python@3"],
            "_default": [
                "bash", "-c",
                "PY_VERSION=$(curl -sSf https://www.python.org/ftp/python/"
                " | grep -oP '(?<=href=\")3\\.\\d+\\.\\d+(?=/\")'"
                " | sort -V | tail -1) && "
                "curl -sSfL \"https://www.python.org/ftp/python/"
                "${PY_VERSION}/Python-${PY_VERSION}.tgz\""
                " -o /tmp/python.tgz && "
                "tar -xzf /tmp/python.tgz -C /tmp && "
                "cd /tmp/Python-${PY_VERSION} && "
                "./configure --enable-optimizations --prefix=/usr/local && "
                "make -j$(nproc) && "
                "sudo make altinstall && "
                "rm -rf /tmp/python.tgz /tmp/Python-${PY_VERSION}",
            ],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
            "_default": True,
        },
        "requires": {
            "binaries": ["curl"],
            "packages": {
                "debian": [
                    "build-essential", "libssl-dev", "zlib1g-dev",
                    "libncurses5-dev", "libreadline-dev", "libsqlite3-dev",
                    "libffi-dev", "libbz2-dev", "liblzma-dev",
                ],
                "rhel": [
                    "gcc", "make", "openssl-devel", "zlib-devel",
                    "ncurses-devel", "readline-devel", "sqlite-devel",
                    "libffi-devel", "bzip2-devel", "xz-devel",
                ],
                "alpine": [
                    "build-base", "openssl-dev", "zlib-dev",
                    "ncurses-dev", "readline-dev", "sqlite-dev",
                    "libffi-dev", "bzip2-dev", "xz-dev",
                ],
                "arch": [
                    "base-devel", "openssl", "zlib",
                    "ncurses", "readline", "sqlite",
                    "libffi", "bzip2", "xz",
                ],
                "suse": [
                    "gcc", "make", "libopenssl-devel", "zlib-devel",
                    "ncurses-devel", "readline-devel", "sqlite3-devel",
                    "libffi-devel", "libbz2-devel", "xz-devel",
                ],
            },
        },
        "verify": ["python3", "--version"],
    },

    "cargo-watch": {
        "label": "cargo-watch (file watcher)",
        "category": "rust",
        "install": {"_default": ["cargo", "install", "cargo-watch"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "cargo"},
        "requires": {"binaries": ["cargo"]},
        "verify": ["cargo", "watch", "--version"],
    },
    "cargo-edit": {
        "label": "cargo-edit (add/rm/upgrade)",
        "category": "rust",
        "install": {"_default": ["cargo", "install", "cargo-edit"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "cargo"},
        "requires": {"binaries": ["cargo"]},
        "verify": ["cargo", "add", "--version"],
    },
    "cargo-nextest": {
        "label": "cargo-nextest (test runner)",
        "category": "rust",
        "install": {
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -LsSf https://get.nexte.st/latest/linux"
                    " | tar zxf - -C ${CARGO_HOME:-~/.cargo}/bin",
                ],
            },
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
        "install_via": {"_default": "cargo"},
        "requires": {"binaries": ["cargo"]},
        "verify": ["sccache", "--version"],
    },
    "cross": {
        "label": "cross (cross-compilation)",
        "category": "rust",
        "install": {"_default": ["cargo", "install", "cross"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "cargo"},
        "requires": {"binaries": ["cargo", "docker"]},
        "verify": ["cross", "--version"],
    },
}
