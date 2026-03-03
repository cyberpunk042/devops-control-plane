# CLI Domain: Pages — GitHub Pages Build, Deploy & Segment Management

> **4 files · 308 lines · 9 commands · Group: `controlplane pages`**
>
> Full GitHub Pages lifecycle: manage page segments (list, add, remove),
> build individual segments using pluggable builders (Docusaurus, MkDocs,
> Hugo, etc.), merge built segments into a unified site, deploy to
> gh-pages branch, generate CI workflows, check build status, and
> list available builders.
>
> Core services: `core/services/pages_engine.py` + `core/services/pages_builders.py`

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                        controlplane pages                           │
│                                                                      │
│  ┌── Segments ──────┐  ┌── Build/Deploy ──────┐  ┌── Info ───────┐ │
│  │ list             │  │ build NAME           │  │ builders      │ │
│  │ add NAME -b -s   │  │ merge                │  └───────────────┘ │
│  │ remove NAME      │  │ deploy               │                    │
│  └──────────────────┘  │ ci                    │                    │
│                         │ status               │                    │
│                         └──────────────────────┘                    │
└──────────┬──────────────────────┬──────────────────┬──────────────┘
           │                      │                  │
           ▼                      ▼                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  core/services/pages_engine.py    core/services/pages_builders.py   │
│                                                                      │
│  Segments:                        Builders:                          │
│    get_segments(root)               list_builders() → Builder[]     │
│    add_segment(root, ...)                                            │
│    remove_segment(root, name)                                        │
│                                                                      │
│  Build pipeline:                                                     │
│    build_segment(root, name)   → success, output_dir, duration      │
│    merge_segments(root)        → merged output dir                  │
│    deploy_to_ghpages(root)     → success, url                       │
│    generate_ci_workflow(root)  → path                               │
│    get_build_status(root)      → {name: {state, ...}}              │
└──────────────────────────────────────────────────────────────────────┘
```

### Segment Architecture

Pages uses a **segment-based architecture** where each segment is an
independent documentation site (Docusaurus docs, MkDocs API reference,
Hugo blog, etc.). Segments are configured, built independently, then
merged into a single static site for deployment.

```
Segment lifecycle:
1. add segment  → register name, builder, source_dir
2. build NAME   → run builder (docusaurus build, mkdocs build, etc.)
3. merge        → copy all built segments into unified output dir
4. deploy       → push unified output to gh-pages branch
```

### Builder Abstraction

Builders are pluggable adapters that know how to build a specific
static site generator. Each builder has:

```
Builder:
├── name        → internal identifier (e.g., "docusaurus")
├── label       → human-readable label (e.g., "Docusaurus v3")
├── available   → whether the builder's CLI is available
└── description → what it builds
```

The `builders` command lists all available builders so users know
what options they have when adding a segment.

### Build Pipeline

```
build segment "docs"
├── Look up segment config (name, builder, source_dir)
├── Invoke builder.build(source_dir)
│   ├── Docusaurus: npx docusaurus build
│   ├── MkDocs: mkdocs build
│   ├── Hugo: hugo --minify
│   └── (etc.)
├── Report: success, output_dir, duration
└── Catch Exception → "Build failed: ..."

merge
├── For each built segment:
│   └── Copy output to unified site directory
└── Report: output_dir

deploy
├── Push unified output to gh-pages branch via git
└── Report: success, url
```

### Error Handling

Build, merge, and deploy commands all wrap calls in `try/except Exception`.
This is a deliberate choice: builder processes can fail in unpredictable
ways (missing node_modules, Python import errors, etc.), and the CLI
must always produce a clean error message rather than a stack trace.

---

## Commands

### `controlplane pages list`

List all configured page segments.

```bash
controlplane pages list
controlplane pages list --json
```

**Output example:**

```
📄 Page segments (3):
   • docs [docusaurus] → site/docs
   • api [mkdocs] → site/api
   • blog [hugo] → site/blog
```

**No segments:**

```
No page segments configured.
   Use 'pages add' to create one.
```

---

### `controlplane pages add NAME`

Add a new page segment.

```bash
controlplane pages add docs -b docusaurus -s site/docs
controlplane pages add api -b mkdocs -s site/api -o build/api
controlplane pages add blog -b hugo -s content/blog --json
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `NAME` | argument | (required) | Segment name |
| `-b/--builder` | string | (required) | Builder type |
| `-s/--source` | path | (required) | Source directory |
| `-o/--output` | path | (auto) | Custom output directory |
| `--json` | flag | off | JSON output |

