# ☸️ Kubernetes Setup Wizard — Implementation Plan

> **Date**: 2026-02-13
> **Status**: ANALYSIS — Deep investigation before implementation
> **Predecessor**: Docker wizard (#3) — complete ✅
> **Core principle**: K8s doesn't ask dumb questions. It READS from Docker, GitHub, CI/CD, and project config to present smart defaults.

---

## 1. THE REAL PROBLEM

The current K8s wizard is a flat form that asks the user to type an app name, image name, and port.
This is the opposite of the project's core principle: **integrated intelligence**.

The K8s wizard should **already know**:
- What Docker services exist (from compose)
- What images they use (from Docker config or CI/CD registry push)
- What ports they expose (from Docker/compose)
- What environment variables they need (from .env / compose env)
- What databases/caches are in the compose stack (postgres, redis)
- What the GitHub repo is (for GHCR image naming)
- What project environments exist (dev/staging/prod → namespace mapping)

**The wizard presents smart answers. The user adjusts.**

---

## 2. CROSS-INTEGRATION DATA FLOW INTO K8S

### What K8s READS from other integrations:

| Source | Data Used | How K8s Uses It |
|--------|-----------|-----------------|
| **Docker compose** | Service names, images, ports, volumes, env vars, depends_on | Each compose service → K8s Deployment + Service candidate |
| **Docker compose** | Infrastructure services (postgres, redis, rabbitmq) | Suggest StatefulSet vs "Use managed service via Terraform →" |
| **Docker status** | `dockerfiles[]`, `compose_services[]` | Validate that images can be built |
| **Project modules** | `name`, `path`, `stack`, `domain` | Map modules to deployable containers, skip libraries/docs |
| **GitHub repo** | `owner/repo` from remote URL | GHCR image name: `ghcr.io/{owner}/{repo}-{module}:latest` |
| **CI/CD status** | Workflow exists? Push to registry? | Image tag strategy (commit SHA, latest, branch-based) |
| **Project environments** | `development`, `production` | Namespace per environment: `{project}-{env}` |
| **.env file** | Environment variables | ConfigMap data source |
| **Terraform status** | `has_cli`, `tf_files` | "Cluster managed by Terraform" context |

### Data availability right now:

| Data | Available via | Format |
|------|--------------|--------|
| Docker compose services (names only) | `wizDetect.docker_status.compose_services` | `["api", "web", "db"]` |
| Docker compose services (FULL detail) | `GET /docker/status` → `compose_services` (only names!) | **GAP: only names, not image/port/env** |
| Project modules | `wizDetect.config_data.modules` | `[{name, path, stack}]` — **missing `domain`** |
| GitHub repo info | `wizDetect.gh_repo_info` | `{owner, name, visibility, ...}` |
| Git remotes | `wizDetect.git_remotes` | `{remotes: [{name, url}]}` |
| K8s probe | `wizDetect.status_probes.k8s` | `{has_kubectl, has_helm, manifest_count, cluster_connected, ...}` |
| K8s detailed status | `GET /k8s/status` | `{has_k8s, kubectl, manifests, resource_summary, helm_charts, kustomize}` |
| Project environments | `wizDetect.config_data.environments` | `[{name}]` |
| K8s env-namespace map | `GET /k8s/env-namespaces` | `{environments: [{name, namespace, has_overlay, values_file}]}` |

---

## 3. IDENTIFIED DATA GAPS

Before the K8s wizard can be truly intelligent, we need:

### Gap 1: Compose service DETAILS (not just names)

`docker_status()` currently returns `compose_services: ["api", "web", "db"]` — just names.

The K8s wizard needs the **full service specification** to generate matching resources:
- Image name (or build context)
- Ports (host:container mapping)
- Environment variables
- Volumes
- depends_on relationships
- Health check configuration

**What to do**: Add a `compose_service_details` field to `docker_status()` or create a new
endpoint `GET /docker/compose/services` that parses the compose file and returns full service
specs. The compose parser already exists (`yaml.safe_load` on the compose file), we just need
to return the full dict instead of just keys.

### Gap 2: Module `domain` field missing from wizard detect

`_wizard_config_data()` returns `{name, path, stack}` but NOT `domain`. The Docker wizard
already needs `domain` to classify modules (library vs deployable). K8s needs it too.

**What to do**: Add `domain` and `description` to _wizard_config_data:
```python
modules = [{"name": m.name, "path": m.path, "stack": m.stack, "domain": m.domain, "description": m.description}
            for m in (proj.modules or [])]
```

### Gap 3: Image name resolution

The wizard needs to figure out what image name a Docker service will use in K8s. Three sources:
1. Compose `image` field (e.g. `ghcr.io/user/app:latest`)
2. Build context → needs registry prefix → `ghcr.io/{github_owner}/{repo}-{service}:latest`
3. CI/CD workflow → might reference a specific registry

Currently no endpoint resolves this automatically. The wizard must construct it from:
- `gh_repo_info.owner` + `gh_repo_info.name` → `ghcr.io/{owner}/{name}`
- Or Docker compose image field if present
- Or module name as fallback

**What to do**: Client-side logic, no backend change needed. Priority:
1. Compose `image` field → use as-is
2. GitHub repo → `ghcr.io/{owner}/{repo}:{module}` or `ghcr.io/{owner}/{repo}-{module}:latest`
3. Fallback → `{module}:latest`

---

## 4. THE USER'S ACTUAL DECISIONS

When setting up Kubernetes for a project, the user needs to decide:

### A. Which services become K8s workloads?

From Docker compose services, the wizard classifies:

| Service Type | Example | K8s Resource | Default |
|-------------|---------|-------------|---------|
| **Application service** (has build context or app image) | `api`, `web` | Deployment + Service | ✅ Pre-selected |
| **Infrastructure service** (well-known image) | `postgres:16`, `redis:7` | StatefulSet OR "Use managed instead" | ⚠️ Offer choice |
| **Utility service** (one-off) | `migrate`, `seed` | Job (or skip) | ❌ Not selected |

Classification logic:
- If `image` starts with `postgres`, `mysql`, `mariadb`, `mongo`, `redis`, `memcached`,
  `rabbitmq`, `kafka`, `elasticsearch`, `minio` → Infrastructure
- If has `build` context → Application
- If `image` matches a project module name → Application
- Everything else → Application (default)

### B. Per-application-service configuration

For each selected application service:

| Field | Smart Default | Source |
|-------|---------------|--------|
| **Image** | `ghcr.io/{owner}/{repo}-{service}:latest` | GitHub + compose |
| **Port** | From compose `ports` mapping | Docker compose |
| **Replicas** | `2` (or `1` for dev namespace) | Convention |
| **CPU request/limit** | `100m` / `500m` | Convention |
| **Memory request/limit** | `128Mi` / `256Mi` (or `512Mi` for JVM stacks) | Stack-aware |
| **Health check path** | `/health` or `/healthz` | Convention, could detect from code |
| **Health check port** | Same as container port | Compose |
| **Liveness initial delay** | `10s` | Convention |
| **Readiness initial delay** | `5s` | Convention |
| **Service type** | `ClusterIP` (internal) or `LoadBalancer` (if main web service) | Compose port exposure |
| **Environment variables** | From compose `environment` | Docker compose |
| **Secrets** | Vault secrets → K8s Secret references | Cross-integration |

### C. Per-infrastructure-service decision

For each detected infrastructure service (postgres, redis, etc.):

| Option | K8s Resource | When to suggest |
|--------|-------------|-----------------|
| **StatefulSet** (self-managed) | StatefulSet + Service + PVC | Dev/testing, local clusters |
| **Managed service** (cloud) | Nothing — Terraform manages it | Production, cloud clusters |
| **Skip** (not needed in K8s) | Nothing | DB runs outside cluster |

If user picks StatefulSet:
- Image: same as compose (e.g. `postgres:16-alpine`)
- Port: standard port for the service (5432, 6379, etc.)
- Volume: PersistentVolumeClaim
- Environment: from compose env (POSTGRES_DB, POSTGRES_USER, etc.)

If user picks "managed service" → CTA: "Set up Terraform → to provision RDS/CloudSQL"

### D. Ingress configuration

| Decision | Options |
|----------|---------|
| **Generate Ingress?** | Yes / No |
| **Which services get external access?** | Checkboxes per service (pre-select: web-facing services) |
| **Host pattern** | `{service}.{domain}` or `{domain}/{service}` (path-based) |
| **TLS?** | Auto-suggest if cert-manager detected or cloud LB |
| **Ingress controller** | nginx (default), traefik, other |

### E. ConfigMap and Secrets

| Source | K8s Resource |
|--------|-------------|
| `.env` file variables (non-sensitive) | ConfigMap |
| Vault secrets / compose secrets | K8s Secret (or ExternalSecret if operator detected) |
| Compose `environment` per service | Per-Deployment env from ConfigMap ref |

### F. Namespace strategy

| Scenario | Strategy |
|----------|----------|
| Single environment (dev only) | `default` namespace or project-named namespace |
| Multi-environment (dev + prod) | One namespace per env: `{project}-{env}` |
| Already have overlays (Kustomize) | Detect and respect existing structure |

Data source: `project.yml` environments + `/k8s/env-namespaces`

### G. Deployment strategy

| Option | YAML |
|--------|------|
| **RollingUpdate** (default) | `maxUnavailable: 1, maxSurge: 1` |
| **Recreate** | Good for stateful apps that can't run two copies |
| **Blue/Green** | Advanced — not for initial setup |

### H. Additional resources

| Resource | When to offer |
|----------|--------------|
| **HorizontalPodAutoscaler** | If replicas > 1, suggest autoscaling |
| **NetworkPolicy** | If multiple services (isolate DB from external) |
| **PodDisruptionBudget** | Production namespaces |
| **ServiceAccount** | If RBAC needed |

### I. Helm vs raw manifests

| Scenario | Path |
|----------|------|
| No Helm chart detected, no Helm installed | Raw manifests (default) |
| Helm installed, no chart yet | Offer: "Scaffold a Helm chart?" |
| Existing Helm chart detected | Offer: "Customize values.yaml instead of modifying templates" |
| Existing Kustomize | Offer: "Generate Kustomize overlay for this environment" |

---

## 5. WIZARD FLOW (4 steps, matching Docker wizard pattern)

### Step 1: Detect

**API calls:**
- `wizDetect` (already cached from shared detect) → probes, docker_status, config_data, gh_repo_info
- `GET /k8s/status` → detailed manifest detection, resource summary, Helm/Kustomize
- `GET /docker/compose/services` (NEW or enhanced) → full compose service details

**Display:**
```
☸️ Kubernetes Environment
──────────────────────────────────────
☸️  kubectl           v1.29              ✓
⎈   Helm              v3.14              ✓
🔗  Cluster           minikube           ✓  (or ⚠ Not connected)
📄  Manifests         0 found            ⚠
📦  Helm Chart        None               ○
🔧  Kustomize         None               ○
🛤  Skaffold          None               ○

🐳 Docker Context (from your Docker setup)
──────────────────────────────────────
📦  api               build: ./src       port 8000    🟢 deployable
📦  web               build: ./web       port 3000    🟢 deployable
📦  postgres           postgres:16        port 5432    🔵 infrastructure
📦  redis             redis:7            port 6379    🔵 infrastructure

📋 Project Environments
──────────────────────────────────────
🌍  development       → namespace: devops-control-plane-development
🌍  production        → namespace: devops-control-plane-production

💡 2 deployable services detected from Docker.
   We'll generate K8s manifests for each.
   Click Configure → to customize.
```

**Read-only scan** notice at top (consistent with Git/GitHub detect UX).

**Cross-integration CTAs:**
- If no Docker: "💡 Set up Docker first — K8s needs container images."
- If no GitHub: "💡 Connect GitHub for GHCR image naming."
- If existing manifests found: "📄 Found {N} existing resources. We'll show what's already deployed."

**Store:** `data._k8s`, `data._docker`, `data._dockerStatus`, `data._composeServices`,
`data._modules`, `data._ghRepo`, `data._envNamespaces`

### Step 2: Configure — Docker-Aware Resource Builder

This is the core intelligence step. Three collapsible sections:

**Section A: Application Services** (from Docker compose)

For each deployable compose service, an expandable card:

```
┌─ api ────────────────────────────────────────────────────────┐
│  ☑ Include in K8s deployment                                 │
│                                                              │
│  Image:     [ghcr.io/cyberpunk042/devops-control-plane-api:latest]  ← from GH repo
│  Port:      [8000]                                           ← from compose
│  Replicas:  [2]                                              │
│  Service:   [ClusterIP ▾]                                    │
│                                                              │
│  ▶ Resources (CPU/Memory)                                    │
│    CPU:   request [100m]  limit [500m]                        │
│    Memory: request [128Mi]  limit [256Mi]                     │
│                                                              │
│  ▶ Health Check                                              │
│    Path: [/health]   Port: [8000]                             │
│    Liveness delay: [10s]   Readiness delay: [5s]              │
│                                                              │
│  ▶ Environment (from compose)                                │
│    DATABASE_URL = postgresql://...     → ConfigMap ref         │
│    SECRET_KEY = ***                    → Secret ref            │
└──────────────────────────────────────────────────────────────┘
```

When no compose services exist but modules are detected:
- Fall back to module-based detection (like Docker wizard does)
- Pre-select modules with domain=ops/service
- Skip domain=library, domain=docs

**Section B: Infrastructure Services** (databases, caches from compose)

For each infrastructure service detected:

```
┌─ postgres (postgres:16-alpine) ────────────────────────────────┐
│  ○ StatefulSet (self-managed in cluster)                       │
│  ○ Managed service (→ set up Terraform)                        │
│  ● Skip (runs outside cluster)                                 │
│                                                                │
│  If StatefulSet:                                               │
│    Port: [5432]     Storage: [10Gi]                            │
│    Env: POSTGRES_DB=[app]  POSTGRES_USER=[app]                 │
└────────────────────────────────────────────────────────────────┘
```

**Section C: Cluster Configuration**

```
Namespace:        [default ▾]   (or project-named, or per-environment)
  ☐ Create separate namespace per environment
     → development: devops-control-plane-development
     → production:  devops-control-plane-production

Ingress:
  ☑ Generate Ingress manifest
     Services with external access:
       ☑ api   → host: [api.example.com]
       ☑ web   → host: [example.com]

Additional:
  ☐ Generate ConfigMap from .env
  ☐ Generate HorizontalPodAutoscaler
  ☐ Generate NetworkPolicy (isolate services)
```

**Section D: Output Format**

```
○ Raw manifests (k8s/ directory)         ← default if no Helm
○ Helm chart (scaffold chart + values)   ← if Helm detected
○ Kustomize overlays                     ← if Kustomize detected
```

**collect():** Store all selections per service + cluster config + output format.

**validate():**
- At least one service must be selected
- No port conflicts across services
- Namespace name must be valid K8s name
- Ingress hosts must not be empty if Ingress is checked

### Step 3: Preview & Edit

For each file to be generated, show content in **editable textareas** (same pattern as Docker wizard):

**API calls:**
- For raw manifests: `POST /k8s/generate/wizard` with the resource list built from user selections
- For Helm chart: `POST /k8s/helm/template` (dry-run render)

**Display:**
```
📄 k8s/api-deployment.yaml                                    [create]
┌─────────────────────────────────────────────────────────────┐
│ apiVersion: apps/v1                                         │
│ kind: Deployment                                            │
│ metadata:                                                   │
│   name: api                                                 │
│   namespace: default                                        │
│   labels:                                                   │
│     app: api                                                │
│ spec:                                                       │
│   replicas: 2                                               │
│   ...                                                       │
└──────────────────────────────────────── [Edit] [Reset] ─────┘

📄 k8s/api-service.yaml                                       [create]
...

📄 k8s/web-deployment.yaml                                    [create]
...

📄 k8s/ingress.yaml                                           [create]
...
```

User can edit any textarea. The `collect()` callback captures edited content.
A "Reset" button re-generates from the backend.

### Step 4: Review & Apply

**Summary:**
```
Review — The following K8s manifests will be generated:

🚀 Deployment: api          2 replicas of ghcr.io/.../api:latest     [create]
🌐 Service: api             ClusterIP port 8000                       [create]
🚀 Deployment: web          2 replicas of ghcr.io/.../web:latest     [create]
🌐 Service: web             ClusterIP port 3000                       [create]
🔀 Ingress: app             api.example.com, example.com             [create]
📋 ConfigMap: app-config    12 environment variables                   [create]
📁 Output: k8s/             6 files                                    [create]
```

**On apply:**
- Write each file via the Docker wizard's write endpoint (`POST /docker/generate/write`)
  or a K8s-specific write endpoint
- Show per-file result (✅ / ❌)
- If cluster connected: "Apply to cluster now?" → `POST /k8s/apply`
- Validate manifests: `GET /k8s/validate`

**CTAs:**
- "Next: Set up CI/CD → " (add K8s deploy step to pipeline)
- "Manage infrastructure with Terraform →"

---

## 6. ENDPOINTS USED

| Step | Endpoint | Purpose | Exists? |
|------|----------|---------|---------|
| Detect | `GET /wizard/detect` (cached) | Probes, docker status, modules, GH repo | ✅ Yes |
| Detect | `GET /k8s/status` | Detailed K8s manifest scan | ✅ Yes |
| Detect | `GET /k8s/env-namespaces` | Environment → namespace mapping | ✅ Yes |
| Detect | `GET /docker/status` (or cached) | Compose services | ✅ Yes (names only) |
| Detect | **GET /docker/compose/details** | **Full compose service specs** | ❌ **NEW** |
| Preview | `POST /k8s/generate/wizard` | Generate manifests from resource list | ✅ Yes |
| Preview | `POST /k8s/generate/manifests` | Generate from simple params | ✅ Yes (simpler) |
| Apply | `POST /docker/generate/write` | Write generated files to disk | ✅ Yes |
| Apply | `POST /k8s/apply` | Apply manifests to cluster | ✅ Yes |
| Apply | `GET /k8s/validate` | Validate generated manifests | ✅ Yes |

**One new endpoint needed:** `GET /docker/compose/details` — parse compose file and return
full service specs (image, build, ports, environment, volumes, depends_on, healthcheck).

Alternative: enhance `docker_status()` to include full compose details (not just names).
This is cleaner and avoids a new route.

---

## 7. BACKEND CHANGES NEEDED

### 7.1 Enhance `docker_status()` — compose_service_details

Currently `_parse_compose_services()` returns only service names.
Add a `_parse_compose_service_details()` that returns full specs:

```python
def _parse_compose_service_details(compose_path: Path) -> list[dict]:
    """Extract full service details from compose file."""
    data = yaml.safe_load(compose_path.read_text())
    services = []
    for name, spec in data.get("services", {}).items():
        svc = {"name": name}
        
        # Image vs build
        svc["image"] = spec.get("image", "")
        build = spec.get("build")
        if isinstance(build, str):
            svc["build_context"] = build
        elif isinstance(build, dict):
            svc["build_context"] = build.get("context", "")
            svc["dockerfile"] = build.get("dockerfile", "")
        
        # Ports
        svc["ports"] = spec.get("ports", [])
        
        # Environment
        env = spec.get("environment", {})
        if isinstance(env, list):
            env = dict(e.split("=", 1) for e in env if "=" in e)
        svc["environment"] = env
        
        # Volumes
        svc["volumes"] = spec.get("volumes", [])
        
        # Dependencies
        deps = spec.get("depends_on", [])
        if isinstance(deps, dict):
            deps = list(deps.keys())
        svc["depends_on"] = deps
        
        # Health check
        svc["healthcheck"] = spec.get("healthcheck")
        
        # Restart
        svc["restart"] = spec.get("restart", "")
        
        # Container name
        svc["container_name"] = spec.get("container_name", "")
        
        # Networks
        svc["networks"] = spec.get("networks", [])
        
        # Classify
        svc["_type"] = _classify_compose_service(name, svc)
        
        services.append(svc)
    return services
```

### 7.2 Add `domain` to `_wizard_config_data()`

```python
modules = [{"name": m.name, "path": m.path, "stack": m.stack,
            "domain": m.domain, "description": m.description}
            for m in (proj.modules or [])]
```

---

## 8. INFRASTRUCTURE SERVICE CLASSIFICATION

Known infrastructure images (for the "StatefulSet vs Managed" decision):

| Image prefix | Service type | Default port | Managed alternative |
|-------------|-------------|-------------|-------------------|
| `postgres` | Database | 5432 | RDS / CloudSQL |
| `mysql`, `mariadb` | Database | 3306 | RDS / CloudSQL |
| `mongo` | Database | 27017 | DocumentDB / Atlas |
| `redis` | Cache | 6379 | ElastiCache / Memorystore |
| `memcached` | Cache | 11211 | ElastiCache |
| `rabbitmq` | Message Queue | 5672 / 15672 | Amazon MQ |
| `kafka` | Message Queue | 9092 | MSK |
| `elasticsearch`, `opensearch` | Search | 9200 | OpenSearch Service |
| `minio` | Object Storage | 9000 | S3 / GCS |
| `nginx`, `traefik`, `envoy` | Proxy | 80/443 | Ingress controller (different path) |
| `prometheus` | Monitoring | 9090 | Managed Prometheus |
| `grafana` | Monitoring | 3000 | Managed Grafana |

---

## 9. IMAGE NAME RESOLUTION LOGIC

Priority order for determining the K8s image name:

```
1. Compose `image` field → use as-is
   e.g. "ghcr.io/user/app:latest" → direct

2. Compose `build` context + GitHub repo → construct registry path
   build: ./src
   GH repo: cyberpunk042/devops-control-plane
   → "ghcr.io/cyberpunk042/devops-control-plane-{service}:latest"

3. Compose `build` context + no GitHub → local image name
   build: ./src
   → "{service}:latest"

4. No compose, module-based → same as #2/#3 with module name
```

---

## 10. MULTI-ENVIRONMENT NAMESPACE STRATEGY

When the project has multiple environments defined:

```yaml
# project.yml
environments:
  - name: development
    default: true
  - name: production
```

The wizard should offer:

**Option A: Single namespace** (simple)
- All resources in `default` or `{project-name}`
- Good for: local dev, minikube, single-env projects

**Option B: Per-environment namespaces** (production-ready)
- `devops-control-plane-development`
- `devops-control-plane-production`
- Generates Namespace manifests
- ConfigMaps per environment (different env vars)
- Kustomize overlays if Kustomize is detected

The `/k8s/env-namespaces` endpoint already does this mapping.

---

## 11. FILES TO EDIT

| File | What changes |
|------|-------------|
| `_integrations_setup_modals.html` | Replace `openK8sSetupWizard()` (lines 2227-2371) |
| `routes_devops.py` | Add `domain` + `description` to `_wizard_config_data()` |
| `docker_ops.py` | Add `_parse_compose_service_details()`, include in `docker_status()` |
| `routes_devops.py` (optional) | Replace `setup_k8s` action with call to `k8s_ops.generate_k8s_wizard()` |

**3 files for backend additions. 1 file for frontend rewrite.**

---

## 12. KEY EDGE CASES

| Scenario | Handling |
|----------|---------|
| No Docker configured | Show "Set up Docker first →" with link to Docker wizard |
| Docker configured but no compose | Fall back to module-based detection (like Docker wizard does) |
| Compose exists but no services | Show "Your compose file has no services defined" |
| No project modules defined | "Configure modules in Settings first" |
| All modules are libraries | "No deployable modules found" with manual fallback |
| Only infrastructure services in compose (postgres-only) | Show them, no application deployments |
| Existing K8s manifests found | Show warning: "Existing manifests detected. Overwrite?" per file |
| kubectl not installed | Allow generation, disable "apply to cluster" |
| No cluster connected | Allow generation + write, disable apply |
| Single module = single container | Suggest root-level k8s/ dir |
| Multiple modules = microservices | Per-service manifests |
| Helm chart already exists | "Customize values.yaml instead?" |
| Kustomize already set up | "Generate overlay for new environment?" |
| Port conflicts | Validation error listing conflicting services |
| No GitHub repo | Use local image names (no ghcr.io prefix) |
| No .env file | Skip ConfigMap generation |

---

## 13. EXISTING BACKEND CAPABILITIES NOT USED BY CURRENT WIZARD

The `k8s_ops.py` backend is **massively underutilized**. The current wizard uses NONE of these:

| Capability | Backend function | Should be used in |
|-----------|-----------------|-------------------|
| Rich manifest detection | `k8s_status()` | Detect step (resource_summary, manifest list) |
| Resource summary chips | `resource_summary` dict | Detect step |
| Manifest validation | `validate_manifests()` | After apply (verify generation) |
| Cluster status + nodes | `cluster_status()` | Detect step (connected, context, nodes) |
| Resource listing | `get_resources()` | After apply (show running pods) |
| Wizard manifest generation | `generate_k8s_wizard()` | Preview step — supports arbitrary resource list |
| Template-based generation | `generate_manifests()` | Preview step — includes health checks, limits, security |
| Apply manifests | `k8s_apply()` | Apply step |
| Pod logs | `k8s_pod_logs()` | Post-apply verification |
| Namespace listing | `k8s_namespaces()` | Configure step (namespace dropdown with live options) |
| Env-namespace mapping | `k8s_env_namespaces()` | Configure step (multi-env strategy) |
| Helm list/install/template | `helm_*()` | Helm path (if chart detected) |
| Skaffold detection | `skaffold_status()` | Detect step |

---

## 14. WHAT I WILL NOT DO

- **No new k8s_ops functions.** The backend already has everything.
- **No new UI components.** Reuse wizard patterns (wizSection, wizFormGrid, wizStatusRow, expandable cards).
- **No changes to the K8s card.** It's already well-built.
- **No `setup_k8s` action.** The new wizard will use `POST /k8s/generate/wizard` + write.
- **No inventing features.** Every feature comes from the master plan spec or existing backend capability.

---

## 15. UX ANALYSIS — THE FULL OPERABILITY SPECTRUM

### 15.1 THE EXISTING UI PATTERN LIBRARY

The project has a mature, consistent UI pattern library. K8s wizard MUST use these — no ad-hoc HTML:

| Pattern | Function | Used by |
|---------|----------|---------|
| `wizardModalOpen({title, size, steps, onComplete, ...})` | Multi-step modal shell | Git, Docker, CI/CD, K8s, Terraform, GitHub |
| `wizSection(title, subtitle)` | Section header in step body | Every wizard |
| `wizStatusRow(icon, label, value, type)` | Status detection row (icon + label + badge) | Detect steps |
| `wizFormGrid([fields])` | Form grid using `modalFormField()` | Configure steps |
| `modalFormField({name, label, type, value, options, ...})` | Input/select/checkbox/textarea field | All configure steps |
| `mfVal(name)` | Read field value by `mf-{name}` ID convention | All collect callbacks |
| `_mfRaw(label, inputHtml)` | Lightweight inline label+input (no mf- prefix) | K8s generate modal, wizard |
| `_wizDetectBanner(cacheKey)` | Cache age + Re-scan button | All detect steps |
| `modalPreview(title, content, id)` | Preview panel (read-only pre block) | K8s card generate modal |
| `cardSetupBanner(icon, title, desc, wizKey, btnLabel)` | Setup CTA banner on card | Cards when missing |
| `cardDepHint(depKey, depLabel, message, wizKey)` | Cross-integration dependency hint | K8s→Docker, CI→Git |
| `cardStatusGrid(stats)` | Grid of status stat chips | All cards |
| `cardDetectionList(items)` | Clickable detection items (icon+label+value) | K8s, CI/CD cards |
| `cardLivePanel(panelId, tabs, onTabClick)` | Tabbed live data panel | K8s card (9 tabs) |
| `cardActionToolbar(actions)` | Action button row | K8s card (7 actions) |
| `cardGenerateToolbar(items)` | Generate button row | K8s, Docker cards |
| `cardCrossLink(targetTab, label)` | Cross-tab navigation link | K8s→DevOps |
| `wizStore(key, data, ts)` / `wizCached(key)` / `wizInvalidate(key)` | Step-level cache | All detect steps |
| `<details>` / `<summary>` | Collapsible sections for advanced settings | Docker wizard per-module |

### 15.2 THE DOCKER WIZARD AS THE BLUEPRINT

The Docker wizard is the gold standard for K8s. Same pattern:

```
Docker Wizard Flow:
────────────────────

Step 1 — DETECT (cacheable, async, read-only)
├── API call: /wizard/detect (cached, one-stop-shop)
├── Show: Docker Engine status, Compose status, Dockerfile, .dockerignore
├── Show: Project modules classified (deployable / library / docs / ops-tool)
├── Store: data._docker, data._dockerStatus, data._modules, data._classified
└── UX: read-only scan → "Configure →" nudge

Step 2 — CONFIGURE (sync render, no API)
├── Section A: "Compose Project" — global settings (project name, platform)
├── Section B: "Containers" — per-module expandable cards
│   ├── Checkbox: include/exclude per module
│   ├── Primary: base image (select), port, Dockerfile path, restart policy
│   ├── <details> Dockerfile Settings: workdir, install, build, entrypoint, CMD, expose
│   └── <details> Compose Settings: container name, healthcheck, build args,
│                                     networks, environment, volumes, depends_on
├── Section C: "Infrastructure Services" — categorized infra catalog
│   ├── Collapsible categories (db-rel, db-nosql, cache, mq, search, proxy, ...)
│   ├── Per-service: checkbox + inline config panel (image, ports, env, volumes)
│   └── 40+ infrastructure services with rich defaults
├── Section D: "Generation Options" — checkboxes for compose, dockerignore
├── collect(): Reads all form inputs into data._selectedContainers, data._selectedInfra
└── validate(): Port conflicts, at least one selection

Step 3 — PREVIEW (async, calls backend to generate)
├── API calls: /docker/generate/{dockerfile,dockerignore,compose-wizard}
├── Show: Editable textareas per generated file (Dockerfiles, compose, .dockerignore)
│   ├── <details open> with path header + "create" badge
│   └── Full content in editable <textarea>
├── collect(): Captures user edits from textareas back into data._generatedFiles
├── Show: File count summary
└── Show: Next integration CTA → "Set up CI/CD →"

onComplete — APPLY (async, writes to disk)
├── Iterates data._generatedFiles
├── Calls POST /docker/generate/write per file
├── Shows results
├── Invalidates card cache: cardInvalidate('docker')
└── Resets project status: _projectStatusTS = 0
```

### 15.3 K8S CARD — THE OPERABILITY ENDPOINT

The K8s card is where the wizard DELIVERS its results. Understanding what the card already does
is critical — the wizard's output must feed this:

```
K8s Card States:
─────────────────

STATE A: No kubectl → error badge
├── cardSetupBanner → "kubectl not found"
├── cardEmpty → install link
└── cardGenerateToolbar → [K8s Manifests] [K8s Wizard] — still accessible!

STATE B: kubectl but no manifests → degraded badge
├── cardSetupBanner → "No K8s manifests" + "Set up K8s →"
├── cardDepHint → "Docker" dependency
├── cardStatusGrid → kubectl version, "Manifests: None"
└── cardGenerateToolbar → [K8s Manifests] [K8s Wizard]

STATE C: kubectl + manifests → ok badge (full operability mode)
├── cardStatusGrid → kubectl version, resource count, Helm, Kustomize
├── cardDetectionList → manifest dirs, Helm charts, Kustomize paths (clickable → editor)
├── Resource summary chips → {Deployment: 2, Service: 2, Ingress: 1, ...}
├── cardLivePanel → 9 TABS:
│   ├── 🫛 Pods        → live pod list with status dots
│   ├── 🔗 Services    → live service list
│   ├── 📦 Deploys     → live deployment list
│   ├── 🖥 Cluster     → context, nodes, namespaces
│   ├── 📣 Events      → recent cluster events
│   ├── 🏢 Namespaces  → namespace list with status
│   ├── ⎈ Helm         → releases list (click → show values)
│   ├── 🛤 Skaffold    → config detection + profiles
│   └── 🗺 Env Map     → environment → namespace mapping (click → overlay/values)
├── cardActionToolbar → 7 ACTIONS:
│   ├── ✅ Validate    → /k8s/validate → inline output (errors/warnings)
│   ├── 🚀 Apply       → modal: path + namespace → /k8s/apply
│   ├── ⚖️ Scale       → modal: deployment + replicas → /k8s/scale
│   ├── 📜 Logs        → modal: pod + namespace + tail → /k8s/pod-logs
│   ├── 🔍 Describe    → modal: kind + name → /k8s/describe
│   ├── 🗑 Delete      → modal: kind + name + confirm → /k8s/delete
│   └── ⎈ Helm         → modal: release + chart + namespace + values → /k8s/helm
├── cardGenerateToolbar → [K8s Manifests] [K8s Wizard]
└── cardCrossLink → "View K8s ops in DevOps →"
```

**Key insight**: The wizard's job is to move the card from STATE B → STATE C.
But there's more: after generation, the user should be offered the card's full operational
capabilities inline — not just "success, close dialog."

### 15.4 THE FULL LIFECYCLE: WIZARD → CARD → OPERATIONS

```
╔═════════════════════════════════════════════════════════════════╗
║  1. DISCOVER  →  2. CONFIGURE  →  3. PREVIEW  →  4. APPLY     ║
╚═════════════════════════════════════════════════════════════════╝
       │                 │                │              │
       ▼                 ▼                ▼              ▼
  Read Docker        Smart defaults    Generate YAML   Write files
  Read K8s status    User adjusts      User edits      Validate
  Read modules       Per-service cfg   Show diffs      Apply to cluster
  Read GH repo       Infra decisions                   Next steps CTAs
  Read environments  Namespace/Ingress
                                                        │
                                                        ▼
╔═════════════════════════════════════════════════════════════════╗
║  5. OPERATE (card)                                             ║
║  Live pods │ Services │ Deploys │ Events │ Logs │ Scale │ Helm ║
╚═════════════════════════════════════════════════════════════════╝
```

After wizard completes:
- `cardInvalidate('k8s')` → card reloads with new manifests detected
- Card moves to STATE C (full ops mode)
- User can immediately validate, apply to cluster, check pods

### 15.5 CROSS-INTEGRATION CTA MAP

| Wizard step | CTA shown | When | Action |
|-------------|-----------|------|--------|
| Detect | "Set up Docker first →" | No Docker configured | `wizardModalClose(); openDockerSetupWizard()` |
| Detect | "Connect GitHub for image naming →" | No GH remote | `wizardModalClose(); openGitHubSetupWizard()` |
| Configure | "→ Terraform" for infra services | User picks "Managed service" | CTA link to Terraform wizard |
| Preview | "Set up CI/CD →" | Always | Next integration CTA |
| Preview | "Validate manifests" | Always | Inline validation |
| Apply success | "View in Content Vault →" | Files written | `openFileInEditor('k8s/...')` |
| Apply success | "Apply to cluster →" | Cluster connected | Inline apply |

### 15.6 UX DETAILS — READ-ONLY SCAN BANNER

Same pattern as Git/GitHub wizards. The detect step shows a banner:

```html
<div style="...info-banner...">
    <span>🔍</span>
    <span>This is a <strong>read-only scan</strong>. To configure K8s resources, proceed to Configure.</span>
    <button onclick="document.getElementById('wiz-btn-next')?.click()">Configure →</button>
</div>
```

### 15.7 UX DETAILS — PER-SERVICE EXPANDABLE CARDS (Configure Step)

Following the Docker wizard's per-module card pattern exactly:

```
┌─ ☑ api ──── python-flask ──── src/ui/web ── 🟢 deployable ─────┐
│                                                                  │
│  Image      [ghcr.io/cyberpunk042/devops-control-plane-api:latest]
│  Port       [8000]  ← from compose     Replicas  [2]            │
│  Service    [ClusterIP ▾]               Strategy  [RollingUpdate ▾]
│                                                                  │
│  ▸ Resource Limits                    ← <details> collapsible    │
│    CPU:   request [100m]  limit [500m]                           │
│    Memory: request [128Mi]  limit [256Mi]                        │
│                                                                  │
│  ▸ Health Checks                      ← <details> collapsible   │
│    HTTP path [/health]  Port [8000]                              │
│    Liveness delay  [10s]  Readiness delay [5s]                   │
│                                                                  │
│  ▸ Environment (from compose)         ← <details> collapsible   │
│    DATABASE_URL = [postgresql://...]                             │
│    SECRET_KEY = [***]                                            │
│                                                                  │
│  ▸ Volume Mounts                      ← <details> if any        │
│    ☑ ./data → /app/data                                         │
└──────────────────────────────────────────────────────────────────┘
```

Note the `<details>/<summary>` pattern from the Docker wizard — this keeps the configure step
compact while allowing deep configuration. Primary fields are always visible; advanced settings
are collapsed.

### 15.8 UX DETAILS — INFRASTRUCTURE SERVICE DECISION

This is unique to K8s and doesn't exist in Docker. For each detected infra service:

```
┌─ postgres (postgres:16-alpine) ─────── from compose ───────────┐
│                                                                 │
│  ○ StatefulSet (self-managed in cluster)                        │
│    └── Port [5432]  Storage [10Gi]  PVC name [pgdata]           │
│    └── Env: POSTGRES_DB=[app]  POSTGRES_USER=[app]              │
│                                                                 │
│  ○ Managed service                                              │
│    └── 💡 → Set up Terraform to provision RDS/CloudSQL          │
│                                                                 │
│  ● Skip (not needed in K8s)                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

Radio group with inline config reveal (same as Docker's checkbox → config panel pattern):
- When "StatefulSet" selected → show PVC config
- When "Managed service" selected → show Terraform CTA
- When "Skip" selected → nothing

### 15.9 UX DETAILS — CLUSTER & NAMESPACE SECTION

This is a shared section, not per-service. It uses `wizFormGrid()`:

```
Cluster Configuration
─────────────────────

Namespace     [default ▾]        ← select with live namespaces from /k8s/namespaces
                                   + "custom" option → text input

☐ Create separate namespace per environment
  └── (reveals when checked):
      development  →  [devops-control-plane-development]   ← from /k8s/env-namespaces
      production   →  [devops-control-plane-production]

Ingress       ☐ Generate Ingress manifest
  └── (reveals when checked):
      Services with external access:
        ☑ api    host: [api.example.com]
        ☑ web    host: [example.com]
      Controller: [nginx-ingress ▾]       ← nginx, traefik, other
      TLS:        ☐ Include TLS section

Output Format ● Raw manifests in k8s/
              ○ Helm chart scaffold
              ○ Kustomize overlay
```

### 15.10 UX DETAILS — PREVIEW STEP (Editable Textareas)

Exactly following the Docker wizard pattern. Each file gets a collapsible `<details>` with
an editable `<textarea>`:

```
File Preview
────────────
Review and edit the generated files before writing to disk.

▾ 📄 k8s/api-deployment.yaml           api ← compose     [create]
  ┌────────────────────────────────────────────────────────────┐
  │ apiVersion: apps/v1                                        │ ← editable textarea
  │ kind: Deployment                                           │
  │ metadata:                                                  │
  │   name: api                                                │
  │   namespace: default                                       │
  │ ...                                                        │
  └────────────────────────────────────────────────────────────┘

▸ 📄 k8s/api-service.yaml              ClusterIP :8000    [create]
▾ 📄 k8s/web-deployment.yaml           web ← compose      [create]
  ┌────────────────────────────────────────────────────────────┐
  │ ...                                                        │
  └────────────────────────────────────────────────────────────┘
▸ 📄 k8s/web-service.yaml              ClusterIP :3000    [create]
▸ 📄 k8s/ingress.yaml                  2 hosts            [create]
▸ 📄 k8s/config.yaml                   ConfigMap          [create]
▸ 📄 k8s/namespace.yaml                production         [create]

✏️ 7 files generated — edit content above if needed, then click Apply.

💡 Next: Set up CI/CD to automate builds and deployments.
   [Set up CI/CD →]
```

### 15.11 UX DETAILS — USER EDITS ARE CAPTURED

The Docker wizard's `collect()` on the preview step captures user edits:
```javascript
collect: (data) => {
    for (let i = 0; i < data._generatedFiles.length; i++) {
        const ta = document.getElementById(`dk-preview-${i}`);
        if (ta) data._generatedFiles[i].content = ta.value;
    }
}
```

K8s wizard does the same — any manual edits to the preview textareas are what gets written.

### 15.12 UX DETAILS — ON COMPLETE (APPLY)

Following Docker wizard pattern, with K8s-specific additions:

```javascript
onComplete: async (data) => {
    const files = data._generatedFiles || [];
    if (files.length === 0) return;

    // Write files
    for (const file of files) {
        await api('/docker/generate/write', {
            method: 'POST', body: JSON.stringify({ file })
        });
    }

    // Invalidate caches
    _projectStatusTS = 0;
    cardInvalidate('k8s');

    // Optional: validate generated manifests
    try {
        const validation = await api('/k8s/validate');
        if (validation.errors > 0) {
            toast(`⚠ ${validation.errors} validation issue(s) — check the K8s card`, 'warning');
        }
    } catch {}
}
```

After completion:
- K8s card reloads → now shows manifests, resource chips, full ops panel
- User can immediately: Validate, Apply to cluster, View pods, etc.

### 15.13 THE WIZARD IS NOT THE ONLY TOOL

The K8s card ALSO has two existing modals that remain useful POST-wizard:

**`_k8sGenerateModal()`** — Quick single-resource generator
- Simple form: name, image, port, replicas, service type, namespace
- Preview + write
- For quick additions AFTER initial setup

**`_k8sWizardModal()`** — Multi-resource wizard (existing, minimal)
- Tab-based resource builder (add/remove resources)
- Supports all kinds: Deployment, Service, ConfigMap, Ingress, StatefulSet, etc.
- For ad-hoc resource creation

Both remain accessible from `cardGenerateToolbar` even after setup wizard runs.
The setup wizard is for initial comprehensive setup; these are for incremental additions.

---

## 16. DATA FLOW DIAGRAM — DETECT STEP

```
                    ┌──────────────────────────────────┐
                    │     GET /wizard/detect            │
                    │     (cached, one-stop-shop)       │
                    └────────────┬─────────────────────┘
                                 │
        ┌────────────────────────┼──────────────────────────┐
        ▼                        ▼                          ▼
  status_probes              docker_status              config_data
  ├─ k8s:                    ├─ available               ├─ modules:
  │  ├─ has_kubectl          ├─ version                 │  ├─ name
  │  ├─ has_helm             ├─ compose_available       │  ├─ path
  │  ├─ cluster_connected    ├─ compose_services[]      │  ├─ stack
  │  ├─ manifest_count       ├─ compose_service_details[] ← NEW │  ├─ domain  ← ADD
  │  ├─ has_chart            └─ dockerfiles[]           │  └─ description ← ADD
  │  └─ has_kustomize                                   └─ environments:
  ├─ docker:                                               ├─ name
  │  ├─ has_dockerfile                                     └─ default
  │  ├─ has_compose
  │  └─ has_dockerignore
  └─ ...

        ┌──────────────────────────────────┐
        │     GET /k8s/status              │ ← ADDITIONAL call in detect
        │     (detailed K8s scan)          │
        └────────────┬─────────────────────┘
                     │
                     ▼
              ├─ has_k8s
              ├─ kubectl{available, version}
              ├─ manifest_dirs[]
              ├─ total_resources
              ├─ resource_summary{Deployment: N, Service: N, ...}
              ├─ helm_charts[{name, path}]
              ├─ kustomize{exists, path}
              └─ skaffold(detected via separate call)

        ┌──────────────────────────────────┐
        │     GET /k8s/env-namespaces      │ ← ADDITIONAL call if multi-env
        │     (env→namespace mapping)      │
        └────────────┬─────────────────────┘
                     │
                     ▼
              environments:
              ├─ {name, namespace, has_overlay, values_file, default}
              └─ ...
```

### Key: What gets stored on `data` for subsequent steps

```javascript
data._k8s               // status_probes.k8s (kubectl, helm, cluster, manifests)
data._k8sStatus         // /k8s/status (full scan: resource_summary, helm, kustomize)
data._docker             // status_probes.docker (has_dockerfile, has_compose)
data._dockerStatus       // docker_status (full: version, compose, services)
data._composeServices    // compose_service_details[] ← NEW: full service specs
data._modules            // config_data.modules (with domain + description)
data._classified         // modules classified as deployable / infra / library
data._ghRepo             // gh_repo_info (owner, name → for image naming)
data._envNamespaces      // /k8s/env-namespaces (env→namespace mapping)
data._envs               // config_data.environments (from project.yml)
```

---

## 17. IMPLEMENTATION ORDER

This is a big wizard. The implementation should be phased:

### Phase 1: Foundation (backend + detect step) ✅ DONE
- ✅ Backend: `_parse_compose_service_details()` in `docker_ops.py`
  - Handles all compose format variations (ports, env, build, volumes, healthcheck, deploy.resources)
  - 3 helper functions: `_env_list_to_dict()`, `_normalise_ports()`, `_long_volume_to_str()`
- ✅ Backend: Add `compose_service_details` to `docker_status()` return
- ✅ Backend: Add `domain`, `description` to `_wizard_config_data()`, `default` for envs
- ✅ Frontend: Rewrite detect step in `openK8sSetupWizard()` with Docker context, K8s status,
  module classification, read-only banner, cross-integration CTAs
  - 4 helper functions: `_k8sModClass`, `_k8sSvcClass`, `_k8sImageName`, `_k8sPrimaryPort`
  - 5 display sections: K8s env, Docker context, Compose services, Registry, Environments

### Phase 2: Configure Step ✅ DONE
- ✅ Section A: Application service cards (from compose services or modules)
  - Per-service expandable card with checkbox, image, port, replicas, service type
  - Collapsed `<details>`: healthcheck, resource limits, env vars, volumes, dependencies
  - 3 rendering paths: compose-based, module-based, manual fallback
- ✅ Section B: Infrastructure service decisions (StatefulSet vs managed vs skip)
  - Radio group per infra service with image/port/volume context
- ✅ Section C: Cluster settings (namespace from env defaults, output dir, ingress, configmap)
- ✅ collect(): Full multi-service data collection into `data._services` + `data._infraDecisions`
  - Backward-compatible flat fields (`data.app_name`, `data.image`, etc.) for current backend
- ✅ validate(): At least one service, all images non-empty
- ✅ Review step: Updated to show all configured services + infra decisions
  - Multi-service awareness note when >1 service
  - CI/CD next-step CTA preserved

### Phase 3: Preview Step
- async render calling `POST /k8s/generate/wizard` with built resource list
- Editable textarea per file in collapsible `<details>` blocks
- collect() capturing user edits
- Next integration CTA ("Set up CI/CD →")

### Phase 4: onComplete
- Write files via `/docker/generate/write`
- Validate via `/k8s/validate` (non-blocking toast)
- Invalidate card cache
- Success toast + card refresh

### Phase 5: Edge Cases & Polish
- No-Docker fallback (module-based mode, like Docker wizard's manual mode)
- Existing manifest handling (overwrite checkbox, "exists — skipped" badges)
- Helm chart scaffold path (if Helm detected)
- Kustomize overlay path (if Kustomize detected)
- No cluster connected → allow generate but disable apply CTA
