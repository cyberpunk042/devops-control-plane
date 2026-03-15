"""
Index domain registration — the root of the mediator data tree.

Registers the project file index as mediator nodes, enabling delta-driven
incremental updates instead of monolithic 30-second full rebuilds.

Phase 8A nodes (core foundation)::

    index.scan    — per-file mtime snapshot via os.walk()     (TTL=0, ~38ms)
    index.delta   — diff(prev_scan, curr_scan)                (TTL=0, ~1ms)
    index.files   — filename → [paths] lookup map             (TTL=0, derived)
    index.dirs    — dirname  → [paths] lookup map             (TTL=0, derived)
    index.paths   — flat set of all relative paths            (TTL=0, derived)
    index.stats   — aggregate counts and timings              (TTL=0, derived)

Phase 8B node (incremental symbols)::

    index.symbols — delta-driven symbol index                 (TTL=0, incremental)
                    cold: ~30s (full parse)  warm: ~60ms/file

Phase 8C node (incremental peek)::

    index.peek    — pre-computed peek results for .md files   (TTL=0, incremental)
                    cold: ~2s   warm: ~50ms/file

Phase 8E node (classification)::

    index.classify — language/framework detection from scan   (TTL=0, derived)
                     ~5ms (extension counting + marker file checks)

Dependency graph::

    index.scan
      ├── index.delta
      │     ├── index.symbols  (incremental)
      │     │     └── index.peek  (incremental, depends on symbols + delta)
      │     └── index.peek      (also depends on delta directly)
      ├── index.files
      ├── index.dirs
      ├── index.paths
      ├── index.classify
      └── index.stats  (depends on scan, delta, dirs, symbols, classify)

Future phases will add:
    (downstream wiring of detect.* to depend on index.classify)

Design decisions
────────────────
1. **Per-file mtime tracking**: the scan stores {path: {mtime, size, ext}}
   for every file in the project.  This enables surgical delta computation
   — we know exactly which files changed, not just "something changed."

2. **TTL=0 for all nodes**: the mediator re-computes on every get().
   This is correct because the FS watcher drives updates via bust(),
   and downstream nodes use the delta to skip unnecessary work.

3. **Persistent accumulators**: the prev_scan and symbol map live in
   closure scope.  They persist across mediator get() calls.

4. **Same skip rules as legacy index**: hidden dirs, __pycache__, .venv, etc.
   Ported from project_index.py's _SKIP_DIRS.

5. **Incremental symbols**: on delta, purge symbols from removed/modified
   files, then parse only added/modified files.  500x faster for the
   common case (1 file edit: ~60ms instead of ~30s).

6. **Incremental peek**: on delta, if only .md files changed, re-peek
   only those files.  If source files changed (symbol index invalidated),
   re-peek all .md files.  Cold start does full peek.

7. **Classification**: derived from scan snapshot — counts extensions to
   identify languages, checks for marker files (Dockerfile, package.json,
   etc.) to detect frameworks.  ~5ms.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.tree import TreeRegistration

logger = logging.getLogger(__name__)


# ── Constants ───────────────────────────────────────────────────

# Directories to skip during walks.  Ported from project_index.py.
_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", ".backup", ".state", ".agent", ".venv", "venv",
    "node_modules", "__pycache__", "build", "dist",
    ".tox", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    ".next", ".nuxt", "site-packages", "_build",
    ".docusaurus",
})


# ── Data structures ─────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class FileEntry:
    """Metadata for a single file in the project scan."""

    mtime: float   # seconds since epoch
    size: int      # bytes
    ext: str       # extension without dot (e.g. "py", "md", "")


@dataclass(frozen=True, slots=True)
class IndexSymbolEntry:
    """A symbol location in the project, for the symbol index.

    Mirrors the legacy ``project_index.IndexSymbolEntry`` but uses
    frozen slots for performance and immutability.
    """

    name: str    # symbol name (e.g. "QueryMediator")
    file: str    # relative file path
    line: int    # line number in the file
    kind: str    # "function", "class", "async_function", etc.


@dataclass(frozen=True, slots=True)
class ScanDelta:
    """What changed between two scan snapshots."""

    added: list[str]       # new files since last scan
    removed: list[str]     # files that no longer exist
    modified: list[str]    # files whose mtime increased
    timestamp: float       # when this delta was computed

    @property
    def empty(self) -> bool:
        """True if nothing changed."""
        return not self.added and not self.removed and not self.modified

    @property
    def changed_paths(self) -> list[str]:
        """All paths that need re-processing (added + modified)."""
        return self.added + self.modified

    @property
    def total_changes(self) -> int:
        """Total number of changes."""
        return len(self.added) + len(self.removed) + len(self.modified)


# ── ScanView — materialized view over scan data ────────────────


class ScanView:
    """Query interface over ``scan_project()`` output.

    Pre-builds indexes for O(1) lookups by extension, filename,
    and directory.  Built once from scan data (~5ms for ~5000 files),
    then all queries are O(1) or O(K) where K is the result count.

    Ops functions use this instead of doing their own ``os.walk``.
    If the scan data changes (FS trigger), the mediator recomputes
    ``index.view`` which creates a fresh ScanView.

    Parameters
    ----------
    scan : dict[str, FileEntry]
        Output of ``scan_project()`` — maps relative paths to
        ``FileEntry(mtime, size, ext)``.
    """

    __slots__ = ("_scan", "_by_ext", "_by_name", "_by_dir", "_dir_set")

    def __init__(self, scan: dict[str, FileEntry]) -> None:
        self._scan = scan

        # Index by extension: {"py": ["src/foo.py", ...], ...}
        by_ext: dict[str, list[str]] = {}
        # Index by filename: {"Dockerfile": ["./Dockerfile", ...], ...}
        by_name: dict[str, list[str]] = {}
        # Index by parent directory: {"src/core": ["src/core/foo.py", ...], ...}
        by_dir: dict[str, list[str]] = {}
        # Set of all directory paths that contain files
        dir_set: set[str] = set()

        for rel_path, entry in scan.items():
            # Extension index
            if entry.ext:
                by_ext.setdefault(entry.ext, []).append(rel_path)

            # Filename index
            sep_idx = rel_path.rfind(os.sep)
            if sep_idx < 0:
                # Check forward slash too (cross-platform)
                sep_idx = rel_path.rfind("/")
            fname = rel_path[sep_idx + 1:] if sep_idx >= 0 else rel_path
            by_name.setdefault(fname, []).append(rel_path)

            # Parent directory index
            if sep_idx >= 0:
                parent = rel_path[:sep_idx]
            else:
                parent = "."
            by_dir.setdefault(parent, []).append(rel_path)

            # Directory set — all ancestor dirs
            parts = rel_path.replace("\\", "/").split("/")
            for i in range(1, len(parts)):
                dir_set.add("/".join(parts[:i]))

        self._by_ext = by_ext
        self._by_name = by_name
        self._by_dir = by_dir
        self._dir_set = dir_set

    # ── Query methods ──────────────────────────────────────────

    def files_with_ext(self, ext: str) -> list[str]:
        """All relative paths with the given extension.

        Parameters
        ----------
        ext : str
            Extension WITHOUT leading dot (e.g. ``"py"``, ``"md"``).

        Returns
        -------
        list[str]
            Relative paths.  Empty list if no matches.
        """
        return list(self._by_ext.get(ext, []))

    def files_named(self, name: str) -> list[str]:
        """All relative paths whose filename matches exactly.

        Parameters
        ----------
        name : str
            Exact filename (e.g. ``"Dockerfile"``, ``"Chart.yaml"``).

        Returns
        -------
        list[str]
            Relative paths.  Empty list if no matches.
        """
        return list(self._by_name.get(name, []))

    def files_in_dir(
        self, dir_path: str, *, recursive: bool = True,
    ) -> list[str]:
        """All files in a directory.

        Parameters
        ----------
        dir_path : str
            Relative directory path (e.g. ``"src/core"``, ``"tests"``).
        recursive : bool
            If ``True``, includes files in subdirectories.
            If ``False``, only direct children.

        Returns
        -------
        list[str]
            Relative file paths.
        """
        # Normalise separators
        dir_path = dir_path.rstrip("/").rstrip(os.sep)

        if not recursive:
            return list(self._by_dir.get(dir_path, []))

        # Recursive: match all paths that start with dir_path/
        prefix = dir_path + "/"
        return [
            p for p in self._scan
            if p.startswith(prefix) or p.replace("\\", "/").startswith(prefix)
        ]

    def dir_exists(self, dir_path: str) -> bool:
        """Check if a directory exists (has any files under it).

        Parameters
        ----------
        dir_path : str
            Relative directory path.

        Returns
        -------
        bool
        """
        dir_path = dir_path.rstrip("/").rstrip(os.sep)
        return dir_path in self._dir_set

    def has_file(self, rel_path: str) -> bool:
        """Check if a specific file exists in the scan.

        Parameters
        ----------
        rel_path : str
            Relative path to the file.

        Returns
        -------
        bool
        """
        return rel_path in self._scan

    def file_entry(self, rel_path: str) -> FileEntry | None:
        """Get the FileEntry for a specific file.

        Parameters
        ----------
        rel_path : str
            Relative path to the file.

        Returns
        -------
        FileEntry | None
            The entry, or ``None`` if not found.
        """
        return self._scan.get(rel_path)

    @property
    def file_count(self) -> int:
        """Total number of files in the scan."""
        return len(self._scan)

    @property
    def extensions(self) -> list[str]:
        """All extensions present in the scan."""
        return list(self._by_ext.keys())

    def __repr__(self) -> str:
        return (
            f"ScanView(files={len(self._scan)}, "
            f"extensions={len(self._by_ext)}, "
            f"dirs={len(self._dir_set)})"
        )


# ── ScanView accessor ──────────────────────────────────────────


def get_scan_view() -> ScanView | None:
    """Get the current ScanView from the mediator cache.

    Uses ``peek()`` — never triggers computation.  Returns ``None``
    if the mediator isn't initialized or the scan hasn't been
    computed yet.

    This is safe to call from anywhere:
    - CLI mode (no mediator): returns ``None``
    - Tests (no mediator): returns ``None``
    - Web server before first scan: returns ``None``
    - Web server after first scan: returns the ``ScanView``

    Ops functions should check the return value and fall back to
    their own ``os.walk`` if ``None``.

    Returns
    -------
    ScanView | None
    """
    try:
        from src.core.services.mediator import get_mediator
        m = get_mediator()
        result = m.peek("index.view")
        if result is not None:
            return result["data"]
    except (RuntimeError, KeyError, Exception):
        pass
    return None


# ── Core functions ──────────────────────────────────────────────

def scan_project(project_root: Path) -> dict[str, FileEntry]:
    """Walk the project tree and return per-file metadata.

    Returns a dict mapping relative paths to FileEntry instances.
    Uses the same skip rules as the legacy project_index.py.

    Parameters
    ----------
    project_root : Path
        The project root directory.

    Returns
    -------
    dict[str, FileEntry]
        Map of relative_path → FileEntry for every file in the project.
    """
    t0 = time.perf_counter()
    result: dict[str, FileEntry] = {}
    root_str = str(project_root)

    for dirpath, dirnames, filenames in os.walk(project_root):
        # Prune hidden and build directories (in-place)
        dirnames[:] = [
            d for d in dirnames
            if d not in _SKIP_DIRS and not d.startswith(".")
        ]

        for fname in filenames:
            if fname.startswith("."):
                continue

            full = os.path.join(dirpath, fname)
            try:
                rel = os.path.relpath(full, root_str)
                st = os.stat(full)
            except (ValueError, OSError):
                continue

            # Extract extension
            dot = fname.rfind(".")
            ext = fname[dot + 1:].lower() if dot > 0 else ""

            result[rel] = FileEntry(
                mtime=st.st_mtime,
                size=st.st_size,
                ext=ext,
            )

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "[MediatorIndex] scan: %d files in %dms",
        len(result), elapsed_ms,
    )
    return result


def diff_scans(
    prev: dict[str, FileEntry],
    curr: dict[str, FileEntry],
) -> ScanDelta:
    """Compute the delta between two scan snapshots.

    Parameters
    ----------
    prev : dict[str, FileEntry]
        The previous scan snapshot (empty dict on first run).
    curr : dict[str, FileEntry]
        The current scan snapshot.

    Returns
    -------
    ScanDelta
        The computed delta.
    """
    prev_keys = set(prev)
    curr_keys = set(curr)

    added = sorted(curr_keys - prev_keys)
    removed = sorted(prev_keys - curr_keys)
    modified = sorted(
        p for p in (curr_keys & prev_keys)
        if curr[p].mtime > prev[p].mtime
    )

    delta = ScanDelta(
        added=added,
        removed=removed,
        modified=modified,
        timestamp=time.time(),
    )

    if not delta.empty:
        logger.info(
            "[MediatorIndex] delta: +%d -%d ~%d",
            len(added), len(removed), len(modified),
        )

    return delta


def derive_file_map(scan: dict[str, FileEntry]) -> dict[str, list[str]]:
    """Derive filename → [relative paths] lookup from the scan.

    Parameters
    ----------
    scan : dict[str, FileEntry]
        The current scan snapshot.

    Returns
    -------
    dict[str, list[str]]
        Map of filename → list of relative paths.
    """
    file_map: dict[str, list[str]] = {}
    for rel_path in scan:
        fname = os.path.basename(rel_path)
        file_map.setdefault(fname, []).append(rel_path)
    return file_map


def derive_dir_map(scan: dict[str, FileEntry]) -> dict[str, list[str]]:
    """Derive dirname → [relative paths] lookup from the scan.

    Collects all unique directory paths from the scan and maps
    each directory name to its list of relative paths.  Also indexes
    with trailing slash (matching legacy behavior).

    Parameters
    ----------
    scan : dict[str, FileEntry]
        The current scan snapshot.

    Returns
    -------
    dict[str, list[str]]
        Map of dirname → list of relative directory paths.
    """
    dirs_seen: dict[str, None] = {}  # ordered set via dict
    for rel_path in scan:
        parent = os.path.dirname(rel_path)
        while parent and parent not in dirs_seen:
            dirs_seen[parent] = None
            parent = os.path.dirname(parent)

    dir_map: dict[str, list[str]] = {}
    for dir_path in dirs_seen:
        name = os.path.basename(dir_path)
        if name:
            dir_map.setdefault(name, []).append(dir_path)
            # Also index with trailing slash (legacy compat)
            dir_map.setdefault(name + "/", []).append(dir_path)

    return dir_map


# ── Incremental symbol parsing ──────────────────────────────────

def incremental_symbols(
    project_root: Path,
    delta: ScanDelta,
    current: dict[str, list[IndexSymbolEntry]],
) -> dict[str, list[IndexSymbolEntry]]:
    """Update the symbol map incrementally based on the scan delta.

    On cold start (empty ``current``), this does a full parse of all
    source files via ``ParserRegistry.parse_tree()``.  On warm runs,
    it only purges symbols from removed/modified files and parses
    newly added/modified files.

    Parameters
    ----------
    project_root : Path
        Project root directory.
    delta : ScanDelta
        The delta from the latest scan.
    current : dict[str, list[IndexSymbolEntry]]
        The current accumulated symbol map (mutated in place).

    Returns
    -------
    dict[str, list[IndexSymbolEntry]]
        The updated symbol map.
    """
    t0 = time.perf_counter()

    # Lazy import so tests without parsers don't crash
    try:
        from src.core.services.audit.parsers import registry
    except ImportError:
        logger.warning("[MediatorIndex] AST parsers not available, skipping symbols")
        return current

    # ── Cold start: full parse ─────────────────────────────
    if not current:
        try:
            analyses = registry.parse_tree(project_root)
        except Exception as e:
            logger.warning("[MediatorIndex] full symbol parse failed: %s", e)
            return current

        for rel_path, analysis in analyses.items():
            for sym in analysis.symbols:
                entry = IndexSymbolEntry(
                    name=sym.name,
                    file=rel_path,
                    line=sym.lineno,
                    kind=sym.kind,
                )
                current.setdefault(sym.name, []).append(entry)

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        sym_count = sum(len(v) for v in current.values())
        logger.info(
            "[MediatorIndex] symbols cold: %d unique names, %d entries in %dms",
            len(current), sym_count, elapsed_ms,
        )
        return current

    # ── Warm: incremental update ───────────────────────────
    if delta.empty:
        return current  # nothing changed, skip entirely

    # Step 1: Purge symbols from removed + modified files
    dirty_files = set(delta.removed + delta.modified)
    if dirty_files:
        purged = 0
        for name in list(current.keys()):
            before = len(current[name])
            current[name] = [
                s for s in current[name] if s.file not in dirty_files
            ]
            purged += before - len(current[name])
            if not current[name]:
                del current[name]
        if purged:
            logger.debug(
                "[MediatorIndex] symbols: purged %d entries from %d files",
                purged, len(dirty_files),
            )

    # Step 2: Parse only new/modified source files
    parse_targets = [
        p for p in delta.changed_paths
        if _is_parseable(p)
    ]
    parsed_count = 0
    new_entries = 0
    for idx, rel_path in enumerate(parse_targets):
        # ── Yield checkpoint — release GIL for web requests ──
        if idx % 10 == 0 and idx > 0:
            try:
                from src.core.services.mediator.work_queue import (
                    current_yield_check, YIELD_SLEEP,
                )
                if current_yield_check():
                    time.sleep(YIELD_SLEEP)
            except ImportError:
                pass

        abs_path = project_root / rel_path
        if not abs_path.is_file():
            continue
        try:
            analysis = registry.parse_file(abs_path, project_root)
            if analysis is None:
                continue
            for sym in analysis.symbols:
                entry = IndexSymbolEntry(
                    name=sym.name,
                    file=analysis.path,
                    line=sym.lineno,
                    kind=sym.kind,
                )
                current.setdefault(sym.name, []).append(entry)
                new_entries += 1
            parsed_count += 1
        except Exception as e:
            logger.debug(
                "[MediatorIndex] symbol parse failed for %s: %s", rel_path, e,
            )

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    if parsed_count > 0 or dirty_files:
        logger.info(
            "[MediatorIndex] symbols incremental: "
            "parsed %d files (+%d entries), purged %d files in %dms",
            parsed_count, new_entries, len(dirty_files), elapsed_ms,
        )

    return current


def _is_parseable(rel_path: str) -> bool:
    """Check if a file extension is recognized by the parser registry.

    Quick check without importing the full registry — matches the
    extensions supported by the audit parsers.
    """
    dot = rel_path.rfind(".")
    if dot < 0:
        return False
    ext = rel_path[dot + 1:].lower()
    # Supported by the audit parsers (python, js, go, rust, templates)
    return ext in {
        "py", "pyw", "pyi",
        "js", "jsx", "ts", "tsx", "mjs", "cjs",
        "go",
        "rs",
        "html", "htm", "jinja", "jinja2", "j2",
        "yml", "yaml",
        "toml",
        "json",
        "css", "scss", "sass", "less",
        "md", "markdown", "rst",
        "sh", "bash", "zsh",
        "dockerfile",
    }


# ── Incremental peek cache ──────────────────────────────────────

def _peek_one_md(
    project_root: Path,
    rel_path: str,
    sym_idx: dict,
) -> dict[str, list[dict]] | None:
    """Peek a single markdown file.

    Returns the peek entry dict (with "resolved" and/or "unresolved" keys),
    or None if the file cannot be peeked.

    Parameters
    ----------
    project_root : Path
        Project root directory.
    rel_path : str
        Relative path to the markdown file.
    sym_idx : dict
        Symbol index in peek's SymbolEntry format.

    Returns
    -------
    dict or None
    """
    try:
        from src.core.services.peek import scan_and_resolve_all
    except ImportError:
        return None

    md_path = project_root / rel_path
    if not md_path.is_file():
        return None

    try:
        content = md_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    if not content.strip():
        return None

    try:
        resolved, unresolved, _pending = scan_and_resolve_all(
            content, rel_path, project_root, sym_idx,
        )
    except Exception as e:
        logger.debug("[MediatorIndex] Peek failed for %s: %s", rel_path, e)
        return None

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

    return entry if entry else None


def _convert_symbols_for_peek(
    symbols: dict[str, list[IndexSymbolEntry]],
) -> dict:
    """Convert IndexSymbolEntry map → peek's SymbolEntry map.

    The peek module uses its own SymbolEntry dataclass.
    This converts our mediator-native format to peek's format.
    """
    try:
        from src.core.services.peek import SymbolEntry
    except ImportError:
        return {}

    result: dict[str, list] = {}
    for name, entries in symbols.items():
        result[name] = [
            SymbolEntry(name=e.name, file=e.file, line=e.line, kind=e.kind)
            for e in entries
        ]
    return result


def incremental_peek(
    project_root: Path,
    delta: ScanDelta,
    symbols: dict[str, list[IndexSymbolEntry]],
    scan: dict[str, FileEntry],
    current: dict[str, dict[str, list[dict]]],
) -> dict[str, dict[str, list[dict]]]:
    """Update the peek cache incrementally based on the scan delta.

    Strategy:
    - **Cold start** (empty ``current``): peek all .md files.
    - **Only .md files changed**: re-peek only those .md files.
    - **Source files changed** (symbols may have changed): re-peek
      ALL .md files since any symbol reference could be affected.
    - **Nothing changed**: return current unchanged.

    Parameters
    ----------
    project_root : Path
        Project root directory.
    delta : ScanDelta
        The delta from the latest scan.
    symbols : dict
        The current symbol index (from index.symbols).
    scan : dict
        The current scan snapshot (from index.scan).
    current : dict
        The current accumulated peek cache (mutated in place).

    Returns
    -------
    dict
        The updated peek cache.
    """
    t0 = time.perf_counter()

    # Convert symbols for peek module compatibility
    sym_idx = _convert_symbols_for_peek(symbols)

    # ── Cold start: full peek ──────────────────────────────
    if not current:
        md_files = sorted(
            p for p in scan if p.endswith(".md")
        )
        count = 0
        for rel in md_files:
            entry = _peek_one_md(project_root, rel, sym_idx)
            if entry:
                current[rel] = entry
                count += 1

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "[MediatorIndex] peek cold: %d pages from %d md files in %dms",
            count, len(md_files), elapsed_ms,
        )
        return current

    # ── Warm: incremental ──────────────────────────────────
    if delta.empty:
        return current  # nothing changed

    all_changed = delta.added + delta.removed + delta.modified
    md_changed = [p for p in all_changed if p.endswith(".md")]
    source_changed = [p for p in all_changed if not p.endswith(".md")]

    # Purge removed .md files from cache
    for removed_path in delta.removed:
        if removed_path.endswith(".md") and removed_path in current:
            del current[removed_path]

    if source_changed:
        # Source files changed → symbol index may have changed →
        # re-peek ALL .md files (any reference could be affected)
        md_files = sorted(p for p in scan if p.endswith(".md"))
        count = 0
        for rel in md_files:
            entry = _peek_one_md(project_root, rel, sym_idx)
            if entry:
                current[rel] = entry
                count += 1
            elif rel in current:
                del current[rel]  # no longer peekable

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "[MediatorIndex] peek full-refresh (source change): "
            "%d pages from %d md files in %dms",
            count, len(md_files), elapsed_ms,
        )
    elif md_changed:
        # Only .md files changed → re-peek only those
        count = 0
        for rel in md_changed:
            if rel in delta.removed:
                continue  # already purged above
            entry = _peek_one_md(project_root, rel, sym_idx)
            if entry:
                current[rel] = entry
                count += 1
            elif rel in current:
                del current[rel]

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "[MediatorIndex] peek incremental: "
            "%d pages from %d changed md files in %dms",
            count, len(md_changed), elapsed_ms,
        )

    return current


# ── Classification ──────────────────────────────────────────────

# Extension → language mapping
_EXT_LANG: dict[str, str] = {
    "py": "python", "pyw": "python", "pyi": "python",
    "js": "javascript", "jsx": "javascript", "mjs": "javascript", "cjs": "javascript",
    "ts": "typescript", "tsx": "typescript",
    "go": "go",
    "rs": "rust",
    "java": "java", "kt": "kotlin", "scala": "scala",
    "rb": "ruby",
    "php": "php",
    "cs": "csharp",
    "cpp": "cpp", "cc": "cpp", "cxx": "cpp", "hpp": "cpp",
    "c": "c", "h": "c",
    "swift": "swift",
    "dart": "dart",
    "lua": "lua",
    "r": "r",
    "html": "html", "htm": "html",
    "css": "css", "scss": "css", "sass": "css", "less": "css",
    "md": "markdown", "markdown": "markdown", "mdx": "markdown", "rst": "markdown",
    "yml": "yaml", "yaml": "yaml",
    "json": "json",
    "toml": "toml",
    "xml": "xml",
    "sql": "sql",
    "sh": "shell", "bash": "shell", "zsh": "shell",
}

# Marker files → framework name
_FRAMEWORK_MARKERS: dict[str, str] = {
    "Dockerfile": "docker",
    "docker-compose.yml": "docker-compose",
    "docker-compose.yaml": "docker-compose",
    "package.json": "node",
    "tsconfig.json": "typescript",
    "Cargo.toml": "rust-cargo",
    "go.mod": "go-modules",
    "pyproject.toml": "python-project",
    "setup.py": "python-setuptools",
    "setup.cfg": "python-setuptools",
    "Pipfile": "pipenv",
    "Gemfile": "ruby-bundler",
    "pom.xml": "java-maven",
    "build.gradle": "java-gradle",
    "mix.exs": "elixir-mix",
    ".terraform": "terraform",
    "Makefile": "make",
    "CMakeLists.txt": "cmake",
    "Vagrantfile": "vagrant",
    "Procfile": "heroku",
    ".github": "github-actions",
    ".gitlab-ci.yml": "gitlab-ci",
    "Jenkinsfile": "jenkins",
    ".circleci": "circleci",
}


def classify_project(
    scan: dict[str, FileEntry],
) -> dict[str, Any]:
    """Derive language and framework classification from the scan.

    Analyzes the scan snapshot to produce:
    - ``languages``: dict of language → file count
    - ``primary_language``: the most common language (by file count)
    - ``frameworks``: list of detected framework names
    - ``extensions``: dict of extension → count (raw data)

    Parameters
    ----------
    scan : dict
        The scan snapshot from ``index.scan``.

    Returns
    -------
    dict
        Classification result.
    """
    # Count extensions
    ext_counts: dict[str, int] = {}
    for _path, entry in scan.items():
        ext = entry.ext
        if ext:
            ext_counts[ext] = ext_counts.get(ext, 0) + 1

    # Map extensions to languages
    lang_counts: dict[str, int] = {}
    for ext, count in ext_counts.items():
        lang = _EXT_LANG.get(ext)
        if lang:
            lang_counts[lang] = lang_counts.get(lang, 0) + count

    # Sort by count descending
    sorted_langs = dict(
        sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)
    )

    # Determine primary language
    primary = ""
    if sorted_langs:
        primary = next(iter(sorted_langs))

    # Detect frameworks from marker files in the scan
    # Check top-level filenames and directory names
    all_top_level: set[str] = set()
    for path in scan:
        # Get the top segment (filename or first directory)
        parts = path.replace("\\", "/").split("/")
        if len(parts) == 1:
            all_top_level.add(parts[0])  # root-level file
        else:
            all_top_level.add(parts[0])  # root-level directory

    detected_frameworks: list[str] = []
    for marker, framework in _FRAMEWORK_MARKERS.items():
        if marker in all_top_level:
            detected_frameworks.append(framework)

    detected_frameworks.sort()

    return {
        "languages": sorted_langs,
        "primary_language": primary,
        "frameworks": detected_frameworks,
        "extensions": dict(sorted(ext_counts.items(), key=lambda x: x[1], reverse=True)),
    }


# ── Registration ────────────────────────────────────────────────

def register_index(mediator: QueryMediator) -> None:
    """Register index.* nodes — the root of the data tree.

    These nodes form the foundation that all other domains
    (detect, devops, posture) will eventually depend on.

    Parameters
    ----------
    mediator : QueryMediator
        The initialized mediator instance.
    """
    tree = mediator.tree
    root = mediator.project_root

    # ── Persistent state for delta computation ─────────────
    # Kept in closure scope.  The prev_scan accumulates across
    # mediator.get() calls to enable delta computation.
    _state: dict[str, Any] = {
        "prev_scan": {},
        "symbol_acc": {},   # accumulator for incremental symbol index
        "peek_acc": {},     # accumulator for incremental peek cache
    }

    # ── Persistence helper ──────────────────────────────────
    # After each persisted resolver computes, save to disk shard.
    from src.core.services.mediator.persistence import save_index_shard

    def _persisting(mediator_path: str, resolver_fn: Any) -> Any:
        """Wrap a resolver to save its result to disk after computation."""
        def _wrapper():
            result = resolver_fn()
            try:
                save_index_shard(root, mediator_path, result)
            except Exception as exc:
                logger.warning(
                    "failed to persist %s: %s", mediator_path, exc,
                )
            return result
        return _wrapper

    # ── index.scan ─────────────────────────────────────────
    tree.register(TreeRegistration(
        path="index.scan",
        resolver=_persisting("index.scan", lambda: scan_project(root)),
        ttl=None,
    ))

    # ── index.view (ScanView — materialized view) ──────────
    tree.register(TreeRegistration(
        path="index.view",
        resolver=lambda: ScanView(mediator.get("index.scan")["data"]),
        ttl=None,
        depends_on=["index.scan"],
    ))

    # ── index.delta ────────────────────────────────────────
    def _compute_delta() -> ScanDelta:
        curr_scan = mediator.get("index.scan")["data"]
        delta = diff_scans(_state["prev_scan"], curr_scan)
        _state["prev_scan"] = curr_scan
        return delta

    tree.register(TreeRegistration(
        path="index.delta",
        resolver=_compute_delta,
        ttl=None,
        depends_on=["index.scan"],
    ))

    # ── index.files ────────────────────────────────────────
    tree.register(TreeRegistration(
        path="index.files",
        resolver=lambda: derive_file_map(
            mediator.get("index.scan")["data"]
        ),
        ttl=None,
        depends_on=["index.scan"],
    ))

    # ── index.dirs ─────────────────────────────────────────
    tree.register(TreeRegistration(
        path="index.dirs",
        resolver=lambda: derive_dir_map(
            mediator.get("index.scan")["data"]
        ),
        ttl=None,
        depends_on=["index.scan"],
    ))

    # ── index.paths ────────────────────────────────────────
    tree.register(TreeRegistration(
        path="index.paths",
        resolver=lambda: set(
            mediator.get("index.scan")["data"].keys()
        ),
        ttl=None,
        depends_on=["index.scan"],
    ))

    # ── index.stats ────────────────────────────────────────
    def _compute_stats() -> dict[str, Any]:
        scan = mediator.get("index.scan")["data"]
        delta = mediator.get("index.delta")["data"]

        # Count by extension
        ext_counts: dict[str, int] = {}
        total_size = 0
        for entry in scan.values():
            ext_counts[entry.ext] = ext_counts.get(entry.ext, 0) + 1
            total_size += entry.size

        # Derive dir count from dir_map
        dirs = mediator.get("index.dirs")["data"]
        # Each dir name maps to N paths; unique dir paths = total entries / 2
        # (because we index both "name" and "name/")
        unique_dir_paths: set[str] = set()
        for paths_list in dirs.values():
            unique_dir_paths.update(paths_list)

        # Fetch classify data
        classification = mediator.get("index.classify")["data"]

        # Fetch symbol count — use peek() to avoid triggering a 30s recompute
        symbol_count = 0
        try:
            sym_result = mediator.peek("index.symbols")
            if sym_result is not None:
                symbols = sym_result.get("data", {})
                symbol_count = sum(len(v) for v in symbols.values())
        except Exception:
            pass

        return {
            "file_count": len(scan),
            "dir_count": len(unique_dir_paths),
            "total_size_bytes": total_size,
            "symbol_count": symbol_count,
            "extensions": ext_counts,
            "primary_language": classification.get("primary_language", ""),
            "framework_count": len(classification.get("frameworks", [])),
            "last_delta": {
                "added": len(delta.added),
                "removed": len(delta.removed),
                "modified": len(delta.modified),
                "empty": delta.empty,
                "timestamp": delta.timestamp,
            } if isinstance(delta, ScanDelta) else {
                "added": delta.get("added", 0) if isinstance(delta, dict) else 0,
                "removed": delta.get("removed", 0) if isinstance(delta, dict) else 0,
                "modified": delta.get("modified", 0) if isinstance(delta, dict) else 0,
                "empty": True,
                "timestamp": 0,
            },
        }

    tree.register(TreeRegistration(
        path="index.stats",
        resolver=_compute_stats,
        ttl=None,
        depends_on=[
            "index.scan",
            "index.delta",
            "index.dirs",
            "index.symbols",
            "index.classify",
        ],
    ))

    # ── index.classify (Phase 8E — classification) ─────────
    tree.register(TreeRegistration(
        path="index.classify",
        resolver=_persisting(
            "index.classify",
            lambda: classify_project(mediator.get("index.scan")["data"]),
        ),
        ttl=None,
        depends_on=["index.scan"],
    ))

    # ── index.symbols (Phase 8B — incremental) ─────────────
    def _resolve_symbols() -> dict[str, list[IndexSymbolEntry]]:
        delta = mediator.get("index.delta")["data"]
        _state["symbol_acc"] = incremental_symbols(
            root, delta, _state["symbol_acc"],
        )
        return _state["symbol_acc"]

    tree.register(TreeRegistration(
        path="index.symbols",
        resolver=_persisting("index.symbols", _resolve_symbols),
        ttl=None,
        size=3,
        depends_on=["index.delta"],
    ))

    # ── index.peek (Phase 8C — incremental) ────────────────
    def _resolve_peek() -> dict[str, dict[str, list[dict]]]:
        delta = mediator.get("index.delta")["data"]
        symbols = mediator.get("index.symbols")["data"]
        scan = mediator.get("index.scan")["data"]
        _state["peek_acc"] = incremental_peek(
            root, delta, symbols, scan, _state["peek_acc"],
        )
        return _state["peek_acc"]

    tree.register(TreeRegistration(
        path="index.peek",
        resolver=_persisting("index.peek", _resolve_peek),
        ttl=None,
        size=2,
        depends_on=["index.delta", "index.symbols", "index.scan"],
    ))

    logger.debug("registered index.* nodes (10 total)")
