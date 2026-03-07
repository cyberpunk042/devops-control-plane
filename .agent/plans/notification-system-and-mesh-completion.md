# Notification & Error Log System + Tab Mesh Completion Plan

> Created: 2026-03-06
> Revised: 2026-03-07 — expanded to include error log, multi-tab panel, 
>   differentiated badges, error interception
> Status: DRAFT — awaiting user approval before any implementation

---

## Vision

A **slide-out panel** (like the Stage Debugger) with **two internal tabs**:

1. **🔔 Notifications** — server-persisted notifications (CDP suggestions,
   session events, chat messages, vault locks, etc.)
2. **⚠️ Error Log** — intercepted frontend + backend errors that would
   otherwise be silently swallowed

Both surfaced via a **single navbar icon** with a **smart badge** that
differentiates notification count from error pulses.

### Badge Behavior

```
┌──────────────────────────────────────────────┐
│  Navbar:  [other controls]  🔔(3)  [gear]   │
│                                              │
│  Badge states:                               │
│  • "3"     = 3 unread notifications          │
│  • "3" 🔴  = 3 notifs + new error (pulse)    │
│  • 🔴      = no notifs but has new error     │
│  • (none)  = nothing to show                 │
│                                              │
│  The notification count is a number.         │
│  The error indicator is a separate pulsing   │
│  dot that appears briefly when a new error   │
│  arrives. It clears when the user opens the  │
│  panel and switches to the Error Log tab.    │
│  The error count shows inside the Error Log  │
│  tab header itself, not on the navbar badge. │
└──────────────────────────────────────────────┘
```

### Panel Layout (when open)

```
┌─────────────────────────────────────────────┐
│  🔔 Notifications & Errors         [✕]     │
├─────────────────────────────────────────────┤
│  [🔔 Notifications]  [⚠️ Errors (12)]      │  ← tab bar
├─────────────────────────────────────────────┤
│                                             │
│  (notification items or error log entries)  │
│  (lazy-loaded, paginated)                   │
│                                             │
└─────────────────────────────────────────────┘
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Server (Python/Flask)                                      │
│                                                             │
│  notifications.py                                           │
│    ├─ .state/notifications.json  (persistent)               │
│    └─ CRUD + dedup + event_bus.publish()                    │
│                                                             │
│  error_log.py                                               │
│    ├─ .state/error_log.ndjson    (append-only, rotated)     │
│    └─ log_error() + event_bus.publish()                     │
│                                                             │
│  routes/notifications/                                      │
│    ├─ GET  /api/notifications                               │
│    ├─ POST /api/notifications/dismiss                       │
│    ├─ DELETE /api/notifications/:id                         │
│    ├─ GET  /api/errors  (?page=N&per_page=20)               │
│    └─ POST /api/errors/ack                                  │
│                                                             │
│  Error interception:                                        │
│    ├─ Flask @app.errorhandler(500) → log_error()            │
│    ├─ Flask after_request → if 5xx → log_error()            │
│    └─ Explicit log_error() in except blocks                 │
│                                                             │
│  SSE events published:                                      │
│    notification:new        → new notification created        │
│    notification:dismissed  → notification dismissed          │
│    notification:deleted    → notification deleted            │
│    error:new               → new error logged               │
│                                                             │
│         ▼  (via GET /api/events SSE stream)                 │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│  Browser (Admin Panel)                                      │
│                                                             │
│  _notifications.html (NEW script include)                   │
│    ├─ Boot: fetch GET /api/notifications → sessionStorage   │
│    ├─ SSE: listen notification:new/dismissed/deleted         │
│    │       listen error:new                                 │
│    ├─ Frontend error interception:                          │
│    │   ├─ window.onerror → capture + POST /api/errors       │
│    │   ├─ window.onunhandledrejection → capture + POST      │
│    │   └─ api() catch → unhandled errors → POST /api/errors │
│    ├─ Badge: notification count + error pulse dot            │
│    └─ Panel: slide-out with two tabs                        │
│                                                             │
│  Cross-tab: BC 'notif:sync' message on devops-tab-mesh      │
│    → other tabs refetch from server on next panel open       │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Notification Server Store

### Goal
Server-side notification CRUD with `.state/` persistence and event bus
integration.

### Files

**CREATE: `src/core/services/notifications.py`**

#### Data Model

```python
# Each notification:
{
    "id": "notif-<uuid4-short>",      # unique ID (8 chars)
    "type": "cdp_suggestion",          # category (for dedup + filtering)
    "title": "Enable CDP",             # short title for the panel
    "message": "Enable Chrome DevTools...",  # full message body
    "created_at": 1741312000.0,        # epoch seconds
    "dismissed": false,                # user dismissed but not deleted
    "meta": {                          # type-specific data (optional)
        "platform": "wsl2",
        "action_url": "#debugging"     # optional: link to relevant UI
    }
}
```

#### .state/notifications.json structure

```json
{
    "notifications": [ ... ],
    "version": 1
}
```

#### Public API

```python
_NOTIF_FILE = ".state/notifications.json"

