# CDP Test Assertions, Diagnostics & Branching — Full Plan

> **Status**: Planning — Design Phase
> **Created**: 2026-03-08
> **Initiative**: CDP Test System Evolution
> **Connects to**: Scripts System M7 (Execution Plans)

---

## 0. Source of Truth — The User's Words (Verbatim)

Every design decision traces back to these exact statements.

### Message 1 — The Need

> "Before execution plan we need to be able to do test but for test to be complete
> you have to be able to do more than just replay an execution, the recording itself
> has to allow the user to add custom validation during or after to say this Xpath
> for example of this one must say XYZ or ABC or must contain IJK and whatnot...
> we need to think of all this to be able to evolve."

### Message 2 — Branching & Routing

> "If I click an element now there will be a badge I can click to open an assertion
> configuration where if the assertion fail I can chose to return as failure / cancel
> or just fail it. the meaning is to decide of the routes and be able to branch back
> in the history of the assertion to actually be able to offer multiple branches of
> choses at the time of this assertion to be able to diagnose for example or even
> just fallback or both with 3 branch"

### Message 3 — Diagnostics & Captures

> "offer me to capture the content, or the innerHTML, or a given attribute for me to
> do my assertion and such, you will even allow me to take a snip screenshot of the
> selected component and I can add multiple diagnosis action and I can also execute
> javascript that is injected into a console.log() and we capture it and the user can
> thus do whatever he want injected / executed into the page"

### Message 4 — Console Scope & Flexibility

> "console log are going to be added to failed tests script execution to be able to
> debug them more easily, we capture them, so when there is a debugged step triggered
> we start to send them and we send them till the end of the diagnostic branch.
> and diagnostic doesn't mean end you could do it like an assertion in between any
> steps right... this is a very flexible and intelligent tool."

---

## 1. The Problem — Why Replay Is Not Testing

### What We Have (Today)

The CDP test system records user actions (click, type, select, key) and replays
them against a target tab. A "passed" test means "all actions executed without
element-not-found errors."

This is a **macro replayer**, not a test framework.

### What's Missing

| Capability | Current | Needed |
|-----------|---------|--------|
| **Verify results** | No — only checks if elements exist | Assert text, value, attribute, visual state |
| **Capture data** | No | Extract text, HTML, attributes, screenshots |
| **Debug failures** | No — just "Element not found" | Inject JS, capture console, scoped diagnostics |
| **Conditional flow** | No — linear step list | Branch on assertion outcome (pass/diagnose/fallback) |
| **Branch-back** | No | Re-enter execution at assertion point, choose different branch |
| **Compose into plans** | No | CDP suites as steps in Execution Plans (M7) |

### The Dependency Chain

```
Execution Plans (Scripts M7)
    ↑ needs
Branching Engine (replay follows tree, not list)
    ↑ needs
Assertion Step Model (assert action + conditions + failure routing)
    ↑ needs
Diagnostic Actions (inject JS, capture console, screenshots)
    ↑ needs
Capture Actions (extract text/HTML/attributes from elements)
    ↑ needs
Step Model Evolution (flat list → directed graph)
    ↑ needs
Recording UX (badge → assertion config during recording)
```

**Chicken and egg**: Execution Plans can't branch without assertions.
Assertions don't exist without the step model evolving. The step model
needs the UX to create it. Everything must be designed together.

---

## 2. Step Model Evolution — Flat List → Graph

### 2.1 Current Model

```python
class TestStep:
    id: str
    action: str          # "click", "type", "select", "key", "ping"
    selector: str        # CSS selector
    value: str           # Text to type, option to select
    sequence: int        # Linear ordering (1, 2, 3, ...)
    wait_before_ms: int
    optional: bool
```

Steps are stored as a flat list, sorted by `sequence`. The replayer iterates
through them in order. There is no branching, no assertions, no captures.

### 2.2 Evolved Model

