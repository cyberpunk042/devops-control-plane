#!/usr/bin/env python3
"""
@script
name: Route Quality Audit
category: audit
mode: fully_automated
tags: routes, flask, quality, audit, http, api
default_output: docs/audits/
output_formats: markdown, json
requires_tools: (none)
timeout: 60
description: Audits HTTP route quality across the project. Detects framework
    automatically (Flask, FastAPI, Express, Spring). Reports coverage facts
    for auth, docstrings, run tracking, error handling, and method declarations.
    Observes and reports — does not judge.

@param scope: string = none | Blueprint scope — limit to specific blueprint (e.g., "vault", "audit")
@param style: choice = smart [raw, smart] | Output style — raw (flat tables) or smart (layered multi-view)
@param output: path = docs/audits/ | Output directory for the report
@param format: choice = markdown [markdown, json] | Output format
@param filename: string = none | Output filename (default: route_audit.md)
@param routes-path: string = src/ui/web/routes | Path to route directory (relative to project root)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    """Main entry point for the route quality audit.

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

    # ── Step 1: Detect framework ─────────────────────────────────
    print("🔍 Detecting web framework...")

    from src.core.data.script_templates.audit.route_analyzer import (
        FlaskRouteAnalyzer,
        detect_framework,
    )

    framework = detect_framework(project_root)
    print(f"   Framework: {framework}")

    if framework == "unknown":
        print("⚠️  No recognized web framework detected. Nothing to audit.")
        return 0

    # ── Step 2: Analyze routes ───────────────────────────────────
    if framework == "flask":
        analyzer = FlaskRouteAnalyzer()
        result = analyzer.analyze(
            project_root,
            routes_path=args.routes_path,
        )
    else:
        print(f"⚠️  Framework '{framework}' detected but analyzer not yet implemented.")
        print("    Currently supported: Flask")
        print("    Future: FastAPI, Express, Spring Boot")
        return 0

    print(f"   Found {result.total_blueprints} blueprints, {result.total_routes} routes")

    if result.total_routes == 0:
        print("⚠️  No routes found. Nothing to audit.")
        return 0

    # ── Step 3: Apply scope filter ───────────────────────────────
    if args.scope:
        result.blueprints = [
            bp for bp in result.blueprints
            if bp.name == args.scope
        ]
        if not result.blueprints:
            print(f"⚠️  No blueprint named '{args.scope}' found.")
            return 0
        print(f"   Scoped to: {args.scope} ({result.total_routes} routes)")

    # ── Step 4: Render report ────────────────────────────────────
    style = args.style or "smart"
    print(f"📊 Generating report (style={style})...")

    if output_format == "json":
        content = _render_json(result)
        ext = ".json"
    elif style == "smart":
        content = _render_smart_markdown(result)
        ext = ".md"
    else:
        content = _render_markdown(result)
        ext = ".md"

    # ── Step 5: Write output ─────────────────────────────────────
    from src.core.data.script_templates.lib.report_formatter import write_report

    filename = args.filename or f"route_audit{ext}"
    output_path = write_report(content, output_dir / filename)
    print(f"✅ Report written to {output_path}")

    return 0


# ═══════════════════════════════════════════════════════════════════
#  Markdown Report
# ═══════════════════════════════════════════════════════════════════


