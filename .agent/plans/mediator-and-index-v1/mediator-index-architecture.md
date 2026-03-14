# Mediator-Native Index — Architecture & Implementation Plan

> **Status:** Architecture — Ready for review
> **Created:** 2026-03-12
> **Companion to:** `query-mediator-plan.md`, `query-mediator-milestone.md`
> **Replaces:** `src/core/services/project_index.py` (legacy monolithic index)

---

## 1. Why This Exists

The mediator was built as a trilateral data hub:

```
Backend  → Mediator
Cache    → Mediator
Index    → Mediator ← THIS DOCUMENT
```

But the **Index** — the foundation, the root of the tree — was never
integrated. Without it, the mediator is a tree without roots. Detection
nodes run subprocess calls instead of reading from the index. Symbols
get re-parsed from scratch on every change. 30–44 seconds to rebuild
when a single file changes.

This document defines the new mediator-native index: **delta-driven,
incremental, observable, and the root that everything else grows from.**

---

## 2. Current State — The Problem

### 2.1 Measured Performance (from production logs)

| Phase | What | Duration | Waste |
|-------|------|----------|-------|
| File walk | `os.walk()` → 1,298 files, 241 dirs | 38–116ms | None — this is cheap |
| Symbol parse | Parse every `.py` file for defs | **26–42 seconds** | 💀 Full re-parse every time |
| Peek cache | Pre-compute refs for 223 `.md` pages | 1.5–2.4 seconds | Full re-compute every time |
| **Full rebuild** | All three phases | **30–44 seconds** | 💀 Triggered by single file edit |
| Disk cache | 1.5MB JSON load/save | ~50ms | Fine |

### 2.2 What's Wrong

1. **Monolithic rebuild** — One file changes → everything rebuilds.
   No delta. No incremental. 30 seconds of CPU for a 1-line edit.

2. **No per-file tracking** — The index uses a single "max mtime" sentinel.
   It knows _something_ changed but not _what_. So it re-processes everything.

3. **Not in the mediator** — The index is a singleton with its own thread,
   its own disk cache, its own staleness detection. None of this goes through
   the mediator, so nothing downstream can cascade from index changes.

4. **Not observable** — No UI visibility into what the index contains,
   what's stale, what's being rebuilt. The debug dashboard can't show it
   because it's not a mediator node.

5. **Not operable** — No way to force-refresh a single file's symbols,
   bust the peek cache for one page, or see what changed since last scan.

---

## 3. The New Architecture

### 3.1 The Tree

```
index.
├── scan                ← the pulse: per-file mtime snapshot
│                         TTL=0 (always re-scan on demand)
│                         resolver: os.walk() + stat()
│                         result: {path: {mtime, size, type}, ...}
│                         ~38ms for 1,300 files
│
├── delta               ← the diff: what changed since last scan
│                         depends_on: index.scan
│                         resolver: diff(prev_scan, new_scan)
│                         result: {added: [], removed: [], modified: []}
│                         ~1ms (dict comparison)
│
├── files               ← filename → [paths] lookup map
│                         depends_on: index.scan
│                         resolver: derive from scan
│                         ~5ms (groupby filename)
│
├── dirs                ← dirname → [paths] lookup map
│                         depends_on: index.scan
│                         resolver: derive from scan
│                         ~2ms (groupby dirname)
│
├── paths               ← flat set of all relative paths
│                         depends_on: index.scan
│                         resolver: derive from scan
│                         ~1ms (set(scan.keys()))
│
├── symbols             ← INCREMENTAL symbol index
│                         depends_on: index.delta
│                         resolver: parse only changed .py files
│                         cold: ~30s | warm: ~50ms per changed file
│                         result: {symbol: [{file, line, kind}, ...]}
│
├── peek                ← INCREMENTAL peek resolution cache
│                         depends_on: index.delta, index.symbols
│                         resolver: re-compute only affected pages
│                         cold: ~2s | warm: ~100ms per affected page
│                         result: {doc_path: {resolved: [], unresolved: []}}
│
├── classify            ← language/framework classification
│                         depends_on: index.scan
│                         resolver: extension analysis, framework detection
│                         result: {languages: {}, frameworks: [], modules: []}
│
└── stats               ← aggregate observability
                          depends_on: index.*
                          result: counts, timings, coverage, health
```

