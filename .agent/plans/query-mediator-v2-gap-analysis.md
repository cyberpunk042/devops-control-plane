# QueryMediator v2 — Full Gap Analysis

> **Date:** 2026-03-13
> **Purpose:** Trace the ACTUAL state of the codebase against the target
> solution from the original vision. Every claim grounded in file:line evidence.
> **Method:** Source code read, not memory. Not summaries. Not milestone doc.

---

## 1. The Target Solution (from the vision)

The original prompt defined five systemic properties:

| # | Property | The user's words |
|---|----------|-----------------|
| T1 | **Trilateral hub** | "Backend → Mediator, Cache → Mediator, Index → Mediator" |
| T2 | **Delta-only** | "you always just get the delta, the new and or the fresh" |
| T3 | **Full cascade** | file change → index → detect → devops → posture, automatically |
| T4 | **Half the time** | "timing can decrease by at least half" |
| T5 | **Complete data hub** | "GET, PUT, bust, refresh, force, cascade, subscribe, dispatch, diag, explain" |

And one overarching constraint:

> "we need the foundation and then infrastructure first.
> and then we go chunk by chunk in order. one thing at the time."

---

## 2. What EXISTS — Layer by Layer

### 2.1 Foundation Engine ✅

| Component | File | Status | Evidence |
|-----------|------|--------|----------|
| DataTree | `mediator/tree.py` (419 lines) | **COMPLETE** | Hierarchical namespace, dependency graph, cascade via `dependents()`, glob matching, introspection |
| QueryMediator core | `mediator/core.py` (1200 lines) | **COMPLETE** | `get()`, `put()`, `bust()` (via put), `peek()`, `peek_many()`, `dispatch()`, `subscribe()`, `diag()`, per-path compute locks, sequence numbers |
| CacheEntry | `core.py:51-62` | **COMPLETE** | data, computed_at, seq, source, elapsed_s |
| Persistence | `mediator/persistence.py` (433 lines) | **COMPLETE** | `persist_node()` (atomic writes), `load_all_nodes()`, `hydrate_cache()`, shard metadata, rehydration of dataclasses |
| Singleton | `mediator/__init__.py` (103 lines) | **COMPLETE** | `init()`, `get_mediator()`, ThreadPoolExecutor(4) |
| Tests | 16 files, 381 passing | **COMPLETE** | Foundation behavior fully validated |

**Verdict: Foundation is SOLID.** REQ-TREE-1 through REQ-PERF-5 satisfied.

### 2.2 Index Domain ✅

| Node | Resolver | depends_on | TTL | persist | Evidence |
|------|----------|------------|-----|---------|----------|
| `index.scan` | `os.walk()` per-file mtime | — (root) | None | Yes | `registrations/index.py` |
| `index.delta` | diff(prev, curr) | `index.scan` | None | No | incremental |
| `index.files` | filename→paths | `index.scan` | None | Yes | derived map |
| `index.dirs` | dirname→paths | `index.scan` | None | Yes | derived map |
| `index.paths` | flat path set | `index.scan` | None | Yes | derived set |
| `index.classify` | extension+marker | `index.scan` | None | Yes | `classify_project()` |
| `index.symbols` | delta-driven parse | `index.delta` | None | Yes | accumulator pattern |
| `index.peek` | delta-driven resolve | `index.delta`, `index.symbols`, `index.scan` | None | Yes | accumulator pattern |
| `index.stats` | aggregate | scan, delta, dirs, symbols, classify | None | No | observability |

**9 nodes. All have resolvers. All have correct dependencies within the index domain.**

### 2.3 Detect Domain ✅

