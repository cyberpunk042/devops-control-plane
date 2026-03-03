# Events Routes — Server-Sent Events (SSE) Real-Time Stream API

> **1 file · 70 lines · 1 endpoint · Blueprint: `events_bp` · Prefix: `/api`**
>
> Single SSE endpoint that connects clients to the global EventBus
> (`src.core.services.event_bus`, 361 lines). Provides real-time push
> of cache lifecycle events, system status, and state snapshots.
> Supports reconnection with `Last-Event-Id`-based replay from a
> bounded ring buffer (500 events), automatic state snapshots for
> new or stale clients, heartbeat keep-alive when idle (30s interval),
> and backpressure handling (drops unresponsive subscribers).

---

## How It Works

### Full Connection Lifecycle

```
Browser
│
├── EventSource("/api/events")               ← initial connection
│   └── (no Last-Event-Id header)
│
│   OR
│
├── EventSource("/api/events")               ← reconnection
│   └── Last-Event-Id: 47                      (set automatically)
│
└── GET /api/events?since=0
     │
     ▼
routes/events/__init__.py  (70 lines)
     │
     ├── Parse reconnection state:
     │   ├── since = ?since query param (default: 0)
     │   ├── Last-Event-Id header (from EventSource reconnect)
     │   └── since = max(query_since, last_event_id)
     │
     └── bus.subscribe(since=since)            ← blocking generator
         │
         ▼
core/services/event_bus.py  (361 lines)
     │
     ├── Phase 1: Connection Setup
     │   ├── Create per-client queue (maxsize=200)
     │   │
     │   ├── Replay Decision:
     │   │   ├── since > 0 AND within buffer range?
     │   │   │   └── YES → replay missed events (seq > since)
     │   │   │              (incremental catch-up)
     │   │   │
     │   │   └── since == 0 OR buffer exhausted?
     │   │       └── YES → send full state:snapshot
     │   │                  (all latest cache:done payloads)
     │   │
     │   └── Register subscriber queue
     │
     ├── Phase 2: Initial Handshake
     │   ├── yield sys:ready event
     │   │   { instance_id, cache_keys }
     │   │
     │   └── yield state:snapshot (if needed)
     │       { docker: {data, cached_at, age_s}, ... }
     │
     ├── Phase 3: Live Streaming
     │   └── while True:
     │       ├── Wait on queue (timeout = 30s)
     │       │
     │       ├── Event received → yield event
     │       │   SSE format:
     │       │     event: cache:done
     │       │     id: 47
     │       │     data: {"v":1,"ts":...,"seq":47,...}
     │       │
     │       └── Timeout (no events for 30s) →
     │           yield sys:heartbeat (keep connection alive)
     │
     └── Phase 4: Cleanup (finally block)
         └── Remove subscriber queue on disconnect
```

### Event Flow: Cache Lifecycle

```
Cache recomputation triggers event publishing:

devops_cache.recompute(root, "docker")
     │
     ├── bus.publish("cache:start", key="docker")
     │   → event: cache:start
     │   → id: 44
     │
     ├── docker_ops.docker_status(root)  ... (takes 2.5s)
     │
     ├── bus.publish("cache:done", key="docker",
     │              data={...status_dict...}, duration_s=2.51)
     │   → event: cache:done
     │   → id: 45
     │
     └── (if error):
         bus.publish("cache:error", key="docker", error="...")
         → event: cache:error
         → id: 46
```

### Event Flow: Cache Bust with Snapshot Invalidation

```
POST /api/devops/cache/bust  { card: "all" }
     │
     ▼
bus.publish("cache:bust", data={"scope": "all"})
     │
     ├── Push to all subscriber queues
     │
     └── Internal: self._latest.clear()
         (next connecting client gets empty snapshot
          instead of stale data)

POST /api/devops/cache/bust  { card: "docker" }
     │
     ▼
bus.publish("cache:bust", data={"scope": "docker"})
     │
     └── Internal: self._latest.pop("docker", None)
```

### SSE Wire Format

```
For each event yielded by subscribe(), the route formats:

    event: {event_type}\n
    id: {seq}\n
    data: {json_payload}\n\n

Example:

    event: cache:done
    id: 47
    data: {"v":1,"ts":1739648400.123,"seq":47,"type":"cache:done","key":"docker","data":{...}}

    event: sys:heartbeat
    id: 48
    data: {"v":1,"ts":1739648430.0,"seq":48,"type":"sys:heartbeat","key":"","data":{}}
```

### Reconnection with Replay

