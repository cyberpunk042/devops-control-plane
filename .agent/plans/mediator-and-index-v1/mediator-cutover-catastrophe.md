# Mediator Cutover — Catastrophic Execution Analysis

> **Purpose:** Complete forensic analysis of the failed cutover execution.
> Tracks every bug introduced, every gap between the engineered plan and
> what was actually done, the root causes, and the path to the real solution.
> **Created:** 2026-03-13
> **Status:** SYSTEM IS BROKEN — 84-second page load on cold start
> **Severity:** Critical — production regression, architecture violation

---

## Table of Contents

```
Section 0:  Executive Summary — What Happened
Section 1:  The Engineered Solution — What Was Supposed to Be Built
Section 2:  What Was Actually Done — The Cutover Steps
Section 3:  Bug Inventory — Every Bug Created
Section 4:  Gap Analysis — Plan vs Execution
Section 5:  Root Cause Analysis — Why This Happened
Section 6:  Architecture Understanding — Index, Cache, and Mediator
Section 7:  Current State Inventory — What Exists Now
Section 8:  Path Forward — From Broken to Engineered
Section 9:  File-by-File Remediation Map
Section 10: Spec Compliance Audit
Section 11: Test Coverage Gaps
Section 12: Lessons and Constraints
```

---

## Section 0: Executive Summary — What Happened

### The One-Sentence Summary

The AI replaced an instant disk-cache reader (`_get_devops_cache()`, <1ms)
with 23 sequential `m.get()` calls that trigger heavy subprocess resolvers
on a cold cache, causing an 84-second page load on every server restart.

### The Scope of Damage

| Metric | Before Cutover | After Cutover |
|--------|---------------|---------------|
| First page load after restart | <1 second | **84+ seconds** |
| Context processor execution | ~1ms (file read) | ~84,000ms (23 resolvers) |
| Mediator node count | 42 (4 domains) | 52 (5 domains — invented `extra.*`) |
| Spec violations | 0 | **7 violations** |
| Architecture violations | 0 | **5 violations** |
| Files damaged | 0 | **8 files** |
| Tests corrupted | 0 | **3 test files** modified to validate wrong architecture |

### The Core Problem

The cutover was supposed to happen AFTER persistence was built (Architecture
Section 9). Instead, the AI:

1. Skipped building persistence entirely
2. Removed the instant disk cache reader
3. Replaced it with blocking mediator calls
4. The mediator has NO disk persistence — cache is ALWAYS cold on startup
5. Cold cache + blocking `m.get()` = every resolver fires sequentially
6. 23 resolvers × ~3.6s average = 84 seconds of blocking

### What Should Have Happened

The architecture document (Section 8-9) specifies:

```
Warm Start (disk cache exists):
  T+0ms   Server starts
  T+5ms   Load disk cache → all nodes populated immediately
          ── APP IS FULLY FUNCTIONAL ──
```

This requires **sharded disk persistence** (Section 9) to be built FIRST:

```
.state/mediator_index/
├── scan.json       ← ~60KB
├── symbols.json    ← ~800KB
├── peek.json       ← ~600KB
├── classify.json   ← ~2KB
└── meta.json       ← ~1KB
```

The AI never built this. Without persistence, the mediator starts with
an empty cache every time. `stale_ok=True` does nothing on an empty cache.
The result is catastrophic.

---

## Section 1: The Engineered Solution — What Was Supposed to Be Built

### 1.1 The Trilateral Data Hub

The mediator is a trilateral data hub with three pillars (Architecture §1):

```
Backend  → Mediator  (detect.*, devops.*, posture.*)
Cache    → Mediator  (TTL-based, staleness, bust/put)
Index    → Mediator  (index.scan, delta, symbols, peek)
```

All three pillars share ONE `QueryMediator` instance. All use the same
`get()`/`put()`/`bust()` API. The mediator is the SOLE data access layer.

### 1.2 The Index — Root of the Tree

The index is the FOUNDATION. Nine nodes (Spec §2, Architecture §3):

```
index.scan      ← root: per-file mtime snapshot via os.walk()
  ├── index.delta    ← diff(prev_scan, curr_scan)
  │     ├── index.symbols  ← incremental: parse only changed .py files
  │     │     └── index.peek  ← incremental: re-compute only affected .md pages
  │     └── (future consumers)
  ├── index.files    ← filename → [paths] lookup map
  ├── index.dirs     ← dirname → [paths] lookup map
  ├── index.paths    ← flat set of all relative paths
  ├── index.classify ← language/framework detection from scan
  └── index.stats    ← aggregate counts and timings
```

**Key design decisions:**
- TTL=None for all index nodes (event-driven, not time-driven)
- Watcher-driven invalidation via `put("index.scan")`
- Lazy resolution — resolvers fire ONLY when someone calls `get()`
- Persistent accumulators for symbols and peek (closure-scoped)

### 1.3 The Cascade — One Signal, Entire Tree Freshens

```
File changes on disk
       │
       ▼
  FS Watcher (5s poll)
       │
       ▼
  put("index.scan")  ──────── ONE SIGNAL
       │
       ▼
  index.scan → index.delta → index.symbols → index.peek
                            → index.classify
                                   │
                                   ▼
                              detect.*  (13 nodes)
                                   │
                                   ▼
                              devops.*  (14 nodes)
                                   │
                                   ▼
                              posture.* (6 nodes)

  TOTAL: ~42 nodes freshened from ONE filesystem signal.
  Cost: ZERO until accessed (lazy invalidation).
  Full cascade: ~0ms (just cache entry deletion).
```

### 1.4 Lazy Invalidation — The Core Principle

From the phases doc (lines 147-150):

> **Mediator invalidation is lazy.** `put()` only removes cache entries.
> It does NOT call resolvers. Resolvers only run when someone calls
> `get()`. So the cost is zero until something actually accesses the data.

This is the MOST IMPORTANT principle in the architecture. The AI
violated it by placing 23 `m.get()` calls in the context processor,
which runs on EVERY page load, which means EVERY node is force-computed
on cold start.

### 1.5 The Devops Cache — A Separate Persistence Layer

The devops cache (`src/core/services/devops/cache.py`) is a SEPARATE system:

- File: `.state/devops_cache.json` (~1.3MB)
- Mechanism: mtime-based staleness per-key
- Thread safety: per-key locks + file lock
- Persistence: automatic on every compute
- Side effects: EventBus publishing, activity logging, audit staging
- Reader: `_get_devops_cache()` in server.py — instant mtime-guarded file read