```python
class TestStep:
    id: str
    action: str          # Expanded: see §3
    selector: str
    value: str
    sequence: int        # Still used for visual ordering within a branch
    wait_before_ms: int
    optional: bool

    # ── NEW: Graph edges ──────────────────────────────────
    next_step_id: str | None          # Default next step (replaces sequence for flow)
    branch_id: str | None             # Which branch this step belongs to (None = main)

    # ── NEW: Assertion config (only for assert steps) ─────
    assert_config: AssertConfig | None

    # ── NEW: Diagnostic config (only for diagnostic steps) ─
    diagnostic_config: DiagnosticConfig | None
```

### 2.3 Suite Structure Change

**Current**:
```json
{
  "steps": [ step1, step2, step3, ... ]  // flat list, ordered by sequence
}
```

**Evolved**:
```json
{
  "steps": {                             // dict keyed by step ID
    "s1": { ... , "next_step_id": "s2" },
    "s2": { ... , "next_step_id": "assert-1" },
    "assert-1": {
      "action": "assert",
      "assert_config": {
        "on_pass": "s3",
        "on_fail": {
          "mode": "branch",
          "branches": [
            { "label": "Diagnose", "first_step_id": "diag-1" },
            { "label": "Fallback", "first_step_id": "fb-1" }
          ]
        }
      }
    },
    "s3": { ... },
    "diag-1": { ..., "branch_id": "diagnose-assert-1", "next_step_id": "diag-2" },
    "diag-2": { ..., "branch_id": "diagnose-assert-1", "next_step_id": null },
    "fb-1": { ..., "branch_id": "fallback-assert-1", "next_step_id": "fb-2" },
    "fb-2": { ..., "branch_id": "fallback-assert-1", "next_step_id": null }
  },
  "start_step_id": "s1",               // entry point
  "branches": {                          // branch metadata
    "main": { "label": "Main", "color": "#8b5cf6" },
    "diagnose-assert-1": { "label": "Diagnose", "color": "#f59e0b" },
    "fallback-assert-1": { "label": "Fallback", "color": "#3b82f6" }
  }
}
```

### 2.4 Backwards Compatibility

The evolved model MUST load old flat-list suites without migration.
Detection: if `steps` is a list → convert to dict at load time, set
`next_step_id` based on sequence ordering. No file rewrite needed.

---

## 3. Action Types — Full Roster

### 3.1 Existing Actions (unchanged)

| Action | Purpose |
|--------|---------|
| `ping` | Verify CDP session is alive |
| `click` | Click an element by CSS selector |
| `type` | Type text into an input/textarea |
| `select` | Select an option from a dropdown |
| `key` | Send a keyboard key (Enter, Escape, etc.) |

### 3.2 New: Capture Actions

Extract data from the page. Captures are **inputs to assertions** or stored
as evidence in reports. Captured values are available to subsequent steps
via a `captures` context dict keyed by step ID.

| Action | What it captures | CDP Mechanism |
|--------|-----------------|---------------|
| `capture_text` | `el.textContent` of the selected element | `Runtime.evaluate` |
| `capture_html` | `el.innerHTML` of the selected element | `Runtime.evaluate` |
| `capture_attribute` | `el.getAttribute(name)` for a specific attribute | `Runtime.evaluate` |
| `capture_value` | `el.value` for input elements | `Runtime.evaluate` |
| `capture_screenshot` | Visual snapshot of JUST that element (not full page) | `DOM.getBoxModel` + `Page.captureScreenshot(clip)` |
| `capture_url` | `window.location.href` | `Runtime.evaluate` |
| `capture_computed_style` | `getComputedStyle(el)[prop]` for a specific CSS property | `Runtime.evaluate` |
| `capture_console` | Start scoped `console.log` capture (see §5) | `Runtime.consoleAPICalled` |

### 3.3 New: Assert Actions — Full Roster

Assertions validate live DOM state or previously captured values.
All assertion steps use `action: "assert"` with an `assertion_type`
that specifies the check. The full type set:

#### Text Assertions (on el.textContent)

| assertion_type | What it validates | Expected format |
|---------------|------------------|-----------------|
| `text_equals` | textContent === expected | string |
| `text_contains` | textContent includes substring | string |
| `text_not_contains` | textContent does NOT include substring | string |
| `text_starts_with` | textContent starts with prefix | string |
| `text_ends_with` | textContent ends with suffix | string |
| `text_matches` | textContent matches regex pattern | regex string |
| `text_one_of` | textContent is one of N acceptable values | list of strings |
| `text_empty` | textContent is empty / whitespace-only | (none) |
| `text_not_empty` | textContent is NOT empty | (none) |

