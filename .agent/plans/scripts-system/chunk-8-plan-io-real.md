# Chunk 8: Execution Plan I/O — From Scaffolding to Production

> **Status**: Not started
> **Created**: 2026-03-10
> **Parent**: `scripts-system-M7-plans.md` → Post-Chunk 7b
> **Depends on**: Chunk 5 (Plans skeleton) ✅, Chunk 6 (I/O evolution scaffold) ✅, Chunk 7b (Suite I/O — three layers) ✅

---

## 0. Why This Chunk Exists

Chunk 7b completed the I/O system at the **suite level** — recording, validation,
and save. Suites now have:
- `variables: dict[str, str]` — declared input parameters with defaults
- `outputs: dict[str, str]` — declared exports from capture steps
- Steps with `export_as` — named output bindings
- Steps with `${VAR_NAME}` in value — input bindings with `original_value` preserved
- `sync_suite_io()` — auto-derives suite-level I/O from step-level bindings

The Execution Plan layer has **scaffolding** that was built BEFORE the I/O refactor.
It references old data shapes, was never tested with real suite I/O data, and the
visual is minimal. This chunk makes it production-ready — full chain, every layer.

---

## 1. Chain Audit — What Exists at Every Layer

### Backend Data Model

| Item | Status | Location | Notes |
|------|--------|----------|-------|
| `PlanStep.produces: list[str]` | ✅ Exists | `plans.py:115` | Stored as explicit field |
| `PlanStep.consumes: list[str]` | ✅ Exists | `plans.py:118` | Stored as explicit field |
| `PlanStep.suite_variables: dict` | ✅ Exists | `plans.py:98` | Per-step overrides for CDP suite variables |
| `PlanStep.script_params: dict` | ✅ Exists | `plans.py:94` | Per-step overrides for script params |
| `ExecutionPlan.variables: dict` | ✅ Exists | `plans.py:188` | Initial namespace variables |
| `StepResult.variables_produced: dict` | ✅ Exists | `plans.py:279` | What the step actually produced |
| `PlanRunResult.variables: dict` | ✅ Exists | `plans.py:361` | Final namespace snapshot |
| `PlanRunResult.step_results[].variables_produced` | ✅ Exists | Serialized in `to_dict()` | Per-step output data in saved results |

**Model gap**: None. The data model is fine.

### Backend Executor

| Item | Status | Location | Notes |
|------|--------|----------|-------|
| Namespace initialization from `plan.variables` | ✅ Works | `plan_executor.py:717` | `namespace = dict(plan.variables)` |
| Namespace merge after each step | ✅ Works | `plan_executor.py:786-787` | `namespace.update(step_result.variables_produced)` |
| Script step: passes namespace as params | ✅ Works | `plan_executor.py:301-303` | `params = dict(namespace); params.update(step.script_params)` |
| Script step: extracts `DCP_VAR_` from stdout | ✅ Works | `plan_executor.py:312` | `_extract_variables_from_lines()` |
| CDP step: passes namespace + suite_variables to replayer | ✅ Works | `plan_executor.py:353-355` | `variables = dict(namespace); variables.update(step.suite_variables)` |
| CDP step: extracts `export_name` outputs | ✅ Works | `plan_executor.py:397-407` | Reads `export_name` and `captured_value` from replay results |
| Checkpoint: sends namespace + next_step I/O | ✅ Works | `plan_executor.py:488-497` | Sends `variables`, `next_step` (with consumes/produces), `steps_produced_since` |
| Interactive pause: sends step_produced | ✅ Works | `plan_executor.py:850-858` | Sends `step_produced`, `next_step`, `variables` |
| Resume: applies variable_updates | ✅ Works | `plan_executor.py:506-508, 867-868` | `namespace.update(plan_run.pending_var_updates)` |
| Validation: chain analysis | ✅ Works | `plan_executor.py:221-233` | Checks consumed vs available |
| plan:step_done event includes variables_produced | ✅ Works | `plan_executor.py:809` | SSE carries produced vars |
| plan:done event includes final namespace | ✅ Works | `plan_executor.py:938` | SSE carries final variables |

