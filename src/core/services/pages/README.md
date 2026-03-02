# Pages Domain

> **7 files · 1,414 lines · Multi-segment documentation builder with pluggable pipelines.**
>
> Manages the full Pages lifecycle: segment CRUD → builder detection →
> scaffolding → build pipeline → merge → preview → deploy to gh-pages.
> Plus CI workflow generation and SSE-streaming install/build.

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────────┐
│  CONFIGURE — Define segments in project.yml                          │
│     add_segment(root, config)    → register new segment              │
│     update_segment(root, name)   → modify config                     │
│     remove_segment(root, name)   → delete + clean workspace          │
│     get_segments(root)           → list all segments                 │
│     set_pages_meta(root, meta)   → base_url, deploy_branch           │
├─────────────────────────────────────────────────────────────────────┤
│  DISCOVER — Auto-detection                                           │
│     init_pages_from_project(root) → auto-create from content_folders │
│     detect_best_builder(folder)   → pick best available builder      │
│     list_builders_detail()        → all builders with schemas         │
│     list_feature_categories()     → builder features by category      │
│     resolve_file_to_segments(root, path) → file→segment mapping       │
├─────────────────────────────────────────────────────────────────────┤
│  BUILD — Execute pipeline                                            │
│     build_segment(root, name)    → sync build with duration           │
│     build_segment_stream(root, name) → SSE streaming pipeline         │
│     get_build_status(root, name) → last build metadata               │
├─────────────────────────────────────────────────────────────────────┤
│  MERGE & DEPLOY                                                      │
│     merge_segments(root)         → combine outputs into _merged/      │
│     deploy_to_ghpages(root)      → force-push to gh-pages branch     │
├─────────────────────────────────────────────────────────────────────┤
│  PREVIEW                                                             │
│     start_preview(root, name)    → launch dev server                  │
│     stop_preview(name)           → terminate process                  │
│     list_previews()              → running preview servers            │
├─────────────────────────────────────────────────────────────────────┤
│  INSTALL                                                             │
│     install_builder_stream(name) → pre-flight check                   │
│     install_builder_events(name) → SSE streaming installation         │
├─────────────────────────────────────────────────────────────────────┤
│  CI                                                                  │
│     generate_ci_workflow(root)   → deploy-pages.yml for GitHub Actions│
└─────────────────────────────────────────────────────────────────────┘
```

### Segment Model

A segment maps a content source folder to a builder and an output path:

```yaml
# project.yml
pages:
  base_url: "https://example.github.io/repo"
  deploy_branch: "gh-pages"
  segments:
    - name: docs
      source: docs
      builder: mkdocs
      path: /docs
      auto: true
    - name: api-ref
      source: api
      builder: docusaurus
      path: /api
```

### Builder Pipeline

Each builder executes a multi-stage pipeline:

```
Segment source → Scaffold → Validate → Build → Post-process → Output
                    │           │         │          │           │
                    │           │         │          │      .pages/<name>/build/
                    │           │         │          │
                    │           │         │       Minify (optional)
                    │           │         │
                    │           │      Builder-specific compile
                    │           │      (mkdocs build / docusaurus build / hugo / cp)
                    │           │
                    │        Source validation (files exist, config valid)
                    │
                 Generate config files
                 (mkdocs.yml / docusaurus.config.ts / etc.)
```

### Supported Builders

| Builder | Requires | Install Method | Detect |
|---------|----------|---------------|--------|
| `raw` | (none) | (built-in) | Always available |
| `mkdocs` | `pip install mkdocs` | `_pip_install()` | `which mkdocs` |
| `hugo` | Hugo binary | `_hugo_binary_install()` | `which hugo` |
| `docusaurus` | Node.js + npm | `_npm_install()` | `which npx` |

### Workspace Layout

```
.pages/
├── docs/               ← segment workspace
│   ├── mkdocs.yml      ← scaffolded config
│   ├── docs/           ← linked/copied source
│   ├── build/          ← build output
│   └── build.json      ← build metadata
├── api-ref/
│   ├── docusaurus.config.ts
│   ├── docs/
│   ├── build/
│   └── build.json
└── _merged/            ← combined output for deploy
    ├── docs/
    ├── api/
    └── index.html      ← auto-generated hub page
