"""
L2 — Structure analysis (on-demand, 1-5s).

Builds the import graph, computes module boundaries,
exposure ratios, and cross-module dependency mapping.

Parses ALL file types via the parser registry.
Import/dependency data comes from parsers that extract it
(currently Python; JS/Go/Rust parsers will add more).

Public API:
    l2_structure(project_root)  → import graph + module analysis
"""

from __future__ import annotations

import collections
import logging
import time
from pathlib import Path

from src.core.services.audit.models import wrap_result
from src.core.services.audit.parsers._base import FileAnalysis

logger = logging.getLogger(__name__)

# Module entry-point files by language.
# These define the public API of a module/package directory.
_MODULE_ENTRY_FILES: set[str] = {
    "__init__.py",     # Python
    "index.js",        # JavaScript / Node.js
    "index.ts",        # TypeScript
    "index.tsx",       # TypeScript React
    "index.mjs",       # ES Module
    "index.cjs",       # CommonJS
    "mod.rs",          # Rust
    "lib.rs",          # Rust (library crate root)
    "main.rs",         # Rust (binary crate root)
    "package.json",    # Node.js package manifest
}


# ═══════════════════════════════════════════════════════════════════
#  Import graph construction
# ═══════════════════════════════════════════════════════════════════


def _build_import_graph(
    analyses: dict[str, FileAnalysis],
) -> dict:
    """Build the import graph from parse_tree results.

    Returns:
        {
            "nodes": [{"id": "src/ui/web/server.py", "module": "src.ui.web",
                       "language": "python", ...}],
            "edges": [{"from": "src/ui/web/server.py", "to": "flask",
                       "type": "external"}, ...],
            "internal_edges": [{"from": "...", "to": "...", "names": [...]}],
            "external_deps": {"flask": {"files": [...], "count": int}},
            "total_nodes": int,
            "internal_edge_count": int,
            "external_edge_count": int,
        }
    """
    nodes = []
    edges = []
    internal_edges = []
    external_deps: dict[str, dict] = collections.defaultdict(
        lambda: {"files": [], "count": 0}
    )

    for rel_path, analysis in analyses.items():
        # Determine module from path
        parts = Path(rel_path).parts
        if len(parts) > 1:
            module = ".".join(parts[:-1])
        else:
            module = "__root__"

        nodes.append({
            "id": rel_path,
            "module": module,
            "language": analysis.language,
            "file_type": analysis.file_type,
            "imports": analysis.metrics.import_count,
            "symbols": analysis.metrics.function_count + analysis.metrics.class_count,
            "lines": analysis.metrics.total_lines,
        })

        for imp in analysis.imports:
            if imp.is_internal:
                internal_edges.append({
                    "from": rel_path,
                    "to": imp.module,
                    "names": imp.names,
                    "lineno": imp.lineno,
                })
            elif not imp.is_stdlib:
                top = imp.top_level
                edges.append({
                    "from": rel_path,
                    "to": top,
                    "type": "external",
                    "lineno": imp.lineno,
                })
                external_deps[top]["files"].append(rel_path)
                external_deps[top]["count"] += 1

    # Deduplicate file lists in external deps
    for dep_info in external_deps.values():
        dep_info["files"] = sorted(set(dep_info["files"]))
        dep_info["count"] = len(dep_info["files"])

    return {
        "nodes": nodes,
        "edges": edges,
        "internal_edges": internal_edges,
        "external_deps": dict(external_deps),
        "total_nodes": len(nodes),
        "internal_edge_count": len(internal_edges),
        "external_edge_count": len(edges),
    }


# ═══════════════════════════════════════════════════════════════════
#  Module boundary analysis
# ═══════════════════════════════════════════════════════════════════


