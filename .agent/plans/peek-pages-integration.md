# Peek → Pages Integration — Solution Analysis & Planning

## 1. Problem Statement

The live admin panel (Web Admin at `:8000`) has a rich set of Peek features for
cross-referencing files, symbols, and directories within documentation. These
features make documentation *alive* — references become clickable, previewable,
and navigable.

The built documentation site (Docusaurus via Pages segment) should provide a
comparable experience to readers. Some Peek infrastructure already exists in the
build pipeline, but it's incomplete and has not been tested against recent
Peek evolutions.

This document maps every Peek capability, its current status in the build
pipeline, the gap, and the work required.

---

## 2. Current State Inventory

### 2.1 Peek Capabilities in the Live Admin Panel

| ID | Feature | Backend | Frontend |
|----|---------|---------|----------|
| P1 | **Reference scanning** — detect file/path/class/function/symbol refs in markdown | `peek.py:scan_peek_candidates()` — T1–T6 type system | `_preview.html` calls `/api/content/peek-refs` |
| P2 | **Reference resolution** — resolve against filesystem + symbol index | `peek.py:resolve_peek_candidates()` | `_preview.html` calls `/api/content/peek-resolve` |
| P3 | **Word-boundary annotations** — highlight refs in rendered markdown DOM | — | `_preview.html:_peekAnnotateAll()` — walks DOM text nodes, wraps matches |
| P4 | **Peek tooltips** — click to see path, actions (open, browse, jump) | — | `_preview.html:_peekShowTooltip()` — positioned tooltip with actions |
| P5 | **Peek preview overlay** — click "Preview" to see file content inline | `/api/content/preview` (renders markdown) | `_preview.html:_peekOpenPreview()` — overlay with rendered content |
| P6 | **Directory peek** — browse dir contents inline, open README | `/api/content/list` | `_preview.html:_peekPreviewDirHTML()` |
| P7 | **Smart folder navigation** — virtual paths, module tree | `/api/smart-folders/<name>/tree` | `_smart_folders.html:_smartFolderRenderDocTree()` |
| P8 | **Smart folder peek panel** — hover to preview with tree context | `/api/smart-folders/<name>/peek` | `_smart_folders.html` (peek panel integration) |
| P9 | **Path not found recovery** — create README, suggestions, browse raw | `/api/content/save` (with `allow_create`) | `_smart_folders.html` — recovery page with 4 options |
| P10 | **Module not found recovery** — fuzzy suggestions, navigate back | — | `_smart_folders.html` — fuzzy matching via `_sfLevenshtein` |
| P11 | **Unresolved reference markers** — dimmed annotations for refs that don't resolve | — | `_preview.html` — `peek-link--unresolved` class |

### 2.2 Peek Infrastructure Already in the Build Pipeline

| Component | File | Status |
|-----------|------|--------|
| **Feature flag** | `template_engine.py` — `"peek"` feature (default: `False`) | ✅ Exists |
| **Build-time scanning** | `docusaurus.py:_stage_scaffold()` lines 552–612 | ✅ Exists — scans all `.mdx` files, resolves refs, writes `peek-index.json` |
| **Symbol index** | `peek.py:build_symbol_index()` | ✅ Exists — called during build |
| **`peek-index.json`** | Written to `workspace/src/peek-index.json` | ✅ Exists — JSON map of doc paths → refs |
| **React hook** | `usePeekLinks.ts` — DOM annotation at runtime | ✅ Exists — 508 lines, full annotation + tooltip + preview |
| **CSS** | `custom.css.tmpl` lines 294–560 | ✅ Exists — `.peek-link`, `.peek-tooltip`, `.peek-preview-overlay` |
| **Conditional in Root.tsx** | `Root.tsx.tmpl` — `// __IF_FEATURE_peek__` block | ✅ Exists (assumed) |

### 2.3 What's Missing / Broken / Incomplete

| Gap | Severity | Details |
|-----|----------|---------|
| **G1: Feature is off by default** | Minor | `"peek"` feature default is `False` — users must manually enable it |
| **G2: No directory preview in built site** | Medium | `usePeekLinks.ts` tooltip says "Preview" for directories but can only fetch the README via raw GitHub URL — no dir listing |
| **G3: No smart folder context in tooltips** | Medium | Built site tooltips show only file path — no module/tree context |
| **G4: Preview only works locally OR with GitHub raw** | Medium | `_openPeekPreview()` uses `localhost:8000` API locally, `raw.githubusercontent.com` Published — breaks if neither |
| **G5: No heading outline in tooltips** | Low | Live admin shows heading outline on hover; built site tooltip only shows path + actions |
| **G6: No cross-doc linking** | High | References are annotated but don't navigate to the doc page within the built site — they link to GitHub or localhost |
| **G7: Reference type not shown** | Low | Live admin distinguishes T1 (file), T5 (symbol), T6 (directory) — built site treats all the same |
| **G8: Unresolved refs from recent changes** | Unknown | `scan_and_resolve_all` now returns a 3-tuple; need to verify build code handles this |
| **G9: Index-driven scanner not reflected** | Medium | `_index_driven_scan()` was added after initial peek build code — verify it's called |
| **G10: No smart sidebar** | Medium | Built site uses vanilla Docusaurus autogenerated sidebar — no smart folder grouping |

