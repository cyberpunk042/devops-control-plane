"""
Batch API — resolve multiple data keys in a single HTTP request.

Eliminates the ~300ms-per-request gap caused by HTTP/1.1 connection
limits.  On page load the frontend fires ONE ``POST /api/batch``
instead of 12+ individual GETs.  Resolvers execute in parallel
via :class:`~concurrent.futures.ThreadPoolExecutor`.

Blueprint: ``batch_bp``
Prefix: ``/api``

Endpoints:
    POST /api/batch  — resolve multiple keys/groups in one response

Example request::

    POST /api/batch
    {"groups": ["boot-critical", "boot-deferred", "boot-config"]}

    POST /api/batch
    {"keys": ["status", "health", "capabilities"]}

Example response::

    {
        "results": {"status": {...}, "health": {...}},
        "errors": {"capabilities": "some error message"},
        "timing_ms": 187
    }
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from flask import Blueprint, current_app, jsonify, request

batch_bp = Blueprint("batch", __name__)
logger = logging.getLogger(__name__)

# ── Batch Registry ──────────────────────────────────────────────
#
# Maps string keys → zero-arg callables that return dicts.
# Resolvers are registered in _register_all() on first use.

_BATCH_REGISTRY: dict[str, Callable[[], dict]] = {}
_registry_done = False

# ── Predefined Groups ──────────────────────────────────────────
#
# Named bundles of keys for common scenarios.  The frontend
# requests groups by name, avoiding the need to hard-code the
# full key list in JavaScript.

BATCH_GROUPS: dict[str, list[str]] = {
    # Critical-path data (blocks first paint)
    "boot-critical": [
        "status",
        "health",
        "tools",
    ],
    # Deferred boot data (loaded after first paint)
    "boot-deferred": [
        "capabilities",
        "git-auth",
        "gh-status",
        "notifications-badge",
        "audits-pending",
    ],
    # Configuration / preferences (fast file reads)
    "boot-config": [
        "server-status",
        "dev-status",
        "devops-prefs",
        "integration-prefs",
    ],
}


# ── Endpoint ────────────────────────────────────────────────────

@batch_bp.route("/batch", methods=["POST"])
def batch_resolve():  # type: ignore[no-untyped-def]
    """Resolve multiple data keys in a single HTTP round-trip.

    Accepts JSON body with ``keys`` (list of strings) and/or
    ``groups`` (list of group names).  Keys are de-duplicated.
    Unknown keys are silently ignored.

    Each resolver runs in a thread pool, so slow resolvers don't
    block fast ones.  Individual errors are isolated — partial
    results are always returned.
    """
    _ensure_registry()

    body = request.get_json(silent=True) or {}

    # Collect requested keys from explicit list + group expansion
    keys: set[str] = set(body.get("keys", []))
    for group_name in body.get("groups", []):
        keys.update(BATCH_GROUPS.get(group_name, []))

    # Filter to registered keys only
    valid = {k for k in keys if k in _BATCH_REGISTRY}

    if not valid:
        return jsonify({"results": {}, "errors": {}, "timing_ms": 0})

    results: dict[str, dict] = {}
    errors: dict[str, str] = {}
    t0 = time.monotonic()

    # Capture the real Flask app object so worker threads can push
    # their own app context.  ThreadPoolExecutor threads do NOT
    # inherit the request thread's application context.
    app = current_app._get_current_object()

    def _run_resolver(key: str) -> dict:
        """Run a single resolver inside an app context."""
        with app.app_context():
            return _BATCH_REGISTRY[key]()

    # Execute resolvers in parallel — this is the key win.
    # Each resolver is read-only and thread-safe (same as the
    # individual GET handlers that already run in werkzeug threads).
    max_workers = min(len(valid), 6)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_run_resolver, k): k for k in valid}
        for future in as_completed(futures, timeout=10):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:
                logger.warning("Batch resolver %r failed: %s", key, exc)
                errors[key] = str(exc)

    elapsed_ms = round((time.monotonic() - t0) * 1000)
    logger.debug("Batch resolved %d keys in %dms", len(results), elapsed_ms)

    return jsonify({
        "results": results,
        "errors": errors,
        "timing_ms": elapsed_ms,
    })


# ── Resolver Registration ──────────────────────────────────────
#
# Each resolver wraps the SAME backend call as the individual
# route handler.  No logic duplication.  Imports are deferred
# to avoid circular import issues at module load time.

def _ensure_registry() -> None:
    """Populate the batch registry (once, on first request)."""
    global _registry_done
    if _registry_done:
        return
    _registry_done = True

    # All resolvers run inside a Flask request context (the POST
    # /api/batch request), so current_app and request are available.

    def _root() -> Path:
        return Path(current_app.config["PROJECT_ROOT"])

    def _config_path() -> Path | None:
        p = current_app.config.get("CONFIG_PATH")
        return Path(p) if p else None

    # ── boot-critical ───────────────────────────────────────

    def _resolve_status() -> dict:
        from src.core.use_cases.status import get_status
        result = get_status(config_path=_config_path())
        if result.error:
            return {"error": result.error}
        return result.to_dict()

    def _resolve_health() -> dict:
        from src.core.observability.health import check_system_health
        return check_system_health().to_dict()

    def _resolve_tools() -> dict:
        from src.core.services.devops.cache import get_cached
        from src.core.services.tool_install.path_refresh import (
            refresh_server_path as _refresh_server_path,
        )

        root = _root()

        def _compute() -> dict:
            _refresh_server_path()
            from src.core.services.audit.l0_detection import detect_tools
            from src.core.services.tool_install import TOOL_RECIPES

            tools = detect_tools()
            for t in tools:
                tid = t["id"]
                recipe = TOOL_RECIPES.get(tid)
                t["has_recipe"] = recipe is not None
                t["needs_sudo"] = (
                    any(recipe["needs_sudo"].values()) if recipe else False
                )
            available = sum(1 for t in tools if t["available"])
            missing = [t for t in tools if not t["available"]]
            return {
                "tools": tools,
                "total": len(tools),
                "available": available,
                "missing_count": len(missing),
                "missing": missing,
            }

        return get_cached(root, "tools", _compute)

    # ── boot-deferred ──────────────────────────────────────

    def _resolve_capabilities() -> dict:
        from src.core.use_cases.status import get_capabilities
        return get_capabilities(
            config_path=_config_path(),
            project_root=_root(),
        )

    def _resolve_git_auth() -> dict:
        from src.core.services.git_auth import check_auth
        return check_auth(_root())

    def _resolve_gh_status() -> dict:
        from src.core.services import git_ops
        from src.core.services.devops.cache import get_cached
        root = _root()
        return get_cached(
            root, "github",
            lambda: git_ops.gh_status(root),
        )

    def _resolve_notifications_badge() -> dict:
        from src.core.services.error_log import get_unacked_count
        from src.core.services.notifications import get_active_notifications
        root = _root()
        return {
            "notification_count": len(get_active_notifications(root)),
            "error_count": get_unacked_count(root),
        }

    def _resolve_audits_pending() -> dict:
        from src.core.services.audit_staging import list_pending
        return {"pending": list_pending(_root())}

    # ── boot-config ────────────────────────────────────────

    def _resolve_server_status() -> dict:
        from src.core.services.server_lifecycle import server_status
        root = _root()
        host = current_app.config.get("SERVER_HOST", "")
        port = current_app.config.get("SERVER_PORT", 0)
        result = server_status(root, host=host, port=port)
        fallback = current_app.config.get("PORT_FALLBACK", {})
        result["fallback_mode"] = fallback.get("active", False)
        if fallback.get("active"):
            result["preferred_port"] = fallback["preferred_port"]
            result["actual_port"] = fallback["actual_port"]
            result["config_path"] = fallback.get("config_path", "project.yml")
        return result

    def _resolve_dev_status() -> dict:
        from src.core.services.identity import get_dev_mode_status
        return get_dev_mode_status(_root())

    def _resolve_devops_prefs() -> dict:
        from src.core.services.devops import cache as devops_cache
        return devops_cache.load_prefs(_root())

    def _resolve_integration_prefs() -> dict:
        from src.core.services.devops import cache as devops_cache
        prefs = devops_cache.load_prefs(_root())
        return {k: v for k, v in prefs.items() if k.startswith("int:")}

    # ── Register all ───────────────────────────────────────

    reg = _BATCH_REGISTRY
    # boot-critical
    reg["status"] = _resolve_status
    reg["health"] = _resolve_health
    reg["tools"] = _resolve_tools
    # boot-deferred
    reg["capabilities"] = _resolve_capabilities
    reg["git-auth"] = _resolve_git_auth
    reg["gh-status"] = _resolve_gh_status
    reg["notifications-badge"] = _resolve_notifications_badge
    reg["audits-pending"] = _resolve_audits_pending
    # boot-config
    reg["server-status"] = _resolve_server_status
    reg["dev-status"] = _resolve_dev_status
    reg["devops-prefs"] = _resolve_devops_prefs
    reg["integration-prefs"] = _resolve_integration_prefs
