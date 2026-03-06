# Peek Feature — 10% → 100% Roadmap & Tracker

> **Created**: 2026-03-06 08:17
> **Rule**: 100% or nothing. No bug is acceptable.
> **Rule**: Nothing is DONE until verified on the RUNNING site.
> **Rule**: Fix ONE at a time. Verify. Then next.
>
> **Source documents** (these contain the details, this file is the tracker):
> - `peek-all-bugs.md` — 38 bugs across 9 categories
> - `peek-gap-analysis.md` — 10 GAPs + infrastructure items
> - `peek-built-site-parity.md` — 6 phases of implementation plan
> - `peek-parity-investigation.md` — 5 traced issues with root causes
>
> **Gold standard**: `src/ui/web/templates/scripts/content/_preview.html`
> **Target**: `src/core/services/pages_builders/templates/docusaurus/theme/hooks/usePeekLinks.ts`
> **Pipeline**: `src/core/services/pages_builders/docusaurus.py`
> **Resolver**: `src/core/services/peek.py`

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ❌ | NOT DONE — no code exists |
| 🔨 | CODE WRITTEN — never tested on running site |
| 🔍 | NEEDS VERIFICATION — must run pipeline to confirm |
| ✅ | VERIFIED — tested on running site, confirmed working |

---

## Current Score: ~10%

We have code written for many features but NOTHING has been verified.
Code that hasn't been tested is worth 0%. The only things that count
toward the score are items marked ✅ VERIFIED.

---

## TRACK 1: Path Resolution (peek.py) — THE FOUNDATION

Nothing else works if paths don't resolve correctly. This is the #1 priority.

| # | Item | Status | Ref |
|---|------|--------|-----|
| 1.1 | `src/` prefix tried for paths with `/` | ✅ User confirmed src matches increased (2026-03-06) | A1, Issue 5 |
| 1.2 | Bare regex truncation fix (T2_BARE vs T2_BACKTICK) | 🔨 | A2, GAP 1 |
| 1.3 | doc_url mapping (resolved_path → Docusaurus route) | 🔨 | A3, GAP 2 |
| 1.4 | Directory detection without trailing `/` | 🔍 | A4 |
| 1.5 | T5 symbol resolution (class names, functions) | 🔍 | A5 |
| 1.6 | Verify resolved refs count matches Content Vault | ❌ | — |
| 1.7 | Verify unresolved refs count is near zero | ❌ | — |
| 1.8 | Verify NO truncated garbage in peek-index.json | ❌ | GAP 1 |

**Verification method**: Run the scanner, generate peek-index.json,
count resolved vs unresolved, compare with Content Vault API output
for the SAME document.

---

## TRACK 2: Outline Data (docusaurus.py) — TOOLTIP CONTENT

| # | Item | Status | Ref |
|---|------|--------|-----|
| 2.1 | Directories with README.md get heading outline | 🔨 | B1 |
| 2.2 | Directories without README.md — fallback behavior | ❌ | B1 |
| 2.3 | Python files get class/function outline from symbol index | 🔍 | B2 |
| 2.4 | Symbol index covers ALL Python files | 🔍 | I3 |
| 2.5 | Markdown files get H1-H3 headings | 🔨 | — |
| 2.6 | MAX_OUTLINE_ITEMS doesn't cut important content | 🔍 | B3 |
| 2.7 | Async outline fallback works when index has no data | 🔨 | B4 |
| 2.8 | Outline data carries line numbers for all items | 🔨 | H1 |
| 2.9 | Verify outline data count matches Content Vault | ❌ | GAP 3 |

**Verification method**: Pick 10 files across types (py, md, dir),
compare outline data in peek-index.json vs Content Vault glossary.

---

## TRACK 3: Frontend Annotation (usePeekLinks.ts) — WHAT YOU SEE

