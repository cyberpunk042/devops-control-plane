"""
Metrics & health routes — project health score endpoints.

Blueprint: metrics_bp
Prefix: /api

Thin HTTP wrappers over ``src.core.services.metrics_ops``.

Endpoints:
    GET /metrics/health   — full health probe with score
    GET /metrics/summary  — quick project summary
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify

from src.core.services import metrics_ops

metrics_bp = Blueprint("metrics", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


@metrics_bp.route("/metrics/health")
def project_health():  # type: ignore[no-untyped-def]
    """Full health probe with unified score."""
    return jsonify(metrics_ops.project_health(_project_root()))


@metrics_bp.route("/metrics/summary")
def project_summary():  # type: ignore[no-untyped-def]
    """Quick project summary."""
    return jsonify(metrics_ops.project_summary(_project_root()))
