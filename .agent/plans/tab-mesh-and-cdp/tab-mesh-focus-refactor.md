# Tab Mesh Focus Refactor Plan

> **Created**: 2026-03-06 19:38
> **Updated**: 2026-03-06 20:27
> **Status**: IMPLEMENTED — All 6 steps complete, awaiting live testing
> **Context**: 5 different browser-side focus approaches tested and all failed.
>              Chrome DevTools Protocol is the correct path.
>              CDP client, Flask routes, frontend integration, SW cleanup,
>              panel wizard, and navigateTo update — all done.

---

## Part 1: What We Proved (Test Results — All Failed)

### Tests performed

All tests used the Mesh panel's diagnostic buttons on two open admin tabs.
Page-side activation was confirmed alive at every checkpoint.

| Test | Mechanism | Result |
|---|---|---|
| **A** | `reg.active.postMessage()` (minimal, no transfer) | ❌ `event.userActivation = null` in SW |
| **B** | `window.open(url, 'devops-admin')` from source tab | ❌ Opens new tab (different browsing context group) |
| **C** | BC navigate → target calls `window.focus()` on itself | ❌ Target has no activation, silently ignored |
| **D** | `controller.postMessage()` fully sync, no async | ❌ Same as A — `userActivation = null` in SW |
| **E** | Notification → user clicks → SW `notificationclick` → `client.focus()` | Requires extra click, not seamless UX |
| **🔗** | `controller.postMessage(msg, { transfer, includeUserActivation: true })` | ❌ `includeUserActivation` had zero effect |

### Root cause

Chrome's `ServiceWorkerGlobalScope` has an internal `is_window_interaction_allowed` flag.
This flag is ONLY set for specific event types:
- ✅ `notificationclick`
- ✅ `paymentrequest`  
- ✅ `push` (for openWindow only)
- ❌ `message` — NEVER sets this flag

No amount of tight-chaining, option-setting, or syntax changes can make `client.focus()` work
from a `message` event handler. Chrome simply does not implement this path.

### Conclusion

**Browser page-level JS cannot focus another tab.** This is by design.
Focus control is **tooling-level**, not application-level. Chrome explicitly
provides this control through the **DevTools Protocol** Target domain.

---

## Part 2: The Correct Architecture — Chrome DevTools Protocol

### Mental model

```
Two worlds:
┌─────────────────────────────────────┐  ┌─────────────────────────────────┐
│  INSIDE THE BROWSER (restricted)    │  │  OUTSIDE THE BROWSER (powerful) │
│                                     │  │                                 │
│  Page JS, Service Workers           │  │  Flask backend on WSL           │
│  Subject to focus-stealing rules    │  │  Talks to Chrome CDP            │
│  Can: navigate, SPA route, flash    │  │  Can: activate tabs, list tabs  │
│  Cannot: focus another tab          │  │  Has tooling-level control      │
└─────────────────────────────────────┘  └─────────────────────────────────┘
```

### Flow

```
User clicks "Focus tab" in admin page
  → POST /api/tab-mesh/focus { targetUrl: "http://localhost:8000/#content" }
  → Flask backend receives request
  → Flask calls Chrome CDP: GET http://<chrome-host>:9222/json
  → Finds target tab by URL matching
  → Flask sends Target.activateTarget via CDP WebSocket
  → Chrome brings the target tab to the foreground ✅
  → Flask returns { success: true, tabId: "..." }
  → Page shows confirmation
```

### Why this works

- Chrome's DevTools Protocol is DESIGNED for tooling-level control
- `Target.activateTarget` brings any tab to the foreground — no restrictions
- The Flask backend runs on WSL, Chrome runs on Windows
- WSL can reach Windows Chrome's debugging port
- No browser-side focus hacks needed

---

## Part 3: Environment — WSL ↔ Windows Chrome Interop

### Existing infrastructure we leverage

The audit system (`l0_hw_detectors.py → _detect_wsl_interop()`) already detects:
```python
{
    "available": True,           # powershell.exe is reachable
    "binfmt_registered": True,   # WSL can run .exe files
    "windows_user": "Jean",      # Windows username
    "wslconfig_path": "/mnt/c/Users/Jean/.wslconfig"
}
```

