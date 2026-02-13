# 🔧 Integrations Refactor — Complete Analysis & Plan

> **Date**: 2026-02-13
> **Status**: ANALYSIS COMPLETE — Awaiting review before implementation
> **Scope**: ALL integrations — Setup Wizards, Integration Cards, Wizard Step 5, User Journey
> **Estimated effort**: 1000+ hours, 200+ features

---

## 1. THE CORE PROBLEM

**Nothing works as a user journey.** The UI has code everywhere but:

- The **Setup Wizard modals** (`_integrations_setup_modals.html`) are a 3-step detect/configure/apply flow but they don't actually handle real scenarios (missing tools, failed operations, partial states)
- The **Wizard Step 5** inline sub-wizards (`_wizard_integrations.html`) duplicate most of the same logic in a cramped inline panel, with *different* backends
- The **Integration Cards** (`_integrations_*.html`) show status but their CTAs are broken (setup buttons either go to wrong modal or do nothing useful)
- The **visual quality** is garbage — cramped inline forms, mismatched styles, no proper spacing, no polish
- There are **3 different systems** for the same action (e.g., "generate a Dockerfile"):
  1. Wizard Step 5 inline sub-form → calls `POST /api/wizard/setup` with `action=setup_docker`
  2. Setup modal (Docker) → calls some combo of `/docker/generate/*` endpoints
  3. Integration card generate toolbar → calls `/docker/generate/dockerfile`

**Nothing is properly connected. Nothing guides the user. Nothing looks good.**

---

## 2. INVENTORY — WHAT EXISTS

### 2.1 Backend Routes (these are solid, keep them)

| Integration | Routes File | Key Endpoints | Status |
|---|---|---|---|
| **Git** | `routes_integrations.py` | `GET /git/status`, `GET /git/log`, `POST /git/commit`, `POST /git/pull`, `POST /git/push` | ✅ Working |
| **GitHub** | `routes_integrations.py` | `GET /integrations/gh/status`, `GET /gh/pulls`, `GET /gh/actions/runs`, `POST /gh/actions/dispatch`, `GET /gh/actions/workflows` | ✅ Working |
| **Docker** | `routes_docker.py` (346 lines) | `GET /docker/status`, `/containers`, `/images`, `/compose`, `/logs`, `/stats`, `POST /build`, `/up`, `/down`, `/restart`, `/prune`, `/generate/*`, `/networks`, `/volumes`, `/inspect`, `/pull`, `/exec`, `/rm`, `/rmi` | ✅ Working |
| **CI/CD** | `routes_ci.py` (111 lines) | `GET /ci/status`, `/ci/workflows`, `/ci/coverage`, `POST /ci/generate/ci`, `/ci/generate/lint` | ✅ Working |
| **Kubernetes** | `routes_k8s.py` (303 lines) | `GET /k8s/status`, `/validate`, `/cluster`, `/resources`, `/events`, `/namespaces`, `POST /k8s/generate`, `/apply`, `/delete`, `/scale`, `/describe`, `/pod-logs`, Helm: `/helm/*`, Skaffold: `/skaffold/status`, Wizard: `/k8s/generate/wizard` | ✅ Working |
| **Terraform** | `routes_terraform.py` (151 lines) | `GET /terraform/status`, `/state`, `/workspaces`, `/output`, `POST /terraform/validate`, `/plan`, `/apply`, `/destroy`, `/init`, `/generate`, `/fmt`, `/workspace/select` | ✅ Working |
| **DNS** | `routes_dns.py` (80 lines) | `GET /dns/status`, `/dns/lookup/:domain`, `/dns/ssl/:domain`, `POST /dns/generate` | ✅ Working |
| **Pages** | `routes_pages_api.py` (700+ lines) | Segments CRUD, builders, build, deploy, merge, preview, init | ✅ Working |
| **Project Status** | `routes_project.py` (437 lines) | `GET /project/status`, `/project/next` — probes all integrations, dependency graph, progress | ✅ Working |
| **Wizard Setup** | `routes_devops.py` (737 lines) | `GET /wizard/detect`, `POST /wizard/setup` (setup_git, setup_docker, setup_k8s, setup_ci, setup_terraform), `DELETE /wizard/config` | ✅ Working |

### 2.2 Frontend — Integration Cards

