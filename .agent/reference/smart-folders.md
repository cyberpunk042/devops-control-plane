# Smart Folders Reference

> **Source of truth** for how smart folders work.
> Derived from: `scripts/content/_smart_folders.html`, `routes/smart_folders/__init__.py`,
> `src/core/services/smart_folders/`.
>
> Last verified: 2026-03-05

---

## What Smart Folders Are

A smart folder is a virtual grouping that collects documentation from
multiple real filesystem paths into a single navigable structure.

**Example:** A smart folder called `code-docs` might combine:
- `src/adapters/` → displayed as `code-docs/adapters`
- `src/core/` → displayed as `code-docs/core`
- `src/ui/web/` → displayed as `code-docs/web`

The user sees a unified documentation tree instead of scattered folders.

---

## Configuration

Smart folders are configured in the project's content config. Each has:

```json
{
  "name": "code-docs",
  "target": "docs",
  "groups": [
    { "module": "adapters", "module_path": "src/adapters" },
    { "module": "core", "module_path": "src/core" },
    { "module": "web", "module_path": "src/ui/web" }
  ]
}
```

| Field | Description |
|-------|-------------|
| `name` | Display name of the smart folder |
| `target` | Parent folder where the smart folder appears in navigation |
| `groups[]` | Array of module entries |
| `groups[].module` | Virtual module name (used in virtual path) |
| `groups[].module_path` | Real filesystem path to the module |

---

## Path Namespaces

### The _smartRoot
Computed as `target + '/' + name` (or just `name` if target === name):
```
target = "docs", name = "code-docs" → _smartRoot = "docs/code-docs"
```

### Virtual Paths (displayed to user)
```
"docs/code-docs"              ← smart folder root
"docs/code-docs/adapters"     ← module within smart folder
"docs/code-docs/core"         ← module within smart folder
"docs/code-docs/core/services" ← subfolder within module
```

These paths DO NOT exist on the filesystem.

### Real Paths (actual filesystem)
```
"src/adapters"                ← where adapters files actually live
"src/core"                    ← where core files actually live
"src/core/services"           ← subfolder within core
```

### Translation Functions

```javascript
// 1. Check if a path is inside a smart folder
const sf = _smartFolderForPath("docs/code-docs/adapters");
// Returns: { name: "code-docs", target: "docs", groups: [...], _smartRoot: "docs/code-docs" }

// 2. Get the sub-path within the smart folder
const sub = _smartFolderSubPath("docs/code-docs/adapters", sf);
// Returns: "adapters"

// 3. Map module name to real path
const moduleName = sub.split('/')[0];  // "adapters"
const group = sf.groups.find(g => g.module === moduleName);
const realPath = group.module_path;     // "src/adapters"
```

---

## Key Variables (from `_init.html`)

| Variable | Type | Description |
|----------|------|-------------|
| `_smartFolders` | array | All configured smart folders from API |
| `_smartFoldersLoaded` | bool | Whether smart folders have been fetched |
| `_smartFolderActive` | object\|null | Currently active smart folder config |
| `_smartFolderTree` | object\|null | Resolved tree data (from `/tree` API) |
| `_smartFolderViewRaw` | bool | Whether showing raw filesystem view |
| `_smartFolderLastRoot` | string | Saved path for toggle-back |

When `_smartFolderActive` is set:
- `contentCurrentPath` is a **virtual path**
- `_smartFolderActive._smartRoot` is the virtual root
- `_smartFolderActive.groups` maps modules to real paths

When `_smartFolderActive` is null:
- `contentCurrentPath` is a **real filesystem path**
- Smart folder functions should not be called

---

## API Endpoints

| Endpoint | Method | Returns |
|----------|--------|---------|
| `/api/smart-folders` | GET | List of configured smart folders |
| `/api/smart-folders/discover` | GET | Auto-detected candidates |
| `/api/smart-folders/<name>/tree` | GET | Full module-grouped tree |
| `/api/smart-folders/<name>/file?path=...` | GET | File content from real source |

The tree endpoint returns the complete documentation structure with
README content, file counts, and nested children for each module.

---

## Lifecycle

```
1. Content tab loads → _smartFoldersLoad() fetches config
2. User navigates to a folder that's a smart folder target
3. _smartFoldersInjectEntries() adds virtual entries to the file listing
4. User clicks a smart folder entry
5. _smartFolderRender(virtualPath, sf) activates:
   - Sets _smartFolderActive = sf
   - Sets contentCurrentPath = virtualPath (VIRTUAL)
   - Fetches tree from API if not cached
   - Renders module overview or doc tree
   - Clears glossary context for re-derivation
6. User clicks a file within the smart folder
   - contentPreviewFile() is called with REAL path
   - previewCurrentPath = real filesystem path
   - contentCurrentPath stays VIRTUAL
```

---

## ⚠️ Common Pitfalls

1. **Passing `contentCurrentPath` to a filesystem API when smart folder is active**
   → Will 404 because the virtual path doesn't exist on disk

2. **Comparing `contentCurrentPath` to `previewCurrentPath`**
   → They're in different namespaces when smart folder is active

3. **Assuming `_smartFolderActive.groups` has the data you need**
   → Groups may come from the config OR from `_smartFolderTree.groups`

4. **Not clearing `_glossaryContextPath` when context changes**
   → Glossary will show stale data from previous context
