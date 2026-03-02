# DevOps — Front-End Scripts

> **12 files · 3,055 lines · The DevOps tab card system.**
>
> This domain owns the DevOps tab — a card-based dashboard where each
> card represents a domain (security, testing, K8s, Terraform, etc.).
> Cards load in parallel, support four visibility modes (auto, visible,
> manual, hidden), and integrate with the SSE-driven state store for live
> updates. Each card file follows an identical pattern: register with
> the store, load data from API, render into a card, and provide
> modals for actions.

---

## How It Works

### Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│ dashboard.html                                                      │
│                                                                      │
│  {% include 'partials/_tab_devops.html' %}              ← HTML     │
│  {% include 'scripts/devops/_devops.html' %}            ← JS      │
│                                                                      │
│  _devops.html wraps all 11 module files in a single <script>.     │
│  All functions share the same scope — no IIFEs.                    │
└────────────────────────────────────────────────────────────────────┘
```

### Card System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ _init.html — Card Registry + Tab Loader                       │
│                                                                │
│ _DEVOPS_CARDS = {                                             │
│   security:  { loadFn: loadSecurityCard,  label: '🔐 Security' },  │
│   testing:   { loadFn: loadTestingCard,   label: '🧪 Testing' },   │
│   quality:   { loadFn: loadQualityCard,   label: '🔧 Quality' },   │
│   packages:  { loadFn: loadPackagesCard,  label: '📦 Packages' },  │
│   env:       { loadFn: loadEnvCard,       label: '⚙️ Environment'},│
│   docs:      { loadFn: loadDocsCard,      label: '📚 Docs' },      │
│   k8s:       { loadFn: loadK8sCard,       label: '☸️ Kubernetes'}, │
│   terraform: { loadFn: loadTerraformCard, label: '🏗️ Terraform'}, │
│   dns:       { loadFn: loadDnsCard,       label: '🌐 DNS & CDN'}, │
│ }                                                              │
│                                                                │
│ Each card also registers via storeRegister() for SSE updates. │
└──────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────┐
│ loadDevopsTab(force)                                          │
│                                                                │
│ 1. Fetch prefs: GET /api/devops/prefs                        │
│ 2. For each card in _DEVOPS_CARDS:                           │
│    ├── hidden: card.style.display = 'none'                   │
│    ├── manual: show "click to load" placeholder              │
│    └── auto:   spinner → load in parallel                    │
│ 3. Promise.allSettled(autoCards.map(loadFn))                  │
│ 4. _devopsLoaded = true                                      │
└──────────────────────────────────────────────────────────────┘
```

### Uniform Card Pattern

Every card file follows this pattern:

```
┌─────────────────────────────────────────────────────────────┐
│ Card File (e.g., _security.html)                             │
│                                                               │
│ 1. storeRegister('security', renderSecurityCard)             │
│    ↑ Register renderer for SSE-driven state updates          │
│                                                               │
│ 2. async function loadSecurityCard()                         │
│    ├── Check store (in-memory SSE data)                      │
│    ├── Check sessionStorage (cardCached)                     │
│    ├── API fallback: GET /api/...                            │
│    ├── Handle errors → badge "Error"                         │
│    └── storeSet('security', data)                            │
│         ↕ Triggers renderSecurityCard(data)                  │
│         ↕ Saved to sessionStorage for page refreshes         │
│                                                               │
│ 3. function renderSecurityCard(data)                         │
│    ├── Set badge: className + innerHTML (dot + label)        │
│    ├── Render detail HTML (findings, tool status, etc.)      │
│    ├── Render action buttons (modals, live panels)           │
│    ├── renderMissingTools(data.missing_tools, containerId)   │
│    └── detail.innerHTML = html                               │
│                                                               │
│ 4. Modal functions (domain-specific actions)                 │
│    ├── modalOpen({ title, body, footerButtons })             │
│    ├── Async API call → render results in modal body         │
│    └── Toast feedback on success/failure                     │
└─────────────────────────────────────────────────────────────┘
```

### DOM Rendering Contract

Every card renders into two fixed DOM elements (defined in `_tab_devops.html`):

```
┌─ Card container: id="devops-{key}-card" ─────────────────────┐
│                                                                │
│  Badge:  <span id="devops-{key}-badge">                       │
│          className: 'status-badge ok|degraded|failed'         │
│          innerHTML: '<span class="status-dot"></span>Label'    │
│                                                                │
│  Detail: <div id="devops-{key}-detail">                       │
│          Full card body — sections, actions, live panels       │
│          Written via detail.innerHTML = html                   │
│                                                                │
│  Tools:  <div id="devops-{key}-missing-tools">                │
│          Injected AFTER innerHTML via renderMissingTools()     │
└────────────────────────────────────────────────────────────────┘

Key:  security | testing | quality | packages | env
      docs | k8s | terraform | dns
```

