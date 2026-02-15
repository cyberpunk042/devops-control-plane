# Phase 7: SSE Event Bus — Reactive Streaming Architecture

**Status:** Deep Planning  
**Depends on:** Phase 6 (Caching Architecture) ✅  
**Goal:** Transition from request/response polling to event-driven streaming.  
The server pushes state changes. The client reacts. External changes trigger automatic refresh.  
Full observability into every backend operation.

---

## 1. Why This Matters

The cache system (Phase 6) solves "don't recompute." This phase solves "**don't re-ask**."

| Problem | Current | With Event Bus |
|---|---|---|
| First load | 15+ parallel API calls, cold-cache contention | Pre-injected data in HTML, zero roundtrips |
| Warm refresh | 15+ API calls returning unchanged data | SSE delivers only what changed |
| External file change | User must manually bust cache | File watcher → auto-invalidate → auto-push |
| Visibility | Black box — request goes out, eventually resolves or times out | Every lifecycle step is visible: miss → computing → done |
| Reconnection | Re-fetch everything from scratch | Replay missed events, or snapshot if too stale |
| CI/GitHub events | Polled on user action | Pushed via webhooks → event bus → SSE |

This is the foundation for a reactive system. Everything downstream (file watchers, git hooks, CI integration, multi-tab sync) builds on this bus.

---

## 2. Architecture

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │  BROWSER                                                                │
 │                                                                         │
 │  ┌──────────────┐       ┌─────────────────────────────────────────┐     │
 │  │  StateStore   │◄──────│  EventSource (/api/events?since=<seq>) │     │
 │  │  _store[key]  │       │  auto-reconnect + Last-Event-Id        │     │
 │  │               │       └─────────────────────────────────────────┘     │
 │  └──────┬───────┘                                                       │
 │         │ state changed → notify visible cards                          │
 │         ▼                                                               │
 │  ┌──────────────┐                                                       │
 │  │  CardRenderer │  renderCard(key, data) — only if card visible        │
 │  │  per card     │  tab switch → reads _store → renders immediately     │
 │  └──────────────┘                                                       │
 │                                                                         │
 │  api() still used for ACTIONS (POST bust, POST validate, etc.)          │
 │  __INITIAL_STATE__ pre-injected for zero-RTT first paint                │
 └─────────────────────────────────┬───────────────────────────────────────┘
                                   │  SSE (read)
                                   │  HTTP POST (write)
                                   ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │  FLASK SERVER                                                           │
 │                                                                         │
 │  ┌────────────────────────────────────────────────────────────────────┐  │
 │  │                         EventBus                                   │  │
 │  │  .publish(type, key, data)  → broadcast to all subscribers        │  │
 │  │  .subscribe(since)          → yields events (SSE generator)       │  │
 │  │  .snapshot()                → current state for pre-injection     │  │
 │  │  ._buffer (ring)            → bounded deque for replay            │  │
 │  │  ._seq (monotonic)          → sequence counter for ordering       │  │
 │  │  ._instance_id              → server boot timestamp              │  │
 │  └───┬──────────────┬──────────────────────┬─────────────────────────┘  │
 │      │              │                      │                            │
 │  ┌───▼────────┐ ┌───▼──────────┐  ┌───────▼──────────┐                 │
 │  │ CacheModule│ │ FileWatcher  │  │ CacheWarming     │                 │
 │  │get_cached()│ │ (future)     │  │ (bg thread)      │                 │
 │  │ publishes: │ │ inotify →    │  │ on server start  │                 │
 │  │ hit/miss/  │ │ debounce →   │  │ walks all keys   │                 │
 │  │ done/error │ │ invalidate → │  │ publishes warm   │                 │
 │  │            │ │ publish      │  │ events           │                 │
 │  └────────────┘ └──────────────┘  └──────────────────┘                 │
 │                                                                         │
 │  index() → render_template("index.html",                               │
 │             initial_state = bus.snapshot())                              │
 └─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Message Standard

This is the core contract. Every event — past, present, and future features — follows this standard.

### 3.1 SSE Wire Format

```
event: cache:done
id: 47
data: {"v":1,"ts":1739648400.123,"type":"cache:done","key":"docker","data":{...},"duration_s":2.51}

```

Three SSE fields only: `event`, `id`, `data`. Always in this order. Always followed by a blank line.

### 3.2 Payload Envelope

Every `data:` line is a JSON object with this structure:

```json
{
  "v": 1,
  "ts": 1739648400.123,
  "seq": 47,
  "type": "cache:done",
  "key": "docker",
  "data": { },
  "meta": { }
}
```

| Field | Type | Required | Stability | Description |
|---|---|---|---|---|
| `v` | int | ✅ always | immutable | Schema version. Allows breaking changes to payload format without breaking old clients. Currently `1`. |
| `ts` | float | ✅ always | immutable | Server timestamp. Unix epoch, millisecond precision. Source of truth for ordering within the same sequence. |
| `seq` | uint64 | ✅ always | immutable | Monotonically increasing per server instance. Resets on server restart. Used for `Last-Event-Id` replay. |
| `type` | string | ✅ always | stable | Event type. Format: `<domain>:<action>`. Matches the SSE `event:` field. See §3.3. |
| `key` | string | depends | stable | Resource identifier. Required for `cache:*` and `fs:*` events. Empty string for `sys:*` events. |
| `data` | object | depends | varies | Event-specific payload. Schema varies by `type`. May be `{}` for signal-only events. |
| `meta` | object | ❌ optional | unstable | Observability metadata. Clients MUST NOT rely on `meta` for logic. |
| `error` | string | ❌ optional | stable | Human-readable error message. Only present on error events. |
| `duration_s` | float | ❌ optional | stable | Wall-clock duration of the operation. Only on completion events. |

**Guarantees about fields:**
- `immutable`: will never change meaning or type
- `stable`: may gain new values but existing values keep their meaning
- `unstable`: may change shape at any time (for debugging/logging only)
- `varies`: defined per event type — see §3.4

### 3.3 Type Namespace

Types follow `<domain>:<action>` format. Domains are independently extensible.

| Domain | Purpose | Current | Future |
|---|---|---|---|
| `cache` | Cache lifecycle | `hit`, `miss`, `done`, `error`, `bust` | — |
| `sys` | Server lifecycle | `ready`, `warming`, `warm`, `heartbeat` | `shutdown` |
| `state` | State synchronization | `snapshot` | `diff` |
| `fs` | Filesystem changes | — | `change`, `invalidate` |
| `git` | Git operations | — | `commit`, `push`, `branch`, `merge` |
| `ci` | CI/CD pipeline | — | `run:start`, `run:done`, `run:fail` |
| `gh` | GitHub events | — | `pr:open`, `pr:merge`, `review`, `release` |

**Rules for adding new domains:**
1. Pick a short, lowercase name (2-5 chars)
2. Actions are lowercase, may use `:` for sub-namespacing (`ci:run:start`)
3. Document the `data` schema for each type
4. Never reuse a retired type name

### 3.4 Event Type Specifications

#### `cache:hit`
```json
{
  "type": "cache:hit",
  "key": "docker",
  "data": { "age_seconds": 42, "mtime": 1739648000.0 },
  "meta": { "watch_paths": ["docker-compose.yml", "Dockerfile"] }
}
```
When: `get_cached()` finds a valid cache entry (mtime unchanged).  
Client action: None (card already has this data from pre-injection or previous event).

#### `cache:miss`
```json
{
  "type": "cache:miss",
  "key": "docker",
  "data": { "reason": "expired" | "absent" | "forced" }
}
```
When: Cache miss detected, computation is starting.  
Client action: Show loading indicator on the card. The UI knows work is happening.
Reason values:
- `expired`: mtime changed since last cache
- `absent`: key not in cache at all (first compute)
- `forced`: user clicked bust/refresh

#### `cache:done`
```json
{
  "type": "cache:done",
  "key": "docker",
  "duration_s": 2.51,
  "data": { /* full card payload — same shape as GET /api/docker/status response */ }
}
```
When: Computation finished, result cached.  
Client action: Update state store, re-render card if visible.  
**The `data` field contains the FULL card payload.** This is intentional — the client never needs a separate `api()` call for card data.

#### `cache:error`
```json
{
  "type": "cache:error",
  "key": "docker",
  "duration_s": 10.03,
  "error": "Docker daemon not responding",
  "data": {}
}
```
When: `compute_fn()` raised an exception.  
Client action: Show error state on the card.

#### `cache:bust`
```json
{
  "type": "cache:bust",
  "key": "",
  "data": { "scope": "all" | "docker" | "docker,k8s,terraform", "source": "user" | "cascade" | "fs" }
}
```
When: Cache invalidated via user action, cascade, or file watcher.  
Client action: Mark affected cards as stale. Wait for subsequent `cache:miss` → `cache:done`.

