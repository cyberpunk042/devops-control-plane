# CLI Domain: K8s — Kubernetes Manifests, Validation, Cluster & Generation

> **4 files · 338 lines · 5 commands + 1 subgroup · Group: `controlplane k8s`**
>
> Kubernetes integration: detect manifests and kubectl availability,
> validate manifests for structural issues and best practices, observe
> live cluster state (nodes, namespaces, resources), and generate
> Deployment/Service/Ingress manifests from parameters.
>
> Core service: `core/services/k8s/ops.py` (re-exported via `k8s_ops.py`)

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                         controlplane k8s                            │
│                                                                      │
│  ┌── Detect ──────────┐   ┌── Observe ──────┐   ┌── Generate ───┐  │
│  │ status             │   │ cluster         │   │ generate      │  │
│  │ validate           │   │ get KIND [-n NS]│   │  manifests    │  │
│  └────────────────────┘   └─────────────────┘   └──────────────-┘  │
└──────────┬──────────────────────┬──────────────────┬───────────────┘
           │                      │                  │
           ▼                      ▼                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                 core/services/k8s/ops.py (via k8s_ops.py)           │
│                                                                      │
│  Detection / Validation:                                             │
│    k8s_status(root)        → kubectl available, manifest dirs,      │
│                               resource_summary, manifests[],         │
│                               helm_charts[], kustomize              │
│    validate_manifests(root)→ ok, errors, warnings, issues[]         │
│                                                                      │
│  Observation (live cluster):                                         │
│    cluster_status()        → connected, context, nodes[], ns[]      │
│    get_resources(ns, kind) → ok, count, resources[] with phase      │
│                                                                      │
│  Generation:                                                         │
│    generate_manifests(root, app, image, port, replicas, ...)        │
│                            → files[] (Deployment, Service, Ingress) │
└──────────────────────────────────────────────────────────────────────┘
```

### Detect + Validate Pattern

Unlike most CLI domains, K8s has **two** detect-phase commands: `status`
and `validate`. This is because detection ("what manifests exist?") and
validation ("are they correct?") are distinct operations with different
output structures.

```
k8s status
├── kubectl check (version, availability)
├── Scan for manifest directories (k8s/, kubernetes/, deploy/)
├── Parse manifest files → resource summary (kind → count)
├── Detect Helm charts (Chart.yaml)
└── Detect Kustomize (kustomization.yaml)

k8s validate
├── Find all manifest files
├── For each manifest:
│   ├── Parse YAML structure
│   ├── Check required fields (apiVersion, kind, metadata)
│   ├── Check best practices (resource limits, probes)
│   └── Collect issues with severity (error, warning, info)
├── Summarize: ok, error count, warning count
└── Display: issues[:25] with severity icons
```

### Live Cluster Commands

The `cluster` and `get` commands differ from all other CLI commands
because they interact with a **live Kubernetes cluster** via kubectl,
not with files on disk:

```
k8s cluster          → kubectl cluster-info, nodes, namespaces
k8s get pods -n app  → kubectl get pods -n app
```

These commands do **not** receive `project_root` — they operate on
whichever cluster context is currently active.

### Multi-File Generation

The `generate manifests` command is unique: it produces **multiple
files** in one operation (Deployment + Service + optional Ingress
+ optional Namespace). It iterates over `result["files"]` rather
than handling a single `result["file"]`.

```
generate manifests myapp --image myapp:latest --port 8080 --host app.example.com
├── generate_manifests(root, "myapp", image=..., port=..., host=...)
│   └── Returns {files: [
│         {path: "k8s/deployment.yaml", content: ...},
│         {path: "k8s/service.yaml", content: ...},
│         {path: "k8s/ingress.yaml", content: ...}  (because --host set)
│       ]}
├── --write?
│   ├── Yes → write_generated_file for EACH file
│   └── No  → Preview ALL files + "(use --write to save files to disk)"
└── Error? → Show error + exit(1)
```

---

## Commands

### `controlplane k8s status`

Show K8s manifest status: kubectl, manifest dirs, resource summary, Helm, Kustomize.

```bash
controlplane k8s status
controlplane k8s status --json
```

**Output example:**

```
☸️  Kubernetes Status:

   🔧 kubectl: v1.28.3
   📁 Manifest dirs: k8s, deploy/k8s

   📦 Resources (12):
      ConfigMap: 2
      Deployment: 3
      Ingress: 1
      Service: 3
      ServiceAccount: 1
      HPA: 2

   📄 k8s/base.yaml (5 resources)
   📄 k8s/ingress.yaml (1 resources)
   📄 deploy/k8s/services.yaml (6 resources)

   ⎈ Helm Charts:
      myapp-chart v0.3.0 (charts/myapp/)

   🔧 Kustomize: k8s/kustomization.yaml
