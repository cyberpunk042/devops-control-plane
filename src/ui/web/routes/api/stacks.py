"""API stacks — stack definitions endpoint."""

from __future__ import annotations

from flask import jsonify

from src.ui.web.helpers import project_root as _project_root

from . import api_bp


@api_bp.route("/stacks")
def api_stacks():  # type: ignore[no-untyped-def]
    """Available stack definitions."""
    from src.core.config.stack_loader import discover_stacks

    stacks_dir = _project_root() / "stacks"
    stacks = discover_stacks(stacks_dir)

    return jsonify({
        name: {
            "name": s.name,
            "description": s.description,
            "capabilities": [
                {"name": c.name, "command": c.command, "description": c.description}
                for c in s.capabilities
            ],
        }
        for name, s in stacks.items()
    })
