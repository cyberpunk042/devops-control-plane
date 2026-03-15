"""Docs generation — changelog, readme."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services.docs_svc import ops as docs_ops
from src.core.services.events.tracked import tracked
from src.ui.web.helpers import project_root as _project_root

from . import docs_bp


@docs_bp.route("/docs/generate/changelog", methods=["POST"])
@tracked("changelog.generated")
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
@tracked("docs.readme.generated")
def docs_generate_readme():  # type: ignore[no-untyped-def]
    """Generate README.md template."""
    return jsonify(docs_ops.generate_readme(_project_root()))