#### Value Assertions (on el.value — inputs, textareas, selects)

| assertion_type | What it validates | Expected format |
|---------------|------------------|-----------------|
| `value_equals` | el.value === expected | string |
| `value_contains` | el.value includes substring | string |
| `value_empty` | el.value is empty | (none) |
| `value_not_empty` | el.value is NOT empty | (none) |

#### Attribute Assertions (on el.getAttribute)

| assertion_type | What it validates | Expected format |
|---------------|------------------|-----------------|
| `attribute_equals` | getAttribute(name) === expected | string (+ `assertion_attribute`) |
| `attribute_contains` | getAttribute(name) includes substring | string (+ `assertion_attribute`) |
| `attribute_exists` | getAttribute(name) !== null | (none, just `assertion_attribute`) |
| `attribute_not_exists` | getAttribute(name) === null | (none, just `assertion_attribute`) |

#### HTML / Structure Assertions (on el.innerHTML or children)

| assertion_type | What it validates | Expected format |
|---------------|------------------|-----------------|
| `html_contains` | innerHTML includes substring | string |
| `html_equals` | innerHTML === expected | string |
| `children_count` | el.children.length === N | integer |
| `children_count_gt` | el.children.length > N | integer |
| `children_count_lt` | el.children.length < N | integer |

#### Element State Assertions (DOM state checks)

| assertion_type | What it validates | Expected format |
|---------------|------------------|-----------------|
| `exists` | Element matching selector is in DOM | (none) |
| `not_exists` | Element matching selector is NOT in DOM | (none) |
| `visible` | Element is visible (display, visibility, opacity, rect) | (none) |
| `hidden` | Element is NOT visible | (none) |
| `enabled` | el.disabled === false | (none) |
| `disabled` | el.disabled === true | (none) |
| `checked` | el.checked === true (checkbox/radio) | (none) |
| `not_checked` | el.checked === false | (none) |
| `focused` | document.activeElement === el | (none) |
| `selected` | option.selected === true | (none) |

#### CSS / Style Assertions

| assertion_type | What it validates | Expected format |
|---------------|------------------|-----------------|
| `css_class_present` | el.classList.contains(className) | class name string |
| `css_class_absent` | !el.classList.contains(className) | class name string |
| `css_property_equals` | getComputedStyle(el)[prop] === expected | string (+ `assertion_attribute` for prop name) |

#### Count Assertions (querySelectorAll — multiple elements)

| assertion_type | What it validates | Expected format |
|---------------|------------------|-----------------|
| `count_equals` | querySelectorAll(selector).length === N | integer |
| `count_gt` | querySelectorAll(selector).length > N | integer |
| `count_lt` | querySelectorAll(selector).length < N | integer |
| `count_gte` | querySelectorAll(selector).length >= N | integer |

#### Numeric Assertions (element text or value parsed as number)

| assertion_type | What it validates | Expected format |
|---------------|------------------|-----------------|
| `numeric_equals` | parseFloat(text) === N | number |
| `numeric_gt` | parseFloat(text) > N | number |
| `numeric_lt` | parseFloat(text) < N | number |
| `numeric_between` | N1 <= parseFloat(text) <= N2 | `"N1,N2"` or list `[N1, N2]` |

#### Page-Level Assertions (no element needed)

| assertion_type | What it validates | Expected format |
|---------------|------------------|-----------------|
| `url_equals` | window.location.href === expected | string |
| `url_contains` | window.location.href includes substring | string |
| `title_equals` | document.title === expected | string |
| `title_contains` | document.title includes substring | string |

#### Cross-Step Assertions (compare against previously captured data)

| assertion_type | What it validates | Expected format |
|---------------|------------------|-----------------|
| `captured_equals` | Value captured in step X === expected | string (+ `capture_step_id`) |
| `captured_contains` | Value captured in step X includes substring | string (+ `capture_step_id`) |
| `captured_changed` | Current live value !== value captured in step X | (none, + `capture_step_id`) |
| `captured_unchanged` | Current live value === value captured in step X | (none, + `capture_step_id`) |