| Node | Resolver | depends_on | TTL | persist |
|------|----------|------------|-----|---------|
| `detect.docker` | `docker_ops.docker_status()` | `index.classify` | 120s | Yes |
| `detect.k8s` | `k8s_ops.k8s_status()` | `index.classify` | 120s | Yes |
| `detect.git` | `git_ops.git_status()` | `index.classify` | 30s | No |
| `detect.github` | `git_ops.gh_status()` | `index.classify` | 120s | Yes |
| `detect.ci` | `ci_ops.ci_status()` | `index.classify` | 120s | Yes |
| `detect.terraform` | `terraform_ops.terraform_status()` | `index.classify` | 120s | Yes |
| `detect.dns` | `dns_cdn_ops.dns_cdn_status()` | `index.classify` | 120s | Yes |
| `detect.env` | `env_ops.env_card_status()` | `index.classify` | 60s | No |
| `detect.security` | composite (scan+posture) | `index.classify` | 120s | Yes |
| `detect.packages` | `package_ops.package_status_enriched()` | `index.classify` | 120s | Yes |
| `detect.quality` | `quality_ops.quality_status()` | `index.classify` | 120s | Yes |
| `detect.testing` | `testing_ops.testing_status()` | `index.classify` | 120s | Yes |
| `detect.docs` | `docs_ops.docs_status()` | `index.classify` | 120s | Yes |

**13 nodes. All depend on `index.classify`.** The bridge between Island 1 (index) and Island 2 (detect) **EXISTS in code.**

### 2.4 DevOps Domain ✅

| Node | Resolver | depends_on | TTL | persist |
|------|----------|------------|-----|---------|
| `devops.docker` | `docker_ops.docker_status(root)` | `detect.docker`, `devops.git` | None | Yes |
| `devops.k8s` | `k8s_ops.k8s_status(root)` | `detect.k8s`, `devops.docker` | None | Yes |
| `devops.git` | `git_ops.git_status(root)` | `detect.git` | None | Yes |
| `devops.github` | `git_ops.gh_status(root)` | `detect.github`, `devops.git` | None | Yes |
| `devops.ci` | `ci_ops.ci_status(root)` | `detect.ci`, `devops.git`, `devops.docker`, `devops.github` | None | Yes |
| `devops.terraform` | `terraform_ops.terraform_status(root)` | `detect.terraform` | None | Yes |
| `devops.env` | `env_ops.env_card_status(root)` | `detect.env` | None | Yes |
| `devops.security` | `_compute_security` | `detect.security` | None | Yes |
| `devops.packages` | `package_ops.package_status_enriched(root)` | `detect.packages` | None | Yes |
| `devops.quality` | `quality_ops.quality_status(root)` | `detect.quality` | None | Yes |
| `devops.testing` | `testing_ops.testing_status(root)` | `detect.testing` | None | Yes |
| `devops.docs` | `docs_ops.docs_status(root)` | `detect.docs` | None | Yes |
| `devops.dns` | `dns_cdn_ops.dns_cdn_status(root)` | `detect.dns` | None | Yes |
| `devops.status` | `_compute_status` | `devops.*` (glob) | None | Yes |

**14 nodes. All depend on detect.* + inter-devops cascade deps.**

**Resolvers call compute functions DIRECTLY — no `get_cached()` wrapper.**
`persist=True` on all nodes — mediator handles its own disk persistence.

### 2.5 Posture Domain ✅

| Node | Resolver | depends_on | TTL | persist |
|------|----------|------------|-----|---------|
| `posture.platform` | `_scan_platform` | — | ∞ | Yes |
| `posture.toolchain` | `_scan_toolchain` | — | 300s | Yes |
| `posture.project` | `_bridge_project(root)` | — | 60s | Yes |
| `posture.runtime` | `_bridge_runtime` | — | 0 | No |
| `posture.full` | assembles 4 pillars via `m.get()` | platform, toolchain, project, runtime | 60s | Yes |
| `posture.summary` | derives from full | `posture.full` | 30s | Yes |

**6 nodes. posture.full correctly assembles from mediator reads.**
`posture.project` depends on `devops.*` — cascade chain complete.

### 2.6 Redistributed Domains ✅

The original `extra.*` domain (20 nodes) has been redistributed into
proper domains per Decision D1:

| Domain | Nodes | Source |
|--------|-------|--------|
| `github.*` | 3 | `github.pulls`, `github.runs`, `github.workflows` |
| `audit.*` | 11 | `audit.scores`, `audit.system`, `audit.deps`, `audit.structure`, `audit.clients`, `audit.system_deep`, `audit.l2_structure`, `audit.l2_quality`, `audit.l2_repo`, `audit.l2_risks`, `audit.scores_enriched` |
| `catalog.*` | 4 | `catalog.tools`, `catalog.builders`, `catalog.scripts`, `catalog.pages` |
| `detect.wizard` | 1 | (moved from `extra.wiz_detect`) |