### Empty State Architecture

When a card has no relevant data (no framework detected, no K8s manifests,
etc.), it renders a guidance state instead of empty space:

```
┌─ Empty State ────────────────────────────────────────────────┐
│                                                              │
│  Badge: 'degraded' or 'N/A'                                 │
│                                                              │
│  Detail:                                                     │
│  ├── renderMissingTools() — install buttons for tools        │
│  ├── Explanation of what's needed to activate                │
│  ├── Supported items list (e.g., "pytest, jest, vitest")     │
│  └── Generate/scaffold button (if applicable)                │
│                                                              │
│  Security has a SPECIAL empty state: links to Audit → Risks  │
│  with a timed auto-click (switchTab + setTimeout + .click()) │
└──────────────────────────────────────────────────────────────┘
```

### Three-Tier Cache Strategy

```
Tier 1: SSE state store (in-memory, real-time)
    ↓ not available?
Tier 2: sessionStorage (cardCached, survives page refresh)
    ↓ not available?
Tier 3: API fetch (server-side detection)
    ↓ result stored in Tier 1 + Tier 2
```

### Preference System

```
GET /api/devops/prefs → { security: 'auto', testing: 'manual', ... }
PUT /api/devops/prefs → save user preferences

Modes:
┌──────────┬────────────────────────────────────────────────┐
│ auto     │ Card loads automatically when tab opens.       │
│ visible  │ Same as auto — always loads. (legacy alias)    │
│ manual   │ Card shows "click to load" — user triggers.    │
│ hidden   │ Card hidden entirely (display: none).          │
└──────────┴────────────────────────────────────────────────┘

Preferences are set via the ⚙️ Card Preferences modal.
```

---

## File Map

```
devops/
├── _devops.html             Loader — includes all modules (35 lines)
├── _init.html               State vars, prefs, card registry, tab load (168 lines)
├── _security.html           Security card: posture, findings, live panels (304 lines)
├── _testing.html            Testing card: frameworks, coverage, test runner (301 lines)
├── _docs.html               Docs card: key files, coverage, link check (208 lines)
├── _k8s.html                K8s card: resources, helm, kustomize, modals (288 lines)
├── _terraform.html          Terraform card: resources, providers, modals (270 lines)
├── _dns.html                DNS card: domains, certs, lookup/ssl/generate (226 lines)
├── _quality.html            Quality card: linters, formatters, run/gen (226 lines)
├── _packages.html           Packages card: managers, outdated/audit/list (180 lines)
├── _env.html                Environment card: envs, drift, live panels, gen (382 lines)
├── _audit_manager.html      Audit manager: pending + saved snapshots modal (479 lines)
└── README.md                This file
```

---

## Per-File Documentation

### `_devops.html` — Loader (35 lines)

Pure Jinja2 include orchestrator. Documents the module index and
assembles all 11 modules into a single `<script>` scope.

### `_init.html` — Card Registry & Tab Load (168 lines)

**State:**

| Variable | Type | Purpose |
|----------|------|---------|
| `_devopsLoaded` | `boolean` | Tab already loaded flag |
| `_DEVOPS_CARDS` | `Object` | Card registry: key → `{ loadFn, label }` (9 cards) |
| `_devopsPrefs` | `Object\|null` | User preferences: key → `'auto'` / `'visible'` / `'manual'` / `'hidden'` |

| Function | What It Does |
|----------|-------------|
| `_fetchDevopsPrefs()` | GET `/devops/prefs` — cached in `_devopsPrefs`, defaults all-auto on error |
| `loadDevopsTab(force)` | Apply prefs → parallel-load auto+visible cards → mark loaded |
| `openDevopsPrefsModal()` | Open preferences modal with per-card dropdowns (auto/visible/manual/hidden) |
| `_saveDevopsPrefs()` | PUT `/devops/prefs` → invalidate all cards → reload tab with new prefs |

### `_security.html` — Security Card (304 lines)

| Function | What It Does |
|----------|-------------|
| `loadSecurityCard()` | 3-tier cache → GET `/security/posture-summary`. Empty state: guide to Audit → Risks |
| `renderSecurityCard(data)` | Score bar (0–100) + posture checks per-check % + findings by severity + actions |
| `secSensitiveFiles()` | Modal: GET `/security/files` → list files + gitignore coverage |
| `secGitignoreAnalysis()` | Modal: GET `/security/gitignore` → coverage %, missing patterns, current count |
| `secGenerateGitignore()` | Toast: POST `/security/generate/gitignore` → invalidate card |
| `_secLive(what)` | Live data panel dispatcher: `scan` \| `posture` \| `status` — renders into `devops-sec-live-panel` |

