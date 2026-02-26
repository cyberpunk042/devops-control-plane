# Phase 2: Recipe Unification — Implementation Plan

## Goal

Create a unified `TOOL_RECIPES` dict with per-platform install commands,
a `resolve_install_plan()` function that walks the dependency tree and
returns an ordered list of install steps for the detected system, a
multi-distro `check_system_deps()`, and a new `/api/audit/install-plan`
endpoint.

**All changes in `tool_install.py` and `routes_audit.py`.** Old recipes
and `install_tool()` stay for backward compat during migration.

---

## 1. Current State (Complete Inventory)

### `tool_install.py`

| Piece | Lines | What it is |
|-------|-------|-----------|
| `_NO_SUDO_RECIPES` | 34-46 | 11 tools: pip (7), npm (2), cargo (2). Flat `tool→cmd` |
| `_SUDO_RECIPES` | 49-83 | 30 tools: apt (18), snap (5), bash-curl (4), apt+misc (3). Flat `tool→cmd` |
| `CARGO_BUILD_DEPS` | 88 | Hardcoded `["pkg-config", "libssl-dev", "libcurl4-openssl-dev"]` — Debian-only names |
| `check_system_deps()` | 91-104 | Uses `dpkg-query` — Debian-only |
| `_analyse_install_failure()` | 111-271 | Post-failure stderr parser → remediation options |
| `_RUNTIME_DEPS` | 354-358 | Inline dict: `cargo`, `npm`, `node` binary lookups |
| `_TOOL_REQUIRES` | 360-363 | Inline dict: `cargo-audit→cargo`, `cargo-outdated→cargo` |
| `install_tool()` | 277-471 | Monolithic: recipe lookup + dep check + exec + error analysis |

### `routes_audit.py` endpoints

| Endpoint | What it does |
|----------|-------------|
| `POST /audit/install-tool` | Calls `install_tool()`, returns JSON |
| `POST /audit/remediate` | Streams command execution (SSE) |
| `POST /audit/check-deps` | Calls `check_system_deps()`, returns JSON |

### Problems that Phase 2 solves

1. **Recipes are Debian-only.** `apt-get install` commands won't work on Fedora/Alpine/macOS.
2. **`CARGO_BUILD_DEPS` is Debian-only.** `libssl-dev` doesn't exist on RHEL (`openssl-devel`).
3. **`check_system_deps()` is Debian-only.** `dpkg-query` doesn't exist on RHEL/Alpine.
4. **No recursive dependency resolution.** `cargo-outdated` needs `cargo` which needs `curl` — but this chain is hardcoded, not walked.
5. **No install plan.** Frontend has to do multiple round-trips and manage state across 6 different modals.
6. **snap recipes assume systemd.** WSL1, containers, and some servers lack systemd.

---

## 2. New Unified Recipe Format

### 2.1 The `TOOL_RECIPES` dict

Each tool has ONE entry. The entry contains ALL platforms:

