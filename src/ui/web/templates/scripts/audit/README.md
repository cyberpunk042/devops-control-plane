# Audit — Front-End Scripts

> **6 files · 1,385 lines · The entire Audit tab.**
>
> This domain owns the Audit tab — a multi-level code analysis
> dashboard that surfaces system profile, dependencies, structure,
> clients, code health, repo health, security risks, and import
> graphs. It uses a tiered L0/L1/L2 model where lightweight scans
> load instantly and deep analysis runs on-demand.

---

## How It Works

### Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│ dashboard.html                                                      │
│                                                                      │
│  {% include 'partials/_tab_audit.html' %}                ← HTML     │
│  {% include 'scripts/audit/_audit.html' %}               ← JS      │
│                                                                      │
│  _audit.html is the LOADER — it wraps a single <script> scope      │
│  and includes all 5 modules so they share state.                    │
└────────────────────────────────────────────────────────────────────┘
```

### Module Loading Order

```
_audit.html                  ← Loader (23 lines)
    │
    ├── _init.html            ← Shared state, helpers, card registry, tab load
    ├── _scores.html          ← Master L0/L1/L2 score rendering + sparklines
    ├── _cards_a.html         ← Cards: System Profile, Dependencies, Structure, Clients
    ├── _cards_b.html         ← Cards: Code Health, Repo Health, Risks, Import Graph
    └── _modals.html          ← Drill-down modals, batch dismiss, filters
```

All modules share a single `<script>` scope. State flows from
`_init.html` to the card renderers, and drill-down data is stored
on `window._auditData` for modal access.

### Analysis Tier Model

The audit system uses a **three-tier analysis model**:

```
┌─────────────────────────────────────────────────────────────────┐
│  L0 — Structural Detection (fast, always-on)                     │
│  System profile, folder structure, manifest parsing, tool check  │
├─────────────────────────────────────────────────────────────────┤
│  L1 — Dependency & Client Analysis (auto-loaded)                 │
│  Dependency classification, framework detection, service clients │
├─────────────────────────────────────────────────────────────────┤
│  L2 — Deep Analysis (on-demand, button-triggered)                │
│  Code health, repo health, security risks, import graph          │
│  Cached results auto-load on revisit                             │
└─────────────────────────────────────────────────────────────────┘
```

| Tier | Cards | Load Strategy |
|------|-------|---------------|
| **L0 + L1** | Scores, System, Deps, Structure, Clients | Parallel auto-load via `_AUDIT_CARDS` |
| **L2** | Code Health, Repo Health, Risks, Import Graph | Manual trigger button; auto-load if cached |

### Tab Load Lifecycle

```
loadAuditTab(force)                      ← called by _tabs.html on tab switch
    │
    ├── force=true? → bust caches:
    │     ├── cardInvalidate() each L0/L1 card
    │     ├── Clear _store[key] (SSE cache)
    │     ├── Reset badge + detail spinners
    │     └── POST /api/devops/cache/bust { card: 'audit' }
    │
    ├── Guard: if _auditLoaded, return
    │
    ├── Load all L0/L1 cards in parallel:
    │     Promise.all([
    │       loadAuditScores(),
    │       loadAuditSystemCard(),
    │       loadAuditDepsCard(),
    │       loadAuditStructureCard(),
    │       loadAuditClientsCard()
    │     ])
    │
    ├── _autoLoadL2Cards()
    │     └── For each L2 card: if cardCached(key), load silently
    │
    └── _auditLoaded = true
```

### Card Loading Pattern

Every card follows the same loading contract:

```javascript
async function loadAudit[X]Card() {
    const detail = document.getElementById('audit-[x]-detail');
    const badge  = document.getElementById('audit-[x]-badge');
    const data   = await cardLoad('audit:[x]', '/audit/[x]', badge, detail);
    if (!data) return;
    // ... render HTML into detail, update badge text + class
}
```

`cardLoad()` (from `globals/_cards.html`) handles caching,
spinner display, and error states. The card function only
handles rendering.

### Score System

Two master scores (0–10 scale) with trend tracking:

```
┌──────────────────┐  ┌──────────────────┐
│ 📊 Complexity    │  │ ⭐ Quality       │
│ Score: 7.2/10    │  │ Score: 6.8/10    │
│ ▼ improving      │  │ ▲ declining      │
│                  │  │                  │
│ [breakdown bars] │  │ [breakdown bars] │
└──────────────────┘  └──────────────────┘
         📈 Score History (sparkline)
