# Smart Folder Peek Panel — Implementation Plan (v2)

## Context & Relationship to Existing Peek

The **document peek** (`peek.py`) resolves cross-references within markdown documents
(e.g. file paths, symbols). It powers the inline reference tooltips in the preview panel.

The **smart folder peek** (this feature) is a SEPARATE concern: it provides a hover-triggered
expandable panel in the smart folder browser views — allowing users to preview documentation
content without navigating away from the browse view.

**Future connection**: Eventually, the document peek tooltips could call the smart folder peek
backend to enrich their tooltips with documentation context (not just "this file exists" but
"here's what it contains"). That's out of scope for now.

---

## Part 1: Verified Data Structures

### 1.1 Smart Folder Tree (from `/api/smart-folders/<name>/tree`)

The tree is accessed client-side via `_smartFolderTree.groups[]`.

```
group = {
    module: "core",              // module name
    module_path: "src/core",     // real filesystem path
    file_count: 26,              // total docs in this module
    tree: {                      // nested tree
        name: "core",
        files: [                 // root-level files
            {
                name: "README.md",
                source_path: "src/core/README.md",
                size_bytes: 4521,
                modified: "2026-02-..."
            }
        ],
        children: [              // sub-directories
            {
                name: "services",    // ← INTERMEDIATE (has 0 or 1 own files)
                files: [{ name: "README.md", source_path: "src/core/services/README.md" }],
                children: [
                    {
                        name: "audit",   // ← LEAF TOPIC
                        files: [{ name: "README.md", source_path: "src/core/services/audit/README.md" }],
                        children: []
                    },
                    { name: "chat", files: [...], children: [] },
                    // ... 22 more topics
                ]
            }
        ]
    }
}
```

### 1.2 Module Patterns (VERIFIED by curl)

| Module   | Root files | Children | Depth to topics | Pattern                    |
|----------|-----------|----------|----------------|----------------------------|
| adapters | README.md | 0        | 0 (flat)       | Root README only           |
| cli      | README.md | 19       | 1 (direct)     | root → 19 leaf topics      |
| core     | README.md | 1        | 2 (nested)     | root → services/ → topics  |
| web      | README.md | 2        | 2 (nested)     | root → routes/, templates/ |

**Key insight**: `core` and `web` have an intermediate directory level before the actual
topics are reached. The peek must handle this by walking down through intermediates.

### 1.3 API Response Contracts (VERIFIED by curl)

#### `/api/content/preview?path=<path>` — File content

```json
{
    "type": "markdown",
    "mime": "text/markdown",
    "content": "# Adapters\n\n> **10 files...",     // RAW MARKDOWN (not HTML!)
    "preview_content": "<h1>Adapters</h1>...",       // HTML with audit directives (OPTIONAL)
    "line_count": 245,
    "size": 8934,
    "truncated": false,
    "has_release": false,
    "release_status": "none",
    "release_orphaned": false
}
```

**Critical**: The field is `content` (raw markdown), NOT `html`.
The `preview_content` field exists only when audit directives are present.

#### `/api/content/outline?path=<path>` — Heading structure

```json
{
    "encrypted": false,
    "line_count": 708,
    "outline": [
        {
            "text": "Adapters",           // ← field is "text", NOT "label" or "name"
            "kind": "heading",
            "level": 1,
            "children": [                 // ← NESTED tree, NOT flat list!
                {
                    "text": "How It Works",
                    "kind": "heading",
                    "level": 2,
                    "children": [
                        { "text": "Data Flow", "kind": "heading", "level": 3, "children": [] }
                    ]
                },
                { "text": "File Map", "kind": "heading", "level": 2, "children": [] }
            ]
        }
    ]
}
```

**Critical**: The outline is a NESTED TREE. Items are inside `children[]`.
Must be FLATTENED to display. Only 1 top-level item per file (the H1).

#### `/api/content/peek-refs?path=<path>` — Cross-references

```json
{
    "references": [                       // ← field is "references", NOT "refs"
        {
            "text": "Receipt",
            "type": "T5",
            "resolved_path": "src/core/models/action.py",
            "line_number": 38,
            "is_directory": false
        }
    ],
    "unresolved": [{ "text": "...", "type": "T1" }],
    "pending": [...],
    "symbols_ready": true,
    "_source": "index"
}
```

---

## Part 2: Backend Endpoint

### Why a backend endpoint

The first attempt tried to make 2-3 parallel API calls from the frontend per peek.
This caused:
- Race conditions with panel lifecycle
- Wrong field name assumptions (no single source of truth)
- Concurrency pressure on the 3-slot API semaphore
- Complex error handling across multiple fetches

