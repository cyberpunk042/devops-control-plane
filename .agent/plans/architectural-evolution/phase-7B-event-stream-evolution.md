# Phase 7B: Event Stream Evolution — Deep Analysis

**Status:** Complete (7B-1 ✅, 7B-2 ✅, 7B-3 ✅, 7B-4 ✅)  
**Depends on:** Phase 7A (EventBus + SSE endpoint + cache events) ✅  
**Goal:** The EventBus becomes the central nervous system. The browser connects  
once and receives ALL state changes. File watchers detect staleness.  
Cards update reactively. The user sees "outdated" badges proactively.

---

## 1. Current State Audit

### 1.1 What's Built (Server Side)

| Component | File | Status | Notes |
|---|---|---|---|
| EventBus | `event_bus.py` | ✅ Done | Thread-safe pub/sub, 500-event ring buffer, per-subscriber queues, heartbeat, snapshot |
| SSE Endpoint | `routes_events.py` | ✅ Done | `GET /api/events`, `Last-Event-Id` replay, chunked streaming |
| Cache Lifecycle Events | `devops_cache.py` | ✅ Done | `cache:hit`, `cache:miss`, `cache:done`, `cache:error` published from `get_cached()` |
| Scoped Bust Events | `devops_cache.py` | ✅ Done | `cache:bust` with scope (devops/integrations/audit/all) |
| Background Recompute | `devops_cache.py` | ✅ Done | `recompute_all()` with `_RECOMPUTE_ORDER`, scoped by keys |
| Compute Registry | `routes_devops.py` | ✅ Done | 18 compute functions registered (devops + integrations + audit L0/L1) |
| Blueprint Registration | `server.py` | ✅ Done | `events_bp` registered at `/api` prefix |

### 1.2 What's Built (Client Side)

| Component | File | Status | Notes |
|---|---|---|---|
| Card Client Cache | `_globals.html` (L93-160) | ✅ Done | `sessionStorage`-backed, 10min TTL, `cardCached/cardStore/cardInvalidate` |
| API Concurrency Semaphore | `_globals.html` (L4-60) | ✅ Done | Max 3 concurrent fetches, JS-level queue before timeout starts |
| Card Load Helper | `_globals.html` (L266-284) | ✅ Done | `cardLoad(key, apiPath, badge, detail)` — fetch + store + error |
| Card Refresh Helper | `_globals.html` (L247-260) | ✅ Done | `cardRefresh(key, badge, detail, loadFn)` — bust + spinner + reload |
| Scoped Bust (DevOps) | `_devops_init.html` (L44) | ✅ Done | `await api('/devops/cache/bust', { card: 'devops' })` |
| Scoped Bust (Integrations) | `_integrations_init.html` (L124) | ✅ Done | `await api('/devops/cache/bust', { card: 'integrations' })` |
| Scoped Bust (Audit) | `_audit_init.html` (L80) | ✅ Done | `await api('/devops/cache/bust', { card: 'audit' })` |
| SSE Client | — | ❌ **Missing** | No `EventSource` connection exists |
| State Store | — | ❌ **Missing** | No in-memory store; data lives in sessionStorage |
| Reactive Rendering | — | ❌ **Missing** | Cards only render on explicit `loadXxxCard()` calls |

### 1.3 What's Missing (The Gap)

**The browser has NO IDEA the SSE stream exists.**

Current data flow:
```
Browser → "give me testing data" → GET /api/testing/status → wait → response → render
```

Target data flow:
```
Browser ← SSE stream: cache:done {key: "testing", data: {...}} → render immediately
         (no explicit fetch needed for READ operations)
```

---

## 2. Gap Analysis: Current Card Loading Patterns

### 2.1 How Cards Load Today

Every card follows the same pattern (via `cardLoad()` or manual equivalent):

