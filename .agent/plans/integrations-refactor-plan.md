# 🧠 Integrations Refactor — Intelligent Setup System

> **Date**: 2026-02-13
> **Status**: PLAN — Discussion & review before implementation
> **Scope**: ALL integrations — Intelligent setup wizards, reactive cards, full user journey
> **Core principle**: Integrated intelligence — the tool knows your project and adapts

---

## 1. THE VISION

This tool is a **DevOps Control Plane**. Its purpose is integrated intelligence.

When a user opens a setup wizard, the tool should already know:
- What language/framework the project uses (Python 3.12 + Flask, Node 20 + Express, etc.)
- What modules exist and what stacks they use
- What integrations are already configured
- What the smart default configuration should be

**The wizard doesn't ask dumb questions. It presents smart answers and lets the user adjust.**

When the user adds a new integration, ALL other integrations **react**:
- Add Docker → CI/CD offers "Build & push image" step
- Add K8s → CI/CD offers "Deploy to cluster" step, Terraform offers "Provision K8s cluster"
- Add Terraform → K8s knows the cluster is IaC-managed
- Remove Docker → CI/CD removes the Docker build step

**The integrations are alive. They evolve with the project.**

---

## 2. THE INTELLIGENCE LAYER (what already exists)

The backend already has the intelligence. The problem is the frontend ignores it.

### Detection System
- `detect_modules()` → finds modules, matches stacks, detects versions & languages
- `match_stack()` → checks directories against stack detection rules (files_any_of, files_all_of, content_contains)
- `detect_version()` → reads pyproject.toml, package.json, go.mod, Cargo.toml, etc.
- `detect_language()` → maps stack names to languages (python-flask → python, node → javascript)

### Smart Generators
- `generate_dockerfile(stack_name)` → **stack-aware** multi-stage Dockerfile with best practices (non-root user, dependency caching, health checks). Templates for: Python, Node, TypeScript, Go, Rust, Java-Maven, Java-Gradle, .NET, Elixir, Ruby
- `generate_compose(modules)` → **module-aware** compose file — one service per module, correct ports per stack, proper build contexts
- `generate_dockerignore(stack_names)` → **stack-aware** ignore patterns
- `generate_ci(stack_names)` → **stack-aware** GitHub Actions with per-language jobs (Python: ruff + mypy + pytest, Node: npm ci + lint + test, Go: vet + lint + test, Rust: clippy + test, etc.)
- `generate_lint(stack_names)` → **stack-aware** lint-only workflow
- Stack-to-port mapping: Python=8000, Node/Ruby=3000, Go/Rust/Java/.NET=8080, Elixir=4000

### Status Probes
- `_probe_git()` → initialized, remote, branch, .gitignore
- `_probe_github()` → gh CLI, auth, repo, environments
- `_probe_docker()` → CLI, daemon, Dockerfile, Compose, .dockerignore
- `_probe_cicd()` → provider, workflow count
- `_probe_k8s()` → kubectl, cluster, manifests, Helm, Skaffold, Kustomize
- `_probe_terraform()` → CLI, .tf files, initialized, state
- `_probe_pages()` → segments, builders
- `_probe_dns()` → domain, records, SSL

**ALL of this exists and works. The wizards just need to USE it.**

---

## 3. THE FULL SCENARIO — 0 TO HERO

This is what the user experiences from start to finish.

### 3.1 First Launch — New Project

```
User runs: ./manage.sh web
→ No project.yml found
→ Auto-redirect to Wizard tab
→ "👋 Welcome! Let's set up your project."

Wizard Step 1: Project name, description
Wizard Step 2: Modules — add paths, auto-detect stacks
  → Tool scans directories, matches against stack rules
  → "We found a Python 3.12 Flask app in ./src and a React frontend in ./web"
Wizard Step 3: Environment configuration, secrets
Wizard Step 4: Content setup
Wizard Step 5: Integrations (THE KEY STEP — see section 4)
Wizard Step 6: Review & save → project.yml generated
```

### 3.2 First Launch — Existing Project

```
User runs: ./manage.sh web on a project that already has Docker, K8s, Git, etc.
→ project.yml exists (or is auto-generated from detection)
→ Dashboard loads with all integrations auto-detected
→ Integration cards show real status from detection
→ Setup progress shows: "6/8 configured — Missing: Terraform, DNS"
→ Cards that need attention show smart CTAs:
  "We detected K8s manifests but no cluster connection. Connect a cluster →"
  "You have Docker + K8s but no CI/CD pipeline. Generate one →"
```

### 3.3 The Integration Chain (Wizard Step 5 or standalone)

The user goes through integrations in this order (or any order — the system adapts):

