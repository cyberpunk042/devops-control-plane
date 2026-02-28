"""Backward-compat shim — real implementation in ci/ops.py."""
from src.core.services.ci.ops import (  # noqa: F401
    ci_status,
    ci_workflows,
    ci_coverage,
    generate_ci_workflow,
    generate_lint_workflow,
    generate_terraform_workflow,
)