def load_notifications(project_root: Path) -> list[dict]:
    """Load all notifications from disk. Returns [] if file missing."""

def save_notifications(project_root: Path, notifications: list[dict]) -> None:
    """Write notifications list to disk. Creates .state/ if needed."""

def create_notification(
    project_root: Path,
    *,
    notif_type: str,
    title: str,
    message: str,
    meta: dict | None = None,
    dedup: bool = True,
) -> dict | None:
    """Create a notification. If dedup=True, skips if an active (non-dismissed)
    notification of the same type already exists. Returns the notification
    dict if created, None if deduped.
    
    Also publishes 'notification:new' to the event bus when created."""

def dismiss_notification(project_root: Path, notif_id: str) -> bool:
    """Mark a notification as dismissed. Returns True if found.
    Publishes 'notification:dismissed'."""

def delete_notification(project_root: Path, notif_id: str) -> bool:
    """Permanently remove a notification. Returns True if found.
    Publishes 'notification:deleted'."""

def get_active_notifications(project_root: Path) -> list[dict]:
    """Return only non-dismissed notifications, newest first."""

def get_all_notifications(project_root: Path) -> list[dict]:
    """Return all notifications (including dismissed), newest first."""
```

#### Event bus integration (inside `create_notification`)

```python
from src.core.services.event_bus import bus

bus.publish("notification:new", key=notif["id"], data=notif)
```

### Conventions followed
- Same pattern as `server_settings.py` (JSON file, load/save, defaults)
- Same `.state/` directory convention
- Same event_bus publish pattern as `audit_staging.py`

### Test criteria
- `create_notification` → `.state/notifications.json` exists with correct data
- `create_notification` twice same type + dedup=True → second returns None
- `dismiss_notification` → `dismissed=True` in file
- `delete_notification` → removed from file
- `get_active_notifications` excludes dismissed
- Event bus receives `notification:new` on create

---

## Phase 2: Error Log Server Store

### Goal
Server-side error logging with append-only NDJSON storage, rotation, and
paginated retrieval.

### Files

**CREATE: `src/core/services/error_log.py`**

#### Data Model

```python
# Each error entry (one line in NDJSON):
{
    "id": "err-<uuid4-short>",
    "source": "backend",             # "backend" | "frontend"
    "level": "error",                # "error" | "warning"  
    "message": "KeyError: 'vault'",  # human-readable summary
    "detail": "Traceback...",        # full traceback or stack trace
    "endpoint": "/api/vault/unlock", # request path (if applicable)
    "ts": 1741312000.0,             # epoch seconds
    "acked": false,                  # user acknowledged (seen)
}
```

#### .state/error_log.ndjson

Append-only NDJSON file. One JSON object per line.

#### Public API

```python
_ERROR_LOG_FILE = ".state/error_log.ndjson"
_MAX_ERRORS = 1000  # rotation: when exceeded, keep newest 800

def log_error(
    project_root: Path,
    *,
    source: str,          # "backend" | "frontend"
    message: str,
    detail: str = "",
    endpoint: str = "",
    level: str = "error",
) -> dict:
    """Append an error to the log. Returns the error dict.
    Publishes 'error:new' to event bus.
    Rotates if file exceeds _MAX_ERRORS."""

