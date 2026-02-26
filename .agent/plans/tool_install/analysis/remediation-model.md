# Remediation Model — Architecture Design

> **Status:** Design phase. No code yet.
> **Created:** 2026-02-25
> **Scope:** How the tool install system handles failures and offers
> actionable recovery paths.

---

## 1. The Problem

The current `_analyse_install_failure()` is a flat pattern matcher with 5 hardcoded
cases. This cannot scale to 296 tools × 14 OS profiles × N failure categories.

The reality of remediation:

```
Tool install fails
  └─ WHY?
       ├─ Bootstrap broken       → no PM, no shell, no curl
       ├─ Infrastructure down    → no network, no disk, no sudo
       ├─ Method-family issue    → pip blocked (PEP 668), rustc too old, npm EACCES
       ├─ Tool-specific issue    → CUDA driver conflict, missing specific header
       └─ Unknown                → unrecognized stderr, novel error
```

Key insights that shape the design:

1. **Many remediations are themselves tool recipes.** "Install curl" is recipe `curl`.
   "Install pip" is recipe `pip`. "Install gcc" is recipe `gcc`. The resolver already
   knows how to install them. Remediation should reuse that knowledge, not duplicate it.

2. **Some remediations are shared across entire method families.** All 9 pip-installed
   tools share the PEP 668 remediation. All 5 cargo-installed tools share the
   rustc-mismatch remediation. These shouldn't be copy-pasted per recipe.

3. **Some remediations are truly tool-specific.** Only pytorch needs CUDA checks.
   Only OpenCV needs `libopencv-dev`. These belong in the recipe.

4. **Remediation is layered.** A tool failure might be caused by a missing dep,
   which itself fails because the PM is locked, which itself is caused by
   unattended-upgrades running. The system needs layers, not a flat list.

5. **Remediation is a sub-plan.** A remediation action is itself one or more steps,
   which need the same resolver pipeline (PM selection, sudo, env). Remediation
   produces plans. Plans use the same executor.

---

## 2. Layer Model

Four handler layers, evaluated bottom-up (most specific first):

```
┌─────────────────────────────────────────────────────┐
│  Layer 3: Recipe-declared handlers                  │  Per-tool
│  "opencv needs libopencv-dev on Debian"             │  overrides
├─────────────────────────────────────────────────────┤
│  Layer 2: Method-family handlers                    │  Per-PM / per-method
│  "all pip installs can hit PEP 668"                 │  shared patterns
├─────────────────────────────────────────────────────┤
│  Layer 1: Infrastructure handlers                   │  Cross-cutting
│  "no network", "disk full", "sudo denied"           │  environment
├─────────────────────────────────────────────────────┤
│  Layer 0: Bootstrap handlers                        │  Foundational
│  "no PM found", "no curl/wget for downloads"        │  prerequisites
└─────────────────────────────────────────────────────┘
```

### Resolution cascade

When a step fails:

1. **Layer 3 (recipe):** Check `recipe["on_failure"]` for a matching pattern.
   If found → use that handler. **Stop.**

2. **Layer 2 (method-family):** Check `METHOD_FAMILY_HANDLERS[method]` for a
   matching pattern. If found → use that handler. **Stop.**

3. **Layer 1 (infrastructure):** Check `INFRA_HANDLERS` for a matching pattern.
   If found → use that handler. **Stop.**

4. **Layer 0 (bootstrap):** Check `BOOTSTRAP_HANDLERS` for a matching pattern.
   If found → use that handler. **Stop.**

5. **Fallback:** Return a generic "unknown failure" with stderr and the option
   to retry, skip, or cancel.

**Why bottom-up (specific first)?** Because a recipe-level handler is the most
precise. If the opencv recipe says "missing libopencv headers → install
libopencv-dev", that's exact. The generic "missing header → install {tool}-dev"
heuristic is less precise and should only fire when no recipe handler matches.

---

## 3. Data Shapes

### 3.1 Handler shape (shared across all layers)

Every handler, regardless of layer, has the same shape. The critical change
from v1: **every handler produces MULTIPLE options**, not one. Real life means
real choices.

```python
{
    # ── Detection ──
    "pattern": str,          # regex matched against stderr (case-insensitive)
    "exit_code": int | None, # optional exit code filter (e.g. 137 = OOM)
    "detect_fn": str | None, # optional: named detection function for complex cases

    # ── Classification ──
    "failure_id": str,       # machine-readable ID: "pep668", "missing_header", etc.
    "category": str,         # grouping: "permissions", "network", "dependency", etc.
    "label": str,            # human-readable title for the failure
    "description": str,      # longer explanation for the user

    # ── Options (always plural) ──
    "options": [
        {
            "id": str,                # unique within this handler: "use-pipx"
            "label": str,             # human-readable: "Install via pipx"
            "description": str,       # why this option, what it does
            "icon": str,              # emoji for UI: "📦", "⬆️", "🔧"
            "recommended": bool,      # True = the system's best guess
            "strategy": str,          # from strategy enum (§3.2)

            # ── Availability (computed at runtime) ──
            "availability": str,      # "ready" | "locked" | "impossible"
            "lock_reason": str|None,  # if locked: why ("requires pip")
            "unlock_deps": list|None, # if locked: recipe IDs to install first
            "impossible_reason": str|None,  # if impossible: why

            # ── Strategy-specific fields ──
            # (vary by strategy — see §3.2)
        },
    ],
}
```

