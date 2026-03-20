# 09 — Batch Execution & Orchestration Spec

> **Document**: 9 of 37
> **Milestone**: M5 — Step lifecycle & state machine
> **Status**: Draft

---

## 1. Purpose

Batch execution runs multiple plan steps in sequence. In v1, the batch runner (`wizard_batch` in wizard.py) had DIFFERENT auto-mark-done logic than the individual executor (`execute_step` in executor.py). This caused steps to be marked done in batch that would NOT be marked done individually.

In v2, batch execution uses the EXACT same code path as individual execution. There is ONE `determine_state()` function, ONE state machine, ONE set of transition rules. The batch runner is just a loop that calls the same single-step execution function repeatedly.

---

## 2. Architecture

```
┌─────────────────────────────────────────────┐
│              Batch Runner                    │
│                                             │
│  for step in steps:                         │
│      result = execute_step(step)    ◄───────┼──── SAME function as individual
│      state = determine_state(result) ◄──────┼──── SAME function as individual
│      state_machine.transition(step, state)  │
│      if state is terminal-failure: break    │
│                                             │
└─────────────────────────────────────────────┘
```

### 2.1 No separate logic

```python
class BatchRunner:
    """Execute multiple steps in sequence.

    Uses the same execution and state determination as individual steps.
    The batch runner adds:
    - Sequential iteration
    - Stop conditions
    - Progress reporting (SSE events)
    - Batch-level summary
    """

    def __init__(
        self,
        step_executor: StepExecutor,
        state_machine: StepStateMachine,
    ):
        self._executor = step_executor
        self._state_machine = state_machine

    def run(
        self,
        module_name: str,
        step_ids: list[str],
        on_progress: Callable[[BatchEvent], None] | None = None,
    ) -> BatchResult:
        """Execute steps in order.

        For each step:
        1. Skip if already in terminal state (PASSED, SKIPPED)
        2. Check if BLOCKED — stop if so
        3. Transition to RUNNING
        4. Call step_executor.execute(step_id)
           → This is the SAME executor used for individual steps
        5. determine_state() on the result
           → This is the SAME function used for individual steps
        6. Transition to determined state
        7. Emit progress event
        8. If FAILED, NEEDS_ATTENTION, or BLOCKED → stop
        9. If PASSED → continue to next
        """
```

### 2.2 StepExecutor — the shared execution function

```python
class StepExecutor:
    """Execute a single step. Used by both individual and batch paths."""

    def __init__(
        self,
        detection_engine: DetectionEngine,
        fix_engine: FixEngine,
        verifier: Verifier,
        import_resolver: ImportResolver,
        registry: FeatureRegistry,
    ):
        ...

    def execute(
        self,
        step_id: str,
        module_name: str,
        ctx: UpgradeContext,
    ) -> StepExecutionResult:
        """Execute a step and return the raw result.

        Does NOT determine state or transition state machine.
        The caller (individual path or batch runner) does that.

        Returns:
            StepExecutionResult with:
            - handler_result: dict from the handler
            - findings: list[Finding] from re-analysis
            - verification: VerificationResult if fixes applied
            - import_graph: ImportGraph if transitive analysis done
            - duration_ms: execution time
        """
```

This separation ensures:
- `StepExecutor.execute()` — runs the step, returns raw results
- `determine_state()` — decides what state the step should be in
- `StepStateMachine.transition()` — validates and persists the transition
- Individual path calls all three
- Batch runner calls all three in a loop
- Same functions. Same logic. No divergence.

---

## 3. Batch Stop Conditions

| State after step | Batch action | Reason |
|-----------------|--------------|--------|
| PASSED | Continue to next step | Step succeeded |
| FAILED | Stop batch | Step failed — user must investigate |
| NEEDS_ATTENTION | Stop batch | Findings exist — user must decide |
| BLOCKED | Stop batch | Dependency not met — user must fix blocker |
| SKIPPED | Continue to next step | Already handled |

