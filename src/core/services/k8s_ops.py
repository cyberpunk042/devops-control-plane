"""
Kubernetes operations — channel-independent service.

Kubernetes manifest detection, validation, resource status (requires
kubectl), and manifest template generation. Works in two modes:

1. **Offline** — detect manifests, validate YAML structure, count
   resources, generate templates. No cluster needed.
2. **Online** — if kubectl is available and configured, probe the
   cluster for resource status, pod health, and service endpoints.

Follows the Detect → Observe → Facilitate → Act pattern.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

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
#  Helpers
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
    """Check if kubectl is available and configured."""
    try:
        result = _run_kubectl("version", "--client", "--short")
        if result.returncode == 0:
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


# ═══════════════════════════════════════════════════════════════════
#  Detect: K8s manifest detection
# ═══════════════════════════════════════════════════════════════════


def k8s_status(project_root: Path) -> dict:
    """Detect Kubernetes manifests and kubectl availability.

    Returns:
        {
            "has_k8s": bool,
            "kubectl": {available, version},
            "manifest_dirs": [str, ...],
            "manifests": [{path, resources}, ...],
            "resource_summary": {Deployment: 2, Service: 3, ...},
            "total_resources": int,
            "helm_charts": [{path, name}, ...],
            "kustomize": {exists, path},
        }
    """
    kubectl = _kubectl_available()

    # Find manifest directories
    manifest_dirs: list[str] = []
    for dir_name in _MANIFEST_DIRS:
        dir_path = project_root / dir_name
        if dir_path.is_dir():
            manifest_dirs.append(dir_name)

    # Scan for YAML files that look like K8s manifests
    manifests: list[dict] = []
    resource_summary: dict[str, int] = {}
    total_resources = 0

    yaml_files = _collect_yaml_files(project_root, manifest_dirs)

    for yaml_file in yaml_files:
        resources = _parse_k8s_yaml(yaml_file)
        if resources:
            rel_path = str(yaml_file.relative_to(project_root))
            resource_kinds = []

            for res in resources:
                kind = res.get("kind", "Unknown")
                resource_kinds.append({
                    "kind": kind,
                    "name": res.get("metadata", {}).get("name", "unnamed"),
                    "namespace": res.get("metadata", {}).get("namespace", "default"),
                    "apiVersion": res.get("apiVersion", ""),
                })
                resource_summary[kind] = resource_summary.get(kind, 0) + 1
                total_resources += 1

            manifests.append({
                "path": rel_path,
                "resources": resource_kinds,
                "count": len(resource_kinds),
            })

    # Detect Helm charts
    helm_charts = _detect_helm_charts(project_root)

    # Detect Kustomize
    kustomize = _detect_kustomize(project_root)

    has_k8s = (
        len(manifests) > 0
        or len(helm_charts) > 0
        or kustomize.get("exists", False)
    )

    return {
        "has_k8s": has_k8s,
        "kubectl": kubectl,
        "manifest_dirs": manifest_dirs,
        "manifests": manifests,
        "resource_summary": resource_summary,
        "total_resources": total_resources,
        "helm_charts": helm_charts,
        "kustomize": kustomize,
    }


def _collect_yaml_files(
    project_root: Path, manifest_dirs: list[str]
) -> list[Path]:
    """Collect YAML files from manifest dirs or root."""
    files: list[Path] = []

    search_dirs = [project_root / d for d in manifest_dirs] if manifest_dirs else [project_root]

    for search_dir in search_dirs:
        for ext in ("*.yaml", "*.yml"):
            for f in search_dir.rglob(ext):
                skip = False
                for part in f.relative_to(project_root).parts:
                    if part in _SKIP_DIRS:
                        skip = True
                        break
                if not skip:
                    files.append(f)

    return files[:50]  # Cap


def _detect_helm_charts(project_root: Path) -> list[dict]:
    """Detect Helm charts (Chart.yaml)."""
    charts: list[dict] = []

    for chart_file in project_root.rglob("Chart.yaml"):
        skip = False
        for part in chart_file.relative_to(project_root).parts:
            if part in _SKIP_DIRS:
                skip = True
                break
        if skip:
            continue

        try:
            import yaml
            content = yaml.safe_load(chart_file.read_text(encoding="utf-8"))
            charts.append({
                "path": str(chart_file.parent.relative_to(project_root)),
                "name": content.get("name", "unknown"),
                "version": content.get("version", "0.0.0"),
                "description": content.get("description", ""),
            })
        except Exception:
            charts.append({
                "path": str(chart_file.parent.relative_to(project_root)),
                "name": "unknown",
            })

    return charts


def _detect_kustomize(project_root: Path) -> dict:
    """Detect Kustomize configuration."""
    for name in ("kustomization.yaml", "kustomization.yml", "Kustomization"):
        path = project_root / name
        if path.is_file():
            return {"exists": True, "path": name}

    # Check in sub-directories
    for d in _MANIFEST_DIRS:
        for name in ("kustomization.yaml", "kustomization.yml"):
            path = project_root / d / name
            if path.is_file():
                return {"exists": True, "path": f"{d}/{name}"}

    return {"exists": False}


# ═══════════════════════════════════════════════════════════════════
#  Detect: Manifest validation
# ═══════════════════════════════════════════════════════════════════


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

            # Deployment-specific checks
            if kind == "Deployment":
                _validate_deployment(res, rel_path, issues)

            # Service-specific checks
            elif kind == "Service":
                _validate_service(res, rel_path, issues)

            # Pod-specific checks (including pod templates)
            if kind in ("Pod", "Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"):
                _validate_pod_spec(res, rel_path, issues)

    errors = sum(1 for i in issues if i["severity"] == "error")
    warnings = sum(1 for i in issues if i["severity"] == "warning")

    return {
        "ok": errors == 0,
        "files_checked": files_checked,
        "issues": issues,
        "errors": errors,
        "warnings": warnings,
    }


def _validate_deployment(res: dict, path: str, issues: list[dict]) -> None:
    """Deployment-specific validation."""
    spec = res.get("spec", {})
    name = res.get("metadata", {}).get("name", "?")

    # Check replicas
    if "replicas" not in spec:
        issues.append({
            "file": path,
            "severity": "warning",
            "message": f"Deployment/{name}: no replicas specified (defaults to 1)",
        })

    # Check selector
    if "selector" not in spec:
        issues.append({
            "file": path,
            "severity": "error",
            "message": f"Deployment/{name}: missing spec.selector",
        })

    # Check strategy
    if "strategy" not in spec:
        issues.append({
            "file": path,
            "severity": "info",
            "message": f"Deployment/{name}: no update strategy (defaults to RollingUpdate)",
        })


def _validate_service(res: dict, path: str, issues: list[dict]) -> None:
    """Service-specific validation."""
    spec = res.get("spec", {})
    name = res.get("metadata", {}).get("name", "?")

    if not spec.get("selector"):
        issues.append({
            "file": path,
            "severity": "warning",
            "message": f"Service/{name}: no selector (headless without selector)",
        })

    ports = spec.get("ports", [])
    if not ports:
        issues.append({
            "file": path,
            "severity": "warning",
            "message": f"Service/{name}: no ports defined",
        })

    for port in ports:
        if not port.get("name") and len(ports) > 1:
            issues.append({
                "file": path,
                "severity": "warning",
                "message": f"Service/{name}: port {port.get('port')} missing name (required for multi-port)",
            })


def _validate_pod_spec(res: dict, path: str, issues: list[dict]) -> None:
    """Validate pod spec (including pod templates in controllers)."""
    kind = res.get("kind", "")
    name = res.get("metadata", {}).get("name", "?")

    # Navigate to the pod spec
    if kind == "Pod":
        pod_spec = res.get("spec", {})
    else:
        pod_spec = res.get("spec", {}).get("template", {}).get("spec", {})

    if not pod_spec:
        return

    containers = pod_spec.get("containers", [])
    if not containers:
        issues.append({
            "file": path,
            "severity": "error",
            "message": f"{kind}/{name}: no containers defined",
        })
        return

    for container in containers:
        c_name = container.get("name", "unnamed")

        # Resource limits
        if not container.get("resources"):
            issues.append({
                "file": path,
                "severity": "warning",
                "message": f"{kind}/{name}/{c_name}: no resource limits/requests",
            })
        else:
            res_config = container.get("resources", {})
            if not res_config.get("limits"):
                issues.append({
                    "file": path,
                    "severity": "warning",
                    "message": f"{kind}/{name}/{c_name}: resources.limits not set",
                })
            if not res_config.get("requests"):
                issues.append({
                    "file": path,
                    "severity": "warning",
                    "message": f"{kind}/{name}/{c_name}: resources.requests not set",
                })

        # Liveness/readiness probes
        if not container.get("livenessProbe"):
            issues.append({
                "file": path,
                "severity": "info",
                "message": f"{kind}/{name}/{c_name}: no livenessProbe",
            })

        if not container.get("readinessProbe"):
            issues.append({
                "file": path,
                "severity": "info",
                "message": f"{kind}/{name}/{c_name}: no readinessProbe",
            })

        # Security context
        if not container.get("securityContext"):
            issues.append({
                "file": path,
                "severity": "info",
                "message": f"{kind}/{name}/{c_name}: no securityContext",
            })

        # Image tag
        image = container.get("image", "")
        if image and ":" not in image:
            issues.append({
                "file": path,
                "severity": "warning",
                "message": f"{kind}/{name}/{c_name}: image '{image}' uses :latest (implicit)",
            })
        elif image.endswith(":latest"):
            issues.append({
                "file": path,
                "severity": "warning",
                "message": f"{kind}/{name}/{c_name}: image uses :latest tag",
            })


# ═══════════════════════════════════════════════════════════════════
#  Observe: Cluster status (online)
# ═══════════════════════════════════════════════════════════════════


def cluster_status() -> dict:
    """Get cluster connection info and node status.

    Returns:
        {
            "connected": bool,
            "context": str,
            "nodes": [{name, status, roles, version}, ...],
            "namespaces": [str, ...],
        }
    """
    kubectl = _kubectl_available()
    if not kubectl.get("available"):
        return {"connected": False, "error": "kubectl not available"}

    # Current context
    try:
        ctx_result = _run_kubectl("config", "current-context")
        context = ctx_result.stdout.strip() if ctx_result.returncode == 0 else "unknown"
    except Exception:
        context = "unknown"

    # Nodes
    nodes: list[dict] = []
    try:
        result = _run_kubectl(
            "get", "nodes",
            "-o", "jsonpath={range .items[*]}{.metadata.name}|{.status.conditions[?(@.type==\"Ready\")].status}|{.metadata.labels.node-role\\.kubernetes\\.io/}|{.status.nodeInfo.kubeletVersion}{\"\\n\"}{end}",
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = line.split("|")
                if len(parts) >= 2:
                    nodes.append({
                        "name": parts[0],
                        "ready": parts[1] == "True",
                        "roles": parts[2] if len(parts) > 2 else "",
                        "version": parts[3] if len(parts) > 3 else "",
                    })
    except Exception:
        pass

    # Namespaces
    namespaces: list[str] = []
    try:
        result = _run_kubectl("get", "namespaces", "-o", "jsonpath={.items[*].metadata.name}")
        if result.returncode == 0:
            namespaces = result.stdout.strip().split()
    except Exception:
        pass

    return {
        "connected": len(nodes) > 0,
        "context": context,
        "nodes": nodes,
        "namespaces": namespaces,
    }


def get_resources(namespace: str = "default", kind: str = "pods") -> dict:
    """Get resources from the cluster.

    Returns:
        {
            "ok": bool,
            "resources": [{name, namespace, status, age}, ...],
            "count": int,
        }
    """
    kubectl = _kubectl_available()
    if not kubectl.get("available"):
        return {"ok": False, "error": "kubectl not available"}

    try:
        result = _run_kubectl(
            "get", kind,
            "-n", namespace,
            "-o", "json",
            timeout=15,
        )

        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()}

        import json
        data = json.loads(result.stdout)
        items = data.get("items", [])

        resources: list[dict] = []
        for item in items:
            metadata = item.get("metadata", {})
            status = item.get("status", {})

            resources.append({
                "name": metadata.get("name", ""),
                "namespace": metadata.get("namespace", namespace),
                "created": metadata.get("creationTimestamp", ""),
                "phase": status.get("phase", ""),
                "conditions": _summarize_conditions(status.get("conditions", [])),
            })

        return {
            "ok": True,
            "resources": resources,
            "count": len(resources),
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}


def _summarize_conditions(conditions: list[dict]) -> str:
    """Summarize K8s resource conditions."""
    if not conditions:
        return ""
    true_conditions = [c.get("type", "") for c in conditions if c.get("status") == "True"]
    return ", ".join(true_conditions)


# ═══════════════════════════════════════════════════════════════════
#  Act: Cluster operations (online)
# ═══════════════════════════════════════════════════════════════════


def k8s_pod_logs(
    namespace: str = "default",
    pod: str = "",
    *,
    tail: int = 100,
    container: str = "",
) -> dict:
    """Get logs from a pod.

    Returns:
        {"ok": True, "logs": "..."} or {"error": "..."}
    """
    kubectl = _kubectl_available()
    if not kubectl.get("available"):
        return {"ok": False, "error": "kubectl not available"}
    if not pod:
        return {"ok": False, "error": "Missing pod name"}

    args = ["logs", pod, "-n", namespace, "--tail", str(tail)]
    if container:
        args.extend(["-c", container])

    try:
        result = _run_kubectl(*args, timeout=15)
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()}
        return {"ok": True, "pod": pod, "namespace": namespace, "logs": result.stdout}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def k8s_apply(project_root: Path, file_path: str = "", *, namespace: str = "") -> dict:
    """Apply Kubernetes manifests.

    Args:
        file_path: Relative path to manifest file or directory.
        namespace: Optional namespace override.

    Returns:
        {"ok": True, "output": "..."} or {"error": "..."}
    """
    kubectl = _kubectl_available()
    if not kubectl.get("available"):
        return {"ok": False, "error": "kubectl not available"}

    target = project_root / file_path if file_path else project_root
    if not target.exists():
        return {"ok": False, "error": f"Path not found: {file_path}"}

    args = ["apply"]
    if target.is_dir():
        args.extend(["-f", str(target), "--recursive"])
    else:
        args.extend(["-f", str(target)])

    if namespace:
        args.extend(["-n", namespace])

    try:
        result = _run_kubectl(*args, timeout=60)
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()}
        return {"ok": True, "output": result.stdout.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def k8s_delete_resource(
    kind: str,
    name: str,
    *,
    namespace: str = "default",
) -> dict:
    """Delete a Kubernetes resource.

    Returns:
        {"ok": True, "output": "..."} or {"error": "..."}
    """
    kubectl = _kubectl_available()
    if not kubectl.get("available"):
        return {"ok": False, "error": "kubectl not available"}
    if not kind or not name:
        return {"ok": False, "error": "Missing kind or name"}

    try:
        result = _run_kubectl("delete", kind, name, "-n", namespace, timeout=30)
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()}
        return {"ok": True, "output": result.stdout.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def k8s_scale(
    name: str,
    replicas: int,
    *,
    namespace: str = "default",
    kind: str = "deployment",
) -> dict:
    """Scale a deployment / statefulset.

    Returns:
        {"ok": True, "output": "..."} or {"error": "..."}
    """
    kubectl = _kubectl_available()
    if not kubectl.get("available"):
        return {"ok": False, "error": "kubectl not available"}
    if not name:
        return {"ok": False, "error": "Missing resource name"}

    try:
        result = _run_kubectl(
            "scale", f"{kind}/{name}",
            f"--replicas={replicas}",
            "-n", namespace,
            timeout=30,
        )
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()}
        return {"ok": True, "output": result.stdout.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def k8s_events(namespace: str = "default") -> dict:
    """Get recent cluster events.

    Returns:
        {"ok": True, "events": [{type, reason, object, message, age}, ...]}
    """
    kubectl = _kubectl_available()
    if not kubectl.get("available"):
        return {"ok": False, "error": "kubectl not available"}

    try:
        result = _run_kubectl(
            "get", "events",
            "-n", namespace,
            "--sort-by=.lastTimestamp",
            "-o", "json",
            timeout=15,
        )
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()}

        import json as _json
        data = _json.loads(result.stdout)
        events: list[dict] = []
        for item in (data.get("items", []) or [])[-50:]:  # last 50
            events.append({
                "type": item.get("type", ""),
                "reason": item.get("reason", ""),
                "object": f"{item.get('involvedObject', {}).get('kind', '')}/{item.get('involvedObject', {}).get('name', '')}",
                "message": item.get("message", ""),
                "count": item.get("count", 1),
                "first_seen": item.get("firstTimestamp", ""),
                "last_seen": item.get("lastTimestamp", ""),
            })
        return {"ok": True, "events": events, "count": len(events)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def k8s_describe(kind: str, name: str, *, namespace: str = "default") -> dict:
    """Describe a Kubernetes resource.

    Returns:
        {"ok": True, "description": "..."} or {"error": "..."}
    """
    kubectl = _kubectl_available()
    if not kubectl.get("available"):
        return {"ok": False, "error": "kubectl not available"}
    if not kind or not name:
        return {"ok": False, "error": "Missing kind or name"}

    try:
        result = _run_kubectl("describe", kind, name, "-n", namespace, timeout=15)
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()}
        return {"ok": True, "description": result.stdout}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def k8s_namespaces() -> dict:
    """List Kubernetes namespaces.

    Returns:
        {"ok": True, "namespaces": [{name, status, age}, ...]}
    """
    kubectl = _kubectl_available()
    if not kubectl.get("available"):
        return {"ok": False, "error": "kubectl not available"}

    try:
        result = _run_kubectl("get", "namespaces", "-o", "json", timeout=10)
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()}

        import json as _json
        data = _json.loads(result.stdout)
        namespaces: list[dict] = []
        for item in data.get("items", []):
            namespaces.append({
                "name": item.get("metadata", {}).get("name", ""),
                "status": item.get("status", {}).get("phase", ""),
                "created": item.get("metadata", {}).get("creationTimestamp", ""),
            })
        return {"ok": True, "namespaces": namespaces, "count": len(namespaces)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def k8s_storage_classes() -> dict:
    """List available StorageClasses from the cluster.

    Returns:
        {
            "ok": True,
            "storage_classes": [{
                "name": str,
                "provisioner": str,
                "is_default": bool,
                "reclaim_policy": str,
                "volume_binding_mode": str,
                "parameters": {str: str},
            }, ...],
            "default_class": str | None,
        }
    """
    kubectl = _kubectl_available()
    if not kubectl.get("available"):
        return {"ok": False, "error": "kubectl not available"}

    try:
        result = _run_kubectl("get", "storageclasses", "-o", "json", timeout=10)
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()}

        import json as _json
        data = _json.loads(result.stdout)
        storage_classes: list[dict] = []
        default_class: str | None = None

        for item in data.get("items", []):
            metadata = item.get("metadata", {})
            annotations = metadata.get("annotations", {})
            name = metadata.get("name", "")

            # Default StorageClass is marked via annotation
            is_default = (
                annotations.get("storageclass.kubernetes.io/is-default-class", "")
                == "true"
                or annotations.get(
                    "storageclass.beta.kubernetes.io/is-default-class", ""
                )
                == "true"
            )
            if is_default:
                default_class = name

            storage_classes.append({
                "name": name,
                "provisioner": item.get("provisioner", ""),
                "is_default": is_default,
                "reclaim_policy": item.get("reclaimPolicy", "Delete"),
                "volume_binding_mode": item.get(
                    "volumeBindingMode", "Immediate"
                ),
                "parameters": item.get("parameters", {}) or {},
            })

        return {
            "ok": True,
            "storage_classes": storage_classes,
            "default_class": default_class,
            "count": len(storage_classes),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


_DEPLOYMENT_TEMPLATE = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
  labels:
    app: {name}
spec:
  replicas: {replicas}
  selector:
    matchLabels:
      app: {name}
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  template:
    metadata:
      labels:
        app: {name}
    spec:
      containers:
        - name: {name}
          image: {image}
          ports:
            - containerPort: {port}
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "256Mi"
          livenessProbe:
            httpGet:
              path: /health
              port: {port}
            initialDelaySeconds: 10
            periodSeconds: 15
          readinessProbe:
            httpGet:
              path: /health
              port: {port}
            initialDelaySeconds: 5
            periodSeconds: 5
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: false
"""

