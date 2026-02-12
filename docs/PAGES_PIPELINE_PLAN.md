# 📄 Pages Pipeline — Comprehensive Implementation Plan

> **Status**: IN PROGRESS — Phase A–D backend+frontend implemented, Phase E testing pending
> **Scope**: ~20 hours of implementation across backend, frontend, and integration layers
> **Principle**: Everything is pluggable. Nothing works alone. A pipeline is a chain of stages, each observable, each producing something the next stage consumes.

---

## 0. What's Wrong With What Exists Today

The current implementation is a **collection of disconnected endpoints and buttons**:

- Build produces output nobody can see
- Preview launches random `http.server` processes on random ports — not integrated
- Docusaurus builder runs `npm install` silently in `scaffold()` — no progress, blocks forever
- The UI has no pipeline visualization — just a wall of buttons
- No connection between Content Vault (file browser) and Pages (rendered site)
- No augmentation layer — no custom navbar, no sidebar enrichment, no hooks
- Builder installation half-works (Hugo GLIBC issue, no progress for npm)
- Each piece was built in isolation, never tested as a chain

**Core mistake**: Treating each endpoint/button as a standalone feature instead of designing the **pipeline as a whole** — where each stage feeds into the next, every transition is observable, and the output is usable.

---

## 1. Architecture — The Pipeline Model

### 1.1 What IS a Pipeline?

A pipeline is an **ordered chain of named stages**. Each stage:
- Takes input from the previous stage's output
- Does one thing
- Reports progress (log lines, timing, status)
- Produces output for the next stage
- Can fail independently (and the pipeline stops with a clear error at that stage)

### 1.2 Docusaurus Pipeline (reference implementation)

```
Source          →  Transform       →  Enrich         →  Scaffold        →  Install         →  Build           →  Serve
━━━━━━━━━━━     ━━━━━━━━━━━━━     ━━━━━━━━━━━━     ━━━━━━━━━━━━━     ━━━━━━━━━━━━     ━━━━━━━━━━━━━     ━━━━━━━━━━━
Read docs/       MD → MDX          Remark plugins    docusaurus.config  npm install       npx docusaurus    Flask serves
decrypt .enc     admonitions       remark-gfm        package.json       (once, cached)    build --out-dir   at /pages/
restore .large   frontmatter       remark-math       sidebars.js                                            site/docs/
filter hidden    link rewriting    mermaid support    custom.css
                 rename .md→.mdx   math support       navbar config
                                                      sidebar config
```

Each of these stages is a **discrete, named, timed operation** that reports to the UI.

### 1.3 MkDocs Pipeline

```
Source          →  Scaffold        →  Install         →  Build           →  Serve
━━━━━━━━━━━     ━━━━━━━━━━━━━     ━━━━━━━━━━━━     ━━━━━━━━━━━━━     ━━━━━━━━━━━
Read source      mkdocs.yml        pip install        mkdocs build       Flask serves
filter hidden    theme config      (venv, cached)                        at /pages/
                 nav from tree                                           site/<seg>/
```

### 1.4 Hugo Pipeline

```
Source          →  Scaffold        →  Build           →  Serve
━━━━━━━━━━━     ━━━━━━━━━━━━━     ━━━━━━━━━━━━━     ━━━━━━━━━━━
Read source      hugo.toml         hugo build         Flask serves
symlink content  theme config
```

### 1.5 Raw Pipeline

```
Source          →  Copy            →  Serve
━━━━━━━━━━━     ━━━━━━━━━━━━━     ━━━━━━━━━━━
Read source      rsync (excl.)     Flask serves
filter hidden    to build/         at /pages/site/<seg>/
```

### 1.6 Key Insight: Every Pipeline Ends With Serve

The final stage is ALWAYS the same: **Flask serves the built static files at an integrated URL**. Not a random port. Not a separate process. The Flask app itself serves `GET /pages/site/<segment>/<path>` directly from `.pages/<segment>/build/`.

---

## 2. Pipeline Stage Model

### 2.1 Data Model

```python
@dataclass
class PipelineStage:
    name: str               # "source", "transform", "enrich", "scaffold", "install", "build", "serve"
    label: str              # Human: "MD → MDX Transform"
    status: str             # "pending" | "running" | "done" | "error" | "skipped"
    duration_ms: int = 0
    log_lines: list[str] = field(default_factory=list)
    error: str = ""

@dataclass
class PipelineResult:
    segment: str
    builder: str
    stages: list[PipelineStage]
    ok: bool
    total_duration_ms: int
    serve_url: str          # "/pages/site/docs/" — always populated on success
```

