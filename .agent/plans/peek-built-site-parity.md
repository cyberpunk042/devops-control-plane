# Peek Feature — Built Site Full Parity Plan

> **Goal**: Bring the Docusaurus built site peek feature to full parity
> with the Content Vault's peek implementation.
>
> **Reference**: `src/ui/web/templates/scripts/content/_preview.html`
> lines 626–1839 — the gold standard.
>
> **Target**: `src/core/services/pages_builders/templates/docusaurus/theme/hooks/usePeekLinks.ts`
> and the build pipeline in `src/core/services/pages_builders/docusaurus.py`.

---

## Architecture Overview

### Content Vault (admin panel)
```
User clicks peek-link → tooltip appears
  → Preview: fetch /api/content/preview → render markdown / Monaco / image
  → Open: navigate within admin SPA
  → Browse: load folder in content browser
  → New Tab: open new admin tab with hash route
  → Outline: headings from glossary / async API
```

### Built Docusaurus Site (target)
```
User clicks peek-link → tooltip appears
  → If ref is an INTERNAL doc page → navigate to that Docusaurus route
  → If ref is an EXTERNAL source file:
      → Preview: fetch raw content → render with Monaco CDN or bundled markdown
      → GitHub: link to blob view
      → Edit: link to GitHub edit URL (published) / localhost admin (local)
  → Outline: pre-baked in peek-index.json (already done)
```

**Key insight**: The built site is static. There is no API.
But we have TWO powerful data sources:
1. **The site itself** — internal doc pages are pre-rendered HTML we can fetch
2. **GitHub raw** — source files can be fetched from `raw.githubusercontent.com`
3. **Localhost API** — when running locally alongside the admin panel

---

## Gap Analysis & Solutions

### ═══════════════════════════════════════════════════
### PHASE 1: Fix What's Broken
### ═══════════════════════════════════════════════════

#### Gap 1.1 — Code block annotation (NOISY/WRONG)

**Problem**: The DOM walker annotates text inside `<code>` and `<pre>` blocks.
Every `filename.py` mention in a code example becomes a peek-link.
This is noisy, visually jarring, and semantically wrong.

**Vault behavior**: Same issue exists but less visible due to admin panel styling.

**Solution**:
In `annotatePeekRefs()` and `annotateUnresolvedRefs()`, add skip conditions:
```typescript
if (textNode.parentElement?.closest('pre')) continue;
if (textNode.parentElement?.closest('code')) continue;
if (textNode.parentElement?.closest('.prism-code')) continue;  // Docusaurus code blocks
```

**Files**: `usePeekLinks.ts` lines 164-165 and 232-233
**Effort**: Small (5 min)

---

#### Gap 1.2 — `__REPO_URL__` not substituted

**Problem**: The placeholder `__REPO_URL__` in `usePeekLinks.ts` is never
replaced during the build pipeline. All GitHub links are broken on published site.

**Vault behavior**: N/A — vault uses API, not GitHub URLs.

**Solution**:
In `docusaurus.py` `_stage_scaffold`, after copying hook files, run
placeholder substitution on `usePeekLinks.ts`:
```python
# After line 508 (hook copy loop)
peek_hook = hooks_dir / "usePeekLinks.ts"
if peek_hook.is_file():
    hook_content = peek_hook.read_text(encoding="utf-8")
    repo_url = config.get("repo_url", "")  # from segment config or project.yml
    hook_content = hook_content.replace("__REPO_URL__", repo_url)
    peek_hook.write_text(hook_content, encoding="utf-8")
```

**Source of repo_url**: `project.yml` → `github.repo` or the segment's
`config.repo_url`. Need to trace where this is stored.

**Files**: `docusaurus.py` ~line 508
**Effort**: Small (10 min)

---

#### Gap 1.3 — Preview overlay fundamentally broken

**Problem**: `_openPeekPreview()` tries to fetch from `localhost:8000/api/...`
(local) or `raw.githubusercontent.com` (published). The local path works only
if the admin panel is running. The published path:
- Doesn't render markdown — displays raw `.md` source in `<pre>`
- No syntax highlighting (Prism.highlightElement never fires)
- Directory preview is just a raw README fetch, no listing, no tabs

