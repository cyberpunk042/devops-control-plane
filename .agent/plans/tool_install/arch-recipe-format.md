# Architecture: Recipe Format

> This document defines the CANONICAL recipe format — the data model
> for how tools and software are described for installation.
>
> This is the DATA MODEL at the heart of the system. Recipes are
> static data (dicts) that describe WHAT to install and HOW. The
> resolver reads recipes + system profile and produces plans.
>
> Obeys: arch-principles §1 (always present), §3 (explicit branches),
>        §6 (extensibility by addition), §7 (nothing off-limits),
>        §12 (data is the interface)
>
> Phase 2 implements the SIMPLE recipe format.
> Phases 4-8 add fields incrementally. Simple recipes never break.

---

## Overview

All recipes live in a single dict: `TOOL_RECIPES`.

```python
TOOL_RECIPES: dict[str, dict] = {
    "tool_id": { ... recipe dict ... },
}
```

The tool ID is the dict key. It must match the tool ID used in the
`_TOOLS` registry and in audit scanning.

There are TWO levels of recipe complexity:

| Level | Has `choices`? | Resolver mode | Phase |
|-------|---------------|--------------|-------|
| Simple | No | Single-pass: recipe → plan | Phase 2 |
| Complex | Yes | Two-pass: recipe → choices → user selects → plan | Phase 4+ |

The resolver checks: `if "choices" in recipe:` to decide which mode.

---

## Simple Recipe Format (Phase 2)

This is the format for the 50+ devops tools the system manages today.
Every field is documented with its type, purpose, and when it's optional.

