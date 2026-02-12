"""
Kubernetes routes — manifest status, validation, cluster probing.

Blueprint: k8s_bp
Prefix: /api

Endpoints:
    GET  /k8s/status              — manifest detection
    GET  /k8s/validate            — manifest validation
    GET  /k8s/cluster             — cluster connection status
    GET  /k8s/resources           — list resources
    POST /k8s/generate/manifests  — generate K8s manifests
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import k8s_ops

k8s_bp = Blueprint("k8s", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


@k8s_bp.route("/k8s/status")
def k8s_status():  # type: ignore[no-untyped-def]
    """Manifest detection and kubectl availability."""
    from src.core.services.devops_cache import get_cached

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


@k8s_bp.route("/k8s/cluster")
def k8s_cluster():  # type: ignore[no-untyped-def]
    """Cluster connection status."""
    return jsonify(k8s_ops.cluster_status())


@k8s_bp.route("/k8s/resources")
def k8s_resources():  # type: ignore[no-untyped-def]
    """List cluster resources."""
    ns = request.args.get("namespace", "default")
    kind = request.args.get("kind", "pods")
    return jsonify(k8s_ops.get_resources(namespace=ns, kind=kind))


@k8s_bp.route("/k8s/generate/manifests", methods=["POST"])
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
