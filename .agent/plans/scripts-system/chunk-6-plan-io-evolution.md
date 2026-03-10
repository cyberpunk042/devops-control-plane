# Chunk 6: Completing the Execution Plan Vision — I/O, Modes, and Chaining

> **Status**: ✅ Implemented — All sub-chunks (6a–6h) complete
> **Created**: 2026-03-09
> **Parent**: `scripts-system-M7-plans.md` → Post-Chunk 5
> **Depends on**: Chunk 5 (Execution Plans — skeleton) ✅

---

## 0. Source of Truth — Verbatim

> "Its because tests script can have inputs and outputs now. Thus why the
> three mode make more sense to the execution plan. not all tests have but
> just like we will support for any script we will support it for test in a
> very similar fashion, for simple / single output of any format vs a single
> or complex object return and we are able to fill those input and even
> default values and we are able to gather output based on the run, we need
> to discuss all this.. this is going to allow us to chain tests and scripts
> with various mode and have complete or partial I/O for each for advanced
> exec plan."

> "This is a long evolution. Treat it as such."

> "remember there are multiple type of execution plan. its not as if it was
> already existing... now its just continuous in the UI after execution"

> "it is 'fully_automated, semi_automated, interactive' but there is nothing
> about it in your plan that would make me feel you really understand"

---

## 1. What This Chunk Is

Chunk 5 built the **skeleton** of execution plans: step models, plan storage,
basic sequential execution, SSE live view, and the initial plan editor. It
works, but the three modes (`fully_automated`, `semi_automated`, `interactive`)
are not meaningfully differentiated yet. The execution is essentially
continuous — steps run, results appear, maybe it pauses, you click resume,
it continues. The pause is empty.

**This chunk completes the vision.** It makes the three modes genuinely
different experiences by adding I/O awareness — declared inputs and outputs
on scripts and tests, smart runtime interaction at pause points, and the
ability to chain step data through a visible, manageable namespace.

Without I/O, the modes are speedbumps. With I/O, the modes become:

| Mode | Experience |
|------|-----------|
| **fully_automated** | Everything pre-wired. No user interaction. Inputs must have defaults or come from upstream outputs. If anything is missing, the plan can't start. Runs autonomously. |
| **semi_automated** | User interaction at checkpoints. At each checkpoint: see accumulated outputs, see what upcoming steps need, fill in missing inputs, adjust values based on what just happened. The checkpoint is an **I/O decision point**. |
| **interactive** | User interaction after **every** step. After each step: see what was produced, see what the next step needs, review/edit/override namespace values, decide to continue/skip/abort based on intermediate results. The user is **driving the data pipeline** step by step. |

---

## 2. Current State — Honest Baseline

### 2.1 What Actually Works Today (UI)

| Feature | State | What it actually does |
|---------|-------|----------------------|
| **Plan list** | ✅ Works | Lists saved plans with Run/Edit/Delete buttons |
| **Plan editor** | ✅ Works | Create/edit plans with name, description, mode select, browser config. Add script/cdp_test/checkpoint steps. Reorder, delete, edit steps. |
| **Step editor modal** | ⚠️ Raw | Script steps: free-text `key=val` textarea for params. CDP test steps: free-text `key=val` for suite_variables. Produces/consumes: comma-separated text fields. No awareness of declared params. |
| **Pre-run confirmation** | ✅ Works | Shows mode label, browser config, step list, initial variables. Then Execute. |
| **Execution live view** | ✅ Works | Modal with pulsing dot, progress bar, step results appearing via SSE. Live CDP test sub-steps expand during execution. Variables panel (collapsed, togglable). |
| **Pause (checkpoint)** | ⚠️ Minimal | Title changes to "⏸ Paused". Shows Resume/Skip/Cancel buttons. Shows checkpoint message if any. **Does NOT show variables, does NOT show next step's needs, does NOT let user edit namespace.** |
| **Pause (interactive)** | ⚠️ Minimal | Same as checkpoint pause: "Step N completed: passed" message + Resume/Skip/Cancel. **Same empty pause — no I/O interaction.** |
| **Result view** | ✅ Works | Per-step results with drill-down (script: exit code, lines; CDP test: replay results with per-step detail, screenshots, console logs). Variable trace (per-step produced vars, final namespace). Chrome close button. |
| **Variable namespace** | ⚠️ Display only | Variables panel shows accumulated `key=value` pairs. **Read-only. No editing. No types. No connection to step requirements.** |

