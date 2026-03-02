# L1 Domain — Pure Logic

> **11 files · 1,811 lines · Zero I/O. Pure input → output.**
>
> No subprocess. No filesystem. No network. Fully testable with no mocks.
> These functions operate on plan data, step dicts, and version strings.
> Called by the resolver (L2) and orchestrator (L5).

---

## How It Works

### Domain Responsibilities

```
┌──────────────────────────────────────────────────────────────┐
│ L1 DOMAIN — PURE LOGIC                                        │
│                                                               │
│  RISK ASSESSMENT                                              │
│  risk.py ─────────── Step/plan risk levels → UI indicators    │
│                                                               │
│  DEPENDENCY GRAPH                                             │
│  dag.py ──────────── Step ordering, cycle detection,          │
│                      PM lock conflict prevention              │
│                                                               │
│  ROLLBACK & RESTART                                           │
│  rollback.py ─────── Undo steps from completed steps          │
│  restart.py ──────── Shell/service/reboot detection            │
│                                                               │
│  VALIDATION                                                   │
│  version_constraint.py ─ Semver constraint checking           │
│  input_validation.py ─── User input validation (6 types)      │
│                                                               │
│  REMEDIATION                                                  │
│  handler_matching.py ──── 4-layer cascade pattern match       │
│  remediation_planning.py ── Full §6 response builder          │
│                                                               │
│  BUILD & DOWNLOAD                                             │
│  error_analysis.py ───── Build failure pattern matching       │
│  download_helpers.py ─── Size formatting, time estimation     │
│                                                               │
│  INVARIANT: No subprocess. No file I/O. No network.          │
│  INVARIANT: Same inputs → same outputs. Always.              │
└──────────────────────────────────────────────────────────────┘
```

### The Remediation Pipeline

```
FAILURE (tool, method, stderr, exit_code, system_profile)
     │
     ▼
handler_matching._collect_all_options()
     │  Cascades through 4 handler layers:
     │    Layer 3: Tool-specific      (TOOL_FAILURE_HANDLERS[tool_id])
     │    Layer 2b: Install pattern   (recipe.install_via → METHOD_FAMILY_HANDLERS)
     │    Layer 2a: Method family     (METHOD_FAMILY_HANDLERS[method])
     │    Layer 1: Infrastructure     (INFRA_HANDLERS)
     │    Layer 0: Bootstrap          (BOOTSTRAP_HANDLERS)
     │
     │  Does NOT stop at first match — collects everything
     │  Deduplicates by option ID (first occurrence wins)
     ▼
handler_matching._sort_options()
     │  Sorts by: recommended > layer priority > availability
     ▼
remediation_planning.build_remediation_response()
     │  For each option:
     │    1. _compute_availability() → ready | locked | impossible
     │    2. _compute_step_count() → estimated execution steps
     │    3. _compute_unlock_preview() → how to install locked deps
     │
     │  Assembles the full §6 response shape
     ▼
OUTPUT: Structured remediation response for the UI
```

---

## File Map

```
domain/
├── __init__.py               44 lines  — re-exports all pure domain functions
├── remediation_planning.py  733 lines  — §6 response builder, availability engine
├── handler_matching.py      190 lines  — 4-layer cascade, pattern matching, sorting
├── dag.py                   178 lines  — step DAG: deps, cycles, PM locks
├── error_analysis.py        146 lines  — build failure patterns, progress parsing
├── input_validation.py      127 lines  — user input + template output validation
├── risk.py                  118 lines  — step/plan risk levels, escalation detection
├── restart.py               104 lines  — restart detection + batching
├── version_constraint.py    103 lines  — semver constraint checking (4 modes)
├── download_helpers.py       39 lines  — size formatting, download time estimation
├── rollback.py               29 lines  — undo plan from completed steps
└── README.md                           — this file
```

---

## Per-File Documentation

### `__init__.py` — Re-exports (44 lines)

Re-exports all public and private symbols from all domain modules:

```python
from src.core.services.tool_install.domain import _infer_risk, _validate_dag, _generate_rollback
```

