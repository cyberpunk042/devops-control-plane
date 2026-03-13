# QueryMediator

> **Package:** `src/core/services/mediator/`
> **Role:** Central data hub — trilateral mediation between Backend, Cache, and Index.

---

## What It Does

The QueryMediator is a coordination layer that sits between all data
producers (scanners, detectors, file system) and all data consumers
(API routes, background jobs). It provides:

1. **Unified query interface** — one `get()` call for any data, regardless
   of whether it comes from cache, index, or fresh computation.
2. **Hierarchical namespace** — dot-separated paths (`posture.toolchain`,
   `devops.docker`, `detect.tools.go`) instead of flat keys.
3. **Cascade invalidation** — declarative dependency graph. Invalidating
   a node automatically invalidates everything that depends on it.
4. **Per-path compute locks** — only one thread computes a given path at
   a time. Others wait and get the cached result.
5. **Diagnostics** — `diag()` returns full tree state, cache ages, and
   staleness information.

---

## Architecture

```
 ┌─────────────────────────────────────────────────┐
 │               API ROUTES                         │
 │   mediator.get("posture.toolchain")              │
 └──────────────────────┬──────────────────────────┘
                        │
 ┌──────────────────────┴──────────────────────────┐
 │              QueryMediator                       │
 │                                                  │
 │  get() → cache check → compute lock → resolve    │
 │  put() → write/invalidate → cascade → publish    │
 │  diag() → tree + cache state                     │
 └───────┬──────────────────┬──────────────────────┘
         │                  │
    ┌────┴────┐        ┌────┴────┐
    │DataTree │        │ Cache   │
    │(metadata│        │ (data)  │
    │ registry│        │ entries │
    └─────────┘        └─────────┘
```

---

## Module Structure

```
mediator/
├── __init__.py           ← public API, singleton (init, get_mediator, mediator)
├── tree.py               ← DataTree, TreeNode, TreeRegistration
├── core.py               ← QueryMediator, CacheEntry
├── README.md             ← this file
└── registrations/
    ├── __init__.py       ← register_all() — called at startup
    ├── posture.py        ← posture.* domain registration (6 nodes)
    ├── detect.py         ← detect.* domain registration (13 nodes)
    └── devops.py         ← devops.* domain registration (13 nodes)
```

---

## Public API

### Initialization

```python
from src.core.services.mediator import init, get_mediator, mediator

# During server startup (server.py):
init(project_root)

# Anywhere else:
m = get_mediator()    # raises RuntimeError if not initialized
# or:
m = mediator          # may be None if not initialized
```

### Registering Nodes

```python
from src.core.services.mediator import get_mediator, TreeRegistration

m = get_mediator()
m.tree.register(TreeRegistration(
    path="posture.toolchain",
    resolver=scan_toolchain,
    ttl=300,               # 5 minutes
    persist=True,          # save to disk
    depends_on=["detect.tools.*"],
))
```

### Querying Data

```python
result = m.get("posture.toolchain")
# result = {
#     "data": <PillarResult>,
#     "meta": {
#         "path": "posture.toolchain",
#         "source": "computed",     # or "cache"
#         "age_s": 0.0,
#         "seq": 42,
#     }
# }

# With options:
result = m.get("posture.toolchain", force=True)       # bypass cache
result = m.get("posture.toolchain", max_age=30)        # accept if < 30s old
result = m.get("posture.toolchain", explain=True)      # include resolution trace
```

### Writing / Invalidating

```python
# Write data explicitly:
m.put("posture.toolchain", data=pillar_result)

# Invalidate (delete from cache, cascade to dependents):
m.put("posture.toolchain", cascade=True)

# Invalidate without cascade:
m.put("posture.toolchain", cascade=False)
```

### Diagnostics

```python
# Full summary:
info = m.diag()
# info = {
#     "tree": {"total_nodes": 42, "registered": 18, ...},
#     "seq": 158,
#     "cached": 12,
#     "stale": 2,
#     "entries": {"posture.toolchain": {"age_s": 42, "stale": false}, ...}
# }

# Single node detail:
info = m.diag("posture.toolchain")
```

---

## Thread Safety

- **`_lock`** protects the cache dict and sequence counter.
- **`_compute_locks`** provides per-path locking: if two threads request
  the same path simultaneously, one computes and the other waits for
  the cached result.
- The DataTree is read-only after initialization — no locking needed.

This matches the patterns in `system_posture/cache.py` (per-key locks)
and `devops/cache.py` (`_lock` + `_file_lock`).

---

## Dependency Graph

Nodes declare `depends_on` at registration. The tree auto-computes
reverse dependencies (`dependents`). When a node is invalidated with
`cascade=True`, all dependents are also invalidated.

