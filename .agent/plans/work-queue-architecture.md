# Work Queue Milestone — Architecture & Design Document

**Date**: 2026-03-13
**Status**: Architecture design
**Companion**: `work-queue-milestone.md` (problem statement)

---

## 1. The Core Pattern: Priority Work Queue with Weighted Admission

### What it solves

The current `ThreadPoolExecutor(max_workers=4)` is a flat FIFO pool.
All tasks are equal. There is no priority, no sizing, no awareness
of what else is running. The queue replacement must enforce:

- Priority ordering (web requests always first)
- Size-based admission (heavy tasks consume more capacity)
- Backpressure (web requests throttle background work)

### Design Pattern: PriorityQueue + WeightedSemaphore

Two standard concurrency primitives composed together:

**PriorityQueue** (from `queue.PriorityQueue`):
- Tasks are `(priority, sequence, work_item)` tuples
- Lower priority number = higher urgency
- Sequence number breaks ties (FIFO within same priority)
- Web requests are priority 0. Background cold-fill is priority 3.
  Heavy idle work is priority 4.

**WeightedSemaphore** (custom, wraps `threading.Semaphore`):
- Total capacity = N units (e.g., 6)
- Before a worker executes a task, it acquires `task.size` units
- After completion, it releases those units
- A size-3 task blocks until 3 units are free
- A size-1 task only needs 1 unit

**Composed**: Worker threads pull from the PriorityQueue (highest
priority first), then acquire WeightedSemaphore capacity before
executing. If capacity is insufficient, the worker blocks — but
the PriorityQueue ensures that when capacity frees up, the
highest-priority waiting task runs first.

```
class WorkItem:
    priority: int     # 0=CRITICAL, 1=HIGH, 2=NORMAL, 3=LOW, 4=IDLE
    size: int         # 1=light, 2=medium, 3=heavy
    path: str         # mediator node path
    resolver: Callable
    callback: Callable  # what to do with result

class WorkQueue:
    _queue: PriorityQueue[tuple[int, int, WorkItem]]
    _semaphore: WeightedSemaphore  # capacity=6
    _workers: list[Thread]         # N worker threads
    _web_request_count: AtomicInt  # tracks active web requests
    _seq: int                      # monotonic for FIFO tiebreak
```

### How it integrates

The WorkQueue **replaces** the `ThreadPoolExecutor` that is currently
created in `mediator/__init__.py` line 82. The mediator's `dispatch()`
method submits to this queue instead of `executor.submit()`.

The mediator's `get()` method — when called from a web route — submits
at CRITICAL priority. When called from `_dispatch_worker` (background),
it submits at the appropriate background priority.

The integration seam is clean:
- `mediator.__init__` creates a `WorkQueue` instead of a `ThreadPoolExecutor`
- `mediator.dispatch()` calls `work_queue.submit(item)` with priority/size
- Web routes continue using `m.get(path)` — the mediator internally
  detects "am I in a web request context?" to assign CRITICAL priority
- Index watcher continues calling `mediator.dispatch(*paths)` — the
  dispatch method assigns background priorities based on tier

### How to detect web request context

Flask provides `flask.has_request_context()` — returns True when
code is executing inside a Flask request handler. The mediator can
check this to auto-assign CRITICAL priority when `get()` is called
from a web route, without any changes to the 50+ route files.

```python
def get(self, path, *, force=False, ...):
    # If we're inside a web request, this is CRITICAL priority
    try:
        from flask import has_request_context
        if has_request_context():
            # Ensure this computation is prioritized
            self._work_queue.boost_priority(path, CRITICAL)
    except ImportError:
        pass
    # ... rest of existing get() logic
```

---

## 2. Web Request Throttling: The Yield Flag

### What it solves

When a CPU-intensive background task (symbol parsing, security regex
scan, test discovery) is running, it holds the GIL during CPU bursts.
The web server's request-handling threads compete for the same GIL.
The result: web responses slow down or freeze while background work
runs.

