# Mediator-Native Index — Full Implementation Plan

> **Purpose:** Step-by-step plan to build the ACTUAL engineered solution
> from the architecture doc, spec, and phases doc. Every phase detailed.
> Every file. Every function. Every test. No shortcuts. No minimizing.
> No invented scope.
>
> **Created:** 2026-03-13
> **Source of truth:**
> - `mediator-index-architecture.md` (the design)
> - `mediator-index-spec.md` (the contract)
> - `mediator-index-phases.md` (the wiring phases — W1-W5)
> - `mediator-cutover-catastrophe.md` (what went wrong — never repeat)
>
> **Principle:** Persistence FIRST. Then startup. Then migration.
> NEVER remove a working system before its replacement is built and validated.

---

## Current State — What Exists Right Now

### ✅ WORKING — Do Not Touch

| Component | Location | What It Does |
|-----------|----------|-------------|
| 9 index nodes | `registrations/index.py` | scan, delta, files, dirs, paths, symbols, peek, classify, stats |
| 13 detect nodes | `registrations/detect.py` | All depend on `index.classify` (Phase W1 complete) |
| 14 devops nodes | `registrations/devops.py` | Wrap `get_cached()`, cascade from detect |
| 6 posture nodes | `registrations/posture.py` | Cascade from pillars → full → summary |
| QueryMediator core | `mediator/core.py` | get/put/bust/diag/subscribe/refresh/dispatch |
| DataTree | `mediator/tree.py` | Registration, dependency graph, cascade resolution |
| FS watcher | `mediator/index_watcher.py` | Dir-level polling → put("index.scan") |
| Peek mediator-direct helpers | `peek.py` lines 77-125 | `_get_index_data()`, `_get_index_symbols()` |
| Bridge (files/dirs/paths only) | `project_index.py` lines 126-248 | `get_index()` → mediator or legacy fallback |
| 338+ tests | `tests/test_mediator_*.py` | All passing |
| Devops disk cache | `devops/cache.py` | `.state/devops_cache.json` — mtime-based persistence |
| Posture disk cache | `system_posture/cache.py` | `.state/posture_cache.json` — file persistence |
| Legacy project index | `project_index.py` | `.state/project_index.json` — full index persistence |

### ❌ BROKEN — The Catastrophe

| Component | Location | What's Wrong |
|-----------|----------|-------------|
| Context processor | `server.py` lines 224-286 | Calls 23 `m.get()` on cold cache → 84s page load |
| `extra.*` domain | `registrations/extra.py` | 10 invented nodes not in any plan |
| `register_extra()` | `registrations/__init__.py` line 37,43 | Registers invented domain |
| Bridge symbols/peek | `project_index.py` lines 205-246 | Violates SPEC-7.9 and SPEC-7.10 |
| Legacy fallback removed | `server.py` | `start_project_index()` call removed prematurely |
| Tests corrupted | `test_mediator_startup.py` | Expects 52 nodes, 5 domains (wrong) |
| Cutover plan doc | `mediator-cutover-plan.md` | Claims false completion |

### ❌ NEVER BUILT — The Missing Foundation

| Component | Architecture Section | Why It Matters |
|-----------|---------------------|----------------|
| Sharded disk persistence | §9 | Without this, mediator cache is ALWAYS cold on startup |
| `m.peek()` / `cache_only` read | — | Without this, `m.get()` ALWAYS computes on cache miss |
| Phased cold start | §8 | Without this, app blocks for 84s on first request |
| Hydration from disk | §8.1 | Without this, warm start is impossible |
| Incremental shard save | §9.3 | Without this, every save rewrites everything |

---

## The Plan — 7 Phases

```
Phase 1: UNDO THE DAMAGE
         Fix what the catastrophe broke. Restore working state.
         No new features. Just fix.

Phase 2: BUILD PERSISTENCE LAYER
         Architecture §9. Sharded disk cache.
         save_shard(), load_shard(), hydrate_mediator().
         This is the FOUNDATION that was skipped.

Phase 3: BUILD NON-BLOCKING READ
         Add m.peek() to QueryMediator.
         Returns cached data or None. NEVER computes.
         This is what the context processor needs.

Phase 4: WIRE PERSISTENCE INTO INDEX RESOLVERS
         After index.scan computes → save scan.json
         After index.symbols computes → save symbols.json
         After index.peek computes → save peek.json
         After index.classify computes → save classify.json
         Incremental: only save the shard that changed.

Phase 5: WIRE HYDRATION INTO STARTUP
         On server start, BEFORE register_all():
           load all shards from .state/mediator_index/
           inject into mediator cache as pre-warmed entries
         Result: mediator cache is WARM on first request.

Phase 6: MIGRATE CONTEXT PROCESSOR
         NOW — and ONLY now — replace _get_devops_cache()
         with mediator reads. Because:
           - Persistence exists (Phase 2) → cache is warm
           - m.peek() exists (Phase 3) → never blocks
           - Hydration exists (Phase 5) → warm from startup
         
         Handle the 23 _INJECT_KEYS properly:
           - 13 devops keys → m.peek("devops.*") (warm from disk cache)
           - 10 extra keys → KEEP reading from devops_cache.json
             OR wire them as proper devops cache keys
             (NOT as invented extra.* mediator nodes)

Phase 7: VALIDATE AND CLEAN UP
         Performance benchmarks (Phase W5 from phases doc)
         Architecture doc alignment (Phase W4 from phases doc)
         Remove legacy fallbacks ONLY after validation
```

