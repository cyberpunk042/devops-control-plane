# Compat V2 Systematic Audit

Generated: 2026-03-20

End-to-end trace of every flow in the version plan + compat-v2 system.

---

## 1. Step Generation

**File:** `src/core/services/module_upgrade/generator.py`

### Flow

1. `generate_checklist()` (line 57) builds an `UpgradeContext`, loads the language recipe JSON, filters steps by conditions, appends common tail steps (deduplicated), then calls `_enrich_with_compat_analysis()`.
2. `_enrich_with_compat_analysis()` (line 199) fetches cached analysis from mediator (`compat.analysis.{module_name}`). If no analysis or no findings, it strips `_COMPAT_REPLACED_AUTOMATIONS` steps and returns.
3. When findings exist, it separates infra steps from compat-replaced steps (line 244), then calls `_generate_compat_steps()` (line 263).
4. After compat steps are generated, infra steps are reordered into groups (line 267-302).

### `_generate_compat_steps()` (line 310) produces this order:
1. **Scan step** (always) -- `scan_incompatible_features`
2. **Blocked step** (if transitive findings) -- `blocked`
3. **Fix steps** (one per feature, each with `fix_compat_auto__{hash}`) -- auto-fixable only
4. **Manual review step** (if manual findings) -- `guide_incompatible_syntax`
5. **Re-scan/verify step** (if any actionable findings) -- `rescan_module`

### Reordering in `_enrich_with_compat_analysis()` (line 266-302):
Infra steps are bucketed into: deps, config, venv, test, ci, other.

**Final merged order:**
```
compat_steps (scan -> blocked -> fix -> manual -> rescan)
+ deps_steps
+ config_steps
+ venv_steps (setup_test_env first, then run_pip_install)
+ test_steps (scaffold_*, generate_smart_*, run_isolated_tests)
+ ci_steps (update_ci_matrix)
+ other_steps
```

### What's broken / issues:

**ISSUE 1 (line 293-302): Rescan is generated TWICE.**
`_generate_compat_steps()` appends a `rescan_module` step at line 419-423. But the recipe also has `rescan_module` as its last step. The `_COMPAT_REPLACED_AUTOMATIONS` set (line 190) includes `"rescan_module"` so the recipe's rescan IS stripped. This is correct -- no duplication.

**ISSUE 2 (line 251-258): No-op config step filtering calls `build_context` again.**
When checking if `current_floor == target` to skip no-op config edits, it calls `build_context()` a second time (line 253). This is wasteful but not broken.

**ISSUE 3 (line 385-386): Feature hash uses MD5 for step ID encoding.**
The `_hl.md5(feature_name.encode()).hexdigest()[:8]` at line 386 is an inline import inside a loop. Works but is ugly.

