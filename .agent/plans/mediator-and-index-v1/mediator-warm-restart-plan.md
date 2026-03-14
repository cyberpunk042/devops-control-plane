# Mediator Warm Restart — Engineering Plan

> **Goal:** On server restart, the mediator hydrates ALL persistable data from disk.
> No "reset from scratch." Only delta gets recomputed. The system was DESIGNED for this
> (persist flags, shard system, hydration).
>
> **Status (2026-03-13):** Phases A, B, C ✅ complete. Phase D (per-node deserializer) future.
> `core.py` now gates `persist_node()` on `node.persist` — devops nodes (persist=False) skip disk I/O.

---

## Current State (What Exists)

### What IS built

1. **Tree nodes declare `persist=True`** — the metadata flag exists on TreeRegistration
   and TreeNode. Every domain already marks which nodes should persist:
   - **Posture**: 5 of 6 nodes have `persist=True` (all except `posture.runtime` which is TTL=0)
   - **Detect**: 11 of 13 nodes have `persist=True` (all except `detect.git`, `detect.env`)
   - **Index**: 4 nodes persisted via SHARD_MAP (scan, symbols, peek, classify)
   - **DevOps**: 0 — `persist=False` by design (devops nodes wrap `get_cached()` which has its own file persistence)

2. **Persistence layer** (`persistence.py`) — can save/load JSON shards to `.state/mediator_index/`

3. **Hydration** (`hydrate_cache()`) — called at startup, loads shards and injects via `put(cascade=False)`

4. **Index watcher** — has warm/cold detection logic

### What IS NOT connected

1. **`persist` flag is IGNORED by persistence.py** — the shard system uses a hardcoded
   `SHARD_MAP` of 4 index nodes. It does NOT read `node.persist` from the tree.
   Nodes that declare `persist=True` (posture.*, detect.*) are never saved.

2. **No save-on-compute hook** — when detect/posture nodes compute, nobody calls
   `save_shard()`. Only index nodes have the `_persisting()` wrapper in `registrations/index.py`.

3. **Deserialization type loss** — JSON flattens dataclass objects (FileEntry, IndexSymbolEntry)
   to plain dicts. The `_rehydrate_shards()` function exists but is specific to index types.
   A generic solution is needed for all persist-flagged nodes.

4. **`dispatch()` always uses `force=True`** — `_dispatch_worker` calls `get(force=True)`,
   which bypasses cache even when data was just hydrated from disk. On warm start, this
   means symbols/peek/detect.* recompute unnecessarily.

5. **Watcher `t0` crash** — the warm path skips Phase 1 (where `t0` is set) but code after
   Phase 2 references `t0` for elapsed time. Crashes the watcher loop on warm start.

---

## Gap Analysis

| Requirement | Status | Gap |
|-------------|--------|-----|
| Nodes declare persist intent | ✅ Done | — |
| Persistence saves on compute | ⚠️ Index only | Not connected to persist flag |
| Persistence loads on startup | ⚠️ Index only | Hardcoded SHARD_MAP |
| Hydration injects into cache | ⚠️ Index only | Only 4 shards, no posture/detect |
| Warm path skips recomputation | ⚠️ Index only | Dispatch still force=True for all |
| Type-safe deserialization | ⚠️ Index only | Only FileEntry/IndexSymbolEntry handled |
| Watcher warm path works | ❌ Broken | `t0` crash kills loop |
| Status view shows warm state | ⚠️ Partial | Index events fire, but dispatch nodes don't |

---

## The Engineering Solution

### Phase A: Fix What's Broken Now (bugs from this session)

**A1. Fix `t0` crash in index_watcher.py**
- The warm path skips Phase 1 but Phase 2's tail references `t0`
- Fix: initialize `t0 = time.time()` before the warm/cold branch

**A2. Verify `_rehydrate_shards` actually runs**
- Add a log line inside `_rehydrate_shards` confirming conversion counts
- Verify the warm path produces proper FileEntry objects

### Phase B: Generic Persist-on-Compute (the missing hook)

**B1. Save on compute for ALL persist-flagged nodes**

Instead of the index-specific `_persisting()` wrapper, move save-on-compute into
the mediator core. When `get()` computes a value (resolver runs), check `node.persist`
and save to disk:

```python
# In QueryMediator.get(), after resolver succeeds:
if node.persist and result is not None:
    self._save_to_disk(path, result)
```

Or alternatively, in `put()` when data is written:
```python
if node.persist and data is not None and notify:
    self._save_to_disk(path, data)
```

