# Wizard — Front-End Scripts

> **9 files · 5,263 lines · The entire Setup Wizard tab + wizard modal system.**
>
> This domain owns two related systems: (1) the **Setup Wizard tab** —
> a 6-step guided project configuration flow, and (2) the **Wizard Modal
> system** — a reusable multi-step modal framework used by every
> integration setup wizard across the application.

---

## How It Works

### Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│ dashboard.html                                                      │
│                                                                      │
│  {% include 'partials/_tab_wizard.html' %}               ← HTML     │
│  {% include 'scripts/wizard/_wizard.html' %}             ← JS tab   │
│  {% include 'scripts/wizard/_setup.html' %}              ← JS modal │
│  {% include 'scripts/wizard/_modal.html' %}              ← JS lib   │
│                                                                      │
│  _wizard.html wraps the TAB modules in a single <script> scope.     │
│  _setup.html and _modal.html are separate <script> elements —       │
│  they're usable independently of the wizard tab.                    │
└────────────────────────────────────────────────────────────────────┘
```

### Two Distinct Systems

This domain contains **two systems** sharing the "wizard" name:

```
┌─────────────────────────────────────────────────────────────────┐
│  System 1: Setup Wizard Tab (6 modules, shared <script> scope)  │
│                                                                  │
│  _wizard.html  → _init.html → _steps.html → _helpers.html      │
│                → _integrations.html → _integration_actions.html │
│                → _nav.html                                       │
│                                                                  │
│  Purpose: 6-step project setup flow                              │
│  Steps: Welcome → Modules → Secrets → Content → Int. → Review   │
├─────────────────────────────────────────────────────────────────┤
│  System 2: Wizard Modal Library (2 standalone files)             │
│                                                                  │
│  _modal.html   → wizardModalOpen() / wizardModalClose()         │
│  _setup.html   → openFullSetupWizard() (uses wizardModalOpen)   │
│                                                                  │
│  Purpose: Reusable multi-step modal framework                    │
│  Consumers: Integration setup wizards (Git, Docker, K8s, etc.)  │
└─────────────────────────────────────────────────────────────────┘
```

### Module Loading Order (Tab)

```
_wizard.html                       ← Loader (24 lines)
    │
    ├── _init.html                  ← Config load, state, step defs, renderWizard()
    ├── _steps.html                 ← All 6 step renderers (Welcome → Review)
    ├── _helpers.html               ← Module/domain/env/content/key helpers
    ├── _integrations.html          ← Integration card rendering + sub-wizard forms
    ├── _integration_actions.html   ← Docker/K8s/Terraform/DNS live panels + apply
    └── _nav.html                   ← Navigation, save, finish
```

### Wizard Tab Step Flow

```
 ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐   ┌──────────┐
 │ Welcome  │──→│ Modules  │──→│ Secrets  │──→│ Content  │──→│Integrations  │──→│  Review  │
 │   👋     │   │   🔍     │   │   🔐     │   │   📁     │   │    🔌        │   │   ✅     │
 │          │   │          │   │          │   │          │   │              │   │          │
 │ Name     │   │ Auto-    │   │ Vault    │   │ Content  │   │ Per-tool     │   │ Summary  │
 │ Desc     │   │ detect   │   │ status   │   │ folder   │   │ cards w/     │   │ of all   │
 │ Repo     │   │ or       │   │ GH       │   │ select   │   │ inline       │   │ config   │
 │ Domains  │   │ manual   │   │ integ.   │   │ Infra    │   │ sub-wizards  │   │ + Finish │
 │ Envs     │   │ add      │   │ Enc key  │   │ folders  │   │ & apply      │   │          │
 └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────────┘   └──────────┘
```

State is collected when **leaving** a step (not entering), so
navigating forward/backward always preserves form data. The URL
hash is synced (`#wizard/welcome`, `#wizard/modules`, etc.) for
bookmarkability.

### Wizard Modal Lifecycle

```
wizardModalOpen(opts)                    ← called by integration setup wizards
    │
    ├── Parse opts: title, steps[], onFinish(), assistantContext
    ├── Render modal overlay + step indicators
    ├── _wizModalRender() — render step[0]
    │     ├── Call step.render(data, el)
    │     ├── Activate assistant panel (if assistantContext set)
    │     └── Attach scroll shadow listener
    │
    ├── _wizModalNext()                  ← Next button
    │     ├── _wizModalCollect() — call step.collect(data)
    │     ├── _wizModalValidate() — call step.validate(data)
    │     └── _wizModalRender() for next step
    │
    ├── _wizModalBack()                  ← Back button
    │     ├── _wizModalCollect()
    │     └── _wizModalRender() for prev step
    │
    └── _wizModalFinish()                ← Finish button
          ├── _wizModalCollect()
          ├── _wizModalValidate()
          ├── Call opts.onFinish(data) — async
          ├── Show success toast
          └── wizardModalClose()
```

### Detection & Caching System

The integrations step uses a 3-tier caching strategy:

```
_wizFetchDetect(force)
    │
    ├── Level 1: In-memory (_wizIntDetection)
    │     └── Fastest — survives tab switches
    │
    ├── Level 2: sessionStorage (via wizCached('detect'))
    │     └── Survives within browser session
    │
    └── Level 3: API /api/wizard/detect (last resort)
          └── Backend also caches with staleness tracking
          └── force=true → bypass all + ?bust=1
```

### Integration Sub-Wizard Architecture

Step 5 (Integrations) embeds **per-integration sub-wizard forms**
inline within each card:

```
Integration card (e.g., Docker)
├── ☑ Checkbox (enable/hide)
├── Status badge (ready / installed / not_installed)
├── Detail text (from _wizCardDetails)
├── ⚙️ Setup button → toggles inline panel:
│     ├── Configuration form fields
│     ├── Live data panel (containers / images / compose)
│     ├── Action buttons (build, up, logs, etc.)
│     ├── ✅ Apply → validates + writes config
│     └── 🗑 Delete → removes generated config
└── 🚀 Full Setup → opens wizardModalOpen() for guided flow
```

The `_wizSubForms` object maps integration keys to render functions
that produce the inline sub-wizard UI.

---

## File Map

```
wizard/
├── _wizard.html              Loader — includes all tab modules (24 lines)
├── _init.html                Config load, state, step defs, renderWizard() (200 lines)
├── _steps.html               All 6 step renderers (727 lines)
├── _helpers.html             Module/domain/env/content/key helpers (415 lines)
├── _integrations.html        Integration cards + sub-wizard forms (2,051 lines)
├── _integration_actions.html Docker/K8s/Terraform/DNS live panels + apply (958 lines)
├── _nav.html                 Navigation (next/prev/goto), save, finish (151 lines)
├── _modal.html               Wizard modal framework (404 lines)
├── _setup.html               Full setup wizard (Detect→Select→Install→Done) (333 lines)
└── README.md                 This file
```

---

## Per-File Documentation

### `_wizard.html` — Loader (24 lines)

Pure Jinja2 include orchestrator. No logic. Assembles the 6 tab
modules into a single `<script>` scope.

### `_init.html` — State & Config (200 lines)

**State:**

| Variable | Type | Purpose |
|----------|------|---------|
| `_wizardConfig` | `Object` | Mutable config being edited (from `project.yml`) |
| `_wizIntDetection` | `Object` | Cached detection results for integrations step |
| `wizardDirty` | `boolean` | Dirty flag — unsaved changes exist |
| `currentWizardStep` | `number` | Current step index (0-based) |
| `wizardSteps` | `Array` | Step definitions: `{id, title, icon}` |

**Functions:**

| Function | What It Does |
|----------|-------------|
| `_wizFetchDetect(force)` | 3-tier cached fetch of `/api/wizard/detect` data |
| `wizardLoadConfig()` | Fetch config from `/api/config`, init state objects |
| `wizardCreateEnv(envName, btnEl)` | Quick-create a `.env` file for an environment |
| `wizardCreateGhEnv(envName, btnEl)` | Create a GitHub deployment environment |
| `renderWizard()` | Main render — sync URL hash, render step indicators, call step renderer, update nav buttons, activate assistant |

**Step Definitions:**

| Index | ID | Title | Icon |
|-------|------|------|------|
| 0 | `welcome` | Welcome | 👋 |
| 1 | `modules` | Modules | 🔍 |
| 2 | `secrets` | Secrets | 🔐 |
| 3 | `content` | Content | 📁 |
| 4 | `integrations` | Integrations | 🔌 |
| 5 | `review` | Review | ✅ |

### `_steps.html` — Step Renderers (727 lines)

Contains `_wizardRenderers` — an object with one `async` render
function per step.

**Step 1 — Welcome:**

| Renders | Details |
|---------|---------|
| Project Name | Required, text input |
| Description | Textarea |
| Repository | URL input |
| Domains | Tag list, add/remove |
| Environments | List with name/description, add/remove, inline edit, default selection |

**Step 2 — Modules:**

| Renders | Details |
|---------|---------|
| Auto-detected modules | Fetched via `wizardDetect()` |
| Module list | Cards with name, path, stack icon |
| Manual add | Name, path, stack selector, language |

**Step 3 — Secrets:**

| Renders | Details |
|---------|---------|
| Per-environment vault status | Async — fetches `/vault/status` per env |
| GitHub integration | Detects `GITHUB_TOKEN`, `GITHUB_REPOSITORY`, offers save |
| GitHub deployment envs | Shows create button for missing GH environments |
| Encryption key status | Shows configured/missing, generate/save actions |

**Step 4 — Content:**

| Renders | Details |
|---------|---------|
| Content folder scan | Fetches `/content/folders`, displays with toggle |
| Infrastructure folder scan | Infrastructure folders with existence status |
| Folder selection | Toggleable cards that update `_contentFolders` |

**Step 5 — Integrations:**

Delegates to `_wizRenderIntegrations()` from `_integrations.html`.
See that file's documentation below.

**Step 6 — Review:**

| Renders | Details |
|---------|---------|
| Project identity summary | Name, repo |
| Domains summary | Tag list |
| Environments summary | With default badge |
| Modules summary | Count + list |
| Content folders summary | Selected paths |

### `_helpers.html` — Core Helpers (415 lines)

| Function | What It Does |
|----------|-------------|
| `_wizardCollectWelcome()` | Gather name, description, repository from form inputs |
| `_wizardModuleRow(m, i)` | Render one module card with stack icon, path, remove button |
| `wizardAddModule()` | Add a module to config from form inputs |
| `wizardRemoveModule(i)` | Remove module at index, re-render |
| `wizardAddDomain()` | Add domain tag to config |
| `wizardRemoveDomain(el, domain)` | Remove domain tag |
| `wizardAddEnv()` | Add environment to config |
| `wizardRemoveEnv(i)` | Show removal confirmation modal with cleanup options |
| `wizardConfirmRemoveEnv(i)` | Execute removal — delete files, GH env, re-render |
| `wizardEditEnvField(i, field, spanEl)` | Inline edit of environment name/description |
| `wizardToggleContentFolder(name, checked)` | Toggle content folder inclusion |
| `wizardGenerateEncKey()` | Generate encryption key via `POST /api/content/setup-enc-key` |
| `wizardSaveGhRepo(repoValue, btnEl)` | Save detected `GITHUB_REPOSITORY` to `.env` |
| `wizardSaveEncKey()` | Save manually entered encryption key |
| `wizardDetect()` | Auto-detect project modules via `/api/wizard/detect` |
| `_wizCollectIntegrations()` | Collect integration checkbox states → `_wizardConfig._integrationPrefs` (in `_integration_actions.html`) |