### 2.2 What Actually Works Today (Backend)

| Feature | State | What it actually does |
|---------|-------|----------------------|
| **Mode-based pausing** | ✅ Works | `interactive` pauses after every step. `semi_automated` pauses at checkpoints. `fully_automated` runs through. Pause blocks via `resume_event.wait()`. |
| **Namespace accumulation** | ✅ Works | `namespace = dict(plan.variables)` → after each step, `namespace.update(step_result.variables_produced)`. |
| **Script var extraction** | ✅ Works | `_extract_variables_from_lines()` parses `DCP_VAR_KEY=VALUE` from stdout → `variables_produced`. |
| **CDP var extraction** | ⚠️ Ad-hoc | Extracts `captured_value` from result records, uses cleaned CSS selector as key. No formal naming. |
| **Pause event data** | ⚠️ Sends vars | `plan:paused` event includes `variables: namespace` — **but the UI ignores it**. |
| **Script input delivery** | ✅ Works | `script_params` from PlanStep merged with namespace → passed as CLI flags. |
| **CDP input delivery** | ✅ Works | `suite_variables` from PlanStep merged with namespace → passed to replayer `variables` param. |
| **Produces/consumes** | ❌ Decorative | Fields exist on PlanStep model, saved/loaded, editable in UI, but **never validated, never enforced, never used at execution time**. |

### 2.3 What Actually Works Today (Script I/O)

| Feature | State | Detail |
|---------|-------|--------|
| **Input declaration** | ✅ Full | `ScriptParameter` — name, type (string/path/boolean/choice/integer), required, default, choices. Parsed from `@param` in `@script` header. |
| **Input delivery** | ✅ Full | CLI flags via `_build_command()`. Env vars via `inject_output_env()`. |
| **Output declaration** | ❌ None | No `@output` convention. No way to declare what variables a script will produce. |
| **Output parsing** | ⚠️ Simple only | `DCP_VAR_KEY=VALUE` convention — string values only. No JSON/object output. |
| **Output format metadata** | ⚠️ Exists | `output_formats` on ScriptMeta — but this describes file output formats (mermaid, json, markdown), NOT variable outputs. |

### 2.4 What Actually Works Today (CDP Test I/O)

| Feature | State | Detail |
|---------|-------|--------|
| **Input declaration** | ⚠️ Loose | `TestSuite.variables: dict[str, str]` — name → default. Untyped. No descriptions. |
| **Input delivery** | ✅ Works | `_resolve_variables()` substitutes `${VAR_NAME}` in step values, selectors, and assertion expectations. |
| **Output capture** | ✅ Works | `capture_text/html/value/attribute/url/computed_style/console` → `captured_value` in result records. |
| **Output naming** | ❌ Ad-hoc | Plan executor uses cleaned CSS selector as variable name. No way to declare "capture X should be named TOKEN". |
| **Output declaration** | ❌ None | No suite-level output metadata. |

---

## 3. The Vision — Complete Picture

### 3.1 What Changes for Each Mode

#### fully_automated — Autonomous Execution

**Before (today)**: Runs all steps, shows results. If a variable is missing, things might fail silently.

**After (this chunk)**:
- **Pre-run validation**: Before starting, the system checks that every step's
  required inputs are satisfied (by plan variables, upstream produces, or
  defaults). If anything is missing → show what's missing and block start.
- **Pre-run view**: Shows input/output wiring diagram — which variables flow
  between which steps. User sees the full data pipeline before clicking Execute.
- **During execution**: Runs autonomously. Variables flow automatically.
  Live view shows variables being produced in real-time.
- **Post-run**: Full I/O trace — which variables were expected, which were
  produced, which were consumed. Any gaps highlighted.

#### semi_automated — User at Decision Points

**Before (today)**: Runs, pauses at checkpoints with "Resume/Skip/Cancel" buttons and maybe a message.

