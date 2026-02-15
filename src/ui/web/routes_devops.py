"""
DevOps dashboard routes — preferences and cache management.

Blueprint: devops_bp
Prefix: /api

This module defines the blueprint and core endpoints.
Route handlers are split across sub-modules for maintainability:

    routes_devops.py              — (this file) blueprint, prefs, cache bust
    routes_devops_detect.py       — wizard environment detection + data helpers
    routes_devops_apply.py        — wizard setup actions + config generation
    routes_devops_audit.py        — audit finding dismissals

Endpoints (this file):
    GET  /devops/prefs           — card load preferences (devops tab)
    PUT  /devops/prefs           — save card load preferences
    GET  /devops/integration-prefs — integration card preferences
    PUT  /devops/integration-prefs — save integration card preferences
    POST /devops/cache/bust      — bust server-side cache
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import devops_cache

devops_bp = Blueprint("devops", __name__)


def _project_root() -> Path:
    return current_app.config["PROJECT_ROOT"]


# ── Card preferences ────────────────────────────────────────────


@devops_bp.route("/devops/prefs", methods=["GET"])
def devops_prefs_get():
    """Get card load preferences."""
    return jsonify(devops_cache.load_prefs(_project_root()))


@devops_bp.route("/devops/prefs", methods=["PUT"])
def devops_prefs_put():
    """Save card load preferences."""
    data = request.get_json(silent=True) or {}
    devops_cache.save_prefs(_project_root(), data)
    return jsonify({"ok": True})


# ── Integration card preferences ────────────────────────────────


@devops_bp.route("/devops/integration-prefs", methods=["GET"])
def integration_prefs_get():
    """Get integration card load preferences (int:* keys only)."""
    prefs = devops_cache.load_prefs(_project_root())
    int_prefs = {k: v for k, v in prefs.items() if k.startswith("int:")}
    return jsonify(int_prefs)


@devops_bp.route("/devops/integration-prefs", methods=["PUT"])
def integration_prefs_put():
    """Save integration card load preferences."""
    data = request.get_json(silent=True) or {}
    all_prefs = devops_cache.load_prefs(_project_root())
    # Only update int:* keys
    for key, val in data.items():
        if key.startswith("int:"):
            all_prefs[key] = val
    devops_cache.save_prefs(_project_root(), all_prefs)
    return jsonify({"ok": True})


# ── Cache bust ──────────────────────────────────────────────────


@devops_bp.route("/devops/cache/bust", methods=["POST"])
def devops_cache_bust():
    """Bust server-side cache.

    Body: {"card": "security"}  — bust one card (with cascade)
    Body: {} or {"card": "all"} — bust all cards
    """
    data = request.get_json(silent=True) or {}
    card = data.get("card", "all")

    if card == "all":
        devops_cache.invalidate_all(_project_root())
        return jsonify({"ok": True, "busted": "all"})
    else:
        busted = devops_cache.invalidate_with_cascade(_project_root(), card)
        return jsonify({"ok": True, "busted": busted})


# ── Sub-module imports (register routes on devops_bp) ───────────

from src.ui.web import routes_devops_detect   # noqa: E402, F401
from src.ui.web import routes_devops_apply    # noqa: E402, F401
from src.ui.web import routes_devops_audit    # noqa: E402, F401