This replaces the per-domain `_persisting()` wrapper pattern with a single
centralized hook. Every node with `persist=True` gets automatic disk persistence.

**B2. Generic shard naming**

Replace the hardcoded `SHARD_MAP` with path-based naming:
```
index.scan     → .state/mediator_cache/index.scan.json
detect.docker  → .state/mediator_cache/detect.docker.json
posture.full   → .state/mediator_cache/posture.full.json
```

The shard directory becomes `.state/mediator_cache/` (renamed from `mediator_index/`
since it's no longer index-specific). Each persist-flagged node gets its own JSON file.

**B3. Generic hydration**

Replace the hardcoded shard loading with tree-driven loading:
```python
def hydrate_cache(mediator, project_root):
    shard_dir = project_root / ".state/mediator_cache"
    for node in mediator.tree.all_registered():
        if node.persist:
            path = shard_dir / f"{node.path}.json"
            if path.exists():
                data = json.loads(path.read_text())
                mediator.put(node.path, data, cascade=False, notify=False)
```

### Phase C: Smart Dispatch (don't recompute what's cached)

**C1. Teach dispatch to respect cache**

`_dispatch_worker` currently does `get(force=True)` unconditionally. Change it to
check if the node is already cached (from hydration) and skip if fresh:

```python
def _dispatch_worker(self, task_id, paths):
    for p in paths:
        try:
            # If already cached and fresh, skip recompute
            node = self._tree.resolve(p)
            entry = self._get_cached(p)
            if entry is not None and not force_needed(entry, node):
                self.clear_refreshing(p)
                continue
            self.get(p, force=True)
        except Exception:
            ...
        finally:
            self.clear_refreshing(p)
```

**C2. Watcher warm path — dispatch only what's missing**

On warm start, instead of dispatching ALL detect/devops/posture nodes, only dispatch
nodes that are NOT cached:

```python
bg_paths = [
    p for p in all_paths
    if p.startswith(("detect.", "devops.", "posture."))
    and self._get_cached(p) is None  # not cached from hydration
]
```

### Phase D: Type-Safe Deserialization

**D1. Per-node deserializer registry**

Each registration can optionally declare a `deserializer` function:
```python
TreeRegistration(
    path="index.scan",
    resolver=...,
    persist=True,
    deserializer=lambda data: {k: FileEntry(**v) for k, v in data.items()},
)
```

During hydration, if a deserializer exists, it's called before `put()`. This
replaces the monolithic `_rehydrate_shards()` with per-node type safety.

For domains that use plain dicts (detect, posture), no deserializer is needed —
JSON round-trips cleanly.

---

## Execution Order

```
Phase A — Fix broken code (5 min)
  A1: Fix t0 crash
  A2: Verify rehydration

Phase B — Generic persistence (30 min)
  B1: Save-on-compute hook in core.py
  B2: Generic shard directory
  B3: Generic hydration

Phase C — Smart dispatch (15 min)
  C1: dispatch respects cache
  C2: warm path dispatches only uncached

Phase D — Type safety (10 min)
  D1: Per-node deserializer on TreeRegistration
```

---

## Success Criteria

1. **Cold start** (no shards on disk): full compute, all persist-flagged nodes saved to disk
2. **Warm start** (shards exist): hydrate from disk, skip recompute for cached nodes,
   only dispatch uncached/stale nodes. Wall time < 5 seconds for index-related work.
3. **No crashes**: watcher loop runs cleanly on both warm and cold paths
4. **Status view**: shows accurate state on both warm and cold starts
5. **No type errors**: deserialized data works with downstream resolvers

---

## Files Affected

| File | Change |
|------|--------|
| `core.py` | Save-on-compute hook in `get()` or `put()` |
| `persistence.py` | Generic shard dir, generic hydration, remove SHARD_MAP |
| `tree.py` | Optional `deserializer` field on TreeRegistration/TreeNode |
| `index_watcher.py` | Fix t0 crash, smart dispatch on warm path |
| `registrations/index.py` | Remove `_persisting()` wrapper (moved to core), add deserializer |

---

## What This Does NOT Change

- DevOps nodes (`devops.*`) stay `persist=False` — they wrap `get_cached()` which has its own persistence
- `detect.git` and `detect.env` stay `persist=False` — they are volatile by nature (TTL=30s / TTL=60s, no persist)
- `posture.runtime` stays `persist=False` — TTL=0, always fresh
- The mediator's core API (get/put/diag) stays identical
- The frontend event flow stays identical
