# Event System

> **12 files. 1,924 lines. Append-only event sourcing for the Timeline / History feature.**
>
> Every operation the tool performs — user actions, mediator computations,
> background builds — becomes an immutable `Event`. Events feed four
> projections that power the timeline UI: entries, chains, domains, calendar.

---

## How It Works

```
                     ┌──────────────────────────────────────────────┐
                     │              Event Sources                    │
                     │                                              │
                     │  Flask Routes    Mediator Core    Background │
                     │  (@tracked)     (core.py:535)    (emit.py)  │
                     └──────┬──────────────┬──────────────┬────────┘
                            │              │              │
                            ▼              ▼              ▼
                     ┌──────────────────────────────────────────────┐
                     │            EventStore.append()                │
                     │                                              │
                     │  1. Assign monotonic ID (evt-N)              │
                     │  2. Push to hot deque (max 5000)             │
                     │  3. Append to JSONL file (cold)              │
                     │  4. Notify subscribers (callbacks)           │
                     └──────────────────────┬───────────────────────┘
                                            │
                     ┌──────────────────────┼───────────────────────┐
                     │                      │                       │
                     ▼                      ▼                       ▼
              Hot Storage            Cold Storage            Subscribers
           deque (5000 max)      .state/events/             (callbacks)
           instant queries       YYYY-MM-DD.jsonl
                     │              (append-only)
                     │
                     ▼
              ┌──────────────────────────────────────────────┐
              │           Projections (on demand)             │
              │                                              │
              │  TimelineProjection  → entry list             │
              │  ChainProjection    → grouped by correlation  │
              │  DomainProjection   → facet counts            │
              │  CalendarProjection → per-day counts          │
              └──────────────────────┬───────────────────────┘
                                     │
                                     ▼
                          timeline.data (mediator node)
                                     │
                          merge with external adapters
                          (git_log, chat, github, ledger)
                                     │
                                     ▼
                          EventBus → cache:done → SSE → Frontend
```

### Event Lifecycle

1. **Emission** — an event source creates an `Event` with type, summary, detail, correlation_id
2. **Storage** — `EventStore.append()` assigns an ID, writes to hot + cold, notifies subscribers
3. **Projection** — when `timeline.data` is requested, projections read from the hot deque and build entries, chains, facets, calendar
4. **Delivery** — the mediator caches the result, EventBus pushes `cache:done` via SSE, frontend renders

### Three Emission Patterns

| Pattern | Where | Correlation | Timeline |
|---------|-------|-------------|----------|
| `@tracked("event.type")` | Flask routes (sync) | Auto from header or generated | Auto-invalidated |
| `emit_event(...)` | Background threads | Caller provides chain ID | Auto-invalidated |
| Mediator internal | `core.py` after resolver | Thread-local context | Not triggered (recursive) |

---

## File Map

```
events/
├── __init__.py          Package exports (21 lines)
├── models.py            Immutable Event dataclass (77 lines)
├── store.py             EventStore: hot deque + JSONL persistence (223 lines)
├── correlation.py       Thread-local correlation context (31 lines)
├── tracked.py           @tracked decorator + _EVENT_LABELS catalog (400 lines)
├── emit.py              emit_event() for background threads (89 lines)
├── enrichment.py        Mediator event type/summary/detail derivation (564 lines)
├── projections/
│   ├── __init__.py      Package marker (1 line)
│   ├── timeline.py      TimelineProjection: entries from events (213 lines)
│   ├── chains.py        ChainProjection: group by correlation_id (196 lines)
│   ├── domains.py       DomainProjection: facet counts (68 lines)
│   └── calendar.py      CalendarProjection: per-day counts (41 lines)
└── README.md            This file
```

---

## Per-File Documentation

### models.py — Event dataclass (77 lines)

