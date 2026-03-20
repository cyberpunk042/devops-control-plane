"""Step lifecycle state machine.

Replaces v1's boolean done/not-done with proper states.
Only PASSED writes done:true. FAILED never marks done. NEVER.

States:
  PENDING → RUNNING → PASSED | FAILED | NEEDS_ATTENTION | BLOCKED
  FAILED → RUNNING (retry) | SKIPPED
  NEEDS_ATTENTION → RUNNING (re-run) | SKIPPED | PASSED (user confirmed)
  BLOCKED → PENDING (blocker resolved) | SKIPPED
  PASSED → (terminal)
  SKIPPED → (terminal)

ONE code path for both individual and batch execution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class StepState(Enum):
    """All possible step states."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    NEEDS_ATTENTION = "needs_attention"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


# Valid state transitions
_VALID_TRANSITIONS: dict[StepState, set[StepState]] = {
    StepState.PENDING: {StepState.RUNNING, StepState.SKIPPED, StepState.BLOCKED},
    StepState.RUNNING: {StepState.PASSED, StepState.FAILED, StepState.NEEDS_ATTENTION, StepState.BLOCKED},
    StepState.PASSED: set(),  # Terminal
    StepState.FAILED: {StepState.RUNNING, StepState.SKIPPED},
    StepState.NEEDS_ATTENTION: {StepState.RUNNING, StepState.SKIPPED, StepState.PASSED},
    StepState.BLOCKED: {StepState.PENDING, StepState.SKIPPED},
    StepState.SKIPPED: set(),  # Terminal
}


class InvalidTransition(Exception):
    """Raised when an invalid state transition is attempted."""
    def __init__(self, step_id: str, from_state: StepState, to_state: StepState):
        self.step_id = step_id
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid transition for step '{step_id}': "
            f"{from_state.value} → {to_state.value}"
        )


@dataclass
class StepStatus:
    """Full status of a step at a point in time."""
    state: StepState
    step_id: str
    label: str = ""
    step_type: str = ""         # "analysis", "transform", "test", "manual", "scaffold"

    # Timing
    last_run_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None

    # Results
    findings_count: int = 0
    findings_fixable: int = 0
    findings_manual: int = 0
    findings_transitive: int = 0
    error_message: str | None = None
    summary: str | None = None

    # Blocking
    blocked_by: str | None = None
    blocked_reason: str | None = None

    # Audit
    result_hash: str | None = None
    run_count: int = 0

    @property
    def is_done(self) -> bool:
        """Is this step in a terminal-done state?"""
        return self.state in (StepState.PASSED, StepState.SKIPPED)

    @property
    def is_terminal(self) -> bool:
        """Is this step in any terminal state?"""
        return self.state in (StepState.PASSED, StepState.SKIPPED)

    @property
    def can_execute(self) -> bool:
        """Can this step be executed (or re-executed)?"""
        return self.state in (StepState.PENDING, StepState.FAILED, StepState.NEEDS_ATTENTION)

    @property
    def needs_user_action(self) -> bool:
        """Does this step need user input before proceeding?"""
        return self.state in (StepState.NEEDS_ATTENTION, StepState.FAILED, StepState.BLOCKED)

    def to_yml_dict(self) -> dict:
        """Convert to dict for project.yml serialization."""
        d: dict = {
            "state": self.state.value,
            "done": self.state == StepState.PASSED,
        }
        if self.state == StepState.SKIPPED:
            d["done"] = "skipped"
        if self.completed_at:
            d["completed_at"] = self.completed_at
        if self.last_run_at:
            d["last_run_at"] = self.last_run_at
        if self.findings_count:
            d["findings_count"] = self.findings_count
        if self.error_message:
            d["error_message"] = self.error_message
        if self.blocked_by:
            d["blocked_by"] = self.blocked_by
        if self.blocked_reason:
            d["blocked_reason"] = self.blocked_reason
        if self.run_count > 1:
            d["run_count"] = self.run_count
        return d


@dataclass
class StateTransition:
    """Record of a state transition (for audit trail)."""
    step_id: str
    from_state: StepState
    to_state: StepState
    timestamp: str
    trigger: str                # "execution", "user_action", "batch", "blocker_resolved"
    details: dict = field(default_factory=dict)


