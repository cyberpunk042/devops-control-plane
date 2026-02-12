# Solution Control Plane — Future Development Analysis

> **Purpose:** Break down the path from current state to final product vision
> into analyzable, plannable work.

---

## 1. Current State Summary

**What exists today (Level 1 — complete):**

| Domain | Detect | Observe | Facilitate | Act | Lines |
|---|---|---|---|---|---|
| Secrets / Vault | ✅ | ✅ | ✅ templates, generate | ✅ encrypt/decrypt/sync | ~1,900 |
| Content | ✅ | ✅ browser, preview | ✅ optimize img+video | ✅ encrypt/decrypt/release | ~2,450 |
| Pages / SSG | ✅ | ✅ build status | ✅ 6 builders, schemas | ✅ build/deploy | ~2,950 |
| Git | ✅ | ✅ status, log | — | ✅ commit/push/pull | ~660 |
| GitHub | ✅ | ✅ PRs, Actions | — | ✅ secrets sync, dispatch | ~1,050 |
| Backups | ✅ | ✅ list, tree | — | ✅ create/restore/export | ~1,180 |
| Stack Detection | ✅ 20 stacks | — | — | — | ~300 |
| Docker | ✅ adapter | — | — | — (adapter only) | ~220 |
| Node/Python | ✅ adapters | — | — | — (adapters only) | ~500 |

**Infrastructure in place:**
- Pydantic models (Project, Module, Stack, Action, State) — 497 lines
- Adapter protocol (base + registry + mock) — 400 lines
- Engine/executor — 257 lines
- Reliability (circuit breaker + retry) — ~400 lines
- Observability (health + metrics) — ~350 lines
- Persistence (state file + audit) — ~350 lines
- Web dashboard — 7 tabs, 40 templates, 4,294 lines of routes
- CLI — 6 command groups, 1,800 lines
- Tests — 324 passing, 3,972 lines

**Total existing codebase:** ~24,600 lines of Python + templates

---

## 2. Integration Domain Analysis

For each integration domain in the final vision, broken down by phase.

---

### 2.1 Docker

**Current state:** Adapter exists (220 lines). Can ps, images, build, up, down, logs, version. Not wired to CLI or web.

**Detect phase:**
- [exists] Adapter checks `docker` CLI availability
- [exists] `docker-compose` stack detects compose files
- [needed] Detect Dockerfile presence, base image, multi-stage
- [needed] Detect .dockerignore presence and quality
- [needed] Detect compose services, networks, volumes

**Observe phase:**
- [needed] Container status (running/stopped/exited) per service
- [needed] Image list with sizes, tags, ages
- [needed] Volume and network inventory
- [needed] Resource usage (CPU/memory per container)
- [needed] Container logs (streaming)
- [needed] Docker daemon health

**Facilitate phase:**
- [needed] Generate Dockerfile from detected stack (Python → python:3.12-slim, etc.)
- [needed] Generate docker-compose.yml from detected modules
- [needed] Generate .dockerignore from project structure
- [needed] Suggest multi-stage builds for production
- [needed] Suggest health checks for services

**Act phase:**
- [exists] Build, up, down, logs, ps, images via adapter
- [needed] CLI commands wrapping adapter (docker group)
- [needed] Web routes exposing adapter operations
- [needed] Web dashboard tab for container management
- [needed] Push to registry
- [needed] Prune unused images/volumes

**Dependencies:** None — can be built independently.
**Effort estimate:** Medium. Adapter exists, need core service + CLI + web.

---

### 2.2 CI/CD

**Current state:** Can list GitHub Actions runs, trigger dispatch events, view workflow status. Stack detection checks for workflow files.