```
posture.toolchain  ──depends_on──→  detect.tools.*
posture.full       ──depends_on──→  posture.toolchain, posture.platform, ...
posture.summary    ──depends_on──→  posture.full

Invalidating detect.tools.go cascades:
  detect.tools.go → posture.toolchain → posture.full → posture.summary
```

Glob patterns (`detect.tools.*`) are expanded at cascade time,
so newly registered nodes are automatically included.

---

## Domain Registrations

Domain-specific node registrations live in `registrations/`. Each
domain has its own module that registers nodes during startup.

### Posture Domain (`registrations/posture.py`)

Registers 6 nodes matching the existing posture cache keys:

| Path | TTL | Persist | Resolver | Depends On |
|------|-----|---------|----------|------------|
| `posture.platform` | ∞ | ✓ | `_scan_platform()` | — |
| `posture.toolchain` | 300s | ✓ | `_scan_toolchain()` | — |
| `posture.project` | 60s | ✓ | `_bridge_project(root)` | — |
| `posture.runtime` | 0s | ✗ | `_bridge_runtime()` | — |
| `posture.full` | 60s | ✓ | assembled from pillars via mediator | all 4 pillars |
| `posture.summary` | 30s | ✓ | `.to_summary_dict()` from full | `posture.full` |

Cascade chain: `pillar → posture.full → posture.summary`

### Detection Domain (`registrations/detect.py`)

Registers 13 nodes wrapping the devops cache compute registry:

| Path | TTL | Persist | Resolver |
|------|-----|---------|----------|
| `detect.docker` | 120s | ✓ | `docker_ops.docker_status(root)` |
| `detect.k8s` | 120s | ✓ | `k8s_ops.k8s_status(root)` |
| `detect.git` | 30s | ✗ | `git_ops.git_status(root)` |
| `detect.github` | 120s | ✓ | `git_ops.gh_status(root)` |
| `detect.ci` | 120s | ✓ | `ci_ops.ci_status(root)` |
| `detect.terraform` | 120s | ✓ | `terraform_ops.terraform_status(root)` |
| `detect.env` | 60s | ✗ | `env_ops.env_card_status(root)` |
| `detect.security` | 120s | ✓ | `security_ops.scan_secrets()` + `security_posture()` |
| `detect.packages` | 120s | ✓ | `package_ops.package_status_enriched(root)` |
| `detect.quality` | 120s | ✓ | `quality_ops.quality_status(root)` |
| `detect.testing` | 120s | ✓ | `testing_ops.testing_status(root)` |
| `detect.docs` | 120s | ✓ | `docs_ops.docs_status(root)` |
| `detect.dns` | 120s | ✓ | `dns_cdn_ops.dns_cdn_status(root)` |

All detection nodes are independent leaves (no `depends_on`). They wrap
the same ops functions used by the devops cache's `_ensure_registry()`,
providing TTL-based caching where none existed before.

### DevOps Domain (`registrations/devops.py`)

Registers 13 nodes that **wrap `get_cached()`** from the devops cache module.
This preserves all devops cache side effects (mtime checking, activity logging,
audit staging, EventBus publishing, file persistence).

| Path | Cache Key | TTL | Persist | Depends On |
|------|-----------|-----|---------|------------|
| `devops.docker` | `"docker"` | None | ✗ | `detect.docker` |
| `devops.k8s` | `"k8s"` | None | ✗ | `detect.k8s` |
| `devops.git` | `"git"` | None | ✗ | `detect.git` |
| `devops.github` | `"github"` | None | ✗ | `detect.github` |
| `devops.ci` | `"ci"` | None | ✗ | `detect.ci` |
| `devops.terraform` | `"terraform"` | None | ✗ | `detect.terraform` |
| `devops.env` | `"env"` | None | ✗ | `detect.env` |
| `devops.security` | `"security"` | None | ✗ | `detect.security` |
| `devops.packages` | `"packages"` | None | ✗ | `detect.packages` |
| `devops.quality` | `"quality"` | None | ✗ | `detect.quality` |
| `devops.testing` | `"testing"` | None | ✗ | `detect.testing` |
| `devops.docs` | `"docs"` | None | ✗ | `detect.docs` |
| `devops.dns` | `"dns"` | None | ✗ | `detect.dns` |

**TTL=None (mtime-delegated):** Freshness is determined by `get_cached`'s
own mtime logic, not the mediator's TTL system.

**persist=False:** The devops cache handles its own file persistence.

**Cross-domain cascade:** `detect.docker` → `devops.docker`. Invalidating
a detection node automatically invalidates the corresponding devops node.

