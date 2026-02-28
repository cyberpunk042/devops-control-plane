"""
L0 Data — Node.js ecosystem tools.

Categories: node, pages
Pure data, no logic.
"""

from __future__ import annotations


_NODE_RECIPES: dict[str, dict] = {

    "eslint": {
        "label": "ESLint",
        "category": "node",
        "install": {"_default": ["npm", "install", "-g", "eslint"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "verify": ["eslint", "--version"],
        "update": {"_default": ["npm", "update", "-g", "eslint"]},
    },
    "prettier": {
        "label": "Prettier",
        "category": "node",
        "install": {"_default": ["npm", "install", "-g", "prettier"]},
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "npm"},
        "requires": {"binaries": ["npm"]},
        "verify": ["prettier", "--version"],
        "update": {"_default": ["npm", "update", "-g", "prettier"]},
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
        "category": "node",
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

    "hugo": {
        "label": "Hugo",
        "category": "pages",
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
}
