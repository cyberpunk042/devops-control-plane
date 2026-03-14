# Work Queue Milestone — Solution Plan

**Date**: 2026-03-13
**Companions**:
- `work-queue-milestone.md` (problem statement)
- `work-queue-architecture.md` (design patterns)

---

## Chunk 1: WorkQueue Core Infrastructure

Build the priority queue with weighted admission as a standalone,
testable module. No integration yet — just the engine.

### 1.1 WorkItem and Priority Constants

**File**: `src/core/services/mediator/work_queue.py` (new)

**Deliverable**: The `WorkItem` dataclass and `Priority` enum.

```python
class Priority(IntEnum):
    CRITICAL = 0   # web request — user is waiting
    HIGH = 1       # user-initiated refresh
    NORMAL = 2     # FS trigger — index watcher change detection
    LOW = 3        # cold start background fill (tier 1, 2)
    IDLE = 4       # heavy background tasks (tier 3, 4, 5)

class WorkItem:
    priority: int
    size: int         # 1, 2, or 3
    path: str         # mediator node path
    resolver: Callable
    callback: Callable | None
    submitted_at: float
    seq: int          # monotonic tiebreaker (FIFO within same priority)
```

`WorkItem` must be comparable for `PriorityQueue` ordering:
`(priority, seq)` tuples determine order. Lower priority number
wins. On tie, lower seq (submitted first) wins.

**Verify**: Unit-testable — create WorkItems, put in PriorityQueue,
verify correct ordering by priority then FIFO within same priority.

### 1.2 WeightedSemaphore

**File**: `src/core/services/mediator/work_queue.py`

**Deliverable**: The `WeightedSemaphore` class.

A semaphore that tracks total acquired "units" instead of a simple
count. `acquire(n)` blocks until `n` units are available.
`release(n)` returns `n` units.

```python
class WeightedSemaphore:
    def __init__(self, capacity: int):
        self._capacity = capacity
        self._used = 0
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)

    def acquire(self, weight: int, timeout: float | None = None) -> bool:
        """Block until `weight` units are available. Return True if acquired."""

    def release(self, weight: int) -> None:
        """Return `weight` units to the pool."""

    @property
    def available(self) -> int:
        """Current available capacity units."""
```

**Critical detail**: CRITICAL priority tasks must bypass the
semaphore. When a web request needs compute, it must not wait for
capacity to free up. The semaphore has a `force_acquire(weight)`
method for CRITICAL tasks that allows temporary over-capacity.

**Verify**: Unit-testable — concurrent threads acquiring/releasing
with different weights. Test that a size-3 acquire blocks when only
2 units free. Test force_acquire bypasses capacity limit.

### 1.3 Yield Flag

**File**: `src/core/services/mediator/work_queue.py`

**Deliverable**: The yield flag mechanism that background workers
check to release the GIL for web requests.

```python
class WorkQueue:
    _yield_flag: threading.Event
    _web_request_count: int  # protected by atomic increment

    def begin_web_request(self) -> None:
        """Signal all background workers to yield."""

    def end_web_request(self) -> None:
        """Clear signal when no web requests pending."""

    def should_yield(self) -> bool:
        """Background workers call this in CPU-bound loops."""
```

Also: a thread-local accessor so ops functions can check without
receiving the queue directly:

```python
import threading
_tls = threading.local()

def current_yield_check() -> bool:
    """Check if this background thread should yield for web requests.
    Returns False if not in a worker thread context."""
    fn = getattr(_tls, 'yield_check', None)
    return fn() if fn else False
```

**Verify**: Unit-testable — two threads, one sets flag, other
detects it. Test flag clears when web request count hits 0.

### 1.4 WorkQueue Main Loop

**File**: `src/core/services/mediator/work_queue.py`

**Deliverable**: The WorkQueue class that pulls from the priority
queue, acquires semaphore capacity, and runs tasks.

Worker loop logic:
1. Pull highest-priority item from PriorityQueue (blocks if empty)
2. Acquire `item.size` units from WeightedSemaphore (blocks if full,
   unless CRITICAL)
3. Set thread-local yield_check on the worker thread
4. Call `item.resolver()`
5. Call `item.callback(result)` if provided
6. Release semaphore units
7. Loop

