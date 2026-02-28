"""
L0 Data — npm method-family remediation handlers.

Pure data, no logic.
"""

from __future__ import annotations


_NPM_HANDLERS: list[dict] = [
        {
            "pattern": r"EACCES.*permission denied",
            "failure_id": "npm_eacces",
            "category": "permissions",
            "label": "npm permission denied",
            "description": "npm cannot write to global node_modules.",
            "example_stderr": "npm ERR! Error: EACCES: permission denied, mkdir '/usr/local/lib/node_modules'",
            "options": [
                {
                    "id": "retry-sudo",
                    "label": "Retry with sudo",
                    "description": "Re-run the npm install with sudo privileges",
                    "icon": "🔒",
                    "recommended": True,
                    "strategy": "retry_with_modifier",
                    "modifier": {"retry_sudo": True},
                },
                {
                    "id": "fix-npm-prefix",
                    "label": "Fix npm prefix (user-local)",
                    "description": "Configure npm to install packages in ~/.npm-global",
                    "icon": "🔧",
                    "recommended": False,
                    "strategy": "env_fix",
                    "fix_commands": [
                        ["npm", "config", "set", "prefix", "${HOME}/.npm-global"],
                    ],
                },
            ],
        },
        {
            "pattern": r"npm:\s*command not found|npm:\s*not found",
            "failure_id": "missing_npm",
            "category": "dependency",
            "label": "npm not installed",
            "description": "npm is required but not found on this system.",
            "example_stderr": "npm: command not found",
            "options": [
                {
                    "id": "install-npm",
                    "label": "Install npm via system packages",
                    "description": "Use the OS package manager to install Node.js + npm",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_dep",
                    "dep": "npm",
                },
                {
                    "id": "install-nvm",
                    "label": "Install via nvm (Node Version Manager)",
                    "description": "Install nvm for flexible Node.js version management",
                    "icon": "🌐",
                    "recommended": False,
                    "strategy": "install_dep",
                    "dep": "nvm",
                },
            ],
        },
        {
            "pattern": r"ERESOLVE.*unable to resolve|could not resolve dependency",
            "failure_id": "npm_eresolve",
            "category": "dependency",
            "label": "npm dependency conflict",
            "description": "npm cannot resolve the dependency tree due to peer dependency conflicts.",
            "example_stderr": "npm ERR! ERESOLVE unable to resolve dependency tree",
            "options": [
                {
                    "id": "retry-legacy-peers",
                    "label": "Retry with --legacy-peer-deps",
                    "description": "Ignore peer dependency conflicts (safe for most cases)",
                    "icon": "🔧",
                    "recommended": True,
                    "strategy": "retry_with_modifier",
                    "modifier": {"npm_legacy_peer_deps": True},
                },
                {
                    "id": "retry-force",
                    "label": "Retry with --force",
                    "description": "Force install despite conflicts (may cause runtime issues)",
                    "icon": "⚠️",
                    "recommended": False,
                    "strategy": "retry_with_modifier",
                    "modifier": {"npm_force": True},
                    "risk": "high",
                },
            ],
        },
        {
            "pattern": (
                r"npm does not support Node\.js v|"
                r"npm v\d+\.\d+\.\d+ does not support|"
                r"SyntaxError: Unexpected token"
            ),
            "failure_id": "npm_node_too_old",
            "category": "dependency",
            "label": "Node.js version too old for npm",
            "description": (
                "The installed Node.js version is too old for this "
                "version of npm or the package being installed."
            ),
            "example_stderr": "npm does not support Node.js v12.22.9",
            "options": [
                {
                    "id": "update-node",
                    "label": "Update Node.js",
                    "description": "Update Node.js to a supported version via the system package manager",
                    "icon": "⬆️",
                    "recommended": True,
                    "strategy": "install_dep",
                    "dep": "node",
                },
                {
                    "id": "install-node-snap",
                    "label": "Install Node.js via snap (latest)",
                    "description": "Install the latest Node.js via snap for a modern version",
                    "icon": "🌐",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Install latest Node.js via snap:\n"
                        "  sudo snap install node --classic\n"
                        "  # Then retry the npm command"
                    ),
                },
            ],
        },
        {
            "pattern": (
                r"node-gyp|gyp ERR!|"
                r"make: \*\*\*.*Error|"
                r"g\+\+: error:|gcc: error:|"
                r"not found: make|"
                r"python[23]?: not found"
            ),
            "failure_id": "node_gyp_build_fail",
            "category": "compiler",
            "label": "Native addon build failed (node-gyp)",
            "description": (
                "npm tried to compile a native C/C++ addon but the "
                "build toolchain is missing or incompatible. Common "
                "on ARM (Raspberry Pi), Alpine (musl libc), and "
                "minimal Docker images."
            ),
            "example_stderr": "gyp ERR! build error\ngyp ERR! not ok",
            "options": [
                {
                    "id": "install-build-tools",
                    "label": "Install build tools (gcc, make, python3)",
                    "description": (
                        "Install the C/C++ toolchain needed by "
                        "node-gyp to compile native addons"
                    ),
                    "icon": "🔧",
                    "recommended": True,
                    "strategy": "install_packages",
                    "packages": {
                        "debian": ["build-essential", "python3"],
                        "rhel": ["gcc-c++", "make", "python3"],
                        "alpine": ["build-base", "python3"],
                        "arch": ["base-devel", "python"],
                        "suse": ["devel_basis", "python3"],
                        "macos": ["python3"],
                    },
                },
                {
                    "id": "retry-ignore-scripts",
                    "label": "Retry with --ignore-scripts",
                    "description": (
                        "Skip native compilation (package may lose "
                        "features that depend on native code)"
                    ),
                    "icon": "⏭️",
                    "recommended": False,
                    "strategy": "retry_with_modifier",
                    "modifier": {"npm_ignore_scripts": True},
                    "risk": "medium",
                },
            ],
        },
        {
            "pattern": (
                r"cb\(\) never called|"
                r"Unexpected end of JSON input|"
                r"EINTEGRITY|"
                r"Invalid response body"
            ),
            "failure_id": "npm_cache_corruption",
            "category": "environment",
            "label": "npm cache corrupted",
            "description": (
                "npm's local cache is corrupted. This can happen after "
                "interrupted installs, disk issues, or npm version upgrades."
            ),
            "example_stderr": "npm ERR! cb() never called!",
            "options": [
                {
                    "id": "clean-cache-retry",
                    "label": "Clean npm cache and retry",
                    "description": "Run 'npm cache clean --force' to clear the corrupted cache",
                    "icon": "🧹",
                    "recommended": True,
                    "strategy": "cleanup_retry",
                    "cleanup_commands": [
                        ["npm", "cache", "clean", "--force"],
                    ],
                },
            ],
        },
        {
            "pattern": (
                r"401 Unauthorized|"
                r"403 Forbidden|"
                r"Unable to authenticate|"
                r"code E401|code E403"
            ),
            "failure_id": "npm_registry_auth",
            "category": "network",
            "label": "npm registry authentication failed",
            "description": (
                "npm received a 401 or 403 from the registry. This "
                "usually means a private registry needs login, or a "
                "corporate proxy is blocking access."
            ),
            "example_stderr": "npm ERR! code E401\nnpm ERR! 401 Unauthorized",
            "options": [
                {
                    "id": "npm-login",
                    "label": "Login to npm registry",
                    "description": "Run 'npm login' to authenticate with the registry",
                    "icon": "🔑",
                    "recommended": True,
                    "strategy": "manual",
                    "instructions": (
                        "Authenticate with the npm registry:\n"
                        "  npm login\n"
                        "For private registries, set the registry URL first:\n"
                        "  npm config set registry https://your-registry.example.com/\n"
                        "Then retry the install."
                    ),
                },
                {
                    "id": "use-public-registry",
                    "label": "Switch to public npm registry",
                    "description": (
                        "Reset npm to use the default public registry "
                        "(if a private registry was configured by mistake)"
                    ),
                    "icon": "🌐",
                    "recommended": False,
                    "strategy": "env_fix",
                    "fix_commands": [
                        ["npm", "config", "set", "registry",
                         "https://registry.npmjs.org/"],
                    ],
                },
            ],
        },
        {
            "pattern": (
                r"ERR! notarget|"
                r"No matching version found|"
                r"ETARGET"
            ),
            "failure_id": "npm_etarget",
            "category": "dependency",
            "label": "Package version not found",
            "description": (
                "The requested version of the package does not "
                "exist on the npm registry."
            ),
            "example_stderr": (
                "npm ERR! notarget No matching version found "
                "for package@99.0.0"
            ),
            "options": [
                {
                    "id": "retry-latest",
                    "label": "Retry with latest version",
                    "description": (
                        "Remove the version constraint and install "
                        "the latest available version"
                    ),
                    "icon": "⬆️",
                    "recommended": True,
                    "strategy": "retry_with_modifier",
                    "modifier": {"npm_use_latest": True},
                },
                {
                    "id": "check-registry",
                    "label": "Check available versions",
                    "description": (
                        "List available versions to find the right one"
                    ),
                    "icon": "🔍",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Check available versions:\n"
                        "  npm view <package> versions --json\n"
                        "Then retry with a valid version."
                    ),
                },
            ],
        },
        {
            "pattern": (
                r"code ELIFECYCLE|"
                r"lifecycle script|"
                r"ERR! lifecycle|"
                r"failed with exit code [1-9]"
            ),
            "failure_id": "npm_elifecycle",
            "category": "install",
            "label": "npm lifecycle script failed",
            "description": (
                "A package's install/postinstall/preinstall script "
                "crashed. This often means the package tried to "
                "compile native code or run a setup step that failed."
            ),
            "example_stderr": (
                "npm ERR! code ELIFECYCLE\n"
                "npm ERR! errno 1\n"
                "npm ERR! some-package@1.0.0 postinstall: `node scripts/build.js`"
            ),
            "options": [
                {
                    "id": "retry-ignore-scripts",
                    "label": "Retry with --ignore-scripts",
                    "description": (
                        "Skip lifecycle scripts. Safe for CLI tools "
                        "that don't depend on postinstall steps."
                    ),
                    "icon": "⏭️",
                    "recommended": True,
                    "strategy": "retry_with_modifier",
                    "modifier": {"npm_ignore_scripts": True},
                    "risk": "medium",
                },
                {
                    "id": "install-build-deps",
                    "label": "Install build dependencies",
                    "description": (
                        "The lifecycle script may need native build "
                        "tools (gcc, make, python3)."
                    ),
                    "icon": "🔧",
                    "recommended": False,
                    "strategy": "install_packages",
                    "packages": {
                        "debian": ["build-essential", "python3"],
                        "rhel": ["gcc-c++", "make", "python3"],
                        "alpine": ["build-base", "python3"],
                        "arch": ["base-devel", "python"],
                        "suse": ["devel_basis", "python3"],
                        "macos": ["python3"],
                    },
                },
            ],
        },
        {
            "pattern": (
                r"SELF_SIGNED_CERT_IN_CHAIN|"
                r"UNABLE_TO_VERIFY_LEAF_SIGNATURE|"
                r"unable to get local issuer certificate|"
                r"ERR_TLS_CERT_ALTNAME_INVALID"
            ),
            "failure_id": "npm_self_signed_cert",
            "category": "network",
            "label": "npm TLS certificate error",
            "description": (
                "npm cannot verify the registry's TLS certificate. "
                "Common behind corporate proxies that perform TLS "
                "inspection (MITM). Also happens when custom/self-signed "
                "CA certs are used."
            ),
            "example_stderr": (
                "npm ERR! code SELF_SIGNED_CERT_IN_CHAIN\n"
                "npm ERR! unable to get local issuer certificate"
            ),
            "options": [
                {
                    "id": "set-cafile",
                    "label": "Configure corporate CA certificate",
                    "description": (
                        "Point npm to your organization's CA bundle "
                        "so it can verify the proxy's certificate"
                    ),
                    "icon": "🔒",
                    "recommended": True,
                    "strategy": "manual",
                    "instructions": (
                        "Get your corporate CA cert (.pem) from IT, "
                        "then:\n"
                        "  npm config set cafile /path/to/corporate-ca.pem\n"
                        "\n"
                        "Or append it to the Node.js CA bundle:\n"
                        "  export NODE_EXTRA_CA_CERTS=/path/to/"
                        "corporate-ca.pem\n"
                        "\n"
                        "Then retry the install."
                    ),
                },
                {
                    "id": "disable-strict-ssl",
                    "label": "Disable strict SSL (not recommended)",
                    "description": (
                        "Turn off SSL verification entirely. "
                        "Insecure — only use as a temporary workaround."
                    ),
                    "icon": "⚠️",
                    "recommended": False,
                    "strategy": "env_fix",
                    "fix_commands": [
                        ["npm", "config", "set",
                         "strict-ssl", "false"],
                    ],
                    "risk": "high",
                },
            ],
        },
        {
            "pattern": (
                r"EBADPLATFORM|"
                r"Unsupported platform|"
                r"notsup Unsupported|"
                r"not compatible with your operating system"
            ),
            "failure_id": "npm_ebadplatform",
            "category": "compatibility",
            "label": "npm package incompatible with this platform",
            "description": (
                "The package declares that it does not support this "
                "OS or CPU architecture. Common on ARM (Raspberry Pi), "
                "Alpine (musl), or when a package is Windows/macOS-only."
            ),
            "example_stderr": (
                "npm ERR! notsup Unsupported platform for "
                "fsevents@2.3.3: wanted {\"os\":\"darwin\"}"
            ),
            "options": [
                {
                    "id": "retry-force",
                    "label": "Retry with --force",
                    "description": (
                        "Force installation anyway. The package "
                        "may work if the platform check is overly "
                        "strict (common with optional deps like fsevents)."
                    ),
                    "icon": "⚠️",
                    "recommended": True,
                    "strategy": "retry_with_modifier",
                    "modifier": {"npm_force": True},
                    "risk": "medium",
                },
                {
                    "id": "check-alternative",
                    "label": "Find cross-platform alternative",
                    "description": (
                        "Search for an alternative package that "
                        "supports this platform"
                    ),
                    "icon": "🔍",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Check the package docs for platform support.\n"
                        "If this is an optional dependency (like "
                        "fsevents on Linux), it can be safely ignored.\n"
                        "Add to .npmrc:\n"
                        "  optional = false"
                    ),
                },
            ],
        },
        {
            "pattern": (
                r"code ENOENT.*npm|"
                r"enoent ENOENT.*package\.json|"
                r"Missing script:|"
                r"npm ERR! enoent"
            ),
            "failure_id": "npm_enoent",
            "category": "environment",
            "label": "npm file or script not found",
            "description": (
                "npm could not find a required file — usually "
                "package.json or a script referenced in lifecycle "
                "hooks. This can mean the working directory is wrong "
                "or the package is corrupted."
            ),
            "example_stderr": (
                "npm ERR! enoent ENOENT: no such file or directory, "
                "open '/path/to/package.json'"
            ),
            "options": [
                {
                    "id": "retry-ignore-scripts",
                    "label": "Retry with --ignore-scripts",
                    "description": (
                        "Skip lifecycle scripts that reference "
                        "missing files"
                    ),
                    "icon": "⏭️",
                    "recommended": True,
                    "strategy": "retry_with_modifier",
                    "modifier": {"npm_ignore_scripts": True},
                },
                {
                    "id": "clean-reinstall",
                    "label": "Clean node_modules and retry",
                    "description": (
                        "Delete node_modules and package-lock.json, "
                        "then retry"
                    ),
                    "icon": "🧹",
                    "recommended": False,
                    "strategy": "cleanup_retry",
                    "cleanup_commands": [
                        ["rm", "-rf", "node_modules"],
                        ["rm", "-f", "package-lock.json"],
                    ],
                },
            ],
        },
]
