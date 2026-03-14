# QueryMediator v2 — Foundation Implementation Plan

> **Status:** Plan — awaiting approval before any code is written  
> **Created:** 2026-03-13  
> **Parent:** `query-mediator-v2-foundation-requirements.md`  
> **Delivers:** Working foundation engine + comprehensive usage documentation  
> **Rule:** NO CODE IS WRITTEN until every ambiguity in this plan is resolved.

---

## 0. Ambiguity Resolution

Before a single line of code is written, every question must have
a clear answer. These are the questions that, if left unanswered,
would lead to wrong decisions during implementation.

### Q1: Keep v1 code or rewrite from scratch?

**Answer: EVALUATE AND EVOLVE.**

The v1 codebase has 2,701 lines of engine code and 5,015 lines of
tests. Some of it maps precisely to the v2 requirements. Some of it
has architectural flaws. The plan evaluates each file:

| File | Lines | Verdict | Reason |
|------|-------|---------|--------|
| `tree.py` | 418 | **KEEP** — satisfies REQ-TREE-1 through TREE-5 | Hierarchical namespace, registration, dependency graph, introspection, immutability. All working, tested. |
| `core.py` | 1,143 | **EVOLVE** — satisfies most REQ-API and REQ-CACHE, but needs targeted fixes | get, peek, peek_many, put, bust, dispatch, subscribe, diag, batch, refresh — all implemented. But: (1) dispatch blindly dispatches all paths instead of only invalidated; (2) bust() is max_age based, should also support path-based cascade bust; (3) persist_node integration needs cleanup. |
| `persistence.py` | 605 | **EVOLVE** — has both legacy shard code and generic persist_node | Dual system: legacy SHARD_MAP (hardcoded index shards) + generic persist_node (any node). Needs consolidation into ONE system: generic persistence for all nodes. Remove legacy SHARD_MAP approach. |
| `__init__.py` | 102 | **EVOLVE** — init/get_mediator/singleton pattern is correct | Minor: adjust thread pool defaults, add persistence wiring. |
| `index_watcher.py` | 433 | **NOT FOUNDATION** — this belongs in the Index Infrastructure phase | Moves to Phase 4 (Index). Not touched in foundation work. |
| `registrations/` | 5 files | **NOT FOUNDATION** — domain-specific, belongs in later phases | `detect.py`, `devops.py`, `posture.py`, `index.py` move to their respective phases. `extra.py` is KEPT (validate necessity). `__init__.py` stays as-is. |
| `README.md` | 520 lines | **REWRITE** — must reflect v2 architecture, not v1 | Delivered as part of this plan's documentation deliverable. |

**Why not rewrite from scratch:** tree.py is correct and has 16 test
files validating it. core.py has 90% of the required API surface
already working. Rewriting would risk introducing regressions in
tested code. The principle is: if it satisfies the requirement AND
passes tests, keep it. If it has a flaw, evolve it surgically.

### Q2: What happens to `extra.py`?

**Answer: NOT DELELED. IT IS NEEDED FOR THE FOUNDATION. IT JUST GOES LAST IN THE INDEXING ORDER.**

We need to verify that the extra nodes are actually needed. If not, we can delete them.
But for now, we keep them. AND VALIDATE THAT THEY ARE ACTUALLY NEEDED.

### Q3: What happens to the 16 test files (5,015 lines)?

**Answer: KEEP all tests that validate foundation behavior.**

The tests are organized by concern:

| Test File | Lines | Foundation? | Action |
|-----------|-------|-------------|--------|
| `test_mediator.py` | 493 | YES — core get/put/bust | Keep, verify passing |
| `test_mediator_cascade.py` | 380 | YES — cascade mechanics | Keep |
| `test_mediator_stale.py` | 259 | YES — TTL/staleness | Keep |
| `test_mediator_refresh.py` | 346 | YES — refresh operations | Keep |
| `test_mediator_subscribe.py` | 226 | YES — subscribe/notify | Keep |
| `test_mediator_dispatch.py` | 163 | YES — background dispatch | Keep |
| `test_mediator_startup.py` | 223 | YES — validates startup and node registration | Keep, verify passing (52 nodes / 5 domains with extra.* kept) |
| `test_mediator_trilateral.py` | 259 | YES — cross-domain cascade | Keep |
| `test_mediator_delta.py` | 434 | NO — index-specific | Keep for Phase 4 |
| `test_mediator_index.py` | 747 | NO — index-specific | Keep for Phase 4 |
| `test_mediator_index_bridge.py` | 162 | NO — index-specific | Keep for Phase 4 |
| `test_mediator_index_dashboard.py` | 184 | NO — index UI specific | Keep for Phase 7 |
| `test_mediator_index_watcher.py` | 275 | NO — watcher-specific | Keep for Phase 4 |
| `test_mediator_detect.py` | 283 | NO — detect-specific | Keep for Phase 5 |
| `test_mediator_devops.py` | 320 | NO — devops-specific | Keep for Phase 6 |
| `test_mediator_posture.py` | 261 | NO — posture-specific | Keep for Phase 6 |

### Q4: Where does persistence data live?

**Answer: `.state/mediator_index/`** — same directory as v1.

Each persisted node gets its own file: `<mediator_path>.json`.
Example: `detect.docker.json`, `index.scan.json`, `posture.full.json`.

No more legacy SHARD_MAP. No more dual naming (scan.json vs
index.scan.json). ONE naming convention: the mediator path IS
the filename (dots preserved).

Existing shard files from v1 will be migrated or ignored (a one-time
cleanup on first v2 startup).

### Q5: What thread pool size?

**Answer: 4 workers** — same as v1.

This will be revisited in Phase 4 (Index) when we measure GIL
contention with real workloads. For the foundation, 4 is fine
because foundation tests don't have CPU-heavy resolvers.

### Q6: Does the foundation touch server.py?

**Answer: NO.**

The foundation builds the ENGINE. How it's initialized in server.py
is part of the infrastructure phases. server.py currently initializes
the mediator, registers nodes, and hydrates — that all stays as-is
for now.

### Q7: Does the foundation touch any route files?

**Answer: NO.**

No route files are modified. The foundation is the `src/core/services/mediator/`
module only.

### Q8: What about EventBus integration?

**Answer: KEEP the existing integration.**

core.py already publishes events via `_publish_change()` which uses
deferred imports to the EventBus. This satisfies REQ-OBS-1 and
REQ-OBS-2. No changes needed.

### Q9: How is the devops cache file handled?

**Answer: NOT TOUCHED.**

The devops cache (`devops/cache.py`, `.state/devops_cache.json`)
is a separate system. The foundation does not modify it. The
context processor in server.py continues to read from it for
non-mediator keys. This stays until Phase 8 (Migration).

### Q10: What's the "v1 to v2 migration" story?

**Answer: THERE IS NO MIGRATION during foundation phase.**

The foundation evolves the engine IN PLACE. The same module path,
the same class names, the same API surface (with additions, not
breaking changes). Existing callers continue to work. New callers
get new capabilities.

No visible change to any caller during foundation phase. The
node count stays at 52 (5 domains including extra.*). The extra
nodes are validated for necessity during this phase but are kept
unless proven unnecessary.

---

## 1. Deliverables

This plan delivers FOUR things:

### D1: Evolved Engine Code

Files in `src/core/services/mediator/`:

| File | Action | What Changes |
|------|--------|-------------|
| `tree.py` | None | Already satisfies requirements |
| `core.py` | 3 surgical edits | See Step 2 |
| `persistence.py` | Consolidation | See Step 3 |
| `__init__.py` | Minor update | See Step 4 |
| `registrations/__init__.py` | Verify ordering | See Step 5 |
| `registrations/extra.py` | VALIDATE | Verify nodes are needed, ensure last in indexing order |

### D2: Fixed Tests

| File | Action |
|------|--------|
| `test_mediator_startup.py` | Verify passes as-is (52 nodes, 5 domains) |

### D3: Usage Documentation (README.md)

Complete rewrite of `src/core/services/mediator/README.md`:

