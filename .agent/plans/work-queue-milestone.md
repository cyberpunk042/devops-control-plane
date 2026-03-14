# Work Queue Milestone — Requirements

**Date**: 2026-03-13
**Status**: Requirements phase
**Scope**: New milestone — core infrastructure

---

## Origin

The user identified fundamental problems with how the system starts
processes and handles workload. These are the user's words, preserved
exactly, followed by the concrete requirements derived from each.

---

## Problem 1: Starting processes in the wrong order

> "you are starting process in the wrong order, you are not thinking
> of the dependencies and the heavy load task such as launching test
> and execute a whole test pipeline and many other tool that were
> before on demand based on the navigation of the user that trigger
> the scan. not that we dont want them now but that it make no sense
> to load them first"

### What this means concretely

Heavy tasks like launching tests, executing a whole test pipeline,
and many other tools were **before on demand based on the navigation
of the user that trigger the scan**. The user navigating to a
specific card/page is what triggered those scans. They were not run
at cold start. They were not run in the background proactively.
They ran when the user asked for them by navigating there.

We still want these tasks. But loading them first makes no sense.
They must load AFTER the lightweight tasks that the user sees
immediately on the dashboard.

The system must think about dependencies: which tasks depend on
which, and which are heavy. Heavy tasks must not run before their
lighter dependencies are satisfied, and must not run before the
tasks the user sees first.

### What this means in the current code

Today, `index_watcher.py` dispatches _FAST_DEVOPS and _HEAVY_DEVOPS
to the executor in order, but the executor is a flat
`ThreadPoolExecutor(max_workers=4)` that picks work FIFO. The
ordering in the dispatch list is meaningless — all tasks hit the
pool at once and 4 run concurrently regardless of weight.

Heavy tasks that run today at cold start (these should NOT run first):
- `devops.security` — 7-13s, full tree scan + regex on every file
- `devops.testing` — 3-7s, test framework detection + file counting
- `devops.docker` — 1.7s, 3 subprocess calls
- `devops.k8s` — 1.2s, 8 subprocess calls + yaml parsing
- `devops.terraform` — 1.4s, subprocess + file parsing
- `devops.env` — 2.3s, gh API calls

Light tasks that the user sees first on the dashboard:
- `devops.git` — 0.05s
- `devops.ci` — 0.00s
- `devops.docs` — 0.01s
- `devops.dns` — 0.12s
- `devops.quality` — 0.44s
- `devops.packages` — 0.72s

---

## Problem 2: Peek / AST L5 feature index loads at the wrong time

> "and obviously peek / AST L5 feature index last (if even enabled
> by the user)"

### What this means concretely

`index.symbols` (30s cold start, AST parsing of every source file)
and `index.peek` (2s cold start, peek cache) must load LAST. After
all devops tasks. After everything else.

And only if the user has the feature enabled. The gate already
exists — `is_peek_index_enabled()` in `server.py` line 292. But
when enabled, these nodes currently dispatch in `_SLOW_INDEX`
alongside everything else on the first cycle.

---

## Problem 3: Web request priority in the index queue

> "what about when a request happens, do you prioritize it in the
> index queue ? imagine I am manually refreshing while the index is
> working because of a change. You most also make sure that a server
> request in general related to index or has a much heavier priority,
> even to the point of slowing down the index worker to avoid
> freezing the com or losing priority."

### What this means concretely

When the user manually refreshes the browser, or any web request
comes in that needs mediator data, that request must have **much
heavier priority** than the background index worker.

"Much heavier" is not "slightly higher." It means:

- The index worker must **slow itself down** when web requests
  are in flight. Not just deprioritize — actually slow down.
  The purpose is to avoid **freezing the communication** (web
  server responses) or **losing priority** (web requests starved
  by background compute).

- The web request must be served FIRST. If the index worker is
  busy recomputing nodes after a FS change and the user refreshes,
  the user's refresh wins. The index worker yields.

### What this means in the current code

Today, `mediator.get(path, force=True)` is called both by web
route handlers (user request) and by `_dispatch_worker` (background
index). They use the SAME code path. There is no priority
distinction. They compete for the same locks (`_compute_locks`).

If the worker is holding `_compute_locks["devops.security"]` and
the user's web request needs `devops.security`, the web request
blocks until the background worker finishes (7-13s).

The `peek()` path serves cached data without blocking, but if the
cache is empty (cold start) or invalidated (FS change just
happened), the web request has no cached data and must wait.

