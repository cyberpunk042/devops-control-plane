# Navigation History — Full-Spectrum Proposed Solution

## Status: PROPOSAL — awaiting review

---

## 1. What the user said (exact words)

1. "we also want a back possibility, even if I was in a modal I could return to another modal"
2. "if I refresh my page I could reland on the modal"
3. "even if I have the ssh password modal on top, I still have all this possible behind"
4. "If I am navigating the raw or the preview and I click somewhere it would get the closest hX/#X parent?"
5. "the button named Back would actually be a real back in the content vault file browser"
6. "there would also be a way to open parent folder"
7. "everywhere its relevant we add this Back button which should be equivalent to the real browser back button"

---

## 2. What this means concretely

### 2a. Every user navigation action pushes a history entry

Every time the user takes a navigation action (not a minor state toggle), the URL hash changes via `history.pushState()`. This creates a browser history entry. The browser's Back button walks backward through these entries. The browser's Forward button walks forward.

### 2b. The "← Back" button in the UI = `history.back()`

Wherever we show a "← Back" button, clicking it is literally `history.back()`. It does the same thing the browser Back button does. No special logic. No "go to parent folder." It goes to whatever the user was looking at before.

### 2c. "↑ Parent" is a separate button from "← Back"

In the content file browser, when viewing a file, the user currently sees a single "← Back" button that goes to the parent folder. Under the new system:
- "← Back" = `history.back()` = go to whatever you were at before (could be a different file, a different folder, a different tab)
- "↑ Parent" = navigate to the parent folder (this is a NEW navigation action, it pushes a new history entry)

### 2d. Navigation-worthy modals push history entries

When the user opens a file preview modal (`openFileInModal`), that IS a navigation action. The URL hash changes to encode the modal state. If the user refreshes the page, the modal re-opens with the same content. If the user clicks "← Back" or browser Back, the modal closes and the previous state is restored.

When the user opens a peek preview overlay (`_openPeekPreview`), that IS a navigation action. Same rules.

### 2e. Prompt modals do NOT push history entries

The SSH passphrase modal, the unsaved changes modal, the rename modal, the move modal, the delete confirmation — these are NOT navigation. They are ephemeral prompts. They don't change the URL. They don't push history. They appear on top and disappear. The navigation stack underneath remains unchanged.

### 2f. Line tracking in code view

When viewing a file in "raw" mode (Monaco editor — read-only), the cursor position is tracked. The URL hash includes the line number. If the user clicks on line 42, the hash updates to `...@raw:42`. This uses `replaceState` (not push), because scrolling/clicking within a file is not a "navigation" — it's positioning.

When the user arrives at a file from a link that specifies a line (e.g., from peek "Jump to", from audit file link, from a hash with `:42`), the editor focuses on that line, reveals it in center, and highlights it.

### 2g. Anchor tracking in rendered markdown

When viewing a file in "preview" mode (rendered markdown), the URL hash tracks the closest visible heading. As the user scrolls, the hash updates to encode which `<h1>`/`<h2>`/`<h3>`/... heading is currently at the top of the viewport. This uses `replaceState` (not push).

When the user clicks on an anchor link in the rendered markdown (e.g., `#installation`), the viewport scrolls to that heading and the hash updates. This also uses `replaceState`.

When the user clicks on a doc-link (a link to another file), that IS a navigation action (push).

---

## 3. Hash format

The hash is a single string that encodes the complete visible state. It must be parseable to reconstruct the view on page load.

### 3a. Base hash anatomy

```
#TAB/MODE/PATH@VIEWMODE:LINE~ANCHOR
```