**Executor gap**: None operationally. BUT: the `produces`/`consumes` fields on `PlanStep` are **manually populated** — the executor doesn't auto-derive them from suite/script metadata. It trusts whatever was saved.

### Backend API

| Item | Status | Location | Notes |
|------|--------|----------|-------|
| `GET /plans` | ✅ Works | `crud.py:31-38` | Returns plan summaries (no step I/O detail) |
| `GET /plans/<id>` | ✅ Works | `crud.py:44-53` | Returns full plan with steps (includes produces/consumes) |
| `POST /plans` | ✅ Works | `crud.py:59-79` | Creates plan from JSON body |
| `PUT /plans/<id>` | ✅ Works | `crud.py:85-122` | Updates plan, replaces steps entirely |
| `POST /plans/<id>/execute` | ✅ Works | `execution.py:32-102` | Starts execution, returns run_id |
| `POST /plans/run/<id>/resume` | ✅ Works | `execution.py:130-148` | Accepts `variables` dict in body |
| `GET /plans/results/<id>` | ✅ Works | `execution.py:214-223` | Returns full result with step_results |
| **`GET /cdp-test/suites/<id>` — suite metadata** | ✅ Works | `suites.py:47-56` | Returns `suite.to_dict()` which includes `variables` and `outputs` |
| **`GET /scripts/info/<id>` — script metadata** | ⚠️ Unclear | Needs check | Does it return `parameters` and `outputs`? The plan editor uses these fields |

**API gap**: Need to verify script info endpoint returns declared outputs — the plan editor renders them.

### Frontend — Plan Editor

| Item | Status | Code Lines | Gap |
|------|--------|------------|-----|
| Fetch suite metadata on step edit | ⚠️ Exists but untested | `_plans.html:791-801` | Uses `_plansFetchSuiteMeta()` which calls `GET /cdp-test/suites/<id>`. Response includes `variables` and `outputs` from `to_dict()`. **But**: was written BEFORE `sync_suite_io` existed — suite may have empty `variables`/`outputs` if `sync_suite_io` was never called for that suite |
| Render suite variables as typed inputs | ⚠️ Scaffold | `_plans.html:922-936` | Reads `suite.variables` — each entry becomes an `<input>`. Works IF the data is populated. |
| Render suite outputs | ⚠️ Scaffold | `_plans.html:943-952` | Reads `suite.outputs` — displays read-only. Works IF the data is populated. |
| Fetch script metadata on step edit | ⚠️ Exists but untested | `_plans.html:779-790` | Uses `_plansFetchScriptMeta()` which calls `GET /scripts/info/<id>`. |
| Render script params as typed fields | ⚠️ Scaffold | `_plans.html:847-895` | Reads `meta.parameters`. Typed by type (boolean, choice, text). |
| Render script declared outputs | ⚠️ Scaffold | `_plans.html:898-910` | Reads `meta.outputs`. |
| Upstream var dropdown | ⚠️ Uses stale data | `_plans.html:803-831` | `_plansUpstreamVars()` reads from `produces` field — which is manually typed or auto-populated on save, NOT from live suite metadata |
| Step row I/O badges | 🔴 Decorative | `_plans.html:601-602` | Shows `📤2 📥1` but values come from manual `produces`/`consumes` — often empty |
| Auto-populate on step pick | 🔴 Missing | `_plans.html:735-751` | `_plansPickSuite()` creates step with `produces: [], consumes: []` — doesn't fetch suite I/O |
| Auto-populate on step save | ⚠️ Partial | `_plans.html:1014-1040` | Auto-populates `produces` from `_suiteMeta.outputs` or `_meta.outputs` on save — but only if `produces` was empty |
| Refresh metadata button | 🔴 Missing | — | No way to re-fetch after editing a suite |
| I/O summary section in editor | 🔴 Missing | — | No overview of all I/O across the plan |
| `consumes` auto-populate | 🔴 Missing | — | Only `produces` is auto-populated, never `consumes` |
| Manual produces/consumes fields | ⚠️ Still there | `_plans.html:962-963` | Free-text comma fields — should be replaced by auto-derived display |

