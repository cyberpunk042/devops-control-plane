"""
L0 Data — Shell & terminal tools.

Categories: shell, terminal
Pure data, no logic.
"""

from __future__ import annotations


_SHELL_RECIPES: dict[str, dict] = {
    "expect": {
        "label": "Expect",
        "category": "terminal",
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

    "xterm": {
        "label": "xterm",
        "category": "terminal",
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
        "category": "terminal",
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
        "category": "terminal",
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
        "category": "terminal",
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
        "category": "terminal",
        "install": {
            "apt":    ["apt-get", "install", "-y", "kitty"],
            "dnf":    ["dnf", "install", "-y", "kitty"],
            "pacman": ["pacman", "-S", "--noconfirm", "kitty"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "pacman": True},
        "verify": ["kitty", "--version"],
    },

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
}
