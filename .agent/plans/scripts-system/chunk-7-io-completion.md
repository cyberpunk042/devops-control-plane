# Chunk 7: I/O Completion — Making It Real

> **Status**: Draft — Awaiting Review
> **Created**: 2026-03-09
> **Parent**: `chunk-6-plan-io-evolution.md` (infrastructure)
> **Purpose**: Bridge the gap between "infrastructure exists" and "end-to-end testable"

---

## 0. Why This Exists

Chunk 6 built the plan-level I/O engine — namespace chaining, SSE events with
variable data, pre-run validation, interactive pause with editable vars, complex
value display. But all of that infrastructure has **nothing to consume** because:

- Scripts declare `@param` but never declare `@output` and never print `DCP_VAR_`
- CDP test suites have model fields for I/O but zero UI to define any of it
- The plan execution UI is functional but basic, not mode-aware, not polished

This document organizes the remaining work into **three distinct domains**
that converge at the plan executor. Each domain is scoped independently.

---

## 1. Domain Map

```
┌─────────────────────────────────┐
│        DOMAIN A: SCRIPTS        │
│  @output declarations           │
│  DCP_VAR_ print statements      │
│  Script header conventions      │
│  Verification via script run    │
└────────────┬────────────────────┘
             │ Feeds
             ▼
┌─────────────────────────────────┐
│      DOMAIN C: PLAN SYSTEM      │
│  Execution modal (3 modes)      │
│  Step results & drill-down      │◄──── Consumes I/O from both
│  Post-run result view           │
│  Wiring verification            │
└─────────────────────────────────┘
             ▲ Feeds
             │
┌─────────────────────────────────┐
│    DOMAIN B: CDP TEST I/O       │
│  Step-level input bindings      │
│  Step-level output exports      │
│  Suite-level I/O summary        │
│  Target-site experience         │
│  Admin-panel step editor        │
└─────────────────────────────────┘
```

Each domain has its own sub-chunks, its own scope, its own verification.
They converge at the plan executor but they are NOT plan features — they are
features of their own systems that happen to feed into plans.

---

# DOMAIN A: Script I/O

## A.1 Current State

| Aspect | Status | Evidence |
|--------|--------|----------|
| `@param` declarations | ✅ 5 scripts, 6-10 params each | `code_hygiene` 8, `class_diagrams` 8, `route_quality` 6, `api_catalog` 7, `data_layer_leaks` 9 |
| `@param` parsing | ✅ Works | `registry.py` → `_parse_param_line()` → `ScriptParameter` |
| API serves params | ✅ Works | `/api/scripts/info/<id>` returns `parameters[]` with name, type, default, choices |
| `@output` declaration format | ✅ Defined | `registry.py` → `_parse_output_line()` → `ScriptOutput(name, type, description)` |
| Scripts with `@output` | ❌ Zero | No script file has `@output` lines |
| `DCP_VAR_` capture in executor | ✅ Code exists | `plan_executor.py` lines 284-310 parse stdout for `DCP_VAR_*=` |
| `DCP_JSON_` capture in executor | ✅ Code exists | `plan_executor.py` lines 89-95 parse `DCP_JSON_*=` as JSON |
| Scripts printing `DCP_VAR_` | ❌ Zero | `grep -r "DCP_VAR_" script_templates/` = empty |

## A.2 Work Items

### A.2.1 — Add `@output` declarations to all 5 scripts

Each script already produces meaningful data (reports, counts, paths).
Declare those outputs in the script header. This is descriptive — it tells
the system what the script WILL produce. The declaration does NOT make the
script produce it; the print statement does (A.2.2).

**Per script — analyze the actual code, identify what meaningful values are
produced, and add `@output` lines for each.**

Concrete analysis needed per script:
- `code_hygiene.py`: What does it compute? (init file count, stale doc count,
  report path). Add `@output` for each computable value.
- `route_quality.py`: Total routes, coverage metrics, report path.
- `class_diagrams.py`: Total classes, module count, diagram path.
- `api_catalog.py`: Endpoint count, catalog path.
- `data_layer_leaks.py`: Total leaks, severity breakdown, report path.

