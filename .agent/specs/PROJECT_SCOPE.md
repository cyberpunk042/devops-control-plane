# Project Scope — Solution Control Plane

> **Source of truth** for what this platform does — every feature, every surface,
> every capability. What's in scope, what's not, and what's coming.
>
> Derived from: `README.md`, `DESIGN.md`, `ARCHITECTURE.md`, `WEB_ADMIN.md`,
> `DEVOPS_UI_GAP_ANALYSIS.md`, `INTEGRATION_GAP_ANALYSIS.md`

---

## Mission

Build a **general-purpose solution control plane** — a meta-tool that discovers
what a project is, what it needs, and how to act on it — through any interface.

**Not an application.** A management platform for applications.

---

## 1. Core Capability Pillars

### 1.1 Project Visibility & Observability
- **Technology detection** — auto-scan 20+ stacks, report versions
- **Unified project status** — health view across all modules and environments
- **Audit trail** — append-only ledger of every operation
- **Health score** — aggregated health across all domains

### 1.2 Integrations
- **Git** — status, commit, push, pull, branch management
- **GitHub** — secrets, environments, PRs, Actions, Releases
- **Docker** — container lifecycle management
- **Kubernetes** — orchestration, manifest generation, cluster operations
- **Helm** — chart detection, release management, chart scaffolding
- **CI/CD** — workflow detection, generation, triggering, monitoring
- **Terraform** — IaC detection, plan, apply, state management
- **Extensible** — pluggable adapter protocol for any tool

### 1.3 Vaults (2 systems)
- **Secret / Variable Vault** — AES-256-GCM encrypted .env, key CRUD, GitHub Secrets sync, auto-lock
- **Content Vault** — per-file encryption, binary envelope, inline preview

### 1.4 Project & Environment Management
- **Environment management** — create, switch, compare configs across dev/staging/prod
- **Backup system** — create, restore, export, archive
- **Documentation sites** — 6 SSG builders (Docusaurus, MkDocs, Hugo, Sphinx, Raw, Custom)
- **Content management** — file browser, media optimization, GitHub Release uploads

### 1.5 Solution Evolution & Augmentation
- Stack detection (20 technology definitions)
- Integration guidance (detect gaps, suggest paths)
- Solution analysis (structure, dependencies, gaps)

### 1.6 Setup Wizard
- Guided step-by-step setup for project, environments, secrets, integrations
- **K8s sub-wizard** — service definitions → manifest generation → Skaffold/Helm configuration
- **CI sub-wizard** — stack detection → workflow generation

### 1.7 Debugging
- Built-in diagnostic tools accessible from web dashboard

### 1.8 Resource Links
- Quick access to remote interfaces (repos, dashboards, CI, deploys, monitoring)

### 1.9 Multi-Module & Multi-Stack
- Mono-repo support with multiple services/modules
- Multiple technology stacks within a single solution

---

## 2. Three-Interface Parity (Iron Rule)

Every capability is accessible from **all three interfaces**:

| Interface | How | Best For |
|-----------|-----|----------|
| `./manage.sh` | Interactive terminal menu | Daily ops, guided workflows |
| CLI | `python -m src.main <command>` | Scripting, CI, automation |
| Web Dashboard | Flask SPA at localhost:8000 | Visual management, content, setup wizard |

**No business logic in the interface layer.** All actions route through core services.

---

## 3. Web Dashboard Tabs

| Tab | Cards / Sections | Key Actions |
|-----|-----------------|-------------|
| 📊 Dashboard | Health score, project status widgets | Overview, recommendations |
| 🧙 Setup | Wizard (project → services → K8s → CI) | Guided onboarding |
| 🔐 Secrets | Vault status, key management | Lock/unlock, CRUD, export |
| ⚡ Commands | Stack capability runner | Run any capability |
| 📁 Content | File browser, media gallery | Encrypt/decrypt, optimize, release |
| 🔌 Integrations | Git, GitHub, CI/CD, Docker, Pages | Status + actions per integration |
| 🛠 DevOps | 9 cards (see below) | Status + actions per domain |
| 🔍 Audit | Security audit findings | Scan, dismiss, track |
| 🐛 Debugging | Diagnostic tools | Troubleshoot |