**Solution**: One backend endpoint that returns ALL peek data in one response.

### `GET /api/smart-folders/peek`

**Query parameters:**
- `module=<module_name>` — for module-level peek (e.g. `module=core`)
- `folder=<smart_folder_name>` — smart folder name (e.g. `folder=code-docs`)
- `topic=<topic_path>` — for topic-level peek (e.g. `topic=audit` or `topic=services/audit`)
  When present, `module` is also required.

**Response (module-level):**
```json
{
    "type": "module",
    "module": "core",
    "module_path": "src/core",
    "overview": {
        "text": "Domain models, services, and engine. The core package...",
        "source_path": "src/core/README.md",
        "line_count": 245,
        "size": 8934
    },
    "outline": [
        { "text": "Core", "level": 1 },
        { "text": "How It Works", "level": 2 },
        { "text": "Data Flow", "level": 3 },
        { "text": "File Map", "level": 2 },
        { "text": "Sub-Package Documentation", "level": 2 }
    ],
    "doc_tree": [
        {
            "name": "services",
            "has_doc": true,
            "source_path": "src/core/services/README.md",
            "children": [
                { "name": "audit", "has_doc": true, "source_path": "src/core/services/audit/README.md", "children": [] },
                { "name": "chat", "has_doc": true, "source_path": "src/core/services/chat/README.md", "children": [] }
            ]
        }
    ],
    "stats": {
        "total_docs": 26,
        "total_topics": 24,
        "depth": 2
    }
}
```

**Response (topic-level):**
```json
{
    "type": "topic",
    "module": "core",
    "topic": "audit",
    "topic_path": "services/audit",
    "preview_html": "<h1>Audit</h1><p>The audit service validates...",
    "preview_text": "The audit service validates tool configurations...",
    "outline": [
        { "text": "Audit", "level": 1 },
        { "text": "Overview", "level": 2 },
        { "text": "Configuration", "level": 2 }
    ],
    "sub_topics": [
        { "name": "reporters", "has_doc": true },
        { "name": "formatters", "has_doc": true }
    ],
    "references": [
        { "text": "run.py", "type": "T1", "resolved_path": "src/core/services/testing/run.py" }
    ],
    "source_path": "src/core/services/audit/README.md"
}
```

### Backend implementation

**File**: `src/ui/web/routes/smart_folders/peek.py` (new)  
or extend existing `src/ui/web/routes/smart_folders/browse.py`

**Logic**:
1. Load the smart folder tree (already cached by `/api/smart-folders/<name>/tree`)
2. Find the target group by module name
3. For module peek: walk the tree to find the root README, extract text, get outline
4. For topic peek: find the specific node in the tree, render its README,
   get outline, get peek-refs
5. Return all data in one response

**Key functions needed**:
- `_find_first_doc(node, max_depth)` — walk tree to find README (handles 2+ level deep)
- `_flatten_outline(outline_items, max_items)` — walk nested outline to flat list
- `_extract_overview_text(markdown_content, max_chars)` — strip markdown to plain text
- `_render_preview_html(markdown_content)` — render markdown to HTML for topic preview

---

## Part 3: Visual Design

### Module Peek Panel

```
┌───────────────────────────────────────────────────────────────┐
│ 📦 core   src/core                              26 topics    │  ← existing card
│   audit · chat · generators · vault                          │
├───────────────────────────────────────────────────────────────┤
│ ╔═══════════════════════════════════════════════════════════╗ │
│ ║                                                           ║ │
│ ║  📖 Overview                                              ║ │
│ ║  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄              ║ │
│ ║  Domain models, services, and engine. The core             ║ │
│ ║  package encapsulates all business logic behind a          ║ │
│ ║  service-layer pattern. Each service is a standalone       ║ │
│ ║  module with its own README documentation.                 ║ │
│ ║                                                           ║ │
│ ║  📋 Outline                         📂 Documentation Tree  ║ │
│ ║  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄              ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  ║ │
│ ║  Core                               services/              ║ │
│ ║    How It Works                        📖 audit             ║ │
│ ║      Data Flow                         📖 backup            ║ │
│ ║      Configuration                     📖 chat              ║ │
│ ║      Service Layer                     📖 ci                ║ │
│ ║    File Map                            📖 content           ║ │
│ ║    Sub-Package Docs                    📖 docker            ║ │
│ ║    Dependency Graph                    📖 dns               ║ │
│ ║    Consumers                           +17 more…            ║ │
│ ║                                                           ║ │
│ ║  ┄ 26 docs · 245 lines · src/core ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  ║ │
│ ╚═══════════════════════════════════════════════════════════╝ │
│ 📦 cli   src/ui/cli                              19 topics   │  ← next card
└───────────────────────────────────────────────────────────────┘
```

