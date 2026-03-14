# Mediator-Native Index — Phased Implementation Plan

> **Purpose:** Step-by-step execution plan from current state to full spec
> **Companion to:** `mediator-index-spec.md` (the contract)
> **Created:** 2026-03-12
> **Principle:** Foundation first. One phase at a time. Verify before moving on.

---

## Current State Inventory

### What EXISTS and is WORKING ✅

| Component | Spec IDs | Status |
|-----------|----------|--------|
| 9 index nodes registered | SPEC-2.1–2.9 | ✅ All exist, all resolve |
| TTL=None on all index nodes | SPEC-3.1 | ✅ Fixed (was ttl=0) |
| Caching works | SPEC-3.2–3.5 | ✅ Compute once, serve from cache |
| `put("index.scan")` cascades within index | SPEC-3.4 | ✅ Invalidates all 8 dependents |
| Incremental symbols | SPEC-4.7–4.12 | ✅ Accumulator pattern works |
| Incremental peek | SPEC-4.13–4.17 | ✅ Delta-driven, tested |
| FS watcher | SPEC-5.1–5.6 | ✅ Dir-level polling, 18 tests |
| Bridge (file_map, dir_map, paths) | SPEC-7.1–7.8 | ✅ Re-entrancy guard in place |
| Dashboard endpoints | SPEC-8.1–8.5 | ✅ status/delta/rescan/rebuild |
| 338 tests passing | — | ✅ All green |

### What is MISSING ❌

| Component | Spec IDs | Gap |
|-----------|---------|-----|
| detect.* depends on index.classify | SPEC-6.1 | detect nodes are independent leaves |
| Cascade reaches detect | SPEC-6.2 | No dependency chain |
| Cascade reaches devops | SPEC-6.3 | Blocked by missing detect→index link |
| Cascade reaches posture | SPEC-6.4 | Blocked by missing detect→index link |
| Full cascade depth verified | SPEC-6.5 | Never tested end-to-end |
| Architecture doc aligned with reality | — | ttl=0 in doc, ttl=None in code |

---

## The Gap Visualized

### Current dependency graph (disconnected)

```
 ISLAND 1: INDEX                    ISLAND 2: DETECT → DEVOPS → POSTURE
 ─────────────────                  ──────────────────────────────────────

 index.scan                         detect.docker ──→ devops.docker ─┐
   ├── index.delta                  detect.k8s    ──→ devops.k8s    ─┤
   │     ├── index.symbols          detect.git    ──→ devops.git    ─┤
   │     │     └── index.peek       detect.github ──→ devops.github ─┤
   │     └── (no consumers)         detect.ci     ──→ devops.ci     ─┤
   ├── index.files                  detect.terraform→ devops.terraform
   ├── index.dirs                   detect.env    ──→ devops.env    ─┤
   ├── index.paths                  detect.security → devops.security│
   ├── index.classify               detect.packages → devops.packages│
   │     └── (no consumers) ←── !!  detect.quality  → devops.quality ├──→ posture.*
   └── index.stats                  detect.testing  → devops.testing │
                                    detect.docs   ──→ devops.docs   ─┤
        ← NO LINK →                detect.dns    ──→ devops.dns    ─┘
```

### Target dependency graph (connected)

```
 SINGLE TREE:
 ────────────

 index.scan (root — FS watcher drives this)
   ├── index.delta
   │     ├── index.symbols
   │     │     └── index.peek
   │     └── (future consumers)
   ├── index.files
   ├── index.dirs
   ├── index.paths
   ├── index.classify
   │     ├── detect.docker ──→ devops.docker ─┐
   │     ├── detect.k8s    ──→ devops.k8s    ─┤
   │     ├── detect.git    ──→ devops.git    ─┤
   │     ├── detect.github ──→ devops.github ─┤
   │     ├── detect.ci     ──→ devops.ci     ─┤
   │     ├── detect.terraform→ devops.terraform
   │     ├── detect.env    ──→ devops.env    ─┤
   │     ├── detect.security → devops.security│
   │     ├── detect.packages → devops.packages│
   │     ├── detect.quality  → devops.quality ├──→ posture.project ──→ posture.full → posture.summary
   │     ├── detect.testing  → devops.testing │
   │     ├── detect.docs   ──→ devops.docs   ─┤
   │     └── detect.dns    ──→ devops.dns    ─┘
   │
   └── index.stats
```

---

## Phase Plan

### Phase W1: Wire detect.* → index.classify

**Goal:** Add `index.classify` as a dependency for all detect nodes.
This is the bridge that connects the two islands.

**Scope:** ONE file change — `registrations/detect.py`

**What changes:**
```python
# BEFORE (current):
tree.register(TreeRegistration(
    path="detect.docker",
    resolver=lambda: docker_ops.docker_status(root),
    ttl=120,
    persist=True,
))

# AFTER (target):
tree.register(TreeRegistration(
    path="detect.docker",
    resolver=lambda: docker_ops.docker_status(root),
    ttl=120,
    persist=True,
    depends_on=["index.classify"],   # ← NEW
))
```

**Every detect.* node gets `depends_on=["index.classify"]`.**

**Why this works:**
- `index.classify` depends on `index.scan`
- `index.scan` is invalidated by the FS watcher
- Cascade: `put("index.scan")` → invalidates `index.classify` → invalidates all `detect.*`
- `detect.*` invalidation cascades to `devops.*` (already wired)
- `devops.*` invalidation cascades to `posture.*` (already wired via `devops.status`)

**What does NOT change:**
- The detect resolvers stay the same (subprocess calls)
- The detect TTLs stay the same (120s, 30s, 60s)
- No new logic, no new features — just adding a `depends_on` edge

