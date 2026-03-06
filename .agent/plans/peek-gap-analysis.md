# Peek Feature — Full Gap Analysis

> **Created**: 2026-03-06
> **Goal**: 100% feature parity with the Content Vault. No exceptions.
> **Reference (gold standard)**: `src/ui/web/templates/scripts/content/_preview.html` lines 620–1839
> **Target**: `src/core/services/pages_builders/templates/docusaurus/theme/hooks/usePeekLinks.ts`
> **Data pipeline**: `src/core/services/pages_builders/docusaurus.py` (peek-index.json generation)
> **Resolver**: `src/core/services/peek.py` (scan + resolve)

---

## Architectural Requirement: Dev/Live Mode Toggle

When running in localhost mode (`IS_LOCAL = true`), the site will have a **dev badge**
(like the admin panel). Clicking it toggles between:

- **Dev mode** (default when local): ALL action buttons route to the Content Vault
  - "Open" → opens in Vault preview
  - "Edit" → opens in Vault editor
  - "Browse" → opens folder in Vault browser
  - "New Tab" → opens Vault hash route in new tab

- **Live mode** (toggled, or default when published): ALL action buttons route to GitHub
  - "Open" → opens GitHub blob view
  - "Edit" → opens GitHub edit URL
  - "Browse" → opens GitHub tree view
  - "New Tab" → opens GitHub in new tab

This is NOT two sets of buttons. It is ONE set of buttons whose targets change
based on the active mode. The button labels stay the same; only the href changes.

When NOT on localhost (published site), there is no toggle — it's always live mode.

---

## Current State Summary

> ⚠️ These metrics were measured ONCE before fixes. The "projected"
> values were NEVER re-measured. The ✅ FIXED markers were LIES.
> See `peek-roadmap.md` for the real tracker.

| Metric | Original Value | Projected After Fix | Actually Verified? |
|---|---|---|---|
| Total refs across all pages | 7,513 | — | ❌ NOT RE-MEASURED |
| Resolved refs | 2,478 (33%) | ~80%+ | ❌ NOT RE-MEASURED |
| Unresolved refs | 5,035 (67%) | ~20% | ❌ NOT RE-MEASURED |
| With outline data | 1,618 | ~1,715 | ❌ NOT RE-MEASURED |
| With dir_listing | 408 | 408 | ❌ NOT RE-MEASURED |
| With doc_url | 78 (3%) | ~96% | ❌ NOT RE-MEASURED |
| Truncated garbage texts | ~4,029 | 0 | ❌ NOT RE-MEASURED |

---

## GAP 1: Bare Regex Produces Truncated Garbage (CRITICAL)

