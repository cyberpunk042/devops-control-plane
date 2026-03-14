"""K8s detection — status and validation endpoints."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import k8s_ops
from src.ui.web.helpers import project_root as _project_root

from . import k8s_bp


@k8s_bp.route("/k8s/status")
def k8s_status():  # type: ignore[no-untyped-def]
    """Manifest detection and kubectl availability."""
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("devops.k8s", force=force)
    return jsonify(result["data"])


@k8s_bp.route("/k8s/validate")
def k8s_validate():  # type: ignore[no-untyped-def]
    """Validate K8s manifests."""
    return jsonify(k8s_ops.validate_manifests(_project_root()))
