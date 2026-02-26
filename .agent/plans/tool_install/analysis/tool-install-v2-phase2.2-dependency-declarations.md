# Phase 2.2 — Dependency Declarations & Recipe Unification — Full Analysis

## What This Sub-Phase Delivers

Replace `_NO_SUDO_RECIPES`, `_SUDO_RECIPES`, `CARGO_BUILD_DEPS`,
`_RUNTIME_DEPS`, and `_TOOL_REQUIRES` with a single `TOOL_RECIPES` dict
that covers the FULL tool lifecycle:

- **Install** — per-platform commands, dependency declarations, sudo flags
- **Post-install** — service start/enable, group membership, PATH setup, config
- **Verify** — confirm the tool is functional after install
- **Update** — per-method upgrade commands
- **Repo setup** — GPG key import + source list for tools not in default repos

---

## 1. What Gets Replaced — Exact Inventory

### 1.1 `_NO_SUDO_RECIPES` (lines 34-46)

11 entries, 3 install types:

| Tool | Type | Command |
|------|------|---------|
| ruff | pip | `[sys.executable, "-m", "pip", "install", "ruff"]` |
| mypy | pip | `[sys.executable, "-m", "pip", "install", "mypy"]` |
| pytest | pip | `[sys.executable, "-m", "pip", "install", "pytest"]` |
| black | pip | `[sys.executable, "-m", "pip", "install", "black"]` |
| pip-audit | pip | `[sys.executable, "-m", "pip", "install", "pip-audit"]` |
| safety | pip | `[sys.executable, "-m", "pip", "install", "safety"]` |
| bandit | pip | `[sys.executable, "-m", "pip", "install", "bandit"]` |
| eslint | npm | `["npm", "install", "-g", "eslint"]` |
| prettier | npm | `["npm", "install", "-g", "prettier"]` |
| cargo-audit | cargo | `["cargo", "install", "cargo-audit"]` |
| cargo-outdated | cargo | `["cargo", "install", "cargo-outdated"]` |

**What's missing from these entries:**
- eslint/prettier don't declare they need `npm` binary → the dep check
  in `install_tool()` catches this by inspecting `cmd[0]`, but it's implicit
- cargo-audit/cargo-outdated don't declare they need `cargo` binary →
  caught by `_TOOL_REQUIRES` (separate dict)
- cargo-audit/cargo-outdated don't declare system packages → only
  surfaces when compilation fails (post-failure in `_analyse_install_failure`)

### 1.2 `_SUDO_RECIPES` (lines 49-83)

31 entries, 4 install methods:

**apt-get tools (18):**

| Tool | Package name | Notes |
|------|-------------|-------|
| docker | docker.io | Debian name. RHEL: `docker` or docker-ce repo. Alpine: `docker` |
| docker-compose | docker-compose-v2 | Debian name. RHEL: `docker-compose-plugin`. Alpine: `docker-compose` |
| git | git | Same across all distros |
| ffmpeg | ffmpeg | Debian/Alpine/Arch: `ffmpeg`. RHEL: `ffmpeg-free` (rpmfusion needed for full) |
| gzip | gzip | Same across all distros |
| curl | curl | Same across all distros |
| jq | jq | Same across all distros |
| make | make | Same across all distros |
| python | python3 | Debian/RHEL/Alpine: `python3`. Arch: `python`. Brew: `python@3` |
| pip | python3-pip | Debian: `python3-pip`. RHEL: `python3-pip`. Alpine: `py3-pip`. Arch: `python-pip` |
| npm | npm | Debian/RHEL/Alpine: `npm`. Brew: comes with `node` |
| npx | npm | Same package as npm (npx is bundled). RHEL/Alpine: same |
| dig | dnsutils | Debian: `dnsutils`. RHEL: `bind-utils`. Alpine: `bind-tools`. Arch: `bind`. Brew: `bind` |
| openssl | openssl | Same across all distros |
| rsync | rsync | Same across all distros |
| xterm | xterm | Desktop Linux only. Same name on RHEL/Arch |
| gnome-terminal | gnome-terminal | Desktop Linux only. Same name on RHEL/Arch |
| xfce4-terminal | xfce4-terminal | Desktop Linux only. Same name on RHEL/Arch |
| konsole | konsole | Desktop Linux only. Same name on RHEL |
| kitty | kitty | Desktop Linux. Brew: `brew install --cask kitty` |
| expect | expect | Same across all distros |

**snap tools (5):**

| Tool | Snap command | What to do without snap |
|------|-------------|------------------------|
| kubectl | `snap install kubectl --classic` | Binary download OR apt repo OR dnf repo OR brew |
| terraform | `snap install terraform --classic` | brew, or binary download from HashiCorp |
| node | `snap install node --classic` | apt `nodejs`, dnf `nodejs`, apk `nodejs`, brew `node` |
| go | `snap install go --classic` | apt `golang-go`, dnf `golang`, apk `go`, brew `go` |
| gh | `snap install gh` | brew `gh`, or GitHub apt repo |

**bash-curl tools (4):**

| Tool | Script URL | Needs curl? | Needs sudo? |
|------|-----------|-------------|-------------|
| helm | `https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3` | YES | YES (writes to /usr/local/bin) |
| trivy | `https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh` | YES | YES (writes to /usr/local/bin) |
| cargo/rustc | `https://sh.rustup.rs` | YES | NO (installs to ~/.cargo) |
| skaffold | Direct binary download from storage.googleapis.com | YES | YES (writes to /usr/local/bin) |

**Important:** cargo/rustc is categorized as `install_type: "sudo"` in
`_SUDO_RECIPES` but the recipe itself does NOT need sudo (installs to
`~/.cargo`). This is a BUG in the current system — cargo is in the sudo
dict even though it doesn't need sudo. The `_TOOLS` registry also marks
it as `install_type: "sudo"`. This means the frontend shows a password
prompt for cargo, but the password is unnecessary.

### 1.3 `CARGO_BUILD_DEPS` (line 88)

```python
CARGO_BUILD_DEPS = ["pkg-config", "libssl-dev", "libcurl4-openssl-dev"]
```

These are Debian package names. The SAME libraries have different names
on each distro:

| Library | Debian | RHEL/Fedora | Alpine | Arch | SUSE | Brew |
|---------|--------|-------------|--------|------|------|------|
| pkg-config | pkg-config | pkgconf-pkg-config | pkgconf | pkgconf | pkg-config | pkg-config |
| OpenSSL dev | libssl-dev | openssl-devel | openssl-dev | openssl | libopenssl-devel | openssl@3 |
| libcurl dev | libcurl4-openssl-dev | libcurl-devel | curl-dev | curl | libcurl-devel | curl |

`CARGO_BUILD_DEPS` is referenced in `_analyse_install_failure()` on
lines 159, 171, 209 as `system_deps` field. The frontend uses this to
pre-check whether those packages are installed before running a
remediation option.

In the new system, this becomes part of each cargo tool's recipe under
`requires.packages`, keyed by distro family.

### 1.4 `_RUNTIME_DEPS` (lines 354-358)

