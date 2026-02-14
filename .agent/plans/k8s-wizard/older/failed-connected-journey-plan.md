# 🔗 Connected Journey — "0 to Hero" Pipeline Plan

> **Date**: 2026-02-13
> **Status**: ✅ DONE — All 7 phases complete (0, 1, 2, 3, 4, 5, 6)
> **Depends on**: `comprehensive-card-overhaul.md` (card UX standards)

---

## 1. THE PROBLEM

The tool has **all the parts** but they don't form a **pipeline**:

- The wizard generates configs but doesn't link to ongoing operations
- Integration cards work independently but don't know about each other
- There's no notion of "Docker enables CI/CD → CI/CD enables K8s deployments → K8s needs Terraform for the cluster"
- A new user can't go from "empty project" to "deployed app" without manually discovering features
- Nobody can use this tool for **an actual useful result** — that's the core failure

## 2. THE DEPENDENCY GRAPH

This is how integrations **build on each other** in a real project:

```
                    ┌─────────────────┐
                    │   Project Init  │  ← Wizard steps 1-4
                    │ name, modules,  │
                    │ envs, secrets   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │    Git Setup    │  ← .git init, remote, .gitignore
                    │                 │
                    └────────┬────────┘
                             │
               ┌─────────────┼─────────────┐
               │             │             │
      ┌────────▼───┐  ┌─────▼──────┐  ┌───▼──────────┐
      │   Docker   │  │   GitHub   │  │    Pages     │
      │ Dockerfile │  │ repo link  │  │ docs setup   │
      │ Compose    │  │ envs/secr  │  │ builder cfg  │
      └────────┬───┘  └─────┬──────┘  └───┬──────────┘
               │             │             │
               └──────┬──────┘             │
                      │                    │
               ┌──────▼──────┐             │
               │    CI/CD    │ ◄───────────┘
               │ workflows   │  (build + deploy docs)
               │ test/lint   │
               │ docker push │
               └──────┬──────┘
                      │
          ┌───────────┼───────────┐
          │                       │
    ┌─────▼──────┐       ┌───────▼────────┐
    │ Kubernetes │       │   Terraform    │
    │ manifests  │       │ cluster setup  │
    │ Helm chart │       │ infra as code  │
    │ deploy     │       │                │
    └─────┬──────┘       └───────┬────────┘
          │                       │
          └───────────┬───────────┘
                      │
               ┌──────▼──────┐
               │    DNS &    │
               │   Domain    │
               │   config    │
               └─────────────┘
```

Each arrow means: "you typically need the parent before the child makes sense."

## 3. WHAT EXISTS TODAY

### Wizard (main setup)
- ✅ Steps 1-4: Project name, modules, secrets, content — **solid**
- ⚠️ Step 5: Integrations — has sub-wizards for Docker/K8s/Terraform/CI but they're **buried** and disconnected
- ✅ Step 6: Review + save project.yml — works

### Wizard sub-wizard actions (`/wizard/setup`)
- ✅ `setup_git` — git init + remote add
- ✅ `setup_docker` — generate Dockerfile + Compose
- ✅ `setup_k8s` — generate manifests
- ✅ `setup_ci` — generate CI workflow
- ✅ `setup_terraform` — generate terraform configs

### Integration cards (Integrations tab)
Each has: loadCard + live panels + some action modals + some generate modals

| Card | Load | Live | Actions | Generate | Status |
|------|------|------|---------|----------|--------|
| Git | ✅ | Commits | commit, pull, push, log | .gitignore | Working |
| GitHub | ✅ | PRs, runs | create env, push secrets | — | Working |
| CI/CD | ✅ | Workflows, runs, coverage | trigger workflow | CI workflow | Working |
| Docker | ✅ | Containers, images, compose, nets, vols | logs, inspect, pull, exec, rm | Dockerfile, Compose, .dockerignore | Working |
| K8s | ✅ | Pods, svcs, deploys, events, logs | apply, scale, describe, delete | Manifests, Helm install, manifest wizard | Working |
| Terraform | ✅ | State, plan, providers, outputs, graph | init, plan, apply, destroy, fmt, workspace | TF config | Working |
| Pages | ✅ | Segments, builders | build, deploy, merge | Segment wizard, config | Working |

