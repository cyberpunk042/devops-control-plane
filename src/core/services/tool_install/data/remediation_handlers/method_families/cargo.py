"""
L0 Data — cargo method-family remediation handlers.

Pure data, no logic.
"""

from __future__ import annotations


_CARGO_HANDLERS: list[dict] = [
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
]