| Card | File | Lines | Load Function | Status |
|---|---|---|---|---|
| **Git** | `_integrations_git.html` | 223 | `loadGitCard()` | Has status, commit/pull/push actions, .gitignore placeholder |
| **GitHub** | `_integrations_github.html` | 289 | `loadGitHubCard()` | Has auth check, PRs, runs, environments, secrets |
| **CI/CD** | `_integrations_cicd.html` | 287 | `loadCICard()` | Has workflows, runs, coverage, trigger, generate modals |
| **Docker** | `_integrations_docker.html` | 498 | `loadDockerCard()` | Has status, containers, images, compose, actions, generate |
| **K8s** | `_integrations_k8s.html` | 735 | `_intLoadK8sCard()` | BLOATED — has everything crammed in, 735 lines of mess |
| **Terraform** | `_integrations_terraform.html` | 304 | `_intLoadTerraformCard()` | Has status, state, actions, generate |
| **Pages** | (in integrations tab) | — | `loadPagesCard()` | Segments, builders |

### 2.3 Frontend — Setup Wizard Modals (`_integrations_setup_modals.html`, 726 lines)

| Wizard | Function | Steps | Backend Used | Issues |
|---|---|---|---|---|
| **Git** | `openGitSetupWizard()` | 3 steps: Detect → Configure → Apply | Calls `/git/status` then `/wizard/setup` | Bare minimum — no .gitignore, no branch setup |
| **Docker** | `openDockerSetupWizard()` | 3 steps: Detect → Configure → Apply | Calls `/docker/status` then `/wizard/setup` | OK-ish but doesn't use the better `/docker/generate/*` endpoints |
| **CI/CD** | `openCICDSetupWizard()` | 3 steps: Detect → Configure → Apply | Calls `/ci/status` then `/wizard/setup` | Doesn't know about existing workflows, no lint option |
| **K8s** | `openK8sSetupWizard()` | 3 steps: Detect → Configure → Apply | Calls `/k8s/status` then `/wizard/setup` | Very basic — no Helm, no Skaffold, no kustomize |
| **Terraform** | `openTerraformSetupWizard()` | 3 steps: Detect → Configure → Apply | Calls `/terraform/status` then `/wizard/setup` | Basic provider/backend setup, misses modules/variables |
| **GitHub** | `openSetupWizard('github')` | None — opens cli.github.com | N/A | Just a link, not an actual wizard |
| **Pages** | `openSetupWizard('pages')` | None — toast + tab switch | N/A | Not a wizard at all |
| **DNS** | `openSetupWizard('dns')` | None — toast "coming soon" | N/A | Not implemented |

### 2.4 Frontend — Wizard Step 5 Inline Sub-Wizards (`_wizard_integrations.html`, 512 lines)

| Sub-Form | Function | Issues |
|---|---|---|
| **Docker** | `_wizSubForms['int:docker']` | Duplicates the setup modal but *also* has live containers/images panel and operational buttons (Start/Stop/Build) crammed into a tiny inline panel |
| **K8s** | `_wizSubForms['k8s']` | Same — duplicates setup modal plus live cluster panel |
| **CI/CD** | `_wizSubForms['int:ci']` | Duplicates setup modal |
| **Terraform** | `_wizSubForms['terraform']` | Duplicates setup modal |
| **Git** | `_wizSubForms['int:git']` | Just a remote URL field |
| **GitHub** | `_wizSubForms['int:github']` | Just "install gh" instructions |
| **Pages** | `_wizSubForms['int:pages']` | Just a text label |

These inline forms call `POST /api/wizard/setup` which is a DIFFERENT backend path than what the setup modals AND the integration cards use.

### 2.5 Frontend — Initialization & Plumbing

| File | Purpose | Issues |
|---|---|---|
| `_integrations_init.html` (239 lines) | Card registry, prefs, tab loading, `cardSetupBanner()`, `cardDepHint()`, `cardCrossLink()` | The helper functions exist but cards don't use them consistently |
| `_globals.html` (280+ lines) | `cardStatusGrid()`, `cardActionToolbar()`, `cardLivePanel()`, `cardGenerateToolbar()`, `cardDetectionList()`, `cardDataTable()` | These generic helpers exist but each card uses them differently, or not at all |
| `_globals_wizard_modal.html` | `wizardModalOpen()`, `wizardNext()`, `wizardPrev()`, `wizardFinish()` | The wizard modal framework — this is the foundation the setup modals use |
| `_boot.html` (96 lines) | First-launch detection, post-wizard next steps | Calls `_showPostWizardNextSteps()` which shows a modal of incomplete integrations |
| `_dashboard.html` | Setup progress widget — `loadSetupProgress()` | Shows progress bar + integration checklist with setup buttons |

