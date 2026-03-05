# Smart Folder Navigation Fixes

Four separate issues related to smart folder context management.
Each analyzed individually.

---

## Issue 1: Non-doc click in outline/glossary → stuck in raw mode

### What the user said
> click a non documentation file or folder in the outline or glossary in the smart docs seem to keep me bugged into raw mode

### What happens in the code

When a file is open in smart docs, `_glossaryRenderOutlineWithSiblings` renders
sibling files and folders fetched from `/content/list?path=<real parent dir>`.

These siblings have **real** paths (e.g. `src/ui/cli/audit/audit_cmds.py`).

- Clicking a **sibling folder** → `contentLoadFolder('src/ui/cli/backup')`
  → `_smartFolderForPath('src/ui/cli/backup')` → returns `null` (only matches virtual paths like `code-docs/...`)
  → line 295: `_smartFolderActive = null` → **smart folder context lost**

- Clicking a **sibling file** → `contentPreviewFile('src/ui/cli/audit/audit_cmds.py', ...)`
  → does NOT clear `_smartFolderActive` directly
  → BUT from that file, clicking "← Back" or "↑ Parent" calls `contentClosePreview()` or `contentGoBack()`
  → these go to `contentLoadFolder` with a real path → same problem

### Code locations
- `_glossaryRenderOutlineWithSiblings` in `_glossary.html` lines ~488-576
  - Sibling folders: `onclick="contentLoadFolder('${esc(d.path || dirPath)}')"` → **real** paths
  - Sibling files: `onclick="contentPreviewFile('${esc(f.path)}', '${esc(f.name)}')"` → **real** paths
- `contentLoadFolder` in `_nav.html` lines 288-295: `_smartFolderForPath` only matches virtual paths

### Proposed fix

In `_glossaryRenderOutlineWithSiblings`, when `_smartFolderActive` is set:
- For **sibling folder** clicks: find the corresponding virtual smart folder path
  and navigate to that instead of the real path.
  e.g. `src/ui/cli/backup` → find module `cli` → navigate to `code-docs/cli/backup`
