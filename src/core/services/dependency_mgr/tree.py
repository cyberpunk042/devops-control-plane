"""
Tree builder — construct the scope tree from scanner output.

Builds a ``TreeNode`` hierarchy (Global → Ecosystem → Package)
from Phase 1/2 scanner results, optionally enriched with version
intelligence and user notes.

The tree is buildable incrementally:
  - Phase 1 only → ecosystem nodes, no package children
  - Phase 2 adds → package children under each ecosystem
  - Version intel → sets ``status``, ``latest_version`` on packages
  - Notes → sets ``note`` on packages

Each enrichment is additive — no full rebuild needed.

Usage::

    tree = build_tree(manifests, registry)
    tree = build_tree(manifests, registry, parsed=parsed_manifests)
    tree = build_tree(manifests, registry, parsed=parsed, notes=notes, version_intel=intel)
"""

from __future__ import annotations

from typing import Any

from .ecosystem import EcosystemRegistry
from .models import (
    ManifestInfo,
    ParsedManifest,
    TreeNode,
    VersionIntel,
)


def build_tree(
    manifests: list[ManifestInfo],
    registry: EcosystemRegistry,
    *,
    parsed: list[ParsedManifest] | None = None,
    notes: dict[str, dict[str, Any]] | None = None,
    version_intel: dict[str, VersionIntel] | None = None,
) -> TreeNode:
    """Build the scope tree from scanner output.

    Args:
        manifests: Phase 1 output (always present).
        registry: Ecosystem adapter registry (for human labels).
        parsed: Phase 2 output (optional — adds package children).
        notes: User annotations keyed by ``'{ecosystem}:{package}:{version}'``.
        version_intel: Version health keyed by ``'{ecosystem}:{package}'``.

    Returns:
        Root ``TreeNode`` (``level="global"``) with ecosystem and package children.
    """
    notes = notes or {}
    version_intel = version_intel or {}

    # Index parsed manifests by (ecosystem, path) for fast lookup
    parsed_index: dict[tuple[str, str], ParsedManifest] = {}
    if parsed:
        for pm in parsed:
            key = (pm.info.ecosystem, pm.info.manifest_path)
            parsed_index[key] = pm

    # Build root
    root = TreeNode(id="global", label="Global", level="global")

    # Group manifests by (ecosystem, path) — each group = one ecosystem node
    seen: dict[tuple[str, str], ManifestInfo] = {}
    for info in manifests:
        key = (info.ecosystem, info.manifest_path)
        if key not in seen:
            seen[key] = info

    # Create ecosystem nodes
    for (eco_id, rel_path), info in sorted(seen.items()):
        node_id = f"{eco_id}:{rel_path}"

        # Human label from adapter, fallback to ecosystem id
        adapter = registry.get(eco_id)
        adapter_name = adapter.name if adapter else eco_id
        label = f"{adapter_name} ({rel_path})" if rel_path != "." else adapter_name

        eco_node = TreeNode(
            id=node_id,
            label=label,
            level="ecosystem",
            ecosystem=eco_id,
            path=rel_path,
        )

        # Add package children if Phase 2 data is available
        pm = parsed_index.get((eco_id, rel_path))
        if pm is not None:
            _add_package_children(eco_node, pm, notes, version_intel)

        root.children.append(eco_node)

    return root


def _add_package_children(
    eco_node: TreeNode,
    pm: ParsedManifest,
    notes: dict[str, dict[str, Any]],
    version_intel: dict[str, VersionIntel],
) -> None:
    """Populate package-level children on an ecosystem node."""
    eco_id = eco_node.ecosystem or ""
    rel_path = eco_node.path or "."

    # Main dependencies first, then dev
    all_deps = list(pm.dependencies) + list(pm.dev_dependencies)

    for dep in all_deps:
        pkg_id = f"{eco_id}:{rel_path}:{dep.name}"
        version_str = dep.pinned_version or dep.version_spec or ""

        label = f"{dep.name} {version_str}" if version_str else dep.name

        pkg_node = TreeNode(
            id=pkg_id,
            label=label,
            level="package",
            ecosystem=eco_id,
            path=rel_path,
            version=version_str or None,
            group=dep.group,
        )

        # Enrich with version intelligence
        intel_key = f"{eco_id}:{dep.name}"
        intel = version_intel.get(intel_key)
        if intel is not None:
            pkg_node.latest_version = intel.latest
            pkg_node.status = intel.status

        # Enrich with user notes
        note_key = f"{eco_id}:{dep.name}:{version_str}"
        note_data = notes.get(note_key)
        if note_data is not None:
            pkg_node.note = note_data.get("note", "")

        eco_node.children.append(pkg_node)