| Segment | Meaning | Examples |
|---------|---------|---------|
| `TAB` | Top-level tab | `dashboard`, `content`, `wizard`, `debugging`, `secrets`, `integrations`, `devops`, `audit` |
| `MODE` | Sub-mode within that tab | For content: `docs`, `media`, `archive`, `chat`. For debugging: `audit`, `state`, `health`, `config`, `commands`, `traces`. For wizard: step ID like `k8s`, `docker`. For secrets: env name. |
| `PATH` | Context within mode | Folder path, file path, thread name, etc. |
| `@VIEWMODE` | View mode suffix for files | `@preview`, `@raw`, `@edit` |
| `:LINE` | Line number suffix | `:42`, `:100` — only meaningful in `@raw` and `@edit` modes |
| `~ANCHOR` | Anchor/heading suffix | `~installation`, `~api-reference` — only meaningful in `@preview` mode for markdown |

### 3b. Hash examples for every reachable state

#### Dashboard
```
#dashboard
```

#### Content — folder browsing
```
#content/docs/docs
#content/docs/docs/guides
#content/docs/docs/guides/setup
#content/media/docs/images
#content/archive/backups
#content/archive/backups/2024
#content/chat
#content/chat/general
```

#### Content — file preview
```
#content/docs/docs/README.md@preview
#content/docs/docs/README.md@preview~installation
#content/docs/docs/README.md@raw
#content/docs/docs/README.md@raw:42
#content/docs/docs/README.md@edit
#content/docs/docs/README.md@edit:42
#content/docs/docs/guides/setup.md@preview~prerequisites
#content/media/docs/images/logo.png@preview
#content/docs/src/core/services/peek.py@raw:100
```

#### Content — peek preview overlay on top of file preview
```
#content/docs/docs/README.md@preview>>peek/src/core/services/peek.py@raw:15
```

#### Content — file preview modal on top of any tab
```
#debugging/audit>>modal/src/core/services/peek.py@preview
#wizard/k8s>>modal/k8s/deployment.yaml@raw:10
#integrations>>modal/Dockerfile@edit
```

#### Wizard
```
#wizard
#wizard/k8s
#wizard/docker
#wizard/pages
```

#### Debugging
```
#debugging/audit
#debugging/state
#debugging/health
#debugging/config
#debugging/commands
#debugging/traces
```

#### Secrets
```
#secrets
#secrets/production
#secrets/staging
```

#### Integrations
```
#integrations
```

#### DevOps
```
#devops
```

#### Audit
```
#audit
```

### 3c. The `>>` separator for overlay/modal state

When a navigation-worthy overlay or modal is open on top of the base view, the hash uses `>>` to separate the base state from the overlay state.

```
BASE_HASH>>OVERLAY_TYPE/OVERLAY_PATH@VIEWMODE:LINE
```

`OVERLAY_TYPE` is one of:
- `peek` — the peek preview overlay (opened from rendered markdown peek links)
- `modal` — the file preview modal (opened from debugging/audit/integrations via `openFileInModal`)

This means:
- `#content/docs/docs/README.md@preview>>peek/src/core/peek.py@raw:42` — the user is viewing README.md in preview mode, and on top of that there is a peek preview overlay showing peek.py at line 42
- `#debugging/audit>>modal/Dockerfile@raw` — the user is in the debugging/audit tab, and on top of that there is a file preview modal showing Dockerfile in raw mode

On page refresh, both the base state AND the overlay state are reconstructed.

On `history.back()`, the overlay closes and the base state is restored (the previous hash had no `>>` segment).

---

## 4. Classification of every user action

### 4a. Actions that PUSH history (create a new entry)

These change the URL hash via `pushState`. The browser's back button will undo them.

