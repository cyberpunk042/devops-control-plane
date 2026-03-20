# 06 — Step Lifecycle State Machine Spec

> **Document**: 6 of 37
> **Milestone**: M5 — Step lifecycle & state machine
> **Status**: Draft

---

## 1. The Problem This Solves

In v1, a step had two states: done or not done. A boolean. This caused:

- **Failed steps marked done**: `guide_incompatible_syntax` returned `ok: True` with findings → auto-marked done. The findings were never addressed.
- **Read-only steps marked done**: `update_ci_matrix` showed ⚠️ warnings → auto-marked done. The CI was never updated.
- **Inconsistent logic**: `executor.py` used `has_incompatible` check. `wizard.py` used version parsing. Different code paths, different results for the same step.
- **No BLOCKED state**: A step that depends on another module being fixed first had no way to express that. It just ran and failed.
- **No NEEDS_ATTENTION state**: A step that found issues requiring user decision had no way to pause. It either passed or failed — no middle ground.
- **Mark as done on failure**: The UI showed "✅ Mark as done" button even after a step failed with 39 test failures. A user could mark a failed step as done.

The new system uses a proper state machine with explicit states, validated transitions, and rules about what each state means for project.yml persistence.

---

## 2. States

```
┌─────────┐
│ PENDING  │ ── Step exists in plan, not yet started
└────┬─────┘
     │ user triggers execution
     ▼
┌─────────┐
│ RUNNING  │ ── Step is currently executing
└────┬─────┘
     │ execution completes
     ▼
     ├──────────────────────────────────────────┐
     │                    │                     │
     ▼                    ▼                     ▼
┌─────────┐      ┌───────────────┐      ┌──────────┐
│ PASSED  │      │NEEDS_ATTENTION│      │  FAILED  │
│         │      │               │      │          │
│done:true│      │  done:false   │      │done:false│
└─────────┘      └───────┬───────┘      └────┬─────┘
                         │                    │
                    user acts                 │ user retries
                         │                    │
                    ┌────▼────┐               │
                    │ RUNNING │ ◄─────────────┘
                    └─────────┘

Also:
┌──────────┐
│ BLOCKED  │ ── Depends on another module/step being completed first
│done:false│    Transitions to PENDING when blocker is resolved
└──────────┘

┌──────────┐
│ SKIPPED  │ ── User explicitly chose to skip this step
│done:skip │    Recorded as skipped, not done
└──────────┘
```

### 2.1 State definitions

| State | Meaning | `done` in project.yml | Can user proceed to next step? |
|-------|---------|----------------------|-------------------------------|
| `PENDING` | Not yet started | absent or `false` | No — must execute or skip |
| `RUNNING` | Currently executing | `false` | No — wait for completion |
| `PASSED` | Execution succeeded, verified | `true` | Yes |
| `FAILED` | Execution failed | `false` | No — must retry or skip |
| `NEEDS_ATTENTION` | Execution found issues requiring user decision | `false` | No — must act or skip |
| `BLOCKED` | Cannot execute — dependency not met | `false` | No — fix blocker first |
| `SKIPPED` | User chose to skip | `"skipped"` | Yes |

### 2.2 project.yml representation

```yaml
checklist:
  - label: Scan for incompatible features
    id: scan_incompatible_features:abc123
    state: passed          # NEW — replaces boolean "done"
    done: true             # KEPT for backward compat — derived from state
    completed_at: "2026-03-19T12:00:00Z"
    result_hash: "a1b2c3"  # Hash of the result for audit

  - label: Review and fix incompatible syntax
    id: guide_incompatible_syntax:def456
    state: needs_attention
    done: false
    findings_count: 15
    last_run_at: "2026-03-19T12:01:00Z"

  - label: Run isolated tests
    id: run_isolated_tests:ghi789
    state: blocked
    done: false
    blocked_by: "core"     # Module that needs fixing first
    blocked_reason: "14 transitive incompatibilities in src/core"
```

### 2.3 Backward compatibility

The `done` field is kept for backward compatibility:
- `state: passed` → `done: true`
- `state: skipped` → `done: "skipped"` (truthy for checklist rendering)
- All other states → `done: false`