```

| Field | Source |
|-------|--------|
| `complexity.score` | Weighted sum of sub-dimensions |
| `quality.score` | Weighted sum of sub-dimensions |
| `trend.complexity_trend` | `improving` / `declining` / `stable` |
| `trend.quality_trend` | Same |
| `history[]` | Array of past snapshots → SVG sparkline |

Enriched mode (`loadAuditScoresEnriched()`) replaces the standard
scores with L2-enhanced data from `/api/audit/scores?enriched=true`.

---

## File Map

```
audit/
├── _audit.html       Loader — includes all modules (23 lines)
├── _init.html        State, helpers, card registry, tab load (112 lines)
├── _scores.html      Master scores, breakdown bars, sparkline (175 lines)
├── _cards_a.html     System Profile, Dependencies, Structure, Clients (357 lines)
├── _cards_b.html     Code Health, Repo Health, Risks, Import Graph (412 lines)
├── _modals.html      Drill-down modals, dismiss, filters (306 lines)
└── README.md         This file
```

---

## Per-File Documentation

### `_audit.html` — Loader (23 lines)

Pure Jinja2 include orchestrator. No logic.

### `_init.html` — State & Tab Orchestrator (112 lines)

Compact init module — defines state, helpers, card registry,
and the main `loadAuditTab()` function.

**State:**

| Variable | Type | Purpose |
|----------|------|---------|
| `_auditLoaded` | `boolean` | Guard against duplicate tab loads |
| `window._auditData` | `Object` | Shared data store for modal drill-downs |

**Helpers:**

| Function | What It Does |
|----------|-------------|
| `_auditFileLink(filePath, line)` | Render a clickable file link (navigates to Content Vault preview) |
| `_auditNavToFile(path, line)` | Close audit modal + open file in editor |
| `_auditModal(title, bodyHtml, width)` | Render a custom modal overlay (Esc to close) |

**Card registry (`_AUDIT_CARDS`):**

| Key | Load Function | What It Shows |
|-----|--------------|---------------|
| `audit:scores` | `loadAuditScores()` | Master complexity + quality scores |
| `audit:system` | `loadAuditSystemCard()` | System profile, tools, modules |
| `audit:deps` | `loadAuditDepsCard()` | Dependencies, frameworks, crossovers |
| `audit:structure` | `loadAuditStructureCard()` | Components, infrastructure flags, layers |
| `audit:clients` | `loadAuditClientsCard()` | External service clients by type |

**Tab orchestrator:**

| Function | What It Does |
|----------|-------------|
| `loadAuditTab(force)` | Main orchestrator — bust caches on force, parallel-load all L0/L1, auto-load cached L2 |
| `_autoLoadL2Cards()` | Check L2 cache; if warm, load silently |

### `_scores.html` — Master Scores (175 lines)

| Function | What It Does |
|----------|-------------|
| `loadAuditScores()` | Fetch `/audit/scores` via `cardLoad()`, render UI |
| `loadAuditScoresEnriched()` | Fetch `/audit/scores?enriched=true` for L2-enhanced scores |
| `_renderScoresUI(data, detail, badge)` | Render complexity + quality cards with breakdown bars |
| `_renderBreakdown(breakdown)` | Render per-dimension progress bars with weight percentages |
| `_renderSparkline(history)` | SVG dual-line sparkline (complexity + quality over time) |

### `_cards_a.html` — L0/L1 Analysis Cards (357 lines)

**System Profile Card:**

| Function | API | Renders |
|----------|-----|---------|
| `loadAuditSystemCard()` | `GET /audit/system` | Python version, OS, container detection, systemd, OpenSSL, available/missing tools, language modules, dependency manifests |

Missing tool tags include an install button that delegates to
`_auditShowMissingTool()` in `_modals.html`.

**Dependencies & Libraries Card:**

| Function | API | Renders |
|----------|-----|---------|
| `loadAuditDepsCard()` | `GET /audit/dependencies` | Total/classified counts, category chart, framework tags, ORM detection, cross-ecosystem patterns, expandable full dependency table |

Category tags are clickable — they invoke `_auditFilterDeps(cat)`
to filter the dependency table.

**Structure & Modules Card:**

| Function | API | Renders |
|----------|-----|---------|
| `loadAuditStructureCard()` | `GET /audit/structure` | Component list with type icons, infrastructure flags (Docker, IaC, CI, Tests, Docs), layer architecture (if detected) |

**Clients & Services Card:**

| Function | API | Renders |
|----------|-----|---------|
| `loadAuditClientsCard()` | `GET /audit/clients` | External service clients grouped by type (API, database, driver, search, payment, email, etc.) with icons and file locations |

### `_cards_b.html` — L2 Deep Analysis Cards (412 lines)

All L2 cards are **on-demand** — they show a trigger button until
the user clicks it or the data is already cached.

**Code Health Card:**

| Function | API | Renders |
|----------|-----|---------|
| `loadAuditHealthCard()` | `GET /audit/health` | Overall health score, dimension scores, hotspots (critical/warning/info), naming consistency |

Hotspots are stored in `window._auditHotspots` for modal drill-down.

**Repo Health Card:**

| Function | API | Renders |
|----------|-----|---------|
| `loadAuditRepoCard()` | `GET /audit/repo` | Git health score, dimension breakdown, object stats, commit history, large files |

**Risks & Issues Card:**

| Function | API | Renders |
|----------|-----|---------|
| `loadAuditRisksCard()` | `GET /audit/risks` | Security grade (A–F), risk score, category breakdown, findings list with severity, inline file previews, action items |

Findings are stored in `window._auditFindings` for modal drill-down.
Each finding shows a summary with up to 3 file previews and a
"drill-down ▸" link.

**Import Graph & Coupling Card:**

| Function | API | Renders |
|----------|-----|---------|
| `loadAuditL2StructureCard()` | `GET /audit/structure?l2=true` | File/line/import/module counts, cross-module dependencies (top 10 with strength), module boundary table, library usage |

Cross-module dependencies are stored in `window._auditData.crossDeps`.

### `_modals.html` — Drill-Down Modals (306 lines)

| Function | What It Does |
|----------|-------------|
| `_auditShowCrossDep(idx)` | Show cross-module dependency details with file list |
| `_auditShowMissingTool(toolId)` | Delegate to `installWithPlan()` for tool installation |
| `_auditInstallTool(toolId, cli, ...)` | Direct install flow with sudo support + log output |
| `_auditShowFinding(finding)` | Full finding modal: severity, description, recommendation, affected files/packages with registry links |
| `_auditToggleSelectAll(checked)` | Select/deselect all dismiss checkboxes |
| `_auditUpdateDismissCount()` | Update batch dismiss button label with count |
| `_auditDismissSelected()` | POST `/audit/dismiss` with comment → invalidate + reload risks card |
| `_auditShowHotspotModal(hotspots)` | Show all hotspots in a scrollable modal |
| `_auditFilterDeps(cat)` | Toggle category filter on dependency table rows |

**Finding drill-down anatomy:**

```
┌──────────────────────────────────────────────┐
│ ⚠️ Finding Title                         ✕  │
├──────────────────────────────────────────────┤
│ Description text                             │
│                                              │
│ 💡 Recommendation                            │
│ Fix text                                     │
│                                              │
│ 📍 Affected Files (or 📦 Affected Packages) │
│ ☐ file.py:42  pattern                       │
│ ☐ other.py:17 pattern                       │
│                                              │
│ ☑ Select All                                │
│ [🚫 Dismiss 2 selected]                     │
│ ┌─────────────────────────────────────┐     │
│ │ Comment: __________________________ │     │
│ └─────────────────────────────────────┘     │
│                                              │
│ Severity: medium    Source: bandit            │
└──────────────────────────────────────────────┘
```

Package entries show registry links (PyPI, npm, crates.io, pkg.go.dev).
File entries get checkboxes for batch dismiss with `# nosec` comment.

