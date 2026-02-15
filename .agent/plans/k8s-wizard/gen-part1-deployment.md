# Part 1: Deployment — Complete Generation Spec

> One Deployment service → all the manifests it produces, every field traced.

---

## Source: Wizard Collector Output (Compose Mode)

This is the exact shape the collector produces for a Deployment service.
Every field listed here MUST appear in the generated output.

```js
{
  // ─── Identity ───
  name: "api",                           // → metadata.name everywhere
  kind: "Deployment",                    // → apiVersion: apps/v1, kind: Deployment
  image: "api:latest",                   // → containers[0].image

  // ─── Deployment-specific ───
  port: "8080",                          // string! must parseInt
  replicas: "3",                         // string! must parseInt
  serviceType: "ClusterIP",              // → separate Service resource .spec.type
  strategy: "RollingUpdate",             // → spec.strategy.type
  maxSurge: "1",                         // → spec.strategy.rollingUpdate.maxSurge
  maxUnavailable: "0",                   // → spec.strategy.rollingUpdate.maxUnavailable

  // ─── Resources ───
  resources: {
    cpu_request: "100m",                 // → containers[0].resources.requests.cpu
    cpu_limit: "500m",                   // → containers[0].resources.limits.cpu
    memory_request: "128Mi",             // → containers[0].resources.requests.memory
    memory_limit: "512Mi",              // → containers[0].resources.limits.memory
  },
  // resources can be null if user left all blank

  // ─── Health Probes ───
  readinessProbe: {                      // null if not enabled
    type: "http",                        // "http" | "tcp" | "exec"
    path: "/healthz",                    // http only
    port: 8080,                          // http + tcp (already int from collector)
    command: "",                         // exec only
    initialDelaySeconds: 5,              // int
    periodSeconds: 10,                   // int
    extra: 3,                            // → failureThreshold
  },
  livenessProbe: {                       // same shape, null if not enabled
    type: "http",
    path: "/healthz",
    port: 8080,
    command: "",
    initialDelaySeconds: 15,
    periodSeconds: 20,
    extra: 3,
  },

  // ─── Environment Variables ───
  envVars: [
    // type: "hardcoded" → goes into ConfigMap data, container refs via envFrom configMapRef
    { key: "APP_ENV", type: "hardcoded", value: "production", varName: null,
      createInVault: false, newValue: "" },

    // type: "variable" → goes into ConfigMap data as placeholder, container refs via envFrom configMapRef
    { key: "LOG_LEVEL", type: "variable", value: "", varName: "${LOG_LEVEL}",
      createInVault: false, newValue: "" },

    // type: "secret" → goes into Secret stringData as placeholder, container refs via env[].secretKeyRef
    { key: "API_SECRET", type: "secret", value: "", varName: "${API_SECRET}",
      createInVault: true, newValue: "generated-value-here" },
  ],

  // ─── Volumes ───
  volumes: [
    // pvc-dynamic → 3 things: PVC resource + pod volume + container volumeMount
    {
      type: "pvc-dynamic",
      name: "uploads",                   // → PVC name, pod volume name, volumeMount name
      mountPath: "/app/uploads",         // → volumeMount.mountPath
      size: "20Gi",                      // → PVC .spec.resources.requests.storage
      accessMode: "ReadWriteOnce",       // → PVC .spec.accessModes[0]
      storageClass: "longhorn",          // → PVC .spec.storageClassName (empty = omit)
      longhornConfig: {                  // only present if storageClass contains "longhorn"
        replicas: "3",                   // → PVC annotation longhorn.io/number-of-replicas
        dataLocality: "best-effort",     // → PVC annotation longhorn.io/data-locality
      },
    },

    // pvc-static → same as pvc-dynamic but binds to existing PV
    {
      type: "pvc-static",
      name: "existing-data",
      mountPath: "/data",
      size: "50Gi",
      accessMode: "ReadWriteOnce",
      pvName: "my-existing-pv",          // → PVC annotation volume.beta.kubernetes.io/storage-class
                                          //   or PVC .spec.volumeName
      storageClass: "",
    },

    // emptyDir → 2 things: pod volume + container volumeMount (NO separate resource)
    {
      type: "emptyDir",
      mountPath: "/tmp/cache",
      medium: "Memory",                  // "" or "Memory" → emptyDir.medium
      sizeLimit: "256Mi",                // "" or size → emptyDir.sizeLimit
      // NOTE: no "name" field! Must synthesize: e.g. "empty-0" or slugify(mountPath)
    },

    // configMap → 2 things: pod volume (configMap ref) + container volumeMount
    {
      type: "configMap",
      mountPath: "/etc/app/config.yaml",
      configMapName: "app-config-files", // → volume.configMap.name
      key: "config.yaml",               // "" = mount all keys, "key" = mount single key via subPath
      // NOTE: no "name" field! Must synthesize volume name: e.g. "cm-app-config-files"
    },

    // secret → 2 things: pod volume (secret ref) + container volumeMount
    {
      type: "secret",
      mountPath: "/etc/tls",
      secretName: "tls-cert",           // → volume.secret.secretName
      key: "",                           // "" = mount all keys
      // NOTE: no "name" field! Must synthesize: e.g. "sec-tls-cert"
    },

    // hostPath → 2 things: pod volume (hostPath) + container volumeMount
    {
      type: "hostPath",
      mountPath: "/var/log/host",
      hostPath: "/var/log",              // → volume.hostPath.path
      hostType: "Directory",             // → volume.hostPath.type
      // NOTE: no "name" field! Must synthesize: e.g. "hp-0"
    },
  ],

  // ─── Init Containers ───
  initContainers: [
    {
      name: "migrate",
      image: "api:latest",
      command: "python manage.py migrate",  // → command: ["sh", "-c", "python manage.py migrate"]
    },
  ],

  // ─── Sidecar Containers ───
  sidecars: [
    {
      name: "log-shipper",
      image: "fluent-bit:2.1",
      command: "",                        // optional override
      nativeSidecar: true,                // true → initContainers with restartPolicy: Always
                                          // false → regular containers[]
      sharedVolume: "logs",               // → emptyDir volume name, mounted in BOTH main + sidecar
      sharedMount: "/var/log/app",        // → mountPath in both containers
    },
  ],

  // ─── Companion Containers (infrastructure moved into same pod) ───
  companions: [
    {
      name: "redis",
      image: "redis:7",
      port: "6379",                       // → containerPort
      env: [/* same envVar shape */],     // → container env/envFrom
      resources: {                        // null if not set
        cpu_request: "50m",
        cpu_limit: "200m",
        memory_request: "64Mi",
        memory_limit: "128Mi",
      },
      volumes: [                          // companion-specific volumes
        { name: "redis-data", type: "emptyDir", mountPath: "/data" },
      ],
      dependsOn: "postgres",             // → wait-for init container
      dependsOnPort: "5432",             // → port for nc check
    },
  ],

  // ─── Service Mesh ───
  mesh: {                                 // null/undefined if not enabled
    provider: "istio",                    // "istio" | "linkerd" | "consul" | "kuma"
    proxyCpuRequest: "100m",
    proxyCpuLimit: "500m",
    proxyMemRequest: "128Mi",
    proxyMemLimit: "256Mi",
    excludeInbound: "",                   // comma-separated port list
    excludeOutbound: "3306",
    logLevel: "warning",
  },

  // ─── Dependencies ───
  dependencies: ["postgres"],             // names of infra services this depends on
  // Effect 1: wait-for init container (nc -z {name} {port})
  // Effect 2: envFrom refs to {name}-config / {name}-secrets if infra is Managed

  // ─── Internal (stripped before save) ───
  _compose: { /* raw compose object */ },
}
```