### DevOps Tab — 9 Cards
| Card | Backend Service | Status |
|------|----------------|--------|
| 🔐 Security | `security_ops.py` | ✅ Full |
| 🧪 Testing | `testing_ops.py` | ✅ Full |
| 📋 Quality | `quality_ops.py` | ✅ Full |
| 📦 Packages | `package_ops.py` | ✅ Full |
| ⚙️ Environment | `env_ops.py` | ✅ Full |
| 📚 Documentation | `docs_ops.py` | ✅ Full |
| ☸️ Kubernetes | `k8s_ops.py` + `k8s_detect.py` + `k8s_helm.py` | ✅ Partial (wizard + Helm routes exist) |
| 🏗️ Terraform | `terraform_ops.py` | ✅ Full |
| 🌐 DNS & CDN | `dns_cdn_ops.py` | ✅ Full |

---

## 4. DevOps Integration Depth

For each DevOps technology, the platform must achieve full **Detect → Observe → Facilitate → Act** coverage.

### 4.1 Kubernetes — Full Pipeline

| Phase | What | Status |
|-------|------|--------|
| **Detect** | Manifests (YAML), Helm charts, Kustomize overlays, Skaffold configs | ✅ Implemented |
| **Detect** | kubectl/helm/skaffold CLI availability + versions | ✅ Implemented |
| **Detect** | Skaffold profiles, portForward, build/deploy strategy, tag policy | ✅ Implemented (0.3.1) |
| **Observe** | Cluster connection, namespaces, pods, services, events, logs | ✅ Implemented |
| **Observe** | Helm releases (installed), release values, release status | ✅ Routes exist |
| **Facilitate** | Generate manifests (Deployment, Service, Ingress, ConfigMap, Secret, PVC) from wizard | ✅ Implemented |
| **Facilitate** | Generate Skaffold config (build, deploy, profiles, portForward, envsubst hooks) | ✅ Implemented (0.3.x) |
| **Facilitate** | Generate Helm Chart.yaml + values.yaml + templates/ scaffolding | ❌ **NOT IMPLEMENTED** |
| **Act** | Apply manifests, delete resources, scale, port-forward | ✅ Implemented |
| **Act** | Helm install, upgrade, template, lint | ✅ CLI wrappers exist |

### 4.2 Helm — Specific Requirements

| Phase | Requirement | Status |
|-------|-------------|--------|
| **Detect** | Find Chart.yaml recursively, skip vendor dirs | ✅ |
| **Detect** | Parse name, version, description, appVersion, type | ✅ |
| **Detect** | Detect chart structure: values.yaml, templates/, charts/, Chart.lock | ✅ |
| **Detect** | Detect env-specific values files (values-{env}.yaml) | ✅ |
| **Detect** | helm CLI availability | ✅ |
| **Observe** | List installed releases (`helm list`) | ✅ CLI wrapper |
| **Observe** | Get release values (`helm get values`) | ✅ CLI wrapper |
| **Facilitate** | Generate Chart.yaml from wizard state (name, version, description, deps) | ❌ **MISSING** |
| **Facilitate** | Generate values.yaml from wizard services (image, port, replicas, env vars) | ❌ **MISSING** |
| **Facilitate** | Generate templates/ (deployment.yaml, service.yaml, ingress.yaml) | ❌ **MISSING** |
| **Facilitate** | Generate values-{env}.yaml per environment | ❌ **MISSING** |
| **Facilitate** | Detection round-trip: generate → write → detect confirms | ❌ **MISSING** |
| **Act** | `helm install` with all options | ✅ CLI wrapper |
| **Act** | `helm upgrade --install` with all options | ✅ CLI wrapper |
| **Act** | `helm template` (offline render) | ✅ CLI wrapper |
| **Act** | `helm lint` | stack.yml exists, no wrapper test |
| **Act** | `helm package` | stack.yml exists, no wrapper test |
| **Act** | `helm dependency update` | stack.yml exists, no wrapper test |

