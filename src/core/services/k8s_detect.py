"""K8s manifest detection — offline scanning for YAML, Helm, Kustomize.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.services.k8s_common import _SKIP_DIRS, _MANIFEST_DIRS, _parse_k8s_yaml, _kubectl_available


logger = logging.getLogger(__name__)

def k8s_status(project_root: Path) -> dict:
    """Detect Kubernetes manifests and kubectl availability.

    Returns:
        {
            "has_k8s": bool,
            "kubectl": {available, version},
            "manifest_dirs": [str, ...],
            "manifests": [{path, resources}, ...],
            "resource_summary": {Deployment: 2, Service: 3, ...},
            "total_resources": int,
            "helm_charts": [{path, name}, ...],
            "kustomize": {exists, path},
        }
    """
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

    has_k8s = (
        len(manifests) > 0
        or len(helm_charts) > 0
        or kustomize.get("exists", False)
    )

    return {
        "has_k8s": has_k8s,
        "kubectl": kubectl,
        "manifest_dirs": manifest_dirs,
        "manifests": manifests,
        "resource_summary": resource_summary,
        "total_resources": total_resources,
        "helm_charts": helm_charts,
        "kustomize": kustomize,
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
    """Detect Helm charts (Chart.yaml)."""
    charts: list[dict] = []

    for chart_file in project_root.rglob("Chart.yaml"):
        skip = False
        for part in chart_file.relative_to(project_root).parts:
            if part in _SKIP_DIRS:
                skip = True
                break
        if skip:
            continue

        try:
            import yaml
            content = yaml.safe_load(chart_file.read_text(encoding="utf-8"))
            charts.append({
                "path": str(chart_file.parent.relative_to(project_root)),
                "name": content.get("name", "unknown"),
                "version": content.get("version", "0.0.0"),
                "description": content.get("description", ""),
            })
        except Exception:
            charts.append({
                "path": str(chart_file.parent.relative_to(project_root)),
                "name": "unknown",
            })

    return charts


def _detect_kustomize(project_root: Path) -> dict:
    """Detect Kustomize configuration."""
    for name in ("kustomization.yaml", "kustomization.yml", "Kustomization"):
        path = project_root / name
        if path.is_file():
            return {"exists": True, "path": name}

    # Check in sub-directories
    for d in _MANIFEST_DIRS:
        for name in ("kustomization.yaml", "kustomization.yml"):
            path = project_root / d / name
            if path.is_file():
                return {"exists": True, "path": f"{d}/{name}"}

    return {"exists": False}
