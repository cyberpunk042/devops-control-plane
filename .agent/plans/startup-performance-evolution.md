# Startup Performance Evolution

> The program startup went from <1s to 7.8s. The `--debug-startup` profiler
> (added in this session) shows exactly where every millisecond goes.
> Two systems don't follow the program's delta-driven incremental pattern:
> the event store and the mediator hydration. Both re-process raw data from
> scratch on every restart instead of persisting and loading the processed form.

---

## The Program's Pattern (what works)

The index system is the gold standard for startup performance:

```
index.scan (38ms)
  → Persists PROCESSED FileEntry dataclasses to JSON shard
  → On hydration: loads shard, rehydrates FileEntry objects, injects into cache
  → Incremental: index.delta knows exactly which files changed
  → Accumulator: _state["symbol_acc"] persists across get() calls in closure scope
  → Warm restart: <100ms for 5000 files
```

Key principles:
1. **Persist the processed form** — not raw data that needs re-processing
2. **Load once, inject directly** — no conversion step on the hot path
3. **Delta-driven** — only re-process what changed since last run
4. **Accumulator pattern** — state persists across calls, grows incrementally

---

## Problem 1: Event Store (868ms → should be <50ms)

### Current behavior

```
Restart
  → load_cold(days=7)
    → _read_cold(): open each JSONL file, read every line, json.loads() each line,
      Event.from_dict() each dict → 25,145 events from 5 files (9.6MB)
    → Dedup against empty hot cache (all are new)
    → Result: 5000 events loaded into hot deque (868ms)

Every subsequent restart: same 868ms. No caching of processed form.
JSONL lines written yesterday are re-parsed today. Same lines, same parsing, same cost.
```

### What's wrong

- Raw JSONL is the WRITE format (append-only, human-readable, one file per day). Good.
- But it's also the READ format on restart. Bad.
- `_read_cold()` parses every line: `json.loads(line)` → `Event.from_dict(d)` → 25K objects
- The hot deque caps at 5000 events, but `_read_cold` parses ALL 25K before dedup
- No tracking of "I already loaded up to this point in this file"
- No persistence of the processed hot cache

### The evolution

The event store should persist its HOT cache as the read format. JSONL stays as the
append-only write format. On restart:

1. Load the hot cache snapshot (pickle — one file, ~1MB, <50ms)
2. Check each JSONL file for lines written AFTER the snapshot timestamp
3. Parse only the delta lines (typically 0 on clean restart, a few on crash recovery)
4. Save updated snapshot

**Snapshot format**: pickle of `{events: list[Event], saved_at: float, seq: int}`

**When to save**: After every `load_cold()` call and periodically during operation
(every N appends or every M seconds). This ensures the snapshot stays fresh.

**Delta detection**: Each JSONL file has a name (date) and grows by appending. The snapshot
records `{filename: byte_offset}` for each file it fully processed. On restart, seek to
the byte offset and read only new lines.

```python
# Snapshot contains:
{
    "events": [Event, Event, ...],     # the hot cache (up to 5000)
    "seq": 12345,                       # sequence counter
    "saved_at": 1711000000.0,           # when snapshot was saved
    "file_offsets": {                    # byte offset per JSONL file
        "2026-03-19.jsonl": 3836822,    # fully processed up to this byte
        "2026-03-20.jsonl": 82378,
    },
}

# On restart:
1. Load snapshot → hot cache populated instantly (<50ms)
2. For each JSONL file:
   a. If file not in file_offsets → new file, parse entirely
   b. If file size == file_offsets[file] → no new data, skip
   c. If file size > file_offsets[file] → seek to offset, parse only new lines
3. Save updated snapshot with new offsets
```

**Expected performance**: <50ms cold start (pickle load) + ~0ms if no new events since
last snapshot. Even after a crash with 100 unsnapshotted events: <10ms to parse 100 lines.

### Files to change

- `src/core/services/events/store.py` — `load_cold()`, `_read_cold()`, add `_save_snapshot()`, `_load_snapshot()`
- No changes to the append path (`_persist()`) — JSONL write stays as-is
- No changes to the query path — hot cache is the same deque

---

## Problem 2: Mediator Hydration (1,489ms → should be <100ms)

### Current behavior

```
Restart
  → hydrate_cache()
    → load_all_nodes(): scan .state/mediator_index/ for 48 .json files,
      json.load() each one → 14MB of JSON parsed individually
    → _rehydrate_shards(): convert JSON dicts back to FileEntry and
      IndexSymbolEntry dataclasses (4.1MB symbols shard alone has thousands
      of entries, each needs IndexSymbolEntry(**dict) construction)
    → Inject each node into mediator cache via put()
    → Also derive index.files, index.dirs, index.paths from scan data
    → Result: 48 nodes hydrated (1,489ms)

Every restart: same 1,489ms. Same files, same parsing, same conversion.
```

### What's wrong

- 48 individual `json.load()` calls instead of one consolidated read
- After JSON load, `_rehydrate_shards()` iterates every entry in the two largest shards
  (index.scan: 5000 FileEntry conversions, index.symbols: thousands of IndexSymbolEntry
  conversions) — this conversion runs on EVERY restart even though the data hasn't changed
- No delta check — shards that haven't changed since last hydration are re-loaded anyway
- The write format (individual JSON shards) is also the read format. Good for debugging
  and atomic writes. Bad for bulk read on startup.