This gives us: Windows username, PowerShell availability, and WSL interop status.

### Chrome locations on Windows

```
Chrome executable:
  C:\Program Files\Google\Chrome\Application\chrome.exe

User's active shortcut (taskbar pin):
  C:\Users\{user}\AppData\Roaming\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\Google Chrome.lnk

Other possible shortcuts:
  C:\Users\{user}\Desktop\Google Chrome.lnk
  C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Google Chrome.lnk
  C:\Users\{user}\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Google Chrome.lnk
```

### Chrome data dir scenarios

| Scenario | `--user-data-dir` | `--remote-debugging-port` | Works? |
|---|---|---|---|
| Default Chrome (no flags) | implicit default | not set | ❌ Need to add both |
| User has custom profile | already set | not set | ✅ Just add port flag |
| Chrome 136+ default profile | not set | adding it | ❌ Port flag ignored without dir |
| Chrome 136+ with `--user-data-dir` | set | adding it | ✅ Works |

**Key insight**: The user may already have `--user-data-dir` in their shortcut.
We read the shortcut FIRST, check what's there, and only add what's missing.

### Default user data dir (for users without custom one)

```
Windows default: %LOCALAPPDATA%\Google\Chrome\User Data
Resolved:        C:\Users\Jean\AppData\Local\Google\Chrome\User Data
```

If adding `--user-data-dir`, we point to the user's EXISTING default profile —
not a new empty profile. This preserves all their bookmarks, extensions, passwords.

### Remediation flow — fully dynamic, wizard feel

**Nothing is hardcoded.** Every value is detected at runtime.

#### Detection layer (backend)

```python
# 1. Windows username — from _detect_wsl_interop() cache
windows_user = audit_cache["wsl_interop"]["windows_user"]   # e.g. "Jean"

# 2. Chrome user data dir — derived from username
chrome_data_dir = f"/mnt/c/Users/{windows_user}/AppData/Local/Google/Chrome/User Data"
# Windows path: C:\Users\{windows_user}\AppData\Local\Google\Chrome\User Data

# 3. Chrome profiles — read Local State file (JSON)
local_state_path = f"{chrome_data_dir}/Local State"
# Parse: profile.info_cache → list of { dir: "Profile 1", name: "Work", email: "..." }
# Profiles: Default, Profile 1, Profile 2, etc.

# 4. All Chrome shortcuts — check every known location
shortcuts = {
    "taskbar": f"/mnt/c/Users/{windows_user}/AppData/Roaming/Microsoft/Internet Explorer/Quick Launch/User Pinned/TaskBar/Google Chrome.lnk",
    "desktop": f"/mnt/c/Users/{windows_user}/Desktop/Google Chrome.lnk",
    "start_menu_global": "/mnt/c/ProgramData/Microsoft/Windows/Start Menu/Programs/Google Chrome.lnk",
    "start_menu_user": f"/mnt/c/Users/{windows_user}/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Google Chrome.lnk",
}
# Check which ones EXIST via os.path.exists()

# 5. Current shortcut args — read via PowerShell COM
# For each found shortcut, read TargetPath and Arguments
# Parse: does it already have --remote-debugging-port? --user-data-dir?

# 6. Chrome version — from the exe
# powershell.exe -Command '& "C:\Program Files\Google\Chrome\Application\chrome.exe" --version'
# → "Google Chrome 138.0.6423.82" → check if >= 136
```

#### Profile selection (when multiple Chrome profiles exist)

```
GET /api/tab-mesh/cdp-diagnose returns:
{
    "windows_user": "Jean",
    "chrome_data_dir": "C:\\Users\\Jean\\AppData\\Local\\Google\\Chrome\\User Data",
    "chrome_version": "138.0.6423.82",
    "requires_user_data_dir": true,     // Chrome >= 136
    "profiles": [
        { "dir": "Default", "name": "Personal", "email": "jean@gmail.com" },
        { "dir": "Profile 1", "name": "Work", "email": "jean@company.com" },
    ],
    "shortcuts": {
        "taskbar": { "found": true, "target": "C:\\...\\chrome.exe", "args": "" },
        "desktop": { "found": true, "target": "C:\\...\\chrome.exe", "args": "" },
        "start_menu_global": { "found": true, "target": "C:\\...\\chrome.exe", "args": "" },
        "start_menu_user": { "found": false }
    },
    "cdp_active": false
}
```

