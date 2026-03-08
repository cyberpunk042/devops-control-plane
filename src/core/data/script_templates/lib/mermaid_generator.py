"""
Mermaid Generator Module
========================
Convert graphs into Mermaid syntax.

Supports multiple diagram types:
- Class diagrams (full UML-style with fields, methods, relationships)
- Flowcharts (simplified dependency overview)
- Component diagrams (package-level architecture)

Pipeline position: discover → parse → graph → **render** → report
"""

from __future__ import annotations

from dataclasses import dataclass

from .graph_builder import ClassGraph, GraphEdge, GraphNode, RelationType


# ═══════════════════════════════════════════════════════════════════
#  Configuration
# ═══════════════════════════════════════════════════════════════════


@dataclass
class MermaidConfig:
    """Configuration for Mermaid diagram generation."""

    direction: str = "TD"              # "TD" (top-down), "LR" (left-right), "BT", "RL"
    show_fields: bool = True           # Show class fields
    show_methods: bool = True          # Show class methods
    show_visibility: bool = True       # Show +/- visibility markers
    max_fields: int = 10               # Max fields to show per class (truncate)
    max_methods: int = 15              # Max methods to show per class (truncate)
    group_by_package: bool = True      # Group classes by package (subgraph)
    include_orphans: bool = False      # Include classes with no relationships
    theme: str = "default"             # Mermaid theme


# ═══════════════════════════════════════════════════════════════════
#  Public renderers
# ═══════════════════════════════════════════════════════════════════


def render_class_diagram(
    graph: ClassGraph,
    *,
    config: MermaidConfig | None = None,
) -> str:
    """Render a ClassGraph as a Mermaid class diagram.

    Output format::

        classDiagram
            direction TD

            namespace core_services {
                class EventBus {
                    - _lock: Lock
                    - _events: list
                    + publish(type, key, data)
                    + subscribe(since) Iterator
                }
            }

            EventBus --|> ABC : inherits
            ArtifactEngine ..> EventBus : uses

    Args:
        graph: ClassGraph to render.
        config: Optional rendering configuration.

    Returns:
        Complete Mermaid block (without the \\`\\`\\`mermaid fences).
    """
    cfg = config or MermaidConfig()
    lines: list[str] = []

    lines.append("classDiagram")
    lines.append(f"    direction {cfg.direction}")
    lines.append("")

    # Determine which nodes to render
    orphans = set(graph.get_orphan_nodes())
    nodes_to_render = {
        nid: node for nid, node in graph.nodes.items()
        if cfg.include_orphans or nid not in orphans
    }

    if not nodes_to_render:
        # Render all nodes if everything is orphan and include_orphans is off
        # but we have nodes — just show them
        if graph.nodes:
            nodes_to_render = dict(graph.nodes)

    # Build short-ID map: node.id → short Mermaid identifier
    # Use node.label when unique; fall back to full sanitized id on collision
    label_counts: dict[str, int] = {}
    for node in nodes_to_render.values():
        label_counts[node.label] = label_counts.get(node.label, 0) + 1

    short_id_map: dict[str, str] = {}
    for nid, node in nodes_to_render.items():
        if label_counts[node.label] == 1:
            short_id_map[nid] = _sanitize_id(node.label)
        else:
            short_id_map[nid] = _sanitize_id(nid)

    # Group by package
    if cfg.group_by_package:
        packages: dict[str, list[GraphNode]] = {}
        for node in nodes_to_render.values():
            pkg = node.package or "(root)"
            packages.setdefault(pkg, []).append(node)

        for pkg_name in sorted(packages):
            safe_pkg = _sanitize_id(pkg_name)
            lines.append(f"    namespace {safe_pkg} {{")
            for node in sorted(packages[pkg_name], key=lambda n: n.label):
                _render_class_block(node, lines, cfg, indent=8,
                                    mermaid_id=short_id_map.get(node.id))
            lines.append("    }")
            lines.append("")
    else:
        for node in sorted(nodes_to_render.values(), key=lambda n: n.label):
            _render_class_block(node, lines, cfg, indent=4,
                                mermaid_id=short_id_map.get(node.id))
        lines.append("")

    # Render relationships
    for edge in graph.edges:
        # Only render edges where both nodes are in our render set
        if edge.source not in nodes_to_render and edge.target not in nodes_to_render:
            continue
        arrow = _relation_arrow(edge.relation)
        src = short_id_map.get(edge.source, _sanitize_id(edge.source))
        tgt = short_id_map.get(edge.target, _sanitize_id(edge.target))
        # Skip edge label when it's just the target class name (redundant)
        label = edge.label or ""
        tgt_node = nodes_to_render.get(edge.target)
        if tgt_node and label == tgt_node.label:
            label = ""
        label_part = f" : {label}" if label else ""
        lines.append(f"    {src} {arrow} {tgt}{label_part}")

    return "\n".join(lines)


def render_flowchart(
    graph: ClassGraph,
    *,
    config: MermaidConfig | None = None,
) -> str:
    """Render a ClassGraph as a Mermaid flowchart.

    Simpler than class diagram — shows only relationships,
    no fields/methods. Good for dependency overview.

    Output format::

        graph TD
            EventBus --> StreamSubprocess
            RunTracker --> EventBus
            ScriptExecutor --> RunTracker

    Args:
        graph: ClassGraph to render.
        config: Optional rendering configuration.

    Returns:
        Complete Mermaid flowchart block.
    """
    cfg = config or MermaidConfig()
    lines: list[str] = []

    lines.append(f"graph {cfg.direction}")
    lines.append("")

    # Render edges
    for edge in graph.edges:
        src = _sanitize_id(edge.source)
        tgt = _sanitize_id(edge.target)
        arrow = _flowchart_arrow(edge.relation)
        if edge.label:
            lines.append(f"    {src} {arrow}|{edge.label}| {tgt}")
        else:
            lines.append(f"    {src} {arrow} {tgt}")

    return "\n".join(lines)