**Environment removal flow:**

```
wizardRemoveEnv(i)
    │
    ├── Show confirmation modal:
    │     ☑ Delete .env.{name} file
    │     ☑ Delete GitHub environment
    │
    └── wizardConfirmRemoveEnv(i)
          ├── POST /api/env/cleanup { name, delete_files, delete_github }
          ├── Remove from config array
          ├── Reset default if needed
          └── toast + re-render
```

### `_integrations.html` — Integration Cards + Sub-Wizards (2,051 lines)

The largest file in the domain. Contains:

1. **Card rendering** — `_wizRenderIntegrations()` renders all
   integration and devops extension cards with detection data
2. **Card details** — `_wizCardDetails(d)` builds rich detail text
   from embedded detection data per integration
3. **Card component** — `_wizIntCard(key, info, enabled, desc)`
   renders one integration card with checkbox, status, setup toggle
4. **Sub-wizard forms** — `_wizSubForms{}` maps integration keys to
   inline configuration panels

**Card categories:**

| Category | Keys | Order |
|----------|------|-------|
| Source & Publishing | `int:git`, `int:github`, `int:pages` | Fixed |
| CI/CD | `int:ci` | Fixed |
| DevOps Extensions | `int:docker`, `k8s`, `terraform`, `dns` | Fixed |
| Remaining | Any other detected cards | Dynamic |

**Card detail enrichment sources:**

| Integration | Detection Data Used |
|-------------|-------------------|
| Git | `git_probe` → branch, remote, .gitignore, hooks |
| GitHub | `gh_cli_status`, `gh_user`, `gh_repo_info`, `gh_environments` |
| CI/CD | `ci_status` → providers, total workflows |
| Docker | `docker_status` → Dockerfile, compose, daemon |
| Pages | `pages_status` → segments, content folders |
| K8s | `k8s_status` → kubectl, context, cluster, readiness |
| Terraform | `terraform_status` → CLI, providers, backend, init state |
| DNS | `dns_status` → CDN providers, domains, SSL certs |

**Sub-wizard forms (`_wizSubForms`):**

Each sub-wizard renders a complete configuration panel:

| Key | Form Fields | Live Data | Actions |
|-----|------------|-----------|---------|
| `int:docker` | Base image, port, command, compose | Containers, images, compose status | Build, up, down, logs |
| `k8s` | App name, port, namespace, workload type | Validate, cluster info, pods, services | Apply manifests |
| `terraform` | Provider, region, project, backend | Validate, resources, workspaces, outputs | Apply config |
| `dns` | Domain, mail, CDN | DNS lookup, SSL check | Apply config |
| `int:ci` | Strategy, branches, language version | Pipeline compose preview | Generate pipeline, write files |
| `int:git` | Remote URL, method (SSH/HTTPS), init commit | — | Apply setup |
| `int:pages` | Segments, content folders, builders | — | Apply setup |
| `int:github` | Environment creation, secrets sync | — | Apply setup |

### `_integration_actions.html` — Live Panels & Actions (958 lines)

**Docker live panels:**

| Function | API | Data |
|----------|-----|------|
| `_wizDockerLive('containers')` | `GET /docker/containers?all=true` | List with name, status, image |
| `_wizDockerLive('images')` | `GET /docker/images` | List with tag, size |
| `_wizDockerLive('compose')` | `GET /docker/compose/status` | Service list with state |

**Docker streaming actions:**

| Function | Streaming API | Behavior |
|----------|--------------|----------|
| `_wizDockerAction('build')` | `POST /docker/stream/build` | SSE stream with progress log |
| `_wizDockerAction('up')` | `POST /docker/stream/up` | SSE stream, auto-scroll |
| `_wizDockerAction('down')` | `POST /docker/stream/down` | SSE stream |
| `_wizDockerAction('logs')` | `GET /docker/logs` | Synchronous fetch |

The streaming uses `ReadableStream` + `TextDecoder` with a
`requestAnimationFrame`-batched log renderer for smooth scrolling.
An `AbortController` enables cancellation of in-flight streams.

**K8s live panels:**

| Function | API | Data |
|----------|-----|------|
| `_wizK8sLive('validate')` | `GET /k8s/validate` | Manifest validation result |
| `_wizK8sLive('cluster')` | `GET /k8s/cluster` | Context, server, version, namespaces |
| `_wizK8sLive('pods')` | `GET /k8s/resources?kind=pods` | Pod list with status |
| `_wizK8sLive('services')` | `GET /k8s/resources?kind=services` | Service list |

**Terraform live panels:**

| Function | API | Data |
|----------|-----|------|
| `_wizTfLive('validate')` | `POST /terraform/validate` | Validation result |
| `_wizTfLive('state')` | `GET /terraform/state` | Resource list with providers |
| `_wizTfLive('workspaces')` | `GET /terraform/workspaces` | Workspace list + current |
| `_wizTfLive('outputs')` | `GET /terraform/output` | Output key/value pairs |

**DNS live panels:**

