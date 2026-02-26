"""
L0 Data — Remediation handler registries.

Three layers of failure handlers, evaluated bottom-up (most specific first):
  Layer 3: Recipe-declared (on_failure in TOOL_RECIPES) — not here
  Layer 2: Method-family handlers (METHOD_FAMILY_HANDLERS)
  Layer 1: Infrastructure handlers (INFRA_HANDLERS)
  Layer 0: Bootstrap handlers (BOOTSTRAP_HANDLERS)

Each handler detects a failure pattern and offers MULTIPLE remediation
options. Option availability (ready/locked/impossible) is computed at
runtime by domain/remediation_planning.py — not stored here.

See .agent/plans/tool_install/remediation-model.md for full design.
"""

from __future__ import annotations

# ── Valid values ────────────────────────────────────────────────

VALID_STRATEGIES = {
    "install_dep",
    "install_dep_then_switch",
    "install_packages",
    "switch_method",
    "retry_with_modifier",
    "add_repo",
    "upgrade_dep",
    "env_fix",
    "manual",
    "cleanup_retry",
}

VALID_AVAILABILITY = {"ready", "locked", "impossible"}

VALID_CATEGORIES = {
    "environment",
    "dependency",
    "permissions",
    "network",
    "disk",
    "resources",
    "timeout",
    "compiler",
    "package_manager",
    "bootstrap",
}


# ═════════════════════════════════════════════════════════════════
# Layer 2 — Method-family handlers
# ═════════════════════════════════════════════════════════════════