**After (this chunk)**:
- **At checkpoint pause**, the user sees:
  - **What just happened**: Variables produced by preceding steps since last checkpoint.
  - **Accumulated namespace**: All current variable values, editable.
  - **What's coming next**: Next step(s) and what inputs they need.
  - **Missing inputs**: Which required inputs for upcoming steps are NOT in the namespace yet.
  - **Input form**: User can fill in missing values or override existing ones before resuming.
- The checkpoint becomes a **cockpit**: review, adjust, proceed.

#### interactive — User Drives the Pipeline

**Before (today)**: Runs one step, pauses with "Step N completed: passed" + Resume/Skip/Cancel.

**After (this chunk)**:
- **After every step**, the user sees:
  - **Step result**: What happened (passed/failed, duration, exit code or pass/fail counts).
  - **Variables produced**: What this step output, highlighted.
  - **Next step preview**: What the next step is, what it needs.
  - **Input readiness**: Which of the next step's inputs are ready (in namespace) vs missing.
  - **Editable namespace**: User can add, change, remove variables.
  - **Input form for next step**: Pre-filled with namespace values and defaults, editable.
- The user is **building the data pipeline live**, inspecting intermediate results and deciding what to feed forward.

### 3.2 Output Shapes

Two output shapes, for both scripts and tests:

| Shape | Convention | Example | Storage |
|-------|-----------|---------|---------|
| **Simple value** | `DCP_VAR_KEY=VALUE` (scripts) or named capture with `export_as` (tests) | `DEPLOY_PATH=/opt/v2` | `str` in namespace |
| **Complex object** | `DCP_JSON_KEY={...}` (scripts) or structured capture (tests) | `AUDIT_RESULT={"issues":0,"status":"ok"}` | `Any` (parsed JSON) in namespace |

### 3.3 Input Handling

For both scripts and tests, inputs work the same way conceptually:

| Priority | Source | Description |
|----------|--------|-------------|
| 1 | **Explicit step override** | `script_params` / `suite_variables` on PlanStep — user typed a specific value |
| 2 | **Namespace variable** | Previous step produced a variable matching this input's name |
| 3 | **Declared default** | `ScriptParameter.default` / `SuiteVariable.default` — from the script/test definition |
| 4 | **Missing** | Input not satisfied — behavior depends on mode |

When an input is missing:
- **fully_automated**: Block start (pre-run validation) or fail the step at runtime.
- **semi_automated**: User fills it at the next checkpoint before the step runs.
- **interactive**: User fills it at the pause point before the step runs.

### 3.4 Partial I/O

Not every step has I/O. The system supports:

| Case | Example | Behavior |
|------|---------|----------|
| **Full I/O** | Script with declared params AND outputs | Inputs pre-filled, outputs flow to namespace |
| **Inputs only** | CDP test with variables but no named captures | Variables consumed from namespace, nothing produced |
| **Outputs only** | Script that produces DCP_VAR_ lines but takes no params | Nothing consumed, variables produced |
| **No I/O** | Checkpoint step, or a script that takes no params and produces no vars | Pure execution, no variable interaction |

---

## 4. Architecture — What Changes

### 4.1 New Model: ScriptOutput

```python
@dataclass
class ScriptOutput:
    """A declared output variable for a script."""
    name: str                       # Variable name (e.g., "DEPLOY_PATH")
    type: str = "string"            # "string" | "json" | "boolean" | "integer"
    description: str = ""           # Help text
```

**Where**: `src/core/services/scripts/models.py`
**Added to**: `ScriptMeta.outputs: list[ScriptOutput]`

**Script header convention**:
```python
"""
@script
name: Docker Audit

@param target: string = production | Target environment
@output DEPLOY_PATH: string | Resolved deployment path
@output AUDIT_RESULT: json | Full audit result as JSON
"""
```

### 4.2 New Model: SuiteVariable

```python
@dataclass
class SuiteVariable:
    """A declared variable for a CDP test suite."""
    name: str                       # Variable name (e.g., "BASE_URL")
    type: str = "string"            # "string" | "secret" | "url" | "integer"
    description: str = ""           # Help text
    default: str = ""               # Default value
    required: bool = False          # Must be provided
```

