"""
System Posture orchestrator — assembles full posture from all pillars.

This is the main entry point for the system posture feature.
It coordinates the four pillar scanners/bridges, applies TTL
caching, and exposes the public API.

Public API:
    scan_posture(force=False)   → SystemPosture  (full scan)
    get_summary(force=False)    → dict            (lightweight for nav badge)
    invalidate_cache(key=None)  → list[str]       (cache busting)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from .cache import get_or_compute, get_stats, invalidate
from .models import PillarResult, RankLevel, SystemPosture

logger = logging.getLogger(__name__)


# ── Public API ──────────────────────────────────────────────────


def scan_posture(
    *,
    force: bool = False,
    project_root: Path | None = None,
) -> SystemPosture:
    """Run a full system posture scan across all four pillars.

    Each pillar is cached independently with its own TTL::

        platform    → until server restart (OS doesn't change)
        toolchain   → 5 minutes (tools could be installed/updated)
        project     → 60 seconds (bridges to mtime-cached data)
        runtime     → always fresh (in-memory state)

    The assembled ``SystemPosture`` is also cached (60s TTL).

    Args:
        force:        Bypass all caches and rescan everything.
        project_root: Override project root for the project bridge.

    Returns:
        SystemPosture with all four pillars populated.
    """
    def _compute() -> SystemPosture:
        return _assemble_posture(force=force, project_root=project_root)

    if force:
        return _compute()

    return get_or_compute("full", _compute, force=force)


def get_summary(*, force: bool = False) -> dict[str, Any]:
    """Get a lightweight summary for the nav badge.

    This is the fast path — it returns only overall status and
    per-pillar ranks without individual item details.

    If a full posture scan has been cached, the summary is derived
    from it.  Otherwise, a fresh scan is triggered.

    Args:
        force: Bypass cache.

    Returns:
        Dict with ``overall_rank``, ``overall_status``, ``summary``,
        ``pillar_ranks``, and ``timestamp``.
    """
    def _compute() -> dict[str, Any]:
        posture = scan_posture(force=force)
        return posture.to_summary_dict()

    return get_or_compute("summary", _compute, force=force)


def invalidate_cache(key: str | None = None) -> list[str]:
    """Invalidate posture cache.

    Args:
        key: Specific key to invalidate (e.g. ``"toolchain"``),
             or ``None`` to clear everything.

    Returns:
        List of invalidated keys.
    """
    busted = invalidate(key)
    if busted:
        # Also invalidate downstream caches
        if key in ("platform", "toolchain", "project", "runtime"):
            invalidate("full")
            invalidate("summary")
    return busted


def cache_stats() -> dict[str, Any]:
    """Return cache diagnostics.

    Returns:
        Dict of key → {age_s, ttl_s, fresh, elapsed_s}.
    """
    return get_stats()


# ── Internal assembly ───────────────────────────────────────────


def _assemble_posture(
    *,
    force: bool = False,
    project_root: Path | None = None,
) -> SystemPosture:
    """Assemble SystemPosture from all four pillars.

    Each pillar is computed via its own cached scanner/bridge.
    Errors in one pillar don't block others — a pillar that
    fails gets an UNKNOWN rank with the error message.
    """
    t0 = time.time()

    # ── Platform (cached until restart) ─────────────────────────
    platform_result = get_or_compute(
        "platform",
        _scan_platform,
        force=force,
    )

    # ── Toolchain (5 min TTL) ───────────────────────────────────
    toolchain_result = get_or_compute(
        "toolchain",
        _scan_toolchain,
        force=force,
    )

    # ── Project (60s TTL) ───────────────────────────────────────
    project_result = get_or_compute(
        "project",
        lambda: _bridge_project(project_root),
        force=force,
    )

    # ── Runtime (always fresh, TTL=0) ───────────────────────────
    runtime_result = get_or_compute(
        "runtime",
        _bridge_runtime,
        force=force,
    )

    # ── Assemble ────────────────────────────────────────────────
    posture = SystemPosture(
        pillars={
            "platform": platform_result,
            "toolchain": toolchain_result,
            "project": project_result,
            "runtime": runtime_result,
        },
        scan_duration_ms=round((time.time() - t0) * 1000),
    )
    posture.recompute_overall()

    logger.info(
        "posture scan: %s %s (%dms)",
        posture.overall_rank.emoji,
        posture.overall_status,
        posture.scan_duration_ms,
    )

    return posture


# ── Pillar wrappers (isolate import + error handling) ───────────


def _scan_platform() -> PillarResult:
    """Run platform scanner with error isolation."""
    try:
        from .scanners.platform import scan_platform
        return scan_platform()
    except Exception as exc:
        logger.error("platform scan failed: %s", exc, exc_info=True)
        return PillarResult(
            pillar="platform",
            rank=RankLevel.UNKNOWN,
            warnings=[f"Platform scan error: {exc}"],
        )


def _scan_toolchain() -> PillarResult:
    """Run toolchain scanner with error isolation."""
    try:
        from .scanners.toolchain import scan_toolchain
        return scan_toolchain()
    except Exception as exc:
        logger.error("toolchain scan failed: %s", exc, exc_info=True)
        return PillarResult(
            pillar="toolchain",
            rank=RankLevel.UNKNOWN,
            warnings=[f"Toolchain scan error: {exc}"],
        )


def _bridge_project(project_root: Path | None) -> PillarResult:
    """Run project bridge with error isolation."""
    try:
        from .bridges.project import bridge_project
        return bridge_project(project_root)
    except Exception as exc:
        logger.error("project bridge failed: %s", exc, exc_info=True)
        return PillarResult(
            pillar="project",
            rank=RankLevel.UNKNOWN,
            warnings=[f"Project bridge error: {exc}"],
        )


def _bridge_runtime() -> PillarResult:
    """Run runtime bridge with error isolation."""
    try:
        from .bridges.runtime import bridge_runtime
        return bridge_runtime()
    except Exception as exc:
        logger.error("runtime bridge failed: %s", exc, exc_info=True)
        return PillarResult(
            pillar="runtime",
            rank=RankLevel.UNKNOWN,
            warnings=[f"Runtime bridge error: {exc}"],
        )
