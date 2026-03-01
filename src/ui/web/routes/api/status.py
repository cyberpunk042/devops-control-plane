"""API status — project status, detection, automation, health, capabilities."""

from __future__ import annotations

import logging
from pathlib import Path

from flask import current_app, jsonify, request

from src.ui.web.helpers import project_root as _project_root

from . import api_bp

logger = logging.getLogger(__name__)


def _config_path() -> Path | None:
    p = current_app.config.get("CONFIG_PATH")
    return Path(p) if p else None


@api_bp.route("/status")
def api_status():  # type: ignore[no-untyped-def]
    """Project status overview."""
    from src.core.use_cases.status import get_status

    config_path = _config_path()
    result = get_status(config_path=config_path)

    if result.error:
        return jsonify({"error": result.error}), 404

    return jsonify(result.to_dict())


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


@api_bp.route("/health")
def api_health():  # type: ignore[no-untyped-def]
    """System health status."""
    from src.core.observability.health import check_system_health

    health = check_system_health()
    return jsonify(health.to_dict())


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