```

---

## Key Data Shapes

### SegmentConfig model

```python
SegmentConfig(
    name="docs",
    source="docs",
    builder="mkdocs",
    path="/docs",
    auto=True,
    config={"clean": False, "build_mode": "default"},
)
```

### build_segment response

```python
{
    "ok": True,
    "output_dir": ".pages/docs/build",
    "log": "...",
    "duration_ms": 3500,
}
```

### build_segment_stream events (SSE)

```python
# Pipeline start
{"type": "pipeline_start", "segment": "docs", "builder": "mkdocs",
 "stages": [{"name": "scaffold", "label": "Scaffold"}, ...]}

# Stage lifecycle
{"type": "stage_start", "stage": "scaffold", "label": "Scaffold"}
{"type": "log", "line": "Generating mkdocs.yml...", "stage": "scaffold"}
{"type": "stage_done", "stage": "scaffold", "label": "Scaffold", "duration_ms": 120}

# Or error
{"type": "stage_error", "stage": "build", "label": "Build",
 "error": "mkdocs build failed", "duration_ms": 500}

# Pipeline end
{"type": "pipeline_done", "ok": True, "segment": "docs",
 "total_ms": 3500, "serve_url": "/pages/site/docs/",
 "stages": [...], "duration_ms": 3500}
```

### merge_segments response

```python
{
    "ok": True,
    "merged_dir": ".pages/_merged",
    "segments_merged": ["docs", "api-ref"],   # list of names, not int
    "errors": [],
}
```

### deploy_to_ghpages response

```python
{"ok": True, "output": "Pushing to gh-pages..."}
```

### list_builders_detail response

```python
[
    {
        "name": "mkdocs",
        "label": "MkDocs",
        "description": "Python documentation generator",
        "available": True,
        "requires": "mkdocs",
        "install_hint": "pip install mkdocs mkdocs-material",
        "installable": True,
        "stages": [
            {"name": "scaffold", "label": "Scaffold"},
            {"name": "validate", "label": "Validate"},
            {"name": "build", "label": "Build"},
        ],
        "config_fields": [
            {"key": "theme", "label": "Theme", "type": "select",
             "default": "material", "options": ["material", "readthedocs"]},
        ],
    },
]
```

### resolve_file_to_segments response

```python
[
    {
        "segment": "docs",
        "builder": "mkdocs",
        "preview_url": "/pages/site/docs/getting-started",
        "built": True,
    },
]
```

### install_builder_stream events (SSE)

```python
# Log lines
{"type": "log", "line": "Installing MkDocs..."}
{"type": "log", "line": "▶ pip install mkdocs mkdocs-material"}
{"type": "log", "line": "Collecting mkdocs..."}

# Done
{"type": "done", "ok": True, "message": "MkDocs installed in venv"}
# Or
{"type": "done", "ok": False, "error": "pip install failed (exit 1)"}
```

### start_preview response

```python
{"ok": True, "port": 8080}
# or
{"ok": True, "port": 8080, "already_running": True}
```

---

## Architecture

```
              Routes / CLI
                  │
         ┌────────▼────────┐
         │  __init__.py     │  Public API re-exports
         └──┬──┬──┬──┬──┬─┘
            │  │  │  │  │
     ┌──────┘  │  │  │  └─────────────┐
     ▼         │  ▼  └────┐           ▼
  engine.py    │  ci.py    │      preview.py
  (segment     │  (GHA     │      (dev server
   CRUD,       │  workflow  │       start/stop,
   build,      │  gen)      │       in-memory
   merge,      │            │       tracking)
   deploy,     │            │
   gitignore)  │            │
     │         │            │
     │    discovery.py   install.py
     │    (builder list,  (SSE streaming
     │     feature list,   install:
     │     auto-init,      pip/npm/
     │     file→segment)   hugo binary)
     │         │            │
     │    build_stream.py   │
     │    (SSE streaming    │
     │     build pipeline)  │
     │         │            │
     └────┬────┘            │
          ▼                 │
    pages_builders/    ◄────┘
    (pluggable builder
     implementations)