METHOD_FAMILY_HANDLERS: dict[str, list[dict]] = {

    # ── pip ──────────────────────────────────────────────────────

    "pip": [
        {
            "pattern": r"externally.managed.environment",
            "failure_id": "pep668",
            "category": "environment",
            "label": "Externally managed Python (PEP 668)",
            "description": (
                "This system's Python is managed by the OS package manager. "
                "pip install is blocked to prevent conflicts."
            ),
            "example_stderr": (
                "error: externally-managed-environment\n"
                "\u00d7 This environment is externally managed\n"
                "\u2570\u2500> To install Python packages system-wide, try apt install\n"
                "    python3-xyz, where xyz is the package you are trying to install."
            ),
            "options": [
                {
                    "id": "use-pipx",
                    "label": "Install via pipx",
                    "description": "pipx installs in isolated venvs, avoids PEP 668",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_dep_then_switch",
                    "dep": "pipx",
                    "switch_to": "pipx",
                },
                {
                    "id": "use-apt",
                    "label": "Install via apt package",
                    "description": "Use the distro package (may be older version)",
                    "icon": "🐧",
                    "recommended": False,
                    "strategy": "switch_method",
                    "method": "apt",
                },
                {
                    "id": "use-venv",
                    "label": "Install in virtual environment",
                    "description": "Creates ~/.local/venvs/tools and installs there",
                    "icon": "🐍",
                    "recommended": False,
                    "strategy": "env_fix",
                    "fix_commands": [
                        ["python3", "-m", "venv", "--system-site-packages",
                         "${HOME}/.local/venvs/tools"],
                    ],
                },
                {
                    "id": "break-system",
                    "label": "Override with --break-system-packages",
                    "description": "Forces pip install into system Python (risky)",
                    "icon": "⚠️",
                    "recommended": False,
                    "strategy": "retry_with_modifier",
                    "modifier": {"extra_args": ["--break-system-packages"]},
                    "risk": "high",
                },
            ],
        },
        {
            "pattern": r"No module named pip|pip:\s*command not found|pip:\s*not found",
            "failure_id": "missing_pip",
            "category": "dependency",
            "label": "pip not installed",
            "description": "pip is required but not found on this system.",
            "example_stderr": "pip: command not found",
            "options": [
                {
                    "id": "install-pip-system",
                    "label": "Install pip via system packages",
                    "description": "Use the OS package manager to install pip",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_dep",
                    "dep": "pip",
                },
                {
                    "id": "install-pip-bootstrap",
                    "label": "Bootstrap pip with get-pip.py",
                    "description": "Download and run the official pip bootstrapper",
                    "icon": "🌐",
                    "recommended": False,
                    "strategy": "env_fix",
                    "fix_commands": [
                        ["bash", "-c",
                         "curl -sS https://bootstrap.pypa.io/get-pip.py | python3"],
                    ],
                },
            ],
        },
    ],

    # ── cargo ────────────────────────────────────────────────────

    "cargo": [
        {
            "pattern": r"requires rustc (\d+\.\d+(?:\.\d+)?)\s+or newer.*?"
                       r"currently active rustc version is (\d+\.\d+(?:\.\d+)?)",
            "failure_id": "rustc_version_mismatch",
            "category": "dependency",
            "label": "Rust compiler too old",
            "description": "This crate requires a newer Rust compiler than what's installed.",
            "example_stderr": (
                "error: package `tokio v1.35.0` requires rustc 1.70.0 or newer — "
                "currently active rustc version is 1.56.1"
            ),
            "options": [
                {
                    "id": "upgrade-rustup",
                    "label": "Upgrade Rust via rustup",
                    "description": "Install rustup + latest Rust, then retry",
                    "icon": "⬆️",
                    "recommended": True,
                    "strategy": "upgrade_dep",
                    "dep": "rustup",
                },
                {
                    "id": "compatible-version",
                    "label": "Install compatible older version",
                    "description": "Install the latest version that supports your rustc",
                    "icon": "📦",
                    "recommended": False,
                    "strategy": "retry_with_modifier",
                    "modifier": {"use_compatible_version": True},
                },
            ],
        },
        {
            "pattern": r"COMPILER BUG DETECTED|memcmp.*gcc\.gnu\.org",
            "failure_id": "gcc_memcmp_bug",
            "category": "compiler",
            "label": "GCC compiler bug (aws-lc-sys)",
            "description": (
                "Your GCC version has a known memcmp bug that prevents "
                "building crypto dependencies (aws-lc-sys)."
            ),
            "example_stderr": (
                "error[internal]: COMPILER BUG DETECTED — see "
                "https://gcc.gnu.org/bugzilla/show_bug.cgi?id=95189"
            ),
            "options": [
                {
                    "id": "install-gcc12",
                    "label": "Install GCC 12+",
                    "description": "Install a newer GCC without the memcmp bug, then rebuild",
                    "icon": "⬆️",
                    "recommended": True,
                    "strategy": "install_packages",
                    "packages": {
                        "debian": ["gcc-12", "g++-12"],
                        "rhel": ["gcc-toolset-12-gcc", "gcc-toolset-12-gcc-c++"],
                        "alpine": ["gcc"],
                        "arch": ["gcc"],
                    },
                    "env_override": {"CC": "gcc-12", "CXX": "g++-12"},
                },
                {
                    "id": "use-clang",
                    "label": "Build with Clang",
                    "description": "Use clang instead of gcc to avoid the compiler bug",
                    "icon": "🔧",
                    "recommended": False,
                    "strategy": "install_dep",
                    "dep": "clang",
                    "env_override": {"CC": "clang", "CXX": "clang++"},
                },
            ],
        },
        {
            "pattern": r"cannot find -l(\S+)",
            "failure_id": "missing_c_library",
            "category": "dependency",
            "label": "Missing C library",
            "description": "A C library needed for compilation is missing.",
            "example_stderr": "/usr/bin/ld: cannot find -lssl: No such file or directory",
            "options": [
                {
                    "id": "install-missing-lib",
                    "label": "Install missing library",
                    "description": "Install the development package for the missing library",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_packages",
                    "dynamic_packages": True,
                },
            ],
        },
        {
            "pattern": r"error: linker `cc` not found|"
                       r"cc:\s*not found|gcc:\s*not found",
            "failure_id": "missing_compiler",
            "category": "dependency",
            "label": "C/C++ compiler not found",
            "description": "A C compiler is required to build this crate.",
            "example_stderr": "error: linker `cc` not found",
            "options": [
                {
                    "id": "install-build-essential",
                    "label": "Install build tools",
                    "description": "Install gcc, make, and essential build dependencies",
                    "icon": "🔧",
                    "recommended": True,
                    "strategy": "install_packages",
                    "packages": {
                        "debian": ["build-essential"],
                        "rhel": ["gcc", "gcc-c++", "make"],
                        "alpine": ["build-base"],
                        "arch": ["base-devel"],
                        "suse": ["gcc", "gcc-c++", "make"],
                    },
                },
            ],
        },
    ],

    # ── npm ──────────────────────────────────────────────────────

    "npm": [
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
    ],

    # ── apt ──────────────────────────────────────────────────────

    "apt": [
        {
            "pattern": r"Unable to locate package",
            "failure_id": "apt_stale_index",
            "category": "package_manager",
            "label": "Package not found — stale index",
            "description": "apt package index may be outdated.",
            "example_stderr": "E: Unable to locate package ruff",
            "options": [
                {
                    "id": "apt-update-retry",
                    "label": "Update package index and retry",
                    "description": "Run apt-get update, then retry the install",
                    "icon": "🔄",
                    "recommended": True,
                    "strategy": "cleanup_retry",
                    "cleanup_commands": [["apt-get", "update"]],
                },
                {
                    "id": "switch-to-other",
                    "label": "Try alternative install method",
                    "description": "Use a different install method for this tool",
                    "icon": "🔧",
                    "recommended": False,
                    "strategy": "switch_method",
                    "method": "_default",
                },
            ],
        },
        {
            "pattern": r"Could not get lock|dpkg was interrupted",
            "failure_id": "apt_locked",
            "category": "package_manager",
            "label": "Package manager locked",
            "description": "Another process is using apt/dpkg. Wait and retry.",
            "example_stderr": "E: Could not get lock /var/lib/dpkg/lock-frontend",
            "options": [
                {
                    "id": "wait-retry",
                    "label": "Wait and retry",
                    "description": "Wait 30 seconds for the lock to release, then retry",
                    "icon": "⏳",
                    "recommended": True,
                    "strategy": "retry_with_modifier",
                    "modifier": {"wait_seconds": 30, "retry": True},
                },
                {
                    "id": "manual-unlock",
                    "label": "Manual intervention",
                    "description": "Check what process holds the lock",
                    "icon": "🔍",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Check for a running apt/dpkg process:\n"
                        "  sudo lsof /var/lib/dpkg/lock-frontend\n"
                        "  sudo kill <PID> or wait for it to finish"
                    ),
                },
            ],
        },
    ],

    # ── dnf ──────────────────────────────────────────────────────

    "dnf": [
        {
            "pattern": r"No match for argument",
            "failure_id": "dnf_no_match",
            "category": "package_manager",
            "label": "Package not found",
            "description": "Package name may differ on this distro/version.",
            "example_stderr": "Error: No match for argument: ruff",
            "options": [
                {
                    "id": "enable-epel",
                    "label": "Enable EPEL repository",
                    "description": "Install and enable EPEL for extra packages",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_packages",
                    "packages": {"rhel": ["epel-release"]},
                },
                {
                    "id": "switch-method",
                    "label": "Try alternative install method",
                    "description": "Use a different install method for this tool",
                    "icon": "🔧",
                    "recommended": False,
                    "strategy": "switch_method",
                    "method": "_default",
                },
            ],
        },
    ],

    # ── yum ──────────────────────────────────────────────────────

    "yum": [
        {
            "pattern": r"No package .* available",
            "failure_id": "yum_no_package",
            "category": "package_manager",
            "label": "Package not available",
            "description": "Package may not exist in enabled repos.",
            "example_stderr": "No package ruff available.",
            "options": [
                {
                    "id": "enable-epel",
                    "label": "Enable EPEL repository",
                    "description": "Install and enable EPEL for extra packages",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_packages",
                    "packages": {"rhel": ["epel-release"]},
                },
                {
                    "id": "switch-method",
                    "label": "Try alternative install method",
                    "description": "Use a different install method for this tool",
                    "icon": "🔧",
                    "recommended": False,
                    "strategy": "switch_method",
                    "method": "_default",
                },
            ],
        },
    ],

    # ── snap ─────────────────────────────────────────────────────

    "snap": [
        {
            "pattern": (
                r"cannot communicate with server|"
                r"system does not fully support snapd|"
                r"snap \"install\" is not available"
            ),
            "failure_id": "snapd_unavailable",
            "category": "environment",
            "label": "snapd not running",
            "description": "snap requires systemd. Falling back to alternative install.",
            "example_stderr": "error: cannot communicate with server: Post http://localhost/v2/snaps: dial unix /run/snapd.socket: connect: no such file or directory",
            "options": [
                {
                    "id": "switch-apt",
                    "label": "Install via apt instead",
                    "description": "Use apt package manager (if available)",
                    "icon": "🐧",
                    "recommended": True,
                    "strategy": "switch_method",
                    "method": "apt",
                },
                {
                    "id": "switch-default",
                    "label": "Install via direct download",
                    "description": "Use the default install script",
                    "icon": "🌐",
                    "recommended": False,
                    "strategy": "switch_method",
                    "method": "_default",
                },
            ],
        },
    ],

    # ── brew ─────────────────────────────────────────────────────

    "brew": [
        {
            "pattern": r"No formulae found|No available formula",
            "failure_id": "brew_no_formula",
            "category": "package_manager",
            "label": "Homebrew formula not found",
            "description": "This tool isn't available via Homebrew.",
            "example_stderr": "Error: No formulae found for \"ruff\".",
            "options": [
                {
                    "id": "switch-default",
                    "label": "Install via direct download",
                    "description": "Use the default install script or binary release",
                    "icon": "🌐",
                    "recommended": True,
                    "strategy": "switch_method",
                    "method": "_default",
                },
                {
                    "id": "switch-pip",
                    "label": "Install via pip",
                    "description": "Use pip if this is a Python tool",
                    "icon": "🐍",
                    "recommended": False,
                    "strategy": "switch_method",
                    "method": "pip",
                },
            ],
        },
    ],

    # ── _default (curl/bash/wget scripts) ────────────────────────

    "_default": [
        {
            "pattern": r"curl:\s*command not found|curl:\s*not found",
            "failure_id": "missing_curl",
            "category": "dependency",
            "label": "curl not installed",
            "description": "curl is required to download the install script.",
            "example_stderr": "bash: curl: command not found",
            "options": [
                {
                    "id": "install-curl",
                    "label": "Install curl",
                    "description": "Install curl via system package manager",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_dep",
                    "dep": "curl",
                },
                {
                    "id": "use-wget",
                    "label": "Use wget instead",
                    "description": "Try downloading with wget instead of curl",
                    "icon": "🔧",
                    "recommended": False,
                    "strategy": "retry_with_modifier",
                    "modifier": {"substitute_curl_with_wget": True},
                },
            ],
        },
        {
            "pattern": r"git:\s*command not found|git:\s*not found",
            "failure_id": "missing_git",
            "category": "dependency",
            "label": "git not installed",
            "description": "git is required to clone the source repository.",
            "example_stderr": "bash: git: command not found",
            "options": [
                {
                    "id": "install-git",
                    "label": "Install git",
                    "description": "Install git via system package manager",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_dep",
                    "dep": "git",
                },
            ],
        },
        {
            "pattern": r"wget:\s*command not found|wget:\s*not found",
            "failure_id": "missing_wget",
            "category": "dependency",
            "label": "wget not installed",
            "description": "wget is required to download files.",
            "example_stderr": "bash: wget: command not found",
            "options": [
                {
                    "id": "install-wget",
                    "label": "Install wget",
                    "description": "Install wget via system package manager",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_dep",
                    "dep": "wget",
                },
            ],
        },
        {
            "pattern": r"unzip:\s*command not found|unzip:\s*not found",
            "failure_id": "missing_unzip",
            "category": "dependency",
            "label": "unzip not installed",
            "description": "unzip is required to extract downloaded archives.",
            "example_stderr": "bash: unzip: command not found",
            "options": [
                {
                    "id": "install-unzip",
                    "label": "Install unzip",
                    "description": "Install unzip via system package manager",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_dep",
                    "dep": "unzip",
                },
            ],
        },
    ],

    # ── source (from-source builds) ──────────────────────────────

    "source": [
        {
            "pattern": r"fatal error:\s*.+\.h:\s*No such file",
            "failure_id": "missing_header",
            "category": "dependency",
            "label": "Missing header file",
            "description": "A C/C++ header file required for compilation is missing.",
            "example_stderr": "fatal error: openssl/ssl.h: No such file or directory",
            "options": [
                {
                    "id": "install-dev-packages",
                    "label": "Install development packages",
                    "description": "Install the -dev/-devel package for the missing header",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_packages",
                    "dynamic_packages": True,
                },
            ],
        },
        {
            "pattern": r"cc:\s*not found|g\+\+:\s*not found|gcc:\s*not found",
            "failure_id": "missing_compiler_source",
            "category": "dependency",
            "label": "C/C++ compiler not found",
            "description": "A C compiler is required to build from source.",
            "example_stderr": "/bin/sh: 1: cc: not found",
            "options": [
                {
                    "id": "install-build-essential",
                    "label": "Install build tools",
                    "description": "Install gcc, make, and essential build dependencies",
                    "icon": "🔧",
                    "recommended": True,
                    "strategy": "install_packages",
                    "packages": {
                        "debian": ["build-essential"],
                        "rhel": ["gcc", "gcc-c++", "make"],
                        "alpine": ["build-base"],
                        "arch": ["base-devel"],
                        "suse": ["gcc", "gcc-c++", "make"],
                    },
                },
            ],
        },
        {
            "pattern": r"could not find.*?package\s+(\S+)",
            "failure_id": "cmake_package_not_found",
            "category": "dependency",
            "label": "CMake package not found",
            "description": "A required CMake package is not available.",
            "example_stderr": "CMake Error: could not find required package OpenSSL",
            "options": [
                {
                    "id": "install-cmake-deps",
                    "label": "Install missing CMake dependency",
                    "description": "Install the system package providing the CMake module",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_packages",
                    "dynamic_packages": True,
                },
                {
                    "id": "set-cmake-prefix",
                    "label": "Set CMAKE_PREFIX_PATH",
                    "description": "Point CMake to the correct install location",
                    "icon": "🔧",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Set CMAKE_PREFIX_PATH to include the package location:\n"
                        "  export CMAKE_PREFIX_PATH=/usr/local:$CMAKE_PREFIX_PATH"
                    ),
                },
            ],
        },
    ],
}