| # | Action | Hash before | Hash after |
|---|--------|------------|------------|
| 1 | Click a top-level tab | `#dashboard` | `#content/docs/docs` |
| 2 | Click a folder in the file list | `#content/docs/docs` | `#content/docs/docs/guides` |
| 3 | Click a file in the file list | `#content/docs/docs` | `#content/docs/docs/README.md@preview` |
| 4 | Click "← Back" button in file preview | `#content/docs/docs/README.md@preview` | (previous history entry — could be anything) |
| 5 | Click "↑ Parent" button in file preview | `#content/docs/docs/README.md@preview` | `#content/docs/docs` |
| 6 | Switch content mode (docs → media) | `#content/docs/docs` | `#content/media/docs` |
| 7 | Click a breadcrumb folder segment | `#content/docs/docs/guides/setup` | `#content/docs/docs/guides` |
| 8 | Click a doc-link in rendered markdown | `#content/docs/docs/README.md@preview` | `#content/docs/docs/guides/setup.md@preview` |
| 9 | Click "Open" in peek tooltip | `#content/docs/docs/README.md@preview` | `#content/docs/docs/README.md@preview>>peek/src/core/peek.py@raw:42` |
| 10 | Click "Jump to" in peek preview header | `#content/docs/docs/README.md@preview>>peek/src/core/peek.py@raw:42` | `#content/docs/src/core/peek.py@raw:42` |
| 11 | Click a file link in debugging/audit | `#debugging/audit` | `#debugging/audit>>modal/src/core/services/peek.py@preview` |
| 12 | Click "Open in Content Tab" in file preview modal | `#debugging/audit>>modal/Dockerfile@raw` | `#content/docs/Dockerfile@raw` |
| 13 | Close peek preview overlay (✕, Esc, backdrop click) | `#content/docs/docs/README.md@preview>>peek/src/core/peek.py@raw:42` | `#content/docs/docs/README.md@preview` |
| 14 | Close file preview modal (✕, Esc, backdrop click) | `#debugging/audit>>modal/Dockerfile@raw` | `#debugging/audit` |
| 15 | Switch debugging sub-tab | `#debugging/audit` | `#debugging/traces` |
| 16 | Select archive folder | `#content/archive` | `#content/archive/backups` |
| 17 | Select chat thread | `#content/chat` | `#content/chat/general` |

### 4b. Actions that REPLACE state (update hash silently, no history entry)

These change the URL hash via `replaceState`. The browser's back button will NOT see them.

| # | Action | What changes in hash |
|---|--------|---------------------|
| 1 | Toggle view mode (preview ↔ raw ↔ edit) | `@preview` → `@raw` or `@edit` |
| 2 | Click/position cursor on a line in Monaco | `:42` → `:100` |
| 3 | Scroll through rendered markdown (viewport anchor tracking) | `~installation` → `~api-reference` |
| 4 | Click an anchor link in rendered markdown | `~` changes to clicked anchor |

### 4c. Actions that do NOT touch the URL at all

| # | Action |
|---|--------|
| 1 | SSH passphrase modal opens/closes |
| 2 | Unsaved changes modal opens/closes |
| 3 | Rename file modal opens/closes |
| 4 | Move file modal opens/closes |
| 5 | Delete confirmation modal opens/closes |
| 6 | Fix orphaned release modal opens/closes |
| 7 | Encrypt file modal opens/closes |
| 8 | Toast notifications |
| 9 | Category filter toggles in file browser |
| 10 | Search/filter input in file browser |
| 11 | Upload zone show/hide |
| 12 | Settings panel |

---

## 5. File-by-file changes

### 5a. `_tabs.html` — NO changes needed

The tab-level logic already works correctly:
- `switchTab()` calls `pushState` for user-initiated navigation
- `popstate` handler calls `switchTab(state.tab, { fromPopstate: true })`
- `hashchange` handler catches direct hash edits
- `_navDepth` tracks push count for safe back detection
- `restoreFromHash()` uses `replaceState` on initial load

One thing we need to add: when `switchTab` receives a hash with `>>`, it needs to parse that and pass the overlay info to the tab loader. This is new.

### 5b. `_nav.html` — contentUpdateHash / contentApplySubNav

#### `contentUpdateHash()` changes

Currently: always uses `replaceState`.

