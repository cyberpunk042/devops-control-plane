# E9 Chunk 2 — Execution Plan

> Automation engine for Python module upgrade/downgrade steps.
> Depends on: Chunk 1 complete (done).
> Status: EXECUTION PLAN — approved before coding

---

## User Experience Flow

```
User opens plan modal (moduleOpenPlan)
    ↓
Sees checklist steps (already exists)
    ↓
Each step now has:
  - checkbox (done/undone) ← existing
  - label ← existing
  - [🔧 Automate] button ← NEW (only if step has automation_id)
  - ✕ remove ← existing
    ↓
User clicks [🔧 Automate]
    ↓
POST /api/posture/module-step-execute { module, step_id, mode: "preview" }
    ↓
Backend extracts automation_id from step_id prefix
    ↓
Handler runs in preview mode → returns result
    ↓
Frontend shows result INLINE in the same plan modal:
  - Config edits: show file path + old value → new value
  - Dep checks: show table of compatible/incompatible deps
  - Code scans: show list of findings with file:line
  - Rescan: show "will re-scan and refresh posture"
    ↓
User sees preview + [✅ Apply] button (for auto steps)
OR just the results (for read-only steps like dep check / code scan)
    ↓
User clicks [✅ Apply] (if applicable)
    ↓
POST /api/posture/module-step-execute { module, step_id, mode: "execute" }
    ↓
Handler runs in execute mode → performs action
    ↓
Backend marks step done in project.yml
    ↓
Frontend refreshes: step shows as done ✓, toast notification
```

---

## Enrichment Strategy

The plan-detail endpoint must tell the frontend which steps are automatable.
Step IDs have the format `automation_id:suffix`. The frontend can split on `:`
to get the automation_id prefix and check if it's in a known set.

Two options:
A) Frontend hardcodes the list of known automation_ids
B) Backend enriches plan-detail response with automation metadata

**Decision: B — backend enrichment.** The backend already loads the recipe JSON
and has the handler registry. It adds `automatable` and `automation_id` to each
step in the response. The frontend just checks `step.automatable` to show the button.

### Plan-detail response (enriched)

```json
{
  "target": "3.12",
  "date": "Q3 2026",
  "checklist": [
    {
      "id": "edit_pyproject_requires_python:a1b2",
      "label": "Update requires-python in pyproject.toml",
      "description": "...",
      "done": false,
      "automatable": true,
      "automation_id": "edit_pyproject_requires_python",
      "risk": "low",
      "category": "config"
    },
    {
      "id": "manual:e5f6",
      "label": "Run test suite...",
      "description": "...",
      "done": false,
      "automatable": false,
      "automation_id": "",
      "risk": "low",
      "category": "test"
    }
  ]
}
```

The enrichment looks up each step's `id` prefix in the recipe JSON to find
`automatable`, `risk`, and `category`. This keeps all metadata in the recipe —
project.yml stays clean.

---

## Handler Prioritization

11 handlers in the scaffold. Not all are equal in complexity or value.
Split into tiers:

### Tier 1 — High value, straightforward (do first)
| Handler | What | Complexity |
|---------|------|-----------|
| `edit_pyproject_requires_python` | Edit requires-python in pyproject.toml | Low — existing pattern in module-fix-floor |
| `check_dep_compat_pypi` | Query PyPI for dep compatibility | Low — existing pattern in module-dep-alternatives |
| `rescan_module` | Invalidate + recompute posture | Trivial — mediator put() |
| `scan_breaking_changes` | Scan code for version features | Low — reuse compute_code_floor() |
| `scan_incompatible_features` | Same as above, downgrade direction | Low — same code path |

### Tier 2 — Medium value, moderate complexity (do second)
| Handler | What | Complexity |
|---------|------|-----------|
| `remove_future_annotations` | Remove __future__ imports (when safe) | Medium — file editing |
| `add_future_annotations` | Add __future__ imports where needed | Medium — file editing |

### Tier 3 — Lower priority, higher complexity (do last or defer)
| Handler | What | Complexity |
|---------|------|-----------|
| `edit_setup_py_python_requires` | Edit setup.py python_requires | Medium — parsing setup() call |
| `edit_setup_cfg_python_requires` | Edit setup.cfg python_requires | Low — INI-style file |
| `update_deps_interactive` | Show alternatives, user picks | High — needs multi-step UI |
| `modernize_type_hints` | Replace typing.X with builtins | High — needs AST-level editing |
| `update_ci_matrix` | Detect + edit CI config | High — many CI formats |

**Proposal:** Implement Tier 1 + Tier 2 in this chunk. Tier 3 gets `automation_id` in
recipes but handlers return a "not yet implemented" preview. This way the infrastructure
is complete and handlers can be added incrementally.

---

## Execution Steps

### Step 1: Enrich plan-detail endpoint

**File:** `src/ui/web/routes/posture.py` — plan-detail endpoint

Add recipe lookup to enrich each step with `automatable`, `automation_id`,
`risk`, `category`. Load the recipe JSON for the module's language, build a
lookup dict by automation_id.

For steps with no matching recipe entry (custom steps, legacy steps) →
`automatable: false`.

### Step 2: Create executor dispatcher

**File:** `src/core/services/module_upgrade/automation/executor.py`

Single function: `execute_step(module_name, step_id, mode, project_root) -> dict`

1. Extract `automation_id` from `step_id` prefix (split on `:`)
2. Look up handler in registry
3. Build UpgradeContext (reuse from chunk 1)
4. Call handler with (ctx, mode)
5. If mode="execute" and result.ok → mark step done in project.yml
6. Return result dict

