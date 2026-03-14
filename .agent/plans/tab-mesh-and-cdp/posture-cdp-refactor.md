# Milestone: System Posture & CDP Boot Sequence Refactor

## Problem Statement

The current system has five bugs of the same class: **data that's already known
being re-queried, loops where no loops should exist, and data being thrown away
on startup despite being persisted.**

---

## Bug Inventory

### Bug 1: Posture polling loop should not exist

**File**: `src/ui/web/templates/scripts/globals/_system_posture.html` line 83

```js
_pollTimer = setInterval(fetchSummary, POLL_INTERVAL);  // 60s
```

This was a bug that was inserted. Posture data doesn't change on its own.
It only changes when tools are installed, project config changes, or the
user clicks "Rescan." The SSE system (`cache:done` events via the mediator's
`eventbus_bridge.py`) already exists to push updates reactively. The posture
frontend just doesn't use it — it polls instead.

**Cost**: 10-18 seconds of computation every other poll cycle. Over a 17-minute
session, 122 seconds spent recomputing posture — 12% of wall time.

### Bug 2: `discover-target` re-runs on every page load

**File**: `src/ui/web/templates/scripts/_tab_mesh.html` line 598

The discovered `chromeTargetId` is stored only in JS memory
(`_meshIdentity.chromeTargetId`). On page reload, it's gone, and the
expensive CDP discovery repeats.

### Bug 3: `cdp-status` re-checked on every page load (5-7s each)

**File**: `src/ui/web/templates/scripts/_tab_mesh.html` line 877

`_meshCheckCDP()` fires **immediately** in `_meshInit()` on every page load.
Takes 5-7 seconds. CDP availability doesn't change between page loads.

### Bug 4: Posture cache flush on restart

**File**: `src/core/services/system_posture/cache.py` lines 132-136

```python
# Skip entries past TTL (inf TTL = always valid)
if ttl != float("inf"):
    age = now - computed_at
    if age >= ttl:
        continue  # THROWS AWAY PERSISTED DATA
```

On restart, `_load_from_disk()` discards entries past their TTL. With
`summary` TTL = 30s and `full` TTL = 60s, any restart lasting more than
30 seconds means all persisted posture data is thrown away.

**Result**: Badge starts as "Pending" (hardcoded in `_nav.html` line 45)
and stays there for 10-18 seconds while a full recompute happens.

**Contrast**: The mediator persistence (`hydrate_cache()` in `persistence.py`)
loads ALL data unconditionally — no TTL check. But the posture summary route
defaults to the standalone cache path, not the mediator path, so it hits
the TTL-discarding `cache.py` instead.

### Bug 5: CDP called before transport warm-up

**File**: `_tab_mesh.html` → `_meshInit()` → `_meshCheckCDP()`

The CDP warm-up is `cdp_client.warm()` which:

1. Initializes the **transport router** — detects WSL2 environment, host IP
2. **Probes ALL channels** for port 9222: native socket, tunnel, direct,
   curl.exe — ranks them by latency
3. **Auto-restarts ephemeral tunnels** (python_proxy, socat, ssh) if the
   app restarted but the same IP is valid
4. **Warms the PS bridge** (~3s PowerShell startup) if no fast WS channel
   exists — this persistent process handles all subsequent CDP WebSocket calls

This warm-up is **only triggered on demand** — when the user opens the CDP
test config modal (`POST /cdp-test/warm`). It is **NOT** called at server
startup.

But `_meshCheckCDP()` fires immediately on page load and calls
`GET /api/tab-mesh/cdp-status`, which calls `cdp_client.try_discover_endpoint()`
+ `cdp_client.is_available()`. This goes through whatever transport channel
happens to exist (often curl.exe fallback = 5-7 seconds per call).

The correct sequence should be: warm-up first → channels established → THEN
CDP operations can use the fast channels.

### Bug 6: Short TTLs on posture data

**File**: `src/core/services/system_posture/cache.py` lines 74-81 AND
`src/core/services/mediator/registrations/posture.py` lines 141-147

- `summary` TTL = 30s — shorter than the poll interval (60s), guaranteeing
  every other poll triggers a full recompute
- `runtime` TTL = 0 (always fresh) — forces recompute of the runtime bridge
  on every `posture.full` assembly, cascading through the full → summary chain

---

## Architecture Context — What Already Exists

### 1. Mediator tree with posture nodes

