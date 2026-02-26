# Phase 2.3 — Resolver Engine — Full Analysis

## What This Sub-Phase Delivers

The resolver takes a tool ID + the system profile and produces an
ordered execution plan. The plan is a list of steps the frontend
(or CLI) can execute one by one.

Three functions:
1. `_pick_install_method()` — choose which install command to use
2. `_collect_deps()` — recursive dependency walker
3. `resolve_install_plan()` — orchestrate everything into an ordered plan

One endpoint:
- `POST /audit/install-plan` — returns the plan as JSON

---

## 1. Inputs and Outputs

### Input: tool ID + system profile

The tool ID is a string like `"cargo-outdated"`.

The system profile comes from Phase 1's `_detect_os()`:
```python
{
    "distro": {
        "family": "debian",  # debian | rhel | alpine | arch | suse | unknown
        ...
    },
    "package_manager": {
        "primary": "apt",
        "available": ["apt"],
        "snap_available": True,
    },
    "capabilities": {
        "systemd": True,
        "has_sudo": True,
        "is_root": False,
    },
    "container": {
        "in_container": False,
    },
    ...
}
```

### Output: ordered plan

```python
{
    "tool": "cargo-outdated",
    "label": "cargo-outdated",
    "needs_sudo": True,           # ANY step in the plan needs sudo
    "already_installed": False,
    "steps": [
        {
            "type": "packages",
            "label": "Install system packages",
            "command": ["apt-get", "install", "-y",
                        "curl", "pkg-config", "libssl-dev",
                        "libcurl4-openssl-dev"],
            "needs_sudo": True,
            "packages": ["curl", "pkg-config", "libssl-dev",
                         "libcurl4-openssl-dev"],
        },
        {
            "type": "tool",
            "label": "Install Cargo (Rust)",
            "tool_id": "cargo",
            "command": ["bash", "-c",
                        "curl --proto '=https' --tlsv1.2 -sSf "
                        "https://sh.rustup.rs | sh -s -- -y"],
            "needs_sudo": False,
        },
        {
            "type": "tool",
            "label": "Install cargo-outdated",
            "tool_id": "cargo-outdated",
            "command": ["bash", "-c",
                        'export PATH="$HOME/.cargo/bin:$PATH" '
                        '&& cargo install cargo-outdated'],
            "needs_sudo": False,
        },
        {
            "type": "verify",
            "label": "Verify cargo-outdated",
            "command": ["bash", "-c",
                        'export PATH="$HOME/.cargo/bin:$PATH" '
                        '&& cargo outdated --version'],
            "needs_sudo": False,
        },
    ],
}
```

### Step types

| Type | When emitted | Source |
|------|-------------|--------|
| `repo_setup` | Before packages, when a tool's install method has `repo_setup` | Recipe `repo_setup[pm]` |
| `packages` | When system packages need installing (batched) | Recipe `requires.packages` + batchable binary deps |
| `tool` | For each tool that needs installing | Recipe `install[method]` |
| `post_install` | After a tool's install step | Recipe `post_install` (condition-filtered) |
| `verify` | Last step, confirms the target tool works | Recipe `verify` |

---

## 2. Function 1: `_pick_install_method()`

### Purpose