**Layout details:**
- Peek panel appears BELOW the card it belongs to
- Background: `var(--bg-card)`, subtle border, accent left border
- Overview sits at the top, full width
- Outline and Doc Tree are side-by-side in a 2-column layout (flex row)
- Stats line at the bottom, subtle/muted
- ALL sections have proper headings with subtle separator lines
- Content sections are separated visually — NOT stacked on top of each other

### Topic Peek Panel

```
┌───────────────────────────────────────────────────────────────┐
│ 📖 audit                                            Read →   │  ← existing entry
├───────────────────────────────────────────────────────────────┤
│ ╔═══════════════════════════════════════════════════════════╗ │
│ ║                                                           ║ │
│ ║  📖 Preview                                               ║ │
│ ║  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄              ║ │
│ ║  ┌─────────────────────────────────────────────────────┐  ║ │
│ ║  │ # Audit                                             │  ║ │
│ ║  │                                                     │  ║ │
│ ║  │ The audit service validates tool configurations     │  ║ │
│ ║  │ across 19 system presets. Each preset defines...    │  ║ │
│ ║  │                                                     │  ║ │
│ ║  │ ## How It Works                                     │  ║ │
│ ║  │ 1. Load preset from catalog                         │  ║ │  ← scrollable
│ ║  └────────────────────────── max-height: 200px ────────┘  ║ │
│ ║                                                           ║ │
│ ║  📋 Outline                         📂 Sub-topics          ║ │
│ ║  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄              ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  ║ │
│ ║  Audit                               📖 reporters          ║ │
│ ║    How It Works                       📖 formatters         ║ │
│ ║    Configuration                      📂 templates          ║ │
│ ║    Per-Tool Results                                        ║ │
│ ║    Consumers                                               ║ │
│ ║                                                           ║ │
│ ║  🔗 References (8)                                         ║ │
│ ║  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄              ║ │
│ ║  → src/core/services/testing/run.py                        ║ │
│ ║  → src/adapters/shell_adapter.py                           ║ │
│ ║  → executor.py                                             ║ │
│ ║  +5 more…                                                  ║ │
│ ║                                                           ║ │
│ ╚═══════════════════════════════════════════════════════════╝ │
│ 📖 backup                                          Read →   │  ← next entry
└───────────────────────────────────────────────────────────────┘
```

**Layout details:**
- Preview section: rendered markdown in a bordered, scrollable container (max-height 200px)
  Uses the SAME markdown rendering as the main preview panel (`md-content` class)
  Uses `preview_content` (HTML) when available, falls back to rendering `content` (raw md)
- Outline and Sub-topics: side-by-side 2-column layout
- References: full width below the 2-column section
- Each section has a heading and separator line
- Sections that have no data are simply not rendered (no empty states cluttering the panel)

---

## Part 4: Frontend Implementation

### CSS (admin.css)

```css
/* ── Smart Peek Panel ────────────────────────────── */
.smart-peek-panel {
    overflow: hidden;
    max-height: 0;
    opacity: 0;
    transition: max-height 0.35s ease-out, opacity 0.25s ease-out;
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-left: 3px solid var(--accent);
    border-radius: 0 0 10px 10px;
    margin-top: -2px;
    margin-bottom: 0.5rem;
}

.smart-peek-panel.open {
    opacity: 1;
    /* max-height set dynamically based on content */
}

.smart-peek-inner {
    padding: 0.75rem 1rem;
    font-size: 0.82rem;
}

.smart-peek-section {
    margin-bottom: 0.6rem;
}

.smart-peek-section-title {
    font-weight: 600;
    font-size: 0.78rem;
    color: var(--text-muted);
    margin-bottom: 0.35rem;
    padding-bottom: 0.2rem;
    border-bottom: 1px solid var(--border-subtle);
}

.smart-peek-columns {
    display: flex;
    gap: 1.2rem;
}

.smart-peek-column {
    flex: 1;
    min-width: 0;
}

.smart-peek-preview-box {
    max-height: 200px;
    overflow-y: auto;
    border: 1px solid var(--border-subtle);
    border-radius: 6px;
    padding: 0.6rem;
    background: var(--bg-inset);
    font-size: 0.8rem;
    line-height: 1.5;
}

.smart-peek-stats {
    font-size: 0.72rem;
    color: var(--text-muted);
    padding-top: 0.4rem;
    border-top: 1px solid var(--border-subtle);
    text-align: right;
}

.smart-peek-outline-item {
    font-size: 0.75rem;
    color: var(--text-secondary);
    padding: 0.05rem 0;
}

.smart-peek-tree-item {
    font-size: 0.78rem;
    padding: 0.1rem 0.3rem;
    cursor: pointer;
    border-radius: 4px;
    color: var(--text-secondary);
}

.smart-peek-tree-item:hover {
    background: var(--accent-glow);
}

.smart-peek-ref {
    font-size: 0.72rem;
    color: var(--accent);
    padding: 0.05rem 0;
}
```