class StepStateMachine:
    """Manages step state transitions with validation.

    ONE instance per module's plan. Used by both individual
    execution and batch execution — same code path.
    """

    def __init__(self, module_name: str):
        self._module_name = module_name
        self._steps: dict[str, StepStatus] = {}
        self._step_order: list[str] = []
        self._history: list[StateTransition] = []

    def load_from_plan(self, checklist: list[dict]) -> None:
        """Initialize step states from a project.yml checklist.

        Handles both v1 format (done: true/false) and
        v2 format (state: "passed"/"pending"/...).
        """
        self._steps.clear()
        self._step_order.clear()

        for step in checklist:
            step_id = step.get("id", "")
            if not step_id:
                continue

            # v2 format
            state_str = step.get("state")
            if state_str:
                try:
                    state = StepState(state_str)
                except ValueError:
                    state = StepState.PENDING
            else:
                # v1 format — derive from done field
                done = step.get("done")
                if done is True:
                    state = StepState.PASSED
                elif done == "skipped":
                    state = StepState.SKIPPED
                else:
                    state = StepState.PENDING

            status = StepStatus(
                state=state,
                step_id=step_id,
                label=step.get("label", ""),
                step_type=step.get("step_type", ""),
                last_run_at=step.get("last_run_at"),
                completed_at=step.get("completed_at"),
                findings_count=step.get("findings_count", 0),
                error_message=step.get("error_message"),
                blocked_by=step.get("blocked_by"),
                blocked_reason=step.get("blocked_reason"),
                run_count=step.get("run_count", 0),
            )

            self._steps[step_id] = status
            self._step_order.append(step_id)

    def get_state(self, step_id: str) -> StepState:
        """Get current state of a step."""
        status = self._steps.get(step_id)
        return status.state if status else StepState.PENDING

    def get_status(self, step_id: str) -> StepStatus | None:
        """Get full status of a step."""
        return self._steps.get(step_id)

    def transition(
        self,
        step_id: str,
        new_state: StepState,
        trigger: str = "execution",
        **kwargs: object,
    ) -> StepStatus:
        """Transition a step to a new state.

        Validates the transition is allowed.
        Updates status fields from kwargs.
        Records transition in history.

        Raises InvalidTransition if not allowed.
        """
        status = self._steps.get(step_id)
        if not status:
            raise ValueError(f"Unknown step: {step_id}")

        old_state = status.state

        # Validate transition
        if new_state not in _VALID_TRANSITIONS.get(old_state, set()):
            raise InvalidTransition(step_id, old_state, new_state)

        # Check: only one RUNNING at a time
        if new_state == StepState.RUNNING:
            running = [
                sid for sid, s in self._steps.items()
                if s.state == StepState.RUNNING and sid != step_id
            ]
            if running:
                raise InvalidTransition(step_id, old_state, new_state)

        # Apply transition
        status.state = new_state
        now = datetime.now(timezone.utc).isoformat()

        if new_state == StepState.RUNNING:
            status.last_run_at = now
            status.run_count += 1
            status.error_message = None  # Clear previous error

        if new_state == StepState.PASSED:
            status.completed_at = now

        if new_state == StepState.FAILED:
            status.error_message = str(kwargs.get("error_message", ""))

        if new_state == StepState.NEEDS_ATTENTION:
            status.findings_count = int(kwargs.get("findings_count", 0))
            status.findings_fixable = int(kwargs.get("findings_fixable", 0))
            status.findings_manual = int(kwargs.get("findings_manual", 0))
            status.findings_transitive = int(kwargs.get("findings_transitive", 0))

        if new_state == StepState.BLOCKED:
            status.blocked_by = str(kwargs.get("blocked_by", ""))
            status.blocked_reason = str(kwargs.get("blocked_reason", ""))

        if "summary" in kwargs:
            status.summary = str(kwargs["summary"])

        if "duration_ms" in kwargs:
            status.duration_ms = int(kwargs["duration_ms"])

        # Record transition
        self._history.append(StateTransition(
            step_id=step_id,
            from_state=old_state,
            to_state=new_state,
            timestamp=now,
            trigger=trigger,
            details=dict(kwargs),
        ))

        logger.info(
            "Step %s: %s → %s (trigger=%s)",
            step_id, old_state.value, new_state.value, trigger,
        )

        return status

    def can_transition(self, step_id: str, new_state: StepState) -> bool:
        """Check if a transition is valid without performing it."""
        status = self._steps.get(step_id)
        if not status:
            return False
        return new_state in _VALID_TRANSITIONS.get(status.state, set())

    def next_actionable_step(self) -> str | None:
        """Return the first step that can be executed.

        Follows plan order. Skips PASSED, SKIPPED.
        Returns the first PENDING, FAILED, or NEEDS_ATTENTION step.
        Stops at BLOCKED (can't skip over it).
        """
        for step_id in self._step_order:
            status = self._steps.get(step_id)
            if not status:
                continue
            if status.state in (StepState.PASSED, StepState.SKIPPED):
                continue
            if status.state == StepState.BLOCKED:
                return None  # Blocked — can't proceed
            if status.can_execute:
                return step_id
        return None  # All done

    def all_done(self) -> bool:
        """Are all steps in a terminal state?"""
        return all(s.is_terminal for s in self._steps.values())

    def progress(self) -> dict:
        """Progress summary."""
        total = len(self._steps)
        by_state: dict[str, int] = {}
        for s in self._steps.values():
            by_state[s.state.value] = by_state.get(s.state.value, 0) + 1

        done = by_state.get("passed", 0) + by_state.get("skipped", 0)
        pct = (done / total * 100) if total > 0 else 0

        return {
            "total": total,
            "by_state": by_state,
            "done": done,
            "percent": round(pct, 1),
        }

    def all_statuses(self) -> list[StepStatus]:
        """All step statuses in plan order."""
        return [self._steps[sid] for sid in self._step_order if sid in self._steps]

    def history(self, step_id: str | None = None) -> list[StateTransition]:
        """Get transition history, optionally filtered by step."""
        if step_id:
            return [t for t in self._history if t.step_id == step_id]
        return list(self._history)

    def to_checklist(self) -> list[dict]:
        """Export step states back to project.yml checklist format."""
        result = []
        for step_id in self._step_order:
            status = self._steps.get(step_id)
            if not status:
                continue
            d = {
                "label": status.label,
                "id": step_id,
            }
            d.update(status.to_yml_dict())
            result.append(d)
        return result


