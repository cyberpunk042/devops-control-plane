#!/usr/bin/env python3
"""
@script
name: Data Layer Leak Audit
category: audit
mode: fully_automated
tags: architecture, layers, data, coupling, quality, python
default_output: docs/audits/
output_formats: markdown, json
requires_tools: (none)
timeout: 120
description: Audits architectural layer boundaries for data leaks.
    Four tiers: (1) inline data in function bodies, (2) data definitions
    in wrong layers, (3) import direction violations, (4) lateral service
    coupling.  Also detects duplicated constants across files.
    Observes and reports facts — does not judge.

@param scope: string = none | Limit analysis to a directory (e.g. "core/services")
@param style: choice = smart [raw, smart] | Output style — raw (flat tables) or smart (layered multi-view)
@param output: path = docs/audits/ | Output directory for the report
@param format: choice = markdown [markdown, json] | Output format
@param filename: string = none | Output filename (default: data_layer_leaks.md)
@param source-dir: string = src | Source directory to analyze
@param min-dict-size: string = 5 | Minimum dict/list/set size to flag inline (Tier 1)
@param min-const-size: string = 3 | Minimum module constant size (Tier 2)
@param tier: choice = all [all, 1, 2, 3, 4] | Which tier(s) to analyze

@output REPORT_PATH: string | Path to the generated report file
@output TIER1_REAL: integer | Number of real inline data leaks (Tier 1)
@output TIER2_COUNT: integer | Number of wrong-layer definitions (Tier 2)
@output TIER3_COUNT: integer | Number of import direction violations (Tier 3)
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    """Main entry point for the data layer leak audit.

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

    scope = args.scope if args.scope != "none" else None
    source_dir = args.source_dir
    style = args.style

    min_dict_size = int(args.min_dict_size)
    min_const_size = int(args.min_const_size)
    tier_filter = args.tier

    # ── Run the analyzer ────────────────────────────────────────
    from layer_analyzer import LayerAnalyzer

    print("🔍 Analyzing data layer boundaries...")
    analyzer = LayerAnalyzer(
        min_dict_size=min_dict_size,
        min_const_size=min_const_size,
        source_dir=source_dir,
    )
    result = analyzer.analyze(project_root, scope=scope)
    result.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Filter tiers if requested
    if tier_filter != "all":
        tier_num = int(tier_filter)
        if tier_num != 1:
            result.inline_leaks = []
        if tier_num != 2:
            result.wrong_layer_defs = []
            result.duplications = []
        if tier_num != 3:
            result.import_violations = []
        if tier_num != 4:
            result.lateral_couplings = []

    print(f"   Scanned {result.files_scanned} files across"
          f" {len(result.layer_counts)} layers")
    print(f"   Tier 1 (inline data): {len(result.inline_leaks)}"
          f" ({result.tier1_real} real leaks, {result.tier1_noise} noise)")
    print(f"   Tier 2 (wrong-layer defs): {result.tier2_count}")
    print(f"   Tier 3 (import violations): {result.tier3_count}")
    print(f"   Tier 4 (lateral coupling): {result.tier4_count}")
    print(f"   Duplicated constants: {len(result.duplications)} groups")

    # ── Generate report ─────────────────────────────────────────
    print(f"📊 Generating report (style={style})...")

    if output_format == "json":
        content = _render_json(result)
        filename = args.filename or "data_layer_leaks.json"
    else:
        if style == "smart":
            content = _render_smart_markdown(result)
        else:
            content = _render_raw_markdown(result)
        filename = args.filename or "data_layer_leaks.md"

    # ── Write output ────────────────────────────────────────────
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename
    out_path.write_text(content, encoding="utf-8")
    print(f"✅ Report written to {out_path}")

    # ── DCP output variables (consumed by plan executor) ─────────
    print(f"DCP_VAR_REPORT_PATH={out_path}")
    print(f"DCP_VAR_TIER1_REAL={result.tier1_real}")
    print(f"DCP_VAR_TIER2_COUNT={result.tier2_count}")
    print(f"DCP_VAR_TIER3_COUNT={result.tier3_count}")

    return 0


