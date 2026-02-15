"""
Project Status API — unified integration status for the connected journey.

Blueprint: project_bp
Prefix: /api

Thin HTTP wrappers over ``src.core.services.project_probes``.

Endpoints:
    GET  /project/status  — complete integration state
    GET  /project/next    — suggested next integration to configure
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify

from src.core.services.project_probes import (
    compute_progress,
    run_all_probes,
    suggest_next,
)

project_bp = Blueprint("project", __name__)


def _root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


@project_bp.route("/project/status")
def project_status():  # type: ignore[no-untyped-def]
    """Complete integration status for all cards."""
    statuses = run_all_probes(_root())

    return jsonify({
        "integrations": statuses,
        "suggested_next": suggest_next(statuses),
        "progress": compute_progress(statuses),
    })


@project_bp.route("/project/next")
def project_next():  # type: ignore[no-untyped-def]
    """Suggest just the next integration to configure."""
    statuses = run_all_probes(_root())

    next_key = suggest_next(statuses)
    return jsonify({
        "suggested_next": next_key,
        "status": statuses.get(next_key) if next_key else None,
        "progress": compute_progress(statuses),
    })