### Design Pattern: Cooperative Yielding via Shared Flag

A `threading.Event` that background workers check periodically:

```python
class WorkQueue:
    _yield_flag: threading.Event  # set() when web requests pending
    _web_request_count: int       # atomic counter

    def begin_web_request(self):
        """Called when a web request enters mediator.get()."""
        self._web_request_count += 1
        self._yield_flag.set()    # signal background workers

    def end_web_request(self):
        """Called when web request exits mediator.get()."""
        self._web_request_count -= 1
        if self._web_request_count == 0:
            self._yield_flag.clear()

    def should_yield(self) -> bool:
        """Background workers call this periodically."""
        return self._yield_flag.is_set()
```

Background workers insert yield checkpoints in their loops:

```python
# Inside security scan's file iteration loop:
for filepath in files:
    if work_queue.should_yield():
        time.sleep(0.01)  # release GIL, let web request run
    # ... process file
```

### How it integrates

The yield flag is a property of the WorkQueue. Background task
resolvers receive a reference to the queue (or a `yield_check`
callable) so they can check periodically.

The ops functions that are CPU-intensive need yield checkpoints
inserted in their inner loops:

- `security/scan.py` `_iter_files()` — yield between files
- `audit/parsers/__init__.py` `parse_tree()` — yield between files
- `registrations/index.py` `incremental_symbols()` — yield between files
- `testing/ops.py` test counting — yield between directories

These checkpoints are cheap (one `Event.is_set()` check ≈ 50ns)
when no web requests are active. When web requests ARE active,
the `time.sleep(0.01)` releases the GIL for 10ms, giving the web
server time to handle the request.

### How background workers receive the yield check

The resolver functions are currently simple lambdas:
```python
("devops.security", _compute_security)
```

The work queue wraps execution so the resolver runs in a context
where `should_yield()` is accessible. Two options:

**Option A**: Thread-local storage
```python
import threading
_tls = threading.local()

def current_yield_check() -> bool:
    return getattr(_tls, 'yield_check', lambda: False)()
```
The worker sets `_tls.yield_check` before calling the resolver.
Ops functions call `current_yield_check()` in their loops.

**Option B**: ContextVar (Python 3.12+)
```python
from contextvars import ContextVar
_yield_cv: ContextVar[Callable] = ContextVar('yield_check', default=lambda: False)
```
Same pattern but using contextvars instead of thread-locals.

Either approach requires NO changes to resolver signatures — the
resolver is still `() -> dict`. The yield check is ambient, accessed
via the thread-local or contextvar when needed.

---

## 3. Consolidated Tree Walker

### What it solves

17 separate tree walk sites currently do independent `os.walk`
passes over the project tree. When the index watcher dispatches a
cycle, many of these run in the same cycle. Each one repeats the
same directory reads and I/O syscalls.

### Design Pattern: Single-Producer Multi-Consumer Walk

One `os.walk` pass produces `(dirpath, dirnames, filenames)` tuples.
Multiple consumers ("checkers") each process the same tuples
during the same walk, accumulating their own results.

