# K8s Wizard State — Field-Level Analysis

> **Goal**: Prove that the `onLeave` collector's output shape can serve as intake
> for every renderer field, identify all shape mismatches, and document the
> lookup strategy per section.

---

## 1. The Canonical State Shape

The `collect()` function (lines 5841–6237) produces this shape. This same shape is:
- **Saved** to `k8s/.wizard-state.json` at the Finish step
- **Loaded** on modal open to pre-populate the Configure step
- **Sent** to the backend for manifest generation

```
{
  namespace:   string,           // from k8s-namespace input
  output_dir:  string,           // from k8s-output-dir input
  ingress:     string,           // from k8s-ingress checkbox
  skaffold:    boolean,          // from k8s-skaffold-toggle checkbox
  _configMode: 'compose' | 'modules' | 'manual',

  _services: [                   // app services (Section A)
    {
      name:       string,        // service name (from compose or module)
      kind:       string,        // Deployment|StatefulSet|DaemonSet|Job|CronJob
      image:      string,
      envVars:    EnvVar[],
      resources:  Resources | null,
      companions: Companion[],

      // Kind-specific — see §3 below
      ...kindFields
    }
  ],

  _infraDecisions: [             // infrastructure services (Section B)
    {
      name:          string,
      kind:          string,     // StatefulSet|Deployment|DaemonSet|Managed|Skip
      image:         string,
      port:          string,
      envVars:       EnvVar[],
      volumes:       Volume[],   // when kind !== 'Managed'
      providerNotes: string,     // when kind === 'Managed'
    }
  ],
}
```

### Sub-shapes

```
EnvVar = {
  key:           string,
  value:         string,
  type:          'hardcoded' | 'variable' | 'secret',
  varName:       string,         // e.g. '${DB_HOST}'
  createInVault: boolean,
  newValue:      string,         // only when createInVault
}

Resources = {
  cpu_request:    string | null,
  cpu_limit:      string | null,
  memory_request: string | null,
  memory_limit:   string | null,
}

Volume = {
  type:       string,   // 'pvc-dynamic'|'pvc-static'|'emptyDir'|'configMap'|'secret'|'hostPath'
  mountPath:  string,
  name:       string,
  size:       string,
  accessMode: string,
  storageClass: string,
  readOnly:   boolean,
  // Type-specific:
  longhornReplicas: string,   // when type=pvc-dynamic + storageClass=longhorn
  longhornBackup:   boolean,
  medium:           string,   // when type=emptyDir ('Memory' or '')
  sizeLimit:        string,   // when type=emptyDir
  cmKeys:           string,   // when type=configMap
  secretName:       string,   // when type=secret
  secretKeys:       string,   // when type=secret
  hostPathType:     string,   // when type=hostPath
}

VolumeClaimTemplate = {
  name:         string,
  mountPath:    string,
  size:         string,
  accessMode:   string,
  storageClass: string,
}

Probe = {
  type:                string,   // 'http'|'tcp'|'exec'
  initialDelaySeconds: number,
  periodSeconds:       number,
  // Type-specific:
  path:    string,   // http
  port:    number,   // http|tcp
  command: string,   // exec
  extra:   number,   // timeout or failure threshold
} | null

InitContainer = {
  name:    string,
  image:   string,
  command: string,
}

Sidecar = {
  name:          string,
  image:         string,
  command:       string,
  nativeSidecar: boolean,
  sharedVolume:  string | undefined,
  sharedMount:   string | undefined,
}

Mesh = {
  provider:         string,  // 'istio'|'linkerd'|'consul'|'kuma'
  proxyCpuRequest:  string,
  proxyCpuLimit:    string,
  proxyMemRequest:  string,
  proxyMemLimit:    string,
  excludeInbound:   string,
  excludeOutbound:  string,
  logLevel:         string,
} | undefined

Companion = {
  name:           string,
  image:          string,
  port:           string,
  env:            EnvVar[],
  resources:      Resources | null,
  volumes:        Volume[],   // own + host pod
  dependsOn:      string | null,
  dependsOnPort:  string | null,
}
```