---

## Phase 1: UNDO THE DAMAGE

### 1.1 Goal

Restore the system to a working state. First page load < 1 second.
No new features. Just fix what the catastrophe broke.

### 1.2 Changes

#### 1.2.1 server.py — Restore disk-cache context processor

**Remove** (lines 224-286):
- `_KEY_TO_MEDIATOR` dict
- Mediator-based `_inject_data_catalogs()`

**Restore** (from git commit `df245d0`):
```python
# ── Mtime-cached devops cache reader ──────────────────────────────
from src.core.services.devops.cache import _cache_path
_devops_cache_file = _cache_path(Path(project_root))
_devops_cache_data: dict = {}
_devops_cache_mtime: float = 0.0

def _get_devops_cache() -> dict:
    nonlocal _devops_cache_data, _devops_cache_mtime
    try:
        stat = _devops_cache_file.stat()
        if stat.st_mtime != _devops_cache_mtime:
            import json as _json
            _devops_cache_data = _json.loads(
                _devops_cache_file.read_text(encoding="utf-8")
            )
            _devops_cache_mtime = stat.st_mtime
    except (OSError, ValueError):
        pass
    return _devops_cache_data

# Pre-warm on startup
_get_devops_cache()

@app.context_processor
def _inject_data_catalogs():
    initial: dict[str, dict] = {}
    try:
        cache = _get_devops_cache()
        for key in _INJECT_KEYS:
            entry = cache.get(key)
            if entry and "data" in entry:
                initial[key] = {"data": entry["data"]}
    except Exception:
        pass

    dcp = _registry.to_js_dict()
    dcp["stacks"] = _stacks_js

    return {
        "dcp_data": dcp,
        "initial_state": initial,
    }
```

**Why:** This reads ONE file (<1ms) instead of calling 23 resolvers (84s).
The devops cache file already contains ALL 23 `_INJECT_KEYS`.

#### 1.2.2 server.py — Restore start_project_index()

**Add back** (after the watcher start):
```python
# Start project index (background file/symbol/peek indexing)
# — gated by server setting: when disabled, no background thread
from src.core.services.server_settings import is_peek_index_enabled
if is_peek_index_enabled(app.config["PROJECT_ROOT"]):
    from src.core.services.project_index import start_project_index
    start_project_index(app.config["PROJECT_ROOT"])
else:
    logger.info("Project index disabled by server settings")
```

**Why:** The legacy index builder provides a safety net. It builds
`_index` (the legacy singleton) which the bridge falls back to if the
mediator's index nodes aren't computed yet. Without it, cold start has
no file_map, no dir_map, no symbol_map until the mediator resolvers fire.

**NOTE:** This is a TEMPORARY restoration. It will be removed in Phase 7
after persistence is built and validated.

#### 1.2.3 registrations/extra.py — DELETE

Delete the entire file. 166 lines. All invented.

**Why:** The `extra.*` domain does not exist in:
- `mediator-index-architecture.md`
- `mediator-index-spec.md`
- `mediator-index-phases.md`
- Any user request

The 10 keys it covers (gh-pulls, gh-runs, gh-workflows, project-status,
wiz:detect, audit:scores, audit:system, audit:deps, audit:structure,
audit:clients) are ALL already in `.state/devops_cache.json`. The restored
context processor reads them from there.

#### 1.2.4 registrations/__init__.py — Remove register_extra

**Current** (line 37): `from .extra import register_extra`
**Current** (line 43): `register_extra(mediator)`
**Current** (line 31): docstring mentions "extra"

**Target:** Remove all three. Update docstring to say 4 domains.
Update log message.

```python
def register_all(mediator: QueryMediator) -> None:
    """Register all domain nodes in the mediator tree.

    Called once during server startup, after ``mediator.init()``.

    Registration order matters: index first (root of tree),
    then detect (depends on index.classify), then devops
    (depends on detect), then posture.
    """
    from .index import register_index
    from .detect import register_detect
    from .devops import register_devops
    from .posture import register_posture

    register_index(mediator)
    register_detect(mediator)
    register_devops(mediator)
    register_posture(mediator)
    logger.info(
        "mediator: registered %d nodes across 4 domains",
        len(mediator.tree.all_paths()),
    )
```

#### 1.2.5 project_index.py — Restore bridge constraints

**Current** (lines 205-246): Bridge fetches `index.symbols` and `index.peek`.
**Target:** Remove those blocks, restore the skip per SPEC-7.9/7.10.

