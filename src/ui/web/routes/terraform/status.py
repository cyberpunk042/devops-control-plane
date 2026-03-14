"""Terraform read-only queries — status, state, workspaces, output."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services.terraform import ops as terraform_ops
from src.ui.web.helpers import project_root as _project_root

from . import terraform_bp


@terraform_bp.route("/terraform/status")
def tf_status():  # type: ignore[no-untyped-def]
    """Terraform configuration analysis."""
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("devops.terraform", force=force)
    return jsonify(result["data"])


@terraform_bp.route("/terraform/state")
def tf_state():  # type: ignore[no-untyped-def]
    """List resources in terraform state."""
    return jsonify(terraform_ops.terraform_state(_project_root()))


@terraform_bp.route("/terraform/workspaces")
def tf_workspaces():  # type: ignore[no-untyped-def]
    """List terraform workspaces."""
    return jsonify(terraform_ops.terraform_workspaces(_project_root()))


@terraform_bp.route("/terraform/output")
def tf_output():  # type: ignore[no-untyped-def]
    """Get Terraform outputs."""
    result = terraform_ops.terraform_output(_project_root())
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)