```javascript
// Called from loadTestingCard(), loadDockerCard(), etc.
async function loadTestingCard() {
    const cached = cardCached('testing');        // 1. Check sessionStorage
    if (cached) { renderTestingCard(cached); return; }
    const data = await api('/testing/status');    // 2. HTTP GET (through semaphore)
    cardStore('testing', data);                   // 3. Save to sessionStorage
    renderTestingCard(data);                      // 4. Render
}
```

**Problems with this pattern:**
1. **Browser pulls.** The browser must explicitly ask. If data changed on the server, the browser doesn't know until it asks again.
2. **Wasted roundtrips.** After a bust, the background thread recomputes data. When the browser's GET arrives, the data is already in cache. The GET was unnecessary — the server could have PUSHED it.
3. **No staleness awareness.** Between explicit loads, the user has no idea if underlying files changed. A test file could be edited and the testing card would show stale data with no visual indicator.
4. **All-or-nothing tab loading.** When switching to the DevOps tab, ALL 9 cards fire GETs simultaneously. With SSE, cards that already have fresh data in the store render instantly.

### 2.2 Card Registry (All Render Functions)

These are the render functions that need to be SSE-aware:

**DevOps Tab** (`_devops_init.html` → `_DEVOPS_CARDS`):
| Cache Key | Render Function | API Endpoint | Typical Time |
|---|---|---|---|
| `security` | `loadSecurityCard()` | `/security/posture-summary` | ~100ms (reads cache only) |
| `testing` | `loadTestingCard()` | `/testing/status` | 6-10s cold |
| `quality` | `loadQualityCard()` | `/quality/status` | 0.5-1s |
| `packages` | `loadPackagesCard()` | `/packages/status` | 0.3-0.8s |
| `env` | `loadEnvCard()` | `/env/card-status` | 0.5-1s |
| `docs` | `loadDocsCard()` | `/docs/status` | 1-3s |
| `k8s` | `loadK8sCard()` | `/k8s/status` | 1-3s |
| `terraform` | `loadTerraformCard()` | `/terraform/status` | 2-5s |
| `dns` | `loadDnsCard()` | `/dns/status` | 3-8s |

**Integrations Tab** (`_integrations_init.html` → `_INT_CARDS`):
| Cache Key | Render Function | API Endpoint |
|---|---|---|
| `int:git` → `git` | via `_INT_CARDS` | `/git/status` |
| `int:github` → `github` | via `_INT_CARDS` | `/github/status` |
| `int:ci` → `ci` | via `_INT_CARDS` | `/ci/status` |
| `int:docker` → `docker` | via `_INT_CARDS` | `/docker/status` |
| `int:k8s` → `k8s` | via `_INT_CARDS` | `/k8s/status` |
| `int:terraform` → `terraform` | via `_INT_CARDS` | `/terraform/status` |
| `int:pages` → `pages` | via `_INT_CARDS` | `/pages/segments` |
| `project-status` | `_fetchIntProjectStatus()` | `/project/status` |

**Audit Tab** (`_audit_init.html` → `_AUDIT_CARDS`):
| Cache Key | Render Function | API Endpoint |
|---|---|---|
| `audit:scores` | `loadAuditScores()` | `/audit/scores` |
| `audit:system` | `loadAuditSystemCard()` | `/audit/system` |
| `audit:deps` | `loadAuditDepsCard()` | `/audit/dependencies` |
| `audit:structure` | `loadAuditStructureCard()` | `/audit/structure` |
| `audit:clients` | `loadAuditClientsCard()` | `/audit/clients` |
| `audit:l2:quality` | `loadAuditHealthCard()` | `/audit/code-health` |
| `audit:l2:repo` | `loadAuditRepoCard()` | `/audit/repo` |
| `audit:l2:risks` | `loadAuditRisksCard()` | `/audit/risks` |
| `audit:l2:structure` | `loadAuditL2StructureCard()` | `/audit/structure-analysis` |

### 2.3 Events Already Being Published (Server Side)