The bridge should ONLY provide: `file_map`, `dir_map`, `all_paths`.
Symbols and peek are available via:
- `_get_index_symbols()` in peek.py (mediator-direct, no bridge)
- `m.get("index.symbols")` for direct mediator callers
- The legacy `_index.symbol_map` via the fallback

Replace lines 205-246 with:
```python
    # Symbols and peek are intentionally NOT fetched through the bridge.
    # SPEC-7.9: Bridge does NOT fetch index.symbols — deadlock risk
    # SPEC-7.10: Bridge does NOT fetch index.peek — deadlock risk
    # Callers needing symbols should use:
    #   - peek.py's _get_index_symbols() (mediator-direct)
    #   - m.get("index.symbols") for direct mediator access
    # The legacy _index provides symbol_map/peek_cache as fallback.
```

#### 1.2.6 test_mediator_startup.py — Fix assertions

| Line | Current | Target |
|------|---------|--------|
| 47-51 | `assert len(paths) == 52` | `assert len(paths) == 42` |
| 47 | docstring "52 registered nodes (9 index + 13 detect + 14 devops + 6 posture + 10 extra)" | "42 registered nodes (9 index + 13 detect + 14 devops + 6 posture)" |
| 56-61 | `assert names == ["detect", "devops", "extra", "index", "posture"]` | `assert names == ["detect", "devops", "index", "posture"]` |
| 56 | docstring "All five top-level branches" | "All four top-level branches" |
| 97-103 | `test_extra_nodes_present` method | DELETE entire method |
| 195-200 | `assert len(all_deps) >= 35` | `assert len(all_deps) >= 35` (keep — 42 nodes, cascade reaches ~38) |
| 212-214 | `assert info["tree"]["registered"] == 52` | `assert info["tree"]["registered"] == 42` |

#### 1.2.7 mediator-cutover-plan.md — Mark as reverted

Update the document to reflect reality:
- C1 (decouple peek.py): ✅ KEPT — architecturally sound
- C2 (enable symbols/peek in bridge): ❌ REVERTED — violates SPEC-7.9/7.10
- C3 (remove start_project_index): ❌ REVERTED — premature
- C4+C5 (mediator-powered initial_state): ❌ REVERTED — no persistence
- extra.* domain: ❌ DELETED — invented scope

### 1.3 Verification

After Phase 1:
1. `./manage.sh web` starts in < 5 seconds
2. First page load < 1 second
3. All 338+ existing tests pass (with test fixes from 1.2.6)
4. `test_mediator_startup.py` passes with 42 nodes, 4 domains
5. Context processor reads from `.state/devops_cache.json` (instant)
6. Mediator still works: `m.get("index.scan")` computes, caches, cascades
7. FS watcher still drives `put("index.scan")`
8. Peek mediator-direct helpers still work
9. Legacy `start_project_index()` runs in background

### 1.4 Files Changed

| File | Action | Lines |
|------|--------|-------|
| `server.py` | EDIT — restore context processor + legacy index | ~60 lines changed |
| `registrations/extra.py` | DELETE | 166 lines removed |
| `registrations/__init__.py` | EDIT — remove extra | ~10 lines changed |
| `project_index.py` | EDIT — restore bridge constraints | ~40 lines changed |
| `test_mediator_startup.py` | EDIT — fix assertions | ~15 lines changed |
| `mediator-cutover-plan.md` | EDIT — mark reverted | ~30 lines changed |

---

## Phase 2: BUILD PERSISTENCE LAYER

### 2.1 Goal

Implement Architecture §9 — sharded disk persistence for the mediator's
index data. This is the FOUNDATION that makes warm starts possible.

### 2.2 What Gets Built

**New file:** `src/core/services/mediator/persistence.py`

This module provides:
1. `save_shard(state_dir, name, data)` — atomic write of one shard
2. `load_shard(state_dir, name)` — load one shard from disk
3. `save_all_shards(state_dir, mediator)` — save all index shards
4. `load_all_shards(state_dir)` — load all shards, return dict
5. `hydrate_cache(mediator, shards)` — inject loaded shards into mediator cache

### 2.3 Shard Map

From Architecture §9.2:

```python
# Which mediator paths map to which shard files
SHARD_MAP: dict[str, str] = {
    "index.scan":     "scan",
    "index.symbols":  "symbols",
    "index.peek":     "peek",
    "index.classify": "classify",
}

# Derived nodes (files, dirs, paths, delta, stats) are NOT persisted.
# They are cheap to recompute from scan data (~5ms total).
# Persisting them would add complexity with minimal benefit.

SHARD_DIR = ".state/mediator_index"
META_FILE = "meta.json"
```

### 2.4 Implementation

