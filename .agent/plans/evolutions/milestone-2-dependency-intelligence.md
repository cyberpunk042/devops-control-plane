# Milestone 2 — Dependency Intelligence

> Status: FOUNDATION BUILT — adapters in progress
> Last updated: 2026-03-16
>
> **Coverage:** All 9 ecosystems implemented (pip, npm, go, cargo,
> bundler, maven, gradle, mix, dotnet). pip/npm/go/cargo have specialized
> output parsers. bundler/maven/gradle/mix/dotnet use generic fallback parser.
> Version intelligence stubs in all adapters — Phase 3 enrichment pending.
> See [m2-adapters-plan.md](m2-adapters-plan.md) for details.

---

## Goal

Make the project's own dependencies first-class citizens of the platform.
Detect what the project needs, manage it at the right scope, stream it live,
detect issues, remediate, and visualize the impact surface.

---

## What M2 adds to the platform

Two new systems (not enhancements to existing code):

| Evolution | Name | What it is |
|-----------|------|------------|
| **E1** | Dependency-Aware Package Management with Live Observability | Scope-aware operations (Global → Ecosystem → Package) with native commands, SSE streaming, per-ecosystem output parsing, version/deprecation intelligence, rollback |
| **E10** | Dependency Graph & Impact Analysis | Model inter-module relationships, blast radius analysis before operations, visual graph |

---

## What already exists (foundation, not replaced)

| Component | Location | Reused how |
|-----------|----------|------------|
| Manifest detection (9 PMs) | `packages_svc/ops.py` | Imported by the new scanner — extended, not rewritten |
| Install/update/audit/outdated | `packages_svc/actions.py` | Package-level operations stay here; E1 adds ecosystem-level above it |
| SSE streaming | `event_bus.py` + route patterns | Same infrastructure, new stream endpoints |
| Streaming execution pattern | `tool_install/orchestration/stream.py` | Reference for SSE event shape |
| Remediation system | `tool_install/domain/remediation_planning.py` | Extended with ecosystem-specific handlers |
| Modal system | `templates/scripts/globals/_modal.html` | Used for the dependency operations modal |
| Dashboard card | `templates/scripts/_dashboard.html:79` | The "📦 N modules" card becomes the entry point |
| Event tracking | `events/emit.py`, `events/tracked.py` | All operations emit timeline events |
| Module detection | `/status` API → `moduleList` | Provides the module list for per-module scanning |

---

# E1 — Dependency-Aware Package Management with Live Observability

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Dashboard Card                        │
│  📦 5 modules · 3 ecosystems · 2 outdated · ● Healthy   │
│  [click → opens modal]                                   │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                  Operations Modal                        │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │              Dependency Tree (left)               │    │
│  │                                                   │    │
│  │  ☐ Global (install all)                          │    │
│  │    ├── ☐ Python (root/) — requirements.txt       │    │
│  │    │     ├── requests 2.31.0  ⚠ 2.32.3 avail    │    │
│  │    │     ├── flask 3.0.1  ✓ current              │    │
│  │    │     └── celery 5.3.6  ⛔ deprecated         │    │
│  │    ├── ☐ Python (workers/) — requirements.txt    │    │
│  │    │     └── ...                                  │    │
│  │    ├── ☐ Node (frontend/) — package.json         │    │
│  │    │     ├── react 18.2.0  ✓ current             │    │
│  │    │     └── webpack 5.89.0  ⚠ 5.91.0 avail     │    │
│  │    └── ☐ Go (api/) — go.mod                      │    │
│  │          └── ...                                  │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │            Operation Panel (right)                │    │
│  │                                                   │    │
│  │  Scope: Python (root/)                           │    │
│  │  Action: [Install ▾] [Update ▾] [Rollback ▾]    │    │
│  │                                                   │    │
│  │  ┌─── Live Output ───────────────────────────┐   │    │
│  │  │ $ pip install -r requirements.txt          │   │    │
│  │  │ Collecting requests==2.31.0                │   │    │
│  │  │   Using cached requests-2.31.0.whl         │   │    │
│  │  │ Collecting flask==3.0.1                    │   │    │
│  │  │   Downloading flask-3.0.1.tar.gz           │   │    │
│  │  │ ⚠ WARNING: celery 5.3.6 is deprecated     │   │    │
│  │  │ Successfully installed 12 packages         │   │    │
│  │  └───────────────────────────────────────────┘   │    │
│  │                                                   │    │
│  │  Warnings: 1 deprecated, 1 conflict             │    │
│  │  [View Remediations]                             │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │         Version Intelligence (bottom)             │    │
│  │                                                   │    │
│  │  celery 5.3.6  ⛔ DEPRECATED                     │    │
│  │    EOL: 2025-06-01 · Successor: celery 5.4.x    │    │
│  │    Impact: workers/ module uses task scheduling   │    │
│  │    Note: "Waiting for kombu 5.4 compat — Q2"     │    │
│  │    [Add Note] [Update] [Dismiss]                 │    │
│  │                                                   │    │
│  │  webpack 5.89.0  ⚠ OUTDATED (5.91.0 available)  │    │
│  │    No breaking changes in 5.91.0                  │    │
│  │    [Update] [Pin Version] [Add Note]             │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

