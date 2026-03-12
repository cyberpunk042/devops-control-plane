"""
Toolchain scanner — detect installed tool versions and rank them.

Reuses the existing version detection infrastructure:
  - ``tool_install/detection/tool_version.get_tool_version(tool)``
    → runs ``tool --version`` and parses output
  - ``tool_install/detection/tool_version.VERSION_COMMANDS``
    → dict of 35+ tools with their version commands and regex

This scanner adds the RANKING layer on top: it loads the lifecycle
database (``data/tool_lifecycle.json``) and computes a deprecation
rank for each detected tool.

Version detection runs in parallel via ThreadPoolExecutor.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from ..models import PillarResult, PostureItem, RankLevel
from ..ranking import load_tool_lifecycle, rank_tool_version, worst_rank

logger = logging.getLogger(__name__)

# Maximum parallel subprocess calls for version detection.
# Each call runs ``tool --version`` with a 10s timeout (enforced
# by get_tool_version).  8 workers keeps the system responsive.
_MAX_WORKERS = 8


def scan_toolchain() -> PillarResult:
    """Scan all known tools and rank their installed versions.

    Workflow:
      1. Load lifecycle database
      2. Get list of scannable tools (intersection of VERSION_COMMANDS
         and lifecycle DB)
      3. Run ``get_tool_version(tool)`` in parallel for each tool
      4. Rank each detected version against lifecycle data
      5. Assemble PillarResult with all ranked items

    Returns:
        PillarResult with one PostureItem per detected tool.
        Tools that are not installed are excluded from the result.
    """
    # Lazy imports — avoid pulling in tool_install at module load
    from src.core.services.tool_install.detection.tool_version import (
        VERSION_COMMANDS,
        get_tool_version,
    )

    lifecycle_db = load_tool_lifecycle()

    # Only scan tools that exist in BOTH VERSION_COMMANDS and lifecycle DB
    tools_to_scan = [
        tool for tool in VERSION_COMMANDS
        if tool in lifecycle_db
    ]

    # ── Parallel version detection ──────────────────────────────
    detected: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {
            pool.submit(get_tool_version, tool): tool
            for tool in tools_to_scan
        }
        for future in as_completed(futures):
            tool = futures[future]
            try:
                version = future.result()
                if version:
                    detected[tool] = version
            except Exception as exc:
                logger.debug("toolchain scan %s failed: %s", tool, exc)

    # ── Rank each detected tool ─────────────────────────────────
    items: list[PostureItem] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    for tool in sorted(detected.keys()):
        version = detected[tool]
        lifecycle = lifecycle_db.get(tool, {})
        rank, detail = rank_tool_version(version, lifecycle)

        items.append(PostureItem(
            name=tool,
            value=version,
            rank=rank,
            detail=detail,
            current_version=lifecycle.get("current", ""),
        ))

        if rank.severity >= RankLevel.OUTDATED.severity:
            current = lifecycle.get("current", "?")
            warnings.append(f"{tool} {version} is {rank.value} (current: {current})")

        if rank.severity >= RankLevel.DEPRECATED.severity:
            recommendations.append(f"Update {tool}: {version} → {lifecycle.get('current', '?')}")

    # ── Summary stats ───────────────────────────────────────────
    n_total = len(items)
    n_current = sum(1 for i in items if i.rank == RankLevel.CURRENT)
    n_aging = sum(1 for i in items if i.rank == RankLevel.AGING)
    n_warn = len(warnings)

    if n_warn == 0:
        logger.info(
            "toolchain scan: %d tools, all current or aging", n_total,
        )
    else:
        logger.info(
            "toolchain scan: %d tools (%d current, %d aging, %d warnings)",
            n_total, n_current, n_aging, n_warn,
        )

    return PillarResult(
        pillar="toolchain",
        rank=worst_rank(items) if items else RankLevel.UNKNOWN,
        items=items,
        warnings=warnings,
        recommendations=recommendations,
    )


def get_tool_context(tool: str) -> PostureItem | None:
    """Get posture context for a single tool (for error enrichment).

    This is a fast path for Chunk 11 (tool_install integration) — it
    checks a single tool without scanning the entire toolchain.

    Args:
        tool: Tool ID (e.g. "terraform", "kubectl").

    Returns:
        PostureItem for the tool, or None if not installed or
        not in the lifecycle database.
    """
    from src.core.services.tool_install.detection.tool_version import (
        get_tool_version,
    )

    lifecycle_db = load_tool_lifecycle()
    lifecycle = lifecycle_db.get(tool)
    if not lifecycle:
        return None

    version = get_tool_version(tool)
    if not version:
        return None

    rank, detail = rank_tool_version(version, lifecycle)
    return PostureItem(
        name=tool,
        value=version,
        rank=rank,
        detail=detail,
        current_version=lifecycle.get("current", ""),
    )
