# Passive Project Index — Analysis & Implementation Plan

> **Status**: ✅ PHASES 1-5 IMPLEMENTED — Phase 5 (status endpoint) deferred
> **Created**: 2026-03-05
> **Scope**: Core service + peek integration + API update
> **Motivation**: Peek resolve takes 500ms+ per request (20s cold start). Must be instant.
>
> **Actual results from implementation:**
> - Disk cache load: **29ms** (was 24,681ms cold build)
> - Disk cache size: **1,286KB**
> - Files indexed: **1,138** | Dirs: **211** | Symbols: **2,511** | Peek pages: **211**
> - File index build: **38ms** | Symbol index: **23,032ms** | Peek cache: **1,600ms**

---

## Problem Statement

### Current Flow (per peek-resolve request)

```
Client → POST /api/content/peek-resolve { doc_path, content }
                                           │
Server receives full file content (wasteful — server has the file on disk)
                                           │
  1. build_symbol_index()       → 20,000ms first call (cached in-memory only)
  2. _build_filename_index()    → 272ms EVERY CALL (rglob of subtree, no cache)
  3. scan_peek_candidates()     → ~30ms (regex)
  4. resolve_peek_candidates()  → ~200ms (filesystem stat per candidate)
                                           │
Total cold start: ~20,500ms
Total warm:       ~500ms
No disk cache → every server restart pays the 20s bill again.
```

### Target Flow (with passive index + disk cache)

```
Server start
    │
    ├─ Load index from disk (.state/project_index.json)    → ~100ms
    │    └─ ready = True immediately (peek can serve from cache)
    │
    ├─ Background thread: validate + rebuild if stale       → ~20s (non-blocking)
    │    └─ Write updated index to disk automatically
    │
Client → GET /api/content/peek-refs?path=src/core/README.md
                                           │
Server looks up pre-computed results from in-memory index
                                           │
Total: ~5ms (dict lookup, zero I/O)
```

---

## Architecture

### New Service: `src/core/services/project_index.py`

A **background-built, disk-cached, in-memory index** of the project's filesystem and symbols.

```
ProjectIndex (singleton)
│
├─ In-Memory (hot data, fast reads)
│   ├── file_map:     { "action.py": ["src/core/models/action.py", ...] }
│   ├── dir_map:      { "audit": ["src/core/services/audit", ...] }
│   ├── all_paths:    set[str]       ← every relative path (instant exists check)
│   ├── symbol_map:   { "DataRegistry": [SymbolEntry(...), ...] }
│   └── peek_cache:   { "src/core/README.md": { "resolved": [...], "unresolved": [...] } }
│
├─ Disk Cache (cold storage, survives restarts)
│   └── .state/project_index.json
│       ├── version:       int            ← schema version for safe migration
│       ├── project_root:  str            ← validates cache belongs to THIS project
│       ├── built_at:      float          ← when last full build completed
│       ├── mtime_sig:     float          ← max mtime at build time (stale check)
│       ├── build_ms:      int            ← how long the build took
│       ├── file_map:      { ... }
│       ├── dir_map:       { ... }
│       ├── all_paths:     [...]          ← serialized as list
│       ├── symbol_map:    { ... }        ← serialized SymbolEntry dicts
│       └── peek_cache:    { ... }
│
└─ State
    ├── ready:         bool   ← False until first usable data exists
    ├── building:      bool   ← True while build is in progress
    ├── last_built:    float  ← timestamp
    └── build_time_ms: int    ← for observability
```

### Lifecycle

```
Server startup (create_app)
    │
    ├─ start_project_index(project_root)
    │    │
    │    ├─ STEP 1: Load disk cache (.state/project_index.json)
    │    │    ├─ If valid cache exists + mtime_sig is fresh:
    │    │    │    ├─ Load into memory (~100ms)
    │    │    │    └─ ready = True ← INSTANT peek on first request
    │    │    │
    │    │    └─ If no cache or stale:
    │    │         └─ Continue to Step 2 (background build)
    │    │
    │    ├─ STEP 2 (background thread): Build file_map + dir_map + all_paths
    │    │    ├─ Single rglob of project root (~300ms)
    │    │    ├─ Skip: .git, __pycache__, node_modules, .venv, build, dist
    │    │    ├─ ready = True (even if symbols not done yet)
    │    │    └─ Write partial cache to disk
    │    │
    │    ├─ STEP 3 (background thread): Build symbol_map
    │    │    ├─ Parse all .py files via AST parser registry (~20s)
    │    │    └─ symbols_ready = True
    │    │
    │    ├─ STEP 4 (background thread): Pre-compute peek_cache
    │    │    ├─ Walk all .md files in project
    │    │    ├─ Run scan_and_resolve_all() for each
    │    │    └─ peek_cached = True ← all-instant responses now
    │    │
    │    └─ STEP 5: Write complete cache to disk
    │         └─ .state/project_index.json (full snapshot)
    │
    └─ Server ready (no startup delay)
```

### Stale Detection

```
How do we know the cache is stale?

mtime_sig = max mtime across sentinel paths:
    - src/           (any source change)
    - docs/          (any doc change)
    - pyproject.toml (dependency change)
    - project.yml    (config change)

On load from disk:
    current_mtime_sig = _max_mtime(project_root, SENTINEL_PATHS)
    if current_mtime_sig > cached.mtime_sig:
        → stale, rebuild in background (but still load stale cache for immediate use)
    else:
        → fresh, use as-is
```

### Invalidation Strategy

```
v1 (simple): Timer-based refresh
    - Every 60s: check mtime_sig
    - If changed: rebuild affected caches in background
    - Publish event_bus "index:stale" → client can show indicator

v2 (future): Event-driven
    - Content save API → invalidate that file's peek_cache entry
    - staleness_watcher events → trigger index refresh
    - Git operations → full rebuild
```

