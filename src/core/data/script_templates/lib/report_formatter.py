"""
Report Formatter Module
=======================
Format analysis results into human-readable reports.

Supports two output formats:
- **Markdown**: Structured document with TOC, diagrams, and statistics
- **JSON**: Machine-readable data export for tooling integration

Pipeline position: discover → parse → graph → render → **report**
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .code_analyzer import ClassInfo, ProjectAnalysis
from .graph_builder import (
    ClassGraph,
    RelationType,
    extract_hub_classes,
    extract_inheritance_trees,
    extract_package_dependencies,
)
from .mermaid_generator import MermaidConfig, render_class_diagram, render_component_diagram


# ═══════════════════════════════════════════════════════════════════
#  Public functions
# ═══════════════════════════════════════════════════════════════════


def format_markdown_report(
    graph: ClassGraph,
    mermaid_output: str,
    *,
    title: str = "Class Diagram Report",
    include_toc: bool = True,
    include_stats: bool = True,
    analysis: ProjectAnalysis | None = None,
) -> str:
    """Format a complete Markdown report with diagram and metadata.

    Sections:
    1. Title + generation timestamp
    2. Table of contents (optional)
    3. Summary statistics (optional)
    4. Mermaid diagram
    5. Class index (all classes with details)
    6. Relationship summary

    Args:
        graph: ClassGraph with nodes and edges.
        mermaid_output: Pre-rendered Mermaid syntax string.
        title: Report title.
        include_toc: Include table of contents.
        include_stats: Include statistics section.
        analysis: Optional ProjectAnalysis for extra stats.

    Returns:
        Complete Markdown document as a string.
    """
    sections: list[tuple[str, str]] = []  # (heading, content)

    # Header
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header = f"# {title}\n\n> Generated: {timestamp}\n"

    # Statistics
    if include_stats:
        stats = _generate_stats(analysis, graph)
        sections.append(("Statistics", stats))

    # Diagram
    diagram_section = f"```mermaid\n{mermaid_output}\n```"
    sections.append(("Diagram", diagram_section))

    # Class Index
    if graph.nodes:
        index = _generate_class_index(graph)
        sections.append(("Class Index", index))

    # Relationship Summary
    if graph.edges:
        rel_summary = _generate_relationship_summary(graph)
        sections.append(("Relationships", rel_summary))

    # Assemble document
    parts: list[str] = [header]

    if include_toc and sections:
        toc = _generate_toc(sections)
        parts.append(toc)

    for heading, content in sections:
        parts.append(f"## {heading}\n\n{content}\n")

    return "\n".join(parts)


def format_json_report(
    analysis: ProjectAnalysis,
    graph: ClassGraph,
) -> str:
    """Format analysis results as a JSON document.

    Includes:
    - Metadata (timestamp, file counts, class counts)
    - Classes (with fields, methods, bases)
    - Relationships (edges with types)
    - Packages (grouped class lists)

    Args:
        analysis: ProjectAnalysis with all class data.
        graph: ClassGraph with relationships.

    Returns:
        Pretty-printed JSON string.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # Build class list
    classes: list[dict] = []
    for cls in analysis.classes:
        classes.append(_class_to_dict(cls))

    # Build edge list
    edges: list[dict] = []
    for edge in graph.edges:
        edges.append({
            "source": edge.source,
            "target": edge.target,
            "relation": edge.relation.value,
            "label": edge.label,
            "cardinality": edge.cardinality,
        })

    # Build package summary
    packages: dict[str, list[str]] = {}
    for node in graph.nodes.values():
        pkg = node.package or "(root)"
        packages.setdefault(pkg, []).append(node.label)

    report = {
        "metadata": {
            "generated": timestamp,
            "files_analyzed": analysis.files_analyzed,
            "files_with_errors": analysis.files_with_errors,
            "total_classes": analysis.total_classes,
            "total_relationships": len(graph.edges),
        },
        "classes": classes,
        "relationships": edges,
        "packages": packages,
    }

    if analysis.analysis_errors:
        report["errors"] = analysis.analysis_errors

    return json.dumps(report, indent=2, default=str)