```python
_RUNTIME_DEPS: dict[str, dict[str, str]] = {
    "cargo":  {"tool": "cargo",  "label": "Cargo (Rust)"},
    "npm":    {"tool": "npm",    "label": "npm"},
    "node":   {"tool": "node",   "label": "Node.js"},
}
```

This maps runtime binaries to their tool info. Used by the dep pre-check
in `install_tool()` to detect when a binary dep is missing.

In the new system, this becomes `requires.binaries` in each recipe.

### 1.5 `_TOOL_REQUIRES` (lines 360-363)

```python
_TOOL_REQUIRES: dict[str, str] = {
    "cargo-audit": "cargo",
    "cargo-outdated": "cargo",
}
```

Maps tools to their runtime binary when the recipe is wrapped in `bash -c`
(so `cmd[0]` is "bash", not "cargo"). Exists because the generic dep
check inspects `cmd[0]` which doesn't work for wrapped commands.

In the new system, this becomes `requires.binaries: ["cargo"]` in each recipe.

---

## 2. The Recipe Format

### 2.1 Complete Specification

```python
{
    "label": str,
    # Human-readable name. Required.
    # Source: matches the "label" field in _TOOLS registry.

    "cli": str,
    # Binary name to check with shutil.which().
    # Optional. Defaults to the tool ID (the dict key).
    # Only needed when tool ID ≠ binary name.
    # Example: tool "python" → cli "python3".

    "install": dict[str, list[str]],
    # Install commands keyed by package manager or method.
    #
    # Keys:
    #   "apt", "dnf", "yum", "apk", "pacman", "zypper", "brew"
    #     → system package manager commands
    #   "snap"
    #     → snap install command (requires systemd)
    #   "_default"
    #     → works on any system (pip, cargo, bash-curl scripts)
    #
    # Values: command list for subprocess.run()
    #
    # A recipe MUST have at least one key.
    # A recipe CAN have multiple keys (platform variants).
    #
    # Resolution order (in the resolver, Phase 2.3):
    #   1. Recipe's "prefer" list (if present)
    #   2. System's primary package manager
    #   3. snap (if snap_available)
    #   4. "_default" fallback

    "needs_sudo": dict[str, bool],
    # Per-method sudo requirement. Keys match "install" keys.
    # Required. Must cover every key in "install".
    #
    # Rule of thumb:
    #   apt/dnf/yum/apk/pacman/zypper/snap → True
    #   brew → False
    #   _default pip/cargo → False
    #   _default bash-curl to /usr/local/bin → True
    #   _default bash-curl to ~/.cargo → False

    "requires": {
        # Optional. Defaults to {}.

        "binaries": list[str],
        # Tool IDs that must be on PATH before this tool can install.
        # These are resolved RECURSIVELY by the resolver (Phase 2.3).
        #
        # Examples:
        #   cargo-audit requires ["cargo"]
        #   cargo requires ["curl"]
        #   eslint requires ["npm"]
        #
        # The resolver walks this tree depth-first:
        #   cargo-outdated → cargo → curl
        # and produces steps in dependency order.

        "packages": dict[str, list[str]],
        # System packages needed for compilation/linking.
        # Keyed by distro FAMILY (not package manager).
        #
        # Keys: "debian", "rhel", "alpine", "arch", "suse", "macos"
        #
        # The resolver uses the family from Phase 1's system profile
        # to look up the right package names, then uses
        # _build_pkg_install_cmd() from Phase 2.1 to build the command.
        #
        # Example for cargo-outdated:
        #   "debian": ["pkg-config", "libssl-dev", "libcurl4-openssl-dev"]
        #   "rhel":   ["pkgconf-pkg-config", "openssl-devel", "libcurl-devel"]
        #   "alpine": ["pkgconf", "openssl-dev", "curl-dev"]
    },

    "prefer": list[str],
    # Optional. Ordered list of preferred install method keys.
    # The resolver tries these FIRST, then falls back to the
    # system's primary pm, then snap, then _default.
    #
    # Example: kubectl prefers ["snap", "brew", "_default"]
    # On a system with snap: uses snap.
    # On macOS with brew: uses brew.
    # On Alpine (no snap, no brew): uses _default (binary download).

    "post_env": str,
    # Optional. Shell commands to set environment after install.
    # Used for tools that install to non-standard paths.
    #
    # Only cargo/rustc use this:
    #   'export PATH="$HOME/.cargo/bin:$PATH"'
    #
    # The resolver (Phase 2.3) prepends this to LATER steps that
    # depend on this tool's binary when that binary wasn't on PATH
    # at resolution time.

    "post_install": list[dict],
    # Optional. Ordered steps to run AFTER the install command succeeds.
    # Each step is a dict:
    #   {
    #     "label": str,          Human-readable description
    #     "command": list[str],   subprocess.run() command
    #     "needs_sudo": bool,     Does this step need sudo?
    #     "condition": str,       Optional. When to run:
    #                             "has_systemd" — only on systems with systemd
    #                             "not_root" — only when not running as root
    #                             "not_container" — skip in containers
    #                             None — always run
    #   }
    #
    # Examples:
    #   Docker:
    #     {"label": "Start Docker",
    #      "command": ["systemctl", "start", "docker"],
    #      "needs_sudo": True,
    #      "condition": "has_systemd"}
    #     {"label": "Enable Docker on boot",
    #      "command": ["systemctl", "enable", "docker"],
    #      "needs_sudo": True,
    #      "condition": "has_systemd"}
    #     {"label": "Add user to docker group",
    #      "command": ["bash", "-c", "usermod -aG docker $USER"],
    #      "needs_sudo": True,
    #      "condition": "not_root"}
    #
    #   Cargo:
    #     (uses post_env instead — PATH export, not a command)

    "verify": list[str],
    # Optional. Command to run after install (and post_install) to
    # confirm the tool is functional.
    #
    # Should be a fast, non-destructive command. Exit code 0 = success.
    #
    # Examples:
    #   git   → ["git", "--version"]
    #   docker → ["docker", "info"]  (needs daemon running)
    #   cargo → ["bash", "-c",
    #            'export PATH="$HOME/.cargo/bin:$PATH" && cargo --version']
    #   trivy → ["trivy", "--version"]
    #
    # If verify fails, the plan's final status should warn that the
    # install command succeeded but the tool isn't functional yet.

    "update": dict[str, list[str]],
    # Optional. Per-method update commands. Keys match "install" keys.
    #
    # Examples:
    #   pip tool:     {"_default": _PIP + ["install", "--upgrade", "ruff"]}
    #   npm tool:     {"_default": ["npm", "update", "-g", "eslint"]}
    #   cargo tool:   {"_default": ["cargo", "install", "cargo-audit"]}
    #   apt package:  {"apt": ["apt-get", "install", "--only-upgrade", "-y", "git"]}
    #   snap package: {"snap": ["snap", "refresh", "kubectl"]}
    #   brew formula: {"brew": ["brew", "upgrade", "helm"]}
    #   cargo/rustc:  {"_default": ["rustup", "update"]}
    #
    # The frontend can show an "Update" button when the tool is
    # installed but outdated. The resolver picks the right update
    # command based on the install method that was originally used.

    "repo_setup": dict[str, list[dict]],
    # Optional. Per-pm repo configuration steps that must run
    # BEFORE the install command.
    #
    # Keys match package manager IDs: "apt", "dnf", etc.
    # Values are ordered lists of setup steps:
    #   {
    #     "label": str,
    #     "command": list[str],
    #     "needs_sudo": bool,
    #   }
    #
    # Example for Docker CE on Debian:
    #   "apt": [
    #     {"label": "Install prerequisites",
    #      "command": ["apt-get", "install", "-y",
    #                  "ca-certificates", "curl", "gnupg"],
    #      "needs_sudo": True},
    #     {"label": "Add Docker GPG key",
    #      "command": ["bash", "-c",
    #                  "curl -fsSL https://download.docker.com/linux/ubuntu/gpg"
    #                  " | gpg --dearmor -o /usr/share/keyrings/docker.gpg"],
    #      "needs_sudo": True},
    #     {"label": "Add Docker apt repository",
    #      "command": ["bash", "-c",
    #                  'echo "deb [signed-by=/usr/share/keyrings/docker.gpg]'
    #                  ' https://download.docker.com/linux/ubuntu'
    #                  ' $(lsb_release -cs) stable"'
    #                  ' | tee /etc/apt/sources.list.d/docker.list'],
    #      "needs_sudo": True},
    #     {"label": "Update package index",
    #      "command": ["apt-get", "update"],
    #      "needs_sudo": True},
    #   ]
    #
    # The resolver (Phase 2.3) runs these steps BEFORE the install
    # command. They are only needed when the tool isn't available
    # in the default system repos.
    #
    # Tools that need repo_setup:
    #   docker (Docker CE official repo — if we want docker-ce instead of docker.io)
    #   gh (GitHub CLI repo)
    #   terraform (HashiCorp repo — alternative to snap)
    #   kubectl (Kubernetes repo — alternative to snap/binary)
    #
    # NOTE: For Phase 2.2 we document the repo_setup structure but
    # only POPULATE it for tools where we actually use the official
    # repo method. Docker currently uses docker.io (community package),
    # kubectl uses snap/binary, etc. Repo setup will be populated
    # as we add more install method variants.
}
```

