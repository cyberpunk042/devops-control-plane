# QueryMediator v2 — Foundation Requirements

> **Status:** Requirements — awaiting review  
> **Created:** 2026-03-13  
> **Parent:** `query-mediator-v2-milestone.md`  
> **Scope:** The core engine only. No domain-specific nodes (index,
> detect, devops, posture). Those are infrastructure and chunks that
> come AFTER the foundation is solid.

---

## 1. What Is the Foundation?

The foundation is the core mediator engine — the `QueryMediator`
class, the `DataTree`, the cache, and the persistence layer. It is
the skeleton on which everything else hangs.

The foundation must be complete and self-sufficient BEFORE any domain
node is registered. You should be able to instantiate a QueryMediator,
register arbitrary test nodes, get/put/bust them, persist to disk,
load from disk, subscribe to changes, and dispatch background work —
all without any knowledge of index, detect, devops, or posture.

---

## 2. The Data Tree

### REQ-TREE-1: Hierarchical Namespace

Nodes are addressed by dot-separated paths: `"domain.subdomain.leaf"`.
The tree supports arbitrary depth. Intermediate segments are auto-created
as branches. A branch can also be a registered node.

### REQ-TREE-2: Registration

A node is registered by providing:
- **path** — its dot-separated address
- **resolver** — the function that produces its value (nullable for virtual nodes)
- **ttl** — seconds before cached value expires (None = event-driven, inf = never expires)
- **persist** — whether the cached value survives restart (saved to disk)
- **depends_on** — list of paths this node depends on (supports glob patterns)

Registration must be idempotent for the same path. Re-registering a
path updates its metadata.

### REQ-TREE-3: Dependency Graph

The tree maintains a directed acyclic graph of dependencies:
- `depends_on` declares what a node reads
- `dependents` is the inverse — computed automatically
- Glob patterns in `depends_on` are resolved at registration time

When a node is invalidated, ALL its dependents (transitive) are also
invalidated. This is the cascade.

### REQ-TREE-4: Introspection

The tree must support:
- `all_paths()` — list every registered path
- `resolve(path)` — get the TreeNode for a path (or None)
- `dependents(path)` — get all transitive dependents
- `dependencies(path)` — get all transitive dependencies
- `stats()` — registered count, branch count, max depth, domains

### REQ-TREE-5: Immutability After Init

The tree structure is built during registration (startup) and is
read-only during normal operation. No locking is needed for reads.
The tree NEVER changes shape after the server starts handling requests.

---

## 3. The Cache

### REQ-CACHE-1: In-Memory Cache

The mediator maintains an in-memory dict mapping path → CacheEntry.
A CacheEntry contains:
- **data** — the computed value (any type)
- **computed_at** — timestamp when the value was computed
- **seq** — monotonic sequence number (global ordering)
- **source** — how the value was produced ("computed", "put", "disk")
- **elapsed_s** — how long the computation took (0 for put/disk)

### REQ-CACHE-2: TTL-Based Expiry

When `get(path)` is called and the cached entry exists but is older
than the node's TTL, the entry is STALE. The mediator recomputes
the value unless `stale_ok=True` was passed.

### REQ-CACHE-3: Stale-OK Behavior

`get(path, stale_ok=True)` returns stale data WITHOUT recomputing.
This is critical for non-blocking reads (context processors, SSE).

**Constraint:** `stale_ok` ONLY works when there IS cached data
(fresh or stale). On a completely empty cache (no entry at all),
`stale_ok` cannot help — there is nothing to return. The caller
must handle None or trigger computation explicitly.

### REQ-CACHE-4: Peek (Cache-Only Read)

`peek(path)` returns the cached value WITHOUT EVER triggering
computation. If the cache has no entry for this path, returns None.
This is the zero-cost read — it never blocks, never computes, never
has side effects.

### REQ-CACHE-5: Sequence Numbers

Every cache mutation (put, compute, disk-load) increments a global
sequence counter. This provides total ordering of all changes across
all nodes. Subscribers use sequence numbers to detect missed updates.

### REQ-CACHE-6: Thread Safety

All cache reads and writes are thread-safe. Per-path compute locks
prevent duplicate computation — if thread A is computing `index.scan`,
thread B's `get("index.scan")` waits for A's result instead of
starting a second computation.

---

## 4. The API — Core Operations

### REQ-API-1: get(path, force=False, stale_ok=False)

The fundamental read operation:
1. If `force=False` and cache has a fresh entry → return it
2. If `force=False` and cache has a stale entry and `stale_ok=True` → return it
3. If `force=True` OR cache miss OR stale without stale_ok:
   - Acquire per-path compute lock
   - Call the resolver
   - Store result in cache with new seq
   - Publish change event
   - Return result

Returns: `{ data, meta: { path, source, seq, elapsed_s, computed_at } }`

### REQ-API-2: put(path, data=None)

Inject data and/or invalidate:
- If `data` is provided: store it in cache (source="put")
- Always: cascade-invalidate all dependents (remove their cache entries)
- Publish change events for the path AND all invalidated dependents

