# K8s Wizard — 2. Workload Types — Chunked Implementation Order

## STATUS: ✅ All 12 Chunks DONE

## RULE: Before each chunk, re-read the knowledge doc + UI spec,
##       re-analyse what exists, then plan the specific changes.

---

## The Chunks

Each chunk is one session's work. Non-breaking. Additive.
Each builds on the previous but the wizard remains functional between chunks.

---

### ✅ Chunk 1: Kind Selector Dropdown — App Services (DONE)

**What:** Add a Kind dropdown to each app service card header.
Currently the card shows a hardcoded `<span>Deployment</span>` badge.
Replace it with a `<select>` dropdown offering:
Deployment (default), StatefulSet, DaemonSet, Job, CronJob, Skip.

**What it does NOT do yet:** The detail panel doesn't change when you switch.
The dropdown is there, it stores the value, collect() picks it up,
but the same Deployment fields show regardless. This is the foundation.

**Why first:** Everything else depends on the Kind value existing per service.
Non-breaking because Deployment is pre-selected and all existing fields still work.

**Scope:**
- Add `<select>` to app card header (replace the green "Deployment" badge)
- Add classification heuristic `_classifyWorkloadKind(svc)` to pre-select
- Add heuristic hint text below dropdown
- Update `collect()` to read from `k8s-wk-kind-{id}` instead of hardcoded `'Deployment'`
- Review step: show the selected kind icon instead of always 🚀

---

### ✅ Chunk 2: Kind Selector Dropdown — Infra Services (DONE)

**What:** Replace the infra card's 3-way radio (StatefulSet / Managed / Skip)
with the same Kind dropdown used for app services.
Options for infra: StatefulSet (default for DBs), Deployment, DaemonSet, Managed, Skip.

**Why second:** Unifies the card model. Both app and infra now have the same
Kind selector mechanism. Still non-breaking — StatefulSet-selected infra cards
still show just the env vars panel (same as today when StatefulSet radio was picked).

**Scope:**
- Replace radio buttons in `_k8sInfraCardHtml` with `<select>` dropdown
- Same classification heuristic picks StatefulSet for DBs, DaemonSet for agents
- Update infra `collect()` to read kind from dropdown
- Review step: show kind-appropriate icon for infra too

---

### ✅ Chunk 3: Container Grouping — "Move to Pod" Mechanism (DONE)

**What:** Add the ability to merge a compose service INTO another workload's
pod as an extra container (sidecar/companion).

Each workload card gets a small action: `[⤵ Move into another pod...]`
Clicking it shows a dropdown of other workload names.
Selecting one REMOVES this card from the list and ADDS it as a
"companion container" row inside the target card.

The target card shows a new section:
```
── Companion Containers (from compose) ──
📦 nginx (from compose service)         [⤴ Split back to own workload]
   Image: [nginx:alpine]  Port: [:80]
```

The "Split back" button reverses it — pulls the container out and
re-creates it as its own workload card.

**Why now:** This is the user's key insight — compose services can be
bundled into the same pod. This must exist BEFORE the kind-specific
panels, because it changes what "a workload card" contains.

**Scope:**
- Add `[⤵ Move into pod...]` dropdown to each workload card header
- When triggered: remove card from list, add as companion in target card
- Companion container row: shows image + port + `[⤴ Split back]` button
- Split back: re-creates original card, removes from companion list
- Companions inherit the target's Kind (they're in the same pod)
- collect(): companions are collected as extra `containers[]` entries
- Review: show companions inline under the workload

