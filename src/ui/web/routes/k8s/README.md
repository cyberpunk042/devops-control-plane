# K8s Routes — Kubernetes Manifest Detection, Cluster Operations, Helm & Wizard API

> **8 files · 395 lines · 24 endpoints · Blueprint: `k8s_bp` · Prefix: `/api`**
>
> Seven sub-domains under a single blueprint:
>
> 1. **Detection** — offline YAML/Helm/Kustomize scanning, kubectl availability,
>    manifest inventory (2 endpoints)
> 2. **Cluster queries** — connection status, resources, pod logs, events,
>    describe, namespaces, storage classes, env-namespace mapping (8 endpoints)
> 3. **Cluster mutations** — apply manifests, delete resources, scale workloads
>    (3 endpoints)
> 4. **Helm** — list releases, get values, install, upgrade, template render
>    (5 endpoints)
> 5. **Generation** — manifest templates from parameters, wizard-based
>    generation from resource definitions (2 endpoints)
> 6. **Wizard state** — load, save, wipe wizard configuration (3 endpoints,
>    same path with GET/POST/DELETE)
> 7. **Skaffold** — Skaffold config detection (1 endpoint)
>
> All delegate through `k8s_ops.py` (re-export shim) to a massive
> core service package: `core/services/k8s/` (8,608 lines across 18 modules).

---

## How It Works

### Request Flow

```
Frontend
│
├── devops/_k8s.html ────────────── K8s DevOps card
│   ├── GET  /api/k8s/status        (cached)
│   └── GET  /api/k8s/validate
│
├── integrations/_k8s.html ──────── K8s integrations panel
│   ├── GET  /api/k8s/cluster
│   ├── GET  /api/k8s/resources
│   ├── GET  /api/k8s/pod-logs
│   ├── GET  /api/k8s/events
│   ├── GET  /api/k8s/describe
│   ├── GET  /api/k8s/namespaces
│   ├── GET  /api/k8s/storageclasses
│   ├── GET  /api/k8s/env-namespaces
│   ├── POST /api/k8s/apply
│   ├── POST /api/k8s/delete
│   └── POST /api/k8s/scale
│
├── k8s_wizard/ ─────────────────── K8s wizard scripts
│   ├── GET  /api/k8s/helm/list
│   ├── GET  /api/k8s/helm/values
│   ├── POST /api/k8s/helm/install
│   ├── POST /api/k8s/helm/upgrade
│   ├── POST /api/k8s/helm/template
│   ├── POST /api/k8s/generate/manifests
│   ├── POST /api/k8s/generate/wizard
│   ├── GET  /api/k8s/wizard-state
│   ├── POST /api/k8s/wizard-state
│   ├── DEL  /api/k8s/wizard-state
│   └── GET  /api/k8s/skaffold/status
│
└── wizard/_integration_actions.html
    └── GET  /api/k8s/status
     │
     ▼
routes/k8s/                            ← HTTP layer (this package)
├── __init__.py   — blueprint definition
├── detect.py     — detection + validation
├── cluster.py    — cluster queries
├── actions.py    — cluster mutations
├── helm.py       — Helm operations
├── generate.py   — manifest generation
├── wizard.py     — wizard state CRUD
└── skaffold.py   — Skaffold detection
     │
     ▼
core/services/k8s/  (8,608 lines)      ← Business logic
├── common.py        (109 lines) — _run_kubectl, constants
├── detect.py        (641 lines) — YAML/Helm/Kustomize scanning
├── cluster.py       (472 lines) — kubectl interactions
├── helm.py          (176 lines) — Helm CLI operations
├── generate.py      (197 lines) — manifest templates
├── pod_builder.py   (559 lines) — probes, volumes, env, mesh
├── wizard.py        (565 lines) — wizard state + generation
├── wizard_detect.py (186 lines) — Skaffold, namespace mapping
├── wizard_generate.py (1012 lines) — full wizard manifest generation
├── helm_generate.py (514 lines) — Helm chart directory generation
├── validate.py      (151 lines) — 7-layer validation orchestrator
├── validate_structural.py   (321 lines)
├── validate_security.py     (290 lines)
├── validate_cluster.py      (229 lines)
├── validate_cross_resource.py (405 lines)
├── validate_cross_domain.py (1289 lines)
├── validate_env_aware.py    (245 lines)
└── validate_strategy.py     (1156 lines)
```

