# QueryMediator — Architecture Model

> **Companion to:** `query-mediator-milestone.md` (census + vision)
> **Purpose:** Crystallize the internal model so we can validate
> it BEFORE writing the implementation plan.
> **Status:** Evolving — not finalized.

---

## 1. The Trilateral — Why Exactly Three

The user's words:

> Backend → Mediator
> Cache   → Mediator
> Index   → Mediator

This is not an arbitrary grouping. These are three fundamentally
different ROLES in the data lifecycle:

```
 INDEX    = what IS (truth — filesystem, subprocess output, config)
 CACHE    = what WAS (acceleration — remembered results, TTL/mtime)
 BACKEND  = what's ASKED (demand — routes, scanners, background jobs)
```

The mediator exists because these three roles should NEVER talk
directly to each other. Today they do:

```
 ❌ Today: route → cache.get() → if miss → scanner() → subprocess → cache.set()
           The route KNOWS about the cache. The scanner KNOWS nothing about the cache.
           The index is not even consulted. Three systems, zero coordination.

 ✅ After: route → mediator.get("posture.toolchain") → done.
           The mediator decides: cache? index? fresh scan? stale-while-revalidate?
           The route doesn't care HOW. The scanner doesn't care WHO asked.
```

### Why NOT the UI?

> "because its upstream its receiving the informations and when it wants
> it refresh naturally over time or show that new information is available,
> it offers manual refresh"

The UI is a CONSUMER, not a PARTICIPANT. It has its own cache
(sessionStorage) but that's a delivery optimization, not a data source.
The trilateral is about the data PLANE. The UI is about the
PRESENTATION plane. They connect through SSE and API calls, but
the UI doesn't need to be inside the mediator — it just asks and
receives.

```
 ┌─────────────────────────────────────────────────────────┐
 │  PRESENTATION PLANE (UI)                                │
 │  sessionStorage cache, SSE listener, poll timers        │
 │  ← receives events, requests data, offers manual refresh│
 └──────────────────────────┬──────────────────────────────┘
                            │ (API / SSE)
 ═══════════════════════════╪═══════════════════════════════
                            │
 ┌──────────────────────────┴──────────────────────────────┐
 │                   DATA PLANE                             │
 │  ┌─────────────────────────────────────────────┐        │
 │  │              MEDIATOR                        │        │
 │  │  coordinates, routes, deduplicates, cascades │        │
 │  └──────┬──────────────┬──────────────┬────────┘        │
 │         │              │              │                  │
 │    ┌────┴────┐    ┌────┴────┐    ┌────┴────┐            │
 │    │ BACKEND │    │  CACHE  │    │  INDEX  │            │
 │    │ (demand)│    │ (memory)│    │ (truth) │            │
 │    └─────────┘    └─────────┘    └─────────┘            │
 └─────────────────────────────────────────────────────────┘
```

---

## 2. The Index — Foundation at the Bottom

> "index sitting at the bottom, we want to make this graceful and strong"

The index is NOT a cache. The index is the TRUTH MAP. It answers:
"what exists, where is it, what is its state."

Today this truth is scattered across 21+ detection/probe functions
that each independently call subprocesses and read files. The index
unifies them.

### What the Index holds

```
index
├── filesystem
│   ├── file_map       ← filename → [paths]  (already exists in project_index)
│   ├── dir_map        ← dirname → [paths]   (already exists in project_index)
│   ├── symbols        ← symbol → [locations] (already exists in project_index)
│   └── watchers       ← path → {mtime, subscribers}
│
├── environment
│   ├── os             ← {distro, version, kernel, glibc, arch, wsl}
│   ├── hardware       ← {gpu, cpu_features, build_toolchain}
│   ├── network        ← {proxy, connectivity}
│   ├── sandbox        ← {container_type, ci_env}
│   └── terminal       ← {type, capabilities}
│
├── tools
│   ├── {tool_name}    ← {version, path, method, lifecycle_status}
│   │                     one entry per installed tool
│   └── (indexed from scan_toolchain + tool_install detection)
│
├── project
│   ├── stacks         ← detected languages/frameworks
│   ├── modules        ← detected project modules
│   ├── probes         ← {git, github, docker, k8s, terraform, pages, dns, ci}
│   │                     consolidated from project_probes.py
│   └── config         ← project.yml / devops_prefs parsed
│
└── services
    ├── docker         ← {daemon, compose, images}
    ├── k8s            ← {kubectl, helm, cluster_status}
    ├── chrome         ← {binary, profiles, debug_port}
    └── wsl            ← {channel, tunnel_state}
```