- What the mediator IS and WHY it exists
- Architecture overview (trilateral hub diagram)
- Complete API reference with examples for every operation
- The dependency tree and how cascade works
- Persistence: how shards work, where they live
- Concurrency model: locks, refreshing guard, thread pool
- How to register a new node (for future phases)
- How to read from the mediator (get, peek, stale_ok)
- How to write to the mediator (put, bust)
- How to observe (subscribe, diag)
- Performance characteristics
- DO's and DON'Ts

This document IS the "clear usage of the layer through any means
necessary." Anyone reading it should understand how to use the
mediator WITHOUT reading the source code.

### D4: Requirements Compliance Matrix

A section at the end of the README that maps every REQ-* to:
- Which file implements it
- Which test verifies it
- Current status (PASS / FAIL / NOT TESTED)

---

## 2. Step-by-Step Execution

### Step 1: Verify Current State

**Goal:** Confirm the foundation tests pass BEFORE making changes.

```
Action: Run the 8 foundation test files
Expected: All pass
If fail: Fix FIRST before proceeding
```

Tests to run:
- test_mediator.py
- test_mediator_cascade.py
- test_mediator_stale.py
- test_mediator_refresh.py
- test_mediator_subscribe.py
- test_mediator_dispatch.py
- test_mediator_startup.py
- test_mediator_trilateral.py

### Step 2: Evolve core.py (3 surgical edits)

**Edit 2a: Dispatch must not blindly dispatch everything**

The current `dispatch()` submits every path it receives. The caller
(index_watcher.py) passes ALL detect/devops/posture paths. This is
the #1 cause of the "new system is slower" problem.

The fix is in `_dispatch_worker()`: skip nodes whose cache is still
fresh (not just "has data" but "data is not stale"). Currently it
skips if cached at all. It should skip if cached AND not stale.

```python
# CURRENT (v1):
def _dispatch_worker(self, task_id, paths):
    for p in paths:
        entry = self._get_cached(p)
        if entry is not None:
            continue  # ← skip if ANY cached data exists
        self.get(p, force=True)

# TARGET (v2):
def _dispatch_worker(self, task_id, paths):
    for p in paths:
        entry = self._get_cached(p)
        if entry is not None:
            node = self._tree.resolve(p)
            if node and node.ttl is not None:
                age = time.time() - entry.computed_at
                if age < node.ttl:
                    continue  # ← skip only if FRESH
        self.get(p, force=True)
```

This means: dispatched nodes with fresh cached data are SKIPPED.
Only stale or missing nodes recompute. This is the delta principle
applied to dispatch.

**Edit 2b: Add path-based bust()**

Current `bust()` takes `max_age` and busts all entries older than
that. The requirements also need `bust(path)` — bust a specific
path and cascade. This is actually what `put(path, data=None)` does
today. So this is already satisfied by `put()`.

However, for API clarity, add a `bust_path()` method that is
explicitly "invalidate this path and cascade":

```python
def bust_path(self, path: str, *, cascade: bool = True,
              cascade_depth: int = -1, notify: bool = True) -> dict:
    """Invalidate a specific path and optionally cascade.

    Convenience wrapper around put(path, data=None).
    """
    return self.put(path, data=None, cascade=cascade,
                    cascade_depth=cascade_depth, notify=notify)
```

**Edit 2c: Integrate persist_node cleanly in get()**

The current `get()` calls `persist_node()` after computation. This
was added as a patch during the persistence work. Verify it's clean:
- Called AFTER `_set_cached()` (so cache is populated first)
- Called ONLY for nodes with `persist=True`
- Fire-and-forget (never blocks the return)
- Error-safe (never crashes the compute path)

READ the current integration, verify these properties, fix if needed.

### Step 3: Consolidate persistence.py

**Goal:** One unified system. No more SHARD_MAP + persist_node duality.

**Current state:**
- `SHARD_MAP` maps 4 hardcoded index paths to legacy filenames
- `persist_node()` saves ANY node as `<path>.json`
- `load_all_shards()` scans directory, handles both naming conventions
- `hydrate_cache()` loads and injects into mediator
- `_rehydrate_shards()` reconstructs dataclasses from JSON dicts
- Legacy functions: `save_shard()`, `save_all_shards()`, `save_meta()`,
  `save_index_shard()`, `load_shard()`, `load_meta()`

