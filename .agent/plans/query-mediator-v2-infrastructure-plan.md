# QueryMediator v2 — Infrastructure & Chunks Plan

> **Date:** 2026-03-13
> **Prerequisite:** `query-mediator-v2-gap-analysis.md` (all decisions resolved)
> **Principle:** Foundation first, chunk by chunk, one at a time, each verifiable.

---

## Phase I: Infrastructure Prerequisites

These chunks add capabilities the mediator engine NEEDS before we can
unwrap `get_cached()` and make it the sole data hub.

### Chunk 1: mtime_paths staleness in core engine

**What:** The `TreeRegistration.mtime_paths` field exists on the data model
but `core.py:get()` does NOT check it. Add mtime-based staleness checking.

**Why:** When `get_cached()` is unwrapped, the mediator must detect file
changes that the FS watcher misses (e.g., `.git/HEAD` changes on branch
switch, `.git/` is in the watcher's skip list). The `_WATCH_PATHS` dict
in `devops/cache.py` captures exactly these per-key file watches.

**Scope:**
- `mediator/core.py` — in `get()`, after TTL check, before returning cached
  entry: if `node.mtime_paths` is set, check `max(mtime(p) for p in paths)`
  against `entry.computed_at`. If any path is newer → stale, recompute.
- `mediator/tree.py` — field already exists, no change needed.

**Files touched:** `core.py` (1 file)

**Verification:** Add test: register node with `mtime_paths=["/tmp/test_file"]`,
get() returns cached. Touch the file. get() recomputes. Existing 381 tests
still pass.

**Estimated size:** ~30 lines in core.py + 1 test file (~60 lines)

---

### Chunk 2: Post-compute hooks (subscribe on get)

**What:** The `subscribe()` mechanism already fires after `get()` completes
computation (via `_publish_change` at `core.py:371`). Verify this is
sufficient for activity logging and audit staging.

**Analysis:** `_publish_change` after compute sends `writes=[path]`.
Subscriber callbacks receive `{"type": "write", "paths": [path], ...}`.
This IS the right hook point. The subscriber needs access to:
- `path` ✅ (in the event payload)
- `data` (the computed result) — ⚠️ NOT in the current payload
- `elapsed_s` — ⚠️ NOT in the current payload
- `status` (ok/error) — ⚠️ NOT in the current payload
- `error` (if any) — ⚠️ NOT in the current payload

**Scope:** Enrich the `_publish_change` / subscriber notification payload
to include `data`, `elapsed_s`, `status`, and `error` when the trigger
is a computation (not a put/invalidation).

**Files touched:** `core.py` (1 file — `_publish_change` and `_notify_subscribers`)

**Verification:** Add test: subscribe to `"devops.*"`, call `m.get("devops.test")`,
verify callback receives data, elapsed_s, status. Existing tests still pass.

**Estimated size:** ~20 lines in core.py + 1 test (~40 lines)

---

### Chunk 3: Activity logging subscriber

**What:** Create a subscriber that replicates `get_cached()`'s two side effects:
1. Activity logging → `_record_scan_activity()` → `.state/audit_activity.json`
2. Audit staging → `stage_audit()` → `.state/pending_audits.json`

**Why:** These features must exist in the mediator BEFORE `get_cached()` is
unwrapped. Otherwise unwrapping loses observability and audit data.

**Scope:**
- New file: `mediator/subscribers/activity.py`
  - `register_activity_subscriber(mediator)` — subscribes to `"devops.*"` + `"audit.*"`
  - Callback calls `_record_scan_activity()` and `stage_audit()` using
    the enriched payload from Chunk 2
- Called from `registrations/__init__.py:register_all()` after all domains

**Files touched:** New file `subscribers/activity.py`, edit `registrations/__init__.py`

**Verification:** Start server, trigger a devops compute, verify
`.state/audit_activity.json` gets an entry AND `.state/pending_audits.json`
gets a staging record. Compare output shape with current `get_cached()` output.

**Estimated size:** ~80 lines new file + ~5 lines init edit

---

### Chunk 4: EventBus compatibility bridge

**What:** Create a subscriber that publishes legacy EventBus events
(`cache:hit`, `cache:miss`, `cache:done`, `cache:error`) so existing
SSE consumers (Live Events panel) continue working.

**Why:** The frontend's Live Events panel listens for `cache:*` events.
The mediator publishes `mediator:*` events. During transition, BOTH must
fire. After full migration, the legacy events can be deprecated.

**Scope:**
- New file: `mediator/subscribers/eventbus_compat.py`
  - Subscribes to `"devops.*"` + `"detect.*"`
  - On compute event → publishes `cache:done` with same payload shape
  - On cache hit (peek returns data) → this is harder, cache hits happen
    in `get()` before the subscriber fires. Revisit: do we need `cache:hit`?
    The current mediator already handles this via `_publish_change` with
    `source="cached"` — map this to `cache:hit`.

**Files touched:** New file `subscribers/eventbus_compat.py`, edit `registrations/__init__.py`

**Verification:** Start server, check SSE stream still shows cache lifecycle
events in the Live Events panel.

**Estimated size:** ~60 lines new file + ~3 lines init edit

---

## Phase II: Domain Restructuring

### Chunk 5: Redistribute extra.* into proper domains

**What:** Split `registrations/extra.py` into:
- `registrations/github.py` — 3 nodes (pulls, runs, workflows)
- `registrations/audit.py` — 11 nodes (scores through enriched)
- `registrations/catalog.py` — 4 nodes (tools, builders, scripts, pages)
- Move `extra.wiz_detect` → `detect.wizard` in `registrations/detect.py`
- Remove `extra.project_status` (redundant with `devops.status`)
- Delete `registrations/extra.py`

**Why:** The `extra` namespace was a temporary holding area. Proper domain
names make the tree self-documenting and enable correct cascade wiring.

**Scope:**
- New files: `registrations/github.py`, `registrations/audit.py`, `registrations/catalog.py`
- Edit: `registrations/detect.py` (add `detect.wizard`)
- Edit: `registrations/__init__.py` (update registration order)
- Edit: `server.py` `_KEY_TO_MEDIATOR` map (update paths)
- Edit: All route consumers that reference `extra.*` mediator paths
- Delete: `registrations/extra.py`

**Consumer updates needed:**
```
server.py _KEY_TO_MEDIATOR:
    "gh-pulls"           → "github.pulls"     (was "extra.gh_pulls")
    "gh-runs"            → "github.runs"       (was "extra.gh_runs")
    "gh-workflows"       → "github.workflows"  (was "extra.gh_workflows")
    "audit:scores"       → "audit.scores"      (was "extra.audit_scores")
    "audit:system"       → "audit.system"      (was "extra.audit_system")
    "audit:deps"         → "audit.deps"        (was "extra.audit_deps")
    "audit:structure"    → "audit.structure"    (was "extra.audit_structure")
    "audit:clients"      → "audit.clients"     (was "extra.audit_clients")
    "wiz:detect"         → "detect.wizard"     (was "extra.wiz_detect")
    "project-status"     → "devops.status"     (was "extra.project_status")
```

Route files that reference `extra.*` paths:
```
routes/integrations/github.py  — extra.gh_pulls, extra.gh_runs, extra.gh_workflows
routes/audit/analysis.py       — extra.audit_* paths
routes/scripts/registry.py     — extra.scripts
routes/devops/detect.py        — extra.wiz_detect
```

**Files touched:** ~12 files

**Verification:** All route endpoints return same data. No `extra.*` in
`mediator.tree.all_paths()`. `_KEY_TO_MEDIATOR` maps to correct new paths.
Context processor still injects all 23 keys. Existing tests pass.

**Estimated size:** 3 new files (~100 lines each), ~50 lines of edits across consumers

---

### Chunk 6: Wire posture cascade

**What:** Add `depends_on=["devops.*"]` to `posture.project`.

**Why:** Project health probes evaluate testing, CI, quality — all devops
card outputs. When devops changes, posture must invalidate.

**Scope:**
- Edit `registrations/posture.py`: add `depends_on=["devops.*"]` to
  `posture.project` registration

**Files touched:** `posture.py` (1 file, 1 line)

**Verification:** `m.put("devops.quality")` → verify `posture.project`
appears in invalidated list. End-to-end: `m.put("index.scan")` cascades
through detect → devops → posture. Run `m.diag()` to inspect dependency graph.

**Estimated size:** 1 line change + test verification

---

### Chunk 7: Add mtime_paths to detect nodes

**What:** Migrate `_WATCH_PATHS` from `devops/cache.py` into `mtime_paths`
on each `detect.*` node registration.

**Why:** When `get_cached()` is unwrapped (Phase III), these per-key file
watches must be preserved. The mtime_paths engine (Chunk 1) provides the
mechanism; this chunk provides the data.

**Scope:**
- Edit `registrations/detect.py`: add `mtime_paths` to each registration

**Mapping from `_WATCH_PATHS`:**
```python
detect.docker     → mtime_paths=["Dockerfile", "docker-compose.yml", "docker-compose.yaml", ".dockerignore"]
detect.k8s        → mtime_paths=["k8s/", "kubernetes/", "charts/"]
detect.git        → mtime_paths=[".git/HEAD", ".git/index", ".gitignore"]
detect.github     → mtime_paths=[".github/"]
detect.ci         → mtime_paths=[".github/workflows/", ".gitlab-ci.yml", "Jenkinsfile", ".circleci/"]
detect.terraform  → mtime_paths=["terraform/", "main.tf", ".terraform.lock.hcl"]
detect.dns        → mtime_paths=["CNAME", "cloudflare/"]
detect.env        → mtime_paths=[".env", ".env.example", ".env.local"]
detect.security   → mtime_paths=[".gitignore", ".gitignore.global", "src/"]
detect.packages   → mtime_paths=["pyproject.toml", "requirements.txt", "package.json", "Cargo.toml", "go.mod"]
detect.quality    → mtime_paths=["pyproject.toml", "setup.cfg", ".flake8", ".pylintrc", "tox.ini"]
detect.testing    → mtime_paths=["tests/", "pyproject.toml", "package.json", "setup.cfg"]
detect.docs       → mtime_paths=["docs/", "README.md", "CHANGELOG.md", "mkdocs.yml"]
```

**Files touched:** `registrations/detect.py` (1 file)

**Verification:** `m.diag()` shows mtime_paths on each detect node.
Touch a watched file → `m.get("detect.docker")` returns fresh compute
even if TTL hasn't expired.

**Estimated size:** ~13 lines of changes (1 per node)

---

## Phase III: The Big Unwrap

### Chunk 8: Unwrap devops.* from get_cached + enable persist

**What:** Replace `get_cached()` wrapper with direct compute function.
Enable `persist=True` on all devops.* nodes.

**Why:** This is THE central change. It makes the mediator the sole data
hub for devops cards, eliminating double caching.

**Before:**
```python
def _make_resolver(ck, fn):
    return lambda: get_cached(root, ck, fn)

tree.register(TreeRegistration(
    path="devops.docker",
    resolver=_make_resolver("docker", lambda: docker_ops.docker_status(root)),
    ttl=None,
    persist=False,
    depends_on=deps,
))
```

**After:**
```python
tree.register(TreeRegistration(
    path="devops.docker",
    resolver=lambda: docker_ops.docker_status(root),
    ttl=None,       # staleness via cascade + mtime_paths (on detect node)
    persist=True,   # mediator handles persistence
    depends_on=deps,
))
```

**Prerequisites:** Chunks 1-4 must be complete (mtime_paths, post-compute
hooks, activity subscriber, EventBus compat). Otherwise unwrapping loses
features.

**Scope:**
- Edit `registrations/devops.py`:
  - Remove `from src.core.services.devops.cache import get_cached`
  - Remove `_make_resolver` wrapper
  - Set `persist=True` on all 13 card nodes
  - `devops.status` resolver: call `_compute_status()` directly (not via get_cached)

**Files touched:** `registrations/devops.py` (1 file)

**Verification:**
1. Start server. All card endpoints return data.
2. `.state/mediator_shards/` contains `devops.docker.json`, etc.
3. `devops_cache.json` does NOT get updated for card keys anymore.
4. Activity log still records compute events (from subscriber).
5. SSE still shows cache lifecycle events (from compat subscriber).
6. Warm restart: mediator hydrates devops.* from shards (no fallback to devops_cache.json).

**Estimated size:** ~40 lines of changes in devops.py

---

## Phase IV: Unify Invalidation

### Chunk 9: Replace devops_cache.invalidate() → mediator.put()

**What:** All code that directly calls `devops_cache.invalidate()` must
use mediator invalidation instead.

**Scope:**
```
security/common.py:328-329   → mediator.put("devops.security") + mediator.put("audit.l2_risks")
security/common.py:367-368   → same
helpers.py:91-95             → mediator.put("detect.*") scope bust
gh_auth.py:22-23             → mediator.put("devops.github") + mediator.put("detect.wizard")
devops/__init__.py:132-149   → mediator replaces devops_cache for invalidation
```

**The bust endpoint** (`devops/__init__.py:devops_cache_bust`) must be
refactored: instead of `devops_cache.invalidate_all()` + `_mediator_bust()`,
use ONLY `mediator.put()` with cascade. The mediator IS the bust path.

**Files touched:** 4 files

**Verification:** Bust endpoint invalidates correctly. `devops_cache.invalidate()`
is no longer called for card keys. Security scan invalidation reaches
`audit.l2_risks` in the mediator.

**Estimated size:** ~60 lines of changes across 4 files

---

### Chunk 10: Remove _mediator_bust dual path

**What:** Delete `_mediator_bust()` helper. After Chunk 9, invalidation
goes through the mediator directly — no need for a "bust both" pattern.

**Scope:**
- Delete `_mediator_bust()` from `devops/__init__.py`
- Remove all calls to it

**Files touched:** `devops/__init__.py` (1 file)

**Verification:** Bust endpoint still works. Only mediator invalidation fires.

**Estimated size:** ~25 lines deleted

---

## Phase V: Consumer Migration

### Chunk 11: Migrate remaining route consumers

**What:** Route files that still use `get_cached()` as primary (not fallback)
must switch to mediator-first.

**Remaining primary consumers:**
```
devops/detect.py:54           → get_cached("wiz:detect", ...) → m.get("detect.wizard")
audit/async_scan.py:175       → get_cached(force=True) → m.get(path, force=True)
scripts/registry.py:61        → fallback path — update mediator path
pages/api.py:112,215          → fallback paths — update mediator paths
audit/tool_install.py:299     → fallback path
```

**Files touched:** ~5 files

**Verification:** Each endpoint returns same data. No `get_cached()` call
for card keys outside of the devops_cache module itself.

---

### Chunk 12: Migrate core service consumers

**What:** Backend services that call `get_cached()` directly must use
the mediator.

**Remaining:**
```
metrics/ops.py (6 sites)     → m.get("devops.<key>") or m.peek("devops.<key>")
audit/l2_risk.py (1 site)    → m.get("devops.security") or m.peek(...)
```

**Files touched:** 2 files

**Verification:** Metrics still computed. L2 risk aggregation still works.
No `get_cached()` imports outside devops/cache.py.

---

## Phase VI: Cleanup

### Chunk 13: Smart dispatch in watcher

**What:** After computing `index.classify` in the fast index phase, compare
the output to the previous classify result. If unchanged, skip dispatching
detect/devops/posture nodes — their cached values are still correct.

**Why:** Currently the watcher dispatches ALL ~33 non-index nodes on every
file change, even if the change doesn't affect classification (e.g.,
editing a Python file in an already-Python project). This wastes subprocess
calls (docker info, kubectl version, etc).

