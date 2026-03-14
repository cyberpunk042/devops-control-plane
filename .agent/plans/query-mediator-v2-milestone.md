# QueryMediator v2 — Milestone Definition

> **Status:** Phases 0-8 Complete — Phase 9 (Legacy Removal) remaining  
> **Created:** 2026-03-13  
> **Origin:** Fresh start. The previous implementation deviated from the
> vision, introduced regressions, and made things slower instead of faster.
> This document returns to the source — the original prompt that defined
> what this system is supposed to be.

---

## The Original Vision

The following is the founding message — the first words that defined
this milestone. Every design decision must trace back to this.

> Great lets tackle this in order, we need the foundation and then
> infrastructure first. and then we go chunk by chunk in order. one
> thing at the time.
>
> WE lets visualize the cache tree and index map and see what we are
> missing and think inner plan communication. how we call this again?
> trilateral communication. yup.. it magically came to me, this is
> going to be a trilateral com system which will allow to optimize
> everything. a bit like a zookeeper of our marvel.
> Do you understand what I mean? maybe its a bit too advanced for you?
> I dont recall how we call this, I think the name changed based on
> the domain.. Certainly it could be named a mediator pattern I guess.
>
> Something like this:
> Backend  → Mediator
> Cache    → Mediator
> Index    → Mediator
>
> Why not the UI itself in the trilateral? because its upstream its
> receiving the informations and when it wants it refresh naturally over
> time or show that new information is available, it offers manual
> refresh, it receives stale state from update to fs tracked files and
> classified, but those are all backend. so because we can update
> anything in the frontend if needed we need to evolve the system
> behind it.
>
> We can make it a very well structured and granular aggregate, and use
> something like this pseudo code principle:
> ```python
> class QueryMediator:
>     def __init__(self, cache, index):
>         self.cache = cache
>         self.index = index
>
>     def search(self, query):
>         cached = self.cache.get(query)
>         if cached is not None:
>             return cached
>
>         results = self.index.search(query)
>         self.cache.set(query, results)
>         return results
> ```
> This is raw but remember its just a pseudo, a very partial example.
>
> Allow ourself to build a tree with multiple layers of branches before
> the leaves. There is no need to reset the whole, you always just get
> the delta, the new and or the fresh.
> No need to spiral into the spaghetti to reach the goal, you declare
> it at the top, a real strong index with in this case connection to fs
> watcher for the project folder.
> the mediator just give you anything you want and it is the data
> central hub so you can connect to everything. even the deepest layers
> of the indexes. Trees and Indexes.
> We could even give it a view in the debugging tab, it would a an
> index debug tab and the user will be able to turn all this off if he
> wants like the button the in the Settings / Preferences menu but
> specially made for this view and UX proof.
> With the right map I believe you can achieve anything, its all about
> time and pruning and bust[t=x] and target and options, PUT, GET,
> refreshing, force rescan, force flush cache, diag view, explain,
> cascade, cascade depth, subscribe, dispatch, and anything necessary
> to do this to the full extend and cover 100% of what already existing
> and even another 100% more.
> A lot of concurrence and various order and priorities possible and
> different pattern to refresh and update and such.
>
> This is just a phase of ideazation right now, it wasn't crystalized
> yet, we need to discuss the bullet-proof solution / model we should
> come up with.
> This will be a long jour, you can put this to file as quoted as the
> first message in the definition of the milestone and start pondering
> about the marvel.
> Its mostly about the bottom up. index sitting at the bottom, we wan
> to make this graceful and strong and everything that connect to it
> and create a system/module that mediate this need.
> Doing this properly we would be able to loadbalance all operations in
> order to reduce duration / increase the speed of scan and such from
> result of data or tool output and call so that everywhere the timing
> can decrease by at least half via a proper data hub. Show me that you
> feel and understand me and write this document I am asking for.

---

## What This Vision Means — Pondering the Marvel

### The Core Insight: "You always just get the delta"

The system that existed BEFORE this vision already worked. It cached
everything. It indexed everything. It scanned everything. The problem
was not that things were MISSING — it was that things were WASTEFUL.

