# 🏗️ Comprehensive Card & UX Overhaul — Master Plan

> Generated: 2026-02-12  
> Status: DRAFT — awaiting user approval before implementation

---

## 1. TAB DEFINITIONS

### 🔌 Integrations Tab — "Core Management"
**Purpose**: Root-level management of external tools and services. *Is this tool installed? Is it configured? Set it up. Connect it. Manage the integration itself.*

This is where you **establish** and **configure** the relationship between your project and external systems. Think of it as the "control panel" for your toolchain.

**Perspective**: Setup · Configuration · Connection · Detection · Health

### 🛠️ DevOps Tab — "Operational Intelligence"  
**Purpose**: Day-to-day operational workflows. *How is it running? What needs attention? Take action. Monitor. Execute.*

This is where you **use** the tools operationally. Run tests, scan for vulnerabilities, deploy, check quality, manage environments.

**Perspective**: Execution · Monitoring · Analysis · Action · Results

### Key Principle
> A card **can** appear in both tabs with the same name if the perspectives are genuinely different. Example: "Kubernetes" in Integrations = cluster connection + manifest setup + Helm chart config. "Kubernetes" in DevOps = live pod status + scale + deploy + rollback.

---

## 2. CARD PLACEMENT MAP

### 🔌 Integrations Tab

| Card | Icon | Subtitle | Focus |
|---|---|---|---|
| **Git** | 🔀 | Repository & version control | Repo init, remote setup, hooks, .gitignore, branch/tag config |
| **GitHub** | 🐙 | Remote platform & API | Auth status, repo settings, org, webhooks, App config |
| **CI/CD** | ⚡ | Pipeline configuration | Workflow files, pipeline setup wizard, runner config |
| **Docker** | 🐳 | Container platform | Engine status, Dockerfile/Compose setup, registry auth |
| **Kubernetes** | ☸️ | Cluster & orchestration | Cluster connection, manifest detection, Helm chart setup, Skaffold, namespace config |
| **Terraform** | 🏗️ | Infrastructure as Code | Backend config, provider setup, module detection, workspace config |
| **Ansible** | 📚 | Configuration management | Playbook detection, role/inventory setup, vault config, linting config |
| **Monitoring** | 📊 | Observability setup | Prometheus/Grafana/Datadog config detection, health endpoint setup |
| **Registry** | 📦 | Container & artifact registry | GHCR/ECR/Docker Hub auth, push/pull config |
| **GitHub Pages** | 📄 | Static site publishing | Segment management, builder config, custom domain |

### 🛠️ DevOps Tab

| Card | Icon | Subtitle | Focus |
|---|---|---|---|
| **Security Posture** | 🔐 | Vulnerability & secret scanning | Secret scan, dependency audit, .gitignore, posture score |
| **Testing** | 🧪 | Test execution & coverage | Framework detection, run tests, coverage, results |
| **Code Quality** | ✨ | Lint, format, typecheck | Tool detection, run checks, fix issues, config generation |
| **Packages** | 📦 | Dependency management | Outdated check, vulnerability audit, install/update, license |
| **Environment** | ⚙️ | Env vars & secrets | .env management, validation, diff, promotion |
| **Documentation** | 📚 | Docs health & generation | Coverage, links, README/CHANGELOG generation |
| **Kubernetes** | ☸️ | Live cluster operations | Pod/deploy status, scale, rollback, logs, events, exec |
| **Terraform** | 🏗️ | IaC operations | Plan, apply, destroy, state, workspaces, drift |
| **DNS & CDN** | 🌐 | Domain & delivery | DNS lookup, SSL check, CDN config, propagation |
| **Metrics** | 📈 | Project health metrics | LOC, dependencies, complexity, build times, trends |
| **CI/CD Runs** | 🚀 | Pipeline execution | Recent runs, status, artifacts, dispatch, rerun |

### Cards to REMOVE from current placement
| Card | Currently In | Action | Why |
|---|---|---|---|
| Docker | Integrations only | Keep in Integrations only | DevOps actions (build/up/down) move into Integration card actions section |
| K8s (current) | Both tabs | Rewrite both | Currently polluted beyond repair |
| Terraform (current) | Both tabs | Rewrite both | Integrations = setup, DevOps = operations |

---

## 3. CARD UX STANDARDS

### 3.1 Card Anatomy (Standard Template)

Every card MUST follow this exact structure:

```
┌─ Card Header ──────────────────────────────────┐
│ [Icon] [Title]          [Age] [🔄] [Badge]     │
│ [Subtitle description]                         │
├─ Status Summary ───────────────────────────────┤
│ Key metrics in a clean grid (2-3 stats)        │
│ e.g. "✅ Connected  │  12 resources  │  v1.28" │
├─ Detection / Info Panel ───────────────────────┤
│ What was found (files, tools, configs)         │
│ Clean list with icons, not raw dumps           │
├─ Actions Toolbar ──────────────────────────────┤
│ [Action 1] [Action 2] [Action 3]               │
│ Contextual buttons — only relevant actions     │
├─ Expandable Live Panel (collapsed by default) ─┤
│ Tab buttons: [Tab A] [Tab B] [Tab C]           │
│ ┌─ Panel content ───────────────────────┐      │
│ │ Loaded on demand when tab clicked     │      │
│ └───────────────────────────────────────┘      │
└────────────────────────────────────────────────┘
```

### 3.2 Rules

1. **No clutter** — Every element must earn its space. If it doesn't add value at a glance, it belongs in a modal or expandable panel.
2. **Status summary first** — The card should communicate health in 2 seconds.
3. **Progressive disclosure** — Simple by default, detail on demand.
4. **Actions over information** — Cards should let you DO things, not just show data.
5. **Contextual actions** — Don't show "Scale deployment" if there are no deployments.
6. **Loading states** — Spinners with messages, not bare spinners.
7. **Error states** — Clear error messages with actionable next steps (install link, config hint).
8. **Empty states** — Not "No data found" but "No Dockerfiles detected. [Generate one →]".

### 3.3 Modal UX Standards

Every wizard modal MUST follow this pattern:

```
┌─ Modal Header ────────────────────────────────┐
│ [Icon] [Title]                          [✕]   │
├─ Modal Body ──────────────────────────────────┤
│                                               │
│  Step indicator (if multi-step):              │
│  ● Step 1 → ○ Step 2 → ○ Step 3              │
│                                               │
│  Form fields:                                 │
│  ┌─ [label] ──────────────────────────┐       │
│  │  [input value]                     │       │
│  └────────────────────────────────────┘       │
│                                               │
│  Preview panel (if generative):               │
│  ┌─ Generated output ────────────────┐        │
│  │  syntax-highlighted preview       │        │
│  └───────────────────────────────────┘        │
│                                               │
├─ Modal Footer ────────────────────────────────┤
│ [Cancel]                 [Secondary] [Primary]│
└───────────────────────────────────────────────┘
```

**Modal rules:**
1. Max width 600-780px depending on content complexity
2. Form fields use 2-column grid where possible
3. Labels are always visible (no placeholder-only inputs)
4. Required fields marked with `*`
5. Preview panel shows live-generated output before writing
6. Primary button disabled until form is valid
7. Success feedback: toast + auto-close after 1s
8. Error feedback: inline error in the modal, not just toast

---

## 4. FULL CARD SPECIFICATION

### 4.1 INTEGRATIONS TAB — Card Details

#### 🔀 Git Card (REWRITE)
**Status summary**: Branch, clean/dirty, commits ahead/behind, remote
**Detection**: .git directory, hooks, .gitignore
**Actions**:
- Quick commit (modal: message + file selection)
- Pull / Push
- Branch management (modal: create/switch/delete/merge)
- Tag management (modal: create, list, push)
- Stash (stash / pop / list)
**Generate**:
- .gitignore wizard (stack-aware)
- Git hooks setup (pre-commit, pre-push)
**Live panels**: Recent commits, diff summary

#### 🐙 GitHub Card (REWRITE)
**Status summary**: Auth status, repo name, org, visibility
**Detection**: gh CLI, .github directory, CODEOWNERS
**Actions**:
- Open repo in browser
- Create/view PRs (modal: title, base, head, body)
- Create/view issues (modal: title, body, labels)
- Create release (modal: tag, title, notes, draft)
- Dispatch workflow
**Live panels**: Open PRs, Recent runs, Issues

