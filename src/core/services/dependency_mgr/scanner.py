"""
Two-phase dependency scanner.

Phase 1 — Detection (fast, no file reads):
    Walks module directories, calls ``adapter.detect()`` per ecosystem.
    Returns lightweight ``ManifestInfo`` objects.  ~5ms typical.

Phase 2 — Parsing (lazy, reads file contents):
    For each ``ManifestInfo``, calls ``adapter.parse_manifest()`` to
    extract declared dependencies.  Slower — reads and parses files.
    Can be called selectively (e.g. only expanded ecosystems in the UI).

Both phases go through the ``EcosystemRegistry`` — no ecosystem-specific
logic here.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .ecosystem import EcosystemRegistry
from .models import ManifestInfo, ParsedManifest

logger = logging.getLogger(__name__)


def detect_manifests(
    project_root: Path,
    modules: list[dict[str, Any]],
    registry: EcosystemRegistry,
) -> list[ManifestInfo]:
    """Phase 1 — scan project for dependency manifests.

    Walks each module directory plus the project root.
    Calls ``adapter.detect()`` for each registered ecosystem.
    Returns lightweight ``ManifestInfo`` objects (no file parsing).

    Args:
        project_root: Absolute path to the project root.
        modules: Module list from ``index.scan`` — each dict has
            a ``'path'`` key (relative dir, e.g. ``'frontend/'``).
        registry: The ecosystem adapter registry.

    Returns:
        Flat list of ``ManifestInfo``, one per manifest file found.
    """
    # Directories to scan: project root + each module path
    dirs: dict[str, Path] = {".": project_root}
    for mod in modules:
        rel = mod.get("path", "")
        if rel and rel != ".":
            abs_dir = project_root / rel
            if abs_dir.is_dir():
                dirs[rel] = abs_dir

    manifests: list[ManifestInfo] = []

    for rel_dir, abs_dir in sorted(dirs.items()):
        for adapter in registry.all():
            try:
                found = adapter.detect(abs_dir)
            except Exception:
                logger.debug(
                    "detect() failed for %s in %s", adapter.id, rel_dir,
                    exc_info=True,
                )
                continue

            for info in found:
                # Normalize manifest_path to be relative to project root
                # (adapter may return it relative to the scanned dir)
                manifests.append(ManifestInfo(
                    ecosystem=info.ecosystem,
                    manifest_file=info.manifest_file,
                    manifest_path=rel_dir,
                    lock_file=info.lock_file,
                    cli=info.cli,
                    cli_available=info.cli_available,
                    mtime=info.mtime,
                ))

    logger.debug(
        "Phase 1 detection: %d manifests across %d directories",
        len(manifests), len(dirs),
    )
    return manifests


def parse_manifests(
    project_root: Path,
    manifests: list[ManifestInfo],
    registry: EcosystemRegistry,
) -> list[ParsedManifest]:
    """Phase 2 — parse manifest files to extract declared dependencies.

    Calls ``adapter.parse_manifest()`` for each detected manifest.
    Slower than detection: reads and parses file contents.

    Can be called selectively — pass a subset of manifests to parse
    only specific ecosystems (e.g. the one the user expanded in the UI).

    Args:
        project_root: Absolute path to the project root.
        manifests: Phase 1 output — list of ``ManifestInfo``.
        registry: The ecosystem adapter registry.

    Returns:
        List of ``ParsedManifest``, one per input manifest.
        Manifests that fail to parse are skipped (logged).
    """
    parsed: list[ParsedManifest] = []

    for info in manifests:
        adapter = registry.get(info.ecosystem)
        if adapter is None:
            logger.debug("No adapter for ecosystem: %s", info.ecosystem)
            continue

        manifest_path = project_root / info.manifest_path / info.manifest_file
        lock_path = (
            (project_root / info.manifest_path / info.lock_file)
            if info.lock_file else None
        )

        try:
            result = adapter.parse_manifest(manifest_path, lock_path)
            # Ensure parsed manifest_path matches the scanner's path
            # (adapters return "." since they don't know the relative dir)
            if result.info.manifest_path != info.manifest_path:
                result = ParsedManifest(
                    info=ManifestInfo(
                        ecosystem=result.info.ecosystem,
                        manifest_file=result.info.manifest_file,
                        manifest_path=info.manifest_path,
                        lock_file=result.info.lock_file,
                        cli=result.info.cli,
                        cli_available=result.info.cli_available,
                        mtime=result.info.mtime,
                    ),
                    dependencies=result.dependencies,
                    dev_dependencies=result.dev_dependencies,
                    total=result.total,
                )
            parsed.append(result)
        except Exception:
            logger.debug(
                "parse_manifest() failed for %s/%s",
                info.manifest_path, info.manifest_file,
                exc_info=True,
            )

    logger.debug(
        "Phase 2 parsing: %d manifests parsed, %d total deps",
        len(parsed), sum(p.total for p in parsed),
    )
    return parsed
