"""Quality actions — run checks, lint, typecheck, test, format, generate config."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services.quality import ops as quality_ops
from src.core.services.run_tracker import run_tracked
from src.ui.web.helpers import project_root as _project_root

from . import quality_bp


@quality_bp.route("/quality/check", methods=["POST"])
@run_tracked("validate", "validate:quality")
def quality_check():  # type: ignore[no-untyped-def]
    """Run quality checks."""
    data = request.get_json(silent=True) or {}
    result = quality_ops.quality_run(
        _project_root(),
        tool=data.get("tool"),
        category=data.get("category"),
        fix=data.get("fix", False),
    )

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@quality_bp.route("/quality/lint", methods=["POST"])
@run_tracked("validate", "validate:lint")
def quality_lint():  # type: ignore[no-untyped-def]
    """Run linters."""
    data = request.get_json(silent=True) or {}
    return jsonify(quality_ops.quality_lint(_project_root(), fix=data.get("fix", False)))


@quality_bp.route("/quality/typecheck", methods=["POST"])
@run_tracked("validate", "validate:typecheck")
def quality_typecheck():  # type: ignore[no-untyped-def]
    """Run type-checkers."""
    return jsonify(quality_ops.quality_typecheck(_project_root()))


@quality_bp.route("/quality/test", methods=["POST"])
@run_tracked("test", "test:quality")
def quality_test():  # type: ignore[no-untyped-def]
    """Run tests."""
    return jsonify(quality_ops.quality_test(_project_root()))


@quality_bp.route("/quality/format", methods=["POST"])
@run_tracked("format", "format:quality")
def quality_format():  # type: ignore[no-untyped-def]
    """Check or apply formatting."""
    data = request.get_json(silent=True) or {}
    return jsonify(quality_ops.quality_format(_project_root(), fix=data.get("fix", False)))


@quality_bp.route("/quality/generate/config", methods=["POST"])
@run_tracked("generate", "generate:quality_config")
def quality_generate_config():  # type: ignore[no-untyped-def]
    """Generate quality configs for a stack."""
    data = request.get_json(silent=True) or {}
    stack = data.get("stack", "")
    if not stack:
        return jsonify({"error": "Missing 'stack' field"}), 400

    result = quality_ops.generate_quality_config(_project_root(), stack)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)