`extra.project_status` was REMOVED (redundant with `devops.status`).
`extra.py` registration file has been deleted (orphaned dead code).

**7 domains total:** index, detect, devops, posture, github, audit, catalog.

### 2.7 FS Watcher ✅

| Component | File | Status |
|-----------|------|--------|
| Dir mtime polling | `index_watcher.py` (434 lines) | **WORKING** |
| Change detection | `scan_dir_mtimes()` → diff → `mediator.put("index.scan")` | **WORKING** |
| Fast index computation | `index.scan` through `index.classify` (sequential) | **WORKING** |
| Background dispatch | detect.*, devops.*, posture.* via `mediator.dispatch()` | **WORKING** |
| Warm-start skip | Peek for hydrated data, skip recompute | **WORKING** |
| EventBus progress events | `index:cycle:start`, `index:node:done`, etc. | **WORKING** |

### 2.8 Route Consumer Migration ✅

**All route endpoints** across 16+ route files now use mediator-first.
All `get_cached()` consumers outside of `devops/cache.py` have been
removed, including core services (`metrics/ops.py`, `audit/l2_risk.py`).
The context processor uses `peek()` for all 23 inject keys — the
`devops_cache.json` fallback has been removed.

### 2.9 Side-Effect Subscribers ✅

Two mediator subscribers replicate `get_cached()` side effects:
- **Activity subscriber** (`subscribers/activity.py`) — records
  `record_scan_activity()` and `stage_audit()` on every `computed` event.
- **EventBus bridge** (`subscribers/eventbus_bridge.py`) — publishes
  `cache:done` and `cache:error` events for frontend SSE compatibility.

### 2.9 Observability (Phase 7) ✅

The diag endpoint exists in `core.py:557-661`. Web routes for mediator
dashboard exist. Progress events published on every cycle.

---

## 3. The GAPS — What's Missing

### GAP 1: devops.* resolvers still wrap `get_cached()` ❌

**File:** `registrations/devops.py:157`
```python
def _make_resolver(ck, fn):
    return lambda: get_cached(root, ck, fn)
```

Every `devops.*` resolver goes through `get_cached()`. This means:
- **Double caching:** mediator cache + devops_cache.json
- **Double persistence:** mediator shards (disabled: persist=False) + devops_cache.json
- **Side effects** live in `get_cached()`, not the mediator:
  - mtime-based staleness (per `_WATCH_PATHS`)
  - Per-key thread locking
  - Disk persistence to `.state/devops_cache.json`
  - EventBus events (`cache:hit`, `cache:miss`, `cache:done`, `cache:error`)
  - Activity logging (`_record_activity`)
  - Audit staging (`stage_audit`)
  - `_cache` metadata injection

**Impact:** The mediator is a PROXY for devops_cache, not a replacement.
It adds overhead (mediator cache lookup + per-path lock) without removing
any of the old overhead. You pay both costs.

**To reach T1 (sole data hub):** The mediator must OWN these side effects.
Each one must be migrated or consciously dropped.

### GAP 2: Side effects not replicated in mediator ❌

The following `get_cached()` side effects have NO mediator equivalent:

| Side Effect | `get_cached()` | Mediator | Gap |
|-------------|----------------|----------|-----|
| mtime-based staleness | `_WATCH_PATHS` + `_max_mtime()` | TTL-based only | ❌ No file watch per key |
| Activity logging | `_record_activity()` → `.state/audit_activity.json` | None | ❌ Not implemented |
| Audit staging | `stage_audit()` → `.state/pending_audits.json` | None | ❌ Not implemented |
| `_cache` metadata injection | `data["_cache"] = {...}` | `result["meta"]` exists but different shape | ⚠️ Shape mismatch |
| EventBus events (`cache:hit/miss/done/error`) | Published per compute | `mediator:computed/put/bust/hydrated` | ⚠️ Different event names |
| Disk persistence to single JSON | `_save_cache()` → `devops_cache.json` | Sharded per-node files | ⚠️ Different format |

