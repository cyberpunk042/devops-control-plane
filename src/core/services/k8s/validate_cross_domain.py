"""K8s validation — Layer 6: Cross-domain validation.

Docker ↔ K8s, Docker ↔ CI/CD, Docker ↔ Terraform, Terraform ↔ K8s,
Terraform ↔ CI/CD, CI/CD ↔ K8s, CI/CD ↔ Environments, cross-cutting.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.core.services.docker.detect import docker_status
from src.core.services.ci_ops import ci_status, ci_workflows
from src.core.services.terraform.ops import terraform_status
from .cluster import cluster_status


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


