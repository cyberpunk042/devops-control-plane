# Peek Feature — COMPLETE Bug List

> Generated 2026-03-06 08:11. HONEST. No "DONE" markers. Every bug listed.
> This list was produced by reading the code. Some bugs may only be
> confirmable by running the pipeline — those are marked (NEEDS VERIFICATION).
>
> **Rule: 100% annotation and resolution match with Content Vault.**
> **Rule: Fix ONE at a time. Verify before moving to next.**

---

## Category A: Path Resolution (peek.py)

These bugs cause paths to show "Not found in project" in Docusaurus
that work fine in the Content Vault.

### A1. `src/` prefix not tried for paths with `/`
- **File**: peek.py `_resolution_candidates()` line 586-603
- **Bug**: For paths like `adapters/containers/docker.py`, the resolver
  tries: root-relative, doc_dir-relative, ancestor prefixes of doc_dir.
  When doc is in `docs/code-docs/...`, ancestors are `docs/...` — never
  `src/`. In the Content Vault, docs are IN `src/`, so ancestors naturally
  include `src/`.
- **Impact**: EVERY path that starts with a `src/` subdirectory fails
  to resolve when the document is outside `src/`. This is likely HUNDREDS
  of refs across all pages.
- **Examples**: `adapters/containers/docker.py`, `core/services/content/crypto.py`,
  `core/engine/executor.py`, `ui/web/routes.py`, etc.

### A2. Bare regex truncation (GAP 1)
- **File**: peek.py `_RE_T2_BARE` line 125-127
- **Bug**: Backtick-enclosed paths get matched by BOTH T2_BACKTICK and
  T2_BARE. The bare regex strips the first and last char because of
  lookbehind/lookahead excluding backtick. Produces truncated garbage
  like `ore/services/git/ops.p` that can't resolve.
- **Impact**: ~4,029 false "Not found" annotations (estimated from
  earlier analysis).
- **Status**: Fix was written (skip bare regex inside backtick spans)
  but NEVER VERIFIED.

### A3. doc_url mapping incomplete (GAP 2)
- **File**: docusaurus.py `_find_doc_route()` line 1160+
- **Bug**: Only 78/2478 resolved refs had doc_url (3%). The function
  was rewritten but coverage was never measured after the fix.
- **Impact**: Without doc_url, "Open Page" button doesn't appear in
  tooltips. Preview falls back to raw fetch instead of fetching
  rendered site HTML.
- **Status**: Fix was written. NEVER VERIFIED.

### A4. Directory detection for paths without trailing `/`
- **File**: peek.py `_resolve_one()` line 528
- **Bug**: `is_dir_ref = cand.candidate_path.endswith("/")`. But many
  directory references in markdown don't have trailing `/`.
  `src/core/engine` is a directory but doesn't end with `/`.
  Detection falls back to `dir_paths` set or filesystem check.
- **Impact**: (NEEDS VERIFICATION) — directories might not get
  `is_directory=true` in the peek-index, which affects tooltip
  rendering and outline extraction.

### A5. Symbol resolution (T5) — classes and functions
- **File**: peek.py `_resolve_symbol()` 
- **Bug**: (NEEDS VERIFICATION) — T5 candidates (PascalCase class names,
  `func_name()` patterns) may or may not be in the peek-index output.
  Never verified that class names like `DocusaurusBuilder` or function
  names like `scan_peek_candidates()` appear as annotations in the
  built site.
- **Impact**: Unknown. Could be zero class/function annotations.

---

## Category B: Outline Data (docusaurus.py)

### B1. Directories without README.md get empty outline
- **File**: docusaurus.py `_extract_outline()` line 1107-1115
- **Bug**: For directories, outline comes from README.md headings.
  If the directory has no README.md, outline is `[]` (empty).
  The tooltip shows no outline rows and no per-row buttons.
- **Impact**: Every directory without README.md has zero buttons
  in its tooltip. Example: `src/core/engine` (if no README.md).
- **Vault comparison**: Content Vault uses glossary data which may
  have symbols even without README. Also has async API fallback.

### B2. Python file outline depends on symbol index
- **File**: docusaurus.py `_extract_outline()` line 1118-1122
- **Bug**: `symbols = file_symbols.get(resolved_path, [])`. If the
  symbol index wasn't built for a file, outline is empty.
