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
    from src.core.config.loader import find_project_file, load_project
    from src.core.persistence.state_file import default_state_path, load_state

    config_path = _config_path() or find_project_file(_project_root())
    if config_path is None:
        return jsonify({"error": "No project.yml found"}), 404

    project = load_project(config_path)
    state_path = default_state_path(_project_root())
    state = load_state(state_path)

    return jsonify({
        "project": {
            "name": project.name,
            "description": project.description,
            "repository": project.repository,
        },
        "modules": [
            {
                "name": m.name,
                "path": m.path,
                "domain": m.domain,
                "stack": m.stack,
            }
            for m in project.modules
        ],
        "environments": [
            {"name": e.name, "default": e.default}
            for e in project.environments
        ],
        "state": {
            "project_name": state.project_name,
            "last_operation": {
                "operation_id": state.last_operation.operation_id,
                "automation": state.last_operation.automation,
                "status": state.last_operation.status,
                "actions_total": state.last_operation.actions_total,
                "actions_succeeded": state.last_operation.actions_succeeded,
                "actions_failed": state.last_operation.actions_failed,
            },
            "modules": {
                name: {
                    "last_action_status": ms.last_action_status,
                    "last_action_at": ms.last_action_at,
                }
                for name, ms in state.modules.items()
            },
        },
    })


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
    from src.core.reliability.circuit_breaker import CircuitBreakerRegistry
    from src.core.reliability.retry_queue import RetryQueue

    cb_registry = CircuitBreakerRegistry()
    retry_path = _project_root() / "state" / "retry_queue.json"
    retry_q = RetryQueue(path=retry_path)

    health = check_system_health(
        cb_registry=cb_registry,
        retry_queue=retry_q,
    )

    return jsonify(health.to_dict())


# ── Audit Log ────────────────────────────────────────────────────────


@api_bp.route("/audit")
def api_audit():  # type: ignore[no-untyped-def]
    """Recent audit log entries."""
    from src.core.persistence.audit import AuditWriter

    n = request.args.get("n", 20, type=int)
    audit = AuditWriter(project_root=_project_root())
    entries = audit.read_recent(n)

    return jsonify({
        "total": audit.entry_count(),
        "entries": [e.model_dump(mode="json") for e in entries],
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
    """Capabilities resolved per module.

    Cross-references modules with their stacks and returns a
    map of capability → which modules support it and with what command.
    """
    from src.core.config.loader import find_project_file, load_project
    from src.core.config.stack_loader import discover_stacks
    from src.core.engine.executor import _resolve_stack

    config_path = _config_path() or find_project_file(_project_root())
    if config_path is None:
        return jsonify({"error": "No project.yml found"}), 404

    project = load_project(config_path)
    stacks_dir = _project_root() / "stacks"
    stacks = discover_stacks(stacks_dir)

    # Build capability → module mapping
    capabilities: dict[str, dict] = {}

    for m in project.modules:
        stack_name = m.stack or ""
        stack = _resolve_stack(stack_name, stacks) if stack_name else None
        if stack is None:
            continue

        for cap in stack.capabilities:
            if cap.name not in capabilities:
                capabilities[cap.name] = {
                    "name": cap.name,
                    "description": cap.description,
                    "modules": [],
                }
            capabilities[cap.name]["modules"].append({
                "module": m.name,
                "stack": stack.name,
                "command": cap.command,
                "adapter": cap.adapter or "shell",
            })

    return jsonify(capabilities)