```python
class TreeWalkCollector:
    """Registered by an ops function to participate in a shared walk."""
    name: str
    wants_full_tree: bool           # True = all dirs, False = scoped
    scope_dirs: list[str] | None    # if scoped, which root-relative dirs
    on_dir: Callable[[str, list[str], list[str]], None]
        # Called for each (dirpath, dirnames, filenames) tuple
    result: Any                     # accumulated result after walk

class ConsolidatedWalker:
    """Runs one os.walk, feeds all registered collectors."""

    def __init__(self, project_root: Path, skip_dirs: frozenset[str]):
        self._root = project_root
        self._skip = skip_dirs

    def walk(self, collectors: list[TreeWalkCollector]) -> None:
        """Execute ONE walk, feed ALL collectors at each step."""

        # Determine walk scope: if ALL collectors are scoped to
        # specific dirs, walk only those dirs. If any collector
        # wants full tree, walk full tree.
        full_tree_needed = any(c.wants_full_tree for c in collectors)

        if full_tree_needed:
            walk_roots = [self._root]
        else:
            # Union of all scoped dirs
            all_dirs = set()
            for c in collectors:
                if c.scope_dirs:
                    for d in c.scope_dirs:
                        all_dirs.add(self._root / d)
            walk_roots = [d for d in all_dirs if d.is_dir()]

        for walk_root in walk_roots:
            for dirpath, dirnames, filenames in os.walk(walk_root):
                # Prune skipped dirs (shared logic)
                dirnames[:] = [
                    d for d in dirnames
                    if d not in self._skip and not d.startswith(".")
                ]

                rel_dir = os.path.relpath(dirpath, self._root)

                # Feed each collector
                for collector in collectors:
                    if collector.wants_full_tree or self._in_scope(
                        rel_dir, collector.scope_dirs
                    ):
                        collector.on_dir(rel_dir, dirnames, filenames)
```

### How tree-browsing tasks become collectors

Each ops function that currently does its own `os.walk` is refactored
to expose a `TreeWalkCollector` instead. Example — `k8s_status()`:

**Before** (3 separate walks):
```python
yaml_files = _collect_yaml_files(project_root, manifest_dirs)   # walk 1
helm_charts = _detect_helm_charts(project_root)                  # walk 2
kustomize = _detect_kustomize(project_root)                      # walk 3 (file checks)
```

**After** (1 collector participating in shared walk):
```python
class K8sCollector(TreeWalkCollector):
    name = "k8s"
    wants_full_tree = False
    scope_dirs = ["k8s", "kubernetes", "deploy", "manifests", "charts", "helm"]

    def __init__(self):
        self.yaml_files = []
        self.chart_files = []
        self.kustomize_files = []

    def on_dir(self, rel_dir, dirnames, filenames):
        for fname in filenames:
            if fname.endswith((".yaml", ".yml")):
                self.yaml_files.append(os.path.join(rel_dir, fname))
            if fname == "Chart.yaml":
                self.chart_files.append(rel_dir)
            if fname == "kustomization.yaml":
                self.kustomize_files.append(rel_dir)
```

Then `k8s_status()` receives the collector's pre-populated data
instead of walking the tree itself.

### How it integrates with the work queue

When the work queue detects that multiple pending tasks need tree
walks, it batches them:

1. Work queue examines pending items tagged `needs_walk=True`
2. Creates a `ConsolidatedWalker` with all their collectors
3. Runs the single walk
4. Passes each collector's accumulated results back to its task
5. Each task continues with its task-specific logic (parsing YAML,
   checking chart structure, etc.)

This batching happens at the queue level, not inside individual
ops functions. Ops functions don't know or care about other ops
functions. They just declare "I need a walk" and provide a collector.

### Interaction with `scan_project()` (index.scan)

`scan_project()` in `registrations/index.py` already does a full
project tree walk producing `{rel_path: FileEntry(mtime, size, ext)}`.
This scan data contains EVERY file's path, extension, size, and mtime.

Many ops functions only need to know "which files exist with which
extensions in which directories." This information is ALREADY in
the scan data. These ops functions could query the scan data instead
of walking the tree at all:

- `docs_ops._collect_md_files()` → filter scan for `ext == "md"`
- `docker/detect.py` dockerfile scan → filter scan for filenames
  matching `Dockerfile*` or `docker-compose*`
- `dns_cdn_ops.py` zone scan → filter scan for extensions
- `terraform/ops.py` tf scan → filter scan for `ext == "tf"`

This eliminates their tree walks entirely. They become scan-data
consumers, not tree walkers.

The remaining tree walks that need MORE than what scan provides
(e.g., security scan needs file contents, symbol parser needs to
read and parse files) still use the consolidated walker for their
I/O, but they do additional per-file processing beyond what the
scan supplies.