---

## 2. Section-by-Section Field Mapping

### 2.1 Global Settings (Section C — lines 5208–5247)

| DOM ID | Renderer Default | Saved State Field | Lookup |
|--------|-----------------|-------------------|--------|
| `k8s-namespace` | `data.namespace \|\| defaultNamespace` | `state.namespace` | ✅ Direct |
| `k8s-output-dir` | `'k8s/'` | `state.output_dir` | ✅ Direct |
| `k8s-ingress` | `false` (checkbox) | `state.ingress` | ✅ Direct |
| `k8s-skaffold-toggle` | `true` (checked) | `state.skaffold` | ✅ Direct |

**Verdict**: Clean mapping. No complications.

---

### 2.2 Application Service Cards (Section A — lines 4350–4957)

For each app service `i` with compose data `svc = appSvcs[i]`:

**Lookup key**: `const saved = state._services.find(s => s.name === svc.name)`

#### 2.2.1 Card Header (line 4384–4413)

| DOM ID | Renderer Default | Saved State Field | Lookup |
|--------|-----------------|-------------------|--------|
| `k8s-svc-chk-${i}` | `checked` (always) | If `saved` exists → checked; if not → depends on detection | ⚠️ Implicit |
| `k8s-svc-kind-${i}` | `_classifyWorkloadKind(svc)` | `saved.kind` | ✅ Direct — need to set `selected` on the right `<option>` |
| `k8s-svc-icon-${i}` | `_kindIcon(svc._kindDefault)` | Derived from `saved.kind` | ✅ Derived |
| `k8s-svc-kind-hint-${i}` | `_kindHint(...)` | Clear it (hint is detection-only) | ✅ Clear |
| Card visibility (`display`) | `block` (or `none` if Skip) | If `saved` exists as companion → `none` | ⚠️ Companion handling |

**Complication — Companion cards**: If `saved` is listed as a `companion` of another service, the card must be hidden and a companion row rendered inside the target. This requires **cross-referencing** the saved state:
```
for each svc in state._services:
  for each comp in svc.companions:
    hide card for comp.name
    render companion row inside svc's card
```

#### 2.2.2 Primary Settings Row (lines 4416–4425)

| DOM ID | Renderer Default | Saved State Field | Lookup |
|--------|-----------------|-------------------|--------|
| `k8s-svc-img-${i}` | `svc._image \|\| ghcr.io/...` | `saved.image` | ✅ Direct |
| `k8s-svc-port-${i}` | `svc._port \|\| 8080` | `saved.port` | ✅ Direct |
| `k8s-svc-replicas-${i}` | `dp.replicas \|\| 2` | `saved.replicas` | ✅ Direct |
| `k8s-svc-type-${i}` | `'ClusterIP'` | `saved.serviceType` | ✅ Direct |

**Verdict**: Clean mapping.

#### 2.2.3 Update Strategy — Deployment (lines 4428–4456)

| DOM ID | Renderer Default | Saved State Field | Lookup |
|--------|-----------------|-------------------|--------|
| `k8s-svc-strategy-${i}` | `hasNamedVols ? 'Recreate' : 'RollingUpdate'` | `saved.strategy` | ✅ Direct |
| `k8s-svc-maxsurge-${i}` | `'1'` | `saved.maxSurge` | ✅ Direct |
| `k8s-svc-maxunavail-${i}` | `'1'` | `saved.maxUnavailable` | ✅ Direct |
| Rolling div visibility | Based on `defaultStrategy` | Based on `saved.strategy === 'RollingUpdate'` | ✅ Derived |

**Verdict**: Clean mapping.

#### 2.2.4 Job Configuration (lines 4458–4481)

