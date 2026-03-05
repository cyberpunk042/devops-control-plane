# Smart Virtual Folders — Implementation Plan

> Implementation order, concrete tasks, and file-level changes for each layer.
> Reference: `.agent/plans/smart-folders-analysis.md` for design decisions.

---

## Phase 1: Foundation (Data Model + Discovery Service)

Everything depends on these two. No UI, no build — just the data layer and the
scanner that every consumer will call.

### 1A: Data Model (`project.yml` + `config_ops.py`)

**Goal:** `smart_folders` is a first-class config key that round-trips through
read/save and is exposed to the API.

**Files to modify:**

| File | Change |
|------|--------|
| `project.yml` | Add `smart_folders` key (initially empty `[]`) |
| `src/core/services/config_ops.py` | Handle `smart_folders` in `read_config()` and `save_config()` |
| `src/ui/web/routes/config/__init__.py` | Expose smart folders in `GET /api/config` response (already comes through `read_config`) |

**Schema:**
```yaml
smart_folders:
  - name: code-docs           # str, required, unique
    label: "Code Documentation" # str, required
    target: docs              # str, required (content folder name or =name for standalone)
    sources:                  # list, required, min 1
      - path: src/            # str, required (relative to project root)
        pattern: "**/README.md" # str, required (glob)
```

**Validation rules:**
- `name` must be a valid directory name (no slashes, no dots prefix)
- `target` must reference an existing `content_folders` entry OR equal `name`
- `sources[].path` must be an existing directory
- `sources[].pattern` must be a valid glob

**Tasks:**
1. Add `smart_folders` schema handling to `config_ops.read_config()`
2. Add `smart_folders` round-trip to `config_ops.save_config()`
3. Add validation for smart folder entries
4. Verify the API endpoint returns smart folders without additional changes

### 1B: Discovery Service

**Goal:** A service that scans source paths, matches glob patterns, cross-references
with declared modules, and returns a structured tree manifest.

**New file:** `src/core/services/smart_folders.py`

**API:**
```python
def discover(
    project_root: Path,
    sources: list[dict],      # [{"path": "src/", "pattern": "**/README.md"}]
) -> list[dict]:
    """Scan sources and return flat list of discovered doc files.

    Returns:
        [{"source_path": "src/core/services/chat/README.md",
          "relative_path": "core/services/chat/README.md",
          "module": "core",         # matched module name or None
          "module_relative": "services/chat/README.md",  # path relative to module root
          "size_bytes": 772,
          "modified": "2026-03-02T..."}]
    """

def resolve(
    project_root: Path,
    smart_folder: dict,       # smart folder config from project.yml
    modules: list[dict],      # modules from project.yml
) -> dict:
    """Resolve a smart folder into a module-grouped tree structure.

    Returns:
        {"name": "code-docs",
         "label": "Code Documentation",
         "target": "docs",
         "total_files": 89,
         "groups": [
           {"module": "core",
            "module_path": "src/core",
            "file_count": 35,
            "tree": {
              "name": "core",
              "children": [
                {"name": "services",
                 "children": [
                   {"name": "audit", "files": [{"name": "README.md", ...}]},
                   {"name": "chat", "files": [{"name": "README.md", ...}]},
                   {"name": "tool_install", "children": [...], "files": [...]},
                   ...
                 ],
                 "files": [
                   {"name": "README.md", ...},
                   {"name": "CROSS_CUTTING.md", ...}
                 ]}
              ]}},
           {"module": "cli", ...},
           {"module": "web", ...},
         ]}
    """
```

**Module matching logic:**
1. Load `modules` from `project.yml`
2. For each discovered file, find the module whose `path` is a prefix of the file's source path
3. Compute `module_relative` = file path relative to the module's `path`
4. Files not matching any module → group under "other"

**Tasks:**
1. Create `src/core/services/smart_folders.py`
2. Implement `discover()` — glob scanning with path matching
3. Implement `resolve()` — module grouping + tree building
4. Add API endpoint: `GET /api/smart-folders/<name>/tree` → calls `resolve()`
5. Add API endpoint: `GET /api/smart-folders/<name>/file?path=...` → reads file content from real location
6. Unit tests for discovery and resolution

---

## Phase 2: Wizard Integration (Content Step)

**Goal:** Step 4 (Content) shows a "Smart Folders" section where the user can
see discovered inner docs, configure smart folders, and save to `project.yml`.

### What to add to Wizard Step 4

Below the existing "Content Folders" and "Content Infrastructure" sections:

```
🔬 Smart Folders — Code Documentation

  Auto-detected: 89 README.md files across 3 modules (core, cli, web)

  ┌─────────────────────────────────────────────┐
  │ ☑ code-docs                                 │
  │   Label: Code Documentation                 │
  │   Target: docs (→ docs/code-docs/)          │
  │   Sources: src/ (**/README.md)              │
  │   Files: 89 across core (35), cli (19),     │
  │          web (35)                            │
  │                                    [⚙ Edit] │
  └─────────────────────────────────────────────┘

  [+ Add Smart Folder]
```

**Files to modify:**