**Card shows:** Security score (0–100 bar), grade badge, posture
checks with per-check scores, findings count by severity (critical/
high/medium), action links to Audit tab, 3 live data panels
(Run Scan, Posture Detail, Full Status), missing tools banner.

### `_testing.html` — Testing Card (301 lines)

| Function | What It Does |
|----------|-------------|
| `loadTestingCard()` | 3-tier cache → GET `/testing/status` |
| `renderTestingCard(data)` | Frameworks + inventory stats + ratio bar + coverage tools |
| `runTests()` | Modal: POST `/testing/run` → pass/fail/skip breakdown + failure details |
| `testCoverage()` | Modal: POST `/testing/coverage` → overall % bar + per-file stmts/miss table |
| `testInventory()` | Modal: GET `/testing/inventory` → per-file function/class/line counts |
| `testGenTemplate()` | Modal form: module name + stack select (python/node/rust) |
| `doTestGenTemplate()` | POST `/testing/generate/template` → generate test file + toast |

**Card shows:** Detected frameworks (name + detected_by + stack),
test functions/classes/files counts, test ratio with visual bar,
coverage tools list, missing tools banner.

### `_docs.html` — Documentation Card (208 lines)

| Function | What It Does |
|----------|-------------|
| `loadDocsCard()` | 3-tier cache → GET `/docs/status` |
| `renderDocsCard(data)` | Key files + doc dirs + API specs + total doc count |
| `docsCoverage()` | Modal: GET `/docs/coverage` → overall % bar + per-module README/doc/API status |
| `docsCheckLinks()` | Modal (wide): GET `/docs/links` → files checked, total links, broken link list |
| `docsGenChangelog()` | Toast: POST `/docs/generate/changelog` → generate CHANGELOG.md, invalidate card |
| `docsGenReadme()` | Toast: POST `/docs/generate/readme` → generate README.md, invalidate card |

**Card shows:** Key file existence (README, CHANGELOG, LICENSE,
CONTRIBUTING), doc directories with file counts and sizes, API
specification files (type + format), total documentation file count,
missing tools banner.

### `_k8s.html` — Kubernetes Card (288 lines)

| Function | What It Does |
|----------|-------------|
| `loadK8sCard()` | 3-tier cache → GET `/k8s/status` |
| `renderK8sCard(data)` | kubectl status + resource summary + helm charts + kustomize + cross-tab link |
| `k8sValidate()` | Modal (wide): GET `/k8s/validate` → errors/warnings per file+resource |
| `k8sCluster()` | Modal: GET `/k8s/cluster` → connected status, context, nodes, namespaces |
| `k8sResources()` | Modal: kind select + namespace input → interactive resource browser |
| `doK8sResources()` | GET `/k8s/resources?kind=X&namespace=Y` → resource list with status+age |
| `k8sGenerate()` | Modal form: app name, port, replicas |
| `doK8sGenerate()` | POST `/k8s/generate/manifests` → generate files, invalidate card, reload |

**Card shows:** kubectl availability + version + context badge,
resource kind summary tags (count per kind), Helm charts with
chart version + app version, Kustomize detection with path,
cross-tab link to integrations, missing tools banner.

### `_terraform.html` — Terraform Card (270 lines)

| Function | What It Does |
|----------|-------------|
| `loadTerraformCard()` | 3-tier cache → GET `/terraform/status` |
| `renderTerraformCard(data)` | CLI status + init badge + .tf files + resources + providers + modules + backend + cross-tab link |
| `tfValidate()` | Modal: POST `/terraform/validate` → valid/error+warning count + diagnostics |
| `tfPlan()` | Modal: POST `/terraform/plan` → add/change/destroy counts + raw output |
| `tfState()` | Modal: GET `/terraform/state` → type.name list per provider |
| `tfWorkspaces()` | Modal (narrow): GET `/terraform/workspaces` → workspace list + current indicator |
| `tfGenerate()` | Modal form: cloud provider select (AWS/GCP/Azure/DO) + backend select (local/S3/GCS/Azure Blob) |
| `doTfGenerate()` | POST `/terraform/generate` → generate scaffold files, invalidate card, reload |

**Card shows:** CLI availability + version, init status badge,
.tf file count, resource count, provider tags, module count,
backend type, cross-tab link to integrations, missing tools banner.

### `_dns.html` — DNS & CDN Card (226 lines)

| Function | What It Does |
|----------|-------------|
| `loadDnsCard()` | 3-tier cache → GET `/dns/status` |
| `renderDnsCard(data)` | CDN providers + domains + SSL certs + actions |
| `dnsLookupModal()` | Modal (narrow): domain input with Enter-to-submit |
| `doDnsLookup()` | GET `/dns/lookup/:domain` → A/CNAME/NS records + full record table |
| `dnsSslCheck()` | Modal (narrow): domain input with Enter-to-submit |
| `doSslCheck()` | GET `/dns/ssl/:domain` → valid/invalid, issuer, expiry, days remaining |
| `dnsGenerateModal()` | Modal (narrow): domain + target IP + mail provider (Google/ProtonMail) |
| `doDnsGenerate()` | POST `/dns/generate` → record table + zone file preview |