**Key decisions:**
- A companion is NOT a sidecar (it's a full app container from compose)
- A companion is NOT an init container (it runs for pod lifetime)
- Companions go into `spec.containers[]` alongside the main container
- Each companion keeps its own image, port, env vars, resources
- The "main" container is the original card's container

---

### ✅ Chunk 4: Kind-Conditional Detail Panel — Job & CronJob (DONE)

**What:** When Kind = Job or CronJob, re-render the detail panel with
job-specific fields and HIDE deployment-specific fields.

This is the first "panel swap" — switching to Job hides:
replicas, service type, strategy, probes, volumes, dependencies.
And shows: command, backoff, completions, parallelism, timeout, restartPolicy.

CronJob adds: schedule, concurrency policy, history limits, suspend.

**Why now:** Job/CronJob is the most visually different from Deployment
(most fields disappear, new fields appear). It proves the conditional
rendering mechanism works. And it's self-contained — no volume model fork.

**Scope:**
- `_renderWorkloadDetail(id, kind)` function that destroys/rebuilds detail HTML
- Job panel: command, args, restartPolicy, backoff, completions, parallelism,
  timeout, TTL. Resources + env vars stay. No probes, no replicas, no strategy.
- CronJob panel: schedule (with human-readable preview) + concurrency Policy +
  history limits + suspend + inner job settings (backoff, timeout, restart).
- Wire Kind dropdown `onchange` to call `_renderWorkloadDetail()`
- collect(): kind-aware field reading
- validate(): kind-aware (schedule required for CronJob, command required for Job)

---

### ✅ Chunk 5: Kind-Conditional Detail Panel — DaemonSet (DONE)

**What:** When Kind = DaemonSet, show DaemonSet-specific fields.

Hides: replicas, service type, maxSurge.
Shows: node selector, tolerations (control-plane, NoSchedule presets),
host access (hostNetwork, hostPID, hostIPC), update strategy (Rolling/OnDelete).

**Scope:**
- DaemonSet detail panel in `_renderWorkloadDetail()`
- Node selector input (comma-separated key=value)
- Toleration presets (checkboxes) + custom add
- Host access checkboxes
- Strategy: RollingUpdate (maxUnavailable only) or OnDelete
- collect(): DaemonSet-specific fields
- validate(): DaemonSet-specific

---

### ✅ Chunk 6: Kind-Conditional Detail Panel — StatefulSet (DONE)

**What:** When Kind = StatefulSet, show StatefulSet-specific fields.

The BIG one: volume handling forks here.
Hides: service type selector, maxSurge.
Shows: headless service name (auto), also-create-ClusterIP checkbox,
pod management policy, partition, and the **volumeClaimTemplates** section
(INSTEAD of the regular Volume Mounts section).

**Scope:**
- StatefulSet detail panel in `_renderWorkloadDetail()`
- Headless service name auto-generated (`{name}-headless`)
- Also create ClusterIP checkbox
- Pod management policy select (OrderedReady / Parallel)
- Strategy: RollingUpdate (with partition) or OnDelete
- **volumeClaimTemplates** section (replaces Volume Mounts):
  - Name, mountPath, size, accessMode, storageClass
  - Hint: "One PVC per pod: data-{name}-0, data-{name}-1, …"
- collect(): StatefulSet-specific (volumeClaimTemplates array)
- This is the most complex chunk — the volume model fork

---

### ✅ Chunk 7: Managed & Skip Panels (DONE)

**What:** When Kind = Managed, show provider notes + connection env vars.
When Kind = Skip, show empty/grayed state.

**Scope:**
- Managed panel: provider text input + connection env var rows
- Connection vars get cross-referenced into dependent services' Secrets
- Skip panel: disabled state, maybe gray overlay
- collect(): Managed = connection vars, Skip = excluded entirely

---

### ✅ Chunk 8: Init Containers Section (DONE)

**What:** Add the Init Containers collapsible section to all workload cards
(all kinds except Managed/Skip).

**Scope:**
- `<details>` section: "▸ Init Containers (N)"
- Preset buttons: Wait for TCP, Wait for HTTP, Run migrations, Fix permissions, Custom
- Each init container: name, image, command, resources, env vars
- Presets auto-fill image + command template (with placeholders)
- Dynamic add/remove
- collect(): `initContainers[]` array per workload
- Review: show init containers with ⏳ icon

---

### ✅ Chunk 9: Sidecar Containers Section (DONE)

**What:** Add the Sidecar Containers collapsible section.
This is for CUSTOM sidecars (not compose companions from Chunk 3).

**Scope:**
- `<details>` section: "▸ Sidecar Containers (N)"
- Preset buttons: Log forwarder, Config reloader, Metrics exporter,
  Auth proxy, Cloud SQL Proxy, Vault agent, Custom
- Each sidecar: name, image, command, resources, env, ports
- Native sidecar checkbox (K8s ≥ 1.28): initContainers + restartPolicy: Always
- Auto-generated shared emptyDir volume for presets that need it
- collect(): `sidecars[]` array per workload
- Review: show sidecars with 📎 icon

---

### ✅ Chunk 10: Service Mesh Section (DONE)

**What:** Add generalized service mesh section (Istio/Linkerd/Consul/Kuma).

**Scope:**
- `<details>` section: "▸ Service Mesh (Istio)"
- Enable checkbox → reveals resource inputs
- Proxy CPU/Memory request + limit inputs
- Advanced: exclude inbound/outbound ports, log level
- Warning when kind = Job/CronJob + Istio enabled
- collect(): `istio` object per workload
- Generated output: pod template annotations only (NOT containers)
- Review: show 🔷 Istio line

---

### ✅ Chunk 11: Backend — Kind-Aware Manifest Generation (DONE)

**What:** Update the backend's `generate_k8s_wizard` to produce correct
manifests for each workload kind.

**Scope:**
- StatefulSet template: volumeClaimTemplates, headless Service, serviceName
- DaemonSet template: no replicas, nodeSelector, tolerations
- Job template: backoffLimit, completions, restartPolicy, no Service
- CronJob template: schedule, jobTemplate wrapper
- Multi-container pod spec: initContainers[], sidecars in correct slot
- Istio: inject annotations into pod template metadata
- Shared emptyDir volumes for sidecars
- Companion containers in containers[] array

---

### ✅ Chunk 12: Rich Companion Containers (DONE)

**What:** When a service is "Moved into pod", the companion row currently
only captures name/image/port. A real companion still needs env vars,
resource limits, and shared volumes. We need a rich companion card with
editable config, and the collect() logic to gather it all.

**Problem:** Right now `_k8sMoveIntoPod()` only reads 3 fields from the
source card. Everything else (env vars, resources, volumes) is lost when
the source card is hidden. The companion row is a flat one-liner with no
configurability.

**Scope:**

#### 12a — Extract full state at move time
In `_k8sMoveIntoPod(sourceIdx, targetIdx)`:
- Read the source card's env vars from `k8s-svc-env-list-{sourceIdx}`
  (iterate `.env-row` children → key, value, injection type)
- Read resource limits from `k8s-svc-res-*-{sourceIdx}` inputs
- Read volumes from `k8s-svc-vol-list-{sourceIdx}` rows
- Store all of this in the `_k8sCompanions` tracking Map entry alongside
  the existing `{sourceIndex, svcName, image, port}`

#### 12b — `_k8sCompanionRowHtml()` function
Create a new helper function (same pattern as `_k8sInitRowHtml`,
`_k8sSidecarRowHtml`) that returns a collapsible companion card:
```
📦 service-name  [image:tag]  :8080        [⤴ Split back]
  ▸ Environment Variables (3)
     key = value   [ConfigMap ▼]
     key = value   [Secret ▼]
  ▸ Resource Limits
     CPU Req [___]  CPU Lim [___]  Mem Req [___]  Mem Lim [___]
  ▸ Volumes (2)
     /data → named-vol   /config → configmap-vol
```
- DOM IDs: `k8s-comp-{targetIdx}-{sourceIdx}-*` pattern
- Env rows reuse the existing `_envRowHtml()` function with a
  `comp-{targetIdx}-{sourceIdx}` prefix
- Resource inputs: 4 fields
- Volume list: read-only display of what was inherited (optional: editable)

#### 12c — Update `_k8sMoveIntoPod` to render rich rows
Replace the simple `row.innerHTML = ...` block with a call to
`_k8sCompanionRowHtml(targetIdx, companion)` which generates the full
UI using the extracted data from 12a.

#### 12d — Update `collect()` to gather companion data
In both collect paths (compose + modules), change the companions mapping:
```javascript
companions: (window._k8sCompanions.get(i) || []).map(c => ({
    name: c.svcName,
    image: c.image,
    port: c.port,
    // NEW:
    env: _readCompanionEnv(i, c.sourceIndex),
    resources: _readCompanionResources(i, c.sourceIndex),
    volumes: _readCompanionVolumes(i, c.sourceIndex),
})),
```

#### 12e — Backend already handles companion env/port
`_build_pod_template()` already processes `comp.env` and `comp.port`.
Just need to add `comp.resources` → `container.resources` and
`comp.volumes` → volume mounts.

**Key constraint:** Font sizes ≥ 0.72rem for all text. Buttons ≥ 0.74rem.

---

## Dependency Graph

```
Chunk 1 (Kind dropdown - app)
  ↓
Chunk 2 (Kind dropdown - infra)
  ↓
Chunk 3 (Container grouping) ← can also be done after Chunk 4
  ↓
Chunk 4 (Job/CronJob panel)
  ↓
Chunk 5 (DaemonSet panel)
  ↓
Chunk 6 (StatefulSet panel)  ← hardest, volume fork
  ↓
Chunk 7 (Managed/Skip panels)
  ↓
Chunk 8 (Init Containers)  ← independent, could be earlier
  ↓
Chunk 9 (Sidecars)  ← independent, could be earlier
  ↓
Chunk 10 (Istio)  ← independent, could be earlier
  ↓
Chunk 11 (Backend generation)  ← depends on all above
  ↓
Chunk 12 (Rich Companions)  ← depends on 3 + 11
```

Chunks 8, 9, 10 are independent of each other and of 4-7.
They can be interleaved. The dependency is:
- 1 → 2 (both add Kind dropdown)
- 1+2 → 4,5,6,7 (kind-conditional panels need the dropdown)
- 4,5,6,7 → 11 (backend needs all panel data to generate)
- 8,9,10 → 11 (backend needs init/sidecar/istio data too)

---

## Session Protocol

Before starting each chunk:
1. Re-read the knowledge doc (k8s-wizard-2-workloads.md)
2. Re-read the UI spec (k8s-wizard-2-workloads-UI.md)
3. Re-read THIS chunk list
4. Look at what currently exists in the code (what changed since last chunk)
5. Plan the specific lines/functions to change
6. Implement
7. Mark chunk as done in this file