### Manifest Detection Pipeline (Cached)

```
GET /api/k8s/status?bust=1
     │
     ▼
devops_cache.get_cached(root, "k8s", lambda: k8s_ops.k8s_status(root))
     │
     ├── Cache HIT → return cached status
     └── Cache MISS → k8s_status(root)
         │
         ├── 1. Scan for YAML files:
         │   _collect_yaml_files(root)
         │   Directories: k8s/, kubernetes/, manifests/, deploy/, charts/
         │   Extensions: *.yml, *.yaml
         │   Skip: .terraform, node_modules, __pycache__, .git
         │   Parse each with _parse_k8s_yaml() → extract kind, name, apiVersion
         │
         ├── 2. Detect Helm charts:
         │   _detect_helm_charts(root)
         │   Look for Chart.yaml files → parse chart name, version
         │
         ├── 3. Detect Kustomize:
         │   _detect_kustomize(root)
         │   Look for kustomization.yaml / kustomize.yaml
         │
         ├── 4. Check tool availability:
         │   shutil.which("kubectl") → kubectl_available
         │   shutil.which("helm")    → helm_available
         │   shutil.which("skaffold") → skaffold_available
         │
         └── Return:
             {
                 manifests: [{kind, name, file, apiVersion}, ...],
                 manifest_count, helm_charts: [...],
                 kustomize_found, kubectl_available,
                 helm_available, skaffold_available,
                 has_k8s: (manifest_count > 0 or helm found)
             }
```

### Manifest Validation Pipeline

```
GET /api/k8s/validate
     │
     ▼
k8s_ops.validate_manifests(root)
     │
     ├── 7-layer validation:
     │   ├── Layer 1: Structural validation
     │   │   Missing required fields, unknown kinds, apiVersion format
     │   │
     │   ├── Layer 2: Security validation
     │   │   runAsRoot, privileged, hostNetwork, capabilities
     │   │
     │   ├── Layer 3: Cluster validation
     │   │   (with live cluster) resource quota, namespace existence
     │   │
     │   ├── Layer 4: Cross-resource validation
     │   │   Service selectors match Deployment labels,
     │   │   ConfigMap/Secret references exist
     │   │
     │   ├── Layer 5: Cross-domain validation
     │   │   Ingress matches Service, PVC matches StorageClass
     │   │
     │   ├── Layer 6: Environment-aware validation
     │   │   Per-env overrides, namespace policy
     │   │
     │   └── Layer 7: Strategy validation
     │       Deployment strategy, resource limits, probe config
     │
     └── Return:
         { ok: true, issues: [{severity, message, file, line}, ...],
           issue_count, valid: bool }
```

### Cluster Query Pipeline

```
GET /api/k8s/cluster
     │
     ▼
k8s_ops.cluster_status()
     │
     └── kubectl cluster-info
         ├── Success → { connected: true, cluster: "...", version: "..." }
         └── Failure → { connected: false, error: "..." }

GET /api/k8s/resources?namespace=default&kind=pods
     │
     ▼
k8s_ops.get_resources(namespace="default", kind="pods")
     │
     └── kubectl get pods -n default -o json
         → parse items[] → [{name, namespace, status, ...}]

GET /api/k8s/pod-logs?pod=my-pod&namespace=default&tail=100&container=app
     │
     ▼
k8s_ops.k8s_pod_logs(namespace="default", pod="my-pod", tail=100, container="app")
     │
     └── kubectl logs my-pod -n default --tail=100 -c app
         → { ok: true, logs: "..." }

GET /api/k8s/events?namespace=default
     │
     ▼
k8s_ops.k8s_events(namespace="default")
     │
     └── kubectl get events -n default --sort-by=.lastTimestamp
         → { ok: true, events: [...] }

GET /api/k8s/describe?kind=deployment&name=web&namespace=default
     │
     ▼
k8s_ops.k8s_describe("deployment", "web", namespace="default")
     │
     └── kubectl describe deployment web -n default
         → { ok: true, output: "..." }

GET /api/k8s/namespaces
     │
     ▼
k8s_ops.k8s_namespaces()
     │
     └── kubectl get namespaces -o json
         → { ok: true, namespaces: ["default", "kube-system", ...] }

GET /api/k8s/storageclasses
     │
     ▼
k8s_ops.k8s_storage_classes()
     │
     └── kubectl get storageclasses -o json
         → { ok: true, classes: [{name, provisioner, default}, ...] }

GET /api/k8s/env-namespaces
     │
     ▼
k8s_ops.k8s_env_namespaces(root)
     │
     ├── Read project.yml → environments
     └── Map each env → namespace
         → { environments: [{name, namespace}, ...] }
```

