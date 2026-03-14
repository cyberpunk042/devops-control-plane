"""Infra IaC — IaC detection and card status endpoints."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services.env import ops as env_ops
from src.ui.web.helpers import project_root as _project_root

from . import infra_bp


@infra_bp.route("/infra/iac/status")
def iac_status():  # type: ignore[no-untyped-def]
    """Detected IaC providers and configs."""
    return jsonify(env_ops.iac_status(_project_root()))


@infra_bp.route("/infra/iac/resources")
def iac_resources():  # type: ignore[no-untyped-def]
    """IaC resource inventory."""
    return jsonify(env_ops.iac_resources(_project_root()))


@infra_bp.route("/env/card-status")
def env_card_status():  # type: ignore[no-untyped-def]
    """Aggregated environment data for the DevOps dashboard card."""
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("devops.env", force=force)
    return jsonify(result["data"])
