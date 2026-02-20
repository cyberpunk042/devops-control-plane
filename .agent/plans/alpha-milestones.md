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

#### 0.2.2 Detection — full K8s ecosystem detection

> **Scope:** Detection spans 4 backend modules (`k8s_detect`, `k8s_wizard_detect`,
> `k8s_cluster`, `k8s_helm`) and 10 routes. Source of truth is the K8s technology
> spec + project scope (single-env / multi-env, Minikube / cloud clusters,
> kubectl / Helm install channels). NOT just the current code.

##### 0.2.2a Manifest collection (`_collect_yaml_files`)
- [x] YAML files in `k8s/` directory → collected
- [x] YAML files in `kubernetes/` directory → collected
- [x] YAML files in `deploy/` directory → collected
- [x] YAML files in `manifests/` directory → collected
- [x] YAML files in `kube/` directory → collected
- [x] YAML files in `charts/` directory → collected
- [x] YAML files in nested subdirectories of manifest dir → collected
- [x] Both `.yaml` and `.yml` extensions → collected
- [x] YAML files inside `_SKIP_DIRS` (.git, node_modules, .venv, __pycache__, etc.) → skipped
- [x] No manifest dirs found → scans project root
- [x] At most 50 YAML files returned (cap)
- [x] Empty manifest dir → empty list
- [x] Multiple manifest dirs simultaneously (k8s/ + deploy/) → all collected

##### 0.2.2b Helm chart detection (`_detect_helm_charts`)
- [x] Chart.yaml with name + version → detected with name, version, description
- [x] Multiple Chart.yaml in different directories → all detected
- [x] Chart.yaml inside `_SKIP_DIRS` → skipped
- [x] Malformed Chart.yaml → still detected with name=unknown
- [x] No Chart.yaml → empty list
- [x] Nested chart (deploy/helm/myapp/Chart.yaml) → detected
- [x] `appVersion` field → extracted when present
- [x] Chart `type` field (application vs library) → extracted when present
- [x] `values.yaml` presence next to Chart.yaml → detected
- [x] `templates/` directory presence → detected
- [x] Sub-charts in `charts/` subdirectory → detected
- [x] `Chart.lock` (dependency lock) presence → detected
- [x] Env-specific values files (`values-dev.yaml`, `values-staging.yaml`) → detected

##### 0.2.2c Kustomize detection (`_detect_kustomize`)
- [x] `kustomization.yaml` at root → detected
- [x] `kustomization.yml` at root → detected
- [x] `Kustomization` (capitalized, no ext) at root → detected
- [x] `kustomization.yaml` in `k8s/` subdirectory → detected
- [x] `kustomization.yaml` in `kubernetes/` subdirectory → detected
- [x] `kustomization.yaml` in `deploy/` subdirectory → detected
- [x] No kustomization file → `{exists: False}`
- [x] Overlays structure detected (`k8s/overlays/` with per-env subdirs)
- [x] Number of overlay environments → counted
- [x] Bases directory detected → `has_bases: True`
- [x] Single-env vs multi-env Kustomize → mode identified
- [x] Patches detected — `patchesStrategicMerge`, `patchesJson6902`, or `patches` referenced
- [x] Patch count per overlay → counted
- [x] `configMapGenerator` entries → detected
- [x] `secretGenerator` entries → detected (auto base64 handling)
- [x] Raw Secret manifests without secretGenerator → flagged (manual base64 risk)
- [x] `${VAR}` patterns in manifests → envsubst dependency detected
- [x] `vars`/`replacements` in kustomization → variable refs detected
- [x] `images` section → image overrides detected per overlay
- [x] `namespace` field → namespace override detected
- [x] `namePrefix`/`nameSuffix` → transformations detected

##### 0.2.2d `k8s_status` orchestration

> `k8s_status` is the single orchestrator that answers: "What does this project deploy,
> how, where, and is it ready?" It combines all sub-detectors into a coherent picture.

###### 0.2.2d-0 Plumbing (existing sub-detector integration)
- [x] Empty project → `has_k8s=False`, empty manifests/charts/kustomize
- [x] Single deployment manifest → detected, resources parsed with kind/name/namespace/apiVersion
- [x] Multi-document YAML (`---`) → all resources detected and counted
- [x] Helm-only project (Chart.yaml, no raw manifests) → `has_k8s=True`
- [x] Kustomize-only project → `has_k8s=True`
- [x] kubectl availability included in result
- [x] Non-K8s YAML (no kind/apiVersion) → not counted
- [x] Multiple manifest dirs (k8s/ + deploy/) → both listed in `manifest_dirs`
- [x] `resource_summary` counts kinds correctly (e.g., Deployment: 2, Service: 3)
- [x] Manifest detail has `path`, `resources` list, and `count`
- [x] Each resource has `kind`, `name`, `namespace`, `apiVersion`
- [x] Files in `.venv` → skipped
- [x] Files in `node_modules` → skipped
- [x] Return shape has all required keys: `has_k8s`, `kubectl`, `manifest_dirs`, `manifests`, `resource_summary`, `total_resources`, `helm_charts`, `kustomize`

###### 0.2.2d-i Deployment strategy detection
- [x] Raw-kubectl-only project (manifests, no Helm/Kustomize/Skaffold) → `deployment_strategy: "raw_kubectl"`
- [x] Helm-only project → `deployment_strategy: "helm"`
- [x] Kustomize-only project → `deployment_strategy: "kustomize"`
- [ ] Skaffold-orchestrated project → `deployment_strategy: "skaffold"` _(depends on 0.2.2e)_
- [x] Mixed project (Helm charts + raw manifests) → `deployment_strategy: "mixed"`, `strategies_detected: ["helm", "raw_kubectl"]`
- [x] Kustomize + Helm sub-charts → `strategies_detected: ["kustomize", "helm"]`
- [x] `strategies_detected` is always a list, even for single strategy
- [x] Each strategy in list is a known enum value (no free-form strings)

###### 0.2.2d-ii Unified environment map
- [x] Environments from Kustomize overlays → rolled up into `environments` list
- [x] Environments from Helm values files (values-dev.yaml) → rolled up
- [ ] Environments from Skaffold profiles → rolled up _(depends on 0.2.2e)_
- [x] Duplicate env names across sources → deduplicated
- [x] Each environment has: `name`, `source` (kustomize_overlay | helm_values | skaffold_profile), `namespace` (if detectable)
- [x] No environments detected → `environments: []`, not error
- [x] Environment count matches sum of unique env names
- [x] Kustomize namespace override → included in env's `namespace` field

###### 0.2.2d-iii Readiness assessment
- [x] `tool_availability` includes: kubectl, helm, kustomize, skaffold (each with available + version)
- [x] `secret_safety.has_raw_secrets` → True when raw `kind: Secret` manifests exist without secretGenerator
- [x] `secret_safety.has_envsubst_vars` → True when `${VAR}` patterns found in manifests
- [x] `secret_safety.envsubst_vars` → list of variable names needed
- [x] `secret_safety.has_secret_generator` → True when Kustomize secretGenerator is used
- [x] `deployment_readiness` → overall level: "ready" | "needs_config" | "needs_tools" | "not_configured"
- [x] "needs_tools" when required tools (based on strategy) are not installed
- [x] "needs_config" when envsubst vars detected or raw secrets present
- [x] "not_configured" when no K8s files detected at all
- [x] "ready" when tools available and no config gaps detected

###### 0.2.2d-iv Infrastructure service detection
- [x] Helm chart with known infra name (ingress-nginx, cert-manager, prometheus, etc.) → classified as infrastructure
- [x] `kind: Ingress` in manifests → `requires_ingress_controller: True`
- [x] `cert-manager.io` annotations or `kind: Certificate` → `requires_cert_manager: True`
- [x] `kind: ServiceMonitor` or `kind: PrometheusRule` → `requires_prometheus: True`
- [x] Each detected infra service has: `name`, `detected_via` (helm_chart | manifest_annotation | resource_kind), `installed` (unknown until cluster query)
- [x] No infra references detected → `infra_services: []`
- [ ] Application resources vs infrastructure resources → classified separately in `resource_summary` _(future refinement)_

##### 0.2.2e Skaffold detection (`skaffold_status`)
- [x] `skaffold.yaml` present → detected with path, api_version, profiles
- [x] `skaffold.yml` present → detected
- [x] Both `.yaml` and `.yml` → both detected
- [x] Skaffold with profiles → profile names extracted
- [x] Malformed skaffold.yaml → still detected with empty profiles
- [x] No skaffold file → `has_skaffold=False`, empty configs
- [x] Skaffold CLI available → `available=True`
- [x] Skaffold CLI not installed → `available=False`

##### 0.2.2f Multi-environment namespace mapping (`k8s_env_namespaces`)
- [x] `project.yml` with environments → namespace convention `{project}-{env}`
- [x] No `project.yml` → empty environments list
- [x] Project with no environments → empty list
- [x] `default` flag on env → propagated
- [x] Overlay in `k8s/overlays/{env}` → detected with path
- [x] Overlay in `k8s/envs/{env}` → detected
- [x] Overlay in `kubernetes/overlays/{env}` → detected
- [x] Overlay in `deploy/overlays/{env}` → detected
- [x] No overlay dir found → `has_overlay=False`
- [x] Overlay priority: `k8s/overlays/` checked first
- [x] Helm values file `values-{env}.yaml` → detected
- [x] Helm values file `values.{env}.yaml` (dot format) → detected
- [x] Helm values in `helm/` subdir → detected
- [x] Helm values in `charts/` subdir → detected
- [x] No values file → empty string
- [x] Multi-env with mixed overlays and values → all detected
- [x] Single-env mode (no env in project.yml) → still returns empty list (no crash)

##### 0.2.2g Cluster connectivity detection (`cluster_status`)
- [x] kubectl not available → `connected=False`, error message
- [x] kubectl available, cluster reachable → `connected=True`, context, nodes, namespaces
- [x] kubectl available, cluster unreachable (timeout) → `connected=False` gracefully
- [x] Current context returned
- [x] Nodes listed with name, ready status, roles, version
- [x] Namespaces listed
- [x] Return shape: `connected`, `context`, `nodes`, `namespaces`
- [x] **FIX**: `_kubectl_available` updated from deprecated `--short` to `-o json` (broken on kubectl v1.28+)

##### 0.2.2h Cluster type detection (NEW)
> Identify what KIND of cluster is running. This changes available features,
> defaults, and what advice the wizard gives.
- [x] **Minikube** detected from context name (`minikube`) or `minikube status`
- [x] **Kind** detected from context name (`kind-*`)
- [x] **Docker Desktop** detected from context name (`docker-desktop`)
- [x] **k3s/k3d** detected from context name or node labels
- [x] **EKS** detected from context name (`arn:aws:eks:*`) or kubeconfig patterns
- [x] **AKS** detected from context name or Azure patterns
- [x] **GKE** detected from context name (`gke_*`)
- [x] **Unknown/bare-metal** as fallback
- [x] Cluster type returned in `cluster_status()` result
- [ ] Cluster type influences wizard recommendations (e.g., LoadBalancer vs NodePort for Minikube) _(deferred to wizard integration)_

##### 0.2.2i Cloud CLI detection (NEW)
> Cloud CLIs are the authentication channel for managed K8s clusters.
> Without them, the user can't connect to their cluster.
- [x] `az` CLI available → detected (Azure)
- [x] `aws` CLI available → detected (AWS)
- [x] `gcloud` CLI available → detected (GCP)
- [x] `minikube` CLI available → detected
- [x] `kind` CLI available → detected
- [x] None available → still works (local/manual kubeconfig)
- [x] Detection result included in `k8s_status()` `tool_availability`

##### 0.2.2j Helm CLI + releases detection (`k8s_helm`)
- [x] `helm` CLI not installed → `available=False`, error message
- [x] `helm` CLI installed → `available=True`
- [x] Helm CLI available but cluster unreachable → releases empty, error returned
- [x] Helm releases listed with name, namespace, revision, status, chart, app_version
- [x] Namespace filter works (specific namespace)
- [x] All-namespaces mode (`--all-namespaces`)
- [x] No releases installed → empty list
- [x] Helm list JSON parse error → graceful error
- [x] Timeout on helm list → graceful error

#### 0.2.3 Validation — full DevOps control plane checks (`k8s_validate.py`)

> **Scope:** Validation is NOT a YAML linter. It is the control plane's
> "single pane of glass" that catches problems across the full deployment
> pipeline — from manifest structure, through cross-resource wiring,
> environment completeness, cluster compatibility, security posture,
> and cross-domain alignment (Docker ↔ K8s ↔ Terraform ↔ CI/CD).
>
> Source of truth: Kubernetes API spec + project scope + detection data
> from 0.2.2. NOT the current code.

##### 0.2.3a Layer 1 — Per-resource structural validation
> "Is each YAML resource individually valid K8s?"
> Single-resource, offline. Already partially implemented.

###### General (all kinds)
- [x] Well-formed Deployment → `ok=True`, `errors=0`
- [x] Well-formed Service → `ok=True`, `errors=0`
- [x] Multi-document YAML with Deployment + Service → `files_checked >= 1`
- [x] Empty project → `ok=True`, zero files, zero errors
- [x] Missing `metadata.name` → error
- [x] Unparseable YAML → should not crash (file skipped, not counted as error)
- [x] Unusual apiVersion (not in `_K8S_API_VERSIONS`) → warning

###### Deployment-specific
- [x] Missing `spec.selector` → error
- [x] No containers in pod template → error
- [x] Missing `replicas` → warning (defaults to 1)
- [x] Missing `strategy` → info (defaults to RollingUpdate)

###### Service-specific
- [x] No `selector` → warning (headless without selector)
- [x] No `ports` → warning
- [x] Multi-port Service with unnamed ports → warning (K8s requires names for multi-port)

###### StatefulSet-specific
- [x] Missing `serviceName` → error (required by K8s API)
- [x] `serviceName` value present but empty string → error
- [ ] No `volumeClaimTemplates` when stateful data expected → info _(deferred — heuristic, not structural)_

###### Job-specific
- [x] `backoffLimit` negative → error
- [x] `completions` and `parallelism` both set and `parallelism > completions` → warning

###### CronJob-specific
- [x] Missing `schedule` → error
- [x] `schedule` not a valid cron expression (5-field) → error
- [x] `concurrencyPolicy` not in `[Allow, Forbid, Replace]` → warning

###### DaemonSet-specific
- [x] Has `replicas` field → warning (DaemonSet ignores replicas, runs on every node)

###### Ingress-specific
- [x] Missing `ingressClassName` and no default class annotation → warning (required K8s 1.22+)
- [x] Rule path without `pathType` → error (required K8s 1.22+)

###### HPA-specific
- [x] `minReplicas >= maxReplicas` → error
- [x] `scaleTargetRef.kind` not in scalable kinds (Deployment, StatefulSet, ReplicaSet) → error
- [x] Missing `metrics` section → warning (HPA without scaling criteria)

###### Pod spec (all workloads)
- [x] Container without `image` → `:latest` implicit warning
- [x] Image with `:latest` tag → warning
- [x] Image without any tag → `:latest` implicit warning
- [x] No `resources` → warning
- [x] `resources.limits` without `resources.requests` → warning (requests default to limits)
- [x] `resources.requests` without `resources.limits` → warning (no ceiling)
- [x] No `livenessProbe` → info
- [x] No `readinessProbe` → info
- [x] No `securityContext` → info

##### 0.2.3b Layer 2 — Cross-resource consistency
> "Do these resources work TOGETHER within the same manifest set?"
> Multi-resource, offline. This is where the control plane adds value
> that `kubectl apply --dry-run` doesn't give you.

- [x] **Service → Deployment selector**: Service's `spec.selector` labels match at least one Deployment's `spec.template.metadata.labels` → if not, warning "Service routes to nothing"
- [x] **Ingress → Service backend**: Ingress backend `service.name` references a Service defined in the manifest set → if not, warning "Ingress backend not found"
- [x] **Ingress → Service port**: Ingress backend `service.port.number` or `service.port.name` exists in the referenced Service's `spec.ports` → if not, warning "Ingress port mismatch"
- [x] **HPA → target reference**: HPA `scaleTargetRef.name` matches an existing Deployment/StatefulSet → if not, warning "HPA target not found"
- [x] **DaemonSet + HPA**: HPA targeting a DaemonSet → error "DaemonSet cannot be autoscaled"
- [x] **Env var → Secret existence**: `secretKeyRef.name` references a `kind: Secret` in manifests → if not, warning "Secret not defined in manifests"
- [x] **Env var → ConfigMap existence**: `configMapKeyRef.name` references a `kind: ConfigMap` in manifests → if not, warning "ConfigMap not defined in manifests"
- [x] **containerPort ↔ Service targetPort**: Service `targetPort` matches a `containerPort` declared in the target Deployment's containers → if not, warning "port mismatch"
- [x] **StatefulSet ↔ headless Service**: StatefulSet's `serviceName` references a Service with `clusterIP: None` → if not, error "StatefulSet requires headless Service"
- [x] **ServiceAccount reference**: `serviceAccountName` in pod spec references a `kind: ServiceAccount` defined in manifests → if not, info "ServiceAccount not defined (may exist on cluster)"
- [x] **Namespace consistency**: all resources in same namespace, or multiple namespaces with explicit `Namespace` resources → if mixed without intent, warning "mixed namespaces"
- [x] **Label orphans**: Deployment/StatefulSet with pod labels that no Service selects → info "pods may be unreachable"
- [x] **PVC reference**: Pod spec `persistentVolumeClaim.claimName` matches a defined PVC → if not, warning "PVC not defined in manifests"
- [x] **PVC access mode ↔ replica count**: `ReadWriteOnce` PVC used by Deployment with `replicas > 1` → error "RWO PVC cannot be shared across replicas"

##### 0.2.3c Layer 3 — Environment-aware validation
> "Is the deployment configuration correct for EACH environment?"
> Uses detection data from `k8s_env_namespaces()`, kustomize overlays,
> and Helm values files.

- [x] **Environment completeness**: project.yml defines N environments, but kustomize overlays exist for fewer → warning "missing overlay for env X"
- [x] **Helm values completeness**: `values-dev.yaml` exists but `values-prod.yaml` doesn't → warning "missing values file for env prod"
- [x] **Kustomize overlay validity**: each overlay's `kustomization.yaml` references base resources that exist on disk → if not, error "overlay references missing base"
- [x] **Kustomize patch targets**: patches reference resources (by kind/name) that exist in the base → if not, error "patch targets nonexistent resource"
- [x] **Prod replica sanity**: prod environment with `replicas: 1` and no HPA → warning "single replica in production"
- [x] **Dev resource oversizing**: dev environment with `replicas > 3` → info "high replica count for dev"
- [ ] **Secret coverage per env**: envsubst vars `${DB_PASSWORD}` referenced but no values source for a specific env → warning "env var not covered for env X" *(deferred — requires deeper per-env values tracking)*
- [x] **Namespace alignment**: environment's expected namespace (from `k8s_env_namespaces`) matches what kustomize overlay sets → if mismatch, warning

##### 0.2.3d Layer 4 — Cluster-aware validation
> "Will this WORK on THIS specific cluster?"
> Uses detection data from `cluster_status()`, `cluster_type`, and
> `tool_availability`. Only runs when cluster connection available.