### 3.2 The Data Flow

```
                         ┌─────────────────────────────────────────────────┐
                         │              FS WATCHER (5s poll)               │
                         │  detects mtime change → bust("index.scan")     │
                         └──────────────────┬──────────────────────────────┘
                                            │
                                            ▼
                         ┌──────────────────────────────────────────────┐
                         │  index.scan  (38ms)                         │
                         │  os.walk() → {path: {mtime, size, type}}    │
                         └──────┬──────────┬───────────┬───────────────┘
                                │          │           │
                    ┌───────────┘          │           └───────────┐
                    ▼                      ▼                       ▼
           ┌─────────────┐     ┌────────────────┐       ┌──────────────┐
           │ index.files │     │  index.delta   │       │ index.dirs   │
           │ index.paths │     │  {+3, -1, ~2}  │       │ index.classify│
           └─────────────┘     └───────┬────────┘       └──────────────┘
                                       │
                          ┌────────────┤
                          ▼            ▼
               ┌─────────────┐  ┌─────────────┐
               │index.symbols│  │ index.peek  │
               │ parse 2 .py │  │ 1 page      │
               │ files (100ms)│  │ affected    │
               └──────┬──────┘  └──────┬──────┘
                      │                │
                      └──┬─────────────┘
                         ▼
              ┌──────────────────┐
              │   index.stats    │
              │ counts, timings  │
              └────────┬─────────┘
                       │
           ─ ─ ─ ─ ─ ─│─ ─ ─ ─ ─ ─ downstream ─ ─ ─
                       ▼
              ┌──────────────────┐
              │    detect.*      │
              │    devops.*      │    index changes cascade to
              │    posture.*     │    all dependent domains
              └──────────────────┘
```

### 3.3 The Scan Snapshot — Core Data Structure

The scan is the ground truth. Every file in the project with its metadata:

```python
@dataclass
class FileEntry:
    """A single file in the project scan."""
    mtime: float        # seconds since epoch
    size: int           # bytes
    ftype: str          # "py", "md", "yml", "js", etc. (extension)

# The scan result:
ScanResult = dict[str, FileEntry]
# key = relative path (e.g., "src/core/services/mediator/core.py")
```

~1,300 entries. Light in memory. Serializable. Diffable.

### 3.4 The Delta — The Key to Performance

```python
@dataclass
class ScanDelta:
    """What changed between two scans."""
    added: list[str]      # new files since last scan
    removed: list[str]    # files that no longer exist
    modified: list[str]   # files whose mtime increased
    timestamp: float      # when this delta was computed

    @property
    def empty(self) -> bool:
        return not self.added and not self.removed and not self.modified

    @property
    def changed_paths(self) -> list[str]:
        """All paths that need re-processing."""
        return self.added + self.modified
```

**How it works:**

```python
def _compute_delta():
    """Compare current scan against previous scan."""
    prev_scan = _prev_scan_snapshot  # kept in memory
    curr_scan = mediator.get("index.scan")["data"]

    added    = [p for p in curr_scan if p not in prev_scan]
    removed  = [p for p in prev_scan if p not in curr_scan]
    modified = [p for p in curr_scan
                if p in prev_scan
                and curr_scan[p].mtime > prev_scan[p].mtime]

    _prev_scan_snapshot = curr_scan  # update for next delta

    return ScanDelta(
        added=added,
        removed=removed,
        modified=modified,
        timestamp=time.time(),
    )
```

**Cost:** O(n) dict comparison, n=1,300. ~1ms.

---

## 4. Incremental Symbol Index

### 4.1 The Problem with Full Rebuild

Current: parse every `.py` file → 30 seconds.
There are ~500 Python files. Each takes ~60ms to parse.
When 1 file changes, we re-parse 500 files. That's 499 wasted.

### 4.2 The Incremental Solution

The symbol index is a **persistent accumulator**. On each delta cycle:

1. **Remove** symbols from `delta.removed + delta.modified` files
2. **Parse** only `delta.added + delta.modified` Python files
3. **Merge** new symbols into the existing map