#### `sys:ready`
```json
{
  "type": "sys:ready",
  "key": "",
  "data": {
    "instance_id": "2026-02-15T17:00:00",
    "version": "0.1.0",
    "cache_keys": ["security", "testing", "quality", "packages", "env", "docs", "docker", "k8s", "terraform", "dns", "ci", "git"],
    "project_root": "/home/jfortin/devops-control-plane"
  }
}
```
When: First event on any new SSE connection (before replay).  
Client action: Check `instance_id` — if it differs from the previous session, discard local state and expect a fresh `state:snapshot`. Store `cache_keys` as the universe of known cards.

#### `sys:warming`
```json
{
  "type": "sys:warming",
  "key": "",
  "data": { "keys": ["security", "testing", ...], "total": 12 }
}
```
When: Background warming thread starts on server boot.  
Client action: Show "warming up..." indicator. The user knows the system is working.

#### `sys:warm`
```json
{
  "type": "sys:warm",
  "key": "",
  "duration_s": 12.4,
  "data": { "keys_computed": 8, "keys_cached": 4, "total": 12 }
}
```
When: All background warming complete.  
Client action: Remove warming indicator. All cards should now have data.

#### `sys:heartbeat`
```json
{
  "type": "sys:heartbeat",
  "key": "",
  "data": {}
}
```
When: Every 30 seconds if no other events. Keeps the SSE connection alive (prevents proxy/browser timeout).  
Client action: None. Internal bookkeeping only.

#### `state:snapshot`
```json
{
  "type": "state:snapshot",
  "key": "",
  "data": {
    "docker": { "data": {...}, "cached_at": 1739648400, "age_s": 42 },
    "testing": { "data": {...}, "cached_at": 1739648100, "age_s": 342 },
    ...
  }
}
```
When: On fresh connect (no `since`) or when replay buffer is exhausted (client was away too long).  
Client action: Replace entire state store with snapshot data. Re-render all visible cards.

---

## 4. Deep Analysis: Guarantees and Edge Cases

### 4.1 Event Ordering

**Guarantee:** Events for the SAME key arrive in `seq` order. Events for DIFFERENT keys may interleave.

```
seq=1  cache:miss  key=docker
seq=2  cache:miss  key=testing
seq=3  cache:done  key=docker     ← docker finishes first
seq=4  cache:done  key=testing    ← testing finishes second
```

The client MUST NOT assume `cache:miss` is immediately followed by `cache:done` for the same key — other events may appear in between.

**Implementation:** The `seq` counter is atomic (single lock), so events from different threads always get distinct, ordered sequence numbers. The order reflects when the event was *published*, not when the underlying work started.

### 4.2 Reconnection Protocol

```
SCENARIO 1: Brief disconnect (< buffer window)
─────────────────────────────────────────────────
1. Client connects:       GET /api/events?since=0
2. Server sends:          sys:ready (instance_id="A") → state:snapshot → ...events...
3. Client receives up to: id=47
4. ── Network blip ──
5. Client reconnects:     GET /api/events  (header: Last-Event-Id: 47)
6. Server checks:         instance_id still "A", seq 47 is in buffer
7. Server replays:        events 48, 49, 50, ... (whatever was missed)
8. Client merges:         updates state store incrementally

SCENARIO 2: Long disconnect (buffer exhausted)
──────────────────────────────────────────────────
1-4. Same as above
5. Client reconnects:     GET /api/events  (header: Last-Event-Id: 47)
6. Server checks:         seq 47 is NOT in buffer (evicted)
7. Server sends:          sys:ready → state:snapshot (full replacement)
8. Client replaces:       entire state store with snapshot

SCENARIO 3: Server restart
──────────────────────────────────────────────────
1. Client had instance_id="A", Last-Event-Id=47
2. Server restarts → new instance_id="B", seq resets to 0
3. Client reconnects:     GET /api/events  (header: Last-Event-Id: 47)
4. Server: seq 47 doesn't exist AND instance_id changed
5. Server sends:          sys:ready (instance_id="B") → state:snapshot
6. Client detects:        instance_id changed from "A" → "B"
7. Client:                discards all local state, loads from snapshot
```

### 4.3 Thread Safety (EventBus internals)

```python
class EventBus:
    # Thread-safe via per-subscriber Queue objects.
    # Publisher pushes to all queues under a single lock.
    # Subscriber generators consume from their own queue (no shared state).
    
    _lock: threading.Lock          # protects _seq, _buffer, _subscribers
    _seq: int = 0                  # monotonic counter
    _buffer: deque[dict]           # ring buffer (bounded)
    _subscribers: list[Queue]      # one Queue per connected SSE client
    _instance_id: str              # server boot timestamp
```