| DOM ID | Renderer Default | Saved State Field | Lookup |
|--------|-----------------|-------------------|--------|
| `k8s-svc-job-cmd-${i}` | `''` | `saved.command` | ✅ Direct |
| `k8s-svc-job-args-${i}` | `''` | `saved.args` | ✅ Direct |
| `k8s-svc-job-restart-${i}` | `'Never'` | `saved.restartPolicy` | ✅ Direct |
| `k8s-svc-job-backoff-${i}` | `3` | `saved.backoffLimit` | ✅ Direct |
| `k8s-svc-job-completions-${i}` | `1` | `saved.completions` | ✅ Direct |
| `k8s-svc-job-parallelism-${i}` | `1` | `saved.parallelism` | ✅ Direct |
| `k8s-svc-job-timeout-${i}` | `600` | `saved.activeDeadlineSeconds` | ✅ Direct |
| `k8s-svc-job-ttl-${i}` | `3600` | `saved.ttlSecondsAfterFinished` | ✅ Direct |

**Verdict**: Clean mapping.

#### 2.2.5 CronJob Configuration (lines 4483–4510)

| DOM ID | Renderer Default | Saved State Field | Lookup |
|--------|-----------------|-------------------|--------|
| `k8s-svc-cron-schedule-${i}` | `'*/5 * * * *'` | `saved.schedule` | ✅ Direct |
| `k8s-svc-cron-concurrency-${i}` | `'Forbid'` | `saved.concurrencyPolicy` | ✅ Direct |
| `k8s-svc-cron-suspend-${i}` | `false` | `saved.suspend` | ✅ Direct |
| `k8s-svc-cron-success-${i}` | `3` | `saved.successfulJobsHistoryLimit` | ✅ Direct |
| `k8s-svc-cron-failed-${i}` | `1` | `saved.failedJobsHistoryLimit` | ✅ Direct |
| `k8s-svc-cron-deadline-${i}` | `300` | `saved.startingDeadlineSeconds` | ✅ Direct |

**Verdict**: Clean mapping.

#### 2.2.6 DaemonSet Configuration (lines 4512–4572)

| DOM ID | Renderer Default | Saved State Field | Lookup |
|--------|-----------------|-------------------|--------|
| `k8s-svc-ds-strategy-${i}` | `'RollingUpdate'` | `saved.strategy` | ✅ Direct |
| `k8s-svc-ds-maxunavail-${i}` | `'1'` | `saved.maxUnavailable` | ✅ Direct |
| `k8s-svc-ds-nodeselector-${i}` | `''` | `saved.nodeSelector` | ✅ Direct |
| `k8s-svc-ds-tol-cp-${i}` | `false` | `saved.tolerations.some(t => t.key === 'node-role.kubernetes.io/control-plane')` | ⚠️ Derived lookup |
| `k8s-svc-ds-tol-nosched-${i}` | `false` | `saved.tolerations.some(t => t.operator === 'Exists' && t.effect === 'NoSchedule' && !t.key)` | ⚠️ Derived lookup |
| `k8s-svc-ds-hostnet-${i}` | `false` | `saved.hostNetwork` | ✅ Direct |
| `k8s-svc-ds-hostpid-${i}` | `false` | `saved.hostPID` | ✅ Direct |
| `k8s-svc-ds-hostipc-${i}` | `false` | `saved.hostIPC` | ✅ Direct |

**Complication — Tolerations**: The renderer has two checkboxes, but the collector produces an array of toleration objects. The intake needs to reverse-map: check the array for the specific toleration signature to set each checkbox.
- Control-plane: `{key:'node-role.kubernetes.io/control-plane', effect:'NoSchedule', operator:'Exists'}`
- NoSchedule: `{key:'', operator:'Exists', effect:'NoSchedule'}`

This is a slight shape mismatch but trivially resolvable with two `Array.some()` checks.

#### 2.2.7 StatefulSet Configuration (lines 4574–4652)