### Option availability states

| State | Meaning | UI behavior |
|-------|---------|-------------|
| `ready` | Can execute immediately | Clickable, primary action |
| `locked` | Needs prerequisites first | Shown with lock icon, shows unlock_deps, user can choose to unlock |
| `impossible` | Cannot work on this system | Shown greyed out with reason, not clickable |

**Example: PEP 668 handler options**

```python
"options": [
    {
        "id": "use-pipx",
        "label": "Install via pipx (recommended)",
        "description": "pipx installs in isolated venvs, avoids PEP 668",
        "icon": "📦",
        "recommended": True,
        "strategy": "install_dep_then_switch",
        "availability": "locked",        # pipx not installed yet
        "lock_reason": "pipx not installed",
        "unlock_deps": ["pipx"],          # install pipx first
    },
    {
        "id": "use-apt",
        "label": "Install via apt package",
        "description": "Use the distro package (may be older version)",
        "icon": "🐧",
        "recommended": False,
        "strategy": "switch_method",
        "availability": "ready",          # apt is available
    },
    {
        "id": "use-venv",
        "label": "Install in virtual environment",
        "description": "Creates ~/.venvs/tools and installs there",
        "icon": "🐍",
        "recommended": False,
        "strategy": "env_fix",
        "availability": "ready",
    },
    {
        "id": "break-system",
        "label": "Override with --break-system-packages",
        "description": "Forces pip install into system Python (risky)",
        "icon": "⚠️",
        "recommended": False,
        "strategy": "retry_with_modifier",
        "availability": "ready",
        "risk": "high",
    },
]
```

### 3.2 Remediation strategies

Each option declares a **strategy** that defines what kind of fix it offers:

| Strategy | Meaning | Extra fields | Example |
|----------|---------|--------------|---------|
| `install_dep` | Install a missing dependency (which is itself a recipe) | `dep: str` (recipe ID) | missing curl → `dep: "curl"` |
| `install_dep_then_switch` | Install dep, then use alt method | `dep: str`, `switch_to: str` | install pipx, then pipx install ruff |
| `install_packages` | Install system packages | `packages: dict[family, list]` | missing libssl-dev |
| `switch_method` | Use a different install method from the SAME recipe | `method: str` | PEP 668 → switch to apt |
| `retry_with_modifier` | Retry the same command with a modification | `modifier: dict` | sudo retry, reduced parallelism |
| `add_repo` | Add a package repo then retry | `repo_setup: dict[pm, list]` | Docker repo on Debian |
| `upgrade_dep` | Upgrade a dependency to a newer version | `dep: str`, `min_version: str` | rustc too old |
| `env_fix` | Fix an environment issue (PATH, locale, etc.) | `fix_commands: list` | PATH not including ~/.cargo/bin |
| `manual` | No auto-fix, show instructions | `instructions: str` | "Ask admin to add you to sudoers" |
| `cleanup_retry` | Free resources then retry | `cleanup_commands: list` | disk full → apt clean |

**Key design rule:** `install_dep` and `upgrade_dep` resolve to actual recipe
installations. The remediation engine calls `resolve_install_plan(dep, system_profile)`
to produce the sub-plan. **No duplicated install logic.**

### 3.3 Recipe-level handlers (`on_failure`)

Declared inside the recipe. Tool-specific overrides.

```python
"opencv": {
    "label": "OpenCV",
    "category": "ml",
    "install": {
        "pip": ["pip3", "install", "opencv-python"],
        "apt": ["apt-get", "install", "-y", "python3-opencv"],
    },
    "needs_sudo": {"pip": False, "apt": True},
    "verify": ["python3", "-c", "import cv2; print(cv2.__version__)"],

    # ── NEW: per-recipe failure handlers ──
    "on_failure": [
        {
            "pattern": "fatal error: opencv2/core.hpp",
            "failure_id": "missing_opencv_headers",
            "category": "dependency",
            "strategy": "install_packages",
            "label": "Missing OpenCV headers",
            "description": "OpenCV C++ headers required for building from source",
            "packages": {
                "debian": ["libopencv-dev"],
                "rhel": ["opencv-devel"],
                "arch": ["opencv"],
            },
        },
    ],
},
```

**Rules for `on_failure`:**