**Vault behavior**: Full rendered markdown preview, Monaco editor for code,
image display, directory tab bar (README + Listing), scroll-to-line,
heading observation, truncation warning.

**Solution**: Complete rewrite of `_openPeekPreview()`. See Phase 3.

---

#### Gap 1.4 — Tooltip actions wrong for static site context

**Problem**: Actions shown are:
- "Preview" → broken overlay
- "Open in Vault" → `localhost:8000/#content/...` (useless on published site)
- "View on GitHub" → broken (`__REPO_URL__` empty)

**Vault behavior**: Preview / Open / Browse / New Tab / Smart browse —
all navigate within the admin panel.

**Solution**: Context-aware actions. See Phase 2.

---

### ═══════════════════════════════════════════════════
### PHASE 2: Smart Tooltip Actions
### ═══════════════════════════════════════════════════

#### Gap 2.1 — Internal vs External ref distinction

**Problem**: Tooltip treats all refs the same. No distinction between a
reference to `audit_ops.py` (which exists as a docs page at
`/core/services/audit/audit_ops`) and a reference to `pyproject.toml`
(which has no docs page).

**Solution**: Add `doc_url` field to peek-index entries at build time.
When a resolved ref maps to an existing `.mdx` file in the docs tree,
compute the Docusaurus route URL and include it:

```python
# In docusaurus.py scaffold loop, after building entries:
for rd in entries:
    if rd.get("resolved"):
        # Check if this ref has a corresponding docs page
        _rp = rd["resolved_path"]
        # Try to find matching .mdx in docs_dir
        for _pfx in ("src/", ""):
            if _rp.startswith(_pfx):
                _rel = _rp[len(_pfx):]
                if _rel.endswith("/README.md"):
                    _mdx = _rel[:-len("/README.md")] + "/index.mdx"
                elif _rel.endswith(".md"):
                    _mdx = _rel[:-3] + ".mdx"
                else:
                    continue
                if (docs_dir / _mdx).is_file():
                    # Compute doc URL relative to site root
                    doc_route = _mdx.replace("/index.mdx", "").replace(".mdx", "")
                    rd["doc_url"] = doc_route
                    break
```

**PeekRef interface update**:
```typescript
interface PeekRef {
    text: string;
    resolved_path: string;
    line_number: number | null;
    is_directory: boolean;
    resolved?: boolean;
    outline?: string[];
    doc_url?: string;    // NEW: Docusaurus route if ref has a docs page
}
```

**Tooltip rendering**:
```typescript
// If ref has doc_url → primary action is "Open Page" (navigate within site)
// If ref has no doc_url → primary action is "View on GitHub"
// Preview remains available for both
```

**Files**: `docusaurus.py` scaffold, `usePeekLinks.ts` tooltip
**Effort**: Medium (30 min)

---

#### Gap 2.2 — File extension tag badge

**Problem**: Tooltip shows "Directory" label or "Line N" but no file type tag.

**Vault behavior**: Shows `.py`, `.md`, etc. as styled tag badges.

**Solution**: Extract extension and render as tag:
```typescript
const ext = ref.resolved_path.includes('.')
    ? '.' + ref.resolved_path.split('.').pop()
    : '';
// In tooltip HTML:
`${ext ? '<span class="peek-tooltip__tag">' + _esc(ext) + '</span>' : ''}`
`${ref.is_directory ? '<span class="peek-tooltip__tag peek-tooltip__tag--dir">Directory</span>' : ''}`
```

**CSS needed**:
```css
.peek-tooltip__tag {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 10px;
    font-family: monospace;
    background: rgba(129, 140, 248, 0.12);
    color: var(--ifm-color-primary);
    border: 1px solid rgba(129, 140, 248, 0.2);
}
.peek-tooltip__tag--dir {
    background: rgba(255, 183, 77, 0.12);
    color: #ffb74d;
    border-color: rgba(255, 183, 77, 0.2);
}
```

