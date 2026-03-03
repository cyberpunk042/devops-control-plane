# Pages Routes — Dashboard, Static Site Serving & Pages Pipeline API

> **3 files · 430 lines · 21 endpoints · 2 Blueprints: `pages_bp` + `pages_api_bp`**
>
> This is the only route package that exports **two blueprints**:
>
> 1. **`pages_bp`** (no prefix) — dashboard HTML rendering + built-site
>    static serving with SPA fallback
> 2. **`pages_api_bp`** (prefix `/api`) — the full Pages pipeline API:
>    segment CRUD, metadata, builders, build, merge, deploy, preview,
>    CI generation, and SSE streaming
>
> Eight sub-domains within the API blueprint:
>
> 1. **Segment CRUD** — list, add, update, remove segments (4 endpoints)
> 2. **Metadata** — get/set top-level pages config (2 endpoints)
> 3. **Builders** — list builders, list features, resolve file, install
>    (4 endpoints)
> 4. **Build** — build single, build all, build status, build stream
>    (4 endpoints)
> 5. **Merge + Deploy** — merge outputs, deploy to gh-pages (2 endpoints)
> 6. **Init** — auto-initialize from project.yml (1 endpoint)
> 7. **Preview** — start, stop, list preview servers (3 endpoints)
> 8. **CI** — generate GitHub Actions workflow (1 endpoint)
>
> Backed by `core/services/pages/engine.py` (470 lines) and the
> `pages_builders` package (3,259 lines across 8 builder modules).

---

## How It Works

### Request Flow

```
Browser
│
├── GET / ──────────────────────── Dashboard
│   └── pages_bp (no prefix)
│       └── render_template("dashboard.html")
│
├── GET /pages/site/<segment>/... ─ Built site serving
│   └── pages_bp (no prefix)
│       └── Flask send_file from .pages/<segment>/build/
│
└── /api/pages/* ──────────────── Pages API
    └── pages_api_bp (prefix /api)
        │
        ├── Segment CRUD
        │   ├── GET  /pages/segments
        │   ├── POST /pages/segments
        │   ├── PUT  /pages/segments/<name>
        │   └── DEL  /pages/segments/<name>
        │
        ├── Metadata
        │   ├── GET  /pages/meta
        │   └── POST /pages/meta
        │
        ├── Builders
        │   ├── GET  /pages/builders
        │   ├── GET  /pages/features
        │   ├── GET  /pages/resolve-file
        │   └── POST /pages/builders/<name>/install (SSE)
        │
        ├── Build
        │   ├── POST /pages/build/<name>
        │   ├── GET  /pages/build-status/<name>
        │   ├── POST /pages/build-all
        │   └── POST /pages/build-stream/<name> (SSE)
        │
        ├── Merge + Deploy
        │   ├── POST /pages/merge
        │   └── POST /pages/deploy (@requires_git_auth)
        │
        ├── Init
        │   └── POST /pages/init
        │
        ├── Preview
        │   ├── POST /pages/preview/<name>
        │   ├── DEL  /pages/preview/<name>
        │   └── GET  /pages/previews
        │
        └── CI
            └── POST /pages/ci
         │
         ▼
    core/services/pages/engine.py (470 lines)
    ├── Segment CRUD: get_segments, add_segment, update_segment, remove_segment
    ├── Metadata: get_pages_meta, set_pages_meta
    ├── Build: build_segment, get_build_status
    ├── Merge: merge_segments → _generate_hub_page
    ├── Deploy: deploy_to_ghpages (git worktree → gh-pages)
    ├── Init: init_pages_from_project
    ├── Preview: start_preview, stop_preview, list_previews
    ├── Builders: list_builders_detail, list_feature_categories, resolve_file_to_segments
    ├── Install: install_builder_stream, install_builder_events
    └── Build stream: build_segment_stream

    core/services/pages_builders/ (3,259 lines)
    ├── docusaurus.py — Docusaurus site builder
    ├── mkdocs.py — MkDocs documentation builder
    ├── sphinx.py — Sphinx documentation builder
    ├── raw.py — passthrough copy builder
    └── template_engine.py — shared template rendering
```

### Static Site Serving Pipeline

