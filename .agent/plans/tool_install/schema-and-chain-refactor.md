# Schema & Chain Refactor Plan

> Discovered during curl per-tool audit (2026-02-26).
> This addresses everything identified during validation/reanalysis.

---

## What the curl audit exposed

The curl audit required:
- A field name that didn't exist in the schema (`configure_args` vs `configure_flags`)
- A field the schema didn't know about (`default_version`)
- An install method value that's a dict, not a list (`install.source`)
- A handler option field that didn't exist (`requires_binary`)
- A remediation chain that should show the full tree of possibilities, not just one level

None of these were caught by validation. None of these were modeled.

---

## Refactor 1: Source Method Sub-Schema

### Problem

`recipe_schema.py` line 172-174 validates install methods:
```python
for method, cmd in install.items():
    if not isinstance(cmd, list):
        errors.append(...)
```

This rejects `install.source` when it's a dict (the structured shape).
The source method has its own shape that is NOT a command list.

### The source spec shape (what exists in code today)

```python
"source": {
    "build_system": str,        # REQUIRED: "autotools" | "cmake" | "cargo" | "meson" | "go" | "make"
    "git_repo": str,            # One of git_repo or tarball_url REQUIRED
    "tarball_url": str,         # One of git_repo or tarball_url REQUIRED
    "default_version": str,     # REQUIRED when tarball_url contains {version}
    "branch": str,              # Optional: git branch/tag (only with git_repo)
    "depth": int,               # Optional: git clone depth (only with git_repo)
    "requires_toolchain": list, # REQUIRED: list of binary names needed for the build
    "configure_args": list,     # Optional: args passed to ./configure (autotools)
    "cmake_args": list,         # Optional: args passed to cmake (cmake)
    "cargo_args": list,         # Optional: args passed to cargo build (cargo)
    "install_prefix": str,      # Optional: --prefix value, default /usr/local
    "build_size": str,          # Optional: "small" | "medium" | "large" — affects timeout
    "configure_timeout": int,   # Optional: configure step timeout in seconds
    "install_needs_sudo": bool, # Optional: whether make install needs sudo, default True
}
```

### What to change in `recipe_schema.py`

1. Line 172-174: Allow `install.source` to be a dict OR a list
2. When it's a dict: validate against the source spec shape above
3. Validate that exactly one of `git_repo` or `tarball_url` is present
4. Validate that `requires_toolchain` is present and is a list
5. Validate that `build_system` is present and is one of the valid values
6. Validate that `default_version` is present when `tarball_url` contains `{version}`
7. Validate that `branch`/`depth` are NOT present when `tarball_url` is used (they only apply to git)
8. Validate that `configure_args` is a list when present

### Valid build_system values

```python
VALID_BUILD_SYSTEMS = {"autotools", "cmake", "cargo", "meson", "go", "make"}
```

### Valid source spec fields

```python
_SOURCE_SPEC_FIELDS = {
    "build_system", "git_repo", "tarball_url", "default_version",
    "branch", "depth", "requires_toolchain", "configure_args",
    "cmake_args", "cargo_args", "install_prefix", "build_size",
    "configure_timeout", "install_needs_sudo",
}
```

### Files to change

| File | Change |
|------|--------|
| `recipe_schema.py` | Add source spec validation, add constants |

---

## Refactor 2: Handler Option Full Schema

### Problem

`recipe_schema.py` line 212 defines the option required fields:
```python
_option_req = {"id", "label", "strategy", "icon"}
```

But options have MANY more fields that are strategy-dependent.
The per-tool analysis doc (line 279-290) documents per-strategy
required fields. None of them are enforced.

Also: `requires_binary` is a new field we added during the curl
refactor. It's not in any schema or doc.

### The full option shape

**Common fields (all strategies):**

| Field | Required? | Type | Description |
|-------|-----------|------|-------------|
| `id` | REQUIRED | str | Unique option ID |
| `label` | REQUIRED | str | Human-readable label |
| `strategy` | REQUIRED | str | One of VALID_STRATEGIES |
| `icon` | REQUIRED | str | Emoji icon |
| `description` | Optional | str | What this option does |
| `recommended` | Optional | bool | Is this the recommended choice? |
| `risk` | Optional | str | "low" \| "medium" \| "high" |
| `requires_binary` | Optional | str | Binary that must be on PATH for this option to be `ready` |
| `group` | Optional | str | "primary" \| "extended" — UI grouping (future) |
| `arch_exclude` | Optional | list[str] | Architectures where this option is impossible |

**Per-strategy required fields:**

| Strategy | Required fields | Type |
|----------|-----------------|------|
| `install_dep` | `dep` | str (tool ID) |
| `install_dep_then_switch` | `dep`, `switch_to` | str, str |
| `install_packages` | `packages` OR `dynamic_packages` | dict \| bool |
| `switch_method` | `method` | str (method key) |
| `retry_with_modifier` | `modifier` | dict |
| `add_repo` | `repo_commands` | list[list[str]] |
| `upgrade_dep` | `dep` | str |
| `env_fix` | `fix_commands` | list[list[str]] |
| `manual` | `instructions` | str |
| `cleanup_retry` | `cleanup_commands` | list[list[str]] |