| # | Item | Status | Ref |
|---|------|--------|-----|
| 3.1 | Resolved refs annotated with peek-link spans | 🔨 | — |
| 3.2 | Unresolved refs annotated with dimmed styling | 🔨 | — |
| 3.3 | Pending T5 refs annotated with pulsing styling | 🔨 | — |
| 3.4 | No substring matching inside longer paths | 🔨 | C1, Issue 1 |
| 3.5 | Annotation inside `<pre>` code blocks (like Vault) | ❌ | C2, GAP 8 |
| 3.6 | Annotation of T5 class names (PascalCase) | 🔍 | GAP 8 |
| 3.7 | Annotation of T5 function calls (func_name()) | 🔍 | GAP 8 |
| 3.8 | data-peek-path attribute on spans | 🔨 | A5 item |
| 3.9 | data-peek-dir attribute on spans | 🔨 | A5 item |
| 3.10 | data-peek-line attribute on spans | 🔨 | A5 item |
| 3.11 | Skip `<a>` tags (no double-linking) | 🔨 | — |
| 3.12 | Skip already-annotated `.peek-link` spans | 🔨 | — |
| 3.13 | Word-boundary regex matches same as Vault | 🔨 | C3, GAP 9 |
| 3.14 | Annotation count badge accurate | 🔨 | C4 |
| 3.15 | Verify annotation count per page matches Vault | ❌ | — |

**Verification method**: Open same document in Content Vault and
Docusaurus site. Count annotations. They must match.

---

## TRACK 4: Tooltip (usePeekLinks.ts) — CLICK INTERACTIONS

| # | Item | Status | Ref |
|---|------|--------|-----|
| 4.1 | Tooltip structure: header + icon + path + close | 🔨 | — |
| 4.2 | File type tag badge (.py, .md, etc.) | 🔨 | Gap 2.2 |
| 4.3 | Line number context display | 🔨 | — |
| 4.4 | Parent directory context | 🔨 | Gap 2.3 |
| 4.5 | Directory tooltip: "Directory" tag badge | 🔨 | — |
| 4.6 | Outline section with per-row headings | 🔨 | GAP 4 |
| 4.7 | Per-row action buttons: Preview | 🔨 | GAP 4 |
| 4.8 | Per-row action buttons: Open (line-aware) | 🔨 | GAP 4 |
| 4.9 | Per-row action buttons: Browse | 🔨 | GAP 4 |
| 4.10 | Per-row action buttons: New Tab (line-aware) | 🔨 | GAP 4 |
| 4.11 | Main action: Preview button | 🔨 | GAP 5 |
| 4.12 | Main action: Open button (mode-aware) | 🔨 | GAP 5 |
| 4.13 | Main action: Edit button (mode-aware) | 🔨 | GAP 5 |
| 4.14 | Main action: Browse button | 🔨 | GAP 5 |
| 4.15 | Main action: New Tab button | 🔨 | GAP 5 |
| 4.16 | Main action: Open Page button (doc_url) | 🔨 | GAP 5 |
| 4.17 | Unresolved tooltip: "Not found" label | 🔨 | — |
| 4.18 | Pending tooltip: "Resolving..." label | 🔨 | — |
| 4.19 | Close button (✕) works | 🔨 | GAP 6 |
| 4.20 | Click outside dismisses | 🔨 | GAP 6 |
| 4.21 | Escape key dismisses | 🔨 | GAP 6 |
| 4.22 | Click another peek-link replaces tooltip | 🔨 | GAP 6 |
| 4.23 | Tooltip positioning (viewport-aware) | 🔨 | — |
| 4.24 | "Open Page" actually navigates to doc page | 🔨 | G1 |
| 4.25 | Per-row buttons actually fire their actions | 🔨 | G2 |
| 4.26 | Verify tooltip matches Vault 1:1 visually | ❌ | — |

**Verification method**: Click 5 different annotated refs (file, dir,
unresolved, py file, md file). Compare tooltip layout and all buttons
with Content Vault tooltip for same ref.

---

## TRACK 5: Preview Overlay — FULL POWER