### 2.2 Relationship Between `install` Keys and Distro Family

These are TWO DIFFERENT concepts:

- `install` keys = which COMMAND to use (apt-get vs dnf vs apk)
- `requires.packages` keys = which NAMES to use (libssl-dev vs openssl-devel)

They're related but not identical:

| Distro family | Primary PM | `install` key | `requires.packages` key |
|--------------|-----------|---------------|------------------------|
| debian | apt | "apt" | "debian" |
| rhel | dnf (or yum) | "dnf" (or "yum") | "rhel" |
| alpine | apk | "apk" | "alpine" |
| arch | pacman | "pacman" | "arch" |
| suse | zypper | "zypper" | "suse" |
| macos | brew | "brew" | "macos" |

The PM is for commands. The family is for package names.
Phase 1's system profile gives us both.

---

## 3. Every Tool — Complete Cross-Platform Analysis

### Category 1: pip tools (7 tools)

These are the SIMPLEST recipes. `pip install` works on ANY platform
because Python/pip is the prerequisite for this entire application.
The app runs in a venv, so `sys.executable -m pip install` always works.

| Tool | Install command | Needs sudo | Requires | Platform variance |
|------|----------------|-----------|----------|-------------------|
| ruff | `_PIP + ["install", "ruff"]` | No | — | NONE |
| mypy | `_PIP + ["install", "mypy"]` | No | — | NONE |
| pytest | `_PIP + ["install", "pytest"]` | No | — | NONE |
| black | `_PIP + ["install", "black"]` | No | — | NONE |
| pip-audit | `_PIP + ["install", "pip-audit"]` | No | — | NONE |
| safety | `_PIP + ["install", "safety"]` | No | — | NONE |
| bandit | `_PIP + ["install", "bandit"]` | No | — | NONE |

**Lifecycle:**
- **Post-install:** None needed
- **Verify:** `_PIP + ["show", "TOOL_NAME"]` — confirms package is in the venv
- **Update:** `_PIP + ["install", "--upgrade", "TOOL_NAME"]`
- **Repo setup:** None needed

Recipe pattern (all 7 identical except name):
```python
"ruff": {
    "label": "Ruff",
    "install": {"_default": _PIP + ["install", "ruff"]},
    "needs_sudo": {"_default": False},
    "verify": ["ruff", "--version"],
    "update": {"_default": _PIP + ["install", "--upgrade", "ruff"]},
},
```

No `requires` needed — the app is running in Python, so pip is available.

### Category 2: npm tools (2 tools)

These need the `npm` binary on PATH. `npm install -g` works the same
on every platform once npm is available.

| Tool | Install command | Needs sudo | Requires |
|------|----------------|-----------|----------|
| eslint | `["npm", "install", "-g", "eslint"]` | No | npm binary |
| prettier | `["npm", "install", "-g", "prettier"]` | No | npm binary |

**Note on sudo:** `npm install -g` on Linux sometimes needs sudo if the
global npm prefix is `/usr/lib` (system npm). If npm was installed via
`nvm` or `snap`, it uses a user-writable prefix and doesn't need sudo.
The current system marks these as no-sudo, and the `EACCES` error
analysis handles the permission case post-failure. We keep this behavior.

**Lifecycle:**
- **Post-install:** None needed
- **Verify:** `["eslint", "--version"]`
- **Update:** `["npm", "update", "-g", "eslint"]`
- **Repo setup:** None needed

Recipe pattern:
```python
"eslint": {
    "label": "ESLint",
    "install": {"_default": ["npm", "install", "-g", "eslint"]},
    "needs_sudo": {"_default": False},
    "requires": {"binaries": ["npm"]},
    "verify": ["eslint", "--version"],
    "update": {"_default": ["npm", "update", "-g", "eslint"]},
},
```

### Category 3: cargo tools (2 tools)

These need the `cargo` binary AND system dev packages for compilation.

| Tool | Install command | Needs sudo | Requires binaries | Requires packages |
|------|----------------|-----------|-------------------|-------------------|
| cargo-audit | `["cargo", "install", "cargo-audit"]` | No | cargo | openssl dev headers |
| cargo-outdated | `["cargo", "install", "cargo-outdated"]` | No | cargo | openssl + curl dev headers |

System package mapping:

**cargo-audit** (needs openssl):

| Family | Packages |
|--------|----------|
| debian | `["pkg-config", "libssl-dev"]` |
| rhel | `["pkgconf-pkg-config", "openssl-devel"]` |
| alpine | `["pkgconf", "openssl-dev"]` |
| arch | `["pkgconf", "openssl"]` |
| suse | `["pkg-config", "libopenssl-devel"]` |
| macos | `["pkg-config", "openssl@3"]` |

**cargo-outdated** (needs openssl + libcurl):

| Family | Packages |
|--------|----------|
| debian | `["pkg-config", "libssl-dev", "libcurl4-openssl-dev"]` |
| rhel | `["pkgconf-pkg-config", "openssl-devel", "libcurl-devel"]` |
| alpine | `["pkgconf", "openssl-dev", "curl-dev"]` |
| arch | `["pkgconf", "openssl", "curl"]` |
| suse | `["pkg-config", "libopenssl-devel", "libcurl-devel"]` |
| macos | `["pkg-config", "openssl@3", "curl"]` |

