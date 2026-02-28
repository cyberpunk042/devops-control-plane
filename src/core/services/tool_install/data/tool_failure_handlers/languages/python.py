"""
L0 Data — Python ecosystem tool-specific failure handlers.

Tools: python, poetry, uv
Pure data, no logic.
"""

from __future__ import annotations


_PYTHON_HANDLERS: list[dict] = [
            # ── python3 command not found ─────────────────────────
            # Some minimal images (Alpine Docker, tiny VMs) don't have
            # python3. Also catches python2/3 confusion.
            {
                "pattern": (
                    r"python3:\s*command not found|"
                    r"python3:\s*not found|"
                    r"No such file or directory.*python3|"
                    r"/usr/bin/python3:\s*No such file"
                ),
                "failure_id": "python_not_found",
                "category": "dependency",
                "label": "Python 3 not installed",
                "description": (
                    "The python3 binary is not found. On most Linux "
                    "distributions python3 is pre-installed, but minimal "
                    "container images and some cloud VMs do not include it."
                ),
                "example_stderr": (
                    "bash: python3: command not found"
                ),
                "options": [
                    {
                        "id": "install-python3",
                        "label": "Install Python 3",
                        "description": (
                            "Install python3 using your system package "
                            "manager."
                        ),
                        "icon": "🐍",
                        "recommended": True,
                        "strategy": "install_dep",
                        "dep": "python",
                    },
                    {
                        "id": "python-is-python3",
                        "label": "Symlink python → python3 (Ubuntu)",
                        "description": (
                            "If python3 IS installed but 'python' is not, "
                            "install the python-is-python3 package to "
                            "create the symlink."
                        ),
                        "icon": "🔗",
                        "recommended": False,
                        "strategy": "install_packages",
                        "packages": {
                            "debian": ["python-is-python3"],
                        },
                    },
                ],
            },
            # ── ssl module not available ──────────────────────────
            # After building Python from source without libssl-dev,
            # import ssl fails. Affects pip, requests, urllib3, etc.
            {
                "pattern": (
                    r"No module named ['\"]?_ssl['\"]?|"
                    r"ssl module in Python is not available|"
                    r"pip is configured with locations that require TLS/SSL|"
                    r"WARNING: pip is configured with locations that require TLS"
                ),
                "failure_id": "python_ssl_module_missing",
                "category": "dependency",
                "label": "Python SSL module not available",
                "description": (
                    "Python was compiled without SSL support. This usually "
                    "means libssl-dev (or equivalent) was not installed "
                    "when Python was built from source. pip and any "
                    "HTTPS-dependent code will not work. You need to "
                    "install the SSL development headers and rebuild "
                    "Python."
                ),
                "example_stderr": (
                    "WARNING: pip is configured with locations that require "
                    "TLS/SSL, however the ssl module in Python is not available."
                ),
                "options": [
                    {
                        "id": "install-libssl-rebuild",
                        "label": "Install SSL headers and rebuild",
                        "description": (
                            "Install the OpenSSL development library for "
                            "your distro, then rebuild Python from source."
                        ),
                        "icon": "🔧",
                        "recommended": True,
                        "strategy": "install_packages",
                        "packages": {
                            "debian": ["libssl-dev"],
                            "rhel": ["openssl-devel"],
                            "alpine": ["openssl-dev"],
                            "arch": ["openssl"],
                            "suse": ["libopenssl-devel"],
                        },
                    },
                    {
                        "id": "use-system-python",
                        "label": "Use system Python instead",
                        "description": (
                            "Switch to the distribution-provided Python "
                            "which includes SSL support."
                        ),
                        "icon": "💡",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "1. Remove the custom Python build\n"
                            "2. Install python3 from your package manager\n"
                            "3. The system package includes SSL support"
                        ),
                    },
                ],
            },
            # ── tkinter not available ─────────────────────────────
            # tkinter requires Tcl/Tk dev libraries at Python build time.
            # Common error for GUI-dependent scripts / matplotlib backends.
            {
                "pattern": (
                    r"No module named ['\"]?_tkinter['\"]?|"
                    r"No module named ['\"]?tkinter['\"]?|"
                    r"ImportError:.*_tkinter"
                ),
                "failure_id": "python_tkinter_missing",
                "category": "dependency",
                "label": "Python tkinter module not available",
                "description": (
                    "The tkinter module is not available. On Debian/Ubuntu, "
                    "tkinter is packaged separately from python3. On "
                    "source-built Python, the Tcl/Tk development libraries "
                    "must be installed before building."
                ),
                "example_stderr": (
                    "ModuleNotFoundError: No module named '_tkinter'"
                ),
                "options": [
                    {
                        "id": "install-tkinter-pkg",
                        "label": "Install tkinter package",
                        "description": (
                            "Install the tkinter package from your "
                            "system package manager."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "install_packages",
                        "packages": {
                            "debian": ["python3-tk"],
                            "rhel": ["python3-tkinter"],
                            "alpine": ["py3-tkinter"],
                            "arch": ["tk"],
                            "suse": ["python3-tk"],
                        },
                    },
                ],
            },
            # ── libpython shared library missing ──────────────────
            # After building Python from source without --enable-shared,
            # or when venv base Python is removed/upgraded. The dynamic
            # linker cannot find libpython3.X.so.
            {
                "pattern": (
                    r"error while loading shared libraries:.*libpython|"
                    r"libpython3\.\d+\.so.*No such file|"
                    r"cannot open shared object file.*libpython"
                ),
                "failure_id": "python_libpython_missing",
                "category": "environment",
                "label": "libpython shared library not found",
                "description": (
                    "The system cannot find the libpython shared library. "
                    "This happens when Python was built from source without "
                    "--enable-shared, or when the base Python for a virtual "
                    "environment was removed or upgraded. Programs that "
                    "embed Python (e.g. GDB, some C extensions) need this."
                ),
                "example_stderr": (
                    "error while loading shared libraries: "
                    "libpython3.12.so.1.0: cannot open shared object file: "
                    "No such file or directory"
                ),
                "options": [
                    {
                        "id": "install-python-dev",
                        "label": "Install Python development package",
                        "description": (
                            "Install the python3-dev package which includes "
                            "the shared library and headers."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "install_packages",
                        "packages": {
                            "debian": ["libpython3-dev"],
                            "rhel": ["python3-devel"],
                            "alpine": ["python3-dev"],
                            "arch": ["python"],
                            "suse": ["python3-devel"],
                        },
                    },
                    {
                        "id": "run-ldconfig",
                        "label": "Update library cache (ldconfig)",
                        "description": (
                            "If the library exists but the linker can't "
                            "find it, run ldconfig to refresh the cache. "
                            "Common after source installs to /usr/local/lib."
                        ),
                        "icon": "🔧",
                        "recommended": False,
                        "strategy": "env_fix",
                        "fix_commands": [
                            ["sudo", "ldconfig"],
                        ],
                    },
                ],
            },
            # ── zlib not available ────────────────────────────────
            # During source build or pip install, zlib module is missing.
            # Affects package decompression.
            {
                "pattern": (
                    r"can't decompress data;?\s*zlib not available|"
                    r"No module named ['\"]?zlib['\"]?|"
                    r"ImportError:.*zlib|"
                    r"zipimport\.ZipImportError:.*zlib"
                ),
                "failure_id": "python_zlib_missing",
                "category": "dependency",
                "label": "Python zlib module not available",
                "description": (
                    "The zlib compression module is not available. This "
                    "usually means zlib development headers were not "
                    "installed when Python was built from source. pip "
                    "cannot decompress downloaded packages without zlib."
                ),
                "example_stderr": (
                    "zipimport.ZipImportError: can't decompress data; "
                    "zlib not available"
                ),
                "options": [
                    {
                        "id": "install-zlib-dev",
                        "label": "Install zlib development headers",
                        "description": (
                            "Install the zlib development package, then "
                            "rebuild Python from source."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "install_packages",
                        "packages": {
                            "debian": ["zlib1g-dev"],
                            "rhel": ["zlib-devel"],
                            "alpine": ["zlib-dev"],
                            "arch": ["zlib"],
                            "suse": ["zlib-devel"],
                        },
                    },
                ],
            },
            # ── Python version too old ────────────────────────────
            # System Python works but is too old for modern tools.
            # openSUSE 15 ships 3.6, RHEL 9 ships 3.9, older Ubuntu
            # ships 3.8. Many tools now require >= 3.10.
            {
                "pattern": (
                    r"requires a different Python|"
                    r"requires Python\s*[><=!]+\s*3\.\d+|"
                    r"Requires-Python|"
                    r"python_requires.*not compatible|"
                    r"Python 3\.\d+ is not supported|"
                    r"This version of.*requires Python 3\.\d+|"
                    r"SyntaxError.*:=.*invalid syntax|"
                    r"SyntaxError.*match.*case"
                ),
                "failure_id": "python_version_too_old",
                "category": "environment",
                "label": "Python version too old",
                "description": (
                    "The installed Python version is too old for this "
                    "tool or package. Many modern tools require Python "
                    "3.10 or later, but some systems ship older versions "
                    "(e.g. openSUSE 15 has 3.6, RHEL 9 has 3.9). You "
                    "need to install a newer Python alongside the system "
                    "one — do NOT replace the system Python."
                ),
                "example_stderr": (
                    "ERROR: Package 'ruff' requires a different Python: "
                    "3.9.18 not in '>=3.10'"
                ),
                "options": [
                    {
                        "id": "install-newer-python-pm",
                        "label": "Install newer Python from repos",
                        "description": (
                            "Install a newer Python version from your "
                            "distribution's repositories or a trusted "
                            "PPA/AppStream. On Ubuntu use deadsnakes PPA "
                            "(ppa:deadsnakes/ppa), on RHEL/Rocky use "
                            "AppStream (dnf install python3.11)."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "manual",
                        "instructions": (
                            "Ubuntu/Debian:\n"
                            "  sudo add-apt-repository ppa:deadsnakes/ppa\n"
                            "  sudo apt-get update\n"
                            "  sudo apt-get install python3.12 "
                            "python3.12-venv\n\n"
                            "RHEL 9 / Rocky 9 / AlmaLinux 9:\n"
                            "  sudo dnf install python3.11\n\n"
                            "Fedora (already has latest):\n"
                            "  sudo dnf install python3\n\n"
                            "After install, use python3.12 (or 3.11) "
                            "directly — do NOT replace system python3."
                        ),
                    },
                    {
                        "id": "build-newer-python",
                        "label": "Build newer Python from source",
                        "description": (
                            "Build a newer Python version from source "
                            "using make altinstall. This installs as "
                            "python3.X without touching the system Python."
                        ),
                        "icon": "🔧",
                        "recommended": False,
                        "strategy": "install_dep",
                        "dep": "python",
                    },
                ],
            },
            # ── macOS Xcode CLT Python missing ────────────────────
            # On macOS, python3 is provided by Xcode Command Line
            # Tools. If CLT is not installed, running python3
            # triggers a GUI popup or errors out. This is macOS-
            # specific and has no equivalent on Linux.
            {
                "pattern": (
                    r"xcode-select:.*install|"
                    r"xcrun:.*error.*active developer|"
                    r"CommandLineTools.*not found|"
                    r"xcode-select --install"
                ),
                "failure_id": "python_macos_xcode_clt_missing",
                "category": "environment",
                "label": "macOS Xcode Command Line Tools not installed",
                "description": (
                    "On macOS, python3 is provided by the Xcode Command "
                    "Line Tools. If CLT is not installed, python3 is "
                    "not available. You can install CLT or use Homebrew "
                    "to install a standalone Python."
                ),
                "example_stderr": (
                    "xcode-select: note: No developer tools were found, "
                    "requesting install."
                ),
                "options": [
                    {
                        "id": "install-xcode-clt",
                        "label": "Install Xcode Command Line Tools",
                        "description": (
                            "Run xcode-select --install to install the "
                            "Xcode Command Line Tools, which include "
                            "Python 3, git, make, and other essentials."
                        ),
                        "icon": "🍎",
                        "recommended": True,
                        "strategy": "env_fix",
                        "fix_commands": [
                            ["xcode-select", "--install"],
                        ],
                    },
                    {
                        "id": "brew-install-python",
                        "label": "Install Python via Homebrew",
                        "description": (
                            "Install a standalone Python via Homebrew "
                            "which is independent of Xcode CLT. This "
                            "is often preferred for development."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "install_dep",
                        "dep": "python",
                    },
                ],
            },
]


_POETRY_HANDLERS: list[dict] = [
            # ── python3 not found during installer ────────────────
            # The official installer pipes to `python3 -`. On minimal
            # Docker images, WSL, or headless servers, python3 may not
            # be on PATH (or may not be installed at all). The error
            # is typically "python3: command not found" or
            # "No such file or directory: python3".
            {
                "pattern": (
                    r"python3.*command not found|"
                    r"python3.*No such file or directory|"
                    r"python3.*not found|"
                    r"/usr/bin/env.*python3.*No such file"
                ),
                "failure_id": "poetry_python3_not_found",
                "category": "dependency",
                "label": "python3 not found (required by Poetry installer)",
                "description": (
                    "The Poetry official installer requires python3 to "
                    "run. The system does not have python3 on PATH. "
                    "Install Python 3 first, or use an install method "
                    "that doesn't pipe to python3."
                ),
                "example_stderr": (
                    "bash: python3: command not found"
                ),
                "options": [
                    {
                        "id": "install-python3",
                        "label": "Install Python 3 and retry",
                        "description": (
                            "Install Python 3 using the system package "
                            "manager, then retry the Poetry installer."
                        ),
                        "icon": "🐍",
                        "recommended": True,
                        "strategy": "install_packages",
                        "packages": {
                            "debian": ["python3"],
                            "rhel": ["python3"],
                            "alpine": ["python3"],
                            "arch": ["python"],
                            "suse": ["python3"],
                            "macos": ["python@3"],
                        },
                        "risk": "low",
                    },
                    {
                        "id": "use-brew",
                        "label": "Install via Homebrew",
                        "description": (
                            "Use Homebrew to install poetry. Homebrew "
                            "handles the Python dependency automatically."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                        "risk": "low",
                    },
                ],
            },
]


_UV_HANDLERS: list[dict] = [
            # ── GLIBC version too old ─────────────────────────────
            # uv is a compiled Rust binary. The standalone installer
            # downloads a pre-built binary that links against glibc.
            # On old Linux distros (CentOS 7 ships glibc 2.17, old
            # Debian/Ubuntu), the binary can't run because it needs
            # a newer glibc (typically 2.28+). Produces the error:
            # "version `GLIBC_2.28' not found"
            {
                "pattern": (
                    r"GLIBC_\d+\.\d+.*not found|"
                    r"version.*GLIBC.*not found|"
                    r"libc\.so\.6.*GLIBC.*not found"
                ),
                "failure_id": "uv_glibc_too_old",
                "category": "compatibility",
                "label": "GLIBC too old for uv binary",
                "description": (
                    "The uv binary requires a newer version of the "
                    "GNU C Library (glibc) than what is available on "
                    "this system. This typically happens on CentOS 7, "
                    "old Debian, or other legacy Linux distros. "
                    "Upgrading glibc system-wide is dangerous — use "
                    "pip/pipx instead (they bundle their own binary) "
                    "or upgrade the operating system."
                ),
                "example_stderr": (
                    "/lib/x86_64-linux-gnu/libc.so.6: version "
                    "`GLIBC_2.28' not found (required by ./uv)"
                ),
                "options": [
                    {
                        "id": "use-pip",
                        "label": "Install via pip (bundles binary)",
                        "description": (
                            "pip install uv downloads a Python wrapper "
                            "that includes the uv binary. This method "
                            "bundles its own dependencies and avoids "
                            "the glibc version issue on most systems."
                        ),
                        "icon": "🐍",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "pip",
                        "risk": "low",
                    },
                    {
                        "id": "use-pipx",
                        "label": "Install via pipx (isolated)",
                        "description": (
                            "pipx install uv installs the Python "
                            "wrapper in an isolated environment."
                        ),
                        "icon": "📦",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "pipx",
                        "risk": "low",
                    },
                    {
                        "id": "build-from-source",
                        "label": "Build from source with cargo",
                        "description": (
                            "Use cargo install --locked uv to compile "
                            "uv from source. This avoids the pre-built "
                            "binary glibc requirement but requires the "
                            "Rust toolchain and is slow (10+ minutes)."
                        ),
                        "icon": "🔧",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "cargo",
                        "risk": "medium",
                    },
                ],
            },
]
