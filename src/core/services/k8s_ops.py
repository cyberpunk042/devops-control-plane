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
#  Facilitate: Manifest generation
# ═══════════════════════════════════════════════════════════════════


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
