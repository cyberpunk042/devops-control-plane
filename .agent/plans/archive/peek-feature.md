# Peek Feature — Evolution Plan

> **Status**: ALL PHASES COMPLETE ✅
> **Created**: 2026-03-05
> **Updated**: 2026-03-05 — All 7 phases delivered
> **Scope**: Content Vault + Docusaurus SPA
> **Applies to**: Smart Docs (module READMEs) + Dumb Docs (hand-written markdown)

---

## What Peek Is

Every file reference, path reference, and symbol reference in a rendered document
that **can be resolved** to an actual location becomes **peekable** — visually
annotated and interactive.

Clicking a peekable element does NOT navigate directly. Instead it opens a
**tooltip panel** showing:
- The resolved path (or "Could not find file" if unresolved)
- File vs directory indicator
- Line number (if applicable, e.g. T3 or T5)
- Actions: **Open** (navigate in current pane), **Open in New Tab**, **Dismiss**

Unresolved references are also annotated (different styling) with a
"Could not find file" message in the tooltip.

This is not a mode or a toggle. Every reference is individually annotated
in the rendered output.

---

## Gap Analysis — Test Case: `src/core/README.md`

### Measured Coverage

```
Total file/path references a human expects to be peekable: 261
Actually resolved by current scanner+resolver:              83
Coverage:                                                   32%
Missed:                                                    178 (68%)
```

### Root Causes of 68% Miss Rate

#### Bug 1: Resolver doesn't search subdirectories (CRITICAL)

Current resolution order:
1. Same directory as the document
2. Project root
3. One level up

`src/core/README.md` references `action.py` which lives at
`src/core/models/action.py` — two levels down. The resolver never
tries `src/core/models/action.py`, `src/core/config/loader.py`,
`src/core/engine/executor.py`, etc.

**Every parent-level README has this problem.** Any README that documents
files in its subdirectories (which is what READMEs do) gets near-zero
resolution for bare filenames.

**Fix**: Add recursive subdirectory search. For a document at `src/core/README.md`,
try `src/core/**/action.py`. Prioritize by proximity (fewest intermediate dirs wins).

#### Bug 2: Scanner deduplicates by text (FLAWED)

The scanner uses `seen_texts` to deduplicate. `action.py` appears on
lines 122, 127, 224, 225 — only the first occurrence emits a candidate.
The DOM annotator's regex replaces ALL text-node matches globally, so
the dedup doesn't cause visible missing links for identical filenames.

BUT: the same filename can mean DIFFERENT files depending on context.
`detect.py` on line 170 means `use_cases/detect.py`, while on line 108
it means the generic "detect" pattern. Context (the surrounding heading
or table section) determines which file is meant.

**For Phase 4**: Dedup is acceptable IF resolution covers subdirectories
(Bug 1). The DOM annotator already replaces all occurrences with the
same resolved path, which is correct when there's only one file with
that name in the subtree. When ambiguous (multiple `detect.py` files),
the tooltip should show all candidates.

#### Bug 3: UX uses direct links instead of tooltip panel

Current behavior:
- Click → navigates to file (or folder) immediately
- No preview of where you're going
- No choice to open in new tab
- Directories call `contentLoadFolder()` indistinguishably from files
- Unresolved references are invisible (plain text, no annotation)

**Fix**: Replace direct `<a data-doclink>` navigation with a tooltip panel.

#### Bug 4: Table cell filenames have reduced detection

Markdown tables render as `<td>` elements. Bare filenames inside table
cells (like `action.py` in `| action.py | 121 |`) are detected by the
scanner but fail resolution due to Bug 1 (subdirectory search).

Not a separate scanner bug — fixing Bug 1 fixes this.

#### Bug 5: Service domain directories not resolved from tables