```
1. GIT SETUP
   → Tool detects: .git exists? remote? branch? .gitignore?
   → Smart action: "Your project uses Python + Node. Here's a .gitignore for both."
   → Result: Git initialized, remote configured, .gitignore generated
   → CTA: "Next: Connect GitHub →"

2. GITHUB SETUP
   → Tool detects: gh CLI? auth status? remote URL → repo name?
   → Smart action: "Repo 'user/my-app' detected. Create environments?"
   → Offers: Create dev/staging/prod environments, push vault secrets to GH
   → Result: GitHub connected, environments created
   → CTA: "Next: Containerize with Docker →"

3. DOCKER SETUP
   → Tool reads: detected modules (Python Flask + React)
   → Smart generation:
     "We detected 2 modules:
      • src/ — Python 3.12 Flask (→ multi-stage Dockerfile, port 8000)
      • web/ — Node 20 React (→ multi-stage Dockerfile, port 3000)
      Here's a docker-compose.yml with both services, proper networking,
      and .dockerignore for Python + Node stacks."
   → User reviews generated files, adjusts if needed
   → Offers: Build now? Start services?
   → Result: Dockerfile(s), docker-compose.yml, .dockerignore written
   → CTA: "Next: Set up CI/CD →"

4. CI/CD SETUP
   → Tool reads: detected stacks + Docker config + GitHub status
   → Smart generation:
     "Based on your project, here's a GitHub Actions workflow:
      Jobs:
      ✅ test-python — ruff lint, mypy type-check, pytest (Python 3.12)
      ✅ test-node — npm ci, eslint, vitest (Node 20)
      ✅ build-docker — Build & push images to GHCR
      Triggers: push to main, pull requests"
   → User can toggle steps on/off, adjust triggers
   → REACTIVE: If Docker is configured → includes Docker build/push job
   → REACTIVE: If K8s is later configured → offers "Add K8s deploy step"
   → Result: .github/workflows/ci.yml written
   → CTA: "Next: Deploy to Kubernetes →" or "Next: Set up Terraform →"

5. KUBERNETES SETUP
   → Tool reads: Docker images, detected modules, cluster status
   → Smart generation:
     "Based on your Docker setup:
      Image: ghcr.io/user/my-app:latest (from CI/CD push)
      Generating:
      • deployment.yml — 2 replicas, port 8000, resource limits
      • service.yml — ClusterIP, port 8000
      • ingress.yml — host: my-app.example.com
      • configmap.yml — from .env variables"
   → REACTIVE: Uses Docker image name from Docker setup
   → REACTIVE: Uses port from Docker setup
   → REACTIVE: If Terraform configures cluster → notes the cluster source
   → Offers: Apply to cluster? View pod status?
   → Result: k8s/ directory with all manifests
   → CTA: "Next: Infrastructure with Terraform →"

6. TERRAFORM SETUP
   → Tool reads: project context, K8s status, cloud preferences
   → Smart generation:
     "Infrastructure for your project:
      Provider: AWS (detected from existing config / user choice)
      Resources:
      • EKS cluster (for your K8s workloads)
      • ECR registry (for your Docker images)
      • RDS PostgreSQL (detected from compose dependencies)
      • S3 bucket (for Terraform state backend)"
   → REACTIVE: If K8s is configured → offers EKS/GKE/AKS cluster
   → REACTIVE: If Docker is configured → offers registry (ECR/GHCR)
   → REACTIVE: If compose has PostgreSQL → offers RDS/CloudSQL
   → Result: terraform/ directory with main.tf, variables.tf, outputs.tf
   → CTA: "Next: Set up DNS →"

7. PAGES SETUP
   → Tool reads: project docs, existing content
   → Smart: Detect README.md, docs/ folder, API specs
   → Offers: Create documentation site segment, configure builder
   → Result: Pages segment configured

8. DNS SETUP
   → Tool reads: Pages config, domain from project.yml
   → Smart: Generate DNS records for detected domain
   → Offers: DNS lookup, SSL check, record generation
   → Result: DNS records generated for reference
```

### 3.4 Re-entry — Reconfigure an Integration

```
User already has Docker configured.
Goes to Docker integration card → clicks "Reconfigure"
→ Wizard opens with CURRENT state pre-loaded
→ Shows existing Dockerfile, Compose, .dockerignore
→ "Your project has changed: new module 'api-gateway' detected. Add to compose?"
→ REACTIVE: "K8s manifests reference image 'my-app:latest'.
   Want to update K8s deployment to match the new compose services?"
→ User adjusts, applies
→ Downstream integrations are notified of changes
```

### 3.5 Adding a New Integration After Initial Setup

```
User has: Git + GitHub + Docker + CI/CD
Now wants to add Kubernetes.

Option A: From Dashboard progress widget → "Set up Kubernetes →"
Option B: From Integrations tab → K8s card → "Set up →"
Option C: From Wizard → Step 5 → K8s → "Set up →"

All three open the SAME K8s setup wizard.
The wizard KNOWS about existing Docker config and CI/CD workflow.
→ "We'll use your Docker image ghcr.io/user/my-app:latest"
→ "After setup, we can add a K8s deploy step to your CI/CD pipeline"
→ After K8s setup completes:
   → CI/CD wizard re-opens: "Add K8s deployment step to your pipeline?"
   → User confirms → CI workflow updated with kubectl apply step
```

