#!/usr/bin/env python3
"""
@script
name: API Catalog Generator
category: generator
mode: fully_automated
tags: api, openapi, bruno, docs, flask, routes, catalog
default_output: docs/api/
output_formats: markdown, json, openapi, bruno
requires_tools: (none)
timeout: 120
description: Generates a complete API catalog from Flask route definitions.
    Scans all route files via AST (no runtime required), resolves blueprint
    prefixes, infers request body schemas from data.get() patterns, detects
    response types and error codes.  Outputs in multiple formats: markdown
    reference doc, JSON catalog, OpenAPI 3.0 YAML spec, or Bruno collection.

@param output: path = docs/api/ | Output directory
@param format: choice = markdown [markdown, json, openapi, bruno, all] | Output format(s)
@param source-dir: string = src | Source directory
@param scope: string = none | Limit to specific module (e.g. "docker")
@param base-url: string = http://localhost:5000 | Base URL for the API
@param title: string = DevOps Control Plane API | API title
@param version: string = 1.0.0 | API version
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    """Main entry point for the API catalog generator."""
    args = parse_args()

    project_root = Path(os.environ.get("SCRIPT_PROJECT_ROOT", ".")).resolve()
    output_dir = Path(
        args.output
        or os.environ.get("SCRIPT_OUTPUT_DIR", "docs/api")
    )
    fmt = args.format or os.environ.get("SCRIPT_PARAM_FORMAT", "markdown")
    scope = args.scope if args.scope != "none" else None
    source_dir = args.source_dir
    base_url = args.base_url
    title = args.title
    version = args.version

    # ── Scan routes ──────────────────────────────────────────────
    from api_route_scanner import ApiRouteScanner

    print("🔍 Scanning API routes...")
    scanner = ApiRouteScanner(source_dir=source_dir)
    catalog = scanner.scan(project_root)
    catalog.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Apply scope filter
    if scope:
        catalog.routes = [
            r for r in catalog.routes if scope in r.tags
        ]

    total = len(catalog.routes)
    modules = catalog.modules
    print(f"   Found {total} routes across {len(modules)} modules")
    print(f"   Modules: {', '.join(modules[:10])}{'...' if len(modules) > 10 else ''}")
    print(f"   Files scanned: {catalog.files_scanned}")

    # ── Generate output ──────────────────────────────────────────
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    formats = ["markdown", "json", "openapi", "bruno"] if fmt == "all" else [fmt]

    for output_fmt in formats:
        print(f"📊 Generating {output_fmt} output...")
        if output_fmt == "markdown":
            content = render_markdown(catalog, title=title, version=version)
            out_path = output_dir / "api-catalog.md"
            out_path.write_text(content, encoding="utf-8")
            print(f"   ✅ {out_path}")

        elif output_fmt == "json":
            content = render_json(catalog)
            out_path = output_dir / "api-catalog.json"
            out_path.write_text(content, encoding="utf-8")
            print(f"   ✅ {out_path}")

        elif output_fmt == "openapi":
            content = render_openapi(
                catalog, title=title, version=version, base_url=base_url,
            )
            out_path = output_dir / "openapi.yaml"
            out_path.write_text(content, encoding="utf-8")
            print(f"   ✅ {out_path}")

        elif output_fmt == "bruno":
            bruno_dir = output_dir / "bruno-collection"
            render_bruno(
                catalog, bruno_dir, base_url=base_url, title=title,
            )
            print(f"   ✅ {bruno_dir}/")

    print(f"✅ API catalog generated in {output_dir}")
    return 0


# ═══════════════════════════════════════════════════════════════════
#  Argument Parsing
# ═══════════════════════════════════════════════════════════════════


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="API Catalog Generator")
    parser.add_argument("--output", default=os.environ.get("SCRIPT_PARAM_OUTPUT", ""))
    parser.add_argument(
        "--format", default=os.environ.get("SCRIPT_PARAM_FORMAT", ""),
        choices=["markdown", "json", "openapi", "bruno", "all"],
    )
    parser.add_argument("--scope", default=os.environ.get("SCRIPT_PARAM_SCOPE", "none"))
    parser.add_argument(
        "--source-dir", dest="source_dir",
        default=os.environ.get("SCRIPT_PARAM_SOURCE_DIR", "src"),
    )
    parser.add_argument(
        "--base-url", dest="base_url",
        default=os.environ.get("SCRIPT_PARAM_BASE_URL", "http://localhost:5000"),
    )
    parser.add_argument(
        "--title", default=os.environ.get("SCRIPT_PARAM_TITLE", "DevOps Control Plane API"),
    )
    parser.add_argument(
        "--version", default=os.environ.get("SCRIPT_PARAM_VERSION", "1.0.0"),
    )
    return parser.parse_args()


# ═══════════════════════════════════════════════════════════════════
#  Markdown Renderer
# ═══════════════════════════════════════════════════════════════════


def render_markdown(catalog, *, title: str, version: str) -> str:
    """Render the API catalog as a comprehensive markdown reference."""
    parts: list[str] = []

    parts.append(f"# {title}\n")
    parts.append(f"> Version: {version}  |  Generated: {catalog.timestamp}\n")
    parts.append(f"> **{len(catalog.routes)}** endpoints across "
                 f"**{len(catalog.modules)}** modules\n")

    # ── Table of Contents ──
    parts.append("## Table of Contents\n")

    parts.append("1. [Overview](#overview)")
    for i, module in enumerate(catalog.modules, 2):
        count = len(catalog.by_module.get(module, []))
        parts.append(f"{i}. [{module.title()}](#module-{module}) ({count} endpoints)")
    parts.append("")

    # ── Overview ──
    parts.append("## Overview\n")

    # Method breakdown
    from collections import Counter
    method_counts = Counter()
    for r in catalog.routes:
        for m in r.methods:
            method_counts[m] += 1

    parts.append("### Methods\n")
    parts.append("| Method | Count |")
    parts.append("|--------|-------|")
    for method in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
        if method in method_counts:
            parts.append(f"| {method} | {method_counts[method]} |")
    parts.append("")

    # Response types
    resp_counts = Counter(r.response_type for r in catalog.routes)
    parts.append("### Response Types\n")
    parts.append("| Type | Count |")
    parts.append("|------|-------|")
    for rtype, count in resp_counts.most_common():
        parts.append(f"| {rtype} | {count} |")
    parts.append("")

    # Quick reference table
    parts.append("### All Endpoints\n")
    parts.append("| Method | Path | Summary | Module |")
    parts.append("|--------|------|---------|--------|")
    for r in catalog.routes:
        methods = ", ".join(r.methods)
        parts.append(
            f"| `{methods}` | `{r.full_path}` | "
            f"{_esc(r.summary[:60])} | {r.tags[0] if r.tags else '—'} |"
        )
    parts.append("")

    # ── Per-Module Sections ──
    for module, routes in catalog.by_module.items():
        parts.append(f"## Module: {module.title()}\n")
        parts.append(f"> {len(routes)} endpoints\n")

        for r in routes:
            methods = ", ".join(r.methods)
            parts.append(f"### `{methods}` `{r.full_path}`\n")
            parts.append(f"**Function**: `{r.function_name}()`  ")
            parts.append(f"**File**: `{r.file}`:{r.lineno}  ")
            parts.append(f"**Response**: {r.response_type}"
                         f"{'  🔄 streaming' if r.is_streaming else ''}\n")

            if r.summary:
                parts.append(f"> {r.summary}\n")
            if r.description:
                parts.append(f"{r.description}\n")

            # Path parameters
            if r.path_params:
                parts.append("**Path Parameters**\n")
                parts.append("| Name | Type |")
                parts.append("|------|------|")
                for p in r.path_params:
                    parts.append(f"| `{p.name}` | {p.type} |")
                parts.append("")

            # Request body
            if r.request_fields:
                parts.append("**Request Body** (`application/json`)\n")
                parts.append("| Field | Type | Required | Default |")
                parts.append("|-------|------|----------|---------|")
                for f in r.request_fields:
                    req = "✓" if f.required else ""
                    default = f"`{f.default!r}`" if f.has_default else "—"
                    parts.append(
                        f"| `{f.name}` | {f.inferred_type} | "
                        f"{req} | {default} |"
                    )
                parts.append("")

            # Error responses
            if r.error_responses:
                parts.append("**Error Responses**\n")
                parts.append("| Code | Message |")
                parts.append("|------|---------|")
                for e in r.error_responses:
                    parts.append(f"| {e.status_code} | {_esc(e.message)} |")
                parts.append("")

            parts.append("---\n")

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════
#  JSON Renderer
# ═══════════════════════════════════════════════════════════════════


def render_json(catalog) -> str:
    """Render the API catalog as JSON."""
    from dataclasses import asdict
    routes_data = [asdict(r) for r in catalog.routes]
    data = {
        "timestamp": catalog.timestamp,
        "files_scanned": catalog.files_scanned,
        "total_routes": len(catalog.routes),
        "modules": catalog.modules,
        "routes": routes_data,
    }
    return json.dumps(data, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════════
#  OpenAPI 3.0 Renderer
# ═══════════════════════════════════════════════════════════════════


def render_openapi(
    catalog,
    *,
    title: str,
    version: str,
    base_url: str,
) -> str:
    """Render the API catalog as an OpenAPI 3.0 YAML spec.

    Uses manual YAML generation (no pyyaml dependency required).
    """
    lines: list[str] = []

    # ── Header ──
    lines.append("openapi: '3.0.3'")
    lines.append("info:")
    lines.append(f"  title: {_yaml_str(title)}")
    lines.append(f"  version: {_yaml_str(version)}")
    lines.append(f"  description: >-")
    lines.append(f"    Auto-generated API specification from Flask route definitions.")
    lines.append(f"    Generated: {catalog.timestamp}")
    lines.append("servers:")
    lines.append(f"  - url: {base_url}")
    lines.append(f"    description: Local development")
    lines.append("")

    # ── Tags ──
    lines.append("tags:")
    for module in catalog.modules:
        count = len(catalog.by_module.get(module, []))
        lines.append(f"  - name: {module}")
        lines.append(f"    description: {module.title()} endpoints ({count})")
    lines.append("")

    # ── Paths ──
    lines.append("paths:")

    # Group routes by path (multiple methods on same path)
    by_path: dict[str, list] = defaultdict(list)
    for r in catalog.routes:
        by_path[r.full_path].append(r)

    for path, routes in sorted(by_path.items()):
        # Convert Flask path params to OpenAPI format
        openapi_path = _flask_to_openapi_path(path)
        lines.append(f"  {openapi_path}:")

        for r in routes:
            for method in r.methods:
                method_lower = method.lower()
                lines.append(f"    {method_lower}:")
                lines.append(f"      operationId: {r.function_name}")
                lines.append(f"      summary: {_yaml_str(r.summary or r.function_name)}")
                if r.tags:
                    lines.append(f"      tags:")
                    for t in r.tags:
                        lines.append(f"        - {t}")

                if r.description:
                    lines.append(f"      description: >-")
                    for desc_line in r.description.split("\n"):
                        lines.append(f"        {desc_line.strip()}")

                # Path parameters
                has_params = bool(r.path_params)
                if has_params:
                    lines.append("      parameters:")
                    for p in r.path_params:
                        oa_type = _flask_type_to_openapi(p.type)
                        lines.append(f"        - name: {p.name}")
                        lines.append(f"          in: path")
                        lines.append(f"          required: true")
                        lines.append(f"          schema:")
                        lines.append(f"            type: {oa_type}")

                # Request body
                if r.request_fields and method_lower in ("post", "put", "patch", "delete"):
                    lines.append("      requestBody:")
                    lines.append("        required: true")
                    lines.append("        content:")
                    lines.append("          application/json:")
                    lines.append("            schema:")
                    lines.append("              type: object")

                    required_fields = [f for f in r.request_fields if f.required]
                    if required_fields:
                        lines.append("              required:")
                        for f in required_fields:
                            lines.append(f"                - {f.name}")

                    lines.append("              properties:")
                    for f in r.request_fields:
                        lines.append(f"                {f.name}:")
                        lines.append(f"                  type: {f.inferred_type}")
                        if f.has_default and f.default is not None:
                            lines.append(f"                  default: {_yaml_value(f.default)}")

                # Responses
                lines.append("      responses:")
                lines.append("        '200':")
                if r.response_type == "json":
                    lines.append("          description: Success")
                    lines.append("          content:")
                    lines.append("            application/json:")
                    lines.append("              schema:")
                    lines.append("                type: object")
                elif r.response_type == "stream":
                    lines.append("          description: Streaming response")
                    lines.append("          content:")
                    lines.append("            text/event-stream:")
                    lines.append("              schema:")
                    lines.append("                type: string")
                elif r.response_type == "file":
                    lines.append("          description: File download")
                elif r.response_type == "html":
                    lines.append("          description: HTML page")
                    lines.append("          content:")
                    lines.append("            text/html:")
                    lines.append("              schema:")
                    lines.append("                type: string")
                else:
                    lines.append("          description: Success")

                for err in r.error_responses:
                    lines.append(f"        '{err.status_code}':")
                    desc = err.message or f"Error {err.status_code}"
                    lines.append(f"          description: {_yaml_str(desc)}")
                    lines.append(f"          content:")
                    lines.append(f"            application/json:")
                    lines.append(f"              schema:")
                    lines.append(f"                type: object")
                    lines.append(f"                properties:")
                    lines.append(f"                  error:")
                    lines.append(f"                    type: string")

                lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
#  Bruno Collection Renderer
# ═══════════════════════════════════════════════════════════════════


def render_bruno(
    catalog,
    output_dir: Path,
    *,
    base_url: str,
    title: str,
) -> None:
    """Render the API catalog as a Bruno collection (folder of .bru files)."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── bruno.json (collection manifest) ──
    collection_manifest = {
        "version": "1",
        "name": title,
        "type": "collection",
    }
    (output_dir / "bruno.json").write_text(
        json.dumps(collection_manifest, indent=2), encoding="utf-8",
    )

    # ── collection.bru (collection settings) ──
    collection_bru = (
        "headers {\n"
        "  Content-Type: application/json\n"
        "}\n"
    )
    (output_dir / "collection.bru").write_text(collection_bru, encoding="utf-8")

    # ── environments/local.bru ──
    env_dir = output_dir / "environments"
    env_dir.mkdir(exist_ok=True)
    env_content = (
        "vars {\n"
        f"  baseUrl: {base_url}\n"
        "}\n"
    )
    (env_dir / "local.bru").write_text(env_content, encoding="utf-8")

    # ── Route files ──
    for module, routes in catalog.by_module.items():
        module_dir = output_dir / module
        module_dir.mkdir(exist_ok=True)

        for i, r in enumerate(routes, 1):
            for method in r.methods:
                # Generate filename
                filename = _bruno_filename(r, method)
                filepath = module_dir / filename

                content = _render_bruno_file(r, method, seq=i)
                filepath.write_text(content, encoding="utf-8")