- Optional. Most recipes won't need it (method-family and infra handlers cover them).
- Only for truly tool-specific failures that generic handlers can't catch.
- Each entry follows the handler shape (§3.1).
- Evaluated in order. First match wins.
- The `pattern` is a regex matched against stderr.

### 3.4 Method-family handlers

Shared across all tools that use the same install method. Defined ONCE,
applied to every recipe that uses that method.

```python
METHOD_FAMILY_HANDLERS: dict[str, list[dict]] = {

    # ── pip family ──
    "pip": [
        {
            "pattern": "externally-managed-environment",
            "failure_id": "pep668",
            "category": "environment",
            "strategy": "switch_method",
            "label": "Externally managed Python (PEP 668)",
            "description": (
                "This system's Python is managed by the OS package manager. "
                "pip install is blocked to prevent conflicts."
            ),
            "prefer": ["pipx", "apt"],
            # If the recipe has a pipx or apt method, switch to it.
            # If not, offer pipx install as a remediation dep.
        },
        {
            "pattern": "No module named pip|pip: command not found",
            "failure_id": "missing_pip",
            "category": "dependency",
            "strategy": "install_dep",
            "label": "pip not installed",
            "description": "pip is required but not found on this system",
            "dep": "pip",
        },
    ],

    # ── cargo family ──
    "cargo": [
        {
            "pattern": r"requires rustc (\d+\.\d+)",
            "failure_id": "rustc_version_mismatch",
            "category": "dependency",
            "strategy": "upgrade_dep",
            "label": "Rust compiler too old",
            "description": "This crate requires a newer Rust compiler",
            "dep": "rustup",
        },
        {
            "pattern": "COMPILER BUG DETECTED|memcmp.*gcc.gnu.org",
            "failure_id": "gcc_memcmp_bug",
            "category": "compiler",
            "strategy": "install_dep",
            "label": "GCC compiler bug (aws-lc-sys)",
            "description": "Your GCC has a known memcmp bug. Need GCC 12+ or clang.",
            "dep": "gcc-12",
            # Alternative: offer clang as second option
        },
        {
            "pattern": r"cannot find -l(\S+)",
            "failure_id": "missing_c_library",
            "category": "dependency",
            "strategy": "install_packages",
            "label": "Missing C library",
            "description": "A C library needed for compilation is missing",
            # packages resolved dynamically from the capture group
            # e.g. -lssl → libssl-dev (debian) / openssl-devel (rhel)
            "dynamic_packages": True,
        },
    ],

    # ── npm family ──
    "npm": [
        {
            "pattern": "EACCES.*permission denied",
            "failure_id": "npm_eacces",
            "category": "permissions",
            "strategy": "retry_with_modifier",
            "label": "npm permission denied",
            "description": "npm cannot write to global node_modules",
            "modifier": {"retry_sudo": True},
            # Also offer: fix npm prefix, use npx
        },
        {
            "pattern": "npm: command not found|npm: not found",
            "failure_id": "missing_npm",
            "category": "dependency",
            "strategy": "install_dep",
            "label": "npm not installed",
            "description": "npm is required but not found",
            "dep": "npm",
        },
    ],

    # ── apt family ──
    "apt": [
        {
            "pattern": "Unable to locate package",
            "failure_id": "apt_stale_index",
            "category": "package_manager",
            "strategy": "cleanup_retry",
            "label": "Package not found — stale index",
            "description": "apt package index may be outdated",
            "cleanup_commands": [["apt-get", "update"]],
        },
        {
            "pattern": "Could not get lock|dpkg was interrupted",
            "failure_id": "apt_locked",
            "category": "package_manager",
            "strategy": "retry_with_modifier",
            "label": "Package manager locked",
            "description": "Another process is using apt/dpkg",
            "modifier": {"wait_seconds": 30, "retry": True},
        },
    ],

    # ── dnf family ──
    "dnf": [
        {
            "pattern": "No match for argument",
            "failure_id": "dnf_no_match",
            "category": "package_manager",
            "strategy": "manual",
            "label": "Package not found",
            "description": "Package name may differ on this distro/version",
            "instructions": "Check EPEL or enable additional repos",
        },
    ],

    # ── snap family ──
    "snap": [
        {
            "pattern": "cannot communicate with server|system does not fully support snapd",
            "failure_id": "snapd_unavailable",
            "category": "environment",
            "strategy": "switch_method",
            "label": "snapd not running",
            "description": "snap requires systemd. Falling back to alternative install.",
            "prefer": ["apt", "dnf", "brew", "_default"],
        },
    ],

    # ── brew family ──
    "brew": [
        {
            "pattern": "No formulae found",
            "failure_id": "brew_no_formula",
            "category": "package_manager",
            "strategy": "switch_method",
            "label": "Homebrew formula not found",
            "description": "This tool isn't available via Homebrew",
            "prefer": ["_default", "pip", "cargo"],
        },
    ],

    # ── _default (curl/bash scripts) ──
    "_default": [
        {
            "pattern": "curl: command not found|curl: not found",
            "failure_id": "missing_curl",
            "category": "dependency",
            "strategy": "install_dep",
            "label": "curl not installed",
            "description": "curl is required to download the install script",
            "dep": "curl",
        },
        {
            "pattern": "git: command not found|git: not found",
            "failure_id": "missing_git",
            "category": "dependency",
            "strategy": "install_dep",
            "label": "git not installed",
            "description": "git is required to clone the source repository",
            "dep": "git",
        },
    ],
}
```