---

## Generated Manifests

For one Deployment service, up to **6 files** are generated.

### File 1: `{output_dir}/{name}-deployment.yaml`

This is the core. Every other file is referenced FROM here.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: production                     # ← global namespace
  labels:
    app: api                                # ← convention: app={name}
spec:
  replicas: 3                               # ← parseInt(svc.replicas)
  selector:
    matchLabels:
      app: api
  strategy:                                 # ← from svc.strategy
    type: RollingUpdate                     # ← "RollingUpdate" or "Recreate"
    rollingUpdate:                          # ← only if type=RollingUpdate
      maxSurge: 1                           # ← parseInt(svc.maxSurge) or default 1
      maxUnavailable: 0                     # ← parseInt(svc.maxUnavailable) or default 0
  template:
    metadata:
      labels:
        app: api
      annotations:                          # ← only if mesh is configured
        sidecar.istio.io/inject: "true"
        sidecar.istio.io/proxyCPU: "100m"
        sidecar.istio.io/proxyCPULimit: "500m"
        sidecar.istio.io/proxyMemory: "128Mi"
        sidecar.istio.io/proxyMemoryLimit: "256Mi"
        traffic.sidecar.istio.io/excludeOutboundPorts: "3306"
        sidecar.istio.io/logLevel: "warning"
    spec:
      initContainers:
        # ── Dependency wait-for containers ──
        # For each name in svc.dependencies:
        #   Look up infra by name → get its port
        #   Generate busybox nc -z wait loop
        - name: wait-for-postgres
          image: busybox:1.36
          command:
            - sh
            - -c
            - |
              echo 'Waiting for postgres:5432…'
              until nc -z postgres 5432; do sleep 2; done
              echo 'Ready.'

        # ── User-defined init containers ──
        # From svc.initContainers[]
        - name: migrate
          image: api:latest
          command: ["sh", "-c", "python manage.py migrate"]

        # ── Native sidecars (K8s ≥1.28) ──
        # From svc.sidecars[] where nativeSidecar=true
        - name: log-shipper
          image: fluent-bit:2.1
          restartPolicy: Always             # ← marks it as native sidecar
          volumeMounts:
            - name: logs
              mountPath: /var/log/app

        # ── Companion wait-for containers ──
        # From svc.companions[] where dependsOn is set and != "__main__"
        # (companion redis depends on postgres)
        # This is actually already handled — companion dependsOn generates
        # wait-for init containers

      containers:
        # ── Main container ──
        - name: api
          image: api:latest
          ports:
            - containerPort: 8080           # ← parseInt(svc.port)
          resources:                        # ← only if svc.resources is not null
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
          readinessProbe:                   # ← only if svc.readinessProbe is not null
            httpGet:                        # ← type="http" → httpGet
              path: /healthz                # ← probe.path
              port: 8080                    # ← probe.port
            initialDelaySeconds: 5          # ← probe.initialDelaySeconds
            periodSeconds: 10               # ← probe.periodSeconds
            failureThreshold: 3             # ← probe.extra
          livenessProbe:                    # ← same pattern
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 15
            periodSeconds: 20
            failureThreshold: 3
          envFrom:                          # ← refs to generated ConfigMap
            - configMapRef:
                name: api-config            # ← {name}-config
            # ── Managed infra refs ──
            # For each dep in svc.dependencies where infra.kind=="Managed":
            - configMapRef:
                name: postgres-config       # ← {infraName}-config
            - secretRef:
                name: postgres-secrets      # ← {infraName}-secrets
          env:                              # ← individual secret refs
            # For each envVar where type=="secret":
            - name: API_SECRET
              valueFrom:
                secretKeyRef:
                  name: api-secrets         # ← {name}-secrets
                  key: API_SECRET           # ← envVar.key
          volumeMounts:
            # ── From svc.volumes[] ──
            - name: uploads                 # ← vol.name (pvc-dynamic has name)
              mountPath: /app/uploads       # ← vol.mountPath
            - name: empty-0                 # ← synthesized (emptyDir has no name)
              mountPath: /tmp/cache
            - name: cm-app-config-files     # ← synthesized from vol.configMapName
              mountPath: /etc/app/config.yaml
              subPath: config.yaml          # ← vol.key (when single key mount)
            - name: sec-tls-cert            # ← synthesized from vol.secretName
              mountPath: /etc/tls
            - name: hp-0                    # ← synthesized
              mountPath: /var/log/host
            # ── From sidecar shared volumes ──
            - name: logs                    # ← sidecar.sharedVolume
              mountPath: /var/log/app       # ← sidecar.sharedMount

        # ── Companion containers ──
        # From svc.companions[]
        - name: redis
          image: redis:7
          ports:
            - containerPort: 6379
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              cpu: "200m"
              memory: "128Mi"
          # companion env vars would go here (same ConfigMap/Secret pattern)
          volumeMounts:
            - name: redis-data
              mountPath: /data

        # ── Non-native sidecars ──
        # From svc.sidecars[] where nativeSidecar=false
        # (none in this example — log-shipper is native)

      volumes:
        # ── From svc.volumes[] ──
        # pvc-dynamic/pvc-static → persistentVolumeClaim ref
        - name: uploads
          persistentVolumeClaim:
            claimName: api-uploads          # ← convention: {svcName}-{volName}
                                            #   or just {volName} if unique enough

        # emptyDir → inline
        - name: empty-0
          emptyDir:
            medium: Memory                  # ← vol.medium (omit if "")
            sizeLimit: "256Mi"              # ← vol.sizeLimit (omit if "")

        # configMap → reference
        - name: cm-app-config-files
          configMap:
            name: app-config-files          # ← vol.configMapName
            items:                          # ← only if vol.key is set
              - key: config.yaml
                path: config.yaml

        # secret → reference
        - name: sec-tls-cert
          secret:
            secretName: tls-cert            # ← vol.secretName
            # no items if vol.key is ""

        # hostPath → inline
        - name: hp-0
          hostPath:
            path: /var/log                  # ← vol.hostPath
            type: Directory                 # ← vol.hostType

        # ── From sidecar shared volumes ──
        - name: logs
          emptyDir: {}

        # ── From companion volumes ──
        - name: redis-data
          emptyDir: {}                      # ← companion vol type=emptyDir