**Card shows:** CDN provider name + type tags, domain list with
link icons, SSL certificate domain + issuer, missing tools banner.

### `_quality.html` — Quality Card (226 lines)

| Function | What It Does |
|----------|-------------|
| `loadQualityCard()` | 3-tier cache → GET `/quality/status` |
| `renderQualityCard(data)` | Category tags (lint/type/test/format) + relevant tools + availability + install hints |
| `qualityRunCategory(category)` | Modal (wide): Run + Auto-Fix buttons (lint/format only get fix), click-to-execute |
| `doQualityRun(category, fix)` | POST `/quality/:category` → per-tool pass/fail + stdout/stderr output |
| `qualityGenConfig()` | Modal (narrow): stack select (Python/Node/TypeScript/Rust) |
| `doQualityGenConfig()` | POST `/quality/generate/config` → file list + toast, invalidate card |

**Card shows:** Category summary tags (lint: N, type: N, test: N,
format: N), relevant tools with ✅/❌ availability + category badge
+ config file indicator, copy-to-clipboard install hints for missing
tools, missing tools banner.

### `_packages.html` — Packages Card (180 lines)

| Function | What It Does |
|----------|-------------|
| `loadPackagesCard()` | 3-tier cache → GET `/packages/status` |
| `renderPackagesCard(data)` | Package managers with CLI status + dep/lock file counts + install hints |
| `pkgOutdated()` | Modal: GET `/packages/outdated` → current vs latest per package |
| `pkgAudit()` | Modal: GET `/packages/audit` → vulnerability count + raw output |
| `pkgList()` | Modal: GET `/packages/list` → name + version per package |
| `pkgInstall()` | Toast: POST `/packages/install` → install dependencies |
| `pkgUpdate()` | Toast: POST `/packages/update` → update packages |

**Card shows:** Detected package managers with ✅/⚠️ CLI
availability, dep file + lock file counts per manager,
copy-to-clipboard install hints for unavailable CLIs,
missing tools banner.

### `_env.html` — Environment & IaC Card (382 lines)

The most complex card. Renders per-environment rows with vault
state, GitHub alignment, and secret counts. Also provides 5 live
data panels and 2 generate actions.

| Function | What It Does |
|----------|-------------|
| `loadEnvCard()` | 3-tier cache → GET `/env/card-status` |
| `renderEnvCard(data)` | Active env indicator + env rows + .env files + live panels + generate toolbar |
| `envDriftModal(envName)` | Modal: parallel fetch `/vault/keys` + `/gh/secrets` → compute local-only / GH-only / synced |
| `envActivate(envName)` | POST `/vault/activate-env` → switch active environment → reload card |
| `_envLive(what)` | Live data panel: `vars` \| `validate` \| `diff` \| `iac` \| `infra` — each fetches its own API |
| `_envGenerate(what)` | Generate `.env.example` or `.env` from template → POST `/infra/env/generate-example` or `/generate-env` |

**Live data panels (via `_envLive`):**

| Panel | API | What It Shows |
|-------|-----|---------------|
| `vars` | `/infra/env/vars` | All .env variables with values |
| `validate` | `/infra/env/validate` | .env validation: pass/fail + issues |
| `diff` | `/infra/env/diff` | .env vs .env.example: missing + extra keys |
| `iac` | `/infra/iac/status` | IaC providers: name, CLI availability, config files |
| `infra` | `/infra/status` | Combined: env files + IaC providers overview |

**Per-environment row shows:**
- Active indicator (green border)
- Vault state: 🔓 unlocked / 🔒 locked / ⬜ none
- GitHub sync: ✅ synced / ⚠️ N drifted (with tooltip: local-only + gh-only counts)
- Local key count + GitHub secrets+variables counts
- 🔍 Drift button + ⬆️ Activate button (if not active)

### `_audit_manager.html` — Audit Manager (479 lines)

Standalone modal system for managing both **pending** and **saved** audit
snapshots. Not a card — triggered from the SSE badge in the header
or from per-card audit badges.

**Pending Audit Manager:**

