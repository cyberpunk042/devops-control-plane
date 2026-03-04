"""
Audit analysis endpoints — L0/L1/L2 audit data.

Routes registered on ``audit_bp`` from the parent package.

Endpoints:
    GET /audit/system               — L0: system profile
    GET /audit/dependencies         — L1: dependency analysis
    GET /audit/structure            — L1: project structure
    GET /audit/clients              — L1: client/service detection
    GET /audit/scores               — aggregate scores
    GET /audit/scores/enriched      — L2-enriched scores
    GET /audit/scores/history       — score trend history
    GET /audit/structure-analysis   — L2: import graph
    GET /audit/code-health          — L2: code quality
    GET /audit/repo                 — L2: repository health
    GET /audit/risks                — L2: risk aggregation
"""

from __future__ import annotations

from flask import jsonify, request

from src.core.services.devops import cache as devops_cache
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
from src.ui.web.helpers import project_root as _project_root

from . import audit_bp


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


# ── L2 Cache-or-Scan Helper ────────────────────────────────────


def _cache_or_needs_scan(root, cache_key, compute_fn, bust):
    """Return cached L2 data, or {"needs_scan": true} on cold cache.

    When ``bust`` is True (explicit refresh), forces synchronous
    recompute via get_cached.  Otherwise, returns instantly:
    either the cached data or a lightweight {"needs_scan": true}
    response that the frontend uses to trigger POST /audit/scan.

    This prevents the 30-second timeout that occurs when slow L2
    compute functions (risks: 32s, quality: 16s) block the request.
    """
    if bust:
        # Explicit refresh — compute synchronously
        return devops_cache.get_cached(
            root, cache_key, compute_fn, force=True,
        )

    # Try cache read without computing
    try:
        from src.core.services.devops.cache import _load_cache
        cache = _load_cache(root)
        entry = cache.get(cache_key)
        if entry and "data" in entry:
            return entry["data"]
    except Exception:
        pass

    # No cache — tell the frontend to trigger async scan
    return {"needs_scan": True, "cache_key": cache_key}


# ── L2: Structure Analysis (on-demand) ─────────────────────────

@audit_bp.route("/audit/structure-analysis")
def audit_structure_analysis():
    """L2: Import graph, module boundaries, cross-module deps.

    Returns cached data instantly, or {"needs_scan": true} on cold
    cache.  Explicit ?bust forces synchronous recompute.
    """
    root = _project_root()
    bust = "bust" in request.args
    return jsonify(_cache_or_needs_scan(
        root, "audit:l2:structure",
        lambda: l2_structure(root), bust,
    ))


# ── L2: Code Health (on-demand) ────────────────────────────────

@audit_bp.route("/audit/code-health")
def audit_code_health():
    """L2: Code quality metrics — health scores, hotspots, naming.

    Returns cached data instantly, or {"needs_scan": true} on cold
    cache.  Explicit ?bust forces synchronous recompute.
    """
    root = _project_root()
    bust = "bust" in request.args
    return jsonify(_cache_or_needs_scan(
        root, "audit:l2:quality",
        lambda: l2_quality(root), bust,
    ))


# ── L2: Repo Health (on-demand) ────────────────────────────────

@audit_bp.route("/audit/repo")
def audit_repo_health():
    """L2: Repository health — git objects, history, large files.

    Returns cached data instantly, or {"needs_scan": true} on cold
    cache.  Explicit ?bust forces synchronous recompute.
    """
    root = _project_root()
    bust = "bust" in request.args
    return jsonify(_cache_or_needs_scan(
        root, "audit:l2:repo",
        lambda: l2_repo(root), bust,
    ))


# ── L2: Risks & Issues (on-demand) ─────────────────────────────

@audit_bp.route("/audit/risks")
def audit_risks():
    """L2: Risk aggregation — security, deps, docs, testing, infra.

    Returns cached data instantly, or {"needs_scan": true} on cold
    cache.  Explicit ?bust forces synchronous recompute.
    """
    root = _project_root()
    bust = "bust" in request.args
    return jsonify(_cache_or_needs_scan(
        root, "audit:l2:risks",
        lambda: l2_risks(root), bust,
    ))