---

## 4. CROSS-INTEGRATION AWARENESS MAP

This is the core of the intelligence. Each integration knows about the others.

### What each integration READS from others:

| Integration | Reads From | What It Uses |
|---|---|---|
| **Git** | Project detection | Stack-aware .gitignore |
| **GitHub** | Git | Remote URL → repo name, branch |
| **GitHub** | Vault/Secrets | Secrets to push to GitHub environments |
| **Docker** | Module detection | Stack names → Dockerfile templates, ports → compose |
| **Docker** | Git | Project name for compose |
| **CI/CD** | Module detection | Stacks → per-language test/lint/typecheck jobs |
| **CI/CD** | Docker | Image name → build/push job, compose → test with services |
| **CI/CD** | K8s | Manifests → deploy step (kubectl apply) |
| **CI/CD** | Terraform | TF configs → plan/apply step |
| **CI/CD** | GitHub | Repo → trigger config, environments → deploy targets |
| **K8s** | Docker | Image name, port, compose services |
| **K8s** | CI/CD | Registry push target → image in deployment |
| **K8s** | Terraform | Cluster provisioning source |
| **Terraform** | Docker | Need registry → offer ECR/GHCR config |
| **Terraform** | K8s | Need cluster → offer EKS/GKE/AKS |
| **Terraform** | Docker compose | Dependencies (postgres, redis) → offer managed services |
| **Pages** | Git | Repo for deploy target |
| **Pages** | CI/CD | Workflow for auto-deploy on push |
| **DNS** | Pages | Domain for DNS records |
| **DNS** | K8s | Ingress host → DNS records |

### What each integration OFFERS to others when it's configured:

| When This Is Added | These Integrations React |
|---|---|
| **Git initialized** | GitHub: "Connect remote?", CI/CD: "Git triggers available" |
| **GitHub connected** | CI/CD: "GitHub Actions available", Pages: "Deploy to GH Pages?" |
| **Docker configured** | CI/CD: "Add Docker build/push step?", K8s: "Use this image for deployment" |
| **CI/CD configured** | K8s: "CI can deploy to cluster", Terraform: "CI can run tf plan/apply" |
| **K8s configured** | CI/CD: "Add kubectl deploy step?", Terraform: "Provision this cluster with IaC?" |
| **Terraform configured** | K8s: "Cluster managed by Terraform", CI/CD: "Add TF plan/apply step?" |
| **Pages configured** | CI/CD: "Add docs deploy step?", DNS: "Configure domain for Pages?" |
| **DNS configured** | K8s: "Update Ingress with domain", Pages: "Custom domain ready" |

---

## 5. PER-INTEGRATION WIZARD SPEC

### 5.1 Git Setup Wizard

**Intelligence sources**: Project detection (stacks), filesystem scan

**Step 1: Detection — "What we found"**
```
🔀 Git Repository Status

├─ Git CLI:        ✅ Installed (v2.43)
├─ Repository:     ✅ Initialized (branch: main)
├─ Remote:         ⚠️ No remote configured
├─ .gitignore:     ❌ Not found
└─ Hooks:          ❌ No hooks configured

💡 Your project uses Python + Node stacks.
   We'll generate a .gitignore with patterns for both.
```

**Step 2: Configure — smart defaults**
- Remote URL field (pre-filled from `gh repo view` if gh CLI available)
- .gitignore: auto-generated from detected stacks (Python patterns + Node patterns + common patterns)
  - Shows preview of generated .gitignore
  - User can add/remove patterns
- Branch: default branch name (main)
- Hooks: offer pre-commit hook if ruff/mypy/eslint detected

**Step 3: Apply & verify**
- Execute: git init (if needed), remote add, write .gitignore, set up hooks
- Re-detect: verify git status is clean
- Show result: "✅ Git configured — branch: main, remote: origin → github.com/user/repo"
- CTA: "Next: Connect GitHub →" (if gh CLI detected)

**Features** (12):
1. Git CLI detection + version display
2. Repository status (initialized, branch, dirty state)  
3. Remote detection + configuration
4. Stack-aware .gitignore generation with preview
5. .gitignore pattern editor (add/remove)
6. Default branch configuration
7. Pre-commit hook setup (if lint tools detected)
8. Initial commit creation
9. Git remote add/change
10. Verification after apply
11. Next-integration CTA
12. Re-entry with current state pre-loaded

---

### 5.2 GitHub Setup Wizard

**Intelligence sources**: Git (remote URL), Vault (secrets), gh CLI status