```python
{
    # ── Identity ──────────────────────────────────────────────

    "label": str,
    # REQUIRED. Human-readable name shown in UI.
    # Example: "Ruff", "kubectl", "Docker", "Cargo (Rust)"

    "cli": str,
    # OPTIONAL. Binary name checked with shutil.which().
    # Defaults to the tool ID (the dict key).
    # Only needed when tool ID ≠ binary name.
    # Examples: tool "python" → cli "python3"
    #           tool "rustc" → cli "rustc" (same, omit)

    # ── Install ───────────────────────────────────────────────

    "install": dict[str, list[str]],
    # REQUIRED. Install commands keyed by method.
    #
    # Method keys:
    #   System PM:  "apt", "dnf", "yum", "apk", "pacman", "zypper", "brew"
    #   Snap:       "snap"     (requires systemd)
    #   Universal:  "_default" (works on any system: pip, cargo, curl scripts)
    #
    # Values: command list for subprocess.run()
    #
    # A recipe MUST have at least one key.
    # A recipe CAN have multiple keys (platform variants).
    #
    # Resolution order (Phase 2.3 resolver):
    #   1. Recipe's "prefer" list (if present)
    #   2. System's primary package manager (from system profile)
    #   3. "snap" (if snap_available in system profile)
    #   4. "_default" fallback

    "needs_sudo": dict[str, bool],
    # REQUIRED. Per-method sudo flag. Keys MUST match "install" keys.
    #
    # Rules of thumb:
    #   apt/dnf/yum/apk/pacman/zypper/snap → True
    #   brew → False
    #   _default pip/cargo → False
    #   _default curl script to /usr/local/bin → True
    #   _default curl script to ~/.cargo → False

    "prefer": list[str],
    # OPTIONAL. Ordered preference for install methods.
    # Resolver tries these FIRST, then system PM, then snap, then _default.
    #
    # Example: kubectl prefers ["snap", "brew", "_default"]

    # ── Dependencies ──────────────────────────────────────────

    "requires": {
        "binaries": list[str],
        # OPTIONAL. Tool IDs that must be on PATH before install.
        # Resolved RECURSIVELY: cargo-audit → cargo → curl.
        # The resolver walks this tree depth-first and inserts
        # dependency install steps BEFORE this tool's install step.
        #
        # Examples: cargo-audit needs ["cargo"]
        #           eslint needs ["npm"]
        #           cargo needs ["curl"]

        "packages": dict[str, list[str]],
        # OPTIONAL. System packages needed (e.g., for compilation).
        # Keyed by distro FAMILY (not PM).
        # Keys: "debian", "rhel", "alpine", "arch", "suse", "macos"
        #
        # The resolver looks up the family from system profile,
        # then builds the install command via Phase 2.1's
        # _build_pkg_install_cmd().
        #
        # Example for cargo-audit:
        #   "debian": ["pkg-config", "libssl-dev"]
        #   "rhel":   ["pkgconf-pkg-config", "openssl-devel"]
        #   "alpine": ["pkgconf", "openssl-dev"]
        #   "arch":   ["pkgconf", "openssl"]
        #   "suse":   ["pkg-config", "libopenssl-devel"]
        #   "macos":  ["pkg-config", "openssl@3"]
    },

    # ── Repo Setup ────────────────────────────────────────────

    "repo_setup": dict[str, list[dict]],
    # OPTIONAL. Per-PM repo configuration steps that must run
    # BEFORE the install command. Needed when the tool isn't in
    # the system's default repos.
    #
    # Keys match PM IDs: "apt", "dnf", etc.
    # Values: ordered list of step dicts:
    #   {
    #     "label": str,           # human-readable description
    #     "command": list[str],   # subprocess.run() command
    #     "needs_sudo": bool,     # does this step need sudo?
    #   }
    #
    # Example: Docker CE on Debian needs GPG key + sources.list + apt update
    #
    # For Phase 2: documented but only populated for tools that
    # actually need repo setup (docker-ce, gh, kubernetes repo, etc.)

    # ── Post-install ──────────────────────────────────────────

    "post_env": str,
    # OPTIONAL. Shell command to set environment after install.
    # Used for tools that install to non-standard PATH locations.
    #
    # Only cargo/rustc use this:
    #   'export PATH="$HOME/.cargo/bin:$PATH"'
    #
    # The resolver prepends this to LATER steps that depend on
    # this tool's binary when that binary wasn't on PATH at
    # resolution time.

    "post_install": list[dict],
    # OPTIONAL. Ordered steps to run AFTER install succeeds.
    # Each step:
    #   {
    #     "label": str,          # human-readable description
    #     "command": list[str],  # subprocess.run() command
    #     "needs_sudo": bool,    # does this step need sudo?
    #     "condition": str|None, # optional gate:
    #                            #   "has_systemd"   — only with systemd
    #                            #   "not_root"      — only when not root
    #                            #   "not_container" — skip in containers
    #                            #   None            — always run
    #   }
    #
    # Examples:
    #   Docker: start service, enable on boot, add user to group
    #   Cargo: (uses post_env instead — PATH export, not a command)

    # ── Verification ──────────────────────────────────────────

    "verify": list[str],
    # OPTIONAL. Command to confirm the tool is functional after
    # install + post_install. Exit code 0 = success.
    #
    # Should be fast and non-destructive.
    # Examples:
    #   git   → ["git", "--version"]
    #   docker → ["docker", "info"]
    #   trivy → ["trivy", "--version"]
    #   cargo → ["bash", "-c",
    #            'export PATH="$HOME/.cargo/bin:$PATH" && cargo --version']

    # ── Update ────────────────────────────────────────────────

    "update": dict[str, list[str]],
    # OPTIONAL. Per-method update commands. Keys match "install" keys.
    #
    # Examples:
    #   pip:   {"_default": _PIP + ["install", "--upgrade", "ruff"]}
    #   apt:   {"apt": ["apt-get", "install", "--only-upgrade", "-y", "git"]}
    #   snap:  {"snap": ["snap", "refresh", "kubectl"]}
    #   brew:  {"brew": ["brew", "upgrade", "helm"]}
    #   cargo: {"_default": ["cargo", "install", "cargo-audit"]}
    #   rust:  {"_default": ["rustup", "update"]}

    # ── Categorization ───────────────────────────────────────

    "category": str,
    # OPTIONAL. UI grouping category for complex recipes.
    # Used to organize tools in the admin panel beyond the
    # default 9 categories (which are based on tool ID).
    #
    # Values: "gpu", "ml", "data_pack", "config", "pages"
    # Simple tools (pip/apt/cargo) don't need this — they are
    # categorized by the existing 9-category system.

    # ── Custom verification ──────────────────────────────────

    "cli_verify_args": list[str],
    # OPTIONAL. Custom command to verify the tool is installed when
    # the standard `cli --version` pattern doesn't work.
    # Used instead of `[cli, "--version"]` for version checking.
    #
    # Examples:
    #   pytorch:     ["-c", "import torch; print(torch.__version__)"]
    #                → run as ["python3", "-c", "import torch; ..."]
    #   opencv:      ["-c", "import cv2; print(cv2.__version__)"]
    #   docusaurus:  ["docusaurus", "--version"]

    # ── Architecture mapping ─────────────────────────────────

    "arch_map": dict[str, str],
    # OPTIONAL. Maps raw uname arch names to download URL arch IDs.
    # Used by binary download recipes where upstream naming differs
    # from Python's platform.machine().
    #
    # Example for Hugo:
    #   {"x86_64": "amd64", "aarch64": "arm64"}
    #
    # The resolved arch is available as {arch} in template variables.

    # ── Removal ──────────────────────────────────────────────

    "remove": dict[str, list[str]],
    # OPTIONAL. Per-method removal commands. Keys match install methods.
    # Used by `remove_tool()` to cleanly uninstall.
    #
    # If absent, `remove_tool()` derives a removal command from the
    # install method using UNDO_COMMANDS (e.g. pip install → pip uninstall).
    #
    # Example for ROCm:
    #   {"apt": ["apt-get", "remove", "-y", "rocm-dev"],
    #    "dnf": ["dnf", "remove", "-y", "rocm-dev"]}
}
```