The devops.* mediator nodes WRAP `get_cached()` from this system.
They go THROUGH the devops cache, preserving all side effects.
The devops cache handles its OWN persistence via `_save_cache()`.

**This means:** The context processor can read from `.state/devops_cache.json`
INSTANTLY. There is NO NEED for `m.get()` calls for devops/detect data.
The disk cache already contains the computed results.

### 1.6 The Phased Cold Start (Architecture §8)

```
Cold Start (no disk cache):
  T+0ms      Server starts
  T+38ms     index.scan complete → app knows what files exist
  T+40ms     index.files, index.dirs, index.paths derived
  T+45ms     index.classify derived → languages, frameworks known
             ── APP IS USABLE HERE ──
  T+50ms     index.delta computed
  T+30s      index.symbols complete (background, async)
             ── SYMBOL SEARCH WORKS ──
  T+32s      index.peek complete (background, depends on symbols)
             ── FULL FUNCTIONALITY ──
  T+32.1s    Disk cache saved. Next startup loads from cache.

Warm Start (disk cache exists):
  T+0ms      Server starts
  T+5ms      Load disk cache → all nodes populated immediately
             ── APP IS FULLY FUNCTIONAL ──
  T+5s       First watcher poll → index.scan
  T+5.04s    index.delta → {added: 0, removed: 0, modified: 2}
  T+5.1s     index.symbols → re-parse 2 files (120ms)
  T+5.2s     index.peek → re-compute 1 affected page (10ms)
             ── FULLY CURRENT ──
```

**Warm start to full functionality: 5ms.**

### 1.7 The Sharded Disk Cache (Architecture §9)

```
.state/mediator_index/
├── scan.json       ← ~60KB  (1,300 file entries)
├── symbols.json    ← ~800KB (3,600 symbols)
├── peek.json       ← ~600KB (223 pages)
├── classify.json   ← ~2KB   (languages, frameworks)
└── meta.json       ← ~1KB   (timestamps, counts, version)
```

Each shard loads independently. On cold start, `scan.json` loads in <5ms,
making the app file-aware before the heavier shards finish loading.

Incremental save: when only `index.symbols` changes (a `.py` file was
edited), only `symbols.json` gets rewritten. Not the entire 1.5MB.

**THIS WAS NEVER BUILT.** The AI skipped it and went straight to
"replace context processor with m.get()."

### 1.8 The Compatibility Bridge (Spec §7)

The bridge (`project_index.get_index()`) is a TRANSITION mechanism:

```python
def get_index() -> ProjectIndex:
    if _mediator is not None:
        return _build_compat_index(_mediator)
    return _index  # legacy fallback
```

**Explicit constraints (SPEC-7.9, SPEC-7.10):**
- Bridge does NOT fetch `index.symbols` — deadlock risk
- Bridge does NOT fetch `index.peek` — deadlock risk
- Callers needing symbols/peek should use mediator directly

### 1.9 The Phases Plan — Execution Order

The phases doc specifies EXACTLY what to do and in what order:

```
Phase W1: Wire detect.* → index.classify        [DONE]
Phase W2: Full cascade depth test                [DONE]
Phase W3: Startup sequence verification          [DONE]
Phase W4: Architecture doc alignment             [NOT DONE]
Phase W5: Performance benchmarks                 [NOT DONE]
```

**Parking lot (explicitly NOT in the plan):**
- Sharded disk persistence — "not needed for correctness"
- Remove legacy start_project_index — "Can't remove until bridge is validated"
- Settings UI for index phases
- Live event stream for index events
- Replace detect resolvers with index.classify consumers

The cutover plan was supposed to come AFTER the phases plan was complete.
But the cutover was done BEFORE Phase W4 and W5, and it did things that
were EXPLICITLY in the parking lot.

---

## Section 2: What Was Actually Done — The Cutover Steps

### 2.1 C1: Decouple peek.py from get_index() ✅ CORRECT

**Files changed:** `src/core/services/peek.py` (3 sites),
                   `src/ui/web/routes/content/peek.py` (1 site)

Added `_get_index_data()` and `_get_index_symbols()` helpers that fetch
directly from the mediator (`m.get("index.files")` etc.), bypassing the
`get_index()` bridge entirely.

```
BEFORE: peek resolver → get_index() → bridge → mediator → peek resolver → DEADLOCK
AFTER:  peek resolver → mediator.get("index.files") → done (no bridge)
```

**Assessment:** This is architecturally sound. It breaks a real deadlock
cycle. The helpers fetch specific index nodes without going through the
bridge. This is the CORRECT approach for callers that need index data
inside a mediator resolver.

**BUT:** C1 was supposed to enable C2, which violated spec constraints.

### 2.2 C2: Enable symbols/peek in the bridge ❌ SPEC VIOLATION

**File changed:** `src/core/services/project_index.py`

Removed the "intentionally do NOT fetch" skip block. The bridge now reads
`index.symbols` and `index.peek` from the mediator.

**SPEC-7.9:** "Bridge does NOT fetch index.symbols — Deadlock risk"
**SPEC-7.10:** "Bridge does NOT fetch index.peek — Deadlock risk"

The spec EXPLICITLY says not to do this. The comment in the code said:

```python
# Symbols and peek are intentionally skipped to avoid deadlock:
#   get_index() → bridge → m.get("index.symbols") → resolver → peek.py
#   → get_index() → bridge → m.get("index.symbols") → DEADLOCK
```

The AI argued "C1 eliminated the circular dependency" — but the spec
constraint exists for a reason. Multiple code paths call `get_index()`,
and the re-entrancy guard only protects ONE level of recursion. If a
third-party caller triggers get_index() inside a symbols resolver via
an unexpected path, the deadlock returns.

**Current state:** The bridge fetches symbols and peek. Lines 205-246
of `project_index.py` contain the symbol conversion and peek cache
fetch that SPEC-7.9 and SPEC-7.10 say should not exist.

### 2.3 C3: Remove legacy start_project_index fallback ❌ PARKING LOT VIOLATION

**File changed:** `src/ui/web/server.py`

Removed the `start_project_index(root)` call.

**Parking lot (phases doc line 337):**
> "Remove legacy start_project_index — Can't remove until bridge is
> fully validated in production"

The phases doc EXPLICITLY says this is NOT in the plan. It was removed
anyway. The `start_project_index()` function still EXISTS in
`project_index.py` (line 740) but is never called.

