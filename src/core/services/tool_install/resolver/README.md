# L2 Resolver — Plan Generation

> The brain of the system. Reads recipes (L0) + system profile (L3 input).
> Produces deterministic, executable plans. No subprocess. No filesystem writes.

This layer is where platform adaptation happens. A single recipe dict
becomes a different plan on Ubuntu vs Fedora vs Alpine vs macOS — all
automatically, based on the system profile.

---

## Resolution Pipeline

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

---

## Files

### `method_selection.py` — Install Method Picker

The core platform-adaptation logic. Given a recipe's `install` map and
the detected system profile, picks which method to use.

**Resolution priority:**
1. Recipe's `prefer` list (respects system availability)
2. System's primary PM (apt on Ubuntu, dnf on Fedora, brew on macOS)
3. snap (if available and recipe has snap method)
4. `_default` fallback (universal method, e.g. pip/cargo/curl)
5. Any remaining method whose binary is on PATH

```python
from src.core.services.tool_install.resolver.method_selection import _pick_install_method

# Recipe has: install = {"apt": [...], "dnf": [...], "_default": [...]}
# On Ubuntu (pm="apt") → picks "apt"
# On Fedora (pm="dnf") → picks "dnf"
# On Arch (pm="pacman", no pacman key) → picks "_default"
method = _pick_install_method(recipe, primary_pm="apt", snap_available=True)
```

**Functions:**
| Function | What it does |
|----------|-------------|
| `_pick_install_method(recipe, pm, snap)` | Pick best method for this system |
| `_pick_method_command(method_map, profile)` | Resolve method map to (command, method) |
| `_build_pkg_install_cmd(packages, pm)` | Build `apt-get install`/`dnf install`/etc. |
| `_extract_packages_from_cmd(cmd, pm)` | Parse package names from install command |
| `_is_batchable(method, pm)` | Can this method's packages be batched? |
| `_wrap_with_env(cmd, env)` | Prepend env setup to command |

**Supported package managers:**
apt, dnf, yum, zypper, apk, pacman, brew, snap

### `dependency_collection.py` — Transitive Dependency Walker

Walks the dependency tree depth-first. For each tool:
1. Check if already installed (`shutil.which`)
2. Recurse into `requires.binaries` (other tool recipes)
3. Collect `requires.packages` for this distro family
4. Determine if this tool is batchable (same PM = batch) or needs its own step
5. Track `post_env` for PATH propagation

```python
from src.core.services.tool_install.resolver.dependency_collection import _collect_deps

batch_packages = []   # accumulator: system packages to batch
tool_steps = []       # accumulator: non-batchable tool installs
batched_tools = []    # accumulator: tool IDs installed via batch
post_env_map = {}     # accumulator: tool_id → post_env string
visited = set()       # cycle guard

_collect_deps("cargo-audit", system_profile, visited,
              batch_packages, tool_steps, batched_tools, post_env_map)

# Result:
# batch_packages = ["pkg-config", "libssl-dev"]
# tool_steps = [
#     {"tool_id": "rustup", "recipe": ..., "method": "_default"},
#     {"tool_id": "cargo-audit", "recipe": ..., "method": "_default"},
# ]
# post_env_map = {"rustup": 'export PATH="$HOME/.cargo/bin:$PATH"'}
```

Also includes `_can_reach(endpoint)` for network reachability probing
(cached 60s per host).

### `plan_resolution.py` — Top-Level Plan Resolver

The main entry points. Combines method selection + dependency collection
+ choice resolution into a final executable plan.

**Functions:**
| Function | What it does |
|----------|-------------|
| `resolve_install_plan(tool, profile)` | Full plan for a tool on this system |
| `resolve_install_plan_with_choices(tool, profile, answers)` | Plan with user's choice answers applied |

**Plan assembly order:**
1. Repo setup steps (from all deps that have `repo_setup` for this PM)
2. Batched system packages (ONE apt-get/dnf call for all deps)
3. Tool install steps (non-batchable, ordered by dependency depth)
4. Post-install steps (from recipe `post_install`)
5. Verify step (from recipe `verify`)

Each tool step gets `post_env` from its dependencies injected via
`_wrap_with_env`, so `cargo install` automatically has `~/.cargo/bin` on PATH
even though rustup was just installed in a previous step.

### `choice_resolution.py` — Interactive Choice System

Handles recipes with `choices` — PyTorch (CPU/CUDA/ROCm), Docker (apt/snap/script),
NVIDIA driver (version selection).

**Key principle:** ALL options returned — available AND unavailable.
Unavailable options have `disabled_reason` and `enable_hint`.
The assistant panel renders these for user education.

```python
from src.core.services.tool_install.resolver.choice_resolution import resolve_choices

result = resolve_choices("pytorch", recipe, system_profile)
# result = {
#     "choices": [{
#         "id": "compute",
#         "label": "Compute backend",
#         "options": [
#             {"id": "cpu", "label": "CPU only", "available": True},
#             {"id": "cuda", "label": "NVIDIA CUDA", "available": False,
#              "disabled_reason": "No NVIDIA GPU detected",
#              "enable_hint": "Install NVIDIA GPU + drivers"},
#             {"id": "rocm", "label": "AMD ROCm", "available": False,
#              "disabled_reason": "No AMD GPU detected"},
#         ],
#     }],
# }
```

---

## Determinism Guarantee

Given the same inputs (tool ID + system profile + user choices), the resolver
produces the **exact same plan**. Every time. No randomness. No time-dependent
logic. No external fetches during resolution.

This makes plans:
- **Reproducible** — "this plan didn't work" can be replayed
- **Testable** — pure function, no mocks needed
- **Cacheable** — same inputs = same output
- **Debuggable** — every decision traceable to inputs