```

### File 2: `{output_dir}/{name}-service.yaml`

Generated if `svc.port` is set and `svc.kind` is NOT `Job`/`CronJob`.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: api
  namespace: production
spec:
  type: LoadBalancer                        # ← svc.serviceType
  selector:
    app: api                                # ← app={name}
  ports:
    - port: 80                              # ← convention: external port 80
      targetPort: 8080                      # ← parseInt(svc.port)
      protocol: TCP
```

**Open question**: Should the Service `port:` be 80 (convention) or match `targetPort`? I'll note this but move on.

### File 3: `{output_dir}/{name}-config.yaml` — ConfigMap

Generated if there are ANY envVars with `type === "hardcoded"` OR `type === "variable"`.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: api-config                          # ← {name}-config
  namespace: production
data:
  APP_ENV: "production"                     # ← hardcoded: key=value
  LOG_LEVEL: "${LOG_LEVEL}"                 # ← variable: key=${varName} as placeholder
```

### File 4: `{output_dir}/{name}-secrets.yaml` — Secret

Generated if there are ANY envVars with `type === "secret"`.

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: api-secrets                         # ← {name}-secrets
  namespace: production
type: Opaque
stringData:
  API_SECRET: "CHANGE_ME"                   # ← placeholder for each secret key
```

