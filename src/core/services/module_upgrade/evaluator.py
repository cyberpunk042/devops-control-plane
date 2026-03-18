"""
Condition evaluator — evaluates structured JSON rules against an UpgradeContext.

Conditions are dicts where all keys are AND'd together. Each key is an
operator name, the value is the operand. Example:

    {"has_file": "pyproject.toml", "target_gte": "3.10"}

This evaluates to True only if the module dir contains pyproject.toml
AND the target version is >= 3.10.

To express OR, duplicate the step in the recipe with different conditions
(same pattern as tool_install recipes with multiple methods).

Operator reference:
    always          — unconditional (value: true)
    has_file        — file exists in module directory (value: filename)
    not_has_file    — file does NOT exist in module dir (value: filename)
    not_has_files   — ALL listed files must be absent (value: list of filenames)
    floor_source_in — floor source is one of these (value: list of strings)
    floor_source_is — floor source matches exactly (value: string)
    has_deps_floor  — module has a dependency floor (value: true/false)
    has_code_floor  — module has a code floor (value: true/false)
    has_future_import — module uses __future__ annotations (value: true/false)
    strategy_is     — version strategy matches (value: string)
    verdict_is      — consistency verdict matches (value: string)
    target_gte      — target version >= value (value: version string)
    target_lt       — target version < value (value: version string)
    current_gte     — current floor >= value (value: version string)
    current_lt      — current floor < value (value: version string)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import UpgradeContext

logger = logging.getLogger(__name__)


def evaluate_condition(condition: dict, ctx: UpgradeContext) -> bool:
    """Evaluate a structured condition dict against an UpgradeContext.

    All keys in the condition dict are AND'd together.
    Returns True if ALL conditions pass, False if any fail.

    Unknown operators are skipped (forward compatibility — new operators
    added in future recipes won't break older evaluator code).
    """
    if not condition:
        return True  # empty condition = always true

    for key, value in condition.items():

        if key == "always":
            # Always true — skip (the step is unconditional)
            continue

        elif key == "has_file":
            path = ctx.project_root / ctx.module_path / value
            if not path.exists():
                return False

        elif key == "not_has_file":
            path = ctx.project_root / ctx.module_path / value
            if path.exists():
                return False

        elif key == "not_has_files":
            # List variant: ALL listed files must be absent
            for filename in value:
                path = ctx.project_root / ctx.module_path / filename
                if path.exists():
                    return False

        elif key == "floor_source_in":
            if ctx.floor_source not in value:
                return False

        elif key == "floor_source_is":
            if ctx.floor_source != value:
                return False

        elif key == "has_deps_floor":
            has = ctx.deps_floor is not None and ctx.deps_floor != ""
            if has != value:
                return False

        elif key == "has_code_floor":
            has = ctx.code_floor is not None and ctx.code_floor != ""
            if has != value:
                return False

        elif key == "has_future_import":
            if ctx.has_future_import != value:
                return False

        elif key == "strategy_is":
            if ctx.strategy != value:
                return False

        elif key == "verdict_is":
            if ctx.verdict != value:
                return False

        elif key == "target_gte":
            if not _ver_gte(ctx.target_floor, value):
                return False

        elif key == "target_lt":
            if _ver_gte(ctx.target_floor, value):
                return False

        elif key == "current_gte":
            if not _ver_gte(ctx.current_floor, value):
                return False

        elif key == "current_lt":
            if _ver_gte(ctx.current_floor, value):
                return False

        else:
            # Unknown operator — skip for forward compatibility
            logger.debug("Unknown condition operator: %s", key)

    return True


def _ver_gte(a: str, b: str) -> bool:
    """Check if version a >= version b.

    Parses dot-separated version strings into integer tuples
    for comparison. Returns False if either version cannot be parsed.
    """
    if not a or not b:
        return False

    try:
        a_parts = [int(x) for x in a.split(".")]
        b_parts = [int(x) for x in b.split(".")]
    except ValueError:
        return False

    return a_parts >= b_parts
