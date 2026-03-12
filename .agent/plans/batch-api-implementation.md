# Batch API — Page Load Optimization Plan

**Created:** 2026-03-12
**Status:** ✅ Phases 1-3 complete — ready for testing
**Goal:** Reduce page load from ~6s to ~1-2s by batching API calls

---

## 1. Problem Statement

### Current State (measured with `--timing`)

```
Page load: ~6s
API calls: 21 individual requests
Peak concurrent: 4 threads (HTTP/1.1 limit of 6 minus 2-3 SSE streams)
Most calls: 20-60ms each (fast)
Bottleneck: ~300ms gaps between requests due to connection scheduling
```

The work itself takes ~500ms total. The other ~5.5s is HTTP round-trip
overhead: browser queues 21 requests through 3-4 available connections.

### Current Flow (from `_boot.html`)

```
DOMContentLoaded
  ├─ restoreFromHash()
  ├─ AWAIT: loadProjectPulse()         → fetches /status + /health
  ├─ AWAIT: loadToolsStatus()          → fetches /tools/status (cached)
  ├─ THEN deferred:
  │    ├─ loadCapabilities()           → fetches /capabilities (uncached)
  │    ├─ loadSetupProgress()          → fetches many endpoints
  │    ├─ loadProjectGrade()           → fetches /metrics/health
  │    ├─ checkGitAuth()               → fetches /git/auth-status
  │    └─ checkGhStatus()              → fetches /integrations/gh/status
  │         └─ THEN: loadAttentionItems()
  └─ Tab-specific loads fire from tab activation
```

Plus the browser auto-fires:
- `GET /api/events` (SSE) ×2-3
- `GET /api/tab-mesh/cdp-status` (3.7s — WSL probe)
- `GET /api/audits/pending`, `/notifications/badge`, `/server/status`
- `GET /api/dev/status`, `/devops/prefs`, `/devops/integration-prefs`
- Tab-specific: GitHub, Pages, artifacts, scripts, plans, etc.

### What Already Exists

1. **`__INITIAL_STATE__`** — Server-side hydration from devops cache.
   Populates: DevOps cards (9), Integrations cards (4+3 GH), Dashboard
   project-status, Audit L0/L1 (5), wiz:detect.
   → These are SSE-publishable keys. NOT the same as the 21 API calls.

2. **`storeGet/storeSet`** — In-memory store (`_event_stream.html`).
   Populated from `__INITIAL_STATE__` on boot (line 816-826).
   Cards check `storeGet(key)` before fetching.

3. **`cardCached/cardStore`** — sessionStorage cache (`_cache.html`).
   10-minute TTL. Cards check `cardCached(key)` before fetching.

4. **`cardLoad()`** — Standard card loader that checks `cardCached()`
   then falls back to `api()` fetch.

### Gap Analysis

The `__INITIAL_STATE__` hydration handles devops/integration CARDS
(the heavy ones that need scan data). But there are ~12 lightweight
endpoints that are NOT in the cache and fire individually every load:

| Endpoint | Time | Why not cached |
|----------|------|----------------|
| `/status` | 97ms | Runtime computed (modules, envs) |
| `/health` | 60ms | Runtime checks |
| `/capabilities` | 64ms | Runtime computed |
| `/dev/status` | 49ms | Runtime state |
| `/server/status` | 0ms | Runtime state |
| `/tools/status` | 20ms | Cached via `get_cached` now |
| `/devops/prefs` | 11ms | File read |
| `/devops/integration-prefs` | 1ms | File read |
| `/git/auth-status` | 111ms | Runtime (SSH agent check) |
| `/integrations/gh/status` | 54ms | Runtime (token check) |
| `/notifications/badge` | 8ms | Runtime query |
| `/audits/pending` | 37ms | Runtime query |

**Total compute: ~512ms. Total wall time with gaps: ~4-5s.**

---

## 2. Solution Architecture

### 2.1 Backend: Batch Registry + Endpoint

**New file:** `src/ui/web/routes/api/batch.py`