# ═════════════════════════════════════════════════════════════════
# Layer 1 — Infrastructure handlers
# ═════════════════════════════════════════════════════════════════

INFRA_HANDLERS: list[dict] = [

    # ── Network ──

    {
        "pattern": (
            r"Could not resolve|Connection timed out|Failed to fetch|"
            r"Network is unreachable|Temporary failure in name resolution|"
            r"Failed to connect"
        ),
        "failure_id": "network_offline",
        "category": "network",
        "label": "Network unreachable",
        "description": "Cannot reach the download server.",
        "example_stderr": "curl: (6) Could not resolve host: github.com",
        "options": [
            {
                "id": "check-network",
                "label": "Check network connectivity",
                "description": "Verify DNS, routes, and proxy settings",
                "icon": "🌐",
                "recommended": True,
                "strategy": "manual",
                "instructions": (
                    "Verify network connectivity:\n"
                    "  ping -c 1 8.8.8.8\n"
                    "  nslookup github.com\n"
                    "  curl -I https://pypi.org\n"
                    "Check proxy: echo $http_proxy $https_proxy"
                ),
            },
            {
                "id": "retry-network",
                "label": "Retry (network may be transient)",
                "description": "Wait a moment and retry the download",
                "icon": "🔄",
                "recommended": False,
                "strategy": "retry_with_modifier",
                "modifier": {"wait_seconds": 10, "retry": True},
            },
        ],
    },
    {
        "pattern": (
            r"HTTP 403|HTTP 407|SSL certificate problem|"
            r"certificate verify failed|CERTIFICATE_VERIFY_FAILED"
        ),
        "failure_id": "network_blocked",
        "category": "network",
        "label": "Download blocked",
        "description": "Connection was rejected — possible proxy or TLS issue.",
        "example_stderr": "curl: (60) SSL certificate problem: unable to get local issuer certificate",
        "options": [
            {
                "id": "check-proxy-tls",
                "label": "Check proxy and TLS settings",
                "description": "Inspect proxy configuration and CA certificates",
                "icon": "🔒",
                "recommended": True,
                "strategy": "manual",
                "instructions": (
                    "Check proxy settings:\n"
                    "  echo $http_proxy $https_proxy $no_proxy\n"
                    "Check CA certificates:\n"
                    "  update-ca-certificates\n"
                    "Try with --insecure (not recommended for production):\n"
                    "  curl -k https://..."
                ),
            },
        ],
    },

    # ── Disk ──

    {
        "pattern": r"No space left on device",
        "failure_id": "disk_full",
        "category": "disk",
        "label": "Disk full",
        "description": "Not enough disk space to complete the installation.",
        "example_stderr": "write /usr/local/bin/ruff: No space left on device",
        "options": [
            {
                "id": "cleanup-apt",
                "label": "Clean package caches",
                "description": "Remove downloaded package archives to free space",
                "icon": "🧹",
                "recommended": True,
                "strategy": "cleanup_retry",
                "cleanup_commands": [["apt-get", "clean"]],
            },
            {
                "id": "cleanup-docker",
                "label": "Prune Docker resources",
                "description": "Remove unused Docker images, containers, and volumes",
                "icon": "🐳",
                "recommended": False,
                "strategy": "cleanup_retry",
                "cleanup_commands": [["docker", "system", "prune", "-f"]],
            },
            {
                "id": "check-disk",
                "label": "Check disk usage",
                "description": "Inspect what's consuming disk space",
                "icon": "🔍",
                "recommended": False,
                "strategy": "manual",
                "instructions": (
                    "Check disk usage:\n"
                    "  df -h\n"
                    "  du -sh /var/cache/apt /var/lib/docker /tmp"
                ),
            },
        ],
    },

    # ── Permissions / sudo ──

    {
        "pattern": r"is not in the sudoers file",
        "failure_id": "no_sudo_access",
        "category": "permissions",
        "label": "No sudo access",
        "description": "Your account cannot use sudo.",
        "example_stderr": "user is not in the sudoers file. This incident will be reported.",
        "options": [
            {
                "id": "switch-user-space",
                "label": "Use user-space install method",
                "description": "Switch to an install method that doesn't need sudo",
                "icon": "🔧",
                "recommended": True,
                "strategy": "switch_method",
                "method": "_default",
            },
            {
                "id": "ask-admin",
                "label": "Request sudo access",
                "description": "Ask your system administrator to grant sudo",
                "icon": "👤",
                "recommended": False,
                "strategy": "manual",
                "instructions": "Ask your admin to add you to the sudo group.",
            },
        ],
    },
    {
        "pattern": r"incorrect password|sorry, try again",
        "failure_id": "wrong_sudo_password",
        "category": "permissions",
        "label": "Wrong sudo password",
        "description": "The sudo password was incorrect.",
        "example_stderr": "Sorry, try again.\nsudo: 3 incorrect password attempts",
        "options": [
            {
                "id": "reprompt",
                "label": "Re-enter password",
                "description": "Try entering the password again",
                "icon": "🔑",
                "recommended": True,
                "strategy": "retry_with_modifier",
                "modifier": {"reprompt_password": True},
            },
        ],
    },
    {
        "pattern": r"Permission denied",
        "failure_id": "permission_denied_generic",
        "category": "permissions",
        "label": "Permission denied",
        "description": "The command needs elevated privileges.",
        "example_stderr": "error: Permission denied (os error 13)",
        "options": [
            {
                "id": "retry-sudo",
                "label": "Retry with sudo",
                "description": "Re-run the command with sudo privileges",
                "icon": "🔒",
                "recommended": True,
                "strategy": "retry_with_modifier",
                "modifier": {"retry_sudo": True},
            },
            {
                "id": "switch-user-space",
                "label": "Use user-space install",
                "description": "Switch to an install method that doesn't need root",
                "icon": "🔧",
                "recommended": False,
                "strategy": "switch_method",
                "method": "_default",
            },
        ],
    },

    # ── Process / OOM ──

    {
        "pattern": r"",
        "exit_code": 137,
        "failure_id": "oom_killed",
        "category": "resources",
        "label": "Out of memory (killed by OOM)",
        "description": "Process was killed — likely out of memory during compilation.",
        "example_stderr": "Killed",
        "example_exit_code": 137,
        "options": [
            {
                "id": "reduce-parallelism",
                "label": "Retry with reduced parallelism",
                "description": "Use fewer parallel jobs to reduce memory usage",
                "icon": "📉",
                "recommended": True,
                "strategy": "retry_with_modifier",
                "modifier": {"reduce_parallelism": True},
            },
            {
                "id": "add-swap",
                "label": "Add swap space",
                "description": "Create temporary swap to increase available memory",
                "icon": "💾",
                "recommended": False,
                "strategy": "manual",
                "instructions": (
                    "Create temporary swap:\n"
                    "  sudo fallocate -l 2G /swapfile\n"
                    "  sudo chmod 600 /swapfile\n"
                    "  sudo mkswap /swapfile\n"
                    "  sudo swapon /swapfile"
                ),
            },
        ],
    },

    # ── Timeout ──

    {
        "pattern": r"",
        "detect_fn": "timeout_expired",
        "failure_id": "command_timeout",
        "category": "timeout",
        "label": "Command timed out",
        "description": "The command exceeded its time limit.",
        "example_stderr": "error: command timed out after 120 seconds",
        "example_exit_code": 124,
        "options": [
            {
                "id": "extend-timeout",
                "label": "Retry with extended timeout",
                "description": "Double the timeout and retry",
                "icon": "⏱️",
                "recommended": True,
                "strategy": "retry_with_modifier",
                "modifier": {"extend_timeout": True},
            },
            {
                "id": "retry-network",
                "label": "Retry (may be network issue)",
                "description": "Retry after a brief pause",
                "icon": "🔄",
                "recommended": False,
                "strategy": "retry_with_modifier",
                "modifier": {"wait_seconds": 5, "retry": True},
            },
        ],
    },
]