**Behavior change:**
- When a file changes → watcher → `put("index.scan")` → cascade → `index.classify` invalidated
- → all `detect.*` cache entries invalidated
- → next `get("detect.docker")` recomputes (calls `docker_status()`)
- → its dependents (`devops.docker`) also invalidated → recompute on next access

**Risk:** detect resolvers are subprocess-heavy (subprocess calls for docker, k8s, etc.).
If the cascade triggers all 13 detect resolvers to recompute eagerly, that's expensive.
BUT — mediator invalidation is lazy. `put()` only removes cache entries. It does NOT
call resolvers. Resolvers only run when someone calls `get()`. So the cost is zero
until something actually accesses the data.

**Test plan:**
1. Register mediator with index + detect
2. Call `m.get("detect.docker")` → computed, cached
3. Call `m.put("index.scan")` → cascade
4. Verify `detect.docker` cache entry is gone
5. Call `m.get("detect.docker")` → recomputed
6. Verify cascade reaches all 13 detect nodes

**Spec coverage:** SPEC-6.1, SPEC-6.2

---

### Phase W2: Verify full cascade depth

**Goal:** Prove that `put("index.scan")` reaches detect → devops → posture.

**Scope:** Test-only. No code changes.

**What to test:**
1. Set up full mediator (index + detect + devops + posture)
2. Populate all nodes via `get()` (so everything is cached)
3. Call `put("index.scan")`
4. Verify cascade invalidated nodes across ALL domains:
   - All 8 index dependents
   - All 13 detect nodes
   - All 14 devops nodes (13 cards + status)
   - `posture.project` → `posture.full` → `posture.summary`
5. Measure: what is the total cascade set?

**This is the trilateral proof.** One `put()` at the root → the entire tree freshen.

**Test:**
```python
def test_full_cascade_from_scan():
    """put("index.scan") reaches all four domains."""
    # Populate everything
    for path in mediator.diag()["entries"]:
        mediator.get(path)
    
    # Fire at the root
    result = mediator.put("index.scan")
    
    # Verify cascade depth
    invalidated = set(result["invalidated"])
    
    # Index nodes
    assert "index.delta" in invalidated
    assert "index.classify" in invalidated
    
    # Detect nodes
    assert "detect.docker" in invalidated
    assert "detect.k8s" in invalidated
    
    # DevOps nodes
    assert "devops.docker" in invalidated
    assert "devops.status" in invalidated
    
    # Posture nodes
    assert "posture.full" in invalidated
    assert "posture.summary" in invalidated
```

**Spec coverage:** SPEC-6.3, SPEC-6.4, SPEC-6.5, SPEC-6.6

---

### Phase W3: Verify startup sequence

**Goal:** Confirm server startup registers all nodes in correct order.

**Scope:** Test-only. Verify the startup path.

**What to test:**
1. After `create_app()`, `get_mediator()` returns an instance
2. `mediator.diag()` shows all nodes from all 4 domains
3. Index nodes exist before watcher starts
4. Watcher thread is alive and daemon
5. First watcher cycle produces log of `put("index.scan")`

**Spec coverage:** SPEC-9.1–9.5

---

### Phase W4: Architecture doc alignment

**Goal:** Update the architecture doc to match reality.

**Scope:** Documentation only. No code.

**What to update:**
1. All `ttl=0` references → `ttl=None` with explanation
2. Remove bridge's symbols/peek section (it only provides file_map, dir_map, paths)
3. Mark Phase 8D/8E/8F as complete with accurate notes
4. Mark Phase W1/W2 states (once completed)
5. Update the cascade map to show the actual wired graph
6. Add note about per-path compute locks being non-reentrant

**Spec coverage:** Documentation alignment, no spec IDs

---

### Phase W5: Performance benchmarks

**Goal:** Verify performance contracts on the real project.

**Scope:** Benchmark script, no production code changes.

**What to measure:**
1. `scan_project()` timing on real project (~1,300 files)
2. `diff_scans()` timing with matching/different scans
3. `incremental_symbols()` timing with empty delta vs 1-file delta
4. `incremental_peek()` timing with empty delta vs 1-page delta
5. Watcher poll cycle timing (~241 dirs)
6. Full cascade timing: `put("index.scan")` → all nodes invalidated

**Spec coverage:** SPEC-10.1–10.7

---

## Execution Order

```
Phase W1: Wire detect.* → index.classify        [code: 1 file, ~13 lines]
    ↓ verify
Phase W2: Full cascade depth test                [test: 1 new test file]
    ↓ verify  
Phase W3: Startup sequence verification          [test: extend existing]
    ↓ verify
Phase W4: Architecture doc alignment             [docs only]
    ↓ verify
Phase W5: Performance benchmarks                 [benchmark script]
```

**Total code changes:** ~13 `depends_on` additions in `detect.py`
**Total new tests:** ~10–15 across W2 and W3
**Total doc updates:** Architecture doc corrections

---

## What This Achieves

After all 5 phases:

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

**This is the trilateral communication system. One signal at the root.
The entire tree knows it's stale. Each node recomputes only when asked.**

---

## Parking Lot (explicitly NOT in this plan)

These are real needs but separate milestones:

| Item | Why it's deferred |
|------|-------------------|
| Replace detect resolvers with index.classify consumers | Detect nodes currently call subprocesses. Replacing docker_status() with "read from index.classify" is a resolver rewrite, not a wiring change |
| Sharded disk persistence | Performance optimization — not needed for correctness |
| Settings UI for index phases | User preference — cosmetic, not foundational |
| Live event stream for index events | Observability enhancement |
| Remove legacy `start_project_index` | Can't remove until bridge is fully validated in production |
| `posture.project` depends on devops nodes | posture.project currently calls `run_all_probes()` independently. Wiring it to depend on devops.* would be correct but requires resolver changes |