- [x] **Service type ↔ cluster type**: `type: LoadBalancer` on Minikube/Kind → warning "LoadBalancer won't get external IP — use NodePort or tunnel"
- [x] **Ingress ↔ ingress controller**: Ingress resource defined but no ingress-controller in `infra_services` → warning "no ingress controller detected"
- [x] **cert-manager annotations ↔ cert-manager**: `cert-manager.io/` annotations but cert-manager not in `infra_services` → warning "cert-manager not detected"
- [x] **Prometheus CRDs ↔ Prometheus**: `ServiceMonitor` / `PrometheusRule` kinds but Prometheus not in `infra_services` → warning "Prometheus operator not detected"
- [x] **Tool ↔ strategy mismatch**: `deployment_strategy` is `helm` but `tool_availability.helm.available` is False → error "helm required but not installed"
- [x] **Tool ↔ strategy mismatch**: `deployment_strategy` is `kustomize` but kustomize not available → error "kustomize required but not installed"
- [x] **Namespace existence**: cluster connected, resource targets namespace `X`, cluster doesn't have namespace `X` → info "namespace does not exist on cluster (will need --create-namespace)"
- [x] **StorageClass existence**: PVC references `storageClassName: X`, cluster connected → check if class exists, warn if not
- [x] **CRD availability**: resource uses non-standard `kind` (not in `_K8S_KINDS`) → info "custom resource — ensure CRD is installed on cluster"
- [x] **kubectl version skew**: client version vs server version differ by more than 1 minor → warning "kubectl version skew"

##### 0.2.3e Layer 5 — Security & production readiness
> "Is this safe to deploy?"
> Goes beyond basic best-practice warnings into security posture.

###### Container security
- [x] `runAsUser: 0` (runs as root) → warning "container runs as root"
- [x] `securityContext.privileged: true` → error "privileged container"
- [x] `allowPrivilegeEscalation: true` or missing → warning "privilege escalation allowed"
- [x] Missing `capabilities.drop: ["ALL"]` → info "capabilities not explicitly dropped"
- [x] `readOnlyRootFilesystem` missing or false → info "writable root filesystem"
- [x] `hostNetwork: true` → warning "uses host network namespace"
- [x] `hostPID: true` → warning "uses host PID namespace"
- [x] `hostIPC: true` → warning "uses host IPC namespace"

###### Operational safety
- [x] `automountServiceAccountToken` not explicitly false on non-controller pods → info "token auto-mounted"
- [x] `livenessProbe` and `readinessProbe` have identical config → warning "same probe for liveness and readiness — may cause restart loops under load"
- [x] No `PodDisruptionBudget` for Deployments with `replicas >= 2` → info "no PDB for HA deployment"
- [x] `imagePullPolicy: Never` on cloud cluster → warning "image won't be pulled from registry"
- [x] No `NetworkPolicy` in namespace with Deployments → info "no network isolation"

###### RBAC
- [x] `ClusterRole` with wildcard verbs (`["*"]`) → warning "overly broad ClusterRole"
- [x] `ClusterRole` with wildcard resources (`["*"]`) → warning "overly broad ClusterRole"
- [x] `ClusterRoleBinding` binding to default ServiceAccount → warning "default SA should not have cluster-wide permissions"

##### 0.2.3f Layer 6 — Cross-domain validation (THE DIFFERENTIATOR)
> "Does the full DevOps pipeline fit together?"
> The control plane knows about Docker, K8s, Terraform, CI/CD, and
> environments. This layer validates the SEAMS between domains.
> 
> 5 integration domains = 10 unique seams + cross-cutting intelligence.
> Source of truth: Docker Compose spec, Kubernetes API, Terraform provider
> model, GitHub Actions workflow schema, project.yml environment model.

###### Docker ↔ K8s (9 checks)
- [x] **Image name alignment**: Compose `image:` or Dockerfile → K8s `containers[].image` should reference the same image (accounting for registry prefix and tag) → warning "K8s image reference does not match Docker build output"
- [x] **Port alignment**: Dockerfile `EXPOSE` ports and/or Compose `ports:` container port → K8s `containerPort` + Service `targetPort` should match → warning "Dockerfile exposes port X but K8s containerPort is Y"
- [x] **Environment variable coverage**: Compose `environment:` keys → K8s should have corresponding `env`, `envFrom`, ConfigMap, or Secret entries → info "compose env var X has no K8s equivalent"
- [x] **Volume pattern translation**: Compose named volumes → K8s should have corresponding PVC definitions → info "compose volume X has no K8s PVC equivalent"
- [x] **Service parity**: Compose services → K8s should have corresponding Deployments/StatefulSets (infra services like `db`, `redis` may be external) → info "compose service X has no K8s equivalent"
- [x] **Health check alignment**: Dockerfile `HEALTHCHECK` or Compose `healthcheck:` → K8s probes should use similar endpoints/commands → info "compose healthcheck defined but K8s has no matching probe"
- [x] **Image pull policy ↔ build locality**: Compose `build:` context (image built locally) + K8s `imagePullPolicy: Always` on cloud cluster → warning "locally-built image with Always pull policy on cloud — image won't be found on registry"
- [x] **Image pull secret ↔ private registry**: Image references private registry (not Docker Hub public) but no `imagePullSecrets` in pod spec → warning "private registry without imagePullSecrets"
- [x] **Service name continuity**: Compose services communicate by service name → K8s Services should provide equivalent DNS names for the same services → info "compose service name X not found as K8s Service name"

###### Docker ↔ CI/CD (5 checks)
- [x] **Dockerfile not built in CI**: Dockerfile present, CI pipeline detected (GitHub Actions), but no `docker build` step in any workflow → info "Dockerfile exists but CI does not build images"
- [x] **CI builds but doesn't push**: CI has docker build step but no push/registry step → warning "CI builds images but never pushes to registry"
- [x] **Registry login missing**: CI pushes to registry but no login step (docker/login-action or `docker login`) → warning "CI pushes images without registry authentication step"
- [x] **Multi-stage test target unused**: Dockerfile has test/builder stage (multi-stage), CI doesn't use `--target` for containerized tests → info "Dockerfile has test stage but CI doesn't use it"
- [x] **Compose for integration testing**: Compose defines test/dependency services, CI doesn't use `docker compose` → info "compose available but CI doesn't use it for integration testing"

###### Docker ↔ Terraform (2 checks)
- [x] **Registry provisioned ↔ image reference**: Terraform creates registry resource (`aws_ecr_repository`, `google_artifact_registry_repository`, `azurerm_container_registry`) → Docker/K8s image references should match that registry URL → warning "Terraform provisions registry X but images reference Y"
- [x] **No registry in IaC**: Docker images are built, cloud infra managed by Terraform, but no registry resource provisioned → info "Docker images built but no container registry in Terraform"

###### Docker ↔ Environments (2 checks)
- [x] **Compose override per environment**: project.yml defines N environments, only base compose file exists → info "project has N environments but no per-environment compose overrides"
- [x] **Env file reference validity**: Compose `env_file:` references file (e.g. `.env.production`) → file should exist on disk → warning "compose references env file X but file not found"

###### Terraform ↔ K8s (5 checks)
- [x] **Cloud cluster without IaC**: K8s manifests target cloud cluster type (EKS/GKE/AKS), no Terraform .tf files exist → info "cloud Kubernetes cluster but no infrastructure-as-code"
- [x] **Environment alignment**: Terraform workspaces ↔ K8s environments/namespaces (from `k8s_env_namespaces()` + project.yml) → info "Terraform workspace X has no corresponding K8s environment"
- [x] **Kubernetes provider conflict**: Terraform has `kubernetes` provider AND repo has raw K8s manifests → warning "Terraform kubernetes provider and raw manifests — risk of dual management conflict"
- [x] **Database connection gap**: Terraform provisions database resource (`aws_rds_instance`, `google_sql_database_instance`) → K8s should have Secret with connection details → info "Terraform provisions database but K8s has no connection Secret"
- [x] **IAM ↔ ServiceAccount alignment**: Terraform creates cloud IAM roles for K8s workload identity (IRSA, Workload Identity) → K8s ServiceAccounts should have corresponding annotations (`eks.amazonaws.com/role-arn`, etc.) → info "Terraform creates IAM role but no K8s ServiceAccount references it"

###### Terraform ↔ CI/CD (3 checks)
- [x] **IaC not in CI pipeline**: .tf files present, CI detected, but no `terraform` steps in any workflow → info "Terraform exists but infrastructure managed manually (no CI)"
- [x] **No plan-on-PR**: Terraform + CI exist but no `terraform plan` step on pull_request trigger → info "no infrastructure preview on pull requests"
- [x] **Apply without environment protection**: CI has `terraform apply` step targeting production but no GitHub environment protection rule → warning "unguarded Terraform apply to production"

###### Terraform ↔ Environments (2 checks)
- [x] **Workspace ↔ environment alignment**: project.yml defines environments, Terraform has workspaces → should correspond → info "project environment X has no Terraform workspace"
- [x] **Variable file coverage**: Terraform uses `.tfvars`, project has N environments → should have corresponding variable files → info "no Terraform variable file for environment X"

###### CI/CD ↔ K8s (5 checks)
- [x] **Deploy step existence**: K8s manifests exist, CI pipeline detected, but no deploy step (`kubectl apply`, `helm upgrade`, etc.) in any workflow → info "K8s manifests exist but CI has no deploy step"
- [x] **Image build→deploy chain**: K8s references container image, CI has deploy step but no image build+push before it → warning "CI deploys to K8s without building images first"
- [x] **Environment gates**: project has production environment, CI deploys to K8s → CI workflow should have `environment:` protection rules → info "CI deploys to production without environment protection"
- [x] **Deploy strategy ↔ CI tool alignment**: K8s deployment strategy is Helm, CI deploy step uses `kubectl apply` (not `helm upgrade`) → warning "K8s uses Helm but CI deploys with kubectl"
- [x] **Cluster credentials in CI**: CI has K8s deploy step but no kubeconfig/token in workflow secrets → warning "CI deploys to K8s but no cluster credentials configured"

###### CI/CD ↔ Environments (3 checks)
- [x] **CI environment coverage**: project.yml defines N environments, CI workflows only target a subset → info "no CI pipeline for environment X"
- [x] **Secret injection per environment**: environment requires specific secrets, CI workflow `env:` block doesn't inject them → warning "CI deploys to env X but doesn't inject required secrets"
- [x] **Production protection**: project has production environment, CI deploys to it → should have approval/review gates → info "CI deploys to production without approval gates"

###### Cross-cutting intelligence (3 checks)
- [x] **Version alignment**: language version in Dockerfile `FROM` (e.g. `python:3.12`) ↔ CI setup step (e.g. `setup-python@v5` with `python-version: '3.11'`) ↔ project config (`pyproject.toml` `requires-python`) → warning "Python version mismatch: Dockerfile uses 3.12, CI uses 3.11"
- [x] **Pipeline completeness**: has code + has Docker + has K8s BUT no CI → info "full deployment stack but no CI/CD automation". Has Docker + has CI BUT no K8s → info "containerized but no orchestration". Has K8s BUT no Docker → info "K8s manifests but no Dockerfile to build images"
- [x] **Secret flow integrity**: .env defines secrets → are they in CI workflow secrets? → are they referenced in K8s Secrets/ConfigMaps? → info "secret X defined in .env but not present in CI secrets" / "secret X in CI but not in K8s Secrets"


##### 0.2.3g Layer 7 — Deployment strategy validation
> "Is the chosen deployment method internally consistent?"
> Based on `deployment_strategy` detected in 0.2.2d-i.
> Source of truth: Helm Chart.yaml v2 spec, Kustomize kustomization.yaml spec,
> Skaffold v4beta schema spec, kubectl apply behavior, K8s API conventions.

###### Raw kubectl (8 checks)
- [x] **Unresolved envsubst variables**: manifests contain `${VAR}` patterns without documented envsubst process → warning "unresolved variable substitution"
- [x] **Missing Namespace manifest**: resource targets namespace X but no Namespace kind manifest exists in project → warning "namespace X referenced but not defined in manifests"
- [x] **CRD ordering gap**: Custom Resources of a CRD kind exist but no CRD manifest found → error "Custom Resource without CRD definition"
- [x] **Raw Secret with literal data**: Secret kind has `data:`/`stringData:` with literal values (not SealedSecret/ExternalSecret/SOPS) → warning "plaintext secrets in manifests"
- [x] **ConfigMap/Secret reference gap**: pod `envFrom`/`volumes` references ConfigMap/Secret name not defined in manifests → warning "referenced ConfigMap/Secret not found"
- [x] **Service selector mismatch**: Service `selector` labels don't match any Deployment/Pod labels in manifests → warning "Service selects no workloads"
- [x] **Ingress backend gap**: Ingress `backend.service.name` references Service not in manifests → warning "Ingress references missing Service"
- [x] **PVC StorageClass gap**: PVC specifies `storageClassName` but no StorageClass manifest exists (raw kubectl on bare metal) → info "StorageClass not in manifests"

###### Helm (13 checks)
- [x] **No templates directory**: Chart.yaml exists but `templates/` directory missing (application chart) → error "Helm chart without templates"
- [x] **No values.yaml**: chart directory has no `values.yaml` → warning "no default values file"
- [x] **Dependencies without lock**: Chart.yaml has `dependencies` but no `Chart.lock` → info "run helm dependency build"
- [x] **Deprecated apiVersion v1**: Chart.yaml uses `apiVersion: v1` (Helm 2 legacy format) → warning "deprecated Chart.yaml apiVersion v1"
- [x] **Library chart with non-helper templates**: `type: library` but `templates/` contains files not starting with `_` → warning "library chart has renderable templates"
- [x] **Orphaned subcharts**: `charts/` directory exists but Chart.yaml has no `dependencies` → info "subchart directory without declared dependencies"
- [x] **Missing required fields**: Chart.yaml missing `name` or `version` → error "Chart.yaml missing required field"
- [x] **Invalid SemVer version**: Chart.yaml `version` doesn't follow SemVer 2 → warning "chart version not valid SemVer"
- [x] **No .helmignore**: chart exists in project with >20 files but no `.helmignore` → info "no .helmignore — helm package will include everything"
- [x] **Missing NOTES.txt**: `templates/` has no `NOTES.txt` → info "no post-install notes for users"
- [x] **No _helpers.tpl**: `templates/` has no `_helpers.tpl` → info "no reusable template helpers defined"
- [x] **No values.schema.json**: chart has no `values.schema.json` for input validation → info "values not schema-validated"
- [x] **Local file:// dependency**: Chart.yaml dependency `repository` uses `file://` → warning "local dependency won't resolve in distributed chart"

###### Kustomize (10 checks)
- [x] **Missing resource file**: `resources:` entry references file that doesn't exist on disk → error "referenced resource file not found"
- [x] **Path traversal in resources**: `resources:` entry traverses outside project root (`../../../`) → error "resource path traversal outside project"
- [x] **Overlays without base**: `overlays/` directory exists but no `base/` directory → warning "overlays without base directory"
- [x] **Secret literals in kustomization**: `secretGenerator` uses `literals:` with secret-like values → warning "plaintext secrets in kustomization.yaml"
- [x] **Duplicate resource entry**: same file listed twice in `resources:` → error "duplicate resource entry"
- [x] **Patch targets missing resource**: patch targets kind+name not found in declared `resources:` → warning "patch targets non-existent resource"
- [x] **Deprecated bases field**: `bases:` field used instead of listing dirs in `resources:` → info "bases is deprecated — use resources"
- [x] **commonLabels immutability risk**: `commonLabels` used (propagates to selector.matchLabels which are immutable) → info "commonLabels can break rolling updates if changed"
- [x] **Missing components directory**: `components:` references directory that doesn't exist → error "component directory not found"
- [x] **Namespace override conflict**: `namespace:` transformer set but resources already have hardcoded namespaces → info "namespace transformer may conflict with hardcoded namespaces"

###### Skaffold (7 checks)
- [x] **Missing manifest file**: `manifests.rawYaml` references file that doesn't exist → error "skaffold references missing manifest"
- [x] **Missing Dockerfile**: `build.artifacts` references Dockerfile that doesn't exist → error "skaffold build references missing Dockerfile"
- [x] **Deprecated apiVersion**: apiVersion is pre-v2 or pre-v3alpha (significantly outdated) → warning "deprecated skaffold apiVersion"
- [x] **No deploy or manifests section**: neither `deploy` nor `manifests` section present → warning "skaffold has no deployment configuration"
- [x] **Build without deploy**: `build` section defined but no `deploy` section → warning "skaffold builds images but doesn't deploy"
- [x] **Empty default pipeline**: all config lives in `profiles`, default pipeline empty → info "default pipeline requires --profile to deploy"
- [x] **Non-reproducible tag policy**: `tagPolicy` uses `sha256` or `latest` → info "non-reproducible image tags — consider gitCommit or inputDigest"

###### Mixed strategy coherence (5 checks)
- [x] **Duplicate resource across strategies**: same resource (kind+name+namespace) in raw manifests AND Helm chart → warning "duplicate resource across deployment strategies"
- [x] **Orphaned manifests alongside Kustomize**: manifests in same directory as kustomization.yaml but not listed in `resources:` → warning "manifest not managed by Kustomize — may be stale"
- [x] **Mixed strategy undocumented**: `deployment_strategy: mixed` but no README/docs explaining the relationship → info "multiple deployment strategies with no documentation"
- [x] **Helm + Kustomize without orchestrator**: both Helm charts and Kustomize active but no Skaffold/ArgoCD/Flux to orchestrate → info "multiple deployment tools without orchestrator"
- [x] **Skaffold dual deployers**: Skaffold uses both helm and rawYaml deployers targeting same namespace → warning "skaffold deploys via multiple strategies to same namespace"

#### 0.2.4 Simple Generation — template-based (`k8s_generate.py`)
- [x] `generate_manifests` produces Deployment + Service files
- [x] Deployment content is valid YAML
- [x] Service content is valid YAML
- [x] Custom replicas reflected in Deployment
- [x] Custom service_type (ClusterIP/NodePort/LoadBalancer) reflected in Service
- [x] With namespace → Namespace manifest generated, placed first
- [x] With host → Ingress manifest generated
- [x] Without host → no Ingress
- [x] Default image → `{app_name}:latest`
- [x] Generated Deployment has resource limits (cpu/memory)
- [x] Generated Deployment has livenessProbe + readinessProbe
- [x] Generated Deployment has securityContext (runAsNonRoot, no privilege escalation)
- [x] Generated Deployment has RollingUpdate strategy
- [x] Generated files placed under k8s/ directory

#### 0.2.5 Pod Builder — shared across generators (`k8s_pod_builder.py`)

##### `_build_probe`
- [x] HTTP probe with all timing fields (initialDelay, period, failureThreshold)
- [x] TCP probe with port only
- [x] Exec probe wraps command in `sh -c`
- [x] Exec probe with no command → fallback to `/bin/true`
- [x] HTTP probe with no args → defaults (path=/health, port=8080)
- [x] Timing values of 0 → omitted from output

##### `_build_wizard_volume`
- [x] PVC-dynamic volume → persistentVolumeClaim with svc-prefixed claim
- [x] PVC-static volume → same structure as dynamic (uses existing PVC)
- [x] EmptyDir with Memory medium and sizeLimit
- [x] EmptyDir without medium → default emptyDir (empty spec)
- [x] ConfigMap volume with key → subPath on mount
- [x] ConfigMap volume without key → mount entire ConfigMap as directory
- [x] Secret volume with key → subPath on mount
- [x] Secret volume without key → mount entire Secret as directory
- [x] HostPath volume with type
- [x] HostPath volume without type → type omitted (K8s: no check performed)
- [x] No mountPath → returns (None, None)
- [x] Unknown volume type → returns (None, None)
- [x] PVC volume with no name → name derived from index
- [x] ReadOnly flag → mount has readOnly=true
- [x] ReadOnly absent when not set → no readOnly key in mount

