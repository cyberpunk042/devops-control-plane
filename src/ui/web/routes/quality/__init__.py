"""
Code quality routes — lint, typecheck, test, format.

Blueprint: quality_bp
Prefix: /api

Sub-modules:
    status.py  — detected quality tools
    actions.py — run checks, lint, typecheck, test, format, generate config
"""

from __future__ import annotations

from flask import Blueprint

quality_bp = Blueprint("quality", __name__)

from . import status, actions  # noqa: E402, F401
