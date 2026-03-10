# CDP Test I/O — Complete System Design (From Scratch)

> Revolution. Not patching. This document defines what the I/O system IS,
> from first principles. Everything currently in place is replaced.

---

## The I/O System

Suites have **INPUTS** — parameters they accept before running.
Suites have **OUTPUTS** — values they produce after running.
Steps are where I/O binds — an input parameter gets consumed by a step,
a captured value gets exported by a step.
Plans chain suites via I/O — Suite A's outputs wire to Suite B's inputs.

Three UI layers let users configure this — target site, recording view,
validation view. The data model stores it. The replayer executes it.
The plan executor chains it.

---

## Concepts

### INPUT — Suite Parameter

An INPUT is a value that flows INTO the suite from outside.

- The user records a step that consumes a value (types into a field, navigates to a URL, selects an option)
- The user decides: "this value should be configurable when running the suite"
- The user gives it a name (e.g. `LOGIN_EMAIL`)
- The recorded value becomes the default
- At runtime, the caller provides the actual value (or accepts the default)
- The replayer substitutes `${LOGIN_EMAIL}` with the provided value

An INPUT binds to a step. The step's value becomes `${VAR_NAME}`. The original
recorded value is preserved separately as the default.

### OUTPUT — Suite Export

An OUTPUT is a value that flows OUT of the suite to the caller.

- During replay, a step captures a value from the live page (text content, input value, attribute, URL, etc.)
- The user decides: "this captured value should be available after the suite runs"
- The user gives it a name (e.g. `AUTH_TOKEN`)
- At runtime, the replayer tags the captured value with that name
- The caller (plan executor) receives it and can pass it to downstream suites

An OUTPUT binds to a capture step. The step's `export_as` field holds the
export name. If the user wants to export from a non-capture step (e.g. the
text content of a clicked element), the system adds a `capture_text` step
targeting the same element.

### User Choice

