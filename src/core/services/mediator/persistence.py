"""Disk persistence for the mediator cache.

Every computed node persists to disk so restarts are warm.
On startup, all persisted files load independently and inject
into the mediator cache. No full recomputation needed.

Persistence directory::

    .state/mediator_index/
    ├── index.scan.json        ← per-file mtime snapshot
    ├── index.symbols.json     ← symbol index
    ├── detect.docker.json     ← docker status
    ├── posture.toolchain.json ← toolchain posture
    ├── ...                    ← any computed node
    └── meta.json              ← timestamps, counts, version

Design decisions:
    1. Atomic writes via tmp + rename (POSIX guarantees)
    2. Each node loads independently — no all-or-nothing
    3. Version check on meta.json — discard if version mismatch
    4. Every computed node persists automatically
    5. Thread-safe: file lock prevents concurrent writes
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

# Maps mediator node path → shard file name (without .json)
SHARD_MAP: dict[str, str] = {
    "index.scan":     "scan",
    "index.symbols":  "symbols",
    "index.peek":     "peek",
    "index.classify": "classify",
}

# Reverse: shard name → mediator path
SHARD_TO_PATH: dict[str, str] = {v: k for k, v in SHARD_MAP.items()}

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
    scan_data = shards.get("scan")
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
        shards["scan"] = rehydrated
        logger.info(
            "[persistence] rehydrated %d scan entries to FileEntry",
            len(rehydrated),
        )

    # symbols shard: {name: [{name, file, line, kind}, ...]} → {name: [IndexSymbolEntry, ...]}
    symbols_data = shards.get("symbols")
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
        shards["symbols"] = rehydrated
        logger.info(
            "[persistence] rehydrated %d symbol names (%d entries) "
            "to IndexSymbolEntry",
            len(rehydrated), total_entries,
        )

# ── Generic node persistence ────────────────────────────────────────


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


# ── Save (legacy index shards) ──────────────────────────────────────


def save_shard(project_root: Path, name: str, data: Any) -> Path:
    """Save a single index shard to disk (atomic write).

    Uses tmp file + rename for atomic write on POSIX.
    Creates the shard directory if it doesn't exist.

    Parameters
    ----------
    project_root : Path
        Project root directory.
    name : str
        Shard name (e.g. "scan", "symbols", "peek", "classify").
    data : Any
        The data to serialize. Must be JSON-serializable.

    Returns
    -------
    Path
        The path to the saved shard file.
    """
    sdir = _state_dir(project_root)
    sdir.mkdir(parents=True, exist_ok=True)

    path = sdir / f"{name}.json"
    tmp = path.with_suffix(".tmp")

    with _file_lock:
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, default=_json_default)
            tmp.rename(path)  # atomic on POSIX
            size_kb = path.stat().st_size / 1024
            logger.debug(
                "[persistence] saved shard %s (%.1fKB)", name, size_kb,
            )
        except Exception as exc:
            logger.warning(
                "[persistence] failed to save shard %s: %s", name, exc,
            )
            # Clean up tmp file if it exists
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    return path


def save_meta(project_root: Path, meta: ShardMeta) -> None:
    """Save the meta.json file."""
    sdir = _state_dir(project_root)
    sdir.mkdir(parents=True, exist_ok=True)

    path = sdir / META_FILE
    tmp = path.with_suffix(".tmp")

    with _file_lock:
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(asdict(meta), f)
            tmp.rename(path)
        except Exception as exc:
            logger.warning("[persistence] failed to save meta: %s", exc)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def save_index_shard(
    project_root: Path,
    mediator_path: str,
    data: Any,
) -> bool:
    """Save one mediator node's data as a shard (if it IS a shard).

    This is called by the persisting resolver wrapper after a node
    computes its value. If the node is not in SHARD_MAP, this is
    a no-op.

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
        True if saved, False if not a shard node or save failed.
    """
    shard_name = SHARD_MAP.get(mediator_path)
    if shard_name is None:
        return False

    try:
        save_shard(project_root, shard_name, data)
        return True
    except Exception:
        return False  # Warning already logged by save_shard


def save_all_shards(
    project_root: Path,
    shard_data: dict[str, Any],
) -> int:
    """Save all provided shards to disk.

    Parameters
    ----------
    project_root : Path
        Project root directory.
    shard_data : dict
        Map of shard name → data. Keys should be from SHARD_MAP values
        (e.g. {"scan": {...}, "symbols": {...}, ...}).

    Returns
    -------
    int
        Number of shards successfully saved.
    """
    saved = 0
    for name, data in shard_data.items():
        try:
            save_shard(project_root, name, data)
            saved += 1
        except Exception:
            pass  # Warning already logged by save_shard

    # Build and save metadata
    meta = ShardMeta(
        saved_at=time.time(),
        project_root=str(project_root.resolve()),
        shard_count=saved,
    )

    # Extract counts for observability
    scan_data = shard_data.get("scan")
    if scan_data and isinstance(scan_data, dict):
        meta.scan_file_count = len(scan_data)

    symbols_data = shard_data.get("symbols")
    if symbols_data and isinstance(symbols_data, dict):
        meta.symbol_count = sum(len(v) for v in symbols_data.values())

    peek_data = shard_data.get("peek")
    if peek_data and isinstance(peek_data, dict):
        meta.peek_page_count = len(peek_data)

    classify_data = shard_data.get("classify")
    if classify_data and isinstance(classify_data, dict):
        meta.classify_languages = list(
            classify_data.get("languages", {}).keys()
        )

    save_meta(project_root, meta)

    logger.info(
        "[persistence] saved %d shards (%d files, %d symbols, %d peek pages)",
        saved, meta.scan_file_count, meta.symbol_count, meta.peek_page_count,
    )
    return saved


# ── Load ────────────────────────────────────────────────────────────


def load_shard(project_root: Path, name: str) -> Any | None:
    """Load a single shard from disk.

    Returns None if the shard file doesn't exist or is corrupt.
    Does NOT raise on error — persistence must never break startup.

    Parameters
    ----------
    project_root : Path
        Project root directory.
    name : str
        Shard name (e.g. "scan", "symbols", "peek", "classify").

    Returns
    -------
    Any | None
        The deserialized data, or None if not available.
    """
    path = _state_dir(project_root) / f"{name}.json"
    if not path.exists():
        return None

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        size_kb = len(raw) / 1024
        logger.debug(
            "[persistence] loaded shard %s (%.1fKB)", name, size_kb,
        )
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "[persistence] failed to load shard %s: %s", name, exc,
        )
        return None


def load_meta(project_root: Path) -> ShardMeta | None:
    """Load the meta.json file.

    Returns None if missing, corrupt, or version mismatch.
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


