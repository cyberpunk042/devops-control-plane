# 🔌 Integrations — Architecture & Implementation Plan

> **Status**: Draft for discussion — decisions made, ready for Phase 1  
> **Date**: 2026-02-11  
> **Principle**: This control plane works on **any project** — nothing is hardcoded to a specific stack.

---

## 1. Current State Audit

### What exists today

| Layer | Component | Status |
|-------|-----------|--------|
| **UI Tab** | `_tab_integrations.html` | 4 cards (Git, GitHub, Docker, CI/CD) — status-only |
| **JS** | `_integrations.html` | 86 lines — reads `/api/status` to populate cards |
| **Backend** | _none dedicated_ | No `routes_integrations.py` — cards pull from `/api/status` |
| **Config** | `project.yml` | Has `repository`, `external.ci`, `content_folders`, `domains` |
| **CI/CD** | `.github/workflows/ci.yml` | Basic lint+type+test pipeline |
| **Content** | `routes_content*.py` + `content_release.py` | Full content vault: upload, encrypt, optimize, release to GitHub |
| **Adapters** | `src/adapters/` | Shell (command, filesystem), VCS (stub), containers (stub) |

### Key observations

1. **The Content Vault is mature** — upload, optimize, encrypt/decrypt, large-file release. Foundation for a `docs` Pages segment.
2. **Adapters layer exists but is thin** — shell adapter works, VCS/container are stubs. Git ops use direct `subprocess`.
3. **No GitHub API integration** — Everything uses the `gh` CLI. Fine for now.
4. **No build system** — No SSG runner, no build pipeline.
5. **`project.yml`** is the sole source of truth for project config.
6. **The control plane is general-purpose** — it runs on any project, any stack.

---

## 2. Feature Map

```
┌──────────────────────────────────────────────────────────────────────┐
│                        🔌 Integrations Tab                          │
├──────────┬──────────┬──────────────────┬──────────┬─────────────────┤
│   Git    │  GitHub  │  GitHub Pages    │  CI/CD   │  Docker / ...   │
│(actions) │ (PR,Act) │  (multi-segment) │ (runs)   │  (status)       │
├──────────┴──────────┴────────┬─────────┴──────────┴─────────────────┤
│                              │                                      │
│   Integration Cards          │   Pages Builder                      │
│   (status + actions)         │   (segments, pipeline, deploy)       │
│                              │                                      │
├──────────────────────────────┴──────────────────────────────────────┤
│                                                                      │
│   Pages Engine (builder-agnostic)                                    │
│   Source → [Transform?] → Build → Merge → Deploy                    │
│                                                                      │
│   Builders:  raw │ mkdocs │ hugo │ docusaurus │ sphinx │ custom     │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   Existing Infrastructure                                            │
│   Content Vault │ Vault/Secrets │ project.yml │ gh CLI │ Adapters   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Design Decisions (Resolved)

### D1. Builder Architecture — Builder-Agnostic

The control plane does NOT assume any specific SSG. The Pages engine is a **generic orchestrator** that works with pluggable builders.

Each builder is a simple contract:

```python
class PageBuilder:
    name: str                    # "mkdocs", "hugo", "docusaurus", etc.
    requires: list[str]          # ["python"], ["node"], ["hugo"], []
    
    def detect(self) -> bool:
        """Can this builder run? (are dependencies available?)"""
    
    def scaffold(self, segment, workspace):
        """Generate build config files in workspace."""
    
    def transform(self, source_dir, workspace):
        """Optional: transform source files (e.g., MD→MDX)."""
    
    def build(self, workspace) -> subprocess.Popen:
        """Run the build. Return process for streaming."""
    
    def preview(self, workspace) -> tuple[subprocess.Popen, int]:
        """Start dev server. Return (process, port)."""
    
    def output_dir(self, workspace) -> Path:
        """Where is the built output?"""