Must change to:
- Accept a `{ push = true }` parameter
- Default `push = true` — most callers want to push
- When `push = true` AND the hash actually changed → call `pushState`
- When `push = false` → call `replaceState` (for view mode toggles, line/anchor tracking)
- Add line number to hash (read from `window._contentFocusLine`)
- Add anchor to hash (read from a new `window._contentFocusAnchor`)
- Skip when `_modalPreviewActive` (existing guard)

#### `contentApplySubNav()` changes

Currently: called from `loadContentTab(subParts)` during both initial load and popstate.

Must change to:
- Parse `>>` overlay segment if present
- After restoring the base content state, open the overlay/modal if the hash says so
- All calls to `contentPreviewFile` / `contentLoadFolder` from within `contentApplySubNav` must use `{ push: false }` since this is a restore, not a new navigation

### 5c. `_preview.html` — file preview header

#### "← Back" button

Currently: `onclick="contentClosePreview()"` — hardcoded to load parent folder.

Must change to:
- Rename from "← Back" to showing TWO buttons:
  - "← Back" → `history.back()` with fallback (if `_navDepth === 0`, go to parent folder)
  - "↑" → `contentLoadFolder(contentCurrentPath)` — always goes to parent folder

#### Anchor tracking in rendered markdown

When rendering markdown preview (the `.content-preview-rendered` container), add an `IntersectionObserver` that watches all headings (`h1, h2, h3, h4, h5, h6`). As headings scroll past the top of the viewport, update `window._contentFocusAnchor` and call `contentUpdateHash({ push: false })`.

The headings already have `id` attributes generated by marked.js (`marked.parse()` with default options generates heading IDs from text content — e.g., "Installation" becomes `id="installation"`).

When arriving at a hash with `~anchor`, scroll to the element with that ID.

#### Line tracking in Monaco raw/edit mode

After `monacoCreate()` sets up the editor, add a cursor position listener:

```javascript
_monacoEditor.onDidChangeCursorPosition((e) => {
    window._contentFocusLine = e.position.lineNumber;
    // Debounced replaceState — don't flood the browser
    clearTimeout(window._lineHashTimer);
    window._lineHashTimer = setTimeout(() => {
        contentUpdateHash({ push: false });
    }, 500);
});
```

This is added in `_monaco.html`, not in `_preview.html`.

### 5d. `_preview_enc.html` — contentClosePreview

The `contentClosePreview()` function is defined here. Same change as the button in `_preview.html`:
- The button becomes `history.back()` with fallback
- A separate "↑" parent button is added

### 5e. `_modal_preview.html` — navigation-worthy modal

#### `openFileInModal()` changes

Currently: opens modal without touching the URL.

Must change to:
- After opening the modal, push a history entry with `>>modal/filePath@viewMode`
- The hash becomes `CURRENT_HASH>>modal/filePath@raw` (or @preview, etc.)

#### `_modalPreviewClose()` changes

Currently: restores previous state and calls `modalClose()`.

Must change to:
- Call `history.back()` instead of manually restoring
- The `popstate` handler will receive the previous hash (without `>>modal/...`) and restore the correct state
- However, we still need the DOM restoration logic (moving `#content-browser` back). This must be triggered from the `popstate` path.

**Important complexity:** When popstate fires and the hash no longer has `>>modal`, we need to detect that a modal was open and close/restore it. This means the popstate handler in `_tabs.html` needs to check `_modalPreviewActive` and call `_modalPreviewRestore()` + `modalClose()` before proceeding.

#### Page refresh with modal hash

When `restoreFromHash()` is called on page load and the hash contains `>>modal/...`:
1. Parse the base hash (before `>>`)
2. Restore the base tab/content state via `switchTab(baseHash, { fromPopstate: true })`
3. Then open the modal via `openFileInModal(filePath)`

### 5f. `_preview.html` — peek preview overlay

#### `_openPeekPreview()` changes

Currently: opens overlay without touching the URL.

Must change to:
- After opening the overlay, push a history entry with `>>peek/filePath@viewMode:line`
- The hash becomes `CURRENT_HASH>>peek/resolved_path@raw:15`