**Lock contention analysis:**

The lock is held for:
1. `publish()`: increment seq, append to buffer, iterate subscribers (N queues × `put_nowait`) — **O(N)** where N = connected tabs (typically 1-3)
2. `subscribe()`: replay from buffer, add queue to list — **O(buffer_size)** on connect, then never again
3. Subscriber removal (finally block): remove queue — **O(N)**

Under normal operation, `publish()` is the hot path. With 1-3 subscribers and put_nowait (non-blocking), this is sub-millisecond. **No concern about lock contention.**

**Dead subscriber detection:**

If a subscriber's queue is full (`maxsize` exceeded), the subscriber is presumed dead (client disconnected but generator not yet garbage-collected). The publisher drops events for that subscriber and marks it for removal.

### 4.4 Backpressure

**Server → Client:** SSE is a push channel with no backpressure signal. If the client can't consume fast enough, events buffer in the TCP send buffer, then the kernel drops the connection. EventSource auto-reconnects and replays from `Last-Event-Id`.

In practice, this is a non-issue:
- Events are small (< 50KB each, most < 5KB)
- Peak rate: ~20 events during cache warming (~2 events/sec)
- Steady state: 1 event per 30s (heartbeat)
- Burst: cache bust → 12 `cache:miss` events → 12 `cache:done` events over 10-30 seconds

**Client → Server:** Actions (POST bust, validate, etc.) still use `api()` with the semaphore. No change.

### 4.5 Multiple Tabs

Each browser tab opens its own SSE connection. Each gets its own subscriber queue in the EventBus. This is correct:

- Tab A and Tab B both receive all events
- Tab A on DevOps tab, Tab B on Integrations tab — both get all cache:done events, each renders only its visible cards
- If Tab A triggers a cache bust (POST), the EventBus publishes `cache:bust` → Tab B receives it and marks cards stale

No special handling needed. The bus treats all subscribers equally.

### 4.6 Data Size Concerns

**Pre-injection (`__INITIAL_STATE__`):**

| Key | Typical data size |
|---|---|
| security | ~2KB |
| testing | ~3KB (file lists) |
| quality | ~1KB |
| packages | ~2KB |
| env | ~1KB |
| docs | ~1KB |
| docker | ~2KB |
| k8s | ~5KB (manifest lists) |
| terraform | ~5KB (resource lists) |
| dns | ~1KB |
| ci | ~1KB |
| git | ~1KB |
| **Total** | **~25KB** |

25KB of JSON embedded in HTML is negligible on localhost. Even on a slow network, it compresses to ~5KB with gzip.

**`cache:done` events:**

Same sizes as above. Each event carries the full card payload. At ~5KB average per event, 12 events during warming = 60KB total over the SSE stream. Negligible.

**Decision: Always include full `data` in `cache:done`.** The alternative (reference-only → separate fetch) adds complexity for zero benefit at these data sizes.

### 4.7 Idempotency

Events MUST be idempotent. Replaying the same event twice must produce the same result as playing it once.

- `cache:done` → updates store[key] = data. Replaying overwrites with same data. ✓
- `cache:miss` → sets loading indicator. Replaying keeps indicator. ✓
- `cache:bust` → marks cards stale. Replaying keeps them stale. ✓
- `state:snapshot` → replaces entire store. Replaying replaces again. ✓

All safe. No side effects from replay.

---

## 5. Future Integration: External Change Detection

This is why the bus must be solid. File watchers, git hooks, and CI webhooks all converge on the same event bus.

### 5.1 File Watcher (Phase 8, future)

```
File saved by editor → inotify detects → debounce (2s) → map to cache key(s)
→ invalidate cache → publish fs:invalidate → SSE → client marks stale
→ auto-recompute → publish cache:done → SSE → client renders fresh
```

**Key design decisions for file watcher:**

1. **Watch directories, not files.** inotify has per-user limits (~8192 watches). With 78k files, watching each is impossible. Watch the project root recursively + specific directories from `_WATCH_PATHS`.

2. **Debounce aggressively.** Editors save files in multiple steps (write temp → rename → delete backup). Many tools trigger 3-5 filesystem events per "save." Debounce: group events by cache key, fire once per key per 2-second window.

