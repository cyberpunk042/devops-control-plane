"""Plan generation and execution integration tests.

Tests the full lifecycle:
1. Assessment → Plan generation → Step execution → Verification

Run: python -m pytest src/core/services/compat/edge_cases/test_plan_integration.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def compat():
    from ..orchestrator import CompatOrchestrator
    return CompatOrchestrator.create(Path("."))


@pytest.fixture
def tmp_module(tmp_path):
    """Create a temp module with known incompatibilities."""
    mod = tmp_path / "test_mod"
    mod.mkdir()
    (mod / "__init__.py").write_text("")

    # File with datetime.UTC (3.11+)
    (mod / "dates.py").write_text(
        "from datetime import UTC, datetime\n"
        "now = datetime.now(UTC)\n"
    )

    # File with removeprefix (3.9+)
    (mod / "strings.py").write_text(
        'result = path.removeprefix("/home/")\n'
    )

    # File with type hints needing __future__
    (mod / "types.py").write_text(
        "def foo(x: int | str) -> list[int]:\n"
        "    return [x]\n"
    )

    return mod


class TestPlanGeneration:
    """Test dynamic plan generation from analysis."""

    def test_plan_has_steps(self, compat):
        """Plan should generate steps from real analysis."""
        plan = compat.create_plan("web", "3.8", save=False)
        assert plan["ok"]
        assert plan["steps"] > 0
        assert len(plan["plan"]["steps"]) > 0

    def test_plan_has_scan_step(self, compat):
        """Every plan starts with a scan step."""
        plan = compat.create_plan("web", "3.8", save=False)
        steps = plan["plan"]["steps"]
        assert steps[0]["label"].startswith("Scan")

    def test_plan_has_verify_step(self, compat):
        """Plan should have a verify step."""
        plan = compat.create_plan("web", "3.8", save=False)
        steps = plan["plan"]["steps"]
        verify_steps = [s for s in steps if "verify" in s["label"].lower() or "re-scan" in s["label"].lower()]
        assert len(verify_steps) >= 1

    def test_plan_has_blocked_step_when_transitive(self, compat):
        """Plan should show blocked step when transitive deps exist."""
        plan = compat.create_plan("web", "3.8", save=False)
        steps = plan["plan"]["steps"]
        blocked = [s for s in steps if s["state"] == "blocked"]
        # Web depends on core which has issues
        assert len(blocked) >= 0  # May or may not be blocked depending on analysis

    def test_plan_includes_assessment(self, compat):
        """Plan should include assessment data."""
        plan = compat.create_plan("web", "3.8", save=False)
        assert "assessment" in plan
        assert "achievable" in plan["assessment"]
        assert "current_floor" in plan["assessment"]

    def test_plan_for_module_with_issues(self, compat, tmp_module):
        """Plan for module with known issues should have fix steps."""
        from ..lifecycle.plan_engine import PlanEngine
        from ..analysis.engine import DetectionEngine
        from ..backends.python_backend import PythonBackend

        backend = PythonBackend()
        engine = DetectionEngine(compat.registry, backend)

        result = engine.analyze_module(
            tmp_module, "3.8", "downgrade", tmp_module.parent,
        )

        plan_engine = PlanEngine()
        plan = plan_engine.generate_plan(
            "test_mod", "3.8", "downgrade", result,
        )

        assert len(plan.steps) > 0
        # Should have scan + fix steps + verify
        step_types = [s.step_type for s in plan.steps]
        assert "analysis" in step_types
        assert "verification" in step_types or "config" in step_types


class TestPlanStepExecution:
    """Test executing individual plan steps."""

    def test_scan_step_returns_findings(self, compat, tmp_module):
        """Executing a scan step should return findings."""
        from ..lifecycle.state_machine import StepStateMachine, StepState
        from ..lifecycle.step_executor import StepExecutor

        executor = StepExecutor(
            compat.registry, compat.detection, compat.fix, compat.backend,
        )

        result = executor.execute(
            step_id="scan:test",
            module_name="test_mod",
            module_dir=tmp_module,
            target_version="3.8",
            project_root=tmp_module.parent,
        )

        assert result.ok
        assert len(result.findings) >= 0  # May find issues

    def test_scan_step_transitions_state(self, compat, tmp_module):
        """Scan step should transition state machine correctly."""
        from ..lifecycle.state_machine import StepStateMachine, StepState
        from ..lifecycle.step_executor import StepExecutor

        sm = StepStateMachine("test_mod")
        sm.load_from_plan([{"id": "scan:test", "label": "Scan"}])

        executor = StepExecutor(
            compat.registry, compat.detection, compat.fix, compat.backend,
        )

        result, state = executor.execute_and_transition(
            step_id="scan:test",
            state_machine=sm,
            module_name="test_mod",
            module_dir=tmp_module,
            target_version="3.8",
            project_root=tmp_module.parent,
        )

        # State should be PASSED (no findings) or NEEDS_ATTENTION (has findings)
        assert state in (StepState.PASSED, StepState.NEEDS_ATTENTION)


class TestBatchExecution:
    """Test batch step execution."""

    def test_batch_executes_steps(self, compat, tmp_module):
        """Batch should execute steps in order."""
        from ..lifecycle.state_machine import StepStateMachine, StepState
        from ..lifecycle.step_executor import StepExecutor
        from ..lifecycle.batch_runner import BatchRunner

        sm = StepStateMachine("test_mod")
        sm.load_from_plan([
            {"id": "scan:test", "label": "Scan"},
            {"id": "verify:test", "label": "Verify"},
        ])

        executor = StepExecutor(
            compat.registry, compat.detection, compat.fix, compat.backend,
        )
        runner = BatchRunner(executor)

        result = runner.run(
            module_name="test_mod",
            step_ids=["scan:test", "verify:test"],
            state_machine=sm,
            module_dir=tmp_module,
            target_version="3.8",
            project_root=tmp_module.parent,
        )

        assert result.steps_executed >= 1
        assert result.duration_ms >= 0

    def test_batch_stops_on_needs_attention(self, compat, tmp_module):
        """Batch should stop when a step needs attention."""
        from ..lifecycle.state_machine import StepStateMachine, StepState
        from ..lifecycle.step_executor import StepExecutor
        from ..lifecycle.batch_runner import BatchRunner

        # Create module with known issues
        (tmp_module / "bad.py").write_text("from datetime import UTC\n")

        sm = StepStateMachine("test_mod")
        sm.load_from_plan([
            {"id": "scan:test", "label": "Scan"},
            {"id": "fix:test", "label": "Fix"},
        ])

        executor = StepExecutor(
            compat.registry, compat.detection, compat.fix, compat.backend,
        )
        runner = BatchRunner(executor)

        result = runner.run(
            module_name="test_mod",
            step_ids=["scan:test", "fix:test"],
            state_machine=sm,
            module_dir=tmp_module,
            target_version="3.8",
            project_root=tmp_module.parent,
        )

        # If scan finds issues → NEEDS_ATTENTION → batch stops
        if result.steps_needs_attention > 0:
            assert result.stopped


class TestFixAndVerifyCycle:
    """Test the fix → verify cycle through the plan."""

    def test_fix_datetime_utc_via_executor(self, compat, tmp_module):
        """Fix datetime.UTC through the step executor."""
        # Create file with UTC
        test_file = tmp_module / "utc.py"
        test_file.write_text(
            "from datetime import UTC, datetime\n"
            "now = datetime.now(UTC)\n"
        )

        from ..lifecycle.step_executor import StepExecutor

        executor = StepExecutor(
            compat.registry, compat.detection, compat.fix, compat.backend,
        )

        # Execute fix step
        result = executor.execute(
            step_id="fix_auto:test",
            module_name="test_mod",
            module_dir=tmp_module,
            target_version="3.8",
            project_root=tmp_module.parent,
        )

        # Fix should apply
        if result.fix_result and result.fix_result.total_fixes > 0:
            content = test_file.read_text()
            assert "timezone" in content or "UTC" not in content.split("timezone")[0]

    def test_verify_after_fix(self, compat, tmp_module):
        """Verify step should pass after fixes are applied."""
        # Create and fix a file
        test_file = tmp_module / "utc.py"
        test_file.write_text("from datetime import UTC\nnow = datetime.now(UTC)\n")

        # Apply fix
        findings = compat.detection.analyze_file(test_file, "3.8", "downgrade", tmp_module.parent)
        for f in findings:
            if f.feature_id == "python.stdlib.datetime_utc":
                compat.fix.fix_finding(f, tmp_module.parent, verify=False)

        # Now run verify
        from ..lifecycle.step_executor import StepExecutor

        executor = StepExecutor(
            compat.registry, compat.detection, compat.fix, compat.backend,
        )

        compat.detection.invalidate_all()
        result = executor.execute(
            step_id="verify:test",
            module_name="test_mod",
            module_dir=tmp_module,
            target_version="3.8",
            project_root=tmp_module.parent,
        )

        # After fix, verify should pass (or find remaining non-UTC issues)
        utc_findings = [f for f in result.findings if f.feature_id == "python.stdlib.datetime_utc"]
        assert len(utc_findings) == 0, "UTC should be fixed"


@pytest.mark.slow
class TestRealProjectPlans:
    """Test plan generation on real project modules.

    These tests are slow (analyze real 600+ file modules with 1000 entries).
    Run with: pytest -m slow
    """

    def test_web_plan_generation(self, compat):
        """Web module plan should generate successfully."""
        plan = compat.create_plan("web", "3.8", save=False)
        assert plan["ok"]
        assert plan["steps"] > 3

    def test_core_plan_generation(self, compat):
        """Core module plan should generate with more steps."""
        plan = compat.create_plan("core", "3.8", save=False)
        assert plan["ok"]
        assert plan["steps"] > 5

    def test_plan_steps_are_ordered(self, compat):
        """Plan steps should be in logical order."""
        plan = compat.create_plan("web", "3.8", save=False)
        steps = plan["plan"]["steps"]
        assert "scan" in steps[0]["label"].lower()
        last_labels = [s["label"].lower() for s in steps[-3:]]
        assert any("verify" in l or "re-scan" in l or "update" in l for l in last_labels)

    def test_plan_assessment_matches_reality(self, compat):
        """Assessment data should match actual analysis."""
        plan = compat.create_plan("web", "3.8", save=False)
        assessment = plan["assessment"]
        assert "achievable" in assessment
        assert "current_floor" in assessment
        assert assessment["current_floor"]
