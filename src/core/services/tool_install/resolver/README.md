# L2 Resolver — Plan Generation

> **6 files · 2,337 lines · The brain of the system.**
>
> Reads recipes (L0) + system profile (L3 input).
> Produces deterministic, executable plans. No subprocess. No filesystem writes.
> Platform adaptation happens here — a single recipe becomes a different plan
> on Ubuntu vs Fedora vs Alpine vs macOS.

---

## How It Works

### Resolution Pipeline

```
Recipe (L0)  +  System Profile  +  User Choices (optional)
     │                │                    │
     ▼                ▼                    ▼
┌────────────────────────────────────────────────────┐
│ 1. METHOD SELECTION (method_selection.py)           │
│    Recipe has install methods keyed by PM.          │
│    System profile says primary PM = apt.            │
│    → Pick "apt" if available, else snap, else       │
│      _default, else any PM on PATH.                 │
│                                                    │
│ 2. DEPENDENCY COLLECTION (dependency_collection.py)│
│    Recipe says requires.binaries = ["cargo"].       │
│    → Recurse into "cargo" recipe (depth-first)     │
│    → Cargo requires "rustup" → recurse again       │
│    → Collect system packages per distro family      │
│    → Batch all apt/dnf packages into ONE step       │
│    If no recipe exists for a dep:                  │
│    → Dynamic fallback (dynamic_dep_resolver.py)    │
│                                                    │
│ 3. CHOICE RESOLUTION (choice_resolution.py)        │
│    Recipe has choices (version, variant, GPU).      │
│    → Present ALL options (available + disabled)     │
│    → Apply user selection to plan branches          │
│    → Auto-select when only one option available     │
│                                                    │
│ 4. PLAN ASSEMBLY (plan_resolution.py)              │
│    Ordered steps:                                  │
│    repo_setup → packages → tools → post_install →  │
│    verify                                          │
│    Post-env propagated to all subsequent steps.    │
└────────────────────────────────────────────────────┘
            │
            ▼
      Plan dict (deterministic)
```

### Dynamic Dependency Resolution (4-Tier Cascade)

```
dependency not in TOOL_RECIPES?
     │
     ▼
dynamic_dep_resolver.resolve_dep_install()
     │
     ├── Tier 1: Recipe lookup (TOOL_RECIPES)  → "recipe" source
     │
     ├── Tier 2: Known packages (KNOWN_PACKAGES map)
     │   55+ tools × 6 PMs → exact per-PM package names
     │   Confidence: HIGH
     │
     ├── Tier 3: Lib-to-package mapping (LIB_TO_PACKAGE_MAP)
     │   "libssl" → debian: libssl-dev, rhel: openssl-devel
     │   For library dependencies from build errors
     │   Confidence: HIGH
     │
     ├── Tier 4: Special installers (KNOWN_PACKAGES["_install_cmd"])
     │   rustup, nvm → curl|bash scripts
     │   Confidence: HIGH
     │
     └── Tier 5: Identity fallback (dep_name = package_name)
         Tries dep name directly as PM package name
         Confidence: MEDIUM (may not work)
```

---

## File Map

```
resolver/
├── __init__.py                  32 lines  — re-exports all resolver functions
├── plan_resolution.py          668 lines  — top-level plan resolvers + data-pack/config plans
├── choice_resolution.py        577 lines  — choice+input evaluation, branch selection
├── dynamic_dep_resolver.py     530 lines  — 4-tier cascade + KNOWN_PACKAGES catalog
├── method_selection.py         336 lines  — PM selection, command building, batching
├── dependency_collection.py    194 lines  — depth-first dep walker + network reachability
└── README.md                              — this file
```

---

## Per-File Documentation

### `__init__.py` — Re-exports (32 lines)

Re-exports all public and private symbols from all resolver modules:

```python
from src.core.services.tool_install.resolver import (
    resolve_install_plan, resolve_choices, _pick_install_method, _collect_deps
)
```

### `plan_resolution.py` — Top-Level Plan Resolver (668 lines)

Main entry points. Combines method selection + dependency collection +
choice resolution into a final executable plan.