**Lifecycle:**
- **Post-install:** None needed
- **Verify:** `["cargo", "audit", "--version"]` (cargo-audit) /
  `["cargo", "outdated", "--version"]` (cargo-outdated)
- **Update:** `["cargo", "install", "cargo-audit"]` — cargo install
  re-installs latest by default. Same command as install.
- **Repo setup:** None needed

Recipe pattern:
```python
"cargo-audit": {
    "label": "cargo-audit",
    "install": {"_default": ["cargo", "install", "cargo-audit"]},
    "needs_sudo": {"_default": False},
    "requires": {
        "binaries": ["cargo"],
        "packages": {
            "debian": ["pkg-config", "libssl-dev"],
            "rhel":   ["pkgconf-pkg-config", "openssl-devel"],
            "alpine": ["pkgconf", "openssl-dev"],
            "arch":   ["pkgconf", "openssl"],
            "suse":   ["pkg-config", "libopenssl-devel"],
            "macos":  ["pkg-config", "openssl@3"],
        },
    },
    "verify": ["cargo", "audit", "--version"],
    "update": {"_default": ["cargo", "install", "cargo-audit"]},
},
```

### Category 4: Runtimes installed via bash-curl (2 tools)

| Tool | Script | Needs sudo | Requires | Installs to | post_env |
|------|--------|-----------|----------|-------------|----------|
| cargo | rustup (`sh.rustup.rs`) | **No** | curl | `~/.cargo/bin` | `export PATH="$HOME/.cargo/bin:$PATH"` |
| rustc | rustup (`sh.rustup.rs`) | **No** | curl | `~/.cargo/bin` | `export PATH="$HOME/.cargo/bin:$PATH"` |

**BUG in current system:** Both are in `_SUDO_RECIPES` which marks them
as needing sudo. They don't — rustup installs to `$HOME/.cargo`. The
frontend shows a password prompt for no reason. The new recipe fixes this.

**Lifecycle:**
- **Post-install:** PATH setup via `post_env` (already covered).
  Shell profile is updated by rustup automatically (`~/.bashrc`,
  `~/.profile`). The `post_env` is for the CURRENT session.
- **Verify:** `["bash", "-c", 'export PATH="$HOME/.cargo/bin:$PATH" && cargo --version']`
- **Update:** `["rustup", "update"]` — updates the entire Rust toolchain
  (rustc, cargo, rustfmt, clippy). Rustup manages versions.
- **Repo setup:** None — installs from sh.rustup.rs

Recipe pattern:
```python
"cargo": {
    "label": "Cargo (Rust)",
    "install": {
        "_default": [
            "bash", "-c",
            "curl --proto '=https' --tlsv1.2 -sSf "
            "https://sh.rustup.rs | sh -s -- -y",
        ],
    },
    "needs_sudo": {"_default": False},
    "requires": {"binaries": ["curl"]},
    "post_env": 'export PATH="$HOME/.cargo/bin:$PATH"',
    "verify": ["bash", "-c",
              'export PATH="$HOME/.cargo/bin:$PATH" && cargo --version'],
    "update": {"_default": ["bash", "-c",
              'export PATH="$HOME/.cargo/bin:$PATH" && rustup update']},
},
```

### Category 5: Tools with bash-curl + brew alternatives (4 tools)

These install via a curl script on Linux, but have a brew formula on macOS.
The curl scripts write to `/usr/local/bin` → needs sudo. Brew doesn't.

| Tool | curl script | Brew formula | Requires |
|------|------------|-------------|----------|
| helm | `get-helm-3` from GitHub | `brew install helm` | curl |
| trivy | `install.sh` from GitHub | `brew install trivy` | curl |
| skaffold | Direct binary download | `brew install skaffold` | curl |

**skaffold specific:** The current recipe downloads `skaffold-linux-amd64`.
This is architecture-hardcoded. On arm64 it would download the wrong binary.
For now, we keep this behavior (the binary URL would need arch interpolation,
which is a Phase 5 enhancement). The brew path works for any architecture.

**Lifecycle:**

helm:
- **Post-install:** None needed
- **Verify:** `["helm", "version"]`
- **Update:** `_default`: re-run the install script (it updates).
  `brew`: `["brew", "upgrade", "helm"]`
- **Repo setup:** None needed

trivy:
- **Post-install:** Downloads vulnerability database on first scan.
  Could pre-download: `["trivy", "image", "--download-db-only"]` but
  this is slow (downloads ~30MB). Mark as optional post-install step.
- **Verify:** `["trivy", "--version"]`
- **Update:** `_default`: re-run install script. `brew`: `["brew", "upgrade", "trivy"]`
- **Repo setup:** None needed

skaffold:
- **Post-install:** None needed
- **Verify:** `["skaffold", "version"]`
- **Update:** `_default`: re-run binary download (same URL gives latest).
  `brew`: `["brew", "upgrade", "skaffold"]`
- **Repo setup:** None needed

Recipe pattern:
```python
"helm": {
    "label": "Helm",
    "install": {
        "_default": [
            "bash", "-c",
            "curl -fsSL https://raw.githubusercontent.com/helm/helm"
            "/main/scripts/get-helm-3 | bash",
        ],
        "brew": ["brew", "install", "helm"],
    },
    "needs_sudo": {"_default": True, "brew": False},
    "requires": {"binaries": ["curl"]},
    "verify": ["helm", "version"],
    "update": {
        "_default": [
            "bash", "-c",
            "curl -fsSL https://raw.githubusercontent.com/helm/helm"
            "/main/scripts/get-helm-3 | bash",
        ],
        "brew": ["brew", "upgrade", "helm"],
    },
},
```

### Category 6: snap tools with platform variants (5 tools)

These use snap on systems with systemd, but need alternatives elsewhere.

**kubectl:**

| Method | Command | Needs sudo | When to use |
|--------|---------|-----------|-------------|
| snap | `snap install kubectl --classic` | Yes | Ubuntu/Debian with systemd |
| brew | `brew install kubectl` | No | macOS |
| _default | Binary download via curl | Yes | Any other Linux |

Binary download command:
```bash
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && chmod +x kubectl && sudo mv kubectl /usr/local/bin/
```

Note: this is also arch-hardcoded to amd64. Same limitation as skaffold.

**terraform:**

| Method | Command | Needs sudo | When to use |
|--------|---------|-----------|-------------|
| snap | `snap install terraform --classic` | Yes | Ubuntu/Debian with systemd |
| brew | `brew install terraform` | No | macOS |

No _default fallback currently. On Linux without snap and without brew,
terraform can't be installed via our system. This is acceptable —
HashiCorp provides apt/dnf repos but configuring them is complex.

**node:**

| Method | Command | Needs sudo | When to use |
|--------|---------|-----------|-------------|
| snap | `snap install node --classic` | Yes | Ubuntu/Debian with systemd |
| apt | `apt-get install -y nodejs` | Yes | Debian without snap |
| dnf | `dnf install -y nodejs` | Yes | RHEL/Fedora |
| apk | `apk add nodejs` | Yes | Alpine |
| brew | `brew install node` | No | macOS |