| Function | API | Data |
|----------|-----|------|
| `_wizDnsLive('lookup')` | Form → `GET /dns/lookup/{domain}` | Records by type |
| `_wizDnsLive('ssl')` | Form → `GET /dns/ssl/{domain}` | Cert subject, issuer, expiry |

**Operational actions:**

| Function | What It Does |
|----------|-------------|
| `_wizDeleteConfig(target, btnEl)` | DELETE `/wizard/config` with JSON body `{ target }` and confirmation |
| `_wizRedetect()` | Force re-scan → re-render integrations |
| `_wizComposeCi(btnEl)` | POST `/wizard/compose-ci` → generate CI pipeline files |
| `_wizWriteCiFiles(btnEl)` | POST `/wizard/setup` → write composed files to disk |
| `_wizApplySetup(key, btnEl)` | Collect form → validate → POST `/wizard/setup` → apply |
| `_wizInstallTool(tool, btnEl)` | POST `/audit/install-tool` → retry with sudo on permission error |
| `_wizCollectIntegrations()` | Collect all checkbox states into `_wizardConfig._integrationPrefs` |

**Apply setup flow:**

```
_wizApplySetup(key, btnEl)
    │
    ├── Collect form values via DOM queries
    │
    ├── Build payload with action: 'setup_{key}'
    │     ├── Docker: base_image, port, cmd, compose, overwrite
    │     ├── K8s: name, port, namespace, workload_type
    │     ├── CI: branches, language_version, deploy_method
    │     ├── Terraform: provider, region, backend
    │     ├── DNS: domain, mail, cdn, spf/dkim/dmarc
    │     ├── Git: remote_url, method, init_commit
    │     └── GitHub: environments, sync_secrets
    │
    ├── Validate (K8s namespace, Terraform provider)
    │     └── POST /wizard/validate
    │
    └── Apply
          └── POST /wizard/setup → success/partial/error toast
```

### `_nav.html` — Navigation & Save (151 lines)

| Function | What It Does |
|----------|-------------|
| `wizardNext()` | Collect current step state → advance → renderWizard() |
| `wizardPrev()` | Collect current step state → go back → renderWizard() |
| `wizardGoTo(idx)` | Jump to specific step (from indicators) |
| `wizardFinish()` | Collect all → POST `/config` → save prefs → seed envs → switch to dashboard → show next-steps modal |

**Finish flow:**

```
wizardFinish()
    │
    ├── Collect welcome + integrations state
    ├── Validate: project name required
    │
    ├── POST /api/config { config }
    │
    ├── Save integration prefs:
    │     ├── GET /api/devops/prefs (existing)
    │     ├── Merge wizard prefs over existing
    │     ├── PUT /api/devops/prefs (merged)
    │     └── Apply card visibility immediately (no reload)
    │
    ├── Seed envs (if multi-env):
    │     └── POST /api/env/seed { environments, default }
    │
    ├── Invalidate tab caches:
    │     ├── projectEnvironments = []
    │     ├── secretsLoaded = false
    │     └── _dashLoaded = false
    │
    ├── switchTab('dashboard')
    │
    └── setTimeout → _showPostWizardNextSteps() (600ms delay)
```

### `_modal.html` — Wizard Modal Framework (404 lines)

A **standalone, reusable** multi-step modal system. Used by all
integration setup wizards in `integrations/setup/`.

**Public API:**

| Function | What It Does |
|----------|-------------|
| `wizardModalOpen(opts)` | Open a new wizard modal with steps, data, and callbacks |
| `wizardModalClose()` | Close + cleanup (scroll listener, assistant refresh) |
| `wizardModalGoTo(idx)` | Jump to specific step from step indicator |

**wizardModalOpen options:**

| Option | Type | Purpose |
|--------|------|---------|
| `title` | `string` | Modal title |
| `size` | `'narrow'/'wide'` | Modal width |
| `steps` | `Array` | Step definitions with `title`, `render(data,el)`, `validate(data)`, `collect(data)` |
| `initialData` | `Object` | Shared data object passed to all step functions |
| `onComplete` | `async fn(data)` | Called when finish button clicked |
| `finishLabel` | `string` | Finish button text (default: '✅ Finish') |
| `finishCls` | `string` | Finish button CSS class |
| `assistantContext` | `string` | Catalogue context ID for assistant panel |

**Form helpers:**

| Function | What It Does |
|----------|-------------|
| `wizSection(title, subtitle, id)` | Section header with optional subtitle |
| `wizStatusRow(icon, label, value, type, rawValue, id)` | Detection status row |
| `wizFormGrid(fields)` | Grid layout of form fields via `modalFormField()` |
| `wizCollectFields(names, data)` | Bulk collect form values from `mfVal()` |

### `_setup.html` — Full Setup Wizard (333 lines)

A **standalone** 4-step wizard that uses `wizardModalOpen()` to
guide new users through initial setup.

**Steps:**

| Step | Function | What It Does |
|------|----------|-------------|
| 1 — Detect | `_wizardRenderStep1()` | Run environment detection, show tools/integrations found |
| 2 — Select | `_wizardRenderStep2()` | Card selection with auto-suggest, enable/hide toggles |
| 3 — Install | `_wizardRenderStep3()` | Show missing tools with install buttons |
| 4 — Save | `_wizardSaveAndFinish()` | Apply selected preferences, save prefs |

**Consumers:**

Called from the "getting started" flow on first launch via
`openFullSetupWizard()`.

---

## Dependency Graph

### Internal (Tab Modules)

