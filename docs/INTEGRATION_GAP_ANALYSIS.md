# Integration & Card Gap Analysis

> Generated: 2026-02-12  
> Purpose: Evaluate the current state of integrations, DevOps cards, and Audit cards — identify duplications, missing infrastructure, and plan the wizard/preferences system.

---

## 1. Current Inventory

### Integrations Tab (5 cards)

| Card | Route File | Backend | Status |
|------|-----------|---------|--------|
| 🔀 Git | `routes_integrations.py` | `git` CLI | ✅ Works — local repo status |
| 🐙 GitHub | `routes_integrations.py` | GitHub API | ✅ Works if token configured |
| 🔄 CI/CD | `routes_ci.py` | GitHub Actions API | ⚠️ Needs GitHub token |
| 🐳 Docker | `routes_docker.py` | `docker` CLI | ❌ Stub — "No Docker modules detected" |
| 📄 GitHub Pages | `routes_pages.py` | Multi-segment builder | ✅ Works |

**Missing from Integrations:**
- ☸️ **Kubernetes** — exists in DevOps but NOT in Integrations
- 🏗️ **Terraform** — exists in DevOps but NOT in Integrations
- 🌐 **DNS & CDN** — exists in DevOps but NOT in Integrations

### DevOps Tab (9 cards)

| Card | Route File | Backend | Status | Duplicates? |
|------|-----------|---------|--------|-------------|
| 🔐 Security | `routes_security_scan.py` | `security_ops.py` | ⚠️ Slow (pip-audit 120s timeout) | **YES** — duplicates Audit ⚠️ Risks |
| 🧪 Testing | `routes_testing.py` | `testing_ops.py` | ✅ Works |  |
| 🔧 Quality | `routes_quality.py` | `quality_ops.py` | ✅ Works |  |
| 📦 Packages | `routes_packages.py` | `package_ops.py` | ✅ Works |  |
| ⚙️ Environment | `routes_infra.py` | Env detection | ✅ Works |  |
| 📚 Docs | `routes_docs.py` | `docs_ops.py` | ✅ Works |  |
| ☸️ Kubernetes | `routes_k8s.py` | `kubectl` CLI | ❌ Shell only — no integration card |
| 🏗️ Terraform | `routes_terraform.py` | `terraform` CLI | ❌ Shell only — no integration card |
| 🌐 DNS & CDN | `routes_dns.py` | DNS resolution | ⚠️ Works but limited |

### Audit Tab (key cards/sections)

| Card | Source | Status |
|------|--------|--------|
| 📊 Scores | `audit/scoring.py` | ✅ Works |
| 🏗️ System Profile (L0) | `audit/l0_system.py` | ✅ Works |
| 📦 Dependencies (L1) | `audit/l1_deps.py` | ✅ Works |
| 🏢 Structure (L1) | `audit/l1_structure.py` | ✅ Works |
| 🔌 Clients (L1) | `audit/l1_clients.py` | ✅ Works |
| ⚠️ Risks (L2) | `audit/l2_risk.py` | ✅ Works — includes secret scanning |
| 🔍 Code Health (L2) | `audit/l2_quality.py` | ✅ Works |
| 📂 Structure Analysis (L2) | `audit/l2_structure.py` | ✅ Works |
| 📦 Repo Health (L2) | `audit/l2_repo.py` | ✅ Works |

---

## 2. Duplications

### 🔐 Security Card (DevOps) vs ⚠️ Risks Card (Audit)

**The most significant duplication.** Both scan for the same things:

| Feature | DevOps Security | Audit Risks |
|---------|----------------|-------------|
| Secret scanning | `scan_secrets()` | `scan_secrets()` via `_security_findings()` |
| Sensitive files | `detect_sensitive_files()` | Same via posture |
| .gitignore analysis | `gitignore_analysis()` | Same via posture |
| Vault status | `vault_status()` | Same via posture |
| Dependency audit | `package_audit()` | Separate via `_dependency_findings()` |
| Posture score | Full posture | Not shown |
| Dismiss mechanism | ❌ None | ✅ `# nosec` inline |

