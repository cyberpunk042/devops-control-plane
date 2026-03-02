# Integrations — Front-End Scripts

> **23 files. 9,081 lines. The entire Integrations tab and its setup wizards.**
>
> This is the largest front-end domain. It powers the Integrations tab —
> a card-based dashboard where each card represents one DevOps integration
> (Git, GitHub, Docker, K8s, Terraform, Pages, CI/CD, DNS). Every card
> follows the same pattern: detect → display status → offer actions →
> provide live data panels. Setup wizards guide users through first-time
> configuration of each integration.

---

## How It Works

### Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│ dashboard.html                                                      │
│                                                                      │
│  {% include 'scripts/integrations/_integrations.html' %}   ← line 69│
│  {% include 'scripts/integrations/setup/_dispatch.html' %} ← line 54│
│                                                                      │
│  _integrations.html is the LOADER — it includes all 12 modules     │
│  in a single <script> scope so they share variables and functions.  │
│  setup/_dispatch.html loads AFTER to route openSetupWizard(key).    │
└────────────────────────────────────────────────────────────────────┘
```

### Module Loading Order

The `_integrations.html` loader includes modules in this exact order:

```
_init.html                 ← state, prefs, card registry, tab load
    ↓
_git.html                  ← Git card + actions
_github.html               ← GitHub card + live panels
_cicd.html                 ← CI/CD card + live panels + generate
_docker.html               ← Docker card + live panels + modals
_docker_compose.html       ← Docker generate + operational actions
_k8s.html                  ← K8s card + live panels + all modals
_terraform.html            ← Terraform card + live panels + actions
_pages.html                ← Pages card + segment management
_pages_config.html         ← Pages config modal + features
_pages_sse.html            ← SSE build streaming + CI gen
_dns.html                  ← DNS & CDN card + live panels
```

All modules share a single `<script>` scope. The `_init.html` module
defines the card registry, state variables, and the `loadIntegrationsTab()`
orchestrator. Each subsequent module registers its load function with
the registry and defines its own card-specific logic.

### Card Lifecycle

Every integration card follows this lifecycle:

```
1. loadIntegrationsTab()
   │
   ├── Fetch user preferences (auto/manual/hidden per card)
   ├── Fetch project status (for cross-dependency hints)
   │
   └── For each card in _INT_CARDS:
       │
       ├── hidden → card.style.display = 'none', skip
       │
       ├── manual → show placeholder with "▶ Load" button
       │
       └── auto/visible → call card.loadFn() in parallel
           │
           ├── Check sessionStorage cache (cardCached)
           │     ├── HIT → render from cache
           │     └── MISS → GET /api/<integration>/status
           │
           ├── Determine state:
           │     ├── NOT INSTALLED → error badge + setup banner
           │     ├── NOT CONFIGURED → degraded badge + wizard CTA
           │     └── READY → ok badge + full card
           │
           ├── Build HTML sections:
           │     ├── cardStatusGrid()       — key-value pairs
           │     ├── cardDetectionList()     — detected files/features
           │     ├── cardLivePanel()         — tabbed live data
           │     ├── cardActionToolbar()     — operation buttons
           │     ├── cardGenerateToolbar()   — file generation buttons
           │     └── cardDepHint()           — cross-dependency hints
           │
           └── Set detail.innerHTML = html
```

### Live Data Panels

Each card can declare tabbed live data panels that load on-demand:

```
cardLivePanel('int-docker-live', [
    { key: 'containers', label: '📦 Containers' },
    { key: 'images',     label: '💿 Images' },
    { key: 'compose',    label: '🔧 Compose' },
    { key: 'networks',   label: '🌐 Networks' },
    { key: 'volumes',    label: '💾 Volumes' },
], '_dockerLiveTab');
```

When a user clicks a tab:
1. `_dockerLiveTab(what, panelId)` is called
2. The handler fetches live data from the API
3. Renders the data using `cardDataTable()` or custom HTML
4. Results are cached in sessionStorage for repeat views

### Setup Wizard System

Setup wizards are multi-step modal flows for first-time integration
configuration:

```
openSetupWizard(key)  ←── dispatch (_dispatch.html)
    │
    ├── git       → openGitSetupWizard()      — 4 steps
    ├── github    → openGitHubSetupWizard()   — 5 steps
    ├── docker    → openDockerSetupWizard()   — 3 steps
    ├── k8s       → openK8sSetupWizard()      — 9 steps
    ├── cicd      → openCICDSetupWizard()     — 5 steps
    ├── terraform → openTerraformSetupWizard()— 5 steps
    ├── dns       → openDnsSetupWizard()      — 5 steps
    └── pages     → toast + tab switch (no wizard; uses card UI)