def _analyze_modules(
    analyses: dict[str, FileAnalysis],
    project_root: Path,
) -> list[dict]:
    """Analyze module boundaries and exposure ratios.

    Returns:
        [{
            "module": "src.core.services",
            "files": int,
            "languages": {"python": 5, "yaml": 2},
            "total_symbols": int,
            "public_symbols": int,
            "private_symbols": int,
            "exposure_ratio": float,
            "has_init": bool,  (any module entry-point file)
            "init_exports": list[str],
            "total_lines": int,
            "total_functions": int,
            "total_classes": int,
        }, ...]
    """
    # Group files by module (directory)
    module_files: dict[str, list] = collections.defaultdict(list)
    for rel_path, analysis in analyses.items():
        parts = Path(rel_path).parts
        if len(parts) > 1:
            module = ".".join(parts[:-1])
        else:
            module = "__root__"
        module_files[module].append((rel_path, analysis))

    modules = []
    for module_name, files in sorted(module_files.items()):
        total_symbols = 0
        public_symbols = 0
        private_symbols = 0
        total_lines = 0
        total_funcs = 0
        total_classes = 0
        has_init = False
        init_exports: list[str] = []
        lang_counts: dict[str, int] = collections.defaultdict(int)

        for rel_path, analysis in files:
            lang_counts[analysis.language] += 1

            filename = Path(rel_path).name
            if filename in _MODULE_ENTRY_FILES:
                has_init = True
                # Extract public symbols from entry-point files
                for sym in analysis.symbols:
                    if sym.is_public:
                        init_exports.append(sym.name)

            for sym in analysis.symbols:
                total_symbols += 1
                if sym.is_public:
                    public_symbols += 1
                else:
                    private_symbols += 1
                if sym.kind in ("function", "async_function"):
                    total_funcs += 1
                elif sym.kind == "class":
                    total_classes += 1

            total_lines += analysis.metrics.total_lines

        exposure = public_symbols / total_symbols if total_symbols > 0 else 0.0

        modules.append({
            "module": module_name,
            "files": len(files),
            "languages": dict(lang_counts),
            "total_symbols": total_symbols,
            "public_symbols": public_symbols,
            "private_symbols": private_symbols,
            "exposure_ratio": round(exposure, 3),
            "has_init": has_init,
            "init_exports": init_exports,
            "total_lines": total_lines,
            "total_functions": total_funcs,
            "total_classes": total_classes,
        })

    return modules


# ═══════════════════════════════════════════════════════════════════
#  Cross-module dependency mapping
# ═══════════════════════════════════════════════════════════════════


def _cross_module_deps(
    analyses: dict[str, FileAnalysis],
) -> list[dict]:
    """Map internal cross-module dependencies.

    Returns:
        [{
            "from_module": "src.ui.web",
            "to_module": "src.core.services",
            "import_count": 15,
            "files_involved": ["src/ui/web/server.py", ...],
            "strength": "strong" | "moderate" | "weak",
        }, ...]
    """
    # Collect edges between modules
    module_edges: dict[tuple[str, str], dict] = {}

    for rel_path, analysis in analyses.items():
        from_parts = Path(rel_path).parts
        from_module = ".".join(from_parts[:-1]) if len(from_parts) > 1 else "__root__"

        for imp in analysis.imports:
            if imp.is_internal:
                # Resolve the to_module
                to_mod = imp.module
                if to_mod.startswith("."):
                    # Relative import — resolve against from_module
                    dots = len(to_mod) - len(to_mod.lstrip("."))
                    remainder = to_mod.lstrip(".")
                    # Go up 'dots' levels from from_module
                    base_parts = from_module.split(".")
                    if dots <= len(base_parts):
                        base = ".".join(base_parts[: len(base_parts) - dots + 1])
                    else:
                        base = from_module
                    to_mod = f"{base}.{remainder}" if remainder else base
                # Trim to module level (directory, not individual file)
                to_parts = to_mod.split(".")
                # Use parent directory — drop the last segment if it looks
                # like a file-level module (lowercase, no further children).
                # Keep the full dotted path to preserve sub-module precision.
                to_module = ".".join(to_parts[:-1]) if len(to_parts) > 1 else to_mod

                if to_module != from_module:
                    key = (from_module, to_module)
                    if key not in module_edges:
                        module_edges[key] = {"count": 0, "files": set()}
                    module_edges[key]["count"] += 1
                    module_edges[key]["files"].add(rel_path)

    result = []
    for (from_mod, to_mod), info in sorted(module_edges.items()):
        count = info["count"]
        if count >= 10:
            strength = "strong"
        elif count >= 4:
            strength = "moderate"
        else:
            strength = "weak"

        result.append({
            "from_module": from_mod,
            "to_module": to_mod,
            "import_count": count,
            "files_involved": sorted(info["files"]),
            "strength": strength,
        })

    # Sort by import count descending
    result.sort(key=lambda x: x["import_count"], reverse=True)
    return result


