# Mediator-Native Index — Definitive Spec

> **Purpose:** This is the contract. Every requirement is testable.
> The architecture doc is the vision — this is the definition of done.
> **Created:** 2026-03-12
> **Origin:** User's trilateral communication system concept

---

## 0. The Origin — Quoted Verbatim

> WE lets visualize the cache tree and index map and see what we are
> missing and think inner plan communication. how we call this again?
> trilateral communication. yup.. it magically came to me, this is
> going to be a trilateral com system which will allow to optimize
> everything. a bit like a zookeeper of our marvel.
>
> Something like this:
> Backend  → Mediator
> Cache    → Mediator
> Index    → Mediator
>
> Allow ourself to build a tree with multiple layers of branches
> before the leaves. There is no need to reset the whole, you always
> just get the delta, the new and or the fresh.
> No need to spiral into the spaghetti to reach the goal, you declare
> it at the top, a real strong index with in this case connection to
> fs watcher for the project folder.
> the mediator just give you anything you want and it is the data
> central hub so you can connect to everything. even the deepest
> layers of the indexes. Trees and Indexes.
>
> Its mostly about the bottom up. index sitting at the bottom, we want
> to make this graceful and strong and everything that connect to it
> and create a system/module that mediate this need.
> Doing this properly we would be able to loadbalance all operations
> in order to reduce duration / increase the speed of scan and such
> from result of data or tool output and call so that everywhere the
> timing can decrease by at least half via a proper data hub.

---

## 1. Trilateral Identity

The mediator is a trilateral data hub. Three pillars. All equal.
All routed through the same mediator instance.

```
┌─────────────────────────────────────────────────┐
│                   QueryMediator                  │
│                                                  │
│   ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│   │ Backend  │  │  Cache   │  │    Index     │  │
│   │          │  │          │  │              │  │
│   │ detect.* │  │ TTL-based│  │ index.scan   │  │
│   │ devops.* │  │ staleness│  │ index.delta  │  │
│   │ posture.*│  │ bust()   │  │ index.files  │  │
│   │          │  │ put()    │  │ index.symbols│  │
│   │          │  │ refresh()│  │ index.peek   │  │
│   └────┬─────┘  └────┬─────┘  └──────┬───────┘  │
│        │             │               │           │
│        └─────────────┼───────────────┘           │
│                      │                           │
│               get() / put()                      │
│               cascade / subscribe                │
│               diag / explain                     │
└─────────────────────────────────────────────────┘
```

### SPEC-1: Three pillars exist as registered node branches

| ID | Requirement | Test |
|----|-------------|------|
| 1.1 | `index.*` nodes are registered in the mediator tree | `mediator.diag()` lists all `index.*` paths |
| 1.2 | `detect.*` nodes are registered in the mediator tree | Already done (Phase 2) |
| 1.3 | `devops.*` nodes are registered in the mediator tree | Already done (Phase 3) |
| 1.4 | `posture.*` nodes are registered in the mediator tree | Already done (Phase 1) |
| 1.5 | All three pillars share the same `QueryMediator` instance | One `get_mediator()` singleton returns the shared instance |
| 1.6 | All three pillars use the same `get()`/`put()`/`bust()` API | No custom access paths — everything goes through the mediator |

---

## 2. Index Nodes — The Root of the Tree

The index is the foundation. Nine nodes. Each with a clear contract.

### SPEC-2: Node registry

| ID | Node | Resolver produces | Depends on | Invalidation |
|----|------|-------------------|------------|--------------|
| 2.1 | `index.scan` | `dict[str, FileEntry]` — every file with mtime, size, ext | None (root) | `put("index.scan")` from watcher |
| 2.2 | `index.delta` | `ScanDelta` — added, removed, modified lists | `index.scan` | Cascade from scan |
| 2.3 | `index.files` | `dict[str, list[str]]` — filename → list of paths | `index.scan` | Cascade from scan |
| 2.4 | `index.dirs` | `dict[str, list[str]]` — dirname → list of paths | `index.scan` | Cascade from scan |
| 2.5 | `index.paths` | `set[str]` — flat set of all relative paths | `index.scan` | Cascade from scan |
| 2.6 | `index.symbols` | `dict[str, list[IndexSymbolEntry]]` — symbol name → locations | `index.delta` | Cascade from delta |
| 2.7 | `index.peek` | `dict[str, dict]` — doc path → resolved/unresolved refs | `index.delta`, `index.symbols` | Cascade from delta |
| 2.8 | `index.classify` | `dict` — languages, frameworks, primary_language, extensions | `index.scan` | Cascade from scan |
| 2.9 | `index.stats` | `dict` — file_count, dir_count, symbol_count, etc. | all index nodes | Cascade from any |

