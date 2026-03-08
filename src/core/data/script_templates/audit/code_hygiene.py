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

    Smart structure:
    1. Executive summary — health verdict + key numbers
    2. Severity tiers — files by size, with function classification
    3. Domain analysis — architectural layer grouping + boilerplate detection
    4. Leaked function inventory — every function in non-clean inits
    5. Refactoring impact — ROI of cleanup
    6. Doc freshness dashboard — trust tiers, no self-referential noise
    7. Stale reference groups — grouped by root cause
    8. Cross-reference — init leaks correlated with stale docs
    9. Fix checklist — ordered action items
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts: list[str] = []

    # ── Header ──
    parts.append("# Code Hygiene Audit\n")
    parts.append(f"> Generated: {timestamp}  |  Style: **smart**\n")

    # ── Table of Contents ──
    parts.append("## Table of Contents\n")
    toc_items = ["1. [Executive Summary](#executive-summary)"]
    if init_result is not None:
        toc_items.append("2. [Severity Tiers](#severity-tiers)")
        toc_items.append("3. [Domain Analysis](#domain-analysis)")
        toc_items.append("4. [Leaked Function Inventory](#leaked-function-inventory)")
        toc_items.append("5. [Refactoring Impact](#refactoring-impact)")
    if doc_result is not None:
        toc_items.append("6. [Documentation Freshness Dashboard](#documentation-freshness-dashboard)")
        toc_items.append("7. [Stale Reference Groups](#stale-reference-groups)")
    if init_result is not None and doc_result is not None:
        toc_items.append("8. [Cross-Reference](#cross-reference)")
    toc_items.append("9. [Fix Checklist](#fix-checklist)")
    parts.extend(toc_items)
    parts.append("")

    # Precompute shared values
    with_logic = []
    total_debt_lines = 0
    total_route = 0
    total_cli = 0
    total_reg = 0
    total_other = 0

    if init_result is not None:
        with_logic = [f for f in init_result.files if not f.is_clean]
        total_debt_lines = sum(
            f.total_function_lines + f.total_class_lines for f in with_logic
        )
        total_route = sum(f.route_handler_count for f in with_logic)
        total_cli = sum(f.cli_command_count for f in with_logic)
        total_reg = sum(f.registration_count for f in with_logic)
        total_other = sum(f.other_function_count for f in with_logic)

    # ═════════════════════════════════════════════════════════════
    # 1. Executive Summary
    # ═════════════════════════════════════════════════════════════
    parts.append("## Executive Summary\n")

    # Health verdict paragraph
    verdict_parts = []
    if init_result is not None:
        clean_pct = (
            (init_result.clean_files * 100 / init_result.total_files)
            if init_result.total_files else 100
        )
        worst = max(with_logic, key=lambda x: x.total_lines) if with_logic else None
        worst_pct = (
            (worst.total_lines * 100 / total_debt_lines)
            if worst and total_debt_lines else 0
        )

        if clean_pct >= 90:
            hygiene = "**good**"
        elif clean_pct >= 70:
            hygiene = "**fair**"
        else:
            hygiene = "**poor**"

        verdict_parts.append(
            f"Your init hygiene is {hygiene} — "
            f"{init_result.files_with_logic}/{init_result.total_files} "
            f"init files contain logic ({total_debt_lines:,} lines)."
        )
        if worst:
            verdict_parts.append(
                f"The worst offender is `{worst.file_path}` with "
                f"{worst.total_lines} lines ({worst_pct:.0f}% of all init debt)."
            )

    if doc_result is not None:
        freshness_pct = doc_result.overall_freshness * 100
        if freshness_pct >= 90:
            doc_health = "**excellent**"
        elif freshness_pct >= 70:
            doc_health = "**fair**"
        else:
            doc_health = "**poor**"
        verdict_parts.append(
            f"Documentation freshness is {doc_health} at {freshness_pct:.0f}% "
            f"— {doc_result.total_stale} stale references across "
            f"{doc_result.docs_with_references} docs with code references."
        )

    if verdict_parts:
        parts.append("> " + " ".join(verdict_parts) + "\n")

    # Metrics table
    parts.append("| Metric | Value |")
    parts.append("|--------|-------|")

    if init_result is not None:
        clean_pct = (
            (init_result.clean_files * 100 / init_result.total_files)
            if init_result.total_files else 0
        )
        parts.append(f"| Init files scanned | **{init_result.total_files}** |")
        parts.append(
            f"| Clean init files | **{init_result.clean_files}** ({clean_pct:.0f}%) |"
        )
        parts.append(
            f"| Init files with logic | **{init_result.files_with_logic}** |"
        )
        parts.append(f"| Total leaked code lines | **{total_debt_lines:,}** |")
        parts.append(f"| 🔧 Route handlers in init | **{total_route}** |")
        parts.append(f"| ⌨️ CLI commands in init | **{total_cli}** |")
        parts.append(f"| 📋 Registration helpers | **{total_reg}** |")
        parts.append(f"| 🔩 Other functions | **{total_other}** |")
        parts.append(
            f"| Leaked classes | **{init_result.total_leaked_classes}** |"
        )

    if doc_result is not None:
        freshness_pct = doc_result.overall_freshness * 100
        parts.append(f"| Docs scanned | **{doc_result.total_docs}** |")
        parts.append(f"| References found | **{doc_result.total_references}** |")
        parts.append(f"| Stale references | **{doc_result.total_stale}** |")
        parts.append(f"| Doc freshness | **{freshness_pct:.0f}%** |")

    parts.append("")

    if init_result is not None:
        # ═════════════════════════════════════════════════════════════
        # 2. Severity Tiers
        # ═════════════════════════════════════════════════════════════
        parts.append("## Severity Tiers\n")
        parts.append(
            "> Init files grouped by how much logic they contain, "
            "with function type breakdown.\n"
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
            parts.append(
                f"### {tier_icon} {tier_name} ({len(tier_files)} files)\n"
            )
            parts.append(f"> {tier_desc}\n")

            if not tier_files:
                parts.append("None.\n")
                continue

            parts.append(
                "| File | Lines | Routes | CLI | Reg | Other | Migration |"
            )
            parts.append(
                "|------|-------|--------|-----|-----|-------|-----------|"
            )

            for f in sorted(tier_files, key=lambda x: -x.total_lines):
                migration = _infer_migration(f)
                parts.append(
                    f"| `{f.file_path}` | {f.total_lines} | "
                    f"{f.route_handler_count} | {f.cli_command_count} | "
                    f"{f.registration_count} | {f.other_function_count} | "
                    f"{migration} |"
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

            # Detect boilerplate pattern
            boilerplate = _detect_boilerplate(files)
            if boilerplate["count"] >= 3:
                parts.append(
                    f"> ℹ️ **Pattern**: {boilerplate['count']}/{len(files)} "
                    f"files follow the `{boilerplate['pattern']}` boilerplate "
                    f"({boilerplate['avg_lines']} lines avg). "
                    f"This is structural, not accidental.\n"
                )

            parts.append("| File | Lines | Type | Top Functions |")
            parts.append("|------|-------|------|---------------|")

            for f in sorted(files, key=lambda x: -x.function_count):
                ftype = _dominant_type(f)
                top_funcs = ", ".join(
                    fn.name for fn in sorted(
                        f.functions, key=lambda x: -x.body_lines
                    )[:3]
                )
                if len(f.functions) > 3:
                    top_funcs += f" (+{len(f.functions) - 3})"
                parts.append(
                    f"| `{f.file_path}` | {f.total_lines} | "
                    f"{ftype} | {top_funcs} |"
                )
            parts.append("")

        # ═════════════════════════════════════════════════════════════
        # 4. Leaked Function Inventory
        # ═════════════════════════════════════════════════════════════
        parts.append("## Leaked Function Inventory\n")
        parts.append(
            "> Every function and class defined in non-clean init files. "
            "Grouped by file, sorted by body size. "
            "Only files with ≥ 50 lines shown (smaller files are in severity tiers).\n"
        )

        inventory_files = [
            f for f in sorted(with_logic, key=lambda x: -x.total_lines)
            if f.total_lines >= 50
        ]

        for f in inventory_files:
            cls_note = (
                f", {f.class_count} class{'es' if f.class_count > 1 else ''}"
                if f.class_count else ""
            )
            parts.append(
                f"### `{f.file_path}` "
                f"({f.total_lines} lines, {f.function_count} "
                f"function{'s' if f.function_count != 1 else ''}{cls_note})\n"
            )

            if f.functions:
                parts.append("| Function | Lines | Type | Decorators |")
                parts.append("|----------|-------|------|------------|")
                for fn in sorted(f.functions, key=lambda x: -x.body_lines):
                    fn_type = _classify_function(fn)
                    decos = ", ".join(fn.decorators) if fn.decorators else "—"
                    parts.append(
                        f"| `{fn.name}` | {fn.body_lines} | {fn_type} | {decos} |"
                    )

            if f.classes:
                parts.append("")
                for cls in f.classes:
                    parts.append(
                        f"| class `{cls.name}` | {cls.body_lines} | "
                        f"class ({cls.method_count} methods) | — |"
                    )

            parts.append("")

        # ═════════════════════════════════════════════════════════════
        # 5. Refactoring Impact
        # ═════════════════════════════════════════════════════════════
        parts.append("## Refactoring Impact\n")
        parts.append(
            "> If you fix these files, here's the impact on your init debt.\n"
        )

        if total_debt_lines > 0:
            parts.append(
                "| Priority | File | Lines | % of Debt | Cumulative |"
            )
            parts.append(
                "|----------|------|-------|-----------|------------|"
            )

            cumulative = 0.0
            sorted_debt = sorted(
                with_logic, key=lambda x: -x.total_lines
            )

            for i, f in enumerate(sorted_debt[:10], 1):
                pct = f.total_lines * 100 / total_debt_lines
                cumulative += pct
                parts.append(
                    f"| {i} | `{f.file_path}` | {f.total_lines} | "
                    f"{pct:.1f}% | {cumulative:.1f}% |"
                )

            parts.append("")

            # Key insight
            top3_pct = sum(
                f.total_lines for f in sorted_debt[:3]
            ) * 100 / total_debt_lines
            top5_pct = sum(
                f.total_lines for f in sorted_debt[:5]
            ) * 100 / total_debt_lines
            parts.append(
                f"> 📊 **Fixing the top 3 files eliminates "
                f"{top3_pct:.0f}% of all init debt.** "
                f"Top 5 eliminates {top5_pct:.0f}%.\n"
            )
        else:
            parts.append("No init debt detected. ✅\n")

    if doc_result is not None:
        # ═════════════════════════════════════════════════════════════
        # 6. Documentation Freshness Dashboard
        # ═════════════════════════════════════════════════════════════
        parts.append("## Documentation Freshness Dashboard\n")
        parts.append(
            "> Freshness of documents containing code references.  \n"
            "> **Note**: Audit output files (`docs/audits/`) are excluded "
            "to avoid self-referential noise.\n"
        )

        freshness_pct = doc_result.overall_freshness * 100
        filled = round(freshness_pct / 5)
        bar = "█" * filled + "░" * (20 - filled)
        parts.append(
            f"📚 **Overall**: `{bar}` {freshness_pct:.1f}% "
            f"({doc_result.total_valid}/{doc_result.total_references} valid)\n"
        )

        # Trust tiers
        docs_with_refs = [f for f in doc_result.files if f.total_references > 0]
        trustworthy = [f for f in docs_with_refs if f.freshness >= 1.0]
        mostly_ok = [f for f in docs_with_refs if 0.8 <= f.freshness < 1.0]
        unreliable = [f for f in docs_with_refs if f.freshness < 0.8]

        parts.append("### Trust Tiers\n")
        parts.append("| Tier | Docs | Status |")
        parts.append("|------|------|--------|")
        parts.append(
            f"| ✅ Trustworthy (100%) | {len(trustworthy)} | "
            f"All references valid |"
        )
        parts.append(
            f"| ⚠️ Mostly OK (≥80%) | {len(mostly_ok)} | "
            f"Minor staleness |"
        )
        parts.append(
            f"| 🔴 Unreliable (<80%) | {len(unreliable)} | "
            f"Significant staleness |"
        )
        parts.append("")

        # Per-doc freshness bars (only docs with stale refs)
        docs_with_stale = [f for f in doc_result.files if f.stale_references]
        if docs_with_stale:
            parts.append("### Per-Document Freshness\n")
            for fa in sorted(docs_with_stale, key=lambda f: f.freshness):
                pct = fa.freshness * 100
                filled = round(pct / 5)
                bar = "█" * filled + "░" * (20 - filled)
                stale_count = len(fa.stale_references)
                parts.append(
                    f"`{fa.doc_file}`: `{bar}` {pct:.0f}% "
                    f"— ⚠️ {stale_count} stale"
                )
            parts.append("")

        # ═════════════════════════════════════════════════════════════
        # 7. Stale Reference Groups
        # ═════════════════════════════════════════════════════════════
        if doc_result.total_stale > 0:
            parts.append("## Stale Reference Groups\n")
            parts.append(
                "> Stale references grouped by root cause. "
                "Multiple references to the same missing target are collapsed.\n"
            )

            # Group by target_file
            by_target: dict[str, list] = {}
            for fa in doc_result.files:
                for ref in fa.stale_references:
                    by_target.setdefault(ref.target_file, []).append(ref)

            for target, refs in sorted(
                by_target.items(), key=lambda x: -len(x[1])
            ):
                # Determine if this is a file ref or function ref
                file_refs = [r for r in refs if r.reference_type == "file"]
                func_refs = [r for r in refs if r.reference_type != "file"]

                issue = refs[0].issue or "Unknown issue"
                # Collect unique doc files that reference this target
                doc_files = sorted({r.doc_file for r in refs})

                parts.append(
                    f"### `{target}` ({len(refs)} ref{'s' if len(refs) > 1 else ''}"
                    f" across {len(doc_files)} doc{'s' if len(doc_files) > 1 else ''})\n"
                )
                parts.append(f"> {issue}\n")

                for doc_file in doc_files:
                    doc_refs = [r for r in refs if r.doc_file == doc_file]
                    lines_str = ", ".join(
                        f"L{r.doc_line}" for r in doc_refs
                    )
                    parts.append(f"- `{doc_file}` — {lines_str}")

                parts.append("")

    # ═════════════════════════════════════════════════════════════
    # 8. Cross-Reference
    # ═════════════════════════════════════════════════════════════
    if init_result is not None and doc_result is not None:
        parts.append("## Cross-Reference\n")
        parts.append(
            "> Areas where init leaks and stale documentation overlap — "
            "potential hotspots for cleanup.\n"
        )

        # Build lookup
        overlaps: list[tuple] = []
        for f in with_logic:
            init_dir = "/".join(f.file_path.split("/")[:-1])
            related_targets = set()
            related_refs: list = []
            for fa in doc_result.files:
                for ref in fa.stale_references:
                    if ref.target_file.startswith(init_dir):
                        if ref.target_file not in related_targets:
                            related_targets.add(ref.target_file)
                            related_refs.append(ref)
            if related_refs:
                overlaps.append((f, related_refs))

        if overlaps:
            for f, refs in overlaps:
                parts.append(f"### `{f.file_path}`\n")
                parts.append(
                    f"- **Init issue**: {f.total_lines} lines, "
                    f"{f.function_count} functions "
                    f"({_dominant_type(f)})"
                )
                doc_groups: dict[str, list] = {}
                for ref in refs:
                    doc_groups.setdefault(ref.doc_file, []).append(ref)
                for doc_file, doc_refs in doc_groups.items():
                    parts.append(
                        f"- **Stale doc**: `{doc_file}` — "
                        f"{len(doc_refs)} stale ref{'s' if len(doc_refs) > 1 else ''}"
                    )
                parts.append("")
        else:
            parts.append(
                "No overlap detected between init-file leaks and stale docs. ✅\n"
            )

    # ═════════════════════════════════════════════════════════════
    # 9. Fix Checklist
    # ═════════════════════════════════════════════════════════════
    parts.append("## Fix Checklist\n")
    parts.append(
        "> Ordered by impact. Each item is independent — "
        "fix any one without the others.\n"
    )

    fix_items: list[str] = []

    if init_result is not None and total_debt_lines > 0:
        sorted_debt = sorted(with_logic, key=lambda x: -x.total_lines)
        for i, f in enumerate(sorted_debt[:5], 1):
            pct = f.total_lines * 100 / total_debt_lines
            migration = _infer_migration(f)
            icon = "🔴" if f.total_lines >= 200 else "🟡"
            fix_items.append(
                f"{i}. {icon} **Split `{f.file_path}`** "
                f"({f.total_lines}L, {_dominant_type(f)})  \n"
                f"   {migration}  \n"
                f"   Impact: eliminates {pct:.0f}% of init debt"
            )

    if doc_result is not None:
        # Group stale by doc and add fix items
        docs_with_stale = sorted(
            [fa for fa in doc_result.files if fa.stale_references],
            key=lambda x: -len(x.stale_references),
        )
        for fa in docs_with_stale:
            fix_items.append(
                f"{len(fix_items) + 1}. 🟡 **Update `{fa.doc_file}`** "
                f"({len(fa.stale_references)} stale ref"
                f"{'s' if len(fa.stale_references) > 1 else ''})  \n"
                f"   Update or remove broken code references"
            )

    if fix_items:
        parts.extend(fix_items)
    else:
        parts.append("No fixes needed — code hygiene is clean! ✅")

    parts.append("")
    return "\n".join(parts)


# ═════════════════════════════════════════════════════════════════
#  Smart Report Helpers
# ═════════════════════════════════════════════════════════════════


def _dominant_type(f) -> str:
    """Return a human-readable label for the dominant function type in an init file."""
    if f.route_handler_count >= f.function_count * 0.5 and f.route_handler_count > 0:
        return f"{f.route_handler_count} route handlers"
    if f.cli_command_count >= f.function_count * 0.5 and f.cli_command_count > 0:
        return f"{f.cli_command_count} CLI commands"
    if f.registration_count >= f.function_count * 0.5 and f.registration_count > 0:
        return f"{f.registration_count} registration helpers"
    if f.function_count == 0 and f.class_count > 0:
        return f"{f.class_count} class{'es' if f.class_count > 1 else ''}"
    # Mixed or other
    parts = []
    if f.route_handler_count:
        parts.append(f"{f.route_handler_count} routes")
    if f.cli_command_count:
        parts.append(f"{f.cli_command_count} CLI")
    if f.registration_count:
        parts.append(f"{f.registration_count} reg")
    if f.other_function_count:
        parts.append(f"{f.other_function_count} other")
    return ", ".join(parts) if parts else "logic"


def _classify_function(fn) -> str:
    """Return a type label for a single function."""
    if fn.is_route_handler:
        return "route handler"
    if fn.is_cli_command:
        return "CLI command"
    if fn.is_registration:
        return "registration"
    if fn.is_trivial:
        return "trivial"
    return "utility"


def _infer_migration(f) -> str:
    """Infer migration advice from dominant function type."""
    if f.route_handler_count > f.function_count * 0.4:
        return "→ split to route sub-modules"
    if f.cli_command_count > f.function_count * 0.4:
        return "→ split to command sub-modules"
    if f.registration_count > 0 and f.function_count <= 3:
        return "→ move to registry.py"
    if f.class_count > 0 and f.function_count <= 2:
        return "→ move class to own module"
    return "→ refactor to sub-modules"


def _detect_boilerplate(files: list) -> dict:
    """Detect repeated boilerplate patterns across init files.

    Looks for files where the dominant function is a known boilerplate
    name (e.g., _resolve_project_root) and the file is small.
    """
    boilerplate_names = {"_resolve_project_root", "_resolve_root"}
    matching = []

    for f in files:
        func_names = {fn.name for fn in f.functions}
        if func_names & boilerplate_names and f.total_lines < 60:
            matching.append(f)

    if not matching:
        return {"count": 0, "pattern": "", "avg_lines": 0}

    avg_lines = sum(f.total_lines for f in matching) // len(matching)
    # Find the most common boilerplate function name
    pattern = next(
        iter(boilerplate_names & {
            fn.name for f in matching for fn in f.functions
        }),
        "boilerplate",
    )

    return {
        "count": len(matching),
        "pattern": f"{pattern} + group",
        "avg_lines": avg_lines,
    }


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