This is how external signals (FS watcher, user action) enter the mediator.

### REQ-API-3: bust(path)

Pure invalidation — remove the cache entry for `path` and all its
transitive dependents. No data injection. No computation.

The cascade is the key: `bust("index.scan")` removes cache entries
for index.scan, index.delta, index.symbols, index.peek, index.classify,
detect.*, devops.*, posture.* — everything downstream. But it does
NOT call resolvers. The resolvers fire lazily when someone calls `get()`.

### REQ-API-4: dispatch(*paths)

Submit paths for background recomputation. Returns immediately.
The mediator uses the thread pool executor to call `get(path, force=True)`
for each path in the background.

**Constraint:** dispatch must only submit paths that have registered
resolvers and are actually worth recomputing. It must NOT blindly
dispatch everything in the tree.

### REQ-API-5: subscribe(pattern, callback)

Register a callback for changes matching a glob pattern.
When any matching path is computed or invalidated, the callback fires
with the path, new seq, and data summary.

Used by SSE streams to push live updates to the UI.

### REQ-API-6: refresh(*paths)

Smart recompute — check if the cached value is stale before
recomputing. Unlike `dispatch` (which always forces), `refresh`
skips nodes that are still fresh. This is the efficient way to
"make sure everything is current" without wasting work.

### REQ-API-7: diag()

Return the complete state of the mediator:
- Tree stats (node count, domains, depth)
- Cache stats (cached, stale, cold, refreshing)
- Per-node detail (age, source, seq, dependencies, stale flag)
- Global seq counter
- Active subscriptions
- Executor state

---

## 5. Cascade Invalidation

### REQ-CASCADE-1: Lazy Invalidation

`put()` and `bust()` only REMOVE cache entries. They do NOT call
resolvers. This is the most important design principle:

> The cost of cascade is ZERO until someone calls `get()`.

When a file changes, `put("index.scan")` removes ~42 cache entries
in microseconds. The resolvers only fire when a route or context
processor actually requests the data. If nobody asks for
`detect.docker` before the next change, it never recomputes.

### REQ-CASCADE-2: Transitive Dependents

Cascade follows the full dependency chain:
```
put("index.scan")
  → bust index.delta      (depends on index.scan)
  → bust index.symbols    (depends on index.delta)
  → bust index.peek       (depends on index.delta + index.symbols)
  → bust index.classify   (depends on index.scan)
  → bust detect.docker    (depends on index.classify)
  → bust devops.docker    (depends on detect.docker)
  ...
```

### REQ-CASCADE-3: No Circular Dependencies

The dependency graph must be a DAG. Registration must reject cycles.

### REQ-CASCADE-4: Cascade Depth Limit

Optional parameter on bust/put to limit cascade depth. Default is
unlimited (full transitive closure). This is a safety valve.

---

## 6. Persistence

### REQ-PERSIST-1: Sharded Disk Storage

Persisted nodes are saved to individual JSON files in a state
directory: `.state/mediator_index/<node_name>.json`

Each file contains the serialized data for ONE node. This allows:
- Incremental save (only write the shard that changed)
- Incremental load (load critical shards first)
- Easy debugging (human-readable JSON files)

### REQ-PERSIST-2: Atomic Writes

Shard files are written atomically: write to `.tmp`, then rename.
No partial writes. No corruption on crash.

### REQ-PERSIST-3: Save After Compute

When a node with `persist=True` is computed (via `get()` triggering
its resolver), the result is automatically saved to its shard file.
No manual save step required.

### REQ-PERSIST-4: Load on Startup (Hydration)

At startup, before any request is served, the mediator scans the
shard directory and loads all available shards into cache. This is
HYDRATION — it makes the cache WARM immediately.

After hydration:
- `peek(path)` returns data for all persisted nodes
- `get(path)` returns cached data without triggering resolvers
- The system is fully functional before the first request

### REQ-PERSIST-5: Staleness on Load

Loaded shards are marked with `source="disk"`. Their `computed_at`
timestamp is preserved from when they were originally computed. This
means TTL still applies — if data is old enough, `get()` will
recompute (but `peek()` and `stale_ok=True` still return it).

### REQ-PERSIST-6: Metadata Shard

A `meta.json` shard stores:
- Version number (for schema migration)
- Last save timestamp
- Node count
- Project root hash (to detect if shards belong to a different project)

---

## 7. Concurrency

### REQ-CONC-1: Thread Pool Executor

The mediator accepts an optional `Executor` (thread or process pool).
Background work (dispatch, refresh) runs on this executor. If no
executor is provided, background operations are no-ops.

### REQ-CONC-2: Per-Path Compute Locks

Each path has its own lock. When `get()` triggers computation for
path A, a concurrent `get()` for path A waits for the first
computation to complete and receives the same result. Concurrent
`get()` calls for DIFFERENT paths do not block each other.

### REQ-CONC-3: Refreshing Guard