### SPEC-2 tests

| ID | Requirement | Test |
|----|-------------|------|
| 2.10 | All 9 nodes exist | `mediator.diag()["entries"]` contains all 9 `index.*` paths |
| 2.11 | Each node's resolver returns the documented type | Call `m.get("index.X")["data"]` → `isinstance()` check |
| 2.12 | Dependency chain is correctly declared | Check `depends_on` in registration matches the table above |
| 2.13 | No circular dependencies | Traversing the dependency graph terminates |

---

## 3. Caching Semantics

Index nodes are **watcher-driven**. They cache their result after first
computation and only recompute when explicitly invalidated.

### SPEC-3: Caching

| ID | Requirement | Test |
|----|-------------|------|
| 3.1 | Index nodes use event-driven invalidation, not TTL expiration | All index nodes have `ttl=None` (cache forever) |
| 3.2 | First `get()` computes and caches | `m.get("index.scan")` → source="computed"; second `m.get("index.scan")` → source="cache" |
| 3.3 | Cached result is returned without re-running resolver | Verify resolver is NOT called on second `get()` |
| 3.4 | `put("index.scan")` invalidates scan AND all dependents | After `put()`, all 9 cache entries are removed |
| 3.5 | After invalidation, next `get()` recomputes | `put("index.scan")` → `m.get("index.delta")` → source="computed" |
| 3.6 | No infinite recomputation loops | Starting the server produces ≤1 scan log line per watcher cycle |

---

## 4. Incremental Processing

The index processes only changes, never the whole.

### SPEC-4A: Scan + Delta

| ID | Requirement | Test |
|----|-------------|------|
| 4.1 | `scan_project()` walks all non-hidden files and returns `FileEntry` per file | Scan a tmp project, verify all visible files are present |
| 4.2 | `diff_scans()` detects added files | Add a file → diff → `delta.added` contains it |
| 4.3 | `diff_scans()` detects removed files | Remove a file → diff → `delta.removed` contains it |
| 4.4 | `diff_scans()` detects modified files (by mtime) | Touch a file → diff → `delta.modified` contains it |
| 4.5 | Empty delta when nothing changed | Two identical scans → `delta.empty is True` |
| 4.6 | Delta state persists across calls (accumulator keeps prev_scan) | First call = all added; invalidate + no changes; second call = empty delta |

### SPEC-4B: Incremental Symbols

| ID | Requirement | Test |
|----|-------------|------|
| 4.7 | Cold start parses all `.py` files | Empty accumulator → parse all → returns all symbols |
| 4.8 | Empty delta skips parsing | `delta.empty` → returns existing accumulator unchanged |
| 4.9 | Added `.py` file → parsed and merged | Add file → symbols contain new file's defs |
| 4.10 | Modified `.py` file → old symbols purged, new parsed | Modify → old symbols gone, new ones present |
| 4.11 | Removed `.py` file → its symbols purged | Remove → symbols from that file are gone |
| 4.12 | Non-Python files are skipped | `.md`, `.yml` in delta → no parse attempted |

### SPEC-4C: Incremental Peek

| ID | Requirement | Test |
|----|-------------|------|
| 4.13 | Cold start peeks all `.md` files | Empty accumulator → peek all → returns all pages |
| 4.14 | Empty delta returns cached | `delta.empty` → returns existing accumulator unchanged |
| 4.15 | Modified `.md` file → only that page re-peeked | One MD changed → only that entry updated |
| 4.16 | Removed `.md` file → purged from cache | Remove MD → gone from result |
| 4.17 | Source file change → re-peek all MD (symbols may have changed) | `.py` changed → all MD pages re-peeked |