**Target state:**
- `persist_node(project_root, path, data)` — saves `<path>.json` (KEEP)
- `load_all_nodes(project_root)` — scans for all `*.json`, returns dict (EVOLVE from load_all_shards)
- `hydrate_cache(mediator, project_root)` — loads all + injects (KEEP)
- `_rehydrate_shards()` — reconstruct dataclasses (KEEP — needed for index nodes)
- `_json_default()` — JSON serializer (KEEP)
- `_state_dir()` — directory path (KEEP)
- `ShardMeta` — metadata class (KEEP but simplify)

**Remove:**
- `SHARD_MAP` — no more hardcoded path-to-filename mapping
- `SHARD_TO_PATH` — inverse map, not needed
- `save_shard()` — replaced by persist_node
- `save_all_shards()` — not needed (individual saves)
- `save_index_shard()` — replaced by persist_node
- `save_meta()` — absorbed into `persist_node` or simplified
- `load_shard()` — replaced by load_all_nodes
- `load_meta()` — simplified

**File naming convention:**
- Path `index.scan` → file `index.scan.json`
- Path `detect.docker` → file `detect.docker.json`
- Path `posture.full` → file `posture.full.json`

Dots in the path are preserved in the filename. No directory nesting.
No translation map.

**Migration:** On first v2 startup, if old-style files exist
(e.g. `scan.json` instead of `index.scan.json`), load them but
DON'T rename. They'll be superseded on next compute. Clean and simple.

### Step 4: Update __init__.py

**Current:** Creates ThreadPoolExecutor(max_workers=4), creates
mediator, exposes `init()`, `get_mediator()`, `_reset()`.

**Changes:**
- No structural changes
- Verify the init sequence is correct:
  1. Create DataTree
  2. Create QueryMediator with tree + executor
  3. Return mediator instance
- Registration and hydration happen OUTSIDE init (in server.py)

### Step 5: Validate and order registrations/

**Validate:** `registrations/extra.py`
- READ every node it registers
- For EACH node: verify it serves a real consumer (route, context
  processor, or UI component that actually reads it)
- Document which nodes are validated as needed
- Ensure `register_extra()` runs LAST in `register_all()` ordering

**Verify:** `registrations/__init__.py`
- Confirm registration order: index → detect → devops → posture → extra
- extra.* goes last because it depends on data from other domains

**Keep:** `detect.py`, `devops.py`, `posture.py`, `index.py`
These are NOT part of foundation work. They stay as-is. They'll
be reviewed in their respective phases.

### Step 6: Verify test_mediator_startup.py

**Expected:** Tests pass as-is with 52 nodes / 5 domains.
If any assertions need updating based on Step 5 validation:
- Only change node counts IF a node was proven unnecessary AND removed
- Do NOT speculatively change counts

### Step 7: Run ALL foundation tests

Run the 8 foundation test files. ALL must pass.
If any fail: fix the test or fix the code (trace first).

### Step 8: Write README.md

This is not optional. This is a DELIVERABLE. The README must be
comprehensive enough that a developer can use the mediator without
reading the source code.

**Structure:**

