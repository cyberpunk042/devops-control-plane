"""
Audit API routes — serve analysis data for the Audit tab.

All endpoints use server-side caching via devops_cache.
L0/L1 endpoints auto-load. L2/L3 endpoints are on-demand.
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import devops_cache
from src.core.services.audit import (
    audit_scores,
    audit_scores_enriched,
    l0_system_profile,
    l1_clients,
    l1_dependencies,
    l1_structure,
    l2_quality,
    l2_repo,
    l2_risks,
    l2_structure,
)
from src.core.services.run_tracker import run_tracked

audit_bp = Blueprint("audit", __name__, url_prefix="/api")


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


def _refresh_server_path() -> None:
    """Ensure common tool-install directories are at the FRONT of PATH.

    After installing tools (e.g. rustup → ~/.cargo/bin, pip → ~/.local/bin),
    the server process's os.environ['PATH'] may be stale because it was
    inherited at startup.  Even if the dir is already on PATH, it may be
    after /usr/bin, so shutil.which() finds the older system binary first.

    This prepends known directories to the front (if they exist on disk),
    mirroring what ``source ~/.cargo/env`` does in a new shell.
    """
    import os
    home = Path.home()
    # Order matters: first entry wins in PATH lookup
    candidates = [
        home / ".cargo" / "bin",
        home / ".local" / "bin",
        home / "go" / "bin",
        home / ".nvm" / "current" / "bin",       # nvm symlink
        Path("/usr/local/go/bin"),
        Path("/snap/bin"),
    ]
    current = os.environ.get("PATH", "")
    dirs = current.split(os.pathsep)

    # Build new PATH: known tool dirs first, then everything else (deduped)
    front: list[str] = []
    for d in candidates:
        s = str(d)
        if d.is_dir() and s not in front:
            front.append(s)

    if not front:
        return

    # Remove duplicates from the rest of PATH
    seen = set(front)
    rest = []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            rest.append(d)

    os.environ["PATH"] = os.pathsep.join(front + rest)


# ── L0: System Profile ─────────────────────────────────────────

@audit_bp.route("/audit/system")
def audit_system():
    root = _project_root()
    bust = "bust" in request.args
    deep = "deep" in request.args

    if deep:
        # Deep tier: separate cache key, longer compute budget
        result = devops_cache.get_cached(
            root, "audit:system:deep",
            lambda: l0_system_profile(root, deep=True),
            force=bust,
        )
    else:
        # Fast tier: original behavior, unchanged
        result = devops_cache.get_cached(
            root, "audit:system",
            lambda: l0_system_profile(root),
            force=bust,
        )
    return jsonify(result)


# ── L1: Dependencies & Libraries ───────────────────────────────

@audit_bp.route("/audit/dependencies")
def audit_dependencies():
    root = _project_root()
    bust = "bust" in request.args
    result = devops_cache.get_cached(
        root, "audit:deps",
        lambda: l1_dependencies(root),
        force=bust,
    )
    return jsonify(result)


# ── L1: Structure & Modules ────────────────────────────────────

@audit_bp.route("/audit/structure")
def audit_structure():
    root = _project_root()
    bust = "bust" in request.args
    result = devops_cache.get_cached(
        root, "audit:structure",
        lambda: l1_structure(root),
        force=bust,
    )
    return jsonify(result)


# ── L1: Clients & Services ─────────────────────────────────────

@audit_bp.route("/audit/clients")
def audit_clients():
    root = _project_root()
    bust = "bust" in request.args
    result = devops_cache.get_cached(
        root, "audit:clients",
        lambda: l1_clients(root),
        force=bust,
    )
    return jsonify(result)


# ── Scores ──────────────────────────────────────────────────────

@audit_bp.route("/audit/scores")
def audit_scores_endpoint():
    root = _project_root()
    bust = "bust" in request.args
    result = devops_cache.get_cached(
        root, "audit:scores",
        lambda: audit_scores(root),
        force=bust,
    )
    return jsonify(result)


@audit_bp.route("/audit/scores/enriched")
def audit_scores_enriched_endpoint():
    """L2-enriched master scores — uses full L2 analysis.

    On-demand — takes 5-25s total. Results are cached.
    """
    root = _project_root()
    bust = "bust" in request.args
    result = devops_cache.get_cached(
        root, "audit:scores:enriched",
        lambda: audit_scores_enriched(root),
        force=bust,
    )
    return jsonify(result)


@audit_bp.route("/audit/scores/history")
def audit_scores_history():
    """Score history — last N snapshots for trend rendering."""
    from src.core.services.audit.scoring import _load_history
    root = _project_root()
    history = _load_history(root)
    return jsonify({"history": history, "total": len(history)})


# ── L2: Structure Analysis (on-demand) ─────────────────────────

@audit_bp.route("/audit/structure-analysis")
def audit_structure_analysis():
    """L2: Import graph, module boundaries, cross-module deps.

    On-demand — typically takes 1-5s. Results are cached.
    """
    root = _project_root()
    bust = "bust" in request.args
    result = devops_cache.get_cached(
        root, "audit:l2:structure",
        lambda: l2_structure(root),
        force=bust,
    )
    return jsonify(result)


# ── L2: Code Health (on-demand) ────────────────────────────────

@audit_bp.route("/audit/code-health")
def audit_code_health():
    """L2: Code quality metrics — health scores, hotspots, naming.

    On-demand — typically takes 1-5s. Results are cached.
    """
    root = _project_root()
    bust = "bust" in request.args
    result = devops_cache.get_cached(
        root, "audit:l2:quality",
        lambda: l2_quality(root),
        force=bust,
    )
    return jsonify(result)


# ── L2: Repo Health (on-demand) ────────────────────────────────

@audit_bp.route("/audit/repo")
def audit_repo_health():
    """L2: Repository health — git objects, history, large files.

    On-demand — typically takes 1-3s. Results are cached.
    """
    root = _project_root()
    bust = "bust" in request.args
    result = devops_cache.get_cached(
        root, "audit:l2:repo",
        lambda: l2_repo(root),
        force=bust,
    )
    return jsonify(result)


# ── L2: Risks & Issues (on-demand) ─────────────────────────────

@audit_bp.route("/audit/risks")
def audit_risks():
    """L2: Risk aggregation — security, deps, docs, testing, infra.

    On-demand — typically takes 2-8s (calls multiple ops services).
    Results are cached.
    """
    root = _project_root()
    bust = "bust" in request.args
    result = devops_cache.get_cached(
        root, "audit:l2:risks",
        lambda: l2_risks(root),
        force=bust,
    )
    return jsonify(result)


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
        try:
            root = Path(current_app.config["PROJECT_ROOT"])
            devops_cache.invalidate_scope(root, "integrations")
            devops_cache.invalidate_scope(root, "devops")
            devops_cache.invalidate(root, "wiz:detect")
            current_app.logger.info("Cache busted after installing %s", body.get("tool"))
        except Exception as exc:
            current_app.logger.warning("Failed to bust cache after install: %s", exc)

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
                try:
                    root = Path(current_app.config["PROJECT_ROOT"])
                    devops_cache.invalidate_scope(root, "integrations")
                    devops_cache.invalidate_scope(root, "devops")
                    devops_cache.invalidate(root, "wiz:detect")
                except Exception:
                    pass
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
        from src.core.services.audit.l0_detection import _detect_os
        os_info = _detect_os()
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
    from src.core.services.audit.l0_detection import _detect_os

    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "").strip().lower()
    if not tool:
        return jsonify({"error": "No tool specified"}), 400

    system_profile = _detect_os()
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
    from src.core.services.audit.l0_detection import _detect_os

    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "").strip().lower()
    if not tool:
        return jsonify({"error": "No tool specified"}), 400

    answers = body.get("answers", {})
    system_profile = _detect_os()

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


# ── Audit Staging (pending snapshots) ───────────────────────────


@audit_bp.route("/audits/pending")
def audits_pending():
    """List all unsaved audit snapshots (metadata only, no data blobs)."""
    from src.core.services.audit_staging import list_pending

    return jsonify({"pending": list_pending(_project_root())})


@audit_bp.route("/audits/pending/<snapshot_id>")
def audits_pending_detail(snapshot_id):
    """Full detail for a single pending audit (includes data blob)."""
    from src.core.services.audit_staging import get_pending

    result = get_pending(_project_root(), snapshot_id)
    if result is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(result)


@audit_bp.route("/audits/save", methods=["POST"])
def audits_save():
    """Save pending snapshots to the git ledger.

    Body: ``{"snapshot_ids": ["id1", "id2"]}`` or ``{"snapshot_ids": "all"}``
    """
    from src.core.services.audit_staging import save_audit, save_all_pending

    body = request.get_json(silent=True) or {}
    ids = body.get("snapshot_ids", "all")

    if ids == "all":
        saved = save_all_pending(_project_root())
    else:
        saved = []
        for sid in ids:
            try:
                save_audit(_project_root(), sid)
                saved.append(sid)
            except (ValueError, Exception):
                pass  # skip missing/failed — log is handled in audit_staging

    return jsonify({"saved": saved, "count": len(saved)})


@audit_bp.route("/audits/discard", methods=["POST"])
def audits_discard():
    """Discard pending snapshots (cache unaffected).

    Body: ``{"snapshot_ids": ["id1", "id2"]}`` or ``{"snapshot_ids": "all"}``
    """
    from src.core.services.audit_staging import discard_audit, discard_all_pending

    body = request.get_json(silent=True) or {}
    ids = body.get("snapshot_ids", "all")

    if ids == "all":
        count = discard_all_pending(_project_root())
    else:
        count = sum(1 for sid in ids if discard_audit(_project_root(), sid))

    return jsonify({"discarded": count})


@audit_bp.route("/audits/saved")
def audits_saved():
    """List saved audit snapshots from the git ledger (metadata only)."""
    from src.core.services.ledger.ledger_ops import list_saved_audits

    return jsonify({"saved": list_saved_audits(_project_root())})


@audit_bp.route("/audits/saved/<snapshot_id>")
def audits_saved_detail(snapshot_id):
    """Return the full saved audit snapshot (including data blob)."""
    from src.core.services.ledger.ledger_ops import get_saved_audit

    snap = get_saved_audit(_project_root(), snapshot_id)
    if snap is None:
        return jsonify({"error": f"Saved audit not found: {snapshot_id}"}), 404
    return jsonify(snap)


@audit_bp.route("/audits/saved/<snapshot_id>", methods=["DELETE"])
def audits_saved_delete(snapshot_id):
    """Delete a saved audit snapshot from the ledger branch."""
    from src.core.services.ledger.ledger_ops import delete_saved_audit

    try:
        deleted = delete_saved_audit(_project_root(), snapshot_id)
        if not deleted:
            return jsonify({"error": f"Saved audit not found: {snapshot_id}"}), 404
        return jsonify({"deleted": snapshot_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Phase 2.5: Update & version routes ─────────────────────────


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
        try:
            root = Path(current_app.config["PROJECT_ROOT"])
            devops_cache.invalidate_scope(root, "integrations")
            devops_cache.invalidate_scope(root, "devops")
            devops_cache.invalidate(root, "wiz:detect")
            current_app.logger.info("Cache busted after updating %s", tool)
        except Exception as exc:
            current_app.logger.warning("Failed to bust cache after update: %s", exc)

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


# ── Deep system detection (on-demand) ──────────────────────────


@audit_bp.route("/audit/system/deep-detect", methods=["POST"])
def audit_deep_detect():
    """Run deep system detection (GPU, kernel, hardware, build tools, network).

    This is the "deep tier" — takes ~2s, called on-demand before
    provisioning flows that need hardware/network info.

    Request body:
        {"checks": ["gpu", "hardware", "kernel", "build", "network", "environment"]}
        If empty, runs all checks.

    Response:
        {"gpu": {...}, "hardware": {...}, "kernel": {...},
         "build_toolchain": {...}, "network": {...}, "environment": {...}}
    """
    from src.core.services.tool_install import (
        detect_build_toolchain,
        detect_gpu,
        detect_kernel,
    )
    from src.core.services.tool_install.detection.environment import (
        detect_cpu_features,
        detect_nvm,
        detect_sandbox,
    )
    from src.core.services.tool_install.detection.hardware import detect_hardware
    from src.core.services.tool_install.detection.network import (
        check_all_registries,
        detect_proxy,
    )

    body = request.get_json(silent=True) or {}
    checks = body.get("checks", [])
    run_all = not checks

    result: dict = {}

    if run_all or "gpu" in checks:
        try:
            gpu_info = detect_gpu()
            # Auto-check CUDA/driver compat when both are available
            from src.core.services.tool_install.detection.hardware import check_cuda_driver_compat
            nvidia = gpu_info.get("nvidia", {})
            if nvidia.get("cuda_version") and nvidia.get("driver_version"):
                compat = check_cuda_driver_compat(
                    nvidia["cuda_version"],
                    nvidia["driver_version"],
                )
                gpu_info["cuda_driver_compat"] = compat
            result["gpu"] = gpu_info
        except Exception as exc:
            result["gpu"] = {"error": str(exc)}

    if run_all or "hardware" in checks:
        try:
            result["hardware"] = detect_hardware()
        except Exception as exc:
            result["hardware"] = {"error": str(exc)}

    if run_all or "kernel" in checks:
        try:
            result["kernel"] = detect_kernel()
        except Exception as exc:
            result["kernel"] = {"error": str(exc)}

    if run_all or "build" in checks:
        try:
            result["build_toolchain"] = detect_build_toolchain()
        except Exception as exc:
            result["build_toolchain"] = {"error": str(exc)}

    if run_all or "network" in checks:
        try:
            result["network"] = {
                "registries": check_all_registries(timeout=3),
                "proxy": detect_proxy(),
            }
            # Add Alpine community repo check if applicable
            from src.core.services.tool_install.detection.network import check_alpine_community_repo
            alpine_check = check_alpine_community_repo()
            if alpine_check.get("is_alpine"):
                result["network"]["alpine_community"] = alpine_check
        except Exception as exc:
            result["network"] = {"error": str(exc)}

    if run_all or "environment" in checks:
        try:
            result["environment"] = {
                "nvm": detect_nvm(),
                "sandbox": detect_sandbox(),
                "cpu_features": detect_cpu_features(),
            }
        except Exception as exc:
            result["environment"] = {"error": str(exc)}

    return jsonify(result)


# ── Phase 3: Plan execution ───────────────────────────────────


@audit_bp.route("/audit/install-plan/execute-sync", methods=["POST"])
@run_tracked("install", "install:execute-plan-sync")
def audit_execute_plan_sync():
    """Execute an install plan synchronously (non-streaming).

    For CLI callers and batch operations. Returns a single JSON
    response when all steps are complete — no SSE stream.

    Request body:
        {"tool": "cargo-audit", "sudo_password": "...", "answers": {}}

    Response:
        {"ok": true, "tool": "cargo-audit", "steps_completed": 3, ...}
        or
        {"ok": false, "error": "...", "step": 1, ...}
    """
    from src.core.services.audit.l0_detection import _detect_os
    from src.core.services.tool_install import (
        resolve_install_plan,
        resolve_install_plan_with_choices,
    )
    from src.core.services.tool_install.orchestration.orchestrator import execute_plan

    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "").strip().lower()
    sudo_password = body.get("sudo_password", "")
    answers = body.get("answers", {})

    if not tool:
        return jsonify({"error": "No tool specified"}), 400

    _refresh_server_path()
    system_profile = _detect_os()

    if answers:
        plan = resolve_install_plan_with_choices(tool, system_profile, answers)
    else:
        plan = resolve_install_plan(tool, system_profile)

    if plan.get("error"):
        return jsonify({"ok": False, "error": plan["error"]}), 400

    if plan.get("already_installed"):
        return jsonify({
            "ok": True,
            "already_installed": True,
            "message": f"{tool} is already installed",
            "version_installed": plan.get("version_installed"),
        })

    result = execute_plan(plan, sudo_password=sudo_password)

    if result.get("ok"):
        _refresh_server_path()
        try:
            root = Path(current_app.config["PROJECT_ROOT"])
            devops_cache.invalidate_scope(root, "integrations")
            devops_cache.invalidate_scope(root, "devops")
            devops_cache.invalidate(root, "wiz:detect")
        except Exception:
            pass

    return jsonify(result)


@audit_bp.route("/audit/install-plan/execute", methods=["POST"])
@run_tracked("install", "install:execute-plan")
def audit_execute_plan():
    """Execute an install plan with SSE streaming.

    Resolves a plan for the requested tool, then executes each step
    in order, streaming progress events to the client.

    Request body:
        {"tool": "cargo-audit", "sudo_password": "...", "answers": {}}

    SSE events:
        {"type": "step_start", "step": 0, "label": "..."}
        {"type": "log", "step": 0, "line": "..."}
        {"type": "step_done", "step": 0}
        {"type": "step_failed", "step": 0, "error": "..."}
        {"type": "done", "ok": true, "message": "..."}
        {"type": "done", "ok": false, "error": "..."}
    """
    import json as _json
    import os as _os

    from flask import Response, stream_with_context

    from src.core.services.audit.l0_detection import _detect_os
    from src.core.services.tool_install import (
        execute_plan_dag,
        execute_plan_step,
        resolve_install_plan,
        resolve_install_plan_with_choices,
        save_plan_state,
    )

    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "").strip().lower()
    sudo_password = body.get("sudo_password", "")
    answers = body.get("answers", {})

    if not tool:
        return jsonify({"error": "No tool specified"}), 400

    # Refresh PATH before resolving — picks up tools installed by
    # previous remediations (e.g. rustup → ~/.cargo/bin) so the
    # resolver finds the correct binary versions.
    _refresh_server_path()

    # Resolve the plan — use answers if provided (Phase 4)
    system_profile = _detect_os()
    if answers:
        plan = resolve_install_plan_with_choices(tool, system_profile, answers)
    else:
        plan = resolve_install_plan(tool, system_profile)

    if plan.get("error"):
        return jsonify({"ok": False, "error": plan["error"]}), 400

    if plan.get("already_installed"):
        return jsonify({
            "ok": True,
            "already_installed": True,
            "message": f"{tool} is already installed",
        })

    steps = plan.get("steps", [])

    # ── Pre-flight: network reachability for required registries ──
    from src.core.services.tool_install.detection.network import (
        check_registry_reachable,
        detect_proxy,
    )

    # Infer required registries from step commands
    _needed_registries: set[str] = set()
    for s in steps:
        cmd_str = " ".join(s.get("command", []))
        if "pip " in cmd_str or "pip3 " in cmd_str:
            _needed_registries.add("pypi")
        elif "cargo " in cmd_str:
            _needed_registries.add("crates")
        elif "npm " in cmd_str:
            _needed_registries.add("npm")
        elif "curl " in cmd_str or "wget " in cmd_str:
            _needed_registries.add("github")

    network_warnings: list[dict] = []
    if _needed_registries:
        proxy_info = detect_proxy()
        for reg in _needed_registries:
            result = check_registry_reachable(reg, timeout=3)
            if not result.get("reachable"):
                warning = {
                    "registry": reg,
                    "url": result.get("url", ""),
                    "error": result.get("error", "unreachable"),
                }
                if proxy_info.get("has_proxy"):
                    warning["proxy_detected"] = True
                network_warnings.append(warning)

    # Generate plan_id for state tracking
    import uuid as _uuid_mod
    plan_id = str(_uuid_mod.uuid4())

    def _sse(data: dict) -> str:
        return f"data: {_json.dumps(data)}\n\n"

    # ── Detect DAG-shaped plans ──────────────────────────────
    is_dag = any(step.get("depends_on") for step in steps)

    if is_dag:
        # DAG execution: bridge callback → SSE via queue
        import queue
        import threading

        # Attach plan_id to plan dict for DAG executor's state saves
        plan["plan_id"] = plan_id

        # Build step index by id for progress events
        step_idx = {s.get("id", f"step_{i}"): i for i, s in enumerate(steps)}

        event_queue: queue.Queue = queue.Queue()

        def _on_progress(step_id: str, status: str) -> None:
            """DAG executor callback → push event to queue."""
            idx = step_idx.get(step_id, 0)
            if status == "started":
                event_queue.put({
                    "type": "step_start", "step": idx,
                    "label": steps[idx].get("label", step_id) if idx < len(steps) else step_id,
                    "total": len(steps),
                })
            elif status == "done":
                event_queue.put({"type": "step_done", "step": idx})
            elif status == "failed":
                event_queue.put({
                    "type": "step_failed", "step": idx,
                    "error": f"Step '{step_id}' failed",
                })
            elif status == "skipped":
                event_queue.put({
                    "type": "step_done", "step": idx,
                    "skipped": True, "message": "Dependency failed",
                })

        def _run_dag() -> None:
            """Execute DAG in background thread."""
            try:
                result = execute_plan_dag(
                    plan, sudo_password=sudo_password,
                    on_progress=_on_progress,
                )
                event_queue.put(("__done__", result))
            except Exception as exc:
                event_queue.put(("__done__", {
                    "ok": False, "error": str(exc),
                }))

        thread = threading.Thread(target=_run_dag, daemon=True)
        thread.start()

        def generate_dag():
            while True:
                event = event_queue.get()
                if isinstance(event, tuple) and event[0] == "__done__":
                    # Final result from DAG executor
                    result = event[1]
                    # Bust caches
                    try:
                        root = Path(current_app.config["PROJECT_ROOT"])
                        devops_cache.invalidate_scope(root, "integrations")
                        devops_cache.invalidate_scope(root, "devops")
                        devops_cache.invalidate(root, "wiz:detect")
                    except Exception:
                        pass
                    yield _sse({
                        "type": "done",
                        "ok": result.get("ok", False),
                        "plan_id": plan_id,
                        "message": f"{tool} installed successfully"
                            if result.get("ok") else result.get("error", "DAG execution failed"),
                        "paused": result.get("paused", False),
                        "pause_reason": result.get("pause_reason"),
                    })
                    return
                else:
                    yield _sse(event)

        return Response(
            stream_with_context(generate_dag()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── Linear execution (original path) ─────────────────────
    def generate():
        env_overrides: dict[str, str] = {}
        post_env = plan.get("post_env", {})
        completed_steps: list[int] = []

        # Emit network warnings before starting execution
        for nw in network_warnings:
            yield _sse({
                "type": "network_warning",
                "registry": nw["registry"],
                "url": nw.get("url", ""),
                "error": nw.get("error", ""),
                "proxy_detected": nw.get("proxy_detected", False),
            })

        for i, step in enumerate(steps):
            step_label = step.get("label", f"Step {i + 1}")
            step_type = step.get("type", "tool")

            yield _sse({
                "type": "step_start",
                "step": i,
                "label": step_label,
                "total": len(steps),
            })

            # Accumulate env overrides from post_env after tool steps
            if step_type == "tool" and post_env:
                for key, val in post_env.items():
                    env_overrides[key] = _os.path.expandvars(val)

            # ── Execute step ──
            # For tool/post_install steps: stream output live via Popen
            # For other step types: use blocking executor (fast steps)
            if step_type in ("tool", "post_install"):
                from src.core.services.tool_install.execution.subprocess_runner import (
                    _run_subprocess_streaming,
                )
                cmd = step.get("command", [])
                if not cmd:
                    yield _sse({"type": "step_failed", "step": i, "error": "No command"})
                    yield _sse({"type": "done", "ok": False, "plan_id": plan_id, "error": "Empty command"})
                    return

                result = None
                try:
                    for chunk in _run_subprocess_streaming(
                        cmd,
                        needs_sudo=step.get("needs_sudo", False),
                        sudo_password=sudo_password,
                        timeout=step.get("timeout", 300),
                        env_overrides=env_overrides if env_overrides else None,
                    ):
                        if chunk.get("done"):
                            result = chunk
                        elif "line" in chunk:
                            yield _sse({"type": "log", "step": i, "line": chunk["line"]})
                except Exception as exc:
                    result = {"ok": False, "error": str(exc)}

                if result is None:
                    result = {"ok": False, "error": "No result from subprocess"}

            else:
                # Non-streaming steps (packages, verify, repo_setup, etc.)
                try:
                    result = execute_plan_step(
                        step,
                        sudo_password=sudo_password,
                        env_overrides=env_overrides if env_overrides else None,
                    )
                except Exception as exc:
                    # Save interrupted state
                    try:
                        save_plan_state({
                            "plan_id": plan_id,
                            "tool": tool,
                            "status": "failed",
                            "current_step": i,
                            "completed_steps": completed_steps,
                            "steps": [dict(s) for s in steps],
                        })
                    except Exception:
                        pass
                    yield _sse({
                        "type": "step_failed",
                        "step": i,
                        "error": str(exc),
                    })
                    yield _sse({
                        "type": "done",
                        "ok": False,
                        "plan_id": plan_id,
                        "error": f"Step {i + 1} crashed: {exc}",
                    })
                    return

                # Emit captured stdout as log lines (for non-streaming steps)
                stdout = result.get("stdout", "")
                if stdout:
                    for line in stdout.splitlines():
                        yield _sse({"type": "log", "step": i, "line": line})

                stderr_out = result.get("stderr", "")
                if stderr_out and not result.get("ok"):
                    for line in stderr_out.splitlines()[-10:]:
                        yield _sse({"type": "log", "step": i, "line": line})

            if result.get("skipped"):
                completed_steps.append(i)
                yield _sse({
                    "type": "step_done",
                    "step": i,
                    "skipped": True,
                    "message": result.get("message", "Already satisfied"),
                })
                continue

            if result.get("ok"):
                completed_steps.append(i)
                # Persist progress after each successful step
                try:
                    save_plan_state({
                        "plan_id": plan_id,
                        "tool": tool,
                        "status": "running",
                        "current_step": i,
                        "completed_steps": completed_steps,
                        "steps": [dict(s) for s in steps],
                    })
                except Exception:
                    pass
                yield _sse({
                    "type": "step_done",
                    "step": i,
                    "elapsed_ms": result.get("elapsed_ms"),
                })
            else:
                # Save failed state
                try:
                    save_plan_state({
                        "plan_id": plan_id,
                        "tool": tool,
                        "status": "failed",
                        "current_step": i,
                        "completed_steps": completed_steps,
                        "steps": [dict(s) for s in steps],
                    })
                except Exception:
                    pass

                # Check for sudo needed
                if result.get("needs_sudo"):
                    yield _sse({
                        "type": "step_failed",
                        "step": i,
                        "error": result.get("error", "Sudo required"),
                        "needs_sudo": True,
                    })
                    yield _sse({
                        "type": "done",
                        "ok": False,
                        "plan_id": plan_id,
                        "error": result.get("error", "Sudo required"),
                        "needs_sudo": True,
                    })
                    return

                yield _sse({
                    "type": "step_failed",
                    "step": i,
                    "error": result.get("error", "Step failed"),
                })

                # ── Remediation analysis ──
                remediation = None
                if step_type in ("tool", "post_install"):
                    from src.core.services.tool_install.detection.install_failure import (
                        _analyse_install_failure,
                    )
                    remediation = _analyse_install_failure(
                        tool,
                        plan.get("cli", tool),
                        result.get("stderr", ""),
                    )

                done_event: dict = {
                    "type": "done",
                    "ok": False,
                    "plan_id": plan_id,
                    "error": result.get("error", f"Step {i + 1} failed"),
                    "step": i,
                    "step_label": step_label,
                }
                if remediation:
                    done_event["remediation"] = remediation
                yield _sse(done_event)
                return

        # All steps done — mark plan complete and bust caches
        try:
            save_plan_state({
                "plan_id": plan_id,
                "tool": tool,
                "status": "done",
                "completed_steps": completed_steps,
                "steps": [dict(s) for s in steps],
            })
        except Exception:
            pass

        _refresh_server_path()
        try:
            root = Path(current_app.config["PROJECT_ROOT"])
            devops_cache.invalidate_scope(root, "integrations")
            devops_cache.invalidate_scope(root, "devops")
            devops_cache.invalidate(root, "wiz:detect")
        except Exception:
            pass

        # ── Restart detection ──
        from src.core.services.tool_install.domain.restart import (
            _batch_restarts,
            detect_restart_needs,
        )

        completed_step_dicts = [steps[ci] for ci in completed_steps if ci < len(steps)]
        restart_needs = detect_restart_needs(plan, completed_step_dicts)
        restart_actions = _batch_restarts(restart_needs) if any(
            restart_needs.get(k) for k in ("shell_restart", "reboot_required", "service_restart")
        ) else []

        done_event: dict = {
            "type": "done",
            "ok": True,
            "plan_id": plan_id,
            "message": f"{tool} installed successfully",
            "steps_completed": len(steps),
        }

        if restart_needs.get("shell_restart") or restart_needs.get("reboot_required") or restart_needs.get("service_restart"):
            done_event["restart"] = restart_needs
            done_event["restart_actions"] = restart_actions

        yield _sse(done_event)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Resumable Plans ────────────────────────────────────────────


@audit_bp.route("/audit/install-plan/pending", methods=["GET"])
def audit_pending_plans():
    """Return a list of resumable (paused/failed) plans.

    Response:
        {"plans": [{"plan_id": "...", "tool": "...", "status": "failed",
                     "completed_steps": [...], "steps": [...]}]}
    """
    from src.core.services.tool_install import list_pending_plans

    plans = list_pending_plans()

    # Return a shallow summary for each plan
    summary = []
    for p in plans:
        summary.append({
            "plan_id": p.get("plan_id", ""),
            "tool": p.get("tool", ""),
            "status": p.get("status", ""),
            "completed_count": len(p.get("completed_steps", [])),
            "total_steps": len(p.get("steps", [])),
        })

    return jsonify({"plans": summary})


@audit_bp.route("/audit/install-plan/resume", methods=["POST"])
def audit_resume_plan():
    """Resume a paused or failed installation plan via SSE.

    Request body:
        {"plan_id": "abc123...", "sudo_password": "..."}

    SSE events: same as /audit/install-plan/execute.
    """
    import json as _json
    import os as _os

    from flask import Response, stream_with_context

    from src.core.services.tool_install import (
        execute_plan_step,
        resume_plan,
        save_plan_state,
    )

    body = request.get_json(silent=True) or {}
    plan_id = body.get("plan_id", "").strip()
    sudo_password = body.get("sudo_password", "")

    if not plan_id:
        return jsonify({"error": "No plan_id specified"}), 400

    # Resume — get remaining steps
    plan = resume_plan(plan_id)
    if plan.get("error"):
        return jsonify({"ok": False, "error": plan["error"]}), 400

    tool = plan.get("tool", "")
    steps = plan.get("steps", [])
    completed_count = plan.get("completed_count", 0)
    original_total = plan.get("original_total", len(steps))

    def _sse(data: dict) -> str:
        return f"data: {_json.dumps(data)}\n\n"

    def generate():
        completed_steps: list[int] = list(range(completed_count))

        for i, step in enumerate(steps):
            step_index = completed_count + i
            step_label = step.get("label", f"Step {step_index + 1}")

            yield _sse({
                "type": "step_start",
                "step": i,
                "label": step_label,
                "total": len(steps),
                "resumed_offset": completed_count,
            })

            try:
                result = execute_plan_step(
                    step,
                    sudo_password=sudo_password,
                )
            except Exception as exc:
                try:
                    save_plan_state({
                        "plan_id": plan_id,
                        "tool": tool,
                        "status": "failed",
                        "current_step": step_index,
                        "completed_steps": completed_steps,
                        "steps": [dict(s) for s in steps],
                    })
                except Exception:
                    pass
                yield _sse({
                    "type": "step_failed",
                    "step": i,
                    "error": str(exc),
                })
                yield _sse({
                    "type": "done",
                    "ok": False,
                    "plan_id": plan_id,
                    "error": f"Step {step_index + 1} crashed: {exc}",
                })
                return

            # Emit stdout
            stdout = result.get("stdout", "")
            if stdout:
                for line in stdout.splitlines():
                    yield _sse({"type": "log", "step": i, "line": line})

            stderr_out = result.get("stderr", "")
            if stderr_out and not result.get("ok"):
                for line in stderr_out.splitlines()[-10:]:
                    yield _sse({"type": "log", "step": i, "line": line})

            if result.get("skipped"):
                completed_steps.append(step_index)
                yield _sse({
                    "type": "step_done",
                    "step": i,
                    "skipped": True,
                    "message": result.get("message", "Already satisfied"),
                })
                continue

            if result.get("ok"):
                completed_steps.append(step_index)
                try:
                    save_plan_state({
                        "plan_id": plan_id,
                        "tool": tool,
                        "status": "running",
                        "current_step": step_index,
                        "completed_steps": completed_steps,
                        "steps": [dict(s) for s in steps],
                    })
                except Exception:
                    pass
                yield _sse({
                    "type": "step_done",
                    "step": i,
                    "elapsed_ms": result.get("elapsed_ms"),
                })
            else:
                try:
                    save_plan_state({
                        "plan_id": plan_id,
                        "tool": tool,
                        "status": "failed",
                        "current_step": step_index,
                        "completed_steps": completed_steps,
                        "steps": [dict(s) for s in steps],
                    })
                except Exception:
                    pass

                if result.get("needs_sudo"):
                    yield _sse({
                        "type": "step_failed",
                        "step": i,
                        "error": result.get("error", "Sudo required"),
                        "needs_sudo": True,
                    })
                    yield _sse({
                        "type": "done",
                        "ok": False,
                        "plan_id": plan_id,
                        "error": result.get("error", "Sudo required"),
                        "needs_sudo": True,
                    })
                    return

                yield _sse({
                    "type": "step_failed",
                    "step": i,
                    "error": result.get("error", "Step failed"),
                })
                yield _sse({
                    "type": "done",
                    "ok": False,
                    "plan_id": plan_id,
                    "error": result.get("error", f"Step {step_index + 1} failed"),
                    "step": i,
                    "step_label": step_label,
                })
                return

        # All steps done
        try:
            save_plan_state({
                "plan_id": plan_id,
                "tool": tool,
                "status": "done",
                "completed_steps": completed_steps,
                "steps": [dict(s) for s in steps],
            })
        except Exception:
            pass

        try:
            root = Path(current_app.config["PROJECT_ROOT"])
            devops_cache.invalidate_scope(root, "integrations")
            devops_cache.invalidate_scope(root, "devops")
            devops_cache.invalidate(root, "wiz:detect")
        except Exception:
            pass

        yield _sse({
            "type": "done",
            "ok": True,
            "plan_id": plan_id,
            "message": f"{tool} resumed and completed successfully",
            "steps_completed": len(steps),
        })

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Plan Cancel / Archive ──────────────────────────────────────


@audit_bp.route("/audit/install-plan/cancel", methods=["POST"])
def audit_cancel_plan():
    """Cancel an interrupted/failed plan.

    Request body:
        {"plan_id": "abc123..."}

    Response:
        {"ok": true, "plan_id": "abc123...", "status": "cancelled"}
    """
    from src.core.services.tool_install import cancel_plan

    body = request.get_json(silent=True) or {}
    plan_id = body.get("plan_id", "").strip()

    if not plan_id:
        return jsonify({"error": "No plan_id specified"}), 400

    result = cancel_plan(plan_id)
    if result.get("error"):
        return jsonify({"ok": False, "error": result["error"]}), 404

    return jsonify({"ok": True, "plan_id": plan_id, "status": "cancelled"})


@audit_bp.route("/audit/install-plan/archive", methods=["POST"])
def audit_archive_plan():
    """Archive a completed/cancelled plan.

    Request body:
        {"plan_id": "abc123..."}

    Response:
        {"ok": true, "plan_id": "abc123...", "status": "archived"}
    """
    from src.core.services.tool_install import archive_plan

    body = request.get_json(silent=True) or {}
    plan_id = body.get("plan_id", "").strip()

    if not plan_id:
        return jsonify({"error": "No plan_id specified"}), 400

    result = archive_plan(plan_id)
    if result.get("error"):
        return jsonify({"ok": False, "error": result["error"]}), 404

    return jsonify({"ok": True, "plan_id": plan_id, "status": "archived"})


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
        try:
            root = Path(current_app.config["PROJECT_ROOT"])
            devops_cache.invalidate_scope(root, "integrations")
            devops_cache.invalidate_scope(root, "devops")
            devops_cache.invalidate(root, "wiz:detect")
        except Exception:
            pass
        return jsonify({
            "ok": True,
            "message": f"{tool} removed",
        })
    else:
        return jsonify({
            "ok": False,
            "error": result.get("error", f"Failed to remove {tool}"),
        }), 500


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
    from src.core.services.audit.l0_detection import _detect_os
    from src.core.services.tool_install import resolve_install_plan, resolve_install_plan_with_choices
    from src.core.services.tool_install.domain.download_helpers import _estimate_download_time
    from src.core.services.tool_install.execution.offline_cache import cache_plan

    body = request.get_json(silent=True) or {}
    tool = body.get("tool", "").strip().lower()
    answers = body.get("answers", {})

    if not tool:
        return jsonify({"error": "No tool specified"}), 400

    system_profile = _detect_os()
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


# ── Phase 8: Service Status ───────────────────────────────────


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
