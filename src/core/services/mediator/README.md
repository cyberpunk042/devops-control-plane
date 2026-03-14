# QueryMediator — Trilateral Data Hub

> Central data hub for the DevOps Control Plane.  
> Mediates between **Backend** (compute), **Cache** (memory + disk), and **Index** (truth).

---

## 1. What It Is

The QueryMediator is the **single source of truth** for all computed data
in the DevOps Control Plane. Every piece of data — file indexes, detection
results, devops probe outputs, posture assessments, audit scores, GitHub
API responses — flows through the mediator.

It is NOT a database. It is NOT a message broker. It is a **data routing
engine** that decides:

- **When** to compute (only when stale or missing)
- **What** to invalidate (cascade through dependency graph)
- **Where** to store (in-memory cache + disk shards)
- **How** to serve (fresh, stale-while-revalidating, or from disk)

**62 registered nodes** across **5 domains**: index (9), detect (13),
devops (14), posture (6), extra (20).

---

## 2. Why It Exists

Before the mediator, each subsystem had its own cache, its own
invalidation logic, and its own persistence strategy:

- The devops cache wrote a monolithic JSON file
- The posture cache had its own TTL system
- The index scanner had its own file watcher
- Detection results were recomputed on every page load

This created three problems:

1. **Redundant computation** — the same data was computed multiple
   times by different subsystems that didn't know about each other.
2. **Stale data** — invalidation was per-subsystem, so changes
   in one system didn't propagate to dependent systems.
3. **Slow cold starts** — no unified persistence meant everything
   had to be recomputed on restart.

The mediator solves all three by being the **single data flow path**:

```
                    ┌─────────────┐
                    │   Backend   │
                    │  (resolvers)│
                    └──────┬──────┘
                           │ computes
                           ▼
┌─────────┐       ┌─────────────────┐       ┌──────────┐
│  Index   │◄────►│  QueryMediator  │◄────►│  Cache    │
│ (truth)  │      │   (data hub)    │      │ (memory + │
└─────────┘       └────────┬────────┘      │   disk)   │
                           │               └──────────┘
                           │ serves
                           ▼
                    ┌─────────────┐
                    │     UI      │
                    │ (consumer)  │
                    └─────────────┘
```

---

## 3. Architecture

### 3.1 The Trilateral Pattern

The mediator coordinates three actors:

- **Backend** — resolver functions that produce data (scan files,
  detect tools, probe services, assess posture)
- **Cache** — in-memory dict + per-node disk shards for persistence
- **Index** — the file scan that serves as the root of all truth

Data flows in one direction: **Index → Detect → DevOps → Posture**.
When the index changes, it cascades invalidation through all
dependent nodes. Each node recomputes only when it's next requested
(lazy invalidation).

### 3.2 The Data Tree

The `DataTree` is a **registry of metadata**, not data. Each registered
node describes:

- **path** — dot-separated address (e.g. `"posture.toolchain"`)
- **resolver** — function that produces the value
- **ttl** — seconds before the cached value expires (None = event-driven)
- **persist** — whether to save to disk for warm restarts
- **depends_on** — paths that trigger cascade invalidation

The tree supports hierarchical namespaces with automatic branch node
creation. Registering `"posture.toolchain"` auto-creates a `"posture"`
branch node.

```
posture                          ← branch (auto-created)
├── posture.platform            ← leaf node, ttl=inf, persist=True
├── posture.toolchain           ← leaf node, ttl=300s, persist=True
├── posture.project             ← leaf node, ttl=60s, persist=True
├── posture.runtime             ← leaf node, ttl=0 (always fresh)
├── posture.full                ← leaf node, depends on platform+toolchain+project+runtime
└── posture.summary             ← leaf node, depends on full
```

**The tree is immutable after initialization.** Registration happens
once during startup. After that, the tree structure is read-only.
No locking is needed for tree reads.

### 3.3 The Cache

The cache is an in-memory `dict[str, CacheEntry]` protected by a
threading lock. Each `CacheEntry` contains:

