# K8s Wizard — 2. Workload Types — Deep Knowledge & Plan

## STATUS: 📖 Knowledge phase — research complete, not yet implemented

---

## 0. THE REAL QUESTION

The current plan frames infrastructure services as "StatefulSet vs Managed vs Skip."
That's incomplete. The real question for **every** service (app AND infra) is:

> **What workload kind should this container run as?**

K8s has 5 workload controllers, each with fundamentally different:
- Pod lifecycle semantics
- Scaling model
- Update strategy options
- Storage handling
- Network identity
- Restart behavior
- Manifest shape

The wizard must understand all 5 to offer intelligent defaults.

---

## 1. THE FIVE K8S WORKLOAD KINDS

### Overview Matrix

| Kind | API Group | Purpose | Runs | Replicas | Identity | Storage | Typical Use |
|------|-----------|---------|------|----------|----------|---------|-------------|
| **Deployment** | `apps/v1` | Long-running stateless services | Continuously | User-set (default 1) | Interchangeable (random pod names) | Shared PVC or none | API servers, web apps, workers |
| **StatefulSet** | `apps/v1` | Long-running stateful services | Continuously | User-set (default 1) | Stable, ordered (`pod-0`, `pod-1`, …) | Per-pod PVC via `volumeClaimTemplates` | Databases, message queues, distributed systems |
| **DaemonSet** | `apps/v1` | One pod per node (or subset) | Continuously | 1 per matching node (auto) | Per-node | hostPath or shared | Log collectors, monitoring agents, node-level services |
| **Job** | `batch/v1` | Run-to-completion (one-shot) | Until success | `completions` count | None | Usually none | DB migrations, data imports, backups |
| **CronJob** | `batch/v1` | Scheduled run-to-completion | On cron schedule | Per-execution | None | Usually none | Scheduled backups, cleanup, reports |

---

## 2. EACH WORKLOAD KIND IN DETAIL

### 2A. Deployment

**What it is:** The most common workload. Manages a ReplicaSet, which ensures N identical pods are running. Pods are interchangeable — any pod can handle any request.

**Key characteristics:**
- Pods get random names: `api-7d8f9c6b4f-x2k9p`
- Rolling updates: new pods created, old pods terminated gradually
- No guaranteed ordering of pod start/stop
- Storage: can reference PVCs, but all replicas share the same PVC (or each gets its own via separate PVC resources — NOT via templates)
- If a pod dies, a new one replaces it (different name, same config)

**Manifest shape:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: default
spec:
  replicas: 2
  strategy:
    type: RollingUpdate          # or Recreate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: ghcr.io/user/api:latest
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 256Mi
          readinessProbe:
            httpGet:
              path: /health
              port: 8080
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
          envFrom:
            - configMapRef:
                name: api-config
            - secretRef:
                name: api-secrets
          volumeMounts:
            - name: data
              mountPath: /app/data
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: api-data
```

**Unique fields the wizard must expose:**
| Field | Options | Default |
|-------|---------|---------|
| `strategy.type` | `RollingUpdate`, `Recreate` | `RollingUpdate` |
| `strategy.rollingUpdate.maxSurge` | integer or % | `1` |
| `strategy.rollingUpdate.maxUnavailable` | integer or % | `1` |
| `replicas` | integer ≥ 1 | `2` (production), `1` (dev) |

**Compose → Deployment signals:**
- Has a `build` context → application code → Deployment
- `restart: always` or `restart: unless-stopped` → long-running → Deployment
- Exposes ports → serves traffic → Deployment
- Is NOT a well-known infra image → Deployment

---

### 2B. StatefulSet

**What it is:** Like Deployment, but pods have **stable identity**. Pod names are ordinal: `postgres-0`, `postgres-1`, `postgres-2`. Each pod gets its own persistent storage via `volumeClaimTemplates`. Pods are created/deleted **in order**.

**Key characteristics:**
- Stable pod names: `{name}-0`, `{name}-1`, …
- Stable network identity via **headless Service** (`clusterIP: None`)
- Each pod gets DNS: `postgres-0.postgres-headless.default.svc.cluster.local`
- **volumeClaimTemplates**: each pod gets its OWN PVC, named `{volName}-{setName}-{ordinal}`
  - E.g., `data-postgres-0`, `data-postgres-1`
  - PVCs are NOT deleted when pods are deleted (data survives scaling down)
- Ordered startup: pod-1 waits for pod-0 to be Ready
- Ordered shutdown: pod-N deleted first, then pod-(N-1), etc.

**Manifest shape:**
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: default
spec:
  serviceName: postgres-headless    # REQUIRED — references headless Service
  replicas: 1
  podManagementPolicy: OrderedReady  # or Parallel
  updateStrategy:
    type: RollingUpdate              # or OnDelete
    rollingUpdate:
      partition: 0                   # for canary updates
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
        - name: postgres
          image: postgres:16-alpine
          ports:
            - containerPort: 5432
          env:
            - name: POSTGRES_DB
              value: myapp
            - name: PGDATA
              value: /var/lib/postgresql/data/pgdata
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:              # ← THE KEY DIFFERENCE
    - metadata:
        name: data
      spec:
        accessModes: [ReadWriteOnce]
        storageClassName: longhorn
        resources:
          requests:
            storage: 10Gi
---
# REQUIRED companion: Headless Service
apiVersion: v1
kind: Service
metadata:
  name: postgres-headless
spec:
  clusterIP: None                   # ← Headless = no load balancing
  selector:
    app: postgres
  ports:
    - port: 5432
      targetPort: 5432
```

**Unique fields the wizard must expose:**
| Field | Options | Default |
|-------|---------|---------|
| `serviceName` | string (auto-generated) | `{name}-headless` |
| `podManagementPolicy` | `OrderedReady`, `Parallel` | `OrderedReady` |
| `updateStrategy.type` | `RollingUpdate`, `OnDelete` | `RollingUpdate` |
| `updateStrategy.rollingUpdate.partition` | integer | `0` |
| `volumeClaimTemplates[].spec` | storageClassName, size, accessMode | per-volume |
| Headless Service | auto-generate checkbox | checked (always) |