Given a recipe and the system's capabilities, choose which install
method (key from the recipe's `install` dict) to use.

### Resolution order

1. Recipe's `prefer` list (if present) — try each in order
2. System's primary package manager (apt, dnf, apk, etc.)
3. snap (if `snap_available` and recipe has `snap` key)
4. `_default` fallback

### Logic

```python
def _pick_install_method(
    recipe: dict,
    primary_pm: str,
    snap_available: bool,
) -> str | None:
    """Pick the best install method for a recipe on this system.

    Args:
        recipe: A TOOL_RECIPES entry.
        primary_pm: The system's primary package manager (e.g. "apt").
        snap_available: Whether snap is available on this system.

    Returns:
        A key from recipe["install"], or None if no method is available.
    """
    install = recipe.get("install", {})
    if not install:
        return None

    # 1. Recipe's preferred order
    for method in recipe.get("prefer", []):
        if method == "snap" and not snap_available:
            continue
        if method in install:
            return method

    # 2. System's primary pm
    if primary_pm in install:
        return primary_pm

    # 3. snap
    if snap_available and "snap" in install:
        return "snap"

    # 4. _default
    if "_default" in install:
        return "_default"

    # 5. Any available pm
    # If the recipe has methods for other pms but not our primary,
    # try to find one that's on PATH. Example: recipe has "dnf"
    # but we detected "yum" as primary. yum is a symlink to dnf.
    # This is rare but possible.
    for method in install:
        if method.startswith("_"):
            continue
        if shutil.which(method):
            return method

    return None
```

### Scenarios

**Scenario A: kubectl on Ubuntu with snap**
- primary_pm = "apt"
- snap_available = True
- prefer = ["snap", "brew", "_default"]
- Step 1: try "snap" → snap_available=True, "snap" in install → **"snap"**

**Scenario B: kubectl on Alpine (no snap)**
- primary_pm = "apk"
- snap_available = False
- prefer = ["snap", "brew", "_default"]
- Step 1: try "snap" → snap_available=False → skip
- Step 1: try "brew" → "brew" not in install... wait, it IS in install
  Actually: is `brew` on PATH on Alpine? No.
  But `_pick_install_method` doesn't check if brew is on PATH for
  preferred methods. It just checks if the key exists in `install`.
  On Alpine, `brew` wouldn't be installed, so `brew install kubectl`
  would fail at execution time.

  **Problem:** `prefer` should respect whether the method is actually
  available on this system, not just whether the recipe has it.

  **Fix:** For non-_default methods, check availability:
  - System pm methods (apt, dnf, etc.): available if it matches primary_pm
  - snap: available if snap_available
  - brew: available if `shutil.which("brew")`

  Updated logic for prefer loop:
  ```python
  for method in recipe.get("prefer", []):
      if method == "snap":
          if not snap_available:
              continue
      elif method == "brew":
          if not shutil.which("brew"):
              continue
      elif method not in (primary_pm, "_default"):
          # It's a pm key that doesn't match our system
          continue
      if method in install:
          return method
  ```

**Scenario C: kubectl on Fedora (no snap, no brew)**
- primary_pm = "dnf"
- snap_available = False
- prefer = ["snap", "brew", "_default"]
- try "snap" → no → skip
- try "brew" → brew not on PATH → skip
- try "_default" → exists → **"_default"** (binary download)

**Scenario D: git on Fedora**
- primary_pm = "dnf"
- snap_available = True
- prefer = not set
- Step 2: "dnf" in install → **"dnf"**

**Scenario E: ruff (pip tool)**
- primary_pm = "apt"
- install only has "_default"
- Step 2: "apt" not in install → skip
- Step 3: "snap" not in install → skip
- Step 4: "_default" in install → **"_default"**

**Scenario F: terraform on Alpine (no snap, no brew)**
- primary_pm = "apk"
- snap_available = False
- install has only: snap, brew
- prefer = not set (or could be ["snap", "brew"])
- Step 2: "apk" not in install → skip
- Step 3: snap not available → skip
- Step 4: "_default" not in install → skip
- Step 5: try remaining methods - "snap" not on PATH, "brew" not on PATH
- Returns **None** → resolver reports: "No install method available
  for terraform on this system"

This is correct! Terraform on Alpine without snap or brew genuinely
can't be installed by our system. The plan should say so.

### What the resolver does with the picked method

Once a method is picked, the resolver uses:
- `recipe["install"][method]` → the install command
- `recipe["needs_sudo"][method]` → whether sudo is needed
- `recipe.get("update", {}).get(method)` → the update command (if needed)
- The method key itself → to check if it's a batchable package install

### How to detect "batchable" package installs

A tool's install step is batchable into the system packages step when
the picked method matches the system's primary package manager.

```python
def _is_batchable(method: str, primary_pm: str) -> bool:
    """Is this install method a system package install that can be batched?"""
    return method == primary_pm
```

If batchable:
- Extract the package name(s) from the install command
  (everything after the flags: apt-get install -y **PKG**)
- Add to the packages batch instead of creating a tool step

If NOT batchable:
- Create a tool step with the full command

---

## 3. Function 2: `_collect_deps()`

### Purpose

Walk the dependency tree depth-first. For each uninstalled dependency,
determine whether it's a batchable package or a tool step. Collect:
- A set of system packages to batch
- An ordered list of tool steps (deepest dep first)
- Post-env propagations

### The algorithm

```
_collect_deps(tool_id, profile, visited):
    if tool_id in visited:
        return  # cycle detection
    visited.add(tool_id)

    recipe = TOOL_RECIPES[tool_id]
    cli = recipe.get("cli", tool_id)

    # Skip if already installed
    if shutil.which(cli):
        return

    # 1. Recurse into binary deps first (depth-first)
    for dep_id in recipe.get("requires", {}).get("binaries", []):
        _collect_deps(dep_id, profile, visited)

    # 2. Collect system packages for this tool
    family = profile["distro"]["family"]
    pm = profile["package_manager"]["primary"]
    pkg_map = recipe.get("requires", {}).get("packages", {})
    packages = pkg_map.get(family, [])
    for pkg in packages:
        if not _is_pkg_installed(pkg, pm):
            batch_packages.add(pkg)

    # 3. Pick install method for this tool
    method = _pick_install_method(recipe, pm, profile["package_manager"]["snap_available"])

    # 4. Is this tool's install itself a batchable package install?
    if _is_batchable(method, pm):
        # Extract package name from command and add to batch
        pkg_name = _extract_package_from_cmd(recipe["install"][method])
        if not _is_pkg_installed(pkg_name, pm):
            batch_packages.add(pkg_name)
    else:
        # Create a tool step
        tool_steps.append({
            "tool_id": tool_id,
            "recipe": recipe,
            "method": method,
        })
```

### The state objects

`_collect_deps` mutates shared state:
- `batch_packages: list[str]` — system packages to install in one batch
- `tool_steps: list[dict]` — ordered tool install steps
- `post_env_stack: list[str]` — accumulated post_env from deps
- `visited: set[str]` — cycle detection

These are collected during the walk and then assembled into the plan
by `resolve_install_plan()`.

### Extracting package names from commands

When a tool like `curl` has `install.apt: ["apt-get", "install", "-y", "curl"]`,
we need to extract `"curl"` from that command to add it to the batch.

Rule: for a pm install command, the package names are everything after
the flags. The flags vary by pm:

| PM | Command prefix | Package names start at index |
|----|---------------|------------------------------|
| apt | `apt-get install -y` | 3 |
| dnf | `dnf install -y` | 3 |
| yum | `yum install -y` | 3 |
| apk | `apk add` | 2 |
| pacman | `pacman -S --noconfirm` | 3 |
| zypper | `zypper install -y` | 3 |
| brew | `brew install` | 2 |

```python
def _extract_packages_from_cmd(cmd: list[str], pm: str) -> list[str]:
    """Extract package names from a pm install command."""
    if pm in ("apt", "dnf", "yum", "zypper"):
        # apt-get install -y PKG1 PKG2
        # dnf install -y PKG1 PKG2
        return [c for c in cmd[3:] if not c.startswith("-")]
    if pm in ("apk", "brew"):
        # apk add PKG1 PKG2
        # brew install PKG1 PKG2
        return [c for c in cmd[2:] if not c.startswith("-")]
    if pm == "pacman":
        # pacman -S --noconfirm PKG1 PKG2
        return [c for c in cmd[3:] if not c.startswith("-")]
    return []
```

### Depth-first ordering

The recursion naturally produces depth-first order:
```
cargo-outdated
  → cargo (recurse first)
    → curl (recurse first)
      curl has no binary deps
      curl is batchable → add "curl" to packages
    cargo is NOT batchable (_default) → add cargo to tool_steps
  cargo-outdated is NOT batchable (_default) → add cargo-outdated to tool_steps
```

Result:
- batch_packages = ["curl", "pkg-config", "libssl-dev", "libcurl4-openssl-dev"]
- tool_steps = [cargo, cargo-outdated]  (depth-first order = dependency order)

This is correct — cargo must be installed before cargo-outdated.

---

## 4. Function 3: `resolve_install_plan()`

### Purpose

Orchestrate everything: walk deps, build the plan, apply post-env,
filter conditions, add verify step.

### The algorithm

```python
def resolve_install_plan(
    tool: str,
    system_profile: dict,
) -> dict:
    """Produce an ordered install plan for a tool.

    Returns a plan dict with steps, or an error if the tool can't
    be installed on this system.
    """
    # 0. Tool already installed?
    recipe = TOOL_RECIPES.get(tool)
    if not recipe:
        return {"tool": tool, "error": f"No recipe for '{tool}'"}

    cli = recipe.get("cli", tool)
    if shutil.which(cli):
        return {
            "tool": tool,
            "label": recipe["label"],
            "already_installed": True,
            "steps": [],
        }

    # 1. Collect deps
    batch_packages = []     # system packages to batch
    tool_steps = []         # ordered tool install steps
    post_env_map = {}       # tool_id → post_env string
    visited = set()

    pm = system_profile["package_manager"]["primary"]
    family = system_profile["distro"]["family"]
    snap_ok = system_profile["package_manager"]["snap_available"]

    _collect_deps(
        tool, system_profile,
        visited, batch_packages, tool_steps, post_env_map,
    )

    # 2. Build plan steps
    steps = []

    # 2a. Repo setup steps (if any tool step has repo_setup for this pm)
    for ts in tool_steps:
        repo_steps = ts["recipe"].get("repo_setup", {}).get(pm, [])
        for rs in repo_steps:
            steps.append({
                "type": "repo_setup",
                "label": rs["label"],
                "tool_id": ts["tool_id"],
                "command": rs["command"],
                "needs_sudo": rs.get("needs_sudo", True),
            })

    # 2b. System packages batch (single step)
    if batch_packages:
        cmd = _build_pkg_install_cmd(batch_packages, pm)
        steps.append({
            "type": "packages",
            "label": "Install system packages",
            "command": cmd,
            "needs_sudo": True,  # package installs always need sudo (except brew)
            "packages": batch_packages,
        })
        # Brew exception
        if pm == "brew":
            steps[-1]["needs_sudo"] = False

    # 2c. Tool install steps (in dependency order)
    accumulated_env = ""
    for ts in tool_steps:
        tool_id = ts["tool_id"]
        recipe_t = ts["recipe"]
        method = ts["method"]
        cmd = list(recipe_t["install"][method])
        sudo = recipe_t["needs_sudo"].get(method, False)

        # Apply accumulated post_env from earlier deps
        if accumulated_env:
            cmd = _wrap_with_env(cmd, accumulated_env)
            # Wrapping changes the command — sudo might need adjustment
            # If we wrapped in bash -c, sudo is applied differently

        steps.append({
            "type": "tool",
            "label": f"Install {recipe_t['label']}",
            "tool_id": tool_id,
            "command": cmd,
            "needs_sudo": sudo,
        })

        # Accumulate post_env for subsequent steps
        pe = recipe_t.get("post_env", "")
        if pe:
            accumulated_env = pe if not accumulated_env else f"{accumulated_env} && {pe}"

    # 2d. Post-install steps (condition-filtered)
    for ts in tool_steps:
        recipe_t = ts["recipe"]
        for pis in recipe_t.get("post_install", []):
            condition = pis.get("condition")
            if not _evaluate_condition(condition, system_profile):
                continue
            steps.append({
                "type": "post_install",
                "label": pis["label"],
                "tool_id": ts["tool_id"],
                "command": pis["command"],
                "needs_sudo": pis.get("needs_sudo", False),
            })

    # 2e. Verify step
    verify_cmd = recipe.get("verify")
    if verify_cmd:
        cmd = list(verify_cmd)
        if accumulated_env:
            cmd = _wrap_with_env(cmd, accumulated_env)
        steps.append({
            "type": "verify",
            "label": f"Verify {recipe['label']}",
            "command": cmd,
            "needs_sudo": False,
        })

    # 3. Compute plan-level flags
    any_sudo = any(s["needs_sudo"] for s in steps)

    return {
        "tool": tool,
        "label": recipe["label"],
        "already_installed": False,
        "needs_sudo": any_sudo,
        "steps": steps,
    }
```

---

## 5. Post-Env Propagation — The Tricky Part

When cargo is installed via rustup, the binary ends up in `~/.cargo/bin`
which is NOT on the current shell's PATH. Any subsequent step that uses
`cargo` (like `cargo install cargo-outdated`) needs the PATH export
prepended.

### How _wrap_with_env works

```python
def _wrap_with_env(cmd: list[str], env_setup: str) -> list[str]:
    """Wrap a command with environment setup.

    If the command is already a bash -c command, prepend the env setup.
    If not, wrap the whole thing in bash -c.

    Args:
        cmd: Original command list.
        env_setup: Shell commands to prepend (e.g. 'export PATH=...')

    Returns:
        New command list with env setup prepended.
    """
    if cmd[0] == "bash" and cmd[1] == "-c":
        # Already wrapped — prepend to the bash expression
        return ["bash", "-c", f"{env_setup} && {cmd[2]}"]
    else:
        # Plain command — wrap in bash -c
        plain = " ".join(shlex.quote(c) for c in cmd)
        return ["bash", "-c", f"{env_setup} && {plain}"]
```

### Example trace

cargo-outdated install plan on Ubuntu, nothing installed:

1. System packages step:
   `["apt-get", "install", "-y", "curl", "pkg-config", "libssl-dev", "libcurl4-openssl-dev"]`
   No env wrapping needed (apt-get doesn't depend on cargo).

2. cargo install step:
   Original: `["bash", "-c", "curl --proto '=https' ... | sh -s -- -y"]`
   No accumulated_env yet → no wrapping.
   After this step: accumulated_env = `'export PATH="$HOME/.cargo/bin:$PATH"'`

3. cargo-outdated install step:
   Original: `["cargo", "install", "cargo-outdated"]`
   accumulated_env exists → wrap:
   Result: `["bash", "-c", 'export PATH="$HOME/.cargo/bin:$PATH" && cargo install cargo-outdated']`

4. Verify step:
   Original: `["cargo", "outdated", "--version"]`
   accumulated_env exists → wrap:
   Result: `["bash", "-c", 'export PATH="$HOME/.cargo/bin:$PATH" && cargo outdated --version']`

### What about sudo + env wrapping?

If a step needs sudo AND has env wrapping, the order matters:

```bash
# WRONG: sudo doesn't propagate PATH from the env setup
sudo bash -c 'export PATH=... && some-command'
# This works because everything runs as root inside bash -c

# RIGHT: the env setup is inside the bash -c, so it works
sudo bash -c 'export PATH="$HOME/.cargo/bin:$PATH" && some-command'
```

Actually, `$HOME` inside `sudo bash -c` resolves to root's home, not
the user's. This is a problem.

**Fix:** When sudo is involved with post_env, use the USER's home:
```bash
sudo -E bash -c '...'   # -E preserves environment
```
Or use `~user` syntax. But this gets complicated.

**Current scope:** No tool that needs post_env (cargo) also needs sudo.
Cargo installs to user space, doesn't need sudo. cargo-audit installs
via `cargo install` which also doesn't need sudo. The scenario of
sudo + post_env doesn't occur in our current recipe set.

**Decision:** Don't handle sudo + post_env combination in Phase 2.3.
If it arises in the future, add it then. Document this limitation.

---

## 6. Condition Evaluation

### The function

```python
def _evaluate_condition(
    condition: str | None,
    system_profile: dict,
) -> bool:
    """Evaluate a post_install condition against the system profile.

    Args:
        condition: One of "has_systemd", "not_root", "not_container", or None.
        system_profile: Phase 1 system detection output.

    Returns:
        True if the condition is met (step should be included).
    """
    if condition is None:
        return True
    if condition == "has_systemd":
        return system_profile.get("capabilities", {}).get("systemd", False)
    if condition == "not_root":
        return not system_profile.get("capabilities", {}).get("is_root", False)
    if condition == "not_container":
        return not system_profile.get("container", {}).get("in_container", False)
    # Unknown condition — default to include (safe)
    logger.warning("Unknown condition: %s", condition)
    return True
```

### Trace: Docker on WSL2 without systemd, running as root

```python
system_profile = {
    "capabilities": {"systemd": False, "is_root": True},
    "container": {"in_container": False},
}

# Post-install step 1: Start Docker
_evaluate_condition("has_systemd", profile)  → False → EXCLUDED

# Post-install step 2: Enable Docker
_evaluate_condition("has_systemd", profile)  → False → EXCLUDED

# Post-install step 3: Add user to docker group
_evaluate_condition("not_root", profile)  → False → EXCLUDED

# Result: 0 post-install steps. Only the install + verify steps.
```

### Trace: Docker on Ubuntu desktop, regular user

```python
system_profile = {
    "capabilities": {"systemd": True, "is_root": False},
    "container": {"in_container": False},
}

# Step 1: Start Docker → has_systemd → True → INCLUDED
# Step 2: Enable Docker → has_systemd → True → INCLUDED
# Step 3: Add to group → not_root → True → INCLUDED

# Result: 3 post-install steps.
```

---

## 7. Complete Scenario Traces

**Full scenario matrix (55 scenarios, 10 angles):**
`tool-install-v2-phase2.3-scenarios.md`

The scenarios below are the key inline traces. The dedicated file covers
all platform variants, edge cases, container environments, service
management, post-env propagation, batching logic, error conditions,
privilege contexts, and update plans.

### Scenario 1: cargo-outdated on fresh Ubuntu (nothing installed)

```
Input: tool="cargo-outdated", primary_pm="apt", family="debian",
       snap_available=True, systemd=True, is_root=False

_collect_deps("cargo-outdated"):
  recipe has requires.binaries = ["cargo"]
  
  _collect_deps("cargo"):
    recipe has requires.binaries = ["curl"]
    
    _collect_deps("curl"):
      shutil.which("curl") → None (not installed)
      no binary deps
      _pick_install_method(curl, "apt", snap_ok=True) → "apt"
      _is_batchable("apt", "apt") → True
      Extract package: "curl" → add to batch_packages
    
    shutil.which("cargo") → None
    no system packages in cargo recipe
    _pick_install_method(cargo, "apt", True) → "_default"
    _is_batchable("_default", "apt") → False
    Add {"tool_id": "cargo", method: "_default"} to tool_steps
    post_env_map["cargo"] = 'export PATH="$HOME/.cargo/bin:$PATH"'
  
  shutil.which("cargo-outdated") → None
  system packages: debian → ["pkg-config", "libssl-dev", "libcurl4-openssl-dev"]
  _is_pkg_installed("pkg-config", "apt") → False → add to batch
  _is_pkg_installed("libssl-dev", "apt") → False → add to batch
  _is_pkg_installed("libcurl4-openssl-dev", "apt") → False → add to batch
  _pick_install_method(cargo-outdated, "apt", True) → "_default"
  _is_batchable("_default", "apt") → False
  Add {"tool_id": "cargo-outdated", method: "_default"} to tool_steps

State after _collect_deps:
  batch_packages = ["curl", "pkg-config", "libssl-dev", "libcurl4-openssl-dev"]
  tool_steps = [
    {"tool_id": "cargo", method: "_default"},
    {"tool_id": "cargo-outdated", method: "_default"},
  ]

Build plan:
  Step 1 (packages): apt-get install -y curl pkg-config libssl-dev libcurl4-openssl-dev
    needs_sudo: True
  Step 2 (tool): bash -c "curl ... | sh -s -- -y"
    needs_sudo: False
    accumulated_env now = 'export PATH="$HOME/.cargo/bin:$PATH"'
  Step 3 (tool): bash -c 'export PATH=... && cargo install cargo-outdated'
    needs_sudo: False
  Step 4 (verify): bash -c 'export PATH=... && cargo outdated --version'
    needs_sudo: False

Plan: needs_sudo=True (step 1), 4 steps
```

### Scenario 2: eslint on Ubuntu, npm is missing

```
Input: tool="eslint", primary_pm="apt", family="debian",
       snap_available=True

_collect_deps("eslint"):
  requires.binaries = ["npm"]
  
  _collect_deps("npm"):
    shutil.which("npm") → None
    _pick_install_method(npm, "apt", True) → "apt"
    _is_batchable("apt", "apt") → True
    Extract package: "npm" → add to batch_packages
  
  shutil.which("eslint") → None
  no system packages
  _pick_install_method(eslint, "apt", True) → "_default"
  _is_batchable("_default", "apt") → False
  Add {"tool_id": "eslint", method: "_default"} to tool_steps

Plan:
  Step 1 (packages): apt-get install -y npm
    needs_sudo: True
  Step 2 (tool): npm install -g eslint
    needs_sudo: False
  Step 3 (verify): eslint --version
    needs_sudo: False
```

### Scenario 3: eslint on Fedora, npm is missing

```
Input: tool="eslint", primary_pm="dnf", family="rhel",
       snap_available=False

_collect_deps("eslint"):
  requires.binaries = ["npm"]
  
  _collect_deps("npm"):
    shutil.which("npm") → None
    _pick_install_method(npm, "dnf", False) → "dnf"
    _is_batchable("dnf", "dnf") → True
    Extract package: "npm" → add to batch_packages
  
  (same as above)

Plan:
  Step 1 (packages): dnf install -y npm
    needs_sudo: True
  Step 2 (tool): npm install -g eslint
    needs_sudo: False
  Step 3 (verify): eslint --version
```

### Scenario 4: kubectl on Alpine (no snap, no brew)

```
Input: tool="kubectl", primary_pm="apk", family="alpine",
       snap_available=False

_collect_deps("kubectl"):
  requires.binaries = ["curl"]
  
  _collect_deps("curl"):
    shutil.which("curl") → None (minimal Alpine)
    _pick_install_method(curl, "apk", False) → "apk"
    _is_batchable("apk", "apk") → True
    Extract package: "curl" → add to batch
  
  shutil.which("kubectl") → None
  _pick_install_method(kubectl, "apk", False):
    prefer = ["snap", "brew", "_default"]
    "snap" → snap_available=False → skip
    "brew" → shutil.which("brew")=None → skip
    "_default" → exists → "_default"
  _is_batchable("_default", "apk") → False
  Add kubectl step

Plan:
  Step 1 (packages): apk add curl
    needs_sudo: True (apk needs root on Alpine)
  Step 2 (tool): bash -c 'curl -LO ... && chmod +x kubectl && sudo mv kubectl /usr/local/bin/'
    needs_sudo: True
  Step 3 (verify): kubectl version --client
```

### Scenario 5: docker on Ubuntu desktop

```
Input: tool="docker", primary_pm="apt", family="debian",
       snap_available=True, systemd=True, is_root=False

_collect_deps("docker"):
  no binary deps
  no system packages
  _pick_install_method(docker, "apt", True) → "apt"
  _is_batchable("apt", "apt") → True
  Extract package: "docker.io" → add to batch

Plan:
  Step 1 (packages): apt-get install -y docker.io
    needs_sudo: True
  Step 2 (post_install): systemctl start docker
    needs_sudo: True
    condition "has_systemd" → True → included
  Step 3 (post_install): systemctl enable docker
    needs_sudo: True
    condition "has_systemd" → True → included
  Step 4 (post_install): usermod -aG docker $USER
    needs_sudo: True
    condition "not_root" → True → included
  Step 5 (verify): docker --version
    needs_sudo: False

Wait — docker was batchable. It went into batch_packages as "docker.io".
But then post_install steps come from docker's recipe.

Problem: if docker is batchable (goes into packages step), who emits
the post_install steps? The packages step is just "apt-get install"
with a list of packages. It doesn't know about individual tool recipes.

FIX: Even when a tool is batchable, we still need to track it for
post_install / verify purposes. The _collect_deps function should
remember that this tool was batched (not create a tool step) but
still add its post_install steps to the plan.

Updated data structures:
  batch_packages: list of package names (for the packages step)
  tool_steps: list of tool install steps (non-batchable tools)
  batched_tools: list of tool_ids that were batched (for post_install)
```

**This is a critical insight.** A tool can be installed via the package
batch, but still have post_install steps (docker), a verify command, etc.
The resolver must track batched tools separately.

### Scenario 6: ruff (simplest possible)

```
Input: tool="ruff", primary_pm="apt"

shutil.which("ruff") → None
no deps
_pick_install_method(ruff, "apt", True) → "_default"
_is_batchable("_default", "apt") → False
Add ruff tool step

Plan:
  Step 1 (tool): python3 -m pip install ruff
    needs_sudo: False
  Step 2 (verify): ruff --version
    needs_sudo: False

needs_sudo: False. No password prompt needed.
```

### Scenario 7: terraform on Alpine (IMPOSSIBLE)

```
Input: tool="terraform", primary_pm="apk", family="alpine",
       snap_available=False

shutil.which("terraform") → None
_pick_install_method(terraform, "apk", False):
  install has: snap, brew
  prefer = not set
  "apk" not in install → skip
  snap not available → skip
  "_default" not in install → skip
  Try remaining: "snap" not on PATH, "brew" not on PATH
  Returns None

resolve_install_plan returns:
{
    "tool": "terraform",
    "label": "Terraform",
    "error": "No install method available for Terraform on this system.",
    "available_methods": ["snap", "brew"],
    "suggestion": "Install snap or brew to enable Terraform installation.",
}
```

### Scenario 8: cargo-audit, cargo IS installed, packages missing

```
Input: tool="cargo-audit", primary_pm="apt", family="debian"

_collect_deps("cargo-audit"):
  requires.binaries = ["cargo"]
  
  _collect_deps("cargo"):
    shutil.which("cargo") → "/home/user/.cargo/bin/cargo" (found!)
    → SKIP (already installed, no step needed)
    But cargo has post_env! Even though cargo is installed, its
    post_env might still be needed if cargo is in ~/.cargo/bin
    and PATH doesn't have it persistently.

    Actually: if shutil.which("cargo") finds it, PATH already has it.
    No post_env needed.
  
  system packages: ["pkg-config", "libssl-dev"]
  Check: pkg-config installed? maybe. libssl-dev installed? maybe.
  Say both missing → add to batch

  _pick_install_method(cargo-audit, "apt", True) → "_default"
  Add cargo-audit tool step

Plan:
  Step 1 (packages): apt-get install -y pkg-config libssl-dev
    needs_sudo: True
  Step 2 (tool): cargo install cargo-audit
    needs_sudo: False
    No env wrapping needed (cargo is on PATH)
  Step 3 (verify): cargo audit --version
```

### Scenario 9: already installed tool

```
Input: tool="git"

shutil.which("git") → "/usr/bin/git"

Return immediately:
{
    "tool": "git",
    "label": "Git",
    "already_installed": True,
    "steps": [],
}
```

---

## 8. The Endpoint

### `POST /audit/install-plan`

```python
@audit_bp.route("/audit/install-plan", methods=["POST"])
def audit_install_plan():
    """Generate an install plan for a tool.

    Request body:
        {"tool": "cargo-outdated"}

    Response:
        Full plan dict (see resolve_install_plan output).
    """
    from src.core.services.tool_install import resolve_install_plan
    from src.core.services.audit.l0_detection import _detect_os

    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "").strip().lower()
    if not tool:
        return jsonify({"error": "No tool specified"}), 400

    system_profile = _detect_os()
    plan = resolve_install_plan(tool, system_profile)

    status = 200 if not plan.get("error") else 422
    return jsonify(plan), status
```

---

## 9. Edge Cases

### 9.1 Circular dependencies

Tool A requires B, B requires A. The `visited` set prevents infinite
recursion. If A is encountered again, skip it. The plan will install B
first (because A's deps are processed before A itself), then A.

In practice: no circular deps exist in our recipe set. But the code
must handle it.

### 9.2 Missing recipe for a dependency

What if `cargo-audit` declares `requires.binaries: ["cargo"]` but
`cargo` is NOT in `TOOL_RECIPES`?

`_collect_deps("cargo")` → `TOOL_RECIPES.get("cargo")` returns None.
This is an error in the recipe data. The resolver should:
- Log a warning
- Skip the unresolvable dep
- The plan will likely fail at execution time (cargo not found)
- But it won't crash the resolver

```python
recipe = TOOL_RECIPES.get(dep_id)
if not recipe:
    logger.warning("Dependency '%s' not found in TOOL_RECIPES", dep_id)
    continue
```

### 9.3 Multiple tools needing the same dep

If the user installs `cargo-audit` AND `cargo-outdated`, both require
`cargo` which requires `curl`. The `visited` set prevents double-
processing. curl is added to the batch once, cargo is added as a
tool step once.

### 9.4 Package already installed

`_is_pkg_installed("libssl-dev", "apt")` returns True.
→ Not added to batch_packages.
If ALL packages are already installed, the packages step is empty
and not emitted.

### 9.5 All deps satisfied, tool itself batchable

`git` on Ubuntu. No deps, install via apt.
→ Batchable. batch_packages = ["git"].
→ No tool steps.
→ Plan: 1 packages step + 1 verify step.

### 9.6 Tool needs sudo but system doesn't have sudo

`system_profile["capabilities"]["has_sudo"]` is False.
This can happen in Docker containers without sudo installed.
The plan should include a warning:
```python
if any_sudo and not system_profile["capabilities"]["has_sudo"]:
    plan["warning"] = "This plan requires sudo but sudo is not available."
```
If running as root, sudo steps can be executed without `sudo` prefix.

---

## 10. Sudo Handling

### Plan-level flag

```python
plan["needs_sudo"] = any(s["needs_sudo"] for s in steps)
```

The frontend uses this to:
1. Show the password prompt ONCE at the start of execution
2. Cache the password for all sudo steps in the plan
3. Skip the prompt entirely if needs_sudo is False

### Running as root

If `is_root` is True, sudo is not needed even for steps marked
`needs_sudo: True`. The execution layer (Phase 2.4) handles this:
- If running as root: strip `sudo -S -k` prefix from commands
- If not root + needs_sudo: prepend `sudo -S -k` and pipe password

This is NOT the resolver's concern. The resolver just declares
`needs_sudo` per step. The execution layer applies it.

---

## 11. Files Changed

| File | What changes |
|------|-------------|
| `tool_install.py` | Add `_pick_install_method()`, `_collect_deps()`, `resolve_install_plan()`, `_wrap_with_env()`, `_evaluate_condition()`, `_extract_packages_from_cmd()`, `_is_batchable()` (~150 lines) |
| `routes_audit.py` | Add `POST /audit/install-plan` endpoint (~20 lines) |

---

## 12. Dependencies on Previous Sub-Phases

| Dependency | From |
|-----------|------|
| `_is_pkg_installed()` | Phase 2.1 |
| `_build_pkg_install_cmd()` | Phase 2.1 |
| `TOOL_RECIPES` dict | Phase 2.2 |
| System profile format | Phase 1 (done) |

---

## 13. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Batchable tool with post_install (docker) gets lost | post_install steps not emitted | Track batched_tools separately from batch_packages |
| post_env + sudo combination | Wrong $HOME in sudo context | Doesn't occur in current recipe set. Document limitation. |
| Slow brew package checking in deps | Resolver takes seconds on macOS with many deps | brew timeout set to 30s in Phase 2.1. Most tools have 0-3 deps. |
| _pick_install_method returns None | No install possible | Return error plan with available_methods and suggestion |
| Circular deps | Infinite recursion | visited set prevents it |
| Missing dep in TOOL_RECIPES | Plan misses a dep, fails at execution | Log warning, continue. Recipe validation should catch this. |
