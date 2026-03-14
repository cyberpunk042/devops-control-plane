# QueryMediator — Implementation Plan

> **Companion to:** `query-mediator-milestone.md` (census) + `query-mediator-model.md` (architecture)
> **Status:** Active — Phases 0–6B complete ✓
> **Approach:** Foundation first. Chunk by chunk. One at a time.
> **Iteration:** This plan grows as we complete phases. Next phase
> gets detailed only after current phase ships.

---

## Overview

```
Phase 0: Foundation   ← COMPLETE ✓ (34 tests passing)
Phase 1: First Wire   ← COMPLETE ✓ (21 tests, 55 total, dual-path validated)
Phase 2: Detection    ← COMPLETE ✓ (22 tests, 77 total, 19 nodes)
Phase 3: DevOps Wire  ← COMPLETE ✓ (43 tests, 120 total, 32 nodes)
Phase 4: Cascade      ← COMPLETE ✓ (30 tests, 150 total, 33 nodes)
Phase 5: Delta        ← COMPLETE ✓ (21 tests, 171 total, EventBus bridge)
Phase 6A: Subscribe   ← COMPLETE ✓ (30 tests, 201 total, pure/no threading)
Phase 6B: Refresh     ← COMPLETE ✓ (31 tests, 232 total, executor-injected)
Phase 7: Debug View   (future)
```

---

## Phase 0 — Foundation

**Goal:** Create the mediator module with the DataTree and
QueryMediator classes. No integration yet — just the skeleton
that everything else will plug into.

**Deliverable:** `src/core/services/mediator/` module with tree
registry, path resolution, and basic get/put that work in isolation.

### 0.1 Module Structure

```
src/core/services/mediator/
├── __init__.py          ← public API re-exports
├── tree.py              ← DataTree: node registration, path resolution
├── core.py              ← QueryMediator: get(), put(), diag()
└── README.md            ← module documentation
```

Follows the same pattern as `devops/` and `system_posture/`:
- `__init__.py` re-exports public symbols
- Internal modules stay internal
- README documents the module

### 0.2 DataTree — The Tree Registry (`tree.py`)

This is the MAP. It knows every path, what resolver produces
its data, how it expires, what it depends on, and whether it
persists to disk. It does NOT hold data — it holds metadata
about data.

**Data structures:**

```python
@dataclass
class TreeNode:
    """A single node in the data tree."""
    path: str                          # "posture.toolchain"
    resolver: Callable | None          # function to compute value
    ttl: float | None                  # seconds (None = mtime-based)
    mtime_paths: list[str] | None      # files to watch (if mtime-based)
    persist: bool                      # save to disk on change
    depends_on: list[str]              # paths this depends on
    dependents: list[str]              # paths that depend on this (auto-computed)
    children: dict[str, TreeNode]      # sub-nodes
    parent: str | None                 # parent path

    # Runtime state (managed by QueryMediator, not set at registration)
    # NOT stored here — stored in the mediator's cache layer.

@dataclass
class TreeRegistration:
    """Input for tree.register() — what the caller provides."""
    path: str
    resolver: Callable | None = None
    ttl: float | None = None
    mtime_paths: list[str] | None = None
    persist: bool = False
    depends_on: list[str] | None = None
```

**Public API:**

```python
class DataTree:
    """Hierarchical namespace for data nodes."""

    def register(self, reg: TreeRegistration) -> TreeNode:
        """Register a node. Creates intermediate branch nodes as needed.

        register("posture.toolchain.items") creates:
          posture (branch)
          posture.toolchain (branch)
          posture.toolchain.items (node with resolver)

        Raises ValueError if path already registered.
        """

    def resolve(self, path: str) -> TreeNode | None:
        """Walk the tree to find a node by dot-separated path.
        Returns None if not found.
        """

    def children(self, path: str) -> list[TreeNode]:
        """Return direct children of a branch node."""

    def dependents(self, path: str) -> list[str]:
        """Return all paths that depend on the given path.
        Walks the dependency graph (not just direct dependents).
        """

    def all_paths(self) -> list[str]:
        """Return all registered paths (for diagnostics)."""

    def subtree(self, path: str) -> dict:
        """Return tree structure from a node down (for diagnostics)."""
```

**Key behaviors:**
- Intermediate branch nodes are auto-created (register "a.b.c" creates
  "a" and "a.b" as branches if they don't exist)
- `depends_on` is bidirectional: if A depends on B, B's `dependents`
  list includes A (auto-computed at registration)
- Glob patterns in `depends_on` (like `"detect.tools.*"`) are expanded
  at cascade time, not at registration time (because detect.tools.go
  might be registered after posture.toolchain)

### 0.3 QueryMediator — Core (`core.py`)

The mediator holds the tree, a cache dict, and the logic for
resolving queries.

**Internal cache structure:**

```python
# Not persisted. Separate from tree metadata.
# One entry per path that has been computed.

_cache: dict[str, CacheEntry]

@dataclass
class CacheEntry:
    data: Any                # the computed/cached value
    computed_at: float       # time.time() when computed
    seq: int                 # monotonic sequence (from EventBus)
    source: str              # "computed" | "cache" | "disk"
```

**Public API (Phase 0 — minimal):**

```python
class QueryMediator:
    """Central data hub — mediates between caches, indexes, and backend."""

    def __init__(self, tree: DataTree, project_root: Path):
        self._tree = tree
        self._project_root = project_root
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._compute_locks: dict[str, threading.Lock] = {}

    def get(self, path: str, *, force: bool = False,
            max_age: float | None = None,
            explain: bool = False) -> dict:
        """Query a value by path.

        Returns:
            {
                "data": <the value>,
                "meta": {
                    "path": "posture.toolchain",
                    "source": "cache",          # "cache" | "computed" | "disk"
                    "age_s": 42,
                    "seq": 158,
                    "explain": "..."            # only if explain=True
                }
            }
        """

    def put(self, path: str, data: Any = None, *,
            cascade: bool = True) -> dict:
        """Write or invalidate a path.

        If data is provided: store it in cache.
        If data is None: invalidate (delete from cache).
        If cascade=True: walk dependents and invalidate them too.

        Returns:
            {
                "invalidated": ["posture.toolchain", "posture.full", "posture.summary"],
                "seq": 159
            }
        """

    def diag(self, path: str = "") -> dict:
        """Diagnostic info.

        If path is empty: return summary of all nodes.
        If path is specific: return detail for that node.

        Returns:
            {
                "nodes": 42,
                "cached": 18,
                "stale": 3,
                "entries": {
                    "posture.toolchain": {"age_s": 42, "ttl": 300, "stale": false},
                    ...
                }
            }
        """
```

**GET resolution logic (Phase 0 — simple):**

```
1. Resolve path → TreeNode (or 404)
2. If force=True → skip cache, go to step 5
3. Check _cache[path]:
   a. Entry exists + TTL not expired + (max_age is None or age < max_age) → return cached
   b. Entry exists + TTL expired → go to step 5
   c. No entry → go to step 5
4. (mtime check for mtime-based nodes — Phase 1)
5. Acquire compute lock for this path (prevents duplicate computation)
6. Double-check cache (another thread may have computed while we waited)
7. Call node.resolver() → result
8. Store in _cache[path]
9. Return result with meta
```

### 0.4 Module Init (`__init__.py`)

```python
"""
QueryMediator — trilateral data hub.

Mediates between Backend, Cache, and Index:

    from src.core.services.mediator import mediator
    result = mediator.get("posture.toolchain")
    mediator.put("posture.toolchain", cascade=True)
    mediator.diag()

The module-level ``mediator`` is a singleton, initialized
via ``init(project_root)`` during server startup.
"""

from .core import QueryMediator
from .tree import DataTree, TreeNode, TreeRegistration

# Module singleton — initialized by init()
mediator: QueryMediator | None = None

def init(project_root: Path) -> QueryMediator:
    """Initialize the mediator singleton."""

def get_mediator() -> QueryMediator:
    """Get the mediator singleton. Raises if not initialized."""
```

### 0.5 Initialization (`server.py` integration)

During server startup, after existing inits:

```python
# In server.py, alongside posture_cache_init and start_watcher:
from src.core.services.mediator import init as mediator_init
mediator_init(app.config["PROJECT_ROOT"])
```

At Phase 0, the tree is EMPTY. No nodes registered.
That's fine — the skeleton is ready to receive registrations.

### 0.6 Tests

Basic tests to validate the foundation works:

```
test_tree_register          — register paths, resolve them
test_tree_intermediate      — auto-creation of branch nodes
test_tree_depends_on        — dependency tracking
test_tree_dependents        — reverse dependency walk
test_mediator_get_miss      — get with no resolver returns error
test_mediator_get_computed  — get calls resolver, caches result
test_mediator_get_cached    — second get returns cached
test_mediator_put_cascade   — put invalidates dependents
test_mediator_diag          — diag returns tree state
```

### 0.7 README

Standard module README documenting:
- What the mediator is and why it exists
- Public API with examples
- How to register nodes
- How get/put/diag work
- Thread safety model (follows project patterns)
- Dependency on EventBus

### Phase 0 Checklist

```
[x] Create src/core/services/mediator/ directory
[x] Write tree.py — DataTree, TreeNode, TreeRegistration
[x] Write core.py — QueryMediator with get(), put(), diag()
[x] Write __init__.py — public API, singleton pattern
[x] Add init() call to server.py
[x] Write tests (34 tests, all passing)
[x] Write README.md
```

**Phase 0 does NOT:**
- Register any existing systems as tree nodes
- Touch any existing cache code
- Change any existing routes
- Integrate with EventBus publishing (diag only reads bus seq)

**Phase 0 DOES:**
- Establish the tree data structure
- Establish the cache entry format
- Establish the get/put/diag interface
- Establish per-path compute locks (thread safety)
- Establish the module pattern (singleton, init)
- Prove the path resolution and cascade logic works

---

## Phase 1 — First Wire: Posture System

**Goal:** Register the posture system's 6 cache keys as mediator
tree nodes with their dependency graph, wire resolvers to existing
scanner/bridge functions, and add mediator-routed alternatives
alongside the existing paths for validation.

**Deliverables:**
- `src/core/services/mediator/registrations/posture.py` — tree registrations
- Modified `server.py` — call posture registration after mediator init
- Modified `routes/posture.py` — add mediator path alongside existing
- New tests validating mediator returns equivalent results

### Why posture is the right first wire

1. **Simplest cache** — 6 keys, all TTL-based (no mtime complexity)
2. **Clear cascade** — 4 pillars → full → summary (one dependency chain)
3. **Just made file-backed** — code is fresh, patterns are familiar
4. **Single orchestrator** — `scan_posture()` and `get_summary()` are
   the only two entry points routes actually call
5. **Expensive scan** — toolchain takes ~12s, so cache behavior is
   immediately visible (mediator caching shows real value)

---

### 1.1 Registration Module

**File:** `src/core/services/mediator/registrations/posture.py`

**What it does:** Registers the 6 posture cache keys as tree nodes
with their resolvers, TTLs, persistence flags, and dependency graph.

**The existing posture cache has:**

| Key | TTL | Persist | Resolver | Depends On |
|-----|-----|---------|----------|------------|
| `platform` | inf | ✓ | `_scan_platform()` | — |
| `toolchain` | 300s | ✓ | `_scan_toolchain()` | — |
| `project` | 60s | ✓ | `_bridge_project(root)` | — |
| `runtime` | 0s | ✗ | `_bridge_runtime()` | — |
| `full` | 60s | ✓ | `_assemble_posture()` | platform, toolchain, project, runtime |
| `summary` | 30s | ✓ | `scan_posture().to_summary_dict()` | full |

**Mapped to tree paths:**

```python
# In registrations/posture.py

def register_posture(mediator: QueryMediator) -> None:
    """Register posture.* nodes in the mediator tree."""
    tree = mediator.tree

    # Import existing scanner/bridge wrappers (they handle error isolation)
    from src.core.services.system_posture.orchestrator import (
        _scan_platform,
        _scan_toolchain,
        _bridge_project,
        _bridge_runtime,
        _assemble_posture,
    )

    tree.register(TreeRegistration(
        path="posture.platform",
        resolver=_scan_platform,
        ttl=math.inf,
        persist=True,
    ))

    tree.register(TreeRegistration(
        path="posture.toolchain",
        resolver=_scan_toolchain,
        ttl=300,
        persist=True,
    ))

    tree.register(TreeRegistration(
        path="posture.project",
        resolver=lambda: _bridge_project(mediator.project_root),
        ttl=60,
        persist=True,
    ))

    tree.register(TreeRegistration(
        path="posture.runtime",
        resolver=_bridge_runtime,
        ttl=0,  # always fresh — mediator skips cache for TTL=0? See 1.2
    ))

    tree.register(TreeRegistration(
        path="posture.full",
        resolver=lambda: _assemble_posture(force=False),
        ttl=60,
        persist=True,
        depends_on=[
            "posture.platform",
            "posture.toolchain",
            "posture.project",
            "posture.runtime",
        ],
    ))

    tree.register(TreeRegistration(
        path="posture.summary",
        resolver=lambda: scan_posture().to_summary_dict(),
        ttl=30,
        persist=True,
        depends_on=["posture.full"],
    ))
```

**Key decision — `project_root`:** The project bridge needs
`project_root`, which is available on the mediator instance.
The resolver lambda captures `mediator.project_root`.

**Key decision — `runtime` (TTL=0):** The existing cache skips
caching entirely for TTL=0 keys (`if ttl <= 0: return compute_fn()`).
The mediator's Phase 0 `get()` doesn't have this behavior — it
always caches. We need to handle this.

### 1.2 TTL=0 Handling in Mediator

**Problem:** Existing posture cache treats `TTL=0` as "always fresh,
never cache." The mediator currently caches everything.

**Solution:** Add TTL=0 handling to `QueryMediator.get()`. When a
node has `ttl=0`, call the resolver directly without caching.

**Change in:** `src/core/services/mediator/core.py`

```python
# At the start of get(), after resolving the node:
if node.ttl is not None and node.ttl <= 0 and not force:
    # TTL=0 means always fresh — skip cache
    result = node.resolver()
    return self._make_result(result, path, "computed", 0.0, self._next_seq(), explanation)
```

This matches the existing posture cache behavior exactly.

### 1.3 Registration Directory Structure

**New directory:** `src/core/services/mediator/registrations/`

```
src/core/services/mediator/
├── __init__.py
├── tree.py
├── core.py
├── README.md
└── registrations/
    ├── __init__.py        ← register_all() function
    └── posture.py         ← posture-specific registrations
```

**`registrations/__init__.py`:**

```python
"""
Node registrations for the mediator tree.

Each sub-module registers one domain's nodes.  Called from
server.py via register_all() after the mediator is initialized.
"""

from src.core.services.mediator.core import QueryMediator


def register_all(mediator: QueryMediator) -> None:
    """Register all domain nodes in the mediator tree."""
    from .posture import register_posture
    register_posture(mediator)
    # Future phases add more: register_devops, register_detect, etc.
```

This keeps each domain's registrations isolated and lets us
add new domains without touching server.py again.

### 1.4 Server Startup Integration

**Change in:** `src/ui/web/server.py`

After the existing `mediator_init()` call, add:

```python
# Register domain nodes in the mediator tree
from src.core.services.mediator.registrations import register_all
register_all(mediator_inst)
```

This runs once at startup. After this, the tree has 6 nodes
registered and ready to serve queries.

### 1.5 Persistence Bridging

**Problem:** The mediator's Phase 0 cache is in-memory only.
The existing posture cache persists to `.state/posture_cache.json`.
We need the mediator to also persist without duplicating the
file I/O code.

**Strategy for Phase 1:** DON'T add persistence to the mediator
yet. The existing posture cache continues to handle persistence.
The mediator's resolvers call into the existing `get_or_compute()`
which handles disk I/O. This means:

1. Mediator tree nodes are registered with resolvers pointing at
   the EXISTING scanner functions (not `get_or_compute()`)
2. The mediator has its OWN in-memory cache (separate from posture cache)
3. On cold start, the existing posture cache loads from disk as before
4. The mediator's first `get()` calls the resolver, which goes through
   `get_or_compute()`, which finds the disk-loaded data — fast

**This is intentionally a BRIDGE, not a REPLACEMENT.** Both caches
exist in parallel. The mediator proves its behavior is correct
before we remove the old cache in a later phase.

**Trade-off:** Some data is cached twice (mediator + posture cache).
This is acceptable for validation. Memory overhead is negligible
(posture data is ~10KB).

### 1.6 Route Integration (Dual-Path Validation)

**Change in:** `src/ui/web/routes/posture.py`

Add a `?via=mediator` query parameter to the existing routes.
When present, the route uses the mediator instead of the direct
service call. When absent, existing behavior is unchanged.

**Why dual-path:** This lets us compare results side-by-side
without risking production behavior. We can test the mediator
path manually while keeping the existing path as default.

```python
@posture_bp.route("/posture/summary")
def posture_summary():
    force = request.args.get("bust", "") == "1"
    via = request.args.get("via", "")

    if via == "mediator":
        from src.core.services.mediator import get_mediator
        m = get_mediator()
        result = m.get("posture.summary", force=force)
        return jsonify(result["data"])

    # Existing path (unchanged)
    from src.core.services.system_posture import get_summary
    try:
        summary = get_summary(force=force)
        return jsonify(summary)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
```

**Routes to add dual-path:**

| Route | Mediator path | Notes |
|-------|--------------|-------|
| `GET /posture/summary` | `mediator.get("posture.summary")` | Fast path for nav badge |
| `GET /posture` | `mediator.get("posture.full")` | + action enrichment after |
| `POST /posture/rescan` | `mediator.put("posture.full", cascade=True)` then `mediator.get("posture.full", force=True)` | Full invalidate + rescan |
| `POST /posture/rescan-tool` | `mediator.put("posture.toolchain", cascade=True)` then `mediator.get("posture.summary", force=True)` | Targeted invalidate |
| `GET /posture/cache` | `mediator.diag("posture")` (NOT mediator-routed — diag is new) | Could expose as additional endpoint |

### 1.7 Resolver Design Decision

**Question:** Should posture mediator resolvers call the RAW
scanner functions (`_scan_platform`, `_scan_toolchain`, etc.)
or the CACHED wrappers (`get_or_compute("platform", ...)`)?

**Answer:** Call the RAW functions. The mediator IS the cache.
If we call `get_or_compute()`, there are two caches with two
TTLs and two invalidation paths — that's confusing and fragile.

BUT for Phase 1 (bridge/validation), we accept dual caching
temporarily. The resolvers call the raw functions. The mediator
caches the result. The existing posture cache still works
independently for all non-mediator paths.

When we're confident the mediator works correctly (all tests pass,
dual-path validation shows equivalent results), Phase 2+ can
migrate routes to mediator-only and the old cache becomes unused.

