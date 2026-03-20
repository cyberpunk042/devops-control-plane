"""State machine tests — verify step lifecycle transitions.

Run: python -m pytest src/core/services/compat/edge_cases/test_state_machine.py -v
"""

from __future__ import annotations

import pytest

from ..lifecycle.state_machine import (
    InvalidTransition,
    StepState,
    StepStateMachine,
    determine_state,
)


class TestStepStates:
    """Test step state transitions."""

    def test_pending_to_running(self):
        sm = StepStateMachine("test")
        sm.load_from_plan([{"id": "s1", "label": "Step 1"}])
        sm.transition("s1", StepState.RUNNING)
        assert sm.get_state("s1") == StepState.RUNNING

    def test_running_to_passed(self):
        sm = StepStateMachine("test")
        sm.load_from_plan([{"id": "s1", "label": "Step 1"}])
        sm.transition("s1", StepState.RUNNING)
        sm.transition("s1", StepState.PASSED, summary="Done")
        assert sm.get_state("s1") == StepState.PASSED
        assert sm.get_status("s1").is_done

    def test_running_to_failed(self):
        sm = StepStateMachine("test")
        sm.load_from_plan([{"id": "s1", "label": "Step 1"}])
        sm.transition("s1", StepState.RUNNING)
        sm.transition("s1", StepState.FAILED, error_message="Broke")
        assert sm.get_state("s1") == StepState.FAILED
        assert sm.get_status("s1").error_message == "Broke"

    def test_running_to_needs_attention(self):
        sm = StepStateMachine("test")
        sm.load_from_plan([{"id": "s1", "label": "Step 1"}])
        sm.transition("s1", StepState.RUNNING)
        sm.transition("s1", StepState.NEEDS_ATTENTION, findings_count=5)
        assert sm.get_state("s1") == StepState.NEEDS_ATTENTION
        assert sm.get_status("s1").findings_count == 5

    def test_running_to_blocked(self):
        sm = StepStateMachine("test")
        sm.load_from_plan([{"id": "s1", "label": "Step 1"}])
        sm.transition("s1", StepState.RUNNING)
        sm.transition("s1", StepState.BLOCKED, blocked_by="core")
        assert sm.get_state("s1") == StepState.BLOCKED
        assert sm.get_status("s1").blocked_by == "core"


class TestInvalidTransitions:
    """Test that invalid transitions are rejected."""

    def test_passed_to_running_rejected(self):
        sm = StepStateMachine("test")
        sm.load_from_plan([{"id": "s1", "label": "Step 1"}])
        sm.transition("s1", StepState.RUNNING)
        sm.transition("s1", StepState.PASSED)
        with pytest.raises(InvalidTransition):
            sm.transition("s1", StepState.RUNNING)

    def test_failed_to_passed_rejected(self):
        sm = StepStateMachine("test")
        sm.load_from_plan([{"id": "s1", "label": "Step 1"}])
        sm.transition("s1", StepState.RUNNING)
        sm.transition("s1", StepState.FAILED)
        with pytest.raises(InvalidTransition):
            sm.transition("s1", StepState.PASSED)

    def test_skipped_is_terminal(self):
        sm = StepStateMachine("test")
        sm.load_from_plan([{"id": "s1", "label": "Step 1"}])
        sm.transition("s1", StepState.SKIPPED)
        with pytest.raises(InvalidTransition):
            sm.transition("s1", StepState.RUNNING)

    def test_blocked_to_passed_rejected(self):
        sm = StepStateMachine("test")
        sm.load_from_plan([{"id": "s1", "label": "Step 1"}])
        sm.transition("s1", StepState.BLOCKED)
        with pytest.raises(InvalidTransition):
            sm.transition("s1", StepState.PASSED)


