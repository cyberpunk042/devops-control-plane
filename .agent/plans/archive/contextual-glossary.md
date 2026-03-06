# Contextual Glossary & Outline Panel — Full Feature Plan

**Status**: APPROVED — decisions resolved, ready for implementation  
**Stage**: Stage 1 (Markdown + Python + Panel + Sync)  
**Stage 2 plan**: `.agent/plans/contextual-glossary-stage2.md` (all remaining languages)  
**Complexity**: Large evolution (new panel, new API, new service, cross-cutting feature)


## 1. Problem Statement

The Content Vault currently shows files as a flat grid. When viewing a file,
you see its content but have zero structural overview:

- **No outline** — opening a 300-line Python file, you can't see its classes
  and functions at a glance
- **No cross-file navigation** — can't see the relationship between documents
  in a folder without going back to the grid
- **No position awareness** — scrolling through a long markdown or code file,
  no indication of which section you're in
- **No heading-level browsing** — markdown files have structure (h2, h3, h4)
  that's invisible until you scroll past it
- **No code structure browsing** — Python files have classes, functions, methods
  that define the architecture but you can't see them without reading every line
- **Context switching cost** — to find a section in another file, you must close
  the current preview, navigate, open, scroll
- **Smart folders underutilize structure** — they group by module but don't show
  what's inside each file (headings, symbols)

Docusaurus auto-generates a sidebar but it requires config, doesn't show inside-file
structure, doesn't sync with scroll, and doesn't work for code.


## 2. Vision

A **collapsible, resizable sidebar panel** that provides structural awareness
for ALL file types and ALL view modes. It adapts its content extraction to the
file type being viewed.

### Two Modes — User's Choice

The panel has **two display modes**, toggled by the user:

| Mode | Button | Shows | Best For |
|------|--------|-------|----------|
| **Outline** | `📋 Outline` | Current file's internal structure only (headings, classes, functions) | Deep focus on a single file — code editing, reading long docs |
| **Glossary** | `📚 Glossary` | Full folder tree with all files and their internal structure | Browsing, cross-file navigation, discovering structure |

- The mode toggles are two buttons in the panel header (not the toolbar)
- The panel itself is toggled on/off via a single button in the toolbar
- Default mode: **Glossary** when browsing folders, **Outline** when viewing a file
- User's choice is persisted via `localStorage` key `glossary-panel-mode`

### Visibility Default

- **Starts visible** on first visit (default = open)
- User can close it; choice persisted to `localStorage` key `glossary-panel-visible`
- Persists across sessions (not just session — `localStorage`)

### 2.1. When Viewing a Folder — Glossary Mode (default)

```
┌──────────────────────┬──────────────────────────────────────────┐
│ [📋 Outline][📚 Gloss]│  📁 docs/ — 12 files                    │
│ ┌─ 🔍 filter... ─┐   │                                          │
│                      │  ┌─────────┐ ┌──────────┐ ┌──────────┐  │
│ ▼ docs/              │  │ ADAPT..  │ │ ANALY..  │ │ README   │  │
│   ▼ ADAPTERS.md 8KB  │  └─────────┘ └──────────┘ └──────────┘  │
│     ├ Overview       │  ┌─────────┐ ┌──────────┐               │
│     ├ Architecture   │  │ DEPLOY.. │ │ SETUP..  │               │
│     │ ├ Registry     │  └─────────┘ └──────────┘               │
│     │ └ Lazy Load    │                                          │
│     ├ Adapters       │                                          │
│     └ Testing        │                                          │
│   ▷ ANALYSIS.md 3KB  │                                          │
│   ▷ README.md   2KB  │                                          │
│   🔐 secrets.md.enc  │                                          │
│   🖼 diagram.png 45K │                                          │
│   🎵 narration.mp3   │                                          │
│                      │                                          │
│ ▷ src/adapters/      │                                          │
│   ▷ registry.py 5KB  │                                          │
│     ├ AdapterReg (C) │                                          │
│     ├ register   (F) │                                          │
│     └ load       (F) │                                          │
└──────────────────────┴──────────────────────────────────────────┘
       File sizes shown inline. Non-text files as leaves.
```

### 2.2. When Viewing a File — Outline Mode (auto-switches)

When a file is opened, the panel auto-switches to **Outline mode**:

```
┌──────────────────────┬──────────────────────────────────────────┐
│ [📋 Outline][📚 Gloss]│  📖 docs/ADAPTERS.md  [Preview|Raw|Edit] │
│ ┌─ 🔍 filter... ─┐   │                                          │
│                      │  # Adapters                               │
│ ADAPTERS.md (8KB)    │                                           │
│ ├ Overview       ●←  │  The adapter layer provides pluggable...  │
│ ├ Architecture       │                                           │
│ │ ├ Registry         │  ## Architecture                          │
│ │ └ Lazy Load        │                                           │
│ ├ Adapters           │  The registry pattern allows each adapter │
│ └ Testing            │  to self-register via...                  │
│                      │                                           │
└──────────────────────┴──────────────────────────────────────────┘
             ● = currently tracked heading (scroll sync)
             No other files shown — pure single-file focus.
```