---

## Dependency Graph

### Internal Dependencies

```
_init.html              ← standalone, defines all shared state + helpers
    ↑
_scores.html            ← uses cardLoad, cardStore from globals/_cards.html
    ↑
_cards_a.html           ← uses cardLoad, _auditFileLink, _auditModal
    ↑
_cards_b.html           ← uses cardLoad, _auditFileLink, window._auditData
    ↑
_modals.html            ← uses _auditModal, _auditFileLink, _auditNavToFile,
                           window._auditFindings, window._auditHotspots,
                           window._auditData.crossDeps
```

### External Dependencies

```
globals/_api.html        ← api(), esc(), toast()
globals/_cache.html      ← cardLoad(), cardStore(), cardCached(),
                           cardInvalidate(), cardRefresh(), openFileInEditor()
globals/_ops_modal.html  ← installWithPlan() (missing tool install)
_tabs.html               ← tab switch integration
Content Vault            ← openFileInEditor() (defined in globals/_cache.html)
```

---

## Consumers

### Tab Loading

| File | How |
|------|------|
| `dashboard.html` | `{% include 'partials/_tab_audit.html' %}` (HTML) + `{% include 'scripts/audit/_audit.html' %}` (JS) |
| `_tabs.html` (line 86) | `loadAuditTab()` — called on tab switch |
| `_auth_modal.html` (line 810) | `loadAuditTab(true)` — force-reload after auth changes |

### API Endpoints Used

| Endpoint | Used By | Purpose |
|----------|---------|---------|
| `GET /api/audit/scores` | `_scores.html` | Master complexity + quality scores |
| `GET /api/audit/scores?enriched=true` | `_scores.html` | L2-enriched scores |
| `GET /api/audit/system` | `_cards_a.html` | System profile + tools |
| `GET /api/audit/dependencies` | `_cards_a.html` | Dependency + framework analysis |
| `GET /api/audit/structure` | `_cards_a.html` | Component + infrastructure detection |
| `GET /api/audit/structure?l2=true` | `_cards_b.html` | Import graph + coupling |
| `GET /api/audit/clients` | `_cards_a.html` | External service clients |
| `GET /api/audit/code-health` | `_cards_b.html` | Code health analysis |
| `GET /api/audit/repo` | `_cards_b.html` | Git repo health |
| `GET /api/audit/risks` | `_cards_b.html` | Security findings + risks |
| `POST /api/audit/install-tool` | `_modals.html` | Install missing system tool |
| `POST /api/devops/audit/dismissals` | `_modals.html` | Dismiss finding (adds `# nosec`) |
| `POST /api/devops/cache/bust` | `_init.html` | Bust server-side audit cache |

