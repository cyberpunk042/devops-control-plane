"""Disk persistence for the mediator cache.

Every computed node persists to disk so restarts are warm.
On startup, all persisted files load independently and inject
into the mediator cache. No full recomputation needed.

Persistence directory::

    .state/mediator_index/
        index.scan.json         ← JSON shard for index.scan
        index.symbols.json      ← JSON shard for index.symbols
        detect.docker.json      ← JSON shard for detect.docker
        posture.full.json       ← JSON shard for posture.full
        meta.json               ← metadata (version, timestamps)

Naming convention:
    The mediator path IS the filename: ``<path>.json``
    Example: ``posture.toolchain`` → ``posture.toolchain.json``

Write path:
    persist_node() is the ONE write function. Called after every
    successful computation in QueryMediator.get(). Uses atomic
    tmp-file + rename on POSIX.

Read path:
    load_all_nodes() scans the shard directory for all .json files.
    hydrate_cache() loads them and injects into the mediator cache.

Legacy compatibility:
    Old shard files (scan.json, symbols.json, etc.) are recognized
    on load via LEGACY_SHARD_NAMES. They are read correctly but
    not renamed. On next compute, persist_node writes the new-style
    name (index.scan.json), and the old file becomes orphaned.

Thread safety:
    _file_lock serializes all disk writes. Reads are independent
    and lock-free (each file is read atomically).
"""

from __future__ import annotations

import dataclasses
import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────

SHARD_VERSION = 1

# Legacy shard name → mediator path (for loading old files)
LEGACY_SHARD_NAMES: dict[str, str] = {
    "scan":     "index.scan",
    "symbols":  "index.symbols",
    "peek":     "index.peek",
    "classify": "index.classify",
}

SHARD_DIR = ".state/mediator_index"
META_FILE = "meta.json"

# Files to skip when scanning the shard directory
_SKIP_FILES = {META_FILE}

_file_lock = threading.Lock()


# ── Data classes ────────────────────────────────────────────────────


@dataclass
class ShardMeta:
    """Metadata about the persisted shards."""

    version: int = SHARD_VERSION
    saved_at: float = 0.0
    project_root: str = ""
    shard_count: int = 0
    scan_file_count: int = 0
    symbol_count: int = 0
    peek_page_count: int = 0
    classify_languages: list[str] | None = None


# ── Helpers ─────────────────────────────────────────────────────────


def _state_dir(project_root: Path) -> Path:
    """Return the shard directory path."""
    return project_root / SHARD_DIR


def _json_default(obj: Any) -> Any:
    """JSON serialization fallback for non-standard types.

    Handles slotted dataclasses (FileEntry, IndexSymbolEntry, ScanDelta)
    which have NO __dict__ due to slots=True.
    """
    # Dataclasses first — handles slots=True classes like FileEntry
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, set):
        return sorted(obj)
    if isinstance(obj, frozenset):
        return sorted(obj)
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _rehydrate_shards(shards: dict[str, Any]) -> None:
    """Reconstruct dataclass objects from deserialized JSON dicts.

    JSON serialization flattens dataclasses (FileEntry, IndexSymbolEntry)
    to plain dicts. Downstream resolvers expect attribute access
    (entry.ext, entry.name). This function mutates shards in-place,
    converting dicts back to proper dataclass instances.
    """
    from src.core.services.mediator.registrations.index import (
        FileEntry,
        IndexSymbolEntry,
    )

    # scan shard: {path: {mtime, size, ext}} → {path: FileEntry}
    scan_data = shards.get("index.scan")
    if scan_data and isinstance(scan_data, dict):
        rehydrated = {}
        for path, entry in scan_data.items():
            if isinstance(entry, dict):
                try:
                    rehydrated[path] = FileEntry(**entry)
                except (TypeError, KeyError):
                    rehydrated[path] = entry  # keep as-is if can't convert
            else:
                rehydrated[path] = entry
        shards["index.scan"] = rehydrated
        logger.info(
            "[persistence] rehydrated %d scan entries to FileEntry",
            len(rehydrated),
        )

    # symbols shard: {name: [{name, file, line, kind}, ...]} → {name: [IndexSymbolEntry, ...]}
    symbols_data = shards.get("index.symbols")
    if symbols_data and isinstance(symbols_data, dict):
        rehydrated = {}
        total_entries = 0
        for name, entries in symbols_data.items():
            if isinstance(entries, list):
                converted = []
                for e in entries:
                    if isinstance(e, dict):
                        try:
                            converted.append(IndexSymbolEntry(**e))
                            total_entries += 1
                        except (TypeError, KeyError):
                            converted.append(e)
                    else:
                        converted.append(e)
                rehydrated[name] = converted
            else:
                rehydrated[name] = entries
        shards["index.symbols"] = rehydrated
        logger.info(
            "[persistence] rehydrated %d symbol names (%d entries) "
            "to IndexSymbolEntry",
            len(rehydrated), total_entries,
        )


