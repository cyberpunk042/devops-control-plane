# Kubernetes Domain

> **19 files · 8,608 lines · The largest service domain in the control plane.**
>
> Offline YAML/Helm/Kustomize scanning, 7-layer manifest validation,
> live cluster operations, full wizard-driven generation, and Helm
> chart scaffolding.

---

## How It Works

The K8s domain operates in **five modes** depending on what the user needs:

### 1. Detection — What exists? (offline)

`detect.py` scans the project filesystem — no cluster connection needed:

```
PROJECT SCANNING                       CLI DETECTION
  k8s/, deploy/, manifests/              kubectl --version
  Chart.yaml (Helm charts)              helm version
  kustomization.yaml + overlays          skaffold version
  *.yaml with apiVersion/kind            kustomize version
  Strategy inference                     aws / gcloud / az version
  Infrastructure annotations
```

Result: a single `k8s_status()` dict with resource inventory, deployment
strategy detection, environment maps, readiness assessments, and infra
service detection.

### 2. Validation — Is it correct? (offline + optional cluster)

`validate.py` orchestrates a **7-layer validation pipeline**, each in its own module:

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Structural (per-resource)    validate_structural.py │
│   Deployment, Service, StatefulSet, Job, CronJob,            │
│   DaemonSet, Ingress, HPA, pod spec checks                  │
├──────────────────────────────────────────────────────────────┤
│ Layer 2: Cross-resource consistency  validate_cross_resource │
│   Service→Deployment selector match, PVC→PV binding,         │
│   HPA→target existence, ServiceAccount references            │
├──────────────────────────────────────────────────────────────┤
│ Layer 3: Environment-aware           validate_env_aware.py   │
│   Per-environment namespace conflicts, env-specific values,  │
│   Kustomize overlay completeness                             │
├──────────────────────────────────────────────────────────────┤
│ Layer 4: Cluster-aware               validate_cluster.py     │
│   API version cluster support, namespace existence,          │
│   StorageClass availability, resource quotas                 │
├──────────────────────────────────────────────────────────────┤
│ Layer 5: Security & production       validate_security.py    │
│   runAsNonRoot, readOnlyRootFilesystem, resource limits,     │
│   privileged containers, host network/PID                    │
├──────────────────────────────────────────────────────────────┤
│ Layer 6: Cross-domain                validate_cross_domain.py│
│   Docker↔K8s image consistency, CI↔K8s secret refs,          │
│   Terraform↔K8s provider alignment, git↔image tags           │
├──────────────────────────────────────────────────────────────┤
│ Layer 7: Deployment strategy         validate_strategy.py    │
│   Rolling update params, blue-green readiness,               │
│   canary traffic splitting, Helm chart structure              │
└─────────────────────────────────────────────────────────────┘
```

All layers contribute to a single `issues[]` list with `{file, severity, message}`.

### 3. Cluster Operations — Observe and act (online)

`cluster.py` wraps `kubectl` for live cluster interactions:

| Observe | Act |
|---------|-----|
| `cluster_status()` → context, nodes, namespaces, cluster type | `k8s_apply(root, file)` → apply manifests |
| `get_resources(ns, kind)` → pod/deploy/svc list | `k8s_delete_resource(kind, name, ns)` → delete |
| `k8s_pod_logs(ns, pod, tail)` → pod logs | `k8s_scale(name, replicas, ns)` → scale deploy |
| `k8s_events(ns)` → cluster events | |
| `k8s_describe(kind, name, ns)` → resource detail | |
| `k8s_namespaces()` → namespace list | |
| `k8s_storage_classes()` → storage info | |

### 4. Generation — Create manifests

Three generation paths:

| Path | Module | Input | Output |
|------|--------|-------|--------|
| **Templates** | `generate.py` + `pod_builder.py` | Stack/module detection | Individual manifest files |
| **Wizard** | `wizard.py` + `wizard_generate.py` | Wizard state dict | Full K8s directory with all resources |
| **Helm** | `helm_generate.py` | Wizard state | Complete Helm chart directory structure |

### 5. Helm — Chart operations (online)

`helm.py` wraps the Helm CLI for chart-level operations:

| Function | What It Does |
|----------|-------------|
| `helm_list(root, *, namespace)` | List installed releases (`--all-namespaces` if no ns) |
| `helm_values(root, release, *, namespace)` | Get release values (YAML) |
| `helm_install(root, release, chart, *, namespace, values_file, set_values, dry_run)` | Install a chart |
| `helm_upgrade(root, release, chart, *, namespace, values_file, set_values, dry_run)` | Upgrade (or install via `--install`) a release |
| `helm_template(root, release, chart, *, namespace, values_file)` | Render templates locally |

---

## Key Data Shapes

### k8s_status response

```python
{
    "has_k8s": True,
    "kubectl": {"available": True, "version": "v1.29.0"},
    "manifest_dirs": ["k8s"],
    "manifests": [
        {
            "path": "k8s/deployment.yaml",
            "resources": [
                {"kind": "Deployment", "name": "web",
                 "namespace": "default", "apiVersion": "apps/v1"},
            ],
            "count": 1,
        },
    ],
    "resource_summary": {"Deployment": 2, "Service": 2, "Ingress": 1},
    "total_resources": 5,
    "helm_charts": [
        {
            "path": "charts/web",
            "name": "web",
            "version": "0.1.0",
            "description": "Web application chart",
            "app_version": "1.0.0",
            "type": "application",
            "has_values": True,
            "has_templates": True,
            "has_subcharts": False,
            "has_lockfile": False,
            "env_values_files": ["values-staging.yaml", "values-production.yaml"],
        },
    ],
    "kustomize": {
        "exists": True,
        "path": "k8s/kustomization.yaml",
        "overlays": ["staging", "production"],
        "overlay_count": 2,
        "overlay_details": [
            {"name": "staging", "patch_count": 3},
        ],
        "has_bases": True,
        "mode": "multi",                        # "single" or "multi"
        "has_patches": True,
        "patch_types": ["patchesStrategicMerge", "patches"],
        "has_config_map_generator": True,
        "config_map_generator_count": 1,
        "has_secret_generator": True,
        "secret_generator_count": 1,
        "has_raw_secrets": False,
        "has_envsubst_vars": True,
        "envsubst_vars": ["DB_PASSWORD", "API_KEY"],
        "has_vars": False,
        "has_image_overrides": True,
        "image_override_count": 2,
        # Conditional keys (only if non-empty):
        # "namespace": "staging",
        # "name_prefix": "myapp-",
        # "name_suffix": "-v2",
    },
    "deployment_strategy": "kustomize",          # raw_kubectl | helm | kustomize | mixed | none
    "strategies_detected": ["raw_kubectl", "kustomize"],
    "environments": [
        {"name": "staging", "source": "kustomize_overlay", "namespace": "staging"},
        {"name": "production", "source": "helm_values"},
    ],
    "tool_availability": {
        "kubectl": {"available": True, "version": "v1.29.0"},
        "helm": {"available": True, "version": "v3.14.0"},
        "kustomize": {"available": True, "version": "v5.3.0"},
        "skaffold": {"available": False, "version": None},
        "minikube": {"available": True, "version": "v1.32.0"},
        "kind": {"available": False, "version": None},
        "az": {"available": False, "version": None},
        "aws": {"available": True, "version": "2.15.0"},
        "gcloud": {"available": False, "version": None},
    },
    "secret_safety": {
        "has_raw_secrets": False,
        "has_envsubst_vars": True,
        "envsubst_vars": ["DB_PASSWORD", "API_KEY"],
        "has_secret_generator": True,
    },
    "deployment_readiness": "ready",             # not_configured | needs_tools | needs_config | ready
    "infra_services": [
        {"name": "cert-manager", "detected_via": "resource_kind"},
        {"name": "ingress-nginx", "detected_via": "helm_chart"},
    ],
    "missing_tools": [],
}
```

### cluster_status response

```python
{
    "connected": True,
    "context": "minikube",
    "nodes": [
        {
            "name": "minikube",
            "ready": True,               # bool, not string
            "roles": "control-plane",
            "version": "v1.29.0",
        },
    ],
    "namespaces": ["default", "kube-system", "staging", "production"],
    "cluster_type": {
        "type": "minikube",               # minikube | kind | docker_desktop | k3s | k3d | eks | aks | gke | unknown
        "detected_via": "context_name",   # context_name | node_version | none
    },
}
```

### get_resources response

```python
{
    "ok": True,
    "resources": [
        {
            "name": "web-7d5b8c6f4-abc12",
            "namespace": "default",
            "created": "2026-02-28T14:30:00Z",
            "phase": "Running",
            "conditions": "Initialized, Ready, PodScheduled",  # comma-joined True conditions
        },
    ],
    "count": 3,
}
```

### validate_manifests response

```python
{
    "ok": False,
    "files_checked": 5,
    "issues": [
        {
            "file": "k8s/deployment.yaml",
            "severity": "error",
            "message": "Deployment: missing metadata.name",
        },
        {
            "file": "k8s/deployment.yaml",
            "severity": "warning",
            "message": "Deployment 'web': no resource limits — may consume unbounded memory",
        },
    ],
    "errors": 1,
    "warnings": 1,
}
```

### helm_list response

```python
{
    "available": True,
    "releases": [
        {
            "name": "my-app",
            "namespace": "default",
            "revision": "3",
            "status": "deployed",
            "chart": "my-app-0.1.0",
            "app_version": "1.0.0",
        },
    ],
}
```

### wizard_state_to_resources input/output

```python
# Input (wizard state)
{
    "_services": [
        {
            "name": "web",
            "image": "web:latest",
            "port": 3000,
            "replicas": 2,
            "workloadType": "Deployment",
            "envVars": [{"key": "NODE_ENV", "value": "production", "kind": "config"}],
            "volumes": [{"name": "data", "type": "pvc-dynamic", "size": "10Gi"}],
            "probes": {"liveness": {"path": "/healthz", "port": 3000}},
        },
    ],
    "deploy_config": {
        "namespace": "production",
        "method": "kubectl",
    },
    "ingress": "web.example.com",
    "skaffold": False,
}