#### ⚡ CI/CD Card (REWRITE)
**Status summary**: Provider (GitHub Actions / GitLab CI), workflow count, last run status
**Detection**: .github/workflows/*.yml, .gitlab-ci.yml
**Actions**:
- Open CI dashboard
- View/edit workflow files
**Generate**:
- CI workflow wizard (modal: stack-aware, test/lint/build/deploy steps)
- Lint workflow wizard
- Deploy workflow wizard
**Live panels**: Workflow list with triggers and status

#### 🐳 Docker Card (REWRITE)
**Status summary**: Engine status, Dockerfile found, Compose found, container count
**Detection**: Dockerfile, docker-compose.yml, .dockerignore
**Actions**:
- Build / Up / Down / Restart (contextual)
- Prune (volumes, images, containers)
- View logs (modal: container selector + live tail)
**Generate**:
- Dockerfile wizard (modal: stack-aware, multi-stage option)
- Compose wizard (modal: service builder with ports/volumes/env/networks)
- .dockerignore wizard (modal: stack-aware)
**Live panels**: Containers, Images, Networks, Volumes, Stats

#### ☸️ Kubernetes Card — Integrations perspective (REWRITE)
**Status summary**: kubectl available, cluster connected, manifest count, Helm charts found
**Detection**: k8s/ directory, *.yaml manifests, Chart.yaml, skaffold.yaml, kustomization.yaml
**Actions**:
- Connect to cluster (context switcher)
- Validate manifests
- Apply manifests
**Generate**:
- K8s manifest wizard (modal: multi-resource, Deployment/Service/Ingress/ConfigMap/Job/CronJob)
- Helm chart scaffold wizard
- Kustomize setup wizard
- Namespace manifest wizard
**Sub-sections** (collapsible):
- Helm charts detected (with values viewer)
- Kustomize overlays detected  
- Skaffold configs detected
- Multi-env namespace mapping

#### 🏗️ Terraform Card — Integrations perspective (REWRITE)
**Status summary**: TF installed, initialized, provider count, resource count
**Detection**: *.tf files, .terraform directory, terraform.tfstate
**Actions**:
- Init / Validate / Format
**Generate**:
- Terraform config wizard (modal: provider + resource type + variables)
- Backend configuration wizard
- Variable definition wizard
**Live panels**: Providers, Modules, Resources by type, Variables

#### 📚 Ansible Card (NEW)
**Status summary**: ansible-playbook available, playbook count, role count, inventory found
**Detection**: playbook*.yml, roles/, inventory/, ansible.cfg, requirements.yml
**Actions**:
- Lint playbooks (ansible-lint)
- Validate syntax (--syntax-check)
- Run playbook (modal: playbook selector, inventory, tags, limit, check mode)
**Generate**:
- Playbook wizard (modal: tasks, handlers, variables)
- Role scaffold wizard
- Inventory file wizard
- ansible.cfg wizard
**Live panels**: Playbooks, Roles, Inventory groups

#### 📊 Monitoring Card (NEW)
**Status summary**: Monitoring tool detected, config files found, health endpoints
**Detection**: prometheus.yml, grafana/, datadog.yaml, .env DATADOG_*, health endpoints in source
**Actions**:
- Open monitoring dashboard (if URL configured)
- Test health endpoint
**Generate**:
- Prometheus config wizard
- Health endpoint scaffold
- Alert rules wizard
**Live panels**: Detected configs, Health endpoint test results

#### 📦 Registry Card (NEW)
**Status summary**: Registry configured, auth status, recent pushes
**Detection**: .docker/config.json auth, GITHUB_TOKEN, ECR login, project.yml registry
**Actions**:
- Login to registry (modal: provider selector + credentials)
- Push image (modal: image tag + registry)
- Pull image
- List remote tags
**Generate**:
- Registry auth configuration
- CI push workflow

#### 📄 GitHub Pages Card (IMPROVE)
**Status summary**: Segments configured, last build status, deployed URL
**Detection**: pages config in project.yml, docs/ or site/ directories
*(Keep current rich functionality, improve UX polish only)*

---

### 4.2 DEVOPS TAB — Card Details

#### 🔐 Security Posture (IMPROVE)
**Current**: Working but could be cleaner
**Add**:
- Dependency vulnerability scan integration
- Generate SECURITY.md wizard
- Pre-commit secret scanning setup
- Dismiss/undismiss with inline comment

#### 🧪 Testing (IMPROVE)
**Current**: Working
**Add**:
- Test execution with live output
- Coverage report viewer
- Test scaffolding wizard (generate test file from source module)
- Fixture generator

#### ✨ Code Quality (IMPROVE)
**Current**: Working
**Add**:
- Run all checks with live output
- Auto-fix option
- Pre-commit hooks setup wizard
- EditorConfig generator
- Quality gate definitions (pass/fail thresholds)

#### 📦 Packages (IMPROVE)
**Current**: Working, has per-module detection
**Add**:
- Outdated packages table with update buttons
- Vulnerability audit with severity
- License compliance check
- Package search/install wizard (modal: search registry, install)

#### ⚙️ Environment (IMPROVE)
**Current**: Working
**Add**:
- Side-by-side env comparison across environments
- Variable promotion wizard (dev → staging → prod)
- Missing required var detection
- Secret rotation reminder

#### 📚 Documentation (IMPROVE)
**Current**: Working but basic
**Add**:
- README generator wizard (modal: sections selector)
- CHANGELOG generator (from git log)
- CONTRIBUTING.md generator
- Code of Conduct generator
- API docs link (if OpenAPI spec detected)

#### ☸️ Kubernetes — DevOps perspective (REWRITE)
**Status summary**: Cluster status, node count, pod health, deployment status
**Live panels** (tabbed):
- Pods (status, restart count, age, logs button, exec button)
- Deployments (replicas, status, scale button, rollback button)
- Services (type, ports, port-forward button)
- Events (recent warnings, errors)
- Namespaces (list with resource counts)
- Helm releases (status, chart, revision, values, upgrade/rollback)
**Actions**:
- Scale deployment (modal)
- Apply manifest
- Delete resource
- Port-forward

#### 🏗️ Terraform — DevOps perspective (REWRITE)
**Status summary**: Initialized, workspace, state resource count, last plan
**Actions**:
- Plan (with diff viewer modal)
- Apply (with confirmation modal)
- Destroy (with double confirmation)
- Workspace switch (modal)
- Format
**Live panels**: State resources, Outputs, Workspaces

#### 🌐 DNS & CDN (IMPROVE)
**Current**: Working but basic
**Add**:
- DNS lookup with record type selector
- SSL certificate details (expiry, issuer, chain)
- CDN provider-specific actions
- DNS record generation wizard

#### 📈 Metrics Card (NEW)
**Status summary**: Project health score, key metrics
**Detection**: Calculated from other card data
**Data**:
- Lines of code (by language)
- Dependency count
- Test-to-source ratio
- Documentation coverage %
- Security posture score
- Build time trends
- Activity timeline

#### 🚀 CI/CD Runs — DevOps perspective (NEW or merge into CI/CD)
**Status summary**: Last run status, success rate, average duration
**Live panels**:
- Recent workflow runs (status, duration, trigger)
- Artifacts list
**Actions**:
- Dispatch workflow (modal: workflow selector + inputs)
- Rerun failed
- Cancel running
- Download artifact

---

## 5. PHASED IMPLEMENTATION PLAN

### Phase 1: Foundation & Standards (MUST DO FIRST)
1. Create reusable card builder helper (JS function to standardize card sections)
2. Create reusable modal builder helper (JS function for standard wizard modals)
3. Define CSS classes for standard card sections (status-grid, action-toolbar, live-panel, etc.)
4. Fix the K8s card (remove pollution, make it sensible)

### Phase 2: Integrations Tab Full Rewrite
Order:
1. **Git Card** — rewrite with branch/tag/stash management + .gitignore wizard
2. **GitHub Card** — rewrite with PR/issue/release management
3. **CI/CD Card** — rewrite with workflow wizard
4. **Docker Card** — rewrite with proper compose wizard + container management
5. **Kubernetes Card** — full rewrite (integration perspective: setup, detection, generate)
6. **Terraform Card** — rewrite (integration perspective: setup, config)
7. **GitHub Pages Card** — UX polish (keep functionality)

### Phase 3: New Integration Cards
1. **Ansible Card** — new backend (`ansible_ops.py`) + routes + UI
2. **Monitoring Card** — new backend (`monitoring_ops.py`) + routes + UI
3. **Registry Card** — new backend (`registry_ops.py`) + routes + UI

### Phase 4: DevOps Tab Full Rewrite
1. **Security Card** — improve with dependency scan, SECURITY.md wizard
2. **Testing Card** — improve with live execution, scaffolding
3. **Quality Card** — improve with pre-commit, quality gates
4. **Packages Card** — improve with update buttons, license check
5. **Environment Card** — improve with comparison, promotion
6. **Documentation Card** — improve with generators
7. **Kubernetes Card** — full rewrite (ops perspective: live cluster, scale, logs)
8. **Terraform Card** — rewrite (ops perspective: plan, apply, state)
9. **DNS & CDN Card** — improve with SSL, lookup expansion

### Phase 5: New DevOps Cards
1. **Metrics Card** — new card with project health dashboard
2. **CI/CD Runs Card** — operational perspective (or merge into existing)

### Phase 6: Cross-cutting Wizard Modals
All the multi-step wizards that span multiple integrations:
1. Project setup wizard
2. Deployment pipeline wizard
3. Environment promotion wizard

---

## 6. MODAL INVENTORY (26 total)

### Integrations Tab Modals
| # | Modal | Card | Type |
|---|---|---|---|
| 1 | Quick Commit | Git | Form: message + files |
| 2 | Branch Manager | Git | Multi-action: create/switch/delete/merge |
| 3 | Tag Manager | Git | Multi-action: create/list/push |
| 4 | .gitignore Wizard | Git | Generator: stack-aware template |
| 5 | Create PR | GitHub | Form: title, base, head, body |
| 6 | Create Issue | GitHub | Form: title, body, labels |
| 7 | Create Release | GitHub | Form: tag, title, notes |
| 8 | CI Workflow Wizard | CI/CD | Multi-step: stack → steps → triggers → generate |
| 9 | Dockerfile Wizard | Docker | Form: stack, base image, stages |
| 10 | Compose Wizard | Docker | Multi-service builder |
| 11 | .dockerignore Wizard | Docker | Generator: stack-aware |
| 12 | K8s Manifest Wizard | Kubernetes | Multi-resource: kind → spec → preview |
| 13 | Helm Install/Upgrade | Kubernetes | Form: release, chart, values, namespace |
| 14 | Terraform Config Wizard | Terraform | Form: provider, resource, variables |
| 15 | Ansible Playbook Wizard | Ansible | Form: tasks, handlers, vars |
| 16 | Ansible Run | Ansible | Form: playbook, inventory, tags, check mode |
| 17 | Registry Login | Registry | Form: provider, credentials |
| 18 | Registry Push | Registry | Form: image, tag, registry |

### DevOps Tab Modals
| # | Modal | Card | Type |
|---|---|---|---|
| 19 | Scale Deployment | K8s | Form: deployment, replicas |
| 20 | Pod Logs Viewer | K8s | Live: container selector + log stream |
| 21 | Terraform Plan Viewer | Terraform | Diff viewer: resource changes |
| 22 | Terraform Apply Confirm | Terraform | Confirmation: resource list + approve |
| 23 | Package Install | Packages | Form: search + install |
| 24 | Env Promotion | Environment | Multi-step: source → target → vars → apply |
| 25 | README Generator | Documentation | Form: section selector → preview |
| 26 | Test Scaffolding | Testing | Form: module → framework → template → generate |

---

## 7. IMPLEMENTATION NOTES

### File Organization
- Each card's HTML shell: `templates/partials/_tab_integrations.html` / `_tab_devops.html`
- Each card's JS logic: `templates/scripts/_integrations.html` / `_devops.html`
- Backend route: `routes_xxx.py`
- Backend service: `src/core/services/xxx_ops.py`

### New Files Needed
| File | Purpose |
|---|---|
| `src/core/services/ansible_ops.py` | Ansible detection, lint, run, generate |
| `src/core/services/monitoring_ops.py` | Monitoring tool detection, health check |
| `src/core/services/registry_ops.py` | Container registry auth, push, pull |
| `src/ui/web/routes_ansible.py` | Ansible API endpoints |
| `src/ui/web/routes_monitoring.py` | Monitoring API endpoints |
| `src/ui/web/routes_registry.py` | Registry API endpoints |

### Skaffold
Skaffold detection and operations stay embedded in `k8s_ops.py` as a sub-section of the Kubernetes integration. It is NOT a separate card — it's shown as a collapsible section within the K8s card when `skaffold.yaml` is detected.

---

## 8. SUCCESS CRITERIA

- [ ] Every card follows the standard anatomy (status → detection → actions → live panels)
- [ ] Every card has contextual empty states with actionable CTAs
- [ ] Every wizard modal follows the standard pattern
- [ ] No card is "polluted" with unrelated features
- [ ] Progressive disclosure: simple by default, detail on demand
- [ ] All cards in correct tab with correct perspective
- [ ] Loading/error/empty states are clean and helpful
- [ ] Every action that can fail shows a clear error with next steps
- [ ] Modals close cleanly on success with toast feedback
