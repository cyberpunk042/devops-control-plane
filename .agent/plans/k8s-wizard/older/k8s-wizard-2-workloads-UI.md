# K8s Wizard — 2. Workload Types — UI Implementation Spec

## STATUS: 📐 Design spec — pending review before implementation

---

## 0. DESIGN PRINCIPLE

One unified card builder function renders ALL workloads (app AND infra).
The **Kind dropdown** sits at card header level — changing it re-renders the
entire detail panel, because different kinds need fundamentally different fields.

The cards still appear in visual groups (Application Services / Infrastructure Services)
but use identical structure — one builder, one collect, one review renderer.

---

## 1. THE UNIFIED WORKLOAD CARD

### Card Header (always visible)

```
┌──────────────────────────────────────────────────────────────────────┐
│ ☑  🚀 api                                                           │
│      [postgres:16-alpine]       :5432  💾2                          │
│                                                                      │
│   Workload Kind: [ StatefulSet  ▾ ]                                  │
│                                                                      │
│   Heuristic hint:                                                    │
│   💡 Detected database image → StatefulSet recommended               │
└──────────────────────────────────────────────────────────────────────┘
```

#### Header Elements

| Element | ID pattern | Purpose |
|---------|-----------|---------|
| Enable checkbox | `k8s-wk-chk-{id}` | Include/exclude this workload |
| Icon | dynamic | 🚀 app, 🗄️ infra-stateful, ⏰ cron, ⚡ job, 🌐 daemon |
| Service name | static | `<strong>` from compose/module |
| Image badge | static | Short image name from compose |
| Port badge | static | `:portNum` if detected |
| Volume badge | static | 💾N if compose volumes exist |
| **Kind dropdown** | `k8s-wk-kind-{id}` | THE key selector (see §2) |
| Heuristic hint | `k8s-wk-hint-{id}` | Explains why this default was chosen |

#### Kind Dropdown Options

Different option sets depending on source classification:

**For app services (has build context or non-infra image):**
```html
<select id="k8s-wk-kind-{id}">
  <option value="Deployment" selected>Deployment</option>
  <option value="StatefulSet">StatefulSet</option>
  <option value="DaemonSet">DaemonSet</option>
  <option value="Job">Job</option>
  <option value="CronJob">CronJob</option>
  <option value="Skip">Skip (exclude)</option>
</select>
```

**For infra services (well-known image):**
```html
<select id="k8s-wk-kind-{id}">
  <option value="StatefulSet" selected>StatefulSet</option>
  <option value="Deployment">Deployment</option>
  <option value="DaemonSet">DaemonSet</option>
  <option value="Managed">Managed (external)</option>
  <option value="Skip">Skip (exclude)</option>
</select>
```

The **pre-selected** option comes from the classification heuristic (§3).

#### `onchange` Behavior

When kind changes → call `_renderWorkloadDetail(id, newKind)`:
1. Destroys the entire `k8s-wk-detail-{id}` inner HTML
2. Rebuilds it with kind-appropriate fields
3. Updates the card icon
4. Preserves shared values (image, env vars) when possible

---

## 2. KIND-SPECIFIC DETAIL PANELS

The detail panel (`k8s-wk-detail-{id}`) re-renders when kind changes.
Below is the EXACT field set for each kind.

### 2A. Kind = Deployment

```
┌─ detail panel ───────────────────────────────────────────────────────┐
│                                                                      │
│  ── Primary Settings ──                                              │
│  [Image ──────────────] [Port ──] [Replicas] [Service Type ▾]       │
│                                                                      │
│  ── Update Strategy ──                                               │
│  [Strategy ▾ RollingUpdate]  [Max Surge: 1]  [Max Unavail: 1]       │
│  💡 hint when Recreate selected                                      │
│                                                                      │
│  ▸ Resource Limits (from Compose)                [QoS: Burstable]   │
│  ▸ Health Checks (recommended)                                       │
│  ▸ Environment Variables (3 from Compose)                            │
│  ▸ Volume Mounts (2 from Compose)  ← separate PVC resources         │
│  ── Pod Composition ──                                               │
│  ▸ Init Containers (0)                                               │
│  ▸ Sidecar Containers (0)                                            │
│  ▸ Service Mesh (Istio)                                              │
│  ── Dependencies ──                                                  │
│  ☑ postgres  ☑ redis                                                 │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**Fields present:**
| Field | ID | Required | From compose |
|-------|----|----------|-------------|
| Image | `k8s-wk-img-{id}` | ✅ | `svc.image` or `svc.name:latest` |
| Port | `k8s-wk-port-{id}` | ✅ | `svc._port` |
| Replicas | `k8s-wk-replicas-{id}` | ✅ | `svc.deploy.replicas` or `2` |
| Service Type | `k8s-wk-svctype-{id}` | ✅ | `ClusterIP` default |
| Strategy | `k8s-wk-strategy-{id}` | ✅ | `RollingUpdate` (or `Recreate` if named vols) |
| Max Surge | `k8s-wk-maxsurge-{id}` | when RollingUpdate | `1` |
| Max Unavailable | `k8s-wk-maxunavail-{id}` | when RollingUpdate | `1` |

**Collapsible sections:**
1. ▸ Resource Limits — same as today (CPU/Memory req/lim, QoS hint)
2. ▸ Health Checks — readiness + liveness probes
3. ▸ Environment Variables — per-var injection type (hardcoded/variable/secret)
4. ▸ Volume Mounts — PVC (dynamic/static), emptyDir, configMap, secret, hostPath
   - **KEY:** Generates SEPARATE PVC resources (not volumeClaimTemplates)
5. ▸ Init Containers — new (§2G below)
6. ▸ Sidecar Containers — new (§2H below)
7. ▸ Service Mesh (Istio) — new (§2I below)
8. Dependencies — checkbox list of infra services

---

### 2B. Kind = StatefulSet

```
┌─ detail panel ───────────────────────────────────────────────────────┐
│                                                                      │
│  ── Primary Settings ──                                              │
│  [Image ──────────────] [Port ──] [Replicas]                        │
│                                                                      │
│  ── StatefulSet Config ──                                            │
│  Headless Service: [postgres-headless] (auto)  ☑ Also create        │
│                                                  ClusterIP Service   │
│  Pod Management: [OrderedReady ▾]                                    │
│                                                                      │
│  ── Update Strategy ──                                               │
│  [Strategy ▾ RollingUpdate]  Partition: [0]                         │
│   💡 "OnDelete = manual pod-by-pod control"                          │
│                                                                      │
│  ▸ Resource Limits                                                   │
│  ▸ Health Checks                                                     │
│  ▸ Environment Variables                                             │
│  ▸ Persistent Storage (volumeClaimTemplates)  ← DIFFERENT from Dep  │
│  ── Pod Composition ──                                               │
│  ▸ Init Containers (0)                                               │
│  ▸ Sidecar Containers (0)                                            │
│  ▸ Service Mesh (Istio)                                              │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**Fields present (differs from Deployment):**
| Field | ID | Required | Default |
|-------|----|----------|---------|
| Image | `k8s-wk-img-{id}` | ✅ | from compose |
| Port | `k8s-wk-port-{id}` | ✅ | from compose |
| Replicas | `k8s-wk-replicas-{id}` | ✅ | `1` (stateful = conservative) |
| Headless Service name | `k8s-wk-headless-{id}` | ✅ auto | `{name}-headless` |
| Also create ClusterIP | `k8s-wk-clusterip-{id}` | optional checkbox | unchecked |
| Pod Management Policy | `k8s-wk-podmgmt-{id}` | ✅ | `OrderedReady` |
| Update Strategy | `k8s-wk-strategy-{id}` | ✅ | `RollingUpdate` |
| Partition | `k8s-wk-partition-{id}` | when RollingUpdate | `0` |

