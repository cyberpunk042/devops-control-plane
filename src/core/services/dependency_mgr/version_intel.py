"""
Version intelligence — query registries for latest versions and deprecation.

Batch-resolves version health for packages in the dependency tree.
Each ecosystem adapter provides ``fetch_latest_version()`` and
``check_deprecated()`` — this module orchestrates the calls and
produces ``VersionIntel`` records.

Results are cached in the mediator (1-hour TTL per ecosystem).
The tree builder uses them to set status icons.

Usage::

    from src.core.services.dependency_mgr.version_intel import resolve_version_intel

    intel = resolve_version_intel(parsed_manifests, registry)
    # intel = {"pip:flask": VersionIntel(...), "pip:requests": VersionIntel(...)}
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .ecosystem import EcosystemRegistry
from .models import ParsedManifest, VersionIntel

logger = logging.getLogger(__name__)


def resolve_version_intel(
    parsed: list[ParsedManifest],
    registry: EcosystemRegistry,
    *,
    max_packages: int = 100,
) -> dict[str, VersionIntel]:
    """Resolve version intelligence for all packages in parsed manifests.

    Calls each adapter's ``fetch_latest_version()`` and ``check_deprecated()``
    for every package. Network-heavy — results should be cached by the caller.

    Args:
        parsed: Phase 2 scanner output.
        registry: Ecosystem adapter registry.
        max_packages: Safety limit — skip if too many packages (avoid
            hammering registries). Default 100.

    Returns:
        Dict keyed by ``'{ecosystem}:{package_name}'`` → ``VersionIntel``.
    """
    result: dict[str, VersionIntel] = {}
    total = sum(p.total for p in parsed)

    if total > max_packages:
        logger.info(
            "version_intel: skipping — %d packages exceeds limit %d",
            total, max_packages,
        )
        return result

    for pm in parsed:
        eco_id = pm.info.ecosystem
        adapter = registry.get(eco_id)
        if adapter is None:
            continue

        all_deps = list(pm.dependencies) + list(pm.dev_dependencies)
        seen: set[str] = set()

        for dep in all_deps:
            key = f"{eco_id}:{dep.name}"
            if key in seen or key in result:
                continue
            seen.add(key)

            installed = dep.pinned_version or dep.version_spec or ""
            intel = _resolve_single(adapter, eco_id, dep.name, installed)
            if intel is not None:
                result[key] = intel

    logger.debug("version_intel: resolved %d/%d packages", len(result), total)
    return result


def _resolve_single(adapter, eco_id: str, package: str, installed: str) -> VersionIntel | None:
    """Resolve version intel for one package. Fail-safe."""
    try:
        latest = adapter.fetch_latest_version(package)
        is_deprecated, dep_detail = adapter.check_deprecated(package, installed)

        if latest is None and not is_deprecated:
            return VersionIntel(
                package=package, ecosystem=eco_id, installed=installed,
                latest=None, status="unknown", eol_date=None, successor=None,
                breaking=False, detail="Could not fetch version info",
            )

        if is_deprecated:
            return VersionIntel(
                package=package, ecosystem=eco_id, installed=installed,
                latest=latest, status="deprecated", eol_date=None,
                successor=None, breaking=False, detail=dep_detail or "Deprecated",
            )

        if latest and installed:
            cmp = _compare_versions(installed, latest)
            if cmp == "current":
                return VersionIntel(
                    package=package, ecosystem=eco_id, installed=installed,
                    latest=latest, status="current", eol_date=None, successor=None,
                    breaking=False, detail="Up to date",
                )
            elif cmp == "outdated":
                breaking = _is_major_bump(installed, latest)
                detail = f"{latest} available"
                if breaking:
                    detail += " (major version — may have breaking changes)"
                return VersionIntel(
                    package=package, ecosystem=eco_id, installed=installed,
                    latest=latest, status="outdated", eol_date=None, successor=None,
                    breaking=breaking, detail=detail,
                )

        # Have latest but can't compare (no installed version)
        return VersionIntel(
            package=package, ecosystem=eco_id, installed=installed,
            latest=latest, status="unknown", eol_date=None, successor=None,
            breaking=False, detail="Version comparison inconclusive",
        )

    except Exception:
        logger.debug("version_intel failed for %s:%s", eco_id, package, exc_info=True)
        return None


def _compare_versions(installed: str, latest: str) -> str:
    """Compare version strings. Returns 'current', 'outdated', or 'unknown'."""
    inst_parts = _ver_parts(installed)
    lat_parts = _ver_parts(latest)
    if not inst_parts or not lat_parts:
        return "unknown"
    # Pad to same length
    while len(inst_parts) < len(lat_parts):
        inst_parts.append(0)
    while len(lat_parts) < len(inst_parts):
        lat_parts.append(0)
    if inst_parts >= lat_parts:
        return "current"
    return "outdated"


def _is_major_bump(from_ver: str, to_ver: str) -> bool:
    """Check if upgrading crosses a major version boundary."""
    from_parts = _ver_parts(from_ver)
    to_parts = _ver_parts(to_ver)
    if not from_parts or not to_parts:
        return False
    return to_parts[0] > from_parts[0]


def _ver_parts(ver: str) -> list[int]:
    """Extract numeric version parts, stripping prefixes like >= ^ ~ v."""
    cleaned = re.sub(r'^[^\d]*', '', ver)
    parts = []
    for p in cleaned.split(".")[:3]:
        m = re.match(r'\d+', p)
        if m:
            parts.append(int(m.group()))
        else:
            break
    return parts


def version_intel_to_dict(intel: dict[str, VersionIntel]) -> dict[str, dict[str, Any]]:
    """Serialize the intel dict for mediator persistence."""
    return {k: v.to_dict() for k, v in intel.items()}


def version_intel_from_dict(data: dict[str, dict[str, Any]]) -> dict[str, VersionIntel]:
    """Deserialize the intel dict from mediator cache."""
    return {k: VersionIntel.from_dict(v) for k, v in data.items()}
