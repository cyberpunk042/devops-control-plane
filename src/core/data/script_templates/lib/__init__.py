"""
Shared Library for Python Code Analysis
========================================

Pipeline: **discover → parse → graph → render → report**

This library provides a complete pipeline for analyzing Python projects
and generating class diagrams, relationship graphs, and reports.

Usage::

    from src.core.data.script_templates.lib import (
        # Step 1: Discover files
        discover_files,
        discover_python_files,
        group_by_package,

        # Step 2: Analyze code
        analyze_file,
        analyze_python_project,

        # Step 3: Build relationship graph
        build_class_graph,

        # Step 4: Render Mermaid diagrams
        render_class_diagram,
        render_flowchart,
        render_component_diagram,

        # Step 5: Format reports
        format_markdown_report,
        format_json_report,
        write_report,
    )

    # Full pipeline example
    analysis = analyze_python_project(Path("."), source_dir="src")
    graph = build_class_graph(analysis)
    mermaid = render_class_diagram(graph)
    report = format_markdown_report(graph, mermaid, analysis=analysis)
    write_report(report, Path("docs/class-diagram.md"))
"""

# ── Step 1: File discovery ────────────────────────────────────────
from .file_discovery import (
    DEFAULT_EXCLUDES,
    discover_files,
    discover_python_files,
    file_relative_module,
    group_by_package,
)

# ── Step 2: Code analysis ────────────────────────────────────────
from .code_analyzer import (
    ClassInfo,
    FieldInfo,
    MethodInfo,
    ProjectAnalysis,
    analyze_file,
    analyze_python_project,
)

# ── Step 3: Graph building ────────────────────────────────────────
from .graph_builder import (
    ClassGraph,
    GraphEdge,
    GraphNode,
    RelationType,
    build_class_graph,
)

# ── Step 4: Mermaid rendering ─────────────────────────────────────
from .mermaid_generator import (
    MermaidConfig,
    render_class_diagram,
    render_component_diagram,
    render_flowchart,
)

# ── Step 5: Report formatting ─────────────────────────────────────
from .report_formatter import (
    format_json_report,
    format_markdown_report,
    write_report,
)


__all__ = [
    # File discovery
    "DEFAULT_EXCLUDES",
    "discover_files",
    "discover_python_files",
    "file_relative_module",
    "group_by_package",
    # Code analysis
    "ClassInfo",
    "FieldInfo",
    "MethodInfo",
    "ProjectAnalysis",
    "analyze_file",
    "analyze_python_project",
    # Graph building
    "ClassGraph",
    "GraphEdge",
    "GraphNode",
    "RelationType",
    "build_class_graph",
    # Mermaid rendering
    "MermaidConfig",
    "render_class_diagram",
    "render_component_diagram",
    "render_flowchart",
    # Report formatting
    "format_json_report",
    "format_markdown_report",
    "write_report",
]
