# Event System Audit — Full Report

## Architecture Overview

```
User actions (routes)          Mediator computations          Background threads
       │                              │                              │
   @tracked()                  core.py:535                    direct append()
       │                     (enrichment.py)                  (plan_executor,
       ▼                          │                            replayer,
  tracked.py                      ▼                            build_stream)
  _build_summary()          EventStore.append()                    │
  _enrich_detail()                │                                ▼
       │                          ├─→ hot deque (5000)       EventStore.append()
       ▼                          ├─→ JSONL on disk
  EventStore.append()             └─→ subscribers
       │
       ▼
  timeline.data recompute
       │
       ├─→ TimelineProjection  (entries)
       ├─→ ChainProjection     (chains)
       ├─→ DomainProjection    (facets)
       ├─→ CalendarProjection  (calendar)
       └─→ External adapters   (git_log, chat, github)
              │
              ▼
         EventBus cache:done → SSE → Frontend
```

---

## File Inventory

| File | Lines | Functions | Purpose |
|------|-------|-----------|---------|
| `events/__init__.py` | 22 | 0 | Package exports |
| `events/models.py` | 78 | 2 (to_dict, from_dict) | Event dataclass |
| `events/store.py` | 224 | 9 | Hot deque + JSONL persistence |
| `events/correlation.py` | 32 | 3 | Thread-local correlation context |
| `events/tracked.py` | 362 | 7 | @tracked decorator for routes |
| `events/enrichment.py` | 600 | 5 | Mediator event summaries + details |
| `projections/timeline.py` | 213 | 7 + 1 class | Entry building from events |
| `projections/chains.py` | 196 | 2 + 1 class | Chain grouping by correlation |
| `projections/domains.py` | 68 | 0 + 1 class | Facet counting |
| `projections/calendar.py` | 41 | 0 + 1 class | Per-day counts |

---

## Issue 1: Duplicated `_path_to_card_key` mapping

**Same dict in 2 files:**
- `enrichment.py:20-47` — 33 entries, inline dict
- `activity.py:29-75` — canonical version (47 entries)
- `eventbus_bridge.py:82-85` — correctly delegates to activity.py

**Impact:** Adding a new mediator node requires updating 2 places.

**Fix:** Delete `enrichment.py`'s `_MAP` dict, import from activity.py like eventbus_bridge does.

---

## Issue 2: Two separate summary systems

**tracked.py** builds summaries for route/user operations:
- `_build_summary()` — 108 lines, hardcoded `_LABELS` dict with 45 entries
- Input: event_type string + request context dict
- Pattern: `"vault.key.added"` → `"Key added: API_TOKEN [production]"`

**enrichment.py** builds summaries for mediator computations:
- `extract_summary()` — 167 lines, path-specific handlers
- Input: mediator path + resolver result data
- Pattern: `"devops.docker"` + data → `"Docker: 3 containers, compose active"`

**These are legitimately different** — different inputs, different events. But they share:
- Dataclass-to-dict conversion logic (duplicated in both)
- Error message truncation patterns
- Fallback strategies

**Fix:** Extract shared utilities (dataclass conversion, truncation). Keep the two summary functions separate since their inputs differ.

---

## Issue 3: Oversized functions

| Function | File | Lines | Issue |
|----------|------|-------|-------|
| `wrapper()` | tracked.py:52-176 | 125 | Entire decorator body — does context extraction, response parsing, event building, timeline recompute |
| `_build_summary()` | tracked.py:240-347 | 108 | 45-entry label dict + 8 context enrichment branches |
| `extract_summary()` | enrichment.py:122-288 | 167 | 20+ path-specific handlers in one function |
| `extract_result_summary()` | enrichment.py:293-526 | 234 | 15+ path-specific detail extractors in one function |
| `compute_delta()` | enrichment.py:531-599 | 69 | 6 path-specific delta comparators |
| `ChainProjection.build()` | chains.py:99-196 | 98 | Chain grouping + cycle splitting + member building |
| `_resolve_data()` | registrations/timeline.py:245-355 | 111 | Merge event store + external adapters + chains + facets |

**Fix:** Break into smaller functions. The label dict should be a module-level constant, not buried inside `_build_summary()`.

---

## Issue 4: Inconsistent event emission patterns

### Pattern A: @tracked decorator (193 routes)
```python
@tracked("vault.key.added")
def add_key():
    return jsonify(result)
```
- Auto correlation ID
- Request context extraction
- Response data extraction
- Timeline recompute after

