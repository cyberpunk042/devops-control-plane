# Focus Tracking & Progressive Enrichment — Content Vault

**Status**: 🔧 IN PROGRESS — fixing integration bugs found during testing  
**Date**: 2026-03-05  
**Depends on**: Contextual Glossary Stage 1+2 (✅ complete)  
**Scope**: Fix broken focus tracking, extend to all view modes and file types,
establish progressive enrichment architecture for outline ↔ peek integration.

---

## 0. The User's Words (verbatim)

> "The Content Vault file preview focus tracking doesn't seem to work.
>  It should track the line I have last clicked and should highlight it,
>  show its focused / select and it should reflect as a line in the URL
>  and from this it will allow us to use the index data to actually place
>  the focus in the outline and glossary."

> "So as we navigate in the edit or in the raw or preview mode we actually
>  follow in the glossary / outline."

> "If I chose to click on a peek element like 'Receipt' it would select it
>  in the glossary / outline based on the current view."

> "The server toggle is about being able to disable the extensive indexing
>  system part when on a less powerful system … but it should not block
>  the experience."

> "Multi level cache with multi enrichment level stage per level and the
>  possibility to be receiving each data when it is ready at the moment
>  it ready and yet never break the experience."

> "Its for all browser views and its for all details for all filetypes."

---

## 1. Confirmed Investigation

### Bug A — `_mapHeadingsToSourceLines()` fails on inline formatting

**File**: `_preview.html` lines 26–44  
**Mechanism**: Compares `h.textContent.trim().toLowerCase()` (DOM) against
`line.substring(prefix.length).trim().toLowerCase()` (source markdown).

**Confirmed evidence**:

Source markdown heading:
```markdown
### `context.py` — Project Root Singleton (37 lines)
```

After `marked.parse()`, the DOM `<h3>` contains:
```html
<h3><code>context.py</code> — Project Root Singleton (37 lines)</h3>
```

`h.textContent` → `"context.py — Project Root Singleton (37 lines)"` (no backticks)  
Source comparison text → `` "`context.py` — Project Root Singleton (37 lines)" `` (WITH backticks)

**These are NOT equal → heading never gets `data-source-line` →
IntersectionObserver has nothing to observe for this heading.**

**Scope of damage**: Measured across project READMEs:
- `src/core/README.md`: **10 / 41** headings have inline formatting (24%)
- `docs/README.md`: **20 / 53** headings have inline formatting (38%)
- Any heading with backticks, `**bold**`, `*italic*`, or HTML entities fails

These are exactly the headings that describe files and code — the most important
ones for peek and glossary integration.


### Bug B — `preview_content` vs `data.content` mismatch

**File**: `_preview.html` lines 402–414  
**Confirmed evidence**:

Line 406: `renderMarkdown(data.preview_content || data.content)` — rendered DOM
may be from `preview_content` (which has audit directives injected/resolved).

Line 411: `const sourceText = data.content || ''` — source mapping uses the
ORIGINAL content (without audit directives).

When `preview_content` exists, the DOM has **additional or modified content**
compared to `data.content`. Heading positions shift. The naive text-matching
mapper tries to match DOM headings against the wrong source → mismatches.

**Server evidence** (`preview.py` lines 106–136): `preview_content` is generated
when `auto_inject_directive()` injects `:::audit-data` blocks into a copy of the
content, then `resolve_audit_directives()` replaces those with HTML. The injected
content can add new headings or shift existing heading line numbers.


### Bug C — No click-to-focus handler in rendered preview

**File**: `_preview.html` — full file searched  
**Confirmed evidence**: `grep` for `click.*_contentFocusLine` and
`addEventListener.*click.*focusLine` returned **zero results**.

The only two channels that set `_contentFocusLine` in preview mode:
1. IntersectionObserver (Bug A: broken)
2. Peek tooltip "Open" button (`line 1115`) — but only when ACTION is taken,
   not when the peek element is first clicked

**Consequence**: Clicking anywhere in rendered markdown preview does NOT
update `_contentFocusLine`, does NOT update the URL hash, does NOT sync
the glossary.


### Bug D — Peek click does not sync to glossary

**File**: `_preview.html` lines 586–590  
**Confirmed evidence**: The peek span's `onclick` handler calls
`_showPeekTooltip(e, ref, span)` only. It does NOT:
- Set `_contentFocusLine` to the current source line
- Call `_glossaryUpdateActive()` to highlight the nearest outline node

The peek element has `data-peek-line` but that's the **target file's line**
(where the reference points to), not the **current document's source line**
where the element appears.


### Bug E — Mode-switch resets focus line to 0

**File**: `_preview.html` lines 389-390 (edit mode) and lines 419-420 (raw mode)  
**Confirmed evidence**:

```javascript
const editFocusLine = window._contentFocusLine || 0;
window._contentFocusLine = 0;  // ← RESET
```

The focus line is consumed for Monaco's initial cursor position but then
zeroed out. The glossary loses its active node until the user moves the cursor
in Monaco (which triggers `onDidChangeCursorPosition` and re-sets it).

**Gap window**: Between mode-switch and first cursor move, `_contentFocusLine`
is 0 and the glossary shows no active node.


### Non-Bug: Server Toggle Independence (Confirmed Correct)

**Confirmed evidence**:
- Outline API (`routes/content/outline.py` line 25): NO peek gate check
- Glossary API (`routes/content/outline.py`): NO peek gate check
- Peek API (`routes/content/peek.py` line 43): Gated by `is_peek_index_enabled()`

The outline and glossary systems are **already independent** of the peek toggle.
Disabling peek does NOT disable outline/glossary. **No change needed here.**


---

## 2. Architecture: The Focus Line Contract

### 2.1 Universal Focus Tracking

All user interactions that imply "I'm looking at this line" must flow through
one contract point:

```
┌─────── Input Sources ──────────────────────────────────────────────┐
│                                                                     │
│  Preview (rendered markdown):                                       │
│    ├─ IntersectionObserver on headings (scroll) → nearest heading   │
│    └─ Click on any element → nearest data-source-line ancestor      │
│                                                                     │
│  Raw / Edit (Monaco):                                               │
│    └─ onDidChangeCursorPosition → cursor line number                │
│                                                                     │
│  Peek interaction:                                                  │
│    └─ Click on .peek-link → source line of clicked element          │
│                                                                     │
│  Glossary click:                                                    │
│    └─ Click on outline node → that node's line number               │
│       (already implemented in _glossaryClickNode)                   │
│                                                                     │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                    window._contentFocusLine = line
                              │
                    ┌─────────┴─────────┐
                    │  Output Effects   │
                    ├───────────────────┤
                    │ 1. URL hash       │  @mode:LINE (debounced 500ms)
                    │ 2. Glossary sync  │  _glossaryUpdateActive(path, line)
                    │ 3. Visual glow    │  .preview-line-focused / .preview-heading-tracked
                    └───────────────────┘
```

### 2.2 Progressive Enrichment Tiers

These tiers exist today but are not unified. This plan formalizes them:

| Tier | Source | API | When Ready | What It Provides | Gated by Toggle? |
|------|--------|-----|------------|------------------|-------------------|
| T0   | Outline (regex/AST strategies) | `/api/content/outline` | Instant | Structural skeleton (headings, classes, functions) | **No** — always available |
| T1   | Project Index file/dir maps | `/api/content/peek-refs` (GET, cache hit) | ~100ms (disk cache) | Resolved peek links | Yes |
| T2   | On-demand peek resolution | `/api/content/peek-resolve` (POST, fallback) | ~500ms | Resolved peek links when cache miss | Yes |
| T3   | T5 symbol worker | Background thread | Seconds | Deep symbol resolution | Yes |

**Rules**:
1. T0 is ALWAYS available. The glossary works even if T1-T3 are all disabled.
2. Each tier enriches the UI when ready, non-destructively.
3. Missing tiers never block the experience — the UI shows what's available.
4. The outline is the skeleton; everything else decorates it.
5. Focus tracking operates on T0 data (outline nodes) exclusively — it
   doesn't need peek or symbols to work.


---

## 3. Implementation Plan

### Phase 1: Fix Heading ↔ Source Line Mapping _(Bug A + Bug B)_

**Problem**: Text-content matching between DOM headings and source markdown
fails when headings contain inline formatting (backticks, bold, italic).
Also fails when `preview_content` shifts heading positions.

**Fix**: Replace text-content matching with **positional matching**:

1. Walk source markdown lines → collect all heading lines with their
   1-indexed line numbers and levels. Strip inline formatting for comparison.
   ```
   Source line 206: "### `context.py` — Project Root Singleton (37 lines)"
   → { line: 206, level: 3, text: "context.py — project root singleton (37 lines)" }
   ```

2. Walk rendered DOM `h1`–`h6` elements in document order.

3. For each DOM heading, strip the markdown formatting from the source
   comparison text (remove backticks, `**`, `*`, etc.) before comparing.
   This way `context.py` (DOM textContent) matches `context.py` (source
   with backticks stripped).

4. Also handle the `preview_content` case: when `preview_content` is used
   for rendering, we still use `data.content` for source-line mapping, BUT
   we need to be aware that audit-injected content may add elements.
   **Mitigation**: The heading text matching (with inline-stripped comparison)
   is resilient because we match by text, not by position. Extra content
   injected by audit directives does NOT change the heading text itself.

