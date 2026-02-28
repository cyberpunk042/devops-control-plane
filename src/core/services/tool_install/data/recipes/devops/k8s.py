"""
L0 Data — Kubernetes tools.

Categories: k8s
Pure data, no logic.
"""

from __future__ import annotations


_K8S_RECIPES: dict[str, dict] = {

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

    "skaffold": {
        "label": "Skaffold",
        "category": "k8s",
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
}
