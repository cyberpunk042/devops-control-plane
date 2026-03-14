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

from src.core.services.devops import cache as devops_cache
from src.ui.web.helpers import project_root as _project_root

devops_bp = Blueprint("devops", __name__)




# ── Card preferences ────────────────────────────────────────────


@devops_bp.route("/devops/prefs", methods=["GET"])
def devops_prefs_get():
    """Get card load preferences."""
    return jsonify(devops_cache.load_prefs(_project_root()))


@devops_bp.route("/devops/prefs", methods=["PUT"])
def devops_prefs_put():
    """Save card load preferences (merges into existing)."""
    data = request.get_json(silent=True) or {}
    all_prefs = devops_cache.load_prefs(_project_root())
    all_prefs.update(data)
    devops_cache.save_prefs(_project_root(), all_prefs)
    return jsonify(all_prefs)


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
    int_prefs = {k: v for k, v in all_prefs.items() if k.startswith("int:")}
    return jsonify(int_prefs)


# ── Cache bust ──────────────────────────────────────────────────


# Mediator paths for scoped busts.
# "devops" scope: detect nodes whose devops.* counterparts are devops tab cards.
_DEVOPS_SCOPE_DETECT = [
    "detect.security", "detect.testing", "detect.quality", "detect.packages",
    "detect.env", "detect.docs", "detect.k8s", "detect.terraform", "detect.dns",
]
# "integrations" scope: detect nodes for integration tab cards.
_INTEGRATIONS_SCOPE_DETECT = [
    "detect.git", "detect.github", "detect.ci", "detect.docker",
    "detect.k8s", "detect.terraform",
]


def _mediator_bust_scope(scope: str) -> list[str]:
    """Bust mediator nodes for a given scope. Returns list of busted paths.

    Invalidating ``detect.*`` cascades to ``devops.*`` via ``depends_on``.
    """
    from src.core.services.mediator import get_mediator

    m = get_mediator()
    busted: list[str] = []

    if scope == "all":
        # Bust ALL detect + audit + catalog nodes
        for path in list(m.tree.all_paths()):
            if path.startswith(("detect.", "audit.", "catalog.")):
                result = m.put(path, cascade=True)
                busted.append(path)
    elif scope == "devops":
        for path in _DEVOPS_SCOPE_DETECT:
            m.put(path, cascade=True)
            busted.append(path)
    elif scope == "integrations":
        for path in _INTEGRATIONS_SCOPE_DETECT:
            m.put(path, cascade=True)
            busted.append(path)
    elif scope == "audit":
        for path in list(m.tree.all_paths()):
            if path.startswith("audit."):
                m.put(path, cascade=True)
                busted.append(path)
    else:
        # Single card: invalidate the detect.* node (cascade → devops.*)
        detect_path = f"detect.{scope}"
        node = m.tree.resolve(detect_path)
        if node is not None:
            m.put(detect_path, cascade=True)
            busted.append(detect_path)

    return busted


@devops_bp.route("/devops/cache/bust", methods=["POST"])
def devops_cache_bust():
    """Bust server-side cache via the mediator.

    Body: {"card": "security"}       — bust one card (with cascade)
    Body: {"card": "devops"}         — bust devops tab cards only
    Body: {"card": "integrations"}   — bust integration tab cards only
    Body: {"card": "audit"}          — bust audit cards only
    Body: {} or {"card": "all"}      — bust all cards

    The mediator handles invalidation and cascade propagation.
    Detect node invalidation cascades to devops.* via depends_on.
    """
    data = request.get_json(silent=True) or {}
    card = data.get("card", "all")

    try:
        busted = _mediator_bust_scope(card)
    except Exception:
        busted = []  # mediator not ready — non-fatal

    return jsonify({"ok": True, "busted": card})



# ── Sub-module imports (register routes on devops_bp) ───────────

from . import detect   # noqa: E402, F401
from . import apply    # noqa: E402, F401
from . import audit    # noqa: E402, F401
