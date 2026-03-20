# Comprehensive Infrastructure Exploration Report

## Request Summary
You needed to understand EXISTING systems that the compat commit completely ignored:
1. Process/thread management
2. Lazy loading patterns
3. Smart cache control
4. Persistence systems
5. File scanning optimizations

## FINDINGS

---

## 1. PROCESS/THREAD MANAGEMENT

### 1.1 WorkQueue — Priority-Aware Task Scheduler
**File:** `/src/core/services/mediator/work_queue.py` (981 lines)

**Purpose:** Replaces ThreadPoolExecutor with smart capacity-aware scheduling.

**Key Components:**
- **Priority Enum (6 levels):**
  - CRITICAL (0): Web requests bypass capacity limits
  - HIGH (1): User-initiated refresh
  - NORMAL (2): FS triggers
  - LOW (3): Cold start background fill
  - IDLE (4): Heavy background tasks (security scan, tests)
  - BACKGROUND (5): Passive indexing (AST peek)

- **WeightedSemaphore:**
  - Tracks capacity units (not just count)
  - Heavy tasks (size=3) consume more capacity
  - Prevents monopolization by expensive operations
  - Uses threading.Condition for thread-safe gating

- **Cooperative Yielding:**
  - Thread-local `_tls.yield_check()` function
  - Background workers pause when web requests arrive
  - Yields GIL for 10ms (GIL build) or 1ms (free-threaded)
  - Detects free-threaded Python (3.13+) at import time

- **Batch Tracking:**
  - Groups work items with `group_id`
  - Fires `on_complete` callback when all items in group finish
  - Tracks per-worker activity (path, priority, size, elapsed_ms)
  - Used for tiered dispatch gating

- **Web Request Priority:**
  - `begin_web_request()` / `end_web_request()` set yield flag
  - Counter tracks active web requests
  - Critical tasks bypass capacity waiting entirely

### 1.2 SSE/Streaming via Wizard Generators
**File:** `/src/core/services/module_upgrade/automation/wizard.py` (661 lines)

**Pattern:** Generator functions yielding SSE event dicts.

**Functions:**
- `wizard_dep_scan(ctx)` — Phase 1: dependency compatibility scanning
  - Yields progress events: step_start, log, step_done, done
  - Scans dependencies, queries registries, finds alternatives
  
- `wizard_subprocess(ctx, cmd, label)` — Run subprocess with streaming
  - Yields output line by line
  - Captures exit code, stderr
  
- `wizard_batch(ctx, step_ids, step_labels, project_root)` — Multi-step automation
  - Runs automation steps sequentially
  - Streams all output via SSE
  - Handles remediation when steps fail

**Design:** No explicit threading — generators are pulled by Flask/Quart SSE handler.

---

## 2. LAZY LOADING PATTERNS

### 2.1 Mediator-Based Lazy Loading
**File:** `/src/core/services/mediator/core.py` (1605 lines)

**Pattern:** Central QueryMediator with lazy resolution.

**Key Methods:**
- `get(path, *, force=False, max_age=None, stale_ok=False, explain=False, since_seq=None)`
  - Returns cached value OR computes via node.resolver()
  - TTL-based freshness checking
  - mtime_paths dependency tracking
  - `stale_ok=True` returns stale data + triggers background refresh
  
- `peek(path)` — Non-blocking peek (never triggers computation)
  - Returns cached value or None
  - Safe to call from anywhere (CLI, tests, no mediator)
  
- `peek_many(*paths)` — Bulk peek without triggering computes

**Phase 6A: Stale-While-Revalidate**
- `subscribe(pattern, callback)` — Register path pattern callbacks
- `mark_refreshing(path)` / `clear_refreshing(path)` — Track refresh state
- Returns stale data with `meta["stale"]=True, meta["refreshing"]=True`

### 2.2 Singleton FeatureRegistry
**File:** `/src/core/services/compat/database/registry.py` (185 lines)

**Pattern:** Class-level singleton with `_singleton` and `_singleton_dir` fields.

```python
@classmethod
def load(cls, entries_dir: Path | None = None) -> FeatureRegistry:
    """Loaded once per process."""
    if cls._singleton is not None and cls._singleton_dir == entries_dir:
        return cls._singleton
    # ... load all entries ...
    cls._singleton = registry
    return registry

@classmethod
def invalidate(cls) -> None:
    """Force reload on next load()."""
    cls._singleton = None
```