**Rule**: Read the FULL script before deciding outputs. Don't guess.

### A.2.2 — Add `DCP_VAR_` / `DCP_JSON_` print statements

At the end of each script's main function (after it has computed and written
its report), print the output values using the established convention:

```python
# Simple values
print(f"DCP_VAR_REPORT_PATH={output_path}")
print(f"DCP_VAR_TOTAL_ROUTES={total_count}")

# Structured data
import json
print(f"DCP_JSON_RESULT={json.dumps(result_dict)}")
```

**Rule**: Only print values that exist. Guard with `if` checks.
**Rule**: The print names must match the `@output` declaration names exactly.

### A.2.3 — Verification

For each modified script:
1. Run it via the normal script runner (not plan executor)
2. Confirm `DCP_VAR_` lines appear in stdout
3. Call `/api/scripts/info/<id>` and confirm `outputs[]` is populated
4. Syntax-check the modified file

**Files**: 5 files in `src/core/data/script_templates/`
**Risk**: Low — adding declarations and print statements to working code
**Effort**: Small

---

# DOMAIN B: CDP Test I/O

This is the largest domain. The CDP test system today records steps and replays
them. What's missing is the ability to parameterize steps (inputs) and export
step results (outputs). This happens in **three surfaces**:

1. **Target site** — while recording/replaying on the actual website
2. **Admin panel step editor** — when editing a recorded step
3. **Admin panel suite level** — the aggregate view of all I/O for the suite

## B.1 Current State

### B.1.1 — Model Layer

| Aspect | Status | Location |
|--------|--------|----------|
| `TestStep.export_as` | ✅ Field exists | `models.py` line 333 — capture step → named export |
| `TestStep.value` | ✅ Used for type/navigate/select | Holds the recorded value (hardcoded text/URL) |
| `TestSuite.variables` | ✅ Dict exists | `models.py` line 509 — name → default value |
| `TestSuite.variable_defs` | ✅ Model exists | `models.py` line 512 — typed `SuiteVariable` list |
| `SuiteVariable` | ✅ Dataclass exists | `models.py` line 425 — name, type, description, default, required |
| `TestSuite.outputs` | ✅ Dict exists | `models.py` line 518 — name → description |
| Replayer `_resolve_variables()` | ✅ Works | `replayer.py` line 80 — expands `${VAR_NAME}` in step values |
| Replayer reads `export_as` | ✅ Works | `replayer.py` line 2425 — writes `export_name` to result |
| Plan executor processes `export_name` | ✅ Works | `plan_executor.py` line 401 — feeds into `produced` dict |

**Summary**: The entire backend pipeline exists. A step COULD have `export_as`,
the replayer WOULD use it, the plan executor WOULD capture it. But nobody sets
these fields because there's no UI.

### B.1.2 — Step Editor UI

| Aspect | Status | Location |
|--------|--------|----------|
| Edit step action | ✅ | `_cdpTestEditStep()` → `_cdpTestBuildEditForm()` |
| Edit selector | ✅ | Dynamic fields per action type |
| Edit value (type/navigate/select) | ✅ | `_cdpTestBuildDynamicFields()` line 1785-1807 |
| Edit `variable_name` (for captures) | ✅ | Line 1822 — "Store as variable" field |
| Edit `export_as` (named export) | ❌ No UI | Field exists on model but not in form |
| Mark value as variable-bound input | ❌ No UI | No way to say "this value comes from `${LOGIN_EMAIL}`" |
| Assert expected as variable-bound | ❌ No UI | Expected value can't reference `${VAR}` in editor |

### B.1.3 — Suite Editor UI

| Aspect | Status | Location |
|--------|--------|----------|
| Suite name, desc, URL, category | ✅ | `_cdpTestOpenValidation()` line 1357-1367 |
| Steps list with edit | ✅ | Line 1378-1382, `_cdpTestValStepRow()` |
| Save suite | ✅ | `_cdpTestSaveSuite()` — sends name/desc/url/cat/steps |
| `variable_defs` in save payload | ❌ | Not included |
| `outputs` in save payload | ❌ | Not included |
| I/O summary panel | ❌ | No way to see or manage the suite's aggregate I/O |

