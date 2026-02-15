# Part 3: DaemonSet — Generation Spec (Deltas from Deployment)

> Everything that differs from the Deployment flow.
> Shared behaviors (probes, resources, env vars, init containers, sidecars, companions, mesh, volumes)
> are identical to Part 1 and not repeated here.

---

## Collector Output Shape (DaemonSet-specific fields)

```js
{
  name: "node-exporter",
  kind: "DaemonSet",
  image: "node-exporter:latest",
  port: "",                              // optional! Can be empty string (no port → no Service)

  // ── DaemonSet-only fields ──
  strategy: "RollingUpdate",             // "RollingUpdate" | "OnDelete"
                                          // → spec.updateStrategy.type
  maxUnavailable: "1",                   // only if strategy=RollingUpdate
                                          // → spec.updateStrategy.rollingUpdate.maxUnavailable

  nodeSelector: "kubernetes.io/os=linux,monitoring=true",
                                          // string format "key=val, key=val"
                                          // → parsed into dict → pod spec.nodeSelector

  tolerations: [                         // array of toleration objects (checkbox-driven)
    {
      key: "node-role.kubernetes.io/control-plane",
      effect: "NoSchedule",
      operator: "Exists",
    },
    {
      key: "",                            // empty key + Exists = tolerate everything with this effect
      operator: "Exists",
      effect: "NoSchedule",
    },
  ],

  // ── Host Access (checkboxes) ──
  hostNetwork: true,                     // → pod spec.hostNetwork
  hostPID: false,                        // → pod spec.hostPID
  hostIPC: false,                        // → pod spec.hostIPC

  // ── Shared fields (same as Deployment) ──
  readinessProbe: {...},
  livenessProbe: {...},
  envVars: [...],
  resources: {...},
  volumes: [...],                         // regular wizard volumes (not VCTs)
  initContainers: [...],
  sidecars: [...],
  companions: [...],
  mesh: {...},
  // NOTE: no replicas — DaemonSet runs one per matching node
  // NOTE: no serviceType — hidden in UI; Service is ClusterIP if port is set
  // NOTE: no dependencies — hidden for DaemonSet
}
```

---

## Generated Manifests

For one DaemonSet service, up to **5 files**:

### File 1: `{output_dir}/{name}-daemonset.yaml`

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: node-exporter
  namespace: monitoring
  labels:
    app: node-exporter
spec:
  selector:
    matchLabels:
      app: node-exporter
  updateStrategy:                            # ← svc.strategy
    type: RollingUpdate
    rollingUpdate:                           # ← only if type=RollingUpdate
      maxUnavailable: 1                     # ← svc.maxUnavailable
  template:
    metadata:
      labels:
        app: node-exporter
    spec:
      hostNetwork: true                     # ← svc.hostNetwork
      # hostPID: true                       # ← only if checked
      # hostIPC: true                       # ← only if checked
      nodeSelector:                          # ← parsed from "key=val" string
        kubernetes.io/os: linux
        monitoring: "true"
      tolerations:                           # ← from checkbox-driven array
        - key: node-role.kubernetes.io/control-plane
          effect: NoSchedule
          operator: Exists
        - key: ""
          operator: Exists
          effect: NoSchedule
      containers:
        - name: node-exporter
          image: node-exporter:latest
          # ports only if svc.port is set
          # resources, probes, env, volumes — same as Deployment
      # volumes, initContainers — same as Deployment
```

### File 2 (optional): `{output_dir}/{name}-service.yaml`

Generated **only if** `svc.port` is set (non-empty string).

```yaml
apiVersion: v1
kind: Service
metadata:
  name: node-exporter
  namespace: monitoring
spec:
  type: ClusterIP                            # ← always ClusterIP for DaemonSet
  selector:
    app: node-exporter
  ports:
    - port: 9100
      targetPort: 9100
```

### Files 3-5: ConfigMap/Secret/PVCs (same as Deployment)

---

## Key Differences from Deployment

| Feature | Deployment | DaemonSet |
|---------|-----------|-----------|
| Replicas | User-defined (default 2) | N/A — one per node |
| Service Type | User-selectable | Always ClusterIP (if port set) |
| Strategy | RollingUpdate/Recreate with maxSurge/maxUnavailable | RollingUpdate/OnDelete with maxUnavailable only |
| Node selection | None | nodeSelector + tolerations |
| Host access | None | hostNetwork/hostPID/hostIPC |
| Dependencies | User-configurable | Hidden in UI |
| Volumes | Regular wizard volumes | Regular wizard volumes (same as Deployment) |

---

## Implementation Status

### ✅ Fully implemented — no gaps:

**Translator** (`wizard_state_to_resources`):
- DaemonSet kind-specific fields: strategy, maxUnavailable, nodeSelector, tolerations, hostNetwork/PID/IPC
- Port → optional Service generation (ClusterIP always)
- All shared fields (env vars, probes, resources, volumes, etc.)

**Generator** (`generate_k8s_wizard` DaemonSet branch):
- updateStrategy with RollingUpdate/OnDelete
- nodeSelector string → dict parsing (comma-separated "key=val" format)
- Tolerations array pass-through to pod spec
- Host access flags supported in `_build_pod_template`

### ❌ No gaps found.