**ISSUE 4 (line 283): `venv_steps.insert(0, step)` for setup_test_env.**
If `setup_test_env` appears multiple times (it won't given the recipe), `insert(0)` would reverse order. Not a real bug since it only appears once.

**ISSUE 5 (line 284-285): `run_pip_install` classified as venv step.**
`run_pip_install` goes into `venv_steps` (line 284), but `run_npm_install` also matches here. These install steps run AFTER venv setup, which is correct ordering. However, `run_pip_install` in the recipe is under "deps" category, not "test". The bucketing here uses `_automation_id` not `category`, so the recipe's category is ignored. This is fine for ordering but potentially confusing.

**ISSUE 6: `_generate_compat_steps` generates its own rescan step, but this rescan lacks the `automatable: True` flag being set explicitly.** Looking at line 418-423, it does set `"automatable": True` -- this is correct.

---

## 2. Batch Wizard Flow

**File:** `src/core/services/module_upgrade/automation/wizard.py`, `wizard_batch()` at line 307.

### Flow
1. Sets `ctx.auto_fix = auto_fix` (line 332).
2. Iterates through `step_ids` + `step_labels` (line 334).
3. For each step:
   - Extracts `automation_id` from step_id (`step_id.split(":")[0]`).
   - Strips feature hash: `handler_id = automation_id.split("__")[0]` (line 341).
   - Looks up handler from registry (line 342-343).
   - Determines mode: fix steps use `"preview"` when `auto_fix=False`, `"execute"` otherwise (line 349-355).
   - Sets `ctx._feature_hash` for per-feature filtering (line 358-361).
   - Calls `handler(ctx, mode)` (line 364).

### auto_fix ON vs OFF behavior per step type:

| Step Type | auto_fix=ON | auto_fix=OFF |
|-----------|-------------|--------------|
| `fix_compat_auto*` | mode="execute", applies fixes | mode="preview", shows preview, yields `needs_attention` |
| `add_future_annotations` | mode="execute", applies fixes | mode="preview", shows preview, yields `needs_attention` |
| `scan_*` | mode="execute", read-only scan | Same (scan is always read-only) |
| `rescan_module` | mode="execute", busts cache+rescans | Same |
| `setup_test_env` | mode="execute", creates venv | Same |
| `run_pip_install` | mode="execute" (subprocess handler) | Same |
| `run_isolated_tests` | mode="execute", runs pytest | Same |
| `check_dep_compat_*` | mode="execute", queries registry | Same |
| `guide_incompatible_syntax` | mode="execute", read-only guide | Same |

### What's broken / issues:

**ISSUE 7 (line 349-355): Only `fix_compat_auto` and `add_future_annotations` are gated by auto_fix.**
The `_FIX_PREFIXES` tuple is `("fix_compat_auto", "add_future_annotations")`. But `guide_incompatible_syntax` is NOT a fix prefix, even though the "Mark reviewed" action in the frontend routes through `_modalApplyStep` which calls execute mode. This means guide steps always run in execute mode regardless of auto_fix toggle. Not a bug per se since the guide handler is read-only.

**ISSUE 8 (line 517): `should_mark_done()` is called from wizard but with the result from the handler.**
For fix steps in preview mode (auto_fix=OFF), the step is marked `needs_attention` (line 381) and `completed` is incremented. But the step is NOT marked done in project.yml. On the next batch run, it would re-run. This is intentional behavior (preview = don't mark done).

**ISSUE 9 (line 543-545): Compat hints extraction uses `result` variable from the loop.**
When a test step fails, `compat_hints = result.get("compat_hints", []) if result else []` reads from the last handler result (line 545). But `result` could be from a handler exception (line 365-369), in which case the `break` at line 370 means `result` is never set for that iteration -- it would be the result from the PREVIOUS iteration, or undefined. Actually, looking more carefully: when the handler raises an exception (line 365), the code breaks immediately (line 370), so `result` is whatever was assigned before the try block -- which is NOT the current step's result. The `result` variable is only assigned at line 364. If the handler raises, the `except` block breaks without setting `result`.

**Wait -- re-reading:** The `except` block at line 366-370 does `break`, and then at line 545, `result` would be the last _successfully_ assigned result from a previous step (or unbound if this is the first step). However, the `if result else []` guard would catch `None` but not an unbound variable. If the first step raises an exception, `result` is unbound, and line 545 would raise `UnboundLocalError`.

**ACTUAL BUG: If the first step in a batch raises an exception, `result` is unbound, and the post-loop remediation code at line 545 would crash with `UnboundLocalError`.** However, the specific code path requires `is_test=True` for the failed step, and test steps (`run_*`) are typically not the first step. So this is a latent bug, unlikely to trigger in practice.

**ISSUE 10 (line 505-512): Error handling for `result.get("error")` happens AFTER the dep remediation block.**
After yielding the done event with remediation (line 503 returns), the code at line 505 checks `result.get("error")`. If the code reaches here, it means `incompat == 0` or `is_dep_check` is False. The flow is:
- Dep check with incompatible deps -> returns at line 503 (correct)
- Non-dep step with error -> falls through to line 505 (correct)
This is fine.

---

## 3. Fix Handler

**File:** `src/core/services/module_upgrade/automation/code_scanner.py`, `handle_fix_compat_auto()` at line 57.

### Flow
1. Fetches cached analysis from mediator: `m.get(f"compat.analysis.{ctx.module_name}")` (line 69).
2. Filters to auto-fixable, actionable, non-transitive findings (line 75-81).
3. If `ctx._feature_hash` is set, further filters to just that feature (line 87-90).
4. Builds preview data with before/after from compat database entries (line 103-131).

### Preview mode (line 133):
Returns `ok=True, can_apply=True, preview_type="compat_fix_preview"` with `by_feature` list showing counts, files, before/after examples.

### Execute mode (line 145):
1. Gets `module_dir` from context.
2. Calls `compat.fix.fix_module()` with findings, verify=True (line 147-153).
3. Returns fixed/failed counts and files_fixed.

### What's broken / issues:

**ISSUE 11 (CRITICAL): Execute mode does NOT bust the analysis cache after applying fixes.**
After `fix_module()` modifies source files (line 147-153), the cached analysis at `compat.analysis.{module_name}` still contains the OLD findings. Any subsequent step that reads the analysis (e.g., rescan, another fix step) will see stale data.

The `handle_rescan_module()` handler (executor.py line 177) does `m.bust_path(f"compat.analysis.{ctx.module_name}", cascade=True)` followed by `m.dispatch(...)`. But if the user clicks individual "Fix" steps without running rescan between them, the second fix step will try to fix findings that were already fixed -- potentially causing double-fixes or errors.

**Mitigation:** The fix engine's `fix_module()` presumably reads from disk and verifies, so double-fixing might be a no-op. But the UI would still show stale finding counts.

**ISSUE 12 (line 69-72): Analysis fetch uses `m.get()` not `m.peek()`.**
`m.get()` may trigger computation if the key doesn't exist. If the compat system isn't initialized, this could block or error. Line 71 checks `if result is None` but doesn't handle the case where `analysis_data` itself is None. If `m.get()` returns None, line 70 `analysis_data["data"]` would raise `TypeError: 'NoneType' object is not subscriptable`.

**Actually:** Line 69-70 does `analysis_data = m.get(...)` then line 70 `result = analysis_data["data"]`. If `m.get()` returns None, this crashes. The `try/except` at line 170 catches it, so it returns `{"ok": False, "error": "Auto-fix failed: ..."}`. Not catastrophic but the error message is opaque.

**ISSUE 13 (line 103): Orchestrator fetch also uses `m.get()` not `m.peek()`.**
Same pattern: `compat = _m.get("compat.orchestrator")["data"]`. Would crash if orchestrator not loaded, caught by outer try/except.

---

## 4. Test Handler

**File:** `src/core/services/module_upgrade/automation/test_env.py`

### `handle_run_isolated_tests()` (line 236)

**Preview mode** (line 248): Checks if venv exists and tests directory exists. Returns `can_apply=False` with helpful messages if missing.

**Execute mode** (line 279):
1. Runs `pytest` via subprocess with the venv python (line 286-289).
2. Parses pytest output for passed/failed/errors/skipped counts using regex (line 297-310).
3. If tests fail (`ok=False`), calls `_detect_compat_failures(output, target)` (line 335).
4. Returns result with optional `compat_hints` list.

### `_detect_compat_failures()` (line 359)

Scans test output against 4 error patterns:

| Pattern | Type | What it detects |
|---------|------|-----------------|
| `cannot import name 'X' from 'Y'` | import_error | Missing imports |
| `No module named 'X'` | module_error | Missing modules (pip vs stdlib) |
| `'X' object has no attribute 'Y'` | attribute_error | Missing attributes |
| `unsupported operand type.*for \|.*'dict'` | operator_error | Dict merge `\|` (3.9+) |

For each match, it:
1. Creates a hint dict with `feature`, `since`, `fix`.
2. Tries to enrich from compat database via `compat.registry.search()` (line 423-434).
3. If enriched, sets `hint["fix_available"]` based on fix strategy.

### What's broken / issues:

**ISSUE 14: `_detect_compat_failures` hints have no `auto_fixable` field by default.**
The hint dict structure varies:
- Non-enriched hints have: `feature`, `since`, `fix` -- NO `auto_fixable` field.
- Enriched hints have: `feature`, `since`, `fix`, `fix_available` -- still NO `auto_fixable` field.

But the wizard.py remediation code at line 549 checks `hint.get("auto_fixable")`. Since `auto_fixable` is never set in any hint, this check always fails. The remediation options will never include the "Fix: search -> replace" option.

**This means the "Fix all detected issues" button in the test failure remediation UI creates compat fix options but they never have `auto_fixable=True`, so the `_renderRemediation` path that shows `search/replace` hints is never reached.** The hints still show as informational items, but the auto-fix path from test failures is dead code.

**ISSUE 15: `_detect_compat_failures` hints lack `search` and `replace` fields.**
The wizard.py code at line 553-556 references `hint['search']` and `hint['replace']`, but `_detect_compat_failures` never sets these fields. If `auto_fixable` were somehow True, accessing `hint['search']` would raise `KeyError`.

**ISSUE 16: The 4 error patterns are very limited.**
Only 4 patterns are checked. Common compat failures like `SyntaxError` (e.g., walrus operator, match/case, f-string `=` syntax) are not detected. The function returns an empty list for most actual compat failures.

**ISSUE 17 (line 316): Exit code 5 treated as success.**
`ok = result.returncode == 0 or result.returncode == 5` -- exit code 5 means "no tests collected", which is treated as success. This means if the venv setup failed and pytest can't find any tests, the step passes silently.

---

## 5. Rescan Handler

**File:** `src/core/services/module_upgrade/automation/executor.py`, `handle_rescan_module()` at line 150.

### Preview mode (line 156): Returns description of what will happen.

### Execute mode (line 169):
1. **Busts** compat analysis cache: `m.bust_path(f"compat.analysis.{ctx.module_name}", cascade=True)` (line 177).
2. **Dispatches** fresh analysis: `m.dispatch(f"compat.analysis.{ctx.module_name}")` (line 178).
3. **Invalidates** posture modules: `m.put("posture.modules", cascade=True)` (line 183).
4. **Reads** fresh analysis to count remaining findings (line 187-194).
5. Returns "Clean" or "N finding(s) remain" summary.

### What's broken / issues:

**ISSUE 18 (line 176-180): Cache bust is in a try/except that passes silently.**
If `m.bust_path()` or `m.dispatch()` raises, it's silently swallowed (`pass`). The handler then reads `m.get()` which may return the OLD cached analysis (since the bust failed). The result would claim "clean" or show old findings count.

**ISSUE 19 (line 183): `m.put("posture.modules", cascade=True)` called with no data.**
The `m.put()` call doesn't pass any data value. This may or may not invalidate correctly depending on the mediator's `put()` semantics. If `put()` without data means "invalidate", this is fine. If it means "set to None", downstream consumers may break.

**ISSUE 20: Rescan re-analyzes from scratch (via bust + dispatch).**
This is the CORRECT behavior -- it does NOT read cache. The bust ensures the old analysis is removed, and dispatch triggers fresh computation. Good.

**ISSUE 21 (line 187-194): Fresh analysis read may return stale data.**
The `m.dispatch()` at line 178 may be asynchronous. If the analysis computation hasn't completed when `m.get()` is called at line 188, the get may either block (good) or return the old/empty data (bad). Depends on mediator semantics.

---

## 6. Frontend Modal Flow

**File:** `src/ui/web/templates/scripts/globals/_system_posture.html`

### Entry point: `modulePlanAutomate()` (line 2019)

Routes by automation_id prefix:
- `scaffold_*`, `generate_module_toml` -> dedicated modal functions
- `run_*` (except `run_isolated_tests`, `setup_test_env`) -> `_openStepModal()` with SSE streaming
- `run_isolated_tests` -> `_modalApplyStep()` directly (no preview)
- `check_dep_compat_*`, `update_deps_*` -> `_openStepModal()` with dep_scan SSE
- Everything else -> fetch preview, show in modal

### Modal Stack:

**Preview flow (non-streaming steps):**
1. `modulePlanAutomate()` fetches `/api/posture/module-step-execute` with `mode: 'preview'`.
2. If `can_apply` or has findings, opens modal with `replace: false` (stacks on top).
3. Modal shows preview. Footer buttons include "Apply" or "Fix All Auto-fixable".
4. User clicks Apply -> `_modalApplyStep()` fires.

**`_modalApplyStep()` (line 2251):**
1. Shows loading state on buttons.
2. POSTs to `/api/posture/module-step-execute` with `mode: 'execute'`.
3. On success (`data.ok`): toast + `modalClose()` x2 (closes fix modal + preview modal).
4. On failure: opens NEW modal with `replace: true` (replaces current modal in place).
   - Shows error/output.
   - If `data.compat_hints` exist: renders hints + "Fix all detected issues" button.
   - Adds "Mark as done" + "Close" buttons.

**Batch flow:**
1. `modulePlanRunBatch()` (line 2344) collects uncompleted steps, opens `_openStepModal()` with `wizardType: 'batch'`.
2. SSE streams step progress.
3. On batch done with remediation: calls `_renderRemediation()`.

### `_renderRemediation()` (line 2733):
- If `compat_hints`: shows hints + "Fix all detected issues" button that calls `modulePlanAutomate()` with `fix_compat_auto:from_wizard` step ID.
- If `packages`: shows incompatible packages with alternatives.
- Fallback: generic "Step failed" message.

### What's broken / issues:

**ISSUE 22 (line 2272-2273): Double `modalClose()` on success.**
On success, `_modalApplyStep()` calls `modalClose()` twice. The comment says "Close fix preview modal + wizard modal underneath." This assumes there are always exactly 2 modals stacked. But:
- If called from a direct "Automate" button click (not from within a wizard), there's only 1 modal (the preview). The second `modalClose()` would close whatever is behind it (possibly the module detail panel or nothing).
- If called from within a batch wizard remediation, there could be a different stack depth.

**ISSUE 23 (line 2309-2311): "Fix all detected issues" button creates invalid step ID.**
The button calls `_modalApplyStep('${moduleName}','fix_compat_auto:from_test',${stepIndex})`. The step ID `fix_compat_auto:from_test` is synthetic -- it doesn't match any step in the plan's checklist. When `_modalApplyStep` succeeds, it tries to mark plan step done at `stepIndex` in the DOM (line 2275-2282), which would mark the WRONG step (the test step, not a fix step).

**ISSUE 24 (line 2751): Similar issue for wizard remediation.**
`modulePlanAutomate('${moduleName}','fix_compat_auto:from_wizard',-1)` uses step index `-1`. At line 2276, `planSteps[-1]` in JavaScript returns `undefined` (arrays don't support negative indexing), so the DOM update is silently skipped. This is a lesser issue since the fix would update via `_refreshPlanState()` eventually.

**ISSUE 25 (line 2224-2225): "Fix All Auto-fixable" button constructs step ID from scan step.**
When showing a compat scan preview, the "Fix All" button uses `'fix_compat_auto:' + stepId.split(':')[1]`. This creates a step ID like `fix_compat_auto:a1b2c3d4` where the suffix comes from the SCAN step. The executor at `executor.py` line 76-77 extracts `automation_id = step_id.split(":")[0]` which gives `"fix_compat_auto"` -- correct. But there's no `__` in this ID, so `_feature_hash` is None, meaning ALL features get fixed, not just the ones from the scan. This is likely intentional ("Fix ALL auto-fixable").

**ISSUE 26 (line 2063-2067): Empty preview auto-marks step done.**
If the preview returns `ok=True` but `can_apply=False` and no findings, the step is auto-marked done via `_wizardMarkDone()`. This happens without the user explicitly confirming. For informational steps (e.g., "No __future__ annotations imports found"), this is reasonable. But for scan steps that return "No actionable incompatibilities" -- this might mark the scan step done even if it should be re-evaluated later.

---

## 7. Step Ordering

### ACTUAL order for Python downgrade with findings (most common compat-v2 scenario):

From `_generate_compat_steps()` + `_enrich_with_compat_analysis()` reordering:

```
 1. Scan -- N finding(s) in M file(s)              [scan_incompatible_features]
 2. Blocked by: X (if transitive)                   [blocked]
 3. Fix feature_A (K file(s))                       [fix_compat_auto__hash1]
 4. Fix feature_B (J file(s))                       [fix_compat_auto__hash2]
 5. Review N manual finding(s)                      [guide_incompatible_syntax]
 6. Re-scan and verify                              [rescan_module]
 7. Check all deps support Python target            [check_dep_compat_pypi]  (deps bucket)
 8. Install pinned dependency versions              [run_pip_install]  (venv bucket -- NOT deps!)
 9. Update requires-python in pyproject.toml        [edit_pyproject_requires_python]  (config bucket)
10. Generate module pyproject.toml                  [generate_module_toml]  (config bucket)
11. Set up test environment                         [setup_test_env]  (venv bucket)
12. Scaffold module test structure                  [scaffold_module_tests]  (test bucket)
13. Generate compatibility tests                    [generate_smart_tests]  (test bucket)
14. Add integration tests                           [scaffold_parent_tests]  (test bucket)
15. Run isolated tests                              [run_isolated_tests]  (test bucket)
16. Update CI pipeline                              [update_ci_matrix]  (ci bucket)
```

### Ordering problems:

**ISSUE 27 (CRITICAL): `run_pip_install` is in the venv bucket, placed AFTER config steps but BEFORE setup_test_env.**
Looking at the bucketing code (generator.py line 284): `run_pip_install` matches `aid == "run_pip_install"` and goes into `venv_steps.append(step)`. `setup_test_env` matches `aid == "setup_test_env"` and goes into `venv_steps.insert(0, step)`. So within `venv_steps`, the order is: `[setup_test_env, run_pip_install]`. Setup IS before install. This is correct.

But wait -- the recipe order matters for the INITIAL insertion. In the recipe, `run_pip_install` (line 101-109 of python.json) comes BEFORE `setup_test_env` (line 201-210). When iterating infra_steps, `run_pip_install` gets appended first, then `setup_test_env` gets inserted at position 0. So `venv_steps = [setup_test_env, run_pip_install]`. Correct.

**ISSUE 28: Config edit happens AFTER rescan.**
The rescan step (from compat_steps) is at position 6, but config edits (edit_pyproject_requires_python) are at position 9. This means the rescan runs before the config file is updated. The rescan will report the old floor. This is wrong -- you'd want to edit the config first, THEN rescan to verify.

However, the compat rescan step specifically checks for CODE incompatibilities, not config floor. The recipe's own `rescan_module` (which was stripped by compat enrichment) was at the END of the recipe. The compat engine adds its own rescan after the fix steps, which makes sense as "verify code fixes worked." The config edit is a separate concern. But the user sees one plan with rescan in the middle, which is confusing.

**ISSUE 29: `run_pip_install` is in the venv bucket but semantically belongs after `check_dep_compat_pypi`.**
The recipe puts `run_pip_install` right after the dep-related steps. But the bucketing moves it to the venv group, which comes after config. In the final order: deps (step 7) -> config (steps 9-10) -> venv [setup_test_env, run_pip_install] (steps 11, then 8). Wait, let me re-trace:

The `venv_steps` list contains: `[setup_test_env, run_pip_install]`. In the final concat:
```
compat_steps + deps_steps + config_steps + venv_steps + test_steps + ci_steps + other_steps
```
So the actual position is:
```
... deps ... config ... [setup_test_env, run_pip_install] ... tests ... ci
```

This means `run_pip_install` runs AFTER `setup_test_env`. But `run_pip_install` from the recipe runs `pip install -r requirements.txt` using the SYSTEM pip (per SUBPROCESS_COMMANDS at wizard.py line 303). It does NOT use the venv pip. So installing into the venv requires the separate `handle_setup_test_env()` which does its own pip install.

**ISSUE 30: Two separate pip install paths.**
- Recipe's `run_pip_install` (subprocess handler) runs `pip install -r requirements.txt` using system pip.
- `handle_setup_test_env()` (test_env.py line 188-200) also installs from requirements.txt using the venv pip.

The user sees both steps in the plan but they serve different purposes. This is not broken but is confusing -- the recipe step installs globally, the venv step installs in isolation.

---

## Summary of Critical Issues

| # | Severity | Location | Description |
|---|----------|----------|-------------|
| 11 | **CRITICAL** | code_scanner.py:147-168 | Fix handler does NOT bust analysis cache after executing. Subsequent fix/scan steps see stale findings. |
| 14 | **HIGH** | test_env.py:359+ / wizard.py:549 | `auto_fixable` field never set in compat hints. Test failure -> fix flow is dead code. |
| 15 | **HIGH** | wizard.py:553-556 | `hint['search']` and `hint['replace']` referenced but never populated. Would crash if reached. |
| 22 | **MEDIUM** | _system_posture.html:2272 | Double `modalClose()` assumes 2-deep modal stack. Can close wrong modal if stack is different. |
| 23 | **MEDIUM** | _system_posture.html:2309 | Synthetic step ID `fix_compat_auto:from_test` marks test step done instead of fix step. |
| 28 | **MEDIUM** | generator.py:293-302 | Compat rescan step placed before config edits. Rescan verifies code fixes but user sees it mid-plan. |
| 16 | **LOW** | test_env.py:351-356 | Only 4 error patterns checked. Most real compat failures (SyntaxError, match/case) not detected. |
| 17 | **LOW** | test_env.py:316 | pytest exit code 5 (no tests collected) treated as success. |
| 18 | **LOW** | executor.py:176-180 | Cache bust silently swallowed on error. May read stale data. |
| 9 | **LOW** | wizard.py:545 | `result` potentially unbound if first step raises exception. |
