# Artifacts Implementation Plan

> [!IMPORTANT]
> This plan adds `artifacts:` alongside `pages:` — zero breaking changes to existing pages infrastructure.

---

## 1. What We're Building

### 1.1 The Concept

Today the control plane builds **one kind of output**: static site pages (docs, code-docs).
We're adding a second kind: **distributable program artifacts** (CLI, packages, bundles, install scripts).

Both share the same lifecycle pattern:

```
Scan → Detect → Configure → Build → Output → Distribute
```

Pages already implements this for static sites. Artifacts reuses the same patterns for tools.

### 1.2 Concrete Artifact Targets (for devops-control-plane)

| Target | What gets produced | Build tool | Output |
|---|---|---|---|
| **local-install** | Editable pip install on this machine | `make install` | pip installs `devops` CLI |
| **pip-wheel** | `.whl` package file | `python -m build` | `dist/devops_control_plane-*.whl` |
| **tarball** | Portable archive with `manage.sh` | custom script | `dist/devops-control-plane-*.tar.gz` |
| **install-script** | One-liner bootstrap script | template generation | `dist/install.sh` |
| **container** | Docker/Podman image | `docker build` | image in local/remote registry |

### 1.3 Release Levels (logical progression)

| Level | When | How |
|---|---|---|
| **local** | First thing we build | `make install` → pip editable → `devops` available on PATH |
| **snapshot** | After local works | Git tag + wheel build → store artifact locally or push to CI |
| **release** | When ready to publish | Version bump + wheel → PyPI or GitHub Release |
| **production** | Deployed | Container image → registry → Kubernetes/systemd |

> [!NOTE]
> We start with **local**. Each level unlocks the next. The plan covers all levels but we build them in order.

---

## 2. Config Schema

### 2.1 `project.yml` Changes

```yaml
# Existing — untouched
pages:
  segments:
    - name: docs
      source: docs
      builder: docusaurus
      path: /docs
      auto: true
      config: {}
    - name: code-docs
      source: code-docs
      builder: docusaurus
      path: /code-docs
      auto: true
      config: {}

# New — Artifacts section
artifacts:
  targets:
    - name: local-install
      kind: local                     # local | package | bundle | script | container
      builder: makefile               # makefile | pip | script | docker
      build_target: install           # Makefile target or script path
      description: "Editable pip install on this machine"
      modules:                        # Which project modules to include
        - core
        - adapters
        - cli
        - web
      config: {}

    - name: cli-package
      kind: package
      builder: pip
      description: "Distributable pip wheel"
      output_dir: dist/
      config:
        version_from: pyproject.toml  # or git-tag
      
    - name: release-bundle
      kind: bundle
      builder: script
      build_cmd: ./scripts/create_release_bundle.sh
      output_dir: dist/
      description: "Portable tarball with manage.sh"
      config:
        include_source: false
```

### 2.2 Data Model

```python
@dataclass
class ArtifactTarget:
    """A build target that produces a distributable artifact."""
    
    name: str                         # Unique identifier
    kind: str                         # local, package, bundle, script, container
    builder: str                      # makefile, pip, script, docker
    description: str = ""             
    build_target: str = ""            # Makefile target or script path
    build_cmd: str = ""               # Full command override
    output_dir: str = "dist/"         # Where artifact lands
    modules: list[str] = field(default_factory=list)  # Project modules
    config: dict = field(default_factory=dict)
```

### 2.3 What Stays Separate

| Concern | Pages | Artifacts |
|---|---|---|
| Config key | `pages:` | `artifacts:` |
| Listing key | `segments` | `targets` |
| Workspace | `.pages/<segment>/` | `.artifacts/<target>/` |
| Serving | Flask static file server at `/pages/site/` | No serving — produces files |
| Builders | docusaurus, hugo, mkdocs, sphinx, raw, custom | makefile, pip, script, docker |
| Deploy | gh-pages branch push | PyPI, registry, release, local install |

---

## 3. Backend Services

### 3.1 New Service: `src/core/services/artifacts/`

```
src/core/services/artifacts/
├── __init__.py
├── engine.py          # Target CRUD, build orchestration
├── discovery.py       # Detect buildable targets from project structure
└── builders/
    ├── __init__.py
    ├── base.py         # ArtifactBuilder ABC (mirrors pages_builders/base.py)
    ├── makefile.py     # Runs Makefile targets
    ├── pip_builder.py  # Runs python -m build
    ├── script.py       # Runs arbitrary scripts
    └── docker.py       # Runs docker build (later)
```

### 3.2 Artifact Engine (`engine.py`)