```

Built-in builders:

| Builder | Requires | Transform | Output |
|---------|----------|-----------|--------|
| `raw` | nothing | none — copies files directly | source dir |
| `mkdocs` | Python + mkdocs | none — uses MD natively | `site/` |
| `hugo` | hugo binary | none — uses MD natively | `public/` |
| `docusaurus` | Node.js + npm | MD → MDX (optional) | `build/` |
| `sphinx` | Python + sphinx | none — RST or MD | `_build/html/` |
| `custom` | user-defined | user-defined | user-defined |

The control plane detects available builders by checking `which hugo`, `which mkdocs`, `which npx`, etc.

### D2. Segment Architecture — Config in project.yml

```yaml
pages:
  base_url: /devops-control-plane      # GH Pages base path (auto-detected from repo)
  deploy_branch: gh-pages
  root_segment: null                   # null = auto hub page, "docs" = docs at /
  segments:
    - name: docs
      source: docs/
      builder: mkdocs                  # whatever builder the user picks
      path: /docs
      auto: true                       # pre-created when content_folders has 'docs'
      config: {}                       # builder-specific (passed to scaffold)
```

### D3. Build Execution — Local Preview + CI Deploy

- **Local**: For preview while authoring. The UI can start a dev server.
- **CI**: For production. A generated workflow file handles the build + deploy.
- **The control plane generates the CI workflow** based on segment config.

### D4. Build Streaming — SSE + Polling Fallback

Real-time build logs via Server-Sent Events. Polling endpoint as fallback.

### D5. Content Vault Integration — Automatic at Build Time

- Small files: copied directly. `.enc` files decrypted to build workspace only.
- Large files (`.large/`): auto-restored from GitHub Release if missing locally.
- Build workspace is gitignored — decrypted content never committed.

### D6. Landing Page — Auto Hub + Optional Root Override

Default: auto-generated landing at `/` with segment cards.
Override: set `root_segment` to put one segment at `/`.

### D7. Transform Pipeline — Builder-Specific, Optional

Transforms are NOT a global concern. They're part of each builder:
- `docusaurus` builder: has a MD→MDX transform step
- `mkdocs` builder: no transform needed (uses MD natively)
- `hugo` builder: no transform (or minimal frontmatter adaptation)
- `custom` builder: user can specify a pre-build command

When transforms exist, they're opt-in remark/rehype directives:
- `:::note` / `:::warning` / `:::tip` → admonition blocks
- `:::tabs` + `:::tab` → tabbed content
- `:::code-group` → multi-file code blocks

### D8. Preview — Local Dev Server from UI

- Start preview per segment (builder's dev server)
- One preview per segment, max 3 concurrent, auto-stop after 30min idle
- UI shows port + "Open" link

---

## 4. Architecture

### 4.1 Backend — New Files

```
src/ui/web/
├── routes_integrations.py      # Git/GitHub/CI integration endpoints  
├── pages_engine.py             # Pages orchestrator
│   ├── detect_builders()       # What's available on this system?
│   ├── scaffold_segment()      # Generate build workspace
│   ├── build_segment()         # Run build via builder
│   ├── merge_segments()        # Combine all outputs
│   ├── deploy_pages()          # Push to gh-pages
│   └── start_preview()         # Start dev server
├── pages_builders/             # Builder implementations
│   ├── __init__.py
│   ├── base.py                 # PageBuilder ABC
│   ├── raw.py                  # Static file copy (no build)
│   ├── mkdocs.py               # MkDocs builder
│   ├── hugo.py                 # Hugo builder
│   ├── docusaurus.py           # Docusaurus builder
│   ├── sphinx.py               # Sphinx builder
│   └── custom.py               # User-defined build command
├── routes_pages.py             # REST API for Pages builder
│   ├── GET  /api/pages/status
│   ├── GET  /api/pages/builders        # available builders
│   ├── GET  /api/pages/segments
│   ├── POST /api/pages/segments        # create
│   ├── PUT  /api/pages/segments/<name> # update
│   ├── DELETE /api/pages/segments/<name>
│   ├── POST /api/pages/build/<name>    # build one
│   ├── POST /api/pages/build-all       # build + merge
│   ├── GET  /api/pages/build-log/<name> # SSE stream
│   ├── POST /api/pages/preview/<name>  # start preview
│   ├── DELETE /api/pages/preview/<name> # stop preview
│   ├── POST /api/pages/deploy          # deploy
│   └── POST /api/pages/generate-ci     # generate workflow file
└── md_transforms.py            # Optional MD transform utils
    ├── convert_admonitions()   # :::note → builder-appropriate format
    ├── enrich_frontmatter()    # Add missing title/description
    └── rewrite_links()         # Fix cross-refs
