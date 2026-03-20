"""Version constraint resolution — compute version floors and target assessments.

Answers: given a module's code and dependencies, what is the minimum
(or maximum) language version it can support? Is the target achievable?
What needs to change?

Aggregates findings from the detection engine and dependency analyzer
to compute code floor, dependency floor, effective floor, and transitive floor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..backends.base import LanguageBackend
    from ..database.registry import FeatureRegistry

from ..database.version import parse_version, version_above
from .engine import DetectionEngine
from .finding import AnalysisResult
from .import_resolver import ImportGraph, ImportResolver

logger = logging.getLogger(__name__)


# ── Data models ──────────────────────────────────────────────────


@dataclass
class FeatureUsage:
    """A feature that contributes to the version floor."""
    feature_id: str
    feature_name: str
    version: str                    # Version the feature was introduced
    occurrence_count: int
    files: list[str]
    fix_available: bool
    fix_strategy: str


@dataclass
class CodeFloor:
    """Minimum version required by the module's own code."""
    version: str                    # "3.11" — highest feature version found
    determining_features: list[FeatureUsage]
    total_features_above: int       # Count of features above a hypothetical target
    fixable_count: int
    manual_count: int


@dataclass
class DependencyFloor:
    """Minimum version required by external dependencies."""
    version: str                    # "3.8"
    determining_packages: list[dict]
    all_compatible: bool
    incompatible_packages: list[dict]


@dataclass
class EffectiveFloor:
    """Actual minimum version = max(code, dependency)."""
    version: str
    code_floor: CodeFloor
    dependency_floor: DependencyFloor
    determined_by: str              # "code" or "dependency"


@dataclass
class TransitiveFloor:
    """Minimum version considering transitive project dependencies."""
    version: str
    effective_floor: EffectiveFloor
    transitive_modules: dict[str, str]  # module_name → its floor version
    blocking_modules: list[str]         # Modules whose floor > target


@dataclass
class TargetAssessment:
    """Full assessment of whether a target version is achievable."""
    target: str
    achievable: bool
    current_floor: str
    gap: str | None = None              # "3.11 → 3.8" or None if achievable without fixes

    # What needs to happen
    code_fixes_needed: int = 0
    code_fixes_auto: int = 0
    code_fixes_manual: int = 0
    dep_changes_needed: int = 0
    transitive_fixes_needed: int = 0
    blocking_modules: list[str] = field(default_factory=list)

    # Fix order
    fix_order: list[list[str]] = field(default_factory=list)  # Tiered: [[core], [cli, web]]

    # Human-readable
    recommendation: str = ""
    estimated_effort: str = ""


# ── Version resolver ─────────────────────────────────────────────


