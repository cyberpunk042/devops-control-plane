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


def _mediator_or_legacy(mediator_path, cache_key, compute_fn, bust):
    """Resolve data via mediator.

    Used for L0/L1 audit routes.
    """
    from src.core.services.mediator import get_mediator
    m = get_mediator()
    result = m.get(mediator_path, force=bust)
    return result["data"]


@audit_bp.route("/audit/system")
def audit_system():
    root = _project_root()
    bust = "bust" in request.args
    deep = "deep" in request.args

    if deep:
        # Deep tier: separate mediator node
        result = _mediator_or_legacy(
            "audit.system_deep", "audit:system:deep",
            lambda: l0_system_profile(root, deep=True), bust,
        )
    else:
        result = _mediator_or_legacy(
            "audit.system", "audit:system",
            lambda: l0_system_profile(root), bust,
        )
    return jsonify(result)


# ── L1: Dependencies & Libraries ───────────────────────────────

@audit_bp.route("/audit/dependencies")
def audit_dependencies():
    root = _project_root()
    bust = "bust" in request.args
    result = _mediator_or_legacy(
        "audit.deps", "audit:deps",
        lambda: l1_dependencies(root), bust,
    )
    return jsonify(result)


# ── L1: Structure & Modules ────────────────────────────────────

@audit_bp.route("/audit/structure")
def audit_structure():
    root = _project_root()
    bust = "bust" in request.args
    result = _mediator_or_legacy(
        "audit.structure", "audit:structure",
        lambda: l1_structure(root), bust,
    )
    return jsonify(result)


# ── L1: Clients & Services ─────────────────────────────────────

@audit_bp.route("/audit/clients")
def audit_clients():
    root = _project_root()
    bust = "bust" in request.args
    result = _mediator_or_legacy(
        "audit.clients", "audit:clients",
        lambda: l1_clients(root), bust,
    )
    return jsonify(result)


# ── Scores ──────────────────────────────────────────────────────

@audit_bp.route("/audit/scores")
def audit_scores_endpoint():
    root = _project_root()
    bust = "bust" in request.args
    result = _mediator_or_legacy(
        "audit.scores", "audit:scores",
        lambda: audit_scores(root), bust,
    )
    return jsonify(result)


@audit_bp.route("/audit/scores/enriched")
def audit_scores_enriched_endpoint():
    """L2-enriched master scores — uses full L2 analysis.

    On-demand — takes 5-25s total. Results are cached.
    """
    root = _project_root()
    bust = "bust" in request.args
    result = _mediator_or_legacy(
        "audit.scores_enriched", "audit:scores:enriched",
        lambda: audit_scores_enriched(root), bust,
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
    recompute via the mediator.  Otherwise, uses ``peek`` to return
    instantly: either the cached data or a lightweight {"needs_scan"}
    response that the frontend uses to trigger POST /audit/scan.

    This prevents the 30-second timeout that occurs when slow L2
    compute functions (risks: 32s, quality: 16s) block the request.
    """
    from src.core.services.mediator import get_mediator

    # Mapping from legacy devops_cache keys to mediator paths
    _L2_KEY_MAP = {
        "audit:l2:structure": "audit.l2_structure",
        "audit:l2:quality": "audit.l2_quality",
        "audit:l2:repo": "audit.l2_repo",
        "audit:l2:risks": "audit.l2_risks",
    }
    mediator_path = _L2_KEY_MAP.get(cache_key)

    if bust:
        # Explicit refresh — compute synchronously via mediator.
        if mediator_path:
            m = get_mediator()
            result = m.get(mediator_path, force=True)
            return result["data"]
        # No mediator path — shouldn't happen, but fallback
        return compute_fn()

    # Non-bust: check mediator cache (peek = never blocks)
    if mediator_path:
        try:
            m = get_mediator()
            result = m.peek(mediator_path)
            if result is not None:
                data = result.get("data")
                if data is not None:
                    return data
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
