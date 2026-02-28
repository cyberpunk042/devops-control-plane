"""
L0 Data — Security scanner tool-specific failure handlers.

Tools: trivy
Pure data, no logic.
"""

from __future__ import annotations


_TRIVY_HANDLERS: list[dict] = [
            # ── Aqua Security GPG key / repo setup failure ───────
            # The apt/dnf install requires adding Aqua Security's
            # repository and GPG key. This can fail due to network
            # issues reaching aquasecurity.github.io, GPG import
            # errors, or permission issues.
            {
                "pattern": (
                    r"gpg:.*keyserver receive failed|"
                    r"gpg:.*no valid OpenPGP data|"
                    r"Could not resolve host.*aquasecurity\.github\.io|"
                    r"trivy\.gpg.*Permission denied|"
                    r"Failed to fetch.*aquasecurity\.github\.io|"
                    r"Unable to connect to.*aquasecurity\.github\.io|"
                    r"Cannot download.*trivy-repo"
                ),
                "failure_id": "trivy_gpg_repo_setup_failed",
                "category": "configuration",
                "label": "Trivy repository setup failed",
                "description": (
                    "The Trivy install requires adding Aqua Security's "
                    "package repository and GPG signing key. This setup "
                    "step failed — likely due to network issues reaching "
                    "aquasecurity.github.io, GPG import errors, or "
                    "permission problems writing the keyring/repo file."
                ),
                "example_stderr": (
                    "Could not resolve host: aquasecurity.github.io"
                ),
                "options": [
                    {
                        "id": "switch-to-default-installer",
                        "label": "Use official Trivy installer script",
                        "description": (
                            "Run the official Trivy install.sh script "
                            "which downloads the binary directly from "
                            "GitHub releases. Bypasses the apt/dnf repo."
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
                            "Use Homebrew to install Trivy. No GPG key "
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
            # apt/dnf can't find 'trivy' because the Aqua Security
            # repo wasn't added or was removed.
            {
                "pattern": (
                    r"Unable to locate package trivy|"
                    r"Package 'trivy' has no installation candidate|"
                    r"No match for argument.*trivy"
                ),
                "failure_id": "trivy_repo_not_configured",
                "category": "configuration",
                "label": "Trivy repository not configured",
                "description": (
                    "The system package manager cannot find the 'trivy' "
                    "package. Trivy requires adding Aqua Security's "
                    "package repository before it can be installed via "
                    "apt or dnf. The repository may not have been set "
                    "up, or it may have been removed."
                ),
                "example_stderr": (
                    "E: Unable to locate package trivy"
                ),
                "options": [
                    {
                        "id": "switch-to-default-installer",
                        "label": "Use official Trivy installer script",
                        "description": (
                            "Run the official Trivy install.sh script "
                            "which downloads the binary directly from "
                            "GitHub. No repository setup required."
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
                            "Use Snap which handles Trivy availability "
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