A set tracks which paths are currently being recomputed. `dispatch()`
skips paths that are already in the refreshing set. This prevents
duplicate background work.

### REQ-CONC-4: GIL Awareness

The thread pool worker count must respect that Python's GIL limits
true parallelism for CPU-bound work. Workers should prioritize I/O-bound
resolvers (subprocess calls, disk reads) where threading provides real
benefit. CPU-bound resolvers (symbol parsing) may need different
scheduling.

---

## 8. Events and Observability

### REQ-OBS-1: Change Events

Every cache mutation publishes an event on the EventBus:
- `mediator:computed` — a resolver produced a new value
- `mediator:put` — external data was injected
- `mediator:bust` — a cache entry was invalidated
- `mediator:hydrated` — a shard was loaded from disk

Events include: path, seq, timestamp, source.

### REQ-OBS-2: Subscription Notifications

Registered subscribers receive callbacks when matching paths change.
Callbacks run in the publishing thread (keep them fast).

### REQ-OBS-3: Diagnostic Endpoint

`diag()` returns a complete snapshot of the mediator state. This
powers the debug tab in the UI. It must be cheap (no computation,
just reading cache state).

---

## 9. Performance Requirements

### REQ-PERF-1: Startup Hydration

Loading all persisted shards into cache must complete in <100ms
for a typical project (10-15 shards, total ~2MB).

### REQ-PERF-2: Cache Read (peek/get with hit)

A cache hit (peek or get with fresh data) must complete in <1ms.
This is a dict lookup + staleness check. Nothing more.

### REQ-PERF-3: Cascade Cost

`bust(path)` or `put(path)` cascade invalidation must complete in
<5ms for a tree of ~42 nodes. This is dict key deletion, not
computation.

### REQ-PERF-4: Persistence Write

Saving a single shard to disk must complete in <50ms for a typical
shard (~100KB JSON). Writes happen in the compute path, so they
add latency to `get()` calls. Keep them fast.

### REQ-PERF-5: No Impact on Request Serving

Background dispatch work must NOT measurably slow down Flask request
handling. If background workers cause GIL contention that increases
API response times by >10%, the worker count must be reduced or
workers must yield.

---

## 10. What Is NOT in the Foundation

The following are explicitly OUT OF SCOPE for the foundation. They
belong in infrastructure (Phase 5-6) or chunks (Phase 7+):

- **Index nodes** (scan, delta, symbols, peek, classify, etc.)
- **Detect nodes** (docker, k8s, git, etc.)
- **DevOps nodes** (merged cards, status)
- **Posture nodes** (platform, toolchain, project, etc.)
- **FS watcher** (drives index.scan — belongs in index infrastructure)
- **SSE streaming** (consumes events — belongs in web layer)
- **Debug tab UI** (consumes diag — belongs in web layer)
- **Context processor migration** (consumes peek — belongs in Phase 8)
- **Legacy removal** (belongs in Phase 9)
- **Extra.* domain** (does not exist — NEVER build this)

The foundation provides the ENGINE. The domains provide the FUEL.
Build the engine first. Add fuel later.

---

## 11. Verification Criteria

The foundation is COMPLETE when these tests pass:

### Functional Tests

1. Register a node with resolver → `get()` calls resolver → returns data
2. `get()` a second time → returns cached, resolver NOT called
3. `put(path)` → dependents invalidated → next `get()` recomputes them
4. `bust(path)` → cache entry removed → next `get()` recomputes
5. `peek(path)` on empty cache → returns None (no computation)
6. `peek(path)` on populated cache → returns data (no computation)
7. `stale_ok=True` on stale entry → returns stale data (no recompute)
8. `stale_ok=True` on empty cache → falls through to computation
9. Cascade: `bust(A)` where B depends on A → B's cache entry removed
10. Cascade: 3 levels deep → all entries removed
11. Circular dependency → rejected at registration time
12. `dispatch(paths)` → background computation → results in cache
13. `subscribe(pattern, cb)` → callback fires on matching put/compute
14. `diag()` → returns accurate state snapshot

### Persistence Tests

15. `persist=True` node computed → shard file written to disk
16. Shard file exists on startup → hydration loads it into cache
17. After hydration, `peek(path)` returns data (no computation needed)
18. Atomic write: crash during save → shard file not corrupted
19. Multiple shards: each saved/loaded independently
20. Meta shard: version, timestamp, node count correct

### Concurrency Tests

21. Two threads `get()` same path → resolver called ONCE
22. Two threads `get()` different paths → both proceed in parallel
23. `dispatch()` while path is refreshing → skipped (no duplicate)
24. Thread pool background work completes → results in cache

### Performance Tests

25. Hydration of 15 shards (<2MB total) → <100ms
26. `peek()` on hot cache → <1ms
27. `bust()` cascade across 42 nodes → <5ms
28. Shard write (100KB) → <50ms

---

*End of foundation requirements.*
*Next document: Foundation Implementation Plan.*