---

## 4. Load Order: Tiered Dispatch

### What it solves

Heavy tasks should not load first. Tasks that were on-demand based
on user navigation should not run at cold start with the same
priority as dashboard-visible tasks.

### Design Pattern: Tiered Dispatch with Dependency Gates

The index watcher's `_poll_loop` already has `_FAST_DEVOPS` and
`_HEAVY_DEVOPS` sets. The problem is that both are submitted to
the executor simultaneously. The fix: dispatch in tiers, where
each tier only dispatches after the previous tier completes.

```python
# In _poll_loop, replace flat dispatch with tiered dispatch:

TIERS = [
    # Tier 0: already runs synchronously (fast index nodes)

    # Tier 1: lightweight devops — dashboard-visible, < 1s each
    {
        "paths": ["devops.git", "devops.ci", "devops.docs",
                  "devops.dns", "devops.quality", "devops.packages"],
        "priority": Priority.LOW,
        "size": 1,
        "gate": None,  # runs immediately after index
    },

    # Tier 2: medium devops — subprocess calls, 1–2s each
    {
        "paths": ["devops.docker", "devops.k8s", "devops.github",
                  "devops.terraform", "devops.env"],
        "priority": Priority.LOW,
        "size": 2,
        "gate": "tier1_complete",  # waits for tier 1
    },

    # Tier 3: heavy devops — full scans, 3–13s each
    # These were on-demand based on user navigation.
    {
        "paths": ["devops.security", "devops.testing"],
        "priority": Priority.IDLE,
        "size": 3,
        "gate": "tier2_complete",  # waits for tiers 1+2
    },

    # Tier 4: aggregates — depend on card data
    {
        "paths": ["devops.status", "posture.*"],
        "priority": Priority.IDLE,
        "size": 1,
        "gate": "tier3_complete",
    },

    # Tier 5: feature index — AST/peek, LAST, conditional
    {
        "paths": ["index.symbols", "index.peek", "index.stats"],
        "priority": Priority.IDLE,
        "size": 3,
        "gate": "tier4_complete",
        "condition": "is_peek_index_enabled()",
    },
]
```

The gate mechanism: each tier submits its tasks to the work queue.
The work queue notifies when all tasks from a tier are complete.
The next tier then submits its tasks.

This is NOT a polling loop. It's a callback chain:
- Tier 1 submits → queue runs tier 1 → all complete → callback fires
- Callback submits tier 2 → queue runs tier 2 → all complete → callback
- etc.

The work queue naturally handles this because each tier's items
have the correct priority. Even if tier 3 is running and a web
request arrives, the web request's CRITICAL priority preempts.

---

## 5. FS Trigger Batching: Blast Coalescing

### What it solves

When a filesystem change triggers invalidation, multiple tasks
get invalidated simultaneously (a "blast"). Today each blasted
task runs independently, potentially walking the tree N times.

### Design Pattern: Debounce + Batch Coalescing

```
FS event → debounce window (50ms) → collect all events → invalidate
→ identify all tasks that need re-execution → batch by walk needs
→ consolidated walk for walk-needing tasks → dispatch remaining tasks
```

The debounce is already implicit in the poll interval
(`POLL_INTERVAL_S`). The new behavior:

1. After mtime change detected, the watcher invalidates `index.scan`
   (existing behavior)
2. The cascade invalidates downstream nodes (existing behavior)
3. Instead of dispatching each invalidated node independently,
   the watcher collects ALL invalidated nodes
4. Nodes that need tree walks are grouped together
5. A single consolidated walk executes with all their collectors
6. Walk results are distributed to each collector
7. Each node's resolver runs with pre-populated walk data
8. Nodes that DON'T need tree walks dispatch normally