---

## Design Decisions

### Why split cards into `_cards_a.html` and `_cards_b.html`?

The split follows the **tier boundary**: `_cards_a.html` contains
L0/L1 cards that auto-load on tab switch (System, Deps, Structure,
Clients). `_cards_b.html` contains L2 cards that require manual
trigger or cached data (Code Health, Repo Health, Risks, Import
Graph). This makes the performance contract visible in the file
structure — everything in `_cards_a` is fast and safe to auto-load.

### Why an L0/L1/L2 tier model?

Deep analysis (L2) is expensive — it requires scanning all files,
parsing imports, running security tools. If all analysis ran on
every tab switch, the UI would freeze. The tier model lets L0/L1
load in milliseconds while L2 runs only when the user explicitly
requests it. Once L2 data is cached, it auto-loads on revisit
via `_autoLoadL2Cards()`.

### Why store drill-down data on `window.*`?

Modal drill-downs need access to the full data (findings, hotspots,
cross-module dependencies) but are rendered lazily when the user
clicks. Storing data on `window._auditFindings`, `window._auditHotspots`,
and `window._auditData` avoids re-fetching and keeps the modal
rendering synchronous for instant response.

### Why does batch dismiss add `# nosec` comments?

The dismiss flow writes `# nosec` inline comments directly into
the source file at the flagged line. This is the standard suppression
mechanism for security scanners like Bandit and Semgrep — they skip
lines marked with `# nosec`. This means dismissals persist across
re-scans without needing a separate suppression config file, and
they're visible in code review.

### Why does `_auditModal()` bypass `modalOpen()` from globals?

Audit modals have unique requirements: they need `overflow-y:auto`
for long finding lists, custom widths per modal type, and Escape key
handling. The audit-specific `_auditModal()` provides a lighter-weight
overlay without wizard infrastructure (no steps, no assistant panel).
This avoids pulling in wizard CSS and keeps audit modals fast.

### Why does missing tool install use `installWithPlan()`?

Tool installation (e.g., installing `bandit` or `semgrep`) uses the
shared plan-based install flow from `globals/_install.html` rather
than a custom install UI. This ensures consistent UX across the
application — the same install modal pattern used for Docker, K8s
tools, etc. After installation, the system card refreshes via
`cardRefresh()` to update the tool availability display.

### Why does force-reload POST `/api/devops/cache/bust` before re-fetching?

The audit backend caches analysis results aggressively because
analysis is expensive. Without busting the server-side cache first,
a force-reload from the UI would just get the same cached data.
The `POST /api/devops/cache/bust { card: 'audit' }` tells the server
to invalidate its cache AND start a background recompute, so the
subsequent `cardLoad()` calls get fresh results.

### Why parallel-load all L0/L1 cards?

The 5 L0/L1 cards (`scores`, `system`, `deps`, `structure`, `clients`)
are independent — they hit different API endpoints with no data
dependencies between them. Loading them sequentially would take 5×
the latency. `Promise.all()` fires all 5 in parallel, so the tab
renders in the time of the slowest single API call rather than the
sum of all five. L2 cards are excluded from this batch because they
are expensive and user-triggered.

---

## Advanced Feature Showcase

> Complex patterns and non-obvious techniques found in the Audit
> front-end source code, with real code examples.

---

### 1. Tiered Card Registry with Parallel Load + L2 Auto-Warm

**File:** `_init.html` · **Lines 56–110**

The card registry defines L0/L1 cards as metadata objects, then
loads them all in parallel. L2 cards are checked for cached data
and silently warm-loaded if available.

```javascript
// _init.html lines 56–62 — card registry
const _AUDIT_CARDS = {
    'audit:scores':    { loadFn: () => loadAuditScores(),       badgeId: 'audit-scores-badge',    detailId: 'audit-scores-detail' },
    'audit:system':    { loadFn: () => loadAuditSystemCard(),   badgeId: 'audit-system-badge',    detailId: 'audit-system-detail' },
    'audit:deps':      { loadFn: () => loadAuditDepsCard(),     badgeId: 'audit-deps-badge',      detailId: 'audit-deps-detail' },
    'audit:structure': { loadFn: () => loadAuditStructureCard(), badgeId: 'audit-structure-badge', detailId: 'audit-structure-detail' },
    'audit:clients':   { loadFn: () => loadAuditClientsCard(),  badgeId: 'audit-clients-badge',   detailId: 'audit-clients-detail' },
};

// _init.html lines 88–94 — parallel load + L2 auto-warm
await Promise.all(Object.values(_AUDIT_CARDS).map(meta => meta.loadFn()));

// Auto-load L2 cards that are already cached
_autoLoadL2Cards();
_auditLoaded = true;

// _init.html lines 98–110 — L2 auto-warm logic
async function _autoLoadL2Cards() {
    for (const [key, fn] of [
        ['audit:l2:quality', loadAuditHealthCard],
        ['audit:l2:repo', loadAuditRepoCard],
        ['audit:l2:risks', loadAuditRisksCard],
        ['audit:l2:structure', loadAuditL2StructureCard],
    ]) {
        if (cardCached(key)) {
            fn();
        }
    }
}
```

