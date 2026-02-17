# DevOps Control Plane — Integration Test Plan

> Generated: 2026-02-16
> Purpose: Complete map of every setup flow, integration chain, combo,
> order of execution, and setting variant. This drives the entire
> development of the platform. Work through it layer by layer.

---

## Dev Workflow — Per Checkbox

**Every checkbox follows this process. No skipping steps. No optimistic shortcuts.**

Revised after completing 0.1.1 Detection and 0.1.2 Generation (2026-02-16).

For each checkbox, do ALL **applicable** steps before confirming:

### Step 1 — TDD Test (always required)
- Does a **dedicated** test exist for this exact scenario?
- Is the test **pessimistic**? Pessimistic means:
  - Asserts on **every expected field/key/structure**, not just a substring check
  - Tests error paths, not just happy path
  - Uses exact values, not `.get()` with defaults that hide missing keys
  - Verifies the **full shape** of the output (metadata, content structure, edge cases)
- **Source of truth is the TECHNOLOGY SPEC + PROJECT SCOPE, not the current code.**
  Look at what the technology supports (docker-compose spec, Kubernetes API, Helm chart structure) and what the project scope requires. The TDD test defines the FULL target — the backend gets leveled up to meet it.
- **BEFORE writing the test:** enumerate EVERY assertion needed. No partial coverage.
- If the test is missing or optimistic → write/fix the test FIRST
- Run the test. If it's a new feature, it MUST fail (TDD red). If it's strengthening an existing feature, it should pass.

### Step 2 — Backend Service (always required)
- Trace the **full call chain**: generator function → wrapper/facade → route
- Does the function return the right keys for this scenario?
- Does it handle edge cases (empty, malformed, missing)?
- Does the return shape match what the test asserts?
- If the backend is broken or incomplete → fix it, re-run the test
- **If a new parameter is added** (e.g., `base_image`), trace it through EVERY layer: generator, wrapper (`docker_generate.py`), web route, CLI command

### Step 3 — UI Route (if applicable)
> Skip if the checkbox is purely about backend/generator logic and no new route or parameter is needed.

- Which route(s) expose this backend function?
- Does the route pass the right arguments (including new ones)?
- Does it pass through the full return dict, or does it drop/transform keys?
- Does it handle errors from the backend?
- If the route is missing or broken → fix it

### Step 4 — UI Template (if applicable)
> Skip if the checkbox is about backend logic and the existing template already renders the output correctly.

- Which template/JS consumes this route's response?
- Does the template handle this exact scenario?
- Are the response keys the template reads matching what the backend returns?
- If the template doesn't handle this case → fix it

### Step 5 — Confirm
- All applicable steps verified
- Test passes with pessimistic assertions
- Backend returns correct data
- No regressions
- Present **summary table** (Layer | Status | Detail) for user approval
- **Only then** → mark checkbox ✅ in this plan

### Rules
- **ONE checkbox at a time** — unless multiple checkboxes follow the **exact same pattern** (same test structure, same template structure, same assertion set). In that case, batching is allowed with user approval. Example: strengthening tests for Rust + Java + .NET + PHP + Ruby was a valid batch because all followed the identical 10-assertion pattern.
- **ONE FOCUS (subsection) at a time** — do NOT expand all subsections of a section at once. Expand the current focus subsection (e.g., 0.2.1 Detection), complete it fully, then move to the next. This applies to the PLAN itself, not just execution. The plan grows section by section, not all at once.
  - The plan for a subsection is derived from the **PRODUCT scope** — what the technology supports, what the project needs, what modes exist (e.g., single-env vs multi-env, Minikube vs cloud clusters, kubectl vs helm install for infra). **Not** just from existing code, which is always incomplete.
  - When expanding a subsection, discuss with the user first. The user will say if more depth is needed before moving on.
- If anything is missing at ANY step → it cannot be checked off
- The user confirms. If the user disagrees → restart the current checkbox
- No cheating, no hacks, no excuses, nothing is impossible
- **Take your time.** Speed is not the goal. Correctness is.

---

## Layer 0 — Single Domain Setup (each in isolation)

### 0.1 Docker

#### 0.1.1 Detection
- [x] Empty project → no Docker detected
- [x] Dockerfile present → detected, parsed (base image, stages, ports)
- [x] Dockerfile in subdirectory → detected
- [x] docker-compose.yml present → detected, services parsed
- [x] docker-compose.yaml (alt extension) → detected
- [x] Both Dockerfile and compose → both detected
- [x] .dockerignore present → detected
- [x] Malformed Dockerfile → detected with warnings
- [x] Malformed compose → detected with warnings

#### 0.1.2 Generation
- [x] Generate Dockerfile for Python project
- [x] Generate Dockerfile for Node project
- [x] Generate Dockerfile for Go project
- [x] Generate Dockerfile for C project
- [x] Generate Dockerfile for C++ project
- [x] Generate Dockerfile for Rust project
- [x] Generate Dockerfile for Java project
- [x] Generate Dockerfile for .NET project
- [x] Generate Dockerfile for PHP project
- [x] Generate Dockerfile for Ruby project
- [x] Generate Dockerfile with multi-stage build
- [x] Generate Dockerfile with custom base image
- [x] Generate docker-compose.yml for single service
- [x] Generate docker-compose.yml for multi-service (app + db)
- [x] Generate docker-compose.yml with volumes
- [x] Generate docker-compose.yml with networks
- [x] Generate docker-compose.yml with environment variables
- [x] Generate docker-compose.yml with port mappings
- [x] Generate docker-compose.yml with depends_on
- [x] Generate .dockerignore from project type
- [x] Overwrite existing Dockerfile (overwrite=True)
- [x] Skip existing Dockerfile (overwrite=False)

#### 0.1.3 Wizard Setup
- [x] `setup_docker()` with minimal data → Dockerfile created
- [x] `setup_docker()` with compose=True → docker-compose.yml created
- [x] `setup_docker()` with dockerignore=True → .dockerignore created
- [x] `setup_docker()` with registry=ghcr.io → registry stored in config
- [x] `setup_docker()` with registry=docker.io → registry stored
- [x] `setup_docker()` with custom registry → stored
- [x] `setup_docker()` with image name → stored
- [x] `setup_docker()` with build args → stored / passed to Dockerfile
- [x] `setup_docker()` round-trip: setup → detect → matches what was generated
- [x] `setup_docker()` idempotent: run twice → same result
- [x] `setup_docker()` overwrite: changes config on second run

