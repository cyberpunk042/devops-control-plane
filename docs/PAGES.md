# Pages Builder System

> Build and deploy multi-segment documentation sites using any static site
> generator — from the web admin.

---

## Overview

The Pages system turns project content into a published website. It supports
multiple **segments** (independent content sections) that can each use a
different builder (MkDocs, Hugo, Docusaurus, Sphinx, etc.). Segments are merged
into a single site and deployed to GitHub Pages.

```
Source         →  Builder         →  Build          →  Merge        →  Deploy
(docs/, blog/)   (mkdocs, hugo)    (HTML output)    (combine all)    (gh-pages)
```

---

## Concepts

### Segment

A segment is a named section of your site. Each segment has:

- **name** — unique identifier (e.g., `docs`, `blog`, `api`)
- **source** — path to the content folder (e.g., `docs/`)
- **builder** — which SSG to use
- **path** — URL path on the published site (e.g., `/docs`)
- **config** — builder-specific settings (theme, plugins, etc.)

Segments are declared in `project.yml`:

```yaml
pages:
  base_url: /devops-control-plane
  deploy_branch: gh-pages
  segments:
    - name: docs
      source: docs/
      builder: mkdocs
      path: /docs
      config:
        theme: material
        site_url: https://docs.example.com
```

### Builder

A builder wraps a specific static site generator. Each builder:

1. **Detects** whether its SSG is installed
2. **Scaffolds** config files (mkdocs.yml, hugo.toml, etc.)
3. **Builds** the site (runs the SSG)
4. **Previews** with a local dev server

---

## Available Builders

| Builder | Requires | Config Fields |
|---------|----------|---------------|
| **raw** | Nothing | None — copies files directly |
| **mkdocs** | Python + mkdocs | Theme, plugins, extensions, YAML override |
| **hugo** | Hugo binary | Theme, menu, params, TOML override |
| **docusaurus** | Node.js + npm | 20+ features: search, math, mermaid, PWA, etc. |
| **sphinx** | Python + sphinx | Theme, extensions, conf.py override |
| **custom** | User-defined | Build command, output dir, preview, env vars |

### Builder Selection

The web admin shows all builders with their availability status. If a builder's
dependencies aren't installed, it shows install hints.

---

## Configuration Schema

Each builder declares a **config schema** — a list of typed fields that the UI
renders dynamically. Field types:

| Type | Renders as |
|------|-----------|
| `text` | Single-line input |
| `textarea` | Multi-line editor |
| `number` | Numeric input |
| `select` | Dropdown menu |
| `bool` | Toggle switch |

Fields are grouped by **category** (e.g., Appearance, Site Identity, Advanced)
and support descriptions, defaults, placeholders, and required flags.

### Example: MkDocs Config

| Field | Type | Category |
|-------|------|----------|
| Theme | select (auto/material/mkdocs/readthedocs) | Appearance |
| Site URL | text | Site Identity |
| Repository URL | text | Site Identity |
| Plugins | textarea (YAML list) | Extensions |
| Markdown Extensions | textarea (YAML list) | Extensions |
| Extra CSS | textarea (YAML list) | Assets |
| Extra JavaScript | textarea (YAML list) | Assets |
| Raw Config Override | textarea (YAML) | Advanced |

### Example: Custom Builder Config

| Field | Type | Category |
|-------|------|----------|
| Build Command | textarea | Build |
| Output Directory | text | Build |
| Preview Command | textarea | Preview |
| Preview Port | number | Preview |
| Environment Variables | textarea (KEY=VALUE) | Advanced |

---

## Build Pipeline

Each builder has a **pipeline** — an ordered list of named stages:

### MkDocs Pipeline
```
Scaffold (Generate mkdocs.yml)  →  Build (mkdocs build)
```

### Docusaurus Pipeline
```
Source  →  Transform  →  Scaffold  →  Install  →  Build
```

### Hugo Pipeline
```
Scaffold (Generate hugo.toml)  →  Build (hugo)
```

Build progress is streamed via **Server-Sent Events (SSE)**. The UI shows
real-time log output with per-stage timing.

---

## Build Workspace

All build artifacts go into `.pages/` (gitignored):

```
.pages/
├── docs/                        # per-segment workspace
│   ├── docs/                    # source content (symlinked)
│   ├── mkdocs.yml               # generated config
│   └── build/                   # output HTML
├── blog/
│   └── ...
└── _merged/                     # combined output for deploy
    ├── docs/
    ├── blog/
    └── index.html               # auto-generated hub page
```

---

## Deploy

### GitHub Pages

The merge stage combines all segment outputs under their configured paths, then
deploys to the `gh-pages` branch via `git push --force`.

### CI Workflow Generation

The system can generate a `.github/workflows/pages.yml` file that automates
the build + deploy on push.

### Preview

Each segment can start a local dev server for authoring:
- One preview per segment at a time
- Auto-stop after 30 minutes idle
- UI shows the port and an "Open" link

---

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/pages/segments` | GET | List all segments |
| `/api/pages/segments` | POST | Create a segment |
| `/api/pages/segments/<name>` | PUT | Update config |
| `/api/pages/segments/<name>` | DELETE | Remove segment |
| `/api/pages/builders` | GET | List builders + schemas |
| `/api/pages/build/<name>` | POST | Build one segment |
| `/api/pages/build-all` | POST | Build + merge all |
| `/api/pages/build-log/<name>` | GET | SSE log stream |
| `/api/pages/preview/<name>` | POST | Start preview |
| `/api/pages/preview/<name>` | DELETE | Stop preview |
| `/api/pages/deploy` | POST | Deploy to gh-pages |
| `/api/pages/features` | GET | Docusaurus features |

---

## Extending

### Adding a New Builder

1. Create `src/ui/web/pages_builders/mybuilder.py`
2. Subclass `PageBuilder` from `base.py`
3. Implement: `info()`, `detect()`, `pipeline_stages()`, `run_stage()`
4. Optionally implement `config_schema()` for UI fields
5. Register in `pages_builders/__init__.py`

The builder will automatically appear in the UI with availability detection
and config rendering.

---

## See Also

- [WEB_ADMIN.md](WEB_ADMIN.md) — Web dashboard overview
- [ARCHITECTURE.md](ARCHITECTURE.md) — System architecture
