"""
L0 Data — Go tool-specific failure handlers.

Tools: go
Pure data, no logic.
"""

from __future__ import annotations


_GO_HANDLERS: list[dict] = [
            # ── GOPATH/GOBIN permission denied ──────────────────
            # Common when GOPATH dirs have wrong ownership (e.g.
            # after using sudo go install or mixed-user installs).
            {
                "pattern": (
                    r"permission denied.*go(?:path|/bin)|"
                    r"GOPATH.*permission denied|"
                    r"cannot create.*go/bin.*permission denied"
                ),
                "failure_id": "go_gopath_permission",
                "category": "permissions",
                "label": "GOPATH/GOBIN permission denied",
                "description": (
                    "Go cannot write to the GOPATH or GOBIN directory. "
                    "This often happens when directories under ~/go "
                    "were created by root (e.g. via 'sudo go install'). "
                    "Fix ownership of the Go workspace."
                ),
                "example_stderr": (
                    "go: could not create module cache: "
                    "mkdir /home/user/go: permission denied"
                ),
                "options": [
                    {
                        "id": "fix-gopath-ownership",
                        "label": "Fix GOPATH ownership",
                        "description": (
                            "Change ownership of ~/go and its contents "
                            "to the current user"
                        ),
                        "icon": "🔧",
                        "recommended": True,
                        "strategy": "env_fix",
                        "fix_commands": [
                            ["bash", "-c",
                             'sudo chown -R "$USER:$USER" '
                             '"${GOPATH:-$HOME/go}"'],
                        ],
                    },
                ],
            },
            # ── go not in PATH after _default install ───────────
            # /usr/local/go/bin is not in PATH by default on most
            # systems. After _default install, verify may fail.
            {
                "pattern": (
                    r"go:\s*command not found|"
                    r"go:\s*not found"
                ),
                "failure_id": "go_path_not_set",
                "category": "environment",
                "label": "Go not found in PATH",
                "description": (
                    "Go was installed but /usr/local/go/bin is not in "
                    "your PATH. Add it to your shell profile."
                ),
                "example_stderr": (
                    "bash: go: command not found"
                ),
                "options": [
                    {
                        "id": "add-go-to-path",
                        "label": "Add Go to PATH",
                        "description": (
                            "Add /usr/local/go/bin to your PATH in "
                            "~/.profile or ~/.bashrc"
                        ),
                        "icon": "🔧",
                        "recommended": True,
                        "strategy": "env_fix",
                        "fix_commands": [
                            ["bash", "-c",
                             "echo 'export PATH=$PATH:/usr/local/go/bin' "
                             ">> ~/.profile && "
                             "export PATH=$PATH:/usr/local/go/bin"],
                        ],
                    },
                ],
            },
            # ── noexec /tmp blocks go build ─────────────────────
            # On hardened systems /tmp is mounted noexec. Go compiles
            # to a temp dir and tries to execute from it, failing
            # with "permission denied" on /tmp/go-build*.
            {
                "pattern": (
                    r"permission denied.*/tmp/go-build|"
                    r"operation not permitted.*/tmp/go-build|"
                    r"fork/exec /tmp/go-build.*permission denied"
                ),
                "failure_id": "go_noexec_tmp",
                "category": "environment",
                "label": "/tmp is noexec — Go cannot compile",
                "description": (
                    "Go compiles to a temporary directory and tries "
                    "to execute binaries from it. On systems where "
                    "/tmp is mounted with 'noexec', this fails. "
                    "Set GOTMPDIR to an executable directory."
                ),
                "example_stderr": (
                    "fork/exec /tmp/go-build1234567890/b001/exe/main: "
                    "permission denied"
                ),
                "options": [
                    {
                        "id": "set-gotmpdir",
                        "label": "Set GOTMPDIR to an executable directory",
                        "description": (
                            "Create ~/go_tmp and set GOTMPDIR so Go "
                            "uses it instead of /tmp"
                        ),
                        "icon": "🔧",
                        "recommended": True,
                        "strategy": "env_fix",
                        "fix_commands": [
                            ["bash", "-c",
                             "mkdir -p ~/go_tmp && "
                             "echo 'export GOTMPDIR=$HOME/go_tmp' "
                             ">> ~/.profile && "
                             "export GOTMPDIR=$HOME/go_tmp"],
                        ],
                    },
                ],
            },
]
