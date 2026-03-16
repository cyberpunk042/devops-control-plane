# Memory Leak / Stall Investigation

## Symptom
Program becomes unresponsive after running for a while. Ctrl+C takes time. Process appears frozen.

## Finding 1: Subprocess calls without timeout (STALL)

**8 `subprocess.run()` calls in `git/auth.py` have NO timeout.**

If any of these hang (SSH passphrase prompt, network, credential helper), the calling worker thread blocks forever. The `WeightedSemaphore.acquire()` in other workers then blocks indefinitely waiting for capacity to be released. Eventually all 4 work queue threads are stuck and the entire system freezes.

**Locations:** `src/core/services/git/auth.py` lines 59, 85, 181, 406, 457, 470, 619

**Also without timeout:**
- `src/core/services/pages_builders/mkdocs.py:46,149`
- `src/core/services/pages_builders/docusaurus.py:753`
- `src/core/services/pages_builders/sphinx.py:43,134`

**Fix:** Add `timeout=15` (or appropriate) to every `subprocess.run()` call.

## Finding 2: WeightedSemaphore blocks forever (STALL)

`work_queue.py:224` — `self._condition.wait()` has no timeout. If a worker thread hangs (see Finding 1), capacity is never released, and all other workers block indefinitely on `acquire()`.

**Location:** `src/core/services/mediator/work_queue.py:224`

**Fix:** Add a timeout to `self._condition.wait()` (e.g., 60s) and log a warning if it expires.

## Finding 3: EventBus subscriber queues (MEMORY)

Each SSE client gets a `Queue(maxsize=2000)`. Each item is the full event dict including `data` payload. A stalled SSE client (tab left open, connection half-closed) holds 2000 events × full payloads in memory. Dead subscribers are only cleaned when `put_nowait` raises `queue.Full`.

**Location:** `src/core/services/event_bus.py:231`

## Finding 4: EventBus `_latest` + `_buffer` hold full payloads (MEMORY)

Every `cache:done` stores the full data payload in:
- `_latest` dict (one per key, unbounded keys)
- `_buffer` deque (500 events with full data)
- All subscriber queues (2000 per client)

The `timeline.data` payload is the largest — contains all entries, chains, facets, calendar.

**Location:** `src/core/services/event_bus.py:74,78,172`

## Root Cause Theory

**Stall:** A `subprocess.run()` in `git/auth.py` hangs (e.g., SSH agent not responding, network timeout). The worker thread holding the `WeightedSemaphore` capacity never releases it. Other workers block on `acquire()` forever. The program appears frozen.

**Memory growth:** EventBus stores full payloads in 3 redundant locations. Each index cycle pushes ~20 cache:done events with full data through the bus. Over time, the buffer and subscriber queues accumulate large payloads.

## Recommended Fixes (DO NOT APPLY — investigation only)

### Critical (stall fix)
1. Add `timeout=15` to all subprocess.run() calls in git/auth.py
2. Add `timeout=60` to `WeightedSemaphore._condition.wait()`

### Important (memory)
3. Strip full `data` from `_buffer` events — only keep metadata
4. Add a periodic subscriber health check to evict stale SSE connections
5. Debounce `timeline.data` recompute in `@tracked` (at most once per 2-3s)
