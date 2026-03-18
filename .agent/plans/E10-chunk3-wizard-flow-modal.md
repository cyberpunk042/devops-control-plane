# E10 Chunk 3 — Wizard Flow Modal

> Interactive multi-step wizard for complex automation.
> Depends on: Chunks 1 + 2 complete.
> Architecture: `.agent/docs/E10-wizard-automation-architecture.md`
> Status: READY FOR PLANNING

---

## What This Chunk Delivers

Complex automations open a wizard modal on top of the plan modal.
The wizard shows live progress, operation logs, results, and presents
user choices when decisions are needed.

Three-phase flow:
1. **Scan** — SSE streaming: analyze deps, query registries, identify problems
2. **Resolve** — Client-side interactive: walk user through each problem, present alternatives
3. **Apply** — SSE streaming: apply chosen changes, run commands, stream output

---

## Wizard Triggers

The wizard opens for steps that involve multi-operation flows:

| Step Type | Trigger | Wizard Does |
|-----------|---------|-------------|
| Dep compat check (any lang) | Click 🔧 Automate | Scan → show results inline (no wizard needed, already works) |
| Update incompatible deps | Click 🔧 Automate | Scan → show incompatible → alternatives per dep → user picks → apply |
| Subprocess ops | Click 🔧 Automate | Show command → confirm → stream output → handle errors |

The wizard is only needed for **update_deps_interactive** (all languages) and
**subprocess ops** since they're multi-step with user interaction.

Simple steps (config edits, read-only scans, rescan) keep the current inline preview.

---

## Execution Steps

### Step 1: Backend wizard endpoint

**File:** `src/ui/web/routes/posture.py`

```
POST /api/posture/module-wizard-execute
Body: { module, step_id, phase: "scan"|"apply", choices?: {...} }
```

Phase "scan":
- Runs the analysis (dep scan + registry queries)
- Returns SSE stream with progress events
- Final event includes the scan results (compatible/incompatible/alternatives)

Phase "apply":
- Receives user's choices from phase 2
- Applies changes (edit files, run commands)
- Returns SSE stream with execution progress

### Step 2: Backend wizard orchestrator

**File:** `src/core/services/module_upgrade/automation/wizard.py`

Generator functions that yield SSE events:

```python
def wizard_scan_deps(ctx, language):
    """Phase 1: Scan deps and query registry."""
    yield {"type": "step_start", "step": 0, "label": "Scanning dependencies"}
    # ... scan deps
    yield {"type": "log", "step": 0, "line": f"Found {n} dependencies"}
    yield {"type": "step_done", "step": 0}

    yield {"type": "step_start", "step": 1, "label": "Querying registry"}
    # ... query each dep
    for dep in deps:
        yield {"type": "log", "step": 1, "line": f"Checking {dep}..."}
    yield {"type": "step_done", "step": 1}

    yield {"type": "done", "ok": True, "scan_result": {...}}

def wizard_apply_deps(ctx, choices):
    """Phase 3: Apply chosen changes."""
    yield {"type": "step_start", "step": 0, "label": "Applying changes"}
    # ... edit dependency files
    yield {"type": "done", "ok": True, "summary": "..."}

def wizard_run_subprocess(ctx, command, cwd):
    """Run a subprocess with streaming output."""
    yield {"type": "step_start", "step": 0, "label": f"Running {command[0]}"}
    for chunk in _run_subprocess_streaming(command, cwd=cwd):
        if "line" in chunk:
            yield {"type": "log", "step": 0, "line": chunk["line"]}
        elif "done" in chunk:
            if chunk["ok"]:
                yield {"type": "step_done", "step": 0}
            else:
                yield {"type": "step_failed", "step": 0, "error": chunk["stderr"]}
    yield {"type": "done", "ok": True}
```

### Step 3: Frontend wizard modal

**File:** `src/ui/web/templates/scripts/globals/_system_posture.html`

New functions:

`modulePlanWizard(moduleName, stepId, stepIndex)` — opens the wizard modal:
1. Opens modal with `replace: false` (stacks on plan modal)
2. Calls phase 1 (scan) via `streamSSE()`
3. Renders step progress + log area
4. When scan completes, shows results
5. If choices needed: renders choice UI (radio buttons / dropdowns per dep)
6. User makes choices, clicks "Apply"
7. Calls phase 3 (apply) via `streamSSE()`
8. On success: marks step done, closes wizard, refreshes plan modal

The wizard reuses:
- `streamSSE()` — existing generic SSE reader
- `modalOpen({replace: false})` — stacks on plan modal
- Step progress CSS from `_ops_modal.html` (`.step-row`, `.step-icon`)
- Log area from `_ops_modal.html` (`.step-log-area`)

### Step 4: CSS for wizard

**File:** `src/ui/web/static/css/admin.css`

Styles for:
- `.wizard-modal` — wizard-specific overrides
- `.wizard-step` — step progress rows in wizard
- `.wizard-log` — log output area
- `.wizard-choice` — choice/alternative selection UI
- `.wizard-choice-option` — radio/checkbox options
- `.wizard-actions` — apply/skip/cancel buttons

### Step 5: Wire wizard into plan modal

Modify `modulePlanAutomate()` to detect steps that need the wizard
(multi-step operations) vs steps that use inline preview (simple operations).

Decision logic:
- If `automation_id` starts with `run_` (subprocess ops) → open wizard
- If `automation_id` starts with `update_deps_` (interactive dep update) → open wizard
- Everything else → current inline preview

---

## Files Summary

| Action | File | Est. Lines |
|--------|------|-----------|
| EDIT | `src/ui/web/routes/posture.py` | +50 (wizard endpoint) |
| CREATE | `automation/wizard.py` | ~200 (scan/apply generators) |
| EDIT | `_system_posture.html` | +120 (wizard modal functions) |
| EDIT | `admin.css` | +50 (wizard styles) |

**Total new code:** ~420 lines