- For **sibling file** clicks: keep using real paths (contentPreviewFile doesn't break context).
  The file preview works fine with real paths since `previewCurrentPath` is always real.

Helper needed: a function `_smartFolderRealToVirtual(realPath)` that maps a real filesystem
path back to its virtual smart folder path by matching against `_smartFolderTree.groups[].module_path`.

---

## Issue 2: Clicking back to a documentation document → should return to smart docs

### What the user said
> when I click back to a documentation document it should return to the smart docs mode into the smart folder

### What happens in the code

After losing smart folder context (Issue 1), the user is browsing a raw folder
(e.g. `src/ui/cli/`). They click on a README.md in the file list:
→ `contentPreviewFile('src/ui/cli/audit/README.md', 'README.md')`
→ `contentPreviewFile` does NOT check if this file belongs to a smart folder source
→ File opens, but `_smartFolderActive` remains `null`
→ User stays in raw mode

Note: the hash restoration code in `_nav.html` lines 558-571 **already has** the logic
to detect smart folder membership for a real file path:
```javascript
for (const sf of _smartFolders) {
    for (const src of (sf.sources || [])) {
        const prefix = (src.path || '').replace(/\/$/, '');
        if (prefix && filePath.startsWith(prefix + '/')) {
            folderContext = (sf.target === sf.name) ? sf.name : sf.target + '/' + sf.name;
            _smartFolderActive = { ...sf, _smartRoot: folderContext };
            break;
        }
    }
}
```
But this only runs on **page load / hash restoration**, not during normal navigation.

### Code locations
- `contentPreviewFile` in `_preview.html` line 300 — no smart folder detection
- Hash restoration in `_nav.html` lines 558-571 — has the detection logic but wrong trigger

### Proposed fix

Extract the "detect smart folder for real file path" logic into a reusable function
(e.g. `_smartFolderForRealPath(realPath)`) in `_smart_folders.html`.

Call it in `contentPreviewFile` (or in the outline/browser click handlers) when
`_smartFolderActive` is null and a file is being opened. If it matches:
- Re-activate `_smartFolderActive`
- Set `contentCurrentPath` to the virtual path
- The outline and glossary will then load in the correct smart folder context

---

## Issue 3: No option to return from raw src/ folder

### What the user said
> at some point I dont even have any option to return to the smart folder from the raw folder that is actually in src in this case

### What happens in the code

After losing smart folder context, the user is browsing `src/ui/cli/`.
The Smart/Raw toggle is NOT shown because the toggle (lines 307-323 in `_nav.html`)
only appears when **both** conditions are true:
- `_smartFolderViewRaw` is `true`
- `_smartFolderLastRoot` is set

But `_smartFolderViewRaw` is only set to `true` by the explicit `_smartFolderToggleView(true)` function.
When the user loses context by clicking an outline/glossary sibling, `_smartFolderViewRaw` is never set.

### Code locations
- `contentLoadFolder` in `_nav.html` line 307: `if (_smartFolderViewRaw && _smartFolderLastRoot)`
- `_smartFolderToggleView` in `_smart_folders.html` line 211: only set by explicit toggle click

### Proposed fix

In `contentLoadFolder`, after `_smartFolderForPath` returns null (line 294),
check if the real folder path is inside any smart folder's `sources[].path`.

If yes:
- Set `_smartFolderLastRoot` to the smart folder's virtual root
- Show the Smart/Raw toggle (reuse existing toggle HTML from lines 307-323)
- This does NOT require `_smartFolderViewRaw` — it's a **detection-based** toggle appearance

This gives the user an explicit way to switch back to smart mode from any raw folder
that belongs to a smart folder's sources.

---

## Issue 4: Content Vault folder with smart docs equivalent → show toggle

### What the user said
> if a Content Vault folder browsing has a smart docs equivalent I should have the same raw vs smart toggle I have on the smart side

### What happens in the code

The user enters the Content Vault tab and browses `src/ui/cli/` through normal
folder navigation (not from a smart folder). This folder is covered by the `code-docs`
smart folder (`sources[0].path = "src/"`).

But since the user never entered a smart folder, `_smartFolderForPath` returns null,
`_smartFolderViewRaw` is false, and `_smartFolderLastRoot` is null.
→ No toggle is shown
→ User has no awareness that a smart docs view exists for this folder

### Code locations
- Same as Issue 3: `contentLoadFolder` in `_nav.html` lines 288-323
- `_smartFoldersInjectEntries` in `_smart_folders.html` lines 65-103 — only injects entries at
  the **target** folder root (e.g. `docs/`), not inside source paths

### Proposed fix

Same mechanism as Issue 3: in `contentLoadFolder`, after the smart folder path check fails,
detect if the real folder path is inside any smart folder's sources.

If yes, show the Smart/Raw toggle.

This is the same fix as Issue 3 — the only difference is the entry path
(Issue 3: user came from smart folder; Issue 4: user came from Content Vault).
The detection logic doesn't care how the user arrived — it just checks if the
current real path has a smart folder equivalent.

### Implementation note

Issues 3 and 4 share the same implementation: a single detection block in
`contentLoadFolder` that checks real paths against smart folder sources.
They are separate user-facing issues but one code change.

---

## Implementation Order

1. **Helper function**: `_smartFolderForRealPath(realPath)` — shared by all fixes
2. **Issue 3+4** (same code change): Show toggle in `contentLoadFolder` for real paths inside smart folder sources
3. **Issue 2**: Re-activate smart folder in `contentPreviewFile` when opening a doc file
4. **Issue 1**: Remap sibling folder clicks in outline to virtual paths when in smart folder context

---

## Shared helper: `_smartFolderForRealPath(realPath)`

```javascript
/**
 * Check if a REAL filesystem path is inside any smart folder's sources.
 * Returns { sf, smartRoot } if matched, or null.
 */
function _smartFolderForRealPath(realPath) {
    if (!_smartFoldersLoaded || !_smartFolders.length) return null;
    for (const sf of _smartFolders) {
        for (const src of (sf.sources || [])) {
            const prefix = (src.path || '').replace(/\/$/, '');
            if (prefix && (realPath === prefix || realPath.startsWith(prefix + '/'))) {
                const smartRoot = (sf.target === sf.name) ? sf.name : sf.target + '/' + sf.name;
                return { sf, smartRoot };
            }
        }
    }
    return null;
}
```