**Why it matters:** The two-tier strategy means L0/L1 cards render
in milliseconds (the tab feels instant), while L2 cards skip their
expensive analysis unless the user explicitly triggers them — or
a previous session already cached the results, in which case they
load silently without any button click. The `force` path also
shows server-side cache busting: it POSTs to `/devops/cache/bust`
and awaits the response before re-fetching, ensuring the server's
background recompute thread starts first.

---

### 2. SVG Dual-Line Sparkline Generation

**File:** `_scores.html` · **Lines 141–173**

A pure-JS SVG sparkline renderer that draws two trend lines
(complexity + quality) from historical snapshot data.

```javascript
// _scores.html lines 141–173
function _renderSparkline(history) {
    if (!history || history.length < 2) return '';
    const max = 10;
    const width = Math.min(history.length * 12, 240);
    const height = 32;
    const padding = 2;

    const cxPoints = history.map((h, i) => {
        const x = padding + (i / (history.length - 1)) * (width - padding * 2);
        const y = height - padding - (h.complexity / max) * (height - padding * 2);
        return `${x},${y}`;
    }).join(' ');

    const quPoints = history.map((h, i) => {
        const x = padding + (i / (history.length - 1)) * (width - padding * 2);
        const y = height - padding - (h.quality / max) * (height - padding * 2);
        return `${x},${y}`;
    }).join(' ');

    return `
        <div style="display:flex;align-items:center;gap:var(--space-md)">
            <span style="font-size:0.72rem;color:var(--text-muted)">📈 Score History (${history.length} snapshots)</span>
            <svg width="${width}" height="${height}" style="flex-shrink:0">
                <polyline points="${cxPoints}" fill="none" stroke="var(--warning)" stroke-width="1.5" opacity="0.7"/>
                <polyline points="${quPoints}" fill="none" stroke="var(--success)" stroke-width="1.5" opacity="0.7"/>
            </svg>
            <span style="font-size:0.64rem;color:var(--text-muted)">
                <span style="color:var(--warning)">━</span> complexity
                <span style="color:var(--success);margin-left:6px">━</span> quality
            </span>
        </div>
    `;
}
```

**Why it matters:** No charting library — the sparkline is built
from raw SVG `<polyline>` elements. The width scales dynamically
with the number of snapshots (`history.length * 12`, capped at
`240px`), and the Y-axis is normalized to the 0–10 score range.
Both lines share the same coordinate system, making it easy to
see when complexity and quality diverge or converge over time.

---

### 3. Score Dashboard with Breakdown Bars + Trend Arrows

**File:** `_scores.html` · **Lines 43–113**

The score renderer builds a two-column dashboard with animated
progress bars, per-dimension breakdowns with weight percentages,
and trend arrows with delta values.

```javascript
// _scores.html lines 56–65 — color coding + trend system
const cxColor = cxScore <= 3 ? 'var(--success)' : cxScore <= 6 ? 'var(--warning)' : 'var(--danger)';
const quColor = quScore >= 7 ? 'var(--success)' : quScore >= 4 ? 'var(--warning)' : 'var(--danger)';

const trendIcon = (t, delta) => {
    if (t === 'up') return `<span style="color:var(--success)">▲ +${delta}</span>`;
    if (t === 'down') return `<span style="color:var(--danger)">▼ ${delta}</span>`;
    if (t === 'stable') return `<span style="color:var(--text-muted)">● stable</span>`;
    return '<span style="color:var(--text-muted)">○ first run</span>';
};

// _scores.html lines 116–138 — per-dimension breakdown bars
function _renderBreakdown(breakdown) {
    if (!breakdown) return '';
    let rows = '';
    for (const [key, item] of Object.entries(breakdown)) {
        const label = key.replace(/_/g, ' ');
        const score = item.score ?? 0;
        const pct = Math.round(score * 10);
        const weightPct = Math.round((item.weight || 0) * 100);
        const color = score >= 7 ? 'var(--success)' : score >= 4 ? 'var(--warning)' : 'var(--danger)';
        const sourceTag = item.source ? `<span style="color:#6366f1">${item.source}</span>` : '';
        rows += `
            <div style="display:flex;align-items:center;gap:var(--space-sm)">
                <span style="width:110px;text-transform:capitalize">${label}${sourceTag}</span>
                <div style="flex:1;height:6px;background:var(--bg-primary);border-radius:3px;overflow:hidden">
                    <div style="width:${pct}%;height:100%;background:${color};transition:width 0.4s"></div>
                </div>
                <span style="font-weight:600;color:${color}">${score}</span>
                <span style="color:var(--text-muted);font-size:0.68rem">${weightPct}%</span>
            </div>`;
    }
    return rows;
}
```

