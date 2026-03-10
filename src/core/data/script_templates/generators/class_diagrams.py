#!/usr/bin/env python3
"""
@script
name: Class Diagram Generator
category: generator
mode: fully_automated
tags: mermaid, diagrams, docs, python, class-diagram
default_output: docs/diagrams/
output_formats: mermaid, json, markdown
requires_tools: (none)
timeout: 120
description: Generates Mermaid class diagrams from Python source code.
    Analyzes class definitions, inheritance, composition, and dependencies.
    Produces markdown reports with embedded Mermaid syntax.

@param scope: string = none | Package scope — limit to a specific package (e.g., core.services.vault). Leave empty for full project.
@param output: path = docs/diagrams/ | Output directory for generated diagrams
@param format: choice = mermaid [mermaid, json, markdown] | Output format
@param style: choice = smart [raw, smart] | Output style — raw (monolithic diagram) or smart (layered multi-view document)
@param filename: string = none | Output filename (default: class_diagram.md or class_architecture.md)
@param max-depth: integer = 3 | Maximum package nesting depth for diagram grouping
@param include-private: boolean = false | Include _private classes in diagrams
@param per-module: boolean = false | Generate separate diagrams per top-level module (e.g., core, adapters, ui)

@output REPORT_PATH: string | Path to the last generated report file
@output TOTAL_CLASSES: integer | Total number of classes discovered
@output FILES_ANALYZED: integer | Total number of Python files analyzed
"""

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    """Main entry point for the class diagram generator.

    Returns exit code: 0 = success, 1 = error.
    """
    args = parse_args()

    project_root = Path(os.environ.get("SCRIPT_PROJECT_ROOT", ".")).resolve()
    output_dir = Path(
        args.output
        or os.environ.get("SCRIPT_OUTPUT_DIR", "docs/diagrams")
    )
    output_format = (
        args.format
        or os.environ.get("SCRIPT_OUTPUT_FORMAT", "mermaid")
    )

    # ── Step 1: Analyze ──────────────────────────────────────────
    print(f"📊 Analyzing Python code in {project_root}...")

    from src.core.data.script_templates.lib.code_analyzer import (
        analyze_python_project,
    )

    analysis = analyze_python_project(
        project_root,
        source_dir="src",
        include_private=args.include_private,
    )

    print(f"   Found {analysis.total_classes} classes in {analysis.files_analyzed} files")

    if analysis.total_classes == 0:
        print("⚠️  No classes found. Nothing to diagram.")
        return 0

    # ── Step 2: Build graph(s) ─────────────────────────────────
    from src.core.data.script_templates.lib.graph_builder import (
        build_class_graph,
    )
    from src.core.data.script_templates.lib.report_formatter import write_report

    # Determine which scopes to render
    if args.per_module:
        # Discover top-level modules from analyzed classes
        top_modules = _discover_top_modules(analysis)
        if not top_modules:
            print("⚠️  No modules found. Nothing to diagram.")
            return 0
        print(f"📦 Per-module mode: generating {len(top_modules)} diagrams")
        scopes = top_modules
    else:
        scopes = [args.scope]  # single scope (may be None = full)

    style = args.style or "smart"
    ext = ".json" if output_format == "json" else ".md"
    last_output = None

    # Smart style handles its own module splitting — ignore per-module
    if style == "smart" and args.per_module:
        print("ℹ️  Smart style handles module splitting — ignoring --per-module")
        scopes = [args.scope]

    for scope in scopes:
        print(f"\n🔗 Building graph for {scope or 'Full Project'}...")

        graph = build_class_graph(analysis, scope=scope)
        print(f"   {len(graph.nodes)} nodes, {len(graph.edges)} edges")

        if len(graph.nodes) == 0:
            print(f"   ⚠️  No classes in scope '{scope}' — skipping")
            continue

        # ── Render ─────────────────────────────────────────────
        if output_format == "json":
            content = _render_json(graph, analysis)
        elif output_format == "markdown":
            content = _render_markdown_only(graph, analysis)
        elif style == "smart":
            content = _render_smart_report(graph, analysis, args, scope=scope)
        else:  # mermaid + raw style
            content = _render_mermaid_report(graph, analysis, args, scope=scope)

        # ── Filename: explicit > scope-derived > default ──────
        if args.filename:
            filename = args.filename
            # If per-module, append scope to avoid overwrites
            if args.per_module and scope:
                stem = Path(filename).stem
                filename = f"{stem}_{_scope_slug(scope)}{ext}"
        else:
            filename = _default_filename(scope, ext, style=style)

        # ── Write output ──────────────────────────────────────
        output_path = write_report(content, output_dir / filename)
        print(f"✅ Report written to {output_path}")
        last_output = output_path

    # ── DCP output variables (consumed by plan executor) ─────────
    if last_output:
        print(f"DCP_VAR_REPORT_PATH={last_output}")
    print(f"DCP_VAR_TOTAL_CLASSES={analysis.total_classes}")
    print(f"DCP_VAR_FILES_ANALYZED={analysis.files_analyzed}")

    return 0