```
GET /pages/site/docs/getting-started
     │
     ▼
serve_pages_site(segment="docs", filepath="getting-started")
     │
     ├── build_dir = project_root / .pages / docs / build
     │   └── Not a directory? → 404 "No build output"
     │
     ├── Step 1: Direct file match
     │   └── .pages/docs/build/getting-started → is_file()? → send_file()
     │
     ├── Step 2: Directory → try index.html
     │   └── .pages/docs/build/getting-started/ → is_dir()?
     │       └── .pages/docs/build/getting-started/index.html → send_file()
     │
     └── Step 3: SPA fallback (Docusaurus client-side routing)
         └── .pages/docs/build/index.html → is_file()? → send_file()
         └── Nothing found → 404 "File not found"

MIME type detection: mimetypes.guess_type() → application/octet-stream fallback
```

### Segment CRUD Pipeline

```
GET /api/pages/segments?bust=1  (cached, key: "pages")
     │
     ▼
devops_cache.get_cached(root, "pages", _compute)
     │
     └── _compute():
         ├── _get_segments(root) → read project.yml → pages.segments[]
         ├── For each segment:
         │   ├── name, source, builder, path, auto, config
         │   └── get_build_status(root, s.name) → last build info
         └── Return: { segments: [...] }

POST /api/pages/segments
     Body: { name: "blog", source: "blog", builder: "docusaurus",
             path: "/blog", auto: false, config: {} }
     │
     ▼
SegmentConfig(name, source, builder, path, auto, config)
     │
     └── add_segment(root, seg)
         ├── Load project.yml
         ├── Name already exists? → ValueError → 409 Conflict
         ├── Append to pages.segments[]
         └── Save project.yml

PUT /api/pages/segments/<name>
     Body: { builder: "mkdocs", config: {...} }
     │
     ▼
update_segment(root, name, data)
     └── Find segment → update fields → save project.yml

DELETE /api/pages/segments/<name>
     │
     ▼
remove_segment(root, name)
     ├── Remove from project.yml
     └── Clean .pages/<name>/ workspace
```

### Build Pipeline

```
POST /api/pages/build/blog
     │
     ├── @run_tracked("build", "build:pages_segment")
     │
     ▼
build_segment(root, "blog")
     │
     ├── Load segment config from project.yml
     ├── Resolve builder (docusaurus, mkdocs, sphinx, raw)
     ├── Create workspace: .pages/blog/
     ├── Run builder pipeline:
     │   ├── Stage 1: Prepare (copy sources, install deps)
     │   ├── Stage 2: Build (run builder command)
     │   ├── Stage 3: Post-process (minify, optimize)
     │   └── Stage 4: Write build metadata
     ├── Record build status
     │
     └── Return BuildResult:
         { ok: true, segment: "blog", duration_ms: 5200,
           serve_url: "/pages/site/blog/" }

POST /api/pages/build-all
     │
     ├── @run_tracked("build", "build:pages_all")
     │
     ▼
For each segment in get_segments(root):
     └── build_segment(root, seg.name) → collect results
     │
     └── Return:
         { ok: (all passed), results: [{segment, ok, error, duration_ms}] }
```

### SSE Build Stream Pipeline

```
POST /api/pages/build-stream/blog?clean=true&wipe=false&no_minify=false
     │
     ▼
build_segment_stream(root, "blog", clean=True, wipe=False, no_minify=False)
     │
     ├── Generator yields stage-aware events:
     │   data: {"stage": "prepare", "status": "running", "message": "Installing deps..."}
     │   data: {"stage": "prepare", "status": "done", "duration_ms": 1200}
     │   data: {"stage": "build", "status": "running", "message": "Building..."}
     │   data: {"stage": "build", "log": "✓ Generated 42 pages", "progress": 0.8}
     │   data: {"stage": "build", "status": "done", "duration_ms": 4000}
     │   data: {"stage": "postprocess", "status": "running"}
     │   data: {"stage": "complete", "ok": true, "duration_ms": 5200}
     │
     └── Response: text/event-stream (SSE)
```

### Builder Install Pipeline (SSE)

```
POST /api/pages/builders/docusaurus/install
     │
     ▼
install_builder_stream("docusaurus")
     │
     ├── Already installed? → { ok: true, message: "Already installed" } (200)
     ├── Not found? → { error: "Builder not found" } (404)
     ├── No install command? → { error: "..." } (400)
     │
     └── Stream events:
         data: {"status": "installing", "message": "npm install..."}
         data: {"status": "progress", "percent": 50}
         data: {"status": "done", "ok": true}
         │
         └── Response: text/event-stream (SSE)
```