### File 5: `{output_dir}/{name}-{volName}-pvc.yaml` — PVC (one per pvc-dynamic/pvc-static volume)

Generated for each volume with `type === "pvc-dynamic"` or `type === "pvc-static"`.

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: api-uploads                         # ← {name}-{vol.name} or just vol.name
  namespace: production
  annotations:                              # ← only if longhornConfig exists
    longhorn.io/number-of-replicas: "3"
    longhorn.io/data-locality: "best-effort"
spec:
  accessModes:
    - ReadWriteOnce                         # ← vol.accessMode
  storageClassName: longhorn                # ← vol.storageClass (omit key entirely if "")
  resources:
    requests:
      storage: "20Gi"                       # ← vol.size
  # For pvc-static:
  # volumeName: my-existing-pv              # ← vol.pvName (binds to specific PV)
```

### File 6: Companion ConfigMap/Secret (if companion has env vars)

Same pattern as Files 3/4 but for the companion. Name convention:
`{svcName}-{companionName}-config` / `{svcName}-{companionName}-secrets`

The companion container's `envFrom` references these.

---

## Volume Name Synthesis Rules

Several volume types lack a `name` field in the collector output.
These need deterministic synthetic names:

| Volume Type | Has `name`? | Synthesis Rule | Example |
|-------------|-------------|----------------|---------|
| `pvc-dynamic` | ✅ `vol.name` | Use directly | `uploads` |
| `pvc-static` | ✅ `vol.name` | Use directly | `existing-data` |
| `emptyDir` | ❌ | `empty-{index}` | `empty-0` |
| `configMap` | ❌ | `cm-{vol.configMapName}` | `cm-app-config-files` |
| `secret` | ❌ | `sec-{vol.secretName}` | `sec-tls-cert` |
| `hostPath` | ❌ | `hp-{index}` | `hp-0` |

---

## PVC Naming Convention

The PVC resource name must EXACTLY match the `claimName` referenced in the pod volume.

Rule: `{vol.name}` — use the volume name directly.
If collision risk (e.g. two services with volume named "data"), prefix with service name: `{svcName}-{vol.name}`.

**Decision needed**: always prefix with svcName, or only on collision?
Recommendation: always prefix → predictable, no surprise collisions.
So: `api-uploads` in both the PVC resource and the pod volume claimName.

---

## Dependency → Init Container Mapping

For each `dep` in `svc.dependencies[]`:
1. Look up `dep` in `_infraDecisions[]` by name
2. Get its `port`
3. Generate init container:

```yaml
- name: wait-for-{dep}
  image: busybox:1.36
  command:
    - sh
    - -c
    - |
      echo 'Waiting for {dep}:{port}…'
      until nc -z {dep} {port}; do sleep 2; done
      echo 'Ready.'