```python
def _resolve_symbols_incremental():
    """Incremental symbol resolution — parse only changed files."""
    delta = mediator.get("index.delta")["data"]
    current = _symbol_accumulator  # persistent between calls

    if delta.empty:
        return current  # nothing changed, skip entirely

    t0 = time.perf_counter()

    # Step 1: Purge symbols from changed/removed files
    dirty_files = set(delta.removed + delta.modified)
    if dirty_files:
        for name in list(current.keys()):
            current[name] = [s for s in current[name]
                             if s.file not in dirty_files]
            if not current[name]:
                del current[name]

    # Step 2: Parse only new/modified .py files
    parse_targets = [p for p in delta.changed_paths
                     if p.endswith(".py")]
    parsed_count = 0
    for path in parse_targets:
        try:
            symbols = _parse_python_file(project_root / path, path)
            for sym in symbols:
                current.setdefault(sym.name, []).append(sym)
            parsed_count += 1
        except Exception:
            pass  # skip unparseable files

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "[MediatorIndex] Symbols: purged %d files, parsed %d files in %dms",
        len(dirty_files), parsed_count, elapsed_ms,
    )

    return current
```

### 4.3 Performance Comparison

| Scenario | Current | New |
|----------|---------|-----|
| Cold start (no cache) | 30s (parse all 500 .py) | 30s (same — unavoidable) |
| 1 file changed | 30s (re-parse all 500) | **60ms** (parse 1 file) |
| 10 files changed | 30s (re-parse all 500) | **600ms** (parse 10 files) |
| New branch checkout | 30s (re-parse all 500) | **5–10s** (parse ~100 changed) |
| No changes | 30s (re-parse all 500) | **0ms** (delta is empty, skip) |

**Expected speedup for the common case (1 file edit): 500x.**

---

## 5. Incremental Peek Cache

### 5.1 Dependency-Aware Invalidation

Peek results for a `.md` page depend on:
- The page's own content (direct references)
- The files those references point to (existence check)
- The symbol index (for code references)

When the delta says `src/core/services/foo.py` was modified,
only `.md` pages that **reference** that file need re-computation.

```python
def _resolve_peek_incremental():
    """Incremental peek resolution — only re-compute affected pages."""
    delta = mediator.get("index.delta")["data"]
    symbols = mediator.get("index.symbols")["data"]
    current = _peek_accumulator  # persistent between calls

    if delta.empty:
        return current

    t0 = time.perf_counter()

    # Which .md pages were directly modified?
    modified_pages = {p for p in delta.modified if p.endswith(".md")}

    # Which .md pages reference files that changed?
    changed_set = set(delta.changed_paths + delta.removed)
    affected_pages = set()
    for page_path, result in current.items():
        for ref in result.get("resolved", []):
            if ref.get("target") in changed_set:
                affected_pages.add(page_path)
                break

    # Union: pages to re-compute
    pages_to_rebuild = modified_pages | affected_pages

    # Also add new .md files
    new_pages = {p for p in delta.added if p.endswith(".md")}
    pages_to_rebuild |= new_pages

    # Remove deleted pages
    for p in delta.removed:
        current.pop(p, None)

    # Re-compute affected pages
    for page_path in pages_to_rebuild:
        if (project_root / page_path).exists():
            current[page_path] = _compute_peek_for_page(
                project_root, page_path, symbols
            )
        else:
            current.pop(page_path, None)

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "[MediatorIndex] Peek: rebuilt %d/%d pages in %dms",
        len(pages_to_rebuild), len(current), elapsed_ms,
    )

    return current
```

### 5.2 Performance Comparison

| Scenario | Current | New |
|----------|---------|-----|
| 1 .py file changed | 2s (all 223 pages) | **<50ms** (0–3 affected pages) |
| 1 .md file changed | 2s (all 223 pages) | **~10ms** (1 page) |
| No changes | 2s (all 223 pages) | **0ms** (skip) |

---

## 6. Classification Node — Language & Framework Detection

Currently `detection.py` (the `ProjectInfo` singleton) does a separate
scan of the project tree to detect languages, frameworks, and modules.
With the index in the mediator, this becomes a **derived node**:

```python
def _resolve_classify():
    """Derive language/framework classification from the scan."""
    scan = mediator.get("index.scan")["data"]

    extensions = Counter()
    for path, entry in scan.items():
        extensions[entry.ftype] += 1

    languages = _detect_languages(extensions)
    frameworks = _detect_frameworks(scan)
    modules = _detect_modules(scan)

    return {
        "languages": languages,
        "frameworks": frameworks,
        "modules": modules,
        "extensions": dict(extensions),
    }
```

**Cost:** ~5ms (just counting extensions and checking for marker files).

This replaces the `ProjectInfo` singleton and gives detection nodes
a proper dependency:

```
index.classify  →  detect.docker (checks for Dockerfile in index)
index.classify  →  detect.k8s (checks for k8s manifests in index)
index.classify  →  detect.ci (checks for .github/workflows in index)
```

---

## 7. FS Watcher — The Pulse

### 7.1 Current State

Two independent watchers:
- `staleness_watcher.py` — 5s poll of `_WATCH_PATHS` → `state:stale` event
- `project_index._refresh_loop` — 60s poll of sentinel dirs → full rebuild

### 7.2 New: Unified Watcher → Mediator Bridge

One watcher. One purpose. Feed the mediator.

```python
def _index_watcher_loop(project_root: Path, mediator: QueryMediator):
    """Unified FS watcher — polls for changes and busts the mediator."""
    last_dir_mtimes: dict[str, float] = {}

    while True:
        time.sleep(POLL_INTERVAL_S)  # 5 seconds

        try:
            # Quick check: scan only directory mtimes (not files)
            # OS updates dir mtime when children change
            current_dir_mtimes = _scan_dir_mtimes(project_root)

            changed_dirs = {
                d for d, mt in current_dir_mtimes.items()
                if last_dir_mtimes.get(d) != mt
            }

            if not changed_dirs:
                continue  # nothing changed, sleep again

            last_dir_mtimes = current_dir_mtimes

            # Something changed — tell the mediator
            logger.debug(
                "[IndexWatcher] %d dirs changed, busting index.scan",
                len(changed_dirs),
            )

            # Bust the scan node — cascade handles the rest
            mediator.bust("index.scan")

        except Exception as e:
            logger.warning("[IndexWatcher] poll error: %s", e)
```

### 7.3 Why Dir-Level Polling?

Checking ~241 directory mtimes is cheaper than checking ~1,298 file mtimes.
When a file is created/modified/deleted in a directory, the OS updates
that directory's mtime. So we get change detection at 1/5th the stat cost.

**Cost per poll cycle:** ~241 stat() calls = ~2ms.

### 7.4 The Cascade Effect

```
dir mtime changes → bust("index.scan") →
  cascade → index.delta computed →
    cascade → index.symbols (incremental) →
      cascade → index.peek (incremental) →
        cascade → index.classify →
          cascade → detect.* (if they depend on index) →
            cascade → devops.* →
              cascade → posture.*
```

One stat() change at the bottom propagates all the way up the tree.
Each level only does the minimum work needed. That's the mediator's power.

---

## 8. Phased Cold Start

On first boot (no disk cache), a full build is unavoidable.
But the new system makes the app **usable much sooner**:

```
T+0ms      Server starts
T+38ms     index.scan complete → app knows what files exist
T+40ms     index.files, index.dirs, index.paths derived
T+45ms     index.classify derived → languages, frameworks known
           ────── APP IS USABLE HERE ──────
           File browsing works. Detection works.
           Content vault works.
           Only symbol search and peek are pending.

T+50ms     index.delta computed (full build = everything is "added")
T+30s      index.symbols complete (background, async via executor)
           ────── SYMBOL SEARCH WORKS ──────

T+32s      index.peek complete (background, depends on symbols)
           ────── FULL FUNCTIONALITY ──────

T+32.1s    Disk cache saved. Next startup loads from cache.
```

### 8.1 Warm Start (disk cache exists)

```
T+0ms      Server starts
T+5ms      Load disk cache → all nodes populated immediately
           ────── APP IS FULLY FUNCTIONAL ──────

T+5s       First watcher poll → index.scan
T+5.04s    index.delta → {added: 0, removed: 0, modified: 2}
T+5.1s     index.symbols → re-parse 2 files (120ms)
T+5.2s     index.peek → re-compute 1 affected page (10ms)
           ────── FULLY CURRENT ──────
```