```python
TOOL_RECIPES: dict[str, dict] = {
    # ── pip tools (universal, no platform variance) ──────────
    "ruff": {
        "label": "Ruff",
        "install": {"_default": _PIP + ["install", "ruff"]},
        "needs_sudo": {"_default": False},
    },
    # ... mypy, pytest, black, pip-audit, safety, bandit same pattern

    # ── npm tools (need npm binary) ─────────────────────────
    "eslint": {
        "label": "ESLint",
        "install": {"_default": ["npm", "install", "-g", "eslint"]},
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["npm"]},
    },

    # ── cargo tools (need cargo + system dev headers) ───────
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
                "macos":  ["pkg-config", "openssl@3"],
            },
        },
    },
    "cargo-outdated": {
        "label": "cargo-outdated",
        "install": {"_default": ["cargo", "install", "cargo-outdated"]},
        "needs_sudo": {"_default": False},
        "requires": {
            "binaries": ["cargo"],
            "packages": {
                "debian": ["pkg-config", "libssl-dev", "libcurl4-openssl-dev"],
                "rhel":   ["pkgconf-pkg-config", "openssl-devel", "libcurl-devel"],
                "alpine": ["pkgconf", "openssl-dev", "curl-dev"],
                "macos":  ["pkg-config", "openssl@3", "curl"],
            },
        },
    },

    # ── System tools (platform-variant) ─────────────────────
    "kubectl": {
        "label": "kubectl",
        "install": {
            "snap": ["snap", "install", "kubectl", "--classic"],
            "apt":  ["bash", "-c", "curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.31/deb/Release.key | gpg --dearmor -o /usr/share/keyrings/kubernetes-apt-keyring.gpg && echo 'deb [signed-by=/usr/share/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.31/deb/ /' > /etc/apt/sources.list.d/kubernetes.list && apt-get update && apt-get install -y kubectl"],
            "dnf":  ["bash", "-c", "cat <<'EOF' > /etc/yum.repos.d/kubernetes.repo\n[kubernetes]\nname=Kubernetes\nbaseurl=https://pkgs.k8s.io/core:/stable:/v1.31/rpm/\nenabled=1\ngpgcheck=1\ngpgkey=https://pkgs.k8s.io/core:/stable:/v1.31/rpm/repodata/repomd.xml.key\nEOF\ndnf install -y kubectl"],
            "brew": ["brew", "install", "kubectl"],
        },
        "needs_sudo": {"snap": True, "apt": True, "dnf": True, "brew": False},
        "prefer": ["snap", "apt", "dnf", "brew"],
    },
    "terraform": {
        "label": "Terraform",
        "install": {
            "snap": ["snap", "install", "terraform", "--classic"],
            "brew": ["brew", "install", "terraform"],
        },
        "needs_sudo": {"snap": True, "brew": False},
        "prefer": ["snap", "brew"],
    },

    # ── apt tools (with Debian/RHEL/Alpine/brew variants) ───
    "git": {
        "label": "Git",
        "install": {
            "apt": ["apt-get", "install", "-y", "git"],
            "dnf": ["dnf", "install", "-y", "git"],
            "apk": ["apk", "add", "git"],
            "pacman": ["pacman", "-S", "--noconfirm", "git"],
            "zypper": ["zypper", "install", "-y", "git"],
            "brew": ["brew", "install", "git"],
        },
        "needs_sudo": {"apt": True, "dnf": True, "apk": True, "pacman": True, "zypper": True, "brew": False},
    },

    # ── Runtime installers (bash-curl, universal) ───────────
    "cargo": {
        "label": "Cargo (Rust)",
        "install": {
            "_default": ["bash", "-c", "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.cargo/bin:$PATH"',
    },
    "rustc": {
        "label": "Rust compiler",
        "install": {
            "_default": ["bash", "-c", "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"],
        },
        "needs_sudo": {"_default": False},
        "requires": {"binaries": ["curl"]},
        "post_env": 'export PATH="$HOME/.cargo/bin:$PATH"',
    },
    "helm": {
        "label": "Helm",
        "install": {
            "_default": ["bash", "-c", "curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash"],
            "brew": ["brew", "install", "helm"],
        },
        "needs_sudo": {"_default": True, "brew": False},
        "requires": {"binaries": ["curl"]},
    },

    # ... etc for ALL tools
}
```

### 2.2 Design Rules

1. **`install` is a dict keyed by package manager id** (`apt`, `dnf`, `apk`, `snap`, `brew`, `pacman`, `zypper`).
2. **`_default`** means "works on any system" (pip, cargo, bash-curl scripts).
3. **`needs_sudo` is per-key** matching `install` keys.
4. **`requires.binaries`** lists tool IDs → recursive resolution.
5. **`requires.packages`** is keyed by distro family (`debian`, `rhel`, `alpine`, `macos`).
6. **`prefer`** is optional ordered list of preferred install methods.
7. **`post_env`** is shell env to set after install (only cargo tools need this).

### 2.3 Complete Tool Mapping

Every tool from `_NO_SUDO_RECIPES` + `_SUDO_RECIPES` gets an entry:

