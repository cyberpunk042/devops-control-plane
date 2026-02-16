"""K8s cluster operations — online kubectl interactions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.core.services.k8s_common import _run_kubectl, _kubectl_available


logger = logging.getLogger(__name__)

from src.core.services.audit_helpers import make_auditor

_audit = make_auditor("k8s")

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