### 3.5 Infrastructure handlers

Generic patterns that apply regardless of tool or method.

```python
INFRA_HANDLERS: list[dict] = [

    # ── Network ──
    {
        "pattern": "Could not resolve|Connection timed out|Failed to fetch|Network is unreachable",
        "failure_id": "network_offline",
        "category": "network",
        "strategy": "manual",
        "label": "Network unreachable",
        "description": "Cannot reach the download server. Check network connectivity.",
        "instructions": "Verify network, DNS, and proxy settings.",
    },
    {
        "pattern": "HTTP 403|HTTP 407|SSL certificate problem|certificate verify failed",
        "failure_id": "network_blocked",
        "category": "network",
        "strategy": "manual",
        "label": "Download blocked",
        "description": "Connection was rejected — possible proxy or TLS issue.",
        "instructions": "Check proxy allowlist or TLS/CA certificate configuration.",
    },

    # ── Disk ──
    {
        "pattern": "No space left on device",
        "failure_id": "disk_full",
        "category": "disk",
        "strategy": "cleanup_retry",
        "label": "Disk full",
        "description": "Not enough disk space to complete the installation.",
        "cleanup_commands": [
            ["apt-get", "clean"],
            ["docker", "system", "prune", "-f"],
        ],
    },

    # ── Permissions / sudo ──
    {
        "pattern": "is not in the sudoers file",
        "failure_id": "no_sudo_access",
        "category": "permissions",
        "strategy": "switch_method",
        "label": "No sudo access",
        "description": "Your account cannot use sudo. Switching to user-space install.",
        "prefer": ["pip", "cargo", "brew", "_default"],
        # Prefer methods that don't need sudo
    },
    {
        "pattern": "incorrect password|sorry, try again",
        "failure_id": "wrong_sudo_password",
        "category": "permissions",
        "strategy": "retry_with_modifier",
        "label": "Wrong sudo password",
        "description": "The sudo password was incorrect.",
        "modifier": {"reprompt_password": True},
    },
    {
        "pattern": "Permission denied",
        "exit_code": None,
        "failure_id": "permission_denied_generic",
        "category": "permissions",
        "strategy": "retry_with_modifier",
        "label": "Permission denied",
        "description": "The command needs elevated privileges.",
        "modifier": {"retry_sudo": True},
    },

    # ── Process / OOM ──
    {
        "pattern": "",  # No stderr pattern — detected by exit code
        "exit_code": 137,
        "failure_id": "oom_killed",
        "category": "resources",
        "strategy": "retry_with_modifier",
        "label": "Out of memory (killed by OOM)",
        "description": "Process was killed — likely out of memory during compilation.",
        "modifier": {"reduce_parallelism": True},
    },

    # ── Timeout ──
    {
        "pattern": "",
        "detect_fn": "timeout_expired",
        "failure_id": "command_timeout",
        "category": "timeout",
        "strategy": "retry_with_modifier",
        "label": "Command timed out",
        "description": "The command exceeded its time limit.",
        "modifier": {"extend_timeout": True},
    },
]
```

### 3.6 Bootstrap handlers

The absolute bottom layer. When even the infrastructure is broken.

```python
BOOTSTRAP_HANDLERS: list[dict] = [
    {
        "pattern": "apt-get: command not found|dnf: command not found|apk: command not found",
        "failure_id": "no_package_manager",
        "category": "bootstrap",
        "strategy": "manual",
        "label": "No package manager found",
        "description": (
            "No system package manager is available. "
            "This system may be a minimal container or a custom build."
        ),
        "instructions": (
            "Install a package manager first:\n"
            "  Debian/Ubuntu: apt-get is usually present by default\n"
            "  Alpine: apk is present by default\n"
            "  RHEL/Fedora: dnf is present by default\n"
            "  macOS: install Homebrew (https://brew.sh)"
        ),
    },
    {
        "pattern": "bash: command not found|sh: not found",
        "failure_id": "no_shell",
        "category": "bootstrap",
        "strategy": "manual",
        "label": "Shell not available",
        "description": "bash or sh is not available. Cannot execute install scripts.",
        "instructions": "Install bash or ensure /bin/sh exists.",
    },
]
```

---

## 4. How it fits in the Recipe