A **batch registry** maps string keys → zero-arg callables that return
dicts. A single `POST /api/batch` endpoint executes requested keys
**in parallel** (ThreadPoolExecutor) and returns all results in one
HTTP response.

```python
# Batch registry: key → resolver function
_BATCH_REGISTRY: dict[str, Callable[[], dict]] = {}

def batch_key(name: str):
    """Decorator to register a batchable resolver."""
    def wrap(fn):
        _BATCH_REGISTRY[name] = fn
        return fn
    return wrap

# Predefined groups for common scenarios
_BATCH_GROUPS: dict[str, list[str]] = {
    "boot-critical": [
        "status", "health", "tools",
    ],
    "boot-deferred": [
        "capabilities", "git-auth", "gh-status",
        "notifications-badge", "audits-pending",
    ],
    "boot-config": [
        "server-status", "dev-status",
        "devops-prefs", "integration-prefs",
    ],
}

@batch_bp.route("/api/batch", methods=["POST"])
def batch_resolve():
    body = request.get_json(silent=True) or {}
    
    # Accept explicit keys and/or group names
    keys = set(body.get("keys", []))
    for group in body.get("groups", []):
        keys.update(_BATCH_GROUPS.get(group, []))
    
    # Filter to registered keys only
    valid = {k for k in keys if k in _BATCH_REGISTRY}
    
    results = {}
    errors = {}
    
    # Execute in parallel — this is the key win
    with ThreadPoolExecutor(max_workers=min(len(valid), 6)) as pool:
        futures = {pool.submit(_BATCH_REGISTRY[k]): k for k in valid}
        for future in as_completed(futures, timeout=8):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as e:
                errors[key] = str(e)
    
    return jsonify({
        "results": results,
        "errors": errors,
    })
```

### 2.2 Resolver Registration

Each resolver is a thin wrapper around existing logic. They are
registered at import time alongside the existing route handlers.
**No changes to existing routes.**

```python
# In batch.py or a separate batch_resolvers.py

@batch_key("status")
def _resolve_status():
    project = load_project(root / "project.yml")
    # Same logic as GET /api/status handler
    return {...}

@batch_key("health")
def _resolve_health():
    # Same logic as GET /api/health handler
    return {...}

@batch_key("capabilities")
def _resolve_capabilities():
    # Same logic as GET /api/capabilities handler
    return {...}

# ... etc for each batchable endpoint
```

**Key principle:** resolvers call the SAME backend functions as the
existing route handlers. No logic duplication. If `/api/status` calls
`project_summary()`, the resolver also calls `project_summary()`.

### 2.3 Frontend: Batch Prefetch

**New file:** `scripts/_batch_prefetch.html`
**Loads:** After `_event_stream.html`, before `_boot.html`.

```javascript
(async function _batchPrefetch() {
    // Skip if data is already fresh (e.g., SPA navigation within session)
    if (window.__BATCH_DONE__) return;
    
    try {
        const resp = await fetch("/api/batch", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                groups: ["boot-critical", "boot-deferred", "boot-config"]
            })
        });
        const { results } = await resp.json();
        
        // Populate store AND sessionStorage so existing card code finds it
        for (const [key, data] of Object.entries(results)) {
            storeSet(key, data);              // in-memory (renderers fire)
            cardStore('batch:' + key, data);  // sessionStorage (TTL cache)
        }
    } catch (e) {
        console.warn('[Batch] prefetch failed, falling back to individual', e);
    }
    
    window.__BATCH_DONE__ = true;
})();
```

### 2.4 Card Adaptation (Where Needed)

Cards already check `cardCached()` or `storeGet()` before fetching.
We need to ensure the batch keys map to the same cache keys the cards
check.

**Option A (preferred): Map batch keys to existing card cache keys.**

The batch response uses the same keys the cards already cache under:

| Batch Key | Card Cache Key | Card Check |
|-----------|---------------|------------|
| `status` | `dash-status` | `cardCached('dash-status')` in `loadProjectPulse` |
| `health` | `dash-health` | `cardCached('dash-health')` in `loadProjectPulse` |
| `capabilities` | `capabilities` | `storeGet('capabilities')` in `loadCapabilities` |
| `tools` | `tools` | Already uses devops cache |
| `git-auth` | — | No cache check, always fetches |
| `gh-status` | — | No cache check, always fetches |

