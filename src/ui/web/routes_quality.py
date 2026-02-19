"""
Code quality routes — lint, typecheck, test, format endpoints.

Blueprint: quality_bp
Prefix: /api

Thin HTTP wrappers over ``src.core.services.quality_ops``.

Endpoints:
    GET  /quality/status          — detected quality tools
    POST /quality/check           — run quality checks
    POST /quality/lint            — run linters
    POST /quality/typecheck       — run type-checkers
    POST /quality/test            — run tests
    POST /quality/format          — check/apply formatting
    POST /quality/generate/config — generate quality configs
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import quality_ops
from src.core.services.run_tracker import run_tracked

quality_bp = Blueprint("quality", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


def _get_stack_names() -> list[str]:
    """Get unique stack names from detected modules."""
    from src.core.config.loader import load_project
    from src.core.config.stack_loader import discover_stacks
    from src.core.services.detection import detect_modules

    root = _project_root()
    project = load_project(root / "project.yml")
    stacks = discover_stacks(root / "stacks")
    detection = detect_modules(project, root, stacks)

    seen: set[str] = set()
    names: list[str] = []
    for m in detection.modules:
        stack = m.effective_stack
        if stack and stack not in seen:
            names.append(stack)
            seen.add(stack)
    return names


# ── Detect ──────────────────────────────────────────────────────────


@quality_bp.route("/quality/status")
def quality_status():  # type: ignore[no-untyped-def]
    """Detected quality tools and their availability."""
    from src.core.services.devops_cache import get_cached

    root = _project_root()
    force = request.args.get("bust", "") == "1"

    def _compute() -> dict:
        stack_names = _get_stack_names()
        return quality_ops.quality_status(root, stack_names=stack_names)

    return jsonify(get_cached(root, "quality", _compute, force=force))


# ── Run ─────────────────────────────────────────────────────────────


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


# ── Facilitate ──────────────────────────────────────────────────────


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