### `remediation_planning.py` — Response Builder (733 lines)

The largest domain file. Builds the complete §6 remediation response
for the UI when tool installation fails.

**Pipeline:**

```
build_remediation_response()
    ├── _collect_all_options()        # from handler_matching.py
    ├── _sort_options()               # from handler_matching.py
    ├── for each option:
    │     ├── _compute_availability() # ready|locked|impossible
    │     ├── _compute_step_count()   # estimated steps
    │     └── _compute_unlock_preview() # how to unlock locked deps
    ├── _build_chain_context()        # failure breadcrumb trail
    └── assemble final response
```

| Function | What It Does |
|----------|-------------|
| `build_remediation_response(tool_id, step_idx, ...)` | Main entry: produces full §6 remediation response |
| `_compute_availability(option, recipe, profile)` | Determines if option is ready, locked, or impossible |
| `_check_dep_availability(dep, profile)` | Check if a dependency (recipe or package) is available |
| `_compute_step_count(option, profile)` | Estimate execution steps for UI progress display |
| `_compute_method_availability(method, profile)` | Check if an install method is usable on this system |
| `_compute_unlock_preview(deps, profile)` | One-level lookahead: how to install locked dependencies |
| `_build_chain_context(chain, tool_id)` | Build failure breadcrumb trail ("helm → curl → curl apt failed") |
| `to_legacy_remediation(response)` | Convert §6 response to legacy `{reason, options}` shape |
| `_get_family(profile)` | Extract distro family from system profile |
| `_get_available_pms(profile)` | Extract available package managers from profile |

**Availability states:**

| State | Meaning | UI Treatment |
|-------|---------|-------------|
| `ready` | Can execute immediately | Primary action button |
| `locked` | Missing prerequisites | Show unlock path + grayed button |
| `impossible` | Can never work on this system | Explain why + hide |

### `handler_matching.py` — Cascade Pattern Matching (190 lines)

Matches failure stderr against handler patterns from 4 layers.

| Function | What It Does |
|----------|-------------|
| `_matches(handler, stderr, exit_code)` | Check if handler's pattern+exit_code match the failure |
| `_collect_all_options(tool_id, method, stderr, exit_code, recipe)` | Cascade through all 4 layers, collect+dedup all matching options |
| `_sort_options(options)` | Sort by recommended → layer priority → availability state |

**Cascade layers (priority order):**

| Layer | Source | Priority |
|-------|--------|----------|
| `recipe` | `TOOL_FAILURE_HANDLERS[tool_id]` | 0 (highest) |
| `method_family` | `METHOD_FAMILY_HANDLERS[method]` | 1 |
| `infra` | `INFRA_HANDLERS` | 2 |
| `bootstrap` | `BOOTSTRAP_HANDLERS` | 3 (lowest) |

### `dag.py` — Dependency Graph (178 lines)

Step ordering for parallel execution with PM lock safety.

