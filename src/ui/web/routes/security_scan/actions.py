"""Security actions — generate gitignore."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services.security import ops as security_ops
from src.core.services.run_tracker import run_tracked
from src.ui.web.helpers import project_root as _project_root, get_stack_names as _get_stack_names

from . import security_bp2


@security_bp2.route("/security/generate/gitignore", methods=["POST"])
@run_tracked("generate", "generate:gitignore")
def security_generate_gitignore():  # type: ignore[no-untyped-def]
    """Generate .gitignore from detected stacks."""
    data = request.get_json(silent=True) or {}
    stack_names = data.get("stacks") or _get_stack_names()

    result = security_ops.generate_gitignore(_project_root(), stack_names)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)