```

Each wizard step follows the `wizardModalOpen()` contract:
- `render(data, el)` — build the step UI
- `collect(data)` — save user inputs back to shared data object
- `validate(data)` — optional, prevent advancing if invalid
- `onComplete(data)` — final step, POST config to backend

---

## File Map

```
integrations/
├── _integrations.html        Loader — includes all modules (36 lines)
├── _init.html                State, prefs, card registry, tab load (253 lines)
├── _git.html                 Git card + actions (319 lines)
├── _github.html              GitHub card + live panels (325 lines)
├── _cicd.html                CI/CD card + live panels + generate (308 lines)
├── _docker.html              Docker card + live panels + modals (497 lines)
├── _docker_compose.html      Docker generate + operational actions (125 lines)
├── _k8s.html                 K8s card + live panels + all modals (806 lines)
├── _terraform.html           Terraform card + live panels + actions (306 lines)
├── _pages.html               Pages card + segment management (538 lines)
├── _pages_config.html        Pages config modal + features (509 lines)
├── _pages_sse.html           SSE build streaming + CI gen (462 lines)
├── _dns.html                 DNS & CDN card + live panels (219 lines)
├── setup/
│   ├── _shared.html          Validation system, env collision, infra catalog (222 lines)
│   ├── _k8s_helpers.html     Pure K8s classification utilities (135 lines)
│   ├── _git.html             Git setup wizard — 4 steps (510 lines)
│   ├── _github.html          GitHub setup wizard — 5 steps (760 lines)
│   ├── _docker.html          Docker setup wizard — 3 steps (94 lines)
│   ├── _cicd.html            CI/CD setup wizard — 5 steps (1,231 lines)
│   ├── _k8s.html             K8s setup wizard — 9 steps (54 lines)
│   ├── _terraform.html       Terraform setup wizard — 5 steps (707 lines)
│   ├── _dns.html             DNS setup wizard — 5 steps (634 lines)
│   └── _dispatch.html        openSetupWizard() router (31 lines)
└── README.md                 This file
```

---

## Per-File Documentation

### `_integrations.html` — Loader (36 lines)

Pure Jinja2 include orchestrator. No logic. Defines the `<script>` scope,
then includes all 12 modules. This file's only job is load order.

### `_init.html` — State & Tab Orchestrator (253 lines)

The brain of the Integrations tab.

| Function | What It Does |
|----------|-------------|
| `_fetchIntProjectStatus()` | GET `/api/project/status`, cache result for dependency hints |
| `_intStatus(key)` | Extract integration status from cached project status |
| `cardSetupBanner(icon, title, desc, wiz)` | Build prominent CTA banner for unconfigured integrations |
| `cardDepHint(depKey, depLabel, msg, wizKey)` | Render cross-dependency hint (e.g., "Docker needed for K8s") |
| `_fetchIntPrefs()` | GET `/api/devops/integration-prefs`, cache preferences |
| `loadIntegrationsTab(force)` | Main orchestrator — load all visible cards in parallel |
| `openIntPrefsModal()` | Preferences modal (auto/manual/hidden per card) |
| `_saveIntPrefs()` | POST preferences to backend |

**State variables:**

| Variable | Type | Purpose |
|----------|------|---------|
| `_intLoaded` | `boolean` | Guard against duplicate tab loads |
| `_intPrefs` | `Object\|null` | Cached user preferences per card |
| `_intProjectStatus` | `Object\|null` | Cached project status for dep hints |
| `_INT_CARDS` | `Object` | Card metadata registry (10 entries) |

**Card registry entry shape:**
```javascript
{
    loadFn: () => loadGitCard(),     // function to call
    cardId: 'int-git-card',          // DOM container ID
    badgeId: 'int-git-badge',        // status badge ID
    detailId: 'int-git-detail',      // detail panel ID
    label: '🔀 Git',                // display label
}
```

### `_git.html` — Git Card (319 lines)

| Function | What It Does |
|----------|-------------|
| `loadGitCard()` | Fetch git status, render branch/changes/commits |
| `gitCommitModal()` | Open modal with message input + stage all checkbox |
| `doGitCommit()` | POST `/api/git/commit` with message |
| `gitPull()` | `ensureGitAuth()` → POST `/api/git/pull` |
| `gitPush()` | `ensureGitAuth()` → POST `/api/git/push` |
| `gitLogModal()` | Open modal with recent commits list |
| `gitStashModal()` | Open modal with stash save/pop/list |
| `gitDiffModal()` | Open modal with staged/unstaged diff |
| `gitIgnoreWizard()` | 3-step wizard: analyze → preview → apply |

### `_github.html` — GitHub Card (325 lines)

| Function | What It Does |
|----------|-------------|
| `loadGitHubCard()` | Fetch gh status, render auth/repo/PR info |
| `_ghLiveTab(what, panelId)` | Live tab handler — PRs, runs, envs, secrets |
| `_ghCreateEnvModal()` | Modal to create a new GitHub environment |
| `_ghPushSecrets()` | Push local vault secrets to GitHub secrets |

**Live tabs:** PRs, Action Runs, Environments, Secrets & Vars.

Gates on `ensureGhReady()` before any live data fetch.

### `_cicd.html` — CI/CD Card (308 lines)

| Function | What It Does |
|----------|-------------|
| `loadCICard()` | Fetch CI status + runs, render provider info |
| `triggerWorkflow()` | `ensureGhReady()` → POST `/api/gh/actions/dispatch` |
| `_ciLiveTab(what, panelId)` | Live tabs — runs, workflows, coverage |
| `_ciGenerate(type)` | Generate CI workflow file via modal preview |

### `_docker.html` — Docker Card (497 lines)

The largest card. Handles three states: not installed, daemon off, daemon running.

| Function | What It Does |
|----------|-------------|
| `loadDockerCard()` | Fetch docker status, render containers/images/compose |
| `_dockerLiveTab(what, panelId)` | Live tabs — containers, images, compose, networks, volumes |
| `_intDockerGenerate(type)` | Modal for Dockerfile/dockerignore/compose generation |
| `_dockerImagePull()` | Pull image modal with progress |
| `_dockerExec(container)` | Container exec terminal |
| `_dockerLogs(container)` | Container log viewer |
| `_dockerInspect(container)` | Container inspect JSON viewer |
| `_dockerRemove(container)` | Container remove with confirmation |

### `_docker_compose.html` — Docker Actions (125 lines)

| Function | What It Does |
|----------|-------------|
| `_dockerGenDockerfile(stack)` | Generate Dockerfile for a specific stack |
| `_dockerWriteGen()` | Write generated file to disk |
| `_intDockerAction(action, btn)` | Execute: up, down, restart, build, build-nc, prune |

### `_k8s.html` — Kubernetes Card (806 lines)

The most complex card. Handles kubectl detection, manifest scanning,
cluster status, resource management, and multiple generation modals.

| Function | What It Does |
|----------|-------------|
| `_intLoadK8sCard()` | Fetch K8s status, render resources/manifests |
| `_k8sLiveTab(what, panelId)` | Live tabs — cluster, pods, services, deployments, events, Skaffold, env map |
| `_k8sAction(action, btn)` | validate, dry-run with progress |
| `_k8sApplyModal()` | Confirm-and-apply modal |
| `_k8sRolloutModal()` | Rollout restart modal |
| `_k8sScaleModal()` | Scale deployment modal |
| `_k8sDescribeModal(type, name)` | kubectl describe viewer |
| `_k8sDeleteModal(type, name)` | Delete resource with confirmation |
| `_k8sPodLogs(name)` | Pod log viewer |
| `_k8sGenManifest()` | Generate manifest modal |
| `_k8sHelmModal()` | Helm values + install modal |
| `_k8sWizardModal()` | Full K8s wizard launch |

### `_terraform.html` — Terraform Card (306 lines)

| Function | What It Does |
|----------|-------------|
| `_intLoadTerraformCard()` | Fetch TF status, render providers/resources |
| `_tfLiveTab(what, panelId)` | Live tabs — state, workspaces, outputs |
| `_tfAction(action, btn)` | Execute: init, plan, apply, destroy, fmt, validate |
| `_tfSwitch(workspace)` | Switch Terraform workspace |
| `_tfGenerateModal()` | Generate TF config modal |

### `_pages.html` — Pages Card (538 lines)

Manages static site segments with a build pipeline.

| Function | What It Does |
|----------|-------------|
| `loadPagesCard()` | Fetch segments + builders, render pipeline status |
| `pagesInit()` | Re-initialize segments from content_folders |
| `addSegmentModal()` | Add new segment modal |
| `removeSegment(name)` | Remove segment with confirmation |
| `installBuilder(name)` | Install missing builder via `installWithPlan()` |
| `_pagesBuilderReInit(name)` | Re-initialize builder settings |
| `_pagesSegmentWizard()` | Multi-step segment config wizard |

### `_pages_config.html` — Pages Configuration (509 lines)

| Function | What It Does |
|----------|-------------|
| `configureSegment(name, path)` | Open config modal for a segment |
| `renderFeatures()` | Dynamic feature toggles from API registry |
| `buildSegment(name)` / `buildAll()` | Trigger build(s) |
| `deployPages()` | `ensureGitAuth()` → push to GitHub Pages |
| `mergePages()` | Merge all segments into unified site |

Supports dynamic config fields from builder schema (text, select,
textarea, bool), grouped by category.

### `_pages_sse.html` — SSE Build Streaming (462 lines)

| Function | What It Does |
|----------|-------------|
| `buildSegmentStream(name, opts)` | Open build modal + SSE stream |
| `_makeStageCard(name, label)` | Create collapsible stage card element |
| `_setStageStatus(name, status, detail)` | Update stage indicator |
| `_addStageLine(name, line)` | Batched log line rendering (RAF) |
| `_flushStageLog(name)` | Flush buffered log lines to DOM |
| `abortBuild()` | Kill SSE stream + cleanup |
| `closeBuildModal()` | Close/minimize build modal |
| `_ciGenerateWorkflow()` | Generate CI workflow for Pages |
| `_ciDeploymentStep(wfName)` | Add deployment step to workflow |
| `timeSince(dateStr)` | Human-readable time ago |

Uses `requestAnimationFrame` batching to prevent UI freeze during
high-volume SSE log output.

### `_dns.html` — DNS & CDN Card (219 lines)

| Function | What It Does |
|----------|-------------|
| `_intLoadDnsCard()` | Fetch DNS status, render domains/CDN/certs |
| `_intDnsLiveTab(what, panelId)` | Live tabs — lookup, SSL check, records |
| `_intDnsDoLookup()` | DNS lookup tool in live panel |
| `_intDnsDoSsl()` | SSL certificate checker in live panel |

---

## Setup Wizard Documentation

### `setup/_shared.html` — Shared Infrastructure (222 lines)

| Function / System | What It Does |
|-------------------|-------------|
| `_wizForceRescan` | Global flag — when true, detect steps add `?bust=1` |
| `_wizDetectBanner(key)` | Cache age banner with "Re-scan" button |
| `_wizValidation` | Registry-based validation system |
| `_wizValidation.register(scope, name, fn)` | Register a validator for a scope (`*`, `k8s`, `dk`) |
| `_wizValidation.recheck(prefix)` | Run all validators for a scope |
| env collision validator | Scans all env rows, detects duplicate keys across services |
| `_setElsewhere(show, ownerSvcId)` | Toggle vault notice when collision exists |
| `_infraOptions`, `_infraCategories` | Infrastructure service catalog from DataRegistry |

### `setup/_k8s_helpers.html` — K8s Utilities (135 lines)

Pure classification functions exposed on `window`:

| Function | What It Does |
|----------|-------------|
| `_k8sModClass(mod)` | Classify project module: library/docs/ops-tool/deployable |
| `_k8sSvcClass(svc, moduleNames)` | Classify compose service: application/infrastructure |
| `_classifyWorkloadKind(svc)` | Pick K8s kind: Deployment/StatefulSet/DaemonSet/Job/CronJob |
| `_kindIcon(kind)` | Kind → emoji icon |
| `_kindHint(kind, svc)` | Kind → explanatory hint text |
| `_k8sImageName(svc, ghRepo)` | Resolve best container image name |
| `_k8sPrimaryPort(svc)` | Get primary port from compose ports array |

### `setup/_dispatch.html` — Router (31 lines)

Single function: `openSetupWizard(key)` → routes to the correct wizard.
Must load AFTER all wizard files.

### Setup Wizard Summary

| Wizard | File | Lines | Steps | Backend Route |
|--------|------|-------|-------|--------------|
| Git | `setup/_git.html` | 510 | 4 | POST `/api/wizard/setup` |
| GitHub | `setup/_github.html` | 760 | 5 | POST `/api/wizard/setup` |
| Docker | `setup/_docker.html` | 94 | 3 | POST `/api/docker/generate/write` |
| K8s | `setup/_k8s.html` | 54 | 9 | POST `/api/wizard/setup` |
| CI/CD | `setup/_cicd.html` | 1,231 | 5 | POST `/api/wizard/setup` |
| Terraform | `setup/_terraform.html` | 707 | 5 | POST `/api/wizard/setup` |
| DNS | `setup/_dns.html` | 634 | 5 | POST `/api/wizard/setup` |

The Docker and K8s setup wizards are small entry points because their
step logic is split into raw JS includes in separate directories
(`docker_wizard/`, `k8s_wizard/`).

---

## Dependency Graph

### Internal Dependencies

```
_init.html                   ← standalone, defines all shared state
    ↑
