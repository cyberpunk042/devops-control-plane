"""K8s wizard detection — Skaffold status and namespace mapping."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def skaffold_status(project_root: Path) -> dict:
    """Detect Skaffold configuration.

    Returns:
        {
            "available": bool (CLI exists),
            "configs": [{path, profiles: [str]}],
            "has_skaffold": bool,
        }
    """
    import shutil
    import yaml

    cli_available = shutil.which("skaffold") is not None

    configs: list[dict] = []
    skaffold_files = [
        "skaffold.yaml", "skaffold.yml",
    ]

    for f in skaffold_files:
        p = project_root / f
        if p.is_file():
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8"))
                profiles = []
                if isinstance(data, dict) and "profiles" in data:
                    profiles = [
                        pr.get("name", "")
                        for pr in data["profiles"]
                        if isinstance(pr, dict) and pr.get("name")
                    ]
                configs.append({
                    "path": f,
                    "profiles": profiles,
                    "api_version": data.get("apiVersion", "") if isinstance(data, dict) else "",
                })
            except Exception:
                configs.append({"path": f, "profiles": [], "api_version": ""})

    return {
        "available": cli_available,
        "configs": configs,
        "has_skaffold": len(configs) > 0,
    }


# ═══════════════════════════════════════════════════════════════════
#  Multi-Environment Namespace Mapping
# ═══════════════════════════════════════════════════════════════════


def k8s_env_namespaces(project_root: Path) -> dict:
    """Map project environments to K8s namespaces.

    Reads project.yml environments and checks for env-specific
    namespace files or Kustomize overlays.

    Returns:
        {
            "environments": [{
                name, namespace, has_overlay, overlay_path
            }, ...],
        }
    """
    from src.core.config.loader import find_project_file, load_project

    config_path = find_project_file(project_root)
    if not config_path:
        return {"environments": []}

    project = load_project(config_path)
    envs: list[dict] = []

    for env in project.environments:
        name = env.name
        # Convention: namespace = project-name-env
        namespace = f"{project.name}-{name}" if project.name else name

        # Check for env-specific overlays
        overlay_paths = [
            f"k8s/overlays/{name}",
            f"k8s/envs/{name}",
            f"kubernetes/overlays/{name}",
            f"deploy/overlays/{name}",
        ]
        has_overlay = False
        overlay_path = ""
        for op in overlay_paths:
            if (project_root / op).is_dir():
                has_overlay = True
                overlay_path = op
                break

        # Check for env-specific values files (Helm)
        values_files = [
            f"values-{name}.yaml", f"values.{name}.yaml",
            f"helm/values-{name}.yaml", f"charts/values-{name}.yaml",
        ]
        values_file = ""
        for vf in values_files:
            if (project_root / vf).is_file():
                values_file = vf
                break

        envs.append({
            "name": name,
            "namespace": namespace,
            "default": env.default,
            "has_overlay": has_overlay,
            "overlay_path": overlay_path,
            "values_file": values_file,
        })

    return {"environments": envs}
