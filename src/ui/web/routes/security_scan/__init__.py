"""
Security scan routes — secret scanning, sensitive files, posture.

Blueprint: security_bp2
Prefix: /api

Sub-modules:
    detect.py  — scan, sensitive files, gitignore, posture
    actions.py — generate gitignore
"""

from __future__ import annotations

from flask import Blueprint

security_bp2 = Blueprint("security2", __name__)

from . import detect, actions  # noqa: E402, F401
