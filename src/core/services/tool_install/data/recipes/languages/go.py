"""
L0 Data — Go ecosystem tools.

Categories: go
Pure data, no logic.
"""

from __future__ import annotations


_GO_RECIPES: dict[str, dict] = {

    "gopls": {
        "cli": "gopls",
        "label": "gopls (Go language server — official)",
        "category": "go",
        # Official Go language server by the Go team.
        # go install only. NOT in any PM except go.
        "install": {
            "_default": ["go", "install", "golang.org/x/tools/gopls@latest"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "go"},
        "requires": {"binaries": ["go"]},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && gopls version'],
        "update": {"_default": ["go", "install",
                                "golang.org/x/tools/gopls@latest"]},
    },
    "golangci-lint": {
        "cli": "golangci-lint",
        "label": "golangci-lint (Go linters aggregator)",
        "category": "go",
        # Aggregates 100+ Go linters into one CLI.
        # Official installer script or brew. Also available via go install
        # but official docs recommend the script for reproducibility.
        "install": {
            "brew": ["brew", "install", "golangci-lint"],
            "_default": [
                "bash", "-c",
                "curl -sSfL https://raw.githubusercontent.com/golangci/"
                "golangci-lint/HEAD/install.sh | sh -s -- -b "
                "$(go env GOPATH)/bin",
            ],
        },
        "needs_sudo": {"_default": False, "brew": False},
        "install_via": {"_default": "curl_pipe_bash"},
        "requires": {"binaries": ["go", "curl"]},
        "prefer": ["brew"],
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && golangci-lint --version'],
        "update": {
            "brew": ["brew", "upgrade", "golangci-lint"],
            "_default": [
                "bash", "-c",
                "curl -sSfL https://raw.githubusercontent.com/golangci/"
                "golangci-lint/HEAD/install.sh | sh -s -- -b "
                "$(go env GOPATH)/bin",
            ],
        },
    },
    "delve": {
        "cli": "dlv",
        "label": "Delve (Go debugger — dlv)",
        "category": "go",
        # Go debugger. Binary name is dlv, not delve.
        # go install only.
        "install": {
            "_default": ["go", "install",
                         "github.com/go-delve/delve/cmd/dlv@latest"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "go"},
        "requires": {"binaries": ["go"]},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && dlv version'],
        "update": {"_default": ["go", "install",
                                "github.com/go-delve/delve/cmd/dlv@latest"]},
    },
    "air": {
        "cli": "air",
        "label": "Air (Go live reload for development)",
        "category": "go",
        # Live reload for Go apps during development.
        # go install only.
        "install": {
            "_default": ["go", "install",
                         "github.com/air-verse/air@latest"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "go"},
        "requires": {"binaries": ["go"]},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && air -v'],
        "update": {"_default": ["go", "install",
                                "github.com/air-verse/air@latest"]},
    },
    "mockgen": {
        "cli": "mockgen",
        "label": "mockgen (Go mock generator — uber/mock)",
        "category": "go",
        # Generates mock implementations for Go interfaces.
        # go install only. From uber/mock (successor to golang/mock).
        "install": {
            "_default": ["go", "install",
                         "go.uber.org/mock/mockgen@latest"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "go"},
        "requires": {"binaries": ["go"]},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && mockgen --version'],
        "update": {"_default": ["go", "install",
                                "go.uber.org/mock/mockgen@latest"]},
    },
    "protoc-gen-go": {
        "cli": "protoc-gen-go",
        "label": "protoc-gen-go (Go protobuf code generator)",
        "category": "go",
        # Generates Go code from .proto files.
        # go install only. Requires protoc (protobuf compiler) at runtime.
        "install": {
            "_default": ["go", "install",
                         "google.golang.org/protobuf/cmd/protoc-gen-go@latest"],
        },
        "needs_sudo": {"_default": False},
        "install_via": {"_default": "go"},
        "requires": {"binaries": ["go"]},
        "post_env": 'export PATH="$HOME/go/bin:$PATH"',
        "verify": ["bash", "-c",
                   'export PATH="$HOME/go/bin:$PATH" && protoc-gen-go --version'],
        "update": {"_default": ["go", "install",
                                "google.golang.org/protobuf/cmd/protoc-gen-go@latest"]},
    },
}