### Cluster Mutation Pipeline

```
POST /api/k8s/apply  { path: "k8s/deployment.yaml", namespace: "production" }
     │
     ├── @run_tracked("deploy", "deploy:k8s")
     │
     ▼
k8s_ops.k8s_apply(root, "k8s/deployment.yaml", namespace="production")
     │
     └── kubectl apply -f k8s/deployment.yaml -n production
         → { ok: true, output: "..." }

POST /api/k8s/delete  { kind: "deployment", name: "web", namespace: "default" }
     │
     ├── @run_tracked("destroy", "destroy:k8s")
     │
     ▼
k8s_ops.k8s_delete_resource("deployment", "web", namespace="default")
     │
     └── kubectl delete deployment web -n default
         → { ok: true }

POST /api/k8s/scale  { name: "web", replicas: 5, namespace: "default", kind: "deployment" }
     │
     ├── @run_tracked("deploy", "deploy:k8s_scale")
     │
     ▼
k8s_ops.k8s_scale("web", 5, namespace="default", kind="deployment")
     │
     └── kubectl scale deployment/web --replicas=5 -n default
         → { ok: true }
```

### Helm Pipeline

```
GET /api/k8s/helm/list?namespace=default
     │
     ▼
k8s_ops.helm_list(root, namespace="default")
     │
     └── helm list -n default -o json
         → { releases: [{name, namespace, revision, status, chart}, ...] }

GET /api/k8s/helm/values?release=web&namespace=default
     │
     ▼
k8s_ops.helm_values(root, "web", namespace="default")
     │
     └── helm get values web -n default -o json
         → { ok: true, values: {...} }

POST /api/k8s/helm/install
     Body: { release: "web", chart: "nginx", namespace: "prod",
             values_file: "values.yaml", set_values: {"key": "val"}, dry_run: false }
     │
     ├── @run_tracked("install", "install:helm")
     │
     ▼
k8s_ops.helm_install(root, "web", "nginx", namespace="prod", ...)
     │
     └── helm install web nginx -n prod -f values.yaml --set key=val
         → { ok: true, output: "..." }

POST /api/k8s/helm/upgrade  (same shape as install)
     │
     ├── @run_tracked("deploy", "deploy:helm_upgrade")
     │
     ▼
k8s_ops.helm_upgrade(root, "web", "nginx", ...)
     │
     └── helm upgrade web nginx -n prod -f values.yaml --set key=val
         → { ok: true, output: "..." }

POST /api/k8s/helm/template
     Body: { release: "web", chart: "nginx", namespace: "prod", values_file: "values.yaml" }
     │
     ├── @run_tracked("plan", "plan:helm_template")
     │
     ▼
k8s_ops.helm_template(root, "web", "nginx", ...)
     │
     └── helm template web nginx -n prod -f values.yaml
         → { ok: true, output: "--- (rendered YAML) ---" }
```

### Manifest Generation Pipeline

```
POST /api/k8s/generate/manifests
     Body: { name: "web", image: "nginx:latest", port: 8080,
             replicas: 2, service_type: "ClusterIP", host: "", namespace: "default" }
     │
     ├── @run_tracked("generate", "generate:k8s_manifests")
     │
     ▼
k8s_ops.generate_manifests(root, "web", image="nginx:latest", ...)
     │
     ├── Generate Deployment YAML (pod_builder)
     │   ├── Probes (liveness, readiness)
     │   ├── Resource limits
     │   ├── Volume mounts
     │   ├── Environment variables
     │   └── Service mesh annotations
     │
     ├── Generate Service YAML
     ├── Generate Ingress YAML (if host provided)
     │
     └── Return:
         { ok: true, files: [{path, content}, ...] }

POST /api/k8s/generate/wizard
     Body: { resources: [{ kind: "Deployment", name: "web", ... }, ...] }
     │
     ├── @run_tracked("generate", "generate:k8s_wizard")
     │
     ▼
k8s_ops.generate_k8s_wizard(root, resources)
     │
     ├── wizard_state_to_resources() → normalize wizard definitions
     ├── For each resource:
     │   ├── Generate YAML from wizard resource definition
     │   ├── Use pod_builder for probes, limits, env
     │   └── Handle special resources (StatefulSet, CronJob, etc.)
     │
     └── Return:
         { ok: true, files: [{path, content, overwrite, reason}, ...] }
```

