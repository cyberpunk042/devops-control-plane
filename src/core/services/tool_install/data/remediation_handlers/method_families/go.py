"""
L0 Data — go method-family remediation handlers.

Pure data, no logic.
"""

from __future__ import annotations


_GO_HANDLERS: list[dict] = [
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
]