3. **Map changes to cache keys.** Reuse the existing `_WATCH_PATHS` mapping in `devops_cache.py`. When a file changes, check which watch paths match → invalidate those keys.

4. **Don't compute on file change.** Only INVALIDATE. Let the next `get_cached()` call (or the SSE-driven re-fetch) trigger the actual computation. This prevents storm scenarios where rapid saves trigger 10 recomputes.

5. **Ignore `.git/` internal changes.** Git operations (commit, rebase, pull) create hundreds of filesystem events inside `.git/objects/`, `.git/refs/`, etc. These should NOT trigger card invalidation. Only watch for `HEAD` change (branch switch), new/deleted files in tracked directories.

### 5.2 Git Event Detection (Phase 9, future)

```
git commit → .git/HEAD mtime changes → fs watcher detects 
→ publish git:commit → invalidate git cache → SSE → client refreshes git card
```

Or via post-commit hook:
```bash
#!/bin/sh
curl -s -X POST http://localhost:8000/api/events/hook/git-commit
```

### 5.3 CI/GitHub Webhooks (Phase 10, future)

```
GitHub PR merged → webhook hits /api/webhooks/github
→ parse event → publish gh:pr:merge → invalidate gh-pulls cache → SSE → client
```

All three paths (file watcher, git hook, webhook) produce events on the same bus. The client doesn't need to know the source — it just reacts to events.

---

## 6. Client-Side Architecture

### 6.1 State Store

The client transitions from "fetch on demand" to "state store + reactive rendering."

```javascript
// Global state store — single source of truth for all card data
const _store = {};

// Cards register themselves as renderers
const _renderers = {};   // key → [renderFn, ...]

function storeSet(key, data) {
    _store[key] = data;
    // Notify all registered renderers for this key
    for (const fn of (_renderers[key] || [])) {
        try { fn(data); } catch (e) { console.error(`Render ${key}:`, e); }
    }
}

function storeGet(key) {
    return _store[key] || null;
}

function storeRegister(key, renderFn) {
    (_renderers[key] ??= []).push(renderFn);
}
```

### 6.2 SSE Connection Manager

```javascript
const _sse = {
    source: null,
    instanceId: null,
    lastSeq: 0,
    
    connect() {
        const url = `/api/events${this.lastSeq ? '?since=' + this.lastSeq : ''}`;
        this.source = new EventSource(url);
        
        // Route events by type
        this.source.addEventListener('sys:ready', (e) => this._onReady(e));
        this.source.addEventListener('state:snapshot', (e) => this._onSnapshot(e));
        this.source.addEventListener('cache:done', (e) => this._onCacheDone(e));
        this.source.addEventListener('cache:miss', (e) => this._onCacheMiss(e));
        this.source.addEventListener('cache:bust', (e) => this._onCacheBust(e));
        this.source.addEventListener('cache:error', (e) => this._onCacheError(e));
        
        this.source.onerror = () => {
            // EventSource auto-reconnects. Last-Event-Id is sent automatically.
            // No manual intervention needed.
        };
    },
    
    _onReady(e) {
        const payload = JSON.parse(e.data);
        if (this.instanceId && this.instanceId !== payload.data.instance_id) {
            // Server restarted — discard local state
            Object.keys(_store).forEach(k => delete _store[k]);
        }
        this.instanceId = payload.data.instance_id;
        this.lastSeq = payload.seq;
    },
    
    _onSnapshot(e) {
        const payload = JSON.parse(e.data);
        for (const [key, entry] of Object.entries(payload.data)) {
            storeSet(key, entry.data);
        }
        this.lastSeq = payload.seq;
    },
    
    _onCacheDone(e) {
        const payload = JSON.parse(e.data);
        storeSet(payload.key, payload.data);
        this.lastSeq = payload.seq;
    },
    
    // ... other handlers
};
```

### 6.3 Migration Path for Cards

**Before (current):**
```javascript
async function loadDockerCard() {
    const cached = cardCached('docker');
    if (cached) { renderDockerCard(cached); return; }
    const data = await api('/docker/status');
    cardStore('docker', data);
    renderDockerCard(data);
}
```

**After (progressive — Phase 7D):**
```javascript
// Registration (runs once at page load)
storeRegister('docker', renderDockerCard);

// On page load: render from pre-injected state (if available)
const initial = storeGet('docker');
if (initial) renderDockerCard(initial);

// SSE delivers cache:done → storeSet('docker', data) → renderDockerCard(data) automatically
// No explicit fetch needed. No loadDockerCard() function needed.
```

