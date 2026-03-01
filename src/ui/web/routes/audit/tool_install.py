"""
Tool install endpoints — install, resolve, check, version, status.

Routes registered on ``audit_bp`` from the parent package.

Endpoints:
    POST /audit/install-tool       — install a missing devops tool
    POST /audit/remediate          — remediation SSE stream
    POST /audit/check-deps         — check system packages
    POST /audit/resolve-choices    — get choices before install
    POST /audit/install-plan       — generate an ordered install plan
    GET  /tools/status             — centralized tool availability
    POST /audit/update-tool        — update installed tool
    POST /audit/check-updates      — check tools for version info
    POST /audit/tool-version       — get version of a single tool
    POST /audit/remove-tool        — remove an installed tool
"""

from __future__ import annotations

from pathlib import Path

from flask import current_app, jsonify, request

from src.core.services.devops import cache as devops_cache
from src.core.services.run_tracker import run_tracked
from src.core.services.tool_install.path_refresh import refresh_server_path as _refresh_server_path
from src.ui.web.helpers import bust_tool_caches

from . import audit_bp


@audit_bp.route("/audit/install-tool", methods=["POST"])
@run_tracked("install", "install:tool")
def audit_install_tool():
    """Install a missing devops tool."""
    from src.core.services.tool_install import install_tool

    body = request.get_json(silent=True) or {}
    result = install_tool(
        tool=body.get("tool", ""),
        cli=body.get("cli", ""),
        sudo_password=body.get("sudo_password", ""),
        override_command=body.get("override_command"),
    )

    # On successful install, bust server-side caches so status re-detects
    if result.get("ok") or result.get("already_installed"):
        bust_tool_caches()
        current_app.logger.info("Cache busted after installing %s", body.get("tool"))

    status = 200 if result.get("ok") or result.get("needs_sudo") or result.get("missing_dependency") or result.get("remediation") else 400
    return jsonify(result), status


@audit_bp.route("/audit/remediate", methods=["POST"])
def audit_remediate():
    """Execute a remediation action with streaming output (SSE)."""
    import json as _json
    import subprocess as _sp

    from flask import Response, stream_with_context

    body = request.get_json(silent=True) or {}
    cmd = body.get("override_command")
    tool = body.get("tool", "")
    sudo_password = body.get("sudo_password", "")

    if not cmd:
        return jsonify({"ok": False, "error": "No command provided"}), 400

    # Wrap with sudo if password provided
    if sudo_password:
        if isinstance(cmd, list):
            cmd = ["sudo", "-S"] + cmd
        else:
            cmd = f"sudo -S {cmd}"

    def generate():
        try:
            proc = _sp.Popen(
                cmd,
                stdin=_sp.PIPE if sudo_password else None,
                stdout=_sp.PIPE,
                stderr=_sp.STDOUT,
                text=True,
                bufsize=1,
            )
            if sudo_password:
                proc.stdin.write(sudo_password + "\n")
                proc.stdin.flush()
                proc.stdin.close()
            for line in proc.stdout:
                yield f"data: {_json.dumps({'line': line.rstrip()})}\n\n"
            proc.wait()

            ok = proc.returncode == 0
            yield f"data: {_json.dumps({'done': True, 'ok': ok, 'exit_code': proc.returncode})}\n\n"

            # Bust caches on success
            if ok:
                _refresh_server_path()
                bust_tool_caches()
        except Exception as exc:
            yield f"data: {_json.dumps({'done': True, 'ok': False, 'error': str(exc)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@audit_bp.route("/audit/check-deps", methods=["POST"])
def audit_check_deps():
    """Check if system packages are installed.

    Request body:
        {"packages": ["libssl-dev", "pkg-config"]}
        or with explicit pm:
        {"packages": ["openssl-devel"], "pkg_manager": "dnf"}

    If pkg_manager is not provided, auto-detects from system profile.
    """
    from src.core.services.tool_install import check_system_deps

    body = request.get_json(silent=True) or {}
    packages = body.get("packages", [])
    if not packages:
        return jsonify({"missing": [], "installed": []}), 200

    pkg_manager = body.get("pkg_manager")
    if not pkg_manager:
        from src.core.services.dev_overrides import resolve_system_profile
        os_info, _ = resolve_system_profile(current_app.config["PROJECT_ROOT"])
        pkg_manager = os_info.get("package_manager", {}).get("primary", "apt")

    result = check_system_deps(packages, pkg_manager)
    return jsonify(result), 200


@audit_bp.route("/audit/resolve-choices", methods=["POST"])
def audit_resolve_choices():
    """Pass 1 — Get choices the user must make before installing a tool.

    Request body:
        {"tool": "docker"}

    Response:
        Decision tree with choices, inputs, defaults, disabled options.
        If the tool has no choices, returns ``auto_resolve: true``.
    """
    from src.core.services.tool_install import resolve_choices
    from src.core.services.dev_overrides import resolve_system_profile

    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "").strip().lower()
    if not tool:
        return jsonify({"error": "No tool specified"}), 400

    system_profile, _ = resolve_system_profile(current_app.config["PROJECT_ROOT"])
    result = resolve_choices(tool, system_profile)

    status = 200 if not result.get("error") else 422
    return jsonify(result), status