#### 0.1.4 Settings Variants
- [x] Python + Flask
- [x] Python + FastAPI
- [x] Python + Django
- [x] Python + plain

- [x] Node + Express
- [x] Node + Next.js
- [x] Node + NestJS
- [x] Node + Fastify
- [x] Node + plain

- [x] Go + Gin
- [x] Go + Fiber
- [x] Go + Echo
- [x] Go + plain

- [x] Rust + Actix Web
- [x] Rust + Axum
- [x] Rust + Rocket
- [x] Rust + plain

- [x] Java + Spring Boot
- [x] Java + Quarkus
- [x] Java + Maven (plain)

- [x] .NET + ASP.NET Core
- [x] .NET + Minimal API

- [x] PHP + Laravel
- [x] Ruby + Rails

- [x] C++ + CMake
- [x] Python + Gunicorn (WSGI)
- [x] Python + Uvicorn (ASGI)
- [x] Python + Celery worker

- [x] Node + Hono
- [x] Node + Koa
- [x] Node + plain (TS)

- [x] Go + Chi
- [x] Go + Buffalo

- [x] Rust + Warp
- [x] Rust + Hyper

- [x] Java + Micronaut
- [x] Java + Gradle (plain)

- [x] .NET + Worker Service

- [x] PHP + Symfony

- [x] C + CMake

- [x] Multi-stage vs single-stage
- [x] With dev dependencies vs production-only
- [x] With health check vs without

#### 0.1.5 Error Cases
- [x] Unknown stack name → `generate_dockerfile` returns None
- [x] Empty modules → `generate_compose` returns error
- [x] Empty wizard services list → `generate_compose_from_wizard` returns error
- [x] Wizard service with no name → service silently skipped, rest generated
- [x] `write_generated_file` with missing path → returns error
- [x] `write_generated_file` with missing content → returns error
- [x] `write_generated_file` with path traversal (`../../../`) → rejected (security)
- [x] `setup_docker` with empty data dict → defaults applied, succeeds
- [x] `setup_docker` with non-dict build_args → no ARG lines, no crash
- [x] `generate_dockerignore` with unknown stacks → base patterns only
- [x] All-markdown modules → compose is stack-agnostic, still generates
- [x] `setup_docker` on read-only path → filesystem error surfaced cleanly

---

### 0.2 Kubernetes

> **Scope:** 10 backend modules (`k8s_common`, `k8s_detect`, `k8s_validate`,
> `k8s_generate`, `k8s_pod_builder`, `k8s_wizard`, `k8s_wizard_generate`,
> `k8s_wizard_detect`, `k8s_cluster`, `k8s_helm`), 6 unit test files,
> 3 integration test files. ~4,400+ existing test lines.

#### 0.2.1 Common — constants & low-level helpers (`k8s_common.py`)
- [x] `_SKIP_DIRS` excludes .git, .venv, node_modules, __pycache__, dist, build, etc.
- [x] `_K8S_API_VERSIONS` includes v1, apps/v1, batch/v1, networking.k8s.io/v1, autoscaling/v2, etc.
- [x] `_K8S_KINDS` includes all standard kinds (Pod, Deployment, StatefulSet, DaemonSet, Job, CronJob, Service, Ingress, ConfigMap, Secret, PVC, PV, Namespace, ServiceAccount, Role, ClusterRole, HPA, NetworkPolicy, etc.)
- [x] `_MANIFEST_DIRS` = [k8s, kubernetes, deploy, manifests, kube, charts]
- [x] `_run_kubectl` runs subprocess with timeout
- [x] `_kubectl_available` returns `{available, version}` when kubectl exists
- [x] `_kubectl_available` returns `{available: False}` when kubectl missing (FileNotFoundError)
- [x] `_kubectl_available` returns `{available: False}` on TimeoutExpired
- [x] `_parse_k8s_yaml` parses multi-document YAML, returns only dicts with `kind` + `apiVersion`
- [x] `_parse_k8s_yaml` returns `[]` on ImportError (no PyYAML)
- [x] `_parse_k8s_yaml` returns `[]` on OSError (file unreadable)
- [x] `_parse_k8s_yaml` returns `[]` on YAMLError (malformed)
- [x] `_parse_k8s_yaml` skips non-dict documents within multi-doc YAML

#### 0.2.2 Detection — offline scanning (`k8s_detect.py`)

##### `_collect_yaml_files`
- [ ] YAML files in k8s/ directory → collected
- [ ] YAML files in nested subdirectories of manifest dir → collected
- [ ] YAML files inside _SKIP_DIRS (.git, node_modules, etc.) → skipped
- [ ] No manifest dirs found → scans project root
- [ ] At most 50 YAML files returned (cap)
- [ ] Empty manifest dir → empty list
- [ ] Both `.yaml` and `.yml` extensions → collected

##### `_detect_helm_charts`
- [ ] Chart.yaml with name + version → detected with name, version, description
- [ ] Multiple Chart.yaml in different directories → all detected
- [ ] Chart.yaml inside _SKIP_DIRS → skipped
- [ ] Malformed Chart.yaml → still detected with name=unknown
- [ ] No Chart.yaml → empty list
- [ ] Nested chart (deploy/helm/myapp/Chart.yaml) → detected

##### `_detect_kustomize`
- [ ] kustomization.yaml at root → detected
- [ ] kustomization.yml at root → detected
- [ ] Kustomization (capitalized, no ext) at root → detected
- [ ] kustomization.yaml in k8s/ subdirectory → detected
- [ ] kustomization.yaml in kubernetes/ subdirectory → detected
- [ ] No kustomization file → `{exists: False}`

##### `k8s_status` (integration)
- [ ] Empty project → `has_k8s=False`, empty manifests/charts/kustomize
- [ ] Single deployment manifest → detected, resources parsed with kind/name/namespace/apiVersion
- [ ] Multi-document YAML (---) → all resources detected and counted
- [ ] Helm-only project (Chart.yaml, no raw manifests) → `has_k8s=True`
- [ ] Kustomize-only project → `has_k8s=True`
- [ ] kubectl availability included in result
- [ ] Non-K8s YAML (no kind/apiVersion) → not counted
- [ ] Multiple manifest dirs (k8s/ + deploy/) → both listed
- [ ] `resource_summary` counts kinds correctly (e.g., Deployment: 2, Service: 3)
- [ ] Manifest detail has path and resource list
- [ ] Manifests in manifests/ dir → detected
- [ ] Manifests in kubernetes/ dir → detected
- [ ] Files in .venv → skipped
- [ ] Files in node_modules → skipped