**Warm start to full functionality: 5ms.**
**Warm start to fully current: ~5 seconds (next poll cycle).**

---

## 9. Persistence — Sharded Disk Cache

### 9.1 Why Not One Big JSON?

The current 1.5MB monolithic JSON works, but:
- Saving 1.5MB after a 1-file incremental update is wasteful
- Loading 1.5MB at startup when we only need the scan is slow
- Can't load phases independently

### 9.2 Sharded Cache Structure

```
.state/mediator_index/
├── scan.json           ← ~60KB  (1,300 file entries)
├── symbols.json        ← ~800KB (3,600 symbols)
├── peek.json           ← ~600KB (223 pages)
├── classify.json       ← ~2KB   (languages, frameworks)
└── meta.json           ← ~1KB   (timestamps, counts, version)
```

Each shard loads independently. On cold start, `scan.json` loads in <5ms,
making the app file-aware before the heavier shards finish loading.

### 9.3 Incremental Save

When only `index.symbols` changes (a `.py` file was edited), only
`symbols.json` gets rewritten. Not the entire 1.5MB.

```python
def _save_shard(name: str, data: Any):
    """Save a single index shard to disk."""
    path = state_dir / f"{name}.json"
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, default=_json_default)
    tmp.rename(path)  # atomic on POSIX
```

---

## 10. Observability — The Dashboard

### 10.1 Index Node in the Debug Dashboard

The index nodes appear in the mediator debug dashboard tree:

```
🌳 root
  ├── index          ← NEW: the foundation
  │   ├── scan       ● 38ms ago    [fresh]
  │   ├── delta      ● 38ms ago    [+0 -0 ~0]
  │   ├── files      ● 38ms ago    [1,298 files]
  │   ├── dirs       ● 38ms ago    [241 dirs]
  │   ├── paths      ● 38ms ago    [1,539 paths]
  │   ├── symbols    ● 38ms ago    [3,664 symbols]
  │   ├── peek       ● 38ms ago    [223 pages]
  │   ├── classify   ● 38ms ago    [py, js, yml]
  │   └── stats      ● 38ms ago
  ├── detect
  ├── devops
  └── posture
```

### 10.2 Index Detail View

Clicking `index` branch shows:

```
┌──────────────────────────────────────────────────────────┐
│ index branch                                             │
│                                                          │
│ Files: 1,298  Dirs: 241  Symbols: 3,664  Peek: 223      │
│ Last scan: 38ms ago  Last delta: +0 -0 ~0                │
│ Cold build: 32.1s  Last incremental: 120ms               │
│ Disk cache: 1.46MB (4 shards)                            │
│                                                          │
│ ┌─ Languages ──────────────────────────────────────────┐ │
│ │ Python: 512 files (39%)  JS: 128 files (10%)         │ │
│ │ HTML: 187 files (14%)  YAML: 43 files (3%)           │ │
│ │ MD: 223 files (17%)  Other: 205 files (16%)          │ │
│ └──────────────────────────────────────────────────────┘ │
│                                                          │
│ [🔄 Force Rescan] [💥 Bust All] [🔍 Rebuild Symbols]    │
│ [📄 Rebuild Peek] [💾 Save to Disk] [🗑️ Clear Cache]    │
└──────────────────────────────────────────────────────────┘
```

### 10.3 Delta Live View

Clicking `index.delta` shows the last computed delta:

```
┌──────────────────────────────────────────────────────────┐
│ index.delta                                              │
│                                                          │
│ Last delta: 2.3s ago                                     │
│ Added: 0  Removed: 0  Modified: 2                        │
│                                                          │
│ Modified:                                                │
│   ~ src/core/services/mediator/core.py       (3.2s ago)  │
│   ~ src/ui/web/templates/scripts/_debug.html (3.2s ago)  │
│                                                          │
│ Cascade triggered:                                       │
│   → index.symbols  (re-parsed 1 .py file, 62ms)         │
│   → index.peek     (0 pages affected, skipped)           │
│   → index.classify (no language change, skipped)         │
└──────────────────────────────────────────────────────────┘
```

### 10.4 Live Event Stream Integration

Index events appear in the mediator's live event stream:

```
20:34:19  index:scan      1,298 files scanned (38ms)
20:34:19  index:delta     +0 -0 ~2 (1ms)
20:34:19  index:symbols   re-parsed 1 file (62ms)
20:34:19  index:peek      0 pages affected (0ms)
20:34:24  index:scan      1,298 files scanned (41ms)
20:34:24  index:delta     +0 -0 ~0 — no changes
```

---

## 11. Operations — UI-Surfaced Actions

### 11.1 Debug Dashboard Operations

| Operation | What it does | API |
|-----------|-------------|-----|
| **Force Rescan** | Bust `index.scan`, trigger full re-walk | `POST /api/mediator/bust` `{path: "index.scan"}` |
| **Rebuild Symbols** | Bust `index.symbols`, force full re-parse | `POST /api/mediator/bust` `{path: "index.symbols"}` |
| **Rebuild Peek** | Bust `index.peek`, force full re-compute | `POST /api/mediator/bust` `{path: "index.peek"}` |
| **Bust All** | Bust entire `index.*` branch | `POST /api/mediator/bust` `{prefix: "index"}` |
| **Save to Disk** | Force persist all shards | `POST /api/mediator/persist` `{prefix: "index"}` |
| **Clear Cache** | Delete disk shards + bust | `POST /api/mediator/clear` `{prefix: "index"}` |

### 11.2 Settings / Preferences

```
☑ Enable mediator index (default: on)
☑ Background symbol parsing (default: on)
☑ Peek pre-computation (default: on)
  Watcher poll interval: [5s ▼]
  Symbol parse timeout: [60s ▼]
```

User can disable expensive phases if they don't use symbol search or peek.

---

## 12. API — Backend Contracts

### 12.1 Registration Module

```python
# src/core/services/mediator/registrations/index.py

def register_index(mediator: QueryMediator) -> None:
    """Register index.* nodes — the root of the data tree."""
    tree = mediator.tree
    root = mediator.project_root

    # Keep accumulators in closure scope for incremental updates
    _prev_scan: dict[str, FileEntry] = {}
    _symbol_acc: dict[str, list[SymbolEntry]] = {}
    _peek_acc: dict[str, dict] = {}

    # ── index.scan ─────────────────────────────────────────
    tree.register(TreeRegistration(
        path="index.scan",
        resolver=lambda: _scan_project(root),
        ttl=0,           # always re-compute when requested
        persist=True,    # save to .state/mediator_index/scan.json
    ))

    # ── index.delta ────────────────────────────────────────
    def _compute_delta():
        nonlocal _prev_scan
        curr = mediator.get("index.scan")["data"]
        delta = _diff_scans(_prev_scan, curr)
        _prev_scan = curr
        return delta

    tree.register(TreeRegistration(
        path="index.delta",
        resolver=_compute_delta,
        ttl=0,
        depends_on=["index.scan"],
    ))

    # ── index.files ────────────────────────────────────────
    tree.register(TreeRegistration(
        path="index.files",
        resolver=lambda: _derive_file_map(mediator.get("index.scan")["data"]),
        ttl=0,
        depends_on=["index.scan"],
    ))

    # ── index.dirs ─────────────────────────────────────────
    tree.register(TreeRegistration(
        path="index.dirs",
        resolver=lambda: _derive_dir_map(mediator.get("index.scan")["data"]),
        ttl=0,
        depends_on=["index.scan"],
    ))

    # ── index.paths ────────────────────────────────────────
    tree.register(TreeRegistration(
        path="index.paths",
        resolver=lambda: set(mediator.get("index.scan")["data"].keys()),
        ttl=0,
        depends_on=["index.scan"],
    ))

    # ── index.symbols (incremental) ────────────────────────
    def _resolve_symbols():
        nonlocal _symbol_acc
        delta = mediator.get("index.delta")["data"]
        _symbol_acc = _incremental_symbols(root, delta, _symbol_acc)
        return _symbol_acc

    tree.register(TreeRegistration(
        path="index.symbols",
        resolver=_resolve_symbols,
        ttl=0,
        persist=True,
        depends_on=["index.delta"],
    ))

    # ── index.peek (incremental) ───────────────────────────
    def _resolve_peek():
        nonlocal _peek_acc
        delta = mediator.get("index.delta")["data"]
        symbols = mediator.get("index.symbols")["data"]
        _peek_acc = _incremental_peek(root, delta, symbols, _peek_acc)
        return _peek_acc

    tree.register(TreeRegistration(
        path="index.peek",
        resolver=_resolve_peek,
        ttl=0,
        persist=True,
        depends_on=["index.delta", "index.symbols"],
    ))

    # ── index.classify ─────────────────────────────────────
    tree.register(TreeRegistration(
        path="index.classify",
        resolver=lambda: _classify_project(mediator.get("index.scan")["data"]),
        ttl=0,
        depends_on=["index.scan"],
    ))

    # ── index.stats ────────────────────────────────────────
    def _resolve_stats():
        scan = mediator.get("index.scan")["data"]
        symbols = mediator.get("index.symbols")["data"]
        peek = mediator.get("index.peek")["data"]
        classify = mediator.get("index.classify")["data"]
        return {
            "file_count": len([p for p in scan if scan[p].ftype != "dir"]),
            "dir_count": len([p for p in scan if scan[p].ftype == "dir"]),
            "symbol_count": sum(len(v) for v in symbols.values()),
            "peek_page_count": len(peek),
            "languages": classify.get("languages", {}),
        }

    tree.register(TreeRegistration(
        path="index.stats",
        resolver=_resolve_stats,
        ttl=0,
        depends_on=["index.scan", "index.symbols", "index.peek", "index.classify"],
    ))

    logger.debug("registered index.* nodes (9 total)")
```