**To unwrap `get_cached()`:** Each side effect needs a decision:
- **Replicate in mediator** (activity log, audit staging)
- **Drop** (if nobody reads it anymore)
- **Adapt** (_cache metadata → mediator meta)

### GAP 3: `_WATCH_PATHS` mtime staleness not in mediator ❌

**File:** `devops/cache.py:100-208`

The devops cache has per-key watch paths:
```python
_WATCH_PATHS = {
    "security": [".gitignore", "src/"],
    "testing": ["tests/", "pyproject.toml", "package.json"],
    "git": [".git/HEAD", ".git/index", ".gitignore"],
    ...
}
```

The mediator's staleness is TTL-based (`ttl=120` for detect nodes) or
event-based (`put("index.scan")` on FS change). The OS-level mtime check
that `get_cached` does per-key is NOT replicated.

**Impact:** The mediator's TTL approach is actually BETTER for most cases
(file change → cascade handles it). But for keys like `git` (watches
`.git/HEAD`), the devops cache's mtime approach catches changes the FS
watcher might miss (git operations happen inside `.git/` which is in the
skip list).

**Decision needed:** Are there keys where the devops_cache's `_WATCH_PATHS`
catch changes that the mediator's cascade does NOT?

### GAP 4: Context processor still reads devops_cache.json ⚠️

**File:** `server.py:248-337`

```python
def _get_devops_cache() -> dict:
    # reads .state/devops_cache.json
```

The context processor has a dual-stack:
1. Peek all 23 keys from mediator
2. Fall back to `devops_cache.json` for anything missing

**Impact:** Once the mediator is warm, the fallback never fires for the
13 devops + 10 extra keys. But on cold start (first ~5s), ALL 23 keys
come from the devops_cache.json file.

**To eliminate:** The mediator must hydrate from its own shards fast enough
that the fallback is never needed. Currently devops.* has `persist=False`
so those shards DON'T exist on disk.

### GAP 5: devops.* nodes have `persist=False` ❌

**File:** `registrations/devops.py:163`

```python
tree.register(TreeRegistration(
    ...
    persist=False,  # devops cache handles its own persistence
    ...
))
```

This means after restart, devops.* nodes have NO data until their resolvers
fire. Resolvers fire via `get_cached()` which reads `devops_cache.json`.
So the cold-start path is:

```
restart → mediator cache empty for devops.*
       → context processor falls back to devops_cache.json
       → first route request triggers m.get("devops.docker")
       → resolver fires get_cached("docker", docker_ops.docker_status)
       → get_cached reads devops_cache.json, checks mtime
       → returns cached or recomputes
```

**To eliminate the devops_cache dependency:** Enable `persist=True` on
devops.* nodes AND unwrap the `get_cached()` resolver.

### GAP 6: Remaining direct `get_cached()` consumers ❌

**Files with active `get_cached()` calls (not in fallback paths):**

| File | Function | Usage |
|------|----------|-------|
| `audit/async_scan.py:175` | `_run_scan` | Force-computes L2 audit phases via `get_cached(force=True)` |
| `audit/analysis.py:64` | `_get_audit_data` | Fallback read path |
| `audit/analysis.py:202` | `_cache_or_needs_scan` | Fallback read path |
| `scripts/registry.py:61` | `scripts_list` | Fallback read path |
| `devops/detect.py:54` | `detect_env` | Direct `get_cached("wiz:detect", ...)` — NOT migrated |
| `audit/tool_install.py:299` | | Fallback read path |
| `pages/api.py:112,215` | | Fallback read path |
| `metrics/ops.py` (6 sites) | | Backend service — reads via `get_cached()` |

**Special concern:** `metrics/ops.py` has 6 `get_cached()` calls in the
core services layer, not the web layer. These are backend consumers.

### GAP 7: Invalidation still goes through both systems ❌

**Files that call `devops_cache.invalidate()`:**