#### 0.2.3 Validation — structural + best-practice checks (`k8s_validate.py`)

##### Valid manifests
- [ ] Well-formed Deployment → `ok=True`, `errors=0`
- [ ] Well-formed Service → `ok=True`, `errors=0`
- [ ] Multi-document YAML with Deployment + Service → `files_checked >= 1`
- [ ] Empty project → `ok=True`, zero files, zero errors

##### Structural errors
- [ ] Missing `metadata.name` → error
- [ ] Deployment missing `spec.selector` → error
- [ ] Deployment with no containers → error
- [ ] Container without image → `:latest` implicit warning
- [ ] Unparseable YAML → should not crash (no error, file just skipped)

##### Best-practice warnings
- [ ] Deployment without resource limits → warning
- [ ] Image with `:latest` tag → warning
- [ ] Image without any tag → `:latest` implicit warning
- [ ] No `livenessProbe` → info-level issue
- [ ] No `readinessProbe` → info-level issue
- [ ] No `securityContext` → info-level issue
- [ ] Service without selector → warning
- [ ] Service without ports → warning
- [ ] Multi-port Service with unnamed ports → warning
- [ ] Unusual apiVersion (not in _K8S_API_VERSIONS) → warning

##### Deployment-specific
- [ ] Missing replicas → warning (defaults to 1)
- [ ] Missing strategy → info (defaults to RollingUpdate)

#### 0.2.4 Simple Generation — template-based (`k8s_generate.py`)
- [ ] `generate_manifests` produces Deployment + Service files
- [ ] Deployment content is valid YAML
- [ ] Service content is valid YAML
- [ ] Custom replicas reflected in Deployment
- [ ] Custom service_type (ClusterIP/NodePort/LoadBalancer) reflected in Service
- [ ] With namespace → Namespace manifest generated, placed first
- [ ] With host → Ingress manifest generated
- [ ] Without host → no Ingress
- [ ] Default image → `{app_name}:latest`
- [ ] Generated Deployment has resource limits (cpu/memory)
- [ ] Generated Deployment has livenessProbe + readinessProbe
- [ ] Generated Deployment has securityContext (runAsNonRoot, no privilege escalation)
- [ ] Generated Deployment has RollingUpdate strategy
- [ ] Generated files placed under k8s/ directory

#### 0.2.5 Pod Builder — shared across generators (`k8s_pod_builder.py`)

##### `_build_probe`
- [ ] HTTP probe with all timing fields (initialDelay, period, failureThreshold)
- [ ] TCP probe with port only
- [ ] Exec probe wraps command in `sh -c`
- [ ] Exec probe with no command → fallback to `/bin/true`
- [ ] HTTP probe with no args → defaults (path=/, port=8080)
- [ ] Timing values of 0 → omitted from output

##### `_build_wizard_volume`
- [ ] PVC-dynamic volume → persistentVolumeClaim with svc-prefixed claim
- [ ] EmptyDir with Memory medium and sizeLimit
- [ ] ConfigMap volume with key → subPath on mount
- [ ] Secret volume with key → subPath on mount
- [ ] HostPath volume with type
- [ ] No mountPath → returns (None, None)
- [ ] Unknown volume type → returns (None, None)
- [ ] PVC volume with no name → name derived from index
- [ ] ReadOnly flag → mount has readOnly=true

##### `_build_pod_template`
- [ ] Main container with image, ports, resources, probes, security context
- [ ] Init containers → `initContainers` field in pod spec
- [ ] Sidecar containers → additional containers in pod
- [ ] Companion containers → multiple containers in same pod
- [ ] Volumes from service config → `volumes` + `volumeMounts`
- [ ] Mesh annotations → pod template annotations
- [ ] Host access config → hostNetwork, hostPID fields
- [ ] VolumeClaimTemplates for StatefulSets

##### `_build_env_vars`
- [ ] Dict input → simple name/value pairs
- [ ] List with explicit `secretName` → `secretKeyRef`
- [ ] List with explicit `configMapName` → `configMapKeyRef`
- [ ] Wizard format `type=secret` + `svc_name` → `{svc}-secrets` reference
- [ ] Wizard format `type=variable` + `svc_name` → `{svc}-config` reference
- [ ] Wizard format `type=hardcoded` → inline value
- [ ] Empty/falsy input → empty list
- [ ] Items missing both `name` and `key` → skipped
- [ ] `key` field accepted as alias for `name`

##### `_build_mesh_annotations`
- [ ] Istio mesh → `sidecar.istio.io/inject: true`
- [ ] Linkerd mesh → `linkerd.io/inject: enabled`
- [ ] Consul mesh → `consul.hashicorp.com/connect-inject: true`
- [ ] Istio proxy resource annotations set
- [ ] No provider → empty annotations

##### `_api_version_for_kind`
- [ ] Deployment → apps/v1
- [ ] StatefulSet → apps/v1
- [ ] DaemonSet → apps/v1
- [ ] Job → batch/v1
- [ ] CronJob → batch/v1
- [ ] Ingress → networking.k8s.io/v1
- [ ] Service → v1
- [ ] Unknown kind → v1 (fallback)

#### 0.2.6 Wizard Translator (`k8s_wizard.py`)

##### `_svc_env_to_resources`
- [ ] Hardcoded env vars → ConfigMap resource
- [ ] Secret env vars → Secret resource with placeholder values
- [ ] Mix of hardcoded + secret → both ConfigMap and Secret
- [ ] Variable env vars → ConfigMap with varName as value
- [ ] Empty env vars → no resources

##### `_svc_volumes_to_pvc_resources`
- [ ] PVC-dynamic volume → PVC resource with storageClass and size
- [ ] PVC-static volume → PVC with volumeName
- [ ] PVC with storageClass preserved
- [ ] EmptyDir and non-PVC volumes → no PVC resources