---

## 3. THE PROBLEMS — EXHAUSTIVE LIST

### 3.1 Architecture Problems

| # | Problem | Where | Impact |
|---|---|---|---|
| A1 | **3 backends for the same thing** | `/wizard/setup` (generic action dispatcher), `/docker/generate/*` (per-integration endpoints), integration card inline calls | No single source of truth for generating configs |
| A2 | **3 frontends for the same thing** | Wizard Step 5 inline, Setup Modals, Card generate toolbars all do "generate Dockerfile" differently | User confusion, maintenance nightmare |
| A3 | **No shared state** | Setup modal completes but card doesn't know it. Wizard step 5 configures but setup modal doesn't see it | Everything feels disconnected |
| A4 | **No error recovery** | If `docker info` fails in the setup modal, you get a generic "Detection failed" with no way to retry | User dead-ends |
| A5 | **No partial state handling** | Docker has Dockerfile but no Compose — setup modal doesn't handle this | User can't incrementally build |

### 3.2 UX Problems

| # | Problem | Where | Impact |
|---|---|---|---|
| U1 | **Two buttons for same action** | Wizard Step 5 has both "⚙️ Setup" (inline) and "🚀 Full Setup →" (modal) on every integration | Confusing — which one do I click? |
| U2 | **Inline forms are unusable** | Wizard Step 5 — forms crammed into 200px panel with mini buttons | Can't read or use them |
| U3 | **Cards don't guide setup** | `cardSetupBanner()` exists but most cards don't use it effectively | User doesn't know what to do |
| U4 | **No flow between integrations** | After setting up Git, you're not guided to Docker/GitHub | User has to figure out the order themselves |
| U5 | **Cross-tab links are noise** | `cardCrossLink()` adds tiny "View X in DevOps →" text that nobody notices | Wasted space, no value |
| U6 | **GitHub "wizard" is just a link** | Opens cli.github.com in a new tab, shows a toast | Not a setup wizard |
| U7 | **DNS is "coming soon"** | Toast message only | Dead end |
| U8 | **Pages "wizard" is a tab switch** | Just navigates to the Integrations tab | Not a setup wizard |

### 3.3 Visual Problems

| # | Problem | Where | Impact |
|---|---|---|---|
| V1 | **Cramped layout** | Every integration card and sub-wizard uses 0.65rem-0.72rem fonts with 0.1rem padding | Unreadable, looks cheap |
| V2 | **Inconsistent styling** | Some status badges use `color-mix`, others use plain vars, some use inline styles, some use CSS classes | No visual coherence |
| V3 | **No hierarchy** | Status, detection, actions, operational panels are just stacked with no visual separation | Can't scan the card |
| V4 | **Modals look bare** | Setup modals are functional but visually plain — no progress indicators, no section headers, no polish | Feels like a prototype |

---

## 4. THE PLAN — PIECE BY PIECE

### Guiding Principles

1. **ONE way to do each thing** — Kill duplicates ruthlessly
2. **User journey first** — Every screen answers "what do I do next?"
3. **Visual quality** — Premium look, not MVP
4. **Proper setup wizards** — Each integration gets a real, complete, beautiful multi-step wizard
5. **Cards reflect reality** — Show actual state, offer actual actions
6. **Backend stays** — The Python routes/services are solid, don't touch them unnecessarily

### Phase 0: Cleanup & Foundation

**Goal**: Remove all the trash, establish clean base

| Task | Detail | Files |
|---|---|---|
| 0.1 | **Kill Wizard Step 5 inline sub-forms** — Replace with a clean integration checklist that launches setup modals via `openSetupWizard(key)`. No more duplicate forms | `_wizard_integrations.html` |
| 0.2 | **Kill `cardCrossLink()`** — Remove all cross-tab links. They add nothing | `_integrations_init.html`, all card files |
| 0.3 | **Audit `_globals.html` helpers** — Verify `cardStatusGrid`, `cardActionToolbar`, `cardLivePanel`, `cardGenerateToolbar`, `cardDetectionList`, `cardDataTable` are clean and usable | `_globals.html` |
| 0.4 | **Establish visual standards** — Define the CSS system for integration cards and setup wizards (consistent spacing, fonts, colors, section separators) | `admin.css` |

