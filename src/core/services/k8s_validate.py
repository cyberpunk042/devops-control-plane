"""K8s manifest validation — structural and best-practice checks.

Layers:
  1. Per-resource structural (this module)
  2. Cross-resource consistency (this module)
  3. Environment-aware (this module)
  4. Cluster-aware (this module)
  5. Security & production readiness (this module)
  6. Cross-domain validation (this module)
  7. Deployment strategy validation (this module)
"""

from __future__ import annotations

import re
from pathlib import Path

from src.core.services.k8s_common import _K8S_API_VERSIONS, _K8S_KINDS, _parse_k8s_yaml
from src.core.services.k8s_detect import k8s_status
from src.core.services.k8s_cluster import cluster_status, k8s_storage_classes
from src.core.services.k8s_wizard_detect import k8s_env_namespaces
from src.core.services.docker_detect import docker_status
from src.core.services.ci_ops import ci_status, ci_workflows
from src.core.services.terraform_ops import terraform_status
import logging

logger = logging.getLogger(__name__)

# Kinds that can be targeted by an HPA
_SCALABLE_KINDS = {"Deployment", "StatefulSet", "ReplicaSet"}

# Valid CronJob concurrencyPolicy values
_VALID_CONCURRENCY_POLICIES = {"Allow", "Forbid", "Replace"}

# Regex for a basic 5-field cron expression
_CRON_RE = re.compile(
    r"^\s*"
    r"(\S+)\s+"   # minute
    r"(\S+)\s+"   # hour
    r"(\S+)\s+"   # day of month
    r"(\S+)\s+"   # month
    r"(\S+)"      # day of week
    r"\s*$"
)



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


def _validate_statefulset(res: dict, path: str, issues: list[dict]) -> None:
    """StatefulSet-specific validation."""
    spec = res.get("spec", {})
    name = res.get("metadata", {}).get("name", "?")

    service_name = spec.get("serviceName")
    if not service_name:
        issues.append({
            "file": path,
            "severity": "error",
            "message": f"StatefulSet/{name}: missing serviceName (required by K8s API)",
        })


def _validate_job(res: dict, path: str, issues: list[dict]) -> None:
    """Job-specific validation."""
    spec = res.get("spec", {})
    name = res.get("metadata", {}).get("name", "?")

    backoff = spec.get("backoffLimit")
    if backoff is not None and isinstance(backoff, int) and backoff < 0:
        issues.append({
            "file": path,
            "severity": "error",
            "message": f"Job/{name}: backoffLimit is negative ({backoff})",
        })

    completions = spec.get("completions")
    parallelism = spec.get("parallelism")
    if (
        completions is not None
        and parallelism is not None
        and isinstance(completions, int)
        and isinstance(parallelism, int)
        and parallelism > completions
    ):
        issues.append({
            "file": path,
            "severity": "warning",
            "message": f"Job/{name}: parallelism ({parallelism}) > completions ({completions})",
        })


def _is_valid_cron(expr: str) -> bool:
    """Check if *expr* looks like a valid 5-field cron expression."""
    return _CRON_RE.match(expr) is not None


def _validate_cronjob(res: dict, path: str, issues: list[dict]) -> None:
    """CronJob-specific validation."""
    spec = res.get("spec", {})
    name = res.get("metadata", {}).get("name", "?")

    schedule = spec.get("schedule")
    if not schedule:
        issues.append({
            "file": path,
            "severity": "error",
            "message": f"CronJob/{name}: missing schedule",
        })
    elif not _is_valid_cron(schedule):
        issues.append({
            "file": path,
            "severity": "error",
            "message": f"CronJob/{name}: invalid cron schedule '{schedule}'",
        })

    policy = spec.get("concurrencyPolicy")
    if policy and policy not in _VALID_CONCURRENCY_POLICIES:
        issues.append({
            "file": path,
            "severity": "warning",
            "message": f"CronJob/{name}: invalid concurrencyPolicy '{policy}' (expected Allow/Forbid/Replace)",
        })


def _validate_daemonset(res: dict, path: str, issues: list[dict]) -> None:
    """DaemonSet-specific validation."""
    spec = res.get("spec", {})
    name = res.get("metadata", {}).get("name", "?")

    if "replicas" in spec:
        issues.append({
            "file": path,
            "severity": "warning",
            "message": f"DaemonSet/{name}: has replicas field (DaemonSet runs on every node, replicas is ignored)",
        })


def _validate_ingress(res: dict, path: str, issues: list[dict]) -> None:
    """Ingress-specific validation."""
    spec = res.get("spec", {})
    metadata = res.get("metadata", {})
    name = metadata.get("name", "?")
    annotations = metadata.get("annotations", {})

    # Check ingressClassName (required K8s 1.22+)
    has_class = bool(spec.get("ingressClassName"))
    has_class_annotation = "kubernetes.io/ingress.class" in annotations
    if not has_class and not has_class_annotation:
        issues.append({
            "file": path,
            "severity": "warning",
            "message": f"Ingress/{name}: no ingressClassName (required K8s 1.22+)",
        })

    # Check pathType on all paths
    for rule in spec.get("rules", []):
        http = rule.get("http", {})
        for p in http.get("paths", []):
            if not p.get("pathType"):
                issues.append({
                    "file": path,
                    "severity": "error",
                    "message": f"Ingress/{name}: path '{p.get('path', '?')}' missing pathType (required K8s 1.22+)",
                })


def _validate_hpa(res: dict, path: str, issues: list[dict]) -> None:
    """HorizontalPodAutoscaler-specific validation."""
    spec = res.get("spec", {})
    name = res.get("metadata", {}).get("name", "?")

    min_r = spec.get("minReplicas", 1)
    max_r = spec.get("maxReplicas", 0)
    if isinstance(min_r, int) and isinstance(max_r, int) and min_r >= max_r:
        issues.append({
            "file": path,
            "severity": "error",
            "message": f"HPA/{name}: minReplicas ({min_r}) >= maxReplicas ({max_r})",
        })

    target_ref = spec.get("scaleTargetRef", {})
    target_kind = target_ref.get("kind", "")
    if target_kind and target_kind not in _SCALABLE_KINDS:
        issues.append({
            "file": path,
            "severity": "error",
            "message": f"HPA/{name}: scaleTargetRef.kind '{target_kind}' is not scalable (expected Deployment/StatefulSet/ReplicaSet)",
        })

    if not spec.get("metrics"):
        issues.append({
            "file": path,
            "severity": "warning",
            "message": f"HPA/{name}: no metrics defined (HPA has no scaling criteria)",
        })


# ═══════════════════════════════════════════════════════════════════
#  Layer 2 — Cross-resource consistency validation
# ═══════════════════════════════════════════════════════════════════

# Workload kinds that have pod templates with labels
_WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job"}


def _get_pod_spec(res: dict) -> dict | None:
    """Extract the pod spec from a resource, handling both Pod and templated kinds."""
    kind = res.get("kind", "")
    if kind == "Pod":
        return res.get("spec", {})
    if kind == "CronJob":
        return (
            res.get("spec", {})
            .get("jobTemplate", {})
            .get("spec", {})
            .get("template", {})
            .get("spec", {})
        )
    # Deployment, StatefulSet, DaemonSet, Job, ReplicaSet
    return res.get("spec", {}).get("template", {}).get("spec", {})


def _get_pod_labels(res: dict) -> dict:
    """Extract pod template labels from a workload resource."""
    kind = res.get("kind", "")
    if kind == "Pod":
        return res.get("metadata", {}).get("labels", {})
    if kind == "CronJob":
        return (
            res.get("spec", {})
            .get("jobTemplate", {})
            .get("spec", {})
            .get("template", {})
            .get("metadata", {})
            .get("labels", {})
        )
    return (
        res.get("spec", {})
        .get("template", {})
        .get("metadata", {})
        .get("labels", {})
    )


def _labels_match(selector: dict, labels: dict) -> bool:
    """Check if all selector key-value pairs are present in labels."""
    if not selector:
        return False
    return all(labels.get(k) == v for k, v in selector.items())


def _get_container_ports(res: dict) -> set[int]:
    """Collect all declared containerPort values from a workload resource."""
    pod_spec = _get_pod_spec(res) or {}
    ports: set[int] = set()
    for container in pod_spec.get("containers", []):
        for p in container.get("ports", []):
            cp = p.get("containerPort")
            if isinstance(cp, int):
                ports.add(cp)
    return ports


def _get_env_refs(res: dict) -> tuple[set[str], set[str]]:
    """Collect Secret and ConfigMap names referenced via env valueFrom.

    Returns:
        (secret_names, configmap_names) referenced by this resource.
    """
    pod_spec = _get_pod_spec(res) or {}
    secret_refs: set[str] = set()
    cm_refs: set[str] = set()
    for container in pod_spec.get("containers", []):
        for env_var in container.get("env", []):
            vf = env_var.get("valueFrom", {})
            skr = vf.get("secretKeyRef", {})
            if skr and skr.get("name"):
                secret_refs.add(skr["name"])
            cmkr = vf.get("configMapKeyRef", {})
            if cmkr and cmkr.get("name"):
                cm_refs.add(cmkr["name"])
        # Also check envFrom
        for ef in container.get("envFrom", []):
            sr = ef.get("secretRef", {})
            if sr and sr.get("name"):
                secret_refs.add(sr["name"])
            cmr = ef.get("configMapRef", {})
            if cmr and cmr.get("name"):
                cm_refs.add(cmr["name"])
    return secret_refs, cm_refs


def _get_pvc_refs(res: dict) -> set[str]:
    """Collect PVC claimNames referenced in pod spec volumes."""
    pod_spec = _get_pod_spec(res) or {}
    pvcs: set[str] = set()
    for vol in pod_spec.get("volumes", []):
        pvc = vol.get("persistentVolumeClaim", {})
        claim = pvc.get("claimName")
        if claim:
            pvcs.add(claim)
    return pvcs