---

## Problem 4: CPU-intensive threads in parallel

> "imagine you started a thread that itself is CPU intensive, what
> happens when you run too much in parallel with it you think ? its
> the same thing it has to take more space in the queue, a size 2
> or a size 3."

### What this means concretely

CPU-intensive tasks (symbol parsing, security regex scanning, test
pipeline execution) take more resources than lightweight tasks.
Running too much in parallel with a CPU-intensive thread degrades
everything — the web server, the index worker, and the other tasks.

The solution: tasks have a **size**. Heavyweight tasks take more
space in the queue. A size 2 or a size 3. Lightweight tasks are
size 1.

The queue has a capacity. When a size-3 task is running, it
consumes 3 units of capacity. This means fewer other tasks can run
alongside it. This prevents the system from running 4 CPU-intensive
tasks simultaneously in a 4-worker pool and starving everything.

Concrete size assignments based on current measurements:

| Task | Current time | Size |
|------|-------------|------|
| `devops.git` | 0.05s | 1 |
| `devops.ci` | 0.00s | 1 |
| `devops.docs` | 0.01s | 1 |
| `devops.dns` | 0.12s | 1 |
| `devops.quality` | 0.44s | 1 |
| `devops.packages` | 0.72s | 1 |
| `devops.github` | 0.89s | 2 (subprocess/API) |
| `devops.docker` | 1.74s | 2 (subprocess) |
| `devops.k8s` | 1.20s | 2 (subprocess + parse) |
| `devops.terraform` | 1.37s | 2 (subprocess + parse) |
| `devops.env` | 2.33s | 2 (gh API calls) |
| `devops.security` | 7-13s | 3 (full tree scan + regex) |
| `devops.testing` | 3-7s | 3 (test discovery + counting) |
| `index.symbols` | 30s cold | 3 (AST parsing, CPU-bound) |
| `index.peek` | 2s cold | 2 (peek cache build) |

---

## Problem 5: Size AND priority — the queue model

> "so everything will have a size and a priority and the queue will
> respect the web request priority and also impose cache access from
> web request and computing priority."

### What this means concretely

Every task has TWO attributes: **size** and **priority**.

The queue enforces TWO things:

1. **Web request priority**: web requests always go first. The queue
   respects their priority above all background work.

2. **Cache access from web request AND computing priority**: the
   queue imposes that web requests get cache access priority (serve
   from cache without waiting for background recomputation) AND
   computing priority (if they need to compute, they compute first).

This is not just a priority queue. It's a resource-aware scheduler
that manages both cache access and compute scheduling. Web requests
get both — cache access AND compute priority.

---

## Problem 6: Consolidated tree walks — browsing together

> "anything that browser the whole tree of the project, should browse
> it together. Do you understand what I mean ? instead of looping 20
> times, there is just one loop every times there are tree browser
> in the queue we let them race with use executing their own check
> in chain after we did ours in the same steps instead of 20
> independent step that repeat the read and I/O"

### What this means concretely

Anything that browses the whole project tree must browse it
TOGETHER. Not separately. Not independently.

Instead of 20 independent loops that each repeat the same directory
reads and I/O syscalls, there is ONE loop.

Every time there are tree browsers in the queue, they race together.
Each one executes their own check in chain, within the same walk
steps. One walk, multiple consumers racing through it, each doing
their own check at each step.

Not 20 independent steps that repeat the read and I/O. One step,
with 20 checks executing in chain within that single step.

### Current tree walk sites (17 separate walks)

These are all the places in the codebase that walk the project tree
today. Each one does its own independent `os.walk` or equivalent:

| File | Function | Scope |
|------|----------|-------|
| `mediator/registrations/index.py` | `scan_project()` | Full project tree |
| `mediator/index_watcher.py` | `scan_dir_mtimes()` | Full project tree (dirs only) |
| `security/scan.py` | `_iter_files()` | Full project tree |
| `security/scan.py` | `detect_sensitive_files()` | Full project tree |
| `docs_svc/ops.py` | `_collect_md_files()` | Full project tree |
| `docs_svc/ops.py` | doc_dirs scan | Scoped to doc dirs |
| `docs_svc/ops.py` | `_detect_api_specs()` | Root + api/ + docs/ |
| `docs_svc/ops.py` | module doc coverage | Per module |
| `docker/detect.py` | dockerfile scan | Full tree (with pruning) |
| `dns_cdn_ops.py` | zone/cert scan | Full tree (with pruning) |
| `k8s/detect.py` | `_collect_yaml_files()` | Manifest dirs |
| `k8s/detect.py` | `_detect_helm_charts()` | Known dirs + 1 level |
| `testing/ops.py` | test file counting | Per test dir |
| `audit/l0_detection.py` | `_detect_modules()` | Per module |
| `audit/parsers/__init__.py` | parse tree | Full project tree |
| `audit/l2_repo.py` | file inventory | Full project tree |
| `terraform/ops.py` | tf file scan | tf_root dir |