```python
# In _poll_loop:

# After invalidation, identify which nodes need walks
walk_nodes = [p for p in invalidated if self._needs_walk(p)]
no_walk_nodes = [p for p in invalidated if p not in walk_nodes]

# Consolidated walk for walk-needing nodes
if walk_nodes:
    collectors = [self._get_collector(p) for p in walk_nodes]
    walker = ConsolidatedWalker(project_root, _SKIP_DIRS)
    walker.walk(collectors)
    # Each collector now has its data. Submit resolvers.
    for path, collector in zip(walk_nodes, collectors):
        work_queue.submit(WorkItem(
            path=path,
            priority=Priority.NORMAL,
            size=_get_size(path),
            resolver=lambda c=collector: _resolve_with_walk_data(path, c),
        ))

# Direct dispatch for non-walk nodes
for path in no_walk_nodes:
    work_queue.submit(WorkItem(
        path=path,
        priority=Priority.NORMAL,
        size=_get_size(path),
    ))
```

---

## 6. Scan Data as Shared Foundation

### What it solves

`scan_project()` already walks the entire tree and produces
`{rel_path: FileEntry(mtime, size, ext)}`. Many ops functions
only need file existence and extension data — they don't need
to read file contents. These functions currently walk the tree
again to discover the same files.

### Design Pattern: Materialized View

The scan data is a materialized view of the filesystem. Ops
functions query this view instead of re-scanning the filesystem.

```python
class ScanView:
    """Query interface over scan_project() output."""

    def __init__(self, scan: dict[str, FileEntry]):
        self._scan = scan
        # Pre-build extension index
        self._by_ext: dict[str, list[str]] = {}
        for path, entry in scan.items():
            self._by_ext.setdefault(entry.ext, []).append(path)
        # Pre-build directory index
        self._by_dir: dict[str, list[str]] = {}
        for path in scan:
            parts = path.split(os.sep)
            for i in range(len(parts) - 1):
                dir_path = os.sep.join(parts[:i+1])
                self._by_dir.setdefault(dir_path, []).append(path)

    def files_with_ext(self, ext: str) -> list[str]:
        """All files with given extension."""
        return self._by_ext.get(ext, [])

    def files_in_dir(self, dir_path: str, recursive=True) -> list[str]:
        """Files in a directory."""
        if recursive:
            return [p for p in self._scan if p.startswith(dir_path + os.sep)]
        return self._by_dir.get(dir_path, [])

    def files_named(self, name: str) -> list[str]:
        """All files with exact filename."""
        return [p for p in self._scan if os.path.basename(p) == name]

    def dir_exists(self, dir_path: str) -> bool:
        """Check if directory has any files."""
        prefix = dir_path + os.sep
        return any(p.startswith(prefix) for p in self._scan)
```

### How ops functions consume it

The `index.scan` node already computes and caches scan data. Ops
functions that just need file listings can depend on `index.scan`
and query its data:

```python
# docs_ops: instead of _collect_md_files() doing os.walk
def docs_status(project_root):
    scan_view = get_scan_view()  # from mediator cache
    md_files = scan_view.files_with_ext("md")
    # ... process md_files, no walk needed

# terraform: instead of glob("*.tf")
def terraform_status(project_root):
    scan_view = get_scan_view()
    tf_files = scan_view.files_with_ext("tf")
    # ... process tf_files, no walk needed

# docker: instead of walking for Dockerfile
def docker_status(project_root):
    scan_view = get_scan_view()
    dockerfiles = scan_view.files_named("Dockerfile")
    compose_files = [p for p in scan_view.files_named("docker-compose.yml")
                     + scan_view.files_named("docker-compose.yaml")
                     + scan_view.files_named("compose.yml")
                     + scan_view.files_named("compose.yaml")]
    # ... no walk needed
```

This eliminates tree walks entirely for functions that only need
to know WHICH files exist. The consolidated walker (pattern 3)
handles functions that need to read file contents (security scan,
symbol parser).

### How it integrates

The ScanView is derived from `index.scan` data. It is computed
once per scan cycle and cached. Ops functions access it through
the mediator dependency graph:

- `devops.docs` depends on `index.scan` → receives ScanView
- `devops.docker` depends on `index.scan` → receives ScanView
- `devops.terraform` depends on `index.scan` → receives ScanView
- etc.

This creates a natural dependency: ops functions wait for the scan
to complete before running, and they consume the scan's output
instead of re-walking.

---

## 7. How Everything Connects

### The execution flow at cold start

```
Server starts
  │
  ├─ 1. Mediator init: create WorkQueue (replaces ThreadPoolExecutor)
  │
  ├─ 2. Disk hydration: load persisted shards into cache
  │      If warm: skip to step 5 (tiers dispatch from cached data)
  │
  ├─ 3. Index watcher first cycle:
  │      ├─ Phase 1: Fast index nodes (sync, 45ms)
  │      │    scan → delta → files → dirs → paths → classify
  │      │    └─ scan produces ScanView (shared foundation)
  │      │
  │      ├─ Phase 2: Tier 1 dispatch (priority=LOW, size=1)
  │      │    git, ci, docs, dns, quality, packages
  │      │    └─ docs, dns, etc. consume ScanView — no tree walk
  │      │
  │      ├─ Phase 3: Tier 2 dispatch (priority=LOW, size=2)
  │      │    docker, k8s, github, terraform, env
  │      │    └─ docker, terraform consume ScanView
  │      │    └─ k8s uses consolidated walk for manifest dirs
  │      │    └─ github, env do subprocess/API calls (no walk)
  │      │
  │      ├─ Phase 4: Tier 3 dispatch (priority=IDLE, size=3)
  │      │    security, testing
  │      │    └─ security uses consolidated walk (needs file content)
  │      │    └─ testing uses ScanView for test file counting
  │      │
  │      ├─ Phase 5: Tier 4 dispatch (priority=IDLE, size=1)
  │      │    devops.status, posture.*
  │      │    └─ waits for card data from tiers 1–3
  │      │
  │      └─ Phase 6: Tier 5 dispatch (priority=IDLE, size=3, conditional)
  │           index.symbols, index.peek, index.stats
  │           └─ only if peek/index enabled by user
  │
  └─ 4. Web server ready, serving requests
         └─ all requests served from cache (disk hydration or tier results)
         └─ cache miss → CRITICAL priority in WorkQueue
```

### The execution flow on FS change

```
File modified on disk
  │
  ├─ Index watcher poll detects mtime change
  │
  ├─ Invalidate index.scan → cascade invalidates downstream
  │
  ├─ Recompute index.scan (sync, ~25ms)
  │    └─ ScanView updated
  │
  ├─ Smart dispatch: check if classify changed
  │    ├─ Changed: dispatch all affected nodes
  │    └─ Unchanged: dispatch only mtime-stale nodes
  │
  ├─ Blast coalescing:
  │    ├─ Collect all invalidated nodes
  │    ├─ Group walk-needing nodes → one consolidated walk
  │    ├─ Group ScanView consumers → they just re-query ScanView
  │    └─ Group subprocess nodes → they dispatch independently
  │
  └─ Submit all to WorkQueue at appropriate priority/size
       └─ If web request in flight → yield flag active
       └─ Background tasks yield at checkpoints
```

### The execution flow on web request (user refreshes)

```
User hits refresh or navigates to card
  │
  ├─ Route handler calls m.get("devops.k8s")
  │
  ├─ Mediator detects Flask request context → CRITICAL priority
  │
  ├─ Check cache via peek():
  │    ├─ Cache hit (common): return immediately, 0ms
  │    └─ Cache miss: must compute
  │
  ├─ Cache miss path:
  │    ├─ Submit to WorkQueue at CRITICAL priority
  │    ├─ WorkQueue sets yield_flag → background workers pause
  │    ├─ CRITICAL task runs immediately (reserved capacity)
  │    ├─ Result computed, cached, returned to user
  │    └─ yield_flag cleared → background workers resume
  │
  └─ User sees data
```