---

### `controlplane pages remove NAME`

Remove a page segment.

```bash
controlplane pages remove blog
```

**Output:** `"✅ Removed segment: blog"`

---

### `controlplane pages build NAME`

Build a single page segment.

```bash
controlplane pages build docs
controlplane pages build docs --json
```

**Output example:**

```
🔨 Building segment: docs...
✅ Build succeeded: docs
   Output: .pages_build/docs
   Duration: 12.3s
```

---

### `controlplane pages merge`

Merge all built segments into the final site output.

```bash
controlplane pages merge
controlplane pages merge --json
```

**Output:** `"✅ Segments merged"` + output directory.

---

### `controlplane pages deploy`

Deploy merged site to GitHub Pages (gh-pages branch).

```bash
controlplane pages deploy
controlplane pages deploy --json
```

**Output example:**

```
🚀 Deploying to GitHub Pages...
✅ Deployed to gh-pages
   URL: https://user.github.io/repo
```

---

### `controlplane pages ci`

Generate a GitHub Actions CI workflow for Pages deployment.

```bash
controlplane pages ci
controlplane pages ci --json
```

**Output example:**

```
✅ CI workflow generated
   Path: .github/workflows/pages.yml
```

---

### `controlplane pages status`

Show build status for all segments.

```bash
controlplane pages status
controlplane pages status --json
```

**Output example:**

```
📊 Build Status:
   ✅ docs: built
   ⏳ api: building
   ❌ blog: failed
```

**Status icons:**

| Icon | State |
|------|-------|
| ✅ | built |
| ❌ | failed |
| ⏳ | building |
| ⬜ | pending |
| ❓ | unknown |

---

### `controlplane pages builders`

List available page builders.

```bash
controlplane pages builders
controlplane pages builders --json
```

**Output example:**

```
🔧 Available builders (4):
   ✓ docusaurus   — Docusaurus v3
     Full-featured documentation framework
   ✓ mkdocs       — MkDocs
     Material-based documentation
   ✓ hugo         — Hugo
     Fast static site generator
   ✗ jekyll       — Jekyll
     GitHub Pages default (Ruby required)
```

---

## File Map

```
cli/pages/
├── __init__.py     37 lines — group definition, _resolve_project_root,
│                              sub-module imports (segments, build, info)
├── segments.py     88 lines — list, add, remove segment commands
├── build.py       147 lines — build, merge, deploy, ci, status commands
├── info.py         36 lines — builders command
└── README.md               — this file
```

**Total: 308 lines of Python across 4 files.**

---

## Per-File Documentation

### `__init__.py` — Group definition (37 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `_resolve_project_root(ctx)` | helper | Reads `config_path` from context, falls back to `find_project_file()` |
| `pages()` | Click group | Top-level `pages` group |
| `from . import segments, build, info` | import | Registers sub-modules |

---

### `segments.py` — Segment management (88 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `list_segments(ctx, as_json)` | command (`list`) | List configured segments |
| `add(ctx, name, builder, source, output, as_json)` | command | Add a page segment with builder + source |
| `remove(ctx, name)` | command | Remove a segment by name |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `get_segments` | `pages_engine` | Segment listing |
| `add_segment` | `pages_engine` | Segment registration |
| `remove_segment` | `pages_engine` | Segment deletion |

**Segment data shape:** Each segment has `name`, `builder`, and
`source_dir` fields. The `add` command allows optional `output_dir`
for custom build output locations.

---

### `build.py` — Build pipeline (147 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `build(ctx, name, as_json)` | command | Build a single segment |
| `merge(ctx, as_json)` | command | Merge all built segments |
| `deploy(ctx, as_json)` | command | Deploy to gh-pages branch |
| `generate_ci(ctx, as_json)` | command (`ci`) | Generate CI workflow YAML |
| `build_status(ctx, as_json)` | command (`status`) | Show per-segment build state |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `build_segment` | `pages_engine` | Individual segment building |
| `merge_segments` | `pages_engine` | Segment merging into unified site |
| `deploy_to_ghpages` | `pages_engine` | gh-pages deployment via git |
| `generate_ci_workflow` | `pages_engine` | GitHub Actions YAML generation |
| `get_build_status` | `pages_engine` | Build state tracking |