### Phase 1: Setup Wizard Modals — Full Rewrite

**Goal**: Each integration gets a PROPER multi-step setup wizard that handles every scenario

Each wizard follows this pattern:
```
Step 1: DETECT
  - Check if tool is installed (with install instructions/button if not)
  - Check if config files exist (show what was found)
  - Check service connectivity (daemon running? cluster connected?)
  - Show clear status: ✅ Ready / ⚠️ Partial / ❌ Missing

Step 2: CONFIGURE (may have sub-steps for complex integrations)
  - Form with all options, pre-filled from detection
  - Live preview of what will be generated
  - Smart defaults based on project context
  - Handles partial states (already have Dockerfile? just add Compose)

Step 3: APPLY & VERIFY
  - Execute the configuration
  - Verify it worked (re-detect)
  - Show results (files created, tests passed)
  - CTA to next integration in the chain
```

#### 1.1 Git Setup Wizard (REWRITE)

**Current state**: Bare minimum — just git init + remote. No .gitignore, no branch setup, no hooks.

**New flow**:
```
Step 1: DETECT
  - Git installed? → Version info
  - .git exists? → Branch, remote, status
  - .gitignore exists? → Show contents
  - Remote configured? → Show URL

Step 2: CONFIGURE
  - Init repo (if not exists)
  - Set remote URL (detect from gh CLI if possible)
  - .gitignore wizard: stack-aware template selection (Python, Node, Go, etc.)
  - Default branch name (main/master)
  - Initial commit options

Step 3: APPLY & VERIFY
  - Execute: git init, remote add, write .gitignore, initial commit
  - Verify: git status shows clean
  - CTA: "Next: Set up GitHub →" or "Next: Set up Docker →"
```

**Backend used**: `/git/status`, `/wizard/setup` (action=setup_git) + new gitignore generation

#### 1.2 GitHub Setup Wizard (REWRITE — currently just a link!)

**Current state**: Opens cli.github.com, shows a toast. Not a wizard at all.

**New flow**:
```
Step 1: DETECT
  - gh CLI installed? → Version, show install command if not
  - gh auth status? → Show user/org
  - Remote repo detected? → Show repo name
  - GITHUB_REPOSITORY in .env? → Show value

Step 2: CONFIGURE (if CLI installed and authed)
  - Detect/confirm repository
  - Create GitHub environments (dev, staging, production)
  - Push secrets to GitHub (from vault)
  - Set up CODEOWNERS

Step 3: VERIFY
  - Show auth status, repo, environments
  - CTA: "Next: Set up CI/CD →"
```

**Backend used**: `/integrations/gh/status`, `/gh/auto`, `/gh/environments`, vault APIs

#### 1.3 Docker Setup Wizard (REWRITE)

**Current state**: Basic Dockerfile + optional Compose. No .dockerignore, no multi-stage, no service builder.

**New flow**:
```
Step 1: DETECT
  - Docker CLI installed? → Version
  - Docker daemon running? → Connection status
  - Dockerfile exists? → Show current content summary
  - docker-compose.yml exists? → Show services
  - .dockerignore exists? → Show status

Step 2a: DOCKERFILE CONFIGURATION
  - Base image selection (stack-aware: python:3.12-slim, node:20-alpine, etc.)
  - Working directory
  - Install command
  - Expose port
  - Entry command
  - Multi-stage build option (builder + runtime)
  - LIVE PREVIEW of generated Dockerfile

Step 2b: COMPOSE CONFIGURATION (optional)
  - Service builder: name, build context, ports, volumes, env vars
  - Add multiple services
  - Network configuration
  - LIVE PREVIEW of generated docker-compose.yml

Step 2c: DOCKERIGNORE (automatic)
  - Stack-aware .dockerignore generation

Step 3: APPLY & TEST
  - Write files
  - Offer to build: `docker compose build`
  - Offer to start: `docker compose up -d`
  - Show running containers
  - CTA: "Next: Set up CI/CD →"
```

**Backend used**: `/docker/status`, `/docker/generate/*`, `/docker/build`, `/docker/up`

#### 1.4 CI/CD Setup Wizard (REWRITE)

**Current state**: Basic workflow generation. No awareness of existing workflows, no lint, no deploy steps.