def _validate_cross_resource(
    all_resources: list[tuple[str, dict]],
    issues: list[dict],
) -> None:
    """Layer 2: Validate consistency across all resources.

    Builds lookup indexes from all parsed resources, then runs cross-checks.
    """
    # ── Build indexes ──────────────────────────────────────────────
    # Services by name → (rel_path, resource)
    services: dict[str, tuple[str, dict]] = {}
    # Workloads (Deployment/StatefulSet/DaemonSet) by (kind, name) → (rel_path, resource)
    workloads: dict[tuple[str, str], tuple[str, dict]] = {}
    # Secrets by name
    secret_names: set[str] = set()
    # ConfigMaps by name
    configmap_names: set[str] = set()
    # ServiceAccounts by name
    sa_names: set[str] = set()
    # PVCs by name → resource
    pvcs: dict[str, dict] = {}
    # Namespace resources by name
    namespace_resources: set[str] = set()
    # All resource namespaces (for consistency check)
    resource_namespaces: set[str] = set()
    # Ingresses
    ingresses: list[tuple[str, dict]] = []
    # HPAs
    hpas: list[tuple[str, dict]] = []
    # StatefulSets
    statefulsets: list[tuple[str, dict]] = []

    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        name = res.get("metadata", {}).get("name", "")
        ns = res.get("metadata", {}).get("namespace", "")

        if ns:
            resource_namespaces.add(ns)

        if kind == "Service" and name:
            services[name] = (rel_path, res)
        if kind in _WORKLOAD_KINDS and name:
            workloads[(kind, name)] = (rel_path, res)
        if kind == "Secret" and name:
            secret_names.add(name)
        if kind == "ConfigMap" and name:
            configmap_names.add(name)
        if kind == "ServiceAccount" and name:
            sa_names.add(name)
        if kind == "PersistentVolumeClaim" and name:
            pvcs[name] = res
        if kind == "Namespace" and name:
            namespace_resources.add(name)
        if kind == "Ingress":
            ingresses.append((rel_path, res))
        if kind == "HorizontalPodAutoscaler":
            hpas.append((rel_path, res))
        if kind == "StatefulSet":
            statefulsets.append((rel_path, res))

    # Collect all pod label sets from workloads (for Service selector matching)
    workload_pod_labels: list[tuple[str, str, dict]] = []  # (kind, name, labels)
    for (kind, name), (_, res) in workloads.items():
        labels = _get_pod_labels(res)
        if labels:
            workload_pod_labels.append((kind, name, labels))

    # ── Cross-checks ──────────────────────────────────────────────

    # 1. Service → Deployment selector alignment
    for svc_name, (svc_path, svc_res) in services.items():
        selector = svc_res.get("spec", {}).get("selector", {})
        if not selector:
            continue  # headless or ExternalName — already warned in Layer 1
        matched = any(
            _labels_match(selector, labels)
            for _, _, labels in workload_pod_labels
        )
        if not matched:
            issues.append({
                "file": svc_path,
                "severity": "warning",
                "message": f"Service/{svc_name}: selector {selector} routes to nothing (no matching workload pod labels)",
            })

    # 2. Ingress → Service backend existence + port match
    for ing_path, ing_res in ingresses:
        ing_name = ing_res.get("metadata", {}).get("name", "?")
        for rule in ing_res.get("spec", {}).get("rules", []):
            for p in rule.get("http", {}).get("paths", []):
                backend = p.get("backend", {})
                svc_ref = backend.get("service", {})
                svc_ref_name = svc_ref.get("name", "")
                if not svc_ref_name:
                    continue
                if svc_ref_name not in services:
                    issues.append({
                        "file": ing_path,
                        "severity": "warning",
                        "message": f"Ingress/{ing_name}: backend service '{svc_ref_name}' not found in manifests",
                    })
                else:
                    # Check port match
                    port_ref = svc_ref.get("port", {})
                    port_num = port_ref.get("number")
                    port_name = port_ref.get("name")
                    _, svc_res = services[svc_ref_name]
                    svc_ports = svc_res.get("spec", {}).get("ports", [])
                    if port_num is not None:
                        port_found = any(
                            sp.get("port") == port_num for sp in svc_ports
                        )
                        if not port_found:
                            issues.append({
                                "file": ing_path,
                                "severity": "warning",
                                "message": f"Ingress/{ing_name}: port {port_num} mismatch — Service/{svc_ref_name} has no port {port_num}",
                            })
                    elif port_name is not None:
                        name_found = any(
                            sp.get("name") == port_name for sp in svc_ports
                        )
                        if not name_found:
                            issues.append({
                                "file": ing_path,
                                "severity": "warning",
                                "message": f"Ingress/{ing_name}: port name '{port_name}' mismatch — Service/{svc_ref_name} has no port named '{port_name}'",
                            })

    # 3. HPA → target reference + DaemonSet conflict
    for hpa_path, hpa_res in hpas:
        hpa_name = hpa_res.get("metadata", {}).get("name", "?")
        target = hpa_res.get("spec", {}).get("scaleTargetRef", {})
        target_kind = target.get("kind", "")
        target_name = target.get("name", "")
        if target_kind and target_name:
            if target_kind == "DaemonSet":
                # DaemonSet + HPA is always invalid
                issues.append({
                    "file": hpa_path,
                    "severity": "error",
                    "message": f"HPA/{hpa_name}: targets DaemonSet/{target_name} — DaemonSet cannot be autoscaled",
                })
            elif (target_kind, target_name) not in workloads:
                issues.append({
                    "file": hpa_path,
                    "severity": "warning",
                    "message": f"HPA/{hpa_name}: target {target_kind}/{target_name} not found in manifests",
                })

    # 4. Env var → Secret/ConfigMap existence
    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        name = res.get("metadata", {}).get("name", "?")
        if kind not in ("Pod", "Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"):
            continue
        sec_refs, cm_refs = _get_env_refs(res)
        for sr in sec_refs:
            if sr not in secret_names:
                issues.append({
                    "file": rel_path,
                    "severity": "warning",
                    "message": f"{kind}/{name}: Secret '{sr}' not defined in manifests",
                })
        for cr in cm_refs:
            if cr not in configmap_names:
                issues.append({
                    "file": rel_path,
                    "severity": "warning",
                    "message": f"{kind}/{name}: ConfigMap '{cr}' not defined in manifests",
                })

    # 5. containerPort ↔ Service targetPort
    for svc_name, (svc_path, svc_res) in services.items():
        selector = svc_res.get("spec", {}).get("selector", {})
        if not selector:
            continue
        # Find matching workload
        for (wk_kind, wk_name), (_, wk_res) in workloads.items():
            wk_labels = _get_pod_labels(wk_res)
            if not _labels_match(selector, wk_labels):
                continue
            # Found the target workload — check ports
            container_ports = _get_container_ports(wk_res)
            if not container_ports:
                continue  # no ports declared (not all containers declare ports)
            for sp in svc_res.get("spec", {}).get("ports", []):
                tp = sp.get("targetPort")
                if isinstance(tp, int) and tp not in container_ports:
                    issues.append({
                        "file": svc_path,
                        "severity": "warning",
                        "message": f"Service/{svc_name}: targetPort {tp} port mismatch — {wk_kind}/{wk_name} declares ports {sorted(container_ports)}",
                    })

    # 6. StatefulSet ↔ headless Service
    for sts_path, sts_res in statefulsets:
        sts_name = sts_res.get("metadata", {}).get("name", "?")
        svc_ref = sts_res.get("spec", {}).get("serviceName", "")
        if not svc_ref:
            continue  # already caught by Layer 1
        if svc_ref in services:
            _, svc_res = services[svc_ref]
            cluster_ip = svc_res.get("spec", {}).get("clusterIP")
            if cluster_ip != "None":
                issues.append({
                    "file": sts_path,
                    "severity": "error",
                    "message": f"StatefulSet/{sts_name}: serviceName '{svc_ref}' is not a headless Service (needs clusterIP: None)",
                })

    # 7. ServiceAccount references
    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        name = res.get("metadata", {}).get("name", "?")
        if kind not in ("Pod", "Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"):
            continue
        pod_spec = _get_pod_spec(res) or {}
        sa = pod_spec.get("serviceAccountName")
        if sa and sa != "default" and sa not in sa_names:
            issues.append({
                "file": rel_path,
                "severity": "info",
                "message": f"{kind}/{name}: ServiceAccount '{sa}' not defined in manifests (may exist on cluster)",
            })

    # 8. Namespace consistency
    if len(resource_namespaces) > 1:
        # Multiple namespaces — is this intentional?
        if not namespace_resources:
            # No explicit Namespace resources defined → probably unintentional
            issues.append({
                "file": "(cross-resource)",
                "severity": "warning",
                "message": f"mixed namespaces {sorted(resource_namespaces)} without explicit Namespace resources",
            })

    # 9. Label orphans — Deployment/StatefulSet labels not selected by any Service
    # Collect all Service selectors
    all_svc_selectors = [
        svc_res.get("spec", {}).get("selector", {})
        for _, (_, svc_res) in services.items()
    ]
    all_svc_selectors = [s for s in all_svc_selectors if s]

    for (wk_kind, wk_name), (wk_path, wk_res) in workloads.items():
        if wk_kind not in ("Deployment", "StatefulSet"):
            continue
        pod_labels = _get_pod_labels(wk_res)
        if not pod_labels:
            continue
        selected = any(
            _labels_match(sel, pod_labels) for sel in all_svc_selectors
        )
        if not selected:
            issues.append({
                "file": wk_path,
                "severity": "info",
                "message": f"{wk_kind}/{wk_name}: pod labels not selected by any Service (pods may be unreachable via no Service)",
            })

    # 10. PVC references + RWO access mode vs replicas
    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        name = res.get("metadata", {}).get("name", "?")
        if kind not in ("Pod", "Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"):
            continue
        pvc_refs = _get_pvc_refs(res)
        replicas = res.get("spec", {}).get("replicas", 1)
        for claim in pvc_refs:
            if claim not in pvcs:
                issues.append({
                    "file": rel_path,
                    "severity": "warning",
                    "message": f"{kind}/{name}: PVC '{claim}' not defined in manifests",
                })
            else:
                # Check RWO + multi-replica
                pvc_res = pvcs[claim]
                access_modes = pvc_res.get("spec", {}).get("accessModes", [])
                if (
                    "ReadWriteOnce" in access_modes
                    and kind == "Deployment"
                    and isinstance(replicas, int)
                    and replicas > 1
                ):
                    issues.append({
                        "file": rel_path,
                        "severity": "error",
                        "message": f"{kind}/{name}: PVC '{claim}' is ReadWriteOnce (RWO) but Deployment has {replicas} replicas — RWO cannot be shared",
                    })


# ═══════════════════════════════════════════════════════════════════
#  Layer 3 — Environment-aware validation
# ═══════════════════════════════════════════════════════════════════

# Environment name patterns that mean "production"
_PROD_PATTERNS = {"prod", "production", "prd", "live"}
# Environment name patterns that mean "development"
_DEV_PATTERNS = {"dev", "development", "local", "sandbox"}


def _validate_env_aware(
    project_root: Path,
    status: dict,
    all_resources: list[tuple[str, dict]],
    issues: list[dict],
) -> None:
    """Layer 3: Validate environment-aware configuration.

    Uses k8s_env_namespaces() for project environments and k8s_status()
    for kustomize/helm detection data to cross-check completeness.
    """
    import yaml

    # Get environment data
    try:
        env_data = k8s_env_namespaces(project_root)
    except Exception:
        return  # no project.yml or environments → skip Layer 3

    envs = env_data.get("environments", [])
    if not envs:
        return

    env_names = {e["name"] for e in envs}
    env_namespaces = {e["name"]: e.get("namespace", "") for e in envs}

    # Get deployment strategy info from status
    kustomize = status.get("kustomize", {})
    helm_charts = status.get("helm_charts", [])
    has_kustomize = kustomize.get("exists", False)
    has_helm = len(helm_charts) > 0

    # 1. Environment completeness — overlay coverage
    if has_kustomize:
        kustomize_overlays = set(kustomize.get("overlays", []))
        for env_name in env_names:
            if env_name not in kustomize_overlays:
                # Also check if an overlay exists on disk directly
                overlay_found = False
                for overlay_dir_name in ("overlays", "envs"):
                    for k8s_dir in ("k8s", "kubernetes", "deploy"):
                        overlay_path = project_root / k8s_dir / overlay_dir_name / env_name
                        if overlay_path.is_dir():
                            overlay_found = True
                            break
                    if overlay_found:
                        break
                if not overlay_found:
                    issues.append({
                        "file": "(env-aware)",
                        "severity": "warning",
                        "message": f"environment '{env_name}': no kustomize overlay found (project declares this environment)",
                    })

    # 2. Helm values completeness
    if has_helm:
        for chart in helm_charts:
            chart_path = project_root / chart.get("path", "")
            existing_values = set(chart.get("env_values_files", []))
            for env_name in env_names:
                # Check for values-{env}.yaml or values.{env}.yaml
                patterns = [f"values-{env_name}.yaml", f"values-{env_name}.yml",
                            f"values.{env_name}.yaml", f"values.{env_name}.yml"]
                found = any(p in existing_values for p in patterns)
                if not found:
                    # Also check disk directly
                    found = any((chart_path / p).is_file() for p in patterns)
                if not found:
                    issues.append({
                        "file": chart.get("path", "(helm)"),
                        "severity": "warning",
                        "message": f"Helm chart '{chart.get('name', '?')}': no values file for env '{env_name}'",
                    })

    # 3 & 4. Kustomize overlay validity: resource refs + patch targets
    if has_kustomize:
        # Build a set of (kind, name) from all base resources in manifests
        base_resource_identities: set[tuple[str, str]] = set()
        for _, res in all_resources:
            kind = res.get("kind", "")
            name = res.get("metadata", {}).get("name", "")
            if kind and name:
                base_resource_identities.add((kind, name))

        # Check each overlay
        for k8s_dir in ("k8s", "kubernetes", "deploy"):
            overlays_dir = project_root / k8s_dir / "overlays"
            if not overlays_dir.is_dir():
                continue
            for overlay_entry in sorted(overlays_dir.iterdir()):
                if not overlay_entry.is_dir():
                    continue
                kust_file = None
                for n in ("kustomization.yaml", "kustomization.yml", "Kustomization"):
                    kf = overlay_entry / n
                    if kf.is_file():
                        kust_file = kf
                        break
                if kust_file is None:
                    continue

                try:
                    kust_data = yaml.safe_load(kust_file.read_text(encoding="utf-8", errors="ignore"))
                except Exception:
                    continue
                if not isinstance(kust_data, dict):
                    continue

                overlay_name = overlay_entry.name

                # Check resource references (skip directory refs like "../../base")
                for res_ref in kust_data.get("resources", []):
                    if not isinstance(res_ref, str):
                        continue
                    ref_path = overlay_entry / res_ref
                    # Only check file references, not directory references
                    if not ref_path.exists() and not (overlay_entry / res_ref).is_dir():
                        issues.append({
                            "file": f"{k8s_dir}/overlays/{overlay_name}/kustomization.yaml",
                            "severity": "error",
                            "message": f"overlay '{overlay_name}': resource '{res_ref}' not found on disk",
                        })

                # Check patch targets against base resources
                for patch in kust_data.get("patches", []):
                    if not isinstance(patch, dict):
                        continue
                    target = patch.get("target", {})
                    if not isinstance(target, dict):
                        continue
                    target_kind = target.get("kind", "")
                    target_name = target.get("name", "")
                    if target_kind and target_name:
                        if (target_kind, target_name) not in base_resource_identities:
                            issues.append({
                                "file": f"{k8s_dir}/overlays/{overlay_name}/kustomization.yaml",
                                "severity": "error",
                                "message": f"overlay '{overlay_name}': patch targets {target_kind}/{target_name} not found in base resources",
                            })

    # 5 & 6. Prod replica sanity + dev oversizing
    # Check if any HPA exists (for prod check)
    has_hpa = any(
        res.get("kind") == "HorizontalPodAutoscaler"
        for _, res in all_resources
    )

    for _, res in all_resources:
        kind = res.get("kind", "")
        if kind != "Deployment":
            continue
        name = res.get("metadata", {}).get("name", "?")
        namespace = res.get("metadata", {}).get("namespace", "")
        replicas = res.get("spec", {}).get("replicas", 1)

        if not isinstance(replicas, int):
            continue

        # Determine which environment this resource belongs to
        for env in envs:
            env_name = env["name"]
            env_ns = env.get("namespace", "")

            # Match by namespace or by overlay convention
            is_this_env = (
                (namespace and env_ns and namespace == env_ns)
                or (namespace and env_name in namespace.lower())
            )

            if is_this_env:
                # Prod: single replica without HPA
                if env_name.lower() in _PROD_PATTERNS and replicas == 1 and not has_hpa:
                    issues.append({
                        "file": "(env-aware)",
                        "severity": "warning",
                        "message": f"Deployment/{name}: single replica in prod environment '{env_name}' with no HPA",
                    })

                # Dev: high replica count
                if env_name.lower() in _DEV_PATTERNS and replicas > 3:
                    issues.append({
                        "file": "(env-aware)",
                        "severity": "info",
                        "message": f"Deployment/{name}: {replicas} replicas in dev environment '{env_name}' (consider reducing for dev)",
                    })

    # 7. Namespace alignment — overlay namespace vs project convention
    if has_kustomize:
        for k8s_dir in ("k8s", "kubernetes", "deploy"):
            overlays_dir = project_root / k8s_dir / "overlays"
            if not overlays_dir.is_dir():
                continue
            for overlay_entry in sorted(overlays_dir.iterdir()):
                if not overlay_entry.is_dir():
                    continue
                overlay_name = overlay_entry.name
                if overlay_name not in env_names:
                    continue

                kust_file = None
                for n in ("kustomization.yaml", "kustomization.yml", "Kustomization"):
                    kf = overlay_entry / n
                    if kf.is_file():
                        kust_file = kf
                        break
                if kust_file is None:
                    continue

                try:
                    kust_data = yaml.safe_load(kust_file.read_text(encoding="utf-8", errors="ignore"))
                except Exception:
                    continue
                if not isinstance(kust_data, dict):
                    continue

                overlay_ns = kust_data.get("namespace", "")
                expected_ns = env_namespaces.get(overlay_name, "")
                if overlay_ns and expected_ns and overlay_ns != expected_ns:
                    issues.append({
                        "file": f"{k8s_dir}/overlays/{overlay_name}/kustomization.yaml",
                        "severity": "warning",
                        "message": f"overlay '{overlay_name}': namespace mismatch — overlay sets '{overlay_ns}' but project convention expects '{expected_ns}'",
                    })


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
        from src.core.services.k8s_common import _run_kubectl
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