**Why it matters:** The color semantics are **inverted** between
complexity (lower = better, green) and quality (higher = better,
green). The breakdown bars show both the absolute score AND the
weight percentage, so users can see which dimensions contribute
most to their overall score. The enrichment tag differentiates
"L0+L1 only" from "L2 enriched" so users know what depth of
analysis produced the scores.

---

### 4. Multi-Registry Package Link Resolution

**File:** `_modals.html` · **Lines 137–160**

The finding modal dynamically generates registry links for
affected packages based on the package manager ecosystem.

```javascript
// _modals.html lines 137–160
if (af.kind === 'package') {
    const mgr = af.manager || 'pip';
    let pkgUrl = '';
    let registryLabel = '';
    if (mgr === 'pip') {
        pkgUrl = `https://pypi.org/project/${encodeURIComponent(af.file)}/`;
        registryLabel = 'PyPI';
    } else if (mgr === 'npm') {
        pkgUrl = `https://www.npmjs.com/package/${encodeURIComponent(af.file)}`;
        registryLabel = 'npm';
    } else if (mgr === 'cargo') {
        pkgUrl = `https://crates.io/crates/${encodeURIComponent(af.file)}`;
        registryLabel = 'crates.io';
    } else if (mgr === 'go') {
        pkgUrl = `https://pkg.go.dev/${encodeURIComponent(af.file)}`;
        registryLabel = 'pkg.go.dev';
    }

    body += `<div style="...">
        <strong>${esc(af.file)}</strong>
        ${af.pattern ? `<span>${esc(af.pattern)}</span>` : ''}
        ${pkgUrl ? `<a href="${pkgUrl}" target="_blank">${registryLabel} ↗</a>` : ''}
    </div>`;
}
```

**Why it matters:** When audit findings flag a package-level issue
(e.g., a known CVE in a dependency), the modal renders clickable
links to the appropriate registry (PyPI, npm, crates.io, pkg.go.dev).
The `encodeURIComponent` handles package names with special characters.
This is distinct from file-level findings, which get checkboxes for
batch dismiss instead of registry links.

---

### 5. Batch Dismiss with `# nosec` Injection

**File:** `_modals.html` · **Lines 172–255**

The dismiss flow lets users select multiple file:line findings,
enter a reason, and POST to the backend which injects `# nosec`
comments directly into the source code.

```javascript
// _modals.html lines 172–188 — dismiss UI with select all + reason input
const hasDismissable = f.files.some(af => af.kind !== 'package' && af.line);
if (hasDismissable) {
    body += `
    <div>
        <label>
            <input type="checkbox" id="audit-dismiss-select-all"
                   onchange="_auditToggleSelectAll(this.checked)">
            Select all
        </label>
        <span id="audit-dismiss-count">0 selected</span>
        <input type="text" id="audit-dismiss-reason"
               placeholder="Reason… (e.g. test fixture, example data)">
        <button id="audit-dismiss-batch-btn" disabled
                onclick="_auditDismissSelected()">🚫 Dismiss selected</button>
        <span>adds <code># nosec</code> to each line</span>
    </div>`;
}

// _modals.html lines 227–255 — dismiss action
async function _auditDismissSelected() {
    const checks = document.querySelectorAll('.audit-dismiss-check:checked');
    if (!checks.length) return;

    const items = Array.from(checks).map(cb => ({
        file: cb.dataset.file,
        line: parseInt(cb.dataset.line),
    }));
    const comment = (document.getElementById('audit-dismiss-reason') || {}).value || '';

    const btn = document.getElementById('audit-dismiss-batch-btn');
    if (btn) { btn.disabled = true; btn.textContent = `⏳ Writing # nosec to ${items.length} line(s)…`; }

    await api('/devops/audit/dismissals', {
        method: 'POST',
        body: JSON.stringify({ items, comment }),
    });
    toast(`# nosec added to ${items.length} line(s)`, 'success');
    // Invalidate and reload the risks card to reflect the change
    cardInvalidate('audit:l2:risks');
    loadAuditRisksCard();
}
```

**Why it matters:** The dismiss mechanism writes suppressions
**into the source code** (not a separate config file), meaning
they survive re-scans and are visible in code review. The button
label dynamically updates with the selection count, and the
`_auditUpdateDismissCount()` helper tracks the select-all checkbox
state for tri-state behavior. After dismiss, only the risks card
is reloaded — not the entire tab — because the server-side cache
for that specific card is already invalidated by the dismiss route.

---

### 6. Security Grade System with Inline File Previews

**File:** `_cards_b.html` · **Lines 191–302**

The risks card renders a letter-grade posture (A–F), severity
breakdown, and per-finding cards with inline file previews
(up to 3 files shown, with a "…and N more" overflow).

```javascript
// _cards_b.html lines 210–225 — grade rendering with color map
const grade = posture.grade || '?';
const gradeColor = {
    'A':'var(--success)', 'B':'#22d3ee', 'C':'var(--warning)',
    'D':'#f97316', 'F':'var(--danger)'
}[grade] || 'var(--text-muted)';