# ── Persist (the ONE write path) ───────────────────────────────────


def persist_node(project_root: Path, node_path: str, data: Any) -> None:
    """Save a computed node's data to disk.

    Called after every successful computation in QueryMediator.get().
    Uses the node's mediator path as the filename (e.g. detect.docker.json).

    This is fire-and-forget — persistence must never break computation.
    """
    try:
        sdir = _state_dir(project_root)
        sdir.mkdir(parents=True, exist_ok=True)
        fpath = sdir / f"{node_path}.json"
        tmp = fpath.with_suffix(".tmp")

        with _file_lock:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, default=_json_default)
            tmp.rename(fpath)

        size_kb = fpath.stat().st_size / 1024
        logger.debug(
            "[persistence] persisted %s (%.1fKB)", node_path, size_kb,
        )
    except Exception as exc:
        logger.warning(
            "[persistence] failed to persist %s: %s", node_path, exc,
        )


def save_index_shard(
    project_root: Path,
    mediator_path: str,
    data: Any,
) -> bool:
    """Save one mediator node's data to disk.

    This function exists for backward compatibility with
    registrations/index.py which uses it in the _persisting()
    resolver wrapper. It delegates to persist_node().

    Parameters
    ----------
    project_root : Path
        Project root.
    mediator_path : str
        The mediator node path (e.g. "index.scan").
    data : Any
        The computed data to persist.

    Returns
    -------
    bool
        True if saved, False if save failed.
    """
    try:
        persist_node(project_root, mediator_path, data)
        return True
    except Exception:
        return False


# ── Load ────────────────────────────────────────────────────────────


_CONSOLIDATED_CACHE = "_consolidated.pkl"


def load_all_nodes(project_root: Path) -> tuple[dict[str, Any], bool]:
    """Load ALL persisted node data from disk.

    Fast path: loads a consolidated pickle that contains REHYDRATED data
    (actual dataclass objects, not raw dicts). Skips JSON parsing and
    rehydration entirely.

    Slow path: falls back to reading individual JSON shards. Returns
    raw dicts that need rehydration by the caller.

    Parameters
    ----------
    project_root : Path
        Project root directory.

    Returns
    -------
    tuple[dict[str, Any], bool]
        (data_dict, already_rehydrated)
        - data_dict: Map of mediator path -> loaded data.
        - already_rehydrated: True if data contains dataclass objects
          (from pickle). False if data contains raw JSON dicts (needs
          _rehydrate_shards).
    """
    import pickle

    sdir = _state_dir(project_root)
    if not sdir.is_dir():
        logger.info("[persistence] no shard directory — cold start")
        return {}, False

    # ── Fast path: consolidated pickle (rehydrated) ─────────
    pkl_path = sdir / _CONSOLIDATED_CACHE
    if pkl_path.is_file():
        try:
            pkl_mtime = pkl_path.stat().st_mtime
            # Check if any JSON shard is newer than the pickle
            any_newer = False
            for json_file in sdir.glob("*.json"):
                if json_file.name in _SKIP_FILES:
                    continue
                if json_file.stat().st_mtime > pkl_mtime:
                    any_newer = True
                    break

            if not any_newer:
                t0 = time.time()
                with pkl_path.open("rb") as f:
                    loaded = pickle.load(f)
                elapsed_ms = int((time.time() - t0) * 1000)
                logger.info(
                    "[persistence] loaded %d nodes from consolidated cache (%dms)",
                    len(loaded), elapsed_ms,
                )
                return loaded, True  # Already rehydrated — skip _rehydrate_shards
            else:
                logger.debug("[persistence] consolidated cache stale — rebuilding")
        except Exception as exc:
            logger.warning("[persistence] consolidated cache load failed: %s", exc)

    # ── Slow path: individual JSON shards ───────────────────
    loaded: dict[str, Any] = {}

    for json_file in sorted(sdir.glob("*.json")):
        if json_file.name in _SKIP_FILES:
            continue

        stem = json_file.stem
        mediator_path = LEGACY_SHARD_NAMES.get(stem, stem)

        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            loaded[mediator_path] = data
        except Exception as exc:
            logger.warning(
                "[persistence] failed to load %s: %s",
                json_file.name, exc,
            )

    if loaded:
        logger.info(
            "[persistence] loaded %d nodes from JSON shards (slow path)",
            len(loaded),
        )
    else:
        logger.info("[persistence] no persisted data found — cold start")

    return loaded, False  # Needs rehydration