# ═══════════════════════════════════════════════════════════════════
#  Library usage sites (for drill-down)
# ═══════════════════════════════════════════════════════════════════


def _library_usage_map(
    analyses: dict[str, FileAnalysis],
) -> dict[str, dict]:
    """Map where each external library is imported.

    Returns:
        {
            "flask": {
                "sites": [{"file": "...", "lineno": 8, "names": ["Flask", "jsonify"]}, ...],
                "file_count": 12,
            },
            ...
        }
    """
    usage: dict[str, dict] = {}

    for rel_path, analysis in analyses.items():
        for imp in analysis.imports:
            if not imp.is_internal and not imp.is_stdlib:
                top = imp.top_level
                if top not in usage:
                    usage[top] = {"sites": [], "file_count": 0, "files": set()}
                usage[top]["sites"].append({
                    "file": rel_path,
                    "lineno": imp.lineno,
                    "names": imp.names,
                })
                usage[top]["files"].add(rel_path)

    # Finalize
    for info in usage.values():
        info["file_count"] = len(info["files"])
        del info["files"]

    return usage


# ═══════════════════════════════════════════════════════════════════
#  Aggregate stats (multi-language)
# ═══════════════════════════════════════════════════════════════════


def _aggregate_stats(analyses: dict[str, FileAnalysis]) -> dict:
    """Compute aggregate statistics across all parsed files.

    Includes per-language file/line breakdowns.
    """
    total_files = len(analyses)
    total_lines = 0
    total_code_lines = 0
    total_functions = 0
    total_classes = 0
    total_imports = 0
    files_with_errors = 0
    per_language: dict[str, dict] = collections.defaultdict(
        lambda: {"files": 0, "lines": 0, "code_lines": 0}
    )

    for analysis in analyses.values():
        m = analysis.metrics
        total_lines += m.total_lines
        total_code_lines += m.code_lines
        total_functions += m.function_count
        total_classes += m.class_count
        total_imports += m.import_count
        if analysis.parse_error:
            files_with_errors += 1

        lang = analysis.language
        per_language[lang]["files"] += 1
        per_language[lang]["lines"] += m.total_lines
        per_language[lang]["code_lines"] += m.code_lines

    return {
        "total_files": total_files,
        "total_lines": total_lines,
        "total_code_lines": total_code_lines,
        "total_functions": total_functions,
        "total_classes": total_classes,
        "total_imports": total_imports,
        "files_with_errors": files_with_errors,
        "per_language": dict(per_language),
    }


# ═══════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════


def l2_structure(project_root: Path) -> dict:
    """L2: Full structure analysis — import graph, modules, usage map.

    Parses ALL file types via the parser registry.
    Builds import graph from files that report imports
    (currently Python; future parsers will add JS/Go/Rust imports).

    Returns:
        {
            "_meta": AuditMeta,
            "stats": {total_files, total_lines, total_functions, per_language, ...},
            "import_graph": {nodes, edges, internal_edges, external_deps},
            "modules": [{module, files, languages, exposure_ratio, ...}, ...],
            "cross_module_deps": [{from_module, to_module, strength, ...}, ...],
            "library_usage": {flask: {sites: [...], file_count: int}, ...},
        }
    """
    from src.core.services.audit.parsers import registry

    started = time.time()

    # Parse ALL files through the registry
    analyses = registry.parse_tree(project_root)
    parse_time = int((time.time() - started) * 1000)

    # Build all derived data
    graph = _build_import_graph(analyses)
    modules = _analyze_modules(analyses, project_root)
    cross_deps = _cross_module_deps(analyses)
    lib_usage = _library_usage_map(analyses)
    stats = _aggregate_stats(analyses)
    stats["parse_time_ms"] = parse_time

    data = {
        "stats": stats,
        "import_graph": graph,
        "modules": modules,
        "cross_module_deps": cross_deps,
        "library_usage": lib_usage,
    }
    return wrap_result(data, "L2", "structure", started)
