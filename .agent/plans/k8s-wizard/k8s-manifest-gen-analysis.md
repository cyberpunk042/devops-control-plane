# K8s Manifest Generation — Exhaustive Gap Analysis

> **Date**: 2026-02-14
> **Status**: Analysis — awaiting review before implementation planning
> **Scope**: Everything the wizard UI can configure → what the backend must generate

---

## Table of Contents

1. [Current Architecture](#1-current-architecture)
2. [Exhaustive Field Inventory](#2-exhaustive-field-inventory)
   - [2A. Global Settings](#2a-global-settings)
   - [2B. App Service — Common Fields](#2b-app-service--common-fields-all-kinds)
   - [2C. Deployment-Specific Fields](#2c-deployment-specific-fields)
   - [2D. StatefulSet-Specific Fields](#2d-statefulset-specific-fields)
   - [2E. DaemonSet-Specific Fields](#2e-daemonset-specific-fields)
   - [2F. Job-Specific Fields](#2f-job-specific-fields)
   - [2G. CronJob-Specific Fields](#2g-cronjob-specific-fields)
   - [2H. Health Probes](#2h-health-probes)
   - [2I. Environment Variables](#2i-environment-variables)
   - [2J. Volumes (Main Container)](#2j-volumes-main-container)
   - [2K. Init Containers](#2k-init-containers)
   - [2L. Sidecar Containers](#2l-sidecar-containers)
   - [2M. Companion Containers](#2m-companion-containers)
   - [2N. Service Mesh](#2n-service-mesh)
   - [2O. Dependencies](#2o-dependencies)
   - [2P. Infrastructure Decisions](#2p-infrastructure-decisions)
3. [Collector Shapes](#3-collector-shapes)
4. [Review Step Coverage](#4-review-step-coverage)
5. [Backend Generator Coverage](#5-backend-generator-coverage)
6. [Modules Mode Gap](#6-modules-mode-gap)
7. [Manual Mode Gap](#7-manual-mode-gap)
8. [Proposed Breakdown](#8-proposed-breakdown-into-workable-parts)

---

## 1. Current Architecture

### Three code paths (only one wired to wizard):

| # | Function | Location | Wired? | Capability |
|---|----------|----------|--------|------------|
| A | `setup_k8s` | routes_devops.py:685-743 | ✅ **onComplete calls this** | Bare f-string: writes deployment.yml + service.yml. Ignores `_services`, `_infraDecisions` |
| B | `generate_manifests` | k8s_ops.py:999-1066 | ❌ Old API | Single-service. String templates. Deployment + Service + optional Ingress |
| C | `generate_k8s_wizard` | k8s_ops.py:1363-1577 | ❌ Not called by wizard | Resource-based. Handles all 5 workload kinds + _build_pod_template |

### The flow today:

```
Wizard Step 2 (Configure) collect()
  ↓
data._services = [...]       ← Rich, detailed objects
data._infraDecisions = [...]  ← Rich decision objects
  ↓
Wizard Step 3 (Review) render()
  ↓ All data DISPLAYED properly in review
onComplete() handler (line 6923)
  ↓
POST /api/wizard/setup → setup_k8s action
  ↓
Backend IGNORES _services/_infraDecisions
  ↓ Writes hardcoded deployment.yml + service.yml with ONLY:
  ↓   app_name, image, port, replicas, namespace, service_type
```

### What needs to happen:

```
onComplete()
  ↓
POST /api/k8s/generate/from-state
  ↓
_wizard_state_to_resources(data)   ← NEW: translates service shape → resource shape
  ↓
generate_k8s_wizard(root, resources)  ← ENHANCED: handle all missing features
  ↓
Write all files to disk (k8s/ or data.output_dir)
  ↓
Return file list
```

---

## 2. Exhaustive Field Inventory

### 2A. Global Settings

| Field | Collector ID | Collected Value | Review Step Shows? | Backend Handles? | Manifest Impact |
|-------|-------------|----------------|--------------------|-----------------|-----------------|
| `namespace` | `k8s-namespace` | string, default `"default"` | ✅ L6892 | ❌ Ignored by setup_k8s (sort of — passes to f-string but NOT to `_services`) | Every resource: `metadata.namespace` + separate Namespace resource if non-default |
| `output_dir` | `k8s-output-dir` | string, default `"k8s/"` | ✅ L6891 | ❌ Ignored | Determines filesystem write path |
| `ingress` | `k8s-ingress` | boolean | ✅ L6887 | ❌ Ignored | Generates `Ingress` resource with rules for all services with ports |
| `skaffold` | `k8s-skaffold-toggle` | boolean | ✅ L6893 | ❌ Ignored | Generates `skaffold.yaml` |

### 2B. App Service — Common Fields (All Kinds)

Collected for every service in `_services[]`, shared across all kinds.

| Field | Collector Source | Type | Review Shows? | Generator Has? | Notes |
|-------|-----------------|------|---------------|----------------|-------|
| `name` | `appSvcs[i].name` | string | ✅ | ✅ | → `metadata.name` |
| `kind` | `k8s-svc-kind-${i}` | `Deployment\|StatefulSet\|DaemonSet\|Job\|CronJob\|Skip` | ✅ | ✅ | Determines K8s `kind` |
| `image` | `k8s-svc-img-${i}` | string | ✅ | ✅ | → `containers[0].image` |
| `envVars` | `_collectEnvVars(i)` | array of env objects | ✅ | ⚠️ Partial (see [2I](#2i-environment-variables)) | → env vars, ConfigMap, Secret |
| `resources.cpu_request` | `k8s-svc-cpu-req-${i}` | string \| null | ✅ | ✅ (via spec flattening) | → `resources.requests.cpu` |
| `resources.cpu_limit` | `k8s-svc-cpu-lim-${i}` | string \| null | ✅ | ✅ | → `resources.limits.cpu` |
| `resources.memory_request` | `k8s-svc-mem-req-${i}` | string \| null | ✅ | ✅ | → `resources.requests.memory` |
| `resources.memory_limit` | `k8s-svc-mem-lim-${i}` | string \| null | ✅ | ✅ | → `resources.limits.memory` |
| `_compose` | `appSvcs[i]` | object (raw compose data) | ❌ | N/A (stripped before save) | Transient — not persisted |
| `companions` | `_collectCompanionData(i)` | array | ✅ | ✅ | → `containers[]` in pod spec |
| `dependencies` | `.k8s-dep-${i}:checked` | array of strings | ❌ Not in review | ❌ Not in generator | **Possibly no manifest impact** — just informational? Or should generate `wait-for` init containers? |

### 2C. Deployment-Specific Fields

Collected when `selectedKind === 'Deployment'` (the default / else branch).

| Field | Collector Source | Type | Review Shows? | Generator Has? | Manifest Impact |
|-------|-----------------|------|---------------|----------------|-----------------|
| `port` | `k8s-svc-port-${i}` | string (int) | ✅ | ✅ | → `containerPort`, Service `targetPort` |
| `replicas` | `k8s-svc-replicas-${i}` | string (int) | ✅ | ✅ | → `spec.replicas` |
| `serviceType` | `k8s-svc-type-${i}` | `ClusterIP\|NodePort\|LoadBalancer` | ✅ | ❌ Hardcoded | → Separate `Service` resource `.spec.type` |
| `strategy` | `k8s-svc-strategy-${i}` | `RollingUpdate\|Recreate` | ✅ | ⚠️ Hardcoded to RollingUpdate if replicas>1 | → `spec.strategy.type` |
| `maxSurge` | `k8s-svc-maxsurge-${i}` | string (int) | ✅ | ⚠️ Hardcoded to 1 | → `spec.strategy.rollingUpdate.maxSurge` |
| `maxUnavailable` | `k8s-svc-maxunavail-${i}` | string (int) | ✅ | ⚠️ Hardcoded to 1 | → `spec.strategy.rollingUpdate.maxUnavailable` |
| `readinessProbe` | `_collectProbe(...)` | probe object \| null | ✅ | ❌ **NOT GENERATED** | → `containers[0].readinessProbe` |
| `livenessProbe` | `_collectProbe(...)` | probe object \| null | ✅ | ❌ **NOT GENERATED** | → `containers[0].livenessProbe` |
| `volumes` | `_collectVolumes(i)` | array of vol objects | ✅ | ⚠️ **Partially** (see [2J](#2j-volumes-main-container)) | → `spec.volumes[]` + `volumeMounts[]` + maybe PVC resources |

### 2D. StatefulSet-Specific Fields

Collected when `selectedKind === 'StatefulSet'`.

| Field | Collector Source | Type | Review Shows? | Generator Has? | Manifest Impact |
|-------|-----------------|------|---------------|----------------|-----------------|
| `port` | same as Deployment | string (int) | ✅ | ✅ | → `containerPort` |
| `replicas` | same | string (int) | ✅ | ✅ | → `spec.replicas` |
| `headlessServiceName` | `k8s-svc-ss-headless-${i}` | string | ✅ | ⚠️ Uses `{name}-headless` hardcoded | → `spec.serviceName`, headless Service name |
| `podManagementPolicy` | `k8s-svc-ss-podmgmt-${i}` | `OrderedReady\|Parallel` | ✅ | ❌ **NOT SET** | → `spec.podManagementPolicy` |
| `alsoCreateClusterIP` | `k8s-svc-ss-clusterip-${i}` | boolean | ✅ (in headless line) | ❌ **NOT HANDLED** | → Generate EXTRA `Service` resource (ClusterIP) |
| `strategy` | `k8s-svc-ss-strategy-${i}` | `RollingUpdate\|OnDelete` | ✅ | ❌ Not set | → `spec.updateStrategy.type` |
| `partition` | `k8s-svc-ss-partition-${i}` | int \| null | ✅ | ❌ Not set | → `spec.updateStrategy.rollingUpdate.partition` |
| `readinessProbe` | `_collectProbe(...)` | probe object \| null | ✅ | ❌ **NOT GENERATED** | Same as Deployment |
| `livenessProbe` | `_collectProbe(...)` | probe object \| null | ✅ | ❌ | Same |
| `volumeClaimTemplates` | VCT rows | array of VCT objects | ✅ | ✅ | → `spec.volumeClaimTemplates[]` |

**VCT object shape** (collected at line 6302-6323):
```js
{ name, mountPath, size, accessMode, storageClass }
```

**Generator handles VCTs** ✅ at k8s_ops.py:1441-1458 — same shape accepted.

### 2E. DaemonSet-Specific Fields

Collected when `selectedKind === 'DaemonSet'`.

| Field | Collector Source | Type | Review Shows? | Generator Has? | Manifest Impact |
|-------|-----------------|------|---------------|----------------|-----------------|
| `port` | `k8s-svc-port-${i}` | string (int) | ✅ (Service if port set) | ✅ | → `containerPort` |
| `strategy` | `k8s-svc-ds-strategy-${i}` | `RollingUpdate\|OnDelete` | ✅ | ❌ Not set | → `spec.updateStrategy.type` |
| `maxUnavailable` | `k8s-svc-ds-maxunavail-${i}` | string \| null | ✅ | ❌ Not set | → `spec.updateStrategy.rollingUpdate.maxUnavailable` |
| `nodeSelector` | `k8s-svc-ds-nodeselector-${i}` | string (comma-separated k=v) | ✅ | ⚠️ Raw pass-through | → `spec.template.spec.nodeSelector` (needs parsing from string to dict) |
| `tolerations` | checkbox-based | array of toleration objects | ✅ | ⚠️ Raw pass-through | → `spec.template.spec.tolerations[]` |
| `hostNetwork` | `k8s-svc-ds-hostnet-${i}` | boolean | ✅ | ❌ **NOT SET** | → `spec.template.spec.hostNetwork` |
| `hostPID` | `k8s-svc-ds-hostpid-${i}` | boolean | ✅ | ❌ **NOT SET** | → `spec.template.spec.hostPID` |
| `hostIPC` | `k8s-svc-ds-hostipc-${i}` | boolean | ✅ | ❌ **NOT SET** | → `spec.template.spec.hostIPC` |
| `readinessProbe` | `_collectProbe(...)` | probe object \| null | ❌ Not in DaemonSet review section | ❌ | Same as Deployment |
| `livenessProbe` | `_collectProbe(...)` | probe object \| null | ❌ | ❌ | Same |
| `volumes` | `_collectVolumes(i)` | array of vol objects | ❌ Not in DaemonSet review section | ⚠️ Partial | Same as Deployment |

### 2F. Job-Specific Fields

Collected when `selectedKind === 'Job'`.

| Field | Collector Source | Type | Review Shows? | Generator Has? | Manifest Impact |
|-------|-----------------|------|---------------|----------------|-----------------|
| `command` | `k8s-svc-job-cmd-${i}` | string | ✅ | ❌ **NOT SET** | → `containers[0].command` |
| `args` | `k8s-svc-job-args-${i}` | string | ✅ (in review value) | ❌ **NOT SET** | → `containers[0].args` |
| `restartPolicy` | `k8s-svc-job-restart-${i}` | `Never\|OnFailure` | ❌ Not in review | ✅ (defaults Never) | → `spec.template.spec.restartPolicy` |
| `backoffLimit` | `k8s-svc-job-backoff-${i}` | int | ✅ | ✅ | → `spec.backoffLimit` |
| `completions` | `k8s-svc-job-completions-${i}` | int | ✅ (if >1) | ✅ | → `spec.completions` |
| `parallelism` | `k8s-svc-job-parallelism-${i}` | int | ✅ (if >1) | ✅ | → `spec.parallelism` |
| `activeDeadlineSeconds` | `k8s-svc-job-timeout-${i}` | int \| undefined | ✅ | ✅ | → `spec.activeDeadlineSeconds` |
| `ttlSecondsAfterFinished` | `k8s-svc-job-ttl-${i}` | int | ✅ | ✅ | → `spec.ttlSecondsAfterFinished` |

### 2G. CronJob-Specific Fields

Collected when `selectedKind === 'CronJob'` (all Job fields + these).

| Field | Collector Source | Type | Review Shows? | Generator Has? | Manifest Impact |
|-------|-----------------|------|---------------|----------------|-----------------|
| `schedule` | `k8s-svc-cron-schedule-${i}` | string (cron expr) | ✅ | ✅ | → `spec.schedule` |
| `concurrencyPolicy` | `k8s-svc-cron-concurrency-${i}` | `Forbid\|Allow\|Replace` | ✅ | ✅ | → `spec.concurrencyPolicy` |
| `suspend` | `k8s-svc-cron-suspend-${i}` | boolean | ✅ (if true) | ❌ **NOT SET** | → `spec.suspend` |
| `successfulJobsHistoryLimit` | `k8s-svc-cron-success-${i}` | int | ✅ | ✅ | → `spec.successfulJobsHistoryLimit` |
| `failedJobsHistoryLimit` | `k8s-svc-cron-failed-${i}` | int | ✅ | ✅ | → `spec.failedJobsHistoryLimit` |
| `startingDeadlineSeconds` | `k8s-svc-cron-deadline-${i}` | int \| undefined | ✅ (if set) | ❌ **NOT SET** | → `spec.startingDeadlineSeconds` |

### 2H. Health Probes

**Probe object shape** (from `_collectProbe`, line 6195-6214):

```js
{
  type: "http" | "tcp" | "exec",
  initialDelaySeconds: 0,
  periodSeconds: 10,
  // HTTP only:
  path: "/health",
  port: 8080,
  // TCP only:
  port: 8080,
  // Exec only:
  command: "...",
  // All:
  extra: 3,   // used as failureThreshold or timeoutSeconds?
}
```

**Collected for**: Deployment, StatefulSet, DaemonSet (NOT Job/CronJob — they don't have probes in the UI).

**Generator status**: `_build_pod_template` has zero probe logic. **Completely missing.**

**K8s manifest output needed**:
```yaml
readinessProbe:
  httpGet:            # or tcpSocket or exec
    path: /health
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 3  # from the 'extra' field
```

### 2I. Environment Variables

**EnvVar object shape** (from `_collectEnvVars`, line 3429-3463):

```js
{
  key: "DB_HOST",              // The env var name
  type: "hardcoded" | "variable" | "secret",
  value: "postgres",           // Hardcoded value (for hardcoded type)
  varName: "${DB_HOST}" | null, // External reference (for variable/secret types)
  createInVault: false,        // Whether to create a vault secret
  newValue: "",                // Value for new vault secret
}
```

**What needs to happen for each type**:

| Type | In Container Spec | Separate Resource | ConfigMap/Secret Name Convention |
|------|-------------------|-------------------|----------------------------------|
| `hardcoded` | `env: [{name: KEY, valueFrom: {configMapKeyRef: ...}}]` | Generate `ConfigMap` with `data: {KEY: value}` | `{svc-name}-config` |
| `variable` | `env: [{name: KEY, valueFrom: {configMapKeyRef: ...}}]` | Generate `ConfigMap` with `data: {KEY: "${VAR}"}` placeholder | `{svc-name}-config` |
| `secret` | `env: [{name: KEY, valueFrom: {secretKeyRef: ...}}]` | Generate `Secret` with `stringData: {KEY: "CHANGE_ME"}` placeholder | `{svc-name}-secrets` |

**Generator status** (`_build_env_vars`, line 1784-1846):
- ✅ Handles wizard format (type-based routing)
- ⚠️ BUT: derives Secret/ConfigMap names from `varName` (e.g., `${DB_PASS}` → `db-pass`), NOT from the service-name convention. **Mismatch with what the Review step shows** (`ConfigMap: api-config`, `Secret: api-secrets`).
- ❌ Does NOT generate the ConfigMap/Secret resources themselves — only the `configMapKeyRef`/`secretKeyRef` references.

**Vault integration** (`createInVault`/`newValue`):
- ❌ Not handled by generator. These fields should trigger vault secret creation at execution time — separate concern but needs to be tracked.

### 2J. Volumes (Main Container)

**Volume object shape** (from `_collectVolumes`, line 3854-3906):

Per volume type:

```js
// pvc-dynamic
{
  type: "pvc-dynamic",
  mountPath: "/data",
  name: "data-0",
  size: "10Gi",
  accessMode: "ReadWriteOnce",
  storageClass: "longhorn" | "" | custom,
  longhornConfig: { replicas: "3", dataLocality: "best-effort" },  // if storageClass contains 'longhorn'
}

// pvc-static
{
  type: "pvc-static",
  mountPath: "/data",
  name: "data-0",
  size: "10Gi",
  accessMode: "ReadWriteOnce",
  pvName: "existing-pv-name",
  storageClass: ...,
}

// emptyDir
{
  type: "emptyDir",
  mountPath: "/cache",
  medium: "" | "Memory",
  sizeLimit: "" | "1Gi",
}

// configMap
{
  type: "configMap",
  mountPath: "/etc/config",
  configMapName: "my-cm",
  key: "" | "specific-key",  // optional: mount single key
}

// secret
{
  type: "secret",
  mountPath: "/etc/secrets",
  secretName: "my-secret",
  key: "" | "tls.crt",  // optional: mount single key
}

// hostPath
{
  type: "hostPath",
  mountPath: "/host/data",
  hostPath: "/var/data",
  hostType: "DirectoryOrCreate" | "Directory" | "File" | "Socket" | ...,
}
```

**Generator status**:
- ❌ `_build_pod_template` does NOT process main-container wizard volumes at all
- ✅ It handles: companion volumes (lines 1703-1738), sidecar shared volumes (lines 1649-1658)
- ❌ Does NOT generate standalone PVC manifests for `pvc-dynamic`/`pvc-static`
- ❌ Does NOT handle Longhorn config annotations on PVCs
- ❌ `emptyDir` has no name field in collector output — need to synthesize one

### 2K. Init Containers

**Init container object shape** (collected at line 6337-6351):

```js
{
  name: "init-0" | "migrate",
  image: "busybox:1.36",
  command: "echo hello",
}
```

**Generator status**: ✅ Handled in `_build_pod_template` (lines 1624-1633). Shape matches.

### 2L. Sidecar Containers

**Sidecar object shape** (collected at line 6353-6379):

```js
{
  name: "sidecar-0" | "log-shipper",
  image: "fluentbit:latest",
  command: "" | "tail -f /var/log/app.log",
  nativeSidecar: true,  // K8s ≥1.28 native sidecar (initContainers + restartPolicy: Always)
  sharedVolume: "logs",       // optional: emptyDir name
  sharedMount: "/var/log",    // optional: mount path in both main + sidecar
}
```

**Generator status**: ✅ Handled in `_build_pod_template` (lines 1639-1666). Shape matches.

### 2M. Companion Containers

**Companion object shape** (collected at line 6091-6173):

```js
{
  name: "redis",
  image: "redis:7",
  port: "6379",
  env: [/* same shape as envVars */],
  resources: {
    cpu_request: "50m" | null,
    cpu_limit: "200m" | null,
    memory_request: "64Mi" | null,
    memory_limit: "128Mi" | null,
  } | null,
  volumes: [
    { name: "vol-name", type: "emptyDir" | "pvc-*" | ..., mountPath: "/data" },
  ],
  dependsOn: "postgres" | "__main__" | null,
  dependsOnPort: "5432" | null,
}
```

**Generator status**: ✅ Handled extensively in `_build_pod_template` (lines 1672-1761):
- ✅ Container spec with image, port, resources
- ✅ Env vars via `_build_env_vars`
- ✅ Volume mounts (adds pod-level volumes)
- ✅ Startup dependency → wait-for init container

### 2N. Service Mesh

**Mesh object shape** (collected at line 6381-6395):

```js
{
  provider: "istio" | "linkerd" | "consul" | "kuma",
  proxyCpuRequest: "100m",
  proxyCpuLimit: "500m",
  proxyMemRequest: "128Mi",
  proxyMemLimit: "256Mi",
  excludeInbound: "" | "8080,9090",
  excludeOutbound: "" | "3306",
  logLevel: "warning",
}
```

**Generator status**: ✅ Fully handled:
- `_build_mesh_annotations` (lines 1893-1931) — correct per-provider annotation mapping
- `_MESH_ANNOTATION_PREFIXES` (lines 1849-1890) — Istio, Linkerd, Consul, Kuma

### 2O. Dependencies

**Shape** (collected at line 6233-6238 / 6416-6421):

```js
dependencies: ["postgres", "redis"]  // names of infra services
```

**Review step**: ❌ Not shown in review
**Generator**: ❌ Not handled

**Question**: What should dependencies DO in manifests? Options:
1. Do nothing (informational only — used for state persistence UX)
2. Generate `wait-for` init containers (like companions do)
3. Generate NetworkPolicy allowing traffic to/from dependencies
4. Generate annotations/labels for service discovery

This needs a decision.

### 2P. Infrastructure Decisions

**Infra decision object shape** (collected at line 6436-6462):

```js
{
  name: "postgres",
  kind: "StatefulSet" | "Managed" | "Skip",  // user's decision
  image: "postgres:16",
  port: "5432",
  envVars: [/* same shape */],
  _compose: { /* raw compose data — stripped before save */ },
  volumes: [/* same shape — only if kind !== "Managed" */],
  providerNotes: "AWS RDS" // only if kind === "Managed"
}
```

**What each decision generates**:

| Decision | Workload | Service | ConfigMap | Secret | PVC | Notes |
|----------|----------|---------|-----------|--------|-----|-------|
| `StatefulSet` | ✅ StatefulSet | ✅ Headless Service | ✅ If env vars | ✅ If secret env vars | ✅ If volumes | Full generation like an app service |
| `Managed` | ❌ | ❌ | ✅ Connection vars as ConfigMap | ✅ Connection secrets | ❌ | Only ConfigMap/Secret for dependent services |
| `Skip` | ❌ | ❌ | ❌ | ❌ | ❌ | Filtered out by collector |

**Generator status**:
- ✅ `generate_k8s_wizard` can handle StatefulSet resources
- ❌ The wizard never sends infra as resources — they're in a separate array
- ❌ "Managed" kind's ConfigMap/Secret for connection vars → not generated
- ❌ Managed providerNotes → could go as annotation/comment, currently ignored

---

## 3. Collector Shapes — Mode Comparison

### Compose mode (line 6176-6398) — MOST COMPLETE

Collects ALL fields documented above. This is the fully-featured path.

### Modules mode (line 6399-6423) — SIGNIFICANTLY INCOMPLETE

Only collects:
- `name`, `kind`, `image`, `port`, `replicas`, `serviceType`
- `companions`, `dependencies`

**MISSING in modules mode**:
- ❌ `envVars` — not collected
- ❌ `resources` (CPU/memory) — not collected
- ❌ `strategy`, `maxSurge`, `maxUnavailable` — not collected
- ❌ `readinessProbe`, `livenessProbe` — not collected
- ❌ `volumes` — not collected
- ❌ `initContainers` — not collected
- ❌ `sidecars` — not collected
- ❌ `mesh` — not collected
- ❌ All StatefulSet/DaemonSet/Job/CronJob-specific fields — not collected
- ❌ Workload kind only goes through basic path, no kind-specific branching

This means the UI renders all these input fields, but the collect step ignores them in modules mode.

### Manual mode (line 6424-6434) — MINIMAL

Only collects: `name`, `kind`, `image`, `port`, `replicas`, `serviceType`.

No infra, no compounds, no probes, no volumes, nothing advanced.

---

## 4. Review Step Coverage

The Review step (line 6525-6921) is comprehensive for compose mode. It renders:

| Feature | Lines | Status |
|---------|-------|--------|
| Deployment workload + strategy | 6649-6667 | ✅ |
| StatefulSet workload + headless + VCTs | 6614-6648 | ✅ |
| DaemonSet workload + node config | 6579-6613 | ✅ |
| Job workload + job settings | 6536-6578 | ✅ |
| CronJob settings | 6565-6578 | ✅ |
| Service resource | 6661-6667 | ✅ |
| Companion containers | 6669-6686 | ✅ |
| Init containers | 6687-6698 | ✅ |
| Sidecar containers | 6700-6710 | ✅ |
| Service mesh | 6711-6722 | ✅ |
| Resource limits | 6723-6738 | ✅ |
| Health probes | 6739-6759 | ✅ |
| ConfigMap (env vars) | 6760-6773 | ✅ |
| Secret (env vars) | 6774-6782 | ✅ |
| Vault creation | 6783-6794 | ✅ |
| Volume mounts (all types) | 6795-6841 | ✅ |
| Infra decisions (Managed/StatefulSet) | 6844-6884 | ✅ |
| Ingress | 6887-6889 | ✅ |
| Output directory | 6891 | ✅ |
| Namespace | 6892 | ✅ |
| Skaffold | 6893-6895 | ✅ |
| Multi-service warning | 6908-6910 | ✅ (should be removed when generation is complete) |
| CI/CD upsell | 6912-6918 | ✅ (fine as-is) |
| Dependencies | ❌ Not shown | Missing |

---

## 5. Backend Generator Coverage Summary

### `_build_pod_template` (k8s_ops.py:1580-1781):

| Feature | Status | Lines | Gap |
|---------|--------|-------|-----|
| Main container (name, image, port) | ✅ | 1590-1595 | — |
| Resource limits/requests | ✅ | 1597-1612 | — |
| Env vars (multi-format) | ✅ | 1614-1617 | ConfigMap/Secret name mismatch |
| Init containers | ✅ | 1623-1633 | — |
| Sidecar containers + shared volumes | ✅ | 1635-1666 | — |
| Companion containers + deps + volumes | ✅ | 1671-1761 | — |
| Pod volumes + main container volumeMounts | ⚠️ | 1762-1766 | Only handles sidecar shared vols + companion vols. **Main-container wizard volumes NOT processed** |
| Mesh annotations | ✅ | 1774-1779 | — |
| **Health probes** | ❌ | — | **Completely missing** |
| **DaemonSet host access** | ❌ | — | hostNetwork, hostPID, hostIPC not set |
| **Job command/args override** | ❌ | — | Job command/args not set on container |
| **Command-based container** | ❌ | — | If svc.command, should override container CMD |

### `generate_k8s_wizard` (k8s_ops.py:1363-1577):

| Feature | Status | Lines | Gap |
|---------|--------|-------|-----|
| Deployment with replicas | ✅ | 1414-1429 | — |
| Deployment strategy from wizard | ⚠️ | 1422-1429 | Hardcoded RollingUpdate(1/1) when replicas>1, ignores wizard maxSurge/maxUnavailable/Recreate |
| StatefulSet with VCTs | ✅ | 1431-1458 | — |
| StatefulSet podManagementPolicy | ❌ | — | Not set |
| StatefulSet updateStrategy | ❌ | — | Not set (OnDelete/partition) |
| DaemonSet with selector/tolerations | ✅ | 1460-1470 | — |
| DaemonSet updateStrategy | ❌ | — | Not set (RollingUpdate maxUnavailable / OnDelete) |
| Job with all fields | ✅ | 1472-1491 | — |
| CronJob with all fields | ✅ | 1493-1512 | — |
| CronJob suspend | ❌ | — | Not set |
| CronJob startingDeadlineSeconds | ❌ | — | Not set |
| Service (all types) | ✅ | 1514-1525 | — |
| ConfigMap | ✅ | 1527-1528 | — |
| Secret | ✅ | 1530-1532 | — |
| Ingress | ✅ | 1534-1555 | — |
| Namespace | ✅ | 1557-1559 | — |
| **PersistentVolumeClaim** | ❌ | — | Kind not handled |
| **File naming with output_dir** | ❌ | 1568 | Hardcoded `k8s/` prefix |
| **File writing to disk** | ❌ | — | Returns dicts but doesn't write files. `setup_k8s` writes files. |

---

## 6. Modules Mode Gap

This is a **frontend collector bug** — the modules mode collect loop (line 6399-6423) doesn't collect any of the advanced fields that the UI renders. This means users can configure probes, resources, volumes, etc. in the UI, click Next, and all that configuration is **silently lost**.

This needs fixing in `_integrations_setup_modals.html` — the modules collector should use the same comprehensive logic as compose mode.

---

## 7. Manual Mode Gap

Manual mode (line 6424-6434) is extremely minimal. It only collects 6 basic fields. This is likely intentional — manual mode is a simple scaffolding path — but it should be documented.

---

## 8. Proposed Breakdown into Workable Parts

Given the scope, I recommend breaking this into **5 independent parts**, each testable on its own:

### Part 1: Generator Enhancements (`_build_pod_template` + `generate_k8s_wizard`)

**Scope**: Make the existing generator handle ALL features the wizard can configure.

**Sub-tasks**:
- 1A. Add `_build_probe()` helper + wire into `_build_pod_template`
- 1B. Add main-container wizard volume processing to `_build_pod_template`
- 1C. Add `hostNetwork`/`hostPID`/`hostIPC` to `_build_pod_template`
- 1D. Add Job `command`/`args` to container spec in `_build_pod_template`
- 1E. Fix Deployment strategy (use wizard values not hardcoded)
- 1F. Add StatefulSet `podManagementPolicy`, `updateStrategy`
- 1G. Add DaemonSet `updateStrategy`
- 1H. Add CronJob `suspend`, `startingDeadlineSeconds`
- 1I. Add `PersistentVolumeClaim` kind handling
- 1J. Support `output_dir` parameter in file paths

**Risk**: Medium — modifying existing code
**Can be tested**: Via direct `POST /k8s/generate/wizard` API calls with crafted payloads

### Part 2: Translator Function (`_wizard_state_to_resources`)

**Scope**: Convert `{_services, _infraDecisions, namespace, ...}` → `resources[]` for the generator.

**Sub-tasks**:
- 2A. Service → Workload resource
- 2B. Service → Service resource (Deployment/DaemonSet with port)
- 2C. Service → Headless Service (StatefulSet)
- 2D. Service → Extra ClusterIP Service (StatefulSet with alsoCreateClusterIP)
- 2E. Service envVars → ConfigMap resource
- 2F. Service envVars → Secret resource
- 2G. Service volumes → PVC resources (for pvc-dynamic)
- 2H. Infra (StatefulSet decision) → same expansion as an app service
- 2I. Infra (Managed decision) → ConfigMap + Secret for connection vars
- 2J. Global namespace → Namespace resource (if non-default)
- 2K. Global ingress → Ingress resource

**Risk**: Medium-High — complex mapping with many edge cases
**Can be tested**: Unit tests on the function with sample wizard state payloads

### Part 3: Skaffold Generation

**Scope**: Generate `skaffold.yaml` from wizard state.

**Sub-tasks**:
- 3A. `_generate_skaffold()` function
- 3B. Wire into the generation flow

**Risk**: Low — purely additive
**Can be tested**: Verify YAML output

### Part 4: Backend Route + File Writing ✅ DONE

**Scope**: New endpoint that ties translator + generator + disk writing together.

**Sub-tasks**:
- ✅ 4A. `setup_k8s` action calls `wizard_state_to_resources` → `generate_k8s_wizard`
- ✅ 4B. File writing logic (mkdir + write each GeneratedFile to disk)
- ✅ 4C. Overwrite handling — `overwrite=False` skips existing files
- ✅ 4D. Return file list + skipped list to frontend

### Part 5: Frontend Wiring + Modules/Manual Mode Fixes ✅ DONE

**Scope**: Fix the frontend to actually call the new backend.

**Sub-tasks**:
- ✅ 5A. `onComplete` handler sends full wizard state to backend
- ✅ 5B. Modules-mode collector captures all fields (full parity with compose)
- ✅ 5C. "Multi-service in progress" warning removed from review step
- ✅ 5D. Dependencies shown in review step display
- 5E. Error handling from endpoint in the wizard (basic — uses apiPost defaults)

---

## 9. Open Questions — Resolution Status

1. **Dependencies**: ✅ **Decided** — generates `wait-for` init containers (busybox nc -z), plus `envFrom` injection for Managed infra ConfigMap/Secret. Skips wait-for for Managed infra (no K8s Service). Uses correct DNS for StatefulSet infra.

2. **Output directory**: ✅ **Decided** — uses `data.output_dir` throughout, default `k8s/`.

3. **File structure**: ✅ **Decided** — flat `k8s/{name}-{kind}.yaml`.

4. **Overwrite behavior**: ✅ **Implemented** — `overwrite=False` on GeneratedFile. Route skips existing files and reports them in `files_skipped`. First run creates; re-run skips existing.

5. **ConfigMap/Secret naming**: ✅ **Decided** — `{svc}-config` / `{svc}-secrets` via `_svc_env_to_resources()`.

6. **Vault integration**: ❌ **Not in scope** — no Vault API calls during generation. Secrets use `CHANGE_ME` placeholder.

7. **Managed infra injection**: ✅ **Decided** — envFrom refs injected into dependent service container specs by translator.

8. **Modules mode**: ✅ **Fixed** — modules collector now has full parity with compose mode.

9. **Longhorn config**: ✅ **Implemented** — PVCs with `longhornConfig` get `longhorn.io/number-of-replicas` and `longhorn.io/data-locality` annotations.