The server ALREADY publishes events. Here's proof from `devops_cache.py:get_cached()`:

```
Every card computation → cache:miss (start) → cache:done (finish) or cache:error (fail)
Every cache hit → cache:hit
Every bust → cache:bust
Background recompute → recompute_all() publishes sys:warming, then per-key cache:miss/done, then sys:warm
```

**Nobody is listening.** The events go to the EventBus, but no SSE client is connected.

---

## 3. The Evolution: 4 Deliverables

### 3.1 Deliverable A: Browser SSE Client

**What:** A persistent `EventSource` connection from the browser to `GET /api/events`.

**Where:** New template include `_event_stream.html` (loaded in `_globals.html` or after it).

**Responsibilities:**
1. Open SSE connection on page load
2. Auto-reconnect on disconnect (EventSource does this natively)
3. Track `Last-Event-Id` for replay
4. Route events to the state store by type
5. Detect server restart (instance_id change) → discard stale local state
6. Visual connection indicator (optional, future)

**Design:**
```javascript
const _sse = {
    source: null,
    instanceId: null,
    lastSeq: 0,
    connected: false,
    
    connect() {
        if (this.source) return; // Already connected
        const url = '/api/events' + (this.lastSeq ? '?since=' + this.lastSeq : '');
        this.source = new EventSource(url);
        
        // Register event listeners by type
        for (const type of [
            'sys:ready', 'sys:warming', 'sys:warm', 'sys:heartbeat',
            'state:snapshot',
            'cache:miss', 'cache:done', 'cache:error', 'cache:bust',
            'state:stale',  // future: file watcher
        ]) {
            this.source.addEventListener(type, (e) => this._dispatch(type, e));
        }
        
        this.source.onerror = () => {
            this.connected = false;
            // EventSource auto-reconnects with Last-Event-Id header
        };
    },
    
    _dispatch(type, sseEvent) {
        const payload = JSON.parse(sseEvent.data);
        this.lastSeq = payload.seq;
        
        switch (type) {
            case 'sys:ready':
                this._onReady(payload);
                break;
            case 'state:snapshot':
                this._onSnapshot(payload);
                break;
            case 'cache:done':
                this._onCacheDone(payload);
                break;
            case 'cache:miss':
                this._onCacheMiss(payload);
                break;
            case 'cache:error':
                this._onCacheError(payload);
                break;
            case 'cache:bust':
                this._onCacheBust(payload);
                break;
            case 'state:stale':
                this._onStateStale(payload);
                break;
        }
    },
};
```

**Key decision:** The SSE client is **additive**. Existing `api()` calls continue to work. Cards that haven't been migrated keep their current behavior. The SSE client populates the state store in PARALLEL — cardCached() can check it as a faster source.

### 3.2 Deliverable B: State Store + Reactive Card Updates

**What:** An in-memory state store that holds card data and notifies renderers when data changes.

**Where:** In `_event_stream.html` (or `_state_store.html`).

**Design:**
```javascript
const _store = {};          // key → data dict
const _renderers = {};      // key → [renderFn, ...]
const _staleKeys = new Set(); // keys marked stale by watcher

function storeSet(key, data) {
    _store[key] = data;
    _staleKeys.delete(key);  // Fresh data clears stale marker
    cardStore(key, data);     // Also update sessionStorage (backward compat)
    // Notify renderers only if the card is currently visible
    for (const fn of (_renderers[key] || [])) {
        try { fn(data); } catch (e) { console.error(`render ${key}:`, e); }
    }
}

function storeGet(key) { return _store[key] || null; }

function storeRegister(key, renderFn) {
    (_renderers[key] ??= []).push(renderFn);
}
```

**Migration strategy (per card):**

Before (current):
```javascript
async function loadTestingCard() {
    const cached = cardCached('testing');
    if (cached) { renderTestingCard(cached); return; }
    const data = await api('/testing/status');
    cardStore('testing', data);
    renderTestingCard(data);
}
```