### Step 3: Create handler registry

**File:** `src/core/services/module_upgrade/automation/__init__.py`

Dict mapping `automation_id → handler_function`. Lazy imports.

### Step 4: Create config_editor handlers

**File:** `src/core/services/module_upgrade/automation/config_editor.py`

- `handle_edit_pyproject_requires_python(ctx, mode)` — reuse pattern from module-fix-floor
  - preview: show old value → new value, file path
  - execute: write file, return result

- `handle_edit_setup_py_python_requires(ctx, mode)` — Tier 3, return "not implemented" preview
- `handle_edit_setup_cfg_python_requires(ctx, mode)` — Tier 3, return "not implemented" preview

### Step 5: Create dep_checker handler

**File:** `src/core/services/module_upgrade/automation/dep_checker.py`

- `handle_check_dep_compat_pypi(ctx, mode)` — reuse pattern from module-dep-alternatives
  - Both preview and execute do the same: scan module imports, query PyPI, return results table
  - This is a read-only operation — it doesn't modify anything
  - preview = execute (just returns compatibility data)

### Step 6: Create code_scanner handlers

**File:** `src/core/services/module_upgrade/automation/code_scanner.py`

- `handle_scan_breaking_changes(ctx, mode)` — reuse compute_code_floor()
  - Returns features found with file:line locations
  - Read-only — doesn't modify code

- `handle_scan_incompatible_features(ctx, mode)` — same as above but for downgrade
  - Scans for features that require version > target

- `handle_remove_future_annotations(ctx, mode)` — Tier 2
  - preview: list files that have __future__ annotations import
  - execute: remove the import line from those files

- `handle_add_future_annotations(ctx, mode)` — Tier 2
  - preview: list files that need __future__ annotations but don't have it
  - execute: add the import to those files

### Step 7: Create rescan handler

Lives in executor.py since it's a generic operation:
- preview: "Will re-scan module and refresh posture"
- execute: `m.put("posture.modules", cascade=True)` + force recompute

### Step 8: Add API endpoint

**File:** `src/ui/web/routes/posture.py`

```
POST /api/posture/module-step-execute
Body: { module, step_id, mode: "preview"|"execute" }
```

Calls executor.execute_step(), returns result.

### Step 9: Frontend — add automation buttons to plan modal

**File:** `src/ui/web/templates/scripts/globals/_system_posture.html`

Modify `moduleOpenPlan()` step rendering loop:
- If `step.automatable && !step.done` → show [🔧] button
- Button calls `modulePlanAutomate(moduleName, step.id, stepIndex)`

New function `modulePlanAutomate(moduleName, stepId, stepIndex)`:
- POST to /api/posture/module-step-execute with mode="preview"
- Show result inline below the step (expand a detail area)
- If result has `can_apply: true` → show [✅ Apply] button
- Apply button calls same endpoint with mode="execute"
- On success → mark step done, refresh

### Step 10: CSS for automation UI

**File:** `src/ui/web/static/css/admin.css`

- `.plan-step-auto` — automation button styling
- `.plan-step-preview` — inline preview area (expandable)
- `.plan-step-preview-diff` — old/new value display
- `.plan-step-preview-table` — dep compatibility table
- `.plan-step-preview-findings` — code scan findings list

---

## Files Summary

| Action | File | Est. |
|--------|------|------|
| EDIT | `src/ui/web/routes/posture.py` — enrich plan-detail | ~25 lines |
| EDIT | `src/ui/web/routes/posture.py` — add step-execute endpoint | ~40 lines |
| REWRITE | `module_upgrade/automation/__init__.py` — handler registry | ~50 lines |
| CREATE | `module_upgrade/automation/executor.py` — dispatcher + rescan | ~100 lines |
| CREATE | `module_upgrade/automation/config_editor.py` — pyproject editing | ~80 lines |
| CREATE | `module_upgrade/automation/dep_checker.py` — PyPI queries | ~100 lines |
| CREATE | `module_upgrade/automation/code_scanner.py` — code analysis + __future__ | ~180 lines |
| EDIT | `_system_posture.html` — plan modal automation buttons | ~80 lines |
| EDIT | `admin.css` — automation UI styles | ~40 lines |

**Total new code:** ~510 lines backend + ~120 lines frontend
**Total edits:** ~65 lines in existing files

---

## Not-Yet-Implemented Handlers

These get entries in the registry that return a standard "not yet available" response:

- `edit_setup_py_python_requires`
- `edit_setup_cfg_python_requires`
- `update_deps_interactive`
- `modernize_type_hints`
- `update_ci_matrix`

The frontend shows these as automatable but the preview says "This automation
is not yet available. Complete this step manually."

This means every automation_id in the recipe has a handler — no missing entries,
no frontend errors. Just some handlers aren't fully implemented yet.

---

## Verification

After implementation:
1. Open plan modal for a Python module with a plan
2. Steps with automation_id show [🔧] button
3. Click [🔧] on "Update requires-python" → shows preview (old → new value)
4. Click [✅ Apply] → file is modified, step marked done
5. Click [🔧] on "Check dep compatibility" → shows dep table
6. Click [🔧] on "Scan breaking changes" → shows code feature findings
7. Click [🔧] on "Rescan module" → rescans and refreshes
8. Steps already done don't show [🔧] button
9. Custom steps (custom:xxx) don't show [🔧] button
10. Not-yet-implemented handlers show friendly "not available" message