**Step 1: Detection — "What we found"**
```
🐙 GitHub Status

├─ gh CLI:         ✅ Installed (v2.45)
├─ Auth:           ✅ Logged in as 'username'
├─ Repository:     ✅ user/my-app (private)
├─ Environments:   ❌ None configured
├─ Secrets:        ❌ 0 repository secrets
└─ CODEOWNERS:     ❌ Not found

💡 We detected secrets in your vault that could be pushed to GitHub.
```

**Step 2: Configure**
- Repository: confirm or link (pre-filled from git remote)
- Environments: 
  - Select environments to create: ☑ dev, ☑ staging, ☑ production
  - Per-environment protection rules
- Secrets from vault:
  - List vault secrets → checkboxes to push to GitHub
  - Map vault key → GitHub secret name
- CODEOWNERS: generate from project structure
- Branch protection rules suggestion

**Step 3: Apply**
- Create environments via `gh api`
- Push selected secrets
- Write CODEOWNERS if selected
- CTA: "Next: Containerize with Docker →" or "Next: Set up CI/CD →"

**Features** (15):
1. gh CLI detection + version + auth status
2. Repository detection from git remote
3. Repository visibility (public/private)
4. Environment listing + creation (dev/staging/prod)
5. Environment protection rules configuration
6. Vault secret listing
7. Secret push to GitHub (vault → GitHub secrets)
8. Secret name mapping
9. CODEOWNERS generation from project structure
10. Branch protection rules suggestion
11. Webhook status check
12. GitHub Apps detection
13. Verification after apply
14. Next-integration CTA
15. Re-entry with current state

---

### 5.3 Docker Setup Wizard

**Intelligence sources**: Module detection (stacks, paths, versions), generator templates

**Step 1: Detection — "What we found"**
```
🐳 Docker Status

├─ Docker CLI:     ✅ Installed (v24.0)
├─ Daemon:         ✅ Running
├─ Dockerfile:     ❌ Not found
├─ Compose:        ❌ Not found
├─ .dockerignore:  ❌ Not found
└─ Images:         3 local images

📦 Detected modules:
   • src/ — Python 3.12 Flask (stack: python-flask)
   • web/ — Node 20 React (stack: node)

💡 We'll generate stack-optimized Dockerfiles with multi-stage builds,
   dependency caching, and non-root users.
```

**Step 2: Configure — smart generation**

Sub-step 2a: **Dockerfiles** (per module)
```
📋 Generated Dockerfiles

┌─ src/ (Python 3.12 Flask) ──────────────────────┐
│ # ── Build stage ─────────────────────────────── │
│ FROM python:3.12-slim AS builder                 │
│ WORKDIR /app                                     │
│ COPY pyproject.toml setup.cfg ./                 │
│ RUN pip install --no-cache-dir ...               │
│ COPY . .                                         │
│ RUN pip install -e .                             │
│                                                  │
│ # ── Runtime stage ───────────────────────────── │
│ FROM python:3.12-slim                            │
│ ...non-root user, health check, EXPOSE 8000...   │
└─────────────────────────────────── [Edit] [✓] ──┘

┌─ web/ (Node 20 React) ──────────────────────────┐
│ FROM node:20-alpine AS builder                   │
│ ...npm ci, npm run build...                      │
│ FROM nginx:alpine                                │
│ COPY --from=builder /app/dist /usr/share/nginx/  │
└─────────────────────────────────── [Edit] [✓] ──┘
```

Sub-step 2b: **docker-compose.yml** (from modules)
```
📋 Generated docker-compose.yml

services:
  api:
    build: ./src
    ports: "8000:8000"
    environment:
      - DATABASE_URL=postgresql://...
    depends_on: [db]
    restart: unless-stopped

  web:
    build: ./web
    ports: "3000:3000"
    depends_on: [api]

  db:
    image: postgres:16-alpine    ← detected from project dependencies
    volumes: [pgdata:/var/lib/postgresql/data]
    environment:
      - POSTGRES_DB=myapp

[+ Add service]  [Edit YAML]
```

Sub-step 2c: **.dockerignore** (auto-generated, reviewable)
```
# Python
__pycache__/
*.pyc
.venv/
# Node
node_modules/
dist/
# Common
.git/
.env
*.md
```

**Step 3: Apply & test**
- Write all files
- Offer: "Build images now?" → `docker compose build`
- Offer: "Start services?" → `docker compose up -d`
- Show running containers with health status
- CTA: "Next: Set up CI/CD pipeline →"