**New flow**:
```
Step 1: DETECT
  - .github/workflows/ exists? → List existing workflows
  - GitHub Actions or GitLab CI? → Auto-detect provider
  - Docker configured? → Can add Docker build/push step
  - Test framework detected? → Can add test step

Step 2: CONFIGURE
  - Trigger branches
  - Python/Node version (from project detection)
  - Steps builder:
    ☑ Install dependencies
    ☑ Run tests (framework-aware)
    ☑ Run linting (tool-aware: ruff, eslint)
    ☑ Type checking (mypy, pyright)
    ☐ Build Docker image
    ☐ Push to registry
    ☐ Deploy to K8s
  - Each step expandable with custom command
  - LIVE PREVIEW of generated workflow YAML

Step 3: APPLY & TRIGGER
  - Write workflow file
  - Option to commit & push
  - Option to dispatch first run
  - Show run status
  - CTA: "Next: Set up Kubernetes →" or "Next: Set up Terraform →"
```

**Backend used**: `/ci/status`, `/ci/generate/ci`, `/ci/generate/lint`, `/gh/actions/dispatch`

#### 1.5 Kubernetes Setup Wizard (REWRITE)

**Current state**: Very basic — just Deployment + Service. No Ingress, no ConfigMap, no Helm, no Skaffold.

**New flow**:
```
Step 1: DETECT
  - kubectl installed? → Version, cluster info
  - Cluster connected? → Context, nodes
  - k8s/ directory exists? → List manifests
  - Helm installed? → Releases
  - Skaffold installed? → Config detected
  - Docker image available? → Use for deployment

Step 2a: MANIFEST CONFIGURATION
  - App name (from project)
  - Container image (from Docker setup or custom)
  - Container port
  - Replicas
  - Namespace
  - Resource type builder:
    ☑ Deployment
    ☑ Service (type: ClusterIP/NodePort/LoadBalancer)
    ☐ Ingress (host, path, TLS)
    ☐ ConfigMap (key-value editor)
    ☐ Secret (key-value editor)
    ☐ HorizontalPodAutoscaler
  - LIVE PREVIEW of each manifest

Step 2b: HELM (optional)
  - Scaffold Helm chart from manifests
  - Values.yaml editor
  - Chart.yaml editor

Step 3: APPLY & VERIFY
  - Write manifest files
  - Option to apply to cluster: `kubectl apply -f k8s/`
  - Show deployment status
  - Show pod status
  - CTA: "Next: Set up Terraform →"
```

**Backend used**: `/k8s/status`, `/k8s/cluster`, `/k8s/generate`, `/k8s/generate/wizard`, `/k8s/apply`, `/k8s/resources`

#### 1.6 Terraform Setup Wizard (REWRITE)

**Current state**: Basic provider + backend. No variables, no modules, no resource selection.

**New flow**:
```
Step 1: DETECT
  - Terraform installed? → Version
  - terraform/ directory exists? → List .tf files
  - .terraform/ exists? → Initialized
  - terraform.tfstate exists? → State info
  - Backend configured? → Type

Step 2: CONFIGURE
  - Provider selection (AWS, GCP, Azure, DigitalOcean, other)
  - Region
  - Backend type (local, S3, GCS, Azure)
  - Backend configuration (bucket name, key prefix)
  - Resource starters:
    ☐ VPC/Network
    ☐ Compute instance
    ☐ K8s cluster (EKS/GKE/AKS)
    ☐ Database (RDS/CloudSQL)
    ☐ Object storage (S3/GCS)
  - Variables file with project defaults
  - LIVE PREVIEW of generated .tf files

Step 3: APPLY & VERIFY
  - Write .tf files
  - Run `terraform init`
  - Run `terraform validate`
  - Show validation results
  - Option to run `terraform plan`
```

**Backend used**: `/terraform/status`, `/terraform/generate`, `/terraform/init`, `/terraform/validate`, `/terraform/plan`

#### 1.7 DNS Setup Wizard (NEW — currently "coming soon")

**New flow**:
```
Step 1: DETECT
  - Domain configured in project.yml?
  - DNS records for domain? → Lookup
  - SSL certificate? → Check

Step 2: CONFIGURE
  - Domain name input
  - Target IP / CNAME
  - Mail provider (for MX records)
  - SPF/DMARC options
  - Generate recommended DNS records

Step 3: VERIFY
  - Run DNS lookup
  - Check SSL certificate
  - Show propagation status
```

**Backend used**: `/dns/status`, `/dns/lookup/*`, `/dns/ssl/*`, `/dns/generate`

