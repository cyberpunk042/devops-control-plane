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
    """Recent audit scan activity (DevOps + Audit tab scans)."""
    from src.core.services import devops_cache

    n = request.args.get("n", 100, type=int)
    entries = devops_cache.load_activity(_project_root(), n=n)

    return jsonify({
        "total": len(entries),
        "entries": entries,
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