### Key relationships

**`install` keys vs `requires.packages` keys — two different things:**

- `install` keys = WHICH COMMAND to use (apt-get vs dnf vs apk)
- `requires.packages` keys = WHICH NAMES to use (libssl-dev vs openssl-devel)

They correlate but aren't identical:

| Distro family | Primary PM | `install` key | `requires.packages` key |
|--------------|-----------|---------------|--------------------------|
| debian | apt | "apt" | "debian" |
| rhel | dnf (or yum) | "dnf" / "yum" | "rhel" |
| alpine | apk | "apk" | "alpine" |
| arch | pacman | "pacman" | "arch" |
| suse | zypper | "zypper" | "suse" |
| macos | brew | "brew" | "macos" |

The PM is for commands. The family is for package names.

---

## Recipe Categories (Phase 2 — 35+ tools)

### Category 1: pip tools (7 tools)

Simplest recipes. pip works everywhere (app runs in venv).

```python
"ruff": {
    "label": "Ruff",
    "install": {"_default": _PIP + ["install", "ruff"]},
    "needs_sudo": {"_default": False},
    "verify": ["ruff", "--version"],
    "update": {"_default": _PIP + ["install", "--upgrade", "ruff"]},
},
```

No `requires` — pip is available because the app is running in Python.
Pattern shared by: ruff, mypy, pytest, black, pip-audit, safety, bandit.

### Category 2: npm tools (2 tools)

Need `npm` binary on PATH.

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

Pattern shared by: eslint, prettier.

### Category 3: cargo tools (2 tools)

Need `cargo` binary AND system dev packages for compilation.

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

### Category 4: curl-script runtimes (2 tools)

Install via curl script, custom PATH location.

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

Note: `_SUDO_RECIPES` / `_NO_SUDO_RECIPES` no longer exist. The per-recipe
`needs_sudo` dict replaced them.

### Category 5: curl-script + brew alternatives (3 tools)

