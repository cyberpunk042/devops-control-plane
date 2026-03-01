"""K8s validation — Layer 3: Environment-aware checks.

Validates environment-specific configuration: prod safety, dev convenience,
namespace mapping, resource scaling.
"""

from __future__ import annotations

from pathlib import Path

from .wizard_detect import k8s_env_namespaces



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