### 2.2 Builder Contract (enhanced)

Each builder must declare its stages:

```python
class PageBuilder(ABC):
    def pipeline_stages(self) -> list[str]:
        """Return ordered list of stage names this builder uses."""
        # e.g. ["source", "transform", "enrich", "scaffold", "install", "build"]

    def run_stage(self, stage: str, segment: SegmentConfig, workspace: Path) -> PipelineStage:
        """Run a single stage. Returns result with log and timing."""
```

This replaces the current monolithic `scaffold()` + `build()` split, which doesn't give stage-level observability.

### 2.3 SSE Streaming Per Stage

The build stream endpoint sends events per stage:

```
data: {"type":"stage_start", "stage":"transform", "label":"MD → MDX Transform"}
data: {"type":"log", "line":"Converting docs/QUICKSTART.md → docs/QUICKSTART.mdx"}
data: {"type":"log", "line":"Converting docs/DESIGN.md → docs/DESIGN.mdx"}
data: {"type":"stage_done", "stage":"transform", "duration_ms": 45, "files": 8}

data: {"type":"stage_start", "stage":"install", "label":"npm install"}
data: {"type":"log", "line":"added 1247 packages in 32s"}
data: {"type":"stage_done", "stage":"install", "duration_ms": 32100}

data: {"type":"stage_start", "stage":"build", "label":"Docusaurus Build"}
data: {"type":"log", "line":"[SUCCESS] Generated static files in \"build\"."}
data: {"type":"stage_done", "stage":"build", "duration_ms": 8500}

data: {"type":"pipeline_done", "ok": true, "total_ms": 40700, "serve_url": "/pages/site/docs/"}
```

---

## 3. Flask Integrated Hosting

### 3.1 Static File Serving Route

```python
# In routes_pages.py (not api — these are user-facing page routes)

@pages_bp.route("/pages/site/<segment>/<path:filepath>")
@pages_bp.route("/pages/site/<segment>/")
def serve_pages_site(segment, filepath="index.html"):
    """Serve built pages output as a static site."""
    build_dir = project_root / ".pages" / segment / "build"
    return send_from_directory(build_dir, filepath)
```

### 3.2 Why This Matters

- **One URL**: `http://127.0.0.1:8000/pages/site/docs/` — always the same
- **No random ports**: Works even after restart
- **Integrated**: Same origin as the admin panel — no CORS, no separate processes
- **Works for ALL builders**: Raw, MkDocs, Hugo, Docusaurus — they all produce static files in `build/`

### 3.3 Preview Dev Servers (Separate — For Live Editing)

The random-port preview servers are still useful for **live editing** (hot reload). But they're SEPARATE from the integrated hosting:

- **Integrated hosting** (`/pages/site/docs/`): The built output. Always available. No process to manage.
- **Preview dev server** (`:8300`): Live-reload for authoring. Start/stop per session. Optional.

The UI should make this distinction clear:
- "🌐 View Site" → opens `/pages/site/docs/` (the built output)
- "🔄 Live Preview" → starts the builder's dev server for hot reload (docusaurus start, mkdocs serve)

---

## 4. Docusaurus Augmentation Layer

### 4.1 What the User Asked For

Not just "build docs with Docusaurus." The full chain:
- **Augmented Navbar**: Auto-generated from project structure, segments, config
- **Augmented Sidebar**: Auto-generated from directory tree with smart ordering
- **Theme Hooks**: Custom dark mode, indigo palette, code highlighting
- **Remark Plugins**: GFM tables, math equations, mermaid diagrams
- **Rehype Plugins**: Heading anchors, code line highlighting
- **Content Integration**: Decrypt .enc files, restore .large files from releases

### 4.2 Navbar Generation

The navbar should reflect the project, not just say "Docs":

```javascript
navbar: {
  title: 'DevOps Control Plane',        // From project.yml name
  items: [
    { type: 'docSidebar', sidebarId: 'docs', label: 'Docs', position: 'left' },
    // If multiple segments exist, show them all:
    // { href: '/pages/site/api/', label: 'API', position: 'left' },
    { href: 'https://github.com/<owner>/<repo>', label: 'GitHub', position: 'right' },
  ],
}
```

The navbar items should be **generated from the segments list** and **project.yml repository config**.

### 4.3 Sidebar Generation