def write_report(
    content: str,
    output_path: Path,
    *,
    create_parents: bool = True,
) -> Path:
    """Write report content to a file.

    Args:
        content: Report content (Markdown or JSON string).
        output_path: Target file path.
        create_parents: Create parent directories if needed.

    Returns:
        The absolute path to the written file.
    """
    resolved = output_path.resolve()

    if create_parents:
        resolved.parent.mkdir(parents=True, exist_ok=True)

    resolved.write_text(content, encoding="utf-8")
    return resolved


def format_smart_report(
    analysis: ProjectAnalysis,
    graph: ClassGraph,
    *,
    title: str = "Class Architecture Report",
    max_depth: int = 3,
    detail_threshold: int = 15,
    small_threshold: int = 3,
) -> str:
    """Assemble a multi-view, multi-layer markdown document.

    Produces 5 views:
    1. Architecture overview (package-level component diagram)
    2. Inheritance forests (one diagram per hierarchy)
    3. Module details (recursive, overview/detail split by class count)
    4. Hub analysis (most-connected classes)
    5. Orphan index (table, not diagram)

    Args:
        analysis: ProjectAnalysis with all class data.
        graph: ClassGraph with nodes and edges.
        title: Report title.
        max_depth: Maximum module depth to recurse into.
        detail_threshold: Max classes for a full-detail diagram.
        small_threshold: Modules with ≤ this many classes get detail directly.

    Returns:
        Complete Markdown document as a string.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts: list[str] = []

    # ── Header ──
    total_classes = len(graph.nodes)
    total_edges = len(graph.edges)
    pkgs_d2, deps_d2 = extract_package_dependencies(graph, depth=2)
    total_modules = len(pkgs_d2)

    parts.append(f"# {title}\n")
    parts.append(
        f"> Generated: {timestamp}  |  "
        f"{total_classes} classes  |  "
        f"{total_edges} relationships  |  "
        f"{total_modules} modules\n"
    )

    # ── Collect sections for TOC ──
    toc_entries: list[tuple[str, int]] = []  # (heading, depth)

    # ── VIEW 1: Architecture Overview ──
    toc_entries.append(("Architecture Overview", 2))
    arch_mermaid = render_component_diagram(pkgs_d2, deps_d2)
    parts.append("## Architecture Overview\n")
    parts.append(f"```mermaid\n{arch_mermaid}\n```\n")

    # ── VIEW 2: Inheritance Forests ──
    trees = extract_inheritance_trees(graph, min_children=2)
    if trees:
        toc_entries.append(("Inheritance Forests", 2))
        parts.append("## Inheritance Forests\n")
        parts.append(
            f"> {len(trees)} inheritance hierarchies detected. "
            "Each shows a base class and its direct implementations.\n"
        )

        for tree in trees:
            heading = f"{tree['root_label']} ({len(tree['children'])} implementations)"
            toc_entries.append((heading, 3))
            parts.append(f"### {heading}\n")

            # Build a minimal subgraph: root + children, inherits edges only
            sub = ClassGraph(title=heading)
            root_node = graph.nodes.get(tree["root"])
            if root_node:
                sub.add_node(root_node)
            for cid in tree["children"]:
                cnode = graph.nodes.get(cid)
                if cnode:
                    sub.add_node(cnode)
            # Add only inheritance edges within this tree
            for edge in graph.edges:
                if edge.target == tree["root"] and edge.source in sub.nodes:
                    sub.add_edge(edge)

            cfg = MermaidConfig(
                show_fields=False,
                show_methods=False,
                group_by_package=False,
                include_orphans=True,
            )
            tree_mermaid = render_class_diagram(sub, config=cfg)
            parts.append(f"```mermaid\n{tree_mermaid}\n```\n")

    # ── VIEW 3: Module Details ──
    toc_entries.append(("Module Details", 2))
    parts.append("## Module Details\n")

    # Collect all depth-2 modules sorted by name
    d2_modules = sorted(pkgs_d2.items(), key=lambda x: x[0])

    # Separate small modules for grouping
    small_modules: list[tuple[str, list[str]]] = []

    for mod_name, class_labels in d2_modules:
        sub_graph = graph.filter_by_package(mod_name)
        node_count = len(sub_graph.nodes)

        if node_count == 0:
            continue

        if node_count <= small_threshold:
            small_modules.append((mod_name, class_labels))
            continue

        toc_entries.append((f"{mod_name} ({node_count} classes)", 3))
        section = _render_module_section(
            mod_name, sub_graph, graph, node_count,
            detail_threshold=detail_threshold,
            small_threshold=small_threshold,
            max_depth=max_depth,
            current_depth=2,
            heading_level=3,
        )
        parts.append(section)

    # Render small modules as a combined section
    if small_modules:
        combined_names = ", ".join(m for m, _ in small_modules)
        total_small = sum(len(cls) for _, cls in small_modules)
        toc_entries.append((f"Small Modules ({total_small} classes)", 3))
        parts.append(f"### Small Modules ({total_small} classes)\n")
        parts.append(f"> Modules: {combined_names}\n")

        # Build a combined subgraph
        combined = ClassGraph(title="Small Modules")
        for mod_name, _ in small_modules:
            sub = graph.filter_by_package(mod_name)
            for node in sub.nodes.values():
                combined.add_node(node)
            for edge in sub.edges:
                combined.add_edge(edge)

        cfg = MermaidConfig(
            show_fields=True,
            show_methods=True,
            include_orphans=True,
        )
        combined_mermaid = render_class_diagram(combined, config=cfg)
        parts.append(f"```mermaid\n{combined_mermaid}\n```\n")

    # ── VIEW 4: Hub Analysis ──
    hubs = extract_hub_classes(graph, min_edges=6)
    if hubs:
        toc_entries.append(("Hub Analysis", 2))
        parts.append("## Hub Analysis\n")
        parts.append(
            "> Classes with the most connections — critical nexus points "
            "for understanding system coupling.\n"
        )

        # Build a subgraph: hub nodes + their immediate neighbors
        hub_graph = ClassGraph(title="Hub Analysis")
        hub_ids = {nid for nid, _ in hubs}

        for nid, _ in hubs:
            node = graph.nodes.get(nid)
            if node:
                hub_graph.add_node(node)

        # Add immediate neighbors
        for edge in graph.edges:
            if edge.source in hub_ids or edge.target in hub_ids:
                for endpoint in (edge.source, edge.target):
                    if endpoint not in hub_graph.nodes:
                        n = graph.nodes.get(endpoint)
                        if n:
                            hub_graph.add_node(n)
                hub_graph.add_edge(edge)

        cfg = MermaidConfig(
            show_fields=False,
            show_methods=False,
            include_orphans=True,
        )
        hub_mermaid = render_class_diagram(hub_graph, config=cfg)
        parts.append(f"```mermaid\n{hub_mermaid}\n```\n")

        # Hub table
        parts.append("| Class | Connections | Module |\n")
        parts.append("|-------|------------|--------|\n")
        for nid, count in hubs:
            node = graph.nodes.get(nid)
            label = node.label if node else nid.split(".")[-1]
            pkg = node.package if node else ""
            parts.append(f"| **{label}** | {count} | {pkg} |\n")
        parts.append("")

    # ── VIEW 5: Orphan Index ──
    orphans = graph.get_orphan_nodes()
    if orphans:
        toc_entries.append(("Orphan Index", 2))
        parts.append("## Orphan Index\n")
        parts.append(
            f"> {len(orphans)} classes with no detected relationships. "
            "These may be utility classes, constants, or under-connected code.\n"
        )
        parts.append("| Class | Module | Kind | Fields | Methods |\n")
        parts.append("|-------|--------|------|--------|--------|\n")
        for oid in orphans:
            node = graph.nodes.get(oid)
            if not node:
                continue
            parts.append(
                f"| {node.label} | {node.package} | "
                f"{node.kind} | {len(node.fields)} | "
                f"{len(node.methods)} |\n"
            )
        parts.append("")

    # ── Insert TOC after header ──
    toc_lines: list[str] = ["## Table of Contents\n"]
    for heading, depth in toc_entries:
        indent = "  " * (depth - 2)
        anchor = heading.lower().replace(" ", "-").replace("(", "").replace(")", "")
        toc_lines.append(f"{indent}- [{heading}](#{anchor})")
    toc_lines.append("\n---\n")
    toc_block = "\n".join(toc_lines)

    # Insert TOC after the header (after first 2 parts)
    parts.insert(2, toc_block)

    return "\n".join(parts)


def _render_module_section(
    mod_name: str,
    sub_graph: ClassGraph,
    full_graph: ClassGraph,
    node_count: int,
    *,
    detail_threshold: int,
    small_threshold: int,
    max_depth: int,
    current_depth: int,
    heading_level: int,
) -> str:
    """Render a module section with smart overview/detail splitting.

    Args:
        mod_name: Module name (e.g., "core.services.audit").
        sub_graph: Filtered subgraph for this module.
        full_graph: Full class graph (for sub-module filtering).
        node_count: Number of classes in this module.
        detail_threshold: Max classes for full-detail diagram.
        small_threshold: Modules with <= this get detail directly.
        max_depth: Maximum depth to recurse into.
        current_depth: Current module depth level.
        heading_level: Markdown heading level (3, 4, 5...).

    Returns:
        Markdown section string.
    """
    hd = "#" * heading_level
    parts: list[str] = []
    parts.append(f"{hd} {mod_name} ({node_count} classes)\n")

    if node_count <= detail_threshold:
        # Small/medium: render full detail in one diagram
        cfg = MermaidConfig(
            show_fields=True,
            show_methods=True,
            include_orphans=True,
        )
        mermaid = render_class_diagram(sub_graph, config=cfg)
        parts.append(f"```mermaid\n{mermaid}\n```\n")
    else:
        # Large: render overview (names only), then recurse into sub-modules
        cfg = MermaidConfig(
            show_fields=False,
            show_methods=False,
            include_orphans=True,
        )
        overview_mermaid = render_class_diagram(sub_graph, config=cfg)
        parts.append(f"{hd}# Overview\n")
        parts.append(f"```mermaid\n{overview_mermaid}\n```\n")

        if current_depth < max_depth:
            # Find sub-modules at next depth level
            sub_pkgs: dict[str, int] = {}
            for node in sub_graph.nodes.values():
                norm = node.package.removeprefix("src.")
                pkg_parts = norm.split(".")
                next_depth = current_depth + 1
                if len(pkg_parts) >= next_depth:
                    sub_pkg = ".".join(pkg_parts[:next_depth])
                    sub_pkgs[sub_pkg] = sub_pkgs.get(sub_pkg, 0) + 1

            for sub_mod in sorted(sub_pkgs.keys()):
                sub_sub = full_graph.filter_by_package(sub_mod)
                sc = len(sub_sub.nodes)
                if sc == 0:
                    continue

                sub_section = _render_module_section(
                    sub_mod, sub_sub, full_graph, sc,
                    detail_threshold=detail_threshold,
                    small_threshold=small_threshold,
                    max_depth=max_depth,
                    current_depth=current_depth + 1,
                    heading_level=heading_level + 1,
                )
                parts.append(sub_section)

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════
#  Internal helpers
# ═══════════════════════════════════════════════════════════════════


def _generate_toc(sections: list[tuple[str, str]]) -> str:
    """Generate a table of contents from section headings.

    Args:
        sections: List of (heading, content) tuples.

    Returns:
        Markdown TOC with anchor links.
    """
    lines: list[str] = ["## Table of Contents\n"]
    for heading, _ in sections:
        anchor = heading.lower().replace(" ", "-")
        lines.append(f"- [{heading}](#{anchor})")
    lines.append("")
    return "\n".join(lines)


def _generate_stats(
    analysis: ProjectAnalysis | None,
    graph: ClassGraph,
) -> str:
    """Generate a statistics summary section.

    Args:
        analysis: Optional ProjectAnalysis for file-level stats.
        graph: ClassGraph for relationship stats.

    Returns:
        Markdown-formatted statistics table.
    """
    lines: list[str] = []

    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")

    if analysis:
        lines.append(f"| Files analyzed | {analysis.files_analyzed} |")
        lines.append(f"| Files with errors | {analysis.files_with_errors} |")
        lines.append(f"| Total classes | {analysis.total_classes} |")

    lines.append(f"| Nodes in graph | {len(graph.nodes)} |")
    lines.append(f"| Relationships | {len(graph.edges)} |")

    # Edge type breakdown
    edge_counts: dict[str, int] = {}
    for edge in graph.edges:
        edge_counts[edge.relation.value] = edge_counts.get(edge.relation.value, 0) + 1

    for rel_name, count in sorted(edge_counts.items()):
        lines.append(f"| ↳ {rel_name} | {count} |")

    # Components
    components = graph.get_connected_components()
    lines.append(f"| Connected components | {len(components)} |")

    orphans = graph.get_orphan_nodes()
    lines.append(f"| Orphan classes | {len(orphans)} |")

    # Package count
    packages = {n.package for n in graph.nodes.values() if n.package}
    lines.append(f"| Packages | {len(packages)} |")

    return "\n".join(lines)


def _generate_class_index(graph: ClassGraph) -> str:
    """Generate a class index with details.

    Lists all classes grouped by package with their fields and methods count.

    Args:
        graph: ClassGraph with nodes.

    Returns:
        Markdown-formatted class listing.
    """
    lines: list[str] = []

    # Group by package
    packages: dict[str, list[GraphNode]] = {}
    for node in graph.nodes.values():
        pkg = node.package or "(root)"
        packages.setdefault(pkg, []).append(node)

    for pkg_name in sorted(packages):
        lines.append(f"### {pkg_name}\n")
        for node in sorted(packages[pkg_name], key=lambda n: n.label):
            kind_badge = f" `{node.kind}`" if node.kind != "class" else ""
            fields_count = len(node.fields)
            methods_count = len(node.methods)
            doc = node.metadata.get("docstring", "")
            doc_part = f" — {doc}" if doc else ""

            lines.append(
                f"- **{node.label}**{kind_badge}"
                f" ({fields_count} fields, {methods_count} methods)"
                f"{doc_part}"
            )
        lines.append("")

    return "\n".join(lines)


def _generate_relationship_summary(graph: ClassGraph) -> str:
    """Generate a relationship summary table.

    Args:
        graph: ClassGraph with edges.

    Returns:
        Markdown table of all relationships.
    """
    lines: list[str] = []

    lines.append("| Source | → | Target | Type | Label |")
    lines.append("|--------|---|--------|------|-------|")

    for edge in sorted(graph.edges, key=lambda e: (e.source, e.target)):
        arrow = _arrow_for_table(edge.relation)
        label = edge.label or ""
        card = f" [{edge.cardinality}]" if edge.cardinality else ""
        lines.append(
            f"| {_short_name(edge.source)} | {arrow} | "
            f"{_short_name(edge.target)} | {edge.relation.value} | "
            f"{label}{card} |"
        )

    return "\n".join(lines)


def _class_to_dict(cls: ClassInfo) -> dict:
    """Convert a ClassInfo to a JSON-serializable dict.

    Uses dataclasses.asdict for the base conversion,
    then converts nested dataclass fields.
    """
    d = asdict(cls)
    return d


def _short_name(qualified: str) -> str:
    """Extract the short class name from a qualified name.

    ``core.services.vault.VaultOps`` → ``VaultOps``
    """
    return qualified.rsplit(".", 1)[-1] if "." in qualified else qualified


def _arrow_for_table(relation: RelationType) -> str:
    """Simple arrow symbol for Markdown tables."""
    arrows = {
        RelationType.INHERITS: "extends",
        RelationType.IMPLEMENTS: "implements",
        RelationType.COMPOSES: "has-a",
        RelationType.AGGREGATES: "has-many",
        RelationType.DEPENDS: "uses",
        RelationType.ASSOCIATES: "knows",
    }
    return arrows.get(relation, "→")