##### `_build_pod_template`
- [x] Main container with image, ports, resources, probes
- [x] Default image → `{name}:latest` when none provided
- [x] No port → no ports array in container
- [x] Command/args override → `command: ["sh", "-c", cmd]` (Job/CronJob pattern)
- [x] Resource limits only set when provided (not empty resources block)
- [x] Env vars wired to main container
- [x] envFrom bulk refs (ConfigMap/Secret) wired to main container
- [x] Init containers → `initContainers` field in pod spec, command wrapped in `sh -c`
- [x] Sidecar native (K8s ≥ 1.28) → initContainers with `restartPolicy: Always`
- [x] Sidecar non-native → added to `containers[]` alongside main
- [x] Sidecar shared volume → emptyDir created, mounted in both sidecar and main
- [x] Companion containers → multiple containers in same pod with ports + env + resources
- [x] Companion startup dependency → wait-for init container with `nc -z`
- [x] Companion volume mounts → pod-level volumes + container volumeMounts
- [x] Volumes from wizard config → `volumes` + `volumeMounts` matched by name
- [x] Volume name deduplication → same name not added twice
- [x] Mesh annotations → pod template `metadata.annotations`
- [x] Mesh absent → no annotations key on template metadata
- [x] Host access config → hostNetwork, hostPID, hostIPC fields
- [x] Host access absent by default → no hostNetwork/hostPID/hostIPC keys
- [x] VolumeClaimTemplates → volumeMounts on main container, NOT in pod volumes

##### `_build_env_vars`
- [x] Dict input → simple name/value pairs
- [x] Dict input values stringified (int → str per K8s EnvVar.value spec)
- [x] List with explicit `secretName` → `secretKeyRef`
- [x] List secretKey defaults to env name when omitted
- [x] List with explicit `configMapName` → `configMapKeyRef`
- [x] Wizard format `type=secret` + `svc_name` → `{svc}-secrets` reference
- [x] Wizard format `type=secret` without `svc_name` → fallback derivation from varName
- [x] Wizard format `type=variable` + `svc_name` → `{svc}-config` reference
- [x] Wizard format `type=hardcoded` → inline value
- [x] Empty/falsy input → empty list
- [x] Non-list non-dict input → empty list
- [x] Items missing both `name` and `key` → skipped
- [x] `key` field accepted as alias for `name`

##### `_build_mesh_annotations`
- [x] Istio mesh → `sidecar.istio.io/inject: true`
- [x] Linkerd mesh → `linkerd.io/inject: enabled` (not "true")
- [x] Consul mesh → `consul.hashicorp.com/connect-inject: true`
- [x] Kuma mesh → `kuma.io/sidecar-injection` annotation
- [x] Istio proxy resource annotations (proxyCPU, proxyMemory)
- [x] Linkerd proxy resource annotations (different keys than Istio)
- [x] Log level annotation (provider-specific key)
- [x] Exclude inbound/outbound ports annotations
- [x] No provider → empty annotations
- [x] Unknown provider → falls back to Istio prefixes

##### `_api_version_for_kind`
- [x] Deployment → apps/v1
- [x] StatefulSet → apps/v1
- [x] DaemonSet → apps/v1
- [x] ReplicaSet → apps/v1
- [x] Job → batch/v1
- [x] CronJob → batch/v1
- [x] Ingress → networking.k8s.io/v1
- [x] NetworkPolicy → networking.k8s.io/v1
- [x] HorizontalPodAutoscaler → autoscaling/v2
- [x] Service → v1
- [x] Unknown kind → v1 (fallback)

#### 0.2.6 Wizard Translator (`k8s_wizard.py`)

##### `_svc_env_to_resources`
- [x] Hardcoded env vars → ConfigMap resource
- [x] Secret env vars → Secret resource with placeholder values
- [x] Mix of hardcoded + secret → both ConfigMap and Secret
- [x] Variable env vars → ConfigMap with varName as value
- [x] Empty env vars → no resources
- [x] Non-dict items in env list → skipped silently
- [x] Items without `key` field → skipped silently
- [x] ConfigMap name convention → `{svc}-config`
- [x] Secret name convention → `{svc}-secrets`
- [x] Return tuple shape → (resources, has_config, has_secrets)

##### `_svc_volumes_to_pvc_resources`
- [x] PVC-dynamic volume → PVC resource with storageClass and size
- [x] PVC-static volume → PVC with volumeName
- [x] PVC with storageClass preserved
- [x] EmptyDir and non-PVC volumes → no PVC resources
- [x] Default accessMode → ReadWriteOnce when not specified
- [x] Default storage size → 10Gi when not specified
- [x] Longhorn annotations → longhornConfig passed through to PVC spec

##### `wizard_state_to_resources`
- [x] Single app service → Deployment + Service resources
- [x] Multiple services → all produce Deployment + Service
- [x] Non-default namespace → Namespace resource created
- [x] `namespace=default` → no Namespace resource
- [x] Service with env vars → ConfigMap + Secret resources + envFrom wiring
- [x] Service with probes → probes in resource spec
- [x] Service with resource limits → limits in spec
- [x] StatefulSet → headless Service + serviceName set
- [x] StatefulSet extras → podManagementPolicy + partition forwarded
- [x] Job with backoffLimit, completions, parallelism
- [x] CronJob with schedule and concurrency policy
- [x] DaemonSet extras → nodeSelector + tolerations forwarded
- [x] HPA autoscaling → HorizontalPodAutoscaler resource with targets
- [x] Sidecars / initContainers / companions → passthrough to spec
- [x] Command/args override → passthrough to spec
- [x] Service type → ClusterIP / NodePort / LoadBalancer on K8s Service resource
- [x] Mesh annotations → spec.annotations when mesh.enabled
- [x] Infra service `kind=Skip` → no resources
- [x] Infra service `kind=Managed` → Managed placeholder resource
- [x] Ingress host set → Ingress resource with backend
- [x] Ingress with multiple services → multi-path rules
- [x] No ingress host → no Ingress resource
- [x] Every resource has namespace field set
- [x] Custom output_dir propagated to all resources
- [x] Deployment strategy forwarded to spec
- [x] Infra services (isInfra=True) → own Deployment + Service
- [x] Infra Postgres with PVC → PVC resource created
- [x] Infra service kind override (e.g., StatefulSet)

##### `_sanitize_state`
- [x] Transient/detection fields removed (_appServices, _infraServices, _classifiedModules, etc.)
- [x] Sanitized state includes `_savedAt` and `_version`
- [x] `_compose` key removed from each service

#### 0.2.7 Wizard Generation — resources → YAML files (`k8s_wizard_generate.py`)

##### `generate_k8s_wizard`
- [x] Deployment resource → valid YAML with correct structure (apiVersion, kind, selector, replicas, strategy, template)
- [x] Deployment template metadata.labels.app matches selector.matchLabels for pod selection
- [x] Service resource → correct port, targetPort, selector, type
- [x] Headless Service → clusterIP: None for StatefulSet backing
- [x] ConfigMap resource → apiVersion v1, data keys at top level (not under spec)
- [x] Secret resource → apiVersion v1, stringData, type Opaque
- [x] Ingress resource → networking.k8s.io/v1, rules with host, pathType, backend.service.port.number
- [x] Ingress multi-path rules → _paths expanded into rules[0].http.paths
- [x] PVC resource → accessModes, resources.requests.storage, storageClassName
- [x] PVC volumeName for pvc-static binding
- [x] Namespace resource → apiVersion v1, no namespace in metadata
- [x] Empty resource list → error
- [x] Managed kind → no manifest file produced (skipped)
- [x] Output dir reflected in file paths
- [x] File naming convention → `{output_dir}/{name}-{kind.lower()}.yaml`
- [x] Deployment strategy in generated YAML (RollingUpdate with rollback params)
- [x] Multiple resources → multiple file entries
- [x] StatefulSet → apps/v1, serviceName, selector, VCTs with accessModes+storage+storageClassName
- [x] DaemonSet → apps/v1, no replicas, nodeSelector + tolerations in pod template
- [x] Job → batch/v1, backoffLimit default 4, restartPolicy Never
- [x] CronJob → batch/v1, schedule, concurrencyPolicy, nested jobTemplate.spec.template
- [x] HPA → autoscaling/v2, scaleTargetRef, minReplicas, maxReplicas, targetCPU

##### `_generate_skaffold`
- [x] Skaffold disabled → None
- [x] Skaffold enabled → valid skaffold.yaml content
- [x] Skaffold rawYaml includes all generated manifest paths

#### 0.2.8 Wizard State Persistence
- [x] `save_wizard_state` + `load_wizard_state` round-trip
- [x] `load_wizard_state` on nonexistent file → `{ok: False, reason: "not_found"}`
- [x] `load_wizard_state` on corrupt JSON → `{ok: False, reason: "invalid"}`
- [x] `load_wizard_state` returns state fields merged with `ok: True`
- [x] `save_wizard_state` creates k8s/ dir if it doesn't exist
- [x] `save_wizard_state` with empty state → error (no _services, no _infraDecisions)
- [x] `save_wizard_state` returns correct path `k8s/.wizard-state.json`
- [x] `wipe_wizard_state` removes state file
- [x] `wipe_wizard_state` on nonexistent file → ok (no crash)
- [x] Sanitization strips transient fields on save (through persistence path)
- [x] Core fields preserved through save/load cycle (_services, namespace, ingress, etc.)

#### 0.2.9 Skaffold Detection (`k8s_wizard_detect.py`)
- [x] Empty project → `has_skaffold=False`, `configs=[]`
- [x] skaffold.yaml present → detected with path
- [x] skaffold.yml present → detected
- [x] Both skaffold.yaml and skaffold.yml → both detected
- [x] Profiles section → profile names extracted
- [x] Profile entries without name → skipped
- [x] No profiles section → empty profiles list
- [x] Malformed YAML → still detected with empty fields
- [x] Non-dict YAML → still detected, `api_version=""`
- [x] Skaffold CLI present → `available=True`
- [x] Skaffold CLI absent → `available=False`
- [x] apiVersion parsed from config

#### 0.2.10 Environment Namespaces (`k8s_wizard_detect.py`)
- [x] No project.yml → empty environments list
- [x] project.yml with no environments → empty list
- [x] Namespace follows `project-name-envname` convention
- [x] Environment names preserved from project.yml
- [x] Default flag propagated
- [x] k8s/overlays/{env} directory → `has_overlay=True`
- [x] k8s/envs/{env} directory → `has_overlay=True`
- [x] kubernetes/overlays/{env} → `has_overlay=True`
- [x] deploy/overlays/{env} → `has_overlay=True`
- [x] k8s/overlays/ checked first (priority)
- [x] Multiple envs with mixed overlays
- [x] Helm values file detected (values-{env}.yaml, values.{env}.yaml, etc.)

#### 0.2.11 Cluster Operations (`k8s_cluster.py`) — online, mocked
- [x] `cluster_status` → connected, context, nodes, namespaces (pre-existing integration test)
- [x] `cluster_status` when kubectl fails → `connected=False` (pre-existing mock test)
- [x] `get_resources` → resources list with name, namespace, phase, conditions
- [x] `get_resources` with namespace filter → passed to kubectl `-n`
- [x] `get_resources` with kind filter (pods, deployments, services, etc.)
- [x] `get_resources` kubectl not available → error
- [x] `k8s_pod_logs` → pod log output with tail limit
- [x] `k8s_pod_logs` with container filter → `-c` arg passed
- [x] `k8s_pod_logs` on missing pod name → error (input validation)
- [x] `k8s_pod_logs` kubectl failure → error dict
- [x] `k8s_apply` with file path → applies manifest, returns output
- [x] `k8s_apply` with namespace override → `-n` arg appended
- [x] `k8s_apply` on failure → error dict
- [x] `k8s_apply` path not found → error
- [x] `k8s_delete_resource` → deletes by kind + name, returns output
- [x] `k8s_delete_resource` with namespace → `-n` arg passed
- [x] `k8s_delete_resource` missing kind or name → error (input validation)
- [x] `k8s_scale` → scales deployment/statefulset, returns output
- [x] `k8s_scale` with kind override → `{kind}/{name}` format
- [x] `k8s_scale` missing name → error (input validation)
- [x] `k8s_events` → events list with type, reason, object, message, count
- [x] `k8s_events` with namespace filter
- [x] `k8s_events` kubectl failure → error dict
- [x] `k8s_describe` → description string for kind/name
- [x] `k8s_describe` on missing kind/name → error (input validation)
- [x] `k8s_namespaces` → list with name, status, created
- [x] `k8s_storage_classes` → list with name, provisioner, is_default, reclaim_policy
- [x] `k8s_storage_classes` identifies default class via annotation
- [x] `_summarize_conditions` → condensed condition summary string (pure logic, tested below)
- [x] `_detect_cluster_type` → cluster type detection (pre-existing integration tests)

#### 0.2.12 Helm Operations (`k8s_helm.py`) — online, mocked
- [x] `_helm_available` → True when helm CLI present
- [x] `_helm_available` → False when helm CLI absent
- [x] `helm_list` → releases list with name, namespace, revision, status, chart, app_version
- [x] `helm_list` when helm not available → `{available: False, error: "helm CLI not found"}`
- [x] `helm_list` with namespace filter
- [x] `helm_list` without namespace → `--all-namespaces`
- [x] `helm_list` on failure → error in result but available=True
- [x] `helm_values` → YAML string of values for a release
- [x] `helm_values` when helm not available → error
- [x] `helm_values` on missing release → error
- [x] `helm_install` → installs chart with release name
- [x] `helm_install` with namespace → `--create-namespace`
- [x] `helm_install` with values_file → `--values`
- [x] `helm_install` with set_values → `--set k=v`
- [x] `helm_install` with dry_run → `--dry-run`
- [x] `helm_install` when helm not available → error
- [x] `helm_install` on failure → error dict
- [x] `helm_upgrade` → upgrades release with `--install`
- [x] `helm_upgrade` with namespace/values/set/dry_run args
- [x] `helm_upgrade` when helm not available → error
- [x] `helm_template` → renders YAML locally (no cluster)
- [x] `helm_template` with namespace + values_file
- [x] `helm_template` when helm not available → error
- [x] `helm_template` on failure → error dict

#### 0.2.13 Workload Kinds (advanced wizard)
- [x] `kind=StatefulSet` → StatefulSet resource produced, not Deployment (pre-existing)
- [x] StatefulSet has `serviceName` referencing headless Service (pre-existing)
- [x] StatefulSet template labels match selector (K8s spec: pods MUST match selector)
- [x] `kind=DaemonSet` → DaemonSet resource, no replicas field (pre-existing)
- [x] `kind=Job` → Job resource with backoffLimit and restartPolicy (pre-existing)
- [x] `kind=CronJob` → CronJob resource with schedule and jobTemplate (pre-existing)
- [x] Multiple services with different kinds → correct resource types per kind
- [x] No kind specified → defaults to Deployment (project scope requirement)

#### 0.2.14 Multi-Container Pods (advanced wizard)
_Source of truth: K8s PodSpec, Container spec (v1), `_build_pod_template`_
- [x] Sidecar (native, default) → `initContainers` with `restartPolicy: Always` (K8s ≥1.28)
- [x] Sidecar (non-native, `nativeSidecar: false`) → `containers[]` alongside main
- [x] Sidecar main container still `containers[0]` after sidecar addition
- [x] Sidecar shared volume → emptyDir auto-created, mounted in BOTH main and sidecar
- [x] Init container → `initContainers` list with `name`, `image`, `command`
- [x] Init container command → wrapped in `["sh", "-c", cmd]`
- [x] Multiple init containers → ordered list in `initContainers`
- [x] Companion container → `containers[]` with name, image, port
- [x] Companion env vars → env list on companion container
- [x] Companion resource limits → resources block on companion container
- [x] Companion volume mounts → pod-level volumes + container volumeMounts
- [x] Companion startup dependency (`dependsOn`) → wait-for init container with `nc -z`
- [x] Volume deduplication → same volume name NOT added twice to `volumes[]`
- [x] VCT volumeMounts → main container has mount, VCT NOT in pod `volumes[]` (K8s auto-injects)
- [x] No sidecar/init/companion → no `initContainers` key at all (absent, not empty)
- [x] Multiple volumes on one service → all volumes[] and volumeMounts match by name (K8s invariant)

#### 0.2.15 Infrastructure Services

> **Scope:** "Infrastructure services" appears at two distinct levels in the tool:
>
> **Level 1 — Detection** (`k8s_detect._detect_infra_services`): Scans *existing*
> manifests and Helm charts to identify cluster-level infrastructure requirements
> (ingress controllers, cert-manager, monitoring, service mesh, storage, secrets).
> Three detection sources: resource kinds, annotations, Helm chart names.
>
> **Level 2 — Generation** (`k8s_wizard.wizard_state_to_resources`): Generates *new*
> K8s resources for application-level infrastructure (Redis, Postgres, RabbitMQ)
> declared via `_infraDecisions` in wizard state. These follow the same translation
> pipeline as app services: env vars → ConfigMap/Secret, volumes → PVC, workload → Deployment/StatefulSet.
>
> Source of truth: K8s API (Deployment, StatefulSet, Service, PVC, ConfigMap, Secret specs)
> + project scope (the tool must handle both detection paths and all wizard-level infra patterns).

##### 0.2.15a Detection — kubectl infra (resource kinds + annotations)
- [x] `Ingress` resource in manifests → `ingress-controller` detected (`detected_via: resource_kind`)
- [x] `Certificate` resource → `cert-manager` detected
- [x] `ServiceMonitor` resource → `prometheus` detected
- [x] `Gateway` resource → `gateway-api` detected
- [x] Annotation `cert-manager.io/*` → `cert-manager` detected (`detected_via: manifest_annotation`)
- [x] Annotation `prometheus.io/*` → `prometheus` detected
- [x] Annotation `nginx.ingress.kubernetes.io/*` → `ingress-nginx` detected
- [x] No infra-implying resources or annotations → empty infra list
- [x] Duplicate detection (same infra from kind + annotation) → deduplicated

##### 0.2.15b Detection — helm infra (chart name matching)
- [x] Helm chart named `ingress-nginx` → detected (`detected_via: helm_chart`)
- [x] Helm chart named `cert-manager` → detected
- [x] Helm chart named `prometheus` / `kube-prometheus-stack` → detected
- [x] Helm chart named `vault` / `sealed-secrets` / `external-secrets` → detected
- [x] Helm chart named `istio` / `linkerd` → detected
- [x] Helm chart named `longhorn` / `rook-ceph` → detected
- [x] Helm chart named `argo-cd` / `flux` → detected
- [x] Non-infra Helm chart (e.g., `my-app`) → NOT classified as infra
- [x] Mixed detection (kubectl kind + helm chart) → both sources merged, deduplicated

##### 0.2.15c Wizard decisions (`_infraDecisions`)
- [x] `kind: Skip` → no resources generated (external/cloud-managed service)
- [x] `kind: Managed` → `Managed` placeholder resource (marker only, no workload)
- [x] `kind: Deployment` (default) → Deployment + Service resources
- [x] `kind: StatefulSet` → StatefulSet + headless Service + regular Service