```python
@dataclass
class CacheEntry:
    data: Any           # the actual computed value
    computed_at: float   # time.time() when computed
    seq: int            # monotonic sequence number
    source: str         # "computed", "cache", "hydrated"
    elapsed_s: float    # how long computation took
```

Cache reads are thread-safe via `_lock`. Cache writes use per-path
compute locks to ensure only one thread computes a given path at a
time (others wait and get the cached result).

### 3.4 The Cascade

When a node is invalidated, all its **dependents** (nodes that
declared `depends_on=[this_node]`) are also invalidated. This
walks the dependency graph transitively:

```
index.scan invalidated
  └─► index.classify invalidated (depends_on=["index.scan"])
       └─► detect.docker invalidated (depends_on=["index.classify"])
            └─► devops.docker invalidated (depends_on=["detect.docker"])
                 └─► devops.status invalidated (depends_on=["devops.*"])
                      └─► extra.project_status invalidated (depends_on=["devops.status"])
```

Cascade is **lazy** — invalidation removes cache entries but does
NOT trigger recomputation. The next `get()` call recomputes.

The dependency graph is a DAG (directed acyclic graph). Cycles are
detected and prevented. Maximum cascade depth is configurable
(`cascade_depth` parameter on `put()`).

---

## 4. API Reference

All API methods are on the `QueryMediator` class. Access via the
singleton:

```python
from src.core.services.mediator import mediator

result = mediator.get("posture.toolchain")
```

### 4.1 `get(path, *, force=False, max_age=None, stale_ok=False, explain=False, since_seq=None)`

**The primary read operation.** Returns data for a path, computing
it if necessary.

```python
result = mediator.get("posture.toolchain")
# result = {
#     "data": {"go": "1.21", "python": "3.12", ...},
#     "meta": {
#         "path": "posture.toolchain",
#         "source": "cache",      # or "computed", "cache_stale"
#         "age_s": 42.3,
#         "seq": 157,
#         "stale": False,
#         "refreshing": False,
#     }
# }
```

**Parameters:**

| Param | Type | Default | Behavior |
|-------|------|---------|----------|
| `path` | str | required | Dot-separated node path |
| `force` | bool | False | Bypass cache, force recompute |
| `max_age` | float∣None | None | Override node's TTL for this call |
| `stale_ok` | bool | False | Return stale data instead of blocking |
| `explain` | bool | False | Include resolution trace in meta |
| `since_seq` | int∣None | None | Short-circuit if unchanged since this seq |

**Resolution order:**

1. Validate path exists and is registered
2. If `since_seq` provided and `node.last_change_seq <= since_seq`:
   return `{"changed": False}` immediately
3. If `ttl == 0`: always compute (skip cache entirely)
4. Check cache — if fresh, return immediately
5. If stale and `stale_ok=True`: return stale data, trigger background refresh
6. If stale and `stale_ok=False`: acquire compute lock, recompute
7. After computing: cache result, persist to disk, publish event

### 4.2 `peek(path)`

**Read-only cache check. NEVER triggers computation.**

```python
data = mediator.peek("posture.toolchain")
# Returns the data directly (not wrapped in {data, meta})
# Returns None if path has no cached data
```

Use `peek()` in context processors, template functions, and anywhere
that must not block the request cycle. If data isn't cached yet,
you get `None` — never a 500ms resolver call.

### 4.3 `peek_many(*paths)`

**Peek at multiple paths at once.**

```python
results = mediator.peek_many("posture.toolchain", "posture.platform")
# results = {
#     "posture.toolchain": {"data": {...}, "meta": {...}},
#     "posture.platform": {"data": {...}, "meta": {...}},
# }
# Missing paths are omitted from the result
```

### 4.4 `put(path, data=None, *, cascade=True, cascade_depth=-1, notify=True)`

**Write or invalidate a path.**

```python
# Inject data (e.g. from hydration)
mediator.put("index.scan", scan_data, cascade=False, notify=False)

# Invalidate (remove from cache) + cascade
mediator.put("index.scan")  # data=None → invalidate
# Returns {"invalidated": ["index.scan", "index.classify", ...], "seq": 42}
```