### Merge + Deploy Pipeline

```
POST /api/pages/merge
     │
     ├── @run_tracked("build", "build:pages_merge")
     │
     ▼
merge_segments(root)
     │
     ├── For each built segment:
     │   └── Copy .pages/<name>/build/ → .pages/_merged/<path>/
     │
     ├── _generate_hub_page(.pages/_merged/, segments)
     │   └── Auto-generate index.html linking to all segments
     │
     └── Return:
         { ok: true, merged_dir: ".pages/_merged", segments_merged: 3 }

POST /api/pages/deploy
     │
     ├── @requires_git_auth (needs git credentials for push)
     ├── @run_tracked("deploy", "deploy:pages")
     │
     ▼
deploy_to_ghpages(root)
     │
     ├── git worktree add .pages/_deploy gh-pages (or create branch)
     ├── Copy .pages/_merged/ → .pages/_deploy/
     ├── git add -A → git commit -m "Deploy Pages"
     ├── git push origin gh-pages --force
     ├── git worktree remove .pages/_deploy
     │
     └── Return:
         { ok: true, output: "Deployed to gh-pages" }
```

### Preview Server Pipeline

```
POST /api/pages/preview/blog
     │
     ▼
start_preview(root, "blog")
     │
     ├── Check segment exists
     ├── Start preview process (builder-specific dev server)
     └── Return: { ok: true, url: "http://localhost:3000" }

DELETE /api/pages/preview/blog
     │
     ▼
stop_preview("blog")
     └── Kill preview process

GET /api/pages/previews
     │
     ▼
list_previews()
     └── Return: { previews: [{name, url, pid}] }
```

---

## File Map

```
routes/pages/
├── __init__.py     13 lines — re-exports both blueprints
├── serving.py      73 lines — dashboard + static site serving (pages_bp)
├── api.py         344 lines — 19 API endpoints (pages_api_bp)
└── README.md               — this file
```

Core business logic:
- `pages/engine.py` (470 lines) — segment lifecycle, build, merge, deploy
- `pages_builders/` (3,259 lines) — Docusaurus, MkDocs, Sphinx, raw builders

---

## Per-File Documentation

### `__init__.py` — Blueprint Re-exports (13 lines)

```python
from .serving import pages_bp        # no prefix — serves / and /pages/site/
from .api import pages_api_bp        # prefix /api — all API endpoints
```

**Unique:** this is the only route package that exports two blueprints.

### `serving.py` — Dashboard + Static Serving (73 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `dashboard()` | GET | `/` | Render main dashboard HTML |
| `serve_pages_site()` | GET | `/pages/site/<segment>/[<path>]` | Serve built static sites |

**Three-tier file resolution for SPA support:**

```python
# 1. Direct file match
if requested.is_file():
    return send_file(requested, mimetype=mime)

# 2. Directory → try index.html
if requested.is_dir():
    index = requested / "index.html"
    if index.is_file():
        return send_file(index, mimetype="text/html")

# 3. SPA fallback → root index.html (Docusaurus client-side routing)
root_index = build_dir / "index.html"
if root_index.is_file():
    return send_file(root_index, mimetype="text/html")
```

### `api.py` — Pages Pipeline API (344 lines)

This file directly imports 17 functions from `pages/engine.py`:

```python
from src.core.services.pages.engine import (
    get_segments, add_segment, update_segment, remove_segment,
    get_pages_meta, set_pages_meta,
    build_segment, get_build_status,
    merge_segments, deploy_to_ghpages,
    start_preview, stop_preview, list_previews,
    generate_ci_workflow,
    list_builders_detail, list_feature_categories,
    resolve_file_to_segments,
    init_pages_from_project,
    install_builder_stream, install_builder_events,
    build_segment_stream,
)
```

#### Segment CRUD

| Function | Method | Route | Cached | What It Does |
|----------|--------|-------|--------|-------------|
| `list_segments()` | GET | `/pages/segments` | ✅ `"pages"` | List all segments + build status |
| `create_segment()` | POST | `/pages/segments` | No | Add new segment |
| `update_segment_route()` | PUT | `/pages/segments/<name>` | No | Update segment config |
| `delete_segment_route()` | DELETE | `/pages/segments/<name>` | No | Remove segment + cleanup |

