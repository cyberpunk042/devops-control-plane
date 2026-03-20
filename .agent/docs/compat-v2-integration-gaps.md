# Compat V2 — Integration Gaps

> Complete audit of what compat v2 built vs what's actually integrated
> into the step execution flow and UI.

---

## What's USED (partially)

### Detection Engine → analysis results
- `analyze_module()` runs via mediator node `compat.analysis.{module}`
- Results are read by 3 handlers: `_scan_features`, `handle_guide`, `handle_add_future`
- Results are read by `handle_rescan_module` for finding count
- Results are read by `posture_module_compat_fix` for targeted fixes

### Fix Engine → single-finding and module-level fixes
- `fix_finding()` called from `handle_add_future_annotations` (for __future__ imports)
- `fix_module()` called from `posture_module_compat_fix` endpoint

### Registry → search and lookup
- `search()` used by compat-fix endpoint to find matching entries
- `get()` used by guide handler for rewrite hints

---

## What's NOT USED (idle code)

### Assessment system — completely unused
- `orchestrator.assess()` — pre-plan assessment, never called from step flow
- `VersionResolver.assess_target()` — target achievability analysis, never called
- `VersionResolver.compute_code_floor()` — compat's own code floor, never called
  (the legacy `module_intel.compute_code_floor()` still runs via posture bridge)
- `VersionResolver.compute_effective_floor()` — never called
- No assessment shown before plan creation (frontend removed in M5)
- No blocking module detection surfaced

### Dynamic plan generation — completely unused
- `PlanEngine.generate_plan()` — generates steps from actual analysis results
- `PlanEngine.save_plan()` — saves to project.yml
- `PlanEngine.load_plan()` — loads from project.yml
- The step flow uses static recipe-based plan generation (`generate_checklist()`)
  which reads JSON recipe files, NOT compat analysis
- The compat plan engine could generate SMARTER plans based on what it actually
  finds in the code (e.g., skip "add __future__" step if no annotation findings)

### Step lifecycle state machine — completely unused
- `StepStateMachine` with PENDING/RUNNING/PASSED/FAILED/NEEDS_ATTENTION/BLOCKED
- `StepStatus` with run count, last run time, error messages, findings counts
- `StateTransition` with history tracking
- `determine_state()` — maps analysis results to step states
- The step flow uses simple `done: true/false` in project.yml
- No NEEDS_ATTENTION, BLOCKED, or FAILED states surfaced in UI
- No transition history tracked

### Compat step executor — completely unused
- `StepExecutor.execute()` — runs a single step with compat engine
- `StepExecutor.execute_and_transition()` — execute + state machine update
- The step flow uses the legacy `executor.py` which dispatches to handler functions
- The compat step executor was designed to REPLACE the legacy executor

### Batch runner — completely unused
- `BatchRunner.run()` — runs multiple steps with state tracking
- `BatchRunner.run_streaming()` — same with SSE event streaming
- `BatchResult` with pass/fail counts, duration
- The step flow uses the legacy `wizard.py` batch system

### Import resolver / transitive analysis — never triggered
- `ImportResolver.build_graph()` — builds cross-module import graph
- `analyze_transitive()` — follows imports across modules
- The analysis nodes use `analyze_module()` (direct only), not `analyze_transitive()`
- No transitive findings surfaced in step flow
- No "blocked by module X" shown

### Fix strategies — most unused
- The database has 10+ fix strategies: replace_import, replace_usage, add_import,
  remove_import, add_future_import, replace_call, wrap_call, conditional_import, etc.
- Only `add_future_import` is used (from handle_add_future_annotations)
- The compat-fix endpoint uses `fix_module()` but only when user clicks specific
  fix buttons — not integrated into the step flow
- No "Fix All Auto-fixable" action in step results
- No verification loop (detect → fix → re-detect → verify) in step flow

### Verification / rollback — unused in step flow
- `Verifier.verify_fix()` — re-detect + syntax check + import check
- `SnapshotManager` — file backup before fix, rollback on failure
- Fix verification runs inside `fix_module()` when called from compat-fix endpoint
- But not triggered from any step handler

---

## What's WRONG in what IS used

### Scan step returns ALL findings unfiltered
- 4963 findings including `severity: info` and `fix: no_fix_needed`
- Entries like "logging improvements (3.13)", "pathlib improvements (3.13)" are noise
- Should filter to `severity: error/warning` with actual fixes available
- Should group by feature, show counts, offer "Fix All" action

### Scan step shows flat list with no actions
- `can_apply: False` — UI renders as read-only
- No "Fix this" buttons on individual findings
- No "Fix All Auto-fixable" button
- No severity badges
- No grouping by feature or by file

### Guide step has rewrite hints but no fix actions
- Shows before/after examples from `_REWRITE_GUIDES`
- But `can_apply: False` — user can see what to do but can't click to do it
- The compat fix engine CAN do these fixes — just not wired to the guide step

### No remediation flow
- Scan finds 4963 issues → user sees a wall of text → no next step
- Should be: scan → show summary → offer fix actions → apply → re-scan → verify

### Plan generation is static, not analysis-driven
- `generate_checklist()` reads JSON recipes with condition evaluation
- It doesn't know what the compat engine found
- A "scan_incompatible_features" step always appears even if there are 0 findings
- A "add_future_annotations" step appears even if no files need it
- The compat `PlanEngine.generate_plan()` creates steps FROM the analysis — if
  the analysis finds 0 annotation issues, no annotation step is generated

---

## What Needs to Happen

### Tier 1: Fix what's wired but broken
1. Filter scan results — only error/warning severity, exclude no_fix_needed
2. Group findings by feature in scan output
3. Add "Fix All Auto-fixable" action to scan step results (`can_apply: True` when fixable findings exist)
4. Show severity and fix availability in finding output
5. Count properly: "12 errors in 8 files (10 auto-fixable)" not "4963 findings"

### Tier 2: Wire the fix flow into steps
6. Scan step with findings → offer fix actions
7. Fix action calls `compat.fix.fix_module()` for all auto-fixable findings
8. After fix → invalidate cache → re-scan → show remaining
9. Verification: detect → fix → re-detect → import check → mark fixed
10. Rollback on failed verification

### Tier 3: Wire the lifecycle
11. Use `StepStateMachine` instead of `done: true/false`
12. Show NEEDS_ATTENTION when findings exist (not just "step done")
13. Show BLOCKED when transitive deps have issues
14. Use compat `PlanEngine.generate_plan()` for analysis-driven step generation
15. Use compat `BatchRunner` for batch execution with proper state tracking

### Tier 4: Wire transitive analysis
16. Enable `analyze_transitive()` — show cross-module import issues
17. Show "blocked by: core" when web depends on core and core has issues
18. Assessment before plan creation — is the target achievable?
