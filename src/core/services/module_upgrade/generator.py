"""
Checklist generator — produces context-aware upgrade/downgrade checklists.

Reads JSON recipe files, evaluates conditions against the module's
UpgradeContext, interpolates labels, generates step IDs, and returns
a list of step dicts ready for ModuleVersionPlanStep creation.

The generator is language-agnostic. Adding a new language means
adding a JSON recipe file — zero code changes here.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from .context import UpgradeContext, build_context
from .evaluator import evaluate_condition

logger = logging.getLogger(__name__)

# Recipe data directory
_RECIPE_DIR = Path(__file__).parent / "data" / "recipes"

# Language name mapping for label interpolation
# Maps detect_language() output → human-readable name
_LANGUAGE_LABELS: dict[str, str] = {
    "python": "Python",
    "javascript": "Node.js",
    "typescript": "Node.js",
    "go": "Go",
    "rust": "Rust",
    "ruby": "Ruby",
    "java": "Java",
    "csharp": "C#",
    "php": "PHP",
    "elixir": "Elixir",
}

# Maps detect_language() output → recipe JSON filename (without extension)
_LANGUAGE_TO_RECIPE: dict[str, str] = {
    "python": "python",
    "javascript": "node",
    "typescript": "node",
    "go": "go",
    "rust": "rust",
    "ruby": "ruby",
    "java": "java",
    "csharp": "dotnet",
    "php": "php",
    "elixir": "elixir",
}


def generate_checklist(
    module_name: str,
    target: str,
    project_root: Path,
) -> list[dict]:
    """Generate a context-aware upgrade/downgrade checklist for a module.

    This is the main entry point. It:
    1. Builds an UpgradeContext from module intelligence
    2. Loads the language-specific recipe JSON
    3. Evaluates conditions to filter applicable steps
    4. Interpolates labels with context values
    5. Appends common tail steps (deduplicated)
    6. Generates step IDs
    7. Returns step dicts for ModuleVersionPlanStep

    Args:
        module_name: Module name (matches project.yml).
        target: Target floor version (e.g. "3.12").
        project_root: Absolute path to project root.

    Returns:
        List of step dicts: [{"id": "...", "label": "...", "description": "..."}]
        Each dict is ready to be saved as a ModuleVersionPlanStep in project.yml.
        Returns a minimal fallback list if the recipe cannot be loaded.
    """
    # ── Build context ────────────────────────────────────────────
    ctx = build_context(module_name, target, project_root)

    if not ctx.language:
        logger.warning(
            "No language detected for module '%s' — using fallback checklist",
            module_name,
        )
        return _fallback_checklist(module_name, target)

    # ── Load recipe ──────────────────────────────────────────────
    recipe = _load_recipe(ctx.language)
    if not recipe:
        logger.warning(
            "No recipe found for language '%s' — using fallback checklist",
            ctx.language,
        )
        return _fallback_checklist(module_name, target)

    # ── Select direction ─────────────────────────────────────────
    direction_key = ctx.direction  # "upgrade" or "downgrade"
    step_templates = recipe.get(direction_key, [])

    if not step_templates:
        logger.warning(
            "No '%s' steps in recipe for '%s' — using fallback",
            direction_key, ctx.language,
        )
        return _fallback_checklist(module_name, target)

    # ── Filter by conditions ─────────────────────────────────────
    steps: list[dict] = []
    seen_automation_ids: set[str] = set()
    seen_categories: set[str] = set()

    for template in step_templates:
        condition = template.get("condition", {})
        if not evaluate_condition(condition, ctx):
            continue

        step = _materialize_step(template, ctx)
        steps.append(step)

        # Track automation_ids and categories for deduplication with common tail
        aid = template.get("automation_id", "")
        if aid:
            seen_automation_ids.add(aid)
        cat = template.get("category", "")
        if cat:
            seen_categories.add(cat)

    # ── Append common tail steps (deduplicated) ──────────────────
    common = _load_common_recipe()
    if common:
        tail_key = f"{direction_key}_tail"
        tail_templates = common.get(tail_key, [])

        for template in tail_templates:
            aid = template.get("automation_id", "")

            # Skip if language recipe already includes this automation
            if aid and aid in seen_automation_ids:
                continue

            # Skip generic fallback steps (no automation_id) if the
            # language recipe already covers this category
            cat = template.get("category", "")
            if not aid and cat and cat in seen_categories:
                continue

            # Skip if label already present (for manual steps without automation_id)
            label = _interpolate(template.get("label", ""), ctx)
            if any(s["label"] == label for s in steps):
                continue

            condition = template.get("condition", {})
            if not evaluate_condition(condition, ctx):
                continue

            step = _materialize_step(template, ctx)
            steps.append(step)

    # ── Enrich with compat v2 analysis (replaces generic scan/fix steps) ──
    steps = _enrich_with_compat_analysis(
        steps, module_name, target, ctx.direction, project_root,
    )

    # ── Generate IDs ─────────────────────────────────────────────
    for step in steps:
        automation_id = step.pop("_automation_id", "")
        compat_state = step.pop("_compat_state", None)
        suffix = uuid.uuid4().hex[:8]
        if automation_id:
            step["id"] = f"{automation_id}:{suffix}"
        else:
            step["id"] = f"manual:{suffix}"
        if compat_state:
            step["state"] = compat_state

    return steps


# ── Compat v2 integration ────────────────────────────────────────


# Steps that are REPLACED by compat-generated steps when analysis is available.
# These are the generic recipe steps that the compat engine does better.
_COMPAT_REPLACED_AUTOMATIONS = {
    "scan_incompatible_features",
    "scan_breaking_changes",
    "add_future_annotations",
    "guide_incompatible_syntax",
    "rescan_module",
}


def _enrich_with_compat_analysis(
    steps: list[dict],
    module_name: str,
    target: str,
    direction: str,
    project_root: Path,
) -> list[dict]:
    """Enrich plan steps with compat v2 analysis results.

    Replaces generic scan/fix/guide steps with analysis-driven steps
    that show exact findings, counts, and fix strategies.

    Falls back to the original recipe steps if compat is not available.
    """
    try:
        from src.core.services.mediator import get_mediator

        m = get_mediator()

        # Get analysis (cached or compute)
        analysis_data = m.get(f"compat.analysis.{module_name}")
        if not analysis_data or not analysis_data.get("data"):
            return steps  # No analysis — keep recipe steps
        analysis = analysis_data["data"]

        if not analysis.findings:
            # No findings — simplify plan: remove fix/guide steps, keep infrastructure
            enriched = []
            for step in steps:
                aid = step.get("_automation_id", "")
                if aid in _COMPAT_REPLACED_AUTOMATIONS:
                    continue  # Skip — no findings means no scan/fix/guide needed
                enriched.append(step)

            # Add a single "Scan — clean" step at the beginning
            enriched.insert(0, {
                "label": f"Scan complete — no incompatibilities for Python {target}",
                "description": "AST analysis found 0 features incompatible with the target version",
                "_automation_id": "scan_incompatible_features",
                "_compat_state": "passed",
            })
            return enriched

        # Separate compat-replaced steps from infrastructure steps
        infra_steps = []
        insert_point = 0
        found_first_compat = False

        for i, step in enumerate(steps):
            aid = step.get("_automation_id", "")
            if aid in _COMPAT_REPLACED_AUTOMATIONS:
                if not found_first_compat:
                    insert_point = len(infra_steps)
                    found_first_compat = True
                # Skip — will be replaced by compat steps
            else:
                infra_steps.append(step)

        # Generate compat-specific steps from analysis
        compat_steps = _generate_compat_steps(analysis, target, direction)

        # Merge: infra steps before insert point + compat steps + infra steps after
        result = infra_steps[:insert_point] + compat_steps + infra_steps[insert_point:]
        return result

    except Exception as exc:
        logger.warning("Compat enrichment failed, using recipe steps: %s", exc)
        return steps


def _generate_compat_steps(analysis, target: str, direction: str) -> list[dict]:
    """Generate plan steps from compat analysis results."""
    steps = []

    # Filter to actionable findings (error/warning, not info/no_fix_needed)
    actionable = [
        f for f in analysis.findings
        if f.severity in ("error", "warning") and f.fix_strategy != "no_fix_needed"
    ]

    direct = [f for f in actionable if not f.is_transitive]
    transitive = [f for f in actionable if f.is_transitive]
    auto_fixable = [f for f in direct if f.fix_available]
    manual = [f for f in direct if not f.fix_available]

    total_files = len(set(f.file for f in actionable))

    # Step: Scan summary
    steps.append({
        "label": f"Scan — {len(actionable)} finding(s) in {total_files} file(s)",
        "description": (
            f"{len(auto_fixable)} auto-fixable, {len(manual)} manual"
            + (f", {len(transitive)} transitive" if transitive else "")
        ),
        "_automation_id": "scan_incompatible_features",
    })

    # Step: Blocked by transitive (if any)
    if transitive:
        blocking_modules = sorted(set(
            f.source_module for f in transitive if f.source_module
        ))
        if blocking_modules:
            steps.append({
                "label": f"Blocked by: {', '.join(blocking_modules)} ({len(transitive)} finding(s))",
                "description": "Fix these modules first to resolve transitive incompatibilities",
                "_automation_id": "blocked",
                "_compat_state": "blocked",
            })

    # Group auto-fixable by fix strategy
    future_fixable = [f for f in auto_fixable if f.fix_strategy == "add_future_import"]
    import_fixable = [f for f in auto_fixable if f.fix_strategy in (
        "replace_import", "replace_import_and_usages", "add_backport_import",
    )]
    other_fixable = [f for f in auto_fixable if f not in future_fixable + import_fixable]

    # Step: Add __future__ annotations
    if future_fixable:
        files = sorted(set(f.file for f in future_fixable))
        steps.append({
            "label": f"Add __future__ annotations ({len(files)} file(s))",
            "description": "Enable PEP 604/585 syntax on older Python via deferred evaluation",
            "_automation_id": "add_future_annotations",
        })

    # Steps: Fix by feature (grouped)
    by_feature: dict[str, list] = {}
    for f in import_fixable + other_fixable:
        by_feature.setdefault(f.feature_name, []).append(f)

    for feature_name, findings in sorted(by_feature.items()):
        files = sorted(set(f.file for f in findings))
        steps.append({
            "label": f"Fix {feature_name} ({len(files)} file(s))",
            "description": f"Auto-fix: {findings[0].fix_strategy}",
            "_automation_id": "fix_compat_auto",
        })

    # Step: Manual fixes
    if manual:
        by_feat_manual: dict[str, list] = {}
        for f in manual:
            by_feat_manual.setdefault(f.feature_name, []).append(f)

        for feature_name, findings in sorted(by_feat_manual.items()):
            steps.append({
                "label": f"Manual fix: {feature_name} ({len(findings)} occurrence(s))",
                "description": "Requires manual rewrite — cannot be auto-fixed",
                "_automation_id": "manual",
            })

    # Step: Guide (only if there are findings)
    if actionable:
        steps.append({
            "label": "Review incompatible syntax guide",
            "description": "Shows rewrite patterns and before/after examples",
            "_automation_id": "guide_incompatible_syntax",
        })

    # Step: Re-scan and verify
    steps.append({
        "label": "Re-scan and verify",
        "description": "Confirm all incompatibilities are resolved",
        "_automation_id": "rescan_module",
    })

    return steps


# ── Internal helpers ─────────────────────────────────────────────


def _load_recipe(language: str) -> dict | None:
    """Load the JSON recipe for a language.

    Returns the parsed dict, or None if the recipe file doesn't exist.
    """
    recipe_name = _LANGUAGE_TO_RECIPE.get(language)
    if not recipe_name:
        return None

    recipe_path = _RECIPE_DIR / f"{recipe_name}.json"
    if not recipe_path.is_file():
        return None

    try:
        with open(recipe_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load recipe '%s': %s", recipe_path, exc)
        return None


def _load_common_recipe() -> dict | None:
    """Load the common recipe JSON (_common.json)."""
    common_path = _RECIPE_DIR / "_common.json"
    if not common_path.is_file():
        return None

    try:
        with open(common_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load common recipe: %s", exc)
        return None


def _materialize_step(template: dict, ctx: UpgradeContext) -> dict:
    """Convert a recipe step template into a concrete step dict.

    Interpolates {target}, {current}, {language} in label and description.
    Carries _automation_id for later ID generation (stripped before return).
    """
    label = _interpolate(template.get("label", ""), ctx)
    description = _interpolate(template.get("description", ""), ctx)

    return {
        "label": label,
        "description": description,
        "_automation_id": template.get("automation_id", ""),
    }


def _interpolate(text: str, ctx: UpgradeContext) -> str:
    """Interpolate placeholders in recipe text.

    Supported placeholders:
      {target}   — target floor version (e.g. "3.12")
      {current}  — current floor version (e.g. "3.8")
      {language} — human-readable language name (e.g. "Python")
    """
    if not text:
        return text

    language_label = _LANGUAGE_LABELS.get(ctx.language, ctx.language)

    try:
        return text.format(
            target=ctx.target_floor,
            current=ctx.current_floor or "?",
            language=language_label,
        )
    except (KeyError, IndexError, ValueError):
        # If interpolation fails, return the raw text
        return text


def _fallback_checklist(module_name: str, target: str) -> list[dict]:
    """Minimal fallback checklist when no recipe is available.

    This ensures plan creation never fails — the user always gets
    some checklist to work with, even if the recipe is missing.
    """
    suffix = uuid.uuid4().hex[:8]
    return [
        {
            "id": f"manual:{uuid.uuid4().hex[:8]}",
            "label": f"Verify dependencies support version {target}",
            "description": "",
        },
        {
            "id": f"manual:{uuid.uuid4().hex[:8]}",
            "label": f"Update version constraint to >={target}",
            "description": "",
        },
        {
            "id": f"manual:{uuid.uuid4().hex[:8]}",
            "label": "Update CI test matrix",
            "description": "",
        },
        {
            "id": f"manual:{uuid.uuid4().hex[:8]}",
            "label": f"Run test suite against {target}",
            "description": "",
        },
        {
            "id": f"manual:{uuid.uuid4().hex[:8]}",
            "label": "Re-scan module and verify new floor",
            "description": "",
        },
    ]