# ═════════════════════════════════════════════════════════════════
# Layer 0 — Bootstrap handlers
# ═════════════════════════════════════════════════════════════════

BOOTSTRAP_HANDLERS: list[dict] = [
    {
        "pattern": (
            r"apt-get:\s*command not found|"
            r"dnf:\s*command not found|"
            r"apk:\s*command not found|"
            r"pacman:\s*command not found"
        ),
        "failure_id": "no_package_manager",
        "category": "bootstrap",
        "label": "No package manager found",
        "description": (
            "No system package manager is available. "
            "This system may be a minimal container or custom build."
        ),
        "example_stderr": "bash: apt-get: command not found",
        "options": [
            {
                "id": "install-brew",
                "label": "Install Homebrew",
                "description": "Install Homebrew (works on Linux and macOS)",
                "icon": "🍺",
                "recommended": True,
                "strategy": "env_fix",
                "fix_commands": [
                    ["bash", "-c",
                     '/bin/bash -c "$(curl -fsSL '
                     'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'],
                ],
            },
            {
                "id": "manual-pm",
                "label": "Manual installation",
                "description": "Install the appropriate package manager for your OS",
                "icon": "📖",
                "recommended": False,
                "strategy": "manual",
                "instructions": (
                    "Install a package manager for your OS:\n"
                    "  Debian/Ubuntu: apt-get is usually present by default\n"
                    "  Alpine: apk is present by default\n"
                    "  RHEL/Fedora: dnf is present by default\n"
                    "  macOS: install Homebrew (https://brew.sh)"
                ),
            },
        ],
    },
    {
        "pattern": r"bash:\s*command not found|/bin/sh:\s*not found",
        "failure_id": "no_shell",
        "category": "bootstrap",
        "label": "Shell not available",
        "description": "bash or sh is not available. Cannot execute install scripts.",
        "example_stderr": "/bin/sh: not found",
        "options": [
            {
                "id": "manual-shell",
                "label": "Install shell manually",
                "description": "Ensure /bin/sh or /bin/bash exists",
                "icon": "📖",
                "recommended": True,
                "strategy": "manual",
                "instructions": (
                    "This environment has no usable shell.\n"
                    "If in a container: use a base image that includes bash.\n"
                    "If on bare metal: something is seriously wrong with the OS."
                ),
            },
        ],
    },
]