The immutable core. Every event in the system is an instance of this frozen dataclass.

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `id` | `str` | `""` | Monotonic ID assigned by store (`evt-42`) |
| `ts` | `float` | 0.0 | Unix epoch timestamp |
| `type` | `str` | `""` | Dotted event type (`vault.key.added`) |
| `correlation_id` | `str` | `""` | Chain ID linking related events |
| `causation_id` | `str\|None` | `None` | ID of the event that caused this one |
| `source` | `str` | `""` | Origin system (`route`, `mediator`, `watcher`) |
| `path` | `str` | `""` | Mediator path or event type |
| `status` | `str` | `"ok"` | `"ok"`, `"error"`, `"warning"` |
| `duration_ms` | `int` | `0` | Operation duration in milliseconds |
| `summary` | `str` | `""` | Human-readable one-line summary |
| `detail` | `dict` | `{}` | Structured metadata |
| `origin` | `str` | `"system"` | `"user"` or `"system"` |
| `actor` | `str` | `"scheduler"` | `"user"`, `"automation"`, `"scheduler"` |

| Method | Returns | Purpose |
|--------|---------|---------|
| `to_dict()` | `dict` | JSON-safe serialization |
| `from_dict(d)` | `Event` | Deserialization from dict/JSONL |

### store.py — EventStore (223 lines)

Append-only log with two storage tiers:
- **Hot**: in-memory `deque(maxlen=5000)` — instant queries
- **Cold**: JSONL files per day in `.state/events/YYYY-MM-DD.jsonl`

| Method | Purpose |
|--------|---------|
| `append(event)` | Assign ID, push hot, persist cold, notify subscribers |
| `query(since_ts, types, correlation_id, limit)` | Search hot first, fall back to cold |
| `all_events()` | Return all hot events, sorted newest-first |
| `count()` | Number of events in hot cache |
| `subscribe(callback)` | Register a function called on every append |
| `load_cold(days)` | Pre-load recent JSONL into hot (startup warm-up) |

**ID assignment**: Monotonic `evt-{seq}`. Sequence counter persists across
restarts via `load_cold()` which reads max ID from cold storage.

**Thread safety**: All mutations protected by `threading.Lock()`. Persistence
happens outside the lock (non-blocking).

### correlation.py — Thread-local context (31 lines)

Links events produced by the same logical operation. Uses `threading.local()`
so each request/worker thread has its own correlation context.

| Function | Purpose |
|----------|---------|
| `set_correlation(id)` | Set active correlation ID for this thread |
| `get_correlation()` | Get active ID or `None` |
| `clear_correlation()` | Clear (call in finally blocks) |

### tracked.py — Route decorator (400 lines)

The primary way Flask route handlers emit events. Wraps the handler with
automatic context extraction, summary building, and timeline invalidation.

```python
@app.route("/vault/unlock", methods=["POST"])
@tracked("vault.unlocked")
def vault_unlock():
    ...
    return jsonify(result)
```

| Component | Lines | Purpose |
|-----------|-------|---------|
| `_EVENT_LABELS` | 40-120 | 61-entry dict: event type → human label |
| `tracked()` | 122-177 | Decorator factory |
| `_get_store()` | 180-189 | Get EventStore from mediator singleton |
| `_extract_request_context()` | 204-222 | Pull fields from request JSON body |
| `_enrich_detail()` | 225-237 | Pull fields from response JSON |
| `_humanize_event_type()` | 240-244 | Fallback label from dotted type |
| `_enrich_label()` | 247-283 | Add target/branch/key/message to label |
| `_append_error()` | 286-290 | Append error info to label |
| `_build_summary()` | 293-300 | Compose label + enrichment + error |
| `_extract_response()` | 303-314 | Extract JSON from Flask response |

**Correlation resolution order**:
1. `X-Correlation-ID` request header (frontend chains like git sync)
2. `chain_domain` tracker lookup (multi-request chains)
3. Auto-generated: `{domain}:{uuid8}`

### emit.py — Background thread utility (89 lines)

For operations that run outside Flask request context: plan executor,
test replayer, pages build stream.

```python
from src.core.services.events.emit import emit_event

emit_event(
    "pages.build.completed",
    summary="Build complete: docs — 3 stages",
    correlation_id="pages-build:a1b2c3d4",
    status="ok",
    duration_ms=5400,
    detail={"segment": "docs"},
)
```

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `event_type` | required | Dotted event type |
| `summary` | required | Human-readable summary |
| `correlation_id` | `""` | Chain ID |
| `status` | `"ok"` | `"ok"` or `"error"` |
| `duration_ms` | `0` | Operation duration |
| `detail` | `None` | Structured metadata dict |
| `invalidate_timeline` | `True` | Whether to invalidate timeline.data |

Fail-safe: catches all exceptions, logs at debug level, never raises.

