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
#  K8s Manifest Wizard
# ═══════════════════════════════════════════════════════════════════


def generate_k8s_wizard(
    project_root: Path,
    resources: list[dict],
) -> dict:
    """Generate K8s manifests from wizard resource definitions.

    Args:
        resources: List of resource dicts with:
            kind: Deployment | Service | ConfigMap | Ingress | ...
            name: resource name
            namespace: target namespace
            spec: kind-specific fields (image, port, replicas, data, etc.)

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

        manifest: dict = {
            "apiVersion": _api_version_for_kind(kind),
            "kind": kind,
            "metadata": {
                "name": name,
                "namespace": namespace,
            },
        }

        if kind == "Deployment":
            image = spec.get("image", f"{name}:latest")
            port = spec.get("port", 8080)
            replicas = spec.get("replicas", 1)

            manifest["spec"] = {
                "replicas": replicas,
                "selector": {"matchLabels": {"app": name}},
                "template": {
                    "metadata": {"labels": {"app": name}},
                    "spec": {
                        "containers": [{
                            "name": name,
                            "image": image,
                            "ports": [{"containerPort": port}],
                        }],
                    },
                },
            }

            # Resource limits
            if spec.get("cpu_limit") or spec.get("memory_limit"):
                container = manifest["spec"]["template"]["spec"]["containers"][0]
                container["resources"] = {"limits": {}, "requests": {}}
                if spec.get("memory_limit"):
                    container["resources"]["limits"]["memory"] = spec["memory_limit"]
                    container["resources"]["requests"]["memory"] = spec.get("memory_request", spec["memory_limit"])
                if spec.get("cpu_limit"):
                    container["resources"]["limits"]["cpu"] = spec["cpu_limit"]
                    container["resources"]["requests"]["cpu"] = spec.get("cpu_request", spec["cpu_limit"])

            # Env vars
            if spec.get("env"):
                container = manifest["spec"]["template"]["spec"]["containers"][0]
                container["env"] = [
                    {"name": k, "value": str(v)}
                    for k, v in spec["env"].items()
                ]

        elif kind == "Service":
            port = spec.get("port", 80)
            target_port = spec.get("target_port", port)
            svc_type = spec.get("type", "ClusterIP")
            manifest["spec"] = {
                "type": svc_type,
                "selector": {"app": spec.get("selector", name)},
                "ports": [{"port": port, "targetPort": target_port}],
            }

        elif kind == "ConfigMap":
            manifest["data"] = spec.get("data", {})

        elif kind == "Ingress":
            manifest["apiVersion"] = "networking.k8s.io/v1"
            host = spec.get("host", f"{name}.example.com")
            port = spec.get("port", 80)
            service = spec.get("service", name)
            manifest["spec"] = {
                "rules": [{
                    "host": host,
                    "http": {
                        "paths": [{
                            "path": "/",
                            "pathType": "Prefix",
                            "backend": {
                                "service": {
                                    "name": service,
                                    "port": {"number": port},
                                },
                            },
                        }],
                    },
                }],
            }

        elif kind == "Namespace":
            del manifest["metadata"]["namespace"]
            manifest.pop("spec", None)

        else:
            # Generic: just metadata, user will edit
            manifest["spec"] = spec or {}

        content = yaml.dump(manifest, default_flow_style=False, sort_keys=False)

        files.append(GeneratedFile(
            path=f"k8s/{name}-{kind.lower()}.yaml",
            content=content,
            overwrite=False,
            reason=f"{kind} '{name}' in namespace '{namespace}'",
        ).model_dump())

    if not files:
        return {"error": "No valid resources to generate"}

    return {"ok": True, "files": files}


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