**Scope:**
- Edit `index_watcher.py`: store previous classify output. After computing
  classify, compare with previous. If same → skip detect/devops dispatch.
  If different → dispatch as before.

**Files touched:** `index_watcher.py` (1 file)

**Verification:** Edit a .py file in a Python project → classify output
unchanged → detect.* nodes NOT dispatched. Add a `Dockerfile` to a
project without one → classify changes → detect.* dispatched.

**Estimated size:** ~20 lines

---

### Chunk 14: Eliminate devops_cache.json data fallback

**What:** Remove `_get_devops_cache()` fallback from context processor.
The mediator's disk shards (now enabled for devops.* via Chunk 8) handle
cold start.

**Why:** After Chunk 8, devops.* nodes have `persist=True`. On restart,
`hydrate_cache()` loads them from shards. The devops_cache.json fallback
in the context processor is no longer needed.

**Scope:**
- Edit `server.py`: remove `_get_devops_cache()` and the Strategy 2
  fallback loop. Only Strategy 1 (mediator peek) remains.

**Files touched:** `server.py` (1 file)

**Verification:** Restart server. First page load still shows all 23 inject
keys. No reads from `.state/devops_cache.json` for card data.

**Estimated size:** ~40 lines removed

---

### Chunk 15: Adapt frontend _cache metadata

