"""
DevOps dashboard routes — preferences and cache management.

Blueprint: devops_bp
Prefix: /api

Endpoints:
    GET  /devops/prefs           — card load preferences
    PUT  /devops/prefs           — save card load preferences
    POST /devops/cache/bust      — bust server-side cache (all or specific)
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import devops_cache

devops_bp = Blueprint("devops", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


# ── Card preferences ────────────────────────────────────────────


@devops_bp.route("/devops/prefs")
def devops_prefs_get():
    """Get card load preferences."""
    return jsonify(devops_cache.load_prefs(_project_root()))


@devops_bp.route("/devops/prefs", methods=["PUT"])
def devops_prefs_put():
    """Save card load preferences."""
    data = request.get_json(silent=True) or {}
    result = devops_cache.save_prefs(_project_root(), data)
    return jsonify(result)


# ── Cache management ────────────────────────────────────────────


@devops_bp.route("/devops/cache/bust", methods=["POST"])
def devops_cache_bust():
    """Bust server-side cache.

    Body: {"card": "security"}  — bust one card
    Body: {} or {"card": "all"} — bust all cards
    """
    data = request.get_json(silent=True) or {}
    card = data.get("card", "all")

    if card == "all":
        devops_cache.invalidate_all(_project_root())
        return jsonify({"ok": True, "busted": "all"})
    else:
        devops_cache.invalidate(_project_root(), card)
        return jsonify({"ok": True, "busted": card})
