# M1 Timeline Infrastructure Refactor

> Status: PLAN — awaiting user approval before execution
>
> Problem: The timeline's 23 mediator nodes bypass the proven double-cache
> pattern used by every other domain. This causes data inconsistencies
> (counts from one population, entries from another), cold starts, and
> fragile frontend wiring. The bugs are not surface issues — they are
> symptoms of missing infrastructure.

---

## What is broken (root causes, not symptoms)

### 1. Not in the tier system

`config.py` defines `TIER_PATHS` and `TIER_PREFIXES` — the work queue
dispatch map. Every working domain is registered here. Timeline has
**zero entries**. All 23 `timeline.*` paths fall through to the
`"T4:index"` fallback in `tier_for_path()`. The index watcher and work
queue don't know they exist as a distinct workload.

### 2. `persist=False` on all 23 nodes

Every working domain card uses `persist=True`. This writes a disk shard
to `.state/mediator_index/<path>.json` after each computation. On server
restart, `hydrate_cache()` loads these shards into `_cache` — warm start,
instant `peek()`, zero-cost page injection.

Timeline has `persist=False` on every node. No disk shards. No warm start.
Every server restart means cold cache. `peek()` returns `None`. No
`__INITIAL_STATE__` injection possible.

### 3. Not in `_KEY_TO_MEDIATOR`

`server.py` defines `_KEY_TO_MEDIATOR` — the map of cache keys to mediator
paths used by the context processor to inject data into `__INITIAL_STATE__`.
Every working card has an entry here. Timeline has none.

Without this, the frontend cannot use `storeGet()` for instant first paint.
It must make HTTP requests on every page load.

### 4. Frontend bypasses the store protocol

Every working card follows this pattern:

```
storeRegister(key, renderFn)     // register for live updates
storeGet(key)                    // read from __INITIAL_STATE__-hydrated store
  → if hit: renderFn(data)       // instant render, zero API calls
  → if miss: api(endpoint)       // fallback
SSE cache:done → storeSet(key)   // live updates via proven path
```

Timeline does none of this. It uses raw `api()` calls to 4 separate
endpoints (`/timeline`, `/timeline/chains`, `/timeline/domains`,
`/timeline/calendar`), each hitting different mediator nodes with
different TTLs. The SSE path uses a custom `timeline:entry` event
instead of the standard `cache:done` → `storeSet` flow.

### 5. 23 nodes with mismatched TTLs = guaranteed inconsistency

`timeline.view.recent` (TTL=30s) and `timeline.view.stats` (TTL=300s)
both call `_get_entries(mediator, _ALL_SOURCES)` independently. Between
30s and 300s they can return data from different source snapshots. This
is the root cause of the "counts say X but list shows Y" bugs.

Working domains avoid this by having a single aggregate node (e.g.,
`devops.status`) that derives everything from one computation, or by
having derived nodes depend on the parent node (not re-fetch sources).

---

## Target architecture

Follow the proven pattern. One aggregate node for the UI. Source nodes
stay as raw data readers. Feed nodes stay for downstream milestones.

### Node structure (target)

```
SOURCE NODES (6) — keep as-is, they are raw data readers
  timeline.source.scan_activity   (mtime-watched)
  timeline.source.cli_ops         (mtime-watched)
  timeline.source.git_log         (TTL=60s)
  timeline.source.ledger_runs     (TTL=120s)
  timeline.source.ledger_audits   (TTL=120s)
  timeline.source.chat            (TTL=120s)

AGGREGATE NODE (1) — NEW, replaces 10 view nodes
  timeline.data                   (TTL=30s, persist=True)
    depends_on: all 6 source nodes
    resolver: single computation that produces:
      {
        entries: [...],           // ALL entries, newest-first (no time filter)
        facets: {
          by_source:   {git: 47, audit: 12, ...},
          by_status:   {ok: 40, warning: 5, failed: 2, ...},
          by_severity: {none: 38, medium: 2, critical: 1, ...},
        },
        chains: [...],            // chain summaries for left nav
        calendar: [...],          // per-day counts for calendar nav
      }

FEED NODES (7) — keep as-is, they serve downstream M2-M5
  timeline.feed.security_posture  (depends_on: timeline.data)
  timeline.feed.pkg_health        (depends_on: timeline.data)
  timeline.feed.tool_lifecycle    (depends_on: timeline.data)
  timeline.feed.stack_health      (depends_on: timeline.data)
  timeline.feed.readiness         (depends_on: timeline.data)
  timeline.feed.changelog         (depends_on: timeline.data)
  timeline.feed.notifications     (depends_on: timeline.data)
```

**Total: 6 source + 1 aggregate + 7 feed = 14 nodes (was 23)**

The 10 view nodes (`view.recent`, `view.today`, `view.week`, etc.) are
removed. Their filtering logic (time range, locality, status) moves to
the `TimelineService.query()` method which applies filters in-memory
on the single `timeline.data` entry set. This is what the service
already does — the view nodes were redundant pre-filters.

### Tier registration

Add to `config.py`:

```python
TIER_PREFIXES = {
    ...
    "T5:aggregate": ["posture.", "timeline."],
}
```

Timeline sources and feeds classified by prefix → `T5:aggregate`.
This puts them in the work queue at the right priority.

### Page injection

Add to `server.py` `_KEY_TO_MEDIATOR`:

```python
"timeline": "timeline.data",
```

This enables:
- `peek("timeline.data")` in context processor
- `__INITIAL_STATE__["timeline"]` in page HTML
- `storeGet("timeline")` in frontend — instant first paint

### Frontend refactor

Replace the 4 separate `api()` calls with the store pattern:

```js
storeRegister('timeline', _tlOnData);

function _tlInit() {
  const data = storeGet('timeline');
  if (data) {
    _tlOnData(data);
  } else {
    // cold start fallback — fetch once
    api('/timeline/data').then(d => { storeSet('timeline', d); });
  }
}

function _tlOnData(data) {
  // data.entries, data.facets, data.chains, data.calendar
  // all from ONE object, guaranteed consistent
  _tlState.allEntries  = data.entries;
  _tlState.navChains   = data.chains;
  _tlState.navCalendar = data.calendar;

  // Build filter menus from facets (always consistent)
  _tlBuildSourceMenu(data.facets.by_source);
  _tlBuildStatusMenu(data.facets.by_status);
  _tlBuildSeverityMenu(data.facets.by_severity);

  // Apply current filters client-side and render
  _tlApplyFiltersAndRender();
}
```

Filtering and pagination happen client-side on `_tlState.allEntries`.
The server `/api/timeline` endpoint remains for advanced queries
(deep pagination, date ranges beyond what's in the aggregate).

SSE live updates arrive via the standard `cache:done` event with
`key: "timeline"` → `storeSet("timeline", data)` → `_tlOnData(data)`
→ UI re-renders with fresh consistent data.

### API route changes

Add one new thin route:

```
GET /api/timeline/data → returns timeline.data from mediator
```

The existing `/api/timeline` (paginated query) stays for backward compat
and advanced use cases. But the primary UI path uses the store, not this
endpoint.

---

## Execution order

Each step must be verified working before the next begins.

### Step 1 — Aggregate node + persist + tier

- Add `timeline.data` node in `registrations/timeline.py`
  - `persist=True`, `TTL=30`, `depends_on=_ALL_SOURCES`
  - Single resolver that produces `{entries, facets, chains, calendar}`
- Remove the 10 `timeline.view.*` nodes
- Update feed nodes to `depends_on=["timeline.data"]`
- Add `"timeline."` to `TIER_PREFIXES["T5:aggregate"]` in `config.py`

**Done when:** `mediator.get("timeline.data")` returns the full object.
Disk shard appears at `.state/mediator_index/timeline.data.json`.

### Step 2 — Page injection

- Add `"timeline": "timeline.data"` to `_KEY_TO_MEDIATOR` in `server.py`

**Done when:** `window.__INITIAL_STATE__.timeline` is present in page HTML.

### Step 3 — API route

- Add `GET /api/timeline/data` that returns `mediator.get("timeline.data")`
- Keep existing `/api/timeline` for advanced queries

**Done when:** `curl /api/timeline/data` returns the full object.

### Step 4 — Frontend store integration

- `storeRegister('timeline', _tlOnData)`
- `_tlInit()` reads from `storeGet('timeline')` first
- `_tlOnData(data)` receives the single consistent object
- Filter menus built from `data.facets`
- Entry list filtered/paginated client-side
- Remove separate `api('/timeline/chains')`, `api('/timeline/domains')`,
  `api('/timeline/calendar')` calls from `_tlNavLoad`

**Done when:** Timeline tab renders from store data. No separate API calls.
Filter counts match entry list. Selecting any filter works correctly.

### Step 5 — SSE integration

- Verify `cache:done` fires with `key: "timeline"` when `timeline.data`
  recomputes (this should happen automatically via the eventbus bridge)
- `storeSet("timeline", data)` → `_tlOnData(data)` → live re-render
- Remove the custom `timeline:entry` SSE handler if it becomes redundant

**Done when:** Changing a source file (e.g., `.state/audit_activity.json`)
triggers a live update in the browser without manual refresh.

### Step 6 — Cleanup

- Remove the `TimelineService.stats()`, `.domains()`, `.calendar()`
  methods if they are no longer called
- Remove `/api/timeline/stats`, `/api/timeline/domains`,
  `/api/timeline/calendar` routes if they are no longer called
- Update `TimelineService.query()` to read from `timeline.data`
  instead of `_pick_view_path()`
- Remove dead `_resolve_*` functions from registrations

**Done when:** No orphan code. All tests pass.

---

## What this does NOT change

- Source adapters (6) — untouched, they are correct
- Feed nodes (7) — kept for M2-M5, only dependency updated
- `TimelineEntry` model — untouched
- `TimelineQuery` model — untouched
- The `/api/timeline` paginated query endpoint — kept for advanced use
- Chain rendering, scroll observer, resize handle — untouched

---

## Risks

- **Data size**: If `timeline.data.entries` is very large (thousands),
  injecting it into `__INITIAL_STATE__` could bloat the page HTML.
  Mitigation: cap entries at a reasonable limit (e.g., last 30 days or
  500 entries) in the aggregate resolver. Deep history stays accessible
  via the `/api/timeline` paginated endpoint.

- **Client-side filtering performance**: If entries exceed ~1000,
  client-side filter/sort may lag. Mitigation: the aggregate caps the
  entry count. For large datasets, the paginated API takes over.