html += `<div style="display:flex;align-items:center;gap:var(--space-md);...">
    <div style="font-size:2.2rem;font-weight:800;color:${gradeColor}">${grade}</div>
    <div>
        <div>Risk Posture: ${score}/10</div>
        <div>${summary.total || 0} findings — ${summary.critical} critical, ...</div>
    </div>
    <div style="height:8px;width:80px;...">
        <div style="width:${Math.round(score*10)}%;background:${scoreColor}"></div>
    </div>
</div>`;

// _cards_b.html lines 249–281 — per-finding inline preview
for (let idx = 0; idx < findings.length; idx++) {
    const f = findings[idx];
    // Build inline detail: show actual file/package data
    if (f.files && f.files.length) {
        const preview = f.files.slice(0, 3);
        for (const af of preview) {
            if (af.pattern && af.pattern.includes('→')) {
                fileParts += `<div><strong>${esc(af.file)}</strong> ${esc(af.pattern)}</div>`;
            } else if (af.line) {
                fileParts += `<div>${_auditFileLink(af.file, af.line)} ${esc(af.pattern)}</div>`;
            }
        }
        if (f.files.length > 3) {
            fileParts += `<div>…and ${f.files.length - 3} more</div>`;
        }
    }
    // Click-to-drill handler stores finding index for modal access
    html += `<div onclick='_auditShowFinding(window._auditFindings[${idx}])'>
        ${sevIcons[f.severity]} <strong>${f.title}</strong>
        ${inlineDetail}
    </div>`;
}
window._auditFindings = findings;
```

**Why it matters:** The inline preview pattern shows just enough
file context (up to 3 files with their line numbers and patterns)
so the user can assess severity without opening the drill-down modal.
Clickable file links route through `_auditFileLink()` which opens
the Content Vault file previewer. The `window._auditFindings` store
avoids re-serializing the array — the click handler passes the index
directly, and the modal reads the original object.

---

### 7. Toggle-Filter Category Pills with Table Sync

**File:** `_modals.html` lines 273–306 · `_cards_a.html` lines 131–148

The dependency card renders clickable category pills that filter
the full dependency table. The filter operates as a toggle —
click once to filter, click again to clear.

```javascript
// _cards_a.html lines 131–148 — color-coded category pills
const catColors = {
    framework: '#6366f1', orm: '#8b5cf6', client: '#ec4899', database: '#f43f5e',
    testing: '#22c55e', devtool: '#06b6d4', security: '#f59e0b', http: '#3b82f6',
    serialization: '#a855f7', cli: '#14b8a6', logging: '#84cc16', utility: '#64748b',
};
for (const [cat, count] of Object.entries(categories).sort((a,b) => b[1] - a[1])) {
    const color = catColors[cat] || '#64748b';
    html += `<span style="background:${color}22;color:${color};border:1px solid ${color}44;cursor:pointer"
                   data-audit-cat="${cat}"
                   onclick="_auditFilterDeps('${cat}')">
        <span style="width:8px;height:8px;border-radius:50%;background:${color}"></span>
        ${cat} (${count})
    </span>`;
}

// _modals.html lines 273–306 — toggle filter logic
let _auditDepFilter = null;

function _auditFilterDeps(cat) {
    const table = document.getElementById('audit-deps-table');
    if (!table) return;

    // Toggle: click same category → clear filter
    if (_auditDepFilter === cat) {
        _auditDepFilter = null;
    } else {
        _auditDepFilter = cat;
    }

    // Dim non-matching pills
    document.querySelectorAll('[data-audit-cat]').forEach(pill => {
        pill.style.opacity = !_auditDepFilter || pill.dataset.auditCat === _auditDepFilter ? '1' : '0.35';
    });

    // Show/hide table rows by data-dep-cat attribute
    const rows = table.querySelectorAll('tbody tr');
    for (const row of rows) {
        row.style.display = !_auditDepFilter || row.dataset.depCat === _auditDepFilter ? '' : 'none';
    }

    // Auto-open the details element when filtering
    if (_auditDepFilter) {
        const details = table.closest('details');
        if (details) details.open = true;
    }
}
```

**Why it matters:** The pills and table rows both carry
`data-audit-cat` / `data-dep-cat` attributes, creating a
declarative filter contract. The filter module state
(`_auditDepFilter`) lives in `_modals.html` but the pill render
lives in `_cards_a.html` — the `data-*` attributes bridge the
two files without import dependencies. The auto-open on `details`
is a nice UX touch: if the dependency table is collapsed, clicking
a filter pill opens it automatically.

---

### 8. Cross-Module Dependency Strength Visualization

**File:** `_cards_b.html` · **Lines 344–366**

The import graph card renders cross-module dependency relationships
with strength-based color coding and click-to-drill modals.

```javascript
// _cards_b.html lines 344–366
window._auditData.crossDeps = crossDeps;
const strengthColors = { strong: 'var(--danger)', moderate: 'var(--warning)', weak: 'var(--text-muted)' };