**go:**

| Method | Command | Needs sudo | When to use |
|--------|---------|-----------|-------------|
| snap | `snap install go --classic` | Yes | Ubuntu/Debian with systemd |
| apt | `apt-get install -y golang-go` | Yes | Debian without snap |
| dnf | `dnf install -y golang` | Yes | RHEL/Fedora |
| apk | `apk add go` | Yes | Alpine |
| brew | `brew install go` | No | macOS |

**gh (GitHub CLI):**

| Method | Command | Needs sudo | When to use |
|--------|---------|-----------|-------------|
| snap | `snap install gh` | Yes | Ubuntu/Debian with systemd |
| brew | `brew install gh` | No | macOS |

No apt/dnf alternatives currently. GitHub provides apt/dnf repos but
configuring them is complex (needs adding repo key + source).

**Lifecycle for snap tools:**

kubectl:
- **Post-install:** None needed (kubectl is a client, no daemon)
- **Verify:** `["kubectl", "version", "--client"]`
- **Update:** `snap`: `["snap", "refresh", "kubectl"]`.
  `brew`: `["brew", "upgrade", "kubectl"]`.
  `_default`: re-run binary download.
- **Repo setup:** The Kubernetes apt/dnf repos exist but require
  GPG key + source list setup. We use snap/binary instead.
  Repo setup would be needed only if we add an "apt" install method:
  ```
  "apt": [
      {"label": "Add Kubernetes GPG key",
       "command": [...], "needs_sudo": True},
      {"label": "Add Kubernetes apt repo",
       "command": [...], "needs_sudo": True},
      {"label": "apt-get update",
       "command": ["apt-get", "update"], "needs_sudo": True},
  ]
  ```
  For now: NOT populated. snap/brew/_default covers all platforms.

terraform:
- **Post-install:** None needed
- **Verify:** `["terraform", "--version"]`
- **Update:** `snap`: `["snap", "refresh", "terraform"]`.
  `brew`: `["brew", "upgrade", "terraform"]`.
- **Repo setup:** HashiCorp apt/dnf repos exist but same complexity.
  Not populated for now.

