# Implementation Plan: Posture & CDP Boot Sequence Refactor

**Source**: `.agent/plans/posture-cdp-refactor.md` (analysis & investigation)
**Created**: 2026-03-14

---

## Overview

Six phases, two independent tracks. Each sub-task is independently
shippable and leaves the system in a working state.

**Track A — CDP Boot** (Phases 1, 2): Silent warm-up → mediator-backed
CDP status → event-driven tab lifecycle.

**Track B — Posture** (Phases 3, 4, 5): Remove polling → mediator path
by default → fix TTLs.

**Phase 6** (Staleness) depends on both tracks.

---

## Phase 1: Silent Transport Warm-up at Startup

> Fixes **Bug 5**: CDP called before transport warm-up
> Priority: HIGHEST — all CDP improvements depend on this

### 1.1 Add `silent` parameter to `cdp_client.warm()`

**File**: `src/ui/web/cdp_client.py`
**Function**: `warm()` (line 350)

**Current signature**:
```python
def warm(port: int = _DEFAULT_PORT) -> dict:
```

**New signature**:
```python
def warm(port: int = _DEFAULT_PORT, *, silent: bool = False) -> dict:
```

**Changes**:
- Lines 382-407: Wrap the `create_notification()` block in `if not silent:`
- Everything else stays IDENTICAL: probing (line 371), lifecycle check
  (lines 373-379), PS bridge warm-up (lines 409-417)

**Exact diff** (lines 381-407):
```python
# BEFORE:
    # If WSL2 NAT mode and no fast channel, notify the user
    if router.needs_tunnel(port):

# AFTER:
    # If WSL2 NAT mode and no fast channel, notify the user
    # (skip notification during silent startup warm-up)
    if router.needs_tunnel(port) and not silent:
```

One line change. That's it for 1.1.

**Verification**: `warm(silent=True)` returns the same dict as `warm()`.
No notification created when `silent=True` and `needs_tunnel()` is True.

---

### 1.2 Submit boot warm-up task to work queue

**File**: `src/ui/web/server.py`
**Location**: After `start_index_watcher()` (line 292), before the Python
runtime optimization notification (line 304).

**Add**:
```python
    # ── CDP transport warm-up (background, silent) ──────────────
    # Probe all channels and warm the PS bridge BEFORE any CDP
    # operation attempts.  Priority NORMAL (2) — runs during first
    # page load, doesn't block server startup.
    try:
        from src.ui.web import cdp_client as _cdp_client
        from src.core.services.mediator.work_queue import WorkItem, Priority

        _wq = mediator_inst.work_queue
        _wq.submit(WorkItem(
            priority=Priority.NORMAL,
            size=1,
            path="boot.transport_warmup",
            resolver=lambda: _cdp_client.warm(silent=True),
        ))
        logger.info("Submitted boot.transport_warmup to work queue (NORMAL)")
    except Exception as exc:
        logger.debug("Could not submit transport warm-up: %s", exc)
```

**Verification**: Server starts, log shows
`"Submitted boot.transport_warmup to work queue (NORMAL)"`.
Work queue status endpoint shows the task completed.

---

## Phase 2: CDP Status as Mediator Node with Double Cache

> Fixes **Bug 2** (discover-target re-runs), **Bug 3** (cdp-status re-checked)
> Depends on: Phase 1

### 2.1 Create `registrations/tabmesh.py`

**File**: `src/core/services/mediator/registrations/tabmesh.py` (NEW)

**Content**:
```python
"""
Tab Mesh domain — CDP status mediator node.

Registers ``tabmesh.cdp_status`` to cache Chrome DevTools Protocol
availability.  Persisted to disk.  Hydrated on server restart.
Updated by the boot warm-up task and invalidated on CDP failure.
"""

from __future__ import annotations

import logging
import time

from src.core.services.mediator.core import QueryMediator
from src.core.services.mediator.tree import TreeRegistration

logger = logging.getLogger(__name__)


def register_tabmesh(mediator: QueryMediator) -> None:
    """Register tab mesh nodes in the mediator tree."""
    tree = mediator.tree

    tree.register(TreeRegistration(
        path="tabmesh.cdp_status",
        resolver=_resolve_cdp_status,
        ttl=300,          # 5 min — Chrome doesn't restart often
        persist=True,     # survives server restart
        size=1,
    ))


def _resolve_cdp_status() -> dict:
    """Check Chrome DevTools Protocol availability.

    Calls cdp_client.is_available() to check if Chrome's
    /json/version endpoint is reachable via any transport channel.
    """
    try:
        from src.ui.web.cdp_client import is_available, try_discover_endpoint

        endpoint = try_discover_endpoint()
        available = is_available() if endpoint else False

        return {
            "available": available,
            "endpoint": endpoint,
            "ts": time.time(),
        }
    except Exception as exc:
        logger.debug("CDP status check failed: %s", exc)
        return {
            "available": False,
            "endpoint": None,
            "error": str(exc),
            "ts": time.time(),
        }
```