---

## 3. Architecture Overview

### 3.1 Data Flow: Build Time

```
project.yml segment
    ↓
[Stage 1: source] → Copy source files + smart folder staging
    ↓
[Stage 2: transform] → MD → MDX (admonitions, frontmatter, links, JSX escape)
    ↓
[Stage 3: scaffold]
    ├── Generate config, CSS, package.json, Root.tsx
    ├── [PEEK] Scan all .mdx files with scan_and_resolve_all()
    ├── [PEEK] Build symbol index
    ├── [PEEK] Write peek-index.json
    └── [NEW: CROSSREF] → Rewrite in-doc refs as Docusaurus internal links
    ↓
[Stage 4: install] → npm install (cached)
    ↓
[Stage 5: build] → npx docusaurus build
```

### 3.2 Data Flow: Runtime (Built Site)

```
Page load → usePeekLinks hook
    ↓
locationToDocPath(url) → lookup peek-index.json
    ↓
annotatePeekRefs() → walk DOM, wrap text matches in <span.peek-link>
    ↓
Click → showPeekTooltip() → path + actions (preview, GitHub, Vault)
    ↓
Preview → _openPeekPreview() → fetch raw content → overlay
```

### 3.3 Key Files

| File | Purpose |
|------|---------|
| `src/core/services/peek.py` | Scanner + resolver (used at build AND live) |
| `src/core/services/pages_builders/docusaurus.py` | Builder pipeline |
| `src/core/services/pages_builders/template_engine.py` | Feature registry |
| `src/core/services/pages_builders/docusaurus_transforms.py` | MD→MDX transforms |
| `src/core/services/pages_builders/smart_folder_enrichment.py` | Smart folder enrichment passes |
| `templates/docusaurus/theme/hooks/usePeekLinks.ts` | Runtime React hook |
| `templates/docusaurus/css/custom.css.tmpl` | Peek CSS styles |

---

## 4. Solution Design

### Phase 1: Fix & Verify Existing Peek Build (Immediate)

**Goal**: Make the existing `peek` feature work correctly with all recent changes.

#### 4.1.1 Verify 3-tuple handling
- `scan_and_resolve_all()` now returns `(resolved, unresolved, pending)`
- Build code at line 580 already destructures correctly: `resolved, unresolved, _pending`
- **Status: OK** — no change needed

#### 4.1.2 Enable peek by default
- Change `template_engine.py` feature default from `False` to `True`
- This is the simplest way to get peek into all new builds

#### 4.1.3 Verify index-driven scanner
- `scan_and_resolve_all()` internally calls `_index_driven_scan()`
- Build code calls `scan_and_resolve_all()` → **already included**
- **Status: OK** — no change needed

#### 4.1.4 Test with actual build
- Build a smart folder segment with `peek: true`
- Verify `peek-index.json` is generated with resolved refs
- Verify `usePeekLinks.ts` annotates text correctly
- Verify tooltip + preview work (locally and published)

### Phase 2: Cross-Doc Linking (High Value)

**Goal**: File references that point to OTHER docs in the same segment should
be Docusaurus internal links, not just annotations.

#### 4.2.1 New transform: `inject_crossref_links()`

Add to `docusaurus_transforms.py`:

```python
def inject_crossref_links(content: str, refs: list[dict], docs_dir: Path, doc_rel: str) -> str:
    """Replace resolved file references with Docusaurus markdown links.

    For refs that resolve to files WITHIN the docs_dir, rewrite as relative
    markdown links so Docusaurus renders them as SPA navigation links.

    For refs that resolve OUTSIDE docs_dir, keep as peek annotations
    (handled by usePeekLinks.ts at runtime).
    """
```

**Logic**:
1. For each resolved ref:
   a. Check if `resolved_path` maps to a file in the staged `docs/` directory
   b. If yes → rewrite the text as `[text](./relative/path.mdx)` in the MDX
   c. If no → leave as-is (usePeekLinks.ts handles it at runtime)
2. This runs AS PART of the transform stage, not a new stage

**Benefit**: ~50% of refs in smart folder docs point to sibling docs → instant
navigable links without any JS runtime.

#### 4.2.2 Split peek-index into internal vs external

After cross-doc linking, `peek-index.json` should only contain:
- **External refs** — files outside the docs (source code, configs)
- **Unresolved refs** — for the dimmed annotation

Internal refs become actual `<a>` links in MDX → no runtime annotation needed.

### Phase 3: Enriched Tooltips (Medium Value)

**Goal**: Tooltips show more context than just the file path.

#### 4.3.1 Heading outline data

At build time, for each resolved external ref:
- If it's a `.md` file → extract `# ` headings
- If it's a `.py` file → extract function/class names from symbol index
- Store as `outline` field in `peek-index.json`