**JSON serialization note:** All commands in this file use
`json.dumps(..., default=str)`. This is because build results can
contain `Path` objects and datetime values that are not JSON-
serializable by default. The `default=str` fallback converts them.

**Build output:** Shows `output_dir` and `duration` (formatted to 1
decimal place as seconds) on success. Shows error message on failure.

**Deploy URL:** On successful deployment, shows the GitHub Pages URL
(e.g., `https://user.github.io/repo`).

---

### `info.py` — Builder listing (36 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `builders(ctx, as_json)` | command | List available page builders |

**Core service import (lazy):**

| Import | From | Used For |
|--------|------|----------|
| `list_builders` | `pages_builders` | Builder registry listing |

**Builder JSON serialization:** This command manually constructs JSON
from Builder objects (`b.name`, `b.label`, `b.available`, `b.description`)
rather than relying on `default=str`. This is because Builder objects
are dataclass instances that need explicit field extraction.

---

## Dependency Graph

```
__init__.py
├── click                        ← click.group
├── core.config.loader           ← find_project_file (lazy)
└── Imports: segments, build, info

segments.py
├── click                        ← click.command
└── core.services.pages_engine   ← get_segments, add_segment,
                                    remove_segment (all lazy)

build.py
├── click                        ← click.command
└── core.services.pages_engine   ← build_segment, merge_segments,
                                    deploy_to_ghpages, generate_ci_workflow,
                                    get_build_status (all lazy)

info.py
├── click                        ← click.command
└── core.services.pages_builders ← list_builders (lazy)
```

**Two core services:** This is the only CLI domain that imports from
two different core service modules (`pages_engine` and `pages_builders`).

---

## Consumers

### Who registers this CLI group

| Layer | Module | What It Does |
|-------|--------|-------------|
| CLI entry | `src/main.py:449` | `from src.ui.cli.pages import pages` |

### Who also uses the same core service

| Layer | Module | Core Service Used |
|-------|--------|------------------|
| Web routes | `routes/pages/api.py` | `pages_builders.SegmentConfig` |

---

## Design Decisions

### Why segments are a first-class concept

Multi-site projects (docs + API reference + blog) need independent
build pipelines. Segments let each sub-site use a different builder
(Docusaurus for docs, MkDocs for API, Hugo for blog) while merging
into a single deployment.

### Why build and deploy are separate commands

Building is slow (Docusaurus/MkDocs compilation). Deploying is fast
(git push). Keeping them separate lets users:
- Build once, inspect output, then deploy
- Build in CI, deploy from a different stage
- Rebuild one segment without redeploying everything

### Why merge exists as a separate step

Each segment builds into its own output directory. Merge copies them
into a unified directory with proper path prefixes. Without merge,
you'd deploy only one segment at a time.

### Why `ci` generates a workflow (not runs one)

CI workflows need to be committed to `.github/workflows/`. The `ci`
command generates the YAML file; the user commits it, and GitHub
Actions runs it. This follows the same pattern as `cli/ci` workflow
generation.

### Why `build` wraps in try/except Exception

Builder processes are external (npm, python, hugo, etc.) and can fail
in unpredictable ways: missing dependencies, syntax errors in config,
permissions issues. Catching all exceptions ensures the CLI always
shows a clean error message.

### Why `builders` uses a separate core module

Builder logic (knowing how to invoke each static site generator) is
complex and independent of the engine logic (knowing how to manage
segments, merge, and deploy). Separating them keeps each module focused.

---

## JSON Output Examples

### `pages list --json`

```json
[
  {
    "name": "docs",
    "builder": "docusaurus",
    "source_dir": "site/docs"
  },
  {
    "name": "api",
    "builder": "mkdocs",
    "source_dir": "site/api"
  }
]
```

### `pages build docs --json`

```json
{
  "success": true,
  "output_dir": ".pages_build/docs",
  "duration": 12.3
}
```

### `pages deploy --json`

```json
{
  "success": true,
  "url": "https://user.github.io/repo"
}
```

### `pages builders --json`

```json
[
  {
    "name": "docusaurus",
    "label": "Docusaurus v3",
    "available": true,
    "description": "Full-featured documentation framework"
  },
  {
    "name": "mkdocs",
    "label": "MkDocs",
    "available": true,
    "description": "Material-based documentation"
  }
]
```

### `pages status --json`

```json
{
  "docs": {"state": "built"},
  "api": {"state": "building"},
  "blog": {"state": "failed"}
}
```