def get_errors(
    project_root: Path,
    *,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    """Return paginated errors, newest first.
    Returns: { errors: [...], total: N, page: N, pages: N }"""

def ack_errors(project_root: Path) -> int:
    """Mark all errors as acknowledged (acked=True).
    Returns count of errors acked."""

def get_unacked_count(project_root: Path) -> int:
    """Return count of unacknowledged errors (for badge)."""
```

#### Rotation logic

When `log_error` detects the file exceeds `_MAX_ERRORS` lines:
1. Read all lines
2. Keep the newest 800
3. Rewrite the file
4. This is a simple, infrequent operation

#### Why NDJSON (not JSON array)?

- Append-only writes (no read-modify-write for each error)
- Safe against corruption from concurrent writes
- Efficient tail reads for the most recent errors
- Same pattern as `.state/runs.jsonl`

### Test criteria
- `log_error()` appends to `.state/error_log.ndjson`
- `get_errors(page=1, per_page=5)` returns correct pagination
- `ack_errors()` marks all as acked
- Rotation: after 1001 errors, file contains 800
- Event bus receives `error:new` on log

---

## Phase 3: Notification & Error API Routes

### Goal
REST API for frontend to read, dismiss, delete notifications and view errors.

### Files

**CREATE: `src/ui/web/routes/notifications/__init__.py`**

#### Routes

```python
notifications_bp = Blueprint("notifications", __name__)

# ── Notifications ─────────────────────────────────────────

@notifications_bp.route("/notifications")
def list_notifications():
    """GET /api/notifications
    Query params: all (bool) — include dismissed. Default: active only.
    Returns: { notifications: [...], unread_count: N }"""

@notifications_bp.route("/notifications/dismiss", methods=["POST"])
def dismiss():
    """POST /api/notifications/dismiss
    Body: { "id": "notif-xxx" }
    Returns: { "success": true }"""

@notifications_bp.route("/notifications/<notif_id>", methods=["DELETE"])
def delete(notif_id):
    """DELETE /api/notifications/<id>
    Returns: { "success": true }"""

# ── Error Log ─────────────────────────────────────────────

@notifications_bp.route("/errors")
def list_errors():
    """GET /api/errors
    Query params: page (int), per_page (int, default 20)
    Returns: { errors: [...], total: N, page: N, pages: N,
               unacked_count: N }"""

@notifications_bp.route("/errors", methods=["POST"])
def log_frontend_error():
    """POST /api/errors
    Body: { "message": "...", "detail": "...", "endpoint": "..." }
    Used by frontend error interceptors to report client-side errors.
    Returns: { "success": true, "id": "err-xxx" }"""

@notifications_bp.route("/errors/ack", methods=["POST"])
def ack():
    """POST /api/errors/ack
    Mark all errors as acknowledged (user opened Error Log tab).
    Returns: { "success": true, "acked": N }"""
```

**MODIFY: `src/ui/web/server.py`**
- Register `notifications_bp` with `url_prefix="/api"`

**MODIFY: `src/ui/web/templates/scripts/_event_stream.html`**
- Add `'notification:new'`, `'notification:dismissed'`, `'notification:deleted'`,
  `'error:new'` to `_sse._eventTypes` array (line ~80-91)
- Add handlers in `_dispatch()` switch (line ~135-158)
- The handlers will call functions defined in `_notifications.html`
  (loaded before `_event_stream.html`... actually check order)

Wait — check include order in `dashboard.html`:
```
Line 43: {% include 'scripts/_event_stream.html' %}
Line 58: {% include 'scripts/_tab_mesh.html' %}
```

`_event_stream.html` loads BEFORE `_tab_mesh.html`. Our new
`_notifications.html` needs to load AFTER `_event_stream.html` (to hook
into SSE) but also needs its functions to exist when the SSE handlers fire.

**Solution**: The SSE handlers in `_event_stream.html` should dispatch
DOM CustomEvents (like `audit-scan-progress`). The `_notifications.html`
script listens for these events. This decouples load order.

Actually, looking more carefully: the SSE `_dispatch()` function already
follows a pattern where unknown event types are silently ignored. So:

**Revised approach**: Add the event types to `_eventTypes` so the SSE
listener subscribes. In `_dispatch()`, fire `document.dispatchEvent()`
for notification/error events. `_notifications.html` (loaded later)
registers DOM event listeners that process these. Clean separation.

### Backend Error Interception

**MODIFY: `src/ui/web/server.py`** (or appropriate middleware location)

```python
@app.errorhandler(500)
def handle_500(error):
    """Log unhandled 500 errors to the error log."""
    from src.core.services.error_log import log_error
    log_error(
        project_root,
        source="backend",
        message=str(error),
        detail=traceback.format_exc(),
        endpoint=request.path,
    )
    return jsonify({"error": "Internal server error"}), 500
```

Also add an `after_request` hook that catches 5xx responses from routes
that handle their own errors but still return error status codes.

### Test criteria
- `curl GET /api/notifications` returns empty list initially
- `curl POST /api/errors` with body → error logged, SSE event fires
- `curl GET /api/errors?page=1&per_page=5` returns paginated results
- `curl POST /api/errors/ack` → all errors marked acked
- Backend 500 → error appears in GET /api/errors

---

## Phase 4: Navbar Icon + Slide-out Panel

### Goal
Add a 🔔 icon to the navbar that opens a slide-out panel (Stage Debugger
pattern) with two tabs: Notifications and Error Log.

### Files

**MODIFY: `src/ui/web/templates/partials/_nav.html`**

Add between the GH menu and the DEV badge (line ~41):

```html
<div class="notif-trigger" id="notif-trigger" onclick="_toggleNotifPanel()"
     title="Notifications & Errors">
    🔔
    <span class="notif-count-badge" id="notif-count-badge"
          style="display:none">0</span>
    <span class="notif-error-dot" id="notif-error-dot"
          style="display:none"></span>
</div>
```

Two badge elements:
- `.notif-count-badge` — notification count number
- `.notif-error-dot` — pulsing red dot for new errors

**MODIFY: `src/ui/web/static/css/admin.css`** (or relevant CSS file)

New styles:
```css
/* ── Notification trigger ──────────────────────────────── */
.notif-trigger { position: relative; cursor: pointer; ... }

.notif-count-badge {
    position: absolute; top: -4px; right: -6px;
    background: hsl(0, 75%, 55%); color: #fff;
    font-size: 0.55rem; font-weight: 700;
    min-width: 14px; height: 14px;
    border-radius: 7px; padding: 0 3px;
    display: flex; align-items: center; justify-content: center;
}

.notif-error-dot {
    position: absolute; bottom: -2px; right: -2px;
    width: 8px; height: 8px;
    background: hsl(0, 80%, 55%);
    border-radius: 50%;
    animation: notif-pulse 1.5s ease-in-out infinite;
}

@keyframes notif-pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.6; transform: scale(1.3); }
}