**TreeRegistration fields used** (verified from `tree.py` lines 41-75):
- `path`: str ✓
- `resolver`: callable ✓
- `ttl`: float ✓
- `persist`: bool ✓
- `size`: int ✓

---

### 2.2 Register tabmesh in `register_all()`

**File**: `src/core/services/mediator/registrations/__init__.py`
**Function**: `register_all()` (line 24)

**Add import** (after line 39):
```python
    from .tabmesh import register_tabmesh
```

**Add call** (after `register_catalog(mediator)` on line 47, before subscribers):
```python
    register_tabmesh(mediator)  # tabmesh.* — CDP status, leaf, no cascade deps
```

**Verification**: Server starts, log shows `tabmesh.cdp_status` in the
registered nodes list.

---

### 2.3 Submit CDP discovery boot task to work queue

**File**: `src/ui/web/server.py`
**Location**: After the transport warm-up submission (added in 1.2).

**Add**:
```python
    # ── CDP status discovery (background, after warm-up) ────────
    # Check Chrome availability using the channels that the
    # transport warm-up just established.  Priority LOW (3) —
    # guaranteed to run AFTER the NORMAL (2) warm-up task.
    # Result persisted to disk and emitted via SSE cache:done.
    try:
        from src.core.services.mediator import get_mediator as _get_med

        def _boot_cdp_discovery():
            m = _get_med()
            return m.get("tabmesh.cdp_status", force=True)

        _wq.submit(WorkItem(
            priority=Priority.LOW,
            size=1,
            path="boot.cdp_discovery",
            resolver=_boot_cdp_discovery,
        ))
        logger.info("Submitted boot.cdp_discovery to work queue (LOW)")
    except Exception as exc:
        logger.debug("Could not submit CDP discovery: %s", exc)
```

**Verification**: Work queue status shows `boot.cdp_discovery` completed
after `boot.transport_warmup`. SSE stream shows `cache:done` event for
card key `cdp_status`.

**SSE card key**: `tabmesh.cdp_status` → fallback `_path_to_card_key`
strips first segment → `"cdp_status"`. Frontend receives it as
`storeSet('cdp_status', data)`.

---

### 2.4 Add `_PATH_TO_CARD_KEY` entry for tabmesh

**File**: `src/core/services/mediator/subscribers/activity.py`
**Dict**: `_PATH_TO_CARD_KEY` (line 29)

**Add** (after catalog entries, before closing `}`):
```python
    # tabmesh domain
    "tabmesh.cdp_status": "tabmesh:cdp_status",
```

This gives the frontend a namespaced key `tabmesh:cdp_status` instead of
the fallback `cdp_status` which could collide with other domains.

**Update 2.3 note**: The card key is now `tabmesh:cdp_status`, so the
frontend `storeRegister()` call uses `'tabmesh:cdp_status'`.

---

### 2.5 Frontend: Remove immediate `_meshCheckCDP()`, add double cache

**File**: `src/ui/web/templates/scripts/_tab_mesh.html`

#### 2.5a Remove immediate `_meshCheckCDP()` from `_meshInit()`

**Location**: Line 877

```js
// REMOVE this line:
        _meshCheckCDP();
```

#### 2.5b Add CDP status cache check + SSE subscription

**Location**: In `_meshInit()`, where `_meshCheckCDP()` was (line 877).
Replace with:

```js
        // ── CDP status: double cache (sessionStorage + mediator SSE) ──
        // 1. Check if sibling tabs already proved CDP is available
        var _siblingWithCDP = null;
        _meshRegistry.forEach(function(entry) {
            if (entry.chromeTargetId && entry.alive) {
                _siblingWithCDP = entry;
            }
        });

        if (_siblingWithCDP) {
            // Sibling already has CDP — skip the 5-7s status check
            _meshCDPAvailable = true;
            sessionStorage.setItem('cdp_status', JSON.stringify({
                available: true, ts: Date.now(),
            }));
            _meshDiscoverTarget();
        } else {
            // 2. Check sessionStorage
            var _cachedCDP = sessionStorage.getItem('cdp_status');
            if (_cachedCDP) {
                try {
                    var _parsed = JSON.parse(_cachedCDP);
                    _meshCDPAvailable = _parsed.available;
                    if (_parsed.available) {
                        _meshDiscoverTarget();
                    }
                } catch (_) {}
            }

            // 3. Subscribe to SSE for boot task result + future updates
            if (typeof storeRegister === 'function') {
                storeRegister('tabmesh:cdp_status', function(data) {
                    _meshCDPAvailable = data.available;
                    sessionStorage.setItem('cdp_status', JSON.stringify(data));
                    if (data.available && !_meshIdentity.chromeTargetId) {
                        _meshDiscoverTarget();
                    }
                });
            }
        }
```

#### 2.5c Cache `chromeTargetId` in sessionStorage on discovery

**Location**: Inside `_meshDiscoverTarget()` success handler (around line 618).
After `_meshIdentity.chromeTargetId = ...`:

```js
        sessionStorage.setItem(
            'chrome_target_' + _meshTabId,
            _meshIdentity.chromeTargetId
        );
```

#### 2.5d Check sessionStorage for cached target before discovery

**Location**: At the top of `_meshDiscoverTarget()` (around line 598).
Add early return:

```js
    function _meshDiscoverTarget() {
        // Check sessionStorage cache first
        var cached = sessionStorage.getItem('chrome_target_' + _meshTabId);
        if (cached) {
            _meshIdentity.chromeTargetId = cached;
            _meshSendPing();  // broadcast to siblings
            return;
        }
        // ... existing discovery logic
```

**Verification**:
1. First page load → no `cdp-status` API call, waits for SSE
2. Boot task completes → SSE pushes `tabmesh:cdp_status` → discovery fires
3. Page reload → sessionStorage has `cdp_status` + `chrome_target_*` → no API calls
4. New tab → reads sibling registry → CDP proven → only discovers own target

---

### 2.6 Extend `_meshSendLeave()` with `sendBeacon`

**File**: `src/ui/web/templates/scripts/_tab_mesh.html`
**Function**: `_meshSendLeave()` (line 224)

**Add after the `_meshBroadcast()` call**:

```js
        // Notify backend (fire-and-forget, survives page unload)
        try {
            navigator.sendBeacon('/api/tab-mesh/leave', JSON.stringify({
                tabId: _meshTabId,
                chromeTargetId: _meshIdentity.chromeTargetId || null,
            }));
        } catch (_) {}
```

---

### 2.7 Add `cdp_lost` BroadcastChannel message handler

**File**: `src/ui/web/templates/scripts/_tab_mesh.html`
**Function**: `_meshHandleMessage()` (line 234), inside the `switch(msg.type)`

**Add case** (after `case 'dump':` around line 303):

```js
            case 'cdp_lost':
                // Chrome crashed — invalidate local CDP state
                _meshCDPAvailable = false;
                _meshIdentity.chromeTargetId = null;
                sessionStorage.removeItem('cdp_status');
                sessionStorage.removeItem('chrome_target_' + _meshTabId);
                break;
```

---

### 2.8 Add `_meshCDPFailure()` function

**File**: `src/ui/web/templates/scripts/_tab_mesh.html`
**Location**: After `_meshSendLeave()` (around line 230)

```js
    function _meshCDPFailure() {
        _meshCDPAvailable = false;
        _meshIdentity.chromeTargetId = null;
        sessionStorage.removeItem('cdp_status');
        sessionStorage.removeItem('chrome_target_' + _meshTabId);

        // Horizontal channel: tell all sibling tabs
        _meshBroadcast({
            type: 'cdp_lost',
            id:   _meshTabId,
            ts:   Date.now(),
        });

        // Vertical channel: tell backend to invalidate mediator node
        try {
            navigator.sendBeacon('/api/tab-mesh/cdp-invalidate');
        } catch (_) {}
    }
```

**Wire into error handlers**: In `_meshCheckCDP()` and
`_meshDiscoverTarget()`, any `catch` or error response should call
`_meshCDPFailure()` when the failure is a network/connection error
(not a "no target found" which is normal for non-Chrome pages).

---

### 2.9 Extend `_meshHandleKill()` with CDP cleanup

**File**: `src/ui/web/templates/scripts/_tab_mesh.html`
**Function**: `_meshHandleKill()` (line 392)

**Add before `_meshSendLeave()` call** (before line 404):

