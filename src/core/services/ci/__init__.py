"""
CI/CD domain — detection, analysis, generation, and composition.

Public API re-exports for backward-compatible ``from src.core.services.ci import X``.
"""

from src.core.services.ci.ops import (
    ci_status,
    ci_workflows,
    ci_coverage,
    generate_ci_workflow,
    generate_lint_workflow,
    generate_terraform_workflow,
)
from src.core.services.ci.compose import compose_ci_workflows

__all__ = [
    # ops — detect / observe / generate
    "ci_status",
    "ci_workflows",
    "ci_coverage",
    "generate_ci_workflow",
    "generate_lint_workflow",
    "generate_terraform_workflow",
    # compose — cross-domain orchestrator
    "compose_ci_workflows",
]