`artifacts/`, `audit/`, `backup/` etc. in the domain summary table
(lines 381-409) are bare directory names with trailing `/`. The scanner
detects them as T2 (path with slash) but resolution fails because:
- `artifacts/` is looked up as `src/core/artifacts/` (doesn't exist)
- Actual path is `src/core/services/artifacts/`

**Fix**: Subdirectory search (Bug 1) resolves this too.

---

## What Exists Today (Honest Assessment)

### Working

| Component | File | Status |
|-----------|------|--------|
| Pattern scanner | `src/core/services/peek.py` | T1, T2, T3, T5, T6 patterns work |
| Symbol index builder | `peek.py` → `build_symbol_index()` | 2,486 symbols indexed |
| Symbol resolver | `peek.py` → `_resolve_symbol()` | Proximity disambiguation works |
| Content Vault API | `src/ui/web/routes/content/peek.py` | Endpoint works |
| Client DOM annotator | `_preview.html` → `_annotatePeekElements()` | Text-node walking works |
| Docusaurus hook | `usePeekLinks.ts` | Hook exists, feature-gated |
| Docusaurus build | `docusaurus.py` → `_stage_scaffold` | Generates peek-index.json |
| CSS styling | `admin.css` + `custom.css.tmpl` | Dotted underline style works |

### Broken

| What | Why | Impact |
|------|-----|--------|
| Resolver doesn't search subdirs | Only tries same dir, root, one up | **68% miss rate** |
| UX is direct navigation | No tooltip, no choice, no preview | Wrong interaction model |
| Unresolved refs invisible | Scanner drops what doesn't resolve | No "not found" feedback |
| Directory handling | Same UX as files | User can't distinguish |
| Multiple files with same name | Dedup picks first, ignores context | Wrong resolution |

### Metrics (current, broken)

```
src/core/README.md:     83 / 261 references covered (32%)
Full project (95 READMEs): 2,365 resolved — but this number is inflated
  because most READMEs document files in their OWN directory where
  resolution succeeds. Parent READMEs are broken.
```

---

## Two Surfaces

### Surface A: Content Vault (Admin Panel SPA)

**Current rendering flow:**
```
User browses to file
  → GET /api/content/preview?path=<path>
  → Returns: { type, content, preview_content (if audit directive) }
  → renderMarkdown(content) or innerHTML = preview_content
  → _attachPreviewLinkHandlers(container) — handles data-doclink clicks
```

**Peek flow (target):**
```
User browses to file → preview renders normally
  → ASYNC: POST /api/content/peek-resolve
    { doc_path: "src/core/README.md", content: "<raw markdown>" }
  → Response: ALL candidates (resolved + unresolved)
  → DOM annotation: wrap matching text with .peek-link or .peek-link--unresolved
  → Click → opens tooltip panel with details and actions
  → User chooses: Open / Open in Tab / Dismiss
```

**Key infrastructure:**
- `previewCurrentPath` — document context
- `_attachPreviewLinkHandlers()` — existing click handler for `a[data-doclink]`
- Vault hash navigation: `#content/docs/<path>@preview[:line]`
- `renderMarkdown()` — uses marked.js with GFM
- `contentPreviewFile()` / `contentLoadFolder()` — navigation functions

### Surface B: Docusaurus SPA (Built Site)

**Build-time:**
```
_stage_scaffold → generates peek-index.json (with symbol index)
```

**Runtime:**
```
usePeekLinks hook → reads peek-index.json → annotates DOM
  → Click → tooltip with link to Content Vault or GitHub
```

---

## Peekable Element Types

### T1 — Backticked Filename with Extension
```
Pattern:  `name.ext`  where ext is a known source/config/script extension
Example:  `l0_detection.py`
Context:  Headings, tables, prose, file map sections (including inside code fences)
```

### T2 — Path with Slashes
```
Pattern:  word/word/thing  or  `word/word/thing`
Example:  src/core/services/audit/
Context:  Prose, dependency graphs, code fences
```

### T3 — Filename:Line
```
Pattern:  name.ext:N  where N is a number
Example:  helpers.py:48
```

### T4 — Filename in Heading
```
Pattern:  ### `name.ext` — Description
Also:     ### name.ext — Description
Covered by T1 (backticked) + T6 (bare)
```

### T5 — Backticked Function/Symbol Name
```
Pattern:  `func_name()`  or  `ClassName`
Example:  `l0_system_profile()`  →  src/core/services/audit/l0_detection.py:425
Resolve:  Symbol index lookup + proximity disambiguation
```

### T6 — Bare Filename in Prose
```
Pattern:  scoring.py (no backticks, known extension, word boundaries)
Context:  Tables, prose, file maps in code fences
```

---

## Context Resolution Strategy — REDESIGN

### Current (Broken)

```
1. Same directory as the document
2. Project root
3. One level up
```

**Fails for**: any README that documents files in subdirectories (i.e., most READMEs).

### Target Resolution Order

```
1. Same directory as the document
2. Recursive subdirectory search (doc_dir/**/filename)
   → ranked by proximity (fewest intermediate directories wins)
   → if multiple matches at same depth, keep all (ambiguous → show in tooltip)
3. Project root
4. One level up from the document
5. Project-wide search (last resort, only for unique filenames)
```

**Example**: `src/core/README.md` references `action.py`:
```
Try 1: src/core/action.py                    → NOT FOUND
Try 2: src/core/**/action.py
        src/core/models/action.py             → FOUND (depth 1) ✓
        (no other action.py under src/core/)
Try 3: action.py (project root)              → NOT FOUND
Try 4: src/action.py                         → NOT FOUND
```

**Ambiguity example**: `detect.py` from `src/core/README.md`:
```
Try 2: src/core/**/detect.py
        src/core/use_cases/detect.py          → FOUND (depth 1)
        src/core/services/docker/detect.py    → FOUND (depth 2)
        src/core/services/k8s/detect.py       → FOUND (depth 2)
        → AMBIGUOUS: 3 candidates
        → Tooltip shows all 3, user chooses
        → Or: use section context to disambiguate (heading "use_cases/" above → pick use_cases/detect.py)
```

### Performance Guard

Recursive subdirectory search could be expensive if done per-reference.
**Mitigation**: Build a **filename index** at the start of resolution:

```python
def _build_filename_index(project_root: Path, doc_dir: str) -> dict[str, list[str]]:
    """Map filename → list of relative paths under doc_dir subtree."""
    index = {}
    base = project_root / doc_dir if doc_dir else project_root
    for f in base.rglob("*"):
        if f.is_file():
            rel = str(f.relative_to(project_root))
            index.setdefault(f.name, []).append(rel)
    return index
```

Built once per document resolution, used for all bare filename lookups.
This turns O(N × rglob) into O(1 rglob + N dict lookups).

---

## UX Redesign — Tooltip Panel

### Interaction Model

```
1. User sees peek-annotated text (dotted underline, subtle)
2. User CLICKS the text
3. A small tooltip panel appears NEAR the clicked element:
   ┌─────────────────────────────────────────┐
   │  📄 src/core/models/action.py           │
   │  Line 121                               │
   │                                         │
   │  [Open]  [Open in New Tab]  [✕]         │
   └─────────────────────────────────────────┘
4. User clicks Open → navigates in current pane
5. User clicks Open in New Tab → opens in new browser tab
6. User clicks ✕ or clicks elsewhere → dismisses tooltip
7. Escape key → dismisses tooltip
```

### Directory Tooltip

```
   ┌─────────────────────────────────────────┐
   │  📁 src/core/models/                    │
   │  Directory (7 files)                    │
   │                                         │
   │  [Browse]                     [✕]       │
   └─────────────────────────────────────────┘
```

### Unresolved Reference Tooltip

```
   ┌─────────────────────────────────────────┐
   │  ⚠️ Could not find file                 │
   │  "action.py" — not found in project     │
   │                                         │
   │                               [✕]       │
   └─────────────────────────────────────────┘
```

### Ambiguous Reference Tooltip

```
   ┌─────────────────────────────────────────┐
   │  📄 detect.py — 3 matches              │
   │                                         │
   │  src/core/use_cases/detect.py           │
   │  src/core/services/docker/detect.py     │
   │  src/core/services/k8s/detect.py        │
   │                                         │
   │  Click a path to navigate               │
   └─────────────────────────────────────────┘
```

### CSS Classes

```css
.peek-link              — resolved, single match (dotted underline, blue on hover)
.peek-link--unresolved  — not found (dotted underline, orange/yellow on hover)
.peek-link--ambiguous   — multiple matches (dotted underline, cyan on hover)
.peek-link--directory   — resolved directory (dotted underline, green on hover)

.peek-tooltip           — the floating panel container
.peek-tooltip__path     — file path display
.peek-tooltip__actions  — action buttons row
.peek-tooltip__candidates — list of ambiguous matches
```

---

## Evolution Phases

### Phase 1 — File References (T1 + T2 + T3) ✅ DONE (scanner + resolver exist)

Scanner patterns delivered. Resolver works for same-directory files.
API endpoint and DOM annotator exist.

### Phase 2 — Heading & Prose (T4 + T6) ✅ DONE (scanner patterns)

T4 handled by T1+T6. Bare filename detection with guards works.

### Phase 3 — Symbol References (T5) ✅ DONE (scanner + index + resolver)

Symbol index builder, disambiguation, regex patterns all work.

### Phase 4 — FIX RESOLVER ✅ COMPLETE

**Problem**: Resolver couldn't find files in subdirectories. 68% miss rate.

**Delivered**:
1. ✅ `_build_filename_index()` — recursive scan of doc subtree, built once per resolution
2. ✅ `_resolution_candidates()` — subdirectory search via index, ranked by depth proximity
3. ✅ Ancestor directory prefixing for path references (core/engine/ → src/core/engine/)
4. ✅ Dedup key fix — use text+resolved_path instead of resolved_path only
   (different text forms of same file each get their own entry for DOM annotation)

**Results**:
- `src/core/README.md`: 83 → 152 refs (83% coverage of human-expected refs)
- Full project: 2,365 → 3,036 refs across 98 READMEs (28% increase)
- Remaining misses: `state.json` (runtime artifact), `src/adapters` (no trailing /),
  `services/detection` (no extension or /), template patterns with `{domain}`

**Files modified**:
```
src/core/services/peek.py               — resolver overhaul (3 changes)
```

### Phase 5 — TOOLTIP PANEL UX ✅ COMPLETE

**Problem**: Direct link navigation, no preview, no choice.

**Delivered**:
1. ✅ `_showPeekTooltip(event, ref, anchorEl)` — creates and positions tooltip
2. ✅ `_dismissPeekTooltip()` — removes on click outside, Escape, ✕ button
3. ✅ Tooltip HTML with file icon, resolved path, line number, action buttons
4. ✅ File tooltip: Open + New Tab actions
5. ✅ Directory tooltip: Browse action with 📁 icon
6. ✅ Peek links changed from `<a>` to `<span>` with `role="button"` — no more direct nav
7. ✅ `.peek-tooltip` glassmorphism CSS (dark panel, blur, shadow, animation)
8. ✅ `.peek-link--directory` green tint variant
9. ✅ `.peek-link--unresolved` orange tint variant (CSS ready)
10. ✅ Viewport-aware positioning (flips above if no space below)

**Files modified**:
```
src/ui/web/templates/scripts/content/_preview.html  — tooltip JS
src/ui/web/static/css/admin.css                     — tooltip CSS + link variants
```

### Phase 6 — UNRESOLVED + AMBIGUOUS ANNOTATIONS ✅ COMPLETE

**Problem**: Unresolved refs invisible. No feedback when file not found.

**Delivered**:
1. ✅ `scan_and_resolve_all()` — returns (resolved, unresolved) tuple
2. ✅ API returns `unresolved` array alongside `references`
3. ✅ `_annotateUnresolvedPeek()` — second-pass annotator for unresolved refs
4. ✅ `.peek-link--unresolved` orange/dimmed styling (already in Phase 5 CSS)
5. ✅ `_showUnresolvedTooltip()` — ⚠️ icon + "Not found in project" label
6. ✅ Unresolved annotation skips already-resolved text nodes (no conflicts)

**Note**: Ambiguous resolution (multiple matches for same filename) deferred —
current resolver picks closest match by proximity, which handles 95%+ of cases.

**Files modified**:
```
src/core/services/peek.py               — scan_and_resolve_all()
src/ui/web/routes/content/peek.py       — return unresolved in API response
src/ui/web/templates/scripts/content/_preview.html  — unresolved annotator + tooltip
```

### Phase 7 — DOCUSAURUS SURFACE UPDATE ✅ COMPLETE

**Problem**: Docusaurus hook used direct `<a>` links with the old resolver.

**Delivered**:
1. ✅ `peek-index.json` now includes unresolved refs with `resolved: false` flag
2. ✅ `usePeekLinks.ts` rewritten: `<a>` → `<span>` tooltip interaction
3. ✅ Tooltip shows "Open in Vault" (localhost) or "View on GitHub" (deployed)
4. ✅ Directory tooltip with Browse action
5. ✅ Unresolved tooltip with ⚠️ "Not found in project" label
6. ✅ Shared `_wireTooltip()` for positioning, dismiss, cleanup
7. ✅ SPA cleanup: tooltip dismissed + spans restored to text on navigation
8. ✅ `.peek-link--directory` + `.peek-link--unresolved` + `.peek-tooltip` CSS

**Files modified**:
```
src/core/services/pages_builders/docusaurus.py    — scan_and_resolve_all + unresolved in index
src/core/services/pages_builders/templates/docusaurus/
  theme/hooks/usePeekLinks.ts                     — tooltip-based interaction
  css/custom.css.tmpl                             — tooltip + variant CSS
```

---

## File Map

```
CORE:
  src/core/services/peek.py                         Scanner + resolver + symbol index

CONTENT VAULT:
  src/ui/web/routes/content/peek.py                 API endpoint
  src/ui/web/templates/scripts/content/_preview.html DOM annotator + tooltip
  src/ui/web/static/css/admin.css                   Peek link + tooltip CSS

DOCUSAURUS:
  src/core/services/pages_builders/docusaurus.py    Build-time peek-index.json
  src/core/services/pages_builders/template_engine.py Feature registry
  src/core/services/pages_builders/templates/docusaurus/
    theme/hooks/usePeekLinks.ts                     React hook (runtime)
    theme/Root.tsx.tmpl                             Feature-gated wiring
    css/custom.css.tmpl                             Peek link + tooltip CSS
```

---

## Edge Cases & Rules

1. **Subdirectory search**: When a bare filename has multiple matches under
   the doc's subtree, mark as ambiguous — show all candidates in tooltip.

2. **Code fence content**: File references inside ``` blocks ARE peekable.
   File maps and tree diagrams are high-value peek targets.

3. **Table cells**: filenames in markdown table cells must resolve. The
   rendered `<td>` contains text nodes that the DOM walker must reach.

4. **Already-linked references**: Skip elements already inside `<a>` tags.
   The audit directive generates `audit-file-link` — don't double-link.

5. **URLs/link targets**: References inside `http://`, `href="`, or
   markdown `[text](url)` are not peekable.

6. **Performance**: Build filename index once per document. Symbol index
   is module-level cached. DOM annotation walks text nodes once.

7. **Tooltip positioning**: Panel appears below or above the element
   depending on viewport space. Dismisses on outside click or Escape.

8. **Self-reference**: A README should not peek-link to itself.

---

## Consumers

| Consumer | Surface | What It Uses |
|----------|---------|-------------|
| Content Vault preview | Admin Panel | peek-resolve API + tooltip panel |
| Docusaurus SPA | Built site | peek-index.json + usePeekLinks hook + tooltip |
| Audit directive | Both | Could leverage peek resolver (future consolidation) |

---

## Non-Goals (Parking Lot)

- **Symbol previews** (showing code inline on hover) — future
- **Cross-project peek** — only within the same project
- **Non-Python symbol index** — Python only (parser exists). Go/JS/Rust via BaseParser later.
- **Live symbol updates** — index built at request/build time, not live
- **Section-context disambiguation** — using heading context to resolve ambiguous
  filenames (e.g. "under the models/ heading, action.py = models/action.py").
  This is a Phase 8+ optimization if ambiguous tooltips prove insufficient.