| Function | What It Does |
|----------|-------------|
| `_hydratePendingAudits()` | GET `/audits/pending` → populate `window._pendingAudits` → show per-card badges |
| `openAuditManager(filterKey, filterType)` | Open modal with pending snapshots — optional filter by card key or type (devops/project) |
| `_auditSaveOne(snapshotId)` | POST `/audits/save` → save single snapshot to git → remove row → re-hydrate |
| `_auditDiscardOne(snapshotId)` | POST `/audits/discard` → discard single snapshot → remove row → re-hydrate |
| `_auditGetSelected()` | Collect all checked checkbox values as array of snapshot IDs |
| `_auditSaveSelected()` | Batch POST `/audits/save` with all selected IDs → close modal → re-hydrate |
| `_auditDiscardSelected()` | Batch POST `/audits/discard` with all selected IDs → close modal → re-hydrate |
| `_auditPreviewOne(snapshotId)` | GET `/audits/pending/:id` → stacked overlay with header + JSON data |
| `_auditToggleAll(checked)` | Select/deselect all `.audit-mgr-cb` checkboxes |
| `_auditUpdateCount()` | Update "N snapshot(s)" counter; show "All processed" when empty |
| `_auditTimeAgo(ts)` | Unix timestamp → "just now" / "5m ago" / "2h ago" / "3d ago" |

**Saved Audit Browser:**

| Function | What It Does |
|----------|-------------|
| `openSavedAuditBrowser(filterType)` | GET `/audits/saved` → modal with saved audit list + type filter tabs |
| `_savedAuditPreview(snapshotId)` | GET `/audits/saved/:id` → stacked overlay with header + JSON data |
| `_savedAuditDelete(snapshotId)` | DELETE `/audits/saved/:id` → confirm → remove row from DOM |

---

## API Response Shapes

Every card's `data` object (passed to the render function) follows a
card-specific shape. These are the actual fields accessed in render code.

### Security Card Data

```javascript
{
  posture: {
    score: 85,           // 0-100 weighted score
    grade: "B+",         // letter grade
    checks: [            // individual posture checks
      { name: "gitignore", passed: true, score: 0.95 }
    ],
    missing_tools: [...]  // tools needing install
  },
  findings: [
    { severity: "critical"|"high"|"medium", file: "...", rule: "..." }
  ]
}
```

### Testing Card Data

```javascript
{
  frameworks: [
    { name: "pytest", detected_by: "config file", stack: "python" }
  ],
  stats: {
    test_files: 12,
    test_functions: 84,
    test_classes: 5,
    source_files: 45,
    test_ratio: 0.27       // test_files / source_files
  },
  coverage_tools: [
    { name: "coverage.py", config: ".coveragerc" }
  ],
  missing_tools: [...]
}
```

### Docs Card Data

```javascript
{
  readme:       { exists: true, headings: ["Install", "Usage", ...] },
  changelog:    { exists: true },
  license:      { exists: true },
  contributing: { exists: false },
  doc_dirs:     [{ name: "docs/", file_count: 8, total_size: 24576 }],
  api_specs:    [{ file: "openapi.yaml", type: "OpenAPI", format: "yaml" }],
  doc_files:    14,           // total doc file count
  missing_tools: [...]
}
```

### K8s Card Data

```javascript
{
  has_k8s: true,
  kubectl:  { available: true, version: "v1.28.2", context: "minikube" },
  total_resources: 12,
  resource_summary: { Deployment: 3, Service: 4, ConfigMap: 5 },
  helm_charts: [
    { name: "myapp", version: "0.2.1", appVersion: "1.0.0" }
  ],
  kustomize: { exists: true, path: "k8s/overlays" },
  missing_tools: [...]
}
```

### Terraform Card Data

```javascript
{
  has_terraform: true,
  cli:         { available: true, version: "v1.6.2" },
  initialized: true,
  files:       ["main.tf", "variables.tf", "outputs.tf"],
  resources:   [{ type: "aws_instance", name: "web" }],
  providers:   ["aws", "random"],       // string array, no versions
  modules:     [{ source: "./modules/vpc" }],
  backend:     { type: "s3" },          // or string "local"
  missing_tools: [...]
}
```

### DNS Card Data

```javascript
{
  cdn_providers: [{ name: "Cloudflare", type: "proxy" }],
  domains:       ["example.com", "api.example.com"],
  ssl_certs:     [{ domain: "example.com", issuer: "Let's Encrypt" }],
  dns_files:     ["dns/zone.txt"],        // presence check for empty state
  missing_tools: [...]
}
```

### Quality Card Data

```javascript
{
  has_quality: true,
  categories: { lint: 2, typecheck: 1, test: 1, format: 2 },
  tools: [
    {
      name: "ruff",
      category: "lint",
      relevant: true,            // relevant to project stack
      cli_available: true,
      config_found: true,
      config_file: ".ruff.toml",
      install_hint: "pip install ruff"
    }
  ],
  missing_tools: [...]
}
```

### Packages Card Data

```javascript
{
  has_packages: true,
  total_managers: 2,
  managers: [
    {
      name: "pip",
      cli_available: true,
      dependency_files: ["requirements.txt"],
      lock_files: [],
      install_hint: "python -m ensurepip"
    }
  ],
  missing_tools: [...]
}
```