### 3.4 New: Diagnostic Actions

Debug probes that can be placed ANYWHERE — inline in the main flow or
within diagnostic branches.

| Action | What it does | Output |
|--------|-------------|--------|
| `inject_js` | Execute user-written JS in page context | Captured return value + console.log output |
| `capture_console` | Start/stop console.log capture scope | All console output within scope |
| `diag_screenshot` | Full-page or element screenshot for evidence | Stored image |
| `diag_capture` | Same as capture_text/html/attr but tagged as diagnostic | Value stored in diagnostic context |

---

## 4. Assertion Configuration Model

### 4.1 AssertConfig

```python
class AssertConfig:
    # ── What source to check ───────────────────────────
    capture_type: str         # "text", "html", "attribute", "value",
                              # "screenshot", "url", "computed_style",
                              # "count", "state"
    attribute_name: str       # For attribute/css_property checks
    capture_step_id: str      # For cross-step assertions — references
                              # the step ID whose captured value to compare

    # ── The check ──────────────────────────────────────
    check_type: str           # Full roster — see §3.3 tables above
    expected: str | list      # Expected value(s) — string, number, list,
                              # regex pattern, or range
    case_sensitive: bool      # Default True

    # ── Failure routing ────────────────────────────────
    on_pass: str              # Step ID to continue to
    on_fail: FailureRoute
```

### 4.2 FailureRoute

```python
class FailureRoute:
    mode: str                 # "fail" | "continue" | "branch"
    # mode == "fail": hard stop, mark run as failed
    # mode == "continue": mark step as failed, continue to on_pass step
    # mode == "branch": route to one of the defined branches

    branches: list[Branch]    # Only if mode == "branch"

class Branch:
    id: str                   # Unique branch ID
    label: str                # "Diagnose", "Fallback", custom
    icon: str                 # "🔍", "🔄", "⛔", custom
    first_step_id: str        # Head of the branch step sequence
    action: str | None        # "cancel" for abort-only branches (no steps)
```

### 4.3 Example: Full Assertion

```json
{
  "id": "assert-content-check",
  "action": "assert",
  "selector": "div.theme-doc-markdown",
  "assert_config": {
    "capture_type": "text",
    "check_type": "contains",
    "expected": "Hello World",
    "case_sensitive": false,
    "on_pass": "step-8",
    "on_fail": {
      "mode": "branch",
      "branches": [
        {
          "id": "diagnose-1",
          "label": "Diagnose",
          "icon": "🔍",
          "first_step_id": "diag-step-1"
        },
        {
          "id": "fallback-1",
          "label": "Fallback",
          "icon": "🔄",
          "first_step_id": "fallback-step-1"
        },
        {
          "id": "abort-1",
          "label": "Abort",
          "icon": "⛔",
          "action": "cancel"
        }
      ]
    }
  }
}
```

---

## 5. Console Capture — Scoped to Diagnostic Branches

### 5.1 How It Works

CDP provides `Runtime.consoleAPICalled` events. When a diagnostic branch
activates, we subscribe to these events. All console output (log, warn, error,
info) is captured and stored.

```
Normal flow: step1 → step2 → step3
                                       (no console capture)

Diagnostic branch: diagStep1 → diagStep2 → diagStep3
                   ┌─ console capture ON ──────────────┐
                   │  [21:45:01] API call failed: 404   │
                   │  [21:45:01] Retry scheduled 3000ms  │
                   │  [21:45:02] AppState.loading = true  │
                   └─ console capture OFF ─────────────┘
                   All captured → attached to failure report
```

### 5.2 Inline Diagnostics (Not Just Branches)

Diagnostic steps can be placed ANYWHERE in the main flow:

```
step1 → step2 → [DIAG: inject_js("console.log(appState)")] → step3
```

No branching needed. The injected JS executes, its console output is
captured, and the result is stored in the step result. This is a
non-destructive probe — it doesn't change flow, just collects data.