_SERVICE_TEMPLATE = """apiVersion: v1
kind: Service
metadata:
  name: {name}
  labels:
    app: {name}
spec:
  type: {service_type}
  ports:
    - port: {port}
      targetPort: {port}
      protocol: TCP
      name: http
  selector:
    app: {name}
"""

_INGRESS_TEMPLATE = """apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {name}
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  rules:
    - host: {host}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {name}
                port:
                  number: {port}
"""

_NAMESPACE_TEMPLATE = """apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
  labels:
    name: {namespace}
"""


def generate_manifests(
    project_root: Path,
    app_name: str,
    *,
    image: str = "",
    port: int = 8080,
    replicas: int = 2,
    service_type: str = "ClusterIP",
    host: str = "",
    namespace: str = "",
) -> dict:
    """Generate Kubernetes manifests for an application.

    Returns:
        {"ok": True, "files": [{path, content, reason}, ...]}
    """
    from src.core.models.template import GeneratedFile

    if not image:
        image = f"{app_name}:latest"

    files: list[dict] = []

    # Namespace (if specified)
    if namespace:
        ns_file = GeneratedFile(
            path=f"k8s/{namespace}-namespace.yaml",
            content=_NAMESPACE_TEMPLATE.format(namespace=namespace),
            overwrite=False,
            reason=f"Namespace for {app_name}",
        )
        files.append(ns_file.model_dump())

    # Deployment
    deploy_file = GeneratedFile(
        path=f"k8s/{app_name}-deployment.yaml",
        content=_DEPLOYMENT_TEMPLATE.format(
            name=app_name, image=image, port=port, replicas=replicas,
        ),
        overwrite=False,
        reason=f"Deployment for {app_name} ({replicas} replicas)",
    )
    files.append(deploy_file.model_dump())

    # Service
    svc_file = GeneratedFile(
        path=f"k8s/{app_name}-service.yaml",
        content=_SERVICE_TEMPLATE.format(
            name=app_name, port=port, service_type=service_type,
        ),
        overwrite=False,
        reason=f"Service ({service_type}) for {app_name}",
    )
    files.append(svc_file.model_dump())

    # Ingress (if host specified)
    if host:
        ing_file = GeneratedFile(
            path=f"k8s/{app_name}-ingress.yaml",
            content=_INGRESS_TEMPLATE.format(
                name=app_name, port=port, host=host,
            ),
            overwrite=False,
            reason=f"Ingress for {app_name} at {host}",
        )
        files.append(ing_file.model_dump())

    return {"ok": True, "files": files}