---

## Phased Delivery

### Phase 1 — Core Index Service + Disk Cache

**Create** `src/core/services/project_index.py`

Contents:
- `ProjectIndex` class with all data fields + state flags
- `_build_file_index(project_root)` → rglob once → file_map + dir_map + all_paths
- `_build_symbol_index(project_root)` → reuse existing parser registry
- `_build_peek_cache(project_root)` → scan_and_resolve_all for all .md files
- `_save_to_disk(project_root)` → write .state/project_index.json
- `_load_from_disk(project_root)` → read + validate cache
- `_mtime_signature(project_root)` → max mtime of sentinel paths
- `get_index()` → returns the singleton instance
- `start_project_index(project_root)` → load cache (instant) + launch background daemon
- Thread phases: load disk → file index → symbols → peek cache → save disk

**Disk cache location**: `.state/project_index.json` (already gitignored via `.state/`)

### Phase 2 — Wire Into Server Startup

**Modify** `src/ui/web/server.py`

Add after staleness watcher start:
```python
from src.core.services.project_index import start_project_index
start_project_index(app.config["PROJECT_ROOT"])
```

### Phase 3 — Peek Resolver Uses Index

**Modify** `src/core/services/peek.py`

- `_build_filename_index()` → check `get_index().file_map` first. If ready, use it. If not, fallback to rglob.
- `build_symbol_index()` → check `get_index().symbol_map` first. If ready, return it. If not, fallback to on-demand.
- `_resolution_candidates()` → use `get_index().all_paths` for instant `in` checks instead of filesystem stat calls.

**Key principle**: graceful fallback. If index not ready, current on-demand code still works.

### Phase 4 — New GET Endpoint + Client Update

**Modify** `src/ui/web/routes/content/peek.py`

- New endpoint: `GET /api/content/peek-refs?path=<doc_path>`
- Looks up `peek_cache[doc_path]` → instant JSON response
- Falls back to on-demand resolution if not cached
- Old POST endpoint kept (backward compat, Docusaurus build still uses it)

**Modify** `src/ui/web/templates/scripts/content/_preview.html`

- `_resolvePeekLinks()` → GET with path only, no content transfer
- Fallback: if GET returns empty/error, use old POST method

### Phase 5 — Refresh + Observability

- Refresh timer in the daemon thread: every 60s check mtime_sig
- If stale: rebuild in background, update disk cache
- On content save (file write via API): invalidate that path's peek_cache entry
- Publish events: `index:building`, `index:ready`, `index:stale`
- Status endpoint: `GET /api/project-index/status`
  → ready, building, last_built, build_time_ms, file_count, symbol_count, peek_page_count

---

## Files Modified

```
NEW:
  src/core/services/project_index.py            ← THE index service

MODIFIED:
  src/ui/web/server.py                          ← start_project_index() call
  src/core/services/peek.py                     ← use index instead of per-request I/O
  src/ui/web/routes/content/peek.py             ← new GET endpoint
  src/ui/web/templates/scripts/content/
    _preview.html                               ← GET instead of POST for peek

CACHE FILE (auto-generated, gitignored):
  .state/project_index.json                     ← persistent disk cache
```

---

## Performance Expectations

| Metric | Before | After (cold, no disk cache) | After (warm, disk cache) |
|--------|--------|----------------------------|--------------------------|
| Server start → peek ready | 20,500ms | ~300ms (file index) | ~100ms (disk load) |
| Peek request latency | 500ms | ~5ms | ~5ms |
| Content transfer | Full file body in POST | None (GET path only) | None |
| Server restart cost | 20s (rebuild from scratch) | ~100ms (load disk cache) | ~100ms |
| Memory cost | 0 (rebuilt per request) | ~5-10MB | ~5-10MB |
| Disk cost | 0 | ~2-5MB (.state/project_index.json) | ~2-5MB |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Index not ready on first request | Graceful fallback to current on-demand resolution |
| Stale index after file edits | Timer refresh + content-save invalidation |
| Stale disk cache after git pull | mtime_sig comparison on load → background rebuild |
| Memory footprint | file_map for 80K files ≈ 5MB — acceptable for dev tool |
| Thread safety | Index is write-once per build cycle; atomic dict swap on completion |
| Large project_index.json | Estimate: ~2-5MB for 80K files + 2.5K symbols + 100 peek pages |
| Schema migration | version field in JSON — if version mismatch, discard + rebuild |

---

## Design Decisions

1. **Disk cache = instant restart**: The 20s symbol build only happens once. Every subsequent server restart loads from `.state/project_index.json` in ~100ms.

2. **Load stale cache → rebuild in background**: Even if the disk cache is outdated, load it immediately for fast first response, then rebuild in the background. User sees results right away (possibly slightly stale) and gets fresh results within seconds.

3. **GET not POST**: Client sends only the path. Server owns the files. No content transfer.

4. **Follows existing patterns**: Same location (`.state/`), same daemon thread pattern (`staleness_watcher`), same event bus integration (`event_bus`). No new infrastructure.

5. **Graceful degradation**: If index not ready → fallback to current on-demand. If disk cache corrupt → discard and rebuild. No request ever fails.

6. **mtime_sig for stale detection**: Single `max mtime` check across a few sentinel paths — same pattern as `devops/cache.py`'s `_max_mtime()`. ~1ms cost.

7. **Phased build order**: File map first (300ms, enables basic resolution), symbols later (20s, enables T5), peek cache last (5s, enables instant responses). Each phase unlocks a level of capability.