---

## Backend — New service: `src/core/services/dependency_mgr/`

This is a **new service**, not an extension of `packages_svc` or `tool_install`.

### File structure

```
src/core/services/dependency_mgr/
├── __init__.py              # Public API
├── README.md                # Service documentation
├── scanner.py               # Manifest detection + dependency parsing
├── tree.py                  # Tree model (Global → Ecosystem → Package)
├── executor.py              # Native command execution with streaming
├── parsers/                 # Per-ecosystem output parsers
│   ├── __init__.py
│   ├── base.py              # Parser protocol
│   ├── pip.py               # pip output → structured events
│   ├── npm.py               # npm output → structured events
│   ├── go.py                # go mod output → structured events
│   ├── cargo.py             # cargo output → structured events
│   └── generic.py           # Fallback for unsupported PMs
├── version_intel.py         # Version/deprecation/EOL intelligence
├── rollback.py              # Snapshot + restore per ecosystem
├── notes.py                 # User annotations on versions/decisions
└── remediation.py           # Ecosystem-specific remediation extensions
```

### scanner.py — Manifest detection + dependency parsing

**Imports from** `packages_svc/ops.py`: `_PACKAGE_MANAGERS`, `_detect_pm_for_dir`

**New responsibility**: Actually **parse** the manifests to extract individual packages with pinned versions.

```python
@dataclass
class DeclaredDependency:
    name: str
    version_spec: str          # ">=2.31.0", "^18.2.0", "~5.3"
    pinned_version: str | None # Resolved from lock file if available
    group: str                 # "main", "dev", "test", "optional"
    source_file: str           # "requirements.txt", "package.json"
    source_path: str           # Relative path from project root

@dataclass
class EcosystemManifest:
    ecosystem: str             # "pip", "npm", "go", "cargo", etc.
    path: str                  # Directory containing the manifest (relative)
    manifest_file: str         # "requirements.txt", "package.json"
    lock_file: str | None      # "requirements.txt", "package-lock.json", etc.
    cli_available: bool
    dependencies: list[DeclaredDependency]
    dev_dependencies: list[DeclaredDependency]
    total_count: int

@dataclass
class ProjectDependencyTree:
    manifests: list[EcosystemManifest]
    total_ecosystems: int
    total_packages: int
    total_outdated: int        # From version intelligence
    total_deprecated: int      # From version intelligence
    scan_ts: float
```

**Manifest parsers** (per ecosystem):

| Ecosystem | Files parsed | How |
|-----------|-------------|-----|
| pip | `requirements.txt` | Line-by-line, `pkg==ver` / `pkg>=ver` / `-r other.txt` recursion |
| pip | `pyproject.toml` | `tomllib` → `[project.dependencies]` + `[project.optional-dependencies]` |
| pip | `Pipfile` | `tomllib` → `[packages]` + `[dev-packages]` |
| npm | `package.json` | JSON → `dependencies` + `devDependencies` + `peerDependencies` |
| go | `go.mod` | Line-by-line → `require (...)` block |
| cargo | `Cargo.toml` | `tomllib` → `[dependencies]` + `[dev-dependencies]` + `[build-dependencies]` |
| bundler | `Gemfile` | Line-by-line → `gem 'name', 'ver'` |
| maven | `pom.xml` | XML → `<dependencies>` |
| mix | `mix.exs` | Regex → `{:dep, "~> ver"}` |