def render_component_diagram(
    packages: dict[str, list[str]],
    dependencies: list[tuple[str, str]],
) -> str:
    """Render a package-level component diagram.

    Shows packages (not individual classes) and their dependencies.
    Good for architectural overview.

    Args:
        packages: Mapping of package name → list of class names in that package.
        dependencies: List of (source_package, target_package) dependency pairs.

    Returns:
        Complete Mermaid flowchart representing package dependencies.
    """
    lines: list[str] = []

    lines.append("graph TD")
    lines.append("")

    # Render package nodes with class counts
    for pkg_name in sorted(packages):
        safe = _sanitize_id(pkg_name)
        count = len(packages[pkg_name])
        lines.append(f"    {safe}[{pkg_name}<br/>{count} classes]")

    lines.append("")

    # Render dependencies (deduplicated)
    seen: set[tuple[str, str]] = set()
    for src, tgt in dependencies:
        if src == tgt:
            continue
        key = (src, tgt)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"    {_sanitize_id(src)} --> {_sanitize_id(tgt)}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
#  Internal helpers
# ═══════════════════════════════════════════════════════════════════


def _render_class_block(
    node: GraphNode,
    lines: list[str],
    cfg: MermaidConfig,
    indent: int = 4,
    mermaid_id: str | None = None,
) -> None:
    """Render a single class block in Mermaid class diagram syntax."""
    pad = " " * indent
    safe_label = mermaid_id or _sanitize_id(node.id)

    lines.append(f"{pad}class {safe_label} {{")

    # Class annotation (stereotype)
    if node.kind == "abstract":
        lines.append(f"{pad}    <<abstract>>")
    elif node.kind == "interface":
        lines.append(f"{pad}    <<interface>>")
    elif node.kind == "dataclass":
        lines.append(f"{pad}    <<dataclass>>")

    # Fields
    if cfg.show_fields and node.fields:
        display_fields = _truncate_members(
            node.fields, cfg.max_fields, label="fields",
        )
        for field_str in display_fields:
            escaped = _escape_mermaid(field_str)
            if not cfg.show_visibility:
                # Strip the + / # / - prefix
                escaped = _strip_visibility_prefix(escaped)
            lines.append(f"{pad}    {escaped}")

    # Methods
    if cfg.show_methods and node.methods:
        display_methods = _truncate_members(
            node.methods, cfg.max_methods, label="methods",
        )
        for method_str in display_methods:
            escaped = _escape_mermaid(method_str)
            if not cfg.show_visibility:
                escaped = _strip_visibility_prefix(escaped)
            lines.append(f"{pad}    {escaped}")

    lines.append(f"{pad}}}")


def _visibility_marker(visibility: str) -> str:
    """Convert visibility to Mermaid marker.

    "public"    → "+"
    "protected" → "#"
    "private"   → "-"
    """
    markers = {
        "public": "+",
        "protected": "#",
        "private": "-",
    }
    return markers.get(visibility, "+")


def _escape_mermaid(text: str) -> str:
    """Escape special characters for Mermaid syntax.

    Characters that need escaping: < > { } | : " ~
    """
    replacements = {
        "<": "‹",
        ">": "›",
        "{": "❴",
        "}": "❵",
        '"': "'",
        "~": "∼",
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


def _relation_arrow(relation: RelationType) -> str:
    """Convert RelationType to Mermaid class diagram arrow syntax.

    INHERITS    → "--|>"     (solid line, closed arrow)
    IMPLEMENTS  → "..|>"     (dashed line, closed arrow)
    COMPOSES    → "*--"      (solid line, filled diamond)
    AGGREGATES  → "o--"      (solid line, open diamond)
    DEPENDS     → "..>"      (dashed line, open arrow)
    ASSOCIATES  → "-->"      (solid line, open arrow)
    """
    arrows = {
        RelationType.INHERITS: "--|>",
        RelationType.IMPLEMENTS: "..|>",
        RelationType.COMPOSES: "*--",
        RelationType.AGGREGATES: "o--",
        RelationType.DEPENDS: "..>",
        RelationType.ASSOCIATES: "-->",
    }
    return arrows.get(relation, "-->")


def _flowchart_arrow(relation: RelationType) -> str:
    """Convert RelationType to Mermaid flowchart arrow syntax."""
    if relation in (RelationType.DEPENDS, RelationType.IMPLEMENTS):
        return "-.->",
    return "-->"


def _truncate_members(
    items: list[str],
    max_items: int,
    label: str = "more",
) -> list[str]:
    """Truncate a list of members with a '... N more' indicator."""
    if len(items) <= max_items:
        return items
    truncated = items[:max_items]
    remaining = len(items) - max_items
    truncated.append(f"... {remaining} more {label}")
    return truncated


def _sanitize_id(name: str) -> str:
    """Sanitize a name for use as a Mermaid node identifier.

    Replaces dots, spaces, and other special chars with underscores.
    """
    result = name.replace(".", "_").replace(" ", "_")
    result = result.replace("(", "").replace(")", "")
    result = result.replace("<", "").replace(">", "")
    result = result.replace("[", "").replace("]", "")
    return result


def _strip_visibility_prefix(text: str) -> str:
    """Strip the visibility prefix (+, #, -) from a member string."""
    if text and text[0] in ("+", "#", "-") and len(text) > 1 and text[1] == " ":
        return text[2:]
    return text
