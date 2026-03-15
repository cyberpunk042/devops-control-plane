"""CI generation — generate CI and lint workflows."""

from __future__ import annotations

from flask import jsonify

from src.core.services import ci_ops
from src.core.services.events.tracked import tracked
from src.ui.web.helpers import project_root as _project_root

from . import ci_bp


@ci_bp.route("/ci/generate/ci", methods=["POST"])
@tracked("ci.workflow.generated")
def generate_ci():  # type: ignore[no-untyped-def]
    """Generate a CI workflow from detected stacks."""
    root = _project_root()
    result = ci_ops.generate_ci_workflow(root)

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@ci_bp.route("/ci/generate/lint", methods=["POST"])
@tracked("ci.lint.generated")
def generate_lint():  # type: ignore[no-untyped-def]
    """Generate a lint workflow from detected stacks."""
    root = _project_root()
    result = ci_ops.generate_lint_workflow(root)

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)