### B.1.4 — Target Site Experience

| Aspect | Status |
|--------|--------|
| Recording steps on target site | ✅ Works |
| Marking a field as variable input during recording | ❌ |
| Marking a capture as named export during recording | ❌ |
| Variable substitution during replay | ✅ `_resolve_variables()` works if variables are set |

## B.2 Work Items

### B.2.1 — Step Editor: Input Variable Binding

**The problem**: When you record a `type` step, the value is hardcoded
(e.g., "admin@test.com"). When you record a `navigate` step, the URL is
hardcoded. There's no way to say "at runtime, use variable `LOGIN_EMAIL`
instead of this recorded value."

**The solution**: In the step editor, for actions that have a `value` field
(`type`, `navigate`, `select`, `keypress`, `inject_js`) AND for assertion
steps with expected values:

1. Add a toggle/field next to the value: **"Bind to variable"**
2. When toggled on, show a text field for the variable name (e.g., `LOGIN_EMAIL`)
3. The original recorded value becomes the **default** for that variable
4. When saved, the step's `value` changes to `${LOGIN_EMAIL}` syntax
5. The original value is preserved as the default in the suite-level
   `variable_defs` / `variables` dict

**How it looks in the step editor**:

```
┌─────────────────────────────────────────┐
│ ⌨️ Edit Step 3: type                    │
│                                         │
│ CSS Selector: #email-input              │
│                                         │
│ Text to type: admin@test.com            │
│ ☐ Bind to variable                      │
│   Variable name: [ LOGIN_EMAIL ]        │
│   (Default: admin@test.com)             │
│                                         │
│ Timeout (ms): [5000]                    │
│ ☐ Optional                              │
│ Description: [___________________]      │
│                                         │
│            [Cancel]  [✅ Apply]          │
└─────────────────────────────────────────┘
```

When "Bind to variable" is checked:
- The value field becomes **read-only** (shows `${LOGIN_EMAIL}`)
- The variable name field becomes active
- The recorded value is stored as the default

**UI changes to `_cdpTestBuildDynamicFields()`**:
- For `type`, `navigate`, `select`, `keypress`, `inject_js` actions:
  Add a checkbox + variable name field below the value field
- Detect if current value already contains `${...}` → pre-check the toggle
- For `assert` action: same treatment on the "Expected Value" field

**UI changes to `_cdpTestApplyStepEdit()`**:
- If toggle is checked, set `step.value = "${VAR_NAME}"` and record the
  original value separately

**Model consideration**: `TestStep` doesn't have an `input_from` field.
We have two options:
- **Option A**: Use convention — step value IS `${VAR_NAME}`, the replayer
  already handles this via `_resolve_variables()`. No model change needed.
  The suite's `variables`/`variable_defs` dict stores the default.
- **Option B**: Add `input_from: str = ""` field on TestStep for explicit
  binding, keeping value as the default.

Option A is simpler and the replayer already supports it.
Option B is cleaner for the editor but adds a model field.

**Recommendation**: Start with Option A (convention-based, already works
in the replayer). The editor detects `${...}` in value to show the toggle.
Evaluate Option B if A feels fragile.

### B.2.2 — Step Editor: Output Export (export_as)