**Per-strategy optional fields:**

| Strategy | Optional fields | Type |
|----------|-----------------|------|
| `install_dep` | `env_override` | dict[str, str] |
| `install_dep_then_switch` | (none extra) | |
| `install_packages` | (none extra) | |
| `switch_method` | (none extra) | |
| `retry_with_modifier` | `requires_binary` | str |
| `add_repo` | (none extra) | |

### What to change in `recipe_schema.py`

1. Replace the flat `_option_req` / `_option_opt` with per-strategy field maps
2. When validating an option: check common required fields, THEN check strategy-specific required fields
3. Reject unknown fields per strategy (not just unknown in the global set)
4. `packages` validation: keys must be in `VALID_FAMILIES`, values must be lists
5. `modifier` validation: must be a dict
6. `dep` validation: must be a non-empty string

### What to change in `per-tool-full-spectrum-analysis.md`

1. Add `requires_binary` to the option structure table (line 265-275)
2. Add `group` to the option structure table
3. Add `arch_exclude` to the option structure table

### What to change in `remediation_handlers.py`

Nothing — the data is correct. The schema catches the errors.

### Files to change

| File | Change |
|------|--------|
| `recipe_schema.py` | Per-strategy option validation |
| `per-tool-full-spectrum-analysis.md` | Update option structure table |

---

## Refactor 3: Chain Model — From Linear to Tree

### Problem

The current chain model (`_build_chain_context`) is a linear breadcrumb trail:

```python
{
    "chain_id": "abc-123",
    "original_goal": "install-helm",
    "depth": 2,
    "max_depth": 3,
    "breadcrumbs": ["install-helm", "install-curl", "install-wget"],
}
```

This tracks WHERE we are (depth) but not THE FULL TREE of what's possible.

When option A is `locked` with unlock dep `curl`, the user sees:
- "locked (install curl first)"

But they DON'T see:
- curl can be installed via apt (ready)
- curl can be installed via dnf (impossible — not this system)
- curl can be installed via snap (locked — no snapd)
- curl can be built from source (locked — needs make, gcc, ...)

The user sees ONE level. The tree is infinite levels deep.

### The tree model

```
install helm
├── _default method: curl | bash
│   ├── FAILURE: curl not found
│   │   ├── OPTION: install curl via apt         → ready
│   │   │   └── (if that fails: apt repo handler, network handler, ...)
│   │   ├── OPTION: use wget instead             → ready (wget on PATH)
│   │   ├── OPTION: use python3 urllib           → ready (python3 on PATH)
│   │   └── OPTION: build curl from source       → locked (needs make, gcc, ...)
│   │       ├── UNLOCK: install make via apt     → ready
│   │       ├── UNLOCK: install gcc via apt      → ready
│   │       └── (recursive: if make install fails → make's own tree)
├── snap method
│   ├── FAILURE: snapd not installed
│   │   ├── OPTION: install snapd via apt        → ready
│   │   └── (if snapd install fails → snapd's own tree)
```

### What the chain needs to become

```python
{
    "chain_id": "abc-123",
    "original_goal": {
        "tool_id": "helm",
        "method": "_default",
    },
    "current_node": {
        "tool_id": "curl",
        "failure_id": "missing_curl",
        "depth": 1,
    },
    "breadcrumbs": [
        {
            "tool_id": "helm",
            "failure_id": "curl_not_found",
            "chosen_option": "install-curl",
            "depth": 0,
        },
    ],
    "max_depth": 5,
    # The sub-tree is NOT pre-computed in the chain.
    # It's computed on demand when the user asks "what would happen if I pick this option?"
    # The chain just tracks the path taken so far.
}
```

### Key principle: the tree is LAZY, not pre-computed