```
_init.html                     ← standalone state + config
    ↑
_steps.html                    ← uses _wizardConfig, renderWizard, helpers
    ↑
_helpers.html                  ← uses _wizardConfig, renderWizard, api
    ↑
_integrations.html             ← uses _wizIntDetection, helpers, config
    ↑
_integration_actions.html      ← uses _integrations context, api, _wizardConfig
    ↑
_nav.html                      ← uses _wizardConfig, renderWizard, state from all
```

### External Dependencies

```
globals/_api.html              ← api(), apiPost(), esc(), toast()
globals/_cards.html            ← cardCached(), cardRefresh()
globals/_tabs.html             ← switchTab()
globals/_auth_modal.html       ← modalOpen(), modalFormField(), mfVal()
globals/_install.html          ← installWithPlan() (tool install)
_boot.html                     ← _showPostWizardNextSteps()
assistant/                     ← window._assistant.refresh()
integrations/setup/            ← consumers of wizardModalOpen()
```

---

## Consumers

### Tab Loading

| File | How |
|------|-----|
| `dashboard.html` (line 65) | `{% include 'scripts/wizard/_wizard.html' %}` — tab JS |
| `dashboard.html` (line 71) | `{% include 'scripts/wizard/_setup.html' %}` — standalone wizard |
| `_tabs.html` (line 72) | `renderWizard()` — called on wizard tab switch |

### Wizard Modal Consumers

| File | Context |
|------|---------|
| `integrations/setup/_git.html` | Git setup wizard |
| `integrations/setup/_github.html` | GitHub setup wizard |
| `integrations/setup/_docker.html` | Docker setup wizard |
| `integrations/setup/_k8s.html` | K8s setup wizard |
| `integrations/setup/_terraform.html` | Terraform setup wizard |
| `integrations/setup/_dns.html` | DNS/CDN setup wizard |
| `integrations/setup/_cicd.html` | CI/CD setup wizard |
| `integrations/_git.html` | Quick Git wizard (direct call) |
| `wizard/_setup.html` | Full setup wizard |

### API Endpoints Used

| Endpoint | Used By | Purpose |
|----------|---------|---------|
| `GET /api/config` | `_init.html` | Load project config |
| `POST /api/config` | `_nav.html` | Save project config |
| `GET /api/wizard/detect` | `_init.html` | Environment detection |
| `POST /api/wizard/setup` | `_integration_actions.html` | Apply integration config |
| `POST /api/wizard/validate` | `_integration_actions.html` | Pre-apply validation |
| `POST /api/wizard/compose-ci` | `_integration_actions.html` | Generate CI pipeline |
| `DELETE /api/wizard/setup` | `_integration_actions.html` | Delete generated config |
| `GET /api/devops/prefs` | `_nav.html` | Fetch existing prefs for merge |
| `PUT /api/devops/prefs` | `_nav.html` | Save merged prefs |
| `POST /api/env/seed` | `_nav.html` | Seed `.env` files for multi-env |
| `POST /api/env/cleanup` | `_helpers.html` | Remove env files/GH env |
| `GET /api/vault/status` | `_steps.html` | Per-env vault status (Secrets step) |
| `GET /api/vault/active-env` | `_steps.html` | Active environment name |
| `GET /api/vault/keys` | `_steps.html` | Env keys for GH integration |
| `GET /api/vault/secrets` | `_steps.html` | Detected secret files listing |
| `GET /api/gh/auto` | `_steps.html` | Auto-detect GH token/repo |
| `GET /api/gh/environments` | `_steps.html` | GitHub deployment envs |
| `POST /api/gh/environment/create` | `_init.html` | Create GH deployment env |
| `GET /api/config/content-folders` | `_steps.html` | Content folder scan |
| `GET /api/content/enc-key-status` | `_steps.html` | Encryption key status |
| `POST /api/content/setup-enc-key` | `_helpers.html` | Generate/save encryption key |
| `POST /api/secret/set` | `_helpers.html` | Save key to `.env` |
| `POST /api/audit/install-tool` | `_integration_actions.html` | Tool installation |
| `GET /api/docker/containers` | `_integration_actions.html` | Docker container list |
| `GET /api/docker/images` | `_integration_actions.html` | Docker image list |
| `GET /api/docker/compose/status` | `_integration_actions.html` | Compose service list |
| `POST /api/docker/stream/*` | `_integration_actions.html` | Docker streaming actions |
| `GET /api/k8s/validate` | `_integration_actions.html` | K8s manifest validation |
| `GET /api/k8s/cluster` | `_integration_actions.html` | K8s cluster info |
| `GET /api/k8s/resources` | `_integration_actions.html` | K8s resource listing |
| `POST /api/terraform/validate` | `_integration_actions.html` | Terraform validation |
| `GET /api/terraform/state` | `_integration_actions.html` | Terraform state/resources |
| `GET /api/terraform/workspaces` | `_integration_actions.html` | Terraform workspaces |
| `GET /api/terraform/output` | `_integration_actions.html` | Terraform outputs |
| `GET /api/dns/lookup/*` | `_integration_actions.html` | DNS lookup |
| `GET /api/dns/ssl/*` | `_integration_actions.html` | SSL certificate check |
| `DELETE /api/wizard/config` | `_integration_actions.html` | Delete generated configs |
| `POST /api/wizard/validate` | `_integration_actions.html` | Validate setup payload |
| `POST /api/wizard/check-tools` | `_integration_actions.html` | Check tool availability |
| `POST /api/wizard/compose-ci` | `_integration_actions.html` | Compose CI pipeline |
| `POST /api/wizard/setup` | `_integration_actions.html` | Apply setup config |
| `GET /api/docker/logs` | `_integration_actions.html` | Docker container logs |

