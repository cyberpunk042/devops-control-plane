# Scripts System — Milestone 4: Interface Integration (CLI + API + Admin Panel)

> **Status**: Planning — Iteration 2
> **Parent**: `.agent/plans/scripts-system.md`
> **Milestone**: M4 — Interface Integration
> **Depends on**: M1 (Execution Framework)
> **Unlocks**: Full user access to scripts from all three UI layers

---

## 0. What This Milestone Delivers

After M4 is complete:

1. **Integrations tab card**: 🧩 Scripts card in the card-grid, after Terraform
2. **Setup wizard**: Detect → Adopt → Configure → Apply — drives the user into a managed scripts setup
3. **CLI**: `controlplane scripts list|run|info|history` — scripts accessible from the command line
4. **Web API**: `GET/POST /api/scripts/*` — scripts accessible from the admin panel and external tools
5. **Admin panel section**: Script browser + run form + live output stream — visual script management
6. All three interfaces use the **same** M1 backend (registry, executor, output_router) — no duplication

**What you can do after M4**: See your scripts as a card in the Integrations tab, run the setup wizard to adopt existing scripts and cherry-pick templates, browse/run/stream scripts from the admin panel, CLI, or API.

---

## 1. Architecture — Three Layers, One Backend

```
 Integrations Tab          CLI (click)            Web API (Flask)
 Card + Wizard             │                      │
    │                      │ import               │ import
    │ fetch()              │                      │
    ▼                      ▼                      ▼
┌──────────────────────────────────────────────────────┐
│          src/core/services/scripts/                    │
│                                                        │
│   registry.discover_scripts()                          │
│   executor.execute_script()                            │
│   output_router.resolve_output()                       │
│   config.load_scripts_config()                         │
└──────────────────────────────────────────────────────┘
```

---

## 2. Card Placement — Integrations Tab

### 2.1 Position

The 🧩 Scripts card goes in the **card-grid**, after Terraform. Same treatment as Docker, K8s, Terraform — a regular integration card, not a special section.

```
┌──────────────────────────────────────────────────────┐
│  card-grid (3+ columns, wraps on resize)             │
│                                                       │
│  [🔀 Git]    [🐙 GitHub]  [⚡ CI/CD]                │
│  [🐳 Docker] [☸ K8s]     [🏗 Terraform]             │
│  [🧩 Scripts]                                        │  ← HERE
│                                                       │
└──────────────────────────────────────────────────────┘

┌─────────────────────────┬────────────────────────────┐
│  📄 Pages               │  📦 Artifacts              │
└─────────────────────────┴────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│  🌐 DNS & CDN                                        │
└──────────────────────────────────────────────────────┘
```

### 2.2 Card HTML

Added to `_tab_integrations.html`, inside the `card-grid`, after the Terraform card div:

```html
<!-- ── Scripts Card ──────────────────────────────────────── -->
<div class="card" id="int-scripts-card">
    <div class="card-header">
        <span class="card-title">🧩 Scripts</span>
        <div style="display:flex;align-items:center;gap:0.4rem">
            <span class="card-age" data-cache-key="scripts" style="font-size:0.64rem;color:var(--text-muted)"></span>
            <button class="btn-icon" onclick="cardRefresh('scripts','int-scripts-badge','int-scripts-detail',loadScriptsCard)" title="Refresh" style="font-size:0.7rem;cursor:pointer;background:none;border:none;color:var(--text-muted);padding:0">🔄</button>
            <span class="status-badge" id="int-scripts-badge">—</span>
        </div>
    </div>
    <div class="card-subtitle">Automation & code analysis</div>
    <div id="int-scripts-detail" class="integration-detail" style="margin-top:var(--space-md)">
        <span class="spinner"></span>
    </div>
</div>
```

### 2.3 Card Registry

Added to `_INT_CARDS` in `_init.html`:

```javascript
'int:scripts': {
    loadFn: () => loadScriptsCard(),
    cardId: 'int-scripts-card',
    badgeId: 'int-scripts-badge',
    detailId: 'int-scripts-detail',
    label: '🧩 Scripts'
},
```

### 2.4 Wizard Dispatch

Added to `_dispatch.html`:

```javascript
scripts: openScriptsSetupWizard,
```

---

## 3. Card States — The Full UX