**Where**: `src/core/services/cdp_test/models.py`
**Added to**: `TestSuite.variable_defs: list[SuiteVariable]`
**Note**: Existing `TestSuite.variables: dict[str, str]` stays for runtime resolution. `variable_defs` is enrichment for the editor/planner. Derived from `variables` dict when `variable_defs` is empty (backward compat).

### 4.3 New Field: TestStep.export_as

```python
export_as: str = ""     # If set, captured value is exported with this name
                        # e.g., export_as="AUTH_TOKEN"
```

**Where**: `src/core/services/cdp_test/models.py` → `TestStep`
**Effect in replayer**: Result record gets `export_name: "AUTH_TOKEN"` alongside `captured_value`.
**Effect in plan executor**: `_execute_cdp_test_step()` maps `captured_value` → `produced["AUTH_TOKEN"]` instead of using cleaned CSS selector.

### 4.4 Enhanced Output: TestSuite.outputs

```python
outputs: dict[str, str] = field(default_factory=dict)
    # Declared outputs: name → description
    # e.g., {"AUTH_TOKEN": "Bearer token from login"}
```

**Where**: `src/core/services/cdp_test/models.py` → `TestSuite`
**Purpose**: Tells the plan editor what this suite can produce.

### 4.5 Type Change: variables_produced → dict[str, Any]

| Model | Change |
|-------|--------|
| `StepResult.variables_produced` | `dict[str, str]` → `dict[str, Any]` |
| `PlanRunResult.variables` | `dict[str, str]` → `dict[str, Any]` |
| `ExecutionPlan.variables` | `dict[str, str]` → `dict[str, Any]` |

### 4.6 Enhanced Parsing: DCP_JSON_ prefix

`_extract_variables_from_lines()` extended:
- `DCP_VAR_KEY=VALUE` → simple string (existing)
- `DCP_JSON_KEY={...}` → parsed as JSON object (new)

### 4.7 UI: Mode-Aware Pause Interaction

The `plan:paused` event already sends `variables: namespace` but the UI
ignores it. The pause UI needs a complete rethink per mode:

**Interactive pause view** (shown after every step):
```
┌─────────────────────────────────────────────────────┐
│ ✅ Step 2: "Login Flow" completed (passed, 3.2s)    │
│                                                     │
│ 📤 Produced Variables:                              │
│   AUTH_TOKEN = abc123def456                          │
│   USER_ID = 42                                      │
│                                                     │
│ ────────────────────────────────────────────────     │
│                                                     │
│ ⏭ Next Up: Step 3 "Verify Deploy" (script)          │
│                                                     │
│ 📥 Required Inputs:                                 │
│   token   ← AUTH_TOKEN ✅ (from namespace)          │
│   path    ← DEPLOY_PATH ✅ (from namespace)         │
│   verbose ← (default: false) ☑️                     │
│                                                     │
│ 📋 Current Namespace:                               │
│   ENV_NAME = production                             │
│   DEPLOY_PATH = /opt/v2        [edit]               │
│   AUTH_TOKEN = abc123def456    [edit]                │
│   USER_ID = 42                 [edit]               │
│   + Add variable                                    │
│                                                     │
│ [▶ Resume]  [⏭ Skip]  [⏹ Cancel]                   │
└─────────────────────────────────────────────────────┘
```

**Semi-automated checkpoint view** (shown at checkpoints):
```
┌─────────────────────────────────────────────────────┐
│ ⏸ Checkpoint: "Review before deployment"            │
│                                                     │
│ 📊 Progress: 3/7 steps completed                    │
│                                                     │
│ 📤 Variables Since Last Checkpoint:                  │
│   Step 1 "Audit Docker" → DEPLOY_PATH=/opt/v2       │
│   Step 2 "Login Flow"   → AUTH_TOKEN=abc123          │
│                                                     │
│ ────────────────────────────────────────────────     │
│                                                     │
│ ⏭ Upcoming Steps (until next checkpoint):           │
│   Step 4: "Deploy Config" — needs: DEPLOY_PATH ✅   │
│   Step 5: "Verify Health" — needs: BASE_URL ❌      │
│                                                     │
│ ❌ Missing Inputs:                                   │
│   BASE_URL for Step 5: [________________] ← fill in │
│                                                     │
│ 📋 Full Namespace: (12 variables) [expand]           │
│                                                     │
│ [▶ Resume]  [⏭ Skip Next]  [⏹ Cancel]              │
└─────────────────────────────────────────────────────┘
```