##### 0.2.15d Generation — infra workload resources
- [x] Infra service → own Deployment (separate from app, not merged into app pod)
- [x] Infra service with port → own ClusterIP Service with correct `selector`, `port`, `targetPort`
- [x] Infra service without port → no Service resource (negative test)
- [x] Infra + app service → both produce independent Deployments + Services (no merging)
- [x] Infra service `kind: StatefulSet` → headless Service Auto-generated with `clusterIP: None`
- [x] Infra service `kind: StatefulSet` → `serviceName` references headless Service

##### 0.2.15e Generation — infra env var wiring
- [x] Infra service with hardcoded env vars → ConfigMap resource (`{svc}-config`)
- [x] Infra service with secret env vars → Secret resource (`{svc}-secrets`)
- [x] Infra service with mixed env vars → both ConfigMap and Secret created
- [x] ConfigMap/Secret names follow `{svc}-config` / `{svc}-secrets` convention
- [x] `envFrom` on workload spec references ConfigMap and Secret by name

##### 0.2.15f Generation — infra PVC / volumes
- [x] pvc-dynamic volume → PVC resource with `accessModes`, `storage` size
- [x] PVC default `accessMode` → `ReadWriteOnce` when not specified
- [x] PVC default storage size → `10Gi` when not specified
- [x] PVC with `storageClass` → preserved in PVC spec
- [x] pvc-static volume → PVC with `volumeName` binding to existing PV
- [x] Longhorn config → `longhornConfig` passthrough on PVC spec
- [x] Non-PVC volume types (emptyDir, configMap, secret) → no PVC resource (negative test)
- [x] StatefulSet infra with PVC → `volumeClaimTemplates` in StatefulSet spec (not standalone PVC)

#### 0.2.16 HPA (Autoscaler)

> **Scope:** The tool generates `HorizontalPodAutoscaler` resources for any
> service with `autoscaling.enabled=True`. The HPA must correctly reference
> the target workload (Deployment or StatefulSet), use `autoscaling/v2` API,
> and translate wizard state fields into the correct HPA spec structure.
>
> Source of truth: K8s `autoscaling/v2` HPA spec + `wizard_state_to_resources` translation.

##### 0.2.16a HPA resource generation
- [x] `autoscaling.enabled=True` → HPA resource created alongside the workload
- [x] `autoscaling.enabled` absent or false → no HPA resource (negative test)
- [x] HPA YAML `apiVersion` is `autoscaling/v2` (not v1 or v2beta)
- [x] HPA resource name follows `{svc}-hpa` convention

##### 0.2.16b HPA scaleTargetRef
- [x] `scaleTargetRef.name` matches the service's workload name
- [x] `scaleTargetRef.kind` matches the workload kind (Deployment by default)
- [x] `scaleTargetRef.apiVersion` is `apps/v1`
- [x] StatefulSet service with HPA → `scaleTargetRef.kind` is `StatefulSet`

##### 0.2.16c HPA metrics
- [x] `minReplicas` from `autoscaling.minReplicas` (defaults to 1)
- [x] `maxReplicas` from `autoscaling.maxReplicas` (defaults to 10)
- [x] `targetCPU` → `targetCPUUtilizationPercentage` in HPA spec
- [x] `targetMemory` → `targetMemoryUtilizationPercentage` in HPA spec
- [x] No `targetCPU` specified → field absent from HPA spec (not zero)

#### 0.2.17 Setup_K8s Integration (round-trip)
> **Scope:** `setup_k8s` is the round-trip pipeline: wizard state → `wizard_state_to_resources`
> → `generate_k8s_wizard` → disk. It creates directories, writes files, optionally generates
> skaffold.yaml, handles overwrite protection, records activity events, and must produce
> output that passes validation and is detected by `k8s_status`.
>
> Source of truth: `wizard_setup.setup_k8s` implementation + K8s manifest structure + cross-layer contracts.

##### 0.2.17a File writing pipeline
- [x] Simple wizard state → files written to `k8s/` directory
- [x] `k8s/` directory created automatically via `mkdir(parents=True, exist_ok=True)`
- [x] Each resource → separate YAML file named `{name}-{kind}.yaml`
- [x] File already exists & `overwrite=False` → file skipped (not overwritten)
- [x] Skipped files listed in `files_skipped` response key
- [x] Generator error → `{ok: False, error: ...}` returned, no files written

##### 0.2.17b Resource type coverage
- [x] Wizard state with env vars → ConfigMap YAML file created
- [x] Wizard state with secret env vars → Secret YAML file created
- [x] Wizard state with non-default namespace → Namespace resource file created
- [x] Wizard state with ingress host → Ingress resource file created
- [x] Wizard state with PVC volume → PVC resource file created
- [x] Multiple services → all Deployments + Services + ConfigMaps/Secrets created

##### 0.2.17c Skaffold integration in setup
- [x] `skaffold=True` in wizard state → skaffold.yaml generated and written alongside manifests
- [x] `skaffold=False` or absent → no skaffold.yaml written

##### 0.2.17d Cross-layer validation
- [ ] Generated output passes `validate_manifests` (valid K8s structure)
- [x] Generated output detected by `k8s_status` (manifest scanning)
- [x] Activity event recorded (`devops_cache.record_event`) after setup

#### 0.2.18 Delete Config

> **Scope:** `delete_generated_configs` removes wizard-generated configuration
> directories and files. Supports multiple targets (`docker`, `k8s`, `ci`, `terraform`, `all`).
> Must be idempotent and integrate with activity logging.
>
> Source of truth: `wizard_setup.delete_generated_configs` + filesystem expectations.

##### 0.2.18a K8s delete
- [x] `delete_generated_configs('k8s')` → `k8s/` directory removed via `shutil.rmtree`
- [x] No `k8s/` directory → nothing deleted, no error (idempotent)
- [x] `deleted` response includes `"k8s/"` when directory existed

##### 0.2.18b Multi-target delete
- [x] `target='all'` → deletes docker, k8s, ci, terraform in sequence
- [x] Unknown target → error in `errors` list, `ok: False`
- [x] Filesystem error during delete → captured in `errors`, not raised

##### 0.2.18c Round-trip verification
- [x] Setup → delete → `k8s_status` shows nothing (no manifests detected)
- [x] Setup → delete → setup again → files recreated (not blocked by stale state)
- [x] Activity event recorded after delete (`devops_cache.record_event`)

#### 0.2.19 Skaffold Integration (wizard)

> **Scope:** `_generate_skaffold` builds a `skaffold.yaml` from wizard state,
> and `skaffold_status` detects existing Skaffold configs on disk. The generated
> config must conform to the Skaffold v4beta11 schema (`apiVersion`, `kind: Config`,
> `metadata`, `build.artifacts`, `manifests.rawYaml`, `deploy.kubectl`).
>
> Source of truth: Skaffold v4beta11 schema + `_generate_skaffold` + `skaffold_status`.

##### 0.2.19a Generation — gate logic
- [x] `skaffold=True` in wizard state → skaffold file dict returned (not None)
- [x] `skaffold=False` → `None` returned (no file)
- [x] `skaffold` key absent → `None` returned (no file)
- [x] `overwrite` field on returned dict is `False` (skip existing)

##### 0.2.19b Generation — Skaffold document structure
- [x] `apiVersion` is `skaffold/v4beta11` (current stable)
- [x] `kind` is `Config`
- [x] `metadata.name` is first service's name when services exist
- [x] `metadata.name` defaults to `"app"` when no services
- [x] Output is valid YAML (round-trip parse succeeds)
- [x] Output file path is `"skaffold.yaml"` (root, not in k8s/)

##### 0.2.19c Generation — build artifacts
- [x] Each non-Skip service with image → build artifact entry
- [x] Artifact `image` matches service image string exactly
- [x] Artifact `context` is `"."` (build context = project root)
- [x] `kind: Skip` service → excluded from artifacts
- [x] Service with empty image → excluded from artifacts
- [x] No eligible services → no `build` section in output
- [x] Multiple services → multiple artifacts in build section

##### 0.2.19d Generation — manifests & deploy
- [x] Generated K8s YAML paths → listed in `manifests.rawYaml`
- [x] Non-YAML files excluded from manifest list
- [x] No generated manifests → fallback glob `{output_dir}/*.yaml`
- [x] Custom `output_dir` reflected in fallback glob path
- [x] `deploy.kubectl` section present (empty dict — kubectl deployer)

##### 0.2.19e Detection — `skaffold_status`
- [x] No skaffold files → `has_skaffold=False`, empty configs
- [x] `skaffold.yaml` present → detected, included in configs
- [x] `skaffold.yml` present → detected (both variants)
- [x] Profiles section parsed → profile names extracted
- [x] Profiles without `name` key → skipped (no crash)
- [x] No profiles section → empty profiles list
- [x] `apiVersion` extracted from config
- [x] Malformed YAML → config still detected, fields empty/default
- [x] After wizard setup with `skaffold=True` → `skaffold_status()` detects it

#### 0.2.20 Env Var Wiring (integration)

> **Scope:** `_build_env_vars` translates wizard env var definitions into K8s
> container `env` entries. It supports multiple input formats (dict, classic K8s
> list, wizard frontend format) and wires `valueFrom` references to ConfigMap/Secret
> resources generated by `_svc_env_to_resources`. When `svc_name` is provided,
> references use the `{svc_name}-config` / `{svc_name}-secrets` convention.
>
> Source of truth: K8s `container.env` spec + `_build_env_vars` + `_svc_env_to_resources`.

##### 0.2.20a Input format handling
- [x] Dict input `{KEY: value}` → list of `{name: KEY, value: value}`
- [x] List of `{name, value}` (classic K8s format) → passthrough
- [x] Empty/None input → empty list
- [x] Non-dict items in list → silently skipped
- [x] Items missing both `name` and `key` → silently skipped

##### 0.2.20b Classic K8s format references
- [x] `{name, secretName}` → `valueFrom.secretKeyRef.name` = secretName
- [x] `{name, secretName, secretKey}` → `valueFrom.secretKeyRef.key` = secretKey
- [x] `{name, secretName}` without secretKey → key defaults to env name
- [x] `{name, configMapName}` → `valueFrom.configMapKeyRef.name` = configMapName
- [x] `{name, configMapName, configMapKey}` → `valueFrom.configMapKeyRef.key` = configMapKey
- [x] `{name, configMapName}` without configMapKey → key defaults to env name

##### 0.2.20c Wizard format — type-based routing
- [x] `type: hardcoded` → inline `value` string in env entry
- [x] `type: secret` with `svc_name` → `secretKeyRef.name` = `{svc_name}-secrets`
- [x] `type: secret` without `svc_name` → `secretKeyRef.name` derived from varName/env name
- [x] `type: variable` with `svc_name` → `configMapKeyRef.name` = `{svc_name}-config`
- [x] `type: variable` without `svc_name` → `configMapKeyRef.name` derived from varName
- [x] Accepts both `"name"` and `"key"` field as the env var name

##### 0.2.20d ConfigMap / Secret resource generation (`_svc_env_to_resources`)
- [x] Hardcoded env vars → ConfigMap resource with `data` dict
- [x] Secret env vars → Secret resource with `stringData` dict (placeholder values)
- [x] Mixed env vars → both ConfigMap and Secret resources
- [x] No env vars → empty resource list, `has_config=False`, `has_secrets=False`
- [x] ConfigMap name follows `{svc_name}-config` convention
- [x] Secret name follows `{svc_name}-secrets` convention
- [x] `envFrom` on workload spec wires both configMapRef and secretRef

#### 0.2.21 Error Cases

> **Scope:** All wizard and K8s functions must handle error conditions gracefully.
> CLI-dependent functions return `{error: "..."}` when the CLI is unavailable.
> Parse functions return safe defaults (empty list, None) on malformed input.
> State persistence functions handle filesystem and JSON errors.
>
> Source of truth: Each function's docstring contract + defensive programming requirements.

##### 0.2.21a CLI availability errors
- [x] `k8s_apply` with kubectl unavailable → `{ok: False, error: "kubectl not available"}`
- [x] `k8s_delete_resource` with kubectl unavailable → same error
- [x] `k8s_scale` with kubectl unavailable → same error
- [x] `helm_install` with helm unavailable → `{error: "helm CLI not found"}`
- [x] `helm_upgrade` with helm unavailable → `{error: "helm CLI not found"}`
- [x] `helm_template` with helm unavailable → `{error: "helm CLI not found"}`

##### 0.2.21b kubectl operation errors
- [x] `k8s_apply` on nonexistent file → `{ok: False, error: "Path not found: ..."}`
- [x] `k8s_delete_resource` with empty kind → `{ok: False, error: "Missing kind or name"}`
- [x] `k8s_delete_resource` with empty name → `{ok: False, error: "Missing kind or name"}`
- [x] `k8s_scale` with empty name → `{ok: False, error: "Missing resource name"}`
- [x] `k8s_apply` subprocess exception → error captured, not raised
- [x] `k8s_scale` subprocess exception → error captured, not raised

##### 0.2.21c Wizard state persistence errors
- [x] `load_wizard_state` — file not found → `{ok: False, reason: "not_found"}`
- [x] `load_wizard_state` — corrupt JSON → `{ok: False, reason: "invalid"}`
- [x] `load_wizard_state` — valid JSON → `{ok: True, ...state}`
- [x] `save_wizard_state` — empty services and infraDecisions → `{error: "Empty state..."}`
- [x] `save_wizard_state` — valid state → file written, `{ok: True, path: "..."}`
- [x] `save_wizard_state` — creates `k8s/` dir if missing

##### 0.2.21d YAML parsing and volume builder errors
- [x] `_parse_k8s_yaml` on unreadable file (OSError) → empty list (no crash)
- [x] `_parse_k8s_yaml` on malformed YAML → empty list (no crash)
- [x] `_parse_k8s_yaml` on valid YAML without kind/apiVersion → empty list (filtered out)
- [x] `_parse_k8s_yaml` on multi-document YAML → all valid docs returned
- [x] `_build_wizard_volume` with no mountPath → `(None, None)`
- [x] `_build_wizard_volume` with unknown type → `(None, None)`
- [x] `_build_wizard_volume` with valid emptyDir → (pod_vol, vm) returned
- [x] `_build_wizard_volume` with valid configMap → (pod_vol, vm) returned
- [x] `_build_wizard_volume` with valid secret → (pod_vol, vm) returned
- [x] `_build_wizard_volume` with valid hostPath → (pod_vol, vm) returned
- [x] `_build_wizard_volume` with readOnly flag → `vm["readOnly"] = True`

##### 0.2.21e Validation errors
- [x] Missing `metadata.name` → validation error
- [x] Deployment without containers → validation error
- [x] Unknown `apiVersion` → validation warning
- [x] `generate_manifests` with empty app_name → still produces files (uses empty string)
- [x] `generate_k8s_wizard` with empty resource list → `{ok: False, error: ...}`


---

### 0.3 Skaffold

> Source of truth: **Skaffold v4beta11 schema spec** (skaffold.dev/docs/references/yaml).
> The generator must produce configs that reflect the real feature surface of Skaffold,
> not just the minimal fields. A DevOps control plane that generates toy configs is useless.
>
> TDD approach: tests define the FULL target first (TDD red). `_generate_skaffold` gets
> evolved to pass them. Detection (`skaffold_status`) gets evolved to parse all new sections.

#### 0.3.1 Detection (already covered by 0.2.19e — verify, don't re-test)
- [x] No skaffold files → `has_skaffold=False`
- [x] skaffold.yaml present → detected with path, apiVersion
- [x] skaffold.yml present → detected
- [x] Both variants → both detected
- [x] apiVersion parsed
- [x] Profiles extracted with names
- [x] Profiles without name → skipped
- [x] No profiles section → empty list
- [x] Malformed YAML → still detected, fields empty
- [x] CLI available → `available=True`
- [x] CLI not available → `available=False`
- [x] **NEW** Detect `portForward` section → `has_port_forward=True`
- [x] **NEW** Detect `build.local` vs `build.cluster` → `build_strategy` field
- [x] **NEW** Detect `deploy.kubectl` vs `deploy.helm` vs `deploy.kustomize` → `deploy_strategy` field
- [x] **NEW** Detect `requires` (multi-config) → `required_configs` list
- [x] **NEW** Detect `build.tagPolicy` type → `tag_policy` field

#### 0.3.2 Generation — Document structure (baseline)

> These are covered by 0.2.19a-b but listed here as the foundation for deeper generation.

- [x] `skaffold=False` → no file generated
- [x] `skaffold=True` → skaffold.yaml created
- [x] Valid YAML output (round-trip parse)
- [x] `apiVersion: skaffold/v4beta11`
- [x] `kind: Config`
- [x] `metadata.name` from first service (fallback `"app"`)
- [x] Output file path is `"skaffold.yaml"` (project root)
- [x] `overwrite=False` by default

#### 0.3.3 Generation — Build section

> Source of truth: Skaffold `build` schema — `artifacts`, `local`, `tagPolicy`.

##### 0.3.3a Build artifacts
- [x] Non-Skip service with image → build artifact entry
- [x] Artifact `image` matches service image exactly
- [x] Artifact `context` defaults to `"."` (project root)
- [x] Skip kind excluded from artifacts
- [x] Empty image excluded from artifacts
- [x] No eligible services → no `build` section at all
- [x] Multiple services → multiple artifacts, one per service
- [x] **NEW** Service with `dockerfile` field → artifact gets `docker.dockerfile` path
- [x] **NEW** Service without `dockerfile` → artifact defaults to `docker.dockerfile: Dockerfile`
- [x] **NEW** Service with `buildArgs` dict → artifact gets `docker.buildArgs`
- [x] **NEW** Service with `buildTarget` → artifact gets `docker.target`