### Critical insight: Index ≠ Cache

The index doesn't have TTLs. It doesn't expire. It is REFRESHED
when the source of truth changes:

- **Filesystem changes** → mtime watcher detects → index.filesystem refreshes
- **Tool installed** → mediator.dispatch("rescan.tools.go") → index.tools.go refreshes
- **Docker started** → next probe detects → index.services.docker refreshes
- **OS doesn't change** → index.environment.os is populated once, forever

The CACHE sits on top of the index. The cache remembers computed
RESULTS (card HTML, posture pillars, audit scores). The index
remembers raw FACTS (file paths, tool versions, service states).

```
 RESULT (cached):  "Docker card shows 3 containers running, compose v2.24.0"
 FACT (indexed):   "docker at /usr/bin/docker, version 27.5.1, daemon running"

 The RESULT depends on the FACT. When the FACT changes, the RESULT
 is stale — but the FACT itself is always either current or refreshed.
```

---

## 3. The Tree — Branches Before Leaves

> "Allow ourselves to build a tree with multiple layers of branches
> before the leaves."

### Path resolution (how `get("posture.toolchain.items.go")` works)

A path is a dot-separated hierarchy. Each segment is either a
BRANCH (has children) or a LEAF (has data). The mediator walks
the tree:

```
get("posture.toolchain.items.go")

Step 1: posture             → branch (has children: summary, full, platform, toolchain, ...)
Step 2: posture.toolchain   → node (PillarResult, has sub-accessor .items)
Step 3: .items              → branch (list of PostureItem)
Step 4: .items.go           → leaf (PostureItem for Go)
```

But here's the power: you can query at ANY level:

```
get("posture")              → all posture data (full SystemPosture)
get("posture.toolchain")    → just the toolchain PillarResult
get("posture.toolchain.items.go")  → just Go's PostureItem
```

Each branch node knows:
- Its children (tree structure)
- Its resolver function (how to compute/fetch)
- Its cache key (if cacheable)
- Its TTL or mtime strategy
- Its parent (for cascade propagation)
- Its dependents (for cascade invalidation)

### Tree Registration (the builder pattern)

```python
# This is conceptual — shows HOW the tree is declared.

tree = DataTree()

# Posture branch
tree.register("posture.platform",   resolver=scan_platform,   ttl=INF,   persist=True)
tree.register("posture.toolchain",  resolver=scan_toolchain,  ttl=300,   persist=True)
tree.register("posture.project",    resolver=scan_project,    ttl=60,    persist=True)
tree.register("posture.runtime",    resolver=scan_runtime,    ttl=0)  # always fresh
tree.register("posture.full",       resolver=assemble_posture, ttl=60,  persist=True,
              depends_on=["posture.platform", "posture.toolchain",
                          "posture.project", "posture.runtime"])
tree.register("posture.summary",    resolver=make_summary,     ttl=30,
              depends_on=["posture.full"])

# DevOps branch (mtime-based)
tree.register("devops.docker",      resolver=compute_docker,   mtime_paths=["Dockerfile", ...])
tree.register("devops.testing",     resolver=compute_testing,  mtime_paths=["tests/", ...])

# Detection branch (shared, deduped)
tree.register("detect.os",          resolver=detect_os,        ttl=INF)
tree.register("detect.tools.go",    resolver=detect_go,        ttl=300)
tree.register("detect.docker",      resolver=detect_docker,    ttl=30)

# Dependency: posture.toolchain feeds from detect.tools.*
tree.register_feed("detect.tools.*", "posture.toolchain")
```