If `data` is provided: store as cached value.  
If `data` is None: remove from cache (invalidate).  
If `cascade=True`: invalidate all transitive dependents.

### 4.5 `bust_path(path, *, cascade=True, cascade_depth=-1, notify=True)`

**Convenience wrapper for targeted invalidation.**

```python
mediator.bust_path("detect.docker")
# Equivalent to: mediator.put("detect.docker", data=None, cascade=True)
```

### 4.6 `bust(max_age, prefix="", *, notify=True)`

**Age-based invalidation across all nodes.**

```python
# Bust all entries older than 5 minutes
mediator.bust(300)

# Bust only posture entries older than 1 minute
mediator.bust(60, prefix="posture")
```

### 4.7 `dispatch(*paths)`

**Submit paths for background recompute. Returns immediately.**

```python
result = mediator.dispatch("detect.docker", "detect.k8s", "detect.ci")
# result = {"task_id": "abc123", "paths": [...], "status": "submitted"}
```

Dispatch uses the ThreadPoolExecutor. Each path runs as a separate
task. **Fresh cached data is skipped** — only stale or missing
nodes are recomputed. This is the delta principle applied to dispatch.

The staleness check works as follows:
- If cached AND TTL-based: skip if `age < ttl`
- If cached AND TTL=inf: always skip (never expires)
- If cached AND TTL=None (event-driven): skip (valid until explicitly invalidated)
- If not cached: recompute

### 4.8 `refresh(*paths)`

**Force-recompute one or more paths. Blocking.**

```python
result = mediator.refresh("posture.toolchain", "posture.platform")
# result = {
#     "refreshed": {
#         "posture.toolchain": {"source": "computed", ...},
#         "posture.platform": {"source": "computed", ...},
#     },
#     "errors": {},
#     "elapsed_s": 0.42,
# }
```

Unlike `dispatch()`, `refresh()` is synchronous — it blocks until
all paths are computed. If an executor is configured and multiple
paths are given, resolvers run concurrently.

### 4.9 `refresh_stale(prefix="")`

**Recompute only nodes whose cache has expired.**

```python
result = mediator.refresh_stale("posture")
# Only recomputes posture.* nodes that are past their TTL
```

### 4.10 `subscribe(pattern, callback)`

**Register a callback for path pattern changes.**

```python
def on_posture_change(event):
    print(f"Posture changed: {event['paths']}")

sub_id = mediator.subscribe("posture.*", on_posture_change)

# Later:
mediator.unsubscribe(sub_id)
```

The callback receives: `{"type": "write"|"invalidate", "trigger": path,
"seq": N, "paths": [...]}`.

Callbacks must be **fast** (< 1ms). They run synchronously in the
`put()` call path. Use them to queue work, log, or update state.
Do NOT call `get()` from a subscriber callback.

### 4.11 `batch()`

**Accumulate changes and publish one aggregate event on exit.**

```python
with mediator.batch():
    mediator.put("devops.git", data=git_data)
    mediator.put("devops.docker", data=docker_data)
    mediator.put("devops.github", data=github_data)
# → single aggregate event published for all 3 changes
```

Useful for bulk updates where you don't want N individual events.

### 4.12 `diag(path="")`

**Diagnostic info about the mediator state.**

```python
# Summary:
info = mediator.diag()
# info = {
#     "tree": {"total_nodes": 67, "registered": 62, ...},
#     "seq": 1234,
#     "cached": 42,
#     "stale": 3,
#     "batch_active": False,
#     "subscriptions": 2,
#     "refreshing": [],
#     "has_executor": True,
#     "entries": {...},
# }

# Detail for a specific node:
info = mediator.diag("posture.toolchain")
```

---

## 5. Persistence

### 5.1 How It Works

Every node with `persist=True` is saved to disk after each successful
computation. This happens inside `get()`, after the value is cached
in memory. Persistence is **fire-and-forget** — it never blocks
computation and errors are swallowed with a warning log.

### 5.2 Shard Files

Each persisted node gets its own JSON file in `.state/mediator_index/`:

```
.state/mediator_index/
├── detect.docker.json
├── detect.k8s.json
├── detect.ci.json
├── extra.gh_pulls.json
├── extra.audit_scores.json
├── index.scan.json
├── index.symbols.json
├── posture.full.json
├── posture.toolchain.json
└── meta.json
```

**Naming convention:** The mediator path IS the filename.
`posture.toolchain` → `posture.toolchain.json`.

Writes are atomic: data is written to a `.tmp` file first, then
renamed. This prevents corrupt shards on crash.

All disk writes are serialized through `_file_lock` to prevent
concurrent writes from interleaving.

### 5.3 Hydration on Startup

On startup, `hydrate_cache()` is called ONCE (from `server.py`),
AFTER all nodes are registered. It:

1. Scans `.state/mediator_index/` for all `.json` files
2. Maps each file to its mediator path (handles legacy names)
3. Rehydrates index dataclasses (FileEntry, IndexSymbolEntry) from
   plain JSON dicts back to proper Python objects
4. Injects each loaded value into the mediator cache via
   `put(path, data, cascade=False, notify=False)`
5. Derives cheap index nodes (files, dirs, paths) from scan data

After hydration, `get()` returns data immediately for all persisted
nodes — no computation needed. This is what makes warm restarts fast.

### 5.4 Save After Compute

The persist call lives in `get()` (in `core.py`), right after
`_set_cached()`:

```python
# Store in cache
self._set_cached(path, entry)

# Persist to disk — survives restarts
try:
    from src.core.services.mediator.persistence import persist_node
    persist_node(self._project_root, path, result)
except Exception:
    pass  # persistence must never break computation
```

This means: every successful computation is automatically persisted
for nodes with `persist=True`. The node's registration controls
whether persistence happens (via the `persist` flag on `TreeRegistration`).

### 5.5 Legacy Compatibility

Old shard files used short names (`scan.json`, `symbols.json`).
The loader recognizes these via `LEGACY_SHARD_NAMES` and maps
them to the correct mediator path on load. No migration is needed —
old files are read correctly, and on next compute, the new-style
filename is written.

---

## 6. Concurrency

### 6.1 Per-Path Compute Locks

When multiple threads request the same path simultaneously, only
ONE thread computes. The others wait on the per-path lock and then
get the cached result:

```
Thread A: get("posture.toolchain")
  → cache miss → acquire lock for "posture.toolchain"
  → compute...

Thread B: get("posture.toolchain")
  → cache miss → wait on lock for "posture.toolchain"
  → lock acquired → double-check cache → HIT → return cached
```

Compute locks are stored in `_compute_locks: dict[str, Lock]`
and created lazily. The dict itself is protected by `_lock`.

### 6.2 Refreshing Guard

When dispatch submits paths for background recompute, it marks
them as "refreshing" via `mark_refreshing(path)`. This set is
available to `get()` so it can report `refreshing=True` in the
metadata when serving stale data.

```python
mediator.mark_refreshing("detect.docker")
# ...background thread computes...
mediator.clear_refreshing("detect.docker")
```

The `_refreshing` set is protected by `_lock`.

### 6.3 Thread Pool Executor

The mediator uses a `ThreadPoolExecutor(max_workers=4)` for
background dispatch. Each dispatched path runs as its own task.

The executor is optional — if `None`, dispatch marks paths but
does not spawn background work. The `on_stale` hook can be used
instead for custom background scheduling.

### 6.4 GIL Considerations

Python's GIL means CPU-bound resolvers don't get true parallelism
from the thread pool. The thread pool is most useful for I/O-bound
resolvers (GitHub API calls, git operations, file reads).

For CPU-heavy resolvers (symbol parsing, classification), the GIL
serializes them. The 4-thread pool still helps because while one
resolver is blocked on I/O, another can run its CPU work.

---

## 7. Registering Nodes

### 7.1 TreeRegistration

```python
from src.core.services.mediator.tree import TreeRegistration

tree.register(TreeRegistration(
    path="detect.docker",
    resolver=_resolve_docker,
    ttl=120,
    persist=True,
    depends_on=["index.classify"],
))
```