Code that only reads `done: true/false` continues to work. New code reads `state` for richer information.

---

## 3. Transitions

### 3.1 Valid transitions

```python
_VALID_TRANSITIONS = {
    StepState.PENDING: {StepState.RUNNING, StepState.SKIPPED, StepState.BLOCKED},
    StepState.RUNNING: {StepState.PASSED, StepState.FAILED, StepState.NEEDS_ATTENTION, StepState.BLOCKED},
    StepState.PASSED: set(),  # Terminal — no transitions out of PASSED
    StepState.FAILED: {StepState.RUNNING, StepState.SKIPPED},  # Retry or skip
    StepState.NEEDS_ATTENTION: {StepState.RUNNING, StepState.SKIPPED, StepState.PASSED},  # Act, skip, or manual pass
    StepState.BLOCKED: {StepState.PENDING, StepState.SKIPPED},  # Unblock or skip
    StepState.SKIPPED: set(),  # Terminal — no transitions out of SKIPPED (user decided)
}
```

### 3.2 Transition rules

| From | To | Trigger | Validation |
|------|----|---------|------------|
| PENDING → RUNNING | User clicks execute / batch runner starts step | Step must exist in plan |
| RUNNING → PASSED | Handler returns `ok: True`, no findings, verification passes | Result must be verified |
| RUNNING → FAILED | Handler returns `ok: False` or verification fails | Error details recorded |
| RUNNING → NEEDS_ATTENTION | Handler returns `ok: True` WITH findings | Findings must be non-empty |
| RUNNING → BLOCKED | Handler detects unresolved dependency | Blocker must be identified |
| FAILED → RUNNING | User clicks retry | Previous failure recorded |
| NEEDS_ATTENTION → RUNNING | User clicks "fix" or "re-run" | Previous findings available |
| NEEDS_ATTENTION → PASSED | User manually confirms (for read-only/guide steps) | User explicitly confirms |
| NEEDS_ATTENTION → SKIPPED | User clicks skip | Recorded as user decision |
| BLOCKED → PENDING | Blocker is resolved (other module completed) | Blocker module's plan must be done |
| PENDING → SKIPPED | User clicks skip | Recorded as user decision |
| PENDING → BLOCKED | Analysis determines dependency exists | Blocker must be identified |

### 3.3 Invalid transitions (enforced)

These transitions are REJECTED by the state machine:

| Invalid transition | Why |
|---|---|
| RUNNING → PASSED (without verification) | Cannot mark done without proving the step succeeded |
| FAILED → PASSED | Cannot go from failed to passed without re-running |
| BLOCKED → PASSED | Cannot pass a step that hasn't been executed |
| PASSED → anything | PASSED is terminal — once done, done |
| SKIPPED → anything | SKIPPED is terminal — user decided |
| Any → RUNNING (while another step is RUNNING) | Only one step runs at a time per module |

---

## 4. State Machine Implementation

```python
class StepState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    NEEDS_ATTENTION = "needs_attention"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass
class StepStatus:
    """Full status of a step at a point in time."""
    state: StepState
    step_id: str
    module_name: str

    # Timing
    last_run_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None

    # Results (populated after execution)
    findings_count: int = 0
    findings_fixable: int = 0
    findings_manual: int = 0
    error_message: str | None = None

    # Blocking info
    blocked_by: str | None = None
    blocked_reason: str | None = None

    # Audit
    result_hash: str | None = None
    run_count: int = 0            # How many times this step has been executed

    @property
    def is_done(self) -> bool:
        return self.state in (StepState.PASSED, StepState.SKIPPED)

    @property
    def is_terminal(self) -> bool:
        return self.state in (StepState.PASSED, StepState.SKIPPED)

    @property
    def can_execute(self) -> bool:
        return self.state in (StepState.PENDING, StepState.FAILED, StepState.NEEDS_ATTENTION)

    @property
    def needs_user_action(self) -> bool:
        return self.state in (StepState.NEEDS_ATTENTION, StepState.FAILED, StepState.BLOCKED)


class StepStateMachine:
    """Manages step state transitions with validation."""

    def __init__(self, module_name: str):
        self._module_name = module_name
        self._steps: dict[str, StepStatus] = {}

    def get_state(self, step_id: str) -> StepState:
        """Get current state of a step."""

    def get_status(self, step_id: str) -> StepStatus:
        """Get full status of a step."""

    def transition(
        self,
        step_id: str,
        new_state: StepState,
        **kwargs,
    ) -> StepStatus:
        """Transition a step to a new state.

        Validates the transition is allowed.
        Updates all status fields.
        Persists to project.yml.

        Raises:
            InvalidTransition: If the transition is not allowed
        """

    def can_transition(self, step_id: str, new_state: StepState) -> bool:
        """Check if a transition is valid without performing it."""

    def next_actionable_step(self) -> str | None:
        """Return the first step that can be executed.

        Skips PASSED, SKIPPED, and BLOCKED steps.
        Returns the first PENDING, FAILED, or NEEDS_ATTENTION step.
        """

    def all_done(self) -> bool:
        """Are all steps in a terminal state (PASSED or SKIPPED)?"""

    def summary(self) -> dict:
        """Return summary: counts by state, overall progress percentage."""
```