### 5.3 Console Capture Scope Rules

| Context | Capture Behavior |
|---------|-----------------|
| **Normal flow, no diag steps** | No console capture (default) |
| **Inline diag step** | Capture for that step only |
| **Diagnostic branch** | Capture starts at branch entry, ends at branch exit |
| **Assert after diagnostic** | Previous capture data available for assertion |
| **Nested assertions in branches** | Each sub-scope maintains its own capture buffer |

### 5.4 CDP Implementation

```python
# Enable console capture:
session.send_command("Runtime.enable")

# Listen for console events (via CDP event stream):
# Event: Runtime.consoleAPICalled
# Data: { type: "log"|"warn"|"error", args: [...], timestamp }

# Disable when scope ends:
session.send_command("Runtime.disable")
```

---

## 6. Branching Engine — Replayer Evolution

### 6.1 Current Replayer Flow

```python
for i, step in enumerate(sorted_steps):
    # visibility check → execute step → pacing → record result
```

Linear iteration. No branching. No decision points.

### 6.2 Evolved Replayer Flow

```python
current_step_id = suite.start_step_id

while current_step_id and not stop_event.is_set():
    step = suite.steps[current_step_id]

    if step.action == "assert":
        # ── Execute assertion ──────────────────────
        captured = _capture_value(step, session)
        passed = _check_assertion(step.assert_config, captured)

        if passed:
            current_step_id = step.assert_config.on_pass
        else:
            route = step.assert_config.on_fail
            if route.mode == "fail":
                # Hard stop — mark run failed
                break
            elif route.mode == "continue":
                # Soft fail — record failure, continue
                current_step_id = step.assert_config.on_pass
            elif route.mode == "branch":
                # ── Branch selection ───────────────
                if interactive_mode:
                    # Present choices to user via SSE
                    branch = _wait_for_user_choice(route.branches)
                else:
                    # Automated: take first non-abort branch
                    branch = route.branches[0]

                if branch.action == "cancel":
                    break
                else:
                    # Enter branch — enable console capture if diagnostic
                    _enable_console_capture(session)
                    current_step_id = branch.first_step_id

    elif step.action in ("inject_js", "diag_capture", "diag_screenshot"):
        # ── Execute diagnostic ─────────────────────
        result = _execute_diagnostic(step, session)
        # Store in diagnostic context
        current_step_id = step.next_step_id

    else:
        # ── Execute normal action ──────────────────
        result = _execute_step(step.to_dict(), ...)
        current_step_id = step.next_step_id
```

### 6.3 Branch-Back (Re-enter at Assertion Point)

The execution trace records every step executed and which branch was taken:

```python
class ExecutionTrace:
    entries: list[TraceEntry]

class TraceEntry:
    step_id: str
    result: str              # "passed", "failed", "skipped"
    branch_taken: str | None # Branch ID if at assertion point
    captured_value: Any      # Captured data (text, HTML, screenshot path)
    console_log: list[str]   # Console output during this step
    timestamp: str
```

**Branch-back** means:
1. User reviews the execution trace in the admin panel
2. Sees an assertion point where branch "Diagnose" was taken
3. Clicks "Re-run from here" → chooses "Fallback" instead
4. Replayer re-executes all steps from start up to the assertion point
5. At the assertion, takes the "Fallback" branch instead
6. Continues from there

This requires re-execution from the beginning (no page state snapshots),
but it's deterministic because the same steps produce the same state.

---

## 7. Recording UX — Creating Assertions

### 7.1 During Recording: Badge on Click

When the user clicks an element during recording:

1. The `click` action is recorded as normal
2. A small badge (●) appears near the element or in the recording toolbar
3. Badge has a tooltip: "Add assertion for this element"
4. Clicking the badge opens the Assertion Config modal

### 7.2 Assertion Config Modal

