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

    Body: {"card": "security"}       — bust one card (with cascade)
    Body: {"card": "devops"}         — bust devops tab cards only
    Body: {"card": "integrations"}   — bust integration tab cards only
    Body: {} or {"card": "all"}      — bust all cards

    On scoped/all bust, starts a background thread that recomputes
    the affected cards sequentially (no I/O contention).  Browser GETs
    that arrive during recompute block on the per-key lock and get
    fresh results without duplicating work.
    """
    data = request.get_json(silent=True) or {}
    card = data.get("card", "all")

    root = _project_root()
    _ensure_registry()

    # Scoped busts: devops / integrations / audit / all
    if card in ("all", "devops", "integrations", "audit"):
        if card == "all":
            devops_cache.invalidate_all(root)
            devops_cache.recompute_all(root)
        else:
            busted = devops_cache.invalidate_scope(root, card)
            scope_map = {
                "devops": devops_cache.DEVOPS_KEYS,
                "integrations": devops_cache.INTEGRATION_KEYS,
                "audit": devops_cache.AUDIT_KEYS,
            }
            devops_cache.recompute_all(root, keys=scope_map[card])
        return jsonify({"ok": True, "busted": card})
    else:
        # Single card bust (with cascade)
        busted = devops_cache.invalidate_with_cascade(root, card)
        return jsonify({"ok": True, "busted": busted})


# ── Compute function registry (lazy init) ───────────────────────
# Populated on first bust-all.  Each entry maps a cache key to a
# function(project_root) → dict.  Imports are deferred to avoid
# circular import issues at module load time.

_registry_done = False


def _ensure_registry() -> None:
    """Register all card compute functions (once)."""
    global _registry_done
    if _registry_done:
        return
    _registry_done = True

    from src.core.services import (
        dns_cdn_ops,
        docker_ops,
        docs_ops,
        env_ops,
        k8s_ops,
        package_ops,
        quality_ops,
        security_ops as _sec_ops,
        testing_ops,
    )
    from src.core.services import ci_ops
    from src.core.services import git_ops

    from src.core.services import terraform_ops

    def _compute_security(root: Path) -> dict:
        scan = _sec_ops.scan_secrets(root)
        posture = _sec_ops.security_posture(root)
        return {
            "findings": scan.get("findings", []),
            "finding_count": scan.get("count", 0),
            "posture": posture,
        }

    reg = devops_cache.register_compute
    reg("packages", lambda root: package_ops.package_status(root))
    reg("quality", lambda root: quality_ops.quality_status(root))
    reg("git", lambda root: git_ops.git_status(root))
    reg("ci", lambda root: ci_ops.ci_status(root))
    reg("security", lambda root: _compute_security(root))
    reg("docker", lambda root: docker_ops.docker_status(root))
    reg("k8s", lambda root: k8s_ops.k8s_status(root))
    reg("env", lambda root: env_ops.env_status(root))
    reg("docs", lambda root: docs_ops.docs_status(root))
    reg("terraform", lambda root: terraform_ops.terraform_status(root))
    reg("dns", lambda root: dns_cdn_ops.dns_cdn_status(root))
    reg("testing", lambda root: testing_ops.testing_status(root))
    # Integration-only keys
    reg("github", lambda root: git_ops.gh_status(root))
    # Note: "pages" uses complex inlined compute (segments + build_status)
    # so it's not registered here; it computes via the browser GET path.

    # Audit L0/L1 keys
    from src.core.services.audit import (
        audit_scores as _audit_scores,
        l0_system_profile, l1_dependencies,
        l1_structure, l1_clients,
    )
    reg("audit:scores", lambda root: _audit_scores(root))
    reg("audit:system", lambda root: l0_system_profile(root))
    reg("audit:deps", lambda root: l1_dependencies(root))
    reg("audit:structure", lambda root: l1_structure(root))
    reg("audit:clients", lambda root: l1_clients(root))


# ── Sub-module imports (register routes on devops_bp) ───────────

from src.ui.web import routes_devops_detect   # noqa: E402, F401
from src.ui.web import routes_devops_apply    # noqa: E402, F401
from src.ui.web import routes_devops_audit    # noqa: E402, F401
