"""
Dev mode API endpoints.

Gated behind owner identity — only project owners see dev tools.
Phase D0: identity status endpoint.
Phase D1: scenario library for the stage debugger.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

dev_bp = Blueprint("dev", __name__)


@dev_bp.route("/dev/status")
def dev_status():
    """Return dev-mode status (identity match result).

    Response::

        {
            "dev_mode": true/false,
            "is_owner": true/false,
            "git_user": "Cyberpunk 042",
            "owners": ["Cyberpunk 042"]
        }
    """
    from src.core.services.identity import get_dev_mode_status

    root = current_app.config["PROJECT_ROOT"]
    return jsonify(get_dev_mode_status(root))


@dev_bp.route("/dev/scenarios")
def dev_scenarios():
    """Return all scenarios for the stage debugger.

    Query params:
        system  -- system preset ID (default: "debian_12")

    Response::

        {
            "scenarios": [ ... ],
            "system_presets": ["debian_12", "fedora_39", ...],
            "current_system": "debian_12"
        }
    """
    from src.core.services.dev_scenarios import (
        generate_all_scenarios,
        get_system_presets,
    )

    system = request.args.get("system", "debian_12")
    presets = get_system_presets()

    # Validate preset
    if system not in presets:
        system = "debian_12"

    scenarios = generate_all_scenarios(system)

    return jsonify({
        "scenarios": scenarios,
        "system_presets": presets,
        "current_system": system,
    })


@dev_bp.route("/dev/scenarios/<scenario_id>")
def dev_scenario_by_id(scenario_id: str):
    """Return a single scenario by ID.

    Useful for deep-linking from logs or chat.
    """
    from src.core.services.dev_scenarios import generate_all_scenarios

    system = request.args.get("system", "debian_12")
    scenarios = generate_all_scenarios(system)

    for s in scenarios:
        if s["_meta"]["id"] == scenario_id:
            return jsonify(s)

    return jsonify({"error": f"Scenario '{scenario_id}' not found"}), 404