### enrichment.py — Mediator event enrichment (564 lines)

Transforms raw mediator computation results into rich event data.
Called automatically by `mediator/core.py` after every resolver runs.

| Function | Purpose |
|----------|---------|
| `derive_event_type(path)` | `"devops.docker"` → `"docker.scanned"` (uses `_ACTION_MAP`, 55 entries) |
| `extract_summary(path, data)` | Path-specific human summaries. Handles posture, index, catalog, audit, docker, git, CI, env, packages, security. Falls back to `activity.py._extract_summary()` then generic. |
| `extract_result_summary(path, data)` | Structured detail dict. Path-specific extractors for 15+ node types. Returns key metrics only (not raw data). |
| `compute_delta(path, new, old)` | Before/after comparison. Returns `None` if unchanged. Specific logic for audit scores, security findings, docker, catalog, index delta. |
| `_to_dict(data)` | Dataclass/object → dict conversion utility |

**Canonical path mapping**: Uses `_path_to_card_key` imported from
`mediator/subscribers/activity.py` (single source of truth, not duplicated).

### projections/timeline.py — Entry building (213 lines)

Transforms raw events into `TimelineEntry` objects for the UI.

| Function | Purpose |
|----------|---------|
| `_derive_domain(event)` | First segment of event type (`docker.scanned` → `docker`) |
| `_derive_source(event)` | Map domain to Source enum via `_DOMAIN_SOURCE` (20 entries) |
| `_derive_subtype(event)` | Everything after first dot (`docker.scanned` → `scanned`) |
| `_map_status(status)` | `"error"` → FAILED, `"warning"` → WARNING, else OK |
| `_map_actor(event)` | `origin="user"` → USER, `"automation"` → AUTOMATION, else SCHEDULER |
| `_should_suppress(event)` | Hide internal events: `mediator.invalidated`, `timeline.*`, `detect.*`, `tabmesh.*` |

`TimelineProjection.build()` iterates all events, applies suppression,
derives fields, creates `TimelineEntry` objects, returns tagged tuples.

### projections/chains.py — Chain grouping (196 lines)

Groups events by `correlation_id` into chains. Special handling for
index cycle chains which are split by domain.

| Constant | Purpose |
|----------|---------|
| `_DOMAIN_LABELS` | 14 entries: domain → human label (`audit` → `"Audit lifecycle"`) |

| Function | Purpose |
|----------|---------|
| `_friendly_chain_name(cid, group)` | Derive human name from correlation ID pattern |

**Chain name patterns**:
| Pattern | Example | Name |
|---------|---------|------|
| `cycle-YYYYMMDD-HHMMSS:domain` | `cycle-20260316-201710:audit` | "Audit lifecycle" |
| `cycle-YYYYMMDD-HHMMSS` | `cycle-20260316-201710` | "System scan . 20:17" |
| `git-sync:*` | `git-sync:mmsmu3n7` | "Git Sync" |
| `pages-build:*` | `pages-build:a1b2c3d4` | "Pages Build" |
| `plan:*` | `plan:a1b2c3d4` | "Plan Execution" |
| `cdp_test:*` | `cdp_test:a1b2c3d4` | "Test Replay" |
| `git:branch` | `git:main` | "Branch: main" |

**Cycle chain splitting**: For `cycle-*` chains, events are grouped by
domain (via `_derive_domain`). Domains with 2+ events get their own sub-chain
(`cycle-xxx:audit`). The full cycle chain is also kept.

### projections/domains.py — Facet counts (68 lines)

Counts events by source, status, severity, and adapter (domain → subtype).
Used for the filter dropdown menus in the timeline UI.

### projections/calendar.py — Per-day counts (41 lines)

Groups events by date. Each day has a count and a `has_failure` flag.
Used for the calendar navigation tree.

---

## Dependency Graph

```
models.py              ← standalone (no internal deps)
    ↑
store.py               ← imports models.py
    ↑
correlation.py         ← standalone (threading.local only)
    ↑
emit.py                ← imports models.py, mediator (lazy)
    ↑
tracked.py             ← imports models.py, correlation.py, mediator (lazy)
    ↑
enrichment.py          ← imports activity.py (path mapping)
    ↑
projections/
├── timeline.py        ← imports models.py, store.py, timeline models
├── chains.py          ← imports timeline.py helpers
├── domains.py         ← imports timeline.py helpers
└── calendar.py        ← imports timeline.py (_should_suppress only)
```

