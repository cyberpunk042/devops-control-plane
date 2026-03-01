"""K8s validation — Layer 1: Per-resource structural checks.

Validates individual resource structure: Deployment, Service, Pod spec,
StatefulSet, Job, CronJob, DaemonSet, Ingress, HPA.
"""

from __future__ import annotations

import re

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
