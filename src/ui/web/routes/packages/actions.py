"""Packages actions — install, update."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services.packages_svc import ops as package_ops
from src.core.services.run_tracker import run_tracked
from src.ui.web.helpers import project_root as _project_root

from . import packages_bp


@packages_bp.route("/packages/install", methods=["POST"])
@run_tracked("install", "install:packages")
def package_install():  # type: ignore[no-untyped-def]
    """Install dependencies."""
    data = request.get_json(silent=True) or {}
    manager = data.get("manager")

    result = package_ops.package_install(_project_root(), manager=manager)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@packages_bp.route("/packages/update", methods=["POST"])
@run_tracked("install", "install:packages_update")
def package_update():  # type: ignore[no-untyped-def]
    """Update packages."""
    data = request.get_json(silent=True) or {}
    manager = data.get("manager")
    package = data.get("package")

    result = package_ops.package_update(
        _project_root(),
        package=package,
        manager=manager,
    )

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)