# ═══════════════════════════════════════════════════════════════════
#  Layer 5 — Security & production readiness
# ═══════════════════════════════════════════════════════════════════

# Kinds that have pod templates
_WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"}


def _validate_security(
    all_resources: list[tuple[str, dict]],
    issues: list[dict],
) -> None:
    """Layer 5: Security posture and production readiness checks.

    Covers container security, operational safety, and RBAC.
    """
    # Build indexes for cross-resource operational checks
    deployment_labels: dict[str, dict[str, str]] = {}  # name → matchLabels
    deployment_replicas: dict[str, int] = {}  # name → replicas
    deployment_namespaces: set[str] = set()  # namespaces with workloads
    has_pdb = False
    network_policy_namespaces: set[str] = set()

    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        name = res.get("metadata", {}).get("name", "?")
        namespace = res.get("metadata", {}).get("namespace", "")

        if kind == "PodDisruptionBudget":
            has_pdb = True

        if kind == "NetworkPolicy":
            np_ns = namespace or "default"
            network_policy_namespaces.add(np_ns)

        if kind in _WORKLOAD_KINDS:
            deploy_ns = namespace or "default"
            deployment_namespaces.add(deploy_ns)

        if kind == "Deployment":
            replicas = res.get("spec", {}).get("replicas", 1)
            if isinstance(replicas, int):
                deployment_replicas[name] = replicas
            match_labels = res.get("spec", {}).get("selector", {}).get("matchLabels", {})
            deployment_labels[name] = match_labels

    # ── Per-resource checks ───────────────────────────────────────

    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        name = res.get("metadata", {}).get("name", "?")

        # Get pod spec for workload kinds
        if kind == "Pod":
            pod_spec = res.get("spec", {})
        elif kind in _WORKLOAD_KINDS:
            if kind == "CronJob":
                pod_spec = res.get("spec", {}).get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec", {})
            else:
                pod_spec = res.get("spec", {}).get("template", {}).get("spec", {})
        else:
            pod_spec = None

        if pod_spec and isinstance(pod_spec, dict):
            _check_pod_security(kind, name, rel_path, pod_spec, issues)
            _check_pod_operational(kind, name, rel_path, pod_spec, issues)

        # RBAC checks
        if kind in ("ClusterRole", "Role"):
            _check_rbac_role(kind, name, rel_path, res, issues)
        if kind in ("ClusterRoleBinding", "RoleBinding"):
            _check_rbac_binding(kind, name, rel_path, res, issues)

    # ── Cross-resource operational checks ─────────────────────────

    # No PDB for HA deployments
    if not has_pdb:
        for dep_name, replicas in deployment_replicas.items():
            if replicas >= 2:
                issues.append({
                    "file": "(security)",
                    "severity": "info",
                    "message": f"Deployment/{dep_name}: {replicas} replicas but no PodDisruptionBudget defined",
                })

    # No NetworkPolicy for namespaces with workloads
    for ns in deployment_namespaces:
        if ns not in network_policy_namespaces:
            issues.append({
                "file": "(security)",
                "severity": "info",
                "message": f"namespace '{ns}': workloads present but no NetworkPolicy (no network isolation)",
            })

    # imagePullPolicy: Never on cloud cluster
    try:
        cluster = cluster_status()
    except Exception:
        cluster = {}
    if cluster.get("connected"):
        cluster_type = cluster.get("cluster_type", {}).get("type", "unknown")
        if cluster_type not in _LOCAL_CLUSTER_TYPES:
            for rel_path, res in all_resources:
                kind = res.get("kind", "")
                name = res.get("metadata", {}).get("name", "?")
                if kind == "Pod":
                    pod_spec = res.get("spec", {})
                elif kind in _WORKLOAD_KINDS:
                    if kind == "CronJob":
                        pod_spec = res.get("spec", {}).get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec", {})
                    else:
                        pod_spec = res.get("spec", {}).get("template", {}).get("spec", {})
                else:
                    continue
                if not pod_spec:
                    continue
                for container in pod_spec.get("containers", []):
                    c_name = container.get("name", "unnamed")
                    pull_policy = container.get("imagePullPolicy", "")
                    if pull_policy == "Never":
                        issues.append({
                            "file": rel_path,
                            "severity": "warning",
                            "message": f"{kind}/{name}/{c_name}: imagePullPolicy is Never on cloud cluster ({cluster_type}) — image won't be pulled from registry",
                        })


def _check_pod_security(
    kind: str, name: str, path: str,
    pod_spec: dict, issues: list[dict],
) -> None:
    """Container-level security checks within a pod spec."""
    # Pod-level host namespace checks
    if pod_spec.get("hostNetwork") is True:
        issues.append({
            "file": path,
            "severity": "warning",
            "message": f"{kind}/{name}: uses host network namespace",
        })
    if pod_spec.get("hostPID") is True:
        issues.append({
            "file": path,
            "severity": "warning",
            "message": f"{kind}/{name}: uses host PID namespace",
        })
    if pod_spec.get("hostIPC") is True:
        issues.append({
            "file": path,
            "severity": "warning",
            "message": f"{kind}/{name}: uses host IPC namespace",
        })

    # Container-level security checks
    for container in pod_spec.get("containers", []):
        c_name = container.get("name", "unnamed")
        sc = container.get("securityContext", {}) or {}

        # runAsUser: 0 (runs as root)
        if sc.get("runAsUser") == 0:
            issues.append({
                "file": path,
                "severity": "warning",
                "message": f"{kind}/{name}/{c_name}: runAsUser is 0 (runs as root)",
            })

        # privileged: true
        if sc.get("privileged") is True:
            issues.append({
                "file": path,
                "severity": "error",
                "message": f"{kind}/{name}/{c_name}: privileged container",
            })

        # allowPrivilegeEscalation: true or missing
        ape = sc.get("allowPrivilegeEscalation")
        if ape is True:
            issues.append({
                "file": path,
                "severity": "warning",
                "message": f"{kind}/{name}/{c_name}: privilege escalation allowed (allowPrivilegeEscalation: true)",
            })

        # capabilities.drop: ["ALL"] missing
        caps = sc.get("capabilities", {}) or {}
        drop_list = caps.get("drop", [])
        has_drop_all = any(
            str(d).upper() == "ALL" for d in (drop_list if isinstance(drop_list, list) else [])
        )
        if not has_drop_all:
            issues.append({
                "file": path,
                "severity": "info",
                "message": f"{kind}/{name}/{c_name}: capabilities not explicitly dropped (missing capabilities.drop: ['ALL'])",
            })

        # readOnlyRootFilesystem missing or false
        if not sc.get("readOnlyRootFilesystem"):
            issues.append({
                "file": path,
                "severity": "info",
                "message": f"{kind}/{name}/{c_name}: writable root filesystem (readOnlyRootFilesystem not set to true)",
            })


def _check_pod_operational(
    kind: str, name: str, path: str,
    pod_spec: dict, issues: list[dict],
) -> None:
    """Operational safety checks within a pod spec."""
    # automountServiceAccountToken not explicitly false
    if pod_spec.get("automountServiceAccountToken") is not False:
        issues.append({
            "file": path,
            "severity": "info",
            "message": f"{kind}/{name}: automountServiceAccountToken not explicitly disabled (service account token auto-mounted)",
        })

    # Identical liveness and readiness probes
    for container in pod_spec.get("containers", []):
        c_name = container.get("name", "unnamed")
        liveness = container.get("livenessProbe")
        readiness = container.get("readinessProbe")
        if liveness and readiness and liveness == readiness:
            issues.append({
                "file": path,
                "severity": "warning",
                "message": f"{kind}/{name}/{c_name}: identical liveness and readiness probes — may cause restart loops under load",
            })


def _check_rbac_role(
    kind: str, name: str, path: str,
    res: dict, issues: list[dict],
) -> None:
    """RBAC role checks for ClusterRole/Role."""
    rules = res.get("rules", [])
    if not isinstance(rules, list):
        return

    for rule in rules:
        if not isinstance(rule, dict):
            continue

        # Wildcard verbs
        verbs = rule.get("verbs", [])
        if isinstance(verbs, list) and "*" in verbs:
            issues.append({
                "file": path,
                "severity": "warning",
                "message": f"{kind}/{name}: wildcard verb ['*'] — overly broad permissions",
            })

        # Wildcard resources
        resources = rule.get("resources", [])
        if isinstance(resources, list) and "*" in resources:
            issues.append({
                "file": path,
                "severity": "warning",
                "message": f"{kind}/{name}: wildcard resource ['*'] — overly broad permissions",
            })


def _check_rbac_binding(
    kind: str, name: str, path: str,
    res: dict, issues: list[dict],
) -> None:
    """RBAC binding checks for ClusterRoleBinding/RoleBinding."""
    subjects = res.get("subjects", [])
    if not isinstance(subjects, list):
        return

    for subj in subjects:
        if not isinstance(subj, dict):
            continue
        if subj.get("kind") == "ServiceAccount" and subj.get("name") == "default":
            issues.append({
                "file": path,
                "severity": "warning",
                "message": f"{kind}/{name}: binds to default ServiceAccount — should not have cluster-wide permissions",
            })


# ═══════════════════════════════════════════════════════════════════
#  Layer 6 — Cross-domain validation (THE DIFFERENTIATOR)
# ═══════════════════════════════════════════════════════════════════

# Private registries — images with a hostname containing a dot
# (e.g. 123456789.dkr.ecr.us-east-1.amazonaws.com/myapp:v1,
#  ghcr.io/owner/image:tag, gcr.io/project/image:tag)
# Docker Hub official images (e.g. nginx:latest, python:3.12) have
# no dot in the first path segment.
_PRIVATE_REGISTRY_RE = re.compile(r"^[a-zA-Z0-9._-]+\.[a-zA-Z0-9._-]+/")


def _validate_cross_domain(
    project_root: Path,
    all_resources: list[tuple[str, dict]],
    issues: list[dict],
) -> None:
    """Layer 6: validate seams between Docker, K8s, Terraform, CI/CD, Environments."""

    # ── Gather detection data from each domain ──────────────────
    try:
        docker = docker_status(project_root)
    except Exception:
        docker = {"has_dockerfile": False, "has_compose": False}

    try:
        ci_st = ci_status(project_root)
    except Exception:
        ci_st = {"has_ci": False}

    try:
        ci_wf = ci_workflows(project_root)
    except Exception:
        ci_wf = {"workflows": []}

    try:
        tf = terraform_status(project_root)
    except Exception:
        tf = {"has_terraform": False}

    # ── Build K8s resource indexes ──────────────────────────────
    k8s_deployment_names: set[str] = set()  # Deployment/StatefulSet/DaemonSet names
    k8s_service_names: set[str] = set()     # Service names
    k8s_pvc_names: set[str] = set()         # PersistentVolumeClaim names
    k8s_images: dict[str, list[dict]] = {}  # image → [{kind, name, path, pod_spec}]

    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        name = res.get("metadata", {}).get("name", "")

        if kind in ("Deployment", "StatefulSet", "DaemonSet"):
            k8s_deployment_names.add(name)
        if kind == "Service":
            k8s_service_names.add(name)
        if kind == "PersistentVolumeClaim":
            k8s_pvc_names.add(name)

        # Extract images and pod specs from workloads
        pod_spec = _extract_pod_spec(res)
        if pod_spec:
            containers = pod_spec.get("containers", [])
            if isinstance(containers, list):
                for c in containers:
                    img = c.get("image", "")
                    if img:
                        k8s_images.setdefault(img, []).append({
                            "kind": kind,
                            "name": name,
                            "path": rel_path,
                            "pod_spec": pod_spec,
                            "container": c,
                        })

    # ── Docker ↔ K8s seam ──────────────────────────────────────
    _cross_docker_k8s(
        docker, all_resources, k8s_deployment_names, k8s_service_names,
        k8s_pvc_names, k8s_images, issues,
    )

    # ── Docker ↔ CI/CD seam ────────────────────────────────────
    _cross_docker_ci(docker, ci_st, ci_wf, issues)

    # ── Docker ↔ Terraform seam ────────────────────────────────
    _cross_docker_terraform(docker, tf, k8s_images, issues)

    # ── Docker ↔ Environments seam ─────────────────────────────
    _cross_docker_envs(project_root, docker, issues)

    # ── Terraform ↔ K8s seam ──────────────────────────────────
    _cross_terraform_k8s(tf, all_resources, issues)

    # ── Terraform ↔ CI/CD seam ────────────────────────────────
    _cross_terraform_ci(tf, ci_st, ci_wf, issues)

    # ── Terraform ↔ Environments seam ─────────────────────────
    _cross_terraform_envs(project_root, tf, issues)

    # ── CI/CD ↔ K8s seam ──────────────────────────────────────
    _cross_ci_k8s(project_root, docker, ci_st, ci_wf, all_resources, issues)

    # ── CI/CD ↔ Environments seam ─────────────────────────────
    _cross_ci_envs(project_root, ci_st, ci_wf, all_resources, issues)

    # ── Cross-cutting intelligence ────────────────────────────
    _cross_cutting(project_root, docker, ci_st, ci_wf, tf, all_resources, issues)


def _extract_pod_spec(res: dict) -> dict | None:
    """Extract the pod spec from a workload resource."""
    kind = res.get("kind", "")
    spec = res.get("spec", {})
    if kind == "Pod":
        return spec
    if kind in ("Deployment", "StatefulSet", "DaemonSet", "ReplicaSet"):
        return spec.get("template", {}).get("spec", {})
    if kind == "Job":
        return spec.get("template", {}).get("spec", {})
    if kind == "CronJob":
        return spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec", {})
    return None


