"""
API routes — REST endpoints for the web admin.

All endpoints return JSON. Grouped under /api/ prefix.
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__)


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


def _config_path() -> Path | None:
    p = current_app.config.get("CONFIG_PATH")
    return Path(p) if p else None


# ── Status ───────────────────────────────────────────────────────────


@api_bp.route("/status")
def api_status():  # type: ignore[no-untyped-def]
    """Project status overview."""
    from src.core.use_cases.status import get_status

    config_path = _config_path()
    result = get_status(config_path=config_path)

    if result.error:
        return jsonify({"error": result.error}), 404

    return jsonify(result.to_dict())


# ── Detection ────────────────────────────────────────────────────────


@api_bp.route("/detect", methods=["POST"])
def api_detect():  # type: ignore[no-untyped-def]
    """Run module detection."""
    from src.core.use_cases.detect import run_detect

    result = run_detect(
        config_path=_config_path(),
        save=True,
    )

    if result.error:
        return jsonify({"error": result.error}), 400

    return jsonify(result.to_dict())


# ── Run Automation ───────────────────────────────────────────────────


@api_bp.route("/run", methods=["POST"])
def api_run():  # type: ignore[no-untyped-def]
    """Execute an automation capability."""
    from src.core.use_cases.run import run_automation

    data = request.get_json(silent=True) or {}
    capability = data.get("capability", "")
    if not capability:
        return jsonify({"error": "Missing 'capability' field"}), 400

    modules = data.get("modules")
    environment = data.get("environment", "dev")
    dry_run = data.get("dry_run", False)
    mock_mode = data.get("mock", current_app.config.get("MOCK_MODE", False))

    result = run_automation(
        capability=capability,
        config_path=_config_path(),
        modules=modules,
        environment=environment,
        dry_run=dry_run,
        mock_mode=mock_mode,
    )

    if result.error:
        return jsonify({"error": result.error}), 400

    return jsonify(result.to_dict())


# ── Health ───────────────────────────────────────────────────────────


@api_bp.route("/health")
def api_health():  # type: ignore[no-untyped-def]
    """System health status."""
    from src.core.observability.health import check_system_health

    health = check_system_health()
    return jsonify(health.to_dict())


# ── Audit Log ────────────────────────────────────────────────────────


@api_bp.route("/audit")
def api_audit():  # type: ignore[no-untyped-def]
    """Recent audit log entries (CLI operations from audit.ndjson)."""
    from src.core.persistence.audit import AuditWriter

    n = request.args.get("n", 20, type=int)
    audit = AuditWriter(project_root=_project_root())
    entries = audit.read_recent(n)

    return jsonify({
        "total": audit.entry_count(),
        "entries": [e.model_dump(mode="json") for e in entries],
    })


@api_bp.route("/audit/activity")
def api_audit_activity():  # type: ignore[no-untyped-def]
    """Recent audit scan activity (DevOps + Audit tab scans).

    Query params:
        offset  — skip first N entries (newest-first), default 0
        limit   — max entries to return, default 50
        card    — filter by card type (e.g. "vault", "content")
        q       — text search in label + summary + target fields
        n       — (legacy) alias for limit, kept for backward compat
    """
    from src.core.services import devops_cache

    # Load all entries (they're stored oldest-first on disk)
    n_legacy = request.args.get("n", 0, type=int)
    all_entries = devops_cache.load_activity(
        _project_root(), n=max(n_legacy, 2000)
    )
    total_all = len(all_entries)

    # Reverse to newest-first for the UI
    all_entries = list(reversed(all_entries))

    # ── Filtering ────────────────────────────────────────────────
    card_filter = request.args.get("card", "", type=str).strip()
    search_q = request.args.get("q", "", type=str).strip().lower()

    filtered = all_entries
    if card_filter:
        filtered = [e for e in filtered if e.get("card") == card_filter]
    if search_q:
        def _matches(entry: dict) -> bool:
            for field in ("label", "summary", "target", "card"):
                val = entry.get(field, "")
                if val and search_q in str(val).lower():
                    return True
            return False
        filtered = [e for e in filtered if _matches(e)]

    total_filtered = len(filtered)

    # ── Pagination ───────────────────────────────────────────────
    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", n_legacy or 50, type=int)
    page = filtered[offset : offset + limit]

    # ── Distinct card types for filter dropdown ──────────────────
    cards_seen: list[str] = []
    cards_set: set[str] = set()
    for e in all_entries:
        c = e.get("card", "")
        if c and c not in cards_set:
            cards_seen.append(c)
            cards_set.add(c)

    return jsonify({
        "total_all": total_all,
        "total_filtered": total_filtered,
        "offset": offset,
        "limit": limit,
        "has_more": (offset + limit) < total_filtered,
        "cards": sorted(cards_seen),
        "entries": page,
    })


# ── Stacks ───────────────────────────────────────────────────────────


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


# ── Capabilities (resolved per-module) ───────────────────────────────


@api_bp.route("/capabilities")
def api_capabilities():  # type: ignore[no-untyped-def]
    """Capabilities resolved per module."""
    from src.core.use_cases.status import get_capabilities

    result = get_capabilities(
        config_path=_config_path(),
        project_root=_project_root(),
    )

    if "error" in result:
        return jsonify(result), 404

    return jsonify(result)

