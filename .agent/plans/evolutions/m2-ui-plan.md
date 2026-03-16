# M2 UI Plan — Dependency Modal & Dashboard Card

> Status: PLAN — visuals established, discuss before executing
> Parent: [milestone-2-dependency-intelligence.md](milestone-2-dependency-intelligence.md)
> Last updated: 2026-03-16

---

## Component inventory

The UI has **2 entry points** and **7 internal components**:

| # | Component | Where | What |
|---|-----------|-------|------|
| **E1** | Dashboard card update | Project Pulse bar | Dependency summary + click target |
| **E2** | Dependency modal shell | Overlay | Header, tabs, layout, states |
| **C1** | Scope tree | Modal left panel | Expandable, checkboxable, status icons |
| **C2** | Operation panel | Modal right top | Scope label, action buttons, strategy, live terminal |
| **C3** | Version intelligence panel | Modal right bottom | Selected package detail, notes, actions |
| **C4** | Remediation panel | Modal right (replaces C3 on trigger) | Per-warning/error remediation options |
| **C5** | Snapshot bar | Modal footer | Rollback snapshot list + restore |
| **C6** | Impact dialog | Pre-operation overlay | Blast radius before confirm (E10) |
| **C7** | Graph view | Modal tab | Visual dependency graph (E10) |

---

## E1. Dashboard Card — Project Pulse Update

**Current:**
```
devops-control-plane  ↗  │  📦 5 modules  🌍 2 envs  ✓ Pulled  ● Healthy
```

**After:**
```
devops-control-plane  ↗  │  📦 5 modules  🌍 2 envs  ✓ Pulled  ● Healthy
                            ╰─ 3 eco · 49 pkg · 2 ⚠ · 1 ⛔
```

- Second line appears under `📦 5 modules` — smaller text, muted
- Counts from `dependency.summary` mediator node (pushed via SSE)
- Numbers: ecosystem count, total packages, outdated count, deprecated count
- Only shows if `ecosystems > 0` (no second line for projects with no manifests)
- Click `📦 5 modules` or the second line → opens dependency modal
- Hover: tooltip with ecosystem breakdown

**States:**
```
No manifests:     📦 5 modules       (no second line, no click)
Loading:          📦 5 modules
                  ╰─ ◌ scanning...
Clean:            📦 5 modules
                  ╰─ 3 eco · 49 pkg
Issues:           📦 5 modules
                  ╰─ 3 eco · 49 pkg · 2 ⚠ · 1 ⛔
```

---

## E2. Modal Shell

Wide modal: `max-width: 960px; max-height: 92vh`.

**Two-column layout** with left tree (~300px fixed) and right panel (flex).

**Header bar** has:
- Title: `📦 Dependencies`
- Tab switcher: `[Tree] [Graph]` (Graph = E10, can be disabled initially)
- Elapsed timer (during operations)
- Close button

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  📦 Dependencies          [Tree] [Graph]               ⏱ 0.0s         ✕   │
├──────────────────────┬──────────────────────────────────────────────────────┤
│                      │                                                      │
│      C1: TREE        │                  C2: OPERATION PANEL                 │
│      (300px)         │                  (flex)                              │
│                      │                                                      │
│                      ├──────────────────────────────────────────────────────┤
│                      │                                                      │
│                      │            C3: VERSION INTELLIGENCE                  │
│                      │            (or C4: REMEDIATION)                      │
│                      │                                                      │
├──────────────────────┴──────────────────────────────────────────────────────┤
│                          C5: SNAPSHOT BAR                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Modal states:**

```
LOADING:
┌─────────────────────────────────────────┐
│  📦 Dependencies                    ✕   │
├─────────────────────────────────────────┤
│        ◌ Scanning manifests...          │
└─────────────────────────────────────────┘

EMPTY:
┌─────────────────────────────────────────┐
│  📦 Dependencies                    ✕   │
├─────────────────────────────────────────┤
│                                         │
│   No dependency manifests detected.     │
│                                         │
│   Supported files:                      │
│   requirements.txt · pyproject.toml     │
│   package.json · go.mod · Cargo.toml    │
│   Gemfile · pom.xml · mix.exs           │
│                                         │
└─────────────────────────────────────────┘
```

---

## C1. Scope Tree

Left panel, 300px fixed width, full height, scrollable.

### Node anatomy

