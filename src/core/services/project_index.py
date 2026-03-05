"""
Passive Project Index — background-built, disk-cached project file/symbol index.

Provides instant file lookups, symbol resolution, and pre-computed peek
results. Built once at server startup (or loaded from disk cache), refreshed
periodically in a background daemon thread.

Design decisions
────────────────
1. **Disk cache** (``.state/project_index.json``): survives server restarts.
   Load takes ~100ms vs ~20s to rebuild from scratch.
2. **Load stale → rebuild behind**: even if the disk cache is outdated, load
   it immediately and rebuild in background. User gets fast first response.
3. **Phased build**: file index (~300ms) before symbols (~20s) before peek
   cache (~5s). Each phase unlocks a level of capability.
4. **Daemon thread**: same pattern as ``staleness_watcher`` — dies with process.
5. **Graceful fallback**: if index not ready, callers fall back to on-demand I/O.
6. **Thread safety**: index data is replaced atomically (dict swap). Reads are
   always safe without locks.

Cache stale detection
─────────────────────
Uses ``mtime_sig``: the max mtime across a set of sentinel paths (``src/``,
``docs/``, ``pyproject.toml``, ``project.yml``). If current mtime > cached
mtime, the cache is stale and a background rebuild is triggered.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────

_CACHE_FILE = ".state/project_index.json"
_CACHE_VERSION = 1

# Sentinel paths for stale detection (mtime comparison).
# If any of these change, the index is stale.
_SENTINEL_PATHS: list[str] = [
    "src/",
    "docs/",
    "pyproject.toml",
    "project.yml",
]

# Directories to skip during rglob walks.
_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", ".backup", ".state", ".agent", ".venv", "venv",
    "node_modules", "__pycache__", "build", "dist",
    ".tox", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    ".next", ".nuxt", "site-packages", "_build",
    ".docusaurus",
})

# Refresh interval for the background watcher.
_REFRESH_INTERVAL_S = 60.0


# ── SymbolEntry (duplicated from peek to avoid circular import) ─

@dataclass
class IndexSymbolEntry:
    """A symbol location in the project (for serialization)."""
    name: str
    file: str
    line: int
    kind: str


# ── Index data class ────────────────────────────────────────────

@dataclass
class ProjectIndex:
    """In-memory project index — all data fields."""

    # File index: filename → list of relative paths
    file_map: dict[str, list[str]] = field(default_factory=dict)

    # Directory index: dirname → list of relative paths
    dir_map: dict[str, list[str]] = field(default_factory=dict)

    # All known relative paths (for instant existence check)
    all_paths: set[str] = field(default_factory=set)

    # Symbol index: symbol_name → list of entries
    symbol_map: dict[str, list[IndexSymbolEntry]] = field(default_factory=dict)

    # Pre-computed peek results: doc_path → { "resolved": [...], "unresolved": [...] }
    peek_cache: dict[str, dict[str, list[dict]]] = field(default_factory=dict)

    # State flags
    ready: bool = False            # True once file_map is usable
    symbols_ready: bool = False    # True once symbol_map is built
    peek_cached: bool = False      # True once peek_cache is populated
    building: bool = False         # True while background build runs
    last_built: float = 0.0        # Timestamp of last completed build
    build_time_ms: int = 0         # Duration of the last build
    mtime_sig: float = 0.0         # Max mtime at build time

    # Counts for observability
    file_count: int = 0
    dir_count: int = 0
    symbol_count: int = 0
    peek_page_count: int = 0


# ── Singleton ───────────────────────────────────────────────────

_index: ProjectIndex = ProjectIndex()
_project_root: Path | None = None
_thread: threading.Thread | None = None


def get_index() -> ProjectIndex:
    """Return the singleton project index instance."""
    return _index


# ── Stale detection ─────────────────────────────────────────────

def _mtime_signature(project_root: Path) -> float:
    """Compute the max mtime across sentinel paths.

    Walks sentinel directories (depth-limited to 3 levels) and checks
    file mtimes. Returns 0.0 if no sentinel paths exist.
    """
    max_mt: float = 0.0
    for rel in _SENTINEL_PATHS:
        p = project_root / rel
        try:
            if rel.endswith("/") and p.is_dir():
                max_mt = max(max_mt, _walk_max_mtime(p, max_depth=3))
            elif p.exists():
                max_mt = max(max_mt, os.stat(p).st_mtime)
        except (FileNotFoundError, OSError):
            pass
    return max_mt


def _walk_max_mtime(directory: Path, max_depth: int = 3) -> float:
    """Walk a directory tree and return the max file mtime."""
    max_mt: float = 0.0
    base = str(directory)

    for root, dirs, files in os.walk(directory):
        depth = root[len(base):].count(os.sep)
        if depth >= max_depth:
            dirs.clear()
            continue

        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]

        for fname in files:
            if fname.startswith("."):
                continue
            try:
                mt = os.stat(os.path.join(root, fname)).st_mtime
                if mt > max_mt:
                    max_mt = mt
            except (FileNotFoundError, OSError):
                pass

    return max_mt


# ── Disk cache I/O ──────────────────────────────────────────────

def _cache_path(project_root: Path) -> Path:
    return project_root / _CACHE_FILE


def _save_to_disk(project_root: Path, index: ProjectIndex) -> None:
    """Write the full index to disk as JSON."""
    path = _cache_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Serialize symbol_map entries as dicts
    sym_serial: dict[str, list[dict]] = {}
    for name, entries in index.symbol_map.items():
        sym_serial[name] = [
            {"name": e.name, "file": e.file, "line": e.line, "kind": e.kind}
            for e in entries
        ]

    payload: dict[str, Any] = {
        "version": _CACHE_VERSION,
        "project_root": str(project_root.resolve()),
        "built_at": index.last_built,
        "mtime_sig": index.mtime_sig,
        "build_ms": index.build_time_ms,
        "file_map": index.file_map,
        "dir_map": index.dir_map,
        "all_paths": sorted(index.all_paths),
        "symbol_map": sym_serial,
        "peek_cache": index.peek_cache,
    }

    try:
        path.write_text(json.dumps(payload), encoding="utf-8")
        size_kb = path.stat().st_size / 1024
        logger.info(
            "[ProjectIndex] Saved disk cache (%.0fKB, %d files, %d symbols, %d peek pages)",
            size_kb, index.file_count, index.symbol_count, index.peek_page_count,
        )
    except OSError as e:
        logger.warning("[ProjectIndex] Failed to save disk cache: %s", e)


def _load_from_disk(project_root: Path) -> ProjectIndex | None:
    """Load index from disk cache. Returns None if invalid/missing."""
    path = _cache_path(project_root)
    if not path.exists():
        return None

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("[ProjectIndex] Disk cache unreadable: %s", e)
        return None

    # Version check
    if raw.get("version") != _CACHE_VERSION:
        logger.info("[ProjectIndex] Disk cache version mismatch, discarding")
        return None

    # Project root check
    if raw.get("project_root") != str(project_root.resolve()):
        logger.info("[ProjectIndex] Disk cache from different project, discarding")
        return None

    # Deserialize
    idx = ProjectIndex()
    idx.file_map = raw.get("file_map", {})
    idx.dir_map = raw.get("dir_map", {})
    idx.all_paths = set(raw.get("all_paths", []))
    idx.peek_cache = raw.get("peek_cache", {})
    idx.mtime_sig = raw.get("mtime_sig", 0.0)
    idx.last_built = raw.get("built_at", 0.0)
    idx.build_time_ms = raw.get("build_ms", 0)

    # Deserialize symbol_map
    sym_raw = raw.get("symbol_map", {})
    for name, entries in sym_raw.items():
        idx.symbol_map[name] = [
            IndexSymbolEntry(
                name=e["name"], file=e["file"],
                line=e["line"], kind=e["kind"],
            )
            for e in entries
        ]

    # Set counts
    idx.file_count = sum(len(v) for v in idx.file_map.values())
    idx.dir_count = sum(len(v) for v in idx.dir_map.values())
    idx.symbol_count = len(idx.symbol_map)
    idx.peek_page_count = len(idx.peek_cache)

    # Mark as ready
    idx.ready = True
    idx.symbols_ready = bool(idx.symbol_map)
    idx.peek_cached = bool(idx.peek_cache)

    logger.info(
        "[ProjectIndex] Loaded disk cache (%.1fs old, %d files, %d symbols, %d peek pages)",
        time.time() - idx.last_built,
        idx.file_count, idx.symbol_count, idx.peek_page_count,
    )

    return idx


# ── Build phases ────────────────────────────────────────────────

def _build_file_index(project_root: Path, index: ProjectIndex) -> None:
    """Phase 1: rglob the project tree → file_map + dir_map + all_paths."""
    t0 = time.perf_counter()

    file_map: dict[str, list[str]] = {}
    dir_map: dict[str, list[str]] = {}
    all_paths: set[str] = set()
    file_count = 0
    dir_count = 0

    for root, dirs, files in os.walk(project_root):
        # Skip hidden/build directories
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]

        for d in dirs:
            full = os.path.join(root, d)
            try:
                rel = os.path.relpath(full, project_root)
            except ValueError:
                continue
            all_paths.add(rel)
            dir_map.setdefault(d, []).append(rel)
            # Also index with trailing slash
            dir_map.setdefault(d + "/", []).append(rel)
            dir_count += 1

        for f in files:
            if f.startswith("."):
                continue
            full = os.path.join(root, f)
            try:
                rel = os.path.relpath(full, project_root)
            except ValueError:
                continue
            all_paths.add(rel)
            file_map.setdefault(f, []).append(rel)
            file_count += 1

    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    index.file_map = file_map
    index.dir_map = dir_map
    index.all_paths = all_paths
    index.file_count = file_count
    index.dir_count = dir_count
    index.ready = True

    logger.info(
        "[ProjectIndex] File index built: %d files, %d dirs in %dms",
        file_count, dir_count, elapsed_ms,
    )


def _build_symbol_index(project_root: Path, index: ProjectIndex) -> None:
    """Phase 2: parse all .py files → symbol_map."""
    t0 = time.perf_counter()

    try:
        from src.core.services.audit.parsers import registry
    except ImportError:
        logger.warning("[ProjectIndex] AST parser not available, skipping symbols")
        index.symbols_ready = True
        return

    sym_map: dict[str, list[IndexSymbolEntry]] = {}

    try:
        analyses = registry.parse_tree(project_root)
    except Exception as e:
        logger.warning("[ProjectIndex] Symbol parse failed: %s", e)
        index.symbols_ready = True
        return

    for rel_path, analysis in analyses.items():
        for sym in analysis.symbols:
            entry = IndexSymbolEntry(
                name=sym.name,
                file=rel_path,
                line=sym.lineno,
                kind=sym.kind,
            )
            sym_map.setdefault(sym.name, []).append(entry)

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    index.symbol_map = sym_map
    index.symbol_count = len(sym_map)
    index.symbols_ready = True

    logger.info(
        "[ProjectIndex] Symbol index built: %d unique symbols in %dms",
        len(sym_map), elapsed_ms,
    )


def _build_peek_cache(project_root: Path, index: ProjectIndex) -> None:
    """Phase 3: pre-compute peek results for all .md files."""
    t0 = time.perf_counter()

    from src.core.services.peek import (
        scan_and_resolve_all,
        build_symbol_index,
        SymbolEntry,
    )

    # Convert our IndexSymbolEntry map → peek's SymbolEntry map
    sym_idx: dict[str, list[SymbolEntry]] = {}
    for name, entries in index.symbol_map.items():
        sym_idx[name] = [
            SymbolEntry(name=e.name, file=e.file, line=e.line, kind=e.kind)
            for e in entries
        ]

    peek_cache: dict[str, dict[str, list[dict]]] = {}
    page_count = 0

    # Walk all .md files in the project
    for rel in sorted(index.all_paths):
        if not rel.endswith(".md"):
            continue

        md_path = project_root / rel
        if not md_path.is_file():
            continue

        try:
            content = md_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        if not content.strip():
            continue

        try:
            resolved, unresolved, _pending = scan_and_resolve_all(
                content, rel, project_root, sym_idx,
            )
        except Exception as e:
            logger.debug("[ProjectIndex] Peek failed for %s: %s", rel, e)
            continue

        entry: dict[str, list[dict]] = {}
        if resolved:
            entry["resolved"] = [
                {
                    "text": r.text,
                    "type": r.type,
                    "resolved_path": r.resolved_path,
                    "line_number": r.line_number,
                    "is_directory": r.is_directory,
                }
                for r in resolved
            ]
        if unresolved:
            entry["unresolved"] = [
                {
                    "text": u.text,
                    "type": u.type,
                }
                for u in unresolved
            ]

        if entry:
            peek_cache[rel] = entry
            page_count += 1

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    index.peek_cache = peek_cache
    index.peek_page_count = page_count
    index.peek_cached = True

    logger.info(
        "[ProjectIndex] Peek cache built: %d pages in %dms",
        page_count, elapsed_ms,
    )


# ── Background thread ───────────────────────────────────────────

def _build_loop(project_root: Path) -> None:
    """Background thread: build index phases, then watch for staleness."""
    global _index

    idx = _index

    # ── Phase 0: Try loading disk cache ─────────────────────
    disk_idx = _load_from_disk(project_root)
    current_mtime = _mtime_signature(project_root)

    if disk_idx is not None:
        # Use the disk cache immediately
        idx.file_map = disk_idx.file_map
        idx.dir_map = disk_idx.dir_map
        idx.all_paths = disk_idx.all_paths
        idx.symbol_map = disk_idx.symbol_map
        idx.peek_cache = disk_idx.peek_cache
        idx.file_count = disk_idx.file_count
        idx.dir_count = disk_idx.dir_count
        idx.symbol_count = disk_idx.symbol_count
        idx.peek_page_count = disk_idx.peek_page_count
        idx.mtime_sig = disk_idx.mtime_sig
        idx.last_built = disk_idx.last_built
        idx.build_time_ms = disk_idx.build_time_ms
        idx.ready = True
        idx.symbols_ready = disk_idx.symbols_ready
        idx.peek_cached = disk_idx.peek_cached

        _publish_event("index:loaded", data={
            "source": "disk",
            "age_s": round(time.time() - disk_idx.last_built),
            "files": idx.file_count,
            "symbols": idx.symbol_count,
            "peek_pages": idx.peek_page_count,
        })

        # Check if stale
        if current_mtime <= disk_idx.mtime_sig:
            logger.info("[ProjectIndex] Disk cache is fresh, skipping rebuild")
            # Skip straight to refresh loop
            _refresh_loop(project_root)
            return

        logger.info("[ProjectIndex] Disk cache is stale, rebuilding in background")

    # ── Full build ──────────────────────────────────────────
    idx.building = True
    t0 = time.perf_counter()

    _publish_event("index:building", data={"phase": "file_index"})

    # Phase 1: file index
    _build_file_index(project_root, idx)

    _publish_event("index:building", data={"phase": "symbols"})

    # Phase 2: symbol index
    _build_symbol_index(project_root, idx)

    _publish_event("index:building", data={"phase": "peek_cache"})

    # Phase 3: peek cache
    _build_peek_cache(project_root, idx)

    # Finalize
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    idx.mtime_sig = current_mtime
    idx.last_built = time.time()
    idx.build_time_ms = elapsed_ms
    idx.building = False

    logger.info(
        "[ProjectIndex] Full build complete in %dms "
        "(%d files, %d symbols, %d peek pages)",
        elapsed_ms, idx.file_count, idx.symbol_count, idx.peek_page_count,
    )

    _publish_event("index:ready", data={
        "build_ms": elapsed_ms,
        "files": idx.file_count,
        "symbols": idx.symbol_count,
        "peek_pages": idx.peek_page_count,
    })

    # Save to disk
    _save_to_disk(project_root, idx)

    # Enter refresh loop
    _refresh_loop(project_root)


def _refresh_loop(project_root: Path) -> None:
    """Periodically check for staleness and rebuild if needed."""
    global _index

    while True:
        time.sleep(_REFRESH_INTERVAL_S)

        try:
            current_mtime = _mtime_signature(project_root)
            if current_mtime <= _index.mtime_sig:
                continue  # Still fresh

            logger.info(
                "[ProjectIndex] Stale detected (mtime %.0f > cached %.0f), rebuilding",
                current_mtime, _index.mtime_sig,
            )

            _publish_event("index:stale", data={
                "current_mtime": current_mtime,
                "cached_mtime": _index.mtime_sig,
            })

            _index.building = True
            t0 = time.perf_counter()

            _build_file_index(project_root, _index)
            _build_symbol_index(project_root, _index)
            _build_peek_cache(project_root, _index)

            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            _index.mtime_sig = current_mtime
            _index.last_built = time.time()
            _index.build_time_ms = elapsed_ms
            _index.building = False

            _save_to_disk(project_root, _index)

            _publish_event("index:ready", data={
                "build_ms": elapsed_ms,
                "files": _index.file_count,
                "symbols": _index.symbol_count,
                "peek_pages": _index.peek_page_count,
                "trigger": "refresh",
            })

            logger.info("[ProjectIndex] Refresh complete in %dms", elapsed_ms)

        except Exception as e:
            logger.warning("[ProjectIndex] Refresh error: %s", e)
            _index.building = False


# ── Event bus (fail-safe) ───────────────────────────────────────

def _publish_event(event_type: str, **kw: Any) -> None:
    """Publish an index lifecycle event (fail-safe)."""
    try:
        from src.core.services.event_bus import bus
        bus.publish(event_type, **kw)
    except Exception:
        pass


# ── Public API ──────────────────────────────────────────────────

def start_project_index(project_root: Path) -> threading.Thread:
    """Start the background index builder daemon thread.

    Should be called once during ``create_app()`` setup, after
    the staleness watcher. The thread runs until the process exits.

    Args:
        project_root: Project root directory.

    Returns:
        The started daemon thread.
    """
    global _project_root, _thread

    _project_root = project_root

    t = threading.Thread(
        target=_build_loop,
        args=(project_root,),
        daemon=True,
        name="project-index",
    )
    t.start()
    _thread = t

    logger.info("[ProjectIndex] Background builder started")
    return t


def invalidate_path(doc_path: str) -> None:
    """Invalidate a single file's peek cache entry.

    Call this when a file is saved via the content API so the next
    peek request gets fresh results.
    """
    if doc_path in _index.peek_cache:
        del _index.peek_cache[doc_path]
        logger.debug("[ProjectIndex] Invalidated peek cache for %s", doc_path)


def index_status() -> dict:
    """Return the current index status for observability.

    Returns:
        Dict with ready, building, last_built, build_time_ms,
        and count fields.
    """
    return {
        "ready": _index.ready,
        "symbols_ready": _index.symbols_ready,
        "peek_cached": _index.peek_cached,
        "building": _index.building,
        "last_built": _index.last_built,
        "build_time_ms": _index.build_time_ms,
        "file_count": _index.file_count,
        "dir_count": _index.dir_count,
        "symbol_count": _index.symbol_count,
        "peek_page_count": _index.peek_page_count,
        "age_s": round(time.time() - _index.last_built) if _index.last_built else None,
    }