def _render_bruno_file(route, method: str, *, seq: int) -> str:
    """Render a single .bru file for a route/method pair."""
    parts: list[str] = []

    # Meta block
    parts.append("meta {")
    parts.append(f"  name: {route.summary or route.function_name}")
    parts.append(f"  type: http")
    parts.append(f"  seq: {seq}")
    parts.append("}\n")

    # Request block
    method_lower = method.lower()
    # Build URL with path params as template variables
    url_path = route.full_path
    for p in route.path_params:
        url_path = url_path.replace(f"<{p.type}:{p.name}>", f"{{{{{p.name}}}}}")
        url_path = url_path.replace(f"<{p.name}>", f"{{{{{p.name}}}}}")

    parts.append(f"{method_lower} {{")
    parts.append(f"  url: {{{{baseUrl}}}}{url_path}")

    if route.request_fields and method_lower in ("post", "put", "patch", "delete"):
        parts.append(f"  body: json")
    else:
        parts.append(f"  body: none")

    parts.append("}\n")

    # Headers
    parts.append("headers {")
    parts.append("  Content-Type: application/json")
    parts.append("}\n")

    # Body (for POST/PUT/PATCH)
    if route.request_fields and method_lower in ("post", "put", "patch", "delete"):
        parts.append("body:json {")
        body_obj = {}
        for f in route.request_fields:
            if f.has_default and f.default is not None:
                body_obj[f.name] = f.default
            elif f.inferred_type == "string":
                body_obj[f.name] = ""
            elif f.inferred_type == "integer":
                body_obj[f.name] = 0
            elif f.inferred_type == "boolean":
                body_obj[f.name] = False
            elif f.inferred_type == "array":
                body_obj[f.name] = []
            elif f.inferred_type == "object":
                body_obj[f.name] = {}
            else:
                body_obj[f.name] = ""
        parts.append(f"  {json.dumps(body_obj, indent=2)}")
        parts.append("}\n")

    # Path params as variables
    if route.path_params:
        parts.append("vars:pre-request {")
        for p in route.path_params:
            example = "1" if p.type == "int" else "example"
            parts.append(f"  {p.name}: {example}")
        parts.append("}\n")

    # Docs (from docstring)
    if route.docstring:
        parts.append("docs {")
        for line in route.docstring.split("\n"):
            parts.append(f"  {line.strip()}")
        parts.append("}")

    return "\n".join(parts)