curl script on Linux (sudo, writes to /usr/local/bin), brew on macOS.

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
        "_default": [...],  # re-run install script
        "brew": ["brew", "upgrade", "helm"],
    },
},
```

Pattern shared by: helm, trivy, skaffold.

### Category 6: snap + platform variants (5 tools)

snap on systemd systems, system PM or brew elsewhere.

```python
"kubectl": {
    "label": "kubectl",
    "install": {
        "snap": ["snap", "install", "kubectl", "--classic"],
        "brew": ["brew", "install", "kubectl"],
        "_default": ["bash", "-c", "curl -LO ..."],
    },
    "needs_sudo": {"snap": True, "brew": False, "_default": True},
    "prefer": ["snap", "brew", "_default"],
    "requires": {"binaries": ["curl"]},
    "verify": ["kubectl", "version", "--client"],
    "update": {
        "snap": ["snap", "refresh", "kubectl"],
        "brew": ["brew", "upgrade", "kubectl"],
        "_default": [...],
    },
},
```

Pattern shared by: kubectl, terraform, node, go, gh.

### Category 7: simple system packages (12 tools)

Same (or nearly same) package name across all distros.

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
        "pacman": ["pacman", "-Syu", "--noconfirm", "git"],
        "zypper": ["zypper", "update", "-y", "git"],
        "brew":   ["brew", "upgrade", "git"],
    },
},
```

Pattern shared by: git, curl, jq, make, ffmpeg, gzip, openssl,
rsync, expect, python, pip, npm.

### Category 8: packages with name variance (4 tools)

Different package names across distros.

```python
"dig": {
    "label": "dig",
    "install": {
        "apt":    ["apt-get", "install", "-y", "dnsutils"],
        "dnf":    ["dnf", "install", "-y", "bind-utils"],
        "apk":    ["apk", "add", "bind-tools"],
        "pacman": ["pacman", "-S", "--noconfirm", "bind"],
        "zypper": ["zypper", "install", "-y", "bind-utils"],
        "brew":   ["brew", "install", "bind"],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True, "brew": False,
    },
    "verify": ["dig", "-v"],
},
```

### Category 9: tools with post-install config (2 tools)

Docker is the primary example.

```python
"docker": {
    "label": "Docker",
    "install": {
        "apt":    ["apt-get", "install", "-y", "docker.io"],
        "dnf":    ["dnf", "install", "-y", "docker"],
        "apk":    ["apk", "add", "docker"],
        "pacman": ["pacman", "-S", "--noconfirm", "docker"],
        "zypper": ["zypper", "install", "-y", "docker"],
        "brew":   ["brew", "install", "--cask", "docker"],
    },
    "needs_sudo": {
        "apt": True, "dnf": True, "apk": True,
        "pacman": True, "zypper": True, "brew": False,
    },
    "post_install": [
        {"label": "Start Docker daemon",
         "command": ["systemctl", "start", "docker"],
         "needs_sudo": True,
         "condition": "has_systemd"},
        {"label": "Enable Docker on boot",
         "command": ["systemctl", "enable", "docker"],
         "needs_sudo": True,
         "condition": "has_systemd"},
        {"label": "Add user to docker group",
         "command": ["bash", "-c", "usermod -aG docker $USER"],
         "needs_sudo": True,
         "condition": "not_root"},
    ],
    "verify": ["docker", "info"],
    "update": {
        "apt": ["apt-get", "install", "--only-upgrade", "-y", "docker.io"],
        # ... etc
    },
},
```

---

## Complex Recipe Extensions (Phase 4+)

These fields are ADDED to simple recipes. A recipe with `choices`
becomes a complex recipe. The resolver uses two-pass mode.

### Detection: simple vs complex

```python
if "choices" in recipe:
    # Two-pass: return choices → user selects → resolve plan
else:
    # Single-pass: resolve plan directly (Phase 2 path)
```

### `choices` — decision points (Phase 4)

