"""K8s manifest generation — basic and wizard-based."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import k8s_ops
from src.core.services.run_tracker import run_tracked
from src.ui.web.helpers import project_root as _project_root

from . import k8s_bp


@k8s_bp.route("/k8s/generate/manifests", methods=["POST"])
@run_tracked("generate", "generate:k8s_manifests")
def k8s_generate_manifests():  # type: ignore[no-untyped-def]
    """Generate K8s manifests."""
    data = request.get_json(silent=True) or {}
    app_name = data.get("name", "")
    if not app_name:
        return jsonify({"error": "Missing 'name' field"}), 400

    result = k8s_ops.generate_manifests(
        _project_root(),
        app_name,
        image=data.get("image", ""),
        port=data.get("port", 8080),
        replicas=data.get("replicas", 2),
        service_type=data.get("service_type", "ClusterIP"),
        host=data.get("host", ""),
        namespace=data.get("namespace", ""),
    )
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@k8s_bp.route("/k8s/generate/wizard", methods=["POST"])
@run_tracked("generate", "generate:k8s_wizard")
def k8s_generate_wizard():  # type: ignore[no-untyped-def]
    """Generate K8s manifests from wizard resource definitions."""
    data = request.get_json(silent=True) or {}
    resources = data.get("resources", [])
    if not resources:
        return jsonify({"error": "At least one resource is required"}), 400
    result = k8s_ops.generate_k8s_wizard(_project_root(), resources)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)