```
┌─────────────────────────────────────────────────────┐
│  🔍 Assertion for: div.theme-doc-markdown            │
│                                                      │
│  ── What to Capture ──────────────────────────────   │
│  ● Text content    ○ innerHTML    ○ Value            │
│  ○ Attribute: [data-status    ]   ○ Screenshot       │
│                                                      │
│  ── Live Preview ─────────────────────────────────   │
│  Current value: "Hello World"                        │
│  ─────────────────────────────────────────────────   │
│                                                      │
│  ── Assertion Check ──────────────────────────────   │
│  Check type: [contains      ▾]                       │
│  Expected:   [Hello World              ]             │
│  ☐ Add alternative: [___________]  (one-of)          │
│  ☐ Case sensitive                                    │
│                                                      │
│  ── On Failure ───────────────────────────────────   │
│  ○ Hard fail (stop execution)                        │
│  ○ Soft fail (mark failed, continue)                 │
│  ● Branch:                                           │
│    ┌ Branches ──────────────────────────────────┐    │
│    │ 🔍 Diagnose    [Record branch...]          │    │
│    │ 🔄 Fallback    [Record branch...]          │    │
│    │ ⛔ Abort                                    │    │
│    │ [+ Add branch]                              │    │
│    └────────────────────────────────────────────┘    │
│                                                      │
│  ── Diagnostic Actions (pre-branch) ──────────────   │
│  [+ Inject JS]                                       │
│  [+ Capture element]                                 │
│  [+ Screenshot]                                      │
│                                                      │
│              [Cancel]  [Save Assertion]               │
└─────────────────────────────────────────────────────┘
```

### 7.3 Recording Branch Steps

When user clicks "Record branch..." for a branch:

1. Recording toolbar shows: "Recording: Diagnose branch for Assert #3"
2. User performs actions in the target page
3. These actions are recorded as steps in the branch
4. User can add inline diagnostic steps (inject JS, captures)
5. User can add ANOTHER assertion within the branch (nested!)
6. User clicks "Stop branch recording"
7. Returns to the assertion config modal

### 7.4 Post-Recording Editing (Admin Panel)

The admin panel suite editor allows:

- Adding assertions to existing suites (no re-recording needed)
- Editing assertion conditions and expected values
- Adding/removing/reordering branch steps
- Adding inline diagnostic probes between any steps
- Visual graph view of the step flow

---

## 8. Admin Panel Views

### 8.1 Suite Editor — Graph View

A visual flow editor showing steps as nodes:

```
  ┌──────┐    ┌──────┐    ┌──────┐    ┌────────────┐
  │ ping │───▶│click │───▶│click │───▶│  ASSERT    │
  │  s1  │    │  s2  │    │  s3  │    │ text == X  │
  └──────┘    └──────┘    └──────┘    └─────┬──────┘
                                         ┌──┼──────┐
                                         │  │      │
                                    ✅ Pass │   ❌ Fail
                                         │  │      │
                                    ┌────▼┐ │ ┌────▼────┐
                                    │type │ │ │🔍 Diag  │
                                    │ s4  │ │ │ branch  │
                                    └─────┘ │ └─────────┘
                                            │
                                       ┌────▼────┐
                                       │🔄 Fall  │
                                       │ branch  │
                                       └─────────┘
```

- Green edges = pass path
- Red edges = fail paths
- Orange nodes = diagnostic branches
- Blue nodes = fallback branches
- Click any node to edit

### 8.2 Results Viewer — Path Trace

After a run:

```
  Run: 8393dd53 — test01 — PASSED (13/13)
  ──────────────────────────────────────────────

  ✅ s1: ping                           3ms
  ✅ s2: click div:nth-child(2)         212ms
  ✅ s3: click div.theme-doc-markdown   559ms
  ✅ a1: ASSERT text contains "Hello"   45ms
       │  Expected: "Hello"
       │  Actual:   "Hello World"
       │  Route: PASS → s4
  ✅ s4: type textarea                  561ms
  ✅ s5: click article                  213ms
  ✅ s6: click div.theme-doc-markdown   556ms
  ❌ a2: ASSERT text contains "Hello"   42ms
       │  Expected: "Hello"
       │  Actual:   "Loading..."
       │  Route: FAIL → diagnose branch
       │
       │  ┌── Diagnostic Branch ───────────────────┐
       │  │ 🔍 inject_js: console.log(appState)    │
       │  │    → { loading: true, error: null }     │
       │  │ 🔍 capture_text: #status → "Fetching"  │
       │  │ 📋 Console captured:                    │
       │  │    [21:45:01] API: GET /content (pending)│
       │  │    [21:45:02] API: 200 OK               │
       │  └────────────────────────────────────────┘
       │
       │  [🔄 Re-run from here: Fallback]
       │  [🔍 Re-run from here: Diagnose]
```