### 7.2 Dependencies

Dependencies declare what invalidates a node. When a dependency
is invalidated, this node is also invalidated (cascade).

```python
# Direct dependency
depends_on=["index.classify"]

# Glob pattern — depends on ALL detect.* nodes
depends_on=["detect.*"]

# Multiple dependencies
depends_on=["posture.platform", "posture.toolchain", "posture.project"]
```

Dependencies are resolved at registration time. The tree builds a
reverse index (`node.dependents`) for fast cascade lookups.

### 7.3 TTL Strategies

| TTL Value | Meaning | Example |
|-----------|---------|---------|
| `ttl=120` | Expires after 120 seconds | detect.docker — tool presence rarely changes |
| `ttl=0` | Always recompute (never cached) | posture.runtime — changes on every call |
| `ttl=math.inf` | Never expires via TTL | posture.platform — OS never changes at runtime |
| `ttl=None` | Event-driven only | index.classify — only invalidated by index.scan cascade |

Event-driven nodes (`ttl=None`) are the most efficient. They only
recompute when explicitly invalidated through the dependency graph.
No background polling, no TTL checks.

### 7.4 Resolver Patterns

Resolvers are zero-argument callables. Data they need must be
captured via closure or accessed through the mediator:

```python
# Pattern 1: Closure over project root
def _resolve_docker():
    return detect_docker(root)

# Pattern 2: Read from mediator (dependency chain)
def _resolve_devops_docker():
    result = mediator.get("detect.docker")
    return process_detection(result.get("data"))

# Pattern 3: Deferred imports (keeps startup fast)
def _resolve_gh_pulls():
    from src.core.services import git_ops
    return git_ops.gh_pulls(root)
```

**Important:** If a resolver calls `mediator.get()` for another
node, that node MUST be listed in `depends_on`. Otherwise, cascade
invalidation won't reach this node when the dependency changes.

---

## 8. Reading Data

### 8.1 `get()` — Compute If Needed

The default read path. Checks cache first, computes if stale or
missing. Blocks until data is available.

```python
result = mediator.get("posture.toolchain")
data = result["data"]
```

**When to use:** Backend operations, API responses, any context
where you need guaranteed-fresh data and can afford to wait.

### 8.2 `peek()` — Never Compute

Returns cached data or `None`. Never calls a resolver. Never blocks.

```python
data = mediator.peek("posture.toolchain")
if data is not None:
    # use it
```

**When to use:** Context processors, template rendering, any path
where computation would delay page load. If data isn't available
yet, display a loading state instead.

### 8.3 `stale_ok` — Accept Stale

Returns stale data immediately if the cache is expired, and triggers
a background refresh via the `on_stale` hook.

```python
result = mediator.get("posture.toolchain", stale_ok=True)
if result["meta"]["stale"]:
    # data is stale but usable
    # background refresh is in progress
```

**When to use:** UI endpoints where "slightly old data now" is
better than "wait 500ms for fresh data." The next request will
get the fresh data.

### 8.4 `force` — Always Recompute

Bypasses the cache entirely. Always calls the resolver.

```python
result = mediator.get("posture.toolchain", force=True)
```

**When to use:** Admin refresh buttons, manual recompute triggers.
Not for normal request paths.

---

## 9. Invalidation

### 9.1 `put()` — Inject and Cascade

The primary invalidation mechanism. Passing `data=None` removes
the cache entry and cascades to all dependents.

```python
# Invalidate index.scan → cascades to classify → detect.* → devops.* → extra.*
mediator.put("index.scan")
```

### 9.2 `bust()` — Age-Based Cleanup

Removes all entries older than a threshold:

```python
mediator.bust(300)  # bust everything older than 5 minutes
mediator.bust(60, prefix="detect")  # bust only detect.* older than 1 min
```

### 9.3 `bust_path()` — Targeted Invalidation

Invalidate a specific path with cascade. Convenience wrapper:

```python
mediator.bust_path("detect.docker")
```

### 9.4 Cascade Mechanics

Cascade invalidation is:

- **Lazy** — removes cache entries but does NOT recompute
- **Transitive** — walks the full dependency graph
- **DAG-safe** — tracks visited nodes to prevent infinite loops
- **Depth-limited** — configurable via `cascade_depth` parameter

The full cascade from `index.scan` affects up to **42 nodes**
(all nodes except the 10 extra.* nodes that don't depend on the
index chain, though `extra.project_status` is reached via
`devops.status`).

---

## 10. Observability

### 10.1 `diag()` — Full State Snapshot

Returns the complete state of the mediator: tree stats, cache
counts, per-node details, sequence numbers, and active refreshes.

Available via the diagnostic API endpoint.

### 10.2 `subscribe()` — Live Events

In-process event notifications. Subscribers are called synchronously
from `put()` whenever a matching path is written or invalidated.

Pattern matching supports globs:
- `"posture.*"` — any direct child of posture
- `"detect.**"` — all descendants under detect
- `"*"` — everything

### 10.3 EventBus Integration

The mediator publishes change events to the EventBus via
`_publish_change()`. This is the bridge to SSE (Server-Sent Events)
for real-time UI updates. Each change event includes:

- `trigger` — the path that caused the change
- `seq` — sequence number
- `writes` — paths that were written (data injected)
- `invalidated` — paths that were invalidated (cache removed)

---

## 11. Performance

### 11.1 Cache Hit: < 1ms

A cache hit is a dict lookup + age comparison. No locks acquired
unless there's contention. Target: < 1ms for any cached read.

### 11.2 Cascade: < 5ms for 62 nodes

The cascade walks the dependency DAG via `tree.dependents()`.
For the full 62-node tree, this takes < 5ms. The actual
invalidation (removing cache entries) is O(N) in the number
of affected nodes.

### 11.3 Hydration: < 100ms for 15 shards

Loading 15 JSON files from disk and injecting into the cache
completes in < 100ms. This includes JSON parsing and dataclass
rehydration for index nodes.

### 11.4 Shard Write: < 50ms per 100KB

Atomic write (tmp + rename) for a typical 100KB shard file.
JSON serialization is the bottleneck for large shards (index.scan
can be 500KB+).

---

## 12. DO's and DON'Ts

### DO

- ✅ Use `peek()` in context processors and template functions
- ✅ Use `get(stale_ok=True)` for UI endpoints
- ✅ Declare `depends_on` for every dependency your resolver uses
- ✅ Use deferred imports in resolvers to keep startup fast
- ✅ Use `persist=True` for data that's expensive to recompute
- ✅ Use `batch()` for bulk updates

### DON'T

- ❌ Call `get()` from a subscriber callback (deadlock risk)
- ❌ Call `get(force=True)` on normal request paths (defeats caching)
- ❌ Use `peek()` when you need guaranteed data (it returns None on miss)
- ❌ Forget `depends_on` when your resolver calls `mediator.get()`
- ❌ Register nodes after initialization (the tree is immutable)
- ❌ Use `dispatch()` for paths that need immediate results (use `refresh()`)

---

## 13. Node Registry

### 13.1 Index Domain (9 nodes)

| Path | TTL | Persist | Depends On |
|------|-----|---------|------------|
| `index.scan` | None | No | — (root) |
| `index.delta` | None | No | index.scan |
| `index.classify` | None | No | index.scan |
| `index.files` | None | No | index.scan |
| `index.dirs` | None | No | index.scan |
| `index.paths` | None | No | index.scan |
| `index.symbols` | None | No | index.delta |
| `index.peek` | None | No | index.delta, index.symbols, index.scan |
| `index.stats` | None | No | index.scan, index.delta, index.dirs, index.symbols, index.classify |

### 13.2 Detect Domain (13 nodes)

All detect nodes: `ttl=120` (except `detect.env`=60, `detect.git`=30),
`persist=True` (except `detect.env`, `detect.git`),
`depends_on=["index.classify"]`.

