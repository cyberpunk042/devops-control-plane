"""Terminal emulator status endpoint."""

from __future__ import annotations

from flask import jsonify

from . import integrations_bp


@integrations_bp.route("/ops/terminal/status")
def ops_terminal_status():  # type: ignore[no-untyped-def]
    """Terminal emulator availability — working, broken, installable."""
    from src.core.services.terminal_ops import terminal_status
    return jsonify(terminal_status())