def _cross_docker_k8s(
    docker: dict,
    all_resources: list[tuple[str, dict]],
    k8s_deploy_names: set[str],
    k8s_svc_names: set[str],
    k8s_pvc_names: set[str],
    k8s_images: dict[str, list[dict]],
    issues: list[dict],
) -> None:
    """Docker ↔ K8s cross-domain checks (9 checks)."""
    compose_details = docker.get("compose_service_details", [])
    dockerfile_details = docker.get("dockerfile_details", [])

    if not compose_details and not dockerfile_details:
        return  # No Docker data — nothing to cross-validate

    # Build a mapping of compose service name → details
    compose_by_name: dict[str, dict] = {}
    for svc in compose_details:
        if isinstance(svc, dict) and svc.get("name"):
            compose_by_name[svc["name"]] = svc

    # Collect all Dockerfile EXPOSE ports
    dockerfile_ports: set[int] = set()
    for df in dockerfile_details:
        if isinstance(df, dict):
            for p in df.get("ports", []):
                if isinstance(p, int):
                    dockerfile_ports.add(p)

    # Collect all compose container ports
    compose_ports: set[int] = set()
    for svc in compose_details:
        for port_entry in svc.get("ports", []):
            if isinstance(port_entry, dict) and "container" in port_entry:
                compose_ports.add(port_entry["container"])

    # All Docker ports (union of Dockerfile EXPOSE and compose container ports)
    all_docker_ports = dockerfile_ports | compose_ports

    # Set of locally-built images (compose services with build context)
    locally_built_images: set[str] = set()
    for svc in compose_details:
        if svc.get("build") and svc.get("image"):
            locally_built_images.add(svc["image"])

    # ── Check 1: Image name alignment ───────────────────────────
    for svc in compose_details:
        compose_img = svc.get("image")
        svc_name = svc.get("name", "?")
        if not compose_img:
            continue

        # Find matching K8s deployment by service name
        for rel_path, res in all_resources:
            kind = res.get("kind", "")
            k8s_name = res.get("metadata", {}).get("name", "")
            if kind not in ("Deployment", "StatefulSet", "DaemonSet"):
                continue
            if k8s_name != svc_name:
                continue

            pod_spec = _extract_pod_spec(res)
            if not pod_spec:
                continue
            for c in pod_spec.get("containers", []):
                k8s_img = c.get("image", "")
                if not k8s_img:
                    continue
                # Compare: strip tag for base comparison
                compose_base = compose_img.rsplit(":", 1)[0]
                k8s_base = k8s_img.rsplit(":", 1)[0]
                if compose_base != k8s_base:
                    issues.append({
                        "file": rel_path,
                        "severity": "warning",
                        "message": (
                            f"Docker↔K8s: compose service '{svc_name}' image "
                            f"'{compose_img}' does not match K8s "
                            f"{kind}/{k8s_name} image '{k8s_img}'"
                        ),
                    })

    # ── Check 2: Port alignment ─────────────────────────────────
    if all_docker_ports:
        for img, refs in k8s_images.items():
            for ref in refs:
                container = ref["container"]
                k8s_ports = set()
                for p in container.get("ports", []):
                    if isinstance(p, dict) and "containerPort" in p:
                        k8s_ports.add(p["containerPort"])
                if k8s_ports:
                    mismatched = all_docker_ports - k8s_ports
                    for docker_port in mismatched:
                        # Only warn if there ARE k8s ports declared (so it's a mismatch, not just missing)
                        if k8s_ports and docker_port not in k8s_ports:
                            issues.append({
                                "file": ref["path"],
                                "severity": "warning",
                                "message": (
                                    f"Docker↔K8s: Docker exposes port {docker_port} "
                                    f"but K8s {ref['kind']}/{ref['name']} containerPort "
                                    f"is {sorted(k8s_ports)}"
                                ),
                            })

    # ── Check 3: Environment variable coverage ──────────────────
    for svc in compose_details:
        svc_name = svc.get("name", "?")
        compose_env = svc.get("environment", {})
        if not compose_env:
            continue

        # Find matching K8s workload
        for rel_path, res in all_resources:
            kind = res.get("kind", "")
            k8s_name = res.get("metadata", {}).get("name", "")
            if kind not in ("Deployment", "StatefulSet", "DaemonSet"):
                continue
            if k8s_name != svc_name:
                continue

            pod_spec = _extract_pod_spec(res)
            if not pod_spec:
                continue

            # Collect all env var names from all containers
            k8s_env_names: set[str] = set()
            for c in pod_spec.get("containers", []):
                for e in c.get("env", []):
                    if isinstance(e, dict):
                        k8s_env_names.add(e.get("name", ""))
                # Also check envFrom (ConfigMap/Secret refs cover all keys)
                for ef in c.get("envFrom", []):
                    if isinstance(ef, dict):
                        # If envFrom is used, we can't know exact keys, so skip
                        k8s_env_names.add("__envFrom__")

            if "__envFrom__" in k8s_env_names:
                continue  # envFrom covers unknown keys, skip

            for var_name in compose_env:
                if var_name not in k8s_env_names:
                    issues.append({
                        "file": rel_path,
                        "severity": "info",
                        "message": (
                            f"Docker↔K8s: compose '{svc_name}' env var "
                            f"'{var_name}' has no K8s equivalent in "
                            f"{kind}/{k8s_name}"
                        ),
                    })

    # ── Check 4: Volume pattern translation ─────────────────────
    for svc in compose_details:
        svc_name = svc.get("name", "?")
        volumes = svc.get("volumes", [])
        for vol_str in volumes:
            if not isinstance(vol_str, str):
                continue
            # Named volumes: "volname:/path" (no leading /. or ~/)
            parts = vol_str.split(":")
            if len(parts) >= 2:
                vol_name = parts[0]
                # Skip bind mounts (start with /, ./, ~/)
                if vol_name.startswith(("/", ".", "~")):
                    continue
                # This is a named volume — check for corresponding PVC
                if vol_name not in k8s_pvc_names:
                    issues.append({
                        "file": "cross-domain",
                        "severity": "info",
                        "message": (
                            f"Docker↔K8s: compose '{svc_name}' volume "
                            f"'{vol_name}' has no K8s PVC equivalent"
                        ),
                    })

    # ── Check 5: Service parity ─────────────────────────────────
    for svc in compose_details:
        svc_name = svc.get("name", "?")
        if svc_name not in k8s_deploy_names:
            issues.append({
                "file": "cross-domain",
                "severity": "info",
                "message": (
                    f"Docker↔K8s: compose service '{svc_name}' "
                    f"has no K8s equivalent (Deployment/StatefulSet/DaemonSet)"
                ),
            })

    # ── Check 6: Health check alignment ─────────────────────────
    for svc in compose_details:
        svc_name = svc.get("name", "?")
        hc = svc.get("healthcheck")
        if not hc:
            continue

        # Find matching K8s workload
        for rel_path, res in all_resources:
            kind = res.get("kind", "")
            k8s_name = res.get("metadata", {}).get("name", "")
            if kind not in ("Deployment", "StatefulSet", "DaemonSet"):
                continue
            if k8s_name != svc_name:
                continue

            pod_spec = _extract_pod_spec(res)
            if not pod_spec:
                continue

            has_probe = False
            for c in pod_spec.get("containers", []):
                if c.get("livenessProbe") or c.get("readinessProbe"):
                    has_probe = True
                    break

            if not has_probe:
                issues.append({
                    "file": rel_path,
                    "severity": "info",
                    "message": (
                        f"Docker↔K8s: compose '{svc_name}' has healthcheck "
                        f"but K8s {kind}/{k8s_name} has no matching probe"
                    ),
                })

    # ── Check 7: Image pull policy ↔ build locality ─────────────
    # Only relevant on cloud clusters
    try:
        cluster = cluster_status()
    except Exception:
        cluster = {}

    cluster_type_raw = cluster.get("cluster_type", "")
    if isinstance(cluster_type_raw, dict):
        cluster_type = cluster_type_raw.get("type", "unknown")
    else:
        cluster_type = str(cluster_type_raw)
    is_cloud = cluster_type in ("eks", "gke", "aks", "generic-cloud")

    if is_cloud and locally_built_images:
        for img, refs in k8s_images.items():
            if img not in locally_built_images:
                continue
            for ref in refs:
                policy = ref["container"].get("imagePullPolicy", "")
                if policy == "Always":
                    issues.append({
                        "file": ref["path"],
                        "severity": "warning",
                        "message": (
                            f"Docker↔K8s: locally-built image '{img}' has "
                            f"imagePullPolicy: Always on cloud cluster — "
                            f"image won't be found on registry"
                        ),
                    })

    # ── Check 8: Image pull secret ↔ private registry ───────────
    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        name = res.get("metadata", {}).get("name", "")
        pod_spec = _extract_pod_spec(res)
        if not pod_spec:
            continue

        has_pull_secrets = bool(pod_spec.get("imagePullSecrets"))
        for c in pod_spec.get("containers", []):
            img = c.get("image", "")
            if _PRIVATE_REGISTRY_RE.match(img) and not has_pull_secrets:
                issues.append({
                    "file": rel_path,
                    "severity": "warning",
                    "message": (
                        f"Docker↔K8s: {kind}/{name} uses private registry image "
                        f"'{img}' without imagePullSecrets"
                    ),
                })

    # ── Check 9: Service name continuity ────────────────────────
    for svc in compose_details:
        svc_name = svc.get("name", "?")
        # Only check services that expose ports (networking-relevant)
        svc_ports = svc.get("ports", [])
        if not svc_ports:
            continue
        if svc_name not in k8s_svc_names:
            issues.append({
                "file": "cross-domain",
                "severity": "info",
                "message": (
                    f"Docker↔K8s: compose service '{svc_name}' "
                    f"not found as K8s Service name — inter-service DNS may differ"
                ),
            })


# ═══════════════════════════════════════════════════════════════════
#  Docker ↔ CI/CD seam (5 checks)
# ═══════════════════════════════════════════════════════════════════

# Patterns for detecting docker operations in CI steps
_DOCKER_BUILD_PATTERNS = ("docker build", "docker/build-push-action")
_DOCKER_PUSH_PATTERNS = ("docker push", "push: true", "docker/build-push-action")
_DOCKER_LOGIN_PATTERNS = ("docker/login-action", "docker login")
_DOCKER_COMPOSE_PATTERNS = ("docker compose", "docker-compose")


def _ci_step_text(step: dict) -> str:
    """Extract searchable text from a CI workflow step."""
    parts = []
    if step.get("run"):
        parts.append(str(step["run"]))
    if step.get("uses"):
        parts.append(str(step["uses"]))
    if step.get("with"):
        for v in step["with"].values():
            parts.append(str(v))
    return " ".join(parts).lower()


def _all_ci_steps(ci_wf: dict) -> list[str]:
    """Collect all step text from all workflows."""
    texts = []
    for wf in ci_wf.get("workflows", []):
        for job in wf.get("jobs", []):
            for step in job.get("steps", []):
                texts.append(_ci_step_text(step))
    return texts


def _cross_docker_ci(
    docker: dict,
    ci_st: dict,
    ci_wf: dict,
    issues: list[dict],
) -> None:
    """Docker ↔ CI/CD cross-domain checks (5 checks)."""
    if not ci_st.get("has_ci"):
        return  # No CI detected — nothing to cross-validate

    has_dockerfile = docker.get("has_dockerfile", False)
    has_compose = docker.get("has_compose", False)
    dockerfile_details = docker.get("dockerfile_details", [])

    if not has_dockerfile and not has_compose:
        return  # No Docker data

    all_steps = _all_ci_steps(ci_wf)
    all_step_text = " ".join(all_steps)

    has_docker_build = any(p in all_step_text for p in _DOCKER_BUILD_PATTERNS)
    has_docker_push = any(p in all_step_text for p in _DOCKER_PUSH_PATTERNS)
    has_docker_login = any(p in all_step_text for p in _DOCKER_LOGIN_PATTERNS)
    has_docker_compose = any(p in all_step_text for p in _DOCKER_COMPOSE_PATTERNS)
    has_target = "--target" in all_step_text

    # Check 1: Dockerfile exists but CI doesn't build
    if has_dockerfile and not has_docker_build:
        issues.append({
            "file": "cross-domain",
            "severity": "info",
            "message": "Docker↔CI: Dockerfile exists but CI does not build Docker images",
        })

    # Check 2: CI builds but doesn't push
    if has_docker_build and not has_docker_push:
        issues.append({
            "file": "cross-domain",
            "severity": "warning",
            "message": "Docker↔CI: CI builds Docker images but never pushes to a registry",
        })

    # Check 3: CI pushes without login
    if has_docker_push and not has_docker_login:
        # build-push-action with push:true might have login elsewhere
        # Only warn if there's an explicit push without a login
        issues.append({
            "file": "cross-domain",
            "severity": "warning",
            "message": "Docker↔CI: CI pushes images without registry authentication step",
        })

    # Check 4: Multi-stage Dockerfile test target unused in CI
    for df in dockerfile_details:
        stages = df.get("stages", [])
        stage_count = df.get("stage_count", 0)
        has_test_stage = any(
            s.lower() in ("test", "testing", "tests")
            for s in stages
        )
        if stage_count > 1 and has_test_stage and has_docker_build and not has_target:
            issues.append({
                "file": "cross-domain",
                "severity": "info",
                "message": (
                    f"Docker↔CI: Dockerfile has test stage (multi-stage) "
                    f"but CI doesn't use --target for containerized tests"
                ),
            })

    # Check 5: Compose available but CI doesn't use it
    if has_compose and not has_docker_compose:
        issues.append({
            "file": "cross-domain",
            "severity": "info",
            "message": "Docker↔CI: compose available but CI doesn't use it for integration testing",
        })


# ═══════════════════════════════════════════════════════════════════
#  Docker ↔ Terraform seam (2 checks)
# ═══════════════════════════════════════════════════════════════════

# Terraform resource types that provision container registries
_TF_REGISTRY_RESOURCES = {
    "aws_ecr_repository",
    "aws_ecr_public_repository",
    "google_container_registry",
    "google_artifact_registry_repository",
    "azurerm_container_registry",
}

# Mapping: Terraform provider → expected image registry pattern
_TF_PROVIDER_REGISTRY_HINTS = {
    "aws": ("ecr", "amazonaws.com"),
    "google": ("gcr.io", "artifact-registry", "pkg.dev"),
    "azurerm": ("azurecr.io",),
}