**Resolution:** The DevOps Security card should become a **summary widget** that shows the posture score + grade and links to the Audit tab for details. All the heavy scanning (secret scan, dependency audit) should only happen in the Audit pipeline, not separately in DevOps.

---

## 3. Integration Infrastructure Gaps

### 🐳 Docker — Largely Stub

**Current state:** The Integration card shows "No Docker modules detected". The DevOps tab has no Docker card.

**Backend (`routes_docker.py`):**
- Has routes for `/docker/status`, `/docker/images`, `/docker/containers`
- Calls `docker` CLI commands
- Only works if Docker is installed and running

**Missing:**
- No module detection integration (project.yml → docker module)
- No Dockerfile analysis
- No docker-compose analysis
- No container management (start/stop/logs in the UI)
- Install recipe exists (`sudo apt-get install docker.io`)

**Effort: 🟡 Medium** — backend routes exist, need UI + module detection + compose parsing

### ☸️ Kubernetes — DevOps Only

**Current state:** DevOps card exists with `kubectl` output. No entry in Integrations tab.

**Backend (`routes_k8s.py`):**
- Routes for `/k8s/status`, `/k8s/namespaces`, `/k8s/pods`, `/k8s/services`
- Calls `kubectl` directly
- Only works if kubeconfig is set up

**Missing:**
- No Integration card (connection setup, cluster selection)
- No namespace picker in DevOps card
- No pod logs viewer
- No manifest validation
- No Helm chart detection
- Install recipes exist for `kubectl`, `helm`

**Effort: 🔴 Large** — need Integration card (cluster config), namespace management, pod/service detail views, Helm integration

### 🏗️ Terraform — DevOps Only

**Current state:** DevOps card exists. No entry in Integrations tab.

**Backend (`routes_terraform.py`):**
- Routes for `/terraform/status`, `/terraform/plan`, `/terraform/validate`
- Calls `terraform` CLI
- Only works if terraform is installed and initialized

**Missing:**
- No Integration card (workspace selection, backend config)
- No state viewer
- No drift detection display
- Install recipe exists (snap)

**Effort: 🟡 Medium** — backend exists, need Integration card + enhanced state display

### 🌐 DNS & CDN — DevOps Only

**Current state:** DevOps card does DNS resolution checks. No entry in Integrations tab.

**Missing:**
- No Integration card (domain configuration)
- No CDN integration (Cloudflare, etc.)
- Limited to DNS record lookup

**Effort: 🟢 Small** — could be a simple config-based Integration card

---

## 4. The Wizard / Setup Flow

### Concept

Instead of showing everything by default and having empty/broken cards, implement:

1. **First-run wizard** that detects the project environment
2. **User preferences** that control card visibility per tab
3. **Integration setup cards** that guide installation + configuration

### Wizard Steps

```
Step 1: Project Detection (auto)
  ├─ Detect stacks: Python? Node? Rust? Go?
  ├─ Detect tools: Docker? K8s? Terraform?
  ├─ Detect services: GitHub? GitLab? Bitbucket?
  └─ Show summary of what's found

Step 2: Integration Selection (user picks)
  ├─ ☑ Git (detected)
  ├─ ☑ GitHub (detected, token needed)
  ├─ ☐ Docker (not detected — offer install)
  ├─ ☐ Kubernetes (not detected — offer install)
  ├─ ☐ Terraform (not detected — offer install)
  ├─ ☑ GitHub Pages (detected)
  └─ Each unchecked = hidden from UI

Step 3: Tool Installation (for selected integrations)
  ├─ Missing tools listed with install buttons
  ├─ pip-audit, bandit, helm, kubectl, etc.
  └─ Skip option for manual install later

Step 4: Configuration (per active integration)
  ├─ GitHub: token setup
  ├─ Kubernetes: kubeconfig path
  ├─ Docker: verify daemon access
  └─ DNS: domain list
```