User can switch to **Glossary mode** while viewing a file to see sibling files:

```
│ [📋 Outline][📚 Gloss]│
│ ┌─ 🔍 filter... ─┐   │
│                      │
│ ▼ ADAPTERS.md ●  8KB │  ← current file highlighted
│   ├ Overview     ●←  │
│   ├ Architecture     │
│   │ ├ Registry       │
│   │ └ Lazy Load      │
│   ├ Adapters         │
│   └ Testing          │
│ ▷ ANALYSIS.md    3KB │
│ ▷ README.md      2KB │
│ 🔐 secrets.md.enc   │
│ 🖼 diagram.png   45K │
└──────────────────────┘
```

### 2.3. When Viewing a Code File

```
┌──────────────────────┬──────────────────────────────────────────┐
│ 📋 Outline           │  📄 src/adapters/registry.py  [Raw|Edit] │
│ ┌─ 🔍 filter... ─┐   │                                          │
│                      │  """                                      │
│ registry.py          │  Adapter registry — lazy-loading service. │
│ ├─ 📦 Imports    3   │  """                                      │
│ ├─ ⚙ REGISTRY   12  │                                           │
│ ▼ 🟦 AdapterReg  18  │  import logging                           │
│ │ ├ __init__     22  │  from pathlib import Path                 │
│ │ ├ register  ●← 45  │  from typing import Any                   │
│ │ ├ get          67  │                                           │
│ │ └ load_all     89  │  REGISTRY: dict[str, Any] = {}            │
│ ├─ 🟨 register  112  │                                           │
│ ├─ 🟨 discover  134  │  class AdapterRegistry:                   │
│ └─ 🟨 _resolve  156  │      """Central registry for adapters.""" │
│                      │                                           │
│ ─── Other files ──── │                                           │
│ ▷ base.py            │                                           │
│ ▷ __init__.py        │                                           │
└──────────────────────┴──────────────────────────────────────────┘
      🟦 = class, 🟨 = function, ⚙ = constant, 📦 = import block
```

### 2.4. When Viewing an Encrypted File

```
│ 🔐 secrets.md.enc   │
│   (encrypted — open  │
│    to see outline)   │
```

Encrypted files appear in the glossary tree as leaf nodes. No structure extraction
(would require the key). Click to open the file which triggers the decrypt flow.

### 2.5. When Viewing a Smart Folder (Code Browser)

```
┌──────────────────────┬──────────────────────────────────────────┐
│ 📋 Outline           │  📖 Code Docs — Browse by Module         │
│ ┌─ 🔍 filter... ─┐   │                                          │
│                      │  ┌──────────────────────────────────────┐ │
│ ▼ 📦 core            │  │ 📦 core — src/core/                  │ │
│   ▼ services/        │  │    12 documentation topics            │ │
│     ▼ chat/          │  │    chat · config · content · packages │ │
│       README.md      │  └──────────────────────────────────────┘ │
│       ├ Overview     │  ┌──────────────────────────────────────┐ │
│       ├ Protocol     │  │ 📦 adapters — src/adapters/           │ │
│       └ Storage      │  │    6 documentation topics             │ │
│     ▷ config/        │  └──────────────────────────────────────┘ │
│     ▷ content/       │  ┌──────────────────────────────────────┐ │
│   ▷ models/          │  │ 📦 web — src/ui/web/                  │ │
│ ▼ 📦 adapters        │  │    3 documentation topics             │ │
│   ▷ README.md        │  └──────────────────────────────────────┘ │
│ ▷ 📦 web             │                                          │
└──────────────────────┴──────────────────────────────────────────┘
```


## 3. Architecture

### 3.1. Multi-Strategy Outline Extraction

The core innovation: a **strategy-based outline extractor** that adapts to
file type. Each strategy returns the same data shape regardless of source:

```python
# Universal outline node
{
    "text": "AdapterRegistry",        # display text
    "kind": "class",                  # type of symbol
    "line": 18,                       # 1-indexed source line
    "children": [                     # nested symbols
        {"text": "__init__", "kind": "method", "line": 22, "children": []},
        {"text": "register",  "kind": "method", "line": 45, "children": []},
    ]
}
```

**Strategies by file type**:

| File Type | Strategy | Extraction Method | Symbols Extracted |
|-----------|----------|-------------------|-------------------|
| `.md` | MarkdownStrategy | Regex `^#{1,6}\s+(.+)$` | h1, h2, h3, h4, h5, h6 (nested by level) |
| `.py` | PythonStrategy | `ast.parse()` | classes, functions, methods, constants |
| `.js`, `.ts`, `.jsx`, `.tsx` | JavaScriptStrategy | Regex-based | classes, functions, arrow functions, exports |
| `.go` | GoStrategy | Regex-based | functions, types, methods |
| `.rs` | RustStrategy | Regex-based | fn, struct, impl, enum, trait |
| `.html` | HTMLStrategy | Regex-based | `<h1>`-`<h6>`, `<section>`, `id=` attributes |
| `.css`, `.scss` | CSSStrategy | Regex-based | Section comments, @media, @keyframes |
| `.yaml`, `.yml` | YAMLStrategy | Top-level keys | Top-level mapping keys as sections |
| `.json` | JSONStrategy | Top-level keys | Top-level object keys as sections |
| `.toml` | TOMLStrategy | `[section]` headers | Tables/sections |
| `.sh`, `.bash` | ShellStrategy | Regex-based | functions |
| `.sql` | SQLStrategy | Regex-based | CREATE TABLE, CREATE VIEW, functions |
| `.enc` | EncryptedStrategy | None | Returns `{"encrypted": true}` — no extraction |
| default | FallbackStrategy | None | Empty outline — file listed as leaf |

**Implementation priority**: Stage 1 ships with Markdown + Python + Encrypted +
Fallback. Stage 2 adds all remaining languages. The strategy pattern makes
adding new languages trivial — each is a self-contained class with zero coupling.
See `.agent/plans/contextual-glossary-stage2.md` for the full Stage 2 plan.

#### Python Strategy Detail (AST-based)

Python is the primary language of this project. Using `ast.parse()` gives us
precise, reliable extraction with zero regex fragility:

```python
import ast

def extract_python_outline(source: str) -> list[dict]:
    """Extract classes, functions, methods, and constants from Python source."""
    tree = ast.parse(source)
    outline = []
    
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            methods = []
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append({
                        "text": child.name,
                        "kind": "method",
                        "line": child.lineno,
                        "children": [],
                    })
            outline.append({
                "text": node.name,
                "kind": "class",
                "line": node.lineno,
                "children": methods,
            })
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            outline.append({
                "text": node.name,
                "kind": "function",
                "line": node.lineno,
                "children": [],
            })
        elif isinstance(node, ast.Assign):
            # Top-level constants: MY_CONST = ...
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    outline.append({
                        "text": target.id,
                        "kind": "constant",
                        "line": node.lineno,
                        "children": [],
                    })
    
    return outline
```

**Performance**: `ast.parse()` is fast (Python stdlib). A 500-line file parses
in < 5ms. Even 50 files = < 250ms. Caching makes repeat requests instant.

#### JavaScript/TypeScript Strategy Detail (Regex-based)

Since we don't bundle a JS parser in a Python backend, we use robust regex
patterns that handle the common cases:

```python
import re

_JS_PATTERNS = [
    # class Foo { / class Foo extends Bar {
    (re.compile(r'^(?:export\s+)?class\s+(\w+)'), 'class'),
    # function foo(...) { / async function foo(...)
    (re.compile(r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)'), 'function'),
    # const foo = (...) => / const foo = function
    (re.compile(r'^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\(|function)'), 'function'),
    # export default function / export default class
    (re.compile(r'^export\s+default\s+(?:async\s+)?function\s+(\w+)'), 'function'),
    (re.compile(r'^export\s+default\s+class\s+(\w+)'), 'class'),
]
```

This doesn't handle every edge case but covers 95% of real-world code. It's
fast, has no dependencies, and is easy to maintain.


### 3.2. API Design

#### 3.2.1. File Outline Endpoint

```
GET /api/content/outline?path=<file_path>
```

Returns the outline for a single file. Used when previewing a file.

**Response** (markdown file):
```json
{
    "path": "docs/ADAPTERS.md",
    "type": "markdown",
    "line_count": 245,
    "outline": [
        {"text": "Adapters", "kind": "heading", "level": 1, "line": 1, "children": [
            {"text": "Overview", "kind": "heading", "level": 2, "line": 5, "children": []},
            {"text": "Architecture", "kind": "heading", "level": 2, "line": 42, "children": [
                {"text": "Registry Pattern", "kind": "heading", "level": 3, "line": 58, "children": []},
                {"text": "Lazy Loading", "kind": "heading", "level": 3, "line": 89, "children": []}
            ]},
            {"text": "Available Adapters", "kind": "heading", "level": 2, "line": 112, "children": []},
            {"text": "Testing", "kind": "heading", "level": 2, "line": 200, "children": []}
        ]}
    ]
}
```

**Response** (Python file):
```json
{
    "path": "src/adapters/registry.py",
    "type": "python",
    "line_count": 180,
    "outline": [
        {"text": "REGISTRY", "kind": "constant", "line": 12, "children": []},
        {"text": "AdapterRegistry", "kind": "class", "line": 18, "children": [
            {"text": "__init__", "kind": "method", "line": 22, "children": []},
            {"text": "register", "kind": "method", "line": 45, "children": []},
            {"text": "get", "kind": "method", "line": 67, "children": []},
            {"text": "load_all", "kind": "method", "line": 89, "children": []}
        ]},
        {"text": "register", "kind": "function", "line": 112, "children": []},
        {"text": "discover", "kind": "function", "line": 134, "children": []},
        {"text": "_resolve", "kind": "function", "line": 156, "children": []}
    ]
}
```