#### Wizard UI — step by step, assistant feel

The remediation appears in the mesh panel as a guided flow, following
the assistant content principles (conversational, state-aware, guiding):

**Step 1: Detection** (automatic, no user input)

```
┌─ 📡 Tab Focus Setup ─────────────────────────────────────┐
│                                                           │
│ Tab focus lets you click a link in one tab and have the   │
│ other tab jump to the front — no manual switching.        │
│                                                           │
│ It works through Chrome's debugging interface, which      │
│ needs a small one-time setup.                             │
│                                                           │
│ Here's what I found on your system:                       │
│                                                           │
│ ✅ WSL interop is working                                  │
│ ✅ Windows user: Jean                                      │
│ ✅ Chrome found at: C:\Program Files\...\chrome.exe       │
│ ❌ Remote debugging is not active                          │
│                                                           │
│ Let me help you set it up.                                │
│                                                           │
│                                        [Continue →]       │
└───────────────────────────────────────────────────────────┘
```

**Step 2: Profile selection** (only if multiple profiles)

```
┌─ 📡 Which Chrome profile do you use? ─────────────────────┐
│                                                            │
│ Chrome stores your bookmarks, extensions, and history in   │
│ a "profile." I found these on your system:                 │
│                                                            │
│ ◉ Personal (jean@gmail.com)     ← Default                 │
│ ○ Work (jean@company.com)       ← Profile 1               │
│                                                            │
│ Pick the one you use for this admin panel.                 │
│ We'll point the shortcut to this profile so everything     │
│ stays exactly the same — bookmarks, passwords, all of it.  │
│                                                            │
│                              [← Back]  [Continue →]        │
└────────────────────────────────────────────────────────────┘
```

If only one profile → skip this step.