### 8.3 Live Replay View

During replay with assertions:

- Normal step progress (existing behavior)
- At assertion: show ✅/❌ with actual vs expected
- At branch point (interactive mode):
  - Pause execution
  - Show branch options as buttons
  - User picks which branch to take
  - Resume execution in chosen branch
- Console log panel (expandable) showing captured output

---

## 9. Failure Report Structure

### 9.1 What Gets Stored

```python
class StepResult:
    step_id: str
    action: str
    status: str              # "passed", "failed", "skipped"
    duration_ms: int
    error: str | None

    # ── NEW ────────────────────────────────────────
    captured_value: Any          # Text, HTML, attribute value, screenshot path
    assertion_expected: Any      # What was expected
    assertion_actual: Any        # What was found
    assertion_check: str         # "equals", "contains", etc.
    branch_taken: str | None     # Which branch was taken on failure
    console_log: list[str]       # Console output captured during this step
    diagnostic_results: list     # Results of diagnostic steps in branch
    screenshot_path: str | None  # Element screenshot if captured
```

### 9.2 What the Failure Report Contains

For each failed assertion:

| Section | Content |
|---------|---------|
| **Assertion** | Check type, expected value, actual value, selector |
| **Element screenshot** | Visual snapshot of the element at time of failure |
| **Diagnostic branch** | All steps executed, their results, captured values |
| **Console log** | All console.log output from diagnostic scope |
| **Branch taken** | Which failure route was followed |
| **Re-run options** | Links to re-run from this point with different branches |

---

## 10. Connection to Scripts System M7 (Execution Plans)

### 10.1 The Shared Pattern

Execution Plans (M7) and CDP test branching are the SAME pattern
at different levels:

| Concept | Scripts M7 | CDP Tests |
|---------|-----------|-----------|
| **Sequence** | Plan = ordered list of scripts | Suite = ordered graph of steps |
| **Checkpoint** | Script completes → next | Step completes → next |
| **Assertion** | Script exit code / output check | Element value check |
| **Branching** | On failure → different script | On failure → different steps |
| **Modes** | fully_automated, semi_automated, interactive | automated, interactive (branch choice) |
| **Events** | script:started, script:completed | step_start, step_passed |

### 10.2 CDP Suites as Plan Steps

Once assertions exist, a CDP test suite becomes a valid step in an
Execution Plan:

```yaml
execution_plan:
  name: "Full deployment validation"
  steps:
    - script: deploy_to_staging.sh
      on_fail: abort
    - cdp_test: smoke_test_homepage
      on_fail: branch
      branches:
        - label: Rollback
          script: rollback_deployment.sh
        - label: Diagnose
          script: collect_logs.sh
    - script: notify_team.py
```

### 10.3 Shared Branching Primitives

The branching engine should be built as a shared module, not duplicated:

```
src/core/services/branching/
    ├── __init__.py
    ├── models.py          # Branch, FailureRoute, ExecutionTrace
    ├── engine.py           # Graph traversal, branch selection
    └── console_capture.py  # CDP console capture utility
```

Both the CDP replayer and the Scripts executor import from this.

---

## 11. Implementation Phases — Layered Delivery

Each phase is independently useful. No phase is wasted if we stop.

### Phase A: Assertion Steps (Foundation)

**What**: Add `assert` step type. Simple pass/fail (no branching).
Check text/value/contains/exists. Hard fail or soft continue.

**Changes**:
- `models.py`: Add `AssertConfig` model
- `replayer.py`: Handle `assert` action type
- `_cdp_test.html`: Show assertion results in replay view
- Recording: Not yet — assertions added manually via suite JSON editing

**Result**: Tests can VERIFY, not just replay.

### Phase B: Capture Actions

