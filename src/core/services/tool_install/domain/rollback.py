"""
L1 Domain — Rollback plan generation (pure).

Derives rollback steps from completed steps.
No I/O, no subprocess.
"""

from __future__ import annotations


def _generate_rollback(completed_steps: list[dict]) -> list[dict]:
    """Generate a rollback plan from completed steps (reverse order).

    For each completed step that has a ``rollback`` field, the
    rollback instruction is added to the list. Steps without
    rollback data are skipped.

    Args:
        completed_steps: List of step dicts that completed successfully.

    Returns:
        Ordered list of rollback step dicts (reverse of execution order).
    """
    rollback: list[dict] = []
    for step in reversed(completed_steps):
        rb = step.get("rollback")
        if rb:
            rollback.append(rb)
    return rollback
