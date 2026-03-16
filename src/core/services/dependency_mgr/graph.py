"""
Dependency graph — inter-module relationships and impact analysis.

Built from the dependency tree. Identifies shared packages across
modules within the same ecosystem and computes blast radius for
upgrade operations.

This is E10 (Dependency Graph & Impact Analysis).

Usage::

    tree_data = mediator.get("dependency.tree")["data"]
    graph = build_graph(tree_data)
    impact = analyze_impact(graph, "pip", "requests", "2.32.3")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# ═════════════════════════════════════════════════════════════════
#  Data models
# ═════════════════════════════════════════════════════════════════


@dataclass
class DependencyEdge:
    """One module depends on one package."""

    source: str                # Ecosystem node id: "pip:.", "pip:workers"
    source_label: str          # Human label: "Python (pip)", "Python (pip) (workers)"
    target: str                # Package name: "flask", "requests"
    ecosystem: str             # "pip", "npm", etc.
    version_spec: str          # ">=3.0", "^18.2.0"
    pinned_version: str        # "3.0.1" or ""
    status: str                # "current", "outdated", "deprecated", "unknown"
    group: str                 # "main", "dev", etc.


@dataclass
class SharedDependency:
    """A package used by multiple modules (within the same ecosystem)."""

    package: str               # "requests", "react"
    ecosystem: str             # "pip", "npm"
    consumers: list[str]       # Module IDs: ["pip:.", "pip:workers"]
    consumer_labels: list[str] # Human labels
    versions: dict[str, str]   # module_id → version spec
    conflict: bool             # True if consumers want different versions
    status: str                # Worst status across consumers

    def to_dict(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "ecosystem": self.ecosystem,
            "consumers": self.consumers,
            "consumer_labels": self.consumer_labels,
            "versions": self.versions,
            "conflict": self.conflict,
            "status": self.status,
            "shared_by": len(self.consumers),
        }


@dataclass
class ImpactAnalysis:
    """Blast radius for upgrading one package."""

    package: str
    ecosystem: str
    from_version: str
    to_version: str
    affected_modules: list[str]
    affected_labels: list[str]
    breaking: bool             # True if major version bump
    shared_by: int
    risk: Literal["low", "medium", "high"]
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "ecosystem": self.ecosystem,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "affected_modules": self.affected_modules,
            "affected_labels": self.affected_labels,
            "breaking": self.breaking,
            "shared_by": self.shared_by,
            "risk": self.risk,
            "detail": self.detail,
        }


@dataclass
class DependencyGraph:
    """Full graph: edges + shared deps + module list."""

    edges: list[DependencyEdge] = field(default_factory=list)
    shared: list[SharedDependency] = field(default_factory=list)
    modules: list[dict[str, str]] = field(default_factory=list)  # [{id, label, ecosystem}]
    total_packages: int = 0
    total_shared: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "edges": [
                {
                    "source": e.source,
                    "source_label": e.source_label,
                    "target": e.target,
                    "ecosystem": e.ecosystem,
                    "version_spec": e.version_spec,
                    "status": e.status,
                    "group": e.group,
                }
                for e in self.edges
            ],
            "shared": [s.to_dict() for s in self.shared],
            "modules": self.modules,
            "total_packages": self.total_packages,
            "total_shared": self.total_shared,
        }


# ═════════════════════════════════════════════════════════════════
#  Graph construction
# ═════════════════════════════════════════════════════════════════


def build_graph(tree_data: dict) -> DependencyGraph:
    """Build the dependency graph from tree data (serialized dict).

    Args:
        tree_data: Output of ``TreeNode.to_dict()`` — the full tree
            as returned by the ``dependency.tree`` mediator node.

    Returns:
        ``DependencyGraph`` with edges, shared dependencies, and module list.
    """
    graph = DependencyGraph()
    # package_key → list of (module_id, module_label, version_spec, status, group)
    package_consumers: dict[str, list[tuple[str, str, str, str, str]]] = {}

    for eco_node in tree_data.get("children", []):
        eco_id = eco_node.get("ecosystem", "")
        module_id = eco_node.get("id", "")
        module_label = eco_node.get("label", module_id)

        graph.modules.append({
            "id": module_id,
            "label": module_label,
            "ecosystem": eco_id,
        })

        for pkg in eco_node.get("children", []):
            pkg_name = _extract_name(pkg)
            version_spec = pkg.get("version", "")
            status = pkg.get("status", "unknown")
            group = pkg.get("group", "main")

            # Add edge
            graph.edges.append(DependencyEdge(
                source=module_id,
                source_label=module_label,
                target=pkg_name,
                ecosystem=eco_id,
                version_spec=version_spec,
                pinned_version=version_spec,
                status=status,
                group=group,
            ))

            graph.total_packages += 1

            # Track consumers for shared dep detection
            # Key by (ecosystem, package_name) — only shared within same ecosystem
            pkey = f"{eco_id}:{pkg_name}"
            if pkey not in package_consumers:
                package_consumers[pkey] = []
            package_consumers[pkey].append((module_id, module_label, version_spec, status, group))

    # Identify shared dependencies (used by 2+ modules)
    for pkey, consumers in package_consumers.items():
        if len(consumers) < 2:
            continue

        eco_id, pkg_name = pkey.split(":", 1)
        module_ids = [c[0] for c in consumers]
        module_labels = [c[1] for c in consumers]
        versions = {c[0]: c[2] for c in consumers}

        # Conflict = different version specs across consumers
        unique_versions = set(v for v in versions.values() if v)
        conflict = len(unique_versions) > 1

        # Worst status
        status = _worst_status([c[3] for c in consumers])

        graph.shared.append(SharedDependency(
            package=pkg_name,
            ecosystem=eco_id,
            consumers=module_ids,
            consumer_labels=module_labels,
            versions=versions,
            conflict=conflict,
            status=status,
        ))

    graph.total_shared = len(graph.shared)
    return graph


# ═════════════════════════════════════════════════════════════════
#  Impact analysis
# ═════════════════════════════════════════════════════════════════


def analyze_impact(
    graph: DependencyGraph,
    ecosystem: str,
    package: str,
    to_version: str,
) -> ImpactAnalysis | None:
    """Compute blast radius for upgrading a package.

    Args:
        graph: The dependency graph.
        ecosystem: Ecosystem ID (e.g. ``"pip"``).
        package: Package name (e.g. ``"requests"``).
        to_version: Target version (e.g. ``"2.32.3"``).

    Returns:
        ``ImpactAnalysis`` if the package exists in the graph, else ``None``.
    """
    # Find all edges for this package in this ecosystem
    matching = [e for e in graph.edges if e.target == package and e.ecosystem == ecosystem]
    if not matching:
        return None

    from_version = matching[0].pinned_version or matching[0].version_spec
    affected_modules = list(dict.fromkeys(e.source for e in matching))
    affected_labels = list(dict.fromkeys(e.source_label for e in matching))
    shared_by = len(affected_modules)

    # Determine if breaking (major version bump)
    breaking = _is_major_bump(from_version, to_version)

    # Risk assessment
    if breaking and shared_by > 1:
        risk: Literal["low", "medium", "high"] = "high"
    elif breaking or shared_by > 2:
        risk = "medium"
    else:
        risk = "low"

    # Human detail
    if shared_by == 1:
        detail = f"{package} is used in {affected_labels[0]}. Update will affect this module only."
    else:
        modules_str = ", ".join(affected_labels[:5])
        if len(affected_labels) > 5:
            modules_str += f" and {len(affected_labels) - 5} more"
        detail = f"{package} is shared by {shared_by} modules ({modules_str}). Update will affect all of them."
        if _has_version_conflict(matching):
            detail += " Warning: modules currently use different version specs."

    return ImpactAnalysis(
        package=package,
        ecosystem=ecosystem,
        from_version=from_version,
        to_version=to_version,
        affected_modules=affected_modules,
        affected_labels=affected_labels,
        breaking=breaking,
        shared_by=shared_by,
        risk=risk,
        detail=detail,
    )


# ═════════════════════════════════════════════════════════════════
#  Internal helpers
# ═════════════════════════════════════════════════════════════════


def _extract_name(pkg_node: dict) -> str:
    """Extract package name from a tree node.

    Label format is ``"name version"`` or ``"name"``.
    """
    label = pkg_node.get("label", "")
    return label.split(" ")[0] if " " in label else label


_STATUS_SEVERITY = {
    "current": 0, "unknown": 1, "outdated": 2,
    "deprecated": 3, "eol": 4, "yanked": 5,
}


def _worst_status(statuses: list[str]) -> str:
    """Return the most severe status from a list."""
    worst = "unknown"
    worst_sev = 0
    for s in statuses:
        sev = _STATUS_SEVERITY.get(s, 1)
        if sev > worst_sev:
            worst_sev = sev
            worst = s
    return worst


def _is_major_bump(from_ver: str, to_ver: str) -> bool:
    """Check if upgrading from_ver → to_ver crosses a major version boundary."""
    from_parts = _ver_parts(from_ver)
    to_parts = _ver_parts(to_ver)
    if not from_parts or not to_parts:
        return False
    return to_parts[0] > from_parts[0]


def _ver_parts(ver: str) -> list[int]:
    """Extract numeric version parts, stripping prefixes like >= ^ ~ v."""
    import re
    cleaned = re.sub(r'^[^\d]*', '', ver)
    parts = []
    for p in cleaned.split(".")[:3]:
        try:
            parts.append(int(re.match(r'\d+', p).group()))  # type: ignore
        except (AttributeError, ValueError):
            break
    return parts


def _has_version_conflict(edges: list[DependencyEdge]) -> bool:
    """Check if edges for the same package have different version specs."""
    specs = set(e.version_spec for e in edges if e.version_spec)
    return len(specs) > 1