**Migration is card-by-card.** Old-style cards using `api()` continue to work alongside new-style cards using the state store. No big-bang rewrite.

### 6.4 Tab Switching

```javascript
function switchTab(tabId) {
    // ... show/hide tab DOM ...
    
    // Render all cards in this tab from current store state
    for (const key of tabCardKeys[tabId]) {
        const data = storeGet(key);
        if (data) {
            // Data available — render immediately
            for (const fn of (_renderers[key] || [])) fn(data);
        }
        // else: no data yet — SSE will deliver it, renderer will fire automatically
    }
}
```

Tab switching is instant because data is already in the store (pre-injected or received via SSE). No fetching, no loading spinners, no waiting.

---

## 7. Server-Side Implementation Details

### 7.1 EventBus (Python)

```python
import json
import logging
import queue
import threading
import time
from collections import deque

logger = logging.getLogger(__name__)


class EventBus:
    """Thread-safe, in-process pub/sub with bounded replay buffer.
    
    Thread safety model:
    - _lock protects _seq, _buffer, _subscribers (all writes)
    - Per-subscriber Queue provides thread-safe producer/consumer
    - publish() is O(N) where N = active subscribers (typically 1-3)
    - subscribe() generator runs in Flask response thread
    
    Replay model:
    - _buffer is a bounded deque (ring buffer)
    - On reconnect, client sends Last-Event-Id → server replays from buffer
    - If Last-Event-Id is too old (not in buffer), server sends full snapshot
    """
    
    def __init__(self, *, buffer_size: int = 500):
        self._lock = threading.Lock()
        self._seq = 0
        self._buffer: deque[dict] = deque(maxlen=buffer_size)
        self._subscribers: list[queue.Queue] = []
        self._instance_id = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._latest: dict[str, dict] = {}  # key → latest cache:done data (for snapshot)
    
    @property
    def instance_id(self) -> str:
        return self._instance_id
    
    def publish(self, event_type: str, *, key: str = "", data: dict | None = None, **kw) -> dict:
        """Broadcast an event to all connected SSE clients.
        
        Returns the event dict (with seq assigned).
        """
        with self._lock:
            self._seq += 1
            event = {
                "v": 1,
                "ts": time.time(),
                "seq": self._seq,
                "type": event_type,
                "key": key,
                "data": data or {},
                **kw,
            }
            self._buffer.append(event)
            
            # Track latest data per key for snapshot
            if event_type == "cache:done" and key:
                self._latest[key] = {
                    "data": data,
                    "cached_at": event["ts"],
                    "age_s": 0,
                }
            elif event_type == "cache:bust":
                scope = (data or {}).get("scope", "")
                if scope == "all":
                    self._latest.clear()
                elif scope:
                    for k in scope.split(","):
                        self._latest.pop(k.strip(), None)
            
            # Push to all subscriber queues
            dead: list[queue.Queue] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except queue.Full:
                    dead.append(q)  # subscriber not consuming — drop it
            for q in dead:
                self._subscribers.remove(q)
                logger.info("dropped dead SSE subscriber (queue full)")
        
        # Log outside the lock
        logger.debug("event: %s key=%s%s", event_type, key or "-",
                     f" ({kw['duration_s']:.2f}s)" if "duration_s" in kw else "")
        return event
    
    def subscribe(self, *, since: int = 0):
        """Yield events as dicts. Blocks on the subscriber queue.
        
        If `since` > 0 and within buffer range, replays missed events.
        If `since` is too old or 0, yields a state:snapshot first.
        """
        q: queue.Queue = queue.Queue(maxsize=200)
        need_snapshot = True
        
        with self._lock:
            if since > 0:
                # Try to replay from buffer
                min_seq = self._buffer[0]["seq"] if self._buffer else 0
                if since >= min_seq:
                    need_snapshot = False
                    for event in self._buffer:
                        if event["seq"] > since:
                            q.put_nowait(event)
            
            self._subscribers.append(q)
        
        try:
            # Always send sys:ready first
            yield self._make_ready_event()
            
            if need_snapshot:
                yield self._make_snapshot_event()
            
            # Stream events as they arrive
            while True:
                try:
                    event = q.get(timeout=30)
                    yield event
                except queue.Empty:
                    # No events for 30s — send heartbeat
                    yield self.publish("sys:heartbeat")
        finally:
            with self._lock:
                if q in self._subscribers:
                    self._subscribers.remove(q)
    
    def snapshot(self) -> dict:
        """Return current state for pre-injection into HTML."""
        with self._lock:
            now = time.time()
            result = {}
            for key, entry in self._latest.items():
                result[key] = {
                    "data": entry["data"],
                    "cached_at": entry["cached_at"],
                    "age_s": round(now - entry["cached_at"]),
                }
            return result
    
    def _make_ready_event(self) -> dict:
        with self._lock:
            self._seq += 1
            event = {
                "v": 1, "ts": time.time(), "seq": self._seq,
                "type": "sys:ready", "key": "",
                "data": {
                    "instance_id": self._instance_id,
                    "cache_keys": list(self._latest.keys()),
                },
            }
            self._buffer.append(event)
            return event
    
    def _make_snapshot_event(self) -> dict:
        with self._lock:
            self._seq += 1
            event = {
                "v": 1, "ts": time.time(), "seq": self._seq,
                "type": "state:snapshot", "key": "",
                "data": self.snapshot(),
            }
            self._buffer.append(event)
            return event


# Module-level singleton
bus = EventBus()
```