### Wizard State Pipeline (RESTful CRUD)

```
GET /api/k8s/wizard-state
     │
     ▼
k8s_ops.load_wizard_state(root)
     │
     └── Read .state/k8s-wizard.json
         → { ok: true, state: {...} } or { ok: true, state: null }

POST /api/k8s/wizard-state  { ...wizard form data... }
     │
     ▼
k8s_ops.save_wizard_state(root, data)
     │
     └── Write .state/k8s-wizard.json
         → { ok: true }

DELETE /api/k8s/wizard-state
     │
     ▼
k8s_ops.wipe_wizard_state(root)
     │
     └── Delete .state/k8s-wizard.json
         → { ok: true }
```

---

## File Map

```
routes/k8s/
├── __init__.py     23 lines — blueprint definition + 7 sub-module imports
├── detect.py       30 lines — 2 detection endpoints
├── cluster.py      88 lines — 8 cluster query endpoints
├── actions.py      57 lines — 3 mutation endpoints
├── helm.py         99 lines — 5 Helm endpoints
├── generate.py     49 lines — 2 generation endpoints
├── wizard.py       32 lines — 3 wizard state endpoints (same path, 3 methods)
├── skaffold.py     17 lines — 1 Skaffold endpoint
└── README.md                — this file
```

Core business logic: `core/services/k8s/` (8,608 lines across 18 modules).
Backward-compat shim: `core/services/k8s_ops.py` (10 lines, re-exports all).

---

## Per-File Documentation

### `__init__.py` — Blueprint Definition (23 lines)

```python
k8s_bp = Blueprint("k8s", __name__)

from . import detect, cluster, actions, helm, generate, wizard, skaffold
```

### `detect.py` — Detection Endpoints (30 lines)

| Function | Method | Route | Cached | What It Does |
|----------|--------|-------|--------|-------------|
| `k8s_status()` | GET | `/k8s/status` | ✅ `"k8s"` | Manifest + tool detection |
| `k8s_validate()` | GET | `/k8s/validate` | No | 7-layer manifest validation |

**Status uses lazy import + cache:**

```python
@k8s_bp.route("/k8s/status")
def k8s_status():
    from src.core.services.devops.cache import get_cached
    root = _project_root()
    force = request.args.get("bust", "") == "1"
    return jsonify(get_cached(root, "k8s", lambda: k8s_ops.k8s_status(root), force=force))
```

### `cluster.py` — Cluster Query Endpoints (88 lines)

| Function | Method | Route | Params | What It Does |
|----------|--------|-------|--------|-------------|
| `k8s_cluster()` | GET | `/k8s/cluster` | — | Connection status |
| `k8s_resources()` | GET | `/k8s/resources` | `namespace`, `kind` | List resources |
| `k8s_pod_logs()` | GET | `/k8s/pod-logs` | `pod`, `namespace`, `tail`, `container` | Pod log output |
| `k8s_events()` | GET | `/k8s/events` | `namespace` | Recent events |
| `k8s_describe()` | GET | `/k8s/describe` | `kind`, `name`, `namespace` | Describe resource |
| `k8s_namespaces()` | GET | `/k8s/namespaces` | — | List namespaces |
| `k8s_storage_classes()` | GET | `/k8s/storageclasses` | — | List StorageClasses |
| `k8s_env_namespaces()` | GET | `/k8s/env-namespaces` | — | Env → namespace mapping |

**All cluster queries use the same error pattern:**

```python
result = k8s_ops.k8s_events(namespace=ns)
if not result.get("ok"):
    return jsonify(result), 400
return jsonify(result)
```

### `actions.py` — Cluster Mutation Endpoints (57 lines)

| Function | Method | Route | Tracked | What It Does |
|----------|--------|-------|---------|-------------|
| `k8s_apply()` | POST | `/k8s/apply` | ✅ `deploy:k8s` | Apply manifests |
| `k8s_delete()` | POST | `/k8s/delete` | ✅ `destroy:k8s` | Delete resource |
| `k8s_scale()` | POST | `/k8s/scale` | ✅ `deploy:k8s_scale` | Scale workload |