### Environment Card Data

```javascript
{
  active_env: "production",
  envs: [
    {
      name: "production",
      is_active: true,
      vault_state: "unlocked",    // unlocked | locked | none
      local_keys: 12,
      gh_secrets: 10,
      gh_vars: 2,
      synced: false,
      drift_summary: { local_only: 2, gh_only: 0 }
    }
  ],
  env_files: [".env", ".env.example"],
  missing_tools: [...]
}
```

---

## Shared Patterns

### `renderMissingTools(tools, containerId)`

Called by **every** card at the end of rendering. If `data.missing_tools`
has entries, renders install buttons inside the given container.
The function is defined in `globals/_shared.html`, not in this domain.

```
renderMissingTools(data.missing_tools, 'devops-sec-missing-tools')
│
├── tools is null or empty → does nothing
└── tools has entries →
    └── each entry → install button with tool name + onclick → installTool()
```

Because `renderMissingTools` injects via `.innerHTML` on a sub-container,
it must be called AFTER `detail.innerHTML = html` — otherwise the
container element doesn't exist yet in the DOM.

### `cardCrossLink(tabKey, label)`

Used by `_k8s.html` and `_terraform.html` to render a subtle link
to the integrations tab. Returns an HTML string:

```
html += cardCrossLink('integrations', 'Full K8s integration card');
```

Renders as a small footer-style link: `→ Full K8s integration card`
with `onclick="switchTab('integrations')"`. Defined in `globals/_shared.html`.

### Modal Form Helpers

Several cards use modal forms for generation actions (K8s generate,
Terraform generate, Testing template, Quality config). They depend
on shared helpers from `globals/_modals.html`:

| Helper | Purpose |
|--------|--------|
| `modalFormField(opts)` | Build a styled label + input/select with hints |
| `mfVal(fieldName)` | Read value: `document.getElementById('mf-' + fieldName).value` |
| `modalError(msg)` | Show error message in the modal footer status area |
| `modalOpen(opts)` | Open modal with title, body, size, footerButtons |
| `modalClose()` | Close the current modal |

Modal sizes: `'narrow'` (form inputs), `'wide'` (tables/results), default (standard).

---

## Dependency Graph

```
_init.html                     ← card registry, tab loader, prefs
    ↑
    ├── Uses: cardCached, cardStore, cardInvalidate, cardInvalidateAll
    ├── Uses: storeRegister, storeSet (from globals/_event_stream.html)
    ├── Uses: api, esc, toast (from globals/_api.html)
    └── Uses: modalOpen, modalClose (from globals/_auth_modal.html)
    │
    │   ALL card files depend on _init.html for registry
    │   ALL card files use the same globals pattern
    │
    ├── _security.html         storeRegister('security', ...)
    ├── _testing.html          storeRegister('testing', ...)
    ├── _docs.html             storeRegister('docs', ...)
    ├── _k8s.html              storeRegister('k8s', ...)
    ├── _terraform.html        storeRegister('terraform', ...)
    ├── _dns.html              storeRegister('dns', ...)
    ├── _quality.html          storeRegister('quality', ...)
    ├── _packages.html         storeRegister('packages', ...)
    ├── _env.html              storeRegister('env', ...)
    │
    └── _audit_manager.html    (no storeRegister — modal only)
```

---

## Consumers

### Tab Loading

| File | How |
|------|-----|
| `dashboard.html` (line 70) | `{% include 'scripts/devops/_devops.html' %}` |
| `_tabs.html` (line 84) | `loadDevopsTab()` — called on devops tab switch |

### Cross-Tab Consumers

| Consumer | What It Calls | When |
|----------|-------------|------|
| Wizard `_nav.html` | `cardInvalidateAll()` | After wizard completes |
| Wizard `_helpers.html` | `cardInvalidate('security')` | After tool install |
| `_event_stream.html` | `storeSet(key, data)` → triggers registered renderer | SSE events |
| Header audit badge | `openAuditManager()` | Badge click |
| Audit tab | `openAuditManager(key, type)` | Filtered view |

### API Endpoints Used

