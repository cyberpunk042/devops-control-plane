"""
K8s shared constants and low-level helpers.

Imported by all k8s_* sub-modules. Must NOT import from any sibling
k8s_* module to avoid circular imports.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════


_SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".mypy_cache", ".ruff_cache", ".pytest_cache", ".tox",
    "dist", "build", ".eggs", ".pages",
    "htmlcov", ".backup", "state",
})

_K8S_API_VERSIONS = frozenset({
    "v1", "apps/v1", "batch/v1", "networking.k8s.io/v1",
    "rbac.authorization.k8s.io/v1", "autoscaling/v1", "autoscaling/v2",
    "policy/v1", "storage.k8s.io/v1", "admissionregistration.k8s.io/v1",
})

_K8S_KINDS = frozenset({
    "Pod", "Deployment", "StatefulSet", "DaemonSet", "ReplicaSet",
    "Job", "CronJob", "Service", "Ingress", "ConfigMap", "Secret",
    "PersistentVolumeClaim", "PersistentVolume", "StorageClass",
    "Namespace", "ServiceAccount", "Role", "ClusterRole",
    "RoleBinding", "ClusterRoleBinding", "HorizontalPodAutoscaler",
    "NetworkPolicy", "ResourceQuota", "LimitRange",
})

_MANIFEST_DIRS = ["k8s", "kubernetes", "deploy", "manifests", "kube", "charts"]


# ═══════════════════════════════════════════════════════════════════
#  Shared Helpers
# ═══════════════════════════════════════════════════════════════════


def _run_kubectl(
    *args: str,
    timeout: int = 15,
) -> subprocess.CompletedProcess[str]:
    """Run a kubectl command and return the result."""
    return subprocess.run(
        ["kubectl", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _kubectl_available() -> dict:
    """Check if kubectl is available and configured.

    Uses ``kubectl version --client -o json`` (the ``--short`` flag
    was removed in kubectl v1.28+).
    """
    try:
        result = _run_kubectl("version", "--client", "-o", "json")
        if result.returncode == 0:
            import json as _json
            try:
                data = _json.loads(result.stdout)
                version = data.get("clientVersion", {}).get("gitVersion", "")
            except (ValueError, KeyError):
                # Fall back to raw output
                version = result.stdout.strip()
            return {"available": True, "version": version}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return {"available": False, "version": None}


def _parse_k8s_yaml(path: Path) -> list[dict]:
    """Parse a YAML file and return K8s resource dicts."""
    try:
        import yaml
    except ImportError:
        return []

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    resources: list[dict] = []
    try:
        for doc in yaml.safe_load_all(content):
            if doc and isinstance(doc, dict):
                if "kind" in doc and "apiVersion" in doc:
                    resources.append(doc)
    except yaml.YAMLError:
        pass

    return resources