### 1.8 Tests

```
test_posture_registration      — 6 nodes registered, dependencies correct
test_posture_tree_structure    — posture branch has expected children
test_posture_cascade_chain     — invalidating toolchain cascades to full → summary
test_posture_cascade_platform  — invalidating platform cascades to full → summary
test_posture_summary_via_med   — mediator.get("posture.summary") returns valid dict
test_posture_full_via_med      — mediator.get("posture.full") returns SystemPosture
test_posture_diag              — mediator.diag("posture.toolchain") returns expected fields
test_posture_force_rescan      — mediator.get(..., force=True) bypasses cache
test_posture_ttl0_runtime      — posture.runtime with ttl=0 never caches
test_posture_invalidate_flow   — put() then get() forces recomputation
```

### 1.9 Validation Criteria

Before Phase 1 is considered complete:

1. **Tree shape:** `mediator.tree.all_paths()` returns 6 posture paths
2. **Cascade correctness:** `mediator.tree.dependents("posture.toolchain")`
   returns `["posture.full", "posture.summary"]`
3. **Data equivalence:** `/api/posture/summary?via=mediator` returns the
   same JSON as `/api/posture/summary` (modulo timing fields)
4. **Force rescan:** `/api/posture/summary?bust=1&via=mediator` triggers
   fresh computation
5. **Diagnostics:** `mediator.diag()` shows 6 nodes, correct TTLs
6. **No regression:** Existing routes without `?via=mediator` work unchanged
7. **All tests pass**

### Phase 1 Checklist

```
[x] Create registrations/ directory with __init__.py
[x] Write registrations/posture.py — register 6 nodes
[x] Add TTL=0 handling to core.py (skip cache for always-fresh nodes)
[x] Wire register_all() in server.py after mediator_init()
[x] Add dual-path ?via=mediator to routes/posture.py
[x] Write Phase 1 tests (21 tests, all passing; 55 total)
[x] Manual validation: compare mediator vs direct paths (identical output confirmed)
[x] Update README.md with registration docs
```

### Phase 1 does NOT:
- Replace the existing posture cache
- Add file persistence to the mediator
- Change any route's default behavior
- Touch EventBus integration
- Modify any existing service code

### Phase 1 DOES:
- Prove the mediator can serve real posture data correctly
- Establish the registration pattern (reusable for devops, detect, etc.)
- Demonstrate cascade invalidation with real dependency chains
- Provide a switchable validation mechanism (`?via=mediator`)
- Handle the TTL=0 edge case

---

## Phase 2 — Detection Dedup Layer (`detect.*`)

### Why Detection Next

The census (Section E) identifies **21+ detection/probe systems** that all
run independently with no shared results. The milestone's Gap #5 says it:

> `probe_docker()` in project_probes.py runs `docker info`.
> `detect.py` in docker/ runs `docker info` again.
> k8s/detect.py runs `kubectl version`.
> system_posture/scanners/toolchain.py runs `kubectl version` again.
> tool_install/detection/environment.py runs its own detections.
> The SAME subprocess calls run multiple times across services.

Detection is the perfect Phase 2 because:

1. **Immediate speed gain** — subprocess calls (`docker info`, `kubectl version`,
   `go version`, etc.) are the slowest operations in the system. Caching them
   once in the mediator eliminates every duplicate call.
2. **Foundation for Phase 3** — DevOps cards (Phase 3) call detection functions
   internally. If detection is already cached in the mediator, Phase 3 resolvers
   get their results instantly instead of re-running subprocesses.
3. **No existing cache to bridge** — Unlike posture (Phase 1) and devops (Phase 3),
   detection functions have NO cache today. This is a pure "add caching where none
   exists" win — no dual-cache complexity.
4. **Simple resolvers** — Each detection function takes `project_root` and returns
   a dict. No assembly logic, no cross-dependency (unlike posture's `full` node).
5. **Same registration pattern** — Uses the exact pattern established in Phase 1.

### Which Detections to Register

Not all 21 systems are worth registering immediately. Focus on the ones that:
- Run subprocess calls (slow)
- Are called from multiple places (dedup value)
- Have clear, stable APIs

**Tier 1 — High-value subprocess dedup (Phase 2 scope):**

| Path | Resolver | What it detects | TTL | Persist |
|------|----------|----------------|-----|---------|
| `detect.docker` | `docker_ops.docker_status(root)` | Daemon, compose, images | 120s | ✓ |
| `detect.k8s` | `k8s_ops.k8s_status(root)` | kubectl, helm, manifests, cluster | 120s | ✓ |
| `detect.git` | `git_ops.git_status(root)` | Remote, branch, HEAD, status | 30s | ✗ |
| `detect.github` | `git_ops.gh_status(root)` | GitHub CLI, auth, repo | 120s | ✓ |
| `detect.ci` | `ci_ops.ci_status(root)` | CI workflows, pipeline status | 120s | ✓ |
| `detect.terraform` | `terraform_ops.terraform_status(root)` | Terraform files, state | 120s | ✓ |
| `detect.env` | `env_ops.env_card_status(root)` | Environment variables, .env files | 60s | ✗ |
| `detect.security` | `_compute_security(root)` | Secret scan + security posture | 120s | ✓ |
| `detect.packages` | `package_ops.package_status_enriched(root)` | Package status | 120s | ✓ |
| `detect.quality` | `quality_ops.quality_status(root)` | Code quality metrics | 120s | ✓ |
| `detect.testing` | `testing_ops.testing_status(root)` | Test status | 120s | ✓ |
| `detect.docs` | `docs_ops.docs_status(root)` | Documentation status | 120s | ✓ |
| `detect.dns` | `dns_cdn_ops.dns_cdn_status(root)` | DNS/CDN configuration | 120s | ✓ |

**13 nodes total** — these are the exact same compute functions already
registered in the devops cache's `_ensure_registry()` (lines 164-196 of
`routes/devops/__init__.py`). The mediator gives them proper TTL caching
where the devops cache only does mtime checking.

**Tier 2 — Deferred to later phases:**
- `detect.probes.*` — The 9 project probes (runs `run_all_probes()`)
- `detect.stacks` — Stack detection (`detection.py`)
- `detect.wizard` — Wizard environment detection
- `detect.chrome` — Chrome binary detection
- `detect.tools.*` — Individual tool version detection (35+ tools)

