"""
Project bridge — wraps /metrics/health probes into posture format.

The project health endpoint runs 7 probes (git, docker, ci, packages,
env, quality, structure).  This bridge calls the same underlying
functions (via ``metrics_ops``) and maps the results into PostureItems.

Why a bridge, not a scanner?
  The data already exists — the ``metrics_ops`` probe functions cache
  their results via the card-level mtime cache.  We just re-format
  the output into the posture data model.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from ..models import PillarResult, PostureItem, RankLevel

logger = logging.getLogger(__name__)

# Probe weight influences how much each probe affects the overall
# project posture.  These mirror metrics_ops._weights() but are
# used here only for severity mapping.
_PROBE_IDS = ["git", "docker", "ci", "packages", "env", "quality", "structure"]


def bridge_project(project_root: Path | None = None) -> PillarResult:
    """Bridge existing project health probes into posture format.

    Args:
        project_root: Project root path.  If None, attempts to
            detect from context.

    Returns:
        PillarResult with one PostureItem per health probe.
    """
    if project_root is None:
        project_root = _get_project_root()

    if project_root is None:
        return PillarResult(
            pillar="project",
            rank=RankLevel.UNKNOWN,
            warnings=["No project root detected"],
        )

    # Run probes in parallel (same approach as /metrics/health endpoint)
    probes = _run_probes(project_root)

    items: list[PostureItem] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    for probe_id in _PROBE_IDS:
        result = probes.get(probe_id)
        if result is None:
            continue

        raw_score = result.get("score", 0)  # 0.0-1.0 from probes
        pct = round(raw_score * 100)
        rank = _score_to_rank(raw_score)
        findings = result.get("findings", [])
        recs = result.get("recommendations", [])

        detail_parts: list[str] = [f"score: {pct}%"]
        if findings:
            detail_parts.append(f"{len(findings)} finding(s)")

        items.append(PostureItem(
            name=f"project:{probe_id}",
            value=f"{pct}%",
            rank=rank,
            detail=" · ".join(detail_parts),
        ))

        if rank.severity >= RankLevel.OUTDATED.severity:
            warnings.append(f"{probe_id} probe scored {pct}%")

        recommendations.extend(recs[:2])  # Cap per-probe recs

    from ..ranking import worst_rank

    return PillarResult(
        pillar="project",
        rank=worst_rank(items) if items else RankLevel.UNKNOWN,
        items=items,
        warnings=warnings,
        recommendations=recommendations[:10],
    )


def _run_probes(project_root: Path) -> dict[str, dict[str, Any]]:
    """Run project health probes in parallel.

    Reuses the same probe functions as /metrics/health.
    Each probe returns: {score, findings, recommendations}.
    """
    try:
        from src.core.services.metrics import ops as metrics_ops
    except ImportError:
        logger.debug("metrics_ops not available")
        return {}

    # Map probe_id → function name (same as health.py _HEALTH_PROBES)
    probe_fns: dict[str, str] = {
        "git": "_probe_git",
        "docker": "_probe_docker",
        "ci": "_probe_ci",
        "packages": "_probe_packages",
        "env": "_probe_env",
        "quality": "_probe_quality",
        "structure": "_probe_structure",
    }

    results: dict[str, dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=len(probe_fns)) as pool:
        futures = {}
        for probe_id, fn_name in probe_fns.items():
            fn = getattr(metrics_ops, fn_name, None)
            if fn:
                futures[pool.submit(fn, project_root)] = probe_id

        for future in as_completed(futures):
            probe_id = futures[future]
            try:
                results[probe_id] = future.result()
            except Exception as exc:
                logger.debug("project probe %s failed: %s", probe_id, exc)
                results[probe_id] = {
                    "score": 0,
                    "findings": [f"Probe error: {exc}"],
                    "recommendations": [],
                }

    return results


def _score_to_rank(score: float) -> RankLevel:
    """Map a 0.0-1.0 health score to a RankLevel.

    Probes return scores in 0.0 to 1.0 range.

    Thresholds:
        >= 0.8:  Current   (healthy project)
        >= 0.6:  Aging     (needs attention)
        >= 0.4:  Outdated  (significant issues)
        >= 0.2:  Deprecated(many issues)
        < 0.2:   Dangerous (critically unhealthy)
    """
    if score >= 0.8:
        return RankLevel.CURRENT
    elif score >= 0.6:
        return RankLevel.AGING
    elif score >= 0.4:
        return RankLevel.OUTDATED
    elif score >= 0.2:
        return RankLevel.DEPRECATED
    else:
        return RankLevel.DANGEROUS


def _get_project_root() -> Path | None:
    """Get project root from context, if available."""
    try:
        from src.core.context import get_project_root
        return get_project_root()
    except Exception:
        return None