### 4.3 CI/CD — Requirements

| Phase | Requirement | Status |
|-------|-------------|--------|
| **Detect** | Find workflow files across 7 providers | Partial |
| **Detect** | Parse workflow names, triggers, jobs, step counts | Partial |
| **Observe** | Pipeline runs, test results, coverage | Partial (GitHub only) |
| **Facilitate** | Generate workflows from detected stacks | ❌ **MISSING** |
| **Act** | Trigger, cancel, re-run workflows | Partial (GitHub dispatch) |

### 4.4 Docker — Requirements

| Phase | Requirement | Status |
|-------|-------------|--------|
| **Detect** | Dockerfiles, compose configs, .dockerignore | ✅ |
| **Observe** | Running containers, images, volumes, logs | ❌ **MISSING** |
| **Facilitate** | Generate Dockerfiles from stacks, compose from modules | ❌ **MISSING** |
| **Act** | Build, push, start/stop/restart, exec, prune | ❌ **MISSING** |

### 4.5 Terraform — Requirements

| Phase | Requirement | Status |
|-------|-------------|--------|
| **Detect** | main.tf, terraform.tf, versions.tf, providers, modules | ✅ |
| **Observe** | State, resources, workspaces | ✅ |
| **Facilitate** | Generate Terraform configs from needs | ✅ Partial |
| **Act** | Init, validate, plan, apply, destroy | ✅ |

### 4.6 DNS & CDN — Requirements

| Phase | Requirement | Status |
|-------|-------------|--------|
| **Detect** | CDN provider config files (Cloudflare, CloudFront, Fastly, Netlify, Vercel, GitHub Pages) | ✅ |
| **Detect** | Domain extraction from project configs (CNAME, netlify.toml, vercel.json, etc.) | ✅ |
| **Detect** | DNS zone files (*.zone, *.dns, db.*) | ✅ |
| **Detect** | SSL/TLS certificate files (*.pem, *.crt, *.cert, *.key) | ✅ |
| **Detect** | CDN CLI availability (wrangler, aws, fastly, netlify, vercel) | ✅ |
| **Observe** | DNS lookup (A, CNAME, MX, TXT, NS records via `dig`) | ✅ |
| **Observe** | SSL certificate check (validity, issuer, expiry via `openssl`) | ✅ |
| **Facilitate** | Generate DNS records (A, CNAME, MX for Google/Protonmail, SPF, DMARC) | ✅ |
| **Facilitate** | Generate BIND zone file from records | ✅ |
| **Act** | No CLI actions (DNS is read-only from project perspective) | N/A |

---

## 5. What's In Scope for Alpha (Milestones 0.x)

The alpha milestone focuses on getting the **Kubernetes + Helm + CI/CD** pipeline
to full Detect → Observe → Facilitate → Act depth:

| Milestone | Focus | D→O→F→A |
|-----------|-------|---------|
| 0.1 | K8s manifest generation (baseline) | F |
| 0.2 | K8s wizard (services → manifests → Skaffold) | F |
| 0.3 | Skaffold detection + generation (complete) | D + F |
| **0.4** | **Helm detection + generation + wizard integration** | **D + F** |
| **0.5** | **CI/CD detection + generation + wizard integration** | **D + F** |
| 0.6 | Docker observability | O |
| 0.7 | K8s observability (cluster integration) | O |
| 0.8 | End-to-end: wizard → deploy → observe | Full pipeline |

---

## 6. Architecture Constraints

1. **Thin interfaces, thick core** — no business logic in CLI/Web/TUI
2. **Three-Layer Touch Rule** — a feature touches at most 2 layers
3. **Dependency direction** — Interfaces → Core → Adapters (never reverse)
4. **Pluggable integrations** — new tools via adapter protocol
5. **Security by default** — encrypted at rest, auto-lock, masked secrets
6. **No silent assumptions** — ambiguity must be stated explicitly
7. **Traceability** — goal → requirement → change → test → evidence