External dependencies (outside `events/`):
- `mediator/subscribers/activity.py` → `_path_to_card_key` (canonical mapping)
- `devops/activity.py` → `_extract_summary`, `_extract_detail` (legacy card summaries)
- `timeline/models.py` → `TimelineEntry`, `Source`, `EntryStatus`, enums
- `mediator/core.py` → calls enrichment functions after resolver runs

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| **Mediator core** | `mediator/core.py` | `Event`, `get_correlation`, `enrichment.*` — emits events after computations |
| **Mediator registrations** | `registrations/__init__.py` | `EventStore`, `enrichment.*` — creates store, seeds from cache |
| **Mediator registrations** | `registrations/timeline.py` | All four projection classes — builds `timeline.data` |
| **Index watcher** | `mediator/index_watcher.py` | `set_correlation`, `clear_correlation`, `Event` — cycle lifecycle events |
| **Flask routes (51 files)** | `routes/vault/*.py`, `routes/pages/*.py`, etc. | `@tracked` decorator |
| **Pages build** | `pages/build_stream.py` | `emit_event` — build progress chain |
| **Plan executor** | `scripts/plan_executor.py` | `emit_event` — plan completion event |
| **Test replayer** | `cdp_test/replayer.py` | `emit_event` — replay completion/failure events |
| **Tool execution** | `routes/audit/tool_execution.py` | `emit_event`, `get_correlation` — install completion events |

---

## Data Shapes

### Event (stored in JSONL)

```json
{
  "id": "evt-42",
  "ts": 1710605110.52,
  "type": "vault.key.added",
  "correlation_id": "vault:a1b2c3d4",
  "causation_id": null,
  "source": "route",
  "path": "vault.key.added",
  "status": "ok",
  "duration_ms": 245,
  "summary": "Key added: API_TOKEN [prod]",
  "detail": {"key": "API_TOKEN", "env": "prod", "elapsed_ms": 245},
  "origin": "user",
  "actor": "user"
}
```

### Chain (from ChainProjection)

```json
{
  "chain_id": "pages-build:a1b2c3d4",
  "entry_count": 4,
  "first_ts": 1710605100.0,
  "last_ts": 1710605145.0,
  "summary": "Pages Build",
  "sources": ["PLATFORM"],
  "members": [
    {"id": "evt-100", "ts": 1710605100.0, "source": "PLATFORM",
     "subtype": "build.started", "status": "ok",
     "summary": "Build started: docs (mkdocs)", "chain_role": "origin"}
  ]
}
```

### Facets (from DomainProjection)

```json
{
  "by_source": {"PLATFORM": 250, "VAULT": 15, "GIT": 30},
  "by_status": {"ok": 280, "error": 15},
  "by_severity": {"none": 290, "medium": 10, "high": 3},
  "by_adapter": {
    "vault": {"unlocked": 8, "key.added": 15},
    "audit": {"scores.computed": 50}
  }
}
```

### Calendar (from CalendarProjection)

```json
[
  {"date": "2026-03-16", "count": 42, "has_failure": false},
  {"date": "2026-03-15", "count": 28, "has_failure": true}
]
```

---

## Design Decisions

### Why event sourcing?

The timeline needs to show WHAT happened, WHEN, and WHY — not just "something
computed." Events are immutable, ordered, and carry full context. This enables:
- Temporal queries ("what happened between 2pm and 3pm?")
- Causation chains ("why did posture recompute?")
- Multiple read-side projections from the same data
- No data loss — append-only means nothing is overwritten

### Why hot deque + cold JSONL (not SQLite)?

- **Hot deque**: O(1) append, instant iteration, bounded memory (~5MB)
- **JSONL**: Human-readable (`tail`, `grep`, `jq`), atomic appends, no schema
  migrations, no DB server, trivially portable
- **SQLite alternative rejected**: Adds complexity (schema, migrations, WAL mode
  tuning), no benefit at this scale (<5000 events/day), JSONL is greppable

### Why 5000 hot events?

Covers ~8 hours of moderate activity. Recent queries hit hot cache only (no disk I/O).
Memory budget: ~5MB (events are small dicts). Older events fall to cold storage.