#### 1.8 Pages Setup Wizard (NEW — currently just a tab switch)

**New flow**:
```
Step 1: DETECT
  - Pages config in project.yml? → Show segments
  - Builders available? → Show installed
  - Content folders configured? → Show list

Step 2: CONFIGURE
  - Create/edit segments
  - Select builder per segment
  - Configure custom domain
  - Select content sources

Step 3: BUILD & DEPLOY
  - Build all segments
  - Preview
  - Deploy
```

**Backend used**: `/pages/segments`, `/pages/builders`, `/pages/build/*`, `/pages/deploy`

---

### Phase 2: Integration Cards — Full Rewrite

**Goal**: Each card follows the standard anatomy, uses consistent helpers, and properly connects to its setup wizard.

#### Card Standard Structure:
```
┌─ Header ─────────────────────────────────┐
│ [Icon] [Title]          [Badge] [🔄]     │
│ [Subtitle]                               │
├─ Setup Banner (if not configured) ───────┤
│ "Docker is not configured. Set up →"     │
├─ Dependency Hint (if deps missing) ──────┤
│ "💡 Set up Git first to push images"     │
├─ Status Grid ────────────────────────────┤
│ ✅ Connected  │  12 containers  │ v24.0  │
├─ Actions ────────────────────────────────┤
│ [Build] [Start] [Stop] [Logs] [Generate] │
├─ Live Panel (tabbed, collapsed) ─────────┤
│ [Containers] [Images] [Networks]         │
│ ┌─ table/list content ──────────┐        │
│ └────────────────────────────────┘        │
└──────────────────────────────────────────┘
```

Each card to be rewritten (in order):
1. **Git Card** — branch/tag/stash management, proper .gitignore wizard
2. **GitHub Card** — auth, PRs, issues, releases, environments
3. **Docker Card** — full container management with proper compose wizard
4. **CI/CD Card** — workflow management with proper generate wizard
5. **K8s Card** — FULL REWRITE (currently 735 lines of mess), clean manifest management
6. **Terraform Card** — clean ops card with plan viewer
7. **Pages Card** — polish existing, add setup wizard link

---

### Phase 3: Wizard Step 5 — Clean Gateway

**Goal**: Wizard Step 5 becomes a clean checklist, NOT inline forms

```
🔌 Integrations

Your project's integration status. Click any item to configure it.

┌────────────────────────────────────────┐
│ ✅ Git          — repo initialized     │  [⚙️ Configure]
│ ⚠️ GitHub       — CLI not installed    │  [🔧 Set up →]
│ ✅ Docker       — Dockerfile found     │  [⚙️ Configure]
│ ❌ CI/CD        — no workflows         │  [🔧 Set up →]
│ ❌ Kubernetes   — not configured       │  [🔧 Set up →]
│ ❌ Terraform    — not configured       │  [🔧 Set up →]
│ ✅ Pages        — 2 segments           │  [⚙️ Configure]
│ ❌ DNS          — not configured       │  [🔧 Set up →]
└────────────────────────────────────────┘

💡 You can skip this step and set up integrations later
   from the Integrations tab.
```

**Clicking "Set up →" opens the setup wizard modal** (`openSetupWizard(key)`).
No inline forms. No duplication. Clean.

---

### Phase 4: Dashboard Progress & Onboarding

**Goal**: Dashboard clearly shows progress and guides next action

```
┌─ Setup Progress ─────────────────── 3/8 ┐
│ ━━━━━━━━━━━━━░░░░░░░░░░░░░░░░░░░  38%  │
│                                          │
│ ✅ Project configured                    │
│ ✅ Git initialized                       │
│ ✅ Docker containerized                  │
│ ⬜ GitHub — connect remote        [→]    │  ← suggested next
│ ⬜ CI/CD pipeline                 [→]    │
│ ⬜ Kubernetes                     [→]    │
│ ⬜ Terraform                      [→]    │
│ ⬜ DNS & Domain                   [→]    │
└──────────────────────────────────────────┘
```

---

## 5. EXECUTION ORDER

**This is the build order. Piece by piece. One integration at a time.**

