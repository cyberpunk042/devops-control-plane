# M6 — WorkQueue: Heavy Operations Off the Request Thread

> The compat engine's heavy operations (analyze, assess, plan create) currently run
> synchronously in Flask request handlers, blocking the single-threaded server. The
> program has a WorkQueue with priority levels, weighted semaphore, cooperative yielding,
> and batch tracking. Every heavy compat operation must go through it.

---

## What Exists Now (broken)

Every compat operation runs synchronously in the request thread:
- `/api/compat/analyze` → runs analyze_module() in the request → blocks server
- `/api/compat/assess` → runs analyze_transitive() in the request → blocks server
- `/api/compat/plan/create` → runs assess() + analyze() in the request → blocks server
- `/api/compat/fix/apply-all` → runs analyze + fix in the request → blocks server

Flask dev server is single-threaded. One 3-second analysis blocks all other requests.

The WorkQueue exists specifically for this. It has:
- `submit_and_wait()` for synchronous results with timeout
- Priority CRITICAL for web requests, BACKGROUND for autonomous work
- WeightedSemaphore: heavy tasks (size=3) limit concurrency
- `begin_web_request()`/`end_web_request()` for yield flag
- Worker threads that yield to web requests via `current_yield_check()`

---

## What M6 Delivers

### 1. `/api/compat/analyze` via WorkQueue

```python
@compat_bp.route("/compat/analyze", methods=["POST"])
def compat_analyze():
    module_name = body.get("module")
    m = get_mediator()

    # First try cache
    cached = m.peek(f"compat.analysis.{module_name}")
    if cached is not None:
        return jsonify({"ok": True, "findings": ..., "source": "cache"})

    # Not cached — submit to WorkQueue at HIGH priority (user clicked button)
    # This runs in a worker thread, not the request thread
    result = m.get(f"compat.analysis.{module_name}")
    # mediator.get() uses submit_and_wait internally for WorkQueue-backed nodes
    return jsonify({"ok": True, "findings": ...})
```

The mediator's `get()` already integrates with WorkQueue for nodes that have resolvers.
If the WorkQueue is configured, `get()` submits the resolver as a WorkItem at CRITICAL
priority (web request) via `submit_and_wait()`. The request thread waits for the result
but the GIL is released during computation — other worker threads can serve other requests.

### 2. Background analysis dispatch

For non-urgent analysis (startup pre-computation, post-fix re-analysis):

```python
# After fixing files — dispatch re-analysis at BACKGROUND priority
m.dispatch(f"compat.analysis.{module_name}")
# Returns immediately — worker picks it up when capacity is available
```

### 3. WorkItem sizing for compat operations

Register compat nodes with appropriate size in the mediator:

```python
tree.register(TreeRegistration(
    path=f"compat.analysis.{module_name}",
    resolver=_make_analysis_resolver(module_name),
    ttl=None,
    persist=True,
    depends_on=["index.scan"],
    size=3,  # Heavy — limits concurrency, prevents monopolizing workers
))
```

Size=3 means a compat analysis consumes 3 of the WorkQueue's 6 capacity units.
Only 2 compat analyses can run simultaneously. This leaves capacity for other work.

### 4. Registry load via WorkQueue

The M1 registry load also goes through the WorkQueue:

```python
# On startup:
mediator.dispatch("compat.registry")
# Runs at BACKGROUND(5) — dead last, only when nothing else needs capacity
```

---

## Files Changed

| File | Action |
|------|--------|
| `src/core/services/mediator/registrations/compat.py` | Add size=3 to analysis nodes |
| `src/ui/web/routes/compat.py` | Use mediator.get() which goes through WorkQueue |

---

## Verification

1. `/api/compat/analyze` does not block the request thread during computation
2. During analysis, other endpoints remain responsive
3. `mediator.diag()` shows compat.analysis nodes with size=3
4. Background dispatch runs at BACKGROUND(5) priority
5. Web requests preempt background analysis via yield checkpoints
