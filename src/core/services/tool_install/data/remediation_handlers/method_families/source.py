"""
L0 Data — source method-family remediation handlers.

Pure data, no logic.
"""

from __future__ import annotations


_SOURCE_HANDLERS: list[dict] = [
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
]