| Endpoint | Used By | Purpose |
|----------|---------|---------|
| `GET /api/devops/prefs` | `_init.html` | Load card visibility preferences |
| `PUT /api/devops/prefs` | `_init.html` | Save card visibility preferences |
| `GET /api/security/posture-summary` | `_security.html` | Security posture overview |
| `GET /api/security/files` | `_security.html` | List sensitive files |
| `GET /api/security/gitignore` | `_security.html` | Gitignore analysis |
| `POST /api/security/generate/gitignore` | `_security.html` | Generate .gitignore |
| `GET /api/security/scan` | `_security.html` | Live panel: run secret scan |
| `GET /api/security/posture` | `_security.html` | Live panel: posture detail |
| `GET /api/security/status` | `_security.html` | Live panel: full status |
| `GET /api/testing/status` | `_testing.html` | Test framework detection |
| `POST /api/testing/run` | `_testing.html` | Run test suite |
| `POST /api/testing/coverage` | `_testing.html` | Test coverage report |
| `GET /api/testing/inventory` | `_testing.html` | Test file inventory |
| `POST /api/testing/generate/template` | `_testing.html` | Generate test template |
| `GET /api/docs/status` | `_docs.html` | Documentation files status |
| `GET /api/docs/coverage` | `_docs.html` | Per-module doc coverage |
| `GET /api/docs/links` | `_docs.html` | Broken link check |
| `POST /api/docs/generate/changelog` | `_docs.html` | Generate CHANGELOG.md |
| `POST /api/docs/generate/readme` | `_docs.html` | Generate README.md |
| `GET /api/k8s/status` | `_k8s.html` | K8s detection + resources |
| `GET /api/k8s/validate` | `_k8s.html` | Manifest validation |
| `GET /api/k8s/cluster` | `_k8s.html` | Cluster status + nodes |
| `GET /api/k8s/resources` | `_k8s.html` | Live K8s resources (kind+namespace) |
| `POST /api/k8s/generate/manifests` | `_k8s.html` | Generate K8s manifests |
| `GET /api/terraform/status` | `_terraform.html` | Terraform detection |
| `POST /api/terraform/validate` | `_terraform.html` | Terraform validate |
| `POST /api/terraform/plan` | `_terraform.html` | Terraform plan |
| `GET /api/terraform/state` | `_terraform.html` | Terraform state list |
| `GET /api/terraform/workspaces` | `_terraform.html` | Workspace list |
| `POST /api/terraform/generate` | `_terraform.html` | Generate Terraform scaffold |
| `GET /api/dns/status` | `_dns.html` | DNS/CDN detection |
| `GET /api/dns/lookup/:domain` | `_dns.html` | DNS record lookup |
| `GET /api/dns/ssl/:domain` | `_dns.html` | SSL certificate check |
| `POST /api/dns/generate` | `_dns.html` | Generate DNS records |
| `GET /api/quality/status` | `_quality.html` | Quality tool detection |
| `POST /api/quality/:category` | `_quality.html` | Run quality check |
| `POST /api/quality/generate/config` | `_quality.html` | Generate quality config |
| `GET /api/packages/status` | `_packages.html` | Package manager detection |
| `GET /api/packages/outdated` | `_packages.html` | Outdated package list |
| `GET /api/packages/audit` | `_packages.html` | Security vulnerability audit |
| `GET /api/packages/list` | `_packages.html` | Installed packages list |
| `POST /api/packages/install` | `_packages.html` | Install dependencies |
| `POST /api/packages/update` | `_packages.html` | Update packages |
| `GET /api/env/card-status` | `_env.html` | Environment card data |
| `POST /api/vault/activate-env` | `_env.html` | Activate environment |
| `GET /api/vault/keys?env=X` | `_env.html` | Local vault keys for drift modal |
| `GET /api/gh/secrets?env=X` | `_env.html` | GitHub secrets+vars for drift modal |
| `GET /api/infra/env/vars` | `_env.html` | Live panel: .env variables |
| `GET /api/infra/env/validate` | `_env.html` | Live panel: .env validation |
| `GET /api/infra/env/diff` | `_env.html` | Live panel: .env vs .env.example |
| `GET /api/infra/iac/status` | `_env.html` | Live panel: IaC providers |
| `GET /api/infra/status` | `_env.html` | Live panel: infra overview |
| `POST /api/infra/env/generate-example` | `_env.html` | Generate .env.example |
| `POST /api/infra/env/generate-env` | `_env.html` | Generate .env from template |
| `GET /api/audits/pending` | `_audit_manager.html` | Pending snapshot list |
| `GET /api/audits/pending/:id` | `_audit_manager.html` | Single pending snapshot detail |
| `POST /api/audits/save` | `_audit_manager.html` | Save snapshot(s) to git |
| `POST /api/audits/discard` | `_audit_manager.html` | Discard snapshot(s) |
| `GET /api/audits/saved` | `_audit_manager.html` | Saved snapshot list |
| `GET /api/audits/saved/:id` | `_audit_manager.html` | Single saved snapshot detail |
| `DELETE /api/audits/saved/:id` | `_audit_manager.html` | Delete saved snapshot |

---

## Design Decisions

### Why the uniform card pattern?

Every card follows the exact same structure: `storeRegister()` → `loadFn()` →
`renderFn()` → modals. This makes the code predictable — a developer
who understands one card understands all nine. It also means the
`loadDevopsTab()` orchestrator can treat all cards identically
through the `_DEVOPS_CARDS` registry.