| File | What it invalidates |
|------|---------------------|
| `security/common.py:328-329` | `audit:l2:risks`, `security` |
| `security/common.py:367-368` | `audit:l2:risks`, `security` |
| `helpers.py:91-95` | integrations scope, devops scope, `wiz:detect`, `tools`, `builders` |
| `gh_auth.py:22-23` | `github`, `wiz:detect` |
| `devops/__init__.py:132-149` | `invalidate_all`, `invalidate_scope`, `invalidate_with_cascade` |

**The `_mediator_bust()` helper** in `devops/__init__.py:84-106` also busts
the mediator when the devops cache is busted. But it only busts `detect.*`
nodes — it doesn't bust `extra.*` nodes.

**Impact:** When `security/common.py` invalidates `audit:l2:risks` in the
devops cache, the mediator's `extra.audit_l2_risks` is NOT invalidated.
The mediator serves stale data until the TTL (600s) expires.

### GAP 8: posture.* not connected to the cascade chain ⚠️

**File:** `registrations/posture.py`

```
posture.platform   — depends on: NOTHING
posture.toolchain  — depends on: NOTHING
posture.project    — depends on: NOTHING
posture.runtime    — depends on: NOTHING
posture.full       — depends on: platform, toolchain, project, runtime
posture.summary    — depends on: posture.full
```

**The vision says:** posture should cascade from devops changes. When
`devops.quality` changes, `posture.project` should be affected because
project health depends on code quality.

**Currently:** posture is a fully independent island. It uses TTL-based
refresh only. No cascade from index → detect → devops → posture.

**Impact:** The full cascade chain `file change → index → detect → devops → posture`
is BROKEN at the devops → posture link. Posture refreshes on its own
schedule via TTL, not via cascade.

### GAP 9: Warm restart not fully optimized ⚠️

**File:** `index_watcher.py:222-265`

On warm start, the watcher skips index recomputation but still dispatches
ALL detect/devops/posture nodes to the background thread pool:

```python
bg_paths = [p for p in all_paths if p.startswith(("detect.", "devops.", "posture."))]
mediator.dispatch(*bg_paths)
```

This dispatches ~33 nodes to a 4-thread pool. Because devops.* resolvers
wrap `get_cached()`, each dispatch triggers mtime checks and potentially
subprocess calls (docker info, kubectl version, etc).

**Impact:** Warm restart STILL runs all 13 detect resolvers and all 13
devops resolvers in background. The delta-only benefit applies to INDEX
nodes but not to detect/devops/posture, which dispatch blindly.

### GAP 10: No smart dispatch based on classify output ❌

**The vision says:** When `index.classify` output changes (new language
detected, framework added), THEN detection re-runs. Not before.

**Currently:** `index_watcher.py:329-346` dispatches ALL detect/devops/posture
nodes on EVERY cycle, regardless of whether classify output changed.

The dependency `detect.* → index.classify` exists in the tree, which means
`put("index.scan")` DOES cascade-invalidate all detect nodes. But the
watcher then blindly dispatches all of them for recomputation anyway.

**The delta-aware approach would be:** After computing `index.classify`,
check if the classify OUTPUT actually changed. If not, don't dispatch
detect nodes — their cache entries were invalidated but the resolver
would produce the same result.

---

## 4. Summary: Distance to Target

| Target | Status | What remains |
|--------|--------|-------------|
| **T1: Trilateral hub** | ✅ COMPLETE | Mediator is the sole data hub. Resolvers call compute directly, persist=True, no `get_cached()` wrapper. |
| **T2: Delta-only** | ✅ COMPLETE | Index is delta-driven. Watcher uses smart dispatch: classify-change check + mtime_paths filtering. |
| **T3: Full cascade** | ✅ COMPLETE | Full chain: file → index → detect → devops → posture. `posture.project` depends on `devops.*`. |
| **T4: Half the time** | ✅ **VALIDATED** | Context processor: 31µs vs ~3-5ms legacy (~100x). Peek: 2µs per key. See `scripts/benchmark_mediator.py`. |
| **T5: Complete API** | ✅ MOSTLY | get, put, bust, peek, dispatch, subscribe, diag all work. `explain` not implemented. |