| Tool | Type | Platform difference? |
|------|------|---------------------|
| ruff, mypy, pytest, black, pip-audit, safety, bandit | pip | No — `_default` only |
| eslint, prettier | npm | No — `_default` only. Requires `npm` |
| cargo-audit, cargo-outdated | cargo | No — `_default` only. Requires `cargo` + system packages |
| helm, trivy, skaffold | bash-curl | Mostly `_default`, some have brew alt |
| cargo, rustc | bash-curl | `_default` only. Requires `curl` |
| kubectl, terraform | snap/apt/dnf/brew | YES — platform-variant |
| docker, docker-compose | apt/dnf | YES — platform-variant |
| git, curl, jq, make, gzip, rsync, ffmpeg, dig, openssl | apt/dnf/apk/pacman/zypper/brew | YES — same pkg name usually, diff command |
| gh | snap/apt/brew | YES — snap or brew |
| node | snap/apt/brew/dnf | YES — platform-variant |
| npm, npx | apt/brew/dnf | YES — platform-variant |
| pip, python | apt/dnf/apk/brew | YES — package name differs |
| go | snap/apt/brew | YES — platform-variant |
| xterm, gnome-terminal, etc. | apt | Debian-only, no other platform equiv |
| expect | apt/dnf/apk | YES — same name usually |

---

## 3. Multi-Distro `check_system_deps()`

### Current (Debian-only)

```python
def check_system_deps(packages: list[str]) -> dict:
    # uses dpkg-query only
```

### New

```python
def check_system_deps(packages: list[str], pkg_manager: str = "apt") -> dict:
    """Check which packages are installed.

    Args:
        packages: List of package names to check.
        pkg_manager: Package manager to use for checking (apt, dnf, apk, pacman, brew).

    Returns:
        {"missing": [...], "installed": [...]}
    """
```

Detection methods per package manager:

| pkg_manager | Check command | Installed if |
|-------------|--------------|-------------|
| `apt` | `dpkg-query -W -f='${Status}' PKG` | stdout contains "install ok installed" |
| `dnf` / `yum` | `rpm -q PKG` | exit code == 0 |
| `apk` | `apk info -e PKG` | exit code == 0 |
| `pacman` | `pacman -Qi PKG` | exit code == 0 |
| `zypper` | `rpm -q PKG` | exit code == 0 (same as dnf, uses rpm) |
| `brew` | `brew list PKG` | exit code == 0 |

Implementation:

```python
def _is_pkg_installed(pkg: str, pkg_manager: str) -> bool:
    """Check if a single package is installed."""
    try:
        if pkg_manager == "apt":
            r = subprocess.run(
                ["dpkg-query", "-W", "-f=${Status}", pkg],
                capture_output=True, text=True, timeout=10,
            )
            return "install ok installed" in r.stdout
        elif pkg_manager in ("dnf", "yum", "zypper"):
            r = subprocess.run(
                ["rpm", "-q", pkg],
                capture_output=True, timeout=10,
            )
            return r.returncode == 0
        elif pkg_manager == "apk":
            r = subprocess.run(
                ["apk", "info", "-e", pkg],
                capture_output=True, timeout=10,
            )
            return r.returncode == 0
        elif pkg_manager == "pacman":
            r = subprocess.run(
                ["pacman", "-Qi", pkg],
                capture_output=True, timeout=10,
            )
            return r.returncode == 0
        elif pkg_manager == "brew":
            r = subprocess.run(
                ["brew", "list", pkg],
                capture_output=True, timeout=10,
            )
            return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        pass
    return False


def check_system_deps(packages: list[str], pkg_manager: str = "apt") -> dict:
    """Check which packages are installed using the given package manager."""
    missing = []
    installed = []
    for pkg in packages:
        if _is_pkg_installed(pkg, pkg_manager):
            installed.append(pkg)
        else:
            missing.append(pkg)
    return {"missing": missing, "installed": installed}
```

### Backward compatibility

