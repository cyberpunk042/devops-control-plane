# Compat V2 Full Integration — Multi-Milestone Plan

> Every compat v2 capability must be integrated, surfaced, observable, and operable.
> The system was built. Now it needs to work end-to-end through the actual UX.
>
> Reference: `.agent/docs/compat-v2-integration-gaps.md` — full gap audit

---

## Current State

The plumbing is done (M1-M9): registry in mediator, detection engine optimized,
analysis cached, handlers wired, startup fast. But the USER EXPERIENCE is broken:

- Plan creation uses static recipes, not analysis-driven steps
- Scan step dumps 4963 unfiltered findings with zero actions
- No fix buttons in step results
- No severity filtering
- No grouping
- Step state is boolean (done/not done), not PENDING/RUNNING/PASSED/FAILED/NEEDS_ATTENTION/BLOCKED
- No transitive analysis surfaced
- No assessment before plan creation
- No verification loop in step execution

---

## Milestone 10: Analysis-Driven Plan Generation

**Goal**: When user creates a plan, the compat engine analyzes the module first and
generates steps tailored to what it actually found.

### What changes

`posture_module_plan()` in posture.py currently calls `generate_checklist()` (static recipes).
After M10, it calls `PlanEngine.generate_plan()` which:

1. Runs compat analysis on the module (from mediator cache if available)
2. Generates steps FROM the findings:
   - "Fix datetime.UTC (14 files)" instead of generic "Scan for incompatible features"
   - Skips "Add __future__" if no annotation findings
   - Groups auto-fixes by strategy
   - Shows "Blocked by: core" if transitive issues exist
3. Includes the non-compat steps from the recipe (dep check, CI matrix, test scaffolding,
   test execution, rescan) — these are still recipe-driven since they're not compat-specific
4. Saves the combined plan to project.yml

### Hybrid approach

The plan merges TWO sources:
- **Compat-generated steps** (from analysis): scan, fix groups, verify
- **Recipe-generated steps** (from JSON): config edits, dep check, CI, tests, scaffold

This gives the best of both: analysis-driven fix steps + infrastructure steps.

```
Plan for module "core" targeting Python 3.8:
  1. [analysis]  Scan — 47 findings in 23 files (from compat engine)
  2. [fix]       Fix datetime.UTC (14 files) — auto-fixable
  3. [fix]       Fix enum.StrEnum (3 files) — manual
  4. [fix]       Add __future__ annotations (8 files) — auto-fixable
  5. [blocked]   Fix module "adapters" first (12 transitive findings)
  6. [config]    Update requires-python in pyproject.toml (from recipe)
  7. [dep]       Check dependency compatibility (from recipe)
  8. [dep]       Install pinned dependencies (from recipe)
  9. [test]      Scaffold tests (from recipe)
  10. [test]     Run isolated tests (from recipe)
  11. [verify]   Re-scan and confirm (from compat engine)
```

### Files changed
- `src/ui/web/routes/posture.py` — `posture_module_plan()`: use PlanEngine + recipe merge
- `src/core/services/module_upgrade/generator.py` — add `merge_with_compat_plan()` function

---

## Milestone 11: Rich Scan Step Output

**Goal**: The scan step shows filtered, grouped, actionable findings — not a 4963-item dump.

### What changes

`_scan_features()` in code_scanner.py output changes:

**Before (broken)**:
```json
{
  "ok": true,
  "can_apply": false,
  "preview_type": "findings",
  "summary": "Found 4963 feature(s) requiring Python > 3.8",
  "findings": [{"file": "...", "line": 1, "feature": "...", "version": "..."}]
}
```

**After**:
```json
{
  "ok": true,
  "can_apply": true,
  "preview_type": "compat_scan",
  "summary": "12 errors, 5 warnings in 23 files (10 auto-fixable)",
  "code_floor": "3.11",
  "by_severity": {"error": 12, "warning": 5},
  "auto_fixable": 10,
  "manual_only": 7,
  "by_feature": [
    {
      "feature": "datetime.UTC",
      "version": "3.11",
      "severity": "error",
      "count": 14,
      "fix_available": true,
      "fix_strategy": "replace_import_and_usages",
      "files": ["src/core/models/action.py:11", "..."]
    }
  ],
  "actions": [
    {"id": "fix_all_auto", "label": "Fix All Auto-fixable (10)", "type": "primary"},
    {"id": "fix_feature", "label": "Fix datetime.UTC", "feature_id": "python.stdlib.datetime_utc"}
  ]
}
```

### Filtering
- Exclude `severity: info` findings (noise: "logging improvements", "pathlib improvements")
- Exclude `fix_strategy: no_fix_needed` entries
- Only show error + warning severity

### Grouping
- Group by feature_name, show count, files, severity, fix availability
- Sort by severity (errors first), then by count (most occurrences first)

### Actions
- `can_apply: true` when auto-fixable findings exist
- `fix_all_auto` action: calls `compat.fix.fix_module()` for all auto-fixable
- Per-feature fix actions for individual features

### Files changed
- `src/core/services/module_upgrade/automation/code_scanner.py` — `_scan_features()` output format
- `src/ui/web/templates/scripts/globals/_system_posture.html` — render `compat_scan` preview type

---

## Milestone 12: Fix Flow in Step Execution

**Goal**: User can fix findings directly from scan step results. Fix → verify → report.

### What changes

When user clicks "Fix All Auto-fixable" from scan results:

1. Handler calls `compat.fix.fix_module()` with the auto-fixable findings
2. Fix engine applies transforms, verifies each (re-detect + syntax check)
3. Rolls back files where verification fails
4. Invalidates mediator cache (`compat.analysis.{module}`)
5. Returns:
   ```json
   {
     "ok": true,
     "summary": "Fixed 10/12 findings in 8 files (2 rolled back)",
     "fixed": 10,
     "failed": 2,
     "files_fixed": ["src/core/models/action.py", "..."],
     "files_rolled_back": ["src/core/engine/old.py"],
     "remaining": 7
   }
   ```

### New handler
Add `handle_fix_compat_auto` handler to code_scanner.py that:
- Reads cached analysis from mediator
- Filters to auto-fixable findings
- Calls `compat.fix.fix_module()`
- Returns results with verification status

Register it in the handler registry as `"fix_compat_auto"`.

### UI rendering
Step result shows:
- Green: "Fixed 10 findings in 8 files"
- Red: "2 fixes rolled back" (with file names)
- Remaining: "7 findings need manual attention"
- Button: "Re-scan" to verify

### Files changed
- `src/core/services/module_upgrade/automation/code_scanner.py` — add `handle_fix_compat_auto()`
- `src/core/services/module_upgrade/automation/__init__.py` — register handler
- `src/ui/web/templates/scripts/globals/_system_posture.html` — render fix results

---

## Milestone 13: Step State Machine Integration

**Goal**: Steps show PENDING/RUNNING/PASSED/FAILED/NEEDS_ATTENTION/BLOCKED instead of done/not-done.

### What changes

Currently project.yml has `done: true/false`. The compat StepStateMachine supports
richer states. This milestone doesn't replace project.yml — it ENRICHES the UI rendering
by computing state from the step's results.

The state is computed dynamically, not stored:
- Step has `done: true` → PASSED
- Step has findings with incompatible results → NEEDS_ATTENTION
- Step depends on a module that has unresolved findings → BLOCKED
- Step execution failed → FAILED
- Step not yet run → PENDING

The `determine_state()` function from `state_machine.py` already does this. Wire it
into the plan detail response.

### UI rendering
Step states render with colors and icons (CSS already exists from the commit):
- `.plan-step.blocked` — grey with lock icon
- `.plan-step.attention` — yellow with warning icon
- `.plan-step.failed` — red with X icon
- `.plan-step.done` — green with check

### Files changed
- `src/ui/web/routes/posture.py` — `posture_module_plan_detail()`: compute state per step
- `src/ui/web/templates/scripts/globals/_system_posture.html` — render states (already partially done)

---

## Milestone 14: Guide Step with Fix Actions

**Goal**: The "Review and fix incompatible syntax patterns" step shows rewrite hints
WITH one-click fix buttons, not just read-only text.

### What changes

`handle_guide_incompatible_syntax()` output adds fix actions:

For each feature group:
- Show before/after code examples (from `_REWRITE_GUIDES` + database entry)
- Show "Auto-fix" button if fix is available
- Show manual instructions if fix is manual
- Fix button calls `compat.fix.fix_module()` filtered to that feature

### Files changed
- `src/core/services/module_upgrade/automation/code_scanner.py` — guide output with actions
- `src/ui/web/templates/scripts/globals/_system_posture.html` — render guide with buttons

---

## Milestone 15: Assessment Before Plan Creation

**Goal**: Before creating a plan, show the user an assessment: is the target achievable?
What's the gap? What needs to happen?

### What changes

When user clicks "Create Plan":
1. Run `compat.assess()` (from mediator cache)
2. Show assessment summary:
   - Current floor: 3.11
   - Target: 3.8
   - Gap: 3 version levels
   - Auto-fixable: 10 findings
   - Manual: 7 findings
   - Blocked by: "core" module (12 transitive findings)
   - Recommendation: "Fix core first, then 10 auto-fixes + 7 manual"
3. User confirms → plan created with analysis-driven steps

This is the pre-flight check. Prevents creating plans for unachievable targets.

### Files changed
- `src/ui/web/routes/posture.py` — assessment endpoint or inline in plan creation
- `src/ui/web/templates/scripts/globals/_system_posture.html` — assessment UI in plan modal

---

## Milestone 16: Transitive Analysis Surface

**Goal**: Show cross-module dependency issues. "Module web is blocked by core."

### What changes

When analysis runs with transitive enabled:
- Findings marked `is_transitive: true` show differently
- Import chain shown: "web → core.models.action → datetime.UTC"
- Blocked module listed: "Fix core first"
- Plan step: "Blocked by: core (12 findings)" with state BLOCKED

### Trigger
Enable `analyze_transitive()` in the analysis resolver — currently uses `analyze_module()`
(direct only). Switch to transitive when the plan requests it.

### Files changed
- `src/core/services/mediator/registrations/compat.py` — analysis resolver uses transitive
- `src/ui/web/templates/scripts/globals/_system_posture.html` — transitive finding rendering

---

## Execution Order

```
M10 (analysis-driven plans)
  ↓
M11 (rich scan output) → M12 (fix flow) → M14 (guide with fix actions)
  ↓
M13 (step states)
  ↓
M15 (assessment) → M16 (transitive)
```

M10 first — changes what steps appear in the plan.
M11 before M12 — scan output must be right before fix actions make sense.
M13 can parallel with M11/M12 — UI state rendering is independent.
M15/M16 last — assessment and transitive build on everything else.

---

## What This Does NOT Change

- The compat YAML database (1000 entries) — stays
- The detection engine (M2 optimized) — stays
- The fix engine — stays (gets used more)
- The mediator integration (M1, M3) — stays
- The recipe system — stays for non-compat steps (CI, tests, scaffold)
- The handler registry — grows (new fix handler)
- The step execution infrastructure (executor.py, wizard.py) — stays