**All mutations are tracked** — apply and scale under `deploy`,
delete under `destroy`.

### `helm.py` — Helm Endpoints (99 lines)

| Function | Method | Route | Tracked | What It Does |
|----------|--------|-------|---------|-------------|
| `helm_list()` | GET | `/k8s/helm/list` | No | List releases |
| `helm_values()` | GET | `/k8s/helm/values` | No | Get release values |
| `helm_install()` | POST | `/k8s/helm/install` | ✅ `install:helm` | Install chart |
| `helm_upgrade()` | POST | `/k8s/helm/upgrade` | ✅ `deploy:helm_upgrade` | Upgrade release |
| `helm_template()` | POST | `/k8s/helm/template` | ✅ `plan:helm_template` | Render templates |

**Install and upgrade share the same parameter shape:**

```python
result = k8s_ops.helm_install(
    _project_root(),
    release,              # release name
    chart,                # chart name or path
    namespace=data.get("namespace", ""),
    values_file=data.get("values_file", ""),
    set_values=data.get("set_values"),     # dict of --set values
    dry_run=data.get("dry_run", False),
)
```

### `generate.py` — Generation Endpoints (49 lines)

| Function | Method | Route | Tracked | What It Does |
|----------|--------|-------|---------|-------------|
| `k8s_generate_manifests()` | POST | `/k8s/generate/manifests` | ✅ `generate:k8s_manifests` | Basic manifest gen |
| `k8s_generate_wizard()` | POST | `/k8s/generate/wizard` | ✅ `generate:k8s_wizard` | Wizard resource gen |

**Two generation modes:**
- **Basic:** parameters (name, image, port, replicas) → Deployment + Service + optional Ingress
- **Wizard:** full resource definitions (list of complex objects) → complete manifest set

### `wizard.py` — Wizard State (32 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `k8s_wizard_state_load()` | GET | `/k8s/wizard-state` | Load saved state |
| `k8s_wizard_state_save()` | POST | `/k8s/wizard-state` | Persist state |
| `k8s_wizard_state_wipe()` | DELETE | `/k8s/wizard-state` | Delete state |

**Same path, three HTTP methods** — RESTful CRUD on a single resource:

```python
@k8s_bp.route("/k8s/wizard-state", methods=["GET"])
def k8s_wizard_state_load(): ...

@k8s_bp.route("/k8s/wizard-state", methods=["POST"])
def k8s_wizard_state_save(): ...

@k8s_bp.route("/k8s/wizard-state", methods=["DELETE"])
def k8s_wizard_state_wipe(): ...
```

### `skaffold.py` — Skaffold Status (17 lines)

| Function | Method | Route | What It Does |
|----------|--------|-------|-------------|
| `skaffold_status()` | GET | `/k8s/skaffold/status` | Detect Skaffold config |

---

## Dependency Graph

```
__init__.py
└── Imports: detect, cluster, actions, helm, generate, wizard, skaffold

detect.py
├── k8s_ops       ← k8s_status, validate_manifests (eager)
├── devops.cache  ← get_cached (lazy, inside handler)
└── helpers       ← project_root

cluster.py
├── k8s_ops       ← cluster_status, get_resources, k8s_pod_logs,
│                   k8s_events, k8s_describe, k8s_namespaces,
│                   k8s_storage_classes, k8s_env_namespaces (eager)
└── helpers       ← project_root

actions.py
├── k8s_ops       ← k8s_apply, k8s_delete_resource, k8s_scale (eager)
├── run_tracker   ← @run_tracked (eager)
└── helpers       ← project_root

helm.py
├── k8s_ops       ← helm_list, helm_values, helm_install,
│                   helm_upgrade, helm_template (eager)
├── run_tracker   ← @run_tracked (eager)
└── helpers       ← project_root

generate.py
├── k8s_ops       ← generate_manifests, generate_k8s_wizard (eager)
├── run_tracker   ← @run_tracked (eager)
└── helpers       ← project_root

wizard.py
├── k8s_ops       ← load_wizard_state, save_wizard_state, wipe_wizard_state (eager)
└── helpers       ← project_root

skaffold.py
├── k8s_ops       ← skaffold_status (eager)
└── helpers       ← project_root
```

---

## Consumers