# ── State determination ──────────────────────────────────────────
# ONE function used by BOTH individual and batch execution.


def determine_state(
    result: dict,
    findings: list | None = None,
    verification_passed: bool | None = None,
    has_transitive_only: bool = False,
    blocking_modules: list[str] | None = None,
) -> tuple[StepState, dict]:
    """Determine a step's new state from execution results.

    This is the SINGLE function called by both individual execution
    and batch execution. No separate logic. No divergence.

    Returns:
        (new_state, metadata_kwargs for transition)
    """
    findings = findings or []
    blocking_modules = blocking_modules or []

    # 1. Execution failed
    if not result.get("ok", False):
        return StepState.FAILED, {
            "error_message": result.get("error", "Step failed"),
            "summary": result.get("summary", ""),
        }

    # 2. Blocked by transitive dependencies
    if blocking_modules:
        transitive = [f for f in findings if getattr(f, "is_transitive", False)]
        direct = [f for f in findings if not getattr(f, "is_transitive", False)]
        if transitive and not direct:
            return StepState.BLOCKED, {
                "blocked_by": ", ".join(blocking_modules),
                "blocked_reason": f"{len(transitive)} transitive incompatibilities",
                "findings_transitive": len(transitive),
            }

    # 3. Has findings that need attention
    if findings:
        fixable = [f for f in findings if getattr(f, "fix_available", False) and not getattr(f, "is_transitive", False)]
        manual = [f for f in findings if not getattr(f, "fix_available", True) and not getattr(f, "is_transitive", False)]
        transitive = [f for f in findings if getattr(f, "is_transitive", False)]

        return StepState.NEEDS_ATTENTION, {
            "findings_count": len(findings),
            "findings_fixable": len(fixable),
            "findings_manual": len(manual),
            "findings_transitive": len(transitive),
            "summary": f"{len(findings)} finding(s): {len(fixable)} auto-fixable, {len(manual)} manual",
        }

    # 4. Verification was run and failed
    if verification_passed is False:
        return StepState.FAILED, {
            "error_message": "Fix verification failed",
        }

    # 5. All clear
    return StepState.PASSED, {
        "summary": result.get("summary", "Completed"),
    }
