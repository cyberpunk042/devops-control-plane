# Part 2: StatefulSet — Generation Spec (Deltas from Deployment)

> Everything that differs from the Deployment flow.
> Shared behaviors (probes, resources, env vars, init containers, sidecars, companions, mesh)
> are identical to Part 1 and not repeated here.

---

## Collector Output Shape (StatefulSet-specific fields)

```js
{
  name: "api",
  kind: "StatefulSet",
  image: "api:latest",
  port: "8080",                          // string → parseInt
  replicas: "1",                         // string → parseInt

  // ── StatefulSet-only fields ──
  headlessServiceName: "api-headless",   // → StatefulSet spec.serviceName
                                          // → Headless Service metadata.name
  podManagementPolicy: "OrderedReady",   // "OrderedReady" (default, omittable) | "Parallel"
  alsoCreateClusterIP: false,            // checkbox: also create a regular ClusterIP Service
  strategy: "RollingUpdate",             // "RollingUpdate" | "OnDelete" → spec.updateStrategy.type
  partition: 0,                          // int, only if strategy=RollingUpdate
                                          // → spec.updateStrategy.rollingUpdate.partition

  // ── No regular volumes! ──
  // The toggle hides the volumes panel for StatefulSet.
  // Instead, volumes are modeled as volumeClaimTemplates:
  volumeClaimTemplates: [
    {
      name: "data",                       // → VCT metadata.name
      mountPath: "/var/lib/data",         // → main container volumeMounts[].mountPath
      size: "10Gi",                       // → VCT spec.resources.requests.storage
      accessMode: "ReadWriteOnce",        // → VCT spec.accessModes[0]
      storageClass: "longhorn",           // → VCT spec.storageClassName (omit if "")
    },
    {
      name: "logs",
      mountPath: "/var/log/app",
      size: "5Gi",
      accessMode: "ReadWriteOnce",
      storageClass: "",                   // omit storageClassName entirely
    },
  ],

  // ── Shared fields (same as Deployment) ──
  readinessProbe: {...},
  livenessProbe: {...},
  envVars: [...],
  resources: {...},
  initContainers: [...],
  sidecars: [...],
  companions: [...],
  mesh: {...},
  // NOTE: no dependencies[] — hidden for StatefulSet in the toggle
  // NOTE: no serviceType — headless is mandatory
  // NOTE: no strategy.maxSurge/maxUnavailable — those are Deployment-only
}
```

---

## Generated Manifests

For one StatefulSet service, up to **5 files**:

### File 1: `{output_dir}/{name}-statefulset.yaml`

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: api
  namespace: production
  labels:
    app: api
spec:
  replicas: 1
  serviceName: api-headless                  # ← svc.headlessServiceName
  selector:
    matchLabels:
      app: api
  podManagementPolicy: Parallel              # ← svc.podManagementPolicy (omit if OrderedReady)
  updateStrategy:                            # ← svc.strategy
    type: RollingUpdate
    rollingUpdate:                           # ← only if type=RollingUpdate AND partition > 0
      partition: 2
  template:
    metadata:
      labels:
        app: api
      # (mesh annotations if configured — same as Deployment)
    spec:
      # initContainers, containers, volumes — same pod template logic as Deployment
      # EXCEPT: VCT mountPaths must be added to main container's volumeMounts
      containers:
        - name: api
          image: api:latest
          ports:
            - containerPort: 8080
          volumeMounts:
            - name: data                     # ← VCT name (matches VCT metadata.name)
              mountPath: /var/lib/data       # ← VCT mountPath
            - name: logs
              mountPath: /var/log/app
            # (+ any sidecar shared volumes, companion volumes)
  volumeClaimTemplates:                      # ← from svc.volumeClaimTemplates[]
    - metadata:
        name: data
      spec:
        accessModes:
          - ReadWriteOnce
        storageClassName: longhorn           # ← omit if empty
        resources:
          requests:
            storage: 10Gi
    - metadata:
        name: logs
      spec:
        accessModes:
          - ReadWriteOnce
        resources:
          requests:
            storage: 5Gi
```

### File 2: `{output_dir}/{name}-headless-service.yaml`

**Always generated** — a StatefulSet requires a headless Service.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: api-headless                         # ← svc.headlessServiceName
  namespace: production
spec:
  clusterIP: None                            # ← headless marker
  selector:
    app: api
  ports:
    - port: 8080                             # ← parseInt(svc.port)
      targetPort: 8080
```

### File 3 (optional): `{output_dir}/{name}-service.yaml`

Generated **only if** `svc.alsoCreateClusterIP === true`.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: api
  namespace: production
spec:
  type: ClusterIP
  selector:
    app: api
  ports:
    - port: 8080
      targetPort: 8080
```

### Files 4-5: ConfigMap/Secret (same as Deployment)

If `svc.envVars` contains hardcoded/variable → `{name}-config.yaml`
If `svc.envVars` contains secret → `{name}-secrets.yaml`

---

## Key Difference: VCT mountPath → volumeMounts

This is the **critical gap** from Part 1.

For Deployments, volumes come from `wizardVolumes[]` and get processed by
`_build_wizard_volume()`. For StatefulSets, volumes come from
`volumeClaimTemplates[]` instead.

The VCT is a K8s StatefulSet concept: each pod gets its own PVC named
`{vctName}-{podName}-{ordinal}`. The pod spec references them by the
VCT name in `volumeMounts`, but they don't appear in `volumes[]`.

**So `_build_pod_template` needs to add volumeMounts for each VCT.**

Mapping:
```
For each VCT in svc.volumeClaimTemplates:
  → main_container.volumeMounts[].push({
      name: vct.name,         // matches VCT metadata.name
      mountPath: vct.mountPath,
  })
```

This is NOT the same as wizard volumes. VCTs don't need pod-level volume
definitions because K8s injects them automatically from the
volumeClaimTemplates. We ONLY need the volumeMount on the container.

---

## What's NOT generated for StatefulSet

| Feature | Why | 
|---------|-----|
| Regular PVC resources | StatefulSet creates PVCs via volumeClaimTemplates automatically |
| Regular volumes | Hidden in UI, replaced by VCTs |
| Service type selector | Headless is mandatory |
| Dependencies | Hidden in UI, StatefulSet IS the infrastructure |
| Deployment strategy fields | maxSurge/maxUnavailable are Deployment-only |

---

## Implementation Status

### ✅ Already implemented (from Part 1):
- `generate_k8s_wizard` StatefulSet branch: podManagementPolicy, updateStrategy, partition, VCTs
- `wizard_state_to_resources` StatefulSet branch: headless Service, optional ClusterIP Service
- Headless Service generation (`clusterIP: None`)

### ✅ Fixed (this session):
- **VCT mountPaths** — `_build_pod_template` now adds volumeMounts for each VCT
  on the main container. Each VCT's `mountPath` becomes a `volumeMount` entry.