### The evolution

Persist a consolidated snapshot of ALL shards in their REHYDRATED form. Individual JSON
shards stay as the write format (atomic, human-readable, per-node). The read path uses
the consolidated snapshot.

**Two-level persistence**:
- **Level 1 (write)**: Individual JSON shards — written by `persist_node()` after each
  computation. Atomic (tmp + rename). One file per mediator node. This is the source of truth.
- **Level 2 (read cache)**: Consolidated pickle — contains ALL shard data in rehydrated
  form (FileEntry objects, IndexSymbolEntry objects, not dicts). Built from Level 1 shards.
  Used exclusively by `hydrate_cache()` on startup.

**Staleness detection**: The consolidated pickle tracks the mtime of every JSON shard it
was built from. On startup:

```python
# Consolidated pickle contains:
{
    "data": {                          # All shard data, REHYDRATED
        "index.scan": {path: FileEntry(...)},
        "index.symbols": {name: [IndexSymbolEntry(...)]},
        "detect.docker": {...},
        ...
    },
    "shard_mtimes": {                  # mtime of each JSON shard when pickle was built
        "index.scan.json": 1711000000.0,
        "index.symbols.json": 1711000001.0,
        "detect.docker.json": 1711000002.0,
        ...
    },
    "saved_at": 1711000003.0,
}

# On startup:
1. Load consolidated pickle
2. Check each JSON shard's current mtime against stored mtime
3. If ALL match → use pickle data directly (0 JSON parsing, 0 rehydration)
4. If SOME changed → reload only changed shards from JSON, rehydrate only those,
   merge with pickle data, save updated pickle
5. If pickle doesn't exist → full JSON load + rehydration (first run only),
   save pickle for next time
```

**Where to build the pickle**: In `hydrate_cache()` AFTER `_rehydrate_shards()` runs.
This ensures the pickle contains the fully rehydrated data. Also rebuild when shards
are updated — add a call in `persist_node()` or lazily on next startup.

**Expected performance**: <100ms for pickle load (one 12MB file read + pickle
deserialization). No JSON parsing. No dataclass conversion. Direct injection.

### Files to change

- `src/core/services/mediator/persistence.py`:
  - `load_all_nodes()` — add consolidated pickle fast path with shard mtime validation
  - `hydrate_cache()` — save consolidated pickle AFTER rehydration (contains dataclass objects)
  - `persist_node()` — no change (individual JSON shards stay as-is)
  - Add `_save_consolidated()`, `_load_consolidated()`

---

## Problem 3: Stacks Catalog (791ms — investigate)

The `--debug-startup` shows 791ms for "Stacks catalog + context processor". This
includes `discover_stacks()` which reads YAML stack definition files. This existed
before the compat commit but is worth investigating:

- Is `discover_stacks()` re-reading YAML files on every startup?
- Can stack definitions be cached (they don't change at runtime)?
- This is a separate investigation — not part of the compat remediation.

---

## Problem 4: Blueprint Imports (621ms — investigate)

591-699ms to import all route blueprints. This is the cost of Python importing ~40
modules with their dependencies. This existed before the compat commit. The compat
blueprint adds ~176ms of this.

Worth investigating:
- Which blueprints are the most expensive to import?
- Can some imports be deferred?
- The compat blueprint imports Flask + mediator — can those be lighter?

---

## Execution Order

1. **Event store evolution** — biggest win for the regression (868ms → <50ms)
2. **Hydration evolution** — second biggest (1,489ms → <100ms)
3. **Stacks catalog** — investigate and fix if possible (791ms)
4. **Blueprint imports** — investigate, lower priority (621ms)

After 1 + 2: startup should drop from 3.3s to ~1.5s (blueprint imports + stacks + overhead).
After 1 + 2 + 3: target <1s.

---

## What NOT to Change

- JSONL append format — stays. It's the write-optimized append-only format.
- Individual JSON shards — stay. They're the atomic write format for each mediator node.
- The `persist_node()` write path — stays. Fire-and-forget after computation.
- The `_rehydrate_shards()` logic — stays. It's correct. Just needs to run less often
  (only when JSON shards change, not every restart).
- The hot deque in EventStore — stays. 5000 event cap is correct.
- The event query path — stays. Reads from hot cache first, falls back to JSONL.

---

## Verification

After implementation, `--debug-startup` should show:

```
⏱  STARTUP PROFILER
⏱    Step    Total   Label
⏱  ──────  ───────  ──────────────────────────────────
⏱      1ms       1ms  Flask app created
⏱    600ms     601ms  Blueprint imports
⏱    200ms     801ms  Blueprint registration
⏱     10ms     811ms  Mediator init
⏱     50ms     861ms  Mediator register_all (all domains + dispatches)
⏱    100ms     961ms  Mediator hydration (consolidated pickle)
⏱      ?ms       ?ms  Stacks catalog (TBD)
⏱      5ms       ?ms  Index watcher + final setup
⏱  ──────  ───────  ──────────────────────────────────
⏱           <1500ms  TOTAL STARTUP (target: <1000ms)
```

Event store load_cold no longer appears as a startup step — it runs in background
via WorkQueue at LOW priority. Timeline.data also runs in background.

The `--debug-startup` flag itself stays as a permanent tool for monitoring startup
performance as the program grows.
