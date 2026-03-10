# Chunk 5: Execution Plans — Master Plan

> **Status**: In Progress (5a ✅, 5b+5c ✅, 5d ✅, 5e-1 ✅, 5e-2 ✅, 5e-3 ✅ — all sub-chunks complete)
> **Created**: 2026-03-09
> **Parent**: `scripts-system-M7-plans.md` → Chunk 5
> **Depends on**: M1 (Script System) ✅, Chunk 4 (Replayer Multi-Endpoint) ✅

---

## 1. What Is An Execution Plan

An Execution Plan is a **chain of test scripts and CDP test suites** that runs as
a coordinated sequence. Variables flow from step to step — output of step N
becomes input for step N+1. Plans support three execution modes that give users
control over how the chain unfolds.

**It is NOT** an extension of the CDP Test modal. It is a **new top-level modal**
that can drill down into the underlying test/script layers when viewing individual
step results.

### Key properties

| Property | Value |
|----------|-------|
| Storage location | `.state/cdp-plans/` |
| Plan definitions | `.state/cdp-plans/plans/{id}.json` |
| Run results | `.state/cdp-plans/results/{id}.json` |
| Browser lifecycle | Kill on plan finish by default, option to keep alive |
| Variable namespace | Shared — scripts and CDP tests can chain |
| Concurrent plans | One at a time (replayer singleton constraint) |

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                     EXECUTION PLANS MODAL                        │
│                     (new top-level UI)                            │
│                                                                  │
│  ┌────────────┐ ┌──────────────┐ ┌──────────────┐               │
│  │  Plan List  │ │ Plan Editor  │ │   Plan Run   │               │
│  │  (home)     │ │ (create/edit)│ │   (live)     │               │
│  └────────────┘ └──────────────┘ └──────┬───────┘               │
│                                         │                        │
│                              ┌──────────┴──────────┐             │
│                              │   Drill-Down View    │             │
│                              │                      │             │
│                              │  • Script → output   │             │
│                              │  • CDP test → replay │             │
│                              │  • Checkpoint → msg  │             │
│                              └──────────────────────┘             │
└──────────────────────────────────────────────────────────────────┘
                              │
                     plan_executor.py
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
    script steps        cdp_test steps       checkpoint steps
    (M1 executor)       (replayer)            (pause + resume)
         │                    │
    execute_script()    start_replay()
    returns dict        runs in thread
    with lines[]        emits SSE events
    (synchronous)       (asynchronous)
```

---

## 3. Data Models (Chunk 5a)

### 3.1 ExecutionPlan

The plan definition. Stored as JSON.

```python
@dataclass
class ExecutionPlan:
    id: str                             # uuid
    name: str
    description: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    mode: str = "fully_automated"       # fully_automated | semi_automated | interactive
    browser_config: BrowserConfig | None = None
    variables: dict[str, str] = field(default_factory=dict)  # initial defaults
    created_at: str = ""
    updated_at: str = ""
```

### 3.2 PlanStep

One step in the chain.

```python
@dataclass
class PlanStep:
    id: str                             # uuid
    sequence: int
    type: str                           # "script" | "cdp_test" | "checkpoint" | "conditional"
    name: str = ""

    # For type="script":
    script_id: str = ""                 # From M1 registry (e.g. "audit-docker")
    script_params: dict[str, str] = field(default_factory=dict)

    # For type="cdp_test":
    suite_id: str = ""                  # CDP test suite UUID
    suite_variables: dict[str, str] = field(default_factory=dict)

    # For type="checkpoint":
    checkpoint_message: str = ""        # What to show the user at pause

    # For type="conditional":
    condition_step_id: str = ""         # Which step's result to check
    condition: str = "passed"           # "passed" | "failed"
    then_step_id: str = ""             # Step to jump to if condition met
    else_step_id: str = ""             # Step to jump to otherwise (or skip)

    optional: bool = False              # If True, failure doesn't fail the plan
    timeout_seconds: int = 0            # 0 = use default from config/executor

    # Variable chaining
    produces: list[str] = field(default_factory=list)   # variable names this step outputs
    consumes: list[str] = field(default_factory=list)    # variable names this step needs
```

### 3.3 BrowserConfig

How Chrome is managed for the plan's browser-dependent steps.

```python
@dataclass
class BrowserConfig:
    mode: str = "separate_instance"     # "separate_instance" | "same_browser" | "none"

    # For separate_instance:
    headless: bool = False
    port: int = 0                       # 0 = auto-allocate
    keep_alive: bool = False            # DEFAULT: kill after plan finishes

    # Resolved at runtime (not stored):
    # - actual_port: int
    # - instance: ChromeInstance