```

---

### `controlplane k8s validate`

Validate Kubernetes manifests for structure and best practices.

```bash
controlplane k8s validate
controlplane k8s validate --json
```

**Output examples:**

```
🔍 Validating manifests...
✅ All manifests valid (5 files)
```

```
🔍 Validating manifests...
❌ 2 error(s), 3 warning(s)

   ❌ [ERROR] k8s/deployment.yaml
      Missing required field: spec.template.spec.containers
   ⚠️  [WARNING] k8s/deployment.yaml
      No resource limits defined for container 'web'
   ℹ️  [INFO] k8s/service.yaml
      Consider adding health check annotations
```

**Issue display cap:** Shows at most 25 issues. If more exist, shows
`"... and N more"`.

---

### `controlplane k8s cluster`

Show cluster connection status, nodes, and namespaces.

```bash
controlplane k8s cluster
controlplane k8s cluster --json
```

**Output example:**

```
☸️  Cluster: minikube

   Nodes (1):
      ✅ minikube (control-plane) v1.28.3

   Namespaces: default, kube-system, kube-public, kube-node-lease
```

**Not connected:**

```
❌ Not connected to any cluster
   kubectl config error: no current context
```

**Namespace truncation:** Shows at most 15 namespaces. If more, shows
`"... and N more"`.

---

### `controlplane k8s get KIND`

Get resources from the cluster by kind and namespace.

```bash
controlplane k8s get pods
controlplane k8s get deployments -n production
controlplane k8s get services --json
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `KIND` | argument | `pods` | Resource kind to list |
| `-n` | string | `default` | Namespace |
| `--json` | flag | off | JSON output |

**Output example:**

```
☸️  pods in default (3):
   ✅ web-abc123 — Running
   ✅ worker-def456 — Running
   ⚠️  migrate-ghi789 — Pending
```

**Phase icons:** ✅ for Running/Succeeded/Active/Bound, ⚠️ for all
other phases (Pending, Failed, Unknown, CrashLoopBackOff, etc.).

---

### `controlplane k8s generate manifests APP`

Generate Deployment, Service, and optional Ingress/Namespace manifests.

```bash
# Basic generation
controlplane k8s generate manifests myapp --image myapp:latest

# Full options
controlplane k8s generate manifests myapp \
  --image myapp:latest \
  --port 3000 \
  --replicas 3 \
  --service-type LoadBalancer \
  --host app.example.com \
  --namespace production \
  --write
```

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `APP` | argument | (required) | Application name |
| `--image` | string | (empty) | Container image |
| `--port` | int | 8080 | Container port |
| `--replicas` | int | 2 | Replica count |
| `--service-type` | string | ClusterIP | Service type (ClusterIP, NodePort, LoadBalancer) |
| `--host` | string | (empty) | Ingress hostname (generates Ingress if set) |
| `--namespace` | string | (empty) | Namespace (generates Namespace if set) |
| `--write` | flag | off | Write files to disk |

**Conditional generation:** Ingress is only generated if `--host` is
provided. Namespace is only generated if `--namespace` is provided.
This keeps the base output minimal (Deployment + Service only).

---

## File Map

```
cli/k8s/
├── __init__.py     36 lines — group definition, _resolve_project_root,
│                              sub-module imports (detect, observe, generate)
├── detect.py      135 lines — status, validate commands
├── observe.py      92 lines — cluster, get commands
├── generate.py     75 lines — generate subgroup (manifests command)
└── README.md               — this file
```

**Total: 338 lines of Python across 4 files.**

---

## Per-File Documentation

### `__init__.py` — Group definition (36 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `_resolve_project_root(ctx)` | helper | Reads `config_path` from context, falls back to `find_project_file()` |
| `k8s()` | Click group | Top-level `k8s` group |
| `from . import detect, observe, generate` | import | Registers sub-modules |

---

### `detect.py` — Status + validation (135 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `status(ctx, as_json)` | command | kubectl version, manifest dirs, resource summary, Helm, Kustomize |
| `validate(ctx, as_json)` | command | Structural validation + best practice checks |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `k8s_status` | `k8s_ops` | Manifest detection + kubectl check |
| `validate_manifests` | `k8s_ops` | Manifest validation |

**Status display sections (6):**
1. kubectl availability + version
2. Manifest directories
3. Resource summary (kind → count, sorted alphabetically)
4. Per-manifest file listing (path + resource count)
5. Helm charts (name, version, path)
6. Kustomize detection (path)

**Validate severity hierarchy:**
- Error: structural problems (missing required fields)
- Warning: best practice violations (no resource limits)
- Info: suggestions (add annotations)

Each severity has both a color and an icon for dual visual encoding.

---

### `observe.py` — Cluster + resource listing (92 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `cluster(ctx, as_json)` | command | Cluster context, nodes with ready status, namespaces |
| `get_resources(ctx, kind, namespace, as_json)` | command (`get`) | List resources by kind from active cluster |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `cluster_status` | `k8s_ops` | Cluster connection + node/namespace listing |
| `get_resources` | `k8s_ops` | Resource listing by kind (aliased to `_get_resources`) |