**Fields NOT present (vs Deployment):**
- ❌ NO Service Type selector (headless is mandatory, optional ClusterIP)
- ❌ NO maxSurge / maxUnavailable (StatefulSet uses partition instead)
- ❌ NO separate PVC volume section

**Volume section is DIFFERENT:**
Instead of "Volume Mounts" (separate PVC resources), StatefulSet shows
**"Persistent Storage (volumeClaimTemplates)"**:

```
▸ Persistent Storage (volumeClaimTemplates)       1 from Compose
  ┌───────────────────────────────────────────────────────────────┐
  │ ☑ data                                                        │
  │   Mount: [/var/lib/postgresql/data]                           │
  │   Size:  [10Gi]  Access: [ReadWriteOnce ▾]                   │
  │   StorageClass: [longhorn ▾]                                  │
  │   💡 One PVC per pod: data-postgres-0, data-postgres-1, …     │
  └───────────────────────────────────────────────────────────────┘
  [+ Add volume claim template]
```

**Critical:** This generates `spec.volumeClaimTemplates[]` INSIDE the StatefulSet,
NOT separate `PersistentVolumeClaim` resources. The collect and backend must handle this.

---

### 2C. Kind = DaemonSet

```
┌─ detail panel ───────────────────────────────────────────────────────┐
│                                                                      │
│  ── Primary Settings ──                                              │
│  [Image ──────────────] [Port (optional) ──]                        │
│                                                                      │
│  ── Update Strategy ──                                               │
│  [Strategy ▾ RollingUpdate]  [Max Unavailable: 1]                   │
│                                                                      │
│  ── Node Selection ──                                                │
│  Node selector:   [key=value, key=value]                            │
│  Tolerations:                                                        │
│    ☑ Run on control-plane nodes                                      │
│    ☑ Run on nodes with NoSchedule taints                             │
│    [+ Add custom toleration]                                         │
│                                                                      │
│  ── Host Access ──                                                   │
│  ☐ Host network (pod shares node's network namespace)                │
│  ☐ Host PID namespace                                                │
│  ☐ Host IPC namespace                                                │
│                                                                      │
│  ▸ Resource Limits                         ← important: limit memory │
│  ▸ Health Checks                                                     │
│  ▸ Environment Variables                                             │
│  ▸ Volume Mounts                           ← typically hostPath      │
│  ── Pod Composition ──                                               │
│  ▸ Init Containers (0)                                               │
│  ▸ Sidecar Containers (0)                                            │
│  ▸ Service Mesh (Istio)                                              │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**Fields present (differs from Deployment):**
| Field | ID | Required | Default |
|-------|----|----------|---------|
| Image | `k8s-wk-img-{id}` | ✅ | from compose |
| Port | `k8s-wk-port-{id}` | optional | from compose or empty |
| Strategy | `k8s-wk-strategy-{id}` | ✅ | `RollingUpdate` (or `OnDelete`) |
| Max Unavailable | `k8s-wk-maxunavail-{id}` | when RollingUpdate | `1` |
| Node Selector | `k8s-wk-nodeselector-{id}` | optional | empty |
| Toleration: control-plane | `k8s-wk-tol-cp-{id}` | checkbox | unchecked |
| Toleration: NoSchedule | `k8s-wk-tol-nosched-{id}` | checkbox | unchecked |
| Host Network | `k8s-wk-hostnet-{id}` | checkbox | unchecked |
| Host PID | `k8s-wk-hostpid-{id}` | checkbox | unchecked |
| Host IPC | `k8s-wk-hostipc-{id}` | checkbox | unchecked |

**Fields NOT present (vs Deployment):**
- ❌ NO Replicas (DaemonSet = 1 per node, auto-scaled by node count)
- ❌ NO Service Type (DaemonSets rarely need Services)
- ❌ NO maxSurge (can't surge — one per node max)
- ❌ NO Dependencies section (DaemonSets are node-level, not app-level)

---

### 2D. Kind = Job

```
┌─ detail panel ───────────────────────────────────────────────────────┐
│                                                                      │
│  ── Primary Settings ──                                              │
│  [Image ──────────────]                                              │
│                                                                      │
│  ── Command ──                                                       │
│  Command: [python manage.py migrate --noinput     ]                 │
│  Args:    [                                        ]  (optional)    │
│                                                                      │
│  ── Job Config ──                                                    │
│  Restart Policy: [Never ▾]       ← Never or OnFailure               │
│  Backoff Limit:  [3   ]          ← retries before failed             │
│  Completions:    [1   ]          ← successful pods needed            │
│  Parallelism:    [1   ]          ← concurrent pods                   │
│  Timeout:        [600 ] seconds  ← activeDeadlineSeconds             │
│  Auto-cleanup:   [3600] seconds  ← ttlSecondsAfterFinished           │
│                                                                      │
│  ▸ Resource Limits                                                   │
│  ▸ Environment Variables                                             │
│  ── Pod Composition ──                                               │
│  ▸ Init Containers (0)                                               │
│  ▸ Sidecar Containers (0)                                            │
│  ▸ Service Mesh (Istio)  ⚠️ Requires K8s ≥ 1.28 native sidecars    │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**Fields present (specific to Job):**
| Field | ID | Required | Default |
|-------|----|----------|---------|
| Image | `k8s-wk-img-{id}` | ✅ | from compose |
| Command | `k8s-wk-cmd-{id}` | ✅ | from compose `command` |
| Args | `k8s-wk-args-{id}` | optional | from compose |
| Restart Policy | `k8s-wk-restart-{id}` | ✅ | `Never` |
| Backoff Limit | `k8s-wk-backoff-{id}` | ✅ | `3` |
| Completions | `k8s-wk-completions-{id}` | ✅ | `1` |
| Parallelism | `k8s-wk-parallel-{id}` | ✅ | `1` |
| Timeout | `k8s-wk-timeout-{id}` | ✅ | `600` |
| TTL After Finished | `k8s-wk-ttl-{id}` | ✅ | `3600` |