def _cross_docker_terraform(
    docker: dict,
    tf: dict,
    k8s_images: dict[str, list[dict]],
    issues: list[dict],
) -> None:
    """Docker ↔ Terraform cross-domain checks (2 checks)."""
    if not tf.get("has_terraform"):
        return
    if not docker.get("has_dockerfile", False):
        return

    tf_resources = tf.get("resources", [])
    tf_resource_types = {r.get("type", "") for r in tf_resources}

    # Find Terraform registry resources
    has_tf_registry = bool(tf_resource_types & _TF_REGISTRY_RESOURCES)

    # Check 1: Registry provisioned but images reference different registry
    if has_tf_registry and k8s_images:
        # Determine which cloud provider the registry belongs to
        tf_providers = tf.get("providers", [])
        expected_hints: list[str] = []
        for prov in tf_providers:
            prov_name = prov.split("/")[-1] if "/" in prov else prov
            hints = _TF_PROVIDER_REGISTRY_HINTS.get(prov_name, ())
            expected_hints.extend(hints)

        if expected_hints:
            for img in k8s_images:
                img_lower = img.lower()
                # Only check images that look like they come from a registry
                if _PRIVATE_REGISTRY_RE.match(img):
                    matches_expected = any(h in img_lower for h in expected_hints)
                    if not matches_expected:
                        issues.append({
                            "file": "cross-domain",
                            "severity": "warning",
                            "message": (
                                f"Docker↔Terraform: Terraform provisions registry "
                                f"(provider: {', '.join(tf_providers)}) but image "
                                f"'{img}' references a different registry"
                            ),
                        })

    # Check 2: No registry in IaC
    if not has_tf_registry:
        issues.append({
            "file": "cross-domain",
            "severity": "info",
            "message": (
                "Docker↔Terraform: Docker images built but "
                "no container registry provisioned in Terraform"
            ),
        })


# ═══════════════════════════════════════════════════════════════════
#  Docker ↔ Environments seam (2 checks)
# ═══════════════════════════════════════════════════════════════════