Pre-computing the full tree for every tool would be:
- Expensive (every tool's every method's every failure's every option ...)
- Fragile (system state changes between computation and execution)
- Unnecessary (user only walks ONE path at a time)

Instead:
1. **At failure time:** Show the options for THIS failure, with availability states
2. **For locked options:** Show what deps are needed and their availability (ONE level of lookahead)
3. **When user picks an option:** Execute it. If it fails, build the NEXT level's options
4. **Breadcrumbs track the path taken** so the user can see "I started with helm, then needed curl, now I'm at wget"

### What changes for ONE level of lookahead on locked options

Currently, a locked option shows:
```python
{
    "id": "build-from-source",
    "availability": "locked",
    "lock_reason": "make not installed (build dependency)",
    "unlock_deps": ["make"],
}
```

With one level of lookahead, it shows:
```python
{
    "id": "build-from-source",
    "availability": "locked",
    "lock_reason": "make not installed (build dependency)",
    "unlock_deps": ["make"],
    "unlock_preview": [
        {
            "dep": "make",
            "install_options": [
                {"method": "apt", "availability": "ready"},
                {"method": "dnf", "availability": "impossible", "reason": "not this system"},
            ],
        },
    ],
}
```

This tells the user: "this option is locked, but make can be installed via apt (ready), so picking this option will first install make, then proceed."

### Files to change

| File | Change |
|------|--------|
| `remediation_planning.py` | `_build_chain_context` → richer node tracking |
| `remediation_planning.py` | `_compute_availability` → one-level lookahead for locked options |
| `remediation_planning.py` | `build_remediation_response` → populate `unlock_preview` |

---

## Refactor 4: Remediation Layers — The Endless Tree

### Problem

The 4-layer cascade (recipe → method_family → infra → bootstrap) runs
once per failure. It collects all matching handlers and all their options.

But when an option says "install curl first" (`install_dep`, dep: curl),
the system does NOT show what installing curl itself involves. The user
picks "install curl", the system tries `apt install curl`, and if THAT
fails — only THEN does the chain advance and show the NEXT failure's options.

The user cannot preview the FULL tree of possibilities before committing.

### What the "endless tree" means

Every remediation option that has a `dep` (another tool) is itself a
node in the tree. That dep has its own recipe, its own methods, its own
potential failures, its own handlers, its own options. Those options
may have their own deps. And so on.

```
helm install fails
  └── options:
      ├── install curl (dep) ──────────────────── node
      │   └── curl recipe:
      │       ├── apt install curl               → ready
      │       ├── snap install curl              → locked (needs snapd)
      │       │   └── snapd recipe:
      │       │       ├── apt install snapd      → ready
      │       │       └── (if fails: snapd tree)
      │       ├── build from source              → locked (needs make, gcc, ...)
      │       │   ├── make recipe:
      │       │   │   ├── apt install make       → ready
      │       │   │   └── (if fails: make tree)
      │       │   └── gcc recipe:
      │       │       ├── apt install gcc        → ready
      │       │       └── (if fails: gcc tree)
      │       └── (if apt fails: apt handler tree)
      ├── use wget (modifier) ──────────────────── leaf (no sub-tree if wget is ready)
      ├── use python3 urllib (modifier) ─────────── leaf
      └── switch to snap method ─────────────────── node
          └── snap install helm
              └── (if fails: snap handler tree)
```

### How to model this WITHOUT pre-computing the full tree

The tree is **demand-driven**:

1. **Level 0 (immediate):** Show options for the current failure.
   Each option has `availability` (ready/locked/impossible).

2. **Level 1 (lookahead):** For `locked` options, show `unlock_preview`:
   what methods exist to install the unlock dep, and are they ready?
   This is computed by looking up the dep's recipe and checking method
   availability against the system profile.

3. **Level 2+ (on demand):** NOT pre-computed. When the user picks an
   option and it fails, the system builds the next level.

4. **The chain tracks the path:** Breadcrumbs record every choice made.
   The UI can show "You're installing helm → needed curl → curl apt failed
   → now choosing how to fix apt" — the user always knows where they are.

5. **Cycle detection:** The chain tracks visited tool_ids. If a dep
   appears in the breadcrumbs already, the option is marked `impossible`
   with reason "circular dependency detected."

### Level 1 lookahead implementation

```python
def _compute_unlock_preview(
    unlock_deps: list[str],
    system_profile: dict | None,
) -> list[dict]:
    """For each unlock dep, preview how it can be installed."""
    previews = []
    for dep in unlock_deps:
        recipe = TOOL_RECIPES.get(dep, {})
        install_methods = recipe.get("install", {})
        options = []
        for method_key in install_methods:
            # Check if this method is available on this system
            avail = _compute_method_availability(method_key, system_profile)
            options.append({
                "method": method_key,
                "availability": avail[0],  # ready/locked/impossible
                "reason": avail[1] or avail[3],
            })
        previews.append({
            "dep": dep,
            "label": recipe.get("label", dep),
            "install_options": options,
        })
    return previews
```

### Files to change

| File | Change |
|------|--------|
| `remediation_planning.py` | Add `_compute_unlock_preview` |
| `remediation_planning.py` | Add `_compute_method_availability` (extract from `_compute_availability`) |
| `remediation_planning.py` | `build_remediation_response` → populate `unlock_preview` on locked options |
| `remediation_planning.py` | Cycle detection in `_build_chain_context` |

---

## Execution Order

These refactors build on each other:

| Order | Refactor | Why this order |
|-------|----------|---------------|
| 1 | Source method sub-schema | Foundation — the recipe shape must be correct before anything else |
| 2 | Handler option full schema | Foundation — per-strategy fields must be validated to be consistent |
| 3 | Chain model evolution | Infra — the chain must track the tree path before lookahead can work |
| 4 | Remediation tree lookahead | Feature — requires schema + chain to be solid first |

---

## Files touched (complete list)

| File | Refactors |
|------|-----------|
| `src/core/services/tool_install/data/recipe_schema.py` | 1, 2 |
| `src/core/services/tool_install/domain/remediation_planning.py` | 3, 4 |
| `.agent/plans/tool_install/per-tool-full-spectrum-analysis.md` | 2 |

No changes to `recipes.py`, `remediation_handlers.py`, `handler_matching.py`,
or `build_helpers.py`. This refactor is schema + planning layer only.
The data and execution layers are already correct.
