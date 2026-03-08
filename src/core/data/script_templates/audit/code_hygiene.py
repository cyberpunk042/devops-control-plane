#!/usr/bin/env python3
"""
@script
name: Code Hygiene Audit
category: audit
mode: fully_automated
tags: hygiene, init, docs, stale, quality, python
default_output: docs/audits/
output_formats: markdown, json
requires_tools: (none)
timeout: 120
description: Audits code hygiene across the project. Two sub-audits:
    (A) Module-index leak detection — finds functions and classes
    defined in __init__.py files instead of proper sub-modules.
    (B) Stale documentation detection — finds references to files,
    functions, or classes that no longer exist.
    Observes and reports facts — does not judge.

@param scope: string = none | Scope — limit init analysis to a directory (e.g., "core/services")
@param style: choice = smart [raw, smart] | Output style — raw (flat tables) or smart (layered multi-view)
@param output: path = docs/audits/ | Output directory for the report
@param format: choice = markdown [markdown, json] | Output format
@param filename: string = none | Output filename (default: code_hygiene.md)
@param source-dir: string = src | Source directory to analyze (relative to project root)
@param doc-dirs: string = docs | Documentation directories to scan, comma-separated
@param sub-audit: choice = all [all, init, docs] | Which sub-audit to run
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    """Main entry point for the code hygiene audit.

    Returns exit code: 0 = success, 1 = error.
    """
    args = parse_args()

    project_root = Path(os.environ.get("SCRIPT_PROJECT_ROOT", ".")).resolve()
    output_dir = Path(
        args.output
        or os.environ.get("SCRIPT_OUTPUT_DIR", "docs/audits")
    )
    output_format = (
        args.format
        or os.environ.get("SCRIPT_OUTPUT_FORMAT", "markdown")
    )

    sub_audit = args.sub_audit

    init_result = None
    doc_result = None

    # ── Sub-audit A: Init leaks ──────────────────────────────────
    if sub_audit in ("all", "init"):
        print("🔍 Analyzing module-index files...")

        from src.core.data.script_templates.audit.init_analyzer import (
            PythonInitAnalyzer,
        )

        analyzer = PythonInitAnalyzer()
        init_result = analyzer.analyze(
            project_root,
            scope=args.scope,
            source_dir=args.source_dir,
        )

        print(
            f"   Found {init_result.total_files} init files "
            f"({init_result.files_with_logic} with logic, "
            f"{init_result.clean_files} clean)"
        )

    # ── Sub-audit B: Stale docs ──────────────────────────────────
    if sub_audit in ("all", "docs"):
        print("📄 Scanning documentation for stale references...")

        from src.core.data.script_templates.audit.doc_validator import (
            DocValidator,
        )

        doc_dirs = [d.strip() for d in args.doc_dirs.split(",") if d.strip()]
        validator = DocValidator()
        doc_result = validator.analyze(
            project_root,
            doc_dirs=doc_dirs,
        )

        print(
            f"   Scanned {doc_result.total_docs} docs, "
            f"found {doc_result.total_references} references "
            f"({doc_result.total_stale} stale)"
        )

    # ── Render report ────────────────────────────────────────
    style = args.style or "smart"
    print(f"📊 Generating report (style={style})...")

    if output_format == "json":
        content = _render_json(init_result, doc_result)
        ext = ".json"
    elif style == "smart":
        content = _render_smart_markdown(init_result, doc_result)
        ext = ".md"
    else:
        content = _render_markdown(init_result, doc_result)
        ext = ".md"

    # ── Write output ─────────────────────────────────────────────
    from src.core.data.script_templates.lib.report_formatter import write_report

    filename = args.filename or f"code_hygiene{ext}"
    output_path = write_report(content, output_dir / filename)
    print(f"✅ Report written to {output_path}")

    return 0


# ═══════════════════════════════════════════════════════════════════
#  Markdown Report
# ═══════════════════════════════════════════════════════════════════


def _render_markdown(init_result, doc_result) -> str:
    """Render the code hygiene audit as a markdown report."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts: list[str] = []

    # ── Header ──
    parts.append("# Code Hygiene Audit\n")
    parts.append(f"> Generated: {timestamp}\n")

    # ── Table of Contents ──
    parts.append("## Table of Contents\n")
    if init_result is not None:
        parts.append("- [Module-Index Leak Detection](#module-index-leak-detection)")
        parts.append("  - [Summary](#init-summary)")
        parts.append("  - [Files with Logic](#files-with-logic)")
    if doc_result is not None:
        parts.append("- [Documentation Freshness](#documentation-freshness)")
        parts.append("  - [Summary](#doc-summary)")
        parts.append("  - [Stale References](#stale-references)")
    parts.append("")

    # ── Sub-audit A: Init Leaks ──
    if init_result is not None:
        parts.append(_render_init_section(init_result))

    # ── Sub-audit B: Stale Docs ──
    if doc_result is not None:
        parts.append(_render_doc_section(doc_result))

    return "\n".join(parts)


