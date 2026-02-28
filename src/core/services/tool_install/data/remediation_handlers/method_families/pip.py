"""
L0 Data — pip method-family remediation handlers.

Pure data, no logic.
"""

from __future__ import annotations


_PIP_HANDLERS: list[dict] = [
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
]