```
Client connected, receives events seq 40-50, then disconnects.

─── time ──→

Client online:     seq 40 · 41 · 42 · ... · 50
                                                    ← disconnect
Server continues:                              51 · 52 · 53 · 54
                                                    ← reconnect
Client reconnects: Last-Event-Id: 50

subscribe(since=50):
  1. Check buffer: is seq 50 still in buffer?
     ├── YES (buffer has seq 10-54):
     │   replay seq 51, 52, 53, 54
     │   then live stream from seq 55+
     │
     └── NO (buffer only has seq 200-554):
         send state:snapshot (full current state)
         then live stream from current seq+
```

---

## File Map

```
routes/events/
├── __init__.py     70 lines — blueprint + SSE endpoint
└── README.md                — this file
```

Core bus implementation: `core/services/event_bus.py` (361 lines).

---

## Per-File Documentation

### `__init__.py` — Blueprint + SSE Endpoint (70 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `event_stream()` | GET | `/events` | SSE stream to browser |

**Full implementation:**

```python
@events_bp.route("/events")
def event_stream():
    """SSE endpoint — streams events to the browser."""

    # 1. Parse reconnection state
    since = request.args.get("since", 0, type=int)
    last_event_id = request.headers.get("Last-Event-Id")
    if last_event_id is not None:
        try:
            since = max(since, int(last_event_id))
        except (ValueError, TypeError):
            pass

    # 2. Generator that yields SSE-formatted events
    def generate():
        for event in bus.subscribe(since=since):
            yield (
                f"event: {event['type']}\n"
                f"id: {event['seq']}\n"
                f"data: {json.dumps(event, default=str)}\n\n"
            )

    # 3. Response with SSE headers
    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
```

**Three response headers and why each matters:**

| Header | Value | Purpose |
|--------|-------|---------|
| `Cache-Control` | `no-cache, no-store, must-revalidate` | Prevent any proxy/browser caching of the stream |
| `X-Accel-Buffering` | `no` | Disable nginx/reverse-proxy buffering so events arrive immediately |
| `Connection` | `keep-alive` | Keep TCP connection open for continuous streaming |

---

## Dependency Graph

```
__init__.py (routes)
└── event_bus.bus            ← global singleton (eager import)
    │
    ├── threading.Lock       ← thread safety for all shared state
    ├── collections.deque    ← bounded ring buffer (maxlen=500)
    ├── queue.Queue          ← per-subscriber message queue (maxsize=200)
    ├── time                 ← timestamps, boot ID
    └── logging              ← connection/event logging
```

**EventBus internals (361 lines):**