**Global node (root):**
```
☐ Global (3 ecosystems, 49 packages)
```

**Ecosystem node:**
```
▼ ☐ Python (pip) — pyproject.toml                    17 pkg
```
- Expand/collapse chevron (▼/▶)
- Checkbox for batch selection
- Adapter name + manifest filename
- Package count badge (right-aligned, muted)

**Package node:**
```
    click >=8.1                                    ✓  [main]
    flask >=3.0               → 3.1.0 avail       ⚠  [web]
    celery 5.3.6              → EOL 2025-06       ⛔  [main]
    webpack 5.89.0            📝 "pinned for..."   📝  [dev]
    requests                                       ◌  [main]
```
- Name + version spec
- Version intel hint (right side, before status icon):
  - `→ 3.1.0 avail` for outdated
  - `→ EOL 2025-06` for deprecated/eol
  - `📝 "note preview..."` for acknowledged
  - (nothing) for current or unknown
- Status icon: `✓` `⚠` `⛔` `📝` `◌`
- Group tag: `[main]` `[dev]` `[web]` `[ocr]` `[peer]` `[build]`

### Expanded tree (this project)

```
☐ Global (3 ecosystems, 49 packages)
  ▼ ☐ Python (pip) — pyproject.toml                 17
      click >=8.1                                  ◌  [main]
      pydantic >=2.0                               ◌  [main]
      pyyaml >=6.0                                 ◌  [main]
      python-dotenv >=1.0                          ◌  [main]
      jinja2 >=3.1                                 ◌  [main]
      flask >=3.0                                  ◌  [web]
      cryptography >=41.0                          ◌  [web]
      pytesseract >=0.3.10                         ◌  [ocr]
      Pillow >=10.0                                ◌  [ocr]
      pytest >=7.0                                 ◌  [dev]
      pytest-cov >=4.0                             ◌  [dev]
      ruff >=0.4                                   ◌  [dev]
      mypy >=1.0                                   ◌  [dev]
      types-PyYAML >=6.0                           ◌  [dev]
      types-click >=7.0                            ◌  [dev]
      flask >=3.0                                  ◌  [dev]
      cryptography >=41.0                          ◌  [dev]
  ▶ ☐ Node (npm) — .pages/code-docs/package.json    16
  ▶ ☐ Node (npm) — .pages/docs/package.json         16
```

### Tree interactions

| Action | Effect |
|--------|--------|
| Click ecosystem node | Select as operation scope → C2 shows that ecosystem's actions |
| Click package node | Select package → C3 shows version intelligence |
| Checkbox ecosystem | Include in batch → Global checkbox auto-updates |
| Checkbox Global | Check/uncheck all ecosystems |
| ▼/▶ chevron | Expand/collapse children |
| Hover package | Tooltip: full version spec + source file |

---

## C2. Operation Panel

Right side, top portion. Shows context-sensitive controls based on tree selection.

### No selection (default)

```
┌───────────────────────────────────────────────────────────────┐
│  Select an ecosystem or package in the tree to begin.         │
│                                                               │
│  Or check ecosystems and click [Install All] [Update All]     │
└───────────────────────────────────────────────────────────────┘
```

### Ecosystem selected

```
┌───────────────────────────────────────────────────────────────┐
│  Scope: Python (pip) — pyproject.toml                         │
│  Path: . (project root)                                       │
│  Packages: 17 (5 main · 2 web · 2 ocr · 8 dev)              │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐     │
│  │ [Install]  [Update ▾]  [Rollback ▾]     [⛔ Abort]  │     │
│  └──────────────────────────────────────────────────────┘     │
│           ╰── Strategy: [compatible ▾]                        │
│               ☐ Include dev dependencies                      │
│                                                               │
│  ┌─── Terminal ───────────────────────────────────────── ┐    │
│  │                                                       │    │
│  │  (empty — click an action to start)                   │    │
│  │                                                       │    │
│  └───────────────────────────────────────────────────────┘    │
│                                                               │
│  Progress: (idle)                                             │
└───────────────────────────────────────────────────────────────┘
```

**Update strategy dropdown:**
```
┌─────────────────────┐
│ compatible (default) │  Minor + patch only (safe)
│ latest               │  Major versions too (may break)
│ exact                │  Pin to specific version
└─────────────────────┘
```

### During operation