def _bruno_filename(route, method: str) -> str:
    """Generate a Bruno-compatible filename for a route.

    Example: "GET /docker/status" → "get-docker-status.bru"
    """
    # Clean up the path
    path_clean = route.path.strip("/").replace("/", "-").replace("<", "").replace(">", "")
    path_clean = re.sub(r"[^a-zA-Z0-9_-]", "", path_clean)
    if not path_clean:
        path_clean = route.function_name

    return f"{method.lower()}-{path_clean}.bru"


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _esc(text: str) -> str:
    """Escape markdown special characters in table cells."""
    return text.replace("|", "\\|").replace("\n", " ")


def _yaml_str(text: str) -> str:
    """Format a string for YAML output."""
    if not text:
        return "''"
    # Simple strings don't need quoting
    if re.match(r'^[a-zA-Z0-9 ._/-]+$', text):
        return text
    return f"'{text.replace(chr(39), chr(39)+chr(39))}'"


def _yaml_value(val: object) -> str:
    """Format a Python value for YAML."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        return _yaml_str(val)
    if isinstance(val, list):
        return "[]"
    if isinstance(val, dict):
        return "{}"
    return str(val)


def _flask_to_openapi_path(path: str) -> str:
    """Convert Flask path params to OpenAPI format.

    Flask: /docker/<int:container_id>/logs
    OpenAPI: /docker/{container_id}/logs
    """
    result = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", path)
    return result


def _flask_type_to_openapi(flask_type: str) -> str:
    """Convert Flask URL param type to OpenAPI type."""
    return {
        "int": "integer",
        "float": "number",
        "path": "string",
        "string": "string",
        "uuid": "string",
    }.get(flask_type, "string")


# ═══════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    sys.exit(main())