| DOM ID | Renderer Default | Saved State Field | Lookup |
|--------|-----------------|-------------------|--------|
| `k8s-svc-ss-headless-${i}` | `${svc.name}-headless` | `saved.headlessServiceName` | ✅ Direct |
| `k8s-svc-ss-podmgmt-${i}` | `'OrderedReady'` | `saved.podManagementPolicy` | ✅ Direct |
| `k8s-svc-ss-clusterip-${i}` | `false` | `saved.alsoCreateClusterIP` | ✅ Direct |
| `k8s-svc-ss-strategy-${i}` | `'RollingUpdate'` | `saved.strategy` | ✅ Direct |
| `k8s-svc-ss-partition-${i}` | `0` | `saved.partition` | ✅ Direct |
| VCT rows | From compose named vols via `_classifyVolume` | `saved.volumeClaimTemplates[]` | ⚠️ Shape difference |

**Complication — VCTs**: The renderer generates VCT rows from compose volume classifications (`cl.name`, `cl.mountPath`). The saved state has `{name, mountPath, size, accessMode, storageClass}` which is a superset. The intake needs to render VCTs from the saved array directly instead of from compose classifications:
```
// Instead of: namedVols.map(cl => ...) 
// Use: saved.volumeClaimTemplates.map(vct => ...)
```
Fields map 1:1 to the VCT row inputs. ✅ Resolvable.

#### 2.2.8 Resource Limits (lines 4654–4684)

| DOM ID | Renderer Default | Saved State Field | Lookup |
|--------|-----------------|-------------------|--------|
| `k8s-svc-cpu-req-${i}` | `dp.cpu_request \|\| ''` | `saved.resources?.cpu_request` | ✅ Direct |
| `k8s-svc-cpu-lim-${i}` | `dp.cpu_limit \|\| ''` | `saved.resources?.cpu_limit` | ✅ Direct |
| `k8s-svc-mem-req-${i}` | `dp.memory_request \|\| ''` | `saved.resources?.memory_request` | ✅ Direct |
| `k8s-svc-mem-lim-${i}` | `dp.memory_limit \|\| ''` | `saved.resources?.memory_limit` | ✅ Direct |

**Verdict**: Clean mapping.

#### 2.2.9 Health Checks (lines 4686–4721)

| DOM ID | Renderer Default | Saved State Field | Lookup |
|--------|-----------------|-------------------|--------|
| `k8s-svc-rdy-${i}-enable` | `true` if compose hc, else `true` | `!!saved.readinessProbe` | ✅ Direct |
| `k8s-svc-rdy-${i}-type` | From compose hc parse | `saved.readinessProbe?.type` | ✅ Direct |
| `k8s-svc-rdy-${i}-path` | From compose hc parse | `saved.readinessProbe?.path` | ✅ Direct |
| `k8s-svc-rdy-${i}-port` | From compose hc parse | `saved.readinessProbe?.port` | ✅ Direct |
| `k8s-svc-rdy-${i}-cmd` | From compose hc parse | `saved.readinessProbe?.command` | ✅ Direct |
| `k8s-svc-rdy-${i}-delay` | `5` | `saved.readinessProbe?.initialDelaySeconds` | ✅ Direct |
| `k8s-svc-rdy-${i}-period` | From compose hc interval | `saved.readinessProbe?.periodSeconds` | ✅ Direct |
| `k8s-svc-rdy-${i}-extra` | From compose hc timeout/retries | `saved.readinessProbe?.extra` | ✅ Direct |
| Same pattern for `liv-${i}-*` | Same | `saved.livenessProbe` | ✅ Direct |

**Complication**: The `_probeBlock` function generates the HTML with these fields baked in. The probe data from saved state maps 1:1 to the arguments of `_probeBlock(prefix, label, type, path, port, cmd, delay, period, extra, extraLabel)`. ✅ Clean.

#### 2.2.10 Environment Variables (lines 4723–4769)

| Aspect | Renderer Source | Saved State Field | Lookup |
|--------|----------------|-------------------|--------|
| Env row list | `Object.entries(svc.environment).map(([k,v],j) => _envRowHtml(i,j,k,v,...))` | `saved.envVars[]` | ⚠️ Shape needs mapping |