#### Metadata

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `get_meta()` | GET | `/pages/meta` | Get pages config (base_url, deploy_branch) |
| `set_meta()` | POST | `/pages/meta` | Update pages config |

#### Builders

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `list_builders_route()` | GET | `/pages/builders` | Available builders with pipeline info |
| `list_features_route()` | GET | `/pages/features` | Builder feature categories |
| `resolve_file_to_pages()` | GET | `/pages/resolve-file` | Map vault file → segment URLs |
| `install_builder_route()` | POST | `/pages/builders/<name>/install` | Install builder deps (SSE) |

**Install builder has dual-mode response:**

```python
preflight = install_builder_stream(name)
if preflight is not None:
    # Synchronous response (already installed, not found, etc.)
    return jsonify(preflight), status

# Async SSE stream for actual installation
def sse():
    for event in install_builder_events(name):
        yield f"data: {json.dumps(event)}\n\n"
return Response(sse(), mimetype="text/event-stream")
```

#### Build

| Function | Method | Route | Tracked | What It Does |
|----------|--------|-------|---------|-------------|
| `build_segment_route()` | POST | `/pages/build/<name>` | ✅ `build:pages_segment` | Build one segment |
| `build_status_route()` | GET | `/pages/build-status/<name>` | No | Last build metadata |
| `build_all_route()` | POST | `/pages/build-all` | ✅ `build:pages_all` | Build all segments |
| `build_stream_route()` | POST | `/pages/build-stream/<name>` | No | Build with SSE streaming |

**Build-all iterates segments sequentially:**

```python
segments = _get_segments(root)
results = []
for seg in segments:
    r = build_segment(root, seg.name)
    results.append({...})
return jsonify({"ok": all(r["ok"] for r in results), "results": results})
```

**Build stream accepts query params for build options:**

```python
clean = request.args.get("clean", "").lower() in ("true", "1", "yes")
wipe = request.args.get("wipe", "").lower() in ("true", "1", "yes")
no_minify = request.args.get("no_minify", "").lower() in ("true", "1", "yes")
```

#### Merge + Deploy

| Function | Method | Route | Auth | Tracked | What It Does |
|----------|--------|-------|------|---------|-------------|
| `merge_route()` | POST | `/pages/merge` | No | ✅ `build:pages_merge` | Merge all built outputs |
| `deploy_route()` | POST | `/pages/deploy` | ✅ | ✅ `deploy:pages` | Deploy to gh-pages |

**Deploy is the only Pages endpoint requiring auth** — it pushes
to a remote git branch, so it needs valid git credentials.

#### Init, Preview, CI

| Function | Method | Route | Tracked | What It Does |
|----------|--------|-------|---------|-------------|
| `init_pages()` | POST | `/pages/init` | ✅ `setup:pages` | Auto-init from project.yml |
| `start_preview_route()` | POST | `/pages/preview/<name>` | No | Start dev server |
| `stop_preview_route()` | DELETE | `/pages/preview/<name>` | No | Stop dev server |
| `list_previews_route()` | GET | `/pages/previews` | No | List running previews |
| `generate_ci_route()` | POST | `/pages/ci` | ✅ `generate:pages_ci` | Generate GH Actions workflow |

---

## Dependency Graph