### 3.1 No "continue on failure" mode

V1 had inconsistent behavior — sometimes batch continued after a failure, sometimes not. V2 is strict: **batch ALWAYS stops on FAILED, NEEDS_ATTENTION, or BLOCKED.** There is no "continue anyway" flag.

Rationale: continuing after failure builds on a broken foundation. Each step assumes previous steps succeeded. Running step 8 after step 5 failed produces unreliable results.

If the user wants to skip a failed step, they explicitly mark it as SKIPPED, then re-run the batch.

### 3.2 Pre-flight check

Before starting the batch, validate that all requested steps are in an executable state:

```python
def preflight_check(
    self,
    step_ids: list[str],
    state_machine: StepStateMachine,
) -> list[str]:
    """Check which steps can be executed.

    Returns list of warnings/errors:
    - "Step X is already PASSED — will be skipped"
    - "Step X is BLOCKED by module Y — batch will stop here"
    - "Step X is FAILED — will retry"
    """
```

---

## 4. Progress Reporting

### 4.1 Event model

```python
@dataclass
class BatchEvent:
    """Event emitted during batch execution for real-time progress."""
    type: str               # Event type (see below)
    step_index: int         # Which step in the batch (0-based)
    step_id: str            # Step identifier
    step_label: str         # Human-readable label
    total_steps: int        # Total steps in batch
    timestamp: str          # ISO timestamp
    data: dict              # Event-specific data

# Event types:
# "batch_start"     — Batch execution begins
# "step_start"      — Step begins executing
# "step_log"        — Log line from step execution
# "step_progress"   — Progress within a step (e.g., "analyzing file 50/200")
# "step_complete"   — Step finished with a state (PASSED, FAILED, etc.)
# "batch_complete"  — Batch finished (all steps done or stopped)
# "batch_stopped"   — Batch stopped early (failure, block, or needs attention)
```

### 4.2 SSE streaming

For the web UI, events are streamed via Server-Sent Events:

```python
def run_streaming(
    self,
    module_name: str,
    step_ids: list[str],
) -> Generator[BatchEvent, None, None]:
    """Execute batch and yield events for SSE streaming.

    Yields events in real-time as steps execute.
    The web route converts these to SSE format:
      data: {"type": "step_complete", "step_index": 2, ...}\n\n
    """
```

### 4.3 Event content per step state

| State | Event data |
|-------|-----------|
| PASSED | `{"summary": "15 files scanned, 0 issues", "duration_ms": 450}` |
| FAILED | `{"error": "Fix verification failed", "details": "datetime.UTC still detected at line 11", "duration_ms": 1200}` |
| NEEDS_ATTENTION | `{"findings_count": 15, "fixable": 14, "manual": 1, "summary": "15 incompatible features found"}` |
| BLOCKED | `{"blocked_by": "core", "reason": "14 transitive incompatibilities in src/core"}` |

---

## 5. Batch Result

```python
@dataclass
class BatchResult:
    """Final result of a batch execution."""
    module_name: str
    steps_requested: int        # How many steps were in the batch
    steps_executed: int         # How many actually ran (excludes skipped/already done)
    steps_passed: int
    steps_failed: int
    steps_needs_attention: int
    steps_blocked: int
    steps_already_done: int     # Skipped because already PASSED/SKIPPED

    stopped: bool               # Did the batch stop early?
    stopped_at_step: str | None # step_id where it stopped
    stopped_state: StepState | None  # Why it stopped
    stopped_message: str | None

    duration_ms: int
    events: list[BatchEvent]    # All events emitted during execution

    @property
    def all_passed(self) -> bool:
        return self.steps_failed == 0 and self.steps_needs_attention == 0 and self.steps_blocked == 0

    @property
    def progress_pct(self) -> float:
        if self.steps_requested == 0:
            return 100.0
        done = self.steps_passed + self.steps_already_done
        return (done / self.steps_requested) * 100
```