```python
"choices": [
    {
        "id": str,              # unique choice ID within recipe
        "label": str,           # human-readable question
        "type": str,            # "single" | "multi"
        "depends_on": dict | None,  # conditional: only shown if...
                                    # {"choice_id": "value"}
        "options": [
            {
                "id": str,          # option ID
                "label": str,       # human-readable name
                "description": str, # what this option does differently
                "available": bool,  # True if can be used on this system
                "disabled_reason": str | None,  # WHY unavailable
                "enable_hint": str | None,      # HOW to make it available
                "risk": str | None,             # "low" | "medium" | "high"
                "warning": str | None,          # risk explanation
                "estimated_time": str | None,   # e.g., "20-60 minutes"
                "default": bool,                # recommended option?
                "requires": dict | None,        # hardware/software needs
            },
        ],
    },
],
```

**Principle §1:** ALL options are always present. `available: false`
means greyed out in UI, with `disabled_reason` shown by assistant.

**Principle §3:** Each choice is a named, explicit branch point.

### `inputs` — user-provided values (Phase 4)

```python
"inputs": [
    {
        "id": str,              # input ID, used in template substitution
        "label": str,           # human-readable label
        "type": str,            # "text" | "number" | "path" | "select"
        "default": any,         # default value
        "description": str,     # help text for assistant
        "condition": str | None,  # when this input is relevant
        "validation": dict | None,  # {min, max, pattern, etc.}
        "options": list[str] | None,  # for type "select" only
    },
],
```

Input values are substituted into commands via `{input_id}` templates.

### `install_variants` — branched install commands (Phase 4)

```python
"install_variants": {
    "variant_id": {
        # Simple variant: single command
        "command": list[str],   # may contain {input_id} templates
        "needs_sudo": bool,

        # OR complex variant: multi-step build
        "steps": [
            {
                "label": str,
                "command": list[str],   # may contain templates
                "needs_sudo": bool,
                "risk": str | None,
            },
        ],
    },
},
```

The `variant_id` matches option IDs from `choices`. The resolver
selects the variant based on user's choice selections.

### `data_packs` — downloadable extras (Phase 7)

```python
"data_packs": [
    {
        "id": str,              # pack ID
        "label": str,           # "English (large)"
        "description": str,     # "300MB, includes word vectors"
        "size_mb": int,         # for UI display
        "command": list[str],   # download command
        "optional": bool,       # True = user can skip
        "default": bool,        # pre-selected?
    },
],
```

Example: spaCy models, NLTK data, HuggingFace models.

### `config_templates` — configuration files (Phase 8)

```python
"config_templates": [
    {
        "id": str,                  # unique template ID within recipe
        "file": str,                # target path, e.g. "/etc/docker/daemon.json"
        "format": str,              # "json" | "ini" | "raw" | "yaml"
        "template": str,            # template string with {input_id} placeholders
        "inputs": [                 # user-provided values for template substitution
            {
                "id": str,          # input ID, used in template {id} placeholders
                "label": str,       # human-readable label
                "type": str,        # "text" | "number" | "select" | "password"
                "default": any,     # default value
                "options": list[str] | None,     # for type "select"
                "validation": dict | None,       # {"min": N, "max": N} for numbers
            },
        ],
        "needs_sudo": bool,         # writing to /etc usually needs sudo
        "backup": bool | None,      # back up existing file first? (default: False)
        "post_command": list[str] | None,  # command to run after writing
                                           # e.g. ["systemctl", "restart", "docker"]
        "condition": str | None,    # conditional execution
                                    # e.g. "has_systemd" — only apply if condition met
    },
],
```

A recipe can have MULTIPLE config templates (e.g. different paths).
Each template is independently conditioned and may have its own inputs.

### `requires.kernel_config` — kernel needs (Phase 6)

```python
"requires": {
    # ... existing binaries and packages fields ...
    "kernel_config": list[str],    # ["CONFIG_VFIO_PCI", "CONFIG_IOMMU_SUPPORT"]
    "hardware": list[str],         # ["nvidia-gpu", "amd-gpu"]
    "network": bool,               # True = needs internet access
},
```