node:
- **Post-install:** None needed (node itself doesn't need config)
- **Verify:** `["node", "--version"]`
- **Update:** `snap`: `["snap", "refresh", "node"]`.
  `apt`: `["apt-get", "install", "--only-upgrade", "-y", "nodejs"]`.
  `brew`: `["brew", "upgrade", "node"]`.
- **Repo setup:** NodeSource repos for newer versions — not populated,
  system default version is acceptable for our use.

go:
- **Post-install:** Go binaries install to `~/go/bin`. PATH update:
  `export PATH="$HOME/go/bin:$PATH"`. Similar to cargo's `post_env`.
  But `go` itself is on PATH after package install — it's only
  `go install`-ed binaries that go to `~/go/bin`. Not needed for
  our use case (we don't install go-based tools via `go install`).
- **Verify:** `["go", "version"]`
- **Update:** `snap`: `["snap", "refresh", "go"]`.
  `apt`: `["apt-get", "install", "--only-upgrade", "-y", "golang-go"]`.
  `brew`: `["brew", "upgrade", "go"]`.
- **Repo setup:** None needed

gh (GitHub CLI):
- **Post-install:** Needs `gh auth login` to be useful. But that's
  an interactive flow (browser-based OAuth or token paste). We can't
  script this. The frontend already handles gh auth via the integrations
  wizard. So: no automated post_install, but the UI should prompt
  for auth after install.
- **Verify:** `["gh", "--version"]`
- **Update:** `snap`: `["snap", "refresh", "gh"]`.
  `brew`: `["brew", "upgrade", "gh"]`.
- **Repo setup:** GitHub apt repo exists. Not populated for now.

Recipe pattern for multi-variant tools:
```python
"kubectl": {
    "label": "kubectl",
    "install": {
        "snap": ["snap", "install", "kubectl", "--classic"],
        "brew": ["brew", "install", "kubectl"],
        "_default": [
            "bash", "-c",
            'curl -LO "https://dl.k8s.io/release/'
            '$(curl -L -s https://dl.k8s.io/release/stable.txt)'
            '/bin/linux/amd64/kubectl" '
            '&& chmod +x kubectl && sudo mv kubectl /usr/local/bin/',
        ],
    },
    "needs_sudo": {"snap": True, "brew": False, "_default": True},
    "prefer": ["snap", "brew", "_default"],
    "requires": {"binaries": ["curl"]},
    "verify": ["kubectl", "version", "--client"],
    "update": {
        "snap": ["snap", "refresh", "kubectl"],
        "brew": ["brew", "upgrade", "kubectl"],
        "_default": [
            "bash", "-c",
            'curl -LO "https://dl.k8s.io/release/'
            '$(curl -L -s https://dl.k8s.io/release/stable.txt)'
            '/bin/linux/amd64/kubectl" '
            '&& chmod +x kubectl && sudo mv kubectl /usr/local/bin/',
        ],
    },
},
```

### Category 7: Simple system packages — same name everywhere (12 tools)

These install via the system package manager. The package name is
the SAME (or nearly the same) across all distros.

| Tool | apt pkg | dnf pkg | apk pkg | pacman pkg | zypper pkg | brew pkg |
|------|---------|---------|---------|-----------|-----------|---------|
| git | git | git | git | git | git | git |
| curl | curl | curl | curl | curl | curl | curl |
| jq | jq | jq | jq | jq | jq | jq |
| make | make | make | make | make | make | make |
| gzip | gzip | gzip | gzip | gzip | gzip | — |
| rsync | rsync | rsync | rsync | rsync | rsync | rsync |
| openssl | openssl | openssl | openssl | openssl | openssl | openssl@3 |
| ffmpeg | ffmpeg | ffmpeg-free | ffmpeg | ffmpeg | ffmpeg | ffmpeg |
| expect | expect | expect | expect | expect | expect | expect |
| xterm | xterm | xterm | — | xterm | xterm | — |
| gnome-terminal | gnome-terminal | gnome-terminal | — | gnome-terminal | — | — |
| konsole | konsole | konsole | — | konsole | — | — |

Notable differences:
- `ffmpeg` on Fedora: `ffmpeg-free` in standard repos (full ffmpeg needs RPMFusion)
- `openssl` on brew: `openssl@3` (versioned formula)
- `gzip` on brew: not needed (macOS ships gzip)
- Terminal emulators: desktop Linux only. Not available on Alpine (no GUI),
  not relevant on macOS (Terminal.app is built-in)
- `xfce4-terminal` and `kitty`: available on apt/dnf/pacman, not on apk/zypper
- `kitty` on brew: `brew install --cask kitty` (it's a GUI app → cask)

**Lifecycle for simple system packages:**
- **Post-install:** None needed for any of these
- **Verify:** `["TOOL", "--version"]` for all of them
- **Update:** pm-specific upgrade commands:
  `apt`: `["apt-get", "install", "--only-upgrade", "-y", "TOOL"]`
  `dnf`: `["dnf", "upgrade", "-y", "TOOL"]`
  `apk`: `["apk", "upgrade", "TOOL"]`
  `pacman`: `["pacman", "-S", "--noconfirm", "TOOL"]`
  `zypper`: `["zypper", "update", "-y", "TOOL"]`
  `brew`: `["brew", "upgrade", "TOOL"]`
- **Repo setup:** None needed — all in default repos

Recipe pattern for simple same-name packages:
```python
"git": {
    "label": "Git",
    "install": {
        "apt":    ["apt-get", "install", "-y", "git"],
        "dnf":    ["dnf", "install", "-y", "git"],
        "apk":    ["apk", "add", "git"],
        "pacman": ["pacman", "-S", "--noconfirm", "git"],
        "zypper": ["zypper", "install", "-y", "git"],
        "brew":   ["brew", "install", "git"],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True, "brew": False,
    },
    "verify": ["git", "--version"],
    "update": {
        "apt":    ["apt-get", "install", "--only-upgrade", "-y", "git"],
        "dnf":    ["dnf", "upgrade", "-y", "git"],
        "apk":    ["apk", "upgrade", "git"],
        "pacman": ["pacman", "-S", "--noconfirm", "git"],
        "zypper": ["zypper", "update", "-y", "git"],
        "brew":   ["brew", "upgrade", "git"],
    },
},
```

### Category 8: System packages — different names per distro (7 tools)

| Tool | cli | apt | dnf | apk | pacman | zypper | brew |
|------|-----|-----|-----|-----|--------|--------|------|
| python | python3 | python3 | python3 | python3 | python | python3 | python@3 |
| pip | pip | python3-pip | python3-pip | py3-pip | python-pip | python3-pip | — |
| npm | npm | npm | npm | npm | npm | — | node |
| npx | npx | npm | npm | npm | npm | — | node |
| dig | dig | dnsutils | bind-utils | bind-tools | bind | bind-utils | bind |
| docker | docker | docker.io | docker | docker | docker | docker | — |
| docker-compose | docker-compose | docker-compose-v2 | docker-compose-plugin | docker-compose | docker-compose | docker-compose | docker-compose |

Notable:
- `python` has `cli: "python3"` — the binary is python3 not python
- `pip` on brew: not needed, comes with python@3
- `npm`/`npx` on brew: comes with `node` package, install `node` not `npm`
- `npm`/`npx` on zypper: no standard package, need NodeSource repo
- `docker` on Debian: `docker.io` (community), or `docker-ce` from Docker repo
- `docker` on brew: `brew install --cask docker` (Docker Desktop, GUI app)
- `docker-compose` on Debian: `docker-compose-v2` (the v2 plugin).
  Some older systems have `docker-compose` as a separate Python package.

**Lifecycle for different-name packages:**

python:
- **Post-install:** None needed
- **Verify:** `["python3", "--version"]`
- **Update:** pm-specific like category 7
- **Repo setup:** None needed

pip:
- **Post-install:** None needed
- **Verify:** `["pip", "--version"]`
- **Update:** `["pip", "install", "--upgrade", "pip"]`
- **Repo setup:** None needed

npm / npx:
- **Post-install:** None needed (npm is ready after install)
- **Verify:** `["npm", "--version"]` / `["npx", "--version"]`
- **Update:** `["npm", "install", "-g", "npm"]` (npm updates itself)
- **Repo setup:** NodeSource repo if newer version needed — not
  populated, system default is acceptable.

dig:
- **Post-install:** None needed
- **Verify:** `["dig", "-v"]`
- **Update:** pm-specific like category 7
- **Repo setup:** None needed

**docker — THE MOST COMPLEX RECIPE:**

- **Post-install:**
  ```python
  "post_install": [
      {
          "label": "Start Docker daemon",
          "command": ["systemctl", "start", "docker"],
          "needs_sudo": True,
          "condition": "has_systemd",
      },
      {
          "label": "Enable Docker on boot",
          "command": ["systemctl", "enable", "docker"],
          "needs_sudo": True,
          "condition": "has_systemd",
      },
      {
          "label": "Add current user to docker group",
          "command": ["bash", "-c", "usermod -aG docker $USER"],
          "needs_sudo": True,
          "condition": "not_root",
      },
  ]
  ```
  **NOTE on group membership:** Adding user to docker group takes
  effect on NEXT login. The current shell session still needs `sudo`.
  The verify step should use sudo to avoid false negatives.

  **Docker in containers:** Skip all post_install. Docker-in-Docker
  has its own rules (mount docker socket or use dind sidecar).
  The `condition` field handles this:
  - `has_systemd` → skips in containers without systemd
  - `not_root` → skips group-add when running as root (no need)
  - Could add `not_container` for explicit container check

  **Docker on WSL2 (no systemd):** Can't start docker daemon via
  systemctl. Options:
  - Use Docker Desktop for Windows with WSL2 backend (recommended)
  - Enable systemd in WSL (`[boot] systemd=true` in `/etc/wsl.conf`)
  - Manual `sudo dockerd &`
  The `has_systemd` condition correctly skips service start on
  WSL1 or WSL2 without systemd enabled.

- **Verify:** `["docker", "info"]` — confirms daemon is running.
  Needs sudo if user not in docker group yet.
  Alternative: `["docker", "--version"]` — just checks binary exists.

- **Update:** pm-specific upgrade commands like category 7.

- **Repo setup:** The `docker.io` package (community) is in default
  Debian repos — no repo setup needed. For Docker CE (official):
  ```python
  "repo_setup": {
      "apt": [
          {
              "label": "Install prerequisites",
              "command": ["apt-get", "install", "-y",
                          "ca-certificates", "curl", "gnupg"],
              "needs_sudo": True,
          },
          {
              "label": "Add Docker GPG key",
              "command": ["bash", "-c",
                          "install -m 0755 -d /etc/apt/keyrings && "
                          "curl -fsSL https://download.docker.com/linux/"
                          "$(. /etc/os-release && echo $ID)/gpg "
                          "| gpg --dearmor -o /etc/apt/keyrings/docker.gpg"],
              "needs_sudo": True,
          },
          {
              "label": "Add Docker apt repo",
              "command": ["bash", "-c",
                          'echo "deb [arch=$(dpkg --print-architecture) '
                          'signed-by=/etc/apt/keyrings/docker.gpg] '
                          'https://download.docker.com/linux/'
                          '$(. /etc/os-release && echo $ID) '
                          '$(. /etc/os-release && echo $VERSION_CODENAME) '
                          'stable" > /etc/apt/sources.list.d/docker.list'],
              "needs_sudo": True,
          },
          {
              "label": "Update package index",
              "command": ["apt-get", "update"],
              "needs_sudo": True,
          },
      ],
  }
  ```
  NOTE: For Phase 2.2, we use `docker.io` (no repo setup needed).
  The Docker CE repo_setup is documented here for future use.

docker-compose:
- **Post-install:** None — it's a CLI plugin, no daemon.
  Depends on `docker` being installed and running.
- **Verify:** `["docker", "compose", "version"]` (v2 plugin syntax)
  or `["docker-compose", "version"]` (standalone syntax)
- **Update:** pm-specific
- **Repo setup:** Same as docker if using Docker CE repo
- **Requires:** `docker` binary (should declare `requires.binaries: ["docker"]`)

Recipe pattern for different-name packages:
```python
"python": {
    "label": "Python",
    "cli": "python3",
    "install": {
        "apt":    ["apt-get", "install", "-y", "python3"],
        "dnf":    ["dnf", "install", "-y", "python3"],
        "apk":    ["apk", "add", "python3"],
        "pacman": ["pacman", "-S", "--noconfirm", "python"],
        "zypper": ["zypper", "install", "-y", "python3"],
        "brew":   ["brew", "install", "python@3"],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True, "brew": False,
    },
    "verify": ["python3", "--version"],
    "update": {
        "apt":    ["apt-get", "install", "--only-upgrade", "-y", "python3"],
        "dnf":    ["dnf", "upgrade", "-y", "python3"],
        "apk":    ["apk", "upgrade", "python3"],
        "pacman": ["pacman", "-S", "--noconfirm", "python"],
        "zypper": ["zypper", "update", "-y", "python3"],
        "brew":   ["brew", "upgrade", "python@3"],
    },
},

"docker": {
    "label": "Docker",
    "install": {
        "apt":    ["apt-get", "install", "-y", "docker.io"],
        "dnf":    ["dnf", "install", "-y", "docker"],
        "apk":    ["apk", "add", "docker"],
        "pacman": ["pacman", "-S", "--noconfirm", "docker"],
        "zypper": ["zypper", "install", "-y", "docker"],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True,
    },
    "post_install": [
        {
            "label": "Start Docker daemon",
            "command": ["systemctl", "start", "docker"],
            "needs_sudo": True,
            "condition": "has_systemd",
        },
        {
            "label": "Enable Docker on boot",
            "command": ["systemctl", "enable", "docker"],
            "needs_sudo": True,
            "condition": "has_systemd",
        },
        {
            "label": "Add user to docker group",
            "command": ["bash", "-c", "usermod -aG docker $USER"],
            "needs_sudo": True,
            "condition": "not_root",
        },
    ],
    "verify": ["docker", "--version"],
    "update": {
        "apt":    ["apt-get", "install", "--only-upgrade", "-y", "docker.io"],
        "dnf":    ["dnf", "upgrade", "-y", "docker"],
        "apk":    ["apk", "upgrade", "docker"],
        "pacman": ["pacman", "-S", "--noconfirm", "docker"],
        "zypper": ["zypper", "update", "-y", "docker"],
    },
},
```

---

## 4. Dependency Chains — Every Path

### Chain 1: cargo-outdated (deepest chain)

```
cargo-outdated
├── requires.binaries: [cargo]
│   └── cargo
│       └── requires.binaries: [curl]
│           └── curl (system package, no further deps)
└── requires.packages:
    └── debian: [pkg-config, libssl-dev, libcurl4-openssl-dev]
    └── rhel:   [pkgconf-pkg-config, openssl-devel, libcurl-devel]
    └── ...
```

On Ubuntu with curl installed, cargo NOT installed:
1. Install system packages: `apt-get install -y pkg-config libssl-dev libcurl4-openssl-dev`
2. Install cargo: `curl ... | sh -s -- -y`
3. Install cargo-outdated: `export PATH=... && cargo install cargo-outdated`

On Ubuntu with NOTHING installed (not even curl):
1. Install curl: `apt-get install -y curl`
2. Install system packages: `apt-get install -y pkg-config libssl-dev libcurl4-openssl-dev`
3. Install cargo: `curl ... | sh -s -- -y`
4. Install cargo-outdated: `export PATH=... && cargo install cargo-outdated`

But wait — steps 1 and 2 both use apt-get. They should be BATCHED:
1. Install packages: `apt-get install -y curl pkg-config libssl-dev libcurl4-openssl-dev`
2. Install cargo: `curl ... | sh -s -- -y`
3. Install cargo-outdated: `export PATH=... && cargo install cargo-outdated`

The resolver (Phase 2.3) must batch all system packages into one step.
This means `curl` needs to be in the package list, not just in `requires.binaries`.

**Critical insight:** When a binary requirement (like `curl`) is itself
a system package, the resolver needs to detect that and add it to the
package batch instead of as a separate tool step. How?

- `curl` has a recipe in TOOL_RECIPES with `install.apt: ["apt-get", ...]`
- The resolver sees `curl` is a binary dep of `cargo`
- `curl` is not installed
- The resolver checks `curl`'s recipe → it's a system package (apt install)
- Instead of adding a separate "Install curl" step, it adds `curl` to the
  package batch

This is a Phase 2.3 concern, but the recipe data must support it. The
resolver needs to be able to distinguish "this is a pm package install"
from "this is a bash-curl script" or "this is a pip install." It can
do this by looking at the install method keys — if the picked method
matches the primary pm (apt, dnf, etc.), it's a package install that
can be batched.

### Chain 2: cargo-audit

```
cargo-audit
├── requires.binaries: [cargo]
│   └── cargo → curl
└── requires.packages:
    └── debian: [pkg-config, libssl-dev]
```

Same as cargo-outdated but fewer system packages (no libcurl-openssl-dev).

### Chain 3: eslint

```
eslint
└── requires.binaries: [npm]
    └── npm (system package)
```

On Ubuntu: `apt-get install -y npm` → `npm install -g eslint`
On Fedora: `dnf install -y npm` → `npm install -g eslint`
On macOS: `brew install node` → `npm install -g eslint`

### Chain 4: prettier

Same as eslint.

### Chain 5: helm, trivy, skaffold

```
helm/trivy/skaffold
└── requires.binaries: [curl]
    └── curl (system package)
```

If curl is installed (usually is): 1 step.
If curl is missing: 2 steps (install curl, then install tool).
But again — if curl is a system package, it can be batched with other
packages if other steps also need system packages.

### Chain 6: kubectl

```
kubectl
└── requires.binaries: [curl]  (only for _default binary download method)
```

If using snap: no curl dependency (snap handles it internally).
If using brew: no curl dependency.
Only the `_default` binary download needs curl.

The resolver needs to know WHICH install method was selected before
determining dependencies. This means `requires.binaries` might be
method-specific. But that adds complexity.

**Decision:** Keep `requires.binaries` global (not per-method). If
kubectl is installed via snap, curl being declared as a dep just means
the resolver checks curl is available — but since snap doesn't need it,
it's a harmless pre-check. The snap install won't fail because of missing
curl.

### Chain 7: All other tools (no deps)

git, jq, make, gzip, etc. — no dependency chains. Single step.

---

## 5. The `_TOOLS` Registry Relationship

The `_TOOLS` list in `l0_detection.py` has 40+ entries. Each has
`id`, `cli`, `label`, `category`, `install_type`.

`TOOL_RECIPES` must cover the SAME set of tools (same IDs, same labels).
The `cli` field in TOOL_RECIPES must match the `cli` field in `_TOOLS`.

Tools where cli ≠ id:
- `python` → cli `python3`

All others: cli = id.

The `install_type` field in `_TOOLS` is used by the frontend to determine
the install flow. Once TOOL_RECIPES is in place, `install_type` becomes
redundant — the recipe itself declares whether sudo is needed, what the
dependencies are, etc. But `install_type` is also used in the audit
frontend for badge colors and categorization. We keep `_TOOLS` as-is
for detection purposes.

---

## 6. The Terminal Emulators Problem

5 terminal emulators in the registry:
xterm, gnome-terminal, xfce4-terminal, konsole, kitty

These are desktop Linux GUI applications. They:
- Don't exist on servers (no GUI)
- Don't exist on Alpine (no GUI in base)
- Don't exist on macOS (macOS has Terminal.app and iTerm2, not these)
- Are only meaningful on desktop Linux with a display server

For the recipe, I'll provide apt/dnf/pacman variants where the package
exists. No brew recipes (macOS has its own terminal). No apk recipes
(Alpine has no GUI). No zypper for gnome-terminal/xfce4-terminal
(they exist but are uncommon on SUSE desktop).

---

## 7. What `_analyse_install_failure()` Needs

`_analyse_install_failure()` currently references `CARGO_BUILD_DEPS`
(Debian names) in its remediation options as `system_deps`. Once
`CARGO_BUILD_DEPS` is removed, the function needs to get system deps
from the recipe.

The function receives `tool` and `stderr`. It can look up
`TOOL_RECIPES[tool]["requires"]["packages"]` and use the current
system's family to get the right package names.

But `_analyse_install_failure` doesn't receive the system profile.
We need to either:
a) Pass system profile to `_analyse_install_failure` — minor signature change
b) Call `_detect_os()` inside the function — adds ~30ms
c) Have the caller (`install_tool`) pass the family/packages