```
__init__.py
├── serving.pages_bp
└── api.pages_api_bp

serving.py
├── mimetypes     ← MIME detection (stdlib)
├── flask         ← send_file, render_template, abort
└── No core service imports

api.py
├── pages.engine      ← 17 functions (eager)
├── pages_builders    ← SegmentConfig dataclass (eager)
├── run_tracker       ← @run_tracked (eager)
├── helpers           ← project_root, requires_git_auth (eager)
├── devops.cache      ← get_cached (lazy, inside handler)
└── json, logging     ← SSE serialization
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | `pages_bp` (no prefix), `pages_api_bp` (prefix `/api`) |
| Pages panel | `scripts/integrations/_pages.html` | `/pages/segments`, `/pages/build/*`, `/pages/merge`, `/pages/deploy` |
| Pages config | `scripts/integrations/_pages_config.html` | `/pages/meta`, `/pages/builders`, `/pages/features`, `/pages/segments` |
| Pages SSE | `scripts/integrations/_pages_sse.html` | `/pages/build-stream/*`, `/pages/builders/*/install` |
| Content browser | `scripts/content/_browser.html` | `/pages/resolve-file` |
| Content preview | `scripts/content/_preview.html` | `/pages/site/*` (static serving) |
| Setup wizard | `scripts/wizard/_integrations.html` | `/pages/init`, `/pages/segments` |

---

## Data Shapes

### `GET /api/pages/segments` response

```json
{
    "segments": [
        {
            "name": "docs",
            "source": "docs",
            "builder": "docusaurus",
            "path": "/docs",
            "auto": true,
            "config": { "sidebar": true, "theme": "classic" },
            "build_status": {
                "built_at": "2026-03-02T15:30:00",
                "duration_ms": 5200,
                "ok": true
            }
        },
        {
            "name": "blog",
            "source": "blog",
            "builder": "mkdocs",
            "path": "/blog",
            "auto": false,
            "config": {},
            "build_status": null
        }
    ]
}
```

### `POST /api/pages/segments` request + response

```json
// Request:
{ "name": "api-docs", "source": "api-docs", "builder": "sphinx",
  "path": "/api-docs", "auto": false, "config": {} }

// Response:
{ "ok": true, "segment": "api-docs" }

// Error (duplicate):
{ "error": "Segment 'api-docs' already exists" }  // 409
```

### `GET /api/pages/meta` response

```json
{
    "base_url": "/",
    "deploy_branch": "gh-pages",
    "custom_domain": ""
}
```

### `GET /api/pages/builders` response

```json
{
    "builders": [
        {
            "name": "docusaurus",
            "label": "Docusaurus",
            "description": "React-based static site generator",
            "installed": true,
            "stages": ["prepare", "build", "optimize"]
        },
        {
            "name": "mkdocs",
            "label": "MkDocs",
            "description": "Python documentation builder",
            "installed": false,
            "stages": ["prepare", "build"]
        }
    ]
}
```

### `GET /api/pages/features` response

```json
{
    "categories": [
        {
            "name": "content",
            "features": ["sidebar", "search", "versioning"]
        },
        {
            "name": "theme",
            "features": ["dark_mode", "custom_css", "logo"]
        }
    ]
}
```

### `GET /api/pages/resolve-file?path=docs/guide.md` response

```json
{
    "matches": [
        {
            "segment": "docs",
            "preview_url": "/pages/site/docs/guide",
            "builder": "docusaurus"
        }
    ]
}
```

### `POST /api/pages/build/docs` response

```json
{
    "ok": true,
    "segment": "docs",
    "duration_ms": 5200,
    "error": null,
    "serve_url": "/pages/site/docs/"
}
```

### `GET /api/pages/build-status/docs` response

```json
{
    "built": true,
    "built_at": "2026-03-02T15:30:00",
    "duration_ms": 5200,
    "ok": true
}
```

### `POST /api/pages/build-all` response

```json
{
    "ok": true,
    "results": [
        { "segment": "docs", "ok": true, "error": null, "duration_ms": 5200 },
        { "segment": "blog", "ok": true, "error": null, "duration_ms": 3100 }
    ]
}
```

### `POST /api/pages/merge` response

```json
{
    "ok": true,
    "merged_dir": ".pages/_merged",
    "segments_merged": 2
}
```

### `POST /api/pages/deploy` response

```json
{
    "ok": true,
    "output": "Deployed to gh-pages"
}
```

### `POST /api/pages/init` response

```json
{
    "ok": true,
    "segments_created": ["docs", "blog"],
    "message": "Initialized 2 segments from project.yml"
}
```

### `GET /api/pages/previews` response

```json
{
    "previews": [
        { "name": "docs", "url": "http://localhost:3000", "pid": 12345 }
    ]
}
```

### `POST /api/pages/ci` response

```json
{
    "ok": true,
    "path": ".github/workflows/pages.yml",
    "message": "Generated Pages deployment workflow"
}
```

---

## Advanced Feature Showcase

### 1. Three-Tier SPA Fallback

The static site server handles Docusaurus-style client-side
routing by trying three resolution strategies:

1. **Direct file** → `/pages/site/docs/api.css` → serve the CSS
2. **Directory index** → `/pages/site/docs/guide/` → serve `guide/index.html`
3. **SPA root** → `/pages/site/docs/nonexistent` → serve root `index.html`

This means deep links work without server-side route config.

### 2. Dual-Mode Builder Install

The install endpoint dynamically switches between synchronous JSON
and SSE streaming based on whether installation is needed:

```python
preflight = install_builder_stream(name)
if preflight is not None:
    return jsonify(preflight), status  # already done → instant response
# Need to install → switch to SSE
return Response(sse(), mimetype="text/event-stream")
```

### 3. Pipeline-Aware Build Streaming

The SSE build stream emits stage-aware events so the frontend can
show a multi-step progress indicator:

```
prepare → build → postprocess → complete
```

Each stage has `running`/`done` lifecycle events with timing.

### 4. Hub Page Auto-Generation

When merging segments, the engine auto-generates a landing page
that links to all segment paths:

```python
_generate_hub_page(merged_dir, segments)
# Creates index.html with links to /docs/, /blog/, /api-docs/
```

### 5. Git Worktree Deploy Strategy

Deployment uses `git worktree` to create a temporary checkout of
the `gh-pages` branch, copies the merged output, commits, and
force-pushes — without affecting the main working tree.

### 6. Build Result with Serve URL

On successful build, the response includes a `serve_url` that
points to the integrated static serving endpoint:

```python
if result.ok and result.output_dir:
    resp["serve_url"] = f"/pages/site/{name}/"
```

---

## Design Decisions

### Why two blueprints instead of one

The dashboard (`GET /`) needs no URL prefix — it's the root page.
The API endpoints need `/api` prefix. Flask blueprints can only
have one prefix, so two blueprints are required.

### Why static serving uses Flask instead of nginx

The control plane is a development tool, not a production server.
Using Flask's `send_file` keeps the architecture simple — no
nginx config, no reverse proxy, no separate process. The built
sites are served at stable URLs that survive restarts.

### Why deploy requires git auth but build does not

Building is a local operation — it runs builder commands and writes
to `.pages/`. Deploying pushes to a remote git branch, which
requires SSH or HTTPS credentials. The `@requires_git_auth`
decorator ensures credentials are available before attempting push.

### Why build-all runs sequentially

Builders may compete for resources (npm installs, disk I/O).
Sequential builds prevent conflicts and make error attribution
clear. Each result includes its own timing for parallel analysis.

### Why segment list includes build status

The cached `/pages/segments` response embeds `build_status` for
each segment. This prevents the frontend from making N+1 requests
to `/pages/build-status/<name>` for each segment.

---

## Coverage Summary

| Capability | Endpoint | Method | Auth | Tracked | Cached |
|-----------|----------|--------|------|---------|--------|
| Dashboard | `/` | GET | No | No | No |
| Serve built site | `/pages/site/<seg>/[path]` | GET | No | No | No |
| List segments | `/pages/segments` | GET | No | No | ✅ `"pages"` |
| Add segment | `/pages/segments` | POST | No | No | No |
| Update segment | `/pages/segments/<name>` | PUT | No | No | No |
| Remove segment | `/pages/segments/<name>` | DELETE | No | No | No |
| Get metadata | `/pages/meta` | GET | No | No | No |
| Set metadata | `/pages/meta` | POST | No | No | No |
| List builders | `/pages/builders` | GET | No | No | No |
| List features | `/pages/features` | GET | No | No | No |
| Resolve file | `/pages/resolve-file` | GET | No | No | No |
| Install builder | `/pages/builders/<n>/install` | POST | No | No | No |
| Build segment | `/pages/build/<name>` | POST | No | ✅ `build:pages_segment` | No |
| Build status | `/pages/build-status/<name>` | GET | No | No | No |
| Build all | `/pages/build-all` | POST | No | ✅ `build:pages_all` | No |
| Build stream | `/pages/build-stream/<name>` | POST | No | No | No |
| Merge | `/pages/merge` | POST | No | ✅ `build:pages_merge` | No |
| Deploy | `/pages/deploy` | POST | ✅ | ✅ `deploy:pages` | No |
| Init pages | `/pages/init` | POST | No | ✅ `setup:pages` | No |
| Start preview | `/pages/preview/<name>` | POST | No | No | No |
| Stop preview | `/pages/preview/<name>` | DELETE | No | No | No |
| List previews | `/pages/previews` | GET | No | No | No |
| Generate CI | `/pages/ci` | POST | No | ✅ `generate:pages_ci` | No |