##### `wizard_state_to_resources`
- [ ] Single app service → Deployment + Service resources
- [ ] Multiple services → all produce Deployment + Service
- [ ] Non-default namespace → Namespace resource created
- [ ] `namespace=default` → no Namespace resource
- [ ] Service with env vars → ConfigMap + Secret resources + envFrom wiring
- [ ] Service with probes → probes in resource spec
- [ ] Service with resource limits → limits in spec
- [ ] StatefulSet → headless Service + serviceName set
- [ ] Job with backoffLimit, completions, parallelism
- [ ] CronJob with schedule and concurrency policy
- [ ] Infra service `kind=Skip` → no resources
- [ ] Infra service `kind=Managed` → Managed placeholder resource
- [ ] Ingress host set → Ingress resource with backend
- [ ] Ingress with multiple services → multi-path rules
- [ ] No ingress host → no Ingress resource
- [ ] Every resource has namespace field set
- [ ] Custom output_dir propagated to all resources
- [ ] Deployment strategy forwarded to spec
- [ ] Infra services (isInfra=True) → own Deployment + Service
- [ ] Infra Postgres with PVC → PVC resource created
- [ ] Infra service kind override (e.g., StatefulSet)

##### `_sanitize_state`
- [ ] Transient/detection fields removed (_appServices, _infraServices, _classifiedModules, etc.)
- [ ] Sanitized state includes `_savedAt` and `_version`
- [ ] `_compose` key removed from each service

#### 0.2.7 Wizard Generation — resources → YAML files (`k8s_wizard_generate.py`)

##### `generate_k8s_wizard`
- [ ] Deployment resource → valid YAML with correct structure
- [ ] Service resource → correct port, selector, type
- [ ] ConfigMap resource → data keys preserved
- [ ] Secret resource → stringData, type Opaque
- [ ] Ingress resource → rules with host and path
- [ ] PVC resource → access modes, storage, storageClass
- [ ] Namespace resource → no namespace in metadata
- [ ] Empty resource list → error
- [ ] Managed kind → no manifest file produced (skipped)
- [ ] Output dir reflected in file paths
- [ ] Deployment strategy in generated YAML
- [ ] Multiple resources → multiple file entries
- [ ] StatefulSet → valid YAML with correct apiVersion (apps/v1)
- [ ] DaemonSet → valid YAML, no replicas field
- [ ] CronJob → YAML includes schedule field
- [ ] HPA → valid YAML with autoscaling apiVersion

##### `_generate_skaffold`
- [ ] Skaffold disabled → None
- [ ] Skaffold enabled → valid skaffold.yaml content
- [ ] Skaffold rawYaml includes all generated manifest paths

#### 0.2.8 Wizard State Persistence
- [ ] `save_wizard_state` + `load_wizard_state` round-trip
- [ ] `load_wizard_state` on nonexistent file → `{ok: False, reason: "not_found"}`
- [ ] `wipe_wizard_state` removes state file
- [ ] `save_wizard_state` creates k8s/ dir if it doesn't exist
- [ ] `load_wizard_state` on corrupt JSON → graceful error, not crash
- [ ] Sanitization strips transient fields on save
- [ ] Core fields preserved through save/load cycle

#### 0.2.9 Skaffold Detection (`k8s_wizard_detect.py`)
- [ ] Empty project → `has_skaffold=False`, `configs=[]`
- [ ] skaffold.yaml present → detected with path
- [ ] skaffold.yml present → detected
- [ ] Both skaffold.yaml and skaffold.yml → both detected
- [ ] Profiles section → profile names extracted
- [ ] Profile entries without name → skipped
- [ ] No profiles section → empty profiles list
- [ ] Malformed YAML → still detected with empty fields
- [ ] Non-dict YAML → still detected, `api_version=""`
- [ ] Skaffold CLI present → `available=True`
- [ ] Skaffold CLI absent → `available=False`
- [ ] apiVersion parsed from config

#### 0.2.10 Environment Namespaces (`k8s_wizard_detect.py`)
- [ ] No project.yml → empty environments list
- [ ] project.yml with no environments → empty list
- [ ] Namespace follows `project-name-envname` convention
- [ ] Environment names preserved from project.yml
- [ ] Default flag propagated
- [ ] k8s/overlays/{env} directory → `has_overlay=True`
- [ ] k8s/envs/{env} directory → `has_overlay=True`
- [ ] kubernetes/overlays/{env} → `has_overlay=True`
- [ ] deploy/overlays/{env} → `has_overlay=True`
- [ ] k8s/overlays/ checked first (priority)
- [ ] Multiple envs with mixed overlays
- [ ] Helm values file detected (values-{env}.yaml, values.{env}.yaml, etc.)

#### 0.2.11 Cluster Operations (`k8s_cluster.py`) — online, mocked
- [ ] `cluster_status` → connected, context, nodes, namespaces
- [ ] `cluster_status` when kubectl fails → `connected=False`
- [ ] `get_resources` → list of pods/deployments with name, namespace, status, age
- [ ] `get_resources` with namespace filter
- [ ] `get_resources` with kind filter (pods, deployments, services, etc.)
- [ ] `k8s_pod_logs` → pod log output with tail limit
- [ ] `k8s_pod_logs` with container filter
- [ ] `k8s_pod_logs` on missing pod → error
- [ ] `k8s_apply` with file path → applies manifest
- [ ] `k8s_apply` with namespace override
- [ ] `k8s_apply` on failure → error dict
- [ ] `k8s_delete_resource` → deletes by kind + name
- [ ] `k8s_delete_resource` with namespace
- [ ] `k8s_scale` → scales deployment/statefulset
- [ ] `k8s_scale` with kind override
- [ ] `k8s_events` → recent events with type, reason, object, message, age
- [ ] `k8s_events` with namespace filter
- [ ] `k8s_describe` → description string for kind/name
- [ ] `k8s_describe` on missing resource → error
- [ ] `k8s_namespaces` → list of namespaces with name, status, age
- [ ] `k8s_storage_classes` → list with name, provisioner, is_default, reclaim_policy
- [ ] `k8s_storage_classes` identifies default class
- [ ] `_summarize_conditions` → condensed condition summary string

