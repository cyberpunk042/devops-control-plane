"""
CI/CD routes — workflow analysis and generation.

Blueprint: ci_bp
Prefix: /api

Sub-modules:
    status.py   — detected CI providers, workflows, coverage
    generate.py — generate CI and lint workflows
"""

from __future__ import annotations

from flask import Blueprint

ci_bp = Blueprint("ci", __name__)

from . import status, generate  # noqa: E402, F401