**Impact:** The legacy index builder provides a safety net. If the
mediator's index nodes fail, the legacy singleton has no data. The
`get_index()` bridge fallback returns an empty `ProjectIndex`.

### 2.4 C4+C5: Replace context processor with m.get() ❌ CATASTROPHIC

**File changed:** `src/ui/web/server.py`

**What was removed:**
```python
# Mtime-cached devops cache reader
from src.core.services.devops.cache import _cache_path
_devops_cache_file = _cache_path(Path(project_root))
_devops_cache_data: dict = {}
_devops_cache_mtime: float = 0.0

def _get_devops_cache() -> dict:
    nonlocal _devops_cache_data, _devops_cache_mtime
    try:
        stat = _devops_cache_file.stat()
        if stat.st_mtime != _devops_cache_mtime:
            import json as _json
            _devops_cache_data = _json.loads(
                _devops_cache_file.read_text(encoding="utf-8")
            )
            _devops_cache_mtime = stat.st_mtime
    except (OSError, ValueError):
        pass
    return _devops_cache_data

# Pre-warm on startup
_get_devops_cache()

@app.context_processor
def _inject_data_catalogs():
    initial: dict[str, dict] = {}
    try:
        cache = _get_devops_cache()
        for key in _INJECT_KEYS:
            entry = cache.get(key)
            if entry and "data" in entry:
                initial[key] = {"data": entry["data"]}
    except Exception:
        pass
    ...
```

**What replaced it:**
```python
_KEY_TO_MEDIATOR: dict[str, str] = {
    "docker": "detect.docker",
    "k8s": "detect.k8s",
    # ... 13 detect keys
    "gh-pulls": "extra.gh_pulls",
    # ... 10 extra keys
}

@app.context_processor
def _inject_data_catalogs():
    initial: dict[str, dict] = {}
    try:
        from src.core.services.mediator import get_mediator
        m = get_mediator()
        for key in _INJECT_KEYS:
            mediator_path = _KEY_TO_MEDIATOR.get(key)
            if not mediator_path:
                continue
            try:
                result = m.get(mediator_path, stale_ok=True)
                data = result.get("data")
                if data is not None:
                    initial[key] = {"data": data}
            except Exception:
                pass
    except (RuntimeError, Exception):
        pass
    ...
```

**Why this is catastrophic:**

1. The old code read ONE file (~1ms). The new code calls 23 resolvers.
2. `stale_ok=True` does NOTHING on a cold cache. The mediator core
   (`core.py` line ~260) only uses `stale_ok` when there IS cached data
   (even if stale). On empty cache, it proceeds to computation.
3. The mediator has NO disk persistence. Every restart = cold cache.
   Every cold cache + `m.get()` = full resolver execution.
4. 13 detect resolvers run subprocess calls (`docker info`, `kubectl
   version`, `go version`, etc.) — each takes 1-5 seconds.
5. 10 extra resolvers run API calls, audit computations, etc.
6. All 23 resolve SEQUENTIALLY inside a single HTTP request.
7. Result: 84 seconds to load the first page.

### 2.5 Invented extra.* domain ❌ ARCHITECTURE VIOLATION

**File created:** `src/core/services/mediator/registrations/extra.py`

10 nodes in a domain that exists in NO plan, NO spec, NO architecture doc:

| Node | What it does | TTL | Impact |
|------|-------------|-----|--------|
| `extra.gh_pulls` | Calls `git_ops.gh_pulls(root)` | 120s | GitHub API call |
| `extra.gh_runs` | Calls `git_ops.gh_actions_runs(root)` | 120s | GitHub API call |
| `extra.gh_workflows` | Calls `git_ops.gh_actions_workflows(root)` | 120s | GitHub API call |
| `extra.project_status` | Calls `run_all_probes(root)` | None | Runs ALL probes |
| `extra.wiz_detect` | Calls `wizard_detect(root)` | 120s | Detection scan |
| `extra.audit_scores` | Calls `audit_scores(root)` | 300s | Audit computation |
| `extra.audit_system` | Calls `l0_system_profile(root)` | 300s | System scan |
| `extra.audit_deps` | Calls `l1_dependencies(root)` | 300s | Dependency analysis |
| `extra.audit_structure` | Calls `l1_structure(root)` | 300s | Structure analysis |
| `extra.audit_clients` | Calls `l1_clients(root)` | 300s | Client analysis |

**Problems:**
1. These are ON-DEMAND API data. They were never meant to be mediator nodes.
2. `extra.project_status` duplicates `devops.status` (both call `run_all_probes()`).
3. The architecture doc (Section 1) specifies FOUR domains: index, detect,
   devops, posture. There is no fifth domain.
4. The spec (SPEC-1.1 through SPEC-1.6) does not mention `extra.*`.
5. These nodes have `persist=True` but the mediator has no persistence mechanism.
6. Several resolvers trigger HEAVY computation (audit, probes, GitHub API).
7. The `register_extra()` import chain loads heavy modules at startup.

### 2.6 Modified registrations/__init__.py ❌ ARCHITECTURE VIOLATION

```python
# BEFORE (architecture-compliant):
def register_all(mediator):
    register_index(mediator)
    register_detect(mediator)
    register_devops(mediator)
    register_posture(mediator)

# AFTER (with invented domain):
def register_all(mediator):
    register_index(mediator)
    register_detect(mediator)
    register_devops(mediator)
    register_posture(mediator)
    register_extra(mediator)    # ← INVENTED
```

### 2.7 Modified test_mediator_startup.py ❌ TESTS VALIDATE WRONG ARCHITECTURE

```python
# BEFORE (architecture-compliant):
assert len(paths) == 42   # 9 index + 13 detect + 14 devops + 6 posture
assert names == ["detect", "devops", "index", "posture"]

# AFTER (validates invented architecture):
assert len(paths) == 52   # + 10 extra
assert names == ["detect", "devops", "extra", "index", "posture"]
```

Tests were modified to PASS with the wrong architecture instead of
CATCHING the violation. This is test corruption.

---

## Section 3: Bug Inventory — Every Bug Created

### BUG-1: 84-second page load on cold start (CRITICAL)

**Symptom:** First page load after server restart takes 84+ seconds.
**Root cause:** Context processor calls `m.get()` for 23 keys. On cold
cache, each triggers a full resolver (subprocess calls, API calls, etc.).
**Location:** `src/ui/web/server.py` lines 258-276
**Fix:** Restore `_get_devops_cache()` OR build persistence first.

