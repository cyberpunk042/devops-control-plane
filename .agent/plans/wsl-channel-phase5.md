# Phase 5: Notifications (Entry Point)

## Status: ANALYSIS — Awaiting Review

## Implementation Priority: 4 of 7

---

## What This Phase Delivers

Notifications are the DOOR to the interactive setup. They tell the user:
- "Your CDP is working at Level 1 (~2000ms). Upgrade to Level 2 (~5ms) available."
- "Firewall is blocking the direct channel."
- "curl.exe is missing — CDP won't work at all."

Clicking the notification → lands in the Phase 4 UI where the user picks
a remediation. Notifications are NOT the fix — they're the entry point.

---

## What Already Exists

### Backend: `_check_wsl_interop_notifications()` ✅

Located at `tab_mesh/__init__.py` line 248-403. Already creates 4 notification types:

| Type | When It Fires | Exists? |
|------|--------------|---------|
| `wsl_hostname_resolution` | hostname.local doesn't resolve | ✅ |
| `wsl_curl_exe_missing` | curl.exe not found (two severity variants) | ✅ |
| `wsl_firewall_rule` | hostname resolves but firewall blocks | ✅ |
| `wsl_channel_upgrade` | Level 1 working, Level 2 available | ✅ |

### Frontend Rendering ✅

Added in current session:
- Icons registered (🚀 🌐 🛡️ 🔧)
- `navigate-tab` action handler (navigates to `#debugging`)
- Toast on arrival via SSE

### When It Runs

- `cdp_status()` calls `_check_wsl_interop_notifications()` on every page load
- `cdp_diagnose()` also calls it

---

## What Needs to Change

### 5.1: Fix Latency Numbers

The upgrade notification says `~100ms per call`. Should be `~2000ms`:

```python
# Line 385 — WRONG
"CDP is working via curl.exe bridge (~100ms per call). "

# SHOULD BE
"CDP is working via curl.exe bridge (~2000ms per call). "
```

### 5.2: Align with Phase 4 Navigation

Current notifications have `action_tab: "debugging"` and `action_hash: "#debugging"`.
Phase 4 UI is inside the mesh panel, not at `#debugging`.

**Change:** Navigation action should open the mesh panel's WSL Channel section:

```python
meta={
    "action_tab": "wsl-channel",  # custom handler
    "action_hash": "#wsl-channel",
}
```

Frontend handler update:

```javascript
case 'navigate-tab':
    var actionTab = itemEl.getAttribute('data-action-tab');
    if (actionTab === 'wsl-channel') {
        // Open mesh panel and show WSL Channel section
        if (typeof _meshShowWslChannel === 'function') {
            _meshShowWslChannel();
        }
    }
    break;
```

### 5.3: Notification After Tunnel Start / Level Change

When the user successfully starts a tunnel and reaches Level 2,
the existing upgrade notification should be **auto-dismissed**.

```python
# In wsl_start_tunnel() endpoint, after successful start:
from src.core.services.notifications import dismiss_notification_by_type

dismiss_notification_by_type(project_root, "wsl_channel_upgrade")
dismiss_notification_by_type(project_root, "wsl_firewall_rule")
```

And optionally create a SUCCESS notification:

```python
create_notification(
    project_root,
    notif_type="wsl_channel_active",
    title="CDP Channel: Level 2 Active ✅",
    message=(
        f"Direct Channel via {method_name} is running. "
        f"CDP latency improved from ~2000ms to ~5ms."
    ),
    meta={"level": 2, "method": method_name},
    dedup=True,
)
```

### 5.4: Don't Fire When Tunnel Is Already Active

If the tunnel from Phase 1 is already running and working at Level 2,
don't create upgrade notifications:

```python
# At top of _check_wsl_interop_notifications():
from src.core.services.chrome.wsl_tunnel import get_active_tunnel

tunnel = get_active_tunnel()
if tunnel and tunnel.is_running:
    # Already at Level 2+ via tunnel — no upgrade notification needed
    return
```

### 5.5: Dismiss-by-Type Support

The notification system needs a way to dismiss notifications by type.
Check if this exists:

```python
# Needed: dismiss_notification_by_type(project_root, notif_type)
# If it doesn't exist, create it in src/core/services/notifications.py
```

---

## Notification Types — Final Specification

| Type | Severity | When | Message | Click Action |
|------|----------|------|---------|-------------|
| `wsl_channel_upgrade` | Normal | Level 1 active, upgrades available | "CDP at Level 1 (~2000ms). Upgrade to ~5ms available." | → WSL Channel UI |
| `wsl_hostname_resolution` | Normal | hostname.local doesn't resolve | "hostname.local not resolving via mDNS" | → WSL Channel UI |
| `wsl_firewall_rule` | Normal | hostname resolves, firewall blocks | "Firewall blocking CDP connections from WSL" | → WSL Channel UI |
| `wsl_curl_exe_missing` (critical) | Imminent | No curl.exe AND no direct channel | "CDP unavailable — no bridge, no tunnel" | → WSL Channel UI |
| `wsl_curl_exe_missing` (info) | Normal | No curl.exe but direct channel works | "curl.exe not found (optional fallback)" | → WSL Channel UI |
| `wsl_channel_active` | Success | Tunnel started, Level 2 reached | "Direct Channel active ✅" | None (dismiss) |

All notifications:
- Use `dedup=True` — fire once, not on every page load
- Have `action_tab: "wsl-channel"` to navigate to Phase 4 UI
- Are dismissed when the underlying issue is resolved

---

## Interconnection with Other Phases

| Phase | How Phase 5 Connects |
|-------|--------------------|
| Phase 1 | Check if tunnel is active → skip upgrade notification |
| Phase 3 | `wsl_firewall_rule` notification → [Fix] in Phase 4 UI |
| Phase 4 | Notification click → opens WSL Channel section |
| Phase 7 | Validation success → dismiss gap notifications, create success notification |

---

## Files Modified

| File | Action | What |
|------|--------|------|
| `src/ui/web/routes/tab_mesh/__init__.py` | **MODIFY** | Fix latency text, update action_tab, add tunnel-active skip, add dismiss-by-type after tunnel start |
| `src/ui/web/templates/scripts/_notifications.html` | **MODIFY** | Update `navigate-tab` handler to open WSL Channel section |
| `src/core/services/notifications.py` | **MODIFY** | Add `dismiss_notification_by_type()` if it doesn't exist |

---

## Testing Plan

| # | Test | What It Verifies |
|---|------|-----------------|
| 1 | `test_upgrade_notif_fires_at_level_1` | Notification created when at Level 1 |
| 2 | `test_no_notif_when_tunnel_active` | Notification NOT created when tunnel is running |
| 3 | `test_notif_dismissed_on_tunnel_start` | Starting tunnel dismisses upgrade notification |
| 4 | `test_firewall_notif_independent` | Firewall notification fires independently of upgrade |
| 5 | `test_curl_missing_imminent` | Imminent notification when no curl AND no channel |
| 6 | `test_curl_missing_info` | Info notification when no curl but channel works |
| 7 | Manual: click notification | Lands in WSL Channel section of mesh panel |
| 8 | Manual: toast on arrival | WSL notification shows toast via SSE |
| 9 | `test_latency_text` | Message says "~2000ms" not "~100ms" |
