"""
L0 Data — Developer tools.

Categories: devtools, editors, testing, taskrunner, profiling, formatting
Pure data, no logic.
"""

from __future__ import annotations

from src.core.services.tool_install.data.constants import _PIP


_DEVTOOLS_RECIPES: dict[str, dict] = {

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
}
