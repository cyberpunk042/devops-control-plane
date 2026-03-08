"""
Graph Builder Module
====================
Build relationship graphs from analyzed code.

A graph is nodes + edges where:
- **Nodes** = Classes (or modules depending on diagram type)
- **Edges** = Relationships (inheritance, composition, dependency, uses)

Pipeline position: discover → parse → **graph** → render → report
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from .code_analyzer import ClassInfo, ProjectAnalysis


# ═══════════════════════════════════════════════════════════════════
#  Data models
# ═══════════════════════════════════════════════════════════════════


class RelationType(Enum):
    """Types of relationships between classes."""

    INHERITS = "inherits"              # A extends B (solid line, closed arrow)
    IMPLEMENTS = "implements"          # A implements B (dashed line, closed arrow)
    COMPOSES = "composes"              # A has-a B (solid line, filled diamond)
    AGGREGATES = "aggregates"          # A contains B (solid line, open diamond)
    DEPENDS = "depends"                # A uses B (dashed line, open arrow)
    ASSOCIATES = "associates"          # A knows B (solid line, open arrow)


@dataclass
class GraphNode:
    """A node in the relationship graph.

    Typically represents a class, but can also represent
    a module or a package depending on the graph type.
    """

    id: str                            # Unique identifier (qualified class name)
    label: str                         # Display label (short class name)
    kind: str = "class"                # "class" | "abstract" | "interface" | "dataclass" | "module"
    package: str = ""                  # Grouping key (module/package path)

    fields: list[str] = field(default_factory=list)
                                       # Field declarations for display
                                       # e.g., ["- name: str", "+ value: int"]
    methods: list[str] = field(default_factory=list)
                                       # Method declarations for display
                                       # e.g., ["+ run()", "- _validate()"]

    metadata: dict = field(default_factory=dict)
                                       # Additional data (file, lines, etc.)


@dataclass
class GraphEdge:
    """A directed edge in the relationship graph."""

    source: str                        # Source node ID
    target: str                        # Target node ID
    relation: RelationType             # Type of relationship
    label: str = ""                    # Optional edge label
    cardinality: str = ""              # Optional cardinality ("1", "*", "0..1", etc.)


@dataclass
class ClassGraph:
    """A complete relationship graph.

    Contains nodes (classes) and edges (relationships).
    This is the intermediate representation between code analysis
    and diagram rendering.
    """

    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    title: str = ""
    scope: str = ""                    # What was analyzed (package, file, project)

    def add_node(self, node: GraphNode) -> None:
        """Add a node to the graph."""
        self.nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        """Add an edge to the graph. Deduplication by (source, target, relation)."""
        key = (edge.source, edge.target, edge.relation)
        # Don't add duplicate edges
        for existing in self.edges:
            if (existing.source, existing.target, existing.relation) == key:
                return
        self.edges.append(edge)

    def filter_by_package(self, package: str) -> ClassGraph:
        """Return a subgraph containing only nodes in the given package."""
        filtered = ClassGraph(title=self.title, scope=package)

        # Normalize: strip leading "src." so both "core.x" and "src.core.x" match
        norm_pkg = package.removeprefix("src.")

        for node_id, node in self.nodes.items():
            norm_node = node.package.removeprefix("src.")
            if norm_node == norm_pkg or norm_node.startswith(norm_pkg + "."):
                filtered.add_node(node)

        # Keep edges where both source and target are in the filtered nodes
        for edge in self.edges:
            if edge.source in filtered.nodes and edge.target in filtered.nodes:
                filtered.add_edge(edge)

        return filtered

    def get_connected_components(self) -> list[list[str]]:
        """Return connected components (groups of related classes)."""
        if not self.nodes:
            return []

        # Build undirected adjacency list
        adj: dict[str, set[str]] = {nid: set() for nid in self.nodes}
        for edge in self.edges:
            if edge.source in adj and edge.target in adj:
                adj[edge.source].add(edge.target)
                adj[edge.target].add(edge.source)

        visited: set[str] = set()
        components: list[list[str]] = []

        for start in self.nodes:
            if start in visited:
                continue
            # BFS from start
            component: list[str] = []
            queue = deque([start])
            visited.add(start)
            while queue:
                current = queue.popleft()
                component.append(current)
                for neighbor in sorted(adj[current]):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            components.append(sorted(component))

        return components

    def get_orphan_nodes(self) -> list[str]:
        """Return nodes with no edges (standalone classes)."""
        connected: set[str] = set()
        for edge in self.edges:
            connected.add(edge.source)
            connected.add(edge.target)
        return sorted(nid for nid in self.nodes if nid not in connected)


# ═══════════════════════════════════════════════════════════════════
#  Graph analysis helpers — smart output extraction
# ═══════════════════════════════════════════════════════════════════


def _normalize_package(pkg: str) -> str:
    """Strip leading 'src.' prefix from a package name."""
    return pkg.removeprefix("src.")


def _package_at_depth(pkg: str, depth: int) -> str:
    """Truncate a package to a given depth.

    Example: _package_at_depth("core.services.audit.models", 2) → "core.services"
    """
    parts = _normalize_package(pkg).split(".")
    return ".".join(parts[:depth]) if len(parts) >= depth else ".".join(parts)


def extract_package_dependencies(
    graph: ClassGraph,
    depth: int = 2,
) -> tuple[dict[str, list[str]], list[tuple[str, str]]]:
    """Aggregate class-level edges into package-level dependencies.

    Groups all classes by their package truncated to *depth* levels,
    then aggregates class-level edges into package-to-package deps.

    Args:
        graph: Full class graph.
        depth: Module depth for grouping
               (2 = core.services, 3 = core.services.audit).

    Returns:
        (packages, dependencies) where:
        - packages: {package_name: [class_label, ...]}
        - dependencies: [(src_pkg, tgt_pkg), ...] deduplicated, sorted
    """
    packages: dict[str, list[str]] = {}

    for node in graph.nodes.values():
        pkg = _package_at_depth(node.package, depth)
        packages.setdefault(pkg, []).append(node.label)

    # Sort class lists for deterministic output
    for pkg in packages:
        packages[pkg] = sorted(packages[pkg])

    # Aggregate edges
    seen: set[tuple[str, str]] = set()
    deps: list[tuple[str, str]] = []

    for edge in graph.edges:
        src_node = graph.nodes.get(edge.source)
        tgt_node = graph.nodes.get(edge.target)
        if not src_node or not tgt_node:
            continue
        src_pkg = _package_at_depth(src_node.package, depth)
        tgt_pkg = _package_at_depth(tgt_node.package, depth)
        if src_pkg == tgt_pkg:
            continue  # intra-package, not a dependency
        pair = (src_pkg, tgt_pkg)
        if pair not in seen:
            seen.add(pair)
            deps.append(pair)

    return packages, sorted(deps)


def extract_inheritance_trees(
    graph: ClassGraph,
    min_children: int = 2,
) -> list[dict]:
    """Find all inheritance hierarchies with N+ children.

    Scans edges for INHERITS relationships and builds parent→children
    mappings. Only returns trees where the root has at least
    *min_children* direct inheritors.

    Args:
        graph: Full class graph.
        min_children: Minimum direct children to include a tree.

    Returns:
        List of dicts, each with:
        - root: node_id of the base class
        - root_label: display name of the base class
        - children: [node_id, ...] of direct inheritors
        - children_labels: [label, ...] of direct inheritors
    """
    # Build parent → [children] from INHERITS edges
    children_map: dict[str, list[str]] = {}
    for edge in graph.edges:
        if edge.relation == RelationType.INHERITS:
            # edge.source = child, edge.target = parent
            children_map.setdefault(edge.target, []).append(edge.source)

    # Also check IMPLEMENTS (for ABC → implementors)
    for edge in graph.edges:
        if edge.relation == RelationType.IMPLEMENTS:
            children_map.setdefault(edge.target, []).append(edge.source)

    # Find roots: nodes that are parents but not children of anything
    all_children = set()
    for kids in children_map.values():
        all_children.update(kids)

    trees: list[dict] = []
    for root_id, child_ids in children_map.items():
        if len(child_ids) < min_children:
            continue
        # Only include if root is NOT itself a child of someone else
        # (we want top-level hierarchies)
        if root_id in all_children:
            continue
        root_node = graph.nodes.get(root_id)
        root_label = root_node.label if root_node else root_id.split(".")[-1]
        child_labels = []
        for cid in sorted(child_ids):
            cn = graph.nodes.get(cid)
            child_labels.append(cn.label if cn else cid.split(".")[-1])
        trees.append({
            "root": root_id,
            "root_label": root_label,
            "children": sorted(child_ids),
            "children_labels": child_labels,
        })

    return sorted(trees, key=lambda t: len(t["children"]), reverse=True)


def extract_hub_classes(
    graph: ClassGraph,
    min_edges: int = 6,
) -> list[tuple[str, int]]:
    """Find classes with the most connections.

    Counts total edges (incoming + outgoing) per node and returns
    those with at least *min_edges* connections.

    Args:
        graph: Full class graph.
        min_edges: Minimum total edges to qualify as a hub.

    Returns:
        List of (node_id, edge_count) sorted by count descending.
    """
    from collections import Counter

    edge_count: Counter[str] = Counter()
    for edge in graph.edges:
        edge_count[edge.source] += 1
        edge_count[edge.target] += 1

    return [
        (nid, count)
        for nid, count in edge_count.most_common()
        if count >= min_edges and nid in graph.nodes
    ]


# ═══════════════════════════════════════════════════════════════════
#  Public function
# ═══════════════════════════════════════════════════════════════════


_VISIBILITY_MARKERS = {
    "public": "+",
    "protected": "#",
    "private": "-",
}


def build_class_graph(
    analysis: ProjectAnalysis,
    *,
    include_external: bool = False,
    include_stdlib: bool = False,
    scope: str | None = None,
) -> ClassGraph:
    """Build a class relationship graph from project analysis.

    Steps:
    1. Create a GraphNode for each ClassInfo
    2. Resolve inheritance → INHERITS edges
    3. Detect composition (fields of class types) → COMPOSES edges
    4. Detect dependencies (used in method bodies) → DEPENDS edges
    5. Group by package for visual layout

    Args:
        analysis: Output from ``code_analyzer.analyze_python_project()``.
        include_external: Include external library classes (e.g., BaseModel).
        include_stdlib: Include stdlib classes (e.g., ABC).
        scope: Limit to a specific package (e.g., "core.services.vault").

    Returns:
        ClassGraph ready for rendering.
    """
    graph = ClassGraph(
        title=f"Class Diagram — {scope or 'project'}",
        scope=scope or "",
    )

    # Index classes by short name and qualified name for resolution
    classes_by_name: dict[str, ClassInfo] = {}
    classes_by_qname: dict[str, ClassInfo] = {}

    # Normalize scope: the packages endpoint strips the "src." prefix,
    # but file_relative_module keeps it.  Accept both forms.
    scope_prefixes: list[str] = []
    if scope:
        scope_prefixes.append(scope)
        # If scope doesn't already start with "src.", also try with it
        if not scope.startswith("src."):
            scope_prefixes.append(f"src.{scope}")

    for cls in analysis.classes:
        # Apply scope filter — match if module starts with ANY prefix
        if scope_prefixes and not any(
            cls.module.startswith(p) for p in scope_prefixes
        ):
            continue
        classes_by_name[cls.name] = cls
        classes_by_qname[cls.qualified_name] = cls

    # Step 1: Create nodes
    for cls in classes_by_qname.values():
        node = _class_to_node(cls)
        graph.add_node(node)

    # Step 2: Resolve inheritance
    _resolve_inheritance(
        classes_by_name, classes_by_qname, graph,
        include_external=include_external,
        include_stdlib=include_stdlib,
    )

    # Step 3: Detect composition
    _detect_composition(classes_by_name, classes_by_qname, graph)

    # Step 4: Detect dependencies
    _detect_dependencies(classes_by_name, classes_by_qname, graph)

    return graph


# ═══════════════════════════════════════════════════════════════════
#  Internal helpers
# ═══════════════════════════════════════════════════════════════════


# Known stdlib / abstract bases to classify as IMPLEMENTS
_ABSTRACT_BASES = frozenset({
    "ABC", "ABCMeta", "abc.ABC", "abc.ABCMeta",
    "Protocol", "typing.Protocol",
})

# Known stdlib base classes to skip (not interesting for diagrams)
_STDLIB_BASES = frozenset({
    "object", "Exception", "BaseException",
    "ValueError", "TypeError", "RuntimeError", "KeyError",
    "OSError", "IOError", "AttributeError", "NotImplementedError",
    "ABC", "ABCMeta", "abc.ABC", "abc.ABCMeta",
    "Generic", "Protocol", "typing.Protocol", "typing.Generic",
})

# Type wrapper patterns — extract the inner type name
_TYPE_WRAPPERS = re.compile(
    r"^(?:list|List|set|Set|tuple|Tuple|dict|Dict|"
    r"Optional|Union|Sequence|Iterable|Iterator|"
    r"frozenset|FrozenSet|Deque|deque)\[(.+)\]$"
)


def _class_to_node(cls: ClassInfo) -> GraphNode:
    """Convert a ClassInfo to a GraphNode."""
    # Determine kind
    if cls.is_protocol:
        kind = "interface"
    elif cls.is_abstract:
        kind = "abstract"
    elif cls.is_dataclass:
        kind = "dataclass"
    else:
        kind = "class"

    # Build display strings for fields
    field_strs: list[str] = []
    for f in cls.fields:
        marker = _VISIBILITY_MARKERS.get(f.visibility, "+")
        field_strs.append(f"{marker} {f.name}: {f.type_annotation}")

    # Build display strings for methods
    method_strs: list[str] = []
    for m in cls.methods:
        marker = _VISIBILITY_MARKERS.get(m.visibility, "+")
        params = ", ".join(m.parameters)
        ret = f" {m.return_type}" if m.return_type else ""
        prefix = "async " if m.is_async else ""
        method_strs.append(f"{marker} {prefix}{m.name}({params}){ret}")

    # Package = module minus the class name
    package = cls.module

    return GraphNode(
        id=cls.qualified_name,
        label=cls.name,
        kind=kind,
        package=package,
        fields=field_strs,
        methods=method_strs,
        metadata={
            "file": cls.file_path,
            "lineno": cls.lineno,
            "end_lineno": cls.end_lineno,
            "docstring": cls.docstring,
        },
    )


def _resolve_inheritance(
    classes_by_name: dict[str, ClassInfo],
    classes_by_qname: dict[str, ClassInfo],
    graph: ClassGraph,
    *,
    include_external: bool = False,
    include_stdlib: bool = False,
) -> None:
    """Resolve inheritance relationships.

    For each class's bases:
    1. Try exact match in classes dict (same name)
    2. Try qualified match (import resolution)
    3. If unresolved and include_external, create a stub node
    4. Otherwise skip (external class not in scope)

    Edge type:
    - If base is ABC or Protocol → IMPLEMENTS
    - Otherwise → INHERITS
    """
    for cls in classes_by_qname.values():
        for base_name in cls.bases:
            # Strip generics for resolution: Generic[T] → Generic
            clean_base = _strip_generics(base_name)

            # Skip stdlib bases unless requested
            if clean_base in _STDLIB_BASES and not include_stdlib:
                continue

            # Try to resolve to a known class
            target_qname = _resolve_class_name(
                clean_base, classes_by_name, classes_by_qname,
            )

            if target_qname is None:
                # Unresolved class — create stub if requested
                is_stdlib_base = clean_base in _STDLIB_BASES
                should_stub = (
                    (is_stdlib_base and include_stdlib)
                    or (not is_stdlib_base and include_external)
                )
                if should_stub:
                    package_label = "(stdlib)" if is_stdlib_base else "(external)"
                    stub = GraphNode(
                        id=clean_base,
                        label=clean_base,
                        kind="class",
                        package=package_label,
                    )
                    graph.add_node(stub)
                    target_qname = clean_base
                else:
                    continue

            # Determine edge type
            if clean_base in _ABSTRACT_BASES:
                relation = RelationType.IMPLEMENTS
            else:
                relation = RelationType.INHERITS

            graph.add_edge(GraphEdge(
                source=cls.qualified_name,
                target=target_qname,
                relation=relation,
                label=base_name,
            ))


def _detect_composition(
    classes_by_name: dict[str, ClassInfo],
    classes_by_qname: dict[str, ClassInfo],
    graph: ClassGraph,
) -> None:
    """Detect composition relationships from field types.

    For each class's fields:
    1. Check if type_annotation refers to another analyzed class
    2. If yes → COMPOSES edge (A has-a B)
    3. Handle common patterns:
       - ``list[ClassName]`` → aggregation (0..*)
       - ``Optional[ClassName]`` → association (0..1)
       - ``ClassName`` → composition (1)
    """
    for cls in classes_by_qname.values():
        for fld in cls.fields:
            type_str = fld.type_annotation
            if type_str == "Any":
                continue

            # Try to extract inner type from wrappers
            inner, cardinality, relation = _parse_type_for_composition(type_str)

            target_qname = _resolve_class_name(
                inner, classes_by_name, classes_by_qname,
            )

            if target_qname is None:
                continue

            # Don't add self-composition
            if target_qname == cls.qualified_name:
                continue

            graph.add_edge(GraphEdge(
                source=cls.qualified_name,
                target=target_qname,
                relation=relation,
                label=fld.name,
                cardinality=cardinality,
            ))


def _detect_dependencies(
    classes_by_name: dict[str, ClassInfo],
    classes_by_qname: dict[str, ClassInfo],
    graph: ClassGraph,
) -> None:
    """Detect dependency relationships from method parameters and return types.

    For each class's methods:
    1. Check parameter types for references to other analyzed classes
    2. Check return types for references to other analyzed classes
    3. If found → DEPENDS edge (A uses B)

    This is weaker than composition — the class doesn't own the
    dependency, it just uses it temporarily.
    """
    # Collect existing edges to avoid duplicating composition as dependency
    existing_targets: dict[str, set[str]] = {}
    for edge in graph.edges:
        existing_targets.setdefault(edge.source, set()).add(edge.target)

    for cls in classes_by_qname.values():
        for method in cls.methods:
            # Check parameter names as type references
            for param in method.parameters:
                target = _resolve_class_name(
                    param, classes_by_name, classes_by_qname,
                )
                if target and target != cls.qualified_name:
                    if target not in existing_targets.get(cls.qualified_name, set()):
                        graph.add_edge(GraphEdge(
                            source=cls.qualified_name,
                            target=target,
                            relation=RelationType.DEPENDS,
                        ))

            # Check return type
            if method.return_type:
                clean_ret = _strip_generics(method.return_type)
                target = _resolve_class_name(
                    clean_ret, classes_by_name, classes_by_qname,
                )
                if target and target != cls.qualified_name:
                    if target not in existing_targets.get(cls.qualified_name, set()):
                        graph.add_edge(GraphEdge(
                            source=cls.qualified_name,
                            target=target,
                            relation=RelationType.DEPENDS,
                        ))


# ═══════════════════════════════════════════════════════════════════
#  Resolution helpers
# ═══════════════════════════════════════════════════════════════════


def _resolve_class_name(
    name: str,
    classes_by_name: dict[str, ClassInfo],
    classes_by_qname: dict[str, ClassInfo],
) -> str | None:
    """Try to resolve a class name to a qualified name.

    1. Exact match in qualified names
    2. Short name match in class names
    3. None if unresolved
    """
    if name in classes_by_qname:
        return name
    if name in classes_by_name:
        return classes_by_name[name].qualified_name
    return None


def _strip_generics(name: str) -> str:
    """Strip generic type parameters: ``Generic[T]`` → ``Generic``."""
    bracket = name.find("[")
    if bracket >= 0:
        return name[:bracket]
    return name


def _parse_type_for_composition(
    type_str: str,
) -> tuple[str, str, RelationType]:
    """Parse a type annotation to determine composition relationship.

    Returns:
        (inner_type_name, cardinality, relation_type)
    """
    # Check for wrapper types
    match = _TYPE_WRAPPERS.match(type_str)
    if match:
        inner = match.group(1).strip()
        wrapper = type_str[:type_str.index("[")]

        if wrapper in ("Optional",):
            return _strip_generics(inner), "0..1", RelationType.ASSOCIATES
        if wrapper in ("list", "List", "set", "Set", "tuple", "Tuple",
                       "Sequence", "Iterable", "Iterator",
                       "frozenset", "FrozenSet", "Deque", "deque"):
            return _strip_generics(inner), "*", RelationType.AGGREGATES
        if wrapper in ("dict", "Dict"):
            # For dict, the value type is the interesting one
            parts = _split_type_args(inner)
            if len(parts) >= 2:
                return _strip_generics(parts[1].strip()), "*", RelationType.AGGREGATES
            return _strip_generics(inner), "*", RelationType.AGGREGATES

    # Check for Union type: X | Y
    if " | " in type_str:
        # Check if None is one side (Optional equivalent)
        parts = [p.strip() for p in type_str.split(" | ")]
        non_none = [p for p in parts if p != "None"]
        if len(non_none) == 1:
            return _strip_generics(non_none[0]), "0..1", RelationType.ASSOCIATES
        # Multiple non-None types — can't determine composition
        return type_str, "", RelationType.ASSOCIATES

    # Direct type reference → composition (1)
    return _strip_generics(type_str), "1", RelationType.COMPOSES


def _split_type_args(type_str: str) -> list[str]:
    """Split type arguments respecting nested brackets.

    ``int, dict[str, int]`` → ``["int", "dict[str, int]"]``
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []

    for char in type_str:
        if char == "[":
            depth += 1
            current.append(char)
        elif char == "]":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)

    if current:
        parts.append("".join(current).strip())

    return parts