### User Preferences System

**Already partially exists** in the DevOps tab:
- `_devopsPrefs` — fetched via `GET /devops/prefs`  
- Each card can be `auto | manual | hidden`
- Saved via `PUT /devops/prefs`
- Preferences modal already built (`openDevopsPrefsModal()`)

**Needs to be extended:**
- Cover Integrations tab cards (currently no prefs)
- Cover Audit tab sections (currently all show)
- Store in `.state/user_prefs.json` (already exists?)
- Wizard writes initial prefs based on user selections
- Re-running wizard resets/updates prefs

### Backend Work Needed

| Item | Location | Effort |
|------|----------|--------|
| Preferences for Integrations tab | `routes_integrations.py` + `devops_cache.py` | 🟢 Small |
| Wizard detection endpoint | New route, uses existing detection | 🟢 Small |
| Wizard preference save | Extends existing prefs system | 🟢 Small |
| Docker module detection | `detection.py` | 🟡 Medium |
| K8s Integration card | `routes_k8s.py` + new HTML | 🟡 Medium |
| Terraform Integration card | `routes_terraform.py` + new HTML | 🟡 Medium |
| DNS Integration card | `routes_dns.py` + new HTML | 🟢 Small |
| Security card → summary only | `_devops.html` refactor | 🟢 Small |

### Frontend Work Needed

| Item | Location | Effort |
|------|----------|--------|
| Wizard modal (multi-step) | New `_wizard.html` | 🟡 Medium |
| Integration prefs toggle | `_integrations.html` | 🟢 Small |
| DevOps Security → link to Audit | `_devops.html` | 🟢 Small |
| K8s Integration card UI | `_integrations.html` | 🟡 Medium |
| Terraform Integration card UI | `_integrations.html` | 🟡 Medium |
| Docker card enhancement | `_integrations.html` | 🟡 Medium |

---

## 5. Priority Ordering

### Phase 1: Quick Wins (now)
- [x] Fix pip-audit install recipe (added to `no_sudo_commands`)
- [x] Fix audit log detail click (all entries now clickable)
- [x] Log dismissals to audit activity log
- [x] DevOps Security card → lightweight summary that links to Audit Risks

### Phase 2: Deduplication & Preferences
- [x] Refactor Security card to posture-score-only + "Open in Audit" link
- [x] Extend preferences to Integrations tab
- [x] User prefs store for cross-tab consistency (unified `devops_prefs.json`)
- [x] Hide broken/stub cards by default (Docker hidden, K8s/Terraform/DNS hidden)

### Phase 3: Wizard
- [x] First-run detection endpoint (`GET /wizard/detect`)
- [x] Wizard modal (3 steps: Detect → Configure → Install)
- [x] Integration selection → writes prefs
- [x] Tool installation step (leverages existing `/audit/install-tool` endpoint)

### Phase 4: Integration Infrastructure
- [ ] Docker: Dockerfile + compose analysis, container list
- [ ] Kubernetes: Integration card, cluster connect, pod viewer
- [ ] Terraform: Integration card, workspace picker, state viewer
- [ ] DNS: Domain config card

---

## 6. Files to Touch

```
src/ui/web/templates/scripts/_devops.html          # Security card → summary
src/ui/web/templates/scripts/_integrations.html     # Prefs + new cards
src/ui/web/templates/scripts/_wizard.html           # New: setup wizard
src/ui/web/templates/partials/_tab_integrations.html # K8s, Terraform, DNS cards
src/ui/web/routes_audit.py                          # Install recipes (done)
src/ui/web/routes_devops.py                         # Prefs for integrations
src/ui/web/routes_k8s.py                            # Integration mode
src/ui/web/routes_terraform.py                      # Integration mode
src/ui/web/routes_docker.py                         # Enhanced status
src/core/services/devops_cache.py                   # Cross-tab prefs
```