#### 0.2.12 Helm Operations (`k8s_helm.py`) — online, mocked
- [ ] `_helm_available` → True when helm CLI present
- [ ] `_helm_available` → False when helm CLI absent
- [ ] `helm_list` → releases list with name, namespace, revision, status, chart, app_version
- [ ] `helm_list` when helm not available → `{available: False, error: "helm CLI not found"}`
- [ ] `helm_list` with namespace filter
- [ ] `helm_list` without namespace → `--all-namespaces`
- [ ] `helm_list` on failure → error in result but available=True
- [ ] `helm_values` → YAML string of values for a release
- [ ] `helm_values` when helm not available → error
- [ ] `helm_values` on missing release → error
- [ ] `helm_install` → installs chart with release name
- [ ] `helm_install` with namespace → `--create-namespace`
- [ ] `helm_install` with values_file → `--values`
- [ ] `helm_install` with set_values → `--set k=v`
- [ ] `helm_install` with dry_run → `--dry-run`
- [ ] `helm_install` when helm not available → error
- [ ] `helm_install` on failure → error dict
- [ ] `helm_upgrade` → upgrades release with `--install`
- [ ] `helm_upgrade` with namespace/values/set/dry_run args
- [ ] `helm_upgrade` when helm not available → error
- [ ] `helm_template` → renders YAML locally (no cluster)
- [ ] `helm_template` with namespace + values_file
- [ ] `helm_template` when helm not available → error
- [ ] `helm_template` on failure → error dict

#### 0.2.13 Workload Kinds (advanced wizard)
- [ ] `kind=StatefulSet` → StatefulSet resource produced, not Deployment
- [ ] StatefulSet has `serviceName` referencing headless Service
- [ ] `kind=DaemonSet` → DaemonSet resource, no replicas field
- [ ] `kind=Job` → Job resource
- [ ] `kind=CronJob` → CronJob resource with schedule
- [ ] Multiple services with different kinds → correct resource types
- [ ] No kind specified → defaults to Deployment

#### 0.2.14 Multi-Container Pods (advanced wizard)
- [ ] Service with sidecar → pod template has 2+ containers
- [ ] Service with init container → `initContainers` in pod template
- [ ] Service with companion → multiple containers in same pod
- [ ] Multiple volumes on one service → all volumes and mounts present

#### 0.2.15 Infrastructure Services
- [ ] Infra service `isInfra=True` → own Deployment + Service resources
- [ ] Postgres infra service with PVC volume → PVC resource created
- [ ] Infra service kind override (e.g., StatefulSet)

#### 0.2.16 HPA (Autoscaler)
- [ ] Service with autoscaling config → HPA resource created
- [ ] HPA references correct Deployment name
- [ ] No autoscaling config → no HPA resource

#### 0.2.17 Setup_K8s Integration (round-trip)
- [ ] `setup_k8s` with simple state → files written to k8s/ dir
- [ ] `setup_k8s` creates k8s/ directory if it doesn't exist
- [ ] `setup_k8s` with env vars → ConfigMap file created
- [ ] `setup_k8s` with non-default namespace → Namespace resource
- [ ] `setup_k8s` output passes `validate_manifests`
- [ ] `setup_k8s` output found by `k8s_status`
- [ ] `setup_k8s` with multiple services → all files created

#### 0.2.18 Delete Config
- [ ] `delete_generated_configs('k8s')` → k8s/ dir removed
- [ ] Delete when no k8s/ dir → nothing deleted, no error
- [ ] Setup → delete → k8s_status shows nothing (round-trip)

#### 0.2.19 Skaffold Integration (wizard)
- [ ] `skaffold=True` in wizard state → skaffold.yaml created
- [ ] `skaffold=False` → no skaffold.yaml
- [ ] Generated skaffold.yaml is valid YAML
- [ ] skaffold.yaml references generated manifest paths
- [ ] Build artifact image matches wizard service image
- [ ] After setup → `skaffold_status()` detects the config

#### 0.2.20 Env Var Wiring (integration)
- [ ] Plain env vars → envFrom/valueFrom referencing ConfigMap
- [ ] Secret env vars → valueFrom referencing Secret
- [ ] Mix of plain + secret → both ConfigMap and Secret resources

#### 0.2.21 Error Cases
- [ ] kubectl not installed → clear error on cluster operations
- [ ] Cluster not reachable → clear error
- [ ] helm not installed → `{error: "helm CLI not found"}`
- [ ] Invalid service image → validation warning (:latest implicit)
- [ ] Missing metadata.name → validation error
- [ ] Deployment without containers → validation error
- [ ] Empty resource list → `generate_k8s_wizard` returns error
- [ ] `load_wizard_state` on corrupt JSON → graceful error
- [ ] `save_wizard_state` on read-only path → filesystem error surfaced
- [ ] `_parse_k8s_yaml` on unreadable file → empty list (no crash)
- [ ] `_parse_k8s_yaml` on malformed YAML → empty list (no crash)
- [ ] `_build_wizard_volume` with no mountPath → (None, None)
- [ ] `_build_wizard_volume` with unknown type → (None, None)
- [ ] `_build_env_vars` with items missing name/key → skipped
- [ ] `generate_manifests` with empty app_name → still produces files (uses empty string)
- [ ] `k8s_apply` on nonexistent file → error from kubectl
- [ ] `k8s_delete_resource` on nonexistent resource → error from kubectl
- [ ] `k8s_scale` with negative replicas → kubectl error
- [ ] `helm_install` failure → error dict with stderr
- [ ] `helm_upgrade` failure → error dict with stderr
- [ ] `helm_template` failure → error dict with stderr

---

### 0.3 Skaffold

#### 0.3.1 Detection
- [ ] No skaffold files → has_skaffold=False
- [ ] skaffold.yaml present → detected
- [ ] skaffold.yml present → detected
- [ ] Both variants → both detected
- [ ] apiVersion parsed
- [ ] Profiles extracted (dev, staging, production)
- [ ] Profiles without name → skipped
- [ ] No profiles section → empty list
- [ ] Malformed YAML → still detected, fields empty
- [ ] CLI available → available=True
- [ ] CLI not available → available=False

#### 0.3.2 Generation
- [ ] skaffold=False → no file generated
- [ ] skaffold=True → skaffold.yaml created
- [ ] Valid YAML output
- [ ] Correct apiVersion (skaffold/v4beta11)
- [ ] kind: Config
- [ ] deploy section present
- [ ] manifests section present
- [ ] Build artifacts from services with images
- [ ] Multiple services → multiple artifacts
- [ ] Skip kind excluded from artifacts
- [ ] Empty image excluded from artifacts
- [ ] No services → no build section
- [ ] Manifest paths from generated K8s files
- [ ] Non-YAML files excluded from manifests
- [ ] Fallback glob when no files
- [ ] Custom output_dir reflected in paths
- [ ] Metadata name from first service
- [ ] Default name "app" when no services
- [ ] overwrite=False by default

