"""
API routes — project status, detection, automation, health, audit, stacks.

Blueprint: api_bp
Prefix: /api

Sub-modules:
    status.py — status, detect, run, health, capabilities
    audit.py  — audit log and activity
    stacks.py — stack definitions
"""

from __future__ import annotations

from flask import Blueprint

api_bp = Blueprint("api", __name__)

from . import status, audit, stacks  # noqa: E402, F401