def _load_project_environments(project_root: Path) -> list[str]:
    """Load environment names from project.yml."""
    try:
        import yaml
        project_yml = project_root / "project.yml"
        if not project_yml.is_file():
            return []
        data = yaml.safe_load(project_yml.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return []
        envs = data.get("environments", [])
        if isinstance(envs, list):
            return [
                e.get("name", "") if isinstance(e, dict) else str(e)
                for e in envs
                if e
            ]
    except Exception:
        pass
    return []


def _cross_docker_envs(
    project_root: Path,
    docker: dict,
    issues: list[dict],
) -> None:
    """Docker ↔ Environments cross-domain checks (2 checks)."""
    if not docker.get("has_compose", False):
        return

    environments = _load_project_environments(project_root)

    # Check 1: Compose override per environment
    if len(environments) > 1:
        # Check for per-env compose overrides
        override_patterns = [
            f"docker-compose.{env}.yml" for env in environments
        ] + [
            f"docker-compose.{env}.yaml" for env in environments
        ] + [
            f"compose.{env}.yml" for env in environments
        ] + [
            f"compose.{env}.yaml" for env in environments
        ]
        has_any_override = any(
            (project_root / p).is_file() for p in override_patterns
        )
        # Also check for the standard override file
        has_override = (
            (project_root / "docker-compose.override.yml").is_file()
            or (project_root / "docker-compose.override.yaml").is_file()
            or has_any_override
        )
        if not has_override:
            issues.append({
                "file": "cross-domain",
                "severity": "info",
                "message": (
                    f"Docker↔Environments: project has {len(environments)} "
                    f"environments but no per-environment compose override files"
                ),
            })

    # Check 2: Env file reference validity
    compose_details = docker.get("compose_service_details", [])
    for svc in compose_details:
        env_files = svc.get("env_file", [])
        if isinstance(env_files, str):
            env_files = [env_files]
        if not isinstance(env_files, list):
            continue
        for ef in env_files:
            if not isinstance(ef, str):
                continue
            ef_path = project_root / ef
            if not ef_path.is_file():
                svc_name = svc.get("name", "?")
                issues.append({
                    "file": "cross-domain",
                    "severity": "warning",
                    "message": (
                        f"Docker↔Environments: compose service '{svc_name}' "
                        f"references env file '{ef}' but file not found"
                    ),
                })


# ═══════════════════════════════════════════════════════════════════
#  Terraform ↔ K8s seam (5 checks)
# ═══════════════════════════════════════════════════════════════════

# Terraform resource types that represent databases
_TF_DATABASE_RESOURCES = {
    "aws_rds_instance", "aws_rds_cluster",
    "aws_db_instance", "aws_aurora_cluster",
    "google_sql_database_instance",
    "azurerm_mysql_server", "azurerm_postgresql_server",
    "azurerm_mssql_server", "azurerm_cosmosdb_account",
}

# Terraform resource types that represent IAM roles for K8s
_TF_IAM_RESOURCES = {
    "aws_iam_role", "aws_iam_policy",
    "google_service_account", "google_project_iam_member",
    "azurerm_user_assigned_identity",
}


def _cross_terraform_k8s(
    tf: dict,
    all_resources: list[tuple[str, dict]],
    issues: list[dict],
) -> None:
    """Terraform ↔ K8s cross-domain checks (5 checks)."""
    if not tf.get("has_terraform") and not all_resources:
        return

    tf_resources = tf.get("resources", [])
    tf_resource_types = {r.get("type", "") for r in tf_resources}
    tf_providers = tf.get("providers", [])

    # Check 1: Cloud cluster without IaC (detected via cluster_status in caller)
    # This check needs cluster info — we look at whether terraform has cloud
    # provider but no cluster provisioning resources
    try:
        cluster = cluster_status()
    except Exception:
        cluster = {}

    cluster_type_raw = cluster.get("cluster_type", "")
    if isinstance(cluster_type_raw, dict):
        c_type = cluster_type_raw.get("type", "")
    else:
        c_type = str(cluster_type_raw)

    is_cloud_cluster = c_type in ("eks", "gke", "aks")
    if is_cloud_cluster and not tf.get("has_terraform"):
        issues.append({
            "file": "cross-domain",
            "severity": "info",
            "message": (
                f"Terraform↔K8s: running on cloud cluster ({c_type}) "
                f"with no infrastructure-as-code — manual provisioning detected"
            ),
        })

    if not tf.get("has_terraform"):
        return

    # Check 2: Environment alignment (delegated to Terraform ↔ Environments seam)
    # Check is handled in _cross_terraform_envs

    # Check 3: Kubernetes provider conflict
    if all_resources and any(p in ("kubernetes", "helm") for p in tf_providers):
        issues.append({
            "file": "cross-domain",
            "severity": "warning",
            "message": (
                "Terraform↔K8s: Terraform has Kubernetes provider "
                "AND raw K8s manifests — dual management risk"
            ),
        })

    # Check 4: Database connection gap
    has_db = bool(tf_resource_types & _TF_DATABASE_RESOURCES)
    has_k8s_secret = any(
        res.get("kind") == "Secret"
        for _, res in all_resources
    )
    if has_db and not has_k8s_secret:
        issues.append({
            "file": "cross-domain",
            "severity": "info",
            "message": (
                "Terraform↔K8s: Terraform provisions database resources "
                "but no K8s Secret for connection strings found"
            ),
        })

    # Check 5: IAM ↔ ServiceAccount alignment
    has_iam = bool(tf_resource_types & _TF_IAM_RESOURCES)
    has_k8s_sa = any(
        res.get("kind") == "ServiceAccount"
        for _, res in all_resources
    )
    if has_iam and not has_k8s_sa:
        issues.append({
            "file": "cross-domain",
            "severity": "info",
            "message": (
                "Terraform↔K8s: Terraform manages IAM roles but "
                "no K8s ServiceAccount found to bind them"
            ),
        })


# ═══════════════════════════════════════════════════════════════════
#  Terraform ↔ CI/CD seam (3 checks)
# ═══════════════════════════════════════════════════════════════════

_TF_CI_PATTERNS = ("terraform", "hashicorp/setup-terraform", "tofu", "opentofu")
_TF_PLAN_PATTERNS = ("terraform plan", "terraform validate")
_TF_APPLY_PATTERNS = ("terraform apply",)


def _cross_terraform_ci(
    tf: dict,
    ci_st: dict,
    ci_wf: dict,
    issues: list[dict],
) -> None:
    """Terraform ↔ CI/CD cross-domain checks (3 checks)."""
    if not tf.get("has_terraform"):
        return
    if not ci_st.get("has_ci"):
        return

    all_steps = _all_ci_steps(ci_wf)
    all_step_text = " ".join(all_steps)

    has_tf_in_ci = any(p in all_step_text for p in _TF_CI_PATTERNS)
    has_tf_plan = any(p in all_step_text for p in _TF_PLAN_PATTERNS)
    has_tf_apply = any(p in all_step_text for p in _TF_APPLY_PATTERNS)

    # Check triggers for PR
    has_pr_trigger = False
    for wf in ci_wf.get("workflows", []):
        triggers = wf.get("triggers", [])
        if "pull_request" in triggers or "pull_request_target" in triggers:
            has_pr_trigger = True

    # Check 1: Terraform not in CI
    if not has_tf_in_ci:
        issues.append({
            "file": "cross-domain",
            "severity": "info",
            "message": (
                "Terraform↔CI: Terraform exists but no CI pipeline "
                "automates it — manual deployment"
            ),
        })

    # Check 2: No plan on PR
    if has_tf_apply and not (has_tf_plan and has_pr_trigger):
        issues.append({
            "file": "cross-domain",
            "severity": "info",
            "message": (
                "Terraform↔CI: CI has terraform apply but no "
                "terraform plan on pull request — missing change preview"
            ),
        })

    # Check 3: Apply without environment protection
    if has_tf_apply:
        has_env_protection = False
        for wf in ci_wf.get("workflows", []):
            for job in wf.get("jobs", []):
                job_text = " ".join(
                    _ci_step_text(s) for s in job.get("steps", [])
                )
                if any(p in job_text for p in _TF_APPLY_PATTERNS):
                    if job.get("environment"):
                        has_env_protection = True
        if not has_env_protection:
            issues.append({
                "file": "cross-domain",
                "severity": "warning",
                "message": (
                    "Terraform↔CI: terraform apply runs without "
                    "environment protection — no approval gates"
                ),
            })


# ═══════════════════════════════════════════════════════════════════
#  Terraform ↔ Environments seam (2 checks)
# ═══════════════════════════════════════════════════════════════════


def _cross_terraform_envs(
    project_root: Path,
    tf: dict,
    issues: list[dict],
) -> None:
    """Terraform ↔ Environments cross-domain checks (2 checks)."""
    if not tf.get("has_terraform"):
        return

    environments = _load_project_environments(project_root)
    if len(environments) < 2:
        return

    # Check 1: Workspace / environment alignment
    # Look for tfvars files that match environment names
    tf_root = tf.get("root") or "."
    tf_dir = project_root / tf_root if tf_root != "." else project_root

    env_tfvars_found = set()
    for env in environments:
        patterns = [
            f"{env}.tfvars",
            f"{env}.auto.tfvars",
            f"environments/{env}.tfvars",
            f"envs/{env}.tfvars",
        ]
        for p in patterns:
            if (tf_dir / p).is_file() or (project_root / p).is_file():
                env_tfvars_found.add(env)
                break

    if not env_tfvars_found:
        issues.append({
            "file": "cross-domain",
            "severity": "info",
            "message": (
                f"Terraform↔Environments: project has {len(environments)} "
                f"environments ({', '.join(environments)}) but "
                f"no per-environment Terraform configuration found"
            ),
        })

    # Check 2: Variable file coverage
    missing_tfvars = set(environments) - env_tfvars_found
    if missing_tfvars and env_tfvars_found:
        # Some envs have tfvars, some don't
        for missing in sorted(missing_tfvars):
            issues.append({
                "file": "cross-domain",
                "severity": "info",
                "message": (
                    f"Terraform↔Environments: no .tfvars variable file "
                    f"for environment '{missing}'"
                ),
            })


# ═══════════════════════════════════════════════════════════════════
#  CI/CD ↔ K8s seam (5 checks)
# ═══════════════════════════════════════════════════════════════════

_K8S_DEPLOY_PATTERNS = (
    "kubectl apply", "kubectl set image", "kubectl rollout",
    "helm upgrade", "helm install",
    "azure/k8s-deploy", "azure/k8s-set-context",
    "aws-actions/amazon-eks", "google-github-actions/deploy-cloudrun",
)
_K8S_AUTH_PATTERNS = (
    "kubeconfig", "kube_config", "KUBECONFIG",
    "azure/k8s-set-context", "aws-actions/configure-aws-credentials",
    "google-github-actions/auth", "google-github-actions/get-gke-credentials",
    "doctl kubernetes cluster kubeconfig",
)


def _cross_ci_k8s(
    project_root: Path,
    docker: dict,
    ci_st: dict,
    ci_wf: dict,
    all_resources: list[tuple[str, dict]],
    issues: list[dict],
) -> None:
    """CI/CD ↔ K8s cross-domain checks (5 checks)."""
    if not ci_st.get("has_ci"):
        return
    if not all_resources:
        return

    all_steps = _all_ci_steps(ci_wf)
    all_step_text = " ".join(all_steps)

    has_k8s_deploy = any(p in all_step_text for p in _K8S_DEPLOY_PATTERNS)
    has_docker_build = any(p in all_step_text for p in _DOCKER_BUILD_PATTERNS)
    has_helm_in_ci = "helm" in all_step_text
    has_kubectl_in_ci = "kubectl" in all_step_text
    has_k8s_auth = any(p.lower() in all_step_text for p in _K8S_AUTH_PATTERNS)

    # Check 1: K8s manifests but no deploy step in CI
    if not has_k8s_deploy:
        issues.append({
            "file": "cross-domain",
            "severity": "info",
            "message": (
                "CI↔K8s: K8s manifests exist but CI has no deploy step "
                "— manual deployment required"
            ),
        })

    # Check 2: Image build→deploy chain
    has_dockerfile = docker.get("has_dockerfile", False)
    if has_k8s_deploy and has_dockerfile and not has_docker_build:
        issues.append({
            "file": "cross-domain",
            "severity": "warning",
            "message": (
                "CI↔K8s: CI deploys to K8s but doesn't build "
                "Docker images — may deploy stale images"
            ),
        })

    # Check 3: Environment gates
    environments = _load_project_environments(project_root)
    has_prod = any(e.lower() in ("production", "prod") for e in environments)

    if has_k8s_deploy and has_prod:
        has_env_gate = False
        for wf in ci_wf.get("workflows", []):
            for job in wf.get("jobs", []):
                if job.get("environment"):
                    job_text = " ".join(
                        _ci_step_text(s) for s in job.get("steps", [])
                    )
                    if any(p in job_text for p in _K8S_DEPLOY_PATTERNS):
                        has_env_gate = True
        if not has_env_gate:
            issues.append({
                "file": "cross-domain",
                "severity": "info",
                "message": (
                    "CI↔K8s: CI deploys to K8s with production environment "
                    "but no environment protection gate"
                ),
            })

    # Check 4: Deploy strategy ↔ CI tool alignment
    has_helm_charts = any(
        (project_root / p).is_file()
        for p in [
            "Chart.yaml", "charts/Chart.yaml",
        ]
    ) or any(
        f.name == "Chart.yaml"
        for f in project_root.rglob("Chart.yaml")
        if ".git" not in str(f) and "node_modules" not in str(f)
    )
    if has_helm_charts and has_kubectl_in_ci and not has_helm_in_ci:
        issues.append({
            "file": "cross-domain",
            "severity": "warning",
            "message": (
                "CI↔K8s: Helm charts present but CI uses kubectl "
                "instead of helm for deployment"
            ),
        })

    # Check 5: Cluster credentials in CI
    if has_k8s_deploy and not has_k8s_auth:
        issues.append({
            "file": "cross-domain",
            "severity": "warning",
            "message": (
                "CI↔K8s: CI deploys to K8s but no cluster credentials "
                "setup detected (missing kubeconfig/auth action)"
            ),
        })


# ═══════════════════════════════════════════════════════════════════
#  CI/CD ↔ Environments seam (3 checks)
# ═══════════════════════════════════════════════════════════════════


def _cross_ci_envs(
    project_root: Path,
    ci_st: dict,
    ci_wf: dict,
    all_resources: list[tuple[str, dict]],
    issues: list[dict],
) -> None:
    """CI/CD ↔ Environments cross-domain checks (3 checks)."""
    if not ci_st.get("has_ci"):
        return

    environments = _load_project_environments(project_root)
    if not environments:
        return

    all_steps = _all_ci_steps(ci_wf)
    all_step_text = " ".join(all_steps)

    has_k8s_deploy = any(p in all_step_text for p in _K8S_DEPLOY_PATTERNS)

    # Collect CI job environments
    ci_envs: set[str] = set()
    for wf in ci_wf.get("workflows", []):
        for job in wf.get("jobs", []):
            env = job.get("environment")
            if env:
                if isinstance(env, dict):
                    env = env.get("name", "")
                ci_envs.add(str(env).lower())

    # Check 1: CI environment coverage
    for env in environments:
        if env.lower() not in ci_envs:
            issues.append({
                "file": "cross-domain",
                "severity": "info",
                "message": (
                    f"CI↔Environments: environment '{env}' has "
                    f"no CI pipeline coverage"
                ),
            })

    # Check 2: Secret injection
    has_secret_refs = "secrets." in all_step_text or "${{ secrets" in all_step_text.replace(" ", "")
    if has_k8s_deploy and not has_secret_refs:
        issues.append({
            "file": "cross-domain",
            "severity": "warning",
            "message": (
                "CI↔Environments: CI deploys but doesn't inject "
                "secrets — credentials may be hardcoded"
            ),
        })

    # Check 3: Production protection
    has_prod = any(e.lower() in ("production", "prod") for e in environments)
    if has_prod and has_k8s_deploy:
        prod_has_gate = any(
            e in ("production", "prod")
            for e in ci_envs
        )
        if not prod_has_gate:
            issues.append({
                "file": "cross-domain",
                "severity": "info",
                "message": (
                    "CI↔Environments: CI deploys with production environment "
                    "present but no approval/protection gate for production"
                ),
            })


# ═══════════════════════════════════════════════════════════════════
#  Cross-cutting intelligence (3 checks)
# ═══════════════════════════════════════════════════════════════════

# Patterns for extracting version from Docker image references
_VERSION_EXTRACT_RE = re.compile(
    r"(?:python|node|ruby|golang|openjdk|java|php|dotnet|rust):(\d+(?:\.\d+)*)"
)
# Patterns for extracting version from CI setup actions
_CI_SETUP_VERSION_ACTIONS = {
    "actions/setup-python": "python",
    "actions/setup-node": "node",
    "actions/setup-java": "java",
    "actions/setup-go": "golang",
    "ruby/setup-ruby": "ruby",
}


def _cross_cutting(
    project_root: Path,
    docker: dict,
    ci_st: dict,
    ci_wf: dict,
    tf: dict,
    all_resources: list[tuple[str, dict]],
    issues: list[dict],
) -> None:
    """Cross-cutting intelligence checks (3 checks)."""

    has_dockerfile = docker.get("has_dockerfile", False)
    has_k8s = bool(all_resources)
    has_ci = ci_st.get("has_ci", False)

    # Check 1: Version alignment (Dockerfile ↔ CI)
    if has_dockerfile and has_ci:
        dockerfile_details = docker.get("dockerfile_details", [])
        docker_versions: dict[str, str] = {}  # lang -> version
        for df in dockerfile_details:
            for img in df.get("base_images", []):
                m = _VERSION_EXTRACT_RE.search(img)
                if m:
                    lang = img.split(":")[0].rsplit("/", 1)[-1]
                    docker_versions[lang.lower()] = m.group(1)

        # Check CI setup actions for version mismatches
        for wf in ci_wf.get("workflows", []):
            for job in wf.get("jobs", []):
                for step in job.get("steps", []):
                    uses = step.get("uses", "")
                    with_data = step.get("with", {})
                    for action_prefix, lang in _CI_SETUP_VERSION_ACTIONS.items():
                        if uses.startswith(action_prefix):
                            ci_version_keys = [
                                f"{lang}-version", "python-version",
                                "node-version", "java-version",
                                "go-version", "ruby-version",
                            ]
                            for key in ci_version_keys:
                                ci_ver = str(with_data.get(key, ""))
                                if ci_ver and lang in docker_versions:
                                    docker_ver = docker_versions[lang]
                                    # Compare major.minor
                                    ci_major_minor = ".".join(ci_ver.split(".")[:2])
                                    docker_major_minor = ".".join(docker_ver.split(".")[:2])
                                    if ci_major_minor != docker_major_minor:
                                        issues.append({
                                            "file": "cross-domain",
                                            "severity": "warning",
                                            "message": (
                                                f"Cross-cutting: {lang} version mismatch — "
                                                f"Dockerfile uses {docker_ver}, "
                                                f"CI uses {ci_ver}"
                                            ),
                                        })

    # Check 2: Pipeline completeness
    if has_dockerfile and has_k8s and not has_ci:
        issues.append({
            "file": "cross-domain",
            "severity": "info",
            "message": (
                "Cross-cutting: Docker + K8s detected but no CI/CD pipeline — "
                "no automation for build/test/deploy"
            ),
        })

    # Check 3: Secret flow integrity
    env_file = project_root / ".env"
    if env_file.is_file() and has_k8s:
        try:
            content = env_file.read_text(encoding="utf-8")
            env_vars = []
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key = line.split("=", 1)[0].strip()
                    # Only flag vars that look like secrets
                    secret_hints = ("password", "secret", "key", "token", "api_key", "apikey")
                    if any(h in key.lower() for h in secret_hints):
                        env_vars.append(key)

            if env_vars:
                has_k8s_secrets = any(
                    res.get("kind") == "Secret"
                    for _, res in all_resources
                )
                if not has_k8s_secrets:
                    issues.append({
                        "file": "cross-domain",
                        "severity": "info",
                        "message": (
                            f"Cross-cutting: .env contains secret-like vars "
                            f"({', '.join(env_vars[:3])}) but no K8s Secret "
                            f"resources found for production deployment"
                        ),
                    })
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════
#  Layer 7 — Deployment strategy validation
# ═══════════════════════════════════════════════════════════════════

# Regex to find ${VAR} envsubst patterns in raw manifest text
_ENVSUBST_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

# Standard K8s namespaces that exist without needing a Namespace manifest
_BUILTIN_NAMESPACES = frozenset({
    "default", "kube-system", "kube-public", "kube-node-lease",
})

# Workload kinds whose pod template labels can match a Service selector
_WORKLOAD_KINDS = {
    "Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Pod",
}


def _validate_deployment_strategy(
    project_root: Path,
    status: dict,
    all_resources: list[tuple[str, dict]],
    issues: list[dict],
) -> None:
    """Deployment strategy validation (Layer 7).

    Checks that the chosen deployment method is internally consistent.
    """
    # Raw kubectl checks apply when we have any raw manifests
    if all_resources:
        _strategy_raw_kubectl(project_root, status, all_resources, issues)

    # Helm checks apply when we have helm charts
    helm_charts = status.get("helm_charts", [])
    if helm_charts:
        _strategy_helm(project_root, status, helm_charts, issues)

    # Kustomize checks apply when kustomize is detected
    kustomize = status.get("kustomize", {})
    if kustomize.get("exists"):
        _strategy_kustomize(project_root, status, kustomize, all_resources, issues)

    # Skaffold checks apply when skaffold.yaml exists
    skaffold_file = project_root / "skaffold.yaml"
    if skaffold_file.is_file():
        _strategy_skaffold(project_root, skaffold_file, issues)

    # Mixed strategy coherence checks
    _strategy_mixed(
        project_root, status, all_resources,
        helm_charts, kustomize, skaffold_file, issues,
    )


def _strategy_raw_kubectl(
    project_root: Path,
    status: dict,
    all_resources: list[tuple[str, dict]],
    issues: list[dict],
) -> None:
    """Raw kubectl deployment strategy checks (8 checks).

    These checks validate that raw K8s manifests are self-contained
    and can be successfully applied with `kubectl apply`.
    """

    # ── Pre-compute resource indices for cross-checks ─────────

    # All Namespace names defined in manifests
    defined_namespaces: set[str] = set()
    # All ConfigMap names by namespace
    defined_configmaps: dict[str, set[str]] = {}  # ns -> {name, ...}
    # All Secret names by namespace
    defined_secrets: dict[str, set[str]] = {}  # ns -> {name, ...}
    # All Service names by namespace
    defined_services: dict[str, set[str]] = {}  # ns -> {name, ...}
    # All StorageClass names
    defined_storageclasses: set[str] = set()
    # All workload pod template labels by namespace
    workload_labels: list[tuple[str, dict]] = []  # (ns, labels_dict)

    for _path, res in all_resources:
        kind = res.get("kind", "")
        name = res.get("metadata", {}).get("name", "")
        ns = res.get("metadata", {}).get("namespace", "") or "default"

        if kind == "Namespace":
            defined_namespaces.add(name)
        elif kind == "ConfigMap":
            defined_configmaps.setdefault(ns, set()).add(name)
        elif kind == "Secret":
            defined_secrets.setdefault(ns, set()).add(name)
        elif kind == "Service":
            defined_services.setdefault(ns, set()).add(name)
        elif kind == "StorageClass":
            defined_storageclasses.add(name)

        # Collect workload pod template labels
        if kind in _WORKLOAD_KINDS:
            if kind == "Pod":
                pod_labels = res.get("metadata", {}).get("labels", {})
            else:
                pod_labels = (
                    res.get("spec", {})
                    .get("template", {})
                    .get("metadata", {})
                    .get("labels", {})
                )
            if pod_labels:
                workload_labels.append((ns, pod_labels))

    # ── Check 1: Unresolved envsubst variables ────────────────
    for manifest in status.get("manifests", []):
        manifest_path = project_root / manifest["path"]
        if manifest_path.is_file():
            try:
                text = manifest_path.read_text(encoding="utf-8", errors="ignore")
                found_vars = _ENVSUBST_RE.findall(text)
                if found_vars:
                    unique_vars = sorted(set(found_vars))
                    issues.append({
                        "file": manifest["path"],
                        "severity": "warning",
                        "message": (
                            f"Raw kubectl: unresolved envsubst variables "
                            f"({', '.join('${' + v + '}' for v in unique_vars)})"
                            f" — manifests need envsubst processing before apply"
                        ),
                    })
            except Exception:
                pass

    # ── Check 2: Missing Namespace manifest ───────────────────
    referenced_namespaces: set[str] = set()
    for _path, res in all_resources:
        ns = res.get("metadata", {}).get("namespace", "")
        if ns:
            referenced_namespaces.add(ns)

    for ns in sorted(referenced_namespaces):
        if ns not in _BUILTIN_NAMESPACES and ns not in defined_namespaces:
            issues.append({
                "file": "deployment-strategy",
                "severity": "warning",
                "message": (
                    f"Raw kubectl: namespace '{ns}' referenced by resources "
                    f"but no Namespace manifest defined — "
                    f"kubectl apply will fail if namespace doesn't exist"
                ),
            })

    # ── Check 3: CRD ordering gap ─────────────────────────────
    # If a resource uses a non-standard apiVersion (contains a dot,
    # like cert-manager.io/v1) AND its kind is not in _K8S_KINDS,
    # it's a Custom Resource. Check if a CRD is present.
    has_crds = any(
        res.get("kind") == "CustomResourceDefinition"
        for _, res in all_resources
    )
    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        api_version = res.get("apiVersion", "")
        name = res.get("metadata", {}).get("name", "?")
        # Custom resource heuristic: apiVersion has a domain (dot)
        # and kind is not a standard K8s kind
        if (
            kind
            and kind not in _K8S_KINDS
            and "." in api_version
            and kind != "CustomResourceDefinition"
            and not has_crds
        ):
            issues.append({
                "file": rel_path,
                "severity": "error",
                "message": (
                    f"Raw kubectl: {kind}/{name} is a Custom Resource "
                    f"(apiVersion: {api_version}) but no CRD manifest found — "
                    f"kubectl apply will fail without the CRD installed"
                ),
            })

    # ── Check 4: Raw Secret with literal data ─────────────────
    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        name = res.get("metadata", {}).get("name", "?")
        if kind == "Secret":
            has_data = bool(res.get("data"))
            has_string_data = bool(res.get("stringData"))
            if has_data or has_string_data:
                issues.append({
                    "file": rel_path,
                    "severity": "warning",
                    "message": (
                        f"Raw kubectl: Secret/{name} contains plaintext "
                        f"secret data in manifests — consider SealedSecret, "
                        f"ExternalSecret, or SOPS for production"
                    ),
                })

    # ── Check 5: ConfigMap/Secret reference gap ───────────────
    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        if kind not in _WORKLOAD_KINDS and kind not in ("Job", "CronJob"):
            continue
        name = res.get("metadata", {}).get("name", "?")
        ns = res.get("metadata", {}).get("namespace", "") or "default"

        # Get pod spec containers
        if kind in ("Job", "CronJob"):
            if kind == "CronJob":
                pod_spec = (
                    res.get("spec", {})
                    .get("jobTemplate", {})
                    .get("spec", {})
                    .get("template", {})
                    .get("spec", {})
                )
            else:
                pod_spec = (
                    res.get("spec", {})
                    .get("template", {})
                    .get("spec", {})
                )
        elif kind == "Pod":
            pod_spec = res.get("spec", {})
        else:
            pod_spec = (
                res.get("spec", {})
                .get("template", {})
                .get("spec", {})
            )

        containers = pod_spec.get("containers", []) + pod_spec.get("initContainers", [])
        for container in containers:
            # Check envFrom references
            for env_from in container.get("envFrom", []):
                cm_ref = env_from.get("configMapRef", {})
                if cm_ref:
                    cm_name = cm_ref.get("name", "")
                    if cm_name and cm_name not in defined_configmaps.get(ns, set()):
                        issues.append({
                            "file": rel_path,
                            "severity": "warning",
                            "message": (
                                f"Raw kubectl: {kind}/{name} references "
                                f"ConfigMap '{cm_name}' via envFrom but "
                                f"no ConfigMap with that name found in manifests"
                            ),
                        })
                secret_ref = env_from.get("secretRef", {})
                if secret_ref:
                    s_name = secret_ref.get("name", "")
                    if s_name and s_name not in defined_secrets.get(ns, set()):
                        issues.append({
                            "file": rel_path,
                            "severity": "warning",
                            "message": (
                                f"Raw kubectl: {kind}/{name} references "
                                f"Secret '{s_name}' via envFrom but "
                                f"no Secret with that name found in manifests"
                            ),
                        })

        # Check volume references
        for vol in pod_spec.get("volumes", []):
            cm_vol = vol.get("configMap", {})
            if cm_vol:
                cm_name = cm_vol.get("name", "")
                if cm_name and cm_name not in defined_configmaps.get(ns, set()):
                    issues.append({
                        "file": rel_path,
                        "severity": "warning",
                        "message": (
                            f"Raw kubectl: {kind}/{name} mounts "
                            f"ConfigMap '{cm_name}' as volume but "
                            f"no ConfigMap with that name found in manifests"
                        ),
                    })
            secret_vol = vol.get("secret", {})
            if secret_vol:
                s_name = secret_vol.get("secretName", "")
                if s_name and s_name not in defined_secrets.get(ns, set()):
                    issues.append({
                        "file": rel_path,
                        "severity": "warning",
                        "message": (
                            f"Raw kubectl: {kind}/{name} mounts "
                            f"Secret '{s_name}' as volume but "
                            f"no Secret with that name found in manifests"
                        ),
                    })

    # ── Check 6: Service selector mismatch ────────────────────
    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        if kind != "Service":
            continue
        name = res.get("metadata", {}).get("name", "?")
        ns = res.get("metadata", {}).get("namespace", "") or "default"
        selector = res.get("spec", {}).get("selector", {})
        if not selector:
            continue  # headless or ExternalName

        # Check if any workload's pod labels are a superset of the selector
        matched = False
        for wl_ns, wl_labels in workload_labels:
            # Services match within same namespace (or if ns not set)
            if wl_ns != ns:
                continue
            # All selector labels must be present in workload labels
            if all(wl_labels.get(k) == v for k, v in selector.items()):
                matched = True
                break

        if not matched:
            issues.append({
                "file": rel_path,
                "severity": "warning",
                "message": (
                    f"Raw kubectl: Service/{name} selector "
                    f"{selector} matches no workload pod labels "
                    f"in namespace '{ns}'"
                ),
            })

    # ── Check 7: Ingress backend gap ──────────────────────────
    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        if kind != "Ingress":
            continue
        ingress_name = res.get("metadata", {}).get("name", "?")
        ns = res.get("metadata", {}).get("namespace", "") or "default"
        ns_services = defined_services.get(ns, set())

        # Check default backend
        default_backend = res.get("spec", {}).get("defaultBackend", {})
        if default_backend:
            svc_name = default_backend.get("service", {}).get("name", "")
            if svc_name and svc_name not in ns_services:
                issues.append({
                    "file": rel_path,
                    "severity": "warning",
                    "message": (
                        f"Raw kubectl: Ingress/{ingress_name} default backend "
                        f"references Service '{svc_name}' not found in manifests"
                    ),
                })

        # Check rule backends
        for rule in res.get("spec", {}).get("rules", []):
            for path_entry in (rule.get("http", {}) or {}).get("paths", []):
                backend = path_entry.get("backend", {})
                svc_name = backend.get("service", {}).get("name", "")
                if svc_name and svc_name not in ns_services:
                    issues.append({
                        "file": rel_path,
                        "severity": "warning",
                        "message": (
                            f"Raw kubectl: Ingress/{ingress_name} references "
                            f"backend Service '{svc_name}' not found in manifests"
                        ),
                    })

    # ── Check 8: PVC StorageClass gap ─────────────────────────
    for rel_path, res in all_resources:
        kind = res.get("kind", "")
        if kind != "PersistentVolumeClaim":
            continue
        name = res.get("metadata", {}).get("name", "?")
        sc_name = res.get("spec", {}).get("storageClassName", "")
        if sc_name and sc_name not in defined_storageclasses:
            issues.append({
                "file": rel_path,
                "severity": "info",
                "message": (
                    f"Raw kubectl: PVC/{name} uses StorageClass "
                    f"'{sc_name}' not defined in manifests — "
                    f"ensure it exists on the cluster"
                ),
            })


# SemVer regex — basic check: MAJOR.MINOR.PATCH with optional pre-release
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?"
    r"(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$"
)


