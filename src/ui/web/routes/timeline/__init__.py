"""
Timeline API routes.

Blueprint: timeline_bp
Prefix: /api

Endpoints:
    GET /api/timeline           — paginated timeline query
    GET /api/timeline/chains    — chain summaries for left navigator
    GET /api/timeline/domains   — per-source entry counts for left navigator
    GET /api/timeline/stats     — aggregate counts
"""

from __future__ import annotations

from flask import Blueprint

timeline_bp = Blueprint("timeline", __name__, url_prefix="/api")

from . import routes  # noqa: E402, F401 — registers routes