**Response** (encrypted file):
```json
{
    "path": "docs/secrets.md.enc",
    "type": "encrypted",
    "line_count": null,
    "encrypted": true,
    "original_name": "secrets.md",
    "outline": null
}
```

#### 3.2.2. Folder Glossary Endpoint

```
GET /api/content/glossary?path=<folder_path>&recursive=<bool>
```

Returns the outline for ALL files in a folder. Used when viewing a folder
listing (so the sidebar can show cross-file structure).

**Response**:
```json
{
    "path": "docs",
    "total_files": 12,
    "entries": [
        {
            "name": "ADAPTERS.md",
            "path": "docs/ADAPTERS.md",
            "is_dir": false,
            "type": "markdown",
            "line_count": 245,
            "outline": [...]
        },
        {
            "name": "examples",
            "path": "docs/examples",
            "is_dir": true,
            "children": [
                {
                    "name": "quickstart.md",
                    "path": "docs/examples/quickstart.md",
                    "is_dir": false,
                    "type": "markdown",
                    "line_count": 89,
                    "outline": [...]
                }
            ]
        },
        {
            "name": "secrets.md.enc",
            "path": "docs/secrets.md.enc",
            "is_dir": false,
            "type": "encrypted",
            "encrypted": true,
            "original_name": "secrets.md",
            "outline": null
        }
    ]
}
```

**Performance guards**:
- Max 200 files per request (configurable via `?limit=N`)
- Max 512 KB per file for outline extraction
- In-memory LRU cache: key = `(folder_path, max_mtime)`, TTL = 60s
- Parallel extraction with `concurrent.futures.ThreadPoolExecutor(max_workers=4)`
- Expected response time: < 100ms for typical projects (10-50 files)
- Python AST parsing: < 5ms per file
- Markdown regex: < 1ms per file

#### 3.2.3. Smart Folder Glossary Extension

```
GET /api/content/glossary?smart_folder=<name>
```

When `smart_folder` is provided, the endpoint uses the smart folder's resolved
tree (`sf.resolve()`) instead of raw directory walking. Groups files by module,
same hierarchy as the smart folder tree response. Heading/symbol extraction
works the same way — reads real source files by `source_path`.

```json
{
    "path": "code-docs",
    "smart_folder": "code-docs",
    "total_files": 28,
    "groups": [
        {
            "module": "core",
            "module_path": "src/core",
            "entries": [
                {
                    "name": "README.md",
                    "path": "src/core/README.md",
                    "is_dir": false,
                    "type": "markdown",
                    "outline": [...]
                },
                {
                    "name": "services",
                    "path": "src/core/services",
                    "is_dir": true,
                    "children": [...]
                }
            ]
        }
    ]
}
```


### 3.3. Backend Service Layer

**New file**: `src/core/services/content/outline.py`

This service contains:
1. The strategy interface and implementations
2. The outline extraction dispatcher
3. The folder glossary builder
4. The caching layer

```
src/core/services/content/outline.py
├── extract_outline(file_path, content=None) -> dict
│   ├── Dispatches to appropriate strategy
│   ├── Uses content if provided (avoids re-read)
│   └── Returns normalized outline dict
│
├── extract_folder_glossary(folder_path, recursive=False) -> dict
│   ├── Walks folder, calls extract_outline for each file
│   ├── Builds nested tree matching folder hierarchy
│   └── Parallel extraction for performance
│
├── MarkdownOutlineStrategy
├── PythonOutlineStrategy
├── JavaScriptOutlineStrategy
├── FallbackOutlineStrategy
├── EncryptedOutlineStrategy
└── (future: Go, Rust, YAML, etc.)
```

**New file**: `src/ui/web/routes/content/outline.py`

Flask route handlers that call into the service:
- `GET /api/content/outline?path=<file>` → `extract_outline()`
- `GET /api/content/glossary?path=<folder>` → `extract_folder_glossary()`
- `GET /api/content/glossary?smart_folder=<name>` → smart folder variant


### 3.4. Client-Side Architecture

**New file**: `src/ui/web/templates/scripts/content/_glossary.html`