**Current renderer** iterates compose `environment` dict:
```js
Object.entries(envVals).map(([k, v], j) => {
    const injType = _defaultInjType(k);  // heuristic
    return _envRowHtml(i, j, k, v || '', injType, injType !== 'hardcoded' ? '${' + k + '}' : '', i);
})
```

**Saved state** has:
```
envVars: [{key, value, type, varName, createInVault, newValue}, ...]
```

**Mapping**: `_envRowHtml(i, j, ev.key, ev.value, ev.type, ev.varName, i)` — maps perfectly.

The difference: saved state preserves the USER's chosen `type` (hardcoded/variable/secret) and `varName`, rather than re-deriving from heuristic `_defaultInjType(k)`. This is exactly what we want!

**Verdict**: ✅ Clean mapping. The `_envRowHtml` signature accepts exactly the fields the saved state contains.

#### 2.2.11 Volume Mounts (lines 4771–4803)

| Aspect | Renderer Source | Saved State Field | Lookup |
|--------|----------------|-------------------|--------|
| Volume row list | `svc.volumes.map(v => _classifyVolume(v)).map((cl, j) => _volRowHtml(i, j, cl))` | `saved.volumes[]` | ⚠️ Shape transform needed |

**Current renderer**: Takes compose volume strings (like `./data:/app/data`), classifies them via `_classifyVolume()` into:
```
{ type, name, mountPath, readOnly, source, defaultSize, classification, skipReason }
```

Then `_volRowHtml(i, j, cl)` renders from this classification.

**Saved state**: The `_collectVolumes(i)` function returns:
```
{ type, mountPath, name, size, accessMode, storageClass, readOnly, ... }
```

**⚠️ SHAPE MISMATCH**: The classification object and the collected volume object have **different field names**:
- Classification: `cl.type` (auto-detected) vs Saved: `vol.type` (user-selected) — same field ✅
- Classification: `cl.name` vs Saved: `vol.name` — same field ✅
- Classification: `cl.mountPath` vs Saved: `vol.mountPath` — same field ✅
- Classification: `cl.readOnly` vs Saved: `vol.readOnly` — same field ✅
- Classification: `cl.defaultSize` vs Saved: `vol.size` — **different name** ⚠️
- Classification: `cl.source` — not in saved state (compose raw string) — not needed ✅
- Classification: `cl.classification` — not in saved state (used for initial type guess) — not needed ✅
- Saved: `vol.accessMode`, `vol.storageClass`, `vol.longhornReplicas`, etc. — **not in classification** ⚠️

**Resolution**: Create a synthetic classification from saved volume data:
```js
const cl = {
    type:          vol.type,
    name:          vol.name,
    mountPath:     vol.mountPath,
    readOnly:      vol.readOnly,
    source:        '',    // not needed for rendering
    defaultSize:   vol.size,
    classification: 'saved',  // flag to skip re-classification
};
```

BUT — `_volRowHtml` also bakes in initial `value="..."` for the size/accessMode/storageClass fields using its own defaults. The saved state values need to be passed through to override these defaults. Looking at `_volRowHtml` (lines 3528-3660), the values for size, accessMode, and storageClass inputs are hardcoded:
- `value="10Gi"` for size
- Select with default `ReadWriteOnce` for accessMode  
- StorageClass select with default `''`

**Better approach**: Modify `_volRowHtml` to optionally accept a full saved volume object, OR create a wrapper function `_volRowHtmlFromState(svcId, j, savedVol)` that:
1. Builds the HTML like `_volRowHtml` does
2. Passes saved values for size, accessMode, storageClass, etc.

OR simpler: extend `_volRowHtml(i, j, cl)` to check if `cl` has the extra fields (`size`, `accessMode`, `storageClass`, `longhornReplicas`, `medium`, `sizeLimit`, `cmKeys`, `secretName`, etc.) and use those as defaults instead of hardcoded values.

