"""
System Posture API routes — deprecation awareness for the nav badge.

Blueprint: ``posture_bp``
Prefix: ``/api``

Endpoints:
    GET /posture           → Full posture scan with all 4 pillars
    GET /posture/summary   → Lightweight summary for nav badge polling
    POST /posture/rescan   → Force rescan (cache bust)
    GET /posture/cache     → Cache diagnostics
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

posture_bp = Blueprint("posture", __name__)


@posture_bp.route("/posture")
def posture_full():  # type: ignore[no-untyped-def]
    """Full system posture scan with action enrichment.

    Returns all four pillars with item-level detail.  Each item
    is enriched with an ``actions`` list describing what the user
    can do about it (update, navigate, reset, etc.).

    Query params:
        bust=1  → Force rescan (bypass all caches).

    Returns:
        200 with full posture JSON including:
        - overall_rank, overall_status, summary
        - pillars: {platform, toolchain, project, runtime}
        - each pillar: {rank, items[], warnings[], recommendations[]}
        - each item may include: actions[]
    """
    force = request.args.get("bust", "") == "1"
    via = request.args.get("via", "")

    try:
        if via == "mediator":
            from src.core.services.mediator import get_mediator

            m = get_mediator()
            if force:
                m.put("posture.full", cascade=True)
            r = m.get("posture.full", force=force)
            posture = r["data"]
            result = posture.to_dict()
        else:
            from src.core.services.system_posture import scan_posture

            root = current_app.config.get("PROJECT_ROOT")
            posture = scan_posture(force=force, project_root=root)
            result = posture.to_dict()

        _enrich_posture_actions(result)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def _enrich_posture_actions(posture_dict: dict) -> None:
    """Add ``actions`` metadata to posture items for frontend buttons.

    Modifies ``posture_dict`` in place.  Each pillar is handled
    differently:

    - **toolchain**: Cross-references ``TOOL_RECIPES`` and
      ``get_update_map()`` to determine if a tool can be updated.
    - **project**: Adds navigation links to the audit tab.
    - **runtime**: Adds reset actions for degraded circuit breakers.
    - **platform**: Adds guide flags for outdated OS versions.
    """
    pillars = posture_dict.get("pillars", {})

    # ── Toolchain — update actions ─────────────────────────────
    toolchain = pillars.get("toolchain", {})
    tc_items = toolchain.get("items", [])

    if tc_items:
        from src.core.services.tool_install.data.recipes import TOOL_RECIPES
        from src.core.services.tool_install.resolver.method_selection import (
            get_update_map,
        )

        # Ranks that qualify for an update action
        _updatable_ranks = {"aging", "outdated", "deprecated", "dangerous"}
        updatable_count = 0

        for item in tc_items:
            rank = item.get("rank", "")
            name = item.get("name", "")

            # Strip common prefixes used by the toolchain scanner
            # (e.g. "toolchain:docker" → "docker")
            tool_id = name.split(":")[-1] if ":" in name else name

            recipe = TOOL_RECIPES.get(tool_id)
            if not recipe:
                # No recipe — no automated action
                continue

            if rank not in _updatable_ranks:
                continue

            update_map = get_update_map(recipe)
            if update_map:
                needs_sudo = any(
                    recipe.get("needs_sudo", {}).get(m, False)
                    for m in update_map
                )
                item["actions"] = [{
                    "type": "update",
                    "available": True,
                    "tool_id": tool_id,
                    "label": f"Update {recipe.get('label', tool_id)}",
                    "needs_sudo": needs_sudo,
                }]
                updatable_count += 1
            else:
                # Has recipe but no update command — manual hint
                cli = recipe.get("cli", tool_id)
                item["actions"] = [{
                    "type": "manual",
                    "available": True,
                    "tool_id": tool_id,
                    "label": f"Manual update for {recipe.get('label', tool_id)}",
                    "hint": _manual_update_hint_simple(tool_id, recipe),
                }]

        # Store count for batch button
        if updatable_count > 0:
            toolchain["updatable_count"] = updatable_count

    # ── Project — audit navigation links ───────────────────────
    project = pillars.get("project", {})
    for item in project.get("items", []):
        name = item.get("name", "")
        # project items are named like "project:git", "project:docker"
        probe_id = name.split(":")[-1] if ":" in name else name
        rank = item.get("rank", "")

        if rank in ("outdated", "deprecated", "dangerous", "aging"):
            item["actions"] = [{
                "type": "link",
                "target": "audit",
                "card_id": probe_id,
                "label": "View in Audit",
            }]

    # ── Runtime — reset actions ────────────────────────────────
    runtime = pillars.get("runtime", {})
    for item in runtime.get("items", []):
        name = item.get("name", "")
        rank = item.get("rank", "")

        if "circuit_breaker" in name and rank in ("outdated", "deprecated", "dangerous"):
            breaker_name = name.split(":")[-1] if ":" in name else name
            item["actions"] = [{
                "type": "reset",
                "target": "circuit_breaker",
                "breaker_id": breaker_name,
                "label": "Reset Breaker",
            }]
        elif "retry_queue" in name and rank in ("outdated", "deprecated", "dangerous"):
            item["actions"] = [{
                "type": "clear",
                "target": "retry_queue",
                "label": "Clear Exhausted",
            }]

    # ── Platform — guide flags ─────────────────────────────────
    platform = pillars.get("platform", {})
    for item in platform.get("items", []):
        name = item.get("name", "")
        rank = item.get("rank", "")

        if rank in ("outdated", "deprecated", "dangerous"):
            # Platform items are named after distro/kernel/etc.
            # (e.g., "Ubuntu", "Kernel", "Debian", "CentOS")
            name_lower = name.lower()
            _platform_guide_names = {
                "ubuntu", "debian", "centos", "rhel", "fedora",
                "kernel", "glibc", "wsl",
            }
            if name_lower in _platform_guide_names or "os" in name_lower or "distro" in name_lower:
                item["actions"] = [{
                    "type": "guide",
                    "target": "os_upgrade",
                    "label": "Upgrade Guide",
                }]


def _manual_update_hint_simple(tool_id: str, recipe: dict) -> str:
    """Short manual update hint based on recipe install methods."""
    install_map = recipe.get("install", {})
    cli = recipe.get("cli", tool_id)

    if "pip" in install_map:
        return f"pip install --upgrade {cli}"
    if "npm" in install_map:
        return f"npm update -g {cli}"
    if "cargo" in install_map:
        return f"cargo install {cli}"
    if "brew" in install_map:
        return f"brew upgrade {cli}"
    if "apt" in install_map:
        return f"sudo apt update && sudo apt upgrade {cli}"

    return f"See official docs for {recipe.get('label', tool_id)}"


@posture_bp.route("/posture/summary")
def posture_summary():  # type: ignore[no-untyped-def]
    """Lightweight posture summary for the nav badge.

    Returns only overall rank and per-pillar ranks, without
    individual item details.  Designed for periodic polling
    (30s TTL in cache).

    Query params:
        bust=1  → Force rescan.

    Returns:
        200 with summary dict:
        - overall_rank, overall_status, overall_css_class
        - summary (human-readable string)
        - pillar_ranks: {platform, toolchain, project, runtime}
        - timestamp
    """
    force = request.args.get("bust", "") == "1"
    via = request.args.get("via", "")

    try:
        if via == "standalone":
            from src.core.services.system_posture import get_summary

            summary = get_summary(force=force)
            return jsonify(summary)
        else:
            # Default: use mediator (persisted, no TTL discard on load)
            from src.core.services.mediator import get_mediator

            m = get_mediator()
            if force:
                m.put("posture.summary", cascade=False)
            r = m.get("posture.summary", force=force)
            return jsonify(r["data"])
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@posture_bp.route("/posture/rescan", methods=["POST"])
def posture_rescan():  # type: ignore[no-untyped-def]
    """Force a full posture rescan.

    Invalidates all caches and runs a fresh scan.
    Returns the new full posture.
    """
    via = request.args.get("via", "")

    try:
        if via == "standalone":
            from src.core.services.system_posture import (
                invalidate_cache,
                scan_posture,
            )

            root = current_app.config.get("PROJECT_ROOT")
            invalidated = invalidate_cache()
            posture = scan_posture(force=True, project_root=root)
            result = posture.to_dict()
            _enrich_posture_actions(result)
            result["cache_invalidated"] = invalidated
        else:
            # Default: use mediator (persisted, cascade invalidation)
            from src.core.services.mediator import get_mediator

            m = get_mediator()
            inv = m.put("posture.full", cascade=True)
            r = m.get("posture.full", force=True)
            posture = r["data"]
            result = posture.to_dict()
            _enrich_posture_actions(result)
            result["cache_invalidated"] = inv["invalidated"]

        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@posture_bp.route("/posture/rescan-tool", methods=["POST"])
def posture_rescan_tool():  # type: ignore[no-untyped-def]
    """Lightweight single-tool cache invalidation.

    After updating one tool, invalidate only the toolchain and
    summary caches, then return the new summary for badge update.
    Much cheaper than a full rescan (~0.5s vs ~10s).

    Request body:
        {"tool": "go"}

    Returns:
        Fresh posture summary (same shape as ``/posture/summary``).
    """
    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "")
    via = request.args.get("via", "")

    try:
        if via == "standalone":
            from src.core.services.system_posture import (
                get_summary,
                invalidate_cache,
            )

            # Invalidate toolchain pillar + downstream (full, summary)
            invalidate_cache("toolchain")
            summary = get_summary(force=True)
            return jsonify(summary)
        else:
            # Default: use mediator (cascade invalidation → SSE push)
            from src.core.services.mediator import get_mediator

            m = get_mediator()
            m.put("posture.toolchain", cascade=True)
            r = m.get("posture.summary", force=True)
            return jsonify(r["data"])
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@posture_bp.route("/posture/cache")
def posture_cache():  # type: ignore[no-untyped-def]
    """Cache diagnostics for posture data.

    Returns per-key cache statistics:
    - age_s:     Seconds since last computation
    - ttl_s:     Configured TTL
    - fresh:     Whether the cached value is still within TTL
    - elapsed_s: How long the last computation took
    """
    from src.core.services.system_posture import cache_stats

    try:
        return jsonify(cache_stats())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