def _render_init_section(result) -> str:
    """Render the init-file analysis section."""
    parts: list[str] = []

    parts.append("## Module-Index Leak Detection\n")
    parts.append(
        "> Observes what functions and classes are defined in `__init__.py` "
        "files instead of proper sub-modules.\n"
    )

    # ── Summary ──
    parts.append("### Init Summary\n")
    parts.append("| Metric | Count |")
    parts.append("|--------|-------|")
    parts.append(f"| Total `__init__.py` files | {result.total_files} |")
    parts.append(f"| Clean (imports/exports only) | {result.clean_files} |")
    parts.append(f"| With functions or classes | {result.files_with_logic} |")
    parts.append(f"| Total leaked functions | {result.total_leaked_functions} |")
    parts.append(f"| Total leaked classes | {result.total_leaked_classes} |")
    parts.append("")

    # ── Files with logic (sorted by function count) ──
    with_logic = [f for f in result.files if not f.is_clean]
    if not with_logic:
        parts.append("All `__init__.py` files are clean — imports and exports only. ✅\n")
        return "\n".join(parts)

    with_logic.sort(key=lambda f: -(f.function_count + f.class_count))

    parts.append("### Files with Logic\n")
    parts.append(
        "| File | Lines | Code Lines | Functions | Classes | Complex Logic |"
    )
    parts.append(
        "|------|-------|-----------|-----------|---------|---------------|"
    )

    for f in with_logic:
        complex_tag = "⚠️" if f.has_complex_logic else "—"
        parts.append(
            f"| `{f.file_path}` | {f.total_lines} | {f.code_lines} | "
            f"{f.function_count} | {f.class_count} | {complex_tag} |"
        )
    parts.append("")

    # ── Detail: functions per file ──
    parts.append("### Function Details\n")
    parts.append(
        "> Functions defined in `__init__.py` that could potentially "
        "live in dedicated sub-modules.\n"
    )

    for f in with_logic:
        if not f.functions:
            continue

        parts.append(f"#### `{f.file_path}` ({f.function_count} functions)\n")
        parts.append("| Function | Lines | Docstring | Trivial |")
        parts.append("|----------|-------|-----------|---------|")

        for fn in sorted(f.functions, key=lambda x: -x.body_lines):
            doc_tag = "✅" if fn.has_docstring else "—"
            trivial_tag = "✅" if fn.is_trivial else "—"
            parts.append(
                f"| `{fn.name}` | {fn.body_lines} | {doc_tag} | {trivial_tag} |"
            )
        parts.append("")

    return "\n".join(parts)


def _render_doc_section(result) -> str:
    """Render the documentation freshness section."""
    parts: list[str] = []

    parts.append("## Documentation Freshness\n")
    parts.append(
        "> Checks backtick-quoted file references and function references "
        "in documentation against the real filesystem.\n"
    )

    # ── Summary ──
    parts.append("### Doc Summary\n")
    parts.append("| Metric | Value |")
    parts.append("|--------|-------|")
    parts.append(f"| Documents scanned | {result.total_docs} |")
    parts.append(f"| Documents with references | {result.docs_with_references} |")
    parts.append(f"| Total references | {result.total_references} |")
    parts.append(f"| Valid references | {result.total_valid} |")
    parts.append(f"| Stale references | {result.total_stale} |")
    freshness_pct = result.overall_freshness * 100
    parts.append(f"| Overall freshness | {freshness_pct:.1f}% |")
    parts.append("")

    # ── Stale references ──
    if result.total_stale == 0:
        parts.append("All documentation references are valid. ✅\n")
        return "\n".join(parts)

    parts.append("### Stale References\n")

    # Group by doc file
    for fa in sorted(result.files, key=lambda f: f.doc_file):
        if not fa.stale_references:
            continue

        freshness = fa.freshness * 100
        parts.append(
            f"#### `{fa.doc_file}` "
            f"({len(fa.stale_references)} stale / "
            f"{fa.total_references} total, "
            f"{freshness:.0f}% fresh)\n"
        )

        parts.append("| Line | Reference | Type | Issue |")
        parts.append("|------|-----------|------|-------|")

        for ref in sorted(fa.stale_references, key=lambda r: r.doc_line):
            parts.append(
                f"| L{ref.doc_line} | {ref.reference_text} | "
                f"{ref.reference_type} | {ref.issue} |"
            )
        parts.append("")

    return "\n".join(parts)


