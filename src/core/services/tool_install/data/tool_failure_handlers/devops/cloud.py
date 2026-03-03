"""
L0 Data — Cloud / platform tool-specific failure handlers.

Tools: gh (GitHub CLI), terraform
Pure data, no logic.
"""

from __future__ import annotations


_GH_INSTALL_HANDLERS: list[dict] = [
            # ── GPG key / repo setup failure ─────────────────────
            # The apt/dnf/zypper install requires adding GitHub's
            # official repo + GPG key. This can fail due to network
            # issues reaching cli.github.com, GPG import errors,
            # or permission issues writing to /etc/apt/keyrings.
            {
                "pattern": (
                    r"gpg:.*keyserver receive failed|"
                    r"gpg:.*no valid OpenPGP data|"
                    r"Could not resolve host.*cli\.github\.com|"
                    r"githubcli-archive-keyring.*Permission denied|"
                    r"Failed to add repository.*gh-cli\.repo|"
                    r"Error:.*adding repo.*cli\.github\.com"
                ),
                "failure_id": "gh_gpg_repo_setup_failed",
                "category": "configuration",
                "label": "GitHub CLI repository setup failed",
                "description": (
                    "The GitHub CLI apt/dnf/zypper install requires adding "
                    "GitHub's official package repository and GPG signing "
                    "key. This setup step failed — likely due to network "
                    "issues reaching cli.github.com, GPG import errors, or "
                    "permission problems writing to /etc/apt/keyrings."
                ),
                "example_stderr": (
                    "Could not resolve host: cli.github.com"
                ),
                "options": [
                    {
                        "id": "switch-to-default-binary",
                        "label": "Download pre-compiled binary from GitHub releases",
                        "description": (
                            "Download the gh binary directly from GitHub "
                            "releases. This bypasses the repo setup entirely."
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
                            "Use Homebrew to install gh. No GPG key or "
                            "repo configuration needed."
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
            # apt/dnf/zypper can't find 'gh' because the GitHub CLI
            # repo wasn't added. This happens when users try the
            # update command without having done the initial setup,
            # or when the repo was removed.
            {
                "pattern": (
                    r"Unable to locate package gh|"
                    r"No match for argument.*['\"]?gh['\"]?|"
                    r"Package 'gh' has no installation candidate|"
                    r"E: Package 'gh' has no installation candidate"
                ),
                "failure_id": "gh_repo_not_configured",
                "category": "configuration",
                "label": "GitHub CLI package repository not configured",
                "description": (
                    "The system package manager cannot find the 'gh' "
                    "package. The GitHub CLI requires adding GitHub's "
                    "official repository before it can be installed via "
                    "apt or dnf. The repository may not have been set up, "
                    "or it may have been removed."
                ),
                "example_stderr": (
                    "E: Unable to locate package gh"
                ),
                "options": [
                    {
                        "id": "switch-to-default-binary",
                        "label": "Download pre-compiled binary from GitHub releases",
                        "description": (
                            "Download the gh binary directly from GitHub "
                            "releases. No repository setup required."
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
                            "Use Homebrew which handles gh availability "
                            "without requiring repository configuration."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                        "risk": "low",
                    },
                ],
            },
]

_GH_HANDLERS: list[dict] = _GH_INSTALL_HANDLERS + [
            # ── gh config migration failure (v2.40+ multi-account) ──
            # gh CLI v2.40+ introduced multi-account support and tries
            # to migrate old config format to new format. During
            # migration, it calls the GitHub API to look up the
            # username. If the API is unreachable (DNS failure, VM
            # network restrictions), migration fails and ALL gh
            # commands break with:
            #   "failed to migrate config: cowardly refusing to
            #    continue with multi account migration"
            # This is NOT an install failure — gh is installed and
            # the binary works. The config file is the problem.
            {
                "pattern": (
                    r"failed to migrate config.*multi account migration|"
                    r"cowardly refusing to continue.*multi account|"
                    r"couldn't get user name.*github\.com"
                ),
                "failure_id": "gh_config_migration_failed",
                "category": "configuration",
                "label": "GitHub CLI config migration failed",
                "description": (
                    "The GitHub CLI v2.40+ tries to migrate your config "
                    "to the new multi-account format. During migration, "
                    "it calls the GitHub API to look up your username. "
                    "If the API is unreachable (DNS issues, restricted VM "
                    "network), migration fails and ALL gh commands break. "
                    "The fix is to reset the config so gh can start fresh."
                ),
                "example_stderr": (
                    "failed to migrate config: cowardly refusing to "
                    "continue with multi account migration: couldn't "
                    "get user name for \"github.com\""
                ),
                "options": [
                    {
                        "id": "reset-gh-config",
                        "label": "Reset gh config (back up and recreate)",
                        "description": (
                            "Back up the current hosts.yml to "
                            "hosts.yml.bak, then delete it so gh can "
                            "start with a fresh config. You will need "
                            "to re-authenticate after this."
                        ),
                        "icon": "🔄",
                        "recommended": True,
                        "strategy": "run_command",
                        "command": [
                            "bash", "-c",
                            "GH_DIR=${GH_CONFIG_DIR:-$HOME/.config/gh}"
                            " && cp -f \"$GH_DIR/hosts.yml\""
                            " \"$GH_DIR/hosts.yml.bak\" 2>/dev/null;"
                            " rm -f \"$GH_DIR/hosts.yml\""
                            " && echo 'Config reset. Ready for re-auth.'",
                        ],
                        "risk": "low",
                    },
                    {
                        "id": "use-device-flow",
                        "label": "Re-authenticate via Browser Auth",
                        "description": (
                            "Use the browser-based device flow to "
                            "authenticate. This creates a fresh token "
                            "and writes a clean config, bypassing the "
                            "migration entirely."
                        ),
                        "icon": "🌐",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "Use the Browser Auth option in the GitHub "
                            "integration card to re-authenticate."
                        ),
                        "risk": "low",
                    },
                ],
            },
]


_TERRAFORM_HANDLERS: list[dict] = [
            # ── HashiCorp GPG key / apt repo setup failed ────────
            # The apt method adds HashiCorp's GPG key and repo.
            # If gpg --dearmor fails, or the keyring can't be
            # written, or the sources list can't be created, the
            # whole multi-step install chain breaks.
            {
                "pattern": (
                    r"gpg:.*keyserver receive failed|"
                    r"gpg:.*no valid OpenPGP data|"
                    r"Could not resolve host.*hashicorp|"
                    r"hashicorp-archive-keyring.*Permission denied|"
                    r"tee.*hashicorp.*Permission denied|"
                    r"The following signatures couldn't be verified|"
                    r"NO_PUBKEY.*hashicorp"
                ),
                "failure_id": "terraform_gpg_repo_setup_failed",
                "category": "configuration",
                "label": "HashiCorp repository setup failed",
                "description": (
                    "The HashiCorp apt/dnf repository could not be "
                    "configured. This typically happens when the GPG "
                    "signing key cannot be downloaded or imported, or "
                    "when the system cannot resolve "
                    "apt.releases.hashicorp.com. The safest fallback "
                    "is to download the binary directly."
                ),
                "example_stderr": (
                    "gpg: no valid OpenPGP data found.\n"
                    "gpg: Total number processed: 0"
                ),
                "options": [
                    {
                        "id": "use-binary-download",
                        "label": "Download Terraform binary directly",
                        "description": (
                            "Download the pre-compiled Terraform binary "
                            "from releases.hashicorp.com. This bypasses "
                            "the repository configuration entirely."
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
                            "Use snap to install Terraform. No external "
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

            # ── HashiCorp repo not configured ────────────────────
            # On fresh systems, apt/dnf won't find 'terraform'
            # because the HashiCorp repository is not added by
            # default. The generic apt_stale_index / dnf_no_match
            # handlers fire the detection, but the user needs to
            # know the fix is HashiCorp-specific: either re-run
            # the full multi-step apt command, or use _default.
            {
                "pattern": (
                    r"Unable to locate package terraform|"
                    r"No match for argument.*terraform|"
                    r"Package 'terraform' has no installation candidate|"
                    r"terraform.*not found in package names"
                ),
                "failure_id": "terraform_repo_not_configured",
                "category": "configuration",
                "label": "HashiCorp package repository not configured",
                "description": (
                    "The terraform package is not available in the "
                    "default system repositories. Terraform requires "
                    "adding the official HashiCorp package repository "
                    "(apt.releases.hashicorp.com or "
                    "rpm.releases.hashicorp.com) before installation "
                    "via apt or dnf."
                ),
                "example_stderr": (
                    "E: Unable to locate package terraform"
                ),
                "options": [
                    {
                        "id": "use-binary-download",
                        "label": "Download Terraform binary directly",
                        "description": (
                            "Download the pre-compiled Terraform binary "
                            "from releases.hashicorp.com. This is the "
                            "most reliable method and does not require "
                            "repository configuration."
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
                            "Use snap to install Terraform. Requires "
                            "snapd but no external repository setup."
                        ),
                        "icon": "📦",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "snap",
                        "risk": "low",
                    },
                ],
            },

            # ── Checkpoint API unreachable ───────────────────────
            # The _default install queries HashiCorp's checkpoint
            # API to discover the latest version. If this fails
            # (DNS, corporate firewall, API down), the whole
            # install chain breaks at the first step.
            {
                "pattern": (
                    r"checkpoint\.hashicorp\.com.*Failed to connect|"
                    r"checkpoint\.hashicorp\.com.*Could not resolve|"
                    r"checkpoint\.hashicorp\.com.*Connection refused|"
                    r"Traceback.*json\.decoder\.JSONDecodeError|"
                    r"current_version.*KeyError|"
                    r"TF_VERSION=\s*$"
                ),
                "failure_id": "terraform_checkpoint_api_failed",
                "category": "network",
                "label": "HashiCorp version discovery API unreachable",
                "description": (
                    "The Terraform _default install method queries "
                    "checkpoint.hashicorp.com to find the latest "
                    "version. This API is unreachable — possibly due "
                    "to DNS failure, firewall rules, or the service "
                    "being temporarily down. You can work around "
                    "this by specifying the version manually or "
                    "using a package manager instead."
                ),
                "example_stderr": (
                    "curl: (6) Could not resolve host: "
                    "checkpoint.hashicorp.com"
                ),
                "options": [
                    {
                        "id": "use-snap",
                        "label": "Install via snap instead",
                        "description": (
                            "Use snap to install Terraform. Does not "
                            "require access to checkpoint.hashicorp.com."
                        ),
                        "icon": "📦",
                        "recommended": True,
                        "strategy": "switch_method",
                        "method": "snap",
                        "risk": "low",
                    },
                    {
                        "id": "use-brew",
                        "label": "Install via Homebrew",
                        "description": (
                            "Use Homebrew to install Terraform. "
                            "Handles version resolution internally."
                        ),
                        "icon": "🍺",
                        "recommended": False,
                        "strategy": "switch_method",
                        "method": "brew",
                        "risk": "low",
                    },
                    {
                        "id": "manual-version",
                        "label": "Specify version manually",
                        "description": (
                            "Download Terraform by specifying the "
                            "version yourself, bypassing the "
                            "checkpoint API."
                        ),
                        "icon": "📝",
                        "recommended": False,
                        "strategy": "manual",
                        "instructions": (
                            "1. Find the latest version at: "
                            "https://releases.hashicorp.com/terraform/\n"
                            "2. Download: curl -sSfL -o /tmp/terraform.zip "
                            "\"https://releases.hashicorp.com/terraform/"
                            "<VERSION>/terraform_<VERSION>_linux_amd64.zip\"\n"
                            "3. Extract: sudo unzip -o /tmp/terraform.zip "
                            "-d /usr/local/bin\n"
                            "4. Clean up: rm /tmp/terraform.zip"
                        ),
                        "risk": "low",
                    },
                ],
            },
]