### 4.1 Recipe shape (extended)

The `on_failure` field is **optional**. Most recipes will NOT have it. The
method-family and infrastructure layers cover the common cases.

```python
"tool_id": {
    # ── Existing fields (unchanged) ──
    "label": str,
    "category": str,
    "cli": str,                  # optional
    "install": dict,
    "needs_sudo": dict,
    "requires": dict,            # optional: binaries, packages
    "verify": list,
    "post_env": str,             # optional
    "update": dict,              # optional
    "repo_setup": dict,          # optional
    "risk": str,                 # optional
    "prefer": list,              # optional

    # ── NEW: failure handlers ──
    "on_failure": list[dict],    # optional, list of handler shapes
}
```

### 4.2 When does a recipe NEED `on_failure`?

Only when the tool has **unique failure modes** that no shared handler covers:

| Needs `on_failure`? | Reason | Example |
|---------------------|--------|---------|
| ❌ No | Uses pip, common failures are method-family | ruff, black, mypy |
| ❌ No | Uses apt, common failures are infra-level | curl, git, jq |
| ❌ No | Uses cargo, rustc mismatch is method-family | cargo-audit, ripgrep |
| ✅ Yes | Needs specific C headers for build | opencv (libopencv-dev) |
| ✅ Yes | Has CUDA driver prerequisites | pytorch (nvidia-driver) |
| ✅ Yes | Tool conflicts with existing install | docker vs podman |
| ✅ Yes | Needs specific repo that's not in recipe | tools needing EPEL |

**Estimated breakdown:** ~80% of recipes need zero `on_failure` entries.
~15% need 1 entry. ~5% need 2-3 entries.

### 4.3 Which method triggered the failure?

The remediation engine receives the **method** that was used for the failed step.
This is what determines which method-family handlers apply:

```python
failed_step = {
    "tool_id": "ruff",
    "method": "pip",         # ← this selects METHOD_FAMILY_HANDLERS["pip"]
    "command": ["pip3", "install", "ruff"],
    "exit_code": 1,
    "stderr": "error: externally-managed-environment ...",
}
```

---

## 5. Resolution Flow

### 5.1 Cascade collects, not short-circuits

The cascade does NOT stop at first match. It **collects options from ALL
matching handlers across ALL layers**, then merges them into a single
response. This gives the user every possible path.

```
Step fails (exit_code != 0)
    │
    ├─ 1. recipe["on_failure"] → scan ALL matching patterns → collect options
    ├─ 2. METHOD_FAMILY_HANDLERS[method] → scan ALL → collect options
    ├─ 3. INFRA_HANDLERS → scan ALL → collect options
    ├─ 4. BOOTSTRAP_HANDLERS → scan ALL → collect options
    │
    └─ Merge: deduplicate, compute availability, sort by recommendation
             → return RemediationResponse to UI
```

**Priority for `recommended` flag:** Recipe options > method-family > infra > bootstrap.
If a recipe handler marks an option as recommended, that takes priority over a
method-family handler's recommendation.

### 5.2 Option availability is computed at resolution time

For each option, the engine checks:

```python
def _compute_availability(option, system_profile):
    strategy = option["strategy"]

    if strategy == "install_dep":
        dep = option["dep"]
        recipe = TOOL_RECIPES.get(dep)
        if not recipe:
            return "impossible", f"No recipe for '{dep}'", None
        cli = recipe.get("cli", dep)
        if shutil.which(cli):
            return "ready", None, None   # dep already installed
        # Dep exists as recipe but not installed → locked
        return "locked", f"{dep} not installed", [dep]

    if strategy == "switch_method":
        method = option["method"]
        if method not in recipe.get("install", {}):
            return "impossible", f"No {method} install method in recipe", None
        return "ready", None, None

    if strategy == "retry_with_modifier":
        return "ready", None, None  # always available

    if strategy == "install_packages":
        family = system_profile["distro"]["family"]
        pkgs = option.get("packages", {}).get(family, [])
        if not pkgs:
            return "impossible", f"No packages defined for {family}", None
        return "ready", None, None

    # ... etc for each strategy
```

### 5.3 Escalation chain

Remediation creates a chain. The user needs to see WHERE THEY ARE in the
chain and how many steps back to the original goal.

```
Original goal: Install ruff
  └─ Failed: PEP 668
     └─ User chose: Install via pipx
        └─ Failed: pipx not installed
           └─ User chose: Install pipx via apt
              └─ ✅ Success → de-escalate:
                 ✅ pipx installed → retry: pipx install ruff
                 ✅ ruff installed → ORIGINAL GOAL COMPLETE
```

The **escalation chain** is a stack:

```python
{
    "chain_id": "uuid-...",
    "original_goal": {
        "tool_id": "ruff",
        "plan": { ... },     # the original plan that failed
        "failed_step_idx": 0,
    },
    "escalation_stack": [
        # Index 0 = current level (deepest)
        {
            "depth": 2,
            "failure_id": "missing_pipx",
            "chosen_option": "install-pipx-apt",
            "plan": { ... },  # the fix plan
            "status": "executing",  # pending | executing | done | failed
        },
        {
            "depth": 1,
            "failure_id": "pep668",
            "chosen_option": "use-pipx",
            "plan": null,     # not yet resolved (waiting for depth 2)
            "status": "pending",
        },
    ],
    "max_depth": 3,         # hard limit
    "created_at": "...",
    "updated_at": "...",
}
```

### 5.4 De-escalation (unwinding the stack)

When a fix succeeds at depth N:

1. Pop depth N from the stack (mark done)
2. At depth N-1: the `unlock_deps` are now satisfied → option becomes `ready`
3. Execute the depth N-1 plan (now unlocked)
4. If depth N-1 succeeds: pop it, continue to N-2
5. When stack is empty: retry the original goal plan from the failed step
6. If the original plan completes: **ORIGINAL GOAL COMPLETE**

The UI shows this as a breadcrumb trail:
```
🎯 Install ruff  →  🔓 Install pipx  →  📦 apt install pipx (current)
```

### 5.5 Max depth and cycle detection

- **Max depth: 3.** Beyond that, show all accumulated errors to the user.
- **Cycle detection:** Track visited tool IDs in the chain. If we'd install
  tool X to fix tool Y, but tool Y is already in the chain, STOP.

```
Level 0: Install ruff → fails (PEP 668)
Level 1: Install pipx → fails (pip not found)
Level 2: Install pip via apt → fails (no sudo)
Level 3: STOP — show all errors, all options at each level, let user decide
```

### 5.6 Resumability (save/restore on reconnect)

The escalation chain is **serializable**. The backend:

1. **Saves** the chain state to disk/memory on every state change
2. On server restart: loads pending chains
3. On SSE/WebSocket connect: **pushes pending chains** to the UI
   via the general message stream
4. UI receives the chain → shows the remediation modal at the right depth
5. User can **continue**, **retry from any depth**, or **cancel the whole chain**

**State lifecycle:**
```
created → user picks option → executing → success → de-escalate
                                        → failure → escalate (or max depth)
created → user closes browser → persisted → server pushes on reconnect
created → user cancels → chain dropped
```

Persistence format: JSON file at `~/.config/devops-cp/remediation-chains/`
or in-memory dict keyed by `chain_id`.

---

## 6. Backend Response Shape (API → UI)

The API returns **one response** when a step fails. The UI gets everything
it needs in one payload — no follow-up requests to understand the failure.

```python
{
    # ── What failed ──
    "ok": False,
    "tool_id": "ruff",
    "step_idx": 0,
    "step_label": "pip install ruff",
    "exit_code": 1,
    "stderr": "error: externally-managed-environment ...",

    # ── What the system detected ──
    "failure": {
        "failure_id": "pep668",
        "category": "environment",
        "label": "Externally managed Python (PEP 668)",
        "description": "This system's Python is managed by the OS ...",
        "matched_layer": "method_family",    # which layer matched
        "matched_method": "pip",             # which method-family
    },

    # ── All available options ──
    "options": [
        {
            "id": "use-pipx",
            "label": "Install via pipx (recommended)",
            "description": "pipx installs in isolated venvs ...",
            "icon": "📦",
            "recommended": True,
            "strategy": "install_dep_then_switch",
            "availability": "locked",
            "lock_reason": "pipx not installed",
            "unlock_deps": ["pipx"],
            "unlock_step_count": 1,    # how many steps to unlock
            "risk": "low",
        },
        {
            "id": "use-apt",
            "label": "Install via apt package",
            "description": "Use the distro package (may be older version)",
            "icon": "🐧",
            "recommended": False,
            "strategy": "switch_method",
            "availability": "ready",
            "step_count": 1,           # how many steps this fix takes
            "risk": "low",
        },
        {
            "id": "use-venv",
            "label": "Install in virtual environment",
            "description": "Creates ~/.venvs/tools and installs there",
            "icon": "🐍",
            "recommended": False,
            "strategy": "env_fix",
            "availability": "ready",
            "step_count": 2,
            "risk": "low",
        },
        {
            "id": "break-system",
            "label": "Override with --break-system-packages",
            "description": "Forces pip install into system Python",
            "icon": "⚠️",
            "recommended": False,
            "strategy": "retry_with_modifier",
            "availability": "ready",
            "step_count": 1,
            "risk": "high",
        },
    ],

    # ── Escalation chain context (if already in a chain) ──
    "chain": {
        "chain_id": "uuid-...",
        "original_goal": "ruff",
        "depth": 0,                # current depth (0 = first failure)
        "max_depth": 3,
        "breadcrumbs": [
            # Empty on first failure. Populated during escalation.
            # {"tool_id": "pipx", "label": "Install pipx", "status": "done"},
        ],
    },

    # ── Always-available actions ──
    "fallback_actions": [
        {"id": "retry", "label": "Retry", "icon": "🔄"},
        {"id": "skip", "label": "Skip this tool", "icon": "⏭️"},
        {"id": "cancel", "label": "Cancel", "icon": "✕"},
    ],
}
```