# ═══════════════════════════════════════════════════════════════════
#  Argument Parsing
# ═══════════════════════════════════════════════════════════════════


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments (mirrors @param declarations)."""
    parser = argparse.ArgumentParser(
        description="Data Layer Leak Audit",
    )
    parser.add_argument(
        "--scope", default=os.environ.get("SCRIPT_PARAM_SCOPE", "none"),
    )
    parser.add_argument(
        "--style", default=os.environ.get("SCRIPT_PARAM_STYLE", "smart"),
        choices=["raw", "smart"],
    )
    parser.add_argument(
        "--output", default=os.environ.get("SCRIPT_PARAM_OUTPUT", ""),
    )
    parser.add_argument(
        "--format", default=os.environ.get("SCRIPT_PARAM_FORMAT", ""),
        choices=["markdown", "json"],
    )
    parser.add_argument("--filename", default=os.environ.get("SCRIPT_PARAM_FILENAME", ""))
    parser.add_argument(
        "--source-dir", dest="source_dir",
        default=os.environ.get("SCRIPT_PARAM_SOURCE_DIR", "src"),
    )
    parser.add_argument(
        "--min-dict-size", dest="min_dict_size",
        default=os.environ.get("SCRIPT_PARAM_MIN_DICT_SIZE", "5"),
    )
    parser.add_argument(
        "--min-const-size", dest="min_const_size",
        default=os.environ.get("SCRIPT_PARAM_MIN_CONST_SIZE", "3"),
    )
    parser.add_argument(
        "--tier", default=os.environ.get("SCRIPT_PARAM_TIER", "all"),
        choices=["all", "1", "2", "3", "4"],
    )
    return parser.parse_args()


# ═══════════════════════════════════════════════════════════════════
#  JSON Renderer
# ═══════════════════════════════════════════════════════════════════


def _render_json(result) -> str:
    """Render audit results as JSON."""
    from dataclasses import asdict
    data = asdict(result)
    data["summary"] = {
        "tier1_total": len(result.inline_leaks),
        "tier1_real": result.tier1_real,
        "tier1_noise": result.tier1_noise,
        "tier2_count": result.tier2_count,
        "tier3_count": result.tier3_count,
        "tier4_count": result.tier4_count,
        "duplication_groups": len(result.duplications),
    }
    return json.dumps(data, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════════
#  Raw Markdown Renderer
# ═══════════════════════════════════════════════════════════════════


def _render_raw_markdown(result) -> str:
    """Render as flat, no-frills markdown tables."""
    timestamp = result.timestamp
    parts: list[str] = []

    parts.append("# Data Layer Leak Audit\n")
    parts.append(f"> Generated: {timestamp}  |  Style: **raw**\n")

    # Tier 1
    parts.append("## Tier 1: Inline Data\n")
    if result.inline_leaks:
        parts.append("| File | Function | Line | Type | Items | Class | Reason |")
        parts.append("|------|----------|------|------|-------|-------|--------|")
        for l in sorted(result.inline_leaks, key=lambda x: (-x.item_count, x.file)):
            parts.append(
                f"| `{l.file}` | {l.function_name}() | {l.lineno} | "
                f"{l.data_type} | {l.item_count} | {l.classification} | "
                f"{l.reason} |"
            )
    else:
        parts.append("No inline data leaks found.\n")

    # Tier 2
    parts.append("\n## Tier 2: Wrong-Layer Definitions\n")
    if result.wrong_layer_defs:
        parts.append("| File | Symbol | Line | Type | Items | Layer | Suggested |")
        parts.append("|------|--------|------|------|-------|-------|-----------|")
        for d in sorted(result.wrong_layer_defs, key=lambda x: (-x.item_count, x.file)):
            parts.append(
                f"| `{d.file}` | {d.symbol_name} | {d.lineno} | "
                f"{d.data_type} | {d.item_count} | {d.current_layer} | "
                f"`{d.suggested_path}` |"
            )
    else:
        parts.append("No wrong-layer definitions found.\n")

    # Tier 3
    parts.append("\n## Tier 3: Import Violations\n")
    if result.import_violations:
        parts.append("| File | Line | Import | Names | From | To | Severity |")
        parts.append("|------|------|--------|-------|------|----|----------|")
        for v in sorted(result.import_violations, key=lambda x: x.file):
            names = ", ".join(v.imported_names[:3])
            parts.append(
                f"| `{v.file}` | {v.lineno} | {v.import_module} | "
                f"{names} | {v.source_layer} | {v.target_layer} | "
                f"{v.severity} |"
            )
    else:
        parts.append("No import violations found.\n")

    # Tier 4
    parts.append("\n## Tier 4: Lateral Coupling\n")
    if result.lateral_couplings:
        parts.append("| File | Line | Source Pkg | Target Pkg | Import | Severity |")
        parts.append("|------|------|-----------|------------|--------|----------|")
        for c in sorted(result.lateral_couplings, key=lambda x: x.file):
            parts.append(
                f"| `{c.file}` | {c.lineno} | {c.source_package} | "
                f"{c.target_package} | {c.import_module} | {c.severity} |"
            )
    else:
        parts.append("No lateral coupling found.\n")

    parts.append("")
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════
#  Smart Markdown Renderer
# ═══════════════════════════════════════════════════════════════════


def _render_smart_markdown(result) -> str:
    """Render the data layer leak audit as a layered, multi-view report.

    Smart structure:
    1. Executive summary — health verdict + key numbers
    2. Architecture map — detected layers
    3. Tier 1 — Inline data leaks (real vs noise, grouped)
    4. Tier 2 — Wrong-layer definitions (with migration suggestions)
    5. Data duplication map — overlapping constants
    6. Tier 3 — Import direction violations
    7. Tier 4 — Lateral service coupling (pair summary + details)
    8. Fix checklist — ordered action items
    """
    timestamp = result.timestamp
    parts: list[str] = []

    # ── Header ──
    parts.append("# Data Layer Leak Audit\n")
    parts.append(f"> Generated: {timestamp}  |  Style: **smart**\n")

    # ── Table of Contents ──
    toc = [
        "1. [Executive Summary](#executive-summary)",
        "2. [Architecture Map](#architecture-map)",
    ]
    section_num = 3
    if result.inline_leaks:
        toc.append(f"{section_num}. [🔴 Inline Data Leaks](#-inline-data-leaks-tier-1)")
        section_num += 1
    if result.wrong_layer_defs:
        toc.append(f"{section_num}. [🟠 Wrong-Layer Definitions](#-wrong-layer-definitions-tier-2)")
        section_num += 1
    if result.duplications:
        toc.append(f"{section_num}. [🔄 Data Duplication Map](#-data-duplication-map)")
        section_num += 1
    if result.import_violations:
        toc.append(f"{section_num}. [🟡 Import Direction Violations](#-import-direction-violations-tier-3)")
        section_num += 1
    if result.lateral_couplings:
        toc.append(f"{section_num}. [🟢 Lateral Service Coupling](#-lateral-service-coupling-tier-4)")
        section_num += 1
    toc.append(f"{section_num}. [Fix Checklist](#fix-checklist)")

    parts.append("## Table of Contents\n")
    parts.extend(toc)
    parts.append("")

    # ── 1. Executive Summary ──
    parts.append("## Executive Summary\n")
    health = _health_verdict(result)
    total_issues = (
        result.tier1_real + result.tier2_count
        + result.tier3_count + len(result.duplications)
    )
    parts.append(
        f"> Your data architecture is **{health}**. "
        f"{total_issues} data boundary issues detected. "
        f"{result.tier1_real} inline data blobs in function bodies, "
        f"{result.tier2_count} module constants in wrong layers, "
        f"{len(result.duplications)} duplication groups, "
        f"{result.tier3_count} import boundary violations. "
        f"{result.tier4_count} lateral service couplings (advisory).\n"
    )

    parts.append("| Tier | Count | Severity |")
    parts.append("|------|-------|----------|")
    parts.append(
        f"| 🔴 Inline data (in functions) | "
        f"{len(result.inline_leaks)} "
        f"({result.tier1_real} real, {result.tier1_noise} structural) "
        f"| Critical |"
    )
    parts.append(
        f"| 🟠 Wrong-layer definitions | {result.tier2_count} | Major |"
    )
    parts.append(
        f"| 🔄 Duplicated constants | {len(result.duplications)} groups | Major |"
    )
    parts.append(
        f"| 🟡 Import violations | {result.tier3_count} | Moderate |"
    )
    parts.append(
        f"| 🟢 Lateral coupling | {result.tier4_count} | Advisory |"
    )
    parts.append("")

    # ── 2. Architecture Map ──
    parts.append("## Architecture Map\n")
    parts.append("> Detected layers from directory structure.\n")
    parts.append("| Layer | Files | Package |")
    parts.append("|-------|-------|---------|")
    for layer, count in sorted(
        result.layer_counts.items(), key=lambda x: -x[1],
    ):
        parts.append(f"| {layer} | {count} | — |")
    parts.append("")

    parts.append("```")
    parts.append("Allowed dependency flow:")
    parts.append("")
    parts.append("  UI (routes, CLI)")
    parts.append("      │")
    parts.append("      ▼")
    parts.append("  Use Cases / Services")
    parts.append("      │")
    parts.append("      ▼")
    parts.append("  Data / Models / Persistence / Config")
    parts.append("")
    parts.append("  ❌  UI → Data/Persistence (skip services)")
    parts.append("  ⚠️  Services/X → Services/Y (lateral)")
    parts.append("```")
    parts.append("")

    # ── 3. Tier 1: Inline Data Leaks ──
    if result.inline_leaks:
        parts.append("## 🔴 Inline Data Leaks (Tier 1)\n")
        parts.append(
            "> Data literals found inside function bodies. "
            "Sorted by item count.\n"
            "> Classification: 🔴 = data leak, ⚪ = response/result "
            "construction, 🔵 = mixed/constructed.\n"
        )

        # Split into real leaks vs noise
        real = [l for l in result.inline_leaks if l.classification == "data_leak"]
        responses = [l for l in result.inline_leaks if l.classification == "response"]
        constructed = [l for l in result.inline_leaks if l.classification == "constructed"]

        if real:
            parts.append("### 🔴 Real Data Leaks\n")
            parts.append(
                "> These should probably be extracted to `core/data/` "
                "or `core/models/`.\n"
            )
            parts.append(
                "| File | Function | Line | Type | Items | Assigned To | Why |"
            )
            parts.append(
                "|------|----------|------|------|-------|-------------|-----|"
            )
            for l in sorted(real, key=lambda x: -x.item_count):
                assigned = f"`{l.assigned_to}`" if l.assigned_to else "—"
                parts.append(
                    f"| `{l.file}` | {l.function_name}() | {l.lineno} | "
                    f"{l.data_type} | {l.item_count} | {assigned} | "
                    f"{l.reason} |"
                )
            parts.append("")

        if responses:
            parts.append("### ⚪ Response / Result Construction (not leaks)\n")
            parts.append(
                "> These are API responses or result dicts — acceptable.\n"
            )
            parts.append(
                "| File | Function | Line | Type | Items | Why it's OK |"
            )
            parts.append(
                "|------|----------|------|------|-------|-------------|"
            )
            for l in sorted(responses, key=lambda x: -x.item_count):
                parts.append(
                    f"| `{l.file}` | {l.function_name}() | {l.lineno} | "
                    f"{l.data_type} | {l.item_count} | {l.reason} |"
                )
            parts.append("")

        if constructed:
            parts.append("### 🔵 Constructed / Mixed (review manually)\n")
            parts.append(
                "> Mix of static and computed values — might be either.\n"
            )
            parts.append(
                "| File | Function | Line | Type | Items | Reason |"
            )
            parts.append(
                "|------|----------|------|------|-------|--------|"
            )
            for l in sorted(constructed, key=lambda x: -x.item_count):
                parts.append(
                    f"| `{l.file}` | {l.function_name}() | {l.lineno} | "
                    f"{l.data_type} | {l.item_count} | {l.reason} |"
                )
            parts.append("")

    # ── 4. Tier 2: Wrong-Layer Definitions ──
    if result.wrong_layer_defs:
        parts.append("## 🟠 Wrong-Layer Definitions (Tier 2)\n")
        parts.append(
            "> Module-level constants and type definitions that live "
            "outside their canonical layer.\n"
        )

        # Group by current layer
        by_layer: dict[str, list] = defaultdict(list)
        for d in result.wrong_layer_defs:
            by_layer[d.current_layer].append(d)

        for layer, defs in sorted(
            by_layer.items(), key=lambda x: -sum(d.item_count for d in x[1]),
        ):
            total_items = sum(d.item_count for d in defs)
            parts.append(
                f"### {layer} ({len(defs)} definitions, "
                f"{total_items} total items)\n"
            )
            parts.append(
                "| File | Symbol | Line | Type | Items | Move to |"
            )
            parts.append(
                "|------|--------|------|------|-------|---------|"
            )
            for d in sorted(defs, key=lambda x: -x.item_count):
                parts.append(
                    f"| `{d.file}` | `{d.symbol_name}` | {d.lineno} | "
                    f"{d.data_type} | {d.item_count} | "
                    f"`{d.suggested_path}` |"
                )
            parts.append("")

    # ── 5. Data Duplication Map ──
    if result.duplications:
        parts.append("## 🔄 Data Duplication Map\n")
        parts.append(
            "> Same or overlapping constants found in multiple files. "
            "These need a single canonical home.\n"
        )

        for i, dup in enumerate(result.duplications, 1):
            entries_desc = [
                f"`{f}:{s}` ({c} items)" for f, s, c in dup.entries
            ]
            parts.append(f"### Group {i}\n")
            parts.append("| File | Symbol | Items |")
            parts.append("|------|--------|-------|")
            for f, s, c in dup.entries:
                parts.append(f"| `{f}` | `{s}` | {c} |")
            parts.append("")

            # Suggest canonical home based on first entry's name
            if dup.entries:
                from layer_analyzer import LayerAnalyzer
                a = LayerAnalyzer()
                suggested = a._suggest_home(
                    dup.entries[0][1], "Set", dup.entries[0][0],
                )
                parts.append(
                    f"> 💡 Suggested canonical home: `{suggested}`\n"
                )

    # ── 6. Tier 3: Import Direction Violations ──
    if result.import_violations:
        parts.append("## 🟡 Import Direction Violations (Tier 3)\n")
        parts.append(
            "> Modules in higher layers importing directly from lower "
            "data layers.\n"
        )

        # Group by pattern (many CLI files import find_project_file)
        by_import: dict[str, list] = defaultdict(list)
        for v in result.import_violations:
            key = f"{v.import_module}→{','.join(v.imported_names)}"
            by_import[key].append(v)

        # Show grouped if many share the same import
        grouped = [
            (key, vs) for key, vs in by_import.items() if len(vs) >= 3
        ]
        individual = [
            v for key, vs in by_import.items() if len(vs) < 3 for v in vs
        ]

        if grouped:
            parts.append("### Boilerplate Patterns (many files, same import)\n")
            parts.append(
                "> These are structural — every CLI module imports the "
                "same config helper.\n"
            )
            for key, vs in sorted(grouped, key=lambda x: -len(x[1])):
                mod = vs[0].import_module
                names = ", ".join(vs[0].imported_names)
                parts.append(
                    f"- **`{mod}`** (`{names}`) — "
                    f"{len(vs)} files import this"
                )
                # List first few files
                for v in vs[:5]:
                    parts.append(f"  - `{v.file}`:L{v.lineno}")
                if len(vs) > 5:
                    parts.append(f"  - … and {len(vs) - 5} more")
            parts.append("")

        if individual:
            parts.append("### Individual Violations\n")
            parts.append(
                "| File | Line | Import | Names | "
                "From Layer | To Layer | Lazy? |"
            )
            parts.append(
                "|------|------|--------|-------|"
                "-----------|----------|-------|"
            )
            for v in sorted(individual, key=lambda x: x.file):
                names = ", ".join(v.imported_names[:3])
                lazy = "✓" if v.is_lazy else ""
                parts.append(
                    f"| `{v.file}` | {v.lineno} | {v.import_module} | "
                    f"{names} | {v.source_layer} | {v.target_layer} | "
                    f"{lazy} |"
                )
            parts.append("")

    # ── 7. Tier 4: Lateral Service Coupling ──
    if result.lateral_couplings:
        parts.append("## 🟢 Lateral Service Coupling (Tier 4)\n")
        parts.append(
            "> Services importing from sibling service sub-packages.\n"
        )

        # Summary by pair
        pairs = Counter()
        for c in result.lateral_couplings:
            pairs[(c.source_package, c.target_package)] += 1

        total_pairs = len(pairs)
        total_imports = len(result.lateral_couplings)
        private_count = sum(
            1 for c in result.lateral_couplings if c.is_private
        )

        parts.append(
            f"**{total_imports}** lateral imports across "
            f"**{total_pairs}** unique pairs "
            f"({private_count} import private symbols).\n"
        )

        parts.append("### Coupling Pairs (sorted by frequency)\n")
        parts.append("| Source | → | Target | Imports | Private? |")
        parts.append("|--------|---|--------|---------|----------|")

        for (src, tgt), count in pairs.most_common():
            has_private = any(
                c.is_private
                for c in result.lateral_couplings
                if c.source_package == src and c.target_package == tgt
            )
            priv_marker = "⚠️" if has_private else ""
            parts.append(
                f"| {src} | → | {tgt} | {count} | {priv_marker} |"
            )
        parts.append("")

        # Top offenders: files with most lateral imports
        file_counts = Counter(c.file for c in result.lateral_couplings)
        parts.append("### Top Files by Lateral Import Count\n")
        parts.append("| File | Lateral Imports | Targets |")
        parts.append("|------|-----------------|---------|")
        for f, count in file_counts.most_common(10):
            targets = sorted(set(
                c.target_package for c in result.lateral_couplings
                if c.file == f
            ))
            parts.append(
                f"| `{f}` | {count} | {', '.join(targets)} |"
            )
        parts.append("")

    # ── 8. Fix Checklist ──
    parts.append("## Fix Checklist\n")
    parts.append(
        "> Ordered by impact. Each item is independent.\n"
    )

    checklist_items: list[tuple[str, str, str]] = []  # (icon, desc, detail)

    # Duplications first (easiest win, proves the problem)
    for dup in result.duplications:
        files = " + ".join(f"`{f}:{s}`" for f, s, c in dup.entries)
        checklist_items.append((
            "🔄",
            f"Deduplicate {files}",
            "Same data in multiple files — create single canonical source",
        ))

    # Top Tier 1 real leaks
    real_leaks = sorted(
        [l for l in result.inline_leaks if l.classification == "data_leak"],
        key=lambda x: -x.item_count,
    )
    for l in real_leaks[:5]:
        checklist_items.append((
            "🔴",
            f"Extract `{l.file}`:L{l.lineno} "
            f"({l.data_type}, {l.item_count} items from {l.function_name}())",
            f"→ move to core/data/",
        ))

    # Top Tier 2 definitions
    top_defs = sorted(result.wrong_layer_defs, key=lambda x: -x.item_count)
    for d in top_defs[:5]:
        checklist_items.append((
            "🟠",
            f"Move `{d.symbol_name}` from `{d.file}` ({d.item_count} items)",
            f"→ `{d.suggested_path}`",
        ))

    # Tier 3 (non-boilerplate only)
    individual_violations = [
        v for v in result.import_violations
        if not _is_boilerplate_import(v, result.import_violations)
    ]
    for v in individual_violations:
        names = ", ".join(v.imported_names[:2])
        checklist_items.append((
            "🟡",
            f"Fix `{v.file}`:L{v.lineno} — imports `{names}` "
            f"from {v.target_layer}",
            "→ go through a service instead",
        ))

    if checklist_items:
        for i, (icon, desc, detail) in enumerate(checklist_items, 1):
            parts.append(f"{i}. {icon} **{desc}**  ")
            parts.append(f"   {detail}")
    else:
        parts.append("✅ No actionable items — architecture is clean!")

    parts.append("")
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════
#  Report Helpers
# ═══════════════════════════════════════════════════════════════════


def _health_verdict(result) -> str:
    """Compute overall health verdict."""
    real_leaks = result.tier1_real
    wrong_defs = result.tier2_count
    import_viols = result.tier3_count
    dupes = len(result.duplications)

    score = real_leaks * 3 + wrong_defs + import_viols * 2 + dupes * 5
    if score == 0:
        return "excellent"
    if score <= 10:
        return "good"
    if score <= 50:
        return "fair"
    if score <= 150:
        return "needs attention"
    return "poor"


def _is_boilerplate_import(violation, all_violations) -> bool:
    """Check if an import violation is a boilerplate pattern.

    If 3+ files import the exact same module+names, it's boilerplate.
    """
    same = [
        v for v in all_violations
        if v.import_module == violation.import_module
        and v.imported_names == violation.imported_names
    ]
    return len(same) >= 3


# ═══════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    sys.exit(main())