/* ── Notification panel (Stage Debugger pattern) ───────── */
.notif-panel {
    /* Same pattern as .debug-drawer */
    position: fixed; top: 0; right: 0;
    width: 380px; height: 100vh;
    background: var(--bg-surface); ...
    transform: translateX(100%);
    transition: transform 0.25s ease;
    z-index: 10001;
}
.notif-panel.open { transform: translateX(0); }

/* Tab bar, tab content, items — all same pattern as debug-drawer */
```

### Design language
- Same slide-out pattern as Stage Debugger (`.debug-drawer`)
- Same tab bar pattern (`.debug-tab-bar`, `.debug-tab`)
- Notification items: type icon, title, message preview, timestamp,
  dismiss/delete hover actions
- Error items: level icon (🔴/🟡), message, endpoint, timestamp,
  expandable detail (click to see full traceback)
- Empty state: muted text, appropriate icon

### Panel DOM (injected by `_notifications.html`)

```
┌─────────────────────────────────────────────┐
│  🔔 Notifications & Errors         [✕]     │  ← header
├─────────────────────────────────────────────┤
│  [🔔 Notifications]  [⚠️ Errors (12)]      │  ← tab bar
├─────────────────────────────────────────────┤
│                                             │
│  Notifications tab:                         │
│  ┌───────────────────────────────────────┐  │
│  │ 💡 Enable instant tab switching       │  │
│  │ Enable CDP for smoother experience    │  │
│  │ 2m ago                    [✓] [✕]     │  │
│  ├───────────────────────────────────────┤  │
│  │ 💬 New chat message                   │  │
│  │ @user replied to your thread          │  │
│  │ 5m ago                    [✓] [✕]     │  │
│  └───────────────────────────────────────┘  │
│  [Load more]  (lazy pagination)             │
│                                             │
│  Error Log tab:                             │
│  ┌───────────────────────────────────────┐  │
│  │ 🔴 KeyError: 'vault_key'             │  │
│  │ /api/vault/unlock  •  12s ago         │  │
│  │ ▸ Click to expand traceback           │  │
│  ├───────────────────────────────────────┤  │
│  │ 🟡 TypeError: Cannot read undefined   │  │
│  │ (frontend)  •  1m ago                 │  │
│  │ ▸ Click to expand stack trace         │  │
│  └───────────────────────────────────────┘  │
│  [Load more]  (lazy pagination)             │
│                                             │
└─────────────────────────────────────────────┘
```

### Test criteria
- 🔔 icon visible in navbar
- Click toggles panel open/close (slide animation)
- Click outside closes panel
- Two tabs switch correctly
- Empty states render

---

## Phase 5: Client-side Logic — Cache, SSE, Error Interception

### Goal
Frontend script that manages notifications, errors, badges, and
intercepts unhandled errors.

### Files

**CREATE: `src/ui/web/templates/scripts/_notifications.html`**

**MODIFY: `src/ui/web/templates/dashboard.html`**
- Add `{% include 'scripts/_notifications.html' %}` AFTER `_tab_mesh.html`
  and BEFORE `_boot.html` (important: after `_event_stream.html` so SSE
  is connected, before `_boot.html` so error interception is active early)

#### Architecture

```javascript
// ── State ──────────────────────────────────────────────────