# Output (resource list)
[
    {"kind": "Deployment", "name": "web", "namespace": "production", "output_dir": "k8s", "spec": {...}},
    {"kind": "Service", "name": "web", "namespace": "production", "output_dir": "k8s", "spec": {...}},
    {"kind": "ConfigMap", "name": "web-config", "namespace": "production", "output_dir": "k8s", "spec": {...}},
    {"kind": "PersistentVolumeClaim", "name": "web-data", "namespace": "production", "output_dir": "k8s", "spec": {...}},
    {"kind": "Ingress", "name": "web-ingress", "namespace": "production", "output_dir": "k8s", "spec": {...}},
    {"kind": "Namespace", "name": "production", "output_dir": "k8s", "spec": {}},
]
```

### k8s_pod_logs response

```python
# Success
{"ok": True, "pod": "web-abc12", "namespace": "default",
 "logs": "2026-02-28 14:30:00 Server started on port 3000\n..."}

# Error
{"ok": False, "error": "Pod 'web-abc12' not found in namespace 'default'"}
```

### k8s_events response

```python
{
    "ok": True,
    "events": [
        {
            "type": "Normal",
            "reason": "Scheduled",
            "object": "Pod/web-7d5b8c6f4-abc12",
            "message": "Successfully assigned default/web-7d5b8c6f4-abc12 to node1",
            "count": 1,
            "first_seen": "2026-02-28T14:25:00Z",
            "last_seen": "2026-02-28T14:25:00Z",
        },
    ],
    "count": 12,
}
```

### k8s_storage_classes response

```python
{
    "ok": True,
    "storage_classes": [
        {
            "name": "standard",
            "provisioner": "k8s.io/minikube-hostpath",
            "is_default": True,
            "reclaim_policy": "Delete",
            "volume_binding_mode": "Immediate",
            "parameters": {},
        },
    ],
    "default_class": "standard",
}
```

---

## Architecture

```
                  CLI (ui/cli/k8s.py)
                  Routes (routes/k8s/)
                         │
                         │ imports
                         │
              ┌──────────▼──────────┐
              │  k8s_ops.py         │  backward-compat shim
              │  (re-exports all)   │  → imports from k8s/
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────────────────────────────┐
              │  k8s/__init__.py                              │
              │  Public API — re-exports all symbols          │
              └──┬────┬────┬────┬────┬────┬────┬────┬────┬──┘
                 │    │    │    │    │    │    │    │    │
     ┌───────────┘    │    │    │    │    │    │    │    └──────────┐
     ▼                ▼    │    ▼    │    ▼    ▼    ▼              ▼
  common.py     detect.py  │  cluster │  helm  wizard  generate  helm_generate
  (constants,   (scan,     │  (live   │  (CLI  (state  (pod      (chart dir
   runners,     Helm,      │  kubectl │  ops)  trans-  builder)  scaffold)
   YAML parse)  Kustomize) │  CRUD)   │       late)
                           │          │
                     validate.py ─────┘
                           │
                 ┌─────────┼─────────────────────┐
                 ▼         ▼         ▼           ▼
          structural  cross_res  env_aware  cluster_aware
                 ▼         ▼
          security    cross_domain   strategy