**Features** (25):
1. Docker CLI + daemon detection
2. Existing Dockerfile/Compose/dockerignore detection
3. Module-aware automatic Dockerfile generation (one per module)
4. Stack-specific multi-stage Dockerfile templates (10 stacks)
5. Generated Dockerfile preview with syntax highlighting
6. Per-Dockerfile edit capability
7. Module-aware docker-compose.yml generation
8. Automatic service dependency detection (PostgreSQL, Redis from project deps)
9. Per-stack default port assignment
10. Compose service editor (add/remove/modify services)
11. YAML preview with syntax highlighting
12. Stack-aware .dockerignore generation
13. .dockerignore pattern editor
14. Build action (docker compose build)
15. Start action (docker compose up -d)
16. Running container status display
17. Image list after build
18. Health check verification
19. Next-integration CTA (CI/CD)
20. Re-entry with existing config pre-loaded
21. Partial state: "You have a Dockerfile but no Compose. Add?"
22. Overwrite confirmation for existing files
23. Multi-module compose with proper networking
24. Volume configuration for databases
25. Environment variable injection from detected .env

---

### 5.4 CI/CD Setup Wizard

**Intelligence sources**: Module detection, Docker config, GitHub config, K8s config, Terraform config

**This is the most reactive wizard — it adapts to everything else.**

**Step 1: Detection — "What we found"**
```
⚡ CI/CD Status

├─ Provider:       GitHub Actions (detected from .github/)
├─ Workflows:      ❌ No workflows found
├─ GitHub:         ✅ Connected (user/my-app)
├─ Docker:         ✅ Configured (2 services)
├─ Kubernetes:     ❌ Not configured
├─ Terraform:      ❌ Not configured
└─ Test framework: ✅ pytest (Python), vitest (Node)

📦 Detected stacks: python-flask, node (React)

💡 We'll generate a CI pipeline with:
   • Per-stack test/lint jobs
   • Docker image build & push
   • Auto-triggered on push to main + PRs
```

**Step 2: Configure — reactive pipeline builder**
```
📋 CI/CD Pipeline Configuration

Trigger:
  ☑ Push to main/master
  ☑ Pull requests
  ☐ Manual dispatch
  ☐ Schedule (cron)

Jobs:
  ✅ test-python
     ├─ Python 3.12
     ├─ Install dependencies (pip install -e .[test])
     ├─ Lint (ruff check .)
     ├─ Type check (mypy src/)
     └─ Test (pytest --cov)

  ✅ test-node
     ├─ Node 20
     ├─ Install (npm ci)
     ├─ Lint (eslint)
     └─ Test (vitest --coverage)

  ✅ build-docker                    ← BECAUSE Docker is configured
     ├─ Build: ghcr.io/user/my-app
     ├─ Push to GHCR
     └─ Tag: commit SHA + latest

  ❌ deploy-k8s                      ← GREYED OUT because K8s not configured
     "Set up Kubernetes first →"

  ❌ terraform-plan                   ← GREYED OUT because TF not configured
     "Set up Terraform first →"

[Preview YAML]
```

**When K8s is later added**, the wizard re-opens or the card offers:
```
🔔 Kubernetes is now configured!
   Add deploy-to-k8s step to your CI pipeline?
   
   deploy-k8s:
     needs: [build-docker]
     steps:
       - kubectl apply -f k8s/
       - kubectl rollout status deployment/my-app
   
   [Add to pipeline]  [Skip]
```

**Step 3: Apply**
- Write .github/workflows/ci.yml
- Show generated YAML with highlighting
- Offer: Commit & push? → triggers first CI run
- Offer: Dispatch workflow now?
- Show workflow run status if triggered
- CTA: "Next: Deploy to Kubernetes →" or "Next: Infrastructure with Terraform →"

**Features** (30):
1. CI provider detection (GitHub Actions, GitLab CI)
2. Existing workflow detection + analysis
3. Stack-aware job generation (Python, Node, Go, Rust, Java, .NET, Elixir, Ruby)
4. Per-stack lint step (ruff, eslint, golangci-lint, clippy)
5. Per-stack type-check step (mypy, tsc)
6. Per-stack test step (pytest, vitest, go test, cargo test)
7. Docker build/push job (reactive — only if Docker configured)
8. Docker image name from Docker config or GitHub repo
9. Registry push target (GHCR, ECR, Docker Hub)
10. K8s deploy job (reactive — only if K8s configured)
11. Terraform plan/apply job (reactive — only if TF configured)
12. Pages deploy job (reactive — only if Pages configured)
13. Trigger configuration (push, PR, dispatch, schedule)
14. Branch filter configuration
15. Matrix testing (multiple Python/Node versions)
16. Dependency caching per-language
17. YAML preview with syntax highlighting
18. Job toggle on/off
19. Job dependency chain visualization
20. Environment selection for deploy jobs
21. Secret reference from GitHub secrets
22. Commit & push after generation
23. Workflow dispatch trigger
24. Run status monitoring
25. Add step to EXISTING workflow (not just generate new)
26. Greyed-out future steps with "Set up X first →" links
27. Re-entry: show existing workflow, offer modifications
28. Lint-only workflow generation (separate)
29. Deploy-only workflow generation (separate)
30. Workflow file naming (ci.yml, lint.yml, deploy.yml)

