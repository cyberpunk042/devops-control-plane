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
    ecosystem: str | None = None,
    module_path: str | None = None,
) -> dict[str, Any]:
    """Get sub-dependencies for a single package.

    Args:
        project_root: Project root.
        package: Package name (e.g. ``"flask"`` or ``"react"``).
        venv_path: Target venv for pip (e.g. ``".venv-ft"``). ``None`` = active.
        ecosystem: ``"pip"`` or ``"npm"``. Auto-detected if None.
        module_path: For npm — directory containing package.json (relative).

    Returns:
        Dict with ``name``, ``version``, ``requires`` (list of names),
        ``required_by`` (list of names), ``requires_detail`` (list of
        dicts with name + installed version), and ``location``.
    """
    # Detect ecosystem from package name heuristics if not specified
    if not ecosystem:
        if package.startswith("@") or module_path:
            ecosystem = "npm"
        else:
            ecosystem = "pip"

    if ecosystem == "npm":
        return _npm_deps(project_root, package, module_path)

    return _pip_deps(project_root, package, venv_path)


def _pip_deps(project_root: Path, package: str, venv_path: str | None) -> dict[str, Any]:
    """Get sub-dependencies for a pip package."""
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
    result["summary"] = raw.get("summary", "")
    result["home_page"] = raw.get("home_page", "")
    result["author"] = raw.get("author", "") or raw.get("author_email", "")
    result["license"] = raw.get("license_expression", "") or raw.get("license", "")

    requires_str = raw.get("requires", "")
    if requires_str:
        result["requires"] = [r.strip() for r in requires_str.split(",") if r.strip()]

    required_by_str = raw.get("required_by", "")
    if required_by_str:
        result["required_by"] = [r.strip() for r in required_by_str.split(",") if r.strip()]

    from .venv_info import get_installed_packages
    installed = get_installed_packages(project_root, venv_path)

    for req_name in result["requires"]:
        inst_ver = installed.get(req_name.lower(), "")
        result["requires_detail"].append({
            "name": req_name,
            "installed": inst_ver,
        })

    return result


def _npm_deps(project_root: Path, package: str, module_path: str | None) -> dict[str, Any]:
    """Get sub-dependencies for an npm package.

    Reads the package's own package.json from node_modules to get
    its declared dependencies. Uses npm ls for required-by info.
    """
    result = {
        "name": package,
        "version": "",
        "requires": [],
        "required_by": [],
        "requires_detail": [],
        "location": "",
    }

    base_dir = project_root / module_path if module_path else project_root
    node_modules = base_dir / "node_modules"

    # Read the package's own package.json from node_modules
    pkg_dir = node_modules / package
    pkg_json = pkg_dir / "package.json"

    if pkg_json.is_file():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            result["name"] = data.get("name", package)
            result["version"] = data.get("version", "")
            result["location"] = str(pkg_dir)

            # Its declared dependencies
            for dep_name, ver_spec in data.get("dependencies", {}).items():
                result["requires"].append(dep_name)
                # Check if installed in node_modules
                dep_pkg_json = node_modules / dep_name / "package.json"
                inst_ver = ""
                if dep_pkg_json.is_file():
                    try:
                        dep_data = json.loads(dep_pkg_json.read_text(encoding="utf-8"))
                        inst_ver = dep_data.get("version", "")
                    except Exception:
                        pass
                result["requires_detail"].append({
                    "name": dep_name,
                    "installed": inst_ver,
                    "version_spec": ver_spec,
                })
        except (json.JSONDecodeError, OSError):
            pass

    # Required-by: use npm ls to find reverse deps
    try:
        r = subprocess.run(
            ["npm", "ls", "--json", "--depth=0"],
            capture_output=True, text=True, timeout=10,
            cwd=str(base_dir),
        )
        if r.returncode in (0, 1) and r.stdout.strip():
            ls_data = json.loads(r.stdout)
            # Check which top-level packages have this as a dependency
            for top_name, top_info in ls_data.get("dependencies", {}).items():
                if top_name == package:
                    continue
                # Read the top-level package's package.json to check its deps
                top_pkg_json = node_modules / top_name / "package.json"
                if top_pkg_json.is_file():
                    try:
                        top_data = json.loads(top_pkg_json.read_text(encoding="utf-8"))
                        all_deps = {}
                        all_deps.update(top_data.get("dependencies", {}))
                        all_deps.update(top_data.get("peerDependencies", {}))
                        if package in all_deps:
                            result["required_by"].append(top_name)
                    except Exception:
                        pass
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        pass

    return result


