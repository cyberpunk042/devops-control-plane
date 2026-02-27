"""
Layer 3 remediation handlers — tool-specific failures.

These are keyed by tool_id and apply ONLY to that specific tool.
They are the highest-priority layer in the handler cascade:

    Layer 3 (here)  →  tool-specific failures
    Layer 2         →  METHOD_FAMILY_HANDLERS (per install method)
    Layer 1         →  INFRA_HANDLERS (cross-tool infrastructure)
    Layer 0         →  BOOTSTRAP_HANDLERS (system-level bootstrap)

Previously these lived in TOOL_RECIPES[tool_id]["on_failure"].
Extracted to keep recipes focused on install logic (SRP).
"""


TOOL_FAILURE_HANDLERS: dict[str, list[dict]] = {

    # ── cargo ──────────────────────────────────────────────────

    "cargo": [
            # ── Raspbian: 64-bit kernel + 32-bit userland ───────
            # uname -m says aarch64 so rustup installs 64-bit binaries,
            # but the userland is armhf — binaries can't execute.
            # Error appears AFTER install when verify runs cargo.
            {
                "pattern": (
                    r"exec format error|"
                    r"cannot execute binary file|"
                    r"command failed.*cargo.*No such file or directory"
                ),
                "failure_id": "rustup_arch_mismatch",
                "category": "environment",
                "label": "Architecture mismatch (32-bit userland on 64-bit kernel)",
                "description": (
                    "Your system has a 64-bit kernel but a 32-bit userland "
                    "(common on Raspberry Pi). rustup detected aarch64 and "
                    "installed 64-bit binaries that cannot run. You need to "
                    "either reinstall with the correct 32-bit target or "
                    "upgrade to a 64-bit OS."
                ),
                "example_stderr": (
                    "bash: /home/pi/.cargo/bin/cargo: "
                    "cannot execute binary file: Exec format error"
                ),
                "options": [
                    {
                        "id": "reinstall-armv7",
                        "label": "Reinstall Rust for 32-bit ARM",
                        "description": (
                            "Uninstall the wrong toolchain and reinstall "
                            "with the armv7 target that matches your "
                            "32-bit userland"
                        ),
                        "icon": "🔧",
                        "recommended": True,
                        "strategy": "env_fix",
                        "fix_commands": [
                            ["bash", "-c",
                             'export PATH="$HOME/.cargo/bin:$PATH" && '
                             "rustup self uninstall -y"],
                            ["bash", "-c",
                             "curl --proto '=https' --tlsv1.2 -sSf "
                             "https://sh.rustup.rs | sh -s -- -y "
                             "--default-toolchain "
                             "stable-armv7-unknown-linux-gnueabihf"],
                        ],
                    },
                    {
                        "id": "upgrade-64bit-os",
                        "label": "Upgrade to 64-bit OS",
                        "description": (
                            "Install a 64-bit Raspberry Pi OS to match "
                            "the 64-bit kernel, then retry the default "
                            "rustup installation"
                        ),
                        "icon": "💡",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "1. Download 64-bit Raspberry Pi OS from "
                            "raspberrypi.com\n"
                            "2. Flash to SD card and boot\n"
                            "3. Retry cargo installation"
                        ),
                    },
                ],
            },
            # ── Low memory: rustup hangs/crashes during unpack ──
            # Raspberry Pi with limited RAM can OOM during toolchain
            # unpacking, especially when extracting rust-docs.
            {
                "pattern": (
                    r"(?i)\bKilled\b|SIGKILL|signal:\s*9|"
                    r"out of memory"
                ),
                "exit_code": 137,
                "failure_id": "rustup_low_memory",
                "category": "resources",
                "label": "Rustup ran out of memory during installation",
                "description": (
                    "rustup was killed due to insufficient memory. This "
                    "is common on Raspberry Pi and other low-RAM devices "
                    "during the toolchain unpacking phase."
                ),
                "example_stderr": (
                    "info: installing component 'rust-docs'\n"
                    "Killed"
                ),
                "example_exit_code": 137,
                "options": [
                    {
                        "id": "minimal-profile",
                        "label": "Install with minimal profile",
                        "description": (
                            "Skip rust-docs and other heavy components "
                            "by using the minimal profile, which only "
                            "includes rustc, cargo, and rust-std"
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "env_fix",
                        "fix_commands": [
                            ["bash", "-c",
                             "curl --proto '=https' --tlsv1.2 -sSf "
                             "https://sh.rustup.rs | sh -s -- -y "
                             "--profile minimal"],
                        ],
                    },
                    {
                        "id": "limit-unpack-ram",
                        "label": "Limit unpack memory usage",
                        "description": (
                            "Set RUSTUP_UNPACK_RAM to limit memory used "
                            "during component extraction"
                        ),
                        "icon": "🔧",
                        "recommended": False,
                        "strategy": "retry_with_modifier",
                        "modifier": {
                            "env": {"RUSTUP_UNPACK_RAM": "100000000"},
                        },
                    },
                ],
            },
    ],

    # ── rustup ─────────────────────────────────────────────────
    # Same underlying failures as cargo (both use sh.rustup.rs),
    # but applied when the user installs rustup directly.

    "rustup": [
        # ── Raspbian: 64-bit kernel + 32-bit userland ───────
        # Same as cargo's rustup_arch_mismatch but triggered during
        # rustup --version verify.
        {
            "pattern": (
                r"exec format error|"
                r"cannot execute binary file|"
                r"command failed.*rustup.*No such file or directory"
            ),
            "failure_id": "rustup_arch_mismatch",
            "category": "environment",
            "label": "Architecture mismatch (32-bit userland on 64-bit kernel)",
            "description": (
                "Your system has a 64-bit kernel but a 32-bit userland "
                "(common on Raspberry Pi). The installer detected aarch64 "
                "and installed 64-bit binaries that cannot run. You need "
                "to either reinstall with the correct 32-bit target or "
                "upgrade to a 64-bit OS."
            ),
            "example_stderr": (
                "bash: /home/pi/.cargo/bin/rustup: "
                "cannot execute binary file: Exec format error"
            ),
            "options": [
                {
                    "id": "reinstall-armv7",
                    "label": "Reinstall Rust for 32-bit ARM",
                    "description": (
                        "Uninstall the wrong toolchain and reinstall "
                        "with the armv7 target that matches your "
                        "32-bit userland"
                    ),
                    "icon": "🔧",
                    "recommended": True,
                    "strategy": "env_fix",
                    "fix_commands": [
                        ["bash", "-c",
                         'export PATH="$HOME/.cargo/bin:$PATH" && '
                         "rustup self uninstall -y"],
                        ["bash", "-c",
                         "curl --proto '=https' --tlsv1.2 -sSf "
                         "https://sh.rustup.rs | sh -s -- -y "
                         "--default-toolchain "
                         "stable-armv7-unknown-linux-gnueabihf"],
                    ],
                },
                {
                    "id": "upgrade-64bit-os",
                    "label": "Upgrade to 64-bit OS",
                    "description": (
                        "Install a 64-bit Raspberry Pi OS to match "
                        "the 64-bit kernel, then retry the default "
                        "rustup installation"
                    ),
                    "icon": "💡",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "1. Download 64-bit Raspberry Pi OS from "
                        "raspberrypi.com\n"
                        "2. Flash to SD card and boot\n"
                        "3. Retry rustup installation"
                    ),
                },
            ],
        },
        # ── Low memory during toolchain unpack ─────────────────
        # Same as cargo — OOM during component extraction.
        {
            "pattern": (
                r"(?i)\bKilled\b|SIGKILL|signal:\s*9|"
                r"out of memory"
            ),
            "exit_code": 137,
            "failure_id": "rustup_low_memory",
            "category": "resources",
            "label": "Rustup ran out of memory during installation",
            "description": (
                "rustup was killed due to insufficient memory. This "
                "is common on Raspberry Pi and other low-RAM devices "
                "during the toolchain unpacking phase."
            ),
            "example_stderr": (
                "info: installing component 'rust-docs'\n"
                "Killed"
            ),
            "example_exit_code": 137,
            "options": [
                {
                    "id": "minimal-profile",
                    "label": "Install with minimal profile",
                    "description": (
                        "Skip rust-docs and other heavy components "
                        "by using the minimal profile, which only "
                        "includes rustc, cargo, and rust-std"
                    ),
                    "icon": "📦",
                    "recommended": True,
                    "strategy": "env_fix",
                    "fix_commands": [
                        ["bash", "-c",
                         "curl --proto '=https' --tlsv1.2 -sSf "
                         "https://sh.rustup.rs | sh -s -- -y "
                         "--profile minimal"],
                    ],
                },
                {
                    "id": "limit-unpack-ram",
                    "label": "Limit unpack memory usage",
                    "description": (
                        "Set RUSTUP_UNPACK_RAM to limit memory used "
                        "during component extraction"
                    ),
                    "icon": "🔧",
                    "recommended": False,
                    "strategy": "retry_with_modifier",
                    "modifier": {
                        "env": {"RUSTUP_UNPACK_RAM": "100000000"},
                    },
                },
            ],
        },
    ],

    # ── go ─────────────────────────────────────────────────────

    "go": [
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
    ],

    # ── docker ─────────────────────────────────────────────────

    "docker": [
            # ── Docker daemon not running ──────────────────────────
            {
                "pattern": (
                    r"Cannot connect to the Docker daemon|"
                    r"Is the docker daemon running\?|"
                    r"docker\.sock:.*connect:.*connection refused|"
                    r"Cannot connect to the Docker daemon at unix:///var/run/docker\.sock"
                ),
                "failure_id": "docker_daemon_not_running",
                "category": "environment",
                "label": "Docker daemon not running",
                "description": (
                    "The Docker daemon (dockerd) is not running. Docker CLI "
                    "commands require the daemon to be active. This is common "
                    "after installation (daemon not auto-started) or after a "
                    "system reboot without Docker enabled at boot."
                ),
                "example_stderr": (
                    "Cannot connect to the Docker daemon at "
                    "unix:///var/run/docker.sock. Is the docker daemon running?"
                ),
                "options": [
                    {
                        "id": "start-docker-systemd",
                        "label": "Start Docker daemon (systemd)",
                        "description": (
                            "Start the Docker daemon using systemctl. "
                            "Also enables it to start on boot."
                        ),
                        "icon": "🔄",
                        "recommended": True,
                        "requires": {"has_systemd": True},
                        "strategy": "env_fix",
                        "fix_commands": [
                            ["sudo", "systemctl", "start", "docker"],
                            ["sudo", "systemctl", "enable", "docker"],
                        ],
                    },
                    {
                        "id": "start-docker-openrc",
                        "label": "Start Docker daemon (OpenRC/Alpine)",
                        "description": (
                            "Start the Docker daemon on Alpine or other "
                            "OpenRC-based systems."
                        ),
                        "icon": "🔄",
                        "recommended": False,
                        "requires": {"is_linux": True},
                        "strategy": "env_fix",
                        "fix_commands": [
                            ["sudo", "rc-update", "add", "docker", "default"],
                            ["sudo", "service", "docker", "start"],
                        ],
                    },
                    {
                        "id": "start-dockerd-manual",
                        "label": "Start Docker daemon manually",
                        "description": (
                            "Start dockerd directly. Use this when systemctl "
                            "and OpenRC are both unavailable (e.g. WSL, "
                            "containers)."
                        ),
                        "icon": "⚙️",
                        "recommended": False,
                        "requires": {"is_linux": True},
                        "strategy": "manual",
                        "instructions": (
                            "Run: sudo dockerd &\n"
                            "Wait a few seconds, then retry your command."
                        ),
                    },
                    {
                        "id": "start-docker-desktop",
                        "label": "Start Docker Desktop (macOS)",
                        "description": (
                            "On macOS, Docker runs via Docker Desktop — "
                            "a GUI application. Open it from Applications "
                            "or the menu bar."
                        ),
                        "icon": "🖥️",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "1. Open Docker Desktop from Applications\n"
                            "2. Wait for the whale icon in the menu bar "
                            "to show 'Docker Desktop is running'\n"
                            "3. Retry your command"
                        ),
                    },
                ],
            },
            # ── Docker socket permission denied ────────────────────
            {
                "pattern": (
                    r"Got permission denied while trying to connect to the Docker daemon socket|"
                    r"dial unix /var/run/docker\.sock:.*permission denied|"
                    r"permission denied.*docker\.sock"
                ),
                "failure_id": "docker_socket_permission",
                "category": "permissions",
                "label": "Docker socket permission denied",
                "description": (
                    "Your user does not have permission to access the Docker "
                    "daemon socket. By default, Docker requires root or "
                    "membership in the 'docker' group."
                ),
                "example_stderr": (
                    "Got permission denied while trying to connect to the "
                    "Docker daemon socket at unix:///var/run/docker.sock"
                ),
                "options": [
                    {
                        "id": "add-docker-group",
                        "label": "Add user to docker group",
                        "description": (
                            "Add your user to the 'docker' group. You will "
                            "need to log out and back in (or run 'newgrp "
                            "docker') for the change to take effect."
                        ),
                        "icon": "👤",
                        "recommended": True,
                        "requires": {"is_linux": True, "not_root": True},
                        "strategy": "env_fix",
                        "fix_commands": [
                            ["sudo", "groupadd", "-f", "docker"],
                            ["sudo", "usermod", "-aG", "docker",
                             "${USER}"],
                        ],
                    },
                    {
                        "id": "use-sudo",
                        "label": "Run with sudo (temporary)",
                        "description": (
                            "Prefix docker commands with sudo. This works "
                            "immediately but is not recommended long-term."
                        ),
                        "icon": "🔑",
                        "recommended": False,
                        "strategy": "retry_with_modifier",
                        "modifier": {"use_sudo": True},
                    },
                ],
            },
            # ── Docker not installed ───────────────────────────────
            {
                "pattern": (
                    r"docker:\s*command not found|"
                    r"docker:\s*not found|"
                    r"No such file or directory.*docker"
                ),
                "failure_id": "docker_not_installed",
                "category": "dependency",
                "label": "Docker not installed",
                "description": (
                    "The docker CLI binary is not found on this system. "
                    "Docker needs to be installed before it can be used."
                ),
                "example_stderr": "docker: command not found",
                "options": [
                    {
                        "id": "install-docker",
                        "label": "Install Docker",
                        "description": (
                            "Install Docker using the system package manager "
                            "or the official convenience script."
                        ),
                        "icon": "🐳",
                        "recommended": True,
                        "strategy": "install_dep",
                        "dep": "docker",
                    },
                ],
            },
            # ── containerd not running ─────────────────────────────
            {
                "pattern": (
                    r"failed to start containerd|"
                    r"containerd\.sock:.*connect:.*connection refused|"
                    r"containerd is not running"
                ),
                "failure_id": "docker_containerd_down",
                "category": "environment",
                "label": "containerd not running",
                "description": (
                    "The containerd runtime is not running. Docker requires "
                    "containerd to manage container lifecycles."
                ),
                "example_stderr": (
                    "failed to start containerd: "
                    "containerd.sock: connect: connection refused"
                ),
                "options": [
                    {
                        "id": "start-containerd",
                        "label": "Start containerd daemon",
                        "description": (
                            "Start the containerd service. If containerd is "
                            "not installed, Install Docker again to get it."
                        ),
                        "icon": "🔄",
                        "recommended": True,
                        "requires": {"has_systemd": True},
                        "strategy": "env_fix",
                        "fix_commands": [
                            ["sudo", "systemctl", "start", "containerd"],
                        ],
                    },
                    {
                        "id": "reinstall-containerd",
                        "label": "Reinstall containerd",
                        "description": (
                            "Install the containerd.io package to restore "
                            "the runtime."
                        ),
                        "icon": "📦",
                        "recommended": False,
                        "strategy": "install_packages",
                        "packages": {
                            "debian": ["containerd.io"],
                            "rhel": ["containerd.io"],
                            "alpine": ["containerd"],
                            "arch": ["containerd"],
                            "suse": ["containerd"],
                        },
                    },
                    {
                        "id": "restart-docker-desktop-containerd",
                        "label": "Restart Docker Desktop (macOS)",
                        "description": (
                            "On macOS, containerd is managed by Docker "
                            "Desktop. Restarting the application often "
                            "resolves containerd issues."
                        ),
                        "icon": "🖥️",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "1. Click the Docker whale icon in the menu bar\n"
                            "2. Select 'Restart'\n"
                            "3. Wait for Docker Desktop to fully start\n"
                            "4. Retry your command"
                        ),
                    },
                ],
            },
            # ── Storage driver error ───────────────────────────────
            {
                "pattern": (
                    r"error initializing graphdriver|"
                    r"driver not supported|"
                    r"Error starting daemon:.*storage-driver|"
                    r"devicemapper:.*Error running deviceCreate"
                ),
                "failure_id": "docker_storage_driver",
                "category": "environment",
                "label": "Docker storage driver error",
                "description": (
                    "Docker cannot initialize its storage driver. This can "
                    "happen when the filesystem does not support the "
                    "configured driver (e.g. overlay2 on an old kernel, "
                    "devicemapper on a filesystem without dm support)."
                ),
                "example_stderr": (
                    "Error starting daemon: error initializing graphdriver: "
                    "driver not supported"
                ),
                "options": [
                    {
                        "id": "reset-storage",
                        "label": "Reset Docker storage",
                        "description": (
                            "Stop Docker, remove the storage directory, "
                            "and restart. WARNING: this deletes all local "
                            "images, containers, and volumes."
                        ),
                        "icon": "🗑️",
                        "recommended": True,
                        "risk": "high",
                        "requires": {"has_systemd": True, "writable_rootfs": True},
                        "strategy": "cleanup_retry",
                        "cleanup_commands": [
                            ["sudo", "systemctl", "stop", "docker"],
                            ["sudo", "rm", "-rf",
                             "/var/lib/docker"],
                            ["sudo", "systemctl", "start", "docker"],
                        ],
                    },
                    {
                        "id": "switch-overlay2",
                        "label": "Switch to overlay2 driver",
                        "description": (
                            "Configure Docker to use the overlay2 storage "
                            "driver, which is compatible with most modern "
                            "Linux kernels (4.0+)."
                        ),
                        "icon": "⚙️",
                        "recommended": False,
                        "requires": {"is_linux": True},
                        "strategy": "manual",
                        "instructions": (
                            "1. Stop Docker: sudo systemctl stop docker\n"
                            "2. Edit /etc/docker/daemon.json:\n"
                            '   {"storage-driver": "overlay2"}\n'
                            "3. Start Docker: sudo systemctl start docker"
                        ),
                    },
                    {
                        "id": "reset-docker-desktop-storage",
                        "label": "Reset Docker Desktop storage (macOS)",
                        "description": (
                            "On macOS, Docker Desktop manages its own "
                            "storage in a VM. Use the Troubleshoot menu "
                            "to purge data."
                        ),
                        "icon": "🖥️",
                        "recommended": False,
                        "risk": "high",
                        "strategy": "manual",
                        "instructions": (
                            "1. Open Docker Desktop → Settings → "
                            "Resources\n"
                            "2. Or: Docker Desktop → Troubleshoot → "
                            "'Clean / Purge data'\n"
                            "3. WARNING: this deletes all images, "
                            "containers, and volumes\n"
                            "4. Restart Docker Desktop"
                        ),
                    },
                ],
            },
            # ── Docker API version mismatch ────────────────────────
            {
                "pattern": (
                    r"client version .* is too old|"
                    r"Minimum supported API version|"
                    r"Error response from daemon: client version|"
                    r"API version .* is too new"
                ),
                "failure_id": "docker_version_mismatch",
                "category": "compatibility",
                "label": "Docker client/server version mismatch",
                "description": (
                    "The Docker CLI version is incompatible with the Docker "
                    "daemon. This happens when the client and server are at "
                    "very different versions."
                ),
                "example_stderr": (
                    "Error response from daemon: client version 1.22 is "
                    "too old. Minimum supported API version is 1.24"
                ),
                "options": [
                    {
                        "id": "upgrade-docker",
                        "label": "Upgrade Docker to latest",
                        "description": (
                            "Upgrade both Docker client and daemon to the "
                            "latest version available."
                        ),
                        "icon": "⬆️",
                        "recommended": True,
                        "strategy": "install_dep",
                        "dep": "docker",
                    },
                ],
            },
            # ── Port already allocated ─────────────────────────────
            {
                "pattern": (
                    r"Bind for 0\.0\.0\.0:.*failed:.*port is already allocated|"
                    r"address already in use|"
                    r"port is already allocated"
                ),
                "failure_id": "docker_port_conflict",
                "category": "environment",
                "label": "Port already in use",
                "description": (
                    "The port Docker is trying to bind is already in use "
                    "by another process or container."
                ),
                "example_stderr": (
                    "Bind for 0.0.0.0:8080 failed: port is already allocated"
                ),
                "options": [
                    {
                        "id": "find-port-conflict",
                        "label": "Find and stop conflicting process",
                        "description": (
                            "Use lsof or ss to find what is using the port, "
                            "then stop it."
                        ),
                        "icon": "🔍",
                        "recommended": True,
                        "strategy": "manual",
                        "instructions": (
                            "Find what is using the port:\n"
                            "  sudo lsof -i :<PORT> -P -n\n"
                            "  sudo ss -tlnp | grep <PORT>\n"
                            "Then stop the conflicting process or use a "
                            "different port with -p <OTHER_PORT>:<PORT>."
                        ),
                    },
                ],
            },
            # ── cgroup v2 incompatibility ──────────────────────────
            {
                "pattern": (
                    r"failed to create shim.*cgroup|"
                    r"OCI runtime create failed|"
                    r"cgroup.*not supported|"
                    r"systemd cgroup flag passed, but systemd.*not detected"
                ),
                "failure_id": "docker_cgroup_v2",
                "category": "compatibility",
                "label": "cgroup v2 incompatibility",
                "description": (
                    "Docker is failing due to cgroup v2 incompatibility. "
                    "Older Docker versions (< 20.10) do not support cgroup "
                    "v2, which is the default on newer kernels."
                ),
                "example_stderr": (
                    "OCI runtime create failed: "
                    "cgroup v2 is not supported"
                ),
                "options": [
                    {
                        "id": "upgrade-docker-cgroup",
                        "label": "Upgrade Docker (cgroup v2 support)",
                        "description": (
                            "Upgrade Docker to version 20.10+ which has "
                            "full cgroup v2 support."
                        ),
                        "icon": "⬆️",
                        "recommended": True,
                        "strategy": "install_dep",
                        "dep": "docker",
                    },
                    {
                        "id": "fallback-cgroup-v1",
                        "label": "Enable cgroup v1 (kernel parameter)",
                        "description": (
                            "Add systemd.unified_cgroup_hierarchy=0 to "
                            "kernel boot parameters to fall back to cgroup "
                            "v1. Requires reboot."
                        ),
                        "icon": "⚙️",
                        "recommended": False,
                        "risk": "high",
                        "requires": {"is_linux": True, "not_container": True},
                        "strategy": "manual",
                        "instructions": (
                            "1. Edit /etc/default/grub\n"
                            "2. Add to GRUB_CMDLINE_LINUX:\n"
                            "   systemd.unified_cgroup_hierarchy=0\n"
                            "3. sudo update-grub (Debian) or "
                            "sudo grub2-mkconfig -o /boot/grub2/grub.cfg "
                            "(RHEL)\n"
                            "4. Reboot"
                        ),
                    },
                ],
            },
    ],

    # ── docker-compose ─────────────────────────────────────────

    "docker-compose": [
            # ── compose: not a docker command ──────────────────────
            {
                "pattern": (
                    r"'compose' is not a docker command|"
                    r"docker: 'compose' is not a docker command|"
                    r"is not a docker command"
                ),
                "failure_id": "compose_plugin_not_found",
                "category": "dependency",
                "label": "Compose plugin not registered",
                "description": (
                    "The 'docker compose' subcommand is not available. "
                    "Docker Compose V2 is a CLI plugin that must be "
                    "installed separately from Docker Engine."
                ),
                "example_stderr": (
                    "docker: 'compose' is not a docker command.\n"
                    "See 'docker --help'"
                ),
                "options": [
                    {
                        "id": "install-compose-plugin",
                        "label": "Install Docker Compose plugin",
                        "description": (
                            "Install the docker-compose-plugin package "
                            "to enable the 'docker compose' command."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "install_dep",
                        "dep": "docker-compose",
                    },
                ],
            },
            # ── docker-compose (v1 legacy) not found ──────────────
            {
                "pattern": (
                    r"docker-compose:\s*command not found|"
                    r"docker-compose:\s*not found|"
                    r"No such file or directory.*docker-compose"
                ),
                "failure_id": "compose_v1_not_found",
                "category": "compatibility",
                "label": "Legacy docker-compose (v1) not found",
                "description": (
                    "The standalone 'docker-compose' binary (v1) is "
                    "not installed. Docker Compose V1 is deprecated. "
                    "Use 'docker compose' (v2 plugin) instead."
                ),
                "example_stderr": "docker-compose: command not found",
                "options": [
                    {
                        "id": "install-compose-v2",
                        "label": "Install Docker Compose V2 (recommended)",
                        "description": (
                            "Install the modern Docker Compose V2 plugin. "
                            "Use 'docker compose' (with space) instead of "
                            "'docker-compose' (with hyphen)."
                        ),
                        "icon": "⬆️",
                        "recommended": True,
                        "strategy": "install_dep",
                        "dep": "docker-compose",
                    },
                    {
                        "id": "alias-compose-v1",
                        "label": "Create compatibility alias",
                        "description": (
                            "Create a shell alias so that "
                            "'docker-compose' maps to 'docker compose'. "
                            "Useful for scripts that still use the v1 "
                            "command name."
                        ),
                        "icon": "🔗",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "Add to your shell profile (~/.bashrc, "
                            "~/.zshrc):\n"
                            "  alias docker-compose='docker compose'\n"
                            "Then source the profile or open a new shell."
                        ),
                    },
                ],
            },
            # ── compose file syntax / version error ───────────────
            {
                "pattern": (
                    r"yaml: line \d+:|"
                    r"Version in .* is unsupported|"
                    r"services\.\w+ must be a mapping|"
                    r"Unsupported config option"
                ),
                "failure_id": "compose_yaml_error",
                "category": "environment",
                "label": "Compose file syntax or version error",
                "description": (
                    "The docker-compose.yml file has a syntax error, "
                    "an unsupported version field, or invalid YAML. "
                    "Compose V2 ignores the 'version' field — removing "
                    "it often fixes version-related errors."
                ),
                "example_stderr": (
                    'Version in "./docker-compose.yml" is unsupported'
                ),
                "options": [
                    {
                        "id": "remove-version-field",
                        "label": "Remove version field from compose file",
                        "description": (
                            "Docker Compose V2 does not require and "
                            "ignores the 'version' field. Removing it "
                            "fixes most version-related parse errors."
                        ),
                        "icon": "✏️",
                        "recommended": True,
                        "strategy": "manual",
                        "instructions": (
                            "Edit your docker-compose.yml and remove "
                            "the 'version: \"X.Y\"' line at the top.\n"
                            "Docker Compose V2 determines the schema "
                            "automatically."
                        ),
                    },
                    {
                        "id": "upgrade-compose-yaml",
                        "label": "Upgrade Docker Compose",
                        "description": (
                            "Upgrade to the latest Compose V2 which "
                            "supports the widest range of compose "
                            "file formats."
                        ),
                        "icon": "⬆️",
                        "recommended": False,
                        "strategy": "install_dep",
                        "dep": "docker-compose",
                    },
                ],
            },
    ],

    # ── python ─────────────────────────────────────────────────

    "python": [
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
    ],

    # ── yarn ───────────────────────────────────────────────────

    "yarn": [
            # ── cmdtest conflict (Debian) ─────────────────────────
            # On Debian, the `cmdtest` package also provides
            # /usr/bin/yarn (a scenario testing tool). If a user
            # runs `apt-get install yarn` on a system without the
            # Yarn repo, they get cmdtest's yarn instead. When
            # they try to use it as a JS package manager, they get
            # errors like "No such file or directory: 'upgrade'"
            # or "There are no scenarios".
            {
                "pattern": (
                    r"There are no scenarios|"
                    r"No such file or directory.*upgrade|"
                    r"No such file or directory.*add|"
                    r"cmdtest"
                ),
                "failure_id": "yarn_cmdtest_conflict",
                "category": "configuration",
                "label": "Wrong yarn installed (cmdtest conflict)",
                "description": (
                    "The system has the 'cmdtest' package installed, "
                    "which also provides a /usr/bin/yarn binary. This "
                    "is NOT the JavaScript package manager Yarn. The "
                    "cmdtest yarn is a scenario testing tool for Unix "
                    "commands. Remove cmdtest and install the correct "
                    "yarn."
                ),
                "example_stderr": (
                    "ERROR: There are no scenarios; must have at "
                    "least one"
                ),
                "options": [
                    {
                        "id": "use-npm",
                        "label": "Install yarn via npm",
                        "description": (
                            "Remove cmdtest's yarn and install the "
                            "correct Yarn via npm. This is the most "
                            "reliable method."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "npm",
                        "risk": "low",
                    },
                    {
                        "id": "remove-cmdtest",
                        "label": "Remove cmdtest and retry apt",
                        "description": (
                            "Remove the cmdtest package, then add the "
                            "Yarn apt repository and install the "
                            "correct yarn package."
                        ),
                        "icon": "🗑️",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "1. sudo apt-get remove cmdtest\n"
                            "2. curl -sS https://dl.yarnpkg.com/debian/"
                            "pubkey.gpg | sudo apt-key add -\n"
                            "3. echo 'deb https://dl.yarnpkg.com/debian/ "
                            "stable main' | sudo tee /etc/apt/sources."
                            "list.d/yarn.list\n"
                            "4. sudo apt-get update && sudo apt-get "
                            "install yarn"
                        ),
                        "risk": "medium",
                    },
                ],
            },

            # ── Yarn repo not configured (apt) ────────────────────
            # On fresh Debian/Ubuntu, `apt-get install yarn` fails
            # because yarn isn't in the default apt repos (unless
            # the Yarn repo or NodeSource repo has been added).
            {
                "pattern": (
                    r"Unable to locate package yarn|"
                    r"Package 'yarn' has no installation candidate|"
                    r"has no installation candidate"
                ),
                "failure_id": "yarn_repo_not_configured",
                "category": "configuration",
                "label": "Yarn package repository not configured",
                "description": (
                    "The yarn package is not available in the default "
                    "apt repositories. On Debian/Ubuntu, yarn requires "
                    "adding the official Yarn repository "
                    "(dl.yarnpkg.com) first, or installing via npm."
                ),
                "example_stderr": (
                    "E: Unable to locate package yarn"
                ),
                "options": [
                    {
                        "id": "use-npm",
                        "label": "Install yarn via npm",
                        "description": (
                            "Install yarn globally using npm. This is "
                            "the most reliable cross-platform method "
                            "and does not require repository "
                            "configuration."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "npm",
                        "risk": "low",
                    },
                    {
                        "id": "use-brew",
                        "label": "Install via Homebrew",
                        "description": (
                            "Use Homebrew to install yarn. No external "
                            "repository configuration needed."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                        "risk": "low",
                    },
                ],
            },

            # ── Corepack conflict (brew) ──────────────────────────
            # On macOS with Homebrew, `brew install yarn` fails if
            # the corepack formula is already installed because both
            # provide yarn and yarnpkg executables.
            {
                "pattern": (
                    r"Cannot install yarn because conflicting formulae|"
                    r"conflicting formulae.*corepack|"
                    r"corepack.*both install.*yarn"
                ),
                "failure_id": "yarn_corepack_conflict",
                "category": "configuration",
                "label": "Yarn conflicts with corepack (Homebrew)",
                "description": (
                    "Cannot install yarn via Homebrew because the "
                    "corepack formula is already installed. Both "
                    "formulae provide the 'yarn' and 'yarnpkg' "
                    "executables. Unlink corepack first or use npm."
                ),
                "example_stderr": (
                    "Error: Cannot install yarn because conflicting "
                    "formulae are installed.\n"
                    "  corepack: because both install `yarn` and "
                    "`yarnpkg` executables"
                ),
                "options": [
                    {
                        "id": "use-npm",
                        "label": "Install yarn via npm instead",
                        "description": (
                            "Use npm to install yarn globally. This "
                            "avoids the Homebrew conflict entirely."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "npm",
                        "risk": "low",
                    },
                    {
                        "id": "unlink-corepack",
                        "label": "Unlink corepack and retry brew",
                        "description": (
                            "Unlink the corepack formula to remove "
                            "its symlinks, then install yarn via brew."
                        ),
                        "icon": "🔗",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "1. brew unlink corepack\n"
                            "2. brew install yarn"
                        ),
                        "risk": "medium",
                    },
                ],
            },
    ],

    # ── poetry ─────────────────────────────────────────────────

    "poetry": [
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
    ],

    # ── uv ─────────────────────────────────────────────────────

    "uv": [
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
    ],

    # ── pnpm ───────────────────────────────────────────────────

    "pnpm": [
            # ── Corepack conflict (brew) ──────────────────────────
            # On macOS with Homebrew, `brew install pnpm` fails if
            # the corepack formula is already installed because both
            # provide the pnpm executable. Same pattern as yarn.
            {
                "pattern": (
                    r"Cannot install pnpm because conflicting formulae|"
                    r"conflicting formulae.*corepack|"
                    r"corepack.*both install.*pnpm"
                ),
                "failure_id": "pnpm_corepack_conflict",
                "category": "configuration",
                "label": "pnpm conflicts with corepack (Homebrew)",
                "description": (
                    "Cannot install pnpm via Homebrew because the "
                    "corepack formula is already installed. Both "
                    "formulae provide the 'pnpm' executable. Unlink "
                    "corepack first, or install via npm."
                ),
                "example_stderr": (
                    "Error: Cannot install pnpm because conflicting "
                    "formulae are installed.\n"
                    "  corepack: because both install `pnpm` "
                    "executables"
                ),
                "options": [
                    {
                        "id": "use-npm",
                        "label": "Install pnpm via npm instead",
                        "description": (
                            "Use npm to install pnpm globally. This "
                            "avoids the Homebrew conflict entirely."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "npm",
                        "risk": "low",
                    },
                    {
                        "id": "use-standalone",
                        "label": "Install via standalone script",
                        "description": (
                            "Use the official pnpm standalone "
                            "installer (get.pnpm.io). Does not "
                            "require npm or Homebrew."
                        ),
                        "icon": "📥",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "_default",
                        "risk": "low",
                    },
                    {
                        "id": "unlink-corepack",
                        "label": "Unlink corepack and retry brew",
                        "description": (
                            "Unlink the corepack formula to remove "
                            "its symlinks, then install pnpm via brew."
                        ),
                        "icon": "🔗",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "1. brew unlink corepack\n"
                            "2. brew install pnpm"
                        ),
                        "risk": "medium",
                    },
                ],
            },
    ],

    # ── nvm ────────────────────────────────────────────────────
    # nvm is a shell function (not a binary) installed via a bash
    # script that git-clones into ~/.nvm.  Two unique failure modes.

    "nvm": [
        # ── ~/.nvm already exists ──────────────────────────────
        # If ~/.nvm exists (partial install, manual mkdir, or
        # previous broken install), git clone fails.
        {
            "pattern": (
                r"already exists and is not an empty directory|"
                r"destination path.*\.nvm.*already exists"
            ),
            "failure_id": "nvm_dir_exists",
            "category": "environment",
            "label": "~/.nvm directory already exists",
            "description": (
                "The nvm installer tries to git-clone into ~/.nvm, "
                "but this directory already exists (possibly from a "
                "previous partial or broken install). The git clone "
                "fails because the target directory is not empty."
            ),
            "example_stderr": (
                "fatal: destination path '/home/user/.nvm' already "
                "exists and is not an empty directory."
            ),
            "options": [
                {
                    "id": "cleanup-nvm-dir",
                    "label": "Remove ~/.nvm and retry",
                    "description": (
                        "Back up and remove the existing ~/.nvm "
                        "directory, then re-run the installer. "
                        "This will remove any previously installed "
                        "Node.js versions managed by nvm."
                    ),
                    "icon": "🗑️",
                    "recommended": True,
                    "strategy": "cleanup_retry",
                    "cleanup_commands": [
                        ["bash", "-c",
                         "mv ~/.nvm ~/.nvm.bak.$(date +%s) 2>/dev/null"
                         " || rm -rf ~/.nvm"],
                    ],
                    "risk": "medium",
                },
                {
                    "id": "use-brew-instead",
                    "label": "Install via Homebrew instead",
                    "description": (
                        "Skip the git-clone installer and use "
                        "brew install nvm. Brew manages nvm "
                        "separately from ~/.nvm."
                    ),
                    "icon": "🍺",
                    "recommended": False,
                    "strategy": "switch_method",
                    "method": "brew",
                    "risk": "low",
                },
            ],
        },
        # ── Shell profile not found ────────────────────────────
        # The installer tries to add sourcing lines to .bashrc,
        # .zshrc, or .profile but can't find any of them.
        {
            "pattern": (
                r"profile.*not found|"
                r"no profile found|"
                r"could not detect.*profile|"
                r"create.*profile.*nvm"
            ),
            "failure_id": "nvm_profile_not_found",
            "category": "configuration",
            "label": "Shell profile not found for nvm",
            "description": (
                "The nvm installer could not find a shell profile "
                "file (.bashrc, .zshrc, .profile, .bash_profile) to "
                "add the nvm sourcing lines. nvm may have installed "
                "correctly but won't be available in new shell "
                "sessions until the profile is configured."
            ),
            "example_stderr": (
                "=> Profile not found. Tried ~/.bashrc, "
                "~/.bash_profile, ~/.zshrc, and ~/.profile."
            ),
            "options": [
                {
                    "id": "create-bashrc",
                    "label": "Create ~/.bashrc with nvm config",
                    "description": (
                        "Create a .bashrc file and add the nvm "
                        "sourcing lines so nvm loads automatically."
                    ),
                    "icon": "📝",
                    "recommended": True,
                    "strategy": "env_fix",
                    "fix_commands": [
                        ["bash", "-c",
                         "touch ~/.bashrc && echo '"
                         'export NVM_DIR="$HOME/.nvm"\n'
                         '[ -s "$NVM_DIR/nvm.sh" ] && '
                         '\\. "$NVM_DIR/nvm.sh"'
                         "' >> ~/.bashrc"],
                    ],
                    "risk": "low",
                },
                {
                    "id": "manual-add-profile",
                    "label": "Manually add nvm to shell profile",
                    "description": (
                        "Add the nvm sourcing lines to your "
                        "preferred shell configuration file."
                    ),
                    "icon": "📋",
                    "recommended": False,
                    "strategy": "manual",
                    "instructions": (
                        "Add these lines to your shell config "
                        "(~/.bashrc, ~/.zshrc, or ~/.profile):\n\n"
                        'export NVM_DIR="$HOME/.nvm"\n'
                        '[ -s "$NVM_DIR/nvm.sh" ] && '
                        '\\. "$NVM_DIR/nvm.sh"\n'
                        '[ -s "$NVM_DIR/bash_completion" ] && '
                        '\\. "$NVM_DIR/bash_completion"'
                    ),
                    "risk": "low",
                },
            ],
        },
    ],

    # ── kubectl ────────────────────────────────────────────────

    "kubectl": [
            # ── K8s repo not configured (apt/dnf/zypper) ──────────
            # On fresh systems, apt/dnf/zypper won't find kubectl
            # because the Kubernetes package repo is not added by
            # default. The generic 'package not found' handler fires
            # the detection, but the remediation needs to suggest
            # adding the K8s repo OR using _default binary download.
            {
                "pattern": (
                    r"Unable to locate package kubectl|"
                    r"No match for argument.*kubernetes|"
                    r"Package 'kubectl' has no installation candidate|"
                    r"not found in package names"
                ),
                "failure_id": "kubectl_repo_not_configured",
                "category": "configuration",
                "label": "Kubernetes package repository not configured",
                "description": (
                    "The kubectl package is not available in the default "
                    "system repositories. On Debian/Ubuntu, Fedora, and "
                    "openSUSE, kubectl requires adding the official "
                    "Kubernetes package repository (pkgs.k8s.io) first."
                ),
                "example_stderr": (
                    "E: Unable to locate package kubectl"
                ),
                "options": [
                    {
                        "id": "use-binary-download",
                        "label": "Download kubectl binary directly",
                        "description": (
                            "Download the pre-compiled kubectl binary "
                            "from dl.k8s.io. This is the most reliable "
                            "method and does not require repository "
                            "configuration."
                        ),
                        "icon": "⬇️",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "_default",
                        "risk": "low",
                    },
                    {
                        "id": "use-snap",
                        "label": "Install via snap",
                        "description": (
                            "Use snap to install kubectl. No external "
                            "repository configuration needed."
                        ),
                        "icon": "📦",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "snap",
                        "risk": "low",
                    },
                ],
            },

            # ── Version skew with cluster ─────────────────────────
            # kubectl warns when its version is more than ±1 minor
            # version from the cluster. This fires when the user runs
            # kubectl version (full, not --client) after install.
            {
                "pattern": (
                    r"WARNING:.*version difference|"
                    r"version skew|"
                    r"client version.*is older than.*server version|"
                    r"client version.*is newer than.*server version"
                ),
                "failure_id": "kubectl_version_skew",
                "category": "environment",
                "label": "kubectl version skew with cluster",
                "description": (
                    "The installed kubectl version is more than ±1 minor "
                    "version away from the Kubernetes cluster version. "
                    "This may cause unexpected behavior or API "
                    "incompatibilities."
                ),
                "example_stderr": (
                    "WARNING: version difference between client (1.32) "
                    "and server (1.28) exceeds the supported minor "
                    "version skew of +/-1"
                ),
                "options": [
                    {
                        "id": "reinstall-matching-version",
                        "label": "Reinstall kubectl matching cluster version",
                        "description": (
                            "Download a specific kubectl version that "
                            "matches your cluster. Use: curl -LO "
                            "\"https://dl.k8s.io/release/v{cluster_version}"
                            "/bin/{os}/{arch}/kubectl\""
                        ),
                        "icon": "🔄",
                        "recommended": True,
                        "strategy": "manual",
                        "instructions": (
                            "1. Check your cluster version: "
                            "kubectl version --short 2>/dev/null | "
                            "grep Server\n"
                            "2. Download matching kubectl: curl -LO "
                            "\"https://dl.k8s.io/release/v<CLUSTER_VER>"
                            "/bin/$(uname -s | tr A-Z a-z)/$(uname -m "
                            "| sed 's/x86_64/amd64/;s/aarch64/arm64/')"
                            "/kubectl\"\n"
                            "3. chmod +x kubectl && sudo mv kubectl "
                            "/usr/local/bin/"
                        ),
                        "risk": "low",
                    },
                ],
            },

            # ── Exec format error (arch mismatch) ─────────────────
            # Defense-in-depth — same pattern as node. Covered by
            # the L0 userland detection, but catches edge cases.
            {
                "pattern": (
                    r"exec format error|"
                    r"cannot execute binary file.*Exec format"
                ),
                "failure_id": "kubectl_exec_format_error",
                "category": "environment",
                "label": "kubectl binary architecture mismatch",
                "description": (
                    "The kubectl binary was compiled for a different "
                    "CPU architecture than this system. This commonly "
                    "occurs on Raspberry Pi systems where the kernel "
                    "is 64-bit but the userland is 32-bit."
                ),
                "example_stderr": (
                    "bash: /usr/local/bin/kubectl: cannot execute "
                    "binary file: Exec format error"
                ),
                "options": [
                    {
                        "id": "reinstall-correct-arch",
                        "label": "Reinstall with correct architecture",
                        "description": (
                            "Remove the wrong-architecture binary and "
                            "reinstall using the _default method which "
                            "now detects the correct userland architecture."
                        ),
                        "icon": "🔄",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "_default",
                        "risk": "low",
                    },
                    {
                        "id": "install-via-apt",
                        "label": "Install via system package manager",
                        "description": (
                            "Use the system package manager which "
                            "selects the correct architecture "
                            "automatically."
                        ),
                        "icon": "📦",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "apt",
                        "risk": "low",
                    },
                ],
            },
    ],

    # ── node ───────────────────────────────────────────────────

    "node": [
            # ── GLIBC too old for pre-compiled binary ────────────────
            # Node.js 18+ requires GLIBC_2.28. Older distros like
            # CentOS 7 (GLIBC 2.17) and Ubuntu 18.04 (GLIBC 2.27)
            # cannot run the official pre-compiled binaries.
            # This fires when the _default binary download path is used.
            {
                "pattern": (
                    r"GLIBC_2\.\d+.*not found|"
                    r"version.*GLIBC.*not found|"
                    r"libc\.so\.6.*version.*not found"
                ),
                "failure_id": "node_glibc_too_old",
                "category": "environment",
                "label": "System glibc too old for Node.js binary",
                "description": (
                    "The pre-compiled Node.js binary requires a newer "
                    "version of glibc than is available on this system. "
                    "Node.js 18+ requires GLIBC_2.28 or newer. Older "
                    "distributions like CentOS 7 (GLIBC 2.17) and "
                    "Ubuntu 18.04 (GLIBC 2.27) cannot run these binaries."
                ),
                "example_stderr": (
                    "node: /lib/x86_64-linux-gnu/libc.so.6: "
                    "version `GLIBC_2.28' not found (required by node)"
                ),
                "options": [
                    {
                        "id": "switch-to-pm",
                        "label": "Install via system package manager",
                        "description": (
                            "Use the distro's package manager to install "
                            "a Node.js version compatible with this system's "
                            "glibc. The version may be older but will work."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "apt",
                        "risk": "low",
                    },
                    {
                        "id": "upgrade-os",
                        "label": "Upgrade to a newer OS release",
                        "description": (
                            "Upgrade your operating system to a version "
                            "that ships GLIBC 2.28+. Ubuntu 20.04+, "
                            "Debian 10+, RHEL 8+, Fedora 28+ all qualify. "
                            "This is the long-term solution."
                        ),
                        "icon": "⬆️",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "Upgrade your Linux distribution to a newer "
                            "release. For Ubuntu: upgrade to 20.04 or newer. "
                            "For CentOS/RHEL: upgrade to RHEL 8 or "
                            "Rocky/Alma 8+."
                        ),
                        "risk": "high",
                    },
                    {
                        "id": "unofficial-builds",
                        "label": "Use unofficial Node.js builds for old glibc",
                        "description": (
                            "The Node.js project provides unofficial builds "
                            "compiled against older glibc versions at "
                            "https://unofficial-builds.nodejs.org/. These "
                            "work on CentOS 7 and Ubuntu 18.04."
                        ),
                        "icon": "🔧",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "Download from "
                            "https://unofficial-builds.nodejs.org/"
                            "download/release/ — look for builds with "
                            "'glibc-217' in the filename."
                        ),
                        "risk": "medium",
                    },
                ],
            },

            # ── Node.js version too old ──────────────────────────────
            # Installed Node.js is too old for modern JS features.
            # This catches: optional chaining (?.), nullish coalescing
            # (??), top-level await, import assertions, ERR_REQUIRE_ESM.
            {
                "pattern": (
                    r"SyntaxError: Unexpected token '\?'|"
                    r"SyntaxError: Unexpected token '\.\.'|"
                    r"SyntaxError.*optional chaining|"
                    r"SyntaxError.*nullish coalescing|"
                    r"ERR_REQUIRE_ESM|"
                    r"ERR_UNKNOWN_FILE_EXTENSION|"
                    r"ERR_UNSUPPORTED_ESM_URL_SCHEME|"
                    r"requires a peer of node@|"
                    r"engine.*node.*npm.*incompatible|"
                    r"The engine \"node\" is incompatible"
                ),
                "failure_id": "node_version_too_old",
                "category": "environment",
                "label": "Node.js version too old for this code",
                "description": (
                    "The installed Node.js version does not support "
                    "modern JavaScript syntax or features. Many tools "
                    "and frameworks require Node.js 18+ for features "
                    "like optional chaining (?.), nullish coalescing "
                    "(??), native ESM imports, and fetch(). Distro "
                    "packages often ship outdated versions."
                ),
                "example_stderr": (
                    "SyntaxError: Unexpected token '?'\n"
                    "    at wrapSafe (internal/modules/cjs/"
                    "loader.js:915:16)"
                ),
                "options": [
                    {
                        "id": "install-via-default",
                        "label": "Install latest LTS from nodejs.org",
                        "description": (
                            "Download the latest LTS Node.js binary "
                            "directly from nodejs.org. This provides the "
                            "newest stable version regardless of distro "
                            "packages."
                        ),
                        "icon": "⬇️",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "_default",
                        "risk": "low",
                    },
                    {
                        "id": "install-via-snap",
                        "label": "Install latest Node.js via snap",
                        "description": (
                            "Snap provides a near-latest Node.js that is "
                            "independent of distro package versions."
                        ),
                        "icon": "📦",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "snap",
                        "risk": "low",
                    },
                    {
                        "id": "use-nvm",
                        "label": "Install Node.js via nvm",
                        "description": (
                            "Use nvm (Node Version Manager) to install "
                            "and manage multiple Node.js versions."
                        ),
                        "icon": "🔄",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "Install nvm, then install the latest LTS:\n"
                            "curl -o- https://raw.githubusercontent.com/"
                            "nvm-sh/nvm/v0.40.1/install.sh | bash\n"
                            "source ~/.bashrc\n"
                            "nvm install --lts"
                        ),
                        "risk": "low",
                    },
                ],
            },

            # ── npm not found after node install ─────────────────────
            # On Debian/Ubuntu/Alpine/Arch, the npm binary is packaged
            # separately from nodejs. If only nodejs was installed
            # (manually, or by a dependency), npm is missing.
            {
                "pattern": (
                    r"npm: command not found|"
                    r"npm: not found|"
                    r"/usr/bin/env:.*npm.*No such file|"
                    r"sh:.*npm.*not found"
                ),
                "failure_id": "node_npm_not_found",
                "category": "dependency",
                "label": "npm not found (packaged separately)",
                "description": (
                    "Node.js is installed but npm is missing. On "
                    "Debian/Ubuntu, Alpine, and Arch Linux, npm is "
                    "distributed as a separate system package. When "
                    "only 'nodejs' is installed via the package manager, "
                    "'npm' is not included automatically."
                ),
                "example_stderr": (
                    "bash: npm: command not found"
                ),
                "options": [
                    {
                        "id": "install-npm-pkg",
                        "label": "Install npm via package manager",
                        "description": (
                            "Install the npm package from your system's "
                            "package manager."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "install_dep",
                        "dep": "npm",
                        "risk": "low",
                    },
                    {
                        "id": "reinstall-node-default",
                        "label": "Reinstall from nodejs.org (includes npm)",
                        "description": (
                            "The pre-compiled Node.js binary from "
                            "nodejs.org includes npm and npx bundled. "
                            "This avoids the split-package issue entirely."
                        ),
                        "icon": "⬇️",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "_default",
                        "risk": "low",
                    },
                ],
            },

            # ── Alpine musl libc incompatibility ────────────────────
            # The official Node.js binaries are compiled against glibc.
            # Alpine uses musl libc. Running a glibc-linked binary on
            # Alpine produces a cryptic "not found" or ENOENT error
            # because the dynamic linker (ld-linux-x86-64.so.2) doesn't
            # exist on musl systems.
            {
                "pattern": (
                    r"Error loading shared library.*ld-linux|"
                    r"No such file or directory.*ld-linux|"
                    r"error while loading shared libraries.*ld-linux|"
                    r"not found.*ld-linux-x86-64|"
                    r"not found.*ld-linux-aarch64"
                ),
                "failure_id": "node_musl_incompatible",
                "category": "environment",
                "label": "Node.js binary incompatible with musl (Alpine)",
                "description": (
                    "The pre-compiled Node.js binary was built for "
                    "glibc but this system uses musl libc (Alpine "
                    "Linux). glibc-linked binaries cannot run on musl "
                    "systems because the expected dynamic linker "
                    "(ld-linux-x86-64.so.2) does not exist."
                ),
                "example_stderr": (
                    "/usr/local/bin/node: error while loading shared "
                    "libraries: ld-linux-x86-64.so.2: "
                    "cannot open shared object file: "
                    "No such file or directory"
                ),
                "options": [
                    {
                        "id": "install-via-apk",
                        "label": "Install Node.js via apk (Alpine-native)",
                        "description": (
                            "Use Alpine's package manager (apk) to "
                            "install a musl-compatible Node.js build. "
                            "This is the correct approach on Alpine."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "apk",
                        "risk": "low",
                    },
                    {
                        "id": "install-compat-layer",
                        "label": "Install glibc compatibility layer",
                        "description": (
                            "Install libc6-compat to provide a glibc "
                            "shim on Alpine. This may allow glibc-linked "
                            "binaries to run but is not recommended for "
                            "production."
                        ),
                        "icon": "🔧",
                        "recommended": False,
                        "strategy": "install_packages",
                        "packages": {
                            "debian": [],
                            "rhel": [],
                            "alpine": ["libc6-compat", "libstdc++"],
                            "arch": [],
                            "suse": [],
                            "macos": [],
                        },
                        "risk": "medium",
                    },
                ],
            },

            # ── Exec format error (arch mismatch) ─────────────────
            # Defense-in-depth: the L0 system profiler now detects
            # 64-bit kernel + 32-bit userland (Raspbian) and corrects
            # the arch, so this should rarely fire. But if someone
            # manually installs an arm64 binary on 32-bit userland,
            # or the detection fails, this catches it.
            {
                "pattern": (
                    r"exec format error|"
                    r"cannot execute binary file.*Exec format|"
                    r"cannot execute: required file not found"
                ),
                "failure_id": "node_exec_format_error",
                "category": "environment",
                "label": "Node.js binary architecture mismatch",
                "description": (
                    "The Node.js binary was compiled for a different "
                    "CPU architecture than this system's userland. "
                    "This commonly occurs on Raspberry Pi systems "
                    "where the kernel is 64-bit (aarch64) but the "
                    "userland is 32-bit (armv7l)."
                ),
                "example_stderr": (
                    "bash: /usr/local/bin/node: "
                    "cannot execute binary file: Exec format error"
                ),
                "options": [
                    {
                        "id": "reinstall-correct-arch",
                        "label": "Reinstall with correct architecture",
                        "description": (
                            "Remove the wrong-architecture binary and "
                            "reinstall using the system package manager "
                            "which will select the correct architecture "
                            "automatically."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "apt",
                        "risk": "low",
                    },
                    {
                        "id": "install-via-snap",
                        "label": "Install via snap",
                        "description": (
                            "Use snap to install Node.js. Snap "
                            "packages are architecture-aware and will "
                            "install the correct build automatically."
                        ),
                        "icon": "📦",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "snap",
                        "risk": "low",
                    },
                ],
            },
    ],

    # ── composer ─────────────────────────────────────────────────

    "composer": [
            # ── PHP version too old for Composer ─────────────────
            # Composer 2.x requires PHP 7.2.5+. The official installer
            # checks PHP version and fails with a clear message.
            # This fires during _default install (curl | php).
            # PM-installed composer has PHP as a dep, so the PM handles
            # version requirements.
            {
                "pattern": (
                    r"Composer requires PHP.*but your PHP version|"
                    r"your PHP version .* does not satisfy that requirement|"
                    r"This version of Composer requires PHP|"
                    r"composer\.phar requires php"
                ),
                "failure_id": "composer_php_version_too_old",
                "category": "environment",
                "label": "PHP version too old for Composer",
                "description": (
                    "Composer 2.x requires PHP 7.2.5 or newer. "
                    "Your system's PHP interpreter is too old. "
                    "Upgrade PHP or use the system package manager "
                    "to install a version of Composer compatible "
                    "with your PHP."
                ),
                "example_stderr": (
                    "Composer requires PHP ^7.2.5 || ^8.0 but your "
                    "PHP version (7.0.33) does not satisfy that "
                    "requirement."
                ),
                "options": [
                    {
                        "id": "upgrade-php",
                        "label": "Upgrade PHP",
                        "description": (
                            "Install a newer PHP version (8.x) using "
                            "your system package manager"
                        ),
                        "icon": "⬆️",
                        "recommended": True,
                        "strategy": "install_dep",
                        "dep": "php",
                    },
                    {
                        "id": "use-apt-composer",
                        "label": "Install Composer via apt",
                        "description": (
                            "On Debian/Ubuntu/Raspbian, apt installs "
                            "a Composer version compatible with the "
                            "system PHP. May be an older Composer "
                            "but it will work."
                        ),
                        "icon": "📦",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "apt",
                    },
                    {
                        "id": "use-brew-composer",
                        "label": "Install Composer via brew",
                        "description": (
                            "On macOS, brew install composer pulls "
                            "a compatible PHP and all required "
                            "extensions automatically."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                    },
                ],
            },
            # ── Missing PHP extension ────────────────────────────
            # The Composer installer requires several PHP extensions.
            # On minimal PHP installs (Docker, stripped system packages),
            # these may be missing. Most common: openssl, mbstring.
            #
            # Platform-aware:
            #   Debian/Raspbian: php-openssl, php-mbstring
            #   RHEL: php-openssl, php-mbstring
            #   Alpine: php-openssl, php-mbstring (versioned)
            #   macOS: brew php includes all extensions
            {
                "pattern": (
                    r"the requested PHP extension (\S+) is missing|"
                    r"The openssl extension is required|"
                    r"ext-openssl is required|"
                    r"requires ext-mbstring|"
                    r"requires ext-json|"
                    r"You need the openssl extension"
                ),
                "failure_id": "composer_missing_php_extension",
                "category": "dependency",
                "label": "Missing PHP extension for Composer",
                "description": (
                    "Composer requires PHP extensions that are not "
                    "installed or enabled. The most common missing "
                    "extensions are openssl (for HTTPS downloads) "
                    "and mbstring (for string handling). Install "
                    "the missing extension packages."
                ),
                "example_stderr": (
                    "The openssl extension is required for SSL/TLS "
                    "protection but is not available. If you can not "
                    "enable the openssl extension, you can disable "
                    "this error, at the risk of compromising the "
                    "security of file downloads via "
                    "the allow_url_fopen directive."
                ),
                "options": [
                    {
                        "id": "install-php-extensions",
                        "label": "Install common PHP extensions",
                        "description": (
                            "Install openssl, mbstring, and other "
                            "extensions Composer needs. On macOS, "
                            "brew PHP includes all extensions."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "install_packages",
                        "packages": {
                            # apt: package names are php-<ext> on
                            # modern Debian/Ubuntu/Raspbian
                            "debian": [
                                "php-curl", "php-mbstring",
                                "php-xml", "php-zip",
                            ],
                            # dnf: same naming on Fedora/RHEL
                            "rhel": [
                                "php-curl", "php-mbstring",
                                "php-xml", "php-zip",
                            ],
                            # apk: php-* in Alpine repos
                            "alpine": [
                                "php-curl", "php-mbstring",
                                "php-openssl", "php-phar",
                                "php-iconv",
                            ],
                            # pacman: php includes most extensions
                            "arch": ["php"],
                            # zypper: same naming
                            "suse": [
                                "php-curl", "php-mbstring",
                                "php-openssl", "php-zip",
                            ],
                            # brew: php formula includes all stdlib
                            # extensions. If somehow missing, reinstall.
                            "macos": ["php"],
                        },
                    },
                    {
                        "id": "use-apt-composer-ext",
                        "label": "Install Composer via apt (pulls PHP deps)",
                        "description": (
                            "On Debian/Ubuntu/Raspbian, apt install "
                            "composer declares correct PHP extension "
                            "dependencies and installs them "
                            "automatically."
                        ),
                        "icon": "📦",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "apt",
                    },
                    {
                        "id": "use-brew-composer-ext",
                        "label": "Install Composer via brew (includes all PHP exts)",
                        "description": (
                            "On macOS, brew install composer pulls "
                            "in brew PHP which includes all standard "
                            "extensions (openssl, mbstring, etc.)."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                    },
                ],
            },
    ],

    # ── phpstan / phpunit ────────────────────────────────────────
    # No per-tool handlers needed. Both tools declare:
    #   install_via: {"_default": "composer_global"}
    # The composer_global method family in METHOD_FAMILY_HANDLERS
    # covers: memory exhaustion + PHP version mismatch.
    # See remediation_handlers.py → METHOD_FAMILY_HANDLERS["composer_global"]
}