### Frontend — Pre-Run Confirmation

| Item | Status | Code Lines | Gap |
|------|--------|------------|-----|
| Wiring analysis (walk steps, detect missing) | ✅ Works | `_plans.html:289-311` | Simulates namespace accumulation from `produces`/`consumes`. BUT: depends on those fields being populated — if they're empty (because auto-populate never ran), everything shows as "no I/O" |
| Step I/O badges in pre-run | ✅ Works | `_plans.html:313-349` | Shows ✅/❌ per consumed, 📤 per produced |
| Block fully_automated if missing | ✅ Works | `_plans.html:311` | `blockExecution = isFullyAutomated && totalMissing > 0` |
| Flow arrows between steps | ⚠️ Minimal | `_plans.html:338-339` | Single `↓` if step has produces. No variable name labels. |
| Visual flow diagram | 🔴 Missing | — | No cards with ports, no connection lines |
| Missing input inline form | 🔴 Missing | — | Shows "switch to semi_automated" but doesn't let you fill missing vars inline |
| Suite/script descriptions alongside vars | 🔴 Missing | — | No context about what each variable means |

### Frontend — Pause View (Interactive + Checkpoint)

| Item | Status | Code Lines | Gap |
|------|--------|------------|-----|
| Pause reason header | ✅ Works | `_plans.html:1996-2000` | Shows "⏸ Checkpoint" or "⏸ Paused" |
| Produced vars panel | ✅ Works | `_plans.html:2002-2018` | Shows key=value for produced vars |
| Next step preview with consumes/produces | ✅ Works | `_plans.html:2020-2044` | Shows ✅/❌ per consumed var |
| Editable namespace | ⚠️ Basic | `_plans.html:2046-2064` | Text inputs per var. No add/delete. No JSON viewer. |
| Resume with var updates | ✅ Works | `_plans.html` (via `_plansResumeWithVars`) | Collects `data-ns-key` inputs, sends as `variables` |
| Next step typed input form | 🔴 Missing | — | User sees what next step needs but can't fill via typed fields from suite/script metadata |
| Add variable button | 🔴 Missing | — | Can't add new variables at pause |
| Delete variable button | 🔴 Missing | — | Can't remove vars |
| JSON tree viewer for complex values | 🔴 Missing | — | Complex values shown as string |
| Differentiate interactive vs checkpoint | 🔴 Same UI | — | Both use identical rendering |
| Step result details at pause | 🔴 Missing | — | Produced vars shown but no step result card (passed/failed, duration) |
| Semi-auto: show upcoming steps until next checkpoint | 🔴 Missing | — | Checkpoint only shows next step, not the full window until next checkpoint |

### Frontend — Result View

| Item | Status | Code Lines | Gap |
|------|--------|------------|-----|
| Verdict card (passed/failed, duration, counts) | ✅ Works | `_plans.html:1306-1342` | |
| Timeline bar | ✅ Works | `_plans.html:1355-1367` | Color-coded segments |
| Step result rows | ✅ Works | `_plans.html:1370+` | Shows step status, duration, expandable |
| Per-step variables_produced in result view | 🔴 NOT shown | — | The data exists in `step_results[].variables_produced` but the result view doesn't display it inline |
| Namespace timeline (diff-style) | 🔴 Missing | — | No view of how namespace grew per step |
| Final namespace panel | ⚠️ Exists | `_plans.html` | Variables panel in result view — but collapsed, no JSON tree |
| Copy namespace as JSON | 🔴 Missing | — | |
| Per-step consumed vs produced trace | 🔴 Missing | — | Result view doesn't show what each step consumed |

---

## 2. The Fundamental Problem