**Configuration**:
- `num_workers`: number of worker threads (default: 4)
- `capacity`: total size units for WeightedSemaphore (default: 6)
- Both configurable at init time

**Verify**: Integration-testable — submit multiple items at
different priorities and sizes, verify execution order respects
priority and that capacity limits are enforced.

### 1.5 WorkQueue Shutdown

**Deliverable**: Graceful shutdown — no orphaned threads, no
leaked resources.

- `shutdown(wait=True)` — stop accepting new work, drain queue,
  join worker threads
- Poison pill pattern: submit sentinel items that cause workers
  to exit their loops
- Timeout guard: if workers don't complete within N seconds,
  forcibly exit

**Verify**: Test that shutdown doesn't hang. Test that in-progress
tasks complete before shutdown returns.

### Chunk 1 Summary

| Sub-chunk | File | Deliverable |
|-----------|------|-------------|
| 1.1 | `work_queue.py` | `WorkItem`, `Priority` enum |
| 1.2 | `work_queue.py` | `WeightedSemaphore` |
| 1.3 | `work_queue.py` | Yield flag + thread-local accessor |
| 1.4 | `work_queue.py` | `WorkQueue` class with worker loop |
| 1.5 | `work_queue.py` | Graceful shutdown |

**Gate**: Chunk 1 complete when WorkQueue can accept, prioritize,
and execute work items with correct ordering and capacity control.
All verifiable with standalone tests (no mediator integration needed).

---

## Chunk 2: ScanView — Materialized View Over Scan Data

Build the query interface over `index.scan` data so ops functions
can look up files by extension, name, or directory without walking
the tree.

### 2.1 ScanView Class

**File**: `src/core/services/mediator/registrations/index.py`
(add to existing file, near `scan_project`)

**Deliverable**: `ScanView` class with pre-built indexes.

```python
class ScanView:
    def __init__(self, scan: dict[str, FileEntry]):
        # Pre-build:
        # _by_ext: {"py": ["src/foo.py", ...], "md": [...], ...}
        # _by_name: {"Dockerfile": ["./Dockerfile", ...], ...}
        # _by_dir: {"src/core": ["src/core/foo.py", ...], ...}

    def files_with_ext(self, ext: str) -> list[str]:
    def files_named(self, name: str) -> list[str]:
    def files_in_dir(self, dir_path: str, recursive: bool = True) -> list[str]:
    def dir_exists(self, dir_path: str) -> bool:
    def has_file(self, rel_path: str) -> bool:
    def file_entry(self, rel_path: str) -> FileEntry | None:
```

The indexes are built ONCE in `__init__` — O(N) where N is the
number of files in the scan. After that, all queries are O(1) or
O(K) where K is the result set size.

**Verify**: Unit-testable with a mock scan dict. Verify that
`files_with_ext("md")` returns exactly the .md files, etc.

### 2.2 ScanView as Mediator Node

**File**: `src/core/services/mediator/registrations/index.py`

**Deliverable**: Register a new `index.view` node that wraps
scan data in a ScanView.

```python
tree.register(TreeRegistration(
    path="index.view",
    resolver=lambda: ScanView(mediator.get("index.scan")["data"]),
    ttl=None,
    depends_on=["index.scan"],
))
```

This node is derived from `index.scan`. Every time the scan
recomputes (FS change), `index.view` invalidates and recomputes
its indexes on next access.

The ScanView is NOT persisted to disk (it's cheap to rebuild from
scan data — O(N) with N=~5000 files takes ~5ms).

**Verify**: Start server, verify `index.view` produces a ScanView
with correct data. Modify a file, verify ScanView reflects the change.

### 2.3 ScanView Accessor Function

**File**: `src/core/services/mediator/registrations/index.py`
(or a separate utility)

**Deliverable**: A convenience function for ops functions to get
the current ScanView without importing the mediator directly.

```python
def get_scan_view() -> ScanView | None:
    """Get the current ScanView from the mediator cache.
    Returns None if the mediator isn't initialized or scan not ready."""
    try:
        from src.core.services.mediator import get_mediator
        m = get_mediator()
        result = m.peek("index.view")
        if result is not None:
            return result["data"]
    except (RuntimeError, Exception):
        pass
    return None
```

Uses `peek()` — never triggers computation. If the scan isn't
ready yet (cold start, view not yet computed), returns None and
the ops function falls back to its own walk. This ensures ops
functions work even when the mediator isn't available (CLI mode,
tests, etc.).