_git.html                    ← uses card registry, cardCached, cardStore
_github.html                 ← uses card registry + ensureGhReady (from auth/)
_cicd.html                   ← uses card registry + ensureGhReady
_docker.html                 ← uses card registry
    ↑
_docker_compose.html         ← extends Docker card (generate + actions)
    ↑
_k8s.html                    ← uses card registry + cardDepHint
_terraform.html              ← uses card registry
_pages.html                  ← uses card registry
    ↑
_pages_config.html           ← extends Pages card (config modal)
_pages_sse.html              ← extends Pages card (SSE streaming)
    ↑
_dns.html                    ← uses card registry
```

### External Dependencies

```
globals/_api.html            ← api(), apiPost(), esc(), toast()
globals/_cache.html          ← cardCached(), cardStore(), cardInvalidate()
globals/_card_builders.html  ← cardStatusGrid(), cardDetectionList(),
                               cardDataTable(), cardActionToolbar(),
                               cardGenerateToolbar(), cardLivePanel(),
                               cardEmpty(), cardCrossLink()
globals/_modal.html          ← modalOpen(), modalClose(), modalError()
globals/_missing_tools.html  ← renderMissingTools()
globals/_ops_modal.html      ← installWithPlan() (used by Pages builders)
auth/_git_auth.html          ← ensureGitAuth() (git push/pull)
auth/_gh_auth.html           ← ensureGhReady() (GitHub live tabs)
wizard/_wizard_modal.html    ← wizardModalOpen() (setup wizards)
```

### Setup Wizard Dependencies

```
setup/_shared.html           ← must load FIRST (validation, infra catalog)
setup/_k8s_helpers.html      ← must load BEFORE setup/_k8s.html
    ↑