The old signature `check_system_deps(packages)` still works because
`pkg_manager` defaults to `"apt"`. The existing `/audit/check-deps`
endpoint continues working unchanged.

---

## 4. The Resolver: `resolve_install_plan()`

### Input

```python
def resolve_install_plan(
    tool: str,
    system_profile: dict,
) -> dict:
```

Where `system_profile` is the `os` dict from Phase 1's `_detect_os()`.

### Output

```python
{
    "tool": "cargo-outdated",
    "steps": [
        {
            "id": "system-packages",
            "type": "packages",
            "label": "Install system packages: pkg-config, libssl-dev, libcurl4-openssl-dev",
            "command": ["apt-get", "install", "-y", "pkg-config", "libssl-dev", "libcurl4-openssl-dev"],
            "needs_sudo": True,
            "packages": ["pkg-config", "libssl-dev", "libcurl4-openssl-dev"],
        },
        {
            "id": "cargo",
            "type": "tool",
            "label": "Install Cargo (Rust)",
            "command": ["bash", "-c", "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"],
            "needs_sudo": False,
            "post_env": "export PATH=\"$HOME/.cargo/bin:$PATH\"",
        },
        {
            "id": "cargo-outdated",
            "type": "tool",
            "label": "Install cargo-outdated",
            "command": ["bash", "-c", "export PATH=\"$HOME/.cargo/bin:$PATH\" && cargo install cargo-outdated"],
            "needs_sudo": False,
        },
    ],
}
```

Or `{"tool": "ruff", "steps": []}` if already installed.

### Algorithm

```python
def resolve_install_plan(tool: str, system_profile: dict) -> dict:
    """Resolve the full dependency tree into an ordered install plan."""
    family = system_profile.get("distro", {}).get("family", "unknown")
    pm = system_profile.get("package_manager", {})
    primary_pm = pm.get("primary", "apt")
    snap_ok = pm.get("snap_available", False)

    # 1. Check if tool already installed
    if shutil.which(tool):
        return {"tool": tool, "steps": []}

    # 2. Get recipe
    recipe = TOOL_RECIPES.get(tool)
    if not recipe:
        return {"tool": tool, "steps": [], "error": f"No recipe for '{tool}'"}

    # 3. Collect all required system packages (mapped to current family)
    all_packages: list[str] = []
    # 4. Collect all required tool binaries (recursive)
    tool_steps: list[dict] = []
    # 5. Walk dependencies recursively
    visited: set[str] = set()
    _collect_deps(tool, visited, all_packages, tool_steps, family, primary_pm, snap_ok)

    steps: list[dict] = []

    # 6. Batch system packages into one step
    if all_packages:
        missing = check_system_deps(all_packages, primary_pm)["missing"]
        if missing:
            pkg_cmd = _build_pkg_install_cmd(missing, primary_pm)
            steps.append({
                "id": "system-packages",
                "type": "packages",
                "label": f"Install system packages: {', '.join(missing)}",
                "command": pkg_cmd,
                "needs_sudo": primary_pm != "brew",
                "packages": missing,
            })

    # 7. Add tool steps (already in topological order from recursion)
    steps.extend(tool_steps)

    return {"tool": tool, "steps": steps}
```

Helper to collect deps recursively:

```python
def _collect_deps(
    tool: str,
    visited: set[str],
    all_packages: list[str],
    tool_steps: list[dict],
    family: str,
    primary_pm: str,
    snap_ok: bool,
):
    """Recursively collect dependencies, depth-first."""
    if tool in visited:
        return
    visited.add(tool)

    recipe = TOOL_RECIPES.get(tool)
    if not recipe:
        return

    requires = recipe.get("requires", {})

    # Recurse into binary dependencies first (depth-first = deps before dependents)
    for dep_bin in requires.get("binaries", []):
        _collect_deps(dep_bin, visited, all_packages, tool_steps, family, primary_pm, snap_ok)

    # Collect system packages for this tool
    pkg_map = requires.get("packages", {})
    pkgs = pkg_map.get(family, pkg_map.get("_default", []))
    for pkg in pkgs:
        if pkg not in all_packages:
            all_packages.append(pkg)

    # Add this tool as a step (if not already installed)
    if not shutil.which(tool):
        install_cmd, needs_sudo = _pick_install_method(recipe, primary_pm, snap_ok)
        if install_cmd:
            step: dict = {
                "id": tool,
                "type": "tool",
                "label": f"Install {recipe['label']}",
                "command": install_cmd,
                "needs_sudo": needs_sudo,
            }
            if recipe.get("post_env"):
                step["post_env"] = recipe["post_env"]
            tool_steps.append(step)
```