var _notifPanelOpen = false;
var _notifActiveTab = 'notifications'; // 'notifications' | 'errors'
var _notifCache = [];                   // cached notifications
var _notifCacheFresh = false;           // has been fetched this session
var _errorNewCount = 0;                 // unacked error count
var _errorPulseTimer = null;            // pulse animation timer

// ── Notification Cache ─────────────────────────────────────

const _NOTIF_STORAGE_KEY = '_notif:cache';
const _NOTIF_TTL = 120_000;  // 2 min

function _notifGetCache() { /* sessionStorage read */ }
function _notifSetCache(data) { /* sessionStorage write */ }

// ── Boot ───────────────────────────────────────────────────

async function _notifBoot() {
    // 1. Try sessionStorage cache
    // 2. If stale or missing → fetch GET /api/notifications
    // 3. Also fetch GET /api/errors?page=1&per_page=1 for unacked count
    // 4. Update badge
    // 5. Register SSE listeners
}

// ── SSE Listeners ──────────────────────────────────────────

// Listen for CustomEvents dispatched by _event_stream.html:
document.addEventListener('sse:notification:new', (e) => {
    _notifHandleNew(e.detail);
});
document.addEventListener('sse:notification:dismissed', (e) => {
    _notifHandleDismissed(e.detail);
});
document.addEventListener('sse:notification:deleted', (e) => {
    _notifHandleDeleted(e.detail);
});
document.addEventListener('sse:error:new', (e) => {
    _notifHandleErrorNew(e.detail);
});

// ── Badge Management ───────────────────────────────────────

function _notifUpdateBadge() {
    // Count active notifications → show/hide count badge
    // Check _errorNewCount → show/hide error dot
}

function _notifPulseErrorDot() {
    // Show the pulsing red dot briefly
    // Clear after panel is opened to Error Log tab
}

// ── Panel Toggle ───────────────────────────────────────────

function _toggleNotifPanel() {
    _notifPanelOpen = !_notifPanelOpen;
    // Inject panel DOM if first open (same pattern as Stage Debugger)
    // Toggle .open class on panel
    // If opening: refresh from server if cache is stale
}