```

### Dependency Rules

| Rule | Detail |
|------|--------|
| `engine.py` is the core | Segment CRUD + build + merge + deploy |
| `discovery.py` imports `engine.py` | Uses `get_segments`, `add_segment` |
| `build_stream.py` imports `engine.py` | Uses `get_segment`, `ensure_gitignore` |
| `install.py` imports `pages_builders` | Uses `get_builder` for install commands |
| `ci.py` imports `engine.py` + `pages_builders` | Reads segments + builder info |
| `preview.py` imports `engine.py` + `pages_builders` | Uses `get_segment` + builder |
| All modules delegate to `pages_builders/` | Pluggable builder implementations |

---

## File Map

```
pages/
├── __init__.py       Public API re-exports (14 lines)
├── engine.py         Segment CRUD, build, merge, deploy (471 lines)
├── discovery.py      Builder listing, auto-init, file→segment (268 lines)
├── build_stream.py   SSE streaming build pipeline (163 lines)
├── ci.py             GitHub Actions workflow generation (167 lines)
├── install.py        SSE streaming builder installation (217 lines)
├── preview.py        Dev server process management (114 lines)
└── README.md         This file
```

---

## Per-File Documentation

### `engine.py` — Core Engine (471 lines)

| Function | What It Does |
|----------|-------------|
| `get_segments(root)` | Load all segments from `project.yml` |
| `get_segment(root, name)` | Get single segment by name |
| `add_segment(root, config)` | Add segment to `project.yml` |
| `update_segment(root, name, updates)` | Update segment config |
| `remove_segment(root, name)` | Remove segment + clean workspace |
| `get_pages_meta(root)` | Get top-level pages metadata |
| `set_pages_meta(root, meta)` | Update pages metadata |
| `build_segment(root, name)` | Synchronous build (returns result) |
| `get_build_status(root, name)` | Read `build.json` for last build |
| `merge_segments(root)` | Combine all outputs into `_merged/` |
| `deploy_to_ghpages(root)` | Force-push `_merged/` to gh-pages |
| `ensure_gitignore(root)` | Add `.pages/` to `.gitignore` |

### `discovery.py` — Builder Listing & Auto-Init (268 lines)

| Function | What It Does |
|----------|-------------|
| `list_builders_detail()` | All builders with stages + config schemas |
| `list_feature_categories()` | Builder features grouped by category |
| `resolve_file_to_segments(root, path)` | File → matching segments + preview URLs |
| `detect_best_builder(folder)` | Pick best builder for a content folder |
| `init_pages_from_project(root)` | Auto-create segments from `content_folders` in `project.yml` |

**Builder detection priority:** Docusaurus > MkDocs > raw (based on availability).

### `build_stream.py` — SSE Build Pipeline (163 lines)

| Function | What It Does |
|----------|-------------|
| `build_segment_stream(root, name, clean, wipe, no_minify)` | Generator yielding SSE events per pipeline stage |

**Build options:**
- `clean=True` → pass `clean: true` to builder config
- `wipe=True` → nuke entire workspace before building
- `no_minify=True` → set `build_mode: no-minify`

### `ci.py` — CI Workflow Generation (167 lines)

| Function | What It Does |
|----------|-------------|
| `generate_ci_workflow(root)` | Generate `.github/workflows/deploy-pages.yml` |

**Auto-detected setup steps:**

| Builder | Setup Action |
|---------|-------------|
| `mkdocs` | `actions/setup-python@v5` (3.12) |
| `docusaurus` | `actions/setup-node@v4` (20) |
| `hugo` | `peaceiris/actions-hugo@v3` |

### `install.py` — Builder Installation (217 lines)

| Function | What It Does |
|----------|-------------|
| `install_builder_stream(name)` | Pre-flight check (already installed? no install cmd?) |
| `install_builder_events(name)` | Generator yielding SSE events for installation |

**Install methods:**

| Method | Builders | How |
|--------|----------|-----|
| `_pip_install()` | mkdocs | `pip install mkdocs mkdocs-material` in venv |
| `_hugo_binary_install()` | hugo | Download latest release binary for linux/amd64 or arm64 |
| `_npm_install()` | docusaurus | `npm install` |

### `preview.py` — Dev Server Management (114 lines)

| Function | What It Does |
|----------|-------------|
| `start_preview(root, name)` | Start builder's dev server subprocess |
| `stop_preview(name)` | Terminate preview process (graceful → kill) |
| `list_previews()` | List running preview servers |
| `_cleanup_dead_previews()` | Remove entries for dead processes |

**Constraints:**
- Max concurrent previews: 3
- In-memory tracking (lost on server restart)
- Graceful shutdown: SIGTERM → wait 5s → SIGKILL

---

## Advanced Feature Showcase

### 1. Pipeline Stage Streaming — Generator-Based SSE Architecture

The build pipeline yields structured events per stage, including skipping
remaining stages on error:

```python
# build_stream.py — build_segment_stream (lines 88-132)