---

## Advanced Feature Showcase

### 1. SSE Docker Streaming with requestAnimationFrame Batching

Docker build/up/down can produce hundreds of log lines per second. Direct DOM
mutation per line causes visible lag. The wizard uses a `ReadableStream` +
`TextDecoder` SSE parser with a `requestAnimationFrame`-batched log renderer
that collects lines between frames and flushes in a single DOM write:

```javascript
// _integration_actions.html — lines 128-148
let _logBuffer = [];
let _logRafScheduled = false;

function _flushLog() {
    if (_logBuffer.length === 0) { _logRafScheduled = false; return; }
    if (output) {
        output.textContent += _logBuffer.join('\n') + '\n';
        output.scrollTop = output.scrollHeight;
    }
    _logBuffer = [];
    _logRafScheduled = false;
}

function _addLine(line) {
    _logBuffer.push(line);
    if (!_logRafScheduled) {
        _logRafScheduled = true;
        requestAnimationFrame(_flushLog);
    }
}
```

Combined with an `AbortController` (line 105) for cancellation and an elapsed
timer updated at 200ms intervals, the streaming handles multi-minute Docker builds
without freezing the UI or leaking resources.

### 2. Three-Tier Detection Caching (Memory → Session → API)

Detection data is expensive — it scans the filesystem, runs `docker info`,
`kubectl version`, `terraform version`, `gh auth status`, and more. The wizard
avoids redundant scans with a three-tier cache:

```javascript
// _init.html — lines 25-39
async function _wizFetchDetect(force = false) {
    // L1: in-memory (same page lifecycle)
    if (!force && _wizIntDetection) return _wizIntDetection;
    // L2: sessionStorage (survives tab switch, not reload)
    if (!force) {
        const cached = wizCached('detect');
        if (cached) {
            _wizIntDetection = cached;
            return cached;
        }
    }
    // L3: backend API (with optional cache bust)
    const url = '/wizard/detect' + (force ? '?bust=1' : '');
    const data = await api(url);
    _wizIntDetection = data;
    wizStore('detect', data);
    return data;
}
```

The `force` parameter bypasses all tiers — used by the "🔄 Rescan" button.
The `?bust=1` query string tells the backend to also bypass its own server-side
cache. This means a normal wizard page load hits zero APIs if detection was
already run in the same session.

### 3. Multi-Source Card Detail Enrichment

Each integration card shows a one-line status summary built from multiple
detection sources. The `_wizCardDetails()` function fuses data from up to
8 different probe results into a single descriptive string per card:

```javascript
// _integrations.html — lines 282-298
'k8s': (() => {
    const k8sSt = d.k8s_status || {};
    const kctl = k8sSt.kubectl || {};
    if (!kctl.available) return 'kubectl not found';
    const parts = [];
    if (kctl.version) parts.push('kubectl ' + (kctl.version + '').split(',')[0]);
    if (k8sSt.total_resources > 0) parts.push(k8sSt.total_resources + ' resource' + ...);
    else parts.push('no manifests');
    const hc = (k8sSt.helm_charts || []).length;
    if (hc > 0) parts.push(hc + ' Helm chart' + (hc !== 1 ? 's' : ''));
    if (k8sSt.kustomize && k8sSt.kustomize.exists) {
        const oc = k8sSt.kustomize.overlay_count || 0;
        parts.push('Kustomize' + (oc > 0 ? ' (' + oc + ' overlay...)' : ''));
    }
    if (k8sSt.deployment_readiness) parts.push(k8sSt.deployment_readiness...);
    return parts.join(' · ') || 'Kubernetes deployment — pods, services, ingress.';
})(),
```

The K8s detail alone fuses: kubectl version, resource count, Helm chart count,
Kustomize presence + overlay count, and deployment readiness — all from
`d.k8s_status`. Similar enrichment exists for all 8 integrations, each reading
different sub-objects of the detection payload.

### 4. Polymorphic Apply Setup with Pre-Validation

`_wizApplySetup(key)` is a single function that handles 8 different integration
types. It collects form values polymorphically (each key builds a different
payload shape), then optionally validates before applying:

```javascript
// _integration_actions.html — lines 696-892
async function _wizApplySetup(key, btnEl) {
    const $ = id => {
        const el = document.getElementById(id);
        if (!el) return undefined;
        if (el.type === 'checkbox') return el.checked;
        return el.value.trim();
    };

    let payload = { integration: key };

    if (key === 'int:docker') {
        payload.action = 'setup_docker';
        payload.base_image = $('wiz-docker-base');
        payload.port = $('wiz-docker-port');
        payload.cmd = $('wiz-docker-cmd');
        payload.compose = $('wiz-docker-compose');
        // ...
    } else if (key === 'k8s') {
        payload.action = 'setup_k8s';
        payload._services = [{
            name: $('wiz-k8s-name') || 'app',
            kind: 'Deployment',
            image: $('wiz-k8s-image') || appName + ':latest',
            port: parseInt($('wiz-k8s-port') || '8080', 10),
            // ...
        }];
    } else if (key === 'int:git') {
        payload.action = 'setup_git';
        // Conditional fields: branch, .gitignore regen, pre-commit hooks
        if ($('wiz-git-setup-hooks')) {
            payload.setup_hooks = true;
            const caps = sd.capabilities || {};
            const hookCmds = [];
            if (caps.lint) hookCmds.push(caps.lint);
            if (caps.format) hookCmds.push(caps.format);
            payload.hook_commands = hookCmds;
        }
    }
    // ... 5 more integration types

    // Pre-validate: only if payload has validatable fields
    const hasValidation = validationState.deploy_config || validationState.terraform_config;
    if (hasValidation) {
        const vRes = await api('/wizard/validate', {
            method: 'POST',
            body: JSON.stringify({ state: validationState }),
        });
        if (!vRes.ok && vRes.errors?.length > 0) return; // block
        if (vRes.warnings?.length > 0) /* show but don't block */;
    }

    // Apply
    const data = await api('/wizard/setup', {
        method: 'POST',
        body: JSON.stringify(payload),
    });
    // Auto-check the integration card + re-detect on success
    setTimeout(() => _wizRedetect(), 500);
}
```