#### `_closePeekPreview()` changes

Currently: removes the overlay DOM element.

Must change to:
- Call `history.back()` instead of directly removing
- The `popstate` handler will receive the previous hash (without `>>peek/...`) and restore the correct state
- But we still need the DOM cleanup (removing the overlay). This must be triggered from the `popstate` path.

**Same complexity as modal:** When popstate fires and the hash no longer has `>>peek`, detect the peek overlay is open and close it.

#### Page refresh with peek hash

Same as modal: parse `>>peek/...`, restore base state, then open peek preview for the specified file.

### 5g. `_monaco.html` — cursor tracking

Add the `onDidChangeCursorPosition` listener in `monacoCreate()` to track `window._contentFocusLine`. Debounce with 500ms `replaceState`.

### 5h. `_debugging.html` — sub-tab navigation

#### `debugSwitchMode()` changes

Currently: uses `replaceState`.

Must change to: use `pushState`. Each sub-tab switch is a navigation action.

### 5i. `_browser.html` — folder breadcrumb

No changes needed to the breadcrumb itself — folder clicks already call `contentLoadFolder()`, which will now call `contentUpdateHash({ push: true })`.

But: we may want to add the "← Back" button to the folder view as well, not just the file preview view. The user said "everywhere its relevant." When browsing folders, there's no explicit "Back" button — you use the breadcrumb to go to parent. A "← Back" button here would go to whatever the user was looking at before — which could be a file preview, a different folder, or a different tab entirely.

### 5j. `_cache.html` — openFileInEditor

No changes to the function signature. The behavior changes because `switchTab()` already pushes history. But when `openFileInModal()` is called instead, that function now pushes its own history entry with `>>modal/...`.

---

## 6. The popstate handler — centralized state restoration

The popstate handler in `_tabs.html` currently does:

```javascript
window.addEventListener('popstate', (e) => {
    _popstateActive = true;
    if (e.state && e.state.tab) {
        _navDepth = e.state.depth || 0;
        switchTab(e.state.tab, { fromPopstate: true });
    }
    setTimeout(() => { _popstateActive = false; }, 50);
});
```

This must be enhanced to:

1. **Check if an overlay/modal is currently open** — if `_peekPreviewOverlay` exists, call `_closePeekPreviewDirect()` (DOM-only close, no `history.back()` call). If `_modalPreviewActive`, call `_modalPreviewRestore()` + `modalClose()`.

2. **Parse the `>>` separator** in `e.state.tab` — if the new hash has `>>`, split into base hash and overlay hash. Restore the base hash, then open the overlay.

3. **If the new hash has NO `>>`** — just restore the tab/content as before (which is the existing behavior).

```
// Pseudocode for enhanced popstate:
popstate(e) {
    // 1. Close any currently-open navigation overlay/modal (DOM only, no history.back)
    if (_peekPreviewOverlay) _closePeekPreviewDirect();
    if (_modalPreviewActive) { _modalPreviewRestore(); modalClose(); }

    // 2. Parse the target hash
    const fullTab = e.state.tab;
    const overlayIdx = fullTab.indexOf('>>');
    const baseTab = overlayIdx > 0 ? fullTab.substring(0, overlayIdx) : fullTab;
    const overlay = overlayIdx > 0 ? fullTab.substring(overlayIdx + 2) : null;

    // 3. Restore base state
    switchTab(baseTab, { fromPopstate: true });

    // 4. Open overlay if present in hash
    if (overlay) {
        const overlayParts = overlay.split('/');
        const overlayType = overlayParts[0]; // 'peek' or 'modal'
        const overlayPath = overlayParts.slice(1).join('/');
        // Parse @viewMode:line from overlayPath...
        if (overlayType === 'peek') _openPeekPreviewFromHash(filePath, line);
        if (overlayType === 'modal') openFileInModal(filePath);
    }
}
```

