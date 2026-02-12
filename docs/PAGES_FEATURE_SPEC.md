# Pages Feature — Specification

> **Created**: 2026-02-11 by USER direction (not AI-generated plans)
> **Status**: DRAFT — Awaiting user validation before any implementation
> **Scope**: Complete Pages feature — segment creation, configuration, build, preview, deployment

---

## 1. Segment Creation — Step-by-Step Wizard

A guided, multi-step flow — NOT a dump of inputs in a single modal.

### Step 1: Context
- What content folder are you building? (e.g. `docs/`, `blog/`, `api/`)
- Auto-detect available content folders from the project

### Step 2: Builder
- Choose builder: Docusaurus, MkDocs, Hugo, Sphinx, Raw, Custom
- Show description, requirements, install status for each
- If builder not installed → offer inline install before proceeding

### Step 3: Features & Options (builder-specific)
- **One by one** — NOT a wall of checkboxes
- Each option gets proper explanation, context, defaults
- For Docusaurus this includes 20+ options. Organized by category:

#### Content Features
- Mermaid diagrams
- GFM tables & strikethrough
- Math / KaTeX equations
- Extended Prism languages (Java, Rust, Go, PHP, Ruby, SQL, etc.)
- Prism themes (light/dark theme selection)

#### Site Features
- Local search (full-text, no external service)
- PWA support (installable, offline)
- Dark mode default
- GitHub link in navbar

#### Build Options
- Faster builds (Rspack — experimental_faster)
- TypeScript config
- future.v4 compatibility flags
- NODE_OPTIONS (memory control)
- Build mode (standard / no-minify / optimize)

#### Advanced: Remark/Rehype Plugins
- Custom remark directives (tabs support via `:::tabs`/`::tab`)
- System-viewer component embedding
- Custom rehype plugins
- Ability to add/configure arbitrary remark/rehype plugins

#### Advanced: Packages & Modules
- Add npm packages to the Docusaurus project
- Add custom theme components
- Add static assets
- Multiple sidebar configuration

#### Theme & Appearance
- Site title, tagline
- Custom CSS (with live preview concept)
- Navbar configuration
- Footer configuration

### Step 4: Review & Confirm
- Summary of all choices
- "Create" / "Create & Build" buttons

### Auto-Init Flow
- Detects content folders, picks best builder, sets sensible defaults
- User can **edit everything after** — the wizard re-opens with current config
- Auto-init is the fast path; manual wizard is the full-control path

---

## 2. Build Feedback & Live Progress

### 2.1 Build Trigger
- Build single segment
- Build all segments
- **Rebuild (smart)**: Only run stages that need re-running (like system-course reference)
  - Content unchanged → skip source + transform
  - package.json unchanged → skip npm install
  - Config unchanged + content hash match → skip Docusaurus build entirely
- **Clean build**: Wipe workspace + full pipeline from scratch
- Cancel button — abort build mid-pipeline

### 2.2 Live Build Modal
- Per-stage cards: Source → Transform → Scaffold → Install → Build
- Each card shows: status icon (pending/running/done/error), label, live timer, line count
- **Expandable log** per stage — click to see full output, click to collapse
- **Auto-expand** current running stage, auto-collapse completed stages
- Error tracking: failed stage highlighted red, error message shown, log auto-expanded
- Status updates visible even when not watching the modal (badge on Pages card updates)

### 2.3 Build Status in Main UI
- The Pages card should reflect build state in real-time
- Even if you close the build modal, if a build is running, the segment row shows progress
- After build: shows elapsed time, "built X ago", success/fail indicator

---

## 3. Preview & Viewing

### 3.1 Static Preview (Python Server)
- Click "🌐 View Site" → opens the built static output served by Flask
- URL: `/pages/site/<segment>/` — integrated, same origin, no random ports
- Works for ALL builders (they all produce static files in `build/`)

### 3.2 Content Vault Integration
- From the Pages card: "View in Content Vault" → opens the source folder in the file browser
- From the Content Vault: if browsing a folder that IS a segment source:
  - Show "View as Site" button → opens the built site
  - Show "Build & View" if not yet built → triggers build, then opens site
  - Per-file: if a `.md` file is part of a build segment, show link to its rendered page

### 3.3 Live Dev Server (Optional)
- Separate from static preview
- Starts the builder's native dev server (e.g. `docusaurus start`, `mkdocs serve`)
- Hot reload for authoring
- Start/stop per session

---

## 4. Smart Rebuild (Reference: system-course)

The reference project (`system-course/scripts/build_site.sh`) has sophisticated build intelligence:

### 4.1 Content Hash Skip
- Hash all source files (`docs/**/*.mdx`, `src/**/*.{ts,tsx,css}`, config files)
- If hash unchanged AND `build/` exists → skip entire Docusaurus build
- Saves 30-120 seconds per rebuild

### 4.2 Cache Management
- CSS changed → clear `.docusaurus/` cache
- Theme files changed → clear `.docusaurus/` cache
- package.json changed → clear `node_modules/.cache/`

### 4.3 Template Sync (not "regenerate everything")
- Config files: regenerated every build (managed by system)
- CSS: base template preserved, user additions appended after marker  
- Theme files (Root.tsx, hooks): generated once, user takes ownership
- Never destroy user customizations

### 4.4 Rspack Segfault Recovery
- If build exits code 139 (SIGSEGV) with `experimental_faster`:
  1. Clear caches
  2. Retry once
  3. If retry fails → disable faster and rebuild

### 4.5 Build Hash Injection
- Compute build hash → inject into `Root.tsx`
- On deploy, client detects new build hash → clears browser caches

---

## 5. Deployment

### 5.1 Merge Segments
- Combine multiple segment builds into single `gh-pages` site
- Each segment at its own URL path

### 5.2 Deploy to gh-pages
- Force-push merged output to `gh-pages` branch
- Uses `gh` CLI (project pattern: never raw REST API)

### 5.3 CI Generation
- Generate GitHub Actions workflow for automated builds/deploys
- Inject required secrets/variables

---

## 6. What Exists vs. What's Needed

> This section is based on reading the ACTUAL SOURCE CODE, not previous docs.

### What the code has (backend — `docusaurus.py`, 650 lines):
- 6-stage pipeline: source → transform → scaffold → install → build (+ output_dir, preview)
- Source: copies files, excludes hidden dirs
- Transform: MD→MDX rename, admonition conversion, frontmatter enrichment, link rewriting
- Scaffold: generates docusaurus.config.js, sidebars.js, custom.css, package.json via **string concatenation**
- Install: npm install with package.json hash skip
- Build: `npx docusaurus build`
- 5 feature toggles only: mermaid, gfm, math, dark_mode, github

### What the UI has (`_integrations.html`):
- Pages card with segment rows (pipeline dots, view site, build, remove)
- Add segment modal (name, source, builder, path — flat, no guidance)
- Configure segment modal (builder dropdown, title, 5 checkboxes, custom CSS — flat, no wizard)
- Build modal with SSE streaming (stage cards, live logs, timers — this part actually works reasonably)
- Auto-init, builder install, merge, deploy buttons

### What's MISSING (the 20+ features):
1. ✅ Step-by-step segment creation wizard (3-step: Name & Source → Builder → Configure with features)
2. ✅ Builder-specific feature configuration (11 features, 6 categories, dynamic from API)
3. ✅ Search plugin support (in registry + template)
4. ✅ PWA plugin support (in registry + template)
5. ✅ Faster builds (experimental_faster) toggle (in registry + template)
6. ✅ TypeScript config generation (docusaurus.config.ts, tsconfig.json)
7. ✅ Prism language selection (prism_extra feature)
8. ✅ Prism theme selection (5 theme pairs — github/dracula, VS Code, One Dark Pro, Night Owl, Oceanic Next)
9. ✅ Custom remark directive support (tabs, system-viewer in registry + template)
10. ✅ Custom rehype plugin configuration (via config.rehype_plugins JSON array)
11. ✅ Npm package management for segments (extra_packages config → merged into package.json)
12. ✅ Theme architecture (Root.tsx, hooks, build hash)
13. ✅ Template-based scaffold (template engine replaces string concat)
14. ✅ Smart rebuild (content hash skip — hashes workspace, skips if unchanged)
15. ✅ Cache management (CSS/theme change detection, auto-clear .docusaurus/)
16. ✅ Rspack segfault recovery (retry on exit 139, auto-disable experimental_faster)
17. ✅ Clean build option (🧹 button + ?clean=true API param)
18. ✅ Build cancel button (⛔ Cancel Build during run, 🔄 Retry + 🧹 Clean Retry on failure)
19. ✅ Persistent build status (pulsing ● + stage name on segment row while building)
20. ✅ Content Vault ↔ Pages bidirectional integration (📖 Pages link in vault preview → resolve-file API)
21. ✅ Template sync engine (file ownership policies — Root.tsx user-owned)
22. ✅ Build modes (standard / no-minify via ?no_minify=true API param)
23. ✅ NODE_OPTIONS configuration (configurable via segment config, default 4GB)
24. ✅ Multiple sidebar support (extra_sidebars config → sidebars.ts template slot)
25. ✅ Navbar configuration beyond "Docs" + GitHub (navbar_items config → config template slot)
26. ✅ Static assets management (auto-copies source/static/ into workspace)
27. ✅ CI workflow generation (generates `.github/workflows/deploy-pages.yml`)

