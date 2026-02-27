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
    "retry",
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
    "install",
    "compatibility",
    "configuration",
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
                "pip install is blocked to prevent conflicts with system packages. "
                "The correct approach is to install into an isolated Python "
                "environment — never into the system Python directly."
            ),
            "example_stderr": (
                "error: externally-managed-environment\n"
                "\u00d7 This environment is externally managed\n"
                "\u2570\u2500> To install Python packages system-wide, try apt install\n"
                "    python3-xyz, where xyz is the package you are trying to install."
            ),
            "options": [
                {
                    "id": "use-venv",
                    "label": "Install in virtual environment (venv)",
                    "description": (
                        "Creates an isolated Python environment using the "
                        "built-in venv module. This is the safest and most "
                        "portable approach — zero additional installs needed."
                    ),
                    "icon": "🐍",
                    "recommended": True,
                    "strategy": "env_fix",
                    "pre_packages": {
                        "debian": ["python3-venv"],
                        "rhel": ["python3-virtualenv"],
                        "suse": ["python3-virtualenv"],
                    },
                    "fix_commands": [
                        ["python3", "-m", "venv",
                         "${HOME}/.local/venvs/tools"],
                        ["${HOME}/.local/venvs/tools/bin/pip", "install",
                         "${TOOL_PACKAGE}"],
                    ],
                },
                {
                    "id": "use-uv",
                    "label": "Install via uv (fast, modern)",
                    "description": (
                        "uv is a blazing-fast Python package manager written "
                        "in Rust. It creates isolated environments automatically. "
                        "If uv is not installed, it will be set up first."
                    ),
                    "icon": "⚡",
                    "recommended": False,
                    "strategy": "install_dep_then_switch",
                    "dep": "uv",
                    "switch_to": "uv",
                },
                {
                    "id": "use-conda",
                    "label": "Install via conda/mamba",
                    "description": (
                        "If you already use conda or miniconda, install the "
                        "package in your active conda environment. Do not mix "
                        "pip system installs with conda environments."
                    ),
                    "icon": "�",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Run: conda install <package> — or if the package is "
                        "not on conda-forge: conda activate <env> && pip install <package>. "
                        "Never pip install outside your conda env on a PEP 668 system."
                    ),
                },
                {
                    "id": "use-pipx",
                    "label": "Install via pipx (CLI tools only)",
                    "description": (
                        "pipx installs each CLI tool in its own isolated "
                        "virtualenv. Only suitable for command-line tools, "
                        "not for library packages."
                    ),
                    "icon": "�",
                    "recommended": False,
                    "strategy": "install_dep_then_switch",
                    "dep": "pipx",
                    "switch_to": "pipx",
                },
                {
                    "id": "use-apt",
                    "label": "Install via OS package manager",
                    "description": "Use the distro package (may be older version)",
                    "icon": "🐧",
                    "recommended": False,
                    "strategy": "switch_method",
                    "method": "apt",
                },
                {
                    "id": "break-system",
                    "label": "Override with --break-system-packages",
                    "description": (
                        "⚠️ DANGER: Forces pip install into the system Python. "
                        "This can break OS tools (apt, yum, etc.) that depend "
                        "on specific Python package versions. Only use in "
                        "throwaway containers."
                    ),
                    "icon": "💀",
                    "recommended": False,
                    "strategy": "retry_with_modifier",
                    "modifier": {"extra_args": ["--break-system-packages"]},
                    "risk": "critical",
                },
            ],
        },
        {
            "pattern": (
                r"ensurepip is not available|"
                r"No module named venv|"
                r"The virtual environment was not created successfully|"
                r"Error:.*ensurepip|"
                r"you need to install the python3-venv package"
            ),
            "failure_id": "pip_venv_not_available",
            "category": "dependency",
            "label": "python3-venv not installed",
            "description": (
                "The Python venv module is not available on this system. "
                "On Debian/Ubuntu, python3-venv must be installed separately. "
                "This is required before creating virtual environments."
            ),
            "example_stderr": (
                "Error: The virtual environment was not created successfully "
                "because ensurepip is not available. On Debian/Ubuntu systems, "
                "you need to install the python3-venv package."
            ),
            "options": [
                {
                    "id": "install-venv-package",
                    "label": "Install python3-venv and create environment",
                    "description": (
                        "Install the venv module from OS packages, then "
                        "create the virtual environment. This is the full "
                        "chain to get from zero to a working venv."
                    ),
                    "icon": "🐍",
                    "recommended": True,
                    "strategy": "install_packages",
                    "packages": {
                        "debian": ["python3-venv"],
                        "rhel": ["python3-virtualenv"],
                        "alpine": ["python3"],
                        "arch": ["python"],
                        "suse": ["python3-virtualenv"],
                        "macos": ["python3"],
                    },
                },
                {
                    "id": "use-uv-instead",
                    "label": "Use uv instead (no venv needed)",
                    "description": (
                        "uv bundles its own environment management and does "
                        "not depend on the system venv module."
                    ),
                    "icon": "⚡",
                    "recommended": False,
                    "strategy": "install_dep_then_switch",
                    "dep": "uv",
                    "switch_to": "uv",
                },
                {
                    "id": "use-virtualenv",
                    "label": "Use virtualenv instead",
                    "description": (
                        "virtualenv is a third-party alternative that works "
                        "even when python3-venv is not available."
                    ),
                    "icon": "📦",
                    "recommended": False,
                    "strategy": "env_fix",
                    "fix_commands": [
                        ["pip", "install", "--user", "virtualenv"],
                        ["python3", "-m", "virtualenv",
                         "${HOME}/.local/venvs/tools"],
                    ],
                },
            ],
        },
        {
            "pattern": (
                r"WARNING: Running pip as the 'root' user|"
                r"Running pip as the 'root' user can result in broken permissions|"
                r"WARNING: pip is being invoked by an old script wrapper"
            ),
            "failure_id": "pip_system_install_warning",
            "category": "environment",
            "label": "pip installed into system Python (dangerous)",
            "description": (
                "pip detected it is running at the system level (as root or "
                "into system site-packages). Even though the install may "
                "succeed, this can break OS packages and create version "
                "conflicts. Future operations should use an isolated "
                "Python environment."
            ),
            "example_stderr": (
                "WARNING: Running pip as the 'root' user can result in broken "
                "permissions and conflicting behaviour with the system "
                "package manager. It is recommended to use a virtual "
                "environment instead: https://pip.pypa.io/warnings/venv"
            ),
            "options": [
                {
                    "id": "use-venv",
                    "label": "Switch to virtual environment (venv)",
                    "description": (
                        "Create an isolated venv and reinstall there. "
                        "This prevents system Python contamination."
                    ),
                    "icon": "🐍",
                    "recommended": True,
                    "strategy": "env_fix",
                    "pre_packages": {
                        "debian": ["python3-venv"],
                        "rhel": ["python3-virtualenv"],
                        "suse": ["python3-virtualenv"],
                    },
                    "fix_commands": [
                        ["python3", "-m", "venv",
                         "${HOME}/.local/venvs/tools"],
                        ["${HOME}/.local/venvs/tools/bin/pip", "install",
                         "${TOOL_PACKAGE}"],
                    ],
                },
                {
                    "id": "use-uv",
                    "label": "Switch to uv (fast, modern)",
                    "description": (
                        "uv manages isolated Python environments automatically "
                        "and never pollutes the system Python."
                    ),
                    "icon": "⚡",
                    "recommended": False,
                    "strategy": "install_dep_then_switch",
                    "dep": "uv",
                    "switch_to": "uv",
                },
                {
                    "id": "use-conda",
                    "label": "Use conda environment",
                    "description": (
                        "If you already use conda/miniconda, install within "
                        "your conda environment instead of the system Python."
                    ),
                    "icon": "🐻",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Activate your conda environment first: "
                        "conda activate <env> && pip install <package>. "
                        "This ensures pip writes to the conda env, not system Python."
                    ),
                },
                {
                    "id": "acknowledge-risk",
                    "label": "Acknowledge and continue (containers only)",
                    "description": (
                        "If running in a disposable container where the system "
                        "Python does not matter, this warning can be ignored."
                    ),
                    "icon": "🐳",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "This warning is safe to ignore ONLY in throwaway "
                        "containers (Docker build steps, CI runners). "
                        "On persistent systems, always use a virtual environment."
                    ),
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
        {
            "pattern": r"Permission denied:.*site-packages|Could not install packages.*permission|"
                       r"PermissionError.*site-packages|pip.*denied.*install",
            "failure_id": "pip_permission_denied",
            "category": "permissions",
            "label": "pip permission denied",
            "description": (
                "pip cannot write to the system site-packages directory. "
                "You are trying to install into the system Python, which "
                "requires root privileges. The recommended approach is to "
                "install into an isolated environment instead."
            ),
            "example_stderr": (
                "ERROR: Could not install packages due to an OSError: "
                "[Errno 13] Permission denied: '/usr/lib/python3/dist-packages/pkg.dist-info'\n"
                "Consider using the `--user` option or check the permissions."
            ),
            "options": [
                {
                    "id": "use-venv",
                    "label": "Install in virtual environment (venv)",
                    "description": (
                        "Create an isolated venv and install there. "
                        "No root/sudo needed. This is the correct approach."
                    ),
                    "icon": "�",
                    "recommended": True,
                    "strategy": "env_fix",
                    "pre_packages": {
                        "debian": ["python3-venv"],
                        "rhel": ["python3-virtualenv"],
                        "suse": ["python3-virtualenv"],
                    },
                    "fix_commands": [
                        ["python3", "-m", "venv",
                         "${HOME}/.local/venvs/tools"],
                        ["${HOME}/.local/venvs/tools/bin/pip", "install",
                         "${TOOL_PACKAGE}"],
                    ],
                },
                {
                    "id": "use-uv",
                    "label": "Install via uv (fast, isolated)",
                    "description": (
                        "uv creates isolated environments automatically and "
                        "handles permissions without sudo."
                    ),
                    "icon": "⚡",
                    "recommended": False,
                    "strategy": "install_dep_then_switch",
                    "dep": "uv",
                    "switch_to": "uv",
                },
                {
                    "id": "use-user-flag",
                    "label": "Install with --user flag",
                    "description": (
                        "Installs to ~/.local (user site-packages). "
                        "No sudo needed, but packages are not isolated."
                    ),
                    "icon": "👤",
                    "recommended": False,
                    "strategy": "retry_with_modifier",
                    "modifier": {"extra_args": ["--user"]},
                },
                {
                    "id": "retry-sudo",
                    "label": "Retry with sudo (not recommended)",
                    "description": (
                        "Run pip install as root. This modifies the system "
                        "Python and can break OS tools. Use only in containers."
                    ),
                    "icon": "⚠️",
                    "recommended": False,
                    "strategy": "retry_with_modifier",
                    "modifier": {"sudo": True},
                    "risk": "high",
                },
            ],
        },
        {
            "pattern": r"requires.*but you.*have|"
                       r"ResolutionImpossible|"
                       r"conflicting dependencies|"
                       r"dependency conflict|"
                       r"which is incompatible",
            "failure_id": "pip_version_conflict",
            "category": "dependency",
            "label": "pip dependency version conflict",
            "description": (
                "pip cannot satisfy dependency constraints. One package requires "
                "a version of a dependency that conflicts with what's installed."
            ),
            "example_stderr": (
                "ERROR: pip's dependency resolver does not currently have all the features.\n"
                "ERROR: package-a 2.0 requires dependency-b>=3.0, "
                "but you have dependency-b 2.1 which is incompatible."
            ),
            "options": [
                {
                    "id": "force-reinstall",
                    "label": "Force reinstall all dependencies",
                    "description": "Reinstalls all packages to resolve version conflicts",
                    "icon": "🔄",
                    "recommended": True,
                    "strategy": "retry_with_modifier",
                    "modifier": {"extra_args": ["--force-reinstall"]},
                },
                {
                    "id": "use-venv",
                    "label": "Install in clean virtual environment",
                    "description": "Start fresh to avoid inherited conflicts",
                    "icon": "🐍",
                    "recommended": False,
                    "strategy": "env_fix",
                    "pre_packages": {
                        "debian": ["python3-venv"],
                        "rhel": ["python3-virtualenv"],
                        "suse": ["python3-virtualenv"],
                    },
                    "fix_commands": [
                        ["python3", "-m", "venv", "${HOME}/.local/venvs/tools"],
                    ],
                },
            ],
        },
        {
            "pattern": r"THESE PACKAGES DO NOT MATCH THE HASHES|"
                       r"HashMismatch|"
                       r"hash.*mismatch|"
                       r"Expected hash.*Got",
            "failure_id": "pip_hash_mismatch",
            "category": "network",
            "label": "pip hash mismatch",
            "description": (
                "Downloaded package hashes don't match expected values. "
                "This can indicate a corrupted download, cache issue, "
                "or man-in-the-middle attack."
            ),
            "example_stderr": (
                "ERROR: THESE PACKAGES DO NOT MATCH THE HASHES FROM THE "
                "REQUIREMENTS FILE.\n"
                "    package-a from https://files.pythonhosted.org/...\n"
                "        Expected sha256 abc123\n"
                "            Got        def456"
            ),
            "options": [
                {
                    "id": "clear-cache-retry",
                    "label": "Clear pip cache and retry",
                    "description": "Removes cached packages and downloads fresh",
                    "icon": "🗑️",
                    "recommended": True,
                    "strategy": "env_fix",
                    "fix_commands": [
                        ["pip", "cache", "purge"],
                    ],
                },
                {
                    "id": "no-cache-dir",
                    "label": "Retry with --no-cache-dir",
                    "description": "Skip cache entirely for this install",
                    "icon": "🔄",
                    "recommended": False,
                    "strategy": "retry_with_modifier",
                    "modifier": {"extra_args": ["--no-cache-dir"]},
                },
            ],
        },
        {
            "pattern": r"Failed building wheel for|"
                       r"error: command 'gcc' failed|"
                       r"error: subprocess-exited-with-error.*setup\.py|"
                       r"Could not build wheels for|"
                       r"building wheel.*failed",
            "failure_id": "pip_build_wheel_failed",
            "category": "compiler",
            "label": "pip failed to build wheel",
            "description": (
                "pip failed to compile a package with C/C++ extensions. "
                "This usually means build dependencies are missing."
            ),
            "example_stderr": (
                "Building wheels for collected packages: lxml\n"
                "  Building wheel for lxml (setup.py) ... error\n"
                "  error: command 'gcc' failed: No such file or directory\n"
                "  ERROR: Failed building wheel for lxml"
            ),
            "options": [
                {
                    "id": "install-build-deps",
                    "label": "Install build dependencies",
                    "description": "Install gcc, python3-dev, and common build tools",
                    "icon": "🔧",
                    "recommended": True,
                    "strategy": "install_packages",
                    "packages": {
                        "debian": ["build-essential", "python3-dev"],
                        "rhel": ["gcc", "python3-devel", "make"],
                        "alpine": ["build-base", "python3-dev"],
                        "arch": ["base-devel", "python"],
                        "suse": ["gcc", "python3-devel", "make"],
                        "macos": ["python3"],
                    },
                },
                {
                    "id": "prefer-binary",
                    "label": "Prefer pre-built binary wheel",
                    "description": "Skip source builds, use existing wheels if available",
                    "icon": "📦",
                    "recommended": False,
                    "strategy": "retry_with_modifier",
                    "modifier": {"extra_args": ["--prefer-binary"]},
                },
            ],
        },
        {
            "pattern": r"No matching distribution found for|"
                       r"Could not find a version that satisfies|"
                       r"No such package",
            "failure_id": "pip_no_matching_dist",
            "category": "dependency",
            "label": "pip package not found",
            "description": (
                "pip cannot find the requested package. The package name "
                "may be wrong, it may not exist on PyPI, or it may not "
                "support the current Python version or platform."
            ),
            "example_stderr": (
                "ERROR: No matching distribution found for nonexistent-package"
            ),
            "options": [
                {
                    "id": "check-name",
                    "label": "Verify package name on PyPI",
                    "description": "The package may have a different name on PyPI",
                    "icon": "🔍",
                    "recommended": True,
                    "strategy": "manual",
                    "instructions": (
                        "Check https://pypi.org/ for the correct package name. "
                        "Python package names are case-insensitive but may use "
                        "hyphens vs underscores (e.g. scikit-learn vs sklearn)."
                    ),
                },
                {
                    "id": "upgrade-pip",
                    "label": "Upgrade pip and retry",
                    "description": "Older pip may not find newer package formats",
                    "icon": "⬆️",
                    "recommended": False,
                    "strategy": "env_fix",
                    "fix_commands": [
                        ["pip", "install", "--upgrade", "pip"],
                    ],
                },
            ],
        },
        {
            "pattern": r"SSL: CERTIFICATE_VERIFY_FAILED|"
                       r"SSLCertVerificationError|"
                       r"ssl\.SSLCertVerificationError|"
                       r"Could not fetch URL.*CERTIFICATE_VERIFY|"
                       r"pip.*SSL.*certificate",
            "failure_id": "pip_ssl_error",
            "category": "network",
            "label": "pip SSL certificate error",
            "description": (
                "pip cannot verify PyPI's SSL certificate. Common in "
                "corporate environments with proxy-based TLS inspection."
            ),
            "example_stderr": (
                "WARNING: pip is configured with locations that require TLS/SSL, "
                "however the ssl module in Python is not available.\n"
                "Could not fetch URL https://pypi.org/simple/package/: "
                "There was a problem confirming the ssl certificate: "
                "SSLCertVerificationError - CERTIFICATE_VERIFY_FAILED"
            ),
            "options": [
                {
                    "id": "trusted-host",
                    "label": "Add PyPI as trusted host",
                    "description": "Skip cert verification for pypi.org (use with caution)",
                    "icon": "🔓",
                    "recommended": True,
                    "strategy": "retry_with_modifier",
                    "modifier": {
                        "extra_args": [
                            "--trusted-host", "pypi.org",
                            "--trusted-host", "files.pythonhosted.org",
                        ],
                    },
                    "risk": "medium",
                },
                {
                    "id": "set-cert",
                    "label": "Point pip to corporate CA bundle",
                    "description": "Configure pip to use your organization's CA certificate",
                    "icon": "🔐",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Set pip config: pip config set global.cert /path/to/ca-bundle.crt. "
                        "Or set environment variable: export PIP_CERT=/path/to/ca-bundle.crt. "
                        "Ask your IT department for the corporate CA certificate file."
                    ),
                },
            ],
        },
        {
            "pattern": r"requires Python\s*>=?\s*[\d.]+.*but.*current.*Python|"
                       r"python_requires.*not compatible|"
                       r"requires a different Python|"
                       r"This package requires Python",
            "failure_id": "pip_python_version",
            "category": "compatibility",
            "label": "Python version incompatible",
            "description": (
                "The package requires a newer Python version than what's "
                "installed on this system."
            ),
            "example_stderr": (
                "ERROR: Package 'modern-package' requires a different Python: "
                "3.8.10 not in '>=3.10'"
            ),
            "options": [
                {
                    "id": "install-older-version",
                    "label": "Install an older compatible version",
                    "description": "Find and install the last version that supports your Python",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "manual",
                    "instructions": (
                        "Run: pip install 'package<latest_version' to find compatible versions. "
                        "Check the package's PyPI page for Python version support matrix."
                    ),
                },
                {
                    "id": "upgrade-python",
                    "label": "Upgrade Python",
                    "description": "Install a newer Python version to meet requirements",
                    "icon": "🐍",
                    "recommended": False,
                    "strategy": "install_dep",
                    "dep": "python3",
                },
            ],
        },
    ],

    # ── pipx ────────────────────────────────────────────────────
    # Handlers for when `pipx install <tool>` is the install method.
    # pipx creates isolated venvs for each tool — the #1 failure is
    # python3-venv not being installed on Debian/Ubuntu systems.

    "pipx": [
        {
            "pattern": (
                r"No module named ['\"]?venv['\"]?|"
                r"python3-venv.*not installed|"
                r"FileNotFoundError.*venv|"
                r"venv.*required|"
                r"venv.*not found"
            ),
            "failure_id": "pipx_venv_missing",
            "category": "dependency",
            "label": "python3-venv not installed (required by pipx)",
            "description": (
                "pipx creates isolated virtual environments for each "
                "tool it installs. On Debian/Ubuntu, the 'venv' module "
                "is packaged separately as python3-venv. Without it, "
                "pipx cannot create environments and all installs fail."
            ),
            "example_stderr": (
                "Error: Python's venv module is required but not found. "
                "Please install python3-venv."
            ),
            "options": [
                {
                    "id": "install-python3-venv",
                    "label": "Install python3-venv",
                    "description": (
                        "Install the python3-venv package so pipx can "
                        "create isolated environments."
                    ),
                    "icon": "🐍",
                    "recommended": True,
                    "strategy": "install_packages",
                    "packages": {
                        "debian": ["python3-venv"],
                        "rhel": ["python3-libs"],
                        "alpine": ["python3"],
                        "arch": ["python"],
                        "suse": ["python3-base"],
                        "macos": ["python@3"],
                    },
                    "risk": "low",
                },
            ],
        },
        {
            "pattern": (
                r"pipx.*command not found|"
                r"pipx.*No such file or directory|"
                r"pipx: not found"
            ),
            "failure_id": "missing_pipx",
            "category": "dependency",
            "label": "pipx not installed",
            "description": (
                "The pipx tool is not installed on this system. "
                "pipx is needed to install Python CLI tools like "
                "poetry, black, and ruff in isolated environments."
            ),
            "example_stderr": (
                "bash: pipx: command not found"
            ),
            "options": [
                {
                    "id": "install-pipx",
                    "label": "Install pipx",
                    "description": (
                        "Install pipx using the system package manager "
                        "or pip, then retry."
                    ),
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_dep",
                    "dep": "pipx",
                    "risk": "low",
                },
                {
                    "id": "use-pip-instead",
                    "label": "Install with pip instead",
                    "description": (
                        "Skip pipx and use pip to install the tool. "
                        "Less isolation but works without pipx."
                    ),
                    "icon": "🔄",
                    "recommended": False,
                    "strategy": "switch_method",
                    "method": "pip",
                    "risk": "low",
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
                        "suse": ["gcc12", "gcc12-c++"],
                        "macos": ["gcc"],
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
                        "macos": ["gcc"],
                    },
                },
            ],
        },
        {
            "pattern": r"could not find.*pkg.config|"
                       r"pkg.config:.*not found|"
                       r"failed to run.*pkg.config",
            "failure_id": "missing_pkg_config",
            "category": "dependency",
            "label": "pkg-config not found",
            "description": (
                "This crate uses pkg-config to find system libraries, "
                "but pkg-config is not installed."
            ),
            "example_stderr": (
                "error: could not find system library 'openssl' "
                "required by the 'openssl-sys' crate\n"
                "--- stderr\n"
                "pkg-config: command not found"
            ),
            "options": [
                {
                    "id": "install-pkg-config",
                    "label": "Install pkg-config",
                    "description": "Install the pkg-config utility",
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_packages",
                    "packages": {
                        "debian": ["pkg-config"],
                        "rhel": ["pkgconf-pkg-config"],
                        "alpine": ["pkgconf"],
                        "arch": ["pkgconf"],
                        "suse": ["pkg-config"],
                        "macos": ["pkg-config"],
                    },
                },
            ],
        },
        {
            "pattern": r"Package (\S+) was not found in the pkg.config search path|"
                       r"No package '(\S+)' found",
            "failure_id": "missing_pkg_config_library",
            "category": "dependency",
            "label": "System library not found (pkg-config)",
            "description": (
                "A crate's build script uses pkg-config to find a system "
                "library, but the library's development package is not "
                "installed. Install the -dev/-devel package for the "
                "missing library."
            ),
            "example_stderr": (
                "Package openssl was not found in the pkg-config "
                "search path.\nPerhaps you should add the directory "
                "containing `openssl.pc' to the PKG_CONFIG_PATH "
                "environment variable"
            ),
            "options": [
                {
                    "id": "install-missing-dev-package",
                    "label": "Install missing development package",
                    "description": (
                        "Install the development package for the "
                        "library that pkg-config cannot find"
                    ),
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_packages",
                    "dynamic_packages": True,
                },
            ],
        },
    ],

    # ── go ───────────────────────────────────────────────────────
    # Handlers for when `go install` is used to install other tools.

    "go": [
        {
            "pattern": (
                r"requires go >= \d|"
                r"module requires Go \d|"
                r"go: go\.mod requires go >= \d|"
                r"cannot use go \d+\.\d+ with go\.mod"
            ),
            "failure_id": "go_version_mismatch",
            "category": "dependency",
            "label": "Go version too old for module",
            "description": (
                "The module requires a newer version of Go than what "
                "is installed. Distro-packaged Go versions often lag "
                "behind. Update Go or switch to the _default install "
                "method (go.dev binary)."
            ),
            "example_stderr": (
                "go: go.mod requires go >= 1.22 "
                "(running go 1.18.1)"
            ),
            "options": [
                {
                    "id": "update-go",
                    "label": "Update Go to latest",
                    "description": (
                        "Update Go via recipefor the current tool's "
                        "install method"
                    ),
                    "icon": "⬆️",
                    "recommended": True,
                    "strategy": "install_dep",
                    "dep": "go",
                },
                {
                    "id": "switch-go-default",
                    "label": "Install Go from go.dev",
                    "description": (
                        "Install the latest Go binary directly from "
                        "go.dev (bypasses distro packages)"
                    ),
                    "icon": "📦",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "curl -sSfL https://go.dev/dl/goX.Y.Z."
                        "linux-amd64.tar.gz -o /tmp/go.tar.gz && "
                        "sudo rm -rf /usr/local/go && "
                        "sudo tar -C /usr/local -xzf /tmp/go.tar.gz"
                    ),
                },
            ],
        },
        {
            "pattern": (
                r"cgo:.*C compiler.*not found|"
                r'exec:\s*"gcc":\s*executable file not found|'
                r"cc1:\s*error|"
                r"gcc:\s*not found"
            ),
            "failure_id": "go_cgo_missing_compiler",
            "category": "dependency",
            "label": "CGO requires C compiler",
            "description": (
                "This Go module uses CGO and requires a C compiler "
                "(gcc/cc) which is not installed. Install build tools."
            ),
            "example_stderr": (
                'cgo: C compiler "gcc" not found: '
                'exec: "gcc": executable file not found in $PATH'
            ),
            "options": [
                {
                    "id": "install-build-tools",
                    "label": "Install C compiler and build tools",
                    "description": (
                        "Install gcc and essential build tools"
                    ),
                    "icon": "🔧",
                    "recommended": True,
                    "strategy": "install_packages",
                    "packages": {
                        "debian": ["build-essential"],
                        "rhel": ["gcc", "gcc-c++", "make"],
                        "alpine": ["build-base"],
                        "arch": ["base-devel"],
                        "suse": ["gcc", "gcc-c++", "make"],
                        "macos": ["gcc", "make"],
                    },
                },
                {
                    "id": "disable-cgo",
                    "label": "Disable CGO",
                    "description": (
                        "Set CGO_ENABLED=0 to skip C compilation "
                        "(only works if the module supports pure Go)"
                    ),
                    "icon": "🔕",
                    "recommended": False,
                    "strategy": "retry_with_modifier",
                    "modifier": {
                        "env": {"CGO_ENABLED": "0"},
                    },
                },
            ],
        },
        {
            "pattern": (
                r"go: module.*not found|"
                r"404 Not Found.*go-get|"
                r"cannot find module providing package"
            ),
            "failure_id": "go_module_not_found",
            "category": "dependency",
            "label": "Go module not found",
            "description": (
                "The specified Go module path could not be resolved. "
                "This may be a typo, a private repository, or the "
                "module may have been removed."
            ),
            "example_stderr": (
                "go: module github.com/user/tool: "
                "reading https://proxy.golang.org/...: "
                "404 Not Found"
            ),
            "options": [
                {
                    "id": "check-module-path",
                    "label": "Verify module path",
                    "description": (
                        "Check the module path for typos and verify "
                        "the repository exists"
                    ),
                    "icon": "🔍",
                    "recommended": True,
                    "strategy": "manual",
                    "instructions": (
                        "1. Check the module path for typos\n"
                        "2. Verify the repository exists on GitHub/GitLab\n"
                        "3. If private, set GONOSUMCHECK and GOPRIVATE"
                    ),
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
                    "packages": {
                        "rhel": ["epel-release"],
                    },
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
                    "packages": "epel",
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

    # ── apk (Alpine) ────────────────────────────────────────────

    "apk": [
        {
            "pattern": (
                r"unsatisfiable constraints|"
                r"ERROR:.*unable to select packages|"
                r"ERROR:.*is not installable"
            ),
            "failure_id": "apk_unsatisfiable",
            "category": "package_manager",
            "label": "Package not found or dependency conflict",
            "description": (
                "The requested package cannot be found or has "
                "unsatisfiable dependencies. The package may not "
                "be in the configured repositories, or the community "
                "repository may need to be enabled."
            ),
            "example_stderr": (
                "ERROR: unsatisfiable constraints:\n"
                "  docker-compose (missing):\n"
                "    required by: world[docker-compose]"
            ),
            "options": [
                {
                    "id": "apk-update-retry",
                    "label": "Update package index and retry",
                    "description": (
                        "Run apk update to refresh the repository "
                        "index, then retry the install."
                    ),
                    "icon": "🔄",
                    "recommended": True,
                    "strategy": "cleanup_retry",
                    "cleanup_commands": [["apk", "update"]],
                },
                {
                    "id": "apk-enable-community",
                    "label": "Enable community repository",
                    "description": (
                        "Add the Alpine community repository. Many "
                        "packages are only in community, not main."
                    ),
                    "icon": "📦",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Edit /etc/apk/repositories and ensure the "
                        "community repo is uncommented:\n"
                        "  https://dl-cdn.alpinelinux.org/alpine/"
                        "v3.XX/community\n"
                        "Then run: apk update"
                    ),
                },
                {
                    "id": "switch-to-default",
                    "label": "Try alternative install method",
                    "description": (
                        "Use a direct download instead of apk."
                    ),
                    "icon": "🔧",
                    "recommended": False,
                    "strategy": "switch_method",
                    "method": "_default",
                },
            ],
        },
        {
            "pattern": (
                r"Unable to lock database|"
                r"unable to obtain lock|"
                r"Failed to lock"
            ),
            "failure_id": "apk_locked",
            "category": "package_manager",
            "label": "Package database locked",
            "description": (
                "Another apk process is using the database. "
                "Wait for it to finish or remove the stale lock."
            ),
            "example_stderr": (
                "ERROR: Unable to lock database: "
                "Resource temporarily unavailable"
            ),
            "options": [
                {
                    "id": "wait-retry",
                    "label": "Wait and retry",
                    "description": (
                        "Wait 30 seconds for the lock to release, "
                        "then retry."
                    ),
                    "icon": "⏳",
                    "recommended": True,
                    "strategy": "retry_with_modifier",
                    "modifier": {"wait_seconds": 30, "retry": True},
                },
                {
                    "id": "manual-unlock",
                    "label": "Remove stale lock",
                    "description": (
                        "Manually remove the lock file if no apk "
                        "process is running."
                    ),
                    "icon": "🔓",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Check for running apk processes:\n"
                        "  ps aux | grep apk\n"
                        "If none are running, remove the lock:\n"
                        "  rm -f /lib/apk/db/lock"
                    ),
                },
            ],
        },
    ],

    # ── pacman (Arch) ───────────────────────────────────────────

    "pacman": [
        {
            "pattern": (
                r"error: target not found|"
                r"error: could not find or read package"
            ),
            "failure_id": "pacman_target_not_found",
            "category": "package_manager",
            "label": "Package not found",
            "description": (
                "pacman cannot find the package. The package "
                "database may be stale, or the package may be "
                "in the AUR (not official repos)."
            ),
            "example_stderr": (
                "error: target not found: docker-compose"
            ),
            "options": [
                {
                    "id": "pacman-sync-retry",
                    "label": "Sync database and retry",
                    "description": (
                        "Run pacman -Syy to force-refresh the "
                        "package database, then retry."
                    ),
                    "icon": "🔄",
                    "recommended": True,
                    "strategy": "cleanup_retry",
                    "cleanup_commands": [
                        ["pacman", "-Syy", "--noconfirm"],
                    ],
                },
                {
                    "id": "switch-to-default",
                    "label": "Try alternative install method",
                    "description": (
                        "Use a direct download. The package may "
                        "only be in the AUR."
                    ),
                    "icon": "🔧",
                    "recommended": False,
                    "strategy": "switch_method",
                    "method": "_default",
                },
            ],
        },
        {
            "pattern": (
                r"unable to lock database|"
                r"failed to init transaction|"
                r"could not lock database"
            ),
            "failure_id": "pacman_locked",
            "category": "package_manager",
            "label": "Package database locked",
            "description": (
                "Another pacman process holds the database lock. "
                "Wait for it to finish or remove the stale lock "
                "file at /var/lib/pacman/db.lck."
            ),
            "example_stderr": (
                "error: failed to init transaction "
                "(unable to lock database)"
            ),
            "options": [
                {
                    "id": "wait-retry",
                    "label": "Wait and retry",
                    "description": (
                        "Wait 30 seconds for the lock to release, "
                        "then retry."
                    ),
                    "icon": "⏳",
                    "recommended": True,
                    "strategy": "retry_with_modifier",
                    "modifier": {"wait_seconds": 30, "retry": True},
                },
                {
                    "id": "manual-unlock",
                    "label": "Remove stale lock",
                    "description": (
                        "Remove the lock file if no pacman process "
                        "is running."
                    ),
                    "icon": "🔓",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Check for running pacman processes:\n"
                        "  ps aux | grep pacman\n"
                        "If none are running, remove the lock:\n"
                        "  sudo rm /var/lib/pacman/db.lck"
                    ),
                },
            ],
        },
    ],

    # ── zypper (openSUSE) ───────────────────────────────────────

    "zypper": [
        {
            "pattern": (
                r"No provider of|"
                r"not found in package names|"
                r"package .* not found"
            ),
            "failure_id": "zypper_not_found",
            "category": "package_manager",
            "label": "Package not found",
            "description": (
                "zypper cannot find the package in any enabled "
                "repository. The repository may need to be added "
                "or refreshed."
            ),
            "example_stderr": (
                "No provider of 'docker-compose' found."
            ),
            "options": [
                {
                    "id": "zypper-refresh-retry",
                    "label": "Refresh repositories and retry",
                    "description": (
                        "Run zypper refresh to update repository "
                        "metadata, then retry."
                    ),
                    "icon": "🔄",
                    "recommended": True,
                    "strategy": "cleanup_retry",
                    "cleanup_commands": [["zypper", "refresh"]],
                },
                {
                    "id": "switch-to-default",
                    "label": "Try alternative install method",
                    "description": (
                        "Use a direct download instead of zypper."
                    ),
                    "icon": "🔧",
                    "recommended": False,
                    "strategy": "switch_method",
                    "method": "_default",
                },
            ],
        },
        {
            "pattern": (
                r"System management is locked|"
                r"another zypper process|"
                r"zypp is locked"
            ),
            "failure_id": "zypper_locked",
            "category": "package_manager",
            "label": "Package manager locked",
            "description": (
                "Another zypper or PackageKit process is using "
                "the system package database. Wait for it to "
                "finish."
            ),
            "example_stderr": (
                "System management is locked by the application "
                "with pid 1234 (zypper)."
            ),
            "options": [
                {
                    "id": "wait-retry",
                    "label": "Wait and retry",
                    "description": (
                        "Wait 30 seconds for the lock to release, "
                        "then retry."
                    ),
                    "icon": "⏳",
                    "recommended": True,
                    "strategy": "retry_with_modifier",
                    "modifier": {"wait_seconds": 30, "retry": True},
                },
                {
                    "id": "manual-unlock",
                    "label": "Check and remove lock",
                    "description": (
                        "Identify the process holding the lock and "
                        "wait or kill it."
                    ),
                    "icon": "🔓",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Check what process holds the zypp lock:\n"
                        "  sudo zypper ps\n"
                        "Or remove the PID file if no zypper process "
                        "is running:\n"
                        "  sudo rm /run/zypp.pid"
                    ),
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
                    "requires_binary": "wget",
                },
                {
                    "id": "use-python3-urllib",
                    "label": "Use python3 urllib instead",
                    "description": (
                        "Download using Python's built-in urllib "
                        "(independent of libcurl)"
                    ),
                    "icon": "🐍",
                    "recommended": False,
                    "strategy": "retry_with_modifier",
                    "modifier": {"substitute_curl_with_python3": True},
                    "requires_binary": "python3",
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
        {
            "pattern": r"npm:\s*command not found|npm:\s*not found",
            "failure_id": "missing_npm_default",
            "category": "dependency",
            "label": "npm not installed",
            "description": "npm is required to install this package.",
            "example_stderr": "bash: npm: command not found",
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

    # ── gem (Ruby gem installs) ───────────────────────────────────
    # Applies to tools installed via `gem install <name>`, used by
    # bundler, rubocop, and other ruby-category tools.

    "gem": [
        # ── Gem::FilePermissionError ────────────────────────────
        # Common when `gem install` tries to write to the system
        # gem directory (/usr/lib/ruby/gems/) without sudo.
        # Happens on systems where Ruby was installed via PM and
        # the default gem path is a root-owned directory.
        {
            "pattern": (
                r"Gem::FilePermissionError|"
                r"You don't have write permissions for the .*/gems/|"
                r"ERROR:.*permission denied.*gems"
            ),
            "failure_id": "gem_permission_error",
            "category": "permissions",
            "label": "No write permission to gem directory",
            "description": (
                "gem install is trying to write to the system gem "
                "directory which requires root permissions. You can "
                "either install to a user-local directory or use "
                "sudo."
            ),
            "example_stderr": (
                "ERROR:  While executing gem ... "
                "(Gem::FilePermissionError)\n"
                "    You don't have write permissions for the "
                "/usr/lib/ruby/gems/3.0.0 directory."
            ),
            "options": [
                {
                    "id": "gem-user-install",
                    "label": "Install to user gem directory",
                    "description": (
                        "Set GEM_HOME to ~/.gem and re-run the "
                        "install. This avoids needing root."
                    ),
                    "icon": "👤",
                    "recommended": True,
                    "strategy": "retry_with_modifier",
                    "modifier": {
                        "env": {
                            "GEM_HOME": "$HOME/.gem",
                        },
                        "prepend_path": "$HOME/.gem/bin",
                    },
                },
                {
                    "id": "gem-sudo-install",
                    "label": "Install with sudo",
                    "description": (
                        "Run gem install with sudo to write to "
                        "the system gem directory"
                    ),
                    "icon": "🔒",
                    "recommended": False,
                    "strategy": "retry_with_modifier",
                    "modifier": {"sudo": True},
                },
            ],
        },
        # ── Native extension build failure ──────────────────────
        # Some gems need C compilation. If ruby-dev / ruby-devel
        # headers are missing, mkmf.rb fails.
        # Note: bundler itself is pure Ruby and won't hit this,
        # but other gems installed via `gem install` will.
        #
        # Platform considerations:
        #   macOS: system Ruby (deprecated since Catalina) has no
        #     headers. Fix = brew ruby (includes everything) OR
        #     Xcode CLT for the SDK headers + clang compiler.
        #   Raspbian (ARM64): same debian packages work, but
        #     native extensions may compile slower on Pi.
        #     build-essential provides ARM-native gcc.
        {
            "pattern": (
                r"mkmf\.rb can't find header files|"
                r"extconf\.rb failed|"
                r"ERROR: Failed to build gem native extension|"
                r"You have to install development tools first"
            ),
            "failure_id": "gem_native_extension_failed",
            "category": "dependency",
            "label": "Gem native extension build failed",
            "description": (
                "This gem includes a C extension that requires "
                "Ruby development headers (ruby.h) and a C compiler "
                "to build. On Linux, install the ruby-dev package. "
                "On macOS, install Xcode Command Line Tools or use "
                "Homebrew Ruby (which includes headers)."
            ),
            "example_stderr": (
                "Building native extensions. This could take a while...\n"
                "ERROR: Error installing nokogiri:\n"
                "    ERROR: Failed to build gem native extension.\n"
                "    mkmf.rb can't find header files for ruby"
            ),
            "options": [
                {
                    "id": "install-ruby-dev",
                    "label": "Install Ruby development headers",
                    "description": (
                        "Install the ruby-dev / ruby-devel package "
                        "for your system. On macOS, this installs "
                        "Homebrew Ruby which includes headers."
                    ),
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_packages",
                    "packages": {
                        # debian covers: Ubuntu, Debian, Raspbian
                        "debian": ["ruby-dev"],
                        "rhel": ["ruby-devel"],
                        "alpine": ["ruby-dev"],
                        "arch": ["ruby"],
                        "suse": ["ruby-devel"],
                        # brew install ruby includes headers + compiler
                        # shim; covers the common macOS case where
                        # system Ruby has no headers post-Catalina
                        "macos": ["ruby"],
                    },
                },
                {
                    "id": "install-build-tools",
                    "label": "Install C compiler and build tools",
                    "description": (
                        "Install gcc/make for native extension "
                        "compilation. On Debian/Raspbian this "
                        "installs build-essential (ARM-native "
                        "on Pi). On macOS, prefer Xcode CLT."
                    ),
                    "icon": "🔧",
                    "recommended": False,
                    "strategy": "install_packages",
                    "packages": {
                        # build-essential works on both x86_64 and
                        # arm64 (Raspbian) — installs ARM-native gcc
                        "debian": ["build-essential"],
                        "rhel": ["gcc", "gcc-c++", "make"],
                        "alpine": ["build-base"],
                        "arch": ["base-devel"],
                        "suse": ["gcc", "gcc-c++", "make"],
                        # brew install gcc gives real GCC (not clang);
                        # for most gems, Xcode CLT clang is enough —
                        # see the manual option below
                        "macos": ["gcc"],
                    },
                },
                {
                    # macOS-specific: Xcode Command Line Tools gives
                    # clang (as cc/gcc), make, headers, and the SDK.
                    # This is the standard macOS way to get build tools.
                    "id": "install-xcode-clt",
                    "label": "Install Xcode Command Line Tools (macOS)",
                    "description": (
                        "On macOS, run 'xcode-select --install' to "
                        "get clang, make, and macOS SDK headers. "
                        "This is the standard way to enable native "
                        "extension compilation on macOS."
                    ),
                    "icon": "🍎",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Run the following command in Terminal:\n"
                        "  xcode-select --install\n\n"
                        "A dialog will appear to download and install "
                        "the Command Line Tools. After installation, "
                        "retry the gem install."
                    ),
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
            "pattern": (
                r"cc:\s*(command )?not found|"
                r"g\+\+:\s*(command )?not found|"
                r"gcc:\s*(command )?not found|"
                r"make:\s*(command )?not found"
            ),
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
                    "packages": "build_tools",
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
        {
            "pattern": r"configure:\s*error:",
            "failure_id": "configure_error",
            "category": "dependency",
            "label": "configure script failed",
            "description": (
                "The autotools configure script failed, usually because "
                "a required library or tool is missing."
            ),
            "example_stderr": (
                "configure: error: OpenSSL libs and/or directories "
                "were not found"
            ),
            "options": [
                {
                    "id": "install-dev-libs",
                    "label": "Install development libraries",
                    "description": (
                        "Install the -dev/-devel packages for "
                        "the missing library"
                    ),
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_packages",
                    "dynamic_packages": True,
                },
                {
                    "id": "check-config-log",
                    "label": "Check config.log",
                    "description": (
                        "Read the config.log file for the exact "
                        "reason configure failed"
                    ),
                    "icon": "🔍",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Examine the configure log for details:\n"
                        "  cat config.log | grep -A5 'error:'"
                    ),
                },
            ],
        },
        {
            "pattern": r"ld:\s*cannot find\s*-l|cannot find -l",
            "failure_id": "linker_error",
            "category": "dependency",
            "label": "Linker cannot find library",
            "description": (
                "The linker cannot find a required shared library. "
                "The development package for this library is likely "
                "not installed."
            ),
            "example_stderr": "ld: cannot find -lssl",
            "options": [
                {
                    "id": "install-lib-dev",
                    "label": "Install library development package",
                    "description": (
                        "Install the -dev/-devel package for "
                        "the missing library"
                    ),
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "install_packages",
                    "dynamic_packages": True,
                },
            ],
        },
    ],

    # ── composer_global (install-pattern family) ────────────────
    # Used via install_via: {"_default": "composer_global"}
    # Applies to ALL tools installed with `composer global require`.
    # NOT the same as "composer" the tool — this is tools installed
    # BY composer, not composer itself.

    "composer_global": [
            # ── Composer memory exhaustion ───────────────────────
            # `composer global require` loads the full dependency
            # graph into memory. PHP's default memory_limit (128MB)
            # is often insufficient. Common on Raspberry Pi and
            # other low-RAM devices.
            {
                "pattern": (
                    r"Allowed memory size of \d+ bytes exhausted|"
                    r"PHP Fatal error:.*memory size.*exhausted|"
                    r"mmap\(\) failed:.*Cannot allocate memory|"
                    r"proc_open\(\):.*Cannot allocate memory"
                ),
                "failure_id": "composer_global_memory_limit",
                "category": "resources",
                "label": "Composer ran out of memory during install",
                "description": (
                    "The composer global require command ran out of "
                    "memory. PHP's default memory_limit (128MB) is "
                    "often insufficient for dependency resolution. "
                    "This is especially common on Raspberry Pi and "
                    "other low-RAM devices."
                ),
                "example_stderr": (
                    "PHP Fatal error:  Allowed memory size of "
                    "134217728 bytes exhausted (tried to allocate "
                    "4096 bytes) in phar:///usr/local/bin/composer/"
                    "src/Composer/DependencyResolver/Solver.php "
                    "on line 223"
                ),
                "options": [
                    {
                        "id": "retry-unlimited-memory",
                        "label": "Retry with unlimited memory",
                        "description": (
                            "Re-run composer global require with "
                            "COMPOSER_MEMORY_LIMIT=-1 to remove "
                            "the PHP memory cap"
                        ),
                        "icon": "🔧",
                        "recommended": True,
                        "strategy": "retry_with_modifier",
                        "modifier": {
                            "env": {
                                "COMPOSER_MEMORY_LIMIT": "-1",
                            },
                        },
                    },
                    {
                        "id": "install-via-brew-mem",
                        "label": "Install via brew instead",
                        "description": (
                            "Brew formulae are pre-compiled — no "
                            "Composer dependency resolution needed, "
                            "so no memory pressure."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                    },
                ],
            },
            # ── PHP version too old for the package ──────────────
            # Composer dependency resolution fails when system PHP
            # doesn't meet the package's version requirement.
            # Generic pattern — matches any package/phpversion combo.
            {
                "pattern": (
                    r"requires php \^[\d.]+ .* your PHP version|"
                    r"requires php .* does not satisfy|"
                    r"your PHP version \([\d.]+\) does not satisfy"
                ),
                "failure_id": "composer_global_php_version",
                "category": "environment",
                "label": "PHP version too old for the package",
                "description": (
                    "The package being installed requires a newer "
                    "PHP version than what your system has. Upgrade "
                    "PHP or use brew (brew bundles its own PHP)."
                ),
                "example_stderr": (
                    "phpstan/phpstan 2.1.0 requires php ^7.4 || ^8.0"
                    " -> your PHP version (7.2.33) does not satisfy "
                    "that requirement."
                ),
                "options": [
                    {
                        "id": "upgrade-php",
                        "label": "Upgrade PHP",
                        "description": (
                            "Install a newer PHP version (8.x) "
                            "using your system package manager"
                        ),
                        "icon": "⬆️",
                        "recommended": True,
                        "strategy": "install_dep",
                        "dep": "php",
                    },
                    {
                        "id": "install-via-brew-ver",
                        "label": "Install via brew instead",
                        "description": (
                            "Brew formulae bundle a compatible PHP "
                            "version — no system PHP dependency."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                    },
                ],
            },
    ],

    # ── curl_pipe_bash (install-pattern family) ─────────────────
    # Used via install_via: {"_default": "curl_pipe_bash"}
    # Applies to ALL tools installed with `curl ... | sh` or
    # `curl ... | bash`. NOT curl itself — this is tools installed
    # BY curl piping into a shell script.
    #
    # 43 tools use this pattern. Shared failure modes are distinct
    # from INFRA (which catches generic network) and _default
    # (which catches missing binaries like curl/git).

    "curl_pipe_bash": [
            # ── TLS / certificate error ──────────────────────────
            # Minimal Docker images (alpine, distroless, scratch)
            # often lack CA certificates. curl can reach the host
            # but rejects the TLS cert. This is NOT a network
            # failure — DNS and TCP work fine.
            {
                "pattern": (
                    r"curl:\s*\(60\).*SSL certificate problem|"
                    r"curl:\s*\(60\).*certificate.*not trusted|"
                    r"curl:\s*\(77\).*error setting certificate|"
                    r"curl:\s*\(35\).*SSL connect error|"
                    r"ssl_client:.*SSL connection error|"
                    r"unable to get local issuer certificate"
                ),
                "failure_id": "curl_tls_certificate",
                "category": "environment",
                "label": "TLS certificate verification failed",
                "description": (
                    "curl could not verify the server's TLS "
                    "certificate. This usually means the system "
                    "is missing CA certificates — common on "
                    "minimal Docker images (Alpine, slim). "
                    "Install the ca-certificates package."
                ),
                "example_stderr": (
                    "curl: (60) SSL certificate problem: "
                    "unable to get local issuer certificate"
                ),
                "options": [
                    {
                        "id": "install-ca-certs",
                        "label": "Install CA certificates",
                        "description": (
                            "Install the system CA certificate "
                            "bundle so curl can verify TLS"
                        ),
                        "icon": "🔒",
                        "recommended": True,
                        "strategy": "install_packages",
                        "packages": {
                            "debian": ["ca-certificates"],
                            "rhel": ["ca-certificates"],
                            "alpine": ["ca-certificates"],
                            "arch": ["ca-certificates"],
                            "suse": ["ca-certificates"],
                            "macos": ["ca-certificates"],
                        },
                    },
                    {
                        "id": "curl-insecure",
                        "label": "Retry with --insecure (unsafe)",
                        "description": (
                            "Skip TLS verification. NOT recommended"
                            " — only use in isolated/test "
                            "environments where you trust the "
                            "network."
                        ),
                        "icon": "⚠️",
                        "recommended": False,
                        "risk": "high",
                        "strategy": "manual",
                        "instructions": (
                            "Re-run the command with curl -k or "
                            "curl --insecure. This skips TLS "
                            "certificate verification."
                        ),
                    },
                ],
            },
            # ── Unsupported architecture ─────────────────────────
            # Many install scripts detect the system architecture
            # (uname -m / uname -s) and fail if it's not x86_64
            # or aarch64. Common on arm7l (32-bit ARM), s390x,
            # ppc64le, riscv64.
            {
                "pattern": (
                    r"unsupported (?:os|arch|platform|system)|"
                    r"architecture .* (?:not supported|unsupported)|"
                    r"no (?:binary|release|download) (?:available |found )?for|"
                    r"(?:os|platform|arch).*not (?:recognized|supported)|"
                    r"does not support .* architecture|"
                    r"No prebuilt binary"
                ),
                "failure_id": "curl_unsupported_arch",
                "category": "environment",
                "label": "Unsupported OS or architecture",
                "description": (
                    "The install script does not have a binary "
                    "for your OS/architecture combination. This "
                    "is common on ARM 32-bit, s390x, ppc64le, "
                    "and RISC-V. You may need to build from "
                    "source or use a different install method."
                ),
                "example_stderr": (
                    "Error: unsupported arch: armv7l. "
                    "Only x86_64 and aarch64 are supported."
                ),
                "options": [
                    {
                        "id": "switch-to-source",
                        "label": "Build from source",
                        "description": (
                            "Some tools offer source builds for "
                            "unsupported architectures. Check the "
                            "tool's documentation for instructions."
                        ),
                        "icon": "🔨",
                        "recommended": True,
                        "strategy": "manual",
                        "instructions": (
                            "Check the tool's GitHub/documentation "
                            "for source build instructions for "
                            "your architecture."
                        ),
                    },
                    {
                        "id": "switch-to-brew-arch",
                        "label": "Try brew instead",
                        "description": (
                            "Homebrew builds from source on "
                            "unsupported architectures."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                    },
                ],
            },
            # ── Script URL gone (404/410) ────────────────────────
            # Projects move domains, change URLs, or deprecate
            # install scripts. curl returns the HTTP error page
            # content which the shell tries to execute.
            {
                "pattern": (
                    r"curl:\s*\(22\).*(?:404|410|403)|"
                    r"The requested URL returned error: (?:404|410|403)|"
                    r"curl:\s*\(22\).*not found|"
                    r"sh:.*syntax error.*unexpected|"
                    r"bash:.*syntax error near unexpected token|"
                    r"<!DOCTYPE html>|<html"
                ),
                "failure_id": "curl_script_not_found",
                "category": "environment",
                "label": "Install script URL not found or returned HTML",
                "description": (
                    "The install script URL returned a 404/403 "
                    "error or an HTML page instead of a shell "
                    "script. The project may have moved to a new "
                    "URL, or the install script format may have "
                    "changed. Check the project's documentation "
                    "for the current install method."
                ),
                "example_stderr": (
                    "curl: (22) The requested URL returned error: "
                    "404 Not Found"
                ),
                "options": [
                    {
                        "id": "check-docs",
                        "label": "Check project documentation",
                        "description": (
                            "The install script URL may have "
                            "changed. Check the project's website "
                            "or GitHub for the current install "
                            "instructions."
                        ),
                        "icon": "📖",
                        "recommended": True,
                        "strategy": "manual",
                        "instructions": (
                            "Visit the project's official website "
                            "or GitHub page to find the current "
                            "installation instructions."
                        ),
                    },
                    {
                        "id": "switch-to-brew-404",
                        "label": "Install via brew instead",
                        "description": (
                            "Homebrew formulae don't depend on "
                            "third-party install scripts."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                    },
                ],
            },
    ],

    # ── github_release (install-pattern family) ─────────────────
    # Used via install_via: {"_default": "github_release"}
    # Applies to tools installed by downloading a pre-built binary
    # from GitHub releases (e.g.  github.com/.../releases/latest/
    # download/tool-linux-amd64.tar.gz).
    #
    # 31 tools use this pattern. Distinct from curl_pipe_bash
    # (no shell script — direct binary download + optional extract).
    # Distinct from INFRA (GitHub is reachable — issue is with the
    # specific release/asset, not connectivity).

    "github_release": [
            # ── GitHub API rate limit ────────────────────────────
            # Many install commands first query the GitHub API to
            # resolve "latest" → concrete version. Unauthenticated
            # requests are limited to 60/hour. CI/CD pipelines and
            # containers burn through this quickly.
            {
                "pattern": (
                    r"API rate limit exceeded|"
                    r"403.*rate limit|"
                    r"rate limit.*exceeded|"
                    r"429 Too Many Requests|"
                    r"secondary rate limit|"
                    r"You have exceeded.*rate limit"
                ),
                "failure_id": "github_rate_limit",
                "category": "environment",
                "label": "GitHub API rate limit exceeded",
                "description": (
                    "The install command hit GitHub's API rate "
                    "limit. Unauthenticated requests are limited "
                    "to 60/hour per IP. This is common in CI/CD "
                    "pipelines and Docker builds. Solutions: set "
                    "a GITHUB_TOKEN, wait, or use a different "
                    "install method."
                ),
                "example_stderr": (
                    "Error: API rate limit exceeded for "
                    "203.0.113.1. (But here's the good news: "
                    "Authenticated requests get a higher rate "
                    "limit.)"
                ),
                "options": [
                    {
                        "id": "set-gh-token",
                        "label": "Set GITHUB_TOKEN for higher rate limit",
                        "description": (
                            "Authenticated requests get 5,000/hour "
                            "instead of 60/hour. Set a personal "
                            "access token."
                        ),
                        "icon": "🔑",
                        "recommended": True,
                        "strategy": "manual",
                        "instructions": (
                            "1. Create a token at github.com/"
                            "settings/tokens (no scopes needed "
                            "for public repos)\n"
                            "2. Export GITHUB_TOKEN=ghp_xxx\n"
                            "3. Re-run the install command"
                        ),
                    },
                    {
                        "id": "switch-to-brew-rate",
                        "label": "Install via brew instead",
                        "description": (
                            "Homebrew has its own caching and "
                            "doesn't hit GitHub API rate limits."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                    },
                ],
            },
            # ── Release asset not found ──────────────────────────
            # The GitHub release exists, but there's no binary for
            # this OS/arch combination. Different from
            # curl_unsupported_arch — here the install script
            # doesn't detect arch; the download URL itself 404s.
            {
                "pattern": (
                    r"No assets? (?:found|matching|available)|"
                    r"release.*not found|"
                    r"no (?:matching|suitable) release|"
                    r"could not find.*release.*for|"
                    r"unable to determine download URL|"
                    r"asset.*not found.*for.*(?:linux|darwin|amd64|arm)"
                ),
                "failure_id": "github_asset_not_found",
                "category": "environment",
                "label": "No release asset for this platform",
                "description": (
                    "The GitHub release exists but does not "
                    "include a binary for your OS/architecture "
                    "combination. The project may not support "
                    "your platform, or the asset naming may have "
                    "changed between versions."
                ),
                "example_stderr": (
                    "Error: no assets found matching "
                    "linux/armv7l in release v2.1.0"
                ),
                "options": [
                    {
                        "id": "build-from-source-gh",
                        "label": "Build from source",
                        "description": (
                            "Clone the repository and build the "
                            "binary for your architecture."
                        ),
                        "icon": "🔨",
                        "recommended": True,
                        "strategy": "manual",
                        "instructions": (
                            "Check the project's README for build "
                            "instructions. Most Go/Rust projects "
                            "support cross-compilation."
                        ),
                    },
                    {
                        "id": "switch-to-brew-asset",
                        "label": "Try brew instead",
                        "description": (
                            "Homebrew builds from source when no "
                            "bottle exists for your architecture."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                    },
                ],
            },
            # ── Archive extraction failure ───────────────────────
            # The download succeeded but the archive can't be
            # extracted. Common causes: partial download, wrong
            # format (HTML error page saved as .tar.gz), or
            # missing extraction tools.
            {
                "pattern": (
                    r"tar:.*Error.*not in gzip format|"
                    r"tar:.*Exiting with failure|"
                    r"gzip:.*not in gzip format|"
                    r"unzip:.*End-of-central-directory|"
                    r"zip:.*bad zipfile|"
                    r"cannot open:.*No such file or directory|"
                    r"unexpected end of file|"
                    r"short read|"
                    r"data integrity error"
                ),
                "failure_id": "github_extract_failed",
                "category": "environment",
                "label": "Archive extraction failed",
                "description": (
                    "The downloaded archive could not be "
                    "extracted. This usually means the download "
                    "was incomplete (network interruption) or the "
                    "server returned an error page (HTML) instead "
                    "of the actual binary archive."
                ),
                "example_stderr": (
                    "gzip: stdin: not in gzip format\n"
                    "tar: Child returned status 1\n"
                    "tar: Error is not recoverable: "
                    "exiting now"
                ),
                "options": [
                    {
                        "id": "retry-download",
                        "label": "Retry the download",
                        "description": (
                            "The archive may have been partially "
                            "downloaded. Retry the install."
                        ),
                        "icon": "🔄",
                        "recommended": True,
                        "strategy": "retry",
                    },
                    {
                        "id": "switch-to-brew-extract",
                        "label": "Install via brew instead",
                        "description": (
                            "Homebrew handles downloads and "
                            "extraction automatically."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
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
            r"Failed to connect|"
            r"ENOTFOUND|ERR_SOCKET_TIMEOUT|ENETUNREACH"
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
            r"certificate verify failed|CERTIFICATE_VERIFY_FAILED|"
            r"Connection refused|Connection reset|ECONNREFUSED"
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

    # ── Read-only filesystem ──

    {
        "pattern": (
            r"Read-only file system|"
            r"EROFS|"
            r"ERROR:.*Read-only"
        ),
        "failure_id": "read_only_rootfs",
        "category": "environment",
        "label": "Read-only filesystem",
        "description": (
            "Cannot write to the filesystem — likely a Kubernetes "
            "pod or container with a read-only root filesystem. "
            "Package managers cannot install to system paths."
        ),
        "example_stderr": "ERROR: Read-only file system",
        "options": [
            {
                "id": "use-writable-mount",
                "label": "Install to writable mount point",
                "description": (
                    "If a writable volume (emptyDir, PVC) is mounted, "
                    "install tools there and update PATH"
                ),
                "icon": "📁",
                "recommended": True,
                "strategy": "manual",
                "instructions": (
                    "Kubernetes read-only rootfs detected.\n"
                    "Options:\n"
                    "  1. Add an emptyDir volume mount for tools:\n"
                    "     volumes: [{name: tools, emptyDir: {}}]\n"
                    "     volumeMounts: [{name: tools, mountPath: /opt/tools}]\n"
                    "  2. Download pre-built binary to the writable path:\n"
                    "     export PATH=/opt/tools/bin:$PATH\n"
                    "  3. Or bake the tool into the container image."
                ),
            },
            {
                "id": "bake-into-image",
                "label": "Bake tool into container image",
                "description": (
                    "Add the tool to the Dockerfile so it's available "
                    "in the read-only filesystem at build time"
                ),
                "icon": "🐳",
                "recommended": False,
                "strategy": "manual",
                "instructions": (
                    "Add to your Dockerfile:\n"
                    "  RUN apt-get update && apt-get install -y <tool>\n"
                    "Then rebuild and redeploy the image."
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
        "pattern": (
            r"timed out|Timed out|ETIMEDOUT|"
            r"timeout expired|killed by signal 15"
        ),
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
        "macos": "curl",
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