Beyond `autogenerated` — smart ordering by:
1. Numeric prefix in filename: `001-intro.md` → position 1
2. README/index files always first
3. Directories become categories with labels from frontmatter or dirname
4. Support for `_category_.json` files (Docusaurus convention)

### 4.4 Remark/Rehype Pipeline

Configure in `docusaurus.config.js`:

```javascript
docs: {
  remarkPlugins: [
    [require('remark-gfm'), {}],
    // Future: remark-math, remark-directive
  ],
  rehypePlugins: [
    // Future: rehype-slug, rehype-autolink-headings
  ],
}
```

These are npm packages — must be in `package.json` dependencies and installed.

---

## 5. Content Vault Integration

### 5.1 "View as Site" in File Browser

When the user is browsing a content folder that corresponds to a pages segment (e.g. `docs/`):

- Show a **"🌐 View as Site"** button in the toolbar
- Links to `/pages/site/docs/`
- Only visible when the segment has been built at least once
- Shows the builder name and last build time

### 5.2 How to Detect

The API already returns segment data. The content browser knows the current folder path.
If `folder === segment.source` → show the button.

### 5.3 "Build & View" Flow

If the segment hasn't been built yet:
1. Button says "🔨 Build & View"
2. Click → triggers build stream modal
3. On success → opens the site URL

---

## 6. UI — Pipeline Visualization

### 6.1 Build Stream Modal (reworked)

Instead of a plain text log, show **stage cards**:

```
┌─────────────────────────────────────────────────┐
│  🔨 Building: docs (docusaurus)                  │
│                                                   │
│  ✅ Source          12 files    3ms               │
│  ✅ Transform       8 .md → .mdx    45ms          │
│  ✅ Enrich          remark-gfm, mermaid    2ms    │
│  ✅ Scaffold        docusaurus.config.js    8ms   │
│  ✅ Install         1247 packages    32.1s        │
│  🔄 Build           [===========        ]  8.5s  │
│                                                   │
│  ┌─────────────────────────────────────────────┐ │
│  │ [log output scrolls here]                    │ │
│  │ [SUCCESS] Generated static files in "build". │ │
│  └─────────────────────────────────────────────┘ │
│                                                   │
│  [🌐 View Site]  [🔄 Live Preview]  [Close]      │
└─────────────────────────────────────────────────┘
```

### 6.2 Segment Row in Pages Card

```
●→●→●→●→●  docs  docs/  docusaurus ▾  🌐 :8000/pages/site/docs/  built 2m ago · 41.2s  🔨 🔄 ✕
```

Where:
- `●→●→●→●→●` = pipeline stage dots (Source → Transform → Build → Serve → Deploy)
- `🌐` = link to the integrated site
- `🔄` = start live preview (dev server)
- `🔨` = rebuild

### 6.3 Builders Panel

Keep what exists but add:
- Status: installed ✅, not installed ❌, installing ⏳
- Each builder shows what pipeline stages it supports
- Install button with SSE streaming (already done, mostly works)

---

## 7. Implementation Plan — Ordered by Dependencies

### Phase A: Pipeline Core (backend) — ~6h

1. **Define `PipelineStage` model** in `pages_builders/base.py`
2. **Add `pipeline_stages()` and `run_stage()` to `PageBuilder` ABC**
3. **Rewrite `DocusaurusBuilder`** to implement stage-by-stage execution:
   - `source`: Copy + filter files from source dir
   - `transform`: MD → MDX (admonitions, frontmatter, links)
   - `enrich`: Configure remark/rehype plugins in config
   - `scaffold`: Generate docusaurus.config.js, package.json, sidebars.js, custom.css
   - `install`: npm install (streamed, skip if node_modules fresh)
   - `build`: npx docusaurus build
4. **Rewrite other builders** with same stage model (simpler — fewer stages)
5. **Docusaurus augmentation**: Smart navbar from project.yml + segments, smart sidebar ordering
6. **Update `build-stream` endpoint** to emit stage_start/stage_done events

### Phase B: Integrated Hosting (backend + frontend) — ~3h

7. **Add `/pages/site/<segment>/<path>` route** to `routes_pages.py`
8. **Handle SPA routing** — Docusaurus uses client-side routing, so `index.html` fallback needed
9. **Update Pages card UI** — add 🌐 View Site link for each segment with a build
10. **Update build modal** — show "🌐 View Site" and "🔄 Live Preview" buttons after success

### Phase C: Build Modal Pipeline UI — ~4h