**What**: Add capture_text, capture_html, capture_attribute,
capture_screenshot actions. Available during recording.

**Changes**:
- `replayer.py`: Implement capture actions
- `models.py`: Add capture fields to step result
- `_cdp_test.html`: Badge on clicked elements → capture config

**Result**: Users can extract data from elements during recording.

### Phase C: Recording UX for Assertions

**What**: Badge → Assertion Config modal during recording.
Admin panel suite editor for post-recording assertion editing.

**Changes**:
- `_cdp_test.html`: Badge UI, assertion config modal
- `_cdp_test.html`: Suite editor with assertion management
- Step model: next_step_id replaces sequence for flow

**Result**: Users can create assertions without editing JSON.

### Phase D: Diagnostic Actions

**What**: inject_js, console capture, diagnostic screenshots.
Inline diagnostics (anywhere) + diagnostic context storage.

**Changes**:
- `replayer.py`: Execute inject_js, capture console
- `cdp_client.py`: Runtime.enable for console events
- `models.py`: DiagnosticConfig, console_log field
- `_cdp_test.html`: Diagnostic step UI, console viewer

**Result**: Users can debug failures with injected JS and console capture.

### Phase E: Branching Engine

**What**: Failure routing with multiple branches. Replayer follows
graph instead of list. Interactive mode for branch selection.

**Changes**:
- `models.py`: FailureRoute, Branch models
- `replayer.py`: Graph traversal, branch routing
- `_cdp_test.html`: Branch selection UI (interactive mode)
- Suite storage: Dict-based step storage with graph edges

**Result**: Conditional execution — different paths for different outcomes.

### Phase F: Branch-Back & Trace

**What**: Execution trace recording. Re-run from assertion point
with different branch choice. Admin panel trace viewer.

**Changes**:
- `models.py`: ExecutionTrace model
- `replayer.py`: Trace recording, re-run from step
- `_cdp_test.html`: Trace viewer, re-run buttons

**Result**: Post-hoc exploration of failure paths.

### Phase G: Execution Plan Integration (connects to Scripts M7)

**What**: CDP test suites as steps in Execution Plans.
Shared branching primitives. Plan-level failure routing.

**Changes**:
- `src/core/services/branching/`: Shared branching module
- Scripts M7 executor: Import branching primitives
- CDP replayer: Import branching primitives
- Plan model: CDP suite step type

**Result**: Full integration — scripts and CDP tests composable.

---

## 12. Cross-References

| Reference | Location |
|-----------|----------|
| Scripts System Overview | `.agent/plans/scripts-system/scripts-system.md` |
| Scripts M7 (Execution Plans) | `.agent/plans/scripts-system/scripts-system-M7-plans.md` |
| Current CDP test models | `src/core/services/cdp_test/models.py` |
| Current replayer | `src/core/services/cdp_test/replayer.py` |
| Current CDP client | `src/ui/web/cdp_client.py` |
| Current recording/replay UI | `src/ui/web/templates/scripts/integrations/_cdp_test.html` |
| Current replay route | `src/ui/web/routes/cdp_test/replay.py` |
| Existing event bus | `src/core/services/event_bus.py` |
| Existing replay robustness layers | Layers 1-5 in replayer.py (visibility, retry) |

---

## 13. Open Questions (To Resolve Before Implementation)

| # | Question | Options | Impact |
|---|----------|---------|--------|
| 1 | Branch step recording UX | Sequential (record one branch at a time) vs. modal editor | Phase C |
| 2 | Nested assertions in branches | Allow or limit to one level? | Phase E complexity |
| 3 | Visual regression testing | Compare screenshots pixel-by-pixel or just store as evidence? | Phase B scope |
| 4 | Branch convergence | Can branches rejoin the main flow, or do they always terminate? | Phase E model |
| 5 | Assertion timeout | How long to wait for an element before declaring assertion failed? | Phase A |
| 6 | Recording format migration | Auto-migrate old suites or load-time conversion only? | Phase E |
| 7 | Console capture performance | Always-on vs. scoped? Memory impact of capturing all console output? | Phase D |
| 8 | Interactive mode vs automated | Default behavior when branches exist but no user is watching? | Phase E |
