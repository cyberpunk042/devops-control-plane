# Frontend State Reference

> **Source of truth** for JS global variables in the web admin.
> Derived from actual source: `scripts/content/_init.html`, `_preview.html`,
> `_smart_folders.html`, `_glossary.html`, `_nav.html`.
>
> Last verified: 2026-03-05

---

## Content Tab — Global Variables

### Core State (defined in `_init.html`)

| Variable | Type | Default | Set By | Description |
|----------|------|---------|--------|-------------|
| `contentCurrentMode` | string | `'docs'` | Mode switcher | `'docs'`, `'media'`, or `'archive'` |
| `contentCurrentPath` | string | `''` | `contentLoadFolder()`, `_smartFolderRender()` | **Current folder path — can be VIRTUAL or REAL** |
| `contentFolders` | array | `[]` | `contentLoadRoots()` | Configured root folders from API |
| `contentLoaded` | bool | `false` | `contentInit()` | Whether content tab has been initialized |
| `encKeyConfigured` | bool | `false` | API response | Whether encryption key is configured |
| `_contentCategoryFilters` | object | `{}` | Filter UI | `mode → { category: bool }` |
| `_contentLastRenderData` | object\|null | `null` | `renderContentFiles()` | Cached listing for filter re-render |
| `_contentMediaShowAll` | bool | `false` | Media toggle | Recursive media listing flag |

### Preview State (defined in `_preview.html`)

| Variable | Type | Default | Set By | Description |
|----------|------|---------|--------|-------------|
| `previewCurrentPath` | string | `''` | `contentPreviewFile()` | **Current file path — always REAL filesystem path** |
| `previewCurrentName` | string | `''` | `contentPreviewFile()` | Filename of open file |
| `previewCurrentHasRelease` | bool | `false` | `contentPreviewFile()` | Whether file has release artifact |
| `previewIsText` | bool | `false` | `contentPreviewFile()` | Whether file is text/previewable |
| `previewRawMode` | bool | `false` | Raw toggle | Show raw text vs rendered markdown |
| `previewEditMode` | bool | `false` | Edit toggle | Whether editor is active |
| `previewOrigContent` | string | `''` | Editor init | Snapshot for discard |

### Smart Folder State (defined in `_init.html`)

| Variable | Type | Default | Set By | Description |
|----------|------|---------|--------|-------------|
| `_smartFolders` | array | `[]` | `_smartFoldersLoad()` | All configured smart folders from API |
| `_smartFoldersLoaded` | bool | `false` | `_smartFoldersLoad()` | Whether smart folders have been fetched |
| `_smartFolderActive` | object\|null | `null` | `_smartFolderRender()` | **Active smart folder config (has `.groups`, `._smartRoot`)** |
| `_smartFolderTree` | object\|null | `null` | `_smartFolderRender()` | Resolved tree data for active smart folder |
| `_smartFolderViewRaw` | bool | `false` | `_smartFolderToggleView()` | Raw mode vs smart mode |
| `_smartFolderLastRoot` | string | `''` | Toggle handler | Saved smart root path for toggle-back |

### Glossary/Outline State (defined in `_init.html`)

| Variable | Type | Default | Set By | Description |
|----------|------|---------|--------|-------------|
| `_glossaryVisible` | bool | from localStorage | Toggle button | Whether glossary panel is visible |
| `_glossaryMode` | string | `'outline'` (from localStorage) | Mode toggle | `'outline'` or `'glossary'` |
| `_glossaryOutlineData` | object\|null | `null` | `_glossaryLoadOutline()` | Cached outline for current file |
| `_glossaryGlossaryData` | object\|null | `null` | `_glossaryLoadGlossary()` | Cached glossary for current folder/context |
| `_glossaryContextPath` | string\|null | `null` | `_glossaryDeriveContextPath()` | **Root folder the glossary is loaded for** |
| `_glossaryExpandedNodes` | object | `{}` | UI interaction | Node expand/collapse state |
| `_glossaryFilterText` | string | `''` | Search input | Current filter text |

### Navigation State (defined in `_init.html`)

| Variable | Type | Default | Set By | Description |
|----------|------|---------|--------|-------------|
| `_isRestoring` | bool | `false` | `contentApplySubNav()` | Suppresses `pushState` during restoration |

---

## Path Namespaces — The Critical Distinction