- **Impact**: (NEEDS VERIFICATION) — how many Python files actually
  have symbol data in the index?

### B3. Outline limited to MAX_OUTLINE_ITEMS
- **File**: docusaurus.py line ~1153
- **Bug**: Headings capped at MAX_OUTLINE_ITEMS. Files with many
  headings get truncated.
- **Impact**: Minor. But Content Vault may show more items. Not verified.

### B4. Async outline fallback
- **File**: usePeekLinks.ts `_peekFetchOutlineAsync()` line 1364+
- **Bug**: Code was written to fetch outline asynchronously when
  peek-index has no data. But this fetches from localhost:8000 or
  GitHub raw. On Docusaurus dev server, localhost:8000 may not be
  running. On deployed site, REPO_URL may not be set.
- **Impact**: (NEEDS VERIFICATION) — does fallback actually work?

---

## Category C: Frontend Annotation (usePeekLinks.ts)

### C1. Substring matching inside longer paths
- **File**: usePeekLinks.ts `annotatePeekRefs()` line 360+
- **Bug**: Ref "content" (a directory) matches inside the text
  "core/services/content/crypto.py". Ref "crypto.py" (a file)
  also matches. Both get annotated as separate peek-links inside
  what should be a single full-path reference.
- **Root cause**: The full path `core/services/content/crypto.py`
  doesn't resolve (see A1), so it's not in the ref list. Only the
  parts match.
- **Guard written**: Path-context check (adjacent `/` chars) was
  added but NOT VERIFIED.

### C2. `<pre>` code block annotation
- **File**: usePeekLinks.ts `annotatePeekRefs()` line ~350
- **Bug**: The Content Vault annotates inside `<pre>` blocks.
  The Docusaurus version may skip them (closest('pre') check).
- **Impact**: (NEEDS VERIFICATION) — is there a closest('pre')
  skip? Need to check.

### C3. Word boundary regex behavior with paths
- **File**: usePeekLinks.ts line ~345
- **Bug**: Regex uses `\b` word boundaries. For paths containing
  `/` and `.`, `\b` may produce unexpected matches because `/`
  and `.` are non-word characters. `\b` fires at every `/` boundary.
- **Impact**: Content Vault uses same `\b` approach, so this is
  technically at parity. But both have the same problem.

### C4. Annotation count accuracy
- **File**: usePeekLinks.ts line 234
- **Bug**: `container.querySelectorAll('.peek-link').length` counts
  DOM elements, not unique refs. If "content" appears 5 times in
  text, count is 5 not 1.
- **Impact**: Minor cosmetic. Badge shows inflated count.

---

## Category D: Line Tracking (usePeekLinks.ts)

### D1. _fetchRawSource fails on Docusaurus dev server
- **File**: usePeekLinks.ts `_fetchRawSource()` line 1326+
- **Bug**: When IS_LOCAL=true (localhost:3000 Docusaurus server),
  tries to fetch from localhost:8000 (admin panel). If admin panel
  isn't running, fetch fails silently. Returns null.
- **Impact**: No raw markdown source → _mapHeadingsToSourceLines
  can't map headings → no data-source-line attributes → 
  _peekObserveLines finds nothing → LINE TRACKING COMPLETELY BROKEN.

### D2. _fetchRawSource fails on deployed site without REPO_URL
- **File**: usePeekLinks.ts `_fetchRawSource()` line 1333+
- **Bug**: On deployed site, needs REPO_URL to fetch from GitHub raw.
  Before my fix, `__REPO_URL__` placeholder was truthy but garbage.
  After my fix, it's `''` (falsy), so the function returns null.
  Raw source fetches ONLY work if REPO_URL is properly substituted
  by the build pipeline.
- **Impact**: On deployed site without REPO_URL, line tracking broken.

### D3. _mapHeadingsToSourceLines matching logic
- **File**: usePeekLinks.ts line 1228-1236
- **Bug**: Matches heading text literally: `m[1].trim() === text`.
  But headings with inline formatting (backticks, bold, etc.) have
  different textContent in DOM vs source. The Content Vault has a
  `_stripInlineMarkdown()` function (line 22-39) that strips
  formatting before comparison. The Docusaurus version does NOT
  have this stripping.
- **Impact**: Headings with formatting won't get data-source-line
  attributes even when raw source IS available.