| Function | What It Does |
|----------|-------------|
| `resolve_install_plan(tool, profile)` | Full plan for a tool on this system (Pass 1 — before choices) |
| `resolve_install_plan_with_choices(tool, profile, answers)` | Plan with user's choice answers applied (Pass 2 — after choices) |
| `_resolve_data_pack_plan(tool, recipe, profile)` | Wrap data-pack recipe's pre-built download/setup steps into a plan |
| `_resolve_config_plan(tool, recipe, profile)` | Wrap config recipe's templates into config steps |

**Plan assembly order:**

1. Repo setup steps (from all deps with `repo_setup` for this PM)
2. Batched system packages (ONE apt-get/dnf call for all deps)
3. Tool install steps (non-batchable, ordered by dependency depth)
4. Post-install steps (from recipe `post_install`, condition-filtered)
5. Verify step (from recipe `verify`)

**Special plan types:**

| Type | Trigger | Handler |
|------|---------|---------|
| `data_pack` | `recipe["type"] == "data_pack"` | `_resolve_data_pack_plan()` |
| `config` | `recipe["type"] == "config"` | `_resolve_config_plan()` |
| Normal | Default | Full dependency walk + method selection |

Each tool step gets `post_env` from its dependencies injected via
`_wrap_with_env`, so `cargo install` automatically has `~/.cargo/bin`
on PATH even though rustup was just installed in a previous step.

### `choice_resolution.py` — Interactive Choice System (577 lines)

Handles recipes with `choices` — PyTorch (CPU/CUDA/ROCm), Docker
(apt/snap/script), NVIDIA driver (version selection).

| Function | What It Does |
|----------|-------------|
| `resolve_choices(tool, profile)` | Pass 1: extract choices/inputs, evaluate constraints, return decision tree |
| `_resolve_choice_option(option, profile)` | Evaluate one option against system (hardware, platform, binary, network checks) |
| `_resolve_single_choice(choice, profile)` | Resolve all options in one choice, determine default |
| `_input_condition_met(inp, answers, profile)` | Check if an input field should be shown (conditional on other choices) |
| `_apply_choices(recipe, answers)` | Apply user's choice answers — select branches, resolve variant dicts |
| `_apply_inputs(recipe, answers)` | Substitute `{input_id}` templates in commands/configs/paths |

**Key principle:** ALL options returned — available AND unavailable.
Unavailable options have `disabled_reason` and `enable_hint`.
The assistant panel renders these for user education.

**Option availability checks (run ALL, not short-circuit):**

| Constraint | Check |
|-----------|-------|
| `requires.network` | `_can_reach()` endpoint probe |
| `requires.platforms` | OS/arch match |
| `requires.binaries` | `shutil.which()` on PATH |
| `requires.hardware` | GPU type/memory from detection |

**Input conditions:**

| Type | Example |
|------|---------|
| Choice-based | `{"choice": "method", "equals": "source"}` |
| Profile-based | `{"profile": "has_systemd", "equals": true}` |

### `dynamic_dep_resolver.py` — Dynamic Dependency Resolution (530 lines)

Resolves dependencies that have no TOOL_RECIPES entry. Contains
KNOWN_PACKAGES (55+ tools × 6 package managers) and PACKAGE_GROUPS.

| Symbol | What It Does |
|--------|-------------|
| `KNOWN_PACKAGES` | Dict: tool_name → {pm: package_name} for 55+ tools |
| `PACKAGE_GROUPS` | Dict: group_name → {family: [packages]} (build_tools, build_tools_python, epel) |
| `_PM_TO_FAMILY` | Dict: PM name → distro family (apt→debian, dnf→rhel, ...) |
| `_PM_INSTALL_CMDS` | Dict: PM → install command prefix (apt → `apt-get install -y`) |
| `resolve_dep_install(dep, profile)` | Core 4-tier cascade resolver |
| `resolve_package_group(packages)` | Expand string group reference to dict |
| `_build_install_cmd(pm, packages, profile)` | Build subprocess command for PM |
| `_needs_sudo(pm, profile)` | Check if PM needs sudo (system PMs: yes, brew: no) |