for si in stages_info:
    yield {"type": "stage_start", "stage": si.name, "label": si.label}

    try:
        for line in builder.run_stage(si.name, segment, workspace):
            yield {"type": "log", "line": line, "stage": si.name}
        status = "done"
    except RuntimeError as e:
        error = str(e)
        status = "error"
        all_ok = False

    if status == "done":
        yield {"type": "stage_done", "stage": si.name, ...}
    else:
        yield {"type": "stage_error", "stage": si.name, "error": error, ...}
        # Skip all remaining stages
        remaining = stages_info[stages_info.index(si) + 1:]
        for rem in remaining:
            stage_results.append({
                "name": rem.name, "status": "skipped", ...
            })
        break
```

Key: each builder's `run_stage()` is itself a generator yielding log lines.
The build_stream wraps those into SSE events, adds timing, and handles the
error-skip cascade. Callers get a flat event stream regardless of how many
stages the builder defines.

### 2. Hugo Binary Auto-Install — Platform-Aware Download Pipeline

Hugo installation downloads the binary directly from GitHub Releases:

```python
# install.py — _hugo_binary_install (lines 86-170)

machine = platform.machine().lower()
arch = "amd64" if machine in ("x86_64", "amd64") else "arm64"

# Fetch latest release metadata from GitHub API
req = urllib.request.Request(
    "https://api.github.com/repos/gohugoio/hugo/releases/latest", ...)
release = json.loads(resp.read().decode())
version = release["tag_name"].lstrip("v")

# Try standard first, then extended
candidates = [
    f"hugo_{version}_linux-{arch}.tar.gz",
    f"hugo_extended_{version}_linux-{arch}.tar.gz",
]
# Download → extract 'hugo' binary → chmod 755 → verify with `hugo version`
```

Unlike pip/npm installs, Hugo is a standalone binary. The installer handles
architecture detection (amd64/arm64), downloads the correct tarball,
extracts only the `hugo` binary, places it in `~/.local/bin`, updates
`$PATH` at runtime, and verifies the binary actually runs.

### 3. Builder Detection Cascade — Priority-Based Auto-Selection

Content folder analysis follows a strict builder priority:

```python
# discovery.py — detect_best_builder (lines 176-213)

def detect_best_builder(folder):
    has_markdown = False
    for ext in ("*.md", "*.mdx"):
        if list(folder.glob(ext)) or list(folder.glob(f"*/{ext}")):
            has_markdown = True
            break

    if has_markdown:
        # Priority: Docusaurus > MkDocs > raw
        docusaurus = get_builder("docusaurus")
        if docusaurus and docusaurus.detect():
            return "docusaurus", "Markdown files detected, Node.js available", ""

        mkdocs = get_builder("mkdocs")
        if mkdocs and mkdocs.detect():
            return "mkdocs", "Markdown files detected, MkDocs available",
                   "Install Node.js for Docusaurus (better UX)"

    return "raw", "Static files (no markdown detected)", ""
```

Returns a 3-tuple `(builder_name, reason, suggestion)` — the suggestion
field recommends installing a better builder when available. This powers
the wizard's builder recommendation UI.

### 4. Hub Page Auto-Generation — Styled Landing for Multi-Segment Sites

When merging segments without a root segment, an `index.html` is
auto-generated with a dark-theme card grid:

```python
# engine.py — _generate_hub_page (lines 315-359)