---

## 5. FS Watcher — The Pulse

The watcher is the only thing that drives index invalidation.
No polling inside the mediator. The watcher polls the filesystem
and tells the mediator when something changed.

### SPEC-5: Watcher

| ID | Requirement | Test |
|----|-------------|------|
| 5.1 | Watcher polls directory mtimes at configurable interval | Watcher runs, checks `~241` dir mtimes |
| 5.2 | When dir mtime changes → `mediator.put("index.scan")` | Mock mediator → verify `put()` called |
| 5.3 | `put("index.scan")` cascades → all 8 dependent nodes invalidated | After put, all nodes need recomputation |
| 5.4 | No change → no `put()` call | Stable filesystem → watcher stays silent |
| 5.5 | Watcher runs as daemon thread | Thread is daemon, name is identifiable |
| 5.6 | Watcher skips hidden dirs, `node_modules`, `.venv`, `__pycache__` | Skip rules match scan skip rules |

---

## 6. Cascade — Index as Root of Everything

**This is the core of the trilateral system.** File changes at the
bottom propagate all the way up through detect → devops → posture.

### SPEC-6: Downstream wiring

| ID | Requirement | Test |
|----|-------------|------|
| 6.1 | `detect.*` nodes declare `depends_on: ["index.classify"]` | Check registration: `detect.docker.depends_on` includes `index.classify` |
| 6.2 | `put("index.scan")` cascade reaches `detect.*` nodes | After `put("index.scan")`, `detect.docker` cache is invalidated |
| 6.3 | `put("index.scan")` cascade reaches `devops.*` nodes | After `put("index.scan")`, `devops.*` cache is invalidated |
| 6.4 | `put("index.scan")` cascade reaches `posture.*` nodes | After `put("index.scan")`, `posture.*` cache is invalidated |
| 6.5 | Full cascade depth is: scan → delta → symbols → peek → classify → detect → devops → posture | `m._tree.dependents("index.scan")` returns paths from all 4 domains |
| 6.6 | Single file change → entire system is coherent | Edit a file → watcher → cascade → all nodes freshen on next access |

### The cascade map (SPEC-6 reference)

```
index.scan (root)
  ├── index.delta
  │     ├── index.symbols
  │     │     └── index.peek
  │     └── (future: more consumers)
  ├── index.files
  ├── index.dirs
  ├── index.paths
  ├── index.classify
  │     ├── detect.docker      ← MUST depend on index.classify
  │     ├── detect.k8s         ← MUST depend on index.classify
  │     ├── detect.ci          ← MUST depend on index.classify
  │     ├── detect.terraform   ← MUST depend on index.classify
  │     ├── detect.git         ← MUST depend on index.classify
  │     └── ... (all detect.*)
  │           ├── devops.* nodes
  │           │     └── posture.* nodes
  │           └── ...
  └── index.stats
```

---

## 7. Backwards Compatibility Bridge

During transition, existing callers of `project_index.get_index()`
must continue to work.

### SPEC-7: Bridge

| ID | Requirement | Test |
|----|-------------|------|
| 7.1 | `get_index()` returns a `ProjectIndex` with `ready=True` when mediator is available | Call `get_index()` with mediator initialized → `ready is True` |
| 7.2 | `get_index()` populates `file_map` from `index.files` | `idx.file_map` contains expected filenames |
| 7.3 | `get_index()` populates `dir_map` from `index.dirs` | `idx.dir_map` contains expected dir names |
| 7.4 | `get_index()` populates `all_paths` from `index.paths` | `idx.all_paths` is a non-empty set |
| 7.5 | `get_index()` populates `file_count` from scan data | `idx.file_count > 0` |
| 7.6 | `get_index()` falls back to legacy `_index` when mediator is not initialized | Set mediator=None → `idx.ready is False` |
| 7.7 | No deadlocks from circular calls | `get_index()` can be called from within any mediator resolver without hanging |
| 7.8 | Re-entrancy guard prevents recursive bridge calls | Bridge called from within peek resolver → returns legacy `_index`, no deadlock |

### SPEC-7 constraints (what the bridge does NOT do)