def _strategy_helm(
    project_root: Path,
    status: dict,
    helm_charts: list[dict],
    issues: list[dict],
) -> None:
    """Helm deployment strategy checks (13 checks).

    Validates Helm charts against the Chart.yaml v2 spec.
    """
    import yaml as _yaml

    for chart in helm_charts:
        chart_path = chart.get("path", "")
        chart_dir = project_root / chart_path
        chart_file = chart_dir / "Chart.yaml"
        chart_name = chart.get("name", "unknown")
        chart_type = chart.get("type", "application")
        has_templates = chart.get("has_templates", False)
        has_values = chart.get("has_values", False)
        has_lockfile = chart.get("has_lockfile", False)
        has_subcharts = chart.get("has_subcharts", False)

        # Parse Chart.yaml for extra data not in detection
        chart_data: dict = {}
        try:
            if chart_file.is_file():
                chart_data = _yaml.safe_load(
                    chart_file.read_text(encoding="utf-8")
                ) or {}
        except Exception:
            pass

        api_version = chart_data.get("apiVersion", "")
        dependencies = chart_data.get("dependencies", []) or []
        chart_version = str(chart_data.get("version", ""))
        chart_name_from_yaml = chart_data.get("name", "")

        # ── 1. No templates directory ─────────────────────────
        if not has_templates and chart_type == "application":
            issues.append({
                "file": chart_path,
                "severity": "error",
                "message": (
                    f"Helm: chart '{chart_name}' has no templates/ directory "
                    f"— application chart without templates cannot render manifests"
                ),
            })

        # ── 2. No values.yaml ─────────────────────────────────
        if not has_values:
            issues.append({
                "file": chart_path,
                "severity": "warning",
                "message": (
                    f"Helm: chart '{chart_name}' has no values.yaml "
                    f"— no default configuration values defined"
                ),
            })

        # ── 3. Dependencies without lock ──────────────────────
        if dependencies and not has_lockfile:
            dep_names = [d.get("name", "?") for d in dependencies[:3]]
            issues.append({
                "file": chart_path,
                "severity": "info",
                "message": (
                    f"Helm: chart '{chart_name}' has dependencies "
                    f"({', '.join(dep_names)}) but no Chart.lock "
                    f"— run 'helm dependency build'"
                ),
            })

        # ── 4. Deprecated apiVersion v1 ───────────────────────
        if api_version == "v1":
            issues.append({
                "file": chart_path,
                "severity": "warning",
                "message": (
                    f"Helm: chart '{chart_name}' uses deprecated "
                    f"apiVersion v1 (Helm 2 format) — migrate to apiVersion v2"
                ),
            })

        # ── 5. Library chart with non-helper templates ────────
        if chart_type == "library" and has_templates:
            templates_dir = chart_dir / "templates"
            if templates_dir.is_dir():
                renderable = [
                    f.name for f in templates_dir.iterdir()
                    if f.is_file() and not f.name.startswith("_")
                ]
                if renderable:
                    issues.append({
                        "file": chart_path,
                        "severity": "warning",
                        "message": (
                            f"Helm: library chart '{chart_name}' has renderable "
                            f"templates ({', '.join(renderable[:3])}) — library "
                            f"charts should only contain _*.tpl helper files"
                        ),
                    })

        # ── 6. Orphaned subcharts ─────────────────────────────
        if has_subcharts and not dependencies:
            issues.append({
                "file": chart_path,
                "severity": "info",
                "message": (
                    f"Helm: chart '{chart_name}' has charts/ subchart "
                    f"directory but no dependencies declared in Chart.yaml"
                ),
            })

        # ── 7. Missing required fields ────────────────────────
        if not chart_name_from_yaml:
            issues.append({
                "file": chart_path,
                "severity": "error",
                "message": (
                    f"Helm: Chart.yaml missing required field 'name'"
                ),
            })
        if not chart_data.get("version"):
            issues.append({
                "file": chart_path,
                "severity": "error",
                "message": (
                    f"Helm: Chart.yaml missing required field 'version'"
                ),
            })

        # ── 8. Invalid SemVer version ─────────────────────────
        if chart_version and not _SEMVER_RE.match(chart_version):
            issues.append({
                "file": chart_path,
                "severity": "warning",
                "message": (
                    f"Helm: chart '{chart_name}' version '{chart_version}' "
                    f"is not valid SemVer — Helm spec requires SemVer 2"
                ),
            })

        # ── 9. No .helmignore ─────────────────────────────────
        helmignore = chart_dir / ".helmignore"
        if not helmignore.is_file():
            # Count files in project to see if worth warning
            try:
                file_count = sum(
                    1 for _ in project_root.rglob("*") if _.is_file()
                )
                if file_count > 20:
                    issues.append({
                        "file": chart_path,
                        "severity": "info",
                        "message": (
                            f"Helm: chart '{chart_name}' has no .helmignore "
                            f"— 'helm package' will include all {file_count} "
                            f"project files"
                        ),
                    })
            except Exception:
                pass

        # ── 10-11-12. Template directory checks ───────────────
        if has_templates:
            templates_dir = chart_dir / "templates"
            if templates_dir.is_dir():
                template_files = [
                    f.name for f in templates_dir.iterdir() if f.is_file()
                ]

                # 10. Missing NOTES.txt
                if "NOTES.txt" not in template_files:
                    issues.append({
                        "file": chart_path,
                        "severity": "info",
                        "message": (
                            f"Helm: chart '{chart_name}' templates/ has no "
                            f"NOTES.txt — no post-install notes for users"
                        ),
                    })

                # 11. No _helpers.tpl
                if not any(f.startswith("_") and f.endswith(".tpl") for f in template_files):
                    issues.append({
                        "file": chart_path,
                        "severity": "info",
                        "message": (
                            f"Helm: chart '{chart_name}' templates/ has no "
                            f"_helpers.tpl — no reusable template helpers defined"
                        ),
                    })

        # 12. No values.schema.json
        schema_file = chart_dir / "values.schema.json"
        if not schema_file.is_file():
            issues.append({
                "file": chart_path,
                "severity": "info",
                "message": (
                    f"Helm: chart '{chart_name}' has no values.schema.json "
                    f"— values input is not schema-validated"
                ),
            })

        # ── 13. Local file:// dependency ──────────────────────
        for dep in dependencies:
            repo = dep.get("repository", "")
            dep_name = dep.get("name", "?")
            if repo.startswith("file://"):
                issues.append({
                    "file": chart_path,
                    "severity": "warning",
                    "message": (
                        f"Helm: chart '{chart_name}' dependency '{dep_name}' "
                        f"uses local repository ({repo}) — this won't resolve "
                        f"in a distributed chart"
                    ),
                })