**Monorepo handling**: The scanner walks all known modules (from `moduleList`)
and detects manifests per directory. Two `package.json` at different paths =
two separate Node ecosystems in the tree. They are **separate entries** but
can be **selected together** via the Global or ecosystem-type checkbox.

```
☐ Global
  ├── ☐ Python (root/)            ← requirements.txt at project root
  ├── ☐ Python (workers/)         ← requirements.txt in workers/
  ├── ☐ Node (frontend/)          ← package.json in frontend/
  ├── ☐ Node (api/)               ← package.json in api/
  └── ☐ Go (services/gateway/)    ← go.mod in services/gateway/
```

### tree.py — Tree model

The tree is the **operation scope selector**. Three levels:

| Level | Selection | What runs |
|-------|-----------|-----------|
| **Global** | All ecosystems | Sequential: pip → npm → go → ... (each native) |
| **Ecosystem** | One ecosystem instance | `pip install -r requirements.txt` in that directory |
| **Package** | One package | `pip install --upgrade requests` (current behavior via `packages_svc`) |

The tree model is a data structure, not a UI component. The frontend renders it.

```python
@dataclass
class TreeNode:
    id: str                    # "global", "pip:root", "pip:workers", "npm:frontend", "npm:frontend:react"
    label: str                 # "Global", "Python (root/)", "react 18.2.0"
    level: Literal["global", "ecosystem", "package"]
    ecosystem: str | None      # "pip", "npm", "go", etc.
    path: str | None           # Relative dir path
    children: list[TreeNode]
    # Package-level fields
    version: str | None
    latest_version: str | None
    version_status: str | None # "current", "outdated", "deprecated", "eol", "unknown"
    note: str | None           # User annotation
```

### executor.py — Native command execution with streaming

Runs the **native command** for each ecosystem and streams output line-by-line
via SSE. Does NOT use `packages_svc/actions.py` for grouped operations — it
runs the commands directly because it needs streaming and parsing.

**Commands per operation:**

| Ecosystem | Install | Update (all) | Update (single) | Rollback |
|-----------|---------|-------------|-----------------|----------|
| pip | `pip install -r requirements.txt` | `pip install -r requirements.txt --upgrade` | `pip install --upgrade <pkg>` | Restore snapshot → `pip install -r` |
| npm | `npm ci` (if lock) / `npm install` | `npm update` | `npm update <pkg>` | Restore lock → `npm ci` |
| go | `go mod download` | `go get -u ./...` | `go get -u <pkg>` | Restore go.sum → `go mod download` |
| cargo | `cargo fetch` | `cargo update` | `cargo update -p <pkg>` | Restore Cargo.lock → `cargo fetch` |
| bundler | `bundle install` | `bundle update` | `bundle update <gem>` | Restore Gemfile.lock → `bundle install` |
| maven | `mvn dependency:resolve` | N/A (managed by POM) | N/A | Restore pom.xml |
| mix | `mix deps.get` | `mix deps.update --all` | `mix deps.update <dep>` | Restore mix.lock → `mix deps.get` |

**Streaming shape** (SSE events):

```json
{"type": "operation_start", "scope": "pip:root", "command": "pip install -r requirements.txt", "ts": 1710600000}
{"type": "log", "line": "Collecting requests==2.31.0", "ts": 1710600001}
{"type": "log", "line": "  Using cached requests-2.31.0-py3-none-any.whl", "ts": 1710600001}
{"type": "package_resolved", "name": "requests", "version": "2.31.0", "action": "installed", "ts": 1710600001}
{"type": "warning", "category": "deprecated", "package": "celery", "message": "celery 5.3.6 is deprecated", "ts": 1710600002}
{"type": "error", "category": "conflict", "package": "kombu", "message": "kombu 5.3.0 requires vine>=5.1.0, but you have vine 5.0.0", "ts": 1710600003}
{"type": "package_resolved", "name": "flask", "version": "3.0.1", "action": "installed", "ts": 1710600003}
{"type": "log", "line": "Successfully installed 12 packages", "ts": 1710600004}
{"type": "operation_done", "scope": "pip:root", "status": "ok", "packages_resolved": 12, "warnings": 1, "errors": 0, "duration_ms": 4200, "ts": 1710600004}
```

For **Global** operations, the executor runs ecosystems sequentially and wraps
the whole thing in a `batch_start` / `batch_done` envelope:

