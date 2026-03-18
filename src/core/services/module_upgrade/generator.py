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

    for template in step_templates:
        condition = template.get("condition", {})
        if not evaluate_condition(condition, ctx):
            continue

        step = _materialize_step(template, ctx)
        steps.append(step)

        # Track automation_ids for deduplication with common tail
        aid = template.get("automation_id", "")
        if aid:
            seen_automation_ids.add(aid)

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

            # Skip if label already present (for manual steps without automation_id)
            label = _interpolate(template.get("label", ""), ctx)
            if any(s["label"] == label for s in steps):
                continue

            condition = template.get("condition", {})
            if not evaluate_condition(condition, ctx):
                continue

            step = _materialize_step(template, ctx)
            steps.append(step)

    # ── Generate IDs ─────────────────────────────────────────────
    for step in steps:
        automation_id = step.pop("_automation_id", "")
        suffix = uuid.uuid4().hex[:8]
        if automation_id:
            step["id"] = f"{automation_id}:{suffix}"
        else:
            step["id"] = f"manual:{suffix}"

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