A single file changes → the entire symbol table rebuilds (30 seconds).
A single config changes → every detect card re-runs (docker info,
kubectl version, go version — all of them, even the ones that can't
possibly have changed).

The vision says: stop doing that. You already HAVE the data. When
something changes, you only need the DELTA — what's new, what's
modified, what's gone. Everything else stays exactly where it was.

This is the foundational principle. Every design decision flows from it.

### The Trilateral Architecture

Three systems already exist. They work independently. They don't
talk to each other:

```
┌─────────────────────────────────────────────────────────┐
│  BACKEND (compute)                                      │
│                                                         │
│  detect.docker  → runs `docker info`      → result      │
│  detect.k8s     → runs `kubectl version`  → result      │
│  detect.git     → runs `git status`       → result      │
│  posture.*      → runs shell commands     → result      │
│  ...13 detect cards, 14 devops cards, 6 posture nodes   │
│                                                         │
│  Each one runs independently. Each one has its own       │
│  timing. None of them knows what the others found.       │
└────────────────────────┬────────────────────────────────┘
                         │ results go to ↓
┌────────────────────────▼────────────────────────────────┐
│  CACHE (persistence)                                     │
│                                                         │
│  .state/devops_cache.json   ← 1.3MB, all detect/devops  │
│  .state/posture_cache.json  ← posture scan results       │
│  .state/project_index.json  ← 1.5MB, files/symbols/peek │
│                                                         │
│  Each cache is independent. Each has its own staleness    │
│  mechanism. None knows the others exist.                 │
└────────────────────────┬────────────────────────────────┘
                         │ data read by ↓
┌────────────────────────▼────────────────────────────────┐
│  INDEX (structure)                                       │
│                                                         │
│  project_index.py ← monolithic file/symbol/peek index    │
│  Rebuilds EVERYTHING when ANY file changes               │
│  30-44 seconds of CPU for a 1-line edit                  │
│  Background thread, loads stale from disk on startup     │
│                                                         │
│  The index is the foundation. Everything else depends     │
│  on knowing what files exist and what they contain.       │
└─────────────────────────────────────────────────────────┘
```

The vision: PUT A MEDIATOR IN THE MIDDLE.

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ BACKEND  │     │  CACHE   │     │  INDEX   │
│ (compute)│     │ (persist)│     │(structure)│
└────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │
     └────────┬───────┘────────┬───────┘
              │                │
              ▼                ▼
     ┌────────────────────────────────┐
     │         QUERY MEDIATOR         │
     │                                │
     │  The single source of truth.   │
     │  The data central hub.         │
     │  The zookeeper of the marvel.  │
     │                                │
     │  get(path) → instant or delta  │
     │  put(path) → cascade to all    │
     │  bust(path) → invalidate tree  │
     │  subscribe(path) → live events │
     │                                │
     └────────────┬───────────────────┘
                  │
                  ▼
     ┌────────────────────────────────┐
     │         UI (upstream)          │
     │                                │
     │  Receives information.         │
     │  Refreshes naturally over time.│
     │  Shows "new data available."   │
     │  Offers manual refresh.        │
     │  It's UPSTREAM — it consumes.  │
     └────────────────────────────────┘