```json
{"type": "batch_start", "ecosystems": ["pip:root", "pip:workers", "npm:frontend", "go:api"], "ts": ...}
...per-ecosystem events...
{"type": "batch_done", "status": "ok", "total_resolved": 47, "total_warnings": 2, "total_errors": 0, "duration_ms": 12400, "ts": ...}
```

### parsers/ — Per-ecosystem output parsing

Each parser receives raw stdout/stderr lines and emits structured events.

**Protocol:**

```python
class OutputParser(Protocol):
    def feed_line(self, line: str, stream: Literal["stdout", "stderr"]) -> list[ParsedEvent]: ...
    def finalize(self) -> list[ParsedEvent]: ...

@dataclass
class ParsedEvent:
    type: str                  # "package_resolved", "warning", "error", "progress"
    package: str | None
    version: str | None
    category: str | None       # "deprecated", "conflict", "missing_dep", "build_error"
    message: str
    severity: str              # "info", "warning", "error"
    remediation_hint: str | None  # Ecosystem-specific hint
```

**What each parser detects:**

| Parser | Detects |
|--------|---------|
| **pip** | `Successfully installed X-Y.Z`, `WARNING: X is deprecated`, `ERROR: Cannot install X`, version conflicts, missing system deps (`No matching distribution`), build failures (`error: subprocess-exited-with-error`) |
| **npm** | `added N packages`, `npm WARN deprecated`, `npm ERR!`, peer dependency conflicts, audit warnings inline, fund notices |
| **go** | `go: downloading X v1.2.3`, `go: module X: not found`, checksum mismatch |
| **cargo** | `Compiling X v1.2.3`, `warning: unused variable`, build errors, version resolution conflicts |
| **generic** | Line-level pass-through with basic error/warning regex (`ERROR`, `WARN`, `FAIL`, non-zero exit) |

### version_intel.py — Version & deprecation intelligence

Enriches the dependency tree with version health information.

**Data sources per ecosystem:**

| Ecosystem | Version data source | Deprecation data |
|-----------|-------------------|-----------------|
| pip | `pip index versions <pkg>` or PyPI JSON API | PyPI `yanked` flag, `classifiers` (Development Status) |
| npm | `npm view <pkg> versions` | npm `deprecated` field |
| go | `go list -m -versions <pkg>` | No native deprecation signal; use retract directive |
| cargo | `cargo search <pkg>` | crates.io `yanked` flag |

**Version status model:**

```python
@dataclass
class VersionIntel:
    package: str
    ecosystem: str
    installed_version: str
    latest_version: str | None
    status: Literal["current", "outdated", "deprecated", "eol", "yanked", "unknown"]
    eol_date: str | None       # ISO date if known
    successor: str | None      # Suggested replacement package
    breaking_changes: bool     # True if latest is a major bump
    changelog_url: str | None  # Link to changelog/release notes
    detail: str                # Human-readable explanation
```

**Caching**: Version intelligence is expensive (network calls per package).
Cached in the mediator with a 1-hour TTL under `dependency.versions.<ecosystem>`.
Force-refresh available from the modal.

### rollback.py — Snapshot + restore

Before every ecosystem-level or global operation, snapshot the state files.

**Snapshot location:** `.state/dependency_snapshots/<timestamp>/`

```
.state/dependency_snapshots/
└── 2026-03-16T14-30-00/
    ├── manifest.json          # What was snapshotted and why
    ├── root/
    │   └── requirements.txt   # Copy of the file before operation
    ├── frontend/
    │   ├── package.json
    │   └── package-lock.json
    └── api/
        ├── go.mod
        └── go.sum
```

**manifest.json:**
```json
{
    "ts": "2026-03-16T14:30:00Z",
    "operation": "update",
    "scope": "global",
    "ecosystems": ["pip:root", "npm:frontend", "go:api"],
    "files": [
        {"src": "requirements.txt", "dst": "root/requirements.txt"},
        {"src": "frontend/package.json", "dst": "frontend/package.json"},
        {"src": "frontend/package-lock.json", "dst": "frontend/package-lock.json"},
        {"src": "api/go.mod", "dst": "api/go.mod"},
        {"src": "api/go.sum", "dst": "api/go.sum"}
    ]
}
```

