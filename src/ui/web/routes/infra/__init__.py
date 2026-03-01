"""
Infra routes — environment and IaC endpoints.

Blueprint: infra_bp
Prefix: /api

Sub-modules:
    env.py — .env file management (status, vars, diff, validate, generate)
    iac.py — IaC detection and card status
"""

from __future__ import annotations

from flask import Blueprint

infra_bp = Blueprint("infra", __name__)

from . import env, iac  # noqa: E402, F401