---

### 5.5 Kubernetes Setup Wizard

**Intelligence sources**: Docker config, CI/CD config, Terraform config, cluster status

**Step 1: Detection — "What we found"**
```
☸️ Kubernetes Status

├─ kubectl:        ✅ Installed (v1.29)
├─ Cluster:        ✅ Connected (minikube / EKS / GKE)
├─ Helm:           ✅ Installed (v3.14)
├─ Manifests:      ❌ No k8s/ directory
├─ Skaffold:       ❌ Not found
└─ Kustomize:      ❌ Not found

🐳 Docker context:
   • Image: ghcr.io/user/my-app:latest (from CI/CD push target)
   • Services: api (port 8000), web (port 3000), db (postgres:16)

💡 We'll generate K8s manifests that match your Docker setup:
   • Deployment for each service
   • Services with correct ports
   • Ingress for external access
   • ConfigMap from your .env
```

**Step 2: Configure — Docker-aware manifest generation**
```
📋 Kubernetes Manifest Configuration

Application: my-app
Namespace: default  [v]

Resources to generate:
  ✅ Deployment — api
     ├─ Image: ghcr.io/user/my-app-api:latest     ← from Docker/CI
     ├─ Port: 8000                                  ← from Docker
     ├─ Replicas: 2
     ├─ CPU: 100m-500m, Memory: 128Mi-512Mi
     ├─ Health check: GET /health :8000
     └─ Env from: configmap/my-app-config

  ✅ Deployment — web
     ├─ Image: ghcr.io/user/my-app-web:latest
     ├─ Port: 3000
     └─ Replicas: 2, behind Ingress

  ☐ StatefulSet — db (PostgreSQL)
     "Use managed database instead? Set up Terraform →"

  ✅ Service — api (ClusterIP:8000)
  ✅ Service — web (ClusterIP:3000)
  ✅ Ingress — my-app.example.com → web:3000, api.my-app.example.com → api:8000
  ✅ ConfigMap — from .env file
  ☐ HorizontalPodAutoscaler
  ☐ NetworkPolicy

[Preview manifests]
```

**Step 3: Apply & verify**
- Write k8s/ directory with all manifests
- Offer: Apply to cluster? → `kubectl apply -f k8s/`
- Show deployment rollout status
- Show pod status (running, ready, restarts)
- Show service endpoints
- CTA: "Add K8s deploy step to CI/CD?" (reactive → opens CI/CD wizard)
- CTA: "Manage cluster infrastructure with Terraform →"

**Features** (30):
1. kubectl + Helm + Skaffold + Kustomize detection
2. Cluster connection status + context info
3. Docker-aware image names in deployments
4. Docker-aware ports in services
5. Per-Docker-service manifest generation
6. Deployment with configurable replicas, resources, health checks
7. Service type selection (ClusterIP/NodePort/LoadBalancer)
8. Ingress generation with host routing
9. ConfigMap from .env file
10. Secret generation from vault
11. HorizontalPodAutoscaler generation
12. NetworkPolicy generation
13. Namespace creation
14. Multi-environment namespace mapping (dev/staging/prod)
15. Manifest preview per-resource with YAML highlighting
16. Manifest editor
17. Apply to cluster action
18. Rollout status monitoring
19. Pod status display
20. Helm chart scaffolding wizard
21. Helm values.yaml editor
22. Helm install/upgrade action
23. Kustomize setup wizard
24. Skaffold config generation
25. Database StatefulSet vs managed service suggestion (→ Terraform)
26. CI/CD deploy step injection (reactive)
27. Re-entry with existing manifests loaded
28. Partial state: "You have Deployment but no Service. Add?"
29. Resource validation before apply (kubectl dry-run)
30. Manifest diff (before vs after apply)

---

### 5.6 Terraform Setup Wizard

**Intelligence sources**: K8s config, Docker config, compose dependencies, cloud context

**Step 1: Detection — "What we found"**
```
🏗️ Terraform Status

├─ terraform CLI:   ✅ Installed (v1.7)
├─ .tf files:       ❌ None found
├─ Initialized:     ❌ No .terraform/
└─ State:           ❌ No state file

☸️ Kubernetes context:
   • Cluster: minikube (local)
   • Manifests: 6 resources in k8s/

🐳 Docker context:
   • Compose dependencies: postgres:16, redis:7

💡 Infrastructure suggestions based on your project:
   • K8s cluster (EKS/GKE/AKS) for your Kubernetes workloads
   • Container registry (ECR/GHCR) for your Docker images
   • Managed PostgreSQL (RDS/CloudSQL) for your database
   • S3/GCS for Terraform state backend
```

