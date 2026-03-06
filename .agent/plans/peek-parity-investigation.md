# Peek Parity Investigation — Real Evidence

> Generated 2026-03-06. Every finding traced to actual code lines.

---

## Issue 1: Path substring matching

**Symptom**: `core/services/content/crypto.py` in markdown text → "content" and
"crypto.py" get annotated individually, NOT the full path.

### Root Cause (TWO problems)

**Problem A — Scanner/Resolver (peek.py line 586-603)**:
When a full path like `adapters/containers/docker.py` appears in text, the scanner
extracts it as a T2 candidate. The resolver tries:
1. `adapters/containers/docker.py` — root-relative (file probably at `src/adapters/...`)
2. `{doc_dir}/adapters/containers/docker.py` — relative to doc
3. Ancestor prefixes of doc_dir only

If the document is in `docs/code-docs/...` (doc_dir=`docs/code-docs`), the ancestors
are `docs` and root. It **never tries `src/` as a prefix**. So
`adapters/containers/docker.py` → UNRESOLVED.

But "docker.py" alone IS resolved (T1 bare filename, found via filename index).
And "content" IS resolved (T3 directory name, found via dir index).

**Problem B — Frontend annotation (usePeekLinks.ts line 360)**:
The resolved refs include "content" (a directory) and "crypto.py" (a file).
The regex pattern has them as alternation options. When the text
`core/services/content/crypto.py` appears, the regex matches "content" at
position 18 and "crypto.py" at position 26 — both get annotated.

I added a guard (lines 367-371) that checks for adjacent `/` chars, but this
guard only prevents annotation of substrings that are NOT in the ref list. The
**real** problem is that "content" and "crypto.py" ARE in the ref list — they're
legitimate refs that happen to appear inside a longer path.

### What we need

1. **peek.py `_resolution_candidates`**: For paths with `/`, also try `src/` prefix
   unconditionally (not just as ancestor of doc_dir). This would make
   `adapters/containers/docker.py` → `src/adapters/containers/docker.py` resolved
   as a FULL path ref with higher priority.

2. **usePeekLinks.ts annotation**: When a match like "content" occurs inside
   what looks like a longer file path (context has `/` on both sides), skip it
   if the FULL path is also in the ref map. The guard I added partially addresses
   this but needs refinement for cases where the full path ref also exists.

---

## Issue 2: Line tracking in preview doesn't work

**Symptom**: When opening a peek preview, the header "Line XX" indicator never
updates as you scroll through the content.

### Root Cause (chain analysis)

The line tracking chain:
1. `_fetchRawSource()` (line 1326) → fetches raw markdown source
2. `_mapHeadingsToSourceLines()` (line 1216) → maps h1-h6 to source line numbers
3. `_peekObserveLines()` (line 1247) → IntersectionObserver on headings

**Problem**: `_fetchRawSource` depends on either:
- `IS_LOCAL=true` → fetches from `localhost:8000` API — requires admin web server running
- `REPO_URL` set → fetches from GitHub raw — requires build substitution

When running on Docusaurus dev server (`localhost:3000`):
- `IS_LOCAL=true` (hostname IS localhost)
- Tries `localhost:8000` API — this is the admin panel, NOT docusaurus
- If admin panel isn't running on 8000, fetch fails silently → no raw source
- No raw source → `_mapHeadingsToSourceLines` doesn't run → no `data-source-line` attributes
- No `data-source-line` → `_peekObserveLines` finds 0 headings → returns immediately

**Fix for deployed (live) site**: `REPO_URL` substitution now guarded (my
recent fix). If substituted correctly, raw source fetches from GitHub should
work. But I never verified this.

**Fix for dev mode**: Need the admin web server running on port 8000
simultaneously with Docusaurus dev server. Or: provide the raw source from
the built docs content (the source markdown is already available since
Docusaurus compiled from it).

**Alternative**: Use the outline data from peek-index.json as a fallback for
heading-to-line mapping. peek-index already has outline items with `line`
numbers. Instead of fetching raw source and parsing headings, map DOM headings
to outline items directly. This would eliminate the need for any external fetch.

---

## Issue 3: No Dev/Live badge visible

**Symptom**: No toggle badge appears on the page to switch between Dev (Content
Vault) and Live (GitHub) link targets.

### Root Cause

Code exists at usePeekLinks.ts lines 248-264. CSS exists at custom.css.tmpl
lines 803-830. The badge IS created.

**BUT**: The badge creation is gated inside the `setTimeout` callback on line 223,
which only runs if `allRefs` is non-empty (line 216: `if (!allRefs || allRefs.length === 0) return;`).

**Possible causes**:
1. **Page has no refs in peek-index** → early return → badge never created
2. **locationToDocPath()** returns wrong key → no match in peek-index → early return
3. **Badge is created but invisible** — possible CSS issue with `position: fixed;
   bottom: 3.5rem; right: 1.5rem` — could be underneath Docusaurus's footer or
   scrolled out of view

### Investigation needed

Check: Does `locationToDocPath()` produce the correct key for actual pages?
The function (line 288-325) maps Docusaurus URLs to peek-index keys. If the
mapping is wrong, zero refs are found and the badge never renders.

---

## Issue 4: Directory `src/core/engine` doesn't show buttons per outline row

**Symptom**: When hovering/clicking a directory reference, the tooltip outline
shows no per-row action buttons.

