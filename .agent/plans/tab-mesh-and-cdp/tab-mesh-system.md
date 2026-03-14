# Tab Mesh System — Complete Implementation Plan

> **Created**: 2026-03-06 13:00
> **Status**: IMPLEMENTED — Phases 0-6 complete. Phase 7 (polish) remaining.
> **Rule**: No hacks. No band-aids. A real system with proper handshakes.
> **Rule**: Adaptive to browser capabilities. Multiple fallback layers.
> **Rule**: ONE change at a time. Verify. Then next.

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Environment & Constraints](#environment--constraints)
3. [Research Findings](#research-findings)
4. [Architecture Overview](#architecture-overview)
5. [Service Worker — The Focus Engine](#service-worker--the-focus-engine)
6. [BroadcastChannel — The Mesh Bus](#broadcastchannel--the-mesh-bus)
7. [Message Protocol](#message-protocol)
8. [Tab Identity Model](#tab-identity-model)
9. [Title Engine](#title-engine)
10. [Navigation Flow](#navigation-flow)
11. [Session Control (Kill)](#session-control-kill)
12. [Debug Panel](#debug-panel)
13. [Browser Capability Detection & Fallbacks](#browser-capability-detection--fallbacks)
14. [File Layout](#file-layout)
15. [Implementation Phases](#implementation-phases)
16. [Phase Details](#phase-details)

---

## Problem Statement

The admin panel (`localhost:8000/`) and Docusaurus sites (`localhost:8000/pages/site/{segment}/`)
need to communicate across browser tabs:

- **Navigate**: clicking a peek/audit link on Docusaurus should navigate the admin panel's
  Content Vault to the right file — via SPA routing, no full reload
- **Focus**: the admin tab should come to the front when navigated
- **Awareness**: each tab should know what other tabs are alive and what they're showing
- **Control**: ability to kill stale tabs remotely (blocking overlay requiring refresh)
- **Debug**: a panel in admin showing all live tabs, their routes, and actions

Previous attempts hacked `window.open()` + `BroadcastChannel` acks + `setTimeout` fallbacks.
This failed because:
- `window.open()` inside `setTimeout` loses user gesture → popup blocker kills it silently
- `window.focus()` from a BroadcastChannel handler has no transient activation → browser ignores it
- `window.open('', 'name')` in Chrome 2024+ unreliably matches existing named windows
- Race conditions between ack timeouts and fallback logic created glitchy behavior

The correct approach uses **two separate systems** for **two separate problems**:
1. **Service Worker** with `client.focus()` — for bringing tabs to the foreground
2. **BroadcastChannel** — for data messaging (navigate, state sync, presence, kill)

---

## Environment & Constraints

### What we control (webmaster)

| Surface | How | Detail |
|---|---|---|
| Admin panel | Flask serves `dashboard.html` + `<script>` partials | Full control of all JS |
| Docusaurus sites | Flask serves built static files at `/pages/site/{segment}/` | Theme hooks injected at build time |
| Docusaurus build | `docusaurus.py` → template processing | We inject `Root.tsx.tmpl`, hooks, CSS |
| Service Worker | Flask can serve `sw.js` at any path | Need root-scope route |
| Static files | `src/ui/web/static/` → served at `/static/` | CSS, data files |

### Origin model

Everything is **same origin**: `http://localhost:8000`

| URL | Type |
|---|---|
| `http://localhost:8000/` | Admin panel (SPA, hash-routed) |
| `http://localhost:8000/#content/docs/path@preview` | Admin → Content tab → file preview |
| `http://localhost:8000/pages/site/code-docs/` | Docusaurus site (file-based routing) |
| `http://localhost:8000/pages/site/code-docs/core/services/` | Docusaurus page |

Same origin means:
- ✅ BroadcastChannel works
- ✅ Service Worker can control ALL pages under `/`
- ✅ `clients.matchAll({ includeUncontrolled: true })` sees ALL tabs
- ✅ `client.focus()` can bring ANY same-origin tab to front
- ✅ `clients.openWindow()` can open new tabs
- ✅ No CORS issues

### Browser support targets

| API | Chrome | Firefox | Safari | Edge |
|---|---|---|---|---|
| BroadcastChannel | 54+ ✅ | 38+ ✅ | 15.4+ ✅ | 79+ ✅ |
| Service Worker | 40+ ✅ | 44+ ✅ | 11.1+ ✅ | 17+ ✅ |
| `client.focus()` | ✅ | ✅ | ✅ | ✅ |
| `clients.matchAll()` | ✅ | ✅ | ✅ | ✅ |
| `clients.openWindow()` | ✅ | ✅ | ✅ | ✅ |
| `crypto.randomUUID()` | 92+ ✅ | 95+ ✅ | 15.4+ ✅ | 92+ ✅ |
| `visibilitychange` | ✅ all | ✅ all | ✅ all | ✅ all |

localhost is treated as a **secure context** → Service Workers are allowed.

---

## Research Findings

### Service Worker `client.focus()` — the key mechanism

```
Page receives user click
  → Page sends postMessage to Service Worker
    → Service Worker calls clients.matchAll() to find target tab
      → Service Worker calls client.focus() to bring it to front
        → THIS WORKS because transient activation propagates through the message chain
```

**Critical rule**: `client.focus()` and `clients.openWindow()` MUST be triggered by a user gesture.
The gesture propagates from page click → postMessage → SW handler. This is spec-compliant.

`client.focus()` will be REJECTED with `InvalidAccessError` if called without user activation
(e.g., from a timer, from a periodic ping, or from a BC handler that wasn't user-initiated).

### BroadcastChannel — reliable for data, unreliable for focus

- Messages always arrive (same-origin, 100% reliable)
- Cannot propagate user activation — `window.focus()` from a BC handler is ignored
- Perfect for: presence, state sync, navigate (data), kill messages
- NOT suitable for: focus control

### `window.open('', 'name')` — unreliable in Chrome 2024+

- Chrome often opens a NEW blank tab instead of finding the named one
- Only reliably finds windows that were OPENED by `window.open` with that name
- Setting `window.name` after load does NOT guarantee findability
- CONCLUSION: do not rely on this for focus. Use Service Worker instead.

### `window.focus()` — only works on the calling window

- A page can only focus ITSELF
- Cannot focus another tab from JS alone
- Even from a BC handler: no activation → browser ignores
- CONCLUSION: Service Worker is the only way to focus cross-tab

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        TAB MESH SYSTEM                          │
│                                                                 │
│               ┌──────────────────────────┐                      │
│               │   SERVICE WORKER (sw.js) │                      │
│               │                          │                      │
│               │  • clients.matchAll()    │                      │
│               │  • client.focus()        │                      │
│               │  • clients.openWindow()  │                      │
│               │  • Message relay         │                      │
│               └──────────┬───────────────┘                      │
│                          │ postMessage                          │
│          ┌───────────────┼───────────────────┐                  │
│          │               │                   │                  │
│   ┌──────▼──────┐  ┌─────▼──────┐  ┌────────▼────────┐        │
│   │  Admin Tab  │  │ Site Tab A │  │   Site Tab B    │        │
│   │  (SPA)      │  │ (Docusaurus│  │   (Docusaurus)  │        │
│   └──────┬──────┘  └─────┬──────┘  └────────┬────────┘        │
│          │               │                   │                  │
│          └───────────────┼───────────────────┘                  │
│                          │ BroadcastChannel                     │
│               ┌──────────▼───────────────┐                      │
│               │  'devops-tab-mesh'        │                      │
│               │                          │                      │
│               │  • Presence (join/ping)  │                      │
│               │  • Registry sync         │                      │
│               │  • Navigate (data)       │                      │
│               │  • State broadcast       │                      │
│               │  • Kill command          │                      │
│               │  • Inspect/dump          │                      │
│               └──────────────────────────┘                      │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                 DEBUG PANEL (admin only)                 │    │
│  │   Debugging tab → "📡 Mesh" mode                        │    │
│  │   Live tab list • Navigate • Kill • Inspect             │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### Separation of concerns

| Concern | Mechanism | Why |
|---|---|---|
| **Focus a tab** | Service Worker `client.focus()` | Only mechanism that works cross-tab |
| **Open a new tab** | Service Worker `clients.openWindow()` | Popup-blocker safe when from user gesture |
| **Presence & registry** | BroadcastChannel join/ping/leave | Lightweight, real-time, 100% reliable |
| **Navigation routing** | BroadcastChannel navigate message | Target tab sets `location.hash` (SPA) |
| **State sync** | BroadcastChannel state message | Hash/title changes broadcast to all |
| **Remote kill** | BroadcastChannel kill message | Target renders blocking overlay |
| **Title flash** | `document.title` + `visibilitychange` | Universal, no API restrictions |

---

## Service Worker — The Focus Engine

### File: `src/ui/web/static/sw.js`

The Service Worker is NOT a general-purpose worker. It has ONE job: **tab focus and opening**.
All data messaging goes through BroadcastChannel, not through the SW.

### SW responsibilities

1. `FOCUS_TAB` — find a tab by URL pattern, bring it to front
2. `OPEN_TAB` — open a new tab at a URL (if target not found)
3. `LIST_TABS` — return all open tabs (for debug panel verification)

### SW message protocol

```javascript
// Page → SW
{ type: 'FOCUS_TAB', urlPattern: '/admin', hash: '#content/docs/vault.py@preview' }
{ type: 'OPEN_TAB', url: 'http://localhost:8000/#content/docs/vault.py@preview' }
{ type: 'LIST_TABS' }

// SW → Page (responses via MessageChannel port)
{ type: 'FOCUS_RESULT', found: true, url: 'http://localhost:8000/' }
{ type: 'FOCUS_RESULT', found: false }
{ type: 'TAB_LIST', tabs: [{ url, focused, visibilityState }...] }
```

### Flask route for SW

The Service Worker MUST be served at the root scope (`/`) to control all pages.
Flask needs a route to serve `sw.js`:

```python
# In server.py or a dedicated route
@app.route('/sw.js')
def service_worker():
    return send_from_directory(app.static_folder, 'sw.js',
                               mimetype='application/javascript')
```

The `Service-Worker-Allowed` header may be needed if the SW file is not at root:
```python
response.headers['Service-Worker-Allowed'] = '/'
```

### SW registration

Every page (admin + Docusaurus) registers the SW on load:

```javascript
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js', { scope: '/' })
        .then(reg => reg.active || navigator.serviceWorker.ready)
        .catch(err => console.warn('SW registration failed:', err));
}
```

### SW focus flow

```
User clicks "Open in Vault" on Docusaurus page:
  1. Click handler (user gesture context):
     a. BroadcastChannel: post { navigate, targetType: 'admin', hash }
        → Admin tab receives → sets location.hash → SPA routes
     b. Service Worker: postMessage { FOCUS_TAB, urlPattern: '/', hash }
        → SW calls clients.matchAll()
        → SW finds admin tab (pathname === '/')
        → SW calls admin.focus() → TAB COMES TO FRONT
        → If admin not found: SW calls clients.openWindow(url)
  2. Both happen in same synchronous click handler
  3. No timeouts. No ack-waiting. No races.
```

### SW focus matching logic

```javascript
// Inside SW message handler
async function handleFocusTab(urlPattern, hash) {
    const windows = await self.clients.matchAll({
        type: 'window',
        includeUncontrolled: true
    });

    // Find the best match
    const target = windows.find(client => {
        const url = new URL(client.url);
        if (urlPattern === '/admin' || urlPattern === '/') {
            // Admin panel: pathname is exactly '/'
            return url.pathname === '/';
        }
        // Site pages: pathname starts with pattern
        return url.pathname.startsWith(urlPattern);
    });

    if (target) {
        // Navigate via hash if provided (admin will handle via hashchange)
        // Note: we don't navigate here — BC navigate handles the SPA routing
        // We ONLY focus.
        await target.focus();
        return { found: true, url: target.url };
    }

    return { found: false };
}
```

### Why FOCUS and NAVIGATE are separate

- **FOCUS** = bring tab to front → Service Worker (requires user activation chain)
- **NAVIGATE** = change what the tab shows → BroadcastChannel (data message, SPA routing)

They execute in parallel. Both in the same click handler. Neither depends on the other.
If focus fails (SW not ready, browser restriction), navigation still works (tab routes in background).
If navigation fails (BC not connected), focus still works (tab comes to front showing whatever it had).

---

## BroadcastChannel — The Mesh Bus

### Channel: `devops-tab-mesh`

All tabs connect to this channel on load. It handles everything except focus/open.

### Lifecycle

```
Tab loads:
  1. const bc = new BroadcastChannel('devops-tab-mesh')
  2. bc.onmessage = handleMeshMessage
  3. Post JOIN
  4. Others respond with ROSTER
  5. Start heartbeat interval (PING every 5s)
  6. Listen for hashchange/popstate → post STATE

Tab unloads:
  1. beforeunload → post LEAVE (best-effort)
  2. bc.close()
  3. Clear heartbeat interval

Tab killed:
  1. Receive KILL message
  2. Stop heartbeat
  3. Post LEAVE
  4. bc.close()
  5. Render blocking overlay
  6. Tab is dead
```

---

## Message Protocol

### Channel: `devops-tab-mesh`

All messages carry `{ type, id, ts }` where:
- `type` = message type string
- `id` = sender's tabId (UUID)
- `ts` = Date.now() timestamp

```
── PRESENCE ──────────────────────────────────────────────

JOIN
  { type: 'join', id, tabType, siteName, url, hash, title, ts }
  Sent: on page load after generating tabId
  Effect: all other tabs respond with ROSTER
  Purpose: announce existence and trigger registry exchange

ROSTER
  { type: 'roster', id, tabType, siteName, url, hash, title, ts }
  Sent: in response to someone else's JOIN
  Effect: joining tab populates its registry with this tab's info
  Purpose: new tab learns about existing tabs

PING
  { type: 'ping', id, hash, title, ts }
  Sent: every 5 seconds by all tabs
  Effect: all tabs update lastSeen for this id in their registry
  Purpose: heartbeat. Tabs not seen for 15s are pruned.

LEAVE
  { type: 'leave', id, ts }
  Sent: on beforeunload (best-effort, not guaranteed to arrive)
  Effect: other tabs immediately move this entry to tombstones
  Purpose: fast death notification

STATE
  { type: 'state', id, hash, title, ts }
  Sent: on hashchange, popstate, pushState, page navigation
  Effect: all tabs update this tab's hash/title in their registry
  Purpose: real-time route tracking for debug panel

── NAVIGATION ────────────────────────────────────────────

NAVIGATE
  { type: 'navigate', id, targetId, hash, ts }
  Sent: by any tab that wants to direct another tab
  targetId: specific tab UUID (from registry lookup)
  hash: the hash route to navigate to (e.g. '#content/docs/vault.py@preview')
  Effect: target tab sets location.hash → SPA routing triggers
  Receiver actions:
    1. if targetId !== myId → ignore
    2. location.hash = msg.hash
    3. Start title flash (attention indicator)
    4. Post STATE with new hash/title

── CONTROL ───────────────────────────────────────────────

KILL
  { type: 'kill', id, targetId, reason, ts }
  Sent: from debug panel "Kill" button
  targetId: specific tab UUID
  reason: human-readable string
  Effect: target tab terminates its session
  Receiver actions:
    1. if targetId !== myId → ignore
    2. Stop heartbeat
    3. Post LEAVE
    4. Close BroadcastChannel
    5. Unregister event listeners
    6. Render full-viewport blocking overlay
    7. Only "Refresh" button in overlay works → location.reload()

INSPECT
  { type: 'inspect', id, targetId, ts }
  Sent: from debug panel "Inspect" button
  Effect: target tab responds with DUMP

DUMP
  { type: 'dump', id, respondingTo, state, ts }
  Sent: in response to INSPECT
  respondingTo: the inspector's tabId
  state: {
    registry: { ...full registry map },
    tabType, siteName, url, hash, title,
    uptime: seconds since page load,
    swReady: boolean,
    bcReady: boolean,
    capabilities: { ...detected browser capabilities }
  }
```

---

## Tab Identity Model

```javascript
const TAB_IDENTITY = {
    id:         crypto.randomUUID(),     // unique per tab instance
    tabType:    detectTabType(),          // 'admin' | 'site'
    siteName:   detectSiteName(),        // 'code-docs' | null (for admin)
    url:        location.href,           // full URL at registration time
    hash:       location.hash,           // current hash/route
    title:      computeBreadcrumb(),     // human-readable breadcrumb
    ts:         Date.now(),              // last update
    alive:      true                     // false after kill
};
```

### Tab type detection

```javascript
function detectTabType() {
    // /pages/site/... → site tab
    if (location.pathname.startsWith('/pages/site/')) return 'site';
    // Everything else on localhost:8000 → admin
    return 'admin';
}

function detectSiteName() {
    // /pages/site/code-docs/... → 'code-docs'
    const m = location.pathname.match(/^\/pages\/site\/([^/]+)/);
    return m ? m[1] : null;
}
```

### Registry entry (stored per tab in a Map)

```javascript
// Map<tabId, RegistryEntry>
{
    id: 'abc-123',
    tabType: 'admin',
    siteName: null,
    url: 'http://localhost:8000/',
    hash: '#content/docs/vault.py@preview',
    title: 'Admin › Content › vault.py (preview)',
    lastSeen: 1741276800000,   // Date.now() of last ping
    alive: true
}
```

### Registry maintenance

- **Populate**: from ROSTER responses after JOIN
- **Update**: from PING (lastSeen) and STATE (hash, title)
- **Prune**: tabs not seen for 15 seconds → `alive = false`
- **Tombstones**: dead tabs kept for 60 seconds for debug visibility, then removed
- **Leave**: immediate → move to tombstones with reason "closed"

---

## Title Engine

### Breadcrumb computation

```
INPUT: location.pathname + location.hash
OUTPUT: human-readable breadcrumb string

Admin panel:
  hash: #dashboard                          → "Admin › Dashboard"
  hash: #content                            → "Admin › Content"
  hash: #content/docs/src/core/vault.py@preview → "Admin › Content › vault.py (preview)"
  hash: #content/docs/services              → "Admin › Content › services"
  hash: #debugging/traces                   → "Admin › Debugging › Traces"
  hash: #audit                              → "Admin › Audit"
  hash: (empty)                             → "Admin › Dashboard"

Docusaurus site:
  path: /pages/site/code-docs/              → "code-docs"
  path: /pages/site/code-docs/core/services → "code-docs › core › services"
  path: /pages/site/code-docs/core/services/vault → "code-docs › services › vault"
```

### Title flash (attention indicator)

When a tab receives a NAVIGATE message, it starts flashing its title:

```
Interval: 800ms toggle
  Frame A: "⚡ Navigate here"
  Frame B: computed breadcrumb (e.g. "Admin › Content › vault.py")

Stop conditions:
  1. visibilitychange → tab gains focus (document.hidden === false)
  2. 10 second timeout → auto-stop
  3. Another NAVIGATE arrives → restart with new target

On stop:
  1. Clear interval
  2. Restore document.title to computed breadcrumb
```

### Title sync on navigation

Every time the tab's route changes (hashchange, popstate, page navigation):
1. Recompute breadcrumb
2. Set `document.title` (unless title-flash is active)
3. Post STATE message with new hash + title

---

## Navigation Flow

### Scenario 1: Docusaurus → Admin (target exists in registry)

```
User clicks "Open in Vault" on Docusaurus page (Tab B):

  CLICK HANDLER (synchronous, user gesture context):
  ├─1─ Registry lookup: find admin tab (Tab A) by tabType === 'admin'
  │    If multiple admin tabs: pick most recent lastSeen
  │    Result: targetId = Tab A's id
  │
  ├─2─ BroadcastChannel: post NAVIGATE { targetId: A.id, hash: '#content/docs/vault.py@preview' }
  │    → Tab A receives → sets location.hash → switchTab() fires → SPA navigates
  │    → Tab A starts title flash
  │    → Tab A posts STATE with new hash
  │
  └─3─ Service Worker: postMessage { type: 'FOCUS_TAB', urlPattern: '/' }
       → SW calls clients.matchAll()
       → SW finds Tab A (pathname === '/')
       → SW calls Tab A.focus() → TAB A COMES TO FRONT
       → Returns { found: true }

  User sees:
    - Tab A (admin) comes to front
    - Content Vault shows vault.py in preview mode
    - Title: "Admin › Content › vault.py (preview)"
    - No new tabs opened
    - Original Docusaurus tab stays in background, unchanged
```

### Scenario 2: Docusaurus → Admin (admin not open)

```
User clicks "Open in Vault" on Docusaurus page (Tab B):

  CLICK HANDLER:
  ├─1─ Registry lookup: no admin tab found
  │
  ├─2─ BroadcastChannel: post NAVIGATE anyway (no one receives, that's fine)
  │
  └─3─ Service Worker: postMessage { type: 'FOCUS_TAB', urlPattern: '/' }
       → SW calls clients.matchAll()
       → No tab with pathname === '/' found
       → SW calls clients.openWindow('http://localhost:8000/#content/docs/vault.py@preview')
       → New tab opens with admin at the right hash
       → Returns { found: false, opened: true }

  User sees:
    - New admin tab opens, navigated to Content > vault.py preview
    - Admin tab joins mesh on load → registry updated
    - Next clicks use Scenario 1 flow
```

### Scenario 3: Admin → Docusaurus site

```
User clicks "View on Site" in admin Content Vault:

  CLICK HANDLER:
  ├─1─ Registry lookup: find site tab by tabType === 'site', siteName === 'code-docs'
  │    If multiple: pick one showing closest path
  │
  ├─2─ BroadcastChannel: post NAVIGATE { targetId: site.id, hash: sitePageUrl }
  │    → Site tab: for Docusaurus, hash-based SPA routing may not apply
  │    → Site tab: uses window.location.href for Docusaurus file-based routing
  │
  └─3─ Service Worker: postMessage { type: 'FOCUS_TAB', urlPattern: '/pages/site/code-docs' }
       → SW finds site tab → focuses it

  Note: Docusaurus uses file-based routing, not hash routing.
  The NAVIGATE handler on site tabs must use location.href = url
  instead of location.hash = hash for non-hash URLs.
```

### Scenario 4: SW not available → graceful fallback

```
User clicks "Open in Vault" but SW failed to register:

  CLICK HANDLER:
  ├─1─ Check: is SW ready?
  │    → NO (registration failed, old browser, etc.)
  │
  ├─2─ BroadcastChannel: post NAVIGATE (still works if BC is available)
  │    → Admin tab receives, SPA navigates (in background)
  │    → Admin tab starts title flash
  │
  └─3─ Fallback: window.open(fullUrl, '_blank')
       → Opens admin in new tab (may create duplicate if admin is already open)
       → User sees flashing admin tab title + new tab

  This is the worst case but still functional.
```

---

## Session Control (Kill)

### Kill flow

```
Debug panel: user clicks [⛔ Kill] on a tab entry:

  1. Confirm dialog: "Kill session for 'code-docs › core › services'?"
  2. On confirm:
     a. BroadcastChannel: post KILL { targetId, reason: 'Manual kill from debug panel' }
     b. Update local registry: mark target as dead

  Target tab receives KILL:
  1. Stop heartbeat interval
  2. Post LEAVE { id }
  3. Close BroadcastChannel (bc.close())
  4. Remove all mesh event listeners
  5. Render blocking overlay (full viewport):

     ┌──────────────────────────────────────────────────────┐
     │                                                      │
     │                  ⛔ Session Terminated                │
     │                                                      │
     │     This tab was closed remotely from the             │
     │     admin debug panel.                                │
     │                                                      │
     │     Reason: Manual kill from debug panel              │
     │     Time: 2026-03-06 13:15:22                        │
     │                                                      │
     │              [🔄 Refresh to Reload]                   │
     │                                                      │
     └──────────────────────────────────────────────────────┘

     Overlay properties:
     - position: fixed; top: 0; left: 0; width: 100vw; height: 100vh
     - z-index: 999999
     - pointer-events: all (blocks ALL interaction below)
     - background: semi-transparent dark with glassmorphism blur
     - Only the Refresh button has pointer-events and calls location.reload()

  6. Tab is effectively dead. Nothing works except refresh.
  7. On refresh → page loads fresh → rejoins mesh normally
```

---

## Debug Panel

### Location in admin UI

- Debugging tab → new mode button: `📡 Mesh`
- Alongside existing: 📋 Audit Log | 📦 State | ❤️ Health | ⚙️ Config | ⚡ Commands | 📝 Traces | **📡 Mesh**

### Panel layout

```
┌────────────────────────────────────────────────────────────────┐
│ 📡 Tab Mesh                                            [⟳ 2s] │
│ My ID: abc-123 (admin) · SW: ✅ Ready · BC: ✅ Connected       │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ALIVE (3)                                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 🟢 🏠 Admin                                      2s ago │  │
│  │    Route: #content/docs/src/core/services/vault.py@prev  │  │
│  │    Title: Admin › Content › vault.py (preview)            │  │
│  │    [📍 Navigate] [⛔ Kill] [🔍 Inspect]                   │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │ 🟢 📄 code-docs                                  3s ago │  │
│  │    Route: /pages/site/code-docs/core/services/            │  │
│  │    Title: code-docs › core › services                     │  │
│  │    [📍 Navigate] [⛔ Kill] [🔍 Inspect]                   │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │ 🟢 📄 code-docs                                  5s ago │  │
│  │    Route: /pages/site/code-docs/cli/audit/                │  │
│  │    Title: code-docs › cli › audit                         │  │
│  │    [📍 Navigate] [⛔ Kill] [🔍 Inspect]                   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  TOMBSTONES (1)                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ ☠️ 📄 code-docs — closed 30s ago (user closed tab)       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  INSPECT RESULTS                                               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ { tabType: 'site', uptime: 342, swReady: true, ... }    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│ SW Clients (raw):                                              │
│ [Refresh SW Clients] — calls LIST_TABS on SW for verification  │
└────────────────────────────────────────────────────────────────┘
```

### Debug panel actions

| Action | What it does |
|---|---|
| **Navigate** | Prompts for hash. Posts NAVIGATE to target. Also focuses via SW. |
| **Kill** | Confirm dialog. Posts KILL. Target shows blocking overlay. |
| **Inspect** | Posts INSPECT. Target responds with DUMP. Panel shows JSON. |
| **Refresh SW Clients** | Calls SW LIST_TABS. Shows raw client list for cross-reference with BC registry. |

### Auto-refresh

The debug panel re-renders the tab list every 2 seconds from the in-memory registry.
Pruning runs on every render: tabs with lastSeen > 15s ago → marked dead → moved to tombstones.
Tombstones older than 60s → removed entirely.

---

## Browser Capability Detection & Fallbacks

### Capability detection on load

```javascript
const MESH_CAPABILITIES = {
    broadcastChannel: typeof BroadcastChannel !== 'undefined',
    serviceWorker:    'serviceWorker' in navigator,
    cryptoUUID:       typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function',
    visibilityAPI:    typeof document.hidden !== 'undefined',
};

// Fallback for randomUUID
function generateTabId() {
    if (MESH_CAPABILITIES.cryptoUUID) return crypto.randomUUID();
    // Fallback: simple random ID
    return 'tab-' + Math.random().toString(36).substring(2, 10) +
           '-' + Date.now().toString(36);
}
```

### Degradation tiers

```
TIER 1 — Full mesh (BC ✅ + SW ✅)
  Everything works as designed.
  Focus, navigate, presence, kill, debug panel.

TIER 2 — Mesh without focus (BC ✅ + SW ❌)
  BroadcastChannel presence and navigation work.
  Tab routes in background (SPA) but cannot be focused.
  Title flash is the only attention indicator.
  Fallback: window.open(url, '_blank') for "open new tab" actions.
  Debug panel works (shows registry from BC).
  Kill works (BC message → blocking overlay).

TIER 3 — Basic fallback (BC ❌ + SW ❌)
  No inter-tab communication at all.
  All navigation falls back to window.open(url, '_blank').
  No presence, no registry, no debug panel.
  Equivalent to a normal website opening links.

TIER 4 — SW only, no BC (BC ❌ + SW ✅)
  Unlikely scenario. SW can focus/open tabs.
  No presence or state sync. Just focus.
  Treated as TIER 3 for simplicity + SW focus where possible.
```

### SW readiness states

```
SW_STATE = 'unavailable' | 'registering' | 'installing' | 'waiting' | 'active' | 'error'

  unavailable:  browser doesn't support SW → TIER 2/3 immediately
  registering:  register() called, waiting for response
  installing:   SW installing, not yet active
  waiting:      SW installed but not controlling pages yet
  active:       SW is active and controlling → FULL CAPABILITY
  error:        registration or activation failed → TIER 2/3

On every focusTab() call:
  if SW_STATE !== 'active' → skip SW focus, rely on title flash
```

### Recovery protocol

```
If SW registration fails:
  1. Log warning: "Service Worker registration failed: {error}"
  2. Set SW_STATE = 'error'
  3. Continue with TIER 2 (BC-only)
  4. Debug panel shows: "SW: ❌ {error message}"
  5. No retry (SW failures are usually persistent until fix)

If BC construction fails:
  1. Log warning: "BroadcastChannel not available"
  2. Set BC to null
  3. Continue with TIER 3 or 4
  4. No presence, no registry, no navigate, no kill
  5. All link actions fallback to window.open()

If SW was active but becomes redundant (page is closed):
  1. SW stays alive (browser manages lifecycle)
  2. Next page load re-registers, SW is already active
  3. Immediate TIER 1
```

### Debug panel capability display

```
Header line:
  My ID: abc-123 (admin) · SW: ✅ Ready · BC: ✅ Connected
  My ID: abc-123 (admin) · SW: ❌ Not supported · BC: ✅ Connected
  My ID: abc-123 (admin) · SW: ⚠️ Installing... · BC: ✅ Connected
  My ID: abc-123 (admin) · SW: ❌ Error: SecurityError · BC: ❌ Not supported
```

---

## File Layout

```
src/ui/web/static/sw.js                                ← Service Worker
src/ui/web/templates/scripts/_tab_mesh.html             ← Core mesh module (admin side)
src/core/services/pages_builders/templates/
    docusaurus/theme/hooks/useTabMesh.ts                ← Docusaurus mesh hook
```

### Modified files

```
src/ui/web/routes/pages/serving.py                      ← Added /sw.js route
src/ui/web/templates/dashboard.html                     ← Include _tab_mesh.html script
src/ui/web/templates/partials/_tab_debugging.html        ← Added "📡 Mesh" mode button + panel HTML
src/ui/web/templates/scripts/_debugging.html             ← Added loadDebugMesh() + mesh mode wiring
src/ui/web/templates/scripts/_tabs.html                 ← Removed broken BC hack
src/core/services/pages_builders/templates/
    docusaurus/theme/Root.tsx.tmpl                       ← Import + call useTabMesh()
src/core/services/pages_builders/templates/
    docusaurus/theme/hooks/usePeekLinks.ts              ← Replaced window.open with _openInAdmin()
```

### Files cleaned up (Phase 0)

```
src/ui/web/templates/scripts/_tabs.html
  → Removed: window.name = 'devops-admin'
  → Removed: BroadcastChannel listener block at bottom

src/core/services/pages_builders/templates/
    docusaurus/theme/hooks/usePeekLinks.ts
  → Removed: _navigateAdmin() function
  → All 13 call sites: rewired to _openInAdmin() → TabMesh.navigateTo() in Phase 4
```

---

## Implementation Phases

| Phase | Name | Scope | Dependencies |
|---|---|---|---|
| **0** | **Cleanup** ✅ | Revert broken hack. Clean slate. | None |
| **1** | **Service Worker** ✅ | `sw.js` + Flask route + registration on admin + Docusaurus | Phase 0 |
| **2** | **Mesh core** ✅ | BroadcastChannel presence, registry, breadcrumbs | Phase 0 |
| **3** | **Navigation** ✅ | Navigate messages + SW focus + title flash | Phase 1 + 2 |
| **4** | **Consumer wiring** ✅ | usePeekLinks → mesh, audit links → mesh | Phase 3 |
| **5** | **Session control** ✅ | Kill messages + blocking overlay | Phase 2 |
| **6** | **Debug panel** ✅ | UI + live tab list + actions | Phase 2 + 5 |
| **7** | **Polish** | CSS, keyboard shortcuts, edge cases | Phase 6 |

---

## Phase Details

### Phase 0 — Cleanup

Revert the broken BroadcastChannel hack from `_tabs.html` and `usePeekLinks.ts`:

1. Remove `window.name = 'devops-admin'` from `_tabs.html`
2. Remove the BroadcastChannel listener block from `_tabs.html`
3. Remove `_navigateAdmin()` function from `usePeekLinks.ts`
4. Restore all 13 call sites to `window.open(\`${ADMIN_URL}/...\`, '_blank')` temporarily
5. Remove audit-link-dev click interceptor from `usePeekLinks.ts`

**Verify**: admin panel loads without errors. Peek links open in new tabs (old behavior).

### Phase 1 — Service Worker

1. Create `src/ui/web/static/sw.js`:
   - `install` handler with `skipWaiting()`
   - `activate` handler with `clients.claim()`
   - `message` handler for `FOCUS_TAB`, `OPEN_TAB`, `LIST_TABS`
   - `FOCUS_TAB`: `clients.matchAll()` → find by URL pattern → `client.focus()`
   - `OPEN_TAB`: `clients.openWindow(url)`
   - `LIST_TABS`: return array of `{ url, focused, visibilityState }`

2. Add Flask route in `server.py`:
   ```python
   @app.route('/sw.js')
   def service_worker():
       return send_from_directory(app.static_folder, 'sw.js',
                                  mimetype='application/javascript')
   ```

3. Add SW registration to admin (`_tab_mesh.html`):
   - Capability detection
   - `navigator.serviceWorker.register('/sw.js', { scope: '/' })`
   - Track SW_STATE

4. Add SW registration to Docusaurus (`useTabMesh.ts`):
   - Same capability detection
   - Same registration

**Verify**: Open admin → check DevTools → Application → Service Workers → sw.js active.
Open Docusaurus page → same check. SW controls both pages.

### Phase 2 — Mesh core (BroadcastChannel presence)

1. Create `_tab_mesh.html` (admin side):
   - Tab identity generation (detectTabType, detectSiteName, generateTabId)
   - BroadcastChannel `devops-tab-mesh` connection
   - Message handlers: JOIN, ROSTER, PING, LEAVE, STATE
   - Registry Map with pruning
   - Heartbeat interval (5s)
   - hashchange/popstate listeners → STATE broadcast
   - Breadcrumb computation
   - Expose global `TabMesh` object:
     ```javascript
     window.TabMesh = {
         id: TAB_IDENTITY.id,
         registry: _registry,
         navigateTo: function(targetType, hash) { ... },
         capabilities: MESH_CAPABILITIES,
         swState: SW_STATE
     };
     ```

2. Create `useTabMesh.ts` (Docusaurus side):
   - Same protocol implementation
   - React hook lifecycle (useEffect cleanup: leave + close)
   - Expose on window for usePeekLinks to call

3. Include `_tab_mesh.html` in `dashboard.html` before other scripts

4. Import `useTabMesh` in `Root.tsx.tmpl`

**Verify**: Open admin + 2 Docusaurus tabs. Check console: JOIN/ROSTER messages.
Close one tab: LEAVE appears in others. Wait 15s without ping: pruned.

### Phase 3 — Navigation

1. Implement `TabMesh.navigateTo(targetType, hash)`:
   - Registry lookup by targetType ('admin' or 'site:segment')
   - Post NAVIGATE message via BC
   - Post FOCUS_TAB message via SW
   - Fallback chain:
     ```
     if target in registry AND sw active → BC navigate + SW focus (TIER 1)
     if target in registry AND sw NOT active → BC navigate + title flash (TIER 2)
     if target NOT in registry AND sw active → SW openWindow(url) (TIER 1)
     if target NOT in registry AND sw NOT active → window.open(url, '_blank') (TIER 3)
     ```

2. Implement NAVIGATE handler on receiving tab:
   - Admin: `location.hash = msg.hash` → switchTab fires → SPA navigation
   - Site: `location.href = url` (Docusaurus file-based routing)

3. Implement title flash:
   - Start: setInterval 800ms toggle between "⚡ Navigate here" and breadcrumb
   - Stop on: visibilitychange (tab visible), 10s timeout, new NAVIGATE
   - Restore document.title on stop

**Verify**: Open admin + Docusaurus. From Docusaurus console:
`TabMesh.navigateTo('admin', '#content/docs/vault.py@preview')`
→ Admin tab comes to front, shows vault.py preview.

### Phase 4 — Consumer wiring

1. In `usePeekLinks.ts`, replace all 13 `window.open(ADMIN_URL/...)` with:
   ```typescript
   window.TabMesh?.navigateTo('admin', `#content/docs/${ref.resolved_path}@preview`);
   ```
   With fallback:
   ```typescript
   if (window.TabMesh) {
       window.TabMesh.navigateTo('admin', hash);
   } else {
       window.open(`${ADMIN_URL}/${hash}`, '_blank');
   }
   ```

2. Add audit-link-dev click interceptor (same as before but using TabMesh)

**Verify**: Click a peek link on Docusaurus → admin navigates + focuses.

### Phase 5 — Session control

1. Implement KILL handler:
   - Stop heartbeat, post LEAVE, close BC
   - Render blocking overlay (inline CSS for z-index: 999999)
   - Refresh button → `location.reload()`

2. Implement `TabMesh.kill(targetId, reason)`:
   - Confirm dialog
   - Post KILL via BC

**Verify**: Open 3 tabs. From admin debug panel, kill a Docusaurus tab.
→ Killed tab shows blocking overlay. Only refresh works.

### Phase 6 — Debug panel

1. Add "📡 Mesh" mode button in `_tab_debugging.html`

2. Create `_tab_mesh_debug.html`:
   - Render tab list from `TabMesh.registry`
   - Auto-refresh every 2s
   - Navigate action: input hash, call `TabMesh.navigateTo()`
   - Kill action: confirm → `TabMesh.kill()`
   - Inspect action: post INSPECT → render DUMP response
   - Tombstones section
   - SW Clients cross-reference (call SW LIST_TABS)
   - Capability status line

3. Include `_tab_mesh_debug.html` in `dashboard.html`

4. Wire `debugSwitchMode('mesh')` to show the panel

**Verify**: Open debug panel → see all tabs. Click Navigate → target tab changes route.
Click Kill → target shows overlay. Click Inspect → see state dump.

### Phase 7 — Polish

1. Kill overlay CSS: glassmorphism, premium dark theme, centered card
2. Debug panel CSS: consistent with existing debug modes
3. Title flash: optional favicon flash (red dot indicator)
4. Admin "View on Site" → `TabMesh.navigateTo('site:code-docs', siteUrl)`
5. Dev/Live mode sync across Docusaurus tabs (BC state message)
6. Keyboard shortcut: `Ctrl+Shift+M` → switch to debug Mesh panel
7. Edge cases:
   - Multiple admin tabs → debug panel shows all, navigate picks most recent
   - Tab opened in incognito → SW scope is separate, no mesh
   - Very rapid navigation → debounce STATE broadcasts

---

## Handshake Sequence Diagram

```
TIME    TAB A (admin)                  TAB B (docusaurus)
────    ─────────────                  ──────────────────

t=0     Page loads
        Generate id=A
        Register SW (/sw.js)
        Open BC 'devops-tab-mesh'
        Post JOIN{A, admin, ...}
        Start heartbeat (5s)
        No ROSTER responses (alone)

t=5     PING{A}
t=10    PING{A}

t=12                                   Page loads
                                       Generate id=B
                                       Register SW (already active)
                                       Open BC 'devops-tab-mesh'
                                       Post JOIN{B, site, code-docs}

t=12    Receive JOIN{B}
        Add B to registry
        Post ROSTER{A, admin}

t=12                                   Receive ROSTER{A}
                                       Add A to registry
                                       Start heartbeat (5s)

t=15    PING{A}                        
t=17                                   PING{B}
t=20    PING{A}
t=22                                   PING{B}

        ... both tabs now know each other ...

t=30                                   User clicks "Open in Vault"
                                       CLICK HANDLER:
                                         Registry: admin = Tab A
                                         BC: NAVIGATE{targetId=A, hash='#content/...'}
                                         SW: postMessage{FOCUS_TAB, urlPattern='/'}

t=30    Receive NAVIGATE{targetId=A}
        location.hash = '#content/...'
        switchTab fires → SPA navigates
        Start title flash
        Post STATE{A, newHash, newTitle}

t=30    SW receives FOCUS_TAB
        clients.matchAll() → finds Tab A
        Tab A.focus() → TAB A COMES TO FRONT

t=30    visibilitychange fires (tab is now visible)
        Stop title flash
        User sees Content Vault → vault.py preview
```

---

## Summary

This is a **real system**, not a hack. Two separate mechanisms for two separate problems:

1. **BroadcastChannel** = the data bus (presence, navigation data, state sync, kill commands)
2. **Service Worker** = the focus engine (bring tabs to front, open new tabs)

Neither depends on the other. Both have independent fallback chains. The debug panel
provides full observability. Browser capability detection ensures graceful degradation
from TIER 1 (full mesh) down to TIER 3 (basic window.open fallback).