**Verdict**: ⚠️ Requires `_volRowHtml` enhancement. The classification object needs to be a superset that carries saved values for all type-specific fields.

#### 2.2.12 Dependencies (lines 4805–4818)

| DOM ID | Renderer Default | Saved State Field | Lookup |
|--------|-----------------|-------------------|--------|
| `.k8s-dep-${i}` checkboxes | `svc.depends_on.includes(inf.name)` | Not directly saved ❌ | ⚠️ Missing |

**Complication**: The dependency checkboxes are render-only — they're not collected by `onLeave`! Looking at the collector, dependencies are NOT part of the service object for app services. They ARE collected for companions (`dependsOn`, `dependsOnPort`).

Wait — let me re-check. Looking at lines 5984-5996 for compose services, I see `_compose: appSvcs[i]` is saved, which contains `depends_on`. But `_compose` is compose detection data, not user config.

**Verdict**: Dependencies for app services are NOT persisted in the current state shape. They may not need to be — they're derived from compose `depends_on` and don't represent user edits. But if a user CHANGES a dependency checkbox, that change IS lost. This is a **semantic gap** but likely acceptable for v1 — dependencies are informational, and the actual init container wait-for logic is captured separately.

#### 2.2.13 Init Containers (lines 4820–4848)

| Aspect | Renderer Source | Saved State Field | Lookup |
|--------|----------------|-------------------|--------|
| Init container rows | Empty on render (no presets) | `saved.initContainers[]` | ⚠️ Post-render injection needed |

**Current renderer**: Renders an empty `k8s-svc-init-list-${i}` div. Init containers are added via preset buttons (`_k8sAddInitPreset`) which call `_k8sInitRowHtml(i, j, name, image, command)` and append to DOM.

**Saved state**: `saved.initContainers = [{name, image, command}, ...]`

**Intake strategy**: After the HTML is rendered, iterate `saved.initContainers` and call `_k8sInitRowHtml(i, j, ic.name, ic.image, ic.command)` for each, appending to the list div. Then update the count badge.

**Verdict**: ✅ Clean — but requires post-render DOM injection (same pattern as `_k8sAddInitPreset` already uses).

#### 2.2.14 Sidecar Containers (lines 4850–4880)

Same pattern as init containers.

| Aspect | Renderer Source | Saved State Field | Lookup |
|--------|----------------|-------------------|--------|
| Sidecar rows | Empty on render | `saved.sidecars[]` | ⚠️ Post-render injection needed |

**Intake**: After render, iterate `saved.sidecars` and call `_k8sSidecarRowHtml(i, j, sc.name, sc.image, sc.command, sc.nativeSidecar, sc.sharedVolume, sc.sharedMount)` for each.

**Verdict**: ✅ Clean — post-render DOM injection.

#### 2.2.15 Service Mesh (lines 4882–4937)

| DOM ID | Renderer Default | Saved State Field | Lookup |
|--------|-----------------|-------------------|--------|
| `k8s-svc-mesh-enable-${i}` | `false` | `!!saved.mesh` | ✅ Direct |
| `k8s-svc-mesh-provider-${i}` | `'istio'` | `saved.mesh?.provider` | ✅ Direct |
| `k8s-svc-mesh-cpureq-${i}` | `'100m'` | `saved.mesh?.proxyCpuRequest` | ✅ Direct |
| `k8s-svc-mesh-cpulim-${i}` | `'500m'` | `saved.mesh?.proxyCpuLimit` | ✅ Direct |
| `k8s-svc-mesh-memreq-${i}` | `'128Mi'` | `saved.mesh?.proxyMemRequest` | ✅ Direct |
| `k8s-svc-mesh-memlim-${i}` | `'256Mi'` | `saved.mesh?.proxyMemLimit` | ✅ Direct |
| `k8s-svc-mesh-exin-${i}` | `''` | `saved.mesh?.excludeInbound` | ✅ Direct |
| `k8s-svc-mesh-exout-${i}` | `''` | `saved.mesh?.excludeOutbound` | ✅ Direct |
| `k8s-svc-mesh-log-${i}` | `'warning'` | `saved.mesh?.logLevel` | ✅ Direct |
| `k8s-svc-mesh-cfg-${i}` visibility | `none` | `saved.mesh ? 'block' : 'none'` | ✅ Derived |