| Layer | Module | What It Uses |
|-------|--------|-------------|
| Server | `ui/web/server.py` | Imports `k8s_bp`, registers at `/api` prefix |
| DevOps card | `scripts/devops/_k8s.html` | `/k8s/status` (cached), `/k8s/validate` |
| K8s panel | `scripts/integrations/_k8s.html` | `/k8s/cluster`, `/k8s/resources`, `/k8s/pod-logs`, `/k8s/events`, etc. |
| K8s wizard | `scripts/k8s_wizard/_raw_step2_cluster.html` | `/k8s/namespaces`, `/k8s/storageclasses`, `/k8s/env-namespaces` |
| K8s wizard | `scripts/k8s_wizard/_raw_step2_collectors.html` | `/k8s/helm/list`, `/k8s/skaffold/status` |
| K8s wizard | `scripts/k8s_wizard/_raw_step2_helpers.html` | `/k8s/wizard-state`, `/k8s/generate/wizard` |
| Setup wizard | `scripts/wizard/_integration_actions.html` | `/k8s/status` (detect K8s from wizard) |
| Cache | `devops/cache` compute registry | `"k8s"` key → `k8s_status(root)` |

---

## Data Shapes

### `GET /api/k8s/status` response

```json
{
    "manifests": [
        { "kind": "Deployment", "name": "web-app", "file": "k8s/deployment.yaml", "apiVersion": "apps/v1" },
        { "kind": "Service", "name": "web-app", "file": "k8s/service.yaml", "apiVersion": "v1" }
    ],
    "manifest_count": 2,
    "helm_charts": [
        { "name": "my-chart", "version": "1.0.0", "path": "charts/my-chart" }
    ],
    "kustomize_found": false,
    "kubectl_available": true,
    "helm_available": true,
    "skaffold_available": false,
    "has_k8s": true
}
```

### `GET /api/k8s/validate` response

```json
{
    "ok": true,
    "issues": [
        {
            "severity": "warning",
            "message": "Container 'web' runs as root (no securityContext.runAsNonRoot)",
            "file": "k8s/deployment.yaml",
            "line": 25
        },
        {
            "severity": "info",
            "message": "No resource limits set for container 'web'",
            "file": "k8s/deployment.yaml",
            "line": 30
        }
    ],
    "issue_count": 2,
    "valid": true
}
```

### `GET /api/k8s/cluster` response

```json
{
    "connected": true,
    "cluster": "kubernetes.docker.internal:6443",
    "version": "v1.28.2"
}
```

### `GET /api/k8s/resources?namespace=default&kind=pods` response

```json
{
    "ok": true,
    "resources": [
        {
            "name": "web-app-6d8f4b7c9-abc12",
            "namespace": "default",
            "status": "Running",
            "ready": "1/1",
            "restarts": 0,
            "age": "2d"
        }
    ]
}
```

### `GET /api/k8s/pod-logs?pod=web-app-6d8f4b7c9-abc12&tail=50` response

```json
{
    "ok": true,
    "logs": "2026-03-02 15:30:00 INFO Starting server on :8080\n2026-03-02 15:30:01 INFO Ready\n..."
}
```

### `GET /api/k8s/events?namespace=default` response

```json
{
    "ok": true,
    "events": [
        {
            "type": "Normal",
            "reason": "Scheduled",
            "message": "Successfully assigned default/web-app-... to node1",
            "object": "pod/web-app-6d8f4b7c9-abc12",
            "age": "5m"
        }
    ]
}
```

### `GET /api/k8s/namespaces` response

```json
{
    "ok": true,
    "namespaces": ["default", "kube-system", "kube-public", "production", "staging"]
}
```

### `GET /api/k8s/storageclasses` response

```json
{
    "ok": true,
    "classes": [
        { "name": "standard", "provisioner": "kubernetes.io/host-path", "default": true },
        { "name": "fast-ssd", "provisioner": "kubernetes.io/gce-pd", "default": false }
    ]
}
```

### `GET /api/k8s/env-namespaces` response

```json
{
    "environments": [
        { "name": "dev", "namespace": "dev" },
        { "name": "staging", "namespace": "staging" },
        { "name": "production", "namespace": "production" }
    ]
}
```

### `POST /api/k8s/apply` request + response

```json
// Request:
{ "path": "k8s/deployment.yaml", "namespace": "production" }

// Response:
{ "ok": true, "output": "deployment.apps/web-app configured" }
```

### `POST /api/k8s/delete` request + response