| File | Change |
|------|--------|
| `src/ui/web/templates/scripts/wizard/_steps.html` | Add smart folders section to the `content` renderer |
| `src/ui/web/templates/scripts/wizard/_helpers.html` | Add helper functions for smart folder CRUD in wizard state |

**Tasks:**
1. Call `GET /api/smart-folders/discover` or equivalent to auto-detect
2. Render existing smart folders from config with summary stats
3. Add/edit/remove smart folder UI
4. Save smart folder config through existing wizard save flow
5. Preview: show file count per module group

---

## Phase 3: Content Browser — Smart Mode

**Goal:** Smart folders appear as virtual subfolders in the content browser
with module-aware tree navigation and a smart/raw toggle.

### Integration Points

1. **Folder listing** — When loading folder contents for a content folder (e.g. `docs/`),
   inject smart folder virtual entries alongside real files/directories
2. **Navigation** — When the user enters a smart folder, switch to smart mode:
   call the smart folder API instead of the regular content file listing API
3. **Toggle** — Show [🔬 Smart] [📁 Raw] toggle inside smart folders
4. **Preview** — Standard markdown preview, reading from real source location

**Backend changes:**

| File | Change |
|------|--------|
| `src/ui/web/routes/content/__init__.py` | Inject smart folder entries in folder listing when target matches |
| New or existing route | API endpoints for smart folder tree + file reading |

**Frontend changes:**

| File | Change |
|------|--------|
| `src/ui/web/templates/scripts/content/_browser.html` | Detect smart folder navigation, switch rendering mode |
| `src/ui/web/templates/scripts/content/_init.html` | Add smart folder state variables |
| `src/ui/web/templates/scripts/content/_nav.html` | Handle smart folder breadcrumbs |
| `src/ui/web/templates/scripts/content/_preview.html` | No change initially (standard markdown) |

**Tasks:**
1. Backend: Inject smart folder entries into content folder listing
2. Backend: Smart folder tree API endpoint
3. Backend: Smart folder file read endpoint (reads from real source path)
4. Frontend: Detect when entering a smart folder vs regular folder
5. Frontend: Render module-grouped tree in smart mode
6. Frontend: Smart/Raw toggle
7. Frontend: Breadcrumb adaptation for smart folder path
8. Frontend: Preview integration (route file read to real source location)

---

## Phase 4: Pages / Build Pipeline Integration

**Goal:** Smart folders participate in Docusaurus builds. When a segment is built,
its targeted smart folders are resolved and their contents injected into the
workspace before the build runs.

### How it works

1. Before `_stage_source` runs, check `project.yml` for smart folders
   targeting this segment's source content folder
2. After `_stage_source` copies the regular docs, resolve each matching
   smart folder and copy discovered files into `workspace/docs/<smart_folder_name>/`
3. The copied files go through the normal `_stage_transform` (MD → MDX)
4. The Docusaurus build picks them up naturally via autogenerated sidebar

**Standalone smart folders** (`target` = `name`): Create their own segment
entry. The builder treats the resolved smart folder output as the segment source.

### Files to modify

| File | Change |
|------|--------|
| `src/core/services/pages_builders/docusaurus.py` | After `_stage_source`, inject smart folder contents |
| `src/core/services/pages_engine.py` | Pass smart folder config to builder |
| `src/core/services/pages_discovery.py` | Smart folders can create auto-segments |

**Tasks:**
1. In `build_segment()`, load smart folders from config
2. Filter smart folders where `target` matches segment source
3. After `_stage_source`, call `smart_folders.resolve()` for each match
4. Copy resolved files into workspace under `docs/<name>/`
5. Generate index.md for each module group (auto-navigation)
6. Standalone mode: create segment from smart folder config
7. Test: build docs segment with smart folder injection, verify site has
   code-docs section with proper navigation

---

## Phase 5: Advanced Preview (analyze when we get there)

**Scope known, details TBD:**
- Module context header in preview
- Code reference detection in markdown content
- Inline code preview / glance into referenced source files
- Cross-module linking (when one README references another module)

---

## Phase 6: Multi-Level Adaptation (analyze when we get there)

**Scope known, details TBD:**
- Remark plugin for code doc references in Docusaurus MDX
- Admin panel enhancements for code documentation browsing
- CLI/TUI integration for code docs discovery and viewing
- Features adapted at each level to the nature of code documentation

---

## Execution Order Summary

```
Phase 1A: Data Model          ← foundation, everything depends on this
    ↓
Phase 1B: Discovery Service   ← the scanner, everything calls this
    ↓
Phase 2:  Wizard Step 4       ← configuration UI
    ↓
Phase 3:  Content Browser     ← browsing / viewing UI
    ↓
Phase 4:  Pages / Build       ← Docusaurus site generation
    ↓
Phase 5:  Advanced Preview    ← code glance, references (analyze then)
    ↓
Phase 6:  Multi-Level         ← remark, admin, CLI adaptation (analyze then)
```

Phases 1–4 are fully detailed above.
Phases 5–6 are scoped but will be analyzed in detail when we reach them.
Nothing is optional — everything is part of the final project.