**The `produces`/`consumes` fields on `PlanStep` are rarely populated.**

They get populated in THREE ways:
1. User manually types them in comma-separated fields ← users won't do this
2. Auto-populate from suite `outputs` on save ← only if user edits and saves the step
3. Auto-populate from script `outputs` on save ← same

But when picking a suite to add as a step (`_plansPickSuite`), the step is created
with `produces: [], consumes: []`. The suite metadata is never fetched at that point.

**This means**: the pre-run wiring analysis, the I/O badges, the upstream var dropdown
— they all show nothing. The I/O system appears broken because the data is never loaded.

**Fix**: When a suite/script is picked as a step, IMMEDIATELY fetch its metadata and
auto-populate `produces` from declared outputs and `consumes` from declared inputs.

---

## 3. Sub-Chunk Breakdown with Full Achievement Chain

### Chunk 8a: Plan Editor — Auto-Derive I/O on Step Add
> Make the I/O data exist from the moment a step is added.

**Steps (ONE at a time)**:

**8a-1**: `_plansPickSuite()` — fetch suite metadata immediately, set `produces`/`consumes`
- **File**: `_plans.html` (function `_plansPickSuite`, line 735)
- **Chain**: `_plansPickSuite()` → `_plansFetchSuiteMeta(suiteId)` → `GET /api/cdp-test/suites/<id>` → `suite.to_dict()` → reads `suite.outputs` (keys = produces) + `suite.variables` (keys = consumes) → populate step
- **What changes**: After `_plansEditorSteps.push({...})`, add async fetch of suite metadata. Set `s.produces = Object.keys(suite.outputs || {})` and `s.consumes = Object.keys(suite.variables || {})`. Pre-populate `s.suite_variables` from suite defaults.
- **Verify**: Add a CDP step for a suite that has variables/outputs → step should show 📥/📤 badges immediately. No edit required.
- **Pre-condition**: The suite must have been through `sync_suite_io()` so `variables` and `outputs` are populated. This is done by chunk 7b on save.

**8a-2**: `_plansPickScript()` — fetch script metadata immediately, set `produces`/`consumes`
- **File**: `_plans.html` (function `_plansPickScript`, line 681)
- **Chain**: `_plansPickScript()` → `_plansFetchScriptMeta(scriptId)` → `GET /api/scripts/info/<id>` → reads `meta.outputs` (produces) + `meta.parameters` where `required=true` (consumes)
- **What changes**: Same pattern as 8a-1 but for scripts
- **Verify**: Add a script step → badges appear immediately
- **Pre-condition**: Need to verify `GET /scripts/info/<id>` returns `outputs` and `parameters`. If not, backend work needed.

**8a-3**: Replace manual produces/consumes text fields with auto-derived read-only display + override toggle
- **File**: `_plans.html` (function `_plansEditStep`, lines 962-963, and `_plansSaveStep`, lines 981-985)
- **What changes**: Remove the two `modalFormField` for produces/consumes. Replace with:
  - Read-only display: "📤 Produces: AUTH_TOKEN, USER_ID (from suite outputs)"
  - Small "✏️ Override" toggle → if clicked, shows editable list (not comma textarea)
  - On save: if no override, produces/consumes come from metadata; if overridden, use user values
- **Verify**: Edit a step → see auto-derived I/O → override toggle works

**8a-4**: Step rows in editor show I/O variable names, not just counts
- **File**: `_plans.html` (function `_plansRenderEditorSteps`, lines 601-602)
- **What changes**: Instead of `📤2`, show `📤 AUTH_TOKEN, USER_ID`. Instead of `📥1`, show `📥 BASE_URL ← initial ✅`. Add upstream resolution for each consumed var.
- **Verify**: Editor step list shows named I/O with source