```
_glossary.html
├── State Variables
│   ├── _glossaryVisible        (panel open/closed)
│   ├── _glossaryData           (cached API response)
│   ├── _glossaryPath           (folder the glossary is for)
│   ├── _glossaryExpanded       (which tree nodes are expanded)
│   ├── _glossaryActiveFile     (currently viewed file path)
│   └── _glossaryActiveLine     (tracked line from _contentFocusLine)
│
├── Panel Control
│   ├── contentToggleGlossary() (show/hide the panel)
│   └── _glossaryResize()       (handle panel resize)
│
├── Data Loading
│   ├── _glossaryLoadFolder(folderPath) (load folder glossary from API)
│   ├── _glossaryLoadFile(filePath)     (load single file outline from API)
│   └── _glossaryLoadSmartFolder(name)  (load smart folder glossary from API)
│
├── Tree Rendering
│   ├── _glossaryRenderTree(data)       (build the tree DOM)
│   ├── _glossaryRenderNode(node, depth)(render a single tree node)
│   ├── _glossaryToggleNode(nodeId)     (expand/collapse)
│   └── _glossaryRenderSearch(query)    (filter tree by search text)
│
├── Active State Sync
│   ├── _glossaryUpdateActive(filePath, line)  (highlight current heading)
│   ├── _glossaryScrollToActive()              (scroll panel to visible)
│   └── _glossaryAutoExpand(filePath)          (expand parent of active node)
│
└── Navigation
    ├── _glossaryNavigateToFile(path)          (click file → open preview)
    └── _glossaryNavigateToLine(path, line)    (click heading → open at line)
```


## 4. UI Design Detail

### 4.1. Toggle Button

Add **📋 Outline** button in the content folder bar action row,
next to 🔄 Refresh and 🗂 Show All Folders:

```html
<button class="btn btn-sm" id="content-glossary-btn"
    onclick="contentToggleGlossary()"
    title="Toggle document outline sidebar (Ctrl+Shift+O)"
    style="...same as explore-all-btn styles...">📋 Outline</button>
```

Active state: same `.active` styling as the Explore All button.

### 4.2. Panel Layout

The `.card.full-width` container (parent of `content-browser`) gets a flexbox
layout when the glossary is open:

```
┌──── .card.full-width ─────────────────────────────────────┐
│ ┌────── #content-glossary-panel ──┐ ┌── #content-browser ─┐│
│ │  width: 260px                   │ │  flex: 1             ││
│ │  resize: horizontal             │ │  min-width: 0        ││
│ │  max-width: 340px               │ │                      ││
│ │  border-right: 1px solid border │ │                      ││
│ │  overflow-y: auto               │ │                      ││
│ └─────────────────────────────────┘ └──────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

**Panel HTML structure**:
```html
<div id="content-glossary-panel" style="display:none">
    <div class="glossary-header">
        <span class="glossary-title">📋 Outline</span>
        <input type="text" class="glossary-search" placeholder="🔍 Filter..."
               oninput="_glossaryFilter(this.value)">
    </div>
    <div class="glossary-tree" id="glossary-tree">
        <!-- Tree nodes rendered here -->
    </div>
</div>
```

**Responsive (< 768px)**: Panel renders as a full-width collapsible section
ABOVE the content browser (stacked, not side-by-side). Toggle becomes
an accordion to save space on mobile.

### 4.3. Panel CSS

```css
#content-glossary-panel {
    width: 260px;
    min-width: 200px;
    max-width: 380px;
    flex-shrink: 0;
    border-right: 1px solid var(--border-subtle);
    overflow-y: auto;
    overflow-x: hidden;
    padding: 0;
    font-size: 0.82rem;
    max-height: 70vh;
    resize: horizontal;
    scrollbar-width: thin;
    transition: width 0.2s ease;
}

.glossary-header {
    padding: 0.5rem 0.6rem;
    border-bottom: 1px solid var(--border-subtle);
    position: sticky;
    top: 0;
    background: var(--bg-card);
    z-index: 1;
}