Helper to pick the right install method:

```python
def _pick_install_method(
    recipe: dict,
    primary_pm: str,
    snap_ok: bool,
) -> tuple[list[str] | None, bool]:
    """Pick the best install method for this recipe given the system.

    Checks in order:
    1. Recipe's `prefer` list (if present)
    2. primary_pm match
    3. snap (if snap_ok and recipe has snap)
    4. _default fallback
    """
    install = recipe.get("install", {})
    needs_sudo_map = recipe.get("needs_sudo", {})
    prefer = recipe.get("prefer", [])

    # Check prefer list first
    for method in prefer:
        if method == "snap" and not snap_ok:
            continue
        if method in install:
            return install[method], needs_sudo_map.get(method, True)

    # Check primary package manager
    if primary_pm in install:
        return install[primary_pm], needs_sudo_map.get(primary_pm, True)

    # Check snap
    if snap_ok and "snap" in install:
        return install["snap"], needs_sudo_map.get("snap", True)

    # Fallback to _default
    if "_default" in install:
        return install["_default"], needs_sudo_map.get("_default", False)

    return None, False
```

Helper to build package install command:

```python
def _build_pkg_install_cmd(packages: list[str], pm: str) -> list[str]:
    """Build the install command for a list of packages."""
    if pm == "apt":
        return ["apt-get", "install", "-y"] + packages
    elif pm == "dnf":
        return ["dnf", "install", "-y"] + packages
    elif pm == "yum":
        return ["yum", "install", "-y"] + packages
    elif pm == "apk":
        return ["apk", "add"] + packages
    elif pm == "pacman":
        return ["pacman", "-S", "--noconfirm"] + packages
    elif pm == "zypper":
        return ["zypper", "install", "-y"] + packages
    elif pm == "brew":
        return ["brew", "install"] + packages
    return ["echo", "No package manager for:", *packages]
```

### 4.1 Post-env Handling

When a tool has `post_env` (like cargo), the NEXT step that uses that
tool's binary needs the env prepended. The resolver handles this by
wrapping the command:

```python
# In the final step for cargo-outdated, if cargo has post_env:
# Original: ["cargo", "install", "cargo-outdated"]
# Wrapped:  ["bash", "-c", "export PATH=\"$HOME/.cargo/bin:$PATH\" && cargo install cargo-outdated"]
```

This wrapping happens in `_collect_deps` when building tool_steps for
tools that depend on a binary with `post_env`.

---

## 5. New Endpoint: `/api/audit/install-plan`

```python
@audit_bp.route("/audit/install-plan", methods=["POST"])
def audit_install_plan():
    """Resolve install plan for a tool — returns ordered steps."""
    from src.core.services.audit.l0_detection import _detect_os
    from src.core.services.tool_install import resolve_install_plan

    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "")
    if not tool:
        return jsonify({"error": "No tool specified"}), 400

    system_profile = _detect_os()
    plan = resolve_install_plan(tool, system_profile)
    return jsonify(plan), 200
```

### Why call `_detect_os()` here instead of using cache?

The install plan endpoint needs the FRESHEST system profile (the user
may have just installed something). Calling `_detect_os()` directly
takes ~30ms (Phase 1 timing). The heavy parts (tool detection, module
scanning) are NOT called.

---

## 6. Update `/audit/check-deps` Endpoint

