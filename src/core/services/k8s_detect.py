"""K8s manifest detection — offline scanning for YAML, Helm, Kustomize.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

from src.core.services.k8s_common import _SKIP_DIRS, _MANIFEST_DIRS, _parse_k8s_yaml, _kubectl_available


logger = logging.getLogger(__name__)


# Version command specs for each CLI tool.
# Each entry: (args, parser) where parser extracts version from stdout.
_CLI_VERSION_SPECS: dict[str, tuple[list[str], str]] = {
    # K8s tools
    "helm":      (["helm", "version", "--short"],    r"(v[\d]+\.[\d]+\.[\d]+)"),
    "kustomize": (["kustomize", "version"],          r"(v[\d]+\.[\d]+\.[\d]+)"),
    "skaffold":  (["skaffold", "version"],            r"(v[\d]+\.[\d]+\.[\d]+)"),
    "minikube":  (["minikube", "version", "--short"], r"(v[\d]+\.[\d]+\.[\d]+)"),
    "kind":      (["kind", "version"],                r"(v[\d]+\.[\d]+\.[\d]+)"),
    # Cloud CLIs
    "az":        (["az", "version", "-o", "json"],    r'"azure-cli":\s*"([\d]+\.[\d]+\.[\d]+)"'),
    "aws":       (["aws", "--version"],               r"aws-cli/([\d]+\.[\d]+\.[\d]+)"),
    "gcloud":    (["gcloud", "version"],              r"Google Cloud SDK ([\d]+\.[\d]+\.[\d]+)"),
}


def _detect_cli(name: str) -> dict:
    """Check if a CLI tool is available on PATH and extract its version.

    Returns:
        {"available": bool, "version": str | None}
    """
    if shutil.which(name) is None:
        return {"available": False, "version": None}

    spec = _CLI_VERSION_SPECS.get(name)
    if spec is None:
        # Unknown tool — available but no version extractor
        return {"available": True, "version": None}

    args, pattern = spec
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            match = re.search(pattern, result.stdout)
            if match:
                return {"available": True, "version": match.group(1)}
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # Binary exists but version extraction failed
    return {"available": True, "version": None}

def k8s_status(project_root: Path) -> dict:
    """Detect Kubernetes manifests and kubectl availability.

    Returns a comprehensive status covering:
    - Resource inventory (manifests, helm_charts, kustomize)
    - Deployment strategy detection
    - Unified environment map
    - Readiness assessment
    - Infrastructure service detection
    """
    import re

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
    all_parsed_resources: list[dict] = []  # for infra detection

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
                all_parsed_resources.append(res)
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

    has_manifests = len(manifests) > 0
    has_helm = len(helm_charts) > 0
    has_kustomize = kustomize.get("exists", False)

    has_k8s = has_manifests or has_helm or has_kustomize

    # ── Deployment strategy detection ─────────────────────────────

    strategies_detected: list[str] = []
    if has_manifests:
        strategies_detected.append("raw_kubectl")
    if has_helm:
        strategies_detected.append("helm")
    if has_kustomize:
        strategies_detected.append("kustomize")
    # NOTE: skaffold detection requires separate check (0.2.2e)

    if not strategies_detected:
        deployment_strategy = "none"
    elif len(strategies_detected) == 1:
        deployment_strategy = strategies_detected[0]
    else:
        deployment_strategy = "mixed"

    # ── Unified environment map ───────────────────────────────────

    environments: list[dict] = []
    seen_envs: set[str] = set()

    # From Kustomize overlays
    if has_kustomize:
        overlay_details = kustomize.get("overlay_details", [])
        for ov in overlay_details:
            env_name = ov["name"]
            if env_name not in seen_envs:
                env_entry: dict = {
                    "name": env_name,
                    "source": "kustomize_overlay",
                }
                # Parse the overlay's kustomization for namespace
                kust_dir = _find_kustomize_dir(project_root, kustomize.get("path", ""))
                if kust_dir:
                    overlay_kust = kust_dir / "overlays" / env_name
                    ns = _read_kustomize_namespace(overlay_kust)
                    if ns:
                        env_entry["namespace"] = ns
                environments.append(env_entry)
                seen_envs.add(env_name)

    # From Helm values files
    for chart in helm_charts:
        for vf in chart.get("env_values_files", []):
            # values-dev.yaml → env name "dev"
            match = re.match(r"values-(.+)\.ya?ml$", vf)
            if match:
                env_name = match.group(1)
                if env_name not in seen_envs:
                    environments.append({
                        "name": env_name,
                        "source": "helm_values",
                    })
                    seen_envs.add(env_name)

    # ── Secret safety assessment ──────────────────────────────────

    # Check for raw Secrets in parsed resources
    has_raw_secrets = any(
        r.get("kind") == "Secret" for r in all_parsed_resources
    )
    # Also check Kustomize analysis
    if kustomize.get("has_raw_secrets"):
        has_raw_secrets = True

    has_envsubst_vars = kustomize.get("has_envsubst_vars", False)
    envsubst_vars = kustomize.get("envsubst_vars", [])
    has_secret_generator = kustomize.get("has_secret_generator", False)

    secret_safety = {
        "has_raw_secrets": has_raw_secrets,
        "has_envsubst_vars": has_envsubst_vars,
        "envsubst_vars": envsubst_vars,
        "has_secret_generator": has_secret_generator,
    }

    # ── Tool availability ─────────────────────────────────────────

    tool_availability = {
        # Core K8s tool
        "kubectl": kubectl,
        # K8s deployment tools
        "helm": _detect_cli("helm"),
        "kustomize": _detect_cli("kustomize"),
        "skaffold": _detect_cli("skaffold"),
        # Local cluster tools
        "minikube": _detect_cli("minikube"),
        "kind": _detect_cli("kind"),
        # Cloud CLIs (authentication for managed clusters)
        "az": _detect_cli("az"),
        "aws": _detect_cli("aws"),
        "gcloud": _detect_cli("gcloud"),
    }

    # ── Deployment readiness ──────────────────────────────────────

    if not has_k8s:
        deployment_readiness = "not_configured"
    elif not kubectl.get("available", False):
        deployment_readiness = "needs_tools"
    elif has_raw_secrets or has_envsubst_vars:
        deployment_readiness = "needs_config"
    else:
        deployment_readiness = "ready"

    # ── Infrastructure service detection ──────────────────────────

    infra_services = _detect_infra_services(all_parsed_resources, helm_charts)

    return {
        "has_k8s": has_k8s,
        "kubectl": kubectl,
        "manifest_dirs": manifest_dirs,
        "manifests": manifests,
        "resource_summary": resource_summary,
        "total_resources": total_resources,
        "helm_charts": helm_charts,
        "kustomize": kustomize,
        "deployment_strategy": deployment_strategy,
        "strategies_detected": strategies_detected,
        "environments": environments,
        "tool_availability": tool_availability,
        "secret_safety": secret_safety,
        "deployment_readiness": deployment_readiness,
        "infra_services": infra_services,
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
    """Detect Helm charts (Chart.yaml) with full structure analysis.

    Returns list of dicts with:
        path, name, version, description, app_version, type,
        has_values, has_templates, has_subcharts, has_lockfile,
        env_values_files
    """
    charts: list[dict] = []

    for chart_file in project_root.rglob("Chart.yaml"):
        skip = False
        for part in chart_file.relative_to(project_root).parts:
            if part in _SKIP_DIRS:
                skip = True
                break
        if skip:
            continue

        chart_dir = chart_file.parent
        rel_path = str(chart_dir.relative_to(project_root))

        try:
            import yaml
            content = yaml.safe_load(chart_file.read_text(encoding="utf-8"))

            # Detect chart structure next to Chart.yaml
            has_values = (chart_dir / "values.yaml").is_file()
            has_templates = (chart_dir / "templates").is_dir()
            has_subcharts = (chart_dir / "charts").is_dir()
            has_lockfile = (chart_dir / "Chart.lock").is_file()

            # Detect env-specific values files (values-{env}.yaml)
            env_values: list[str] = []
            for f in sorted(chart_dir.iterdir()):
                if (
                    f.is_file()
                    and f.name.startswith("values-")
                    and f.suffix in (".yaml", ".yml")
                ):
                    env_values.append(f.name)

            charts.append({
                "path": rel_path,
                "name": content.get("name", "unknown"),
                "version": content.get("version", "0.0.0"),
                "description": content.get("description", ""),
                "app_version": str(content.get("appVersion", "")),
                "type": content.get("type", "application"),
                "has_values": has_values,
                "has_templates": has_templates,
                "has_subcharts": has_subcharts,
                "has_lockfile": has_lockfile,
                "env_values_files": env_values,
            })
        except Exception:
            charts.append({
                "path": rel_path,
                "name": "unknown",
            })

    return charts


def _detect_kustomize(project_root: Path) -> dict:
    """Detect Kustomize configuration with full content analysis.

    Returns:
        {exists, path, overlays, overlay_count, overlay_details,
         has_bases, mode, has_patches, patch_types,
         has_config_map_generator, config_map_generator_count,
         has_secret_generator, secret_generator_count,
         has_raw_secrets, has_envsubst_vars, envsubst_vars,
         has_vars, has_image_overrides, image_override_count,
         namespace, name_prefix, name_suffix}
        or {exists: False} if not found.
    """
    import re

    kustomize_path: str | None = None
    kustomize_dir: Path | None = None

    # Check root first
    for name in ("kustomization.yaml", "kustomization.yml", "Kustomization"):
        path = project_root / name
        if path.is_file():
            kustomize_path = name
            kustomize_dir = project_root
            break

    # Check in sub-directories
    if kustomize_path is None:
        for d in _MANIFEST_DIRS:
            for name in ("kustomization.yaml", "kustomization.yml"):
                path = project_root / d / name
                if path.is_file():
                    kustomize_path = f"{d}/{name}"
                    kustomize_dir = project_root / d
                    break
            if kustomize_path is not None:
                break

    if kustomize_path is None:
        return {"exists": False}

    # Analyze structure around the kustomization file
    assert kustomize_dir is not None

    # Parse the kustomization file content
    kustomize_file = kustomize_dir / kustomize_path.split("/")[-1]
    content: dict = {}
    try:
        import yaml
        raw = kustomize_file.read_text(encoding="utf-8", errors="ignore")
        loaded = yaml.safe_load(raw)
        if isinstance(loaded, dict):
            content = loaded
    except Exception:
        pass

    # Detect overlays (per-environment subdirs with their own kustomization)
    overlays: list[str] = []
    overlay_details: list[dict] = []
    overlays_dir = kustomize_dir / "overlays"
    if overlays_dir.is_dir():
        for entry in sorted(overlays_dir.iterdir()):
            if entry.is_dir():
                # Check if the overlay has its own kustomization file
                overlay_kustomization = None
                for n in ("kustomization.yaml", "kustomization.yml", "Kustomization"):
                    if (entry / n).is_file():
                        overlay_kustomization = entry / n
                        break
                if overlay_kustomization is not None:
                    overlays.append(entry.name)
                    # Parse overlay for details
                    overlay_info: dict = {"name": entry.name, "patch_count": 0}
                    try:
                        overlay_data = yaml.safe_load(
                            overlay_kustomization.read_text(encoding="utf-8", errors="ignore")
                        )
                        if isinstance(overlay_data, dict):
                            overlay_info["patch_count"] = _count_patches(overlay_data)
                    except Exception:
                        pass
                    overlay_details.append(overlay_info)

    # Detect bases directory
    has_bases = (kustomize_dir / "base").is_dir()

    # Determine mode
    mode = "multi" if overlays else "single"

    # ── Content analysis ──────────────────────────────────────────

    # Patches
    patch_types: list[str] = []
    for pt in ("patchesStrategicMerge", "patchesJson6902", "patches"):
        if content.get(pt):
            patch_types.append(pt)
    has_patches = len(patch_types) > 0

    # Generators
    cm_gen = content.get("configMapGenerator", [])
    secret_gen = content.get("secretGenerator", [])
    has_config_map_generator = bool(cm_gen)
    has_secret_generator = bool(secret_gen)

    # Scan referenced resource files for raw Secrets and envsubst vars
    has_raw_secrets = False
    envsubst_vars: list[str] = []
    resources = content.get("resources", [])
    if isinstance(resources, list):
        for res_ref in resources:
            if not isinstance(res_ref, str):
                continue
            res_path = kustomize_dir / res_ref
            if res_path.is_file():
                try:
                    res_text = res_path.read_text(encoding="utf-8", errors="ignore")
                    # Check for raw Secret kind
                    try:
                        for doc in yaml.safe_load_all(res_text):
                            if (
                                isinstance(doc, dict)
                                and doc.get("kind") == "Secret"
                            ):
                                has_raw_secrets = True
                    except Exception:
                        pass
                    # Check for ${VAR} patterns (envsubst)
                    found_vars = re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", res_text)
                    envsubst_vars.extend(found_vars)
                except OSError:
                    pass

    envsubst_vars = sorted(set(envsubst_vars))
    has_envsubst_vars = len(envsubst_vars) > 0

    # vars / replacements
    has_vars = bool(content.get("vars")) or bool(content.get("replacements"))

    # Image overrides
    images = content.get("images", [])
    has_image_overrides = bool(images) and isinstance(images, list)
    image_override_count = len(images) if isinstance(images, list) else 0

    # Namespace override
    ns = content.get("namespace", "")

    # Name transformations
    name_prefix = content.get("namePrefix", "")
    name_suffix = content.get("nameSuffix", "")

    result: dict = {
        "exists": True,
        "path": kustomize_path,
        "overlays": overlays,
        "overlay_count": len(overlays),
        "overlay_details": overlay_details,
        "has_bases": has_bases,
        "mode": mode,
        "has_patches": has_patches,
        "patch_types": patch_types,
        "has_config_map_generator": has_config_map_generator,
        "config_map_generator_count": len(cm_gen) if isinstance(cm_gen, list) else 0,
        "has_secret_generator": has_secret_generator,
        "secret_generator_count": len(secret_gen) if isinstance(secret_gen, list) else 0,
        "has_raw_secrets": has_raw_secrets,
        "has_envsubst_vars": has_envsubst_vars,
        "envsubst_vars": envsubst_vars,
        "has_vars": has_vars,
        "has_image_overrides": has_image_overrides,
        "image_override_count": image_override_count,
    }

    # Only include these if they have values (keep dict clean)
    if ns:
        result["namespace"] = ns
    if name_prefix:
        result["name_prefix"] = name_prefix
    if name_suffix:
        result["name_suffix"] = name_suffix

    return result


def _count_patches(kustomize_data: dict) -> int:
    """Count total patches in a kustomization dict."""
    count = 0
    for key in ("patchesStrategicMerge", "patchesJson6902", "patches"):
        val = kustomize_data.get(key, [])
        if isinstance(val, list):
            count += len(val)
    return count


def _find_kustomize_dir(project_root: Path, kustomize_path: str) -> Path | None:
    """Resolve the directory containing the kustomization file."""
    if not kustomize_path:
        return None
    # kustomize_path is like "kustomization.yaml" or "k8s/kustomization.yaml"
    parts = kustomize_path.split("/")
    if len(parts) == 1:
        return project_root
    return project_root / "/".join(parts[:-1])


def _read_kustomize_namespace(overlay_dir: Path) -> str:
    """Read the namespace field from a kustomization file in a directory."""
    import yaml

    for name in ("kustomization.yaml", "kustomization.yml", "Kustomization"):
        kf = overlay_dir / name
        if kf.is_file():
            try:
                data = yaml.safe_load(kf.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(data, dict):
                    return data.get("namespace", "")
            except Exception:
                pass
    return ""


# Known infrastructure Helm chart names
_INFRA_CHART_NAMES = frozenset({
    "ingress-nginx", "traefik", "ambassador", "haproxy-ingress",
    "cert-manager",
    "prometheus", "grafana", "datadog", "kube-prometheus-stack",
    "istio", "linkerd",
    "longhorn", "rook-ceph",
    "external-secrets", "sealed-secrets", "vault",
    "metallb", "calico", "cilium",
    "argo-cd", "argocd", "flux",
})

# Resource kinds that imply infrastructure requirements
_INFRA_KIND_MAP: dict[str, str] = {
    "Ingress": "ingress-controller",
    "Certificate": "cert-manager",
    "ClusterIssuer": "cert-manager",
    "Issuer": "cert-manager",
    "ServiceMonitor": "prometheus",
    "PrometheusRule": "prometheus",
    "PodMonitor": "prometheus",
    "Gateway": "gateway-api",
    "HTTPRoute": "gateway-api",
}

# Annotation prefixes that imply infrastructure requirements
_INFRA_ANNOTATION_PREFIXES: dict[str, str] = {
    "cert-manager.io/": "cert-manager",
    "prometheus.io/": "prometheus",
    "nginx.ingress.kubernetes.io/": "ingress-nginx",
}


def _detect_infra_services(
    parsed_resources: list[dict], helm_charts: list[dict]
) -> list[dict]:
    """Detect infrastructure service requirements from resources and charts."""
    infra: dict[str, dict] = {}  # name → {name, detected_via}

    # From resource kinds
    for res in parsed_resources:
        kind = res.get("kind", "")
        if kind in _INFRA_KIND_MAP:
            svc_name = _INFRA_KIND_MAP[kind]
            if svc_name not in infra:
                infra[svc_name] = {
                    "name": svc_name,
                    "detected_via": "resource_kind",
                }

        # From annotations
        annotations = res.get("metadata", {}).get("annotations", {})
        if isinstance(annotations, dict):
            for anno_key in annotations:
                for prefix, svc_name in _INFRA_ANNOTATION_PREFIXES.items():
                    if anno_key.startswith(prefix) and svc_name not in infra:
                        infra[svc_name] = {
                            "name": svc_name,
                            "detected_via": "manifest_annotation",
                        }

    # From Helm charts with known infra names
    for chart in helm_charts:
        chart_name = chart.get("name", "")
        if chart_name in _INFRA_CHART_NAMES:
            if chart_name not in infra:
                infra[chart_name] = {
                    "name": chart_name,
                    "detected_via": "helm_chart",
                }

    return sorted(infra.values(), key=lambda x: x["name"])