**Rollback process:**
1. Copy snapshot files back to their original locations
2. Run the ecosystem's install command (to restore the actual installed state)
3. Stream the install output via SSE (same as a normal install)
4. Emit rollback timeline event

**Retention**: Keep last 10 snapshots. Older ones auto-pruned.

### notes.py — User annotations on version decisions

Users can attach notes to explain why a version is pinned or why a deprecation
is acknowledged. This feeds into version intelligence — annotated packages stop
being flagged.

**Storage:** `.state/dependency_notes.json`

```json
{
    "pip:celery:5.3.6": {
        "note": "Waiting for kombu 5.4 compat -- Q2 2026",
        "author": "user",
        "ts": "2026-03-16T14:30:00Z",
        "dismiss_until": "2026-06-01",
        "status": "acknowledged"
    },
    "npm:webpack:5.89.0": {
        "note": "Pinned for build stability until frontend rewrite",
        "author": "user",
        "ts": "2026-03-10T09:00:00Z",
        "dismiss_until": null,
        "status": "acknowledged"
    }
}
```

**Behavior:**
- Acknowledged packages show in the tree but with a note icon instead of a warning
- `dismiss_until` date auto-removes the acknowledgement when reached
- Notes are visible in the Version Intelligence panel and in the timeline
- Adding/removing a note emits a timeline event

### remediation.py — Ecosystem-specific remediation extensions

Extends the existing remediation system with handlers for dependency-level issues.

**New remediation categories:**

| Category | Example | Remediation options |
|----------|---------|-------------------|
| `version_conflict` | "kombu requires vine>=5.1" | 1. Pin compatible version 2. Upgrade both 3. Remove conflicting dep |
| `missing_system_dep` | "No matching distribution for X" | 1. Install system package 2. Use pre-built wheel 3. Build from source |
| `deprecated_package` | "celery 5.3.6 is deprecated" | 1. Upgrade to latest 2. Pin successor 3. Acknowledge with note |
| `build_failure` | "error: subprocess-exited-with-error" | 1. Install build tools 2. Use binary wheel 3. Try different version |
| `audit_vulnerability` | "CVE-2024-XXXX in requests" | 1. Upgrade to patched version 2. Pin safe version 3. Acknowledge risk |

These plug into the existing remediation planning system at Layer 2
(method-family level), similar to how `tool_install` handlers work.

---

## Backend — API surface

### Routes: `src/ui/web/routes/dependencies/`

```
GET  /api/dependencies/tree                    → Full dependency tree (cached via mediator)
GET  /api/dependencies/tree?bust=1             → Force rescan
POST /api/dependencies/install                 → Install at scope
POST /api/dependencies/update                  → Update at scope
POST /api/dependencies/rollback                → Rollback to snapshot
GET  /api/dependencies/install/stream           → SSE stream for install
GET  /api/dependencies/update/stream            → SSE stream for update
GET  /api/dependencies/versions/<ecosystem>     → Version intelligence for ecosystem
POST /api/dependencies/note                     → Add/update note on a package
DELETE /api/dependencies/note                   → Remove note
GET  /api/dependencies/snapshots               → List rollback snapshots
GET  /api/dependencies/snapshot/<id>            → Snapshot detail
```

**Request shapes:**

```json
// POST /api/dependencies/install
{
    "scope": "pip:root",           // or "global", or "npm:frontend:react"
    "options": {                   // Ecosystem-specific flags
        "dev": false,              // Include dev dependencies
        "frozen": true             // Use lock file (npm ci vs npm install)
    }
}

// POST /api/dependencies/update
{
    "scope": "pip:root",           // Ecosystem scope
    "packages": ["requests"],      // Optional: specific packages (null = all)
    "strategy": "compatible"       // "compatible" (minor+patch) | "latest" (major) | "exact" (pin)
}

// POST /api/dependencies/rollback
{
    "snapshot_id": "2026-03-16T14-30-00"
}

// POST /api/dependencies/note
{
    "ecosystem": "pip",
    "package": "celery",
    "version": "5.3.6",
    "note": "Waiting for kombu 5.4 compat",
    "dismiss_until": "2026-06-01"      // Optional
}
```

### Mediator nodes

```
dependency.tree           → ProjectDependencyTree (cached, TTL 5min)
dependency.tree.module.*  → Per-module manifest data
dependency.versions.pip   → Version intel for pip ecosystem (TTL 1hr)
dependency.versions.npm   → Version intel for npm ecosystem (TTL 1hr)
dependency.snapshots      → Rollback snapshot list
```

