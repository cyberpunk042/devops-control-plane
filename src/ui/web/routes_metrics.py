"""
Metrics & health routes — project health score endpoints.

Blueprint: metrics_bp
Prefix: /api

Thin HTTP wrappers over ``src.core.services.metrics_ops``.

Endpoints:
    GET /metrics/health   — full health probe with score
    GET /metrics/summary  — quick project summary
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.core.services import metrics_ops

metrics_bp = Blueprint("metrics", __name__)

# Map each health probe to:
#   1. its watch-path cache key (matches devops_cache._WATCH_PATHS)
#   2. the probe function name in metrics_ops
_HEALTH_PROBES: dict[str, tuple[str, str]] = {
    "git":       ("git",      "_probe_git"),
    "docker":    ("docker",   "_probe_docker"),
    "ci":        ("ci",       "_probe_ci"),
    "packages":  ("packages", "_probe_packages"),
    "env":       ("env",      "_probe_env"),
    "quality":   ("quality",  "_probe_quality"),
    "structure": ("docs",     "_probe_structure"),
}


def _project_root() -> Path:
    return Path(current_app.config["PROJECT_ROOT"])


@metrics_bp.route("/metrics/health")
def project_health():  # type: ignore[no-untyped-def]
    """Full health probe with unified score.

    Each probe reuses the card-level cache (``docker``, ``git``, etc.)
    so it shares data with the DevOps card endpoints.  All 7 probes
    run in parallel via ThreadPoolExecutor — cold-cache time is bounded
    by the *slowest* probe, not the sum.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    root = _project_root()
    force = request.args.get("bust", "") == "1"

    # Run all 7 probes in parallel (each caches via the card-level key).
    probe_fns: dict[str, Callable] = {}
    for probe_id, (cache_key, fn_name) in _HEALTH_PROBES.items():
        probe_fns[probe_id] = getattr(metrics_ops, fn_name)

    probes: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=len(probe_fns)) as pool:
        futures = {
            pool.submit(fn, root): probe_id
            for probe_id, fn in probe_fns.items()
        }
        for future in as_completed(futures):
            probe_id = futures[future]
            try:
                probes[probe_id] = future.result()
            except Exception as exc:
                probes[probe_id] = {
                    "score": 0,
                    "findings": [f"Probe error: {exc}"],
                    "recommendations": [],
                }

    # Assemble composite score (same logic as metrics_ops.project_health)
    weights = metrics_ops._WEIGHTS
    total_score = 0.0
    for probe_id, result in probes.items():
        weighted = result.get("score", 0) * weights.get(probe_id, 0)
        total_score += weighted

    # Compute grade
    if total_score >= 90:
        grade = "A"
    elif total_score >= 75:
        grade = "B"
    elif total_score >= 60:
        grade = "C"
    elif total_score >= 40:
        grade = "D"
    else:
        grade = "F"

    # Gather recommendations sorted by weight
    all_recs: list[str] = []
    for probe_id in sorted(weights, key=lambda k: weights[k], reverse=True):
        probe = probes.get(probe_id, {})
        for rec in probe.get("recommendations", []):
            if rec not in all_recs:
                all_recs.append(rec)

    return jsonify({
        "score": round(total_score, 1),
        "max_score": metrics_ops._MAX_SCORE,
        "grade": grade,
        "timestamp": datetime.now(UTC).isoformat(),
        "probes": probes,
        "recommendations": all_recs[:10],
    })


@metrics_bp.route("/metrics/summary")
def project_summary():  # type: ignore[no-untyped-def]
    """Quick project summary."""
    return jsonify(metrics_ops.project_summary(_project_root()))