### What the UI does with this

1. **Shows the failure** — label, description, stderr (collapsible)
2. **Shows ALL options** — sorted: recommended first, then ready, then locked, then impossible
3. **Locked options** show a 🔒 with the lock reason and a "Unlock" button  
   that triggers the unlock_deps install (which escalates the chain)
4. **Impossible options** shown greyed out with reason (no action)
5. **Breadcrumbs** show the chain path back to the original goal
6. **Fallback actions** always at the bottom (retry, skip, cancel)

### When user picks an option

The UI sends:
```python
POST /api/audit/remediate-choice
{
    "chain_id": "uuid-...",
    "chosen_option_id": "use-pipx",
    // If locked option chosen, backend auto-escalates (installs deps first)
}
```

The backend either:
- **Executes** the fix (if `ready`) → SSE stream of steps
- **Escalates** (if `locked`) → pushes the deps as a new depth in the chain,
  returns a NEW remediation response for the dep install

---

## 7. How this replaces install_failure.py

The current `_analyse_install_failure()` becomes a thin dispatcher:

```python
def _analyse_install_failure(tool, cli, stderr, exit_code, method, system_profile):
    """Cascade through handler layers and return structured remediation."""

    recipe = TOOL_RECIPES.get(tool, {})

    # Layer 3: Recipe-declared handlers
    for handler in recipe.get("on_failure", []):
        if _matches(handler, stderr, exit_code):
            return _build_remediation_plan(handler, ...)

    # Layer 2: Method-family handlers
    for handler in METHOD_FAMILY_HANDLERS.get(method, []):
        if _matches(handler, stderr, exit_code):
            return _build_remediation_plan(handler, ...)

    # Layer 1: Infrastructure handlers
    for handler in INFRA_HANDLERS:
        if _matches(handler, stderr, exit_code):
            return _build_remediation_plan(handler, ...)

    # Layer 0: Bootstrap handlers
    for handler in BOOTSTRAP_HANDLERS:
        if _matches(handler, stderr, exit_code):
            return _build_remediation_plan(handler, ...)

    return None  # unknown failure
```

The 5 hardcoded cases in today's code become entries in the data registries:
- rustc mismatch → `METHOD_FAMILY_HANDLERS["cargo"][0]`
- npm not found → `METHOD_FAMILY_HANDLERS["npm"][1]`
- pip not found → `METHOD_FAMILY_HANDLERS["pip"][1]`
- npm EACCES → `METHOD_FAMILY_HANDLERS["npm"][0]`
- GCC memcmp bug → `METHOD_FAMILY_HANDLERS["cargo"][1]`

Nothing is lost. Everything is gained: the cascade, the layering,
the composability.

---

## 8. Relationship to Existing Code

| Current | New | Change |
|---------|-----|--------|
| `install_failure.py` (250 lines, 5 cases) | Thin dispatcher + data registries | Refactor to cascade |
| `error_analysis.py` (147 lines, build errors) | Merge build patterns into method-family handlers | Build errors become `METHOD_FAMILY_HANDLERS["make"]`, etc. |
| `recipe_deps.py` (27 lines) | Unchanged — still resolves system packages | No change |
| `dependency_collection.py` (151 lines) | Unchanged — proactive dep resolution | No change |
| `plan_resolution.py` (618 lines) | Add `resolve_install_plan_with_method()` for switch_method strategy | Small addition |
| `recipes.py` / TOOL_RECIPES | Some recipes get `on_failure` field | Data extension |
| `recipe_schema.py` | Validate `on_failure` field | Schema update |

### What stays proactive (plan-time)

- `requires.binaries` — still resolved depth-first before install
- `requires.packages` — still batch-collected before install
- `repo_setup` — still prepended to install steps

### What is reactive (failure-time)

- `on_failure` — only evaluated when a step fails
- Method-family handlers — only evaluated when a step fails
- Infra/bootstrap handlers — only evaluated when a step fails

The proactive path prevents many failures. The reactive path handles
what the proactive path couldn't predict.

---

## 9. File Layout