**Cascade:** `dependency.tree` depends on `index.scan` (module list).
Version intel depends on `dependency.tree`.

### Event tracking

All operations emit timeline events via `@tracked` and `emit_event`:

| Event type | When | Summary example |
|------------|------|----------------|
| `dependency.scan.completed` | Tree scan done | "Scanned 5 ecosystems, 127 packages" |
| `dependency.install.started` | Install begins | "Installing: Python (root/)" |
| `dependency.install.completed` | Install done | "Installed 12 packages (4.2s)" |
| `dependency.install.failed` | Install failed | "Install failed: pip — version conflict" |
| `dependency.update.started` | Update begins | "Updating: requests → 2.32.3" |
| `dependency.update.completed` | Update done | "Updated 3 packages" |
| `dependency.update.failed` | Update failed | "Update failed: npm ERR!" |
| `dependency.rollback.completed` | Rollback done | "Rolled back to 2026-03-16T14:30" |
| `dependency.note.added` | Note added | "Note on celery 5.3.6: Waiting for..." |
| `dependency.note.removed` | Note removed | "Note removed: celery 5.3.6" |

Chain domain: `dependency` — all operations in a session share a correlation ID.

---

## Frontend — Dashboard card update

The existing "📦 N modules" line in Project Pulse becomes richer:

**Before:**
```
📦 5 modules
```

**After:**
```
📦 5 modules · 3 ecosystems · 2 outdated · 1 deprecated
```

Clicking the 📦 area opens the **Dependency Modal**.

The numbers come from `dependency.tree` mediator data, pushed via SSE
(same pattern as posture badge).

---

## Frontend — Dependency Modal

### Layout

The modal uses `modalOpen({ size: 'wide' })` — the existing wide modal pattern.

**Three panels:**

1. **Dependency Tree (left, ~35% width)** — checkboxable tree with Global → Ecosystem → Package hierarchy. Each node shows version status icon.

2. **Operation Panel (right, ~65% width, top)** — shows the selected scope, action buttons (Install / Update / Rollback), live SSE output terminal, warning/error summary.

3. **Version Intelligence (right, ~65% width, bottom)** — selected package detail: version status, EOL info, notes, remediation options.

### Tree interactions

- **Click** a tree node → selects it as the operation scope, shows its detail in the right panel
- **Checkbox** a tree node → includes it in a batch operation
- **Expand/collapse** ecosystem nodes to show/hide packages
- Tree nodes have status icons:
  - ✓ green = current
  - ⚠ yellow = outdated
  - ⛔ red = deprecated / EOL / yanked
  - 📝 = has user note (overrides warning icon)
  - ◌ gray = unknown (no version intel yet)

### Live output terminal

When an operation runs, the right panel shows a terminal-style output area:
- Raw command output streams in real-time via SSE
- Parsed warnings/errors are highlighted inline (yellow/red background)
- Per-package resolution lines get a ✓ or ✗ prefix
- Progress indicator at the top (N/M packages resolved)
- On completion: summary bar with counts + duration

### Version Intelligence panel

Shows when a package is selected in the tree:
- Current version vs. latest available
- Status badge (CURRENT / OUTDATED / DEPRECATED / EOL)
- EOL date if known
- Breaking changes warning if major version bump
- Changelog link if available
- User notes (editable inline)
- Action buttons: Update, Pin, Add Note, Dismiss

---

# E10 — Dependency Graph & Impact Analysis

## Architecture

E10 models the **relationships between modules and their shared dependencies**.
It answers: "If I upgrade X, what else is affected?"

### Backend: `src/core/services/dependency_mgr/graph.py`

```python
@dataclass
class DependencyEdge:
    source: str                # Module or ecosystem ID
    target: str                # Package name
    version_spec: str          # What the source requires
    pinned_version: str | None

@dataclass
class SharedDependency:
    package: str
    ecosystem: str
    consumers: list[str]       # Module IDs that depend on this
    versions: dict[str, str]   # module_id → pinned version
    conflict: bool             # True if consumers want different versions

@dataclass
class ImpactAnalysis:
    package: str
    from_version: str
    to_version: str
    affected_modules: list[str]
    breaking: bool
    shared_by: int             # Number of consumers
    risk: Literal["low", "medium", "high"]
    detail: str
```