`registrations/posture.py` registers `posture.*` nodes with dependency graph:
```
posture.platform  ─┐
posture.toolchain ─┤
posture.project   ─┼──→ posture.full ──→ posture.summary
posture.runtime   ─┘
```
TTLs, persistence, and cascade invalidation are all handled by the mediator.

### 2. SSE event system

The mediator emits `cache:done` via `eventbus_bridge.py` when any node is
computed. The frontend's `_event_stream.html` listens for `cache:done` and
calls `storeSet(key, data)` to update the reactive state store. Renderers
can subscribe via `storeRegister(key, renderFn)`.

### 3. Work queue with priority levels

```
CRITICAL = 0  — web requests (user waiting)
HIGH     = 1  — urgent background
NORMAL   = 2  — standard background
LOW      = 3  — deferred background
IDLE     = 4  — when nothing else is running
BACKGROUND = 5 — passive indexing
```

Submit via `WorkItem(priority=N, path="...", resolver=fn, size=1)`.

### 4. Mediator persistence (no TTL discard)

`hydrate_cache()` in `persistence.py` loads ALL persisted data into the
mediator cache unconditionally. No TTL check. Data survives restarts.

### 5. Startup sequence (server.py)

```
1. posture_cache_init()        ← initializes standalone cache (DISCARDS expired)
2. mediator_init()             ← creates mediator
3. register_all()              ← registers posture.* nodes
4. hydrate_cache()             ← loads ALL persisted data (NO TTL discard)
5. start_index_watcher()       ← starts FS watcher
6. [server starts listening]
   — NO CDP warm-up happens here
```

---

## Refactor Plan

### Phase 1: Silent transport warm-up at startup via work queue (Priority 2)

**Goal**: After the mediator is hydrated and the server starts, submit a
silent warm-up task to the work queue at NORMAL priority (2). This probes
the transport channels and establishes fast paths BEFORE any CDP operation.

**What "silent" means**: `cdp_client.warm()` currently creates a
notification if `router.needs_tunnel(port)` — this notification forces a
modal to open. The startup warm-up must NOT create this notification.

**Implementation**:

1. Add a `silent=True` parameter to `cdp_client.warm()`:
   ```python
   def warm(port: int = _DEFAULT_PORT, *, silent: bool = False) -> dict:
   ```
   When `silent=True`, skip the `create_notification()` call on lines 391-405.
   Everything else stays the same — probing, lifecycle check, PS bridge warm-up.

2. In `server.py`, after `start_index_watcher()` (line 292), submit a
   work queue task:
   ```python
   from src.core.services.mediator.work_queue import WorkItem, Priority

   wq = mediator_inst.work_queue
   wq.submit(WorkItem(
       priority=Priority.NORMAL,  # 2
       size=1,
       path="boot.transport_warmup",
       resolver=lambda: cdp_client.warm(silent=True),
   ))
   ```

This runs in the background after the server is listening. UI loads
immediately. Transport channels get probed and tunnel/bridge gets
warmed while the user sees the first page.

### Phase 2: CDP status + discover-target via work queue (Priority 3)

**Goal**: After the transport warm-up completes, run CDP status check and
target discovery. This depends on Phase 1 (channels must be established
first), so it gets Priority LOW (3) — guaranteed to run after the
NORMAL (2) transport warm-up.

**Double cache** — same pattern as everything else in the project:

#### Layer 1: Backend — Mediator nodes (persisted to disk)

Register new mediator nodes in a `registrations/tabmesh.py`:

```python
tree.register(TreeRegistration(
    path="tabmesh.cdp_status",
    resolver=_resolve_cdp_status,   # calls cdp_client.is_available()
    ttl=300,                        # 5 min — Chrome doesn't restart often
    persist=True,                   # survives server restart
))
```

- `tabmesh.cdp_status` — `{ available: bool, endpoint: str|null, ts: float }`
- On startup, `hydrate_cache()` loads persisted CDP status from disk
  automatically — no extra code needed, it's the same persistence system
- The boot work queue task (Priority 3) computes these nodes:
  ```python
  wq.submit(WorkItem(
      priority=Priority.LOW,  # 3
      size=1,
      path="tabmesh.cdp_status",
      resolver=lambda: mediator.get("tabmesh.cdp_status", force=True),
  ))
  ```
- When computed, the mediator emits `cache:done` → SSE → frontend receives
  the CDP status without any explicit API call

#### Layer 2: Frontend — sessionStorage (survives page reload)

In `_tab_mesh.html`:

**CDP status**:
```js
// On boot — check sessionStorage first
var cached = sessionStorage.getItem('cdp_status');
if (cached) {
    var parsed = JSON.parse(cached);
    _meshCDPAvailable = parsed.available;
    // Skip API call — use cached value
}

// Subscribe to SSE for updates from mediator
storeRegister('tabmesh:cdp_status', function(data) {
    _meshCDPAvailable = data.available;
    sessionStorage.setItem('cdp_status', JSON.stringify(data));
});
```

**Chrome target ID** (per-tab — frontend-only):
```js
// On discover success — persist to sessionStorage
sessionStorage.setItem('chrome_target_' + _meshTabId, chromeTargetId);

// On boot — check sessionStorage before calling discover-target
var cachedTarget = sessionStorage.getItem('chrome_target_' + _meshTabId);
if (cachedTarget) {
    _meshIdentity.chromeTargetId = cachedTarget;
    // Skip discover-target API call
} else if (_meshCDPAvailable) {
    _meshDiscoverTarget();  // only if CDP warm-up says it's available
}
```

#### Flow

```
Server restart:
  hydrate_cache() → loads tabmesh.cdp_status from disk → available immediately

  work_queue NORMAL(2): transport warm-up (probes channels, warms bridge)
  work_queue LOW(3):    mediator.get("tabmesh.cdp_status", force=True)
                        → uses fast channels from warm-up
                        → result persisted to disk + emitted via SSE

Page load (frontend):
  1. Check sessionStorage for cdp_status → if present, use it (instant)
  2. Check sessionStorage for chrome_target_{tabId} → if present, use it
  3. Subscribe to SSE for tabmesh:cdp_status updates
  4. If no cached CDP status → wait for SSE event from boot task
  5. If CDP available + no cached target → _meshDiscoverTarget() → cache result
```
#### Edge Cases — Browser & Tab Lifecycle

