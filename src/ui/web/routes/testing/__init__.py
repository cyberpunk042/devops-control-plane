"""
Testing routes — test status, inventory, run, coverage.

Blueprint: testing_bp
Prefix: /api

Sub-modules:
    status.py  — detected frameworks, inventory
    actions.py — run tests, coverage, generate template
"""

from __future__ import annotations

from flask import Blueprint

testing_bp = Blueprint("testing", __name__)

from . import status, actions  # noqa: E402, F401
