"""
L0 Data — Remediation handler registries.

Three layers of failure handlers, evaluated bottom-up (most specific first):
  Layer 3: Recipe-declared (on_failure in TOOL_RECIPES) — not here
  Layer 2: Method-family handlers (METHOD_FAMILY_HANDLERS)
  Layer 1: Infrastructure handlers (INFRA_HANDLERS)
  Layer 0: Bootstrap handlers (BOOTSTRAP_HANDLERS)

Each handler detects a failure pattern and offers MULTIPLE remediation
options. Option availability (ready/locked/impossible) is computed at
runtime by domain/remediation_planning.py — not stored here.

See .agent/plans/tool_install/remediation-model.md for full design.
"""

from __future__ import annotations

from .constants import VALID_STRATEGIES, VALID_AVAILABILITY, VALID_CATEGORIES
from .method_families import METHOD_FAMILY_HANDLERS
from .infra import INFRA_HANDLERS
from .bootstrap import BOOTSTRAP_HANDLERS
from .lib_package_map import LIB_TO_PACKAGE_MAP

__all__ = [
    "VALID_STRATEGIES",
    "VALID_AVAILABILITY",
    "VALID_CATEGORIES",
    "METHOD_FAMILY_HANDLERS",
    "INFRA_HANDLERS",
    "BOOTSTRAP_HANDLERS",
    "LIB_TO_PACKAGE_MAP",
]
