---
description: Frontend-specific pre-flight checklist for JS template changes
---

# Before Frontend JS Template Changes

> **ALSO READ:** `before-change/common.md` (applies to ALL changes)
> This checklist covers frontend-specific concerns.
> For state variable reference, see: `.agent/reference/frontend-state.md`

---

## Architecture Reminder

### Template File Structure
```
templates/
├── partials/              ← HTML fragments (included in Jinja2 pages)
├── scripts/               ← RAW JAVASCRIPT files (NOT HTML pages)
│   ├── globals/           ← Shared JS: api, cache, modals, card builders
│   │   ├── _api.html      ← api() function
│   │   ├── _cache.html    ← Session/memory caching
│   │   └── _modal.html    ← Modal helpers
│   ├── content/           ← Content tab JS modules
│   │   ├── _init.html     ← Tab initialization
│   │   ├── _nav.html      ← Folder navigation
│   │   ├── _preview.html  ← File preview
│   │   ├── _glossary.html ← Glossary/outline panel
│   │   └── _smart_folders.html ← Smart folder system
│   └── _boot.html         ← Closes </script> block
└── index.html             ← Main SPA template
```

### CRITICAL: scripts/*.html are RAW JAVASCRIPT
They are concatenated into a single `<script>` block.
`globals/_api.html` opens the block. `_boot.html` closes it.
**Adding `<script>` tags inside these files causes syntax errors.**

### API Routes
```
src/ui/web/routes/         ← Flask blueprints
├── content/
│   ├── browse.py          ← /api/content/list, /api/content/preview
│   ├── outline.py         ← /api/content/outline, /api/content/glossary
│   └── peek.py            ← /api/content/peek
├── devops/                ← /api/devops/*
└── ...
```

---

## Frontend Checklist

### 1. Namespace Check (CRITICAL for smart folders)
- [ ] Is `contentCurrentPath` a **virtual** or **real** path at this call site?
- [ ] Is `_smartFolderActive` set or null at this point?
- [ ] Is `previewCurrentPath` set or null?
- [ ] Am I comparing paths from the **same namespace**? (virtual ≠ real)
- [ ] If I need a filesystem path but have a virtual path, am I translating it?

### 2. Caller Trace
- [ ] I have `grep_search`'d for ALL callers of the function I'm modifying
- [ ] I have read each caller and noted what arguments they pass
- [ ] I have verified the state of global variables at each call site

### 3. Function Verification
- [ ] Every function I'm calling EXISTS in the codebase (grep_search)
- [ ] I have read each function's DEFINITION (view_code_item)
- [ ] I know what each function RETURNS

### 4. DOM & Rendering
- [ ] Every DOM element I reference exists (check the template)
- [ ] Event handlers will parse correctly (attribute quoting, escaping)
- [ ] Template literals handle `${}` correctly (no accidental evaluation)

### 5. API Alignment
- [ ] The API route I'm calling EXISTS in the routes/ directory
- [ ] I know the EXACT parameter names the API expects
- [ ] I know the EXACT response format the API returns
- [ ] I've verified by reading the route handler, not guessing

---

## Path Namespace Rules

### Virtual Paths (when `_smartFolderActive` is set)
`contentCurrentPath` = `"code-docs/adapters"` (smart folder virtual name)
These DO NOT exist on the filesystem. They are display paths.

### Real Paths (when `_smartFolderActive` is null)
`contentCurrentPath` = `"src/adapters"` (actual filesystem path)
These match the project's directory structure.

### Translation
```
Virtual → Real:
  subPath = _smartFolderSubPath(currentPath, smartFolder)
  group = smartFolder.groups.find(g => g.module === subPath)
  realPath = group.module_path
```

**NEVER compare a virtual path to a real path. They will never match.**
**NEVER pass a virtual path to a filesystem API. It will 404.**

---

## Frontend-Specific Mistakes

1. **Calling functions that don't exist** → verify with grep_search
2. **Passing virtual paths to /api/content/list** → translate to real first
3. **Assuming contentCurrentPath is always a filesystem path** → not in smart folders
4. **Adding `<script>` tags inside scripts/*.html** → raw JS, no HTML tags
5. **Forgetting to escape `${}` in template literals** → accidental evaluation
6. **Not checking if _smartFolderActive is null before accessing .groups** → crash
