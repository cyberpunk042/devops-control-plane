"""
L1 Domain — Version constraint validation (pure).

Validates selected versions against semver-style constraints.
No I/O, no subprocess.
"""

from __future__ import annotations


def check_version_constraint(
    selected_version: str,
    constraint: dict,
) -> dict:
    """Validate a selected version against a constraint rule.

    Constraint types:
        - ``minor_range``: ±N minor versions (e.g. kubectl ±1 of cluster)
        - ``gte``: >= a minimum version
        - ``exact``: must match exactly
        - ``semver_compat``: ~= compatibility (same major, >= minor)

    Args:
        selected_version: The version string chosen, e.g. ``"1.29.3"``.
        constraint: Dict with ``type``, ``reference``, and type-specific fields.
            Examples::

                {"type": "minor_range", "reference": "1.30.0", "range": 1}
                {"type": "gte", "reference": "2.0.0"}
                {"type": "exact", "reference": "3.1.4"}

    Returns:
        ``{"valid": True}`` or ``{"valid": False, "message": "...", "warning": "..."}``
    """
    def _parse_semver(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in v.lstrip("v").split(".")[:3])

    ctype = constraint.get("type", "gte")
    ref = constraint.get("reference", "")

    try:
        sel_parts = _parse_semver(selected_version)
        ref_parts = _parse_semver(ref)
    except (ValueError, IndexError):
        return {"valid": True, "parse_error": True}

    if ctype == "minor_range":
        rng = constraint.get("range", 1)
        # Compare major must match, minor within ±range
        if sel_parts[0] != ref_parts[0]:
            return {
                "valid": False,
                "message": (
                    f"Major version mismatch: {selected_version} vs {ref}. "
                    f"Must be same major version."
                ),
            }
        minor_diff = abs(sel_parts[1] - ref_parts[1])
        if minor_diff > rng:
            return {
                "valid": False,
                "message": (
                    f"Version {selected_version} is {minor_diff} minor versions "
                    f"away from {ref}. Maximum allowed: ±{rng}."
                ),
                "warning": (
                    f"kubectl should be within ±{rng} minor versions of the "
                    f"cluster version ({ref})."
                ),
            }
        return {"valid": True}

    elif ctype == "gte":
        if sel_parts >= ref_parts:
            return {"valid": True}
        return {
            "valid": False,
            "message": f"Version {selected_version} < {ref}. Minimum required: {ref}.",
        }

    elif ctype == "exact":
        if sel_parts == ref_parts:
            return {"valid": True}
        return {
            "valid": False,
            "message": f"Version {selected_version} != {ref}. Exact match required.",
        }

    elif ctype == "semver_compat":
        # ~=: same major, selected minor >= reference minor
        if sel_parts[0] != ref_parts[0]:
            return {
                "valid": False,
                "message": f"Major version mismatch: {selected_version} vs {ref}.",
            }
        if sel_parts[1:] >= ref_parts[1:]:
            return {"valid": True}
        return {
            "valid": False,
            "message": f"Version {selected_version} not compatible with ~={ref}.",
        }

    return {"valid": True}