### Root Cause (peek.py line 1107-1115)

For directories, `_extract_outline()` does:
1. Check `if not ext:` → directory
2. Look for `{dir}/README.md`
3. If README exists → recursively call `_extract_outline` for the README
4. If README doesn't exist → return `[]` (empty list)

**Two problems**:
1. If `src/core/engine/README.md` doesn't exist, outline is empty → no buttons
2. Even if README exists, only H1-H3 headings are extracted (not class/function
   symbols from Python files in the directory)

### Content Vault comparison (line 1520-1533)

The Content Vault uses `_peekExtractHeadings()` which searches the **glossary
data** for outline headings. The glossary is richer — it has full AST symbol
data. If not in glossary, it falls back to async API fetch. The Docusaurus
version has no glossary equivalent — it relies entirely on peek-index.json
outline data generated at build time.

### Fix needed

Verify that `src/core/engine/README.md` exists. If it does, check that
`_extract_outline` produces non-empty data for it. If it doesn't exist,
the directory will never have outline data in the peek-index.

---

## Issue 5: `adapters/containers/docker.py` "Not found in project"

**Symptom**: Path appears as unresolved (dimmed, yellow underline, "Not found
in project" tooltip).

### Root Cause (same as Issue 1 Problem A)

`_resolution_candidates()` in peek.py line 570-640:

For `adapters/containers/docker.py` (contains `/`):
1. Try `adapters/containers/docker.py` — doesn't exist at project root
2. Try `{doc_dir}/adapters/containers/docker.py` — doesn't exist
3. Try ancestor prefixes of doc_dir

The actual file is at `src/adapters/containers/docker.py`. The resolver never
tries `src/` prefix unless doc_dir itself is inside `src/`.

### Fix needed

Add `src/` prefix as a standard resolution candidate for paths containing `/`.
This is the most common case — users write `adapters/containers/docker.py`
meaning `src/adapters/containers/docker.py`.

---

## Summary: What's ACTUALLY done vs. what's NOT

| Feature | Content Vault | Docusaurus | Status |
|---------|--------------|------------|--------|
| Annotation — resolved refs | ✅ Word-boundary regex | ✅ Word-boundary regex | ✅ Parity |
| Annotation — unresolved refs | ✅ Dimmed yellow | ✅ Dimmed yellow | ✅ Parity |
| Annotation — pending refs | ✅ Pulsing blue | ✅ Pulsing blue | ✅ Parity |
| PATH RESOLUTION — bare filenames | ✅ Filename index | ✅ Filename index | ✅ Works |
| PATH RESOLUTION — paths with `/` | ✅ Resolves to src/ | ❌ Misses src/ prefix | ❌ BROKEN |
| Tooltip — structure/layout | ✅ Header + info + outline + actions | ✅ Same structure | ✅ Parity |
| Tooltip — outline per-row buttons | ✅ Preview/Open/Browse/NewTab | ✅ Same buttons | ✅ Parity |
| Tooltip — outline DATA for dirs | ✅ Glossary + async API | ⚠️ peek-index only | ⚠️ Partial |
| Tooltip — actions mode-gated | ✅ All actions go through vault | ✅ Now mode-gated | ✅ Parity |
| Preview — overlay structure | ✅ Box + header + body | ✅ Same structure | ✅ Parity |
| Preview — internal doc fetch | ✅ Direct API call | ✅ Fetch rendered page | ✅ Parity |
| Preview — external raw fetch | N/A (always local) | ✅ GitHub raw | ✅ Parity |
| Preview — Monaco for code | ✅ Admin has raw view | ✅ Monaco CDN | ✅ Parity |
| Preview — line tracking | ✅ IntersectionObserver | ❌ Raw source fetch breaks | ❌ BROKEN |
| Preview — header buttons | ✅ Back/Open/Edit | ✅ Jump/Edit (now mode-gated) | ✅ Parity |
| Dev/Live badge | N/A (vault is always dev) | ⚠️ Code exists but may not render | ⚠️ UNVERIFIED |
| Dev/Live toggle gates links | N/A (vault is always dev) | ✅ _peekMode() at click time | ✅ Done |
| Substring path matching | ✅ Word-boundary sufficient | ❌ Matches inside paths | ❌ BROKEN |

### Priority fixes needed (3 real issues)

1. **P0 — Path resolution (`src/` prefix)**: peek.py `_resolution_candidates()` —
   add `src/{path}` as a candidate for paths with `/`. This fixes BOTH Issue 1
   (full paths like `core/services/content/crypto.py`) and Issue 5
   (`adapters/containers/docker.py`).

2. **P1 — Line tracking**: Either fix `_fetchRawSource` to work without localhost:8000,
   OR use peek-index outline data as fallback for heading-line mapping.

3. **P2 — Badge rendering**: Verify `locationToDocPath()` produces correct keys.
   If the badge code never executes because page lookup fails, that's the issue.

---

## Content Vault features NOT present in Docusaurus (by design)

These exist in Content Vault but are **not applicable** to the static site:
- Edit mode (inline file editing)
- Delete button
- Upload/Release management
- Rename button
- Smart folder virtual path resolution
- Encrypted file preview
- Glossary sync
- Raw/Rendered/Edit toggle
- Back/Parent navigation (vault is SPA, docs are multi-page)