```
EventBus
├── Properties:
│   ├── instance_id    — server boot timestamp (reconnect detection)
│   ├── seq            — monotonic sequence counter
│   └── subscriber_count — active SSE connections
│
├── Listener management (internal consumers):
│   ├── add_listener(q)    — register queue (trace recorder, etc.)
│   └── remove_listener(q) — unregister queue (idempotent)
│
├── Publishing:
│   └── publish(event_type, key=, data=, **kw)
│       ├── Assign seq, ts, v=1
│       ├── Append to ring buffer
│       ├── Track _latest for cache:done events
│       ├── Clear _latest on cache:bust (scoped or all)
│       ├── Push to all subscriber queues
│       └── Drop unresponsive subscribers (queue.Full)
│
├── Subscribing:
│   └── subscribe(since=0, heartbeat_interval=30.0)
│       ├── Create per-client queue
│       ├── Attempt replay from buffer (since > 0)
│       ├── Fallback to state:snapshot
│       ├── Yield sys:ready
│       ├── Yield state:snapshot (if needed)
│       ├── Yield events as they arrive
│       ├── Yield sys:heartbeat on idle timeout
│       └── Cleanup on disconnect (finally)
│
├── Snapshot:
│   └── snapshot() → { key: {data, cached_at, age_s} }
│
└── Module singleton:
    bus = EventBus()
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `events_bp`, registers at `/api` prefix |
| Event stream | `scripts/_event_stream.html` | `EventSource("/api/events")` — primary consumer |
| Chat | `scripts/content/_chat.html` | Monitors events for chat-related state |
| K8s | `scripts/integrations/_k8s.html` | K8s-specific event handling |
| Debugging | `scripts/_debugging.html` | Shows live event stream for debugging |
| Cache system | `core/services/devops/cache.py` | Publishes `cache:start`, `cache:done`, `cache:error` |
| Trace recorder | `core/services/trace/recorder.py` | Internal listener via `add_listener()` |

---

## Event Type Catalogue

| Event Type | Key | Published By | Purpose |
|-----------|-----|-------------|---------|
| `sys:ready` | — | EventBus (per-client) | Handshake: instance_id, available cache keys |
| `sys:heartbeat` | — | EventBus (idle timer) | Keep-alive during inactivity (30s) |
| `state:snapshot` | — | EventBus (per-client) | Full state for new/stale clients |
| `cache:start` | cache key | devops/cache | Recomputation started |
| `cache:done` | cache key | devops/cache | Recomputation complete with data payload |
| `cache:error` | cache key | devops/cache | Recomputation failed |
| `cache:bust` | — | devops/cache | Cache invalidated (scope in data) |

---

## Data Shapes

### Message Standard (v1)

Every event follows this schema:

```json
{
    "v": 1,
    "ts": 1739648400.123,
    "seq": 47,
    "type": "cache:done",
    "key": "docker",
    "data": {}
}
```

| Field | Type | Stability | Description |
|-------|------|-----------|-------------|
| `v` | int | Immutable | Schema version (always 1) |
| `ts` | float | Immutable | Server timestamp (epoch seconds) |
| `seq` | int | Immutable | Monotonically increasing sequence |
| `type` | string | Stable | Event type (`<domain>:<action>` format) |
| `key` | string | Stable | Resource identifier (cache key, etc.) |
| `data` | dict | Varies | Event-specific payload |

Optional fields: `error` (string), `duration_s` (float), `meta` (dict).

### `sys:ready` event

```json
{
    "v": 1,
    "ts": 1739648400.0,
    "seq": 1,
    "type": "sys:ready",
    "key": "",
    "data": {
        "instance_id": "2026-03-02T10:00:00",
        "cache_keys": ["audit", "ci", "dns", "docker", "docs", "k8s", "testing"]
    }
}
```

### `state:snapshot` event

```json
{
    "v": 1,
    "ts": 1739648400.5,
    "seq": 2,
    "type": "state:snapshot",
    "key": "",
    "data": {
        "docker": {
            "data": {
                "installed": true,
                "version": "24.0.7",
                "daemon_running": true
            },
            "cached_at": 1739648390.0,
            "age_s": 10
        },
        "ci": {
            "data": {
                "provider": "github",
                "workflows": 3
            },
            "cached_at": 1739648380.0,
            "age_s": 20
        }
    }
}
```

### `cache:start` event

```json
{
    "v": 1,
    "ts": 1739648400.123,
    "seq": 44,
    "type": "cache:start",
    "key": "docker",
    "data": {}
}
```

### `cache:done` event

```json
{
    "v": 1,
    "ts": 1739648402.634,
    "seq": 45,
    "type": "cache:done",
    "key": "docker",
    "data": {
        "installed": true,
        "version": "24.0.7",
        "daemon_running": true,
        "has_dockerfile": true,
        "has_compose": true
    },
    "duration_s": 2.51
}
```

### `cache:error` event

```json
{
    "v": 1,
    "ts": 1739648402.0,
    "seq": 46,
    "type": "cache:error",
    "key": "docker",
    "data": {},
    "error": "Docker daemon not responding: timeout after 10s"
}
```

### `cache:bust` event

```json
{
    "v": 1,
    "ts": 1739648500.0,
    "seq": 50,
    "type": "cache:bust",
    "key": "",
    "data": {
        "scope": "docker"
    }
}
```

### `sys:heartbeat` event

```json
{
    "v": 1,
    "ts": 1739648430.0,
    "seq": 48,
    "type": "sys:heartbeat",
    "key": "",
    "data": {}
}
```

---

## Advanced Feature Showcase

### 1. Reconnection with Incremental Replay

The route honors `Last-Event-Id` for seamless reconnection:

```python
# EventSource sends this header automatically on reconnect
last_event_id = request.headers.get("Last-Event-Id")
if last_event_id is not None:
    try:
        since = max(since, int(last_event_id))
    except (ValueError, TypeError):
        pass
```

The bus then replays missed events from its ring buffer:

```python
if since > 0 and self._buffer:
    min_seq = self._buffer[0]["seq"]
    if since >= min_seq:
        # Replay events with seq > since
        for event in self._buffer:
            if event["seq"] > since:
                q.put_nowait(event)