setup/_git.html              ← depends on _shared
setup/_github.html           ← depends on _shared
setup/_docker.html           ← depends on _shared + docker_wizard/ includes
setup/_k8s.html              ← depends on _shared + _k8s_helpers + k8s_wizard/ includes
setup/_cicd.html             ← depends on _shared
setup/_terraform.html        ← depends on _shared
setup/_dns.html              ← depends on _shared
    ↑
setup/_dispatch.html         ← must load LAST (routes to all wizards)
```

---

## Consumers

### Tab Loading

| File | How |
|------|-----|
| `dashboard.html` (line 69) | `{% include 'scripts/integrations/_integrations.html' %}` |
| `dashboard.html` (line 54) | `{% include 'scripts/integrations/setup/_dispatch.html' %}` |
| `partials/_tab_integrations.html` | HTML structure (cards, badges, detail panels) |

### Cross-Domain References

| Consumer | What It Calls | Why |
|----------|--------------|-----|
| `wizard/_integration_actions.html` | `openSetupWizard(key)` | Main wizard offers integration setup |
| `content/_browser.html` | `buildSegmentStream(name)` | Content browser triggers page builds |
| `devops/*.html` | Various live tab functions | DevOps tab cross-links to integration ops |

### API Endpoints Used

| Integration | Status Route | Action Routes |
|-------------|-------------|---------------|
| Git | `/api/git/status` | `/api/git/commit`, `/api/git/push`, `/api/git/pull`, `/api/git/log`, `/api/git/stash/*`, `/api/git/diff` |
| GitHub | `/api/integrations/gh/status` | `/api/gh/pulls`, `/api/gh/actions/*`, `/api/gh/environments`, `/api/gh/secrets` |
| CI/CD | `/api/ci/status`, `/api/gh/actions/runs` | `/api/gh/actions/dispatch`, `/api/ci/workflows`, `/api/ci/generate/*` |
| Docker | `/api/docker/status` | `/api/docker/up`, `/api/docker/down`, `/api/docker/restart`, `/api/docker/build`, `/api/docker/prune`, `/api/docker/containers`, `/api/docker/images`, `/api/docker/networks`, `/api/docker/volumes` |
| K8s | `/api/k8s/status` | `/api/k8s/cluster`, `/api/k8s/pods`, `/api/k8s/services`, `/api/k8s/deployments`, `/api/k8s/events`, `/api/k8s/apply`, `/api/k8s/validate` |
| Terraform | `/api/terraform/status` | `/api/terraform/state`, `/api/terraform/workspaces`, `/api/terraform/output`, `/api/terraform/action/*` |
| Pages | `/api/pages/segments`, `/api/pages/builders` | `/api/pages/build-stream/*`, `/api/pages/merge`, `/api/pages/deploy`, `/api/pages/init` |
| DNS | `/api/dns/status` | `/api/dns/lookup`, `/api/dns/ssl-check` |

---

## Advanced Feature Showcase

### 1. Preference-Gated Parallel Card Loading

Each integration card has a user-configurable preference (auto/visible/manual/hidden).
The tab loader reads these, applies visibility, then loads all `auto`+`visible` cards
in parallel using `Promise.allSettled`:

```javascript
// _init.html — lines 109-190
async function loadIntegrationsTab(force) {
    if (force) {
        _intLoaded = false;
        _intPrefs = null;
        _intProjectStatus = null;
        cardInvalidate('project-status');
        for (const [key, meta] of Object.entries(_INT_CARDS)) {
            const cacheKey = key.replace('int:', '');
            cardInvalidate(cacheKey);
            if (typeof _store !== 'undefined') delete _store[cacheKey];
            // Show spinners while reloading
            const detail = document.getElementById(meta.detailId);
            if (detail) detail.innerHTML = '<span class="spinner"></span>';
        }
        await api('/devops/cache/bust', { method: 'POST', ... }).catch(() => {});
    }
    if (_intLoaded) return;

    await _fetchIntProjectStatus();
    const prefs = await _fetchIntPrefs();

    for (const [key, meta] of Object.entries(_INT_CARDS)) {
        const pref = prefs[key] || 'auto';
        if (pref === 'hidden') { card.style.display = 'none'; continue; }
        if (pref === 'manual') {
            // Show "▶ Load" button instead of fetching
            detail.innerHTML = `<button onclick="...">▶ Load ${meta.label}</button>`;
            continue;
        }
    }

    // Load auto + visible cards in parallel (server is threaded)
    const autoCards = Object.entries(_INT_CARDS)
        .filter(([key]) => (prefs[key] || 'auto') !== 'hidden' && (prefs[key] || 'auto') !== 'manual');

    await Promise.allSettled(autoCards.map(async ([key, meta]) => {
        try { await meta.loadFn(); }
        catch (err) { /* show error badge + message per card */ }
    }));

    _intLoaded = true;
}
```

The card metadata registry (`_INT_CARDS`) maps 8 integration keys to
their load functions, DOM element IDs, and labels — a single source of
truth used by loading, preferences, and refresh logic.

### 2. Multi-Stage SSE Build Pipeline with Batched Log Rendering

The Pages build system streams real-time logs via SSE. The most advanced
pattern is the **batched log rendering** that prevents UI freeze during
high-frequency log output:

```javascript
// _pages_sse.html — lines 182-221
const _logBuffers = {};  // stageName → { lines: [], scheduled: false }