function _notifSwitchTab(tab) {
    _notifActiveTab = tab;
    // Toggle tab active states
    // If switching to 'errors': ack all errors, clear error dot
}

// ── Notification Rendering ─────────────────────────────────

function _notifRenderNotifications() {
    // Render notification items into the panel body
    // Lazy loading: show first 20, "Load more" button for next page
}

function _notifRenderErrors() {
    // Render error items into the panel body  
    // Lazy loading: show first 20, "Load more" button for next page
    // Each item expandable to show full detail/traceback
}

// ── Notification Actions ───────────────────────────────────

async function _notifDismiss(id) {
    // POST /api/notifications/dismiss → update cache → re-render
}

async function _notifDelete(id) {
    // DELETE /api/notifications/:id → update cache → re-render
}

// ── Error Interception ─────────────────────────────────────

// Frontend errors that are NOT caught by the api() function
window.onerror = function(msg, source, line, col, error) {
    _notifReportFrontendError({
        message: msg,
        detail: error ? error.stack : `${source}:${line}:${col}`,
        endpoint: location.hash || location.pathname,
    });
};

window.addEventListener('unhandledrejection', function(event) {
    _notifReportFrontendError({
        message: 'Unhandled Promise: ' + (event.reason?.message || String(event.reason)),
        detail: event.reason?.stack || '',
        endpoint: location.hash || location.pathname,
    });
});

function _notifReportFrontendError(errData) {
    // POST /api/errors { source: "frontend", ...errData }
    // Fire-and-forget (don't await, don't block)
    // Debounce: max 1 per second per unique message
}

// ── Cross-tab Sync ─────────────────────────────────────────

// After any mutation, broadcast on existing BC:
function _notifBroadcastSync() {
    if (typeof _meshBroadcast === 'function') {
        _meshBroadcast({ type: 'notif:sync', ts: Date.now() });
    }
}

// Listen for sync from other tabs:
// (hooked into _meshHandleMessage in _tab_mesh.html)
```

**MODIFY: `src/ui/web/templates/scripts/_event_stream.html`**

In `_eventTypes` array (~line 80-91), add:
```javascript
'notification:new', 'notification:dismissed', 'notification:deleted',
'error:new',
```

In `_dispatch()` switch (~line 135-158), add:
```javascript
case 'notification:new':
case 'notification:dismissed':
case 'notification:deleted':
case 'error:new':
    document.dispatchEvent(new CustomEvent('sse:' + type, { detail: payload }));
    break;
```

This cleanly bridges SSE events to DOM events without `_event_stream.html`
needing to know about `_notifications.html` functions.

### Test criteria
- Page load → badge shows correct notification count
- `window.onerror` firing → error captured, badge pulses
- SSE `notification:new` → badge count increments live
- SSE `error:new` → error dot pulses
- Open panel → notifications rendered
- Switch to Error Log tab → error dot clears
- Lazy loading: >20 items → "Load more" loads next page
- Cross-tab: create notification in tab A → badge updates in tab B

---

## Phase 6: CDP Fallback → Notification (First Consumer)

### Goal
When cross-tab focus falls back because CDP is unavailable, create a
one-time notification suggesting CDP setup.

### Files

**MODIFY: `src/ui/web/templates/scripts/_tab_mesh.html`**

In `_meshNavigateTo()`, after the CDP-unavailable path:

```javascript
// NEW: on first CDP-unavailable cross-tab action, suggest CDP
if (!_meshCDPAvailable && !_meshCDPNotifSent) {
    _meshCDPNotifSent = true;
    // Fire-and-forget — don't block navigation
    fetch('/api/tab-mesh/suggest-cdp', { method: 'POST' }).catch(() => {});
}
```

Add state variable near top:
```javascript
var _meshCDPNotifSent = false;
```

**MODIFY: `src/ui/web/routes/tab_mesh/__init__.py`**

New route:
```python
@tab_mesh_bp.route("/tab-mesh/suggest-cdp", methods=["POST"])
def suggest_cdp():
    """Create a one-time notification suggesting CDP setup."""
    from src.core.services.notifications import create_notification
    
    result = create_notification(
        project_root,
        notif_type="cdp_suggestion",
        title="Enable instant tab switching",
        message=(
            "Chrome DevTools Protocol (CDP) enables instant tab focus "
            "when switching between admin panel and Pages sites. "
            "Currently supported on Windows + WSL2. "
            "Set it up in the Debugging tab → Tab Mesh panel."
        ),
        meta={"action_url": "#debugging"},
        dedup=True,  # only one of these at a time
    )
    if result:
        return jsonify({"created": True})
    return jsonify({"created": False, "reason": "already_exists"})