```json
{
  "core/services/audit/index.mdx": [
    {
      "text": "audit_ops.py",
      "resolved_path": "src/core/services/audit/audit_ops.py",
      "outline": ["run_audit()", "AuditResult", "SEVERITY_MAP"],
      "resolved": true
    }
  ]
}
```

#### 4.3.2 Update usePeekLinks.ts tooltip

Show outline items in tooltip when available:

```
📄 src/core/services/audit/audit_ops.py
  ├─ run_audit()
  ├─ AuditResult
  └─ SEVERITY_MAP
[👁 Preview] [↗ GitHub]
```

### Phase 4: Smart Sidebar (Low Priority, High Polish)

**Goal**: Built site sidebar mirrors the smart folder tree structure.

#### 4.4.1 Generate sidebar from smart folder groups

During enrichment (`smart_folder_enrichment.py`), the tree structure is already
known. Generate a custom `sidebars.ts` that groups modules:

```typescript
module.exports = {
  docs: [
    {
      type: 'category',
      label: '⚙️ Core',
      items: [{type: 'autogenerated', dirName: 'core'}],
    },
    {
      type: 'category',
      label: '🔌 Adapters',
      items: [{type: 'autogenerated', dirName: 'adapters'}],
    },
    // ...
  ],
};
```

This is already partially done by `_generate_categories()` in enrichment.

---

## 5. Implementation Plan

### Phase 1: Fix & Verify (1-2 hours)

| Step | Task | File | Risk |
|------|------|------|------|
| 1.1 | Change peek default to `True` | `template_engine.py` | None |
| 1.2 | Test build with peek enabled | — | Low |
| 1.3 | Verify peek-index.json output | — | Low |
| 1.4 | Test usePeekLinks.ts in built site | — | Medium |
| 1.5 | Fix any runtime issues found | `usePeekLinks.ts` | Medium |

### Phase 2: Cross-Doc Linking (3-4 hours)

| Step | Task | File | Risk |
|------|------|------|------|
| 2.1 | Write `inject_crossref_links()` | `docusaurus_transforms.py` | Medium |
| 2.2 | Integrate into `_stage_transform()` or scaffold | `docusaurus.py` | Medium |
| 2.3 | Build mapping: resolved_path → docs_dir relative path | `docusaurus.py` | Medium |
| 2.4 | Split peek-index into external-only refs | `docusaurus.py` | Low |
| 2.5 | Test: verify internal links render as Docusaurus nav | — | Medium |
| 2.6 | Test: verify external refs still get peek annotations | — | Low |

### Phase 3: Enriched Tooltips (2-3 hours)

| Step | Task | File | Risk |
|------|------|------|------|
| 3.1 | Extract heading outlines at build time | `docusaurus.py` | Low |
| 3.2 | Extract symbol outlines from symbol index | `docusaurus.py` | Low |
| 3.3 | Add `outline` field to peek-index.json entries | `docusaurus.py` | Low |
| 3.4 | Update tooltip rendering in usePeekLinks.ts | `usePeekLinks.ts` | Medium |
| 3.5 | Test: verify outlines appear in tooltip | — | Low |

### Phase 4: Smart Sidebar (2 hours)

| Step | Task | File | Risk |
|------|------|------|------|
| 4.1 | Generate module-grouped sidebar config | `smart_folder_enrichment.py` | Medium |
| 4.2 | Wire into scaffold stage sidebar generation | `docusaurus.py` | Medium |
| 4.3 | Test: verify sidebar groups match smart folder modules | — | Low |

---

## 6. Dependencies & Risks

| Risk | Mitigation |
|------|-----------|
| Cross-doc linking could break MDX if refs appear inside code blocks | Only rewrite refs in prose text nodes, skip fenced/inline code |
| peek-index.json could be very large for big projects | Only include external refs after cross-doc linking strips internal ones |
| usePeekLinks.ts preview may fail if GitHub repo is private | Show clear "private repo" message instead of error |
| Transform order matters — crossref must run AFTER MDX transforms | Sequence: admonitions → frontmatter → links → JSX escape → crossref |

---

## 7. Success Criteria

- [ ] Smart folder segment builds with `peek: true` (default)
- [ ] File/symbol references within docs become clickable Docusaurus links
- [ ] External file references get peek annotations with tooltips
- [ ] Tooltip shows: icon, path, outline items, actions (preview, GitHub)
- [ ] Preview overlay works: locally (via API) and published (via GitHub raw)
- [ ] Sidebar groups documents by module (matching smart folder structure)
- [ ] No regressions in existing transforms (admonitions, frontmatter, links)

---

## 8. Out of Scope (Future)

- **Live editing from built site** — the admin panel is the editing surface
- **Real-time peek resolution** — the built site uses pre-computed data only
- **Cross-segment peek** — references between different Pages segments
- **Peek for non-markdown** — previewing images, PDFs, etc.
- **Path not found recovery in built site** — this is an admin panel feature
  (creating files from the built site doesn't make sense)