```

### 3.4 PlanRunResult

The result of a plan execution. Stored as JSON.

```python
@dataclass
class PlanRunResult:
    id: str                             # uuid (run ID)
    plan_id: str
    plan_name: str
    status: str = "running"             # running | passed | failed | partial | cancelled
    mode: str = ""                      # execution mode used
    step_results: list[StepResult] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)  # final accumulated namespace
    chrome_instance: dict | None = None  # instance info if separate Chrome was launched
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0
    error: str = ""
```

### 3.5 StepResult

Result of one step within a plan run.

```python
@dataclass
class StepResult:
    step_id: str
    step_name: str
    step_type: str                      # "script" | "cdp_test" | "checkpoint" | "conditional"
    status: str = "pending"             # pending | running | passed | failed | skipped | cancelled
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0
    error: str = ""

    # Script step outputs:
    script_run_id: str = ""
    script_exit_code: int = 0
    script_lines: list[str] = field(default_factory=list)

    # CDP test step outputs:
    replay_run_id: str = ""
    replay_passed: int = 0
    replay_failed: int = 0
    replay_total: int = 0

    # Variables produced by this step:
    variables_produced: dict[str, str] = field(default_factory=dict)
```

---

## 4. Variable Chaining Design

### 4.1 How variables flow

```
Plan variables (initial defaults)
  ↓
Step 1 (script) → runs with current namespace → produces new vars → merge
  ↓
Step 2 (cdp_test) → runs with accumulated namespace → produces new vars → merge
  ↓
Step 3 (checkpoint) → pauses, shows accumulated vars
  ↓
...
  ↓
Final namespace = all accumulated variables
```

### 4.2 How scripts produce variables

Convention: scripts output `DCP_VAR_KEY=VALUE` lines to stdout.
The plan executor parses these from the script's output lines.

```python
# In the script:
print("DCP_VAR_DEPLOY_PATH=/opt/app/v2")
print("DCP_VAR_CONFIG_OK=true")
```

The executor scans output lines for `DCP_VAR_` prefix, strips it, and adds
`DEPLOY_PATH` and `CONFIG_OK` to the shared namespace.

### 4.3 How CDP tests produce variables

CDP test suites already have a variables system. The replayer can return
captured values (e.g. from `capture_attribute` diagnostic steps). These
get merged into the shared namespace.

### 4.4 How checkpoint steps use variables

Interactive/semi-automated mode: the checkpoint pause shows the user
the current variable namespace so they can review intermediate state
before deciding to continue.

---

## 5. Execution Modes Design

### 5.1 Fully Automated

Runs all steps sequentially. No pauses. Stops on first non-optional failure.

```
[start] → step1 → step2 → step3 → ... → [done]
                                   ↑
                          (fail + !optional → abort)
```

### 5.2 Semi-Automated

Runs until a checkpoint step, then pauses. User reviews and resumes.

```
[start] → step1 → step2 → [CHECKPOINT: pause]
                                ↓
                         user clicks Resume
                                ↓
                           step4 → step5 → [done]
```

### 5.3 Interactive

Pauses after EVERY step. User reviews each result and chooses:
- **Continue** → run next step
- **Skip** → skip next step, move to the one after
- **Abort** → cancel the plan

```
[start] → step1 → [PAUSE] → user: Continue
                                ↓
         step2 → [PAUSE] → user: Skip step3
                                ↓
         step4 → [PAUSE] → user: Continue → step5 → [done]
```

### 5.4 Resume/Pause mechanism

The executor runs in a background thread (like the replayer). When paused:
1. It sets `_paused = True` and waits on a `threading.Event`
2. The API receives `POST /plans/run/{id}/resume` → sets the event
3. The executor thread wakes up and continues

```python
# In plan_executor:
class _PlanRun:
    run_id: str
    thread: Thread
    stop_event: Event    # cancellation
    resume_event: Event  # resume from pause
    paused: bool
    current_step_sequence: int