### 3.1 State 1: Nothing configured

No `scripts/` directory, no `scripts:` section in `project.yml`.

```
┌──────────────────────────────────────────────────────┐
│ 🧩 Scripts                                      — │
│ Automation & code analysis                            │
│                                                      │
│  ┌─────────────────────────────────────────────────┐ │
│  │ 💡 No scripts configured                       │ │
│  │ Set up automation scripts for code analysis,   │ │
│  │ quality audits, and project maintenance.        │ │
│  │                              [Set up →]         │ │
│  └─────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

Uses `cardSetupBanner()` — same pattern as other unconfigured integrations.

### 3.2 State 2: Scripts detected but unmanaged

`scripts/` directory exists with scripts, but no `scripts:` section in `project.yml`. Scripts have no `@script` headers.

```
┌──────────────────────────────────────────────────────┐
│ 🧩 Scripts                          🟡 3 found   │
│ Automation & code analysis                            │
│                                                      │
│  ● → ○  deploy.py              ops      unmanaged  │
│  ● → ○  report.py              ops      unmanaged  │
│  ● → ○  clean.sh               ops      unmanaged  │
│                                                      │
│  💡 3 scripts found but not managed — limited       │
│     operability. Set up to unlock tracking,         │
│     parameters, and template scripts.               │
│                                                      │
│  [🚀 Full Setup]   [▶ Run Script]                  │
└──────────────────────────────────────────────────────┘
```

Badge: `🟡 3 found` — not red, not green. They exist but aren't fully managed.

### 3.3 State 3: Fully managed

`project.yml` has `scripts:` section. Scripts have `@script` headers. Templates activated.

```
┌──────────────────────────────────────────────────────┐
│ 🧩 Scripts                          🟢 5 ready   │
│ Automation & code analysis                            │
│                                                      │
│  ● → ●  Class Diagrams     generator   template  ▶ │
│  ● → ●  Route Quality      audit       template  ▶ │
│  ● → ●  Code Hygiene       audit       template  ▶ │
│  ● → ●  deploy.py          ops         user      ▶ │
│  ● → ○  clean.sh           ops         user      ▶ │
│                                                      │
│  Coverage: Python 100% · Shell 85%                   │
│  Categories: ✓ generator  ✓ audit  ✓ ops            │
│                                                      │
│  Pipeline: Discover → Configure → Run → Track       │
│  [+ Add Script]  [📋 History]  [🚀 Full Setup]    │
└──────────────────────────────────────────────────────┘
```

#### Coverage Metrics

The card shows **language coverage** — how well each script language is supported:

| Language | Coverage | What full coverage means |
|----------|----------|------------------------|
| Python | 100% | @script header, parameter form, AST analysis, streaming, tracking, output routing |
| Bash/Shell | 85% | @script header parsing, param extraction, execution, streaming, tracking, output routing. Missing: parameter form (M4+). AST N/A. |
| PowerShell | 0% | Planned: M8 |

Coverage % is computed from: `(supported_features / applicable_features) * 100`
Features: header parsing, param extraction, execution, streaming, tracking, output routing, parameter form generation, AST analysis

AST analysis is N/A for shell (no `ast` equivalent). So shell denominator is 7, not 8.

### 3.4 Status Dot Legend

Same pattern as Artifacts:
```
● → ●   Discovered + Configured (fully managed)
● → ○   Discovered + Not yet configured / partial support
```

### 3.5 Source Badges

| Badge | Meaning |
|-------|---------|
| `template` | Shipped with the control plane, from `script_templates/` |
| `user` | User's own script in `scripts/` |
| `override` | User script that overrides a template |

---

## 4. Setup Wizard — The "Drive the User" Experience

### 4.1 Overview

Like the Artifacts wizard (Detect → Evolve → Configure → Apply), the Scripts wizard guides the user from discovery to a fully managed setup.

```
Step 1: DETECT     → Scan for existing scripts + available templates
Step 2: ADOPT      → Choose how to handle each script (full adopt / as-is)
Step 3: CONFIGURE  → Cherry-pick templates, set defaults, preview config
Step 4: APPLY      → Write project.yml, patch scripts if needed, reload
```

### 4.2 Step 1: Detect

```
📡 Scanning project…

Detection Results — Found 3 scripts + 5 templates available