### Why per-day JSONL files?

- Simple retention (delete files older than N days)
- Partial load at startup (`load_cold(days=7)` reads only recent files)
- Concurrent appends are safe (one writer, file-append is atomic on Linux)
- Easy manual inspection (`cat .state/events/2026-03-16.jsonl | jq`)

### Why 3 emission patterns?

- **`@tracked`**: Flask routes have request context (body, headers, response).
  The decorator extracts all of this automatically. 51 route files use it.
- **`emit_event()`**: Background threads (plan executor, test replayer, build
  stream) have no Flask context. They build summaries manually.
- **Mediator internal**: Automatic — no code needed. `core.py` calls
  `enrichment.py` after every resolver. Covers all 50+ mediator nodes.

### Why projections are on-demand?

Projections iterate the hot deque and build results. At 5000 events this takes
<10ms. The mediator caches the result (`timeline.data`, TTL=5s). No separate
materialized-view sync logic needed. Adding a new projection is one class with
a `build()` method — no schema changes, no migration.

---

## Adding New Events

### New @tracked route

1. Add `@tracked("domain.action")` to the route handler
2. Add the event type to `_EVENT_LABELS` in `tracked.py`:
   ```python
   "domain.action": "Human Label",
   ```
3. Done. Summary, detail, correlation are handled automatically.

### New background chain (like Pages Build)

1. Generate a chain ID at the start:
   ```python
   chain_id = f"domain:{uuid.uuid4().hex[:8]}"
   ```
2. Call `emit_event()` for each step with the same `correlation_id`
3. Add a friendly name pattern to `_friendly_chain_name()` in `chains.py`:
   ```python
   if cid.startswith("domain:"):
       return "Domain Operation"
   ```

### New mediator node

No event code needed. The mediator emits events automatically.
To improve the summary/detail:

1. Add to `_ACTION_MAP` in `enrichment.py`:
   ```python
   "domain.node": "domain.node.computed",
   ```
2. Add a handler in `extract_summary()` for the path
3. Optionally add to `extract_result_summary()` for structured detail

### Frontend chain linking

Pass `X-Correlation-ID` header from the frontend to link multiple
`@tracked` routes into one chain:

```javascript
const chainId = 'git-sync:' + Date.now().toString(36);
await api('/git/commit', { headers: { 'X-Correlation-ID': chainId } });
await api('/git/pull',   { headers: { 'X-Correlation-ID': chainId } });
await api('/git/push',   { headers: { 'X-Correlation-ID': chainId } });
```

---

## Event Type Naming

Format: `{domain}.{action}` or `{domain}.{noun}.{action}`

| Category | Examples |
|----------|---------|
| User actions | `vault.unlocked`, `git.committed`, `chat.message.sent` |
| Background steps | `pages.build.started`, `pages.build.stage.done`, `pages.build.completed` |
| Plan lifecycle | `plan.executed`, `plan.completed`, `plan.failed` |
| Test lifecycle | `cdp_test.replay.started`, `cdp_test.replay.completed` |
| Mediator (auto) | `docker.scanned`, `audit.scores.computed`, `posture.assessed` |
| Index lifecycle | `index.cycle.started`, `index.cycle.completed` |

## Correlation ID Conventions

| Pattern | Source | Example |
|---------|--------|---------|
| `{domain}:{uuid8}` | @tracked auto | `vault:a1b2c3d4` |
| `git-sync:{id}` | Frontend header | `git-sync:mmsmu3n7` |
| `pages-build:{uuid8}` | build_stream.py | `pages-build:a1b2c3d4` |
| `plan:{uuid8}` | plan_executor.py | `plan:a1b2c3d4` |
| `cdp_test:{uuid8}` | replayer.py | `cdp_test:a1b2c3d4` |
| `cycle-{YYYYMMDD-HHMMSS}` | index_watcher.py | `cycle-20260316-201710` |
| `cycle-{ts}:{domain}` | chains.py (derived) | `cycle-20260316-201710:audit` |

## Storage

| Tier | Location | Capacity | Access |
|------|----------|----------|--------|
| Hot | In-memory deque | 5000 events | Instant |
| Cold | `.state/events/YYYY-MM-DD.jsonl` | Unbounded | Disk read |
| Startup | `load_cold(days=7)` | Last 7 days | One-time load |