def save_consolidated(project_root: Path, data: dict[str, Any]) -> None:
    """Save consolidated pickle with REHYDRATED data for fast startup.

    Called by hydrate_cache() AFTER _rehydrate_shards() so the pickle
    contains actual dataclass objects (FileEntry, IndexSymbolEntry),
    not raw JSON dicts. This eliminates both JSON parsing AND
    dataclass conversion on subsequent startups.
    """
    import pickle

    sdir = _state_dir(project_root)
    pkl_path = sdir / _CONSOLIDATED_CACHE
    try:
        tmp = pkl_path.with_suffix(".tmp")
        with tmp.open("wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.rename(pkl_path)
        size_kb = pkl_path.stat().st_size / 1024
        logger.info("[persistence] saved consolidated cache (%.1fKB)", size_kb)
    except Exception as exc:
        logger.warning("[persistence] failed to save consolidated cache: %s", exc)


def _load_meta(project_root: Path) -> ShardMeta | None:
    """Load the meta.json file.

    Returns None if missing, corrupt, or version mismatch.
    Internal helper — not part of the public API.
    """
    path = _state_dir(project_root) / META_FILE
    if not path.exists():
        return None

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("version") != SHARD_VERSION:
            logger.info(
                "[persistence] version mismatch (got %s, want %s), "
                "discarding shards",
                raw.get("version"), SHARD_VERSION,
            )
            return None
        # Only pass known fields to avoid TypeErrors on schema changes
        known = {f.name for f in fields(ShardMeta)}
        return ShardMeta(**{k: v for k, v in raw.items() if k in known})
    except Exception as exc:
        logger.warning("[persistence] failed to load meta: %s", exc)
        return None


# ── Hydration ───────────────────────────────────────────────────────


def hydrate_cache(
    mediator: Any,  # QueryMediator — Any to avoid circular import
    project_root: Path,
) -> int:
    """Load ALL persisted data from disk and inject into the mediator's cache.

    This is called ONCE at startup, AFTER register_all() and BEFORE
    the first request is served. It pre-warms the mediator cache so
    that m.get() returns data immediately without computing.

    Parameters
    ----------
    mediator : QueryMediator
        The initialized mediator instance.
    project_root : Path
        Project root directory.

    Returns
    -------
    int
        Number of cache entries injected.
    """
    all_data, already_rehydrated = load_all_nodes(project_root)
    if not all_data:
        logger.info("[persistence] cold start — nothing to hydrate")
        return 0

    # Rehydrate index dataclass objects from JSON dicts — ONLY if loaded
    # from individual JSON shards (slow path). The consolidated pickle
    # already contains rehydrated dataclass objects.
    if not already_rehydrated:
        _rehydrate_shards(all_data)

    injected = 0

    for mediator_path, data in all_data.items():
        # Only inject if the path is registered in the tree
        node = mediator.tree.resolve(mediator_path)
        if node is None or not node.is_registered:
            logger.debug(
                "[persistence] skipping %s — not registered in tree",
                mediator_path,
            )
            continue

        try:
            mediator.put(mediator_path, data, cascade=False, notify=False)
            injected += 1
            logger.debug("[persistence] hydrated %s", mediator_path)
        except Exception as exc:
            logger.warning(
                "[persistence] failed to hydrate %s: %s",
                mediator_path, exc,
            )

    # Derive cheap nodes from scan if we have it.
    scan_data = all_data.get("index.scan")
    if scan_data and isinstance(scan_data, dict):
        try:
            from src.core.services.mediator.registrations.index import (
                derive_file_map,
                derive_dir_map,
            )

            file_map = derive_file_map(scan_data)
            dir_map = derive_dir_map(scan_data)
            all_paths = set(scan_data.keys())

            mediator.put("index.files", file_map, cascade=False, notify=False)
            mediator.put("index.dirs", dir_map, cascade=False, notify=False)
            mediator.put("index.paths", all_paths, cascade=False, notify=False)
            injected += 3
            logger.debug(
                "[persistence] derived files/dirs/paths from scan "
                "(%d files, %d dirs, %d paths)",
                len(file_map), len(dir_map), len(all_paths),
            )
        except Exception as exc:
            logger.warning(
                "[persistence] failed to derive from scan: %s", exc,
            )

    # Save consolidated pickle with REHYDRATED data for fast startup next time.
    # Only save if we loaded from JSON shards (slow path) — the pickle from
    # the fast path is already up to date.
    if not already_rehydrated and all_data:
        save_consolidated(project_root, all_data)

    logger.info(
        "[persistence] hydrated %d cache entries from disk%s",
        injected,
        " (from consolidated cache)" if already_rehydrated else " (from JSON shards)",
    )
    return injected