EXISTING SCRIPTS (in scripts/)
┌──────────────────────────────────────────────────────────────┐
│ [✓] deploy.py       Python   🟡 Partial — no @script header │
│     "Deployment automation script"                            │
│     Detected: argparse usage, 3 arguments found              │
│                                                               │
│ [✓] report.py       Python   🟡 Partial — no @script header │
│     "Report generation"                                       │
│     Detected: sys.argv usage, 1 argument found               │
│                                                               │
│ [✓] clean.sh        Shell    🟡 Partial — param form TBD │
│     "Cleanup script"                                          │
│     Detected: 45 lines, executable                           │
└──────────────────────────────────────────────────────────────┘

AVAILABLE TEMPLATES (from control plane)
┌──────────────────────────────────────────────────────────────┐
│ [✓] Class Diagrams   generator   Python   🟢 Ready          │
│     "Generate Mermaid class diagrams from Python codebase"   │
│                                                               │
│ [✓] Route Quality    audit       Python   🟢 Ready          │
│     "Audit Flask routes against quality standards"           │
│                                                               │
│ [✓] Code Hygiene     audit       Python   🟢 Ready          │
│     "Detect __init__ leaks and stale documentation"          │
│                                                               │
│ [ ] (future templates become available as they ship)         │
└──────────────────────────────────────────────────────────────┘

PROJECT STATUS
  scripts/ directory: ✅ exists (3 files)  
  project.yml scripts: section: ❌ not configured
  Template source: ✅ available (5 templates)
```

The wizard scans:
1. `scripts/` directory (configurable root) for any script files (.py, .sh, .bash, .ps1)
2. Each script is analyzed:
   - Python: AST scan for argparse/click usage, docstrings, `@script` header presence
   - Shell: basic analysis (line count, shebang, executable bit)
3. `script_templates/` for available templates
4. `project.yml` for existing `scripts:` configuration

### 4.3 Step 2: Adopt

For each existing script, the user chooses how to onboard it:

```
Adopt Scripts — How should each script be managed?

┌──────────────────────────────────────────────────────────────┐
│ deploy.py (Python)                                            │
│                                                               │
│ ○ Full Adopt — add @script header for full operability       │
│   → Proposed header (auto-generated from argparse analysis): │
│   ┌─────────────────────────────────────────────────────────┐│
│   │ + """                                                    ││
│   │ + @script                                                ││
│   │ + name: Deploy                                           ││
│   │ + category: ops                                          ││
│   │ + mode: interactive                                      ││
│   │ +                                                        ││
│   │ + @param environment: choice = staging [staging, prod]   ││
│   │ + @param dry-run: boolean = true                         ││
│   │ + @param force: boolean = false                          ││
│   │ + """                                                    ││
│   └─────────────────────────────────────────────────────────┘│
│                                                               │
│ ● As-is — run and stream, reduced operability for now        │
│   → Runs without modification                                │
│   → Basic tracking (start/stop/exit code)                    │
│   → No parameter form in UI (manual --args)                  │
│   → Full support coming in future milestone                  │
│                                                               │
│ ○ Skip — don't manage this script                            │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ clean.sh (Shell)                                              │
│                                                               │
│ Current shell support: 85%                                    │
│ Supported: execution, streaming, tracking, output routing,    │
│            @script header parsing, param extraction            │
│ Planned:   auto-generated parameter form                      │
│                                                               │
│ ● As-is — run and stream (header parsing supported, form TBD)│
│ ○ Skip — don't manage this script                            │
└──────────────────────────────────────────────────────────────┘
```

For Python scripts: can auto-generate `@script` headers by analyzing:
- `argparse.ArgumentParser` → extract params
- `click.option` / `click.argument` → extract params
- Module docstring → extract description
- Filename conventions → suggest category

For shell scripts: as-is only for now (no header patching). Full shell support is planned — this is not a dead end, it's a roadmap item.

### 4.4 Step 3: Configure

```
Configure Scripts Integration

TEMPLATE SCRIPTS — Cherry-pick which ones to activate
┌──────────────────────────────────────────────────────────────┐
│ [✓] Class Diagrams    generator   "Mermaid diagrams"         │
│ [✓] Route Quality     audit       "Route compliance check"   │
│ [ ] Code Hygiene      audit       "Init leaks + stale docs"  │
│                                                               │
│ Selected: 2 of 3 templates                                   │
└──────────────────────────────────────────────────────────────┘