| ID | Constraint | Reason |
|----|-----------|--------|
| 7.9 | Bridge does NOT fetch `index.symbols` | Deadlock risk: symbols → delta → scan chain + per-path compute lock |
| 7.10 | Bridge does NOT fetch `index.peek` | Deadlock risk: peek → `peek.py` → `get_index()` → `m.get("index.peek")` → same lock |
| 7.11 | Callers needing symbols/peek should use mediator directly | `m.get("index.symbols")`, `m.get("index.peek")` |

---

## 8. Observability — Dashboard

The index must be visible, inspectable, and operable from the UI.

### SPEC-8A: API endpoints

| ID | Endpoint | Returns | Test |
|----|----------|---------|------|
| 8.1 | `GET /api/mediator/index/status` | Aggregated summary: files, dirs, symbols, peek_pages, languages, frameworks, node health | HTTP 200 with all fields |
| 8.2 | `GET /api/mediator/index/delta` | Current delta: added, removed, modified, empty, timestamp | HTTP 200 with delta shape |
| 8.3 | `POST /api/mediator/index/rescan` | Force invalidate `index.scan` → cascade → refresh result | HTTP 200, `index.scan` recomputed |
| 8.4 | `POST /api/mediator/index/rebuild-symbols` | Force refresh `index.symbols` | HTTP 200 |
| 8.5 | `POST /api/mediator/index/rebuild-peek` | Force refresh `index.peek` | HTTP 200 |

### SPEC-8B: Generic mediator endpoints (already exist)

| ID | Endpoint | Purpose |
|----|----------|---------|
| 8.6 | `GET /api/mediator/diag` | Full tree diagnostic — includes all `index.*` nodes |
| 8.7 | `GET /api/mediator/diag/<path>` | Single node detail |
| 8.8 | `POST /api/mediator/refresh` | Force recompute specific paths |
| 8.9 | `POST /api/mediator/bust` | Temporal invalidation |
| 8.10 | `POST /api/mediator/dispatch` | Async background recompute |

---

## 9. Startup Sequence

### SPEC-9: Server startup

| ID | Requirement | Test |
|----|-------------|------|
| 9.1 | Mediator is initialized during `create_app()` | `get_mediator()` returns instance after app starts |
| 9.2 | All index nodes are registered before watcher starts | `mediator.diag()` shows 9 index nodes |
| 9.3 | Watcher thread starts after mediator + index registration | Watcher thread is alive and daemon |
| 9.4 | First watcher cycle triggers initial `put("index.scan")` → full cascade | On startup, all index nodes compute once |
| 9.5 | Legacy `start_project_index` runs as fallback during transition | Legacy thread starts alongside watcher |
| 9.6 | App is usable (file browsing) within 50ms of startup | `index.scan` + `files` + `dirs` + `paths` computed before heavy nodes |

---

## 10. Performance Contracts

| ID | Requirement | Target | Test |
|----|-------------|--------|------|
| 10.1 | `scan_project()` for ~1,300 files | < 100ms | Benchmark on real project |
| 10.2 | `diff_scans()` for two ~1,300-entry dicts | < 5ms | Benchmark |
| 10.3 | Incremental symbols: 1 file changed | < 200ms | Benchmark (parse + merge) |
| 10.4 | Incremental symbols: 0 files changed (empty delta) | < 1ms | Returns accumulator unchanged |
| 10.5 | Incremental peek: 1 MD page affected | < 100ms | Benchmark |
| 10.6 | Watcher poll cycle (241 dirs) | < 10ms | Benchmark |
| 10.7 | No computation when no files changed | 0ms work | `delta.empty → skip` |

---

## 11. Data Integrity Contracts

