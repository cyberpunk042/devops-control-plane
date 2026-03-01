"""K8s cluster queries — resources, namespaces, events, describe, logs, storage."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import k8s_ops
from src.ui.web.helpers import project_root as _project_root

from . import k8s_bp


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


@k8s_bp.route("/k8s/env-namespaces")
def k8s_env_namespaces():  # type: ignore[no-untyped-def]
    """Map project environments to K8s namespaces."""
    result = k8s_ops.k8s_env_namespaces(_project_root())
    return jsonify(result)