**The problem**: For `capture_*` steps, there's a "Store as variable" field
(`variable_name`) but no `export_as` field. `variable_name` is for
internal cross-step reference within the suite. `export_as` is for
exporting the captured value to the **plan namespace** (or to the
suite's declared outputs for external consumers).

**The solution**: Add an `export_as` field in the step editor for all
`capture_*` actions and for `assert` steps (which also capture actual values):

```
┌─────────────────────────────────────────┐
│ 📋 Edit Step 7: capture_text           │
│                                         │
│ CSS Selector: .auth-token-display       │
│                                         │
│ Store as variable (internal): [my_tok]  │
│ Export as named output: [AUTH_TOKEN]     │
│   ↳ This value will be available to     │
│     plan steps and external consumers   │
│                                         │
│ Timeout (ms): [5000]                    │
│ ☐ Optional                              │
│ Description: [Capture auth token]       │
│                                         │
│            [Cancel]  [✅ Apply]          │
└─────────────────────────────────────────┘
```

**UI changes to `_cdpTestBuildDynamicFields()`**:
- For `isCapture` block (line 1820-1823): add `export_as` field after
  `variable_name`
- For `assert` steps: optionally add `export_as` for the assertion's
  actual value

**UI changes to `_cdpTestApplyStepEdit()`**:
- Read `mf-cdp-edit-export-as` and save to `step.export_as`

**Model**: `TestStep.export_as` already exists. No model change needed.

### B.2.3 — Suite-Level I/O Summary Panel

**The problem**: After annotating individual steps with input bindings
and output exports, there's no way to see the aggregate I/O picture
for the suite. A user needs to see "this suite requires these inputs
and produces these outputs" at a glance.

**The solution**: Add a collapsible "📥📤 I/O Configuration" section to
the suite validation view. This section has two modes:

1. **Auto-derived mode** (recommended): Scan all steps, collect all
   `${VAR}` references as inputs and all `export_as` values as outputs.
   Display them as a summary table. The user can edit descriptions and
   mark required/optional.

2. **Manual mode**: Let the user add variables that aren't bound to any
   specific step (e.g., a `BASE_URL` that gets resolved in multiple
   steps' selectors, or a configuration flag).

**How it looks**:

```
┌────────────────────────────────────────────────┐
│ 📥📤 I/O Configuration ▾                       │
│                                                │
│ 📥 Input Variables (3)                         │
│ ┌──────────────────────────────────────────┐   │
│ │ Name         │ Type   │ Default    │ Req │   │
│ │ LOGIN_EMAIL  │ string │ admin@t... │ ☑   │   │
│ │ LOGIN_PASS   │ secret │ ********   │ ☑   │   │
│ │ BASE_URL     │ url    │ http://... │ ☐   │   │
│ │                [+ Add Variable]          │   │
│ └──────────────────────────────────────────┘   │
│ Auto-detected from steps: LOGIN_EMAIL (step 3),│
│ LOGIN_PASS (step 4)                            │
│                                                │
│ 📤 Declared Outputs (1)                        │
│ ┌──────────────────────────────────────────┐   │
│ │ Name        │ Source       │ Description │   │
│ │ AUTH_TOKEN   │ Step 7      │ Bearer tok  │   │
│ │                [+ Add Output]            │   │
│ └──────────────────────────────────────────┘   │
│ Auto-detected from steps: AUTH_TOKEN (step 7)  │
└────────────────────────────────────────────────┘
```

**The auto-detect logic**:
```javascript
function _cdpTestAutoDetectIO(steps) {
    const inputs = {};   // name → { default, step_indices: [] }
    const outputs = {};  // name → { step_index, description }

    for (let i = 0; i < steps.length; i++) {
        const s = steps[i];
        // Detect ${VAR} in value, selector, etc.
        const varRefs = (s.value || '').match(/\$\{(\w+)\}/g) || [];
        for (const ref of varRefs) {
            const name = ref.slice(2, -1);
            if (!inputs[name]) inputs[name] = { default: '', step_indices: [] };
            inputs[name].step_indices.push(i);
        }
        // Detect export_as
        if (s.export_as) {
            outputs[s.export_as] = { step_index: i, description: s.description || '' };
        }
    }
    return { inputs, outputs };
}
```

**The user can also add manual entries** — variables not derived from steps.
For example, `BASE_URL` might be used in multiple step selectors or injected
JS code, and the user wants to declare it formally.

**Save behavior**: `_cdpTestSaveSuite()` collects the I/O panel data and
includes `variable_defs` and `outputs` in the save payload.

### B.2.4 — Save Route Update

**The problem**: `_cdpTestSaveSuite()` currently sends only
`{name, description, target_url, category, steps}`. It doesn't include
`variable_defs` or `outputs`.

**The solution**:
1. Update `_cdpTestSaveSuite()` to collect and include I/O data
2. Verify the backend PUT/POST routes pass those fields through to
   `TestSuite.from_dict()` (which already parses them)
3. Verify round-trip: save → reload → edit again → I/O still there

**Backend check**: The suite save route likely already passes the full
request body to `TestSuite.from_dict()`. Verify this. If not, add the
fields to the handler.

### B.2.5 — Target Site: Input Marking During Recording

**The problem**: When recording on the target site, you interact with
elements naturally — clicking, typing, navigating. The recorder captures
the literal values. There's no way to say "this input should be a
variable" during the recording itself.

**The solution**: Enhance the recording experience on the target site:

1. **Context menu / overlay option**: When the recorder captures a `type`
   step, briefly show a small overlay near the typed field offering:
   "📌 Make this a variable?" If clicked, show a quick name field.

2. **Post-step annotation**: After each recorded step, the recorder's
   live step list (in the admin panel) could show a quick "📌" button
   to mark the just-recorded value as a variable.

3. **Batch marking**: After recording finishes, in the validation view,
   the user can go through and mark any values as variables. This is
   essentially B.2.1 (the step editor) applied after recording.

**Practical approach**: Option 3 (batch marking post-recording) is
the minimum viable path — it's just B.2.1. Options 1 and 2 are UX
improvements ON TOP of option 3.

**Recommendation**: Start with Option 3 (post-recording in validation).
Plan Option 2 (live step list annotation) as an enhancement. Option 1
(target site overlay) is the most invasive and should come last.

### B.2.6 — Target Site: Export Marking During Recording

Same principle as B.2.5 but for capture steps:

1. When a `capture_*` step is recorded on the target site, offer to
   name the export right there.
2. Or do it in the post-recording validation (B.2.2).

**Recommendation**: Same as inputs — start with post-recording (B.2.2).
The target-site experience (B.2.5/B.2.6) is an enhancement layer.

### B.2.7 — Replay Config: Variable Overrides

**The problem**: When replaying a suite that has declared variables,
the replay config overlay (`_cdpTestShowReplayConfig`) doesn't show
the variables for override. The user has no way to provide runtime
values for declared inputs.

**The solution**: In the replay config overlay:
1. Show a "Variables" section listing all `variable_defs` (or raw
   `variables` dict) with their defaults
2. Let the user edit values before replay
3. Pass overrides to the replay API call

**Current state of replay flow**:
```
_cdpTestShowReplayConfig() → shows timing, clear_site_data, keep_background
_cdpTestExecuteReplay() → calls /api/cdp-test/replay with overrides
```

The replay API already accepts `variables` in the request body.
The replayer already merges overrides with suite defaults.
The UI just doesn't surface the variable fields.

### B.2.8 — Verification

For the complete CDP test I/O system:
1. Create a test suite with 3+ steps
2. Mark a `type` step's value as variable-bound (`${LOGIN_EMAIL}`)
3. Mark a `capture_text` step as `export_as: AUTH_TOKEN`
4. Verify the I/O summary panel shows both
5. Save → reload → verify persistence
6. Replay with variable override → verify substitution works
7. Use the suite in a plan step → verify plan editor shows the I/O

**Files**: `_cdp_test.html`, possibly `models.py` (if Option B for input binding),
  possibly suite save routes
**Risk**: Medium — new UI panels in existing modals
**Effort**: Medium-Large (B.2.1 through B.2.7 is substantial)

---

# DOMAIN C: Plan Execution System

This domain covers the execution experience itself — the modal that appears
when you run a plan, the step results, and the post-run result view. It
consumes I/O from Domain A and Domain B.

## C.1 Current State

### C.1.1 — Execution Modal

| Aspect | Status | Location |
|--------|--------|----------|
| `_plansShowExecutionView()` | ✅ | Line 1217 — header, progress bar, step list |
| Progress bar | ✅ | Animated, shows N/total and percentage |
| Running step indicator | ✅ | Blue pulsing dot in header |
| Step rows (inline results) | ✅ | Status icon + name + duration + vars badge |
| Variables panel | ✅ | Collapsible, updated per step_done event |
| Mode label in header | ✅ | Shows fully_automated/semi/interactive |
| Cancel button | ✅ | Closes SSE, sends cancel to API |
| SSE event handling | ✅ | `plan:step_start`, `plan:step_done`, `plan:paused`, `plan:done` |
| Pause view (interactive) | ✅ | Chunk 6f — produced vars, next step preview, editable namespace |
| Pause view (checkpoint) | ✅ | Chunk 6g — accumulated vars since last checkpoint |
| Mode-specific UX adaptation | ❌ | All three modes use the same layout/behavior |
| Estimated time remaining | ❌ | |
| Run Complete summary card | ❌ | |
| Keyboard shortcuts | ❌ | |

### C.1.2 — Step Results & Drill-Down

| Aspect | Status | Location |
|--------|--------|----------|
| Drill-down toggle (click row) | ✅ | `_plansToggleStepDetail()` — expands inline |
| Script detail | ✅ | `_plansScriptDetail()` — mini terminal + exit code |
| CDP test detail | ✅ | `_plansCdpTestDetail()` — progress bar + pass/fail + replay steps |
| Checkpoint detail | ✅ | `_plansCheckpointDetail()` — message only |
| Produced vars in step row | ✅ | `_plansFormatValueShort()` badge |
| Input params shown in drill-down | ❌ | What went IN to this step |
| Produced vars shown in drill-down | ❌ | What came OUT of this step (rich) |
| Copy script output | ❌ | |
| Failed assertions emphasized | ❌ | All assertions shown equally |
| Screenshots click-to-zoom | ❌ | Thumbnail + link only |
| Replay step grouping | ❌ | Flat list |
| Duration timeline | ❌ | |

### C.1.3 — Post-Run Result View

| Aspect | Status | Location |
|--------|--------|----------|
| `_plansOpenResult()` | ✅ | Shows step list + variable trace |
| Step list | ✅ | Same format as live view |
| Variable trace | ✅ | Lists produced vars per step + final namespace |
| Summary header | ⚠️ | Basic — no verdict card |
| Timeline visualization | ❌ | |
| Variable flow diagram | ❌ | |
| Quick re-run | ⚠️ | "Run Again" exists but no "Run Again with Edits" |

## C.2 Work Items

### C.2.1 — Wiring Verification (depends on A + B)

Before improving the execution UI, verify the full I/O chain actually works:

1. **Script param expansion**: Does the executor expand `{{VAR}}` in
   `script_params` against the namespace? Trace `_execute_script_step()`
   to verify.

2. **Script output capture**: Does `DCP_VAR_*=` from stdout get into
   `StepResult.variables_produced` → namespace → next step? Trace the
   full path.

3. **CDP test variable injection**: Does the plan executor pass namespace
   vars as `variables` to the replayer? Trace `_execute_cdp_test_step()`.

4. **CDP test output extraction**: Does `export_name` from replay results
   get into `produced` → namespace? Already verified in research above
   (plan_executor.py line 401-407).

5. **Auto-populate produces/consumes**: When saving a step in the plan
   editor, does `_plansSaveStep()` auto-set `produces` from declared
   outputs and `consumes` from `{{VAR}}` references? Trace the save logic.

**Goal**: Confirm or fix every link in the chain. No UI work, just
verification and surgical fixes.

### C.2.2 — Execution Modal: Mode-Aware UX

**The problem**: All three modes display the same execution view. The
experience should feel different for each mode because the user's intent
is different:

- **Fully Automated**: "Fire and forget" → user wants to see progress,
  then final result. Minimal interaction during execution.
- **Semi-Automated**: "Run segments, inspect, continue" → user pauses
  at checkpoints, inspects accumulated state, decides to continue.
- **Interactive**: "Step-by-step debugging" → user controls every step,
  inspects everything, can tweak variables live.

**Changes per mode**:

**Fully Automated**:
- Progress bar is the hero element (larger, more prominent)
- Step rows appear as they complete (current behavior, polish it)
- No pause panel (unless error occurs)
- On completion: show a summary card:
  - Green/red header based on pass/fail
  - Key metrics: duration, steps passed/failed, vars produced
  - Quick actions: "View Details", "Run Again", "Back to Plans"
- On failure: first error highlighted, suggestion to switch to interactive

**Semi-Automated**:
- Show segment progress: "Steps 1-4 of 8 (running)"
- When paused at checkpoint:
  - Full-width checkpoint banner (amber accent)
  - "What happened since last checkpoint": collapsed step list
  - "Coming up next": preview of steps until next checkpoint
  - Editable namespace (current Chunk 6g behavior, polished)
  - "▶ Continue" button prominent
- Between checkpoints: step rows stream in like fully_automated

**Interactive**:
- Current step is the hero element (expanded, prominent)
- After each step completes:
  - Auto-expand the just-completed step detail (no click needed)
  - Next step preview always visible below
  - Produced variables shown inline
- Resume controls:
  - "▶ Continue" (run next step)
  - "⏭ Skip" (skip next step)
  - "✏️ Edit Vars" (open namespace editor before continuing)
  - Keyboard: Enter = Continue, Esc = Skip
- Completed steps collapse upward (scroll focus follows active step)

**Universal improvements (all modes)**:
- Step rows show step number: "1/8", "2/8", etc.
- Running step has animated indicator (spinner or pulse)
- Duration timer running live for current step
- Better transitions between states (smooth animations)

### C.2.3 — Step Results Enhancement

**Script step drill-down** (`_plansScriptDetail`):

Currently: mini terminal with raw output, exit code.

Enhance to:
- Terminal section with copy button
- Below terminal: "Inputs" section showing params that were passed
- Below inputs: "Outputs" section showing each `DCP_VAR_` with
  name + value (using `_plansFormatValue` for complex values)
- Duration + timestamp header
- If failed: error message prominently above terminal

**CDP test step drill-down** (`_plansCdpTestDetail`):

Currently: progress bar + stats + flat replay step list.

Enhance to:
- Summary section stays (progress bar + pass/fail counts)
- Replay steps: group by status (failures first, then passed)
- Failed assertions: expected vs actual with visual diff
  - Color-coded: expected in one color, actual in another
  - For text comparisons: highlight the differing parts
- Exported variables: highlight which capture steps produced plan vars
  (show `📤 AUTH_TOKEN = "..."` badge on the relevant capture step)
- Screenshots: larger thumbnails, click opens fullscreen overlay
- Collapse passed steps by default (toggle "show all")

**Checkpoint step drill-down** (`_plansCheckpointDetail`):

Currently: just the checkpoint message.

Enhance to:
- Checkpoint message
- "Namespace at this point": show full variable state when checkpoint hit
- If variables were edited during pause: show "Modified" badge with
  before/after values
- Duration paused (time between pause and resume)

### C.2.4 — Post-Run Result View

**The problem**: After a plan completes (or viewing a past result), the
result view is just a step list and variable trace. It should be a
comprehensive post-mortem tool.

**Changes**:

1. **Summary card at top**:
   - Verdict: PASSED (green), FAILED (red), PARTIAL (amber)
   - Duration, step count, vars produced
   - Mode used, initial variables
   - Timestamp

2. **Timeline visualization**:
   - Horizontal bar showing each step as a segment
   - Width proportional to duration
   - Color: green (passed), red (failed), gray (skipped), amber (checkpoint)
   - Hover shows step name + duration
   - Click jumps to step detail

3. **Step list** (current, polish it):
   - Same drill-down capability as live view
   - Each step expandable for full detail

4. **Variable trace** (current, enhance):
   - Show as a flow: initial → step additions → final
   - Each variable tagged with which step introduced it
   - If a variable was modified during a pause: show edit history

5. **Quick re-run with edits**:
   - "▶ Run Again" (same params → runs immediately)
   - "▶ Run Again with Edits" (opens plan editor pre-filled with the
     exact params/mode used in this run, lets user tweak before running)

### C.2.5 — Verification

1. Run a plan with script + CDP test + checkpoint in fully_automated mode
2. Run the same plan in semi_automated mode → verify checkpoint UX
3. Run in interactive mode → verify step-by-step UX
4. View a past result → verify post-mortem view
5. Re-run from result view → verify quick re-run

**Files**: `_plans.html`
**Risk**: Medium — UX polish in complex SSE-driven views
**Effort**: Medium-Large

---

## 3. Dependency Graph

```
DOMAIN A                    DOMAIN B
Script @output/DCP_VAR      CDP Test I/O
   │                           │
   │  A.2.1-3                  │  B.2.1-7
   │  (add outputs             │  (input binding, export_as,
   │   to scripts)             │   I/O panel, replay config)
   │                           │
   └───────────┬───────────────┘
               │
               ▼
         DOMAIN C
     Plan Execution
               │
    ┌──────────┼──────────┐
    │          │          │
    ▼          ▼          ▼
  C.2.1      C.2.2     C.2.4
  Wiring     Mode-      Result
  verify     aware UX   view
               │
               ▼
             C.2.3
             Step
             results
```

- A and B are fully independent — can be done in parallel
- C.2.1 (wiring verification) depends on A + B being done
- C.2.2-C.2.4 are sequential (execution UX → step results → result view)
- C.2.2 includes C.2.3 since step results are rendered within execution

---

## 4. Execution Order

| Order | Item | Effort | Reason |
|-------|------|--------|--------|
| 1 | **A.2.1-3** (Script outputs) | Small | Unblocks plan I/O testing for scripts |
| 2 | **B.2.1** (Input variable binding in step editor) | Medium | Core capability — enables parameterized tests |
| 3 | **B.2.2** (Output export in step editor) | Small | `export_as` field — straightforward |
| 4 | **B.2.3** (Suite-level I/O summary) | Medium | Aggregate view — depends on B.2.1 + B.2.2 data |
| 5 | **B.2.4** (Save route update) | Small | Include I/O in save payload |
| 6 | **B.2.7** (Replay config variables) | Small | Show vars in replay overlay |
| 7 | **C.2.1** (Wiring verification) | Small | Prove the chain works end-to-end |
| 8 | **C.2.2** (Mode-aware execution UX) | Medium-Large | The main UX evolution |
| 9 | **C.2.3** (Step results enhancement) | Medium | Richer drill-downs |
| 10 | **C.2.4** (Result view evolution) | Medium | Post-mortem experience |
| Later | **B.2.5-6** (Target site I/O marking) | Medium | Enhancement on top of working system |

---

## 5. What This Unlocks

After all three domains are complete:

1. **Script I/O**: Run `audit/code_hygiene` → it produces `REPORT_PATH`
   and `HYGIENE_RESULT` → next plan step can consume them

2. **CDP Test I/O**: Record a login test → mark email/password fields
   as `${LOGIN_EMAIL}` and `${LOGIN_PASS}` → mark captured auth token
   as `export_as: AUTH_TOKEN` → suite declares 2 inputs, 1 output →
   plan editor shows typed fields with upstream wiring

3. **Plan chaining**: Script A (produces report) → Script B (consumes report)
   → CDP Test (consumes BASE_URL, produces AUTH_TOKEN) → Script C
   (consumes AUTH_TOKEN). The I/O wiring is visible, validated, and
   mode-appropriate.

4. **Mode-specific execution**: Each of the 3 modes provides a distinct,
   purpose-built UX. Interactive mode is a debugger. Semi-automated is
   a checkpoint system. Fully automated is a fire-and-forget runner.

5. **Rich results**: Post-run view shows timeline, variable flow, step
   details with inputs/outputs, assertion diffs, and quick re-run.

---

## 6. Parking Lot (Not In Scope)

- Conditional step logic (if/else based on variables)
- Looping (for-each over list variables)
- External webhook triggers
- Plan templates (parameterized reusable plans)
- Multi-plan orchestration
- Result diffing between runs
- Target-site recording-time I/O marking (B.2.5-6 — deferred enhancement)