**Verify**: Test that it returns None before mediator init,
returns ScanView after init + scan computation.

### Chunk 2 Summary

| Sub-chunk | File | Deliverable |
|-----------|------|-------------|
| 2.1 | `registrations/index.py` | `ScanView` class |
| 2.2 | `registrations/index.py` | `index.view` node registration |
| 2.3 | `registrations/index.py` | `get_scan_view()` accessor |

**Gate**: Chunk 2 complete when ScanView is registered as a mediator
node and queryable. Does NOT change any ops functions yet.

---

## Chunk 3: Integrate WorkQueue into Mediator

Replace the flat `ThreadPoolExecutor` with the new WorkQueue.
All existing behavior preserved — just routed through the queue.

### 3.1 Mediator Init — WorkQueue Replacement

**File**: `src/core/services/mediator/__init__.py`

**Deliverable**: Replace `ThreadPoolExecutor` with `WorkQueue`.

Change line 82:
```python
# Before:
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mediator")
mediator = QueryMediator(tree, project_root, executor=_executor)

# After:
from .work_queue import WorkQueue
_work_queue = WorkQueue(num_workers=4, capacity=6)
mediator = QueryMediator(tree, project_root, work_queue=_work_queue)
```

### 3.2 Mediator Core — Work Queue Integration

**File**: `src/core/services/mediator/core.py`

**Deliverable**: `dispatch()` method uses WorkQueue instead of
executor.submit().

The `__init__` accepts `work_queue` parameter alongside (or
replacing) `executor`. The `dispatch()` method creates WorkItems
with the correct priority and size and submits them.

```python
def dispatch(self, *paths: str, priority: int = Priority.LOW,
             size: int | None = None) -> dict:
    for p in valid_paths:
        item = WorkItem(
            priority=priority,
            size=size or self._infer_size(p),
            path=p,
            resolver=lambda p=p: self.get(p, force=True),
            callback=lambda result, p=p: self.clear_refreshing(p),
        )
        self._work_queue.submit(item)
```

Size inference: the mediator reads a `size` attribute from the
TreeRegistration (new field, see 3.3) or defaults to 1.

### 3.3 TreeRegistration — Add Size Field

**File**: `src/core/services/mediator/tree.py`

**Deliverable**: Add `size: int = 1` to `TreeRegistration` and
`TreeNode`.

```python
@dataclass
class TreeRegistration:
    path: str
    resolver: Callable[..., Any] | None = None
    ttl: float | None = None
    mtime_paths: list[str] | None = None
    persist: bool = False
    depends_on: list[str] | None = None
    size: int = 1           # NEW — 1=light, 2=medium, 3=heavy
```

### 3.4 Registration Updates — Assign Sizes

**File**: `src/core/services/mediator/registrations/devops.py`
**File**: `src/core/services/mediator/registrations/detect.py`

**Deliverable**: Each node gets a `size` attribute matching the
sizes from the architecture doc.

Devops node sizes:
```python
# Size 1 (lightweight — PATH checks, file reads, < 1s)
"devops.git"       → size=1
"devops.ci"        → size=1
"devops.docs"      → size=1
"devops.dns"       → size=1
"devops.quality"   → size=1
"devops.packages"  → size=1
"devops.status"    → size=1

# Size 2 (medium — subprocess calls, API calls, 1–2s)
"devops.docker"    → size=2
"devops.k8s"       → size=2
"devops.github"    → size=2
"devops.terraform" → size=2
"devops.env"       → size=2

# Size 3 (heavy — full tree scan, CPU-bound, 3–13s)
"devops.security"  → size=3
"devops.testing"   → size=3
```

Index node sizes:
```python
"index.scan"       → size=1  (25ms, OS-level I/O)
"index.delta"      → size=1  (5ms, dict diff)
"index.files"      → size=1  (2ms, derived)
"index.dirs"       → size=1  (2ms, derived)
"index.paths"      → size=1  (1ms, derived)
"index.classify"   → size=1  (5ms, counting)
"index.view"       → size=1  (5ms, index building)
"index.symbols"    → size=3  (30s cold, CPU-bound AST parsing)
"index.peek"       → size=2  (2s cold, file reading)
"index.stats"      → size=1  (1ms, aggregation)
```