```js
        // Clean up CDP state for this tab
        if (_meshIdentity.chromeTargetId) {
            try {
                navigator.sendBeacon('/api/tab-mesh/leave', JSON.stringify({
                    tabId: _meshTabId,
                    chromeTargetId: _meshIdentity.chromeTargetId,
                }));
            } catch (_) {}
            _meshIdentity.chromeTargetId = null;
            sessionStorage.removeItem('chrome_target_' + _meshTabId);
        }
```

---

### 2.10 Backend: Add `leave` and `cdp-invalidate` endpoints

**File**: `src/ui/web/routes/tab_mesh/__init__.py`

#### 2.10a `POST /api/tab-mesh/leave`

```python
@tab_mesh_bp.route("/tab-mesh/leave", methods=["POST"])
def tab_mesh_leave():
    """Handle tab departure beacon.

    Receives sendBeacon payload when a tab closes, is killed,
    or the browser exits.  Removes the tab's chromeTargetId
    from the active target index.
    """
    try:
        data = request.get_json(silent=True) or {}
        tab_id = data.get("tabId")
        target_id = data.get("chromeTargetId")

        if tab_id and target_id:
            logger.debug(
                "Tab %s leaving, releasing target %s",
                tab_id, target_id,
            )
            # Future: maintain a server-side target index
            # For now, just log for observability

        return "", 204
    except Exception:
        return "", 204  # sendBeacon — never fail
```

#### 2.10b `POST /api/tab-mesh/cdp-invalidate`

```python
@tab_mesh_bp.route("/tab-mesh/cdp-invalidate", methods=["POST"])
def tab_mesh_cdp_invalidate():
    """Invalidate cached CDP status.

    Called via sendBeacon when a CDP operation fails,
    indicating Chrome may have crashed or become unreachable.
    """
    try:
        from src.core.services.mediator import get_mediator

        m = get_mediator()
        m.put("tabmesh.cdp_status", cascade=False)
        logger.info("CDP status invalidated via tab-mesh beacon")
    except Exception as exc:
        logger.debug("CDP invalidation failed: %s", exc)

    return "", 204
```

**Note**: `m.put()` invalidates the cache entry and emits `cache:bust`
via the EventBus bridge → SSE → all connected tabs clear their state.

**Verification**:
- Tab close → `sendBeacon` → server log shows "Tab X leaving"
- CDP failure → `sendBeacon` → server log shows "CDP status invalidated"
- SSE stream shows `cache:bust` event for `tabmesh:cdp_status`

---

## Phase 3: Remove Posture Polling Loop

> Fixes **Bug 1**: Posture polling loop should not exist
> Depends on: Phase 4 (needs mediator path for reliable data)
> Can be implemented in parallel if testing against mediator path

### 3.1 Remove `setInterval` from `_system_posture.html`

**File**: `src/ui/web/templates/scripts/globals/_system_posture.html`

#### 3.1a Remove polling infrastructure

**Remove** the following (exact locations to be confirmed by reading
the full file at implementation time):
- `POLL_INTERVAL` constant
- `_pollTimer` variable
- `setInterval(fetchSummary, POLL_INTERVAL)` call
- `clearInterval(_pollTimer)` if any cleanup exists

#### 3.1b Keep single initial fetch

**Keep**: The initial `fetchSummary()` call on page load. This ensures
the badge has data even if the mediator hasn't computed yet.

#### 3.1c Add SSE subscription

**Add** (in the init block, after `fetchSummary()`):

```js
        // Subscribe to SSE for posture updates (replaces polling)
        if (typeof storeRegister === 'function') {
            storeRegister('summary', function(data) {
                _lastPosture = data;
                updateBadge(data);
            });
        }
```

**Card key**: `posture.summary` → `_path_to_card_key` fallback strips
first segment → `"summary"`. The frontend receives it as
`storeSet('summary', data)`.

**Verification**:
1. Page load → one `fetchSummary()` call → badge shows data
2. No more periodic API calls (network tab shows no `/api/posture/summary`
   after initial load)
3. Trigger rescan → SSE pushes `cache:done` for `summary` → badge updates

---

## Phase 4: Fix Posture Cache Flush on Restart

> Fixes **Bug 4**: Posture data thrown away on restart
> No dependencies — can start immediately

### 4.1 Route posture summary through mediator by default

**File**: `src/ui/web/routes/posture.py`
**Function**: `posture_summary()` (line 222)

**Current logic** (lines 238-250):
```python
        if via == "mediator":
            # mediator path
        else:
            # standalone cache path (TTL-discarding)
```