**KNOWN_PACKAGES coverage (55+ entries):**

| Category | Tools |
|----------|-------|
| System utils | curl, wget, git, jq, tar, unzip, tree, file |
| Build tools | gcc, g++, make, cmake, autoconf, automake, libtool, ninja |
| Crypto/security | gnupg, openssl |
| Compression | zstd |
| Package managers | pip3, pipx, cargo, go, npm, yarn |
| Languages | python3, python3-venv, node |
| DevOps | kubectl, helm, terraform, docker, docker-compose |
| Libraries | pkg-config, build-essential |
| Auth | sudo |

**resolve_dep_install() return shapes:**

```python
# Tier 1: Recipe found
{"source": "recipe", "tool_id": "helm", "recipe": {...}}

# Tier 2-5: Package found
{
    "source": "known_package",  # or "lib_mapping", "identity"
    "package_names": ["libssl-dev"],
    "install_cmd": ["apt-get", "install", "-y", "libssl-dev"],
    "pm": "apt",
    "confidence": "high",  # or "medium" for identity
}

# Tier 4: Special installer
{"source": "special_installer", "install_cmd": ["bash", "-c", "curl ... | sh"]}
```

### `method_selection.py` — Install Method Picker (336 lines)

Core platform-adaptation logic. Given a recipe's `install` map and
the system profile, picks which method to use.

| Function | What It Does |
|----------|-------------|
| `_pick_install_method(recipe, pm, snap)` | Pick best method for this system (5-tier priority) |
| `_pick_method_command(method_map, profile)` | Resolve method map to (command, method) tuple |
| `_build_pkg_install_cmd(packages, pm)` | Build `apt-get install -y`/`dnf install -y`/etc. command |
| `_extract_packages_from_cmd(cmd, pm)` | Parse package names from install command |
| `_is_batchable(method, pm, cmd)` | Can this method's packages be batched into one call? |
| `_wrap_with_env(cmd, env_setup)` | Prepend env setup to command (bash -c wrapper) |
| `_derive_update_cmd(install_cmd, pm)` | Derive update command from install command |
| `get_update_map(recipe)` | Get update command map (explicit or derived) |

**Method resolution priority:**

| Priority | Source | Example |
|----------|--------|---------|
| 1 | Recipe's `prefer` list | `prefer: ["dnf", "apt"]` — respects order |
| 2 | System's primary PM | Ubuntu → `apt`, Fedora → `dnf` |
| 3 | snap (if available) | snap method + snap binary on PATH |
| 4 | `_default` fallback | Universal method (pip, cargo, curl) |
| 5 | Any PM on PATH | `shutil.which()` each method key |

**Supported package managers:**
apt, dnf, yum, zypper, apk, pacman, brew, snap

**Batchability rules:**

| Condition | Batchable? |
|-----------|-----------|
| Method matches primary PM | Yes (normally) |
| Command is `bash -c "..."` | No (complex multi-step) |
| Method is `_default` | No (language PM / curl) |
| Method is `snap` | No (different install flow) |

### `dependency_collection.py` — Transitive Dependency Walker (194 lines)

Walks the dependency tree depth-first.

| Function | What It Does |
|----------|-------------|
| `_collect_deps(tool_id, profile, visited, ...)` | Recursive dep walker. Mutates accumulators in place. |
| `_can_reach(endpoint, timeout)` | Network reachability probe (HTTP HEAD, cached 60s) |

**Walk algorithm for each tool:**

1. Cycle guard: skip if in `visited` set
2. Recipe lookup → if missing, fall back to `dynamic_dep_resolver`
3. Check if already installed (`shutil.which(cli)`) → skip
4. **Recurse** into `requires.binaries` (depth-first)
5. Collect `requires.packages` for this distro family
6. Pick install method → batchable or individual step
7. Track `post_env` for PATH propagation

**Dynamic fallback (no recipe):**

| Resolution | Action |
|-----------|--------|
| `special_installer` | Add as non-batchable tool step |
| `known_package`/`identity` | Add packages to batch list |
| Not resolved | Log warning, skip |