DEFAULTS
┌──────────────────────────────────────────────────────────────┐
│ Scripts root:      [scripts/           ]  (default)          │
│ Default output:    [scripts/output/    ]  (default)          │
│ History retention: [50                 ]  runs               │
│ Timeout:           [300                ]  seconds            │
└──────────────────────────────────────────────────────────────┘

PREVIEW — project.yml scripts: section
┌─────────────────────────────────────────────────────────────┐
│ scripts:                                                     │
│   root: scripts/                                             │
│   template_source: src/core/data/script_templates/           │
│   default_output: scripts/output/                            │
│   history:                                                   │
│     max_runs: 50                                             │
│   execution:                                                 │
│     timeout: 300                                             │
│   categories:                                                │
│     - generator                                              │
│     - audit                                                  │
│     - ops                                                    │
└─────────────────────────────────────────────────────────────┘
```

The user can:
- Cherry-pick which template scripts to activate (not all-or-nothing)
- Override defaults (root directory, output directory, history retention)
- Preview the exact YAML that will be written

### 4.5 Step 4: Apply

```
Applying Configuration…

Results

✅ Added scripts: section to project.yml
✅ Activated template: Class Diagrams (generators/class_diagrams.py)
✅ Activated template: Route Quality (audit/route_quality.py)
⏭️ Skipped template: Code Hygiene (not selected)
✅ Adopted: deploy.py (as-is — basic tracking)
✅ Adopted: report.py (full adopt — @script header added)
✅ Adopted: clean.sh (as-is — shell support 85%)