```

### Dependency Rules

| Rule | Detail |
|------|--------|
| `common.py` is standalone | Constants, `_run_kubectl`, `_parse_k8s_yaml` |
| `detect.py` imports `common` only | Uses constants + YAML parsing |
| `cluster.py` imports `common` only | Uses `_run_kubectl` |
| `validate.py` imports `common` + `detect` + all 7 validators | Orchestration hub |
| `validate_*.py` modules are standalone | Receive data, return issues |
| `wizard.py` imports `generate` | Uses pod_builder helpers |
| `helm.py` is standalone | Direct subprocess calls |

---

## File Map

```
k8s/
├── __init__.py               Public API re-exports (91 lines)
├── common.py                 Shared constants, _run_kubectl, _parse_k8s_yaml (109 lines)
├── detect.py                 Offline manifest/Helm/Kustomize scanning (641 lines)
├── cluster.py                Live kubectl cluster operations (472 lines)
├── helm.py                   Helm CLI operations (176 lines)
├── pod_builder.py            Probes, volumes, env vars, mesh annotations (559 lines)
├── generate.py               Manifest templates + re-exports from pod_builder (197 lines)
├── wizard.py                 Wizard state translator + persistence (565 lines)
├── wizard_detect.py          Skaffold status, namespace mapping (186 lines)
├── wizard_generate.py        Manifest generation from wizard resource defs (1,012 lines)
├── helm_generate.py          Full Helm chart directory generation (514 lines)
├── validate.py               7-layer validation orchestrator (151 lines)
├── validate_structural.py    Layer 1: per-resource structural checks (321 lines)
├── validate_cross_resource.py Layer 2: cross-resource consistency (405 lines)
├── validate_env_aware.py     Layer 3: environment-aware checks (245 lines)
├── validate_cluster.py       Layer 4: cluster-aware checks (229 lines)
├── validate_security.py      Layer 5: security & production readiness (290 lines)
├── validate_cross_domain.py  Layer 6: cross-domain consistency (1,289 lines)
├── validate_strategy.py      Layer 7: deployment strategy validation (1,156 lines)
└── README.md                 This file
```

---

## Per-File Documentation

### `common.py` — Shared Constants & Runners (109 lines)

| Export | What It Is |
|--------|-----------|
| `_SKIP_DIRS` | Directories excluded from scanning (`.git`, `node_modules`, `__pycache__`, etc.) — 14 entries |
| `_K8S_API_VERSIONS` | Set of known K8s API versions for validation — 10 versions |
| `_K8S_KINDS` | Set of known K8s resource kinds — 24 kinds |
| `_MANIFEST_DIRS` | Conventional directories for K8s manifests (`k8s`, `kubernetes`, `deploy`, `manifests`, `kube`, `charts`) |
| `_run_kubectl(*args, timeout=15)` | `subprocess.run(["kubectl", *args])` with configurable timeout |
| `_kubectl_available()` | Check if kubectl is installed — uses `kubectl version --client -o json` |
| `_parse_k8s_yaml(path)` | Parse multi-document YAML → list of resource dicts (filters for apiVersion+kind) |

### `detect.py` — Offline Scanning (641 lines)

| Function | What It Does |
|----------|-------------|
| `k8s_status(root)` | **Main entry** — comprehensive K8s environment report (16-key dict) |
| `_detect_cli(name)` | Check CLI availability + version extraction via `_CLI_VERSION_SPECS` |
| `_collect_yaml_files(root, dirs)` | Find YAML in manifest directories (capped at 50 files) |
| `_detect_helm_charts(root)` | Chart.yaml scanning with full structure analysis |
| `_detect_kustomize(root)` | Kustomization scanning with overlay/patch/generator/secret analysis |
| `_detect_infra_services(resources, charts)` | Infrastructure service detection from resource kinds, annotations, and charts |
| `_count_patches(kustomize_data)` | Count total patches across patchesStrategicMerge/patchesJson6902/patches |
| `_find_kustomize_dir(root, path)` | Resolve directory from kustomize path string |
| `_read_kustomize_namespace(overlay_dir)` | Read namespace field from overlay's kustomization file |

**CLI detection registry (`_CLI_VERSION_SPECS`):**

| Tool | Command | Version Pattern |
|------|---------|----------------|
| helm | `helm version --short` | `v(\d+\.\d+\.\d+)` |
| kustomize | `kustomize version` | `v(\d+\.\d+\.\d+)` |
| skaffold | `skaffold version` | `v(\d+\.\d+\.\d+)` |
| minikube | `minikube version --short` | `v(\d+\.\d+\.\d+)` |
| kind | `kind version` | `v(\d+\.\d+\.\d+)` |
| az | `az version -o json` | `"azure-cli": "(\d+\.\d+\.\d+)"` |
| aws | `aws --version` | `aws-cli/(\d+\.\d+\.\d+)` |
| gcloud | `gcloud version` | `Google Cloud SDK (\d+\.\d+\.\d+)` |

> **Note:** kubectl is NOT in `_CLI_VERSION_SPECS` — it uses `_kubectl_available()` from
> `common.py` which calls `kubectl version --client -o json` and parses the JSON.

**Infrastructure detection — three sources:**

- `_INFRA_CHART_NAMES` — 21 known Helm charts (ingress-nginx, cert-manager, prometheus, etc.)
- `_INFRA_KIND_MAP` — 9 K8s kinds that imply infra (Ingress→ingress-controller, Certificate→cert-manager, etc.)
- `_INFRA_ANNOTATION_PREFIXES` — 3 annotation prefixes (cert-manager.io/, prometheus.io/, nginx.ingress.kubernetes.io/)

### `cluster.py` — Live Cluster Operations (472 lines)

**Observe functions:**

| Function | Return Shape |
|----------|-------------|
| `cluster_status()` | `{connected, context, nodes: [{name, ready, roles, version}], namespaces, cluster_type}` |
| `get_resources(ns, kind)` | `{ok, resources: [{name, namespace, created, phase, conditions}], count}` |
| `k8s_pod_logs(ns, pod, *, tail, container)` | `{ok, pod, namespace, logs}` or `{ok: False, error}` |
| `k8s_events(ns)` | `{ok, events: [{type, reason, object, message, count, first_seen, last_seen}], count}` |
| `k8s_describe(kind, name, *, ns)` | `{ok, description}` or `{ok: False, error}` |
| `k8s_namespaces()` | `{ok, namespaces: [{name, status, created}], count}` |
| `k8s_storage_classes()` | `{ok, storage_classes: [{name, provisioner, is_default, reclaim_policy, volume_binding_mode, parameters}], default_class, count}` |

**Act functions:**

| Function | What It Does | Audited |
|----------|-------------|---------|
| `k8s_apply(root, file_path, *, ns)` | `kubectl apply -f` (files or dirs with `--recursive`) | ❌ |
| `k8s_delete_resource(kind, name, *, ns)` | `kubectl delete` | ❌ |
| `k8s_scale(name, replicas, *, ns, kind)` | `kubectl scale` | ❌ |

> **Note:** `make_auditor("k8s")` is imported in `cluster.py` but `_audit()` is
> never called. Act functions are NOT currently audited (see Audit Trail section).

**Cluster type detection (`_detect_cluster_type`):**

| Type | Detection Method | Source |
|------|-----------------|--------|
| minikube | `ctx == "minikube"` | context_name |
| kind | `ctx.startswith("kind-")` | context_name |
| docker_desktop | `ctx == "docker-desktop"` | context_name |
| k3d | `ctx.startswith("k3d-")` | context_name |
| gke | `ctx.startswith("gke_")` | context_name |
| eks | `"arn:aws:eks:" in ctx` or `ctx.startswith("eks-")` or `ctx.startswith("eks_")` | context_name |
| aks | `re.search(r"\baks\b", ctx)` | context_name |
| k3s | `"+k3s" in node.version` | node_version |
| unknown | No pattern matched | none |

### `validate.py` — 7-Layer Orchestrator (151 lines)

Single entry point: `validate_manifests(project_root)`.

1. Collects all manifest files from `k8s_status()`
2. Parses each with `_parse_k8s_yaml()`
3. Runs per-resource structural checks (Layers 1)
4. Runs cross-resource consistency (Layer 2)
5. Runs environment-aware checks (Layer 3)
6. Runs cluster-aware checks (Layer 4)
7. Runs security & production checks (Layer 5)
8. Runs cross-domain checks (Layer 6)
9. Runs deployment strategy checks (Layer 7)
10. Counts errors/warnings, returns unified result

### `validate_structural.py` — Layer 1 (321 lines)

Per-resource-kind checks:

| Validator | Checks |
|-----------|--------|
| `_validate_deployment` | Replicas ≥ 1, selector matches template labels, strategy type |
| `_validate_service` | Port definitions, selector matches, ClusterIP/NodePort/LoadBalancer |
| `_validate_pod_spec` | Container image tags (not `:latest`), ports, resource limits |
| `_validate_statefulset` | serviceName defined, volumeClaimTemplates |
| `_validate_job` | backoffLimit, restartPolicy |
| `_validate_cronjob` | schedule format, concurrencyPolicy |
| `_validate_daemonset` | updateStrategy, tolerations |
| `_validate_ingress` | Rules, TLS, backend service references |
| `_validate_hpa` | Min/max replicas, target ref |

### `validate_cross_domain.py` — Layer 6 (1,289 lines)

The largest validator. Cross-references K8s manifests against:

- **Docker** — Image consistency between Dockerfiles and K8s deployments
- **CI/CD** — Secret references in workflows vs K8s secret manifests
- **Terraform** — Provider alignment (EKS ↔ AWS, GKE ↔ GCP)
- **Git** — Image tags vs branch naming conventions
- **Secrets** — .env key coverage vs K8s ConfigMap/Secret refs

### `wizard.py` — State Translator + Persistence (565 lines)

| Function | What It Does |
|----------|-------------|
| `wizard_state_to_resources(data)` | **Key translator** — wizard state → resource list |
| `_svc_env_to_resources(name, envVars, ns, dir)` | Extract ConfigMap / Secret from env vars |
| `_svc_volumes_to_pvc_resources(name, volumes, ns, dir)` | Generate PVCs from volume definitions |
| `_sanitize_state(data)` | Strip transient/detection fields before persisting |
| `load_wizard_state(root)` | Load from `k8s/.wizard-state.json` |
| `save_wizard_state(root, data)` | Save to `k8s/.wizard-state.json` |
| `wipe_wizard_state(root)` | Delete wizard state file |

Re-exports from siblings: `skaffold_status`, `k8s_env_namespaces` (from `wizard_detect.py`),
`generate_k8s_wizard`, `_generate_skaffold` (from `wizard_generate.py`).

### `wizard_generate.py` — Manifest Generation (1,012 lines)

| Function | What It Does |
|----------|-------------|
| `generate_k8s_wizard(root, resources)` | **Main entry** — generate all K8s files from resource list |
| `_generate_skaffold(data, generated_files)` | Generate `skaffold.yaml` for dev workflow |
| `_build_profiles(data, envs, output_dir)` | Build Skaffold profiles from wizard environments |
| `_build_profile(env, data, output_dir)` | Build a single Skaffold profile (dev/staging/prod flavors) |
| `_build_port_forward_entries(services, *, ns)` | Build Skaffold portForward entries with collision detection |
| `_build_sync_artifacts(services)` | Build artifact entries with sync rules for dev hot-reload |
| `_sync_rules_for_language(language)` | Return sync.manual rules for a given language |
| `_build_kustomization_files(files, dir, vars, secrets)` | Generate base + overlay kustomization.yaml files |
| `_build_helm_releases(data)` | Build Skaffold helm.releases list from wizard state |
| `_build_tag_policy(name)` | Build Skaffold tagPolicy dict (gitCommit/sha256/dateTime/etc.) |
| `_collect_variable_env_keys(services)` | Scan services for env vars needing envsubst |
| `_collect_secret_env_keys(services)` | Scan services for secret-only env var keys |
| `_build_envsubst_hooks(manifest_paths)` | Build Skaffold pre-deploy hooks for envsubst |
| `_build_env_example(variable_keys)` | Build .env.example listing all required variables |

Generates full YAML files for: Deployment, StatefulSet, DaemonSet,
Service, Ingress, ConfigMap, Secret, Namespace, HPA, PVC, CronJob, Job.

### `helm_generate.py` — Chart Scaffolding (514 lines)

Generates a complete Helm chart directory:

```
charts/<name>/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── _helpers.tpl
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   └── hpa.yaml
└── values-<env>.yaml (per environment)
```

### `pod_builder.py` — Pod Spec Building (559 lines)

Low-level builders used by `generate.py` and `wizard.py`:

| Function | What It Builds |
|----------|---------------|
| `_build_probe(probe)` | Liveness/readiness probe (HTTP, TCP, exec) — converts wizard format |
| `_build_wizard_volume(vol, index, svc_name)` | Volume + volumeMount from wizard volume def |
| `_build_pod_template(name, spec)` | Complete pod template spec (main/init/sidecar containers, volumes, probes, mesh) |
| `_build_env_vars(env_spec, *, svc_name)` | K8s env var list from dict, name/value list, or wizard format |
| `_mesh_annotation_prefixes()` | Mesh annotation prefixes loaded from DataRegistry |
| `_build_mesh_annotations(mesh)` | Istio/Linkerd/Consul sidecar annotations |
| `_api_version_for_kind(kind)` | Resolve conventional apiVersion for a K8s kind |

---

## Audit Trail

> **⚠️ Status: NOT IMPLEMENTED.** `make_auditor("k8s")` is imported in
> `cluster.py`, `helm.py`, and `generate.py`, creating `_audit` instances.
> However, `_audit()` is **never called** anywhere in the k8s package.
> Mutating cluster operations (apply, delete, scale, helm install/upgrade)
> are NOT currently logged to the audit trail.

---

## Dependency Graph

```
common.py  ← standalone (subprocess, yaml, pathlib)
   ▲
   │
   ├── detect.py        (imports constants + YAML parse)
   ├── cluster.py       (imports _run_kubectl, _kubectl_available)
   │
   └── validate.py      orchestrator
          ├── detect.py  (for k8s_status)
          ├── validate_structural.py
          ├── validate_cross_resource.py
          ├── validate_env_aware.py
          ├── validate_cluster.py
          ├── validate_security.py
          ├── validate_cross_domain.py
          └── validate_strategy.py