# ═════════════════════════════════════════════════════════════════
# C library → package name mapping (for dynamic_packages resolution)
# ═════════════════════════════════════════════════════════════════

LIB_TO_PACKAGE_MAP: dict[str, dict[str, str]] = {
    "ssl": {
        "debian": "libssl-dev",
        "rhel": "openssl-devel",
        "alpine": "openssl-dev",
        "arch": "openssl",
        "suse": "libopenssl-devel",
        "macos": "openssl@3",
    },
    "crypto": {
        "debian": "libssl-dev",
        "rhel": "openssl-devel",
        "alpine": "openssl-dev",
        "arch": "openssl",
        "suse": "libopenssl-devel",
        "macos": "openssl@3",
    },
    "curl": {
        "debian": "libcurl4-openssl-dev",
        "rhel": "libcurl-devel",
        "alpine": "curl-dev",
        "arch": "curl",
        "suse": "libcurl-devel",
    },
    "z": {
        "debian": "zlib1g-dev",
        "rhel": "zlib-devel",
        "alpine": "zlib-dev",
        "arch": "zlib",
        "suse": "zlib-devel",
    },
    "ffi": {
        "debian": "libffi-dev",
        "rhel": "libffi-devel",
        "alpine": "libffi-dev",
        "arch": "libffi",
        "suse": "libffi-devel",
    },
    "sqlite3": {
        "debian": "libsqlite3-dev",
        "rhel": "sqlite-devel",
        "alpine": "sqlite-dev",
        "arch": "sqlite",
        "suse": "sqlite3-devel",
    },
    "xml2": {
        "debian": "libxml2-dev",
        "rhel": "libxml2-devel",
        "alpine": "libxml2-dev",
        "arch": "libxml2",
        "suse": "libxml2-devel",
    },
    "yaml": {
        "debian": "libyaml-dev",
        "rhel": "libyaml-devel",
        "alpine": "yaml-dev",
        "arch": "libyaml",
        "suse": "libyaml-devel",
    },
    "readline": {
        "debian": "libreadline-dev",
        "rhel": "readline-devel",
        "alpine": "readline-dev",
        "arch": "readline",
        "suse": "readline-devel",
    },
    "bz2": {
        "debian": "libbz2-dev",
        "rhel": "bzip2-devel",
        "alpine": "bzip2-dev",
        "arch": "bzip2",
        "suse": "libbz2-devel",
    },
    "lzma": {
        "debian": "liblzma-dev",
        "rhel": "xz-devel",
        "alpine": "xz-dev",
        "arch": "xz",
        "suse": "xz-devel",
    },
    "gdbm": {
        "debian": "libgdbm-dev",
        "rhel": "gdbm-devel",
        "alpine": "gdbm-dev",
        "arch": "gdbm",
        "suse": "gdbm-devel",
    },
    "ncurses": {
        "debian": "libncurses-dev",
        "rhel": "ncurses-devel",
        "alpine": "ncurses-dev",
        "arch": "ncurses",
        "suse": "ncurses-devel",
    },
    "png": {
        "debian": "libpng-dev",
        "rhel": "libpng-devel",
        "alpine": "libpng-dev",
        "arch": "libpng",
        "suse": "libpng16-devel",
    },
    "jpeg": {
        "debian": "libjpeg-dev",
        "rhel": "libjpeg-turbo-devel",
        "alpine": "libjpeg-turbo-dev",
        "arch": "libjpeg-turbo",
        "suse": "libjpeg-turbo-devel",
    },
    "pcre2-8": {
        "debian": "libpcre2-dev",
        "rhel": "pcre2-devel",
        "alpine": "pcre2-dev",
        "arch": "pcre2",
        "suse": "pcre2-devel",
    },
}