```python
@audit_bp.route("/audit/check-deps", methods=["POST"])
def audit_check_deps():
    """Check if system packages are installed."""
    from src.core.services.audit.l0_detection import _detect_os
    from src.core.services.tool_install import check_system_deps

    body = request.get_json(silent=True) or {}
    packages = body.get("packages", [])
    if not packages:
        return jsonify({"missing": [], "installed": []}), 200

    # Auto-detect package manager if not provided
    pkg_manager = body.get("pkg_manager")
    if not pkg_manager:
        os_info = _detect_os()
        pkg_manager = os_info.get("package_manager", {}).get("primary", "apt")

    result = check_system_deps(packages, pkg_manager)
    return jsonify(result), 200
```

---

## 7. Files Changed

| File | What changes |
|------|-------------|
| `src/core/services/tool_install.py` | Add `TOOL_RECIPES`, `_is_pkg_installed()`, update `check_system_deps()`, add `_pick_install_method()`, `_build_pkg_install_cmd()`, `_collect_deps()`, `resolve_install_plan()` |
| `src/ui/web/routes_audit.py` | Add `/audit/install-plan` endpoint, update `/audit/check-deps` for auto-detect |

### What stays unchanged

| Piece | Why |
|-------|-----|
| `_NO_SUDO_RECIPES` | Backward compat — `install_tool()` still uses them |
| `_SUDO_RECIPES` | Backward compat — `install_tool()` still uses them |
| `install_tool()` | Still used by `/audit/install-tool` (Phase 3 will migrate frontend) |
| `_analyse_install_failure()` | Still used as post-failure fallback |
| `_RUNTIME_DEPS`, `_TOOL_REQUIRES` | Still used by `install_tool()` |
| `CARGO_BUILD_DEPS` | Still referenced by `_analyse_install_failure()` |

---

## 8. Implementation Steps

### Step 1: Add `TOOL_RECIPES` dict

Add a new section in `tool_install.py` after the existing recipes.
Map EVERY tool from `_NO_SUDO_RECIPES` + `_SUDO_RECIPES` into the
new format. Add platform variants for tools that need them.

### Step 2: Add `_is_pkg_installed()` and update `check_system_deps()`

Add `_is_pkg_installed()` helper function.
Add `pkg_manager` parameter to `check_system_deps()` with default `"apt"`.

### Step 3: Add resolver helpers

Add `_pick_install_method()`, `_build_pkg_install_cmd()`, `_collect_deps()`.

### Step 4: Add `resolve_install_plan()`

The main public resolver function.

### Step 5: Add `/api/audit/install-plan` endpoint

In `routes_audit.py`.

### Step 6: Update `/audit/check-deps` endpoint

Auto-detect package manager when not provided.

### Step 7: Verification

Test the plan endpoint with different tools:
- `curl /api/audit/install-plan -d '{"tool":"ruff"}'` → 0 steps (already installed) or 1 pip step
- `curl /api/audit/install-plan -d '{"tool":"cargo-outdated"}'` → up to 3 steps
- `curl /api/audit/install-plan -d '{"tool":"kubectl"}'` → 1 step (snap or apt based on system)

---

## 9. Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Circular dependency in recipes | `visited` set in `_collect_deps` prevents infinite recursion |
| Missing recipe for a tool | Returns `{"steps": [], "error": "No recipe"}` — non-breaking |
| Wrong package names for a distro | Explicit mapping per family, not guessing |
| `_detect_os()` slow on plan endpoint | Phase 1 showed ~30ms — acceptable |
| `check_system_deps` slow with many packages | Packages are batched (one dpkg-query per pkg, ~5ms each) |
| Old `install_tool()` still used | Stays unchanged — no regression |

---

## 10. What This Enables for Phase 3

With the plan endpoint returning ordered steps:
- Frontend calls ONE endpoint → gets the full plan
- Frontend walks steps with stacked modals (Phase 3)
- Each step knows if it needs sudo → frontend shows password field
- System packages are batched → one sudo prompt for all
- Post-env is attached to steps → frontend can pass env to execution
