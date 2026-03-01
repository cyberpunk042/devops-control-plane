"""
Kubernetes — detection, validation, cluster ops, generation, wizard, Helm.

Sub-modules::

    common.py           — shared constants, _run_kubectl, _parse_k8s_yaml
    detect.py           — offline YAML/Helm/Kustomize scanning, tool availability
    cluster.py          — online kubectl interactions (pods, events, scale, apply)
    helm.py             — Helm CLI operations (list, install, upgrade, template)
    pod_builder.py      — probes, volumes, env vars, mesh annotations
    generate.py         — manifest templates + re-exports from pod_builder
    wizard.py           — wizard state translator + persistence
    wizard_detect.py    — Skaffold status, namespace mapping
    wizard_generate.py  — manifest generation from wizard resource definitions
    helm_generate.py    — full Helm chart directory generation
    validate.py         — 7-layer structural and cross-domain validation

Public re-exports below keep ``from src.core.services.k8s import X`` working.
The legacy ``k8s_ops.py`` facade also re-exports from here for backward compat.
"""

from __future__ import annotations

# ── Shared constants & helpers ──
from .common import (  # noqa: F401
    _SKIP_DIRS,
    _K8S_API_VERSIONS,
    _K8S_KINDS,
    _MANIFEST_DIRS,
    _run_kubectl,
    _kubectl_available,
    _parse_k8s_yaml,
)

# ── Detect ──
from .detect import (  # noqa: F401
    k8s_status,
    _collect_yaml_files,
    _detect_helm_charts,
    _detect_kustomize,
)

# ── Validate ──
from .validate import (  # noqa: F401
    validate_manifests,
)

# ── Cluster ──
from .cluster import (  # noqa: F401
    cluster_status,
    get_resources,
    k8s_pod_logs,
    k8s_apply,
    k8s_delete_resource,
    k8s_scale,
    k8s_events,
    k8s_describe,
    k8s_namespaces,
    k8s_storage_classes,
)

# ── Helm ──
from .helm import (  # noqa: F401
    helm_list,
    helm_values,
    helm_install,
    helm_upgrade,
    helm_template,
)

# ── Generate ──
from .generate import (  # noqa: F401
    generate_manifests,
)

# ── Wizard ──
from .wizard import (  # noqa: F401
    skaffold_status,
    k8s_env_namespaces,
    wizard_state_to_resources,
    generate_k8s_wizard,
    _generate_skaffold,
    load_wizard_state,
    save_wizard_state,
    wipe_wizard_state,
)

# ── Helm chart generation ──
from .helm_generate import (  # noqa: F401
    generate_helm_chart,
)
