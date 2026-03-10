"""
CDP Test I/O sync — single source of truth for suite-level I/O.

Scans all steps in a suite and rebuilds ``variables`` and ``outputs``
from step-level I/O bindings.  This ensures suite-level declarations
are always consistent with what the steps actually reference.

Called:
    - After any I/O modification via UI
    - When saving a recording as a suite
    - When loading a suite for validation

Used by:
    recording.py   — after I/O configure endpoint modifies a step
    storage.py     — when saving/loading suites
    session.py     — when finalizing a recording session into a suite
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import TestSuite

# Pattern to match ${VAR_NAME} references in step values
_VAR_PATTERN = re.compile(r"^\$\{(\w+)\}$")


def sync_suite_io(suite: TestSuite) -> dict:
    """Rebuild suite.variables and suite.outputs from step data.

    Scans every step in the suite:
    - Steps whose value matches ``${VAR_NAME}`` contribute to ``variables``
      using their ``original_value`` as the default.
    - Steps with ``export_as`` set contribute to ``outputs``.

    Returns a summary dict for API responses::

        {
            "inputs": [{"name": "LOGIN_EMAIL", "default": "admin@test.com", "step_id": "...", "step_sequence": 3}],
            "outputs": [{"name": "AUTH_TOKEN", "step_id": "...", "step_sequence": 7}],
        }
    """
    variables: dict[str, str] = {}
    outputs: dict[str, str] = {}
    inputs_summary: list[dict] = []
    outputs_summary: list[dict] = []

    for step in suite.steps:
        # ── INPUT: detect ${VAR} in step value ────────────────
        m = _VAR_PATTERN.match(step.value)
        if m:
            var_name = m.group(1)
            default_val = step.original_value or ""
            variables[var_name] = default_val
            inputs_summary.append({
                "name": var_name,
                "default": default_val,
                "step_id": step.id,
                "step_sequence": step.sequence,
            })

        # ── OUTPUT: detect export_as on capture steps ─────────
        if step.export_as:
            outputs[step.export_as] = ""
            outputs_summary.append({
                "name": step.export_as,
                "step_id": step.id,
                "step_sequence": step.sequence,
            })

    suite.variables = variables
    suite.outputs = outputs

    return {
        "inputs": inputs_summary,
        "outputs": outputs_summary,
    }