**Files**: `usePeekLinks.ts`, `custom.css.tmpl`
**Effort**: Small (10 min)

---

#### Gap 2.3 — Parent directory context

**Problem**: Tooltip shows full path but no separated context.

**Vault behavior**: Shows directory name next to the tag badge.

**Solution**:
```typescript
const parentDir = ref.resolved_path.substring(0, ref.resolved_path.lastIndexOf('/'));
// Add to tooltip:
`<span class="peek-tooltip__context">${_esc(parentDir || '/')}</span>`
```

**Files**: `usePeekLinks.ts`
**Effort**: Small (5 min)

---

#### Gap 2.4 — Context-aware action buttons

**Problem**: Actions are hardcoded and wrong for the static site context.

**Solution**: Generate actions based on ref type + deployment context:

| Ref Type | IS_LOCAL | Published |
|----------|----------|-----------|
| Internal doc (has doc_url) | **Open Page** (router.push) / Preview / Open in Vault / New Tab | **Open Page** / Preview / View on GitHub |
| External file (no doc_url) | Preview / Open in Vault / New Tab | Preview / View on GitHub / Edit on GitHub |
| Directory (internal) | **Browse Section** (router.push) / Preview / New Tab | **Browse Section** / Preview / View on GitHub |
| Directory (external) | Preview / Browse in Vault | Preview / View on GitHub |
| Unresolved | (no actions) | (no actions) |

"Open Page" uses Docusaurus client-side navigation (no full page reload):
```typescript
import { useHistory } from '@docusaurus/router';
// Or: window.location.href = baseUrl + ref.doc_url;
```

"Edit on GitHub":
```typescript
const editHref = `${REPO_URL}/edit/main/${ref.resolved_path}`;
```

**Files**: `usePeekLinks.ts`
**Effort**: Medium (20 min)

---

### ═══════════════════════════════════════════════════
### PHASE 3: Preview Overlay — Full Power
### ═══════════════════════════════════════════════════

#### Gap 3.1 — Preview strategy for internal doc pages

**Problem**: Internal doc pages already exist as rendered HTML within the site.
Current code doesn't use this.

**Solution**: If `ref.doc_url` exists, fetch the Docusaurus page HTML and
extract the `.markdown` content container:

```typescript
async function _previewInternalDoc(ref: PeekRef, body: HTMLElement): Promise<void> {
    const baseUrl = document.querySelector('meta[name="docusaurus_base_url"]')?.getAttribute('content') || '/';
    const pageUrl = baseUrl + ref.doc_url;
    const resp = await fetch(pageUrl);
    const html = await resp.text();
    
    // Parse and extract the markdown content
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const content = doc.querySelector('.markdown');
    
    if (content) {
        body.innerHTML = '';
        const rendered = document.createElement('div');
        rendered.className = 'markdown peek-preview-rendered';
        rendered.innerHTML = content.innerHTML;
        body.appendChild(rendered);
    } else {
        body.innerHTML = '<div class="peek-preview-loading">Page content not found</div>';
    }
}
```

**Benefit**: Zero additional dependencies. Content is already styled with
Docusaurus CSS. Links within the preview work because they're relative.

**Files**: `usePeekLinks.ts`
**Effort**: Medium (20 min)

---

#### Gap 3.2 — Preview strategy for source code files (Monaco CDN)

**Problem**: Source code files (`.py`, `.ts`, `.json`, etc.) currently
render as unformatted `<pre>` blocks with no highlighting.

**Vault behavior**: Full Monaco editor with syntax highlighting,
line numbers, scroll-to-line, read-only mode.

**Solution**: Load Monaco from CDN. The exact same strategy the admin
panel uses but with CDN instead of local assets:

```typescript
const MONACO_CDN = 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min';

let _monacoLoaded = false;
let _monacoLoadPromise: Promise<void> | null = null;

function _loadMonaco(): Promise<void> {
    if (_monacoLoaded) return Promise.resolve();
    if (_monacoLoadPromise) return _monacoLoadPromise;
    
    _monacoLoadPromise = new Promise((resolve, reject) => {
        // Configure Monaco AMD loader
        const script = document.createElement('script');
        script.src = `${MONACO_CDN}/vs/loader.js`;
        script.onload = () => {
            (window as any).require.config({
                paths: { vs: `${MONACO_CDN}/vs` }
            });
            (window as any).require(['vs/editor/editor.main'], () => {
                _monacoLoaded = true;
                resolve();
            });
        };
        script.onerror = reject;
        document.head.appendChild(script);
    });
    return _monacoLoadPromise;
}

async function _previewSourceCode(
    ref: PeekRef,
    content: string,
    body: HTMLElement,
): Promise<void> {
    await _loadMonaco();
    
    const container = document.createElement('div');
    container.style.width = '100%';
    container.style.height = '100%';
    container.style.minHeight = '400px';
    body.innerHTML = '';
    body.appendChild(container);
    
    const ext = ref.resolved_path.split('.').pop() || '';
    const langMap: Record<string, string> = {
        py: 'python', ts: 'typescript', tsx: 'typescript', js: 'javascript',
        jsx: 'javascript', yml: 'yaml', yaml: 'yaml', json: 'json',
        sh: 'shell', bash: 'shell', css: 'css', html: 'html',
        md: 'markdown', toml: 'ini', sql: 'sql', go: 'go',
        rs: 'rust', tf: 'hcl', Dockerfile: 'dockerfile',
    };
    
    const monaco = (window as any).monaco;
    const editor = monaco.editor.create(container, {
        value: content,
        language: langMap[ext] || 'plaintext',
        theme: 'vs-dark',
        readOnly: true,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        fontSize: 13,
        lineNumbers: 'on',
        renderLineHighlight: 'line',
        automaticLayout: true,
    });
    
    if (ref.line_number && ref.line_number > 0) {
        editor.revealLineInCenter(ref.line_number);
        editor.setPosition({ lineNumber: ref.line_number, column: 1 });
    }
}
```

**Note**: Monaco CDN is ~2MB but loaded LAZILY only when preview is
opened. No impact on initial page load.

**Files**: `usePeekLinks.ts`
**Effort**: Medium (30 min)

---

#### Gap 3.3 — Markdown preview rendering from source

**Problem**: When we preview a `.md` file that isn't a docs page, we need
to render it from raw source. Currently shows raw text in `<pre>`.

**Solution**: Bundle a lightweight markdown renderer. Options:
1. `marked` (~40KB minified) — fast, good enough
2. Use Docusaurus's built-in MDX renderer (already in the bundle)

**Recommended approach**: Import `marked` from CDN and render:

```typescript
const MARKED_CDN = 'https://cdn.jsdelivr.net/npm/marked@12.0.0/marked.min.js';

let _markedLoaded = false;
let _markedLoadPromise: Promise<void> | null = null;

function _loadMarked(): Promise<void> {
    if (_markedLoaded) return Promise.resolve();
    if (_markedLoadPromise) return _markedLoadPromise;
    
    _markedLoadPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = MARKED_CDN;
        script.onload = () => { _markedLoaded = true; resolve(); };
        script.onerror = reject;
        document.head.appendChild(script);
    });
    return _markedLoadPromise;
}

async function _previewMarkdown(content: string, body: HTMLElement): Promise<void> {
    await _loadMarked();
    const marked = (window as any).marked;
    const html = marked.parse(content);
    body.innerHTML = `<div class="markdown peek-preview-rendered">${html}</div>`;
}
```

**Files**: `usePeekLinks.ts`
**Effort**: Small (15 min)

---

#### Gap 3.4 — Directory preview with tabs (README + Listing)

**Problem**: Directory preview just fetches README.md. No listing, no tabs.

**Vault behavior**: Tab bar with README tab (rendered markdown) and
Listing tab (browsable file tree with sizes, clickable items).

**Solution for published site**: No API for listing. But we can build
a **directory index at build time** and include it in peek-index.json:

```python
# In docusaurus.py scaffold, for directory refs:
if rd.get("is_directory") and rd.get("resolved"):
    dir_path = project_root / rd["resolved_path"]
    if dir_path.is_dir():
        listing = []
        for item in sorted(dir_path.iterdir()):
            if item.name.startswith('.'):
                continue
            listing.append({
                "name": item.name,
                "is_dir": item.is_dir(),
                "size": item.stat().st_size if item.is_file() else None,
            })
        rd["dir_listing"] = listing[:50]  # cap at 50
```

**PeekRef interface update**:
```typescript
interface PeekRef {
    // ... existing fields
    dir_listing?: Array<{name: string; is_dir: boolean; size: number | null}>;
}
```

**Tab rendering** (same structure as vault):
```typescript
// Build tab content
const readmeContent = ...; // fetched from GitHub raw or embedded
const listingHtml = ref.dir_listing ? _buildListingHtml(ref) : '';

body.innerHTML = `
    <div class="peek-dir-tabs">
        <button class="peek-dir-tab active" data-tab="readme">📖 README</button>
        <button class="peek-dir-tab" data-tab="listing">
            📂 Listing <span>(${ref.dir_listing?.length || 0})</span>
        </button>
    </div>
    <div class="peek-dir-content" data-tab-content="readme">${readmeHtml}</div>
    <div class="peek-dir-content" data-tab-content="listing">${listingHtml}</div>
`;
// Wire tab clicks (same as vault)
```

**For local**: Can still use localhost API to get live listing.

**Files**: `docusaurus.py`, `usePeekLinks.ts`
**Effort**: Medium (30 min)

---

#### Gap 3.5 — Preview header actions (Jump / Edit)

**Problem**: Preview overlay has minimal actions.

**Vault behavior**: Jump to file (navigates in content browser),
Edit (opens editor mode), Close. For directories: Raw browse,
Smart browse, Open README.

**Solution for built site**:

| Action | Local | Published |
|--------|-------|-----------|
| Jump to (internal doc) | Navigate to Docusaurus route | Navigate to route |
| Jump to (external file) | Open in Vault (`localhost:8000/#...`) | Open on GitHub blob |
| Edit | Open in Vault edit mode | GitHub edit URL |
| Close | ✕ / Esc / backdrop click | Same |

```typescript
// Header actions for preview overlay:
const jumpHref = ref.doc_url
    ? baseUrl + ref.doc_url                              // internal → navigate
    : IS_LOCAL
        ? `http://localhost:8000/#content/docs/${ref.resolved_path}@preview`
        : `${REPO_URL}/blob/main/${ref.resolved_path}`;  // published → GitHub

const editHref = IS_LOCAL
    ? `http://localhost:8000/#content/docs/${ref.resolved_path}@edit`
    : `${REPO_URL}/edit/main/${ref.resolved_path}`;
```

**Files**: `usePeekLinks.ts`
**Effort**: Small (15 min)

---

#### Gap 3.6 — Scroll-to-line in preview

**Problem**: When a ref has `line_number`, preview doesn't scroll to it.

**Vault behavior**: `_peekScrollToLine()` scrolls rendered markdown or
Monaco editor to the target line. Uses `data-source-line` attributes
mapped from source headings.

**Solution**:
- For Monaco: `editor.revealLineInCenter(lineNumber)` (already in Gap 3.2)
- For rendered markdown: Map headings to source lines at build time.
  Add `data-source-line` to heading elements in rendered HTML.
  Then scroll the peek-preview-body to the matching element.

**Files**: `usePeekLinks.ts`
**Effort**: Small (10 min, mostly in Monaco — markdown scroll is nice-to-have)

---

#### Gap 3.7 — History integration (Back button closes peek)

**Problem**: Opening peek preview doesn't push a history entry.
Pressing Back navigates away from the entire page.

**Vault behavior**: Pushes `>>peek/path` to history. Back button
closes the peek overlay instead of navigating away.

**Solution**:
```typescript
// When opening preview:
const currentUrl = window.location.href;
history.pushState({ peek: true, path: ref.resolved_path }, '', currentUrl);