# ═══════════════════════════════════════════════════════════════════
#  Helm Operations
# ═══════════════════════════════════════════════════════════════════


def _helm_available() -> bool:
    """Check if helm CLI is available."""
    import shutil
    return shutil.which("helm") is not None


def helm_list(project_root: Path, *, namespace: str = "") -> dict:
    """List installed Helm releases.

    Returns:
        {"available": True, "releases": [{name, namespace, revision, status, chart, app_version}, ...]}
    """
    if not _helm_available():
        return {"available": False, "error": "helm CLI not found"}

    cmd = ["helm", "list", "--output", "json"]
    if namespace:
        cmd.extend(["--namespace", namespace])
    else:
        cmd.append("--all-namespaces")

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=project_root)
        if r.returncode != 0:
            return {"available": True, "releases": [], "error": r.stderr.strip()}

        import json
        releases = json.loads(r.stdout) if r.stdout.strip() else []
        return {"available": True, "releases": releases}
    except Exception as e:
        return {"available": True, "releases": [], "error": str(e)}


def helm_values(project_root: Path, release: str, *, namespace: str = "") -> dict:
    """Get values for a Helm release.

    Returns:
        {"ok": True, "values": str (YAML)} or {"error": "..."}
    """
    if not _helm_available():
        return {"error": "helm CLI not found"}

    cmd = ["helm", "get", "values", release, "--output", "yaml"]
    if namespace:
        cmd.extend(["--namespace", namespace])

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=project_root)
        if r.returncode != 0:
            return {"error": r.stderr.strip() or "Failed to get values"}
        return {"ok": True, "values": r.stdout, "release": release}
    except Exception as e:
        return {"error": str(e)}


def helm_install(
    project_root: Path,
    release: str,
    chart: str,
    *,
    namespace: str = "",
    values_file: str = "",
    set_values: dict | None = None,
    dry_run: bool = False,
) -> dict:
    """Install a Helm chart.

    Returns:
        {"ok": True, "output": str} or {"error": "..."}
    """
    if not _helm_available():
        return {"error": "helm CLI not found"}

    cmd = ["helm", "install", release, chart]
    if namespace:
        cmd.extend(["--namespace", namespace, "--create-namespace"])
    if values_file:
        cmd.extend(["--values", values_file])
    if set_values:
        for k, v in set_values.items():
            cmd.extend(["--set", f"{k}={v}"])
    if dry_run:
        cmd.append("--dry-run")

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=project_root)
        if r.returncode != 0:
            return {"error": r.stderr.strip() or "Helm install failed"}
        return {"ok": True, "output": r.stdout}
    except Exception as e:
        return {"error": str(e)}


def helm_upgrade(
    project_root: Path,
    release: str,
    chart: str,
    *,
    namespace: str = "",
    values_file: str = "",
    set_values: dict | None = None,
    dry_run: bool = False,
) -> dict:
    """Upgrade a Helm release.

    Returns:
        {"ok": True, "output": str} or {"error": "..."}
    """
    if not _helm_available():
        return {"error": "helm CLI not found"}

    cmd = ["helm", "upgrade", release, chart, "--install"]
    if namespace:
        cmd.extend(["--namespace", namespace])
    if values_file:
        cmd.extend(["--values", values_file])
    if set_values:
        for k, v in set_values.items():
            cmd.extend(["--set", f"{k}={v}"])
    if dry_run:
        cmd.append("--dry-run")

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=project_root)
        if r.returncode != 0:
            return {"error": r.stderr.strip() or "Helm upgrade failed"}
        return {"ok": True, "output": r.stdout}
    except Exception as e:
        return {"error": str(e)}


def helm_template(
    project_root: Path,
    release: str,
    chart: str,
    *,
    namespace: str = "",
    values_file: str = "",
) -> dict:
    """Render Helm templates locally (dry-run without cluster).

    Returns:
        {"ok": True, "output": str (rendered YAML)} or {"error": "..."}
    """
    if not _helm_available():
        return {"error": "helm CLI not found"}

    cmd = ["helm", "template", release, chart]
    if namespace:
        cmd.extend(["--namespace", namespace])
    if values_file:
        cmd.extend(["--values", values_file])

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=project_root)
        if r.returncode != 0:
            return {"error": r.stderr.strip() or "Helm template failed"}
        return {"ok": True, "output": r.stdout}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════
#  Skaffold Detection
# ═══════════════════════════════════════════════════════════════════


def skaffold_status(project_root: Path) -> dict:
    """Detect Skaffold configuration.

    Returns:
        {
            "available": bool (CLI exists),
            "configs": [{path, profiles: [str]}],
            "has_skaffold": bool,
        }
    """
    import shutil
    import yaml

    cli_available = shutil.which("skaffold") is not None

    configs: list[dict] = []
    skaffold_files = [
        "skaffold.yaml", "skaffold.yml",
    ]

    for f in skaffold_files:
        p = project_root / f
        if p.is_file():
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8"))
                profiles = []
                if isinstance(data, dict) and "profiles" in data:
                    profiles = [
                        pr.get("name", "")
                        for pr in data["profiles"]
                        if isinstance(pr, dict) and pr.get("name")
                    ]
                configs.append({
                    "path": f,
                    "profiles": profiles,
                    "api_version": data.get("apiVersion", "") if isinstance(data, dict) else "",
                })
            except Exception:
                configs.append({"path": f, "profiles": [], "api_version": ""})

    return {
        "available": cli_available,
        "configs": configs,
        "has_skaffold": len(configs) > 0,
    }


# ═══════════════════════════════════════════════════════════════════
#  Multi-Environment Namespace Mapping
# ═══════════════════════════════════════════════════════════════════


def k8s_env_namespaces(project_root: Path) -> dict:
    """Map project environments to K8s namespaces.

    Reads project.yml environments and checks for env-specific
    namespace files or Kustomize overlays.

    Returns:
        {
            "environments": [{
                name, namespace, has_overlay, overlay_path
            }, ...],
        }
    """
    from src.core.config.loader import find_project_file, load_project

    config_path = find_project_file(project_root)
    if not config_path:
        return {"environments": []}

    project = load_project(config_path)
    envs: list[dict] = []

    for env in project.environments:
        name = env.name
        # Convention: namespace = project-name-env
        namespace = f"{project.name}-{name}" if project.name else name

        # Check for env-specific overlays
        overlay_paths = [
            f"k8s/overlays/{name}",
            f"k8s/envs/{name}",
            f"kubernetes/overlays/{name}",
            f"deploy/overlays/{name}",
        ]
        has_overlay = False
        overlay_path = ""
        for op in overlay_paths:
            if (project_root / op).is_dir():
                has_overlay = True
                overlay_path = op
                break

        # Check for env-specific values files (Helm)
        values_files = [
            f"values-{name}.yaml", f"values.{name}.yaml",
            f"helm/values-{name}.yaml", f"charts/values-{name}.yaml",
        ]
        values_file = ""
        for vf in values_files:
            if (project_root / vf).is_file():
                values_file = vf
                break

        envs.append({
            "name": name,
            "namespace": namespace,
            "default": env.default,
            "has_overlay": has_overlay,
            "overlay_path": overlay_path,
            "values_file": values_file,
        })

    return {"environments": envs}