After (progressive — SSE-aware):
```javascript
// Register renderer (runs once at page load)
storeRegister('testing', renderTestingCard);

async function loadTestingCard() {
    // 1. Check state store first (populated by SSE or pre-injection)
    const storeData = storeGet('testing');
    if (storeData) { renderTestingCard(storeData); return; }
    // 2. Check sessionStorage (backward compat)
    const cached = cardCached('testing');
    if (cached) { renderTestingCard(cached); return; }
    // 3. Fall back to API fetch (SSE will also deliver via cache:done)
    const data = await api('/testing/status');
    storeSet('testing', data);  // storeSet also calls cardStore
    renderTestingCard(data);
}
```

**The key insight:** Once the SSE connection is live, `cache:done` events will call `storeSet(key, data)` → which calls `renderTestingCard(data)` automatically. The explicit `loadTestingCard()` becomes a fallback for the initial load or reconnection scenarios.

**This migration can be done card by card.** Non-migrated cards keep working exactly as before. Zero big-bang risk.

### 3.3 Deliverable C: Staleness Watcher (mtime poll)

**What:** A background thread that periodically checks `_WATCH_PATHS` mtimes and publishes `state:stale` events when underlying files change.

**Where:** New module `src/core/services/staleness_watcher.py` (or extend `devops_cache.py`).

**Design:**
```python
import threading
import time
from pathlib import Path

from src.core.services.devops_cache import _WATCH_PATHS, _max_mtime, _load_cache

POLL_INTERVAL = 5.0  # seconds

def start_watcher(project_root: Path) -> threading.Thread:
    """Start a daemon thread that polls for file changes."""
    
    def _poll_loop():
        last_mtimes: dict[str, float] = {}
        
        while True:
            time.sleep(POLL_INTERVAL)
            cache = _load_cache(project_root)
            
            for key, watch_paths in _WATCH_PATHS.items():
                current_mtime = _max_mtime(project_root, watch_paths)
                cached_at = cache.get(key, {}).get("mtime", 0)
                
                # File changed AFTER the cache was written
                if current_mtime > cached_at and current_mtime != last_mtimes.get(key, 0):
                    last_mtimes[key] = current_mtime
                    _publish_stale(key, current_mtime, cached_at)
    
    t = threading.Thread(target=_poll_loop, daemon=True, name="staleness-watcher")
    t.start()
    return t

def _publish_stale(key: str, current_mtime: float, cached_mtime: float):
    """Publish a state:stale event for a cache key."""
    try:
        from src.core.services.event_bus import bus
        bus.publish("state:stale", key=key, data={
            "file_mtime": current_mtime,
            "cache_mtime": cached_mtime,
            "stale_by_s": round(current_mtime - cached_mtime, 1),
        })
    except Exception:
        pass  # fail-safe
```

**Why mtime polling (not inotify):**

1. **Reuses existing code.** `_WATCH_PATHS` and `_max_mtime()` already exist and are battle-tested.
2. **Zero new dependencies.** No `watchdog` or `pyinotify` needed.
3. **5s latency is fine.** This is a dev tool. Knowing "your tests changed 5 seconds ago" is perfectly adequate.
4. **No OS limits.** inotify has per-user watch limits (~8192). With 78K files, we'd hit it.
5. **Can always upgrade later.** The event contract is the same — only the detection mechanism changes.

**Key considerations:**
- **Debounce:** The `last_mtimes` dict prevents re-firing the same stale event repeatedly until the cache is refreshed.
- **Low cost:** Reading mtimes for ~30 watch path groups at 5s intervals is negligible I/O.
- **Doesn't auto-recompute:** Only publishes `state:stale`. The browser decides what to do (show badge, auto-refresh, or ignore).

### 3.4 Deliverable D: Stale Badges on Cards