### JavaScript Functions (in `_smart_folders.html`)

#### Global state
```javascript
// In _init.html:
let _smartPeekState = null;  // { element, panel, hoverTimer, dismissTimer }
```

#### Helper: Find first doc in tree

```javascript
function _smartPeekFindDoc(node, maxDepth) {
    // Returns { source_path, name } or null
    // Handles the 2+ level deep case (core → services → audit → README.md)
    if (!node || maxDepth < 0) return null;
    if (node.files && node.files.length > 0) return node.files[0];
    for (const child of (node.children || [])) {
        const found = _smartPeekFindDoc(child, maxDepth - 1);
        if (found) return found;
    }
    return null;
}
```

#### Core: Open/Close/Dismiss cycle

```javascript
function _smartPeekClose() { ... }       // Remove panel, clear timers
function _smartPeekStartDismiss() { ... } // 300ms grace period
function _smartPeekCancelDismiss() { ... } // Mouse re-entered
function _smartPeekOpen(el, mode, data, sf) { ... }
    // 1. Close any existing peek
    // 2. Create panel DOM with .smart-peek-panel class
    // 3. Insert after trigger element
    // 4. Add mouse handlers on panel (enter → cancel dismiss, leave → start dismiss)
    // 5. Animate open (requestAnimationFrame → add .open class)
    // 6. Fetch data from backend: GET /api/smart-folders/peek?...
    // 7. On response: render content into panel
```

#### Render: Module peek content

```javascript
function _smartPeekRenderModule(container, data) {
    // data = response from /api/smart-folders/peek (type=module)
    //
    // Section 1: Overview (full width)
    //   data.overview.text → plain text excerpt
    //
    // Section 2: 2-column layout
    //   Left: Outline (data.outline → flat list with indentation by level)
    //   Right: Doc Tree (data.doc_tree → nested clickable entries)
    //
    // Section 3: Stats line
    //   data.stats.total_docs, data.stats.depth
}
```

#### Render: Topic peek content

```javascript
function _smartPeekRenderTopic(container, data) {
    // data = response from /api/smart-folders/peek (type=topic)
    //
    // Section 1: Preview (full width, scrollable)
    //   data.preview_html → rendered markdown in .smart-peek-preview-box
    //
    // Section 2: 2-column layout
    //   Left: Outline (data.outline → flat list)
    //   Right: Sub-topics (data.sub_topics → list with icons)
    //
    // Section 3: References (full width)
    //   data.references → list of linked paths
}
```

#### Hover attachment

```javascript
function _smartPeekAttachHover(el, mode, data, sf) {
    // mouseenter → start 1500ms timer
    // mouseleave → cancel timer OR start dismiss if peek is open
    // Uses event listeners (NOT inline handlers) attached AFTER innerHTML render
}
```

### Attach in existing render functions

In `_smartFolderRenderModules`: after `browserEl.innerHTML = html`, query for
cards and call `_smartPeekAttachHover(card, 'module', group, sf)`.

In `_smartFolderRenderDocTree` / `_smartFolderRenderTocEntries`: after
`browserEl.innerHTML = html`, query for entries and call
`_smartPeekAttachHover(entry, 'topic', nodeData, sf)`.

Cards and entries need `data-peek-*` attributes for post-render querying.

---

## Part 5: Implementation Order

### Step 1: Backend endpoint
- Create `GET /api/smart-folders/peek`
- Reuse existing `extract_outline`, preview reading, peek-refs logic
- One response with everything the panel needs
- Test with curl before touching frontend

### Step 2: CSS classes
- Add all `.smart-peek-*` classes to `admin.css`
- Proper layout rules, transitions, responsive behavior
- Test: just verify classes exist, no visual test yet

### Step 3: JS core engine (open/close/dismiss)
- Add `_smartPeekState` to `_init.html`
- Add `_smartPeekOpen`, `_smartPeekClose`, `_smartPeekStartDismiss`,
  `_smartPeekCancelDismiss` to `_smart_folders.html`