For cards that don't cache-check (`git-auth`, `gh-status`, etc.),
we add a `storeGet` check before their fetch:

```javascript
// Before (checkGitAuth):
async function checkGitAuth() {
    const data = await api('/git/auth-status');
    // ... render
}

// After:
async function checkGitAuth() {
    const data = storeGet('git-auth') || await api('/git/auth-status');
    // ... render
}
```

**Option B (alternative): The batch prefetch writes to `cardStore`
using the same keys the cards check.** This requires mapping batch
keys exactly to the card cache keys (`dash-status`, `dash-health`,
etc.).

→ **Option A is cleaner** because `storeGet` is in-memory (instant)
and doesn't involve sessionStorage serialization.

---

## 3. What Stays OUTSIDE the Batch

These are inherently slow and should fire independently (non-blocking):

| Endpoint | Duration | Reason |
|----------|----------|--------|
| `/api/tab-mesh/cdp-status` | 3-4s | WSL transport probe |
| `/api/metrics/health` | 8-10s | Full project scan |
| `/api/cdp-test/warm` | 300-600ms | Bridge warmup |
| `/api/tab-mesh/discover-target` | 16ms but depends on cdp-status | Sequential dependency |
| `/api/events` (SSE) | Long-lived | Streaming connection |
| `/api/ledger/sync-status` | 59ms | Depends on git auth |

These fire as they do today — their latency is inherent, not
caused by connection scheduling.

---

## 4. Implementation Phases

### Phase 1: Backend Batch Endpoint (no frontend changes)

**Files to create/modify:**

1. `src/ui/web/routes/api/batch.py` — NEW
   - Blueprint: `batch_bp`
   - Registry: `_BATCH_REGISTRY`, `_BATCH_GROUPS`
   - Route: `POST /api/batch`
   - Resolvers for all boot-time endpoints

2. `src/ui/web/server.py` — register `batch_bp`

**Testing:** `curl -X POST http://localhost:8000/api/batch -H 'Content-Type: application/json' -d '{"groups":["boot-critical"]}'`

**Success criteria:** Single HTTP request returns status + health + tools data in ~200ms.

### Phase 2: Frontend Batch Prefetch

**Files to create/modify:**

1. `src/ui/web/templates/scripts/_batch_prefetch.html` — NEW
   - One-shot async IIFE
   - Fetches batch → populates store
   - Sets `window.__BATCH_DONE__`

2. `src/ui/web/templates/dashboard.html` — add include
   - After `_event_stream.html`, before `_boot.html`

**Testing:** Open browser, check network tab — should see one POST /api/batch
instead of 12 individual GETs.

### Phase 3: Card Store Guards

**Files to modify:** Add `storeGet(key) ||` guards to cards that
currently always fetch:

| Card Function | File | Guard Needed |
|--------------|------|-------------|
| `loadProjectPulse` | `_dashboard.html` | Already checks `cardCached` — needs batch key mapping |
| `loadCapabilities` | `_commands.html` | Already checks `cardCached` |
| `checkGitAuth` | `auth/_git_auth.html` | Needs `storeGet('git-auth')` guard |
| `checkGhStatus` | `auth/_gh_auth.html` | Needs `storeGet('gh-status')` guard |
| `loadAttentionItems` | `_dashboard.html` | Uses data from other calls, no fetch |
| `loadSetupProgress` | `_dashboard.html` | Fetches `/project/status` — batch it |
| `loadProjectGrade` | `_dashboard.html` | Fetches `/metrics/health` — TOO SLOW, keep individual |

**Estimated changes:** ~5-8 small edits (add one `storeGet` line).

### Phase 4: Key Mapping + Dedup

Ensure the batch response keys match exactly what each card checks:

```javascript
// In _batch_prefetch.html — key mapping
const _BATCH_TO_CARD = {
    'status':        'dash-status',     // loadProjectPulse checks this
    'health':        'dash-health',     // loadProjectPulse checks this
    'capabilities':  'capabilities',    // loadCapabilities checks this
    'tools':         'tools',           // devops cache key
};

for (const [batchKey, data] of Object.entries(results)) {
    const cardKey = _BATCH_TO_CARD[batchKey] || batchKey;
    storeSet(cardKey, data);
    cardStore(cardKey, data);
}
```

---

## 5. Expected Timing After

```
DOMContentLoaded (t=0)
  ├─ __INITIAL_STATE__ hydrates devops/audit cards (0ms, inline JSON)
  ├─ SSE connects (non-blocking)
  ├─ POST /api/batch (groups: boot-critical + boot-deferred + boot-config)
  │     Backend: parallel ThreadPool → all 12 resolvers finish in ~200ms
  │     Response arrives at ~250ms
  │     Store populated → cards render instantly
  ├─ GET /api/tab-mesh/cdp-status (fires independently, 3-4s)
  ├─ loadProjectPulse() → finds data in store → instant render
  ├─ loadToolsStatus() → finds data in store → instant render
  ├─ loadCapabilities() → finds data in store → instant render
  ├─ checkGitAuth() → finds data in store → instant render
  └─ checkGhStatus() → finds data in store → instant render

Total: ~300ms to interactive (critical cards visible)
       ~3-4s for CDP status to appear (inherent, non-blocking)
```

**Savings:**
- Individual API calls eliminated: ~12 (from 21 → 9, remaining are SSE + slow probes)
- HTTP round-trips saved: ~12 × 300ms = ~3.6s
- Backend compute unchanged (same work, parallel instead of sequential)

---

## 6. Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Batch endpoint errors kill all data | Each key is independently try/caught; partial results returned |
| Resolver function has side effects | Resolvers are read-only (same as GET handlers) |
| Thread safety of resolver functions | Existing handlers already run in werkzeug threads; ThreadPool is equivalent |
| Frontend timing: batch arrives after card already fetched | `storeGet` check runs before fetch; if batch is slow, card fetches normally (no regression) |
| sessionStorage quota | Batch data is small (~2-5KB total for lightweight endpoints); not an issue |
| Backward compatibility | Individual endpoints remain unchanged; batch is additive |

---

## 7. Files Inventory

### New Files
- `src/ui/web/routes/api/batch.py` — batch endpoint + registry + resolvers
- `src/ui/web/templates/scripts/_batch_prefetch.html` — frontend prefetch

### Modified Files
- `src/ui/web/server.py` — register batch blueprint (1 line)
- `src/ui/web/templates/dashboard.html` — add include (1 line)
- `src/ui/web/templates/scripts/auth/_git_auth.html` — add storeGet guard (~1 line)
- `src/ui/web/templates/scripts/auth/_gh_auth.html` — add storeGet guard (~1 line)
- ~3-4 other card scripts — add storeGet guards

### Unchanged (verified no impact)
- All existing API routes — still work individually
- SSE event stream — unchanged
- DevOps cache / `__INITIAL_STATE__` — unchanged
- `cardCached`/`cardStore` — unchanged

---

## 8. Open Questions for Discussion

1. **Should tab-specific data be batched too?** When switching to
   Integrations tab, it fires GitHub + Pages + artifacts endpoints.
   We could add a `"tab:integrations"` group. But: these are already
   fast due to `__INITIAL_STATE__` hydration. Lower priority.

2. **Should the batch endpoint support GET with query params?**
   `GET /api/batch?groups=boot-critical,boot-deferred` would be
   simpler for debugging but less flexible than POST JSON.
   → Recommend supporting both.

3. **Should batch results be SSE-publishable?** When batch data
   changes (e.g., tool installed), the SSE could push a batch update.
   → Phase 2+ optimization, not needed for initial implementation.

4. **Naming: `/api/batch` vs `/api/hydrate` vs `/api/prefetch`?**
   → `/api/batch` is the most standard term.