def load_all_shards(project_root: Path) -> dict[str, Any]:
    """Load ALL persisted node data from disk.

    Scans the shard directory for all .json files and returns
    a dict of mediator_path -> data.

    Handles both legacy shard names (scan.json, symbols.json) and
    new-style node paths (detect.docker.json, posture.toolchain.json).

    Parameters
    ----------
    project_root : Path
        Project root directory.

    Returns
    -------
    dict[str, Any]
        Map of mediator path -> loaded data.
    """
    sdir = _state_dir(project_root)
    if not sdir.is_dir():
        logger.info("[persistence] no shard directory — cold start")
        return {}

    # Log meta info if available (optional)
    meta = load_meta(project_root)
    if meta is not None:
        age_s = time.time() - meta.saved_at
        logger.info(
            "[persistence] meta: %.1fs old, %d files, %d symbols, "
            "%d peek pages",
            age_s, meta.scan_file_count, meta.symbol_count,
            meta.peek_page_count,
        )

    loaded: dict[str, Any] = {}

    # Scan ALL .json files in the shard directory
    for json_file in sorted(sdir.glob("*.json")):
        if json_file.name in _SKIP_FILES:
            continue

        stem = json_file.stem  # e.g. "scan", "detect.docker", "index.scan"

        # Map legacy shard names to mediator paths
        mediator_path = SHARD_TO_PATH.get(stem, stem)

        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            loaded[mediator_path] = data
            size_kb = json_file.stat().st_size / 1024
            logger.debug(
                "[persistence] loaded %s (%.1fKB)",
                mediator_path, size_kb,
            )
        except Exception as exc:
            logger.warning(
                "[persistence] failed to load %s: %s",
                json_file.name, exc,
            )

    if loaded:
        logger.info(
            "[persistence] loaded %d nodes from disk",
            len(loaded),
        )
    else:
        logger.info("[persistence] no persisted data found — cold start")

    return loaded


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
    all_data = load_all_shards(project_root)
    if not all_data:
        logger.info("[persistence] cold start — nothing to hydrate")
        return 0

    # Rehydrate index dataclass objects from JSON dicts.
    # JSON flattens dataclasses; downstream resolvers expect attribute access.
    # Build a temp dict keyed by legacy shard name for _rehydrate_shards.
    index_shards: dict[str, Any] = {}
    for mpath in list(all_data.keys()):
        shard_name = SHARD_MAP.get(mpath)
        if shard_name:
            index_shards[shard_name] = all_data[mpath]
    if index_shards:
        _rehydrate_shards(index_shards)
        # Write rehydrated data back
        for mpath, shard_name in SHARD_MAP.items():
            if shard_name in index_shards:
                all_data[mpath] = index_shards[shard_name]

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

    logger.info(
        "[persistence] hydrated %d cache entries from disk",
        injected,
    )
    return injected