**Fields NOT present (vs Deployment):**
- ❌ NO Port (Jobs don't serve traffic)
- ❌ NO Replicas (uses completions/parallelism instead)
- ❌ NO Service Type (no Service resource generated)
- ❌ NO Strategy (no update strategy for Jobs)
- ❌ NO Health Checks (readiness/liveness probes make no sense for run-to-completion)
- ❌ NO Volume Mounts (rarely needed — but possible via optional toggle)
- ❌ NO Dependencies section

**Special:** When Istio is enabled + kind = Job, show warning:
`⚠️ Istio sidecar + Job requires K8s ≥ 1.28 native sidecar support`

---

### 2E. Kind = CronJob

```
┌─ detail panel ───────────────────────────────────────────────────────┐
│                                                                      │
│  ── Primary Settings ──                                              │
│  [Image ──────────────]                                              │
│                                                                      │
│  ── Command ──                                                       │
│  Command: [sh -c "pg_dump ... > /backup/db.sql.gz"              ]   │
│                                                                      │
│  ── Schedule ──                                                      │
│  Cron: [0 2 * * *        ]    ← "Every day at 2:00 AM"             │
│                                  ^ live human-readable preview       │
│                                                                      │
│  ── CronJob Config ──                                                │
│  Concurrency:  [Forbid ▾]   ← Allow / Forbid / Replace             │
│  Deadline:     [300   ] s    ← skip if missed by this much          │
│  Suspend:      ☐             ← pause scheduling                     │
│  Keep history: [3] successful  [1] failed                           │
│                                                                      │
│  ── Inner Job Config ──                                              │
│  Restart Policy: [OnFailure ▾]                                       │
│  Backoff Limit:  [2   ]                                              │
│  Timeout:        [1800] seconds                                      │
│                                                                      │
│  ▸ Resource Limits                                                   │
│  ▸ Environment Variables                                             │
│  ── Pod Composition ──                                               │
│  ▸ Init Containers (0)                                               │
│  ▸ Sidecar Containers (0)                                            │
│  ▸ Service Mesh (Istio)  ⚠️ Requires K8s ≥ 1.28 native sidecars    │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**Fields present (specific to CronJob):**
| Field | ID | Required | Default |
|-------|----|----------|---------|
| Image | `k8s-wk-img-{id}` | ✅ | from compose |
| Command | `k8s-wk-cmd-{id}` | ✅ | from compose |
| Schedule | `k8s-wk-schedule-{id}` | ✅ **REQUIRED** | no default — must be set |
| Concurrency Policy | `k8s-wk-concurrency-{id}` | ✅ | `Forbid` |
| Starting Deadline | `k8s-wk-deadline-{id}` | ✅ | `300` |
| Suspend | `k8s-wk-suspend-{id}` | checkbox | unchecked |
| Success History | `k8s-wk-histsuccess-{id}` | ✅ | `3` |
| Failure History | `k8s-wk-histfail-{id}` | ✅ | `1` |
| Inner: Restart Policy | `k8s-wk-restart-{id}` | ✅ | `OnFailure` |
| Inner: Backoff Limit | `k8s-wk-backoff-{id}` | ✅ | `2` |
| Inner: Timeout | `k8s-wk-timeout-{id}` | ✅ | `1800` |

**Same exclusions as Job** (no port, no replicas, no probes, no service, no strategy).

**Schedule preview:** Live hint under the cron input showing human-readable translation:
- `0 2 * * *` → "Every day at 2:00 AM"
- `*/5 * * * *` → "Every 5 minutes"
- `0 0 * * 0` → "Weekly on Sunday at midnight"

---

### 2F. Kind = Managed (external)

```
┌─ detail panel ───────────────────────────────────────────────────────┐
│                                                                      │
│  ℹ️ This service will be managed OUTSIDE Kubernetes.                 │
│     No K8s resources will be generated for it.                       │
│                                                                      │
│  Provider / Notes: [AWS RDS PostgreSQL                         ]     │
│                                                                      │
│  ── Connection Environment Variables ──                              │
│  These vars will be injected into dependent services as Secrets:     │
│                                                                      │
│  DATABASE_HOST  = [my-db.xxxxx.rds.amazonaws.com]                    │
│  DATABASE_PORT  = [5432                         ]                    │
│  DATABASE_NAME  = [myapp                        ]                    │
│  DATABASE_USER  = [${DATABASE_USER}             ]  ← Secret ref     │
│  DATABASE_PASS  = [${DATABASE_PASS}             ]  ← Secret ref     │
│                                                                      │
│  [+ Add connection variable]                                         │
│                                                                      │
│  💡 Tip: Use Terraform to provision this. See our IaC wizard.        │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**This is NOT a workload.** No manifest generated. But the connection env vars
get cross-referenced into dependent app services' Secret resources.

**Fields present:**
| Field | ID | Required | Default |
|-------|----|----------|---------|
| Provider notes | `k8s-wk-provider-{id}` | optional | empty |
| Connection env vars | `k8s-wk-connvars-{id}` | optional | pre-filled from compose env |

---

### 2G. Kind = Skip

```
┌─ detail panel ───────────────────────────────────────────────────────┐
│                                                                      │
│  ── Excluded ──                                                      │
│  This service will not be deployed to Kubernetes.                    │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

No fields. No collect. Grayed out card.

---

## 3. CLASSIFICATION HEURISTIC — PRE-SELECTING THE KIND

When the wizard loads, each service gets a pre-selected kind based on:

### Decision Logic (from knowledge doc §4)

```javascript
function _classifyWorkloadKind(svc) {
    const img = (svc.image || '').split(':')[0].split('/').pop().toLowerCase();
    const name = svc.name.toLowerCase();

    // 1. Well-known stateful databases → StatefulSet
    if (_INFRA_STATEFULSET.has(img)) return 'StatefulSet';

    // 2. Well-known node-level agents → DaemonSet
    if (_INFRA_DAEMONSET.has(img)) return 'DaemonSet';

    // 3. Compose deploy.mode: global → DaemonSet
    if (svc.deploy?.mode === 'global') return 'DaemonSet';

    // 4. No ports + one-shot signals → Job
    const noPorts = !svc.ports || svc.ports.length === 0;
    const isOneShot = svc.restart === 'no' || svc.restart === 'on-failure';
    const nameIsJob = _JOB_NAME_PATTERNS.some(p => name.includes(p));
    if (noPorts && (isOneShot || nameIsJob)) return 'Job';

    // 5. Default → Deployment
    return 'Deployment';
}
```

### Heuristic Hints (shown under Kind dropdown)

| Detection | Kind | Hint text |
|-----------|------|-----------|
| Image = `postgres:*` | StatefulSet | 💡 Database image detected — StatefulSet for stable identity + per-pod storage |
| Image = `fluentd:*` | DaemonSet | 💡 Log collector detected — DaemonSet for one pod per node |
| `deploy.mode: global` | DaemonSet | 💡 Compose `deploy.mode: global` → maps to DaemonSet |
| No ports + `restart: no` | Job | 💡 No ports + one-shot restart policy → Job (run-to-completion) |
| Name contains `migrate` | Job | 💡 Name suggests migration task → Job |
| Has build context + ports | Deployment | 💡 Application service with ports → Deployment |
| Has build context, no ports | Deployment | 💡 Background worker → Deployment (no Service generated) |

---

## 4. CONDITIONAL FIELD VISIBILITY MATRIX

Master reference of what fields exist per kind:

| Field / Section | Deployment | StatefulSet | DaemonSet | Job | CronJob | Managed | Skip |
|----------------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Image** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| **Port** | ✅ | ✅ | ⚠️ opt | ❌ | ❌ | ❌ | ❌ |
| **Replicas** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Service Type** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Headless Svc name** | ❌ | ✅ auto | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Also ClusterIP** | ❌ | ☐ opt | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Pod Mgmt Policy** | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Strategy** | ✅ Roll/Recr | ✅ Roll/OnDel | ✅ Roll/OnDel | ❌ | ❌ | ❌ | ❌ |
| **maxSurge** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **maxUnavailable** | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Partition** | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Command override** | ⚠️ opt | ⚠️ opt | ⚠️ opt | ✅ | ✅ | ❌ | ❌ |
| **Schedule** | ❌ | ❌ | ❌ | ❌ | ✅ **REQ** | ❌ | ❌ |
| **Concurrency Policy** | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| **Backoff Limit** | ❌ | ❌ | ❌ | ✅ | ✅ inner | ❌ | ❌ |
| **Completions** | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| **Parallelism** | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| **Timeout** | ❌ | ❌ | ❌ | ✅ | ✅ inner | ❌ | ❌ |
| **TTL after finished** | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| **Restart Policy** | implicit | implicit | implicit | ✅ | ✅ inner | ❌ | ❌ |
| **History limits** | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| **Suspend** | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| **Deadline seconds** | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| **Node Selector** | ⚠️ opt | ⚠️ opt | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Tolerations** | ⚠️ opt | ⚠️ opt | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Host Network** | ❌ | ❌ | ☐ opt | ❌ | ❌ | ❌ | ❌ |
| **Host PID** | ❌ | ❌ | ☐ opt | ❌ | ❌ | ❌ | ❌ |
| **Host IPC** | ❌ | ❌ | ☐ opt | ❌ | ❌ | ❌ | ❌ |
| **Provider notes** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| **Connection vars** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| **── Sections ──** | | | | | | | |
| ▸ Resource Limits | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| ▸ Health Checks | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| ▸ Environment Vars | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| ▸ Volume Mounts (PVC) | ✅ | ❌ | ✅ | ⚠️ opt | ⚠️ opt | ❌ | ❌ |
| ▸ volumeClaimTemplates | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| ▸ Init Containers | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| ▸ Sidecar Containers | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| ▸ Service Mesh (Istio) | ✅ | ✅ | ✅ | ✅ ⚠️ | ✅ ⚠️ | ❌ | ❌ |
| Dependencies | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

---

## 5. NEW COLLAPSIBLE SECTIONS — DETAIL SPECS

### 5A. Init Containers Section

```
▸ Init Containers (0)
```
When expanded:
```
  ┌─────────────────────────────────────────────────────────────────┐
  │  No init containers configured.                                 │
  │                                                                 │
  │  Presets:                                                       │
  │  [Wait for TCP ▾]  [Run migrations ▾]  [Fix permissions ▾]     │
  │               [Wait for HTTP ▾]              [Custom ▾]         │
  │                                                                 │
  │  [+ Add init container]                                         │
  └─────────────────────────────────────────────────────────────────┘
```

When an init container is added:
```
  ┌─────────────────────────────────────────────────────────────────┐
  │  ⏳ 1. wait-for-postgres                               [✕ Del] │
  │     Image:   [busybox:1.36              ]                       │
  │     Command: [sh -c "until nc -z postgres-headless 5432; ...]   │
  │     ▸ Resources  CPU req [10m] lim [50m] Mem req [16Mi] lim ... │
  │     ▸ Env Vars (0)                                              │
  │                                                                 │
  │  ⏳ 2. run-migrations                                  [✕ Del] │
  │     Image:   [ghcr.io/user/api:latest   ]  ← same as main      │
  │     Command: [python manage.py migrate --noinput           ]    │
  │     ▸ Resources  CPU req [100m] lim [500m]                      │
  │     ▸ Env Vars (1)  DATABASE_URL → Secret                      │
  │                                                                 │
  │  [+ Add init container]                                         │
  └─────────────────────────────────────────────────────────────────┘
```

**Preset auto-fill when selected:**

| Preset | Image | Command template | Notes |
|--------|-------|-----------------|-------|
| Wait for TCP | `busybox:1.36` | `until nc -z {host} {port}; do echo "Waiting..."; sleep 2; done` | Prompts for host + port |
| Wait for HTTP | `curlimages/curl:latest` | `until curl -sf http://{host}:{port}{path}; do sleep 2; done` | Prompts for URL |
| Run migrations | *same as main container* | *empty — user fills in* | Pre-fills image from main |
| Fix permissions | `busybox:1.36` | `chown -R {uid}:{gid} {path}` | Prompts for uid, gid, path |
| Custom | *empty* | *empty* | Blank form |

**Fields per init container:**
| Field | ID | Required |
|-------|-----|----------|
| Name | `k8s-wk-init-name-{id}-{j}` | ✅ |
| Image | `k8s-wk-init-img-{id}-{j}` | ✅ |
| Command | `k8s-wk-init-cmd-{id}-{j}` | ✅ |
| CPU Request | `k8s-wk-init-cpureq-{id}-{j}` | optional |
| CPU Limit | `k8s-wk-init-cpulim-{id}-{j}` | optional |
| Mem Request | `k8s-wk-init-memreq-{id}-{j}` | optional |
| Mem Limit | `k8s-wk-init-memlim-{id}-{j}` | optional |
| Env vars | reuses `_envRowHtml` | optional |

---

### 5B. Sidecar Containers Section

```
▸ Sidecar Containers (0)
```
When expanded:
```
  ┌─────────────────────────────────────────────────────────────────┐
  │  No sidecar containers configured.                              │
  │                                                                 │
  │  Presets:                                                       │
  │  [Log forwarder ▾]  [Config reloader ▾]  [Metrics exporter ▾]  │
  │  [Auth proxy ▾]     [Cloud SQL Proxy ▾]  [Vault agent ▾]       │
  │                                          [Custom ▾]             │
  │                                                                 │
  │  [+ Add sidecar]                                                │
  └─────────────────────────────────────────────────────────────────┘
```

When a sidecar is added:
```
  ┌─────────────────────────────────────────────────────────────────┐
  │  📎 1. log-forwarder                                    [✕ Del] │
  │     Image:    [fluent/fluent-bit:2.2              ]             │
  │     Command:  [                                    ]  (opt)    │
  │     ☑ Native sidecar (K8s ≥ 1.28 — starts before main,        │
  │       auto-terminates after)                                    │
  │     Shared volume: [shared-logs] mount [/var/log/app] ☑ RO     │
  │     ▸ Resources  CPU req [50m] lim [100m] Mem req [64Mi] ...   │
  │     ▸ Env Vars (0)                                              │
  │                                                                 │
  │  [+ Add sidecar]                                                │
  └─────────────────────────────────────────────────────────────────┘
```

**Key sidecar-specific elements:**

1. **Native sidecar checkbox** (`k8s-wk-sc-native-{id}-{j}`):
   - When ✅: generates as `initContainers[]` with `restartPolicy: Always`
   - When ☐: generates as additional entry in `containers[]`
   - Default: ✅ checked (modern K8s recommended)

2. **Shared volume auto-creation:**
   - When adding a sidecar that shares data (log forwarder, vault agent),
     auto-create an `emptyDir` volume and mount it in both main + sidecar
   - Show the shared mount config inline

**Preset auto-fill:**

| Preset | Image | Native? | Shared vol? | Mount path | ReadOnly? |
|--------|-------|---------|-------------|-----------|-----------|
| Log forwarder | `fluent/fluent-bit:2.2` | ✅ | ✅ `shared-logs` | `/var/log/app` | sidecar: RO |
| Config reloader | `jimmidyson/configmap-reload:v0.13` | ✅ | ❌ | — | — |
| Metrics exporter | `prom/statsd-exporter:v0.26` | ✅ | ❌ | — | — |
| Auth proxy | `oauth2-proxy/oauth2-proxy:v7` | ✅ | ❌ | — | — |
| Cloud SQL Proxy | `gcr.io/cloud-sql-connectors/cloud-sql-proxy:2` | ✅ | ❌ | — | — |
| Vault agent | `hashicorp/vault:1.15` | ✅ | ✅ `vault-secrets` | `/vault/secrets` | sidecar: RW, main: RO |
| Custom | *empty* | ✅ | ❌ | — | — |

**Fields per sidecar:**
| Field | ID | Required |
|-------|-----|----------|
| Name | `k8s-wk-sc-name-{id}-{j}` | ✅ |
| Image | `k8s-wk-sc-img-{id}-{j}` | ✅ |
| Command | `k8s-wk-sc-cmd-{id}-{j}` | optional |
| Native sidecar | `k8s-wk-sc-native-{id}-{j}` | checkbox, default ✅ |
| Shared vol name | `k8s-wk-sc-shvol-{id}-{j}` | when applicable |
| Shared mount path | `k8s-wk-sc-shmount-{id}-{j}` | when applicable |
| Shared ReadOnly | `k8s-wk-sc-shro-{id}-{j}` | checkbox |
| CPU Request/Limit | `k8s-wk-sc-cpureq/lim-{id}-{j}` | optional |
| Mem Request/Limit | `k8s-wk-sc-memreq/lim-{id}-{j}` | optional |
| Ports | `k8s-wk-sc-port-{id}-{j}` | optional |
| Env vars | reuses `_envRowHtml` | optional |

---

### 5C. Service Mesh (Istio) Section

```
▸ Service Mesh (Istio)
```
When expanded:
```
  ┌─────────────────────────────────────────────────────────────────┐
  │  ☐ Enable Istio sidecar injection                              │
  └─────────────────────────────────────────────────────────────────┘
```

When checkbox is checked:
```
  ┌─────────────────────────────────────────────────────────────────┐
  │  ☑ Enable Istio sidecar injection                              │
  │                                                                 │
  │  ℹ️ Istio proxy is injected by the cluster, not defined in      │
  │     your manifest. Only annotations are added.                  │
  │                                                                 │
  │  Proxy Resources:                                               │
  │    CPU:    request [100m ]  limit [500m ]                       │
  │    Memory: request [128Mi]  limit [256Mi]                       │
  │                                                                 │
  │  ▸ Advanced                                                     │
  │    Exclude inbound ports:  [          ]  (comma-separated)      │
  │    Exclude outbound ports: [          ]  (comma-separated)      │
  │    Log level: [warning ▾]                                       │
  │                                                                 │
  │  ⚠️ Job/CronJob + Istio requires K8s ≥ 1.28 (shows only when   │
  │     kind = Job or CronJob)                                      │
  └─────────────────────────────────────────────────────────────────┘
```

**What this generates:** Only pod template annotations, NOT containers:
```yaml
spec.template.metadata.annotations:
  sidecar.istio.io/inject: "true"
  sidecar.istio.io/proxyCPU: "100m"
  sidecar.istio.io/proxyCPULimit: "500m"
  sidecar.istio.io/proxyMemory: "128Mi"
  sidecar.istio.io/proxyMemoryLimit: "256Mi"
  sidecar.istio.io/logLevel: "warning"
  traffic.sidecar.istio.io/excludeInboundPorts: ""
  traffic.sidecar.istio.io/excludeOutboundPorts: ""
```

**Fields:**
| Field | ID | Required | Default |
|-------|-----|----------|---------|
| Enable | `k8s-wk-istio-{id}` | checkbox | unchecked |
| Proxy CPU req | `k8s-wk-istio-cpureq-{id}` | when enabled | `100m` |
| Proxy CPU lim | `k8s-wk-istio-cpulim-{id}` | when enabled | `500m` |
| Proxy Mem req | `k8s-wk-istio-memreq-{id}` | when enabled | `128Mi` |
| Proxy Mem lim | `k8s-wk-istio-memlim-{id}` | when enabled | `256Mi` |
| Exclude inbound | `k8s-wk-istio-exin-{id}` | optional | empty |
| Exclude outbound | `k8s-wk-istio-exout-{id}` | optional | empty |
| Log level | `k8s-wk-istio-log-{id}` | optional | `warning` |

---

## 6. VOLUME HANDLING — THE CRITICAL FORK

The volume UI changes based on kind. This is the most important conditional behavior.

### Kind = Deployment: Volume Mounts (existing 1E behavior)

Uses the existing volume section (PVC dynamic/static, emptyDir, configMap, secret, hostPath).
These generate **separate** `PersistentVolumeClaim` resources.

```yaml
# Generated: separate PVC resource
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: api-data
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 10Gi

# Referenced in Deployment pod spec
volumes:
  - name: data
    persistentVolumeClaim:
      claimName: api-data
```

### Kind = StatefulSet: volumeClaimTemplates (NEW)

Instead of "Volume Mounts", shows "Persistent Storage (volumeClaimTemplates)".
These generate `spec.volumeClaimTemplates[]` **inside** the StatefulSet.

```yaml
# Generated: INLINE in StatefulSet spec — no separate PVC resource
spec:
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: [ReadWriteOnce]
        storageClassName: longhorn
        resources:
          requests:
            storage: 10Gi

# Pod spec only has the mount — volume source is auto-bound from template
containers:
  - volumeMounts:
      - name: data
        mountPath: /var/lib/postgresql/data
```

**UI differences:**
| Aspect | Deployment volumes | StatefulSet volumeClaimTemplates |
|--------|-------------------|--------------------------------|
| Section title | "Volume Mounts" | "Persistent Storage (volumeClaimTemplates)" |
| Volume types offered | PVC, emptyDir, configMap, secret, hostPath | PVC template only (+ emptyDir for scratch) |
| StorageClass | per-volume | per-template |
| Hint | — | "One PVC per pod: data-{name}-0, data-{name}-1, …" |
| Generated resource | Separate PVC resource | Inline in StatefulSet spec |
| PVC naming | `{name}-data` | `data-{name}-{ordinal}` (auto) |

### Kind = DaemonSet: Volume Mounts

Same section as Deployment but defaults to `hostPath` type and shows host access hints.

### Kind = Job / CronJob: Volume Mounts (optional, collapsed)

Rarely needed. Section exists but is more tucked away. Same as Deployment when expanded.

---

## 7. SERVICE RESOURCE GENERATION — PER KIND

The wizard also generates K8s `Service` resources, which vary by kind:

| Kind | Service generated? | Type | Notes |
|------|:-:|:--:|-------|
| **Deployment** | ✅ always (if port set) | User-selected: ClusterIP / NodePort / LoadBalancer | Standard |
| **StatefulSet** | ✅ headless (mandatory) | `clusterIP: None` | Required for stable DNS. Optional additional ClusterIP. |
| **DaemonSet** | ⚠️ only if port set | ClusterIP (auto) | Rare — most DaemonSets don't serve traffic |
| **Job** | ❌ never | — | Jobs don't serve traffic |
| **CronJob** | ❌ never | — | CronJobs don't serve traffic |
| **Managed** | ❌ never | — | Not in K8s |
| **Skip** | ❌ never | — | Excluded |

---

## 8. COLLECT() SCHEMA — UNIFIED

Replace the current split (`services[]` + `infraDecisions[]`) with one unified array:

```javascript
data._workloads = [
    {
        name: 'api',
        kind: 'Deployment',           // from kind dropdown
        source: 'app',                // or 'infra' — for visual grouping only
        image: 'ghcr.io/user/api:latest',
        port: '8080',
        replicas: '2',
        serviceType: 'ClusterIP',
        strategy: 'RollingUpdate',
        maxSurge: '1',
        maxUnavailable: '1',
        resources: { cpu_request, cpu_limit, memory_request, memory_limit },
        readinessProbe: { type, path, port, ... },
        livenessProbe: { type, path, port, ... },
        envVars: [ { key, value, injection, ref } ],
        volumes: [ { type, mountPath, name, size, ... } ],

        // NEW: Multi-container
        initContainers: [
            { name, image, command, resources, env, volumeMounts }
        ],
        sidecars: [
            { name, image, command, native: true, resources, env, volumeMounts, sharedVol }
        ],
        istio: {
            enabled: false,
            proxyCPU: '100m', proxyCPULimit: '500m',
            proxyMemory: '128Mi', proxyMemoryLimit: '256Mi',
            excludeInboundPorts: '', excludeOutboundPorts: '',
            logLevel: 'warning',
        },

        // StatefulSet-specific
        headlessServiceName: null,      // auto: '{name}-headless'
        alsoCreateClusterIP: false,
        podManagementPolicy: null,      // 'OrderedReady' | 'Parallel'
        partition: null,
        volumeClaimTemplates: null,     // [{name, mountPath, size, accessMode, storageClass}]

        // DaemonSet-specific
        nodeSelector: null,             // 'key=value,key=value'
        tolerations: [],                // [{key, operator, value, effect}]
        hostNetwork: false,
        hostPID: false,
        hostIPC: false,

        // Job-specific
        command: null,
        args: null,
        restartPolicy: null,            // 'Never' | 'OnFailure'
        backoffLimit: null,
        completions: null,
        parallelism: null,
        activeDeadlineSeconds: null,
        ttlSecondsAfterFinished: null,

        // CronJob-specific
        schedule: null,                 // cron expression
        concurrencyPolicy: null,        // 'Allow' | 'Forbid' | 'Replace'
        startingDeadlineSeconds: null,
        suspend: false,
        successfulJobsHistoryLimit: null,
        failedJobsHistoryLimit: null,

        // Managed-specific
        providerNotes: null,
        connectionVars: null,

        // Original compose data
        _compose: { ... },
    }
];
```

Only the fields relevant to the selected `kind` are populated. Others are null.

---

## 9. REVIEW STEP — KIND-AWARE RENDERING

The review step shows a summary that reflects the kind:

```
── Application Services ──────────────────────────────────

🚀 Deployment: api                                              [create]
   📦 api (main)              ghcr.io/user/api:latest   :8080
   Strategy: RollingUpdate (maxSurge: 1, maxUnavail: 1)
   Replicas: 2    Service: ClusterIP
   Resources: CPU 100m/500m  Memory 128Mi/256Mi  (Burstable)
   Probes: ✅ readiness (HTTP /health:8080)  ✅ liveness
   Env: 3 vars (1 hardcoded, 1 variable, 1 secret)
   Volumes: 1 PVC (api-data, 10Gi, longhorn)
   ⏳ wait-for-db (init)      busybox:1.36 — wait for postgres:5432
   📎 log-forwarder (sidecar)  fluent-bit:2.2 — native, shares /var/log
   🔷 Istio                   CPU 100m/500m  Mem 128Mi/256Mi

⚡ Job: migrate                                                 [create]
   📦 migrate                 ghcr.io/user/api:latest
   Command: python manage.py migrate --noinput
   Backoff: 3   Completions: 1   Timeout: 600s   Cleanup: 3600s

── Infrastructure Services ────────────────────────────────

🗄️ StatefulSet: postgres                                        [create]
   📦 postgres                postgres:16-alpine   :5432
   Strategy: RollingUpdate (partition: 0)
   Replicas: 1    Headless: postgres-headless
   Pod management: OrderedReady
   volumeClaimTemplates: data (10Gi, RWO, longhorn)
   Env: 2 vars (POSTGRES_DB → ConfigMap, PGDATA → ConfigMap)

☁️ Managed: redis                                               [external]
   Provider: AWS ElastiCache
   Connection vars: REDIS_URL → Secret (injected into dependent services)
```

---

## 10. IMPLEMENTATION ORDER

### Phase 1: Unified card builder + Kind selector
1. Create `_workloadCardHtml(svc, id, kindDefault, source)` replacing both the current app card builder and `_k8sInfraCardHtml`
2. Add Kind dropdown to card header with onchange → `_renderWorkloadDetail(id, kind)`
3. Create `_renderWorkloadDetail(id, kind)` that builds kind-specific HTML
4. Create classification heuristic `_classifyWorkloadKind(svc)`
5. Wire up Section A + Section B to use the unified builder
6. Both sections iterate through their respective lists but call the same builder

### Phase 2: Kind-specific detail panels
7. Deployment panel — reuse existing fields (strategy, resources, probes, env, volumes, deps)
8. StatefulSet panel — headless service, podMgmtPolicy, volumeClaimTemplates
9. DaemonSet panel — node selector, tolerations, host access
10. Job panel — command, backoff, completions, parallelism, timeout, restartPolicy
11. CronJob panel — schedule + concurrency + inner job + all Job fields
12. Managed panel — provider notes + connection env vars
13. Skip panel — empty/disabled state

### Phase 3: Multi-container support
14. Init Containers collapsible section with presets
15. Sidecar Containers collapsible section with presets + native checkbox
16. Auto-generated shared emptyDir volumes for sidecar communication
17. Istio panel with checkbox + resource annotations

### Phase 4: Unified collect + review
18. Unified `collect()` that iterates all `[data-wk-id]` cards
19. Kind-aware field collection (only collect fields present for that kind)
20. Unified review rendering per kind
21. Backward compat: populate legacy `data._services` / `data._infraDecisions` if needed

### Phase 5: Backend manifest generation
22. StatefulSet template (volumeClaimTemplates, headless Service)
23. DaemonSet template (nodeSelector, tolerations, no replicas)
24. Job template (backoffLimit, completions, restartPolicy: Never)
25. CronJob template (schedule, jobTemplate wrapper)
26. Multi-container pod spec assembly (initContainers + sidecars + main)
27. Istio annotations injection

---

## 11. WHAT CHANGES FROM TODAY (BREAKING CHANGES)

### Cards
- **App service cards**: Add Kind dropdown (currently hardcoded "Deployment" badge)
- **Infra service cards**: Replace 3-way radio (StatefulSet/Managed/Skip) with Kind dropdown
- **Infra service cards**: Add full detail panels (resources, probes, volumes) — currently only env vars

### Collect
- **`data._services`** → replaced by unified **`data._workloads`** (or kept for backward compat)
- **`data._infraDecisions`** → merged into `data._workloads`
- **`kind: 'Deployment'`** → no longer hardcoded
- **New fields**: initContainers, sidecars, istio, volumeClaimTemplates, nodeSelector, tolerations, etc.

### Review
- Review step must render different summaries per kind
- New icons: 🚀 Deployment, 🗄️ StatefulSet, 🌐 DaemonSet, ⚡ Job, ⏰ CronJob, ☁️ Managed

### Backend
- `generate_k8s_wizard` needs new manifest templates for each kind
- Volume generation fork: separate PVC vs volumeClaimTemplates
- Service generation fork: standard vs headless vs none

---

## 12. RISK & COMPLEXITY ASSESSMENT

| Area | Risk | Complexity | Notes |
|------|------|-----------|-------|
| Kind dropdown + card rebuild | Low | Medium | Main challenge: preserving values across kind switch |
| Deployment panel | None | Low | Already exists — just wrapped in kind-conditional |
| StatefulSet panel | Medium | High | volumeClaimTemplates is a new storage model |
| DaemonSet panel | Low | Medium | New fields but straightforward |
| Job panel | Low | Medium | New fields, simpler than Deployment |
| CronJob panel | Low | Medium | Wraps Job, adds schedule |
| Managed panel | Low | Low | Mostly text + env vars |
| Init Containers | Medium | Medium | Preset system, dynamic add/remove |
| Sidecars | Medium | High | Native vs traditional, shared volumes, presets |
| Istio | Low | Low | Just a checkbox + annotation inputs |
| Unified collect | Medium | High | Must handle all kind-specific fields |
| Backend generation | High | High | 5 different manifest templates |

**Total estimated scope:** This is a multi-session feature. Suggested chunking:
1. Phase 1-2: Unified card + Kind panels (biggest chunk)
2. Phase 3: Multi-container (independent additive)
3. Phase 4: Unified collect + review (depends on 1-2)
4. Phase 5: Backend generation (depends on 4)