**Step 2: Configure — context-aware IaC generation**
```
📋 Terraform Configuration

Cloud provider: [AWS ▾]  (or GCP, Azure, DigitalOcean)
Region: [us-east-1 ▾]

State backend:
  ○ Local (default)
  ● S3 (recommended for team projects)
    Bucket: my-app-terraform-state
    Key: terraform.tfstate

Resources to generate:
  ✅ VPC + subnets                       ← networking foundation
  ✅ EKS cluster                         ← BECAUSE K8s is configured
     ├─ Node group: 2x t3.medium
     └─ K8s version: 1.29
  ✅ ECR repository                      ← BECAUSE Docker is configured
     └─ Image: my-app
  ✅ RDS PostgreSQL                      ← BECAUSE compose has postgres
     ├─ Instance: db.t3.micro
     └─ Database: myapp
  ☐ ElastiCache Redis                   ← BECAUSE compose has redis
  ☐ S3 bucket (app storage)
  ☐ CloudFront CDN                      ← BECAUSE Pages is configured
  ☐ Route53 DNS                         ← links to DNS setup

Variables:
  project_name = "my-app"
  environment = "production"
  region = "us-east-1"

[Preview .tf files]
```

**Step 3: Apply & verify**
- Write terraform/ directory with: main.tf, variables.tf, outputs.tf, backend.tf
- Run: `terraform init`
- Run: `terraform validate`
- Show validation result
- Offer: `terraform plan` → show planned changes
- CTA: "Add TF plan step to CI/CD?" (reactive)

**Features** (25):
1. Terraform CLI detection + version
2. Existing .tf file detection + analysis
3. State/initialization detection
4. Cloud provider selection (AWS/GCP/Azure/DO)
5. Region selection
6. State backend configuration (local, S3, GCS, Azure)
7. K8s-reactive: EKS/GKE/AKS cluster generation
8. Docker-reactive: ECR/GHCR/ACR registry generation
9. Compose-reactive: managed database from compose deps
10. Compose-reactive: managed cache from compose deps
11. Pages-reactive: CDN configuration
12. DNS-reactive: Route53/Cloud DNS configuration
13. VPC/network generation
14. Variable definition file
15. Output definition file
16. Provider version pinning
17. .tf file preview with HCL highlighting
18. terraform init action
19. terraform validate action
20. terraform plan action with diff view
21. terraform apply action (with confirmation)
22. Workspace management
23. CI/CD plan step injection (reactive)
24. Re-entry with existing config loaded
25. Module detection (existing TF modules)

---

### 5.7 Pages Setup Wizard

**Intelligence sources**: Project docs, Git config, CI/CD config

**Features** (10):
1. Existing content detection (docs/, README, API specs)
2. Segment creation wizard
3. Builder selection per segment (Docusaurus, etc.)
4. Custom domain configuration
5. Build action
6. Deploy action (GitHub Pages, custom)
7. CI/CD deploy step injection (reactive)
8. Preview capability
9. Git-reactive: deploy from repo
10. DNS-reactive: custom domain ready

---

### 5.8 DNS Setup Wizard

**Intelligence sources**: Pages config, K8s Ingress, domain configuration

**Features** (10):
1. Domain detection from project config
2. DNS lookup for current records
3. SSL certificate check
4. Record generation for detected services
5. K8s-reactive: Ingress host → A/CNAME records
6. Pages-reactive: custom domain → CNAME record
7. Mail provider configuration (MX records)
8. SPF/DMARC generation
9. Propagation check
10. Re-entry with current DNS state

---

## 6. INTEGRATION CARD SPEC (post-setup, operational view)

After setup, each card becomes an **operational view** of that integration.

### Card Behavior Rules:

1. **Not configured** → Card shows setup banner: "Docker is not configured. [Set up →]" — opens setup wizard
2. **Dependency missing** → Card shows dependency hint: "💡 Set up Docker first to containerize your app" — links to Docker wizard
3. **Configured** → Card shows live status, actions, live panels
4. **Outdated** → Card detects changes: "Your project has new modules. [Update configuration →]" — re-opens setup wizard with changes highlighted

### Per-Card Features (summary):

| Card | Status View | Actions | Live Panels | Reactive Updates |
|---|---|---|---|---|
| **Git** | Branch, dirty, ahead/behind, remote | Commit, Pull, Push, Stash | Recent commits, Diff | — |
| **GitHub** | Auth, repo, PRs, Issues | Create PR, Create Issue, Dispatch | Open PRs, Runs, Issues | — |
| **Docker** | Engine, containers, images | Build, Up, Down, Restart, Prune, Logs | Containers, Images, Networks, Volumes, Stats | New module → "Add to compose?" |
| **CI/CD** | Provider, workflows, last run | Edit workflow, Trigger, Re-run | Workflows, Runs, Coverage | New integration → "Add step?" |
| **K8s** | Cluster, pods, services | Apply, Scale, Rollback, Logs, Exec | Pods, Deployments, Services, Events, Helm | Docker change → "Update image?" |
| **Terraform** | State, workspaces, outputs | Plan, Apply, Destroy, Format | State resources, Plan diff, Outputs | K8s change → "Update cluster?" |
| **Pages** | Segments, builders, deploy | Build, Deploy, Preview | Segments, Build status | — |
| **DNS** | Domain, records, SSL | Lookup, SSL check | Record list, Certificate info | Ingress change → "Update DNS?" |