**8a-5**: Add "🔄 Refresh" button to step edit form to re-fetch metadata
- **File**: `_plans.html` (function `_plansEditStep`, near lines 917-920)
- **What changes**: Button next to suite/script ID that clears cache and re-fetches. `delete _plansMetaCache.suites[suiteId]; _plansEditStep(index);`
- **Verify**: Edit suite in another tab → refresh in plan editor → see new I/O

**8a-6**: I/O summary section at bottom of editor
- **File**: `_plans.html` (function `_plansShowEditor`)
- **What changes**: Below the step list, add an "I/O Summary" panel:
  - Left column: all inputs needed (variable name, source step or initial, whether satisfied)
  - Right column: all outputs produced (variable name, source step)
  - Red highlight for unsatisfied inputs
- **Verify**: Create a plan with 3 steps → summary shows complete I/O picture

---

### Chunk 8b: Pre-Run — Rich I/O Wiring View
> Make the pre-run confirmation show the I/O story clearly.

**Steps (ONE at a time)**:

**8b-1**: Expand step cards in pre-run to show variable NAMES not just badges
- **File**: `_plans.html` (function `_plansRun`, lines 313-349)
- **What changes**: Each step card shows:
  - Input panel: `📥 BASE_URL ← initial ✅` / `📥 AUTH_TOKEN ← Step 1 ✅` / `📥 DB_HOST ← ❌ MISSING`
  - Output panel: `📤 AUTH_TOKEN · 📤 USER_ID`
  - Vertical flow connector between steps showing which variables flow
- **Verify**: Open pre-run for a plan with I/O → see named wiring

**8b-2**: Variable flow arrows between steps
- **File**: `_plans.html` (same section)
- **What changes**: Between step cards, show the variable names that flow through:
  ```
  [Step 1 Login] produces AUTH_TOKEN, USER_ID
       ↓ AUTH_TOKEN
  [Step 2 Deploy] consumes AUTH_TOKEN
  ```
  Currently just a bare `↓` arrow
- **Verify**: Flow arrows show variable names

**8b-3**: Missing input inline form
- **File**: `_plans.html` (after the step list in pre-run)
- **What changes**: For each missing input, show an input field. Values entered here get added to the plan's initial variables before execution.
  - "❌ Step 4 needs DB_HOST — no producer, no default"
  - `[db.example.com____]` input field
  - On execute: merge these into `variables` in the execute POST body
- **Currently**: The pre-run shows "switch to semi_automated mode" but no way to fill values
- **Verify**: Pre-run with missing input → fill it → execute → step receives the value

---

### Chunk 8c: Pause View — I/O Cockpit
> Make the interactive/checkpoint pause view a proper I/O control panel.

**Steps (ONE at a time)**:

**8c-1**: Step result card at pause — show what just completed
- **File**: `_plans.html` (SSE handler for `plan:paused`, lines 1991-2068)
- **What changes**: Before the pause panel, show a result card for the step that just ran:
  - Status (✅/❌), duration, step name
  - If CDP test: replay passed/failed/total
  - Variables produced (highlighted)
- **Currently**: The pause panel shows produced vars but no step result context
- **Data source**: The `plan:step_done` event fires BEFORE `plan:paused` — the step result is already in `_plansStepResults`. But for interactive mode, `plan:paused` fires in the SAME callback context as `plan:step_done` (lines 834-882) — need to verify ordering.
- **Verify**: Run interactive plan → step completes → pause shows step result card

**8c-2**: Next step typed input form at pause
- **File**: `_plans.html` (pause panel, after next-step preview)
- **What changes**: When paused, fetch the next step's metadata (suite or script) and render typed form fields. Pre-fill from namespace. Let user edit before resume.
  - For CDP test: fetch suite via `_plansFetchSuiteMeta(nextStep.suite_id)` → render variable inputs from `suite.variables`
  - For script: fetch script via `_plansFetchScriptMeta(nextStep.script_id)` → render param inputs from `meta.parameters`
  - On resume: merge these typed values into the `variable_updates` sent to resume
