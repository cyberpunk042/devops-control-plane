"""K8s wizard state — load, save, wipe."""

from __future__ import annotations

from flask import jsonify, request

from src.core.services import k8s_ops
from src.ui.web.helpers import project_root as _project_root

from . import k8s_bp


@k8s_bp.route("/k8s/wizard-state", methods=["GET"])
def k8s_wizard_state_load():  # type: ignore[no-untyped-def]
    """Load saved wizard state."""
    return jsonify(k8s_ops.load_wizard_state(_project_root()))


@k8s_bp.route("/k8s/wizard-state", methods=["POST"])
def k8s_wizard_state_save():  # type: ignore[no-untyped-def]
    """Persist wizard state."""
    data = request.get_json(silent=True) or {}
    result = k8s_ops.save_wizard_state(_project_root(), data)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@k8s_bp.route("/k8s/wizard-state", methods=["DELETE"])
def k8s_wizard_state_wipe():  # type: ignore[no-untyped-def]
    """Delete saved wizard state."""
    return jsonify(k8s_ops.wipe_wizard_state(_project_root()))
