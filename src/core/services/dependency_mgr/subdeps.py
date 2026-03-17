"""
Sub-dependency resolution — shows what each package pulls in.

Uses ``uv pip show`` or ``pip show`` to get per-package dependency
info: what it requires (children) and what requires it (parents).

Usage::

    deps = get_package_deps(project_root, "flask", venv_path=".venv-ft")
    # deps = {
    #     "name": "flask",
    #     "version": "3.1.3",
    #     "requires": ["werkzeug", "jinja2", "click", ...],
    #     "required_by": ["devops-control-plane"],
    # }
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_package_deps(
    project_root: Path,
    package: str,
    venv_path: str | None = None,
) -> dict[str, Any]:
    """Get sub-dependencies for a single package.

    Args:
        project_root: Project root.
        package: Package name (e.g. ``"flask"``).
        venv_path: Target venv (e.g. ``".venv-ft"``). ``None`` = active.

    Returns:
        Dict with ``name``, ``version``, ``requires`` (list of names),
        ``required_by`` (list of names), ``requires_detail`` (list of
        dicts with name + version_spec), and ``location``.
    """
    result = {
        "name": package,
        "version": "",
        "requires": [],
        "required_by": [],
        "requires_detail": [],
        "location": "",
    }

    raw = _pip_show(project_root, package, venv_path)
    if not raw:
        return result

    result["name"] = raw.get("name", package)
    result["version"] = raw.get("version", "")
    result["location"] = raw.get("location", "")

    # Parse Requires field — comma-separated package names
    requires_str = raw.get("requires", "")
    if requires_str:
        result["requires"] = [r.strip() for r in requires_str.split(",") if r.strip()]

    # Parse Required-by field
    required_by_str = raw.get("required_by", "")
    if required_by_str:
        result["required_by"] = [r.strip() for r in required_by_str.split(",") if r.strip()]

    # Enrich requires with installed versions
    from .venv_info import get_installed_packages
    installed = get_installed_packages(project_root, venv_path)

    for req_name in result["requires"]:
        inst_ver = installed.get(req_name.lower(), "")
        result["requires_detail"].append({
            "name": req_name,
            "installed": inst_ver,
        })

    return result


def get_package_deps_batch(
    project_root: Path,
    packages: list[str],
    venv_path: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Get sub-dependencies for multiple packages at once.

    More efficient than calling ``get_package_deps`` in a loop
    because it shares the installed packages lookup.

    Returns:
        Dict mapping package name → deps info.
    """
    from .venv_info import get_installed_packages
    installed = get_installed_packages(project_root, venv_path)

    results = {}
    for pkg in packages:
        raw = _pip_show(project_root, pkg, venv_path)
        if not raw:
            results[pkg] = {"name": pkg, "version": "", "requires": [],
                            "required_by": [], "requires_detail": [], "location": ""}
            continue

        requires_str = raw.get("requires", "")
        requires = [r.strip() for r in requires_str.split(",") if r.strip()] if requires_str else []

        required_by_str = raw.get("required_by", "")
        required_by = [r.strip() for r in required_by_str.split(",") if r.strip()] if required_by_str else []

        requires_detail = []
        for req_name in requires:
            requires_detail.append({
                "name": req_name,
                "installed": installed.get(req_name.lower(), ""),
            })

        results[pkg] = {
            "name": raw.get("name", pkg),
            "version": raw.get("version", ""),
            "requires": requires,
            "required_by": required_by,
            "requires_detail": requires_detail,
            "location": raw.get("location", ""),
        }

    return results


def _pip_show(project_root: Path, package: str, venv_path: str | None) -> dict[str, str] | None:
    """Run pip show and parse the output into a dict."""
    # Determine python binary
    if venv_path == "system":
        from .venv_info import _find_system_python
        python_bin = _find_system_python() or sys.executable
    elif venv_path:
        python_bin = str(project_root / venv_path / "bin" / "python")
    else:
        python_bin = sys.executable

    # Try pip show
    try:
        r = subprocess.run(
            [python_bin, "-m", "pip", "show", package],
            capture_output=True, text=True, timeout=10,
            cwd=str(project_root),
        )
        if r.returncode == 0 and r.stdout.strip():
            return _parse_pip_show(r.stdout)
    except (subprocess.TimeoutExpired, OSError):
        pass

    # Fallback: uv pip show
    try:
        import shutil
        if not shutil.which("uv"):
            return None

        env = os.environ.copy()
        if venv_path and venv_path != "system":
            env["VIRTUAL_ENV"] = str(project_root / venv_path)
        elif not venv_path:
            prefix = Path(sys.prefix)
            if prefix != Path(sys.base_prefix):
                env["VIRTUAL_ENV"] = str(prefix)

        r = subprocess.run(
            ["uv", "pip", "show", package],
            capture_output=True, text=True, timeout=10,
            cwd=str(project_root), env=env,
        )
        if r.returncode == 0 and r.stdout.strip():
            return _parse_pip_show(r.stdout)
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        pass

    return None


def _parse_pip_show(output: str) -> dict[str, str]:
    """Parse ``pip show`` output into a dict.

    Format::

        Name: flask
        Version: 3.1.3
        Location: /path/to/site-packages
        Requires: werkzeug, jinja2, click
        Required-by: devops-control-plane
    """
    result: dict[str, str] = {}
    for line in output.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            # Normalize key: "Required-by" → "required_by"
            norm_key = key.strip().lower().replace("-", "_")
            result[norm_key] = value.strip()
    return result
