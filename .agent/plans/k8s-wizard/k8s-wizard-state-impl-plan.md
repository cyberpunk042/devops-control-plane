# K8s Wizard State — Implementation Plan

> **Prerequisite**: Read `k8s-wizard-state-analysis.md` for the full field-level proof.
> **Principle**: The state IS the creation payload. One shape, three uses.
> **Rule**: No exceptions. Every complication identified in the analysis is solved here.

---

## Change Sequence

Six phases, strictly ordered. Each phase is self-contained and testable.

---

## Phase 1: Backend Endpoints

**File**: `src/ui/web/routes_k8s.py`

Three endpoints, following existing patterns in routes_k8s.py (the jsonify + try/catch 
pattern used by `k8s_generate_wizard`, `k8s_storage_classes`, etc.).

### 1A. GET /k8s/wizard-state

```
Read <project_root>/k8s/.wizard-state.json
Return JSON contents if found, {ok: false, reason: "not_found"} if not.
```

- Use `_project_root()` helper (already exists, used by other routes)
- Read the file, `json.loads()`, return via `jsonify()`
- If file doesn't exist → `{ok: false, reason: "not_found"}`
- If file is malformed → `{ok: false, reason: "invalid"}`

### 1B. POST /k8s/wizard-state

```
Receive the full state shape in request body.
Strip non-state fields (_compose, _appSvcCount, _infraSvcCount, etc).
Write to <project_root>/k8s/.wizard-state.json
Return {ok: true}
```

- Create `k8s/` dir if needed (`mkdir(exist_ok=True)`)
- Strip fields: `_compose`, `_appSvcCount`, `_infraSvcCount`, `_configMode`, 
  `_appServices`, `_infraServices`, `_classifiedModules`, backward-compat flat fields
  (`app_name`, `image`, `port`, `replicas`, `service_type`)
- Also strip `_compose` from each item in `_services[]` and `_infraDecisions[]`
- Add metadata: `_savedAt` (ISO timestamp), `_version` (schema version, start at `1`)
- Write with `json.dump(data, f, indent=2)`
- Return `{ok: true, path: "k8s/.wizard-state.json"}`

### 1C. DELETE /k8s/wizard-state

```
Delete the file if it exists.
Return {ok: true}
```

- If file exists → delete it, return `{ok: true}`
- If not → return `{ok: true, message: "already absent"}`

---

## Phase 2: Collector Completeness Fixes

**File**: `src/ui/web/templates/scripts/_integrations_setup_modals.html`

Fix the gaps in the `collect()` function so the state shape is complete.

### 2A. Add `dependencies` to app service collection

**Location**: compose collector (line ~5984) — inside the `svcObj` construction.

After `companions: _collectCompanionData(i)`, add:

```js
// Collect dependency checkboxes (infra services this app depends on)
const depEls = document.querySelectorAll('.k8s-dep-' + i + ':checked');
const dependencies = [];
depEls.forEach(el => dependencies.push(el.value));
svcObj.dependencies = dependencies;
```

Repeat for the modules collector (line ~6157).

### 2B. Ensure VCT saved state has checked status

**Location**: VCT collector (line ~6060) — currently skips unchecked VCTs.

The current behavior is correct (unchecked = user removed it). No change needed.
The saved state only contains VCTs the user kept. ✅

### 2C. Verify _collectVolumes captures all type-specific fields

**Location**: `_collectVolumes` function (~line 3778).

Verify these fields are ALL collected per volume type:
- `pvc-dynamic`/`pvc-static`: size, accessMode, storageClass, longhornReplicas, longhornBackup
- `emptyDir`: medium, sizeLimit
- `configMap`: cmKeys (the keys input)
- `secret`: secretName, secretKeys
- `hostPath`: hostPathType

If any are missing from the current collector, add them. This ensures round-trip fidelity.

> **Action**: View `_collectVolumes` (lines 3778-3830) and verify each field is collected.