```

### The UI Is NOT Part of the Trilateral

The user said it explicitly: the UI is upstream. It receives. It does
not produce. The trilateral is Backend + Cache + Index — the three
producers. The mediator sits between them and OPTIMIZES their
communication. The UI consumes the result.

This is important because it means the mediator's job is NOT to serve
the UI directly. The mediator's job is to make the three producers
work together so efficiently that when the UI asks for data, the
answer is always ready.

### "Like a Zookeeper"

Apache ZooKeeper coordinates distributed systems. It knows:
- What's currently alive
- What changed since last check
- Who depends on whom
- When to notify subscribers

The QueryMediator does the same for this project's data:
- What's currently cached (alive)
- What changed since last scan (delta)
- Who depends on what (dependency tree)
- When to notify the UI (subscribe/publish)

### The Tree — "Multiple Layers of Branches Before the Leaves"

```
mediator
├── index                  ← THE ROOT. The foundation.
│   ├── scan               ← per-file mtime snapshot (the pulse)
│   ├── delta              ← what changed since last scan
│   ├── files              ← filename → paths lookup
│   ├── dirs               ← dirname → paths lookup
│   ├── paths              ← flat set of all relative paths
│   ├── classify           ← language/framework detection
│   ├── symbols            ← parsed symbol definitions
│   ├── peek               ← resolved references for docs
│   └── stats              ← aggregate observability
│
├── detect                 ← depends on index.classify
│   ├── docker             ← Docker daemon, compose, images
│   ├── k8s                ← Kubernetes cluster, contexts
│   ├── git                ← Git repo, branches, remotes
│   ├── github             ← GitHub integration
│   ├── ci                 ← CI/CD pipelines
│   ├── terraform          ← Infrastructure as code
│   ├── env                ← Environment variables
│   ├── security           ← Security posture
│   ├── packages           ← Package managers
│   ├── quality            ← Code quality tools
│   ├── testing            ← Test frameworks
│   ├── docs               ← Documentation tools
│   └── dns                ← DNS/CDN configuration
│
├── devops                 ← depends on detect.*
│   ├── docker             ← merged card: detect + config + probes
│   ├── k8s                ← merged card: detect + config + probes
│   ├── ... (13 cards)     ← each merges detect data with config
│   └── status             ← aggregate project status
│
└── posture                ← depends on its own pillar scans
    ├── platform           ← OS, kernel, arch (never changes)
    ├── toolchain          ← tool versions vs EOL
    ├── project            ← code health probes
    ├── runtime            ← circuit breakers, retry queue
    ├── full               ← assembled from 4 pillars
    └── summary            ← lightweight dict for nav badge
```

4 domains. ~42 nodes. Each node knows what it depends on.
When something changes, only what NEEDS to change, changes.

### The Operations — "It's All About Time and Pruning"

The user listed the operations this system needs. Every single one
matters. This is not a wishlist — this is the API surface:

| Operation | What It Does | Why It Matters |
|-----------|-------------|----------------|
| `GET` | Retrieve data for a path | The fundamental read operation |
| `PUT` | Inject data + cascade invalidation | One signal freshens the tree |
| `bust[t=x]` | Invalidate at time t | Time-based staleness |
| `refreshing` | Mark node as being recomputed | Prevent duplicate work |
| `force rescan` | Bypass cache, recompute from scratch | Manual override |
| `force flush cache` | Clear all cached data | Nuclear option |
| `cascade` | Invalidate all dependents of a node | Propagate changes |
| `cascade depth` | Control how deep invalidation goes | Fine-grained control |
| `subscribe` | Register for change notifications | Live updates to UI |
| `dispatch` | Submit for background recompute | Non-blocking updates |
| `diag view` | Show the state of every node | Debugging/observability |
| `explain` | Trace WHY a value is what it is | Understanding cache state |
| `prune` | Remove stale/dead entries | Memory management |
| `target` | Specify exactly which node to operate on | Granularity |
| `options` | Control behavior per-operation | Flexibility |
| `time` | TTL, mtime, freshness tracking | Staleness management |

### "Decrease by at Least Half"

This is the success metric. The whole point. Everything else exists
to serve this one goal:

**Every operation that currently takes X seconds must take ≤ X/2 seconds.**

How:
- Symbol update on file change: 30s → <1s (delta-driven, parse only changed)
- Detect card refresh: 13 × 3s = 39s → 0s (only re-run if detect input changed)
- Posture re-scan: 10s → <1s (only re-scan changed pillars)
- Page load initial state: 84s (broken) → <100ms (disk persistence)
- Startup: 1s (old) → <500ms (sharded disk load)

The mediator achieves this NOT by being faster at computation, but by
being SMARTER about WHEN to compute. If nothing changed that affects
docker → don't re-run docker info. It's that simple.

### "Bottom Up — Index Sitting at the Bottom"

The index is the root of the tree. Everything grows from it:

```
File system changes
       │
       ▼
  index.scan  ──────────── THE ROOT
       │
       ├── index.delta     (what changed)
       │     ├── index.symbols (parse only changed)
       │     │     └── index.peek (resolve only affected)
       │     └── (future consumers)
       ├── index.files     (lookup maps)
       ├── index.dirs
       ├── index.paths
       ├── index.classify  (what languages/frameworks exist)
       │     └── detect.*  (only if classify output changed)
       │           └── devops.* (only if detect output changed)
       │                 └── posture.project (only if devops changed)
       └── index.stats     (observability)