**New logic**: Swap default — mediator is the primary path:
```python
        if via == "standalone":
            from src.core.services.system_posture import get_summary
            summary = get_summary(force=force)
            return jsonify(summary)
        else:
            # Default: use mediator (persisted, no TTL discard on load)
            from src.core.services.mediator import get_mediator
            m = get_mediator()
            if force:
                m.put("posture.summary", cascade=False)
            r = m.get("posture.summary", force=force)
            return jsonify(r["data"])
```

**Also update `posture_rescan()`** (line 255) with the same swap.

### 4.2 Add `posture.summary` to `_PATH_TO_CARD_KEY`

**File**: `src/core/services/mediator/subscribers/activity.py`
**Dict**: `_PATH_TO_CARD_KEY` (line 29)

**Add**:
```python
    # posture domain
    "posture.summary": "posture:summary",
    "posture.full": "posture:full",
```

**Frontend impact**: The SSE card key changes from `"summary"` (fallback)
to `"posture:summary"` (explicit). Update the `storeRegister()` call in
Phase 3.1c accordingly:
```js
storeRegister('posture:summary', function(data) { ... });
```

**Verification**:
1. Server restart → badge shows last known posture IMMEDIATELY
   (from mediator's hydrated cache — no TTL discard)
2. No "Pending" state lasting 10-18 seconds
3. `/api/posture/summary` returns data without `?via=mediator`

---

## Phase 5: Fix Posture TTLs

> Fixes **Bug 6**: Short TTLs causing unnecessary recomputation
> No dependencies — can start immediately

### How TTLs interact with cascade invalidation

TTLs are **backstops**, not the primary update mechanism. The cascade
invalidation chain handles real changes:

```
File changes → FS watcher → devops.* invalidated
  → posture.project cascade-invalidated (depends_on=["devops.*"])
    → posture.full cascade-invalidated (depends_on posture.project)
      → posture.summary cascade-invalidated (depends_on posture.full)
        → SSE push → badge updates
```

Cascade ignores TTLs entirely — it wipes cached values immediately.
The TTL only matters when **nothing triggered a cascade** — it says
"even if no files changed, after this many seconds, consider stale."

### Confirmed TTL values

| Node | Current | New | Rationale |
|------|---------|-----|-----------|
| `posture.summary` | 30s | **600s** (10 min) | Real updates via cascade+SSE. TTL is backstop only. |
| `posture.full` | 60s | **1200s** (20 min) | Summary depends on full. 1200s > 600s avoids full recomputing when only summary expires. |
| `posture.runtime` | 0 | **0** (no change) | In-memory reads (circuit breakers, retry queue). Cheap. Always fresh is fine. |
| `posture.platform` | inf | inf (no change) | OS/kernel doesn't change until restart. |
| `posture.toolchain` | 300s | 300s (no change) | 5 min is reasonable for tool version checks. |
| `posture.project` | 60s | 60s (no change) | Has `depends_on=["devops.*"]` for cascade. |

### 5.1 Fix standalone cache TTLs

**File**: `src/core/services/system_posture/cache.py`
**Location**: `TTLS` dict (line 74)

**Changes**:
```python
# BEFORE:
"full": 60,                # Full posture assembly
"summary": 30,             # Nav badge summary

# AFTER:
"full": 1200,              # 20 min — cascade handles real changes
"summary": 600,            # 10 min — cascade handles real changes
```

### 5.2 Fix mediator registration TTLs

**File**: `src/core/services/mediator/registrations/posture.py`
**Location**: TTL values in `TreeRegistration()` calls

**Changes**:
```python
# posture.full (line 126):
ttl=1200,            # 20 min — cascade handles real changes

# posture.summary (line 144):
ttl=600,             # 10 min — cascade handles real changes
```

**Verification**:
1. After fix, posture data only recomputes via TTL backstop every 10-20 min
2. File changes still trigger immediate cascade → SSE → badge update
3. Opening the posture modal after a file change: cascade already
   invalidated → `mediator.get()` recomputes → fresh data

---

## Phase 6: Staleness Detection

> Depends on Phases 3-5
> Ensures all posture change events propagate via mediator cascade → SSE

### 6.1 Cascade invalidation via mediator dependencies

**Status**: ✅ Already working — no changes needed.

`posture.project` has `depends_on=["devops.*"]` in its registration.
When file changes happen:
```
FS watcher → devops.* nodes update
  → posture.project cascade-invalidated
    → posture.full cascade-invalidated
      → posture.summary cascade-invalidated
        → SSE push → badge updates
```

### 6.2 Tool install events

**Status**: ✅ Implemented — default-swap on `rescan-tool` endpoint.

**File**: `src/ui/web/routes/posture.py`
**Function**: `posture_rescan_tool()` (line 295)

The mediator path already existed (`m.put("posture.toolchain", cascade=True)`)
but was behind `?via=mediator`. Swapped default to mediator, same pattern
as Phase 4. Now when a tool is updated:
```
Frontend calls /api/posture/rescan-tool
  → m.put("posture.toolchain", cascade=True)
    → posture.full cascade-invalidated
      → posture.summary cascade-invalidated
        → SSE push → badge updates
```

### 6.3 Runtime state change events

**Status**: ✅ No changes needed.

Runtime pillar (circuit breakers, retry queue) has TTL=0 — always
recomputed fresh from in-memory state. These are cheap reads.
There is no external event source that changes circuit breaker state
outside of normal request processing, so no invalidation hook is needed.


---

## Implementation Order & Dependencies

```
Phase 1.1  ──→  Phase 1.2  ──→  Phase 2.1  ──→  Phase 2.2  ──→  Phase 2.3
(warm silent)   (boot task)     (tabmesh.py)    (register_all)  (boot CDP)
                                                                     │
                                                    Phase 2.4  ◄─────┘
                                                    (card key)
                                                         │
                                              Phase 2.5a-d  ◄───────┘
                                              (frontend cache)
                                                         │
                                   Phase 2.6-2.9  ◄──────┘
                                   (lifecycle events)
                                              │
                                   Phase 2.10  ◄─────────┘
                                   (backend endpoints)

Phase 4.1  ──→  Phase 4.2
(mediator path)  (card key)
       │
Phase 3.1  ◄─────┘
(remove poll)
       │
Phase 5.1  ──→  Phase 5.2
(cache TTLs)    (mediator TTLs)

Phase 6 (deferred)
```

**Track A** (CDP): 1.1 → 1.2 → 2.1 → 2.2 → 2.3 → 2.4 → 2.5 → 2.6-2.9 → 2.10
**Track B** (Posture): 4.1 → 4.2 → 3.1 → 5.1 → 5.2

Tracks A and B are independent and can be implemented in parallel.

---

## Files Modified — Complete List

| File | Sub-task | Change |
|------|----------|--------|
| `src/ui/web/cdp_client.py` | 1.1 | Add `silent` param, guard notification |
| `src/ui/web/server.py` | 1.2, 2.3 | Submit 2 boot tasks to work queue |
| `src/core/services/mediator/registrations/tabmesh.py` | 2.1 | **NEW** — `tabmesh.cdp_status` node |
| `src/core/services/mediator/registrations/__init__.py` | 2.2 | Import + call `register_tabmesh()` |
| `src/core/services/mediator/subscribers/activity.py` | 2.4, 4.2 | Add card key mappings |
| `src/ui/web/templates/scripts/_tab_mesh.html` | 2.5-2.9 | Double cache, lifecycle events, `cdp_lost` |
| `src/ui/web/routes/tab_mesh/__init__.py` | 2.10 | Add `/leave` and `/cdp-invalidate` endpoints |
| `src/ui/web/templates/scripts/globals/_system_posture.html` | 3.1 | Remove polling, add SSE subscription |
| `src/ui/web/routes/posture.py` | 4.1 | Default to mediator path |
| `src/core/services/system_posture/cache.py` | 5.1 | Fix TTLs |
| `src/core/services/mediator/registrations/posture.py` | 5.2 | Fix mediator TTLs |

---

## Risks & Open Questions

1. **`storeRegister` availability**: Is `storeRegister()` defined by the
   time `_meshInit()` runs? The SSE event stream script loads as a global.
   Need to verify load order.
   **RESOLVED**: `_event_stream.html` is included at line 44 in
   `dashboard.html`, `_tab_mesh.html` at line 60. Load order confirmed.

2. **`m.put()` for invalidation**: Confirm that `m.put()` with
   `cascade=False` only invalidates the target node without triggering a
   recompute. Check if `cache:bust` is emitted.

3. **Phase 4 rollback**: If routing through mediator by default causes
   unexpected issues, the `?via=standalone` escape hatch is preserved.

4. **sendBeacon content type**: `navigator.sendBeacon()` sends
   `text/plain` by default. The backend endpoint needs to handle this
   (use `request.get_json(silent=True)` with fallback).
