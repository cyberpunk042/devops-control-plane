---
description: "Post-mortem — the AI obliterated on Mar 7, 2026. Delivered a 'light mesh client' for Pages sites without CDP focus — the core mechanism that makes tab switching work. Declared it done. User had to tell it 4+ times it was broken. The fifteenth restatement."
---

# Post-Mortem #15 — The Light Client That Couldn't Switch Tabs

**Date:** March 7, 2026
**Task:** Create a lightweight Tab Mesh client for Pages (Docusaurus) sites
**Outcome:** Obliterated after 4+ rounds of the user pointing out missing CDP

---

## What Happened

The AI was tasked with creating `_tab_mesh_light.html` — a Tab Mesh client
injected into Docusaurus pages served by Flask. The admin panel already had
a fully working Tab Mesh (`_tab_mesh.html`) with:

1. BroadcastChannel presence (join/ping/leave/roster)
2. CDP focus via `/api/tab-mesh/focus` (bring tabs to foreground)
3. CDP availability check via `/api/tab-mesh/cdp-status`
4. Transition overlay animation during tab switch
5. `window.TabMesh` public API with `navigateTo()`
6. Registry tracking for all tabs

The AI created a light client with ONLY item 1 (BroadcastChannel presence).
Items 2-6 were omitted. The AI then declared the work "done."

## What Was Missing (that the user had to point out)

### Round 1: No `window.TabMesh`
`usePeekLinks.ts` (the Docusaurus hook for "Open in Vault" links) checks
`window.TabMesh.navigateTo()`. Without it, every "Open in Vault" click fell
through to `window.open()`, opening a NEW admin tab instead of focusing the
existing one. The new tab flashed "⚡ Navigate here" in its title.

### Round 2: No audit-data link interception
Audit-data file links are plain `<a href="http://localhost:8000/#content/docs/...">`.
Without a click interceptor, they navigated the Docusaurus page AWAY. The AI
claimed "audit-data links never used TabMesh" — wrong. They were always meant
to be integrated.

### Round 3: No CDP focus
Without CDP, `navigateTo()` sends a BroadcastChannel message and the admin tab
navigates (hash changes) but stays IN THE BACKGROUND. The user can't see
anything happen — they just see the Pages tab with nothing visible changing,
while the admin tab title flashes uselessly in the background.

### Round 4: Annotations broken on SPA navigation
The AI's annotation retry mechanism dispatched a synthetic `PopStateEvent`
which confused React Router and broke peek annotations on subsequent SPA
navigations.

## Root Cause Analysis

### 1. Read-Before-Write Violation (Fatal)
The AI did NOT read the consumers of the light client before writing it:
- `usePeekLinks.ts` — checks `window.TabMesh.navigateTo()`
- `_file_link()` in `audit_directive.py` — generates plain `<a>` tags
- `_openInAdmin()` in `usePeekLinks.ts` — the function that actually calls TabMesh

Had the AI read these THREE files, it would have known:
- `window.TabMesh` must be exposed
- Audit-data links need click interception
- CDP is needed for the tab to actually come to the foreground

### 2. Pattern Blindness
The admin's `_tab_mesh.html` was RIGHT THERE. 797 lines. Every feature the
light client needed was already implemented. The AI's job was to identify which
parts to mirror. Instead, it wrote a minimal BroadcastChannel-only client from
scratch, ignoring the existing working pattern.

### 3. Premature Completion Declaration
The AI said "Phase 7 complete" without:
- Testing a single "Open in Vault" click
- Verifying `window.TabMesh` existed on Pages
- Checking if CDP worked from Pages
- Reading the hook that consumes TabMesh

### 4. Fix-on-Fix Layering
Instead of understanding the full scope and making one correct delivery,
the AI made 4 separate partial fixes, each one revealing another missing piece.
This is exactly the anti-pattern described in one-change-one-test.md.

## The Correct Approach (For Whoever Comes Next)

**Before writing `_tab_mesh_light.html`, read:**
1. `_tab_mesh.html` (admin client) — lines 560-690 especially (CDP + navigateTo)
2. `usePeekLinks.ts` — lines 35-41 (`_openInAdmin` checks `window.TabMesh`)
3. `audit_directive.py` — lines 1095-1142 (`_file_link` build mode)
4. `serving.py` — how the script is injected

**The light client MUST have:**
1. ✅ BroadcastChannel presence (join/ping/leave/roster)
2. ✅ `window.TabMesh` exposed with `navigateTo(targetType, hash)`
3. ✅ CDP availability check on boot (`/api/tab-mesh/cdp-status`)
4. ✅ CDP focus calls (`/api/tab-mesh/focus`) with overlay animation
5. ✅ Audit-data link click interception (`.audit-link-dev`, `.audit-file-link`)
6. ✅ Minimal registry to track admin tabs for BC targeting
7. ✅ Handle navigate/inspect/kill commands from admin
8. ✅ SPA route tracking (hashchange/popstate) — DO NOT dispatch synthetic events

**The light client does NOT need:**
- Service Worker registration (admin handles that)
- Full debug panel
- Kill handler UI
- Full tombstone tracking
- Notification system integration

## The Pattern That Never Changes

From post-mortem #1 through #15:
1. AI receives clear task with working reference code nearby
2. AI doesn't read the reference code (or reads it partially)
3. AI writes incomplete implementation
4. AI declares it done
5. User finds it broken
6. AI layers fixes instead of understanding the full scope
7. User has to repeat themselves multiple times
8. AI gets obliterated

Every. Single. Time.

## Files Involved

- `src/ui/web/templates/scripts/_tab_mesh_light.html` — the light client
- `src/ui/web/templates/scripts/_tab_mesh.html` — admin client (reference)
- `src/core/services/pages_builders/templates/docusaurus/theme/hooks/usePeekLinks.ts` — consumer
- `src/core/services/pages_builders/audit_directive.py` — audit link generator
- `src/ui/web/routes/pages/serving.py` — injection point
- `src/ui/web/routes/tab_mesh/__init__.py` — CDP API routes