```

### Test criteria
- First cross-tab nav without CDP → notification in 🔔 panel
- Second cross-tab nav → no duplicate
- Dismiss notification → stays dismissed (dedup checks active only)
- Delete notification → next CDP fallback creates a new one

---

## Phase 7: Pages Site Light Mesh Client

### Goal
Inject a lightweight BroadcastChannel client into Docusaurus pages so
they join the tab mesh registry (presence + navigate handler).

### Approach: Flask serve-time injection

When `serve_pages_site()` serves an `index.html`, inject a `<script>` tag
before `</body>`. The script is a minimal IIFE that joins the BC mesh.

### Files

**MODIFY: `src/ui/web/routes/pages/serving.py`**

When serving HTML files (specifically `index.html` — Docusaurus SPA root):
```python
def _inject_mesh_client(html_bytes: bytes, segment: str) -> bytes:
    """Inject light mesh client before </body>."""
    script = render_template("scripts/_tab_mesh_light.html", segment=segment)
    injection = script.encode("utf-8")
    return html_bytes.replace(b"</body>", injection + b"</body>")
```

Only inject into `index.html` (SPA root), not into every HTML file. All
Docusaurus routes load through the root `index.html` via SPA routing, so
one injection point covers all pages.

**CREATE: `src/ui/web/templates/scripts/_tab_mesh_light.html`**

Minimal mesh client (~80 lines, self-contained IIFE):
- Join BC mesh with `tabType: 'site'` and `siteName: segment`
- Heartbeat every 5s
- Handle `navigate` messages (Docusaurus client-side routing)
- Handle `kill` messages
- Title flash for attention
- Leave on `beforeunload`
- No CDP, no notifications, no error interception (admin-only features)
- Uses `var` for maximum compat (Docusaurus may target older browsers)

### Design notes
- Self-contained IIFE — no globals leak into Docusaurus
- Zero build-time changes (no Docusaurus plugin needed)
- `{{ segment }}` is Jinja-injected at serve time
- Only injected into `index.html`, not CSS/JS/image files

### Test criteria
- Open admin + Pages site in two tabs
- Admin mesh registry shows Pages site tab
- `TabMesh.navigateTo('site:code-docs', '/docs/intro')` → Pages tab navigates
- Close Pages tab → tombstone in admin registry
- Kill from debug panel → Pages tab shows termination message

---

## Phase 8: Pages Transition Animation

### Goal
Context-aware transition overlay when focusing tabs via CDP.

### Files

**MODIFY: `src/ui/web/templates/scripts/_tab_mesh.html`**

Modify `_meshFocusViaCDP()` to accept context parameter:

```javascript
async function _meshFocusViaCDP(urlPattern, context) {
    context = context || {};
    var isToSite = context.tabType === 'site';
    
    // Customize overlay based on target
    var overlayBg = isToSite
        ? 'radial-gradient(circle at center, rgba(37,194,160,0.08), rgba(0,0,0,0.7))'
        : 'radial-gradient(circle at center, rgba(255,255,255,0.03), rgba(0,0,0,0.7))';
    var overlayIcon = isToSite ? '📄' : '🎯';
    var overlayText = isToSite
        ? 'Opening ' + (context.siteName || 'docs') + ' site…'
        : 'Switching tab…';
    
    // ... rest of overlay creation using these variables
}
```

Update callers to pass context:
```javascript
_meshFocusViaCDP(urlMatch, { tabType: matchTabType, siteName: matchSiteName });
```

**MODIFY: `src/ui/web/templates/scripts/_tab_mesh_light.html`**

Add a subtle "incoming navigation" flash for Pages sites:
```javascript
// When receiving a navigate message, briefly flash the page
// with a green border glow to acknowledge the incoming navigation
```

### Test criteria
- Focus admin tab → neutral dark overlay (existing behavior preserved)
- Focus Pages site tab → green-accented overlay with "Opening docs site…"
- Overlay fades in/out smoothly

---

## Phase 9: Platform Coverage Documentation

### Goal
Document CDP platform support matrix.

### Files

**CREATE OR MODIFY**: Appropriate docs location (TBD — could be in
`docs/`, in a README, or in the Debugging tab's assistant content)

### Content

| Platform | CDP Status | Notes |
|----------|------------|-------|
| Windows + WSL2 | ✅ Tested | `curl.exe` bridge crosses WSL2→Windows network |
| Native Linux | 🟡 Untested | Chrome with `--remote-debugging-port=9222` |
| macOS | 🟡 Untested | Same as native Linux in principle |
| Windows native | 🟡 Untested | Direct HTTP (no bridge needed) |
| Remote/Docker Chrome | ❌ Not supported | CDP binds localhost only |

### Test criteria
- Documentation exists and is accurate

---

## Implementation Order & Dependencies

```
Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5 ──► Phase 6
  (notif      (error      (API        (navbar     (JS +       (CDP
   store)      store)      routes)     + panel)    SSE)        notif)
                                                      │
                                         Phase 7 ◄────┘
                                         (light mesh)
                                              │
                                         Phase 8
                                         (transitions)
                                              │
                                         Phase 9
                                         (docs)