### D4. No _stripInlineMarkdown equivalent
- **File**: usePeekLinks.ts — MISSING
- **Bug**: Content Vault has `_stripInlineMarkdown(text)` that
  removes backticks, bold, italic, strikethrough, HTML tags before
  comparing heading text. Docusaurus version doesn't have this.
- **Impact**: Headings like "### `context.py` — Title" won't match.

### D5. No click-to-focus handler
- **File**: usePeekLinks.ts — MISSING
- **Bug**: Content Vault has `_contentPreviewClickHandler()` that
  sets focus line when clicking anywhere in the preview. Docusaurus
  version doesn't have this.
- **Impact**: Clicking in the preview doesn't update the line number.

### D6. No _contentSetFocusLine equivalent
- **File**: usePeekLinks.ts — MISSING
- **Bug**: Content Vault has `_contentSetFocusLine()` that syncs
  focus line with glossary and URL hash. Docusaurus doesn't need
  glossary sync, but the line focus concept is missing.
- **Impact**: Minor — related to D5.

---

## Category E: Dev/Live Badge & Mode Toggle

### E1. Badge gated behind refs count
- **File**: usePeekLinks.ts line 216, 248
- **Bug**: Badge creation is inside the setTimeout callback that only
  runs if `allRefs.length > 0`. If peek-index lookup returns no refs
  for the current page, badge never renders on that page.
- **Impact**: Pages without peek data have no Dev/Live toggle.

### E2. locationToDocPath may produce wrong keys
- **File**: usePeekLinks.ts `locationToDocPath()` line 288-325
- **Bug**: (NEEDS VERIFICATION) The function maps Docusaurus URLs to
  peek-index keys. If the mapping is wrong, ZERO refs are found for
  the page, and everything fails — no annotations, no badge, nothing.
- **Impact**: Could be the reason entire pages have zero annotations.

### E3. Badge may be hidden by Docusaurus UI elements
- **File**: CSS custom.css.tmpl line 803+
- **Bug**: Badge is `position: fixed; bottom: 3.5rem; right: 1.5rem`.
  Docusaurus may have footer, ToC sidebar, or other elements at that
  position that cover the badge.
- **Impact**: (NEEDS VERIFICATION) Badge rendered but not visible.

---

## Category F: Preview Overlay

### F1. Unicode escapes in template literals
- **File**: usePeekLinks.ts line 836-844
- **Bug**: After my edit, the template literal contains `\\u2197`,
  `\\u270f\\ufe0f`, `\\ud83d\\udcc4`, `\\u2715`. These may render
  as literal escaped text instead of the intended emoji/symbols
  because they're in template literal strings, not raw strings.
- **Impact**: Buttons may show `\u2197` instead of ↗. NEEDS VERIFICATION.

### F2. Preview header buttons changed from <a> to <button>
- **File**: usePeekLinks.ts line 836-844
- **Bug**: I changed <a href="..."> to <button data-action="..."> in
  the preview header. The CSS was designed for <a> elements and may
  not style <button> the same way (different default styles).
- **Impact**: Buttons may look wrong. NEEDS VERIFICATION.

### F3. Preview directory listing — clickable items
- **File**: usePeekLinks.ts `_previewDirectory()` line 946+
- **Bug**: (NEEDS VERIFICATION) Listing items should be clickable to
  open that file's preview. Code was written but never tested.

### F4. Preview image display
- **File**: usePeekLinks.ts `_previewViaLocalAPI()` line 1098+
- **Bug**: (NEEDS VERIFICATION) Image preview code exists but never
  tested for either local API or GitHub raw path.

### F5. CORS issues between localhost:3000 and localhost:8000
- **File**: usePeekLinks.ts — all fetch calls to localhost:8000
- **Bug**: Docusaurus dev server runs on localhost:3000. Admin panel
  runs on localhost:8000. Fetch calls from 3000→8000 are cross-origin.
  If admin panel doesn't set CORS headers, ALL fetches will fail.
- **Impact**: Preview, raw source fetch, outline fetch — ALL broken
  if CORS isn't configured.

### F6. GitHub raw fetch for private repos
- **File**: usePeekLinks.ts `_previewViaGitHub()` line 1113+
- **Bug**: Fetches from `raw.githubusercontent.com`. For private repos,
  this requires authentication tokens. The code doesn't provide any.
- **Impact**: On deployed site for private repos, preview won't load.

---

## Category G: Tooltip