```

4. If the infra is `Managed`:
   - Add `envFrom` refs to `{dep}-config` and `{dep}-secrets` in the main container
   - The ConfigMap/Secret for the managed infra are generated separately (see Part 6: Infra)

5. If the infra is `StatefulSet` (self-hosted):
   - The wait-for init container still uses the infra service DNS name
   - No automatic envFrom injection — the user configures their own env vars

---

## Probe → K8s Spec Mapping

```
probe.type === "http"
  → httpGet:
      path: probe.path
      port: probe.port

probe.type === "tcp"
  → tcpSocket:
      port: probe.port

probe.type === "exec"
  → exec:
      command: ["sh", "-c", probe.command]

Always:
  initialDelaySeconds: probe.initialDelaySeconds  (if > 0)
  periodSeconds: probe.periodSeconds              (if > 0)
  failureThreshold: probe.extra                   (if > 0)
```

---

## Strategy Mapping

```
svc.strategy === "Recreate"
  → spec.strategy:
      type: Recreate
  (no rollingUpdate block)

svc.strategy === "RollingUpdate"
  → spec.strategy:
      type: RollingUpdate
      rollingUpdate:
        maxSurge: parseInt(svc.maxSurge) || 1
        maxUnavailable: parseInt(svc.maxUnavailable) || 0
```

---

## Mesh Annotation Mapping

Already implemented in `_build_mesh_annotations` (k8s_ops.py:1893-1931).
Uses `_MESH_ANNOTATION_PREFIXES` dict per provider. ✅ No changes needed.

---

## Implementation Status (updated 2026-02-14)

### ✅ Now implemented:
- Main container (name, image, port, command/args)
- Resource limits/requests
- **Health probes** (readinessProbe, livenessProbe) → `_build_probe()`
- **Main-container wizard volumes** → `_build_wizard_volume()` called from `_build_pod_template`
- Init containers (name, image, command)
- Sidecar containers (native + regular, shared volumes)
- Companion containers (image, port, resources, volumes, dependsOn → wait-for)
- Mesh annotations
- **Env vars with service-name convention** → `_build_env_vars(svc_name=...)`
- **envFrom bulk ConfigMap/Secret refs** → set by translator
- **Deployment strategy** from wizard values (not hardcoded)
- **PersistentVolumeClaim** kind handling in `generate_k8s_wizard`
- **output_dir** parameterization
- **Host access flags** (hostNetwork, hostPID, hostIPC)
- **ConfigMap/Secret resource generation** → `_svc_env_to_resources()`
- **PVC resource generation** → `_svc_volumes_to_pvc_resources()`
- **Translator function** → `wizard_state_to_resources()`
- **StatefulSet extras** (podManagementPolicy, updateStrategy, partition)
- **DaemonSet extras** (nodeSelector string→dict, updateStrategy)
- **CronJob extras** (suspend, startingDeadlineSeconds, ttlSecondsAfterFinished)
- **Backend route** → `setup_k8s` action calls translator → generator → writes files to disk
- **Frontend wiring** → `onComplete` sends full wizard state to backend
- **Skaffold generation** → `_generate_skaffold()` creates skaffold.yaml from wizard state
- **Multi-service Ingress** → path-based routing with pre-built rules for multiple services
- **Overwrite protection** → route respects `overwrite=False` flag, skips existing files
- **Modules mode collector fix** → full advanced field collection (parity with compose mode)
- **Multi-service warning removed** → all services fully generated now

### ⚠️ Low-priority remaining:
- **Companion env var ConfigMap/Secret** (companion-specific, rarely needed)
- **Companion PVC volumes** (companion-specific PVC resources, rarely used)

---

## Summary: What a Deployment generates

| # | File | Condition | K8s Kind |
|---|------|-----------|----------|
| 1 | `{name}-deployment.yaml` | Always | Deployment |
| 2 | `{name}-service.yaml` | If port is set | Service |
| 3 | `{name}-config.yaml` | If any hardcoded/variable envVars | ConfigMap |
| 4 | `{name}-secrets.yaml` | If any secret envVars | Secret |
| 5 | `{name}-{volName}-pvc.yaml` | For each pvc-dynamic/pvc-static volume | PersistentVolumeClaim |
| 6 | `{name}-{compName}-config.yaml` | If companion has hardcoded/variable env | ConfigMap |
| 7 | `{name}-{compName}-secrets.yaml` | If companion has secret env | Secret |