- These just create/remove the DOM panel — no content rendering yet
- Use CSS classes (not inline styles) for the panel

### Step 4: JS render functions
- `_smartPeekFindDoc` helper
- `_smartPeekRenderModule` — reads backend response, builds HTML sections
- `_smartPeekRenderTopic` — same for topic level
- Uses proper section layout with CSS classes

### Step 5: Attach hover handlers
- Modify `_smartFolderRenderModules` to add data attributes + post-render attachment
- Modify `_smartFolderRenderTocEntries` to add data attributes + post-render attachment
- Test: hover should trigger the full flow

### Step 6: Polish
- Progressive loading (spinner → content fade-in)
- Edge cases (no README, very long content, viewport overflow)
- Performance (cancel in-flight fetch if user moves away)

---

## Part 6: Edge Cases

### No README at any depth
- Module peek: Show doc tree only + "No documentation overview" in muted text
- Topic peek: Show sub-topics only + "No documentation available"

### Flat module (adapters: 0 children)
- Module peek: show overview + outline only, NO doc tree section (don't render empty section)

### Multi-level intermediate dirs (core → services → topics)
- `_smartPeekFindDoc(tree, 3)` with maxDepth=3 handles up to 3 levels deep
- Doc tree renders the full tree including intermediates

### Very long README
- Preview is in a scrollable container (max-height 200px)
- Overview text is truncated to ~300 chars

### Rapid hover events
- Only ONE peek panel at a time
- Opening a new peek immediately closes the previous one
- 1500ms timer is cancelled on mouseleave, preventing phantom panels

### Panel near viewport bottom
- Panel has max-height constraint (won't overflow page)
- If content is shorter than max, panel fits content naturally

### User clicks during peek
- Click on the card/entry navigates normally (peek doesn't interfere)
- Click inside the peek panel on a tree item: close peek + navigate
- Two separate concerns: hover → peek, click → navigate

### Smart folder tree not loaded
- Guard: `if (!_smartFolderTree) return;` — shouldn't happen but defensive

---

## Part 7: Data Flow Summary

### Module card peek
```
User hovers module card for 1.5s
  → _smartPeekOpen(cardElement, 'module', group, sf)
    → Create panel DOM with spinner
    → Single fetch: GET /api/smart-folders/peek?folder=code-docs&module=core
    → Backend:
        1. Load tree from smart folder tree cache
        2. Find root README via _find_first_doc(tree, 3)
        3. Read file, extract plain text overview (~300 chars)
        4. Extract outline (flatten nested headings)
        5. Build doc_tree from tree children
        6. Return all in one response
    → Frontend:
        1. Check panel still exists (user may have moved away)
        2. Render overview (full width)
        3. Render outline + doc tree (2-column)
        4. Render stats line
        5. Transition: spinner → content fade-in
```

### ToC entry peek
```
User hovers ToC entry for 1.5s
  → _smartPeekOpen(entryElement, 'topic', { node, parentPath }, sf)
    → Create panel DOM with spinner
    → Single fetch: GET /api/smart-folders/peek?folder=code-docs&module=cli&topic=audit
    → Backend:
        1. Load tree, find module group, find topic node
        2. Find README via _find_first_doc(node, 3)
        3. Render markdown to HTML (for preview)
        4. Extract outline (flatten)
        5. Get sub_topics from node.children
        6. Get peek-refs from existing peek service
        7. Return all in one response
    → Frontend:
        1. Check panel still exists
        2. Render preview (scrollable markdown container)
        3. Render outline + sub-topics (2-column)
        4. Render references (full width)
        5. Transition: spinner → content fade-in
```

---

## Part 8: Mistakes From v1 (Lessons Learned)

| What went wrong | Root cause | How v2 fixes it |
|----------------|-----------|-----------------|
| `previewData.html` — field doesn't exist | Never read the API handler | Backend returns exactly what frontend needs |
| `item.label` — field is `item.text` | Never curled the API | Backend flattens outline, returns `text` directly |
| `refsData.refs` — field is `references` | Guessed field names | Backend normalizes into `references` |
| Outline was 1 item (nested) | Assumed flat list | Backend flattens the nested tree |
| CLI showed tree but no async | Phase 1 error blocked Phase 2 | Single fetch, no phased rendering |
| Multiple parallel API calls | Frontend-only approach | One backend call returns everything |
| Stacked inline styles | No CSS classes | Proper `.smart-peek-*` CSS classes |
| Sections piled on top of each other | No layout structure | 2-column flex layout with section dividers |
