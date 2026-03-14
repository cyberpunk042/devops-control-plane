"""CI status — detected providers, workflows, coverage."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import ci_ops
from src.ui.web.helpers import project_root as _project_root

from . import ci_bp


@ci_bp.route("/ci/status")
def ci_status():  # type: ignore[no-untyped-def]
    """CI/CD availability: detected providers, workflow count."""
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("devops.ci", force=force)
    return jsonify(result["data"])


@ci_bp.route("/ci/workflows")
def ci_workflows():  # type: ignore[no-untyped-def]
    """Parsed workflow files with structural analysis."""
    return jsonify(ci_ops.ci_workflows(_project_root()))


@ci_bp.route("/ci/coverage")
def ci_coverage():  # type: ignore[no-untyped-def]
    """Module CI coverage analysis."""
    return jsonify(ci_ops.ci_coverage(_project_root()))
