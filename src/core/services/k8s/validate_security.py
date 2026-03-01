"""K8s validation — Layer 5: Security & production readiness.

Pod security, RBAC, privilege checks, production readiness.
"""

from __future__ import annotations


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