| Scenario | sessionStorage | Backend cache | Target IDs | Outcome |
|----------|---------------|---------------|------------|---------|
| **Close browser, reopen** | Wiped ✅ | Stale but boot task refreshes | Invalid (new Chrome process) | Cache miss → re-discovery → ✅ |
| **Close DCP tab, reopen** | Wiped ✅ | Valid | Valid (Chrome stayed open) | Cache miss → re-discovery → ✅ |
| **Open new DCP tab** | CDP status present, no target for new tabId | Valid | Need discovery for new tab | CDP status cached → skip check, discover target → ✅ |
| **Server restarts, Chrome stays** | Survives | Hydrated from disk, boot task refreshes | Valid | sessionStorage used immediately → ✅ |
| **Chrome crashes, DCP stays** | Says "available" ❌ | Says "available" ❌ | All invalid | **STALE — needs error-driven invalidation** |
| **Tab killed via mesh** | Still present (tab is dead but browser isn't) | Valid | Killed tab's target is orphaned | **Needs cleanup via kill handler** |

#### Error-Driven Cache Invalidation

The critical gap: Chrome dies while DCP is running. Both caches say
`available: true` but Chrome isn't there. Additionally, a tab killed
remotely via the mesh `kill` command leaves its `chromeTargetId` orphaned
in the backend target index.

The smart approach below handles both — plus eliminates redundant calls.

#### Smart Approach — Event-Driven CDP Lifecycle

The existing mesh infrastructure already has what we need:

- `BroadcastChannel('devops-tab-mesh')` — horizontal channel between tabs
- `join`/`roster`/`ping` messages carry `chromeTargetId`
- `leave` fires on `beforeunload` — sibling tabs know immediately
- `kill` renders a blocking overlay and fires `leave` + closes channel
- `_meshRegistry` tracks all known tabs with their target IDs
- `_meshTombstones` stores closed tabs (with their target IDs)

**What's missing**: the backend doesn't know when tabs/browser close, and
each tab independently calls the expensive CDP discovery. We can fix both.

**1. Tab opens — inherit from siblings, don't re-discover**

```js
// In _meshInit(), AFTER joining the mesh:
// Step 1: Check if any sibling tab already has CDP info
var siblingWithCDP = null;
_meshRegistry.forEach(function(entry) {
    if (entry.chromeTargetId && entry.alive) {
        siblingWithCDP = entry;
    }
});

if (siblingWithCDP) {
    // CDP is available — siblings already proved it
    _meshCDPAvailable = true;
    sessionStorage.setItem('cdp_status', JSON.stringify({ available: true }));
    // Don't inherit THEIR targetId — discover our own
    // But skip the cdp-status check entirely (saves 5-7s)
    _meshDiscoverTarget();
} else {
    // No siblings with CDP — check sessionStorage, then SSE
    var cached = sessionStorage.getItem('cdp_status');
    if (cached) {
        _meshCDPAvailable = JSON.parse(cached).available;
    }
    // Subscribe to SSE for boot task result
    storeRegister('tabmesh:cdp_status', function(data) {
        _meshCDPAvailable = data.available;
        sessionStorage.setItem('cdp_status', JSON.stringify(data));
        if (data.available && !_meshIdentity.chromeTargetId) {
            _meshDiscoverTarget();
        }
    });
}
```

**Key insight**: the `cdp-status` check (5-7s) only needs to happen ONCE
across ALL tabs. If any sibling already has a `chromeTargetId`, CDP is
proven available. The new tab only needs to discover ITS OWN target.

**2. Tab closes — notify backend via sendBeacon**

```js
// Extend _meshSendLeave() — already fires on beforeunload
function _meshSendLeave() {
    // Existing: broadcast to sibling tabs
    _meshBroadcast({
        type: 'leave',
        id:   _meshIdentity.id,
        ts:   Date.now(),
    });

    // NEW: notify backend (fire-and-forget, survives page unload)
    navigator.sendBeacon('/api/tab-mesh/leave', JSON.stringify({
        tabId: _meshTabId,
        chromeTargetId: _meshIdentity.chromeTargetId,
    }));
}
```

Backend `POST /api/tab-mesh/leave` handler:
- Removes this tab's target from the active target index
- If this was the LAST tab → marks `tabmesh.cdp_status` as "no active tabs"
  (but does NOT invalidate CDP availability — Chrome is still running)

**3. Browser close — all tabs fire leave simultaneously**

When the browser closes, ALL tabs fire `beforeunload` → `_meshSendLeave()`.
Each sends a `sendBeacon`. The backend receives N beacons in quick
succession and sees all tabs leaving within ~100ms. This is the signal
that the browser session ended.

Alternatively, a single beacon from the last tab is enough — the backend
already knows the other tabs are gone (they all sent beacons).

Either way: the backend cleans up all target IDs for this session.
No stale data survives.

**4. Chrome crashes — error-driven invalidation**

Chrome dies while DCP stays running. Both caches say `available: true`.

When any CDP operation fails:
```js
// Frontend: propagate failure to all tabs via BroadcastChannel
function _meshCDPFailure() {
    _meshCDPAvailable = false;
    _meshIdentity.chromeTargetId = null;
    sessionStorage.removeItem('cdp_status');
    sessionStorage.removeItem('chrome_target_' + _meshTabId);

    // Tell all sibling tabs (horizontal channel)
    _meshBroadcast({
        type: 'cdp_lost',
        id:   _meshTabId,
        ts:   Date.now(),
    });

    // Tell backend (invalidate mediator node → SSE to future tabs)
    navigator.sendBeacon('/api/tab-mesh/cdp-invalidate');
}
```

Sibling tabs handle `cdp_lost`:
```js
case 'cdp_lost':
    _meshCDPAvailable = false;
    _meshIdentity.chromeTargetId = null;
    sessionStorage.removeItem('cdp_status');
    sessionStorage.removeItem('chrome_target_' + _meshTabId);
    break;
```

Backend `/api/tab-mesh/cdp-invalidate`:
- `mediator.invalidate("tabmesh.cdp_status")` → clears cache
- Emits `cache:bust` via SSE → any tabs that haven't received the
  BroadcastChannel message (e.g., different window) also get notified

**5. Chrome comes back — recovery**

After invalidation, recovery happens through:
- User opens CDP test panel → triggers `warm()` → recomputes mediator node
  → SSE pushes to all tabs → sessionStorage updated
- Or: TTL expiry on the mediator node → next access recomputes
- Or: any tab tries a CDP operation that succeeds → broadcasts `cdp_available`
  to siblings

**6. Tab killed remotely via mesh**

The existing `_meshHandleKill()` already calls `_meshSendLeave()` and
closes the BroadcastChannel. But it doesn't clean up CDP state.

```js
// Extend _meshHandleKill():
function _meshHandleKill(msg) {
    if (msg.targetId !== _meshTabId) return;

    _meshIdentity.alive = false;

    // Stop heartbeat (existing)
    if (_meshHeartbeatInterval) {
        clearInterval(_meshHeartbeatInterval);
        _meshHeartbeatInterval = null;
    }

    // NEW: clean up CDP state for this tab
    if (_meshIdentity.chromeTargetId) {
        // Notify backend to remove this target from the index
        navigator.sendBeacon('/api/tab-mesh/leave', JSON.stringify({
            tabId: _meshTabId,
            chromeTargetId: _meshIdentity.chromeTargetId,
        }));
        _meshIdentity.chromeTargetId = null;
        sessionStorage.removeItem('chrome_target_' + _meshTabId);
    }

    // Send leave and close channel (existing)
    _meshSendLeave();
    if (_meshBC) {
        try { _meshBC.close(); } catch (_) {}
        _meshBC = null;
    }

    // Render blocking overlay (existing)
    _meshRenderKillOverlay(msg.reason || 'Session terminated remotely');
}
```

The killed tab's `chromeTargetId` is removed from the backend target
index via `sendBeacon`. Sibling tabs already received the `leave` message
via BroadcastChannel and removed it from their registry. No orphaned
target IDs.

##### Summary — No Redundant Calls

| Event | Who acts | What happens | Cost |
|-------|----------|-------------|------|
| First tab after boot | Boot task (work queue) | `warm()` + `mediator.get("tabmesh.cdp_status")` | One probe |
| Second tab opens | New tab | Reads from sibling registry → CDP proven → discover own target only | One `discover-target` call |
| Third tab opens | New tab | Same — reads siblings, discovers own target | One `discover-target` call |
| Tab closes | Closing tab | `sendBeacon` → backend removes target from index | Zero cost |
| Tab killed via mesh | Killed tab | `sendBeacon` + `leave` → backend + siblings clean up | Zero cost |
| Browser closes | All tabs | N `sendBeacon`s → backend cleans all targets | Zero cost |
| Chrome crashes | First tab to notice | `_meshCDPFailure()` → horizontal broadcast + backend invalidation | One broadcast |
| Chrome comes back | User or TTL | Manual warm or TTL-triggered recompute | One probe |

### Phase 3: Remove posture polling loop

**Goal**: Replace `setInterval` with SSE-driven reactive updates.

**File**: `src/ui/web/templates/scripts/globals/_system_posture.html`

**Changes**:
1. Remove `POLL_INTERVAL`, `_pollTimer`, and `setInterval(fetchSummary, ...)`
2. Keep the single initial `fetchSummary()` call on page load
3. Register a renderer on the SSE store:
   ```js
   // posture.summary → card key "summary" via fallback strip
   storeRegister('summary', function(data) {
       _lastPosture = data;
       updateBadge(data);
   });
   ```
4. When the mediator computes `posture.summary`, it emits `cache:done`
   via the EventBus bridge → SSE → `storeSet('summary', data)` →
   registered renderer calls `updateBadge(data)`

5. The "Rescan" button (`/posture/rescan`) triggers a forced recompute.
   The SSE event will push the new data to the badge automatically.

**New flow**:
```
Page load → fetch /api/posture/summary (one-time, instant from mediator cache)
          → updateBadge(data)

Mediator recomputes → SSE cache:done → storeSet('summary', data) → updateBadge

User clicks Rescan → POST /posture/rescan → mediator force recompute
                   → SSE cache:done → badge updates automatically
```

### Phase 4: Fix posture cache flush on restart

**Goal**: Posture data should survive restarts. No more "Pending" badge.

**Two approaches** (choose one):

**Approach A** — Route posture summary through mediator (preferred):
- Change `/api/posture/summary` to use the mediator path by default
  (currently requires `?via=mediator` query param)
- The mediator's `hydrate_cache()` already loads persisted data with
  no TTL check — data is immediately available after restart
- Requires: add `posture.summary` → `"posture:summary"` mapping to
  `_PATH_TO_CARD_KEY` in `activity.py`

**Approach B** — Fix the standalone cache's `_load_from_disk()`:
- Don't discard entries based on TTL when loading from disk on restart
- Load all persisted entries and serve them as "stale but valid"
- Mark them for refresh on next access

### Phase 5: Fix posture TTLs

**Goal**: TTL values should make sense given the new architecture.

Once polling is removed and updates are event-driven:
- `summary` TTL should match `full` TTL (both 60s, or both longer)
- `runtime` TTL should be > 0 (e.g., 30s or 60s) — circuit breaker
  state doesn't change every second
- Both `cache.py` TTLS dict AND mediator registration TTLs must match

The exact values to be decided — the PRINCIPLE is: no TTL should be
shorter than what queries it, and TTL=0 should only be used for data
that genuinely changes every second.

### Phase 6: Staleness detection

**Goal**: Know when cached posture data is stale without polling.

Already partially exists:
- `posture.project` depends on `devops.*` in the mediator tree
- When devops nodes change, the dependency graph cascades invalidation
- File watcher detects project file changes → invalidates scan → cascades

Still needed:
- Tool install events → invalidate `posture.toolchain`
- Runtime state change events → invalidate `posture.runtime`
- These cascade through `posture.full` → `posture.summary` automatically

---

## Implementation Order

| Phase | Priority | What | Depends On |
|-------|----------|------|------------|
| 1 | HIGHEST | Silent transport warm-up at startup | Nothing |
| 2 | HIGH | CDP discovery via work queue | Phase 1 |
| 3 | HIGH | Remove posture polling loop | Phase 4 (needs mediator path) |
| 4 | HIGH | Fix posture cache flush (use mediator path) | Nothing |
| 5 | MEDIUM | Fix posture TTLs | Nothing |
| 6 | LOW | Staleness detection | Phases 3-5 |

Phases 1+2 (CDP boot) and 3+4 (posture) are independent tracks.

---

## Files Involved

| File | Phase | Changes |
|------|-------|---------|
| `src/ui/web/cdp_client.py` | 1 | Add `silent=True` param to `warm()` |
| `src/ui/web/server.py` | 1,2 | Submit boot tasks to work queue |
| `src/core/services/mediator/registrations/tabmesh.py` | 2 | NEW — register `tabmesh.cdp_status` mediator node |
| `src/ui/web/templates/scripts/_tab_mesh.html` | 2 | Remove immediate `_meshCheckCDP()`, add sessionStorage + SSE double cache |
| `src/ui/web/templates/scripts/globals/_system_posture.html` | 3 | Remove `setInterval`, add SSE subscription |
| `src/ui/web/routes/posture.py` | 4 | Default to mediator path |
| `src/core/services/mediator/subscribers/activity.py` | 4 | Add posture key mapping |
| `src/core/services/system_posture/cache.py` | 5 | Fix TTLs |
| `src/core/services/mediator/registrations/posture.py` | 5 | Fix mediator TTLs |

---

## Boot Sequence — Before vs After

### BEFORE (current, broken):
```
server.py:
  posture_cache_init()     ← loads from disk, DISCARDS expired entries
  mediator_init()
  register_all()
  hydrate_cache()          ← loads to mediator (no TTL discard) but posture
                              route uses standalone cache, not mediator
  start_index_watcher()
  [server starts]

Page load (frontend):
  _meshInit()              ← fires IMMEDIATELY
    _meshCheckCDP()        ← 5-7s via curl.exe (no warm-up done)
      _meshDiscoverTarget() ← runs every load (not cached)
  startPolling()           ← setInterval(fetchSummary, 60000) BUG
    fetchSummary()         ← hits standalone cache → expired → 10-18s recompute
```

### AFTER (fixed):
```
server.py:
  posture_cache_init()
  mediator_init()
  register_all()             ← now includes tabmesh.cdp_status node
  hydrate_cache()            ← posture data + CDP status available immediately
  start_index_watcher()
  [server starts]

  work_queue NORMAL(2):
    cdp_client.warm(silent=True)  ← probes channels, warms bridge, NO notification
  work_queue LOW(3):
    mediator.get("tabmesh.cdp_status", force=True)
                                  ← checks CDP via fast channels from warm-up
                                  ← result persisted to disk + emitted via SSE

Page load (frontend):
  Badge shows last known posture immediately (from mediator via SSE snapshot
  or initial page data — NOT "Pending")

  storeRegister('summary', updateBadge)  ← subscribe to SSE updates
  fetchSummary() ONE TIME               ← via mediator path, instant from cache

  _meshInit()
    1. sessionStorage.getItem('cdp_status') → if present, _meshCDPAvailable = cached
    2. sessionStorage.getItem('chrome_target_{tabId}') → if present, skip discovery
    3. storeRegister('tabmesh:cdp_status', updateCDP) → subscribe to SSE
    4. If no cached CDP status → wait for SSE cache:done from boot task
    5. If CDP available + no cached target → _meshDiscoverTarget()
       → on success → sessionStorage.setItem('chrome_target_{tabId}', id)
```
