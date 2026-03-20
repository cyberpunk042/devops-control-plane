"""Plan engine — generate and manage version plans.

Generates dynamic plans based on actual analysis results instead
of static recipes. Each plan's steps are tailored to what the
analysis found in the specific module.

Plan flow:
1. Run assessment (assess target achievability)
2. Generate plan steps from findings
3. Persist plan to project.yml
4. Execute steps (via step_executor / batch_runner)
5. Re-scan to verify completion
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..analysis.finding import AnalysisResult
    from ..analysis.version_resolver import TargetAssessment

from .state_machine import StepState, StepStateMachine

logger = logging.getLogger(__name__)


@dataclass
class PlanStep:
    """A step in a version plan."""
    id: str                         # "scan:abc123"
    label: str                      # "Scan for incompatible features"
    description: str = ""
    automation_id: str = ""         # "scan", "fix_all", "verify", etc.
    step_type: str = ""             # "analysis", "transform", "test", "manual", "config"
    state: str = "pending"
    category: str = ""              # For grouping in UI

    def to_yml(self) -> dict:
        """Convert to project.yml format."""
        d: dict = {
            "label": self.label,
            "id": self.id,
            "description": self.description,
            "step_type": self.step_type,
            "state": self.state,
        }
        if self.state == "passed":
            d["done"] = True
        elif self.state == "skipped":
            d["done"] = "skipped"
        else:
            d["done"] = False
        return d


@dataclass
class VersionPlan:
    """A complete version plan for a module."""
    module_name: str
    target_version: str
    direction: str = "downgrade"
    created_at: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    assessment: TargetAssessment | None = None

    def to_yml(self) -> dict:
        """Convert to project.yml version_plan format."""
        return {
            "target": self.target_version,
            "direction": self.direction,
            "date": "Now",
            "created_at": self.created_at,
            "checklist": [s.to_yml() for s in self.steps],
        }


def _make_id(automation_id: str) -> str:
    """Generate a step ID: automation_id:random_suffix."""
    suffix = hashlib.md5(
        f"{automation_id}{time.time()}".encode()
    ).hexdigest()[:8]
    return f"{automation_id}:{suffix}"


class PlanEngine:
    """Generate and manage version plans."""

    def generate_plan(
        self,
        module_name: str,
        target_version: str,
        direction: str,
        analysis: AnalysisResult,
        assessment: TargetAssessment | None = None,
    ) -> VersionPlan:
        """Generate a version plan from analysis results.

        Steps are dynamic — based on what the analysis actually found.
        Not a static recipe.
        """
        plan = VersionPlan(
            module_name=module_name,
            target_version=target_version,
            direction=direction,
            created_at=datetime.now(timezone.utc).isoformat(),
            assessment=assessment,
        )

        if direction == "downgrade":
            self._generate_downgrade_steps(plan, analysis, assessment)
        else:
            self._generate_upgrade_steps(plan, analysis, assessment)

        return plan

    def _generate_downgrade_steps(
        self,
        plan: VersionPlan,
        analysis: AnalysisResult,
        assessment: TargetAssessment | None,
    ) -> None:
        """Generate steps for a downgrade plan."""
        direct = analysis.direct_findings
        transitive = analysis.transitive_findings
        fixable = [f for f in direct if f.fix_available]
        manual = [f for f in direct if not f.fix_available]

        # Group fixable by strategy
        future_fixable = [f for f in fixable if f.fix_strategy == "add_future_import"]
        import_fixable = [f for f in fixable if f.fix_strategy in (
            "replace_import", "replace_import_and_usages", "add_backport_import",
        )]
        rewrite_fixable = [f for f in fixable if f.fix_strategy in (
            "rewrite_expression",
        )]
        other_fixable = [f for f in fixable if f not in future_fixable + import_fixable + rewrite_fixable]

        # Step 1: Scan
        plan.steps.append(PlanStep(
            id=_make_id("scan"),
            label=f"Scan for features incompatible with Python {plan.target_version}",
            description=f"AST-based analysis of all source files — finds {analysis.total_findings} finding(s)",
            automation_id="scan",
            step_type="analysis",
            category="analysis",
        ))

        # Step 2: Blocked by transitive (if applicable)
        if assessment and assessment.blocking_modules:
            plan.steps.append(PlanStep(
                id=_make_id("blocked"),
                label=f"Fix dependency module(s): {', '.join(assessment.blocking_modules)}",
                description=f"{len(transitive)} transitive incompatibilities in {', '.join(assessment.blocking_modules)}",
                automation_id="blocked",
                step_type="manual",
                category="dependency",
                state="blocked",
            ))

        # Step 3: Add __future__ annotations (if needed)
        if future_fixable:
            files = sorted(set(f.file for f in future_fixable))
            plan.steps.append(PlanStep(
                id=_make_id("add_future_annotations"),
                label=f"Add __future__ annotations ({len(files)} file(s))",
                description="Enable PEP 604/585 syntax on older Python via deferred evaluation",
                automation_id="add_future_annotations",
                step_type="transform",
                category="fix",
            ))

        # Step 4: Fix import-level issues
        if import_fixable:
            by_feature: dict[str, list] = {}
            for f in import_fixable:
                by_feature.setdefault(f.feature_name, []).append(f)

            for feature_name, findings in sorted(by_feature.items()):
                files = sorted(set(f.file for f in findings))
                plan.steps.append(PlanStep(
                    id=_make_id("fix_auto"),
                    label=f"Fix {feature_name} ({len(files)} file(s))",
                    description=f"Auto-fix: {findings[0].fix_strategy}",
                    automation_id="fix_auto",
                    step_type="transform",
                    category="fix",
                ))

        # Step 5: Fix expression-level issues
        if rewrite_fixable:
            by_feature = {}
            for f in rewrite_fixable:
                by_feature.setdefault(f.feature_name, []).append(f)

            for feature_name, findings in sorted(by_feature.items()):
                files = sorted(set(f.file for f in findings))
                plan.steps.append(PlanStep(
                    id=_make_id("fix_auto"),
                    label=f"Fix {feature_name} ({len(files)} file(s))",
                    description=f"Rewrite expression to compatible form",
                    automation_id="fix_auto",
                    step_type="transform",
                    category="fix",
                ))

        # Step 6: Other auto-fixable
        if other_fixable:
            plan.steps.append(PlanStep(
                id=_make_id("fix_auto"),
                label=f"Apply remaining auto-fixes ({len(other_fixable)} finding(s))",
                automation_id="fix_auto",
                step_type="transform",
                category="fix",
            ))

        # Step 7: Manual fixes
        if manual:
            by_feature = {}
            for f in manual:
                by_feature.setdefault(f.feature_name, []).append(f)

            for feature_name, findings in sorted(by_feature.items()):
                plan.steps.append(PlanStep(
                    id=_make_id("manual"),
                    label=f"Manual fix: {feature_name} ({len(findings)} occurrence(s))",
                    description="Cannot be auto-fixed — requires manual rewrite",
                    automation_id="manual",
                    step_type="manual",
                    category="fix",
                ))

        # Step 8: Verify fixes
        if fixable or manual:
            plan.steps.append(PlanStep(
                id=_make_id("verify"),
                label="Verify all fixes",
                description="Re-scan module to confirm all incompatibilities are resolved",
                automation_id="verify",
                step_type="analysis",
                category="verification",
            ))

        # Step 9: Check dependencies
        plan.steps.append(PlanStep(
            id=_make_id("check_dep_compat"),
            label=f"Check dependency compatibility with Python {plan.target_version}",
            description="Verify all pip packages support the target version",
            automation_id="check_dep_compat",
            step_type="analysis",
            category="dependency",
        ))

        # Step 10: Update config
        plan.steps.append(PlanStep(
            id=_make_id("update_config"),
            label=f"Update requires-python to >={plan.target_version}",
            description="Update pyproject.toml or setup.cfg version constraint",
            automation_id="update_config",
            step_type="config",
            category="config",
        ))

        # Step 11: Re-scan
        plan.steps.append(PlanStep(
            id=_make_id("rescan"),
            label="Final re-scan and confirm",
            description="Verify zero incompatibilities remain",
            automation_id="rescan_module",
            step_type="analysis",
            category="verification",
        ))

    def _generate_upgrade_steps(
        self,
        plan: VersionPlan,
        analysis: AnalysisResult,
        assessment: TargetAssessment | None,
    ) -> None:
        """Generate steps for an upgrade plan."""
        direct = analysis.direct_findings
        fixable = [f for f in direct if f.fix_available]

        # Step 1: Scan for upgrade opportunities
        plan.steps.append(PlanStep(
            id=_make_id("scan"),
            label=f"Scan for upgrade opportunities to Python {plan.target_version}",
            description="Find backports, workarounds, and deprecated patterns to modernize",
            automation_id="scan",
            step_type="analysis",
            category="analysis",
        ))

        # Step 2: Remove backports
        backport_findings = [f for f in fixable if f.fix_strategy in (
            "replace_import", "add_backport_import",
        )]
        if backport_findings:
            plan.steps.append(PlanStep(
                id=_make_id("remove_backports"),
                label=f"Remove backport imports ({len(backport_findings)} finding(s))",
                description="Replace backport imports with stdlib equivalents",
                automation_id="fix_auto",
                step_type="transform",
                category="modernize",
            ))

        # Step 3: Remove __future__
        future_findings = [f for f in fixable if "future" in f.fix_strategy]
        if future_findings:
            plan.steps.append(PlanStep(
                id=_make_id("remove_future"),
                label="Remove __future__ annotations imports",
                description="No longer needed with the new target version",
                automation_id="remove_future",
                step_type="transform",
                category="modernize",
            ))

        # Step 4: Modernize code
        modernize_findings = [f for f in fixable if f not in backport_findings + future_findings]
        if modernize_findings:
            plan.steps.append(PlanStep(
                id=_make_id("modernize"),
                label=f"Modernize code ({len(modernize_findings)} opportunity(ies))",
                description="Use modern syntax and APIs",
                automation_id="fix_auto",
                step_type="transform",
                category="modernize",
            ))

        # Step 5: Update config
        plan.steps.append(PlanStep(
            id=_make_id("update_config"),
            label=f"Update requires-python to >={plan.target_version}",
            automation_id="update_config",
            step_type="config",
            category="config",
        ))

        # Step 6: Remove unused backport dependencies
        plan.steps.append(PlanStep(
            id=_make_id("cleanup_deps"),
            label="Remove unused backport dependencies",
            description="Remove packages like tomli, typing-extensions if no longer needed",
            automation_id="cleanup_deps",
            step_type="config",
            category="config",
        ))

        # Step 7: Verify
        plan.steps.append(PlanStep(
            id=_make_id("verify"),
            label="Verify changes",
            description="Run tests to confirm everything works on the new version",
            automation_id="verify",
            step_type="analysis",
            category="verification",
        ))

    def save_plan(
        self,
        plan: VersionPlan,
        project_root: Path,
    ) -> bool:
        """Save a plan to project.yml."""
        try:
            import yaml
            from src.core.config.loader import find_project_file

            config_path = find_project_file()
            if not config_path:
                logger.error("project.yml not found")
                return False

            raw = config_path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw)
            project_data = data.get("project", data) if "project" in data else data

            # Find the module and set/update its version_plan
            for mod in project_data.get("modules", []):
                if mod.get("name") == plan.module_name:
                    mod["version_plan"] = plan.to_yml()
                    break
            else:
                logger.error("Module '%s' not found in project.yml", plan.module_name)
                return False

            config_path.write_text(
                yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

            logger.info("Saved plan for '%s' to project.yml", plan.module_name)
            return True

        except Exception as exc:
            logger.error("Failed to save plan: %s", exc)
            return False

    def load_plan(
        self,
        module_name: str,
        project_root: Path,
    ) -> VersionPlan | None:
        """Load a plan from project.yml."""
        try:
            import yaml
            from src.core.config.loader import find_project_file

            config_path = find_project_file()
            if not config_path:
                return None

            raw = config_path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw)
            project_data = data.get("project", data) if "project" in data else data

            for mod in project_data.get("modules", []):
                if mod.get("name") == module_name:
                    vp = mod.get("version_plan")
                    if not vp:
                        return None

                    plan = VersionPlan(
                        module_name=module_name,
                        target_version=vp.get("target", ""),
                        direction=vp.get("direction", "downgrade"),
                        created_at=vp.get("created_at", ""),
                    )

                    for step in vp.get("checklist", []):
                        plan.steps.append(PlanStep(
                            id=step.get("id", ""),
                            label=step.get("label", ""),
                            description=step.get("description", ""),
                            step_type=step.get("step_type", ""),
                            state=step.get("state", "pending"),
                            automation_id=step.get("id", "").split(":")[0] if ":" in step.get("id", "") else "",
                        ))

                    return plan

        except Exception as exc:
            logger.error("Failed to load plan: %s", exc)
        return None