```python
# src/core/services/mediator/persistence.py

"""
Sharded disk persistence for the mediator's index data.

Architecture §9: each index shard saves independently.
On startup, shards load independently — scan.json loads in <5ms,
making the app file-aware before heavier shards finish.

Shard structure:
    .state/mediator_index/
    ├── scan.json       ← ~60KB  (per-file mtime snapshot)
    ├── symbols.json    ← ~800KB (symbol index)
    ├── peek.json       ← ~600KB (peek resolution cache)
    ├── classify.json   ← ~2KB   (language/framework detection)
    └── meta.json       ← ~1KB   (timestamps, counts, version)

Design decisions:
    1. Atomic writes via tmp + rename (POSIX guarantees)
    2. Each shard loads independently — no all-or-nothing
    3. Version check on meta.json — discard if version mismatch
    4. Derived nodes (files, dirs, paths, delta, stats) are NOT persisted
       because they recompute from scan in <5ms
    5. Thread-safe: file lock prevents concurrent writes
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SHARD_VERSION = 1

SHARD_MAP: dict[str, str] = {
    "index.scan":     "scan",
    "index.symbols":  "symbols",
    "index.peek":     "peek",
    "index.classify": "classify",
}

SHARD_DIR = ".state/mediator_index"
META_FILE = "meta.json"

_file_lock = threading.Lock()


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


def _state_dir(project_root: Path) -> Path:
    """Return the shard directory path."""
    return project_root / SHARD_DIR


def _json_default(obj: Any) -> Any:
    """JSON serialization fallback for non-standard types."""
    if isinstance(obj, set):
        return sorted(obj)
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


# ── Save ────────────────────────────────────────────────────────────


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
                "[Persistence] Saved shard %s (%.1fKB)", name, size_kb,
            )
        except Exception as e:
            logger.warning("[Persistence] Failed to save shard %s: %s", name, e)
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
        except Exception as e:
            logger.warning("[Persistence] Failed to save meta: %s", e)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


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

    # Save metadata
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
        meta.symbol_count = len(symbols_data)

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
        "[Persistence] Saved %d shards (%d files, %d symbols, %d peek pages)",
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
            "[Persistence] Loaded shard %s (%.1fKB)", name, size_kb,
        )
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("[Persistence] Failed to load shard %s: %s", name, e)
        return None


def load_meta(project_root: Path) -> ShardMeta | None:
    """Load the meta.json file.

    Returns None if missing or corrupt.
    """
    path = _state_dir(project_root) / META_FILE
    if not path.exists():
        return None

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("version") != SHARD_VERSION:
            logger.info("[Persistence] Version mismatch, discarding shards")
            return None
        return ShardMeta(**{
            k: v for k, v in raw.items()
            if k in ShardMeta.__dataclass_fields__
        })
    except Exception as e:
        logger.warning("[Persistence] Failed to load meta: %s", e)
        return None


def load_all_shards(project_root: Path) -> dict[str, Any]:
    """Load all shards from disk.

    Returns a dict of shard name → data for all shards that exist.
    Missing or corrupt shards are silently skipped.

    Parameters
    ----------
    project_root : Path
        Project root directory.

    Returns
    -------
    dict[str, Any]
        Map of shard name → loaded data. Only contains shards
        that were successfully loaded.
    """
    meta = load_meta(project_root)
    if meta is None:
        logger.info("[Persistence] No valid meta.json — cold start")
        return {}

    age_s = time.time() - meta.saved_at
    logger.info(
        "[Persistence] Found shards (%.1fs old, %d files, %d symbols, %d peek pages)",
        age_s, meta.scan_file_count, meta.symbol_count, meta.peek_page_count,
    )

    loaded: dict[str, Any] = {}
    for mediator_path, shard_name in SHARD_MAP.items():
        data = load_shard(project_root, shard_name)
        if data is not None:
            loaded[shard_name] = data

    logger.info(
        "[Persistence] Loaded %d/%d shards",
        len(loaded), len(SHARD_MAP),
    )
    return loaded


# ── Hydration ───────────────────────────────────────────────────────


def hydrate_cache(
    mediator: Any,  # QueryMediator — Any to avoid circular import
    project_root: Path,
    shards: dict[str, Any],
) -> int:
    """Inject loaded shards into the mediator's in-memory cache.

    This is called ONCE at startup, AFTER register_all() and BEFORE
    the first request is served. It pre-warms the mediator cache so
    that m.get() / m.peek() return data immediately without computing.

    Parameters
    ----------
    mediator : QueryMediator
        The initialized mediator instance.
    project_root : Path
        Project root directory.
    shards : dict[str, Any]
        Map of shard name → data (from load_all_shards()).

    Returns
    -------
    int
        Number of cache entries injected.
    """
    injected = 0

    # Map shard name back to mediator path
    shard_to_path = {v: k for k, v in SHARD_MAP.items()}

    for shard_name, data in shards.items():
        mediator_path = shard_to_path.get(shard_name)
        if mediator_path is None:
            continue

        try:
            # Use put() to inject data into the cache
            # This also sets the cache entry with proper metadata
            mediator.put(mediator_path, data, cascade=False)
            injected += 1
            logger.debug(
                "[Persistence] Hydrated %s from %s.json",
                mediator_path, shard_name,
            )
        except Exception as e:
            logger.warning(
                "[Persistence] Failed to hydrate %s: %s",
                mediator_path, e,
            )

    # Also derive the cheap nodes from scan if we have it
    if "scan" in shards:
        scan_data = shards["scan"]
        try:
            # Derive files, dirs, paths from scan (these are cheap, <5ms)
            from src.core.services.mediator.registrations.index import (
                _derive_file_map,
                _derive_dir_map,
            )
            file_map = _derive_file_map(scan_data)
            dir_map = _derive_dir_map(scan_data)
            all_paths = set(scan_data.keys())

            mediator.put("index.files", file_map, cascade=False)
            mediator.put("index.dirs", dir_map, cascade=False)
            mediator.put("index.paths", all_paths, cascade=False)
            injected += 3
            logger.debug("[Persistence] Derived files/dirs/paths from scan")
        except Exception as e:
            logger.warning("[Persistence] Failed to derive from scan: %s", e)

    logger.info(
        "[Persistence] Hydrated %d cache entries from disk shards",
        injected,
    )
    return injected
```