**Step 3: Shortcut review** (show what we'll change)

```
┌─ 📡 Here's what I'll change ──────────────────────────────┐
│                                                            │
│ I found 3 Chrome shortcuts. I'll add the debugging flag    │
│ to all of them so it works however you open Chrome.        │
│                                                            │
│ ☑ Taskbar pin         (currently: no flags)                │
│ ☑ Desktop shortcut    (currently: no flags)                │
│ ☑ Start Menu          (currently: no flags)                │
│                                                            │
│ What I'll add to each:                                     │
│   --remote-debugging-port=9222                             │
│   --user-data-dir="C:\Users\Jean\AppData\...\User Data"   │
│                                                            │
│ Nothing else changes. Same Chrome, same profile,           │
│ same everything — just with debugging enabled.             │
│                                                            │
│                              [← Back]  [Apply All →]       │
└────────────────────────────────────────────────────────────┘
```

**Step 4: Apply + verify**

```
┌─ 📡 Almost done! ─────────────────────────────────────────┐
│                                                            │
│ ✅ Taskbar shortcut updated                                 │
│ ✅ Desktop shortcut updated                                 │
│ ✅ Start Menu shortcut updated                              │
│                                                            │
│ One last step:                                             │
│                                                            │
│   1. Close Chrome completely                               │
│      (check your system tray — Chrome may still be         │
│       running in the background)                           │
│                                                            │
│   2. Reopen Chrome from any of your shortcuts              │
│                                                            │
│   3. Navigate back here and click Verify                   │
│                                                            │
│                                         [Verify ↻]        │
└────────────────────────────────────────────────────────────┘
```

After verify:
```
│ ✅ Chrome debugging is active!                              │
│                                                            │
│ Tab focus is now working. When you click a cross-tab       │
│ link, the target tab will come to the front automatically. │
│                                                            │
│                                           [Done ✓]        │
└────────────────────────────────────────────────────────────┘
```

Or if verify fails:
```
│ ❌ Chrome debugging is still not responding.                │
│                                                            │
│ This usually means Chrome is still running from before     │
│ the update. Try:                                           │
│                                                            │
│   • Check system tray (bottom-right ▲) for Chrome icon    │
│   • Right-click → Exit                                     │
│   • Then reopen Chrome from your shortcut                  │
│                                                            │
│                            [Retry ↻]  [Manual Steps]       │
└────────────────────────────────────────────────────────────┘
```

### Multiple paths for different situations

| Path | When | Action |
|---|---|---|
| **Auto-remediate taskbar shortcut** | WSL interop available, shortcut found | Modify .lnk via PowerShell |
| **Auto-remediate desktop shortcut** | Taskbar shortcut not found, desktop exists | Same via desktop .lnk |
| **Manual instructions** | PowerShell not available or user prefers | Show copy-paste instructions |
| **Already configured** | CDP endpoint responds | No action needed |
| **Linux native (not WSL)** | No WSL detected | Different instructions (launch Chrome with flags) |

### Manual fallback instructions

For users who prefer manual setup, or if PowerShell can't modify shortcuts:

The UI dynamically generates instructions using the detected `windows_user` and
`chrome_data_dir`. Example (values filled from detection):

```
1. Right-click each Chrome shortcut → Properties
   (Taskbar, Desktop, Start Menu — whichever you use)
2. In the "Target" field, add at the end:
     --remote-debugging-port=9222
3. Also add (required for Chrome 136+):
     --user-data-dir="{detected_chrome_data_dir}"
4. Click OK for each shortcut
5. Close Chrome completely (check system tray!)
6. Reopen Chrome from any modified shortcut
```

The paths are never hardcoded — they come from the `/api/tab-mesh/cdp-diagnose` response.

### WSL → Windows Chrome connectivity

WSL2 can reach Windows localhost via:
- `localhost:9222` — works with WSL2 mirrored networking mode
- Windows host IP — fallback if mirrored networking is off
- The Flask app tries both and stores the working endpoint

### Detection flow at app startup

```
1. Check if WSL (from audit cache or /proc/version)
2. If not WSL → skip CDP (or offer native Linux instructions)
3. If WSL → get windows_user from _detect_wsl_interop() cache
4. Try GET http://localhost:9222/json/version (timeout: 500ms)
5. If reachable → store CDP endpoint, set _meshCDPAvailable = true
6. If not → try http://$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}'):9222
7. If still not → CDP unavailable, show setup/remediation in mesh panel
```

---

## Part 4: Implementation Steps

### Step 1: CDP client in Flask backend

**File**: `src/ui/web/cdp_client.py` (new)

Minimal CDP client:
- `get_targets()` → `GET http://<host>:9222/json` → list of open tabs
- `activate_target(target_id)` → `GET http://<host>:9222/json/activate/{id}`
- `is_available()` → check if CDP endpoint responds
- `find_target_by_url(url_pattern)` → match a tab by URL

Uses `httpx` (already a dependency) — no WebSocket needed for `activateTarget`.

Chrome CDP has a REST-like JSON API:
```
GET /json/version          → Chrome version info
GET /json                  → list all open tabs (targets)
GET /json/activate/{id}    → bring tab to foreground
GET /json/close/{id}       → close a tab
GET /json/new?{url}        → open a new tab
```

No WebSocket needed for basic target activation!

### Step 2: Flask API routes

**Dir**: `src/ui/web/routes/tab_mesh/` (new, follows existing route pattern)

Routes:
```python
# GET /api/tab-mesh/cdp-status
# Returns: { available, chrome_version, endpoint, shortcuts_found }

# POST /api/tab-mesh/focus
# Body: { urlPattern: "/" }  
# Returns: { success, url, targetId }

# GET /api/tab-mesh/cdp-diagnose
# Reads Chrome shortcut via PowerShell, returns current args
# Returns: { shortcut_found, target_path, current_args, has_debug_port, has_user_data_dir }

# POST /api/tab-mesh/cdp-remediate
# Modifies shortcut to add --remote-debugging-port=9222
# Body: { shortcut: "taskbar" | "desktop" | "start_menu" }
# Returns: { success, applied_args, requires_restart: true }
```

### Step 3: Frontend integration

**File**: `_tab_mesh.html` — update `navigateTo`

```javascript
// Instead of SW focus, call the backend
async function _meshFocusViaCDP(urlPattern) {
    try {
        var resp = await fetch('/api/tab-mesh/focus', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ urlPattern: urlPattern }),
        });
        var data = await resp.json();
        if (data.success) {
            console.log('[MESH] CDP focus succeeded:', data.url);
        } else if (data.reason === 'cdp_unavailable') {
            console.log('[MESH] CDP not available, falling back to title flash');
        }
        return data;
    } catch (err) {
        console.log('[MESH] CDP focus error:', err.message);
        return { success: false, reason: 'error' };
    }
}
```

### Step 4: CDP status + remediation UI in mesh panel

Show in the panel header:
```
📡 Tab Mesh
My ID: abc-123 (admin) · SW: ✅ · BC: ✅ · CDP: ✅ (or ❌)
```

If CDP is ❌ and WSL is detected, show the remediation panel:
```
┌─ Tab Focus Setup ────────────────────────────────────────┐
│                                                          │
│ Chrome remote debugging is not active.                   │
│                                                          │
│ Detected:                                                │
│   Windows user: Jean                                     │
│   Taskbar shortcut: ✅ found                              │
│   Current args: (none)                                   │
│                                                          │
│ To enable tab focus, we need to add:                     │
│   --remote-debugging-port=9222                           │
│   --user-data-dir="C:\Users\Jean\AppData\Local\..."     │
│                                                          │
│ Your profile, bookmarks, and extensions stay the same.   │
│                                                          │
│ [Apply to Shortcut]  [Manual Instructions]  [Diagnose]   │
│                                                          │
│ After applying: Close Chrome → Reopen → [Verify] ← here │
└──────────────────────────────────────────────────────────┘
```

The **[Verify]** button calls `GET /api/tab-mesh/cdp-status` and shows ✅ or ❌.

### Step 5: Update navigateTo flow

```
navigateTo(targetType, hash):
  1. BC navigate → target tab SPA-routes (always works)
  2. CDP focus → Flask backend → Chrome activates target tab
  3. If CDP unavailable → title flash (existing fallback)
```

### Step 6: Detect CDP on app startup

On admin page load, call `GET /api/tab-mesh/cdp-status` once.
Store `_meshCDPAvailable` flag. Use it to decide whether to show
Focus buttons or setup instructions.

---

## Part 5: What We Keep / Remove

| Component | Status | Reason |
|---|---|---|
| **BC navigate** | ✅ Keep | SPA routing — always works |
| **BC presence (join/ping/leave)** | ✅ Keep | Tab registry, awareness |
| **Title flash** | ✅ Keep | Fallback when CDP unavailable |
| **SW registration** | ✅ Keep | LIST_TABS for debug verification |
| **SW FOCUS_TAB handler** | 🗑️ Remove | Proven non-functional |
| **SW FOCUS_TAB in navigateTo** | 🗑️ Remove | Dead code |
| **includeUserActivation** | 🗑️ Remove | Has zero effect |
| **Diagnostic test buttons (A-E)** | 🗑️ Remove | Served their purpose |
| **Diagnostic #mesh-diag area** | 🗑️ Remove | Served its purpose |
| **CDP focus via Flask** | ✨ New | The actual focus mechanism |
| **CDP availability check** | ✨ New | Detection + setup instructions |

---

## Part 6: Files Affected

| File | Change |
|---|---|
| `src/ui/web/cdp_client.py` | **NEW** — CDP client (get_targets, activate_target, is_available) |
| `src/ui/web/routes/tab_mesh/__init__.py` | **NEW** — Blueprint: focus, cdp-status, diagnose, remediate |
| `src/ui/web/server.py` | Register `tab_mesh_bp` blueprint |
| `src/ui/web/static/sw.js` | Remove FOCUS_TAB handler, keep LIST_TABS |
| `src/ui/web/templates/scripts/_tab_mesh.html` | Remove SW focus from navigateTo, add CDP fetch |
| `src/ui/web/templates/scripts/_tab_mesh_panel.html` | Remove diagnostics, add CDP status + remediation UI |

---

## Part 7: Security Considerations

- CDP is only reachable from localhost — no external exposure
- The Flask backend validates URL patterns before passing to CDP
- CDP `activateTarget` only activates, does not inject code or read page content
- Shortcut modification via PowerShell only adds Chrome flags — no code execution
- If the user hasn't enabled remote debugging, the feature simply doesn't work
  (graceful degradation to title flash)
- The remediation requires explicit user action ("Apply" button) — never automatic
- User sees exactly what will change before applying