### Graph construction

Built from `ProjectDependencyTree` data:

1. For each ecosystem manifest, extract declared dependencies
2. Build edges: module → package
3. Identify shared packages (same package name across multiple manifests)
4. Cross-reference version specs to detect conflicts
5. When an operation targets a shared package, compute blast radius

### Impact analysis before operations

When the user selects "Update requests" in the tree, before executing:

```json
{
    "package": "requests",
    "from_version": "2.31.0",
    "to_version": "2.32.3",
    "affected_modules": ["root", "workers"],
    "shared_by": 2,
    "breaking": false,
    "risk": "low",
    "detail": "requests is used in 2 modules (root/, workers/). Both pin ==2.31.0. Update will affect both."
}
```

This is shown in the Operation Panel **before** the user confirms.

### Visual graph

Rendered in the modal as an optional view (tab or toggle):

```
    ┌─────────┐     ┌─────────────┐     ┌──────────┐
    │  root/  │────▶│  requests   │◀────│ workers/ │
    │ (Python)│     │   2.31.0    │     │ (Python) │
    └────┬────┘     └─────────────┘     └────┬─────┘
         │                                    │
         │          ┌─────────────┐           │
         └────────▶ │   flask     │           │
                    │   3.0.1     │           │
                    └─────────────┘           │
                                              │
                    ┌─────────────┐           │
                    │   celery    │◀──────────┘
                    │   5.3.6 ⛔  │
                    └─────────────┘
```

**Rendering**: Simple SVG or canvas — no heavy library. Modules on the sides,
shared packages in the middle. Edges colored by status (green=ok, yellow=outdated,
red=deprecated). Clicking a package highlights all consuming modules.

For v1, a simple force-directed layout or a bipartite layout (modules left,
packages right) is sufficient. No need for d3 — a lightweight SVG renderer
handles this scale (typically <50 nodes).

### API

```
GET  /api/dependencies/graph              → Full graph data
GET  /api/dependencies/impact?package=X&to_version=Y  → Impact analysis
```

### Mediator node

```
dependency.graph          → Graph edges + shared deps (derived from dependency.tree)
```

---

## State management

### .state/ directory additions

```
.state/
├── dependency_snapshots/              # Rollback snapshots (max 10)
│   └── <timestamp>/
│       ├── manifest.json
│       └── <path>/<files>
├── dependency_notes.json              # User annotations
└── dependency_cache/                  # Version intel cache (backup)
    ├── pip_versions.json
    ├── npm_versions.json
    └── ...
```

### Mediator integration

New registrations in `src/core/services/mediator/registrations/dependencies.py`:

```python
def register_dependency_nodes(mediator):
    mediator.register("dependency.tree", resolver=resolve_dependency_tree,
                      depends_on=["index.scan"], ttl=300)
    mediator.register("dependency.versions.pip", resolver=resolve_pip_versions,
                      depends_on=["dependency.tree"], ttl=3600)
    mediator.register("dependency.versions.npm", resolver=resolve_npm_versions,
                      depends_on=["dependency.tree"], ttl=3600)
    mediator.register("dependency.graph", resolver=resolve_dependency_graph,
                      depends_on=["dependency.tree"], ttl=300)
    mediator.register("dependency.snapshots", resolver=resolve_snapshots, ttl=60)
```

---

## Version/deprecation scanning and its connection to stack intelligence

This is the piece that makes E1 more than just "npm install with a pretty UI."

### What it scans

For every declared dependency:
1. **Current version** — from lock file or manifest
2. **Latest available** — from ecosystem registry (PyPI, npm, crates.io, etc.)
3. **Deprecation status** — from ecosystem metadata
4. **EOL date** — from known EOL databases or ecosystem signals
5. **Security advisories** — from `package_audit()` (already exists in `packages_svc`)

### How it connects to module/stack intelligence

Each module in the project has a detected stack (Python 3.12, Node 20, Go 1.22).
The dependency versions often have **constraints tied to the stack version**:

- Django 5.0 requires Python ≥ 3.10
- Next.js 14 requires Node ≥ 18.17
- A Go module with `go 1.22` in go.mod won't build on Go 1.20

**The version intelligence system cross-references:**

