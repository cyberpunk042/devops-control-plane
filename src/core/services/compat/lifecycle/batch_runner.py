"""Batch runner — execute multiple steps in sequence.

Uses the SAME StepExecutor and determine_state() as individual execution.
The batch runner adds: iteration, stop conditions, progress events.
No separate logic. No divergent code paths.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Generator

from .state_machine import StepState, StepStateMachine
from .step_executor import StepExecutionResult, StepExecutor

logger = logging.getLogger(__name__)


@dataclass
class BatchEvent:
    """Event emitted during batch execution."""
    type: str                    # "batch_start", "step_start", "step_log", "step_complete",
                                 # "batch_stopped", "batch_complete"
    step_index: int = -1
    step_id: str = ""
    step_label: str = ""
    total_steps: int = 0
    timestamp: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class BatchResult:
    """Final result of batch execution."""
    module_name: str
    steps_requested: int = 0
    steps_executed: int = 0
    steps_passed: int = 0
    steps_failed: int = 0
    steps_needs_attention: int = 0
    steps_blocked: int = 0
    steps_already_done: int = 0

    stopped: bool = False
    stopped_at_step: str | None = None
    stopped_state: StepState | None = None
    stopped_message: str | None = None

    duration_ms: int = 0

    @property
    def all_passed(self) -> bool:
        return (
            self.steps_failed == 0
            and self.steps_needs_attention == 0
            and self.steps_blocked == 0
        )

    @property
    def progress_pct(self) -> float:
        if self.steps_requested == 0:
            return 100.0
        done = self.steps_passed + self.steps_already_done
        return (done / self.steps_requested) * 100


class BatchRunner:
    """Execute multiple steps in sequence.

    Calls StepExecutor.execute_and_transition() for each step.
    SAME function as individual execution. No separate logic.
    Stops on FAILED, NEEDS_ATTENTION, or BLOCKED.
    """

    def __init__(self, executor: StepExecutor):
        self._executor = executor

    def run(
        self,
        module_name: str,
        step_ids: list[str],
        state_machine: StepStateMachine,
        module_dir: Path,
        target_version: str,
        project_root: Path,
        direction: str = "downgrade",
        module_configs: list[dict] | None = None,
        on_event: Callable[[BatchEvent], None] | None = None,
    ) -> BatchResult:
        """Execute steps in order. Stop on failure.

        For each step:
        1. Skip if already PASSED or SKIPPED
        2. Call executor.execute_and_transition()
           → SAME function as individual execution
        3. Emit progress event
        4. If FAILED/NEEDS_ATTENTION/BLOCKED → stop
        5. If PASSED → continue
        """
        t0 = time.time()
        result = BatchResult(
            module_name=module_name,
            steps_requested=len(step_ids),
        )

        def emit(event: BatchEvent) -> None:
            event.timestamp = datetime.now(timezone.utc).isoformat()
            if on_event:
                on_event(event)

        emit(BatchEvent(
            type="batch_start",
            total_steps=len(step_ids),
            data={"module": module_name},
        ))

        for idx, step_id in enumerate(step_ids):
            status = state_machine.get_status(step_id)
            if not status:
                continue

            # Skip already-done steps
            if status.is_terminal:
                result.steps_already_done += 1
                continue

            # Check if blocked
            if status.state == StepState.BLOCKED:
                result.steps_blocked += 1
                result.stopped = True
                result.stopped_at_step = step_id
                result.stopped_state = StepState.BLOCKED
                result.stopped_message = f"Blocked by {status.blocked_by}"
                emit(BatchEvent(
                    type="batch_stopped",
                    step_index=idx,
                    step_id=step_id,
                    step_label=status.label,
                    data={"reason": result.stopped_message},
                ))
                break

            # Check if can execute
            if not status.can_execute:
                continue

            # Emit step start
            emit(BatchEvent(
                type="step_start",
                step_index=idx,
                step_id=step_id,
                step_label=status.label,
                total_steps=len(step_ids),
            ))

            # Execute — SAME function as individual execution
            exec_result, new_state = self._executor.execute_and_transition(
                step_id=step_id,
                state_machine=state_machine,
                module_name=module_name,
                module_dir=module_dir,
                target_version=target_version,
                project_root=project_root,
                direction=direction,
                module_configs=module_configs,
                trigger="batch",
            )

            result.steps_executed += 1

            # Emit step complete
            updated_status = state_machine.get_status(step_id)
            emit(BatchEvent(
                type="step_complete",
                step_index=idx,
                step_id=step_id,
                step_label=status.label,
                data={
                    "state": new_state.value,
                    "summary": exec_result.summary,
                    "duration_ms": exec_result.duration_ms,
                },
            ))

            # Update batch counts
            if new_state == StepState.PASSED:
                result.steps_passed += 1
            elif new_state == StepState.FAILED:
                result.steps_failed += 1
                result.stopped = True
                result.stopped_at_step = step_id
                result.stopped_state = StepState.FAILED
                result.stopped_message = exec_result.error or "Step failed"
                emit(BatchEvent(
                    type="batch_stopped",
                    step_index=idx,
                    step_id=step_id,
                    data={"reason": result.stopped_message, "state": "failed"},
                ))
                break
            elif new_state == StepState.NEEDS_ATTENTION:
                result.steps_needs_attention += 1
                result.stopped = True
                result.stopped_at_step = step_id
                result.stopped_state = StepState.NEEDS_ATTENTION
                result.stopped_message = f"{exec_result.summary} — action needed"
                emit(BatchEvent(
                    type="batch_stopped",
                    step_index=idx,
                    step_id=step_id,
                    data={"reason": result.stopped_message, "state": "needs_attention"},
                ))
                break
            elif new_state == StepState.BLOCKED:
                result.steps_blocked += 1
                result.stopped = True
                result.stopped_at_step = step_id
                result.stopped_state = StepState.BLOCKED
                result.stopped_message = updated_status.blocked_reason if updated_status else "Blocked"
                emit(BatchEvent(
                    type="batch_stopped",
                    step_index=idx,
                    step_id=step_id,
                    data={"reason": result.stopped_message, "state": "blocked"},
                ))
                break

        # Batch complete
        result.duration_ms = int((time.time() - t0) * 1000)
        emit(BatchEvent(
            type="batch_complete",
            data={
                "steps_passed": result.steps_passed,
                "steps_failed": result.steps_failed,
                "steps_needs_attention": result.steps_needs_attention,
                "steps_blocked": result.steps_blocked,
                "steps_already_done": result.steps_already_done,
                "stopped": result.stopped,
                "duration_ms": result.duration_ms,
            },
        ))

        return result

    def run_streaming(
        self,
        module_name: str,
        step_ids: list[str],
        state_machine: StepStateMachine,
        module_dir: Path,
        target_version: str,
        project_root: Path,
        direction: str = "downgrade",
        module_configs: list[dict] | None = None,
    ) -> Generator[BatchEvent, None, None]:
        """Execute batch and yield events for SSE streaming.

        Same as run() but yields events instead of using a callback.
        """
        events: list[BatchEvent] = []

        def collect(event: BatchEvent) -> None:
            events.append(event)

        # We can't truly stream from run() since it's synchronous.
        # For real SSE streaming, the caller should use run() with
        # on_event that yields. This method collects and yields after.
        # A proper streaming implementation would use async or threading.
        result = self.run(
            module_name=module_name,
            step_ids=step_ids,
            state_machine=state_machine,
            module_dir=module_dir,
            target_version=target_version,
            project_root=project_root,
            direction=direction,
            module_configs=module_configs,
            on_event=collect,
        )

        yield from events