```json
// Request:
{ "kind": "deployment", "name": "web-app", "namespace": "default" }

// Response:
{ "ok": true }
```

### `POST /api/k8s/scale` request + response

```json
// Request:
{ "name": "web-app", "replicas": 5, "namespace": "default", "kind": "deployment" }

// Response:
{ "ok": true }
```

### `GET /api/k8s/helm/list?namespace=default` response

```json
{
    "releases": [
        {
            "name": "nginx-ingress",
            "namespace": "default",
            "revision": "3",
            "status": "deployed",
            "chart": "ingress-nginx-4.8.3"
        }
    ]
}
```

### `POST /api/k8s/helm/install` request + response

```json
// Request:
{
    "release": "web",
    "chart": "bitnami/nginx",
    "namespace": "production",
    "values_file": "values-prod.yaml",
    "set_values": { "replicaCount": "3" },
    "dry_run": false
}

// Response:
{ "ok": true, "output": "NAME: web\nLAST DEPLOYED: ...\nSTATUS: deployed" }
```

### `POST /api/k8s/helm/template` response

```json
{
    "ok": true,
    "output": "---\napiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web\n..."
}
```

### `POST /api/k8s/generate/manifests` request + response

```json
// Request:
{
    "name": "web-app",
    "image": "nginx:latest",
    "port": 8080,
    "replicas": 2,
    "service_type": "ClusterIP",
    "host": "web.example.com",
    "namespace": "production"
}

// Response:
{
    "ok": true,
    "files": [
        { "path": "k8s/deployment.yaml", "content": "apiVersion: apps/v1\nkind: Deployment\n..." },
        { "path": "k8s/service.yaml", "content": "apiVersion: v1\nkind: Service\n..." },
        { "path": "k8s/ingress.yaml", "content": "apiVersion: networking.k8s.io/v1\nkind: Ingress\n..." }
    ]
}
```

### `POST /api/k8s/generate/wizard` request + response

```json
// Request:
{
    "resources": [
        {
            "kind": "Deployment",
            "name": "api-server",
            "image": "my-api:v2",
            "port": 3000,
            "replicas": 3,
            "env": { "DATABASE_URL": "..." },
            "probes": { "liveness": "/healthz", "readiness": "/ready" }
        }
    ]
}

// Response:
{
    "ok": true,
    "files": [
        { "path": "k8s/api-server/deployment.yaml", "content": "...", "overwrite": false, "reason": "Generated from wizard" }
    ]
}
```

### `GET /api/k8s/wizard-state` response

```json
{
    "ok": true,
    "state": {
        "resources": [...],
        "namespace": "default",
        "created_at": "2026-03-01T10:00:00"
    }
}
```

### `GET /api/k8s/skaffold/status` response

```json
{
    "ok": true,
    "available": true,
    "config_found": true,
    "config_path": "skaffold.yaml"
}
```

---

## Advanced Feature Showcase

### 1. 7-Layer Manifest Validation

The `/k8s/validate` endpoint runs a comprehensive multi-layer
validation pipeline across 7 specialized validators:

```
validate_manifests(root)
├── validate_structural.py   — YAML structure, required fields
├── validate_security.py     — Security best practices
├── validate_cluster.py      — Live cluster compatibility
├── validate_cross_resource.py — Inter-resource references
├── validate_cross_domain.py — Cross-concern consistency
├── validate_env_aware.py    — Environment-specific rules
└── validate_strategy.py     — Deployment strategy analysis
```

Each layer adds issues without blocking subsequent layers.
The result aggregates all issues with severity and location.

### 2. Helm Install/Upgrade with --set Values

Both install and upgrade accept a `set_values` dict that maps
directly to Helm's `--set` flags:

```python
result = k8s_ops.helm_install(
    root, release, chart,
    set_values={"replicaCount": "3", "image.tag": "v2"},
    dry_run=True,  # preview only
)
# → helm install web chart --set replicaCount=3 --set image.tag=v2 --dry-run
```

### 3. RESTful Wizard State

The wizard state uses three HTTP methods on the same path
for a clean REST API:

```
GET    /k8s/wizard-state  → load
POST   /k8s/wizard-state  → save
DELETE /k8s/wizard-state  → wipe
```

State persists to `.state/k8s-wizard.json` so the wizard
survives page refreshes and server restarts.

### 4. Two Generation Strategies