def _strategy_kustomize(
    project_root: Path,
    status: dict,
    kustomize: dict,
    all_resources: list[tuple[str, dict]],
    issues: list[dict],
) -> None:
    """Kustomize deployment strategy checks (10 checks).

    Validates kustomization.yaml against the Kustomize spec.
    """
    import yaml as _yaml

    kust_path = kustomize.get("path", "")
    # Determine kustomize directory from the path
    # path could be "k8s/kustomization.yaml" — dir is "k8s"
    kust_file_path = project_root / kust_path
    if kust_file_path.is_file():
        kust_dir = kust_file_path.parent
    else:
        # Try as directory containing kustomization.yaml
        kust_dir = project_root / kust_path
        kust_file_path = None
        for name in ("kustomization.yaml", "kustomization.yml", "Kustomization"):
            candidate = kust_dir / name
            if candidate.is_file():
                kust_file_path = candidate
                break

    if not kust_file_path or not kust_file_path.is_file():
        return

    # Parse kustomization content
    content: dict = {}
    try:
        content = _yaml.safe_load(
            kust_file_path.read_text(encoding="utf-8")
        ) or {}
    except Exception:
        return

    resources = content.get("resources", []) or []
    if not isinstance(resources, list):
        resources = []

    # ── 1. Missing resource file ──────────────────────────────
    for res_ref in resources:
        if not isinstance(res_ref, str):
            continue
        res_path = kust_dir / res_ref
        if not res_path.exists():
            issues.append({
                "file": kust_path,
                "severity": "error",
                "message": (
                    f"Kustomize: resource '{res_ref}' referenced in "
                    f"kustomization.yaml not found on disk"
                ),
            })

    # ── 2. Path traversal ─────────────────────────────────────
    for res_ref in resources:
        if not isinstance(res_ref, str):
            continue
        try:
            resolved = (kust_dir / res_ref).resolve()
            if not str(resolved).startswith(str(project_root.resolve())):
                issues.append({
                    "file": kust_path,
                    "severity": "error",
                    "message": (
                        f"Kustomize: resource '{res_ref}' traverses outside "
                        f"project root — potential security risk"
                    ),
                })
        except Exception:
            pass

    # ── 3. Overlays without base ──────────────────────────────
    overlays = kustomize.get("overlays", [])
    has_base = kustomize.get("has_bases", False)
    if overlays and not has_base:
        issues.append({
            "file": kust_path,
            "severity": "warning",
            "message": (
                f"Kustomize: overlays found ({', '.join(overlays[:3])}) "
                f"but no base/ directory — overlay/base pattern incomplete"
            ),
        })

    # ── 4. Secret generator with literals ─────────────────────
    secret_gen = content.get("secretGenerator", []) or []
    if isinstance(secret_gen, list):
        for sg in secret_gen:
            if isinstance(sg, dict) and sg.get("literals"):
                sg_name = sg.get("name", "?")
                issues.append({
                    "file": kust_path,
                    "severity": "warning",
                    "message": (
                        f"Kustomize: secretGenerator '{sg_name}' has "
                        f"plaintext secret literals in kustomization.yaml "
                        f"— avoid committing secrets to VCS"
                    ),
                })

    # ── 5. Duplicate resource ─────────────────────────────────
    seen_resources: set[str] = set()
    for res_ref in resources:
        if not isinstance(res_ref, str):
            continue
        if res_ref in seen_resources:
            issues.append({
                "file": kust_path,
                "severity": "error",
                "message": (
                    f"Kustomize: duplicate resource '{res_ref}' "
                    f"in resources list — kustomize build will fail"
                ),
            })
        seen_resources.add(res_ref)

    # ── 6. Patch targets missing resource ─────────────────────
    # Build index of known resource kinds+names from all_resources
    known_resources: set[tuple[str, str]] = set()  # (kind, name)
    for _, res in all_resources:
        kind = res.get("kind", "")
        name = res.get("metadata", {}).get("name", "")
        if kind and name:
            known_resources.add((kind, name))

    patches = content.get("patches", []) or []
    if isinstance(patches, list):
        for patch in patches:
            if not isinstance(patch, dict):
                continue
            target = patch.get("target", {})
            if not isinstance(target, dict):
                continue
            t_kind = target.get("kind", "")
            t_name = target.get("name", "")
            if t_kind and t_name and (t_kind, t_name) not in known_resources:
                issues.append({
                    "file": kust_path,
                    "severity": "warning",
                    "message": (
                        f"Kustomize: patch targets {t_kind}/{t_name} but "
                        f"no matching resource found in manifests"
                    ),
                })

    # ── 7. Deprecated bases field ─────────────────────────────
    if content.get("bases"):
        issues.append({
            "file": kust_path,
            "severity": "info",
            "message": (
                f"Kustomize: deprecated 'bases' field used — "
                f"migrate to 'resources' entries (deprecated since kustomize v2.1.0)"
            ),
        })

    # ── 8. commonLabels immutability risk ──────────────────────
    if content.get("commonLabels"):
        issues.append({
            "file": kust_path,
            "severity": "info",
            "message": (
                f"Kustomize: commonLabels is used — label changes will "
                f"break immutable selector fields (spec.selector.matchLabels) "
                f"on existing Deployments"
            ),
        })

    # ── 9. Missing components directory ───────────────────────
    components = content.get("components", []) or []
    if isinstance(components, list):
        for comp_ref in components:
            if not isinstance(comp_ref, str):
                continue
            comp_path = kust_dir / comp_ref
            if not comp_path.is_dir():
                issues.append({
                    "file": kust_path,
                    "severity": "error",
                    "message": (
                        f"Kustomize: component '{comp_ref}' not found "
                        f"on disk — kustomize build will fail"
                    ),
                })

    # ── 10. Namespace override conflict ───────────────────────
    kust_namespace = content.get("namespace", "")
    if kust_namespace:
        hardcoded_ns = set()
        for _, res in all_resources:
            res_ns = res.get("metadata", {}).get("namespace", "")
            if res_ns and res_ns != kust_namespace:
                hardcoded_ns.add(res_ns)
        if hardcoded_ns:
            issues.append({
                "file": kust_path,
                "severity": "info",
                "message": (
                    f"Kustomize: namespace override '{kust_namespace}' set "
                    f"but resources have hardcoded namespaces "
                    f"({', '.join(sorted(hardcoded_ns)[:3])}) — "
                    f"override may conflict or be redundant"
                ),
            })


# Skaffold apiVersion prefixes considered "current" (v2+ and v3+ and v4+)
_SKAFFOLD_CURRENT_PREFIXES = ("skaffold/v2", "skaffold/v3", "skaffold/v4")


def _strategy_skaffold(
    project_root: Path,
    skaffold_file: Path,
    issues: list[dict],
) -> None:
    """Skaffold deployment strategy checks (7 checks).

    Validates skaffold.yaml against the Skaffold schema.
    """
    import yaml as _yaml

    try:
        content = _yaml.safe_load(
            skaffold_file.read_text(encoding="utf-8")
        ) or {}
    except Exception:
        return

    if not isinstance(content, dict):
        return

    api_version = content.get("apiVersion", "")
    build = content.get("build", {}) or {}
    deploy = content.get("deploy", {}) or {}
    manifests = content.get("manifests", {}) or {}
    profiles = content.get("profiles", []) or []

    # ── 1. Missing manifest file ────────────────────────────
    raw_yaml = manifests.get("rawYaml", []) or []
    if isinstance(raw_yaml, list):
        for ref in raw_yaml:
            if isinstance(ref, str) and not (project_root / ref).exists():
                issues.append({
                    "file": "skaffold.yaml",
                    "severity": "error",
                    "message": (
                        f"Skaffold: manifests.rawYaml references missing "
                        f"file '{ref}'"
                    ),
                })

    # ── 2. Missing Dockerfile ────────────────────────────────
    artifacts = build.get("artifacts", []) or []
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            docker = artifact.get("docker", {}) or {}
            dockerfile = docker.get("dockerfile", "")
            if dockerfile:
                # Resolve relative to artifact context or project root
                context = artifact.get("context", ".")
                df_path = project_root / context / dockerfile
                if not df_path.is_file():
                    image = artifact.get("image", "?")
                    issues.append({
                        "file": "skaffold.yaml",
                        "severity": "error",
                        "message": (
                            f"Skaffold: build artifact '{image}' references "
                            f"Dockerfile '{dockerfile}' not found on disk"
                        ),
                    })

    # ── 3. Deprecated apiVersion ─────────────────────────────
    if api_version and not any(
        api_version.startswith(p) for p in _SKAFFOLD_CURRENT_PREFIXES
    ):
        issues.append({
            "file": "skaffold.yaml",
            "severity": "warning",
            "message": (
                f"Skaffold: apiVersion '{api_version}' is deprecated "
                f"or outdated — consider migrating to v4beta+"
            ),
        })

    # ── 4 & 5. No deploy/manifests, or build without deploy ────
    has_deploy = bool(deploy)
    has_manifests = bool(manifests)
    has_build = bool(build.get("artifacts"))

    if not has_deploy and not has_manifests:
        if has_build:
            # Check 5: build without deploy
            issues.append({
                "file": "skaffold.yaml",
                "severity": "warning",
                "message": (
                    f"Skaffold: build section defined but no deploy "
                    f"or manifests section — images are built but not deployed"
                ),
            })
        else:
            # Check 4: truly empty
            issues.append({
                "file": "skaffold.yaml",
                "severity": "warning",
                "message": (
                    f"Skaffold: no deploy or manifests section "
                    f"— skaffold has no deployment configuration"
                ),
            })

    # ── 6. Empty default pipeline ────────────────────────────
    if (
        profiles
        and not has_build
        and not has_deploy
        and not has_manifests
    ):
        profile_names = [
            p.get("name", "?") for p in profiles[:3]
            if isinstance(p, dict)
        ]
        issues.append({
            "file": "skaffold.yaml",
            "severity": "info",
            "message": (
                f"Skaffold: default pipeline is empty, all config "
                f"lives in profiles ({', '.join(profile_names)}) "
                f"— requires --profile flag to deploy"
            ),
        })

    # ── 7. Non-reproducible tag policy ───────────────────────
    tag_policy = build.get("tagPolicy", {}) or {}
    if isinstance(tag_policy, dict):
        non_reproducible = {"sha256", "latest"}
        for policy_name in tag_policy:
            if policy_name in non_reproducible:
                issues.append({
                    "file": "skaffold.yaml",
                    "severity": "info",
                    "message": (
                        f"Skaffold: tagPolicy '{policy_name}' produces "
                        f"non-reproducible image tags — consider "
                        f"gitCommit or inputDigest for traceability"
                    ),
                })



def _strategy_mixed(
    project_root: Path,
    status: dict,
    all_resources: list[tuple[str, dict]],
    helm_charts: list[dict],
    kustomize: dict,
    skaffold_file: Path,
    issues: list[dict],
) -> None:
    """Mixed strategy coherence checks (5 checks).

    Cross-strategy consistency validation.
    """
    import yaml as _yaml

    deployment_strategy = status.get("deployment_strategy", "none")
    has_helm = bool(helm_charts)
    has_kustomize = kustomize.get("exists", False)
    has_skaffold = skaffold_file.is_file()

    # ── 1. Duplicate resource across strategies ──────────────
    # Check if same (kind, name, namespace) appears in raw manifests AND
    # Helm templates
    if has_helm and all_resources:
        # Resources from standard manifest dirs (non-template paths)
        raw_resource_keys: set[tuple[str, str, str]] = set()
        helm_resource_keys: set[tuple[str, str, str]] = set()

        for rel_path, res in all_resources:
            kind = res.get("kind", "")
            name = res.get("metadata", {}).get("name", "")
            ns = res.get("metadata", {}).get("namespace", "") or "default"
            if not kind or not name:
                continue
            key = (kind, name, ns)
            # Check if this is inside a Helm chart templates/ dir
            is_helm_template = False
            for chart in helm_charts:
                chart_path = chart.get("path", "")
                if chart_path and rel_path.startswith(chart_path + "/templates/"):
                    is_helm_template = True
                    break
            if is_helm_template:
                helm_resource_keys.add(key)
            else:
                raw_resource_keys.add(key)

        duplicates = raw_resource_keys & helm_resource_keys
        for kind, name, ns in sorted(duplicates):
            issues.append({
                "file": "deployment-strategy",
                "severity": "warning",
                "message": (
                    f"Mixed: {kind}/{name} (namespace: {ns}) exists in both "
                    f"raw manifests and Helm templates — dual management risk"
                ),
            })

    # ── 2. Orphaned manifests alongside Kustomize ────────────
    if has_kustomize:
        kust_path = kustomize.get("path", "")
        kust_file_path = project_root / kust_path
        if kust_file_path.is_file():
            kust_dir = kust_file_path.parent
        else:
            kust_dir = project_root / kust_path
            kust_file_path = None
            for kf_name in ("kustomization.yaml", "kustomization.yml", "Kustomization"):
                candidate = kust_dir / kf_name
                if candidate.is_file():
                    kust_file_path = candidate
                    break

        if kust_file_path and kust_file_path.is_file():
            try:
                kust_content = _yaml.safe_load(
                    kust_file_path.read_text(encoding="utf-8")
                ) or {}
                resources_list = kust_content.get("resources", []) or []
                if isinstance(resources_list, list):
                    listed = set(str(r) for r in resources_list if isinstance(r, str))
                    # Check for .yaml/.yml files in kust_dir not in resources
                    for f in sorted(kust_dir.iterdir()):
                        if (
                            f.is_file()
                            and f.suffix in (".yaml", ".yml")
                            and f.name not in (
                                "kustomization.yaml", "kustomization.yml",
                                "Kustomization",
                            )
                            and f.name not in listed
                        ):
                            issues.append({
                                "file": kust_path,
                                "severity": "warning",
                                "message": (
                                    f"Mixed: orphaned manifest '{f.name}' in "
                                    f"Kustomize directory but not listed in "
                                    f"resources — may be stale/unused"
                                ),
                            })
            except Exception:
                pass

    # ── 3. Mixed strategy undocumented ───────────────────────
    if deployment_strategy == "mixed":
        readme_found = any(
            (project_root / name).is_file()
            for name in (
                "README.md", "README.rst", "README.txt", "README",
                "docs/deployment.md", "docs/DEPLOYMENT.md",
                "DEPLOYMENT.md",
            )
        )
        if not readme_found:
            issues.append({
                "file": "deployment-strategy",
                "severity": "info",
                "message": (
                    f"Mixed: multiple deployment strategies detected "
                    f"but no README or deployment docs found — "
                    f"new contributors have no guide"
                ),
            })

    # ── 4. Helm + Kustomize without orchestrator ──────────────
    if has_helm and has_kustomize and not has_skaffold:
        # Check for ArgoCD/Flux markers
        has_argo = any(
            (project_root / d).is_dir()
            for d in ("argocd", ".argocd", "argo-cd")
        )
        has_flux = any(
            (project_root / d).is_dir()
            for d in ("flux", ".flux", "flux-system")
        )
        if not has_argo and not has_flux:
            issues.append({
                "file": "deployment-strategy",
                "severity": "info",
                "message": (
                    f"Mixed: both Helm and Kustomize active but no "
                    f"orchestrator (Skaffold/ArgoCD/Flux) detected — "
                    f"unclear which tool applies what"
                ),
            })

    # ── 5. Skaffold dual deployers ───────────────────────────
    if has_skaffold:
        try:
            skf = _yaml.safe_load(
                skaffold_file.read_text(encoding="utf-8")
            ) or {}
            if isinstance(skf, dict):
                skf_manifests = skf.get("manifests", {}) or {}
                skf_deploy = skf.get("deploy", {}) or {}
                has_raw_deploy = bool(skf_manifests.get("rawYaml"))
                has_helm_deploy = bool(skf_deploy.get("helm"))
                if has_raw_deploy and has_helm_deploy:
                    issues.append({
                        "file": "skaffold.yaml",
                        "severity": "warning",
                        "message": (
                            f"Skaffold: uses both Helm releases and rawYaml "
                            f"manifests — potential resource conflict in "
                            f"same namespace"
                        ),
                    })
        except Exception:
            pass