def _default_filename(scope: str | None, ext: str, style: str = "raw") -> str:
    """Compute a default output filename from the scope.

    - style='raw':  class_diagram.md / class_diagram_core.md
    - style='smart': class_architecture.md / class_architecture_core.md
    """
    prefix = "class_architecture" if style == "smart" else "class_diagram"
    if not scope:
        return f"{prefix}{ext}"
    slug = _scope_slug(scope)
    return f"{prefix}_{slug}{ext}"


def _scope_slug(scope: str) -> str:
    """Turn a dotted scope into an underscore slug for filenames."""
    # Strip leading 'src.' if present (UI never shows it)
    s = scope
    if s.startswith("src."):
        s = s[4:]
    return s.replace(".", "_")


def _discover_top_modules(analysis) -> list[str]:
    """Extract unique top-level modules from analyzed classes.

    e.g., from modules like src.core.services.vault, src.adapters.base
    returns ['core', 'adapters', 'ui']
    """
    seen = set()
    for cls in analysis.classes:
        parts = cls.module.split(".")
        # Skip the 'src' prefix if present
        if parts and parts[0] == "src" and len(parts) > 1:
            seen.add(parts[1])
        elif parts:
            seen.add(parts[0])
    return sorted(seen)


def _render_mermaid_report(graph, analysis, args, scope=None) -> str:
    """Render the full Mermaid report with diagrams."""
    from src.core.data.script_templates.lib.mermaid_generator import (
        MermaidConfig,
        render_class_diagram,
    )
    from src.core.data.script_templates.lib.report_formatter import (
        format_markdown_report,
    )

    config = MermaidConfig(
        max_fields=10,
        max_methods=15,
        group_by_package=True,
        show_visibility=True,
    )

    mermaid_content = render_class_diagram(graph, config=config)

    scope_label = scope or args.scope or "Full Project"

    return format_markdown_report(
        graph,
        mermaid_content,
        title=f"Class Diagram — {scope_label}",
        include_toc=True,
        include_stats=True,
        analysis=analysis,
    )


def _render_smart_report(graph, analysis, args, scope=None) -> str:
    """Render the smart multi-view layered report."""
    from src.core.data.script_templates.lib.report_formatter import (
        format_smart_report,
    )

    scope_label = scope or args.scope or "Full Project"

    return format_smart_report(
        analysis,
        graph,
        title=f"Class Architecture — {scope_label}",
        max_depth=args.max_depth,
    )


def _render_json(graph, analysis) -> str:
    """Render graph data as JSON."""
    from src.core.data.script_templates.lib.report_formatter import (
        format_json_report,
    )

    return format_json_report(analysis, graph)


def _render_markdown_only(graph, analysis) -> str:
    """Render as markdown tables (no Mermaid diagrams)."""
    from src.core.data.script_templates.lib.report_formatter import (
        format_markdown_report,
    )

    # Pass empty mermaid → no diagram block, just stats + index
    return format_markdown_report(
        graph,
        "",
        title="Class Diagram — Tabular",
        include_toc=True,
        include_stats=True,
        analysis=analysis,
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Parameters match the @param declarations in the script header.
    """
    parser = argparse.ArgumentParser(
        description="Generate Mermaid class diagrams from Python source code.",
    )
    parser.add_argument(
        "--scope", default=None,
        help="Package scope (e.g., core.services.vault)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output directory for generated diagrams",
    )
    parser.add_argument(
        "--format", default=None, choices=["mermaid", "json", "markdown"],
        help="Output format (default: mermaid)",
    )
    parser.add_argument(
        "--filename", default=None,
        help="Output filename (default: class_diagram_{scope}.md)",
    )
    parser.add_argument(
        "--max-depth", type=int, default=3,
        help="Maximum package nesting depth (default: 3)",
    )
    parser.add_argument(
        "--include-private", action="store_true",
        help="Include _private classes in diagrams",
    )
    parser.add_argument(
        "--per-module", action="store_true",
        help="Generate separate diagrams per top-level module",
    )
    parser.add_argument(
        "--style", default="smart", choices=["raw", "smart"],
        help="Output style: raw (monolithic diagram) or smart (layered multi-view)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