#### 0.3.3 Wizard Integration
- [ ] `setup_k8s()` with skaffold=True → skaffold.yaml created
- [ ] skaffold.yaml on disk after setup
- [ ] Generated skaffold.yaml is valid YAML
- [ ] skaffold.yaml references generated manifests
- [ ] skaffold=False → no skaffold.yaml
- [ ] After setup → skaffold_status() detects the config
- [ ] Build artifact image matches wizard service image

#### 0.3.4 Settings Variants
- [ ] Single service, single artifact
- [ ] Multiple services, multiple artifacts
- [ ] With custom skaffold file path
- [ ] With profiles for different environments
- [ ] With default-repo for registry

#### 0.3.5 Error Cases
- [ ] skaffold CLI not installed → detection still works (file-based)
- [ ] Malformed existing skaffold.yaml → overwrite works

---

### 0.4 Helm

#### 0.4.1 Detection
- [ ] No Chart.yaml → empty list
- [ ] Single chart → detected with name, version, description
- [ ] Multiple charts → all detected
- [ ] Nested chart (deploy/helm/myapp/) → detected
- [ ] Charts in skipped dirs (node_modules, .venv) → not detected
- [ ] Chart path is relative to project root
- [ ] Missing chart name → defaults to "unknown"
- [ ] Missing chart version → defaults to "0.0.0"
- [ ] Chart description extracted
- [ ] Malformed Chart.yaml → detected as "unknown"
- [ ] Chart with dependencies → still detected

#### 0.4.2 CLI Wrappers (mocked)
- [ ] `helm_list()` — no helm CLI → error
- [ ] `helm_list()` — basic call uses --all-namespaces
- [ ] `helm_list()` — with namespace uses --namespace
- [ ] `helm_list()` — parses JSON releases
- [ ] `helm_list()` — error returned on failure
- [ ] `helm_values()` — basic call with release name
- [ ] `helm_values()` — with namespace
- [ ] `helm_values()` — error on failure
- [ ] `helm_install()` — basic install command
- [ ] `helm_install()` — with namespace + --create-namespace
- [ ] `helm_install()` — with values file
- [ ] `helm_install()` — with --set values
- [ ] `helm_install()` — with --dry-run
- [ ] `helm_install()` — error response
- [ ] `helm_upgrade()` — uses --install flag
- [ ] `helm_upgrade()` — all options combined (ns + values + set + dry-run)
- [ ] `helm_upgrade()` — error response
- [ ] `helm_template()` — renders YAML output
- [ ] `helm_template()` — with namespace
- [ ] `helm_template()` — with values file
- [ ] `helm_template()` — error response

#### 0.4.3 Values File Detection
- [ ] values-{env}.yaml in project root → detected
- [ ] values-{env}.yaml in helm/ dir → detected
- [ ] values-{env}.yaml in charts/ dir → detected
- [ ] values.{env}.yaml (dot format) → detected
- [ ] No values file → empty string

#### 0.4.4 Error Cases
- [ ] helm CLI not installed → detection still works (file-based)
- [ ] helm CLI timeout → graceful error
- [ ] Invalid chart path → error message

---

### 0.5 CI/CD