**Detect phase:**
- [exists] GitHub Actions runs listed
- [needed] Detect all workflow files (.github/workflows/*.yml)
- [needed] Parse workflow structure (triggers, jobs, steps)
- [needed] Detect other CI providers (GitLab CI, Jenkins, etc.)
- [needed] Detect missing CI for detected stacks

**Observe phase:**
- [exists] List workflow runs with status
- [needed] Detailed job/step results per run
- [needed] Test results and coverage from artifacts
- [needed] Build duration trends
- [needed] Failure patterns

**Facilitate phase:**
- [needed] Generate GitHub Actions workflow from detected stacks
- [needed] Generate test step configs per stack (pytest for Python, jest for Node, etc.)
- [needed] Generate deployment workflows
- [needed] Generate matrix builds for multi-module repos
- [needed] Suggest workflow improvements

**Act phase:**
- [exists] Trigger dispatch events
- [needed] Cancel running workflows
- [needed] Re-run failed workflows
- [needed] Download artifacts
- [needed] Enable/disable workflows

**Dependencies:** GitHub integration (partially exists), Stack detection.
**Effort estimate:** Large. Needs workflow parsing + generation engine.

---

### 2.3 Kubernetes

**Current state:** Stack detection only (`kubernetes/stack.yml` detects manifests).

**Detect phase:**
- [exists] Stack detects k8s manifest files
- [needed] Detect Helm charts
- [needed] Detect Kustomize overlays
- [needed] Detect cluster connection (kubeconfig)
- [needed] Detect namespaces and contexts

**Observe phase:**
- [needed] Deployment status (replicas, ready, available)
- [needed] Pod health (running, pending, failed, restarts)
- [needed] Service and ingress listing
- [needed] Resource usage per pod
- [needed] Events and logs
- [needed] Node status

**Facilitate phase:**
- [needed] Generate k8s manifests from Docker setup
- [needed] Generate Helm chart skeleton
- [needed] Generate ingress configs
- [needed] Suggest resource limits from observed usage
- [needed] Generate namespace isolation

**Act phase:**
- [needed] kubectl adapter (apply, delete, rollback, scale)
- [needed] Port-forward
- [needed] Log streaming per pod
- [needed] Helm install/upgrade/rollback
- [needed] Context/namespace switching

**Dependencies:** Docker integration (for image references), kubectl/helm CLIs.
**Effort estimate:** Very large. New adapter + full service + CLI + web.

---

### 2.4 Cloud Infrastructure (Terraform / IaC)

**Current state:** Stack detection only (`terraform/stack.yml`).

**Detect phase:**
- [exists] Stack detects .tf files
- [needed] Parse Terraform providers, resources, modules
- [needed] Detect state backend configuration
- [needed] Detect other IaC (Pulumi, CloudFormation)
- [needed] Detect cloud service usage (AWS, GCP, Azure)

**Observe phase:**
- [needed] Terraform state summary (resources managed)
- [needed] Drift detection (plan with no changes = clean)
- [needed] Cost estimation
- [needed] Resource dependencies graph

**Facilitate phase:**
- [needed] Generate Terraform for common patterns (VPC, ECS, RDS, etc.)
- [needed] Generate backend configuration
- [needed] Generate variable files from .env
- [needed] Suggest cloud services for detected stacks

**Act phase:**
- [needed] Terraform adapter (init, plan, apply, destroy, import)
- [needed] State management (list, show, move, rm)
- [needed] Workspace management

**Dependencies:** Secrets vault (for cloud credentials).
**Effort estimate:** Very large. Complex domain, safety-critical operations.

---

### 2.5 Databases

**Current state:** Nothing.

**Detect phase:**
- [needed] Detect connection strings in .env
- [needed] Detect ORM configs (SQLAlchemy, Prisma, TypeORM, etc.)
- [needed] Detect migration files and framework
- [needed] Identify database type (Postgres, MySQL, SQLite, MongoDB)

**Observe phase:**
- [needed] Connection health (can we connect?)
- [needed] Migration status (pending migrations?)
- [needed] Schema summary
- [needed] Size and row counts

**Facilitate phase:**
- [needed] Generate connection configs from .env
- [needed] Generate migration templates
- [needed] Suggest indexes from query patterns
- [needed] Generate seed data templates

**Act phase:**
- [needed] Run migrations (up/down/status)
- [needed] Seed data
- [needed] Backup/restore database
- [needed] Connection testing

**Dependencies:** Secrets vault (for connection strings), stack detection.
**Effort estimate:** Large. Multiple database types, ORM frameworks.

---

### 2.6 Package Management

**Current state:** Detection knows about pyproject.toml, package.json, Cargo.toml, go.mod (for version extraction). Adapters for Python and Node exist but only for running commands.

**Detect phase:**
- [partial] Dependency files detected per stack
- [needed] Parse dependency lists with versions
- [needed] Compare installed vs declared vs latest
- [needed] Detect lock files (presence and freshness)

**Observe phase:**
- [needed] Outdated package report
- [needed] Known vulnerability scan (CVE databases)
- [needed] License inventory
- [needed] Dependency tree / depth analysis
- [needed] Unused dependency detection

**Facilitate phase:**
- [needed] Suggest version updates (minor/major/patch)
- [needed] Generate lock files
- [needed] Suggest alternatives for problematic dependencies

**Act phase:**
- [needed] Install dependencies
- [needed] Update specific packages
- [needed] Audit and fix vulnerabilities
- [needed] Lock/freeze

**Dependencies:** Stack detection, language adapters.
**Effort estimate:** Large. Each package manager is different.

---

### 2.7 Monitoring & Observability

**Current state:** Internal health checks and metrics exist for the control plane itself.

**Detect phase:**
- [needed] Detect monitoring configs (prometheus.yml, grafana dashboards)
- [needed] Detect logging configs (ELK, Loki, etc.)
- [needed] Detect alerting rules
- [needed] Detect application instrumentation

**Observe phase:**
- [needed] Endpoint health checks (HTTP probes)
- [needed] Dashboard links and status
- [needed] Alert status (firing, resolved)
- [needed] Uptime tracking

**Facilitate phase:**
- [needed] Generate Prometheus configs from detected services
- [needed] Generate basic Grafana dashboards
- [needed] Suggest alert rules based on service type
- [needed] Generate health check endpoints for services

**Act phase:**
- [needed] Configure alerts
- [needed] Silence/acknowledge alerts
- [needed] Test health probes

**Dependencies:** Docker/K8s (for service discovery), DNS/CDN.
**Effort estimate:** Large. Highly provider-dependent.

---

### 2.8 Security

**Current state:** Vaults handle secret encryption. Secret detection scans for .env files.

**Detect phase:**
- [partial] .env detection exists
- [needed] Scan for hardcoded secrets in code
- [needed] Detect exposed ports and services
- [needed] Detect missing .gitignore entries
- [needed] Detect insecure configurations

**Observe phase:**
- [needed] Security posture score
- [needed] Open vulnerability count
- [needed] Exposed secret count
- [needed] Permission/access audit

**Facilitate phase:**
- [needed] Generate .gitignore from detected stacks
- [needed] Generate security headers configs
- [needed] Suggest secret rotation schedule
- [needed] Generate SBOM (Software Bill of Materials)

**Act phase:**
- [needed] Rotate secrets across environments
- [needed] Fix detected vulnerabilities
- [needed] Update exposed configurations

**Dependencies:** Vault (exists), Package management (for vulnerability data).
**Effort estimate:** Medium-Large. Many are extensions of existing vault work.

---

### 2.9 Testing

**Current state:** Stack detection can identify test directories. Language adapters can run commands.

**Detect phase:**
- [needed] Detect test framework per module (pytest, jest, go test, etc.)
- [needed] Detect coverage configuration
- [needed] Count test files and test functions
- [needed] Detect test/coverage gaps

**Observe phase:**
- [needed] Last test run results
- [needed] Coverage percentage and trends
- [needed] Flaky test tracking
- [needed] Slow test identification
- [needed] Test-to-code coverage mapping

**Facilitate phase:**
- [needed] Generate test templates per stack
- [needed] Generate coverage configs
- [needed] Suggest missing test cases
- [needed] Generate test fixtures/mocks

**Act phase:**
- [needed] Run tests per module via adapter
- [needed] Run with coverage
- [needed] Run specific test files/functions
- [needed] Generate test reports

**Dependencies:** Language adapters (exist), stack detection.
**Effort estimate:** Medium. Adapters exist, mostly wiring + reporting.

---

### 2.10 DNS / CDN

**Current state:** Nothing.

**Detect phase:**
- [needed] Detect domain configs (CNAME, DNS records)
- [needed] Detect CDN configs (Cloudflare, CloudFront)
- [needed] Detect SSL certificates

**Observe phase:**
- [needed] DNS resolution health
- [needed] SSL certificate expiry
- [needed] CDN cache hit rates

**Facilitate phase:**
- [needed] Generate DNS records for deployments
- [needed] Generate CDN configs
- [needed] Suggest caching strategies

**Act phase:**
- [needed] Update DNS records
- [needed] Purge CDN cache
- [needed] Renew SSL certificates

**Dependencies:** Cloud infrastructure, deployment pipeline.
**Effort estimate:** Medium. API-driven, well-defined scope.

---

### 2.11 Documentation

**Current state:** Pages builder can build and deploy doc sites (Docusaurus, MkDocs, Hugo, Sphinx). Content management handles files.

**Detect phase:**
- [exists] Detects doc folders and configs
- [needed] Detect API spec files (OpenAPI, GraphQL schemas)
- [needed] Detect README presence per module
- [needed] Detect inline documentation quality

**Observe phase:**
- [needed] Documentation coverage per module
- [needed] Stale documentation detection
- [needed] Broken link scanning
- [needed] API spec validation

**Facilitate phase:**
- [partial] Builders generate site configs
- [needed] Generate API docs from specs
- [needed] Generate README templates per module
- [needed] Generate changelog from commits

**Act phase:**
- [exists] Build and deploy doc sites
- [needed] Validate API specs
- [needed] Link checking
- [needed] Doc linting

**Dependencies:** Git (for changelog), stack detection.
**Effort estimate:** Medium. Much exists, extensions are well-scoped.

---

## 3. Platform Intelligence Analysis

Cross-cutting capabilities that work across all integrations:

**Cross-integration analysis:**
- Compare versions across integrations (Docker image Python version vs CI Python version vs project Python version)
- Identify configuration inconsistencies
- Detect environment drift (dev vs staging vs production)
- **Dependencies:** Requires multiple integrations at Observe depth

**Gap detection:**
- Compare detected stacks against best practices (has Python → should have tests, Docker, CI, linting)
- Suggest missing integrations based on project type
- **Dependencies:** Deep detection across stacks

**Template library:**
- Community and custom templates for every generator
- Stack-specific defaults (Python → pytest + black + ruff, Node → jest + prettier)
- **Dependencies:** Facilitate phase of at least several integrations

**Plugin architecture:**
- Third parties can add new integration domains
- Standard adapter + service + CLI + web pattern
- **Dependencies:** Stable patterns from building first integrations

---

## 4. Dependency Graph

```
                    Stack Detection (exists)
                          │
              ┌───────────┼───────────┐
              │           │           │
           Docker     CI/CD      Language
          (adapter    (partial)   Adapters
           exists)                (exist)
              │           │           │
              ├───────────┼───────────┤
              │                       │
         Kubernetes              Package Mgmt
              │                       │
              │                  Security
         Cloud / IaC                  │
              │                  Testing
              │                       │
         Monitoring              Documentation
              │
          DNS / CDN
```

**Natural build order (by dependency):**

1. Docker (adapter exists, no blockers)
2. CI/CD (GitHub exists, workflow generation needed)
3. Package Management (language adapters exist)
4. Testing (language adapters + package management)
5. Security (extends vault + package management)
6. Kubernetes (depends on Docker)
7. Cloud / IaC (depends on secrets vault)
8. Documentation (extends existing pages)
9. Monitoring (depends on Docker/K8s)
10. DNS / CDN (depends on cloud/deployment)
11. Platform Intelligence (depends on several integrations at depth)

---

## 5. Sizing Estimate

| Domain | New Adapter | Core Service | CLI | Web | Templates | Est. Lines |
|---|---|---|---|---|---|---|
| Docker | extend | ~500 | ~200 | ~400 | ~2 | ~1,100 |
| CI/CD | — | ~800 | ~300 | ~500 | ~3 | ~1,600 |
| Package Mgmt | — | ~600 | ~200 | ~400 | ~2 | ~1,200 |
| Testing | extend | ~400 | ~150 | ~300 | ~2 | ~850 |
| Security | — | ~500 | ~200 | ~300 | ~2 | ~1,000 |
| Kubernetes | new ~300 | ~700 | ~300 | ~500 | ~3 | ~1,800 |
| Cloud/IaC | new ~300 | ~800 | ~300 | ~500 | ~3 | ~1,900 |
| Documentation | extend | ~400 | ~150 | ~300 | ~2 | ~850 |
| Monitoring | new ~200 | ~500 | ~200 | ~400 | ~2 | ~1,300 |
| DNS/CDN | new ~200 | ~300 | ~150 | ~300 | ~1 | ~950 |
| Intelligence | — | ~1,000 | ~200 | ~500 | — | ~1,700 |
| **Total** | | | | | | **~14,250** |

Current codebase: ~24,600 lines → Final: ~38,850 lines (60% growth)

---

---

## 6. Foundation & Infrastructure Analysis

### 6.1 The Proven Integration Pattern

Every existing integration follows the same three-file pattern:

```
core service (logic)  →  CLI wrapper  →  Web routes wrapper
   git_ops.py              git.py         routes_integrations.py
   vault.py                vault.py       routes_vault.py
   backup_ops.py           backup.py      routes_backup*.py
```

**Core service** (`src/core/services/<domain>_ops.py`):
- Pure functions, no Flask/Click imports
- Takes `project_root: Path` as first arg
- Returns `dict` results (JSON-serializable)
- Calls CLI tools via `subprocess.run()`
- 300–1,200 lines per domain

**CLI wrapper** (`src/ui/cli/<domain>.py`):
- Click group + commands
- Resolves `project_root` from context
- Calls core service functions directly
- Formats output for terminal (emoji, tables)
- 150–370 lines per domain

**Web routes** (`src/ui/web/routes_<domain>.py`):
- Flask blueprint
- `_project_root()` from `current_app.config`
- Calls core service functions, returns `jsonify(result)`
- 100–400 lines per domain

**This pattern is solid and does NOT need an abstraction layer.** New
integrations should follow this exact pattern.

### 6.2 Proposed Structure for New Integrations

Current:
```
src/core/services/
├── git_ops.py
├── vault.py / vault_io.py / vault_env_ops.py
├── content_crypto.py / content_optimize.py / content_release.py
├── backup_ops.py
├── secrets_ops.py
├── detection.py
├── pages_engine.py
└── pages_builders/
```

Proposed additions:
```
src/core/services/
├── (existing...)
├── docker_ops.py          # Docker & Compose operations
├── ci_ops.py              # CI/CD workflow management
├── package_ops.py         # Dependency analysis & management
├── testing_ops.py         # Test execution & reporting
├── security_ops.py        # Secret scanning, vulnerability detection
├── k8s_ops.py             # Kubernetes operations
├── iac_ops.py             # Terraform / IaC operations
├── monitoring_ops.py      # Health probes, uptime, alerts
├── dns_ops.py             # DNS/CDN management
├── docs_ops.py            # Documentation analysis & generation
└── intelligence.py        # Cross-integration analysis engine
```

CLI additions:
```
src/ui/cli/
├── (existing: vault, content, pages, git, backup, secrets)
├── docker.py              # docker ps / build / up / down / logs
├── ci.py                  # ci list / trigger / generate
├── packages.py            # packages outdated / audit / update
├── test.py                # test run / coverage / report
├── security.py            # security scan / fix
├── k8s.py                 # k8s status / apply / rollback
├── iac.py                 # iac plan / apply / destroy
└── docs.py                # docs check / generate / build
```

Web route additions:
```
src/ui/web/
├── (existing routes...)
├── routes_docker.py       # /api/docker/*
├── routes_ci.py           # /api/ci/*
├── routes_packages.py     # /api/packages/*
├── routes_testing.py      # /api/testing/*
├── routes_security.py     # /api/security/*
├── routes_k8s.py          # /api/k8s/*
├── routes_iac.py          # /api/iac/*
└── routes_docs.py         # /api/docs/*
```

Dashboard tab additions:
```
src/ui/web/templates/
├── partials/
│   ├── (existing tabs...)
│   ├── _tab_docker.html
│   ├── _tab_ci.html
│   ├── _tab_packages.html
│   └── _tab_infrastructure.html  (K8s + IaC + DNS combined)
├── scripts/
│   ├── (existing...)
│   ├── _docker.html
│   ├── _ci.html
│   ├── _packages.html
│   └── _infrastructure.html
```

### 6.3 Adapter Extensions

The adapter layer already has the right structure:

```
src/adapters/
├── base.py                # Adapter ABC — unchanged
├── registry.py            # Registry — add new registrations
├── mock.py                # Mock — unchanged (handles any adapter)
├── containers/
│   └── docker.py          # EXISTS — 220 lines, ready to use
├── vcs/
│   └── git.py             # EXISTS — 246 lines
├── languages/
│   ├── python.py          # EXISTS — 240 lines
│   └── node.py            # EXISTS — 254 lines
├── shell/
│   ├── command.py          # EXISTS
│   └── filesystem.py      # EXISTS
├── orchestration/          # NEW
│   ├── kubernetes.py       # kubectl adapter
│   └── helm.py             # helm adapter
├── iac/                    # NEW
│   └── terraform.py        # terraform adapter
└── monitoring/             # NEW
    └── prometheus.py       # prometheus/alertmanager adapter
```

Most integrations do NOT need a dedicated adapter — they use `subprocess.run()`
directly in the core service (like `git_ops.py` calls `git` directly). Adapters
are only needed when the tool binding has complex state or needs mock-swap for
testing.

### 6.4 Model Additions

Current models cover: Project, Module, Stack, Action, Receipt, State.

**Needed for deeper detection:**
```python
# src/core/models/integration.py  (NEW)

class IntegrationStatus(BaseModel):
    """Status of one integration domain."""
    name: str                    # "docker", "ci", "k8s", etc.
    available: bool              # Is the CLI tool installed?
    detected: bool               # Are config files present?
    version: str | None          # Tool version
    details: dict[str, Any]      # Domain-specific status info

class ProjectHealth(BaseModel):
    """Aggregated health across all integrations."""
    integrations: list[IntegrationStatus]
    gaps: list[str]              # "No Dockerfile found", "No CI configured"
    warnings: list[str]          # "Outdated deps", "Secrets drift"
```

**Needed for config generation:**
```python
# src/core/models/template.py  (NEW)

class GeneratedFile(BaseModel):
    """A file generated by the facilitate phase."""
    path: str                    # Relative path from project root
    content: str                 # File content
    overwrite: bool = False      # Whether to overwrite if exists
    reason: str                  # Why this file was generated
```

### 6.5 Detection Expansion

Current `detection.py` only detects stacks by marker files. It needs to grow
to detect integration status:

```python
# Proposed: src/core/services/detection.py additions

def detect_integrations(project_root: Path) -> list[IntegrationStatus]:
    """Detect all integration domains in the project."""
    return [
        _detect_docker(project_root),
        _detect_ci(project_root),
        _detect_k8s(project_root),
        _detect_terraform(project_root),
        _detect_monitoring(project_root),
        # ... etc
    ]

def _detect_docker(project_root: Path) -> IntegrationStatus:
    """Check for Dockerfile, docker-compose.yml, Docker CLI."""
    has_dockerfile = (project_root / "Dockerfile").exists()
    has_compose = any(
        (project_root / f).exists()
        for f in ["docker-compose.yml", "docker-compose.yaml", "compose.yml"]
    )
    docker_available = shutil.which("docker") is not None
    # ...
```

### 6.6 Config Generation Infrastructure

The facilitate phase needs a way to generate files from templates. The pages
builders already have `template_engine.py` — this can be generalized:

```
src/core/services/generators/          # NEW directory
├── __init__.py
├── dockerfile.py                      # Generate Dockerfile from stack
├── compose.py                         # Generate docker-compose.yml from modules
├── github_workflow.py                 # Generate .github/workflows/*.yml
├── gitignore.py                       # Generate .gitignore from stacks
├── k8s_manifest.py                    # Generate k8s deployment/service/ingress
└── terraform.py                       # Generate basic tf configs

# Each generator follows the same pattern:
# def generate(project: Project, modules: list[Module], **opts) -> list[GeneratedFile]
```

### 6.7 Recipe: Building a New Integration

Every new integration follows this exact sequence:

1. **Core service** — `src/core/services/<domain>_ops.py`
   - Pure functions, subprocess calls to the CLI tool
   - Detection function: is the tool installed? Are config files present?
   - Status function: what's the current state?
   - Action functions: the operations users will need

2. **CLI wrapper** — `src/ui/cli/<domain>.py`
   - Click group with commands wrapping each core function
   - Register in `src/main.py` Click group

3. **Web routes** — `src/ui/web/routes_<domain>.py`
   - Flask blueprint wrapping each core function as JSON endpoint
   - Register in `src/ui/web/server.py`

4. **Dashboard tab** — `templates/partials/_tab_<domain>.html` + `scripts/_<domain>.html`
   - HTML structure + JS logic calling the API endpoints
   - Add include in `dashboard.html`

5. **Generator** (if facilitate phase needed) — `src/core/services/generators/<domain>.py`
   - Takes project/module data, produces `GeneratedFile` list

6. **Tests** — `tests/test_<domain>.py`
   - Unit tests for core service
   - CLI smoke tests
   - Web endpoint tests

7. **Stack integration** — update relevant `stacks/*/stack.yml` with capabilities

**Estimated per integration: 4-7 files, 800-1,800 lines, 1-3 days.**

---

*This analysis should be refined as each integration domain is designed
in detail. Estimates are rough and will shift as patterns emerge from
building the first few integrations.*