// Listen for popstate:
window.addEventListener('popstate', (e) => {
    if (_peekPreviewEl) {
        _closePeekPreview();
    }
});
```

**Files**: `usePeekLinks.ts`
**Effort**: Small (10 min)

---

### ═══════════════════════════════════════════════════
### PHASE 4: Content Strategy (Build-Time Data)
### ═══════════════════════════════════════════════════

#### Gap 4.1 — Embed preview content in peek-index.json

**Problem**: On a published static site, there is no API. Fetching from
GitHub raw is slow and may hit rate limits. The peek-index is already 1.1MB.

**Options**:
1. **Don't embed** — fetch from GitHub raw at preview time (current approach)
2. **Embed first N lines** — include first 50 lines of each referenced file
   in peek-index.json (increases size but instant preview)
3. **Separate chunks** — generate per-page peek data files and lazy-load

**Recommended**: Option 1 (GitHub raw) for published, Option 3 (localhost API)
for local. Embedding increases build artifact size too much.

For markdown files specifically, we could embed the **rendered HTML**
since we already have it in the docs build. This is the smartest approach:
internal docs pages are already HTML — just fetch from the site itself (Gap 3.1).

**Decision**: No embedding. Use site-self-fetch for internal docs,
GitHub raw for external files, localhost API for local dev.

---

#### Gap 4.2 — Optimize peek-index.json size

**Problem**: Currently 1.1MB for ~150 pages. Adding `doc_url`, `dir_listing`,
and `outline` fields will grow it further.

**Solutions**:
1. **Minify keys** — use short keys: `t` for text, `r` for resolved_path, etc.
   (ugly, harder to debug)
2. **Split per-page** — generate `peek-index/core/services/audit.json` per page,
   lazy-load on navigation. Hook fetches the per-page JSON instead of importing
   the full index.
3. **Gzip** — Docusaurus serves gzipped assets. 1MB JSON gzips to ~100KB.
   This is already handled by the production build.

**Recommended**: Keep as-is for now. Gzip handles it. If it grows past 3MB,
split per-page (option 2).

---

### ═══════════════════════════════════════════════════
### PHASE 5: Visual Polish
### ═══════════════════════════════════════════════════

#### Gap 5.1 — Tooltip info row (tag + context)

Vault has `peek-tooltip__info` row with:
- File extension tag (`.py`)
- Line number context
- Parent directory name

**Solution**: Replace `peek-tooltip__label` with `peek-tooltip__info`:
```html
<div class="peek-tooltip__info">
    <span class="peek-tooltip__tag">.py</span>
    <span class="peek-tooltip__context">audit · Line 42</span>
</div>
```

**CSS**: See Gap 2.2.

---

#### Gap 5.2 — Clickable outline items

**Problem**: Outline items in tooltip are static text.

**Vault behavior**: Clicking a heading in the outline navigates to it
within the preview.

**Solution**: If `doc_url` exists, clicking an outline item navigates
to the docs page with an anchor:
```typescript
// For markdown headings, generate anchors:
const anchor = item.toLowerCase().replace(/[^a-z0-9]+/g, '-');
`<div class="peek-tooltip__outline-item"
     onclick="window.location.href='${baseUrl}${ref.doc_url}#${anchor}'"
     style="cursor:pointer">
    ${_esc(item)}
</div>`
```

**Files**: `usePeekLinks.ts`
**Effort**: Small (10 min)

---

#### Gap 5.3 — Spinner in loading state

**Vault behavior**: Shows `<span class="spinner"></span>` during load.

**Solution**: Add spinner CSS to `custom.css.tmpl`:
```css
.peek-preview-loading .spinner {
    display: inline-block;
    width: 16px;
    height: 16px;
    border: 2px solid rgba(255,255,255,0.15);
    border-top-color: var(--ifm-color-primary);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
}
@keyframes spin {
    to { transform: rotate(360deg); }
}
```

And use in loading state:
```html
<div class="peek-preview-loading"><span class="spinner"></span> Loading…</div>
```

**Files**: `custom.css.tmpl`, `usePeekLinks.ts`
**Effort**: Small (5 min)

---

### ═══════════════════════════════════════════════════
### PHASE 6: Docusaurus-Specific Enhancements
### ═══════════════════════════════════════════════════

#### Gap 6.1 — Line number tracking in preview

**Vault behavior**: `_peekObserveLines()` uses IntersectionObserver
to track which source line the user is scrolled to. Live-updates
the header with current line. Used for "Jump" actions.

**Solution**: For Monaco previews, listen to `editor.onDidScrollChange`
and `editor.getVisibleRanges()`. For markdown previews, use the same
IntersectionObserver pattern as the vault.

**Files**: `usePeekLinks.ts`
**Effort**: Medium (20 min)

---

#### Gap 6.2 — Annotation count indicator

**Problem**: No feedback on how many peek annotations were found.

**Solution**: Add a small floating badge to the page:
```html
<div class="peek-status">
    <span class="peek-status__icon">🔗</span>
    <span class="peek-status__count">12 refs</span>
