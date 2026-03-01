"""K8s detection — status and validation endpoints."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import k8s_ops
from src.ui.web.helpers import project_root as _project_root

from . import k8s_bp


@k8s_bp.route("/k8s/status")
def k8s_status():  # type: ignore[no-untyped-def]
    """Manifest detection and kubectl availability."""
    from src.core.services.devops.cache import get_cached

    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "k8s",
        lambda: k8s_ops.k8s_status(root),
        force=force,
    ))


@k8s_bp.route("/k8s/validate")
def k8s_validate():  # type: ignore[no-untyped-def]
    """Validate K8s manifests."""
    return jsonify(k8s_ops.validate_manifests(_project_root()))