# ═════════════════════════════════════════════════════════════════
#  Smart Report — layered multi-view
# ═════════════════════════════════════════════════════════════════


def _render_smart_markdown(init_result, doc_result) -> str:
    """Render the code hygiene audit as a layered, multi-view markdown report.

    Smart structure (vs raw which is flat tables):
    1. Executive summary — key numbers at a glance
    2. Severity tiers — critical / major / minor grouping
    3. Domain analysis — files grouped by architectural layer
    4. Doc freshness dashboard — visual freshness bars
    5. Cross-reference — init leaks correlated with stale docs
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts: list[str] = []

    # ── Header ──
    parts.append("# Code Hygiene Audit\n")
    parts.append(f"> Generated: {timestamp}  |  Style: **smart**\n")

    # ── Table of Contents ──
    parts.append("## Table of Contents\n")
    parts.append("1. [Executive Summary](#executive-summary)")
    if init_result is not None:
        parts.append("2. [Severity Tiers](#severity-tiers)")
        parts.append("3. [Domain Analysis](#domain-analysis)")
    if doc_result is not None:
        parts.append("4. [Documentation Freshness Dashboard](#documentation-freshness-dashboard)")
    if init_result is not None and doc_result is not None:
        parts.append("5. [Cross-Reference](#cross-reference)")
    parts.append("")

    # ═════════════════════════════════════════════════════════════
    # 1. Executive Summary
    # ═════════════════════════════════════════════════════════════
    parts.append("## Executive Summary\n")
    parts.append("| Metric | Value |")
    parts.append("|--------|-------|")

    if init_result is not None:
        with_logic = [f for f in init_result.files if not f.is_clean]
        clean_pct = (init_result.clean_files * 100 / init_result.total_files) if init_result.total_files else 0
        parts.append(f"| Init files scanned | **{init_result.total_files}** |")
        parts.append(f"| Clean init files | **{init_result.clean_files}** ({clean_pct:.0f}%) |")
        parts.append(f"| Init files with logic | **{init_result.files_with_logic}** |")
        parts.append(f"| Leaked functions | **{init_result.total_leaked_functions}** |")
        parts.append(f"| Leaked classes | **{init_result.total_leaked_classes}** |")

        # Total leaked lines
        total_leaked_lines = sum(f.total_function_lines + f.total_class_lines for f in with_logic)
        parts.append(f"| Total leaked code lines | **{total_leaked_lines}** |")

    if doc_result is not None:
        freshness_pct = doc_result.overall_freshness * 100
        parts.append(f"| Docs scanned | **{doc_result.total_docs}** |")
        parts.append(f"| References found | **{doc_result.total_references}** |")
        parts.append(f"| Stale references | **{doc_result.total_stale}** |")
        parts.append(f"| Doc freshness | **{freshness_pct:.0f}%** |")

    parts.append("")

    if init_result is not None:
        with_logic = [f for f in init_result.files if not f.is_clean]

        # ═════════════════════════════════════════════════════════════
        # 2. Severity Tiers
        # ═════════════════════════════════════════════════════════════
        parts.append("## Severity Tiers\n")
        parts.append(
            "> Init files grouped by how much logic they contain. "
            "This is a **size observation**, not a judgment.\n"
        )

        # Tier thresholds
        critical = [f for f in with_logic if f.total_lines >= 200]
        major = [f for f in with_logic if 50 <= f.total_lines < 200]
        minor = [f for f in with_logic if f.total_lines < 50]

        for tier_name, tier_icon, tier_files, tier_desc in [
            ("Critical", "🔴", critical, "≥ 200 lines of init code"),
            ("Major", "🟡", major, "50–199 lines of init code"),
            ("Minor", "🟢", minor, "< 50 lines of init code"),
        ]:
            parts.append(f"### {tier_icon} {tier_name} ({len(tier_files)} files)\n")
            parts.append(f"> {tier_desc}\n")

            if not tier_files:
                parts.append("None.\n")
                continue

            parts.append("| File | Total Lines | Functions | Classes |")
            parts.append("|------|-----------|-----------|---------|")

            for f in sorted(tier_files, key=lambda x: -x.total_lines):
                parts.append(
                    f"| `{f.file_path}` | {f.total_lines} | "
                    f"{f.function_count} | {f.class_count} |"
                )
            parts.append("")

        # ═════════════════════════════════════════════════════════════
        # 3. Domain Analysis
        # ═════════════════════════════════════════════════════════════
        parts.append("## Domain Analysis\n")
        parts.append(
            "> Init files grouped by architectural layer — "
            "shows where logic leaks concentrate.\n"
        )

        # Infer domain from path
        domains: dict[str, list] = {}
        for f in with_logic:
            path = f.file_path
            if "ui/web/routes" in path:
                domain = "🌐 Web Routes"
            elif "ui/cli" in path:
                domain = "⌨️ CLI Commands"
            elif "core/services" in path:
                domain = "⚙️ Core Services"
            elif "core/data" in path:
                domain = "💾 Core Data"
            else:
                domain = "📦 Other"
            domains.setdefault(domain, []).append(f)

        for domain, files in sorted(domains.items(), key=lambda x: -len(x[1])):
            total_funcs = sum(f.function_count for f in files)
            total_lines = sum(f.total_lines for f in files)
            parts.append(
                f"### {domain} ({len(files)} files, "
                f"{total_funcs} functions, {total_lines} lines)\n"
            )

            parts.append("| File | Lines | Funcs | Top Functions |")
            parts.append("|------|-------|-------|---------------|")

            for f in sorted(files, key=lambda x: -x.function_count):
                top_funcs = ", ".join(
                    fn.name for fn in sorted(
                        f.functions, key=lambda x: -x.body_lines
                    )[:3]
                )
                if len(f.functions) > 3:
                    top_funcs += f" (+{len(f.functions) - 3})"
                parts.append(
                    f"| `{f.file_path}` | {f.total_lines} | "
                    f"{f.function_count} | {top_funcs} |"
                )
            parts.append("")

    if doc_result is not None:
        # ═════════════════════════════════════════════════════════════
        # 4. Documentation Freshness Dashboard
        # ═════════════════════════════════════════════════════════════
        parts.append("## Documentation Freshness Dashboard\n")
        parts.append(
            "> Visual freshness of each document containing code references.\n"
        )

        freshness_pct = doc_result.overall_freshness * 100
        filled = round(freshness_pct / 5)
        bar = "█" * filled + "░" * (20 - filled)
        parts.append(
            f"📚 **Overall**: `{bar}` {freshness_pct:.1f}% "
            f"({doc_result.total_valid}/{doc_result.total_references} valid)\n"
        )

        # Per-doc freshness bars (only docs with refs)
        docs_with_refs = [f for f in doc_result.files if f.total_references > 0]
        if docs_with_refs:
            parts.append("### Per-Document Freshness\n")
            for fa in sorted(docs_with_refs, key=lambda f: f.freshness):
                pct = fa.freshness * 100
                filled = round(pct / 5)
                bar = "█" * filled + "░" * (20 - filled)
                stale_count = len(fa.stale_references)
                icon = "✅" if stale_count == 0 else f"⚠️ {stale_count} stale"
                parts.append(
                    f"`{fa.doc_file}`: `{bar}` {pct:.0f}% — {icon}"
                )
            parts.append("")

        # Stale reference details
        if doc_result.total_stale > 0:
            parts.append("### Stale References\n")
            parts.append("| Document | Line | Reference | Issue |")
            parts.append("|----------|------|-----------|-------|")

            for fa in sorted(doc_result.files, key=lambda f: f.doc_file):
                for ref in fa.stale_references:
                    parts.append(
                        f"| `{ref.doc_file}` | L{ref.doc_line} | "
                        f"{ref.reference_text} | {ref.issue} |"
                    )
            parts.append("")

    # ═════════════════════════════════════════════════════════════
    # 5. Cross-Reference
    # ═════════════════════════════════════════════════════════════
    if init_result is not None and doc_result is not None:
        parts.append("## Cross-Reference\n")
        parts.append(
            "> Areas where init leaks and stale documentation overlap — "
            "potential hotspots for cleanup.\n"
        )

        # Build sets for comparison
        init_paths = {f.file_path for f in init_result.files if not f.is_clean}
        stale_targets = {ref.target_file for f in doc_result.files for ref in f.stale_references}

        # Find overlap: stale refs pointing at directories that have init issues
        overlaps = []
        for init_path in init_paths:
            # Check if any stale ref targets the same directory
            init_dir = "/".join(init_path.split("/")[:-1])
            related_stale = [
                ref for f in doc_result.files
                for ref in f.stale_references
                if ref.target_file.startswith(init_dir)
            ]
            if related_stale:
                overlaps.append((init_path, related_stale))

        if overlaps:
            parts.append("| Init File | Related Stale Docs | Issue |")
            parts.append("|-----------|-------------------|-------|")
            for init_path, refs in overlaps:
                for ref in refs:
                    parts.append(
                        f"| `{init_path}` | `{ref.doc_file}` L{ref.doc_line} | "
                        f"{ref.issue} |"
                    )
        else:
            parts.append(
                "No overlap detected between init-file leaks and stale docs. ✅\n"
            )
        parts.append("")

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════
#  JSON Report
# ═══════════════════════════════════════════════════════════════════


def _render_json(init_result, doc_result) -> str:
    """Render the code hygiene audit as JSON."""
    from dataclasses import asdict

    data = {
        "generated": datetime.now(timezone.utc).isoformat(),
    }

    if init_result is not None:
        data["init_leaks"] = {
            "total_files": init_result.total_files,
            "clean_files": init_result.clean_files,
            "files_with_logic": init_result.files_with_logic,
            "total_leaked_functions": init_result.total_leaked_functions,
            "total_leaked_classes": init_result.total_leaked_classes,
            "files": [
                {
                    "file_path": f.file_path,
                    "total_lines": f.total_lines,
                    "code_lines": f.code_lines,
                    "function_count": f.function_count,
                    "class_count": f.class_count,
                    "has_complex_logic": f.has_complex_logic,
                    "has_all_export": f.has_all_export,
                    "functions": [asdict(fn) for fn in f.functions],
                    "classes": [asdict(c) for c in f.classes],
                }
                for f in init_result.files
                if not f.is_clean
            ],
        }

    if doc_result is not None:
        data["doc_freshness"] = {
            "total_docs": doc_result.total_docs,
            "docs_with_references": doc_result.docs_with_references,
            "total_references": doc_result.total_references,
            "valid_references": doc_result.total_valid,
            "stale_references": doc_result.total_stale,
            "overall_freshness": round(doc_result.overall_freshness, 3),
            "stale_details": [
                {
                    "doc_file": ref.doc_file,
                    "doc_line": ref.doc_line,
                    "reference_type": ref.reference_type,
                    "reference_text": ref.reference_text,
                    "target_file": ref.target_file,
                    "issue": ref.issue,
                }
                for f in doc_result.files
                for ref in f.stale_references
            ],
        }

    return json.dumps(data, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Audit code hygiene — observe and report facts.",
    )
    parser.add_argument(
        "--scope", default=None,
        help="Scope for init analysis (e.g., core/services)",
    )
    parser.add_argument(
        "--style", default=None, choices=["raw", "smart"],
        help="Output style — raw (flat tables) or smart (layered multi-view)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output directory for the report",
    )
    parser.add_argument(
        "--format", default=None, choices=["markdown", "json"],
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--filename", default=None,
        help="Output filename (default: code_hygiene.md)",
    )
    parser.add_argument(
        "--source-dir", default="src",
        help="Source directory to analyze (default: src)",
    )
    parser.add_argument(
        "--doc-dirs", default="docs",
        help="Documentation directories, comma-separated (default: docs)",
    )
    parser.add_argument(
        "--sub-audit", default="all", choices=["all", "init", "docs"],
        help="Which sub-audit to run (default: all)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