---

## Phase 3: Volume Adapter

**File**: `src/ui/web/templates/scripts/_integrations_setup_modals.html`

### 3A. Create `_savedVolToClassification(vol)` adapter function

**Location**: Near `_classifyVolume` (line ~3485), add a sibling function.

```js
// Convert a saved wizard-state volume into a classification object
// that _volRowHtml can consume with full fidelity
window._savedVolToClassification = (vol) => ({
    // Core fields (same names in both shapes)
    type:           vol.type || 'pvc-dynamic',
    name:           vol.name || '',
    mountPath:      vol.mountPath || '',
    readOnly:       vol.readOnly || false,
    // Mapped fields
    source:         '',                    // not used for saved data
    defaultSize:    vol.size || '10Gi',
    classification: 'saved',              // flag: came from saved state
    skipReason:     null,
    // Pass-through for _volRowHtml to use as defaults
    _savedAccessMode:       vol.accessMode || 'ReadWriteOnce',
    _savedStorageClass:     vol.storageClass || '',
    _savedLonghornReplicas: vol.longhornReplicas || '3',
    _savedLonghornBackup:   vol.longhornBackup || false,
    _savedMedium:           vol.medium || '',
    _savedSizeLimit:        vol.sizeLimit || '',
    _savedCmKeys:           vol.cmKeys || '',
    _savedSecretName:       vol.secretName || '',
    _savedSecretKeys:       vol.secretKeys || '',
    _savedHostPathType:     vol.hostPathType || '',
});
```

### 3B. Enhance `_volRowHtml` to use saved values

**Location**: `_volRowHtml` function (~lines 3528-3660)

For each input that currently uses a hardcoded default, check if `cl._savedXxx` exists:

| Current hardcoded | Replace with |
|---|---|
| `value="10Gi"` (size) | `value="${cl.defaultSize \|\| '10Gi'}"` — already works via `defaultSize` ✅ |
| AccessMode select default `ReadWriteOnce` | Check `cl._savedAccessMode` for `selected` attribute |
| StorageClass select default `''` | Check `cl._savedStorageClass` — set value after render or add `selected` |
| Longhorn replicas `value="3"` | Use `cl._savedLonghornReplicas \|\| '3'` |
| Longhorn backup checkbox unchecked | Use `cl._savedLonghornBackup ? 'checked' : ''` |
| emptyDir medium select default `''` | Check `cl._savedMedium` for selected |
| emptyDir sizeLimit `value=""` | Use `cl._savedSizeLimit \|\| ''` |
| ConfigMap keys input `value=""` | Use `cl._savedCmKeys \|\| ''` |
| Secret name input `value=""` | Use `cl._savedSecretName \|\| ''` |
| Secret keys input `value=""` | Use `cl._savedSecretKeys \|\| ''` |
| hostPath type select default `''` | Check `cl._savedHostPathType` for selected |

The changes are small — each is adding `cl._savedXxx ||` before the existing default.

Also: the checkbox `k8s-svc-vol-chk-${i}-${j}` — saved volumes are always checked 
(they were in the state because they were checked when collected). Add `checked` always
when rendering from saved state (`cl.classification === 'saved'` → force checked).

---

## Phase 4: Renderer Intake Logic

**File**: `src/ui/web/templates/scripts/_integrations_setup_modals.html`

This is the core change. The Configure step's `render(el, data)` function needs to:
1. Accept saved state
2. Look up saved values per service
3. Use them as defaults instead of detection-derived values

### 4A. Load state on modal open