# ═══════════════════════════════════════════════════════════════════
#  K8s Manifest Wizard — Translator + Generator
# ═══════════════════════════════════════════════════════════════════


def _svc_env_to_resources(
    svc_name: str,
    env_vars: list[dict],
    namespace: str,
    output_dir: str,
) -> tuple[list[dict], bool, bool]:
    """Extract ConfigMap / Secret resources from a service's envVars.

    Returns:
        (resources, has_config, has_secrets)
        - resources: ConfigMap and/or Secret resource dicts
        - has_config: True if a ConfigMap was generated (for envFrom wiring)
        - has_secrets: True if a Secret was generated
    """
    resources: list[dict] = []
    config_data: dict = {}
    secret_data: dict = {}

    for ev in env_vars:
        if not isinstance(ev, dict):
            continue
        key = ev.get("key", "")
        if not key:
            continue
        ev_type = ev.get("type", "hardcoded")
        if ev_type == "secret":
            # Placeholder — user replaces at deploy time
            secret_data[key] = "CHANGE_ME"
        elif ev_type == "variable":
            # Placeholder referencing external variable
            var_name = ev.get("varName", f"${{{key}}}")
            config_data[key] = var_name
        else:
            # Hardcoded value
            config_data[key] = ev.get("value", "")

    has_config = bool(config_data)
    has_secrets = bool(secret_data)

    if has_config:
        resources.append({
            "kind": "ConfigMap",
            "name": f"{svc_name}-config",
            "namespace": namespace,
            "output_dir": output_dir,
            "spec": {"data": config_data},
        })
    if has_secrets:
        resources.append({
            "kind": "Secret",
            "name": f"{svc_name}-secrets",
            "namespace": namespace,
            "output_dir": output_dir,
            "spec": {"stringData": secret_data},
        })

    return resources, has_config, has_secrets


def _svc_volumes_to_pvc_resources(
    svc_name: str,
    volumes: list[dict],
    namespace: str,
    output_dir: str,
) -> list[dict]:
    """Generate PVC resources for pvc-dynamic / pvc-static volumes."""
    resources: list[dict] = []
    for vol in volumes:
        vol_type = vol.get("type", "")
        if vol_type not in ("pvc-dynamic", "pvc-static"):
            continue
        vol_name = vol.get("name", "data")
        pvc_name = f"{svc_name}-{vol_name}"
        pvc_res: dict = {
            "kind": "PersistentVolumeClaim",
            "name": pvc_name,
            "namespace": namespace,
            "output_dir": output_dir,
            "spec": {
                "accessModes": [vol.get("accessMode", "ReadWriteOnce")],
                "storage": vol.get("size", "10Gi"),
            },
        }
        sc = vol.get("storageClass", "")
        if sc:
            pvc_res["spec"]["storageClass"] = sc
        if vol_type == "pvc-static" and vol.get("pvName"):
            pvc_res["spec"]["volumeName"] = vol["pvName"]
        # Longhorn annotations
        lh = vol.get("longhornConfig")
        if lh:
            pvc_res["spec"]["longhornConfig"] = lh
        resources.append(pvc_res)
    return resources


def _generate_skaffold(data: dict, generated_files: list[dict]) -> dict | None:
    """Build a skaffold.yaml from the wizard state.

    Args:
        data: Wizard state (same shape as wizard_state_to_resources input).
        generated_files: The list of file dicts from generate_k8s_wizard output,
            used to collect manifest paths for the deploy section.

    Returns:
        A file dict {path, content, reason} or None if skaffold is disabled.
    """
    if not data.get("skaffold"):
        return None

    import yaml

    output_dir = (data.get("output_dir") or "k8s").rstrip("/")

    # Collect build artifacts — one per service that has a local-looking image
    # (i.e. not a known registry image like postgres:16 or redis:7)
    artifacts: list[dict] = []
    for svc in data.get("_services", []):
        svc_kind = svc.get("kind", "Deployment")
        if svc_kind in ("Skip",):
            continue
        image = svc.get("image", "")
        if not image:
            continue
        # Heuristic: registry images contain '/' or ':' with a known base
        # Local images are typically just 'name:tag' or 'name:latest'
        # We include everything and let users prune
        artifacts.append({
            "image": image,
            "context": ".",
        })

    # Collect manifest paths from generated files
    manifest_paths: list[str] = []
    for f in generated_files:
        path = f.get("path", "")
        if path.endswith(".yaml") or path.endswith(".yml"):
            manifest_paths.append(path)

    # If no manifests, use the output dir glob
    if not manifest_paths:
        manifest_paths = [f"{output_dir}/*.yaml"]

    skaffold_doc: dict = {
        "apiVersion": "skaffold/v4beta11",
        "kind": "Config",
        "metadata": {"name": data.get("_services", [{}])[0].get("name", "app")
                     if data.get("_services") else "app"},
    }

    if artifacts:
        skaffold_doc["build"] = {"artifacts": artifacts}

    skaffold_doc["manifests"] = {"rawYaml": manifest_paths}

    skaffold_doc["deploy"] = {"kubectl": {}}

    content = yaml.dump(skaffold_doc, default_flow_style=False, sort_keys=False)
    return {
        "path": "skaffold.yaml",
        "content": content,
        "reason": "Skaffold pipeline — build → push → deploy",
        "overwrite": False,
    }