**Fully automated pre-run validation** (shown before Execute):
```
┌─────────────────────────────────────────────────────┐
│ ▶ Run Plan: "Full Deploy Pipeline"                  │
│   Mode: Fully Automated · 7 steps                   │
│                                                     │
│ 🔗 I/O Wiring:                                      │
│   Step 1 → DEPLOY_PATH, AUDIT_RESULT                │
│                ↓                                    │
│   Step 2 → AUTH_TOKEN, USER_ID                       │
│                ↓                                    │
│   Step 3 ← DEPLOY_PATH, AUTH_TOKEN                   │
│         → VERIFY_OK                                 │
│                ↓                                    │
│   Step 4 ← VERIFY_OK (conditional)                   │
│                                                     │
│ ✅ All required inputs satisfied                     │
│   — or —                                            │
│ ❌ 2 inputs cannot be satisfied:                     │
│   Step 5 needs BASE_URL (no producer, no default)    │
│   Step 6 needs DB_HOST (no producer, no default)     │
│   → Fill them in Initial Variables or switch mode    │
│                                                     │
│ [← Back] [▶ Execute]                                │
└─────────────────────────────────────────────────────┘
```

### 4.8 UI: Smart Step Editor

The step editor in the plan editor (design time) becomes I/O-aware:

**Script step**: Fetch `ScriptMeta` via API → render each declared parameter
as a proper form field (type-appropriate input) with default pre-filled.
Show declared outputs below. Each input offers a dropdown of available
namespace variables from prior steps.

**CDP test step**: Load `TestSuite` → render declared `variable_defs` as
proper form fields. Show declared `outputs`. Same namespace variable dropdown.

**Auto-populate**: `produces` auto-filled from declared outputs. `consumes`
auto-filled from declared required inputs that match upstream produces.

---

## 5. Sub-Chunk Breakdown

### Chunk 6a: Script Output Declarations

**Goal**: Scripts can declare what variables they output.

**Scope**: Backend only. No UI changes (except API response).

**Changes**:
1. `ScriptOutput` dataclass in `models.py`
2. `outputs: list[ScriptOutput]` on `ScriptMeta`
3. `_parse_output_line()` in `registry.py` (same pattern as `_parse_param_line()`)
4. Parse `@output` lines in `_parse_header_fields()`
5. Include `outputs` in `GET /scripts/info/<id>` response
6. Include `outputs` count in script list/summary

**Risk**: Low — additive, non-breaking. Existing scripts without `@output`
have empty `outputs` list.

**Test**: Add `@output` lines to a template script → verify API returns them.

---

### Chunk 6b: CDP Test Output Declarations

**Goal**: CDP test suites can declare inputs with types and outputs with names.

**Scope**: Models, replayer output tagging, suite editor UI.

**Changes**:
1. `SuiteVariable` dataclass in `cdp_test/models.py`
2. `variable_defs: list[SuiteVariable]` on `TestSuite`
3. `outputs: dict[str, str]` on `TestSuite`
4. `export_as: str` on `TestStep`
5. Replayer: include `export_name` in result_record when `export_as` is set
6. Plan executor: use `export_as` names for variable mapping (instead of
   cleaned CSS selector)
7. Suite serialization: save/load new fields
8. Suite editor UI: add `export_as` field to capture step editing
9. Suite editor UI: add `variable_defs` editing section
10. Suite editor UI: add `outputs` editing section
11. Suite API responses: include new metadata

**Risk**: Medium — touches replayer, models, storage, UI, and plan executor.
Must maintain backward compatibility (suites without these fields work as before).

**Test**: Create suite with `export_as` on a capture step → run in plan →
verify the named variable appears in namespace (not the selector name).

---

### Chunk 6c: Enhanced Output Parsing

**Goal**: Scripts can output complex JSON objects; namespace supports mixed types.

**Scope**: Parser, type annotations, serialization.