- **Currently**: Next step preview shows "needs: ✅ VAR_A ❌ VAR_B" but no typed input form
- **Chain**: Pause SSE → get next step info → async fetch metadata → render form → user fills → resume sends values
- **Gap**: Need the next step's `suite_id` or `script_id` in the `next_step` payload from the backend. Currently (plan_executor.py:469-477) the checkpoint sends `id, name, type, sequence, consumes, produces` — **missing `suite_id` and `script_id`**.
- **Backend change needed**: Add `suite_id` and `script_id` to the `next_step_info` dict in both `_execute_checkpoint_step` (line 470) and the interactive pause (line 841).
- **Verify**: Pause at checkpoint → see typed input form for next CDP step → fill value → resume → step receives that value

**8c-3**: Add/delete namespace variables at pause
- **File**: `_plans.html` (pause panel, editable namespace section)
- **What changes**:
  - "➕ Add Variable" button below namespace list. Adds empty row with key + value inputs.
  - "✕" button on each namespace row to delete a variable.
  - On resume: deleted vars still exist in backend namespace — add a `deleted_keys` field or simply send the full edited namespace. Safest: send the FULL namespace as the user sees it.
- **Currently**: Editable namespace is fixed — can edit values but can't add/remove keys.
- **Backend change evaluation**: The `resume_plan()` function does `namespace.update(variable_updates)` — this ADDS but doesn't REMOVE. To support deletion, we'd need either:
  a. Send `{variable_name: null}` to signal deletion, and have executor treat null as delete
  b. Send full replacement namespace instead of merge
  Option (a) is simpler and non-breaking.
- **Verify**: Pause → add a variable → resume → new var available in namespace. Pause → delete a var → resume → var is gone.

**8c-4**: Differentiate interactive vs checkpoint pause UI
- **File**: `_plans.html` (SSE handler for `plan:paused`)
- **What changes**:
  - `reason === 'interactive'`: Show the completing step's result card prominently. Show produced vars inline. Show next step form.
  - `reason === 'checkpoint'`: Show the checkpoint message. Show ALL vars produced since last checkpoint (already exists). Show ALL upcoming steps until next checkpoint with their I/O readiness.
- **Currently**: Both render identically except for the label.
- **For checkpoint upcoming steps**: Backend already sends `sorted_steps` but the pause event only includes `next_step` (the one after the checkpoint). To show ALL upcoming, the frontend would need the full step list — which it has from the plan data (cached from editor or fetched at execution start).
- **Verify**: Interactive pause shows step-focused view. Checkpoint pause shows window-focused view.

---

### Chunk 8d: Result View — Variable Trace
> Make the post-execution result view tell the I/O story.

**Steps (ONE at a time)**:

**8d-1**: Per-step variables_produced display in result view
- **File**: `_plans.html` (function `_plansViewResult`, step rendering section)
- **What changes**: Under each step result row, show:
  - `📤 produced: AUTH_TOKEN = abc123…, USER_ID = 42` (if step produced vars)
  - `📥 consumed: BASE_URL, AUTH_TOKEN` (from step's `consumes` field — but this is stored in the plan, not in the result. Need to cross-reference.)
- **Data source**: `result.step_results[i].variables_produced` is in the saved result JSON. But `consumes` is on the plan step, not the result. Need to either:
  a. Fetch the plan alongside the result (already done — result has `plan_id`)
  b. Store `consumes` in `StepResult` (backend model change)
  Option (a) is simpler — fetch plan, match step IDs.
- **Verify**: View a result → each step shows produced variables inline

**8d-2**: Namespace timeline — how the namespace grew step by step
- **File**: `_plans.html` (function `_plansViewResult`)
- **What changes**: After the step list, add a "Variable Trace" section:
  - Table: Variable | Source | Value | Step
  - Walk `step_results` in order, accumulate namespace, show what each step added
  - Color-code: initial vars (blue), step-produced vars (green), user-added-at-pause (yellow)
- **Data source**: `result.step_results[i].variables_produced` + `result.variables` (final namespace)
- **Verify**: View a result → see full variable timeline

**8d-3**: Final namespace expandable panel with JSON tree + copy
- **File**: `_plans.html` (function `_plansViewResult`, variables panel)
- **What changes**: Replace the collapsed Variables panel with:
  - Expandable panel showing all final namespace variables
  - JSON tree viewer for complex (object/array) values
  - "📋 Copy as JSON" button
- **Currently**: Collapsed text panel with raw display
- **Verify**: View a result → expand vars → see JSON tree → copy works

---

## 4. Execution Order

```
8a-1 ─ Pick suite → auto-populate I/O
8a-2 ─ Pick script → auto-populate I/O
8a-3 ─ Replace manual fields with auto-derived display
8a-4 ─ Step rows show named I/O
8a-5 ─ Refresh metadata button
8a-6 ─ I/O summary section
  ↓
8b-1 ─ Pre-run named variable display
8b-2 ─ Flow arrows with variable names
8b-3 ─ Missing input inline form
  ↓
8c-1 ─ Step result card at pause
8c-2 ─ Next step typed input form ← NEEDS BACKEND: add suite_id/script_id to next_step payload
8c-3 ─ Add/delete namespace vars ← NEEDS BACKEND: handle null = delete in resume
8c-4 ─ Differentiate interactive vs checkpoint
  ↓
8d-1 ─ Per-step produced vars in result view
8d-2 ─ Namespace timeline
8d-3 ─ Final namespace JSON tree + copy
```

Each step is independently deliverable and testable.

---

## 5. Backend Changes Required

| Change | Sub-chunk | File | Description |
|--------|-----------|------|-------------|
| Add `suite_id`/`script_id` to `next_step_info` | 8c-2 | `plan_executor.py:470, 841` | Add `"suite_id": ns.suite_id, "script_id": ns.script_id` to the next_step dict sent in pause events |
| Handle `null` in `variable_updates` as delete | 8c-3 | `plan_executor.py:506-508, 867-868` | After `namespace.update(updates)`, do `namespace = {k: v for k, v in namespace.items() if v is not None}` |
| Verify `GET /scripts/info/<id>` returns outputs | 8a-2 | Script info route | Check that `ScriptOutput` data is returned |

---

## 6. What We Do NOT Build

| Not in scope | Why |
|-------------|-----|
| Drag-and-drop visual wiring editor | Future enhancement — auto-derive + dropdown is sufficient |
| Type coercion at runtime | Types are advisory for now |
| Cross-plan namespace sharing | Each plan has its own namespace |
| Real-time streaming of variable values during step execution | Variables are extracted after step completes |
| I/O validation on plan save (backend) | Frontend validates at pre-run; save is permissive |

---

## 7. File Map

| Sub-chunk | Frontend File | Backend File |
|-----------|--------------|-------------|
| 8a | `_plans.html` | — |
| 8b | `_plans.html` | — |
| 8c | `_plans.html` | `plan_executor.py` (2 small changes) |
| 8d | `_plans.html` | — |

---

## 8. Cross-References

| Reference | Location |
|-----------|----------|
| Plan Executor | `src/core/services/scripts/plan_executor.py` (1017 lines) |
| Plan Models | `src/core/services/scripts/plans.py` (414 lines) |
| Plan Storage | `src/core/services/scripts/plan_storage.py` (186 lines) |
| Plan CRUD Routes | `src/ui/web/routes/plans/crud.py` (178 lines) |
| Plan Execution Routes | `src/ui/web/routes/plans/execution.py` (224 lines) |
| Plans UI | `src/ui/web/templates/scripts/integrations/_plans.html` (2307 lines) |
| CDP Test Models | `src/core/services/cdp_test/models.py` (686 lines) |
| Suite Routes | `src/ui/web/routes/cdp_test/suites.py` (254 lines) |
| Script Models | `src/core/services/scripts/models.py` |
| Chunk 7b Plan | `.agent/plans/scripts-system/chunk-7b-io-three-layers.md` |