helm.py              ← standalone (subprocess only)

pod_builder.py       ← standalone (data transformation)
   ▲
   └── generate.py   (re-exports + simple templates)
         ▲
         └── wizard.py (uses pod_builder helpers)
               ├── wizard_detect.py    (re-exported)
               └── wizard_generate.py  (re-exported)

helm_generate.py     ← standalone (file generation)
```

---

## Error Handling Patterns

```python
# Pattern 1: "connected" / "available" (cluster/observe)
{"connected": False, "error": "kubectl not available"}
{"available": False, "error": "helm CLI not found"}

# Pattern 2: "ok" + "error" (act/validate)
{"ok": False, "files_checked": 5, "issues": [...], "errors": 3}
{"error": "Pod 'web-abc12' not found"}
{"ok": True, "output": "deployment.apps/web scaled"}
```

**Tool availability gates:** `cluster.py` and `helm.py` check tool
availability before executing commands. If kubectl/helm is missing,
they return structured error dicts instead of crashing.

---

## Backward Compatibility

| Old path | Re-exports from |
|----------|----------------|
| `services/k8s_ops.py` | `k8s/` — all public functions |

```python
# ✅ New (package-level)
from src.core.services.k8s import k8s_status, cluster_status, validate_manifests

# ⚠️ Legacy shim — still works, avoid in new code
from src.core.services.k8s_ops import k8s_status
```

---

## Consumers

| Consumer | What It Uses |
|----------|-------------|
| **Routes** `routes/k8s/` | All functions — detection, cluster ops, validation, generation |
| **CLI** `ui/cli/k8s.py` | `k8s_status`, `cluster_status`, `validate_manifests`, `generate_k8s_wizard` |
| **Docker bridge** `docker/k8s_bridge.py` | Provides `docker_to_k8s_services()` consumed by wizard |
| **Wizard** `wizard/setup_infra.py` | `generate_k8s_wizard`, `save_wizard_state` |
| **CI compose** `ci/compose.py` | K8s deploy config for CI job generation |
| **Metrics** `metrics/ops.py` | `k8s_status`, `cluster_status` for health probes |

---

## Design Decisions

### Why 7 validation layers instead of one big checker?

Each layer has fundamentally different inputs and concerns:
- Layers 1–3 are purely offline (parse YAML, check structure)
- Layer 4 needs optional cluster connection
- Layers 5–7 need cross-domain data (Docker, CI, Terraform status)

Separating them means: each can be tested independently, users can
understand which category an issue falls into, and new checks can
be added to the correct layer without touching others.

### Why is validate_cross_domain.py 1,289 lines?

Layer 6 cross-references K8s manifests against 5 other domains
(Docker, CI, Terraform, Git, Secrets). Each cross-domain check
is self-contained within the file but needs access to the other
domain's detection functions. The size reflects the combinatorial
nature of cross-domain validation — there are 30+ distinct check
types across the domain pairings.

### Why does the wizard translate state instead of generating directly?

`wizard_state_to_resources()` converts frontend wizard state into
a normalized `[{kind, name, namespace, spec}]` list. Then
`generate_k8s_wizard()` consumes that list to produce YAML.
This two-phase approach means: (1) the translator can be unit-tested
without filesystem writes, (2) the generator is reusable for non-wizard
inputs, and (3) the intermediate resource list serves as a readable
"plan" that can be shown to the user before generation.

### Why are Helm chart operations separate from Helm chart generation?

`helm.py` wraps the Helm CLI for runtime operations (install, upgrade,
template). `helm_generate.py` creates chart directory structures as
files on disk. Different lifecycle: operations run in a cluster context,
generation runs offline during wizard setup. They never cross-reference
each other.

### Why does cluster_status auto-detect cluster type?

The UI shows cluster-type-specific guidance (e.g., "your minikube
cluster has 1 node" vs "your EKS cluster has 3 nodes across 2 AZs").
Auto-detection from context name + node metadata works for all common
local (minikube, kind, Docker Desktop) and cloud (EKS, AKS, GKE)
clusters without requiring user configuration.

### Why does detect.py scan for infrastructure services?

The wizard needs to know if the user already has ingress-nginx or
cert-manager deployed (via Helm charts or annotations) to avoid
generating duplicate infrastructure manifests. Scanning existing
resources for known infra chart names and annotation prefixes
provides this without a cluster connection.

### Why is pod_builder.py separate from generate.py?

`pod_builder.py` contains reusable pod spec building functions
(probes, volumes, env vars, mesh annotations).
These are used by both the template-based `generate.py` path and
the wizard-based `wizard.py` path. Keeping builders separate means
both generation paths produce consistent pod specs from the same logic.

---

## Advanced Feature Showcase

### 1. 16-Key Comprehensive Detection Engine (`detect.py` lines 63–261)

```python
# detect.py — k8s_status
def k8s_status(project_root: Path) -> dict:
    kubectl = _kubectl_available()
    manifest_dirs: list[str] = []
    for dir_name in _MANIFEST_DIRS:  # 6 conventional dirs
        dir_path = project_root / dir_name
        if dir_path.is_dir():
            manifest_dirs.append(dir_name)

    # Scan YAML, detect Helm, detect Kustomize
    yaml_files = _collect_yaml_files(project_root, manifest_dirs)
    # ...

    # Deployment strategy detection
    strategies_detected: list[str] = []
    if has_manifests: strategies_detected.append("raw_kubectl")
    if has_helm:      strategies_detected.append("helm")
    if has_kustomize: strategies_detected.append("kustomize")

    deployment_strategy = (
        "none" if not strategies_detected
        else strategies_detected[0] if len(strategies_detected) == 1
        else "mixed"
    )

    # Unified environment map from Kustomize overlays + Helm values files
    environments: list[dict] = []
    # ... merges both sources by name with deduplication

    # Tool availability (9 tools including cloud CLIs)
    tool_availability = {
        "kubectl": kubectl, "helm": _detect_cli("helm"),
        "kustomize": _detect_cli("kustomize"), "skaffold": _detect_cli("skaffold"),
        "minikube": _detect_cli("minikube"), "kind": _detect_cli("kind"),
        "az": _detect_cli("az"), "aws": _detect_cli("aws"),
        "gcloud": _detect_cli("gcloud"),
    }

    # Deployment readiness (4-state assessment)
    if not has_k8s:                           deployment_readiness = "not_configured"
    elif not kubectl.get("available", False): deployment_readiness = "needs_tools"
    elif has_raw_secrets or has_envsubst_vars: deployment_readiness = "needs_config"
    else:                                     deployment_readiness = "ready"

    # Infrastructure service detection from 3 sources
    infra_services = _detect_infra_services(all_parsed_resources, helm_charts)

    return {
        "has_k8s": has_k8s, "kubectl": kubectl,
        "manifest_dirs": manifest_dirs, "manifests": manifests,
        "resource_summary": resource_summary, "total_resources": total_resources,
        "helm_charts": helm_charts, "kustomize": kustomize,
        "deployment_strategy": deployment_strategy,
        "strategies_detected": strategies_detected,
        "environments": environments,
        "tool_availability": tool_availability,
        "secret_safety": secret_safety,
        "deployment_readiness": deployment_readiness,
        "infra_services": infra_services,
        "missing_tools": missing_tools,
    }
