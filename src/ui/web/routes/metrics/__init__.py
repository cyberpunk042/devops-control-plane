"""
Metrics routes — project health score endpoints.

Blueprint: metrics_bp
Prefix: /api

Sub-modules:
    health.py  — full health probe scoring
    summary.py — quick project summary
"""

from __future__ import annotations

from flask import Blueprint

metrics_bp = Blueprint("metrics", __name__)

from . import health, summary  # noqa: E402, F401