**This is what the compat commit should have used but didn't.**

### 2.3 Property Decorators for Lazy Computation
**Pattern:** Used across mediator and work_queue

Examples:
- `@property` on QueryMediator: tree, project_root
- `@property` on WorkQueue: pending, semaphore_used, semaphore_available, web_requests_active
- `@property` on ScanView: file_count, extensions
- `@property` on Priority: (IntEnum)

---

## 3. SMART CACHE CONTROL

### 3.1 Mediator Cascade Invalidation
**File:** `/src/core/services/mediator/core.py` (lines 629-728)

**Method: `put(path, data=None, *, cascade=True, cascade_depth=-1, notify=True)`**

**Write Path (data provided):**
```python
entry = CacheEntry(data=data, computed_at=time.time(), seq=seq, source="computed")
self._set_cached(path, entry)
node.last_change_seq = seq
```

**Invalidate Path (data=None):**
```python
removed = self._remove_cached(path)
if removed:
    invalidated.append(path)
    node.last_change_seq = seq
```

**Cascade (if enabled):**
```python
dep_paths = self._tree.dependents(path, depth=cascade_depth)
for dep_path in dep_paths:
    removed = self._remove_cached(dep_path)
    if removed:
        invalidated.append(dep_path)
```

**Dependency Graph:**
- `index.scan` (root)
  - → `index.delta` (diff logic)
    - → `index.symbols` (incremental parse)
    - → `index.peek` (incremental md peek)
  - → `index.files`, `index.dirs`, `index.paths` (derived lookups)
  - → `index.classify` (language/framework detection)

### 3.2 Per-Path Threading Locks
**File:** `/src/core/services/mediator/core.py` (lines 185-186, 340-395)

```python
self._compute_locks: dict[str, threading.Lock] = {}
```

**Usage:** One thread computes a path at a time; others wait and get the cached result.

### 3.3 Batch Mode — Aggregate Events
**File:** `/src/core/services/mediator/core.py` (lines 967-1021)

```python
@contextmanager
def batch(self) -> Generator[None, None, None]:
    """Accumulate changes, publish ONE aggregate event on exit."""
    self._batch_active = True
    self._batch_writes = []
    self._batch_invalidated = []
    # ... yield ...
    # On exit: publish aggregate event
```

**Use:** Multiple `put()` calls inside batch context publish ONE event instead of N.

### 3.4 EventBus Integration
**File:** `/src/core/services/mediator/core.py` (lines 908-963)

Publishes two event types:
- `mediator:write` — when data is written
- `mediator:invalidated` — when cache is busted

Also emits to event store via `Event` object with correlation ID.

---

## 4. PERSISTENCE

### 4.1 Disk-Based Cache Hydration
**File:** `/src/core/services/mediator/persistence.py` (433 lines)

**Cold Start (First Run):**
```
Empty cache on startup
→ resolve() computes values
→ persist_node() saves to disk (fire-and-forget)
```

**Warm Start (Subsequent Runs):**
```
load_all_nodes() scans .state/mediator_index/ for *.json
→ hydrate_cache() injects into mediator._cache
→ m.get() returns persisted data immediately (no recompute)
```

**Naming Convention:**
- Mediator path `"detect.docker"` → file `.state/mediator_index/detect.docker.json`
- Handles legacy shard names (scan.json → index.scan)

**Atomic Writes:**
```python
tmp = fpath.with_suffix(".tmp")
json.dump(data, f)
tmp.rename(fpath)  # atomic POSIX rename
```

**Dataclass Rehydration:**
- JSON flattens dataclasses to dicts
- `_rehydrate_shards()` reconstructs FileEntry, IndexSymbolEntry objects
- Enables downstream code to use `entry.ext`, `entry.name` attribute access

**Thread Safety:**
```python
_file_lock = threading.Lock()
```

---

## 5. FILE SCANNING OPTIMIZATIONS

### 5.1 Per-File Mtime Tracking — Surgical Delta
**File:** `/src/core/services/mediator/registrations/index.py` (1252 lines)

**Scan Data Structure:**
```python
@dataclass(frozen=True, slots=True)
class FileEntry:
    mtime: float      # seconds since epoch
    size: int         # bytes
    ext: str          # "py", "md", ""
```