```

**Why this matters:** A single call to `k8s_status()` drives the entire UI —
detection panels, wizard pre-population, readiness badges, and missing-tool
install prompts. The 16-key return dict avoids multiple round-trips and gives
the frontend everything it needs in one shot. The deployment strategy
detection automatically classifies projects as `raw_kubectl | helm | kustomize | mixed`,
the 4-state readiness assessment tells users exactly what's missing, and the
unified environment map merges Kustomize overlays with Helm values files
into a single list — eliminating duplicate detection logic in the frontend.

### 2. Kustomize Deep Analysis with Secret Safety Assessment (`detect.py` lines 350–530)

```python
# detect.py — _detect_kustomize
# Scan referenced resource files for raw Secrets and envsubst vars
has_raw_secrets = False
envsubst_vars: list[str] = []
resources = content.get("resources", [])
if isinstance(resources, list):
    for res_ref in resources:
        res_path = kustomize_dir / res_ref
        if res_path.is_file():
            res_text = res_path.read_text(encoding="utf-8", errors="ignore")
            # Check for raw Secret kind
            for doc in yaml.safe_load_all(res_text):
                if isinstance(doc, dict) and doc.get("kind") == "Secret":
                    has_raw_secrets = True
            # Check for ${VAR} patterns (envsubst)
            found_vars = re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", res_text)
            envsubst_vars.extend(found_vars)