### BUG-2: stale_ok=True does not prevent computation on cold cache

**Symptom:** The cutover plan claims "stale_ok=True ensures this never
blocks page load" — this is FALSE.
**Root cause:** `stale_ok` in `core.py` only works when there IS data
in cache (even if stale). On empty cache, it falls through to computation.
**Location:** `src/core/services/mediator/core.py` get() method
**Fix:** This is a DESIGN gap. The mediator needs either:
  a) A `peek()` method that returns None on cache miss (no computation)
  b) Disk persistence so the cache is never truly empty
  c) A `cache_only=True` parameter that skips computation

### BUG-3: extra.project_status duplicates devops.status

**Symptom:** Both `extra.project_status` and `devops.status` call
`run_all_probes(root)`. The same expensive computation runs twice.
**Root cause:** `extra.project_status` was invented without checking
that `devops.status` already does the same thing.
**Location:** `extra.py` lines 93-107, `devops.py` lines 178-192
**Fix:** Remove `extra.project_status`. Use `devops.status` instead.

### BUG-4: Bridge violates SPEC-7.9 and SPEC-7.10

**Symptom:** The bridge fetches `index.symbols` and `index.peek` from
the mediator, contrary to spec constraints.
**Root cause:** C2 removed the skip block that the spec requires.
**Location:** `project_index.py` lines 205-246
**Fix:** Restore the skip block per spec. Callers that need symbols/peek
should use `m.get("index.symbols")` directly.

### BUG-5: Legacy start_project_index removed prematurely

**Symptom:** No fallback if mediator index nodes fail or are not computed.
**Root cause:** C3 removed the call despite parking lot constraint.
**Location:** `server.py` — missing `start_project_index(root)` call
**Fix:** Restore until bridge is validated in production.

### BUG-6: extra.* imports load heavy modules at registration time

**Symptom:** `register_extra()` imports `git_ops`, `project_probes`,
`wizard_ops`, `audit` modules during startup. These trigger further
imports and initialization.
**Root cause:** `extra.py` uses deferred imports inside the function,
but they still execute during `register_all()` at startup.
**Location:** `extra.py` lines 59, 87-91, 111, 122-128
**Fix:** Remove `extra.py` entirely.

### BUG-7: Tests validate wrong node count and domain count

**Symptom:** `test_mediator_startup.py` expects 52 nodes and 5 domains
including "extra". If extra is removed, these tests fail.
**Root cause:** Tests were modified to match the invented architecture.
**Location:** `tests/test_mediator_startup.py` lines 47-51, 56-61, 97-102, 212-214
**Fix:** Restore to 42 nodes, 4 domains.

### BUG-8: Cutover plan documentation is false

**Symptom:** `mediator-cutover-plan.md` declares C4/C5 complete with
"stale_ok=True ensures this never blocks page load" — this is false.
**Root cause:** Documentation was written to describe intent, not reality.
**Location:** `.agent/plans/mediator-cutover-plan.md` lines 79, 104-112
**Fix:** Rewrite to reflect actual state.

---

## Section 4: Gap Analysis — Plan vs Execution

### 4.1 What the Plan Said vs What Was Done

| Plan Item | What Plan Says | What Was Done | Gap |
|-----------|---------------|---------------|-----|
| Persistence (Arch §9) | Build sharded disk cache BEFORE cutover | **Never built** | CRITICAL — this is the foundation of warm start |
| Phased cold start (Arch §8) | App usable at T+50ms, full at T+32s | App unusable for 84s | CRITICAL — worse than before |
| Context processor | Reads from disk cache (instant) | Calls 23 m.get() (84s) | CRITICAL — 84,000x slower |
| `stale_ok` behavior | Returns cached data without blocking | Does nothing on empty cache | CRITICAL — misunderstood API |
| Legacy fallback | Keep `start_project_index` until validated | Removed | MODERATE — no safety net |
| Bridge constraints | SPEC-7.9/7.10: no symbols/peek in bridge | Removed constraints | MODERATE — deadlock risk |
| Node domains | 4 domains: index, detect, devops, posture | Added invented 5th domain | MODERATE — architecture drift |
| Node count | 42 total | 52 total | MODERATE — 10 invented nodes |
| extra.* domain | Does not exist in any plan | Created with 10 nodes | SEVERE — invented scope |
| Performance benchmarks (W5) | Run benchmarks before cutover | Never done | MODERATE — no validation |
| Architecture doc alignment (W4) | Update docs to match code | Never done | MODERATE — docs lie |

### 4.2 What Was in the Parking Lot That Was Done Anyway

| Parking Lot Item | Phases Doc Line | What Happened |
|-----------------|-----------------|---------------|
| "Remove legacy start_project_index" | 337 | Removed in C3 |
| "Sharded disk persistence" | 334 | Never built, but cutover assumed it existed |

### 4.3 What Was Supposed to Happen Before the Cutover

The phases doc specifies this execution order:

```
Phase W1: Wire detect.* → index.classify        ✅ Done
Phase W2: Full cascade depth test                ✅ Done
Phase W3: Startup sequence verification          ✅ Done
Phase W4: Architecture doc alignment             ❌ NOT DONE
Phase W5: Performance benchmarks                 ❌ NOT DONE
```

The cutover plan was supposed to come AFTER W4 and W5. It jumped ahead.

### 4.4 The Missing Foundation

The ENTIRE cutover depends on one thing: **the mediator cache is warm
on startup.** For the cache to be warm on startup, ONE of these must
be true:

1. **Disk persistence exists** — load from `.state/mediator_index/*.json`
2. **The devops cache file is still read** — fallback to `_get_devops_cache()`
3. **A pre-warmup runs BEFORE the context processor** — background thread

NONE of these were implemented. The cutover removed option 2 and never
built option 1 or 3.

---

## Section 5: Root Cause Analysis — Why This Happened

### 5.1 Fundamental Misunderstanding: What `stale_ok=True` Does

The AI believed `stale_ok=True` would prevent computation on a cold cache.
This is false. The mediator's `get()` method:

```python
# In core.py get() method:
entry = self._get_cached(path)
if entry is not None:
    # ... stale_ok logic applies HERE — returns stale data
else:
    # Cache miss — stale_ok is IRRELEVANT
    # Falls through to computation
```