class TestRetryFlow:
    """Test retry from FAILED state."""

    def test_failed_to_running_allowed(self):
        sm = StepStateMachine("test")
        sm.load_from_plan([{"id": "s1", "label": "Step 1"}])
        sm.transition("s1", StepState.RUNNING)
        sm.transition("s1", StepState.FAILED)
        sm.transition("s1", StepState.RUNNING)  # Retry
        assert sm.get_state("s1") == StepState.RUNNING
        assert sm.get_status("s1").run_count == 2

    def test_needs_attention_to_running(self):
        sm = StepStateMachine("test")
        sm.load_from_plan([{"id": "s1", "label": "Step 1"}])
        sm.transition("s1", StepState.RUNNING)
        sm.transition("s1", StepState.NEEDS_ATTENTION)
        sm.transition("s1", StepState.RUNNING)  # Re-run after fixing
        assert sm.get_state("s1") == StepState.RUNNING

    def test_needs_attention_to_passed(self):
        """User confirms they reviewed the findings."""
        sm = StepStateMachine("test")
        sm.load_from_plan([{"id": "s1", "label": "Step 1"}])
        sm.transition("s1", StepState.RUNNING)
        sm.transition("s1", StepState.NEEDS_ATTENTION)
        sm.transition("s1", StepState.PASSED)  # User confirmed
        assert sm.get_state("s1") == StepState.PASSED


class TestDetermineState:
    """Test the determine_state function."""

    def test_ok_no_findings_passes(self):
        state, meta = determine_state({"ok": True, "summary": "Done"})
        assert state == StepState.PASSED

    def test_not_ok_fails(self):
        state, meta = determine_state({"ok": False, "error": "Broke"})
        assert state == StepState.FAILED
        assert "Broke" in meta.get("error_message", "")

    def test_findings_needs_attention(self):
        class F:
            fix_available = True
            is_transitive = False
            source_module = None
        state, meta = determine_state({"ok": True}, findings=[F(), F()])
        assert state == StepState.NEEDS_ATTENTION
        assert meta["findings_count"] == 2

    def test_all_transitive_blocked(self):
        class F:
            fix_available = True
            is_transitive = True
            source_module = "core"
        state, meta = determine_state(
            {"ok": True},
            findings=[F()],
            blocking_modules=["core"],
        )
        assert state == StepState.BLOCKED

    def test_verification_failed(self):
        state, meta = determine_state({"ok": True}, verification_passed=False)
        assert state == StepState.FAILED


class TestV1BackwardCompat:
    """Test loading v1 format plans."""

    def test_done_true_becomes_passed(self):
        sm = StepStateMachine("test")
        sm.load_from_plan([{"id": "s1", "label": "S1", "done": True}])
        assert sm.get_state("s1") == StepState.PASSED

    def test_done_false_becomes_pending(self):
        sm = StepStateMachine("test")
        sm.load_from_plan([{"id": "s1", "label": "S1", "done": False}])
        assert sm.get_state("s1") == StepState.PENDING

    def test_missing_done_becomes_pending(self):
        sm = StepStateMachine("test")
        sm.load_from_plan([{"id": "s1", "label": "S1"}])
        assert sm.get_state("s1") == StepState.PENDING

    def test_done_skipped(self):
        sm = StepStateMachine("test")
        sm.load_from_plan([{"id": "s1", "label": "S1", "done": "skipped"}])
        assert sm.get_state("s1") == StepState.SKIPPED


class TestProgress:
    """Test progress tracking."""

    def test_empty_plan(self):
        sm = StepStateMachine("test")
        sm.load_from_plan([])
        assert sm.all_done()

    def test_progress_calculation(self):
        sm = StepStateMachine("test")
        sm.load_from_plan([
            {"id": "s1", "label": "S1", "done": True},
            {"id": "s2", "label": "S2"},
            {"id": "s3", "label": "S3"},
        ])
        progress = sm.progress()
        assert progress["total"] == 3
        assert progress["done"] == 1
        assert progress["percent"] == pytest.approx(33.3, abs=0.1)

    def test_next_actionable(self):
        sm = StepStateMachine("test")
        sm.load_from_plan([
            {"id": "s1", "label": "S1", "done": True},
            {"id": "s2", "label": "S2"},
            {"id": "s3", "label": "S3"},
        ])
        assert sm.next_actionable_step() == "s2"

    def test_next_actionable_blocked(self):
        sm = StepStateMachine("test")
        sm.load_from_plan([
            {"id": "s1", "label": "S1", "done": True},
            {"id": "s2", "label": "S2", "state": "blocked"},
            {"id": "s3", "label": "S3"},
        ])
        # Blocked step should stop — can't skip over it
        assert sm.next_actionable_step() is None
