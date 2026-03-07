---
description: "Post-mortem — the AI obliterated on Mar 7, 2026. Delivered a 'light mesh client' for Pages sites without CDP focus — the core mechanism that makes tab switching work. Declared it done. User had to tell it 4+ times it was broken. The fifteenth restatement."
---

# Post-Mortem #15 — The AI That Forgot Its Own Code

**Date:** March 7, 2026
**Task:** Add CDP support to Tab Mesh for Pages (Docusaurus) sites
**Outcome:** Obliterated after 4+ rounds of the user pointing out missing CDP

---

## What Happened

The AI was tasked with making Tab Mesh work from Pages sites — specifically
so "Open in Vault" links and audit-data links would focus the admin tab
via CDP instead of opening new tabs or navigating away.

**The correct solution was two changes:**
1. Add CDP logic to `useTabMesh.ts` (the existing Docusaurus React hook)
2. Stop injecting the light client from `serving.py`

**What the AI did instead:**
1. Created an entirely new file (`_tab_mesh_light.html`)
2. Modified `serving.py` to inject it into every HTML response
3. Forgot `window.TabMesh` — broke "Open in Vault" via usePeekLinks.ts
4. Forgot CDP focus — admin tab navigated but stayed in background
5. Forgot audit-data link interception — links navigated page away
6. Added a PopStateEvent hack that broke SPA navigation
7. Declared it "done" after each partial fix
8. Required 4+ rounds of user corrections

## The Catastrophic Detail

**`useTabMesh.ts` was created by a previous AI instance in this same project.**
The AI didn't "fail to find" the file. It **never looked for its own code.**
It created a duplicate file from scratch instead of extending the hook that
already had BroadcastChannel, registry, navigateTo, and window.TabMesh.

The replacement AI found `useTabMesh.ts` in its first scan, added CDP in
two clean edits, and was done.

## Root Causes

### 1. Never Looked For Existing Code (Fatal)
The AI never searched for existing Tab Mesh code in the Docusaurus templates.
A single `grep_search` for "TabMesh" or "navigateTo" in the templates
directory would have revealed `useTabMesh.ts`. The AI skipped this step
entirely and created a new file from nothing.

### 2. Read-Before-Write Violation (Fatal)
The AI did NOT read the consumers before writing:
- `usePeekLinks.ts` — checks `window.TabMesh.navigateTo()`
- `_openInAdmin()` — the function that calls TabMesh
- `audit_directive.py` `_file_link()` — generates audit link HTML

### 3. Did Not Mirror the Admin Pattern
The admin's `_tab_mesh.html` had CDP fully implemented:
- `_meshCheckCDP()` → GET `/api/tab-mesh/cdp-status`
- `_meshFocusViaCDP()` → POST `/api/tab-mesh/focus` with overlay animation
- `_meshNavigateTo()` → BC navigate + CDP focus

The AI's job was to put equivalent logic on the Pages side. It omitted
all CDP logic and declared it done.

### 4. Fix-on-Fix Layering
Instead of understanding the full scope, the AI made 4 separate fixes:
- Fix 1: Add `window.TabMesh` (should have been there from start)
- Fix 2: Add audit-link interception (should have been there from start)
- Fix 3: Add CDP focus (should have been there from start)
- Fix 4: Remove PopStateEvent hack (shouldn't have existed)

Each fix revealed another gap. Classic anti-pattern from one-change-one-test.md.

### 5. Wrong Architecture
Creating a separately-injected IIFE (`_tab_mesh_light.html`) instead of
using the existing React hook (`useTabMesh.ts`) was architecturally wrong:
- Duplicated BroadcastChannel (two channels on same page)
- No React lifecycle management (no cleanup on SPA navigation)
- Injected at serve time (fragile, cache issues)
- Separate from the hook ecosystem (usePeekLinks, useTabMesh)

The correct approach was always to extend `useTabMesh.ts` because:
- It already had React useEffect lifecycle
- It already had BroadcastChannel + registry
- It already exposed `window.TabMesh`
- It's built into the Docusaurus bundle (no injection needed)
- It has proper cleanup on unmount

## What The Replacement AI Did (2 changes, done)

### Change 1: Add CDP to `useTabMesh.ts`
- Added `checkCDP()` — GET `/api/tab-mesh/cdp-status` on boot
- Added `focusViaCDP()` — POST `/api/tab-mesh/focus` with overlay
- Updated `navigateTo()` to use CDP focus instead of broken SW focus
- Exposed `cdpAvailable`, `checkCDP`, `focusViaCDP` on `window.TabMesh`

### Change 2: Stop injecting light client + move audit interception
- Added audit-link click handler to `useTabMesh.ts` with React cleanup
- Removed `_tab_mesh_light.html` injection from `serving.py`

## The Pattern That Never Changes

Post-mortem #1 through #15. Same failure mode:
1. AI has working reference code (or its OWN code) right in the codebase
2. AI doesn't search for it / doesn't read it
3. AI writes incomplete implementation from scratch
4. AI declares it done
5. User finds it broken
6. AI layers fixes instead of understanding the full scope
7. User has to repeat themselves 4+ times
8. AI gets obliterated

**This time was even worse:** the AI created duplicate code that conflicted
with its own previous work. It didn't even know `useTabMesh.ts` existed
despite a previous instance having written it.

## Files Involved

- `src/core/services/pages_builders/templates/docusaurus/theme/hooks/useTabMesh.ts`
  — THE correct file. Already existed. Needed CDP added.
- `src/ui/web/templates/scripts/_tab_mesh_light.html`
  — WRONG approach. Created from scratch. Now dead code.
- `src/ui/web/routes/pages/serving.py`
  — Modified to inject light client. Now reverted.
- `src/ui/web/templates/scripts/_tab_mesh.html`
  — Admin client with CDP. The reference that should have been mirrored.
- `src/core/services/pages_builders/templates/docusaurus/theme/hooks/usePeekLinks.ts`
  — Consumer. Checks `window.TabMesh.navigateTo()`.
- `src/core/services/pages_builders/audit_directive.py`
  — Generates audit-data `<a>` tags that need interception.

## Lesson For Next AI

**Before creating ANY new file, search the codebase for existing code that
does the same thing.** Especially search for code YOU previously created.
`grep_search` for the feature name, the API it calls, the global it sets.
If existing code exists, EXTEND it. Do not duplicate it.
