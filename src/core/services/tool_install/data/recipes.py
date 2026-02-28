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
        "install_via": {"_default": "pip"},
        "verify": ["ruff", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "ruff"]},
    },
    "mypy": {
        "label": "mypy",
        "install": {"_default": _PIP + ["install", "mypy"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": ["mypy", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "mypy"]},
    },
    "pytest": {
        "label": "pytest",
        "install": {"_default": _PIP + ["install", "pytest"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": ["pytest", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "pytest"]},
    },
    "black": {
        "label": "Black",
        "install": {"_default": _PIP + ["install", "black"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": ["black", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "black"]},
    },
    "pip-audit": {
        "label": "pip-audit",
        "install": {"_default": _PIP + ["install", "pip-audit"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": _PIP + ["show", "pip-audit"],
        "update": {"_default": _PIP + ["install", "--upgrade", "pip-audit"]},
    },
    "safety": {
        "label": "Safety",
        "install": {"_default": _PIP + ["install", "safety"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": ["safety", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "safety"]},
    },
    "bandit": {
        "label": "Bandit",
        "install": {"_default": _PIP + ["install", "bandit"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": ["bandit", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "bandit"]},
    },

    # ── Category 2: npm tools ───────────────────────────────────

    "eslint": {
        "label": "ESLint",
        "install": {"_default": ["npm", "install", "-g", "eslint"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "verify": ["eslint", "--version"],
        "update": {"_default": ["npm", "update", "-g", "eslint"]},
    },
    "prettier": {
        "label": "Prettier",
        "install": {"_default": ["npm", "install", "-g", "prettier"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "verify": ["prettier", "--version"],
        "update": {"_default": ["npm", "update", "-g", "prettier"]},
    },

    # ── Category 3: cargo tools (need cargo + sys dev packages) ─

    "cargo-audit": {
        "label": "cargo-audit",
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

    # ── Category 4: Runtimes via bash-curl ──────────────────────

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

    # ── Category 5: bash-curl + brew alternatives ───────────────

    "helm": {
        "cli": "helm",
        "label": "Helm (Kubernetes package manager)",
        "category": "k8s",
        # Helm is available via apt (Buildkite repo + GPG), dnf (Fedora 35+),
        # apk (Alpine community), brew, snap (--classic), and the official
        # get-helm-3 installer script. NOT in pacman or zypper official repos.
        "install": {
            "apt": [
                "bash", "-c",
                "apt-get install -y curl gpg apt-transport-https"
                " && curl -fsSL https://packages.buildkite.com/"
                "helm-linux/helm-debian/gpgkey"
                " | gpg --dearmor"
                " | tee /usr/share/keyrings/helm.gpg > /dev/null"
                " && echo 'deb [signed-by=/usr/share/keyrings/helm.gpg]"
                " https://packages.buildkite.com/helm-linux/helm-debian/"
                "any/ any main'"
                " | tee /etc/apt/sources.list.d/helm-stable-debian.list"
                " && apt-get update"
                " && apt-get install -y helm",
            ],
            "dnf": ["dnf", "install", "-y", "helm"],
            "apk": ["apk", "add", "helm"],
            "brew": ["brew", "install", "helm"],
            "snap": ["snap", "install", "helm", "--classic"],
            "_default": [
                "bash", "-c",
                "curl -fsSL https://raw.githubusercontent.com/helm/helm"
                "/main/scripts/get-helm-3 | bash",
            ],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "brew": False, "snap": True, "_default": True,
        },
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "prefer": ["apt", "dnf", "apk", "brew"],
        "verify": ["helm", "version"],
        "update": {
            "apt": ["apt-get", "install", "--only-upgrade", "-y", "helm"],
            "dnf": ["dnf", "upgrade", "-y", "helm"],
            "apk": ["apk", "upgrade", "helm"],
            "brew": ["brew", "upgrade", "helm"],
            "snap": ["snap", "refresh", "helm"],
            "_default": [
                "bash", "-c",
                "curl -fsSL https://raw.githubusercontent.com/helm/helm"
                "/main/scripts/get-helm-3 | bash",
            ],
        },
    },

    "trivy": {
        "cli": "trivy",
        "label": "Trivy (comprehensive vulnerability scanner)",
        "category": "security",
        # Trivy apt/dnf require adding Aqua Security's GPG key + repo.
        # Not in apk/pacman/zypper standard repos.
        # Official curl|bash installer handles OS/arch detection.
        "install": {
            "apt": [
                "bash", "-c",
                "apt-get install -y wget apt-transport-https gnupg"
                " && wget -qO - https://aquasecurity.github.io/trivy-repo/"
                "deb/public.key"
                " | gpg --dearmor"
                " | tee /usr/share/keyrings/trivy.gpg > /dev/null"
                " && echo 'deb [signed-by=/usr/share/keyrings/trivy.gpg]"
                " https://aquasecurity.github.io/trivy-repo/deb"
                " generic main'"
                " | tee /etc/apt/sources.list.d/trivy.list"
                " && apt-get update"
                " && apt-get install -y trivy",
            ],
            "dnf": [
                "bash", "-c",
                "cat << 'EOF' | tee /etc/yum.repos.d/trivy.repo\n"
                "[trivy]\n"
                "name=Trivy repository\n"
                "baseurl=https://aquasecurity.github.io/trivy-repo/rpm/"
                "releases/$basearch/\n"
                "gpgcheck=0\n"
                "enabled=1\n"
                "EOF\n"
                " && dnf install -y trivy",
            ],
            "brew": ["brew", "install", "trivy"],
            "snap": ["snap", "install", "trivy"],
            "_default": [
                "bash", "-c",
                "curl -sfL https://raw.githubusercontent.com/aquasecurity/"
                "trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin",
            ],
        },
        "needs_sudo": {
            "apt": True, "dnf": True,
            "brew": False, "snap": True, "_default": True,
        },
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "prefer": ["apt", "dnf", "brew"],
        "verify": ["trivy", "--version"],
        "update": {
            "apt": ["apt-get", "install", "--only-upgrade", "-y", "trivy"],
            "dnf": ["dnf", "upgrade", "-y", "trivy"],
            "brew": ["brew", "upgrade", "trivy"],
            "snap": ["snap", "refresh", "trivy"],
            "_default": [
                "bash", "-c",
                "curl -sfL https://raw.githubusercontent.com/aquasecurity/"
                "trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin",
            ],
        },
    },

    "skaffold": {
        "label": "Skaffold",
        "install": {
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -Lo /usr/local/bin/skaffold "
                    "https://storage.googleapis.com/skaffold/releases/latest/"
                    "skaffold-linux-amd64 && chmod +x /usr/local/bin/skaffold",
                ],
            },
            "brew": ["brew", "install", "skaffold"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
        "verify": ["skaffold", "version"],
        "update": {
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -Lo /usr/local/bin/skaffold "
                    "https://storage.googleapis.com/skaffold/releases/latest/"
                    "skaffold-linux-amd64 && chmod +x /usr/local/bin/skaffold",
                ],
            },
            "brew": ["brew", "upgrade", "skaffold"],
        },
    },

    # ── Category 6: snap tools with platform variants ───────────

    "kubectl": {
        "label": "kubectl (Kubernetes CLI)",
        "cli": "kubectl",
        "category": "k8s",
        # EVOLUTION NOTE (2026-02-26):
        # Full coverage audit. Added cli, category, all distro PM methods,
        # upgraded _default from hardcoded linux/amd64 to {os}/{arch}
        # portable binary download.
        #
        # _default uses {os} and {arch} placeholders — kubectl publishes
        # bare binaries (no archive) for linux and darwin, amd64 and arm64.
        # URL: dl.k8s.io/release/stable.txt → /bin/{os}/{arch}/kubectl
        #
        # Note: apt/zypper require adding external Kubernetes repos,
        # which are not set up by default on most systems. dnf has
        # kubernetes-client in standard Fedora repos. The _default
        # binary download is the most reliable path.
        "install": {
            "snap":   ["snap", "install", "kubectl", "--classic"],
            "apt":    ["apt-get", "install", "-y", "kubectl"],
            "dnf":    ["dnf", "install", "-y", "kubernetes-client"],
            "apk":    ["apk", "add", "kubectl"],
            "pacman": ["pacman", "-S", "--noconfirm", "kubectl"],
            "zypper": ["zypper", "install", "-y", "kubernetes-client"],
            "brew":   ["brew", "install", "kubectl"],
            "_default": [
                "bash", "-c",
                "curl -sSfL -o /tmp/kubectl "
                "\"https://dl.k8s.io/release/"
                "$(curl -sSfL https://dl.k8s.io/release/stable.txt)"
                "/bin/{os}/{arch}/kubectl\" && "
                "chmod +x /tmp/kubectl && "
                "mv /tmp/kubectl /usr/local/bin/kubectl",
            ],
        },
        "needs_sudo": {
            "snap": True, "apt": True, "dnf": True,
            "apk": True, "pacman": True, "zypper": True,
            "brew": False, "_default": True,
        },
        "install_via": {"_default": "binary_download"},
        "prefer": ["_default", "snap", "brew"],
        "requires": {"binaries": ["curl"]},
        "arch_map": {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "arm"},
        "version_constraint": {
            "type": "minor_range",
            "reference_hint": "cluster_version",
            "range": 1,
            "description": "kubectl should be within ±1 minor version of the K8s cluster.",
        },
        "verify": ["kubectl", "version", "--client"],
        "update": {
            "snap": ["snap", "refresh", "kubectl"],
            "apt": ["apt-get", "install", "--only-upgrade", "-y", "kubectl"],
            "dnf": ["dnf", "upgrade", "-y", "kubernetes-client"],
            "apk": ["apk", "upgrade", "kubectl"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "kubectl"],
            "zypper": ["zypper", "update", "-y", "kubernetes-client"],
            "brew": ["brew", "upgrade", "kubectl"],
            "_default": [
                "bash", "-c",
                "curl -sSfL -o /tmp/kubectl "
                "\"https://dl.k8s.io/release/"
                "$(curl -sSfL https://dl.k8s.io/release/stable.txt)"
                "/bin/{os}/{arch}/kubectl\" && "
                "chmod +x /tmp/kubectl && "
                "mv /tmp/kubectl /usr/local/bin/kubectl",
            ],
        },
    },

    "terraform": {
        "cli": "terraform",
        "label": "Terraform (infrastructure as code)",
        "category": "iac",
        "install": {
            "apt": [
                "bash", "-c",
                "wget -O- https://apt.releases.hashicorp.com/gpg"
                " | sudo gpg --dearmor -o"
                " /usr/share/keyrings/hashicorp-archive-keyring.gpg"
                " && echo \"deb [arch=$(dpkg --print-architecture)"
                " signed-by=/usr/share/keyrings/"
                "hashicorp-archive-keyring.gpg]"
                " https://apt.releases.hashicorp.com"
                " $(lsb_release -cs) main\""
                " | sudo tee /etc/apt/sources.list.d/hashicorp.list"
                " && sudo apt-get update"
                " && sudo apt-get install -y terraform",
            ],
            "dnf": [
                "bash", "-c",
                "sudo dnf install -y dnf-plugins-core"
                " && sudo dnf config-manager addrepo"
                " --from-repofile="
                "https://rpm.releases.hashicorp.com/fedora/"
                "hashicorp.repo"
                " && sudo dnf -y install terraform",
            ],
            "pacman": ["pacman", "-S", "--noconfirm", "terraform"],
            "snap": ["snap", "install", "terraform", "--classic"],
            "brew": [
                "bash", "-c",
                "brew tap hashicorp/tap"
                " && brew install hashicorp/tap/terraform",
            ],
            "_default": [
                "bash", "-c",
                "TF_VERSION=$(curl -sSf"
                " https://checkpoint.hashicorp.com/v1/check/terraform"
                " | python3 -c"
                " \"import sys,json;"
                "print(json.load(sys.stdin)['current_version'])\")"
                " && curl -sSfL -o /tmp/terraform.zip"
                " \"https://releases.hashicorp.com/terraform/"
                "${TF_VERSION}/terraform_${TF_VERSION}"
                "_{os}_{arch}.zip\""
                " && sudo unzip -o /tmp/terraform.zip"
                " -d /usr/local/bin"
                " && rm /tmp/terraform.zip",
            ],
        },
        "needs_sudo": {
            "apt": True,
            "dnf": True,
            "pacman": True,
            "snap": True,
            "brew": False,
            "_default": True,
        },
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl", "unzip"]},
        "arch_map": {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "arm"},
        "prefer": ["apt", "dnf", "pacman", "snap", "brew"],
        "verify": ["terraform", "--version"],
        "update": {
            "apt": [
                "bash", "-c",
                "sudo apt-get update"
                " && sudo apt-get install -y --only-upgrade terraform",
            ],
            "dnf": ["dnf", "upgrade", "-y", "terraform"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "terraform"],
            "snap": ["snap", "refresh", "terraform"],
            "brew": ["brew", "upgrade", "hashicorp/tap/terraform"],
            "_default": [
                "bash", "-c",
                "TF_VERSION=$(curl -sSf"
                " https://checkpoint.hashicorp.com/v1/check/terraform"
                " | python3 -c"
                " \"import sys,json;"
                "print(json.load(sys.stdin)['current_version'])\")"
                " && curl -sSfL -o /tmp/terraform.zip"
                " \"https://releases.hashicorp.com/terraform/"
                "${TF_VERSION}/terraform_${TF_VERSION}"
                "_{os}_{arch}.zip\""
                " && sudo unzip -o /tmp/terraform.zip"
                " -d /usr/local/bin"
                " && rm /tmp/terraform.zip",
            ],
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
    "gh": {
        "cli": "gh",
        "label": "GitHub CLI (GitHub from the terminal)",
        "category": "scm",
        # OFFICIAL install methods: apt (GPG + repo), dnf (repo), zypper (repo),
        # brew. COMMUNITY: apk (github-cli), pacman (github-cli).
        # Snap is OFFICIALLY DISCOURAGED by GitHub CLI maintainers.
        # _default downloads from GitHub releases.
        "install": {
            "apt": [
                "bash", "-c",
                "(type -p wget >/dev/null"
                " || (sudo apt update && sudo apt install wget -y))"
                " && sudo mkdir -p -m 755 /etc/apt/keyrings"
                " && out=$(mktemp)"
                " && wget -nv -O$out"
                " https://cli.github.com/packages/"
                "githubcli-archive-keyring.gpg"
                " && cat $out | sudo tee"
                " /etc/apt/keyrings/githubcli-archive-keyring.gpg"
                " > /dev/null"
                " && sudo chmod go+r"
                " /etc/apt/keyrings/githubcli-archive-keyring.gpg"
                " && echo \"deb [arch=$(dpkg --print-architecture)"
                " signed-by=/etc/apt/keyrings/"
                "githubcli-archive-keyring.gpg]"
                " https://cli.github.com/packages stable main\""
                " | sudo tee /etc/apt/sources.list.d/github-cli.list"
                " > /dev/null"
                " && sudo apt update"
                " && sudo apt install gh -y",
            ],
            "dnf": [
                "bash", "-c",
                "sudo dnf install -y 'dnf-command(config-manager)'"
                " && sudo dnf config-manager"
                " --add-repo"
                " https://cli.github.com/packages/rpm/gh-cli.repo"
                " && sudo dnf install -y gh --repo gh-cli",
            ],
            "apk": ["apk", "add", "github-cli"],
            "pacman": ["pacman", "-S", "--noconfirm", "github-cli"],
            "zypper": [
                "bash", "-c",
                "sudo zypper addrepo"
                " https://cli.github.com/packages/rpm/gh-cli.repo"
                " && sudo zypper ref"
                " && sudo zypper install -y gh",
            ],
            "brew": ["brew", "install", "gh"],
            "snap": ["snap", "install", "gh"],
            "_default": [
                "bash", "-c",
                "GH_VERSION=$(curl -sSf"
                " https://api.github.com/repos/cli/cli/releases/latest"
                " | grep '\"tag_name\"'"
                " | sed 's/.*\"v\\(.*\\)\".*/\\1/')"
                " && curl -sSfL -o /tmp/gh.tar.gz"
                " \"https://github.com/cli/cli/releases/download/"
                "v${GH_VERSION}/gh_${GH_VERSION}_{os}_{arch}.tar.gz\""
                " && sudo tar -xzf /tmp/gh.tar.gz"
                " -C /usr/local"
                " --strip-components=1"
                " && rm /tmp/gh.tar.gz",
            ],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True,
            "brew": False, "snap": True, "_default": True,
        },
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "arch_map": {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "armv6"},
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["gh", "--version"],
        "update": {
            "apt": [
                "bash", "-c",
                "sudo apt update && sudo apt install -y --only-upgrade gh",
            ],
            "dnf": ["dnf", "update", "-y", "gh"],
            "apk": ["apk", "upgrade", "github-cli"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "github-cli"],
            "zypper": [
                "bash", "-c",
                "sudo zypper ref && sudo zypper update -y gh",
            ],
            "brew": ["brew", "upgrade", "gh"],
            "snap": ["snap", "refresh", "gh"],
            "_default": [
                "bash", "-c",
                "GH_VERSION=$(curl -sSf"
                " https://api.github.com/repos/cli/cli/releases/latest"
                " | grep '\"tag_name\"'"
                " | sed 's/.*\"v\\(.*\\)\".*/\\1/')"
                " && curl -sSfL -o /tmp/gh.tar.gz"
                " \"https://github.com/cli/cli/releases/download/"
                "v${GH_VERSION}/gh_${GH_VERSION}_{os}_{arch}.tar.gz\""
                " && sudo tar -xzf /tmp/gh.tar.gz"
                " -C /usr/local"
                " --strip-components=1"
                " && rm /tmp/gh.tar.gz",
            ],
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
    "pip": {
        "cli": "pip",
        "label": "pip",
        "category": "python",
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
    "pipx": {
        "cli": "pipx",
        "label": "pipx (install & run Python CLI apps in isolated environments)",
        "category": "python",
        "install": {
            "apt": ["apt-get", "install", "-y", "pipx"],
            "dnf": ["dnf", "install", "-y", "pipx"],
            "apk": ["apk", "add", "pipx"],
            "pacman": ["pacman", "-S", "--noconfirm", "python-pipx"],
            "zypper": ["zypper", "install", "-y", "python3-pipx"],
            "brew": ["brew", "install", "pipx"],
            "_default": [
                "bash", "-c",
                "pip install --user pipx && python3 -m pipx ensurepath",
            ],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True,
            "brew": False, "_default": False,
        },
        "install_via": {"_default": "pip"},
        "prefer": ["apt", "dnf", "brew"],
        "requires": {"binaries": ["python3"]},
        "post_env": 'export PATH="$HOME/.local/bin:$PATH"',
        "verify": ["pipx", "--version"],
        "update": {
            "pip": ["pip", "install", "--upgrade", "pipx"],
            "brew": ["brew", "upgrade", "pipx"],
        },
    },
    "npm": {
        "cli": "npm",
        "label": "npm (Node Package Manager)",
        "category": "node",
        "install": {
            "apt":    ["apt-get", "install", "-y", "npm"],
            "dnf":    ["dnf", "install", "-y", "npm"],
            "apk":    ["apk", "add", "nodejs", "npm"],
            "pacman": ["pacman", "-S", "--noconfirm", "npm"],
            "zypper": ["zypper", "install", "-y", "npm20"],
            "brew":   ["brew", "install", "node"],
            "snap":   ["snap", "install", "node", "--classic"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
            "snap": True,
        },
        "requires": {
            "binaries": ["node"],
        },
        "verify": ["npm", "--version"],
        "update": {
            "_default": ["npm", "install", "-g", "npm"],
            "snap":     ["snap", "refresh", "node"],
            "brew":     ["brew", "upgrade", "node"],
        },
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
    # ── nvm ─────────────────────────────────────────────────────
    # nvm is a SHELL FUNCTION, not a binary.  shutil.which("nvm")
    # never works.  Verify checks for the nvm.sh file instead.
    # Only available via brew and the official installer script —
    # not in any Linux system PM repos.
    "nvm": {
        "cli": "nvm",
        "label": "nvm (Node Version Manager)",
        "category": "node",
        "install": {
            "brew": ["brew", "install", "nvm"],
            "_default": [
                "bash", "-c",
                "curl -o-"
                " https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.4/install.sh"
                " | bash",
            ],
        },
        "needs_sudo": {
            "brew": False,
            "_default": False,
        },
        "install_via": {"_default": "curl_pipe_bash"},
        "prefer": ["_default", "brew"],
        "requires": {
            "binaries": ["curl", "bash"],
        },
        "post_env": (
            'export NVM_DIR="$HOME/.nvm" && '
            '[ -s "$NVM_DIR/nvm.sh" ] && '
            'source "$NVM_DIR/nvm.sh"'
        ),
        "verify": ["bash", "-c", "[ -s \"$HOME/.nvm/nvm.sh\" ]"],
        "update": {
            "_default": [
                "bash", "-c",
                "cd \"$NVM_DIR\" && git fetch --tags origin"
                " && git checkout $(git describe --abbrev=0 --tags"
                " --match 'v[0-9]*' $(git rev-list --tags --max-count=1))"
                " && source \"$NVM_DIR/nvm.sh\"",
            ],
            "brew": ["brew", "upgrade", "nvm"],
        },
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
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sL https://github.com/gohugoio/hugo/releases/latest/"
                    "download/hugo_extended_{version}_linux-{arch}.tar.gz "
                    "| tar xz -C /usr/local/bin hugo",
                ],
            },
        },
        "needs_sudo": {
            "apt": True, "brew": False, "snap": True, "_default": True,
        },
        "install_via": {"_default": "github_release"},
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
        "cli": "gopls",
        "label": "gopls (Go language server — official)",
        "category": "go",
        # Official Go language server by the Go team.
        # go install only. NOT in any PM except go.
        "install": {
            "_default": ["go", "install", "golang.org/x/tools/gopls@latest"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "go"},
        "requires": {"binaries": ["go"]},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && gopls version'],
        "update": {"_default": ["go", "install",
                                "golang.org/x/tools/gopls@latest"]},
    },
    "golangci-lint": {
        "cli": "golangci-lint",
        "label": "golangci-lint (Go linters aggregator)",
        "category": "go",
        # Aggregates 100+ Go linters into one CLI.
        # Official installer script or brew. Also available via go install
        # but official docs recommend the script for reproducibility.
        "install": {
            "brew": ["brew", "install", "golangci-lint"],
            "_default": [
                "bash", "-c",
                "curl -sSfL https://raw.githubusercontent.com/golangci/"
                "golangci-lint/HEAD/install.sh | sh -s -- -b "
                "$(go env GOPATH)/bin",
            ],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["go", "curl"]},
        "prefer": ["brew"],
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && golangci-lint --version'],
        "update": {
            "brew": ["brew", "upgrade", "golangci-lint"],
            "_default": [
                "bash", "-c",
                "curl -sSfL https://raw.githubusercontent.com/golangci/"
                "golangci-lint/HEAD/install.sh | sh -s -- -b "
                "$(go env GOPATH)/bin",
            ],
        },
    },
    "delve": {
        "cli": "dlv",
        "label": "Delve (Go debugger — dlv)",
        "category": "go",
        # Go debugger. Binary name is dlv, not delve.
        # go install only.
        "install": {
            "_default": ["go", "install",
                         "github.com/go-delve/delve/cmd/dlv@latest"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "go"},
        "requires": {"binaries": ["go"]},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && dlv version'],
        "update": {"_default": ["go", "install",
                                "github.com/go-delve/delve/cmd/dlv@latest"]},
    },
    "air": {
        "cli": "air",
        "label": "Air (Go live reload for development)",
        "category": "go",
        # Live reload for Go apps during development.
        # go install only.
        "install": {
            "_default": ["go", "install",
                         "github.com/air-verse/air@latest"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "go"},
        "requires": {"binaries": ["go"]},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && air -v'],
        "update": {"_default": ["go", "install",
                                "github.com/air-verse/air@latest"]},
    },
    "mockgen": {
        "cli": "mockgen",
        "label": "mockgen (Go mock generator — uber/mock)",
        "category": "go",
        # Generates mock implementations for Go interfaces.
        # go install only. From uber/mock (successor to golang/mock).
        "install": {
            "_default": ["go", "install",
                         "go.uber.org/mock/mockgen@latest"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "go"},
        "requires": {"binaries": ["go"]},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && mockgen --version'],
        "update": {"_default": ["go", "install",
                                "go.uber.org/mock/mockgen@latest"]},
    },
    "protoc-gen-go": {
        "cli": "protoc-gen-go",
        "label": "protoc-gen-go (Go protobuf code generator)",
        "category": "go",
        # Generates Go code from .proto files.
        # go install only. Requires protoc (protobuf compiler) at runtime.
        "install": {
            "_default": ["go", "install",
                         "google.golang.org/protobuf/cmd/protoc-gen-go@latest"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "go"},
        "requires": {"binaries": ["go"]},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && protoc-gen-go --version'],
        "update": {"_default": ["go", "install",
                                "google.golang.org/protobuf/cmd/protoc-gen-go@latest"]},
    },

    # ════════════════════════════════════════════════════════════
    # Cloud CLIs
    # ════════════════════════════════════════════════════════════

    "aws-cli": {
        "cli": "aws",
        "label": "AWS CLI v2 (Amazon Web Services command-line interface)",
        "category": "cloud",
        # Written in Python but v2 ships as a self-contained installer.
        # Official installer is bundled zip with embedded Python — no pip deps.
        # brew formula: awscli. snap: aws-cli --classic.
        # pip has `awscli` but AWS discourages for v2 — use official installer.
        # NOT in apt (v1 only), dnf (v1 only), pacman, zypper.
        # apk has it in community repo but may lag versions.
        # _default uses $(uname -m) for runtime arch detection.
        # AWS URLs: awscli-exe-linux-x86_64.zip / awscli-exe-linux-aarch64.zip
        # uname -m outputs x86_64 or aarch64 — matches AWS naming exactly.
        "install": {
            "brew": ["brew", "install", "awscli"],
            "snap": ["snap", "install", "aws-cli", "--classic"],
            "_default": [
                "bash", "-c",
                'ARCH=$(uname -m) && '
                'curl "https://awscli.amazonaws.com/awscli-exe-linux-${ARCH}.zip"'
                ' -o /tmp/awscliv2.zip && cd /tmp && unzip -qo awscliv2.zip'
                ' && sudo ./aws/install --update && rm -rf /tmp/aws /tmp/awscliv2.zip',
            ],
        },
        "needs_sudo": {"brew": False, "snap": True, "_default": True},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "prefer": ["brew", "snap"],
        "verify": ["aws", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "awscli"],
            "snap": ["snap", "refresh", "aws-cli"],
            "_default": [
                "bash", "-c",
                'ARCH=$(uname -m) && '
                'curl "https://awscli.amazonaws.com/awscli-exe-linux-${ARCH}.zip"'
                ' -o /tmp/awscliv2.zip && cd /tmp && unzip -qo awscliv2.zip'
                ' && sudo ./aws/install --update && rm -rf /tmp/aws /tmp/awscliv2.zip',
            ],
        },
    },
    "gcloud": {
        "cli": "gcloud",
        "label": "Google Cloud SDK (gcloud CLI)",
        "category": "cloud",
        # Written in Python. Google provides official apt/dnf repos but
        # they require adding Google's signing key and repo — complex setup.
        # snap is simpler (google-cloud-cli --classic), brew works too.
        # _default installer pipes to bash — installs to $HOME.
        # NOT in apk, pacman, zypper.
        # apt/dnf methods omitted because they need repo setup (not simple apt install).
        "install": {
            "snap": ["snap", "install", "google-cloud-cli", "--classic"],
            "brew": ["brew", "install", "google-cloud-sdk"],
            "_default": [
                "bash", "-c",
                "curl -sSL https://sdk.cloud.google.com | bash -s -- "
                "--disable-prompts --install-dir=$HOME",
            ],
        },
        "needs_sudo": {"snap": True, "brew": False, "_default": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/google-cloud-sdk/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/google-cloud-sdk/bin:$PATH" && gcloud --version'],
        "prefer": ["snap", "brew"],
        "update": {
            "snap": ["snap", "refresh", "google-cloud-cli"],
            "brew": ["brew", "upgrade", "google-cloud-sdk"],
            "_default": ["bash", "-c",
                         'export PATH="$HOME/google-cloud-sdk/bin:$PATH" '
                         '&& gcloud components update --quiet'],
        },
    },
    "az-cli": {
        "cli": "az",
        "label": "Azure CLI (Microsoft Azure command-line interface)",
        "category": "cloud",
        # Written in Python. `pip install azure-cli` is the cross-platform
        # method Microsoft recommends for any Linux/macOS.
        # brew formula: azure-cli.
        # Microsoft also has distro-specific repo setup scripts
        # (InstallAzureCLIDeb for Debian, RPM repo for Fedora, etc.)
        # but those require repo + key setup and are distro-locked.
        # pip is the true universal fallback — works everywhere Python runs.
        # NOT in snap, apk, pacman.
        "install": {
            "brew": ["brew", "install", "azure-cli"],
            "_default": _PIP + ["install", "azure-cli"],
        },
        "needs_sudo": {"brew": False, "_default": False},
        "install_via": {"_default": "pip"},
        "prefer": ["brew"],
        "verify": ["az", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "azure-cli"],
            "_default": _PIP + ["install", "--upgrade", "azure-cli"],
        },
    },

    # ════════════════════════════════════════════════════════════
    # K8s extended
    # ════════════════════════════════════════════════════════════

    "kustomize": {
        "cli": "kustomize",
        "label": "Kustomize (Kubernetes config customization)",
        "category": "k8s",
        # kustomize is in apk (Alpine community), brew, snap.
        # NOT in apt, dnf, pacman, zypper standard repos.
        # Official curl|bash installer from kubernetes-sigs handles
        # OS/arch detection. GitHub releases use tool-prefixed tags
        # (kustomize/vX.Y.Z) with lowercase os/arch naming.
        "install": {
            "apk": ["apk", "add", "kustomize"],
            "brew": ["brew", "install", "kustomize"],
            "snap": ["snap", "install", "kustomize"],
            "_default": [
                "bash", "-c",
                "curl -s https://raw.githubusercontent.com/kubernetes-sigs/"
                "kustomize/master/hack/install_kustomize.sh | bash"
                " && mv kustomize /usr/local/bin/",
            ],
        },
        "needs_sudo": {
            "apk": True, "brew": False,
            "snap": True, "_default": True,
        },
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "arch_map": {
            "x86_64": "amd64", "aarch64": "arm64",
        },
        "prefer": ["apk", "brew"],
        "verify": ["kustomize", "version"],
        "update": {
            "apk": ["apk", "upgrade", "kustomize"],
            "brew": ["brew", "upgrade", "kustomize"],
            "snap": ["snap", "refresh", "kustomize"],
            "_default": [
                "bash", "-c",
                "curl -s https://raw.githubusercontent.com/kubernetes-sigs/"
                "kustomize/master/hack/install_kustomize.sh | bash"
                " && mv kustomize /usr/local/bin/",
            ],
        },
    },

    "k9s": {
        "cli": "k9s",
        "label": "K9s (Kubernetes TUI)",
        "category": "k8s",
        # k9s is in dnf (Fedora 42+), apk (Alpine community),
        # pacman (Arch community), brew, snap (--devmode).
        # NOT in apt or zypper standard repos.
        # GitHub releases: k9s_{OS}_{arch}.tar.gz (OS capitalized).
        "install": {
            "dnf": ["dnf", "install", "-y", "k9s"],
            "apk": ["apk", "add", "k9s"],
            "pacman": ["pacman", "-S", "--noconfirm", "k9s"],
            "brew": ["brew", "install", "k9s"],
            "snap": ["snap", "install", "k9s", "--devmode"],
            "_default": [
                "bash", "-c",
                "K9S_VERSION=$(curl -sSf"
                " https://api.github.com/repos/derailed/k9s/releases/latest"
                " | grep -o '\"tag_name\":\"[^\"]*\"'"
                " | cut -d'\"' -f4)"
                " && curl -sSfL"
                " https://github.com/derailed/k9s/releases/download/"
                "${K9S_VERSION}/k9s_Linux_{arch}.tar.gz"
                " | tar -xz -C /usr/local/bin k9s",
            ],
        },
        "needs_sudo": {
            "dnf": True, "apk": True, "pacman": True,
            "brew": False, "snap": True, "_default": True,
        },
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "arch_map": {
            "x86_64": "amd64", "aarch64": "arm64", "armv7l": "armv7",
        },
        "prefer": ["dnf", "apk", "pacman", "brew"],
        "verify": ["k9s", "version"],
        "update": {
            "dnf": ["dnf", "upgrade", "-y", "k9s"],
            "apk": ["apk", "upgrade", "k9s"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "k9s"],
            "brew": ["brew", "upgrade", "k9s"],
            "snap": ["snap", "refresh", "k9s"],
            "_default": [
                "bash", "-c",
                "K9S_VERSION=$(curl -sSf"
                " https://api.github.com/repos/derailed/k9s/releases/latest"
                " | grep -o '\"tag_name\":\"[^\"]*\"'"
                " | cut -d'\"' -f4)"
                " && curl -sSfL"
                " https://github.com/derailed/k9s/releases/download/"
                "${K9S_VERSION}/k9s_Linux_{arch}.tar.gz"
                " | tar -xz -C /usr/local/bin k9s",
            ],
        },
    },

    "stern": {
        "cli": "stern",
        "label": "Stern (multi-pod K8s log tailing)",
        "category": "k8s",
        # stern is NOT in any system PM repos (apt, dnf, apk, pacman, zypper).
        # Only available via brew and GitHub releases.
        # GitHub releases: stern_{version}_{os}_{arch}.tar.gz
        # OS: linux, darwin (lowercase). Arch: amd64, arm64, arm.
        # Version in tag has 'v' prefix, in filename it does not.
        "install": {
            "brew": ["brew", "install", "stern"],
            "_default": [
                "bash", "-c",
                "VERSION=$(curl -sSf https://api.github.com/repos/stern/stern"
                "/releases/latest | grep -o '\"tag_name\": \"v[^\"]*\"'"
                " | cut -d'\"' -f4 | sed 's/^v//') && "
                "curl -sSfL https://github.com/stern/stern/releases/download/"
                "v${VERSION}/stern_${VERSION}_{os}_{arch}.tar.gz"
                " | tar -xz -C /usr/local/bin stern",
            ],
        },
        "needs_sudo": {"brew": False, "_default": True},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "arch_map": {
            "x86_64": "amd64", "aarch64": "arm64", "armv7l": "arm",
        },
        "prefer": ["brew"],
        "verify": ["stern", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "stern"],
            "_default": [
                "bash", "-c",
                "VERSION=$(curl -sSf https://api.github.com/repos/stern/stern"
                "/releases/latest | grep -o '\"tag_name\": \"v[^\"]*\"'"
                " | cut -d'\"' -f4 | sed 's/^v//') && "
                "curl -sSfL https://github.com/stern/stern/releases/download/"
                "v${VERSION}/stern_${VERSION}_{os}_{arch}.tar.gz"
                " | tar -xz -C /usr/local/bin stern",
            ],
        },
    },

    "kubectx": {
        "cli": "kubectx",
        "label": "kubectx + kubens (K8s context/namespace switcher)",
        "category": "k8s",
        # kubectx installs BOTH kubectx and kubens binaries.
        # NOT in apt, dnf, apk, zypper standard repos.
        # Available in pacman (community), brew, snap.
        # GitHub releases: separate tar.gz for kubectx and kubens.
        # Uses x86_64 (not amd64!) in asset names, arm64, armv7.
        # Tag version IS included in filename: kubectx_v0.9.5_linux_x86_64.tar.gz
        "install": {
            "pacman": ["pacman", "-S", "--noconfirm", "kubectx"],
            "brew": ["brew", "install", "kubectx"],
            "snap": ["snap", "install", "kubectx", "--classic"],
            "_default": [
                "bash", "-c",
                "VERSION=$(curl -sSf https://api.github.com/repos/ahmetb/"
                "kubectx/releases/latest | grep -o '\"tag_name\": \"[^\"]*\"'"
                " | cut -d'\"' -f4) && "
                "curl -sSfL https://github.com/ahmetb/kubectx/releases/"
                "download/${VERSION}/kubectx_${VERSION}_{os}_{arch}.tar.gz"
                " | tar -xz -C /usr/local/bin kubectx && "
                "curl -sSfL https://github.com/ahmetb/kubectx/releases/"
                "download/${VERSION}/kubens_${VERSION}_{os}_{arch}.tar.gz"
                " | tar -xz -C /usr/local/bin kubens",
            ],
        },
        "needs_sudo": {
            "pacman": True, "brew": False,
            "snap": True, "_default": True,
        },
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "arch_map": {
            "aarch64": "arm64", "armv7l": "armv7",
        },
        "prefer": ["pacman", "brew"],
        "verify": ["kubectx", "--help"],
        "update": {
            "pacman": ["pacman", "-Syu", "--noconfirm", "kubectx"],
            "brew": ["brew", "upgrade", "kubectx"],
            "snap": ["snap", "refresh", "kubectx"],
            "_default": [
                "bash", "-c",
                "VERSION=$(curl -sSf https://api.github.com/repos/ahmetb/"
                "kubectx/releases/latest | grep -o '\"tag_name\": \"[^\"]*\"'"
                " | cut -d'\"' -f4) && "
                "curl -sSfL https://github.com/ahmetb/kubectx/releases/"
                "download/${VERSION}/kubectx_${VERSION}_{os}_{arch}.tar.gz"
                " | tar -xz -C /usr/local/bin kubectx && "
                "curl -sSfL https://github.com/ahmetb/kubectx/releases/"
                "download/${VERSION}/kubens_${VERSION}_{os}_{arch}.tar.gz"
                " | tar -xz -C /usr/local/bin kubens",
            ],
        },
    },

    "argocd-cli": {
        "cli": "argocd",
        "label": "Argo CD CLI (GitOps continuous delivery)",
        "category": "k8s",
        # argocd is NOT in apt, dnf, apk, zypper, snap.
        # Available in pacman (AUR/community) and brew.
        # GitHub releases (argoproj/argo-cd): raw binaries, no archive.
        # Asset naming: argocd-{os}-{arch} (no extension).
        # OS: linux, darwin. Arch: amd64, arm64.
        "install": {
            "pacman": ["pacman", "-S", "--noconfirm", "argocd"],
            "brew": ["brew", "install", "argocd"],
            "_default": [
                "bash", "-c",
                "curl -sSfL -o /tmp/argocd https://github.com/argoproj/"
                "argo-cd/releases/latest/download/argocd-{os}-{arch}"
                " && chmod +x /tmp/argocd"
                " && mv /tmp/argocd /usr/local/bin/argocd",
            ],
        },
        "needs_sudo": {
            "pacman": True, "brew": False, "_default": True,
        },
        "install_via": {"_default": "binary_download"},
        "requires": {"binaries": ["curl"]},
        "arch_map": {
            "x86_64": "amd64", "aarch64": "arm64",
        },
        "prefer": ["pacman", "brew"],
        "verify": ["argocd", "version", "--client"],
        "update": {
            "pacman": ["pacman", "-Syu", "--noconfirm", "argocd"],
            "brew": ["brew", "upgrade", "argocd"],
            "_default": [
                "bash", "-c",
                "curl -sSfL -o /tmp/argocd https://github.com/argoproj/"
                "argo-cd/releases/latest/download/argocd-{os}-{arch}"
                " && chmod +x /tmp/argocd"
                " && mv /tmp/argocd /usr/local/bin/argocd",
            ],
        },
    },

    "flux": {
        "cli": "flux",
        "label": "Flux CD CLI (GitOps for Kubernetes)",
        "category": "k8s",
        # flux is NOT in apt, dnf, apk, zypper, snap standard repos.
        # brew uses a custom tap: fluxcd/tap/flux.
        # Official curl|bash installer handles OS/arch detection.
        # GitHub releases (fluxcd/flux2): flux_{version}_{os}_{arch}.tar.gz
        # Version in tag has 'v' prefix, in filename it does not.
        "install": {
            "brew": ["brew", "install", "fluxcd/tap/flux"],
            "_default": [
                "bash", "-c",
                "curl -s https://fluxcd.io/install.sh | bash",
            ],
        },
        "needs_sudo": {"brew": False, "_default": True},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "arch_map": {
            "x86_64": "amd64", "aarch64": "arm64", "armv7l": "arm",
        },
        "prefer": ["brew"],
        "verify": ["flux", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "fluxcd/tap/flux"],
            "_default": [
                "bash", "-c",
                "curl -s https://fluxcd.io/install.sh | bash",
            ],
        },
    },

    "istioctl": {
        "cli": "istioctl",
        "label": "istioctl (Istio service mesh CLI)",
        "category": "k8s",
        # istioctl is NOT in apt, dnf, apk, pacman, zypper, snap.
        # Only available via brew and GitHub releases.
        # GitHub releases (istio/istio): two asset sets:
        #   istio-{ver}-{os}-{arch}.tar.gz  (full distro + samples)
        #   istioctl-{ver}-{os}-{arch}.tar.gz (CLI only) ← use this
        # Tag has NO 'v' prefix: 1.29.0 (not v1.29.0).
        # OS: linux (NOT darwin — macOS uses 'osx').
        # Arch: amd64, arm64, armv7 (Go-standard).
        "install": {
            "brew": ["brew", "install", "istioctl"],
            "_default": [
                "bash", "-c",
                "VERSION=$(curl -sSf https://api.github.com/repos/istio/istio"
                "/releases/latest | grep -o '\"tag_name\": \"[^\"]*\"'"
                " | cut -d'\"' -f4) && "
                "curl -sSfL https://github.com/istio/istio/releases/download/"
                "${VERSION}/istioctl-${VERSION}-{os}-{arch}.tar.gz"
                " | tar -xz -C /usr/local/bin istioctl",
            ],
        },
        "needs_sudo": {"brew": False, "_default": True},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "arch_map": {
            "x86_64": "amd64", "aarch64": "arm64", "armv7l": "armv7",
        },
        "prefer": ["brew"],
        "verify": ["istioctl", "version", "--remote=false"],
        "update": {
            "brew": ["brew", "upgrade", "istioctl"],
            "_default": [
                "bash", "-c",
                "VERSION=$(curl -sSf https://api.github.com/repos/istio/istio"
                "/releases/latest | grep -o '\"tag_name\": \"[^\"]*\"'"
                " | cut -d'\"' -f4) && "
                "curl -sSfL https://github.com/istio/istio/releases/download/"
                "${VERSION}/istioctl-${VERSION}-{os}-{arch}.tar.gz"
                " | tar -xz -C /usr/local/bin istioctl",
            ],
        },
    },

    "helmfile": {
        "cli": "helmfile",
        "label": "Helmfile (declarative Helm chart management)",
        "category": "k8s",
        # helmfile is NOT in apt, dnf, apk, zypper standard repos.
        # Available in pacman (community), brew, snap.
        # GitHub releases: helmfile_{version}_{os}_{arch}.tar.gz
        # OS: linux, darwin (lowercase). Arch: amd64, arm64.
        # Version in tag has 'v' prefix, in filename it does not.
        # Requires helm as a runtime dependency.
        "install": {
            "pacman": ["pacman", "-S", "--noconfirm", "helmfile"],
            "brew": ["brew", "install", "helmfile"],
            "snap": ["snap", "install", "helmfile", "--classic"],
            "_default": [
                "bash", "-c",
                "VERSION=$(curl -sSf https://api.github.com/repos/helmfile/"
                "helmfile/releases/latest | grep -o '\"tag_name\": \"v[^\"]*\"'"
                " | cut -d'\"' -f4 | sed 's/^v//') && "
                "curl -sSfL https://github.com/helmfile/helmfile/releases/"
                "download/v${VERSION}/helmfile_${VERSION}_{os}_{arch}.tar.gz"
                " | tar -xz -C /usr/local/bin helmfile",
            ],
        },
        "needs_sudo": {
            "pacman": True, "brew": False,
            "snap": True, "_default": True,
        },
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl", "helm"]},
        "arch_map": {
            "x86_64": "amd64", "aarch64": "arm64",
        },
        "prefer": ["pacman", "brew"],
        "verify": ["helmfile", "--version"],
        "update": {
            "pacman": ["pacman", "-Syu", "--noconfirm", "helmfile"],
            "brew": ["brew", "upgrade", "helmfile"],
            "snap": ["snap", "refresh", "helmfile"],
            "_default": [
                "bash", "-c",
                "VERSION=$(curl -sSf https://api.github.com/repos/helmfile/"
                "helmfile/releases/latest | grep -o '\"tag_name\": \"v[^\"]*\"'"
                " | cut -d'\"' -f4 | sed 's/^v//') && "
                "curl -sSfL https://github.com/helmfile/helmfile/releases/"
                "download/v${VERSION}/helmfile_${VERSION}_{os}_{arch}.tar.gz"
                " | tar -xz -C /usr/local/bin helmfile",
            ],
        },
    },


    # ════════════════════════════════════════════════════════════
    # Security tools
    # ════════════════════════════════════════════════════════════

    "snyk": {
        "cli": "snyk",
        "label": "Snyk CLI (security vulnerability scanner)",
        "category": "security",
        # snyk is NOT in apt, dnf, apk, pacman, zypper, snap.
        # Available via npm (canonical) and brew (snyk-cli, not snyk!).
        # Also provides standalone binaries from CDN:
        #   https://static.snyk.io/cli/latest/snyk-linux
        #   https://static.snyk.io/cli/latest/snyk-linux-arm64
        # But npm is the official/recommended install method.
        "install": {
            "_default": ["npm", "install", "-g", "snyk"],
            "brew": ["brew", "install", "snyk-cli"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "prefer": ["brew"],
        "verify": ["snyk", "--version"],
        "update": {
            "_default": ["npm", "update", "-g", "snyk"],
            "brew": ["brew", "upgrade", "snyk-cli"],
        },
    },

    "grype": {
        "cli": "grype",
        "label": "Grype (container vulnerability scanner)",
        "category": "security",
        # grype is NOT in apt, dnf, apk, pacman, zypper standard repos.
        # Available via brew, snap, and official curl|bash installer.
        # GitHub releases (anchore/grype): .tar.gz, .deb, .rpm
        # Asset naming: grype_{ver}_{os}_{arch}.tar.gz
        # Tag has 'v' prefix, filename does not.
        # OS: linux, darwin. Arch: amd64, arm64.
        "install": {
            "brew": ["brew", "install", "grype"],
            "snap": ["snap", "install", "grype"],
            "_default": [
                "bash", "-c",
                "curl -sSfL https://raw.githubusercontent.com/anchore/grype/"
                "main/install.sh | sh -s -- -b /usr/local/bin",
            ],
        },
        "needs_sudo": {"brew": False, "snap": True, "_default": True},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "arch_map": {
            "x86_64": "amd64", "aarch64": "arm64",
        },
        "prefer": ["brew"],
        "verify": ["grype", "version"],
        "update": {
            "brew": ["brew", "upgrade", "grype"],
            "snap": ["snap", "refresh", "grype"],
            "_default": [
                "bash", "-c",
                "curl -sSfL https://raw.githubusercontent.com/anchore/grype/"
                "main/install.sh | sh -s -- -b /usr/local/bin",
            ],
        },
    },

    "gitleaks": {
        "cli": "gitleaks",
        "label": "Gitleaks (Git secret scanner)",
        "category": "security",
        # gitleaks is NOT in apt, dnf, apk, zypper, snap.
        # Available in pacman (community) and brew.
        # GitHub releases (gitleaks/gitleaks): .tar.gz
        # Asset naming: gitleaks_{ver}_{os}_{arch}.tar.gz
        # NON-STANDARD arch: uses 'x64' (NOT amd64!) for x86_64.
        # arm64 is standard. OS: linux, darwin.
        # Tag has 'v' prefix, filename does not.
        "install": {
            "pacman": ["pacman", "-S", "--noconfirm", "gitleaks"],
            "brew": ["brew", "install", "gitleaks"],
            "_default": [
                "bash", "-c",
                "VERSION=$(curl -sSf https://api.github.com/repos/gitleaks/"
                "gitleaks/releases/latest | grep -o '\"tag_name\": \"v[^\"]*\"'"
                " | cut -d'\"' -f4 | sed 's/^v//') && "
                "curl -sSfL https://github.com/gitleaks/gitleaks/releases/"
                "download/v${VERSION}/gitleaks_${VERSION}_{os}_{arch}.tar.gz"
                " | tar -xz -C /usr/local/bin gitleaks",
            ],
        },
        "needs_sudo": {
            "pacman": True, "brew": False, "_default": True,
        },
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "arch_map": {
            "x86_64": "x64", "aarch64": "arm64",
        },
        "prefer": ["pacman", "brew"],
        "verify": ["gitleaks", "version"],
        "update": {
            "pacman": ["pacman", "-Syu", "--noconfirm", "gitleaks"],
            "brew": ["brew", "upgrade", "gitleaks"],
            "_default": [
                "bash", "-c",
                "VERSION=$(curl -sSf https://api.github.com/repos/gitleaks/"
                "gitleaks/releases/latest | grep -o '\"tag_name\": \"v[^\"]*\"'"
                " | cut -d'\"' -f4 | sed 's/^v//') && "
                "curl -sSfL https://github.com/gitleaks/gitleaks/releases/"
                "download/v${VERSION}/gitleaks_${VERSION}_{os}_{arch}.tar.gz"
                " | tar -xz -C /usr/local/bin gitleaks",
            ],
        },
    },

    "tfsec": {
        "cli": "tfsec",
        "label": "tfsec (Terraform security scanner — deprecated, use Trivy)",
        "category": "security",
        # DEPRECATED: tfsec is merged into Trivy (aquasecurity).
        # Still gets maintenance releases but no new features.
        # NOT in apt, dnf, apk, zypper, snap.
        # Available in pacman (AUR) and brew.
        # GitHub releases: raw binaries (tfsec-{os}-{arch})
        #   and tar.gz (tfsec_{ver}_{os}_{arch}.tar.gz).
        # Using raw binary download (simpler, no extraction).
        # OS: linux, darwin. Arch: amd64, arm64 (Go-standard).
        # Latest release redirect works for raw binaries.
        "install": {
            "pacman": ["pacman", "-S", "--noconfirm", "tfsec"],
            "brew": ["brew", "install", "tfsec"],
            "_default": [
                "bash", "-c",
                "curl -sSfL -o /tmp/tfsec https://github.com/aquasecurity/"
                "tfsec/releases/latest/download/tfsec-{os}-{arch}"
                " && chmod +x /tmp/tfsec && mv /tmp/tfsec /usr/local/bin/tfsec",
            ],
        },
        "needs_sudo": {
            "pacman": True, "brew": False, "_default": True,
        },
        "install_via": {"_default": "binary_download"},
        "requires": {"binaries": ["curl"]},
        "arch_map": {
            "x86_64": "amd64", "aarch64": "arm64",
        },
        "prefer": ["pacman", "brew"],
        "verify": ["tfsec", "--version"],
        "update": {
            "pacman": ["pacman", "-Syu", "--noconfirm", "tfsec"],
            "brew": ["brew", "upgrade", "tfsec"],
            "_default": [
                "bash", "-c",
                "curl -sSfL -o /tmp/tfsec https://github.com/aquasecurity/"
                "tfsec/releases/latest/download/tfsec-{os}-{arch}"
                " && chmod +x /tmp/tfsec && mv /tmp/tfsec /usr/local/bin/tfsec",
            ],
        },
    },

    "checkov": {
        "cli": "checkov",
        "label": "Checkov (IaC security scanner)",
        "category": "security",
        # checkov is a Python package — pip is canonical.
        # Also available via brew (handles Python deps automatically).
        # NOT in apt, dnf, apk, pacman, zypper, snap.
        # Requires Python 3.9–3.12.
        # Heavy dependency tree — brew is simpler for end users.
        "install": {
            "brew": ["brew", "install", "checkov"],
            "_default": _PIP + ["install", "checkov"],
        },
        "needs_sudo": {"brew": False, "_default": False},
        "install_via": {"_default": "pip"},
        "prefer": ["brew"],
        "verify": ["checkov", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "checkov"],
            "_default": _PIP + ["install", "--upgrade", "checkov"],
        },
    },

    "semgrep": {
        "cli": "semgrep",
        "label": "Semgrep (SAST — static analysis security testing)",
        "category": "security",
        # semgrep is a Python package — pip is canonical.
        # Also available via brew and snap (with ARM64 support).
        # NOT in apt, dnf, apk, pacman, zypper.
        # Requires Python 3.10+.
        # snap is good for ARM64 / Raspbian where pip wheels may fail.
        "install": {
            "brew": ["brew", "install", "semgrep"],
            "snap": ["snap", "install", "semgrep"],
            "_default": _PIP + ["install", "semgrep"],
        },
        "needs_sudo": {"brew": False, "snap": True, "_default": False},
        "install_via": {"_default": "pip"},
        "prefer": ["brew", "snap"],
        "verify": ["semgrep", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "semgrep"],
            "snap": ["snap", "refresh", "semgrep"],
            "_default": _PIP + ["install", "--upgrade", "semgrep"],
        },
    },

    "detect-secrets": {
        "cli": "detect-secrets",
        "label": "detect-secrets (Yelp secret detection tool)",
        "category": "security",
        # detect-secrets is a pure Python package — pip is canonical.
        # Also available via brew.
        # NOT in apt, dnf, apk, pacman (standard), zypper, snap.
        # Lightweight Python package, few native deps.
        "install": {
            "brew": ["brew", "install", "detect-secrets"],
            "_default": _PIP + ["install", "detect-secrets"],
        },
        "needs_sudo": {"brew": False, "_default": False},
        "install_via": {"_default": "pip"},
        "prefer": ["brew"],
        "verify": ["detect-secrets", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "detect-secrets"],
            "_default": _PIP + ["install", "--upgrade", "detect-secrets"],
        },
    },


    # ════════════════════════════════════════════════════════════
    # Container tools
    # ════════════════════════════════════════════════════════════

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

    # ════════════════════════════════════════════════════════════
    # Dev tools
    # ════════════════════════════════════════════════════════════

    "direnv": {
        "cli": "direnv",
        "label": "direnv (environment switcher for the shell)",
        "category": "devtools",
        # Go-based. Auto-loads/unloads env vars per directory.
        # Available in ALL native PMs + snap + official installer.
        # Verify: "direnv version" (no --)
        "install": {
            "apt": ["apt-get", "install", "-y", "direnv"],
            "dnf": ["dnf", "install", "-y", "direnv"],
            "apk": ["apk", "add", "direnv"],
            "pacman": ["pacman", "-S", "--noconfirm", "direnv"],
            "zypper": ["zypper", "install", "-y", "direnv"],
            "brew": ["brew", "install", "direnv"],
            "snap": ["snap", "install", "direnv"],
            "_default": [
                "bash", "-c",
                "curl -sfL https://direnv.net/install.sh | bash",
            ],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
            "snap": True, "_default": True,
        },
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew", "snap"],
        "verify": ["direnv", "version"],
        "update": {
            "apt": ["apt-get", "install", "-y", "--only-upgrade", "direnv"],
            "dnf": ["dnf", "upgrade", "-y", "direnv"],
            "apk": ["apk", "upgrade", "direnv"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "direnv"],
            "zypper": ["zypper", "update", "-y", "direnv"],
            "brew": ["brew", "upgrade", "direnv"],
            "snap": ["snap", "refresh", "direnv"],
            "_default": [
                "bash", "-c",
                "curl -sfL https://direnv.net/install.sh | bash",
            ],
        },
    },
    "tmux": {
        "cli": "tmux",
        "label": "tmux (terminal multiplexer)",
        "category": "devtools",
        # C-based. Classic Unix tool.
        # Available in ALL native PMs — no _default needed.
        # Verify: "tmux -V" (capital V, no --)
        "install": {
            "apt": ["apt-get", "install", "-y", "tmux"],
            "dnf": ["dnf", "install", "-y", "tmux"],
            "apk": ["apk", "add", "tmux"],
            "pacman": ["pacman", "-S", "--noconfirm", "tmux"],
            "zypper": ["zypper", "install", "-y", "tmux"],
            "brew": ["brew", "install", "tmux"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["tmux", "-V"],
        "update": {
            "apt": ["apt-get", "install", "-y", "--only-upgrade", "tmux"],
            "dnf": ["dnf", "upgrade", "-y", "tmux"],
            "apk": ["apk", "upgrade", "tmux"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "tmux"],
            "zypper": ["zypper", "update", "-y", "tmux"],
            "brew": ["brew", "upgrade", "tmux"],
        },
    },
    "fzf": {
        "cli": "fzf",
        "label": "fzf (command-line fuzzy finder)",
        "category": "devtools",
        # Go-based. By junegunn.
        # Available in ALL native PMs.
        # _default: git clone to ~/.fzf (user-local, no sudo).
        # Snap exists but unofficial (fzf-slowday) — skipped.
        "install": {
            "apt": ["apt-get", "install", "-y", "fzf"],
            "dnf": ["dnf", "install", "-y", "fzf"],
            "apk": ["apk", "add", "fzf"],
            "pacman": ["pacman", "-S", "--noconfirm", "fzf"],
            "zypper": ["zypper", "install", "-y", "fzf"],
            "brew": ["brew", "install", "fzf"],
            "_default": [
                "bash", "-c",
                "git clone --depth 1 https://github.com/junegunn/fzf.git "
                "~/.fzf && ~/.fzf/install --all",
            ],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
            "_default": False,
        },
        "requires": {"binaries": ["git"]},
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["fzf", "--version"],
        "update": {
            "apt": ["apt-get", "install", "-y", "--only-upgrade", "fzf"],
            "dnf": ["dnf", "upgrade", "-y", "fzf"],
            "apk": ["apk", "upgrade", "fzf"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "fzf"],
            "zypper": ["zypper", "update", "-y", "fzf"],
            "brew": ["brew", "upgrade", "fzf"],
            "_default": [
                "bash", "-c",
                "cd ~/.fzf && git pull && ./install --all",
            ],
        },
    },
    "ripgrep": {
        "label": "ripgrep (rg — recursive grep replacement)",
        "category": "devtools",
        "cli": "rg",
        # Rust-based. By BurntSushi.
        # Available in ALL native PMs.
        # Package name is "ripgrep" but binary is "rg".
        "install": {
            "apt": ["apt-get", "install", "-y", "ripgrep"],
            "dnf": ["dnf", "install", "-y", "ripgrep"],
            "apk": ["apk", "add", "ripgrep"],
            "pacman": ["pacman", "-S", "--noconfirm", "ripgrep"],
            "zypper": ["zypper", "install", "-y", "ripgrep"],
            "brew": ["brew", "install", "ripgrep"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["rg", "--version"],
        "update": {
            "apt": ["apt-get", "install", "-y", "--only-upgrade", "ripgrep"],
            "dnf": ["dnf", "upgrade", "-y", "ripgrep"],
            "apk": ["apk", "upgrade", "ripgrep"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "ripgrep"],
            "zypper": ["zypper", "update", "-y", "ripgrep"],
            "brew": ["brew", "upgrade", "ripgrep"],
        },
    },
    "bat": {
        "cli": "bat",
        "label": "bat (cat replacement with syntax highlighting)",
        "category": "devtools",
        # Rust-based. By sharkdp.
        # Available in ALL native PMs.
        # Note: on Debian/Ubuntu older versions, binary may be "batcat".
        "install": {
            "apt": ["apt-get", "install", "-y", "bat"],
            "dnf": ["dnf", "install", "-y", "bat"],
            "apk": ["apk", "add", "bat"],
            "pacman": ["pacman", "-S", "--noconfirm", "bat"],
            "zypper": ["zypper", "install", "-y", "bat"],
            "brew": ["brew", "install", "bat"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["bat", "--version"],
        "update": {
            "apt": ["apt-get", "install", "-y", "--only-upgrade", "bat"],
            "dnf": ["dnf", "upgrade", "-y", "bat"],
            "apk": ["apk", "upgrade", "bat"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "bat"],
            "zypper": ["zypper", "update", "-y", "bat"],
            "brew": ["brew", "upgrade", "bat"],
        },
    },
    "eza": {
        "cli": "eza",
        "label": "eza (modern ls replacement)",
        "category": "devtools",
        # Rust-based. Fork of exa (unmaintained).
        # Available: apt (24.04+), dnf, pacman, brew.
        # NOT in apk, zypper.
        # _default: cargo install — needs Rust toolchain.
        "install": {
            "apt": ["apt-get", "install", "-y", "eza"],
            "dnf": ["dnf", "install", "-y", "eza"],
            "pacman": ["pacman", "-S", "--noconfirm", "eza"],
            "brew": ["brew", "install", "eza"],
            "_default": ["cargo", "install", "eza"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "pacman": True,
            "brew": False, "_default": False,
        },
        "install_via": {"_default": "cargo"},
        "prefer": ["apt", "dnf", "pacman", "brew"],
        "verify": ["eza", "--version"],
        "update": {
            "apt": ["apt-get", "install", "-y", "--only-upgrade", "eza"],
            "dnf": ["dnf", "upgrade", "-y", "eza"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "eza"],
            "brew": ["brew", "upgrade", "eza"],
            "_default": ["cargo", "install", "eza"],
        },
    },
    "fd": {
        "cli": "fd",
        "label": "fd (modern find replacement)",
        "category": "devtools",
        # Rust-based. By sharkdp.
        # Available in ALL native PMs.
        # Package name varies: fd-find (apt, dnf) vs fd (apk, pacman, zypper, brew).
        "install": {
            "apt": ["apt-get", "install", "-y", "fd-find"],
            "dnf": ["dnf", "install", "-y", "fd-find"],
            "apk": ["apk", "add", "fd"],
            "pacman": ["pacman", "-S", "--noconfirm", "fd"],
            "zypper": ["zypper", "install", "-y", "fd"],
            "brew": ["brew", "install", "fd"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["fd", "--version"],
        "update": {
            "apt": ["apt-get", "install", "-y", "--only-upgrade", "fd-find"],
            "dnf": ["dnf", "upgrade", "-y", "fd-find"],
            "apk": ["apk", "upgrade", "fd"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "fd"],
            "zypper": ["zypper", "update", "-y", "fd"],
            "brew": ["brew", "upgrade", "fd"],
        },
    },
    "starship": {
        "cli": "starship",
        "label": "Starship (cross-shell customizable prompt)",
        "category": "devtools",
        # Rust-based. Minimal, blazing-fast prompt for any shell.
        # Available: apt (Debian 13+), apk (3.13+), pacman, zypper, brew, snap.
        # dnf requires COPR repo (atim/starship) — non-standard, skipped.
        # _default: official installer script from starship.rs.
        # Recommends Nerd Font for proper icon display.
        "install": {
            "apt": ["apt-get", "install", "-y", "starship"],
            "apk": ["apk", "add", "starship"],
            "pacman": ["pacman", "-S", "--noconfirm", "starship"],
            "zypper": ["zypper", "install", "-y", "starship"],
            "brew": ["brew", "install", "starship"],
            "snap": ["snap", "install", "starship"],
            "_default": [
                "bash", "-c",
                "curl -sS https://starship.rs/install.sh | sh -s -- -y",
            ],
        },
        "needs_sudo": {
            "apt": True, "apk": True, "pacman": True,
            "zypper": True, "brew": False, "snap": True,
            "_default": True,
        },
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "prefer": ["apt", "apk", "pacman", "zypper", "brew", "snap"],
        "verify": ["starship", "--version"],
        "update": {
            "apt": ["apt-get", "install", "-y", "--only-upgrade", "starship"],
            "apk": ["apk", "upgrade", "starship"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "starship"],
            "zypper": ["zypper", "update", "-y", "starship"],
            "brew": ["brew", "upgrade", "starship"],
            "snap": ["snap", "refresh", "starship"],
            "_default": [
                "bash", "-c",
                "curl -sS https://starship.rs/install.sh | sh -s -- -y",
            ],
        },
    },
    "zoxide": {
        "cli": "zoxide",
        "label": "zoxide (smarter cd command)",
        "category": "devtools",
        # Rust-based. By ajeetdsouza.
        # Learns most-used directories, provides smart jump.
        # Available: apt, dnf, apk, pacman, zypper, brew.
        # _default: official installer script (no sudo, ~/.local/bin).
        # NOT available as snap.
        "install": {
            "apt": ["apt-get", "install", "-y", "zoxide"],
            "dnf": ["dnf", "install", "-y", "zoxide"],
            "apk": ["apk", "add", "zoxide"],
            "pacman": ["pacman", "-S", "--noconfirm", "zoxide"],
            "zypper": ["zypper", "install", "-y", "zoxide"],
            "brew": ["brew", "install", "zoxide"],
            "_default": [
                "bash", "-c",
                "curl -sS https://raw.githubusercontent.com/ajeetdsouza/"
                "zoxide/main/install.sh | bash",
            ],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
            "_default": False,
        },
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["zoxide", "--version"],
        "update": {
            "apt": ["apt-get", "install", "-y", "--only-upgrade", "zoxide"],
            "dnf": ["dnf", "upgrade", "-y", "zoxide"],
            "apk": ["apk", "upgrade", "zoxide"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "zoxide"],
            "zypper": ["zypper", "update", "-y", "zoxide"],
            "brew": ["brew", "upgrade", "zoxide"],
            "_default": [
                "bash", "-c",
                "curl -sS https://raw.githubusercontent.com/ajeetdsouza/"
                "zoxide/main/install.sh | bash",
            ],
        },
    },

    # ════════════════════════════════════════════════════════════
    # Python extended
    # ════════════════════════════════════════════════════════════

    "poetry": {
        "cli": "poetry",
        "label": "Poetry (Python dependency management and packaging)",
        "category": "python",
        "install": {
            "pipx": ["pipx", "install", "poetry"],
            "pip": ["pip", "install", "--user", "poetry"],
            "apt": ["apt-get", "install", "-y", "python3-poetry"],
            "dnf": ["dnf", "install", "-y", "python3-poetry"],
            "pacman": ["pacman", "-S", "--noconfirm", "python-poetry"],
            "brew": ["brew", "install", "poetry"],
            "_default": [
                "bash", "-c",
                "curl -sSL https://install.python-poetry.org | python3 -",
            ],
        },
        "needs_sudo": {
            "pipx": False, "pip": False,
            "apt": True, "dnf": True, "pacman": True,
            "brew": False, "_default": False,
        },
        "prefer": ["pipx", "_default", "brew"],
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.local/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.local/bin:$PATH" && poetry --version'],
        "update": {
            "pipx": ["pipx", "upgrade", "poetry"],
            "pip": ["pip", "install", "--upgrade", "poetry"],
            "brew": ["brew", "upgrade", "poetry"],
        },
    },
    "uv": {
        "cli": "uv",
        "label": "uv (extremely fast Python package and project manager)",
        "category": "python",
        "install": {
            "pip": ["pip", "install", "uv"],
            "pipx": ["pipx", "install", "uv"],
            "dnf": ["dnf", "install", "-y", "uv"],
            "apk": ["apk", "add", "uv"],
            "pacman": ["pacman", "-S", "--noconfirm", "uv"],
            "cargo": ["cargo", "install", "--locked", "uv"],
            "brew": ["brew", "install", "uv"],
            "_default": [
                "bash", "-c",
                "curl -LsSf https://astral.sh/uv/install.sh | sh",
            ],
        },
        "needs_sudo": {
            "pip": False, "pipx": False,
            "dnf": True, "apk": True, "pacman": True,
            "cargo": False, "brew": False, "_default": False,
        },
        "install_via": {"_default": "curl_pipe_bash"},
        "prefer": ["_default", "brew", "pipx"],
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.local/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.local/bin:$PATH" && uv --version'],
        "update": {
            "pip": ["pip", "install", "--upgrade", "uv"],
            "pipx": ["pipx", "upgrade", "uv"],
            "brew": ["brew", "upgrade", "uv"],
            "_default": [
                "bash", "-c",
                "curl -LsSf https://astral.sh/uv/install.sh | sh",
            ],
        },
    },
    "pyright": {
        "cli": "pyright",
        "label": "Pyright (fast Python type checker — by Microsoft)",
        "category": "python",
        # TypeScript/Node.js based. By Microsoft.
        # Primary install via npm (native).
        # PyPI wrapper exists — bundles Node.js internally,
        # so pip/pipx work WITHOUT npm installed.
        # Available: npm, pip, pipx, pacman, brew, snap.
        # NOT in apt, dnf, apk, zypper.
        "install": {
            "pipx": ["pipx", "install", "pyright"],
            "pacman": ["pacman", "-S", "--noconfirm", "pyright"],
            "brew": ["brew", "install", "pyright"],
            "snap": ["snap", "install", "pyright", "--classic"],
            "_default": ["npm", "install", "-g", "pyright"],
        },
        "needs_sudo": {
            "pipx": False, "pacman": True,
            "brew": False, "snap": True,
            "_default": False,
        },
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "prefer": ["pipx", "pacman", "brew", "snap"],
        "verify": ["pyright", "--version"],
        "update": {
            "pipx": ["pipx", "upgrade", "pyright"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "pyright"],
            "brew": ["brew", "upgrade", "pyright"],
            "snap": ["snap", "refresh", "pyright"],
            "_default": ["npm", "update", "-g", "pyright"],
        },
    },
    "isort": {
        "cli": "isort",
        "label": "isort (Python import sorter)",
        "category": "python",
        # Pure Python. Sorts imports per PEP 8 / isort profiles.
        # pipx recommended. pacman: python-isort.
        # NOT in apt, dnf, apk, zypper system repos.
        "install": {
            "pipx": ["pipx", "install", "isort"],
            "pacman": ["pacman", "-S", "--noconfirm", "python-isort"],
            "brew": ["brew", "install", "isort"],
            "_default": _PIP + ["install", "isort"],
        },
        "needs_sudo": {
            "pipx": False, "pacman": True,
            "brew": False, "_default": False,
        },
        "install_via": {"_default": "pip"},
        "prefer": ["pipx", "pacman", "brew"],
        "verify": ["isort", "--version"],
        "update": {
            "pipx": ["pipx", "upgrade", "isort"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "python-isort"],
            "brew": ["brew", "upgrade", "isort"],
            "_default": _PIP + ["install", "--upgrade", "isort"],
        },
    },
    "flake8": {
        "cli": "flake8",
        "label": "Flake8 (Python linter — pycodestyle + pyflakes + mccabe)",
        "category": "python",
        # Pure Python. Combines pycodestyle, pyflakes, mccabe.
        # pipx recommended. pacman: flake8 (same name).
        # NOT in apt, dnf, apk, zypper system repos.
        "install": {
            "pipx": ["pipx", "install", "flake8"],
            "pacman": ["pacman", "-S", "--noconfirm", "flake8"],
            "brew": ["brew", "install", "flake8"],
            "_default": _PIP + ["install", "flake8"],
        },
        "needs_sudo": {
            "pipx": False, "pacman": True,
            "brew": False, "_default": False,
        },
        "install_via": {"_default": "pip"},
        "prefer": ["pipx", "pacman", "brew"],
        "verify": ["flake8", "--version"],
        "update": {
            "pipx": ["pipx", "upgrade", "flake8"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "flake8"],
            "brew": ["brew", "upgrade", "flake8"],
            "_default": _PIP + ["install", "--upgrade", "flake8"],
        },
    },
    "tox": {
        "cli": "tox",
        "label": "tox (Python test automation framework)",
        "category": "python",
        # Pure Python. Automates testing across multiple envs.
        # pipx recommended. pacman: python-tox.
        # NOT in apt, dnf, apk, zypper system repos.
        "install": {
            "pipx": ["pipx", "install", "tox"],
            "pacman": ["pacman", "-S", "--noconfirm", "python-tox"],
            "brew": ["brew", "install", "tox"],
            "_default": _PIP + ["install", "tox"],
        },
        "needs_sudo": {
            "pipx": False, "pacman": True,
            "brew": False, "_default": False,
        },
        "install_via": {"_default": "pip"},
        "prefer": ["pipx", "pacman", "brew"],
        "verify": ["tox", "--version"],
        "update": {
            "pipx": ["pipx", "upgrade", "tox"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "python-tox"],
            "brew": ["brew", "upgrade", "tox"],
            "_default": _PIP + ["install", "--upgrade", "tox"],
        },
    },
    "nox": {
        "cli": "nox",
        "label": "nox (flexible Python test automation)",
        "category": "python",
        # Pure Python. Similar to tox but uses Python for config.
        # pipx recommended. pacman: python-nox.
        # NOT in apt, dnf, apk, zypper system repos.
        "install": {
            "pipx": ["pipx", "install", "nox"],
            "pacman": ["pacman", "-S", "--noconfirm", "python-nox"],
            "brew": ["brew", "install", "nox"],
            "_default": _PIP + ["install", "nox"],
        },
        "needs_sudo": {
            "pipx": False, "pacman": True,
            "brew": False, "_default": False,
        },
        "install_via": {"_default": "pip"},
        "prefer": ["pipx", "pacman", "brew"],
        "verify": ["nox", "--version"],
        "update": {
            "pipx": ["pipx", "upgrade", "nox"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "python-nox"],
            "brew": ["brew", "upgrade", "nox"],
            "_default": _PIP + ["install", "--upgrade", "nox"],
        },
    },
    "pdm": {
        "cli": "pdm",
        "label": "PDM (modern Python package and project manager)",
        "category": "python",
        # Python-based. PEP 582 pioneer, now PEP 621 compliant.
        # NOT in any native system PMs. Python-ecosystem only.
        # pipx is recommended (isolated env).
        # _default: official installer script (pipes to python3).
        "install": {
            "pipx": ["pipx", "install", "pdm"],
            "pip": ["pip", "install", "--user", "pdm"],
            "brew": ["brew", "install", "pdm"],
            "_default": [
                "bash", "-c",
                "curl -sSL https://pdm-project.org/install-pdm.py | python3 -",
            ],
        },
        "needs_sudo": {
            "pipx": False, "pip": False, "brew": False,
            "_default": False,
        },
        "install_via": {"pip": "pip", "_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl", "python3"]},
        "prefer": ["pipx", "brew", "pip"],
        "post_env": 'export PATH="$HOME/.local/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.local/bin:$PATH" && pdm --version'],
        "update": {
            "pipx": ["pipx", "upgrade", "pdm"],
            "pip": ["pip", "install", "--upgrade", "pdm"],
            "brew": ["brew", "upgrade", "pdm"],
            "_default": [
                "bash", "-c",
                "curl -sSL https://pdm-project.org/install-pdm.py | python3 -",
            ],
        },
    },
    "hatch": {
        "cli": "hatch",
        "label": "Hatch (modern Python project manager — PyPA)",
        "category": "python",
        # Python-based. Official PyPA project manager.
        # Handles environments, builds, publishing, version bumping.
        # pipx recommended. Available on pacman as python-hatch.
        # NOT in apt, dnf, apk, zypper system repos.
        # Available on conda-forge but we don't track conda.
        "install": {
            "pipx": ["pipx", "install", "hatch"],
            "pacman": ["pacman", "-S", "--noconfirm", "python-hatch"],
            "brew": ["brew", "install", "hatch"],
            "_default": _PIP + ["install", "hatch"],
        },
        "needs_sudo": {
            "pipx": False, "pacman": True,
            "brew": False, "_default": False,
        },
        "install_via": {"_default": "pip"},
        "prefer": ["pipx", "pacman", "brew"],
        "verify": ["hatch", "--version"],
        "update": {
            "pipx": ["pipx", "upgrade", "hatch"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "python-hatch"],
            "brew": ["brew", "upgrade", "hatch"],
            "_default": _PIP + ["install", "--upgrade", "hatch"],
        },
    },

    # ════════════════════════════════════════════════════════════
    # Node.js extended
    # ════════════════════════════════════════════════════════════

    "yarn": {
        "cli": "yarn",
        "label": "Yarn (JavaScript package manager)",
        "category": "node",
        "install": {
            "npm": ["npm", "install", "-g", "yarn"],
            "apt": ["apt-get", "install", "-y", "yarn"],
            "dnf": ["dnf", "install", "-y", "yarnpkg"],
            "apk": ["apk", "add", "yarn"],
            "pacman": ["pacman", "-S", "--noconfirm", "yarn"],
            "zypper": ["zypper", "install", "-y", "yarn"],
            "brew": ["brew", "install", "yarn"],
            "_default": ["npm", "install", "-g", "yarn"],
        },
        "needs_sudo": {
            "npm": False, "apt": True, "dnf": True,
            "apk": True, "pacman": True, "zypper": True,
            "brew": False, "_default": False,
        },
        "install_via": {"_default": "npm"},
        "prefer": ["npm", "brew", "_default"],
        "requires": {"binaries": ["npm"]},
        "verify": ["yarn", "--version"],
        "update": {
            "npm": ["npm", "update", "-g", "yarn"],
            "brew": ["brew", "upgrade", "yarn"],
        },
    },
    "pnpm": {
        "cli": "pnpm",
        "label": "pnpm (fast, disk efficient Node package manager)",
        "category": "node",
        "install": {
            "npm": ["npm", "install", "-g", "pnpm"],
            "apk": ["apk", "add", "pnpm"],
            "brew": ["brew", "install", "pnpm"],
            "_default": [
                "bash", "-c",
                "curl -fsSL https://get.pnpm.io/install.sh | sh -",
            ],
        },
        "needs_sudo": {
            "npm": False, "apk": True,
            "brew": False, "_default": False,
        },
        "install_via": {"_default": "curl_pipe_bash"},
        "prefer": ["npm", "brew", "_default"],
        "requires": {"binaries": ["curl"]},
        "verify": ["pnpm", "--version"],
        "update": {
            "npm": ["npm", "update", "-g", "pnpm"],
            "brew": ["brew", "upgrade", "pnpm"],
        },
        "post_env": "export PNPM_HOME=\"$HOME/.local/share/pnpm\" && export PATH=\"$PNPM_HOME:$PATH\"",
    },
    "bun": {
        "cli": "bun",
        "label": "Bun (fast all-in-one JavaScript runtime, bundler, and PM)",
        "category": "node",
        # Written in Zig. JS/TS runtime + bundler + package manager.
        # Official installer script is recommended.
        # brew uses tap: oven-sh/bun/bun.
        # npm install works (installs runtime via competitor — ironic).
        # NOT in apt, dnf, apk, zypper, snap system repos.
        # pacman: AUR only (bun-bin) — skipped.
        "install": {
            "brew": ["brew", "install", "oven-sh/bun/bun"],
            "npm": ["npm", "install", "-g", "bun"],
            "_default": [
                "bash", "-c",
                "curl -fsSL https://bun.sh/install | bash",
            ],
        },
        "needs_sudo": {"brew": False, "npm": False, "_default": False},
        "install_via": {"_default": "curl_pipe_bash", "npm": "npm"},
        "requires": {"binaries": ["curl"]},
        "prefer": ["brew", "npm"],
        "post_env": 'export PATH="$HOME/.bun/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.bun/bin:$PATH" && bun --version'],
        "update": {
            "brew": ["brew", "upgrade", "oven-sh/bun/bun"],
            "npm": ["npm", "update", "-g", "bun"],
            "_default": [
                "bash", "-c",
                "curl -fsSL https://bun.sh/install | bash",
            ],
        },
    },
    "tsx": {
        "cli": "tsx",
        "label": "tsx (TypeScript execute — Node.js enhanced)",
        "category": "node",
        # npm-only. Runs TypeScript files directly via Node.js.
        # No brew, no native PMs. npm is the only install method.
        "install": {"_default": ["npm", "install", "-g", "tsx"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "verify": ["tsx", "--version"],
        "update": {"_default": ["npm", "update", "-g", "tsx"]},
    },
    "vitest": {
        "cli": "vitest",
        "label": "Vitest (Vite-native unit test framework)",
        "category": "node",
        # npm-only. Blazing fast unit tests powered by Vite.
        # No brew, no native PMs. npm is the only install method.
        "install": {"_default": ["npm", "install", "-g", "vitest"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "verify": ["vitest", "--version"],
        "update": {"_default": ["npm", "update", "-g", "vitest"]},
    },
    "playwright": {
        "cli": "npx",
        "label": "Playwright (cross-browser E2E testing — by Microsoft)",
        "category": "node",
        # npm-only. By Microsoft. Browser automation + testing.
        # Uses npx as cli — no global binary, runs via npx playwright.
        # No brew, no native PMs.
        "install": {"_default": ["npm", "install", "-g", "playwright"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "verify": ["npx", "playwright", "--version"],
        "update": {"_default": ["npm", "update", "-g", "playwright"]},
    },
    "storybook": {
        "cli": "npx",
        "label": "Storybook (UI component explorer and workshop)",
        "category": "node",
        # npm-only. Interactive UI development environment.
        # Best used via npx (npx storybook init / npx storybook dev).
        # Global npm install of @storybook/cli provides `sb` command.
        # No brew, no native PMs.
        "install": {"_default": ["npm", "install", "-g", "@storybook/cli"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "verify": ["npx", "sb", "--version"],
        "update": {"_default": ["npm", "update", "-g", "@storybook/cli"]},
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
        "cli": "ansible",
        "label": "Ansible (configuration management & automation)",
        "category": "iac",
        "install": {
            "_default": _PIP + ["install", "ansible"],
            "apt": ["apt-get", "install", "-y", "ansible"],
            "dnf": ["dnf", "install", "-y", "ansible"],
            "apk": ["apk", "add", "ansible"],
            "pacman": ["pacman", "-S", "--noconfirm", "ansible"],
            "zypper": ["zypper", "install", "-y", "ansible"],
            "brew": ["brew", "install", "ansible"],
        },
        "needs_sudo": {
            "_default": False, "apt": True, "dnf": True,
            "apk": True, "pacman": True, "zypper": True,
            "brew": False,
        },
        "install_via": {"_default": "pip"},
        "requires": {"binaries": ["python3"]},
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["ansible", "--version"],
        "update": {
            "_default": _PIP + ["install", "--upgrade", "ansible"],
            "apt": [
                "bash", "-c",
                "sudo apt-get update"
                " && sudo apt-get install -y --only-upgrade ansible",
            ],
            "dnf": ["dnf", "upgrade", "-y", "ansible"],
            "apk": ["apk", "upgrade", "ansible"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "ansible"],
            "zypper": ["zypper", "update", "-y", "ansible"],
            "brew": ["brew", "upgrade", "ansible"],
        },
    },

    "pulumi": {
        "cli": "pulumi",
        "label": "Pulumi (infrastructure as code SDK)",
        "category": "iac",
        # Written in Go. IaC using real programming languages (Python, TS, Go, etc.).
        # brew: pulumi. Official installer: get.pulumi.com — auto-detects arch.
        # Installs to $HOME/.pulumi/bin — NO sudo needed.
        # NOT in apt, dnf, apk, pacman (official), zypper, snap.
        # AUR has pulumi-bin but that's yay, not pacman -S.
        # Verify: `pulumi version` (NOT --version).
        "install": {
            "brew": ["brew", "install", "pulumi"],
            "_default": [
                "bash", "-c",
                "curl -fsSL https://get.pulumi.com | sh",
            ],
        },
        "needs_sudo": {"brew": False, "_default": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.pulumi/bin:$PATH"',
        "prefer": ["brew"],
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.pulumi/bin:$PATH" && pulumi version'],
        "update": {
            "brew": ["brew", "upgrade", "pulumi"],
            "_default": [
                "bash", "-c",
                "curl -fsSL https://get.pulumi.com | sh",
            ],
        },
    },
    "cdktf": {
        "cli": "cdktf",
        "label": "CDK for Terraform (infrastructure as code with programming languages)",
        "category": "iac",
        # Written in TypeScript. By HashiCorp.
        # ⚠️  DEPRECATED by HashiCorp — archived December 10, 2025.
        # npm: cdktf-cli (global install). brew: cdktf.
        # Requires terraform CLI (>= 1.2.0) and Node.js at runtime.
        # NOT in apt, dnf, apk, pacman, zypper, snap.
        "install": {
            "brew": ["brew", "install", "cdktf"],
            "_default": ["npm", "install", "-g", "cdktf-cli"],
        },
        "needs_sudo": {"brew": False, "_default": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "prefer": ["brew"],
        "verify": ["cdktf", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "cdktf"],
            "_default": ["npm", "update", "-g", "cdktf-cli"],
        },
    },

    # ════════════════════════════════════════════════════════════
    # Database CLIs
    # ════════════════════════════════════════════════════════════

    "psql": {
        "cli": "psql",
        "label": "PostgreSQL client (psql command-line interface)",
        "category": "database",
        # Written in C. Available in all major distro repos.
        # Package names differ: apt=postgresql-client, dnf/pacman/zypper=postgresql,
        # apk=postgresql-client, brew=libpq (client-only formula).
        # brew libpq installs to keg-only — needs `brew link --force libpq`
        # or PATH addition. Formula provides psql without server.
        # No _default needed — every target platform has it.
        "install": {
            "apt": ["apt-get", "install", "-y", "postgresql-client"],
            "dnf": ["dnf", "install", "-y", "postgresql"],
            "apk": ["apk", "add", "--no-cache", "postgresql-client"],
            "pacman": ["pacman", "-S", "--noconfirm", "postgresql"],
            "zypper": ["zypper", "install", "-y", "postgresql"],
            "brew": ["brew", "install", "libpq"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["psql", "--version"],
        "update": {
            "apt": ["apt-get", "install", "--only-upgrade", "-y", "postgresql-client"],
            "dnf": ["dnf", "upgrade", "-y", "postgresql"],
            "apk": ["apk", "upgrade", "postgresql-client"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "postgresql"],
            "zypper": ["zypper", "update", "-y", "postgresql"],
            "brew": ["brew", "upgrade", "libpq"],
        },
    },
    "mysql-client": {
        "cli": "mysql",
        "label": "MySQL client (mysql command-line interface)",
        "category": "database",
        # Written in C/C++. Client-only — no server installed.
        # Package names differ: apt=mysql-client, dnf=mysql,
        # apk=mysql-client, pacman=mariadb-clients (provides mysql binary),
        # zypper=mysql-client, brew=mysql-client (keg-only).
        # Arch uses MariaDB as default MySQL-compatible client.
        # No _default needed — every target platform has it.
        "install": {
            "apt": ["apt-get", "install", "-y", "mysql-client"],
            "dnf": ["dnf", "install", "-y", "mysql"],
            "apk": ["apk", "add", "--no-cache", "mysql-client"],
            "pacman": ["pacman", "-S", "--noconfirm", "mariadb-clients"],
            "zypper": ["zypper", "install", "-y", "mysql-client"],
            "brew": ["brew", "install", "mysql-client"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["mysql", "--version"],
        "update": {
            "apt": ["apt-get", "install", "--only-upgrade", "-y", "mysql-client"],
            "dnf": ["dnf", "upgrade", "-y", "mysql"],
            "apk": ["apk", "upgrade", "mysql-client"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "mariadb-clients"],
            "zypper": ["zypper", "update", "-y", "mysql-client"],
            "brew": ["brew", "upgrade", "mysql-client"],
        },
    },
    "mongosh": {
        "cli": "mongosh",
        "label": "MongoDB Shell (mongosh interactive client)",
        "category": "database",
        # Written in TypeScript/Node.js. Modern replacement for mongo shell.
        # npm: mongosh (global install). brew: mongosh.
        # NOT in apt, dnf, apk, pacman, zypper (MongoDB provides own repos
        # but setup is complex — repo + key. npm is simpler).
        # _default uses npm because mongosh is a Node.js package.
        "install": {
            "brew": ["brew", "install", "mongosh"],
            "_default": ["npm", "install", "-g", "mongosh"],
        },
        "needs_sudo": {"brew": False, "_default": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "prefer": ["brew"],
        "verify": ["mongosh", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "mongosh"],
            "_default": ["npm", "update", "-g", "mongosh"],
        },
    },
    "redis-cli": {
        "cli": "redis-cli",
        "label": "Redis CLI (redis-cli command-line interface)",
        "category": "database",
        # Written in C. Client-only — installs redis-cli without server.
        # Package names: apt=redis-tools (client-only), dnf/apk/pacman/
        # zypper/brew=redis (full package, includes redis-cli).
        # No _default needed — every target platform has it.
        "install": {
            "apt": ["apt-get", "install", "-y", "redis-tools"],
            "dnf": ["dnf", "install", "-y", "redis"],
            "apk": ["apk", "add", "--no-cache", "redis"],
            "pacman": ["pacman", "-S", "--noconfirm", "redis"],
            "zypper": ["zypper", "install", "-y", "redis"],
            "brew": ["brew", "install", "redis"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["redis-cli", "--version"],
        "update": {
            "apt": ["apt-get", "install", "--only-upgrade", "-y", "redis-tools"],
            "dnf": ["dnf", "upgrade", "-y", "redis"],
            "apk": ["apk", "upgrade", "redis"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "redis"],
            "zypper": ["zypper", "update", "-y", "redis"],
            "brew": ["brew", "upgrade", "redis"],
        },
    },
    "sqlite3": {
        "cli": "sqlite3",
        "label": "SQLite3 (lightweight embedded SQL database)",
        "category": "database",
        # Written in C. Self-contained, serverless, zero-configuration.
        # Package names: apt/zypper=sqlite3, dnf/apk/pacman/brew=sqlite.
        # Available in ALL major distro repos.
        # No _default needed — universal availability.
        "install": {
            "apt": ["apt-get", "install", "-y", "sqlite3"],
            "dnf": ["dnf", "install", "-y", "sqlite"],
            "apk": ["apk", "add", "--no-cache", "sqlite"],
            "pacman": ["pacman", "-S", "--noconfirm", "sqlite"],
            "zypper": ["zypper", "install", "-y", "sqlite3"],
            "brew": ["brew", "install", "sqlite"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "prefer": ["apt", "dnf", "apk", "pacman", "zypper", "brew"],
        "verify": ["sqlite3", "--version"],
        "update": {
            "apt": ["apt-get", "install", "--only-upgrade", "-y", "sqlite3"],
            "dnf": ["dnf", "upgrade", "-y", "sqlite"],
            "apk": ["apk", "upgrade", "sqlite"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "sqlite"],
            "zypper": ["zypper", "update", "-y", "sqlite3"],
            "brew": ["brew", "upgrade", "sqlite"],
        },
    },

    # ════════════════════════════════════════════════════════════
    # CI/CD tools
    # ════════════════════════════════════════════════════════════

    "act": {
        "cli": "act",
        "label": "act (local GitHub Actions runner)",
        "category": "cicd",
        # Written in Go. Runs GitHub Actions workflows locally using Docker.
        # brew formula: act. pacman: act (Arch community repo).
        # _default uses official install.sh script — auto-detects arch and OS.
        # Script installs to /usr/local/bin by default (needs sudo).
        # Also available via COPR (Fedora) but not standard dnf.
        # NOT in apt, dnf (standard), apk, zypper, snap.
        # Runtime dependency: Docker Engine (must be running).
        "install": {
            "brew": ["brew", "install", "act"],
            "pacman": ["pacman", "-S", "--noconfirm", "act"],
            "_default": [
                "bash", "-c",
                "curl -sSfL https://raw.githubusercontent.com/nektos/act/"
                "master/install.sh | sudo bash",
            ],
        },
        "needs_sudo": {"brew": False, "pacman": True, "_default": True},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["curl", "docker"]},
        "prefer": ["brew", "pacman"],
        "verify": ["act", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "act"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "act"],
            "_default": [
                "bash", "-c",
                "curl -sSfL https://raw.githubusercontent.com/nektos/act/"
                "master/install.sh | sudo bash",
            ],
        },
    },
    "gitlab-cli": {
        "cli": "glab",
        "label": "GitLab CLI (glab — GitLab command-line tool)",
        "category": "cicd",
        # Written in Go. Official repo: gitlab.com/gitlab-org/cli
        # (formerly profclems/glab — old install script URLs are BROKEN).
        # brew: glab. snap: glab. pacman: glab (Arch community).
        # dnf: glab (Fedora 38+). apk: glab (Alpine edge/testing).
        # Wide PM coverage — no need for curl script.
        # NOT in apt (standard), zypper.
        "install": {
            "brew": ["brew", "install", "glab"],
            "snap": ["snap", "install", "glab"],
            "pacman": ["pacman", "-S", "--noconfirm", "glab"],
            "dnf": ["dnf", "install", "-y", "glab"],
            "apk": ["apk", "add", "--no-cache", "glab"],
            "_default": ["snap", "install", "glab"],
        },
        "needs_sudo": {
            "brew": False, "snap": True, "pacman": True,
            "dnf": True, "apk": True, "_default": True,
        },
        "prefer": ["brew", "snap", "pacman", "dnf", "apk"],
        "verify": ["glab", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "glab"],
            "snap": ["snap", "refresh", "glab"],
            "pacman": ["pacman", "-Syu", "--noconfirm", "glab"],
            "dnf": ["dnf", "upgrade", "-y", "glab"],
            "apk": ["apk", "upgrade", "glab"],
            "_default": ["snap", "refresh", "glab"],
        },
    },

    # ════════════════════════════════════════════════════════════
    # Networking tools
    # ════════════════════════════════════════════════════════════

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
        "cli": "ruby",
        "label": "Ruby",
        "category": "ruby",
        # No _default (binary download) — Ruby from source requires
        # autotools + C compiler + many deps. System packages are
        # the correct path. No snap package exists.
        #
        # apt ruby-full = ruby + ruby-dev + ruby-doc (all-in-one).
        # dnf/apk need separate -devel/-dev for gem native extensions.
        # pacman/brew ruby includes everything.
        "install": {
            "apt":    ["apt-get", "install", "-y", "ruby-full"],
            "dnf":    ["dnf", "install", "-y", "ruby", "ruby-devel"],
            "apk":    ["apk", "add", "ruby", "ruby-dev"],
            "pacman": ["pacman", "-S", "--noconfirm", "ruby"],
            "zypper": ["zypper", "install", "-y", "ruby-devel"],
            "brew":   ["brew", "install", "ruby"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "brew": False,
        },
        "verify": ["ruby", "--version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y",
                       "ruby-full"],
            "dnf":    ["dnf", "upgrade", "-y", "ruby"],
            "apk":    ["apk", "upgrade", "ruby"],
            "pacman": ["pacman", "-S", "--noconfirm", "ruby"],
            "zypper": ["zypper", "update", "-y", "ruby-devel"],
            "brew":   ["brew", "upgrade", "ruby"],
        },
    },
    "bundler": {
        "cli": "bundle",
        "label": "Bundler (Ruby dependency manager)",
        "category": "ruby",
        # _default via gem is preferred — always latest, Ruby is
        # already a hard dependency. System packages often lag.
        # brew doesn't have a separate formula — bundler ships
        # with brewed Ruby since Ruby 2.6+.
        "install": {
            "apt":    ["apt-get", "install", "-y", "ruby-bundler"],
            "dnf":    ["dnf", "install", "-y", "rubygem-bundler"],
            "apk":    ["apk", "add", "ruby-bundler"],
            "pacman": ["pacman", "-S", "--noconfirm", "ruby-bundler"],
            "zypper": ["zypper", "install", "-y", "ruby-bundler"],
            "_default": ["gem", "install", "bundler"],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True, "_default": False,
        },
        "install_via": {"_default": "gem"},
        "prefer": ["_default"],
        "requires": {"binaries": ["ruby"]},
        "verify": ["bundle", "--version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y",
                       "ruby-bundler"],
            "dnf":    ["dnf", "upgrade", "-y", "rubygem-bundler"],
            "apk":    ["apk", "upgrade", "ruby-bundler"],
            "pacman": ["pacman", "-S", "--noconfirm", "ruby-bundler"],
            "zypper": ["zypper", "update", "-y", "ruby-bundler"],
            "_default": ["gem", "update", "bundler"],
        },
    },
    "rubocop": {
        "label": "RuboCop (Ruby linter)",
        "category": "ruby",
        "install": {"_default": ["gem", "install", "rubocop"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "gem"},
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
        "cli": "composer",
        "label": "Composer (PHP dependency manager)",
        "category": "php",
        # Available in all major PMs. zypper uses php-composer (not
        # composer). No snap package. _default uses the official
        # installer from getcomposer.org which requires php + curl.
        #
        # The installer is smarter than manual mv: it verifies the
        # download hash, places the binary directly, and supports
        # --install-dir and --filename flags.
        "install": {
            "apt":    ["apt-get", "install", "-y", "composer"],
            "dnf":    ["dnf", "install", "-y", "composer"],
            "apk":    ["apk", "add", "composer"],
            "pacman": ["pacman", "-S", "--noconfirm", "composer"],
            "zypper": ["zypper", "install", "-y", "php-composer"],
            "brew":   ["brew", "install", "composer"],
            "_default": [
                "bash", "-c",
                "curl -sS https://getcomposer.org/installer"
                " | php -- --install-dir=/usr/local/bin"
                " --filename=composer",
            ],
        },
        "needs_sudo": {
            "apt": True, "dnf": True, "apk": True,
            "pacman": True, "zypper": True,
            "brew": False, "_default": True,
        },
        "prefer": ["_default", "brew"],
        "requires": {"binaries": ["php", "curl"]},
        "verify": ["composer", "--version"],
        "update": {
            "apt":    ["apt-get", "install", "--only-upgrade", "-y",
                       "composer"],
            "dnf":    ["dnf", "upgrade", "-y", "composer"],
            "apk":    ["apk", "upgrade", "composer"],
            "pacman": ["pacman", "-S", "--noconfirm", "composer"],
            "zypper": ["zypper", "update", "-y", "php-composer"],
            "brew":   ["brew", "upgrade", "composer"],
            "_default": ["composer", "self-update"],
        },
    },
    "phpstan": {
        "cli": "phpstan",
        "label": "PHPStan (PHP static analysis)",
        "category": "php",
        # Not in apt/dnf/apk/pacman/zypper repos.
        # Available via composer (recommended) and brew.
        # Arch has AUR phpstan-bin but not official repos.
        "install": {
            "_default": [
                "bash", "-c",
                "composer global require phpstan/phpstan",
            ],
            "brew": ["brew", "install", "phpstan"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "composer_global"},
        "requires": {"binaries": ["composer"]},
        "post_env": 'export PATH="$HOME/.config/composer/vendor/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.config/composer/vendor/bin:$PATH"'
                   ' && phpstan --version'],
        "update": {
            "_default": [
                "bash", "-c",
                "composer global update phpstan/phpstan",
            ],
            "brew": ["brew", "upgrade", "phpstan"],
        },
    },
    "phpunit": {
        "cli": "phpunit",
        "label": "PHPUnit (PHP testing)",
        "category": "php",
        # Not in apt/dnf/apk/pacman/zypper repos.
        # Available via composer (recommended) and brew.
        # PHPUnit 11 requires PHP 8.2+, PHPUnit 12 requires PHP 8.3+.
        "install": {
            "_default": [
                "bash", "-c",
                "composer global require phpunit/phpunit",
            ],
            "brew": ["brew", "install", "phpunit"],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "composer_global"},
        "requires": {"binaries": ["composer"]},
        "post_env": 'export PATH="$HOME/.config/composer/vendor/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/.config/composer/vendor/bin:$PATH"'
                   ' && phpunit --version'],
        "update": {
            "_default": [
                "bash", "-c",
                "composer global update phpunit/phpunit",
            ],
            "brew": ["brew", "upgrade", "phpunit"],
        },
    },

    # ════════════════════════════════════════════════════════════
    # Batch 2 — Rust extended
    # ════════════════════════════════════════════════════════════

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

    # ════════════════════════════════════════════════════════════
    # Monitoring & Observability
    # ════════════════════════════════════════════════════════════

    "prometheus": {
        "cli": "prometheus",
        "label": "Prometheus (metrics monitoring and alerting toolkit)",
        "category": "monitoring",
        # Written in Go. By the CNCF (Cloud Native Computing Foundation).
        # brew: prometheus. snap: not available.
        # GitHub releases: prometheus-VERSION.OS-ARCH.tar.gz
        # Version is in BOTH the tag (v2.x.x) and filename (2.x.x).
        # Tag has 'v' prefix, filename does not.
        # Arch: amd64, arm64, armv7. OS: linux, darwin.
        # NOT in apt, dnf, apk (via community), pacman, zypper as standard.
        # pacman has prometheus in community but it includes the server service.
        # Archive contains: prometheus, promtool, config, consoles — we extract
        # just the binaries.
        "install": {
            "brew": ["brew", "install", "prometheus"],
            "_default": [
                "bash", "-c",
                "VERSION=$(curl -sSf https://api.github.com/repos/prometheus/"
                "prometheus/releases/latest | grep -o '\"tag_name\": \"v[^\"]*\"'"
                " | cut -d'\"' -f4 | sed 's/^v//') && "
                "curl -sSfL https://github.com/prometheus/prometheus/releases/"
                "download/v${VERSION}/prometheus-${VERSION}.{os}-{arch}.tar.gz"
                " | sudo tar -xz --strip-components=1 -C /usr/local/bin"
                " prometheus-${VERSION}.{os}-{arch}/prometheus"
                " prometheus-${VERSION}.{os}-{arch}/promtool",
            ],
        },
        "needs_sudo": {"brew": False, "_default": True},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "arch_map": {
            "x86_64": "amd64", "aarch64": "arm64", "armv7l": "armv7",
        },
        "prefer": ["brew"],
        "verify": ["prometheus", "--version"],
        "update": {
            "brew": ["brew", "upgrade", "prometheus"],
            "_default": [
                "bash", "-c",
                "VERSION=$(curl -sSf https://api.github.com/repos/prometheus/"
                "prometheus/releases/latest | grep -o '\"tag_name\": \"v[^\"]*\"'"
                " | cut -d'\"' -f4 | sed 's/^v//') && "
                "curl -sSfL https://github.com/prometheus/prometheus/releases/"
                "download/v${VERSION}/prometheus-${VERSION}.{os}-{arch}.tar.gz"
                " | sudo tar -xz --strip-components=1 -C /usr/local/bin"
                " prometheus-${VERSION}.{os}-{arch}/prometheus"
                " prometheus-${VERSION}.{os}-{arch}/promtool",
            ],
        },
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
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL -o /usr/local/bin/loki"
                    " https://github.com/grafana/loki/releases/latest/download/"
                    "loki-linux-amd64.zip && chmod +x /usr/local/bin/loki",
                ],
            },
            "brew": ["brew", "install", "loki"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "verify": ["loki", "--version"],
    },
    "promtail": {
        "label": "Promtail (Loki agent)",
        "category": "monitoring",
        "install": {
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL -o /usr/local/bin/promtail"
                    " https://github.com/grafana/loki/releases/latest/download/"
                    "promtail-linux-amd64.zip && chmod +x /usr/local/bin/promtail",
                ],
            },
            "brew": ["brew", "install", "promtail"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "verify": ["promtail", "--version"],
    },
    "jaeger": {
        "label": "Jaeger (distributed tracing)",
        "category": "monitoring",
        "install": {
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL https://github.com/jaegertracing/jaeger/releases/"
                    "latest/download/jaeger-all-in-one-linux-amd64.tar.gz"
                    " | tar xz -C /usr/local/bin",
                ],
            },
            "brew": ["brew", "install", "jaeger"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
        "requires": {"binaries": ["curl"]},
        "verify": ["jaeger-all-in-one", "version"],
        "cli": "jaeger-all-in-one",
    },
    "vegeta": {
        "label": "Vegeta (HTTP load testing)",
        "category": "monitoring",
        "install": {
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL https://github.com/tsenart/vegeta/releases/"
                    "latest/download/vegeta_linux_amd64.tar.gz"
                    " | tar xz -C /usr/local/bin vegeta",
                ],
            },
            "brew": ["brew", "install", "vegeta"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
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
        "install_via": {"_default": "go"},
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
        "install_via": {"_default": "cargo"},
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

    # ════════════════════════════════════════════════════════════
    # Data / ML extended
    # ════════════════════════════════════════════════════════════

    "jupyter": {
        "label": "Jupyter Notebook",
        "category": "ml",
        "install": {"_default": _PIP + ["install", "jupyter"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": ["jupyter", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "jupyter"]},
    },
    "numpy": {
        "label": "NumPy",
        "category": "ml",
        "install": {"_default": _PIP + ["install", "numpy"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "cli": "python3",
        "verify": ["python3", "-c", "import numpy; print(numpy.__version__)"],
    },
    "pandas": {
        "label": "Pandas",
        "category": "ml",
        "install": {"_default": _PIP + ["install", "pandas"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "cli": "python3",
        "verify": ["python3", "-c", "import pandas; print(pandas.__version__)"],
    },
    "tensorflow": {
        "label": "TensorFlow",
        "category": "ml",
        "install": {"_default": _PIP + ["install", "tensorflow"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
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
        "install_via": {"_default": "curl_pipe_bash"},
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
        "install_via": {"_default": "curl_pipe_bash"},
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
        "install_via": {"_default": "curl_pipe_bash"},
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
        "install_via": {"_default": "curl_pipe_bash"},
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
        "install_via": {"_default": "curl_pipe_bash"},
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
        "install_via": {"_default": "pip"},
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
        "install_via": {"_default": "cargo"},
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
        "install_via": {"_default": "gem"},
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
        "install_via": {"_default": "cargo"},
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
        "install_via": {"_default": "go"},
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
        "install_via": {"_default": "pip"},
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
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL -o /usr/local/bin/ec"
                    " https://github.com/editorconfig-checker/"
                    "editorconfig-checker/releases/latest/download/"
                    "ec-linux-amd64 && chmod +x /usr/local/bin/ec",
                ],
            },
            "brew": ["brew", "install", "editorconfig-checker"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
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
        "install_via": {"_default": "pip"},
        "verify": ["yamllint", "--version"],
    },
    "jsonlint": {
        "label": "jsonlint (JSON linter)",
        "category": "formatting",
        "install": {
            "_default": ["npm", "install", "-g", "jsonlint"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "npm"},
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
        "install_via": {"_default": "npm"},
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
        "install_via": {"_default": "cargo"},
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
        "install_via": {"_default": "cargo"},
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
        "install_via": {"_default": "curl_pipe_bash"},
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
        "install_via": {"_default": "curl_pipe_bash"},
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
        "install_via": {"_default": "go"},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && grpcurl --version'],
    },
    "buf": {
        "label": "Buf (protobuf tooling)",
        "category": "protobuf",
        "install": {
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSL https://github.com/bufbuild/buf/releases/latest/"
                    "download/buf-Linux-x86_64"
                    " -o /usr/local/bin/buf && chmod +x /usr/local/bin/buf",
                ],
            },
            "brew": ["brew", "install", "bufbuild/buf/buf"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
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
        "install_via": {"_default": "curl_pipe_bash"},
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
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL -o /usr/local/bin/zls"
                    " https://github.com/zigtools/zls/releases/latest/download/"
                    "zls-linux-x86_64 && chmod +x /usr/local/bin/zls",
                ],
            },
            "brew": ["brew", "install", "zls"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
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
        "install_via": {"_default": "cargo"},
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
        "install_via": {"_default": "curl_pipe_bash"},
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
        "install_via": {"_default": "curl_pipe_bash"},
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
        "install_via": {"_default": "cargo"},
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
        "install_via": {"_default": "curl_pipe_bash"},
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
        "install_via": {"_default": "npm"},
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
        "install_via": {"_default": "npm"},
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
        "install_via": {"_default": "npm"},
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
        "install_via": {"_default": "npm"},
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
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSL https://github.com/digitalocean/doctl/releases/"
                    "latest/download/doctl-linux-amd64.tar.gz"
                    " | tar xz -C /usr/local/bin",
                ],
            },
            "brew": ["brew", "install", "doctl"],
            "snap": ["snap", "install", "doctl"],
        },
        "needs_sudo": {"_default": True, "brew": False, "snap": True},
        "install_via": {"_default": "github_release"},
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
        "install_via": {"_default": "pip"},
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
        "install_via": {"_default": "curl_pipe_bash"},
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
        "install_via": {"_default": "npm"},
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
        "install_via": {"_default": "npm"},
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
        "install_via": {"_default": "npm"},
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
        "install_via": {"_default": "curl_pipe_bash"},
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
        "install_via": {"_default": "github_release"},
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
        "install_via": {"_default": "github_release"},
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
        "install_via": {"_default": "curl_pipe_bash"},
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
        "install_via": {"_default": "curl_pipe_bash"},
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
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL https://github.com/stern/stern/releases/"
                    "latest/download/stern_linux_amd64.tar.gz"
                    " | tar xz -C /usr/local/bin stern",
                ],
            },
            "brew": ["brew", "install", "stern"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
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
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL https://github.com/grafana/k6/releases/"
                    "latest/download/k6-linux-amd64.tar.gz"
                    " | tar xz --strip-components=1 -C /usr/local/bin",
                ],
            },
            "brew": ["brew", "install", "k6"],
            "snap": ["snap", "install", "k6"],
        },
        "needs_sudo": {"_default": True, "brew": False, "snap": True},
        "install_via": {"_default": "github_release"},
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
        "install_via": {"_default": "pip"},
        "verify": ["locust", "--version"],
    },
    "cypress": {
        "cli": "cypress",
        "label": "Cypress (JavaScript E2E and component testing)",
        "category": "testing",
        # npm-only. JavaScript E2E testing framework.
        # Has a desktop app but CLI is the primary interface.
        # No brew, no native PMs.
        "install": {
            "_default": ["npm", "install", "-g", "cypress"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "verify": ["cypress", "--version"],
        "update": {"_default": ["npm", "update", "-g", "cypress"]},
    },
    "artillery": {
        "label": "Artillery (load testing)",
        "category": "testing",
        "install": {
            "_default": ["npm", "install", "-g", "artillery"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "npm"},
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
        "install_via": {"_default": "npm"},
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
        "install_via": {"_default": "cargo"},
        "verify": ["just", "--version"],
    },
    "earthly": {
        "label": "Earthly (CI/CD build tool)",
        "category": "taskrunner",
        "install": {
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL https://github.com/earthly/earthly/releases/"
                    "latest/download/earthly-linux-amd64"
                    " -o /usr/local/bin/earthly && chmod +x /usr/local/bin/earthly",
                ],
            },
            "brew": ["brew", "install", "earthly"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "install_via": {"_default": "github_release"},
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
        "install_via": {"_default": "go"},
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
            "_default": {
                "linux": [
                    "bash", "-c",
                    "curl -sSfL https://github.com/etcd-io/etcd/releases/"
                    "latest/download/etcd-linux-amd64.tar.gz"
                    " | tar xz --strip-components=1 -C /usr/local/bin"
                    " etcdctl etcd",
                ],
            },
        },
        "needs_sudo": {"apt": True, "brew": False, "_default": True},
        "install_via": {"_default": "github_release"},
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
        "install_via": {"_default": "curl_pipe_bash"},
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
        "install_via": {"_default": "cargo"},
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
        "install_via": {"_default": "pip"},
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
        "install_via": {"_default": "cargo"},
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
        "install_via": {"_default": "pip"},
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
        "install_via": {"_default": "pip"},
        "verify": ["esptool.py", "version"],
        "cli": "esptool.py",
    },
}

