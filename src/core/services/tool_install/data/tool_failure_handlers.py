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
}