```

---

## 6. Integration Points — What Exists, What's Needed

### 6.1 Script Executor (M1)

**Exists**: `execute_script(project_root, script_id, params=, output_target=)`
**Returns**: `{"ok": bool, "run_id": str, "exit_code": int, "lines": list[str], ...}`
**Behavior**: Synchronous — blocks until script finishes
**What we need**: Parse `DCP_VAR_` lines from `result["lines"]` for variable extraction

**No changes needed to `execute_script`** — it already returns all output lines.

### 6.2 CDP Test Replayer

**Exists**: `start_replay(suite, target_id, variables=, cdp_port=, ...)`
**Returns**: `run_id` string (async — starts a thread)
**Behavior**: Asynchronous — runs in a background thread, fires SSE events
**Problem**: The plan executor needs to WAIT for the replay to finish.

**Solution options** (to be decided in Chunk 5b deep-dive):
1. **Thread.join()**: `start_replay` returns the run_id → poll `get_active_run()`
   until `None` → then read the result from storage
2. **Result holder**: `start_replay` already has `result_holder: list[TestRunResult]`
   (line 2736 in replayer.py) but it's a local variable. Could be exposed.
3. **Synchronous wrapper**: New `replay_suite_sync(...)` that calls `replay_suite`
   directly (not in a thread) and returns the result. Plan executor manages its
   own thread, so the replayer doesn't need to.

Option 3 is cleanest — the plan executor already runs in its own thread, so it
can call `replay_suite()` directly (synchronously) instead of going through
`start_replay()` which adds another thread layer.

### 6.3 Chrome Launcher

**Exists**: `get_launcher().launch(config)` → `ChromeInstance`
**Exists**: `get_launcher().kill_instance(instance)`
**What we need**: Launch at plan start, kill at plan end (unless `keep_alive`)

**No changes needed** — Chunk 2a/2b already provides this.

### 6.4 Event Bus

**Exists**: `bus.publish(event_type, key=, data=)`
**SSE event types for plans**:
- `plan:start` → `{run_id, plan_id, plan_name, total_steps}`
- `plan:step_start` → `{run_id, step_id, step_name, step_type, sequence}`
- `plan:step_done` → `{run_id, step_id, status, variables_produced, duration_ms}`
- `plan:checkpoint` → `{run_id, step_id, message, variables}`
- `plan:done` → `{run_id, status, passed, failed, total, duration_ms}`

**No changes needed to event bus** — just publish new event types.

### 6.5 CDP Test Storage

**Exists**: `get_suite(project_root, suite_id)` → `TestSuite | None`
**What we need**: Load suites referenced by plan steps for validation + execution

**No changes needed**.

### 6.6 Script Registry

**Exists**: `get_script(project_root, script_id)` → `ScriptMeta | None`
**What we need**: Validate that all script_ids in plan steps exist

**No changes needed**.

---

## 7. Sub-Chunk Breakdown

### Chunk 5a: Data Models + Storage

**Scope**: Pure data, no execution logic, no routes, no UI.

**New files**:
- `src/core/services/scripts/plans.py` — All dataclass models
- `src/core/services/scripts/plan_storage.py` — JSON CRUD

**Storage layout**:
```
.state/
  cdp-plans/
    plans/
      {uuid}.json          # ExecutionPlan
    results/
      {uuid}.json          # PlanRunResult
