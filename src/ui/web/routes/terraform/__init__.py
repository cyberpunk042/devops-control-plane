"""
Terraform routes — IaC status, validation, plan, state, generation.

Blueprint: terraform_bp
Prefix: /api

Sub-modules:
    status.py   — read-only queries (status, state, workspaces, output)
    actions.py  — mutations (validate, plan, init, apply, destroy, generate, fmt)
"""

from __future__ import annotations

from flask import Blueprint

terraform_bp = Blueprint("terraform", __name__)

from . import status, actions  # noqa: E402, F401