Detect nodes: same sizes as their devops counterparts (they call
the same resolvers).

### 3.5 Web Request Priority Detection

**File**: `src/core/services/mediator/core.py`

**Deliverable**: When `get()` is called inside a Flask request
context, the computation gets CRITICAL priority.

```python
def get(self, path, *, force=False, ...):
    # ... existing cache check logic ...

    # If we need to compute and we're in a web request,
    # use CRITICAL priority for the compute
    _priority = Priority.LOW  # default for background
    try:
        from flask import has_request_context
        if has_request_context():
            _priority = Priority.CRITICAL
            self._work_queue.begin_web_request()
    except ImportError:
        pass

    try:
        # ... compute logic (uses _priority if submitted to queue)
    finally:
        if _priority == Priority.CRITICAL:
            self._work_queue.end_web_request()
```

**Critical detail**: For CRITICAL priority, the `get()` call must
still be SYNCHRONOUS — the web route handler is blocking, waiting
for the result. The WorkQueue must support a `submit_and_wait(item)`
method that submits at CRITICAL priority and blocks until the result
is available, returning it to the caller.

### 3.6 Backward Compatibility — Executor Fallback

**File**: `src/core/services/mediator/core.py`

**Deliverable**: If `work_queue` is None but `executor` is provided,
the old behavior works unchanged. This allows incremental migration.

```python
def __init__(self, ..., executor=None, work_queue=None):
    self._work_queue = work_queue
    self._executor = executor  # legacy fallback
```

`dispatch()` checks: if `_work_queue` → use it. Else if
`_executor` → old behavior.

**Verify**: Existing tests pass without modification. The mediator
works the same way with WorkQueue as it did with ThreadPoolExecutor.

### Chunk 3 Summary

| Sub-chunk | File | Deliverable |
|-----------|------|-------------|
| 3.1 | `__init__.py` | WorkQueue replaces ThreadPoolExecutor |
| 3.2 | `core.py` | `dispatch()` uses WorkQueue |
| 3.3 | `tree.py` | `size` field on TreeRegistration/TreeNode |
| 3.4 | `devops.py`, `detect.py` | Size assignments for all nodes |
| 3.5 | `core.py` | Flask context → CRITICAL priority |
| 3.6 | `core.py` | Backward compatibility with executor |

**Gate**: Chunk 3 complete when the server starts with WorkQueue,
dispatches at correct priorities and sizes, and web requests
auto-elevate to CRITICAL. All existing behavior preserved.

---

## Chunk 4: Tiered Dispatch in Index Watcher

Replace the flat dispatch in `_poll_loop` with tiered, gated dispatch.

### 4.1 Tier Definitions

**File**: `src/core/services/mediator/index_watcher.py`

**Deliverable**: Replace the current `_FAST_DEVOPS` / `_HEAVY_DEVOPS` /
`_LAST` frozensets with tier definitions that carry priority, size,
and gate information.

```python
_DISPATCH_TIERS = [
    {
        "name": "tier1_fast_devops",
        "paths": ["devops.git", "devops.ci", "devops.docs",
                  "devops.dns", "devops.quality", "devops.packages"],
        "priority": Priority.LOW,
        "gate": None,  # immediate after fast index
    },
    {
        "name": "tier2_medium_devops",
        "paths": ["devops.docker", "devops.k8s", "devops.github",
                  "devops.terraform", "devops.env"],
        "priority": Priority.LOW,
        "gate": "tier1_fast_devops",
    },
    {
        "name": "tier3_heavy_devops",
        "paths": ["devops.security", "devops.testing"],
        "priority": Priority.IDLE,
        "gate": "tier2_medium_devops",
    },
    {
        "name": "tier4_aggregates",
        "paths": ["devops.status"],  # + posture.* (resolved dynamically)
        "priority": Priority.IDLE,
        "gate": "tier3_heavy_devops",
    },
    {
        "name": "tier5_feature_index",
        "paths": ["index.symbols", "index.peek", "index.stats"],
        "priority": Priority.IDLE,
        "condition": "peek_index_enabled",
        "gate": "tier4_aggregates",
    },
]
```

### 4.2 Tier Gate Mechanism

**File**: `src/core/services/mediator/index_watcher.py`