envsubst_vars = sorted(set(envsubst_vars))
```

**Why this matters:** Raw Secrets committed to Git are a security risk. Envsubst
variables (`${DB_PASSWORD}`) need to be resolved before `kubectl apply`. This
detection doesn't just check the kustomization.yaml itself — it follows every
`resources:` reference and parses the actual YAML files looking for `kind: Secret`
and `${VAR}` patterns. The result feeds into `deployment_readiness`: if either
`has_raw_secrets` or `has_envsubst_vars` is true, readiness drops to `needs_config`,
and the UI warns the user before they attempt to deploy.

### 3. Cluster Type Heuristic Chain (`cluster.py` lines 20–60)

```python
# cluster.py — _detect_cluster_type
def _detect_cluster_type(context: str, nodes: list[dict]) -> dict:
    ctx = context.lower()

    # Exact / prefix matches (most reliable)
    if ctx == "minikube":                return {"type": "minikube",        "detected_via": "context_name"}
    if ctx.startswith("kind-"):          return {"type": "kind",            "detected_via": "context_name"}
    if ctx == "docker-desktop":          return {"type": "docker_desktop",  "detected_via": "context_name"}
    if ctx.startswith("k3d-"):           return {"type": "k3d",             "detected_via": "context_name"}
    if ctx.startswith("gke_"):           return {"type": "gke",             "detected_via": "context_name"}

    # Pattern matches
    if "arn:aws:eks:" in ctx or ctx.startswith("eks-") or ctx.startswith("eks_"):
        return {"type": "eks", "detected_via": "context_name"}
    if re.search(r"\baks\b", ctx):
        return {"type": "aks", "detected_via": "context_name"}

    # Node-level detection (fallback)
    for node in nodes:
        if "+k3s" in node.get("version", ""):
            return {"type": "k3s", "detected_via": "node_version"}

    return {"type": "unknown", "detected_via": "none"}
