# Auto-Check Investigation: Steps Marked Done Without User Approval

**Date**: 2026-03-20
**Bug**: Version plan batch steps are auto-checked (marked done) without user clicking approve/apply.

---

## Summary of All Locations That Mark Steps Done

### SERVER-SIDE (writes `done: true` to project.yml)

#### Location 1: `executor.py` line 142-144 — `execute_step()` post-handler mark-done
- **File**: `src/core/services/module_upgrade/automation/executor.py:142-144`
- **Code**: `if mode == "execute" and result.get("ok"): if should_mark_done(result): _mark_step_done(...)`
- **Conditions**: Mode is "execute", result is ok, `should_mark_done()` returns True
- **Can fire without user action?** YES — in batch mode, `wizard_batch()` does NOT call `execute_step()`. But for single-step calls via `/api/posture/module-step-execute`, this fires after the user clicks "Apply" in the modal. **Not the batch culprit.**

#### Location 2: `wizard.py` line 525-526 — `wizard_batch()` inline mark-done
- **File**: `src/core/services/module_upgrade/automation/wizard.py:525-526`
- **Code**: `if ok and should_mark_done(result): _mark_step_done(ctx.module_name, step_id, ...)`
- **Conditions**: Handler returned `ok=True` AND `should_mark_done(result)` returns True
- **Can fire without user action?** **YES — THIS IS THE PRIMARY CULPRIT.**
  - In batch mode, the wizard calls handlers directly (line 364: `result = handler(ctx, mode)`)
  - For non-fix steps, mode is always `"execute"` (line 353)
  - Scan steps, toml generation, test scaffolding — all return `ok: True` with no findings
  - `should_mark_done()` returns True for these results
  - Result: step is marked done in project.yml **without any user preview/approval**

#### Location 3: `executor.py` line 117-120 — `_check_already_done()` skip path
- **File**: `src/core/services/module_upgrade/automation/executor.py:117-120`
- **Code**: `skip = _check_already_done(automation_id, ctx); if skip: return skip`
- **Conditions**: Artifact already exists (pyproject.toml, test files, venv)
- **Returns**: `{"ok": True, "summary": "...skipped"}` — NO findings, NO `can_apply` field
- **Can fire without user action?** YES, but only via `execute_step()`, not directly in `wizard_batch()`.
- **Note**: `wizard_batch()` does NOT call `execute_step()` — it calls handlers directly. So `_check_already_done()` is NOT invoked during batch runs. However, if a single step is executed via the API, the skip result flows into `should_mark_done()` which returns True (ok=True, no findings), and `_mark_step_done()` fires at line 144.

#### Location 4: `_mark_step_done()` — the actual writer
- **File**: `src/core/services/module_upgrade/automation/executor.py:632-679`
- **Writes**: `step["done"] = True` in project.yml, also updates step label if summary provided
- **Side effect**: Calls `mediator.put("posture.modules", cascade=True)` which triggers posture refresh

---

### CLIENT-SIDE (DOM manipulation: classList.add('done'), cb.checked = true)

#### Location 5: `onStepDone` handler in batch SSE stream — lines 2636-2657
- **File**: `src/ui/web/templates/scripts/globals/_system_posture.html:2636-2657`
- **Code**:
  ```js
  onStepDone: function(event) {
      // ...
      if (isBatch && stepIndices) {
          const planIdx = stepIndices[event.step];
          if (planIdx !== undefined) {
              planSteps[planIdx].classList.add('done');
              cb.checked = true;
          }
      }
  }
  ```
- **Conditions**: `isBatch` is true AND `stepIndices` array maps the wizard step index to a plan step index
- **Can fire without user action?** **YES — THIS IS THE FRONTEND CULPRIT.**
  - The `onStepDone` handler fires for EVERY `step_done` SSE event from the batch
  - It does NOT check `event.needs_attention` — it marks the DOM done regardless
  - Even fix steps in preview mode (line 380-381 of wizard.py) emit `step_done` with `needs_attention: true`, but the frontend ignores this flag and checks the box anyway

#### Location 6: `_wizardMarkDone()` — lines 3296-3316
- **File**: `src/ui/web/templates/scripts/globals/_system_posture.html:3296-3316`
- **Server**: YES (PATCHes `/api/posture/module-plan-progress`)
- **DOM**: YES (classList.add('done'), cb.checked = true)
- **Called from**:
  - Line 2065: After preview returns nothing to do (`!data.can_apply && !data.findings && !data.by_feature`) — **auto-fires when preview shows "nothing to do"**
  - Line 2279: After `_modalApplyStep` succeeds — user clicked "Apply", this is correct
  - Line 2738: After dep scan shows all compatible — **auto-fires without user confirm**
  - Line 2746: After subprocess completes with a summary — **auto-fires without user confirm**

#### Location 7: `_markStepDoneByIndex()` — lines 2962-2981
- **File**: `src/ui/web/templates/scripts/globals/_system_posture.html:2962-2981`
- **Server**: YES (PATCHes `/api/posture/module-plan-progress`)
- **DOM**: YES (classList.add('done'), cb.checked = true)
- **Called from**:
  - Line 2943: `_wizardMarkRemDone()` — marks failed step done when user clicks remediation option
  - Line 2954: `_wizardMarkRemDone()` — also marks next `update_deps_*` step done automatically
  - Line 3266: `wizardAddFuture()` — marks future annotations step done after apply