**What:** Route endpoints that inject `_cache` metadata into responses
must use mediator's result meta instead.

**Scope:** Each migrated route consumer currently does:
```python
result = m.get("devops.docker")
data = result["data"]
# data may still have _cache from get_cached — after unwrap, it won't
```

After unwrap (Chunk 8), `data` no longer has `_cache`. The frontend may
expect it. Update route handlers to inject equivalent metadata:
```python
result = m.get("devops.docker")
data = result["data"]
data["_cache"] = {
    "computed_at": result["meta"]["computed_at"],
    "fresh": result["meta"]["source"] == "cached",
    "age_seconds": int(time.time() - result["meta"]["computed_at"]),
}
```

Or, if the frontend is adapted to read `result["meta"]` directly, skip
the bridge (D4 decision: adapt frontend, nothing lost, strictly more).

**Files touched:** Route consumers (~16 files) OR frontend JS (~2 files)

**Decision:** Adapt frontend — cheaper, gains seq/source/path fields.

---

## Phase VII: Benchmark

### Chunk 16: Measure T4 ("half the time")

**What:** No code change. Measurement only.

**Metrics to capture:**

| Metric | Before (legacy) | After (mediator) | Target |
|--------|-----------------|------------------|--------|
| File change → index update | ~30s (full rebuild) | ~45ms (delta) | 50% reduction ✅ |
| File change → detect stale | 0ms (mtime check) | 0ms (cascade) | Same |
| File change → card data served | ~2s (subprocess) | ~2s (same subprocess) | — |
| Cold start → first page | ~5s | ~2s (shard hydration) | 50% reduction |
| Warm page load (all 23 keys) | ~50ms (JSON read) | ~5ms (peek, in-memory) | 50% reduction ✅ |
| Posture scan | ~3s | ~300ms (cached pillars) | 50% reduction ✅ |

