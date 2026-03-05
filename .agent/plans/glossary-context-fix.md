# Glossary Context Loading — Failure Analysis & Remediation Plan

**Date**: 2026-03-05  
**Status**: MUST FIX — the glossary is broken  
**Root cause**: Failed to follow the original plan (`contextual-glossary.md`)


## 1. What Failed

The original plan (`.agent/plans/contextual-glossary.md`, section 3.4) specifies
two distinct data loading functions with separate lifecycles:

```
Data Loading:
├── _glossaryLoadFolder(folderPath)     → loads folder glossary from API
├── _glossaryLoadSmartFolder(name)      → loads smart folder glossary from API  
└── _glossaryLoadFile(filePath)         → loads single file outline from API
```

And two distinct state variables:

```
State Variables:
├── _glossaryPath          → folder the glossary is for (set ONCE per context)
├── _glossaryActiveFile    → currently viewed file path (changes on navigation)
```

**What was built instead:**

- ONE function `_glossaryLoadForCurrentContext()` that handles both outline AND
  glossary mode with the same lifecycle
- ONE resolver `_glossaryResolveCurrentFolder()` that re-derives the glossary
  folder path from `contentCurrentPath` on EVERY call
- NO dedicated `_glossaryPath` variable — the path is ephemeral, re-computed
  each time from transient state

**Why this is catastrophically broken:**

- `contentCurrentPath` changes on every folder click, file open, and hash restore
- The resolver produces different results depending on timing and caller context
- 5 different callers invoke the load function → 5 different derived paths
- Result: navigating to `src/adapters/languages` loads glossary for that subfolder
  (3 files) instead of `src/adapters` (16 files)
- The bug is STRUCTURAL — no amount of patching the resolver can fix it because
  the architecture is wrong


## 2. The Core Design Error

**Outline and glossary have different lifecycles. They were conflated.**

| Behavior | Outline Mode | Glossary Mode |
|---|---|---|
| Scope | Current file | Current root context |
| Changes when | User opens a different file | User changes root (folder bar, smart folder) |
| On file navigation | Re-fetch for new file ✅ | NEVER re-fetch — only move highlight |
| On subfolder browsing | No effect | NEVER re-fetch — only move highlight |

By putting both in the same `_glossaryLoadForCurrentContext()` with the same
"resolve → fetch" pattern, glossary mode inherited outline mode's behavior of
re-fetching on every navigation. This made partial glossaries structurally
inevitable.


## 3. Remediation Plan

### 3.1 New state variable

Add `_glossaryContextPath` to `_init.html`:
- Set ONCE when the glossary context changes
- Never re-derived during file navigation or subfolder browsing
- Cleared only when the user explicitly changes root context

### 3.2 Delete `_glossaryResolveCurrentFolder()`

This function is the source of every bug. It must be removed entirely.
Replace with `_glossaryDeriveContextPath()` which is called ONCE to derive
the initial context, then the result is stored in `_glossaryContextPath`.

### 3.3 Separate the lifecycles in `_glossaryLoadForCurrentContext()`

```javascript
function _glossaryLoadForCurrentContext(force) {
    if (!_glossaryVisible) return;

    if (_glossaryMode === 'outline') {
        // Outline: re-fetches per file — this is CORRECT
        if (previewCurrentPath) {
            _glossaryLoadOutline(previewCurrentPath);
        } else {
            _glossaryShowEmpty('Open a file to see its outline');
        }
        return;
    }

    // ── Glossary mode: STABLE per context ──

    // Data already loaded and not forced → just update highlights
    if (_glossaryGlossaryData && !force) {
        _glossaryUpdateActiveFile();
        return;
    }

    // First load or forced → derive context path ONCE if not set
    if (!_glossaryContextPath) {
        _glossaryContextPath = _glossaryDeriveContextPath();
    }
    if (_glossaryContextPath) {
        _glossaryLoadGlossary(_glossaryContextPath);
    } else {
        _glossaryShowEmpty('Select a folder to see its glossary');
    }
}
```

### 3.4 One-time derivation function

```javascript
function _glossaryDeriveContextPath() {
    // Smart folder → use module_path from groups
    if (_smartFolderActive) {
        const groups = (_smartFolderActive.groups
            || (_smartFolderTree && _smartFolderTree.groups)
            || []);
        if (previewCurrentPath) {
            for (const g of groups) {
                if (g.module_path && previewCurrentPath.startsWith(g.module_path + '/')) {
                    return g.module_path;
                }
            }
        }
        if (groups.length > 0) return groups[0].module_path;
        return null;
    }

    // Regular folder → use the folder-bar selector value (always root)
    const sel = document.getElementById('content-folder-select');
    if (sel && sel.value) return sel.value;

    // Last resort
    return contentCurrentPath || null;
}
```

### 3.5 Fix all callers

| File | Caller | Current (broken) | Fix |
|---|---|---|---|
| `_nav.html:324` | `contentLoadFolder` | `_glossaryLoadForCurrentContext()` | `_glossaryUpdateActiveFile()` |
| `_preview.html:557` | `contentPreviewFile` | `_glossaryLoadForCurrentContext()` | Keep — outline will re-fetch, glossary will skip (correct) |
| `_smart_folders.html:149` | `_smartFolderRender` | `_glossaryLoadForCurrentContext()` | Set `_glossaryContextPath` + `_glossaryGlossaryData = null` first, THEN call with `force=true` |
| `_glossary.html:31` | `contentToggleGlossary` | `_glossaryLoadForCurrentContext()` | Keep — will derive context on first open |
| `_glossary.html:51` | `_glossarySwitchMode` | `_glossaryLoadForCurrentContext(true)` | Clear `_glossaryGlossaryData = null` first, then call with `force=true` |

### 3.6 Reset context on root change

When the user clicks a DIFFERENT root folder in the folder bar (not a subfolder):
- `_glossaryContextPath = null`
- `_glossaryGlossaryData = null`
- Next `_glossaryLoadForCurrentContext()` will derive and fetch fresh


## 4. Files to Change

1. `src/ui/web/templates/scripts/content/_init.html` — add `_glossaryContextPath`
2. `src/ui/web/templates/scripts/content/_glossary.html` — rewrite load function, delete resolver, add derivation
3. `src/ui/web/templates/scripts/content/_nav.html` — fix `contentLoadFolder` caller
4. `src/ui/web/templates/scripts/content/_smart_folders.html` — set context before calling glossary
5. `src/ui/web/templates/scripts/content/_preview.html` — no change needed (outline re-fetches correctly, glossary skips correctly)


## 5. What This Fixes

- Landing on `src/adapters/languages` → glossary shows `src/adapters` (16 files)
- Navigating from `containers/__init__.py` to `languages/node.py` → glossary stays
- Browsing into any subfolder → glossary stays
- Switching between outline and glossary → each has correct data
- Smart folder context → glossary loads correct module root