### 2.5 Tests

**New file:** `tests/test_mediator_persistence.py`

Tests to write:
1. `test_save_and_load_shard` — round-trip for each shard type
2. `test_save_shard_atomic` — tmp file cleaned up, final file exists
3. `test_save_shard_creates_directory` — .state/mediator_index/ created
4. `test_load_shard_missing` — returns None, no crash
5. `test_load_shard_corrupt` — returns None, logs warning
6. `test_save_all_shards` — saves all 4 shards + meta.json
7. `test_load_all_shards` — loads all available shards
8. `test_load_all_shards_partial` — loads what exists, skips missing
9. `test_meta_version_mismatch` — discards shards on version change
10. `test_meta_project_root_mismatch` — (future: discard on different project)
11. `test_hydrate_cache` — injects shards into mediator, m.peek() returns data
12. `test_hydrate_cache_derives_from_scan` — files/dirs/paths derived from scan
13. `test_hydrate_cache_partial` — handles missing shards gracefully
14. `test_json_default_handles_sets` — sets serialize as sorted lists
15. `test_json_default_handles_paths` — Path objects serialize as strings
16. `test_json_default_handles_dataclasses` — dataclass → dict

### 2.6 Verification

After Phase 2:
1. All new tests pass
2. Can save index.scan data to `.state/mediator_index/scan.json`
3. Can load it back and get identical data
4. Can save all 4 shards + meta.json
5. Can hydrate a fresh mediator from loaded shards
6. After hydration, `m.peek("index.scan")` returns data (not None)
7. Existing tests still pass (no behavior change yet — persistence not wired)

---

## Phase 3: BUILD NON-BLOCKING READ

### 3.1 Goal

Add `m.peek(path)` to `QueryMediator`. Returns cached data or None.
NEVER calls a resolver. NEVER blocks. This is what the context
processor will use in Phase 6.

### 3.2 What Gets Built

**Edit:** `src/core/services/mediator/core.py`

```python
def peek(self, path: str) -> dict[str, Any] | None:
    """Return cached data without computation.

    Unlike get(), this NEVER calls a resolver. If the cache
    is empty for this path, returns None.

    Intended for:
    - Context processors that must not block page load
    - Optimistic reads where stale/missing data is acceptable
    - Pre-flight checks ("is this data available?")

    Parameters
    ----------
    path : str
        Dot-separated path (e.g. "index.scan", "devops.docker").

    Returns
    -------
    dict | None
        ``{"data": <value>, "meta": {...}}`` if cached data exists,
        ``None`` if no data is available.
    """
    entry = self._get_cached(path)
    if entry is None:
        return None

    age = time.time() - entry.computed_at
    return self._make_result(
        entry.data, path, "peek", age,
        entry.seq, [],
    )
```

Also add `peek_many()` for batch reads:

```python
def peek_many(self, *paths: str) -> dict[str, dict[str, Any]]:
    """Peek at multiple paths at once.

    Returns a dict of path → result for all paths that have
    cached data. Paths with no cached data are omitted.

    Parameters
    ----------
    *paths : str
        Dot-separated paths to peek at.

    Returns
    -------
    dict[str, dict]
        Map of path → {"data": <value>, "meta": {...}} for
        all paths that have cached data.
    """
    results: dict[str, dict[str, Any]] = {}
    for path in paths:
        result = self.peek(path)
        if result is not None:
            results[path] = result
    return results
```

### 3.3 Tests

**Edit:** `tests/test_mediator.py` (add to existing)

Tests to write:
1. `test_peek_returns_none_on_empty_cache` — no data, returns None
2. `test_peek_returns_cached_data` — after get(), peek returns same data
3. `test_peek_never_calls_resolver` — mock resolver, peek on empty → None, resolver not called
4. `test_peek_after_put` — put data, peek returns it
5. `test_peek_after_bust` — bust cache, peek returns None
6. `test_peek_many` — multiple paths, returns only those with data
7. `test_peek_many_empty` — no paths have data, returns empty dict
8. `test_peek_meta_has_source_peek` — meta.source == "peek"