| ID | Requirement | Test |
|----|-------------|------|
| 11.1 | `FileEntry.ext` matches file extension (no leading dot) | `scan["foo.py"].ext == "py"` |
| 11.2 | `FileEntry.mtime` is a float (seconds since epoch) | `isinstance(entry.mtime, float)` |
| 11.3 | `FileEntry.size` is file size in bytes | `entry.size == os.path.getsize(path)` |
| 11.4 | Scan skips `.git`, `__pycache__`, `node_modules`, `.venv`, hidden dirs | None of these appear in scan keys |
| 11.5 | Scan paths are relative to project root, POSIX-style | No absolute paths, forward slashes |
| 11.6 | `ScanDelta.added` contains only NEW paths (not in previous scan) | Set difference check |
| 11.7 | `ScanDelta.modified` contains only paths where `mtime` increased | Verify mtime comparison |
| 11.8 | Symbol entries have `name`, `file`, `line`, `kind` fields | Field presence check |
| 11.9 | Peek entries have `resolved` and/or `unresolved` lists | Structure check |
| 11.10 | Classify returns `languages`, `frameworks`, `primary_language`, `extensions` | Key presence check |

---

## 12. Thread Safety Contracts

| ID | Requirement | Test |
|----|-------------|------|
| 12.1 | Concurrent `get()` calls on the same path do not corrupt data | Two threads call `m.get("index.scan")` → both get valid results |
| 12.2 | `put()` during `get()` does not deadlock | Put + Get on different threads complete |
| 12.3 | Per-path compute locks prevent duplicate computation | Two simultaneous `get()` calls → resolver runs once |
| 12.4 | Watcher `put()` does not block during resolver execution | Watcher thread is never blocked by resolvers |
| 12.5 | Re-entrancy guard in bridge prevents deadlock from circular calls | `get_index()` from within a resolver returns legacy `_index` |

---

## 13. What "Done" Looks Like

### Tier 1 — Foundation (must have)
- [ ] All 9 index nodes registered with correct `ttl=None`
- [ ] Caching works: compute once, serve from cache until invalidated
- [ ] `put("index.scan")` cascades to all 8 dependent nodes
- [ ] FS watcher detects changes and calls `put("index.scan")`
- [ ] No infinite loops, no deadlocks
- [ ] All existing tests pass (338+)

### Tier 2 — Trilateral Wiring (the vision)
- [ ] `detect.*` nodes depend on `index.classify`
- [ ] `put("index.scan")` cascade reaches detect → devops → posture
- [ ] Single file change propagates through the entire tree
- [ ] Dashboard shows index nodes alongside detect/devops/posture

### Tier 3 — Operations (usability)
- [ ] `/api/mediator/index/status` returns clean summary
- [ ] `/api/mediator/index/delta` shows what changed
- [ ] `/api/mediator/index/rescan` forces full rescan + cascade
- [ ] `/api/mediator/index/rebuild-symbols` and `rebuild-peek` work
- [ ] Server startup produces ≤1 scan log per watcher cycle

### Tier 4 — Performance (polish)
- [ ] Scan < 100ms for 1,300 files
- [ ] 1-file change: < 200ms total (scan + delta + symbols + peek)
- [ ] Empty delta: 0ms work (skip entirely)
- [ ] Cold start: app usable at T+50ms, full at T+35s
- [ ] Warm start: full at T+5ms + first watcher cycle

---

## 14. What This Spec Does NOT Cover (Future)

These are explicitly out of scope for this milestone:

- Sharded disk persistence (`scan.json`, `symbols.json`, etc.)
- Settings/preferences UI for enabling/disabling index phases
- Live event stream integration (SSE/WebSocket for index events)
- Replacing `ProjectInfo` singleton with `index.classify` consumers
- Migration of callers from `get_index()` to direct mediator access
- Detection nodes using index data instead of subprocess calls
  (SPEC-6.1 wires the dependency, but the resolvers still call subprocesses;
  replacing the resolvers to read from index.classify is a separate milestone)

---

## 15. Spec Identifiers — Quick Reference

| Range | Domain |
|-------|--------|
| SPEC-1.x | Trilateral identity |
| SPEC-2.x | Node registry |
| SPEC-3.x | Caching semantics |
| SPEC-4.x | Incremental processing |
| SPEC-5.x | FS watcher |
| SPEC-6.x | Cascade / downstream wiring |
| SPEC-7.x | Backwards compat bridge |
| SPEC-8.x | Dashboard / observability |
| SPEC-9.x | Startup sequence |
| SPEC-10.x | Performance |
| SPEC-11.x | Data integrity |
| SPEC-12.x | Thread safety |