**Exact code change location**: `_preview.html` function `_mapHeadingsToSourceLines()`
(lines 26–44). Single function replacement.

**What changes**:
- Strip inline markdown formatting (`backticks`, `**bold**`, `*italic*`,
  `<tags>`) from the source line before comparison
- This is a single `replace(/`[^`]+`/g, ...)` type transform

**What does NOT change**:
- The IntersectionObserver setup (`_contentObservePreviewLines`) — untouched
- The observer callback logic — untouched
- The visual `.preview-heading-tracked` style — untouched


### Phase 2: Click-to-Focus in Rendered Preview _(Bug C)_

**Problem**: No click handler in rendered markdown preview sets `_contentFocusLine`.

**Fix**: Add a delegated click handler on the `.content-preview-rendered` container.

**Logic**:
1. On click, check if the clicked element (or any ancestor up to the container)
   has `data-source-line` → use that line number directly.
2. If not, walk BACKWARD through preceding sibling elements and their
   children to find the nearest element with `data-source-line`.
3. If found → set `_contentFocusLine`, call `_glossaryUpdateActive()`,
   update URL hash (debounced).
4. If NOT found (clicked before first heading) → set line 1.
5. Add visual feedback: `.preview-line-focused` class on the heading
   that "owns" the clicked section.

**Exact code change location**: After `_attachPreviewLinkHandlers(body)` call
(line 408), add the new click handler. Or add it inside
`_contentObservePreviewLines()` since that's where tracking is set up.

**What changes**:
- New function `_contentPreviewClickHandler(container)` — ~30 lines
- Called from `contentPreviewFile()` when rendering markdown preview
- New CSS class `.preview-line-focused` in `admin.css`

**What does NOT change**:
- `_attachPreviewLinkHandlers()` — existing link handler untouched
- Peek annotation — untouched
- Monaco cursor handler — untouched


### Phase 3: Peek Click → Glossary Sync _(Bug D)_

**Problem**: Clicking a peek element shows tooltip but doesn't sync glossary.

**Fix**: In the peek `span.onclick` handler (line 586), BEFORE showing the
tooltip:
1. Walk from the peek span backward to find the nearest heading with
   `data-source-line` (same logic as Phase 2).
2. Set `_contentFocusLine` to that source line.
3. Call `_glossaryUpdateActive(previewCurrentPath, sourceLine)`.

**This makes the peek click behave like any other content click for
focus-tracking purposes.** The tooltip still appears on top, but the
glossary simultaneously highlights which section the user is in.

**Exact code change location**: `_preview.html` span.onclick in
`_annotatePeekElements()` (line 586–590). Add 3 lines before the
`_showPeekTooltip` call.

**What changes**:
- 3 lines added to existing onclick handler
- New helper function `_findNearestSourceLine(element)` shared with Phase 2

**What does NOT change**:
- `_showPeekTooltip()` — untouched
- Peek annotation logic — untouched
- Peek API — untouched


### Phase 4: Mode-Switch Focus Persistence _(Bug E)_

**Problem**: Switching modes (preview → raw → edit) resets `_contentFocusLine`
to 0, losing glossary sync until user interacts with Monaco.

**Fix**: After Monaco initializes (or after preview renders), restore the
previous focus state:

1. Change lines 389-390 and 419-420: instead of `window._contentFocusLine = 0`,
   keep the value. Monaco's `focusLine` option already positions the cursor.
   The `onDidChangeCursorPosition` handler fires on initial cursor placement,
   which will re-set `_contentFocusLine` and call `_glossaryUpdateActive()`.

   Actually — **simpler**: just DON'T reset to 0. The value is consumed by
   Monaco (passed as `focusLine`), and Monaco's cursor handler will fire
   immediately with the correct line. The reset is unnecessary.

2. For preview mode (when switching FROM raw/edit TO preview): the focus line
   is already used by `_contentScrollToSourceLine()` (line 414). After scroll,
   `_glossaryUpdateActive()` should fire. Currently it doesn't because the
   IntersectionObserver takes time to fire. **Fix**: call
   `_glossaryUpdateActive()` directly after `_contentScrollToSourceLine()`.

**Exact code change locations**:
- Line 390: `window._contentFocusLine = 0` → remove this line
- Line 420: `window._contentFocusLine = 0` → remove this line
- After line 414: add `_glossaryUpdateActive(path, window._contentFocusLine || 0)`

**What changes**: 3 lines (2 removals, 1 addition)

**What does NOT change**:
- Monaco creation — untouched
- `contentSetPreviewMode()` — untouched (it calls `contentPreviewFile()` which
  handles everything)


### Phase 5: Non-Text File Glossary Handling _(Edge Cases)_

**Problem**: Non-text files (image, video, audio, binary) have no line concept.
The glossary panel should handle this gracefully.

**Current behavior**: The glossary loads for the containing folder (glossary mode)
or the file (outline mode). For binary files, the outline is empty → "No outline
data" message.

**Fix**: When a file is opened that has no outline data AND `_contentFocusLine = 0`:
- In glossary mode: highlight the file entry in the glossary tree
- In outline mode: show a contextual message like "📦 Binary file — no outline"
  instead of the generic "No outline data"

**Exact code change location**: `_glossary.html` — `_glossaryRenderOutline()`
and `_glossaryUpdateActive()`.

**What changes**: ~10 lines of edge-case handling

**What does NOT change**:
- No API changes
- No backend changes
- Outline extraction — untouched


### Phase 6: Visual Polish _(CSS)_

**New CSS class**: `.preview-line-focused` for the clicked heading in preview.

**Style**: Subtle left-border highlight (similar to existing
`.preview-heading-tracked` but distinct color — amber/gold vs blue).
This shows "you clicked here" (amber) vs "you scrolled past here" (blue).

**Exact code change location**: `admin.css` after `.preview-heading-tracked`
block (line 3599).


---

## 4. Files Changed

| File | Phase | What |
|------|-------|------|
| `_preview.html` | 1 | Fix `_mapHeadingsToSourceLines()` — strip inline markdown formatting before comparison |
| `_preview.html` | 2 | New `_contentPreviewClickHandler()` + helper `_findNearestSourceLine()` |
| `_preview.html` | 3 | Add 3 lines to peek span.onclick — sync glossary on peek click |
| `_preview.html` | 4 | Remove 2 `_contentFocusLine = 0` resets, add 1 glossary sync call |
| `_glossary.html` | 5 | Edge-case handling for binary/no-outline files |
| `admin.css` | 6 | `.preview-line-focused` class |

**No backend changes.** No new APIs. No new dependencies. No new files.


## 5. Implementation Order

```
Phase 1 (fix heading mapping) ← BLOCKER — until this works, observer is dead
    ↓