**scan_project(project_root) → dict[rel_path: FileEntry]**
- Walks project tree (15-30 seconds with ~5000 files)
- Stores {path: {mtime, size, ext}} for every file
- Enables **surgical delta computation**

**Delta Computation:**
```python
@dataclass(frozen=True, slots=True)
class ScanDelta:
    added: list[str]      # new files
    removed: list[str]    # deleted files
    modified: list[str]   # mtime increased
    timestamp: float
```

`diff_scans(prev, curr)` → ScanDelta (~1ms)

### 5.2 Incremental Symbol Parsing
**File:** `/src/core/services/mediator/registrations/index.py` (lines 536-669)

**Cold Start:**
- Full parse of all parseable files via `registry.parse_tree()`
- ~30 seconds (first run)

**Warm Update (after file change):**
1. **Purge**: Remove symbols from removed/modified files (~1ms)
2. **Parse**: Parse only added/modified files
   - Yield checkpoint every 10 files via `current_yield_check()`
   - Releases GIL for web requests
   - **Result: ~60ms for 1 file edit** (500x faster)

**Parseable Extensions:**
```python
"py", "pyw", "pyi", "js", "jsx", "ts", "tsx", "go", "rs",
"html", "htm", "jinja", "yml", "yaml", "toml", "json",
"css", "scss", "md", "markdown", "rst", "sh", "dockerfile"
```

### 5.3 Incremental Markdown Peek
**File:** `/src/core/services/mediator/registrations/index.py` (lines 794-905)

**Strategy:**
- **Cold**: Peek all .md files (~2s)
- **.md files only changed**: Re-peek only those files
- **Source files changed**: Re-peek ALL .md files (symbols may have changed)
- **Nothing changed**: Return unchanged

**_peek_one_md(project_root, rel_path, sym_idx):**
- Reads markdown content
- Calls `scan_and_resolve_all(content, rel_path, project_root, sym_idx)`
- Returns resolved/unresolved symbol references

### 5.4 ScanView — O(1) Lookups
**File:** `/src/core/services/mediator/registrations/index.py` (lines 156-340)

**Pre-computed Indexes:**
```python
self._by_ext = {"py": [...paths], "md": [...paths], ...}  # O(1) by extension
self._by_name = {"Dockerfile": [...paths], ...}            # O(1) by filename
self._by_dir = {"src/core": [...paths], ...}               # O(1) by directory
self._dir_set = {"src", "src/core", "src/core/api", ...}   # O(1) dir exists?
```

**Query Methods:**
- `files_with_ext(ext)` — all .py files
- `files_named(name)` — all Dockerfiles
- `files_in_dir(dir, recursive=True)` — all files under src/
- `dir_exists(dir)` — check if directory has files
- `has_file(rel_path)` — exact file exists?

**Usage Pattern:**
```python
view = mediator.peek("index.view")  # get ScanView
python_files = view.files_with_ext("py")  # O(1)
```

### 5.5 Directory Mtime Polling (Not Inotify)
**File:** `/src/core/services/mediator/index_watcher.py` (822 lines)

**FS Watch Strategy:**
- Polls ~241 directory mtimes every 5 seconds
- **Why not inotify:** unreliable on WSL/Docker/NFS
- **Cost:** ~2ms (5x cheaper than checking ~1,300 file mtimes)
- **Result:** When OS updates dir mtime (child create/modify/delete)
  → Watcher invalidates `index.scan`
  → Mediator cascade recomputes downstream nodes

**Daemon Thread:**
```python
start_index_watcher(project_root, mediator, poll_interval=5.0)
# → starts thread with target=_poll_loop, daemon=True
```

**Tiered Dispatch** (lines 175-193):
```python
_FAST_INDEX = [
    "index.scan",      # root (~25ms)
    "index.delta",     # diff (~5ms)
    "index.files",     # O(1) by name (~2ms)
    "index.dirs",      # O(1) by dir (~2ms)
    "index.paths",     # set (~1ms)
    "index.classify",  # language detection (~10ms)
]
_SLOW_INDEX_PEEK = [
    "index.symbols",   # cold ~30s, warm <1ms
    "index.peek",      # cold ~2s, warm <100ms
]
```