```

Phases 1-5 are the core notification + error system (sequential).
Phase 6 is the first notification consumer (depends on 1-5).
Phase 7-8 are mesh completion (can start after Phase 6).
Phase 9 is documentation (any time).

---

## Key Design Decisions

### 1. Panel style: Slide-out drawer (not dropdown)
- Same pattern as Stage Debugger
- Room for expansion (more tabs, complex content)
- Doesn't fight with other dropdowns
- Consistent UX

### 2. No cap, lazy loading with pagination
- Server returns paginated results (`?page=N&per_page=20`)
- Panel shows first 20 items, "Load more" button fetches next page
- NDJSON for errors = efficient append + tail reads
- No max cap, rotation handles disk usage (keep newest 800/1000)

### 3. Silent (no sound, no browser Notification API)
- Non-invasive by design
- Badge + pulse dot provide visual attention without interruption

### 4. Error dot vs notification count: separate channels
- Notification count = persistent state (unread notifications exist)
- Error dot = transient signal (new error just arrived)
- Error dot clears when user opens Error Log tab (ack)
- Error count shows inside the tab header, not on navbar badge

### 5. BroadcastChannel reuse (single channel, type prefixed)
- Notifications use `{ type: 'notif:sync', ... }` on existing
  `devops-tab-mesh` channel
- Less infrastructure, same isolation via type filtering
- `_meshHandleMessage` already ignores unknown types

### 6. SSE → DOM CustomEvents for decoupling
- `_event_stream.html` doesn't know about `_notifications.html`
- Clean separation: SSE dispatches events, consumers listen
- Same pattern used for `audit-scan-progress`

### 7. Two-tier error interception
- **Frontend**: `window.onerror` + `unhandledrejection` → POST to server
- **Backend**: Flask `errorhandler(500)` + explicit `log_error()` calls
- Both end up in the same error log, both push SSE `error:new`

### 8. Pages injection: index.html only
- Docusaurus SPA loads everything through root `index.html`
- Injecting once covers all routes
- No performance impact on CSS/JS/image responses

---

## Pre-flight Checklist (Before Each Phase)

Per project rules:
```
□ Read the files I'm about to modify (view_file, not memory)
□ Read all callers/consumers of functions I'm changing
□ One change at a time — verify before moving to next
□ No scope drift — stick to the phase
□ State trace written before any code edit
□ Existing behavior preserved (no regressions)
```