**What:** When a `state:stale` event arrives, the browser shows a ⚠️ badge on the affected card, telling the user "this data may be outdated."

**Where:** CSS class + JS event handler.

**Design:**
```javascript
// In SSE client _onStateStale handler:
_onStateStale(payload) {
    const key = payload.key;
    _staleKeys.add(key);
    
    // Find the card DOM element and add stale badge
    const badge = document.querySelector(`[data-cache-key="${key}"]`);
    if (badge) {
        badge.classList.add('stale');
        badge.title = 'Underlying files changed — click 🔄 to refresh';
    }
    
    // Optionally: auto-refresh in background if card is visible
    // (future enhancement, not MVP)
}
```

**CSS:**
```css
.status-badge.stale::after {
    content: '⚠️';
    margin-left: 4px;
    font-size: 0.7rem;
}
```

**When the stale badge clears:** On `cache:done` for the same key (data is now fresh). `storeSet()` already does `_staleKeys.delete(key)`.

---

## 4. Integration Map: Events × Cards × Behavior

### 4.1 Event → Client Behavior Matrix

| Event | Key | Client Action |
|---|---|---|
| `sys:ready` | — | Store `instance_id`, check for server restart |
| `sys:warming` | — | (optional) Show "warming up..." toast |
| `sys:warm` | — | (optional) Hide warming toast |
| `sys:heartbeat` | — | No-op (keep connection alive) |
| `state:snapshot` | — | Replace entire store, re-render visible cards |
| `cache:miss` | testing | Show ⏳ spinner on testing card (if visible) |
| `cache:done` | testing | `storeSet('testing', data)` → re-render card instantly |
| `cache:error` | testing | Show ❌ error on card with message |
| `cache:bust` | devops | Mark devops keys as busted (expect miss → done sequence) |
| `state:stale` | testing | Add ⚠️ badge to testing card ("tests/ changed") |

### 4.2 Current Watch Paths → Stale Detection Examples

| User Action | Files Changed | Watch Path Match | Stale Event |
|---|---|---|---|
| Edit `tests/test_auth.py` | `tests/test_auth.py` | `testing: ["tests/"]` | `state:stale {key: "testing"}` |
| Edit `Dockerfile` | `Dockerfile` | `docker: ["Dockerfile"]` | `state:stale {key: "docker"}` |
| Edit `pyproject.toml` | `pyproject.toml` | `quality`, `packages`, `testing`, `audit:deps`, `audit:scores` | 5 separate stale events |
| `git commit` | `.git/HEAD` | `git: [".git/HEAD"]` | `state:stale {key: "git"}` |
| Edit `k8s/deployment.yaml` | `k8s/...` | `k8s: ["k8s/"]` | `state:stale {key: "k8s"}` |

### 4.3 Full Lifecycle Example: User Edits a Test File

```
t=0s:   User saves tests/test_auth.py in their editor
t=5s:   Watcher poll detects tests/ mtime changed
t=5s:   Watcher publishes: state:stale {key: "testing", stale_by_s: 5.0}
t=5s:   SSE delivers event to browser
t=5s:   Browser: testing card shows ⚠️ "Outdated" badge
        (User can see at a glance that test data is stale)

t=?:    User clicks 🔄 on testing card (or Refresh All)
t=?:    Browser: POST /devops/cache/bust {card: "testing"}
t=?:    Server: invalidates testing cache → starts recompute
t=?:    SSE: cache:miss {key: "testing"}
t=?:    Browser: testing card shows ⏳ spinner
t=?+6s: SSE: cache:done {key: "testing", data: {...}, duration_s: 6.2}
t=?+6s: Browser: storeSet("testing", data) → re-render card → ⚠️ badge clears
```

---

## 5. Implementation Sequence

### Phase 7B-1: SSE Client + State Store (foundation)

**Scope:** `_event_stream.html` — ~100 lines of JS

