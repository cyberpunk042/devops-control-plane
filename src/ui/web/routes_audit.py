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
def audit_install_tool():
    """Install a missing devops tool."""
    from src.core.services.tool_install import install_tool

    body = request.get_json(silent=True) or {}
    result = install_tool(
        tool=body.get("tool", ""),
        cli=body.get("cli", ""),
        sudo_password=body.get("sudo_password", ""),
    )

    status = 200 if result.get("ok") or result.get("needs_sudo") else 400
    return jsonify(result), status