**Deliverable**: A callback mechanism that dispatches the next tier
when the current tier's tasks all complete.

The WorkQueue needs a `submit_batch(items, on_complete)` method:
- Submits all items in the batch
- When all items have completed, calls `on_complete()`
- `on_complete` triggers the next tier's dispatch

This is a counting mechanism: track how many items were submitted
for a tier, decrement on each completion, fire callback at zero.

```python
def dispatch_tiered(self, mediator, tiers):
    """Dispatch tiers sequentially via callbacks."""

    def dispatch_tier(tier_index):
        if tier_index >= len(tiers):
            return  # all tiers dispatched

        tier = tiers[tier_index]

        # Check condition (e.g., peek_index_enabled)
        if tier.get("condition") and not self._check_condition(tier["condition"]):
            dispatch_tier(tier_index + 1)  # skip, next tier
            return

        paths = self._resolve_paths(tier["paths"], mediator)
        if not paths:
            dispatch_tier(tier_index + 1)
            return

        def on_tier_complete():
            dispatch_tier(tier_index + 1)

        mediator.dispatch(
            *paths,
            priority=tier["priority"],
            on_complete=on_tier_complete,
        )

    dispatch_tier(0)
```

### 4.3 FS Change Dispatch (Non-Cold-Start)

**File**: `src/core/services/mediator/index_watcher.py`

**Deliverable**: When an FS change triggers invalidation (not cold
start), the dispatch still respects tiers but uses NORMAL priority
instead of LOW.

The smart dispatch logic (classify change check, mtime-stale
filtering) already exists. This chunk adds tier awareness to the
FS-change path:
- Invalidated nodes that are tier-1 dispatch at NORMAL priority
- Invalidated nodes that are tier-3 dispatch at IDLE priority
- The gate mechanism still applies (tier 3 waits for tier 1+2)

### 4.4 SSE Progress Events for Tiers

**File**: `src/core/services/mediator/index_watcher.py`

**Deliverable**: Existing `_publish_progress` calls updated to
include tier information so the frontend can show tier-by-tier
loading progress.

```python
_publish_progress("index:tier:start", {
    "tier": tier["name"],
    "paths": paths,
    "count": len(paths),
})
# ... on each node completion:
_publish_progress("index:tier:node:done", {
    "tier": tier["name"],
    "path": path,
    "step": i,
    "total": len(paths),
})
# ... on tier completion:
_publish_progress("index:tier:done", {
    "tier": tier["name"],
    "elapsed_ms": elapsed,
})
```

### Chunk 4 Summary

| Sub-chunk | File | Deliverable |
|-----------|------|-------------|
| 4.1 | `index_watcher.py` | Tier definitions |
| 4.2 | `index_watcher.py` + `work_queue.py` | Gate mechanism (callback chain) |
| 4.3 | `index_watcher.py` | FS change dispatch with tier awareness |
| 4.4 | `index_watcher.py` | SSE progress events per tier |

**Gate**: Chunk 4 complete when cold start dispatches tiers 1→2→3→4→5
sequentially, each waiting for the previous. Tier 5 only runs if
peek/index enabled. FS changes dispatch with appropriate priorities.

---

## Chunk 5: Migrate Ops Functions to ScanView Consumers

Convert ops functions that walk the tree just to find files into
ScanView consumers. This eliminates independent tree walks.

### 5.1 docs_ops — ScanView Consumer

**File**: `src/core/services/docs_svc/ops.py`

**What changes**: `_collect_md_files()` currently does its own
`os.walk` of the project tree collecting .md files. Change it to:
1. Try `get_scan_view()` — if available, query `files_with_ext("md")`
2. Fallback to current `os.walk` if ScanView not available

Also for doc_dirs scan, `_detect_api_specs()`, and module coverage
walks — all can query ScanView for file listings by extension and
directory, falling back to os.walk when ScanView is unavailable.

**Deliverable**: All 4 rglob/os.walk sites in docs_ops converted.
ScanView path is ~0.1ms. Fallback path unchanged.

### 5.2 docker detect — ScanView Consumer

**File**: `src/core/services/docker/detect.py`
(or wherever `docker_status` calls its file detection)

**What changes**: Dockerfile and docker-compose detection currently
walks the project tree. Change to:
1. `scan_view.files_named("Dockerfile")` — all Dockerfiles
2. `scan_view.files_named("docker-compose.yml")` + variants
3. Fallback to current walk