Option (a) is cleanest. `install_tool` already knows the tool. It can
look up the recipe and pass the system deps. But `install_tool` itself
is being replaced (Phase 2.4).

**Decision:** For Phase 2.2, replace `CARGO_BUILD_DEPS` references in
`_analyse_install_failure` with a lookup from `TOOL_RECIPES`. This
requires getting the distro family, which means calling `_detect_os()`
inside the function. The ~30ms cost is acceptable — this function only
runs on failure, not on the hot path.

---

## 8. Condition System — How post_install Steps Are Filtered

The `condition` field on post_install steps uses data from Phase 1's
system profile:

| Condition | System profile field | True when |
|-----------|---------------------|----------|
| `has_systemd` | `capabilities.systemd` | systemd is PID 1 |
| `not_root` | `capabilities.is_root` | NOT running as root |
| `not_container` | `container.in_container` | NOT inside a container |
| `None` | — | Always run |

The resolver (Phase 2.3) evaluates conditions at plan-creation time.
Steps whose conditions are false are EXCLUDED from the plan entirely.
The frontend never sees them.

Combination example: Docker on WSL2 without systemd, running as root:
- `has_systemd` → False → skip "Start Docker" and "Enable Docker"
- `not_root` → False → skip "Add user to docker group"
- Result: only the install step, no post-install steps