---

## 7. Implementation Order

> Not implementing yet — just the logical sequence. Each phase builds on the previous.

### Phase 1: Template Foundation ✅ DONE
Replace string concatenation with real template files + conditional processor.
Without this, nothing else works properly.

**Delivered:**
- `pages_builders/template_engine.py` — template processor + feature registry (11 features, 6 categories)
- `pages_builders/templates/docusaurus/` — 8 template files (config, CSS, theme, hooks)
- Refactored `_stage_scaffold` in `docusaurus.py` — uses templates, not string concat
- `GET /pages/features` API endpoint — exposes feature registry to UI
- Docusaurus 3.9.2 with TypeScript config, tsconfig, sidebars.ts
- Theme architecture: Root.tsx + build hash hook (user-owned, won't overwrite)
- Build hash computation for cache invalidation

### Phase 2: Feature Registry & Configuration ✅ DONE
Define all features properly, make them configurable, wire them through templates.

**Delivered** (alongside Phase 1):
- 11 features across 6 categories, all wired through templates
- `GET /pages/features` API endpoint for dynamic UI rendering
- Feature-specific dependencies auto-injected into package.json

### Phase 3: Segment Configuration UI ✅ DONE
Dynamic configuration experience driven by the feature registry.

**Delivered:**
- `configureSegment()` rewritten to fetch from `/pages/features` API
- Features grouped by category with toggle switches (not hardcoded checkboxes)
- Added tagline field, dependency badges (`+deps`), helper text
- Custom CSS editor with usage guidance
- Removed hardcoded `DOCUSAURUS_FEATURES` array (was only 5 features)
- Still TODO: Step-by-step *creation* wizard (vs editing existing segments)

### Phase 4: Build Intelligence ✅ DONE
Content hash, cache management, smart rebuild, Rspack recovery, clean build.

**Delivered:**
- `_compute_workspace_hash()` — SHA-256 of all docs/src/config files (24-char digest)
- Content hash skip — saves `.content_hash`, skips entire `npx docusaurus build` if unchanged
- `_maybe_clear_caches()` — tracks config/CSS/theme changes via `.cache_hash`, clears `.docusaurus/` and `node_modules/.cache/`
- Rspack segfault recovery — exit code 139 (SIGSEGV): retry once, then disable `experimental_faster` and retry again
- `NODE_OPTIONS` — configurable `--max-old-space-size` (default 4096MB)
- Clean build — `?clean=true` API parameter, 🧹 button in UI, wipes all caches
- Build modes — `?no_minify=true` API parameter, `--no-minify` flag appended to build cmd
- `_run_docusaurus_build()` — extracted subprocess execution, returns (lines, returncode)
- Build cancel button — ⛔ Cancel Build while running, 🔄 Retry + 🧹 Clean Retry on failure

### Phase 5: Preview & Integration
Content Vault integration, per-file preview links, live dev server.

### Phase 6: Theme Architecture ✅ DONE (delivered in Phase 1)
Root.tsx, hooks, build hash injection.

**Delivered** (as part of Phase 1):
- `Root.tsx.tmpl` — user-owned theme root with build hash injection
- `useBuildHashCheck.ts` hook — client-side cache invalidation
- `compute_build_hash()` — deterministic hash from config + pkg + css
- Build hash injection via regex replacement in `_stage_scaffold`

### Phase 7: Deployment & CI ✅ DONE (already implemented)
Merge, deploy, CI generation.

**Delivered** (pre-existing in `pages_engine.py`):
- `merge_segments()` — copies all built segment outputs into `_merged/`, generates hub page
- `deploy_to_ghpages()` — inits temp git repo in `_merged/`, force-pushes to `gh-pages`
- `generate_ci_workflow()` — generates `.github/workflows/deploy-pages.yml` with proper setup steps
- All three wired to API routes (`POST /pages/merge`, `/deploy`, `/generate-ci`)
- Frontend buttons already exist in pipeline actions bar

---

**⚠️ This document is a clean spec from user direction. Do NOT merge with or reference the old `DOCUSAURUS_BUILDER_DEEP_ANALYSIS.md` or `PAGES_PIPELINE_PLAN.md` — those contain AI-generated garbage mixed with truth and should NOT be trusted as source of truth.**
