"""
Terraform — detection, validation, planning, actions, generation.

Sub-modules::

    ops.py       — detect, validate, plan, state, workspaces
    actions.py   — init, apply, destroy, output, workspace select, fmt
    generate.py  — HCL generation (main.tf, variables.tf, outputs.tf)

Public re-exports below keep ``from src.core.services.terraform import X`` working.
"""

from __future__ import annotations

# ── Ops (detect + read-only) ──
from .ops import (  # noqa: F401
    terraform_status,
    terraform_validate,
    terraform_plan,
    terraform_state,
    terraform_workspaces,
)

# ── Actions (mutating) ──
from .actions import (  # noqa: F401
    terraform_init,
    terraform_apply,
    terraform_output,
    terraform_destroy,
    terraform_workspace_select,
    terraform_fmt,
)

# ── Generate ──
from .generate import (  # noqa: F401
    generate_terraform,
    generate_terraform_k8s,
    terraform_to_docker_registry,
)