| # | Item | Status | Ref |
|---|------|--------|-----|
| 5.1 | Overlay structure: backdrop + box + header + body | 🔨 | — |
| 5.2 | Header: icon + path + line badge | 🔨 | — |
| 5.3 | Header: Jump button (mode-aware) | 🔨 | F2, Gap 3.5 |
| 5.4 | Header: Edit button (mode-aware) | 🔨 | F2, Gap 3.5 |
| 5.5 | Header: Close button | 🔨 | — |
| 5.6 | Unicode emoji rendered correctly (not escape sequences) | 🔍 | F1 |
| 5.7 | Button styling correct (changed from `<a>` to `<button>`) | 🔍 | F2, H4 |
| 5.8 | Internal doc preview: fetch rendered page HTML | 🔨 | Gap 3.1 |
| 5.9 | Source code preview: Monaco CDN | 🔨 | Gap 3.2 |
| 5.10 | Markdown preview: Marked CDN rendering | 🔨 | Gap 3.3 |
| 5.11 | Directory preview: tabbed README + listing | 🔨 | Gap 3.4 |
| 5.12 | Directory listing items are clickable | 🔨 | Gap 7.11 |
| 5.13 | "Open README" button in directory header | 🔨 | Gap 7.12 |
| 5.14 | Image preview | 🔨 | Gap 7.13 |
| 5.15 | Binary file fallback message | 🔨 | F7 |
| 5.16 | Truncation warning | 🔨 | F8 |
| 5.17 | History pushState (Back closes preview) | 🔨 | Gap 3.7 |
| 5.18 | Escape key closes | 🔨 | — |
| 5.19 | Backdrop click closes | 🔨 | — |
| 5.20 | Preview works via local API (localhost:8000) | 🔍 | F5 |
| 5.21 | Preview works via GitHub raw (deployed site) | 🔍 | F6 |
| 5.22 | CORS configured for localhost:3000 → localhost:8000 | 🔍 | F5 |
| 5.23 | Verify preview matches Vault 1:1 visually | ❌ | — |

**Verification method**: Open preview for 5 different ref types.
Compare with Content Vault preview for same file. Must match.

---

## TRACK 6: Line Tracking — SCROLL AWARENESS

| # | Item | Status | Ref |
|---|------|--------|-----|
| 6.1 | _stripInlineMarkdown function exists | ❌ | D3, D4 |
| 6.2 | _fetchRawSource works on dev server | ❌ BROKEN | D1 |
| 6.3 | _fetchRawSource works on deployed site | 🔍 | D2 |
| 6.4 | _mapHeadingsToSourceLines with inline-md stripping | ❌ BROKEN | D3 |
| 6.5 | data-source-line attributes set on headings | ❌ BROKEN | D1 chain |
| 6.6 | IntersectionObserver tracks visible heading | ❌ BROKEN | D1 chain |
| 6.7 | Header line badge updates on scroll | ❌ BROKEN | D1 chain |
| 6.8 | _peekCurrentLine tracked correctly | ❌ BROKEN | D1 chain |
| 6.9 | Scroll-to-line when opening preview at specific line | 🔨 | G3 |
| 6.10 | Click-to-focus handler in preview | ❌ | D5 |
| 6.11 | Observer cleanup on close | 🔨 | D7 |
| 6.12 | Monaco cursor position → line badge update | 🔨 | — |
| 6.13 | Verify line tracking matches Vault behavior | ❌ | — |

**Verification method**: Open preview for a markdown file with headings.
Scroll through content. Header line badge must update in real-time.
Must match Content Vault behavior exactly.

---

## TRACK 7: Dev/Live Mode — INFRASTRUCTURE

| # | Item | Status | Ref |
|---|------|--------|-----|
| 7.1 | Dev badge renders on localhost | ❌ BROKEN | E1 |
| 7.2 | Dev badge hidden on deployed site | 🔍 | — |
| 7.3 | Badge visible (not hidden by other UI elements) | 🔍 | E3 |
| 7.4 | Click toggles window.__peekMode | 🔨 | — |
| 7.5 | Badge label updates (Dev ↔ Live) | 🔨 | — |
| 7.6 | All tooltip buttons use _peekMode() at click time | 🔨 | — |
| 7.7 | Dev mode: Open → Content Vault | 🔨 | — |
| 7.8 | Dev mode: Edit → Content Vault editor | 🔨 | — |
| 7.9 | Dev mode: Browse → Content Vault browser | 🔨 | — |
| 7.10 | Dev mode: New Tab → Vault hash route | 🔨 | — |
| 7.11 | Live mode: Open → GitHub blob | 🔨 | — |
| 7.12 | Live mode: Edit → GitHub edit URL | 🔨 | — |
| 7.13 | Live mode: Browse → GitHub tree | 🔨 | — |
| 7.14 | Live mode: New Tab → GitHub new tab | 🔨 | — |
| 7.15 | Preview header buttons also mode-aware | 🔨 | — |
| 7.16 | Verify all mode combinations work | ❌ | — |