```
┌───────────────────────────────────────────────────────────────┐
│  Scope: Python (pip)                        ⏱ 4.2s           │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐     │
│  │ [Install]  [Update]  [Rollback]          [⛔ Abort]  │     │
│  │  (dim)     (dim)     (dim)               (active)    │     │
│  └──────────────────────────────────────────────────────┘     │
│                                                               │
│  ┌─── Terminal ───────────────────────────────────────── ┐    │
│  │ 📸 Backed up 1 files                                  │    │
│  │ $ pip install -e .                                     │    │
│  │ Collecting click>=8.1                                  │    │
│  │   Using cached click-8.1.7-py3-none-any.whl           │    │
│  │   ✓ click 8.1.7                                       │    │
│  │ Collecting pydantic>=2.0                               │    │
│  │   Downloading pydantic-2.6.3.whl                      │    │
│  │   ✓ pydantic 2.6.3                                    │    │
│  │   ⚠ DEPRECATION: pkg-resources is deprecated          │    │
│  │ Successfully installed 12 packages                     │    │
│  └───────────────────────────────────────────────────────┘    │
│                                                               │
│  12 resolved · 1 ⚠ · 0 ✗                  ✅ Done — 4.2s    │
│                                                               │
│  ⚠ 1 warning detected  [View Remediations]                   │
└───────────────────────────────────────────────────────────────┘
```

### After operation — completion actions

```
  12 resolved · 1 ⚠ · 0 ✗                  ✅ Done — 4.2s

  ⚠ 1 warning detected  [View Remediations]
  ┌─ Warnings ────────────────────────────────────────────┐
  │  ⚠ DEPRECATION: pkg-resources is deprecated           │
  │    → [Upgrade] [Acknowledge] [Dismiss]                │
  └───────────────────────────────────────────────────────┘
```

### Batch operation (Global / multiple checked)

```
┌───────────────────────────────────────────────────────────────┐
│  Scope: Global (3 ecosystems checked)                         │
│                                                               │
│  [Install All]  [Update All]                    [⛔ Abort]    │
│                                                               │
│  ┌─── Terminal ───────────────────────────────────────── ┐    │
│  │ ─── Python (pip) ──────────────────────────────────── │    │
│  │ 📸 Backed up 1 files                                  │    │
│  │ $ pip install -e .                                     │    │
│  │ ...                                                    │    │
│  │ ✅ pip:. — 12 packages — 4.2s                          │    │
│  │                                                        │    │
│  │ ─── Node (npm) — .pages/code-docs ─────────────────── │    │
│  │ 📸 Backed up 2 files                                  │    │
│  │ $ npm ci                                               │    │
│  │ added 847 packages in 8.1s                             │    │
│  │ ✅ npm:.pages/code-docs — 847 packages — 8.1s          │    │
│  │                                                        │    │
│  │ ─── Node (npm) — .pages/docs ──────────────────────── │    │
│  │ $ npm ci                                               │    │
│  │ added 847 packages in 7.9s                             │    │
│  │ ✅ npm:.pages/docs — 847 packages — 7.9s               │    │
│  └───────────────────────────────────────────────────────┘    │
│                                                               │
│  ✅ All done — 1706 packages — 3 ecosystems — 20.2s          │
└───────────────────────────────────────────────────────────────┘
```

---

## C3. Version Intelligence Panel

Shows when a **package node** is selected in the tree.
Replaces C2's bottom area (below terminal, or fullscreen if no operation running).

### Package with version intel

```
┌───────────────────────────────────────────────────────────────┐
│  flask                                                  ⚠     │
│                                                               │
│  Installed:   >=3.0 (resolved: 3.0.1)                        │
│  Latest:      3.1.0                                           │
│  Status:      OUTDATED — minor update available               │
│  Breaking:    No (minor version bump)                         │
│  Changelog:   https://flask.palletsprojects.com/changes/      │
│  Group:       web (pyproject.toml)                            │
│                                                               │
│  📝 Notes: (none)                                             │
│                                                               │
│  [Update to 3.1.0]  [Pin 3.0.1]  [Add Note]                 │
└───────────────────────────────────────────────────────────────┘
```

### Deprecated package