def _render_markdown(result) -> str:
    """Render the route audit as a markdown report.

    Structure:
    1. Header + metadata
    2. Coverage summary (facts, not grades)
    3. Return type distribution
    4. Init-file observations (routes in __init__)
    5. Per-blueprint detail tables
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts: list[str] = []

    # ── Header ──
    parts.append("# Route Quality Audit\n")
    parts.append(
        f"> Generated: {timestamp}  |  "
        f"Framework: {result.framework}  |  "
        f"{result.total_blueprints} blueprints  |  "
        f"{result.total_routes} routes\n"
    )

    # ── Table of Contents ──
    parts.append("## Table of Contents\n")
    parts.append("- [Coverage Summary](#coverage-summary)")
    parts.append("- [Return Type Distribution](#return-type-distribution)")
    parts.append("- [Init-File Observations](#init-file-observations)")
    parts.append("- [HTTP Methods](#http-methods)")
    parts.append("- [Blueprint Details](#blueprint-details)\n")

    # ── Coverage Summary ──
    parts.append("## Coverage Summary\n")
    parts.append(
        "> These are **observations**, not compliance scores. "
        "Not every route needs auth or run tracking — "
        "that depends on what the route does.\n"
    )
    parts.append("| Attribute | With | Without | Coverage |")
    parts.append("|-----------|------|---------|----------|")

    for attr, label in [
        ("has_docstring", "Docstring"),
        ("has_auth", "Auth decorator"),
        ("has_run_tracking", "Run tracking"),
        ("has_error_handling", "Error handling (try/except)"),
        ("methods_explicit", "Explicit methods="),
    ]:
        with_it, total = result.coverage(attr)
        without = total - with_it
        pct = (with_it * 100 / total) if total else 0
        parts.append(f"| {label} | {with_it} | {without} | {pct:.1f}% |")
    parts.append("")

    # ── Return Type Distribution ──
    parts.append("## Return Type Distribution\n")
    from collections import Counter
    return_types: Counter[str] = Counter()
    for bp in result.blueprints:
        for r in bp.routes:
            return_types[r.return_type] += 1

    parts.append("| Return Type | Count | % |")
    parts.append("|-------------|-------|---|")
    for rt, count in return_types.most_common():
        pct = count * 100 / result.total_routes
        parts.append(f"| {rt} | {count} | {pct:.1f}% |")
    parts.append("")

    # ── Init-File Observations ──
    init_blueprints = [
        bp for bp in result.blueprints if bp.init_has_route_handlers
    ]
    parts.append("## Init-File Observations\n")
    if init_blueprints:
        parts.append(
            f"> {len(init_blueprints)} blueprint(s) have route handlers "
            "defined directly in `__init__.py` instead of sub-modules.\n"
        )
        parts.append("| Blueprint | Init Lines | Routes in Init | Total Routes |")
        parts.append("|-----------|-----------|----------------|--------------|")
        for bp in sorted(init_blueprints, key=lambda b: -b.init_lines):
            init_routes = sum(
                1 for r in bp.routes
                if r.file_path.endswith("__init__.py")
            )
            parts.append(
                f"| {bp.name} | {bp.init_lines} | {init_routes} | {bp.total_routes} |"
            )
    else:
        parts.append(
            "All blueprints use sub-modules for route handlers. "
            "No route handlers detected in `__init__.py` files. ✅\n"
        )
    parts.append("")

    # ── HTTP Methods ──
    parts.append("## HTTP Methods\n")
    method_counts: Counter[str] = Counter()
    for bp in result.blueprints:
        for r in bp.routes:
            for m in r.http_methods:
                method_counts[m] += 1

    parts.append("| Method | Count | % |")
    parts.append("|--------|-------|---|")
    for method, count in method_counts.most_common():
        pct = count * 100 / result.total_routes
        parts.append(f"| {method} | {count} | {pct:.1f}% |")
    parts.append("")

    # ── Blueprint Details ──
    parts.append("## Blueprint Details\n")
    parts.append(
        "> Per-blueprint route listing with observed attributes.\n"
    )

    for bp in sorted(result.blueprints, key=lambda b: -b.total_routes):
        # Count attributes for this blueprint
        bp_auth = sum(1 for r in bp.routes if r.has_auth)
        bp_run = sum(1 for r in bp.routes if r.has_run_tracking)
        bp_docs = sum(1 for r in bp.routes if r.has_docstring)
        bp_err = sum(1 for r in bp.routes if r.has_error_handling)

        init_tag = " 📌" if bp.init_has_route_handlers else ""

        parts.append(
            f"### {bp.name}{init_tag} "
            f"({bp.total_routes} routes)\n"
        )

        # Quick summary line
        summaries = []
        if bp_docs < bp.total_routes:
            summaries.append(f"docs={bp_docs}/{bp.total_routes}")
        if bp_auth > 0:
            summaries.append(f"auth={bp_auth}")
        if bp_run > 0:
            summaries.append(f"tracked={bp_run}")
        if bp_err > 0:
            summaries.append(f"try/except={bp_err}")
        if summaries:
            parts.append(f"> {' · '.join(summaries)}\n")

        # Route table
        parts.append(
            "| Function | Endpoint | Method | "
            "Docs | Auth | Track | Err | Return | Lines |"
        )
        parts.append(
            "|----------|----------|--------|"
            "------|------|-------|-----|--------|-------|"
        )

        for r in sorted(bp.routes, key=lambda x: x.endpoint):
            methods = ",".join(r.http_methods) if r.http_methods else "-"
            docs = "✅" if r.has_docstring else "—"
            auth = "✅" if r.has_auth else "—"
            track = "✅" if r.has_run_tracking else "—"
            err = "✅" if r.has_error_handling else "—"
            parts.append(
                f"| `{r.function_name}` | `{r.endpoint}` | {methods} | "
                f"{docs} | {auth} | {track} | {err} | {r.return_type} | {r.body_lines} |"
            )
        parts.append("")

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════
#  Smart Report — layered multi-view
# ═══════════════════════════════════════════════════════════════════


def _render_smart_markdown(result) -> str:
    """Render the route audit as an architecture-level analysis.

    Smart structure (vs raw which is flat tables):
    1. Executive summary — key metrics at a glance
    2. API surface map — endpoint tree with CRUD analysis
    3. Blueprint architecture — file distribution + naming patterns
    4. Decorator inventory — actual decorator names, categorized
    5. Route contracts — inputs/outputs per route
    6. Complexity tiers — size distribution with outliers
    7. Consistency matrix — cross-blueprint pattern comparison
    8. Anomaly detection — pattern-breaking routes
    """
    from collections import Counter, defaultdict

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts: list[str] = []
    all_routes = [r for bp in result.blueprints for r in bp.routes]

    # ── Header ──
    parts.append("# Route Quality Audit\n")
    parts.append(
        f"> Generated: {timestamp}  |  "
        f"Framework: {result.framework}  |  "
        f"Style: **smart**\n"
    )

    # ── Table of Contents ──
    parts.append("## Table of Contents\n")
    parts.append("1. [Executive Summary](#executive-summary)")
    parts.append("2. [API Surface Map](#api-surface-map)")
    parts.append("3. [Blueprint Architecture](#blueprint-architecture)")
    parts.append("4. [Decorator Inventory](#decorator-inventory)")
    parts.append("5. [Route Contracts](#route-contracts)")
    parts.append("6. [Complexity Analysis](#complexity-analysis)")
    parts.append("7. [Consistency Matrix](#consistency-matrix)")
    parts.append("8. [Anomaly Detection](#anomaly-detection)\n")

    # ═════════════════════════════════════════════════════════════════
    # 1. Executive Summary
    # ═════════════════════════════════════════════════════════════════
    parts.append("## Executive Summary\n")
    parts.append(
        f"| Metric | Value |\n|--------|-------|\n"
        f"| Blueprints | **{result.total_blueprints}** |\n"
        f"| Routes | **{result.total_routes}** |"
    )

    # Coverage bars
    for attr, label, icon in [
        ("has_docstring", "Docstrings", "📝"),
        ("has_run_tracking", "Run tracking", "📊"),
        ("has_error_handling", "Error handling", "🛡️"),
        ("methods_explicit", "Explicit methods", "📋"),
    ]:
        with_it, total = result.coverage(attr)
        pct = (with_it * 100 / total) if total else 0
        parts.append(f"| {icon} {label} | **{pct:.0f}%** ({with_it}/{total}) |")

    # Unique decorators count
    all_decos = set()
    for r in all_routes:
        all_decos.update(d for d in r.decorators if d != "route")
    parts.append(f"| 🎭 Unique decorators | **{len(all_decos)}** |")

    # Average complexity
    avg_lines = sum(r.body_lines for r in all_routes) / len(all_routes) if all_routes else 0
    avg_branches = sum(r.branch_count for r in all_routes) / len(all_routes) if all_routes else 0
    parts.append(f"| 📏 Avg body size | **{avg_lines:.0f} lines** |")
    parts.append(f"| 🔀 Avg branches | **{avg_branches:.1f}** |")

    # Init-file count
    init_bps = [bp for bp in result.blueprints if bp.init_has_route_handlers]
    parts.append(
        f"| 📌 Init-file routes | **{len(init_bps)}** / {result.total_blueprints} blueprints |"
    )
    parts.append("")

    # ═════════════════════════════════════════════════════════════════
    # 2. API Surface Map — endpoint tree with CRUD analysis
    # ═════════════════════════════════════════════════════════════════
    parts.append("## API Surface Map\n")
    parts.append(
        "> Endpoint tree organized by blueprint. Each route shows its "
        "HTTP method, decorators, and detected parameters.\n"
    )

    for bp in sorted(result.blueprints, key=lambda b: -b.total_routes):
        # Group routes by endpoint prefix
        routes_sorted = sorted(bp.routes, key=lambda r: r.endpoint)
        parts.append(f"### 📦 {bp.name} ({bp.total_routes} routes)\n")
        parts.append("```")

        for r in routes_sorted:
            methods = ",".join(r.http_methods)
            # Build annotation string from actual decorators
            annotations = [d for d in r.decorators if d != "route"]
            ann_str = f"  [{', '.join(annotations)}]" if annotations else ""

            # Show URL params inline
            url_p = ""
            if r.url_params:
                url_p = " " + " ".join(f"<{p}>" for p in r.url_params)

            # Show request params
            req_parts = []
            for p in r.request_params:
                req_flag = "!" if p["required"] else "?"
                req_parts.append(f"{p['source']}:{p['name']}{req_flag}")
            req_str = f"  ← {', '.join(req_parts)}" if req_parts else ""

            # Show response codes
            code_str = ""
            if r.response_codes:
                code_str = f"  → {','.join(str(c) for c in r.response_codes)}"

            parts.append(
                f"  {methods:7s} {r.endpoint}{url_p}{ann_str}{req_str}{code_str}"
            )

        parts.append("```")

        # CRUD analysis for this blueprint
        bp_methods = set()
        for r in bp.routes:
            bp_methods.update(r.http_methods)
        crud = []
        if "POST" in bp_methods:
            crud.append("C")
        if "GET" in bp_methods:
            crud.append("R")
        if "PUT" in bp_methods or "PATCH" in bp_methods:
            crud.append("U")
        if "DELETE" in bp_methods:
            crud.append("D")
        crud_str = "".join(crud)
        missing = []
        for letter, name in [("C", "Create/POST"), ("R", "Read/GET"), ("U", "Update/PUT"), ("D", "Delete/DELETE")]:
            if letter not in crud_str:
                missing.append(name)
        crud_note = f" — missing: {', '.join(missing)}" if missing else " — complete"
        parts.append(f"\n> CRUD: **{crud_str}**{crud_note}\n")

    # ═════════════════════════════════════════════════════════════════
    # 3. Blueprint Architecture — file distribution
    # ═════════════════════════════════════════════════════════════════
    parts.append("## Blueprint Architecture\n")
    parts.append(
        "> File distribution and structure per blueprint.\n"
    )

    for bp in sorted(result.blueprints, key=lambda b: -b.total_routes):
        parts.append(f"### 📁 {bp.name}/\n")
        parts.append("```")

        # Group routes by file
        by_file: dict[str, list] = defaultdict(list)
        for r in bp.routes:
            # Get filename from path
            fname = r.file_path.split("/")[-1] if "/" in r.file_path else r.file_path
            by_file[fname].append(r)

        for fname in sorted(by_file.keys()):
            file_routes = by_file[fname]
            total_lines = sum(r.body_lines for r in file_routes)
            init_marker = " (📌 init)" if fname == "__init__.py" and bp.init_has_route_handlers else ""
            parts.append(
                f"  {fname:30s} {len(file_routes):3d} routes  {total_lines:5d} lines{init_marker}"
            )

        parts.append("```")

        # Naming convention check
        func_names = [r.function_name for r in bp.routes]
        prefix_match = sum(1 for fn in func_names if fn.startswith(bp.name) or fn.startswith(bp.name.rstrip("s")))
        if prefix_match > 0:
            pct = prefix_match * 100 // len(func_names)
            parts.append(f"\n> Naming: {prefix_match}/{len(func_names)} functions ({pct}%) follow `{bp.name}_*` convention\n")
        else:
            parts.append("")

    # ═════════════════════════════════════════════════════════════════
    # 4. Decorator Inventory
    # ═════════════════════════════════════════════════════════════════
    parts.append("## Decorator Inventory\n")
    parts.append(
        "> All decorators used across the project, categorized by type.\n"
    )

    # Collect all decorator combos
    deco_usage: Counter[str] = Counter()
    deco_blueprints: dict[str, set] = defaultdict(set)
    for r in all_routes:
        for d in r.decorators:
            if d != "route":
                deco_usage[d] += 1
                deco_blueprints[d].add(r.blueprint)

    if deco_usage:
        parts.append("| Decorator | Routes | Blueprints | Used In |")
        parts.append("|-----------|--------|------------|---------|")
        for deco, count in deco_usage.most_common():
            bps = sorted(deco_blueprints[deco])
            bp_str = ", ".join(bps[:5])
            if len(bps) > 5:
                bp_str += f" +{len(bps)-5}"
            parts.append(f"| `{deco}` | {count} | {len(bps)} | {bp_str} |")
        parts.append("")

    # Decorator combination patterns
    parts.append("### Decorator Combinations\n")
    combo_counts: Counter[str] = Counter()
    for r in all_routes:
        non_route = sorted(d for d in r.decorators if d != "route")
        combo = " + ".join(non_route) if non_route else "(route only)"
        combo_counts[combo] += 1

    parts.append("| Combination | Count | % |")
    parts.append("|-------------|-------|---|")
    for combo, count in combo_counts.most_common():
        pct = count * 100 / len(all_routes)
        parts.append(f"| {combo} | {count} | {pct:.1f}% |")
    parts.append("")

    # ═════════════════════════════════════════════════════════════════
    # 5. Route Contracts — inputs/outputs per blueprint
    # ═════════════════════════════════════════════════════════════════
    parts.append("## Route Contracts\n")
    parts.append(
        "> Per-route input/output analysis. Shows what each route accepts "
        "and what it returns.\n"
    )

    for bp in sorted(result.blueprints, key=lambda b: -b.total_routes):
        # Only show blueprints that have routes with detected params or codes
        has_contract_data = any(
            r.request_params or r.response_codes or r.url_params
            for r in bp.routes
        )
        if not has_contract_data:
            continue

        parts.append(f"### {bp.name}\n")

        for r in sorted(bp.routes, key=lambda x: x.endpoint):
            if not (r.request_params or r.response_codes or r.url_params):
                continue

            methods = ",".join(r.http_methods)
            decos = [d for d in r.decorators if d != "route"]
            deco_str = f"  🎭 {', '.join(decos)}" if decos else ""

            parts.append(f"**`{methods} {r.endpoint}`** — `{r.function_name}`{deco_str}\n")

            # URL params
            if r.url_params:
                parts.append(f"- 🔗 URL: {', '.join(f'`<{p}>`' for p in r.url_params)}")

            # Request params
            if r.request_params:
                for p in r.request_params:
                    req = "required" if p["required"] else "optional"
                    parts.append(f"- 📥 `{p['source']}.{p['name']}` ({req})")

            # Response codes
            if r.response_codes:
                code_strs = []
                for c in r.response_codes:
                    if c < 300:
                        code_strs.append(f"✅ {c}")
                    elif c < 400:
                        code_strs.append(f"↗️ {c}")
                    elif c < 500:
                        code_strs.append(f"⚠️ {c}")
                    else:
                        code_strs.append(f"❌ {c}")
                parts.append(f"- 📤 Codes: {', '.join(code_strs)}")

            parts.append("")

    # ═════════════════════════════════════════════════════════════════
    # 6. Complexity Analysis
    # ═════════════════════════════════════════════════════════════════
    parts.append("## Complexity Analysis\n")

    # Size distribution tiers
    parts.append("### Size Distribution\n")
    tiers = [
        ("🟢", "Small", lambda r: r.body_lines < 20),
        ("🟡", "Medium", lambda r: 20 <= r.body_lines < 50),
        ("🟠", "Large", lambda r: 50 <= r.body_lines < 100),
        ("🔴", "Very Large", lambda r: r.body_lines >= 100),
    ]

    for icon, label, pred in tiers:
        count = sum(1 for r in all_routes if pred(r))
        pct = count * 100 / len(all_routes) if all_routes else 0
        filled = round(pct / 5)
        bar = "█" * filled + "░" * (20 - filled)
        parts.append(f"{icon} **{label}**: `{bar}` {count} routes ({pct:.0f}%)")
    parts.append("")

    # Top 15 by complexity (branches * nesting)
    parts.append("### Highest Complexity Routes\n")
    parts.append(
        "> Sorted by composite complexity: body lines × branch count × nesting depth.\n"
    )
    parts.append("| # | Function | Blueprint | Lines | Branches | Depth | Complexity |")
    parts.append("|---|----------|-----------|-------|----------|-------|-----------|")

    def _complexity_score(r):
        return r.body_lines * max(r.branch_count, 1) * max(r.nesting_depth, 1)

    for i, r in enumerate(sorted(all_routes, key=_complexity_score, reverse=True)[:15], 1):
        score = _complexity_score(r)
        parts.append(
            f"| {i} | `{r.function_name}` | {r.blueprint} | "
            f"{r.body_lines} | {r.branch_count} | {r.nesting_depth} | **{score:,}** |"
        )
    parts.append("")

    # Docstring quality tiers
    parts.append("### Docstring Quality\n")
    doc_none = sum(1 for r in all_routes if not r.has_docstring)
    doc_brief = sum(1 for r in all_routes if r.has_docstring and r.docstring_lines < 5)
    doc_detailed = sum(1 for r in all_routes if r.has_docstring and r.docstring_lines >= 5)

    parts.append(f"| Tier | Count | Description |")
    parts.append(f"|------|-------|-------------|")
    parts.append(f"| 🟢 Detailed (5+ lines) | {doc_detailed} | Comprehensive documentation |")
    parts.append(f"| 🟡 Brief (1-4 lines) | {doc_brief} | Short description |")
    parts.append(f"| 🔴 Missing | {doc_none} | No docstring |")

    if doc_none > 0:
        parts.append(f"\n**Missing docstrings:**")
        for r in sorted((r for r in all_routes if not r.has_docstring), key=lambda x: x.blueprint):
            parts.append(f"- `{r.blueprint}.{r.function_name}` ({r.endpoint})")
    parts.append("")

    # ═════════════════════════════════════════════════════════════════
    # 7. Consistency Matrix
    # ═════════════════════════════════════════════════════════════════
    parts.append("## Consistency Matrix\n")
    parts.append(
        "> Cross-blueprint pattern comparison. Highlights where a blueprint "
        "deviates from the project norm.\n"
    )

    # Calculate project-wide norms
    total_r = len(all_routes)
    pct_tracked = sum(1 for r in all_routes if r.has_run_tracking) * 100 / total_r if total_r else 0
    pct_err = sum(1 for r in all_routes if r.has_error_handling) * 100 / total_r if total_r else 0
    pct_docs = sum(1 for r in all_routes if r.has_docstring) * 100 / total_r if total_r else 0
    pct_methods = sum(1 for r in all_routes if r.methods_explicit) * 100 / total_r if total_r else 0

    parts.append(
        f"> **Project norms**: docs={pct_docs:.0f}%, "
        f"tracking={pct_tracked:.0f}%, "
        f"error handling={pct_err:.0f}%, "
        f"explicit methods={pct_methods:.0f}%\n"
    )

    parts.append("| Blueprint | Routes | Docs | Track | ErrH | Methods | vs Norm |")
    parts.append("|-----------|--------|------|-------|------|---------|---------|")

    for bp in sorted(result.blueprints, key=lambda b: -b.total_routes):
        n = bp.total_routes
        if n == 0:
            continue
        bp_docs = sum(1 for r in bp.routes if r.has_docstring) * 100 / n
        bp_track = sum(1 for r in bp.routes if r.has_run_tracking) * 100 / n
        bp_err = sum(1 for r in bp.routes if r.has_error_handling) * 100 / n
        bp_meth = sum(1 for r in bp.routes if r.methods_explicit) * 100 / n

        # Calculate deviation from norm
        deviations = []
        if bp_track < pct_tracked - 20:
            deviations.append("📊↓")
        elif bp_track > pct_tracked + 20:
            deviations.append("📊↑")
        if bp_err < pct_err - 15:
            deviations.append("🛡️↓")
        elif bp_err > pct_err + 30:
            deviations.append("🛡️↑")
        if bp_meth < pct_methods - 20:
            deviations.append("📋↓")
        elif bp_meth > pct_methods + 20:
            deviations.append("📋↑")

        dev_str = " ".join(deviations) if deviations else "≈"

        parts.append(
            f"| **{bp.name}** | {n} | "
            f"{bp_docs:.0f}% | {bp_track:.0f}% | {bp_err:.0f}% | {bp_meth:.0f}% | {dev_str} |"
        )
    parts.append("")

    # ═════════════════════════════════════════════════════════════════
    # 8. Anomaly Detection
    # ═════════════════════════════════════════════════════════════════
    parts.append("## Anomaly Detection\n")
    parts.append(
        "> Routes that break the dominant pattern of their blueprint. "
        "Not violations — just observations worth reviewing.\n"
    )

    anomalies_found = False

    for bp in sorted(result.blueprints, key=lambda b: -b.total_routes):
        n = bp.total_routes
        if n < 3:
            continue  # Too few routes to establish a pattern

        bp_anomalies = []

        # Check for tracking outliers
        tracked_count = sum(1 for r in bp.routes if r.has_run_tracking)
        tracked_pct = tracked_count * 100 / n
        if 20 < tracked_pct < 80:
            # Mixed — some tracked, some not. Flag the minority
            if tracked_pct >= 50:
                outliers = [r for r in bp.routes if not r.has_run_tracking]
                bp_anomalies.append(
                    f"📊 {tracked_count}/{n} routes tracked — "
                    f"untracked: {', '.join(f'`{r.function_name}`' for r in outliers[:5])}"
                )
            else:
                outliers = [r for r in bp.routes if r.has_run_tracking]
                bp_anomalies.append(
                    f"📊 Only {tracked_count}/{n} routes tracked: "
                    f"{', '.join(f'`{r.function_name}`' for r in outliers[:5])}"
                )

        # Check for error handling outliers
        err_count = sum(1 for r in bp.routes if r.has_error_handling)
        err_pct = err_count * 100 / n
        if 20 < err_pct < 80:
            if err_pct >= 50:
                outliers = [r for r in bp.routes if not r.has_error_handling]
                bp_anomalies.append(
                    f"🛡️ {err_count}/{n} routes have error handling — "
                    f"without: {', '.join(f'`{r.function_name}`' for r in outliers[:5])}"
                )
            else:
                outliers = [r for r in bp.routes if r.has_error_handling]
                bp_anomalies.append(
                    f"🛡️ Only {err_count}/{n} routes have error handling: "
                    f"{', '.join(f'`{r.function_name}`' for r in outliers[:5])}"
                )

        # Check for size outliers within blueprint
        avg_size = sum(r.body_lines for r in bp.routes) / n
        size_outliers = [r for r in bp.routes if r.body_lines > avg_size * 3 and r.body_lines > 50]
        if size_outliers:
            bp_anomalies.append(
                f"📏 Avg body {avg_size:.0f} lines — outliers: "
                + ", ".join(f"`{r.function_name}` ({r.body_lines}L)" for r in sorted(size_outliers, key=lambda x: -x.body_lines)[:3])
            )

        # Check for docstring gaps
        doc_count = sum(1 for r in bp.routes if r.has_docstring)
        if 0 < n - doc_count <= 5 and doc_count > 0:
            missing = [r for r in bp.routes if not r.has_docstring]
            bp_anomalies.append(
                f"📝 {doc_count}/{n} documented — missing: "
                + ", ".join(f"`{r.function_name}`" for r in missing)
            )

        if bp_anomalies:
            anomalies_found = True
            parts.append(f"### {bp.name}\n")
            for a in bp_anomalies:
                parts.append(f"- {a}")
            parts.append("")

    if not anomalies_found:
        parts.append("No significant anomalies detected. All blueprints show consistent patterns. ✅\n")

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════
#  JSON Report
# ═══════════════════════════════════════════════════════════════════


def _render_json(result) -> str:
    """Render the route audit as a JSON document."""
    from dataclasses import asdict

    data = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "framework": result.framework,
        "total_blueprints": result.total_blueprints,
        "total_routes": result.total_routes,
        "coverage": {},
        "blueprints": [],
    }

    # Coverage facts
    for attr in [
        "has_docstring", "has_auth", "has_run_tracking",
        "has_error_handling", "methods_explicit",
    ]:
        with_it, total = result.coverage(attr)
        data["coverage"][attr] = {
            "with": with_it,
            "without": total - with_it,
            "total": total,
            "percent": round(with_it * 100 / total, 1) if total else 0,
        }

    # Blueprint details
    for bp in result.blueprints:
        bp_data = {
            "name": bp.name,
            "package_path": bp.package_path,
            "total_routes": bp.total_routes,
            "init_lines": bp.init_lines,
            "init_has_route_handlers": bp.init_has_route_handlers,
            "routes": [],
        }
        for r in bp.routes:
            bp_data["routes"].append(asdict(r))
        data["blueprints"].append(bp_data)

    return json.dumps(data, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Parameters match the @param declarations in the script header.
    """
    parser = argparse.ArgumentParser(
        description="Audit HTTP route quality — observe and report facts.",
    )
    parser.add_argument(
        "--scope", default=None,
        help="Blueprint scope — limit to specific blueprint name",
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
        help="Output filename (default: route_audit.md)",
    )
    parser.add_argument(
        "--routes-path", default="src/ui/web/routes",
        help="Path to route directory relative to project root",
    )
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