```

If the buffer has been exhausted (client was away too long),
a full `state:snapshot` is sent instead.

### 2. Bounded Ring Buffer

```python
self._buffer: deque[dict] = deque(maxlen=500)
```

The `deque` with `maxlen=500` automatically evicts oldest events
when new ones are published. This provides O(1) append and bounded
memory usage regardless of server uptime.

### 3. Backpressure: Drop Unresponsive Subscribers

```python
dead: list[queue.Queue[dict]] = []
for q in self._subscribers:
    try:
        q.put_nowait(event)
    except queue.Full:
        dead.append(q)
for q in dead:
    self._subscribers.remove(q)
```

If a client can't consume events fast enough (queue reaches 200),
it's silently dropped. This prevents one slow client from blocking
the entire publish path.

### 4. Per-Client vs Broadcast Events

Two event types are NOT broadcast — they're created per-client:

```python
# sys:ready — unique per connecting client (not in buffer)
def _make_ready_event(self):
    # Don't append to buffer — sys:ready is per-client

# state:snapshot — unique per connecting client (not in buffer)
def _make_snapshot_event(self):
    # Don't append to buffer — snapshot is per-client
```

All other events (cache:done, cache:start, etc.) go through
`publish()` and are both broadcast AND stored in the buffer.

### 5. Latest-State Tracking for Snapshots

```python
# On cache:done: remember the latest payload
if event_type == "cache:done" and key:
    self._latest[key] = {
        "data": data,
        "cached_at": event["ts"],
    }

# On cache:bust: clear tracked state
elif event_type == "cache:bust":
    scope = (data or {}).get("scope", "")
    if scope == "all":
        self._latest.clear()
```

This `_latest` dict enables the `state:snapshot` event to contain
the current state without re-reading from cache. It's updated
on every `cache:done` and cleared on `cache:bust`.

### 6. Heartbeat Keep-Alive

```python
while True:
    try:
        event = q.get(timeout=heartbeat_interval)  # 30s
        yield event
    except queue.Empty:
        yield self.publish("sys:heartbeat")
```

If no events arrive for 30 seconds, a heartbeat is published.
This prevents proxies (nginx, CloudFlare) from closing the
connection due to inactivity timeout.

### 7. X-Accel-Buffering Header

```python
headers={
    "X-Accel-Buffering": "no",
}
```

Nginx (and many reverse proxies) buffer upstream responses by
default. This header tells nginx to disable buffering for this
response, ensuring events are pushed to the client immediately
instead of being batched.

---

## Design Decisions

### Why a single-endpoint package

70 lines, 1 endpoint. The package exists as a directory for
consistency with every other route domain. The heavy lifting is
in `event_bus.py` (361 lines), which is used both by this route
and by internal consumers (trace recorder, cache system).

### Why GET not WebSocket

SSE (Server-Sent Events) over GET is chosen over WebSocket because:
1. **Unidirectional** — the client only receives, never sends events
2. **Auto-reconnect** — EventSource has built-in reconnection with
   `Last-Event-Id` replay, which WebSocket requires manual implementation
3. **HTTP-native** — works through proxies, CDNs, load balancers without
   special WebSocket upgrade handling
4. **Simpler** — no handshake protocol, no frame encoding

### Why `default=str` in json.dumps

```python
f"data: {json.dumps(event, default=str)}\n\n"
```

Event payloads may contain `datetime`, `Path`, or other non-serializable
types. Using `default=str` as a fallback serializer prevents crashes
while producing reasonable human-readable output.

### Why the bus is a module-level singleton

```python
bus = EventBus()
```

All consumers (route endpoint, cache system, trace recorder) need
the same bus instance. A module-level singleton avoids dependency
injection complexity while remaining importable from anywhere.

### Why subscriber queue size is 200 (not unbounded)

An unbounded queue would let a frozen client consume server memory
indefinitely. The 200-event cap means a client must process events
within ~200 cache cycles before being dropped. At normal cache
frequency (5-10 events/minute), this gives ~20 minutes of slack.

### Why heartbeat is published (not just yielded)

```python
yield self.publish("sys:heartbeat")
```

The heartbeat goes through `publish()` which assigns a `seq` number.
This means the heartbeat `id` in SSE advances the `Last-Event-Id`,
so reconnecting after a quiet period works correctly without
triggering unnecessary replays.

---

## Coverage Summary

| Capability | Endpoint | Method | Mechanism |
|-----------|----------|--------|-----------|
| Live event stream | `/events` | GET | SSE (text/event-stream) |
| Reconnection replay | `/events` | GET | `Last-Event-Id` + ring buffer |
| State snapshot | `/events` | GET | Automatic for new/stale clients |
| Heartbeat keep-alive | `/events` | GET | Every 30s idle |