---

## 5. Determining State After Execution

When a step handler executes and returns a result, the state machine determines the next state:

```python
def determine_state(
    result: dict,
    findings: list[Finding],
    verification: VerificationResult | None,
    import_graph: ImportGraph | None,
) -> tuple[StepState, dict]:
    """Determine the step's new state from execution results.

    Returns:
        (new_state, metadata_dict)
    """

    # 1. Execution failed
    if not result.get("ok"):
        return StepState.FAILED, {
            "error_message": result.get("error", "Step failed"),
        }

    # 2. Blocked by transitive dependency
    if import_graph and findings:
        transitive = [f for f in findings if f.is_transitive]
        if transitive and not any(not f.is_transitive for f in findings):
            # ALL findings are transitive — nothing to fix in this module
            blocking_modules = set(
                import_graph.determine_module(f.file)
                for f in transitive
            )
            return StepState.BLOCKED, {
                "blocked_by": ", ".join(sorted(blocking_modules)),
                "blocked_reason": f"{len(transitive)} transitive incompatibilities",
            }

    # 3. Has findings that need attention
    if findings:
        fixable = [f for f in findings if f.fix_available and not f.is_transitive]
        manual = [f for f in findings if not f.fix_available and not f.is_transitive]
        transitive = [f for f in findings if f.is_transitive]

        return StepState.NEEDS_ATTENTION, {
            "findings_count": len(findings),
            "findings_fixable": len(fixable),
            "findings_manual": len(manual),
            "findings_transitive": len(transitive),
        }

    # 4. Fix was applied — check verification
    if verification:
        if not verification.all_passed:
            return StepState.FAILED, {
                "error_message": "Fix verification failed: " + "; ".join(verification.errors),
            }

    # 5. All clear — no findings, or all findings fixed and verified
    return StepState.PASSED, {
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
```

### 5.1 Decision matrix

| `ok` | Findings? | Transitive only? | Verification | → State |
|------|-----------|-------------------|--------------|---------|
| False | — | — | — | FAILED |
| True | None | — | — | PASSED |
| True | Yes | All transitive | — | BLOCKED |
| True | Yes | Some direct | — | NEEDS_ATTENTION |
| True | None | — | Failed | FAILED |
| True | None | — | Passed | PASSED |

### 5.2 ONE code path

This function is called from BOTH individual execution and batch execution. There is no separate logic in the batch runner. The batch runner calls the same `determine_state()` function for each step.

```python
# Individual execution
result = handler(ctx, "execute")
findings = detection_engine.analyze(...)
state, metadata = determine_state(result, findings, verification, graph)
state_machine.transition(step_id, state, **metadata)

# Batch execution — SAME CODE
for step_id in step_ids:
    result = handler(ctx, "execute")
    findings = detection_engine.analyze(...)
    state, metadata = determine_state(result, findings, verification, graph)
    state_machine.transition(step_id, state, **metadata)
    if state in (StepState.FAILED, StepState.BLOCKED):
        break  # Stop batch on failure or block
```