def wizard_state_to_resources(data: dict) -> list[dict]:
    """Translate wizard state into flat resource list for generate_k8s_wizard.

    Input shape (from frontend collector + saved state):
        {
            _services: [...],       # app services with all config
            _infraDecisions: [...], # infra decisions (StatefulSet/Managed/Skip)
            namespace: "default",
            output_dir: "k8s/",
            ingress: "host.example.com" or "",
            skaffold: true/false,
        }

    Output: list of resource dicts, each with:
        {kind, name, namespace, output_dir, spec: {...}}
    """
    services = data.get("_services", [])
    infra = data.get("_infraDecisions", [])
    namespace = data.get("namespace", "default")
    output_dir = (data.get("output_dir") or "k8s").rstrip("/")

    resources: list[dict] = []

    # ── Build infra lookup for dependency resolution ──
    # Maps infra name → {kind, port, has_config, has_secrets}
    infra_lookup: dict[str, dict] = {}
    for inf in infra:
        inf_name = inf.get("name", "")
        if not inf_name:
            continue
        infra_lookup[inf_name] = {
            "kind": inf.get("kind", "Skip"),
            "port": inf.get("port", ""),
        }

    # ── Process infrastructure decisions first ──
    # (so their ConfigMap/Secret names are known when we wire dependencies)
    for inf in infra:
        inf_name = inf.get("name", "")
        inf_kind = inf.get("kind", "Skip")
        if not inf_name or inf_kind == "Skip":
            continue

        inf_env_vars = inf.get("envVars", [])
        inf_volumes = inf.get("volumes", [])

        # Generate ConfigMap/Secret from env vars
        env_resources, has_cm, has_sec = _svc_env_to_resources(
            inf_name, inf_env_vars, namespace, output_dir,
        )
        resources.extend(env_resources)

        # Update lookup with generated resource info
        infra_lookup[inf_name]["has_config"] = has_cm
        infra_lookup[inf_name]["has_secrets"] = has_sec

        if inf_kind == "Managed":
            # Managed infra → only ConfigMap/Secret (no workload)
            # These get referenced by dependent services via envFrom
            continue

        # Self-hosted infra (StatefulSet, Deployment, DaemonSet)
        inf_port = inf.get("port", "")

        # Build workload resource
        inf_spec: dict = {
            "image": inf.get("image", inf_name),
            "_svc_name": inf_name,  # for env var naming convention
            "env": inf_env_vars,
            "wizardVolumes": inf_volumes,
        }
        if inf_port:
            inf_spec["port"] = int(inf_port)

        resources.append({
            "kind": inf_kind,
            "name": inf_name,
            "namespace": namespace,
            "output_dir": output_dir,
            "spec": inf_spec,
        })

        # Generate Service for self-hosted infra (if port set)
        if inf_port:
            svc_spec: dict = {
                "port": int(inf_port),
                "target_port": int(inf_port),
                "selector": inf_name,
            }
            if inf_kind == "StatefulSet":
                # Headless service for StatefulSet infra
                svc_spec["headless"] = True
                svc_dns = f"{inf_name}-headless"
                resources.append({
                    "kind": "Service",
                    "name": svc_dns,
                    "namespace": namespace,
                    "output_dir": output_dir,
                    "spec": svc_spec,
                })
            else:
                svc_dns = inf_name
                svc_spec["type"] = "ClusterIP"
                resources.append({
                    "kind": "Service",
                    "name": svc_dns,
                    "namespace": namespace,
                    "output_dir": output_dir,
                    "spec": svc_spec,
                })
            # Store the actual K8s Service DNS name for wait-for resolution
            infra_lookup[inf_name]["svc_dns"] = svc_dns

        # Generate PVC resources for infra volumes
        resources.extend(
            _svc_volumes_to_pvc_resources(inf_name, inf_volumes, namespace, output_dir)
        )

    # ── Process application services ──
    for svc in services:
        svc_name = svc.get("name", "")
        svc_kind = svc.get("kind", "Deployment")
        if not svc_name or svc_kind in ("Skip", "Managed"):
            continue

        env_vars = svc.get("envVars", [])
        volumes = svc.get("volumes", [])
        is_job = svc_kind in ("Job", "CronJob")

        # ── Generate ConfigMap/Secret from env vars ──
        env_resources, has_cm, has_sec = _svc_env_to_resources(
            svc_name, env_vars, namespace, output_dir,
        )
        resources.extend(env_resources)

        # ── Generate PVC resources from volumes ──
        resources.extend(
            _svc_volumes_to_pvc_resources(svc_name, volumes, namespace, output_dir)
        )

        # ── Build envFrom list (bulk ConfigMap/Secret refs) ──
        env_from: list[dict] = []
        if has_cm:
            env_from.append({"configMapRef": {"name": f"{svc_name}-config"}})
        if has_sec:
            env_from.append({"secretRef": {"name": f"{svc_name}-secrets"}})

        # Wire managed infra ConfigMap/Secret into dependent services
        dependencies = svc.get("dependencies", [])
        for dep_name in dependencies:
            dep_info = infra_lookup.get(dep_name, {})
            if dep_info.get("has_config"):
                env_from.append({"configMapRef": {"name": f"{dep_name}-config"}})
            if dep_info.get("has_secrets"):
                env_from.append({"secretRef": {"name": f"{dep_name}-secrets"}})

        # ── Build dependency wait-for init containers ──
        dep_init_containers: list[dict] = []
        for dep_name in dependencies:
            dep_info = infra_lookup.get(dep_name, {})
            # Skip wait-for for Managed infra — no K8s Service exists
            if dep_info.get("kind") == "Managed":
                continue
            dep_port = dep_info.get("port", "")
            if dep_port:
                # Use resolved K8s Service DNS name (e.g. postgres-headless for StatefulSet)
                dns_name = dep_info.get("svc_dns", dep_name)
                dep_init_containers.append({
                    "name": f"wait-for-{dep_name}",
                    "image": "busybox:1.36",
                    "command": (
                        f"echo 'Waiting for {dns_name}:{dep_port}…'; "
                        f"until nc -z {dns_name} {dep_port}; do sleep 2; done; "
                        f"echo 'Ready.'"
                    ),
                })

        # Merge user-defined init containers with dependency wait-fors
        all_init = dep_init_containers + (svc.get("initContainers") or [])

        # ── Flatten resources object ──
        res_obj = svc.get("resources") or {}

        # ── Build workload spec ──
        spec: dict = {
            "image": svc.get("image", f"{svc_name}:latest"),
            "_svc_name": svc_name,
            "env": env_vars,
            "wizardVolumes": volumes,
            "initContainers": all_init,
            "sidecars": svc.get("sidecars", []),
            "companions": svc.get("companions", []),
            "mesh": svc.get("mesh"),
            # Flatten resource limits
            "cpu_request": res_obj.get("cpu_request"),
            "cpu_limit": res_obj.get("cpu_limit"),
            "memory_request": res_obj.get("memory_request"),
            "memory_limit": res_obj.get("memory_limit"),
            # Health probes
            "readinessProbe": svc.get("readinessProbe"),
            "livenessProbe": svc.get("livenessProbe"),
        }

        # envFrom (only if there are refs to inject)
        if env_from:
            spec["envFrom"] = env_from

        # ── Kind-specific fields ──
        if svc_kind == "Deployment":
            port = svc.get("port")
            if port:
                spec["port"] = int(port)
            spec["replicas"] = int(svc.get("replicas", 2))
            spec["strategy"] = svc.get("strategy", "RollingUpdate")
            spec["maxSurge"] = svc.get("maxSurge", 1)
            spec["maxUnavailable"] = svc.get("maxUnavailable", 0)

        elif svc_kind == "StatefulSet":
            port = svc.get("port")
            if port:
                spec["port"] = int(port)
            spec["replicas"] = int(svc.get("replicas", 1))
            spec["headlessServiceName"] = svc.get(
                "headlessServiceName", f"{svc_name}-headless"
            )
            spec["podManagementPolicy"] = svc.get("podManagementPolicy", "OrderedReady")
            spec["strategy"] = svc.get("strategy")
            spec["partition"] = svc.get("partition")
            spec["volumeClaimTemplates"] = svc.get("volumeClaimTemplates", [])

        elif svc_kind == "DaemonSet":
            port = svc.get("port")
            if port:
                spec["port"] = int(port)
            spec["strategy"] = svc.get("strategy")
            spec["maxUnavailable"] = svc.get("maxUnavailable")
            spec["nodeSelector"] = svc.get("nodeSelector", "")
            spec["tolerations"] = svc.get("tolerations", [])
            spec["hostNetwork"] = svc.get("hostNetwork", False)
            spec["hostPID"] = svc.get("hostPID", False)
            spec["hostIPC"] = svc.get("hostIPC", False)

        elif svc_kind in ("Job", "CronJob"):
            spec["command"] = svc.get("command", "")
            spec["args"] = svc.get("args", "")
            spec["restartPolicy"] = svc.get("restartPolicy", "Never")
            spec["backoffLimit"] = int(svc.get("backoffLimit", 3))
            spec["completions"] = int(svc.get("completions", 1))
            spec["parallelism"] = int(svc.get("parallelism", 1))
            if svc.get("activeDeadlineSeconds"):
                spec["activeDeadlineSeconds"] = int(svc["activeDeadlineSeconds"])
            spec["ttlSecondsAfterFinished"] = int(svc.get("ttlSecondsAfterFinished", 3600))

            if svc_kind == "CronJob":
                spec["schedule"] = svc.get("schedule", "*/5 * * * *")
                spec["concurrencyPolicy"] = svc.get("concurrencyPolicy", "Forbid")
                spec["suspend"] = svc.get("suspend", False)
                spec["successfulJobsHistoryLimit"] = int(
                    svc.get("successfulJobsHistoryLimit", 3)
                )
                spec["failedJobsHistoryLimit"] = int(
                    svc.get("failedJobsHistoryLimit", 1)
                )
                if svc.get("startingDeadlineSeconds"):
                    spec["startingDeadlineSeconds"] = int(svc["startingDeadlineSeconds"])

        # Add workload resource
        resources.append({
            "kind": svc_kind,
            "name": svc_name,
            "namespace": namespace,
            "output_dir": output_dir,
            "spec": spec,
        })

        # ── Generate Service resource (not for Jobs) ──
        svc_port = svc.get("port")
        if svc_port and not is_job:
            if svc_kind == "StatefulSet":
                # Headless service for StatefulSet
                hl_name = svc.get("headlessServiceName", f"{svc_name}-headless")
                resources.append({
                    "kind": "Service",
                    "name": hl_name,
                    "namespace": namespace,
                    "output_dir": output_dir,
                    "spec": {
                        "headless": True,
                        "port": int(svc_port),
                        "target_port": int(svc_port),
                        "selector": svc_name,
                    },
                })
                # Optional extra ClusterIP service
                if svc.get("alsoCreateClusterIP"):
                    resources.append({
                        "kind": "Service",
                        "name": svc_name,
                        "namespace": namespace,
                        "output_dir": output_dir,
                        "spec": {
                            "type": "ClusterIP",
                            "port": int(svc_port),
                            "target_port": int(svc_port),
                            "selector": svc_name,
                        },
                    })
            else:
                # Regular Service (Deployment, DaemonSet)
                resources.append({
                    "kind": "Service",
                    "name": svc_name,
                    "namespace": namespace,
                    "output_dir": output_dir,
                    "spec": {
                        "type": svc.get("serviceType", "ClusterIP"),
                        "port": int(svc_port),
                        "target_port": int(svc_port),
                        "selector": svc_name,
                    },
                })

    # ── Global: Namespace ──
    if namespace and namespace != "default":
        resources.insert(0, {
            "kind": "Namespace",
            "name": namespace,
            "namespace": namespace,
            "output_dir": output_dir,
        })

    # ── Global: Ingress ──
    ingress_host = data.get("ingress", "")
    if ingress_host:
        # Collect all services with ports for ingress rules
        svc_ports = []
        for svc in services:
            if svc.get("port") and svc.get("kind") not in ("Skip", "Managed", "Job", "CronJob"):
                svc_ports.append({
                    "name": svc["name"],
                    "port": int(svc["port"]),
                })
        if svc_ports:
            # If single service → simple ingress; multi → path-based
            if len(svc_ports) == 1:
                resources.append({
                    "kind": "Ingress",
                    "name": "ingress",
                    "namespace": namespace,
                    "output_dir": output_dir,
                    "spec": {
                        "host": ingress_host if isinstance(ingress_host, str) and ingress_host != "true"
                                else f"{svc_ports[0]['name']}.example.com",
                        "service": svc_ports[0]["name"],
                        "port": svc_ports[0]["port"],
                    },
                })
            else:
                # Multi-service: one Ingress with path-based routing
                # The generate_k8s_wizard function handles single-service Ingress;
                # for multi we build the manifest spec manually
                rules_paths = []
                for sp in svc_ports:
                    rules_paths.append({
                        "path": f"/{sp['name']}",
                        "pathType": "Prefix",
                        "backend": {
                            "service": {
                                "name": sp["name"],
                                "port": {"number": sp["port"]},
                            },
                        },
                    })
                host = ingress_host if isinstance(ingress_host, str) and ingress_host != "true" \
                    else "app.example.com"
                resources.append({
                    "kind": "Ingress",
                    "name": "ingress",
                    "namespace": namespace,
                    "output_dir": output_dir,
                    "spec": {
                        "host": host,
                        "_paths": rules_paths,  # pre-built path rules for generator
                    },
                })

    return resources