**Location**: The modal open handler — specifically where `wizDetect` is fetched 
(line ~2944, inside the K8s wizard's detect step or config step initialization).

At the top of the Configure step's render function, before building HTML:

```js
// Load saved wizard state (if available)
const savedState = data._wizardState || null;
```

The state gets attached to `data._wizardState` during modal init (see Phase 5B).

### 4B. Per-service lookup helper

At the top of the render function, after savedState:

```js
// Lookup helpers for saved state
const _savedSvc = (name) => 
    savedState?._services?.find(s => s.name === name) || null;
const _savedInfra = (name) => 
    savedState?._infraDecisions?.find(d => d.name === name) || null;
```

### 4C. App service card intake — compose mode

**Location**: Inside the `for (let i = 0; i < appSvcs.length; i++)` loop (line ~4355)

At the top of each iteration:
```js
const saved = _savedSvc(svc.name);
```

Then every field uses the pattern: `saved?.field ?? detectionDefault`

Specific changes:

**Kind select** (line ~4398):
```
// Currently: svc._kindDefault === 'Deployment' ? ' selected' : ''
// Change to: (saved?.kind || svc._kindDefault) === 'Deployment' ? ' selected' : ''
```
Apply same pattern to all kind options.

**Image** (line ~4417):
```
// Currently: _inp(`k8s-svc-img-${i}`, imgStr, ...)
// Change to: _inp(`k8s-svc-img-${i}`, saved?.image || imgStr, ...)
```

**Port** (line ~4418):
```
// Currently: _num(`k8s-svc-port-${i}`, portVal)
// Change to: _num(`k8s-svc-port-${i}`, saved?.port || portVal)
```

**Replicas** (line ~4419):
```
// Currently: _num(`k8s-svc-replicas-${i}`, dp && dp.replicas ? dp.replicas : 2)
// Change to: _num(`k8s-svc-replicas-${i}`, saved?.replicas || (dp && dp.replicas ? dp.replicas : 2))
```

**Service Type** (line ~4420):
```
// Currently: 'ClusterIP' default
// Change to: Use saved?.serviceType for selected attribute
```

**Strategy** (line ~4435):
```
// Change defaultStrategy calculation:
const defaultStrategy = saved?.strategy || (hasNamedVols ? 'Recreate' : 'RollingUpdate');
```

**Max Surge/Unavailable** (lines ~4442-4447):
```
_inp(`k8s-svc-maxsurge-${i}`, saved?.maxSurge || '1', '1')
_inp(`k8s-svc-maxunavail-${i}`, saved?.maxUnavailable || '1', '1')
```

**Job fields** (lines ~4463-4478):
```
_inp(`k8s-svc-job-cmd-${i}`, saved?.command || '', ...)
_inp(`k8s-svc-job-args-${i}`, saved?.args || '', ...)
// ... same pattern for all 8 fields
```

**CronJob fields** (lines ~4489-4506):
```
_inp(`k8s-svc-cron-schedule-${i}`, saved?.schedule || '*/5 * * * *', ...)
// ... same pattern for all 6 fields
```

**DaemonSet fields** (lines ~4521-4569):
```
// Strategy select: use saved?.strategy
// MaxUnavail: use saved?.maxUnavailable
// NodeSelector: use saved?.nodeSelector
// Tolerations checkboxes: derive from saved?.tolerations array
const savedTols = saved?.tolerations || [];
const hasCpTol = savedTols.some(t => t.key === 'node-role.kubernetes.io/control-plane');
const hasNsTol = savedTols.some(t => !t.key && t.operator === 'Exists' && t.effect === 'NoSchedule');
// Use hasCpTol/hasNsTol for checked attribute
// Host access: saved?.hostNetwork, saved?.hostPID, saved?.hostIPC
```

**StatefulSet fields** (lines ~4580-4616):
```
_inp(`k8s-svc-ss-headless-${i}`, saved?.headlessServiceName || `${svc.name}-headless`, ...)
// podManagementPolicy select: use saved?.podManagementPolicy
// alsoCreateClusterIP checkbox: use saved?.alsoCreateClusterIP
// strategy select: use saved?.strategy
// partition: use saved?.partition
```

**StatefulSet VCTs** (lines ~4627-4647):
```
// If saved state exists, render VCTs from saved.volumeClaimTemplates instead of compose vols
const vctSource = saved?.volumeClaimTemplates || namedVols.map(cl => ({
    name: cl.name, mountPath: cl.mountPath, size: '10Gi',
    accessMode: 'ReadWriteOnce', storageClass: ''
}));
// Render VCT rows from vctSource
```

**Resource limits** (lines ~4669-4674):
```
_inp(`k8s-svc-cpu-req-${i}`, saved?.resources?.cpu_request || compCpuReq, '100m')
_inp(`k8s-svc-cpu-lim-${i}`, saved?.resources?.cpu_limit || compCpuLim, '500m')
_inp(`k8s-svc-mem-req-${i}`, saved?.resources?.memory_request || compMemReq, '128Mi')
_inp(`k8s-svc-mem-lim-${i}`, saved?.resources?.memory_limit || compMemLim, '256Mi')
```

**Probes** (lines ~4700-4713):
```
// If saved state has probes, use saved values instead of compose healthcheck parse
const rdyProbe = saved?.readinessProbe;
const livProbe = saved?.livenessProbe;
if (rdyProbe) {
    // Use _probeBlock with saved values
    _probeBlock(`k8s-svc-rdy-${i}`, 'Readiness Probe',
        rdyProbe.type, rdyProbe.path || '', rdyProbe.port || 8080, rdyProbe.command || '',
        rdyProbe.initialDelaySeconds, rdyProbe.periodSeconds, rdyProbe.extra, 'Timeout (s)')
} else {
    // Use existing compose healthcheck parse (current logic)
}
// Same for liveness
```

BUT: `_probeBlock` also sets the enabled checkbox to `checked` by default. If saved state 
has `readinessProbe: null`, we need the checkbox UNCHECKED. Currently `_probeBlock` always 
renders it checked. 

**Fix**: Add an optional `enabled` parameter to `_probeBlock`:
```js
const _probeBlock = (prefix, label, type, path, port, cmd, delay, period, extra, extraLabel, enabled = true) => {
    // Change: checked="${enabled ? 'checked' : ''}"
};
```

Then:
```js
_probeBlock(..., rdyProbe != null)  // enabled = true if probe exists in saved state
```

When there's NO saved state: behavior unchanged (enabled=true, same as current).
When saved state has probe: enabled=true, values from saved.
When saved state has null probe: enabled=false.

**Env vars** (lines ~4741-4745):
```
// If saved state, render from saved.envVars instead of compose environment
const envSource = saved?.envVars || Object.entries(envVals).map(([k, v]) => ({
    key: k, value: v || '', type: _defaultInjType(k),
    varName: _defaultInjType(k) !== 'hardcoded' ? '${' + k + '}' : ''
}));
envSource.forEach((ev, j) => {
    html += _envRowHtml(i, j, ev.key, ev.value, ev.type, ev.varName, i);
});
```

**Volumes** (lines ~4787-4794):
```
// If saved state, render from saved.volumes using adapter
if (saved?.volumes) {
    html += saved.volumes.map((vol, j) => {
        const cl = window._savedVolToClassification(vol);
        return window._volRowHtml(i, j, cl);
    }).join('');
} else {
    // Existing: compose vols → _classifyVolume → _volRowHtml
    html += vols.map((v, j) => {
        const cl = window._classifyVolume(v);
        return window._volRowHtml(i, j, cl);
    }).join('');
}
```

**Dependencies** (lines ~4810-4816):
```
// If saved state, use saved.dependencies for checked state
const savedDeps = saved?.dependencies || svc.depends_on || [];
const checked = savedDeps.includes(inf.name) ? ' checked' : '';
```

**Service mesh** (lines ~4888-4935):
```
// Mesh enable checkbox:
const meshEnabled = saved?.mesh ? true : false;
// checked="${meshEnabled ? 'checked' : ''}"

// Mesh provider select: use saved?.mesh?.provider for selected
// Mesh resource inputs: use saved?.mesh?.proxyCpuRequest || '100m', etc.
// Mesh cfg div visibility: use meshEnabled ? 'block' : 'none'
// Advanced fields: use saved?.mesh?.excludeInbound, etc.
```

### 4D. App service card intake — modules mode (lines ~4959-5021)

Same pattern as compose mode but simpler (fewer detection-derived defaults).
Apply `saved?.field || moduleDefault` for image, port, replicas, serviceType, kind.

### 4E. Infrastructure card intake (lines ~5047-5183)

Inside `_k8sInfraCardHtml(svc)`:

```js
const savedInfra = _savedInfra(svc.name);  // need to make _savedInfra accessible
```

**Kind select**: `savedInfra?.kind || infraKindDefault`  
**Provider notes**: `savedInfra?.providerNotes || ''`  
**Env vars**: Same pattern as app env vars — use `savedInfra?.envVars` if available  
**Volumes**: Same pattern — use `savedInfra?.volumes` with `_savedVolToClassification` adapter

**Challenge**: `_k8sInfraCardHtml` is defined inside `render()` but needs access to 
`_savedInfra` helper. Solution: make the lookup function a parameter or closure variable 
(it already has closure access since it's defined inside render).

### 4F. Global settings intake (lines ~5213-5247)

```
// Namespace
{ name: 'k8s-namespace', value: savedState?.namespace || data.namespace || defaultNamespace, ... }

// Output dir
{ name: 'k8s-output-dir', value: savedState?.output_dir || 'k8s/', ... }

// Ingress checkbox
{ name: 'k8s-ingress', value: savedState?.ingress ?? false, ... }

// Skaffold checkbox
// Change: checked="${(savedState?.skaffold ?? true) ? 'checked' : ''}"
```

---

## Phase 5: Post-Render Restoration

**Location**: The `setTimeout(() => { ... }, 0)` block (line ~5418) that already runs 
after DOM render.

### 5A. Restore init containers

```js
if (savedState) {
    savedState._services.forEach(savedSvc => {
        // Find the index of this service in appSvcs
        const i = appSvcs.findIndex(s => s.name === savedSvc.name);
        if (i < 0) return;
        
        // Init containers
        (savedSvc.initContainers || []).forEach((ic, j) => {
            const list = document.getElementById('k8s-svc-init-list-' + i);
            if (!list) return;
            const wrapper = document.createElement('div');
            wrapper.innerHTML = window._k8sInitRowHtml(i, j, ic.name, ic.image, ic.command);
            list.appendChild(wrapper.firstElementChild);
        });
        window._k8sUpdateInitCount(i);
    });
}
```

### 5B. Restore sidecars

Same pattern:
```js
(savedSvc.sidecars || []).forEach((sc, j) => {
    const list = document.getElementById('k8s-svc-sc-list-' + i);
    if (!list) return;
    const wrapper = document.createElement('div');
    wrapper.innerHTML = window._k8sSidecarRowHtml(
        i, j, sc.name, sc.image, sc.command, 
        sc.nativeSidecar, sc.sharedVolume, sc.sharedMount
    );
    list.appendChild(wrapper.firstElementChild);
});
window._k8sUpdateScCount(i);
```

### 5C. Restore mesh checkbox state

```js
if (savedSvc.mesh) {
    const meshChk = document.getElementById('k8s-svc-mesh-enable-' + i);
    if (meshChk) {
        meshChk.checked = true;
        const meshCfg = document.getElementById('k8s-svc-mesh-cfg-' + i);
        if (meshCfg) meshCfg.style.display = 'block';
    }
}
```

Note: The mesh INPUT values are already set during HTML render (Phase 4C), 
this only handles the checkbox + visibility toggle that can't be done in static HTML.

### 5D. Restore probe checkboxes

```js
// If saved state says no readiness probe, uncheck it
if (saved && !saved.readinessProbe) {
    const rdyChk = document.getElementById('k8s-svc-rdy-' + i + '-enable');
    if (rdyChk) rdyChk.checked = false;
}
if (saved && !saved.livenessProbe) {
    const livChk = document.getElementById('k8s-svc-liv-' + i + '-enable');
    if (livChk) livChk.checked = false;
}
```

### 5E. Restore companions (MOST COMPLEX)

This runs AFTER all cards are rendered and kind panels are synced.

```js
if (savedState) {
    savedState._services.forEach(savedSvc => {
        const targetIdx = appSvcs.findIndex(s => s.name === savedSvc.name);
        if (targetIdx < 0) return;
        
        (savedSvc.companions || []).forEach(comp => {
            // Find source index by companion name
            const sourceIdx = appSvcs.findIndex(s => s.name === comp.name);
            if (sourceIdx < 0) return;  // source service no longer in detection
            
            // Build companion object matching _k8sMoveIntoPod's format
            const companion = {
                sourceIndex: sourceIdx,
                svcName:     comp.name,
                image:       comp.image,
                port:        comp.port,
                envVars:     comp.env || [],
                resources:   comp.resources,
                volumes:     comp.volumes || [],
            };
            
            // Track the companion
            if (!window._k8sCompanions.has(targetIdx)) {
                window._k8sCompanions.set(targetIdx, []);
            }
            window._k8sCompanions.get(targetIdx).push(companion);
            
            // Hide the source card
            const srcCard = document.getElementById('k8s-svc-card-' + sourceIdx);
            if (srcCard) srcCard.style.display = 'none';
            
            // Show companion section in target
            const compSec = document.getElementById('k8s-svc-companions-' + targetIdx);
            if (compSec) compSec.style.display = 'block';
            
            // Render companion row
            const compList = document.getElementById('k8s-svc-companion-list-' + targetIdx);
            if (compList) {
                const wrapper = document.createElement('div');
                wrapper.innerHTML = window._k8sCompanionRowHtml(targetIdx, companion);
                compList.appendChild(wrapper.firstElementChild);
            }
            
            // Set dependency dropdown value
            if (comp.dependsOn) {
                const depVal = comp.dependsOnPort 
                    ? comp.dependsOn + ':' + comp.dependsOnPort 
                    : comp.dependsOn;
                const depSel = document.getElementById(
                    'k8s-comp-dep-' + targetIdx + '-' + sourceIdx
                );
                if (depSel) depSel.value = depVal;
            }
            
            // Register in svcNames
            window._k8sSvcNames['comp-' + targetIdx + '-' + sourceIdx] = 
                comp.name + ' (companion)';
        });
    });
    
    // Refresh move-to dropdowns after all companions are restored
    window._k8sRefreshMoveToDropdowns();
}
```

### 5F. Restore dependency checkboxes

```js
if (savedState) {
    savedState._services.forEach(savedSvc => {
        const i = appSvcs.findIndex(s => s.name === savedSvc.name);
        if (i < 0) return;
        (savedSvc.dependencies || []).forEach(depName => {
            const depChk = document.querySelector(
                '.k8s-dep-' + i + '[value="' + depName + '"]'
            );
            if (depChk) depChk.checked = true;
        });
        // Trigger env select refresh to reflect restored dependencies
        window._refreshEnvSelects(i);
    });
}
```

---

## Phase 6: State Persistence Triggers

### 6A. Load state on K8s wizard modal open

**Location**: Where the K8s wizard modal initializes — the point where `wizDetect` is 
fetched and `data` object is constructed for the Configure step.

Before the Configure step renders:
```js
// Fetch saved wizard state alongside detection
let savedWizState = null;
try {
    const stateRes = await api('/k8s/wizard-state');
    if (stateRes && stateRes.ok !== false) {
        savedWizState = stateRes;
    }
} catch (e) { /* no saved state — fresh start */ }

data._wizardState = savedWizState;
```

This makes the saved state available to the Configure step's render function.

### 6B. Save state at Finish step

**Location**: The Review & Apply step's "apply" action — inside the `onLeave` or the 
submit handler where `setup_k8s` is called.

BEFORE calling the manifest generation endpoint:
```js
// Persist wizard state
const stateToSave = {
    namespace: data.namespace,
    output_dir: data.output_dir,
    ingress: data.ingress,
    skaffold: data.skaffold,
    _services: data._services.map(svc => {
        const { _compose, ...rest } = svc;
        return rest;
    }),
    _infraDecisions: data._infraDecisions.map(inf => {
        const { _compose, ...rest } = inf;
        return rest;
    }),
};

try {
    await api('/k8s/wizard-state', {
        method: 'POST',
        body: JSON.stringify(stateToSave),
    });
} catch (e) {
    console.warn('Failed to save wizard state:', e);
    // Non-blocking — don't prevent manifest generation
}
```

### 6C. Add "Rescan" button behavior

**Location**: Configure step UI — inside global settings or as a top-level action.

"Rescan" clears the detection cache and re-fetches, but does NOT wipe saved state.
The next render will merge: fresh detection (new services discovered) + saved state 
(user's previous decisions).

This already works with our lookup-by-name model:
- New service not in saved state → detection defaults (fresh card)
- Saved service still in detection → saved values (restored card)
- Saved service GONE from detection → silently skipped (user notice TBD)

### 6D. Add "Wipe Config" action (future)

A button in the wizard UI:
```js
await api('/k8s/wizard-state', { method: 'DELETE' });
// Clear data._wizardState
data._wizardState = null;
// Re-render configure step to reset all fields to detection defaults
```

---

## Execution Order for Coding

| # | Phase | Scope | Risk |
|---|-------|-------|------|
| 1 | Backend endpoints | `routes_k8s.py` | Low — isolated, no existing code touched |
| 2 | Collector fixes | `_integrations_setup_modals.html` (collector) | Low — additive |
| 3 | Volume adapter | `_integrations_setup_modals.html` (helpers) | Medium — touches _volRowHtml |
| 4 | Renderer intake | `_integrations_setup_modals.html` (render) | High — many fields, must not break detection-only flow |
| 5 | Post-render restore | `_integrations_setup_modals.html` (setTimeout) | Medium — complex companion logic |
| 6 | Save/Load triggers | `_integrations_setup_modals.html` (modal init + finish) | Low — wiring |

**Critical invariant**: When `savedState` is `null` (no saved file), ALL behavior must be 
IDENTICAL to current. Every `saved?.field ?? existingDefault` falls through to the existing 
default. This is the safety net — we never break the "fresh wizard" flow.

---

## Files Changed

| File | Changes |
|------|---------|
| `src/ui/web/routes_k8s.py` | +3 endpoints (~60 lines) |
| `src/ui/web/templates/scripts/_integrations_setup_modals.html` | Collector fixes, volume adapter, renderer intake, post-render restore, save/load triggers |

Total: **2 files**. No new files needed (besides this plan).

---

## Testing Strategy

1. **Fresh wizard (no state file)**: Verify behavior is 100% identical to current
2. **Save → Close → Reopen**: Verify all fields restored
3. **Save → Add new compose service → Reopen**: New service has detection defaults, 
   existing services have saved values
4. **Save → Remove compose service → Reopen**: Removed service silently skipped
5. **Save → Rescan → Verify**: Detection refreshed, saved values preserved
6. **Wipe → Reopen**: All fields back to detection defaults
7. **Companion round-trip**: Save with companions, reopen, verify cards hidden/shown correctly
8. **All workload kinds**: Test save/load for Deployment, StatefulSet, DaemonSet, Job, CronJob