---

## 7. Preventing double-pushes and loops

### 7a. switchTab() already pushes for tab changes

When `switchTab()` is called by a user action, it pushes history. Then it calls `loadContentTab(subParts)` → `contentApplySubNav()` → `contentPreviewFile()` → `contentUpdateHash()`. If `contentUpdateHash()` also pushes, we get a DOUBLE push.

**Solution:** `contentApplySubNav()` always calls functions with `{ push: false }`. It is a RESTORE function, not a navigation function. Only direct user actions (clicks on folders, files, mode buttons) call with `{ push: true }`.

### 7b. popstate → switchTab → contentApplySubNav → contentUpdateHash

When `popstate` fires, we call `switchTab(hash, { fromPopstate: true })`. `switchTab` skips its own push (because `fromPopstate`). Then `loadContentTab` → `contentApplySubNav` → `contentPreviewFile` → `contentUpdateHash()`. `contentUpdateHash()` must NOT push because this is a restore.

**Solution:** Add a flag `_isRestoring` set to `true` during `contentApplySubNav()`. `contentUpdateHash()` checks this flag and uses `replaceState` regardless of the `push` parameter.

### 7c. Close overlay → history.back() → popstate → check overlay

When the user closes a peek overlay by clicking ✕, we call `history.back()`. This triggers `popstate`. The `popstate` handler sees `_peekPreviewOverlay` exists and calls `_closePeekPreviewDirect()`. But we already started closing from the ✕ click...

**Solution:** Two separate close functions:
- `_closePeekPreview()` — called by user action (✕, Esc, backdrop). Calls `history.back()`. Does NOT remove DOM directly.
- `_closePeekPreviewDirect()` — called by popstate handler. Removes DOM directly. Does NOT touch history.

When `_closePeekPreview()` calls `history.back()`, the popstate fires and calls `_closePeekPreviewDirect()` which does the actual DOM cleanup.

Same pattern for modal: `_modalPreviewClose()` calls `history.back()`, popstate calls `_modalPreviewRestore()` + `modalClose()`.

---

## 8. Anchor tracking implementation detail

### 8a. Generating heading IDs

`marked.parse()` (the markdown library) generates heading IDs by default. For example, `## Installation Guide` becomes `<h2 id="installation-guide">Installation Guide</h2>`.

If the fallback regex renderer is used, we need to generate IDs manually in the heading replacement:
```javascript
html = html.replace(/^##\s+(.+)$/gm, (_, t) => {
    const id = t.toLowerCase().replace(/[^\w]+/g, '-').replace(/-$/, '');
    return `<h2 id="${id}">${t}</h2>`;
});
```

### 8b. IntersectionObserver for scroll tracking

After rendering markdown preview, set up an `IntersectionObserver`:

```javascript
const headings = body.querySelectorAll('h1[id], h2[id], h3[id], h4[id], h5[id], h6[id]');
const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
        if (entry.isIntersecting) {
            window._contentFocusAnchor = entry.target.id;
            contentUpdateHash({ push: false });
            break;
        }
    }
}, { rootMargin: '-10% 0px -80% 0px' }); // trigger when heading is near top 10-20% of viewport

headings.forEach(h => observer.observe(h));
```

Store the observer reference so it can be disconnected when leaving preview mode.

### 8c. Restoring anchor from hash

In `contentApplySubNav()`, when the hash has `~anchor`:

```javascript
const tildeIdx = viewMode.indexOf('~');
if (tildeIdx > 0) {
    const anchor = viewMode.substring(tildeIdx + 1);
    viewMode = viewMode.substring(0, tildeIdx);
    // After file loads and renders, scroll to anchor
    window._contentFocusAnchor = anchor;
}
```

After markdown rendering completes, check `window._contentFocusAnchor` and scroll:

```javascript
if (window._contentFocusAnchor) {
    const el = document.getElementById(window._contentFocusAnchor);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    window._contentFocusAnchor = null;
}
```