function _addStageLine(stageName, line) {
    const info = stages[stageName];
    info.lineCount++;

    // Buffer the line instead of writing to DOM immediately
    if (!_logBuffers[stageName]) {
        _logBuffers[stageName] = { lines: [], scheduled: false };
    }
    _logBuffers[stageName].lines.push(line);

    // Schedule a flush if not already scheduled
    if (!_logBuffers[stageName].scheduled) {
        _logBuffers[stageName].scheduled = true;
        requestAnimationFrame(() => _flushStageLog(stageName));
    }
}

function _flushStageLog(stageName) {
    const buf = _logBuffers[stageName];
    const info = stages[stageName];

    // Batch write all buffered lines at once
    info.logEl.textContent += buf.lines.join('\n') + '\n';
    buf.lines = [];
    buf.scheduled = false;

    // Single scroll + counter update
    info.logEl.scrollTop = info.logEl.scrollHeight;
    const linesEl = info.el.querySelector('.stage-lines');
    linesEl.textContent = info.lineCount;
}
```

Without batching, each SSE `log` event would trigger a DOM write + scroll.
At 100+ lines/sec during a build, this freezes the UI. The
`requestAnimationFrame` batching coalesces all lines received within
one frame into a single DOM write.

The build modal also supports:
- **Per-stage collapsible cards** with status icons (pending/running/done/error/skipped)
- **Per-stage live timers** (line 243-252)
- **Pipeline total timer** (line 117-121)
- **Minimize without abort** — closing the modal hides it but the SSE stays alive (line 49)
- **Escalating retry** — Retry → Clean Retry → Full Rebuild (lines 380-383)

### 3. Tri-State Card Rendering (Docker)

Every integration card renders three distinct UIs based on detection state.
Docker's card is the clearest example with three paths:

```javascript
// _docker.html — loadDockerCard() lines 8-179
// Path 1: Not installed (!data.available)
//   → "Not installed" badge, setup banner, install button,
//     but STILL shows detected files (Dockerfiles, compose)