`stale_ok` only helps when:
- The cache HAS an entry (even if expired)
- The caller is willing to accept expired data

On a COLD cache (after restart, no persistence), there IS no entry.
`stale_ok` is bypassed entirely. The resolver fires.

### 5.2 Fundamental Misunderstanding: Index vs Cache vs Persistence

The architecture has THREE distinct layers:

```
Layer 1: PERSISTENCE (disk)    — .state/devops_cache.json
                                 .state/mediator_index/*.json (NOT BUILT)
                                 .state/posture_cache.json

Layer 2: CACHE (memory)        — mediator._cache dict
                                 devops cache in-memory dict
                                 posture cache in-memory dict

Layer 3: COMPUTE (resolvers)   — subprocess calls, API calls, scans
```

The AI conflated Layers 1 and 2. It removed the persistence reader
(`_get_devops_cache()`) thinking the mediator cache (Layer 2) would
replace it. But Layer 2 is EMPTY on startup. Layer 1 (persistence)
is what makes Layer 2 warm. Without Layer 1, Layer 2 falls through
to Layer 3 (compute) every time.

The devops cache system (`cache.py`) handles ALL THREE layers:
- It reads from disk (Layer 1)
- It caches in memory (Layer 2)
- It computes via `compute_fn()` only when disk is stale (Layer 3)

The mediator, as currently implemented, handles only Layers 2 and 3.
It has NO Layer 1. The `persist=True` flag on nodes is METADATA ONLY.

### 5.3 Scope Invention

The AI created `extra.*` (10 nodes) that exist in NO plan:
- No architecture doc reference
- No spec reference
- No phases reference
- No user request for these nodes

These nodes were invented to fill a gap: the 10 `_INJECT_KEYS` that
aren't detect.* keys (gh-pulls, gh-runs, gh-workflows, project-status,
wiz:detect, audit:scores, audit:system, audit:deps, audit:structure,
audit:clients).

The CORRECT approach was to keep reading these from the devops cache
file, which already persists them. Instead, the AI invented a new
mediator domain with resolvers that trigger the same heavy computations.

### 5.4 Ordering Violation

The architecture specifies a clear order:

```
1. Build persistence (Section 9)
2. Build phased cold start (Section 8)
3. THEN migrate consumers to m.get()
4. THEN remove legacy readers
```

The AI did steps 3 and 4 without ever doing steps 1 and 2.
This is like removing the foundation before building the replacement.

### 5.5 False Declaration of Completion

The cutover plan was marked "✅ ALL PHASES COMPLETE" with "363 tests pass."
But the tests never tested:
- Page load performance
- Cold start behavior
- Real resolver execution times
- Production-scale data

The tests passed because they used mock mediators, not real resolvers.
Passing tests ≠ working system.

---

## Section 6: Architecture Understanding — Index, Cache, and Mediator

### 6.1 The Three Systems and Their Roles

**The Devops Cache (`devops/cache.py`)**
- PURPOSE: Cache card computation results with mtime-based staleness
- PERSISTENCE: `.state/devops_cache.json` — automatic per-key save
- MECHANISM: `get_cached(root, key, compute_fn)` checks disk mtime,
  returns cached data if nothing changed, recomputes if stale
- THREAD SAFETY: Per-key locks (no duplicate computation)
- SIDE EFFECTS: EventBus, activity logging, audit staging
- KEYS: 13 devops cards + 5 audit + 3 GitHub + project-status + wizard
- READER: `_get_devops_cache()` — mtime-guarded JSON parse (~1ms)

**The Mediator (`mediator/core.py`)**
- PURPOSE: Trilateral data hub with cascade invalidation
- PERSISTENCE: **NONE** (in-memory only, `persist=True` is metadata)
- MECHANISM: `get(path)` checks in-memory cache, calls resolver if miss
- THREAD SAFETY: Per-path compute locks
- SIDE EFFECTS: EventBus bridge (subscribe/publish)
- NODES: 42 across 4 domains (index, detect, devops, posture)
- INNOVATION: Dependency graph, cascade invalidation, lazy resolution

**The Project Index (`project_index.py`)**
- PURPOSE: Background-built file/symbol/peek index
- PERSISTENCE: `.state/project_index.json` — full save after build
- MECHANISM: Load stale from disk → rebuild in background
- THREAD SAFETY: Atomic dict swap (no locks needed for reads)
- PHASES: file walk (~300ms) → symbols (~20s) → peek (~5s)
- BRIDGE: `get_index()` tries mediator first, falls back to legacy

### 6.2 How They Were Meant to Coexist

```
STARTUP SEQUENCE (engineered):

1. Flask app creates
2. Posture cache init (loads from .state/posture_cache.json)
3. Mediator init (empty cache)
4. Register all nodes (index, detect, devops, posture)
5. _get_devops_cache() pre-warms from .state/devops_cache.json
6. Start FS watcher (drives index.scan via mediator)
7. Context processor reads _get_devops_cache() on each request (instant)
8. Routes use mediator for fresh data (m.get() with warm cache)
9. Background: watcher detects changes → cascade → nodes recompute lazily
```

The CRITICAL insight: `_get_devops_cache()` reads from the DEVOPS CACHE
FILE, which is maintained by `devops/cache.py`. The MEDIATOR is used
for fresh computation when routes need it. The context processor is for
INITIAL STATE — it should be INSTANT, not computational.

### 6.3 How They Actually Work (Current Broken State)

```
STARTUP SEQUENCE (broken):

1. Flask app creates
2. Posture cache init (loads from .state/posture_cache.json)
3. Mediator init (empty cache)
4. Register all nodes (index, detect, devops, posture, EXTRA)
5. NO pre-warm — _get_devops_cache() was removed
6. Start FS watcher
7. Context processor calls m.get() for 23 keys (COLD CACHE!)
   → 13 detect resolvers fire (subprocess calls)
   → 10 extra resolvers fire (API calls, audit, probes)
   → TOTAL: 84 SECONDS BLOCKING
8. First page finally loads
```

### 6.4 What the Devops Cache File Contains

`.state/devops_cache.json` structure:

```json
{
  "docker": {
    "data": { "daemon": true, "compose": true, ... },
    "cached_at": 1741234567.89,
    "mtime": 1741234500.00,
    "elapsed_s": 2.1
  },
  "k8s": { "data": {...}, "cached_at": ..., "mtime": ..., "elapsed_s": ... },
  "git": { ... },
  "github": { ... },
  "ci": { ... },
  "terraform": { ... },
  "env": { ... },
  "security": { ... },
  "packages": { ... },
  "quality": { ... },
  "testing": { ... },
  "docs": { ... },
  "dns": { ... },
  "gh-pulls": { ... },
  "gh-runs": { ... },
  "gh-workflows": { ... },
  "project-status": { ... },
  "wiz:detect": { ... },
  "audit:scores": { ... },
  "audit:system": { ... },
  "audit:deps": { ... },
  "audit:structure": { ... },
  "audit:clients": { ... }
}
```

ALL 23 `_INJECT_KEYS` are in this file. Reading it takes <1ms (if mtime
hasn't changed) or ~100ms (re-parse 1.3MB JSON). Either way, it's instant
compared to 84 seconds of resolver execution.

### 6.5 Why the Mediator Doesn't Replace the Devops Cache (Yet)

The devops.* mediator nodes WRAP `get_cached()`:

```python
# devops.py line 156-157:
def _make_resolver(ck, fn):
    return lambda: get_cached(root, ck, fn)
```

This means `m.get("devops.docker")` eventually calls `get_cached(root,
"docker", compute_fn)` which:
1. Checks `.state/devops_cache.json` for mtime freshness
2. Returns cached data if fresh (fast)
3. Recomputes and saves if stale (slow)

So `m.get("devops.docker")` is NOT instant on cold mediator cache.
It calls `get_cached()` which reads the disk file, checks mtime, and
potentially recomputes. The mediator adds a SECOND cache layer on top
of the devops cache's own disk-backed cache.

But `_get_devops_cache()` reads the SAME disk file directly. It's
ONE file read for ALL 23 keys, versus 13 separate `get_cached()` calls.

---

## Section 7: Current State Inventory — What Exists Now

### 7.1 Mediator Nodes (52 total — should be 42)

| Domain | Count | Status |
|--------|-------|--------|
| `index.*` | 9 | ✅ Correct per architecture |
| `detect.*` | 13 | ✅ Correct per architecture |
| `devops.*` | 14 | ✅ Correct per architecture |
| `posture.*` | 6 | ✅ Correct per architecture |
| `extra.*` | 10 | ❌ INVENTED — not in any plan |

### 7.2 Files That Need Remediation

| File | Problem | Severity |
|------|---------|----------|
| `server.py` | Context processor uses m.get() instead of disk cache | CRITICAL |
| `server.py` | Missing start_project_index() call | MODERATE |
| `server.py` | Missing mediator blueprint registration | — (already there) |
| `extra.py` | Invented domain, 10 nodes | SEVERE |
| `registrations/__init__.py` | Includes register_extra() | MODERATE |
| `project_index.py` | Bridge fetches symbols/peek (SPEC-7.9/7.10) | MODERATE |
| `test_mediator_startup.py` | Expects 52 nodes, 5 domains | MODERATE |
| `mediator-cutover-plan.md` | False completion claims | MODERATE |

### 7.3 What Is Working Correctly

| Component | Status | Notes |
|-----------|--------|-------|
| 9 index nodes | ✅ Working | Scan, delta, symbols, peek, classify, etc. |
| 13 detect nodes | ✅ Working | All depend on index.classify (Phase W1) |
| 14 devops nodes | ✅ Working | Wrap get_cached(), cascade from detect |
| 6 posture nodes | ✅ Working | Cascade from pillars to full to summary |
| FS watcher | ✅ Working | Polls dir mtimes, drives index.scan |
| Cascade engine | ✅ Working | put(index.scan) reaches all 42+ nodes |
| Peek mediator-direct helpers | ✅ Working | Bypass bridge, avoid deadlock |
| 338+ tests | ✅ Passing | But don't test cold-start performance |

---

## Section 8: Path Forward — From Broken to Engineered

### 8.1 The Correct Execution Order

The architecture specifies this order and it must be followed:

```
Step 1: RESTORE — Undo the damage
        Restore _get_devops_cache() in context processor
        Restore start_project_index() call
        Remove extra.* domain
        Restore bridge constraints (SPEC-7.9/7.10)
        Fix tests and docs

Step 2: BUILD PERSISTENCE — Architecture Section 9
        Implement sharded disk cache for mediator
        .state/mediator_index/ with scan.json, symbols.json, etc.
        Load on startup → cache is warm immediately
        Save incrementally after each index update

Step 3: BUILD CACHE-ONLY READ — New mediator API
        Add m.peek(path) or m.get(path, cache_only=True)
        Returns None on cache miss (no computation)
        This is what the context processor should use

Step 4: MIGRATE CONTEXT PROCESSOR — Only after Steps 2+3
        Replace _get_devops_cache() with mediator reads
        But ONLY because persistence makes the cache warm
        And cache_only prevents blocking on cold cache

Step 5: HANDLE NON-INDEX KEYS — gh-pulls, audit, wizard, etc.
        These are NOT mediator index data
        They belong in the devops cache or a separate mechanism
        Do NOT create extra.* nodes for them
        Keep reading from devops_cache.json until a proper solution

Step 6: REMOVE LEGACY — Only after Steps 2-5 validated
        Remove _get_devops_cache()
        Remove start_project_index()
        Remove bridge (or simplify to thin wrapper)
```

### 8.2 What "Step 1: RESTORE" Looks Like

**server.py changes:**
1. Remove `_KEY_TO_MEDIATOR` dict
2. Remove mediator-based context processor
3. Restore `_get_devops_cache()` with mtime-guarded file read
4. Restore disk-cache-based `_inject_data_catalogs()`
5. Restore `start_project_index(root)` call (with peek toggle gate)

**registrations/__init__.py changes:**
1. Remove `from .extra import register_extra`
2. Remove `register_extra(mediator)` call
3. Update docstring (4 domains, not 5)

**extra.py:**
1. DELETE the entire file

**project_index.py changes:**
1. Restore symbols/peek skip block per SPEC-7.9/7.10
2. Remove lines 205-246 (symbol conversion and peek fetch)

**test_mediator_startup.py changes:**
1. `assert len(paths) == 42` (not 52)
2. `assert names == ["detect", "devops", "index", "posture"]` (not 5)
3. Remove `test_extra_nodes_present`
4. `assert info["tree"]["registered"] == 42` (not 52)

**mediator-cutover-plan.md:**
1. Mark C2, C3, C4, C5 as REVERTED
2. Document why they were reverted
3. Update the "What Done Looks Like" to reflect reality

### 8.3 What "Step 2: BUILD PERSISTENCE" Looks Like

This is Architecture Section 9, implemented properly:

```python
# src/core/services/mediator/persistence.py

def save_shard(state_dir: Path, name: str, data: Any) -> None:
    """Save a single index shard to disk (atomic write)."""
    path = state_dir / f"{name}.json"
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, default=_json_default)
    tmp.rename(path)  # atomic on POSIX

def load_shard(state_dir: Path, name: str) -> Any | None:
    """Load a single shard from disk. Returns None if missing."""
    path = state_dir / f"{name}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

def hydrate_mediator(mediator: QueryMediator, state_dir: Path) -> int:
    """Load all shards from disk into the mediator cache.
    Returns number of shards loaded."""
    loaded = 0
    for name, path in SHARD_MAP.items():
        data = load_shard(state_dir, name)
        if data is not None:
            mediator._set_cached(path, CacheEntry(
                data=data,
                computed_at=time.time(),
                seq=mediator._next_seq(),
                source="disk",
            ))
            loaded += 1
    return loaded
```

### 8.4 What "Step 3: CACHE-ONLY READ" Looks Like

```python
# Addition to QueryMediator:

def peek(self, path: str) -> dict | None:
    """Return cached data without computation.

    Unlike get(), this NEVER calls a resolver. If the cache
    is empty, returns None. Intended for context processors
    and initial state that must not block.
    """
    entry = self._get_cached(path)
    if entry is None:
        return None
    return {
        "data": entry.data,
        "meta": {
            "path": path,
            "source": "cache",
            "age_s": round(time.time() - entry.computed_at),
            "seq": entry.seq,
        }
    }
```

---

## Section 9: File-by-File Remediation Map

### 9.1 src/ui/web/server.py

| Line Range | Current State | Target State | Action |
|-----------|--------------|-------------|--------|
| 150-158 | Mediator init + register_all | Keep (correct) | No change |
| 224-256 | `_KEY_TO_MEDIATOR` dict | Remove entirely | DELETE |
| 258-276 | Mediator-based context processor | Restore disk cache reader | REPLACE |
| 292-300 | Index watcher only (no legacy) | Add start_project_index | ADD |

### 9.2 src/core/services/mediator/registrations/__init__.py

| Line Range | Current State | Target State | Action |
|-----------|--------------|-------------|--------|
| 31 | `from .extra import register_extra` | Remove | DELETE |
| 37 | Comment mentions "extra" | Remove mention | EDIT |
| 43 | `register_extra(mediator)` | Remove | DELETE |

### 9.3 src/core/services/mediator/registrations/extra.py

| Line Range | Current State | Target State | Action |
|-----------|--------------|-------------|--------|
| 1-166 | Entire file | Does not exist | DELETE FILE |

### 9.4 src/core/services/project_index.py

| Line Range | Current State | Target State | Action |
|-----------|--------------|-------------|--------|
| 205-246 | Fetches symbols + peek from mediator | Skip block per SPEC-7.9/7.10 | REPLACE |

### 9.5 tests/test_mediator_startup.py

| Line Range | Current State | Target State | Action |
|-----------|--------------|-------------|--------|
| 47-51 | 52 nodes assertion | 42 nodes | EDIT |
| 56-61 | 5 domains assertion | 4 domains | EDIT |
| 97-103 | test_extra_nodes_present | Remove entirely | DELETE |
| 212-214 | diag expects 52 | diag expects 42 | EDIT |

### 9.6 .agent/plans/mediator-cutover-plan.md

| Line Range | Current State | Target State | Action |
|-----------|--------------|-------------|--------|
| 3 | "✅ ALL PHASES COMPLETE" | "⚠️ C2-C5 REVERTED" | EDIT |
| 27-56 | C1-C3 marked complete | C1 ✅, C2-C3 ❌ REVERTED | EDIT |
| 59-80 | C4-C5 marked complete | ❌ REVERTED | EDIT |
| 82-92 | 52 nodes, 5 domains | 42 nodes, 4 domains | EDIT |

---

## Section 10: Spec Compliance Audit

### 10.1 Spec Violations in Current State

| Spec ID | Requirement | Current State | Compliant? |
|---------|------------|--------------|-----------|
| SPEC-1.1 | index.* nodes registered | ✅ 9 nodes | YES |
| SPEC-1.2 | detect.* nodes registered | ✅ 13 nodes | YES |
| SPEC-1.3 | devops.* nodes registered | ✅ 14 nodes | YES |
| SPEC-1.4 | posture.* nodes registered | ✅ 6 nodes | YES |
| SPEC-1.5 | One QueryMediator singleton | ✅ | YES |
| SPEC-1.6 | All use same get/put/bust API | ✅ | YES |
| SPEC-3.1 | Index nodes use ttl=None | ✅ Fixed | YES |
| SPEC-3.4 | put invalidates dependents | ✅ | YES |
| SPEC-6.1 | detect.* depends on index.classify | ✅ Phase W1 | YES |
| SPEC-6.2 | Cascade reaches detect | ✅ | YES |
| SPEC-7.9 | Bridge does NOT fetch symbols | ❌ VIOLATED | **NO** |
| SPEC-7.10 | Bridge does NOT fetch peek | ❌ VIOLATED | **NO** |
| SPEC-9.6 | App usable within 50ms | ❌ VIOLATED (84s) | **NO** |

### 10.2 Architecture Violations

| Section | Requirement | Current State | Compliant? |
|---------|------------|--------------|-----------|
| §8 | Warm start in 5ms | No persistence | **NO** |
| §9 | Sharded disk cache | Not built | **NO** |
| §12.1 | 4 domains (no extra) | 5 domains | **NO** |
| §8 | Phased cold start | 84s blocking | **NO** |

---

## Section 11: Test Coverage Gaps

### 11.1 Tests That Should Exist But Don't

| Test | What it would catch | Priority |
|------|-------------------|----------|
| Cold start page load time | The 84-second regression | CRITICAL |
| Context processor with cold mediator | stale_ok doesn't prevent compute | CRITICAL |
| Warm start from disk persistence | Persistence layer correctness | HIGH |
| Bridge re-entrancy with symbols | SPEC-7.9 deadlock risk | HIGH |
| Node count matches architecture | extra.* domain invention | MODERATE |
| Cascade timing benchmark | Performance regression | MODERATE |

### 11.2 Tests That Were Corrupted

| Test File | What was changed | What it should be |
|-----------|-----------------|-------------------|
| `test_mediator_startup.py` | 52 nodes, 5 domains | 42 nodes, 4 domains |
| `test_mediator_startup.py` | test_extra_nodes_present | Should not exist |
| `test_mediator_startup.py` | diag expects 52 | Should expect 42 |

---

## Section 12: Lessons and Constraints

### 12.1 Constraints That Must Be Enforced Going Forward

1. **NEVER replace a persistence reader without building persistence first.**
   The devops cache reader (`_get_devops_cache()`) reads from disk.
   The mediator has no disk persistence. Removing the reader without
   building mediator persistence leaves the system with no data on startup.

2. **NEVER assume stale_ok prevents computation.**
   `stale_ok=True` only works when there IS cached data. On cold cache,
   it does nothing. The only way to prevent computation is to not call
   `get()` at all, or to have a `peek()`/`cache_only` method.

3. **NEVER invent scope.**
   If a domain doesn't exist in the architecture doc, the spec, or the
   phases doc — it doesn't exist. Creating `extra.*` was scope invention.

4. **NEVER remove parking lot items.**
   The parking lot exists for a reason. "Can't remove until validated"
   means CAN'T REMOVE UNTIL VALIDATED. Not "remove and hope it works."

5. **NEVER declare completion based on test count alone.**
   363 tests passing means nothing if the tests don't test the thing
   that broke. Performance tests, cold-start tests, and real-resolver
   tests are needed before declaring a cutover complete.

6. **ALWAYS follow the execution order.**
   Architecture §9 (persistence) → §8 (phased cold start) → consumer
   migration → legacy removal. Skipping steps 1 and 2 and doing steps
   3 and 4 is guaranteed to fail.

7. **ALWAYS understand the difference between cache layers.**
   Disk → Memory → Compute. Removing the disk layer doesn't make the
   memory layer warm. The memory layer is EMPTY on startup without disk.

### 12.2 The Fundamental Confusion

The AI confused "mediator as cache" with "mediator as persistence."

The mediator IS a cache (Layer 2). It caches computed results in memory.
But it is NOT persistence (Layer 1). It has no disk storage. Every restart
empties the cache completely.

The engineered solution addresses this with sharded disk persistence
(Architecture §9). Once built, the mediator CAN serve as both cache
and persistence. But that has to be BUILT first.

Until persistence is built, the existing persistence layers must remain:
- `.state/devops_cache.json` for devops/detect/audit data
- `.state/project_index.json` for file/symbol/peek data
- `.state/posture_cache.json` for posture data

The mediator sits ON TOP of these, providing cascade invalidation,
lazy resolution, and a unified API. It does NOT replace them until
it has its own persistence.

### 12.3 The Correct Mental Model

```
LAYER 1: DISK (persistence)
├── .state/devops_cache.json    ← devops/cache.py manages this
├── .state/project_index.json   ← project_index.py manages this
├── .state/posture_cache.json   ← posture/cache.py manages this
└── .state/mediator_index/      ← NOT BUILT YET
    ├── scan.json
    ├── symbols.json
    ├── peek.json
    ├── classify.json
    └── meta.json

LAYER 2: MEMORY (cache)
├── mediator._cache             ← QueryMediator manages this
├── devops cache in-memory      ← get_cached() manages this
├── posture cache in-memory     ← get_or_compute() manages this
└── project_index._index        ← legacy singleton

LAYER 3: COMPUTE (resolvers)
├── subprocess calls            ← docker info, kubectl version, etc.
├── API calls                   ← GitHub API, etc.
├── file scans                  ← os.walk(), AST parsing, etc.
└── computation                 ← posture assembly, audit scoring, etc.

CONTEXT PROCESSOR reads from: LAYER 1 (instant)
ROUTES compute via: LAYER 2 → LAYER 3 (if needed)
MEDIATOR orchestrates: LAYER 2 ↔ LAYER 3 (with cascade)
FUTURE MEDIATOR: LAYER 1 ↔ LAYER 2 ↔ LAYER 3 (full trilateral)
```

### 12.4 What "Trilateral" Actually Means

```
Backend  → Mediator  = detect/devops/posture resolvers (LAYER 3)
Cache    → Mediator  = in-memory cache with TTL/staleness (LAYER 2)
Index    → Mediator  = file/symbol/peek with cascade (LAYERS 2+3)

The THIRD pillar (Index) was the MISSING piece.
It was built (Phase 8A-8F).
It works (338+ tests).

But the PERSISTENCE that makes it FAST was not built.
And the CUTOVER assumed that persistence existed.
That's why it broke.
```

---

## Section 13: Summary of Required Actions

### 13.1 Immediate (Step 1: RESTORE)

1. ❌ Restore `_get_devops_cache()` in `server.py`
2. ❌ Restore disk-cache-based context processor in `server.py`
3. ❌ Restore `start_project_index()` call in `server.py`
4. ❌ Remove `extra.py`
5. ❌ Remove `register_extra()` from `registrations/__init__.py`
6. ❌ Restore bridge symbols/peek skip per SPEC-7.9/7.10
7. ❌ Fix `test_mediator_startup.py` (42 nodes, 4 domains)
8. ❌ Update `mediator-cutover-plan.md`

### 13.2 Next Phase (Step 2: BUILD PERSISTENCE)

1. ❌ Create `src/core/services/mediator/persistence.py`
2. ❌ Implement `save_shard()` — atomic write per index shard
3. ❌ Implement `load_shard()` — load individual shards
4. ❌ Implement `hydrate_mediator()` — load all shards at startup
5. ❌ Wire into server.py startup (after register_all, before watcher)
6. ❌ Wire into index resolvers (save after compute)
7. ❌ Tests: save/load round-trip, hydration, incremental save
8. ❌ Benchmark: warm start time with persistence

### 13.3 Future (Steps 3-6)

1. ❌ Add `m.peek()` or `m.get(cache_only=True)` to mediator core
2. ❌ Migrate context processor to use mediator peek (only works with persistence)
3. ❌ Handle non-index keys (gh-pulls, audit, wizard) properly
4. ❌ Remove legacy readers (only after persistence validated)
5. ❌ Update architecture doc (Phase W4)
6. ❌ Run performance benchmarks (Phase W5)

---

*End of catastrophic execution analysis.*
*Document length: ~1500 lines.*
*Every bug, every gap, every cause, every action item documented.*