def generate_k8s_wizard(
    project_root: Path,
    resources: list[dict],
) -> dict:
    """Generate K8s manifests from wizard resource definitions.

    Args:
        resources: List of resource dicts with:
            kind: Deployment | StatefulSet | DaemonSet | Job | CronJob |
                  Service | ConfigMap | Ingress | Namespace | ...
            name: resource name
            namespace: target namespace
            spec: kind-specific fields (image, port, replicas, etc.)

    Returns:
        {"ok": True, "files": [{path, content, reason}, ...]}
    """
    import yaml
    from src.core.models.template import GeneratedFile

    if not resources:
        return {"error": "At least one resource is required"}

    files: list[dict] = []

    for res in resources:
        kind = (res.get("kind") or "").strip()
        name = (res.get("name") or "").strip()
        namespace = (res.get("namespace") or "default").strip()
        spec = res.get("spec", {})

        if not kind or not name:
            continue

        # Skip Managed services — no manifest generated
        if kind == "Managed":
            continue

        manifest: dict = {
            "apiVersion": _api_version_for_kind(kind),
            "kind": kind,
            "metadata": {
                "name": name,
                "namespace": namespace,
            },
        }

        # ── Workload kinds (have pod templates) ──────────────────
        if kind in ("Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"):
            pod_template = _build_pod_template(name, spec)

            if kind == "Deployment":
                replicas = spec.get("replicas", 1)
                manifest["spec"] = {
                    "replicas": replicas,
                    "selector": {"matchLabels": {"app": name}},
                    "template": pod_template,
                }
                # Deployment strategy — use wizard values, not hardcoded
                strategy_type = spec.get("strategy", "RollingUpdate" if replicas > 1 else "Recreate")
                strategy_obj: dict = {"type": strategy_type}
                if strategy_type == "RollingUpdate":
                    strategy_obj["rollingUpdate"] = {
                        "maxSurge": spec.get("maxSurge", 1),
                        "maxUnavailable": spec.get("maxUnavailable", 0),
                    }
                manifest["spec"]["strategy"] = strategy_obj

            elif kind == "StatefulSet":
                replicas = spec.get("replicas", 1)
                svc_name = spec.get("headlessServiceName", f"{name}-headless")
                manifest["spec"] = {
                    "replicas": replicas,
                    "serviceName": svc_name,
                    "selector": {"matchLabels": {"app": name}},
                    "template": pod_template,
                }
                # Pod management policy
                pmp = spec.get("podManagementPolicy")
                if pmp and pmp != "OrderedReady":  # OrderedReady is default
                    manifest["spec"]["podManagementPolicy"] = pmp
                # Update strategy
                ss_strategy = spec.get("strategy")
                if ss_strategy:
                    ss_update: dict = {"type": ss_strategy}
                    if ss_strategy == "RollingUpdate" and spec.get("partition") is not None:
                        part_val = spec["partition"]
                        if part_val and int(part_val) > 0:
                            ss_update["rollingUpdate"] = {"partition": int(part_val)}
                    manifest["spec"]["updateStrategy"] = ss_update
                # Volume claim templates
                vcts = spec.get("volumeClaimTemplates", [])
                if vcts:
                    manifest["spec"]["volumeClaimTemplates"] = []
                    for vct in vcts:
                        vct_spec: dict = {
                            "metadata": {"name": vct.get("name", "data")},
                            "spec": {
                                "accessModes": [vct.get("accessMode", "ReadWriteOnce")],
                                "resources": {
                                    "requests": {
                                        "storage": vct.get("size", "1Gi"),
                                    },
                                },
                            },
                        }
                        if vct.get("storageClass"):
                            vct_spec["spec"]["storageClassName"] = vct["storageClass"]
                        manifest["spec"]["volumeClaimTemplates"].append(vct_spec)

            elif kind == "DaemonSet":
                manifest["spec"] = {
                    "selector": {"matchLabels": {"app": name}},
                    "template": pod_template,
                }
                # Node selector (string → dict)
                ns_raw = spec.get("nodeSelector")
                if ns_raw:
                    if isinstance(ns_raw, str):
                        # Parse "key=val,key2=val2" format
                        ns_dict = {}
                        for pair in ns_raw.split(","):
                            pair = pair.strip()
                            if "=" in pair:
                                k, v = pair.split("=", 1)
                                ns_dict[k.strip()] = v.strip()
                        if ns_dict:
                            pod_template["spec"]["nodeSelector"] = ns_dict
                    else:
                        pod_template["spec"]["nodeSelector"] = ns_raw
                # Tolerations
                if spec.get("tolerations"):
                    pod_template["spec"]["tolerations"] = spec["tolerations"]
                # Update strategy
                ds_strategy = spec.get("strategy")
                if ds_strategy:
                    ds_update: dict = {"type": ds_strategy}
                    if ds_strategy == "RollingUpdate" and spec.get("maxUnavailable"):
                        ds_update["rollingUpdate"] = {
                            "maxUnavailable": spec["maxUnavailable"],
                        }
                    manifest["spec"]["updateStrategy"] = ds_update

            elif kind == "Job":
                job_spec: dict = {
                    "template": pod_template,
                }
                # Job fields
                if spec.get("backoffLimit") is not None:
                    job_spec["backoffLimit"] = spec["backoffLimit"]
                else:
                    job_spec["backoffLimit"] = 4
                if spec.get("completions") is not None:
                    job_spec["completions"] = spec["completions"]
                if spec.get("parallelism") is not None:
                    job_spec["parallelism"] = spec["parallelism"]
                if spec.get("activeDeadlineSeconds"):
                    job_spec["activeDeadlineSeconds"] = spec["activeDeadlineSeconds"]
                if spec.get("ttlSecondsAfterFinished") is not None:
                    job_spec["ttlSecondsAfterFinished"] = spec["ttlSecondsAfterFinished"]
                # Jobs default to Never restart
                pod_template["spec"]["restartPolicy"] = spec.get("restartPolicy", "Never")
                manifest["spec"] = job_spec

            elif kind == "CronJob":
                schedule = spec.get("schedule", "0 * * * *")
                job_template_pod = pod_template
                job_template_pod["spec"]["restartPolicy"] = spec.get("restartPolicy", "Never")
                manifest["spec"] = {
                    "schedule": schedule,
                    "concurrencyPolicy": spec.get("concurrencyPolicy", "Forbid"),
                    "jobTemplate": {
                        "spec": {
                            "template": job_template_pod,
                            "backoffLimit": spec.get("backoffLimit", 4),
                        },
                    },
                }
                if spec.get("successfulJobsHistoryLimit") is not None:
                    manifest["spec"]["successfulJobsHistoryLimit"] = spec["successfulJobsHistoryLimit"]
                if spec.get("failedJobsHistoryLimit") is not None:
                    manifest["spec"]["failedJobsHistoryLimit"] = spec["failedJobsHistoryLimit"]
                if spec.get("activeDeadlineSeconds"):
                    manifest["spec"]["jobTemplate"]["spec"]["activeDeadlineSeconds"] = spec["activeDeadlineSeconds"]
                # CronJob extras
                if spec.get("suspend"):
                    manifest["spec"]["suspend"] = True
                if spec.get("startingDeadlineSeconds"):
                    manifest["spec"]["startingDeadlineSeconds"] = int(spec["startingDeadlineSeconds"])
                if spec.get("ttlSecondsAfterFinished") is not None:
                    manifest["spec"]["jobTemplate"]["spec"]["ttlSecondsAfterFinished"] = spec["ttlSecondsAfterFinished"]

        elif kind == "Service":
            port = spec.get("port", 80)
            target_port = spec.get("target_port", port)
            svc_type = spec.get("type", "ClusterIP")
            manifest["spec"] = {
                "type": svc_type,
                "selector": {"app": spec.get("selector", name)},
                "ports": [{"port": port, "targetPort": target_port}],
            }
            # Headless service for StatefulSets
            if svc_type == "None" or spec.get("headless"):
                manifest["spec"]["clusterIP"] = "None"

        elif kind == "ConfigMap":
            manifest["data"] = spec.get("data", {})

        elif kind == "Secret":
            manifest["type"] = spec.get("type", "Opaque")
            manifest["stringData"] = spec.get("stringData", spec.get("data", {}))

        elif kind == "Ingress":
            manifest["apiVersion"] = "networking.k8s.io/v1"
            host = spec.get("host", f"{name}.example.com")
            # Multi-service: translator provides pre-built path rules
            if spec.get("_paths"):
                paths = spec["_paths"]
            else:
                # Single service: build simple default-backend path
                port = spec.get("port", 80)
                service = spec.get("service", name)
                paths = [{
                    "path": "/",
                    "pathType": "Prefix",
                    "backend": {
                        "service": {
                            "name": service,
                            "port": {"number": port},
                        },
                    },
                }]
            manifest["spec"] = {
                "rules": [{
                    "host": host,
                    "http": {
                        "paths": paths,
                    },
                }],
            }

        elif kind == "PersistentVolumeClaim":
            pvc_spec: dict = {
                "accessModes": spec.get("accessModes", ["ReadWriteOnce"]),
                "resources": {
                    "requests": {
                        "storage": spec.get("storage", spec.get("size", "1Gi")),
                    },
                },
            }
            sc = spec.get("storageClassName", spec.get("storageClass"))
            if sc:
                pvc_spec["storageClassName"] = sc
            # Bind to specific PV (pvc-static)
            if spec.get("volumeName"):
                pvc_spec["volumeName"] = spec["volumeName"]
            manifest["spec"] = pvc_spec
            # Longhorn annotations
            lh = spec.get("longhornConfig")
            if lh:
                manifest["metadata"].setdefault("annotations", {})
                if lh.get("replicas"):
                    manifest["metadata"]["annotations"]["longhorn.io/number-of-replicas"] = str(lh["replicas"])
                if lh.get("dataLocality"):
                    manifest["metadata"]["annotations"]["longhorn.io/data-locality"] = lh["dataLocality"]

        elif kind == "Namespace":
            del manifest["metadata"]["namespace"]
            manifest.pop("spec", None)

        else:
            # Generic: just metadata, user will edit
            manifest["spec"] = spec or {}

        content = yaml.dump(manifest, default_flow_style=False, sort_keys=False)

        # Use output_dir from resource or default to k8s/
        out_dir = res.get("output_dir", "k8s")
        files.append(GeneratedFile(
            path=f"{out_dir}/{name}-{kind.lower()}.yaml",
            content=content,
            overwrite=False,
            reason=f"{kind} '{name}' in namespace '{namespace}'",
        ).model_dump())

    if not files:
        return {"error": "No valid resources to generate"}

    return {"ok": True, "files": files}


def _build_probe(probe: dict) -> dict:
    """Convert wizard probe format to K8s probe spec.

    Input shape (from _collectProbe in frontend):
        {type: "http"|"tcp"|"exec", path, port, command,
         initialDelaySeconds, periodSeconds, extra (→ failureThreshold)}
    """
    p: dict = {}
    ptype = probe.get("type", "http")
    if ptype == "http":
        p["httpGet"] = {
            "path": probe.get("path", "/health"),
            "port": int(probe.get("port", 8080)),
        }
    elif ptype == "tcp":
        p["tcpSocket"] = {"port": int(probe.get("port", 8080))}
    else:  # exec
        cmd = probe.get("command", "")
        p["exec"] = {"command": ["sh", "-c", cmd] if cmd else ["/bin/true"]}

    delay = probe.get("initialDelaySeconds")
    if delay and int(delay) > 0:
        p["initialDelaySeconds"] = int(delay)
    period = probe.get("periodSeconds")
    if period and int(period) > 0:
        p["periodSeconds"] = int(period)
    threshold = probe.get("extra")
    if threshold and int(threshold) > 0:
        p["failureThreshold"] = int(threshold)

    return p