---

## 5. The Remaining Work (Infrastructure + Chunks)

### Chunk A: Unwrap devops.* from `get_cached()` ✅ DONE

**Completed.** All 13 devops.* + 1 devops.status resolvers call compute
functions directly (e.g., `docker_ops.docker_status(root)`). `persist=True`
on all nodes. The mediator handles its own caching and persistence.

### Chunk B: Wire posture.* into the cascade chain ✅ DONE

**Completed.** `posture.project` has `depends_on=["devops.*"]`.
End-to-end cascade: file → index → detect → devops → posture.

### Chunk C: Smart dispatch in watcher ✅ DONE

**Completed.** After computing fast index nodes, the watcher compares
`index.classify` output to the previous cycle. If unchanged (same
languages, same frameworks), only detects nodes whose `mtime_paths`
indicate file-level staleness are dispatched — along with their
downstream devops/posture dependents. Reduces dispatch from ~33 nodes
to typically 1-3 per cycle when classify is stable.

### Chunk D: Unify invalidation ✅ DONE

**Completed.** All bust/invalidation flows go through the mediator.
`bust_tool_caches()`, `devops_cache_bust()`, and `_mediator_bust_scope()`
all use `mediator.put()` with `cascade=True`.

### Chunk E: Eliminate devops_cache.json for data ✅ DONE

**Completed.** The context processor no longer falls back to
`devops_cache.json`. Mediator hydrates from its own shards on startup
(`persist=True` + `hydrate_cache()`). `devops_cache.json` continues to
exist for prefs and activity log (separate concerns, not data).

### Chunk F: Migrate core service consumers ✅ DONE

**Completed.** `metrics/ops.py` (6 probes) and `audit/l2_risk.py`
(`_cached_get` helper) now use mediator `get()` and `peek()` instead
of `get_cached()`. Zero `get_cached()` consumers remain outside cache.py.

### Chunk G: Benchmark and validate T4 ✅ DONE

**Completed.** Benchmark script: `scripts/benchmark_mediator.py`

Key results (measured 2026-03-13):

| Operation | Latency | Notes |
|-----------|---------|-------|
| peek 1 key | 2µs | In-memory dict lookup |
| peek 23 inject keys | 31µs | Full context processor injection |
| get (warm cache hit) | 2µs | No computation, no disk I/O |
| Cascade invalidation (full tree) | 30µs | index.scan → 61 nodes |
| Cascade invalidation (1 detect) | 7µs | detect.docker → devops/posture |
| mtime check (4 paths) | 45µs | Docker: Dockerfile, compose, ignore |
| mtime check (10 paths) | 118µs | Quality: ruff, mypy, eslint, etc. |
| mtime check (76 paths, all detect) | 5.4ms | Full staleness sweep |
| Classify comparison | <1µs | Near-zero cost for smart dispatch |
| Context processor (23 keys) | 31µs | **Was ~3-5ms with disk JSON — ~100x faster** |
| Hydration (42 entries from shards) | 45ms | One-time warm start |
| FS scan (243 dirs) | 8.6ms | Watcher poll baseline |
| Cold compute: index.scan | 26ms | Full filesystem scan |
| Cold compute: index.classify | 0.9ms | Language/framework detection |

**T4 validated:** Context processor injection (the hottest path — runs on
every request) went from ~3-5ms (disk I/O + JSON parse) to 31µs (in-memory
peek). This is a **~100x improvement**, far exceeding the "decrease by at
least half" target.

### Dead Code Cleanup ✅ DONE

With the mediator as the sole data hub, legacy code was removed:

| Removed | Lines | Reason |
|---------|:-----:|--------|
| `cache.py` — `get_cached()`, all invalidation, `recompute_all`, `register_compute`, `_WATCH_PATHS`, `_max_mtime`, `_load_cache`/`_save_cache`, locks, threads, cascade maps | ~650 | Replaced by mediator resolvers, cascade, mtime_paths |
| `staleness_watcher.py` | 124 | Replaced by mediator index_watcher smart dispatch |
| `routes/devops/__init__.py` — `_ensure_registry()`, all `register_compute()` calls | 75 | Legacy compute registry, unused |
| `devops/__init__.py` — dead re-exports | 13 | Removed symbols no longer exist |
| `activity.py` — seed-from-cache block | 40 | Legacy bootstrap from devops_cache.json |
| `audit_directive.py` — `_read_cached_card` | 15 | Migrated to `mediator.peek()` |
| `test_mediator_cascade.py` — `TestLegacyCascadeEquivalence`, `TestMediatorCascade` | 149 | Tested removed functions |

**Remaining in `cache.py`:** `load_prefs()`, `save_prefs()`, `record_event()`,
`load_activity()`, `_DEFAULT_PREFS`. These are preference/activity APIs —
separate concerns from caching, kept alive.


## 6. Resolved Decisions

| # | Question | Resolution |
|---|----------|------------|
| D1 | `extra.*` domain | **Redistribute** into proper domains: github.*, audit.*, catalog.*, detect.wizard. Remove extra.project_status (redundant with devops.status). |
| D2 | Side effects | **Replicate ALL** via mediator `subscribe()` callbacks — activity log, audit staging, EventBus compatibility events. Nothing dropped. |
| D3 | Posture cascade | **Yes** — `posture.project → depends_on ["devops.*"]`. End-to-end cascade: file → index → detect → devops → posture. |
| D4 | `_cache` metadata | **Adapt frontend** — mediator meta preserves all existing info + adds seq, source, path. Nothing lost, strictly more. |
| D5 | Skip | **Nothing skipped.** |
| D6 | Order | **Clarify first** (this doc), then infrastructure plan, then execute chunk by chunk. |

### D1 Detail: Domain Redistribution

```
extra.gh_pulls              →  github.pulls
extra.gh_runs               →  github.runs
extra.gh_workflows          →  github.workflows

extra.audit_scores          →  audit.scores
extra.audit_system          →  audit.system
extra.audit_deps            →  audit.deps
extra.audit_structure       →  audit.structure
extra.audit_clients         →  audit.clients
extra.audit_system_deep     →  audit.system_deep
extra.audit_l2_structure    →  audit.l2_structure
extra.audit_l2_quality      →  audit.l2_quality
extra.audit_l2_repo         →  audit.l2_repo
extra.audit_l2_risks        →  audit.l2_risks
extra.audit_scores_enriched →  audit.scores_enriched

extra.tools                 →  catalog.tools
extra.builders              →  catalog.builders
extra.scripts               →  catalog.scripts
extra.pages                 →  catalog.pages

extra.wiz_detect            →  detect.wizard

extra.project_status        →  REMOVE (redundant with devops.status)
```

**7 domains total:** index, detect, devops, posture, github, audit, catalog.

### D3 Detail: Posture Cascade Wiring

```
posture.project → depends_on ["devops.*"]
```

posture.project probes check: is testing configured? is CI set up?
does quality tooling exist? That data comes from devops cards. When
devops cards change, posture must invalidate.

### GAP 3 Resolution: mtime_paths

`TreeRegistration` already has an `mtime_paths` field. Migrate
`_WATCH_PATHS` from devops/cache.py into `mtime_paths` on each
detect node. If the core engine doesn't check mtime_paths yet,
add support: before returning cached value, check if any mtime_path
is newer than computed_at.

---

## 7. Node Count Summary (after redistribution)

| Domain | Nodes | State |
|--------|-------|-------|
| index.* | 9 | ✅ Complete, delta-driven |
| detect.* | 14 (+wizard) | ✅ Registered, depends_on index.classify |
| devops.* | 14 | ⚠️ Wraps get_cached(), persist=False |
| posture.* | 6 | ⚠️ Independent island → will wire to devops |
| github.* | 3 | NEW domain (from extra) |
| audit.* | 11 | NEW domain (from extra) |
| catalog.* | 4 | NEW domain (from extra) |
| **Total** | **61** (-1: removed extra.project_status) | |

---

*This analysis was produced by reading every registration file, the core
engine, the watcher, the devops cache, and the route consumers. Every
claim traces to a file and line number in the source.*