**Note:** The subprocess operations (docker info, kubectl version, git status)
dominate card computation time. The mediator doesn't speed those up — they
take the same time. The win is in NOT running them when nothing changed
(via cascade + smart dispatch) and in faster reads (in-memory peek vs
JSON file parse).

---

## Dependency Graph

```
Chunk 1 (mtime_paths engine)
  ↓
Chunk 2 (post-compute hooks)
  ↓
Chunk 3 (activity subscriber)  ─┐
  ↓                              │
Chunk 4 (EventBus compat)       │   Chunk 5 (domain restructure)
  ↓                              │     ↓
  ├──────────────────────────────┘   Chunk 6 (posture cascade wire)
  ↓                                    ↓
Chunk 7 (mtime_paths on detect)     Chunk 7 (mtime_paths on detect)
  ↓
Chunk 8 (THE BIG UNWRAP) ←── requires Chunks 1-7
  ↓
Chunk 9 (unify invalidation) ←── requires Chunk 8
  ↓
Chunk 10 (remove dual bust) ←── requires Chunk 9
  ↓
Chunk 11 (route consumers) ─── can run in parallel with 12
Chunk 12 (core consumers)
  ↓
Chunk 13 (smart dispatch)
  ↓
Chunk 14 (eliminate JSON fallback) ←── requires Chunk 8
  ↓
Chunk 15 (frontend _cache adapt) ←── requires Chunk 8
  ↓
Chunk 16 (benchmark)
```

