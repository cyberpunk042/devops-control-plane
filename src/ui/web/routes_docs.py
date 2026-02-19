"""
Documentation routes — status, coverage, links, generation.

Blueprint: docs_bp
Prefix: /api

Endpoints:
    GET  /docs/status          — documentation inventory
    GET  /docs/coverage        — per-module doc coverage
    GET  /docs/links           — broken link check
    POST /docs/generate/changelog — generate changelog
    POST /docs/generate/readme    — generate README template
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import docs_ops
from src.core.services.run_tracker import run_tracked

docs_bp = Blueprint("docs", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


@docs_bp.route("/docs/status")
def docs_status():  # type: ignore[no-untyped-def]
    """Documentation inventory."""
    from src.core.services.devops_cache import get_cached

    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(
        root, "docs",
        lambda: docs_ops.docs_status(root),
        force=force,
    ))


@docs_bp.route("/docs/coverage")
def docs_coverage():  # type: ignore[no-untyped-def]
    """Per-module documentation coverage."""
    return jsonify(docs_ops.docs_coverage(_project_root()))


@docs_bp.route("/docs/links")
def docs_links():  # type: ignore[no-untyped-def]
    """Check for broken internal links."""
    file_path = request.args.get("file")
    return jsonify(docs_ops.check_links(_project_root(), file_path=file_path))


@docs_bp.route("/docs/generate/changelog", methods=["POST"])
@run_tracked("generate", "generate:changelog")
def docs_generate_changelog():  # type: ignore[no-untyped-def]
    """Generate CHANGELOG.md from git history."""
    data = request.get_json(silent=True) or {}
    result = docs_ops.generate_changelog(
        _project_root(),
        max_commits=data.get("commits", 50),
        since=data.get("since"),
    )
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@docs_bp.route("/docs/generate/readme", methods=["POST"])
@run_tracked("generate", "generate:readme")
def docs_generate_readme():  # type: ignore[no-untyped-def]
    """Generate README.md template."""
    return jsonify(docs_ops.generate_readme(_project_root()))
