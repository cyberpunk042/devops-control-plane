"""
Offline cache, data packs, and service status endpoints.

Routes registered on ``audit_bp`` from the parent package.

Endpoints:
    POST /audit/install-plan/cache         — pre-download plan artifacts
    GET  /audit/install-cache/status       — cached artifact summary
    POST /audit/install-cache/clear        — clear cached artifacts
    POST /audit/install-cache/artifacts    — load cached artifact manifest
    POST /audit/data-status                — check data pack freshness
    GET  /audit/data-usage                 — disk usage of data packs
    POST /audit/service-status             — query system service status
"""

from __future__ import annotations

from flask import current_app, jsonify, request

from src.core.services.run_tracker import run_tracked

from . import audit_bp


# ── Offline Install Cache ──────────────────────────────────────


@audit_bp.route("/audit/install-plan/cache", methods=["POST"])
@run_tracked("install", "install:cache-plan")
def audit_cache_plan():
    """Pre-download plan artifacts for offline installation.

    Request body:
        {"tool": "cargo-audit", "answers": {}}

    Response:
        {"ok": true, "cached_count": 3, "total_size_mb": 12.3,
         "download_estimates": {"10 Mbps": "2s", ...}}
    """
    from src.core.services.dev_overrides import resolve_system_profile
    from src.core.services.tool_install import resolve_install_plan, resolve_install_plan_with_choices
    from src.core.services.tool_install.domain.download_helpers import _estimate_download_time
    from src.core.services.tool_install.execution.offline_cache import cache_plan

    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "").strip().lower()
    answers = body.get("answers", {})

    if not tool:
        return jsonify({"error": "No tool specified"}), 400

    system_profile, _ = resolve_system_profile(current_app.config["PROJECT_ROOT"])
    if answers:
        plan = resolve_install_plan_with_choices(tool, system_profile, answers)
    else:
        plan = resolve_install_plan(tool, system_profile)

    if plan.get("error"):
        return jsonify({"ok": False, "error": plan["error"]}), 400

    if plan.get("already_installed"):
        return jsonify({"ok": True, "already_installed": True, "message": f"{tool} is already installed"})

    result = cache_plan(plan)

    # Add download time estimate
    total_bytes = int(result.get("total_size_mb", 0) * 1024 * 1024)
    if total_bytes > 0:
        result["download_estimates"] = _estimate_download_time(total_bytes)

    return jsonify(result)


@audit_bp.route("/audit/install-cache/status", methods=["GET"])
def audit_cache_status():
    """Return summary of cached install artifacts.

    Response:
        {"cache_dir": "...", "tools": {"kubectl": {"files": 3, "size_mb": 12.3}},
         "total_size_mb": 45.6}
    """
    from src.core.services.tool_install.execution.offline_cache import cache_status

    return jsonify(cache_status())


@audit_bp.route("/audit/install-cache/clear", methods=["POST"])
def audit_cache_clear():
    """Clear cached artifacts for a tool or all tools.

    Request body:
        {"tool": "kubectl"}   — clear one tool
        {}                     — clear all

    Response:
        {"ok": true, "cleared": "kubectl"}
    """
    from src.core.services.tool_install.execution.offline_cache import clear_cache

    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "").strip().lower() or None

    return jsonify(clear_cache(tool=tool))


@audit_bp.route("/audit/install-cache/artifacts", methods=["POST"])
def audit_cache_artifacts():
    """Load cached artifact manifest for a tool.

    Request body:
        {"tool": "kubectl"}

    Response:
        {"step_id": {...artifact info...}} or null
    """
    from src.core.services.tool_install.execution.offline_cache import load_cached_artifacts

    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "").strip().lower()

    if not tool:
        return jsonify({"error": "No tool specified"}), 400

    artifacts = load_cached_artifacts(tool)
    return jsonify(artifacts or {})


# ── Data Packs ─────────────────────────────────────────────────


@audit_bp.route("/audit/data-status", methods=["POST"])
def audit_data_status():
    """Check freshness of a data pack.

    Request body:
        {"pack_id": "spacy-en-core-web-sm"}

    Response:
        {"stale": true, "schedule": "weekly", "age_seconds": 604900, ...}
    """
    from src.core.services.tool_install import check_data_freshness

    body = request.get_json(silent=True) or {}
    pack_id = body.get("pack_id", "").strip()
    if not pack_id:
        return jsonify({"error": "No pack_id specified"}), 400

    result = check_data_freshness(pack_id)
    return jsonify(result)


@audit_bp.route("/audit/data-usage")
def audit_data_usage():
    """Report disk usage of all known data pack directories.

    Response:
        {"packs": [{"type": "spacy", "path": "...", "size_bytes": N, "size_human": "1.2G"}, ...]}
    """
    from src.core.services.tool_install import get_data_pack_usage

    usage = get_data_pack_usage()
    return jsonify({"packs": usage, "total": len(usage)})


# ── Service Status ─────────────────────────────────────────────


@audit_bp.route("/audit/service-status", methods=["POST"])
def audit_service_status():
    """Query status of a system service.

    Request body:
        {"service": "docker"}

    Response (systemd):
        {"service": "docker", "init_system": "systemd", "active": true,
         "state": "active", "sub_state": "running", "loaded": true}

    Response (other/unknown init):
        {"service": "docker", "init_system": "...", "active": null, "state": "unknown"}
    """
    from src.core.services.tool_install import get_service_status

    body = request.get_json(silent=True) or {}
    service = body.get("service", "").strip()
    if not service:
        return jsonify({"error": "No service specified"}), 400

    result = get_service_status(service)
    return jsonify(result)