### 7.2 SSE Endpoint

```python
@events_bp.route("/events")
def event_stream():
    since = request.args.get("since", 0, type=int)
    # Also check Last-Event-Id header (EventSource sends this on reconnect)
    last_id = request.headers.get("Last-Event-Id")
    if last_id:
        since = max(since, int(last_id))
    
    def generate():
        for event in bus.subscribe(since=since):
            yield (
                f"event: {event['type']}\n"
                f"id: {event['seq']}\n"
                f"data: {json.dumps(event, default=str)}\n\n"
            )
    
    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "Connection": "keep-alive",
        },
    )
```

### 7.3 Cache Module Integration

```python
# In devops_cache.py get_cached():

def get_cached(project_root, card_key, compute_fn, *, force=False):
    from src.core.services.event_bus import bus
    
    lock = _get_key_lock(card_key)
    with lock:
        cache = _load_cache(project_root)
        entry = cache.get(card_key)
        watch = _WATCH_PATHS.get(card_key, [])
        current_mtime = _max_mtime(project_root, watch)
        
        if not force and entry:
            if current_mtime <= entry.get("mtime", 0):
                bus.publish("cache:hit", key=card_key,
                            data={"age_seconds": round(time.time() - entry["cached_at"]), "mtime": current_mtime})
                data = entry["data"]
                data["_cache"] = {...}
                return data
        
        # Miss
        reason = "forced" if force else ("expired" if entry else "absent")
        bus.publish("cache:miss", key=card_key, data={"reason": reason})
        
        t0 = time.time()
        try:
            data = compute_fn()
        except Exception as exc:
            elapsed = round(time.time() - t0, 3)
            bus.publish("cache:error", key=card_key, error=str(exc), duration_s=elapsed)
            raise
        
        elapsed = round(time.time() - t0, 3)
        # ... save to cache ...
        
        bus.publish("cache:done", key=card_key, data=data, duration_s=elapsed)
        return data
```

---

## 8. Cache Warming

### 8.1 Design

```python
def _warm_cache(app):
    """Background thread: pre-compute all card caches on server start.
    
    Non-blocking: the server accepts connections while warming runs.
    Cards warm in a controlled sequence (fast cards first, slow cards last).
    Each card publishes cache:miss → cache:done events on the SSE bus.
    """
    with app.app_context():
        root = Path(app.config["PROJECT_ROOT"])
        keys = list(_WATCH_PATHS.keys())  # all known card keys
        
        bus.publish("sys:warming", data={"keys": keys, "total": len(keys)})
        
        computed = 0
        cached = 0
        t0 = time.time()
        
        for key in keys:
            compute_fn = _CARD_COMPUTE_FNS.get(key)
            if compute_fn:
                try:
                    result = get_cached(root, key, compute_fn)
                    if result.get("_cache", {}).get("fresh"):
                        cached += 1
                    else:
                        computed += 1
                except Exception as exc:
                    logger.warning("warm %s failed: %s", key, exc)
        
        bus.publish("sys:warm", duration_s=round(time.time() - t0, 2),
                    data={"keys_computed": computed, "keys_cached": cached, "total": len(keys)})
```

### 8.2 Card Compute Function Registry

The warming thread needs to know which function computes each card. Currently this mapping is scattered across route files. We need a central registry:

```python
# In devops_cache.py (or a new registry module)

_CARD_COMPUTE_FNS: dict[str, Callable] = {}

def register_compute(key: str, fn: Callable) -> None:
    """Register the compute function for a cache key."""
    _CARD_COMPUTE_FNS[key] = fn
```