.glossary-title {
    font-weight: 600;
    font-size: 0.78rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.glossary-search {
    width: 100%;
    margin-top: 0.4rem;
    padding: 0.25rem 0.5rem;
    border: 1px solid var(--border-subtle);
    border-radius: 6px;
    background: var(--bg-inset);
    color: var(--text-primary);
    font-size: 0.78rem;
    outline: none;
    transition: border-color 0.15s;
}
.glossary-search:focus {
    border-color: var(--accent);
}

.glossary-tree {
    padding: 0.3rem 0;
}

/* ── Tree node styles ──────────────────────────────────────── */

.glossary-node {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.2rem 0.5rem;
    cursor: pointer;
    border-radius: 4px;
    transition: background 0.1s;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    user-select: none;
    line-height: 1.5;
}
.glossary-node:hover {
    background: var(--bg-tertiary);
}
.glossary-node.active {
    background: var(--accent-glow);
    color: var(--accent);
    font-weight: 600;
}
.glossary-node.active-heading {
    border-left: 3px solid var(--accent);
    background: rgba(59, 130, 246, 0.08);
}

.glossary-node__arrow {
    width: 14px;
    flex-shrink: 0;
    text-align: center;
    font-size: 0.65rem;
    color: var(--text-muted);
}
.glossary-node__icon {
    flex-shrink: 0;
    font-size: 0.75rem;
}
.glossary-node__text {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
}
.glossary-node__line {
    flex-shrink: 0;
    font-size: 0.65rem;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
}
.glossary-node__kind {
    flex-shrink: 0;
    font-size: 0.58rem;
    padding: 0 0.25rem;
    border-radius: 3px;
    background: var(--bg-inset);
    color: var(--text-muted);
    border: 1px solid var(--border-subtle);
}

.glossary-children {
    margin-left: 0.8rem;
}
.glossary-children.collapsed {
    display: none;
}
```

### 4.4. Icon System

Consistent iconography for each symbol kind:

| Kind | Icon | Color intent |
|------|------|-------------|
| folder | 📁 | neutral |
| file (md) | 📝 | neutral |
| file (py) | 🐍 | neutral |
| file (js/ts) | 📜 | neutral |
| file (other code) | 📄 | neutral |
| file (encrypted) | 🔐 | warning |
| heading (h1) | — | bold |
| heading (h2) | — | normal |
| heading (h3+) | — | muted |
| class | 🟦 | blue badge |
| function | 🟨 | yellow badge |
| method | 🔹 | light blue |
| constant | ⚙ | gray |
| import block | 📦 | neutral |
| section comment | ── | muted |

### 4.5. Search/Filter

The search input at the top of the panel filters the tree in real-time:
- Fuzzy-matching on node text (heading names, function names, file names)
- When filtering, all matching nodes are auto-expanded to show results
- Non-matching branches are hidden
- The search is client-side (no API call) — filters the already-loaded data
- Clear button (×) resets filter and restores expand/collapse state
- No debounce needed (instant, operates on in-memory data)

### 4.6. Scroll Sync (Active Heading Tracking)

When the user scrolls the preview or moves the cursor in the editor:

1. `_contentFocusLine` is updated (existing mechanism)
2. The observer/cursor callback calls `_glossaryUpdateActive(currentFilePath, line)`
3. This function finds the heading in the glossary tree whose `line` is
   closest to `_contentFocusLine` without exceeding it (floor match)
4. The previous active heading loses `.active-heading` class
5. The new active heading gets `.active-heading` class
6. The glossary panel auto-scrolls to keep the active heading visible
   (using `scrollIntoView({ block: 'nearest', behavior: 'smooth' })`)
7. If the file node is collapsed, it auto-expands

### 4.7. Keyboard Shortcut

`Ctrl+Shift+O` (or `Cmd+Shift+O` on Mac) toggles the outline panel.
This mirrors VS Code's "Go to Symbol" shortcut, which is familiar to developers.

### 4.8. State Persistence

| State | Storage | Scope | Key |
|-------|---------|-------|-----|
| Panel visible | `localStorage` | Persistent | `glossary-panel-visible` |
| Panel mode (outline/glossary) | `localStorage` | Persistent | `glossary-panel-mode` |
| Panel width | `localStorage` | Persistent | `glossary-panel-width` |
| Expanded nodes | `sessionStorage` | Per session | `glossary-expanded` |
| Active file/heading | Transient (derived) | — | — |
| Glossary data | In-memory | Transient | — |
| Search query | Transient | — | — |

**Default values** (first visit, no stored preference):
- Panel visible: `true` (starts open)
- Panel mode: `glossary` when in folder view, `outline` when viewing a file
- Panel width: `260px`


## 5. Integration Matrix

### 5.1. With Content Tab Modes (docs / media / archive / chat)

| Mode | Glossary behavior |
|------|-------------------|
| docs | ✅ Full feature — folder glossary + file outline |
| media | ⚠️ Limited — shows file list only (no heading extraction for images) |
| archive | ❌ Hidden — archive mode has its own navigation |
| chat | ❌ Hidden — chat mode has its own panel |

### 5.2. With View Modes (preview / raw / edit)

| View mode | Outline shows | Scroll sync method |
|-----------|---------------|-------------------|
| preview (markdown) | Headings | IntersectionObserver (`_contentObservePreviewLines`) |
| preview (code) | Headings (if md) or symbols (if code) | Not applicable (rendered output) |
| raw | Same outline as preview | Monaco `onDidChangeCursorPosition` |
| edit | Same outline as raw | Monaco `onDidChangeCursorPosition` |

The outline stays the same regardless of view mode — it always shows the
structure of the source file. The only thing that changes is the sync method.

### 5.3. With Existing Line Tracking

The glossary hooks into the existing `window._contentFocusLine` system:

```
User scrolls preview → IntersectionObserver fires
                     → _contentFocusLine updated
                     → contentUpdateHash({ push: false }) [existing]
                     → _glossaryUpdateActive(file, line)  [new]

User clicks in editor → Monaco cursor fires
                      → _contentFocusLine updated
                      → contentUpdateHash({ push: false }) [existing]
                      → _glossaryUpdateActive(file, line)  [new]

User clicks glossary heading → _glossaryNavigateToLine(file, line)
                             → _contentFocusLine = line
                             → contentPreviewFile(file, name) [if different file]
                             → OR scrollToLine/revealLineInCenter [if same file]
                             → contentUpdateHash() [existing]
```

### 5.4. With Peek Preview

When a peek overlay is active:
- Glossary stays visible underneath (part of base layout)
- Active heading does NOT update (peek suppresses `contentUpdateHash`)
- Clicking glossary closes peek first, then navigates

### 5.5. With Modal Preview

When a modal is active:
- Glossary is hidden behind modal overlay
- No interaction, no state updates

### 5.6. With Smart Folders

Smart folder glossary uses the same API with `?smart_folder=<name>`:
- Groups entries by module (same hierarchy as existing smart folder tree)
- Each module is a top-level expandable node
- Within each module, files and headings are shown
- Click-to-navigate uses the real `source_path` from the smart folder resolution

### 5.7. With Navigation History

- Clicking a heading pushes a new history entry (via `contentPreviewFile` → `contentUpdateHash`)
- The hash contains `:LINE` so Back button restores position
- Glossary expand/collapse state is NOT in the hash (session-persisted separately)
- Toggling the glossary panel is NOT a history event


## 6. Implementation Phases

### Phase 1: Backend — Outline Service + Markdown Strategy ✅
**New files**:
- `src/core/services/content/outline.py` — strategy interface, Markdown extractor
- `src/ui/web/routes/content/outline.py` — API routes

**Scope**:
- `extract_outline()` for markdown files (heading regex + nesting)
- `extract_folder_glossary()` for folder-level heading maps
- In-memory LRU cache with mtime invalidation
- Performance guard (200 file limit, 512 KB per file)
- Register routes on `content_bp`

**Deliverable**: `/api/content/outline?path=file.md` and
`/api/content/glossary?path=docs/` return correct data.

### Phase 2: Backend — Python Strategy ✅
**Edit file**: `src/core/services/content/outline.py`

**Scope**:
- `PythonOutlineStrategy` using `ast.parse()`
- Extract classes, functions, methods, constants with line numbers
- Nested structure (methods inside classes)
- Handle syntax errors gracefully (return empty outline, not 500)

**Deliverable**: `/api/content/outline?path=file.py` returns class/function tree.

### Phase 3: Frontend — Panel Shell + Toggle ✅
**Edit files**:
- `_tab_content.html` — add glossary panel div
- `admin.css` — panel styles, layout
- `_init.html` — state variables
- `_nav.html` — wire toggle button, load glossary on folder change

**New file**: `_glossary.html` — panel control, state, toggle

**Scope**:
- Panel HTML structure (header with mode tabs, search input, tree container)
- Dual-mode tabs: Outline / Glossary in panel header
- Toggle button in toolbar with active state
- Side-by-side flexbox layout
- localStorage persistence for visibility, mode, and width
- CSS resize handle
- Mobile responsive (stacked layout)
- Keyboard shortcut (Ctrl+Shift+O)
- Auto-switch to Outline mode when opening a file
- Auto-switch to Glossary mode when navigating back to folder grid

**Deliverable**: Toggle shows/hides panel with proper layout.

### Phase 4: Frontend — Tree Rendering + Navigation ✅
**Edit file**: `_glossary.html`

**Implementation note**: Delivered together with Phase 3 since tree rendering
is a core dependency of the panel shell. All scope items implemented in
`_glossary.html` functions: `_glossaryRenderNodes`, `_glossaryRenderEntries`,
`_glossaryToggleExpand`, `_glossaryClickNode`, `_glossaryClickFile`, `_glossaryFilter`.

**Scope**:
- `_glossaryLoadFolder()` and `_glossaryLoadFile()`
- `_glossaryRenderTree()` — recursive tree builder
- `_glossaryToggleNode()` — expand/collapse with session persistence
- Click-to-navigate: headings → open file at `:LINE`
- Icon system for different symbol kinds
- File size shown inline (human-readable: KB, MB)
- Encrypted files as 🔐 leaves ("encrypted — open to see outline")
- Non-text files as leaves with type icons (🖼 📹 🎵 📦)
- Search/filter input (client-side fuzzy match)

**Deliverable**: Full glossary tree with expand/collapse, navigation, search.

### Phase 5: Frontend — Scroll Sync ✅
**Edit files**: `_preview.html`, `_monaco.html`, `_glossary.html`

**Implementation note**: `_glossaryUpdateActive` wired into existing
IntersectionObserver and Monaco `onDidChangeCursorPosition` callbacks.
60ms debounce prevents jank during fast scrolling.

**Scope**:
- `_glossaryUpdateActive(filePath, line)` — find nearest heading
- Wire from IntersectionObserver callback in `_preview.html`
- Wire from Monaco cursor callback in `_monaco.html`
- Auto-scroll panel to keep active heading visible
- Auto-expand parent nodes
- Visual highlight (`.active-heading` class)

**Deliverable**: Glossary tracks scroll position in real-time.

### Phase 6: (Stage 2) — All Remaining Language Strategies ✅

**Implemented in Stage 2** — `.agent/plans/contextual-glossary-stage2.md`

10 new strategies added: JS/TS, Go, Rust, HTML, CSS/SCSS, YAML, JSON, TOML,
Shell, SQL. All regex-based except JSON (uses `json.loads()`). Total: 30
extensions across 14 strategies. Single file change: `outline.py`.

### Phase 7: Smart Folder Integration ✅
**Edit files**: `_glossary.html`, `_smart_folders.html`

**Implementation note**: Handled client-side rather than backend to avoid
cross-domain coupling. `_glossaryResolveCurrentFolder()` detects active
smart folder and resolves virtual path → real source `module_path` from
the cached smart folder tree. No backend changes needed.

**Scope**:
- ~~Extend `/api/content/glossary` to accept `smart_folder=<name>`~~ (handled client-side)
- Module-grouped tree in the glossary panel (via real source path resolution)
- Cross-module navigation
- Works with the existing smart folder rendering

**Deliverable**: Glossary works for smart folders.

### Phase 8: Polish + Edge Cases ✅
**All files**

**Implementation note**: Most polish items were already covered by prior phases.
Save-triggered refresh automatically works because `contentSaveEdit` calls
`contentPreviewFile` which triggers `_glossaryLoadForCurrentContext`. Width
persistence uses `ResizeObserver` + `localStorage`. Keyboard nav uses `Alt+↑/↓`.

**Scope**:
- ~~Performance testing with large projects (100+ files)~~ — covered by backend guards (200 file cap, 512KB limit, parallel extraction)
- Error handling (network failures, large files, parse errors) ✅
- Empty states ("no files", "no headings", "encrypted") ✅
- ~~Animations for expand/collapse~~ — arrow rotation transition provides visual feedback; `display:none` toggle is fast and reliable
- Panel width persistence (localStorage) ✅
- File change detection (refresh outline after save) ✅ — automatic via save → preview reload → glossary reload chain
- Keyboard navigation within the glossary tree (Alt+arrow keys) ✅


## 7. Files Changed (Complete List)

| File | Action | Phase | Purpose |
|------|--------|-------|---------|
| `src/core/services/content/outline.py` | **New** | 1, 2 | Outline extraction service (Markdown + Python strategies, caching, parallel extraction) |
| `src/ui/web/routes/content/outline.py` | **New** | 1 | API endpoints (`/api/content/outline`, `/api/content/glossary`) |
| `src/ui/web/routes/content/__init__.py` | Edit | 1 | Import outline sub-module |
| `src/ui/web/templates/scripts/content/_glossary.html` | **New** | 3–8 | Glossary panel JS (toggle, modes, render, filter, scroll sync, keyboard nav, width persistence) |
| `src/ui/web/templates/scripts/content/_content.html` | Edit | 3 | Include `_glossary.html`, update module index |
| `src/ui/web/templates/scripts/content/_init.html` | Edit | 3 | State variables (`_glossaryVisible`, `_glossaryMode`, caches) |
| `src/ui/web/templates/partials/_tab_content.html` | Edit | 3 | Panel div + toggle button + flex container |
| `src/ui/web/static/css/admin.css` | Edit | 3 | Panel, tree, mode tab, search, node styles + mobile responsive |
| `src/ui/web/templates/scripts/content/_nav.html` | Edit | 3 | Wire glossary refresh on folder load |
| `src/ui/web/templates/scripts/content/_preview.html` | Edit | 3, 5 | Wire glossary refresh on file open + scroll sync IntersectionObserver |
| `src/ui/web/templates/scripts/content/_preview_enc.html` | Edit | 3 | Wire glossary refresh on preview close |
| `src/ui/web/templates/scripts/_monaco.html` | Edit | 5 | Wire scroll sync from Monaco cursor callback |
| `src/ui/web/templates/scripts/content/_smart_folders.html` | Edit | 7 | Wire glossary refresh on smart folder render |


## 8. Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| AST parsing fails on invalid Python | Medium | Wrap in try/except, return empty outline |
| Large folder (500+ files) causes slow glossary | Low | 200-file cap, parallel extraction, caching |
| Regex-based extraction misses edge cases (JS) | Medium | Acceptable for v1 — covers 95% of real code |
| Panel layout breaks on small screens | Medium | Mobile-first CSS, stacked layout below 768px |
| Glossary panel increases page load time | Low | Lazy-loaded (only on toggle), cached after first load |
| Encrypted file handling edge cases | Low | Show 🔐 leaf, no extraction, clear UX messaging |
| Smart folder tree is very deep (10+ levels) | Low | Max depth limit in rendering, horizontal scroll |


## 9. Resolved Decisions

All questions have been discussed and resolved with the user:

| # | Question | Decision |
|---|----------|----------|
| 1 | Panel title | **Both**: Outline (single-file focus) + Glossary (cross-file tree). User toggles between them via tabs in the panel header |
| 2 | Default visibility | **Start visible**. Persist choice to `localStorage` across sessions |
| 3 | Non-text files | **Show as leaves** with appropriate icons (🖼 📹 🎵 📦) |
| 4 | Panel position | **Left sidebar** |
| 5 | Strategy scope | **Ship Markdown + Python first** (Stage 1). Full language coverage in Stage 2 — separate plan document exists to ensure nothing is lost |
| 6 | File size display | **Show in tree** inline. We want a smart tree with sizes visible, will iterate to improve |
