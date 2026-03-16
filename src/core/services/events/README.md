# Event System

Append-only event sourcing for the timeline / history feature.
Every operation the tool performs becomes an immutable `Event` that
feeds the timeline UI.

## Architecture

```
User actions (routes)          Mediator computations         Background threads
       │                              │                             │
   @tracked()                  core.py → enrichment.py        emit_event()
       │                              │                             │
       ▼                              ▼                             ▼
                          EventStore.append()
                                  │
                     ┌────────────┼────────────┐
                     ▼            ▼             ▼
              hot deque       JSONL/day     subscribers
             (5000 max)     (.state/events/)   (callbacks)
                     │
                     ▼
            Projections (on demand)
            ├── TimelineProjection  → entries
            ├── ChainProjection    → chains (grouped by correlation_id)
            ├── DomainProjection   → facets (by source/status/severity/adapter)
            └── CalendarProjection → per-day counts
                     │
                     ▼
              timeline.data (mediator node)
                     │
                     ▼
              EventBus cache:done → SSE → Frontend
```

## Files

| File | Purpose |
|------|---------|
| `models.py` | Immutable `Event` dataclass (id, ts, type, correlation_id, ...) |
| `store.py` | `EventStore` — append, query, hot deque + JSONL persistence |
| `correlation.py` | Thread-local correlation context (set/get/clear) |
| `tracked.py` | `@tracked` decorator for Flask route handlers |
| `emit.py` | `emit_event()` utility for background threads |
| `enrichment.py` | Derives semantic types, summaries, details from mediator data |
| `projections/` | Read-side projections (timeline, chains, domains, calendar) |

## Three Emission Patterns

### Pattern 1: `@tracked` decorator (for Flask routes)

```python
from src.core.services.events.tracked import tracked

@app.route("/vault/unlock", methods=["POST"])
@tracked("vault.unlocked")
def vault_unlock():
    ...
    return jsonify(result)
```

The decorator handles:
- Correlation ID (from `X-Correlation-ID` header or auto-generated)
- Request context extraction (tool, env, key, branch, etc.)
- Response data extraction (ok, error, message)
- Summary building (from `_EVENT_LABELS` catalog)
- Timeline invalidation after the event

**Use when:** The operation is a synchronous Flask route handler.

### Pattern 2: `emit_event()` (for background threads)

```python
from src.core.services.events.emit import emit_event

emit_event(
    "pages.build.completed",
    summary="Build complete: docs — 3 stages (5400ms)",
    correlation_id="pages-build:abc123",
    status="ok",
    duration_ms=5400,
    detail={"segment": "docs", "stages": 3},
)
```

**Use when:** The operation runs in a background thread (plan executor,
test replayer, build stream) where there's no Flask request context.

### Pattern 3: Mediator internal (automatic)

Events are emitted automatically by `mediator/core.py` after every
node computation. The `enrichment.py` module derives the event type,
summary, detail, and delta. No manual code needed.

**You don't call this directly.** It happens when a mediator node's
resolver runs.

## Event Type Naming

Format: `{domain}.{action}` or `{domain}.{noun}.{action}`

```
vault.unlocked          — user action
git.committed           — user action
pages.build.completed   — background chain step
plan.failed             — background completion
docker.scanned          — mediator computation (auto)
audit.scores.computed   — mediator computation (auto)
index.cycle.started     — lifecycle event
```

## Correlation ID Conventions

Correlation IDs link related events into chains.

| Pattern | Source | Example |
|---------|--------|---------|
| `{domain}:{uuid8}` | @tracked (auto) | `vault:a1b2c3d4` |
| `git-sync:{id}` | Frontend header | `git-sync:mmsmu3n7` |
| `pages-build:{uuid8}` | build_stream.py | `pages-build:a1b2c3d4` |
| `plan:{uuid8}` | plan_executor.py | `plan:a1b2c3d4` |
| `cdp_test:{uuid8}` | replayer.py | `cdp_test:a1b2c3d4` |
| `cycle-{YYYYMMDD-HHMMSS}` | index_watcher.py | `cycle-20260316-201710` |

Frontend can pass `X-Correlation-ID` header to chain multiple
`@tracked` routes into one chain (e.g., git sync: commit → pull → push).

## Adding a New Tracked Route

1. Add `@tracked("domain.action")` to the route
2. Add the event type to `_EVENT_LABELS` in `tracked.py`
3. Done — summary, detail, correlation are handled automatically

## Adding a New Background Chain

1. Generate a correlation ID: `chain_id = f"domain:{uuid.uuid4().hex[:8]}"`
2. Call `emit_event()` for each step with the same `correlation_id`
3. Add a friendly name pattern to `_friendly_chain_name()` in `projections/chains.py`

## Adding a New Mediator Node

No event code needed. The mediator automatically emits events for every
computation. To improve the summary/detail quality:

1. Add the path to `_ACTION_MAP` in `enrichment.py` (semantic event type)
2. Add a path-specific handler in `extract_summary()` (human summary)
3. Optionally add to `extract_result_summary()` (structured detail)

## Storage

- **Hot:** In-memory deque, max 5000 events (instant access)
- **Cold:** JSONL files per day in `.state/events/YYYY-MM-DD.jsonl`
- **Startup:** `load_cold(days=7)` pre-loads recent history into hot cache
- **IDs:** Monotonic `evt-{seq}` assigned by the store