11. **Redesign build modal** — stage cards with status indicators
12. **Parse SSE stage events** — update stage cards in real-time
13. **Progress indicators** — show running stage, completed stages, timing
14. **Log panel** — collapsible, shows current stage's log output
15. **Error handling** — failed stage highlighted, clear error message

### Phase D: Content Vault Integration — ~3h

16. **Detect when browsing a segment source folder** — match `contentCurrentPath` against segments
17. **Add "🌐 View as Site" button** to content browser toolbar
18. **Add "🔨 Build & View" flow** — build if not built, then open site
19. **Show segment info** — builder, last build time, pipeline stages

### Phase E: Polish & Testing — ~4h

20. **Test full Docusaurus pipeline** — create segment, build, view, edit, rebuild
21. **Test MkDocs pipeline** — same flow
22. **Test Raw pipeline** — same flow
23. **Test Hugo pipeline** — binary download + build
24. **Test builder installation** — pip, npm, Hugo binary
25. **Test Content Vault integration** — View as Site button
26. **Error cases** — missing deps, build failures, corrupt source
27. **Fix npm install caching** — skip if `package.json` hasn't changed
28. **Cleanup** — remove dead code, consolidate endpoints

---

## 8. What Already Works (keep)

- ✅ Builder detection (`detect()`)
- ✅ Builder installation SSE (pip-based, Hugo binary download)
- ✅ Segment CRUD (`add`, `update`, `delete`)
- ✅ Build streaming SSE — **stage-aware** (pipeline_start, stage_start, log, stage_done, pipeline_done)
- ✅ MD → MDX transform logic (admonitions, frontmatter, links)
- ✅ Docusaurus config generation — **augmented** (navbar w/ GitHub, sidebar, custom CSS)
- ✅ Segment config modal (change builder)
- ✅ project.yml integration
- ✅ Pipeline stage model (`StageInfo`, `StageResult`, `PipelineResult`, `run_pipeline`)
- ✅ All 6 builders migrated to stage model (raw, mkdocs, hugo, sphinx, custom, docusaurus)
- ✅ Integrated hosting: Flask serves `/pages/site/<segment>/` with SPA fallback
- ✅ Build modal: stage cards with real-time status, timing, collapsible log
- ✅ Segment rows: 🌐 View Site links, pipeline dots (source → build → serve)
- ✅ Content browser: "View as Site" button when browsing a segment folder
- ✅ npm install caching (package.json hash)
- ✅ Builders list API includes pipeline stages

## 9. What Still Needs Work

- ✅ Docusaurus Enrich — remark-gfm, remark-math, rehype-katex, mermaid configured in scaffold
- ✅ "Build & View" flow from Content Vault (build if not built, then open site)
- ✅ Removed preview() random-port toggle from segment rows
- ✅ Better auto-init (detect .md files → suggest docusaurus, offer install)
- ⬜ Auto-decrypt .enc files during build (security implications — needs decision)
- ⬜ Test full end-to-end for all builders
- ⬜ Docusaurus: Handle baseUrl correctly for integrated hosting (/pages/site/docs/)

---

## 11. Files Affected

| File | Change Type |
|------|-------------|
| `pages_builders/base.py` | Add `PipelineStage`, `pipeline_stages()`, `run_stage()` |
| `pages_builders/docusaurus.py` | Major rewrite — stage-based pipeline |
| `pages_builders/mkdocs.py` | Moderate — add stage methods |
| `pages_builders/hugo.py` | Moderate — add stage methods |
| `pages_builders/raw.py` | Minor — add stage methods |
| `pages_builders/sphinx.py` | Moderate — add stage methods |
| `routes_pages.py` | Add `/pages/site/<segment>/<path>` static serving |
| `routes_pages_api.py` | Rewrite `build-stream` for stage events |
| `pages_engine.py` | Update build orchestration for stages |
| `templates/scripts/_integrations.html` | Major — stage visualization, site links |
| `templates/scripts/_content_browser.html` | Add "View as Site" button |

---

## 12. Open Questions for User

1. **Navbar items**: Should the navbar auto-include links to all segments, or just the current one?
2. **Theme**: Keep the indigo/dark palette, or should it be configurable per segment?
3. **Live preview vs integrated hosting**: Should both always be available, or should live preview only appear during active editing sessions?
4. **Content Vault .enc files**: Should the build pipeline auto-decrypt for the build workspace? (Security implication: built output would contain decrypted content)