```
src/core/services/tool_install/
├── data/
│   ├── recipes.py                    # TOOL_RECIPES (gains on_failure field)
│   ├── recipe_schema.py              # validates on_failure
│   ├── remediation_handlers.py       # NEW: METHOD_FAMILY_HANDLERS,
│   │                                 #       INFRA_HANDLERS,
│   │                                 #       BOOTSTRAP_HANDLERS
│   └── constants.py                  # unchanged
├── domain/
│   ├── error_analysis.py             # build patterns merge into remediation_handlers
│   ├── handler_matching.py           # NEW: _matches(), pattern matching logic
│   └── remediation_planning.py       # NEW: _build_remediation_plan()
├── detection/
│   ├── install_failure.py            # REFACTORED: thin dispatcher using cascade
│   └── recipe_deps.py               # unchanged
└── resolver/
    ├── plan_resolution.py            # gains resolve_install_plan_with_method()
    ├── method_selection.py           # unchanged
    └── dependency_collection.py      # unchanged
```

---

## 10. Scalability Analysis

### Without this model (current state)

- Adding a new tool = add recipe + possibly add hardcoded case to install_failure.py
- 296 tools with 5 failure handlers = 1,480 potential handler entries
- Most would be duplicates of method-family patterns
- No composability — each handler builds its own commands

### With this model

- Adding a new pip tool = add recipe. PEP 668, missing pip, etc. are covered FOR FREE.
- Adding a new cargo tool = add recipe. Rustc mismatch, gcc bug are covered FOR FREE.
- Only truly tool-specific failures need `on_failure`.
- ~80% of recipes need zero handler entries.
- Method-family handlers: ~20 entries total, cover ~80% of failures.
- Infra handlers: ~10 entries total, cover ~15% of failures.
- Recipe-specific: ~30-50 entries total, cover the remaining ~5%.

**Total data entries needed: ~60-80 handlers to cover 296 tools × 14 platforms.**

Compared to the naive approach: **1,480+ handlers.**

---

## 11. Schema Validation

The `on_failure` field in recipes needs schema validation:

```python
# In recipe_schema.py
VALID_STRATEGIES = {
    "install_dep", "install_dep_then_switch", "install_packages",
    "switch_method", "retry_with_modifier", "add_repo",
    "upgrade_dep", "env_fix", "manual", "cleanup_retry",
}

VALID_AVAILABILITY = {"ready", "locked", "impossible"}

# For each handler in on_failure:
HANDLER_REQUIRED_FIELDS = {"pattern", "failure_id", "category", "label", "options"}
HANDLER_OPTIONAL_FIELDS = {
    "description", "exit_code", "detect_fn",
}

# For each option within a handler:
OPTION_REQUIRED_FIELDS = {"id", "label", "strategy", "icon"}
OPTION_OPTIONAL_FIELDS = {
    "description", "recommended", "risk",
    "dep", "switch_to", "method", "packages", "modifier",
    "repo_setup", "min_version", "fix_commands",
    "cleanup_commands", "instructions", "dynamic_packages",
}
```

---

## 12. Test Strategy

### Unit tests (handler matching)

- Every handler pattern matches its intended stderr
- No pattern accidentally matches unrelated stderr (false positive)
- Cascade order: recipe > method-family > infra > bootstrap
- Cycle detection works
- Max depth respected

### Integration tests (remediation planning)

- `install_dep` strategy produces valid sub-plan from recipe
- `switch_method` strategy picks correct alternative
- `retry_with_modifier` produces correct modifier fields
- `install_packages` resolves correct packages per distro family

### Parametric tests (coverage)

- Every recipe × every simulated profile: inject known failure stderr,
  verify a handler matches and produces a valid remediation plan.
- This extends the existing test_resolver_coverage.py framework.

---

## 13. Decisions Made

1. **✅ DECIDED: Separate file.** Method-family handlers live in
   `remediation_handlers.py`, not in `recipes.py`. Keeps data focused.

2. **✅ DECIDED: Multiple options per handler.** Every handler declares
   N options with `options: [...]`. The cascade collects from ALL matching
   handlers across ALL layers, merges, deduplicates, computes availability.
   No single-strategy limitation.

3. **✅ DECIDED: `-lssl → libssl-dev` mapping.** Yes, becomes
   `LIB_TO_PACKAGE_MAP` constant in `remediation_handlers.py`.

## 14. Open Questions

1. **Persistence backend for escalation chains.** File-based JSON vs
   in-memory dict? File survives server restart. In-memory is faster.
   Could use both (write-through cache).

2. **SSE event type for chain push.** Need to define the event name
   and shape for pushing pending chains on reconnect. Should align
   with the existing general message stream.

---

## Traceability

| Topic | Source |
|-------|--------|
| Current install_failure.py | detection/install_failure.py (5 handlers) |
| Current error_analysis.py | domain/error_analysis.py (build patterns) |
| Failure scenarios | scenario-failure-modes.md (8 categories, 20+ scenarios) |
| PM error handling | domain-package-managers.md §Error Handling |
| Package naming | domain-package-managers.md §Package Naming Across PMs |
| Dependency resolution | resolver/dependency_collection.py |
| Method selection | resolver/method_selection.py |
| Plan resolution | resolver/plan_resolution.py |