---

## Dependency Graph

```
__init__.py          ← re-exports from all modules below

plan_resolution.py
   ├── dependency_collection._collect_deps()
   ├── method_selection._pick_install_method()
   ├── method_selection._build_pkg_install_cmd()
   ├── method_selection._wrap_with_env()
   ├── choice_resolution.resolve_choices()
   ├── choice_resolution._apply_choices()
   ├── choice_resolution._apply_inputs()
   ├── domain.risk._infer_risk(), _plan_risk()    (L1)
   ├── domain.dag._add_implicit_deps()            (L1)
   └── data.recipes.TOOL_RECIPES                   (L0)

choice_resolution.py
   ├── dependency_collection._can_reach()
   ├── data.recipes.TOOL_RECIPES                   (L0)
   └── data.constants._VERSION_FETCH_CACHE         (L0)

dependency_collection.py
   ├── method_selection._pick_install_method()
   ├── method_selection._is_batchable()
   ├── method_selection._extract_packages_from_cmd()
   ├── dynamic_dep_resolver.resolve_dep_install()  (local fallback)
   ├── detection.system_deps._is_pkg_installed()   (L3)
   └── data.recipes.TOOL_RECIPES                   (L0)

dynamic_dep_resolver.py
   ├── data.recipes.TOOL_RECIPES                   (L0)
   └── KNOWN_PACKAGES, PACKAGE_GROUPS              (self-contained catalogs)

method_selection.py
   └── data.recipes.TOOL_RECIPES                   (L0)
```

---

## Key Data Shapes

### resolve_install_plan() output

```python
{
    "tool": "cargo-audit",
    "label": "cargo-audit",
    "needs_sudo": True,
    "already_installed": False,
    "post_env": {"PATH": "$HOME/.cargo/bin:$PATH"},
    "steps": [
        {"type": "packages", "command": ["apt-get", "install", "-y", "pkg-config", "libssl-dev"],
         "label": "Install system dependencies", "needs_sudo": True},
        {"type": "tool", "command": ["bash", "-c", "curl ... | sh -s -- -y"],
         "label": "Install rustup", "needs_sudo": False},
        {"type": "tool", "command": ["cargo", "install", "cargo-audit"],
         "label": "Install cargo-audit", "needs_sudo": False},
        {"type": "verify", "command": ["cargo-audit", "--version"],
         "label": "Verify cargo-audit"},
    ],
    "risk": {"level": "low", "counts": {"low": 4}},
}
```

### resolve_choices() output

```python
{
    "tool": "pytorch",
    "label": "PyTorch",
    "choices": [{
        "id": "compute",
        "label": "Compute backend",
        "options": [
            {"id": "cpu", "label": "CPU only", "available": True},
            {"id": "cuda", "label": "NVIDIA CUDA", "available": False,
             "disabled_reason": "No NVIDIA GPU detected",
             "enable_hint": "Install NVIDIA GPU + drivers"},
            {"id": "rocm", "label": "AMD ROCm", "available": False,
             "disabled_reason": "No AMD GPU detected"},
        ],
    }],
    "inputs": [],
    "defaults": {"compute": "cpu"},
    "auto_resolve": False,
}
```

---

## Design Decisions

### Why ALL choice options are returned (not just available)

The UI shows unavailable options grayed out with explanations. This
educates users about what they could do ("Install NVIDIA GPU + drivers"
to unlock CUDA). Removing options would make users think they don't
exist at all.

### Why dependency collection is depth-first

Installing `cargo-audit` requires `rustup`, which requires no other
tools. Depth-first ensures `rustup` appears BEFORE `cargo-audit` in
the plan. If we used breadth-first, dependency ordering would be wrong.

### Why dynamic_dep_resolver has 530 lines

The KNOWN_PACKAGES catalog maps 55+ tools across 6 package managers.
Each entry needs per-PM package names because naming differs:
`gnupg` (apt) vs `gnupg2` (dnf) vs `gpg2` (zypper). This data can't
be generated — it must be curated.