**Verdict**: Clean mapping.

#### 2.2.16 Companion Containers (lines 4939–4953)

| Aspect | Renderer Source | Saved State Field | Lookup |
|--------|----------------|-------------------|--------|
| Companion section | Hidden, empty | `saved.companions[]` | ⚠️ Complex post-render |

**Current flow**: Companions are created dynamically via `_k8sMoveIntoPod(sourceIdx, targetIdx)` which:
1. Reads state from source card
2. Hides source card
3. Renders companion row via `_k8sCompanionRowHtml(targetIdx, companion)`
4. Tracks in `window._k8sCompanions` Map

**Intake strategy**: After all cards render, for each service with companions:
1. For each `comp` in `saved.companions`:
   - Find the source card index (by matching `comp.name` against `svc.name` in the appSvcs array)
   - Build a companion object: `{sourceIndex, svcName: comp.name, image: comp.image, port: comp.port, envVars: comp.env, resources: comp.resources, volumes: comp.volumes}`
   - Hide the source card (`display: none`)
   - Render companion row via `_k8sCompanionRowHtml`
   - Append to `window._k8sCompanions` tracking
   - Set dependency dropdown value from `comp.dependsOn` + `comp.dependsOnPort`
2. Show the companion section div
3. Refresh move-to dropdowns

**Verdict**: ⚠️ Most complex intake, but the building blocks (`_k8sCompanionRowHtml`, `_k8sCompanions` Map) already exist. Needs orchestration logic.

---

### 2.3 Infrastructure Service Cards (Section B — lines 5043–5206)

For each infra service `svc = infraSvcs[i]`:

**Lookup key**: `const savedInfra = state._infraDecisions.find(d => d.name === svc.name)`

| DOM ID / Aspect | Renderer Default | Saved State Field | Lookup |
|--------|-----------------|-------------------|--------|
| `k8s-infra-kind-${name}` | `_classifyWorkloadKind(svc)` | `savedInfra.kind` | ✅ Direct |
| `k8s-infra-provider-${name}` | `''` | `savedInfra.providerNotes` | ✅ Direct |
| Env vars list | `Object.entries(svc.environment)` | `savedInfra.envVars[]` | ✅ Same as §2.2.10 |
| Volume rows | `svc.volumes.map(classifyVolume)` | `savedInfra.volumes[]` | ⚠️ Same as §2.2.11 |
| Skip/Managed visibility toggles | Based on `infraKindDefault` | Based on `savedInfra.kind` | ✅ Derived |

**Verdict**: Same patterns as app services. Volume shape mismatch applies here too.

---

## 3. Identified Complications

### 3.1 Volume Shape Transform (Severity: MEDIUM)
`_volRowHtml(i, j, cl)` expects a classification object with `defaultSize`, `source`, `classification`. Saved state has `size`, `accessMode`, `storageClass`, etc.

**Resolution**: Enhance `_volRowHtml` to accept optional override values OR create a `_savedVolToClassification(vol)` adapter:
```js
function _savedVolToClassification(vol) {
    return {
        type: vol.type, name: vol.name, mountPath: vol.mountPath,
        readOnly: vol.readOnly || false,
        source: '',  // not relevant for saved data
        defaultSize: vol.size || '10Gi',
        classification: 'saved',
        // Carry through all saved values for _volRowHtml to use:
        _savedAccessMode: vol.accessMode,
        _savedStorageClass: vol.storageClass,
        _savedLonghornReplicas: vol.longhornReplicas,
        _savedLonghornBackup: vol.longhornBackup,
        _savedMedium: vol.medium,
        _savedSizeLimit: vol.sizeLimit,
        _savedCmKeys: vol.cmKeys,
        _savedSecretName: vol.secretName,
        _savedSecretKeys: vol.secretKeys,
        _savedHostPathType: vol.hostPathType,
    };
}
```
Then `_volRowHtml` checks for `cl._savedAccessMode` etc. to use as defaults instead of hardcoded values.

