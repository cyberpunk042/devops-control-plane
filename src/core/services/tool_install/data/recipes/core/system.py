"""
L0 Data — Core system tools.

Categories: system, compression, process, backup, utility
Pure data, no logic.
"""

from __future__ import annotations

from src.core.services.tool_install.data.constants import _PIP


_SYSTEM_RECIPES: dict[str, dict] = {

    "git": {
        "label": "Git",
        "category": "system",
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
    "git-filter-repo": {
        "label": "git-filter-repo (history rewriting)",
        "category": "system",
        "cli": "git-filter-repo",
        "install": {
            "_default": _PIP + ["install", "git-filter-repo"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "requires": {"binaries": ["git"]},
        "verify": ["git-filter-repo", "--version"],
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
        "cli": "jq",
        "label": "jq (command-line JSON processor)",
        "category": "utility",
        # jq is a simple system package on all PMs.
        # _default downloads the raw binary from GitHub (no archive).
        # Binary naming: jq-{os}-{arch} (os: linux/macos, arch: amd64/arm64)
        # Tag format: jq-VERSION (not v-prefixed)
        "install": {
            "apt":    ["apt-get", "install", "-y", "jq"],
            "dnf":    ["dnf", "install", "-y", "jq"],
            "apk":    ["apk", "add", "jq"],
            "pacman": ["pacman", "-S", "--noconfirm", "jq"],
            "zypper": ["zypper", "install", "-y", "jq"],
            "brew":   ["brew", "install", "jq"],
            "_default": [
                "bash", "-c",
                "JQ_VERSION=$(curl -sSf"
                " https://api.github.com/repos/jqlang/jq/releases/latest"
                " | grep '\"tag_name\"'"
                " | sed 's/.*\"\\(jq-[^\"]*\\)\".*/\\1/')"
                " && curl -sSfL -o /usr/local/bin/jq"
                " \"https://github.com/jqlang/jq/releases/download/"
                "${JQ_VERSION}/jq-{os}-{arch}\""
                " && chmod +x /usr/local/bin/jq",
            ],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
            "_default": True,
        },
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "arch_map": {
            "x86_64": "amd64", "aarch64": "arm64", "armv7l": "armhf",
        },
        "verify": ["jq", "--version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y", "jq"],
            "dnf":    ["dnf", "upgrade", "-y", "jq"],
            "apk":    ["apk", "upgrade", "jq"],
            "pacman": ["pacman", "-S", "--noconfirm", "jq"],
            "zypper": ["zypper", "update", "-y", "jq"],
            "brew":   ["brew", "upgrade", "jq"],
            "_default": [
                "bash", "-c",
                "JQ_VERSION=$(curl -sSf"
                " https://api.github.com/repos/jqlang/jq/releases/latest"
                " | grep '\"tag_name\"'"
                " | sed 's/.*\"\\(jq-[^\"]*\\)\".*/\\1/')"
                " && curl -sSfL -o /usr/local/bin/jq"
                " \"https://github.com/jqlang/jq/releases/download/"
                "${JQ_VERSION}/jq-{os}-{arch}\""
                " && chmod +x /usr/local/bin/jq",
            ],
        },
    },

    "make": {
        "label": "Make",
        "category": "system",
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
        "category": "compression",
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
        "category": "system",
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
        "install_via": {"_default": "pip"},
        "verify": ["jc", "--version"],
    },
    "yq": {
        "label": "yq (YAML processor)",
        "category": "system",
        "install": {
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL -o /usr/local/bin/yq"
                    " https://github.com/mikefarah/yq/releases/latest/download/"
                    "yq_linux_amd64 && chmod +x /usr/local/bin/yq",
                ],
            },
            "brew": ["brew", "install", "yq"],
            "snap": ["snap", "install", "yq"],
        },
        "needs_sudo": {"_default": True, "brew": False, "snap": True},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "verify": ["yq", "--version"],
    },

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
        "install_via": {"_default": "curl_pipe_bash"},
        "verify": ["rclone", "version"],
    },

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
        "install_via": {"_default": "pip"},
        "verify": ["supervisord", "--version"],
    },
    "pm2": {
        "label": "PM2 (Node process manager)",
        "category": "process",
        "install": {
            "_default": ["npm", "install", "-g", "pm2"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "npm"},
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
}