**Bust integration:** The devops cache bust handler (`POST /devops/cache/bust`)
also invalidates mediator nodes via `_mediator_bust()`.

### Cascade Engine (Phase 4)

Phase 4 migrated the devops cache's hardcoded `_CASCADE` dict into the
mediator's declarative dependency graph.

**Inter-devops dependencies** (mirrors `_CASCADE`):
```
devops.github   depends_on=[detect.github, devops.git]
devops.docker   depends_on=[detect.docker, devops.git]
devops.ci       depends_on=[detect.ci, devops.git, devops.docker, devops.github]
devops.k8s      depends_on=[detect.k8s, devops.docker]
```

**Aggregate node:** `devops.status` depends on `devops.*` (glob).
Replaces `_AGGREGATE_KEYS = ["project-status"]`.

**`invalidate_with_cascade()`** now tries the mediator graph first,
falling back to the legacy `_CASCADE` dict when the mediator is not
initialized (CLI, tests, non-web contexts).

**Cascade visualization:**
```
detect.git
  └→ devops.git
       ├→ devops.docker
       │    ├→ devops.k8s
       │    │    └→ devops.status
       │    ├→ devops.ci
       │    │    └→ devops.status
       │    └→ devops.status
       ├→ devops.github
       │    ├→ devops.ci  (already visited — skipped)
       │    └→ devops.status
       ├→ devops.ci  (already visited — skipped)
       └→ devops.status
```

### EventBus Bridge (Phase 5)

Phase 5 makes the mediator observable by bridging to the EventBus.

**Event types published by `put()`:**
- `mediator:write` — new data was written to a path
- `mediator:invalidated` — paths were invalidated (cascade or direct)

**Payload structure:**
```json
{
    "trigger": "devops.git",
    "mediator_seq": 201,
    "writes": ["devops.git"],
    "invalidated": ["devops.docker", "devops.github", "devops.ci"]
}
```

**`since_seq` parameter on `get()`:**
```python
# Consumer tracks its last-seen seq
result = mediator.get("devops.docker", since_seq=142)
# Returns {"changed": False, ...} if nothing changed since seq 142
# Returns {"data": ..., "meta": {...}} if data changed
```

**`notify=False`** suppresses EventBus publishing (for cache warming, tests).

**Batch mode** accumulates changes and publishes one aggregate event:
```python
with mediator.batch():
    mediator.put("devops.git", data=git_data)
    mediator.put("devops.docker", data=docker_data)
    mediator.put("devops.ci", data=ci_data)
# → ONE mediator:write event listing all 3 paths
```

### subscribe() + stale-while-revalidate (Phase 6A)

Phase 6A adds in-process subscribers and zero-latency stale reads.

**subscribe()** — pure callback registry:
```python
# Register a callback for path patterns (fnmatch glob syntax)
sub_id = mediator.subscribe("devops.*", my_callback)

# Callback signature
def my_callback(event: dict) -> None:
    # event = {"type": "write"|"invalidated", "trigger": "devops.git",
    #          "seq": 201, "paths": ["devops.git"]}
    pass  # must be fast (< 1ms)

# Unsubscribe
mediator.unsubscribe(sub_id)
```

**stale_ok** — return stale data instantly:
```python
result = mediator.get("posture.toolchain", stale_ok=True)
# If cache is stale: returns immediately with meta.stale=True
# If cache is fresh: normal return
# If no cache: falls through to blocking compute

# Meta when stale:
# {"source": "cache_stale", "stale": true, "refreshing": false}
```

**on_stale hook** — dependency-injected background recompute:
```python
# Production: hook spawns a daemon thread
mediator = QueryMediator(tree, project_root, on_stale=my_handler)
# Tests: hook is None (default) or a mock. Zero threading in tests.
```

**refreshing state** — explicit tracking:
```python
mediator.mark_refreshing("posture.toolchain")  # bg thread started
mediator.clear_refreshing("posture.toolchain")  # bg thread done
# get(stale_ok=True) includes meta.refreshing=True/False
```

### refresh() + bust() + dispatch() (Phase 6B)

Phase 6B adds bulk recompute, temporal invalidation, and async dispatch.

**refresh()** — force recompute one or more paths:
```python
# Single path
results = mediator.refresh("posture.toolchain")

# Multiple paths (uses executor if configured)
results = mediator.refresh("posture.toolchain", "posture.platform")
# → {"refreshed": {path: meta}, "errors": {}, "elapsed_s": 0.5}

# Branch shortcut — all nodes under a prefix
results = mediator.refresh_branch("posture")

# Only stale nodes
results = mediator.refresh_stale(prefix="devops")
```