Each route file registers its compute function at import time:
```python
# In routes_docker.py
devops_cache.register_compute("docker", lambda root: docker_ops.docker_status(root))
```

### 8.3 Warm Order

Cards should warm in a controlled order: fast cards first (so the UI has data quickly), slow cards last.

Proposed order based on measured cold-cache times:
1. **Instant** (< 50ms): status, health, devops/prefs, ci, packages, git, audit
2. **Fast** (50-500ms): security, quality, capabilities
3. **Medium** (500ms-2s): docs, k8s, terraform, gh/pulls, gh/runs, gh/workflows, docker
4. **Slow** (2-7s): dns, project-status, env, testing

Warming runs sequentially (no contention), so total time ≈ sum ≈ 25-35s. But the first results are available within 50ms of server start.

---

## 9. Pre-Injection

### 9.1 Server Side

```python
@app.route("/")
def index():
    initial_state = bus.snapshot()
    return render_template("index.html",
                           initial_state=json.dumps(initial_state, default=str))
```

### 9.2 Client Side

```html
<!-- In index.html -->
<script>window.__INITIAL_STATE__ = {{ initial_state | safe }};</script>
```

```javascript
// In _globals.html — enhanced cardCached
function cardCached(key) {
    // 1. Check pre-injected state (consumed once per key)
    if (window.__INITIAL_STATE__?.[key]) {
        const entry = window.__INITIAL_STATE__[key];
        delete window.__INITIAL_STATE__[key];
        storeSet(key, entry.data);  // populate state store
        return entry.data;
    }
    // 2. Check state store (populated by SSE events)
    const storeData = storeGet(key);
    if (storeData) return storeData;
    // 3. Fall back to sessionStorage (backward compat during migration)
    const raw = sessionStorage.getItem('_cc:' + key);
    // ... existing logic ...
}
```

### 9.3 Expected Impact

| Metric | Before | After pre-injection |
|---|---|---|
| API calls on warm load | 15+ | 0 (all pre-injected) |
| Time to first content | ~500ms (fastest API response) | ~0ms (embedded in HTML) |
| HTML size increase | — | +25KB (~5KB gzipped) |
| Network requests saved | — | 15 per page load |

---

## 10. Execution Phases

| Phase | Scope | Deliverables | Risk |
|---|---|---|---|
| **7A** | Event bus + SSE endpoint | `event_bus.py`, `routes_events.py`, wire `get_cached()` to publish events | Low — additive, no existing code changes |
| **7B** | Cache warming on server start | `server.py` background thread, compute function registry | Low — fire-and-forget thread |
| **7C** | Pre-inject initial state | `server.py` index route, template `__INITIAL_STATE__` | Low — template change only |
| **7D** | Client SSE + state store | `_event_bus.html`, `_state_store.html` | Medium — requires careful migration |
| **7E** | Card migration (card by card) | Each card switches from api() to state store + SSE | Medium — incremental, testable |
| **7F** | File watcher (future) | `file_watcher.py`, inotify integration | High — OS-specific, edge cases |

**Start with 7A.** It's the foundation. Everything else is additive on top.

---

## 11. Open Design Questions (To Resolve During Implementation)

1. **Buffer size:** 500 events is ~5 minutes at peak rate. Enough for brief disconnects. Too small for overnight sleep. What's the acceptable reconnect window?

2. **Warming concurrency:** Should warming run cards sequentially (no contention, predictable) or with limited parallelism (faster total time)? Current analysis suggests sequential is better due to the 78k-file rglob contention problem.

3. **Event filtering:** Should clients be able to subscribe to specific event types or keys? (e.g., "I only care about cache:done for docker"). Simplifies client code but adds server complexity. Proposal: start with "all events to all clients," optimize later if needed.

4. **`api()` retirement timeline:** How aggressively do we migrate cards from `api()` to SSE? Proposal: keep `api()` permanently for POST actions, migrate GET-based card loads card-by-card in Phase 7E.

5. **Snapshot size threshold:** If the pre-injected state grows beyond X KB, should we lazy-load some cards? Proposal: no — 25KB is negligible. Revisit if it grows past 200KB.

6. **Cold start sequence:** If a user connects before warming is complete, they get partial pre-injection + SSE events as warming progresses. Is this acceptable UX? Proposal: yes — each card appears progressively, which is better than a blank page waiting for all 12 to finish.