- **Basic generation** (`/generate/manifests`): takes flat parameters
  (name, image, port, replicas) — suitable for quick deployment of
  simple services.
- **Wizard generation** (`/generate/wizard`): takes full resource
  definitions with probes, volumes, env vars, mesh annotations —
  powered by the 559-line `pod_builder.py` module.

### 5. Tracker Category Semantics

Actions are tracked with semantic categories:

```python
@run_tracked("deploy", "deploy:k8s")         # apply → deployment
@run_tracked("destroy", "destroy:k8s")        # delete → destruction
@run_tracked("deploy", "deploy:k8s_scale")    # scale → deployment
@run_tracked("install", "install:helm")        # first install
@run_tracked("deploy", "deploy:helm_upgrade")  # upgrade existing
@run_tracked("plan", "plan:helm_template")     # preview only
@run_tracked("generate", "generate:k8s_manifests")  # manifest creation
```

---

## Design Decisions

### Why offline detection and live cluster are separate

Detection (`/k8s/status`) scans files offline — no cluster needed.
Cluster queries (`/k8s/resources`, `/k8s/pod-logs`) require a live
connection. Separating them allows the DevOps dashboard to show
manifest info even when no cluster is connected.

### Why validation is GET not POST

Validation reads existing manifest files — it doesn't create or
modify anything. GET is semantically correct for idempotent
read-only operations, and it plays well with browser caching
and simple URL sharing.

### Why Helm endpoints live under /k8s/ not /helm/

Helm is a Kubernetes package manager. Everything it does operates
on K8s clusters. Grouping under `/k8s/helm/` keeps the namespace
consistent and reflects the domain hierarchy.

### Why wizard state uses DELETE not POST

RESTful convention: DELETE on a resource means "remove this resource."
Using POST with a `{"action": "wipe"}` body would work but
violates REST semantics. The DELETE method clearly communicates
the destructive intent.

### Why cluster queries don't use caching

Cluster state changes frequently (pods restart, events fire, logs
grow). Caching would show stale data. Only the detection endpoint
(offline file scanning) uses caching because manifest files change
far less frequently.

### Why generate produces file objects not direct writes

Both generation endpoints return `{ files: [{path, content}, ...] }`
instead of writing to disk. The frontend can preview the output
before confirming the write. This prevents accidental overwrites
and gives the user control over which files to create.

---

## Coverage Summary

| Capability | Endpoint | Method | Tracked | Cached |
|-----------|----------|--------|---------|--------|
| Manifest detection | `/k8s/status` | GET | No | ✅ `"k8s"` |
| Manifest validation | `/k8s/validate` | GET | No | No |
| Cluster status | `/k8s/cluster` | GET | No | No |
| List resources | `/k8s/resources` | GET | No | No |
| Pod logs | `/k8s/pod-logs` | GET | No | No |
| Events | `/k8s/events` | GET | No | No |
| Describe | `/k8s/describe` | GET | No | No |
| Namespaces | `/k8s/namespaces` | GET | No | No |
| StorageClasses | `/k8s/storageclasses` | GET | No | No |
| Env namespaces | `/k8s/env-namespaces` | GET | No | No |
| Apply manifest | `/k8s/apply` | POST | ✅ `deploy:k8s` | No |
| Delete resource | `/k8s/delete` | POST | ✅ `destroy:k8s` | No |
| Scale workload | `/k8s/scale` | POST | ✅ `deploy:k8s_scale` | No |
| Helm list | `/k8s/helm/list` | GET | No | No |
| Helm values | `/k8s/helm/values` | GET | No | No |
| Helm install | `/k8s/helm/install` | POST | ✅ `install:helm` | No |
| Helm upgrade | `/k8s/helm/upgrade` | POST | ✅ `deploy:helm_upgrade` | No |
| Helm template | `/k8s/helm/template` | POST | ✅ `plan:helm_template` | No |
| Generate manifests | `/k8s/generate/manifests` | POST | ✅ `generate:k8s_manifests` | No |
| Generate wizard | `/k8s/generate/wizard` | POST | ✅ `generate:k8s_wizard` | No |
| Load wizard state | `/k8s/wizard-state` | GET | No | No |
| Save wizard state | `/k8s/wizard-state` | POST | No | No |
| Wipe wizard state | `/k8s/wizard-state` | DELETE | No | No |
| Skaffold status | `/k8s/skaffold/status` | GET | No | No |