#### Location 8: `_wizardMarkDone_close()` — line 2361-2363
- **File**: `src/ui/web/templates/scripts/globals/_system_posture.html:2361-2363`
- **Code**: Calls `_wizardMarkDone()` then `modalClose()`
- **Called from**:
  - Line 2227: "Mark as reviewed" button on compat_scan modal — user-initiated
  - Line 2339: "Mark as done" button on failed step modal — user-initiated

---

## Critical Finding: The Batch Auto-Check Flow

### Server-side path (wizard_batch):

1. User clicks "Run N automatable steps"
2. `modulePlanRunBatch()` collects undone steps, calls `/api/posture/module-wizard` with `wizard_type: "batch"`
3. Route handler calls `wizard_batch()` (wizard.py:307)
4. For each step:
   - Fix steps with `auto_fix=False`: mode is set to `"preview"` (line 354) — emits `step_done` with `needs_attention: true` (line 380-381) — **but `_mark_step_done` is NOT called** (correct)
   - All other steps: mode is `"execute"` (line 353) — handler runs, then:
     - Line 525: `if ok and should_mark_done(result)` — **marks done in project.yml**
     - Line 527: Emits `step_done` SSE event

### Frontend path (onStepDone):

5. For every `step_done` event in batch mode (line 2636-2657):
   - `planSteps[planIdx].classList.add('done')` — checks the box in DOM
   - `cb.checked = true` — visually marks as done
   - **Does NOT check `event.needs_attention`** — marks ALL steps done regardless

### Result:
- Non-fix steps (scans, toml gen, test scaffold, etc.) are marked done in BOTH project.yml AND DOM without user seeing any preview or approval modal
- Fix steps with auto_fix OFF are marked done in DOM (checkbox) even though they were only previewed — though NOT in project.yml (correct server-side, wrong client-side)

---

## `should_mark_done()` Analysis for Fix Steps with auto_fix OFF

**File**: `src/core/services/module_upgrade/automation/executor.py:17-50`

In `wizard_batch()`, fix steps with `auto_fix=False` get `mode="preview"` (line 354). The handler returns a preview result. The `should_mark_done()` check at line 525 IS reached for fix steps in preview mode.

However, there is a guard at line 376:
```python
if is_fix_step and not auto_fix and ok:
    yield {"type": "step_done", ...needs_attention: True}
    completed += 1
    continue  # <-- skips to next step, bypassing should_mark_done at line 525
```

So fix steps with auto_fix OFF do NOT reach `should_mark_done()` — the `continue` at line 383 skips the mark-done block. **Server-side is correct for fix steps.**

But the frontend `onStepDone` handler at line 2636 does NOT check `needs_attention`, so the DOM checkbox gets checked anyway.

---

## `_check_already_done()` — Which Steps It Auto-Skips

**File**: `src/core/services/module_upgrade/automation/executor.py:582-615`

| automation_id | Artifact checked | Skip condition |
|---|---|---|
| `generate_module_toml` | `module_dir/pyproject.toml` | File exists |
| `scaffold_module_tests` | `module_dir/tests/test_smoke.py` | File exists |
| `scaffold_parent_tests` | `project_root/tests/test_{mod}_integration.py` | File exists |
| `generate_smart_tests` | `module_dir/tests/test_compatibility.py` | File exists |
| `setup_test_env` | `.venvs/{module}-{target}/bin/python` | File exists AND requirements.txt not newer |

All skip results return `{"ok": True, "summary": "...skipped"}` — no findings, no `can_apply` field.

**Important**: `_check_already_done()` is only called from `execute_step()` (line 118), NOT from `wizard_batch()`. The batch wizard calls handlers directly. So `_check_already_done()` does NOT contribute to the batch auto-check bug.

---

## Root Causes

### Root Cause 1 — Server-side: `wizard_batch()` marks non-fix steps done without user preview
- **Location**: `src/core/services/module_upgrade/automation/wizard.py:525-526`
- Non-fix steps run in `mode="execute"` directly, and if `should_mark_done()` returns True, `_mark_step_done()` writes `done: true` to project.yml
- The user never sees a preview modal for these steps in batch mode

### Root Cause 2 — Client-side: `onStepDone` handler ignores `needs_attention` flag
- **Location**: `src/ui/web/templates/scripts/globals/_system_posture.html:2644-2657`
- Every `step_done` event in batch mode marks the DOM checkbox as done
- Even steps with `needs_attention: true` get their checkbox checked
- This gives the visual impression that fix steps (preview-only) are also done

### Root Cause 3 — Client-side: Several auto-mark paths fire without explicit user confirmation
- Line 2065: `_wizardMarkDone` called when preview returns "nothing to do" (reasonable but no user action)
- Line 2738: `_wizardMarkDone` called when dep scan says "all compatible" (auto-fires)
- Line 2746: `_wizardMarkDone` called when subprocess completes successfully (auto-fires)
