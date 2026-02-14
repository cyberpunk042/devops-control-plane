# K8s Wizard — 1E. Volume Mounts — Detailed Plan

## STATUS: ✅ Implemented — Backend + UI + Collect + Review

---

## 0. K8s Storage Model — What We Must Support

Kubernetes volumes are NOT a flat concept. The wizard must understand
the layered model to generate correct manifests.

### Volume Categories

| Category | K8s Objects Created | How Accessed |
|----------|-------------------|-------------|
| **1. Persistent (CSI/dynamic)** | PVC only — PV auto-created by StorageClass provisioner | Pod → PVC → (auto) PV → CSI driver → storage backend |
| **2. Persistent (static)** | PV + PVC — user manages both | Pod → PVC → PV → storage backend |
| **3. Ephemeral** | None (inline in Pod spec) | `emptyDir`, `configMap`, `secret`, `projected`, `downwardAPI` |
| **4. Object storage** | None (not a K8s volume) | HTTP API / SDK (MinIO, S3, GCS) — NOT mounted unless via CSI wrapper |

### StorageClass — The Key Concept

The **StorageClass** determines which provisioner creates PVs and how.
It is the user's primary decision point for persistent storage.

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: longhorn
provisioner: driver.longhorn.io
parameters:
  numberOfReplicas: "3"
  dataLocality: "best-effort"
```

Common StorageClasses:
- `(default)` — whatever the cluster admin set as default
- `longhorn` — Longhorn CSI (auto-creates PV + Volume + Replicas + Engine)
- `gp2` / `gp3` — AWS EBS
- `premium-rwo` — GKE
- `managed-premium` / `managed-csi` — Azure
- `nfs-client` — NFS via CSI
- `ceph-rbd` — Ceph block via CSI
- `local-path` — Rancher local-path-provisioner

### Provisioning Modes

**Dynamic (default, most common):**
- User creates: 1 PVC manifest
- Provisioner creates: PV automatically
- Manifest: just `PersistentVolumeClaim` with `storageClassName`

**Static (advanced):**
- User creates: 1 PV + 1 PVC
- PVC binds to PV by label selector or explicit `volumeName`
- Manifests: `PersistentVolume` + `PersistentVolumeClaim`

The wizard defaults to **dynamic provisioning**. Static is an advanced option
shown in a collapsed `<details>` panel.

---

## 1. BACKEND — StorageClass Detection API

### New function: `k8s_storage_classes()` in `k8s_ops.py`

```python
def k8s_storage_classes() -> dict:
    """List available StorageClasses from the cluster.

    Returns:
        {
            "ok": True,
            "storage_classes": [
                {
                    "name": "longhorn",
                    "provisioner": "driver.longhorn.io",
                    "is_default": False,
                    "reclaim_policy": "Delete",
                    "volume_binding_mode": "Immediate",
                    "parameters": {"numberOfReplicas": "3", ...},
                },
                ...
            ],
            "default_class": "longhorn" | null,
        }
    """
```

**Implementation:** Follows same pattern as `k8s_namespaces()`:
```python
result = _run_kubectl("get", "storageclasses", "-o", "json", timeout=10)
```

Parse the JSON, extract:
- `metadata.name`
- `provisioner`
- `metadata.annotations["storageclass.kubernetes.io/is-default-class"]` == "true"
- `reclaimPolicy`
- `volumeBindingMode`
- `parameters` (dict of provisioner-specific params)

### New route: `/k8s/storageclasses` in `routes_k8s.py`

```python
@k8s_bp.route("/k8s/storageclasses")
def k8s_storage_classes():
    result = k8s_ops.k8s_storage_classes()
    return jsonify(result)
