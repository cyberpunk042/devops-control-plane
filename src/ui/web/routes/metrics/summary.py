"""Metrics summary — quick project summary endpoint."""

from __future__ import annotations

from flask import jsonify

from src.core.services.metrics import ops as metrics_ops
from src.ui.web.helpers import project_root as _project_root

from . import metrics_bp


@metrics_bp.route("/metrics/summary")
def project_summary():  # type: ignore[no-untyped-def]
    """Quick project summary."""
    return jsonify(metrics_ops.project_summary(_project_root()))
