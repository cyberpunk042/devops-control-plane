"""K8s validation — Layer 4: Cluster-aware checks.

Online cluster checks: API version compatibility, storage classes,
server version constraints.
"""

from __future__ import annotations

from .cluster import cluster_status, k8s_storage_classes


# ═══════════════════════════════════════════════════════════════════
#  Layer 4 — Cluster-aware validation
# ═══════════════════════════════════════════════════════════════════

# Cluster types that don't support LoadBalancer natively
_LOCAL_CLUSTER_TYPES = {"minikube", "kind", "docker_desktop", "k3d", "k3s"}

# Infra services referenced by resource kinds/annotations
_INFRA_REQUIREMENTS = {
    "Ingress": "ingress-controller",
    "ServiceMonitor": "prometheus",
    "PrometheusRule": "prometheus",
    "PodMonitor": "prometheus",
}

_CERT_MANAGER_ANNOTATION_PREFIX = "cert-manager.io/"


def _parse_k8s_version(version_str: str) -> tuple[int, int] | None:
    """Parse a Kubernetes version string like 'v1.28.0' into (major, minor)."""
    m = re.match(r"v?(\d+)\.(\d+)", version_str or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _get_kubectl_server_version() -> str:
    """Get the Kubernetes server version from kubectl.

    Returns version string like 'v1.28.0' or empty string on failure.
    """
    try:
        from .common import _run_kubectl
        result = _run_kubectl("version", "--output=json", timeout=5)
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            server = data.get("serverVersion", {})
            major = server.get("major", "")
            minor = server.get("minor", "").rstrip("+")
            if major and minor:
                return f"v{major}.{minor}.0"
    except Exception:
        pass
    return ""


def _validate_cluster_aware(
    status: dict,
    all_resources: list[tuple[str, dict]],
    issues: list[dict],
) -> None:
    """Layer 4: Validate against the connected cluster.

    Calls cluster_status() to get live cluster data. If no cluster
    is connected, this layer is silently skipped.
    """
    # Try to get cluster info — skip if unavailable
    try:
        cluster = cluster_status()
    except Exception:
        return  # cluster operations not available
    if not cluster.get("connected"):
        return  # no cluster connection — skip Layer 4

    cluster_type = cluster.get("cluster_type", {}).get("type", "unknown")
    cluster_namespaces = set(cluster.get("namespaces", []))

    # Collect infra services — distinguish providers from consumers
    # A service detected via "helm_chart" is a PROVIDER (user is deploying it)
    # A service detected via "resource_kind" or "manifest_annotation" is a CONSUMER (user needs it)
    infra_providers: set[str] = set()  # actually deployed in manifests
    for svc in status.get("infra_services", []):
        via = svc.get("detected_via", "")
        name = svc.get("name", "")
        if via == "helm_chart":
            infra_providers.add(name)

    # Get tool availability from status
    tool_availability = status.get("tool_availability", {})
    deployment_strategy = status.get("deployment_strategy", "none")
    strategies_detected = status.get("strategies_detected", [])

    # Get kubectl client version
    kubectl_info = status.get("kubectl", {})
    client_version = kubectl_info.get("version", "")

    # ── Checks ────────────────────────────────────────────────────

    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        name = res.get("metadata", {}).get("name", "?")
        namespace = res.get("metadata", {}).get("namespace", "")
        annotations = res.get("metadata", {}).get("annotations", {}) or {}

        # 1. Service type ↔ cluster type
        if kind == "Service":
            svc_type = res.get("spec", {}).get("type", "ClusterIP")
            if svc_type == "LoadBalancer" and cluster_type in _LOCAL_CLUSTER_TYPES:
                issues.append({
                    "file": rel_path,
                    "severity": "warning",
                    "message": f"Service/{name}: type LoadBalancer on {cluster_type} — won't get external IP (use NodePort or tunnel)",
                })

        # 2. Ingress ↔ ingress controller
        if kind == "Ingress":
            if "ingress-controller" not in infra_providers and "ingress-nginx" not in infra_providers:
                issues.append({
                    "file": rel_path,
                    "severity": "warning",
                    "message": f"Ingress/{name}: no ingress controller detected in manifests — ensure one is installed on the cluster",
                })

        # 3. cert-manager annotations ↔ cert-manager
        if isinstance(annotations, dict):
            has_cm_annotations = any(
                k.startswith(_CERT_MANAGER_ANNOTATION_PREFIX)
                for k in annotations
            )
            if has_cm_annotations and "cert-manager" not in infra_providers:
                issues.append({
                    "file": rel_path,
                    "severity": "warning",
                    "message": f"{kind}/{name}: cert-manager annotations present but cert-manager not detected in manifests",
                })

        # 4. Prometheus CRDs ↔ Prometheus
        if kind in ("ServiceMonitor", "PrometheusRule", "PodMonitor"):
            if "prometheus" not in infra_providers:
                issues.append({
                    "file": rel_path,
                    "severity": "warning",
                    "message": f"{kind}/{name}: requires Prometheus operator but prometheus not detected in manifests",
                })

        # 7. Namespace existence on cluster
        if namespace and namespace not in cluster_namespaces:
            issues.append({
                "file": rel_path,
                "severity": "info",
                "message": f"{kind}/{name}: namespace '{namespace}' does not exist on cluster (will need --create-namespace or manual creation)",
            })

        # 8. StorageClass existence
        if kind == "PersistentVolumeClaim":
            sc_name = res.get("spec", {}).get("storageClassName")
            if sc_name:
                # Check if this StorageClass exists on cluster
                try:
                    sc_data = k8s_storage_classes()
                    if sc_data.get("ok"):
                        sc_names = {
                            sc.get("name", "")
                            for sc in sc_data.get("storage_classes", [])
                        }
                        if sc_name not in sc_names:
                            issues.append({
                                "file": rel_path,
                                "severity": "warning",
                                "message": f"PVC/{name}: StorageClass '{sc_name}' not found on cluster",
                            })
                except Exception:
                    pass  # can't check — don't warn

        # 9. CRD availability — non-standard kinds
        if kind and kind not in _K8S_KINDS and kind not in _INFRA_REQUIREMENTS:
            issues.append({
                "file": rel_path,
                "severity": "info",
                "message": f"{kind}/{name}: custom resource — ensure CRD is installed on cluster",
            })

    # 5. Tool ↔ strategy: Helm
    if "helm" in strategies_detected:
        helm_tool = tool_availability.get("helm", {})
        if not helm_tool.get("available", False):
            issues.append({
                "file": "(cluster-aware)",
                "severity": "error",
                "message": "deployment strategy requires Helm but helm is not installed/available",
            })

    # 6. Tool ↔ strategy: Kustomize
    if "kustomize" in strategies_detected:
        kustomize_tool = tool_availability.get("kustomize", {})
        if not kustomize_tool.get("available", False):
            issues.append({
                "file": "(cluster-aware)",
                "severity": "error",
                "message": "deployment strategy requires Kustomize but kustomize is not installed/available",
            })

    # 10. kubectl version skew
    server_version = ""
    # Try to get server version from cluster nodes
    nodes = cluster.get("nodes", [])
    if nodes:
        server_version = nodes[0].get("version", "")
    # Or try kubectl version command
    if not server_version:
        server_version = _get_kubectl_server_version()

    if client_version and server_version:
        client_parsed = _parse_k8s_version(client_version)
        server_parsed = _parse_k8s_version(server_version)
        if client_parsed and server_parsed:
            _, client_minor = client_parsed
            _, server_minor = server_parsed
            skew = abs(client_minor - server_minor)
            if skew > 1:
                issues.append({
                    "file": "(cluster-aware)",
                    "severity": "warning",
                    "message": f"kubectl version skew: client {client_version} vs server {server_version} (differ by {skew} minor versions, supported skew is ±1)",
                })


