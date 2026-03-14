"""
DevOps wizard — environment detection endpoint.

Blueprint: devops_bp (imported from routes_devops)
Prefix: /api

Thin HTTP wrapper over ``src.core.services.wizard_ops``.

Endpoint:
    GET  /wizard/detect  — detect integrations, tools, project characteristics
"""

from __future__ import annotations

from flask import jsonify, request

from . import devops_bp




@devops_bp.route("/wizard/detect")
def wizard_detect():  # type: ignore[no-untyped-def]
    """Detect available integrations, tools, and project characteristics.

    Returns a lightweight snapshot used by the setup wizard to suggest
    which integrations to enable and which tools to install.

    Cached via the mediator (node ``detect.wizard``).
    Pass ``?bust=1`` to force a fresh scan.
    """
    force = request.args.get("bust", "") == "1"

    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get("detect.wizard", force=force)
    return jsonify(result["data"])