---

## 6. Batch Scope Selection

### 6.1 Run all remaining

Run all steps that are not yet in a terminal state:

```python
def run_remaining(self, module_name: str) -> BatchResult:
    """Run all PENDING, FAILED, and NEEDS_ATTENTION steps in order."""
    plan = load_plan(module_name)
    step_ids = [
        s.id for s in plan.steps
        if s.state not in (StepState.PASSED, StepState.SKIPPED)
    ]
    return self.run(module_name, step_ids)
```

### 6.2 Run from step N

Run from a specific step onward:

```python
def run_from(self, module_name: str, from_step_id: str) -> BatchResult:
    """Run from a specific step to the end of the plan."""
    plan = load_plan(module_name)
    found = False
    step_ids = []
    for s in plan.steps:
        if s.id == from_step_id:
            found = True
        if found and s.state not in (StepState.PASSED, StepState.SKIPPED):
            step_ids.append(s.id)
    return self.run(module_name, step_ids)
```

### 6.3 Run specific steps

Run a specific set of steps (selected by user in UI):

```python
def run_selected(self, module_name: str, step_ids: list[str]) -> BatchResult:
    """Run specific steps. Order is determined by plan order, not input order."""
    plan = load_plan(module_name)
    plan_order = {s.id: i for i, s in enumerate(plan.steps)}
    ordered = sorted(step_ids, key=lambda sid: plan_order.get(sid, 999))
    return self.run(module_name, ordered)
```

---

## 7. Retry Behavior

### 7.1 Retrying a failed step

When a step is in FAILED state and the user retries:
1. State transitions from FAILED → RUNNING
2. Step re-executes from scratch
3. Previous failure is recorded in audit trail
4. `run_count` increments

### 7.2 Retrying after NEEDS_ATTENTION

When a step is in NEEDS_ATTENTION and the user has applied fixes:
1. State transitions from NEEDS_ATTENTION → RUNNING
2. Step re-executes (re-scans)
3. If findings are resolved → PASSED
4. If findings remain → NEEDS_ATTENTION again (with updated findings)

### 7.3 Retry limits

No hard retry limit — the user can retry as many times as they want. But the audit trail records every attempt, and the UI can show:
- "This step has been retried 5 times"
- "Last failure: Fix verification failed"
- "Consider skipping this step or fixing manually"

---

## 8. Concurrency

### 8.1 Single module — sequential

Within a single module, steps execute sequentially. No parallel step execution within one module. Reason: steps may depend on previous steps' side effects (file modifications, venv creation).

### 8.2 Multiple modules — parallel (future)

Different modules can execute their plans in parallel if they don't have dependencies:

```
Tier 0: [core]       ← execute alone
Tier 1: [adapters]   ← execute after core
Tier 2: [cli, web]   ← execute in PARALLEL after adapters
```

This is a future optimization. V2 initial implementation runs one module at a time.

### 8.3 File locking

Multiple execution paths (web UI, CLI, multiple browser tabs) must not execute steps concurrently on the same module. The state machine enforces this:
- Only one step can be RUNNING at a time per module
- Attempting to transition a second step to RUNNING fails with "another step is already running"
- project.yml writes use file locking

---

## 9. Integration Points

### 9.1 With Step Lifecycle (Document 06)
- Batch runner uses StepStateMachine for transitions
- Uses determine_state() for state determination
- Same code path as individual execution

### 9.2 With StepExecutor
- Batch runner calls StepExecutor.execute() for each step
- StepExecutor is shared with individual execution path

### 9.3 With Web UI (Document 31)
- SSE streaming for real-time progress
- BatchEvent model maps to SSE data format
- UI renders progress based on events

### 9.4 With CLI (Document 32)
- CLI can run batch with console output instead of SSE
- Same BatchRunner, different progress callback (print to terminal)
