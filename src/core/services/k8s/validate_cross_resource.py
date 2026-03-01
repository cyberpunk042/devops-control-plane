"""K8s validation — Layer 2: Cross-resource consistency.

Validates consistency across resources: selector ↔ label matching,
port alignment, ConfigMap/Secret/PVC references, namespace consistency.
"""

from __future__ import annotations


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

