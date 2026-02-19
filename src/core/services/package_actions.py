"""
Package management — observe & act operations.

Extracted from package_ops.py. Handles:
- Outdated package checking (pip, npm, go, cargo)
- Security auditing (pip-audit, npm audit, cargo audit)
- Package listing (pip, npm)
- Install & update operations

Channel-independent.
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path

from src.core.services.package_ops import (
    _run,
    _PACKAGE_MANAGERS,
    _detect_pm_for_dir,
)

logger = logging.getLogger(__name__)


def _pip_cmd(*args: str) -> list[str]:
    """Build a pip command using the current interpreter.

    Uses ``sys.executable -m pip`` so pip always runs in the same
    environment as the application — regardless of PATH.
    """
    return [sys.executable, "-m", "pip", *args]


# ═══════════════════════════════════════════════════════════════════
#  Internal helpers
# ═══════════════════════════════════════════════════════════════════


def _resolve_manager(project_root: Path) -> str | None:
    """Auto-detect the primary package manager for the project root."""
    managers = _detect_pm_for_dir(project_root)
    return managers[0]["id"] if managers else None


# ═══════════════════════════════════════════════════════════════════
#  Observe — outdated
# ═══════════════════════════════════════════════════════════════════


def package_outdated(project_root: Path, *, manager: str | None = None) -> dict:
    """Check for outdated packages.

    Returns:
        {"ok": True, "manager": str, "outdated": [...]} or {"error": "..."}
    """
    if not manager:
        manager = _resolve_manager(project_root)
    if not manager:
        return {"error": "No package manager detected"}

    spec = _PACKAGE_MANAGERS.get(manager)
    if not spec:
        return {"error": f"Unknown package manager: {manager}"}

    if not shutil.which(spec["cli"]):
        return {"error": f"{spec['cli']} not installed"}

    if manager == "pip":
        return _pip_outdated(project_root)
    elif manager == "npm":
        return _npm_outdated(project_root)
    elif manager == "go":
        return _go_outdated(project_root)
    elif manager == "cargo":
        return _cargo_outdated(project_root)
    else:
        return {"error": f"Outdated check not implemented for {spec['name']}"}


def _pip_outdated(project_root: Path) -> dict:
    """Check outdated pip packages."""
    r = _run(
        _pip_cmd("list", "--outdated", "--format", "json"),
        cwd=project_root,
        timeout=30,
    )
    if r.returncode != 0:
        return {"error": r.stderr.strip() or "pip list --outdated failed"}

    try:
        packages = json.loads(r.stdout)
    except json.JSONDecodeError:
        packages = []

    outdated = [
        {
            "name": p.get("name", ""),
            "current": p.get("version", ""),
            "latest": p.get("latest_version", ""),
            "type": p.get("latest_filetype", ""),
        }
        for p in packages
    ]

    return {"ok": True, "manager": "pip", "outdated": outdated, "count": len(outdated)}


def _npm_outdated(project_root: Path) -> dict:
    """Check outdated npm packages."""
    r = _run(
        ["npm", "outdated", "--json"],
        cwd=project_root,
        timeout=30,
    )
    # npm outdated returns exit code 1 when outdated packages exist
    try:
        data = json.loads(r.stdout) if r.stdout.strip() else {}
    except json.JSONDecodeError:
        data = {}

    outdated = [
        {
            "name": name,
            "current": info.get("current", ""),
            "wanted": info.get("wanted", ""),
            "latest": info.get("latest", ""),
            "type": info.get("type", ""),
        }
        for name, info in data.items()
    ]

    return {"ok": True, "manager": "npm", "outdated": outdated, "count": len(outdated)}


def _go_outdated(project_root: Path) -> dict:
    """Check outdated Go modules."""
    r = _run(
        ["go", "list", "-u", "-m", "-json", "all"],
        cwd=project_root,
        timeout=30,
    )
    if r.returncode != 0:
        return {"error": r.stderr.strip() or "go list failed"}

    outdated = []
    # go list -json outputs one JSON object per line (not an array)
    for line in r.stdout.strip().split("}\n{"):
        line = line.strip()
        if not line.startswith("{"):
            line = "{" + line
        if not line.endswith("}"):
            line = line + "}"
        try:
            mod = json.loads(line)
            update = mod.get("Update")
            if update:
                outdated.append({
                    "name": mod.get("Path", ""),
                    "current": mod.get("Version", ""),
                    "latest": update.get("Version", ""),
                })
        except json.JSONDecodeError:
            continue

    return {"ok": True, "manager": "go", "outdated": outdated, "count": len(outdated)}


def _cargo_outdated(project_root: Path) -> dict:
    """Check outdated Cargo dependencies (requires cargo-outdated)."""
    if not shutil.which("cargo-outdated"):
        # Fallback: just check Cargo.toml exists
        return {
            "ok": True,
            "manager": "cargo",
            "outdated": [],
            "count": 0,
            "note": "Install cargo-outdated for full analysis: cargo install cargo-outdated",
        }

    r = _run(
        ["cargo", "outdated", "--format", "json"],
        cwd=project_root,
        timeout=60,
    )
    if r.returncode != 0:
        return {"error": r.stderr.strip() or "cargo outdated failed"}

    try:
        data = json.loads(r.stdout)
        deps = data.get("dependencies", [])
    except json.JSONDecodeError:
        deps = []

    outdated = [
        {
            "name": d.get("name", ""),
            "current": d.get("project", ""),
            "latest": d.get("latest", ""),
        }
        for d in deps
    ]

    return {"ok": True, "manager": "cargo", "outdated": outdated, "count": len(outdated)}


# ═══════════════════════════════════════════════════════════════════
#  Observe — security audit
# ═══════════════════════════════════════════════════════════════════


def package_audit(project_root: Path, *, manager: str | None = None) -> dict:
    """Run a security audit on dependencies.

    Returns:
        {"ok": True, "manager": str, "vulnerabilities": int, "output": str}
        or {"error": "..."}
    """
    if not manager:
        manager = _resolve_manager(project_root)
    if not manager:
        return {"error": "No package manager detected"}

    spec = _PACKAGE_MANAGERS.get(manager)
    if not spec:
        return {"error": f"Unknown package manager: {manager}"}

    if not shutil.which(spec["cli"]):
        return {"error": f"{spec['cli']} not installed"}

    if manager == "pip":
        return _pip_audit(project_root)
    elif manager == "npm":
        return _npm_audit(project_root)
    elif manager == "cargo":
        return _cargo_audit(project_root)
    else:
        return {"error": f"Audit not implemented for {spec['name']}"}


def _pip_audit(project_root: Path) -> dict:
    """Run pip-audit (if installed)."""
    if not shutil.which("pip-audit"):
        return {
            "ok": True,
            "manager": "pip",
            "vulnerabilities": 0,
            "output": "pip-audit not installed. Install with: pip install pip-audit",
            "available": False,
        }

    r = _run(
        ["pip-audit", "--format", "json"],
        cwd=project_root,
        timeout=120,
    )

    try:
        data = json.loads(r.stdout) if r.stdout.strip() else {}
        vulns = data.get("dependencies", [])
        vuln_count = sum(len(d.get("vulns", [])) for d in vulns if d.get("vulns"))
    except json.JSONDecodeError:
        vuln_count = 0

    return {
        "ok": True,
        "manager": "pip",
        "vulnerabilities": vuln_count,
        "output": r.stdout.strip()[:2000],
        "available": True,
    }


def _npm_audit(project_root: Path) -> dict:
    """Run npm audit."""
    r = _run(
        ["npm", "audit", "--json"],
        cwd=project_root,
        timeout=60,
    )

    try:
        data = json.loads(r.stdout) if r.stdout.strip() else {}
        vuln_count = data.get("metadata", {}).get("vulnerabilities", {})
        total = sum(vuln_count.values()) if isinstance(vuln_count, dict) else 0
    except json.JSONDecodeError:
        total = 0

    return {
        "ok": True,
        "manager": "npm",
        "vulnerabilities": total,
        "output": r.stdout.strip()[:2000],
        "available": True,
    }


def _cargo_audit(project_root: Path) -> dict:
    """Run cargo audit (if installed)."""
    if not shutil.which("cargo-audit"):
        return {
            "ok": True,
            "manager": "cargo",
            "vulnerabilities": 0,
            "output": "cargo-audit not installed. Install with: cargo install cargo-audit",
            "available": False,
        }

    r = _run(
        ["cargo", "audit", "--json"],
        cwd=project_root,
        timeout=60,
    )

    try:
        data = json.loads(r.stdout) if r.stdout.strip() else {}
        vuln_count = len(data.get("vulnerabilities", {}).get("list", []))
    except json.JSONDecodeError:
        vuln_count = 0

    return {
        "ok": True,
        "manager": "cargo",
        "vulnerabilities": vuln_count,
        "output": r.stdout.strip()[:2000],
        "available": True,
    }


# ═══════════════════════════════════════════════════════════════════
#  Observe — package listing
# ═══════════════════════════════════════════════════════════════════


def package_list(project_root: Path, *, manager: str | None = None) -> dict:
    """List installed/declared packages.

    Returns:
        {"ok": True, "manager": str, "packages": [...]}
    """
    if not manager:
        manager = _resolve_manager(project_root)
    if not manager:
        return {"error": "No package manager detected"}

    spec = _PACKAGE_MANAGERS.get(manager)
    if not spec or not shutil.which(spec["cli"]):
        return {"error": f"{manager} not available"}

    if manager == "pip":
        return _pip_list(project_root)
    elif manager == "npm":
        return _npm_list(project_root)
    else:
        return {"error": f"List not implemented for {spec['name']}"}


def _pip_list(project_root: Path) -> dict:
    """List installed pip packages."""
    r = _run(_pip_cmd("list", "--format", "json"), cwd=project_root, timeout=15)
    if r.returncode != 0:
        return {"error": r.stderr.strip() or "pip list failed"}

    try:
        packages = json.loads(r.stdout)
    except json.JSONDecodeError:
        packages = []

    return {
        "ok": True,
        "manager": "pip",
        "packages": [
            {"name": p.get("name", ""), "version": p.get("version", "")}
            for p in packages
        ],
        "count": len(packages),
    }


def _npm_list(project_root: Path) -> dict:
    """List installed npm packages."""
    r = _run(
        ["npm", "list", "--json", "--depth=0"],
        cwd=project_root,
        timeout=15,
    )

    try:
        data = json.loads(r.stdout) if r.stdout.strip() else {}
        deps = data.get("dependencies", {})
    except json.JSONDecodeError:
        deps = {}

    packages = [
        {"name": name, "version": info.get("version", "")}
        for name, info in deps.items()
    ]

    return {
        "ok": True,
        "manager": "npm",
        "packages": packages,
        "count": len(packages),
    }


# ═══════════════════════════════════════════════════════════════════
#  Act — install & update
# ═══════════════════════════════════════════════════════════════════


def package_install(project_root: Path, *, manager: str | None = None) -> dict:
    """Install dependencies.

    Returns:
        {"ok": True, "output": "..."} or {"error": "..."}
    """
    if not manager:
        manager = _resolve_manager(project_root)
    if not manager:
        return {"error": "No package manager detected"}

    spec = _PACKAGE_MANAGERS.get(manager)
    if not spec or not shutil.which(spec["cli"]):
        return {"error": f"{manager} not available"}

    cmd_map = {
        "pip": _pip_cmd("install", "-e", "."),
        "npm": ["npm", "ci"],
        "go": ["go", "mod", "download"],
        "cargo": ["cargo", "fetch"],
        "maven": ["mvn", "dependency:resolve", "-q"],
        "gradle": ["gradle", "dependencies", "--no-daemon", "-q"],
        "mix": ["mix", "deps.get"],
        "bundler": ["bundle", "install"],
    }

    cmd = cmd_map.get(manager)
    if not cmd:
        return {"error": f"Install not implemented for {spec['name']}"}

    r = _run(cmd, cwd=project_root, timeout=300)
    if r.returncode != 0:
        return {"error": r.stderr.strip() or f"{cmd[0]} install failed"}

    return {"ok": True, "manager": manager, "output": r.stdout.strip()[:2000]}


def package_update(
    project_root: Path,
    *,
    package: str | None = None,
    manager: str | None = None,
) -> dict:
    """Update packages.

    Args:
        package: Specific package to update (default: all).
        manager: Package manager to use (default: auto-detect).

    Returns:
        {"ok": True, "output": "..."} or {"error": "..."}
    """
    if not manager:
        manager = _resolve_manager(project_root)
    if not manager:
        return {"error": "No package manager detected"}

    spec = _PACKAGE_MANAGERS.get(manager)
    if not spec or not shutil.which(spec["cli"]):
        return {"error": f"{manager} not available"}

    if manager == "pip":
        if package:
            cmd = _pip_cmd("install", "--upgrade", package)
        else:
            cmd = _pip_cmd("install", "--upgrade", "-e", ".")
    elif manager == "npm":
        if package:
            cmd = ["npm", "update", package]
        else:
            cmd = ["npm", "update"]
    elif manager == "go":
        if package:
            cmd = ["go", "get", "-u", package]
        else:
            cmd = ["go", "get", "-u", "./..."]
    elif manager == "cargo":
        cmd = ["cargo", "update"]
        if package:
            cmd.extend(["-p", package])
    else:
        return {"error": f"Update not implemented for {spec['name']}"}

    r = _run(cmd, cwd=project_root, timeout=300)
    if r.returncode != 0:
        return {"error": r.stderr.strip() or "Update failed"}

    return {
        "ok": True,
        "manager": manager,
        "package": package or "all",
        "output": r.stdout.strip()[:2000],
    }
