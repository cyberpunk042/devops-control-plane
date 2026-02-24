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


# ── L0: System Profile ─────────────────────────────────────────

@audit_bp.route("/audit/system")
def audit_system():
    root = _project_root()
    bust = "bust" in request.args
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
    """Check if system packages are installed."""
    from src.core.services.tool_install import check_system_deps

    body = request.get_json(silent=True) or {}
    packages = body.get("packages", [])
    if not packages:
        return jsonify({"missing": [], "installed": []}), 200
    result = check_system_deps(packages)
    return jsonify(result), 200


@audit_bp.route("/tools/status")
def tools_status():
    """Centralized tool availability status.

    Returns all registered tools with availability, category,
    install type, and whether an install recipe exists.
    """
    from src.core.services.audit.l0_detection import detect_tools
    from src.core.services.tool_install import (
        _NO_SUDO_RECIPES,
        _SUDO_RECIPES,
    )

    tools = detect_tools()
    # Enrich with recipe availability
    for t in tools:
        tid = t["id"]
        t["has_recipe"] = tid in _NO_SUDO_RECIPES or tid in _SUDO_RECIPES
        t["needs_sudo"] = tid in _SUDO_RECIPES

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