```

### 4.2 Build Workspace

```
.pages/                          # Gitignored
├── <segment-name>/
│   ├── ... (builder-generated scaffold)
│   ├── content/                 # Source content (copied/symlinked)
│   └── build/                   # Builder output
└── _merged/                     # Combined output for deploy
    ├── <segment-path>/
    ├── <segment-path>/
    └── index.html               # Auto-generated hub (if no root_segment)
```

### 4.3 Git Integration Endpoints

```
routes_integrations.py:
├── GET  /api/git/status         # branch, dirty, staged, ahead/behind
├── GET  /api/git/log?n=10       # recent commits
├── POST /api/git/commit         # { message, files? }
├── POST /api/git/pull
├── POST /api/git/push
├── GET  /api/gh/pulls           # open PRs
├── GET  /api/gh/actions/runs    # workflow run history
├── POST /api/gh/actions/dispatch # trigger workflow
```

### 4.4 Frontend

```
templates/
├── partials/
│   └── _tab_integrations.html    # Redesigned layout
├── scripts/
│   ├── _integrations.html        # Loader (like _secrets.html)
│   ├── _integrations_git.html    # Git card
│   ├── _integrations_gh.html     # GitHub + CI cards
│   └── _integrations_pages.html  # Pages builder panel
```

---

## 5. Implementation Phases

### Phase 1: Git Integration (foundation)
**Goal**: Working Git card with real actions.

1. Create `routes_integrations.py` — Git status, log, commit, pull, push
2. Redesign `_tab_integrations.html` — new card layout
3. Build Git card JS — status display, commit form, push/pull buttons
4. Wire up GitHub card — PR count, latest Actions run
5. Wire up CI/CD card — run history, dispatch trigger

**Deliverable**: Fully functional Git/GitHub/CI cards with real data and actions.

### Phase 2: Pages Infrastructure
**Goal**: Builder-agnostic engine with segment CRUD.

6. Create `pages_builders/base.py` — the `PageBuilder` ABC
7. Implement `raw` builder (simplest — just copy files)
8. Create `pages_engine.py` — detect, scaffold, build, merge orchestrator
9. Add `pages:` schema to `project.yml` handling
10. Create `routes_pages.py` — REST API
11. Build Pages card UI — segment list, add/configure/delete

**Deliverable**: Can create segments, configure them, build with `raw` builder.

### Phase 3: Real Builders
**Goal**: At least 2 production-grade builders.

12. Implement `mkdocs` builder (most natural for Python projects)
13. Implement `hugo` builder (fastest SSG, single binary)
14. Implement `docusaurus` builder (for MDX-powered sites)
15. MD transform layer (admonitions, frontmatter enrichment)
16. Builder auto-detection and availability UI

**Deliverable**: Can build real static sites with MkDocs/Hugo/Docusaurus.

### Phase 4: Deploy & Preview
**Goal**: Full lifecycle — preview, build, deploy.

17. Implement SSE build log streaming
18. Implement merge logic (combine segment outputs)
19. Implement gh-pages deploy (force-push or GitHub Actions workflow generation)
20. Implement preview server management
21. Auto-generated hub landing page
22. Auto `docs` segment when project has `docs` domain

**Deliverable**: Complete Pages workflow from authoring to live deploy.

---

## 6. Principles

1. **No stack assumptions** — the control plane works on Python, Node, Go, Ruby, whatever
2. **Builder-agnostic** — the engine doesn't know or care what SSG you use
3. **Convention over configuration** — sensible defaults, override when needed
4. **CI is the deploy path** — local builds are for preview only
5. **Config in project.yml** — everything version-controlled, no hidden state
6. **Gitignore the workspace** — `.pages/` is ephemeral, only source files matter
7. **Graceful degradation** — no Node? No Docusaurus builder. No Python? No MkDocs. `raw` always works.