Mirrors `pages/engine.py` structure:

```python
# Config I/O
def _get_artifacts_config(project_root: Path) -> dict
def _set_artifacts_config(project_root: Path, config: dict)

# Target CRUD
def get_targets(project_root: Path) -> list[ArtifactTarget]
def get_target(project_root: Path, name: str) -> ArtifactTarget | None
def add_target(project_root: Path, target: ArtifactTarget)
def update_target(project_root: Path, name: str, updates: dict)
def remove_target(project_root: Path, name: str)

# Build
def build_target(project_root: Path, name: str) -> BuildResult
def get_build_status(project_root: Path, name: str) -> dict | None
```

### 3.3 Artifact Discovery (`discovery.py`)

Auto-detect what can be built from project structure:

```python
def detect_artifact_targets(project_root: Path) -> list[dict]:
    """Scan project for buildable artifact targets.
    
    Detects:
    - Makefile with install/build/dist targets → local-install, pip-package
    - pyproject.toml / setup.py → pip-package
    - Dockerfile → container
    - scripts/ with release/bundle scripts → bundle
    - manage.sh → local entry point
    """
```

Uses the existing `pipeline_scanner.py` for Makefile/script analysis.

### 3.4 Makefile Builder (`builders/makefile.py`)

First builder — runs Makefile targets with streaming output:

```python
class MakefileBuilder(ArtifactBuilder):
    def stages(self, target: ArtifactTarget) -> list[str]:
        # Parse Makefile for the target's dependencies
        # e.g., "check" depends on ["lint", "types", "test"]
        return ["lint", "types", "test"]  # for "check" target
    
    def run_stage(self, stage: str, target, workspace) -> Generator[str]:
        # Run: make <stage> with streaming stdout/stderr
        ...
    
    def build(self, target: ArtifactTarget, workspace: Path) -> BuildResult:
        # Run: make <build_target>
        ...
```

### 3.5 The Pipeline Scanner Extension

`pipeline_scanner.py` already detects:
- Shell scripts (with stages, flags, operability)
- Makefiles (with targets)
- Frameworks (docusaurus, etc.)
- CI workflows

Add to its output:

```python
@dataclass
class ScanResult:
    # Existing
    scripts: list[DetectedScript]
    frameworks: list[DetectedFramework]
    ci_workflows: list[CIWorkflow]
    compatibility: str
    compatibility_notes: list[str]
    
    # New
    artifact_candidates: list[dict]  # Detected buildable artifact targets
```

Each candidate:
```python
{
    "name": "local-install",
    "kind": "local",
    "builder": "makefile",
    "build_target": "install",
    "detected_from": "Makefile",
    "description": "Install package in editable mode with dev deps",
    "confidence": "high",
}
```

---

## 4. API Routes

### 4.1 New Blueprint: `routes/artifacts/api.py`

```python
# ── Target CRUD
GET  /api/artifacts/targets          # List all artifact targets
POST /api/artifacts/targets          # Add a target
PUT  /api/artifacts/targets/<name>   # Update a target
DEL  /api/artifacts/targets/<name>   # Remove a target

# ── Discovery
POST /api/artifacts/detect           # Auto-detect from project structure

# ── Build
POST /api/artifacts/build/<name>     # Build a single target
GET  /api/artifacts/build/<name>/status  # Build status
GET  /api/artifacts/build/<name>/stream  # SSE build log stream

# ── (Later: Release/Publish)
POST /api/artifacts/publish/<name>   # Publish to registry/PyPI
```

### 4.2 Reuse from Pages

These patterns are copied from `routes/pages/api.py`:
- SSE streaming for build logs (`build_stream.py` pattern)
- Config read/write via `project.yml`
- Error handling and response format

---

## 5. UI — Card Layout

### 5.1 Split Card Design

The current Pages card is **full-width** below the 3-column grid.
We split it into **two halves** side by side:

```
┌──────────────────────────────────────────────────────┐
│  card-grid (3 columns)                               │
│  [Git] [GitHub] [CI/CD] [Docker] [K8s] [Terraform]  │
└──────────────────────────────────────────────────────┘

┌─────────────────────────┬────────────────────────────┐
│  📄 Pages               │  📦 Artifacts              │
│                         │                            │
│  Segments list          │  Targets list              │
│  Pipeline: Build→Merge  │  Pipeline: Build→Package   │
│  Builders row           │  Builders row              │
│  [Full Setup]           │  [Full Setup]              │
└─────────────────────────┴────────────────────────────┘
         ↕ On mobile: stacks vertically ↕
┌─────────────────────────┐
│  📄 Pages               │
│  ...                    │
├─────────────────────────┤
│  📦 Artifacts           │
│  ...                    │
└─────────────────────────┘
```