```
┌───────────────────────────────────────────────────────────────┐
│  celery                                                 ⛔     │
│                                                               │
│  Installed:   5.3.6                                           │
│  Latest:      5.4.0                                           │
│  Status:      DEPRECATED — past EOL                           │
│  EOL:         2025-06-01                                      │
│  Successor:   celery 5.4.x                                   │
│  Breaking:    Yes (major changes in task API)                 │
│  Impact:      Used by workers/ (task scheduling)              │
│                                                               │
│  📝 Note: "Waiting for kombu 5.4 compat — Q2 2026"           │
│     Added: 2026-03-16 · Expires: 2026-06-01                  │
│     [Edit Note]  [Remove Note]                                │
│                                                               │
│  [Update to 5.4.0]  [Acknowledge Risk]  [View CVEs]          │
└───────────────────────────────────────────────────────────────┘
```

### Package with no intel yet

```
┌───────────────────────────────────────────────────────────────┐
│  click                                                  ◌     │
│                                                               │
│  Version spec: >=8.1                                          │
│  Group:        main (pyproject.toml)                          │
│  Status:       Unknown — version intelligence not loaded      │
│                                                               │
│  [Check Latest Version]                                       │
└───────────────────────────────────────────────────────────────┘
```

---

## C4. Remediation Panel

Appears when user clicks `[View Remediations]` after an operation with warnings/errors.
Replaces C3 temporarily.

```
┌───────────────────────────────────────────────────────────────┐
│  Remediations (1 warning, 0 errors)                    [✕]   │
│                                                               │
│  ⚠ DEPRECATION: pkg-resources is deprecated                  │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  Option 1: Upgrade to latest                          │   │
│  │    pip install --upgrade pkg-resources                 │   │
│  │    [Execute]                                          │   │
│  │                                                       │   │
│  │  Option 2: Acknowledge with note                      │   │
│  │    Add a note explaining why this is acceptable        │   │
│  │    [Acknowledge]                                      │   │
│  │                                                       │   │
│  │  Option 3: Dismiss                                    │   │
│  │    Hide this warning for 30 days                      │   │
│  │    [Dismiss]                                          │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                               │
│  ⛔ ERROR: No matching distribution for nonexistent-pkg      │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  Option 1: Remove from requirements                   │   │
│  │    [Remove]                                           │   │
│  │                                                       │   │
│  │  Option 2: Install system dependency                  │   │
│  │    apt install libfoo-dev                             │   │
│  │    [Execute]                                          │   │
│  └───────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────┘
```

---

## C5. Snapshot Bar

Modal footer. Always visible. Collapsed by default.

**Collapsed:**
```
┌───────────────────────────────────────────────────────────────┐
│  ▶ Snapshots: 3 available · Last: 2026-03-16 14:30           │
└───────────────────────────────────────────────────────────────┘
```

**Expanded (click to toggle):**
```
┌───────────────────────────────────────────────────────────────┐
│  ▼ Snapshots (3)                                              │
│                                                               │
│  2026-03-16 14:30  │ install │ pip:.             │ 1 file  │ [Restore]
│  2026-03-16 12:15  │ update  │ npm:.pages/docs   │ 2 files │ [Restore]
│  2026-03-15 09:00  │ install │ global            │ 7 files │ [Restore]
│                                                               │
│  Restore copies manifest/lock files back and runs the         │
│  ecosystem's install command to sync installed packages.      │
└───────────────────────────────────────────────────────────────┘
```

---

## C6. Impact Dialog (E10)

Pre-operation overlay. Shows before confirming an update that affects shared deps.
Only appears when the graph detects cross-module impact.

```
┌───────────────────────────────────────────────────────────────┐
│  ⚠ Impact Analysis                                           │
│                                                               │
│  Updating requests 2.31.0 → 2.32.3                          │
│                                                               │
│  This package is shared by 2 modules:                        │
│    • root/ (Python) — requires ==2.31.0                      │
│    • workers/ (Python) — requires ==2.31.0                   │
│                                                               │
│  Risk: Low (minor version, no breaking changes)              │
│                                                               │
│  Both modules will be updated.                               │
│                                                               │
│  [Proceed]  [Cancel]                                         │
└───────────────────────────────────────────────────────────────┘
```

---

## C7. Graph View (E10)