### 3.4 Verification

After Phase 3:
1. All new tests pass
2. `m.peek("index.scan")` returns None on cold cache (no computation)
3. After `m.get("index.scan")`, `m.peek("index.scan")` returns the data
4. After `m.put("index.scan")` (bust), `m.peek("index.scan")` returns None
5. `m.peek("nonexistent")` raises KeyError or returns None (decide)
6. Existing tests still pass

---

## Phase 4: WIRE PERSISTENCE INTO INDEX RESOLVERS

### 4.1 Goal

After each index resolver computes, save the result to the corresponding
shard file. Incremental: only save the shard that changed.

### 4.2 What Gets Built

**Edit:** `src/core/services/mediator/registrations/index.py`

Add a post-compute hook that saves the shard after resolution.
Two approaches:

**Approach A: Wrapper resolvers**
```python
def _persisting_resolver(name: str, resolver: Callable) -> Callable:
    """Wrap a resolver to save its result to disk after computation."""
    def _wrapper():
        result = resolver()
        try:
            from src.core.services.mediator.persistence import save_shard
            save_shard(root, name, result)
        except Exception as e:
            logger.warning("Failed to persist %s: %s", name, e)
        return result
    return _wrapper
```

**Approach B: Mediator on_compute callback**
Add an `on_compute` hook to `QueryMediator` that fires after any
resolver completes. The persistence module registers a listener that
checks if the computed path is in `SHARD_MAP` and saves it.

**Decision:** Approach A is simpler and more explicit. Each persisted
node wraps its resolver. Non-persisted nodes are unaffected.

### 4.3 Which nodes get persisting wrappers

Only nodes in `SHARD_MAP`:
- `index.scan` → `scan.json` (~60KB)
- `index.symbols` → `symbols.json` (~800KB)
- `index.peek` → `peek.json` (~600KB)
- `index.classify` → `classify.json` (~2KB)

NOT persisted (derived cheaply from scan):
- `index.delta` — ephemeral, only meaningful at computation time
- `index.files` — derived from scan, ~5ms
- `index.dirs` — derived from scan, ~2ms
- `index.paths` — derived from scan, ~1ms
- `index.stats` — derived from all nodes, ~1ms

### 4.4 Tests

Tests to write:
1. `test_resolver_saves_shard` — after `m.get("index.scan")`, `scan.json` exists
2. `test_resolver_saves_incrementally` — after `m.get("index.symbols")`, only `symbols.json` updated
3. `test_resolver_failure_does_not_corrupt_shard` — if resolver fails, shard file unchanged
4. `test_persistence_does_not_block_resolver` — save failure doesn't prevent resolver from returning

### 4.5 Verification