```
# QueryMediator — Trilateral Data Hub

## 1. What It Is
## 2. Why It Exists
## 3. Architecture
   ### 3.1 The Trilateral Pattern
   ### 3.2 The Tree
   ### 3.3 The Cache
   ### 3.4 The Cascade
## 4. API Reference
   ### 4.1 get(path, ...)
   ### 4.2 peek(path)
   ### 4.3 put(path, data, ...)
   ### 4.4 bust(max_age, ...)
   ### 4.5 bust_path(path, ...)
   ### 4.6 dispatch(*paths)
   ### 4.7 refresh(*paths)
   ### 4.8 refresh_stale(prefix)
   ### 4.9 subscribe(pattern, callback)
   ### 4.10 diag(path)
   ### 4.11 batch()
   ### 4.12 peek_many(*paths)
## 5. Persistence
   ### 5.1 How It Works
   ### 5.2 Shard Files
   ### 5.3 Hydration on Startup
   ### 5.4 Save After Compute
## 6. Concurrency
   ### 6.1 Per-Path Compute Locks
   ### 6.2 Refreshing Guard
   ### 6.3 Thread Pool Executor
   ### 6.4 GIL Considerations
## 7. Registering Nodes
   ### 7.1 TreeRegistration
   ### 7.2 Dependencies
   ### 7.3 TTL Strategies
   ### 7.4 Resolver Patterns
## 8. Reading Data
   ### 8.1 get() — Compute If Needed
   ### 8.2 peek() — Never Compute
   ### 8.3 stale_ok — Accept Stale
   ### 8.4 force — Always Recompute
## 9. Invalidation
   ### 9.1 put() — Inject and Cascade
   ### 9.2 bust() — Age-Based Cleanup
   ### 9.3 bust_path() — Targeted Invalidation
   ### 9.4 Cascade Mechanics
## 10. Observability
   ### 10.1 diag() — Full State Snapshot
   ### 10.2 subscribe() — Live Events
   ### 10.3 EventBus Integration
## 11. Performance
   ### 11.1 Cache Hit: <1ms
   ### 11.2 Cascade: <5ms for 42 nodes
   ### 11.3 Hydration: <100ms for 15 shards
   ### 11.4 Shard Write: <50ms per 100KB
## 12. DO's and DON'Ts
## 13. Requirements Compliance Matrix
```

**Minimum length:** 450 lines. This is a gold-standard README.

### Step 9: Run full test suite (non-foundation tests too)

After all changes, run ALL 16 mediator test files. The ones that
test detect/devops/posture/index should still pass because:
- tree.py is unchanged
- core.py changes are additive (bust_path) or behavioral (dispatch)
- persistence.py changes maintain backward compatibility
- extra.py is kept (validated in Step 5)

If any test fails: trace the root cause, fix the code or test
(trace first). DO NOT change test logic without understanding why.

### Step 10: Compliance verification

Walk through every REQ-* from the requirements doc. For each:
1. Identify which file implements it
2. Identify which test verifies it
3. Mark status: PASS / FAIL / NOT TESTED
4. Write this into the README Section 13

---

## 3. Execution Order (Summary)

```
Step 1:  Verify tests pass              → GATE: all green
Step 2:  Evolve core.py (3 edits)       → GATE: foundation tests pass
Step 3:  Consolidate persistence.py     → GATE: foundation tests pass
Step 4:  Update __init__.py             → GATE: foundation tests pass
Step 5:  Validate extra.py, order regs  → GATE: each node justified
Step 6:  Verify test_mediator_startup   → GATE: test passes
Step 7:  Run ALL foundation tests       → GATE: all green
Step 8:  Write README.md                → GATE: 450+ lines, all sections
Step 9:  Run full test suite            → GATE: all green
Step 10: Compliance matrix              → GATE: all REQ-* mapped
```

Each step has a GATE. If the gate fails, we stop and fix before
proceeding. No step is skipped. No steps are parallelized.

---

## 4. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Changing dispatch_worker staleness logic breaks existing behavior | MEDIUM | HIGH | Test with real resolvers in Step 9 |
| Removing SHARD_MAP breaks hydration of old shard files | LOW | MEDIUM | Migration path: load old names on first startup |
| Extra nodes validated but turn out unnecessary later | LOW | LOW | Keep for now, reassess in Phase 8 when consumers are migrated |
| persistence.py consolidation breaks index node persistence | MEDIUM | HIGH | Run test_mediator_index.py in Step 9 |
| core.py changes cause regressions in domain tests | LOW | MEDIUM | Steps 2 is additive; Step 9 catches regressions |

---

## 5. What This Plan Does NOT Do

Explicitly out of scope for this plan:

1. ❌ Modify server.py
2. ❌ Modify any route file
3. ❌ Modify index_watcher.py (that's Phase 4)
4. ❌ Modify registrations/detect.py, devops.py, posture.py, index.py
5. ❌ Add new domain nodes
6. ❌ Change the FS watcher behavior
7. ❌ Touch the context processor
8. ❌ Modify the devops cache
9. ❌ Modify the posture cache
10. ❌ Change any UI template or JavaScript

This plan touches ONLY the foundation engine and its documentation.

---

*End of foundation implementation plan.*
*Next: Execute Step 1 (verify current tests pass).*
*After foundation: Infrastructure Requirements Document.*