### DevOps cards (DevOps tab)
| Card | Load | Live | Actions | Generate |
|------|------|------|---------|----------|
| Security | ✅ | scans | sensitive files, gitignore analysis | gitignore |
| Testing | ✅ | — | run tests, coverage, inventory | test template |
| Docs | ✅ | — | coverage, check links | changelog, readme |
| K8s | ✅ | — | validate, cluster, resources | manifests |
| Terraform | ✅ | — | validate, plan, state, workspaces | TF config |
| DNS | ✅ | — | lookup, ssl check | DNS config |
| Quality | ✅ | — | run category | quality config |
| Packages | ✅ | — | outdated, audit, list | install/update |
| Environment | ✅ | env vars, diff, drift | activate, drift | example .env |

### What's MISSING: the connective tissue

1. **No first-launch detection** — Dashboard shows empty cards, no redirect to wizard
2. **No "Setup this integration" CTA on cards** — When GitHub card says "not configured", there's no button to fix it
3. **No cross-card awareness** — Docker card doesn't know if K8s needs a different Dockerfile
4. **No wizard re-entry from cards** — You can't go from the K8s card back to the K8s sub-wizard
5. **No progress indicator** — User doesn't know what's configured vs what's not
6. **No dependency hints** — K8s card doesn't say "Set up Docker first to containerize your app"
7. **Duplicate generate modals** — Both wizard and integration cards can generate Docker/K8s/TF configs, with different UIs

---

## 4. PROPOSED ARCHITECTURE

### 4.1 Project Status Model

Add a `/api/project/status` endpoint that returns the **complete integration state**:

```json
{
  "project": { "configured": true, "name": "my-app" },
  "integrations": {
    "git":       { "status": "ready",    "has_remote": true },
    "github":    { "status": "ready",    "repo": "user/my-app" },
    "docker":    { "status": "partial",  "has_dockerfile": true, "has_compose": false },
    "cicd":      { "status": "missing",  "workflows": 0 },
    "k8s":       { "status": "missing",  "manifests": 0, "cluster_connected": false },
    "terraform": { "status": "missing",  "tf_files": 0, "initialized": false },
    "pages":     { "status": "ready",    "segments": 2 },
    "dns":       { "status": "missing" }
  },
  "devops": {
    "security":  { "status": "ok",   "score": 85 },
    "testing":   { "status": "warn", "coverage": 60 },
    "quality":   { "status": "ok" },
    "packages":  { "status": "warn", "outdated": 3 }
  },
  "suggested_next": "cicd"  // What should the user focus on next?
}
```

### 4.2 Integration Setup Modals (linked FROM cards)

Each integration card gets a **"Setup" button** that opens a focused setup modal.
These are NOT the wizard sub-wizards — they're **standalone modals** that can be invoked from:
- The integration card itself (when status is "missing" or "partial")
- The wizard step 5 (as embedded sub-wizards, like today)
- A "Next Steps" panel on the dashboard
- Cross-card CTAs (e.g., K8s card saying "Set up Docker first →")

The key: **one modal per integration**, reusable everywhere.

### 4.3 Progressive Dependency Hints

Each card includes awareness of its dependencies:

```javascript
// In _integrations_docker.html
if (!_projectStatus.integrations.git.has_remote) {
    showHint('docker', 'Set up a Git remote first to push container images', 'git');
}

// In _integrations_k8s.html
if (!_projectStatus.integrations.docker.has_dockerfile) {
    showHint('k8s', 'Containerize your app with Docker before deploying to K8s', 'docker');
}

// In _integrations_cicd.html
if (!_projectStatus.integrations.docker.has_dockerfile && 
    !_projectStatus.integrations.k8s.manifests) {
    showHint('cicd', 'Set up Docker and/or K8s first for deployment workflows', 'docker');
}
```

### 4.4 Dashboard "Next Steps" Panel

The dashboard gets a **progress tracker** that shows:
```
Project Setup Progress
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 40%

✅ Project configured
✅ Git initialized
✅ Docker containerized
⬜ CI/CD pipeline  ← "Set up CI/CD →"
⬜ Kubernetes manifests
⬜ Terraform infrastructure
⬜ DNS & domain
```

Each unconfigured item links directly to the setup modal for that integration.

---

## 5. IMPLEMENTATION PLAN

### Phase 0: Fix what's broken first ✅ DONE (2026-02-13)
1. ✅ `.bak` backup files removed
2. ✅ All tabs load correctly — `node --check` passes on all child files
3. ✅ DevOps cards syntax fixed (missing closing braces)