When the index watcher triggers a dispatch cycle, many of these run
in the same cycle. Each one does its own `os.walk`. That's the same
tree read N times. The consolidated walk makes it 1 read, N checks.

---

## Problem 7: FS trigger batching — blasted works together

> "this mean when there is a index fs trigger, everytime there is a
> blast those blasted works together to reduce needless operations"

### What this means concretely

When the index watcher detects a filesystem change (a "blast"),
ALL the tasks that get invalidated ("blasted") by that change must
work together. They must share their I/O. They must reduce needless
repetition of the same operations.

Today, when a directory mtime changes, the watcher invalidates
`index.scan` which cascades to invalidate all downstream nodes.
Then it dispatches all those nodes to the executor. Each node runs
its resolver independently. If 10 resolvers each walk the tree,
that's 10 walks triggered by a single FS event.

With consolidated walks, a single FS trigger (blast) causes a
single walk, and all blasted tasks consume that single walk's
output.

---

## Problem 8: Within-task consolidation

> "This is major because this also mean that within a same task like
> k8s scan you will need to group all the scan into a single walk
> instead of multiple ones"

### What this means concretely

Even within a single task like `k8s_status()`, there are currently
multiple independent file scans:

- `_collect_yaml_files()` — walks manifest dirs collecting yaml
- `_detect_helm_charts()` — walks known dirs looking for Chart.yaml
- `_detect_kustomize()` — checks specific file paths

These should be a SINGLE walk of the relevant directories. One walk
that collects yaml files, detects Chart.yaml locations, AND checks
for kustomization.yaml — all in the same pass.

Same applies to other tasks:
- `security_ops` does `_iter_files()` + `detect_sensitive_files()` — two walks
- `docs_ops` does `_collect_md_files()` + doc_dirs + api_specs + module coverage — four walks
- `docker_status` scans for Dockerfiles, docker-compose files, and .dockerignore — could be one walk

---

## This is a new milestone

> "is a new milestone, treat it accordingly"

This is not a quick optimization. This is not a code edit. This is
a fundamental change to how the system orchestrates work.

It requires:
1. A new queue system with size and priority attributes
2. Web request priority enforcement with index worker throttling
3. A consolidated tree walk mechanism
4. Load order awareness based on dependencies and weight
5. FS trigger batching (blasted works together)
6. Within-task walk consolidation for each ops function
7. Peek / AST L5 deferred to last, conditional on user setting

---

## Current System State (Reference)

### Executor
- `ThreadPoolExecutor(max_workers=4, thread_name_prefix="mediator")`
- Flat FIFO — no priority, no size tracking
- Located in `mediator/__init__.py` line 82

### Dispatch mechanism
- `QueryMediator.dispatch()` in `core.py` line 1206
- Submits each path as its own task: `executor.submit(_dispatch_worker, task_id, [p])`
- No priority. No size. No backpressure.
- `_dispatch_worker` calls `self.get(p, force=True)` — same code path as web requests

### Index watcher loop
- `_poll_loop()` in `index_watcher.py` line 141
- Polls every `POLL_INTERVAL_S` seconds
- On change: invalidates `index.scan`, cascades, dispatches bg nodes
- Has _FAST_DEVOPS / _HEAVY_DEVOPS / _LAST ordering but it's
  meaningless because executor is flat FIFO
- No awareness of web request load
- No throttling when web requests are in flight

### Web request path
- Context processors use `mediator.peek()` — non-blocking, cache-only
- Route handlers use `mediator.get()` — blocking, computes on miss
- No priority distinction from background dispatch
- Competes for same `_compute_locks` as background workers

### Cold start behavior
- First cycle: fast index nodes sync (45ms), then dispatches ALL
  devops/posture nodes to executor simultaneously
- No tier ordering. No load-order awareness.
- Heavy tasks (security 13s, testing 7s) run alongside light tasks
- Peek/symbols dispatched in same cycle if enabled
