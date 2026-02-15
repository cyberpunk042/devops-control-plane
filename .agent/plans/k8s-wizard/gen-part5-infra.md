# Part 5: Infrastructure Decisions — Generation Spec

> How `_infraDecisions[]` flows through the translator and what it generates.

---

## Collector Output Shape

Each entry in `data._infraDecisions[]`:

```js
{
  name: "postgres",                      // infra service name (from Compose)
  kind: "StatefulSet",                   // "StatefulSet" | "Deployment" | "DaemonSet" | "Managed" | "Skip"
  image: "postgres:15",                  // from compose image field
  port: "5432",                          // string, first container port from compose
  envVars: [                             // same envVar shape as app services
    { key: "POSTGRES_DB", type: "hardcoded", value: "myapp" },
    { key: "POSTGRES_PASSWORD", type: "secret", value: "", varName: "${POSTGRES_PASSWORD}" },
  ],
  _compose: { /* raw compose object */ },

  // ── If kind !== "Managed" ──
  volumes: [                             // wizard volumes (pvc-dynamic, emptyDir, etc.)
    { type: "pvc-dynamic", name: "data", mountPath: "/var/lib/postgresql/data",
      size: "50Gi", accessMode: "ReadWriteOnce", storageClass: "longhorn" },
  ],

  // ── If kind === "Managed" ──
  providerNotes: "AWS RDS PostgreSQL",   // informational only, not in any manifest
}
```

### Key observations:
1. **Skip** → excluded from `infraDecisions` in collector (filtered at collection time)
2. **Managed** → no workload, no volumes, only ConfigMap/Secret for connection vars
3. **Self-hosted** (StatefulSet/Deployment/DaemonSet) → full workload + Service + PVC
4. **envVars** → always collected (both Managed and self-hosted use them)
5. **port** → extracted from compose; used for Service generation and wait-for init containers

---

## Decision Matrix: What Gets Generated

| Decision | Workload | Service | ConfigMap | Secret | PVCs |
|----------|----------|---------|-----------|--------|------|
| **Skip** | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Managed** | ❌ | ❌ | ✅ (if has hardcoded/variable env) | ✅ (if has secret env) | ❌ |
| **StatefulSet** | ✅ StatefulSet | ✅ Headless (clusterIP: None) | ✅ | ✅ | ✅ |
| **Deployment** | ✅ Deployment | ✅ ClusterIP | ✅ | ✅ | ✅ |
| **DaemonSet** | ✅ DaemonSet | ✅ ClusterIP (if port) | ✅ | ✅ | ✅ |

---

## Managed Infrastructure Flow

This is the most interesting path — Managed infra doesn't generate a workload
but its env vars get **injected into dependent app services**.

### Example: Managed PostgreSQL

**Collector output:**
```js
_infraDecisions: [{
  name: "postgres",
  kind: "Managed",
  envVars: [
    { key: "DB_HOST", type: "hardcoded", value: "my-rds-instance.abc.us-east-1.rds.amazonaws.com" },
    { key: "DB_PORT", type: "hardcoded", value: "5432" },
    { key: "DB_NAME", type: "hardcoded", value: "myapp" },
    { key: "DB_PASSWORD", type: "secret", value: "" },
  ],
  providerNotes: "AWS RDS PostgreSQL",
}]
```

**Generated resources:**
1. `postgres-config` ConfigMap:
   ```yaml
   data:
     DB_HOST: "my-rds-instance.abc.us-east-1.rds.amazonaws.com"
     DB_PORT: "5432"
     DB_NAME: "myapp"
   ```
2. `postgres-secrets` Secret:
   ```yaml
   stringData:
     DB_PASSWORD: "CHANGE_ME"
   ```

**Dependency wiring** — any app service with `dependencies: ["postgres"]` gets:
```yaml
# In the app service's container spec:
envFrom:
  - configMapRef:
      name: postgres-config    # ← injected by translator
  - secretRef:
      name: postgres-secrets   # ← injected by translator
```

### No wait-for init container for Managed

Managed infra doesn't generate a wait-for init container because there's
no K8s Service to wait for — the connection goes to an external endpoint.
The translator correctly handles this: wait-for is only generated when
`infra_lookup[dep].port` is set, and for Managed infra the port IS set
in the lookup but a wait-for IS generated for it.

**⚠️ GAP FOUND**: The translator generates wait-for init containers for
ALL dependencies with a port, including Managed infra. But for Managed
infra, the DNS name `postgres` won't resolve in the cluster because
there's no Service. The wait-for should be **skipped for Managed infra**.

---

## Self-Hosted Infrastructure Flow

### Example: Self-hosted PostgreSQL (StatefulSet)

**Generated resources:**
1. `postgres` StatefulSet workload
2. `postgres-headless` Headless Service (for StatefulSet)
3. `postgres-config` ConfigMap (if env vars)
4. `postgres-secrets` Secret (if secret env vars)
5. `postgres-data` PVC (for each pvc-dynamic/pvc-static volume)

**Dependency wiring** — app services with `dependencies: ["postgres"]`:
- wait-for init container: `nc -z postgres 5432`
  - Uses headless service DNS name (for StatefulSet)
  - Actually this is a nuance: the service name in K8s DNS is
    `postgres-headless` not `postgres`. **But** the translator uses
    the infra NAME (`postgres`) not the service name.
  - **⚠️ GAP FOUND**: The wait-for uses `postgres:5432` but the K8s Service
    name for StatefulSet infra is `postgres-headless`. The DNS would need
    to match the Service name, not the infra name.
- envFrom injection: only if the infra has ConfigMap/Secret resources
  (same as Managed, handled by `infra_lookup[dep].has_config/has_secrets`)

---

## Gaps Found

### Gap 1: Wait-for generated for Managed infra (incorrect)

The translator generates wait-for init containers for Managed infra
dependencies. Managed infra has no K8s Service, so `nc -z postgres 5432`
would hang forever.

**Fix**: Skip wait-for when `infra_lookup[dep_name].kind == "Managed"`.

### Gap 2: Wait-for uses wrong DNS name for StatefulSet infra

For StatefulSet infra, the Service is named `{name}-headless`, but the
wait-for init container uses `nc -z {name} {port}`. The DNS lookup
for `{name}` won't find the headless service.

**Fix**: Store the resolved K8s service name in `infra_lookup` and use
that for wait-for DNS.

---

## Implementation Status

### ✅ Already implemented:
- Managed infra → ConfigMap/Secret generation only (no workload)
- Self-hosted infra → full workload + Service + PVC generation
- Dependency wiring: envFrom injection of infra ConfigMap/Secret
- infra_lookup for dependency resolution

### ✅ Fixed (this session):
- **Gap 1**: Skip wait-for for Managed infra → `if dep_info.get("kind") == "Managed": continue`
- **Gap 2**: Use correct DNS name for StatefulSet infra wait-for → `infra_lookup[name]["svc_dns"]`