### Pattern B: Direct append with helper (pages/build_stream.py)
```python
_emit_event("pages.build.started", chain_id, summary, detail)
```
- Manual correlation ID
- Manual summary
- Dedicated helper function
- Timeline recompute at end only

### Pattern C: Direct append inline (plan_executor.py, replayer.py)
```python
m._event_store.append(Event(
    id="", ts=_time.time(),
    type="plan.completed",
    correlation_id=f"plan:{run_id[:8]}",
    ...
))
```
- Manual everything
- Hardcoded correlation pattern
- Copy-pasted structure across files

### Pattern D: Mediator internal (core.py)
```python
self._event_store.append(Event(
    type=_evt_type,
    correlation_id=get_correlation() or "",
    source="mediator",
    ...
))
```
- Uses enrichment.py for type/summary/detail
- Uses thread-local correlation context
- No timeline recompute (would be recursive)

**Fix:** Standardize B and C. Create a single `emit_event()` utility that handles correlation, timeline invalidation, and try/except. Pattern D (mediator internal) stays separate.

---

## Issue 5: Scattered hardcoded catalogs

| Catalog | File | Lines | Entries |
|---------|------|-------|---------|
| Event labels | tracked.py:246-292 | `_LABELS` | 45 |
| Path → card key | enrichment.py:20-47 | `_MAP` | 33 |
| Path → card key | activity.py:29-75 | `_PATH_TO_CARD_KEY` | 47 |
| Path → event type | enrichment.py:52-107 | `_ACTION_MAP` | 55 |
| Domain → Source | projections/timeline.py:29-60 | `_DOMAIN_SOURCE` | 20 |
| Domain → label | projections/chains.py:23-40 | `_DOMAIN_LABELS` | 14 |
| Chain name patterns | projections/chains.py:43-90 | `_friendly_chain_name` | 7 patterns |

Total: ~221 hardcoded mapping entries across 7 locations.

**Fix:** Not necessarily one mega-catalog — but the duplicated ones (path→card_key) should be single-source. The rest are contextual and fine where they are as long as they're documented.

---

## Issue 6: Dead code and stale artifacts

1. **registrations/timeline.py:79-80** — Comment about removed functions. Delete it.
2. **registrations/timeline.py:62-68 vs 267-273** — `_EXTERNAL_SOURCES` defined at module level AND inside `_resolve_data()`. The local one shadows the module one. Remove the module-level constant.
3. **enrichment.py** — `_path_to_card_key()` duplicates activity.py. Replace with import.

---

## Issue 7: Correlation ID inconsistency

| Source | Pattern | Example |
|--------|---------|---------|
| @tracked (no chain) | `{domain}:{uuid8}` | `vault:a1b2c3d4` |
| @tracked (with header) | from `X-Correlation-ID` | `git-sync:mmsmu3n7` |
| plan_executor.py | `plan:{run_id8}` | `plan:a1b2c3d4` |
| replayer.py | `cdp_test:{run_id8}` | `cdp_test:a1b2c3d4` |
| build_stream.py | `pages-build:{uuid8}` | `pages-build:a1b2c3d4` |
| mediator core | `get_correlation()` or `""` | inherits from caller |
| index_watcher.py | `cycle-{YYYYMMDD-HHMMSS}` | `cycle-20260316-201710` |
| _seed_events | `seed-{timestamp}` | `seed-1710648000` |

These are all valid patterns — they just need to be documented so new code follows them.

---

## Issue 8: No documentation

No README exists for `src/core/services/events/`. A developer adding a new feature has no guide for:
- When to use `@tracked` vs direct emit
- How to name event types
- How correlation IDs work
- What goes in `detail` vs `summary`
- How to add a new chain type

---

## Recommended Cleanup Order

### Phase 1: Dedup + dead code (small, safe)
1. Delete `enrichment.py`'s `_path_to_card_key()` → import from activity.py
2. Delete stale comment in registrations/timeline.py:79-80
3. Remove shadowed `_EXTERNAL_SOURCES` in `_resolve_data()` → use module-level

### Phase 2: Extract shared utilities
4. Move `_LABELS` dict out of `_build_summary()` → module-level constant in tracked.py
5. Extract dataclass-to-dict conversion from enrichment.py into a small utility
6. Create `events/emit.py` — single helper for Pattern B/C direct emitters

### Phase 3: Documentation
7. Write `events/README.md` — architecture, patterns, naming conventions, examples

### Phase 4: Function splitting (optional, lower priority)
8. Split `extract_summary()` into path-specific handlers
9. Split `extract_result_summary()` similarly
10. Split `ChainProjection.build()` into group + split + build steps