| Function | What It Does |
|----------|-------------|
| `_add_implicit_deps(steps)` | Add linear dependencies + auto-generate step IDs for plan steps |
| `_validate_dag(steps)` | Validate DAG: duplicate IDs, missing refs, cycle detection (Kahn's algorithm) |
| `_get_ready_steps(steps, completed, running)` | Find steps whose deps are all completed (not running or pending) |
| `_get_step_pm(step)` | Extract PM from step command (apt, dnf, apk, pacman, zypper, snap, brew) |
| `_enforce_parallel_safety(steps)` | Filter parallel candidates: only one step per PM at a time |

**Cycle detection algorithm:** Kahn's topological sort — O(V+E). If
`processed < len(steps)` after BFS, a cycle exists.

### `error_analysis.py` — Build Failure Patterns (146 lines)

Parses build tool output for known failure patterns.

| Function | What It Does |
|----------|-------------|
| `_parse_build_progress(output)` | Parse ninja `[N/M]`, cmake `[N%]`, make heuristics → progress dict |
| `_analyse_build_failure(tool, stderr, build_system)` | Match stderr against 6 failure patterns → `{cause, suggestion, confidence}` |

**Known failure patterns:**

| Pattern | Cause | Confidence |
|---------|-------|-----------|
| `fatal error: *.h: No such file` | Missing header file | High |
| `cannot find -l<lib>` | Missing library | High |
| `internal compiler error` + killed | Out of memory (OOM) | Medium |
| `could not find` + cmake | CMake package not found | Medium |
| `cc: not found` / `gcc: not found` | Missing compiler | High |
| `permission denied` | Permission issue | Medium |

### `input_validation.py` — Input Validation (127 lines)

Validates user inputs and rendered template output.

| Function | What It Does |
|----------|-------------|
| `_validate_input(input_def, value)` | Validate one input against its schema → error string or None |
| `_validate_output(content, fmt)` | Validate rendered template against format (JSON, YAML, INI) |
| `_check_unsubstituted(rendered)` | Find unresolved `{var}` placeholders in rendered output |

**Supported input types:**

| Type | Validation Rules |
|------|-----------------|
| `select` | Value must be in `options` list |
| `number` | Must be numeric, within `min`/`max` range |
| `text` | String, `min_length`/`max_length`/`pattern` (regex) |
| `path` | Must start with `/` (absolute path) |
| `boolean` | Must be `True` or `False` |
| `password` | Min length, implicitly sensitive (never logged) |

### `risk.py` — Risk Assessment (118 lines)

Computes risk levels for steps and plans.

| Symbol | What It Does |
|--------|-------------|
| `_infer_risk(step)` | Infer risk from step context (sudo, label keywords, restart type) |
| `_plan_risk(steps)` | Aggregate risk across all steps → `{level, counts, has_high}` |
| `_check_risk_escalation(recipe, resolved_risk)` | Detect if user choices escalated risk beyond recipe default |
| `_HIGH_RISK_LABELS` | Frozenset: kernel, driver, grub, bootloader, dkms, vfio, modprobe, nvidia |
| `_RISK_ORDER` | Dict: `{"low": 0, "medium": 1, "high": 2}` |

**Risk inference rules (first match wins):**

```
restart_required == "system"     → HIGH
label contains high-risk keyword → HIGH
needs_sudo == True               → MEDIUM
otherwise                        → LOW
explicit step["risk"] always wins
```

### `restart.py` — Restart Detection (104 lines)

Detects restart needs from completed plan steps.

| Function | What It Does |
|----------|-------------|
| `detect_restart_needs(plan, completed_steps)` | Scan steps for PATH changes, config changes, kernel modules, GPU drivers |
| `_batch_restarts(restart_needs)` | Convert restart needs into service steps + notifications |

**Restart triggers:**

| Trigger | Type | Action |
|---------|------|--------|
| `post_env` in plan | Shell | Notification: "Restart shell" |
| Config step with `restart_service` | Service | `systemctl restart <svc>` |
| `modprobe` command | Reboot | Notification: "Reboot recommended" |
| GPU driver step | Reboot | Notification: "Reboot required" |

### `version_constraint.py` — Version Validation (103 lines)

Validates selected versions against semver constraints.

| Function | What It Does |
|----------|-------------|
| `check_version_constraint(version, constraint)` | Validate version against 4 constraint types → `{valid, message, warning}` |

**Constraint types:**

| Type | Example | Rule |
|------|---------|------|
| `minor_range` | `{"type": "minor_range", "reference": "1.30.0", "range": 1}` | Same major, minor within ±N |
| `gte` | `{"type": "gte", "reference": "2.0.0"}` | Selected ≥ reference |
| `exact` | `{"type": "exact", "reference": "3.1.4"}` | Exact match |
| `semver_compat` | `{"type": "semver_compat", "reference": "1.5.0"}` | Same major, selected ≥ reference minor |

### `download_helpers.py` — Download UX Helpers (39 lines)

Format file sizes and estimate download times.

| Function | What It Does |
|----------|-------------|
| `_fmt_size(n)` | Format bytes → "1.0 MB", "3.2 GB" etc. |
| `_estimate_download_time(size_bytes)` | Estimate at 10/50/100 Mbps → `{"10 Mbps": "2m 30s", ...}` |

### `rollback.py` — Rollback Plan Generation (29 lines)

Generates undo plans from completed steps.

| Function | What It Does |
|----------|-------------|
| `_generate_rollback(completed_steps)` | Reverse completed steps, extract `rollback` field from each → undo list |

---

## Dependency Graph

```
__init__.py          ← re-exports from all modules below

remediation_planning.py
   ├── handler_matching.py      (cascade + options)
   ├── data.recipes.TOOL_RECIPES  (for recipe lookup + CLI checks)
   └── shutil.which              (only stdlib — for binary availability)

handler_matching.py
   ├── data.remediation_handlers (BOOTSTRAP, INFRA, METHOD_FAMILY)
   └── data.tool_failure_handlers (TOOL_FAILURE_HANDLERS)

dag.py               ← standalone (no domain imports)
risk.py              ← standalone (no domain imports)
rollback.py          ← standalone (no domain imports)
restart.py           ← standalone (no domain imports)
version_constraint.py ← standalone (no domain imports)
input_validation.py  ← standalone (json, re, configparser, yaml)
error_analysis.py    ← standalone (re only)
download_helpers.py  ← standalone (no imports)
```

**Note:** `remediation_planning.py` uses `shutil.which()` for binary
existence checks. This is an acceptable impurity — it reads PATH state
but doesn't execute anything.

---

## Key Data Shapes

### _plan_risk() output

```python
{
    "level": "medium",           # highest step risk
    "counts": {"low": 3, "medium": 2, "high": 0},
    "has_high": False,
    "has_medium": True,
}
```

### detect_restart_needs() output

```python
{
    "shell_restart": True,
    "service_restart": ["docker", "nginx"],
    "reboot_required": False,
    "reasons": ["PATH was modified — restart shell", "Config changed — restart docker"],
}
```

### build_remediation_response() output (§6 shape)

```python
{
    "tool": "cargo-audit",
    "step_idx": 0,
    "step_label": "install cargo-audit",
    "failure": {
        "exit_code": 101,
        "matched_handlers": [...],
    },
    "options": [
        {
            "id": "retry_deps",
            "label": "Install missing dependencies first",
            "recommended": True,
            "availability": "ready",        # or "locked", "impossible"
            "estimated_steps": 3,
            "_source_layer": "method_family",
        },
        ...
    ],
    "chain": {
        "depth": 0,
        "breadcrumbs": [...],
    },
    "actions": [
        {"id": "retry", "label": "Retry", "icon": "🔄"},
        {"id": "skip", "label": "Skip this tool", "icon": "⏭️"},
        {"id": "cancel", "label": "Cancel", "icon": "✕"},
    ],
}
```

---

## Design Decisions

### Why remediation_planning is the largest domain file

It handles the most complex business logic in the provisioning engine:
determining what the user can do when installation fails. It must
consider the handler cascade, compute availability for each option
(which requires checking binary existence, PM availability, and
recipe dependencies), estimate step counts, and provide unlock previews.
This is inherently complex and can't be simplified without losing
functionality.

### Why handler matching collects ALL matches (not first-match)

A failure might match multiple handler layers simultaneously. For
example, a cargo OOM failure matches both the tool-specific handler
(Layer 3) and the infrastructure handler for OOM (Layer 1). By
collecting all matches, the UI can present the user with multiple
remediation paths ranked by relevance.

### Why DAG uses Kahn's algorithm

Kahn's topological sort handles cycle detection as a natural byproduct —
if the BFS doesn't process all nodes, there's a cycle. This avoids
needing a separate cycle detection pass. The O(V+E) complexity is
appropriate for plans with typically 3-15 steps.

### Why risk inference has a keyword-based fallback

Step labels like "Install NVIDIA driver" or "Update GRUB" should
automatically trigger high risk without requiring every recipe to
declare `risk: "high"` explicitly. The `_HIGH_RISK_LABELS` frozenset
acts as a safety net — even if a recipe author forgets the risk field,
dangerous operations are flagged.

### Why input validation handles 6 types

Recipes can define interactive inputs (choice fields, path selectors,
version numbers). Each input type needs its own validation logic to
prevent invalid data from reaching the resolver or execution layers.
The `password` type has special semantics — values are never logged
or persisted in plan state.

---

## Advanced Feature Showcase

### 1. 4-Layer Handler Cascade with Priority Sorting

```python
# handler_matching.py — collects from ALL layers, deduplicates, sorts
matched_handlers, options = _collect_all_options(
    tool_id="cargo-audit", method="cargo", stderr="error[E0463]...", exit_code=101
)
# Scans: recipe → method_family → infra → bootstrap
# Each option tagged with _source_layer + _source_handler
# Deduped by option ID (first occurrence wins = higher priority)

sorted_options = _sort_options(options)
# Sort: recommended > layer priority > availability
```

### 2. Availability State Machine (3 states)

```python
# remediation_planning.py — _compute_availability()
# For each remediation option, determines:
#   "ready"     → binary on PATH, PM available → can execute NOW
#   "locked"    → prerequisite missing → show unlock path
#   "impossible" → native PM mismatch (apt on Fedora) → explain why

# Native PM check: apt/dnf/yum/zypper/apk/pacman → tied to distro
# Language PM check: pip/npm/cargo/go → binary must be on PATH
# Locked options get unlock_preview: how to install the missing dep
```

### 3. Cycle-Safe DAG with PM Lock Conflicts

```python
# dag.py — prevents two apt-get calls from running in parallel
ready = _get_ready_steps(steps, completed={"step_0"}, running=set())
# Returns all steps whose deps are satisfied

safe = _enforce_parallel_safety(ready)
# Filters: only one step per PM (apt, dnf, brew, etc.)
# Two apt-get steps → first runs, second waits
```

### 4. Version Constraint with ±N Minor Range

```python
# version_constraint.py — kubectl version compatibility
result = check_version_constraint("1.28.0", {
    "type": "minor_range",
    "reference": "1.30.0",
    "range": 1,
})
# → {"valid": False, "message": "2 minor versions away from 1.30.0. Max: ±1."}
```

### 5. Build Progress Parsing (3 build systems)

```python
# error_analysis.py — _parse_build_progress()
_parse_build_progress("[45/100] Compiling main.rs")
# → {"total_targets": 100, "completed": 45, "percent": 45}

_parse_build_progress("[ 83%] Building CXX object")
# → {"percent": 83}
```

### 6. Risk Escalation Detection

```python
# risk.py — _check_risk_escalation()
recipe = {"risk": "low"}  # Recipe says low risk
resolved = _plan_risk(steps)  # But resolved plan has sudo steps → medium
escalation = _check_risk_escalation(recipe, resolved)
# → {"from": "low", "to": "medium", "reason": "Your choices escalated..."}
```

---

## Coverage Summary

| Capability | File | Scope |
|-----------|------|-------|
| Risk levels | `risk.py` | 3 levels (low/medium/high), 8 trigger keywords, escalation detection |
| DAG validation | `dag.py` | Cycle detection (Kahn's), PM lock safety (7 PMs), implicit deps |
| Rollback | `rollback.py` | Reverse order, extracts from step `rollback` field |
| Restart | `restart.py` | Shell/service/reboot detection, batch conversion |
| Version checks | `version_constraint.py` | 4 modes: minor_range, gte, exact, semver_compat |
| Input validation | `input_validation.py` | 6 types: select, number, text, path, boolean, password |
| Output validation | `input_validation.py` | 3 formats: JSON, YAML, INI |
| Handler cascade | `handler_matching.py` | 4 layers, dedup, priority sort |
| Remediation | `remediation_planning.py` | 3 availability states, unlock preview, chain breadcrumbs |
| Build errors | `error_analysis.py` | 6 patterns, 3 build system parsers |
| Download UX | `download_helpers.py` | Size formatting, 3-speed time estimation |
