"""Packages status — detection, outdated, audit, list."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services.packages_svc import ops as package_ops
from src.ui.web.helpers import project_root as _project_root

from . import packages_bp


@packages_bp.route("/packages/status")
def package_status():  # type: ignore[no-untyped-def]
    """Detected package managers and dependency files."""
    from src.core.services.devops.cache import get_cached

    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "packages",
        lambda: package_ops.package_status_enriched(root),
        force=force,
    ))


@packages_bp.route("/packages/outdated")
def package_outdated():  # type: ignore[no-untyped-def]
    """Check for outdated packages."""
    manager = request.args.get("manager")
    result = package_ops.package_outdated(_project_root(), manager=manager)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@packages_bp.route("/packages/audit")
def package_audit():  # type: ignore[no-untyped-def]
    """Run security audit on dependencies."""
    manager = request.args.get("manager")
    result = package_ops.package_audit(_project_root(), manager=manager)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@packages_bp.route("/packages/list")
def package_list():  # type: ignore[no-untyped-def]
    """List installed packages."""
    manager = request.args.get("manager")
    result = package_ops.package_list(_project_root(), manager=manager)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)