Docker on Ubuntu desktop, running as regular user:
- `has_systemd` → True → include service steps
- `not_root` → True → include group-add step
- Result: install + 3 post-install steps

---

## 9. Implementation Steps

### Step 1: Add `TOOL_RECIPES` dict after the old recipe dicts

Position: after line 83 (end of `_SUDO_RECIPES`), before line 85
(`# ── System dependency checks`).

The dict contains ALL tools from sections 3.1 through 3.8 above.
Estimated size: ~400 lines (expanded from 200 due to lifecycle fields).

### Step 2: Update `_analyse_install_failure()` to use TOOL_RECIPES

Replace `CARGO_BUILD_DEPS` references with recipe lookup:
```python
# Before:
"system_deps": CARGO_BUILD_DEPS,

# After:
"system_deps": _get_system_deps(tool),
```

Add helper:
```python
def _get_system_deps(tool: str) -> list[str]:
    """Get system package deps for a tool, using detected distro family."""
    recipe = TOOL_RECIPES.get(tool, {})
    pkg_map = recipe.get("requires", {}).get("packages", {})
    if not pkg_map:
        return []
    from src.core.services.audit.l0_detection import _detect_os
    family = _detect_os().get("distro", {}).get("family", "debian")
    return pkg_map.get(family, pkg_map.get("debian", []))
```

### Step 3: Update `install_tool()` to use TOOL_RECIPES

Replace the recipe lookup section (lines 318-350):
```python
# Before:
if tool in _NO_SUDO_RECIPES:
    cmd = _NO_SUDO_RECIPES[tool]
    needs_sudo = False
elif tool in _SUDO_RECIPES:
    needs_sudo = True
    ...

# After:
recipe = TOOL_RECIPES.get(tool)
if recipe:
    # Pick install method based on system profile
    ...
else:
    return {"ok": False, "error": f"No install recipe for '{tool}'."}
```

This also replaces the `_RUNTIME_DEPS` / `_TOOL_REQUIRES` dep check
with the recipe's `requires.binaries`.

### Step 4: Remove old data structures

Delete:
- `_NO_SUDO_RECIPES` (lines 34-46)
- `_SUDO_RECIPES` (lines 49-83)
- `CARGO_BUILD_DEPS` (line 88)
- `_RUNTIME_DEPS` (lines 354-358)
- `_TOOL_REQUIRES` (lines 360-363)

### Step 5: Update `_TOOLS` registry `install_type`

The `install_type` field in `l0_detection.py` is now derivable from
TOOL_RECIPES. But it's still used by the frontend for badge colors.
Leave it as-is for now. The resolver doesn't use it.

---

## 10. Files Changed

| File | What changes |
|------|-------------|
| `tool_install.py` | Add TOOL_RECIPES (~400 lines). Remove _NO_SUDO_RECIPES, _SUDO_RECIPES, CARGO_BUILD_DEPS, _RUNTIME_DEPS, _TOOL_REQUIRES. Update _analyse_install_failure to use recipe lookup. Update install_tool to use TOOL_RECIPES. |
| `l0_detection.py` | No changes in Phase 2.2 |
| `routes_audit.py` | No changes in Phase 2.2 |

---

## 11. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Wrong package name for a distro | Install fails on that distro | Each name verified against official repos. Can be corrected per-tool without affecting others |
| cargo/rustc recipe changes from sudo to no-sudo | Changes frontend behavior (no password prompt) | This is a BUG FIX — cargo doesn't need sudo. Correct behavior |
| `_analyse_install_failure` calls `_detect_os()` | ~30ms on failure path only | Acceptable — error path is not performance-sensitive |
| Missing recipe for a tool | `install_tool` returns error | Same behavior as current system when tool not in either dict |
| Brew timeout in dependency check | Slow check on macOS | brew timeout set to 30s in Phase 2.1's `_is_pkg_installed` |
| Docker post_install fails without systemd | Service steps skipped | `condition: "has_systemd"` filters these out at plan time |
| Group membership requires re-login | Docker still needs sudo until next session | Verify step uses `docker --version` not `docker info` to avoid false negatives |
| TOOL_RECIPES is large (~400 lines) | Harder to review | Organized by category, each tool is self-contained, easy to edit one without affecting others |