def get_package_deps_batch(
    project_root: Path,
    packages: list[str],
    venv_path: str | None = None,
    installed: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Get sub-dependencies for multiple packages at once.

    Uses a single ``pip show`` subprocess for all packages (batch mode).

    Args:
        project_root: Project root.
        packages: List of package names.
        venv_path: Target venv (e.g. ``".venv-ft"``). ``None`` = active.
        installed: Pre-fetched installed packages dict. If ``None``,
            calls ``get_installed_packages()`` internally.

    Returns:
        Dict mapping package name → deps info.
    """
    if installed is None:
        from .venv_info import get_installed_packages
        installed = get_installed_packages(project_root, venv_path)

    # Batch pip show — one subprocess for all packages
    batch = _pip_show_batch(project_root, packages, venv_path)

    results = {}
    for pkg in packages:
        raw = batch.get(pkg.lower())
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
            "summary": raw.get("summary", ""),
            "home_page": raw.get("home_page", ""),
            "author": raw.get("author", "") or raw.get("author_email", ""),
            "license": raw.get("license_expression", "") or raw.get("license", ""),
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


def _pip_show_batch(
    project_root: Path,
    packages: list[str],
    venv_path: str | None,
) -> dict[str, dict[str, str]]:
    """Run ``pip show`` for ALL packages in one subprocess call.

    Returns dict mapping ``package_name_lower`` → parsed pip-show dict.
    Much faster than calling ``_pip_show`` per package (1 subprocess vs N).
    """
    if not packages:
        return {}

    # Determine python binary (same logic as _pip_show)
    if venv_path == "system":
        from .venv_info import _find_system_python
        python_bin = _find_system_python() or sys.executable
    elif venv_path:
        python_bin = str(project_root / venv_path / "bin" / "python")
    else:
        python_bin = sys.executable

    # Try pip show with all packages at once
    try:
        r = subprocess.run(
            [python_bin, "-m", "pip", "show"] + list(packages),
            capture_output=True, text=True, timeout=30,
            cwd=str(project_root),
        )
        if r.returncode == 0 and r.stdout.strip():
            return _parse_pip_show_batch(r.stdout)
    except (subprocess.TimeoutExpired, OSError):
        pass

    # Fallback: uv pip show with all packages
    try:
        import shutil
        if not shutil.which("uv"):
            return {}

        env = os.environ.copy()
        if venv_path and venv_path != "system":
            env["VIRTUAL_ENV"] = str(project_root / venv_path)
        elif not venv_path:
            prefix = Path(sys.prefix)
            if prefix != Path(sys.base_prefix):
                env["VIRTUAL_ENV"] = str(prefix)

        r = subprocess.run(
            ["uv", "pip", "show"] + list(packages),
            capture_output=True, text=True, timeout=30,
            cwd=str(project_root), env=env,
        )
        if r.returncode == 0 and r.stdout.strip():
            return _parse_pip_show_batch(r.stdout)
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        pass

    return {}


def _parse_pip_show_batch(output: str) -> dict[str, dict[str, str]]:
    """Parse multi-package ``pip show`` output (``---``-separated sections).

    Returns dict mapping ``name.lower()`` → parsed key-value dict.
    """
    results: dict[str, dict[str, str]] = {}
    sections = output.strip().split("---")
    for section in sections:
        section = section.strip()
        if not section:
            continue
        parsed = _parse_pip_show(section)
        name = parsed.get("name", "")
        if name:
            results[name.lower()] = parsed
    return results


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