##### 0.3.3b Build local config
- [x] **NEW** Default build is `local` (no cluster build)
- [x] **NEW** `build.local.push: false` for dev profile (don't push to registry)
- [x] **NEW** `build.local.useBuildkit: true` by default
- [x] **NEW** `build.local.concurrency` reflects number of services (0 = unlimited)
- [x] **NEW** `build.local.tryImportMissing: true` to avoid redundant builds

##### 0.3.3c Tag policy
- [x] **NEW** Default tag policy is `gitCommit` (reproducible)
- [x] **NEW** `build.tagPolicy.gitCommit.variant: Tags` (use git tag if available)
- [x] **NEW** Wizard option `tagPolicy: "sha256"` → `build.tagPolicy: sha256: {}`
- [x] **NEW** Wizard option `tagPolicy: "dateTime"` → `build.tagPolicy.dateTime` with `format` and `timezone`
- [x] **NEW** Wizard option `tagPolicy: "envTemplate"` → `build.tagPolicy.envTemplate.template: "{{.IMAGE_NAME}}:{{.DIGEST_HEX}}"`
- [x] **NEW** Wizard option `tagPolicy: "inputDigest"` → `build.tagPolicy: inputDigest: {}`

#### 0.3.4 Generation — Manifests & Deploy

> Source of truth: Skaffold `manifests` + `deploy` schemas — kubectl, helm, kustomize deployers.
>
> **Critical real-world concern:** When running locally (not in CI/CD), manifests
> contain `${VAR}` placeholders that need resolution. Skaffold does NOT do envsubst
> natively. The generator must wire up either:
> - Pre-deploy hooks running `envsubst`
> - Kustomize configMapGenerator/secretGenerator pulling from `.env` files
> - Helm `--set` values from environment
>
> Without this, `skaffold dev` from a local machine will deploy broken manifests
> with literal `${VAR}` strings.

##### 0.3.4a Manifests section (baseline)
- [x] Generated K8s YAML paths → `manifests.rawYaml` list
- [x] Non-YAML files excluded
- [x] No manifests → fallback glob `{output_dir}/*.yaml`
- [x] Custom `output_dir` reflected in paths

##### 0.3.4b Manifests — Kustomize overlay structure
- [x] **NEW** Kustomize-based project → `manifests.kustomize.paths` instead of `rawYaml`
- [x] **NEW** Base overlay: `manifests.kustomize.paths: ["k8s/base"]` for shared resources
- [x] **NEW** Dev overlay: profile overrides to `["k8s/overlays/dev"]`
- [x] **NEW** Staging overlay: profile overrides to `["k8s/overlays/staging"]`
- [x] **NEW** Prod overlay: profile overrides to `["k8s/overlays/prod"]`
- [x] **NEW** `manifests.kustomize.buildArgs` passed through from wizard state
- [x] **NEW** Base kustomization references all generated manifests in `resources:`

##### 0.3.4c Manifests — envsubst for variable resolution
> When manifests contain `${VAR}` patterns (ConfigMap data, Secret stringData,
> container env values), they need substitution before deploy. This is the
> **core problem** for new development without CI/CD variable injection.

- [x] **NEW** Wizard env vars with `type: "variable"` → manifest uses `${VAR_NAME}` placeholder
- [x] **NEW** Pre-deploy hook generated: `envsubst < manifest.yaml > manifest.yaml` per file with variables
- [x] **NEW** Hook only runs for manifests that actually contain `${...}` patterns
- [x] **NEW** `.env.example` file generated listing all required variables with comments
- [x] **NEW** Deploy hook `dir` set to project root
- [x] **NEW** Kustomize alternative: `configMapGenerator.envs: [".env"]` pulls from `.env` file
- [x] **NEW** Kustomize alternative: `secretGenerator.envs: [".env.secret"]` for secrets

##### 0.3.4d Manifests — Secret encoding
> Kubernetes Secrets with `data:` must be base64-encoded. `stringData:` is
> auto-encoded by kubectl. But if the secret VALUE is `${DB_PASSWORD}`,
> envsubst must run BEFORE kubectl apply. The generator must choose the right
> encoding strategy based on whether the value is a literal or a variable.

- [x] **NEW** Literal secret values → use `stringData:` (kubectl handles base64)
- [x] **NEW** Variable secret values (`${VAR}`) → use `stringData:` + envsubst hook
- [x] **NEW** Never generate `data:` with raw (non-base64) values — that's an error
- [x] **NEW** Generated secrets with variables include comment: `# requires envsubst`
- [x] **NEW** Validation: if secret has `data:` field, values must be valid base64

##### 0.3.4e Deploy section — kubectl (default)
- [x] `deploy.kubectl` present when deployment strategy is raw kubectl
- [x] **NEW** `deploy.kubectl.defaultNamespace` set from wizard namespace
- [x] **NEW** `deploy.kubectl.flags.apply` includes `--server-side` when wizard option set
- [x] **NEW** `deploy.kubectl.flags.global` includes `--namespace` when namespace specified
- [x] **NEW** `deploy.kubectl.hooks.before` includes envsubst commands when manifests have variables
- [x] **NEW** `deploy.kubectl.hooks.after` available for post-deploy verification

##### 0.3.4f Deploy section — helm
- [x] **NEW** Helm-based project → `deploy.helm.releases` list instead of kubectl
- [x] **NEW** Each Helm release has `name`, `chartPath`, `valuesFiles`
- [x] **NEW** `deploy.helm.releases[].setValues` from wizard env vars (no envsubst needed — Helm handles it)
- [x] **NEW** `deploy.helm.releases[].setValueTemplates` for env-var-based values: `"{{.DB_HOST}}"`
- [x] **NEW** `deploy.helm.releases[].namespace` from wizard namespace
- [x] **NEW** `deploy.helm.releases[].createNamespace: true` when namespace specified
- [x] **NEW** `deploy.helm.releases[].useHelmSecrets: true` when secrets plugin detected

##### 0.3.4g Deploy section — kustomize
- [x] **NEW** Kustomize-based project → `deploy.kustomize.paths` list
- [x] **NEW** Default path is base: `["k8s/base"]`
- [x] **NEW** Overlays reflected per profile (see 0.3.5)
- [x] **NEW** `deploy.kustomize.buildArgs` passed through

#### 0.3.5 Generation — Profiles

> Source of truth: Skaffold `profiles` schema — overlay build/deploy per environment.
> Profiles are the core of multi-environment Skaffold. Without them, the config is single-env.
>
> **Critical design decision:** The `dev-from-local` profile is the most important profile
> because it's what developers use daily. It must handle:
> 1. envsubst for `${VAR}` resolution from shell/`.env` file
> 2. Local builds (no push to registry)
> 3. Port-forwarding for debugging
> 4. File sync for hot-reload
> Without these, `skaffold dev` is useless on a developer's machine.

##### 0.3.5a Profile structure
- [x] **NEW** Wizard with environments → `profiles` section generated
- [x] **NEW** Each environment → one profile entry with `name` matching env name
- [x] **NEW** Profile activation by kubeContext → `activation[].kubeContext` pattern
- [x] **NEW** Profile activation by env var → `activation[].env` with name + value
- [x] **NEW** Profile activation by command → `activation[].command` (dev/run/deploy)
- [x] **NEW** No environments → no `profiles` section

##### 0.3.5b Dev-from-local profile (the critical one)
> This is the profile for `skaffold dev -p dev-from-local`. Developer runs
> this on their machine. No CI/CD. No registry. Variables come from shell env
> or `.env` file. This MUST work out of the box.

- [x] **NEW** `dev-from-local` profile generated when wizard has local-dev services
- [x] **NEW** Profile overrides `build.local.push: false` (images stay local)
- [x] **NEW** Profile sets `build.tagPolicy: sha256: {}` (fast, no git tag needed)
- [x] **NEW** Profile activates on `command: dev` (auto-active during `skaffold dev`)
- [x] **NEW** Profile includes envsubst pre-deploy hook for all variable-bearing manifests
- [x] **NEW** Profile includes `portForward` entries for all services with ports
- [x] **NEW** Profile includes `sync` rules for hot-reload (see 0.3.7)
- [x] **NEW** Profile overrides `deploy.kubectl.defaultNamespace: "default"` (local cluster)
- [x] **NEW** Profile sets env var `SKAFFOLD_DEFAULT_REPO=""` (no remote registry)
- [x] **NEW** Profile comment documents: "Load your .env file: `set -a; source .env; set +a`"

##### 0.3.5c Dev profile (CI/CD dev environment)
> Different from dev-from-local: this runs in CI/CD for a dev/staging cluster.
> Variables are injected by the CI system. Images may be pushed to a dev registry.

- [x] **NEW** `dev` profile for CI/CD dev environment
- [x] **NEW** `dev` profile overrides `build.local.push: true` (push to dev registry)
- [x] **NEW** `dev` profile uses Kustomize overlay: `deploy.kustomize.paths: ["k8s/overlays/dev"]`
- [x] **NEW** `dev` profile does NOT include envsubst hooks (CI/CD injects vars)
- [x] **NEW** `dev` profile does NOT include port-forwarding (not local)

##### 0.3.5d Staging / Production profiles
- [x] **NEW** Staging profile with registry push enabled (`build.local.push: true`)
- [x] **NEW** Staging profile uses overlay: `deploy.kustomize.paths: ["k8s/overlays/staging"]`
- [x] **NEW** Production profile with `build.tagPolicy: gitCommit` (reproducible)
- [x] **NEW** Production profile with `deploy.kubectl.flags.apply: ["--server-side"]`
- [x] **NEW** Per-profile namespace override via `deploy.kubectl.defaultNamespace`
- [x] **NEW** Profiles can override `manifests` section (e.g., different overlay per env)

##### 0.3.5e Profile patches
- [x] **NEW** Profile `patches` array for fine-grained overrides instead of full section replacement
- [x] **NEW** Patch with `op: replace`, `path: /build/artifacts/0/image`, `value: "registry.io/app:prod"`
- [x] **NEW** Patch with `op: add` to inject additional build args per profile

#### 0.3.6 Generation — Port Forwarding

> Source of truth: Skaffold `portForward` schema — maps K8s ports to localhost.

- [x] **NEW** Service with `port` → `portForward` entry generated
- [x] **NEW** `portForward[].resourceType: "service"` (default)
- [x] **NEW** `portForward[].resourceName` from service name
- [x] **NEW** `portForward[].port` from service port
- [x] **NEW** `portForward[].localPort` defaults to same as remote port
- [x] **NEW** `portForward[].namespace` from wizard namespace
- [x] **NEW** Multiple services → multiple port-forward entries, no port collisions
- [x] **NEW** Port collision detection → `localPort` auto-incremented
- [x] **NEW** Port forwarding only in dev profile (not production)

#### 0.3.7 Generation — File Sync (dev hot-reload)

> Source of truth: Skaffold `sync` schema — copy files to container without rebuild.

- [x] **NEW** Dev profile services get `sync` section in their artifacts
- [x] **NEW** `sync.manual[].src` glob pattern (e.g., `"src/**/*.py"`, `"src/**/*.js"`)
- [x] **NEW** `sync.manual[].dest` destination in container (e.g., `"/app"`)
- [x] **NEW** Language detection → appropriate sync globs (Python: `*.py`, Node: `*.js,*.ts`, Go: none)
- [x] **NEW** `sync.manual[].strip` removes local path prefix
- [x] **NEW** No language detected → no sync section (full rebuild only)
- [x] **NEW** Sync only in dev profile (not staging/prod)

#### 0.3.8 Generation — Lifecycle Hooks

> Source of truth: Skaffold hooks — pre/post build, deploy, sync commands.

- [x] **NEW** Wizard with `preDeploy` commands → `deploy.hooks.before[].host.command`
- [x] **NEW** Wizard with `postDeploy` commands → `deploy.hooks.after[].host.command`
- [x] **NEW** Hook `dir` defaults to project root
- [x] **NEW** No hooks configured → no hooks section

#### 0.3.9 Wizard Integration (end-to-end)

> Round-trip: wizard state → `_generate_skaffold` → disk → `skaffold_status` detection.

- [x] `setup_k8s()` with `skaffold=True` → skaffold.yaml written to disk
- [x] Generated skaffold.yaml is valid YAML (round-trip parse)
- [x] skaffold.yaml references generated manifest paths
- [x] `skaffold=False` → no skaffold.yaml written
- [x] After setup → `skaffold_status()` detects the config
- [x] Build artifact images match wizard service images
- [x] **NEW** Profiles in generated config → detected by `skaffold_status`
- [x] **NEW** Port-forward in generated config → detected by `skaffold_status`
- [x] **NEW** Deploy strategy in generated config → detected by `skaffold_status`
- [x] **NEW** Tag policy in generated config → detected by `skaffold_status`

#### 0.3.10 Error Cases & Edge Cases

- [x] Skaffold CLI not installed → detection still works (file-based)
- [x] Malformed existing skaffold.yaml → overwrite works
- [x] **NEW** Service with port conflict → port-forward auto-increment works
- [x] **NEW** No services at all → minimal valid skaffold.yaml (manifests only, no build)
- [x] **NEW** All services are Skip kind → no build section, manifests still present
- [x] **NEW** Empty wizard state with `skaffold=True` → valid minimal config produced
- [x] **NEW** Profile name collision with reserved names → error or warning
- [x] **NEW** Dockerfile not at default path → `docker.dockerfile` reflects actual path

---

### 0.4 Helm

> **Scope:** Full Detect → Observe → Facilitate → Act lifecycle for Helm charts.
>
> Helm is a first-class ops stack (STACKS.md line 65). The control plane must:
> - Detect existing charts and their structure
> - Observe installed releases via CLI wrappers
> - **Facilitate** chart generation from wizard state (the missing piece)
> - Act on charts via install/upgrade/template/lint/package
>
> **Standard Helm chart structure** (what we generate):
> ```
> charts/{name}/
> ├── Chart.yaml              # Chart metadata (name, version, description, deps)
> ├── values.yaml             # Default values (image, port, replicas, env)
> ├── values-{env}.yaml       # Per-environment overrides
> ├── templates/
> │   ├── _helpers.tpl        # Reusable Go template snippets
> │   ├── deployment.yaml     # Deployment template
> │   ├── service.yaml        # Service template
> │   ├── ingress.yaml        # Ingress template (conditional)
> │   ├── configmap.yaml      # ConfigMap template (conditional)
> │   ├── secret.yaml         # Secret template (conditional)
> │   └── NOTES.txt           # Post-install usage notes
> └── .helmignore             # Packaging exclusions
> ```

#### 0.4.1 Detection (already covered — verify, don't re-test)

> These map to `_detect_helm_charts` in `k8s_detect.py` and tests in `test_helm.py::TestHelmChartDetection`.
> 42 tests already exist and pass. Verify they are pessimistic.

- [x] No Chart.yaml → empty list
- [x] Single chart → detected with name, version, description
- [x] Multiple charts → all detected
- [x] Nested chart (deploy/helm/myapp/) → detected
- [x] Charts in skipped dirs (node_modules, .venv) → not detected
- [x] Chart path is relative to project root
- [x] Missing chart name → defaults to "unknown"
- [x] Missing chart version → defaults to "0.0.0"
- [x] Chart description extracted
- [x] Malformed Chart.yaml → detected as "unknown"
- [x] Chart with dependencies → still detected
- [x] **NEW** Chart structure detection: `has_values`, `has_templates`, `has_subcharts`, `has_lockfile` fields present and correct
- [x] **NEW** Env-specific values files detected: `env_values_files` list populated
- [x] **NEW** `app_version` and `type` fields parsed (defaults: `""`, `"application"`)

#### 0.4.2 CLI Wrappers (already covered — verify, don't re-test)

> These map to `k8s_helm.py` functions and tests in `test_helm.py`.
> Verify existing tests are pessimistic (exact command construction, not just "it ran").

- [x] `helm_list()` — no helm CLI → error dict
- [x] `helm_list()` — basic call uses --all-namespaces + -o json
- [x] `helm_list()` — with namespace uses --namespace
- [x] `helm_list()` — parses JSON releases into list of dicts
- [x] `helm_list()` — error returned on CLI failure
- [x] `helm_list()` — JSON parse error → graceful error
- [x] `helm_list()` — timeout → graceful error
- [x] `helm_list()` — empty stdout → empty releases list
- [x] `helm_list()` — release entries have expected fields (name, namespace, status, chart, app_version)
- [x] `helm_values()` — basic call with release name
- [x] `helm_values()` — with namespace
- [x] `helm_values()` — error on missing release
- [x] `helm_install()` — basic install command
- [x] `helm_install()` — with namespace + --create-namespace
- [x] `helm_install()` — with values file
- [x] `helm_install()` — with --set values
- [x] `helm_install()` — with --dry-run
- [x] `helm_install()` — error response
- [x] `helm_upgrade()` — uses --install flag
- [x] `helm_upgrade()` — all options combined (ns + values + set + dry-run)
- [x] `helm_upgrade()` — error response
- [x] `helm_template()` — renders YAML output
- [x] `helm_template()` — with namespace
- [x] `helm_template()` — with values file
- [x] `helm_template()` — error response

#### 0.4.3 Values File Detection (already covered — verify, don't re-test)

> Part of chart detection enrichment + env-namespace mapping.

- [x] values-{env}.yaml in chart dir → detected in `env_values_files`
- [x] values-dev.yaml, values-staging.yaml → both detected
- [x] No values-{env} files → empty list
- [x] values.yaml base file → `has_values=True`
- [x] No values.yaml → `has_values=False`

#### 0.4.4 Generation — Chart.yaml (NEW)

> `_generate_helm_chart()` function creates a complete chart directory.
> TDD: tests first → then implement.

- [x] `helm_chart=False` → no chart generated
- [x] `helm_chart=True` → Chart.yaml created
- [x] Chart.yaml is valid YAML (round-trip parse)
- [x] `apiVersion: v2` (Helm 3 format)
- [x] `name` from first service name (fallback: `"app"`)
- [x] `version: "0.1.0"` (default initial version)
- [x] `description` from wizard project description (fallback: default)
- [x] `appVersion` from first service image tag (fallback: `"1.0.0"`)
- [x] `type: application` (default)
- [x] Chart.yaml output path is `charts/{name}/Chart.yaml`
- [x] Multiple services → single chart with multi-container templates
- [x] No services → minimal chart (empty templates)

#### 0.4.5 Generation — values.yaml (NEW)

> Default values file that parameterizes the templates.

- [x] values.yaml created alongside Chart.yaml
- [x] Valid YAML output (round-trip parse)
- [x] Per-service section: `image.repository`, `image.tag`, `image.pullPolicy`
- [x] Per-service section: `replicaCount` from wizard replicas
- [x] Per-service section: `service.type`, `service.port` from wizard ports
- [x] Per-service section: `resources.requests` and `resources.limits` from wizard
- [x] Per-service section: `env` list from wizard env vars (plain values)
- [x] Ingress section: `ingress.enabled`, `ingress.host` from wizard
- [x] No services → minimal values (empty sections)
- [x] Secret env vars → referenced as `existingSecret` (not inlined)

#### 0.4.6 Generation — templates/ (NEW)

> Go-template Kubernetes manifests that reference `{{ .Values }}`.

- [x] templates/ directory created
- [x] `_helpers.tpl` created with chart name/fullname/labels helpers
- [x] `deployment.yaml` created for each non-Skip service
- [x] `deployment.yaml` uses `{{ .Values.image.repository }}:{{ .Values.image.tag }}`
- [x] `deployment.yaml` includes resource limits from `{{ .Values.resources }}`
- [x] `deployment.yaml` includes env vars from `{{ .Values.env }}`
- [x] `service.yaml` created for services with ports
- [x] `service.yaml` uses `{{ .Values.service.type }}` and `{{ .Values.service.port }}`
- [x] `ingress.yaml` created conditionally (`{{ if .Values.ingress.enabled }}`)
- [x] `configmap.yaml` created when wizard has config env vars
- [x] `secret.yaml` created when wizard has secret env vars
- [x] `NOTES.txt` created with post-install instructions
- [x] All templates use `{{ include "chart.fullname" . }}` for naming consistency
- [x] All templates use `{{ include "chart.labels" . }}` for label consistency
- [x] Templates are valid Go templates (no syntax errors)

#### 0.4.7 Generation — Per-Environment Values (NEW)

> Environment-specific overrides (values-dev.yaml, values-staging.yaml, etc.).

- [x] Wizard with environments → values-{env}.yaml files created
- [x] values-dev.yaml overrides: `replicaCount: 1`, reduced resources
- [x] values-staging.yaml overrides: staging-specific image tag pattern
- [x] values-prod.yaml overrides: `replicaCount: 3`, full resources
- [x] No environments → no values-{env}.yaml files
- [x] Per-env values are valid YAML
- [x] Per-env values only contain overrides (not full copy)

#### 0.4.8 Generation — .helmignore (NEW)

- [x] .helmignore created with standard exclusions
- [x] Excludes: `.git/`, `*.swp`, `*.bak`, `*.tmp`, `__pycache__/`, `.venv/`

#### 0.4.9 Wizard Integration (end-to-end, NEW)

> Round-trip: wizard state → `_generate_helm_chart()` → disk → `_detect_helm_charts()`.

- [x] `setup_k8s()` with `helm_chart=True` → chart directory written to disk
- [x] Generated Chart.yaml is valid YAML (round-trip parse)
- [x] Chart directory has correct structure (Chart.yaml, values.yaml, templates/)
- [x] `helm_chart=False` → no chart directory written
- [x] After setup → `_detect_helm_charts()` detects the generated chart
- [x] Detected chart name matches wizard service name
- [x] Detected chart version matches generated version
- [x] `has_values=True` after generation
- [x] `has_templates=True` after generation
- [x] Env-specific values files detected after generation
- [x] **Combined flow:** `helm_chart=True` + `skaffold=True` → Skaffold `deploy.helm.releases` points to generated chart path

#### 0.4.10 Skaffold + Helm Combined (NEW)

> When the wizard uses deploy_strategy=helm, Skaffold and Helm chart must work together.

- [x] `deploy_strategy="helm"` + `helm_chart=True` → both Skaffold config and Helm chart generated
- [x] Skaffold `deploy.helm.releases[].chartPath` matches generated chart directory
- [x] Skaffold `deploy.helm.releases[].valuesFiles` includes generated values files
- [x] Round-trip: `skaffold_status()` detects `deploy_strategy="helm"` from combined config
- [x] `deploy_strategy="helm"` without `helm_chart=True` → Skaffold config only (references external chart)

#### 0.4.11 Error Cases & Edge Cases

- [x] helm CLI not installed → detection still works (file-based)
- [x] helm CLI timeout → graceful error
- [x] Invalid chart path → error message
- [x] **NEW** Service with no image → excluded from chart templates
- [x] **NEW** Service with kind=Skip → excluded from chart
- [x] **NEW** Empty wizard state with `helm_chart=True` → minimal valid chart
- [x] **NEW** Chart name collision with existing chart → overwrite=False respected
- [x] **NEW** Special characters in service name → sanitized for chart name
- [x] **NEW** Very long service name → truncated to 63 chars (DNS label limit)

---

### 0.5 CI/CD

> **Scope:** CI/CD is the **orchestrator of all integrations**. A single workflow file
> must compose knowledge from: stacks (20), Docker (build/push), Kubernetes
> (kubectl/Skaffold/Helm), environments (dev/staging/prod), secrets, and Git branching.
>
> **Source of truth:** TECHNOLOGY_SPEC §5.3 + PROJECT_SCOPE §4.3 + 59 existing
> integration TDD tests in `tests/integration/test_ci_integration.py`.
>
> **Architecture:**
> ```
> wizard state → setup_ci() → compose jobs → .github/workflows/ci.yml
>                                │
>                 ┌──────────────┼──────────────┐
>                 │              │              │
>            test jobs      build jobs     deploy jobs
>          (from stacks)   (from Docker)  (from K8s strategy)
>                                              │
>                              ┌────────────────┼────────────────┐
>                              │                │                │
>                          kubectl          skaffold           helm
> ```
>
> **Existing test baseline:** 81 unit tests pass (detection + generators + ops).
> 59 integration tests exist but are ALL RED (forward TDD targets).

#### 0.5.1 Detection — Audit & Strengthen

> Verify existing `ci_status()` detection is pessimistic across all 7 providers.
> These tests already exist in `test_ci_detect.py::TestCiStatus` (33 tests).

- [x] Empty project → `has_ci=False`, `providers=[]`, `total_workflows=0`
- [x] `.github/workflows/*.yml` → GitHub Actions detected with `id="github_actions"`, `name="GitHub Actions"`
- [x] Multiple workflow files → `workflows` count matches file count
- [x] `.gitlab-ci.yml` → GitLab CI detected
- [x] `.gitlab-ci.yaml` → GitLab CI detected (alternate extension)
- [x] `Jenkinsfile` → Jenkins detected
- [x] `.circleci/config.yml` → CircleCI detected
- [x] `.travis.yml` → Travis CI detected
- [x] `azure-pipelines.yml` → Azure Pipelines detected
- [x] `bitbucket-pipelines.yml` → Bitbucket Pipelines detected
- [x] Multiple providers simultaneously → all detected, `total_workflows` summed
- [x] Non-YAML files in `.github/workflows/` → ignored (no false positives)
- [x] Return shape: `{"providers": [...], "total_workflows": int, "has_ci": bool}`
- [x] Provider shape: `{"id": str, "name": str, "workflows": int}`

#### 0.5.2 Workflow Parsing — Audit & Strengthen

> Verify `ci_workflows()` parses structure from all provider formats.
> Tests in `test_ci_detect.py::TestCiWorkflows` + `test_ci_ops.py::TestParseGithubWorkflow`.

- [x] Empty project → `{"workflows": []}`
- [x] GitHub Actions workflow → `name`, `triggers`, `jobs` parsed
- [x] GitHub Actions triggers → list of trigger event names (`push`, `pull_request`, etc.)
- [x] GitHub Actions jobs → list with `name`, `steps_count`, `runs_on`
- [x] GitHub Actions steps → correct `steps_count` per job
- [x] GitHub Actions with multiple jobs → all jobs parsed
- [x] GitLab CI → jobs extracted as list
- [x] GitLab CI → dot-prefixed templates (`.template`) skipped
- [x] GitLab CI → meta keys (`stages`, `variables`, `include`, `default`, `image`, `before_script`, `after_script`, `workflow`, `cache`, `services`) skipped
- [x] GitLab CI → invalid YAML → result with issues, no crash
- [x] Jenkinsfile → listed with `provider="jenkins"`, not deeply parsed
- [x] Multi-provider → combined sorted list
- [x] Invalid YAML → handled gracefully with `issues` field
- [x] Workflow shape: `{"file": str, "provider": str, "name": str, "triggers": [...], "jobs": [...], "issues": [...]}`
- [x] Audit: unpinned actions → issue reported
- [x] Audit: empty run commands → issue reported

#### 0.5.3 Stack-Based Generation — Audit & Strengthen

> Verify `generators/github_workflow.py` produces correct CI/lint workflows per stack.
> Tests in `test_ci_generators.py::TestGenerateCi` + `TestGenerateLint` + `TestResolveJob`.

- [x] `_resolve_job("python")` → `_python_ci_job`
- [x] `_resolve_job("node")` → `_node_ci_job`
- [x] `_resolve_job("typescript")` → `_node_ci_job` (shares with node)
- [x] `_resolve_job("go")` → `_go_ci_job`
- [x] `_resolve_job("rust")` → `_rust_ci_job`
- [x] `_resolve_job("java-maven")` → `_java_maven_ci_job`
- [x] `_resolve_job("java-gradle")` → `_java_gradle_ci_job`
- [x] `_resolve_job("python-flask")` → `_python_ci_job` (prefix match)
- [x] `_resolve_job("unknown")` → `None`
- [x] `generate_ci([], "python")` → content includes `pytest`, `ruff`
- [x] `generate_ci([], "node")` → content includes `npm ci`
- [x] `generate_ci([], "go")` → content includes `go test`
- [x] `generate_ci([], "rust")` → content includes `cargo test`
- [x] `generate_ci([], ["python", "node"])` → multi-stack combined
- [x] `generate_ci([], ["python", "python-flask"])` → deduplicated (one job)
- [x] All `uses:` actions pinned to versions (`@v4`, etc.)
- [x] `permissions:` block present
- [x] Output path = `.github/workflows/ci.yml`
- [x] Output is valid YAML with `jobs` key
- [x] `generate_lint()` → separate lint-only workflow at `.github/workflows/lint.yml`
- [x] `generate_lint("python")` → includes `ruff`, `mypy`
- [x] `generate_lint("node")` → includes lint commands
- [x] `generate_lint("unknown")` → `None`
- [x] `overwrite=False` on generated files

#### 0.5.4 Wizard `setup_ci()` — Redesign as Composable Generator

> **BREAKING CHANGE:** Current `setup_ci()` is a hardcoded Python-only string template.
> Must be redesigned to accept a wizard state dict and compose jobs from all integrations.
>
> This is the **central generator** — everything else feeds into it.

- [x] `setup_ci()` accepts wizard state dict with: `stacks`, `docker`, `k8s`, `environments`, `branches`
- [x] `setup_ci()` delegates test job generation to `generators/github_workflow.py`
- [x] `setup_ci()` produces valid YAML output
- [x] `setup_ci()` includes `push` and `pull_request` triggers
- [x] `setup_ci()` trigger branches configurable (default: `main, master`)
- [x] `setup_ci()` with `overwrite=False` → error if file exists
- [x] `setup_ci()` with `overwrite=True` → replaces existing file
- [x] `setup_ci()` → `ci_status()` detects GitHub Actions after generation
- [x] `setup_ci()` → `ci_workflows()` can parse the generated file
- [x] `setup_ci()` with only stacks (no Docker/K8s) → test-only workflow

#### 0.5.5 Docker Build — CI Steps for Docker Builds

> When wizard enables Docker, CI must include Docker build steps.
> Integration tests: `test_ci_integration.py::TestCiDockerBuild` (6 tests).

- [x] `docker=True` → CI includes a `docker build` step
- [x] Docker build uses Buildx (`docker/setup-buildx-action`)
- [x] Build args from wizard → `--build-arg` flags in CI
- [x] Docker build runs on push but **not** on PRs (PRs test only)
- [x] Docker build uses GHA layer caching (`type=gha`)
- [x] Docker image tagged with SHA or version, not just `latest`
- [x] `docker=False` → no Docker steps in CI
- [x] Docker build step appears **after** test job
- [x] Docker build output is valid YAML

#### 0.5.6 Docker Push — Registry Login + Push

> When a Docker registry is configured, CI pushes images after building.
> Integration tests: `test_ci_integration.py::TestCiDockerPush` (7 tests).

- [x] `docker_registry="ghcr"` → push to `ghcr.io`
- [x] GHCR login uses `${{ secrets.GITHUB_TOKEN }}`
- [x] `docker_registry="dockerhub"` → push to `docker.io`
- [x] DockerHub login uses `${{ secrets.DOCKERHUB_USERNAME }}` / `${{ secrets.DOCKERHUB_TOKEN }}`
- [x] Login step appears **before** push step (ordering enforced)
- [x] Docker without registry (`docker=True`, no registry) → build only, no push
- [x] Custom private registry → registry URL in CI login + push
- [x] Registry login uses `docker/login-action` (pinned version)
- [x] Push step produces image reference for downstream deploy jobs

#### 0.5.7 K8s kubectl Deploy — Raw Manifest Deployment

> When K8s uses kubectl strategy, CI deploys via `kubectl apply`.
> Integration tests: `test_ci_integration.py::TestCiKubectlDeploy` (7 tests).

- [x] `k8s=True, deploy_strategy="kubectl"` → CI includes `kubectl apply`
- [x] Manifest dir from wizard referenced in apply command
- [x] Kubeconfig setup from secrets (`${{ secrets.KUBECONFIG }}`)
- [x] Namespace flag (`-n`) when wizard specifies namespace
- [x] Deploy job **depends on** test job (`needs: [test]`)
- [x] `kubectl apply --dry-run=client` validation before actual apply
- [x] `kubectl rollout status` wait after apply
- [x] `k8s=False` → no kubectl steps
- [x] Kubeconfig step uses `azure/k8s-set-context` or equivalent (pinned)

#### 0.5.8 K8s Skaffold Deploy — Skaffold-Based Deployment

> When K8s uses Skaffold strategy, CI delegates to skaffold CLI.
> Integration tests: `test_ci_integration.py::TestCiSkaffoldDeploy` (7 tests).

- [x] `deploy_strategy="skaffold"` → CI uses `skaffold run` or `skaffold deploy`
- [x] CI installs skaffold CLI (install step)
- [x] Skaffold mode → **no** raw `kubectl apply` in CI
- [x] Skaffold + environments → `-p {env}` profile flag per environment
- [x] Skaffold + registry → `--default-repo` flag
- [x] Custom skaffold file path → `-f` flag
- [x] Skaffold still needs kubeconfig setup
- [x] `deploy_strategy != "skaffold"` → no skaffold steps
- [x] Skaffold install pinned to specific version

#### 0.5.9 K8s Helm Deploy — Helm-Based Deployment

> When K8s uses Helm strategy, CI deploys via `helm upgrade --install`.
> Integration tests: `test_ci_integration.py::TestCiHelmDeploy` (9 tests).

- [x] `deploy_strategy="helm"` → CI uses `helm upgrade --install`
- [x] Chart path from wizard referenced in helm command
- [x] Helm release name set (from service name)
- [x] Helm + environments → `-f values-{env}.yaml` per environment
- [x] Helm + Docker → `--set image.tag=${{ ... }}` with dynamic tag from build
- [x] Helm deploy uses `--namespace` flag when specified
- [x] Helm mode → **no** raw `kubectl apply` in CI
- [x] Helm mode → **no** `skaffold` commands in CI
- [x] Helm still needs kubeconfig setup
- [x] `deploy_strategy != "helm"` → no helm steps
- [x] Helm install step (`helm` CLI assumed available on `ubuntu-latest`)

#### 0.5.10 Multi-Environment — Per-Env Deploy Pipelines

> When wizard defines multiple environments, CI generates separate deploy steps/jobs.
> Integration tests: `test_ci_integration.py::TestCiMultiEnvironment` (7 tests).

- [x] 3 environments (`dev`, `staging`, `prod`) → all appear in CI
- [x] Each env's namespace appears in deploy commands
- [x] Deploy ordering: dev → staging → prod (job dependency chain)
- [x] Production deploy constrained to `main` branch (`if: github.ref == 'refs/heads/main'`)
- [x] Different secret references per environment (env-scoped GitHub secrets)
- [x] Multi-env + Skaffold → `-p {env}` profile per environment
- [x] Multi-env + Helm → `-f values-{env}.yaml` per environment
- [x] Multi-env + kubectl → `-n {env}` namespace per environment
- [x] Single environment → single deploy job (no chaining)

#### 0.5.11 Full Pipeline — Test → Build → Deploy Composition

> The composition layer: all concerns merge into a single workflow.
> Integration tests: `test_ci_integration.py::TestCiFullPipeline` (8 tests).

- [x] Docker + kubectl → test → build/push → kubectl apply (3 jobs)
- [x] Docker + Skaffold → test → skaffold run (Skaffold handles build+deploy)
- [x] Docker + Helm → test → build/push → helm upgrade (3 jobs)
- [x] Job dependency chain: `test → build → deploy` (`needs:` fields)
- [x] Deploy job only runs on pushes to `main`, not on PRs
- [x] PRs run **only** test job (no build, no deploy)
- [x] Docker image tag/SHA passed from build job to deploy job (GitHub Actions outputs)
- [x] Full pipeline output is valid, parseable YAML
- [x] Stacks-only (no Docker, no K8s) → test-only workflow (graceful degradation)
- [x] Deploy strategy mutually exclusive: kubectl OR skaffold OR helm (never combined)

#### 0.5.12 Cleanup & Error Cases

> Edge cases, error handling, and generated config cleanup.
> Integration tests: `test_ci_integration.py::TestCiCleanup` (1 test) + new tests.

- [x] `delete_generated_configs("ci")` removes `.github/workflows/ci.yml`
- [x] `delete_generated_configs("ci")` removes `.github/workflows/lint.yml` if present
- [x] Malformed existing workflow → detection handles gracefully (no crash)
- [x] Empty YAML file → detection returns result with issues
- [x] No stacks detected → test job omitted, build/deploy still generated if Docker/K8s enabled
- [x] Invalid combo: Helm + Skaffold simultaneously → error or pick one
- [x] Missing required config (e.g. `k8s=True` but no `deploy_strategy`) → defaults to `kubectl`
- [x] `setup_ci()` returns `{"ok": true, "files_created": [...]}` on success

#### 0.5.13 Round-Trip Integration — Generate → Detect → Validate

> End-to-end: `setup_ci()` produces a workflow that `ci_status()` + `ci_workflows()` can fully consume.
> Integration tests: `test_ci_integration.py::TestCiRoundTrip` (7 tests).

- [x] `setup_ci()` → `ci_status()` detects GitHub Actions
- [x] `setup_ci()` → `ci_workflows()` parses generated file
- [x] Generated workflow has valid YAML with `jobs` key
- [x] Generated workflow has `push` trigger
- [x] Generated workflow has `pull_request` trigger
- [x] Generated jobs have non-zero `steps_count`

---

### 0.6 Terraform

> **Strategy**: Same as 0.5 — audit existing code against the spec, write
> pessimistic tests, fix gaps.  Source of truth: TECHNOLOGY_SPEC §3.4 +
> PROJECT_SCOPE §4.5.
>
> **Source files**: `terraform_ops.py`, `terraform_generate.py`,
> `terraform_actions.py`, `wizard_setup.py::setup_terraform()`.
> **Test files**: `tests/test_terraform_detect.py` (unit),
> `tests/test_terraform_actions.py` (unit, mocked CLI),
> `tests/integration/test_terraform_integration.py` (integration).

#### 0.6.1 Detection — `terraform_status()` Audit

> Source: `terraform_ops.py::terraform_status`, `_find_tf_root`,
> `_classify_tf_file`.  Tests: `tests/test_terraform_detect.py`.

- [x] Empty project → `has_terraform=False`, all lists empty
- [x] Return shape: `has_terraform`, `cli`, `root`, `files`, `providers`, `modules`, `resources`, `backend`, `initialized` — all keys present
- [x] `*.tf` files in project root → `has_terraform=True`, root is `"."`
- [x] `terraform/` directory with `*.tf` → root is `"terraform"`
- [x] `infra/` directory with `*.tf` → root is `"infra"`
- [x] `infrastructure/` directory with `*.tf` → root is `"infrastructure"`
- [x] Priority ordering: `terraform/` preferred over project root when both have `.tf` files
- [x] `.terraform/` state dir presence → `initialized=True`
- [x] No `.terraform/` → `initialized=False`
- [x] Skip directories respected: `.git`, `node_modules`, `.venv`, `.terraform` not scanned for `.tf` files
- [x] File classification: `main.tf` → type `"main"`, `variables.tf` → `"variables"`, `outputs.tf` → `"outputs"`, `providers.tf` → `"providers"`, `backend.tf` → `"backend"`, `terraform.tf` → `"versions"`, `data.tf` → `"data"`, `modules_foo.tf` → `"modules"`, `random.tf` → `"other"`
- [x] Provider parsing: `provider "aws" {}` → `"aws"` in providers list
- [x] Provider parsing: `required_providers { aws = { source = "hashicorp/aws" } }` → `"hashicorp/aws"` in providers list
- [x] Multiple providers → all listed, sorted
- [x] Module parsing: `module "vpc" { source = "./modules/vpc" }` → `{name: "vpc", source: "./modules/vpc"}`
- [x] Resource parsing: `resource "aws_instance" "web" {}` → `{type: "aws_instance", name: "web", file: ...}`
- [x] Data source parsing: `data "aws_ami" "latest" {}` → `{type: "data.aws_ami", name: "latest", file: ...}`
- [x] Backend parsing: `backend "s3" { bucket = "..." }` → `{type: "s3", file: ...}`
- [x] Backend parsing: GCS and azurerm backends also detected
- [x] No backend → `backend=None`
- [x] `resource_count` matches length of `resources` list
- [x] Nested `.tf` files (e.g. `terraform/modules/vpc/main.tf`) → found and classified

#### 0.6.2 Generation — `generate_terraform()` Audit

> Source: `terraform_generate.py::generate_terraform`.
> Tests: `tests/test_terraform_detect.py::TestGenerateTerraform` or
> `tests/integration/test_terraform_integration.py`.

- [x] Return shape: `{ok: True, files: [{path, content, reason, overwrite}, ...]}`
- [x] Unknown provider → returns `{error: "Unknown provider: ..."}`
- [x] AWS provider → `main.tf` contains `hashicorp/aws`, `region = var.region`
- [x] GCP provider → `main.tf` contains `hashicorp/google`, `project = var.project`
- [x] Azure provider → `main.tf` contains `hashicorp/azurerm`, `features {}`
- [x] DigitalOcean provider → `main.tf` contains `digitalocean/digitalocean`
- [x] Local backend → `main.tf` contains `backend "local"`
- [x] S3 backend → `main.tf` contains `backend "s3"`, bucket name includes project
- [x] GCS backend → `main.tf` contains `backend "gcs"`
- [x] Azure backend → `main.tf` contains `backend "azurerm"`
- [x] `variables.tf` generated with `project`, `environment`, `region`, `tags` variables
- [x] `environment` variable has validation block (`dev`, `staging`, `production`)
- [x] `outputs.tf` generated (template/placeholder)
- [x] `.gitignore` generated with `.terraform/`, `*.tfstate`, `*.tfplan`, `crash.log`
- [x] All 4 files have `overwrite=False`
- [x] Audit event logged on generation

#### 0.6.3 CLI Wrappers — `_run_terraform` & `_terraform_available` Audit

> Source: `terraform_ops.py::_run_terraform`, `_terraform_available`.
> Tests: `tests/test_terraform_actions.py` (mock `subprocess.run`).
>
> NOTE: All CLI wrapper tests use `unittest.mock.patch` to mock
> `subprocess.run`.  They never invoke real `terraform`.

- [x] `_terraform_available()` — CLI installed → `{available: True, version: "x.y.z"}`
- [x] `_terraform_available()` — CLI not installed → `{available: False}`
- [x] `_run_terraform()` calls `subprocess.run` with correct args, `cwd`, `timeout`

#### 0.6.4 Action Wrappers — Init, Plan, Apply, Destroy, Output, Fmt

> Source: `terraform_actions.py`.
> Tests: `tests/test_terraform_actions.py` (mock subprocess).

- [x] `terraform_init()` — success → `{ok: True, output: "..."}`
- [x] `terraform_init()` — no tf files → `{ok: False, error: "No Terraform files found"}`
- [x] `terraform_init()` — CLI not available → `{ok: False, error: "terraform CLI not available"}`
- [x] `terraform_init(upgrade=True)` — includes `-upgrade` flag
- [x] `terraform_init()` — timeout → error message
- [x] `terraform_apply()` — success → `{ok: True, output: "...", changes: {...}}`
- [x] `terraform_apply()` — not initialized → `{ok: False, error: "...not initialized..."}`
- [x] `terraform_apply(auto_approve=True)` — includes `-auto-approve` flag
- [x] `terraform_apply()` — timeout → error message
- [x] `terraform_plan()` — success → `{ok: True, changes: {...}, output: "..."}`
- [x] `terraform_plan()` — not initialized → error
- [x] `terraform_plan()` — with var-file support (parameter to add if missing)
- [x] `terraform_destroy()` — success → `{ok: True, output: "..."}`
- [x] `terraform_destroy()` — not initialized → error
- [x] `terraform_destroy(auto_approve=True)` — includes `-auto-approve` flag
- [x] `terraform_output()` — JSON parsed → `{ok: True, outputs: {key: {value, type, sensitive}}}`
- [x] `terraform_output()` — no outputs / no state → `{ok: True, outputs: {}}`
- [x] `terraform_fmt()` — success → `{ok: True, files: [...], count: N}`
- [x] `terraform_fmt()` — no tf files → error
- [x] All actions — audit event logged on success

#### 0.6.5 Observe — Validate, State, Workspaces

> Source: `terraform_ops.py::terraform_validate`, `terraform_state`,
> `terraform_workspaces`.
> Tests: `tests/test_terraform_actions.py` (mock subprocess).

- [x] `terraform_validate()` — valid → `{ok: True, valid: True, errors: []}`
- [x] `terraform_validate()` — invalid → `{ok: True, valid: False, errors: [{message, severity}]}`
- [x] `terraform_validate()` — CLI not available → error
- [x] `terraform_state()` — has resources → `{ok: True, resources: [...], count: N}`
- [x] `terraform_state()` — parses `module.x.type.name` addresses
- [x] `terraform_state()` — parses `data.type.name` addresses
- [x] `terraform_state()` — no state → `{ok: True, resources: [], count: 0}`
- [x] `terraform_workspaces()` — parses `* default` as current
- [x] `terraform_workspaces()` — multiple workspaces listed
- [x] `terraform_workspace_select()` — existing workspace → `{ok: True, created: False}`
- [x] `terraform_workspace_select()` — new workspace → fallback create → `{ok: True, created: True}`
- [x] `terraform_workspace_select()` — empty name → error

#### 0.6.6 Wizard — `setup_terraform()` Redesign

> Source: `wizard_setup.py::setup_terraform`.
> Tests: `tests/integration/test_terraform_integration.py`.
>
> ~~GAP: Current `setup_terraform()` generates only `main.tf` with inline
> templates.  It should delegate to `generate_terraform()` which produces
> `main.tf`, `variables.tf`, `outputs.tf`, and `.gitignore`.~~
> **FIXED**: `setup_terraform()` now delegates to `generate_terraform()`.

- [x] `setup_terraform()` delegates to `generate_terraform()` — not inline templates
- [x] `setup_terraform()` → creates 4 files: `main.tf`, `variables.tf`, `outputs.tf`, `.gitignore`
- [x] `setup_terraform()` → round-trip: generate → `terraform_status()` detects the files
- [x] AWS provider flows through → `main.tf` contains `hashicorp/aws`
- [x] GCP provider flows through → `main.tf` contains `hashicorp/google`
- [x] Azure provider flows through → `main.tf` contains `hashicorp/azurerm`
- [x] S3 backend flows through → `main.tf` contains `backend "s3"`
- [x] GCS backend flows through → `main.tf` contains `backend "gcs"`
- [x] Local backend flows through → `main.tf` contains `backend "local"`
- [x] Overwrite guard: existing `main.tf` + `overwrite=False` → error
- [x] Overwrite guard: existing `main.tf` + `overwrite=True` → success
- [x] Event recorded in `devops_cache` on success
- [x] `files_created` list in return matches what was written to disk

#### 0.6.7 Cleanup & Error Cases

> Tests: `tests/integration/test_terraform_integration.py::TestTerraformCleanup`.

- [x] `delete_generated_configs("terraform")` removes `terraform/` directory
- [x] `delete_generated_configs("terraform")` on empty project → no crash, empty deleted list
- [x] Detection without CLI → file-based detection still works (`has_terraform=True`, `cli.available=False`)
- [x] Invalid `.tf` file content (not valid HCL) → detection returns result (no crash), resources may be empty
- [x] `_find_tf_root` with no `.tf` files anywhere → returns `None`

#### 0.6.8 Round-Trip Integration

> Tests: `tests/integration/test_terraform_integration.py::TestTerraformRoundTrip`.

- [x] Generate (AWS/S3) → detect → status shows provider `aws`, backend `s3`, 4 files
- [x] Generate (GCP/GCS) → detect → status shows provider `google`, backend `gcs`
- [x] Generate (Azure/azurerm) → detect → status shows provider `azurerm`, backend `azurerm`
- [x] Generate → cleanup → detect → `has_terraform=False`

---

### 0.7 DNS/CDN

> **Strategy**: Same as 0.5/0.6 — audit existing code against the spec, write
> pessimistic tests, fix gaps.  Source of truth: PROJECT_SCOPE §4.6.
>
> **Source files**: `dns_cdn_ops.py`.
> **Test files**: `tests/test_dns_cdn_detect.py` (unit, file-based),
> `tests/test_dns_cdn_actions.py` (unit, mocked CLI),
> `tests/integration/test_dns_cdn_integration.py` (integration).

#### 0.7.1 Detection — `dns_cdn_status()` Audit

> Source: `dns_cdn_ops.py::dns_cdn_status`, `_detect_cdn_provider`,
> `_extract_domains_from_configs`.
> Tests: `tests/test_dns_cdn_detect.py`.

- [x] Empty project → `has_cdn=False`, `has_dns=False`, all lists empty
- [x] Return shape: `cdn_providers`, `domains`, `dns_files`, `ssl_certs`, `has_cdn`, `has_dns` — all keys present
- [x] CNAME file with domain → `has_dns=True`, domain in `domains`, `"CNAME"` in `dns_files`
- [x] CNAME file empty → domain not added
- [x] Cloudflare detected: `wrangler.toml` present → provider `cloudflare` in `cdn_providers`
- [x] Cloudflare detected: `cloudflare.json` present → provider `cloudflare` in `cdn_providers`
- [x] CloudFront detected: `.tf` file with `aws_cloudfront_distribution` → provider `cloudfront` in `cdn_providers`
- [x] Netlify detected: `netlify.toml` present → provider `netlify` in `cdn_providers`
- [x] Vercel detected: `vercel.json` present → provider `vercel` in `cdn_providers`
- [x] Fastly detected: `fastly.toml` present → provider `fastly` in `cdn_providers`
- [x] GitHub Pages detected: `CNAME` file → provider `github_pages` in `cdn_providers`
- [x] CDN detection via env var: `.env` with `CLOUDFLARE_API_TOKEN` → Cloudflare detected
- [x] CDN detection via env var: `.env` with `NETLIFY_AUTH_TOKEN` → Netlify detected
- [x] CDN provider result includes `id`, `name`, `detected_by`, `cli`, `cli_available`
- [x] Multiple CDN providers → all reported
- [x] DNS zone files detected: `*.zone`, `*.dns`, `db.*` → listed in `dns_files`
- [x] Skip directories respected: zone files in `.git/`, `node_modules/`, `.venv/` not scanned
- [x] SSL certificate files: `*.pem`, `*.crt` → listed in `ssl_certs` with `type: "certificate"`
- [x] SSL key files: `*.key` → listed in `ssl_certs` with `type: "private_key"`
- [x] Skip directories respected: certs in `node_modules/`, `.venv/` not scanned
- [x] Domain extraction from `netlify.toml` → domain in `domains`
- [x] Domain extraction from `vercel.json` → domain in `domains`
- [x] Domain extraction filters out `example.com`, `localhost`, `npmjs.com`, `github.com`

#### 0.7.2 DNS Lookup — `dns_lookup()` Audit

> Source: `dns_cdn_ops.py::dns_lookup`.
> Tests: `tests/test_dns_cdn_actions.py` (mock `subprocess.run`).
>
> NOTE: All lookup tests mock `subprocess.run`. They never invoke real `dig`.

- [x] Return shape: `ok`, `domain`, `records`, `cname`, `a_records`, `nameservers`, `record_count`
- [x] `dig` not available → `{ok: False, error: "dig command not available"}`
- [x] A record lookup → `{type: "A", value: "1.2.3.4"}` in records, `"1.2.3.4"` in `a_records`
- [x] CNAME lookup → `{type: "CNAME", value: "target.example.com"}` in records, `cname` field set
- [x] CNAME trailing dot stripped
- [x] MX record lookup → `{type: "MX", value: "10 mail.example.com"}` in records
- [x] TXT record lookup → `{type: "TXT", value: "v=spf1 ..."}` in records, quotes stripped
- [x] NS record lookup → `{type: "NS", value: "ns1.example.com"}` in records, trailing dot stripped, in `nameservers`
- [x] Multiple A records → all listed
- [x] No records → `{ok: True, records: [], record_count: 0}`
- [x] Timeout on dig → graceful handling (no crash, partial results)

#### 0.7.3 SSL Check — `ssl_check()` Audit

> Source: `dns_cdn_ops.py::ssl_check`.
> Tests: `tests/test_dns_cdn_actions.py` (mock `subprocess.run`).

- [x] Return shape: `ok`, `domain`, `valid`, `issuer`, `expiry`
- [x] `openssl` not available → `{ok: False, error: "openssl not available"}`
- [x] Valid cert → `{ok: True, valid: True, issuer: "...", expiry: "..."}`
- [x] Timeout → `{ok: False, error: "..."}`

#### 0.7.4 DNS Record Generation — `generate_dns_records()` Audit

> Source: `dns_cdn_ops.py::generate_dns_records`.
> Tests: `tests/test_dns_cdn_detect.py::TestGenerateDnsRecords`.

- [x] Return shape: `ok`, `domain`, `records`, `record_count`, `zone_file`
- [x] A record with target_ip → `{type: "A", name: "@"}` and `{type: "A", name: "www"}` with correct IP
- [x] CNAME with cname_target → `{type: "CNAME", name: "www"}` with target
- [x] No target_ip and no cname_target → no A/CNAME records
- [x] Google mail → 5 MX records (aspmx.l.google.com, alt1, alt2, alt3, alt4)
- [x] Protonmail mail → 2 MX records (mail.protonmail.ch, mailsec.protonmail.ch)
- [x] No mail provider → no MX records
- [x] SPF included by default → TXT record with `v=spf1`
- [x] SPF with Google → includes `_spf.google.com`
- [x] SPF with Protonmail → includes `_spf.protonmail.ch`
- [x] SPF disabled → no SPF TXT record
- [x] DMARC included by default → TXT record with `v=DMARC1`, `_dmarc` name
- [x] DMARC disabled → no DMARC TXT record
- [x] Zone file generated: starts with `$ORIGIN domain.`
- [x] Zone file generated: contains `$TTL 300`
- [x] Zone file contains all records in BIND format
- [x] Audit event logged on generation
- [x] record_count matches length of records list

#### 0.7.5 Round-Trip & Error Cases

> Tests: `tests/integration/test_dns_cdn_integration.py`.

- [x] Empty project → detection returns clean result (no crash)
- [x] CDN + domain detection round-trip: create config files → detect → status correct
- [x] Generate records → zone file is valid BIND format
- [x] Multiple CDN providers in same project → all detected
- [x] CNAME + netlify.toml + certs → all three types detected together

---

## Layer 1 — Two-Domain Chains

Every pair of domains that can interact.

### 1.1 Docker + K8s

> **Source files**: `docker_detect.py`, `k8s_generate.py`, `k8s_wizard.py`.
> **Test file**: `tests/integration/test_docker_k8s_chain.py`.
>
> Tests how Docker detection output feeds into K8s manifest generation.
> Split into **parameter pass-through** (existing code) and **auto-wiring**
> (requires a helper function to bridge the two domains).

#### 1.1a Parameter Pass-Through (existing API)

- [x] `generate_manifests(image="myapp:v1")` → Deployment YAML contains `image: myapp:v1`
- [x] `generate_manifests(port=3000)` → Service YAML contains `port: 3000`
- [x] `generate_manifests()` with no image → defaults to `{app_name}:latest`
- [x] `wizard_state_to_resources()` with service `image: "myapp:v1"` → resource spec has `image: myapp:v1`
- [x] `wizard_state_to_resources()` with service `port: 3000` → Service resource has port 3000
- [x] `wizard_state_to_resources()` with multiple services → each gets its own Deployment + Service

#### 1.1b Auto-Wiring (cross-domain bridge)

> RESOLVED: `docker_k8s_bridge.docker_to_k8s_services()` bridges
> docker_status() → K8s-ready service defs.

- [x] Docker Dockerfile with `EXPOSE 8080` → K8s manifest port=8080 (via bridge)
- [x] Docker compose service `web` with `image: myapp:v1` → K8s Deployment image=`myapp:v1`
- [x] Docker compose service `web` with `ports: ["3000:3000"]` → K8s Service port=3000
- [x] Docker compose with 2 services → K8s generates 2 Deployments + 2 Services
- [x] Docker compose service with `build: .` → K8s uses `{service_name}:latest` as image
- [x] Docker Dockerfile with multi-stage build → K8s uses final stage image name
- [x] Docker compose service with registry prefix `ghcr.io/org/app:v1` → K8s image matches exactly
- [x] Docker compose `build.args` → K8s ConfigMap includes matching keys
- [x] Enable Docker first, generate K8s second → K8s manifests reference Docker images
- [x] Enable K8s first (placeholder images), then Docker → K8s can be regenerated with real Docker images

### 1.2 Docker + CI/CD

> **Source files**: `generators/github_workflow.py`, `docker_detect.py`.
> **New code**: `docker_ci_job()` in `generators/github_workflow.py`.
> **Test file**: `tests/integration/test_docker_ci_chain.py`.
>
> Tests how Docker detection output feeds into CI workflow generation.

- [x] Docker detected → CI workflow includes a `docker` job with `docker build`
- [x] Docker + GHCR registry → CI has `docker/login-action` with `registry: ghcr.io` + `docker push`
- [x] Docker + DockerHub registry → CI has `docker/login-action` with DockerHub + `docker push`
- [x] Docker + custom registry → CI has `docker/login-action` with custom registry URL + `docker push`
- [x] Docker + no registry → CI has `docker build` only, no `docker push`
- [x] Docker + Buildx → CI includes `docker/setup-buildx-action`
- [x] Docker + build args → CI passes `--build-arg` for each arg
- [x] Docker + layer caching → CI uses `cache-from: type=gha` / `cache-to: type=gha`
- [x] Docker + image tagging → CI tags with `${{ github.sha }}` and `latest`
- [x] Docker CI job depends on test job (`needs: [test]`)
- [x] Docker CI job only builds on `push` to `main`, not PRs
- [x] Docker image name derived from project name or compose service
- [x] Multiple Docker services → CI builds each image separately
- [x] Generated workflow is valid YAML
- [x] Docker job uses `actions/checkout@v4`
- [x] Return shape: `{ok: True, file: {path, content, ...}}`

### 1.3 Docker + Skaffold

> **Source files**: `k8s_wizard_generate.py` (`_generate_skaffold`).
> **Test file**: `tests/integration/test_docker_skaffold_chain.py`.
>
> The Skaffold generator already reads Docker config from wizard state.
> Tests verify the cross-domain wiring works end-to-end.

- [x] Service with `image: "myapp:v1"` + `dockerfile: "Dockerfile"` → Skaffold artifact has matching image + docker.dockerfile
- [x] Service with `buildArgs: {VERSION: "1.0"}` → Skaffold artifact.docker.buildArgs matches
- [x] Service with `buildTarget: "prod"` → Skaffold artifact.docker.target = "prod"
- [x] Multiple services → multiple Skaffold build artifacts
- [x] Service with no image → Skaffold skips that service (no artifact)
- [x] Service with kind=Skip → Skaffold skips entirely
- [x] Skaffold build.local.push = false (default local dev)
- [x] Skaffold build.local.useBuildkit = true

### 1.4 Docker + Helm

> **Source files**: `k8s_wizard_generate.py` (`_build_helm_releases`).
> **Test file**: `tests/integration/test_docker_skaffold_chain.py` (same file).
>
> Helm releases in Skaffold wire Docker images through setValues.

- [x] Service with image → Helm release created with name matching service
- [x] Namespace → Helm release.namespace matches
- [x] helmChartPath → Helm release.chartPath matches
- [x] helmValuesFiles → Helm release.valuesFiles matches
- [x] Env vars (hardcoded) → Helm release.setValues includes them
- [x] Env vars (variable type) → Helm release.setValueTemplates includes them

### 1.5 K8s + CI/CD (kubectl)

> **New code**: `_kubectl_deploy_ci_job()` in `generators/github_workflow.py`.
> **Test file**: `tests/integration/test_k8s_ci_chain.py`.

- [x] K8s + kubectl → CI has `kubectl apply -f <manifest_dir>/` step
- [x] K8s manifest dir → CI references it in apply command
- [x] K8s namespace → CI uses `-n <namespace>` flag
- [x] Deploy job depends on docker build job or test job (`needs:`)
- [x] Deploy job sets up kubeconfig from `${{ secrets.KUBECONFIG }}`
- [x] Deploy job runs `kubectl diff` or `--dry-run=server` before apply
- [x] Deploy job runs `kubectl rollout status` after apply
- [x] Deploy job only runs on `push` to `main`
- [x] Generated YAML is valid

### 1.6 K8s + CI/CD (Skaffold)

> **New code**: `_skaffold_deploy_ci_job()` in `generators/github_workflow.py`.
> **Test file**: `tests/integration/test_k8s_ci_chain.py`.

- [x] K8s + skaffold → CI has `skaffold run` step
- [x] CI installs skaffold CLI
- [x] No raw `kubectl apply` in CI output
- [x] Skaffold profile via `--profile <env>` flag
- [x] Skaffold `--default-repo` from config
- [x] Custom skaffold file path → `--filename <path>`
- [x] Deploy job sets up kubeconfig
- [x] Deploy job only runs on `push` to `main`
- [x] Generated YAML is valid

### 1.7 K8s + CI/CD (Helm)

> **New code**: `_helm_deploy_ci_job()` in `generators/github_workflow.py`.
> **Test file**: `tests/integration/test_k8s_ci_chain.py`.

- [x] K8s + helm → CI has `helm upgrade --install` step
- [x] Chart path referenced
- [x] Release name matches service
- [x] Values file per environment (`-f values-<env>.yaml`)
- [x] `--set image.tag=${{ github.sha }}` in command
- [x] Namespace via `--namespace`
- [x] No `kubectl apply` in CI output
- [x] No `skaffold` in CI output
- [x] Deploy job sets up kubeconfig
- [x] Deploy job only runs on `push` to `main`
- [x] Generated YAML is valid
- [x] Deploy job depends on docker build or test

### 1.8 K8s + Skaffold

> **Existing code**: `_generate_skaffold()` in `k8s_wizard_generate.py`.
> **Test file**: `tests/integration/test_k8s_skaffold_chain.py`.

- [x] K8s manifests → referenced in skaffold.yaml rawYaml manifests section
- [x] K8s services → Skaffold build artifacts (one per service with image)
- [x] K8s namespace → Skaffold deploy.kubectl.defaultNamespace
- [x] K8s namespace → Skaffold flags.global `--namespace`
- [x] Generated K8s manifest paths → Skaffold manifests.rawYaml list
- [x] Skaffold disabled (skaffold=False) → returns None
- [x] No artifacts when no services have images → build section empty or absent
- [x] Multiple services → multiple artifacts
- [x] Dockerfile override → artifact docker.dockerfile
- [x] Build args flow through → artifact docker.buildArgs
- [x] Deploy strategy=kubectl → deploy.kubectl section present
- [x] Deploy strategy=helm → deploy.helm.releases present
- [x] Deploy strategy=kustomize → manifests.kustomize paths present
- [x] Tag policy flows through → build.tagPolicy
- [x] Generated YAML is valid

### 1.9 K8s + Helm

> **Existing code**: `generate_helm_chart()` in `k8s_helm_generate.py`.
> **Test file**: `tests/integration/test_k8s_helm_chain.py`.

- [x] K8s services → Helm values.yaml (image.repository, image.tag, service.port, replicaCount)
- [x] K8s namespace → Helm release namespace in Skaffold helm releases
- [x] K8s env vars (literal) → Helm values.yaml env list
- [x] K8s env vars (secret) → Helm existingSecret reference
- [x] Chart.yaml has correct apiVersion, name, description, appVersion
- [x] templates/ includes deployment.yaml, service.yaml, ingress.yaml, _helpers.tpl, NOTES.txt
- [x] Configmap template generated only when literal env vars exist
- [x] Secret template generated only when secret env vars exist
- [x] Helm chart disabled (helm_chart=False) → returns empty files list
- [x] Per-environment values-{env}.yaml generated for each environment
- [x] .helmignore file generated
- [x] values.yaml ingress.enabled reflects data.ingress_host
- [x] Chart name sanitized to DNS-label format
- [x] Generated YAML files are all valid

### 1.10 K8s + Terraform

> **Spec grounding**: TECHNOLOGY_SPEC §3.4 Facilitate = "Generate IaC from needs".
> K8s wizard knows cluster/namespace/service needs → Terraform provisions them.
> **New code**: `generate_terraform_k8s()` in `terraform_generate.py`.
> **New data**: `catalogs/terraform_k8s.json` (HCL templates per provider).
> **Test file**: `tests/integration/test_k8s_terraform_chain.py`.

#### Provider routing
- [x] provider=aws → EKS cluster + ECR registry resources
- [x] provider=google → GKE cluster + Artifact Registry resources
- [x] provider=azurerm → AKS cluster + ACR resources
- [x] Unknown provider → error dict, no crash

#### Namespace flow
- [x] K8s namespace → `kubernetes_namespace` resource in k8s.tf
- [x] No namespace → no namespace resource generated

#### Service → Registry
- [x] Services with images → container registry resource(s)
- [x] No services / no images → no registry resource
- [x] Multiple services → single registry (not one per service)

#### Outputs for K8s
- [x] `cluster_endpoint` output always present
- [x] `cluster_ca_certificate` output always present
- [x] `kubeconfig_command` output always present (provider-specific)
- [x] `registry_url` output present when registry generated

#### Variables
- [x] namespace variable propagated from wizard state
- [x] node_count variable with default
- [x] node_size variable with provider-appropriate default
- [x] project_name variable
- [x] region variable with provider default

#### File structure
- [x] Generates terraform/main.tf (cluster + providers)
- [x] Generates terraform/variables.tf
- [x] Generates terraform/outputs.tf (cross-domain outputs)
- [x] Generates terraform/k8s.tf (namespace resource + kubernetes provider)
- [x] Generates terraform/.gitignore
- [x] All generated content is syntactically plausible HCL
- [x] Uses GeneratedFile model (same pattern as generate_terraform)

### 1.11 CI/CD + Terraform

> **Spec grounding**: PROJECT_SCOPE §4.3 Facilitate = "Generate workflows from detected stacks" (❌ MISSING).
> TECHNOLOGY_SPEC §5.3 Facilitate = "Generate workflows, suggest test/deploy steps".
> **New code**: `_terraform_ci_job()` + `generate_terraform_ci()` in `github_workflow.py`.
> **Wire**: `generate_terraform_workflow()` in `ci_ops.py`.
> **Test file**: `tests/integration/test_ci_terraform_chain.py`.

#### Workflow structure
- [x] Generates `.github/workflows/terraform.yml`
- [x] Workflow triggers on push to main AND pull_request
- [x] Generated YAML is valid
- [x] Uses GeneratedFile model

#### PR vs push branching
- [x] PR → terraform plan only (no apply)
- [x] Push to main → terraform apply -auto-approve
- [x] Plan step always runs (both PR and push)
- [x] Apply step has `if: github.event_name == 'push'` guard

#### Terraform steps
- [x] terraform init step present
- [x] terraform validate step present
- [x] terraform plan step present
- [x] terraform apply step present (guarded)
- [x] Steps run in correct order: init → validate → plan → apply

#### Backend credentials
- [x] AWS provider → `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` secrets
- [x] Google provider → `GOOGLE_CREDENTIALS` secret
- [x] Azure provider → `ARM_CLIENT_ID` + `ARM_CLIENT_SECRET` + `ARM_TENANT_ID` + `ARM_SUBSCRIPTION_ID`
- [x] Credentials injected via `env:` block on job

#### Workspace / environments
- [x] Single workspace → no workspace select step
- [x] Multiple workspaces → workspace select step per environment
- [x] Working directory set to terraform/ subdirectory

### 1.12 Skaffold + Helm

> **Spec grounding**: PROJECT_SCOPE §4.2 Facilitate = "Generate Skaffold config (build, deploy, profiles, portForward, envsubst hooks)".
> **Existing code**: `_generate_skaffold()` already routes `deployStrategy="helm"` → `deploy.helm.releases`.
> **Gap**: Integration test coverage is thin (1 test). Expanding to evidence the full chain.
> **Test file**: `tests/integration/test_skaffold_helm_chain.py`.

#### Helm deployer routing
- [x] deployStrategy=helm → deploy.helm.releases present, NOT deploy.kubectl
- [x] deployStrategy=kubectl → deploy.kubectl present, NOT deploy.helm

#### Build + Helm deploy together
- [x] Build artifacts present alongside Helm deploy in same doc
- [x] Multiple services → multiple build artifacts + Helm releases

#### Helm release properties
- [x] Namespace propagated to Helm release → release.namespace
- [x] createNamespace=true when namespace present
- [x] Custom chartPath flows to release.chartPath
- [x] valuesFiles flow to release.valuesFiles
- [x] helmSecretsPlugin → release.useHelmSecrets

#### Env vars → Helm setValues
- [x] Literal env vars → release.setValues
- [x] Variable/secret env vars → release.setValueTemplates (Go template syntax)
- [x] Mixed env vars → both setValues and setValueTemplates

### 1.13 DNS + CI/CD

> **Spec grounding**: TECHNOLOGY_SPEC §DNS/CDN = "Records, SSL status → Generate configs → Update, purge, renew".
> PROJECT_SCOPE §4.6 Facilitate = "Generate DNS records, BIND zone files".
> **New code**: `_dns_verify_ci_step()` + `_cdn_purge_ci_step()` + `generate_deploy_post_steps()` in `github_workflow.py`.
> **Test file**: `tests/integration/test_dns_ci_chain.py`.

#### DNS verification step
- [x] DNS verify step present in workflow
- [x] Uses `dig` to check domain resolution
- [x] Verifies multiple domains if configured
- [x] Step runs after deploy

#### CDN cache purge step
- [x] Cloudflare → wrangler pages purge or API call
- [x] CloudFront → `aws cloudfront create-invalidation`
- [x] Netlify → purge via netlify CLI
- [x] CDN provider credentials via secrets
- [x] Purge step runs after deploy

#### Workflow structure
- [x] Generates `.github/workflows/post-deploy.yml`
- [x] Valid YAML output
- [x] Uses GeneratedFile model
- [x] project_name flows into workflow name

### 1.14 Docker + Terraform

> **Spec grounding**: Terraform provisions container registries (ECR/GAR/ACR) → Docker CI needs matching login config.
> **Existing code**: `generate_terraform_k8s()` outputs `registry_url`. `generate_docker_ci()` accepts `registry_type`.
> **Gap**: No bridge function mapping Terraform provider → Docker CI registry config.
> **New code**: `terraform_to_docker_registry()` in `terraform_generate.py` (cross-domain bridge).
> **Test file**: `tests/integration/test_docker_terraform_chain.py`.

#### Provider → registry mapping
- [x] AWS → ECR registry type with ECR login action
- [x] Google → GAR registry type with gcloud auth
- [x] Azure → ACR registry type with ACR login
- [x] Returns registry URL pattern from Terraform output

#### Docker CI integration
- [x] Bridge output feeds into generate_docker_ci registry param
- [x] Registry URL includes provider-specific format (ECR URL, GAR URL, ACR URL)
- [x] Credentials mapped to correct secrets per provider

#### Cross-domain outputs
- [x] registry_url from Terraform → Docker push target
- [x] Provider detected from Terraform config automatically

---

## Spec Gap Fix — 0.4 Helm Round-Trip + 0.5 CI/CD Compose

> **Rationale**: PROJECT_SCOPE §4.2 and §4.3 had gaps. Helm Facilitate was implemented
> but not spec-tracked. CI/CD Facilitate has individual generators but no compose
> orchestration. These must be solid before Layer 2 chains.

### 0.4.close — Helm round-trip (close out)

> Helm generation exists. Only gap: prove generate → detect round-trip works.
> **Test file**: `tests/integration/test_helm_roundtrip.py`.

- [x] Generate chart via `generate_helm_chart()` → run `_detect_helm_charts()` on output
- [x] Detected chart has correct name, version, description
- [x] Detected chart has_values, has_templates flags True
- [x] Per-env values files detected in env_values_files list

### 0.5 — CI/CD Compose Function

> **New code**: `compose_ci_workflows()` in `src/core/services/ci_compose.py`.
> **Test file**: `tests/integration/test_ci_compose_chain.py`.

#### 0.5.1 — Basic structure
- [x] Accepts wizard state, returns list[GeneratedFile]
- [x] strategy="unified" → single ci-cd.yml with all jobs
- [x] strategy="split" → separate files with workflow_run links
- [x] Returns empty list when no CI-relevant config present

#### 0.5.2 — Job dependency chains
- [x] test → build → deploy ordering via `needs:`
- [x] Image tag passed from build to deploy (${{ github.sha }})
- [x] PR: test-only jobs. Push to main: full pipeline
- [x] Deploy jobs have `if: github.event_name == 'push'`

#### 0.5.3 — Domain integration
- [x] stack_names → correct test jobs in output
- [x] docker_services → correct build jobs in output
- [x] deploy_config (kubectl) → kubectl deploy job
- [x] deploy_config (helm) → helm deploy job
- [x] deploy_config (skaffold) → skaffold deploy job
- [x] terraform_config → infra job before deploy
- [x] dns/cdn config → post-deploy steps

#### 0.5.4 — Multi-environment
- [x] Per-env deploy jobs when environments configured
- [x] Environment-specific namespace in deploy jobs
- [x] Environment-specific values file for Helm deploys

---

## Layer 2 — Three-Domain Chains

### 2.1 Docker + K8s + CI/CD
- [x] Full pipeline: test → docker build → docker push → kubectl apply
- [x] Full pipeline: test → docker build → docker push → skaffold run
- [x] Full pipeline: test → docker build → docker push → helm upgrade
- [x] Job dependency chain: test → build → deploy
- [x] Docker image tag passed from build to deploy job
- [x] Deploy only on push to main, not on PRs
- [x] PRs run tests only

### 2.2 Docker + K8s + Skaffold
- [x] Skaffold builds Docker image and deploys K8s manifests
- [x] Docker registry → Skaffold --default-repo → K8s image pull
- [x] Skaffold profiles select different K8s manifests per env

### 2.3 Docker + K8s + Helm
- [x] Docker image → Helm values → K8s Deployment
- [x] Docker registry → Helm image.repository
- [x] Docker tag → Helm image.tag
- [x] Helm values per env → different Docker tags per env

### 2.4 Docker + K8s + Terraform
- [x] Terraform provisions cluster + registry
- [x] Docker builds and pushes to provisioned registry
- [x] K8s deploys to provisioned cluster

### 2.5 K8s + CI/CD + Multi-Environment
- [x] All environments referenced in CI
- [x] Namespace per environment
- [x] Deploy ordering: dev → staging → production
- [x] Production deploy constrained to main branch
- [x] Per-environment secrets in CI
- [x] Per-environment kubeconfig
- [x] Skaffold profiles per env in CI
- [x] Helm values per env in CI

### 2.6 K8s + Terraform + CI/CD
- [x] CI does terraform plan → terraform apply → kubectl apply
- [x] Terraform provisions, then K8s deploys, in single workflow
- [x] Terraform state and kubeconfig both from secrets

---

## Layer 3 — Full Stack Chains

### 3.1 Docker + K8s + Skaffold + CI/CD + Multi-Env
- [x] Wizard: enable Docker → enable K8s with Skaffold → enable CI/CD
- [x] CI: test → docker build (via Skaffold) → deploy per env (via Skaffold profiles)
- [x] Each env: different Skaffold profile, different namespace, different secrets
- [x] PR: test only. Push to main: full pipeline

### 3.2 Docker + K8s + Helm + CI/CD + Multi-Env
- [x] Wizard: enable Docker → enable K8s with Helm → enable CI/CD
- [x] CI: test → docker build → docker push → helm upgrade per env
- [x] Each env: different values file, different namespace
- [x] Helm --set image.tag=${{ github.sha }}
- [x] PR: test only. Push to main: full pipeline

### 3.3 Docker + K8s + Terraform + CI/CD
- [x] CI: terraform plan/apply → docker build/push → k8s deploy
- [x] Terraform outputs feed into K8s config (cluster endpoint, registry URL)

### 3.4 Everything
- [x] Docker + K8s (Helm or Skaffold) + Terraform + CI/CD + DNS + Multi-Env
- [x] Complete wizard flow: detect → configure → generate → validate → deploy
- [x] Cleanup: delete all generated configs → clean slate

---

## Layer 4 — Order of Execution Variants

### 4.1 Docker first
- [x] Enable Docker → then K8s → K8s picks up Docker image
- [x] Enable Docker → then CI → CI picks up Docker build steps
- [x] Enable Docker → then K8s → then CI → CI has full pipeline

### 4.2 K8s first
- [x] Enable K8s (no Docker yet) → plain manifests with external image
- [x] Enable K8s → then Docker → manifests updated with Docker image
- [x] Enable K8s → then Docker → then CI → full pipeline

### 4.3 CI first
- [x] Enable CI alone → basic test-only workflow
- [x] Enable CI → then Docker → CI updated with Docker build
- [x] Enable CI → then K8s → CI updated with deploy steps
- [x] Enable CI → then Docker → then K8s → CI has full pipeline

### 4.4 Terraform first
- [x] Enable Terraform → then K8s → K8s uses Terraform-provisioned cluster
- [x] Enable Terraform → then Docker → Docker uses Terraform-provisioned registry

### 4.5 Re-run after changes
- [x] Change Docker registry → CI updates
- [x] Change K8s deploy method (kubectl → helm) → CI updates
- [x] Add environment → CI adds deploy job
- [x] Remove environment → CI removes deploy job
- [x] Disable Docker → CI removes Docker steps

---

## Layer 5 — Error & Edge Cases

### 5.1 Missing Tools
- [x] Docker enabled but docker CLI missing → clear message, install button
- [x] K8s enabled but kubectl missing → clear message, install button
- [x] Skaffold enabled but skaffold CLI missing → clear message, install button
- [x] Helm enabled but helm CLI missing → clear message, install button
- [x] Terraform enabled but terraform CLI missing → clear message, install button

### 5.2 Misconfiguration
- [x] Docker registry URL malformed → validation error
- [x] K8s namespace with invalid characters → validation error
- [x] Helm chart path doesn't exist → warning
- [x] Skaffold profiles reference nonexistent manifests → warning
- [x] CI references secrets that don't exist → warning in generated YAML comments

### 5.3 Partial State
- [x] Wizard interrupted mid-flow → state saved, resumable
- [x] Some files generated, some not → detection handles partial state
- [x] Generated files manually edited → detect picks up changes

### 5.4 Cleanup
- [x] `delete_generated_configs("docker")` → removes Docker files only
- [x] `delete_generated_configs("k8s")` → removes K8s files only
- [x] `delete_generated_configs("ci")` → removes CI files only
- [x] `delete_generated_configs("skaffold")` → removes skaffold.yaml only
- [x] `delete_generated_configs("terraform")` → removes tf files only
- [x] Cleanup one domain → others untouched
- [x] Re-setup after cleanup → works cleanly