### 12.2 Backwards Compatibility Bridge

During transition, the old `get_index()` API continues to work,
backed by the mediator:

```python
# In project_index.py — bridge to mediator

def get_index() -> ProjectIndex:
    """Return the project index (backed by mediator if available)."""
    if _mediator is not None:
        return _build_compat_index(_mediator)
    return _index  # legacy fallback

def _build_compat_index(mediator) -> ProjectIndex:
    """Build a ProjectIndex-compatible object from mediator data."""
    scan = mediator.get("index.scan")["data"]
    files = mediator.get("index.files")["data"]
    dirs = mediator.get("index.dirs")["data"]
    symbols = mediator.get("index.symbols")["data"]
    peek = mediator.get("index.peek")["data"]

    idx = ProjectIndex()
    idx.file_map = files
    idx.dir_map = dirs
    idx.all_paths = set(scan.keys())
    idx.symbol_map = symbols
    idx.peek_cache = peek
    idx.ready = True
    idx.symbols_ready = bool(symbols)
    idx.peek_cached = bool(peek)
    # ... fill counts from index.stats
    return idx
```

This means existing callers (`peek.py`, `content/peek.py`) work
unchanged during the migration. Once all callers are updated to
use mediator paths directly, the bridge is removed.

---

## 13. Wiring Downstream — Index as Root

### 13.1 Detection Nodes Depend on Index

Once the index is registered, detection nodes can (optionally)
declare dependency on it. This means when files change, detection
results automatically cascade:

```python
# In registrations/detect.py — add index dependency

tree.register(TreeRegistration(
    path="detect.docker",
    resolver=lambda: docker_ops.docker_status(root),
    ttl=120,
    persist=True,
    depends_on=["index.classify"],  # ← NEW: re-detect when project files change
))
```

### 13.2 The Full Cascade Map

```
index.scan
  └── index.delta
  │     ├── index.symbols
  │     │     └── index.peek
  │     └── index.classify
  │           ├── detect.docker
  │           ├── detect.k8s
  │           ├── detect.ci
  │           ├── detect.terraform
  │           ├── detect.git
  │           └── ... (all detect.* nodes)
  │                 └── devops.* nodes
  │                       └── posture.* nodes
  │
  ├── index.files
  ├── index.dirs
  └── index.paths
```

**One file change at the bottom → surgical updates all the way up.**

---

## 14. Implementation Phases

### Phase 8A: Core Index Registration (the foundation)

1. Create `src/core/services/mediator/registrations/index.py`
2. Implement `_scan_project()` — the per-file walker
3. Implement `_diff_scans()` — the delta computation
4. Implement `_derive_file_map()`, `_derive_dir_map()` — simple derivations
5. Register all 9 `index.*` nodes
6. Wire into mediator startup (alongside detect/devops/posture)
7. Tests: scan, delta, file/dir derivation
8. **Validate:** `mediator.get("index.scan")` returns full file map

