# Technology Spec — Solution Control Plane

> **Source of truth** for what technologies this platform supports and what
> each technology requires across the four phases: **Detect → Observe → Facilitate → Act**.
>
> Derived from: `STACKS.md`, `DESIGN.md §7.1`, `ARCHITECTURE.md`, `stacks/*/stack.yml`

---

## The Pattern (DESIGN.md §6)

Every integration follows the same four-phase lifecycle:

| Phase | What it does | Example (Kubernetes) |
|-------|-------------|---------------------|
| **Detect** | Is it in the project? What version? What configuration? | Find manifests, Helm charts, kustomize overlays |
| **Observe** | What's its current state? What's healthy, what's broken? | Deployments, pods, services, health |
| **Facilitate** | Can we generate configs? Suggest improvements? Fill gaps? | Generate manifests from services, suggest resource limits |
| **Act** | Provide the tools to operate it: build, deploy, manage, fix | Apply, rollback, scale, port-forward, view logs |

---

## 1. Service Stacks — Languages (12)

### 1.1 Python
- **Detection:** `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements.txt`, `Pipfile`
- **Capabilities:** install, lint (ruff), format (ruff), test (pytest), types (mypy)
- **Version source:** `pyproject.toml` → `version = "x.y.z"`

### 1.2 Node (JavaScript)
- **Detection:** `package.json`
- **Capabilities:** install (npm), lint (eslint), format (prettier), test (jest/vitest), build
- **Version source:** `package.json` → `"version": "x.y.z"`

### 1.3 TypeScript
- **Detection:** `tsconfig.json` + `package.json` (both required)
- **Capabilities:** install, lint, format, test, build, compile, types (tsc)

### 1.4 Go
- **Detection:** `go.mod`
- **Capabilities:** install, lint (golangci-lint), format (gofmt), test, build, vet
- **Version source:** `go.mod` → `go 1.22`

### 1.5 Rust
- **Detection:** `Cargo.toml`
- **Capabilities:** install, lint (clippy), format (rustfmt), test, build, check
- **Version source:** `Cargo.toml` → `version = "x.y.z"`

### 1.6 Ruby
- **Detection:** `Gemfile`, `Rakefile`
- **Capabilities:** install (bundle), lint (rubocop), format, test (rspec), console

### 1.7 Java (Maven)
- **Detection:** `pom.xml`
- **Capabilities:** install, lint, test, build, clean, verify

### 1.8 Java (Gradle)
- **Detection:** `build.gradle`, `build.gradle.kts`
- **Capabilities:** install, lint, test, build, clean

### 1.9 .NET (C#)
- **Detection:** `Directory.Build.props`, `global.json`, `nuget.config`
- **Capabilities:** install, lint, format, test, build, clean

### 1.10 Swift
- **Detection:** `Package.swift`
- **Capabilities:** install, build, test, clean, format, lint

### 1.11 Elixir
- **Detection:** `mix.exs`
- **Capabilities:** install, lint, format, test, build, types (dialyzer)
- **Version source:** `mix.exs` → `version: "x.y.z"`

### 1.12 Zig
- **Detection:** `build.zig`, `build.zig.zon`
- **Capabilities:** build, test, format, clean

---

## 2. Low-Level Stacks (2)

### 2.1 C
- **Detection:** `CMakeLists.txt`, `Makefile`, `configure.ac`, `meson.build`
- **Capabilities:** install (configure), build, test, clean, lint (cppcheck), format (clang-format)

### 2.2 C++
- **Detection:** `CMakeLists.txt` containing `CXX`
- **Capabilities:** install (cmake), build (parallel), test, clean, lint, format

---

## 3. Ops / Infrastructure Stacks (4)

### 3.1 Docker Compose
- **Detection:** `docker-compose.yml`, `compose.yml` (+ `.yaml` variants)
- **Capabilities:** up, down, build, logs, status
- **D→O→F→A requirements (DESIGN.md §7.1):**
  - **Detect:** Dockerfiles, compose configs, .dockerignore
  - **Observe:** Running containers, images, volumes, resource usage, logs
  - **Facilitate:** Generate Dockerfiles from detected stacks, compose files from modules, suggest multi-stage builds
  - **Act:** Build, push to registry, start/stop/restart, view logs, exec, prune

### 3.2 Kubernetes
- **Detection:** `kustomization.yaml`, `kustomization.yml`, `skaffold.yaml`
- **Capabilities:** lint (dry-run), apply, diff, status, build (kustomize), delete
- **D→O→F→A requirements (DESIGN.md §7.1):**
  - **Detect:** Manifests, helm charts, kustomize
  - **Observe:** Deployments, pods, services, ingresses, health
  - **Facilitate:** Generate manifests from Docker setup, helm charts, suggest resource limits
  - **Act:** Apply, rollback, scale, port-forward, view pod logs
- **Sub-tools:**
  - **Skaffold** — dev workflow orchestrator (detect configs, profiles, portForward, build/deploy strategy, tag policy)
  - **Kustomize** — overlay-based customization

