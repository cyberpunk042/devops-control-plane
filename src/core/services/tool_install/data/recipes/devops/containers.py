"""
L0 Data — Container & virtualization tools.

Categories: container, virtualization
Pure data, no logic.
"""

from __future__ import annotations


_CONTAINERS_RECIPES: dict[str, dict] = {
    "docker": {
        "label": "Docker",
        "category": "container",
        "install": {
            "apt":    ["apt-get", "install", "-y", "docker.io"],
            "dnf":    ["dnf", "install", "-y", "docker"],
            "apk":    ["apk", "add", "docker"],
            "pacman": ["pacman", "-S", "--noconfirm", "docker"],
            "zypper": ["zypper", "install", "-y", "docker"],
            "brew":   ["brew", "install", "docker"],
            "_default": [
                "bash", "-c",
                "curl -fsSL https://get.docker.com | sudo sh",
            ],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
            "_default": True,
        },
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
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
            "brew":   ["brew", "upgrade", "docker"],
            "_default": [
                "bash", "-c",
                "curl -fsSL https://get.docker.com | sudo sh",
            ],
        },
    },
    "docker-compose": {
        "cli": "docker",
        "label": "Docker Compose",
        "category": "container",
        "install": {
            "apt":    ["apt-get", "install", "-y", "docker-compose-plugin"],
            "dnf":    ["dnf", "install", "-y", "docker-compose-plugin"],
            "apk":    ["apk", "add", "docker-cli-compose"],
            "pacman": ["pacman", "-S", "--noconfirm", "docker-compose"],
            "zypper": ["zypper", "install", "-y", "docker-compose"],
            "brew":   ["brew", "install", "docker-compose"],
            "_default": {
                "linux": [
                    "bash", "-c",
                    "COMPOSE_ARCH={arch} && "
                    "mkdir -p /usr/local/lib/docker/cli-plugins && "
                    "curl -sSfL https://github.com/docker/compose/releases/"
                    "latest/download/docker-compose-linux-$COMPOSE_ARCH "
                    "-o /usr/local/lib/docker/cli-plugins/docker-compose && "
                    "chmod +x /usr/local/lib/docker/cli-plugins/docker-compose",
                ],
            },
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
            "_default": True,
        },
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["docker", "curl"]},
        "version_constraint": {
            "type": "gte",
            "reference": "2.0.0",
            "description": "Docker Compose V2 required (docker compose, not docker-compose).",
        },
        "verify": ["docker", "compose", "version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y",
                       "docker-compose-plugin"],
            "dnf":    ["dnf", "upgrade", "-y", "docker-compose-plugin"],
            "apk":    ["apk", "upgrade", "docker-cli-compose"],
            "pacman": ["pacman", "-S", "--noconfirm", "docker-compose"],
            "zypper": ["zypper", "update", "-y", "docker-compose"],
            "brew":   ["brew", "upgrade", "docker-compose"],
            "_default": {
                "linux": [
                    "bash", "-c",
                    "COMPOSE_ARCH={arch} && "
                    "mkdir -p /usr/local/lib/docker/cli-plugins && "
                    "curl -sSfL https://github.com/docker/compose/releases/"
                    "latest/download/docker-compose-linux-$COMPOSE_ARCH "
                    "-o /usr/local/lib/docker/cli-plugins/docker-compose && "
                    "chmod +x /usr/local/lib/docker/cli-plugins/docker-compose",
                ],
            },
        },
        "arch_map": {"x86_64": "x86_64", "aarch64": "aarch64", "armv7l": "armv7"},
    },

    "buildx": {
        "cli": "docker",
        "label": "Docker Buildx (extended build capabilities)",
        "category": "container",
        "cli_verify_args": ["buildx", "version"],
        # Docker CLI plugin — NOT a standalone binary.
        # Installs to ~/.docker/cli-plugins/docker-buildx
        # Available in apt/dnf (docker-buildx-plugin), pacman, brew.
        # GitHub releases (docker/buildx): raw binary (no archive).
        # Asset naming: buildx-v{ver}.{os}-{arch} (dot separator!).
        # OS: linux, darwin. Arch: amd64, arm64 (Go-standard).
        # /releases/latest/download/ redirect works.
        # Requires docker as runtime dependency.
        "install": {
            "apt": ["apt-get", "install", "-y", "docker-buildx-plugin"],
            "dnf": ["dnf", "install", "-y", "docker-buildx-plugin"],
            "pacman": ["pacman", "-S", "--noconfirm", "docker-buildx"],
            "brew": ["brew", "install", "docker-buildx"],
            "_default": [
                "bash", "-c",
                "mkdir -p ~/.docker/cli-plugins"
                " && curl -sSfL https://github.com/docker/buildx/releases/"
                "latest/download/buildx-v0.31.1.{os}-{arch}"
                " -o ~/.docker/cli-plugins/docker-buildx"
                " && chmod +x ~/.docker/cli-plugins/docker-buildx",
            ],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "pacman": True,
            "brew": False, "_default": False,
        },
        "install_via": {"_default": "binary_download"},
        "requires": {"binaries": ["docker", "curl"]},
        "arch_map": {
            "x86_64": "amd64", "aarch64": "arm64",
        },
        "prefer": ["apt", "dnf", "pacman", "brew"],
        "verify": ["docker", "buildx", "version"],
        "update": {
            "apt": ["apt-get", "install", "-y", "--only-upgrade",
                    "docker-buildx-plugin"],
            "dnf": ["dnf", "upgrade", "-y", "docker-buildx-plugin"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "docker-buildx"],
            "brew": ["brew", "upgrade", "docker-buildx"],
            "_default": [
                "bash", "-c",
                "mkdir -p ~/.docker/cli-plugins"
                " && curl -sSfL https://github.com/docker/buildx/releases/"
                "latest/download/buildx-v0.31.1.{os}-{arch}"
                " -o ~/.docker/cli-plugins/docker-buildx"
                " && chmod +x ~/.docker/cli-plugins/docker-buildx",
            ],
        },
    },

    "podman": {
        "cli": "podman",
        "label": "Podman (daemonless container engine)",
        "category": "container",
        # Podman is available in ALL native PMs — widest coverage.
        # By Red Hat / containers project. Go-based.
        # No _default needed — every PM has it.
        # snap exists but edge-only — not stable enough.
        "install": {
            "apt": ["apt-get", "install", "-y", "podman"],
            "dnf": ["dnf", "install", "-y", "podman"],
            "apk": ["apk", "add", "podman"],
            "pacman": ["pacman", "-S", "--noconfirm", "podman"],
            "zypper": ["zypper", "install", "-y", "podman"],
            "brew": ["brew", "install", "podman"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["podman", "--version"],
        "update": {
            "apt": ["apt-get", "install", "-y", "--only-upgrade", "podman"],
            "dnf": ["dnf", "upgrade", "-y", "podman"],
            "apk": ["apk", "upgrade", "podman"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "podman"],
            "zypper": ["zypper", "update", "-y", "podman"],
            "brew": ["brew", "upgrade", "podman"],
        },
    },
    "skopeo": {
        "cli": "skopeo",
        "label": "Skopeo (container image inspection & transfer)",
        "category": "container",
        # Same containers project as podman. Go-based.
        # Available in ALL native PMs — wide coverage.
        # No _default needed — every PM has it.
        "install": {
            "apt": ["apt-get", "install", "-y", "skopeo"],
            "dnf": ["dnf", "install", "-y", "skopeo"],
            "apk": ["apk", "add", "skopeo"],
            "pacman": ["pacman", "-S", "--noconfirm", "skopeo"],
            "zypper": ["zypper", "install", "-y", "skopeo"],
            "brew": ["brew", "install", "skopeo"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["skopeo", "--version"],
        "update": {
            "apt": ["apt-get", "install", "-y", "--only-upgrade", "skopeo"],
            "dnf": ["dnf", "upgrade", "-y", "skopeo"],
            "apk": ["apk", "upgrade", "skopeo"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "skopeo"],
            "zypper": ["zypper", "update", "-y", "skopeo"],
            "brew": ["brew", "upgrade", "skopeo"],
        },
    },
    "dive": {
        "cli": "dive",
        "label": "Dive (Docker image layer explorer)",
        "category": "container",
        # Go-based. By wagoodman.
        # NOT in apt, dnf, apk, zypper.
        # Available in pacman (extra), brew, snap.
        # GitHub releases (wagoodman/dive): .tar.gz, .deb, .rpm.
        # Asset naming: dive_{ver}_{os}_{arch}.tar.gz
        # OS: linux, darwin. Arch: amd64, arm64 (Go-standard).
        # Tag has 'v' prefix, filename does NOT.
        # snap available but may interfere with Docker rootdir.
        "install": {
            "pacman": ["pacman", "-S", "--noconfirm", "dive"],
            "brew": ["brew", "install", "dive"],
            "snap": ["snap", "install", "dive"],
            "_default": [
                "bash", "-c",
                "VERSION=$(curl -sSf https://api.github.com/repos/wagoodman/"
                "dive/releases/latest | grep -o '\"tag_name\": \"v[^\"]*\"'"
                " | cut -d'\"' -f4 | sed 's/^v//') && "
                "curl -sSfL https://github.com/wagoodman/dive/releases/"
                "download/v${VERSION}/dive_${VERSION}_{os}_{arch}.tar.gz"
                " | tar -xz -C /usr/local/bin dive",
            ],
        },
        "needs_sudo": {
            "pacman": True, "brew": False, "snap": True,
            "_default": True,
        },
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "arch_map": {
            "x86_64": "amd64", "aarch64": "arm64",
        },
        "prefer": ["pacman", "brew", "snap"],
        "verify": ["dive", "--version"],
        "update": {
            "pacman": ["pacman", "-Syu", "--noconfirm", "dive"],
            "brew": ["brew", "upgrade", "dive"],
            "snap": ["snap", "refresh", "dive"],
            "_default": [
                "bash", "-c",
                "VERSION=$(curl -sSf https://api.github.com/repos/wagoodman/"
                "dive/releases/latest | grep -o '\"tag_name\": \"v[^\"]*\"'"
                " | cut -d'\"' -f4 | sed 's/^v//') && "
                "curl -sSfL https://github.com/wagoodman/dive/releases/"
                "download/v${VERSION}/dive_${VERSION}_{os}_{arch}.tar.gz"
                " | tar -xz -C /usr/local/bin dive",
            ],
        },
    },
    "hadolint": {
        "cli": "hadolint",
        "label": "Hadolint (Dockerfile linter)",
        "category": "container",
        # Written in Haskell. By hadolint.
        # NOT in apt, dnf, apk, zypper, snap.
        # pacman only via AUR (not official).
        # Available in brew.
        # GitHub releases (hadolint/hadolint): RAW BINARY (no archive).
        # NON-STANDARD naming:
        #   Capital OS: Linux, Darwin (NOT lowercase!)
        #   Arch: x86_64, arm64 (NOT amd64!)
        # Asset: hadolint-$(uname -s)-{arch}
        # Using $(uname -s) instead of {os} because it natively returns
        # "Linux"/"Darwin" matching hadolint's capital-letter convention.
        # /releases/latest/download/ redirect works.
        "install": {
            "brew": ["brew", "install", "hadolint"],
            "_default": [
                "bash", "-c",
                "curl -sSfL -o /usr/local/bin/hadolint"
                " https://github.com/hadolint/hadolint/releases/latest/"
                "download/hadolint-$(uname -s)-{arch}"
                " && chmod +x /usr/local/bin/hadolint",
            ],
        },
        "needs_sudo": {
            "brew": False, "_default": True,
        },
        "install_via": {"_default": "binary_download"},
        "requires": {"binaries": ["curl"]},
        "arch_map": {
            "x86_64": "x86_64", "aarch64": "arm64",
        },
        "prefer": ["brew"],
        "verify": ["hadolint", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "hadolint"],
            "_default": [
                "bash", "-c",
                "curl -sSfL -o /usr/local/bin/hadolint"
                " https://github.com/hadolint/hadolint/releases/latest/"
                "download/hadolint-$(uname -s)-{arch}"
                " && chmod +x /usr/local/bin/hadolint",
            ],
        },
    },
    "dagger": {
        "cli": "dagger",
        "label": "Dagger (programmable CI/CD engine)",
        "category": "container",
        # Go-based. By Dagger Inc.
        # NOT in apt, dnf, apk, pacman, zypper, snap.
        # Available in brew (custom tap: dagger/tap/dagger).
        # Official installer: dl.dagger.io/dagger/install.sh
        # Auto-detects OS and arch — no placeholders needed.
        # GitHub releases: dagger_v{ver}_{os}_{arch}.tar.gz
        # Requires Docker as container runtime.
        "install": {
            "brew": ["brew", "install", "dagger/tap/dagger"],
            "_default": [
                "bash", "-c",
                "curl -sSfL https://dl.dagger.io/dagger/install.sh | sh",
            ],
        },
        "needs_sudo": {
            "brew": False, "_default": True,
        },
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["docker", "curl"]},
        "prefer": ["brew"],
        "verify": ["dagger", "version"],
        "update": {
            "brew": ["brew", "upgrade", "dagger/tap/dagger"],
            "_default": [
                "bash", "-c",
                "curl -sSfL https://dl.dagger.io/dagger/install.sh | sh",
            ],
        },
    },

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
        "install_via": {"_default": "curl_pipe_bash"},
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
        "install_via": {"_default": "curl_pipe_bash"},
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
}
