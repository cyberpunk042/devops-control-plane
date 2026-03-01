"""K8s Helm endpoints — list, values, install, upgrade, template."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import k8s_ops
from src.core.services.run_tracker import run_tracked
from src.ui.web.helpers import project_root as _project_root

from . import k8s_bp


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
@run_tracked("install", "install:helm")
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
@run_tracked("deploy", "deploy:helm_upgrade")
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
@run_tracked("plan", "plan:helm_template")
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