**Note on client-side `project_root`:** Neither `cluster` nor `get`
passes `project_root` to the core service. These commands operate on
the live cluster (via kubeconfig), not on project files.

---

### `generate.py` — Manifest generation (75 lines)

| Symbol | Kind | What It Does |
|--------|------|-------------|
| `generate()` | Click group | `k8s generate` subgroup |
| `gen_manifests(ctx, app_name, image, port, replicas, service_type, host, namespace, write)` | command (`generate manifests`) | Generate Deployment + Service + optional Ingress/Namespace |

**Core service imports (all lazy):**

| Import | From | Used For |
|--------|------|----------|
| `generate_manifests` | `k8s_ops` | Manifest YAML generation |
| `write_generated_file` | `docker_ops` | Shared file writer |

**Multi-file write loop:** Unlike other generate commands that handle
a single `result["file"]`, this command iterates over `result["files"]`
(plural). Each file is independently written or previewed.

---

## Dependency Graph

```
__init__.py
├── click                     ← click.group
├── core.config.loader        ← find_project_file (lazy)
└── Imports: detect, observe, generate

detect.py
├── click                     ← click.command
└── core.services.k8s_ops     ← k8s_status, validate_manifests (lazy)

observe.py
├── click                     ← click.command
└── core.services.k8s_ops     ← cluster_status, get_resources (lazy)

generate.py
├── click                     ← click.group, click.command
├── core.services.k8s_ops     ← generate_manifests (lazy)
└── core.services.docker_ops  ← write_generated_file (lazy)
```

---

## Consumers

### Who registers this CLI group

| Layer | Module | What It Does |
|-------|--------|-------------|
| CLI entry | `src/main.py:462` | `from src.ui.cli.k8s import k8s` |

### Who also uses the same core service

| Layer | Module | Core Service Used |
|-------|--------|------------------|
| Web routes | `routes/k8s/` | `k8s_ops` (status, cluster, get, generate, validate) |
| Core | `wizard/setup_infra.py:183` | `k8s.generate_manifests`, `k8s.generate_helm_chart` |

---

## Design Decisions

### Why detect has two commands (status + validate)

Detection tells you *what exists*. Validation tells you *if it's
correct*. These are fundamentally different questions with different
output structures. `status` returns an inventory (dirs, files, counts).
`validate` returns a pass/fail with issue details.

### Why validate caps at 25 issues

A malformed manifest directory can produce hundreds of issues. Showing
all of them floods the terminal and makes it hard to identify the
most important problems. 25 is enough to see patterns and prioritize.

### Why `cluster` and `get` don't use project_root

These commands talk to a live Kubernetes cluster via kubeconfig. The
project root is irrelevant — the active kubectl context determines
which cluster is queried. This is intentionally different from all
other CLI commands.

### Why `get` defaults to pods

Pods are the most commonly inspected K8s resource. When debugging,
`k8s get` (with no arguments) gives the quickest useful information.

### Why `generate manifests` produces multiple files

Kubernetes best practice is to separate resources into individual
files (deployment.yaml, service.yaml, ingress.yaml). This makes it
easier to manage, review, and selectively apply manifests. Generating
them as separate files follows this convention.

### Why Ingress and Namespace are conditional

Not every application needs an Ingress (internal services) or a
custom Namespace (simple deployments). Making these conditional keeps
the basic output minimal while allowing full-featured generation
when needed.

---

## JSON Output Examples

### `k8s status --json`

```json
{
  "kubectl": {
    "available": true,
    "version": "v1.28.3"
  },
  "manifest_dirs": ["k8s", "deploy/k8s"],
  "total_resources": 12,
  "resource_summary": {
    "Deployment": 3,
    "Service": 3,
    "ConfigMap": 2,
    "Ingress": 1,
    "ServiceAccount": 1,
    "HPA": 2
  },
  "manifests": [
    {"path": "k8s/base.yaml", "count": 5}
  ],
  "helm_charts": [
    {"name": "myapp-chart", "version": "0.3.0", "path": "charts/myapp"}
  ],
  "kustomize": {
    "exists": true,
    "path": "k8s/kustomization.yaml"
  }
}
```

### `k8s validate --json`

```json
{
  "ok": false,
  "files_checked": 5,
  "errors": 2,
  "warnings": 3,
  "issues": [
    {
      "severity": "error",
      "file": "k8s/deployment.yaml",
      "message": "Missing required field: spec.template.spec.containers"
    },
    {
      "severity": "warning",
      "file": "k8s/deployment.yaml",
      "message": "No resource limits defined for container 'web'"
    }
  ]
}
```

### `k8s cluster --json`

```json
{
  "connected": true,
  "context": "minikube",
  "nodes": [
    {
      "name": "minikube",
      "ready": true,
      "roles": "control-plane",
      "version": "v1.28.3"
    }
  ],
  "namespaces": ["default", "kube-system", "kube-public"]
}
```