The USER chooses whether an element is INPUT or OUTPUT. The system does not
decide for them. A textarea can be INPUT (parameterize what gets typed into it)
or OUTPUT (capture what's currently in it). The system detects the element type
and offers the appropriate options:

- **Form elements** (input, textarea, select): Can be INPUT or OUTPUT
  - INPUT: parameterize the value being entered
  - OUTPUT: capture the current value (adds `capture_value` step if needed)
- **Non-form elements** (div, span, button, link, heading, etc.): OUTPUT only
  - OUTPUT: capture the text content (adds `capture_text` step if needed)
  - INPUT does not apply — you cannot type into these elements

The system SUGGESTS based on element detection (form field → suggest INPUT,
non-form → suggest OUTPUT) but the user makes the final choice.

---

## Layer 1: Data Model

### TestStep fields for I/O

```python
# Existing field — keep
export_as: str = ""              # Export name for capture steps (e.g. "AUTH_TOKEN")

# NEW field — add to TestStep dataclass
original_value: str = ""         # The recorded default value, preserved when
                                 # value is replaced with ${VAR}. Used to show
                                 # the default and to restore if I/O is removed.
```

`original_value` replaces the ad-hoc `_original_value` dict key. It is a real
field that survives serialization (`to_dict`/`from_dict`).

### TestSuite fields for I/O

```python
# Existing field — keep, AUTO-POPULATE
variables: dict[str, str]        # Variable name → default value
                                 # Auto-populated from steps with ${VAR} in value
                                 # No types. No descriptions. Name → default. That's it.

# DROP variable_defs entirely. SuiteVariable is overengineered garbage.
# Variables are simple: name and default value.

# Existing field — keep, AUTO-POPULATE
outputs: dict[str, str]          # Export name → description
                                 # Auto-populated from steps with export_as set
```

### Auto-sync

When I/O is configured on a step (via any of the 3 UI layers):

**For INPUT:**
1. Step's `value` becomes `${VAR_NAME}`
2. Step's `original_value` stores the recorded value
3. User sets the default value (pre-populated with the recorded value, editable)
4. Suite's `variables[VAR_NAME]` is set to the user's chosen default

**For OUTPUT:**
1. Step's `export_as` is set to the export name
2. Suite's `outputs[EXPORT_NAME]` is set

**When I/O is removed:**
1. For INPUT: Step's `value` restored from `original_value`. Variable removed
   from suite's `variables`.
2. For OUTPUT: Step's `export_as` cleared. Export removed from suite's `outputs`.

### Auto-sync implementation

A utility function `sync_suite_io(suite)` scans all steps and rebuilds
`variables` and `outputs` from step data. Called:
- After any I/O modification via UI
- When saving a recording as a suite
- When loading a suite for validation

This is the SINGLE SOURCE OF TRUTH. Suite-level I/O declarations are always
derived from step-level I/O bindings. Never manually maintained.

---

## Layer 2: Backend

### I/O Configuration Endpoint

A single endpoint for all I/O configuration, replacing the fragmented
`io_bind` handler and `modify-step` workarounds.

```
POST /cdp-test/io/configure
{
    "step_id": "uuid",              // REQUIRED — identifies the step by ID, not selector
    "session_id": "uuid",           // For recording context
    "suite_id": "uuid",             // For validation context (mutually exclusive with session_id)
    "io_type": "input" | "output",  // What the user chose
    "name": "LOGIN_EMAIL",          // Variable name (input) or export name (output)
    "default_value": "admin@test.com", // Default value (INPUT only, set by user)
    "remove": false                 // true = remove I/O from this step
}
```

**Backend logic:**

```
if io_type == "input":
    1. Validate step has a consumable value (action in value_actions)
    2. Set step.original_value = step.value (preserve recorded value)
    3. Set step.value = "${NAME}"
    4. Set suite.variables[NAME] = default_value (user's chosen default)
    5. Clear step.export_as (mutual exclusivity)
    6. Sync suite-level variables

if io_type == "output":
    1. If step is already a capture_* action:
       - Set step.export_as = NAME
    2. If step is NOT a capture action (click, hover, type, etc.):
       - Determine capture type from element:
         - Form element (input/textarea/select) → capture_value
         - Non-form element → capture_text
       - CREATE a new capture step:
         - action = determined capture type
         - selector = same as original step
         - xpath = same as original step
         - export_as = NAME
         - sequence = original step's sequence + 0.5 (inserted after)
       - Re-sequence all steps
    3. Clear any INPUT binding on original step (mutual exclusivity)
    4. Sync suite-level outputs

if remove:
    1. If step has INPUT: restore value from original_value, clear variables
    2. If step has OUTPUT: clear export_as, if step was auto-created capture → delete it
    3. Sync suite-level I/O
```

**Response:**

```json
{
    "ok": true,
    "step": { ... },           // Updated step (or new capture step)
    "suite_io": {              // Updated suite-level I/O summary
        "inputs": [...],
        "outputs": [...]
    }
}
```

**SSE broadcast:** `cdp_test:io_configured` with step data and suite I/O summary.

### Target Site Event Handler

The target site sends I/O configuration via the existing event endpoint.
The handler routes to the same I/O logic:

```
POST /cdp-test/record/event
{
    "action": "io_configure",
    "selector": "...",           // Used to find the step (fallback)
    "step_id": "...",            // If known (preferred)
    "io_type": "input" | "output",
    "name": "LOGIN_EMAIL"
}
```

The handler finds the step (by ID if provided, by selector if not — walking
backwards through recent steps). Then calls the same I/O configuration logic.

---

## Layer 3: Replayer

### INPUT execution

`_resolve_variables()` already works. No changes needed.

```python
# Step value: "${LOGIN_EMAIL}"
# Variables: {"LOGIN_EMAIL": "admin@test.com"}
# Resolved: "admin@test.com"
```

The variables dict is built from:
1. Suite's `variables` (defaults)
2. Runtime overrides from the replay start API
3. Plan executor's output→input mappings

### OUTPUT execution

The existing capture + export logic already works:

```python
if step.action.startswith("capture_") and step_result["status"] == "passed":
    captured_val = details.get("captured")
    if captured_val is not None:
        captures[step.id] = captured_val
        if step.export_as:
            result_record["export_name"] = step.export_as
```

The replayer handles both sides of I/O: substituting `${VAR}` for inputs
and capturing + exporting values for outputs. The layers above ensure
OUTPUT binds to a capture step (creating one if needed).

### Result data

After replay, `TestRunResult.step_results` contains entries with:
- `captured_value` — the actual captured data
- `export_name` — the export name (from `step.export_as`)

The plan executor reads these to build the output namespace.

---

## Layer 4: Target Site UI (`cdp_recorder.js`)

### When to show the I/O badge

The I/O badge appears alongside the assert badge when the user interacts
with an element. It appears:

- After a **click** on any element (user might want to export text content)
- After **typing** into a form field (user might want to parameterize the input)
- After **selecting** an option (user might want to parameterize the selection)

The badge does NOT appear for scroll or navigate steps (no meaningful I/O).

### I/O Modal

When the user clicks the I/O badge:

1. **Detect element type** using `_isFormElement()`:
   - Form element → show INPUT and OUTPUT options (radio toggle)
   - Non-form element → show OUTPUT only (no toggle needed)

2. **Suggest default choice**:
   - Form element with recent type step → suggest INPUT
   - Form element without type step → suggest OUTPUT
   - Non-form element → OUTPUT (only option)

3. **Show the modal**:
   - Selector chain picker (same as assertion modal — user can pick parent/child)
   - Changing the selected element re-evaluates form detection and updates suggestions
   - Mode toggle (INPUT / OUTPUT) — only for form elements
   - Name field (variable name for INPUT, export name for OUTPUT)
   - Default value field (INPUT only — pre-populated with element's current value, user can edit)
   - Save / Cancel buttons

4. **Pre-populate existing config**:
   - If the most recent step for this selector already has `${VAR}` → show INPUT with the variable name filled in
   - If there's already a capture step with `export_as` for this selector → show OUTPUT with the export name filled in

5. **On save**:
   - Pause recording
   - Send `io_configure` event to backend (with selector + io_type + name + default_value)
   - Backend handles step modification or capture step creation
   - Resume recording
   - Close modal

### Color palette

- INPUT accent: purple (#8b5cf6) — consistent across all layers
- OUTPUT accent: green (#22c55e) — consistent across all layers
- Self-contained styling (no CSS vars — we're on a foreign page)

---

## Layer 5: Admin Recording View (`_cdp_test.html`)

### I/O button visibility

The 🔗 I/O button appears on steps where I/O makes sense:

- **Value actions** (type, navigate, select, keypress, inject_js): Can be INPUT
- **Capture actions** (capture_*): Can be OUTPUT
- **Element-targeting actions** (click, hover): Can trigger OUTPUT (adds capture step)
- **No I/O**: scroll, assert, wait — no 🔗 button

### I/O Overlay

When user clicks 🔗 on a step:

**For value actions:**
- Show INPUT section (purple accent)
- Title: "📥 Input — Suite Parameter"
- Variable name field, pre-populated if already bound
- Default value shown (from `original_value` or current value)
- Option to switch to OUTPUT if the step targets a form element
  (this would add a capture_value step and remove the INPUT binding)

**For capture actions:**
- Show OUTPUT section (green accent)
- Title: "📤 Output — Export"
- Export name field, pre-populated if `export_as` already set

**For click/hover (element-targeting, non-value, non-capture):**
- Show OUTPUT section (green accent)
- Title: "📤 Export Element Content"
- Explain: "Adds a capture step after this step to capture the element's text"
- Export name field
- On save → calls I/O configure endpoint → backend adds capture step
- The new capture step appears in the step list

### Save logic

All saves go through the unified `/cdp-test/io/configure` endpoint with
`step_id`. No more selector-based lookup. No more `modify-step` workaround.

### Visual badges

Steps with I/O show inline badges:
- `📥 ${LOGIN_EMAIL}` — purple, for INPUT-bound steps
- `📤 AUTH_TOKEN` — green, for OUTPUT-bound steps

SSE listener for `cdp_test:io_configured` updates badges in real-time.

---

## Layer 6: Admin Validation/Edit View (`_cdp_test.html`)

### Step Edit Form I/O Section

When editing a step, the I/O section appears based on step type:

**Value actions (type, navigate, select, keypress, inject_js):**
```
📥 Input — Suite Parameter
[x] Mark as input parameter
    Variable name: [LOGIN_EMAIL_______]
    Default value: [admin@test.com____]  (pre-populated with recorded value, editable)
```

If the step also has a selector (which type steps do), an additional option:
```
📤 Or export element content instead
    [Add Capture Step]
```
Clicking "Add Capture Step" creates a capture step after this one and
removes any INPUT binding. Mutual exclusivity.

**Capture actions:**
```
📤 Output — Export
    Export name: [AUTH_TOKEN__________]
    Captured value exported to plan namespace for downstream suites
```

**Click/hover (element-targeting, non-capture):**
```
📤 Export Element Content
    Export name: [ELEMENT_TEXT________]
    Adds a capture step to export this element's text content
    [Add Capture Step]
```

**Assert, scroll, wait:** No I/O section.

### Step row badges

Same as recording view — 📥 and 📤 badges inline.

### I/O Summary Panel

Two tables at the top of the validation view:

**Inputs:**
| Variable | Default | Step |
|----------|---------|------|
| LOGIN_EMAIL | admin@test.com | #3 type |
| PASSWORD | secret123 | #4 type |

**Outputs:**
| Export | Step | Source |
|--------|------|--------|
| AUTH_TOKEN | #7 capture_text | #login-token .value |
| PAGE_TITLE | #12 capture_text | h1.title |

Rows are clickable → scroll to the corresponding step and highlight it.
Each row has a 🔗 button to open the I/O overlay for that step.

Empty state: "No inputs configured" / "No outputs configured" with
guidance text on how to add them.

### Save behavior

Validation view saves locally to the step data JSON. When the user
clicks "Save Suite", the suite is persisted with `sync_suite_io()` called
to ensure suite-level declarations are consistent with step-level bindings.

---

## Layer 7: Plan Executor

### Reading suite I/O declarations

The plan editor reads `suite.variables` and `suite.outputs` to present
I/O wiring options. These are always up-to-date because `sync_suite_io()`
maintains them.

### Passing inputs

When the plan executor starts a suite, it builds the variables dict:

```python
variables = {}
# 1. Suite defaults (name → default value)
variables.update(suite.variables)
# 2. Plan-level overrides (user-configured in plan editor)
variables.update(plan_step.variable_overrides)
# 3. Output→input mappings from upstream suites
for mapping in plan_step.input_mappings:
    upstream_value = upstream_results.get(mapping.source_export)
    if upstream_value is not None:
        variables[mapping.target_variable] = upstream_value
```

This `variables` dict is passed to `start_replay()`.

### Collecting outputs

After a suite finishes, the plan executor reads the step results:

```python
suite_outputs = {}
for step_result in run_result.step_results:
    if step_result.get("export_name") and step_result.get("captured_value"):
        suite_outputs[step_result["export_name"]] = step_result["captured_value"]
```

These outputs are stored in the plan's namespace and available for
downstream suite mappings.

---

## Layer 8: Plan Editor UI

### Suite I/O display

Each suite node in the plan editor shows:
- **Left side (inputs):** Variable names with types, connected by wires
- **Right side (outputs):** Export names, connected by wires to downstream inputs

### Wiring

User drags from an output port to an input port on a downstream suite.
This creates an `input_mapping`:

```json
{
    "source_suite_id": "suite-a",
    "source_export": "AUTH_TOKEN",
    "target_suite_id": "suite-b",
    "target_variable": "TOKEN"
}
```

### Validation

- Warn if an input has no mapping and no default value (required but unset)
- Warn if an output is mapped but the capture step is optional
- Show type compatibility (string→string ok, secret→string ok with warning)

---

## Execution Order

The layers build on each other. Implementation order:

1. **Data model** — Add `original_value` field to TestStep. Update `to_dict`/`from_dict`. Build `sync_suite_io()` utility.

2. **Backend** — Build `/cdp-test/io/configure` endpoint. Update event handler for `io_configure` action. The endpoint uses step ID, validates step type, handles capture step creation, calls `sync_suite_io()`.

3. **Replayer** — Verify no changes needed. The existing `_resolve_variables()` and `export_as` logic already work. Document this verification.

4. **Target site UI** — Rewrite the I/O modal from scratch. Correct element detection, user choice, selector chain picker, pre-population, save via `io_configure` event.

5. **Admin recording view** — Rewrite the I/O overlay from scratch. Correct step-type-aware sections, unified save via `/cdp-test/io/configure`, visual badges, SSE listener.

6. **Admin validation view** — Rewrite the step edit form I/O section. Same correct model. I/O summary panel. Save with `sync_suite_io()`.

7. **Plan executor** — Build input passing and output collection. Wire the variables and outputs through the replay lifecycle.

8. **Plan editor** — Build I/O visualization and wiring UI. Connect to plan executor data model.

Each layer is implemented and verified independently before moving to the next.
Each change within a layer is one change, one test.

---

## File Map

| Layer | Files |
|-------|-------|
| Data model | `src/core/services/cdp_test/models.py`, new `src/core/services/cdp_test/io_sync.py` |
| Backend | `src/ui/web/routes/cdp_test/recording.py`, possibly new `src/ui/web/routes/cdp_test/io.py` |
| Replayer | `src/core/services/cdp_test/replayer.py` (verify only) |
| Target site | `src/core/data/cdp_recorder.js` |
| Admin recording | `src/ui/web/templates/scripts/integrations/_cdp_test.html` |
| Admin validation | `src/ui/web/templates/scripts/integrations/_cdp_test.html` |
| Plan executor | `src/core/services/cdp_test/plan_executor.py` (new or existing) |
| Plan editor | `src/ui/web/templates/scripts/integrations/_cdp_plan.html` (new or existing) |