---

## 4. The Delta — Never Reset the Whole

> "There is no need to reset the whole, you always just get the delta,
> the new and or the fresh."

### How delta works

Every value in the tree has a SEQUENCE NUMBER (monotonic, like the
EventBus's seq). When data changes, a new seq is assigned.

```
Consumer says: "I have posture.summary at seq=142"
Mediator says: "Current is seq=158. Here's what changed:"

{
    "path": "posture.summary",
    "from_seq": 142,
    "to_seq": 158,
    "delta": {
        "overall_rank": "outdated" → "current",
        "pillar_ranks.toolchain.rank": "outdated" → "current",
    }
}
```

The consumer patches its local state instead of replacing everything.
This is already partially happening — the `_postureUpdateToolRow()`
we just built updates ONE row instead of refetching the whole table.
The mediator makes this systematic.

### Seq propagation through the tree

When a leaf changes, its seq bumps. The parent's seq bumps. The
parent's parent's seq bumps. All the way to the root.

```
detect.tools.go changes (go updated 1.22→1.24)
  → detect.tools.go         seq: 200→201
  → posture.toolchain        invalidated (depends_on detect.tools.*)
  → posture.full             invalidated (depends_on posture.toolchain)
  → posture.summary          invalidated (depends_on posture.full)
```

But the consumer holding `posture.summary` at seq=200 doesn't need
to refetch everything. The mediator recomputes the chain and returns
a delta: "overall_rank changed from outdated to current." One field.

### Stale-while-revalidate

When a node is expired (TTL passed) but a consumer asks for it:

```
Option A (blocking): compute fresh, return.  Slow but accurate.
Option B (stale-ok):  return stale data + header {stale: true, refreshing: true}
                      background recompute, push delta via SSE when ready.
```

Option B is what nginx does. It's excellent UX. The page loads
instantly with slightly stale data, then patches in the fresh
values when ready. Zero perceived latency.

---

## 5. The Mediator's Operations

> "PUT, GET, refreshing, force rescan, force flush cache, diag view,
> explain, cascade, cascade depth, subscribe, dispatch"

Let me map each one to what it DOES inside the trilateral:

| Operation | What it mediates | Who benefits |
|-----------|-----------------|-------------|
| **GET** | Check cache → check index → compute if needed → return | Every route, every card |
| **PUT** | Write data → update cache → update index → cascade | Tool updates, config changes |
| **refresh** | Bump TTL timer on a node → return fresh next time | Manual refresh button |
| **force rescan** | Bypass cache entirely → compute → replace cache → cascade | User-triggered rescan |
| **force flush** | Delete cache entry → delete persisted file → force cold | Debug, troubleshooting |
| **diag** | Return tree state: ages, TTLs, seqs, hit rates | Debug tab |
| **explain** | Return the RESOLUTION PATH: "served from cache, age 42s" | Debug, learning |
| **cascade** | Walk dependency graph → invalidate all dependents | Any data change |
| **cascade_depth** | Limit cascade to N levels deep | Targeted invalidation |
| **subscribe** | Register callback for path pattern → receive deltas | SSE, reactive UI |
| **dispatch** | Queue background work (rescan, rebuild) → return estimate | Async operations |
| **bust[t=x]** | Invalidate entries older than X seconds | Temporal pruning |

### GET resolution flow (the heart of the mediator)

```
mediator.get("posture.toolchain", max_age=30, stale_ok=True, explain=True)

1. RESOLVE PATH: "posture.toolchain" → tree node found
   node.resolver = scan_toolchain
   node.ttl = 300s
   node.cache_key = "toolchain"
   node.persist = True

2. CHECK CACHE:
   cache.get("toolchain") → entry found, age=42s
   max_age=30 requested → 42s > 30s → STALE

3. STALE-OK CHECK:
   stale_ok=True → return stale data immediately
   queue background recompute

4. RETURN:
   {
     data: <PillarResult>,
     meta: {
       source: "cache",
       age_s: 42,
       stale: true,
       refreshing: true,
       seq: 158,
       explain: "cache hit, age 42s > max_age 30s, stale_ok=true,
                 returning stale + queued background recompute"
     }
   }

5. BACKGROUND:
   → compute_lock("toolchain")
   → scan_toolchain()
   → cache.set("toolchain", result)
   → persist to disk
   → cascade: invalidate posture.full → posture.summary
   → event_bus.publish("mediator:updated", path="posture.toolchain", delta={...})
   → SSE → frontend patches row
```

---

## 6. How Speed Doubles — The Optimization Map

> "Doing this properly we would be able to loadbalance all operations
> in order to reduce duration / increase the speed of scan and such...
> the timing can decrease by at least half"

The speed gain comes from FIVE sources:

### 6.1 Detection deduplication

**Today:** `probe_docker()`, `docker/detect.py`, `scan_toolchain()`,
and wizard detection ALL independently run `docker info`, `docker version`.
That's 4× the same subprocess call.

**After:** `detect.docker` is computed ONCE. Everyone reads from
the index. Detected → indexed → cached. One subprocess call,
four consumers.

**Saving:** ~1.5s on every page load that touches Docker.

### 6.2 Parallel branch scanning

**Today:** `scan_posture()` scans platform → toolchain → project → runtime
SEQUENTIALLY. Toolchain alone takes ~12s.

**After:** The mediator dispatches all four pillar scans in PARALLEL.
Platform (~0.1s), project (~0.5s), runtime (~0.01s) finish immediately.
Toolchain (~12s) is the bottleneck. But instead of 12+0.1+0.5+0.01=12.6s,
it's just ~12s. And with detection dedup (6.1), toolchain drops to ~6s.

**Saving:** ~50% on full posture scan.

### 6.3 Stale-while-revalidate

**Today:** Expired cache → block → compute → return. User waits.

**After:** Expired cache → return stale instantly → compute in
background → push delta via SSE.

**Saving:** Perceived latency drops to ~0s for repeat visits.

### 6.4 Cascade intelligence

**Today:** Updating Go triggers full posture rescan (~12s) or at
best, targeted rescan-tool (~0.5s). But devops card, audit scores,
and project index don't know about the change.

**After:** Updating Go → mediator.put("detect.tools.go") →
cascade chain: posture.toolchain → posture.full → posture.summary.
Each stage recomputes ONLY what depends on Go. The audit scores
check if Go's status change affects the security score. The devops
"tools" card reflects the new version. All from ONE event.

**Saving:** Eliminates redundant rescans triggered by fragmented state.

### 6.5 Persistent warm cache

**Today (already done):** posture_cache.json, devops_cache.json,
project_index.json survive restart.

**After:** The mediator ensures ALL tree nodes that are marked
`persist=True` survive restart. On startup, the tree loads from
disk and the first page load is instant.

**Saving:** Cold start from >12s to <1s.

---

## 7. Plugging In Existing Systems (Zero Rewrite)

> "cover 100% of what already existing and even another 100% more"

The mediator WRAPS existing systems. It doesn't replace them.

| Existing System | How It Plugs In |
|----------------|----------------|
| `devops/cache.py` `get_cached()` | Registered as resolver for `devops.*` branch nodes |
| `system_posture/cache.py` `get_or_compute()` | Registered as resolver for `posture.*` nodes |
| `project_index.py` `get_index()` | Registered as the `index.*` branch |
| `staleness_watcher.py` | Feeds `mediator.put()` when mtime changes detected |
| `event_bus.py` | Mediator publishes through bus. Bus subscribers unchanged. |
| `project_probes.py` `probe_*()` | Registered as resolvers for `detect.project.*` |
| All `detection.py` functions | Registered as resolvers for `detect.*` nodes |
| Route handlers | Call `mediator.get()` instead of direct service calls |
| Frontend `_cache.html` | Receives deltas via SSE, patches sessionStorage |

### Migration path

1. Create mediator module with tree registry
2. Register existing systems as resolvers (they don't change)
3. Add `mediator.get()` as an alternative path in routes (alongside existing direct calls)
4. Validate mediator returns same results
5. Switch routes to use mediator one by one
6. Once all routes migrate, the old direct-call paths become internal resolvers only

At NO point does anything break. The mediator is additive.

---

## 8. Coordination Model — Why "Like a Zookeeper"

> "a bit like a zookeeper of our marvel"

ZooKeeper's core value is COORDINATION of distributed state.
Our mediator coordinates LAYERED state:

| ZooKeeper concept | Our mediator equivalent |
|-------------------|------------------------|
| znodes (hierarchical namespace) | Tree nodes (dot-separated paths) |
| Ephemeral nodes | TTL-based cache entries |
| Persistent nodes | File-backed, survive restart |
| Watches (subscribe to changes) | subscribe() with pattern matching |
| Sequential nodes (ordering) | Sequence numbers for delta protocol |
| Leader election | Per-key compute locks (no duplicate work) |
| ACLs | Not needed (single-user dev tool) |

The mediator is a single-process ZooKeeper for our data layer.
No network overhead, no consensus protocol — just coordination
of cache, index, and backend into one coherent system.

---

## 9. What This Model Must Prove Before Implementation

Before we write the plan, this model must answer:

**Q1: Can every existing call site map to a mediator path?**
Spot-check: `get_cached(project_root, "docker", compute_fn)` →
`mediator.get("devops.docker")`. Yes. The `project_root` comes
from the tree node registration, not the caller. The `compute_fn`
is the registered resolver. ✓

**Q2: Does the delta protocol work with the existing EventBus?**
The bus already has seq numbers. The mediator piggybacks on them.
When data changes, publish event with `{path, from_seq, to_seq, delta}`.
Frontend SSE handler already listens — just needs a new event type
handler. ✓

**Q3: Does detection dedup actually save time?**
`docker info` + `docker version` take ~0.3s each. Called 4× = 1.2s.
Deduped = 0.3s. Net saving = 0.9s. Similar for kubectl (~0.5s × 3),
go version (~0.2s × 3), etc. Across a full page load touching
10+ tools, saving is 3–5s. ✓

**Q4: Can the tree handle both TTL and mtime strategies?**
Yes — each node declares its invalidation strategy. TTL nodes
expire by age. Mtime nodes expire when watched files change.
The mediator checks the right strategy per node. Some nodes
could even use BOTH (TTL with mtime as early-invalidation hint).

**Q5: Does stale-while-revalidate work with the current UI?**
The UI already handles "data arrives, render it." SSE already
pushes events. Adding "here's an update to what you already have"
is an incremental change, not a paradigm shift. ✓

---

## 10. What We Build, In What Order

```
Layer 0 (bottom):  Index consolidation
                   Unify 21+ detect/probe functions under one namespace.
                   Each gets a TTL. Results cached. Subprocess dedup.

Layer 1:           Tree registry
                   DataTree class. Register paths, resolvers, TTLs,
                   dependencies, persistence flags.

Layer 2:           Mediator core
                   get(), put(), invalidate() wired to existing caches.
                   Cascade engine walks dependency graph.
                   Sequence numbers assigned.

Layer 3:           Delta protocol
                   EventBus integration. Delta computation.
                   subscribe() with pattern matching.

Layer 4:           Scheduling
                   Background job queue. Parallel scanning.
                   Stale-while-revalidate.

Layer 5:           Migration
                   Route-by-route, validate equivalent results.

Layer 6 (top):     Diagnostic view
                   Debug tab showing tree, ages, stats. Toggle in settings.
```

Each layer is COMPLETE and USEFUL on its own. Layer 0 alone gives
us detection dedup. Layer 1 alone gives us the tree structure.
Layer 2 alone gives us unified querying. No layer requires the
next one to deliver value.
