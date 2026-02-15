"""
Kubernetes operations — backward-compat re-export hub.

All shared constants and helpers live in ``k8s_common``.
Feature code lives in ``k8s_detect``, ``k8s_validate``, ``k8s_cluster``,
``k8s_helm``, ``k8s_generate``, and ``k8s_wizard``.

This module re-exports every public symbol so that existing consumers
(``from k8s_ops import X`` or ``k8s_ops.X``) continue to work.
"""

from __future__ import annotations

# ── Shared constants & helpers (also re-exported) ──
from src.core.services.k8s_common import (  # noqa: F401
    _SKIP_DIRS,
    _K8S_API_VERSIONS,
    _K8S_KINDS,
    _MANIFEST_DIRS,
    _run_kubectl,
    _kubectl_available,
    _parse_k8s_yaml,
)

# ── Detect ──
from src.core.services.k8s_detect import (  # noqa: F401
    k8s_status,
    _collect_yaml_files,
    _detect_helm_charts,
    _detect_kustomize,
)

# ── Validate ──
from src.core.services.k8s_validate import (  # noqa: F401
    validate_manifests,
)

# ── Cluster ──
from src.core.services.k8s_cluster import (  # noqa: F401
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
from src.core.services.k8s_helm import (  # noqa: F401
    helm_list,
    helm_values,
    helm_install,
    helm_upgrade,
    helm_template,
)

# ── Generate ──
from src.core.services.k8s_generate import (  # noqa: F401
    generate_manifests,
)

# ── Wizard ──
from src.core.services.k8s_wizard import (  # noqa: F401
    skaffold_status,
    k8s_env_namespaces,
    wizard_state_to_resources,
    generate_k8s_wizard,
    _generate_skaffold,
)