### 5.2 HTML Structure

Replace the single full-width `int-pages-card` with:

```html
<div class="build-cards">
    <!-- Pages half -->
    <div class="card" id="int-pages-card">
        <div class="card-header">
            <span class="card-title">📄 Pages</span>
            <div style="display:flex;align-items:center;gap:0.4rem">
                <span class="card-age" data-cache-key="pages" style="font-size:0.64rem;color:var(--text-muted)"></span>
                <button class="btn-icon" onclick="cardRefresh('pages','int-pages-badge','int-pages-detail',loadPagesCard)" title="Refresh" style="font-size:0.7rem;cursor:pointer;background:none;border:none;color:var(--text-muted);padding:0">🔄</button>
                <span class="status-badge" id="int-pages-badge">—</span>
                <span class="audit-pending-badge" data-audit-key="pages" onclick="openAuditManager(this.dataset.auditKey)" title="Unsaved audit — click to manage" style="display:none">📋</span>
            </div>
        </div>
        <div class="card-subtitle">Static site segments</div>
        <div id="int-pages-detail" class="integration-detail" style="margin-top:var(--space-md)">
            <span class="spinner"></span>
        </div>
    </div>

    <!-- Artifacts half -->
    <div class="card" id="int-artifacts-card">
        <div class="card-header">
            <span class="card-title">📦 Artifacts</span>
            <div style="display:flex;align-items:center;gap:0.4rem">
                <span class="card-age" data-cache-key="artifacts" style="font-size:0.64rem;color:var(--text-muted)"></span>
                <button class="btn-icon" onclick="cardRefresh('artifacts','int-artifacts-badge','int-artifacts-detail',loadArtifactsCard)" title="Refresh" style="font-size:0.7rem;cursor:pointer;background:none;border:none;color:var(--text-muted);padding:0">🔄</button>
                <span class="status-badge" id="int-artifacts-badge">—</span>
            </div>
        </div>
        <div class="card-subtitle">Build targets & distribution</div>
        <div id="int-artifacts-detail" class="integration-detail" style="margin-top:var(--space-md)">
            <span class="spinner"></span>
        </div>
    </div>
</div>
```

### 5.3 CSS for Responsiveness

```css
.build-cards {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-lg);
    margin-top: var(--space-lg);
}

@media (max-width: 768px) {
    .build-cards {
        grid-template-columns: 1fr;
    }
}
```

### 5.4 Content Flex Behavior

Both cards share the same content patterns:
- Segment/target rows with status dots
- Pipeline action bar with buttons (flex-wrap ensures wrapping)
- Builders chips row (already flex-wrap)

The Builders row currently uses `display:flex; flex-wrap:wrap` — it will wrap naturally in the narrower half-card.

### 5.5 Card Registry Update

```javascript
// In _init.html card registry:
'int:pages':     { loadFn: () => loadPagesCard(),     cardId: 'int-pages-card',     badgeId: 'int-pages-badge',     detailId: 'int-pages-detail',     label: '📄 Pages' },
'int:artifacts': { loadFn: () => loadArtifactsCard(),  cardId: 'int-artifacts-card', badgeId: 'int-artifacts-badge', detailId: 'int-artifacts-detail', label: '📦 Artifacts' },
```

---

## 6. UI — Wizard Routing

### 6.1 Setup Wizard Evolution

Currently `openSetupWizard('pages')` opens the pages wizard.
With artifacts, it needs a routing step:

```
openSetupWizard('build') → Step 0: What are you building?
  ○ Pages — Static site content
  ○ Artifacts — Distributable programs
  
openSetupWizard('pages') → Goes directly to pages wizard (unchanged)
openSetupWizard('artifacts') → Goes directly to artifacts wizard
```

### 6.2 Artifacts Wizard Steps

```
Step 1: Detect
  - Reads project.yml modules
  - Scans Makefile targets
  - Detects pyproject.toml/setup.py
  - Detects Dockerfile
  - Shows: "What can be built from this project"

Step 2: Configure Targets
  - For each detected buildable:
    ☑ local-install   — make install (editable pip)
    ☐ pip-wheel       — python -m build (distributable)
    ☐ release-bundle  — tarball with manage.sh
    ☐ install-script  — curl | bash bootstrap
    ☐ container       — Docker image
  - Module selection per target
  - Build command customization

Step 3: Review & Apply
  - Show what will be added to project.yml
  - Show build commands
  - Apply configuration
```

---

## 7. Phased Delivery