### G1. "Open Page" button — was <a>, now <button>
- **File**: usePeekLinks.ts line 511-513
- **Bug**: Changed from `<a href="..." data-action="navigate">` to
  `<button data-action="navigate">`. The navigate handler was added
  to _resolveAction. But was there any CSS that targeted `a.peek-tooltip__btn`
  specifically? Button default styling differs from anchor.
- **Impact**: NEEDS VERIFICATION.

### G2. Outline per-row button wiring
- **File**: usePeekLinks.ts line 620-665
- **Bug**: Per-row buttons wire through event delegation. But the
  delegation queries `.peek-tooltip__outline-row .peek-outline-act`
  and relies on `data-line` attributes.
- **Impact**: (NEEDS VERIFICATION) Do per-row buttons actually fire
  their actions?

### G3. Smart browse equivalent missing
- **File**: usePeekLinks.ts — MISSING
- **Bug**: Content Vault has "📖 Smart" button that navigates to
  smart folder virtual path. Docusaurus has no smart folder concept.
- **Impact**: Minor — smart folders are Content-Vault-only concept.
  But "Browse Docs" button was added as equivalent. Unverified.

---

## Category H: CSS

### H1. peek-listing-item CSS
- **File**: custom.css.tmpl
- **Bug**: (NEEDS VERIFICATION) Class used in directory listing.
  May not have CSS defined.

### H2. peek-spinner CSS
- **File**: custom.css.tmpl
- **Bug**: (NEEDS VERIFICATION) Loading spinner class. May not
  have keyframe animation defined.

### H3. peek-heading-tracked CSS
- **File**: custom.css.tmpl
- **Bug**: Class added by IntersectionObserver to highlight tracked
  heading. May not have CSS defined.

### H4. peek-preview-header__action button styling
- **File**: custom.css.tmpl
- **Bug**: CSS was written for `<a>` elements. Now using `<button>`.
  Buttons have different default styling (border, background, padding).
- **Impact**: Buttons may look visually wrong.

---

## Category I: Build Pipeline (docusaurus.py)

### I1. peek-index.json key format
- **File**: docusaurus.py peek index generation
- **Bug**: (NEEDS VERIFICATION) The keys in peek-index.json must
  exactly match what `locationToDocPath()` produces. If they don't,
  pages find zero refs.

### I2. Template placeholder substitution
- **File**: docusaurus.py line 514-517
- **Bug**: `__REPO_URL__` and `__BASE_URL__` replaced in usePeekLinks.ts.
  But usePeekLinks.ts now has `_RAW_REPO = '__REPO_URL__'` with a
  guard: `_RAW_REPO.startsWith('__') ? '' : _RAW_REPO`. The
  substitution replaces the STRING `__REPO_URL__` which is inside
  the quotes. After substitution it becomes `_RAW_REPO = 'https://...'`.
  The guard then sees it doesn't start with `__` and uses the real URL.
  This SHOULD work. But never verified.

### I3. Symbol index population
- **File**: docusaurus.py `file_symbols` line 579+
- **Bug**: (NEEDS VERIFICATION) How is the symbol index built?
  Does it cover ALL Python files? Or only some? If it's incomplete,
  Python file outlines will be empty.

---

## Summary Count

| Category | Bug Count | Confirmed Broken | Needs Verification |
|----------|-----------|-----------------|-------------------|
| A: Path Resolution | 5 | 2 (A1, A2) | 3 |
| B: Outline Data | 4 | 1 (B1) | 3 |
| C: Frontend Annotation | 4 | 1 (C1) | 3 |
| D: Line Tracking | 6 | 3 (D1, D3, D4) | 3 |
| E: Badge & Mode | 3 | 1 (E1) | 2 |
| F: Preview Overlay | 6 | 1 (F5) | 5 |
| G: Tooltip | 3 | 0 | 3 |
| H: CSS | 4 | 0 | 4 |
| I: Build Pipeline | 3 | 0 | 3 |
| **TOTAL** | **38** | **9** | **29** |

9 confirmed broken. 29 need verification (running the pipeline and
checking the actual site). Total: 38 known issues.

> **NOTE**: There may be MORE bugs that I cannot find by reading code
> alone. The only way to find them all is to run the pipeline, generate
> peek-index.json, and compare the output page-by-page against the
> Content Vault. I have not done this yet.