// Path 2: Daemon not running (!data.daemon_running)
//   → "Daemon off" badge, CLI version shown, systemctl hint,
//     detected files, fewer generate options

// Path 3: Daemon running (full card)
//   → Service count badge, status grid, Dockerfile detail parsing,
//     7 live tabs, 8 action buttons, generate toolbar, cross-tab link
```

Even in "not installed" state, the card detects and shows existing Docker
files so the user knows configs exist before installing the tool:

```javascript
// _docker.html — lines 29-34
const hasFiles = (data.dockerfiles && data.dockerfiles.length) || data.has_compose;
if (hasFiles) {
    html += cardDetectionList([
        ...(data.dockerfiles||[]).map(f => ({
            icon: '📄', label: 'Dockerfile', value: f,
            click: `openFileInEditor('${esc(f)}','edit')`
        })),
        ...(data.has_compose ? [{ icon: '📋', label: 'Compose', ... }] : []),
    ]);
}
```

### 4. K8s Manifest Wizard with Multi-Resource Tabbing

The K8s wizard allows building multiple resources (Deployment, Service,
Ingress, ConfigMap, etc.) in a single modal with live preview:

```javascript
// _k8s.html — lines 709-791
function _k8sWizardModal() {
    // ...
    window._kwRes = []; window._kwIdx = -1; window._kwGen = null;
    _kwAddResource();  // seed first resource
}

function _kwAddResource() {
    window._kwRes.push({
        kind: 'Deployment', name: `res-${window._kwRes.length+1}`,
        namespace: 'default', spec: { image: '', port: 8080, replicas: 1 }
    });
    window._kwIdx = window._kwRes.length - 1;
    _kwRenderTabs(); _kwRenderForm();
}

// Tabs render dynamically with remove buttons
function _kwRenderTabs() {
    c.innerHTML = window._kwRes.map((r, i) =>
        `<button class="btn btn-sm ${i===window._kwIdx?'btn-primary':'btn-ghost'}"
            onclick="_kwSelectResource(${i})">
            ${esc(r.kind)}:${esc(r.name)}
            ${window._kwRes.length>1?
                `<span onclick="event.stopPropagation();_kwRemoveResource(${i})"
                 style="color:var(--error)">✕</span>`:''
            }
        </button>`
    ).join('');
}

// Form adapts to resource kind
function _kwRenderForm() {
    const r = window._kwRes[window._kwIdx];
    if (['Deployment','StatefulSet','DaemonSet'].includes(r.kind)) {
        extra = /* image, port, replicas fields */;
    } else if (r.kind === 'Service') {
        extra = /* port, type fields */;
    } else if (r.kind === 'Ingress') {
        extra = /* host, port fields */;
    }
}
```

The preview is generated server-side (`/k8s/generate/wizard`) and includes
all resources combined. Writing to disk iterates each file and calls
the shared file-write endpoint.

### 5. Deployment Readiness & Strategy Inference

The K8s card infers the deployment strategy from project structure and
shows readiness status using a state map:

```javascript
// _k8s.html — lines 69-86
if (data.deployment_strategy && data.deployment_strategy !== 'none') {
    const stratLabel = {
        raw_kubectl: 'Raw kubectl', helm: 'Helm', kustomize: 'Kustomize',
        skaffold: 'Skaffold', mixed: 'Mixed',
    }[data.deployment_strategy] || data.deployment_strategy;
    stats.push({ label: 'Strategy', value: stratLabel });
}
if (data.deployment_readiness) {
    const rdyMap = {
        ready:          { value: 'Ready',          cls: 'ok' },
        needs_config:   { value: 'Needs config',   cls: 'warn' },
        needs_tools:    { value: 'Needs tools',    cls: 'warn' },
        not_configured: { value: 'Not configured', cls: 'muted' },
    };
    const rdy = rdyMap[data.deployment_readiness] || { value: data.deployment_readiness };
    stats.push({ label: 'Readiness', ...rdy });
}
```

Combined with tool availability scanning (lines 88-98), this shows a
full operational picture: tools installed, strategy detected, readiness
assessed — all in the card's status grid.

### 6. Secret Safety Analysis

The K8s card renders security warnings when it detects raw Kubernetes
Secrets without encryption or envsubst variables without environment setup:

```javascript
// _k8s.html — lines 117-135
if (data.secret_safety) {
    const ss = data.secret_safety;
    const warnings = [];
    if (ss.has_raw_secrets && !ss.has_secret_generator) {
        warnings.push('⚠️ Raw Secret manifests detected — consider using '
            + 'secretGenerator or external-secrets');
    }
    if (ss.has_envsubst_vars) {
        const vars = (ss.envsubst_vars || []).join(', ');
        warnings.push(`⚠️ envsubst variables detected: ${vars} `
            + '— ensure these are set before apply');
    }
    if (warnings.length > 0) {
        html += `<div>`;
        warnings.forEach(w => {
            html += `<div style="color:var(--warning)">${esc(w)}</div>`;
        });
        html += `</div>`;
    }
}
```

This is a frontend-level security gate — the backend scans manifests for
raw `kind: Secret` without `secretGenerator` and for `${VAR}` patterns
that would expand to empty strings if unset.

### 7. Cross-Integration Dependency Hints

Cards can declare dependencies on other integrations. The dependency hint
system checks the project status cache and renders contextual setup prompts:

```javascript
// _init.html — lines 60-70
function cardDepHint(depKey, depLabel, message, wizKey) {
    const dep = _intStatus(depKey);
    if (dep.status === 'ready') return '';  // dependency OK — no hint
    const btn = wizKey
        ? ` <button onclick="openSetupWizard('${wizKey}')">Set up ${depLabel} →</button>`
        : '';
    return `<div class="card-dep-hint">
        <span>💡</span>
        <span>${esc(message)}${btn}</span>
    </div>`;
}