No duplication. No divergent logic. One function. One truth.

---

## 6. Step Types

Different types of steps have different execution patterns and state determination:

### 6.1 Analysis steps

Steps that scan code for issues. Do not modify files.

| Step | Handler | Findings → State |
|------|---------|------------------|
| Scan for incompatible features | `scan_incompatible_features` | Findings → NEEDS_ATTENTION. No findings → PASSED |
| Review incompatible syntax | `guide_incompatible_syntax` | Findings → NEEDS_ATTENTION. No findings → PASSED |
| Check dependency compatibility | `check_dep_compat` | Incompatible deps → NEEDS_ATTENTION. All compatible → PASSED |
| Update CI matrix | `update_ci_matrix` | CI needs changes → NEEDS_ATTENTION. Already correct → PASSED |

Key: analysis steps NEVER auto-mark PASSED if they have findings. The user must acknowledge or fix the findings.

### 6.2 Transform steps

Steps that modify code. Always followed by verification.

| Step | Handler | State logic |
|------|---------|-------------|
| Add `__future__` annotations | `add_future_annotations` | Files modified + verification passes → PASSED |
| Fix incompatible code | `apply_fixes` | All fixes verified → PASSED. Any fix failed → FAILED |
| Update config files | `edit_pyproject_requires_python` | Config updated + correct → PASSED |
| Generate module toml | `generate_module_toml` | File created → PASSED |

Key: transform steps are PASSED only when the transform succeeds AND verification confirms it.

### 6.3 Test steps

Steps that run tests to validate compatibility.

| Step | Handler | State logic |
|------|---------|-------------|
| Set up test environment | `setup_test_env` | Venv created + deps installed → PASSED |
| Run isolated tests | `run_isolated_tests` | Tests pass → PASSED. Tests fail → FAILED with output |
| Run full test suite | `run_test_suite` | Tests pass → PASSED. Tests fail → FAILED with output |

Key: test steps are binary — either all tests pass (PASSED) or some fail (FAILED). No NEEDS_ATTENTION for test steps.

### 6.4 Scaffold steps

Steps that create new files (tests, configs).

| Step | Handler | State logic |
|------|---------|-------------|
| Scaffold module tests | `scaffold_module_tests` | Files created → PASSED |
| Generate compatibility tests | `generate_smart_tests` | Files created → PASSED |
| Scaffold parent tests | `scaffold_parent_tests` | Files created → PASSED |

Key: scaffold steps are simple — create files, PASSED if successful.

### 6.5 Manual steps

Steps that require human action.

| Step | Handler | State logic |
|------|---------|-------------|
| Run test suite (manual) | `manual` | User marks done → PASSED |
| Add version decision note | `manual` | User marks done → PASSED |

Key: manual steps start as PENDING and can only be moved to PASSED or SKIPPED by the user. No automation.

---

## 7. Persistence

### 7.1 Writing to project.yml

```python
def persist_step_state(
    module_name: str,
    step_id: str,
    status: StepStatus,
    project_root: Path,
) -> None:
    """Write step state to project.yml.

    Updates the step's fields:
      state: <state>
      done: <derived from state>
      completed_at: <timestamp if PASSED>
      last_run_at: <timestamp>
      findings_count: <count if NEEDS_ATTENTION>
      error_message: <message if FAILED>
      blocked_by: <module if BLOCKED>
    """
```

### 7.2 Reading from project.yml

```python
def load_step_states(
    module_name: str,
    project_root: Path,
) -> dict[str, StepStatus]:
    """Load all step states for a module from project.yml.

    Handles backward compatibility:
      - Old format: {done: true} → StepState.PASSED
      - Old format: {done: false} or missing → StepState.PENDING
      - New format: {state: "needs_attention", ...} → full status
    """
```

### 7.3 Atomicity

State changes are written atomically:
1. Read project.yml
2. Update the step's fields in memory
3. Write the entire file back
4. Use file locking to prevent concurrent writes (multiple browser tabs, CLI + web)

---

## 8. Batch Execution Integration

### 8.1 Batch runner behavior

The batch runner executes multiple steps sequentially. It uses the state machine for each step:

```python
class BatchRunner:
    """Execute multiple steps in sequence."""

    def run(
        self,
        module_name: str,
        step_ids: list[str],
        state_machine: StepStateMachine,
        **kwargs,
    ) -> BatchResult:
        """Run steps in order. Stop on FAILED or BLOCKED.

        For each step:
        1. Check state — skip if already PASSED or SKIPPED
        2. Transition to RUNNING
        3. Execute handler
        4. Determine new state via determine_state()
        5. Transition to new state
        6. If FAILED or BLOCKED → stop batch
        7. If NEEDS_ATTENTION → stop batch (user must act)
        8. If PASSED → continue to next step
        """
```

### 8.2 Batch stop conditions

| State after execution | Batch behavior |
|----------------------|----------------|
| PASSED | Continue to next step |
| FAILED | Stop batch. Report failure. |
| NEEDS_ATTENTION | Stop batch. Show findings. User must act. |
| BLOCKED | Stop batch. Show blocker. User must fix dependency. |

### 8.3 Batch result

```python
@dataclass
class BatchResult:
    steps_attempted: int
    steps_passed: int
    steps_failed: int
    steps_need_attention: int
    steps_blocked: int
    steps_skipped: int       # Already done before batch started
    stopped_at: str | None   # step_id where batch stopped
    stopped_reason: str | None
    duration_ms: int
```

---

## 9. UI State Rendering

Each state maps to a visual representation:

| State | Icon | Color | Label | Actions available |
|-------|------|-------|-------|-------------------|
| PENDING | ○ | grey | "Pending" | Execute, Skip |
| RUNNING | ◉ (spinner) | blue | "Running..." | — |
| PASSED | ✅ | green | "Done" | — |
| FAILED | ❌ | red | "Failed" | Retry, Skip, View error |
| NEEDS_ATTENTION | ⚠️ | yellow | "Needs attention" | Fix, Skip, View findings |
| BLOCKED | 🔒 | orange | "Blocked" | View blocker, Skip |
| SKIPPED | ⏭️ | grey | "Skipped" | — |

### 9.1 What is NOT shown

- No "✅ Mark as done" button on FAILED steps. NEVER.
- No "✅ Mark as done" button on NEEDS_ATTENTION steps unless it's a read-only/guide step where the user has reviewed the findings.
- No way to transition from FAILED to PASSED without re-running.

### 9.2 Manual confirmation

For NEEDS_ATTENTION steps that are read-only (scan, guide, CI update), the user can confirm they've reviewed the findings:

- Button: "I've reviewed this — mark as done"
- This transitions NEEDS_ATTENTION → PASSED
- Requires explicit user action — never automatic
- Records that the user confirmed, not that the system verified

---

## 10. Audit Trail

Every state transition is recorded:

```python
@dataclass
class StateTransition:
    step_id: str
    module_name: str
    from_state: StepState
    to_state: StepState
    timestamp: str
    trigger: str           # "execution", "user_action", "batch", "blocker_resolved"
    details: dict          # State-specific details (error message, findings count, etc.)
```

The audit trail answers:
- When was this step last run?
- How many times has it been retried?
- Who marked it as done — the system (verified) or the user (manual)?
- What was the error message on failure?
- What findings existed when the user chose to skip?

---

## 11. Integration Points

### 11.1 With Detection Engine (Document 03)
- Detection results feed into `determine_state()`
- Findings count and types determine NEEDS_ATTENTION vs PASSED

### 11.2 With Fix Engine (Document 05)
- Fix results (success/failure/rollback) feed into `determine_state()`
- Verification results determine PASSED vs FAILED

### 11.3 With Import Resolver (Document 04)
- Import graph identifies transitive dependencies → BLOCKED state
- Module dependency order determines which modules to fix first

### 11.4 With Batch Execution (Document 09)
- Batch runner uses the state machine for each step
- Same `determine_state()` function — no separate logic

### 11.5 With UI (Documents 30-31)
- UI reads state for rendering (icons, colors, actions)
- UI triggers transitions (execute, skip, retry, confirm)
- UI never directly writes to project.yml — always through state machine
