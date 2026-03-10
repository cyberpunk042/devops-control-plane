"""
Execution Plans API routes — plan CRUD + execution control.

Blueprint: ``plans_bp``, registered at ``/api`` prefix.

Sub-modules:
    crud.py        — Plan CRUD endpoints (list, get, create, update, delete)
    execution.py   — Execution control (run, cancel, resume, skip, status, results)
"""

from __future__ import annotations

from flask import Blueprint

plans_bp = Blueprint("plans", __name__)

# Import sub-modules so their routes register on the blueprint.
from src.ui.web.routes.plans import crud as _crud  # noqa: F401, E402
from src.ui.web.routes.plans import execution as _execution  # noqa: F401, E402