---

## 8. Component Inventory — What Gets Built

| Component | Location | What It Does |
|-----------|----------|--------------|
| `WorkQueue` | `mediator/work_queue.py` (new) | Priority queue + weighted semaphore + yield flag |
| `WorkItem` | `mediator/work_queue.py` (new) | Task descriptor: priority, size, path, resolver |
| `WeightedSemaphore` | `mediator/work_queue.py` (new) | Size-based admission control |
| `ConsolidatedWalker` | `mediator/tree_walker.py` (new) | Single os.walk, multiple collectors |
| `TreeWalkCollector` | `mediator/tree_walker.py` (new) | Per-task walk consumer interface |
| `ScanView` | `mediator/registrations/index.py` (evolve) | Query interface over scan data |
| Tiered dispatch | `mediator/index_watcher.py` (evolve) | Replace flat dispatch with tier gates |
| Yield checkpoints | various ops files (evolve) | `should_yield()` checks in CPU loops |
| Priority detection | `mediator/core.py` (evolve) | Flask context → CRITICAL priority |

### What gets modified (integration points)

| File | Change |
|------|--------|
| `mediator/__init__.py` | `WorkQueue` instead of `ThreadPoolExecutor` |
| `mediator/core.py` | `get()` assigns priority via request context; `dispatch()` uses WorkQueue |
| `mediator/index_watcher.py` | Tiered dispatch; blast coalescing; consolidated walk trigger |
| `mediator/registrations/index.py` | ScanView derivation from scan data |
| `k8s/detect.py` | K8sCollector for consolidated walk OR ScanView consumer |
| `docker/detect.py` | ScanView consumer for file detection |
| `docs_svc/ops.py` | ScanView consumer for md file listing |
| `dns_cdn_ops.py` | ScanView consumer for zone/cert detection |
| `terraform/ops.py` | ScanView consumer for tf file listing |
| `security/scan.py` | ConsolidatedWalker participant + yield checkpoints |
| `testing/ops.py` | ScanView consumer + yield checkpoints |
| `audit/l0_detection.py` | ScanView consumer for module file counting |
| `audit/parsers/__init__.py` | ConsolidatedWalker participant + yield checkpoints |

### What does NOT change

| File | Why |
|------|-----|
| All 50+ web route files | They call `m.get(path)` — priority is auto-detected |
| `mediator/tree.py` | Dependency graph is unchanged |
| `mediator/persistence.py` | Disk sharding is unchanged |
| `registrations/devops.py` | Node registration is unchanged |
| `registrations/detect.py` | Node registration is unchanged |
| `registrations/posture.py` | Node registration is unchanged |

---

## 9. Efficiency Summary

### Before (current state)

- 17 independent tree walks per dispatch cycle
- 4-worker flat FIFO pool — no priority, no sizing
- Web requests compete with background work for compute locks
- Heavy tasks (security 13s, symbols 30s) run alongside light tasks
- No throttling of background work when user is active
- Cold start: everything dispatched in one flat batch

### After (this milestone)

- 1 tree walk per dispatch cycle (consolidated walker + ScanView)
- Priority queue with size-based admission
- Web requests auto-elevate to CRITICAL, background workers yield
- Heavy tasks dispatch last, at IDLE priority, size 3
- Yield checkpoints release GIL for web requests
- Cold start: 5-tier graduated dispatch, light → heavy → conditional

### Expected impact

| Metric | Before | After |
|--------|--------|-------|
| Tree walks per cycle | ~17 | 1 (+ ScanView queries) |
| Time to first dashboard data | ~2s (blocked by heavy tasks) | <100ms (tier 1 runs first) |
| Web request latency during index | 100ms–13s (competes) | <50ms (cache + priority) |
| Cold start total | ~31s sequential | ~31s but graduated — user sees data in <100ms |
| CPU contention during heavy tasks | high (4 size-3 tasks) | controlled (capacity limit) |
