"""Step executor — execute a single plan step.

This is the SHARED function called by both individual execution
and batch execution. There is ONE code path. No duplication.
No divergent logic between individual and batch.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..analysis.engine import DetectionEngine
    from ..analysis.finding import Finding
    from ..backends.base import LanguageBackend
    from ..database.registry import FeatureRegistry
    from ..fix.engine import FixEngine, ModuleFixResult

from .state_machine import StepState, StepStateMachine, determine_state

logger = logging.getLogger(__name__)


@dataclass
class StepExecutionResult:
    """Raw result of executing a step (before state determination)."""
    step_id: str
    ok: bool = True
    summary: str = ""
    error: str | None = None
    duration_ms: int = 0

    # Analysis results
    findings: list[Finding] = field(default_factory=list)
    blocking_modules: list[str] = field(default_factory=list)

    # Fix results
    fix_result: ModuleFixResult | None = None
    verification_passed: bool | None = None

    # Raw handler result (for backward compat / custom data)
    raw: dict = field(default_factory=dict)


class StepExecutor:
    """Execute a single step and determine its state.

    Used by both individual step execution AND the batch runner.
    Both call execute() → determine_state() → transition().
    Same functions. Same logic. No divergence.
    """

    def __init__(
        self,
        registry: FeatureRegistry,
        detection_engine: DetectionEngine,
        fix_engine: FixEngine,
        backend: LanguageBackend,
    ):
        self._registry = registry
        self._detection = detection_engine
        self._fix = fix_engine
        self._backend = backend

    def execute(
        self,
        step_id: str,
        module_name: str,
        module_dir: Path,
        target_version: str,
        project_root: Path,
        direction: str = "downgrade",
        module_configs: list[dict] | None = None,
    ) -> StepExecutionResult:
        """Execute a step and return raw results.

        Does NOT determine state or transition the state machine.
        The caller (individual or batch) does that using determine_state().
        """
        t0 = time.time()
        automation_id = step_id.split(":")[0] if ":" in step_id else step_id

        try:
            result = self._execute_by_type(
                automation_id=automation_id,
                module_name=module_name,
                module_dir=module_dir,
                target_version=target_version,
                project_root=project_root,
                direction=direction,
                module_configs=module_configs,
            )
        except Exception as exc:
            logger.error("Step %s failed: %s", step_id, exc, exc_info=True)
            result = StepExecutionResult(
                step_id=step_id,
                ok=False,
                error=f"Step execution failed: {exc}",
            )

        result.step_id = step_id
        result.duration_ms = int((time.time() - t0) * 1000)
        return result

    def execute_and_transition(
        self,
        step_id: str,
        state_machine: StepStateMachine,
        module_name: str,
        module_dir: Path,
        target_version: str,
        project_root: Path,
        direction: str = "downgrade",
        module_configs: list[dict] | None = None,
        trigger: str = "execution",
    ) -> tuple[StepExecutionResult, StepState]:
        """Execute a step AND transition its state.

        Convenience method that combines execute() + determine_state() + transition().
        Used by both individual and batch paths.
        """
        # Transition to RUNNING
        state_machine.transition(step_id, StepState.RUNNING, trigger=trigger)

        # Execute
        result = self.execute(
            step_id=step_id,
            module_name=module_name,
            module_dir=module_dir,
            target_version=target_version,
            project_root=project_root,
            direction=direction,
            module_configs=module_configs,
        )

        # Determine state
        new_state, metadata = determine_state(
            result={"ok": result.ok, "error": result.error, "summary": result.summary},
            findings=result.findings,
            verification_passed=result.verification_passed,
            blocking_modules=result.blocking_modules,
        )

        # Transition to determined state
        metadata["duration_ms"] = result.duration_ms
        state_machine.transition(step_id, new_state, trigger=trigger, **metadata)

        return result, new_state

    def _execute_by_type(
        self,
        automation_id: str,
        module_name: str,
        module_dir: Path,
        target_version: str,
        project_root: Path,
        direction: str,
        module_configs: list[dict] | None,
    ) -> StepExecutionResult:
        """Route to the appropriate step handler based on automation_id."""

        # Analysis steps
        if automation_id in ("scan_incompatible_features", "scan"):
            return self._execute_scan(
                module_name, module_dir, target_version, project_root,
                direction, module_configs,
            )

        if automation_id in ("guide_incompatible_syntax", "guide"):
            return self._execute_scan(
                module_name, module_dir, target_version, project_root,
                direction, module_configs,
            )

        # Fix steps
        if automation_id in ("fix_all", "fix_auto", "apply_fixes"):
            return self._execute_fix(
                module_name, module_dir, target_version, project_root,
                direction, module_configs,
            )

        if automation_id == "add_future_annotations":
            return self._execute_fix_specific(
                module_name, module_dir, target_version, project_root,
                feature_filter=lambda e: e.fix.strategy.value == "add_future_import",
                direction=direction,
                module_configs=module_configs,
            )

        # Verification steps
        if automation_id in ("verify", "verify_fixes"):
            return self._execute_verify(
                module_name, module_dir, target_version, project_root,
                direction,
            )

        if automation_id == "rescan_module":
            return self._execute_scan(
                module_name, module_dir, target_version, project_root,
                direction, module_configs,
            )

        # Dependency steps
        if automation_id.startswith("check_dep_compat"):
            return self._execute_dep_check(
                module_name, module_dir, target_version, project_root,
            )

        # Fallback: unknown step type
        return StepExecutionResult(
            step_id=automation_id,
            ok=False,
            error=f"Unknown step type: {automation_id}",
        )

    # ── Step handlers ────────────────────────────────────────────

    def _execute_scan(
        self,
        module_name: str,
        module_dir: Path,
        target_version: str,
        project_root: Path,
        direction: str,
        module_configs: list[dict] | None,
    ) -> StepExecutionResult:
        """Run analysis scan on the module."""
        analysis = self._detection.analyze_transitive(
            module_dir=module_dir,
            module_name=module_name,
            target_version=target_version,
            project_root=project_root,
            module_configs=module_configs,
            direction=direction,
        )

        # Identify blocking modules
        transitive = analysis.transitive_findings
        blocking = set()
        for f in transitive:
            if f.source_module and f.source_module != module_name:
                blocking.add(f.source_module)

        return StepExecutionResult(
            step_id="scan",
            ok=True,
            summary=f"{analysis.total_findings} finding(s) in {analysis.files_scanned} files",
            findings=analysis.findings,
            blocking_modules=sorted(blocking),
        )

    def _execute_fix(
        self,
        module_name: str,
        module_dir: Path,
        target_version: str,
        project_root: Path,
        direction: str,
        module_configs: list[dict] | None,
    ) -> StepExecutionResult:
        """Apply all auto-fixable fixes to the module."""
        # First, detect what needs fixing
        analysis = self._detection.analyze_module(
            module_dir=module_dir,
            target_version=target_version,
            direction=direction,
            project_root=project_root,
        )

        fixable = [f for f in analysis.findings if f.fix_available]
        if not fixable:
            return StepExecutionResult(
                step_id="fix",
                ok=True,
                summary="No auto-fixable findings",
            )

        # Apply fixes
        fix_result = self._fix.fix_module(
            module_dir=module_dir,
            findings=fixable,
            module_name=module_name,
            project_root=project_root,
            verify=True,
        )

        return StepExecutionResult(
            step_id="fix",
            ok=fix_result.all_verified,
            summary=(
                f"Fixed {fix_result.verified_fixes}/{fix_result.total_fixes} findings"
                + (f" ({fix_result.failed_fixes} failed)" if fix_result.failed_fixes else "")
            ),
            error=(
                f"{fix_result.failed_fixes} fix(es) failed verification"
                if fix_result.failed_fixes else None
            ),
            fix_result=fix_result,
            verification_passed=fix_result.all_verified if fix_result.total_fixes > 0 else None,
        )

    def _execute_fix_specific(
        self,
        module_name: str,
        module_dir: Path,
        target_version: str,
        project_root: Path,
        feature_filter: object,
        direction: str,
        module_configs: list[dict] | None,
    ) -> StepExecutionResult:
        """Apply fixes for specific feature types only."""
        analysis = self._detection.analyze_module(
            module_dir=module_dir,
            target_version=target_version,
            direction=direction,
            project_root=project_root,
        )

        # Filter findings to specific features
        matching = []
        for f in analysis.findings:
            entry = self._registry.get(f.feature_id)
            if entry and feature_filter(entry):
                matching.append(f)

        if not matching:
            return StepExecutionResult(
                step_id="fix_specific",
                ok=True,
                summary="No matching findings to fix",
            )

        fix_result = self._fix.fix_module(
            module_dir=module_dir,
            findings=matching,
            module_name=module_name,
            project_root=project_root,
            verify=True,
        )

        return StepExecutionResult(
            step_id="fix_specific",
            ok=fix_result.all_verified,
            summary=f"Fixed {fix_result.verified_fixes}/{fix_result.total_fixes}",
            fix_result=fix_result,
            verification_passed=fix_result.all_verified if fix_result.total_fixes > 0 else None,
        )

    def _execute_verify(
        self,
        module_name: str,
        module_dir: Path,
        target_version: str,
        project_root: Path,
        direction: str,
    ) -> StepExecutionResult:
        """Re-scan module to verify all fixes are applied."""
        analysis = self._detection.analyze_module(
            module_dir=module_dir,
            target_version=target_version,
            direction=direction,
            project_root=project_root,
        )

        if analysis.total_findings == 0:
            return StepExecutionResult(
                step_id="verify",
                ok=True,
                summary=f"Clean — 0 findings in {analysis.files_scanned} files",
            )

        return StepExecutionResult(
            step_id="verify",
            ok=False,
            error=f"{analysis.total_findings} finding(s) remain after fixes",
            summary=f"{analysis.total_findings} remaining in {analysis.files_with_findings} files",
            findings=analysis.findings,
        )

    def _execute_dep_check(
        self,
        module_name: str,
        module_dir: Path,
        target_version: str,
        project_root: Path,
    ) -> StepExecutionResult:
        """Check dependency compatibility via package registry."""
        from ..analysis.dep_analyzer import DependencyAnalyzer

        analyzer = DependencyAnalyzer()
        dep_result = analyzer.analyze(module_dir, "python", target_version)

        if dep_result.all_compatible:
            return StepExecutionResult(
                step_id="dep_check",
                ok=True,
                summary=f"All {len(dep_result.packages)} dependencies compatible with Python {target_version}",
            )

        # Has incompatible deps — build findings-like objects for state determination
        incompat = dep_result.incompatible_packages
        return StepExecutionResult(
            step_id="dep_check",
            ok=True,
            summary=f"{len(incompat)} incompatible package(s) found",
            findings=[
                type("DepFinding", (), {
                    "fix_available": False,
                    "is_transitive": False,
                    "source_module": None,
                })()
                for p in incompat
            ],
        )
