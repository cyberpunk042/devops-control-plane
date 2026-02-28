"""
L0 Data — Security scanning tools.

Categories: security
Pure data, no logic.
"""

from __future__ import annotations

from src.core.services.tool_install.data.constants import _PIP


_SCANNERS_RECIPES: dict[str, dict] = {
    "pip-audit": {
        "label": "pip-audit",
        "category": "security",
        "install": {"_default": _PIP + ["install", "pip-audit"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": _PIP + ["show", "pip-audit"],
        "update": {"_default": _PIP + ["install", "--upgrade", "pip-audit"]},
    },
    "safety": {
        "label": "Safety",
        "category": "security",
        "install": {"_default": _PIP + ["install", "safety"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": ["safety", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "safety"]},
    },
    "bandit": {
        "label": "Bandit",
        "category": "security",
        "install": {"_default": _PIP + ["install", "bandit"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "pip"},
        "verify": ["bandit", "--version"],
        "update": {"_default": _PIP + ["install", "--upgrade", "bandit"]},
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
}
