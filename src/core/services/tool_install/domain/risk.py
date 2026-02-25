"""
L1 Domain — Risk assessment (pure).

Infer, aggregate, and compare risk levels for install plans.
No I/O, no subprocess, no imports beyond stdlib.
"""

from __future__ import annotations


_HIGH_RISK_LABELS = frozenset({
    "kernel", "driver", "grub", "bootloader", "dkms", "vfio",
    "modprobe", "nvidia",
})
"""Label keywords that automatically promote a step to high risk."""

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def _infer_risk(step: dict) -> str:
    """Infer risk level for a plan step from its context.

    Rules (first match wins):
        1. ``restart_required == "system"`` → **high**
        2. Label contains a high-risk keyword → **high**
        3. ``needs_sudo`` is True → **medium**
        4. Otherwise → **low**

    An explicit ``step["risk"]`` always takes precedence—this
    function is only called when ``risk`` is absent.

    Returns:
        ``"low"`` | ``"medium"`` | ``"high"``
    """
    # Explicit risk always wins.
    explicit = step.get("risk")
    if explicit in ("low", "medium", "high"):
        return explicit

    if step.get("restart_required") == "system":
        return "high"

    label = step.get("label", "").lower()
    if any(kw in label for kw in _HIGH_RISK_LABELS):
        return "high"

    if step.get("needs_sudo"):
        return "medium"

    return "low"


def _plan_risk(steps: list[dict]) -> dict:
    """Compute aggregate risk metadata for a plan.

    Returns a summary dict suitable for inclusion in the plan
    response so the frontend can display risk indicators and
    gate confirmations.

    Returns::

        {
            "level": "medium",          # highest step risk
            "counts": {"low": 3, "medium": 2, "high": 0},
            "has_high": False,
        }
    """
    counts: dict[str, int] = {"low": 0, "medium": 0, "high": 0}
    for step in steps:
        risk = step.get("risk", "low")
        counts[risk] = counts.get(risk, 0) + 1

    if counts["high"]:
        level = "high"
    elif counts["medium"]:
        level = "medium"
    else:
        level = "low"

    return {
        "level": level,
        "counts": counts,
        "has_high": counts["high"] > 0,
        "has_medium": counts["medium"] > 0,
    }


def _check_risk_escalation(
    recipe: dict,
    resolved_risk: dict,
) -> dict | None:
    """Check if user choices escalated the risk beyond recipe default.

    Compares the recipe's base ``risk`` field with the resolved plan's
    aggregate risk.  If the resolved risk is higher, returns escalation
    details for the frontend confirmation gate.

    Args:
        recipe: TOOL_RECIPES entry.
        resolved_risk: Output of ``_plan_risk()``.

    Returns:
        Escalation dict ``{"from": "low", "to": "high", "reason": "..."}``
        or ``None`` if no escalation.
    """
    base_risk = recipe.get("risk", "low")
    resolved_level = resolved_risk.get("level", "low")

    if _RISK_ORDER.get(resolved_level, 0) > _RISK_ORDER.get(base_risk, 0):
        return {
            "from": base_risk,
            "to": resolved_level,
            "reason": (
                f"Your choices escalated the risk from {base_risk} to "
                f"{resolved_level}. Please review the plan carefully."
            ),
        }
    return None