</div>
```

Shows briefly (2s fade-in, then subtle) after annotation finishes.
Click opens a legend/mini-panel showing all refs for the page.

**Files**: `usePeekLinks.ts`, `custom.css.tmpl`
**Effort**: Medium (20 min)

---

---

## Implementation Order

```
Phase 1 — Fix What's Broken (required for basic functionality)
  1.1  Skip code blocks in annotation         [5 min]
  1.2  Fix __REPO_URL__ substitution           [10 min]

Phase 2 — Smart Tooltip Actions
  2.1  Add doc_url to peek-index entries       [30 min]
  2.2  File extension tag badge                [10 min]
  2.3  Parent directory context                [5 min]
  2.4  Context-aware action buttons            [20 min]

Phase 3 — Preview Overlay (the big one)
  3.1  Internal doc preview (self-fetch)       [20 min]
  3.2  Source code preview (Monaco CDN)        [30 min]
  3.3  Markdown preview (marked CDN)           [15 min]
  3.4  Directory preview with tabs             [30 min]
  3.5  Preview header actions                  [15 min]
  3.6  Scroll-to-line                          [10 min]
  3.7  History integration                     [10 min]

Phase 5 — Visual Polish
  5.1  Tooltip info row                        [10 min]
  5.2  Clickable outline items                 [10 min]
  5.3  Loading spinner                         [5 min]

Phase 6 — Enhancements
  6.1  Line number tracking                    [20 min]
  6.2  Annotation count indicator              [20 min]
```

**Total estimated**: ~5 hours of focused implementation.

---

## Files Modified

| File | Changes |
|------|---------|
| `usePeekLinks.ts` | Major rewrite — tooltip, preview, Monaco, marked, history |
| `custom.css.tmpl` | Tag badges, spinner, status indicator, tab styles |
| `docusaurus.py` | `__REPO_URL__` substitution, `doc_url` field, `dir_listing` |
| `PeekRef` interface | New fields: `doc_url`, `dir_listing` |

---

## Open Questions

1. **Where is `repo_url` stored?** Need to trace from `project.yml`
   through to the builder to know how to substitute `__REPO_URL__`.

2. **Monaco CDN version pinning** — should we pin to a specific version
   or use `latest`? Recommend pinning for reproducibility.

3. **Marked CDN** — same question. Recommend pinning.

4. **peek-index.json split threshold** — at what size do we split
   per-page? Suggest 3MB uncompressed.

---

## Status

- [x] Phase 0: peek feature enabled by default
- [x] Phase 0: locationToDocPath URL mapping fixed
- [x] Phase 0: streaming progress for build modal
- [ ] Phase 1: Fix broken fundamentals
- [ ] Phase 2: Smart tooltip actions
- [ ] Phase 3: Preview overlay rewrite
- [ ] Phase 5: Visual polish
- [ ] Phase 6: Enhancements