def _build_wizard_volume(vol: dict, index: int, svc_name: str) -> tuple[dict | None, dict | None]:
    """Convert a wizard volume entry to (pod_volume_def, volume_mount).

    Returns (None, None) if the volume is invalid.
    The caller is responsible for deduplicating pod volumes by name.
    """
    mount_path = vol.get("mountPath", "")
    if not mount_path:
        return None, None

    vol_type = vol.get("type", "emptyDir")
    vol_name: str = ""
    pod_vol: dict = {}
    vm: dict = {}

    if vol_type in ("pvc-dynamic", "pvc-static"):
        vol_name = vol.get("name") or f"data-{index}"
        # PVC claim name also prefixed with svc name for uniqueness
        claim_name = f"{svc_name}-{vol_name}" if svc_name else vol_name
        pod_vol = {"name": vol_name, "persistentVolumeClaim": {"claimName": claim_name}}
        vm = {"name": vol_name, "mountPath": mount_path}

    elif vol_type == "emptyDir":
        vol_name = vol.get("name") or f"empty-{index}"
        empty_spec: dict = {}
        if vol.get("medium") == "Memory":
            empty_spec["medium"] = "Memory"
        if vol.get("sizeLimit"):
            empty_spec["sizeLimit"] = vol["sizeLimit"]
        pod_vol = {"name": vol_name, "emptyDir": empty_spec}
        vm = {"name": vol_name, "mountPath": mount_path}

    elif vol_type == "configMap":
        cm_name = vol.get("configMapName", "")
        vol_name = f"cm-{cm_name}" if cm_name else f"cm-{index}"
        cm_def: dict = {"name": cm_name}
        key = vol.get("key", "")
        if key:
            cm_def["items"] = [{"key": key, "path": key}]
        pod_vol = {"name": vol_name, "configMap": cm_def}
        vm = {"name": vol_name, "mountPath": mount_path}
        if key:
            vm["subPath"] = key

    elif vol_type == "secret":
        sec_name = vol.get("secretName", "")
        vol_name = f"sec-{sec_name}" if sec_name else f"sec-{index}"
        sec_def: dict = {"secretName": sec_name}
        key = vol.get("key", "")
        if key:
            sec_def["items"] = [{"key": key, "path": key}]
        pod_vol = {"name": vol_name, "secret": sec_def}
        vm = {"name": vol_name, "mountPath": mount_path}
        if key:
            vm["subPath"] = key

    elif vol_type == "hostPath":
        vol_name = vol.get("name") or f"hp-{index}"
        hp_def: dict = {"path": vol.get("hostPath", mount_path)}
        host_type = vol.get("hostType", "")
        if host_type:
            hp_def["type"] = host_type
        pod_vol = {"name": vol_name, "hostPath": hp_def}
        vm = {"name": vol_name, "mountPath": mount_path}

    else:
        return None, None

    return pod_vol, vm


def _build_pod_template(name: str, spec: dict) -> dict:
    """Build a pod template dict shared across all workload kinds.

    Handles: main container, init containers, sidecar containers,
    companion containers, volumes, probes, host access, and mesh annotations.
    """
    image = spec.get("image", f"{name}:latest")
    port = spec.get("port")

    # ── Main container ──
    main_container: dict = {
        "name": name,
        "image": image,
    }
    if port:
        main_container["ports"] = [{"containerPort": int(port)}]

    # Job/CronJob command/args override
    cmd = spec.get("command", "")
    if cmd:
        main_container["command"] = ["sh", "-c", cmd]
    args = spec.get("args", "")
    if args:
        main_container["args"] = args.split() if isinstance(args, str) else args

    # Resource limits
    resources: dict = {}
    if spec.get("cpu_limit") or spec.get("memory_limit"):
        resources["limits"] = {}
        if spec.get("cpu_limit"):
            resources["limits"]["cpu"] = spec["cpu_limit"]
        if spec.get("memory_limit"):
            resources["limits"]["memory"] = spec["memory_limit"]
    if spec.get("cpu_request") or spec.get("memory_request"):
        resources.setdefault("requests", {})
        if spec.get("cpu_request"):
            resources["requests"]["cpu"] = spec["cpu_request"]
        if spec.get("memory_request"):
            resources["requests"]["memory"] = spec["memory_request"]
    if resources:
        main_container["resources"] = resources

    # ── Health probes ──
    if spec.get("readinessProbe"):
        main_container["readinessProbe"] = _build_probe(spec["readinessProbe"])
    if spec.get("livenessProbe"):
        main_container["livenessProbe"] = _build_probe(spec["livenessProbe"])

    # ── Env vars ──
    # svc_name is used by the translator to set the correct ConfigMap/Secret name
    env_list = _build_env_vars(spec.get("env"), svc_name=spec.get("_svc_name", ""))
    if env_list:
        main_container["env"] = env_list

    # envFrom — bulk ConfigMap/Secret refs (set by translator)
    env_from = spec.get("envFrom")
    if env_from:
        main_container["envFrom"] = env_from

    pod_spec: dict = {
        "containers": [main_container],
    }

    # ── Init containers ──
    init_containers_list: list[dict] = []
    for ic in (spec.get("initContainers") or []):
        ic_spec: dict = {
            "name": ic.get("name", "init"),
            "image": ic.get("image", "busybox:1.36"),
        }
        cmd = ic.get("command", "")
        if cmd:
            ic_spec["command"] = ["sh", "-c", cmd]
        init_containers_list.append(ic_spec)

    # ── Sidecar containers ──
    # ── Volumes ──
    # Start with any pod-level volumes already provided (rare, for direct API)
    volumes: list[dict] = list(spec.get("_pod_volumes") or [])
    volume_mounts_main: list[dict] = list(spec.get("volumeMounts") or [])

    # Process wizard volumes (from _collectVolumes frontend)
    vol_names_seen: set[str] = {v.get("name", "") for v in volumes}
    for vi, wv in enumerate(spec.get("wizardVolumes") or []):
        pod_vol_def, vm_def = _build_wizard_volume(wv, vi, name)
        if pod_vol_def and vm_def:
            vn = pod_vol_def.get("name", "")
            if vn and vn not in vol_names_seen:
                volumes.append(pod_vol_def)
                vol_names_seen.add(vn)
            volume_mounts_main.append(vm_def)

    for sc in (spec.get("sidecars") or []):
        sc_spec: dict = {
            "name": sc.get("name", "sidecar"),
            "image": sc.get("image", ""),
        }
        cmd = sc.get("command", "")
        if cmd:
            sc_spec["command"] = ["sh", "-c", cmd]

        # Shared volume handling
        shared_vol = sc.get("sharedVolume", "")
        shared_mount = sc.get("sharedMount", "")
        if shared_vol and shared_mount:
            # Add emptyDir volume if not already present
            vol_names = {v.get("name") for v in volumes}
            if shared_vol not in vol_names:
                volumes.append({"name": shared_vol, "emptyDir": {}})
            sc_spec["volumeMounts"] = [{"name": shared_vol, "mountPath": shared_mount}]
            # Also mount in the main container
            volume_mounts_main.append({"name": shared_vol, "mountPath": shared_mount})

        if sc.get("nativeSidecar", True):
            # Native sidecar (K8s ≥ 1.28): add to initContainers with restartPolicy: Always
            sc_spec["restartPolicy"] = "Always"
            init_containers_list.append(sc_spec)
        else:
            # Regular sidecar: add to containers[]
            pod_spec["containers"].append(sc_spec)

    # ── Companion containers (from "move into pod") ──
    for comp in (spec.get("companions") or []):
        comp_spec: dict = {
            "name": comp.get("name", "companion"),
            "image": comp.get("image", ""),
        }
        if comp.get("port"):
            comp_spec["ports"] = [{"containerPort": int(comp["port"])}]
        comp_env = _build_env_vars(comp.get("env"))
        if comp_env:
            comp_spec["env"] = comp_env

        # Companion resource limits
        comp_res = comp.get("resources")
        if comp_res:
            res_spec: dict = {}
            if comp_res.get("cpu_limit") or comp_res.get("memory_limit"):
                res_spec["limits"] = {}
                if comp_res.get("cpu_limit"):
                    res_spec["limits"]["cpu"] = comp_res["cpu_limit"]
                if comp_res.get("memory_limit"):
                    res_spec["limits"]["memory"] = comp_res["memory_limit"]
            if comp_res.get("cpu_request") or comp_res.get("memory_request"):
                res_spec.setdefault("requests", {})
                if comp_res.get("cpu_request"):
                    res_spec["requests"]["cpu"] = comp_res["cpu_request"]
                if comp_res.get("memory_request"):
                    res_spec["requests"]["memory"] = comp_res["memory_request"]
            if res_spec:
                comp_spec["resources"] = res_spec

        # Companion volume mounts
        comp_vols = comp.get("volumes") or []
        if comp_vols:
            comp_volume_mounts: list[dict] = []
            vol_names = {v.get("name") for v in volumes}
            for cv in comp_vols:
                mount_path = cv.get("mountPath", "")
                vol_name = cv.get("name", "")
                vol_type = cv.get("type", "emptyDir")
                if not mount_path:
                    continue
                # Add to pod-level volumes if not already present
                if vol_name and vol_name not in vol_names:
                    if vol_type == "emptyDir":
                        volumes.append({"name": vol_name, "emptyDir": {}})
                    elif vol_type in ("pvc-dynamic", "pvc-static"):
                        volumes.append({
                            "name": vol_name,
                            "persistentVolumeClaim": {"claimName": vol_name},
                        })
                    elif vol_type == "configMap":
                        volumes.append({
                            "name": vol_name,
                            "configMap": {"name": vol_name},
                        })
                    elif vol_type == "secret":
                        volumes.append({
                            "name": vol_name,
                            "secret": {"secretName": vol_name},
                        })
                    vol_names.add(vol_name)
                if vol_name:
                    comp_volume_mounts.append({
                        "name": vol_name,
                        "mountPath": mount_path,
                    })
            if comp_volume_mounts:
                comp_spec["volumeMounts"] = comp_volume_mounts

        pod_spec["containers"].append(comp_spec)

        # Companion startup dependency → wait-for init container
        depends_on = comp.get("dependsOn")
        if depends_on and depends_on != "__main__":
            # Infrastructure service — use K8s DNS name
            wait_host = depends_on
            wait_port = str(comp.get("dependsOnPort") or spec.get("port", "8080"))

            wait_name = f"wait-for-{comp.get('name', 'companion')}"
            wait_cmd = (
                f"echo 'Waiting for {wait_host}:{wait_port}…'; "
                f"until nc -z {wait_host} {wait_port}; do sleep 2; done; "
                f"echo 'Ready.'"
            )
            init_containers_list.append({
                "name": wait_name,
                "image": "busybox:1.36",
                "command": ["sh", "-c", wait_cmd],
            })

    # ── Finalize initContainers (after ALL sources: user, sidecar, companion) ──
    if init_containers_list:
        pod_spec["initContainers"] = init_containers_list

    # ── VCT volumeMounts (StatefulSet) ──
    # VolumeClaimTemplates don't need pod volumes[] — K8s injects them.
    # But the container DOES need volumeMounts referencing each VCT by name.
    for vct in (spec.get("volumeClaimTemplates") or []):
        vct_name = vct.get("name", "")
        vct_mount = vct.get("mountPath", "")
        if vct_name and vct_mount:
            volume_mounts_main.append({
                "name": vct_name,
                "mountPath": vct_mount,
            })

    # ── Final volume assembly ──
    if volumes:
        pod_spec["volumes"] = volumes
    if volume_mounts_main:
        main_container["volumeMounts"] = volume_mounts_main

    # ── Host access flags (DaemonSet) ──
    if spec.get("hostNetwork"):
        pod_spec["hostNetwork"] = True
    if spec.get("hostPID"):
        pod_spec["hostPID"] = True
    if spec.get("hostIPC"):
        pod_spec["hostIPC"] = True

    # Build the template
    template: dict = {
        "metadata": {"labels": {"app": name}},
        "spec": pod_spec,
    }

    # ── Mesh annotations ──
    mesh = spec.get("mesh")
    if mesh:
        annotations = _build_mesh_annotations(mesh)
        if annotations:
            template["metadata"]["annotations"] = annotations

    return template