```

**Deliverables**:
1. `ExecutionPlan` with `to_dict()` / `from_dict()` serialization
2. `PlanStep` with all 4 step types
3. `BrowserConfig` with defaults (`keep_alive=False`)
4. `PlanRunResult` and `StepResult` for run tracking
5. `plan_storage.py` CRUD: `save_plan`, `get_plan`, `list_plans`, `delete_plan`,
   `save_result`, `get_result`, `list_results`

**Testing**: Create a plan in Python, save it, load it, verify round-trip.

**Dependencies**: None
**Risk**: Low — pure data structures + file I/O

---

### Chunk 5b: Plan Executor Core

**Scope**: The execution engine. Runs plans, routes steps, manages browser,
chains variables.

**New file**: `src/core/services/scripts/plan_executor.py`

**Core responsibilities**:
1. Validate plan (all scripts exist, all suites exist, all consumed vars declared)
2. Resolve browser config (launch if `separate_instance`, verify if `same_browser`)
3. Execute steps sequentially:
   - `script` → call `execute_script()` synchronously
   - `cdp_test` → call `replay_suite()` directly (not `start_replay`)
   - `checkpoint` → just record, no pause (pausing added in 5c)
   - `conditional` → evaluate condition, decide which step to execute
4. After each step: extract `DCP_VAR_` outputs, merge into namespace
5. On finish: kill browser if `!keep_alive`, emit `plan:done`, save result
6. Cancellation via `stop_event`

**Key design decision**: The plan executor calls `replay_suite()` directly
(the synchronous function) instead of `start_replay()` (the async wrapper).
This is because the executor already runs in its own thread.

**Singleton**: Like the replayer, only one plan can run at a time.
```python
_active_plan_run: _PlanRun | None = None
_plan_lock = threading.Lock()
```

**Deliverables**:
1. `execute_plan(project_root, plan, callback=)` — main entry point
2. `start_plan(plan)` — async wrapper (starts thread, returns run_id)
3. `cancel_active_plan()` — set stop_event
4. `get_active_plan_run()` — return current run info

**Interaction with replayer**: When executing a `cdp_test` step, the executor
needs a `target_id` (Chrome tab). For `same_browser`, it can reuse the existing
CDP target. For `separate_instance`, it needs to discover or create a tab.
This is the same logic as the replay route (lines 72-134 of `replay.py`).

**Dependencies**: Chunk 5a (models + storage)
**Risk**: Medium — the tricky part is getting `replay_suite()` calls right
(it needs `target_id`, `ws_url`, proper callbacks, etc.)

---

### Chunk 5c: Execution Modes

**Scope**: Add `semi_automated` and `interactive` control flow to the executor.

**Modified file**: `src/core/services/scripts/plan_executor.py`

**What's added**:
1. `resume_event: threading.Event` on `_PlanRun`
2. Checkpoint pause logic: after a checkpoint step, wait on `resume_event`
3. Interactive pause logic: after EVERY step, wait on `resume_event`
4. API functions: `resume_plan(run_id)`, `skip_step(run_id)`, `abort_plan(run_id)`

**SSE events for modes**:
- `plan:paused` → `{run_id, step_id, reason:"checkpoint"|"interactive", message}`
- `plan:resumed` → `{run_id, step_id}`
- `plan:step_skipped` → `{run_id, step_id}`

**Dependencies**: Chunk 5b (executor core)
**Risk**: Medium — thread synchronization with resume/skip/abort

---

### Chunk 5d: API Routes

**Scope**: REST endpoints for plan CRUD + execution control.

**New files**:
- `src/ui/web/routes/plans/__init__.py` — Blueprint + sub-module imports
- `src/ui/web/routes/plans/crud.py` — CRUD endpoints
- `src/ui/web/routes/plans/execution.py` — Execute/cancel/resume/status

**Endpoints**:

| Method | Path | What |
|--------|------|------|
| `GET` | `/plans` | List all plans |
| `GET` | `/plans/{id}` | Get plan details |
| `POST` | `/plans` | Create plan |
| `PUT` | `/plans/{id}` | Update plan |
| `DELETE` | `/plans/{id}` | Delete plan |
| `POST` | `/plans/{id}/execute` | Start plan execution |
| `POST` | `/plans/run/{run_id}/cancel` | Cancel running plan |
| `POST` | `/plans/run/{run_id}/resume` | Resume from pause |
| `POST` | `/plans/run/{run_id}/skip` | Skip current step |
| `GET` | `/plans/run/{run_id}/status` | Get run status + step results |
| `GET` | `/plans/results` | List past results |
| `GET` | `/plans/results/{id}` | Get specific result |

**Blueprint registration**: Same pattern as `cdp_test_bp` — register on `/api` prefix.

**Dependencies**: Chunk 5a + 5b + 5c
**Risk**: Low — follows established route patterns

---

### Chunk 5e: Plan Modal UI

**Scope**: The full UI — new modal, plan management, execution view.

**New file**: `src/ui/web/templates/scripts/integrations/_plans.html`

**Views**:

1. **Plan List (Home)**
   - Table: name, step count, mode, last run status, last run date
   - Actions: ▶ Run, ✏️ Edit, 🗑️ Delete, ➕ Create New

2. **Plan Editor (Create/Edit)**
   - Plan name + description
   - Mode selector: fully_automated / semi_automated / interactive
   - Browser config: same_browser / separate_instance / none
   - Steps list:
     - Drag to reorder
     - Add step: script picker (from M1 registry), suite picker (from CDP tests),
       checkpoint (free text), conditional (pick step + condition)
     - Per step: optional toggle, timeout, produces/consumes vars
   - Initial variables: key=value pairs editor

3. **Plan Execution (Live)**
   - Progress bar (steps completed / total)
   - Step-by-step list: icon + name + status + duration
   - Variable namespace panel: shows accumulated vars in real-time
   - Controls: Cancel / Resume (when paused) / Skip (when paused in interactive)
   - Drill-down: click a completed step to see:
     - Script → output lines (inline terminal)
     - CDP test → replay summary (passed/failed steps)
     - Checkpoint → message shown

4. **Plan Results (Post-execution)**
   - Summary: pass/fail/skip per step, total duration
   - Variable trace: initial → accumulated → final
   - "Close test browser" button if separate instance was used
   - "Run Again" button

**How it integrates with the Scripts Panel**:
The Execution Plans modal is launched from a new button / tab in the Scripts panel,
alongside the existing CDP Tests button. They are peers, not parent-child.

**Dependencies**: Chunk 5d (API routes)
**Risk**: High — largest chunk, most UI work. May need sub-splitting:
- 5e-1: List + Run flow  
- 5e-2: Editor
- 5e-3: Live execution view + drill-down

---

## 8. Execution Order

```
5a (Models + Storage)           ← FIRST — no dependencies
  ↓