### ⚠️ `contentCurrentPath` has TWO possible namespaces

**When `_smartFolderActive` is NULL (regular browsing):**
```
contentCurrentPath = "src/adapters"          ← REAL filesystem path
contentCurrentPath = "docs"                  ← REAL filesystem path
```

**When `_smartFolderActive` is SET (smart folder browsing):**
```
contentCurrentPath = "code-docs"             ← VIRTUAL (smart folder root)
contentCurrentPath = "code-docs/adapters"    ← VIRTUAL (smart folder module)
contentCurrentPath = "code-docs/core"        ← VIRTUAL (smart folder module)
```

These virtual paths DO NOT exist on the filesystem. They are constructed
from `sf.target + '/' + sf.name` → `_smartRoot`.

### `previewCurrentPath` is ALWAYS real
```
previewCurrentPath = "src/adapters/base.py"  ← ALWAYS real filesystem path
previewCurrentPath = ""                      ← Empty when no file open
```

### Translation: Virtual → Real

Defined in `_smart_folders.html`:

```javascript
// Get subpath within smart folder
// "code-docs/adapters" with root "code-docs" → "adapters"
function _smartFolderSubPath(folderPath, sf) {
    const root = sf._smartRoot || '';
    if (folderPath === root) return '';
    return folderPath.substring(root.length + 1);
}

// Then find the real filesystem path
const subPath = _smartFolderSubPath(contentCurrentPath, _smartFolderActive);
const moduleName = subPath.split('/')[0];  // "adapters"
const group = _smartFolderActive.groups.find(g => g.module === moduleName);
const realPath = group.module_path;         // "src/adapters"
```

### `_glossaryContextPath` can be THREE things:
1. **Real path** — `"src/adapters"` (regular folder glossary context)
2. **`@smart:<name>`** — `"@smart:code-docs"` (combined smart folder glossary)
3. **`null`** — Not yet derived

---

## State Lifecycle: Folder Navigation

```
User clicks a regular folder:
  1. contentLoadFolder("src/adapters") is called
  2. contentCurrentPath = "src/adapters"     ← REAL
  3. previewCurrentPath = ""                  ← cleared
  4. _smartFolderActive = remains unchanged
  5. If _smartFolderActive was set, it's NOT cleared by contentLoadFolder

User clicks a smart folder module:
  1. _smartFolderRender("code-docs/adapters", sf) is called
  2. _smartFolderActive = sf                  ← SET
  3. contentCurrentPath = "code-docs/adapters" ← VIRTUAL
  4. previewCurrentPath = not changed (stays as was)
  5. _glossaryContextPath = null              ← CLEARED for re-derivation
  6. _glossaryGlossaryData = null             ← CLEARED

User opens a file (from any context):
  1. contentPreviewFile(path, name, ...) is called
  2. previewCurrentPath = "src/adapters/base.py" ← REAL
  3. contentCurrentPath = unchanged
  4. _smartFolderActive = unchanged
```

---

## Key Functions Reference

### Content Navigation (`_nav.html`)
| Function | Purpose |
|----------|---------|
| `contentLoadFolder(folderPath)` | Navigate to folder, set `contentCurrentPath`, clear preview |
| `contentPreviewFile(path, name, ...)` | Open file preview, set `previewCurrentPath` |
| `contentLoadRoots()` | Fetch configured root folders into `contentFolders` |

### Smart Folders (`_smart_folders.html`)
| Function | Purpose |
|----------|---------|
| `_smartFolderForPath(folderPath)` | Check if path is inside a smart folder, return config |
| `_smartFolderSubPath(folderPath, sf)` | Strip smart root → get relative module path |
| `_smartFolderRender(folderPath, sf)` | Activate smart folder, set virtual `contentCurrentPath` |
| `_smartFolderRenderModules(browser, sf)` | Render module overview at smart folder root |
| `_smartFolderRenderDocTree(browser, sf, subPath)` | Render doc tree inside a module |

### Glossary (`_glossary.html`)
| Function | Purpose |
|----------|---------|
| `_glossaryDeriveContextPath()` | Determine glossary scope — returns REAL path or `@smart:name` |
| `_glossaryLoadForCurrentContext(force)` | Main entry: derive context, load if needed |
| `_glossaryLoadGlossary(contextPath)` | Fetch glossary from API for given path |
| `_glossaryLoadOutline()` | Fetch outline for current file |