FAST runs sequentially (~45ms total), SLOW can parallel with detect/devops/posture.

---

## 6. REFRESH / BUST / DISPATCH API

**File:** `/src/core/services/mediator/core.py`

### 6.1 refresh() — Force Recompute
```python
def refresh(self, *paths: str) -> dict[str, Any]:
    """Force-recompute (bypass cache)."""
    # If executor + multiple paths: parallel via futures
    # Otherwise: sequential
    return {"refreshed": {path: meta}, "errors": {path: str}, "elapsed_s": float}
```

- `refresh_branch(prefix)` — all nodes under prefix
- `refresh_stale(prefix)` — only expired nodes

### 6.2 bust() — Invalidate by Age
```python
def bust(self, max_age: float, prefix: str = "", *, notify: bool = True) -> dict:
    """Invalidate entries older than max_age seconds."""
    return {"busted": [paths], "count": int}
```

- `bust_path(path, cascade=True, cascade_depth=-1)` — invalidate specific path + dependents

### 6.3 dispatch() — Background Recompute
```python
def dispatch(self, *paths: str, priority: int | None = None, 
             on_complete: Callable[[], None] | None = None) -> dict:
    """Submit to work queue for background computation."""
```

**Tiered Dispatch Strategy:**
- Groups paths by priority tier
- Each tier runs sequentially (higher priority finishes before lower starts)
- Within tier: concurrent via work queue
- `on_complete` fires when entire dispatch done
- Used for: cold start background fill, FS-triggered updates

---

## 7. CONFIGURATION & DEFAULTS

### 7.1 TTL Settings
- **TTL=0**: Always fresh, skip cache, recompute every time
- **TTL=None**: No time-based expiry, only mtime-based or explicit bust
- **TTL=inf**: Cache forever (unless explicitly invalidated)

### 7.2 Skip Patterns (in both index and watcher)
```python
_SKIP_DIRS = frozenset({
    ".git", ".backup", "node_modules", "__pycache__", ".venv", "venv",
    "build", "dist", ".tox", ".mypy_cache", ".ruff_cache",
    ".pytest_cache", ".next", ".nuxt", "site-packages", "_build",
    ".docusaurus", ".state", ".agent",
})
```

### 7.3 Tree Node Registration
Each node specifies:
- **ttl:** TTL in seconds (0, None, or number)
- **mtime_paths:** Paths to watch for file changes
- **resolver:** Function that computes the value
- **size:** Work capacity units (1–3)
- **dependencies:** (implicitly via cascade graph)

---

## 8. WHAT THE COMPAT COMMIT IGNORED

The compat system is a **monolithic singleton** that:

❌ **Does NOT use the mediator** — no lazy loading, no incremental updates
❌ **Does NOT use WorkQueue** — no priority-aware scheduling
❌ **Does NOT persist** — rebuilds entire registry from scratch on restart
❌ **Does NOT integrate with index watcher** — no FS-driven updates
❌ **Does NOT cascade invalidations** — no dependency tracking
❌ **Does NOT support stale-while-revalidate** — no background refresh
❌ **Does NOT batch writes** — no aggregate events
❌ **Does NOT profile parallelism** — sequential only

**The infrastructure to support smart caching, incremental updates, async composition, and FS-driven automation already exists.** The compat commit completely bypassed it.

---

## 9. FILES TO READ FOR DEEPER UNDERSTANDING

**Core Mediator:**
- `/src/core/services/mediator/core.py` — QueryMediator (1605 lines)
- `/src/core/services/mediator/work_queue.py` — Priority scheduler (981 lines)
- `/src/core/services/mediator/persistence.py` — Disk caching (433 lines)

**File Scanning:**
- `/src/core/services/mediator/registrations/index.py` — Index domain (1252 lines)

**FS Watching:**
- `/src/core/services/mediator/index_watcher.py` — Dir mtime polling (822 lines)

**Compat (what should have used mediator):**
- `/src/core/services/compat/database/registry.py` — Singleton pattern (185 lines)
- `/src/core/services/compat/orchestrator.py` — Main logic

**Wizard (SSE streaming):**
- `/src/core/services/module_upgrade/automation/wizard.py` — Generator-based SSE (661 lines)

**Adapter Registry:**
- `/src/adapters/registry.py` — Another singleton registry (216 lines)