```

---

## 2. COMPOSE VOLUME PARSING — `_classifyVolume()`

The compose volume string format:
```
"postgres-data:/var/lib/postgresql/data"     → named volume
"./data:/app/data"                            → data bind mount
"./src:/app/src"                              → dev bind mount (skip)
"/tmp/cache:/cache"                           → absolute bind mount
"mydata:/data:ro"                             → named, read-only
```

### Classification Function

```javascript
function _classifyVolume(volStr) {
    const parts = volStr.split(':');
    const source = parts[0];
    const target = parts[1] || source;
    const flags = parts[2] || '';
    const readOnly = flags.includes('ro');

    // Named volume (no path separator in source)
    if (!source.includes('/') && !source.startsWith('.')) {
        return {
            type: 'pvc',           // K8s type: PVC (dynamic)
            name: source,          // PVC name = compose volume name
            mountPath: target,     // Container mount path
            readOnly,
            source,
            defaultSize: '10Gi',   // Reasonable default for named volumes
            classification: 'named',
        };
    }

    // Dev bind mount — source code directories
    // These do NOT belong in K8s manifests. Source code is baked into the image.
    const devPatterns = /^\.\/(src|app|lib|pkg|cmd|internal|components|pages|public|assets|frontend|backend|server|client|api)/;
    if (devPatterns.test(source)) {
        return {
            type: 'skip',
            name: source.replace(/^\.\//, '').replace(/\//g, '-'),
            mountPath: target,
            readOnly,
            source,
            classification: 'dev-bind',
            skipReason: 'Source code is baked into the container image at build time',
        };
    }

    // Data bind mount — persistent data directories
    const dataPatterns = /^\.\/(data|db|storage|uploads|logs|backup|config|certs|ssl|tls)/;
    if (dataPatterns.test(source) || /^\//.test(source)) {
        return {
            type: 'pvc',
            name: source.replace(/^\.\//, '').replace(/\//g, '-'),
            mountPath: target,
            readOnly,
            source,
            defaultSize: '5Gi',
            classification: 'data-bind',
        };
    }

    // Unknown bind mount — default to skip (user can override)
    return {
        type: 'skip',
        name: source.replace(/^\.\//, '').replace(/\//g, '-'),
        mountPath: target,
        readOnly,
        source,
        classification: 'unknown-bind',
        skipReason: 'Bind mount — may not be needed in K8s (override if needed)',
    };
}
```

---

## 3. UI DESIGN — Per-Volume Row Interface

### Overall Panel Structure

```
▸ Volume Mounts (3 from Compose)
  ┌──────────────────────────────────────────────────────────────────────┐
  │                                                                      │
  │ Storage Class:  [longhorn         ▾]  (detected from cluster)        │
  │                  ├ longhorn (default) — driver.longhorn.io            │
  │                  ├ nfs-client — nfs-subdir-external-provisioner       │
  │                  └ (custom…)                                          │
  │                                                                      │
  │ ────────────────────────────────────────────────────────────────────  │
  │                                                                      │
  │ ☑ postgres-data → /var/lib/postgresql/data                 [named]  │
  │   Type [PVC (dynamic) ▾]  Size [10Gi]  Access [ReadWriteOnce ▾]     │
  │                                                                      │
  │ ☑ ./data → /app/data                                    [data-bind] │
  │   Type [PVC (dynamic) ▾]  Size [5Gi]   Access [ReadWriteOnce ▾]     │
  │                                                                      │
  │ ☐ ./src → /app/src                          ⚠️ dev-only (skipped)   │
  │   Source code is baked into the container image at build time.        │
  │                                                                      │
  │ [+ Add volume mount]                                                 │
  │                                                                      │
  └──────────────────────────────────────────────────────────────────────┘
```

### StorageClass Selector (Top of Volume Panel)

The StorageClass is set **once per service** (not per volume), shown at the top
of the volume panel. All PVCs for this service use the same StorageClass.

- If cluster connected: async call to `/api/k8s/storageclasses` to populate dropdown
  - Shows provisioner name alongside class name
  - Marks default class with "(default)" tag
- If no cluster: just a text input with placeholder "e.g. longhorn, gp2, default"
- Empty = use cluster default (omit `storageClassName` from PVC — K8s uses default)
- "Custom…" option reveals text input for manual entry

**ID:** `k8s-svc-storageclass-{i}`

### Per-Volume Controls

Each volume row has these controls:

**Column 1: Include checkbox**
- `k8s-svc-vol-chk-{i}-{j}` — checkbox
- Checked by default for `pvc` classification
- Unchecked by default for `skip` classification

**Column 2: Source + Mount Path display**
- Shows compose source → mount path
- Mount path is editable: `k8s-svc-vol-mount-{i}-{j}`

**Column 3: K8s Volume Type**
- `k8s-svc-vol-type-{i}-{j}` — select
- Options:
  | Value | Label | When Selected |
  |-------|-------|--------------|
  | `pvc-dynamic` | PVC (dynamic) | Show: size, access mode. _Default for named/data volumes_ |
  | `pvc-static` | PVC (static — advanced) | Show: size, access mode, PV name. _For pre-existing PVs_ |
  | `emptyDir` | emptyDir (ephemeral) | Show: medium select (disk/memory), sizeLimit. _Data lost on pod restart_ |
  | `configMap` | ConfigMap (file mount) | Show: configMap name, mount path, items. _Mount config as file_ |
  | `secret` | Secret (file mount) | Show: secret name, mount path, items. _Mount secret as file (e.g. TLS certs)_ |
  | `hostPath` | hostPath (⚠️ not recommended) | Show: host path, type select. _Security risk, not portable_ |

**Column 4: Type-specific sub-fields (conditional)**

**When `pvc-dynamic`:**
- `k8s-svc-vol-size-{i}-{j}` — text input, e.g. "10Gi"
- `k8s-svc-vol-access-{i}-{j}` — select: ReadWriteOnce (default) | ReadWriteMany | ReadOnlyMany
- `k8s-svc-vol-name-{i}-{j}` — PVC name (pre-filled from compose name or generated)

**When `pvc-static`:**
- Same as dynamic PLUS:
- `k8s-svc-vol-pvname-{i}-{j}` — text input for PV name to bind to
- Note: "Requires a pre-existing PersistentVolume in the cluster"

**When `emptyDir`:**
- `k8s-svc-vol-medium-{i}-{j}` — select: `""` (disk, default) | `Memory` (tmpfs, faster but uses RAM)
- `k8s-svc-vol-sizelimit-{i}-{j}` — text, e.g. "1Gi" (optional, limit for the emptyDir)
- Warning: "⚠️ Data is lost when pod is restarted or rescheduled"

**When `configMap`:**
- `k8s-svc-vol-cmname-{i}-{j}` — text, ConfigMap resource name
- `k8s-svc-vol-cmkey-{i}-{j}` — text, specific key (optional, if mounting single file)
- Note: "Mounts ConfigMap data as files in the container"

**When `secret`:**
- `k8s-svc-vol-secname-{i}-{j}` — text, Secret resource name
- `k8s-svc-vol-seckey-{i}-{j}` — text, specific key (optional)
- Note: "Mounts Secret data as files (e.g. TLS certificates, SSH keys)"

**When `hostPath`:**
- `k8s-svc-vol-hostpath-{i}-{j}` — text, host filesystem path
- `k8s-svc-vol-hosttype-{i}-{j}` — select: DirectoryOrCreate | Directory | FileOrCreate | File
- Warning: "⚠️ Not portable. Ties pod to specific node. Security risk."

### Longhorn-Specific Options

When the StorageClass dropdown value contains "longhorn":
- Show an optional collapsed `<details>` with:
  - Number of replicas: `k8s-svc-vol-lh-replicas-{i}` (default 3)
  - Data locality: `k8s-svc-vol-lh-locality-{i}` (best-effort | strict | disabled)
- These map to PVC annotations:
  ```yaml
  annotations:
    numberOfReplicas: "3"
    dataLocality: "best-effort"
  ```
- For anything beyond these basics → user enters as custom annotations text

---

## 4. PRE-FILL LOGIC

1. Parse each compose volume string via `_classifyVolume()`
2. For each classified volume:
   - `named` → checkbox checked, type = `pvc-dynamic`, size = 10Gi, access = ReadWriteOnce
   - `data-bind` → checkbox checked, type = `pvc-dynamic`, size = 5Gi, access = ReadWriteOnce
   - `dev-bind` → checkbox unchecked, type = skip, with clear explanation
   - `unknown-bind` → checkbox unchecked, type = skip, user can override
3. PVC name: from compose volume name (sanitized) or generated as `{svcName}-{purpose}-{j}`
4. Mount path: from compose target
5. StorageClass: empty (cluster default) unless cluster connected and we detect options

---

## 5. TYPE SELECT `onchange` HANDLER

```javascript
onchange="((sel) => {
    const i = sel.dataset.i, j = sel.dataset.j;
    const t = sel.value;
    // Toggle visibility of sub-field rows
    const pvcFields = document.getElementById('k8s-vol-pvc-fields-' + i + '-' + j);
    const staticFields = document.getElementById('k8s-vol-static-fields-' + i + '-' + j);
    const emptyFields = document.getElementById('k8s-vol-empty-fields-' + i + '-' + j);
    const cmFields = document.getElementById('k8s-vol-cm-fields-' + i + '-' + j);
    const secFields = document.getElementById('k8s-vol-sec-fields-' + i + '-' + j);
    const hostFields = document.getElementById('k8s-vol-host-fields-' + i + '-' + j);
    if (pvcFields)    pvcFields.style.display    = (t === 'pvc-dynamic' || t === 'pvc-static') ? '' : 'none';
    if (staticFields) staticFields.style.display = (t === 'pvc-static') ? '' : 'none';
    if (emptyFields)  emptyFields.style.display  = (t === 'emptyDir') ? '' : 'none';
    if (cmFields)     cmFields.style.display     = (t === 'configMap') ? '' : 'none';
    if (secFields)    secFields.style.display     = (t === 'secret') ? '' : 'none';
    if (hostFields)   hostFields.style.display   = (t === 'hostPath') ? '' : 'none';
})(this)"
```

---

## 6. COLLECT() OUTPUT

```javascript
svc.volumes = [];
const volList = document.getElementById('k8s-svc-vol-list-' + i);
if (volList) {
    volList.querySelectorAll('.k8s-vol-row').forEach(row => {
        const chkEl = row.querySelector('[id^="k8s-svc-vol-chk-"]');
        if (!chkEl || !chkEl.checked) return;  // skip unchecked
        const j = chkEl.id.split('-').pop();
        const type = _v('k8s-svc-vol-type-' + i + '-' + j) || 'pvc-dynamic';
        const mountPath = _v('k8s-svc-vol-mount-' + i + '-' + j);
        if (!mountPath) return;  // skip empty mount paths

        const vol = { type, mountPath };

        if (type === 'pvc-dynamic' || type === 'pvc-static') {
            vol.name = _v('k8s-svc-vol-name-' + i + '-' + j) || svcName + '-data-' + j;
            vol.size = _v('k8s-svc-vol-size-' + i + '-' + j) || '10Gi';
            vol.accessMode = _v('k8s-svc-vol-access-' + i + '-' + j) || 'ReadWriteOnce';
            if (type === 'pvc-static') {
                vol.pvName = _v('k8s-svc-vol-pvname-' + i + '-' + j) || '';
            }
        } else if (type === 'emptyDir') {
            vol.medium = _v('k8s-svc-vol-medium-' + i + '-' + j) || '';
            vol.sizeLimit = _v('k8s-svc-vol-sizelimit-' + i + '-' + j) || '';
        } else if (type === 'configMap') {
            vol.configMapName = _v('k8s-svc-vol-cmname-' + i + '-' + j) || '';
            vol.key = _v('k8s-svc-vol-cmkey-' + i + '-' + j) || '';
        } else if (type === 'secret') {
            vol.secretName = _v('k8s-svc-vol-secname-' + i + '-' + j) || '';
            vol.key = _v('k8s-svc-vol-seckey-' + i + '-' + j) || '';
        } else if (type === 'hostPath') {
            vol.hostPath = _v('k8s-svc-vol-hostpath-' + i + '-' + j) || '';
            vol.hostType = _v('k8s-svc-vol-hosttype-' + i + '-' + j) || 'DirectoryOrCreate';
        }

        svc.volumes.push(vol);
    });
}

// StorageClass (shared for all PVCs of this service)
svc.storageClass = _v('k8s-svc-storageclass-' + i) || '';

// Longhorn-specific (if applicable)
const scVal = svc.storageClass.toLowerCase();
if (scVal.includes('longhorn')) {
    svc.longhornConfig = {
        replicas: _v('k8s-svc-vol-lh-replicas-' + i) || '3',
        dataLocality: _v('k8s-svc-vol-lh-locality-' + i) || 'best-effort',
    };
}
```

---

## 7. WHAT GETS GENERATED (Backend — per volume type)

### PVC (dynamic):
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data
  namespace: default
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: longhorn        # omitted if empty (uses cluster default)
  resources:
    requests:
      storage: 10Gi
```

### PVC (dynamic, Longhorn):
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data
  namespace: default
  annotations:
    numberOfReplicas: "3"
    dataLocality: "best-effort"
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: longhorn
  resources:
    requests:
      storage: 10Gi
```

### PV + PVC (static):
```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: postgres-data-pv
spec:
  capacity:
    storage: 10Gi
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Retain
  # Backend-specific source would go here
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data
  namespace: default
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 10Gi
  volumeName: postgres-data-pv    # bind to specific PV
```

### Deployment pod spec (volume references):
```yaml
spec:
  containers:
    - name: api
      volumeMounts:
        - name: postgres-data
          mountPath: /var/lib/postgresql/data
        - name: app-config
          mountPath: /etc/app/config.yaml
          subPath: config.yaml
  volumes:
    - name: postgres-data
      persistentVolumeClaim:
        claimName: postgres-data
    - name: app-config
      configMap:
        name: api-config
    - name: cache
      emptyDir: {}
    - name: tls-certs
      secret:
        secretName: api-tls
```

---

## 8. VALIDATION

- If PVC: size must be valid K8s quantity (regex: `/^\d+(\.\d+)?(Ki|Mi|Gi|Ti|Pi|Ei)?$/`)
- If PVC: name must be valid DNS subdomain (`/^[a-z0-9][a-z0-9-]*[a-z0-9]$/`)
- Mount path must start with `/`
- No duplicate mount paths within same service
- No duplicate PVC names across all services
- If PVC (static): PV name required
- If configMap/secret mount: resource name required
- If hostPath: path required, show warning about security

---

## 9. REVIEW STEP

```
💾 PVC: postgres-data     10Gi ReadWriteOnce (longhorn)     [create]
💾 PVC: api-data           5Gi ReadWriteOnce (longhorn)     [create]
📂 emptyDir: cache        /tmp/cache (ephemeral)            [inline]
📄 ConfigMap mount: nginx  /etc/nginx/nginx.conf            [ref]
```

---

## 10. IMPLEMENTATION ORDER

1. **Backend**: Add `k8s_storage_classes()` to `k8s_ops.py` + route in `routes_k8s.py`
2. **Classify function**: Add `_classifyVolume()` to the wizard script
3. **StorageClass dropdown**: Render at top of volume panel, async populate from API
4. **Volume rows**: Render per-compose-volume with classification, checkbox, type select
5. **Type-specific sub-fields**: Conditional panels for PVC/emptyDir/configMap/secret/hostPath
6. **Longhorn extras**: Detect `longhorn` in StorageClass, show replica/locality config
7. **Add volume button**: Dynamic row addition (same pattern as env vars)
8. **collect()**: Read all volume fields into `svc.volumes[]`
9. **validate()**: Format + uniqueness checks
10. **Review**: Volume summary rows

---

## 11. DEPENDENCIES & CROSS-CONCERNS

- **PVC names must be unique** across all app services AND infra services
- **Infra service volumes** (2A StatefulSet) will use the same StorageClass + PVC model
  - When we implement 2A, infra volumes reuse this same UI pattern
- **ConfigMap/Secret file mounts** are separate from env var injection (1D)
  - env vars: `envFrom` → bulk key-value injection
  - file mounts: `volumeMount` → mount as file at specific path
- **StorageClass detection** is a new backend API call — needs cluster connection
  - Fallback: text input if cluster not connected