**Compose → StatefulSet signals:**
- Uses well-known stateful image (postgres, mysql, mongo, redis, kafka, etc.)
- Has named volumes for data persistence
- Typically single replica in compose

**Critical difference from Deployment:**
- Deployment volumes: service has separate PVC resources, all pods share them (or you create N separate PVCs manually)
- StatefulSet volumes: `volumeClaimTemplates` auto-creates one PVC per pod — **the PVC lives inside the StatefulSet spec**, not as a separate resource

---

### 2C. DaemonSet

**What it is:** Ensures exactly one pod runs on every node (or a filtered subset). No `replicas` field — the count is driven by node count. When a new node joins, a pod is auto-created. When a node is removed, the pod is garbage collected.

**Key characteristics:**
- No `replicas` field — pod count = node count (or filtered node count)
- Node scheduling via `nodeSelector` or `affinity`
- `tolerations` to run on tainted nodes (e.g., control-plane nodes)
- Commonly uses `hostPath` volumes for node-level access
- Commonly uses `hostNetwork: true` for network monitoring

**Manifest shape:**
```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: fluentd
  namespace: kube-system
spec:
  selector:
    matchLabels:
      app: fluentd
  updateStrategy:
    type: RollingUpdate            # or OnDelete
    rollingUpdate:
      maxUnavailable: 1
  template:
    metadata:
      labels:
        app: fluentd
    spec:
      tolerations:
        - key: node-role.kubernetes.io/control-plane
          effect: NoSchedule
      containers:
        - name: fluentd
          image: fluent/fluentd:v1.16
          resources:
            limits:
              memory: 200Mi
            requests:
              cpu: 100m
              memory: 200Mi
          volumeMounts:
            - name: varlog
              mountPath: /var/log
            - name: varlibdockercontainers
              mountPath: /var/lib/docker/containers
              readOnly: true
      volumes:
        - name: varlog
          hostPath:
            path: /var/log
        - name: varlibdockercontainers
          hostPath:
            path: /var/lib/docker/containers
```

**Unique fields the wizard must expose:**
| Field | Options | Default |
|-------|---------|---------|
| `updateStrategy.type` | `RollingUpdate`, `OnDelete` | `RollingUpdate` |
| `updateStrategy.rollingUpdate.maxUnavailable` | integer or % | `1` |
| `nodeSelector` | key=value labels | empty (all nodes) |
| `tolerations[]` | key, operator, value, effect | common presets |