Phase 2 (click-to-focus) + Phase 3 (peek→glossary) — share _findNearestSourceLine
    ↓
Phase 4 (mode-switch persistence) — independent, small
    ↓
Phase 5 (non-text edge cases) — independent, small
    ↓
Phase 6 (CSS polish) — parallel with anything
```


## 6. What This Explicitly Does NOT Touch

- **Outline extraction strategies** (Stage 1+2) — complete, no changes
- **Peek resolution backend** (`peek.py`, `project_index.py`) — no changes
- **Peek API toggle** (`is_peek_index_enabled`) — no changes
- **Server settings** — no changes
- **Glossary API endpoints** — no changes
- **Monaco integration** — cursor handler already works, no changes
- **URL hash format** — already correct (`@mode:line`), no changes


## 7. Testing Criteria

| # | Test | Verify |
|---|------|--------|
| 1 | Open `src/core/README.md` in preview | Headings with backticks (e.g. `` `context.py` ``) get `data-source-line` |
| 2 | Scroll in preview | `.preview-heading-tracked` follows viewport position |
| 3 | Click a paragraph between headings | `_contentFocusLine` updates to nearest heading line, glossary highlights |
| 4 | Click a peek element | Glossary highlights the section containing the peek element |
| 5 | Switch preview → raw | Focus line persists, glossary shows same active node |
| 6 | Switch raw → edit | Focus line persists, Monaco cursor at same line |
| 7 | Switch edit → preview | Preview scrolls to the line, glossary highlights |
| 8 | Reload with `#content/docs/src/core/README.md@preview:206` | Preview scrolls to line 206, glossary highlights matching node |
| 9 | Disable peek in server settings | Glossary/outline still works, focus tracking still works |
| 10 | Open an image file | Glossary shows "Binary file" message, no crash |


## 8. Progressive Enrichment — Architectural Foundation

This plan establishes the **foundation** for the multi-tier enrichment:

**What exists after this plan**:
- T0 (outline) works reliably for all file types — ALWAYS available
- Focus tracking works in all modes — ALWAYS available
- Glossary sync works from any interaction — ALWAYS available
- Peek enriches when available, doesn't block when disabled
- Each tier is independent, non-destructive, and additive

**Future extension points** (not in this plan's scope):
- T5 symbols → when ready, add symbol nodes to the outline tree
- Real-time invalidation → content save triggers outline cache bust
- WebSocket push → server notifies client when enrichment tiers complete
- Cross-file reference graph → outline nodes link to their peek references

The key architectural decision: **the outline is the skeleton, focus tracking
is the nervous system, and enrichment tiers are layers of muscle**. Each can
operate independently. The skeleton and nerves must work first.