5b (Executor Core)              ← needs 5a
  ↓
5c (Execution Modes)            ← needs 5b
  ↓
5d (API Routes)                 ← needs 5a + 5b + 5c
  ↓
5e (Plan Modal UI)              ← needs 5d
  5e-1: List + basic run
  5e-2: Editor
  5e-3: Live execution + drill-down
```

Each sub-chunk gets its own detailed plan document before implementation.

---

## 9. Open Design Questions

### Q1: Conditional steps — how complex?

The current design has `condition_step_id` + `condition` (passed/failed) +
`then_step_id` / `else_step_id`. This is a simple if/else.

Should we support:
- (a) Simple if/else only (sufficient for M7)
- (b) Variable-based conditions (`if VAR_NAME == "value"`)
- (c) Full expression language

**Recommendation**: (a) for Chunk 5, with (b) as a natural extension later.

### Q2: Script output variable convention

`DCP_VAR_KEY=VALUE` in stdout. Alternatives:
- (a) `DCP_VAR_` prefix in stdout lines (proposed)
- (b) JSON blob in stdout (harder to implement for bash scripts)
- (c) Write to a temp file that the executor reads

**Recommendation**: (a) — simple, works for all script languages.

### Q3: CDP test variable extraction

How does a CDP test "produce" variables for the next step?
- (a) From diagnostic `capture_attribute` results
- (b) From a special "export" step type in the suite
- (c) Manual mapping in the plan step definition

**Recommendation**: (a) initially — diagnostic captures are already stored in
the test run result. The executor reads them and merges into the namespace.

### Q4: Plan editor — drag-and-drop or simple list?

- (a) Drag-and-drop reorder (more UX work)
- (b) Up/down arrow buttons (simpler)
- (c) Sequence number input (simplest)

**Recommendation**: (b) for M7 — feels interactive without the complexity of
full drag-and-drop.

### Q5: Chunk 5e sub-splitting

Should 5e be one chunk or three?

**Recommendation**: Three sub-chunks (5e-1, 5e-2, 5e-3) given the UI complexity.
Each is independently deliverable and testable.

---

## 10. What We Do NOT Build

| Not in scope | Why |
|-------------|-----|
| Parallel step execution | Replayer singleton + sequential simplicity |
| Plan import/export (YAML) | Future enhancement |
| Plan templates | Future enhancement |
| Plan scheduling (cron) | Future enhancement |
| Variables from external sources | Future enhancement |
| Plan composition (plans calling plans) | Future enhancement |

---

## 11. Cross-References

| Reference | Location |
|-----------|----------|
| M1 Script Executor | `src/core/services/scripts/executor.py` (305 lines) |
| M1 Script Registry | `src/core/services/scripts/registry.py` (564 lines) |
| M1 Script Models | `src/core/services/scripts/models.py` (151 lines) |
| CDP Test Replayer | `src/core/services/cdp_test/replayer.py` (2801 lines) |
| CDP Test Models | `src/core/services/cdp_test/models.py` (657 lines) |
| CDP Test Storage | `src/core/services/cdp_test/storage.py` (181 lines) |
| Chrome Launcher | `src/core/services/chrome/launcher.py` (921 lines) |
| Event Bus | `src/core/services/event_bus.py` (361 lines) |
| Stream Subprocess | `src/core/services/stream_subprocess.py` (193 lines) |
| Chunk 4 Plan | `.agent/plans/scripts-system/chunk-4-replayer-multi-endpoint.md` |
| M7 Master Plan | `.agent/plans/scripts-system/scripts-system-M7-plans.md` |
