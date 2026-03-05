"""
Audit Directive Resolver — :::audit-data in code documentation.

Resolves ``:::audit-data`` markdown directives into HTML ``<details>``
blocks containing scoped audit information (health scores, hotspots,
risk findings, cross-module dependencies).

Two entry points:

    resolve_audit_directives()
        For the admin preview endpoint.  Handles everything in-process:
        parse → scope → load → filter → render → replace.

    precompute_audit_data()
        For the Docusaurus build pipeline.  Pre-computes scoped audit
        data for every file containing the directive.  Returns a map
        written as ``_audit_data.json`` for the remark plugin.

Data sources:
    local  — reads from devops_cache (latest in-memory/file cache)
    saved  — reads from .ledger/audits/ (committed production snapshot)
    auto   — prefers saved, falls back to local
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Directive Parsing
# ═══════════════════════════════════════════════════════════════════


@dataclass
class DirectiveMatch:
    """A single :::audit-data block found in markdown content."""
    start: int          # character offset of the block start
    end: int            # character offset of the block end (after closing :::)
    scope: str          # explicit scope param, or "" for auto
    source: str         # "local", "saved", or "auto"
    raw: str            # the full matched text


# Pattern: :::audit-data with optional key="value" params, then :::
# Supports both:
#   :::audit-data
#   :::
# and:
#   :::audit-data scope="cli/audit" source="saved"
#   :::
_DIRECTIVE_RE = re.compile(
    r"^:::audit-data(?P<params>[^\n]*)\n"   # opening line with optional params
    r"(?P<body>.*?)"                         # optional body (currently unused)
    r"^:::[ \t]*$",                          # closing :::
    re.MULTILINE | re.DOTALL,
)

# Extracts key="value" pairs from the params portion
_PARAM_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


def _parse_directives(content: str) -> list[DirectiveMatch]:
    """Scan markdown for :::audit-data blocks and extract parameters."""
    matches: list[DirectiveMatch] = []

    for m in _DIRECTIVE_RE.finditer(content):
        params_str = m.group("params").strip()
        params = dict(_PARAM_RE.findall(params_str))

        matches.append(DirectiveMatch(
            start=m.start(),
            end=m.end(),
            scope=params.get("scope", ""),
            source=params.get("source", "auto"),
            raw=m.group(0),
        ))

    return matches


# ═══════════════════════════════════════════════════════════════════
#  Scope Resolution
# ═══════════════════════════════════════════════════════════════════


@dataclass
class AuditScope:
    """Resolved scope for filtering audit data."""
    module: str          # module name, e.g. "cli"
    sub_path: str        # path within module, e.g. "audit" or ""
    source_prefix: str   # full source path prefix for filtering, e.g. "src/ui/cli/audit"
    module_path: str     # module root path, e.g. "src/ui/cli"


def _resolve_scope(
    file_path: str,
    project_root: Path,
) -> AuditScope | None:
    """Auto-resolve scope from a file's position in the module tree.

    Uses _match_module() from smart_folders to find which module
    the file belongs to.

    Args:
        file_path: Relative path like "src/ui/cli/audit/README.md"
        project_root: Project root directory

    Returns:
        AuditScope or None if file is not inside any module.
    """
    from src.core.services.config_ops import read_config
    from src.core.services.smart_folders import _match_module

    cfg = read_config(project_root).get("config", {})
    modules = cfg.get("modules", [])

    if not modules:
        return None

    mod, mod_rel = _match_module(file_path, modules)
    if mod is None:
        return None

    mod_name = mod["name"]
    mod_path = mod.get("path", mod_name).rstrip("/")

    # Sub-path: everything after the module path, minus the filename
    # e.g. file_path="src/ui/cli/audit/README.md", mod_path="src/ui/cli"
    #   → mod_rel="audit/README.md" → sub_path="audit"
    parts = mod_rel.split("/") if mod_rel else []
    # Remove the filename (last part)
    if parts and "." in parts[-1]:
        parts = parts[:-1]
    sub_path = "/".join(parts)

    # Source prefix = module path + sub_path (for filtering file_scores etc.)
    source_prefix = mod_path
    if sub_path:
        source_prefix = f"{mod_path}/{sub_path}"

    return AuditScope(
        module=mod_name,
        sub_path=sub_path,
        source_prefix=source_prefix,
        module_path=mod_path,
    )


def _resolve_scope_from_explicit(
    scope_str: str,
    project_root: Path,
) -> AuditScope | None:
    """Build an AuditScope from an explicit scope parameter.

    scope_str can be:
        "cli"           → module=cli, sub_path=""
        "cli/audit"     → module=cli, sub_path="audit"
    """
    from src.core.services.config_ops import read_config

    cfg = read_config(project_root).get("config", {})
    modules = cfg.get("modules", [])

    parts = scope_str.strip("/").split("/", 1)
    target_module = parts[0]
    sub_path = parts[1] if len(parts) > 1 else ""

    # Find the module definition
    mod = None
    for m in modules:
        if m.get("name") == target_module:
            mod = m
            break

    if mod is None:
        log.warning("Explicit scope '%s' — module '%s' not found", scope_str, target_module)
        return None

    mod_path = mod.get("path", target_module).rstrip("/")
    source_prefix = mod_path
    if sub_path:
        source_prefix = f"{mod_path}/{sub_path}"

    return AuditScope(
        module=target_module,
        sub_path=sub_path,
        source_prefix=source_prefix,
        module_path=mod_path,
    )


# ═══════════════════════════════════════════════════════════════════
#  Data Loading (read-only, never triggers recomputation)
# ═══════════════════════════════════════════════════════════════════


def _read_cached_card(project_root: Path, card_key: str) -> dict | None:
    """Read cached card data without triggering recomputation.

    Follows the same pattern as l2_risk._cached_or_compute().
    Returns the data dict or None if not available.
    """
    try:
        from src.core.services.devops.cache import _load_cache
        cache = _load_cache(project_root)
        entry = cache.get(card_key)
        if entry and "data" in entry:
            return entry["data"]
    except Exception:
        pass
    return None


def _read_saved_card(project_root: Path, card_key: str) -> dict | None:
    """Read the latest saved audit snapshot for a card key from the ledger.

    Scans saved audits for the most recent one matching the card_key.
    Returns the data dict or None if not found.
    """
    try:
        from src.core.services.ledger import list_saved_audits, get_saved_audit

        saved = list_saved_audits(project_root, n=50)
        for entry in saved:
            if entry.get("card_key") == card_key:
                snapshot = get_saved_audit(project_root, entry["snapshot_id"])
                if snapshot and "data" in snapshot:
                    return snapshot["data"]
    except Exception as exc:
        log.debug("Failed to read saved audit for %s: %s", card_key, exc)
    return None


@dataclass
class AuditDataBundle:
    """All audit data needed for rendering a directive."""
    quality: dict | None       # from audit:l2:quality
    structure: dict | None     # from audit:l2:structure
    risks: dict | None         # from audit:l2:risks
    scores: dict | None        # from audit:scores
    testing: dict | None       # from testing cache
    git: dict | None           # from git cache
    configured_modules: list[dict]  # module configs [{name, path}]
    source_label: str          # "Local" or "Saved" or "N/A"
    computed_at: str           # ISO timestamp of most recent data


def _load_audit_data(project_root: Path, source: str) -> AuditDataBundle:
    """Load full audit data from the requested source.

    Loads from all 7 data sources: audit cache (quality, risks, structure,
    scores), testing cache, git cache, and module configuration.

    source values:
        "local" — only read from devops_cache
        "saved" — only read from ledger
        "auto"  — try saved first, fall back to local
    """
    audit_keys = [
        "audit:l2:quality",
        "audit:l2:structure",
        "audit:l2:risks",
        "audit:scores",
    ]

    def _read_all(reader):
        return {k: reader(project_root, k) for k in audit_keys}

    # Determine which reader(s) to use for audit data
    if source == "saved":
        data = _read_all(_read_saved_card)
        label = "Saved"
    elif source == "local":
        data = _read_all(_read_cached_card)
        label = "Local"
    else:  # auto
        data = _read_all(_read_saved_card)
        has_saved = any(v is not None for v in data.values())
        if has_saved:
            label = "Saved"
        else:
            data = _read_all(_read_cached_card)
            label = "Local"

    # Always read testing and git from local cache (not ledger)
    testing_data = _read_cached_card(project_root, "testing")
    git_data = _read_cached_card(project_root, "git")

    # Load configured modules
    configured_modules: list[dict] = []
    try:
        from src.core.services.config_ops import read_config
        cfg = read_config(project_root).get("config", {})
        configured_modules = cfg.get("modules", [])
    except Exception:
        pass

    # Determine computed_at from any available _meta
    computed_at = ""
    for card_data in data.values():
        if card_data and "_meta" in card_data:
            ts = card_data["_meta"].get("computed_at", 0)
            if ts:
                computed_at = datetime.fromtimestamp(
                    ts, tz=timezone.utc,
                ).strftime("%Y-%m-%d %H:%M UTC")
                break

    has_any = any(v is not None for v in data.values())
    if not has_any:
        label = "N/A"

    return AuditDataBundle(
        quality=data.get("audit:l2:quality"),
        structure=data.get("audit:l2:structure"),
        risks=data.get("audit:l2:risks"),
        scores=data.get("audit:scores"),
        testing=testing_data,
        git=git_data,
        configured_modules=configured_modules,
        source_label=label,
        computed_at=computed_at,
    )


# ═══════════════════════════════════════════════════════════════════
#  Scope Filtering
# ═══════════════════════════════════════════════════════════════════


@dataclass
class ScopedAuditData:
    """Audit data filtered and enriched for a specific code scope."""

    # ── Identity ──
    scope: AuditScope
    source_label: str       # "Local" / "Saved" / "N/A"
    computed_at: str         # ISO timestamp

    # ── Section 2: Module Health ──
    health_score: float | None
    file_count: int                    # live FS count
    total_lines: int                   # live FS total
    total_functions: int               # from structure module metadata
    total_classes: int                 # from structure module metadata
    cached_file_count: int             # from cache, for diff detection
    subcategory_averages: dict         # {docstrings: 9.2, nesting: 5.4, ...}
    worst_files: list[dict]            # bottom 3: [{file, score, weakest, weakest_val}]
    exposure_ratio: float | None

    # ── Context ──
    project_quality_score: float | None
    project_complexity_score: float | None
    quality_trend: str | None          # "stable" / "improving" / "declining"

    # ── Section 3: Hotspots ──
    hotspots: list[dict]
    hotspot_count: int                 # total count (not just displayed subset)

    # ── Section 4: Risk Findings ──
    findings: list[dict]               # ONLY file-scoped findings
    risk_summary: dict                 # {total, critical, high, medium, info}

    # ── Section 5: Dependencies ──
    deps_outbound: list[dict]          # [{module_name, strength, import_count}] deduped
    deps_inbound: list[dict]           # [{module_name, strength, import_count}] deduped

    # ── Section 6: Library Usage ──
    libraries: list[dict]              # [{name, files: [basename1, ...]}]

    # ── Section 7: Test Coverage ──
    test_files: list[str]
    test_ratio: float | None
    test_framework: str | None

    # ── Section 8: Development Activity ──
    git_modified: list[str]
    git_staged: list[str]
    git_untracked: list[str]
    last_modified_date: str | None
    last_modified_file: str | None

    # ── Section 2b: File Composition (multi-language) ──
    language_breakdown: list[dict] = field(default_factory=list)
    # [{language, file_type, files, lines}] sorted by lines desc

    # ── Module-root extras (only populated when sub_path == "") ──
    is_module_root: bool = False
    project_wide_findings: list[dict] = field(default_factory=list)
    # findings with no file refs (e.g. "No .env.example", vulnerabilities)
    sub_module_scores: list[dict] = field(default_factory=list)
    # [{name, score, files, worst_sub}] per sub-module under this module


# Strength ordering for dedup (keep strongest)
_STRENGTH_ORDER = {"strong": 3, "moderate": 2, "weak": 1, "": 0}


def _module_matches(dotted_path: str, module_name: str, module_path: str) -> bool:
    """Check if a dotted module path corresponds to a module.

    Cross-module deps use dotted paths like "src.ui.cli" while
    module definitions use forward-slash paths like "src/ui/cli".
    """
    if dotted_path == module_name:
        return True
    dotted_mod = module_path.replace("/", ".")
    return dotted_path == dotted_mod or dotted_path.startswith(dotted_mod + ".")


def _dotted_to_module_name(
    dotted_path: str,
    configured_modules: list[dict],
) -> str:
    """Map a dotted sub-path to a configured module name.

    E.g. "src.ui.cli.audit" → "cli" (if cli module has path "src/ui/cli").
    Falls back to the last dotted segment if no match.
    """
    for mod in configured_modules:
        mod_path = mod.get("path", "")
        dotted_mod = mod_path.replace("/", ".")
        if dotted_path == dotted_mod or dotted_path.startswith(dotted_mod + "."):
            return mod.get("name", mod_path.rsplit("/", 1)[-1])
    # Fallback: use last segment
    return dotted_path.rsplit(".", 1)[-1] if "." in dotted_path else dotted_path


# Extension → language label for dependency ecosystem detection
_EXT_LANG_MAP = {
    ".py": "python", ".pyx": "python", ".pyi": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java", ".kt": "kotlin", ".scala": "scala",
    ".c": "c", ".h": "c", ".cpp": "c++", ".cc": "c++", ".hpp": "c++",
    ".rb": "ruby", ".php": "php", ".cs": "c#",
    ".ex": "elixir", ".exs": "elixir",
    ".swift": "swift", ".zig": "zig",
    ".html": "html", ".jinja2": "jinja2", ".j2": "jinja2",
    ".css": "css", ".scss": "scss", ".less": "less",
    ".yaml": "yaml", ".yml": "yaml", ".json": "json", ".toml": "toml",
    ".tf": "terraform", ".hcl": "hcl",
    ".sh": "shell", ".bash": "shell",
    ".sql": "sql", ".graphql": "graphql", ".gql": "graphql",
    ".md": "markdown", ".proto": "protobuf",
}


def _dominant_language(files_involved: list[str]) -> str:
    """Determine the dominant language/ecosystem from a list of file paths.

    Counts file extensions and returns the most common language label.
    Returns empty string if no files or no recognized extensions.
    """
    if not files_involved:
        return ""
    counts: dict[str, int] = {}
    for fp in files_involved:
        ext = Path(fp).suffix.lower()
        lang = _EXT_LANG_MAP.get(ext, "")
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    if not counts:
        return ""
    return max(counts, key=counts.get)



def _filter_to_scope(
    bundle: AuditDataBundle,
    scope: AuditScope,
) -> ScopedAuditData:
    """Slice full audit data to a specific module/path scope.

    Processes all 7 data sources:
        1. audit:l2:quality → file_scores, hotspots, subcategory averages
        2. audit:l2:risks → scoped findings only
        3. audit:l2:structure → deduped cross-deps, library usage
        4. audit:scores → project context + trend
        5. testing → test file matching
        6. git → scoped changes
        7. live FS → real file count, lines, mod dates
    """
    prefix = scope.source_prefix
    configured_modules = bundle.configured_modules

    # ═══════════════════════════════════════════════════════════════
    # Source 1: audit:l2:quality — file scores, hotspots
    # ═══════════════════════════════════════════════════════════════

    cached_file_count = 0
    hotspots: list[dict] = []
    subcategory_averages: dict[str, float] = {}
    worst_files: list[dict] = []
    scoped_scores: list[dict] = []
    health_score: float | None = None

    if bundle.quality:
        all_scores = bundle.quality.get("file_scores", [])
        scoped_scores = [
            fs for fs in all_scores
            if fs.get("file", "").startswith(prefix)
        ]
        cached_file_count = len(scoped_scores)

        if scoped_scores:
            # Average top-level score
            raw_scores = [fs["score"] for fs in scoped_scores if "score" in fs]
            health_score = round(
                sum(raw_scores) / len(raw_scores), 1,
            ) if raw_scores else None

            # Per-subcategory averages
            sub_accum: dict[str, list[float]] = {}
            for fs in scoped_scores:
                bd = fs.get("breakdown", {})
                for key, val in bd.items():
                    if isinstance(val, (int, float)):
                        sub_accum.setdefault(key, []).append(val)
            subcategory_averages = {
                k: round(sum(v) / len(v), 1)
                for k, v in sub_accum.items()
                if v
            }

            # Worst files (bottom 3 by score)
            sorted_scores = sorted(scoped_scores, key=lambda s: s.get("score", 10))
            for fs in sorted_scores[:3]:
                bd = fs.get("breakdown", {})
                # Find the weakest subcategory
                weakest_key = ""
                weakest_val = 11.0
                for k, v in bd.items():
                    if isinstance(v, (int, float)) and v < weakest_val:
                        weakest_key = k
                        weakest_val = v
                worst_files.append({
                    "file": fs.get("file", "").rsplit("/", 1)[-1],
                    "file_path": fs.get("file", ""),
                    "score": fs.get("score", 0),
                    "weakest": weakest_key,
                    "weakest_val": round(weakest_val, 1) if weakest_val < 11 else 0,
                })

        # Hotspots
        all_hotspots = bundle.quality.get("hotspots", [])
        hotspots = [
            h for h in all_hotspots
            if h.get("file", "").startswith(prefix)
        ]

    # ═══════════════════════════════════════════════════════════════
    # Source 2: audit:l2:risks — SCOPED findings only
    # ═══════════════════════════════════════════════════════════════

    findings: list[dict] = []
    project_wide_findings: list[dict] = []
    risk_summary = {"total": 0, "critical": 0, "high": 0, "medium": 0, "info": 0}
    is_module_root = scope.sub_path == ""

    if bundle.risks:
        all_findings = bundle.risks.get("findings", [])
        for f in all_findings:
            f_files = f.get("files", [])
            if not f_files:
                # Project-wide (no file refs)
                # At module root: include as project_wide_findings
                # At sub-module: skip (noise)
                if is_module_root:
                    project_wide_findings.append(f)
                continue
            has_match = any(
                ff.get("file", "").startswith(prefix)
                for ff in f_files
            )
            if has_match:
                findings.append(f)

        risk_summary["total"] = len(findings) + len(project_wide_findings)
        for f in findings + project_wide_findings:
            sev = f.get("severity", "info")
            risk_summary[sev] = risk_summary.get(sev, 0) + 1

    # ═══════════════════════════════════════════════════════════════
    # Source 3: audit:l2:structure — deps, library usage, module stats
    # ═══════════════════════════════════════════════════════════════

    exposure_ratio: float | None = None
    total_functions = 0
    total_classes = 0
    deps_outbound: list[dict] = []
    deps_inbound: list[dict] = []
    libraries: list[dict] = []

    if bundle.structure:
        # Module metadata — match by dotted prefix from source_prefix
        # e.g. source_prefix "src/core/services/audit" → dotted "src.core.services.audit"
        dotted_prefix = prefix.replace("/", ".")
        all_modules = bundle.structure.get("modules", [])

        # Find exact match first, then aggregate children
        for mod_entry in all_modules:
            mod_dotted = mod_entry.get("module", "")
            if mod_dotted == dotted_prefix:
                exposure_ratio = mod_entry.get("exposure_ratio")
                total_functions = mod_entry.get("total_functions", 0)
                total_classes = mod_entry.get("total_classes", 0)
                break
        else:
            # No exact match — aggregate all child sub-modules
            child_prefix = dotted_prefix + "."
            for mod_entry in all_modules:
                mod_dotted = mod_entry.get("module", "")
                if mod_dotted.startswith(child_prefix) or mod_dotted == dotted_prefix:
                    total_functions += mod_entry.get("total_functions", 0)
                    total_classes += mod_entry.get("total_classes", 0)
                    if exposure_ratio is None:
                        exposure_ratio = mod_entry.get("exposure_ratio")

        # ── Cross-module dependencies with DEDUP ──
        # Use dotted_prefix for sub-module-level matching, not just configured module
        outbound_map: dict[str, dict] = {}  # module_name → {strength, import_count}
        inbound_map: dict[str, dict] = {}

        all_cross = bundle.structure.get("cross_module_deps", [])
        for dep in all_cross:
            from_mod = dep.get("from_module", "")
            to_mod = dep.get("to_module", "")
            # Match against dotted_prefix for sub-module precision
            from_inside = (
                from_mod == dotted_prefix
                or from_mod.startswith(dotted_prefix + ".")
            )
            to_inside = (
                to_mod == dotted_prefix
                or to_mod.startswith(dotted_prefix + ".")
            )

            if from_inside and to_inside:
                continue  # internal dep — skip

            strength = dep.get("strength", "")
            import_count = dep.get("import_count", 0)
            files_involved = dep.get("files_involved", [])

            # Determine dominant language from files_involved extensions
            dep_lang = _dominant_language(files_involved)

            if from_inside:
                # Outbound: this scope → external module
                ext_name = _dotted_to_module_name(to_mod, configured_modules)
                existing = outbound_map.get(ext_name)
                if existing:
                    # Keep strongest strength, sum import counts
                    if _STRENGTH_ORDER.get(strength, 0) > _STRENGTH_ORDER.get(
                        existing["strength"], 0
                    ):
                        existing["strength"] = strength
                    existing["import_count"] += import_count
                else:
                    outbound_map[ext_name] = {
                        "module_name": ext_name,
                        "strength": strength,
                        "import_count": import_count,
                        "language": dep_lang,
                    }
            elif to_inside:
                # Inbound: external module → this scope
                ext_name = _dotted_to_module_name(from_mod, configured_modules)
                existing = inbound_map.get(ext_name)
                if existing:
                    if _STRENGTH_ORDER.get(strength, 0) > _STRENGTH_ORDER.get(
                        existing["strength"], 0
                    ):
                        existing["strength"] = strength
                    existing["import_count"] += import_count
                else:
                    inbound_map[ext_name] = {
                        "module_name": ext_name,
                        "strength": strength,
                        "import_count": import_count,
                        "language": dep_lang,
                    }

        # Sort: strongest first
        deps_outbound = sorted(
            outbound_map.values(),
            key=lambda d: _STRENGTH_ORDER.get(d["strength"], 0),
            reverse=True,
        )
        deps_inbound = sorted(
            inbound_map.values(),
            key=lambda d: _STRENGTH_ORDER.get(d["strength"], 0),
            reverse=True,
        )

        # ── Library Usage ──
        lib_usage = bundle.structure.get("library_usage", {})
        if isinstance(lib_usage, dict):
            for lib_name, lib_data in lib_usage.items():
                sites = lib_data.get("sites", []) if isinstance(lib_data, dict) else []
                scoped_sites = [
                    s for s in sites
                    if s.get("file", "").startswith(prefix)
                ]
                if scoped_sites:
                    files = sorted(set(
                        s.get("file", "").rsplit("/", 1)[-1]
                        for s in scoped_sites
                    ))
                    libraries.append({"name": lib_name, "files": files})
            libraries.sort(key=lambda x: x["name"])

    # ═══════════════════════════════════════════════════════════════
    # Source 4: audit:scores — project context + trend
    # ═══════════════════════════════════════════════════════════════

    project_quality_score: float | None = None
    project_complexity_score: float | None = None
    quality_trend: str | None = None

    if bundle.scores:
        q = bundle.scores.get("quality", {})
        c = bundle.scores.get("complexity", {})
        project_quality_score = q.get("score")
        project_complexity_score = c.get("score")
        trend = bundle.scores.get("trend", {})
        quality_trend = trend.get("quality_trend")

    # ═══════════════════════════════════════════════════════════════
    # Source 5: testing — test files matching scope
    # ═══════════════════════════════════════════════════════════════

    test_files: list[str] = []
    test_ratio: float | None = None
    test_framework: str | None = None

    if bundle.testing:
        stats = bundle.testing.get("stats", {})
        test_ratio = stats.get("test_ratio")
        all_test_paths = stats.get("test_file_paths", [])
        # Match test files by scope module name or subpath
        scope_terms = [scope.module]
        if scope.sub_path:
            # Also match sub_path segments (e.g. "vault" for services/vault)
            for part in scope.sub_path.split("/"):
                if part:
                    scope_terms.append(part)
        for tp in all_test_paths:
            tp_lower = tp.lower()
            if any(term.lower() in tp_lower for term in scope_terms):
                test_files.append(tp)

        frameworks = bundle.testing.get("frameworks", [])
        if frameworks:
            test_framework = frameworks[0].get("name")

    # ═══════════════════════════════════════════════════════════════
    # Source 6: git — scoped changes
    # ═══════════════════════════════════════════════════════════════

    git_modified: list[str] = []
    git_staged: list[str] = []
    git_untracked: list[str] = []

    if bundle.git:
        for f in bundle.git.get("modified", []):
            if f.startswith(prefix):
                git_modified.append(f.rsplit("/", 1)[-1])
        for f in bundle.git.get("staged", []):
            if f.startswith(prefix):
                git_staged.append(f.rsplit("/", 1)[-1])
        for f in bundle.git.get("untracked", []):
            if f.startswith(prefix):
                git_untracked.append(f.rsplit("/", 1)[-1])

    # ═══════════════════════════════════════════════════════════════
    # Source 7: live file system — real stats (multi-language)
    # ═══════════════════════════════════════════════════════════════

    live_file_count = 0
    live_total_lines = 0
    last_modified_date: str | None = None
    last_modified_file: str | None = None
    language_breakdown: list[dict] = []

    try:
        scope_path = Path(prefix)
        if scope_path.is_dir():
            # Use the ParserRegistry to identify all file types
            try:
                from src.core.services.audit.parsers import registry as _parser_reg
                analyses = _parser_reg.parse_tree(scope_path)
            except Exception:
                analyses = {}

            # Aggregate per-language stats
            lang_stats: dict[str, dict] = {}  # lang -> {files, lines, file_type}
            newest_mtime = 0.0
            newest_file = ""

            for rel_path, analysis in analyses.items():
                lang = analysis.language or "unknown"
                ftype = analysis.file_type or "source"
                lines = analysis.metrics.total_lines if analysis.metrics else 0

                if lang not in lang_stats:
                    lang_stats[lang] = {"files": 0, "lines": 0, "file_type": ftype}
                lang_stats[lang]["files"] += 1
                lang_stats[lang]["lines"] += lines
                live_file_count += 1
                live_total_lines += lines

                # Track newest modification
                try:
                    full_path = scope_path / rel_path if not Path(rel_path).is_absolute() else Path(rel_path)
                    mt = os.path.getmtime(full_path)
                    if mt > newest_mtime:
                        newest_mtime = mt
                        newest_file = Path(rel_path).name
                except OSError:
                    pass

            if newest_mtime > 0:
                dt = datetime.fromtimestamp(newest_mtime)
                last_modified_date = dt.strftime("%Y-%m-%d")
                last_modified_file = newest_file

            # Build sorted breakdown (by lines descending)
            language_breakdown = [
                {
                    "language": lang,
                    "file_type": stats["file_type"],
                    "files": stats["files"],
                    "lines": stats["lines"],
                }
                for lang, stats in sorted(
                    lang_stats.items(), key=lambda x: x[1]["lines"], reverse=True
                )
            ]
    except Exception:
        pass

    # Use live FS counts if available, otherwise fallback to cache
    file_count = live_file_count if live_file_count > 0 else cached_file_count
    total_lines = live_total_lines if live_total_lines > 0 else 0

    # ═══════════════════════════════════════════════════════════════
    # Module-root extras: sub-module health breakdown
    # ═══════════════════════════════════════════════════════════════
    sub_module_scores: list[dict] = []
    if is_module_root and bundle.quality:
        all_scores = bundle.quality.get("file_scores", [])
        # Group scores by sub-module directory under the module path
        sub_groups: dict[str, list[float]] = {}
        for fs in all_scores:
            fpath = fs.get("file", "")
            if not fpath.startswith(prefix + "/"):
                continue
            remainder = fpath[len(prefix) + 1:]  # e.g. "services/audit/scoring.py"
            parts = remainder.split("/")
            if len(parts) < 2:
                continue  # root-level file, not a sub-module
            # Use first directory as the sub-module key
            sub_key = parts[0]
            # If it's "services", go one level deeper for better granularity
            if sub_key == "services" and len(parts) >= 3:
                sub_key = f"services/{parts[1]}"
            sub_groups.setdefault(sub_key, []).append(fs.get("score", 0))

        for sub_name, scores in sorted(sub_groups.items()):
            if len(scores) < 2:
                continue  # skip single-file "sub-modules"
            avg = round(sum(scores) / len(scores), 1)
            worst = round(min(scores), 1)
            sub_module_scores.append({
                "name": sub_name,
                "score": avg,
                "files": len(scores),
                "worst": worst,
            })
        # Sort by score ascending (worst first)
        sub_module_scores.sort(key=lambda x: x["score"])

    return ScopedAuditData(
        scope=scope,
        source_label=bundle.source_label,
        computed_at=bundle.computed_at,
        health_score=health_score,
        file_count=file_count,
        total_lines=total_lines,
        total_functions=total_functions,
        total_classes=total_classes,
        cached_file_count=cached_file_count,
        subcategory_averages=subcategory_averages,
        worst_files=worst_files,
        exposure_ratio=exposure_ratio,
        project_quality_score=project_quality_score,
        project_complexity_score=project_complexity_score,
        quality_trend=quality_trend,
        hotspots=hotspots,
        hotspot_count=len(hotspots),
        findings=findings,
        risk_summary=risk_summary,
        deps_outbound=deps_outbound,
        deps_inbound=deps_inbound,
        libraries=libraries,
        test_files=test_files,
        test_ratio=test_ratio,
        test_framework=test_framework,
        git_modified=git_modified,
        git_staged=git_staged,
        git_untracked=git_untracked,
        last_modified_date=last_modified_date,
        last_modified_file=last_modified_file,
        language_breakdown=language_breakdown,
        is_module_root=is_module_root,
        project_wide_findings=project_wide_findings,
        sub_module_scores=sub_module_scores,
    )


# ═══════════════════════════════════════════════════════════════════
#  HTML Rendering
# ═══════════════════════════════════════════════════════════════════


# Severity emoji mapping
_SEV_EMOJI = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "info": "ℹ️",
}

# Hotspot severity → color
_SEVERITY_COLOR = {
    "critical": "#e57373",
    "warning": "#ffb74d",
    "info": "#90caf9",
}


def _render_no_data() -> str:
    """Render a placeholder when no audit data is available.

    Includes a "Start Scan" button that triggers POST /api/audit/scan
    and an SSE listener that auto-refreshes the preview on completion.
    """
    return (
        '<details class="audit-data-block audit-no-data" open>\n'
        '<summary>📊 <strong>Audit Data</strong> — '
        '<em>Not available</em></summary>\n'
        '<div style="padding:0.75rem;font-size:0.85rem;color:#888">\n'
        '<p>No audit data found. You can start a background scan — '
        'results will appear automatically when complete.</p>\n'
        '<button onclick="auditStartScan(this)" '
        'style="margin-top:0.4rem;padding:0.3rem 0.8rem;border:1px solid #555;'
        'border-radius:4px;background:#2a2d35;color:#ccc;cursor:pointer;'
        'font-size:0.8rem">'
        '🔍 Start Audit Scan</button>\n'
        '<span class="audit-scan-status" '
        'style="margin-left:0.5rem;font-size:0.8rem;display:none">'
        '</span>\n'
        '</div>\n'
        '</details>\n'
        '<script>\n'
        'function auditStartScan(btn) {\n'
        '  btn.disabled = true;\n'
        '  btn.textContent = "⏳ Starting scan...";\n'
        '  const status = btn.parentElement.querySelector(".audit-scan-status");\n'
        '  fetch("/api/audit/scan", {method:"POST", '
        'headers:{"Content-Type":"application/json"}, '
        'body:JSON.stringify({force:true})})\n'
        '    .then(r => r.json())\n'
        '    .then(d => {\n'
        '      btn.textContent = "⏳ Scan running...";\n'
        '      if (status) { status.style.display="inline"; '
        'status.textContent = "Task: " + d.task_id; }\n'
        '    })\n'
        '    .catch(e => {\n'
        '      btn.disabled = false;\n'
        '      btn.textContent = "❌ Failed — retry";\n'
        '    });\n'
        '}\n'
        '// Auto-refresh preview when scan completes\n'
        'document.addEventListener("audit-scan-complete", function _auditDone(e) {\n'
        '  document.removeEventListener("audit-scan-complete", _auditDone);\n'
        '  const btn = document.querySelector(".audit-no-data button");\n'
        '  if (btn) btn.textContent = "✅ Scan complete — refreshing...";\n'
        '  // Trigger preview refresh after a short delay\n'
        '  setTimeout(function() {\n'
        '    if (typeof previewRefresh === "function") previewRefresh();\n'
        '    else location.reload();\n'
        '  }, 500);\n'
        '});\n'
        '// Update progress in real-time\n'
        'document.addEventListener("audit-scan-progress", function(e) {\n'
        '  const btn = document.querySelector(".audit-no-data button");\n'
        '  if (btn && btn.disabled) {\n'
        '    const pct = Math.round((e.detail.progress || 0) * 100);\n'
        '    const phase = e.detail.phase || "";\n'
        '    btn.textContent = "⏳ " + phase + " (" + pct + "%)";\n'
        '  }\n'
        '});\n'
        '</script>\n'
    )


def _score_color(score: float) -> str:
    """Return a color for a health score (0-10)."""
    if score >= 8.0:
        return "#4caf50"
    if score >= 6.0:
        return "#8bc34a"
    if score >= 4.0:
        return "#ffeb3b"
    if score >= 2.0:
        return "#ff9800"
    return "#f44336"


def _score_gradient(score: float) -> str:
    """Return a CSS linear-gradient for the score bar."""
    if score >= 8.0:
        return "background:linear-gradient(90deg,#4caf50,#8bc34a)"
    if score >= 6.0:
        return "background:linear-gradient(90deg,#8bc34a,#c6e04f)"
    if score >= 4.0:
        return "background:linear-gradient(90deg,#ffeb3b,#ff9800)"
    if score >= 2.0:
        return "background:linear-gradient(90deg,#ff9800,#f44336)"
    return "background:linear-gradient(90deg,#f44336,#b71c1c)"


def _mini_bar(value: float, max_val: float = 10.0) -> str:
    """Render a mini text bar for subcategory scores."""
    filled = int((value / max_val) * 10)
    return "█" * filled + "░" * (10 - filled)


def _file_link(
    file_path: str,
    display_name: str,
    line: int = 0,
    render_mode: str = "preview",
    repo_url: str = "",
) -> str:
    """Generate a clickable file link.

    Preview mode (admin panel):
        ``<a href="/#content/docs/<path>@preview">`` — hash-based tab
        navigation inside the admin SPA.

    Build mode (Docusaurus):
        Always uses a full absolute URL (``http://…`` or ``https://…``)
        so Docusaurus treats it as external and does NOT prepend its
        baseUrl.

        - **CI build** (``CI`` env var set):  GitHub blob URL so links
          work on the deployed site (GitHub Pages).
        - **Local build** (no ``CI``):  full ``http://localhost:8000``
          URL pointing to the admin SPA content vault tab.
    """
    import html as _html
    import os as _os
    esc_display = _html.escape(display_name)

    if not file_path:
        return f'<code>{esc_display}</code>'

    # Content vault hash: /#content/docs/<path>@preview[:line]
    line_suffix = f":{line}" if line else ""
    vault_hash = f"#content/docs/{file_path}@preview{line_suffix}"

    if render_mode == "preview":
        # Admin panel SPA — hash navigation
        return (
            f'<a href="/{vault_hash}" '
            f'class="audit-file-link" '
            f'title="Open in Content Vault" '
            f'style="font-family:monospace;font-size:0.78rem;'
            f'color:#64b5f6;text-decoration:none;cursor:pointer"'
            f'>{esc_display}</a>'
        )
    else:
        # Build mode — full URL to avoid Docusaurus link rewriting
        is_ci = bool(_os.environ.get("CI") or _os.environ.get("GITHUB_ACTIONS"))

        if is_ci and repo_url:
            # Deployed site → GitHub source link
            line_anchor = f"#L{line}" if line else ""
            href = f"{repo_url.rstrip('/')}/blob/main/{file_path}{line_anchor}"
            return (
                f'<a href="{_html.escape(href)}" '
                f'target="_blank" rel="noopener" '
                f'class="audit-file-link" '
                f'title="View source on GitHub" '
                f'style="font-family:monospace;font-size:0.78rem;'
                f'color:#64b5f6;text-decoration:none;cursor:pointer"'
                f'>{esc_display}</a>'
            )
        else:
            # Local build → full URL to admin SPA content vault
            href = f"http://localhost:8000/{vault_hash}"
            return (
                f'<a href="{_html.escape(href)}" '
                f'class="audit-file-link" '
                f'title="Open in Content Vault" '
                f'style="font-family:monospace;font-size:0.78rem;'
                f'color:#64b5f6;text-decoration:none;cursor:pointer"'
                f'>{esc_display}</a>'
            )


def render_html(
    data: ScopedAuditData,
    render_mode: str = "preview",
    repo_url: str = "",
) -> str:
    """Convert scoped audit data to an HTML <details> block.

    Args:
        data: Scoped audit data to render.
        render_mode: "preview" (web admin) or "build" (Docusaurus).
            Controls how file links are generated.
        repo_url: GitHub repository URL (e.g. "https://github.com/org/repo").
            Used in build mode to link source files to GitHub.

    Renders 9 sections, each omitted if no scoped data exists:
        1. Summary line (collapsed header)
        2. Module Health (score + breakdown + worst files)
        3. Hotspots (grouped by severity)
        4. Risk Findings (scoped only)
        5. Dependencies (deduped, labeled)
        6. Library Usage
        7. Test Coverage
        8. Development Activity
        9. Narrative Insights (Phase 8.3 — computed observations)
    """
    scope = data.scope

    # ── Section 1: Summary line ──────────────────────────────────
    summary_parts = []
    if data.health_score is not None:
        summary_parts.append(f"Health: {data.health_score}/10")
    if data.hotspot_count > 0:
        n = data.hotspot_count
        summary_parts.append(f"{n} hotspot{'s' if n != 1 else ''}")
    if data.findings:
        n = len(data.findings)
        summary_parts.append(f"{n} finding{'s' if n != 1 else ''}")
    summary_parts.append(f"Source: {data.source_label}")
    summary_text = " · ".join(summary_parts)

    # ── Build sections ───────────────────────────────────────────
    sections: list[str] = []

    # ══════════════════════════════════════════════════════════════
    # Section 2: Module Health
    # ══════════════════════════════════════════════════════════════
    if data.health_score is not None or data.file_count > 0:
        stats_parts = []
        if data.file_count > 0:
            stats_parts.append(f"{data.file_count} files")
        if data.total_lines > 0:
            stats_parts.append(f"{data.total_lines:,} lines")
        if data.total_functions > 0:
            stats_parts.append(f"{data.total_functions} functions")
        if data.total_classes > 0:
            stats_parts.append(f"{data.total_classes} classes")
        stats_text = " · ".join(stats_parts)

        # Language summary pills (e.g., "22 Python · 12 Jinja2 · 3 JS")
        lang_pills = ""
        if data.language_breakdown:
            pill_style = (
                "display:inline-block;padding:0.1rem 0.4rem;margin:0.1rem;"
                "border-radius:8px;font-size:0.7rem;background:#2a2d35;"
                "color:#b0bec5"
            )
            pills = []
            for lb in data.language_breakdown[:6]:  # Top 6 languages
                lang = lb["language"].capitalize()
                count = lb["files"]
                pills.append(
                    f'<span style="{pill_style}">{count} {lang}</span>'
                )
            lang_pills = " ".join(pills)
            if len(data.language_breakdown) > 6:
                more = len(data.language_breakdown) - 6
                lang_pills += f' <span style="font-size:0.7rem;color:#666">+{more} more</span>'

        s = '<div style="margin-bottom:0.75rem">\n'
        s += "<strong>Module Health</strong>"
        if stats_text:
            s += (
                f' <span style="float:right;font-size:0.8rem;'
                f'color:#888">{stats_text}</span>'
            )
        s += "\n"

        # Language pills row
        if lang_pills:
            s += f'<div style="margin-top:0.3rem">{lang_pills}</div>\n'

        if data.health_score is not None:
            pct = int(data.health_score * 10)
            gradient = _score_gradient(data.health_score)
            s += (
                f'<div style="background:#333;border-radius:4px;'
                f'height:8px;margin-top:0.4rem;overflow:hidden">\n'
                f'  <div style="width:{pct}%;height:100%;'
                f'{gradient}"></div>\n'
                f"</div>\n"
                f'<span style="font-size:0.8rem">'
                f"{data.health_score} / 10</span>\n"
            )
            # Project comparison
            if data.project_quality_score is not None:
                delta = data.health_score - data.project_quality_score
                sign = "+" if delta > 0 else ""
                s += (
                    f'<span style="font-size:0.75rem;color:#888;'
                    f'margin-left:1rem">Project avg: '
                    f'{data.project_quality_score} '
                    f'({sign}{delta:.1f})</span>\n'
                )

        # Quality Breakdown (subcategory averages)
        if data.subcategory_averages:
            # Find weakest subcategory
            weakest = min(data.subcategory_averages, key=data.subcategory_averages.get)
            s += '<div style="margin-top:0.5rem;font-size:0.8rem">\n'
            s += '<strong style="font-size:0.85rem">Quality Breakdown</strong>\n'
            s += '<table style="width:100%;font-size:0.8rem;margin-top:0.25rem;'
            s += 'border-collapse:collapse">\n'
            for key, val in sorted(
                data.subcategory_averages.items(),
                key=lambda x: x[1],
            ):
                bar = _mini_bar(val)
                is_weak = key == weakest and val < 7.0
                style = ' style="color:#e57373"' if is_weak else ""
                weak_note = " ← weakest" if is_weak else ""
                display_key = key.replace("_", " ")
                s += (
                    f"<tr><td{style}>{display_key}</td>"
                    f'<td{style}><code>{bar}</code> {val}{weak_note}'
                    f"</td></tr>\n"
                )
            s += "</table>\n</div>\n"

        # Worst Files (bottom 3)
        if data.worst_files:
            s += '<div style="margin-top:0.5rem;font-size:0.8rem">\n'
            s += "<strong>Weakest Files</strong>\n"
            s += '<ul style="margin:0.25rem 0;padding-left:1.2rem">\n'
            for wf in data.worst_files:
                w_name = wf.get("weakest", "")
                w_val = wf.get("weakest_val", 0)
                reason = f" ({w_name}: {w_val})" if w_name else ""
                flink = _file_link(
                    wf.get("file_path", ""),
                    wf["file"],
                    render_mode=render_mode,
                    repo_url=repo_url,
                )
                s += f'<li>⚠ {flink} — {wf["score"]}/10{reason}</li>\n'
            s += "</ul>\n</div>\n"

        # Exposure ratio
        if data.exposure_ratio is not None:
            pct_exp = round(data.exposure_ratio * 100)
            s += (
                f'<div style="margin-top:0.3rem;font-size:0.75rem;color:#888">'
                f"Exposure ratio: {pct_exp}%</div>\n"
            )

        # Cache vs live diff note
        if (
            data.cached_file_count > 0
            and data.file_count != data.cached_file_count
        ):
            s += (
                f'<div style="margin-top:0.25rem;font-size:0.75rem;color:#e57373">'
                f"⚠ Live: {data.file_count} files — cache: "
                f"{data.cached_file_count} (re-scan recommended)</div>\n"
            )

        s += "</div>"
        sections.append(s)

    # ══════════════════════════════════════════════════════════════
    # Section 2b: File Composition (multi-language tree)
    # ══════════════════════════════════════════════════════════════
    if data.language_breakdown and len(data.language_breakdown) > 1:
        s = '<div style="margin-bottom:0.75rem">\n'
        s += "<strong>File Composition</strong>\n"
        s += '<div style="font-size:0.8rem;margin-top:0.3rem;'
        s += 'font-family:monospace;line-height:1.6">\n'

        _FILE_TYPE_LABELS = {
            "source": "sources",
            "template": "templates",
            "style": "styles",
            "config": "configs",
            "documentation": "docs",
            "data": "data files",
            "build": "build files",
            "schema": "schemas",
            "infrastructure": "infra",
            "script": "scripts",
        }

        total = len(data.language_breakdown)
        for i, lb in enumerate(data.language_breakdown):
            is_last = i == total - 1
            prefix_char = "└── " if is_last else "├── "
            lang_label = lb["language"].capitalize()
            ftype = _FILE_TYPE_LABELS.get(lb["file_type"], lb["file_type"])
            files = lb["files"]
            lines = lb["lines"]
            s += (
                f'<div style="color:#b0bec5">{prefix_char}'
                f'<span style="color:#81d4fa">{lang_label}</span> '
                f'{ftype}'
                f'<span style="float:right;color:#888">'
                f'{files} file{"s" if files != 1 else ""}'
                f' &nbsp; {lines:,} lines</span>'
                f'</div>\n'
            )

        s += "</div>\n</div>"
        sections.append(s)

    # ══════════════════════════════════════════════════════════════
    # Section 3: Hotspots (grouped by severity)
    # ══════════════════════════════════════════════════════════════
    if data.hotspots:
        s = '<div style="margin-bottom:0.75rem">\n'
        s += "<strong>Hotspots</strong>"
        s += (
            f' <span style="float:right;font-size:0.75rem;color:#888">'
            f"{data.hotspot_count} total</span>\n"
        )
        s += '<div style="margin-top:0.25rem;font-size:0.8rem">\n'

        # Group by severity
        by_severity: dict[str, list[dict]] = {}
        for h in data.hotspots:
            sev = h.get("severity", "warning")
            by_severity.setdefault(sev, []).append(h)

        severity_order = ["critical", "warning", "info"]
        for sev in severity_order:
            items = by_severity.get(sev, [])
            if not items:
                continue
            color = _SEVERITY_COLOR.get(sev, "#888")
            s += (
                f'<div style="color:{color};font-weight:600;'
                f'margin:0.25rem 0">{sev.capitalize()}</div>\n'
            )
            s += '<ul style="margin:0;padding-left:1.2rem">\n'
            limit = 99 if sev == "critical" else 5
            for h in items[:limit]:
                file_path = h.get("file", "")
                file_name = file_path.rsplit("/", 1)[-1]
                symbol = h.get("symbol", "")
                detail = h.get("detail", "")
                h_type = h.get("type", "unknown").replace("_", " ")
                lineno = h.get("lineno", 0)

                file_link = _file_link(
                    file_path, file_name,
                    line=lineno,
                    render_mode=render_mode,
                    repo_url=repo_url,
                )

                if symbol and detail:
                    s += (
                        f"<li>⚠ {file_link} → "
                        f"{symbol} — {detail} ({h_type})</li>\n"
                    )
                elif detail:
                    s += (
                        f"<li>⚠ {file_link} — "
                        f"{detail} ({h_type})</li>\n"
                    )
                else:
                    s += f"<li>⚠ {file_link} — {h_type}</li>\n"
            if len(items) > limit:
                s += f"<li><em>...and {len(items) - limit} more</em></li>\n"
            s += "</ul>\n"

        s += "</div>\n</div>"
        sections.append(s)

    # ══════════════════════════════════════════════════════════════
    # Section 4: Risk Findings (ONLY if scoped findings exist)
    # ══════════════════════════════════════════════════════════════
    if data.findings:
        s = '<div style="margin-bottom:0.75rem">\n'
        n = len(data.findings)
        s += f"<strong>Risk Findings</strong>"
        s += (
            f' <span style="float:right;font-size:0.75rem;color:#888">'
            f"{n} total</span>\n"
        )
        s += '<ul style="margin:0.25rem 0;padding-left:1.2rem;font-size:0.8rem">\n'
        for f in data.findings[:8]:
            sev = f.get("severity", "info")
            emoji = _SEV_EMOJI.get(sev, "ℹ️")
            title = f.get("title", "Unknown")
            # Show affected files if available
            f_files = f.get("files", [])
            file_names = ", ".join(
                ff.get("file", "").rsplit("/", 1)[-1]
                for ff in f_files[:3]
                if ff.get("file", "").startswith(data.scope.source_prefix)
            )
            detail = f" ({file_names})" if file_names else ""
            s += f"<li>{emoji} {sev.capitalize()}: {title}{detail}</li>\n"
        if n > 8:
            s += f"<li><em>...and {n - 8} more</em></li>\n"
        s += "</ul>\n</div>"
        sections.append(s)
    # ══════════════════════════════════════════════════════════════
    # Section 4b: Project-Wide Findings (module root only)
    # ══════════════════════════════════════════════════════════════
    if data.project_wide_findings:
        s = '<div style="margin-bottom:0.75rem">\n'
        n = len(data.project_wide_findings)
        s += f"<strong>Project-Wide Findings</strong>"
        s += (
            f' <span style="float:right;font-size:0.75rem;color:#888">'
            f"{n} finding{'s' if n != 1 else ''}</span>\n"
        )
        s += '<ul style="margin:0.25rem 0;padding-left:1.2rem;font-size:0.8rem">\n'
        for f in data.project_wide_findings:
            sev = f.get("severity", "info")
            emoji = _SEV_EMOJI.get(sev, "ℹ️")
            title = f.get("title", "Unknown")
            detail_text = f.get("detail", "")
            rec = f.get("recommendation", "")
            s += f"<li>{emoji} <strong>{sev.capitalize()}</strong>: {title}"
            if detail_text:
                s += f' <span style="color:#888">— {detail_text}</span>'
            s += "</li>\n"
            if rec:
                s += (
                    f'<li style="list-style:none;font-size:0.75rem;'
                    f'color:#90caf9;padding-left:0.5rem">'
                    f"💡 {rec}</li>\n"
                )
        s += "</ul>\n</div>"
        sections.append(s)

    # ══════════════════════════════════════════════════════════════
    # Section 4c: Sub-Module Health (module root only)
    # ══════════════════════════════════════════════════════════════
    if data.sub_module_scores:
        s = '<div style="margin-bottom:0.75rem">\n'
        s += "<strong>Sub-Module Health</strong>"
        s += (
            f' <span style="float:right;font-size:0.75rem;color:#888">'
            f"{len(data.sub_module_scores)} sub-modules</span>\n"
        )
        s += (
            '<table style="width:100%;font-size:0.78rem;margin-top:0.3rem;'
            'border-collapse:collapse;line-height:1.6">\n'
            '<tr style="color:#888;font-size:0.72rem;border-bottom:1px solid #333">'
            "<th style=\"text-align:left;padding:2px 6px\">Sub-module</th>"
            "<th style=\"text-align:center;padding:2px 6px\">Score</th>"
            "<th style=\"text-align:center;padding:2px 6px\">Files</th>"
            "<th style=\"text-align:center;padding:2px 6px\">Worst</th>"
            "<th style=\"text-align:left;padding:2px 6px\">Health</th>"
            "</tr>\n"
        )
        for sm in data.sub_module_scores[:20]:
            score = sm["score"]
            color = _score_color(score)
            bar_pct = int(score * 10)
            worst = sm["worst"]
            worst_color = _score_color(worst)
            s += (
                f"<tr>"
                f'<td style="padding:2px 6px;font-family:monospace">'
                f'{sm["name"]}</td>'
                f'<td style="text-align:center;padding:2px 6px;'
                f'color:{color};font-weight:600">{score}</td>'
                f'<td style="text-align:center;padding:2px 6px;'
                f'color:#888">{sm["files"]}</td>'
                f'<td style="text-align:center;padding:2px 6px;'
                f'color:{worst_color}">{worst}</td>'
                f'<td style="padding:2px 6px">'
                f'<div style="background:#333;border-radius:2px;'
                f'height:6px;width:80px;overflow:hidden">'
                f'<div style="width:{bar_pct}%;height:100%;'
                f'background:{color}"></div>'
                f'</div></td>'
                f"</tr>\n"
            )
        if len(data.sub_module_scores) > 20:
            s += (
                f'<tr><td colspan="5" style="padding:2px 6px;'
                f'font-size:0.72rem;color:#888">'
                f"...and {len(data.sub_module_scores) - 20} more</td></tr>\n"
            )
        s += "</table>\n</div>"
        sections.append(s)

    # ══════════════════════════════════════════════════════════════
    # Section 5: Dependencies (deduped, labeled with module names)
    # ══════════════════════════════════════════════════════════════
    if data.deps_outbound or data.deps_inbound:
        pill_style = (
            "display:inline-block;padding:0.15rem 0.5rem;margin:0.15rem;"
            "border-radius:12px;font-size:0.75rem;background:#2a2d35"
        )
        s = '<div style="margin-bottom:0.75rem">\n<strong>Dependencies</strong>\n'

        if data.deps_outbound:
            s += (
                '<div style="margin:0.25rem 0;font-size:0.75rem;color:#888">'
                "Outbound (this code imports from)</div>\n"
            )
            for dep in data.deps_outbound:
                mod = dep.get("module_name", "?")
                strength = dep.get("strength", "")
                count = dep.get("import_count", 0)
                lang = dep.get("language", "")
                label = f"→ {mod}"
                detail_parts = []
                if lang:
                    detail_parts.append(lang.capitalize())
                if strength:
                    detail_parts.append(strength)
                if count > 0:
                    detail_parts.append(str(count))
                if detail_parts:
                    label += f" ({' · '.join(detail_parts)})"
                s += f'<span style="{pill_style}">{label}</span>\n'

        if data.deps_inbound:
            s += (
                '<div style="margin:0.25rem 0;font-size:0.75rem;color:#888">'
                "Inbound (other code imports this)</div>\n"
            )
            for dep in data.deps_inbound:
                mod = dep.get("module_name", "?")
                strength = dep.get("strength", "")
                count = dep.get("import_count", 0)
                lang = dep.get("language", "")
                label = f"← {mod}"
                detail_parts = []
                if lang:
                    detail_parts.append(lang.capitalize())
                if strength:
                    detail_parts.append(strength)
                if count > 0:
                    detail_parts.append(str(count))
                if detail_parts:
                    label += f" ({' · '.join(detail_parts)})"
                s += f'<span style="{pill_style}">{label}</span>\n'

        s += "</div>"
        sections.append(s)

    # ══════════════════════════════════════════════════════════════
    # Section 6: Library Usage (third-party libs used in scope)
    # ══════════════════════════════════════════════════════════════
    if data.libraries:
        s = '<div style="margin-bottom:0.75rem">\n'
        s += "<strong>Third-Party Libraries</strong>\n"
        s += '<ul style="margin:0.25rem 0;padding-left:1.2rem;font-size:0.8rem">\n'
        for lib in data.libraries:
            files_str = ", ".join(lib["files"])
            s += f'<li><code>{lib["name"]}</code> — {files_str}</li>\n'
        s += "</ul>\n</div>"
        sections.append(s)

    # ══════════════════════════════════════════════════════════════
    # Section 7: Test Coverage
    # ══════════════════════════════════════════════════════════════
    # Always show — "no tests" is important information
    s = '<div style="margin-bottom:0.75rem">\n'
    s += "<strong>Test Coverage</strong>\n"
    s += '<div style="font-size:0.8rem;margin-top:0.25rem">\n'
    if data.test_files:
        test_names = [tp.rsplit("/", 1)[-1] for tp in data.test_files[:5]]
        s += "Test files: " + ", ".join(
            f"<code>{n}</code>" for n in test_names
        )
        if len(data.test_files) > 5:
            s += f" <em>...and {len(data.test_files) - 5} more</em>"
        s += "\n"
    else:
        s += "⚠ No test files found for this scope\n"
    extra = []
    if data.test_ratio is not None:
        extra.append(f"Project test ratio: {data.test_ratio}")
    if data.test_framework:
        extra.append(f"Framework: {data.test_framework}")
    if extra:
        s += (
            f'<br><span style="color:#888">'
            f'{" · ".join(extra)}</span>\n'
        )
    s += "</div>\n</div>"
    sections.append(s)

    # ══════════════════════════════════════════════════════════════
    # Section 8: Development Activity
    # ══════════════════════════════════════════════════════════════
    has_git = data.git_modified or data.git_staged or data.git_untracked
    has_mtime = data.last_modified_date is not None
    if has_git or has_mtime:
        s = '<div style="margin-bottom:0.75rem">\n'
        s += "<strong>Development Activity</strong>\n"
        s += '<div style="font-size:0.8rem;margin-top:0.25rem">\n'
        git_parts = []
        if data.git_modified:
            names = ", ".join(data.git_modified[:5])
            extra_n = max(0, len(data.git_modified) - 5)
            label = f"Modified: {names}"
            if extra_n:
                label += f" +{extra_n}"
            git_parts.append(label)
        if data.git_staged:
            names = ", ".join(data.git_staged[:3])
            git_parts.append(f"Staged: {names}")
        if data.git_untracked:
            names = ", ".join(data.git_untracked[:3])
            git_parts.append(f"Untracked: {names}")
        if git_parts:
            s += "<br>".join(git_parts) + "\n"
        if has_mtime:
            file_note = f" ({data.last_modified_file})" if data.last_modified_file else ""
            s += f"Last modified: {data.last_modified_date}{file_note}\n"
        s += "</div>\n</div>"
        sections.append(s)

    # ══════════════════════════════════════════════════════════════
    # Assemble <details> block
    # ══════════════════════════════════════════════════════════════
    if not sections:
        return (
            '<details class="audit-data-block">\n'
            f"<summary>📊 <strong>Audit Data</strong> — "
            f"No findings for <code>{scope.source_prefix}</code> "
            f"· Source: {data.source_label}</summary>\n"
            '<div style="padding:0.75rem;font-size:0.85rem;color:#888">\n'
            f"No audit data matches the scope <code>{scope.source_prefix}</code>. "
            "This module may not have been included in the latest audit scan.\n"
            "</div>\n"
            "</details>\n"
        )

    # ══════════════════════════════════════════════════════════════
    # Section 9: Narrative Observations (Phase 8.3)
    # ══════════════════════════════════════════════════════════════
    try:
        from src.core.services.audit.narrative import (
            generate_observations,
            render_observations_html,
            render_recommendations_html,
        )
        obs_data = {
            "health_score": data.health_score,
            "hotspots": data.hotspots,
            "deps_outbound": data.deps_outbound,
            "deps_inbound": data.deps_inbound,
            "file_count": data.file_count,
            "total_lines": data.total_lines,
            "language_breakdown": data.language_breakdown,
            "subcategory_averages": data.subcategory_averages,
            "worst_files": data.worst_files,
            "findings": data.findings,
            "matched_tests": data.test_files,
        }
        observations = generate_observations(obs_data)
        obs_html = render_observations_html(observations)
        if obs_html:
            # Insert as the first section (right after the header)
            sections.insert(0, obs_html)
        # Recommendations go at the end (Phase 8.5)
        recs_html = render_recommendations_html(obs_data)
        if recs_html:
            sections.append(recs_html)
    except Exception:
        pass  # Narrative generation must never break the card

    inner = "\n\n".join(sections)

    computed_note = ""
    if data.computed_at:
        computed_note = (
            f'\n<div style="margin-top:0.5rem;font-size:0.75rem;color:#666;'
            f'border-top:1px solid #333;padding-top:0.4rem">'
            f"Last computed: {data.computed_at}"
            f"</div>"
        )

    html = (
        '<details class="audit-data-block">\n'
        f"<summary>📊 <strong>Audit Data</strong> — {summary_text}</summary>\n"
        f'\n<div style="padding:0.75rem;font-size:0.85rem;line-height:1.5">\n\n'
        f"{inner}"
        f"{computed_note}\n\n"
        f"</div>\n"
        f"</details>\n"
    )
    return html


# ═══════════════════════════════════════════════════════════════════
#  Public API — Preview (in-process)
# ═══════════════════════════════════════════════════════════════════


def resolve_audit_directives(
    content: str,
    file_path: str,
    project_root: Path,
) -> str:
    """Replace :::audit-data blocks with rendered HTML.

    Used by the admin preview endpoint. Handles everything in-process:
    parse → scope → load → filter → render → replace.

    Args:
        content: Raw markdown file content.
        file_path: Relative path to the file, e.g. "src/ui/cli/audit/README.md".
        project_root: Project root directory.

    Returns:
        Markdown content with :::audit-data blocks replaced by HTML.
    """
    directives = _parse_directives(content)
    if not directives:
        return content

    # Process in reverse order to preserve character offsets
    for directive in reversed(directives):
        # ── Resolve scope ────────────────────────────────────────
        if directive.scope:
            scope = _resolve_scope_from_explicit(directive.scope, project_root)
        else:
            scope = _resolve_scope(file_path, project_root)

        if scope is None:
            # Can't determine scope — render a warning
            replacement = (
                '<details class="audit-data-block">\n'
                "<summary>📊 <strong>Audit Data</strong> — "
                "<em>Could not determine scope</em></summary>\n"
                '<div style="padding:0.75rem;font-size:0.85rem;color:#888">\n'
                f"Unable to resolve scope for <code>{file_path}</code>. "
                "Ensure the file is inside a configured module, or specify "
                'an explicit scope: <code>:::audit-data scope="module/path"</code>\n'
                "</div>\n"
                "</details>\n"
            )
            content = content[:directive.start] + replacement + content[directive.end:]
            continue

        # ── Load and filter ──────────────────────────────────────
        bundle = _load_audit_data(project_root, directive.source)

        if bundle.source_label == "N/A":
            replacement = _render_no_data()
            content = content[:directive.start] + replacement + content[directive.end:]
            continue

        filtered = _filter_to_scope(bundle, scope)
        replacement = render_html(filtered)
        content = content[:directive.start] + replacement + content[directive.end:]

    return content


def auto_inject_directive(
    content: str,
    file_path: str,
    project_root: Path,
) -> str:
    """Auto-inject :::audit-data directive text into module markdown files.

    Inserts the directive text after the first heading so it appears
    at the top of the document. In raw/source mode the user sees the
    directive syntax; in preview mode a separate resolve step
    converts it to rendered HTML.

    If the file is not inside a module, the content is returned unchanged.

    Args:
        content: Raw markdown file content.
        file_path: Relative path to the file.
        project_root: Project root directory.

    Returns:
        Markdown content with :::audit-data directive injected (or unchanged).
    """
    # Don't double-inject
    if ":::audit-data" in content:
        return content

    scope = _resolve_scope(file_path, project_root)
    if scope is None:
        return content

    directive_block = "\n:::audit-data\n:::\n"

    # Insert after the first heading
    heading_match = re.search(r"^#\s+.+$", content, re.MULTILINE)
    if heading_match:
        insert_pos = heading_match.end()
        return content[:insert_pos] + "\n" + directive_block + content[insert_pos:]

    # No heading — prepend
    return directive_block + "\n" + content


# ═══════════════════════════════════════════════════════════════════
#  Public API — Build (pre-compute for remark plugin)
# ═══════════════════════════════════════════════════════════════════


def precompute_audit_data(
    docs_dir: Path,
    project_root: Path,
    modules: list[dict],
    smart_folders: list[dict],
    repo_url: str = "",
) -> dict[str, dict]:
    """Pre-compute scoped audit data for files containing :::audit-data.

    Scans all .md files under docs_dir. For each file with the directive,
    resolves scope, loads audit data, filters, and stores the result.

    Returns:
        Map of { "relative/doc/path.md": { ...serializable audit data... } }
        to be written as _audit_data.json for the remark plugin.
    """
    audit_map: dict[str, dict] = {}

    for md_file in sorted(docs_dir.rglob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        if ":::audit-data" not in content:
            continue

        directives = _parse_directives(content)
        if not directives:
            continue

        rel = str(md_file.relative_to(docs_dir))

        # Use the first directive's source preference
        # (multiple directives per file is unusual for build)
        directive = directives[0]
        source = directive.source

        # ── Resolve scope from the staged doc path ───────────────
        # In the staged docs tree, the first path component is the
        # module name (e.g. "cli/audit/index.md" → module="cli")
        if directive.scope:
            scope = _resolve_scope_from_explicit(directive.scope, project_root)
        else:
            # Staged path mapping: the file is at docs_dir/<module>/<sub_path>/file.md
            # We reconstruct the source path from the module metadata
            parts = rel.split("/")
            if parts:
                candidate_module = parts[0]
                # Find the module definition
                mod = None
                for m in modules:
                    if m.get("name") == candidate_module:
                        mod = m
                        break
                if mod:
                    mod_path = mod.get("path", candidate_module).rstrip("/")
                    sub_parts = parts[1:]
                    if sub_parts and "." in sub_parts[-1]:
                        sub_parts = sub_parts[:-1]
                    sub_path = "/".join(sub_parts)
                    source_prefix = mod_path
                    if sub_path:
                        source_prefix = f"{mod_path}/{sub_path}"

                    scope = AuditScope(
                        module=candidate_module,
                        sub_path=sub_path,
                        source_prefix=source_prefix,
                        module_path=mod_path,
                    )
                else:
                    scope = None
            else:
                scope = None

        if scope is None:
            audit_map[rel] = {"error": "Could not determine scope"}
            continue

        # ── Load and filter ──────────────────────────────────────
        bundle = _load_audit_data(project_root, source)
        if bundle.source_label == "N/A":
            audit_map[rel] = {"error": "No audit data available"}
            continue

        filtered = _filter_to_scope(bundle, scope)

        # Serialize to a plain dict for JSON
        audit_map[rel] = {
            "scope": {
                "module": scope.module,
                "sub_path": scope.sub_path,
                "source_prefix": scope.source_prefix,
            },
            "source_label": filtered.source_label,
            "computed_at": filtered.computed_at,
            "health_score": filtered.health_score,
            "file_count": filtered.file_count,
            "total_lines": filtered.total_lines,
            "total_functions": filtered.total_functions,
            "total_classes": filtered.total_classes,
            "cached_file_count": filtered.cached_file_count,
            "subcategory_averages": filtered.subcategory_averages,
            "worst_files": filtered.worst_files,
            "exposure_ratio": filtered.exposure_ratio,
            "project_quality_score": filtered.project_quality_score,
            "project_complexity_score": filtered.project_complexity_score,
            "quality_trend": filtered.quality_trend,
            "hotspots": filtered.hotspots,
            "hotspot_count": filtered.hotspot_count,
            "findings": filtered.findings,
            "risk_summary": filtered.risk_summary,
            "deps_outbound": filtered.deps_outbound,
            "deps_inbound": filtered.deps_inbound,
            "libraries": filtered.libraries,
            "test_files": filtered.test_files,
            "test_ratio": filtered.test_ratio,
            "test_framework": filtered.test_framework,
            "git_modified": filtered.git_modified,
            "git_staged": filtered.git_staged,
            "git_untracked": filtered.git_untracked,
            "last_modified_date": filtered.last_modified_date,
            "last_modified_file": filtered.last_modified_file,
            # Pre-rendered HTML (the remark plugin can use this directly)
            "html": render_html(filtered, render_mode="build", repo_url=repo_url),
        }

    return audit_map
