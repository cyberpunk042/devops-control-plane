"""
Package management routes — dependency analysis and management.

Blueprint: packages_bp
Prefix: /api

Sub-modules:
    status.py  — detected package managers, outdated, audit, list
    actions.py — install, update
"""

from __future__ import annotations

from flask import Blueprint

packages_bp = Blueprint("packages", __name__)

from . import status, actions  # noqa: E402, F401