| # | Task | Dependencies | Scope |
|---|---|---|---|
| **0.1** | Kill wizard step 5 inline sub-forms, make it a clean checklist | — | `_wizard_integrations.html` |
| **0.2** | Clean up CSS — establish card/wizard visual standards | — | `admin.css` |
| **0.3** | Clean up `_globals.html` helpers | — | `_globals.html` |
| **1.1** | **Git Setup Wizard** — full rewrite | 0.1, 0.2 | `_integrations_setup_modals.html` |
| **1.1b** | **Git Card** — full rewrite | 1.1 | `_integrations_git.html` |
| **1.2** | **GitHub Setup Wizard** — full rewrite (from link to real wizard) | 1.1 | `_integrations_setup_modals.html` |
| **1.2b** | **GitHub Card** — full rewrite | 1.2 | `_integrations_github.html` |
| **1.3** | **Docker Setup Wizard** — full rewrite | 1.1 | `_integrations_setup_modals.html` |
| **1.3b** | **Docker Card** — full rewrite | 1.3 | `_integrations_docker.html` |
| **1.4** | **CI/CD Setup Wizard** — full rewrite | 1.2, 1.3 | `_integrations_setup_modals.html` |
| **1.4b** | **CI/CD Card** — full rewrite | 1.4 | `_integrations_cicd.html` |
| **1.5** | **K8s Setup Wizard** — full rewrite | 1.3 | `_integrations_setup_modals.html` |
| **1.5b** | **K8s Card** — FULL REWRITE (biggest job) | 1.5 | `_integrations_k8s.html` |
| **1.6** | **Terraform Setup Wizard** — full rewrite | 1.5 | `_integrations_setup_modals.html` |
| **1.6b** | **Terraform Card** — full rewrite | 1.6 | `_integrations_terraform.html` |
| **1.7** | **Pages Setup Wizard** — new | — | `_integrations_setup_modals.html` |
| **1.8** | **DNS Setup Wizard** — new | — | `_integrations_setup_modals.html` |
| **2.0** | Dashboard progress widget polish | All above | `_dashboard.html` |
| **2.1** | Wizard Step 5 integration with new setup wizards | All above | `_wizard_integrations.html` |
| **2.2** | Post-wizard "Next Steps" modal polish | All above | `_boot.html` |
| **3.0** | Onboarding flow end-to-end testing | All above | All files |

---

## 6. FILE IMPACT MAP

### Files to REWRITE from scratch:
| File | Current Lines | Why |
|---|---|---|
| `_integrations_setup_modals.html` | 726 | Every wizard needs full rewrite |
| `_wizard_integrations.html` | 512 | Kill inline sub-forms, replace with clean checklist |
| `_integrations_k8s.html` | 735 | Completely bloated, beyond repair |

### Files to heavily modify:
| File | Current Lines | What changes |
|---|---|---|
| `_integrations_git.html` | 223 | Full card rewrite |
| `_integrations_github.html` | 289 | Full card rewrite |
| `_integrations_docker.html` | 498 | Full card rewrite |
| `_integrations_cicd.html` | 287 | Full card rewrite |
| `_integrations_terraform.html` | 304 | Full card rewrite |
| `_integrations_init.html` | 239 | Clean up helpers |
| `_globals.html` | 280+ | Verify/fix card helpers |
| `admin.css` | — | Add wizard/card visual standards |

### Files to lightly modify:
| File | What changes |
|---|---|
| `_boot.html` | Polish post-wizard flow |
| `_dashboard.html` | Polish progress widget |
| `_wizard_nav.html` | Simplify integration collection |

### Files to NOT touch:
| File | Why |
|---|---|
| All `routes_*.py` | Backend is solid |
| All `*_ops.py` | Service layer is solid |
| `_wizard_steps.html` | Steps 1-4 and 6 are fine |
| `_wizard_init.html` | Works fine |
| `_globals_wizard_modal.html` | Modal framework is fine |

---

## 7. SUCCESS CRITERIA

- [ ] Every integration has a proper multi-step setup wizard
- [ ] Every integration card follows standard anatomy
- [ ] Wizard Step 5 is a clean checklist, not inline forms
- [ ] After completing the wizard, user is guided to set up integrations in order
- [ ] Each setup wizard offers "Next: Set up X →" to continue the chain
- [ ] No duplicate UI for the same action
- [ ] All cards have proper setup banners when not configured
- [ ] All cards have proper dependency hints when deps missing
- [ ] Visual quality is premium — proper spacing, fonts, colors
- [ ] GitHub setup is a real wizard, not a link
- [ ] DNS setup is a real wizard, not "coming soon"
- [ ] Pages setup is a real wizard, not a tab switch