What's next: Close this wizard to see your scripts card.
Use ▶ to run any script, or 📋 History to see past runs.
```

---

## 5. Script Detail / Run Panel

When a user clicks a script in the card (or via a dedicated "Run" UI), they see:

### 5.1 Script Detail View

```
┌──────────────────────────────────────────────────────────────┐
│ Class Diagrams                           generator  template │
│ Generate Mermaid class diagrams from Python codebase         │
│                                                               │
│ Parameters:                                                   │
│ ┌───────────────────────────────────────────────────────────┐│
│ │ Scope:      [core.services.vault    ] (package path)      ││
│ │ Output:     [docs/diagrams/         ] (directory)          ││
│ │ Format:     [mermaid ▼]               (mermaid/json/md)    ││
│ │ Max Depth:  [3                      ] (inheritance depth)  ││
│ │ Private:    [ ] Include private members                    ││
│ └───────────────────────────────────────────────────────────┘│
│                                                               │
│ [▶ Run]   [🧪 Dry Run]   [📋 History (3 runs)]             │
└──────────────────────────────────────────────────────────────┘
```

- Parameter forms are **auto-generated** from `ScriptMeta.parameters` (M1)
- For scripts without `@script` headers: show a text input for raw arguments
- For shell scripts: show a text input for arguments (until header parsing is supported)

### 5.2 Live Output Stream

```
┌──────────────────────────────────────────────────────────────┐
│ ▶ Running: Class Diagrams           run-abc123  ⏱ 0:03      │
│ ─────────────────────────────────────────────────────────────│
│ 📊 Analyzing Python code in /project/src/core/services/vault │
│    Found 8 classes in 5 files                                │
│    Building relationship graph...                            │
│    Generating Mermaid syntax...                              │
│    ✅ Output written to docs/diagrams/vault_classes.md       │
│ ─────────────────────────────────────────────────────────────│
│ ✅ Completed in 2.1s — exit code 0                           │
│                                                               │
│ Output: docs/diagrams/vault_classes.md                       │
│ [📄 View Output]  [🔄 Run Again]  [✕ Close]                │
└──────────────────────────────────────────────────────────────┘
```

Uses SSE streaming via existing `event_bus` infrastructure — same pattern as Artifacts build modal.

---

## 6. CLI Layer — `controlplane scripts ...`

### 6.1 File Layout

```
src/ui/cli/scripts/
├── __init__.py            ← click.group + _resolve_project_root
├── list.py                ← controlplane scripts list [--category] [--source] [--json]
├── run.py                 ← controlplane scripts run <script-id> [--param KEY=VALUE]
├── info.py                ← controlplane scripts info <script-id>
└── history.py             ← controlplane scripts history [--script-id] [--last N]
```

Follows the exact pattern of `src/ui/cli/audit/` — group in `__init__.py`, one file per command.

### 6.2 Commands

| Command | What it does |
|---------|-------------|
| `controlplane scripts list` | List all discovered scripts with metadata |
| `controlplane scripts list --category audit` | Filter by category |
| `controlplane scripts list --json` | JSON output for piping |
| `controlplane scripts run generators/class_diagrams --param scope=core.services.vault` | Run a script with params |
| `controlplane scripts run generators/class_diagrams --dry-run` | Show what would execute |
| `controlplane scripts info generators/class_diagrams` | Full metadata + parameters |
| `controlplane scripts history` | Last 10 runs |
| `controlplane scripts history --script-id generators/class_diagrams --last 5` | Filtered history |

### 6.3 Registration

```python
# src/ui/cli/__init__.py — add scripts group
from .scripts import scripts
cli.add_command(scripts)
```

---

## 7. Web API Layer — `/api/scripts/*`

### 7.1 File Layout

```
src/ui/web/routes/scripts/
├── __init__.py            ← Blueprint definition (scripts_bp)
├── registry.py            ← GET endpoints for script listing and info
├── execution.py           ← POST endpoint for running + SSE for streaming
└── history.py             ← GET endpoints for run history
```

Follows the exact pattern of `src/ui/web/routes/audit/`.

### 7.2 Endpoints

| Method | Path | Module | Purpose |
|--------|------|--------|---------|
| GET | `/api/scripts/list` | registry.py | List all discovered scripts |
| GET | `/api/scripts/info/<script_id>` | registry.py | Script metadata + parameters |
| GET | `/api/scripts/categories` | registry.py | List unique categories |
| GET | `/api/scripts/coverage` | registry.py | Language coverage metrics |
| POST | `/api/scripts/detect` | registry.py | Scan project (for wizard) |
| POST | `/api/scripts/run` | execution.py | Execute a script (returns run_id) |
| GET | `/api/scripts/stream/<run_id>` | execution.py | SSE stream of script output |
| GET | `/api/scripts/status/<run_id>` | execution.py | Run status (poll alternative) |
| POST | `/api/scripts/adopt` | execution.py | Adopt a script (patch headers) |
| GET | `/api/scripts/history` | history.py | List recent script runs |
| GET | `/api/scripts/history/<run_id>` | history.py | Detail for one run |
| GET | `/api/scripts/templates` | registry.py | List available templates |
| POST | `/api/scripts/templates/activate` | registry.py | Activate selected templates |

### 7.3 Blueprint Registration

```python
# src/ui/web/routes/scripts/__init__.py
from flask import Blueprint
scripts_bp = Blueprint("scripts", __name__, url_prefix="/api")

from . import registry    # noqa: E402, F401
from . import execution   # noqa: E402, F401
from . import history     # noqa: E402, F401
```

---

## 8. Admin Panel JS Files

### 8.1 File Layout

```
src/ui/web/templates/scripts/integrations/
├── _scripts.html              ← Card JS: loadScriptsCard(), script rows, actions
├── _scripts_run.html          ← Run modal: parameter form, SSE stream, output view
└── setup/
    └── _scripts.html          ← Setup wizard: Detect → Adopt → Configure → Apply
```

### 8.2 Include Chain

Added to `_integrations.html`:
```javascript
{% include 'scripts/integrations/_scripts.html' %}
{% include 'scripts/integrations/_scripts_run.html' %}
```

Added to setup includes (loaded by wizard modal system):
```javascript
// setup/_scripts.html loaded via openScriptsSetupWizard()
```

---

## 9. Language Coverage Model

### 9.1 Coverage Features

Every script language is measured against these capabilities:

| Feature | Python | Bash/Shell | PowerShell |
|---------|--------|------------|------------|
| Execution (subprocess) | ✅ M1 | ✅ M1 | 🔮 M8 |
| Streaming (stdout/stderr) | ✅ M1 | ✅ M1 | 🔮 M8 |
| Tracking (run record) | ✅ M1 | ✅ M1 | 🔮 M8 |
| Output routing | ✅ M1 | ✅ M1 | 🔮 M8 |
| @script header parsing | ✅ M1 | ✅ M1 | 🔮 M8 |
| Parameter extraction | ✅ M1 | ✅ M1 | 🔮 M8 |
| Parameter form generation | ✅ M4 | 🔮 M4+ | 🔮 M8 |
| AST analysis | ✅ M2 | N/A | N/A |

### 9.2 Coverage Calculation

```
coverage = supported_features / applicable_features * 100

Python:     8/8 = 100%
Bash/Shell: 6/7 =  86% → displayed as "85%" (rounded)
PowerShell: 0/7 =   0% → displayed as "Planned"
```

AST analysis is N/A for shell (no equivalent), so it's not counted against coverage.
Parameter form generation for shell is listed as M4+ — the params ARE extracted in M1, but the form auto-generation in the UI needs a shell-to-form adapter that may ship with M4 or shortly after.

### 9.3 What This Means in Practice

| Coverage Level | User Experience |
|----------------|----------------|
| 100% | Full parameter form, auto-generated UI, history, reports |
| 50-70% | Can run and stream, basic tracking, manual --args in UI |
| 0% | Planned — shown in roadmap, not yet executable |

**"85% is not second-class"**: An 85% shell script runs, streams, tracks, and has its header parsed with params extracted. The user just types arguments manually in the UI instead of getting an auto-generated form. That's a UX limitation, not a functionality limitation.

---

## 10. File Inventory

### 10.1 New Files

| File | Lines (est.) | Purpose | Depends on |
|------|-------------|---------|-----------|
| **CLI** | | | |
| `src/ui/cli/scripts/__init__.py` | ~35 | click.group + helpers | — |
| `src/ui/cli/scripts/list.py` | ~80 | List scripts command | M1 registry |
| `src/ui/cli/scripts/run.py` | ~100 | Run script command | M1 executor |
| `src/ui/cli/scripts/info.py` | ~50 | Script info command | M1 registry |
| `src/ui/cli/scripts/history.py` | ~60 | Script history command | M1 tracker |
| **Web API** | | | |
| `src/ui/web/routes/scripts/__init__.py` | ~20 | Blueprint definition | — |
| `src/ui/web/routes/scripts/registry.py` | ~120 | List + info + detect + templates | M1 registry |
| `src/ui/web/routes/scripts/execution.py` | ~130 | Run + stream + adopt | M1 executor |
| `src/ui/web/routes/scripts/history.py` | ~60 | History endpoints | M1 tracker |
| **Admin Panel** | | | |
| `templates/scripts/integrations/_scripts.html` | ~200 | Card JS + loadScriptsCard() | API |
| `templates/scripts/integrations/_scripts_run.html` | ~250 | Run modal + SSE stream | API |
| `templates/scripts/integrations/setup/_scripts.html` | ~500 | Setup wizard (4 steps) | API |

**Total new code**: ~1,605 lines across 12 files

### 10.2 Modified Files

| File | Change |
|------|--------|
| `src/ui/cli/__init__.py` | Register `scripts` group (~2 lines) |
| Main app factory | Register `scripts_bp` blueprint (~2 lines) |
| `_tab_integrations.html` | Add Scripts card HTML (~18 lines, after Terraform) |
| `_init.html` | Add `'int:scripts'` to `_INT_CARDS` (~1 line) |
| `_integrations.html` | Add `{% include %}` for scripts JS files (~2 lines) |
| `setup/_dispatch.html` | Add `scripts: openScriptsSetupWizard` (~1 line) |

---

## 11. Orthogonality

| Interface touched | M4 creates | M1 provides | M2/M3 provide |
|-------------------|-----------|-------------|---------------|
| Integrations card | Card HTML + JS | `_wizard_scripts_status()` | Nothing |
| Setup wizard | 4-step wizard | registry, config, executor | Nothing |
| CLI list/run | Thin click wrappers | `discover_scripts`, `execute_script` | Nothing |
| API list/run | Flask routes | Same service functions | Nothing |
| Run modal + SSE | JS + SSE handler | `event_bus` integration | Nothing |
| History | Ledger query | `run_tracker` with type="script" | Nothing |

M4 has **zero dependency on M2 or M3**. It depends only on M1. The card will show template scripts as available even before M2/M3 code exists — they just won't be runnable until M2+M3 ship the actual script files.