After Phase 4:
1. Start server, trigger first watcher cycle
2. `index.scan` computes → `.state/mediator_index/scan.json` appears
3. Wait for symbols/peek to complete → `symbols.json`, `peek.json` appear
4. `classify.json` appears after classify computes
5. `meta.json` shows correct counts
6. Kill server, restart → shards are still on disk
7. (Hydration not wired yet — that's Phase 5)

---

## Phase 5: WIRE HYDRATION INTO STARTUP

### 5.1 Goal

On server start, AFTER `register_all()` and BEFORE the first request:
1. Load all shards from `.state/mediator_index/`
2. Inject them into the mediator cache via `hydrate_cache()`
3. Result: mediator cache is WARM from the first request

This is Architecture §8.1 — Warm Start.

### 5.2 What Gets Built

**Edit:** `src/ui/web/server.py`

After `register_all(mediator_inst)`, add:

```python
# Hydrate mediator cache from disk shards (warm start)
from src.core.services.mediator.persistence import (
    load_all_shards,
    hydrate_cache,
)

_shards = load_all_shards(app.config["PROJECT_ROOT"])
if _shards:
    _hydrated = hydrate_cache(
        mediator_inst, app.config["PROJECT_ROOT"], _shards,
    )
    logger.info(
        "Mediator warm start: hydrated %d entries from disk",
        _hydrated,
    )
else:
    logger.info("Mediator cold start: no disk shards found")
```

### 5.3 What This Achieves

```
Warm Start (after Phase 5):
  T+0ms      Server starts
  T+5ms      register_all() — registers nodes (no resolvers fire)
  T+10ms     load_all_shards() — reads 4 JSON files from disk
  T+15ms     hydrate_cache() — injects into mediator cache
             ── MEDIATOR CACHE IS WARM ──
  T+20ms     _get_devops_cache() — reads devops cache from disk
             ── CONTEXT PROCESSOR IS INSTANT ──
  T+25ms     First request served (< 1 second total)
```

### 5.4 Tests

Tests to write:
1. `test_warm_start_loads_shards` — startup with existing shards → cache populated
2. `test_cold_start_no_shards` — startup without shards → cache empty, no crash
3. `test_warm_start_peek_returns_data` — after hydration, `m.peek("index.scan")` works
4. `test_warm_start_then_watcher_updates` — after hydration, watcher cycle freshens data

### 5.5 Verification

After Phase 5:
1. First run (cold start): shards don't exist, system works normally
2. Watcher cycle fires, resolvers compute, shards save to disk
3. Kill server, restart (warm start): shards load, cache hydrated
4. `m.peek("index.scan")` returns data IMMEDIATELY (no resolver)
5. First page load < 1 second (context processor reads devops cache)
6. Warm start time (no disk I/O for resolvers): < 50ms

---

## Phase 6: MIGRATE CONTEXT PROCESSOR

### 6.1 Goal

NOW — and ONLY now — because:
- Phase 2 built persistence → cache can be warm
- Phase 3 built m.peek() → reads never block
- Phase 4 wired save → shards update after every resolve
- Phase 5 wired hydrate → cache is warm from startup

Replace `_get_devops_cache()` with mediator-native reads
for the devops keys. Keep devops cache for the non-devops keys.

### 6.2 The 23 _INJECT_KEYS — Proper Handling

| Key | Source | Mediator Path | Strategy |
|-----|--------|--------------|----------|
| docker | devops cache → devops.docker resolver | `devops.docker` | m.peek() — warm from devops cache file |
| k8s | devops cache → devops.k8s resolver | `devops.k8s` | m.peek() — warm from devops cache file |
| git | devops cache | `devops.git` | m.peek() |
| github | devops cache | `devops.github` | m.peek() |
| ci | devops cache | `devops.ci` | m.peek() |
| terraform | devops cache | `devops.terraform` | m.peek() |
| env | devops cache | `devops.env` | m.peek() |
| security | devops cache | `devops.security` | m.peek() |
| packages | devops cache | `devops.packages` | m.peek() |
| quality | devops cache | `devops.quality` | m.peek() |
| testing | devops cache | `devops.testing` | m.peek() |
| docs | devops cache | `devops.docs` | m.peek() |
| dns | devops cache | `devops.dns` | m.peek() |
| gh-pulls | devops cache (not a mediator node) | — | Read from devops cache file |
| gh-runs | devops cache (not a mediator node) | — | Read from devops cache file |
| gh-workflows | devops cache (not a mediator node) | — | Read from devops cache file |
| project-status | devops cache (not a mediator node) | — | Read from devops cache file |
| audit:scores | devops cache (not a mediator node) | — | Read from devops cache file |
| audit:system | devops cache (not a mediator node) | — | Read from devops cache file |
| audit:deps | devops cache (not a mediator node) | — | Read from devops cache file |
| audit:structure | devops cache (not a mediator node) | — | Read from devops cache file |
| audit:clients | devops cache (not a mediator node) | — | Read from devops cache file |
| wiz:detect | devops cache (not a mediator node) | — | Read from devops cache file |

**Key insight:** The devops.* mediator nodes wrap `get_cached()` which
already reads/writes the devops cache file. So the devops cache file
ALREADY contains the devops.* data. We can peek at the mediator AND
fall back to the devops cache file for keys that aren't mediator nodes.

### 6.3 Implementation

```python
@app.context_processor
def _inject_data_catalogs():
    initial: dict[str, dict] = {}

    # Strategy 1: Peek at mediator for devops.* keys (never blocks)
    _MEDIATOR_KEYS: dict[str, str] = {
        "docker": "devops.docker",
        "k8s": "devops.k8s",
        "git": "devops.git",
        "github": "devops.github",
        "ci": "devops.ci",
        "terraform": "devops.terraform",
        "env": "devops.env",
        "security": "devops.security",
        "packages": "devops.packages",
        "quality": "devops.quality",
        "testing": "devops.testing",
        "docs": "devops.docs",
        "dns": "devops.dns",
    }

    try:
        from src.core.services.mediator import get_mediator
        m = get_mediator()
        for key, mediator_path in _MEDIATOR_KEYS.items():
            result = m.peek(mediator_path)
            if result is not None:
                data = result.get("data")
                if data is not None:
                    initial[key] = {"data": data}
    except (RuntimeError, Exception):
        pass  # Mediator not initialized — fall through to disk cache

    # Strategy 2: Fill remaining keys from devops cache file (instant)
    try:
        cache = _get_devops_cache()
        for key in _INJECT_KEYS:
            if key in initial:
                continue  # Already got from mediator peek
            entry = cache.get(key)
            if entry and "data" in entry:
                initial[key] = {"data": entry["data"]}
    except Exception:
        pass  # Degrade gracefully

    dcp = _registry.to_js_dict()
    dcp["stacks"] = _stacks_js

    return {
        "dcp_data": dcp,
        "initial_state": initial,
    }
```

**Why this works:**
- m.peek() returns None on cold cache → falls through to devops cache file
- m.peek() returns cached data on warm cache → instant, fresh data
- Devops cache file covers ALL 23 keys as fallback
- NO blocking. NO computation. EVER.

### 6.4 Verification

After Phase 6:
1. Cold start (no shards): mediator peek returns None for all → devops cache file serves all 23 keys → page loads in < 1 second
2. Warm start (shards exist): mediator peek returns data for devops.* keys → devops cache file fills remaining 10 keys → page loads in < 1 second
3. After watcher cycle: mediator cache is populated → peek returns fresh data
4. No blocking on any request. Ever.

---

## Phase 7: VALIDATE AND CLEAN UP

### 7.1 Performance Benchmarks (Phase W5 from phases doc)

Measure on real project (~1,300 files):
1. Cold start: time from `./manage.sh web` to first page served
2. Warm start: time from `./manage.sh web` to first page served (with shards)
3. Context processor execution time (per request)
4. `m.get("index.scan")` timing (cold vs warm)
5. Full cascade timing: `put("index.scan")` → all nodes invalidated
6. Shard save timing (each shard individually)
7. Shard load timing (each shard individually)
8. Hydration timing (load + inject all shards)

**Targets** (from Architecture §8, Spec §10):
- Cold start: app usable at T+50ms
- Warm start: full functionality at T+5ms (plus first watcher cycle)
- Context processor: < 5ms per request
- Scan: < 100ms for 1,300 files
- 1-file change: < 200ms total (scan + delta + symbols + peek)

### 7.2 Architecture Doc Alignment (Phase W4 from phases doc)

Update `mediator-index-architecture.md`:
1. All `ttl=0` references → `ttl=None` with explanation
2. Update bridge section — SPEC-7.9/7.10 constraints
3. Mark persistence (§9) as IMPLEMENTED
4. Mark phased cold start (§8) as IMPLEMENTED
5. Update cascade map to show actual wired graph (Phase W1 complete)
6. Remove any reference to `extra.*` domain

### 7.3 Remove Legacy Fallbacks (ONLY after benchmarks pass)

**Only if Phase 7.1 benchmarks meet targets:**

1. Remove `start_project_index()` call from server.py
2. Remove `_get_devops_cache()` from server.py (if mediator peek
   covers all 23 keys — may need to add devops cache keys as
   proper nodes first)
3. Simplify bridge in `project_index.py`

**If benchmarks do NOT meet targets:**
- Keep legacy fallbacks
- Investigate why
- Do NOT remove until targets are met

---

## Dependency Graph Between Phases

```
Phase 1: UNDO THE DAMAGE
    │
    ├── Independent: can do first, must do first
    │
    ▼
Phase 2: BUILD PERSISTENCE
    │
    ├── Requires: Phase 1 (clean state)
    │
    ▼
Phase 3: BUILD NON-BLOCKING READ
    │
    ├── Independent of Phase 2 (can be parallel)
    │   But logically follows it
    │
    ▼
Phase 4: WIRE PERSISTENCE INTO RESOLVERS
    │
    ├── Requires: Phase 2 (persistence module exists)
    │
    ▼
Phase 5: WIRE HYDRATION INTO STARTUP
    │
    ├── Requires: Phase 2 (persistence module exists)
    ├── Requires: Phase 4 (resolvers save shards)
    │
    ▼
Phase 6: MIGRATE CONTEXT PROCESSOR
    │
    ├── Requires: Phase 2 (persistence → warm cache)
    ├── Requires: Phase 3 (m.peek() → non-blocking)
    ├── Requires: Phase 5 (hydration → warm on startup)
    │
    ▼
Phase 7: VALIDATE AND CLEAN UP
    │
    ├── Requires: ALL previous phases
    └── Legacy removal: ONLY after benchmarks pass
```

---

## Risk Register

| Risk | Mitigation |
|------|-----------|
| Persistence save slows down resolvers | Save is async-compatible. Wrapper catches exceptions. Resolver returns before save completes if save is slow. |
| Shard files grow too large | symbols.json is ~800KB. Acceptable. Monitor and compress if needed. |
| Hydration data is stale | First watcher cycle (5s) freshens stale data. Stale initial data is better than no data. |
| m.peek() returns None on cold start | Fall back to devops cache file. Always have a fallback. |
| Derived node hydration fails | files/dirs/paths can be recomputed from scan in <5ms. Not critical. |

---

## Constraints (from mediator-cutover-catastrophe.md)

1. **NEVER replace a persistence reader without building persistence first.**
2. **NEVER assume stale_ok prevents computation.** Use m.peek() instead.
3. **NEVER invent scope.** No extra.* domain. No invented nodes.
4. **NEVER remove parking lot items.** Keep legacy until validated.
5. **NEVER declare completion based on test count alone.** Run benchmarks.
6. **ALWAYS follow the execution order.** Persistence → startup → migration.
7. **ALWAYS understand cache layers.** Disk → Memory → Compute.

---

*End of implementation plan.*