These are deferred because they're either less frequently called, have
fewer duplicate-call sites, or need special handling (like wizard detect's
large return shape).

### Dependency Graph

```
detect.docker  ─┐
detect.k8s     ─┤
detect.git     ─┼──→ (no downstream in Phase 2 — these are leaves)
detect.ci      ─┤
...            ─┘

Future Phase 3 will wire:
  devops.docker  ──depends_on──→ detect.docker
  devops.k8s     ──depends_on──→ detect.k8s
  devops.security ─depends_on──→ detect.security
  etc.
```

In Phase 2, the detect.* nodes are independent leaves with no cascading.
Phase 3 adds the `devops.*` layer on top and declares dependencies,
allowing automatic cascade: `detect.docker` invalidated → `devops.docker`
also invalidated.

### TTL Strategy

| Category | TTL | Rationale |
|----------|-----|-----------|
| Tool/infra detection (docker, k8s, terraform, etc.) | 120s | Subprocess calls are expensive (~1-3s each). 2 min cache eliminates most repeat calls. |
| Git status | 30s | Changes frequently during development. Shorter TTL. |
| Environment status | 60s | Middle ground — env files change occasionally. |

All TTLs are generous because the devops cache already has mtime-based
invalidation as a separate mechanism.  The mediator's TTL is a safety net,
not the primary staleness signal.  In Phase 3, we'll bridge mtime into the
mediator.  In Phase 2, TTL alone is enough.

### Deliverables

```
1. NEW: src/core/services/mediator/registrations/detect.py
   - register_detect(mediator) function
   - 13 node registrations with resolvers, TTLs
   - Resolvers are the RAW ops functions (same as devops __init__ registry)

2. MODIFIED: src/core/services/mediator/registrations/__init__.py
   - Import and call register_detect() in register_all()

3. NEW: tests/test_mediator_detect.py
   - Registration tests (13 nodes, TTLs, persist flags)
   - Resolver verification (all nodes have resolvers)
   - Tree structure tests (detect branch with 13 children)
   - Diag tests

4. MODIFIED: src/core/services/mediator/README.md
   - Document detect.* domain registration
```

### Chunk Breakdown

**Chunk 2.1 — Registration module (`registrations/detect.py`)**

Create `register_detect(mediator)` that registers 13 nodes. Each resolver
is a lambda wrapping the ops function with `mediator.project_root`:

```python
tree.register(TreeRegistration(
    path="detect.docker",
    resolver=lambda: docker_ops.docker_status(mediator.project_root),
    ttl=120,
    persist=True,
))
```

Pattern: identical to `registrations/posture.py` but with different
import sources (the ops modules instead of posture scanners).

**Chunk 2.2 — Wire into register_all()**

Add `from .detect import register_detect` and `register_detect(mediator)`
to `registrations/__init__.py`. After this, startup creates 19 nodes
total (6 posture + 13 detect).

**Chunk 2.3 — Tests**

Test categories:
1. All 13 detect nodes registered (names, TTLs, persist, resolvers)
2. Tree structure (detect branch, 13 children)
3. Detect.git has shorter TTL (30s vs 120s default)
4. No dependencies (all are leaves in Phase 2)
5. No dependents (no downstream nodes yet)
6. Diag shows 19 total nodes (6 posture + 13 detect)

**Chunk 2.4 — README update**

Add detect.* table to README's Domain Registrations section.

### What Phase 2 does NOT include

- **No route integration (`?via=mediator`)** — Unlike posture (Phase 1),
  we don't add dual-path to the 30+ devops card routes yet. That's Phase 3
  which bridges the devops cache.
- **No mtime-based invalidation** — The mediator uses TTL only in Phase 2.
  Mtime bridging comes in Phase 3.
- **No cascade dependencies** — Detect nodes are independent leaves.
  Dependencies like `devops.docker → detect.docker` come in Phase 3.
- **No EventBus publishing** — No `cache:hit`/`cache:miss` events yet.
  That's Phase 5.
- **No replacement of devops cache** — The devops cache and mediator
  coexist. Detect.* in the mediator is additive — it provides a cached
  layer that Phase 3 can tap into.

### What Phase 2 DOES

- **Eliminates future duplicate subprocess calls** — Once devops routes
  (Phase 3) use `mediator.get("detect.docker")` instead of calling
  `docker_ops.docker_status(root)` directly, every duplicate call is eliminated.
- **Establishes the `detect.*` namespace** — The tree has 19 reachable
  nodes across 2 domains (posture, detect).
- **Proves the pattern scales** — Registration is modular; adding a domain
  is one file + one line in `register_all()`.
- **Prepares the foundation for Phase 3** — When devops.* nodes declare
  `depends_on=["detect.docker"]`, the cascade engine works automatically.

### Validation Criteria

1. **19 total nodes** in the tree (6 posture + 13 detect)
2. **detect branch** has 13 registered children
3. **All 13 detect nodes have resolvers** (callable)
4. **TTLs are correct** (docker=120, git=30, env=60, etc.)
5. **Persist flags are correct** (git and env are False, rest True)
6. **No dependencies** — all detect nodes are independent leaves
7. **Startup succeeds** with both registrations active
8. **All tests pass** (Phase 0 + Phase 1 + Phase 2)

### Phase 2 Checklist

```
[x] Create registrations/detect.py — register 13 nodes
[x] Wire register_detect() in registrations/__init__.py
[x] Write Phase 2 tests — 22 tests (77 total with Phase 0+1)
[x] Verify startup with both registrations — 19 nodes confirmed
[x] Update README.md with detect.* domain docs
```

---

## Phase 3 — DevOps Wire (`devops.*`)

### Investigation Summary

Phase 3 was originally scoped as "register devops.* nodes, bridge mtime-based
cache, dual-path in card routes." After thorough investigation of the devops
cache system, the scope is narrower and more surgical than expected.

**What `get_cached()` does (7 side effects beyond caching):**

```
get_cached(root, "docker", lambda: docker_ops.docker_status(root), force=force)
  │
  ├── 1. Mtime check         → _max_mtime(root, _WATCH_PATHS["docker"])
  ├── 2. Per-key lock         → _get_key_lock("docker")
  ├── 3. Compute              → docker_ops.docker_status(root)
  ├── 4. File persistence     → _save_cache(root, cache) → .state/devops_cache.json
  ├── 5. EventBus publish     → cache:hit / cache:miss / cache:done / cache:error
  ├── 6. Activity logging     → record_scan_activity() → .state/audit_activity.json
  ├── 7. Audit staging        → stage_audit() → .state/pending_audits.json
  └── 8. _cache metadata      → adds {_cache: {computed_at, fresh, age_seconds}}
```

**Why this matters:** These 7 side effects are consumed by the activity timeline,
audit pipeline, SSE event stream, and frontend age display. Replacing `get_cached`
would break all of them. The devops cache is not just a cache — it's a **compute
pipeline** with observability, audit trail, and persistence.

**34 call sites** in the route layer call `get_cached`. Modifying them all is
high-risk and scope-bloat.

### Strategy: Compose, Don't Replace

Instead of replacing `get_cached` or adding `?via=mediator` to 34 routes,
Phase 3 takes a smarter approach:

**The detect.* resolvers already wrap the same ops functions.** The bridge
is to make Phase 3 teach the devops cache about the mediator — not the
other way around.

Specifically:

1. **Register `devops.*` nodes** in the mediator tree with the SAME keys
   as the devops cache (`docker`, `k8s`, `security`, etc.)
2. **Resolvers go THROUGH `get_cached`** — so all 7 side effects are preserved
3. **`detect.*` → `devops.*` dependency chain** — invalidating a detect node
   cascades to the devops node
4. **New: mediator-aware bust** — when `/devops/cache/bust` fires, it also
   invalidates the mediator's detect.* and devops.* nodes

This approach means:
- **Zero route changes** — existing routes continue using `get_cached`
- **All side effects preserved** — activity, audit staging, EventBus, persistence
- **Mediator provides the hierarchy** — `mediator.get("devops.docker")` works
- **Cascade from detect → devops** — unified dependency graph
- **Foundation for Phase 4** — when cascade engine replaces imperative cascade

### What We Register

**DevOps card nodes (13 nodes):**

| Path | Devops Cache Key | Resolver | TTL | Depends On |
|------|-----------------|----------|-----|------------|
| `devops.docker` | `"docker"` | `get_cached(root, "docker", ...)` | mtime | `detect.docker` |
| `devops.k8s` | `"k8s"` | `get_cached(root, "k8s", ...)` | mtime | `detect.k8s` |
| `devops.git` | `"git"` | `get_cached(root, "git", ...)` | mtime | `detect.git` |
| `devops.github` | `"github"` | `get_cached(root, "github", ...)` | mtime | `detect.github` |
| `devops.ci` | `"ci"` | `get_cached(root, "ci", ...)` | mtime | `detect.ci` |
| `devops.terraform` | `"terraform"` | `get_cached(root, "terraform", ...)` | mtime | `detect.terraform` |
| `devops.env` | `"env"` | `get_cached(root, "env", ...)` | mtime | `detect.env` |
| `devops.security` | `"security"` | `get_cached(root, "security", ...)` | mtime | `detect.security` |
| `devops.packages` | `"packages"` | `get_cached(root, "packages", ...)` | mtime | `detect.packages` |
| `devops.quality` | `"quality"` | `get_cached(root, "quality", ...)` | mtime | `detect.quality` |
| `devops.testing` | `"testing"` | `get_cached(root, "testing", ...)` | mtime | `detect.testing` |
| `devops.docs` | `"docs"` | `get_cached(root, "docs", ...)` | mtime | `detect.docs` |
| `devops.dns` | `"dns"` | `get_cached(root, "dns", ...)` | mtime | `detect.dns` |

**Key design: TTL = None (mtime-delegated)**

