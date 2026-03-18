"""
Dependency compatibility checker — queries PyPI for Requires-Python.

Scans the module's imports, maps them to package names via dist-info,
then queries PyPI JSON API to check if each package supports the
target Python version.

This is a read-only operation — both preview and execute return the
same compatibility report. Nothing is modified.

Pattern reused from the existing module-dep-alternatives endpoint.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..context import UpgradeContext

logger = logging.getLogger(__name__)

_PYPI_TIMEOUT = 10  # seconds per package query


def handle_check_dep_compat_pypi(ctx: UpgradeContext, mode: str) -> dict:
    """Check if the module's dependencies support the target Python version.

    Both preview and execute do the same thing: scan imports, query PyPI,
    return a compatibility report. This is read-only.
    """
    if ctx.language != "python":
        return {
            "ok": True,
            "can_apply": False,
            "preview_type": "info",
            "summary": "Dependency checking only available for Python",
        }

    # ── Scan module imports ──────────────────────────────────────
    try:
        from src.core.services.system_posture.bridges.module_intel import (
            _build_import_mapping,
            _find_site_packages,
            _scan_module_imports,
        )

        module_dir = ctx.project_root / ctx.module_path
        if not module_dir.is_dir():
            return {"ok": False, "error": f"Module directory not found: {ctx.module_path}"}

        module_imports = _scan_module_imports(module_dir)
        if not module_imports:
            return {
                "ok": True,
                "can_apply": False,
                "preview_type": "findings",
                "summary": "No third-party imports found",
                "findings": [],
            }

        site_packages = _find_site_packages(ctx.project_root)
        if not site_packages:
            return {"ok": False, "error": "Could not find site-packages directory"}

        import_to_pkg = _build_import_mapping(site_packages)

        # Map imports to package names
        packages: set[str] = set()
        for imp in module_imports:
            if imp in import_to_pkg:
                packages.add(import_to_pkg[imp])
            else:
                packages.add(imp)

    except Exception as exc:
        return {"ok": False, "error": f"Failed to scan imports: {exc}"}

    # ── Query PyPI for each package ──────────────────────────────
    target_parts = _parse_version(ctx.target_floor)
    if not target_parts:
        return {"ok": False, "error": f"Cannot parse target version: {ctx.target_floor}"}

    findings = []
    errors = []

    for pkg_name in sorted(packages):
        pkg_normalized = pkg_name.lower().replace("_", "-")
        result = _check_package_compat(pkg_normalized, target_parts, ctx.target_floor)
        if result:
            findings.append(result)
        # Errors are logged but don't stop the process

    compatible_count = sum(1 for f in findings if f["compatible"])
    incompatible_count = sum(1 for f in findings if not f["compatible"])
    unknown_count = sum(1 for f in findings if f.get("unknown"))

    all_ok = incompatible_count == 0

    return {
        "ok": True,
        "can_apply": False,  # read-only operation
        "preview_type": "findings",
        "summary": (
            f"All {compatible_count} checked dependencies support Python {ctx.target_floor}"
            if all_ok
            else f"{incompatible_count} of {len(findings)} dependencies may not support Python {ctx.target_floor}"
        ),
        "findings": findings,
        "compatible_count": compatible_count,
        "incompatible_count": incompatible_count,
        "unknown_count": unknown_count,
        "all_compatible": all_ok,
    }


def _check_package_compat(
    package: str,
    target_parts: list[int],
    target_str: str,
) -> dict | None:
    """Check a single package's Python version compatibility via PyPI.

    Returns a finding dict, or None if the package can't be checked.
    """
    try:
        url = f"https://pypi.org/pypi/{package}/json"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=_PYPI_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except Exception as exc:
        logger.debug("PyPI query failed for %s: %s", package, exc)
        return {
            "package": package,
            "compatible": True,  # assume compatible if we can't check
            "unknown": True,
            "requires_python": "?",
            "note": "Could not query PyPI",
        }

    info = data.get("info", {})
    current_version = info.get("version", "")
    requires_python = info.get("requires_python") or ""

    if not requires_python:
        return {
            "package": package,
            "version": current_version,
            "compatible": True,
            "unknown": True,
            "requires_python": "(none specified)",
            "note": "No Requires-Python metadata",
        }

    # Parse the floor from requires_python (e.g., ">=3.8" → [3, 8])
    floor_match = re.search(r">=\s*(\d+(?:\.\d+)*)", requires_python)
    if not floor_match:
        return {
            "package": package,
            "version": current_version,
            "compatible": True,
            "unknown": True,
            "requires_python": requires_python,
            "note": "Cannot parse constraint",
        }

    req_parts = _parse_version(floor_match.group(1))
    if not req_parts:
        return None

    # Check: does the package SUPPORT our target?
    # If requires-python is ">=3.8", it supports 3.12 (target >= floor)
    compatible = target_parts >= req_parts

    # Also check for upper bounds like "<4" or "<=3.11"
    upper_match = re.search(r"<\s*(\d+(?:\.\d+)*)", requires_python)
    if upper_match and compatible:
        upper_parts = _parse_version(upper_match.group(1))
        if upper_parts and target_parts >= upper_parts:
            compatible = False

    return {
        "package": package,
        "version": current_version,
        "compatible": compatible,
        "requires_python": requires_python,
    }


def handle_update_deps_interactive(ctx: UpgradeContext, mode: str) -> dict:
    """Find alternative versions of incompatible deps.

    For each dependency that doesn't support the target Python version,
    queries PyPI for older versions that DO support it and presents
    them as alternatives the user can choose.

    Both preview and execute return the same data — this is a read-only
    analysis. The user applies changes manually (editing requirements files).
    """
    if ctx.language != "python":
        return {
            "ok": True,
            "can_apply": False,
            "preview_type": "info",
            "summary": "Dependency alternatives only available for Python",
        }

    # First, run the compatibility check to find incompatible deps
    compat_result = handle_check_dep_compat_pypi(ctx, mode)
    if not compat_result.get("ok"):
        return compat_result

    findings = compat_result.get("findings", [])
    incompatible = [f for f in findings if not f.get("compatible") and not f.get("unknown")]

    if not incompatible:
        return {
            "ok": True,
            "can_apply": False,
            "preview_type": "info",
            "summary": "All dependencies are compatible — no alternatives needed",
        }

    target_parts = _parse_version(ctx.target_floor)
    if not target_parts:
        return {"ok": False, "error": f"Cannot parse target version: {ctx.target_floor}"}

    # For each incompatible dep, find compatible versions
    alternatives = []
    for dep in incompatible:
        pkg = dep.get("package", "")
        if not pkg:
            continue

        alt_versions = _find_compatible_versions(pkg, target_parts, ctx.target_floor)
        alternatives.append({
            "package": pkg,
            "current_version": dep.get("version", ""),
            "requires_python": dep.get("requires_python", ""),
            "compatible_versions": alt_versions[:5],  # top 5 alternatives
        })

    return {
        "ok": True,
        "can_apply": False,  # user picks versions manually
        "preview_type": "findings",
        "summary": f"Found alternatives for {len(alternatives)} incompatible package(s)",
        "detail": (
            "These packages don't support Python {target} in their latest version. "
            "Below are older versions that do. Update your requirements accordingly."
        ).format(target=ctx.target_floor),
        "findings": [
            {
                "package": a["package"],
                "note": (
                    f"Current {a['current_version']} ({a['requires_python']}) → "
                    + (
                        ", ".join(
                            f"{v['version']} ({v['requires_python']})"
                            for v in a["compatible_versions"]
                        )
                        if a["compatible_versions"]
                        else "no compatible version found"
                    )
                ),
                "compatible": False,
            }
            for a in alternatives
        ],
    }


def _find_compatible_versions(
    package: str,
    target_parts: list[int],
    target_str: str,
) -> list[dict]:
    """Query PyPI for versions of a package that support the target Python.

    Returns a list of {version, requires_python} sorted newest-first.
    """
    try:
        url = f"https://pypi.org/pypi/{package}/json"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=_PYPI_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return []

    releases = data.get("releases", {})
    compatible = []

    for ver, files in releases.items():
        if not files:
            continue
        # Skip pre-releases
        if any(c in ver for c in ("a", "b", "rc", "dev", "post")):
            continue

        # Find requires_python from file metadata
        requires_python = None
        for f in files:
            rp = f.get("requires_python")
            if rp:
                requires_python = rp
                break

        if not requires_python:
            continue

        # Check if target satisfies requires_python
        floor_match = re.search(r">=\s*(\d+(?:\.\d+)*)", requires_python)
        if not floor_match:
            continue

        req_parts = _parse_version(floor_match.group(1))
        if not req_parts:
            continue

        if target_parts >= req_parts:
            # Also check upper bound
            upper_match = re.search(r"<\s*(\d+(?:\.\d+)*)", requires_python)
            if upper_match:
                upper_parts = _parse_version(upper_match.group(1))
                if upper_parts and target_parts >= upper_parts:
                    continue

            compatible.append({
                "version": ver,
                "requires_python": requires_python,
            })

    # Sort by version descending
    compatible.sort(
        key=lambda a: [int(x) for x in a["version"].split(".")[:3] if x.isdigit()],
        reverse=True,
    )

    return compatible


def _parse_version(v: str) -> list[int] | None:
    """Parse version string to integer list."""
    try:
        return [int(x) for x in v.split(".")]
    except (ValueError, AttributeError):
        return None