### `risk` — recipe-level risk tag (Phase 6)

```python
"risk": str,    # "low" | "medium" | "high" | "critical"
                # Defaults to "low" if absent.
                # Affects UI treatment (arch-principles §7).
```

### `restart_required` — restart declaration (Phase 8)

```python
"restart_required": str | None,  # "session" | "service" | "system" | None
                                 # What must restart after install.
```

### `shell_config` — profile file updates (Phase 4)

```python
"shell_config": {
    "env_vars": dict[str, str],    # {"GOPATH": "$HOME/go"}
    "path_append": list[str],      # ["$HOME/.cargo/bin"]
    "profile_file": str | None,    # override detected profile file
},
```

---

## Backward Compatibility

The recipe format is designed so that:

1. **Adding new fields never breaks existing recipes.**
   Simple recipes don't have `choices`, `inputs`, `data_packs`, etc.
   The resolver checks for field presence before using them.

2. **Phase 2 recipes survive unchanged through Phase 8.**
   The ruff recipe written in Phase 2 still works identically in Phase 8.
   No migration needed.

3. **The compatibility test:**
   ```python
   # Phase 2 recipe — written once, works forever:
   "ruff": {
       "label": "Ruff",
       "install": {"_default": _PIP + ["install", "ruff"]},
       "needs_sudo": {"_default": False},
       "verify": ["ruff", "--version"],
       "update": {"_default": _PIP + ["install", "--upgrade", "ruff"]},
   }
   # Phase 8 adds GPU, kernel, data_packs to OTHER recipes.
   # This recipe is unchanged. Resolver handles it the same way.
   ```

---

## What This Replaces

| Old structure | New location (in TOOL_RECIPES) |
|--------------|-------------------------------|
| `_NO_SUDO_RECIPES[tool] = [cmd]` | `recipe["install"]["_default"]` + `recipe["needs_sudo"]["_default"] = False` |
| `_SUDO_RECIPES[tool] = [cmd]` | `recipe["install"][pm]` + `recipe["needs_sudo"][pm] = True` |
| `CARGO_BUILD_DEPS = [...]` | `recipe["requires"]["packages"]["debian"]` (per-family) |
| `_RUNTIME_DEPS[tool] = {...}` | `recipe["requires"]["binaries"]` |
| `_TOOL_REQUIRES[tool] = "dep"` | `recipe["requires"]["binaries"]` |

---

## Traceability

| Field | First defined in | Phase introduced |
|-------|-----------------|-----------------|
| label, cli | phase2.2 §2.1 | Phase 2 |
| install, needs_sudo | phase2.2 §2.1 | Phase 2 |
| prefer | phase2.2 §2.1 | Phase 2 |
| requires.binaries | phase2.2 §2.1 | Phase 2 |
| requires.packages | phase2.2 §2.1 | Phase 2 |
| repo_setup | phase2.2 §2.1 | Phase 2 |
| post_env | phase2.2 §2.1 | Phase 2 |
| post_install | phase2.2 §2.1 | Phase 2 |
| verify | phase2.2 §2.1 | Phase 2 |
| update | phase2.2 §2.1 | Phase 2 |
| choices | scope-expansion §2.1 | Phase 4 |
| inputs | scope-expansion §2.2 | Phase 4 |
| install_variants | scope-expansion §2.1 | Phase 4 |
| shell_config | scope-expansion §2.6 | Phase 4 |
| requires.network | scope-expansion §2.16 | Phase 4 |
| requires.kernel_config | scope-expansion §2.5 | Phase 6 |
| requires.hardware | scope-expansion §2.9 | Phase 6 |
| risk | scope-expansion §2.5 | Phase 6 |
| data_packs | scope-expansion §2.10 | Phase 7 |
| config_templates | scope-expansion §2.12 | Phase 8 |
| restart_required | scope-expansion §2.8 | Phase 8 |
