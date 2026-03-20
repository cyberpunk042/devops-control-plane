# M4 — Handler Integration: Clean Up Every Modified File

> The commit modified 6 handler/route files by bolting compat engine calls into them
> via try/except blocks. Each one creates a fresh orchestrator, runs a full analysis,
> and falls back to legacy on failure. After M1-M3, the mediator owns the orchestrator
> and cached analysis. This milestone rewrites every handler to use the mediator properly.

---

## What Exists Now (broken)

### code_scanner.py — 3 try/except compat blocks

`handle_add_future_annotations()` (line 140-204):
- Creates CompatOrchestrator.create() — 2.9s first, 33ms after
- Runs analyze_module() on entire module — 57s (pre-M2)
- Filters to add_future_import findings — throws away 99% of results
- Applies fixes in a loop, then RE-APPLIES them in a list comprehension (double fix)
- Falls back to legacy regex on any exception

`_scan_features()` (line 302-357):
- Same pattern — create orchestrator, full analysis, fall back
- Read-only scan — no fixes, just returns findings

`handle_guide_incompatible_syntax()` (line 757-840):
- Same pattern — create orchestrator, full analysis, fall back
- Read-only guide — no fixes

### executor.py — compat analysis in rescan

`handle_rescan_module()` (line 155-193):
- Creates CompatOrchestrator.create() + analyze_module()
- `except Exception: pass` — swallows 60s failure silently
- remaining_findings=0 when analysis crashes — false "clean" result
- Runs this BEFORE the mediator cache refresh

Mark-done logic (line 97-128):
- Expanded from 2 conditions to 5 nested conditions
- `step_not_done` flag pattern added for compat results
- `_mark_step_done` removed from `_check_already_done` path

### wizard.py — copy-pasted mark-done logic

Lines 563-590:
- Same 5-condition mark-done logic from executor.py duplicated
- Comment says "ONE logic, no divergence" — but it IS two copies

### posture.py — compat-fix endpoint

`posture_module_compat_fix()` (line 1690-1827):
- Creates uncached CompatOrchestrator.create()
- Runs full analyze_module() to fix ONE pattern
- Imports private function `_get_plan_target` cross-module

### compat.py — _get_orchestrator

`_get_orchestrator()` (line 18-29):
- Caches on `current_app._compat_orchestrator` — fragile
- Still creates via CompatOrchestrator.create()

---

## What M4 Delivers

### 1. code_scanner.py — All 3 handlers cleaned up

All three handlers follow the same pattern after M4:

```python
def _scan_features(ctx, direction):
    # Try compat engine via mediator — 0ms if cached, None if not loaded
    m = get_mediator()
    compat_data = m.peek("compat.orchestrator")
    if compat_data is not None:
        compat = compat_data["data"]
        # Read cached analysis — 0ms
        analysis_data = m.peek(f"compat.analysis.{ctx.module_name}")
        if analysis_data is not None:
            result = analysis_data["data"]
            # Format findings for UI
            return _format_scan_result(result, ctx, direction)

    # Compat not available — use existing legacy path (fast, works)
    # ... existing compute_code_floor() code unchanged ...
```

No try/except. No creating orchestrators. No running analysis. Either cached data
is available (0ms) or it isn't (legacy path).

`handle_add_future_annotations()` — remove double fix_finding() loop. Use single
loop that tracks fixed files:

```python
fixed_files = set()
for finding in future_findings:
    fix_result = compat.fix.fix_finding(finding, ctx.project_root, verify=False)
    if fix_result.success:
        fixed_files.add(finding.file)
return {"ok": True, "summary": f"Added __future__ to {len(fixed_files)} file(s)"}
```

### 2. executor.py — handle_rescan_module restored

Restore original behavior — mediator cache invalidation + recompute:

```python
def handle_rescan_module(ctx, mode):
    if mode == "preview":
        return {"ok": True, "can_apply": True, ...}

    # Invalidate compat analysis cache (cascade handles posture)
    m = get_mediator()
    m.bust_path(f"compat.analysis.{ctx.module_name}", cascade=True)

    # Refresh posture via mediator
    m.put("posture.modules", cascade=True)

    return {"ok": True, "summary": "Module re-scanned successfully"}
```

No compat analysis in the handler. The bust_path invalidates cached analysis.
The mediator cascade invalidates posture. Next peek() for the analysis triggers
a background recompute via WorkQueue.

No `except Exception: pass`. No false "clean" results.

### 3. executor.py — mark-done logic simplified

Restore the original 2-condition check:

```python
if mode == "execute" and result.get("ok"):
    findings = result.get("findings", [])
    has_incompatible = any(
        not f.get("compatible") and not f.get("unknown")
        for f in findings if isinstance(f, dict)
    )
    if has_incompatible:
        result["step_not_done"] = True
    else:
        _mark_step_done(module_name, step_id)
```

Restore `_mark_step_done` in `_check_already_done` return path.

Remove the `step_not_done` flag, `can_apply is False` check, and 3-level nesting.
These were added to handle compat analysis results that no longer come through handlers.

### 4. wizard.py — shared mark-done function

Extract mark-done logic into a shared function:

```python
# In executor.py:
def should_mark_done(result):
    """Determine if a step result should be marked done.

    ONE function, called by executor.py and wizard.py.
    """
    if not result.get("ok"):
        return False
    findings = result.get("findings", [])
    if not findings:
        return True
    has_incompatible = any(
        not f.get("compatible") and not f.get("unknown")
        for f in findings if isinstance(f, dict)
    )
    return not has_incompatible
```

wizard.py calls `should_mark_done(result)` instead of duplicating the logic.

### 5. posture.py — compat-fix endpoint cleaned up

```python
def posture_module_compat_fix():
    # Try compat engine for AST-based fix
    m = get_mediator()
    compat_data = m.peek("compat.orchestrator")
    if compat_data is not None:
        compat = compat_data["data"]
        # Use registry to find matching entry
        entries = compat.registry.search(search)
        if entries:
            # Get cached analysis — don't re-analyze
            analysis_data = m.peek(f"compat.analysis.{module_name}")
            if analysis_data is not None:
                # Filter to matching findings and fix them
                ...
                # Invalidate cache after fix
                m.bust_path(f"compat.analysis.{module_name}", cascade=True)
                return jsonify({"ok": True, ...})

    # Legacy string-replace fallback (milliseconds)
    # ... existing code unchanged ...
```

No orchestrator creation. No full analysis. Read from cache or fall back.

### 6. compat.py — use mediator directly

Replace `_get_orchestrator()`:

```python
def _get_orchestrator():
    from src.core.services.mediator import get_mediator
    m = get_mediator()
    return m.get("compat.orchestrator")["data"]
```

No `current_app._compat_orchestrator`. No CompatOrchestrator.create(). The mediator
owns the instance.

---

## Files Changed

| File | Action |
|------|--------|
| `src/core/services/module_upgrade/automation/code_scanner.py` | Remove 3 try/except blocks, use mediator peek, fix double-apply |
| `src/core/services/module_upgrade/automation/executor.py` | Restore handle_rescan_module, simplify mark-done, restore _check_already_done |
| `src/core/services/module_upgrade/automation/wizard.py` | Use shared should_mark_done(), remove duplicated logic |
| `src/ui/web/routes/posture.py` | Clean up compat-fix endpoint |
| `src/ui/web/routes/compat.py` | Replace _get_orchestrator() with mediator.get() |

---

## Verification

1. No handler calls CompatOrchestrator.create()
2. No handler calls analyze_module() directly
3. No `except Exception: pass` in executor.py
4. handle_rescan_module completes in <5s
5. handle_add_future_annotations does not double-apply fixes
6. should_mark_done is ONE function used by both executor and wizard
7. `grep -r "step_not_done" src/core/services/module_upgrade/` returns 0 hits