**Changes**:
1. `_extract_variables_from_lines()` extended for `DCP_JSON_` prefix
2. JSON parsing for `DCP_JSON_KEY={...}` lines
3. `variables_produced` type: `dict[str, str]` → `dict[str, Any]`
4. `PlanRunResult.variables` type: `dict[str, str]` → `dict[str, Any]`
5. `ExecutionPlan.variables` type: `dict[str, str]` → `dict[str, Any]`
6. `StepResult.to_dict()` / `from_dict()` handle Any values
7. `${VAR}` resolution: JSON objects auto-stringify in string context

**Risk**: Medium — type ripple through serialization, UI rendering, variable
resolution. Must test that existing string-only flows work unchanged.

**Test**: Script outputs `DCP_JSON_RESULT={"ok":true}` → verify namespace
has parsed dict, not raw string.

---

### Chunk 6d: Smart Plan Editor (Design-Time I/O)

**Goal**: The plan step editor understands what each step needs and produces.

**Scope**: Plan editor UI only.

**Changes**:
1. Script step: fetch ScriptMeta → render declared params as typed form fields
   with defaults pre-filled
2. CDP test step: load TestSuite → render variable_defs as typed form fields
3. Each input field: dropdown of available namespace variables from prior steps'
   declared outputs
4. Auto-populate `produces` from declared outputs
5. Auto-populate `consumes` from required inputs matching upstream produces
6. Visual indicator on step list: badges showing produced/consumed variables
7. Validation: warn (not block) when consumed variable has no producer upstream

**Risk**: High — most complex UI work. Needs API calls to fetch script/suite
metadata. Must gracefully handle scripts/suites that don't have declarations.

**Dependencies**: Needs 6a and 6b (for metadata to exist).

---

### Chunk 6e: Fully Automated Pre-Run Validation

**Goal**: Before starting a fully_automated plan, validate that all I/O is
wired correctly. Show the data pipeline to the user.

**Scope**: Pre-run confirmation UI, validation logic.

**Changes**:
1. Pre-run view: show I/O wiring (which variables flow between steps)
2. Input satisfaction check: walk steps, track namespace, verify each step's
   required inputs are satisfied by that point
3. Show missing inputs with clear diagnostics
4. Block execution if required inputs are missing (in fully_automated mode)
5. Suggest: fill in Initial Variables or switch to semi_automated/interactive