Replaces the tree+panel layout when Graph tab is selected.
Full-width SVG/canvas visualization.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  📦 Dependencies          [Tree] [Graph]                               ✕   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│     ┌──────────┐                                         ┌──────────┐      │
│     │  root/   │─── requests 2.31.0 ──────────────────── │ workers/ │      │
│     │ (Python) │─── flask 3.0.1                          │ (Python) │      │
│     └────┬─────┘                                         └────┬─────┘      │
│          │                                                    │             │
│          ├─── click 8.1.7                                     │             │
│          ├─── pydantic 2.6.3                                  │             │
│          └─── jinja2 3.1.3                                    │             │
│                                                               │             │
│                                                    celery 5.3.6 ⛔          │
│                                                                             │
│     ┌─────────────────┐                      ┌──────────────────┐          │
│     │ .pages/code-docs│─── react 18.2.0 ──── │ .pages/docs     │          │
│     │ (Node)          │─── @docusaurus 3.9.2 │ (Node)          │          │
│     └─────────────────┘                      └──────────────────┘          │
│                                                                             │
│  Legend: ── shared dep   ⚠ outdated   ⛔ deprecated   ✓ current            │
│  Click a package to see consuming modules. Click a module to see its deps. │
├─────────────────────────────────────────────────────────────────────────────┤
│  ▶ Snapshots: 3 available · Last: 2026-03-16 14:30                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation plan (UI chunks)

### UI-1: Modal shell + tree (read-only)
- Modal open/close from dashboard card click
- Fetch `dependency.tree` on open
- Render scope tree (C1) — expand/collapse, status icons, group tags
- Loading + empty states
- No operations yet, no version intel
- **Files:** `_dep_modal.html`, update `_dashboard.html`

### UI-2: Operation panel + live terminal
- Action buttons (Install, Update, Rollback, Abort)
- Strategy dropdown, dev checkbox
- SSE streaming terminal (uses existing `_dep_stream.html`)
- Progress counters, completion status
- Batch mode for Global / multiple checked
- **Files:** `_dep_modal.html` (extend), `_dep_stream.html` (already exists)

### UI-3: Version intelligence panel
- Package selection → detail panel
- Current vs. latest, status badge, EOL, breaking, changelog
- Notes: display, add, edit, remove (uses existing `/dependencies/note` routes)
- Action buttons: Update, Pin, Add Note
- **Files:** `_dep_modal.html` (extend)

### UI-4: Remediation panel
- `[View Remediations]` button after operations with warnings/errors
- Per-issue remediation options (upgrade, acknowledge, dismiss, remove)
- Execute remediation actions inline
- **Files:** `_dep_modal.html` (extend)

### UI-5: Snapshot bar
- Footer: collapsed count, click to expand
- Snapshot list with restore buttons
- Restore triggers rollback stream
- **Files:** `_dep_modal.html` (extend)

### UI-6: Impact dialog (E10)
- Pre-operation overlay
- Requires `graph.py` backend (not yet built)
- Shows blast radius from shared dep analysis
- Proceed/Cancel buttons
- **Files:** `_dep_modal.html` (extend), `graph.py` (new backend)

### UI-7: Graph view (E10)
- Full-width SVG visualization
- Tab switch Tree ↔ Graph
- Module nodes on sides, shared packages in middle
- Click interactions
- **Files:** `_dep_graph.html` (new), `graph.py` (shared with UI-6)

---

## Dependency order

```
UI-1 ──→ UI-2 ──→ UI-3 ──→ UI-4
  │                          │
  └──→ UI-5                  │
                             │
UI-6 ──→ UI-7               │
  │       (E10 backend       │
  └──────needed first)───────┘
```

UI-1 through UI-5 = E1 (core feature, no E10 dependency).
UI-6 and UI-7 = E10 (graph backend needed first).

---

## Files

| Chunk | New files | Modified |
|-------|-----------|----------|
| UI-1 | `templates/scripts/dependencies/_dep_modal.html` | `_dashboard.html`, `_tab_dashboard.html` |
| UI-2 | — (extends _dep_modal.html) | `_dep_stream.html` (already exists) |
| UI-3 | — (extends _dep_modal.html) | — |
| UI-4 | — (extends _dep_modal.html) | — |
| UI-5 | — (extends _dep_modal.html) | — |
| UI-6 | — (extends _dep_modal.html) | new: `dependency_mgr/graph.py` |
| UI-7 | `templates/scripts/dependencies/_dep_graph.html` | — |

Most of the UI lives in **one file** (`_dep_modal.html`) that grows through chunks.
This is intentional — keeps the modal self-contained like `_pages_sse.html`.