```
Module: workers/ (Python 3.12)
  ├── celery 5.3.6 → DEPRECATED (successor: 5.4.x, requires Python ≥ 3.10 ✓)
  ├── django 4.2.0 → OUTDATED (5.0 available, requires Python ≥ 3.10 ✓)
  └── numpy 1.24.0 → OUTDATED (2.0 available, requires Python ≥ 3.9 ✓, but has breaking API changes ⚠)
```

When a **stack upgrade** is being considered (Python 3.12 → 3.13), the system
can report which dependencies support the new version and which don't — this
is the **impact analysis feeding M3** (Stack Version Advisor).

### User notes at the module level

Notes can be attached at two levels:
1. **Package level**: "Staying on celery 5.3.6 because kombu compat"
2. **Module level**: "workers/ pinned to Python 3.12 — deployment constraint"

Both are stored in `dependency_notes.json` and surfaced in the UI.
Both emit timeline events. Both feed into posture (acknowledged items don't
drag the rank down).

---

## Relationship to existing systems

```
                    ┌──────────────────┐
                    │   tool_install    │  System-level tools
                    │  (94 recipes)     │  "Install docker on your machine"
                    └──────────────────┘
                              │
                              │  Different concern
                              │
┌──────────────────┐         │         ┌──────────────────┐
│   packages_svc    │ ◀──────┼───────▶ │  dependency_mgr   │  E1/E10 (NEW)
│  (detection +     │  imports         │  (scope-aware ops, │
│   individual ops) │  scanner data    │   streaming,       │
└──────────────────┘                   │   version intel,   │
                                       │   graph, rollback) │
                                       └──────────────────┘
                                                │
                                                │  Feeds into
                                                ▼
                                       ┌──────────────────┐
                                       │   M3: Lifecycle   │
                                       │   Stack Health    │
                                       │   (E3, E8, E2)    │
                                       └──────────────────┘
```

- `packages_svc` stays as-is. It's the low-level library for detection and individual operations.
- `dependency_mgr` is the high-level system that provides scope-aware operations, streaming, intelligence, and graph.
- `tool_install` is a completely separate concern (system tools vs. project packages).

---

## Implementation phases (suggested)

### Phase 1 — Scanner + Tree + Card
- Build `scanner.py` — parse all 9 manifest types
- Build `tree.py` — tree model
- Mediator node `dependency.tree`
- Dashboard card update (counts from tree)
- Basic modal with tree view (read-only)

### Phase 2 — Operations + Streaming
- Build `executor.py` — native command execution
- Build `parsers/pip.py` and `parsers/npm.py` (most common first)
- SSE streaming endpoints
- Install / Update operations in the modal
- Event tracking for all operations

### Phase 3 — Rollback + Version Intelligence
- Build `rollback.py` — snapshot before operations, restore
- Build `version_intel.py` — PyPI/npm registry queries
- Version status icons in the tree
- Version Intelligence panel in the modal

### Phase 4 — Notes + Remediation
- Build `notes.py` — user annotations
- Build `remediation.py` — ecosystem-specific handlers
- Remediation panel in the modal
- Note editing in the UI

### Phase 5 — Graph (E10)
- Build `graph.py` — edge model, shared dependency detection
- Impact analysis before operations
- Graph visualization in the modal
- Graph API endpoint

---

## Open decisions (for iteration)

1. **Graph rendering approach** — Simple SVG bipartite layout, or something more interactive? For v1 I think simple SVG is enough. We can always add interactivity later.

2. **Version intel batch vs. on-demand** — Scan all packages on tree load (slow, 30s+) or lazy-load per ecosystem when expanded? I lean toward lazy-load with background pre-fetch.

3. **Shared packages across ecosystem types** — A Python package and an npm package can have the same name but be unrelated. The graph should only show cross-module sharing within the same ecosystem, not across ecosystems. Confirm?

4. **Remediation depth** — How deep do we go on ecosystem-specific remediation in Phase 4? Full handler stack per PM, or just the top 3-5 most common issues per ecosystem?

5. **Lock file generation** — When updating, should we auto-generate lock files if they don't exist? (`pip freeze > requirements.txt`, `npm shrinkwrap`)

6. **Dashboard card click behavior** — Does clicking the whole Project Pulse row open the modal, or only clicking the "📦" section? I lean toward just the 📦 section to avoid hijacking other card interactions.