The devops.* nodes have `ttl=None` because freshness is determined by
`get_cached`'s own mtime logic, not the mediator's TTL. The mediator
resolves these nodes but delegates staleness to the devops cache. This
avoids the dual-TTL problem: there's one source of truth for staleness
(the devops cache's mtime check), not two.

### Dependency Graph

```
detect.docker  ────→  devops.docker
detect.k8s     ────→  devops.k8s
detect.git     ────→  devops.git
detect.github  ────→  devops.github
detect.ci      ────→  devops.ci
...            ────→  ...

Cascade: mediator.put("detect.docker") → invalidates devops.docker
```

The cascade direction is `detect → devops`. When tool availability changes
(e.g., Docker installed/updated), the detect.* node is invalidated, which
cascades to invalidate the devops.* node. On next access, devops.* calls
`get_cached` which runs the mtime check and potentially recomputes.

### Bust Integration

**Current flow:**
```
POST /devops/cache/bust {card: "docker"}
  → devops_cache.invalidate_with_cascade("docker")
  → deletes from .state/devops_cache.json
```

**Phase 3 addition:**
```
POST /devops/cache/bust {card: "docker"}
  → devops_cache.invalidate_with_cascade("docker")     (existing)
  → mediator.put("devops.docker", cascade=True)         (new)
     → also invalidates detect.docker (reverse cascade)
```

This is a one-line addition to the bust handler, not a rewrite.

### Deliverables

```
1. NEW: src/core/services/mediator/registrations/devops.py
   - register_devops(mediator) function
   - 13 node registrations with get_cached-wrapping resolvers
   - depends_on declarations linking to detect.* nodes

2. MODIFIED: src/core/services/mediator/registrations/__init__.py
   - Import and call register_devops() in register_all()

3. MODIFIED: src/ui/web/routes/devops/__init__.py
   - Add mediator invalidation to devops_cache_bust handler
   - One-line addition, not rewrite

4. NEW: tests/test_mediator_devops.py
   - Registration tests (13 nodes, deps, resolvers)
   - Cascade tests (detect → devops dependency chain)
   - Bust integration test (mediator invalidation on bust)
   - Tree structure tests (3 branches: posture, detect, devops)
   - Diag tests

5. MODIFIED: src/core/services/mediator/README.md
   - Document devops.* domain registration
```

### Chunk Breakdown

**Chunk 3.1 — Registration module (`registrations/devops.py`)**

Create `register_devops(mediator)` that registers 13 nodes. Each resolver
wraps `get_cached` to preserve all side effects:

```python
from src.core.services.devops.cache import get_cached

tree.register(TreeRegistration(
    path="devops.docker",
    resolver=lambda: get_cached(
        root, "docker",
        lambda: docker_ops.docker_status(root),
    ),
    ttl=None,        # mtime-delegated to get_cached
    persist=False,   # devops cache handles its own persistence
    depends_on=["detect.docker"],
))
```

The ops module imports are deferred (same pattern as detect.py).
The devops cache `get_cached` import is deferred too.

**Chunk 3.2 — Wire into register_all()**

Add `from .devops import register_devops` and `register_devops(mediator)`
to `registrations/__init__.py`. After this, startup creates 32 nodes total
(6 posture + 13 detect + 13 devops).

**Chunk 3.3 — Bust integration**

Add mediator invalidation to `devops_cache_bust()` in `routes/devops/__init__.py`:

```python
# After existing invalidation:
try:
    from src.core.services.mediator import get_mediator
    m = get_mediator()
    if card == "all":
        m.put("devops", cascade=True)
        m.put("detect", cascade=True)
    else:
        m.put(f"devops.{card}", cascade=True)
except Exception:
    pass  # mediator bust is best-effort
```

**Chunk 3.4 — Tests**

Test categories:
1. All 13 devops nodes registered (names, deps, resolvers)
2. Tree has 3 branches (posture, detect, devops)
3. 32 total nodes
4. `devops.docker` depends_on `detect.docker` (for all 13 pairs)
5. `detect.docker` has `devops.docker` as dependent
6. Cascade: invalidate `detect.docker` → `devops.docker` invalidated
7. TTL=None for all devops nodes
8. persist=False for all devops nodes (delegated to get_cached)
9. Diag shows 32 registered nodes
10. Bust integration: mediator nodes invalidated on bust

**Chunk 3.5 — README update**

Add devops.* domain docs with the composition strategy explanation.

### What Phase 3 does NOT include

- **No route changes** — Routes continue using `get_cached` directly.
  The mediator wraps `get_cached`, not the other way around.
- **No `?via=mediator` on card routes** — Unlike posture (Phase 1),
  no dual-path. The mediator path is available via `mediator.get("devops.docker")`
  for internal use, but routes don't expose it yet.
- **No mtime logic in the mediator** — The mediator delegates freshness
  to `get_cached`'s mtime check. Phase 4 may bring mtime awareness.
- **No replacement of devops cache** — The devops cache continues operating
  independently. The mediator adds hierarchy and cascade on top.
- **No audit node registration** — `audit:scores`, `audit:system`, etc.
  are deferred. They use `get_cached` too, but adding them is mechanical
  once the devops pattern works.

### What Phase 3 DOES

- **Establishes `devops.*` namespace** — The tree has 32 nodes across 3 domains.
- **Creates detect → devops dependency chain** — Invalidating detection
  cascades to devops cards. This is the first cross-domain cascade.
- **Bridges the devops cache into the hierarchy** — `mediator.get("devops.docker")`
  returns the same data as `get_cached(root, "docker", ...)` but with
  mediator metadata (seq, source, age).
- **Bust integration** — Server-side bust also invalidates mediator nodes.
- **Foundation for Phase 4** — The declarative dependency graph now spans
  three domains. Phase 4 can replace the devops cache's hardcoded `_CASCADE`
  dict with the mediator's dependency graph.

### Validation Criteria

1. **32 total nodes** in the tree (6 posture + 13 detect + 13 devops)
2. **3 top-level branches** (posture, detect, devops)
3. **All 13 devops nodes have resolvers** (callable)
4. **All 13 devops nodes have depends_on** pointing to detect.*
5. **All 13 detect nodes have dependents** pointing to devops.*
6. **TTL is None** for all devops nodes
7. **Persist is False** for all devops nodes
8. **Cascade works**: `put("detect.docker")` invalidates `devops.docker`
9. **Bust integration**: POST /devops/cache/bust also invalidates mediator
10. **All tests pass** (Phase 0 + Phase 1 + Phase 2 + Phase 3)
11. **Existing routes unchanged** — no regression in card data

### Phase 3 Checklist

```
[x] Create registrations/devops.py — register 13 nodes with get_cached resolvers
[x] Wire register_devops() in registrations/__init__.py
[x] Add mediator invalidation to devops_cache_bust() handler
[x] Write Phase 3 tests — 43 tests (120 total with Phase 0+1+2)
[x] Verify startup with all 3 registrations — 32 nodes confirmed
[x] Update README.md with devops.* domain docs
```

### Risk Assessment

**Risk: Circular resolver calls**
- devops.docker resolver calls `get_cached("docker", ...)` which calls
  `docker_ops.docker_status(root)`. No mediator involved → no circularity.
- detect.docker resolver also calls `docker_ops.docker_status(root)` directly.
- The two resolvers are independent — they don't call each other.

**Risk: Double computation**
- If both `detect.docker` and `devops.docker` are accessed simultaneously,
  `docker_ops.docker_status(root)` could run twice (once via detect.docker's
  resolver, once via get_cached's compute_fn inside devops.docker's resolver).
- Mitigation: `get_cached` holds a per-key lock. The mediator also holds a
  per-path compute lock. These prevent truly concurrent duplicate computation.
- Acceptable: In Phase 4, the devops.docker resolver can be changed to
  `mediator.get("detect.docker")["data"]` instead, eliminating the duplicate.
  Not worth the coupling in Phase 3.

**Risk: Bust event ordering**
- The bust handler invalidates devops cache first, then mediator.
- If a request arrives between the two, it gets stale mediator data but
  fresh devops data. This is acceptable — the mediator is additive, not
  authoritative.

---

---

## Phase 4 — Cascade Engine (declarative graph replaces imperative cascade)

### Investigation Summary

The system currently has **three independent cascade mechanisms**:

**1. Backend `_CASCADE` dict** (devops/cache.py, line 590-594):
```python
_CASCADE: dict[str, list[str]] = {
    "git":    ["github", "docker", "ci", "pages"],
    "docker": ["ci", "k8s"],
    "github": ["ci"],
    "pages":  ["dns"],
}
```
Used only by `invalidate_with_cascade()`, called only from the bust handler.
Additionally, `_AGGREGATE_KEYS = ["project-status"]` is busted whenever
ANY integration card changes.

**2. Frontend `_CASCADE` dict** (_cache.html, line 146-151):
```javascript
const _CASCADE = {
    'git': ['github', 'docker', 'ci', 'pages'],
    'docker': ['ci', 'k8s'],
    'github': ['ci'],
    'pages': ['dns'],
};
```
Exact copy of the backend. Used by `cardRefresh()` to bust client-side
sessionStorage entries. Also hardcodes `project-status` and `health-score`
invalidation on every card refresh.

**3. Mediator dependency graph** (Phase 1-3):
- `posture.{pillar}` → `posture.full` → `posture.summary`
- `detect.*` → `devops.*` (13 pairs)

These three are **disconnected**. The mediator has the best graph infrastructure
(transitive walk, glob support, bidirectional lookup) but doesn't know about the
devops cache's inter-card cascade rules.

**Dead code in `invalidate_with_cascade`:** The `hp:{card_key}` health probe
key pattern (`hp:docker`, `hp:ci`, etc.) is checked against `_WATCH_PATHS`
but no `hp:*` keys exist in `_WATCH_PATHS`. This is dead code.

### What Phase 4 Does

Phase 4 migrates the hardcoded `_CASCADE` dict into the mediator's
declarative dependency graph. After this phase:

- **Source of truth for cascade rules lives in the mediator tree**
- `invalidate_with_cascade()` delegates to the mediator instead of its own dict
- Inter-devops dependencies are expressed as `depends_on` relationships
- The `project-status` aggregate is a mediator node

### The Graph After Phase 4

```
Current _CASCADE semantics (what it means):
  git changes      → github, docker, ci, pages may be affected
  docker changes   → ci, k8s may be affected
  github changes   → ci may be affected
  pages changes    → dns may be affected

Expressed as mediator depends_on:
  devops.github    depends_on=[detect.github, devops.git]
  devops.docker    depends_on=[detect.docker, devops.git]
  devops.ci        depends_on=[detect.ci, devops.git, devops.docker, devops.github]
  devops.pages     depends_on=[detect.pages, devops.git]
  devops.k8s       depends_on=[detect.k8s, devops.docker]
  devops.dns       depends_on=[detect.dns, devops.pages]

unchanged (single detect.* dependency only):
  devops.terraform depends_on=[detect.terraform]
  devops.env       depends_on=[detect.env]
  devops.security  depends_on=[detect.security]
  devops.packages  depends_on=[detect.packages]
  devops.quality   depends_on=[detect.quality]
  devops.testing   depends_on=[detect.testing]
  devops.docs      depends_on=[detect.docs]
  devops.git       depends_on=[detect.git]
```

**Key insight:** The _CASCADE dict says "when git changes, also bust github,
docker, ci, pages." In dependency graph terms, devops.github DEPENDS ON
devops.git (among others). When devops.git is invalidated, cascade walks
`dependents("devops.git")` and finds devops.github, devops.docker,
devops.ci, devops.pages.

**Direction mapping:**
```
_CASCADE["git"] = ["github", "docker", "ci", "pages"]
  ↓ reversed into depends_on ↓
devops.github  depends_on includes devops.git
devops.docker  depends_on includes devops.git
devops.ci      depends_on includes devops.git
devops.pages   depends_on includes devops.git
```

### Aggregate Node: `devops.status`

The `project-status` cache key is an aggregate that depends on ALL
integration cards. In the mediator, this becomes a node:

```
devops.status
  depends_on=["devops.*"]    ← glob pattern (already supported)
  resolver=lambda: run_all_probes(root) + suggest_next + compute_progress
  ttl=None (mtime-delegated via get_cached)
```

When ANY devops.* node is invalidated, `devops.status` is also invalidated.
This replaces the hardcoded `_AGGREGATE_KEYS = ["project-status"]`.

### The Migration Strategy

**Phase 4 does NOT delete `_CASCADE` or `invalidate_with_cascade`.** Instead:

1. **Add inter-devops dependencies** to `registrations/devops.py`
2. **Add `devops.status` node** that depends on `devops.*` (glob)
3. **Add a mediator-driven cascade function** (`mediator_cascade()`)
4. **Redirect `invalidate_with_cascade` to use mediator when available**
5. **Frontend stays unchanged** — still uses its own `_CASCADE` for now

The frontend `_CASCADE` is client-side only (sessionStorage invalidation).
Replacing it requires exposing the dependency graph via an API endpoint,
which is Phase 5+ scope.

### Deliverables

```
1. MODIFIED: src/core/services/mediator/registrations/devops.py
   - Add inter-devops dependencies (git→github, git→docker, etc.)
   - Add devops.status aggregate node

2. MODIFIED: src/core/services/devops/cache.py
   - invalidate_with_cascade() uses mediator graph when available
   - Falls back to hardcoded _CASCADE when mediator not initialized

3. NEW: tests/test_mediator_cascade.py
   - Inter-devops cascade tests
   - Aggregate node tests (devops.status)
   - Full cascade chain tests (detect → devops → dependents)
   - Equivalence tests (mediator cascade = _CASCADE result)

4. MODIFIED: tests/test_mediator_devops.py
   - Update dependency counts to include inter-devops deps

5. MODIFIED: src/core/services/mediator/README.md
   - Document cascade engine, dependency graph visualization
```

### Chunk Breakdown

**Chunk 4.1 — Add inter-devops dependencies**

Modify `registrations/devops.py` to add the inter-devops dependencies.
Currently each devops.* node has `depends_on=[detect.*]` only. Add:

```python
# Phase 4: inter-devops dependencies (mirrors _CASCADE)
#
# _CASCADE["git"] = ["github", "docker", "ci", "pages"]
# → devops.github additionally depends_on devops.git
# → devops.docker additionally depends_on devops.git
# → devops.ci     additionally depends_on devops.git
# → devops.pages  additionally depends_on devops.git
#
# _CASCADE["docker"] = ["ci", "k8s"]
# → devops.ci additionally depends_on devops.docker
# → devops.k8s additionally depends_on devops.docker
#
# _CASCADE["github"] = ["ci"]
# → devops.ci additionally depends_on devops.github
#
# _CASCADE["pages"] = ["dns"]
# → devops.dns additionally depends_on devops.pages

_INTER_DEVOPS_DEPS: dict[str, list[str]] = {
    "devops.github":  ["devops.git"],
    "devops.docker":  ["devops.git"],
    "devops.ci":      ["devops.git", "devops.docker", "devops.github"],
    "devops.pages":   ["devops.git"],
    "devops.k8s":     ["devops.docker"],
    "devops.dns":     ["devops.pages"],
}
```

The `depends_on` for each node becomes `[detect.*] + inter-devops deps`.

**Chunk 4.2 — Add `devops.status` aggregate node**

Register a new node in `registrations/devops.py`:

```python
tree.register(TreeRegistration(
    path="devops.status",
    resolver=lambda: get_cached(
        root, "project-status",
        lambda: {
            "integrations": run_all_probes(root),
            "suggested_next": suggest_next(run_all_probes(root)),
            "progress": compute_progress(run_all_probes(root)),
        },
    ),
    ttl=None,
    persist=False,
    depends_on=["devops.*"],  # glob → depends on ALL devops nodes
))
```

This means when ANY `devops.*` node is invalidated, `devops.status`
is also invalidated. Replaces the hardcoded `_AGGREGATE_KEYS`.

After this chunk: **33 total nodes** (6 posture + 13 detect + 14 devops).

**Chunk 4.3 — Redirect `invalidate_with_cascade`**

Modify `invalidate_with_cascade()` in `devops/cache.py` to optionally use
the mediator's dependency graph:

```python
def invalidate_with_cascade(project_root: Path, card_key: str) -> list[str]:
    # Try mediator-driven cascade first
    mediator_keys = _mediator_cascade(card_key)
    if mediator_keys is not None:
        keys_to_bust = mediator_keys
    else:
        # Fallback: hardcoded _CASCADE
        keys_to_bust = _legacy_cascade(card_key)

    # Aggregate cascade: any integration card → bust aggregates
    if card_key in _INTEGRATION_KEYS:
        keys_to_bust.extend(_AGGREGATE_KEYS)

    # Single read-modify-write
    with _file_lock:
        cache = _load_cache(project_root)
        changed = False
        for k in keys_to_bust:
            if k in cache:
                del cache[k]
                changed = True
        if changed:
            _save_cache(project_root, cache)

    return keys_to_bust


def _mediator_cascade(card_key: str) -> list[str] | None:
    """Get cascade keys from the mediator dependency graph.

    Returns None if mediator is not available (fallback to legacy).
    Returns list of devops cache keys to bust (not mediator paths).
    """
    try:
        from src.core.services.mediator import get_mediator
        m = get_mediator()

        # Map card_key to mediator path
        mediator_path = f"devops.{card_key}"
        node = m.tree.resolve(mediator_path)
        if node is None:
            return None  # unknown card, fall back to legacy

        # Get all dependents (transitive)
        dep_paths = m.tree.dependents(mediator_path)

        # Convert mediator paths back to cache keys
        # devops.github → "github", devops.status → "project-status"
        keys = [card_key]
        for dep in dep_paths:
            if dep.startswith("devops."):
                suffix = dep[len("devops."):]
                if suffix == "status":
                    keys.append("project-status")
                else:
                    keys.append(suffix)
        return keys
    except Exception:
        return None  # mediator not available, fall back to legacy


def _legacy_cascade(card_key: str) -> list[str]:
    """Original hardcoded cascade logic (fallback)."""
    keys = [card_key]
    for dep in _CASCADE.get(card_key, []):
        keys.append(dep)
    return keys
```

**Important safety pattern:** The mediator cascade returns `None` if
unavailable, triggering fallback to the existing `_CASCADE` dict. This
means the system never regresses — if the mediator isn't initialized
(tests, CLI, non-web contexts), the legacy cascade continues working.

**Chunk 4.4 — Tests**

Test categories:

**4.4a — Inter-devops cascade tests:**
1. `devops.git` dependents include `[devops.github, devops.docker, devops.ci, devops.pages]`
2. `devops.docker` dependents include `[devops.ci, devops.k8s]`
3. `devops.github` dependents include `[devops.ci]`
4. `devops.pages` dependents include `[devops.dns]`
5. Transitive: `detect.git` → `devops.git` → `[devops.github, devops.docker, devops.ci, devops.pages]`
6. `devops.ci` depends_on `[detect.ci, devops.git, devops.docker, devops.github]`

**4.4b — Aggregate node tests:**
7. `devops.status` is registered (has resolver, ttl=None)
8. `devops.status` depends_on includes all 13 devops card nodes (glob match)
9. Invalidating any devops.* node cascades to devops.status
10. 33 total nodes

**4.4c — Equivalence tests:**
11. For each key in `_CASCADE`, verify the mediator cascade produces
    the same set of keys (superset is fine, subset is a bug)
12. `invalidate_with_cascade("git")` returns keys that include all of
    `["git", "github", "docker", "ci", "pages"]`

**4.4d — Fallback tests:**
13. `_mediator_cascade` returns None when mediator not initialized
14. `_legacy_cascade` produces same result as old `_CASCADE` dict

**Chunk 4.5 — Update existing tests & README**

- Update `test_mediator_devops.py`: dependency counts change for 6 nodes
- Update README with cascade engine docs and dependency visualization

### What Phase 4 does NOT include

- **No frontend changes** — The client-side `_CASCADE` dict stays for now.
  Exposing the dependency graph via API is Phase 5+ scope.
- **No deletion of `_CASCADE` dict** — It stays as fallback documentation.
  Removing it is a follow-up once the mediator cascade is proven in production.
- **No `hp:` health probe cleanup** — Dead code removal is a separate task.
- **No new route endpoints** — No `/mediator/cascade` API yet.

### What Phase 4 DOES

- **Unifies cascade logic** — One graph, one source of truth (mediator tree)
- **Adds inter-devops dependencies** — git→github, docker→k8s, etc.
- **Adds aggregate node** — `devops.status` depends on all cards
- **Safe migration** — Falls back to `_CASCADE` when mediator unavailable
- **Enables future phases** — Graph-aware invalidation for SSE delta events

### Validation Criteria

1. **33 total nodes** (6 posture + 13 detect + 14 devops)
2. **Cascade equivalence**: `_mediator_cascade("git")` ⊇ `_legacy_cascade("git")`
3. **Transitive cascade**: `put("detect.git")` invalidates devops.git AND
   devops.github, devops.docker, devops.ci, devops.pages, devops.status
4. **Aggregate node**: invalidating any devops.* invalidates devops.status
5. **Fallback works**: system functions normally without mediator initialized
6. **All existing tests still pass** (Phase 0+1+2+3 tests)
7. **Frontend unchanged** — no regression in card refresh behavior

### Phase 4 Checklist

```
[x] Add inter-devops dependencies to registrations/devops.py
[x] Add devops.status aggregate node
[x] Redirect invalidate_with_cascade to use mediator graph
[x] Write Phase 4 tests — 30 tests (150 total with Phase 0+1+2+3)
[x] Update test_mediator_devops.py for new dependency counts
[x] Verify 33 total nodes at startup
[x] Update README with cascade engine docs
```

### Risk Assessment

**Risk: Circular dependencies**
- `devops.ci` depends on `devops.git`, `devops.docker`, `devops.github`.
  `devops.git` does NOT depend on `devops.ci`. These are DAG edges, no cycles.
- The dependency walker has `visited` set protection (`_walk_dependents`).
  Even if a cycle existed, it would terminate without infinite recursion.

**Risk: Cascade explosion**
- Worst case: `detect.git` → `devops.git` → `[devops.github, devops.docker,
  devops.ci, devops.pages]` → `devops.status` → `devops.dns` (via pages→dns),
  `devops.k8s` (via docker→k8s). That's 8 nodes invalidated. This exactly
  matches the behavior of the hardcoded `_CASCADE` + `_AGGREGATE_KEYS`.
- The mediator cascade may produce a slightly larger set than the legacy
  cascade (because of transitive walking), but this is CORRECT behavior —
  the legacy cascade was shallow (one level only).

**Risk: Order sensitivity in `register_devops`**
- The `_recompute_dependents()` call after each `register()` handles reverse
  dependency updates. Even if `devops.ci` is registered before `devops.git`,
  the final `_recompute_dependents()` call will correctly establish all edges.
- However, `depends_on=["devops.git"]` on `devops.ci` requires that
  `devops.git` is already registered. If not, the dependency is silently
  ignored. **Fix:** register nodes in dependency order (leaves first), or
  add a final `_recompute_dependents()` call after all registrations.

**Risk: Performance of `_mediator_cascade` in `invalidate_with_cascade`**
- The mediator cascade involves: import check, tree resolve, transitive
  dependent walk (N nodes, M edges), path-to-key mapping. For 33 nodes
  this is microseconds. Not a concern.

## Phase 5 — EventBus Bridge + Path Delta

> **Goal:** Make the mediator observable. Every data change publishes an event
> through the EventBus, enabling SSE consumers to know WHAT changed. Consumers
> can skip unchanged data via `since_seq`.
>
> **Source:** Model §4 "The Delta — Never Reset the Whole" + Model §5 "subscribe"
> + Milestone §4 "Delta & Subscription" + Milestone Target Outcome "Delta-only patches"

### Investigation Summary

**What exists:**

| Component | Current State | What Phase 5 Adds |
|---|---|---|
| `QueryMediator._seq` | Monotonic counter, incremented on every `put()` | Per-node `last_change_seq` tracking |
| `CacheEntry.seq` | Set on cache write | Unchanged (already tracks write-time seq) |
| `put()` return | `{"invalidated": [...], "seq": N}` | Also publishes `mediator:changed` on EventBus |
| `get()` params | `force`, `max_age`, `explain` | Adds `since_seq` parameter |
| `EventBus.publish()` | Supports any event type, auto-assigns bus seq | Receives `mediator:changed` and `mediator:write` events |
| SSE frontend | Listens to EventBus via `/api/events` | Receives mediator events (frontend wiring is later phase) |

**What we're NOT building in Phase 5:**

- No field-level delta (deep diff). Path-level delta only.
- No `subscribe(pattern, callback)` in-process callbacks (Phase 6).
- No frontend JS changes (frontend wiring is a follow-up).
- No stale-while-revalidate (Phase 6 with background queue).

**Design decisions:**

1. **One aggregate event per `put()`, not N individual events.** When `devops.git`
   is invalidated and cascades to docker, github, ci, k8s, status — ONE event
   fires listing all affected paths. This lets consumers batch their reactions.

2. **Two event types:**
   - `mediator:write` — new data was written to a path (has `data` payload)
   - `mediator:invalidated` — paths were invalidated (no data, consumer should re-fetch)

3. **`since_seq` returns `{changed: False}` or full data.** Not a diff.
   The consumer uses it to skip re-fetching unchanged nodes. Full field-level
   delta is a future optimization (the seq infrastructure enables it later).

4. **Batch context manager for startup.** During `register_all()` + initial
   population, dozens of `put()` calls happen. A `batch()` context manager
   suppresses individual events and publishes one aggregate at the end.

5. **`notify=False` parameter** for internal operations that shouldn't broadcast
   (e.g., cache warming on startup, test fixtures).

### Deliverables

| File | Change | Lines |
|---|---|---|
| `src/core/services/mediator/core.py` | Add `_publish_change()`, `since_seq` in `get()`, `batch()` context manager, `notify` param | ~80 |
| `src/core/services/mediator/tree.py` | Add `last_change_seq` field to `TreeNode` | ~3 |
| `tests/test_mediator_delta.py` | Phase 5 tests: seq tracking, EventBus integration, batch, since_seq | ~250 |
| `src/core/services/mediator/README.md` | Phase 5 docs: EventBus bridge, delta protocol, batch | ~40 |
| `.agent/plans/query-mediator-plan.md` | Phase 5 checklist complete | update |

### Chunk Breakdown

#### Chunk 5.1: Node seq tracking

**TreeNode gets `last_change_seq`:**

```python
# tree.py — TreeNode dataclass
last_change_seq: int = 0  # seq of last write/invalidation
```

**`put()` stamps the affected node:**

When `put(path, data=X)` writes data, set `node.last_change_seq = seq`.
When `put(path)` invalidates, also set `node.last_change_seq = seq`.
When cascade invalidates dependents, stamp each dependent node too.

This enables `get(since_seq=N)` — if `node.last_change_seq <= N`, the
consumer already has the latest version.

**Files:** `tree.py` (1 field), `core.py` (`put()` stamps nodes)

#### Chunk 5.2: `since_seq` parameter on `get()`

```python
def get(self, path: str, *, since_seq: int | None = None, ...) -> dict:
    """
    If since_seq is provided and node.last_change_seq <= since_seq,
    return {"changed": False, "meta": {"current_seq": node.last_change_seq}}
    without computing or returning data.

    Otherwise, normal get() behavior (compute if needed, return data).
    """
```

This is the consumer's shortcut: "I have seq=142 for this path, is there
anything new?" If not, skip. If yes, compute and return normally.

**Files:** `core.py` (`get()` method)

#### Chunk 5.3: EventBus publishing in `put()`

```python
def put(self, path, data=None, *, cascade=True, cascade_depth=-1,
        notify=True) -> dict:
    # ... existing write/invalidate/cascade logic ...

    # Phase 5: publish change event
    if notify and not self._batch_active:
        self._publish_change(path, seq, writes, invalidated)

    return {"invalidated": invalidated, "seq": seq}

def _publish_change(self, trigger: str, seq: int,
                    writes: list[str], invalidated: list[str]) -> None:
    """Publish a mediator change event on the EventBus."""
    from src.core.services.event_bus import bus

    if writes:
        bus.publish("mediator:write", key=trigger, data={
            "trigger": trigger,
            "mediator_seq": seq,
            "writes": writes,
        })

    if invalidated:
        bus.publish("mediator:invalidated", key=trigger, data={
            "trigger": trigger,
            "mediator_seq": seq,
            "invalidated": invalidated,
        })
```

**`notify=False`** suppresses events. Used for:
- Test fixtures that seed data without noise
- Internal cache warming during startup

**Files:** `core.py` (`put()`, `_publish_change()`)

#### Chunk 5.4: Batch context manager

```python
@contextmanager
def batch(self):
    """Accumulate changes and publish one aggregate event at the end.

    Usage::

        with mediator.batch():
            mediator.put("devops.git", data=git_data)
            mediator.put("devops.docker", data=docker_data)
            mediator.put("devops.ci", data=ci_data)
        # → ONE mediator:write event listing all 3 paths

    During batch mode:
    - Individual put() calls do NOT publish events
    - Changes accumulate in _batch_writes and _batch_invalidated
    - On exit, one aggregate event publishes
    """
```

Internal state:
```python
self._batch_active: bool = False
self._batch_writes: list[str] = []
self._batch_invalidated: list[str] = []
self._batch_seq: int = 0
```

**Files:** `core.py` (context manager + state fields)

#### Chunk 5.5: Tests

```
tests/test_mediator_delta.py

TestNodeSeqTracking:
  - test_put_write_stamps_node_seq
  - test_put_invalidate_stamps_node_seq
  - test_cascade_stamps_dependent_nodes
  - test_initial_last_change_seq_is_zero
  - test_seq_is_monotonically_increasing

TestSinceSeq:
  - test_get_since_seq_unchanged_returns_false
  - test_get_since_seq_changed_returns_data
  - test_get_since_seq_zero_always_returns_data
  - test_get_since_seq_none_is_normal_get

TestEventBusPublishing:
  - test_put_write_publishes_mediator_write
  - test_put_invalidate_publishes_mediator_invalidated
  - test_cascade_invalidation_publishes_all_paths
  - test_notify_false_suppresses_events
  - test_event_payload_structure

TestBatchMode:
  - test_batch_suppresses_individual_events
  - test_batch_publishes_aggregate_on_exit
  - test_batch_accumulates_writes_and_invalidations
  - test_nested_batch_raises_error
  - test_batch_empty_no_event

TestDiag (Phase 5 additions):
  - test_diag_includes_last_change_seq
  - test_diag_includes_batch_state
```

### Risk Assessment

**Risk: EventBus import in mediator creates circular dependency**
- `core.py` imports `event_bus.bus` inside `_publish_change()` (deferred import).
- The EventBus module doesn't import from mediator. No cycle.
- Same pattern as `_mediator_cascade()` in `devops/cache.py`.

**Risk: Batch mode not thread-safe**
- Batch is designed for single-thread startup sequences, not concurrent use.
- `_batch_active` is checked in `put()` which already holds `_lock`.
- If batch is used from multiple threads simultaneously, writes accumulate
  correctly (protected by `_lock`) but the aggregate event fires once per
  context manager exit. This is acceptable.

**Risk: Event storms from cascade invalidation**
- Without batch mode, invalidating `detect.git` would fire ONE event listing
  all affected paths. Not N events. This is bounded: worst case ~8 paths
  for git cascade. Not a concern.
- During startup, `register_all()` doesn't call `put()`, so no events fire
  during registration. Events only fire when data is written/invalidated.

**Risk: `since_seq` stale reads**
- `last_change_seq` is set AFTER data is written/removed. A concurrent reader
  checking `since_seq` might see the new seq but old data, or old seq but new
  data. Both are safe: the worst case is an unnecessary re-fetch (old seq) or
  a "no change" when data just changed (new seq, checked before write completes).
- This is acceptable for our use case (frontend polling, not transactional).

### Phase 5 Checklist

```
[x] Add last_change_seq field to TreeNode
[x] Stamp last_change_seq in put() (write + invalidate + cascade)
[x] Add since_seq parameter to get()
[x] Add _publish_change() method with EventBus integration
[x] Add notify parameter to put()
[x] Add batch() context manager
[x] Write Phase 5 tests — 21 tests (171 total with Phase 0–4)
[x] Update README with EventBus bridge docs
[x] Verify all 171 tests still pass
```

---

## Phase 6A — subscribe() + stale-while-revalidate

> **Goal:** Complete the reactive pattern (subscribe) and enable zero-latency
> stale reads (stale_ok). The mediator stays pure — no threading inside.
>
> **Source:** Model §5 "subscribe" + Model §6.3 "stale-while-revalidate"
> + Milestone Phase 5 "Priority Scheduling"
>
> **Design principle:** The mediator is a pure data coordination layer.
> Threading is a deployment concern, injected via `on_stale` hook.

### Investigation Summary

**What exists:**

| Component | Current State | What Phase 6A Adds |
|---|---|---|
| `put()` | Publishes `mediator:write`/`mediator:invalidated` on EventBus | Also calls `_notify_subscribers()` |
| `get()` | Returns stale data only for no-resolver nodes | `stale_ok=True` returns stale data for ANY node |
| `on_stale` | Does not exist | Injected hook called when stale data is served |
| `subscribe()` | Does not exist | Pure callback registry with pattern matching |
| `_refreshing` | Does not exist | Tracks which paths are being refreshed |

**What we're NOT building:**

- No threading inside the mediator (hook-based injection)
- No task queue / job system (Phase 6B)
- No parallel scanning (Phase 6B)
- No dispatch() command (Phase 6B)

**Design decisions:**

1. **subscribe() is synchronous.** Callbacks run inline in `put()` thread.
   Same pattern as `EventBus._subscribers`. Contract: callbacks must be fast.

2. **stale_ok is a read-side return change.** Mediator returns stale data with
   honest metadata. It does NOT spawn threads — it calls `on_stale(path)`.

3. **on_stale is dependency-injected.** In production, it spawns a daemon thread
   (following the proven `devops/cache.py` `_recompute_thread` pattern). In tests,
   it's None or a mock. Zero threading in tests.

4. **_refreshing is a set, protected by _lock.** `mark_refreshing()` and
   `clear_refreshing()` are explicit methods. No implicit state transitions.

5. **Subscriber errors are swallowed.** One bad callback doesn't block others.
   Errors are logged with the subscriber's pattern and path.

### Deliverables

| File | Change | Lines |
|---|---|---|
| `core.py` | `subscribe()`, `unsubscribe()`, `_notify_subscribers()` | ~45 |
| `core.py` | `stale_ok` param on `get()` | ~20 |
| `core.py` | `on_stale` hook, `_refreshing`, `mark_refreshing()`, `clear_refreshing()` | ~25 |
| `core.py` | `__init__` updates (subscriptions, refreshing, on_stale) | ~6 |
| `core.py` | `diag()` updates (subscriptions count, refreshing paths) | ~5 |
| `tests/test_mediator_subscribe.py` | subscribe/unsubscribe/pattern/error tests | ~150 |
| `tests/test_mediator_stale.py` | stale_ok + hook + refreshing tests | ~150 |
| `README.md` | Phase 6A docs | ~30 |

### Chunk Breakdown

#### Chunk 6A.1: subscribe() + unsubscribe() + _notify_subscribers()

```python
@dataclass
class _Subscription:
    id: str
    pattern: str
    callback: Callable[[dict], None]

def subscribe(self, pattern: str, callback: Callable[[dict], None]) -> str:
    """Register a callback for path pattern changes.
    
    Returns subscription ID for later unsubscribe().
    Pattern uses fnmatch glob syntax (same as depends_on).
    """

def unsubscribe(self, sub_id: str) -> bool:
    """Remove a subscription. Returns True if found."""

def _notify_subscribers(self, event_type: str, trigger: str,
                        seq: int, paths: list[str]) -> None:
    """Call all matching subscribers. Errors logged and swallowed."""
```

**Wiring into put():**
- `_notify_subscribers()` called AFTER `_publish_change()` (EventBus first, then in-process)
- In batch mode, subscribers notified on batch exit (same as EventBus)
- `notify=False` also suppresses subscriber notification

**Files:** `core.py`

#### Chunk 6A.2: stale_ok on get()

```python
def get(self, path, *, stale_ok=False, ...):
    # ... existing cache check detects staleness ...
    
    if not fresh and stale_ok and entry is not None:
        if explain:
            explanation.append(
                f"cache stale, age {age:.1f}s > max_age {eff}s, "
                f"stale_ok=True, returning stale"
            )
        # Call the stale hook (production: spawns bg thread)
        if self._on_stale is not None:
            self._on_stale(path)
        
        return self._make_result(
            entry.data, path, "cache_stale", age, entry.seq, explanation,
            stale=True, refreshing=(path in self._refreshing),
        )
    
    # ... existing blocking compute path (stale_ok=False) ...
```

**_make_result update:** Add optional `stale` and `refreshing` fields to meta.

**Files:** `core.py` (`get()`, `_make_result()`)

#### Chunk 6A.3: on_stale hook + refreshing state

```python
def __init__(self, tree, project_root, *, on_stale=None):
    # ... existing fields ...
    self._on_stale = on_stale
    self._refreshing: set[str] = set()
    self._subscriptions: dict[str, _Subscription] = {}
    self._sub_counter: int = 0

def mark_refreshing(self, path: str) -> None:
    with self._lock:
        self._refreshing.add(path)

def clear_refreshing(self, path: str) -> None:
    with self._lock:
        self._refreshing.discard(path)
```

**Files:** `core.py` (`__init__`, public methods)

#### Chunk 6A.4: diag() updates

```python
# Summary diag
return {
    "tree": tree_stats,
    "seq": self._seq,
    "cached": cached_count,
    "stale": stale_count,
    "batch_active": self._batch_active,
    "subscriptions": len(self._subscriptions),
    "refreshing": sorted(self._refreshing),
    "entries": entries,
}

# Detail diag — add refreshing flag
d["refreshing"] = path in self._refreshing
```

**Files:** `core.py` (`diag()`)

#### Chunk 6A.5: Tests

```
tests/test_mediator_subscribe.py

TestSubscribe:
  - test_subscribe_returns_unique_id
  - test_subscriber_called_on_write
  - test_subscriber_called_on_invalidation
  - test_wildcard_pattern_matches
  - test_exact_pattern_matches
  - test_non_matching_pattern_not_called
  - test_unsubscribe_stops_delivery
  - test_unsubscribe_unknown_id_returns_false
  - test_multiple_subscribers_all_called
  - test_subscriber_error_swallowed
  - test_notify_false_skips_subscribers
  - test_batch_notifies_on_exit

tests/test_mediator_stale.py

TestStaleOk:
  - test_stale_ok_returns_stale_data
  - test_stale_ok_meta_has_stale_flag
  - test_stale_ok_calls_on_stale_hook
  - test_stale_ok_no_hook_still_returns_stale
  - test_stale_ok_fresh_data_returns_normally
  - test_stale_ok_no_cache_computes_blocking
  - test_stale_ok_false_blocks_on_stale

TestRefreshing:
  - test_mark_refreshing
  - test_clear_refreshing
  - test_meta_shows_refreshing_true
  - test_meta_shows_refreshing_false
  - test_diag_includes_refreshing
  - test_diag_includes_subscription_count
```

### Phase 6A Checklist

```
[x] Add _Subscription dataclass and subscription state to __init__
[x] Implement subscribe() and unsubscribe()
[x] Implement _notify_subscribers()
[x] Wire _notify_subscribers into put() and batch exit
[x] Add on_stale hook to __init__
[x] Add _refreshing set with mark/clear methods
[x] Add stale_ok parameter to get()
[x] Update _make_result for stale/refreshing metadata
[x] Update diag() with subscriptions and refreshing
[x] Write subscribe tests — 12 tests (test_mediator_subscribe.py)
[x] Write stale_ok tests — 18 tests (test_mediator_stale.py)
[x] Update README with Phase 6A docs
[x] Verify all 201 tests pass
```

---

## Phase 6B — refresh() + bust() + dispatch()

> **Goal:** Bulk refresh, temporal invalidation, and async dispatch.
> Completes the model's operations table. Executor-injected parallelism.
>
> **Design principle:** Same as 6A — mediator stays pure, executor injected.

### Phase 6B Checklist

```
[x] Add executor param to __init__
[x] Implement refresh(*paths)
[x] Implement refresh_branch(prefix)
[x] Implement refresh_stale(prefix)
[x] Implement bust(max_age, prefix)
[x] Implement dispatch(*paths) + _dispatch_worker()
[x] Update diag() with has_executor
[x] Write refresh tests — 22 tests (test_mediator_refresh.py)
[x] Write dispatch tests — 9 tests (test_mediator_dispatch.py)
[x] Update README with Phase 6B docs
[x] Verify all 232 tests pass
```

---

## Phase 7 — Mediator Debug Dashboard (Full Option C)

> **Goal:** Web UI debug view showing the full mediator tree,
> node detail, dependency graph, and live event stream.
>
> **Location:** New sub-mode "🌳 Mediator" in the existing Debugging tab.
>
> **Sub-phases:** 7A (API) → 7B (HTML) → 7C (Tree+Detail JS)
> → 7D (Dependency Graph) → 7E (Live Event Stream).
> Each sub-phase is independently shippable.

---

### 7A — API Routes

**Files:**

```
src/ui/web/routes/mediator/__init__.py   ← Blueprint: mediator_bp
src/ui/web/server.py                     ← register_blueprint
```

**Routes:**

```
GET  /api/mediator/diag               → summary diag
GET  /api/mediator/diag/<path:path>   → detail diag for one node
POST /api/mediator/refresh            → force recompute paths
POST /api/mediator/refresh-branch     → refresh all under prefix
POST /api/mediator/refresh-stale      → refresh only stale nodes
POST /api/mediator/bust               → temporal invalidation
POST /api/mediator/dispatch           → async background recompute
```

**Route specifications:**

```python
# GET /api/mediator/diag
# Returns: mediator.diag() → full summary JSON
# Response shape:
# {
#   "tree": {"total_nodes": 40, "registered": 33, ...},
#   "seq": 47,
#   "cached": 28,
#   "stale": 3,
#   "batch_active": false,
#   "subscriptions": 2,
#   "refreshing": ["posture.toolchain"],
#   "has_executor": true,
#   "entries": {
#     "posture.platform": {
#       "path": "posture.platform",
#       "registered": true,
#       "has_resolver": true,
#       "ttl": 120,
#       "persist": true,
#       "depends_on": ["detect.os.platform"],
#       "dependents": ["posture.full"],
#       "is_branch": false,
#       "children": [],
#       "last_change_seq": 38,
#       "refreshing": false,
#       "cached": true,
#       "age_s": 5.2,
#       "source": "computed",
#       "seq": 42,
#       "elapsed_s": 0.123,
#       "stale": false,
#       "ttl_remaining_s": 114.8
#     },
#     ...
#   }
# }

# GET /api/mediator/diag/<path:path>
# Returns: mediator.diag(path) → detail for one node
# Query params: none
# 404 if path not found in tree

# POST /api/mediator/refresh
# Body: {"paths": ["posture.toolchain", "posture.platform"]}
# Returns: mediator.refresh(*paths) result
# {
#   "refreshed": {"posture.toolchain": {...meta...}},
#   "errors": {},
#   "elapsed_s": 0.482
# }

# POST /api/mediator/refresh-branch
# Body: {"prefix": "posture"}
# Returns: mediator.refresh_branch(prefix) result
# Same shape as refresh

# POST /api/mediator/refresh-stale
# Body: {"prefix": ""} (optional)
# Returns: mediator.refresh_stale(prefix) result

# POST /api/mediator/bust
# Body: {"max_age": 300, "prefix": "devops"}
# Returns: mediator.bust(max_age, prefix) result
# {"busted": ["devops.git", ...], "count": 3}

# POST /api/mediator/dispatch
# Body: {"paths": ["posture.toolchain"]}
# Returns: mediator.dispatch(*paths) result
# {"task_id": "task-1", "paths": [...], "status": "dispatched"}
```

**Blueprint pattern (follows existing project pattern):**

```python
# src/ui/web/routes/mediator/__init__.py
from flask import Blueprint, jsonify, request
from src.core.services.mediator import get_mediator

mediator_bp = Blueprint("mediator", __name__)

@mediator_bp.route("/mediator/diag")
def mediator_diag():
    m = get_mediator()
    if m is None:
        return jsonify({"error": "mediator not initialized"}), 503
    return jsonify(m.diag())

@mediator_bp.route("/mediator/diag/<path:path>")
def mediator_diag_path(path):
    m = get_mediator()
    if m is None:
        return jsonify({"error": "mediator not initialized"}), 503
    result = m.diag(path)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)

@mediator_bp.route("/mediator/refresh", methods=["POST"])
def mediator_refresh():
    m = get_mediator()
    if m is None:
        return jsonify({"error": "mediator not initialized"}), 503
    body = request.get_json(silent=True) or {}
    paths = body.get("paths", [])
    return jsonify(m.refresh(*paths))

@mediator_bp.route("/mediator/refresh-branch", methods=["POST"])
def mediator_refresh_branch():
    m = get_mediator()
    if m is None:
        return jsonify({"error": "mediator not initialized"}), 503
    body = request.get_json(silent=True) or {}
    prefix = body.get("prefix", "")
    return jsonify(m.refresh_branch(prefix))

@mediator_bp.route("/mediator/refresh-stale", methods=["POST"])
def mediator_refresh_stale():
    m = get_mediator()
    if m is None:
        return jsonify({"error": "mediator not initialized"}), 503
    body = request.get_json(silent=True) or {}
    prefix = body.get("prefix", "")
    return jsonify(m.refresh_stale(prefix))

@mediator_bp.route("/mediator/bust", methods=["POST"])
def mediator_bust():
    m = get_mediator()
    if m is None:
        return jsonify({"error": "mediator not initialized"}), 503
    body = request.get_json(silent=True) or {}
    max_age = body.get("max_age", 300)
    prefix = body.get("prefix", "")
    return jsonify(m.bust(max_age, prefix))

@mediator_bp.route("/mediator/dispatch", methods=["POST"])
def mediator_dispatch():
    m = get_mediator()
    if m is None:
        return jsonify({"error": "mediator not initialized"}), 503
    body = request.get_json(silent=True) or {}
    paths = body.get("paths", [])
    return jsonify(m.dispatch(*paths))
```

**Registration in server.py:**

```python
from src.ui.web.routes.mediator import mediator_bp
app.register_blueprint(mediator_bp, url_prefix="/api")
```

**Prerequisite check:** `get_mediator()` must exist in
`src/core/services/mediator/__init__.py`. Currently the module has
`_instance` and `get()` — need to verify exact accessor name and add
`get_mediator()` alias if not present.

### 7A Checklist

```
[x] Verify get_mediator() accessor exists in mediator/__init__.py
[x] Create src/ui/web/routes/mediator/__init__.py with all 7 routes
[x] Register mediator_bp in server.py
[x] Test all routes with existing test suite (232 still pass)
```

---

### 7B — HTML Partial (Mediator mode in Debugging tab)

**Files:**

```
src/ui/web/templates/partials/_tab_debugging.html  ← add mode button + panel
```

**Changes to _tab_debugging.html:**

1. Add `🌳 Mediator` button to the `.debug-modes` button bar (line 8-15)
2. Add `#debug-mediator` panel div after the traces panel

**New button (in debug-modes bar):**

```html
<button class="content-mode" onclick="debugSwitchMode('mediator')">🌳 Mediator</button>
```

**New panel structure:**

```html
<!-- Mediator Debug Dashboard -->
<div class="card full-width" id="debug-mediator" style="display:none">
    <!-- Summary bar -->
    <div id="mediator-summary" style="...">
        <!-- Rendered by JS: seq, nodes, cached, stale, etc. -->
    </div>

    <!-- Action bar -->
    <div id="mediator-actions" style="...">
        <button class="btn btn-sm btn-ghost" onclick="_mediatorRefreshStale()"
            title="Recompute all stale nodes">🔄 Refresh Stale</button>
        <button class="btn btn-sm btn-ghost" onclick="_mediatorBust(300)"
            title="Invalidate entries >5min old">💥 Bust >5min</button>
        <button class="btn btn-sm btn-ghost debug-view-toggle active"
            data-panel="mediator" data-mode="preview"
            onclick="debugToggleView('mediator','preview')">📊 Preview</button>
        <button class="btn btn-sm btn-ghost debug-view-toggle"
            data-panel="mediator" data-mode="source"
            onclick="debugToggleView('mediator','source')">{ } Source</button>
    </div>

    <!-- Preview: Two-column layout -->
    <div id="debug-mediator-preview" style="display:flex;gap:16px;min-height:400px">
        <!-- Left: Tree Explorer -->
        <div id="mediator-tree" style="flex:1;min-width:280px;max-width:400px;
            overflow-y:auto;max-height:600px;border-right:1px solid var(--border-subtle);
            padding-right:12px">
            <!-- Rendered by JS -->
        </div>

        <!-- Right: Node Detail -->
        <div id="mediator-detail" style="flex:2;overflow-y:auto;max-height:600px">
            <div style="color:var(--text-muted);font-size:0.78rem;padding:20px">
                ← Click a node in the tree to inspect
            </div>
        </div>
    </div>

    <!-- Source view (raw JSON via Monaco) -->
    <div id="debug-mediator-editor" style="display:none;height:500px;
        border-radius:var(--radius-md);overflow:hidden;
        border:1px solid var(--border)"></div>

    <!-- Dependency graph (Phase 7D) -->
    <div id="mediator-graph" style="margin-top:16px">
        <!-- Rendered by JS -->
    </div>

    <!-- Live events (Phase 7E) -->
    <div id="mediator-events" style="margin-top:16px">
        <!-- Rendered by JS -->
    </div>
</div>
```

**JS wiring changes in `_debugging.html`:**

1. Add `'mediator'` to the `validModes` arrays in `debugSwitchMode()` and
   `loadDebugTab()` (currently: `['audit','state','health','config','commands','traces']`)
2. Add `modeLabels.mediator = '🌳 Mediator'`
3. Add `if (mode === 'mediator') loadMediatorDiag();` in the mode-switch handler

### 7B Checklist

```
[x] Add 🌳 Mediator button to debug-modes bar
[x] Add #debug-mediator panel with two-column layout
[x] Wire mediator into debugSwitchMode() and loadDebugTab()
[x] Verify all other debug modes still work
```

---

### 7C — Tree Explorer + Node Detail (JS)

**Files:**

```
src/ui/web/templates/scripts/mediator/_mediator.html  ← new JS module
src/ui/web/templates/dashboard.html                    ← include it
```

**Include order in dashboard.html:**

```html
{% include 'scripts/mediator/_mediator.html' %}
```

Insert BEFORE `{% include 'scripts/_debugging.html' %}` (line 78) so that
the mediator JS functions are available when `_debugging.html` calls
`loadMediatorDiag()`.

**JS module structure (`scripts/mediator/_mediator.html`):**

```
No <script> tag (raw JS, included in the global <script> block).

Global variables:
  let _mediatorDiagData = null;    // Last diag() response
  let _mediatorSelectedPath = null; // Currently selected node

Functions:

  async function loadMediatorDiag()
    - Calls GET /api/mediator/diag
    - Stores response in _mediatorDiagData
    - Calls _mediatorRenderSummary()
    - Calls _mediatorRenderTree()
    - Stores in _debugData.mediator for Source view

  function _mediatorRenderSummary()
    - Renders the summary bar:
      seq: 47 │ 33 nodes │ 28 cached │ 3 stale │ 2 refreshing │ 2 subs │ executor: ✓
    - Uses badges with color coding:
      - stale count > 0 → amber badge
      - refreshing count > 0 → blue pulsing badge
      - has_executor → green check / gray cross

  function _mediatorRenderTree()
    - Groups entries by first path segment (posture, detect, devops)
    - Renders collapsible branch headers with node count
    - Each node row shows: icon + name + age + status badge
    - Status badges:
      ● cached + fresh → green ✓
      ● cached + stale → amber ⚠
      ○ not cached → gray ∅
      🔄 refreshing → blue spinner
      ∞ ttl=0 → gray ∞ (always recompute)
    - Each row has onclick="_mediatorSelectNode('path')"
    - Branch headers have onclick to toggle collapse
    - Age column auto-updates every 5s via _mediatorAgeTimer

  function _mediatorSelectNode(path)
    - Sets _mediatorSelectedPath = path
    - Highlights the selected row in the tree
    - Calls GET /api/mediator/diag/<path> for full detail
    - Calls _mediatorRenderDetail(data)

  function _mediatorRenderDetail(data)
    - Renders the right column with full node information:
      Status      ⚠ STALE
      Source      computed
      Cached      ✓ yes
      Age         12.3s
      TTL         10.0s
      Remaining   -2.3s (expired)
      Seq         #42
      Last Δ      seq #38
      Compute     0.482s
      Persist     ✓ file-backed
      Refreshing  ✗
    - Dependencies section:
      "Depends on:" → clickable links to other nodes
      "Depended on by:" → clickable links
      Clicking a dependency calls _mediatorSelectNode(depPath)
    - Cached data section:
      JSON viewer showing the cached data (collapsible, max-height)
    - Action buttons:
      [🔄 Refresh] → calls _mediatorRefreshPath(path)
      [💥 Bust] → calls _mediatorBustPath(path)

  async function _mediatorRefreshPath(path)
    - POST /api/mediator/refresh with {"paths": [path]}
    - Shows toast with result
    - Reloads diag

  async function _mediatorRefreshStale()
    - POST /api/mediator/refresh-stale
    - Shows toast with result
    - Reloads diag

  async function _mediatorBust(maxAge)
    - POST /api/mediator/bust with {"max_age": maxAge}
    - Shows toast with count
    - Reloads diag

  async function _mediatorBustPath(path)
    - POST /api/mediator/bust with {"max_age": 0, "prefix": path}
    - Shows toast
    - Reloads diag + detail

  let _mediatorAgeTimer = null;

  function _mediatorStartAgeTimer()
    - setInterval every 5000ms
    - For each node row in the tree, recalculates age from
      stored computed_at timestamp
    - Updates the age text in-place (no full re-render)

  function _mediatorStopAgeTimer()
    - clearInterval(_mediatorAgeTimer)
    - Called when switching away from mediator mode
```

**CSS (inline styles, following existing pattern):**

No separate CSS file needed — the existing debug tab uses inline styles
throughout. The mediator panel follows the same pattern:
- `var(--bg-secondary)` for card backgrounds
- `var(--border-subtle)` for borders
- `var(--text-muted)` for labels
- `var(--accent)` for clickable elements
- `var(--success)` / `var(--warning)` / `var(--danger)` for status

### 7C Checklist

```
[x] Create scripts/mediator/_mediator.html with all functions
[x] Include in dashboard.html before _debugging.html
[x] Verify loadMediatorDiag() renders tree and summary
[x] Verify node selection populates detail panel
[x] Verify refresh/bust actions work and reload
[x] Verify age timer updates every 5s
[x] Verify collapsible branches work
[x] Verify dependency links navigate between nodes
```

---

### 7D — Dependency Graph

**Files:**

```
src/ui/web/templates/scripts/mediator/_mediator.html  ← add graph functions
```

**Added to the same JS module (appended):**

```
Functions:

  function _mediatorRenderGraph()
    - Reads _mediatorDiagData.entries
    - Builds adjacency list from depends_on/dependents
    - Groups by branch prefix
    - Renders a box-drawing graph using HTML divs and CSS arrows
    - Each node is a small pill/badge, color-coded by status
    - Nodes are clickable → _mediatorSelectNode(path)
    - Branch sections are separated by horizontal rules

  Graph rendering approach:
    - NOT SVG or canvas (too complex for this use case)
    - NOT ASCII (too limited in HTML)
    - Use CSS flexbox rows with connecting lines
    - Each dependency chain is a horizontal row:
      [source1] ─┐
      [source2] ─┤──▶ [target] ──▶ [next]
      [source3] ─┘
    - Connecting lines use CSS borders (left/top/bottom borders on a
      narrow div between columns)

  Layout structure:
    <div class="mediator-graph-container">
      <!-- Branch header -->
      <div class="mediator-graph-branch">posture branch</div>
      <!-- Row of connected nodes -->
      <div class="mediator-graph-row">
        <div class="mediator-graph-sources">
          <span class="mediator-node-pill fresh">detect.tools.go</span>
          <span class="mediator-node-pill fresh">detect.tools.docker</span>
          ...
        </div>
        <div class="mediator-graph-arrow">──▶</div>
        <span class="mediator-node-pill stale">posture.toolchain</span>
        <div class="mediator-graph-arrow">──▶</div>
        <span class="mediator-node-pill fresh">posture.full</span>
      </div>
    </div>

  Node pill colors (inline styles):
    fresh  → background: rgba(52,211,153,0.1); border-color: #34d399
    stale  → background: rgba(251,191,36,0.1); border-color: #fbbf24
    cold   → background: rgba(148,163,184,0.1); border-color: #94a3b8
    active → background: rgba(99,102,241,0.1); border-color: #6366f1

  Branch filter dropdown:
    <select id="mediator-graph-filter">
      <option value="">All branches</option>
      <option value="posture">posture</option>
      <option value="detect">detect</option>
      <option value="devops">devops</option>
    </select>
    - Filters which branch sections are visible
```

### 7D Checklist

```
[x] Implement _mediatorRenderGraph()
[x] Graph reads from _mediatorDiagData (no extra API call)
[x] Nodes are clickable → select in tree
[x] Branch filter dropdown works
[x] Empty branches are hidden
[x] Graph handles nodes with 0 dependencies gracefully
```

---

### 7E — Live Event Stream

**Files:**

```
src/ui/web/templates/scripts/_event_stream.html       ← add mediator event types
src/ui/web/templates/scripts/mediator/_mediator.html  ← add event rendering
```

**SSE integration:**

The mediator already publishes to EventBus via `_publish_change()`:
- `mediator:write` — when data is written via put(data=...)
- `mediator:invalidated` — when a path is invalidated

These events are already flowing through the SSE endpoint
(`/api/events`) because the events route streams ALL EventBus events.
The frontend just doesn't listen for them yet.

**Changes to `_event_stream.html`:**

1. Add `'mediator:write'` and `'mediator:invalidated'` to the
   `_eventTypes` array (line 80-93)
2. Add handler methods:

```javascript
case 'mediator:write':    this._onMediatorWrite(payload);    break;
case 'mediator:invalidated': this._onMediatorInvalidated(payload); break;
```

3. Handler implementations:

```javascript
_onMediatorWrite(payload) {
    const data = payload.data || {};
    console.debug('[SSE] mediator:write %s (seq %d, %d paths)',
        data.trigger, data.mediator_seq, (data.writes || []).length);

    // Dispatch DOM event for mediator panel
    document.dispatchEvent(new CustomEvent('mediator:event', {
        detail: {
            type: 'write',
            trigger: data.trigger,
            seq: data.mediator_seq,
            paths: data.writes || [],
            ts: Date.now(),
        }
    }));
},

_onMediatorInvalidated(payload) {
    const data = payload.data || {};
    console.debug('[SSE] mediator:invalidated %s (seq %d, %d paths)',
        data.trigger, data.mediator_seq, (data.invalidated || []).length);

    document.dispatchEvent(new CustomEvent('mediator:event', {
        detail: {
            type: 'invalidated',
            trigger: data.trigger,
            seq: data.mediator_seq,
            paths: data.invalidated || [],
            ts: Date.now(),
        }
    }));
},
```

**Live event panel (in mediator/_mediator.html):**

```
Variables:
  let _mediatorEvents = [];          // Rolling buffer (max 100)
  let _mediatorEventsPaused = false; // Pause auto-scroll
  let _mediatorEventsListener = null;

Functions:

  function _mediatorRenderEventStream()
    - Renders the #mediator-events panel:
      Header: ⚡ Live Events [🟢 Connected] [Clear] [Pause]
      Body: Rolling log of events, newest at top

  function _mediatorStartListening()
    - Registers DOM event listener for 'mediator:event'
    - On each event:
      - Pushes to _mediatorEvents (cap at 100, drop oldest)
      - Calls _mediatorAppendEvent(event) for incremental render
      - If not paused, auto-scrolls to show newest
    - Also listens for user-triggered actions (refresh, bust, dispatch)
      from the action buttons — these are logged as local events too

  function _mediatorStopListening()
    - Removes DOM event listener
    - Called when switching away from mediator mode

  function _mediatorAppendEvent(event)
    - Prepends a new row to the event list:
      19:42:01  ✏️ WRITE    posture.toolchain     seq #47    0.48s
    - Row format:
      [timestamp]  [icon]  [type]  [path(s)]  [seq]  [extra]
    - Type icons:
      write → ✏️
      invalidated → 💥
      refresh → 🔄 (from action buttons)
      bust → 💥 (from action buttons)
      dispatch → 📡 (from action buttons)
    - Each row is clickable → _mediatorSelectNode(firstPath)
    - Rows fade in with a subtle CSS animation

  function _mediatorClearEvents()
    - Empties _mediatorEvents
    - Clears the event list DOM

  function _mediatorTogglePause()
    - Toggles _mediatorEventsPaused
    - Updates Pause button text: "Pause" ↔ "Resume"
```

**Integration with mode switching:**

When debug mode switches TO mediator:
- `_mediatorStartListening()` is called
- `_mediatorStartAgeTimer()` is called

When debug mode switches AWAY from mediator:
- `_mediatorStopListening()` is called
- `_mediatorStopAgeTimer()` is called

This prevents the mediator panel from consuming resources when hidden.

### 7E Checklist

```
[x] Add mediator:write and mediator:invalidated to SSE _eventTypes
[x] Add SSE handlers that dispatch DOM CustomEvents
[x] Implement _mediatorRenderEventStream()
[x] Implement _mediatorStartListening() / _mediatorStopListening()
[x] Implement _mediatorAppendEvent() with incremental rendering
[x] Implement Clear / Pause controls
[x] Verify events appear when mediator operations are triggered
[x] Verify cleanup on mode switch (no memory leaks)
[x] Verify rolling buffer caps at 100 events
```

---

### Phase 7 Complete Checklist

```
7A — API Routes
[x] Verify get_mediator() accessor in mediator/__init__.py
[x] Create routes/mediator/__init__.py (7 routes)
[x] Register mediator_bp in server.py
[x] Verify 232 existing tests still pass

7B — HTML Partial
[x] Add 🌳 Mediator button to debug-modes bar
[x] Add #debug-mediator panel with two-column layout
[x] Wire into debugSwitchMode() and loadDebugTab()
[x] Add 'mediator' to validModes arrays

7C — Tree Explorer + Node Detail
[x] Create scripts/mediator/_mediator.html
[x] Include in dashboard.html before _debugging.html
[x] Implement loadMediatorDiag() → summary + tree render
[x] Implement _mediatorSelectNode() → detail render
[x] Implement action buttons (refresh, bust)
[x] Implement age timer (5s updates)
[x] Implement collapsible branches
[x] Implement dependency navigation

7D — Dependency Graph
[x] Implement _mediatorRenderGraph()
[x] Node pills color-coded by status
[x] Clickable nodes → tree selection
[x] Branch filter dropdown
[x] Handle empty/disconnected nodes

7E — Live Event Stream
[x] Add mediator event types to SSE _eventTypes
[x] Add SSE → DOM CustomEvent handlers
[x] Implement event stream panel
[x] Implement start/stop listening
[x] Implement incremental append with animation
[x] Implement Clear / Pause
[x] Verify cleanup on mode switch
```

---

### Implementation Order

```
7A  →  Backend routes. Testable with curl.
        No frontend changes.
        Zero risk to existing functionality.

7B  →  HTML skeleton. Adds the panel but no data.
        Only touches _tab_debugging.html.
        Visible immediately but shows "Loading..."

7C  →  Core JS. Makes the panel functional.
        Tree, detail, actions all work.
        This is the "MVP" — after 7C, the dashboard is usable.

7D  →  Enhancement. Dependency graph is visual polish.
        Reads from already-loaded diag data.
        No API calls.

7E  →  Enhancement. Live events are real-time polish.
        Touches _event_stream.html (add 2 event types).
        Rest is contained in the mediator JS module.
```

Each chunk is shippable independently. After 7A+7B+7C, the dashboard
is fully functional. 7D and 7E are additive polish.

---

## Future Phases

No further mediator phases planned. Phase 7 completes the model's
full vision (§10, Layer 6: Diagnostic View).