**Deliverable**: Docker file detection uses ScanView, no tree walk.

### 5.3 terraform ops — ScanView Consumer

**File**: `src/core/services/terraform/ops.py`

**What changes**: .tf file scanning. Change to:
1. `scan_view.files_with_ext("tf")` — all .tf files
2. Filter by directory (terraform/, infra/)
3. Fallback to current walk

**Deliverable**: Terraform file detection uses ScanView.

### 5.4 dns_cdn_ops — ScanView Consumer

**File**: `src/core/services/dns_cdn_ops.py`

**What changes**: Zone file and cert detection. Change to:
1. `scan_view.files_with_ext("zone")` + domain config filenames
2. Fallback to current walk

**Deliverable**: DNS file detection uses ScanView.

### 5.5 testing_ops — ScanView Consumer

**File**: `src/core/services/testing/ops.py`

**What changes**: Test file counting currently walks test dirs.
Change to:
1. `scan_view.files_in_dir("tests/")` + filter by ext
2. Count by framework (pytest, jest, etc.) from filenames
3. Fallback to current walk

**Deliverable**: Test counting uses ScanView. No walk for counting.

### 5.6 k8s detect — ScanView Consumer (partial)

**File**: `src/core/services/k8s/detect.py`
(or wherever `k8s_status` scans for yaml)

**What changes**: YAML collection, Chart.yaml detection, kustomize
detection. All three currently do separate walks/checks. Change to:
1. `scan_view.files_with_ext("yaml")` + `files_with_ext("yml")`
   filtered to manifest dirs
2. `scan_view.files_named("Chart.yaml")` — all helm charts
3. `scan_view.has_file("kustomization.yaml")` — kustomize check
4. Fallback to current walks

**Deliverable**: k8s file detection uses ScanView for ALL three
scans instead of three separate walks. This is the within-task
consolidation for k8s.

### 5.7 audit/l0_detection — ScanView Consumer (partial)

**File**: `src/core/services/audit/l0_detection.py`

**What changes**: `_detect_modules()` walks per module looking for
source files. Change to ScanView queries for file counts per module
directory.

**Deliverable**: Module detection uses ScanView for file counting.

### Chunk 5 Summary

| Sub-chunk | File | Walks eliminated |
|-----------|------|------------------|
| 5.1 | `docs_svc/ops.py` | 4 walks → 0 |
| 5.2 | `docker/detect.py` | 1 walk → 0 |
| 5.3 | `terraform/ops.py` | 1 walk → 0 |
| 5.4 | `dns_cdn_ops.py` | 1 walk → 0 |
| 5.5 | `testing/ops.py` | 1 walk → 0 |
| 5.6 | `k8s/detect.py` | 3 walks → 0 |
| 5.7 | `audit/l0_detection.py` | 1+ walks → 0 |

**Gate**: Chunk 5 complete when these ops functions use ScanView
when available, maintaining fallback to os.walk for CLI/test mode.
Tree walks per dispatch cycle drops from ~17 to ~5 (security scan,
symbol parser, and a few remaining content-reading walks).

---

## Chunk 6: Consolidated Tree Walker

Build the shared tree walker for ops functions that need file
CONTENTS (not just file listings). This handles the remaining
walks that ScanView can't eliminate.

### 6.1 TreeWalkCollector Interface

**File**: `src/core/services/mediator/tree_walker.py` (new)

**Deliverable**: The `TreeWalkCollector` base class / protocol.

```python
class TreeWalkCollector:
    name: str
    wants_full_tree: bool
    scope_dirs: list[str] | None

    def on_dir(self, rel_dir: str, dirnames: list[str],
               filenames: list[str]) -> None:
        """Called for each directory step. Accumulate results."""

    def on_file(self, rel_path: str, full_path: str) -> None:
        """Called for each file (optional, for content readers)."""
```

### 6.2 ConsolidatedWalker

**File**: `src/core/services/mediator/tree_walker.py`

**Deliverable**: The single-walk engine.

```python
class ConsolidatedWalker:
    def __init__(self, project_root: Path, skip_dirs: frozenset[str]):
        ...

    def walk(self, collectors: list[TreeWalkCollector],
             yield_check: Callable[[], bool] | None = None) -> None:
        """One os.walk pass, feeding all collectors.

        If yield_check is provided, calls it between directories
        and pauses briefly if it returns True (web request yielding).
        """
```

