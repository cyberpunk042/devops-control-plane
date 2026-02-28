"""
L0 Data — Infrastructure failure handlers (Layer 1).

Cross-cutting failures: network, disk, permissions, OOM, timeout.
Pure data, no logic.
"""

from __future__ import annotations


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



