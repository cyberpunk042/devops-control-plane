"""K8s cluster mutations — apply, delete, scale."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import k8s_ops
from src.core.services.events.tracked import tracked
from src.ui.web.helpers import project_root as _project_root

from . import k8s_bp


@k8s_bp.route("/k8s/apply", methods=["POST"])
@tracked("k8s.applied")
def k8s_apply():  # type: ignore[no-untyped-def]
    """Apply Kubernetes manifests."""
    data = request.get_json(silent=True) or {}
    file_path = data.get("path", "")
    ns = data.get("namespace", "")
    result = k8s_ops.k8s_apply(_project_root(), file_path, namespace=ns)
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)


@k8s_bp.route("/k8s/delete", methods=["POST"])
@tracked("k8s.deleted")
def k8s_delete():  # type: ignore[no-untyped-def]
    """Delete a Kubernetes resource."""
    data = request.get_json(silent=True) or {}
    kind = data.get("kind", "")
    name = data.get("name", "")
    ns = data.get("namespace", "default")
    if not kind or not name:
        return jsonify({"error": "Missing 'kind' or 'name'"}), 400
    result = k8s_ops.k8s_delete_resource(kind, name, namespace=ns)
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)


@k8s_bp.route("/k8s/scale", methods=["POST"])
@tracked("k8s.scaled")
def k8s_scale():  # type: ignore[no-untyped-def]
    """Scale a deployment/statefulset."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    replicas = data.get("replicas", 1)
    ns = data.get("namespace", "default")
    kind = data.get("kind", "deployment")
    if not name:
        return jsonify({"error": "Missing 'name'"}), 400
    result = k8s_ops.k8s_scale(name, replicas, namespace=ns, kind=kind)
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)
