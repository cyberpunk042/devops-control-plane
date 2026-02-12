"""
Package management routes — dependency analysis and management endpoints.

Blueprint: packages_bp
Prefix: /api

Thin HTTP wrappers over ``src.core.services.package_ops``.

Endpoints:
    GET  /packages/status     — detected package managers
    GET  /packages/outdated   — outdated packages
    GET  /packages/audit      — security audit
    GET  /packages/list       — list installed packages
    POST /packages/install    — install dependencies
    POST /packages/update     — update packages
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import package_ops

packages_bp = Blueprint("packages", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


# ── Detect ──────────────────────────────────────────────────────────


@packages_bp.route("/packages/status")
def package_status():  # type: ignore[no-untyped-def]
    """Detected package managers and dependency files."""
    from src.core.services.devops_cache import get_cached

    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "packages",
        lambda: package_ops.package_status(root),
        force=force,
    ))


# ── Observe ─────────────────────────────────────────────────────────


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


# ── Act ─────────────────────────────────────────────────────────────


@packages_bp.route("/packages/install", methods=["POST"])
def package_install():  # type: ignore[no-untyped-def]
    """Install dependencies."""
    data = request.get_json(silent=True) or {}
    manager = data.get("manager")

    result = package_ops.package_install(_project_root(), manager=manager)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@packages_bp.route("/packages/update", methods=["POST"])
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