```

**Why this matters:** The UI adapts guidance based on cluster type (e.g.,
"minikube has 1 node" vs "EKS spans multiple AZs"). The detection uses a
deliberate cascade: exact matches first (minikube, docker-desktop), then
prefix matching (kind-, k3d-, gke_), then substring/regex (eks, aks), and
finally node metadata as a last resort (k3s detected via kubelet version).
This ordering ensures deterministic results — a context named `kind-eks-test`
correctly detects as `kind`, not `eks`. The `detected_via` field in the
return dict makes the heuristic transparent for debugging.

### 4. Wizard State Translator — 337-Line Pipeline (`wizard.py` lines 123–459)

```python
# wizard.py — wizard_state_to_resources
def wizard_state_to_resources(data: dict) -> list[dict]:
    namespace = data.get("namespace", "default")
    output_dir = (data.get("output_dir") or "k8s").rstrip("/")
    resources: list[dict] = []
    services_needing_svc: list[dict] = []

    # Phase 1: Namespace
    if namespace and namespace != "default":
        resources.append({"kind": "Namespace", "name": namespace, ...})

    # Phase 2: App + Infra services → workload resources
    all_services  = list(data.get("_services", []))
    all_services += list(data.get("_infraDecisions", []))

    for svc in all_services:
        svc_kind = svc.get("kind", "Deployment")
        if svc_kind in ("Skip", "Managed"):
            continue

        # Each service generates: workload + env ConfigMap/Secret + PVCs + HPA
        # Resources for env vars (ConfigMap + Secret)
        env_resources, has_config, has_secrets = _svc_env_to_resources(...)
        # PVC resources from volumes
        pvc_resources = _svc_volumes_to_pvc_resources(...)
        # Probes, resources, mesh, strategy — all collected into spec dict

        resources.append({"kind": svc_kind, "name": svc_name, "spec": spec, ...})

        # HPA if autoscaling is enabled
        if autoscaling and autoscaling.get("enabled"):
            resources.append({"kind": "HorizontalPodAutoscaler", ...})

        # Track services needing K8s Service resources
        if port and svc_kind in ("Deployment", "StatefulSet", "DaemonSet"):
            services_needing_svc.append(svc_entry)

    # Phase 3: K8s Services (including headless for StatefulSets)
    # Phase 4: Multi-path Ingress (single-service→simple, multi-service→path-based)

    return resources
```

**Why this matters:** This is the critical bridge between the web wizard UI
and the YAML generator. The 337-line translator handles every K8s resource
type the wizard supports — Deployment, StatefulSet, DaemonSet, Job, CronJob,
ConfigMap, Secret, PVC, HPA, Service, Ingress, Namespace — plus edge cases
like `Skip` (user doesn't want this service) and `Managed` (externally managed
service, tracked but not generated). The two-phase architecture
(translate → generate) means the intermediate resource list can be inspected
as a "plan" before any files are written. Multi-service Ingress automatically
switches from a simple single-backend to path-based routing when multiple
services with ports exist.

### 5. Infrastructure Service Detection from Three Sources (`detect.py` lines 570–641)

```python
# detect.py — three detection source constants