**Key integration**: the `yield_check` parameter connects the
consolidated walker to the yield flag from Chunk 1. The walker
checks for web request pressure between directory steps and
pauses if needed.

### 6.3 Security Scan Collector

**File**: `src/core/services/security/scan.py`

**What changes**: `_iter_files()` and `detect_sensitive_files()`
currently do independent full-tree walks. Refactor them to expose
a `SecurityCollector` that accumulates files during the shared walk,
then processes them (regex matching) after the walk.

**Deliverable**: Security scan participates in consolidated walks
instead of doing its own. The regex processing still happens after
file collection, but the file collection is shared.

### 6.4 Symbol Parser Collector

**File**: `src/core/services/audit/parsers/__init__.py`

**What changes**: `parse_tree()` walks the tree to find parseable
files. The incremental path (`incremental_symbols()`) already
receives a delta and only processes changed files. The cold-start
path needs the consolidated walker.

**Deliverable**: Cold-start symbol parsing uses the consolidated
walker for file discovery, then does per-file AST parsing with
yield checkpoints (see Chunk 7).

### 6.5 Work Queue Batching — Walk Detection

**File**: `src/core/services/mediator/work_queue.py`

**Deliverable**: The WorkQueue detects when multiple pending items
need tree walks and batches them.

Each WorkItem can carry a `collector: TreeWalkCollector | None`
attribute. When the queue is about to dispatch items, it checks:
1. Are there multiple items with collectors?
2. If yes → run one consolidated walk with all their collectors
3. Then dispatch each item with its pre-populated collector data

This is the "blast those blasted works together" mechanism — when
an FS trigger invalidates multiple tree-walking tasks, they share
one walk.

### Chunk 6 Summary

| Sub-chunk | File | Deliverable |
|-----------|------|-------------|
| 6.1 | `tree_walker.py` | `TreeWalkCollector` interface |
| 6.2 | `tree_walker.py` | `ConsolidatedWalker` engine |
| 6.3 | `security/scan.py` | Security collector |
| 6.4 | `audit/parsers/__init__.py` | Symbol parser collector |
| 6.5 | `work_queue.py` | Walk batching in queue |

**Gate**: Chunk 6 complete when tasks that need file content share
a single walk. Combined with Chunk 5 (ScanView consumers), tree
walks per dispatch cycle drops from ~17 to 1.

---

## Chunk 7: Yield Checkpoints in CPU-Intensive Loops

Insert yield checks in the CPU-bound loops so background work
releases the GIL for web requests.

### 7.1 Security Scan Yield Points

**File**: `src/core/services/security/scan.py`

**Deliverable**: In the inner file-reading + regex-matching loop,
check `current_yield_check()` every N files (e.g., every 10 files):

```python
from src.core.services.mediator.work_queue import current_yield_check

for i, filepath in enumerate(files):
    if i % 10 == 0 and current_yield_check():
        time.sleep(0.01)
    # ... process file
```

### 7.2 Symbol Parser Yield Points

**File**: `src/core/services/mediator/registrations/index.py`
(in `incremental_symbols`)

**Deliverable**: Yield check between file parses in the cold-start
full-parse loop.

### 7.3 Test Discovery Yield Points

**File**: `src/core/services/testing/ops.py`

**Deliverable**: Yield check between directory steps in test
counting.

### 7.4 Consolidated Walker Yield Points

**File**: `src/core/services/mediator/tree_walker.py`

**Deliverable**: The consolidated walker already accepts a
`yield_check` parameter (from 6.2). This chunk verifies that the
walker actually pauses between directory steps when the flag is set.

### Chunk 7 Summary

| Sub-chunk | File | Loop |
|-----------|------|------|
| 7.1 | `security/scan.py` | File regex matching |
| 7.2 | `registrations/index.py` | AST file parsing |
| 7.3 | `testing/ops.py` | Test file counting |
| 7.4 | `tree_walker.py` | Directory iteration |

**Gate**: Chunk 7 complete when CPU-intensive background tasks
yield at checkpoints, releasing GIL for web requests. Verified by:
start heavy background task, make web request, verify response
time is < 100ms.

---

## Chunk 8: Integration Testing & Tuning