### Why four visibility modes?

"Auto" loads everything on tab open (fast for power users). "Visible"
is a legacy alias — behaves identically to auto. "Manual" prevents
expensive API calls for cards the user rarely needs (e.g., Terraform
on a project that doesn't use it). "Hidden" removes the card entirely
for clean UI. Preferences persist server-side in `devops_prefs.json`.

### Why parallel card loading?

Cards are independent — Security doesn't need Testing data, K8s
doesn't need DNS data. `Promise.allSettled()` loads all auto cards
in parallel, with per-card error isolation. A failing `/k8s/status`
endpoint shows "Error" on the K8s card without blocking the rest.

### Why SSE-driven re-rendering?

The store system (`storeRegister`, `storeSet`) allows the SSE event
stream to push updates to cards without the user refreshing.
When a background scan completes, the server sends an SSE event,
the store updates, and the registered renderer re-draws the card.
This is why each card has a separate `renderFn` — it must be
callable both from `loadFn` and from SSE events.

### Why is `_audit_manager.html` in devops/?

The audit manager modal handles *pending audit snapshots* — results
from background scans that haven't been saved to git yet. It's
triggered from the SSE badge in the header bar, not from a card.
It lives in `devops/` because audit scans are DevOps operations
and the modal shares the same `api()`, `modalOpen()`, `toast()`
scope.

### Why does `_env.html` have drift detection?

Environment drift (local .env keys vs GitHub Secrets) is a common
problem. The drift modal fetches both sources in parallel
(`/vault/keys` + `/github/secrets`), computes the diff, and shows
local-only / GitHub-only / shared keys. This gives immediate
visibility into secret synchronization status.

### Why do modals follow a consistent pattern?

Every modal opens with `modalOpen({ title, body, footerButtons })`,
shows a spinner, makes an async API call, replaces the body with
results, and provides close/action buttons. This consistency means
users always know what to expect — spinner, results, close.

---

## Adding a New Card

The registry pattern makes adding a new card mechanical. Follow these steps:

### 1. Create the card file

```
devops/_newcard.html
```

Follow the uniform pattern:

```javascript
/* DevOps Tab JS — NewCard Card
     loadNewCardCard(), modals.
     Depends on: _devops_init.html (card registry)
*/
    storeRegister('newcard', renderNewCardCard);

    async function loadNewCardCard() {
        const badge = document.getElementById('devops-newcard-badge');
        const detail = document.getElementById('devops-newcard-detail');

        // 1. SSE store
        const storeData = storeGet('newcard');
        if (storeData) { renderNewCardCard(storeData); return; }

        // 2. sessionStorage
        const cached = cardCached('newcard');
        if (cached) { renderNewCardCard(cached); return; }

        // 3. API fallback
        const data = await api('/newcard/status').catch(e => ({ _err: e }));
        if (data._err) {
            badge.className = 'status-badge failed';
            badge.innerHTML = '<span class="status-dot"></span>Error';
            detail.innerHTML = `<p class="empty-state-sm" style="color:var(--error)">${esc(data._err.message)}</p>`;
            return;
        }
        storeSet('newcard', data);
    }

    function renderNewCardCard(data) {
        const badge = document.getElementById('devops-newcard-badge');
        const detail = document.getElementById('devops-newcard-detail');
        if (!badge || !detail) return;

        // ... render badge + detail HTML ...
        // Must end with:
        html += '<div id="devops-newcard-missing-tools"></div>';
        detail.innerHTML = html;
        renderMissingTools(data.missing_tools, 'devops-newcard-missing-tools');
    }
```

### 2. Register in `_init.html`

Add entry to `_DEVOPS_CARDS`:

```javascript
newcard: { loadFn: () => loadNewCardCard(), label: '🆕 New Card' },
```

### 3. Add the include in `_devops.html`

```jinja2
{% include 'scripts/devops/_newcard.html' %}
```

### 4. Add HTML in `_tab_devops.html`

Add the card container with badge + detail divs using the DOM ID
convention: `devops-newcard-badge`, `devops-newcard-detail`.

### 5. Add backend endpoint

Create `GET /api/newcard/status` returning the card's data shape.
The SSE system should emit `cache:done` events for the `newcard` key
when background scanning completes.

### Checklist

- [ ] File created following uniform pattern
- [ ] `storeRegister()` called with correct key
- [ ] 3-tier cache implemented (store → sessionStorage → API)
- [ ] Empty state rendered when no data
- [ ] `renderMissingTools()` called AFTER `detail.innerHTML`
- [ ] Card registered in `_DEVOPS_CARDS`
- [ ] Include added in `_devops.html`
- [ ] HTML container added in `_tab_devops.html`
- [ ] Backend endpoint returns expected data shape
- [ ] README updated with new card's documentation