### Why method selection checks snap availability

Canonical's snap is not universally available. Alpine, Arch, and
minimal containers don't have snapd. The resolver must verify snap
binary exists before offering snap as an install method, even if the
recipe has a snap entry.

### Determinism Guarantee

Given the same inputs (tool ID + system profile + user choices), the
resolver produces the **exact same plan**. Every time. No randomness.
No time-dependent logic. No external fetches during resolution.

This makes plans:
- **Reproducible** — "this plan didn't work" can be replayed
- **Testable** — pure function, no mocks needed
- **Cacheable** — same inputs = same output
- **Debuggable** — every decision traceable to inputs

---

## Advanced Feature Showcase

### 1. Transitive Dependency Walk with Batching

```python
# dependency_collection.py — depth-first with accumulator mutation
batch_packages = []   # accumulator: system packages to batch
tool_steps = []       # accumulator: non-batchable tool installs
batched_tools = []    # accumulator: tool IDs installed via batch
post_env_map = {}     # accumulator: tool_id → post_env string
visited = set()       # cycle guard

_collect_deps("cargo-audit", profile, visited,
              batch_packages, tool_steps, batched_tools, post_env_map)

# Result:
# batch_packages = ["pkg-config", "libssl-dev"]       → ONE apt-get call
# tool_steps = [
#     {"tool_id": "rustup", "method": "_default"},    → curl|bash
#     {"tool_id": "cargo-audit", "method": "_default"},  → cargo install
# ]
# post_env_map = {"rustup": 'export PATH="$HOME/.cargo/bin:$PATH"'}
```

### 2. Dynamic Fallback (No Recipe Needed)

```python
# dynamic_dep_resolver.py — when no TOOL_RECIPES entry exists
result = resolve_dep_install("cmake", profile)
# → {"source": "known_package", "package_names": ["cmake"],
#    "install_cmd": ["apt-get", "install", "-y", "cmake"],
#    "confidence": "high"}

result = resolve_dep_install("rustup", profile)
# → {"source": "special_installer",
#    "install_cmd": ["bash", "-c", "curl ... | sh -s -- -y"]}
```

### 3. Choice with Conditional Inputs

```python
# choice_resolution.py — inputs that depend on choice answers
# Recipe: {"inputs": [{"id": "prefix", "condition": {"choice": "method", "equals": "source"}}]}
# If user chose method="source" → show prefix input
# If user chose method="apt" → hide prefix input
```

### 4. Post-env Propagation Across Steps

```python
# plan_resolution.py — rustup's PATH feeds into cargo install
# Step 1: Install rustup (post_env: PATH=$HOME/.cargo/bin:$PATH)
# Step 2: cargo install cargo-audit
#   → command wrapped with: bash -c 'export PATH=... && cargo install ...'
```

### 5. Package Group Expansion

```python
# dynamic_dep_resolver.py — shared package groups
resolve_package_group("build_tools")
# → {"debian": ["build-essential"], "rhel": ["gcc", "gcc-c++", "make"],
#    "alpine": ["build-base"], "arch": ["base-devel"]}
```

---

## Coverage Summary

| Capability | File | Scope |
|-----------|------|-------|
| Plan resolution | `plan_resolution.py` | Tool + data-pack + config plans |
| Choice system | `choice_resolution.py` | 4 constraint types, conditional inputs, branch selection |
| Dep walking | `dependency_collection.py` | Depth-first, batch optimization, cycle guard |
| Dynamic deps | `dynamic_dep_resolver.py` | 55+ tools, 4-tier cascade, PACKAGE_GROUPS |
| Method picking | `method_selection.py` | 5-tier priority, 8 PMs, batchability |
| Update derivation | `method_selection.py` | Auto-derive update from install commands |
| Env wrapping | `method_selection.py` | bash -c wrapper for non-standard PATH |
| Network probe | `dependency_collection.py` | HTTP HEAD, 60s cache |
| Version fetch | `choice_resolution.py` | Cached version list resolution |
| Input substitution | `choice_resolution.py` | `{var}` templates + 4 built-in variables |
