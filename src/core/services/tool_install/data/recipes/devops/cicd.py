"""
L0 Data — CI/CD & Git tools.

Categories: cicd, git, scm
Pure data, no logic.
"""

from __future__ import annotations

from src.core.services.tool_install.data.constants import _PIP


_CICD_RECIPES: dict[str, dict] = {
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
}