def _build_env_vars(env_spec, *, svc_name: str = "") -> list[dict]:
    """Build K8s env var list from various input formats.

    Handles:
    - dict: simple {KEY: value} mapping
    - list of {name, value} or {name, secretName} (classic K8s format)
    - list of {key, type, value, varName} (wizard frontend format)

    When svc_name is provided (set by the translator), wizard-format env vars
    use the service-name convention for ConfigMap/Secret references:
        secret  → secretKeyRef.name = "{svc_name}-secrets"
        variable → configMapKeyRef.name = "{svc_name}-config"
        hardcoded → configMapKeyRef.name = "{svc_name}-config"
    This ensures the references match the ConfigMap/Secret resources that
    the translator generates alongside the workload.
    """
    if not env_spec:
        return []
    if isinstance(env_spec, dict):
        return [{"name": k, "value": str(v)} for k, v in env_spec.items()]
    if isinstance(env_spec, list):
        result: list[dict] = []
        for item in env_spec:
            if not isinstance(item, dict):
                continue
            # Accept both "name" and "key" as the env var name
            env_name = item.get("name") or item.get("key")
            if not env_name:
                continue
            entry: dict = {"name": env_name}
            # Classic format: explicit secretKeyRef
            if item.get("secretName"):
                entry["valueFrom"] = {
                    "secretKeyRef": {
                        "name": item["secretName"],
                        "key": item.get("secretKey", env_name),
                    },
                }
            elif item.get("configMapName"):
                entry["valueFrom"] = {
                    "configMapKeyRef": {
                        "name": item["configMapName"],
                        "key": item.get("configMapKey", env_name),
                    },
                }
            # Wizard format: type-based routing
            elif item.get("type") == "secret":
                # Use service-name convention when svc_name is known
                if svc_name:
                    secret_ref_name = f"{svc_name}-secrets"
                else:
                    # Fallback: derive from varName
                    var_ref = (item.get("varName") or "").strip("${}")
                    secret_ref_name = var_ref.lower().replace("_", "-") if var_ref else env_name.lower().replace("_", "-")
                entry["valueFrom"] = {
                    "secretKeyRef": {
                        "name": secret_ref_name,
                        "key": env_name,
                    },
                }
            elif item.get("type") == "variable":
                if svc_name:
                    cm_ref_name = f"{svc_name}-config"
                else:
                    var_ref = (item.get("varName") or "").strip("${}")
                    cm_ref_name = var_ref.lower().replace("_", "-") if var_ref else "app-config"
                entry["valueFrom"] = {
                    "configMapKeyRef": {
                        "name": cm_ref_name,
                        "key": env_name,
                    },
                }
            else:
                # hardcoded: inline value for now.
                # When svc_name is set, the translator uses envFrom for bulk
                # ConfigMap injection, so hardcoded vars go into the ConfigMap
                # resource and don't need individual env entries. BUT we still
                # include them here as fallback for direct API use.
                entry["value"] = str(item.get("value", ""))
            result.append(entry)
        return result
    return []


_MESH_ANNOTATION_PREFIXES = {
    "istio": {
        "inject": "sidecar.istio.io/inject",
        "proxyCPU": "sidecar.istio.io/proxyCPU",
        "proxyCPULimit": "sidecar.istio.io/proxyCPULimit",
        "proxyMemory": "sidecar.istio.io/proxyMemory",
        "proxyMemoryLimit": "sidecar.istio.io/proxyMemoryLimit",
        "logLevel": "sidecar.istio.io/logLevel",
        "excludeInbound": "traffic.sidecar.istio.io/excludeInboundPorts",
        "excludeOutbound": "traffic.sidecar.istio.io/excludeOutboundPorts",
    },
    "linkerd": {
        "inject": "linkerd.io/inject",
        "proxyCPU": "config.linkerd.io/proxy-cpu-request",
        "proxyCPULimit": "config.linkerd.io/proxy-cpu-limit",
        "proxyMemory": "config.linkerd.io/proxy-memory-request",
        "proxyMemoryLimit": "config.linkerd.io/proxy-memory-limit",
        "logLevel": "config.linkerd.io/proxy-log-level",
        "excludeInbound": "config.linkerd.io/skip-inbound-ports",
        "excludeOutbound": "config.linkerd.io/skip-outbound-ports",
    },
    "consul": {
        "inject": "consul.hashicorp.com/connect-inject",
        "proxyCPU": "consul.hashicorp.com/sidecar-proxy-cpu-request",
        "proxyCPULimit": "consul.hashicorp.com/sidecar-proxy-cpu-limit",
        "proxyMemory": "consul.hashicorp.com/sidecar-proxy-memory-request",
        "proxyMemoryLimit": "consul.hashicorp.com/sidecar-proxy-memory-limit",
        "logLevel": "",
        "excludeInbound": "",
        "excludeOutbound": "",
    },
    "kuma": {
        "inject": "kuma.io/sidecar-injection",
        "proxyCPU": "kuma.io/sidecar-proxy-cpu-requests",
        "proxyCPULimit": "kuma.io/sidecar-proxy-cpu-limits",
        "proxyMemory": "kuma.io/sidecar-proxy-memory-requests",
        "proxyMemoryLimit": "kuma.io/sidecar-proxy-memory-limits",
        "logLevel": "",
        "excludeInbound": "",
        "excludeOutbound": "",
    },
}


def _build_mesh_annotations(mesh: dict) -> dict:
    """Build mesh-provider-specific annotations for pod template."""
    provider = mesh.get("provider", "istio")
    prefixes = _MESH_ANNOTATION_PREFIXES.get(provider, _MESH_ANNOTATION_PREFIXES["istio"])

    annotations: dict = {}

    # Inject annotation
    inject_key = prefixes.get("inject", "")
    if inject_key:
        annotations[inject_key] = "true" if provider != "linkerd" else "enabled"

    # Proxy resources
    field_map = {
        "proxyCpuRequest": "proxyCPU",
        "proxyCpuLimit": "proxyCPULimit",
        "proxyMemRequest": "proxyMemory",
        "proxyMemLimit": "proxyMemoryLimit",
    }
    for mesh_key, prefix_key in field_map.items():
        val = mesh.get(mesh_key, "")
        anno_key = prefixes.get(prefix_key, "")
        if val and anno_key:
            annotations[anno_key] = val

    # Log level
    log_level = mesh.get("logLevel", "")
    log_key = prefixes.get("logLevel", "")
    if log_level and log_key:
        annotations[log_key] = log_level

    # Exclude ports
    for field, prefix_key in [("excludeInbound", "excludeInbound"), ("excludeOutbound", "excludeOutbound")]:
        val = mesh.get(field, "")
        anno_key = prefixes.get(prefix_key, "")
        if val and anno_key:
            annotations[anno_key] = val

    return annotations


def _api_version_for_kind(kind: str) -> str:
    """Resolve the conventional apiVersion for a K8s kind."""
    mapping = {
        "Deployment": "apps/v1",
        "StatefulSet": "apps/v1",
        "DaemonSet": "apps/v1",
        "ReplicaSet": "apps/v1",
        "Job": "batch/v1",
        "CronJob": "batch/v1",
        "Ingress": "networking.k8s.io/v1",
        "NetworkPolicy": "networking.k8s.io/v1",
        "HorizontalPodAutoscaler": "autoscaling/v2",
    }
    return mapping.get(kind, "v1")
