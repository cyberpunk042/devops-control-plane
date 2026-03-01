# k8s/ — Kubernetes Service Package

> Detection, validation, cluster operations, manifest generation, wizard pipeline, Helm operations.

## Architecture

```
k8s/
├── __init__.py              — public API re-exports
├── common.py                — shared constants, _run_kubectl, _parse_k8s_yaml
├── detect.py                — offline YAML/Helm/Kustomize scanning, tool availability
├── cluster.py               — online kubectl interactions (pods, events, scale, apply)
├── helm.py                  — Helm CLI operations (list, install, upgrade, template)
├── pod_builder.py           — probes, volumes, env vars, mesh annotations
├── generate.py              — manifest templates + re-exports from pod_builder
├── wizard.py                — wizard state translator + persistence
├── wizard_detect.py         — Skaffold status, namespace mapping
├── wizard_generate.py       — Skaffold/Kustomize generation from wizard state
├── helm_generate.py         — full Helm chart directory generation
├── validate.py              — orchestrator (imports 7 layer validators)
├── validate_structural.py   — L1: per-resource structural checks
├── validate_cross_resource.py — L2: cross-resource consistency
├── validate_env_aware.py    — L3: environment-aware checks
├── validate_cluster.py      — L4: cluster-aware checks (online)
├── validate_security.py     — L5: security & production readiness
├── validate_cross_domain.py — L6: cross-domain (Docker ↔ K8s ↔ CI ↔ Terraform ↔ Envs)
└── validate_strategy.py     — L7: deployment strategy validation
```

## Module Roles

### Core (Observe)

| Module | Lines | Purpose |
|--------|-------|---------|
| `common.py` | ~110 | Shared constants (`_K8S_API_VERSIONS`, `_K8S_KINDS`, `_MANIFEST_DIRS`), `_run_kubectl`, `_parse_k8s_yaml`. Must NOT import from siblings. |
| `detect.py` | ~640 | Offline scanning: YAML manifests, Helm charts, Kustomize, CLI tool availability, infra service detection. |
| `cluster.py` | ~470 | Live kubectl queries: nodes, namespaces, pods, events, logs, apply, scale, describe, storage classes. |

### Generate (Create)

| Module | Lines | Purpose |
|--------|-------|---------|
| `pod_builder.py` | ~560 | Reusable pod template construction: probes, volumes, env vars, mesh annotations. |
| `generate.py` | ~200 | Manifest templates (Deployment, Service, Ingress, Namespace) + re-exports from pod_builder. |
| `helm_generate.py` | ~510 | Full Helm chart generation: Chart.yaml, values.yaml, templates, env overrides. |

### Wizard (Pipeline)

| Module | Lines | Purpose |
|--------|-------|---------|
| `wizard.py` | ~565 | Wizard state → K8s resources translator + state persistence (load/save/wipe). |
| `wizard_detect.py` | ~185 | Skaffold config detection, environment↔namespace mapping. |
| `wizard_generate.py` | ~800 | Skaffold/Kustomize generation from wizard resource definitions. |

### Helm Ops

| Module | Lines | Purpose |
|--------|-------|---------|
| `helm.py` | ~175 | Helm CLI wrapper: list, values, install, upgrade, template. |

### Validation (7 Layers)

| Module | Lines | Layer | Purpose |
|--------|-------|-------|---------|
| `validate.py` | ~140 | Orchestrator | Runs L1–L7 in sequence, collects issues |
| `validate_structural.py` | ~350 | L1 | Per-resource checks (Deployment, Service, Pod, HPA, etc.) |
| `validate_cross_resource.py` | ~400 | L2 | Selector ↔ label matching, port alignment, Secret/CM/PVC refs |
| `validate_env_aware.py` | ~235 | L3 | Prod safety, dev convenience, namespace mapping |
| `validate_cluster.py` | ~220 | L4 | Online cluster checks, API version compat, storage classes |
| `validate_security.py` | ~280 | L5 | Pod security, RBAC, privilege, production readiness |
| `validate_cross_domain.py` | ~1,275 | L6 | Docker ↔ K8s ↔ CI ↔ Terraform ↔ Environments seams |
| `validate_strategy.py` | ~1,145 | L7 | Raw kubectl, Helm, Kustomize, Skaffold strategy checks |

## Dependency Graph

```
common.py (foundation — no siblings)
├── detect.py
├── cluster.py
└── validate*.py (L1–L7)

pod_builder.py (standalone)
└── generate.py
    ├── wizard.py
    └── wizard_generate.py

wizard_detect.py (standalone)
└── wizard.py (re-exports)

helm.py (standalone)
helm_generate.py (standalone)
```

## Consumers

| Consumer | Import Path | Notes |
|----------|------------|-------|
| `routes/k8s.py` | `k8s_ops` (shim) | Uses `k8s_ops.X` attribute access |
| `ui/cli/k8s.py` | `k8s_ops` (shim) | Named imports |
| `wizard/helpers.py` | `k8s.detect` (direct) | `k8s_status` |
| `wizard/setup_infra.py` | `k8s` + `k8s.helm_generate` (direct) | wizard_state_to_resources, generate_helm_chart |

## Backward Compatibility

`src/core/services/k8s_ops.py` remains as a thin shim:

```python
from src.core.services.k8s import *  # noqa: F401, F403
```

All existing `from src.core.services.k8s_ops import X` continues to work.
