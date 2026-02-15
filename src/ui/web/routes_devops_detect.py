"""
DevOps wizard — environment detection endpoint.

Blueprint: devops_bp (imported from routes_devops)
Prefix: /api

Thin HTTP wrapper over ``src.core.services.wizard_ops``.

Endpoint:
    GET  /wizard/detect  — detect integrations, tools, project characteristics
"""

from __future__ import annotations

from pathlib import Path

from flask import current_app, jsonify, request

from src.core.services import devops_cache
from src.ui.web.routes_devops import devops_bp


def _project_root() -> Path:
    return current_app.config["PROJECT_ROOT"]


@devops_bp.route("/wizard/detect")
def wizard_detect():  # type: ignore[no-untyped-def]
    """Detect available integrations, tools, and project characteristics.

    Returns a lightweight snapshot used by the setup wizard to suggest
    which integrations to enable and which tools to install.

    Cached server-side via devops_cache (key ``wiz:detect``).
    Pass ``?bust=1`` to force a fresh scan.
    """
    from src.core.services.wizard_ops import wizard_detect as _detect

    root = _project_root()
    force = request.args.get("bust", "") == "1"

    return jsonify(devops_cache.get_cached(
        root, "wiz:detect",
        lambda: _detect(root),
        force=force,
    ))