### What's happening
The `_RE_T2_BARE` regex in `peek.py` line 125-127:
```python
_RE_T2_BARE = re.compile(
    r"(?<![(\\\"'`/])([A-Za-z0-9_.][A-Za-z0-9_./-]*/[A-Za-z0-9_./-]*)(?![)\"'`])"
)
```

When a path like `core/services/git/ops.py` is inside backticks in markdown:
```markdown
Check `core/services/git/ops.py` for details
```

**Both regexes fire:**
- `_RE_T2_BACKTICK` correctly captures: `core/services/git/ops.py` ✅
- `_RE_T2_BARE` captures TRUNCATED: `ore/services/git/ops.p` ❌

The bare regex's negative lookbehind `(?<![...`])` strips the char after the backtick,
and the negative lookahead `(?![...`])` strips the char before the closing backtick.

Since these are DIFFERENT strings, `seen_texts` doesn't dedup them. Both get added.
The truncated string can't resolve → shows as "Not found in project."

### Impact
- ~4,029 false "Not found in project" annotations across 99 pages
- Clutters the page with broken underlines
- Makes the feature look completely broken

### Fix
In `scan_peek_candidates`, after T2 backtick matching completes, strip backtick 
delimiters from the line before running T2 bare. OR: add backtick to the LEADING
character class in the bare regex's positive character class, so backtick-adjacent
paths are captured fully. OR: skip bare T2 matching entirely on segments inside backticks.

---

## GAP 2: doc_url Nearly Empty (CRITICAL)

### What's happening
Only 78 out of 2,478 resolved refs have a `doc_url` field (3%).
This field maps a resolved file path to its Docusaurus route.

Without `doc_url`:
- The tooltip can't offer "📖 Open Page" (navigate within the site)
- The preview can't fetch rendered HTML from the site itself
- Falls back to GitHub raw / Monaco — much worse UX

### Root cause
The `_find_doc_route` function in `docusaurus.py` only maps paths that are
directly under the `docs_dir` with matching filenames. It doesn't handle:
- Nested category/subcategory structures
- Index files mapped to category routes
- Files in subdirectories that get flattened routes

### Fix
The `_find_doc_route` helper needs to properly map `resolved_path` →
Docusaurus route using the same routing logic Docusaurus uses:
- Strip `docs_dir` prefix
- Convert path separators to `/`
- Handle `index.md[x]` → parent directory route
- Handle category metadata

---

## GAP 3: Outline Data Missing for 35% of Resolved Refs

### What's happening
Only 1,618 of 2,478 resolved refs have `outline` data. Files like `git_ops.py`
resolve correctly but show only `.py` in the tooltip with no function/class list.

### Root cause
The outline extraction in the build pipeline (`docusaurus.py`) only runs for
files that have AST data pre-computed. Files without outline data show an empty
outline section.

### Content Vault comparison
The Content Vault uses **glossary data** to populate outlines. If glossary data
is missing, it falls back to an **async API call** (`/content/outline?path=...`).
The Docusaurus site has NO async fallback — it's static and can only use pre-baked data.

### Fix
The build pipeline must ensure outline extraction runs for ALL resolved file refs
during `peek-index.json` generation, not just those that happen to have
pre-computed AST data.

---

## GAP 4: Tooltip Buttons — Missing Per-Row Actions

### Content Vault tooltip has (per outline row):
```
▸ status()     [👁 Preview] [📄 Open] [📂 Browse] [↗ New Tab]
· log()        [👁 Preview] [📄 Open] [📂 Browse] [↗ New Tab]
· commit()     [👁 Preview] [📄 Open] [📂 Browse] [↗ New Tab]
```
Each outline row has 4 action buttons that operate at that specific line number.

### Docusaurus tooltip currently has:
```
status()
log()
commit()
```
Plain text items. Or clickable links to heading anchors if `doc_url` exists.
**No per-row action buttons.**

### Fix
Implement per-row action buttons in `_renderOutline()` — same 4 buttons as Vault:
- 👁 Preview → opens peek preview at that line
- � Open → in dev mode: Vault preview at line. In live mode: GitHub blob at line.
- 📂 Browse → in dev mode: Vault browser on parent. In live mode: GitHub tree.
- ↗ New Tab → opens target in new tab

---

## GAP 5: Tooltip Main Action Buttons — Must Match Content Vault 1:1

### Content Vault tooltip actions (bottom of tooltip):
For files:
```
[👁 Preview]  [📄 Open]  [📂 Browse]  [↗ New Tab]
```
For directories:
```
[👁 Preview]  [📂 Browse]  [↗ New Tab]
```

### Current Docusaurus tooltip has separate GitHub/Vault buttons — WRONG.
There should be ONE set of buttons. The targets change based on dev/live mode:

**Dev mode (localhost, toggle=dev):**
```
[👁 Preview]  [📄 Open (→ Vault)]  [✏️ Edit (→ Vault)]  [📂 Browse (→ Vault)]  [↗ New Tab]
```

**Live mode (published, or localhost toggle=live):**
```
[👁 Preview]  [📄 Open (→ GitHub)]  [✏️ Edit (→ GitHub)]  [📂 Browse (→ GitHub)]  [↗ New Tab]
```

If `doc_url` exists → add "📖 Open Page" button (navigates within site).
This always routes to the Docusaurus page regardless of mode.

### Fix
- Remove all separate "Open in Vault" / "↗ GitHub" buttons
- Create ONE unified button set that reads the current mode
- Dev badge JS variable: `window.__peekMode = 'dev' | 'live'`
- Each button resolves its href at click time based on mode

---

## GAP 6: Tooltip Dismiss Behavior — Missing Handlers

### Content Vault:
- ✅ Close button (✕)
- ✅ Click outside tooltip → dismiss (with `setTimeout` to avoid immediate dismiss)
- ✅ Escape key → dismiss
- ✅ Click another peek-link → dismiss current, open new

### Docusaurus:
- ✅ Close button (✕)
- ✅ Click outside → dismiss (in `_wireTooltip`)
- ✅ Escape key → dismiss (in `_wireTooltip`)
- ✅ Click another peek-link → dismiss current (in `showPeekTooltip`)

Status: This gap is actually CLOSED. Both have the same dismiss behavior.

---

## GAP 7: Preview Overlay — Feature Comparison

### Content Vault preview features:
1. ✅ Header: icon, path, line badge
2. ✅ Header actions: Jump to, Edit, Close
3. ✅ Directory: Browse Raw, Smart, Open README buttons
4. ✅ File types: markdown (rendered), text (Monaco), image, binary fallback
5. ✅ Directory: tabbed README + listing with clickable items
6. ✅ History pushState — Back button closes preview
7. ✅ Escape key closes
8. ✅ Backdrop click closes
9. ✅ Line tracking — live line badge updates on scroll
10. ✅ Heading-to-source mapping — scroll to specific headings
11. ✅ IntersectionObserver for visible line tracking

### Docusaurus preview features:
1. ✅ Header: icon, path, line badge
2. ✅ Header actions: Jump/Open, Edit, Close (mode-aware)
3. ✅ File types: markdown (rendered), source (Monaco), markdown via Marked CDN, image, binary fallback
4. ✅ Directory: tabbed README + listing (build-time data) with clickable items
5. ✅ History pushState — Back button closes
6. ✅ Escape key closes
7. ✅ Backdrop click closes
8. ✅ Line tracking in Monaco (cursor position → badge update + _peekCurrentLine)
9. ✅ Heading-to-source mapping for markdown preview (_mapHeadingsToSourceLines)
10. ✅ IntersectionObserver for markdown scroll tracking (_peekObserveLines)
11. ✅ Directory listing items are clickable
12. ✅ "Open README" button in directory preview header
13. ✅ Images handled (local API + GitHub raw)
14. ✅ Binary file fallback message
15. ✅ Truncation warning
16. ✅ _peekCurrentLine tracked, used by Jump/Edit actions
17. ✅ Scroll-to-line via _peekScrollToLine
18. ✅ Observer cleanup on close (_peekLineObserver disconnect)

---

## GAP 8: Annotation Coverage — Must Match Content Vault 1:1

### Content Vault annotates:
- Inside text paragraphs ✅
- Inside inline `<code>` elements ✅
- Inside list items ✅
- Inside table cells ✅
- Inside `<pre>` code blocks ✅ (file paths in code maps are clickable)
- Skips inside `<a>` tags ✅
- Skips inside `.peek-link` spans ✅
- Annotates class names (T5: PascalCase) ✅
- Annotates function calls (T5: `func_name()`) ✅

### Docusaurus currently:
- Inside text paragraphs ✅
- Inside inline `<code>` elements ✅ (after bugfix)
- Inside list items ✅
- Inside table cells ✅
- Inside `<pre>` code blocks ❌ SKIPPED — must be enabled
- Skips inside `<a>` tags ✅
- Skips inside `.peek-link` spans ✅
- Class names ❌ — data may be in peek-index but not tested
- Function calls ❌ — data may be in peek-index but not tested

### Fix — REQUIRED (100% parity, no exceptions):
1. Remove the `closest('pre')` skip — annotate inside code blocks like the Vault
2. Verify T5 class names and function calls are in peek-index data and annotated
3. All annotation types the Vault supports must work here too

---

## GAP 9: Annotation Quality — Pattern Matching

### Content Vault annotation matching:
The Content Vault uses server-resolved data. The regex patterns in `peek.py` are
used server-side, and the DOM annotator receives clean, validated data.

### Docusaurus annotation matching:
Same `peek.py` resolver runs at build time. The data is baked into `peek-index.json`.
The DOM annotator in `usePeekLinks.ts` uses a regex built from the ref texts.

### Problem: The regex in `usePeekLinks.ts` uses `\b` word boundaries:
```typescript
const pattern = new RegExp('\\b(' + escaped.join('|') + ')\\b', 'g');
```

Word boundary `\b` doesn't work well with paths containing `/` or `.` because
these are not word characters. A path like `src/core/services/` might not match
properly because `\b` before `s` might not fire after a space or start of text.

Actually `\b` matches at position between `\w` and `\W`, so `src/` at the start
of text would match. BUT: the issue is that partial path matches inside longer
paths might be incorrectly bounded. For example, `src/ui/cli` as a ref text
would match inside `src/ui/cli/git` because `\b` fires at the `/` after `cli`.

### Content Vault matching:
Same `\b` approach: `new RegExp('\\b(' + escaped.join('|') + ')\\b', 'g')`.
So this is actually at parity — same behavior, same limitations.

---

## GAP 10: CSS Styling Gaps

### Missing CSS in Docusaurus custom.css.tmpl:
1. ❌ `.peek-listing-item` — used in directory listing but no CSS rule
2. ❌ `.peek-spinner` — loading spinner class but no animation
3. ❌ `.peek-dir-tabs` — tab bar styling incomplete
4. ❌ `.peek-dir-tab.active` — active tab indicator

### Fix
Add missing CSS rules matching Content Vault's styling.

---

## Priority Order for Fixes

**ALL items are REQUIRED. 100% parity. No exceptions.**

> ⚠️ **HONESTY NOTE (2026-03-06 08:07)**: Previous version of this file
> marked everything "✅ DONE". That was a LIE. Code was written but NEVER
> verified on the running site. Corrected below with real status.
>
> Legend:
> - ✅ VERIFIED = tested on running site, confirmed working
> - 🔨 CODE WRITTEN = code exists in source, NEVER tested/verified
> - ❌ BROKEN = investigation proved it does not work
> - ❌ NOT DONE = not even attempted

### P0 — CRITICAL
1. **GAP 1**: 🔨 CODE WRITTEN — regex fix committed to peek.py BUT never tested.
   Not verified that truncated garbage texts are actually eliminated.
2. **GAP 2**: 🔨 CODE WRITTEN — `_find_doc_route` rewritten BUT never verified
   that doc_url coverage actually went from 3% to 96%.

### P1 — HIGH
3. **GAP 3**: 🔨 CODE WRITTEN — outline extraction code exists BUT never
   verified that all resolved refs actually have outline data.
4. **GAP 4**: 🔨 CODE WRITTEN — per-row buttons exist in `_renderOutline()`
   BUT never verified they render or work. Directory `src/core/engine`
   confirmed to show NO buttons — likely because outline data is empty.
5. **GAP 5**: 🔨 CODE WRITTEN — unified buttons + `_resolveAction` exist
   BUT never verified the mode toggle actually changes link targets.
6. **GAP 8**: ❌ NOT VERIFIED — annotation coverage for `<pre>`, class names,
   function calls never tested. Unknown if T5 symbols appear in peek-index.

### P2 — UNVERIFIED
7. **GAP 7.11**: 🔨 CODE WRITTEN — clickable listing items never verified
8. **GAP 7.12**: 🔨 CODE WRITTEN — "Open README" button never verified
9. **GAP 7.13**: 🔨 CODE WRITTEN — image preview never verified
10. **GAP 10**: 🔨 CODE WRITTEN — CSS rules added but never verified on site
11. **GAP 7.9**: ❌ BROKEN — `_mapHeadingsToSourceLines` requires raw source
    from localhost:8000 API (admin panel). Fails silently when admin panel is
    not running. No heading-to-line mapping → no data-source-line attributes.
12. **GAP 7.10**: ❌ BROKEN — `_peekObserveLines` depends on GAP 7.9.
    Without data-source-line attributes, finds 0 headings and returns
    immediately. Line tracking DOES NOT WORK.

### Additional Parity Items — UNVERIFIED
- **A5**: 🔨 CODE WRITTEN — data attributes on spans never verified in DOM
- **D7**: 🔨 CODE WRITTEN — observer cleanup never verified
- **D8**: 🔨 CODE WRITTEN — _peekCurrentLine never verified
- **F7**: 🔨 CODE WRITTEN — binary fallback never verified
- **F8**: 🔨 CODE WRITTEN — truncation warning never verified
- **H1**: 🔨 CODE WRITTEN — outline line numbers never verified
- **G3**: 🔨 CODE WRITTEN — _peekScrollToLine never verified

### Infrastructure
13. **Dev badge**: ❌ BROKEN — badge creation code exists but is gated behind
    `allRefs.length > 0`. If peek-index lookup fails (wrong key from
    `locationToDocPath`), badge never renders. NEVER VERIFIED on site.
14. **Mode-aware URLs**: 🔨 CODE WRITTEN — buttons call `_peekMode()` at
    click time. Never verified that clicking actually routes correctly.

### NEWLY DISCOVERED BUGS (from investigation 2026-03-06)
15. **Path resolution broken for `/` paths**: peek.py `_resolution_candidates()`
    never tries `src/` prefix. `adapters/containers/docker.py` → "Not found"
    because the actual file is `src/adapters/containers/docker.py`. This is
    why MANY paths show "Not found in project". ❌ NOT FIXED.
16. **Substring matching inside paths**: `core/services/content/crypto.py` in
    text → "content" and "crypto.py" annotated individually because they ARE
    in the ref list as separate entries (directory + bare filename). The full
    path doesn't resolve (see bug 15) so only the parts match. ❌ NOT FIXED.
17. **REPO_URL placeholder guard**: `__REPO_URL__` was truthy when unsubstituted,
    causing garbage fetch URLs. 🔨 FIX WRITTEN but not verified.
