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

from flask import Blueprint, current_app, jsonify, request

from src.core.services.devops_cache import get_cached
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
    root = _root()
    force = request.args.get("bust", "") == "1"

    def _compute() -> dict:
        statuses = run_all_probes(root)
        return {
            "integrations": statuses,
            "suggested_next": suggest_next(statuses),
            "progress": compute_progress(statuses),
        }

    return jsonify(get_cached(root, "project-status", _compute, force=force))


@project_bp.route("/project/next")
def project_next():  # type: ignore[no-untyped-def]
    """Suggest just the next integration to configure."""
    root = _root()
    force = request.args.get("bust", "") == "1"

    def _compute() -> dict:
        statuses = run_all_probes(root)
        next_key = suggest_next(statuses)
        return {
            "suggested_next": next_key,
            "status": statuses.get(next_key) if next_key else None,
            "progress": compute_progress(statuses),
        }

    return jsonify(get_cached(root, "project-status", _compute, force=force))