End-to-end verification that all chunks work together.

### 8.1 Cold Start Benchmark

**Deliverable**: Script that times the full cold start with the
new system. Verify that:
- Tier 1 data is available in < 100ms
- Tier 2 data is available in < 3s
- Tier 3 data is available in < 15s
- Tier 5 only runs if peek/index enabled
- Total cold start time is comparable or better than the 31s current

### 8.2 Web Request Latency Under Load

**Deliverable**: Script that starts background indexing, then makes
concurrent web requests. Verify that:
- Web request response time < 100ms when cache is warm
- Web request response time < 500ms when cache miss (CRITICAL compute)
- Background tasks don't block web requests

### 8.3 FS Trigger Consolidation

**Deliverable**: Script that modifies a file, triggers the watcher,
and counts the number of os.walk calls. Verify that:
- Only 1 walk occurs per FS trigger (not 17)
- All ops functions get correct data from the shared walk/ScanView

### 8.4 Capacity Tuning

**Deliverable**: Measure actual system behavior with different
capacity values (4, 6, 8) and worker counts (3, 4, 5). Document
the optimal configuration for the project's typical workload size.

### Chunk 8 Summary

| Sub-chunk | Deliverable |
|-----------|-------------|
| 8.1 | Cold start benchmark — tiered data availability |
| 8.2 | Web latency under load — priority enforcement |
| 8.3 | Walk consolidation — 1 walk per trigger |
| 8.4 | Capacity tuning — optimal config |

**Gate**: Milestone complete when all benchmarks pass.

---

## Dependency Graph Between Chunks

```
Chunk 1 (WorkQueue core)
    │
    ├──→ Chunk 3 (Integrate into Mediator)
    │        │
    │        ├──→ Chunk 4 (Tiered Dispatch)
    │        │
    │        └──→ Chunk 7 (Yield Checkpoints)
    │
    └──→ Chunk 6.5 (Walk Batching in Queue)

Chunk 2 (ScanView)
    │
    └──→ Chunk 5 (Migrate Ops to ScanView)

Chunk 6.1–6.2 (Consolidated Walker) ← independent of 1–5
    │
    ├──→ Chunk 6.3 (Security Collector)
    ├──→ Chunk 6.4 (Symbol Parser Collector)
    └──→ Chunk 6.5 (Walk Batching) ← needs Chunk 1

Chunk 8 (Integration Testing) ← needs ALL of 1–7
```

### Parallelizable work

Chunks that can be built in parallel:
- Chunk 1 (WorkQueue) and Chunk 2 (ScanView) — no dependencies
- Chunk 2 (ScanView) and Chunk 6.1–6.2 (Walker) — no dependencies
- Chunk 5 (ScanView migration) and Chunk 6.3–6.4 (Collectors) —
  independent ops functions

### Recommended execution order

1. **Chunk 1** — WorkQueue core (foundation for everything)
2. **Chunk 2** — ScanView (foundation for ops migration)
3. **Chunk 3** — Integrate WorkQueue into mediator
4. **Chunk 5** — Migrate ops functions to ScanView
   (immediate I/O reduction, each sub-chunk is independently testable)
5. **Chunk 4** — Tiered dispatch (needs Chunk 3)
6. **Chunk 6** — Consolidated walker (needs Chunks 1+2 done)
7. **Chunk 7** — Yield checkpoints (needs Chunk 1 for yield flag)
8. **Chunk 8** — Integration testing (needs everything)

---

## Size Estimate

| Chunk | New code | Modified code | Complexity |
|-------|----------|---------------|------------|
| 1 | ~300 lines | 0 | High — concurrency primitives |
| 2 | ~100 lines | ~20 lines | Low — data structure + queries |
| 3 | ~50 lines | ~100 lines | Medium — integration seam |
| 4 | ~150 lines | ~200 lines (replacing existing dispatch) | Medium — callback chain |
| 5 | 0 new | ~200 lines across 7 files | Low per file — pattern repetition |
| 6 | ~150 lines | ~100 lines | Medium — walker engine + collectors |
| 7 | 0 new | ~30 lines across 4 files | Low — inserting yield checks |
| 8 | ~200 lines (scripts) | 0 | Low — benchmarking |

**Total**: ~950 lines new, ~650 lines modified across ~15 files.
