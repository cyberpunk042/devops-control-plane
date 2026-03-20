"""Compat system orchestrator — top-level API for all operations.

This is the single entry point for the web API, CLI, and any
other consumer. It wires together the registry, detection engine,
fix engine, state machine, and version resolver.

Usage:
    compat = CompatOrchestrator.create(project_root)
    assessment = compat.assess("web", "3.8")
    result = compat.analyze("web", "3.8")
    fix_result = compat.fix_all("web", "3.8")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .analysis.engine import DetectionEngine
from .analysis.finding import AnalysisResult
from .analysis.version_resolver import TargetAssessment, VersionResolver
from .backends.python_backend import PythonBackend
from .database.registry import FeatureRegistry
from .fix.engine import FixEngine, ModuleFixResult
from .lifecycle.batch_runner import BatchResult, BatchRunner
from .lifecycle.state_machine import StepStateMachine
from .lifecycle.step_executor import StepExecutor

logger = logging.getLogger(__name__)


class CompatOrchestrator:
    """Top-level API for the compat system."""

    def __init__(
        self,
        project_root: Path,
        registry: FeatureRegistry,
        detection: DetectionEngine,
        fix: FixEngine,
        resolver: VersionResolver,
        executor: StepExecutor,
        batch_runner: BatchRunner,
        backend: PythonBackend,
        module_configs: list[dict] | None = None,
    ):
        self.project_root = project_root
        self.registry = registry
        self.detection = detection
        self.fix = fix
        self.resolver = resolver
        self.executor = executor
        self.batch_runner = batch_runner
        self.backend = backend
        self.module_configs = module_configs or []

    @classmethod
    def create(
        cls,
        project_root: Path | None = None,
        module_configs: list[dict] | None = None,
    ) -> CompatOrchestrator:
        """Create a fully wired orchestrator.

        Loads the feature database, creates all engines,
        and returns a ready-to-use orchestrator.
        """
        project_root = project_root or Path(".")

        # Load module configs from project.yml if not provided
        if module_configs is None:
            module_configs = _load_module_configs(project_root)

        # Build the stack
        registry = FeatureRegistry.load()
        backend = PythonBackend()
        detection = DetectionEngine(registry, backend)
        fix_engine = FixEngine(registry, detection, backend)
        resolver = VersionResolver(detection, registry, backend)
        executor = StepExecutor(registry, detection, fix_engine, backend)
        batch = BatchRunner(executor)

        return cls(
            project_root=project_root,
            registry=registry,
            detection=detection,
            fix=fix_engine,
            resolver=resolver,
            executor=executor,
            batch_runner=batch,
            backend=backend,
            module_configs=module_configs,
        )

    # ── Analysis ─────────────────────────────────────────────────

    def analyze(
        self,
        module_name: str,
        target_version: str,
        direction: str = "downgrade",
        include_transitive: bool = True,
    ) -> AnalysisResult:
        """Analyze a module for version compatibility."""
        module_dir = self._resolve_module_dir(module_name)
        if not module_dir:
            from .analysis.finding import AnalysisResult as AR
            return AR(module_dir="", language="python", target_version=target_version,
                      direction=direction)

        if include_transitive:
            return self.detection.analyze_transitive(
                module_dir=module_dir,
                module_name=module_name,
                target_version=target_version,
                project_root=self.project_root,
                module_configs=self.module_configs,
                direction=direction,
            )
        else:
            return self.detection.analyze_module(
                module_dir=module_dir,
                target_version=target_version,
                direction=direction,
                project_root=self.project_root,
            )

    def assess(
        self,
        module_name: str,
        target_version: str,
        direction: str = "downgrade",
    ) -> TargetAssessment:
        """Pre-plan assessment — is the target achievable?"""
        module_dir = self._resolve_module_dir(module_name)
        if not module_dir:
            return TargetAssessment(target=target_version, achievable=False,
                                    current_floor="", recommendation="Module not found")

        return self.resolver.assess_target(
            module_name=module_name,
            module_dir=module_dir,
            target_version=target_version,
            language="python",
            project_root=self.project_root,
            direction=direction,
            module_configs=self.module_configs,
        )

    # ── Fixes ────────────────────────────────────────────────────

    def fix_all(
        self,
        module_name: str,
        target_version: str,
        direction: str = "downgrade",
        verify: bool = True,
    ) -> ModuleFixResult:
        """Apply all auto-fixable fixes to a module."""
        module_dir = self._resolve_module_dir(module_name)
        if not module_dir:
            return ModuleFixResult(module_name=module_name)

        # Analyze first
        result = self.detection.analyze_module(
            module_dir=module_dir,
            target_version=target_version,
            direction=direction,
            project_root=self.project_root,
        )

        # Fix
        return self.fix.fix_module(
            module_dir=module_dir,
            findings=result.fixable_findings,
            module_name=module_name,
            project_root=self.project_root,
            verify=verify,
        )

    # ── Plan execution ───────────────────────────────────────────

    def execute_step(
        self,
        module_name: str,
        step_id: str,
        target_version: str,
        state_machine: StepStateMachine,
        direction: str = "downgrade",
    ) -> tuple:
        """Execute a single plan step."""
        module_dir = self._resolve_module_dir(module_name)
        if not module_dir:
            return None, None

        return self.executor.execute_and_transition(
            step_id=step_id,
            state_machine=state_machine,
            module_name=module_name,
            module_dir=module_dir,
            target_version=target_version,
            project_root=self.project_root,
            direction=direction,
            module_configs=self.module_configs,
        )

    def execute_batch(
        self,
        module_name: str,
        step_ids: list[str],
        target_version: str,
        state_machine: StepStateMachine,
        direction: str = "downgrade",
    ) -> BatchResult:
        """Execute multiple plan steps."""
        module_dir = self._resolve_module_dir(module_name)
        if not module_dir:
            return BatchResult(module_name=module_name)

        return self.batch_runner.run(
            module_name=module_name,
            step_ids=step_ids,
            state_machine=state_machine,
            module_dir=module_dir,
            target_version=target_version,
            project_root=self.project_root,
            direction=direction,
            module_configs=self.module_configs,
        )

    # ── Plan management ────────────────────────────────────────────

    def create_plan(
        self,
        module_name: str,
        target_version: str,
        direction: str = "downgrade",
        save: bool = True,
    ) -> dict:
        """Create a version plan from analysis results.

        Returns the plan as a dict suitable for API response.
        """
        from .lifecycle.plan_engine import PlanEngine

        module_dir = self._resolve_module_dir(module_name)
        if not module_dir:
            return {"ok": False, "error": f"Module '{module_name}' not found"}

        # Run assessment
        assessment = self.assess(module_name, target_version, direction)

        # Run analysis
        analysis = self.analyze(module_name, target_version, direction, include_transitive=True)

        # Generate plan
        engine = PlanEngine()
        plan = engine.generate_plan(
            module_name=module_name,
            target_version=target_version,
            direction=direction,
            analysis=analysis,
            assessment=assessment,
        )

        # Save to project.yml
        if save:
            engine.save_plan(plan, self.project_root)

        return {
            "ok": True,
            "module": module_name,
            "target": target_version,
            "direction": direction,
            "steps": len(plan.steps),
            "plan": {
                "steps": [
                    {
                        "id": s.id,
                        "label": s.label,
                        "description": s.description,
                        "type": s.step_type,
                        "state": s.state,
                        "category": s.category,
                    }
                    for s in plan.steps
                ],
            },
            "assessment": {
                "achievable": assessment.achievable,
                "current_floor": assessment.current_floor,
                "gap": assessment.gap,
                "code_fixes_auto": assessment.code_fixes_auto,
                "code_fixes_manual": assessment.code_fixes_manual,
                "blocking_modules": assessment.blocking_modules,
                "recommendation": assessment.recommendation,
            },
        }

    def get_plan(self, module_name: str) -> dict | None:
        """Load existing plan from project.yml."""
        from .lifecycle.plan_engine import PlanEngine

        engine = PlanEngine()
        plan = engine.load_plan(module_name, self.project_root)
        if not plan:
            return None

        return {
            "module": module_name,
            "target": plan.target_version,
            "direction": plan.direction,
            "steps": [
                {
                    "id": s.id,
                    "label": s.label,
                    "description": s.description,
                    "type": s.step_type,
                    "state": s.state,
                }
                for s in plan.steps
            ],
        }

    # ── Helpers ──────────────────────────────────────────────────

    def _resolve_module_dir(self, module_name: str) -> Path | None:
        """Resolve module name to directory path."""
        for mod in self.module_configs:
            if mod.get("name") == module_name:
                d = self.project_root / mod["path"]
                if d.is_dir():
                    return d
        return None


def _load_module_configs(project_root: Path) -> list[dict]:
    """Load module configs from project.yml."""
    try:
        import yaml
        config_path = project_root / "project.yml"
        if not config_path.is_file():
            return []
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        modules = data.get("modules", [])
        return [{"name": m.get("name", ""), "path": m.get("path", "")} for m in modules]
    except Exception as exc:
        logger.warning("Failed to load project.yml: %s", exc)
        return []