1. Create `_event_stream.html` template include
2. Implement `_sse.connect()` with event routing
3. Implement `storeSet/storeGet/storeRegister`
4. Wire `cache:done` → `storeSet()` → existing `cardStore()` for backward compat
5. Wire `cache:miss` → show spinner on visible card (if not already)
6. Wire `cache:error` → show error on visible card
7. Call `_sse.connect()` on page load (after `_globals.html`)
8. Include in `index.html` template

**Risk:** Low — additive only, no existing code changes.  
**Test:** Open browser, check DevTools EventStream tab, verify events arrive.

### Phase 7B-2: Reactive Card Migration (card by card)

**Scope:** Each card's `loadXxxCard()` function

For each card (start with `testing` — the most impactful):
1. Extract render logic into standalone `renderTestingCard(data)` (may already be separate)
2. Call `storeRegister('testing', renderTestingCard)` at page load
3. In `loadTestingCard()`, check `storeGet('testing')` before `cardCached()`
4. After bust + background recompute, `cache:done` SSE event → `storeSet()` → re-render automatically

**Risk:** Medium — requires careful verification that render functions are idempotent.  
**Migration order:** testing → docker → k8s → terraform → dns (slowest first = most impactful).

### Phase 7B-3: Staleness Watcher

**Scope:** `staleness_watcher.py` — ~60 lines + 1 line in `server.py`

1. Create `staleness_watcher.py` with mtime polling loop
2. Add `state:stale` event type to EventBus
3. Start watcher thread from `server.py` (or `create_app()`)
4. Client: handle `state:stale` → set badge

**Risk:** Low — entirely in background, fail-safe.  
**Test:** Start server, edit a test file, verify `state:stale` event arrives in SSE stream.

### Phase 7B-4: Stale Badges

**Scope:** CSS + event handler in `_event_stream.html`

1. Add CSS for `.stale` badge state
2. Wire `state:stale` → add badge to card DOM
3. Wire `cache:done` → clear badge (already happens via `storeSet` → `_staleKeys.delete`)
4. Wire age ticker to show stale indicator for old data

**Risk:** Low — CSS + DOM manipulation only.

---

## 6. What This Does NOT Change

- **POST actions** (bust, validate, generate, install) still use `api()` / `apiPost()`. SSE is read-only.
- **Session storage** continues to work as secondary cache (offline resilience, backward compat).
- **API semaphore** continues to throttle concurrent fetches (for POST actions and fallback GETs).
- **Card load preferences** (auto/manual/hidden) continue to work — renderers just have a new data source.
- **Individual card refresh (🔄)** continues to work — it busts + re-fetches, and the SSE stream delivers the result.

---

## 7. Open Questions

1. **Auto-recompute on stale?** When `state:stale` fires, should the server automatically recompute the stale card in the background? Or just notify and let the user decide? **Recommendation:** Notify only (show badge). Auto-recompute would create constant load during active editing sessions.

2. **Watcher scope.** Should the watcher only poll keys that are currently visible on an active tab? Or poll all keys always? **Recommendation:** Poll all keys always — the cost is negligible (reading ~30 mtimes every 5s) and ensures that stale data is detected even for tabs the user hasn't opened yet.

3. **Multi-key stale batching.** Editing `pyproject.toml` makes 5 keys stale simultaneously. Should we batch these into one event or send 5 separate events? **Recommendation:** 5 separate events — each key has its own badge and render path, and the EventBus is designed for high fanout.

4. **Connection indicator.** Should the UI show a small dot/icon indicating SSE connection status (connected/disconnected/reconnecting)? **Recommendation:** Yes, but as a subtle indicator in the footer or header — not a blocking overlay. Future phase.

5. **`cache:done` data size.** The plan spec says `cache:done` carries the FULL card payload. At ~5KB per card and peak 12 events during warming, this is 60KB total — negligible. **Confirmed:** Keep full data in events.