| Path | TTL | Persist |
|------|-----|---------|
| `detect.ci` | 120 | Yes |
| `detect.dns` | 120 | Yes |
| `detect.docker` | 120 | Yes |
| `detect.docs` | 120 | Yes |
| `detect.env` | 60 | No |
| `detect.git` | 30 | No |
| `detect.github` | 120 | Yes |
| `detect.k8s` | 120 | Yes |
| `detect.packages` | 120 | Yes |
| `detect.quality` | 120 | Yes |
| `detect.security` | 120 | Yes |
| `detect.terraform` | 120 | Yes |
| `detect.testing` | 120 | Yes |

### 13.3 DevOps Domain (14 nodes)

All devops nodes: `ttl=None` (event-driven), `persist=False`.

| Path | Depends On |
|------|------------|
| `devops.ci` | detect.ci, devops.git, devops.docker, devops.github |
| `devops.dns` | detect.dns |
| `devops.docker` | detect.docker, devops.git |
| `devops.docs` | detect.docs |
| `devops.env` | detect.env |
| `devops.git` | detect.git |
| `devops.github` | detect.github, devops.git |
| `devops.k8s` | detect.k8s, devops.docker |
| `devops.packages` | detect.packages |
| `devops.quality` | detect.quality |
| `devops.security` | detect.security |
| `devops.status` | devops.* (glob — all devops nodes) |
| `devops.terraform` | detect.terraform |
| `devops.testing` | detect.testing |

### 13.4 Posture Domain (6 nodes)

| Path | TTL | Persist | Depends On |
|------|-----|---------|------------|
| `posture.platform` | inf | Yes | — |
| `posture.toolchain` | 300 | Yes | — |
| `posture.project` | 60 | Yes | — |
| `posture.runtime` | 0 | No | — |
| `posture.full` | 60 | Yes | platform, toolchain, project, runtime |
| `posture.summary` | 30 | Yes | posture.full |

### 13.5 Extra Domain (20 nodes)

| Path | TTL | Persist | Depends On |
|------|-----|---------|------------|
| `extra.gh_pulls` | 120 | Yes | — |
| `extra.gh_runs` | 120 | Yes | — |
| `extra.gh_workflows` | 120 | Yes | — |
| `extra.project_status` | None | Yes | devops.status |
| `extra.wiz_detect` | 120 | Yes | — |
| `extra.audit_scores` | 300 | Yes | — |
| `extra.audit_system` | 300 | Yes | — |
| `extra.audit_deps` | 300 | Yes | — |
| `extra.audit_structure` | 300 | Yes | — |
| `extra.audit_clients` | 300 | Yes | — |
| `extra.tools` | 120 | Yes | — |
| `extra.builders` | 120 | Yes | — |
| `extra.scripts` | 120 | Yes | — |
| `extra.pages` | 120 | Yes | — |
| `extra.audit_system_deep` | 600 | Yes | — |
| `extra.audit_l2_structure` | 600 | Yes | — |
| `extra.audit_l2_quality` | 600 | Yes | — |
| `extra.audit_l2_repo` | 600 | Yes | — |
| `extra.audit_l2_risks` | 600 | Yes | — |
| `extra.audit_scores_enriched` | 600 | Yes | — |

---

## 14. Module Structure

```
src/core/services/mediator/
├── __init__.py          ← Singleton init, get_mediator()
├── core.py              ← QueryMediator class (get/put/bust/dispatch/subscribe/diag)
├── tree.py              ← DataTree + TreeNode + TreeRegistration
├── persistence.py       ← Disk shards (persist_node, hydrate_cache)
├── index_watcher.py     ← FS polling loop (index infrastructure)
├── registrations/
│   ├── __init__.py      ← register_all() — orchestrates registration order
│   ├── index.py         ← index.* nodes (scan, symbols, peek, classify, ...)
│   ├── detect.py        ← detect.* nodes (docker, k8s, ci, ...)
│   ├── devops.py        ← devops.* nodes (probes, status)
│   ├── posture.py       ← posture.* nodes (platform, toolchain, ...)
│   └── extra.py         ← extra.* nodes (gh API, audit, wizard, tools, builders, scripts, pages)
└── README.md            ← This file
```

---

*Last updated: 2026-03-13. Reflects v2 foundation with 62 registered nodes across 5 domains.*