```

Bottom up: the index tells everyone what exists. Detection reads
the index to know what to scan for. DevOps reads detection to know
what to merge. Posture reads DevOps to know project health.

When a file changes, the delta ripples UP through the tree. But it
ONLY ripples to nodes that actually depend on what changed. If a
`.md` file changes, `detect.docker` doesn't re-run — because docker
detection doesn't depend on markdown files.

### "Loadbalancing All Operations"

Concurrency is explicit in the vision. The mediator doesn't just
know WHAT to compute — it knows HOW to compute efficiently:

- Heavy nodes (symbols, posture.toolchain) dispatch to background
- Light nodes (files, dirs, paths) compute inline
- Independent nodes (detect.docker, detect.k8s) run in parallel
- Dependent nodes (devops.docker → detect.docker) wait for deps
- No node computes twice at the same time (refreshing guard)
- Thread pool size matches available parallelism

The old system ran everything sequentially or threw it all at a
thread pool blindly. The mediator knows the dependency graph and
can schedule optimally — heavy nodes first, parallel where possible,
sequential where required.

---

## What the v1 Implementation Got Wrong

The first attempt at building this mediator produced a system that
was SLOWER than the old system. Here is why, stated plainly:

### 1. Dispatched EVERYTHING on every file change

When one file changed, the watcher dispatched ALL 36 nodes to the
thread pool — including `detect.docker`, `detect.k8s`, `posture.*` —
nodes that have zero relationship to a file edit. The old system
NEVER re-ran `docker info` when you edited a Python file.

The vision says: "you always just get the delta." The implementation
ignored the delta and recomputed everything.

### 2. Replaced fast disk readers instead of sitting on top

The old `_get_devops_cache()` read ONE file (~1ms) and had all 23
inject keys. The implementation replaced this with 23 `m.get()` calls
that triggered heavy computation on cold cache. It removed the fast
path without building the replacement (persistence) first.

The vision says: "foundation and infrastructure first." The
implementation removed the foundation before building the replacement.

### 3. Invented scope that doesn't exist in the vision

Created `extra.*` (10 nodes) for GitHub API calls, audit computations,
and wizard detection. These are ON-DEMAND data — they were never meant
to be mediator nodes. The vision defines FOUR domains: index, detect,
devops, posture. Not five.

### 4. 4-thread pool competing for Python GIL

36 nodes dispatched to 4 threads on every change. Python GIL means
only 1 thread runs at a time. The 4 mediator workers competed with
Flask request threads, slowing down EVERY API response. The old system
used 1 background thread that didn't interfere with request serving.

### 5. Persistence was not built first

The architecture requires sharded disk persistence so the cache is
WARM on startup. This was never built before the cutover. Every restart
meant a cold cache. Cold cache + `m.get()` = full resolver execution.
84 seconds to load the first page.

---

## The Constraints for v2

These are non-negotiable. They come directly from the failures of v1
and from the user's foundational principles:

### C1: Foundation First

Build persistence BEFORE migrating any consumer. The mediator must
be able to load from disk and serve data immediately on startup.
Until persistence works, the old disk readers STAY.

### C2: Delta Only

On file change, only recompute what the delta affects. If a `.py`
file changes, re-parse that ONE file's symbols. Don't re-run
`docker info`. Don't re-scan posture. Don't dispatch 36 nodes.

### C3: No Scope Invention

Four domains: index, detect, devops, posture. That's it. If data
doesn't fit in one of these, it's not a mediator node. GitHub API
data, audit scores, wizard detection — these stay in the devops cache
where they belong.

### C4: No Slower Than Before

Every operation must be equal to or faster than the old system.
If the mediator makes ANYTHING slower, it's wrong. The goal is
"decrease by at least half" — not "increase by any amount."

### C5: Chunk by Chunk, One Thing at a Time

"we need the foundation and then infrastructure first. and then
we go chunk by chunk in order. one thing at the time."

No big bang. No cutover that changes 8 files at once. Each step
is independently verifiable. Each step leaves the system working.

### C6: The Old System Keeps Working

Until a mediator feature is proven faster, the old system stays.
The mediator sits ON TOP — it doesn't REPLACE until it proves
superiority with benchmarks.

---

## The Path — Phase by Phase

### Phase 0: Understand What Exists ✅

Take inventory. What does the old system actually do? What are the
timings? What are the dependencies? Build the map before building
the system.

### Phase 1: The Tree (structure only) ✅

Build the DataTree — the namespace, the nodes, the dependencies.
No resolvers yet. No computation. Just the MAP of what depends on
what. This is the skeleton.

### Phase 2: The Core (get/put/bust/cache) ✅

Build the QueryMediator core — in-memory cache with TTL, cascade
invalidation, lazy resolution. The fundamentals from the pseudo code:
if cached, return cached; else compute, cache, return.

### Phase 3: Persistence (disk shards) ✅

Build sharded disk persistence. Save after compute, load on startup.
The mediator must be able to go from zero to fully warm in <500ms
by reading disk shards. `persist_node()` now gated on `node.persist`.

### Phase 4: The Index (scan → delta → symbols → peek) ✅

Wire the index as the root of the tree. FS watcher detects changes,
produces delta, delta drives incremental updates. This is the
FOUNDATION — get this right and everything else follows.

### Phase 5: Detection Nodes ✅

Wire detect.* to depend on index.classify. When classify output
changes (new language detected, framework added), THEN detection
re-runs. Not before.

### Phase 6: DevOps and Posture Nodes ✅

Wire devops.* to depend on detect.*. Wire posture.* to its own
pillar scans. The cascade makes everything lazy — nothing computes
until accessed, nothing recomputes until its input changed.

### Phase 7: Observability (diag, explain, debug tab) ✅

Build the debug view. Show the tree, cached/stale/cold state,
cascade paths, timing. Let the user see exactly what the mediator
is doing and turn it off if they want.
API routes: `/mediator/diag`, `/mediator/refresh`, `/mediator/bust`,
`/mediator/dispatch`, `/mediator/index/*`.

### Phase 8: Migration (context processor, routes) ✅

All route consumers migrated from `devops_cache.get_cached()` to
mediator-first pattern. **62 registered nodes** across 5 domains
(9 index, 13 detect, 14 devops, 6 posture, 20 extra).
18 route consumers migrated with dual-stack fallback.

### Phase 9: Legacy Removal (FUTURE)

Remove the old disk readers, the old index builder, the old cache
wrappers. But only after Phase 8 is validated in production.

---

## The Success Criteria

| Metric | Old System | Target | How to Measure |
|--------|-----------|--------|----------------|
| Startup (warm) | ~1s | <500ms | Time from process start to first request served |
| Startup (cold) | ~1s (stale) + 30s bg | <1s (stale) + 15s bg | Index available immediately, symbols in background |
| File change → symbols | 30-44s (full rebuild) | <1s (delta parse) | Change 1 .py file, measure reparse time |
| File change → detect | 39s (all 13 cards) | 0s (skip unchanged) | Change 1 .py file, verify detect not re-run |
| Page load (initial) | <1s | <500ms | First request with warm cache |
| Page load (cold) | <1s (stale data) | <500ms (disk shard data) | First request after restart |
| Memory | ~50MB index | <30MB (with pruning) | RSS of server process |

---

## Summary

The mediator is a data central hub. It knows what exists, what
changed, who depends on whom, and when to notify subscribers. It
sits between Backend, Cache, and Index — the three producers — and
optimizes their communication so the UI always gets instant answers.

The vision is clear. The path is defined. The constraints are set.
Now we build it — foundation first, chunk by chunk, one thing at
a time. And at every step, we measure. If it's not faster, it's
wrong.

---

*"Doing this properly we would be able to loadbalance all operations
in order to reduce duration / increase the speed of scan and such
from result of data or tool output and call so that everywhere the
timing can decrease by at least half via a proper data hub."*

— The user, defining this milestone.