def _generate_hub_page(merged_dir, segments):
    cards_html = ""
    for seg in segments:
        path = seg.path.strip("/") or seg.name
        cards_html += f"""
        <a href="./{path}/" class="card">
            <h2>{seg.name.title()}</h2>
            <p>{seg.config.get('title', seg.name)} &rarr;</p>
        </a>"""

    # Full HTML with dark theme, CSS grid, hover animations
    html = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
        <style>
            body {{ background: #0f1117; color: #e0e0e0; ... }}
            .card:hover {{ border-color: #6366f1;
                          transform: translateY(-2px); ... }}
        </style>
    </head>
    <body>
        <h1>📄 Documentation Hub</h1>
        <div class="grid">{cards_html}</div>
    </body></html>"""
```

The hub page is fully self-contained (inline CSS, no dependencies) and
styled with the same dark indigo theme used by the admin panel. Users
can override it by configuring a "root" segment.

### 5. Graceful Preview Lifecycle — SIGTERM → Wait → SIGKILL

Preview server shutdown follows a graceful termination pattern:

```python
# preview.py — stop_preview (lines 74-92)

def stop_preview(name):
    info = _preview_servers.pop(name)
    proc = info["proc"]
    if proc.poll() is None:           # Still running?
        proc.terminate()               # SIGTERM first
        try:
            proc.wait(timeout=5)       # Wait up to 5 seconds
        except subprocess.TimeoutExpired:
            proc.kill()                # SIGKILL if stuck
    return {"ok": True}

# Enforced concurrency: max 3 simultaneous previews
_MAX_PREVIEWS = 3
```

Combined with `_cleanup_dead_previews()` which polls all tracked
processes, stale entries are automatically removed. The max-3 limit
prevents resource exhaustion during development.

### 6. File-to-Segment URL Resolution — Content Path to Preview URL

Maps file paths to segment preview URLs with smart slug generation:

```python
# discovery.py — resolve_file_to_segments (lines 112-170)

def resolve_file_to_segments(project_root, file_path):
    for seg in get_segments(project_root):
        source = seg.source.rstrip("/")
        if not file_path.startswith(source + "/"):
            continue

        rel_path = file_path[len(source) + 1:]

        # Strip .md / .mdx for URL
        for ext in [".mdx", ".md"]:
            if doc_slug.endswith(ext):
                doc_slug = doc_slug[:-len(ext)]
                break

        # Handle index pages → / instead of /index
        if doc_slug == "index":
            doc_slug = ""
        elif doc_slug.endswith("/index"):
            doc_slug = doc_slug[:-6]

        preview_url = f"/pages/site/{seg.name}/{doc_slug}"
```

This powers the "Preview" button in the content panel — clicking a
markdown file opens the corresponding built page in the preview server.
The `.mdx` → `.md` priority ensures MDX files get correct URLs.

### 7. CI Workflow Template Composition — Per-Builder Setup Steps

The CI generator assembles GitHub Actions setup steps dynamically
based on which builders the segments use:

```python
# ci.py — generate_ci_workflow (lines 78-103)

needs_node = "docusaurus" in builders_used
needs_python = "mkdocs" in builders_used
needs_hugo = "hugo" in builders_used

setup_steps = ""
if needs_python:
    setup_steps += """
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
"""
if needs_node:
    setup_steps += """
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
"""
if needs_hugo:
    setup_steps += """
      - name: Set up Hugo
        uses: peaceiris/actions-hugo@v3
"""
```

A project mixing MkDocs and Docusaurus segments gets both Python and
Node.js setup steps. The workflow template also builds each segment
with builder-specific commands and merges outputs to `_merged/`.

---

### Feature Coverage Summary

| Feature | Where | Complexity |
|---------|-------|-----------|
| Generator-based stage streaming with error cascade | `build_stream.py` | Per-stage yield + skip-remaining on error |
| Platform-aware Hugo binary download | `install.py` `_hugo_binary_install` | GitHub API → tarball → extract → verify |
| Priority-based builder auto-detection | `discovery.py` `detect_best_builder` | Docusaurus > MkDocs > raw + suggestions |
| Self-contained dark-theme hub page | `engine.py` `_generate_hub_page` | Inline CSS grid + card hover animations |
| SIGTERM → wait → SIGKILL preview shutdown | `preview.py` `stop_preview` | Graceful + max-3 concurrency limit |
| File path → segment preview URL resolution | `discovery.py` `resolve_file_to_segments` | .mdx/.md strip + index handling |
| Per-builder CI workflow composition | `ci.py` `generate_ci_workflow` | Dynamic setup steps + per-segment build |

---

## Design Decisions

### Why multi-segment architecture instead of single-site?

Projects often have multiple documentation concerns: user docs,
API reference, guides, changelog. Multi-segment lets each use the
best builder (MkDocs for user docs, Docusaurus for API) while
producing a unified site via the merge step.

### Why .pages/ workspace instead of building in-source?

Builders like MkDocs and Docusaurus generate config files, node_modules,
and build artifacts. Isolating these in `.pages/` keeps the source
tree clean and makes gitignoring trivial. The workspace also persists
between builds for incremental compilation.

### Why SSE streaming for build and install?

Build and install operations can take 30+ seconds (especially
Docusaurus with npm). SSE streaming gives real-time feedback
(stage-by-stage progress, log lines) without requiring WebSocket
infrastructure. The generator pattern makes it easy to yield
events from subprocess output.

### Why auto-generate a hub page during merge?

When merging multiple segments, the root `/` path needs a landing page.
Auto-generating `index.html` with links to each segment ensures the
deployed site is navigable without manual configuration. Users can
override this by adding a "root" segment.

### Why in-memory preview tracking instead of disk?

Preview servers are ephemeral — they're only meaningful while the
main server process is running. Persisting them to disk would create
stale entries after restart. In-memory tracking with process polling
is simpler and always accurate.
