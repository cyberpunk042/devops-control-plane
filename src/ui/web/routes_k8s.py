"""
Kubernetes routes — manifest status, validation, cluster probing.

Blueprint: k8s_bp
Prefix: /api

Endpoints:
    GET  /k8s/status              — manifest detection
    GET  /k8s/validate            — manifest validation
    GET  /k8s/cluster             — cluster connection status
    GET  /k8s/resources           — list resources
    GET  /k8s/storageclasses      — list cluster StorageClasses
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


# ── Act: Cluster operations ─────────────────────────────────────────


@k8s_bp.route("/k8s/pod-logs")
def k8s_pod_logs():  # type: ignore[no-untyped-def]
    """Get logs from a pod."""
    pod = request.args.get("pod", "")
    ns = request.args.get("namespace", "default")
    tail = request.args.get("tail", 100, type=int)
    container = request.args.get("container", "")
    if not pod:
        return jsonify({"error": "Missing 'pod' parameter"}), 400
    result = k8s_ops.k8s_pod_logs(namespace=ns, pod=pod, tail=tail, container=container)
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)


@k8s_bp.route("/k8s/apply", methods=["POST"])
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


@k8s_bp.route("/k8s/events")
def k8s_events():  # type: ignore[no-untyped-def]
    """Get recent cluster events."""
    ns = request.args.get("namespace", "default")
    result = k8s_ops.k8s_events(namespace=ns)
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)


@k8s_bp.route("/k8s/describe")
def k8s_describe():  # type: ignore[no-untyped-def]
    """Describe a Kubernetes resource."""
    kind = request.args.get("kind", "")
    name = request.args.get("name", "")
    ns = request.args.get("namespace", "default")
    if not kind or not name:
        return jsonify({"error": "Missing 'kind' or 'name'"}), 400
    result = k8s_ops.k8s_describe(kind, name, namespace=ns)
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)


@k8s_bp.route("/k8s/namespaces")
def k8s_namespaces():  # type: ignore[no-untyped-def]
    """List Kubernetes namespaces."""
    result = k8s_ops.k8s_namespaces()
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)


@k8s_bp.route("/k8s/storageclasses")
def k8s_storage_classes():  # type: ignore[no-untyped-def]
    """List available StorageClasses from the cluster."""
    result = k8s_ops.k8s_storage_classes()
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)


# ── Helm ────────────────────────────────────────────────────────────


@k8s_bp.route("/k8s/helm/list")
def helm_list():  # type: ignore[no-untyped-def]
    """List installed Helm releases."""
    ns = request.args.get("namespace", "")
    result = k8s_ops.helm_list(_project_root(), namespace=ns)
    return jsonify(result)


@k8s_bp.route("/k8s/helm/values")
def helm_values():  # type: ignore[no-untyped-def]
    """Get values for a Helm release."""
    release = request.args.get("release", "")
    ns = request.args.get("namespace", "")
    if not release:
        return jsonify({"error": "Missing 'release' parameter"}), 400
    result = k8s_ops.helm_values(_project_root(), release, namespace=ns)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@k8s_bp.route("/k8s/helm/install", methods=["POST"])
def helm_install():  # type: ignore[no-untyped-def]
    """Install a Helm chart."""
    data = request.get_json(silent=True) or {}
    release = data.get("release", "")
    chart = data.get("chart", "")
    if not release or not chart:
        return jsonify({"error": "Missing 'release' or 'chart'"}), 400
    result = k8s_ops.helm_install(
        _project_root(),
        release,
        chart,
        namespace=data.get("namespace", ""),
        values_file=data.get("values_file", ""),
        set_values=data.get("set_values"),
        dry_run=data.get("dry_run", False),
    )
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@k8s_bp.route("/k8s/helm/upgrade", methods=["POST"])
def helm_upgrade():  # type: ignore[no-untyped-def]
    """Upgrade a Helm release."""
    data = request.get_json(silent=True) or {}
    release = data.get("release", "")
    chart = data.get("chart", "")
    if not release or not chart:
        return jsonify({"error": "Missing 'release' or 'chart'"}), 400
    result = k8s_ops.helm_upgrade(
        _project_root(),
        release,
        chart,
        namespace=data.get("namespace", ""),
        values_file=data.get("values_file", ""),
        set_values=data.get("set_values"),
        dry_run=data.get("dry_run", False),
    )
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@k8s_bp.route("/k8s/helm/template", methods=["POST"])
def helm_template():  # type: ignore[no-untyped-def]
    """Render Helm templates locally."""
    data = request.get_json(silent=True) or {}
    release = data.get("release", "")
    chart = data.get("chart", "")
    if not release or not chart:
        return jsonify({"error": "Missing 'release' or 'chart'"}), 400
    result = k8s_ops.helm_template(
        _project_root(),
        release,
        chart,
        namespace=data.get("namespace", ""),
        values_file=data.get("values_file", ""),
    )
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ── Skaffold ────────────────────────────────────────────────────────


@k8s_bp.route("/k8s/skaffold/status")
def skaffold_status():  # type: ignore[no-untyped-def]
    """Detect Skaffold configuration."""
    result = k8s_ops.skaffold_status(_project_root())
    return jsonify(result)


# ── Multi-Environment ──────────────────────────────────────────────


@k8s_bp.route("/k8s/env-namespaces")
def k8s_env_namespaces():  # type: ignore[no-untyped-def]
    """Map project environments to K8s namespaces."""
    result = k8s_ops.k8s_env_namespaces(_project_root())
    return jsonify(result)


# ── K8s Wizard ─────────────────────────────────────────────────────


@k8s_bp.route("/k8s/generate/wizard", methods=["POST"])
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