### 3.2 Companion Restoration (Severity: MEDIUM)
Companions require cross-referencing saved state services, hiding source cards, rendering companion rows, and populating the tracking Map. The building blocks exist, but orchestration is needed.

### 3.3 DaemonSet Toleration Reverse-Map (Severity: LOW)
Two `Array.some()` checks — trivial.

### 3.4 Post-Render DOM Injection (Severity: LOW)
Init containers, sidecars, and mesh checkboxes need to be set after the HTML is rendered and inserted into the DOM. The existing `setTimeout(() => { ... }, 0)` block (line 5418) already does post-render work and is the right place for this.

### 3.5 Index Stability (Severity: LOW)
The renderer iterates `appSvcs` by index `i`, but DOM IDs are keyed by index. If compose services are reordered or one is removed between saves, index `i` for a name changes. The lookup by `name` handles this — the saved state for "redis" still maps to the card for "redis" regardless of what `i` it gets.

### 3.6 Dependencies Not In State (Severity: LOW)
App service dependency checkboxes are not collected. They come from compose `depends_on`. User changes to these are lost. Acceptable for v1 — the actual "wait-for" logic is in init containers which ARE saved.

### 3.7 The `_compose` Field (Severity: INFO)
The collector includes `_compose: appSvcs[i]` (the raw compose data). This should NOT be saved to state — it's detection data, not user config. On load, fresh detection provides this. The state file should strip `_compose` before saving.

---

## 4. Intake Flow Summary

```
1. Modal opens
2. Fetch detection:  wizDetect = await api('/wizard/detect')
3. Fetch state:      savedState = await api('/k8s/wizard-state')  // null if no file
4. Configure step render(el, data):
   a. Build appSvcs[], infraSvcs[] from detection (existing logic)
   b. For each app service card:
      - saved = savedState?._services?.find(s => s.name === svc.name)
      - Use saved.field for values, fall back to detection defaults
      - Render env rows from saved.envVars (not compose environment)
      - Render volume rows from saved.volumes (via adapter)
   c. Post-render (setTimeout):
      - Restore init containers from saved
      - Restore sidecars from saved
      - Restore mesh checkboxes from saved  
      - Restore companions (hide source cards, render companion rows)
      - Set probe checkbox states
      - Toggle kind panels
   d. For each infra service:
      - savedInfra = savedState?._infraDecisions?.find(d => d.name === name)
      - Use savedInfra.kind, envVars, volumes, providerNotes
   e. Globals:
      - namespace, output_dir, ingress, skaffold from savedState
```

---

## 5. Backend Endpoints Needed

### GET /k8s/wizard-state
- Read `<project_root>/k8s/.wizard-state.json`
- Return contents or `{ok: false}` if not found

### POST /k8s/wizard-state  
- Receive the state shape from the Finish step
- Strip `_compose` fields from services and infraDecisions
- Write to `<project_root>/k8s/.wizard-state.json`
- Return `{ok: true}`

### DELETE /k8s/wizard-state (future: "wipe state")
- Delete the file
- Return `{ok: true}`

---

## 6. What We Do NOT Save

- `_compose`: Raw compose service data (comes from fresh detection)
- `_appSvcCount`, `_infraSvcCount`, `_configMode`: Derivable from detection
- `_appServices`, `_infraServices`, `_classifiedModules`: Detection data
- Backward compat flat fields (`app_name`, `image`, `port`, `replicas`, `service_type`)
- Skaffold CLI status, StorageClass detection results