---

## 9. Implementation order

### Phase 1: Core history mechanics
1. Modify `contentUpdateHash()` to accept `{ push }` parameter
2. Update all callers — `contentLoadFolder`, `contentPreviewFile`, `contentPreviewEncrypted`, `contentSwitchMode`
3. Mark `contentApplySubNav` as restore-only (no push)
4. Add `_isRestoring` flag to prevent pushes during restore
5. Change `debugSwitchMode()` from `replaceState` to `pushState`

### Phase 2: Back and Parent buttons
6. Split "← Back" into two buttons in `_preview.html` and `_preview_enc.html`
7. Wire "← Back" to `history.back()` with `_navDepth > 0` fallback
8. Wire "↑" to `contentLoadFolder(contentCurrentPath)` (push)
9. Add "← Back" button to folder browser views where relevant

### Phase 3: Line tracking
10. Add `onDidChangeCursorPosition` listener in `monacoCreate()` → debounced `replaceState`
11. Include line number in `contentUpdateHash()` output for `@raw` and `@edit` modes
12. Verify `contentApplySubNav()` already parses `:LINE` (it does — line 510-515)

### Phase 4: Anchor tracking
13. Ensure heading IDs are generated in both marked.js and fallback renderer
14. Add `IntersectionObserver` for scroll tracking in rendered markdown
15. Parse `~ANCHOR` in `contentApplySubNav()`
16. Include anchor in `contentUpdateHash()` output for `@preview` mode
17. Scroll to anchor on restore

### Phase 5: Modal/overlay history
18. Implement `>>` hash separator parsing in `restoreFromHash()` and `popstate`
19. Modify `openFileInModal()` to push `>>modal/...` hash
20. Modify `_modalPreviewClose()` to call `history.back()`
21. Split peek close into `_closePeekPreview()` (history.back) and `_closePeekPreviewDirect()` (DOM only)
22. Modify `_openPeekPreview()` to push `>>peek/...` hash
23. Handle popstate for overlay cleanup + restore

---

## 10. Files touched (summary)

| File | What changes |
|------|-------------|
| `_tabs.html` | Enhanced popstate handler for `>>` overlay parsing |
| `_nav.html` | `contentUpdateHash()` push/replace param, line+anchor in hash. `contentApplySubNav()` restore flag, `~anchor` parsing. |
| `_preview.html` | Split Back/Parent buttons. IntersectionObserver for anchors. Scroll-to-anchor on restore. |
| `_preview_enc.html` | Split Back/Parent buttons in `contentClosePreview()`. |
| `_monaco.html` | `onDidChangeCursorPosition` listener for line tracking. |
| `_modal_preview.html` | Push `>>modal/...` hash on open. `history.back()` on close. |
| `_debugging.html` | `debugSwitchMode()` → `pushState`. |
| `_browser.html` | Optional "← Back" button for folder views. |
| `_cache.html` | No signature changes, behavior changes via modal push. |

---

## 11. Resolved decisions

1. ✅ **Peek/modal close = `history.back()`** — Confirmed. Cleaner because we don't want needless modals in the history loop. The overlay/modal is _undone_, not replaced. Forward would re-open — that's fine, it's all about the specific cases.

2. ✅ **View mode toggle (raw ↔ preview ↔ edit) = `replaceState`** — Confirmed. You're within a scope and adapting, not navigating to a new place. Back should go to the previous _location_, not the previous view mode of the same file.

## 12. Remaining open questions

1. **Breadcrumb clicks:** When clicking a breadcrumb segment (e.g., clicking "docs" in `docs > guides > setup`), should that push history? Currently proposed as yes (it's a navigation). _(Likely yes — it changes what you're looking at.)_

2. **Archive / chat sub-navigation:** Should archive folder selection and chat thread selection also push history? Currently proposed as yes. _(Likely yes — same reasoning.)_
