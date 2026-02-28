"""
L0 Data — Node.js ecosystem tool-specific failure handlers.

Tools: node, nvm, yarn, pnpm
Pure data, no logic.
"""

from __future__ import annotations


_YARN_HANDLERS: list[dict] = [
            # ── cmdtest conflict (Debian) ─────────────────────────
            # On Debian, the `cmdtest` package also provides
            # /usr/bin/yarn (a scenario testing tool). If a user
            # runs `apt-get install yarn` on a system without the
            # Yarn repo, they get cmdtest's yarn instead. When
            # they try to use it as a JS package manager, they get
            # errors like "No such file or directory: 'upgrade'"
            # or "There are no scenarios".
            {
                "pattern": (
                    r"There are no scenarios|"
                    r"No such file or directory.*upgrade|"
                    r"No such file or directory.*add|"
                    r"cmdtest"
                ),
                "failure_id": "yarn_cmdtest_conflict",
                "category": "configuration",
                "label": "Wrong yarn installed (cmdtest conflict)",
                "description": (
                    "The system has the 'cmdtest' package installed, "
                    "which also provides a /usr/bin/yarn binary. This "
                    "is NOT the JavaScript package manager Yarn. The "
                    "cmdtest yarn is a scenario testing tool for Unix "
                    "commands. Remove cmdtest and install the correct "
                    "yarn."
                ),
                "example_stderr": (
                    "ERROR: There are no scenarios; must have at "
                    "least one"
                ),
                "options": [
                    {
                        "id": "use-npm",
                        "label": "Install yarn via npm",
                        "description": (
                            "Remove cmdtest's yarn and install the "
                            "correct Yarn via npm. This is the most "
                            "reliable method."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "npm",
                        "risk": "low",
                    },
                    {
                        "id": "remove-cmdtest",
                        "label": "Remove cmdtest and retry apt",
                        "description": (
                            "Remove the cmdtest package, then add the "
                            "Yarn apt repository and install the "
                            "correct yarn package."
                        ),
                        "icon": "🗑️",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "1. sudo apt-get remove cmdtest\n"
                            "2. curl -sS https://dl.yarnpkg.com/debian/"
                            "pubkey.gpg | sudo apt-key add -\n"
                            "3. echo 'deb https://dl.yarnpkg.com/debian/ "
                            "stable main' | sudo tee /etc/apt/sources."
                            "list.d/yarn.list\n"
                            "4. sudo apt-get update && sudo apt-get "
                            "install yarn"
                        ),
                        "risk": "medium",
                    },
                ],
            },

            # ── Yarn repo not configured (apt) ────────────────────
            # On fresh Debian/Ubuntu, `apt-get install yarn` fails
            # because yarn isn't in the default apt repos (unless
            # the Yarn repo or NodeSource repo has been added).
            {
                "pattern": (
                    r"Unable to locate package yarn|"
                    r"Package 'yarn' has no installation candidate|"
                    r"has no installation candidate"
                ),
                "failure_id": "yarn_repo_not_configured",
                "category": "configuration",
                "label": "Yarn package repository not configured",
                "description": (
                    "The yarn package is not available in the default "
                    "apt repositories. On Debian/Ubuntu, yarn requires "
                    "adding the official Yarn repository "
                    "(dl.yarnpkg.com) first, or installing via npm."
                ),
                "example_stderr": (
                    "E: Unable to locate package yarn"
                ),
                "options": [
                    {
                        "id": "use-npm",
                        "label": "Install yarn via npm",
                        "description": (
                            "Install yarn globally using npm. This is "
                            "the most reliable cross-platform method "
                            "and does not require repository "
                            "configuration."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "npm",
                        "risk": "low",
                    },
                    {
                        "id": "use-brew",
                        "label": "Install via Homebrew",
                        "description": (
                            "Use Homebrew to install yarn. No external "
                            "repository configuration needed."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                        "risk": "low",
                    },
                ],
            },

            # ── Corepack conflict (brew) ──────────────────────────
            # On macOS with Homebrew, `brew install yarn` fails if
            # the corepack formula is already installed because both
            # provide yarn and yarnpkg executables.
            {
                "pattern": (
                    r"Cannot install yarn because conflicting formulae|"
                    r"conflicting formulae.*corepack|"
                    r"corepack.*both install.*yarn"
                ),
                "failure_id": "yarn_corepack_conflict",
                "category": "configuration",
                "label": "Yarn conflicts with corepack (Homebrew)",
                "description": (
                    "Cannot install yarn via Homebrew because the "
                    "corepack formula is already installed. Both "
                    "formulae provide the 'yarn' and 'yarnpkg' "
                    "executables. Unlink corepack first or use npm."
                ),
                "example_stderr": (
                    "Error: Cannot install yarn because conflicting "
                    "formulae are installed.\n"
                    "  corepack: because both install `yarn` and "
                    "`yarnpkg` executables"
                ),
                "options": [
                    {
                        "id": "use-npm",
                        "label": "Install yarn via npm instead",
                        "description": (
                            "Use npm to install yarn globally. This "
                            "avoids the Homebrew conflict entirely."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "npm",
                        "risk": "low",
                    },
                    {
                        "id": "unlink-corepack",
                        "label": "Unlink corepack and retry brew",
                        "description": (
                            "Unlink the corepack formula to remove "
                            "its symlinks, then install yarn via brew."
                        ),
                        "icon": "🔗",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "1. brew unlink corepack\n"
                            "2. brew install yarn"
                        ),
                        "risk": "medium",
                    },
                ],
            },
]


_PNPM_HANDLERS: list[dict] = [
            # ── Corepack conflict (brew) ──────────────────────────
            # On macOS with Homebrew, `brew install pnpm` fails if
            # the corepack formula is already installed because both
            # provide the pnpm executable. Same pattern as yarn.
            {
                "pattern": (
                    r"Cannot install pnpm because conflicting formulae|"
                    r"conflicting formulae.*corepack|"
                    r"corepack.*both install.*pnpm"
                ),
                "failure_id": "pnpm_corepack_conflict",
                "category": "configuration",
                "label": "pnpm conflicts with corepack (Homebrew)",
                "description": (
                    "Cannot install pnpm via Homebrew because the "
                    "corepack formula is already installed. Both "
                    "formulae provide the 'pnpm' executable. Unlink "
                    "corepack first, or install via npm."
                ),
                "example_stderr": (
                    "Error: Cannot install pnpm because conflicting "
                    "formulae are installed.\n"
                    "  corepack: because both install `pnpm` "
                    "executables"
                ),
                "options": [
                    {
                        "id": "use-npm",
                        "label": "Install pnpm via npm instead",
                        "description": (
                            "Use npm to install pnpm globally. This "
                            "avoids the Homebrew conflict entirely."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "npm",
                        "risk": "low",
                    },
                    {
                        "id": "use-standalone",
                        "label": "Install via standalone script",
                        "description": (
                            "Use the official pnpm standalone "
                            "installer (get.pnpm.io). Does not "
                            "require npm or Homebrew."
                        ),
                        "icon": "📥",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "_default",
                        "risk": "low",
                    },
                    {
                        "id": "unlink-corepack",
                        "label": "Unlink corepack and retry brew",
                        "description": (
                            "Unlink the corepack formula to remove "
                            "its symlinks, then install pnpm via brew."
                        ),
                        "icon": "🔗",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "1. brew unlink corepack\n"
                            "2. brew install pnpm"
                        ),
                        "risk": "medium",
                    },
                ],
            },
]


_NVM_HANDLERS: list[dict] = [
        # ── ~/.nvm already exists ──────────────────────────────
        # If ~/.nvm exists (partial install, manual mkdir, or
        # previous broken install), git clone fails.
        {
            "pattern": (
                r"already exists and is not an empty directory|"
                r"destination path.*\.nvm.*already exists"
            ),
            "failure_id": "nvm_dir_exists",
            "category": "environment",
            "label": "~/.nvm directory already exists",
            "description": (
                "The nvm installer tries to git-clone into ~/.nvm, "
                "but this directory already exists (possibly from a "
                "previous partial or broken install). The git clone "
                "fails because the target directory is not empty."
            ),
            "example_stderr": (
                "fatal: destination path '/home/user/.nvm' already "
                "exists and is not an empty directory."
            ),
            "options": [
                {
                    "id": "cleanup-nvm-dir",
                    "label": "Remove ~/.nvm and retry",
                    "description": (
                        "Back up and remove the existing ~/.nvm "
                        "directory, then re-run the installer. "
                        "This will remove any previously installed "
                        "Node.js versions managed by nvm."
                    ),
                    "icon": "🗑️",
                    "recommended": True,
                    "strategy": "cleanup_retry",
                    "cleanup_commands": [
                        ["bash", "-c",
                         "mv ~/.nvm ~/.nvm.bak.$(date +%s) 2>/dev/null"
                         " || rm -rf ~/.nvm"],
                    ],
                    "risk": "medium",
                },
                {
                    "id": "use-brew-instead",
                    "label": "Install via Homebrew instead",
                    "description": (
                        "Skip the git-clone installer and use "
                        "brew install nvm. Brew manages nvm "
                        "separately from ~/.nvm."
                    ),
                    "icon": "🍺",
                    "recommended": False,
                    "strategy": "switch_method",
                    "method": "brew",
                    "risk": "low",
                },
            ],
        },
        # ── Shell profile not found ────────────────────────────
        # The installer tries to add sourcing lines to .bashrc,
        # .zshrc, or .profile but can't find any of them.
        {
            "pattern": (
                r"profile.*not found|"
                r"no profile found|"
                r"could not detect.*profile|"
                r"create.*profile.*nvm"
            ),
            "failure_id": "nvm_profile_not_found",
            "category": "configuration",
            "label": "Shell profile not found for nvm",
            "description": (
                "The nvm installer could not find a shell profile "
                "file (.bashrc, .zshrc, .profile, .bash_profile) to "
                "add the nvm sourcing lines. nvm may have installed "
                "correctly but won't be available in new shell "
                "sessions until the profile is configured."
            ),
            "example_stderr": (
                "=> Profile not found. Tried ~/.bashrc, "
                "~/.bash_profile, ~/.zshrc, and ~/.profile."
            ),
            "options": [
                {
                    "id": "create-bashrc",
                    "label": "Create ~/.bashrc with nvm config",
                    "description": (
                        "Create a .bashrc file and add the nvm "
                        "sourcing lines so nvm loads automatically."
                    ),
                    "icon": "📝",
                    "recommended": True,
                    "strategy": "env_fix",
                    "fix_commands": [
                        ["bash", "-c",
                         "touch ~/.bashrc && echo '"
                         'export NVM_DIR="$HOME/.nvm"\n'
                         '[ -s "$NVM_DIR/nvm.sh" ] && '
                         '\\. "$NVM_DIR/nvm.sh"'
                         "' >> ~/.bashrc"],
                    ],
                    "risk": "low",
                },
                {
                    "id": "manual-add-profile",
                    "label": "Manually add nvm to shell profile",
                    "description": (
                        "Add the nvm sourcing lines to your "
                        "preferred shell configuration file."
                    ),
                    "icon": "📋",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Add these lines to your shell config "
                        "(~/.bashrc, ~/.zshrc, or ~/.profile):\n\n"
                        'export NVM_DIR="$HOME/.nvm"\n'
                        '[ -s "$NVM_DIR/nvm.sh" ] && '
                        '\\. "$NVM_DIR/nvm.sh"\n'
                        '[ -s "$NVM_DIR/bash_completion" ] && '
                        '\\. "$NVM_DIR/bash_completion"'
                    ),
                    "risk": "low",
                },
            ],
        },
]


_NODE_HANDLERS: list[dict] = [
            # ── GLIBC too old for pre-compiled binary ────────────────
            # Node.js 18+ requires GLIBC_2.28. Older distros like
            # CentOS 7 (GLIBC 2.17) and Ubuntu 18.04 (GLIBC 2.27)
            # cannot run the official pre-compiled binaries.
            # This fires when the _default binary download path is used.
            {
                "pattern": (
                    r"GLIBC_2\.\d+.*not found|"
                    r"version.*GLIBC.*not found|"
                    r"libc\.so\.6.*version.*not found"
                ),
                "failure_id": "node_glibc_too_old",
                "category": "environment",
                "label": "System glibc too old for Node.js binary",
                "description": (
                    "The pre-compiled Node.js binary requires a newer "
                    "version of glibc than is available on this system. "
                    "Node.js 18+ requires GLIBC_2.28 or newer. Older "
                    "distributions like CentOS 7 (GLIBC 2.17) and "
                    "Ubuntu 18.04 (GLIBC 2.27) cannot run these binaries."
                ),
                "example_stderr": (
                    "node: /lib/x86_64-linux-gnu/libc.so.6: "
                    "version `GLIBC_2.28' not found (required by node)"
                ),
                "options": [
                    {
                        "id": "switch-to-pm",
                        "label": "Install via system package manager",
                        "description": (
                            "Use the distro's package manager to install "
                            "a Node.js version compatible with this system's "
                            "glibc. The version may be older but will work."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "apt",
                        "risk": "low",
                    },
                    {
                        "id": "upgrade-os",
                        "label": "Upgrade to a newer OS release",
                        "description": (
                            "Upgrade your operating system to a version "
                            "that ships GLIBC 2.28+. Ubuntu 20.04+, "
                            "Debian 10+, RHEL 8+, Fedora 28+ all qualify. "
                            "This is the long-term solution."
                        ),
                        "icon": "⬆️",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "Upgrade your Linux distribution to a newer "
                            "release. For Ubuntu: upgrade to 20.04 or newer. "
                            "For CentOS/RHEL: upgrade to RHEL 8 or "
                            "Rocky/Alma 8+."
                        ),
                        "risk": "high",
                    },
                    {
                        "id": "unofficial-builds",
                        "label": "Use unofficial Node.js builds for old glibc",
                        "description": (
                            "The Node.js project provides unofficial builds "
                            "compiled against older glibc versions at "
                            "https://unofficial-builds.nodejs.org/. These "
                            "work on CentOS 7 and Ubuntu 18.04."
                        ),
                        "icon": "🔧",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "Download from "
                            "https://unofficial-builds.nodejs.org/"
                            "download/release/ — look for builds with "
                            "'glibc-217' in the filename."
                        ),
                        "risk": "medium",
                    },
                ],
            },

            # ── Node.js version too old ──────────────────────────────
            # Installed Node.js is too old for modern JS features.
            # This catches: optional chaining (?.), nullish coalescing
            # (??), top-level await, import assertions, ERR_REQUIRE_ESM.
            {
                "pattern": (
                    r"SyntaxError: Unexpected token '\?'|"
                    r"SyntaxError: Unexpected token '\.\.'|"
                    r"SyntaxError.*optional chaining|"
                    r"SyntaxError.*nullish coalescing|"
                    r"ERR_REQUIRE_ESM|"
                    r"ERR_UNKNOWN_FILE_EXTENSION|"
                    r"ERR_UNSUPPORTED_ESM_URL_SCHEME|"
                    r"requires a peer of node@|"
                    r"engine.*node.*npm.*incompatible|"
                    r"The engine \"node\" is incompatible"
                ),
                "failure_id": "node_version_too_old",
                "category": "environment",
                "label": "Node.js version too old for this code",
                "description": (
                    "The installed Node.js version does not support "
                    "modern JavaScript syntax or features. Many tools "
                    "and frameworks require Node.js 18+ for features "
                    "like optional chaining (?.), nullish coalescing "
                    "(??), native ESM imports, and fetch(). Distro "
                    "packages often ship outdated versions."
                ),
                "example_stderr": (
                    "SyntaxError: Unexpected token '?'\n"
                    "    at wrapSafe (internal/modules/cjs/"
                    "loader.js:915:16)"
                ),
                "options": [
                    {
                        "id": "install-via-default",
                        "label": "Install latest LTS from nodejs.org",
                        "description": (
                            "Download the latest LTS Node.js binary "
                            "directly from nodejs.org. This provides the "
                            "newest stable version regardless of distro "
                            "packages."
                        ),
                        "icon": "⬇️",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "_default",
                        "risk": "low",
                    },
                    {
                        "id": "install-via-snap",
                        "label": "Install latest Node.js via snap",
                        "description": (
                            "Snap provides a near-latest Node.js that is "
                            "independent of distro package versions."
                        ),
                        "icon": "📦",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "snap",
                        "risk": "low",
                    },
                    {
                        "id": "use-nvm",
                        "label": "Install Node.js via nvm",
                        "description": (
                            "Use nvm (Node Version Manager) to install "
                            "and manage multiple Node.js versions."
                        ),
                        "icon": "🔄",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "Install nvm, then install the latest LTS:\n"
                            "curl -o- https://raw.githubusercontent.com/"
                            "nvm-sh/nvm/v0.40.1/install.sh | bash\n"
                            "source ~/.bashrc\n"
                            "nvm install --lts"
                        ),
                        "risk": "low",
                    },
                ],
            },

            # ── npm not found after node install ─────────────────────
            # On Debian/Ubuntu/Alpine/Arch, the npm binary is packaged
            # separately from nodejs. If only nodejs was installed
            # (manually, or by a dependency), npm is missing.
            {
                "pattern": (
                    r"npm: command not found|"
                    r"npm: not found|"
                    r"/usr/bin/env:.*npm.*No such file|"
                    r"sh:.*npm.*not found"
                ),
                "failure_id": "node_npm_not_found",
                "category": "dependency",
                "label": "npm not found (packaged separately)",
                "description": (
                    "Node.js is installed but npm is missing. On "
                    "Debian/Ubuntu, Alpine, and Arch Linux, npm is "
                    "distributed as a separate system package. When "
                    "only 'nodejs' is installed via the package manager, "
                    "'npm' is not included automatically."
                ),
                "example_stderr": (
                    "bash: npm: command not found"
                ),
                "options": [
                    {
                        "id": "install-npm-pkg",
                        "label": "Install npm via package manager",
                        "description": (
                            "Install the npm package from your system's "
                            "package manager."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "install_dep",
                        "dep": "npm",
                        "risk": "low",
                    },
                    {
                        "id": "reinstall-node-default",
                        "label": "Reinstall from nodejs.org (includes npm)",
                        "description": (
                            "The pre-compiled Node.js binary from "
                            "nodejs.org includes npm and npx bundled. "
                            "This avoids the split-package issue entirely."
                        ),
                        "icon": "⬇️",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "_default",
                        "risk": "low",
                    },
                ],
            },

            # ── Alpine musl libc incompatibility ────────────────────
            # The official Node.js binaries are compiled against glibc.
            # Alpine uses musl libc. Running a glibc-linked binary on
            # Alpine produces a cryptic "not found" or ENOENT error
            # because the dynamic linker (ld-linux-x86-64.so.2) doesn't
            # exist on musl systems.
            {
                "pattern": (
                    r"Error loading shared library.*ld-linux|"
                    r"No such file or directory.*ld-linux|"
                    r"error while loading shared libraries.*ld-linux|"
                    r"not found.*ld-linux-x86-64|"
                    r"not found.*ld-linux-aarch64"
                ),
                "failure_id": "node_musl_incompatible",
                "category": "environment",
                "label": "Node.js binary incompatible with musl (Alpine)",
                "description": (
                    "The pre-compiled Node.js binary was built for "
                    "glibc but this system uses musl libc (Alpine "
                    "Linux). glibc-linked binaries cannot run on musl "
                    "systems because the expected dynamic linker "
                    "(ld-linux-x86-64.so.2) does not exist."
                ),
                "example_stderr": (
                    "/usr/local/bin/node: error while loading shared "
                    "libraries: ld-linux-x86-64.so.2: "
                    "cannot open shared object file: "
                    "No such file or directory"
                ),
                "options": [
                    {
                        "id": "install-via-apk",
                        "label": "Install Node.js via apk (Alpine-native)",
                        "description": (
                            "Use Alpine's package manager (apk) to "
                            "install a musl-compatible Node.js build. "
                            "This is the correct approach on Alpine."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "apk",
                        "risk": "low",
                    },
                    {
                        "id": "install-compat-layer",
                        "label": "Install glibc compatibility layer",
                        "description": (
                            "Install libc6-compat to provide a glibc "
                            "shim on Alpine. This may allow glibc-linked "
                            "binaries to run but is not recommended for "
                            "production."
                        ),
                        "icon": "🔧",
                        "recommended": False,
                        "strategy": "install_packages",
                        "packages": {
                            "debian": [],
                            "rhel": [],
                            "alpine": ["libc6-compat", "libstdc++"],
                            "arch": [],
                            "suse": [],
                            "macos": [],
                        },
                        "risk": "medium",
                    },
                ],
            },

            # ── Exec format error (arch mismatch) ─────────────────
            # Defense-in-depth: the L0 system profiler now detects
            # 64-bit kernel + 32-bit userland (Raspbian) and corrects
            # the arch, so this should rarely fire. But if someone
            # manually installs an arm64 binary on 32-bit userland,
            # or the detection fails, this catches it.
            {
                "pattern": (
                    r"exec format error|"
                    r"cannot execute binary file.*Exec format|"
                    r"cannot execute: required file not found"
                ),
                "failure_id": "node_exec_format_error",
                "category": "environment",
                "label": "Node.js binary architecture mismatch",
                "description": (
                    "The Node.js binary was compiled for a different "
                    "CPU architecture than this system's userland. "
                    "This commonly occurs on Raspberry Pi systems "
                    "where the kernel is 64-bit (aarch64) but the "
                    "userland is 32-bit (armv7l)."
                ),
                "example_stderr": (
                    "bash: /usr/local/bin/node: "
                    "cannot execute binary file: Exec format error"
                ),
                "options": [
                    {
                        "id": "reinstall-correct-arch",
                        "label": "Reinstall with correct architecture",
                        "description": (
                            "Remove the wrong-architecture binary and "
                            "reinstall using the system package manager "
                            "which will select the correct architecture "
                            "automatically."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "apt",
                        "risk": "low",
                    },
                    {
                        "id": "install-via-snap",
                        "label": "Install via snap",
                        "description": (
                            "Use snap to install Node.js. Snap "
                            "packages are architecture-aware and will "
                            "install the correct build automatically."
                        ),
                        "icon": "📦",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "snap",
                        "risk": "low",
                    },
                ],
            },
]