#### 0.5.1 Detection
- [ ] Empty project → no CI detected
- [ ] .github/workflows/*.yml → GitHub Actions detected
- [ ] Multiple workflow files → counted correctly
- [ ] .gitlab-ci.yml → GitLab CI detected
- [ ] .gitlab-ci.yaml → GitLab CI detected
- [ ] Jenkinsfile → Jenkins detected
- [ ] .circleci/config.yml → CircleCI detected
- [ ] .travis.yml → Travis detected
- [ ] azure-pipelines.yml → Azure Pipelines detected
- [ ] bitbucket-pipelines.yml → Bitbucket Pipelines detected
- [ ] Multiple providers → all detected
- [ ] Non-YAML files in .github/workflows → ignored

#### 0.5.2 Workflow Parsing
- [ ] GitHub Actions workflow → name, triggers, jobs parsed
- [ ] GitLab CI → jobs extracted, dot-templates skipped, meta keys skipped
- [ ] Jenkinsfile → listed (not parsed)
- [ ] Multi-provider → combined list
- [ ] Invalid YAML → handled gracefully
- [ ] Jobs have step counts

#### 0.5.3 Generation (stack-based)
- [ ] Python stack → pytest, ruff, mypy steps
- [ ] Node stack → npm test, eslint steps
- [ ] Go stack → go test steps
- [ ] Rust stack → cargo test steps
- [ ] Java Maven stack → mvn test steps
- [ ] Java Gradle stack → gradle test steps
- [ ] Multi-stack → combined workflow
- [ ] Unknown stack → returns None
- [ ] Empty stacks → returns None
- [ ] Project name in workflow name
- [ ] Deduplication (python + python-flask → one job)
- [ ] Actions pinned to versions
- [ ] permissions: contents: read
- [ ] Output is valid YAML
- [ ] Lint-only workflow generation

#### 0.5.4 Wizard Setup (basic)
- [ ] `setup_ci()` with minimal data → ci.yml created
- [ ] `setup_ci()` → ci_status detects GHA
- [ ] `setup_ci()` → ci_workflows parses the file
- [ ] Valid YAML output
- [ ] Push and PR triggers present
- [ ] Jobs have steps
- [ ] Overwrite works
- [ ] Round-trip: setup → detect → parse → validate

#### 0.5.5 Error Cases
- [ ] Malformed existing workflow → detection handles gracefully
- [ ] Empty YAML file → handled

---

### 0.6 Terraform

#### 0.6.1 Detection
- [ ] Empty project → no Terraform detected
- [ ] *.tf files present → detected
- [ ] terraform/ directory → detected
- [ ] .terraform/ state dir → detected
- [ ] terraform.tfstate → detected
- [ ] terraform.tfvars → detected
- [ ] Backend configuration detected (S3, GCS, Azure)
- [ ] Provider configuration detected (AWS, GCP, Azure)
- [ ] Module references detected
- [ ] Workspace detection

#### 0.6.2 Generation
- [ ] Generate main.tf with provider block
- [ ] Generate variables.tf
- [ ] Generate outputs.tf
- [ ] Generate backend configuration
- [ ] Generate for AWS provider
- [ ] Generate for GCP provider
- [ ] Generate for Azure provider
- [ ] Generate with remote state (S3)
- [ ] Generate with remote state (GCS)
- [ ] Environment-specific tfvars files

#### 0.6.3 CLI Wrappers (mocked)
- [ ] `terraform init` — command construction
- [ ] `terraform plan` — command construction
- [ ] `terraform plan` — with var-file
- [ ] `terraform apply` — command construction
- [ ] `terraform apply` — auto-approve flag
- [ ] `terraform destroy` — command construction
- [ ] `terraform workspace list`
- [ ] `terraform workspace select`
- [ ] `terraform workspace new`
- [ ] `terraform output` — JSON parsing
- [ ] `terraform state list`
- [ ] All commands — CLI not installed → error
- [ ] All commands — timeout → error

#### 0.6.4 Wizard Setup
- [ ] `setup_terraform()` → tf files created
- [ ] `setup_terraform()` → round-trip with detection
- [ ] Provider selection flows through to generated files
- [ ] Backend selection flows through

#### 0.6.5 Error Cases
- [ ] Terraform CLI not installed → detection still works (file-based)
- [ ] Invalid HCL → detection warns
- [ ] State lock → appropriate error

---

### 0.7 DNS/CDN

#### 0.7.1 Detection
- [ ] No domain config → nothing detected
- [ ] Domain in project config → detected
- [ ] DNS records resolvable → reported
- [ ] DNS records not resolvable → reported
- [ ] Multiple domains → all checked
- [ ] CDN configuration detected (Cloudflare, AWS CloudFront)
- [ ] SSL/TLS certificate status

#### 0.7.2 Operations
- [ ] DNS lookup for A record
- [ ] DNS lookup for CNAME record
- [ ] DNS lookup for MX record
- [ ] DNS lookup for TXT record
- [ ] DNS propagation check
- [ ] CDN cache purge (mocked)
- [ ] CDN configuration query (mocked)

#### 0.7.3 Wizard Setup
- [ ] `setup_dns()` → domain config stored
- [ ] Round-trip: setup → detect → matches

#### 0.7.4 Error Cases
- [ ] Unreachable DNS → timeout with message
- [ ] Invalid domain format → validation error

---

## Layer 1 — Two-Domain Chains

Every pair of domains that can interact.

### 1.1 Docker + K8s
- [ ] Docker image name from Docker setup → used in K8s Deployment manifest
- [ ] Docker ports → match K8s Service ports
- [ ] Docker compose services → map to K8s services
- [ ] Docker registry from Docker setup → used in K8s image pull
- [ ] Enable Docker first, then K8s → K8s references Docker image
- [ ] Enable K8s first, then Docker → K8s updated with Docker image
- [ ] Docker build args → reflected in K8s env vars or ConfigMap

### 1.2 Docker + CI/CD
- [ ] Docker enabled → CI includes docker build step
- [ ] Docker + GHCR registry → CI has GHCR login + push
- [ ] Docker + DockerHub registry → CI has DockerHub login + push
- [ ] Docker + custom registry → CI has custom login + push
- [ ] Docker + no registry → CI has build only, no push
- [ ] Docker + Buildx → CI uses docker/setup-buildx-action
- [ ] Docker + build args → CI passes --build-arg
- [ ] Docker + layer caching → CI uses GHA cache
- [ ] Docker + image tagging → CI uses SHA/version tags

### 1.3 Docker + Skaffold
- [ ] Docker image → Skaffold build artifact
- [ ] Docker registry → Skaffold --default-repo
- [ ] Multiple Docker services → multiple Skaffold artifacts

### 1.4 Docker + Helm
- [ ] Docker image → Helm --set image.tag
- [ ] Docker registry → Helm values image.repository

### 1.5 K8s + CI/CD (kubectl)
- [ ] K8s enabled, method=kubectl → CI has kubectl apply step
- [ ] K8s manifest dir → CI references it
- [ ] K8s namespace → CI uses -n flag
- [ ] CI deploy job depends on test job
- [ ] CI sets up kubeconfig from secret
- [ ] CI does dry-run validation before apply
- [ ] CI waits for rollout after apply

### 1.6 K8s + CI/CD (Skaffold)
- [ ] K8s enabled, method=skaffold → CI has skaffold command
- [ ] CI installs skaffold CLI
- [ ] No raw kubectl apply in CI
- [ ] Skaffold profiles per environment in CI
- [ ] Skaffold --default-repo in CI
- [ ] Custom skaffold file path in CI
- [ ] CI sets up kubeconfig

### 1.7 K8s + CI/CD (Helm)
- [ ] K8s enabled, method=helm → CI has helm upgrade --install
- [ ] Chart path in CI
- [ ] Release name in CI
- [ ] Values per environment in CI
- [ ] --set image.tag in CI
- [ ] Namespace in CI
- [ ] No kubectl apply in CI
- [ ] No skaffold in CI
- [ ] CI sets up kubeconfig

### 1.8 K8s + Skaffold
- [ ] K8s manifests → referenced in skaffold.yaml manifests section
- [ ] K8s services → Skaffold build artifacts
- [ ] K8s namespace → Skaffold deploy namespace

### 1.9 K8s + Helm
- [ ] K8s services → Helm chart templates
- [ ] K8s values → Helm values.yaml
- [ ] K8s namespace → Helm --namespace

### 1.10 K8s + Terraform
- [ ] Terraform provisions cluster → K8s connects to it
- [ ] Terraform outputs (cluster endpoint, kubeconfig) → K8s uses them
- [ ] Terraform namespace resource → K8s namespace

### 1.11 CI/CD + Terraform
- [ ] Terraform enabled → CI has terraform init/plan steps
- [ ] PR → terraform plan only (no apply)
- [ ] Merge to main → terraform apply
- [ ] Terraform state backend credentials in CI secrets
- [ ] Per-environment terraform workspaces in CI

### 1.12 Skaffold + Helm
- [ ] Skaffold can use Helm deployer instead of kubectl deployer
- [ ] Skaffold handles both build and Helm deploy

### 1.13 DNS + CI/CD
- [ ] DNS verification step in deploy pipeline
- [ ] CDN cache purge step after deploy

### 1.14 Docker + Terraform
- [ ] Terraform provisions container registry → Docker uses it
- [ ] ECR/GCR/ACR provisioned → Docker registry config updated

---

## Layer 2 — Three-Domain Chains

### 2.1 Docker + K8s + CI/CD
- [ ] Full pipeline: test → docker build → docker push → kubectl apply
- [ ] Full pipeline: test → docker build → docker push → skaffold run
- [ ] Full pipeline: test → docker build → docker push → helm upgrade
- [ ] Job dependency chain: test → build → deploy
- [ ] Docker image tag passed from build to deploy job
- [ ] Deploy only on push to main, not on PRs
- [ ] PRs run tests only

### 2.2 Docker + K8s + Skaffold
- [ ] Skaffold builds Docker image and deploys K8s manifests
- [ ] Docker registry → Skaffold --default-repo → K8s image pull
- [ ] Skaffold profiles select different K8s manifests per env

### 2.3 Docker + K8s + Helm
- [ ] Docker image → Helm values → K8s Deployment
- [ ] Docker registry → Helm image.repository
- [ ] Docker tag → Helm image.tag
- [ ] Helm values per env → different Docker tags per env

### 2.4 Docker + K8s + Terraform
- [ ] Terraform provisions cluster + registry
- [ ] Docker builds and pushes to provisioned registry
- [ ] K8s deploys to provisioned cluster

### 2.5 K8s + CI/CD + Multi-Environment
- [ ] All environments referenced in CI
- [ ] Namespace per environment
- [ ] Deploy ordering: dev → staging → production
- [ ] Production deploy constrained to main branch
- [ ] Per-environment secrets in CI
- [ ] Per-environment kubeconfig
- [ ] Skaffold profiles per env in CI
- [ ] Helm values per env in CI

### 2.6 K8s + Terraform + CI/CD
- [ ] CI does terraform plan → terraform apply → kubectl apply
- [ ] Terraform provisions, then K8s deploys, in single workflow
- [ ] Terraform state and kubeconfig both from secrets

---

## Layer 3 — Full Stack Chains

### 3.1 Docker + K8s + Skaffold + CI/CD + Multi-Env
- [ ] Wizard: enable Docker → enable K8s with Skaffold → enable CI/CD
- [ ] CI: test → docker build (via Skaffold) → deploy per env (via Skaffold profiles)
- [ ] Each env: different Skaffold profile, different namespace, different secrets
- [ ] PR: test only. Push to main: full pipeline

### 3.2 Docker + K8s + Helm + CI/CD + Multi-Env
- [ ] Wizard: enable Docker → enable K8s with Helm → enable CI/CD
- [ ] CI: test → docker build → docker push → helm upgrade per env
- [ ] Each env: different values file, different namespace
- [ ] Helm --set image.tag=${{ github.sha }}
- [ ] PR: test only. Push to main: full pipeline

### 3.3 Docker + K8s + Terraform + CI/CD
- [ ] CI: terraform plan/apply → docker build/push → k8s deploy
- [ ] Terraform outputs feed into K8s config (cluster endpoint, registry URL)

### 3.4 Everything
- [ ] Docker + K8s (Helm or Skaffold) + Terraform + CI/CD + DNS + Multi-Env
- [ ] Complete wizard flow: detect → configure → generate → validate → deploy
- [ ] Cleanup: delete all generated configs → clean slate

---

## Layer 4 — Order of Execution Variants

### 4.1 Docker first
- [ ] Enable Docker → then K8s → K8s picks up Docker image
- [ ] Enable Docker → then CI → CI picks up Docker build steps
- [ ] Enable Docker → then K8s → then CI → CI has full pipeline

### 4.2 K8s first
- [ ] Enable K8s (no Docker yet) → plain manifests with external image
- [ ] Enable K8s → then Docker → manifests updated with Docker image
- [ ] Enable K8s → then Docker → then CI → full pipeline

### 4.3 CI first
- [ ] Enable CI alone → basic test-only workflow
- [ ] Enable CI → then Docker → CI updated with Docker build
- [ ] Enable CI → then K8s → CI updated with deploy steps
- [ ] Enable CI → then Docker → then K8s → CI has full pipeline

### 4.4 Terraform first
- [ ] Enable Terraform → then K8s → K8s uses Terraform-provisioned cluster
- [ ] Enable Terraform → then Docker → Docker uses Terraform-provisioned registry

### 4.5 Re-run after changes
- [ ] Change Docker registry → CI updates
- [ ] Change K8s deploy method (kubectl → helm) → CI updates
- [ ] Add environment → CI adds deploy job
- [ ] Remove environment → CI removes deploy job
- [ ] Disable Docker → CI removes Docker steps

---

## Layer 5 — Error & Edge Cases

### 5.1 Missing Tools
- [ ] Docker enabled but docker CLI missing → clear message, install button
- [ ] K8s enabled but kubectl missing → clear message, install button
- [ ] Skaffold enabled but skaffold CLI missing → clear message, install button
- [ ] Helm enabled but helm CLI missing → clear message, install button
- [ ] Terraform enabled but terraform CLI missing → clear message, install button

### 5.2 Misconfiguration
- [ ] Docker registry URL malformed → validation error
- [ ] K8s namespace with invalid characters → validation error
- [ ] Helm chart path doesn't exist → warning
- [ ] Skaffold profiles reference nonexistent manifests → warning
- [ ] CI references secrets that don't exist → warning in generated YAML comments

### 5.3 Partial State
- [ ] Wizard interrupted mid-flow → state saved, resumable
- [ ] Some files generated, some not → detection handles partial state
- [ ] Generated files manually edited → detect picks up changes

### 5.4 Cleanup
- [ ] `delete_generated_configs("docker")` → removes Docker files only
- [ ] `delete_generated_configs("k8s")` → removes K8s files only
- [ ] `delete_generated_configs("ci")` → removes CI files only
- [ ] `delete_generated_configs("skaffold")` → removes skaffold.yaml only
- [ ] `delete_generated_configs("terraform")` → removes tf files only
- [ ] Cleanup one domain → others untouched
- [ ] Re-setup after cleanup → works cleanly
