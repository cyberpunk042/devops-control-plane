# M9 — Step Integration: Compat V2 Powers the Automation Flow

> The upgrade/downgrade automation flow creates a plan, then executes steps.
> Four critical steps need the compat v2 engine: scan_incompatible_features,
> add_future_annotations, guide_incompatible_syntax, rescan_module.
>
> Currently these handlers read from `peek("compat.analysis.{module}")`, get
> `None` (analysis never triggered), and fall through to legacy regex.
>
> This milestone makes the compat engine the ACTUAL engine that powers
> step execution. The legacy fallback stays for graceful degradation
> but should never be the primary path.

---

## The Current Flow

```
User creates plan (target: 3.8)
  → generate_checklist() → writes steps to project.yml
  → Steps include: scan_incompatible_features, add_future_annotations, etc.

User clicks "Automate" on a step
  → executor.py → handler registry → e.g. _scan_features()
  → _scan_features() calls peek("compat.analysis.{module}")
  → Returns None (nobody triggered the analysis computation)
  → Falls through to legacy regex scan (compute_code_floor)
  → Returns results from ~13 regex patterns instead of 1000 database entries
```

## The Problem

The `compat.analysis.{module}` mediator nodes are registered with `TTL=None`
(event-driven). They only compute when:
1. Something calls `mediator.get("compat.analysis.{module}")` — never happens from handlers (they use `peek`)
2. Or when `index.scan` cascades — but compat.analysis depends on compat.orchestrator which depends on compat.registry which is BACKGROUND(5) dispatched and may not be loaded yet

So the analysis sits idle. The handlers use legacy. The 1000-entry database is never consulted during step execution.

## The Solution

### 1. Trigger analysis when a plan is created

When `posture_module_plan()` creates a plan with a target, dispatch the compat
analysis for that module:

```python
# In posture_module_plan() after writing project.yml:
m = get_mediator()
m.put("posture.modules", cascade=True)

# Also dispatch compat analysis so it's ready when steps execute
try:
    m.dispatch(f"compat.analysis.{module_name}")
except Exception:
    pass  # Node may not exist if compat isn't loaded yet
```

This means: by the time the user opens the plan modal and clicks "Automate",
the compat analysis is already cached and `peek()` returns data.

### 2. Handlers use `get()` not `peek()` for compat analysis

The handlers should use `mediator.get()` (which blocks and computes if needed)
instead of `peek()` (which returns None if not cached). BUT — they should use
it with a timeout to avoid blocking forever:

```python
# Instead of:
_analysis_data = _m.peek(f"compat.analysis.{ctx.module_name}")
if _analysis_data is None:
    raise RuntimeError("compat analysis not cached yet")

# Use:
try:
    _analysis_data = _m.get(f"compat.analysis.{ctx.module_name}", max_age=120)
    result = _analysis_data["data"]
except Exception:
    raise RuntimeError("compat analysis not available")
```

This way:
- If analysis is cached: <1ms (cache hit)
- If analysis is in progress: waits for it (the dispatch from plan creation is running)
- If analysis never started: triggers computation (first time, ~3s with M2 optimizations)
- Fall-through to legacy only if the compat system is completely broken

### 3. The `rescan_module` handler triggers fresh analysis

When rescan runs, it should:
1. Bust the existing compat analysis cache
2. Dispatch a fresh analysis
3. Bust posture.modules (existing behavior)

The fresh analysis runs in the WorkQueue. The rescan returns immediately with
"Module re-scanned" and the next step that reads the analysis gets the fresh results.

### 4. The `add_future_annotations` handler uses compat fix engine

Currently it reads cached analysis for the findings, then needs the orchestrator
for `fix.fix_finding()`. This is already correct in the M4 changes — it calls
`peek("compat.orchestrator")` for the fix engine. As long as the analysis and
orchestrator are available, this works.

### 5. Plan creation also dispatches compat.registry if not loaded

The plan creation is the first user action that needs compat. If the registry
hasn't loaded yet (BACKGROUND dispatch), plan creation should wait for it:

```python
# In posture_module_plan():
m = get_mediator()
# Ensure compat is available before dispatching analysis
try:
    m.get("compat.registry")  # blocks until loaded (~1s first time)
    m.dispatch(f"compat.analysis.{module_name}")
except Exception:
    pass  # Compat not available — steps will use legacy
```

---

## Steps That Change

| Handler | Current | After M9 |
|---------|---------|----------|
| `_scan_features()` | `peek()` → None → legacy | `get()` → compat analysis (1000 entries) |
| `handle_guide_incompatible_syntax()` | `peek()` → None → legacy | `get()` → compat analysis + rewrite hints |
| `handle_add_future_annotations()` | `peek()` → None → legacy | `get()` → compat findings + fix engine |
| `handle_rescan_module()` | busts cache, mediator refresh | busts cache, dispatches fresh analysis, mediator refresh |

## Steps That DON'T Change

| Handler | Reason |
|---------|--------|
| `check_dep_compat_pypi` | Uses its own dep checker, not compat AST engine |
| `run_pip_install` | Subprocess, no compat involvement |
| `update_ci_matrix` | File editing, no compat involvement |
| `scaffold_module_tests` | File generation, no compat involvement |
| `generate_smart_tests` | File generation, no compat involvement |
| `setup_test_env` | Venv creation, no compat involvement |
| `run_isolated_tests` | Subprocess (pytest), no compat involvement |
| Config editors | YAML/TOML editing, no compat involvement |

## What This Achieves

After M9:
- Creating a plan triggers compat analysis in background
- By the time user clicks first step, analysis is cached
- `scan_incompatible_features` returns findings from 1000 database entries (not 13 regex patterns)
- `guide_incompatible_syntax` shows AST-accurate rewrite hints from the database
- `add_future_annotations` uses AST detection (not regex) to find files needing `__future__`
- `rescan_module` verifies using the compat engine, not just posture mediator refresh
- Legacy fallback still works if compat engine fails

## Files Changed

| File | Change |
|------|--------|
| `src/ui/web/routes/posture.py` | posture_module_plan: dispatch compat analysis after plan creation |
| `src/core/services/module_upgrade/automation/code_scanner.py` | Change `peek()` to `get()` in 3 handlers |
| `src/core/services/module_upgrade/automation/executor.py` | handle_rescan_module: dispatch fresh analysis |

## Verification

1. Create a new plan for module "core" targeting 3.8
2. Open plan modal → steps are listed
3. Click "Automate" on "Scan for features not available in Python 3.8"
4. Result shows findings from compat AST engine (not legacy regex)
   - Should show datetime.UTC, StrEnum, tomllib, etc. with fix availability
   - Should show severity levels (error/warning/info)
   - Should show exact file:line locations from AST (not regex approximate)
5. Click "Automate" on "Add __future__ annotations"
   - Should use compat fix engine to add imports
   - Should verify via AST that annotations are added correctly
6. Click "Automate" on "Re-scan module"
   - Should show remaining findings count from fresh compat analysis
   - If all fixed, should report "Clean"