// Usage in K8s card (_k8s.html line 102):
html += cardDepHint('docker', 'Docker',
    'Build a container image for your app to deploy to K8s.', 'docker');

// Usage in Docker card (_docker.html line 86):
html += cardDepHint('git', 'Git',
    'Set up Git first to version-control your Docker config.', 'git');
```

The hint only renders when the dependency is not ready. When the user
sets up the dependency and returns, the hint disappears automatically
on next card load.

### 8. Dockerfile Detail Parsing with Multi-Stage Detection

The Docker card doesn't just detect Dockerfiles — it parses their contents
and displays base images, stage count, ports, and build warnings:

```javascript
// _docker.html — lines 97-120
const dfDetails = data.dockerfile_details || [];
(data.dockerfiles||[]).forEach((f, i) => {
    const detail = dfDetails[i];
    let desc = f;
    if (detail) {
        const parts = [];
        if (detail.base_images && detail.base_images.length) {
            const unique = [...new Set(detail.base_images)];
            parts.push(unique.join(', '));  // e.g. "python:3.11, nginx:alpine"
        }
        if (detail.stage_count > 1) parts.push(`${detail.stage_count}-stage`);
        if (detail.ports && detail.ports.length) parts.push(`ports: ${detail.ports.join(', ')}`);
        if (parts.length) desc = `${f}  ·  ${parts.join(' · ')}`;
    }
    detections.push({ icon: '📄', label: 'Dockerfile', value: desc, ... });

    // Show warnings for malformed Dockerfiles
    if (detail && detail.warnings && detail.warnings.length) {
        detail.warnings.forEach(w => {
            detections.push({ icon: '⚠️', label: 'Warning', value: w, cls: 'warning' });
        });
    }
});
```

A 3-stage Dockerfile with nginx and python renders as:
`Dockerfile  ·  python:3.11, nginx:alpine  ·  3-stage  ·  ports: 80, 8080`

---

### Feature Coverage Summary

| Feature | File | Key Functions | Complexity |
|---------|------|--------------|------------|
| Card metadata registry (8 integrations) | `_init.html` | `_INT_CARDS`, `loadIntegrationsTab()` | Parallel loading with preference gating |
| Preference persistence (auto/visible/manual/hidden) | `_init.html` | `openIntPrefsModal()`, `_saveIntPrefs()` | Server-synced per-card visibility |
| Cross-integration dependency hints | `_init.html` | `cardDepHint()`, `_intStatus()`, `_fetchIntProjectStatus()` | Cached project status check |
| Setup CTA banners | `_init.html` | `cardSetupBanner()` | Wizard-linked setup prompts |
| Cross-tab navigation | `_init.html` | `cardCrossLink()` | Deep links between tab views |
| Multi-state Docker card (3 paths) | `_docker.html` | `loadDockerCard()` | Not installed / daemon off / running |
| Dockerfile detail parsing | `_docker.html` | Per-file detail rendering | Base images, stages, ports, warnings |
| Docker live tabs (7 panels) | `_docker.html` | `_dockerLiveTab()` | Containers, images, compose, stats, logs, networks, volumes |
| Docker exec modal | `_docker.html` | `_dockerExecModal()`, `_dockerExecRun()` | Running container selection + command execution |
| Docker pull modal | `_docker.html` | `_dockerPullModal()`, `_dockerPullExec()` | Image pull with live output |
| Docker compose actions (6) | `_docker_compose.html` | `_intDockerAction()` | up/down/restart/build/build-nc/prune |
| K8s live tabs (9 panels) | `_k8s.html` | `_k8sLiveTab()` | pods/services/deployments/cluster/events/namespaces/helm/skaffold/envmap |
| K8s deployment strategy inference | `_k8s.html` | Status grid rendering | raw_kubectl/helm/kustomize/skaffold/mixed |
| K8s deployment readiness | `_k8s.html` | Readiness state map | ready/needs_config/needs_tools/not_configured |
| K8s secret safety analysis | `_k8s.html` | Warning rendering | Raw secrets + envsubst detection |
| K8s resource summary chips | `_k8s.html` | Resource kind counts | Visual chip rendering |
| K8s manifest wizard | `_k8s.html` | `_k8sWizardModal()`, `_kwAddResource()` | Multi-resource tabbing + live preview |
| K8s Helm operations | `_k8s.html` | `_k8sHelmInstallModal()`, `_k8sHelmDoInstall()` | Install/upgrade/template with dry-run |
| SSE build pipeline streaming | `_pages_sse.html` | `buildSegmentStream()`, `streamSSE` reader | Per-stage cards with batched log rendering |
| Batched log rendering | `_pages_sse.html` | `_addStageLine()`, `_flushStageLog()` | requestAnimationFrame coalescing |
| Per-stage timers | `_pages_sse.html` | `_startStageTimer()`, `_stopStageTimer()` | 100ms resolution with cleanup |
| Minimize-without-abort | `_pages_sse.html` | `closeBuildModal()` | SSE stream survives modal close |
| Git commit summary | `_git.html` | `loadGitCard()` | Branch, status, recent commits |
| GitHub integration card | `_github.html` | `loadGitHubCard()` | Repo info, PRs, actions status |
| CI/CD pipeline status | `_cicd.html` | `loadCICard()` | Workflow detection + run status |
| Terraform card | `_terraform.html` | `_intLoadTerraformCard()` | State file, resources, providers |
| DNS/CDN card | `_dns.html` | `_intLoadDnsCard()` | Record listing + provider detection |
| Pages segment card | `_pages.html` | `loadPagesCard()` | Multi-segment listing + build controls |
| Pages config modal | `_pages_config.html` | `_pagesConfigModal()` | Dynamic form from builder schema |

---

## Design Decisions

### Why a single `<script>` scope instead of modules?

All integration modules share one `<script>` tag injected by
`_integrations.html`. This means every function is globally visible
within the scope. The alternative — ES modules — would require
a build step (bundler) and import/export declarations, which this
project deliberately avoids. The Jinja2 `{% include %}` approach
gives module-level organization (separate files) without build
tooling. The trade-off is no encapsulation — naming conventions
(`_intDockerAction`, `_tfLiveTab`) prevent collisions manually.

### Why is `_k8s.html` so large (806 lines)?

Kubernetes has the most complex state space: kubectl not found,
manifests not found, cluster not connected, multiple resource types,
secret safety warnings, validation, apply, rollout, scale, describe,
delete, pod logs, manifest generation, Helm, and a full wizard.
Each of these is a distinct UI concern that needs its own handler.
Splitting further would require passing card context between files,
which in the shared-scope model means more global state.

### Why separate `_docker.html` and `_docker_compose.html`?

The Docker card (`_docker.html`) handles detection, status, and live
data panels. Compose actions (up/down/restart/build) and file
generation are operationally distinct — they're imperative actions
rather than read-only status. Separating them keeps the card file
focused on display and the compose file focused on mutations.

### Why are Pages split across three files?

Pages has three distinct concerns:
1. **Card** (`_pages.html`) — segment listing, pipeline status
2. **Config** (`_pages_config.html`) — per-segment configuration modal
   with dynamic fields from builder schema
3. **SSE** (`_pages_sse.html`) — real-time build streaming with
   stage cards, batched log rendering, elapsed timers

Each is large enough (460-540 lines) to justify its own file.
Merging them would create a 1,500+ line monolith.

### Why do setup wizards use `wizardModalOpen()` while cards use `modalOpen()`?

Cards use `modalOpen()` for simple one-shot modals (confirm, input, preview).
Setup wizards need multi-step navigation with state persistence, step
indicators, back/next/finish buttons, and data collection across steps.
`wizardModalOpen()` (from `wizard/_wizard_modal.html`) provides all of
this infrastructure. Using `modalOpen()` for wizards would require
reimplementing step management in every wizard.

### Why is `setup/_docker.html` only 94 lines?

The Docker setup wizard's step logic is split into raw JS includes in
`docker_wizard/` (step1_detect, step2_configure, step3_preview).
The `_docker.html` file is just the entry point that defines helpers,
calls `wizardModalOpen()`, and handles `onComplete`. The actual
wizard complexity lives in the sub-files.

### Why `setup/_k8s_helpers.html` as a separate file?

K8s classification logic (module classification, workload kind
detection, image name resolution) is used by both the K8s card
(`_k8s.html`) and the K8s setup wizard (`setup/_k8s.html`).
Extracting it into a shared helpers file prevents duplication.
The helpers are pure functions with no side effects — they classify
data without touching the DOM.

### Why does `_cicd.html` at 1,231 lines not need splitting?

The CI/CD setup wizard is already a single-concern file: one wizard
with 5 steps. Each step's `render()` function is large because of
the complex env var configuration UI (injection types, vault
references, secret selectors, duplicate detection). The steps are
sequential and share state heavily — splitting by step would
fragment interdependent logic.

### Why registervalidation with scopes instead of per-wizard?

The `_wizValidation` system uses scopes (`*`, `k8s`, `dk`) so that
cross-cutting validators (like env key collision detection) can run
for multiple wizards without registering separately in each. The `*`
scope runs for ALL wizards. Integration-specific scopes only run
when that wizard is active. This is more maintainable than having
each wizard duplicate the same validation logic.
