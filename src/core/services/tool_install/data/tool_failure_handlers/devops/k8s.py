"""
L0 Data — Kubernetes ecosystem tool-specific failure handlers.

Tools: helm, kubectl
Pure data, no logic.
"""

from __future__ import annotations


_HELM_HANDLERS: list[dict] = [
            # ── Buildkite GPG key / repo setup failure ───────────
            # The apt install requires adding the Buildkite-hosted
            # Helm Debian repo + GPG key. This can fail due to
            # network issues reaching packages.buildkite.com, GPG
            # import errors, or permission issues writing keyrings.
            {
                "pattern": (
                    r"gpg:.*keyserver receive failed|"
                    r"gpg:.*no valid OpenPGP data|"
                    r"Could not resolve host.*packages\.buildkite\.com|"
                    r"helm\.gpg.*Permission denied|"
                    r"Failed to fetch.*buildkite\.com|"
                    r"Unable to connect to.*buildkite\.com"
                ),
                "failure_id": "helm_gpg_repo_setup_failed",
                "category": "configuration",
                "label": "Helm apt repository setup failed",
                "description": (
                    "The Helm apt install requires adding the Buildkite-"
                    "hosted Debian repository and GPG signing key. This "
                    "setup step failed — likely due to network issues "
                    "reaching packages.buildkite.com, GPG import errors, "
                    "or permission problems writing the keyring file."
                ),
                "example_stderr": (
                    "Could not resolve host: packages.buildkite.com"
                ),
                "options": [
                    {
                        "id": "switch-to-default-installer",
                        "label": "Use official get-helm-3 installer script",
                        "description": (
                            "Run the official Helm installer script which "
                            "downloads the binary directly from GitHub "
                            "releases. Bypasses the apt repo entirely."
                        ),
                        "icon": "📥",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "_default",
                        "risk": "low",
                    },
                    {
                        "id": "switch-to-brew",
                        "label": "Install via Homebrew",
                        "description": (
                            "Use Homebrew to install Helm. No GPG key "
                            "or repository configuration needed."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                        "risk": "low",
                    },
                ],
            },

            # ── Package not found (repo not configured) ──────────
            # apt can't find 'helm' because the Buildkite repo
            # wasn't added. This happens when the user tries to
            # update helm via apt without the initial repo setup.
            {
                "pattern": (
                    r"Unable to locate package helm|"
                    r"Package 'helm' has no installation candidate|"
                    r"E: Package 'helm' has no installation candidate"
                ),
                "failure_id": "helm_repo_not_configured",
                "category": "configuration",
                "label": "Helm apt repository not configured",
                "description": (
                    "The system package manager cannot find the 'helm' "
                    "package. Helm requires adding the Buildkite-hosted "
                    "Debian repository before it can be installed via "
                    "apt. The repository may not have been set up, or "
                    "it may have been removed."
                ),
                "example_stderr": (
                    "E: Unable to locate package helm"
                ),
                "options": [
                    {
                        "id": "switch-to-default-installer",
                        "label": "Use official get-helm-3 installer script",
                        "description": (
                            "Run the official Helm installer script which "
                            "downloads the binary directly from GitHub. "
                            "No repository setup required."
                        ),
                        "icon": "📥",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "_default",
                        "risk": "low",
                    },
                    {
                        "id": "switch-to-snap",
                        "label": "Install via Snap",
                        "description": (
                            "Use Snap which handles Helm availability "
                            "without requiring repository configuration."
                        ),
                        "icon": "📦",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "snap",
                        "risk": "low",
                    },
                ],
            },
]


_KUBECTL_HANDLERS: list[dict] = [
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
]
