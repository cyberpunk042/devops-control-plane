"""Helm operations — list, install, upgrade, template.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path


logger = logging.getLogger(__name__)

def _helm_available() -> bool:
    """Check if helm CLI is available."""
    import shutil
    return shutil.which("helm") is not None


def helm_list(project_root: Path, *, namespace: str = "") -> dict:
    """List installed Helm releases.

    Returns:
        {"available": True, "releases": [{name, namespace, revision, status, chart, app_version}, ...]}
    """
    if not _helm_available():
        return {"available": False, "error": "helm CLI not found"}

    cmd = ["helm", "list", "--output", "json"]
    if namespace:
        cmd.extend(["--namespace", namespace])
    else:
        cmd.append("--all-namespaces")

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=project_root)
        if r.returncode != 0:
            return {"available": True, "releases": [], "error": r.stderr.strip()}

        import json
        releases = json.loads(r.stdout) if r.stdout.strip() else []
        return {"available": True, "releases": releases}
    except Exception as e:
        return {"available": True, "releases": [], "error": str(e)}


def helm_values(project_root: Path, release: str, *, namespace: str = "") -> dict:
    """Get values for a Helm release.

    Returns:
        {"ok": True, "values": str (YAML)} or {"error": "..."}
    """
    if not _helm_available():
        return {"error": "helm CLI not found"}

    cmd = ["helm", "get", "values", release, "--output", "yaml"]
    if namespace:
        cmd.extend(["--namespace", namespace])

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=project_root)
        if r.returncode != 0:
            return {"error": r.stderr.strip() or "Failed to get values"}
        return {"ok": True, "values": r.stdout, "release": release}
    except Exception as e:
        return {"error": str(e)}


def helm_install(
    project_root: Path,
    release: str,
    chart: str,
    *,
    namespace: str = "",
    values_file: str = "",
    set_values: dict | None = None,
    dry_run: bool = False,
) -> dict:
    """Install a Helm chart.

    Returns:
        {"ok": True, "output": str} or {"error": "..."}
    """
    if not _helm_available():
        return {"error": "helm CLI not found"}

    cmd = ["helm", "install", release, chart]
    if namespace:
        cmd.extend(["--namespace", namespace, "--create-namespace"])
    if values_file:
        cmd.extend(["--values", values_file])
    if set_values:
        for k, v in set_values.items():
            cmd.extend(["--set", f"{k}={v}"])
    if dry_run:
        cmd.append("--dry-run")

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=project_root)
        if r.returncode != 0:
            return {"error": r.stderr.strip() or "Helm install failed"}
        return {"ok": True, "output": r.stdout}
    except Exception as e:
        return {"error": str(e)}


def helm_upgrade(
    project_root: Path,
    release: str,
    chart: str,
    *,
    namespace: str = "",
    values_file: str = "",
    set_values: dict | None = None,
    dry_run: bool = False,
) -> dict:
    """Upgrade a Helm release.

    Returns:
        {"ok": True, "output": str} or {"error": "..."}
    """
    if not _helm_available():
        return {"error": "helm CLI not found"}

    cmd = ["helm", "upgrade", release, chart, "--install"]
    if namespace:
        cmd.extend(["--namespace", namespace])
    if values_file:
        cmd.extend(["--values", values_file])
    if set_values:
        for k, v in set_values.items():
            cmd.extend(["--set", f"{k}={v}"])
    if dry_run:
        cmd.append("--dry-run")

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=project_root)
        if r.returncode != 0:
            return {"error": r.stderr.strip() or "Helm upgrade failed"}
        return {"ok": True, "output": r.stdout}
    except Exception as e:
        return {"error": str(e)}


def helm_template(
    project_root: Path,
    release: str,
    chart: str,
    *,
    namespace: str = "",
    values_file: str = "",
) -> dict:
    """Render Helm templates locally (dry-run without cluster).

    Returns:
        {"ok": True, "output": str (rendered YAML)} or {"error": "..."}
    """
    if not _helm_available():
        return {"error": "helm CLI not found"}

    cmd = ["helm", "template", release, chart]
    if namespace:
        cmd.extend(["--namespace", namespace])
    if values_file:
        cmd.extend(["--values", values_file])

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=project_root)
        if r.returncode != 0:
            return {"error": r.stderr.strip() or "Helm template failed"}
        return {"ok": True, "output": r.stdout}
    except Exception as e:
        return {"error": str(e)}