@audit_bp.route("/audit/install-plan", methods=["POST"])
def audit_install_plan():
    """Generate an ordered install plan for a tool.

    Request body:
        {"tool": "cargo-outdated"}
        — or with choice answers (Phase 4 two-pass) —
        {"tool": "docker", "answers": {"variant": "docker-ce"}}

    Response:
        Plan dict with steps, or error if tool can't be installed.
    """
    from src.core.services.tool_install import (
        resolve_install_plan,
        resolve_install_plan_with_choices,
    )
    from src.core.services.dev_overrides import resolve_system_profile

    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "").strip().lower()
    if not tool:
        return jsonify({"error": "No tool specified"}), 400

    answers = body.get("answers", {})
    system_profile, _ = resolve_system_profile(current_app.config["PROJECT_ROOT"])

    if answers:
        plan = resolve_install_plan_with_choices(tool, system_profile, answers)
    else:
        plan = resolve_install_plan(tool, system_profile)

    status = 200 if not plan.get("error") else 422
    return jsonify(plan), status


@audit_bp.route("/tools/status")
def tools_status():
    """Centralized tool availability status.

    Returns all registered tools with availability, category,
    install type, and whether an install recipe exists.
    """
    _refresh_server_path()
    from src.core.services.audit.l0_detection import detect_tools
    from src.core.services.tool_install import TOOL_RECIPES

    tools = detect_tools()
    # Enrich with recipe availability
    for t in tools:
        tid = t["id"]
        recipe = TOOL_RECIPES.get(tid)
        t["has_recipe"] = recipe is not None
        t["needs_sudo"] = (
            any(recipe["needs_sudo"].values()) if recipe else False
        )

    available = sum(1 for t in tools if t["available"])
    missing = [t for t in tools if not t["available"]]

    return jsonify({
        "tools": tools,
        "total": len(tools),
        "available": available,
        "missing_count": len(missing),
        "missing": missing,
    })


# ── Update & version routes ─────────────────────────────────


@audit_bp.route("/audit/update-tool", methods=["POST"])
@run_tracked("install", "install:update")
def audit_update_tool():
    """Update an installed tool to its latest version.

    Request body:
        {"tool": "ruff", "sudo_password": "..."}

    Response:
        {"ok": true, "from_version": "...", "to_version": "..."}
    """
    from src.core.services.tool_install import update_tool

    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "").strip().lower()
    if not tool:
        return jsonify({"error": "No tool specified"}), 400

    result = update_tool(
        tool,
        sudo_password=body.get("sudo_password", ""),
    )

    # On success, bust server-side caches
    if result.get("ok"):
        bust_tool_caches()
        current_app.logger.info("Cache busted after updating %s", tool)

    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@audit_bp.route("/audit/check-updates", methods=["POST"])
def audit_check_updates():
    """Check installed tools for version info.

    Request body (optional):
        {"tools": ["ruff", "docker"]}

    Response:
        {"updates": [{"tool": "ruff", "installed": true, "version": "0.5.1", ...}]}
    """
    from src.core.services.tool_install import check_updates

    body = request.get_json(silent=True) or {}
    tools = body.get("tools")  # None = check all

    return jsonify({"updates": check_updates(tools)})


@audit_bp.route("/audit/tool-version", methods=["POST"])
def audit_tool_version():
    """Get version of a single installed tool.

    Request body:
        {"tool": "ruff"}

    Response:
        {"tool": "ruff", "version": "0.5.1"}
    """
    from src.core.services.tool_install import get_tool_version

    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "").strip().lower()
    if not tool:
        return jsonify({"error": "No tool specified"}), 400

    version = get_tool_version(tool)
    return jsonify({"tool": tool, "version": version})


# ── Tool Removal ───────────────────────────────────────────────

@audit_bp.route("/audit/remove-tool", methods=["POST"])
@run_tracked("install", "install:remove-tool")
def audit_remove_tool():
    """Remove an installed tool.

    Request body:
        {"tool": "cargo-audit", "sudo_password": "..."}

    Response:
        {"ok": true, "message": "cargo-audit removed"}
    """
    from src.core.services.tool_install import remove_tool

    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "").strip().lower()
    sudo_password = body.get("sudo_password", "")

    if not tool:
        return jsonify({"error": "No tool specified"}), 400

    result = remove_tool(tool, sudo_password=sudo_password)
    if result.get("ok"):
        # Bust caches after removal
        _refresh_server_path()
        bust_tool_caches()
        return jsonify({
            "ok": True,
            "message": f"{tool} removed",
        })
    else:
        return jsonify({
            "ok": False,
            "error": result.get("error", f"Failed to remove {tool}"),
        }), 500
