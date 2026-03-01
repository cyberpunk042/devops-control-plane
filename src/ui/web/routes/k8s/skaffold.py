"""K8s Skaffold detection endpoint."""

from __future__ import annotations

from flask import jsonify

from src.core.services import k8s_ops
from src.ui.web.helpers import project_root as _project_root

from . import k8s_bp


@k8s_bp.route("/k8s/skaffold/status")
def skaffold_status():  # type: ignore[no-untyped-def]
    """Detect Skaffold configuration."""
    result = k8s_ops.skaffold_status(_project_root())
    return jsonify(result)