---

## 7. FEATURE COUNT

| Integration | Setup Wizard | Card Operations | Reactive Cross-Links | Total |
|---|---|---|---|---|
| Git | 12 | 10 | 2 | **24** |
| GitHub | 15 | 12 | 3 | **30** |
| Docker | 25 | 15 | 5 | **45** |
| CI/CD | 30 | 12 | 8 | **50** |
| Kubernetes | 30 | 18 | 6 | **54** |
| Terraform | 25 | 12 | 7 | **44** |
| Pages | 10 | 8 | 3 | **21** |
| DNS | 10 | 6 | 3 | **19** |
| **TOTAL** | **157** | **93** | **37** | **287** |

---

## 8. IMPLEMENTATION ORDER

**One integration at a time. Complete before moving to next.**

"Complete" means: setup wizard works end-to-end + card works + reactive awareness works

| # | Integration | Why this order |
|---|---|---|
| 1 | **Git** | Foundation — everything depends on Git |
| 2 | **GitHub** | Needs Git. Enables CI/CD triggers |
| 3 | **Docker** | Core containerization. Feeds CI/CD + K8s |
| 4 | **CI/CD** | The most reactive wizard. Needs Docker + GitHub context |
| 5 | **Kubernetes** | Needs Docker images. Core deployment target |
| 6 | **Terraform** | Needs K8s + Docker context for smart infrastructure |
| 7 | **Pages** | Lower priority, simpler |
| 8 | **DNS** | Last — needs everything else for context |

### Per-integration: what we touch

For EACH integration, the work is:

1. **Setup Wizard** — rewrite `openXxxSetupWizard()` in `_integrations_setup_modals.html`
   - Detection step: call status APIs, read project context
   - Configure step: call generators, show smart defaults, preview
   - Apply step: write files, verify, offer next
2. **Integration Card** — rewrite `_integrations_xxx.html`
   - Status grid from detection
   - Setup banner / dependency hints
   - Action toolbar (contextual)
   - Live panels (on-demand)
   - Reactive update banners
3. **Wizard Step 5** — update `_wizard_integrations.html` to show status + launch wizard modals
4. **Backend** — add or modify endpoints IF the intelligence requires it (as discovered)

### Foundation work (before integration 1):

- [ ] Clean up wizard Step 5: replace inline sub-forms with clean status + "Set up →" buttons
- [ ] Standardize CSS for wizard modals (spacing, fonts, sections, preview panels)
- [ ] Ensure `wizardModalOpen()` framework supports the intelligence pattern (passing context data between steps)
- [ ] Create helper: `getProjectContext()` — single call that returns modules, stacks, tool detection, integration statuses — the intelligence payload every wizard needs

---

## 9. DESIGN DECISIONS (LOCKED IN)

These are confirmed. Not open for re-discussion.

### 1. Visual design → EVOLVE
Nothing is fixed. The wizard modal system will evolve as we build. Each integration may need different UI patterns — the design adapts to the content, not the other way around.

### 2. Reactivity timing → BOTH
- **Immediately** after setup completes → prompt: "K8s is now configured. Add deploy step to CI/CD?"
- **Persistently** on card load → banner: "K8s detected. Add deploy step?" (until user acts or dismisses)

### 3. Re-entry behavior → QUICK RECONFIGURE + FULL WIZARD
- Default: quick reconfigure mode (current state loaded, change what you need)
- Option to run full wizard again if user wants to start over

### 4. Compose service detection → YES, DETECT EVERYTHING
- Detect databases from project dependencies (SQLAlchemy/psycopg → postgres, prisma → postgres/mysql)
- Detect caches (redis, memcached from requirements/package.json)
- Detect message queues (RabbitMQ, Kafka)
- **Offer them** — user toggles what to include

### 5. Terraform provider → DETECT + USER DECIDES
- Detect from existing environment (AWS credentials, gcloud config, az config)
- Detect from existing .tf files
- If nothing detected → walk the user through setup, configure together
- **User always decides** — detection is a suggestion, not a decision

### 6. CI/CD step injection → USER DECIDES
- Show ALL options: modify existing workflow, generate separate file, or skip
- Show diff/preview before any change
- **User approves every change** — nothing is automatic

### CORE PRINCIPLE: THE USER IS GOD
Every wizard detects, suggests, and previews. The USER confirms, adjusts, and applies. Nothing happens without explicit user action. The tool serves the user, not the other way around.