### Phase 1: Backend — Project Status API ✅ DONE (2026-02-13)
1. ✅ Created `routes_project.py` with `project_bp`
2. ✅ `/api/project/status` — probes git, docker, github, cicd, k8s, terraform, pages, dns
3. ✅ `/api/project/next` — suggests next integration based on dependency graph
4. ✅ Registered in `server.py`
5. ✅ Tested: returns 200, correct status, correct progress percentage

### Phase 2: First-Launch Experience ✅ DONE (2026-02-13)
1. ✅ Detect missing `project.yml` → auto-redirect to Wizard tab (`_boot.html`)
2. ✅ Welcome toast: "👋 Welcome! Let's set up your project."
3. ✅ After wizard save → "Next Steps" modal with top 3 incomplete integrations
   - Uses `getProjectStatus(true)` for fresh data
   - Shows suggested-next integration highlighted with accent
   - "Set up →" buttons per integration → `openSetupWizard(key)`
   - "Skip for now" → dashboard

### Phase 3: Integration Setup Modals (the heart of it) ✅ DONE (2026-02-13)
Created `_integrations_setup_modals.html` with standalone 3-step wizard modals.
Each modal: **Detect → Configure → Review & Apply**

Completed modals:
1. ✅ `openGitSetupWizard()` — git init, remote, .gitignore
2. ✅ `openDockerSetupWizard()` — Dockerfile, Compose, .dockerignore
3. ✅ `openCICDSetupWizard()` — GitHub Actions workflow with Docker/test/lint steps
4. ✅ `openK8sSetupWizard()` — Deployment, Service, Ingress, ConfigMap manifests
5. ✅ `openTerraformSetupWizard()` — provider, region, resources, backend
6. ✅ GitHub → opens cli.github.com + auth toast
7. ✅ Pages → toast + navigates to Integrations tab
8. ✅ DNS → toast (coming soon)

Dispatcher: `openSetupWizard(key)` — single entry point for all 8 wizards.

Foundation built:
- ✅ `_globals_wizard_modal.html` — multi-step wizard modal system (navigation, validation, data persistence)
- ✅ CSS for wizard modal system (status grid, section headers, review items, error/warn panels)

### Phase 4: Card CTAs & Dependency Hints ✅ DONE (2026-02-13)
1. ✅ `cardSetupBanner()` + `cardDepHint()` helpers in `_integrations_init.html`
2. ✅ CSS for `.card-setup-banner` and `.card-dep-hint` in `admin.css`
3. ✅ Project status cache (`_fetchIntProjectStatus`) for dependency checks
4. ✅ Git card — setup banner when no repo
5. ✅ Docker card — setup banner when CLI missing + Git dep hint
6. ✅ GitHub card — setup banner when gh CLI missing + Git dep hint
7. ✅ CI/CD card — setup banner when no config + Docker/GitHub dep hints
8. ✅ K8s card — setup banners for kubectl missing / no manifests + Docker dep hint
9. ✅ Terraform card — setup banners for CLI missing / no config + K8s dep hint
10. ✅ Dashboard progress widget — all 8 integrations now have Setup buttons

### Phase 5: Dashboard Progress Tracker ✅ DONE (2026-02-13)
1. ✅ HTML panel in `_tab_dashboard.html`
2. ✅ `loadSetupProgress()` in `_dashboard.html`
3. ✅ Progress bar + integration checklist with status icons
4. ✅ CTA buttons per integration launching setup wizards
5. ✅ "Suggested next" hint with accent styling
6. ✅ Wired into boot sequence in `_boot.html`

### Phase 6: Cross-Tab Navigation ✅ DONE (2026-02-13)
1. ✅ Wizard step 5 integration cards: added "🚀 Full Setup →" button that opens standalone setup modals via `openSetupWizard(key)` alongside the existing inline "⚙️ Setup" button
2. ✅ `_wizKeyToSetupKey()` helper maps wizard keys (`int:git`, `int:docker`, etc.) to dispatcher keys
3. ✅ `cardCrossLink(targetTab, label)` reusable helper in `_integrations_init.html`
4. ✅ Integration → DevOps cross-links on: Docker, K8s, Terraform, CI/CD cards
5. ✅ DevOps → Integration cross-links on: K8s, Terraform cards

---

## 6. THE FULL "0 TO HERO" JOURNEY (after this plan)