**No `replicas` field. No `strategy.maxSurge` either (pods can't "surge" — one per node max).**

**Compose → DaemonSet signals:**
- `deploy.mode: global` in compose → DaemonSet
- Log/monitoring agents (fluentd, filebeat, prometheus-node-exporter)
- Network plugins
- Extremely rare from compose — most compose files don't describe DaemonSets

---

### 2D. Job

**What it is:** Run-to-completion workload. Creates pod(s), waits for them to succeed, then stops. Once all `completions` succeed, the Job is done. Dead pods are NOT replaced continuously — they're retried up to `backoffLimit`.

**Key characteristics:**
- `restartPolicy`: must be `Never` or `OnFailure` (NOT `Always`)
- `backoffLimit`: max retries before marking Job as Failed (default: 6)
- `completions`: how many successful pod completions needed (default: 1)
- `parallelism`: how many pods run concurrently (default: 1)
- `activeDeadlineSeconds`: timeout for the entire Job
- `ttlSecondsAfterFinished`: auto-cleanup finished Job after N seconds

**Manifest shape:**
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: db-migrate
  namespace: default
spec:
  backoffLimit: 3
  activeDeadlineSeconds: 600       # 10 min timeout
  ttlSecondsAfterFinished: 3600    # cleanup after 1 hour
  template:
    spec:
      restartPolicy: Never          # REQUIRED: Never or OnFailure
      containers:
        - name: migrate
          image: ghcr.io/user/api:latest
          command: ["python", "manage.py", "migrate"]
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: api-secrets
                  key: DATABASE_URL
```

**Unique fields the wizard must expose:**
| Field | Options | Default |
|-------|---------|---------|
| `backoffLimit` | integer | `3` |
| `completions` | integer | `1` |
| `parallelism` | integer | `1` |
| `activeDeadlineSeconds` | integer (seconds) | `600` (10 min) |
| `ttlSecondsAfterFinished` | integer (seconds) | `3600` (1 hour) |
| `restartPolicy` | `Never`, `OnFailure` | `Never` |
| `command` | string[] override | from image |

**No `replicas`, no `strategy`, no probes, no Service.**

**Compose → Job signals:**
- Compose service with `restart: "no"` or `restart: on-failure`
- Service name contains `migrate`, `seed`, `init`, `setup`, `import`
- No `ports` exposed (not serving traffic)
- Has `command` or `entrypoint` that looks like a one-shot task
- `depends_on` other services (runs after they're ready)

---

### 2E. CronJob

**What it is:** A Job that runs on a schedule. Creates a new Job object at each scheduled time. The Job then creates pods. Finished pods are cleaned up based on history limits.

**Key characteristics:**
- `schedule`: cron expression (e.g., `"0 2 * * *"` = 2 AM daily)
- `concurrencyPolicy`: what happens if previous run hasn't finished
  - `Allow` (default): multiple Jobs can run simultaneously
  - `Forbid`: skip this run if previous is still active
  - `Replace`: kill previous Job, start new one
- `successfulJobsHistoryLimit`: keep N successful Job objects (default: 3)
- `failedJobsHistoryLimit`: keep N failed Job objects (default: 1)
- `startingDeadlineSeconds`: miss window → skip this run
- `suspend`: true = pause scheduling (useful for maintenance)

**Manifest shape:**
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: nightly-backup
  namespace: default
spec:
  schedule: "0 2 * * *"            # 2 AM daily
  concurrencyPolicy: Forbid         # don't overlap
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 1
  startingDeadlineSeconds: 300      # 5 min window
  jobTemplate:
    spec:
      backoffLimit: 2
      activeDeadlineSeconds: 1800   # 30 min timeout
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: backup
              image: ghcr.io/user/backup:latest
              command: ["sh", "-c", "pg_dump ... | gzip > /backup/db.sql.gz"]
              volumeMounts:
                - name: backup-vol
                  mountPath: /backup
          volumes:
            - name: backup-vol
              persistentVolumeClaim:
                claimName: backup-storage
```

**Unique fields the wizard must expose:**
| Field | Options | Default |
|-------|---------|---------|
| `schedule` | cron expression | required (no default) |
| `concurrencyPolicy` | `Allow`, `Forbid`, `Replace` | `Forbid` |
| `successfulJobsHistoryLimit` | integer | `3` |
| `failedJobsHistoryLimit` | integer | `1` |
| `startingDeadlineSeconds` | integer (seconds) | `300` |
| `suspend` | boolean | `false` |
| Inner jobTemplate: same fields as Job | | |

**Compose → CronJob signals:**
- Compose `labels` like `com.example.schedule: "0 2 * * *"`
- Service name contains `cron`, `scheduled`, `periodic`, `nightly`, `hourly`
- Rarely present in compose — most cron tasks aren't in docker-compose.yml
- Could be suggested: "This migration job — want to run it on a schedule?"

---

## 3. THE MANIFEST SHAPE DIFFERENCES — WHAT THE WIZARD GENERATES

### Resource Generation Per Workload Kind

| Kind | Generates | Does NOT generate |
|------|-----------|-------------------|
| **Deployment** | Deployment + Service + PVC(s) (separate) + ConfigMap + Secret | volumeClaimTemplates |
| **StatefulSet** | StatefulSet (with volumeClaimTemplates) + headless Service + (optional) regular Service + ConfigMap + Secret | Separate PVC resources (templates handle it) |
| **DaemonSet** | DaemonSet + (optional) Service | PVCs typically (uses hostPath), no replicas |
| **Job** | Job | Service, PVCs (usually), probes |
| **CronJob** | CronJob | Service, PVCs (usually), probes |

### Pod Spec Differences

| Pod Spec Feature | Deployment | StatefulSet | DaemonSet | Job | CronJob |
|------------------|:----------:|:-----------:|:---------:|:---:|:-------:|
| `containers[]` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `resources` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `env` / `envFrom` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `readinessProbe` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `livenessProbe` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `volumeMounts` | ✅ | ✅ | ✅ | ⚠️ rare | ⚠️ rare |
| `command` override | ⚠️ rare | ⚠️ rare | ⚠️ rare | ✅ common | ✅ common |
| `restartPolicy` | `Always` (implicit) | `Always` (implicit) | `Always` (implicit) | `Never`/`OnFailure` | `Never`/`OnFailure` |
| `nodeSelector` | ⚠️ optional | ⚠️ optional | ✅ common | ❌ | ❌ |
| `tolerations` | ⚠️ optional | ⚠️ optional | ✅ common | ❌ | ❌ |
| `hostNetwork` | ❌ | ❌ | ⚠️ optional | ❌ | ❌ |

---

## 4. COMPOSE → WORKLOAD KIND CLASSIFICATION

### Decision Tree

```
Is it a well-known infra image?
├── YES → Is it a database/cache/MQ?
│   ├── YES → StatefulSet (or Managed/Skip)
│   └── NO → Is it a log/monitoring agent?
│       ├── YES → DaemonSet
│       └── NO → Deployment
├── NO → Does it expose ports?
│   ├── YES → Does it have named volumes?
│   │   ├── YES → Deployment (with PVCs)
│   │   └── NO → Deployment (stateless)
│   └── NO → Does it look like a one-shot task?
│       ├── YES → Job
│       │   └── Want it scheduled? → CronJob
│       └── NO → Deployment (background worker)
```

### Classification Heuristics

```javascript
const _INFRA_STATEFULSET = new Set([
    'postgres', 'postgresql', 'mysql', 'mariadb', 'mongo', 'mongodb',
    'redis', 'memcached', 'rabbitmq', 'kafka', 'zookeeper',
    'elasticsearch', 'opensearch', 'cassandra', 'couchdb',
    'cockroachdb', 'etcd', 'consul', 'vault',
    'minio', 'clickhouse', 'influxdb', 'timescaledb',
    'nats', 'pulsar',
]);

const _INFRA_DAEMONSET = new Set([
    'fluentd', 'fluent-bit', 'filebeat', 'logstash',
    'prometheus-node-exporter', 'node-exporter',
    'datadog-agent', 'newrelic-infrastructure',
    'calico-node', 'cilium-agent', 'weave-net',
    'kube-proxy',
]);

const _JOB_NAME_PATTERNS = [
    'migrate', 'migration', 'seed', 'seeder', 'init',
    'setup', 'import', 'export', 'backup', 'restore',
    'cleanup', 'test', 'e2e', 'integration-test',
];

function _classifyWorkloadKind(svc) {
    const imageName = (svc.image || '').split(':')[0].split('/').pop().toLowerCase();
    const svcName = svc.name.toLowerCase();

    // Check infra images for StatefulSet
    for (const prefix of _INFRA_STATEFULSET) {
        if (imageName.startsWith(prefix)) return 'StatefulSet';
    }

    // Check for DaemonSet patterns
    for (const prefix of _INFRA_DAEMONSET) {
        if (imageName.startsWith(prefix)) return 'DaemonSet';
    }

    // Check compose deploy.mode: global → DaemonSet
    if (svc.deploy?.mode === 'global') return 'DaemonSet';

    // Check for Job patterns
    const hasNoPorts = !svc.ports || svc.ports.length === 0;
    const isOneShot = svc.restart === 'no' || svc.restart === 'on-failure';
    const nameIsJobLike = _JOB_NAME_PATTERNS.some(p => svcName.includes(p));

    if (hasNoPorts && (isOneShot || nameIsJobLike)) return 'Job';

    // Default: Deployment
    return 'Deployment';
}
```

---

## 5. UI IMPLICATIONS — WHAT EACH KIND NEEDS

### Shared Fields (All Kinds)

Every workload kind needs:
- Image
- Container port (except Job/CronJob)
- Resources (CPU/Memory)
- Environment variables
- Command override (especially Job/CronJob)

### Kind-Specific UI Panels

#### When kind = Deployment:
```
[Image ────────] [Port] [Replicas] [Service Type ▾] [Strategy ▾]
▸ Resources ···
▸ Health Checks ···        ← readinessProbe + livenessProbe
▸ Environment Variables ···
▸ Volume Mounts ···        ← PVCs (separate resources)
```

#### When kind = StatefulSet:
```
[Image ────────] [Port] [Replicas]
▸ Resources ···
▸ Health Checks ···        ← readinessProbe + livenessProbe
▸ Environment Variables ···
▸ Persistent Storage ···   ← volumeClaimTemplates (PER-POD PVCs, not separate)
  ├── Volume name [data    ]
  ├── Size        [10Gi   ]
  ├── Access Mode [ReadWriteOnce ▾]
  └── StorageClass [longhorn ▾]
☑ Create headless Service (for DNS discovery)
  Pod management: [OrderedReady ▾]
```

**KEY DIFFERENCE:** StatefulSet uses `volumeClaimTemplates` — the PVC spec
is INLINE in the StatefulSet, not a separate resource. The wizard must generate
the storage config differently than for Deployments.

#### When kind = DaemonSet:
```
[Image ────────] [Port (optional)]
▸ Resources ···             ← important: limit memory to not starve nodes
▸ Environment Variables ···
▸ Node Selection ···
  ├── Node selector: [label=value]
  └── Tolerations:
      ☑ Run on control-plane nodes
      ☑ Run on tainted nodes
▸ Host Access ···
  ☑ Host network
  ☑ Host PID
  ☑ Host IPC
Update strategy: [RollingUpdate ▾]  maxUnavailable: [1]
```

**NO `replicas`. NO `strategy.maxSurge`. NO Service Type select (usually).**

#### When kind = Job:
```
[Image ────────]
Command: [python manage.py migrate    ]  ← critical field
▸ Resources ···
▸ Environment Variables ···
Backoff limit:    [3  ]  ← retries on failure
Completions:      [1  ]  ← how many successful pods needed
Parallelism:      [1  ]  ← concurrent pods
Timeout:          [600]s ← activeDeadlineSeconds
Auto-cleanup:     [3600]s ← ttlSecondsAfterFinished
Restart policy:   [Never ▾]  ← Never or OnFailure
```

**NO probes. NO replicas. NO Service. NO volumes (usually).**

#### When kind = CronJob:
```
[Image ────────]
Command:    [sh -c "pg_dump ... > /backup/db.sql.gz"]
Schedule:   [0 2 * * *]   ← cron expression (REQUIRED)
            "Every day at 2:00 AM"  ← human-readable hint
Concurrency: [Forbid ▾]   ← what if previous run is still going
▸ Resources ···
▸ Environment Variables ···
History: keep [3] successful, [1] failed
Deadline: [300]s ← skip if missed by this much
Suspend:  ☐      ← pause scheduling
── Inner Job settings: ──
  Backoff limit: [2]
  Timeout:       [1800]s
  Restart:       [OnFailure ▾]
```

**Same as Job but wrapped in schedule. NO probes. NO Service.**

---

## 6. PER-KIND SERVICE RESOURCE GENERATION

The K8s `Service` resource also varies by workload kind:

| Workload Kind | Needs Service? | Service Type | Special |
|---------------|:--------------:|:------------:|---------|
| Deployment | ✅ always | ClusterIP / LoadBalancer / NodePort | Standard |
| StatefulSet | ✅ headless + optional regular | `clusterIP: None` (headless) | Must exist for stable DNS |
| DaemonSet | ⚠️ optional | ClusterIP or headless | Only if pods serve traffic |
| Job | ❌ never | — | — |
| CronJob | ❌ never | — | — |

---

## 7. COMPOSE → WORKLOAD: REALISTIC MAPPING EXAMPLES

### Example 1: Typical web app compose
```yaml
services:
  api:                          # → Deployment
    build: ./src
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgres://...
    restart: always

  postgres:                     # → StatefulSet (or Managed)
    image: postgres:16-alpine
    volumes: ["pg-data:/var/lib/postgresql/data"]
    environment:
      POSTGRES_DB: app

  redis:                        # → StatefulSet (or Managed)
    image: redis:7-alpine
    restart: always

  migrate:                      # → Job
    build: ./src
    command: python manage.py migrate
    restart: "no"
    depends_on: [postgres]

  worker:                       # → Deployment (consumer/processor)
    build: ./src
    command: celery worker
    restart: always
    # No ports!
```

### Example 2: Monitoring stack
```yaml
services:
  prometheus:                   # → StatefulSet (long-term data)
    image: prom/prometheus
    volumes: ["prom-data:/prometheus"]

  grafana:                      # → Deployment (stateless UI, data in external DB)
    image: grafana/grafana
    ports: ["3000:3000"]

  node-exporter:                # → DaemonSet (one per node)
    image: prom/node-exporter
    deploy:
      mode: global              # ← explicit DaemonSet signal
```

---

## 8. WHAT THIS MEANS FOR THE WIZARD UI

### Current (wrong) model:
```
App services:   → always Deployment (hardcoded)
Infra services: → StatefulSet / Managed / Skip (3-way radio)
```

### Correct model:
```
ALL services:   → Workload Kind selector:
                   [Deployment ▾]  ← shows Deployment-specific fields
                   [StatefulSet ▾] ← shows StatefulSet-specific fields
                   [DaemonSet ▾]   ← shows DaemonSet-specific fields
                   [Job ▾]         ← shows Job-specific fields
                   [CronJob ▾]     ← shows CronJob-specific fields
                   [Managed ▾]     ← external service (no K8s resource)
                   [Skip ▾]        ← exclude entirely

                   Pre-selected based on classification heuristic.
                   User can always override.
```

### Smart Defaults:
- `api` with build context → **Deployment** (pre-selected)
- `postgres:16-alpine` with volumes → **StatefulSet** (pre-selected, plus "Managed" as visible alternative)
- `node-exporter` with `deploy.mode: global` → **DaemonSet**
- `migrate` with `restart: "no"` → **Job**
- Regular worker queue consumer → **Deployment** (even without ports)

### What Changes When User Switches Kind:

Switching workload kind in the dropdown should **re-render the entire detail panel** for that service, because the fields are fundamentally different:
- Deployment → StatefulSet: volumes panel changes to volumeClaimTemplates, headless service checkbox appears
- Deployment → Job: probes disappear, replicas disappears, command appears, backoffLimit appears
- StatefulSet → Deployment: volumeClaimTemplates → separate PVCs, headless checkbox disappears
- Any → Managed: everything disappears, Terraform CTA appears
- Any → Skip: everything disappears

---

## 9. IMPLEMENTATION CONSIDERATIONS

### The Kind Selector

The workload kind selector replaces the old 3-way radio for infra, and adds kind selection for app services too. Options shown should be context-aware:

**For app services (build context / non-infra image):**
- Deployment ← default
- StatefulSet
- DaemonSet ← only if matches signal
- Job ← only if matches signal
- CronJob
- Skip

**For infra services (well-known image):**
- StatefulSet ← default for databases
- Deployment ← if they prefer
- Managed (external) ← prominent alternative
- Skip

### volumeClaimTemplates vs Separate PVCs

This is the most critical difference to get right:

**Deployment volumes** (what we built in 1E):
```yaml
# Separate PVC resource
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: api-data
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 10Gi

# Referenced in Deployment
volumes:
  - name: data
    persistentVolumeClaim:
      claimName: api-data
```

**StatefulSet volumes** (different!):
```yaml
# INLINE in StatefulSet spec — no separate PVC resource
volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: [ReadWriteOnce]
      storageClassName: longhorn
      resources:
        requests:
          storage: 10Gi

# Referenced in container — same
volumeMounts:
  - name: data
    mountPath: /var/lib/postgresql/data
```

The wizard's `collect()` and the backend's manifest generation must handle both patterns.

---

## 10. IMPLEMENTATION ORDER

1. **Add kind selector** to all service cards (app + infra) — replaces the old 3-way infra radio AND adds kind to app services
2. **Render kind-specific detail panels** — different fields per kind
3. **Update `collect()`** — capture kind + kind-specific fields
4. **Update review step** — show kind-appropriate summary
5. **Update backend generation** — generate correct manifest per kind (Deployment already works, need StatefulSet, DaemonSet, Job, CronJob)

### What exists today and what needs to change:

| Component | Current State | Needed |
|-----------|--------------|--------|
| App service kind | Hardcoded `Deployment` | Kind selector dropdown |
| Infra service kind | 3-way radio (StatefulSet/Managed/Skip) | Same dropdown as app (Deployment/StatefulSet/DaemonSet/Job/CronJob/Managed/Skip) |
| Detail panels | Same for all app services | Kind-conditional rendering |
| Volume handling | Deployment-style (separate PVCs) for all | StatefulSet gets volumeClaimTemplates |
| Probes | Always shown | Hidden for Job/CronJob |
| Replicas | Always shown | Hidden for DaemonSet/Job/CronJob |
| Service Type | Always shown | Hidden for Job/CronJob/DaemonSet |
| Strategy | Always shown | Different per kind (RollingUpdate/Recreate vs OnDelete vs N/A) |
| Command override | Not shown | Shown for Job/CronJob |
| Schedule | Not shown | Shown for CronJob |
| Node selector | Not shown | Shown for DaemonSet |
| Backend generation | Only Deployment | All 5 kinds |

---

## 11. DEPENDENCIES & CROSS-CONCERNS

- The existing 1A–1E features (strategy, resources, probes, env vars, volumes) are all Deployment-centric. They need to be made conditional on the selected kind.
- The infra "Managed" option should show connection env var hints (cross-references app services' env vars — depends on 1D).
- Backend `generate_k8s_wizard` needs new kind handlers (StatefulSet, DaemonSet, Job, CronJob).
- The review step needs kind-aware summary rendering.

---

## 12. MULTI-CONTAINER PODS — THE POD IS THE UNIT, NOT THE CONTAINER

### The K8s Pod Model

A K8s **Pod** is NOT a single container. A Pod is a group of one or more containers that:
- Share the same network namespace (same IP, can reach each other on `localhost`)
- Share the same IPC namespace
- Can share volumes (mount the same `emptyDir` or PVC)
- Are co-scheduled on the same node
- Have a shared lifecycle (all containers start/stop together)

The pod spec has **three container arrays**:

```yaml
spec:
  initContainers:     # Run sequentially, each to completion, BEFORE app starts
    - name: wait-for-db
      image: busybox
      command: ['sh', '-c', 'until nc -z postgres 5432; do sleep 1; done']

  containers:         # The main application containers — run concurrently
    - name: api               # Primary container
      image: ghcr.io/user/api:latest
      ports: [{ containerPort: 8080 }]
    - name: log-shipper        # Second container (sidecar pattern)
      image: fluent/fluent-bit:latest
      volumeMounts:
        - name: shared-logs
          mountPath: /var/log/app

  # K8s 1.28+ native sidecars (defined as init containers with restartPolicy: Always)
  # These start before main containers but run for the pod's entire lifetime
  initContainers:
    - name: istio-proxy         # Native sidecar example
      image: istio/proxyv2
      restartPolicy: Always     # ← This makes it a sidecar, not a regular init
```

### Three Container "Slots" in the Pod Spec

| Slot | Array | Lifecycle | When Used |
|------|-------|-----------|-----------|
| **Init containers** | `initContainers[]` | Run sequentially, each to completion, then stop. **Block** main containers until all finish. | DB wait, schema setup, config sync, permission fix |
| **Native sidecars** (K8s 1.28+) | `initContainers[]` with `restartPolicy: Always` | Start before main containers, run continuously alongside them, stop after main containers exit. | Service mesh proxy, log forwarder, config reloader |
| **App containers** | `containers[]` | Run concurrently. Pod is "running" when all are running. Pod is "completed" when all exit (for Jobs). | Primary app + tightly-coupled helpers |

### Key: What DEFINES Each Slot

The difference is **who defines it** and **how it runs**:

| | Defined in manifest? | Runs to completion? | Runs for pod lifetime? | Injected externally? |
|---|:---:|:---:|:---:|:---:|
| **Init container** | ✅ Yes, explicitly | ✅ Yes, then stops | ❌ No | ❌ No |
| **Native sidecar** | ✅ Yes, explicitly (or injected) | ❌ No | ✅ Yes | Can be either |
| **App container** | ✅ Yes, explicitly | Depends on workload kind | ✅ Yes (for Deployment/StatefulSet) | ❌ No |
| **Injected sidecar** (Istio) | ❌ No — added by admission webhook | ❌ No | ✅ Yes | ✅ Yes |

---

## 13. INIT CONTAINERS — PRE-FLIGHT TASKS

### What They Do

Init containers run **before** any app container starts. Use cases:
- Wait for a dependency (DB, cache, config server) to be available
- Clone a git repo or download assets
- Run database migrations before the app starts
- Set file permissions on shared volumes
- Generate config files from templates

### Manifest Shape

```yaml
spec:
  initContainers:
    - name: wait-for-postgres
      image: busybox:1.36
      command:
        - sh
        - -c
        - |
          until nc -z postgres-headless 5432; do
            echo "Waiting for postgres..."
            sleep 2
          done
          echo "Postgres is ready"
      resources:
        requests:
          cpu: 10m
          memory: 16Mi
        limits:
          cpu: 50m
          memory: 32Mi

    - name: run-migrations
      image: ghcr.io/user/api:latest
      command: ["python", "manage.py", "migrate", "--noinput"]
      env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: api-secrets
              key: DATABASE_URL
```

### Fields the Wizard Should Expose Per Init Container

| Field | Options | Default |
|-------|---------|---------|
| `name` | string | required |
| `image` | string | `busybox:1.36` for wait patterns |
| `command` | string[] | required |
| `resources` | CPU/memory req/lim | minimal defaults |
| `env` | same as app container | optional |
| `volumeMounts` | shared volumes | optional |

### Common Init Patterns (Wizard Presets)

The wizard can offer quick-add presets:

| Preset | Image | Command | Purpose |
|--------|-------|---------|---------|
| **Wait for TCP** | `busybox:1.36` | `until nc -z {host} {port}; do sleep 2; done` | Wait for DB/cache |
| **Wait for HTTP** | `curlimages/curl:latest` | `until curl -sf http://{host}:{port}/health; do sleep 2; done` | Wait for API |
| **Run migrations** | same as app | `python manage.py migrate` / `npx prisma migrate deploy` / `flyway migrate` | Schema migration |
| **Fix permissions** | `busybox:1.36` | `chown -R 1000:1000 /data` | Volume permission fix |
| **Custom** | user-specified | user-specified | Anything else |

---

## 14. SIDECARS — CONTAINERS THAT LIVE ALONGSIDE THE APP

### Traditional Sidecars (pre-K8s 1.28)

Before native sidecar support, sidecars were just additional entries in `containers[]`:

```yaml
spec:
  containers:
    - name: api                    # Primary application
      image: ghcr.io/user/api:latest
      ports: [{ containerPort: 8080 }]
      volumeMounts:
        - name: shared-logs
          mountPath: /var/log/app

    - name: log-forwarder          # Sidecar: ships logs
      image: fluent/fluent-bit:2.2
      volumeMounts:
        - name: shared-logs
          mountPath: /var/log/app
          readOnly: true
      resources:
        requests:
          cpu: 50m
          memory: 64Mi
        limits:
          cpu: 100m
          memory: 128Mi

  volumes:
    - name: shared-logs
      emptyDir: {}                 # Shared between containers
```

**Problem with traditional sidecars:**
- No startup ordering guarantee (sidecar might start after app)
- Sidecar crash doesn't get special handling
- For Jobs: sidecar never exits → Job never completes (the classic Istio+Job problem)

### Native Sidecars (K8s 1.28+ / stable 1.29+)

K8s solved this with `restartPolicy: Always` on init containers:

```yaml
spec:
  initContainers:
    - name: log-forwarder
      image: fluent/fluent-bit:2.2
      restartPolicy: Always         # ← This is the magic
      volumeMounts:
        - name: shared-logs
          mountPath: /var/log/app
          readOnly: true
      resources:
        requests:
          cpu: 50m
          memory: 64Mi

  containers:
    - name: api
      image: ghcr.io/user/api:latest
      volumeMounts:
        - name: shared-logs
          mountPath: /var/log/app
```

**Benefits:**
- Guaranteed to start BEFORE main containers
- Automatically restarted if it crashes (like a regular container)
- Gracefully terminated AFTER main containers exit (solves the Job problem)
- Supports probes (readiness, liveness, startup)

### Common Sidecar Use Cases

| Sidecar | Image | Purpose | Shares |
|---------|-------|---------|--------|
| **Log forwarder** | `fluent/fluent-bit`, `elastic/filebeat` | Ship app logs to centralized logging | `emptyDir` volume |
| **Config reloader** | `jimmidyson/configmap-reload` | Watch ConfigMap changes, signal app to reload | Process signal (localhost) |
| **Proxy** | `envoyproxy/envoy`, `haproxy` | Reverse proxy, TLS termination | Network (localhost) |
| **Metrics exporter** | `prom/statsd-exporter` | Convert app metrics to Prometheus format | Network (localhost) |
| **Auth proxy** | `oauth2-proxy/oauth2-proxy` | Handle OAuth2/OIDC authentication | Network (localhost) |
| **Cloud SQL Proxy** | `gcr.io/cloud-sql-connectors/cloud-sql-proxy` | Secure tunnel to Cloud SQL | Network (localhost) |
| **Vault agent** | `hashicorp/vault` | Inject secrets from Vault | `emptyDir` volume |

### Fields the Wizard Should Expose Per Sidecar

| Field | Options | Default |
|-------|---------|---------|
| `name` | string | required |
| `image` | string | from preset or custom |
| `command` / `args` | string[] | from preset |
| `resources` | CPU/memory | small defaults (50m/64Mi) |
| `env` | key-value pairs | optional |
| `volumeMounts` | shared volumes | depends on sidecar type |
| `ports` | container ports | optional (metrics, health) |
| Native sidecar? | checkbox | ✅ if K8s ≥ 1.28 |

---

## 15. ISTIO SERVICE MESH — INJECTION, NOT DEFINITION

### What Makes Istio Different

Istio is NOT defined in your manifest. It is **injected by the cluster** at pod creation time
via a Kubernetes **mutating admission webhook**. When a pod is created in an Istio-enabled
namespace, the webhook automatically adds:

1. **`istio-init`** — an init container that sets up iptables rules
2. **`istio-proxy`** — the Envoy sidecar that intercepts all traffic

You never write these containers in your YAML. You just:
1. Label the namespace: `istio-injection: enabled`
2. Optionally annotate individual pods

### How to Enable/Disable Istio

**Namespace-level (recommended):**
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: my-app
  labels:
    istio-injection: enabled       # ← All pods in this namespace get Istio
```

**Per-workload override (opt-out from namespace):**
```yaml
spec:
  template:
    metadata:
      annotations:
        sidecar.istio.io/inject: "false"   # ← This specific workload skips Istio
```

**Per-workload override (opt-in without namespace label):**
```yaml
spec:
  template:
    metadata:
      labels:
        sidecar.istio.io/inject: "true"    # ← Force Istio for this workload
```

### Istio Resource Annotations

When Istio IS enabled, you can control the proxy's resource allocation:

```yaml
spec:
  template:
    metadata:
      annotations:
        # Proxy resource requests
        sidecar.istio.io/proxyCPU: "100m"
        sidecar.istio.io/proxyMemory: "128Mi"
        # Proxy resource limits
        sidecar.istio.io/proxyCPULimit: "500m"
        sidecar.istio.io/proxyMemoryLimit: "256Mi"
        # Log level
        sidecar.istio.io/logLevel: "warning"
        # Exclude ports from interception
        traffic.sidecar.istio.io/excludeInboundPorts: "8081"
        traffic.sidecar.istio.io/excludeOutboundPorts: "3306"
```

### What the Wizard Needs for Istio

The wizard should offer a **simple panel** (not complex — Istio is either on or off per workload):

```
▸ Service Mesh (Istio)
  ☐ Enable Istio sidecar injection
  │
  │ When checked:
  │   Proxy CPU:    request [100m]  limit [500m]
  │   Proxy Memory: request [128Mi] limit [256Mi]
  │   ▸ Advanced
  │     Exclude inbound ports:  [          ]  (comma-separated)
  │     Exclude outbound ports: [          ]  (comma-separated)
  │     Log level: [warning ▾]
```

This translates to annotations on the pod template, NOT extra containers in the manifest.

### Istio + Job/CronJob Concern

Historically, Istio sidecars broke Jobs because the Envoy proxy never terminates,
preventing the Job from completing. K8s native sidecars (1.28+) fix this — the sidecar
terminates after the main container exits. The wizard should:
- If kind = Job/CronJob AND Istio enabled → show info note: "Requires K8s ≥ 1.28 for native sidecar support"
- Or suggest the `holdApplicationUntilProxyStarts` annotation

---

## 16. MULTI-CONTAINER & CONTAINER GROUPING — WIZARD UI CONCEPT

### The Core User Decision: "Bundle or Separate?"

In Docker Compose, each service = one container. But in K8s, each workload = one **pod**
which can have multiple containers. The user needs to decide:

1. Should compose services `api` and `worker` be **separate Deployments** (separate pods)? → Yes, usually
2. Should `api` and `nginx` be in the **same pod** (nginx as a sidecar/proxy)? → Maybe
3. Should `api` have init containers for migrations? → Yes, often

### What the Wizard Exposes

Each workload card (the thing with the Kind selector) represents one **pod definition**.
It should allow adding containers within that pod:

```
┌─ api ─────────── Kind: [Deployment ▾] ──────────────────────────────┐
│                                                                      │
│  📦 Main Container                                                   │
│     Image:   [ghcr.io/user/api:latest]                               │
│     Port:    [8080]                                                  │
│     ...existing fields...                                            │
│                                                                      │
│  ▸ Init Containers (0)                                               │
│    [+ Add init container]                                            │
│    Presets: [Wait for TCP ▾] [Run migrations ▾] [Custom]             │
│                                                                      │
│  ▸ Sidecar Containers (0)                                            │
│    [+ Add sidecar]                                                   │
│    Presets: [Log forwarder ▾] [Config reloader ▾] [Custom]           │
│                                                                      │
│  ▸ Service Mesh (Istio)                                              │
│    ☐ Enable Istio sidecar injection                                  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Key Distinction Summary

| Container concept | Where defined | In manifest? | Lifecycle |
|-------------------|---------------|:---:|-----------|
| **Main container** | `spec.containers[0]` | ✅ Explicit | Runs for pod lifetime |
| **Extra container** (manual sidecar) | `spec.containers[1+]` | ✅ Explicit | Runs for pod lifetime |
| **Init container** | `spec.initContainers[]` | ✅ Explicit | Runs to completion, then stops |
| **Native sidecar** | `spec.initContainers[]` with `restartPolicy: Always` | ✅ Explicit | Starts before main, runs for lifetime, stops after main |
| **Istio proxy** | Injected by webhook | ❌ NOT in manifest | Injected at creation, runs for lifetime |

### What Gets Generated

When the user adds containers:

**Init container added → appears in manifest:**
```yaml
spec:
  initContainers:
    - name: wait-for-db
      image: busybox:1.36
      command: ['sh', '-c', 'until nc -z postgres 5432; do sleep 1; done']
```

**Sidecar added (native mode) → appears in manifest:**
```yaml
spec:
  initContainers:
    - name: log-forwarder
      image: fluent/fluent-bit:2.2
      restartPolicy: Always
      volumeMounts: [...]
```

**Sidecar added (traditional mode) → appears in manifest:**
```yaml
spec:
  containers:
    - name: api
      ...
    - name: log-forwarder
      image: fluent/fluent-bit:2.2
      volumeMounts: [...]
```

**Istio enabled → only annotations, no containers in manifest:**
```yaml
spec:
  template:
    metadata:
      annotations:
        sidecar.istio.io/inject: "true"
        sidecar.istio.io/proxyCPU: "100m"
        sidecar.istio.io/proxyMemory: "128Mi"
```

### Shared Volumes Between Containers

When a pod has multiple containers, they often need to share data.
The wizard should auto-suggest an `emptyDir` volume when adding a sidecar
that typically shares data (e.g., log forwarder):

```yaml
volumes:
  - name: shared-logs
    emptyDir: {}

# Main container writes:
containers:
  - name: api
    volumeMounts:
      - name: shared-logs
        mountPath: /var/log/app

# Sidecar reads:
  - name: log-forwarder
    volumeMounts:
      - name: shared-logs
        mountPath: /var/log/app
        readOnly: true
```

---

## 17. UPDATED IMPLEMENTATION CONSIDERATIONS

### What This Adds to the UI Complexity

The multi-container, sidecar, and Istio features add 3 optional panels per workload card:

| Panel | Complexity | User interaction |
|-------|-----------|-----------------|
| Init Containers | Medium — preset-driven, add/remove rows | [+ Add] button → preset or custom form |
| Sidecar Containers | Medium — preset-driven, add/remove rows | [+ Add] button → preset or custom form |
| Istio | Low — just a checkbox + resource inputs | Checkbox → reveal resource fields |

These are all **optional** collapsible `<details>` sections. The wizard stays simple for
basic use cases but exposes the power when needed.

### Collect() Updates Needed

```javascript
// Per workload card
svc.initContainers = [...];     // array of {name, image, command, resources, env, volumeMounts}
svc.sidecars = [...];           // array of {name, image, command, resources, env, volumeMounts, native: bool}
svc.istio = {
    enabled: false,
    proxyCPU: '100m',
    proxyCPULimit: '500m',
    proxyMemory: '128Mi',
    proxyMemoryLimit: '256Mi',
    excludeInboundPorts: '',
    excludeOutboundPorts: '',
    logLevel: 'warning',
};
```

### Review Step Updates

```
🚀 Deployment: api                                                     [create]
   📦 api (main)           ghcr.io/user/api:latest   port 8080
   ⏳ wait-for-db (init)   busybox:1.36              wait for postgres:5432
   📎 log-forwarder (sidecar) fluent/fluent-bit:2.2  shared: /var/log/app
   🔷 Istio proxy          injected                  CPU 100m/500m  Mem 128Mi/256Mi
```

### Backend Generation Updates

The backend must assemble the full pod spec:
1. `initContainers[]` — regular init containers first
2. `initContainers[]` — then native sidecars (with `restartPolicy: Always`) 
3. `containers[]` — main container + any traditional sidecars
4. Pod template annotations — Istio annotations if enabled
5. Shared `volumes[]` — auto-generated `emptyDir` for sidecar communication

---

## 18. DEPENDENCIES & CROSS-CONCERNS (UPDATED)

- The existing 1A–1E features (strategy, resources, probes, env vars, volumes) are all Deployment-centric. They need to be made conditional on the selected kind.
- The infra "Managed" option should show connection env var hints (cross-references app services' env vars — depends on 1D).
- Backend `generate_k8s_wizard` needs new kind handlers (StatefulSet, DaemonSet, Job, CronJob).
- The review step needs kind-aware summary rendering.
- **NEW:** Init containers, sidecars, and Istio are pod-level concerns — they apply to ALL workload kinds (Deployment, StatefulSet, DaemonSet, Job, CronJob).
- **NEW:** Shared volumes (`emptyDir`) between containers must be auto-managed when adding sidecars.
- **NEW:** Istio + Job requires K8s ≥ 1.28 native sidecar awareness.
- **NEW:** The "container" concept in compose (1 service = 1 container) vs K8s (1 workload = N containers in 1 pod) is a key mental model shift the UI must communicate.