The `$()` helper handles both inputs and checkboxes. Validation is selective —
only K8s (namespace check) and Terraform (provider check) trigger the
pre-validation call. Other integrations skip directly to apply.

### 5. CI Pipeline Composition with Live Preview

The CI wizard doesn't just write a static template — it composes a pipeline
from the detected project state. It inspects Docker, K8s, Terraform, and
environment configuration to build a state object, validates it, checks tool
availability, then requests a composed pipeline:

```javascript
// _integration_actions.html — lines 503-653
async function _wizComposeCi(btnEl) {
    const state = {
        stack_names: d.detected_stacks || ['generic'],
    };
    // Conditionally add Docker services
    if (d.integrations['int:docker']?.detected || d.files?.dockerfile) {
        state.docker_services = [{
            name: safeName,
            image: safeName + ':latest',
            registry: registry + '/' + safeName,
            registry_type: registryType,  // ghcr, dockerhub, or ecr
        }];
    }
    // Conditionally add K8s deploy config
    if (d.devops_cards?.k8s?.detected || d.files?.k8s_manifests) {
        state.deploy_config = { method: deployMethod, namespace: 'default' };
    }

    // 1. Pre-validate state
    const vRes = await api('/wizard/validate', { method: 'POST', body: JSON.stringify({ state }) });
    // 2. Check tool availability
    const tRes = await api('/wizard/check-tools', { method: 'POST', body: JSON.stringify({ state }) });
    // 3. Compose the pipeline
    const data = await api('/wizard/compose-ci', {
        method: 'POST',
        body: JSON.stringify({ state, strategy, project_name: projectName }),
    });

    // Render preview with per-file copy buttons and "Write Files" action
    for (const f of data.files) {
        previewHtml += `<pre data-yaml="${esc(f.content)}">${esc(f.content)}</pre>`;
    }
    output._pendingFiles = data.files;  // stored for _wizWriteCiFiles()
}
```

The composed files are previewed in the wizard before writing — the user
can copy individual files or write all files at once via `_wizWriteCiFiles()`.

### 6. Inline Environment Editing with Validation

Environment names and descriptions are editable in-place without a modal.
Clicking a span replaces it with an input that commits on Enter/blur and
cancels on Escape, with duplicate name detection:

```javascript
// _helpers.html — lines 221-270
function wizardEditEnvField(i, field, spanEl) {
    var env = _wizardConfig.environments[i];
    var currentValue = env[field] || '';

    var input = document.createElement('input');
    input.value = currentValue;
    input.style.cssText = spanEl.style.cssText +
        ';padding:0.15rem 0.4rem;border:1px solid var(--accent);...';

    function commit() {
        var val = input.value.trim();
        if (isName) {
            if (!val) { toast('Environment name cannot be empty.', 'warning'); return; }
            if (_wizardConfig.environments.some((e, idx) => idx !== i && e.name === val)) {
                toast('Environment name already exists.', 'warning');
                return;
            }
        }
        env[field] = val;
        wizardDirty = true;
        renderWizard();
    }

    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); commit(); }
        if (e.key === 'Escape') { renderWizard(); }  // cancel — re-render restores original
    });
    input.addEventListener('blur', commit);
    spanEl.replaceWith(input);
    input.focus();
    input.select();
}
```

The key insight: Escape triggers `renderWizard()` which rebuilds the step
from `_wizardConfig` (which was never mutated), effectively undoing the edit.
No explicit undo state is needed.

### 7. State Collection on Step Exit (Not Entry)

HTML form values live in DOM inputs and are lost when the step is re-rendered.
The wizard collects state at **exit** — every navigation function
(`wizardNext`, `wizardPrev`, `wizardGoTo`) collects the current step's form
state before moving:

```javascript
// _nav.html — lines 7-26
function wizardNext() {
    // Collect current state before advancing
    if (wizardSteps[currentWizardStep].id === 'welcome') {
        _wizardCollectWelcome();
        if (!_wizardConfig || !_wizardConfig.name) {
            toast('Project name is required.', 'warning');
            return;  // block navigation
        }
    }
    if (wizardSteps[currentWizardStep].id === 'integrations') {
        _wizCollectIntegrations();
    }
    if (currentWizardStep < wizardSteps.length - 1) {
        currentWizardStep++;
        renderWizard();
    }
}
```

This pattern also happens in `wizardPrev()` and `wizardGoTo()` — the same
collection logic runs regardless of navigation direction. The Welcome step
additionally validates (project name required) before allowing forward
navigation. The modal system uses the same pattern via `step.collect(data)`.

### 8. Merge-Not-Overwrite Preference Saving

The wizard only exposes a subset of all DevOps/integration preferences.
A naive overwrite would destroy preferences managed outside the wizard
(e.g., from the DevOps tab settings). The finish flow fetches existing
prefs, merges, then saves:

```javascript
// _nav.html — lines 78-103
// Merge with existing prefs (don't overwrite core DevOps prefs)
const existing = await api('/devops/prefs');
const merged = { ...existing, ..._wizardConfig._integrationPrefs };
const saved = await api('/devops/prefs', {
    method: 'PUT',
    body: JSON.stringify(merged),
});

// Update cached prefs in tabs so modals read correct values
if (typeof _devopsPrefs !== 'undefined') _devopsPrefs = saved;
if (typeof _intPrefs !== 'undefined') _intPrefs = saved;

// Apply card visibility immediately (no reload needed)
if (typeof _DEVOPS_CARDS !== 'undefined') {
    for (const [key, meta] of Object.entries(_DEVOPS_CARDS)) {
        const card = document.getElementById('devops-' + key + '-card');
        if (!card) continue;
        const wasHidden = card.style.display === 'none';
        const nowHidden = saved[key] === 'hidden';
        card.style.display = nowHidden ? 'none' : '';
        if (wasHidden && !nowHidden) meta.loadFn();  // lazy-load newly visible cards
    }
}
```

The merge pattern (`{ ...existing, ...wizard }`) ensures the wizard's
selections win for the keys it touches, but keys it doesn't know about
(added after the wizard was written, or managed by other tabs) survive.
The immediate card visibility update avoids a full page reload.

---

## Feature Coverage Summary

| Feature | Where | Instances | Example |
|---------|-------|-----------|---------|
| SSE streaming with RAF batching | `_integration_actions.html` | 3 actions (build, up, down) | Docker build log |
| Three-tier caching | `_init.html` | 1 (detection data) | `_wizFetchDetect` |
| Multi-source card enrichment | `_integrations.html` | 8 integrations | K8s detail from 6 probe fields |
| Polymorphic apply setup | `_integration_actions.html` | 8 integration types | `_wizApplySetup` |
| CI pipeline composition | `_integration_actions.html` | 1 (3-phase: validate → check tools → compose) | `_wizComposeCi` |
| Inline editing with validation | `_helpers.html` | 2 fields (name, description) | `wizardEditEnvField` |
| State collection on step exit | `_nav.html` | 3 functions (next, prev, goTo) | `wizardNext` |
| Merge-not-overwrite save | `_nav.html` | 1 (preference saving) | `wizardFinish` |
| AbortController cancellation | `_integration_actions.html` | 1 (Docker streams) | `_dockerStreamAbort` |
| Pre-validation before write | `_integration_actions.html` | 2 (apply setup + CI compose) | `_wizApplySetup` K8s namespace |
| Wizard Modal framework | `_modal.html` | 4 public + 7 internal functions | `wizardModalOpen` |
| Sub-wizard form system | `_integrations.html` | 8 sub-forms in `_wizSubForms{}` | Docker, K8s, Terraform panels |
| URL hash synchronization | `_init.html` | 1 (renderWizard) | `history.replaceState` |
| Environment file seeding | `_nav.html` | 1 (multi-env finish) | `POST /api/env/seed` |

---

## Design Decisions

### Why is `_integrations.html` 2,051 lines?

This file contains **all sub-wizard form definitions** via the
`_wizSubForms` object. Each integration (Docker, K8s, Terraform,
DNS, CI/CD, Git, GitHub) needs its own complete form panel with
fields, live data, and action buttons. These forms are tightly
coupled to each other (they share card rendering and apply logic)
and would gain nothing from splitting — the mental tax of finding
code across 7+ files would outweigh the benefit. The file is
organized as: card rendering → card details → card component →
sub-wizard forms (one per integration).

### Why two systems (Tab + Modal) in one domain?

Both systems share the "wizard" concept and vocabulary. The modal
system (`_modal.html`) was built as generic infrastructure that the
tab uses indirectly (via `_setup.html`). Keeping them co-located
makes the dependency chain visible. The modal system is deliberately
a separate `<script>` tag so it can be loaded independently of the
tab — integration setup wizards need `wizardModalOpen()` even when
the wizard tab isn't active.

### Why collect state when leaving a step, not when entering?

HTML form values are ephemeral — they live in DOM inputs and are
lost when the step is re-rendered. Collecting state at
**exit** (in `wizardNext()`, `wizardPrev()`, `wizardGoTo()`) ensures
no form data is lost regardless of navigation direction. This is
simpler than two-way binding and avoids stale state bugs.

### Why does finish merge prefs rather than overwrite?

The wizard only exposes a subset of DevOps/integration preferences.
If it overwrote the entire prefs object, any preferences managed
outside the wizard (e.g., from the DevOps tab settings panel) would
be lost. The `GET existing → merge → PUT` pattern preserves prefs
the wizard doesn't touch.

### Why does Docker streaming use `requestAnimationFrame` batching?

Docker build/up/down can produce hundreds of log lines per second.
Without batching, each line would trigger a DOM mutation + layout
recalculation, causing visible UI lag. The `_logBuffer` + RAF pattern
collects lines between frames and appends them in a single DOM
operation, maintaining smooth scrolling even under heavy output.

### Why is `_setup.html` a separate `<script>` from `_wizard.html`?

The full setup wizard (`openFullSetupWizard()`) needs to be callable
from anywhere — the boot sequence, the dashboard, the getting-started
flow — without requiring the full wizard tab to be loaded. Making it
a separate `<script>` element ensures it exists in the global scope
independently.

### Why does the apply flow validate before writing?

`_wizApplySetup()` first calls `POST /wizard/validate` with a
partial state before calling `POST /wizard/setup`. This catches
configuration errors (e.g., reserved K8s namespace, unsupported
Terraform provider) before any files are written to disk. The
validation is optional — it only runs when the form contains
validatable fields.