_INFRA_CHART_NAMES = frozenset({
    "ingress-nginx", "traefik", "ambassador", "haproxy-ingress",
    "cert-manager", "prometheus", "grafana", "datadog",
    "kube-prometheus-stack", "istio", "linkerd",
    "longhorn", "rook-ceph",
    "external-secrets", "sealed-secrets", "vault",
    "metallb", "calico", "cilium",
    "argo-cd", "argocd", "flux",
})  # 21 entries

_INFRA_KIND_MAP: dict[str, str] = {
    "Ingress": "ingress-controller", "Certificate": "cert-manager",
    "ClusterIssuer": "cert-manager", "Issuer": "cert-manager",
    "ServiceMonitor": "prometheus", "PrometheusRule": "prometheus",
    "PodMonitor": "prometheus",
    "Gateway": "gateway-api", "HTTPRoute": "gateway-api",
}  # 9 entries

_INFRA_ANNOTATION_PREFIXES: dict[str, str] = {
    "cert-manager.io/": "cert-manager",
    "prometheus.io/": "prometheus",
    "nginx.ingress.kubernetes.io/": "ingress-nginx",
}  # 3 prefixes

def _detect_infra_services(parsed_resources, helm_charts) -> list[dict]:
    infra: dict[str, dict] = {}
    # Source 1: resource kinds (Ingress → ingress-controller, etc.)
    # Source 2: annotation prefixes (cert-manager.io/ → cert-manager, etc.)
    # Source 3: Helm chart names (ingress-nginx, cert-manager, etc.)
    return sorted(infra.values(), key=lambda x: x["name"])
```

**Why this matters:** The wizard needs to know whether infrastructure services
(ingress, cert-manager, monitoring) are already deployed to avoid generating
duplicates. Detection runs *without a cluster connection* by scanning the parsed
manifest resources. Three independent sources cover different deployment patterns:
direct resource kinds (someone deployed an Ingress), annotations (someone
annotated pods with `prometheus.io/scrape`), and Helm charts (someone installed
`ingress-nginx` via Helm). Each detected service carries a `detected_via` field
(`resource_kind | manifest_annotation | helm_chart`) so the wizard can show
users *how* it was detected.

### 6. CLI Version Detection Registry (`detect.py` lines 18–61)

```python
# detect.py — version detection via regex patterns
_CLI_VERSION_SPECS: dict[str, tuple[list[str], str]] = {
    # K8s tools
    "helm":      (["helm", "version", "--short"],    r"(v[\d]+\.[\d]+\.[\d]+)"),
    "kustomize": (["kustomize", "version"],          r"(v[\d]+\.[\d]+\.[\d]+)"),
    "skaffold":  (["skaffold", "version"],            r"(v[\d]+\.[\d]+\.[\d]+)"),
    "minikube":  (["minikube", "version", "--short"], r"(v[\d]+\.[\d]+\.[\d]+)"),
    "kind":      (["kind", "version"],                r"(v[\d]+\.[\d]+\.[\d]+)"),
    # Cloud CLIs
    "az":        (["az", "version", "-o", "json"],    r'"azure-cli":\s*"([\d]+\.[\d]+\.[\d]+)"'),
    "aws":       (["aws", "--version"],               r"aws-cli/([\d]+\.[\d]+\.[\d]+)"),
    "gcloud":    (["gcloud", "version"],              r"Google Cloud SDK ([\d]+\.[\d]+\.[\d]+)"),
}

def _detect_cli(name: str) -> dict:
    if shutil.which(name) is None:
        return {"available": False, "version": None}
    spec = _CLI_VERSION_SPECS.get(name)
    if spec is None:
        return {"available": True, "version": None}
    args, pattern = spec
    result = subprocess.run(args, capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        match = re.search(pattern, result.stdout)
        if match:
            return {"available": True, "version": match.group(1)}
    return {"available": True, "version": None}  # exists but couldn't parse version
```

**Why this matters:** Each CLI tool has its own idiosyncratic version command
and output format. The registry-based approach means adding a new tool requires
only one line in `_CLI_VERSION_SPECS` instead of a new function. The three-state
return (`not available | available but version unknown | available with version`)
handles every edge case: missing binary, broken installation, or unparseable output.
The 10-second timeout on `subprocess.run` prevents a hung CLI from blocking the
entire detection pipeline. Note that kubectl is handled separately by `_kubectl_available()`
in `common.py` because it uses JSON output parsing instead of regex.

---

### Feature Coverage Summary

| Feature | File(s) | Core Detail |
|---------|---------|-------------|
| 16-key detection engine | `detect.py` (641 lines) | Single function drives entire K8s UI |
| Kustomize secret safety | `detect.py` lines 454-483 | Follows resource refs to scan for raw Secrets + envsubst |
| Cluster type heuristics | `cluster.py` lines 20-60 | Cascading exact → prefix → regex → node fallback |
| 337-line state translator | `wizard.py` lines 123-459 | Frontend wizard state → normalized resource list |
| 3-source infra detection | `detect.py` lines 570-641 | resource kinds + annotations + Helm charts |
| CLI version registry | `detect.py` lines 18-61 | Data-driven version extraction for 8 tools |
| 7-layer validation pipeline | `validate*.py` (7 files, 3,936 lines) | Standalone layers from structural to cross-domain |
| Skaffold config deep parse | `wizard_detect.py` lines 11-116 | Profiles, port-forward, build/deploy strategy, tag policy |
| Pod template builder | `pod_builder.py` (559 lines) | Shared by both generate.py and wizard.py paths |
| Full Helm chart generation | `helm_generate.py` (514 lines) | Complete directory with templates, values, helpers |
| Multi-service path-based Ingress | `wizard.py` lines 418-457 | Auto-switches from simple to path-based routing |
| Wizard state persistence | `wizard.py` lines 462-548 | Sanitize → save → load with transient field stripping |