### 3.3 Helm
- **Detection:** `Chart.yaml`
- **Capabilities:** install (dep update), lint, test (dry-run), build (package), status
- **Version source:** `Chart.yaml` → `version: x.y.z`
- **D→O→F→A requirements:**
  - **Detect:** Chart.yaml files (recursive, skip vendor dirs), parse name/version/description/appVersion/type, detect chart structure (values.yaml, templates/, charts/ subcharts, Chart.lock), detect env-specific values files (values-{env}.yaml)
  - **Observe:** Installed releases (helm list), release values (helm get values), release status
  - **Facilitate:** Generate Chart.yaml + values.yaml scaffolding from wizard state, suggest values files per environment, generate templates/ from service definitions
  - **Act:** Install (helm install), upgrade (helm upgrade --install), template (helm template), lint (helm lint), package (helm package), dependency update (helm dependency update)

### 3.4 Terraform
- **Detection:** `main.tf`, `terraform.tf`, `versions.tf`
- **Capabilities:** install (init), lint (validate), format, plan, apply, status
- **D→O→F→A requirements (DESIGN.md §7.1):**
  - **Detect:** AWS/GCP/Azure/Terraform configs
  - **Observe:** Deployed resources, costs, health
  - **Facilitate:** Generate infrastructure-as-code from needs
  - **Act:** Plan, apply, destroy

---

## 4. Docs / Frontend Stacks (2)

### 4.1 Static Site
- **Detection:** `index.html`
- **Capabilities:** lint (htmlhint), format (prettier), test (lighthouse), serve

### 4.2 Protobuf
- **Detection:** `buf.yaml`, `buf.gen.yaml`, `buf.work.yaml`
- **Capabilities:** lint, format, build (generate), test (breaking)

---

## 5. Platform Integrations (beyond stacks)

These are not "stacks" but first-class integrations in the control plane:

### 5.1 Git
- Status, commit, push, pull, branch management
- Full CLI + Web + TUI parity

### 5.2 GitHub
- Secrets, environments, pull requests, Actions workflows, Releases
- Two-way sync (secrets push/pull, environment management)

### 5.3 CI/CD
- **D→O→F→A requirements (DESIGN.md §7.1):**
  - **Detect:** Workflow files across providers (GitHub Actions, GitLab CI, Jenkins, CircleCI, Travis, Azure, Bitbucket)
  - **Observe:** Pipeline runs, test results, coverage, artifacts
  - **Facilitate:** Generate workflows from detected stacks, suggest test/deploy steps
  - **Act:** Trigger, cancel, re-run, download artifacts

### 5.4 Secrets / .env
- AES-256-GCM encrypted vault, environment-specific configs
- Key CRUD, GitHub Secrets sync, auto-lock, portable export

### 5.5 Content Vault
- Per-file encryption, binary envelope format
- Media optimization (image compression, video transcoding)
- GitHub Release uploads for large assets

### 5.6 Pages / SSG
- 6 builders: Docusaurus, MkDocs, Hugo, Sphinx, Raw, Custom
- Build, deploy, preview

### 5.7 Backups
- Create, restore, export, archive project state

---

## 6. Future Integrations (DESIGN.md §7.1)

These are defined in the design doc as the growth path:

| Integration | Detect | Observe | Facilitate | Act |
|-------------|--------|---------|------------|-----|
| Cloud Infrastructure | AWS/GCP/Azure configs | Resources, costs, health | Generate IaC | Plan, apply, destroy |
| Databases | Connection strings, ORMs, migrations | Connection health, schema | Generate migrations | Migrate, rollback, seed |
| Package Management | Dependency files | Outdated, vulns, licenses | Suggest updates | Install, update, audit |
| Monitoring | Prometheus/Grafana configs | Metrics, alerts, uptime | Generate dashboards | Configure, silence |
| Security | Exposed secrets, misconfigs | Security posture, compliance | Suggest fixes | Rotate, fix, update |
| Testing | Test frameworks, coverage | Results, trends, flaky tests | Generate templates | Run, report, track |
| DNS / CDN | Domain configs, CDN settings | Records, SSL status | Generate configs | Update, purge, renew |
| Documentation | Docs, README, API specs | Coverage, staleness, links | Generate from code | Build, deploy, validate |

---

## 7. Current State Matrix (DESIGN.md §7.3)

| Integration | Detect | Observe | Facilitate | Act |
|-------------|--------|---------|------------|-----|
| Git | ✅ | ✅ | — | ✅ |
| GitHub | ✅ | ✅ | — | ✅ |
| Secrets / .env | ✅ | ✅ | ✅ | ✅ |
| Content | ✅ | ✅ | ✅ | ✅ |
| Pages / SSG | ✅ | ✅ | ✅ | ✅ |
| Backups | ✅ | ✅ | — | ✅ |
| Docker | ✅ | — | — | — |
| **Kubernetes** | ✅ | partial | ✅ | partial |
| **Helm** | ✅ | — | — | partial |
| CI/CD | partial | partial | — | partial |
| Stacks (20) | ✅ | — | — | — |