**Critical path:** 1 → 2 → 3 → 4 → 7 → 8 → 9 → 10 → 14 → 16

**Parallelizable:** Chunks 5+6 can run anytime before Chunk 8.
Chunks 11+12 can run in parallel after Chunk 8. Chunk 13 and 15
are independent of each other.

---

## What devops_cache.py KEEPS (not migrated)

After all chunks complete, `devops/cache.py` retains:

| Function | Purpose | Why it stays |
|----------|---------|-------------|
| `load_prefs()` | Read devops_prefs.json | Preferences ≠ data. Not a mediator concern. |
| `save_prefs()` | Write devops_prefs.json | Same. |
| `DEVOPS_KEYS` | Key set constant | Used by bust endpoint scope logic. |
| `INTEGRATION_KEYS` | Key set constant | Same. |
| `AUDIT_KEYS` | Key set constant | Same. |
| `DEFAULT_PREFS` | Default preferences dict | Same. |

Everything else (`get_cached`, `invalidate*`, `recompute_all`, `_WATCH_PATHS`,
`_max_mtime`, `_save_cache`, `_load_cache`) is dead code after completion
and can be removed in a final cleanup pass.

---

## Total Estimated Effort

| Phase | Chunks | New files | Edited files | Lines changed |
|-------|--------|-----------|-------------|---------------|
| I — Prerequisites | 1-4 | 2 | 2 | ~210 |
| II — Restructure | 5-7 | 3 | ~14 | ~350 |
| III — Big Unwrap | 8 | 0 | 1 | ~40 |
| IV — Unify | 9-10 | 0 | 5 | ~85 |
| V — Migrate | 11-12 | 0 | 7 | ~70 |
| VI — Cleanup | 13-15 | 0 | ~18 | ~100 |
| VII — Benchmark | 16 | 0 | 0 | 0 |
| **Total** | **16** | **5** | **~47** | **~855** |