**bust()** — temporal invalidation:
```python
# Invalidate entries older than 5 minutes
mediator.bust(max_age=300)

# Only devops branch
mediator.bust(max_age=300, prefix="devops")
# → {"busted": ["devops.git", ...], "count": 3}
```

**dispatch()** — async background recompute:
```python
task = mediator.dispatch("posture.toolchain", "posture.platform")
# → {"task_id": "task-1", "paths": [...], "status": "dispatched"}
# Returns immediately. Work happens in executor or via on_stale hook.
# Paths are marked as refreshing → stale_ok reads show refreshing=True.
```

**Executor injection** — parallelism without threads in mediator:
```python
from concurrent.futures import ThreadPoolExecutor

# Production: concurrent refresh
mediator = QueryMediator(tree, root, executor=ThreadPoolExecutor(4))

# Tests: sequential (default, executor=None)
mediator = QueryMediator(tree, root)
```

### Adding a New Domain

1. Create `registrations/<domain>.py` with `register_<domain>(mediator)`
2. Import and call it from `register_all()` in `registrations/__init__.py`
3. Define `TreeRegistration` for each data node

---

## TTL=0 Behavior

Nodes with `ttl=0` (like `posture.runtime`) are **never cached**.
Every `get()` call invokes the resolver directly. This matches
the existing `system_posture/cache.py` behavior where `TTL=0`
means "always fresh."

---

## Dual-Path Validation

During Phase 1 integration, routes support `?via=mediator`:

```
GET /api/posture/summary               → existing direct path
GET /api/posture/summary?via=mediator   → mediator path
```

Both return identical JSON. The mediator path is opt-in for
validation — default behavior is completely unchanged.

---

## Design Decisions

1. **Metadata vs data separation** — The DataTree holds metadata (paths,
   resolvers, TTLs, dependencies). The QueryMediator holds data (cache
   entries). This keeps the tree immutable after startup.

2. **Singleton pattern** — Matches `event_bus.bus`, `devops/cache`,
   `system_posture/cache`. One global mediator, initialized at startup.

3. **Standard result format** — Every `get()` returns
   `{"data": ..., "meta": {...}}`. The meta always includes source,
   age, and seq. This enables the frontend to make caching decisions.

4. **Resolvers call raw functions** — Mediator resolvers call the
   scanner/bridge functions directly, not the cached `get_or_compute()`
   wrappers. The mediator IS the cache layer.

5. **Dual caching is temporary** — During Phase 1, both the mediator
   and the existing posture cache are active. This is by design for
   validation. Once proven equivalent, the old cache becomes unused.

6. **One aggregate event per `put()`** — When a cascade invalidates
   multiple paths, ONE event fires listing all affected paths.
   This lets consumers batch their reactions instead of reacting N times.

7. **Path-level delta, not field-level** — `since_seq` returns "changed
   or not changed" at the path level. Field-level diffing is a future
   optimization on top of this foundation.

8. **Mediator stays pure — no threading inside** — Background recompute
   is handled via the injected `on_stale` hook. The mediator itself has
   zero threading code. Tests are deterministic and synchronous.

9. **Subscribers are synchronous** — Callbacks run inline in `put()`,
   same pattern as EventBus. Contract: callbacks must be fast. Errors
   are logged and swallowed (one bad subscriber doesn't block others).

10. **refresh() reuses get(force=True)** — No new compute logic.
    `refresh()` is simply "parallel `get(force=True)` for multiple paths."
    This keeps the compute path single and well-tested.

11. **Executor injection for parallelism** — The mediator accepts an
    optional `Executor` (any `concurrent.futures.Executor` subclass).
    In production, a `ThreadPoolExecutor`. In tests, None (sequential).
    The mediator never creates threads itself.

---

## Phase Roadmap

| Phase | Scope |
|-------|-------|
| **0** ✓ | Tree registry, mediator core (get/put/diag), module skeleton |
| **1** ✓ | First wire — posture system through mediator (6 nodes, dual-path) |
| **2** ✓ | Detection dedup layer (13 detect.* nodes) |
| **3** ✓ | DevOps cache wire (13 devops.* nodes, 32 total) |
| **4** ✓ | Cascade engine (inter-devops deps, devops.status aggregate, 33 total) |
| **5** ✓ | EventBus bridge + path delta (since_seq, batch mode, 171 tests) |
| **6A** ✓ | subscribe() + stale-while-revalidate (pure, 201 tests) |
| **6B** ✓ | refresh + bust + dispatch (executor-injected, 232 tests) |
| 7 | Debug view (web UI tab) |