class VersionResolver:
    """Compute version constraints for a module."""

    def __init__(
        self,
        detection_engine: DetectionEngine,
        registry: FeatureRegistry,
        backend: LanguageBackend,
    ):
        self._detection = detection_engine
        self._registry = registry
        self._backend = backend

    def compute_code_floor(
        self,
        module_dir: Path,
        language: str,
        project_root: Path,
    ) -> CodeFloor:
        """Compute the minimum version required by the module's own code.

        Scans all source files, finds the highest feature version used.
        """
        # Get ALL entries for this language (not filtered by target)
        all_entries = self._registry.by_language(language)
        if not all_entries:
            return CodeFloor(version="", determining_features=[], total_features_above=0,
                             fixable_count=0, manual_count=0)

        # Find the lowest version to use as a baseline scan target
        # We want to detect ALL features, so target the lowest possible version
        versions = [e.introduced for e in all_entries]
        parsed = [(parse_version(language, v), v) for v in versions]
        valid = [(p, v) for p, v in parsed if p is not None]
        if not valid:
            return CodeFloor(version="", determining_features=[], total_features_above=0,
                             fixable_count=0, manual_count=0)

        lowest = min(valid, key=lambda x: x[0])[1]

        # Scan with the lowest version as target → detects everything above it
        result = self._detection.analyze_module(
            module_dir=module_dir,
            target_version=lowest,
            direction="downgrade",
            project_root=project_root,
        )

        if not result.findings:
            return CodeFloor(version=lowest, determining_features=[], total_features_above=0,
                             fixable_count=0, manual_count=0)

        # Group by feature, find highest version
        by_feature: dict[str, list] = {}
        for f in result.findings:
            by_feature.setdefault(f.feature_id, []).append(f)

        feature_usages = []
        highest_version = lowest
        fixable = 0
        manual = 0

        for feature_id, findings in by_feature.items():
            entry = self._registry.get(feature_id)
            if not entry:
                continue

            usage = FeatureUsage(
                feature_id=feature_id,
                feature_name=entry.feature_name,
                version=entry.introduced,
                occurrence_count=len(findings),
                files=sorted(set(f.file for f in findings)),
                fix_available=entry.fix.strategy.value != "manual",
                fix_strategy=entry.fix.strategy.value,
            )
            feature_usages.append(usage)

            if version_above(language, entry.introduced, highest_version):
                highest_version = entry.introduced

            if usage.fix_available:
                fixable += len(findings)
            else:
                manual += len(findings)

        # Sort by version (highest first)
        feature_usages.sort(
            key=lambda u: parse_version(language, u.version) or (0,),
            reverse=True,
        )

        return CodeFloor(
            version=highest_version,
            determining_features=feature_usages,
            total_features_above=len(result.findings),
            fixable_count=fixable,
            manual_count=manual,
        )

    def compute_dependency_floor(
        self,
        module_dir: Path,
        language: str,
        target_version: str,
    ) -> DependencyFloor:
        """Compute the minimum version required by dependencies.

        Queries package registries for requires-python (or equivalent)
        of each dependency. Returns the highest minimum version.
        """
        from .dep_analyzer import DependencyAnalyzer

        analyzer = DependencyAnalyzer()
        dep_result = analyzer.analyze(module_dir, language, target_version)

        return DependencyFloor(
            version=dep_result.dependency_floor or target_version,
            determining_packages=[
                {
                    "package": p.package,
                    "version": p.installed_version,
                    "requires_python": p.requires_python,
                    "min_version": p.min_version,
                    "compatible": p.compatible,
                }
                for p in dep_result.packages
                if not p.unknown
            ],
            all_compatible=dep_result.all_compatible,
            incompatible_packages=[
                {
                    "package": p.package,
                    "version": p.installed_version,
                    "requires_python": p.requires_python,
                    "note": p.note,
                }
                for p in dep_result.incompatible_packages
            ],
        )

    def compute_effective_floor(
        self,
        module_dir: Path,
        language: str,
        target_version: str,
        project_root: Path,
    ) -> EffectiveFloor:
        """Compute the actual minimum version = max(code, dep)."""
        code = self.compute_code_floor(module_dir, language, project_root)
        dep = self.compute_dependency_floor(module_dir, language, target_version)

        code_v = parse_version(language, code.version)
        dep_v = parse_version(language, dep.version)

        if code_v and dep_v:
            if code_v >= dep_v:
                return EffectiveFloor(
                    version=code.version,
                    code_floor=code,
                    dependency_floor=dep,
                    determined_by="code",
                )
            else:
                return EffectiveFloor(
                    version=dep.version,
                    code_floor=code,
                    dependency_floor=dep,
                    determined_by="dependency",
                )

        return EffectiveFloor(
            version=code.version or dep.version,
            code_floor=code,
            dependency_floor=dep,
            determined_by="code" if code.version else "dependency",
        )

    def assess_target(
        self,
        module_name: str,
        module_dir: Path,
        target_version: str,
        language: str,
        project_root: Path,
        direction: str = "downgrade",
        module_configs: list[dict] | None = None,
    ) -> TargetAssessment:
        """Full assessment: is the target achievable? What needs to change?

        This is shown to the user BEFORE they create a version plan.
        """
        # Compute effective floor
        effective = self.compute_effective_floor(
            module_dir, language, target_version, project_root,
        )

        # Run transitive analysis
        analysis = self._detection.analyze_transitive(
            module_dir=module_dir,
            module_name=module_name,
            target_version=target_version,
            project_root=project_root,
            module_configs=module_configs,
            direction=direction,
        )

        # Classify findings
        direct = analysis.direct_findings
        transitive = analysis.transitive_findings
        fixable_direct = [f for f in direct if f.fix_available]
        manual_direct = [f for f in direct if not f.fix_available]

        # Identify blocking modules
        blocking: set[str] = set()
        for f in transitive:
            if f.source_module and f.source_module != module_name:
                blocking.add(f.source_module)

        # Determine achievability
        target_v = parse_version(language, target_version)
        floor_v = parse_version(language, effective.version)
        achievable = True
        gap = None

        if target_v and floor_v and floor_v > target_v:
            # Floor is above target — need fixes
            gap = f"{effective.version} → {target_version}"
            # Still achievable if all code issues are fixable
            # (dep issues would need dep changes)
            if effective.code_floor.manual_count > 0:
                achievable = True  # Still achievable, just needs manual work
            if not effective.dependency_floor.all_compatible:
                achievable = True  # Achievable with dep changes

        # Compute fix order based on module dependencies
        fix_order = self._compute_fix_order(
            module_name, blocking, module_configs or [],
        )

        # Build recommendation
        parts = []
        if blocking:
            parts.append(f"Fix module(s) {', '.join(sorted(blocking))} first")
        if len(fixable_direct) > 0:
            parts.append(f"{len(fixable_direct)} auto-fixable finding(s) in {module_name}")
        if len(manual_direct) > 0:
            parts.append(f"{len(manual_direct)} manual fix(es) needed in {module_name}")
        if not direct and not transitive:
            parts.append("No incompatibilities found — target already met")

        recommendation = ". ".join(parts) if parts else "No action needed"

        # Estimate effort
        auto_time = len(fixable_direct) * 5  # ~5 seconds per auto-fix
        manual_time = len(manual_direct) * 600  # ~10 minutes per manual fix
        total_seconds = auto_time + manual_time
        if total_seconds < 60:
            effort = f"~{total_seconds} seconds"
        elif total_seconds < 3600:
            effort = f"~{total_seconds // 60} minutes"
        else:
            effort = f"~{total_seconds // 3600} hours"

        return TargetAssessment(
            target=target_version,
            achievable=achievable,
            current_floor=effective.version,
            gap=gap,
            code_fixes_needed=len(direct),
            code_fixes_auto=len(fixable_direct),
            code_fixes_manual=len(manual_direct),
            dep_changes_needed=len(effective.dependency_floor.incompatible_packages),
            transitive_fixes_needed=len(transitive),
            blocking_modules=sorted(blocking),
            fix_order=fix_order,
            recommendation=recommendation,
            estimated_effort=effort,
        )

    def _compute_fix_order(
        self,
        target_module: str,
        blocking_modules: set[str],
        module_configs: list[dict],
    ) -> list[list[str]]:
        """Compute tiered fix order.

        Tier 0: blocking modules (fix first)
        Tier 1: the target module (fix after blockers)
        """
        if not blocking_modules:
            return [[target_module]]

        return [sorted(blocking_modules), [target_module]]