for (let di = 0; di < Math.min(crossDeps.length, 10); di++) {
    const dep = crossDeps[di];
    const color = strengthColors[dep.strength] || 'var(--text-muted)';
    const fileCount = (dep.files_involved || []).length;
    html += `<div style="display:flex;align-items:center;gap:8px;cursor:pointer"
                 onclick="_auditShowCrossDep(${di})"
                 title="Click to see ${fileCount} files">
        <span style="font-family:var(--font-mono)">${dep.from_module || '?'}</span>
        <span style="color:${color}">→</span>
        <span style="font-family:var(--font-mono)">${dep.to_module || '?'}</span>
        <span style="font-weight:600;color:${color}">${dep.import_count || 0}</span>
        <span style="font-size:0.64rem;color:var(--text-muted)">${dep.strength}</span>
    </div>`;
}
if (crossDeps.length > 10) {
    html += `<div>…and ${crossDeps.length - 10} more</div>`;
}
```

**Why it matters:** The three-tier strength system (strong → red,
moderate → yellow, weak → muted) gives an instant visual heat map
of coupling risks. The arrow (`→`) between module names is colored
by strength, and the import count shows the raw number of cross-
boundary imports. The click handler passes the index into
`_auditShowCrossDep()` which reads from `window._auditData.crossDeps`
to display the full file list. Only the top 10 are shown inline —
the rest are accessible via the drill-down modal.

---

### Feature Coverage Summary

| # | Feature | File(s) | Key Function(s) | Complexity |
|---|---------|---------|-----------------|------------|
| 1 | 5-way parallel L0/L1 load | `_init.html` | `loadAuditTab` | High |
| 2 | L2 auto-warm from cache | `_init.html` | `_autoLoadL2Cards` | Medium |
| 3 | Force-reload with server cache bust | `_init.html` | `loadAuditTab(force)` | Medium |
| 4 | Custom modal with Escape handler | `_init.html` | `_auditModal` | Low |
| 5 | File link → Content Vault navigation | `_init.html` | `_auditFileLink`, `_auditNavToFile` | Low |
| 6 | SVG dual-line sparkline | `_scores.html` | `_renderSparkline` | Medium |
| 7 | Animated breakdown bars with weights | `_scores.html` | `_renderBreakdown` | Medium |
| 8 | Score dashboard with trend arrows | `_scores.html` | `_renderScoresUI` | Medium |
| 9 | L2 enrichment upgrade path | `_scores.html` | `loadAuditScoresEnriched` | Medium |
| 10 | System profile with tool detection | `_cards_a.html` | `loadAuditSystemCard` | High |
| 11 | Missing tool install via plan flow | `_cards_a.html`, `_modals.html` | `_auditShowMissingTool` | Medium |
| 12 | Color-coded category pills | `_cards_a.html` | `loadAuditDepsCard` | Medium |
| 13 | Expandable dependency table | `_cards_a.html` | `loadAuditDepsCard` | Low |
| 14 | Framework + ORM detection cards | `_cards_a.html` | `loadAuditDepsCard` | Low |
| 15 | Cross-ecosystem pattern display | `_cards_a.html` | `loadAuditDepsCard` | Low |
| 16 | Infrastructure flag tags | `_cards_a.html` | `loadAuditStructureCard` | Low |
| 17 | Client grouping by service type | `_cards_a.html` | `loadAuditClientsCard` | Medium |
| 18 | Code health dimension scoring | `_cards_b.html` | `loadAuditHealthCard` | Medium |
| 19 | Severity-graded hotspot list | `_cards_b.html` | `loadAuditHealthCard` | Medium |
| 20 | Git repo health with object stats | `_cards_b.html` | `loadAuditRepoCard` | Medium |
| 21 | Large file detection table | `_cards_b.html` | `loadAuditRepoCard` | Low |
| 22 | Security grade (A–F) posture | `_cards_b.html` | `loadAuditRisksCard` | High |
| 23 | Inline file previews (3 + overflow) | `_cards_b.html` | `loadAuditRisksCard` | Medium |
| 24 | Cross-module dependency strength viz | `_cards_b.html` | `loadAuditL2StructureCard` | Medium |
| 25 | Library usage frequency bars | `_cards_b.html` | `loadAuditL2StructureCard` | Low |
| 26 | Multi-registry package links | `_modals.html` | `_auditShowFinding` | Medium |
| 27 | Batch `# nosec` dismiss with reason | `_modals.html` | `_auditDismissSelected` | High |
| 28 | Toggle-filter category + table sync | `_modals.html` | `_auditFilterDeps` | Medium |