**Risk**: Medium — needs step metadata (from 6d's API calls). Validation
logic must match execution logic exactly.

**Dependencies**: Needs 6d (for metadata fetching pattern).

---

### Chunk 6f: Interactive Mode I/O UX

**Goal**: After every step in interactive mode, show a rich pause view
with produced variables, next step preview, input readiness, and editable
namespace.

**Scope**: Execution UI — pause view rework.

**Changes**:
1. Parse `plan:paused` event data (already has `variables: namespace`)
2. Show variables produced by the just-completed step
3. Show next step name, type, declared inputs
4. Show input readiness: which inputs are in namespace ✅ vs missing ❌
5. Editable namespace: click to edit any value, add new variables
6. Input form for next step: pre-filled from namespace + defaults
7. Resume sends updated namespace to backend
8. Backend: accept namespace updates on resume

**Risk**: High — requires backend enhancement (resume endpoint accepting
updated variables), and significant UI work for the interactive pause view.

**Sub-chunks** (if needed):
- 6f.1: Read-only pause view (show produced vars + next step preview)
- 6f.2: Editable namespace (edit/add/remove variables at pause)
- 6f.3: Input form for next step (pre-filled, editable)

**Dependencies**: Needs 6a + 6b (for step metadata). Needs 6c if
complex objects are to be displayed properly.

---

### Chunk 6g: Semi-Automated Checkpoint I/O UX

**Goal**: At checkpoint pauses, show accumulated outputs since last checkpoint,
upcoming step requirements, and let user fill missing inputs.

**Scope**: Execution UI — checkpoint view rework.

**Changes**:
1. Track "changed since last checkpoint" in namespace
2. Show variables produced since last checkpoint (per-step attribution)
3. Show upcoming steps until next checkpoint with their input requirements
4. Highlight missing inputs for upcoming steps
5. Input form for missing values
6. Editable namespace with full visibility
7. Resume sends updated namespace

**Risk**: Medium — similar to 6f but scoped to checkpoint steps.

**Dependencies**: Needs 6f (shared infrastructure for editable namespace
and backend resume-with-updates).

---

### Chunk 6h: Complex Output Display

**Goal**: JSON objects in namespace are rendered with expandable viewers
instead of raw `[object Object]`.

**Scope**: UI only — namespace display, drill-down, result view.

**Changes**:
1. Detect object values in namespace display
2. Render with expandable JSON tree viewer
3. Step drill-down: show complex outputs with proper formatting
4. Result view: variable trace handles mixed string/object values
5. Interactive pause: complex values displayed properly in editable view

**Risk**: Low — UI-only enhancement.

**Dependencies**: Needs 6c (for objects to exist in namespace).

---

## 6. Execution Order

```
6a ─── Script Output Declarations
  ↓
6b ─── CDP Test Output Declarations
  ↓
6c ─── Enhanced Output Parsing (complex objects)
  ↓
6d ─── Smart Plan Editor (design-time I/O)
  ↓
6e ─── Fully Automated Pre-Run Validation
  ↓
6f ─── Interactive Mode I/O UX ←── THE BIG ONE
  ↓
6g ─── Semi-Automated Checkpoint I/O UX
  ↓
6h ─── Complex Output Display
```

**Dependency graph**:
```
6a ─┬─── 6d ─── 6e
    │      │
6b ─┘      └─── 6f ─── 6g
                  │
6c ──────────── 6h
```

**6a + 6b** are independent foundations (can be parallel).
**6c** is independent of 6a/6b (parser/type work).
**6d** needs 6a + 6b (metadata must exist).
**6e** needs 6d (pre-run view uses metadata fetching).
**6f** needs 6d (pause view needs step metadata) — largest chunk.
**6g** builds on 6f infrastructure.
**6h** needs 6c (needs objects to exist to display them).

---

## 7. Data Flow — Complete Picture After Evolution

### 7.1 Design Time (Plan Editor)

```
User adds script step "audit-docker"
  → UI fetches ScriptMeta via API
  → Renders declared @param fields with proper types and defaults
  → Renders declared @output list
  → User maps inputs from namespace dropdown or types values
  → User sees: step will produce DEPLOY_PATH, AUDIT_RESULT
  → produces auto-populated, consumes auto-populated

User adds cdp_test step "login-flow"
  → UI loads TestSuite
  → Renders declared variable_defs with defaults
  → Renders declared outputs
  → User maps BASE_URL ← "${DEPLOY_PATH}/app" (from step 1)
  → produces auto-populated: AUTH_TOKEN, PAGE_TITLE
  → consumes auto-populated: DEPLOY_PATH
```

### 7.2 Run Time — Fully Automated

```
Pre-run validation:
  Walk steps 1 → N, track what would be in namespace
  Step 1: needs target (default: "production") ✅, scope ❌ no default, no producer
  → Block: "Step 1 needs 'scope' — add to Initial Variables"

After fixing:
  Execute → runs all steps → vars flow automatically → done
```

### 7.3 Run Time — Interactive

```
Step 1 runs → passes → pauses
  Pause view shows:
    Produced: DEPLOY_PATH=/opt/v2, AUDIT_RESULT={...}
    Next: Step 2 "Login Flow"
    Needs: BASE_URL ← not in namespace ❌
           USERNAME ← not in namespace ❌, default: "admin"
    User fills: BASE_URL = "http://localhost:3000"
    User accepts USERNAME default
  → Resume (namespace updated with user edits)

Step 2 runs → passes → pauses
  Pause view shows:
    Produced: AUTH_TOKEN=abc123
    Next: Step 3 "Verify Deploy"
    Needs: token ← AUTH_TOKEN ✅
           path ← DEPLOY_PATH ✅
  → Resume
```

### 7.4 Run Time — Semi-Automated

```
Steps 1-3 run automatically → checkpoint step → pauses
  Checkpoint view shows:
    Since last checkpoint:
      Step 1 → DEPLOY_PATH=/opt/v2
      Step 2 → AUTH_TOKEN=abc123
      Step 3 → VERIFY_OK=true
    Upcoming (until next checkpoint):
      Step 4: "Deploy Config" — needs DEPLOY_PATH ✅, VERIFY_OK ✅
      Step 5: "Health Check" — needs BASE_URL ❌
    User fills BASE_URL
  → Resume → Steps 4-5 run automatically
```

---

## 8. Backward Compatibility

| Concern | Mitigation |
|---------|-----------|
| Scripts without `@output` | `outputs` defaults to `[]`. DCP_VAR_ parsing unchanged. Plan editor shows "No declared outputs." |
| Suites without `variable_defs` | `variable_defs` defaults to `[]`. Editor falls back to `variables` dict for display. |
| Suites without `export_as` | Steps without `export_as` use current behavior (selector-based naming). |
| Suites without `outputs` | `outputs` defaults to `{}`. |
| `dict[str, str]` → `dict[str, Any]` | Existing string values work unchanged. JSON serialization handles both. |
| Plans saved before this evolution | All new fields have defaults. Old plans load and run unchanged. |
| Interactive/semi_automated without I/O metadata | Pause view gracefully shows "No declared inputs/outputs" and falls back to raw namespace display. |

---

## 9. What We Do NOT Build (Yet)

| Not in scope | Why |
|-------------|-----|
| Type coercion/validation at runtime | Types are advisory for the editor. Enforcement is a future evolution. |
| Conditional branching based on output values | Separate concern (Chunk 5's conditional step type). |
| Output streaming (real-time variable updates during step) | Variables extracted after step completes, not during. |
| Cross-plan variable sharing | Each plan has its own namespace. |
| JSON Schema validation for complex outputs | Too heavyweight for first iteration. |
| Visual DAG/pipeline editor | Graph-based editing is a future evolution. Current step list is sufficient. |
| Auto-input-mapping by name matching | User explicitly wires inputs. Auto-suggest via dropdown, but not auto-connect. |

---

## 10. Open Design Questions

### Q1: variables_produced type — single dict or split?

**Option A**: `dict[str, Any]` — single namespace with mixed types.
**Option B**: Separate `strings_produced` and `objects_produced`.
**Recommendation**: Option A. One namespace. JSON handles mixed types.

### Q2: How does `${VAR}` work when value is a JSON object?

**Option A**: Stringifies the object when embedded in a string. Raw object
available in conditional expressions.
**Option B**: `${VAR}` always stringifies. `${VAR.key}` for nested access.
**Recommendation**: Option A for first iteration. Nested access is a future
enhancement.

### Q3: Should `@output` be required for plan I/O?

**Option A**: Optional — undeclared outputs still work via DCP_VAR_ at runtime.
**Option B**: Required for plan integration.
**Recommendation**: Option A. Backward compat. Undeclared outputs work; they
just don't appear in editor auto-suggest.

### Q4: How do namespace edits reach the backend on resume?

**Option A**: Resume endpoint accepts `variables_update: dict` → merged into namespace.
**Option B**: Resume endpoint accepts full replacement `namespace: dict`.
**Recommendation**: Option A. Merge preserves system-set variables.

### Q5: Where does `SuiteVariable` live vs `TestSuite.variables`?

**Option A**: Replace `variables` with `variable_defs`.
**Option B**: Keep both — `variables` for runtime, `variable_defs` for metadata.
**Recommendation**: Option B. `variables` is used everywhere in the replayer.
`variable_defs` is enrichment for the editor.

---

## 11. Cross-References

| Reference | Location |
|-----------|----------|
| Script Models | `src/core/services/scripts/models.py` (151 lines) |
| Script Registry | `src/core/services/scripts/registry.py` (564 lines) |
| Script Executor | `src/core/services/scripts/executor.py` (305 lines) |
| Plan Executor | `src/core/services/scripts/plan_executor.py` (915 lines) |
| Plan Models | `src/core/services/scripts/plans.py` (410 lines) |
| CDP Test Models | `src/core/services/cdp_test/models.py` (657 lines) |
| CDP Test Replayer | `src/core/services/cdp_test/replayer.py` (2801 lines) |
| Plans UI | `src/ui/web/templates/scripts/integrations/_plans.html` (1683 lines) |
| Script Info API | `src/ui/web/routes/scripts/registry.py` (268 lines) |
| Chunk 5 Plan | `.agent/plans/scripts-system/chunk-5-execution-plans.md` |
| M7 Master Plan | `.agent/plans/scripts-system/scripts-system-M7-plans.md` |
