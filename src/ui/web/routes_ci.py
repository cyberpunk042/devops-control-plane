"""
CI/CD routes — workflow analysis and generation endpoints.

Blueprint: ci_bp
Prefix: /api

Thin HTTP wrappers over ``src.core.services.ci_ops``.

Endpoints:
    GET  /ci/status              — detected CI providers
    GET  /ci/workflows           — parsed workflow files with analysis
    GET  /ci/coverage            — module CI coverage analysis
    POST /ci/generate/ci         — generate CI workflow
    POST /ci/generate/lint       — generate lint workflow
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import ci_ops

ci_bp = Blueprint("ci", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


# ── Detect ──────────────────────────────────────────────────────────


@ci_bp.route("/ci/status")
def ci_status():  # type: ignore[no-untyped-def]
    """CI/CD availability: detected providers, workflow count."""
    from src.core.services.devops_cache import get_cached

    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "ci",
        lambda: ci_ops.ci_status(root),
        force=force,
    ))


# ── Observe ─────────────────────────────────────────────────────────


@ci_bp.route("/ci/workflows")
def ci_workflows():  # type: ignore[no-untyped-def]
    """Parsed workflow files with structural analysis."""
    return jsonify(ci_ops.ci_workflows(_project_root()))


@ci_bp.route("/ci/coverage")
def ci_coverage():  # type: ignore[no-untyped-def]
    """Module CI coverage analysis."""
    return jsonify(ci_ops.ci_coverage(_project_root()))


# ── Facilitate (generate) ───────────────────────────────────────────


@ci_bp.route("/ci/generate/ci", methods=["POST"])
def generate_ci():  # type: ignore[no-untyped-def]
    """Generate a CI workflow from detected stacks."""
    root = _project_root()
    result = ci_ops.generate_ci_workflow(root)

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@ci_bp.route("/ci/generate/lint", methods=["POST"])
def generate_lint():  # type: ignore[no-untyped-def]
    """Generate a lint workflow from detected stacks."""
    root = _project_root()
    result = ci_ops.generate_lint_workflow(root)

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)