**Verification method**: Toggle badge. Click every button in both modes.
Verify URLs are correct.

---

## TRACK 8: Build Pipeline — DATA GENERATION

| # | Item | Status | Ref |
|---|------|--------|-----|
| 8.1 | peek-index.json keys match locationToDocPath() output | 🔍 | I1, E2 |
| 8.2 | __REPO_URL__ placeholder substituted correctly | 🔍 | I2 |
| 8.3 | __BASE_URL__ placeholder substituted correctly | 🔍 | I2 |
| 8.4 | REPO_URL guard (empty when unsubstituted) | 🔨 | bug 17 |
| 8.5 | BASE_URL guard (default '/' when unsubstituted) | 🔨 | bug 17 |
| 8.6 | Symbol index built for all Python files | 🔍 | I3 |
| 8.7 | peek-index.json generated without errors | 🔍 | — |
| 8.8 | Verify peek-index.json is importable in Docusaurus | 🔍 | — |

**Verification method**: Run the build pipeline. Check peek-index.json
output. Verify substitutions in the built usePeekLinks.ts.

---

## TRACK 9: CSS — VISUAL CORRECTNESS

| # | Item | Status | Ref |
|---|------|--------|-----|
| 9.1 | .peek-link resolved styling | 🔨 | — |
| 9.2 | .peek-link--unresolved styling | 🔨 | — |
| 9.3 | .peek-link--pending styling + animation | 🔨 | — |
| 9.4 | .peek-link--directory styling | 🔨 | — |
| 9.5 | .peek-tooltip positioning, border, shadow | 🔨 | — |
| 9.6 | .peek-tooltip__tag badge styling | 🔨 | — |
| 9.7 | .peek-tooltip__tag--dir styling | 🔨 | — |
| 9.8 | .peek-tooltip__outline-row styling | 🔨 | — |
| 9.9 | .peek-outline-act button styling | 🔨 | — |
| 9.10 | .peek-listing-item styling | 🔍 | H1 |
| 9.11 | .peek-spinner animation | 🔍 | H2 |
| 9.12 | .peek-heading-tracked highlight | 🔍 | H3 |
| 9.13 | .peek-preview header button styling (now `<button>`) | 🔍 | H4 |
| 9.14 | .peek-dir-tabs tab bar styling | 🔍 | GAP 10 |
| 9.15 | .peek-dir-tab.active indicator | 🔍 | GAP 10 |
| 9.16 | .peek-mode-badge styling | 🔨 | — |
| 9.17 | .peek-status badge styling | 🔨 | — |
| 9.18 | Verify all CSS matches Vault visual appearance | ❌ | — |

**Verification method**: Visual comparison of every element between
Content Vault and Docusaurus site.

---

## SCORE CARD

| Track | Total Items | ✅ Verified | Score |
|-------|-------------|-------------|-------|
| 1. Path Resolution | 8 | 1 | 12% |
| 2. Outline Data | 9 | 0 | 0% |
| 3. Frontend Annotation | 15 | 0 | 0% |
| 4. Tooltip | 26 | 0 | 0% |
| 5. Preview Overlay | 23 | 0 | 0% |
| 6. Line Tracking | 13 | 0 | 0% |
| 7. Dev/Live Mode | 16 | 0 | 0% |
| 8. Build Pipeline | 8 | 0 | 0% |
| 9. CSS | 18 | 0 | 0% |
| **TOTAL** | **136** | **1** | **1%** |

> **Honest assessment**: We are at 0% VERIFIED. Code exists for ~60%
> of items but none of it has been tested. 9 items are confirmed BROKEN.
> The remaining ~40% hasn't even been attempted.
>
> To get to 100%:
> 1. Start with Track 1 (Path Resolution) — everything depends on this
> 2. Then Track 8 (Build Pipeline) — generate correct data
> 3. Then Track 3 (Annotation) — verify it shows up
> 4. Then Tracks 4-9 in order

---

## HOW TO USE THIS DOCUMENT

1. Before starting work: READ this document to know where we are
2. Pick the NEXT item from the highest-priority track
3. Fix it (ONE change)
4. VERIFY it on the running site
5. Update the status in this document from 🔨 to ✅ (or note what's still wrong)
6. Move to the next item
7. NEVER mark something ✅ without verification evidence