```
1. User installs, runs ./manage.sh web
   → Sees "Welcome! Let's set up your project"
   → Auto-redirected to Wizard

2. Wizard steps 1-4: Project name, modules, secrets, content
   → project.yml generated
   → Redirect to Dashboard with "Next Steps" panel

3. Dashboard shows progress: "4/11 steps complete"
   → "Next: Set up Git →" CTA
   → Opens Git setup modal → git init + remote

4. "Next: Containerize with Docker →"
   → Opens Docker setup modal
   → Generates Dockerfile + Compose
   → "Try it: Build & Run →" → docker compose up

5. "Next: Connect GitHub →"
   → Opens GitHub setup modal
   → Links repo, creates environments, pushes secrets

6. "Next: Set up CI/CD →"
   → Opens CI/CD setup modal
   → Generates workflow (stack-aware, Docker-aware)
   → "Try it: Trigger workflow →" → dispatches first run

7. "Next: Deploy to Kubernetes →"
   → Opens K8s setup modal
   → Detects Docker image from step 4
   → Generates Deployment + Service + Ingress
   → "Try it: Apply to cluster →"

8. User can now SWITCH to operational mode:
   → DevOps tab → K8s card → live pod status, scale, logs
   → DevOps tab → Testing card → run tests, check coverage
   → DevOps tab → Security card → scan for vulnerabilities

9. Optional: "Add Terraform for cluster management →"
   → Opens Terraform setup modal
   → Pre-fills provider based on K8s context
   → Generates main.tf + variables.tf

10. Optional: "Set up documentation site →"
    → Pages card → add segments → configure builder → deploy

11. Dashboard shows: "Setup complete! All integrations configured."
    → Full operational mode — all cards showing live data
```

---

## 7. FILE IMPACT ANALYSIS

### New files created ✅
| File | Purpose | Status |
|------|---------|--------|
| `routes_project.py` | `/api/project/status` and `/api/project/next` | ✅ Done |
| `_globals_wizard_modal.html` | Multi-step wizard modal system | ✅ Done |
| `_integrations_setup_modals.html` | Setup wizards for Git/Docker/CI/K8s/TF | ✅ Done |

### Modified files ✅
| File | Changes | Status |
|------|---------|--------|
| `server.py` | Register `project_bp` | ✅ Done |
| `dashboard.html` | Include wizard modal + setup modals | ✅ Done |
| `_tab_dashboard.html` | Add progress tracker HTML panel | ✅ Done |
| `_dashboard.html` | Add `loadSetupProgress()` | ✅ Done |
| `_boot.html` | Add `loadSetupProgress()` to boot | ✅ Done |
| `admin.css` | Wizard modal CSS system | ✅ Done |

### Still to modify
| File | Changes |
|------|---------|
| `_devops_init.html` | Cross-link to integration setup modals |
| `_wizard_integrations.html` | Reuse standalone modals instead of inline |

---

## 8. EXECUTION ORDER

Priority is **what delivers the most user value soonest**:

1. **Phase 0** — Fix broken things (< 1 hour)
2. **Phase 1** — Project Status API (backend foundation, ~2 hours)
3. **Phase 3** — Setup modals, one at a time in dependency order (~1-2 hours each)
4. **Phase 2** — First-launch experience (~1 hour)
5. **Phase 4** — Card CTAs & hints (~2 hours)
6. **Phase 5** — Dashboard progress tracker (~2 hours)
7. **Phase 6** — Cross-tab navigation (~1 hour)

Total estimated: **15-20 hours of implementation** across ~6 phases.

---

## 9. RELATIONSHIP TO COMPREHENSIVE CARD OVERHAUL

The `comprehensive-card-overhaul.md` plan defines:
- Card UX standards (anatomy, modals, CSS)
- Per-card feature specifications
- New cards (Ansible, Monitoring, Registry)

**This plan (connected-journey) adds:**
- The dependency graph between cards
- The project status backbone
- The first-launch → setup → operational flow
- The progress tracking system
- Cross-card awareness and linking

**They should be implemented together**: the card overhaul provides the UX foundation,
the connected journey provides the threading that makes it usable.

### Recommended merge order:
1. Card UX standards first (Phase 1 of card overhaul = foundation CSS/JS helpers)
2. Then connected journey Phase 1 (status API) 
3. Then one card at a time: overhaul the card + add setup modal + add CTA + add hints
4. This way each card is "done done" when it's touched