### Phase 1: Foundation ✅ COMPLETE
- [x] `project.yml` schema: `artifacts.targets` section
- [x] Data model: `ArtifactTarget` dataclass
- [x] Engine: target CRUD (add, list, get, update, remove)
- [x] API routes: `/api/artifacts/targets` CRUD
- [x] UI: Split card layout (Pages left, Artifacts right)
- [x] UI: Artifacts card with empty state + "Full Setup" button
- [x] Card registry entry for artifacts

### Phase 2: Local Build ✅ COMPLETE
- [x] Makefile builder: runs `make <target>` with streaming
- [x] Build streaming: SSE output for artifact builds
- [x] Artifact discovery: detect Makefile targets, pyproject.toml
- [x] Artifacts wizard: Detect → Configure → Review
- [x] API: `/api/artifacts/build/<name>` with SSE stream
- [x] API: `/api/artifacts/detect` for auto-detection
- [x] UI: Target rows with build status, build button, log viewer
- [x] First target: `local-install` via `make install`

### Phase 3: Package Build ✅ COMPLETE
- [x] Pip builder: runs `python -m build`
- [x] Output tracking: `.artifacts/<target>/` workspace
- [x] Build status persistence (like pages build metadata)
- [x] Version detection from pyproject.toml / git tags
- [x] Target: `pip-package` via discovery

### Phase 4: Distribution ✅ PARTIALLY COMPLETE
- [x] Script builder: runs arbitrary release scripts
- [ ] Install script generation (template-based)
- [ ] Release bundle creation (tarball)
- [ ] Target: `release-bundle`, `install-script`

### Phase 5: Container & Publish — PARTIALLY COMPLETE
- [x] Docker builder: runs `docker build` (auto-detects docker/podman, BuildKit, image size)
- [ ] PyPI publish support
- [ ] GitHub Release integration
- [ ] Container registry push
- [ ] Release level management (local → snapshot → release → production)

---

## 8. File Inventory

### New Files

| File | Purpose |
|---|---|
| `src/core/services/artifacts/__init__.py` | Package init, re-exports |
| `src/core/services/artifacts/engine.py` | Target CRUD, build orchestration |
| `src/core/services/artifacts/discovery.py` | Auto-detect targets from project |
| `src/core/services/artifacts/builders/__init__.py` | Builder registry |
| `src/core/services/artifacts/builders/base.py` | ArtifactBuilder ABC |
| `src/core/services/artifacts/builders/makefile.py` | Makefile target runner |
| `src/core/services/artifacts/builders/pip_builder.py` | pip wheel builder |
| `src/core/services/artifacts/builders/script.py` | Arbitrary script runner |
| `src/ui/web/routes/artifacts/__init__.py` | Blueprint init |
| `src/ui/web/routes/artifacts/api.py` | REST API routes |
| `src/ui/web/templates/scripts/integrations/_artifacts.html` | Card JS |
| `src/ui/web/templates/scripts/integrations/setup/_artifacts.html` | Wizard JS |

### Modified Files

| File | Change |
|---|---|
| `project.yml` | Add `artifacts:` section |
| `_tab_integrations.html` | Split card layout, add artifacts card HTML |
| `admin.css` | Add `.build-cards` grid + responsive rules |
| `_init.html` | Add `int:artifacts` card registry entry |
| `server.py` | Register artifacts API blueprint |
| `pipeline_scanner.py` | Add `artifact_candidates` to scan output |

---

## 9. Design Decisions Log

| Decision | Choice | Rationale |
|---|---|---|
| Keep `pages:` separate | ✅ Additive, no migration | Zero risk to existing pages functionality |
| Workspace dir | `.artifacts/<target>/` | Mirrors `.pages/<segment>/` pattern |
| First builder | Makefile | Already exists, already parsed by scanner |
| First target | `local-install` | Most useful immediately, lowest complexity |
| Card layout | Split 50/50 | Same visual area, both visible, responsive flex |
| Wizard routing | Type selector at top | Clean separation, reuses wizard infra |

---

## 10. Dependencies & Constraints

### What's ready to use
- Pipeline scanner (Makefile parsing, script detection)
- Build streaming (SSE pattern from pages)
- Custom builder (arbitrary script execution with DEVOPS_* env)
- Wizard infrastructure (step flow, wizSection, wizStatusRow)
- Card registry and refresh system

### What needs to exist first
- `artifacts:` config schema must be defined before engine
- Engine must exist before API routes
- API routes must exist before UI
- Discovery must exist before wizard

### Build order
```
Schema → Engine → Discovery → API → UI Card → UI Wizard
```