### Phase 8B: Incremental Symbols

1. Port `_build_symbol_index` logic to `_incremental_symbols()`
2. Accumulator pattern with delta-driven purge + parse
3. Tests: cold parse, incremental add, incremental modify, remove
4. **Validate:** 1-file change triggers only 1-file parse

### Phase 8C: Incremental Peek

1. Port `_build_peek_cache` logic to `_incremental_peek()`
2. Dependency-aware page detection (which pages reference changed files?)
3. Tests: page modification, referenced file change, removed file
4. **Validate:** `.py` change triggers only affected `.md` pages

### Phase 8D: FS Watcher Bridge ✅ COMPLETE

1. ✅ Created `src/core/services/mediator/index_watcher.py`
2. ✅ Dir-level mtime polling (~241 dirs, ~2ms per cycle)
3. ✅ `scan_dir_mtimes()` → compare → `mediator.put("index.scan")` → cascade
4. ✅ EventBus integration: `index:watcher:change` events
5. ✅ 18 tests: scan, skip rules, change detection, cascade, thread startup
6. ✅ Wired into `server.py` startup alongside mediator

### Phase 8E: Classification + Detection Wiring ✅ COMPLETE

1. ✅ Implemented `index.classify` resolver (extension counts + marker files)
2. ✅ `classify_project()`: languages, primary_language, frameworks, extensions
3. ✅ Updated `index.stats` to include symbol_count, primary_language, framework_count
4. ✅ 11 tests: classify unit + mediator integration + stats enrichment
5. Note: `detect.*` wiring deferred — detect nodes use subprocess calls and
   don't benefit from file composition changes. The classify data is available
   for future downstream consumers.

### Phase 8F: Backwards Compat Bridge + Cutover ✅ COMPLETE

1. ✅ `get_index()` bridge: tries mediator first, falls back to legacy singleton
2. ✅ All 5 callers (peek.py ×3, routes/content/peek.py ×1, server.py ×1) work unchanged
3. ✅ Symbol type conversion: mediator IndexSymbolEntry → project_index IndexSymbolEntry
4. ✅ 9 tests: bridge file_map, dir_map, all_paths, symbols, peek, fallback
5. ✅ Index watcher wired in server.py alongside legacy builder (transition period)
6. Legacy `start_project_index` kept as fallback; can be removed once bridge is validated

### Phase 8G: Dashboard + Operations

1. Index nodes visible in debug dashboard tree
2. Delta live view (what changed since last scan)
3. Index-specific operations (force rescan, rebuild symbols, etc.)
4. Settings for disabling expensive phases
5. **Validate:** all operations work from the UI

---

## 15. Risk Analysis

| Risk | Mitigation |
|------|-----------|
| Cold start still takes 30s | Phased availability — app usable at T+38ms |
| Incremental symbols miss edge cases | Full rebuild fallback via `bust("index.symbols")` |
| WSL inotify unreliability | Dir-level mtime polling (proven pattern) |
| Memory pressure from persistent accumulators | ~2MB total (scan 60KB + symbols 800KB + peek 600KB) — fine |
| Race conditions during concurrent delta | Mediator's existing lock-per-node handles this |
| Backwards compat breaks | Bridge layer + gradual caller migration |

---

## 16. Success Metrics

| Metric | Before | Target |
|--------|--------|--------|
| Single-file update latency | 30–44 seconds | **< 200ms** |
| Cold start to file-aware | 30 seconds | **< 50ms** |
| Cold start to full functionality | 30 seconds | **< 35 seconds** (same, but usable at 50ms) |
| Warm start to current | 60 seconds (poll interval) | **< 6 seconds** (5s poll + 1s cascade) |
| Memory footprint | ~2MB (monolithic) | ~2MB (sharded, same) |
| Disk cache load time | ~50ms (1.5MB) | **< 10ms** (scan.json only for instant start) |
| Observability | None | Full dashboard + live events + operations |
| Rebuild on no-change | 30 seconds wasted | **0ms** (delta is empty → skip) |
