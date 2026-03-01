"""K8s manifest validation — orchestrator.

Layers (each in its own module):
  1. Per-resource structural     → validate_structural.py
  2. Cross-resource consistency  → validate_cross_resource.py
  3. Environment-aware           → validate_env_aware.py
  4. Cluster-aware               → validate_cluster.py
  5. Security & production       → validate_security.py
  6. Cross-domain                → validate_cross_domain.py
  7. Deployment strategy         → validate_strategy.py
"""

from __future__ import annotations

import logging
from pathlib import Path

from .common import _K8S_API_VERSIONS, _parse_k8s_yaml
from .detect import k8s_status

# Layer validators
from .validate_structural import (
    _validate_deployment,
    _validate_service,
    _validate_pod_spec,
    _validate_statefulset,
    _validate_job,
    _validate_cronjob,
    _validate_daemonset,
    _validate_ingress,
    _validate_hpa,
)
from .validate_cross_resource import _validate_cross_resource
from .validate_env_aware import _validate_env_aware
from .validate_cluster import _validate_cluster_aware
from .validate_security import _validate_security
from .validate_cross_domain import _validate_cross_domain
from .validate_strategy import _validate_deployment_strategy

logger = logging.getLogger(__name__)


def validate_manifests(project_root: Path) -> dict:
    """Validate Kubernetes manifest files.

    Checks:
    - YAML structure validity
    - Required fields (apiVersion, kind, metadata)
    - Known API versions
    - Known resource kinds
    - Namespace consistency
    - Common misconfigurations

    Returns:
        {
            "ok": bool,
            "files_checked": int,
            "issues": [{file, line, severity, message}, ...],
            "warnings": int,
            "errors": int,
        }
    """
    status = k8s_status(project_root)
    issues: list[dict] = []
    files_checked = 0

    # Collect all resources for cross-resource validation (Layer 2)
    all_resources: list[tuple[str, dict]] = []  # (rel_path, resource_dict)

    for manifest in status.get("manifests", []):
        path = project_root / manifest["path"]
        files_checked += 1
        resources = _parse_k8s_yaml(path)

        for res in resources:
            rel_path = manifest["path"]
            kind = res.get("kind", "")
            api_version = res.get("apiVersion", "")
            metadata = res.get("metadata", {})
            spec = res.get("spec", {})

            # Collect for cross-resource checks
            all_resources.append((rel_path, res))

            # Check for missing metadata.name
            if not metadata.get("name"):
                issues.append({
                    "file": rel_path,
                    "severity": "error",
                    "message": f"{kind}: missing metadata.name",
                })

            # Check known API version
            if api_version and api_version not in _K8S_API_VERSIONS:
                issues.append({
                    "file": rel_path,
                    "severity": "warning",
                    "message": f"{kind}: unusual apiVersion '{api_version}'",
                })

            # Kind-specific checks
            if kind == "Deployment":
                _validate_deployment(res, rel_path, issues)
            elif kind == "Service":
                _validate_service(res, rel_path, issues)
            elif kind == "StatefulSet":
                _validate_statefulset(res, rel_path, issues)
            elif kind == "Job":
                _validate_job(res, rel_path, issues)
            elif kind == "CronJob":
                _validate_cronjob(res, rel_path, issues)
            elif kind == "DaemonSet":
                _validate_daemonset(res, rel_path, issues)
            elif kind == "Ingress":
                _validate_ingress(res, rel_path, issues)
            elif kind == "HorizontalPodAutoscaler":
                _validate_hpa(res, rel_path, issues)

            # Pod-spec checks (all workload kinds with containers)
            if kind in ("Pod", "Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"):
                _validate_pod_spec(res, rel_path, issues)

    # Layer 2: Cross-resource consistency
    if all_resources:
        _validate_cross_resource(all_resources, issues)

    # Layer 3: Environment-aware validation
    _validate_env_aware(project_root, status, all_resources, issues)

    # Layer 4: Cluster-aware validation
    _validate_cluster_aware(status, all_resources, issues)

    # Layer 5: Security & production readiness
    _validate_security(all_resources, issues)

    # Layer 6: Cross-domain validation
    _validate_cross_domain(project_root, all_resources, issues)

    # Layer 7: Deployment strategy validation
    _validate_deployment_strategy(project_root, status, all_resources, issues)

    errors = sum(1 for i in issues if i["severity"] == "error")
    warnings = sum(1 for i in issues if i["severity"] == "warning")

    return {
        "ok": errors == 0,
        "files_checked": files_checked,
        "issues": issues,
        "errors": errors,
        "warnings": warnings,
    }
